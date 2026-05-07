# Pixiis

A controller-first Windows game launcher with voice control and an
editorial typographic feel. Tauri 2 + Vite 8 + React 19 on a Rust core.

<!-- TODO: screenshot -->

## What it is

Pixiis scans every storefront on the box (Steam, Xbox / Game Pass, Epic,
GOG, EA, Start Menu shortcuts, manual entries, and free-form folder
scans), then presents the result as a single quiet grid you can drive
with a controller, your voice, or a mouse. The chrome is restrained —
warm near-black, off-white serif display type, a single accent reserved
for the play action and focus rings, no springs or bounces.

The application originally shipped as a PySide6 + faster-whisper +
Kokoro Python program. Version 0.2.0 is a complete reimplementation: a
Rust crate via Tauri 2, a Vite 8 + React 19 + TypeScript frontend, and
type contracts auto-generated from the Rust side via ts-rs.

## Features

- **Multi-storefront scanning** — Steam, Xbox / UWP / Game Pass, Epic,
  GOG, EA, Start Menu (.lnk parsing, no PowerShell shell-out), folder
  scanner, manual entries
- **Voice control** — local STT via whisper-rs (whisper.cpp bindings),
  TTS via Kokoro v1.0 ONNX through `ort 2.0`, optional Silero VAD, all
  on-device
- **Controller** — gilrs-driven background poller for tray-mode macros,
  Web Gamepad API for foreground UI, configurable button + combo macros
- **Editorial UI** — Fraunces serif for display, Inter for body,
  single-accent rule, no springs, cross-fade transitions, focus rings
  on every interactive element
- **Game metadata** — RAWG (cover art, ratings, genres), YouTube
  trailers, Twitch live streams (when you sign in)
- **System integration** — system tray (Open / Scan / Quit), single-
  instance enforcement, optional autostart, frameless 1280×800 window
  with HTML drag region
- **Onboarding** — five-step first-run flow (welcome, library scan,
  voice mic test, controller test, done)

## Install

