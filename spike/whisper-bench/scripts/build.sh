#!/usr/bin/env bash
# Build whisper-bench in release mode on Linux (used by the Phase 0 spike).
# Requires: rustup-managed cargo + a working C toolchain (cc/cmake on PATH).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
cargo build --release "$@"
