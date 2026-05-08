# Wave 3 — Rust backend audit

Hunt was scoped to issues that would surface as compile errors or first-launch
panics on Windows MSVC against Tauri 2 / cpal 0.15 / whisper-rs 0.16 /
windows-rs 0.58. Performed by reading code against the registry sources for
each crate (`whisper-rs-0.16.0`, `windows-0.58.0`, `ort-2.0.0-rc.10`).

Branch: `worktree-agent-a8209a2359d58ed40` (reset to `wave1/integration` HEAD
`c4a71bb`).

Verification — TTS sanity check is clean:

```
$ grep -rn "TtsEngine\|voice_speak\|Kokoro\|kokoro" src-tauri/
(no output)
```

## Findings

### Core

- **`src-tauri/src/main.rs`** — OK. One-line shim, `windows_subsystem = "windows"`
  gate is correct.
- **`src-tauri/src/lib.rs`** — FIXED.
  - L240–242: `load_default_macros` listed `../resources/default_config.toml`
    twice; the second slot was meant to hold the project-root fallback
    (`resources/default_config.toml`) so `cargo run` from the repo root finds
    the file. Mirrored the candidate list in `commands/config.rs`.
  - L75 / L85: `cache_dir.clone()` and `app_data_dir.clone()` in setup were
    cloning a value used exactly once. Removed the redundant `.clone()`s.
  - Plugin order, `manage()` ordering, tray construction, invoke_handler list,
    and `voice_slot` graceful-degradation pattern are all correct.
- **`src-tauri/src/types.rs`** — OK. Every enum has a stable `slug()` /
  `serde(rename_all)` mapping, ts-rs derives are consistent, `Default` is on
  every wire-shape used as a JSON return value, and `AppEntry` helpers handle
  missing-metadata cleanly.
- **`src-tauri/src/error.rs`** — OK. `From` impls cover every error type the
  command layer actually surfaces (io, serde_json, tauri). `Serialize` flattens
  to a string the JS side can render as `Error.message`.

### Library subsystem

- **`src-tauri/src/library/mod.rs`** — OK.
  - `scan_with_progress` correctly wraps each provider in
    `panic::catch_unwind(AssertUnwindSafe(...))`, decodes the panic payload
    into a string, and pushes a `ProviderState::Error` row instead of
    collapsing the whole pass.
  - `library:scan:done` emit on L231 fires the count, which `LibraryContext`
    on the frontend uses to refetch.
  - `library:scan:progress` matches `SCAN_PROGRESS_EVENT` constant; per-state
    rows fire before AND after each provider runs.
  - `iso_utc_now` + `civil_from_days` is the standard Howard-Hinnant civil
    date algorithm; verified against the reference paper.
  - The voice subsystem uses `dirs::data_dir()` (Python parity), but `lib.rs`
    uses Tauri's `app_data_dir()` for library cache + config — that's
    deliberate (different bundle-id-suffixed dir) and matches the comments on
    each call site.
- **`src-tauri/src/library/steam.rs`** — FIXED.
  - `parse_library_folders` used `splitn(2, '"')` on lines like
    `"path"  "C:\\..."`. `splitn(2, ...)` yields at most two pieces, so the
    third `parts.next()` always returned `None` and `rest` was `""` — every
    secondary library folder was silently dropped, leaving only the main
    `<steam>/steamapps`. Bumped to `splitn(3, '"')` so the iterator yields
    `["", "path", "  \"C:\\...\""]` as the surrounding code already assumed.
  - `is_available` correctly gates on `cfg!(target_os = "windows")` AND a
    resolved install path; `find_steam_path` honours config override before
    registry before the two well-known fallback paths.
- **`src-tauri/src/library/xbox/mod.rs`** — OK.
  - `is_available` gates on `cfg!(target_os = "windows")` AND
    `enumerator.is_available()`. The `WinRtEnumerator` constructor calls
    `CoInitializeEx` once via `Once`, and `is_available` re-runs it before
    probing `PackageManager::new()` so the runtime check is honest even after
    a `with_enumerator(...)` injection.
  - `XboxProvider::with_enumerator` is `#[allow(dead_code)]` with a clear
    "Test/DI hook" comment — that's an intentional surface for the unit tests
    in the same file; not stale.
  - `scan_with` short-circuits framework packages, skip-list hits, blank
    display names, and unresolvable executables — none of those branches can
    panic.
