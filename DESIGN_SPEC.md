# Pixiis — Design Spec

This document is the high-level shape of the application. Tokens,
components, and command bodies are out of scope here — read the code
referenced from each section for detail.

## Design language

Pixiis is editorial. The look is closer to a magazine spread than a
dashboard or a games console: warm near-black ground, off-white serif
display type, generous whitespace, and a single accent. Restraint is
the design.

The complete palette + scale spec lives in
[`src/styles/PALETTE.md`](src/styles/PALETTE.md). The condensed rules:

- **Colour.** Six tokens. `--bg` `#0F0E0C`, `--bg-elev` `#15130F`,
  `--text` `#EDE9DD`, `--text-dim` `#8A8478`, `--text-mute` `#5C574E`,
  `--rule` `rgba(237,233,221,.08)`, `--accent` `#C5402F`. The accent
  appears in exactly two places: the `▶ PLAY` button and
  `:focus-visible` outlines (also exposed as `--focus`). Anything else
  uses `--text*`.
- **Type.** Two fonts — Fraunces for display (`--font-display`), Inter
  for body (`--font-body`). IBM Plex Mono is the fallback for
  monospace IDs and paths only. Both web fonts load via Google Fonts
  CDN with `display: swap`. The `.label` primitive is Inter 500
  uppercase with `letter-spacing: 0.18em` and `--text-dim` for
  small-caps section headings.
- **Spacing.** 4 px base. `--s-xs` 4 / `--s-sm` 8 / `--s-md` 16 /
  `--s-lg` 24 / `--s-xl` 48 / `--s-2xl` 96.
- **Motion.** No springs, no overshoots, no bounces. Default ease
  `cubic-bezier(0.4, 0, 0.2, 1)`. Three durations — `--t-fast` 120 ms
  for hover nudges, `--t-base` 200 ms for cross-fade and tile focus,
  `--t-slow` 400 ms for larger view transitions. Tile focus is a 1 px
  → 2 px border with a `1.0 → 1.04` scale, no spring. Toast in 150 ms
  / out 300 ms (asymmetric for legibility). All animations collapse
  to ~1 ms under `prefers-reduced-motion: reduce`.

Tokens, primitives, and animation classes live in
[`src/styles/tokens.css`](src/styles/tokens.css) and
[`src/styles/animations.css`](src/styles/animations.css). New code
should reference tokens, never hex literals.

## Page structure

The application is a single Tauri webview with five routed pages plus
the onboarding entry. Routing is `react-router-dom` 7 with the
shell-level redirect logic in [`src/App.tsx`](src/App.tsx).

| Route             | Component             | Notes                                                                  |
|-------------------|-----------------------|------------------------------------------------------------------------|
| `/`               | `HomePage`            | Featured tile, Continue Playing rail, full library grid, search        |
| `/game/:id`       | `GameDetailPage`      | Hero (banner-with-overlay or capped poster), meta sidebar, About body  |
| `/settings`       | `SettingsPage`        | Two-column editorial form: Library / Voice / Controller / Services / About |
| `/onboarding`     | `OnboardingPage`      | Five steps: Welcome / Library scan / Voice mic / Controller / Done     |
| `/files`          | `FileManagerPage`     | Manual launcher entries — list on the left, edit form on the right     |

All non-onboarding pages render under a top-level `<NavBar>` that
carries the `data-tauri-drag-region` attribute for window drag (Tauri
2 ignores `-webkit-app-region`). The onboarding route is chrome-less
and owns its own back / skip affordances.

A first-launch redirect in `App.tsx` checks `getOnboarded()` once on
mount; an absent marker forces `/onboarding`. The marker is a sentinel
file at `%APPDATA%\pixiis\.onboarded` written by
`app_set_onboarded(true)` either through "Done" or "Skip setup".

Component primitives live in [`src/components/`](src/components/):
`NavBar`, `GameTile`, `SearchBar`. Hooks (`useController`,
`useSpatialNav`, …) live in [`src/hooks/`](src/hooks/).

## Tauri command surface

The frontend talks to the Rust crate exclusively through
`@tauri-apps/api/core::invoke()`, wrapped in
[`src/api/bridge.ts`](src/api/bridge.ts). Every command is registered
in [`src-tauri/src/lib.rs`](src-tauri/src/lib.rs) and grouped by
subsystem under
[`src-tauri/src/commands/`](src-tauri/src/commands/). High-level shape:

