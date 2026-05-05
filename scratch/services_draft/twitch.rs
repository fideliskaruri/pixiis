//! Twitch Helix API client — top live streams for a game.
//!
//! Mirrors `src/pixiis/services/twitch.py`. Two auth modes:
//!
//! * **Implicit grant**: `access_token` already obtained via OAuth (browser).
//! * **Client-credentials**: exchange `client_id` + `client_secret` for a
//!   bearer token at `id.twitch.tv/oauth2/token`.

use std::sync::RwLock;

use reqwest::Client;
use serde::Deserialize;
use urlencoding::encode;

use crate::error::{AppError, AppResult};
use crate::types::TwitchStream;

const TOKEN_URL: &str = "https://id.twitch.tv/oauth2/token";
const HELIX_BASE: &str = "https://api.twitch.tv/helix";

#[derive(Clone, Debug, Default)]
pub struct TwitchAuth {
    pub client_id: String,
    pub client_secret: String,
    pub access_token: String,
}

pub struct TwitchClient {
    http: Client,
    auth: RwLock<TwitchAuth>,
}

impl TwitchClient {
    pub fn new(http: Client, auth: TwitchAuth) -> Self {
        Self {
            http,
            auth: RwLock::new(auth),
        }
    }

    /// OAuth implicit-grant authorize URL (browser flow).
    pub fn authorize_url(client_id: &str, redirect_uri: &str) -> String {
        format!(
            "https://id.twitch.tv/oauth2/authorize?client_id={cid}&redirect_uri={ruri}&response_type=token&scope=",
            cid = encode(client_id),
            ruri = encode(redirect_uri),
        )
    }

    /// Top 5 live streams for `game_name`. Returns an empty Vec when not
    /// configured (no client_id) or when category resolution fails.
    pub async fn get_top_streams(&self, game_name: &str) -> AppResult<Vec<TwitchStream>> {
        let client_id = {
            let g = self.auth.read().unwrap();
            g.client_id.clone()
        };
        if client_id.is_empty() {
            return Ok(Vec::new());
        }

        // Make sure we have an access token, exchanging client-credentials if
        // we only have a secret.
        self.ensure_token().await?;

        let token = {
            let g = self.auth.read().unwrap();
            g.access_token.clone()
        };
        if token.is_empty() {
            return Ok(Vec::new());
        }

        let game_id = match self.resolve_category(&client_id, &token, game_name).await? {
            Some(id) => id,
            None => return Ok(Vec::new()),
        };

        self.fetch_streams(&client_id, &token, &game_id).await
    }

    async fn ensure_token(&self) -> AppResult<()> {
        let (have_token, have_secret, client_id, client_secret) = {
            let g = self.auth.read().unwrap();
            (
                !g.access_token.is_empty(),
                !g.client_secret.is_empty(),
                g.client_id.clone(),
                g.client_secret.clone(),
            )
        };
        if have_token || !have_secret {
            return Ok(());
        }

        let url = std::env::var("PIXIIS_TWITCH_TOKEN_URL_OVERRIDE")
            .unwrap_or_else(|_| TOKEN_URL.to_string());
        let resp = self
            .http
            .post(&url)
            .form(&[
                ("client_id", client_id.as_str()),
                ("client_secret", client_secret.as_str()),
                ("grant_type", "client_credentials"),
            ])
            .send()
            .await
            .map_err(http_err)?;
        if !resp.status().is_success() {
            return Ok(()); // leave token empty; caller returns empty Vec
        }

        #[derive(Deserialize)]
        struct TokenResponse {
            access_token: String,
        }
        let body: TokenResponse = resp.json().await.map_err(http_err)?;
        self.auth.write().unwrap().access_token = body.access_token;
        Ok(())
    }

    async fn resolve_category(
        &self,
        client_id: &str,
        token: &str,
        game_name: &str,
    ) -> AppResult<Option<String>> {
        #[derive(Deserialize)]
        struct CategoryEntry {
            id: String,
        }
        #[derive(Deserialize)]
        struct CategoryResponse {
            #[serde(default)]
            data: Vec<CategoryEntry>,
        }

        let base = helix_base();
        let url = format!("{base}/search/categories");
        let resp = self
            .http
            .get(&url)
            .header("Client-Id", client_id)
            .bearer_auth(token)
            .query(&[("query", game_name)])
            .send()
            .await
            .map_err(http_err)?;

        if resp.status().as_u16() == 401 {
            self.auth.write().unwrap().access_token.clear();
            return Ok(None);
        }
        if !resp.status().is_success() {
            return Ok(None);
        }

        let body: CategoryResponse = resp.json().await.map_err(http_err)?;
        Ok(body.data.into_iter().next().map(|c| c.id))
    }

