# Pane 9 — services scaffold (RAWG / Twitch / YouTube / OAuth / image / vibration)

**Branch:** `wave1/services`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/pane9-services/`
**Wave:** 1 (Phase 5-prep — depends on Pane 5)

> Read `/mnt/d/code/python/pixiis/agents/CONTEXT.md` first.

## Mission

Port the **services layer** to Rust: HTTP clients, OAuth callback server, image cache, vibration. These are mostly mechanical — `reqwest` + `serde` + `tokio`. No IPC plumbing yet; you produce reusable modules that Phase 5 will wire as Tauri commands.

## Dependency

**Wait until `frontend/src-tauri/Cargo.toml` exists.** Same poll pattern.

While waiting:

1. Read these Python files for the contracts:
   - `src/pixiis/services/rawg.py`
   - `src/pixiis/services/twitch.py`
   - `src/pixiis/services/youtube.py`
   - `src/pixiis/services/oauth.py`
   - `src/pixiis/services/image_loader.py`
   - `src/pixiis/services/vibration.py`
2. Sketch crate dependencies in `scratch/services_deps.md`.

## Working directory

`/mnt/d/code/python/pixiis/.worktrees/pane9-services/`

Files land in `frontend/src-tauri/src/services/`.

## Deliverables

### 1. `frontend/src-tauri/src/services/mod.rs`

Module declarations + a `ServicesContainer` struct holding shared `reqwest::Client` + image cache state.

### 2. `services/rawg.rs`

Port `RawgClient`:
- `search_game(name: &str) -> Result<RawgGameData>` — calls `https://api.rawg.io/api/games?search=...`
- `get_game_details(id: u64) -> Result<RawgGameData>` — calls `https://api.rawg.io/api/games/{id}`
- In-memory cache (`Mutex<HashMap<String, RawgGameData>>` is fine).
- Use Pane 7's `RawgGameData` from `crate::types`.
- Reads API key from config: `services.rawg.api_key`.

### 3. `services/twitch.rs`

- `authorize_url(client_id: &str, redirect_uri: &str) -> String` — implicit-grant auth URL.
- `get_top_streams(game_name: &str) -> Result<Vec<TwitchStream>>` — uses `services.twitch.access_token` from config.
- Two auth modes: client-credentials (if secret set) or implicit-grant token already stored.

### 4. `services/youtube.rs`

- `get_trailer(game_name: &str) -> Result<Option<YouTubeTrailer>>` — calls YouTube Data API v3 with `services.youtube.api_key`.

### 5. `services/oauth.rs`

OAuth callback server using `axum`:
- `start(auth_url: &str) -> Result<u16>` — start local axum server on random port, return port. Open browser via `tauri::api::shell::open` (or store the URL and let the caller open).
- `wait_for_result(timeout: Duration) -> Result<HashMap<String, String>>` — block until callback received.
- Bridge HTML page identical to `oauth.py:22-50` for fragment-based grants (Twitch implicit).
- Once result captured, server shuts down.

### 6. `services/image_loader.rs`

- `request(url: &str) -> Result<PathBuf>` — async download to `%APPDATA%/pixiis/images/{md5}.{ext}`. Returns the local path.
- `as_tauri_url(path: &Path) -> String` — converts to a URL the webview can load: `https://asset.localhost/{percent_encoded}` or use `tauri::path::PathResolver`. Document which approach.
- Three-layer cache: memory (`LruCache`) → disk → network.

### 7. `services/vibration.rs`

- `pulse(left: u16, right: u16, duration_ms: u32)` — fire-and-forget vibration.
- Use `gilrs::Gilrs::ff_effect_factory` if available, else direct `windows::Win32::UI::Input::XboxController::XInputSetState`.
- Coordinate with Pane 8 — both touch gilrs. Make sure you don't double-init `Gilrs`. Probably best to take a `&Gilrs` reference rather than owning one.

### 8. Update `lib.rs`

`pub mod services;` and instantiate `ServicesContainer` in `setup`.

### 9. Replace command bodies (just these — implement, don't stub)

- `services_image_url`
- `services_twitch_streams` (returns empty Vec if no auth — log warning)
- `services_youtube_trailer`
- `services_oauth_start`

`library_get_metadata` (which calls RAWG) can also be implemented if straightforward.

## Acceptance criteria

- `cargo build` succeeds.
- Unit tests using mocked HTTP (`httpmock` crate) for RAWG search and Twitch streams.
- `services_image_url` works on a test URL: returns a `https://asset.localhost/...` URL.
- `STATUS.md` updated.

## Out of scope

- **Don't** implement library/voice commands.
- **Don't** touch the Tauri scaffold beyond adding `pub mod services;`.

## Reporting

- Update `agents/STATUS.md`.
- Commit to `wave1/services`.