End users: download the NSIS installer from the [Releases
page](https://github.com/your-org/pixiis/releases) — the artefact is
named `Pixiis_0.2.0_x64-setup.exe`. The installer is per-user and
needs no administrator rights; Pixiis lands in
`%LOCALAPPDATA%\Programs\Pixiis\` with a Start Menu shortcut.

External services need API keys before they return data — set them
through the Settings page or via environment variables (see
[Configuration](#configuration)).

## Build from source

End-to-end Windows recipe — toolchain, build script, troubleshooting —
lives in [BUILD.md](BUILD.md). The short version, from a clean checkout
on a Windows box with the prereqs installed:

```bash
./build.sh           # release → NSIS installer .exe
./build.sh dev       # hot-reloading dev shell, no installer
./build.sh clean     # nuke node_modules / target / dist, then build
```

## Architecture

Pixiis is two co-resident processes inside a single Tauri shell:

```
┌──────────────────── Tauri main window ────────────────────┐
│                                                            │
│  React 19 webview                  Rust crate (pixiis_lib) │
│  ─────────────────                 ────────────────────────│
│  Pages (Home / Game / …)   ←──┐                            │
│  Components / hooks            │                           │
│  bridge.ts (typed invoke)  ────┼──── invoke handlers ──┐   │
│  api/types/* (ts-rs codegen)   │                       │   │
│                                │   commands/           │   │
│                                │     library / voice / │   │
│                                │     controller /      │   │
│                                │     services / config │   │
│                                │                       │   │
│                                │   subsystems          │   │
│                                │     library/  ── 7 providers
│                                │     controller/ ─ gilrs poller + macros
│                                │     voice/ ────── whisper + kokoro + cpal
│                                │     services/ ─── RAWG, Twitch, YouTube, OAuth
│                                │                                       │
│                                └─── tray (Open / Scan / Quit) ─────────┘
│                                     single-instance, autostart, fs, dialog, shell plugins
└────────────────────────────────────────────────────────────┘
```

The webview talks to Rust through `@tauri-apps/api/core::invoke()`,
typed via `frontend/src/api/bridge.ts`. Every wire-format struct is
defined once in `src-tauri/src/types.rs` with `#[derive(TS)]`; running
`cargo test` regenerates `src/api/types/*.ts` so the frontend never
drifts.

The controller poller runs at ~60 Hz on a tokio task; it forwards
events to the foreground UI (which prefers the Web Gamepad API for
input latency) and only fires macros while the main window is hidden,
so navigation keys never double-fire while the app is focused.

## Controller mapping

Default macros from `resources/default_config.toml` — override per-user
through the Settings page.

| Input              | Action            | Mode  | Notes                              |
|--------------------|-------------------|-------|------------------------------------|
| A (button 0)       | `voice_record`    | hold  | Hold to talk; release ends capture |
| B (button 1)       | `navigate_ui`     | press | Back / cancel                      |
| X (button 2)       | `navigate_ui`     | press | Search                             |
| Y (button 3)       | `favorite_toggle` | press | Toggle favorite on focused tile    |
| LB + RB (combo 4+5)| `navigate_ui`     | combo | Open file manager                  |

Voice trigger is configurable (`rt`, `lt`, `hold_y`, `hold_x`); deadzone,
hold-threshold (ms before a press becomes a hold), combo window, and
vibration are all in the `[controller]` section of `config.toml`.

## Configuration

Configuration lives in `%APPDATA%\pixiis\` on Windows:

```
%APPDATA%\pixiis\
├── config.toml             merged user config; .onboarded sentinel sits next to it
├── library_overlay.json    favorites + playtime cache
├── images\                 RAWG cover-art LRU cache
├── models\
│   ├── whisper\            ggml-base.en-q5_0.bin (first-run copy from bundle)
│   ├── silero\             silero_vad.onnx (when feature is enabled)
│   └── kokoro\             kokoro-v1.0.onnx + voices-v1.0.bin
└── .onboarded              one-shot first-run marker
```

`config.toml` is TOML; the defaults shipped in
`resources/default_config.toml` are the source of truth for keys and
shapes. The main sections:

- `[voice]` — STT model, compute device (`auto` / `cuda` / `cpu`),
  energy threshold, VAD backend, sample rate
- `[voice.tts]` — enabled flag, Kokoro voice id, speed
- `[voice.transcription]` — beam sizes, language, no-speech / compression
  thresholds
- `[controller]` — deadzone, hold/combo windows, voice trigger,
  vibration enable
- `[controller.macros]` — see the table above
- `[library]` — provider allow-list, scan interval, favorites
- `[library.steam]` / `[library.folders]` / `[library.manual]` —
  provider-specific paths and entries
- `[services.rawg]` / `[services.youtube]` / `[services.twitch]` — API
  credentials; without them the relevant feature silently returns empty
- `[daemon]` — autostart toggle

For headless setups, the same keys can be supplied as environment
variables:

```
PIXIIS_RAWG_API_KEY
PIXIIS_YT_API_KEY
PIXIIS_TWITCH_CLIENT_ID
PIXIIS_TWITCH_CLIENT_SECRET
PIXIIS_TWITCH_TOKEN
```

In-app, the Settings page exposes the same controls grouped by
Library / Voice / Controller / Services / About.

## Project layout

```
.
├── README.md
├── CHANGELOG.md
├── BUILD.md
├── DESIGN_SPEC.md
├── build.sh
├── package.json                npm workspace for the React frontend
├── index.html
├── public/                     static favicon, fonts, etc.
├── resources/                  bundled at install: default_config.toml, models/
├── src/                        React + TypeScript frontend
│   ├── api/                    bridge.ts, LibraryContext, ts-rs-generated types/
│   ├── components/             NavBar, GameTile, SearchBar
│   ├── hooks/                  useController, useSpatialNav, …
│   ├── pages/                  Home, GameDetail, Settings, Onboarding, FileManager
│   ├── styles/                 tokens.css + animations.css + PALETTE.md
│   └── App.tsx
├── src-tauri/                  Rust crate (Tauri 2 backend)
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── icons/
│   └── src/
│       ├── lib.rs              builder, plugins, tray, setup
│       ├── types.rs            wire-format DTOs + ts-rs export hooks
│       ├── error.rs
│       ├── commands/           invoke handlers, split per subsystem
│       ├── controller/         gilrs backend, mapping, macro engine
│       ├── library/            steam, xbox/, epic, gog, ea, startmenu, folder, cache
│       ├── services/           rawg, twitch, youtube, oauth, image_loader, vibration
│       └── voice/              transcriber, audio_capture, vad, pipeline,
│                               text_injection, tts, model
└── agents/                     migration journals (STATUS.md is the canonical record)
```

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgments

- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) and
  [whisper-rs](https://github.com/tazz4843/whisper-rs) — local STT
- [Kokoro](https://github.com/hexgrad/kokoro) — TTS voice model
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — the
  reference baseline for the Phase 0 spike
- [Tauri](https://tauri.app/), [Vite](https://vitejs.dev/), and
  [React](https://react.dev/) — application shell and frontend
- [gilrs](https://gitlab.com/gilrs-project/gilrs) — controller input
- [ort](https://ort.pyke.io/) — ONNX runtime bindings for Kokoro and
  Silero
- [Fraunces](https://fonts.google.com/specimen/Fraunces) and
  [Inter](https://rsms.me/inter/) — display and body type
