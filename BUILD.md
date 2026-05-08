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

Voice STT, TTS, and (optionally) Silero VAD need model weights that
are **not bundled with the installer** and **not committed to git**.
They're not listed in `tauri.conf.json::bundle.resources` because (a)
they'd add 350+ MB to the installer and (b) Tauri's bundler errors
on globs that match nothing, which would break the build for anyone
who hadn't staged weights.

The build succeeds without any model files. Voice / TTS commands
return a clean `NotFound` error at runtime until the user drops the
weights in. The runtime looks at `%APPDATA%\pixiis\models\<kind>\`
first, so this is where users put downloaded models.

```powershell
# Whisper STT (~31 MB, required for voice search)
curl.exe -L -o "$env:APPDATA\pixiis\models\whisper\ggml-base.en-q5_0.bin" `
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_0.bin

# Kokoro TTS (~325 MB + ~26 MB, required for voice_speak)
curl.exe -L -o "$env:APPDATA\pixiis\models\kokoro\kokoro-v1.0.onnx" `
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl.exe -L -o "$env:APPDATA\pixiis\models\kokoro\voices-v1.0.bin" `
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

# Silero VAD (~2 MB, only needed when the silero-vad feature is on)
curl.exe -L -o "$env:APPDATA\pixiis\models\silero\silero_vad.onnx" `
  https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx
```

(Create the `kokoro\`, `whisper\`, `silero\` subdirectories first if
PowerShell complains.)

To **bundle** the models into a release installer, drop them into the
matching `resources/models/<kind>/` directory in the repo before
building, then add globs back to `tauri.conf.json::bundle.resources`:

```jsonc
"resources": [
  "../resources/default_config.toml",
  "../resources/models/whisper/*.bin",
  "../resources/models/kokoro/*.onnx",
  "../resources/models/kokoro/*.bin",
  "../resources/models/silero/*.onnx"
]
```

On first launch the runtime copies bundled models into
`%APPDATA%\pixiis\models\` so the installer files become read-only.

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
  in `voice/vad.rs`. Requires `onnxruntime.dll` to be resolvable at
  runtime and the `silero_vad.onnx` file to be present. The
  energy-RMS fallback (`EnergyVad`) is always available and is the
  default when this feature is off.
- `custom-protocol` — set automatically by the Tauri CLI for
  production builds. Do not toggle by hand.

To build with VAD on:

```bash
cd src-tauri && cargo tauri build --features silero-vad
```

`ort` (the ONNX runtime crate Kokoro TTS uses) is **not** behind a
feature flag — it's a hard dep, dlopened at runtime via
`load-dynamic`, so `onnxruntime.dll` must be on the search path of any
machine running `voice_speak`.

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
