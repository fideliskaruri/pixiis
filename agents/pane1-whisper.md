# Pane 1 — whisper-rs spike

**Branch:** `wave1/whisper-spike`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/pane1-whisper/`
**Wave:** 1 (Phase 0 — gate)

> Read `/mnt/d/code/python/pixiis/agents/CONTEXT.md` first.

## Mission

Validate that **whisper-rs** (Rust bindings to whisper.cpp) can replace **faster-whisper** (CTranslate2-based, current Python) without regressing user-facing voice latency or accuracy. This is one of three Phase 0 gates — if you fail, the whole "full Rust port" plan reroutes to a Python sidecar fallback.

## Working directory

Create the spike crate at:
`/mnt/d/code/python/pixiis/.worktrees/pane1-whisper/spike/whisper-bench/`

You're operating inside the worktree, so when you `cd` into your worktree root and create files there, you're isolated from the other panes.

## Deliverables

1. A standalone Cargo binary crate `spike/whisper-bench/` with:
   - `Cargo.toml` depending on `whisper-rs = "0.13"` (or current latest), `hound` for WAV I/O, `clap` for CLI flags, `anyhow` for errors.
   - `src/main.rs` that:
     - Accepts `--model <path>` (path to GGUF model file) and `--wav <path>` (path to test WAV)
     - Loads the model with `WhisperContext::new`, times it
     - Reads the WAV, resamples to 16 kHz mono f32 if needed
     - Runs `state.full(...)` with timing
     - Streams partial tokens via `set_progress_callback` or `set_segment_callback` and times time-to-first-token (TTFB)
     - Reports: model load time, full transcription time, TTFB, peak RSS (use `peak_alloc` or read `/proc/self/status`)
     - Prints results as JSON
2. A `spike/whisper-bench/README.md` documenting how to run, where to get models (`https://huggingface.co/ggerganov/whisper.cpp`), and the expected outputs.
3. A `spike/whisper-bench/RESULTS.md` with the actual numbers from your runs on the user's machine, compared against the baseline from Pane 4.

## Acceptance criteria

| Metric | Target | Source of comparison |
|---|---|---|
| `base.en` cold load (CPU, int8) | ≤ 2 s | absolute |
| `large-v3` cold load (CUDA fp16) | ≤ 5 s | absolute |
| `base.en` 10 s clip transcription (CPU) | ≤ 1.5× faster-whisper | `spike/baselines.md` (Pane 4) |
| `large-v3` 10 s clip (CUDA) | ≤ 1.2× faster-whisper | `spike/baselines.md` (Pane 4) |
| TTFB on ~750 ms chunk (live mode) | ≤ 400 ms | absolute |
| Peak RSS, 1 min sustained | ≤ 1.2× Python | `spike/baselines.md` (Pane 4) |

If any metric misses by **>2×**, write a clear note in `RESULTS.md` and mark the spike `FAILED` in `STATUS.md` so the user can decide on Plan B.

## Dependencies

- **Pane 4** produces `spike/baselines.md` and `spike/fixtures/test_clip.wav`. If they're missing when you start, poll every 30 s. While waiting, scaffold the crate and write the code — you don't need the WAV until you actually run the benchmark.
- Models: download manually from HuggingFace (`ggml-base.en.bin`, `ggml-large-v3.bin`) into `spike/models/`. They're large (150 MB / 3 GB) — ask the user via chat which to test if disk is a concern.

## Out of scope

- Don't integrate with `frontend/src-tauri/` — this is a sandbox.
- Don't optimize beyond what's needed to measure honestly.
- Don't ship a UI. CLI only.

## Reporting

- Append to `/mnt/d/code/python/pixiis/agents/STATUS.md` at start, on each result, and on done.
- Commit to `wave1/whisper-spike` as you go. Suggested commits: scaffold → first run → final results.
- If whisper-rs has a critical limitation (no streaming callback, CUDA build failure, etc.), document it and ask the user before deciding on a fallback.
