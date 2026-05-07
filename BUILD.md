# Building Pixiis

End-to-end: from a clean Windows machine to a clickable
**`Pixiis_0.1.0_x64-setup.exe`**.

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
src-tauri/target/release/bundle/nsis/Pixiis_0.1.0_x64-setup.exe
```

Double-click to install. Pixiis lands in
`%LOCALAPPDATA%\Programs\Pixiis\` with a Start Menu shortcut.

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
