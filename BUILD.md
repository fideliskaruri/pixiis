# Building Pixiis (Tauri/Rust port)

These instructions get you from a fresh clone to a clickable
**`Pixiis_0.1.0_x64-setup.exe`** on Windows.

The Tauri port lives on branch `wave1/integration` (the merge of all
nine Wave 1 panes). The legacy Python launcher on `master` still works
and is documented in the top-level `README.md` — this doc is only
for the new Rust app.

## Prerequisites (Windows)

Install once. Most are large (~5 GB total) but only the CMake one is
under 100 MB.

1. **Visual Studio 2026** (or the standalone Build Tools 2026)
   with the workload **"Desktop development with C++"**. This installs
   `cl.exe`, `link.exe`, and the desktop x64 lib + headers that
   Rust + whisper.cpp need.
   - Quick check: open `x64 Native Tools Command Prompt for VS 2026`
     and run `cl`. Should print Microsoft compiler banner. If you
     see *"vcvarsall.bat is not recognised"*, you only have the
     OneCore workload — re-run the VS Installer and tick **"Desktop
     development with C++"**.
2. **Rust stable** via `rustup` — <https://rustup.rs/>.
   ```bat
   rustup default stable
   rustup target add x86_64-pc-windows-msvc
   ```
3. **CMake ≥ 3.20** — `winget install Kitware.CMake`. Required by
   `whisper-rs` (when the voice subsystem lands) but harmless for the
   current build, which doesn't depend on it.
4. **Node.js 20+** — `winget install OpenJS.NodeJS.LTS`.
5. **Tauri CLI** — installed automatically when you `npm install` in
   the frontend (it's a devDependency of `frontend/package.json`).
6. **NSIS** — `winget install NSIS.NSIS`. Tauri shells out to it for
   the installer step.

## Build

From the repo root, on the `wave1/integration` branch, in **Git Bash**
(included with Git for Windows) or WSL:

```bash
./build.sh
```

That's it. The script `npm install`s if needed, then `npm run tauri
build`s, then prints the path to the resulting `.exe`. Two other
modes are available:

```bash
./build.sh dev      # hot-reloading dev shell — no installer
./build.sh clean    # nuke target/ dist/ node_modules/ then rebuild
```

If you're in cmd or PowerShell and don't want to install Git Bash, the
manual equivalent is:

```bat
cd frontend
npm install
npm run tauri build
```

The first invocation pulls ~700 cargo crates and compiles them. Plan
for **8–15 minutes** on a recent laptop. Subsequent builds are
incremental and finish in 30–60 s.

When it completes, the installer is written to:

```
frontend/src-tauri/target/release/bundle/nsis/Pixiis_0.1.0_x64-setup.exe
```

Double-click that file to install Pixiis under
`%LOCALAPPDATA%\Programs\Pixiis\`. Launch from Start menu or the
desktop shortcut.

## What the build contains

| Subsystem | State |
|---|---|
| Tauri 2 window + tray (Open / Scan Library / Quit) | ✅ wired |
| Frontend → backend `invoke()` bridge | ✅ migrated from HTTP |
| **Steam library scanning** (registry → libraryfolders.vdf → .acf) | ✅ ported |
| **Folder scanner** (Program Files + drive-root game dirs) | ✅ ported |
| Controller subsystem (gilrs poller, macro engine) | ✅ Pane 8 |
| External services (RAWG / Twitch / YouTube / OAuth callback) | ✅ Pane 9 (env-var-keyed) |
| Frontend type contracts (`frontend/src/api/types/*.ts`) | ✅ Pane 7 (ts-rs auto-export) |
| Editorial design tokens (Fraunces / Inter / `#C5402F`) | ✅ Pane 6 (tokens.css) |
| Voice transcription (whisper-rs) | ⏳ scaffolded; commands return `Ok(default)` — voice button is wired but no audio pipeline yet |
| Other storefront scanners (Epic, GOG, EA, Xbox, Start Menu) | ⏳ stubs return empty; the `Provider` trait + folder fallback covers most catalogues |

The full whisper / additional-storefront wiring lives in the spike
crates under `spike/whisper-bench/` and `spike/uwp-detect/` — both
are production-grade Phase 0 spikes that just haven't been lifted
into `frontend/src-tauri/` yet. See each spike's `RESULTS.md` for
benchmarks and recommended models.

## Configuration

External services need API keys. Set these env vars before launching
(or `.env` next to the .exe is loaded by the Tauri app once the config
loader lands):

```bat
set PIXIIS_RAWG_API_KEY=...
set PIXIIS_YT_API_KEY=...
set PIXIIS_TWITCH_CLIENT_ID=...
set PIXIIS_TWITCH_CLIENT_SECRET=...
```

Without keys, those services silently return empty — the launcher
itself still works for local + Steam library + controller nav.

## Troubleshooting

- **`error: linker 'link.exe' not found`** — VS Build Tools' C++
  workload isn't on PATH. Open the *x64 Native Tools Command Prompt
  for VS 2026* and re-run from there, or call
  `"C:\Program Files\Microsoft Visual Studio\18\Enterprise\VC\Auxiliary\Build\vcvars64.bat"`
  in your shell first.
- **`LNK1104: cannot open file 'msvcrt.lib'`** — same fix; means the
  desktop x64 workload isn't installed. Run the Visual Studio Installer
  → Modify → tick *"Desktop development with C++"*.
- **`cmake: command not found`** during `cargo build` — `winget
  install Kitware.CMake` then restart the shell.
- **Tauri build hangs at "Compiling tauri v2..."** — that step alone
  is 4-6 min on a cold cache; not a hang. Watch CPU.
- **NSIS error about missing `makensis.exe`** — `winget install
  NSIS.NSIS` then restart the shell.

## Dev mode (no installer)

Faster iteration during development:

```bat
cd frontend
npm run tauri dev
```

This skips the NSIS step and runs the binary directly from
`target/debug/`. The window stays open until you close it; Vite hot
reloads the React side on file change.

## Re-running the type bindings (after editing `types.rs`)

The Pane 7 ts-rs hooks emit `frontend/src/api/types/*.ts` from
`#[derive(TS)]` decorations. Trigger a re-emit with:

```bat
cd frontend\src-tauri
cargo test --bins
```
