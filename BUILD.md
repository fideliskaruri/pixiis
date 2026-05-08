# Building Pixiis

End-to-end: from a clean Windows machine to a clickable
**`Pixiis_0.2.0_x64-setup.exe`**.

## Prereqs

Install once. Total ~5 GB.

1. **Visual Studio 2026** (or standalone Build Tools 2026) with the
   workload **"Desktop development with C++"**. This is what gives
   you `cl.exe`, `link.exe`, and the desktop x64 runtime libs that
   Rust links against.
   - Sanity check: open the *x64 Native Tools Command Prompt for
     VS 2026* and run `cl`. Should print the Microsoft compiler
     banner. If you see *"vcvarsall.bat is not recognised"*, you
     only have the OneCore workload — re-run the VS Installer and
     tick *"Desktop development with C++"*.
2. **Rust stable** — <https://rustup.rs/>
   ```
   rustup default stable
   ```
3. **Node 20+** — `winget install OpenJS.NodeJS.LTS`
4. **CMake** — `winget install Kitware.CMake`
5. **NSIS** — `winget install NSIS.NSIS` (Tauri shells out to it for
   the installer step)
6. **LLVM / libclang** — `winget install LLVM.LLVM`. `whisper-rs-sys`'s
   `bindgen` step needs `libclang.dll`. After install, restart the
   shell *and* set the env var explicitly because bindgen sometimes
   misses it even when it's on PATH:
   ```powershell
   [System.Environment]::SetEnvironmentVariable(
     "LIBCLANG_PATH", "C:\Program Files\LLVM\bin", "User")
   ```
   If you already have VS 2026's *C++ Clang tools* component, point
   `LIBCLANG_PATH` at
   `C:\Program Files\Microsoft Visual Studio\2026\<Edition>\VC\Tools\Llvm\x64\bin`
   instead.

## Model files

| Model              | Bundled?                | Size   | Notes                                                                 |
|--------------------|-------------------------|--------|-----------------------------------------------------------------------|
| Whisper STT        | **Yes** (since v0.2.1)  | ~57 MB | `resources/models/whisper/ggml-base.en-q5_1.bin` is committed to git. |
| Kokoro TTS         | No                      | —      | TTS removed from the build.                                           |
| Silero VAD         | No                      | ~2 MB  | Feature-gated (`silero-vad`); not enabled by default.                 |

The Whisper model ships with the installer, so voice search works on
first launch with no manual download step. On first run the runtime
copies it from `<install>\resources\models\whisper\` into
`%APPDATA%\pixiis\models\whisper\` so subsequent launches load from a
writable location.

If the file ever goes missing or you want to replace it (e.g. with a
larger checkpoint), drop a fresh copy at the same path and rebuild:

```powershell
curl.exe -L -o "resources\models\whisper\ggml-base.en-q5_1.bin" `
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_1.bin
```

### Optional: Silero VAD

Only relevant when building with `--features silero-vad` (off by
default). Drop the ONNX file into `resources/models/silero/` and add a
glob to `tauri.conf.json::bundle.resources`:

```powershell
curl.exe -L -o "resources\models\silero\silero_vad.onnx" `
  https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx
