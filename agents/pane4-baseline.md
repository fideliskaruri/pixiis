# Pane 4 — faster-whisper Python baseline

**Branch:** `wave1/baseline`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/pane4-baseline/`
**Wave:** 1 (Phase 0 prep — unblocks Panes 1 & 2)

> Read `/mnt/d/code/python/pixiis/agents/CONTEXT.md` first.

## Mission

Establish a **faster-whisper baseline** on the user's machine. Without this number, Panes 1 (whisper-rs) and 2 (Kokoro) have nothing to compare against, and the Phase 0 gate decision becomes guesswork.

You also produce the **shared test fixture** (`spike/fixtures/test_clip.wav`) that the spikes use.

## Working directory

`/mnt/d/code/python/pixiis/.worktrees/pane4-baseline/spike/`

Create files at `spike/baselines.md` and `spike/fixtures/`.

## Reference

`src/pixiis/voice/transcriber.py` and `src/pixiis/voice/pipeline.py` show how faster-whisper is configured:
- `compute_type="int8"` for CPU
- `compute_type="float16"` for CUDA
- `beam_size=5` (default), `beam_size=3` ("fast" mode)
- Models: `tiny`, `base`, `small`, `medium`, `large-v3`

## Deliverables

1. **`spike/fixtures/test_clip.wav`** — a 10-second 16 kHz mono WAV of clean speech. Either:
   - Find an existing one in `examples/` or `inbox/` (check first)
   - Record one with sounddevice
   - Synthesize one with the existing TTS (`from pixiis.voice.tts import TTSEngine; TTSEngine().speak("...")` then capture the output)
   - Pull a Mozilla Common Voice clip if downloadable
2. **`spike/fixtures/test_clip_noisy.wav`** — same content with added background hum/noise (use scipy or sox).
3. **`spike/baseline_runner.py`** — a script that:
   - Sets up a venv with `faster-whisper` and `psutil`
   - Loads `base.en` (CPU int8) and `large-v3` (CUDA fp16 if available, else CPU int8 — mark which)
   - Runs the WAV through each model
   - Captures: model load time, full transcription wall time, time-to-first-segment (use the streaming generator), peak RSS via psutil
   - Repeats 3× per model and reports median
4. **`spike/baselines.md`** — markdown table:
   ```
   | Model | Device | Compute | Load (s) | Total (s) | TTFB (ms) | Peak RSS (MB) | Transcript |
   ```
   Plus a sustained 1-min run for RSS-under-load.

## Acceptance criteria

- Numbers exist for all 6 cells (2 models × 3 metrics × medians).
- Test WAV is 10 s ± 100 ms, mono, 16 kHz, no clipping.
- `baselines.md` is committed.
- File `spike/baselines.md` exists at known path so Panes 1 and 2 can read it.

## Dependencies

- None — you're the first one. Run before the spikes need numbers.
- Python 3.10+ available (the user has it — current project's Python).
- CUDA optional. If unavailable, mark the large-v3 row "CPU int8" instead.

## Out of scope

- Don't write Rust here.
- Don't replace faster-whisper — just baseline.

## Reporting

- Update `agents/STATUS.md` when the WAV is ready (Panes 1 & 2 unblock then).
- Update again when `baselines.md` is final.
- Commit to `wave1/baseline` as you go.
