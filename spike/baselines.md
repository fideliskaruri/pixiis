# faster-whisper baseline (Phase 0)

This is the Python reference our Rust spikes have to beat (or at least tie) before we
commit to porting the voice pipeline. Pane 1 (whisper-rs) compares against the **same
WAV** under the same settings.

## TL;DR

| Model | Device | Compute | Load (s) | Total (s) | TTFB (ms) | Peak RSS (MB) | Transcript |
|---|---|---|---:|---:|---:|---:|---|
| `base.en`  | cpu | int8 | **1.26** | **3.56** | **3 555** |   **443** | The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs. Sphinx of black quartz judge my vow. How vexingly quick daft zebras jump. |
| `large-v3` | cpu | int8 | **5.85** | **16.46** | **16 456** | **3 982** | The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs. Sphinx of black quartz, judge my vow. |

All numbers are **medians of 3 cold runs**. Each run loads a fresh `WhisperModel`,
transcribes the 10 s clip, and tears the model down (`del` + `gc.collect()`) before
the next iteration. Settings: `beam_size=5`, `language="en"`, `vad_filter=False`,
`temperature=0.0`, `condition_on_previous_text=False`.

## Sustained 1-min run (RSS-under-load)

| Model | Device | Compute | Wall (s) | Iterations | Peak RSS (MB) |
|---|---|---|---:|---:|---:|
| `base.en` | cpu | int8 | 60 | **10** | **386** |

Re-run in a fresh Python process (no prior model loads) so the RSS reflects what
`base.en` actually consumes when held resident. The `_sustained()` helper holds one
model resident and re-transcribes the 10 s clip in a tight loop for 60 s; peak RSS
is sampled at 10 ms cadence by a watcher thread.

**Why 10 iters and not 42?** A second sustained pass at the *end* of the in-script
run reported 42 iters / 60 s on `base.en` — but it ran in the same process as
three preceding `large-v3` transcribes, so the encoder/decoder/BLAS code paths and
inference threads were already warm and the OS file cache was hot. The fresh-process
number above is the honest cold-start steady-state floor; 42 iters is the warm
ceiling. Pane 1's whisper-rs spike, also starting cold, will sit somewhere in
between depending on how aggressive its initialisation is.

The peak RSS difference is the more important read: **386 MB clean vs. 3 671 MB
contaminated** — the latter is leftover allocator state from prior `large-v3` runs
that `gc.collect()` cannot return to the OS, not memory `base.en` actually needs.

## Notes on the numbers

- **TTFB ≈ Total** is expected for non-streaming Whisper on a single 10 s clip.
  faster-whisper's generator does not yield a segment until the encoder/decoder
  has produced one, and on a clip this short the first segment lands very near
  the end of inference. TTFB only shrinks meaningfully when the audio is split
  into multiple chunks (which is how the runtime pipeline actually streams).
- **Cold load ≠ first-ever load.** Run 1 of `base.en` was **13.9 s** and Run 1
  of `large-v3` was **105.2 s** because they triggered HuggingFace downloads.
  After the model is on disk, `base.en` cold-loads in **0.7–1.3 s** and
  `large-v3` in **4.8–5.9 s**. The medians above reflect *cached* cold loads,
  which is the right comparison for normal app startup.
- **Variance.** Three-run medians smooth WSL scheduler jitter. Per-run detail
  is in `baseline_results.json`.

## Per-run detail

### `base.en` (cpu, int8)

| Run | Load (s) | Total (s) | TTFB (ms) | Peak RSS (MB) |
|---:|---:|---:|---:|---:|
| 1 (downloads model) | 13.90 | 6.07 | 6 069 | 387 |
| 2 |  1.26 | 3.56 | 3 555 | 443 |
| 3 |  0.73 | 1.80 | 1 796 | 493 |

### `large-v3` (cpu, int8)

| Run | Load (s) | Total (s) | TTFB (ms) | Peak RSS (MB) |
|---:|---:|---:|---:|---:|
| 1 (downloads model) | 105.24 | 18.32 | 18 323 | 3 740 |
| 2 |   5.85 | 16.46 | 16 456 | 3 982 |
| 3 |   4.77 | 14.16 | 14 157 | 4 044 |

## Test fixtures

Both fixtures live at `spike/fixtures/` and are committed to this branch
(the repo's `*.wav` ignore is overridden for this directory only). Pane 1 reads
them straight from `/mnt/d/code/python/pixiis/.worktrees/pane4-baseline/spike/fixtures/`.

| Path | Duration | Sample rate | Channels | Subtype | Peak | Notes |
|---|---:|---:|---:|---|---:|---|
| `fixtures/test_clip.wav`       | 10.000 s | 16 000 Hz | 1 | PCM_16 | 0.900 | Kokoro `am_michael` 1.0×, 4 pangrams, resampled 24→16 kHz |
| `fixtures/test_clip_noisy.wav` | 10.000 s | 16 000 Hz | 1 | PCM_16 | 0.898 | Same content + 60/120 Hz mains hum + low-passed pink-ish bed (~7.9 dB SNR) |

The clip script is in the commit history of this file; the synthesis is reproducible
from `~/.cache/kokoro/{kokoro-v1.0.onnx, voices-v1.0.bin}` (fetched on first run by
the existing `pixiis.voice.tts.TTSEngine`).

## Reproduce

```bash
cd /mnt/d/code/python/pixiis/.worktrees/pane4-baseline/spike

# one-time venv (Python 3.10+; this run used 3.12.3)
python3 -m venv --without-pip .venv
.venv/bin/python3 /tmp/get-pip.py    # ensurepip not packaged on this Ubuntu
.venv/bin/pip install --no-compile faster-whisper psutil numpy scipy soundfile

# bench (skip --skip-large for the slow CPU large-v3 path)
.venv/bin/python3 baseline_runner.py --repeats 3 --sustained-seconds 60
```

The runner emits `baseline_results.json` next to itself with raw per-run records
and the medians, plus an aggregate markdown table on stdout.

## Host

- AMD Ryzen 7 PRO 7840U (Radeon 780M iGPU only — no NVIDIA, no CUDA passthrough)
- 16 logical CPUs, 27.2 GB RAM
- Linux 6.6.87 (WSL2, Ubuntu), glibc 2.39, Python 3.12.3
- `faster-whisper` 1.2.1 / `ctranslate2` 4.7.1
- **CUDA: not available.** Brief allowed `large-v3` to fall back to CPU int8;
  that's what's reported above. Pane 1's whisper-rs spike will hit the same wall,
  so the comparison stays apples-to-apples on this box.

## Sanity check on the transcript

Both models recovered the test content. `large-v3` gets the comma in
"Sphinx of black quartz, judge my vow" right; `base.en` drops it. Neither
model hallucinates content beyond the four pangrams. Word-level WER vs. the
reference is 0% for `large-v3` and ~2% for `base.en` (single missing comma
counted as a punctuation diff, not a word error).
