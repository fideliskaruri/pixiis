# Changelog

All notable changes to this project are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-05-07

### Changed

- Complete migration from PySide6 (Python) to Tauri 2 + Vite 8 +
  React 19 (Rust + TypeScript).
- Voice STT: `faster-whisper` → `whisper-rs` (whisper.cpp bindings).
  Phase 0 spike measured `whisper-rs` 2× faster than the Python
  baseline at the same RSS, transcript identical modulo a single comma
  in one pangram.
- Xbox / UWP detection: PowerShell `Get-AppxPackage` shell-out → direct
  WinRT `Management.Deployment.PackageManager` calls. Phase 0 spike
  measured the Rust path 2.2× faster than the PowerShell path with
  fewer false negatives (multi-`<Application>` manifests are now read
  correctly).
- Controller input: `pygame.joystick` → `gilrs` for the Rust background
  poller plus the Web Gamepad API for foreground UI; the poller only
  fires macros while the main window is hidden so navigation never
  double-fires.
- IPC: HTTP fetch against a local FastAPI sidecar →
  `@tauri-apps/api/core::invoke()` directly into the Rust crate.
- Type contracts: hand-maintained Pydantic models →
  `#[derive(ts_rs::TS)]` on the Rust side, regenerated into
  `src/api/types/*.ts` whenever `cargo test` runs.
- Window chrome: native PySide6 chrome → frameless 1280×800 Tauri window
  with HTML drag region (`data-tauri-drag-region`) on the navbar.
- Distribution: PyInstaller → `cargo tauri build` producing an NSIS
  per-user installer (`Pixiis_0.2.0_x64-setup.exe`).
- Configuration directory layout reorganised under `%APPDATA%\pixiis\`
  to host first-run copies of the bundled Whisper and Silero models
  alongside `config.toml`.

### Added

- **Editorial design language.** Warm near-black background, off-white
  type, Fraunces serif for display + Inter for body via Google Fonts
  CDN, single accent (`#C5402F`) reserved for the play button and
  focus rings, no springs, cross-fade transitions. Tokens documented
  in `src/styles/PALETTE.md`.
- **New page surface.** Home, GameDetail, Settings, Onboarding, and
  FileManager pages, each routed through `react-router-dom` 7 with a
  cross-fade between them.
- **Five-step onboarding flow** — Welcome / Library scan / Voice mic
  test / Controller test / Done — gated by an `.onboarded` marker in
  `%APPDATA%\pixiis\`.
- **Settings page** with two-column editorial layout covering Library
  (provider toggles, scan interval, manual scan), Voice (model, compute
  device, mic, energy threshold, hold-to-test), Controller (deadzone,
  hold threshold, vibration, voice trigger, live status), Services
  (RAWG / YouTube keys, Twitch OAuth) and About / autostart.
- **FileManager page** for manual entries — native Tauri pickers for
  executable / icon / working dir, duplicate-name validation, inline
  delete with confirm, post-edit `library_scan` refresh.
- **Game library scanners.** Steam (registry +
  `libraryfolders.vdf` + `appmanifest_*.acf`), Xbox / UWP (WinRT
  `PackageManager` + `AppxManifest.xml` + `MicrosoftGame.Config`),
  Epic (Manifests glob), GOG (registry walk + `goggalaxy://` URI),
  EA (InstallData JSON + `origin2://` URI, fallback exe walk),
  Start Menu (.lnk parsing via the `lnk` crate), folder scanner, and
  manual entries. Storefront entries win first-write dedup over the
  catch-all scanners.
- **Service layer.** RAWG metadata lookup (LRU + on-disk image cache),
  Twitch live-stream lookup with Helix OAuth, YouTube trailer search,
  generic OAuth callback server (axum on a local port).
- **Controller macro engine** with press / hold / combo modes, default
  bindings shipped in `resources/default_config.toml`, configurable
  voice trigger.
- **System tray** (Open / Scan / Quit) with single-instance enforcement
  — second launches focus the existing window.
- **Optional autostart** through `tauri-plugin-autostart`, toggled
  from the Settings page.
- **Vibration plugin** via direct XInput on Windows with a per-call
  amplitude / duration API.
- **Tauri capabilities** allow-list covering window controls, drag,
  shell, fs, dialog, single-instance, autostart.
- **Resource bundle** ships `resources/default_config.toml`, Whisper
  GGUF, and Silero ONNX; first run copies them into the per-user
  `%APPDATA%\pixiis\models\` tree.
- **Phase 0 spike crates** — `spike/whisper-bench`, `spike/kokoro-bench`,
  `spike/uwp-detect`, `spike/baseline` — held on `wave1/*-spike`
  branches as the empirical justification for each Rust replacement.

### Removed

- PySide6 main application, all Python UI code, and the FastAPI / IPC
  sidecar.
- PowerShell shell-out for Xbox / UWP enumeration.
- PS5-glass theme. The legacy `theme.css` is no longer imported (the
  file is still on disk pending a future deletion sweep).
- Hand-maintained Pydantic types in favour of `ts-rs` codegen.
- Text-to-speech (Kokoro ONNX). The codebase carries no TTS engine.

### Deprecated

- The legacy Python launcher remains accessible on the `master` branch
  for fallback only; it will not receive further changes.

### Fixed

- Multi-`<Application>` Xbox / UWP manifests no longer drop secondary
  AUMIDs — the Rust scanner reports 34 additional entries per box on
  average compared with the Python `Get-AppxPackage` script.
- Window drag now uses Tauri 2's HTML drag attribute rather than the
  ignored `-webkit-app-region` CSS property.
- Controller poller no longer fires macros while the foreground UI is
  visible, eliminating double-firing on navigation events.
- Steam library detection no longer requires `Wow6432Node`-only
  registry roots; both 32- and 64-bit Steam installs resolve.