```

```jsonc
"resources": [
  "../resources/default_config.toml",
  "../resources/models/whisper/*.bin",
  "../resources/models/silero/*.onnx"
]
```

(The energy-RMS fallback (`EnergyVad`) is always available and is the
default when this feature is off, so most builds don't need this.)

## Build

From the repo root, in **Git Bash** or WSL:

```bash
./build.sh
```

That's it. The script `npm install`s if needed, runs `npm run tauri
build`, and prints where the installer landed. Two other modes:

```bash
./build.sh dev      # hot-reloading dev shell, no installer
./build.sh clean    # nuke target/, dist/, node_modules/ then rebuild
```

If you'd rather not use Git Bash:

```bat
npm install
npm run tauri build
```

The first invocation pulls ~700 cargo crates and compiles them — plan
for **8–15 minutes** on a recent laptop. Subsequent builds are
incremental and finish in 30–60 s.

The installer ends up at:

```
src-tauri/target/release/bundle/nsis/Pixiis_0.2.0_x64-setup.exe
```

Double-click to install. Pixiis lands in
`%LOCALAPPDATA%\Programs\Pixiis\` with a Start Menu shortcut.

## Cargo features

Optional features defined in `src-tauri/Cargo.toml`:

- `silero-vad` (off by default) — enables the ONNX Silero VAD path
  in `voice/vad.rs`. Pulls in `ort` + `ndarray` as build-time deps,
  requires `onnxruntime.dll` to be resolvable at runtime, and needs
  the `silero_vad.onnx` file to be present. The energy-RMS fallback
  (`EnergyVad`) is always available and is the default when this
  feature is off.
- `custom-protocol` — set automatically by the Tauri CLI for
  production builds. Do not toggle by hand.

To build with VAD on:

```bash
cd src-tauri && cargo tauri build --features silero-vad
```

## Troubleshooting

- **`error: linker 'link.exe' not found`** — the C++ workload isn't on
  PATH. Open the *x64 Native Tools Command Prompt for VS 2026* and
  re-run from there.
- **`LNK1104: cannot open file 'msvcrt.lib'`** — same fix; the
  desktop x64 workload isn't installed. VS Installer → Modify → tick
  *Desktop development with C++*.
- **`cmake: command not found`** — `winget install Kitware.CMake`,
  then restart the shell so PATH picks it up.
- **`makensis.exe` not found** — `winget install NSIS.NSIS`, then
  restart the shell.
- **The build looks like it's hanging at "Compiling tauri v2..."** —
  not a hang. That step alone takes 4–6 minutes on a cold cache.
- **Type bindings out of sync** after editing `src-tauri/src/types.rs` —
  re-emit them with `cd src-tauri && cargo test --bins`.
- **`Unable to find libclang`** — install LLVM (`winget install
  LLVM.LLVM`), restart the shell, and ensure `LIBCLANG_PATH` is set
  to the directory containing `libclang.dll` (typically
  `C:\Program Files\LLVM\bin`). See prereq #6.
- **`glob pattern ../resources/models/.../* path not found`** — Tauri
  errors when a `bundle.resources` glob matches nothing. Either drop
  model files into the matching `resources/models/<kind>/` directory
  or remove the glob from `tauri.conf.json::bundle.resources`.

## Code signing (release builds)

`bundle.windows.signCommand` is `null` in `src-tauri/tauri.conf.json`,
which is the right setting for dev and CI smoke builds — Tauri skips
signtool entirely and the resulting `.exe` is unsigned. Windows
SmartScreen will warn the first time a downloaded copy launches; that
is expected and only goes away once we ship a signed build.

For release, hook one of two flows.

### Option A — Authenticode certificate on the build host

The simplest path. Set the env vars below before `npm run tauri build`,
then point `signCommand` at `signtool.exe` (it lives in the Windows SDK
under `C:\Program Files (x86)\Windows Kits\10\bin\<sdk>\x64\`):

```bash
export TAURI_SIGNING_PRIVATE_KEY=path/to/cert.pfx
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD='cert-password'
```

In `tauri.conf.json`:

```jsonc
"windows": {
  "signCommand": "signtool sign /fd sha256 /td sha256 /tr http://timestamp.digicert.com /f $env:TAURI_SIGNING_PRIVATE_KEY /p $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD %1",
  "nsis": { ... }
}
```

The `%1` placeholder is mandatory — Tauri substitutes the binary path
into it before invoking the command, once for each PE file in the
bundle (the main exe + the NSIS installer).

### Option B — Cross-platform via osslsigncode

If the build host isn't Windows (e.g. a Linux release pipeline cross-
compiling with `cargo-xwin`), use `osslsigncode` instead:

```jsonc
"signCommand": "osslsigncode sign -pkcs12 $TAURI_SIGNING_PRIVATE_KEY -pass $TAURI_SIGNING_PRIVATE_KEY_PASSWORD -t http://timestamp.digicert.com -in %1 -out %1.signed && mv %1.signed %1"
```

### CI checklist

1. Inject the `.pfx` from a secret store at job start; never commit it.
2. Keep `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` in encrypted env, not in
   the repo or build logs.
3. After `tauri build`, run `signtool verify /pa
   target/release/bundle/nsis/Pixiis_*_x64-setup.exe` to confirm the
   Authenticode chain validates.
4. Update the version in `src-tauri/tauri.conf.json` and
   `src-tauri/Cargo.toml` together — the NSIS installer name embeds
   the former, and the latter shows up in the file properties dialog.
