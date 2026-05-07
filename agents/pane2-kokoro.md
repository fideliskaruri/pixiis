# Pane 2 — Kokoro ONNX spike

**Branch:** `wave1/kokoro-spike`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/pane2-kokoro/`
**Wave:** 1 (Phase 0 — gate)

> Read `/mnt/d/code/python/pixiis/agents/CONTEXT.md` first.

## Mission

Validate that **Kokoro TTS** (currently used in Python via `kokoro-onnx`) can run in pure Rust via the **`ort` crate** (ONNX Runtime bindings). We need byte-identical or perceptually-equivalent output and acceptable first-sample latency.

## Working directory

Create the spike crate at:
`/mnt/d/code/python/pixiis/.worktrees/pane2-kokoro/spike/kokoro-bench/`

## Reference

Read the existing Python implementation: `/mnt/d/code/python/pixiis/src/pixiis/voice/tts.py`. It uses the `kokoro_onnx.Kokoro` class, the model file `kokoro-v1.0.onnx` (~325 MB), and a voices binary `voices-v1.0.bin`. The default voice is `am_michael` and the prompt template is just plain text.

## Deliverables

1. A Cargo binary crate `spike/kokoro-bench/`:
   - `Cargo.toml`: `ort = "2.0"` (with `cuda` and `cpu` features), `ndarray`, `hound`, `clap`, `anyhow`.
   - `src/main.rs` that:
     - Accepts `--model <path>` (kokoro-v1.0.onnx), `--voices <path>` (voices-v1.0.bin), `--voice <name>` (default `am_michael`), `--text <prompt>`, `--out <wav-path>`.
     - Loads the ONNX model with `ort::Session::builder()`.
     - Reproduces the phoneme tokenization Kokoro expects (look at `kokoro_onnx`'s Python source — likely uses `phonemizer` or a built-in tokenizer; you may need to call out to a phonemizer or pre-tokenize).
     - Runs inference, gets the audio tensor, writes a 24 kHz (or whatever Kokoro outputs) WAV to `--out`.
     - Reports: model load time, time-to-first-sample, total inference time, output WAV duration.
2. A side-by-side comparison: same prompt run through Python `kokoro-onnx` and through this Rust spike. Diff the WAV bytes — log if they're identical, else compute SNR/PSNR.
3. `spike/kokoro-bench/RESULTS.md` documenting findings.

## Acceptance criteria

| Metric | Target |
|---|---|
| Model load | ≤ 3 s |
| First audio sample | ≤ 200 ms after inference start |
| Output equivalence | byte-identical OR manual A/B listening test passes |
| 5 s prompt total inference | ≤ Python × 1.3 |

## Critical risk

Kokoro's tokenization (text → phonemes → tokens) may not be reproducible in Rust without porting the upstream Python `tokenizer.py` or shelling to `espeak-ng`. If the tokenizer can't be matched, output will diverge. **If this happens, document it clearly in `RESULTS.md` and ask the user.** Options would be:
- Ship `espeak-ng` as a bundled binary
- Call Python sidecar just for tokenization (cheap)
- Use the `windows::Media::SpeechSynthesis` SAPI fallback for v1, real Kokoro v1.1

## Dependencies

- Models: download `kokoro-v1.0.onnx` and `voices-v1.0.bin` — typical source is the `kokoro-onnx` GitHub releases page. If Python's user-cache version exists at `~/.cache/kokoro/`, copy from there.
- No dependency on other panes.

## Out of scope

- Don't ship a CLI tool — this is a benchmark.
- Don't integrate with `src-tauri/`.

## Reporting

- Update `agents/STATUS.md` at start, milestones, done.
- Commit to `wave1/kokoro-spike` as you progress.