    async fn fetch_streams(
        &self,
        client_id: &str,
        token: &str,
        game_id: &str,
    ) -> AppResult<Vec<TwitchStream>> {
        #[derive(Deserialize)]
        struct StreamEntry {
            #[serde(default)]
            user_name: String,
            #[serde(default)]
            title: String,
            #[serde(default)]
            viewer_count: u64,
            #[serde(default)]
            thumbnail_url: String,
        }
        #[derive(Deserialize)]
        struct StreamsResponse {
            #[serde(default)]
            data: Vec<StreamEntry>,
        }

        let base = helix_base();
        let url = format!("{base}/streams");
        let resp = self
            .http
            .get(&url)
            .header("Client-Id", client_id)
            .bearer_auth(token)
            .query(&[("game_id", game_id), ("first", "5")])
            .send()
            .await
            .map_err(http_err)?;

        if resp.status().as_u16() == 401 {
            self.auth.write().unwrap().access_token.clear();
            return Ok(Vec::new());
        }
        if !resp.status().is_success() {
            return Ok(Vec::new());
        }

        let body: StreamsResponse = resp.json().await.map_err(http_err)?;
        let streams = body
            .data
            .into_iter()
            .map(|s| TwitchStream {
                stream_url: if s.user_name.is_empty() {
                    String::new()
                } else {
                    format!("https://twitch.tv/{}", s.user_name)
                },
                user_name: s.user_name,
                title: s.title,
                viewer_count: s.viewer_count,
                thumbnail_url: s.thumbnail_url,
            })
            .collect();
        Ok(streams)
    }
}

fn helix_base() -> String {
    std::env::var("PIXIIS_TWITCH_HELIX_OVERRIDE").unwrap_or_else(|_| HELIX_BASE.to_string())
}

fn http_err(e: reqwest::Error) -> AppError {
    AppError::Other(format!("twitch http: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use httpmock::prelude::*;
    use serde_json::json;

    #[tokio::test]
    async fn empty_when_no_client_id() {
        let client = TwitchClient::new(Client::new(), TwitchAuth::default());
        let streams = client.get_top_streams("Hades").await.unwrap();
        assert!(streams.is_empty());
    }

    #[tokio::test]
    async fn fetches_top_streams_with_existing_token() {
        let server = MockServer::start_async().await;
        let cat_mock = server.mock(|when, then| {
            when.method(GET)
                .path("/search/categories")
                .query_param("query", "Hades")
                .header("client-id", "CID")
                .header("authorization", "Bearer TOK");
            then.status(200).json_body(json!({
                "data": [{"id": "999"}]
            }));
        });
        let streams_mock = server.mock(|when, then| {
            when.method(GET)
                .path("/streams")
                .query_param("game_id", "999")
                .query_param("first", "5");
            then.status(200).json_body(json!({
                "data": [
                    {"user_name": "stream_a", "title": "speedrun", "viewer_count": 1234, "thumbnail_url": "t1"},
                    {"user_name": "stream_b", "title": "casual",   "viewer_count": 99,   "thumbnail_url": "t2"}
                ]
            }));
        });

        std::env::set_var("PIXIIS_TWITCH_HELIX_OVERRIDE", server.base_url());
        let client = TwitchClient::new(
            Client::new(),
            TwitchAuth {
                client_id: "CID".into(),
                access_token: "TOK".into(),
                ..Default::default()
            },
        );
        let streams = client.get_top_streams("Hades").await.unwrap();
        std::env::remove_var("PIXIIS_TWITCH_HELIX_OVERRIDE");

        cat_mock.assert();
        streams_mock.assert();
        assert_eq!(streams.len(), 2);
        assert_eq!(streams[0].user_name, "stream_a");
        assert_eq!(streams[0].stream_url, "https://twitch.tv/stream_a");
        assert_eq!(streams[0].viewer_count, 1234);
    }

    #[tokio::test]
    async fn empty_when_category_not_found() {
        let server = MockServer::start_async().await;
        server.mock(|when, then| {
            when.method(GET).path("/search/categories");
            then.status(200).json_body(json!({"data": []}));
        });
        std::env::set_var("PIXIIS_TWITCH_HELIX_OVERRIDE", server.base_url());
        let client = TwitchClient::new(
            Client::new(),
            TwitchAuth {
                client_id: "CID".into(),
                access_token: "TOK".into(),
                ..Default::default()
            },
        );
        let streams = client.get_top_streams("ObscureGame").await.unwrap();
        std::env::remove_var("PIXIIS_TWITCH_HELIX_OVERRIDE");
        assert!(streams.is_empty());
    }

    #[test]
    fn authorize_url_encodes_components() {
        let url = TwitchClient::authorize_url("abc&def", "http://localhost:1234/cb");
        assert!(url.contains("client_id=abc%26def"));
        assert!(url.contains("redirect_uri=http%3A%2F%2Flocalhost%3A1234%2Fcb"));
        assert!(url.contains("response_type=token"));
    }
}
