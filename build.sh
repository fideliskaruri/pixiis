#!/usr/bin/env bash
# Build the Pixiis Tauri app.
#
# Defaults to a release build (NSIS installer at
# `frontend/src-tauri/target/release/bundle/nsis/Pixiis_*-setup.exe`).
# Pass `dev` to run `npm run tauri dev` instead, or `clean` to scrub
# build artifacts before rebuilding.
#
# Skips `npm install` when `node_modules` is already up-to-date with
# `package-lock.json`, so re-runs are cheap.
#
# Works from anywhere — the script cd's to its own parent before doing
# anything. Run on Windows under Git Bash, on Linux/WSL, or on macOS.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$REPO_ROOT/frontend"

mode="release"
case "${1:-}" in
  ""|build|release) mode="release" ;;
  dev)              mode="dev" ;;
  clean)            mode="clean" ;;
  -h|--help)
    cat <<EOF
usage: build.sh [release|dev|clean]
  release   (default) Full release build → NSIS installer .exe
  dev       Run \`npm run tauri dev\` (hot-reloading dev shell)
  clean     Remove target/, dist/, node_modules/ then build release
EOF
    exit 0
    ;;
  *)
    echo "build.sh: unknown mode '$1' (try --help)" >&2
    exit 2
    ;;
esac

cd "$FRONTEND"

if [[ "$mode" == "clean" ]]; then
  echo "==> clean: removing target/, dist/, node_modules/"
  rm -rf src-tauri/target dist node_modules
  mode="release"
fi

# Skip `npm install` when node_modules is newer than package-lock.json
# (cheap re-runs). Force on missing node_modules or first run.
need_install=0
if [[ ! -d node_modules ]]; then
  need_install=1
elif [[ -f package-lock.json && package-lock.json -nt node_modules/.package-lock.json ]]; then
  need_install=1
fi

if [[ "$need_install" == "1" ]]; then
  echo "==> npm install"
  npm install
else
  echo "==> npm install: up-to-date, skipping"
fi

if [[ "$mode" == "dev" ]]; then
  echo "==> npm run tauri dev"
  exec npm run tauri dev
fi

echo "==> npm run tauri build"
npm run tauri build

# Surface where the installer landed (only the Windows NSIS path is
# enabled in tauri.conf.json; the others fall through silently).
INSTALLER_DIR="$FRONTEND/src-tauri/target/release/bundle/nsis"
if [[ -d "$INSTALLER_DIR" ]]; then
  echo
  echo "==> Installers:"
  ls -lh "$INSTALLER_DIR"/*.exe 2>/dev/null | awk '{print "    " $NF " (" $5 ")"}' || true
else
  echo
  echo "==> NSIS bundle dir not found ($INSTALLER_DIR) — check tauri build output above"
fi
