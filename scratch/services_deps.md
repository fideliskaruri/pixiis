# Pane 9 — services crate dependency sketch

Notes for `frontend/src-tauri/Cargo.toml` once the Tauri scaffold (Pane 5) lands.
Goal: a ServicesContainer that holds shared `reqwest::Client` + image cache state and exposes RAWG / Twitch / YouTube / OAuth / image / vibration as plain async Rust modules consumable by Tauri commands (Phase 5 will wire them).

## Runtime / async

| Crate | Version (rough) | Why |
|---|---|---|
| `tokio` | 1 | runtime; need `rt-multi-thread`, `macros`, `sync`, `time`, `fs` |
| `async-trait` | maybe not needed | only if we end up with trait objects across async boundaries |

## HTTP

| Crate | Features | Why |
|---|---|---|
| `reqwest` | `json`, `rustls-tls`, `gzip` | RAWG + Twitch Helix + YouTube Data API + image GET. Use `rustls` to avoid pulling OpenSSL on Windows. Disable default-features so we don't drag in `default-tls` (Schannel/OpenSSL). |
| `serde` | `derive` | model deserialization |
| `serde_json` | — | hand-rolled parsing for shapes that don't quite map to a struct |
| `urlencoding` | — | percent-encoding for query params and fragment forwarding |

Notes:
- A single shared `reqwest::Client` lives on `ServicesContainer`. Cloning is cheap (it's an `Arc` internally) but we still pass `&Client` where possible to avoid noise.
- Twitch needs custom `Client-Id` + `Authorization: Bearer …` headers per request — set them on the request, not the client (token can be refreshed mid-session).

## OAuth callback server

| Crate | Features | Why |
|---|---|---|
| `axum` | `tokio` | minimal local HTTP server; `Router::new().route("/callback", ..).route("/token", ..)` |
| `tower` | — | usually pulled in transitively by axum |
| `tokio` | `net`, `signal` | `TcpListener::bind("127.0.0.1:0")` to grab a random port |
| `webbrowser` | — | `webbrowser::open(auth_url)` matches Python's `webbrowser.open` semantics; avoids depending on `tauri::api::shell::open` until Pane 5 settles plugin choices |

The Python flow (oauth.py) supports two redirect shapes — query-based (auth-code) and fragment-based (Twitch implicit). We replicate that:
- `GET /callback?…` with query → parse, finish.
- `GET /callback` with no query → serve `_FRAGMENT_HTML` (JS reads `window.location.hash` and re-issues `GET /token?…`).
- `GET /token?…` → parse, finish.

After `_finish` the server should shut down. With axum the easiest pattern is a `tokio::sync::oneshot` that signals graceful-shutdown; the handlers grab the result and fire the shutdown.

## Image cache

| Crate | Why |
|---|---|
| `lru` | bounded in-memory cache (we do not need pixmaps any more — Tauri webview decodes; we just hand back a path/URL string per request) |
| `sha2` | mirror Python's sha256-prefix-as-filename trick (`hashlib.sha256(url).hexdigest()[:24]`). Note: the brief says `md5`, but matching Python keeps disk caches interchangeable across the migration window. **Defer to user** if they want md5. |
| `tokio::fs` | async file I/O |

Three-layer strategy:
1. Memory: `Mutex<LruCache<String, PathBuf>>` (cache the decoded path, not bytes — webview handles bytes).
2. Disk: `%APPDATA%/pixiis/images/{hash}{ext}` exists → return path.
3. Network: download bytes, write to disk, populate memory.

For the webview URL helper: Tauri 2 exposes paths via the `asset:` protocol when configured, which the brief alludes to. Actual surface depends on Pane 5's `tauri.conf.json`. Plan: emit a path through `tauri::path::PathResolver` and let Phase 5 wire the protocol; fall back to a `file://` URL with percent-encoding if no asset protocol is configured.

## Vibration

| Crate | Why |
|---|---|
| `gilrs` | shared with Pane 8. **Take `&Gilrs`**, never construct one. |
| `windows` (`Win32_UI_Input_XboxController`, `Win32_Foundation`) | direct `XInputSetState` fallback if gilrs ff support is unavailable on the target controller. |

Cross-platform notes:
- Non-Windows targets: vibration is a no-op (matches Python).
- Don't spawn a Tokio task for the duration timer if a `tokio::time::sleep` would do — just `tokio::spawn` a tiny fire-and-forget future that calls SetState(0,0) after `duration_ms`.

## md5 vs sha256 for image filenames

Brief says `md5`; Python uses `sha256[:24]`. Going with **sha256[:24]** to keep disk caches interoperable during the migration. Will surface this to the user for sign-off — md5 isn't security-relevant here so either works; the cost is just a one-time cache invalidation.

## Test deps (dev-dependencies)

| Crate | Why |
|---|---|
| `httpmock` | mocked HTTP for RAWG / Twitch / YouTube tests |
| `tokio` | `macros`, `rt-multi-thread` for `#[tokio::test]` |
| `tempfile` | scratch dirs for image-cache tests |
| `wiremock` | only if `httpmock` ergonomics fall short |

## Workspace concerns

- All these crates compile cleanly against `tauri 2.x` and target `x86_64-pc-windows-msvc`.
- `reqwest` w/ `rustls-tls` avoids the Windows-on-OpenSSL build mess.
- `axum` is the same major as in tauri's plugins — should be no diamond.

## Open questions for the user

1. md5 vs sha256 for image cache filenames? Sticking with sha256 unless told otherwise.
2. `webbrowser` crate vs `tauri::api::shell::open` for the OAuth flow — depends on whether Pane 5 enables the shell plugin. Default to caller-opens-the-URL (i.e., `start()` returns the `(port, auth_url)` and lets the Tauri command open it).