- **library** — `library_get_all`, `library_scan`, `library_launch`,
  `library_toggle_favorite`, `library_search`, `library_get_icon`,
  `library_get_metadata`, `playtime_get`. Reads from the seven
  providers in [`src-tauri/src/library/`](src-tauri/src/library/) and
  persists favourites + playtime in a JSON overlay.
- **voice** — `voice_start`, `voice_stop`, `voice_get_devices`,
  `voice_set_device`, `voice_inject_text`, `voice_get_transcript_log`,
  `voice_speak`. Backed by the pipeline in
  [`src-tauri/src/voice/`](src-tauri/src/voice/). STT emits
  `voice:partial` / `voice:final` / `voice:state` Tauri events; TTS is
  fire-and-forget and runs on a dedicated cpal output stream.
- **controller** — `controller_register_macro`, `controller_get_state`,
  `vibration_pulse`. Implementation in
  [`src-tauri/src/controller/`](src-tauri/src/controller/) with the
  gilrs poller spawned from `lib.rs::run::setup`.
- **services** — `services_twitch_streams`,
  `services_youtube_trailer`, `services_rawg_lookup`,
  `services_oauth_start`, `services_image_url`. Implementation in
  [`src-tauri/src/services/`](src-tauri/src/services/). Each service
  returns empty cleanly when its API key is absent.
- **config + app** — `config_get`, `config_set`, `config_reset`,
  `app_quit`, `app_show`, `app_set_autostart`, `app_get_onboarded`,
  `app_set_onboarded`. The config layer reads / merges TOML; the app
  layer is a thin shim over the window + autostart plugins.

The system tray emits a `tray://scan` event when the user picks Scan
Library; the frontend listens and calls `library_scan` itself, so the
poll path is identical to the Settings page button.

## Data model

The single source of truth for wire-format types is
[`src-tauri/src/types.rs`](src-tauri/src/types.rs). Every public
struct / enum derives `Serialize, Deserialize, TS` and exports to
`src/api/types/*.ts` whenever `cargo test` runs (the ts-rs hooks are
auto-generated). The frontend does not hand-write any boundary types.

The principal types:

- **`AppSource`** — `Steam | Xbox | Epic | Gog | Ea | Startmenu |
  Manual`. Storefront tag.
- **`AppEntry`** — id, name, source, launch_command, optional exe
  path, optional icon path, optional art url, free-form metadata map.
  Helpers compute favourite state, playtime display, "is game" vs
  app, last-played epoch.
- **`ControllerEvent` / `AxisEvent` / `ButtonState`** — emitted by the
  poller on the `controller:event` channel.
- **`MacroAction` / `MacroMode` / `ActionKind`** — describes a single
  macro binding loaded from `[controller.macros]`.
- **`TranscriptionEvent`** — `voice:partial` / `voice:final` /
  `voice:state` payload shape.
- **`RawgGameData` / `TwitchStream` / `YouTubeTrailer`** — service
  response DTOs.
- **`Playtime` / `ControllerState` / `VoiceDevice`** — boundary
  helpers used by the `*_get_state` commands.

Editing `types.rs` and re-running `cargo test --bins` from
`src-tauri/` regenerates the matching `.ts` files in
`src/api/types/`. The build script declares
`rerun-if-changed=src/types.rs` so incremental rebuilds are correct.

## Background services

`lib.rs::run::setup` instantiates four services and registers them via
`app.manage(Arc<…>)`:

1. **`ControllerService`** — gilrs poller at ~60 Hz on a tokio task,
   loads macros from the bundled `default_config.toml`, only fires
   while the main window is hidden.
2. **`ServicesContainer`** — RAWG + Twitch + YouTube + image cache,
   wires keys from environment variables (interim) or the merged
   config.
3. **`LibraryService`** — runs the seven providers in declared order
   on each `library_scan`; first-write wins on the case-insensitive
   path dedup.
4. **`VoiceService` + `TtsEngine`** — Whisper STT (eager load at
   startup, costs 200–500 ms) and Kokoro TTS (lazy load on first
   `voice_speak`). Both gracefully degrade to a clean error if their
   model files are missing rather than panicking the app.

## Out of scope for this document

Each subsystem owns more detail than belongs here. The canonical
record of why each piece is shaped the way it is — the Phase 0 spike
results, the per-pane integration notes, the verification gaps — is
[`agents/STATUS.md`](agents/STATUS.md). The Windows build recipe and
troubleshooting list lives in [`BUILD.md`](BUILD.md).
