# Pixiis

Controller-first Windows game launcher with voice control. Tauri 2 +
React 19 + Rust.

Scans Steam (registry → `libraryfolders.vdf` → `appmanifest_*.acf`)
and common game folders (`C:\Program Files`, drive-root `Games`,
`SteamLibrary`, `GOG Games`, `Epic Games` directories), then presents
a controller-friendly grid with one accent colour and zero bouncy
animations.

## Build

```bash
./build.sh           # release → NSIS installer .exe
./build.sh dev       # hot-reloading dev shell, no installer
./build.sh clean     # nuke node_modules / target / dist, then build
```

Prereqs and detail in [`BUILD.md`](BUILD.md). On a fresh Windows box
you'll need: VS 2026 with the *Desktop development with C++* workload,
Rust stable (`rustup`), Node 20+, CMake, and NSIS.

## Layout

```
.
├── README.md           this file
├── BUILD.md            prerequisites + troubleshooting
├── build.sh            one-shot build wrapper
├── package.json        React app
├── index.html
├── public/
├── src/                ── React (Vite + TS)
│   ├── api/            bridge.ts + auto-generated types/
│   ├── components/
│   ├── pages/
│   └── styles/         editorial design tokens
├── src-tauri/          ── Rust (Tauri 2 backend)
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── icons/
│   └── src/
│       ├── lib.rs
│       ├── commands/   ── invoke handlers, split per subsystem
│       ├── controller/ ── gilrs poller + macro engine
│       ├── library/    ── Steam + folder scanners
│       ├── services/   ── RAWG / Twitch / YouTube / OAuth
│       └── types.rs    ── ts-rs auto-exports to src/api/types/
└── resources/          bundled config + theme defaults
```

## Configuration

External services need API keys at runtime via env vars (the proper
config loader is a future Phase):

```
PIXIIS_RAWG_API_KEY
PIXIIS_YT_API_KEY
PIXIIS_TWITCH_CLIENT_ID
PIXIIS_TWITCH_CLIENT_SECRET
```

Without keys those services silently return empty — the launcher
itself still works for local + Steam library + controller nav.

## Status

| Subsystem | State |
|---|---|
| Tauri window + tray (Open / Scan / Quit) | shipped |
| React → Rust `invoke()` bridge | shipped |
| Steam scanner + folder scanner | shipped |
| Controller (gilrs poller + macros) | shipped |
| External services (RAWG / Twitch / YouTube / OAuth) | shipped |
| Type contracts (ts-rs auto-export) | shipped |
| Editorial design tokens | shipped |
| Voice transcription (whisper-rs) | scaffolded — commands return `Ok(default)`, no audio pipeline yet |
| Other storefronts (Epic, GOG, EA, Xbox/UWP, Start Menu) | not yet — folder scanner catches most catalogues |

The legacy Python launcher lives on the `master` branch if you want to
fall back. Phase-0 spike crates (whisper-rs benchmark, Kokoro TTS
benchmark, faster-whisper baseline, UWP detection) are reachable
through their `wave1/*-spike` branches.