- **`src-tauri/src/library/xbox/winrt.rs`** — OK. Each per-package
  `Id()/Name()/FamilyName()/InstalledLocation()` call uses `let Ok(...) else {
  continue }`, so a single broken package can't take down the scan. The
  `windows::Management::Deployment::PackageManager` API matches the 0.58
  bindings.
- **`src-tauri/src/library/xbox/manifest.rs`** — OK. quick-xml 0.31 API used
  correctly (`local_name()`, `unescape_value()`, `read_event_into`). Empty
  `Executable=""` is filtered to `None` so the caller can fall back to
  `MicrosoftGame.Config`.
- **`src-tauri/src/library/epic.rs` / `gog.rs` / `ea.rs` / `manual.rs` /
  `folder.rs` / `startmenu.rs`** — OK.
  - All `is_available` checks are pure (no I/O panics, no unwraps).
  - All `scan` bodies tolerate missing dirs / unreadable files via
    `.ok()?` / `let Ok(...) else { continue }`.
  - ID prefixes are consistent: `steam:<appid>`, `epic:<AppName>`,
    `gog:<game_id>`, `ea:<contentId>` (or filename fallback), `manual:<slug>`,
    `folder:<slug>`, `sm:<slug>`, and Xbox uses the bare `family_name` to
    match the AUMID launch URL.
- **`src-tauri/src/library/cache.rs`** — OK. `serde_json::to_vec_pretty` is
  wrapped in an `io::Error::new(ErrorKind::Other, ...)` for the public
  signature; minor stylistic note that `io::Error::other(...)` (1.74+) is the
  newer idiom but it's not a bug.
- **`src-tauri/src/commands/library.rs`** — OK. `library_scan` correctly
  offloads to `spawn_blocking`, surfaces a JoinError as `AppError::Other`
  (no `unwrap_or_default()` swallow), and returns `{entries, providers}` in
  the `ScanResult` shape the frontend already consumes.

### Voice subsystem

- **`src-tauri/src/voice/mod.rs`** — OK. Re-exports `VoiceService` from
  pipeline; module list matches files on disk.
- **`src-tauri/src/voice/pipeline.rs`** — OK.
  - `Stream` is `!Send` on Windows, but `AudioCapture` doesn't *own* the
    `Stream`: the stream lives on a dedicated `voice-capture` thread, and
    `AudioCapture` only holds a `Sender<()>` (Send) and a `JoinHandle<()>`
    (Send) — verified `Session: Send` so `Mutex<Option<Session>>` is sound.
  - `start()` order is correct: spawn transcribe worker first (so it can
    receive `Live`/`Final`), then rolling worker, then the cpal capture
    callback that pushes into the shared buffer.
  - `stop()` order is correct: flip `recording=false`, drop capture (joins
    the cpal thread cleanly), snapshot buffer, send `Final` then `Stop`,
    join rolling, `recv_timeout(30s)` for the final transcript, join
    transcriber. Stop is robust against a transcription stall via the
    timeout.
  - Whisper-rs 0.16 API usage is correct (`new_with_params`, `create_state`,
    `full(params, samples)`, `full_n_segments`, `get_segment`,
    `to_str_lossy`).
  - `voice:partial` / `voice:final` / `voice:state` event names match the
    spec — the frontend listens for these in `useVoice.ts`.
- **`src-tauri/src/voice/audio_capture.rs`** — OK.
  - cpal 0.15 build uses the four-arg form
    (`build_input_stream(config, data_cb, err_cb, timeout: None)`) — verified
    against 0.15 source.
  - F32/I16/U16 sample formats covered; downmix and linear resample are
    bounds-safe (early-return on empty / same rate, `lo` always non-negative
    given non-negative `src`).
  - Both `stop()` and `Drop` send to a `bounded(1)` channel and `let _ =`
    the result, so a double-stop or drop-after-stop is harmless.
