//! Local OAuth callback server.
//!
//! Mirrors `src/pixiis/services/oauth.py`:
//!
//! * Binds an axum server to `127.0.0.1:0` (random port).
//! * `GET /callback?…` with query string → finishes (auth-code grant).
//! * `GET /callback` with no query → serves the JS bridge page that reads
//!   `window.location.hash` and re-issues `GET /token?…` (Twitch implicit).
//! * `GET /token?…` → finishes.
//!
//! Once finished, the server shuts down on its own. `start()` opens the
//! browser at the supplied auth URL.

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::extract::{Query, State};
use axum::http::header;
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::Router;
use tokio::net::TcpListener;
use tokio::sync::oneshot;
use tokio::time::timeout;

use crate::error::{AppError, AppResult};

const FRAGMENT_HTML: &str = r#"<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Connecting...</title>
<style>
  body { font-family: system-ui, sans-serif; background: #1a1a2e; color: #e0e0e8;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
  .card { text-align: center; padding: 2rem; }
  .ok   { color: #4ade80; font-size: 1.5rem; }
  .fail { color: #f87171; font-size: 1.5rem; }
</style></head><body>
<div class="card" id="msg">Connecting&hellip;</div>
<script>
(function() {
  var hash = window.location.hash.substring(1);
  if (!hash) {
    document.getElementById("msg").innerHTML = '<span class="fail">No token received.</span>';
    return;
  }
  var xhr = new XMLHttpRequest();
  xhr.open("GET", "/token?" + hash, true);
  xhr.onload = function() {
    document.getElementById("msg").innerHTML = '<span class="ok">Connected! You can close this tab.</span>';
  };
  xhr.onerror = function() {
    document.getElementById("msg").innerHTML = '<span class="fail">Failed to send token to app.</span>';
  };
  xhr.send();
})();
</script></body></html>"#;

const SUCCESS_HTML: &str = r#"<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Done</title>
<style>
  body { font-family: system-ui, sans-serif; background: #1a1a2e; color: #4ade80;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
</style></head><body>
<h2>Connected! You can close this tab.</h2>
</body></html>"#;

/// Owns one in-flight OAuth flow.
///
/// Lifecycle: `start()` -> caller opens browser -> `wait_for_result()` blocks
/// (with timeout) until the redirect lands. Server self-terminates on success
/// or via `cancel()` for early teardown. If neither fires, a built-in
/// watchdog (10 min by default) tears it down so dropped flows don't leak.
pub struct OAuthFlow {
    port: u16,
    result_rx: Mutex<Option<oneshot::Receiver<HashMap<String, String>>>>,
    shutdown: Arc<Mutex<Option<oneshot::Sender<()>>>>,
}

const DEFAULT_WATCHDOG: Duration = Duration::from_secs(600);

#[derive(Clone)]
struct AppState {
    finish: Arc<Mutex<Option<oneshot::Sender<HashMap<String, String>>>>>,
    shutdown: Arc<Mutex<Option<oneshot::Sender<()>>>>,
}

impl OAuthFlow {
    /// Bind to a random localhost port and start serving. Returns once the
    /// listener is bound — the server itself runs in a spawned tokio task.
    pub async fn start() -> AppResult<Self> {
        let listener = TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], 0)))
            .await
            .map_err(AppError::Io)?;
        let port = listener.local_addr().map_err(AppError::Io)?.port();

        let (result_tx, result_rx) = oneshot::channel();
        let (shutdown_tx, shutdown_rx) = oneshot::channel();
        let shutdown = Arc::new(Mutex::new(Some(shutdown_tx)));

        let state = AppState {
            finish: Arc::new(Mutex::new(Some(result_tx))),
            shutdown: Arc::clone(&shutdown),
        };

        let app = Router::new()
            .route("/callback", get(handle_callback))
            .route("/token", get(handle_token))
            .with_state(state);

        tokio::spawn(async move {
            let _ = axum::serve(listener, app)
                .with_graceful_shutdown(async move {
                    let _ = shutdown_rx.await;
                })
                .await;
        });

        // Watchdog: ensures the server shuts down even if the OAuthFlow is
        // dropped without anyone calling wait_for_result/cancel (e.g. the
        // user never completes the browser flow).
        {
            let watchdog = Arc::clone(&shutdown);
            tokio::spawn(async move {
                tokio::time::sleep(DEFAULT_WATCHDOG).await;
                if let Some(tx) = watchdog.lock().unwrap().take() {
                    let _ = tx.send(());
                }
            });
        }

        Ok(Self {
            port,
            result_rx: Mutex::new(Some(result_rx)),
            shutdown,
        })
    }

    pub fn port(&self) -> u16 {
        self.port
    }

    /// Block (async) until the redirect arrives or `dur` elapses.
    pub async fn wait_for_result(&self, dur: Duration) -> AppResult<HashMap<String, String>> {
        let rx = self
            .result_rx
            .lock()
            .unwrap()
            .take()
            .ok_or_else(|| AppError::Other("oauth result already consumed".into()))?;
        let res = match timeout(dur, rx).await {
            Ok(Ok(params)) => Ok(params),
            Ok(Err(_)) => Err(AppError::Other("oauth flow cancelled".into())),
            Err(_) => Err(AppError::Other("oauth timeout".into())),
        };
        // Whether timeout, cancel, or success — make sure the server is down.
        self.cancel();
        res
    }

    /// Tear down the local server early without waiting for a callback.
    pub fn cancel(&self) {
        if let Some(tx) = self.shutdown.lock().unwrap().take() {
            let _ = tx.send(());
        }
    }
}

