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