- **`src-tauri/src/voice/vad.rs`** — OK.
  - `Vad: Send + Sync` declared on the trait so `Arc<dyn Vad>` cleanly stores
    in `VoiceService`.
  - Silero impl is feature-gated and uses `Mutex<SileroState>` so `is_speech`
    can stay `&self` while owning the LSTM state.
  - `build()` falls back to `EnergyVad` in three cases: feature off, path
    `None`, path doesn't exist, or `try_load` fails — covers every realistic
    runtime miss.
- **`src-tauri/src/voice/transcriber.rs`** — OK. Pads short clips to ≥1 s,
  applies the energy gate before paying whisper cost, drops repeated 4-gram
  hallucinations. `WhisperContext` is `Send + Sync` per whisper-rs 0.16
  (`unsafe impl` on `WhisperInnerContext`); `Arc<Transcriber>` is sound.
- **`src-tauri/src/voice/text_injection.rs`** — OK. `r#type: INPUT_KEYBOARD`
  is the correct field name in windows-rs 0.58 (`INPUT_TYPE` newtype, not raw
  u32). `SendInput(&[INPUT], i32)` matches the 0.58 signature; the
  per-keystroke pacing matches `text_injection.py::KEYSTROKE_DELAY`.
- **`src-tauri/src/voice/model.rs`** — OK.
  - User dir uses `dirs::data_dir().join("pixiis").join("models")` — Python
    parity, `%APPDATA%/pixiis/...` on Windows.
  - `find_bundled` checks the executable-relative path AND two source-tree
    fallbacks for `cargo run`.
  - First-run copy from bundle into user dir falls through to using the
    bundled path when the copy fails, so the worst case is a second
    first-run after upgrade — never a panic.
- **`src-tauri/src/commands/voice.rs`** — OK. `voice_speak` is gone; the
  surface is exactly the six commands declared in `lib.rs`'s
  `invoke_handler!` list. `VoiceServiceSlot` cleanly returns
  `AppError::Other("voice unavailable: ...")` when the model wasn't found at
  startup, and the `transcript_log` getter no-ops to `[]` rather than erroring
  if voice never came up.

### Controller

- **`src-tauri/src/controller/mod.rs`** — OK. The 60 Hz poller uses
  `tokio::time::interval(16ms)` with `MissedTickBehavior::Delay` so a stall
  doesn't fire a burst, and skips macro emission while the main window is
  visible (foreground UI owns input via the Web Gamepad API). Connection
  state is updated every tick so `controller_get_state` stays fresh even
  when macros are skipped.
- **`src-tauri/src/controller/backend.rs`** — OK. `Backend::new` is gated by
  `#[allow(clippy::result_large_err)]` (gilrs::Error is genuinely fat); the
  poll loop synthesises D-pad axis events out of D-pad button presses so
  downstream sees one shape. `connected_gamepads` is `#[allow(dead_code)]`
  because it'll surface via the `voice_get_devices`-style command later;
  intentional.
- **`src-tauri/src/controller/mapping.rs`** — OK. Hold detection only fires
  once per press (`held_fired` flag), combo detection clears `recent_downs`
  on match so the same pair doesn't re-trigger while held, axis events are
  deadzone-gated. Tests cover all four paths.
- **`src-tauri/src/controller/macros.rs`** — OK. `register` replaces by
  trigger-string, which is a fine policy — case differences would create
  duplicate entries, but the wire format is canonical lowercase. Garbage
  rows in TOML are silently dropped (matches Python).
- **`src-tauri/src/commands/controller.rs`** — OK. `vibration_pulse` is
  intentionally `Err(AppError::NotImplemented)` per the Pane 9 split — the
  real impl lives in `services::vibration::pulse` and will be wired in once
  the services state is available here.

### Services

- **`src-tauri/src/services/mod.rs`** — OK. `ServicesContainer::new` shares
  one reqwest `Client` (with `gzip + rustls-tls`) across every sub-client.
  Build failure aborts startup via `?` in `lib.rs::setup`, but rustls-tls
  init never fails on Windows MSVC in practice.
- **`src-tauri/src/services/rawg.rs`** — OK. Empty API key → `default()`,
  HTTP error → `default()`. Cache is keyed on lowercased name AND `__id_<n>`
  for detail lookups; cache poison is silently dropped (`cache.lock().ok()?`)
  which means a poisoned mutex resets to a missed-cache, not a panic.