async fn handle_callback(
    State(state): State<AppState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if params.is_empty() {
        // Fragment-based redirect — serve the JS bridge.
        return html(FRAGMENT_HTML);
    }
    finish(&state, params);
    html(SUCCESS_HTML)
}

async fn handle_token(
    State(state): State<AppState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if params.is_empty() {
        return ([(header::CONTENT_TYPE, "text/plain; charset=utf-8")], "no params").into_response();
    }
    finish(&state, params);
    ([(header::CONTENT_TYPE, "text/plain; charset=utf-8")], "ok").into_response()
}

fn finish(state: &AppState, params: HashMap<String, String>) {
    if let Some(tx) = state.finish.lock().unwrap().take() {
        let _ = tx.send(params);
    }
    // Defer shutdown briefly so the response can flush before the listener
    // stops. 100ms matches the Python implementation's threading.Thread spawn.
    let shutdown = Arc::clone(&state.shutdown);
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(100)).await;
        if let Some(tx) = shutdown.lock().unwrap().take() {
            let _ = tx.send(());
        }
    });
}

fn html(body: &'static str) -> Response {
    (
        [
            (header::CONTENT_TYPE, "text/html; charset=utf-8"),
            (header::ACCESS_CONTROL_ALLOW_ORIGIN, "*"),
        ],
        body,
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn callback_with_query_completes_flow() {
        let flow = OAuthFlow::start().await.unwrap();
        let port = flow.port();

        let url = format!("http://127.0.0.1:{port}/callback?code=abc&state=xyz");
        let client = reqwest::Client::new();
        let body = client
            .get(&url)
            .send()
            .await
            .unwrap()
            .text()
            .await
            .unwrap();
        assert!(body.contains("Connected"));

        let params = flow.wait_for_result(Duration::from_secs(2)).await.unwrap();
        assert_eq!(params.get("code").map(String::as_str), Some("abc"));
        assert_eq!(params.get("state").map(String::as_str), Some("xyz"));
    }

    #[tokio::test]
    async fn fragment_bridge_completes_via_token() {
        let flow = OAuthFlow::start().await.unwrap();
        let port = flow.port();
        let client = reqwest::Client::new();

        let body = client
            .get(format!("http://127.0.0.1:{port}/callback"))
            .send()
            .await
            .unwrap()
            .text()
            .await
            .unwrap();
        assert!(body.contains("/token"));

        let body = client
            .get(format!(
                "http://127.0.0.1:{port}/token?access_token=TOKEN&token_type=bearer"
            ))
            .send()
            .await
            .unwrap()
            .text()
            .await
            .unwrap();
        assert_eq!(body, "ok");

        let params = flow.wait_for_result(Duration::from_secs(2)).await.unwrap();
        assert_eq!(params.get("access_token").map(String::as_str), Some("TOKEN"));
    }

    #[tokio::test]
    async fn timeout_returns_error() {
        let flow = OAuthFlow::start().await.unwrap();
        let err = flow.wait_for_result(Duration::from_millis(50)).await;
        assert!(err.is_err());
    }
}
