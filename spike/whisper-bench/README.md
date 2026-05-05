# whisper-bench

Phase 0 spike for the Pixiis Tauri/Rust port. Validates that
[`whisper-rs`](https://crates.io/crates/whisper-rs) (Rust bindings to
`whisper.cpp`) can replace the current Python `faster-whisper` pipeline
without regressing user-facing voice latency or accuracy.

CLI tool only — no integration with the main app crate.

## Build

```bash
# Linux / WSL
cd spike/whisper-bench
./scripts/build.sh
```

```bat
:: Windows
cd spike\whisper-bench
scripts\build.bat
```

`whisper-rs` invokes CMake at build time to compile bundled `whisper.cpp`.
Toolchain prerequisites:

- Rust stable (`rustup install stable`)
- CMake ≥ 3.20 on `PATH`
- A C/C++ compiler:
  - Linux: `gcc` / `g++` or `clang` (zig's bundled clang via a `cc` wrapper works)
  - Windows: MSVC build tools with the "Desktop development with C++"
    workload (the `vcvars64.bat` env-setup is invoked by `scripts\build.bat`)

GPU is **not** enabled in this build. CUDA / Vulkan / Metal would require
extra cargo features on `whisper-rs` (e.g. `cuda`, `vulkan`) and the
matching SDKs. The host this spike runs on has no NVIDIA hardware, so
the `--gpu` flag is wired through but inert.

## Models

Download GGUF weights from
<https://huggingface.co/ggerganov/whisper.cpp> into `models/`:

| File | Size | Use |
|---|---|---|
| `ggml-base.en.bin` | ~150 MB | Default — fast CPU live mode (English only) |
| `ggml-large-v3.bin` | ~3 GB | Highest accuracy — needs CUDA in practice |

Quick fetch (PowerShell):

```powershell
mkdir models -Force
curl.exe -L -o models\ggml-base.en.bin `
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
```

## Run

```bash
# Linux / WSL
./target/release/whisper-bench \
  --model models/ggml-base.en.bin \
  --wav   ../../.worktrees/pane4-baseline/spike/fixtures/test_clip.wav \
  --label base.en-cpu
```

```bat
:: Windows
target\release\whisper-bench.exe ^
  --model models\ggml-base.en.bin ^
  --wav   ..\fixtures\test_clip.wav ^
  --label base.en-cpu
```

Flags:

| Flag | Default | What |
|---|---|---|
| `--model PATH` | required | GGUF/ggml weights |
| `--wav PATH` | required | Any-rate, any-channel WAV (auto down-mixed + resampled to 16 kHz mono) |
| `--threads N` | physical core count | CPU thread count |
| `--gpu` | false | Pass-through to `whisper-rs` GPU flag (no-op without GPU features) |
| `--language` | `en` | Whisper language hint |
| `--beam` | `1` | Greedy beam (kept low to mirror live mode) |
| `--label TAG` | `run` | Tag echoed in the JSON for cross-run diffing |

## Output

JSON on stdout — one object per run. Fields:

```jsonc
{
  "label": "base.en-cpu",
  "model": "models/ggml-base.en.bin",
  "wav": "../fixtures/test_clip.wav",
  "audio_seconds": 10.0,        // duration of decoded clip
  "threads": 8,
  "gpu_requested": false,
  "model_load_ms": 0.0,         // WhisperContext::new wall time
  "transcribe_ms": 0.0,         // state.full() wall time
  "ttfb_ms": 0.0,               // first new-segment callback wall time
  "rss_baseline_mb": 0.0,
  "rss_after_load_mb": 0.0,
  "rss_peak_mb": 0.0,           // captured right after full() returns
  "rss_delta_mb": 0.0,
  "realtime_factor": 0.0,       // transcribe_ms / 1000 / audio_seconds
  "transcript": "..."
}
```

For the live-mode TTFB target (≤ 400 ms on a ~750 ms chunk), pass a
short clip via `--wav` and read the `ttfb_ms` field.

Cold-load comparison against Python `faster-whisper` (Pane 4) lives in
`RESULTS.md`.