- **`src-tauri/src/services/twitch.rs`** — OK. Auth is parking-lot-free
  `RwLock` (std), but lock holders never panic so poisoning is a non-issue.
  401 clears the cached token so the next call re-runs client-credentials.
  `authorize_url` URL-encodes both args.
- **`src-tauri/src/services/youtube.rs`** — OK. Empty API key → `None`.
  Thumbnail fallback chain is high → medium → default.
- **`src-tauri/src/services/oauth.rs`** — OK. axum 0.7 server binds on `0`
  port, reports it back via `port()`, fragment-bridge HTML re-issues `/token`
  with the hash, watchdog tears it down after 10 min so a dropped flow can't
  leak. The `services_oauth_start` command immediately drops the flow
  (acknowledged in the comment); the watchdog covers the leak window.
- **`src-tauri/src/services/image_loader.rs`** — OK. SHA-256-12-byte hash
  for the disk filename, LRU memory cache (cap 256), `convertFileSrc`-style
  URL on read.
- **`src-tauri/src/services/vibration.rs`** — OK. XInput call is
  `cfg(windows)`-gated; the off-thread shut-off uses `tokio::spawn` when a
  runtime is present, falls back to `std::thread::spawn` when called from a
  blocking context. Non-Windows is a true no-op, parameters discarded by
  pattern.
- **`src-tauri/src/commands/services.rs`** — OK. Every command returns an
  empty / `None` result (not an error) when its prerequisite config is
  missing — matches the no-network-error pattern the frontend expects.

### Config

- **`src-tauri/src/commands/config.rs`** — OK.
  - `write_document` is atomic-ish: write to `<path>.tmp`, then `fs::rename`.
    On Windows that's a `MoveFileEx`-equivalent, atomic for a same-volume
    rename.
  - `merge_into_table` recursively descends into nested objects so siblings
    (and their `toml_edit` decoration / comments) survive — covered by
    `merge_preserves_sibling_keys`, `merge_handles_deep_nesting`,
    `merge_creates_missing_tables`, `json_view_round_trips_scalars`.
  - Missing-file fallback: `load_document` reads the bundled
    `default_config.toml`, then an empty doc — and on parse failure of an
    *existing* user file, returns `AppError::Other` so the UI can surface
    the corruption instead of clobbering it. The bundled default is read by
    the same multi-candidate path resolver as `lib.rs::load_default_macros`.
  - `app_get_onboarded` / `app_set_onboarded` use Tauri's `app_data_dir` and
    create the parent on write — first-run safe.

### Cargo.toml

- OK. whisper-rs at 0.16, cpal at 0.15, ort `=2.0.0-rc.10` pinned with
  `load-dynamic` so onnxruntime.dll is dlopen'd, `silero-vad` feature
  declares `["dep:ort", "dep:ndarray"]` so optional deps activate together.
  No leftover TTS deps (`libloading`, `zip`, `byteorder`, `num_cpus` all
  absent from the manifest). Windows-only deps (`windows`, `winreg`) are
  under `[target.'cfg(windows)'.dependencies]`.

## Bugs found / fixed

| # | Severity | File | Status |
|---|----------|------|--------|
| 1 | HIGH — silent data loss on every Steam scan beyond the main library folder | `src-tauri/src/library/steam.rs` | FIXED |
| 2 | LOW — dev fallback never resolved when running from project root | `src-tauri/src/lib.rs` (`load_default_macros`) | FIXED |
| 3 | TRIVIAL — redundant `.clone()` on a value used once | `src-tauri/src/lib.rs` (setup) | FIXED |

## What's left

- Nothing blocking. The remaining `#[allow(dead_code)]` markers
  (`metadata_for`, `XboxProvider::with_enumerator`, `Backend::connected_gamepads`,
  `MapperEvent::Axis`) are all intentional forward-compat hooks documented in
  context comments.
- `vibration_pulse` deliberately returns `AppError::NotImplemented`; that's
  the Pane 8 / Pane 9 split, not a defect to fix here.
- The `services_oauth_start` watchdog leak window (10 min after a cancelled
  flow) is acknowledged in the existing TODO comment; not in scope for this
  audit.
