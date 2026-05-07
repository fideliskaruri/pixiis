# Wave 2 Pane 2 — TTS integration (Kokoro)

**Branch:** `wave2/tts`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/wave2-tts/`

> Read `agents/CONTEXT_WAVE2.md` first.

## Mission

Lift the **Kokoro spike** (`spike/kokoro-bench/`) into `src-tauri/src/voice/tts.rs` and wire the `voice_speak` command.

## Reference

- Python original: `src/pixiis/voice/tts.py`
- Spike crate: `spike/kokoro-bench/` (Wave 1, passed perceptual equivalence — cosine 0.9991)
- Spike results: `spike/kokoro-bench/RESULTS.md` — note the **phonemizer punctuation divergence**. Three options listed; choose **option B** (port phonemizer-fork's punctuation logic to Rust) unless the user disagrees.

## Deliverables

1. **`src-tauri/src/voice/tts.rs`** — port the spike's Kokoro engine:
   - Load `kokoro-v1.0.onnx` via `ort`
   - Load `voices-v1.0.bin`
   - Phoneme tokenization (espeak-ng FFI, same as spike — works)
   - Inference → 24 kHz audio tensor
   - Resample to 48 kHz if needed for cpal
   - Output via `cpal` (reuse Pane 1's output device handling if possible — coordinate via `VoiceService` shared state)
2. **`src-tauri/src/commands/voice.rs::voice_speak`** — implement (replace stub):
   - `voice_speak(text: String, voice: Option<String>) -> Result<()>`
   - Default voice: `am_michael`
   - Fire-and-forget: returns immediately, audio plays async
3. **Model bundling:** same pattern as Pane 1 — bundle `kokoro-v1.0.onnx` (~325 MB) and `voices-v1.0.bin` in the installer's `resources/models/kokoro/`, copy to `%APPDATA%/pixiis/models/kokoro/` on first run.
4. **Coexistence with Pane 1:** Pane 1 is also writing to `src-tauri/src/voice/`. Coordinate by:
   - Pane 1 owns: `mod.rs`, `pipeline.rs`, `audio_capture.rs`, `vad.rs`, `transcriber.rs`, `text_injection.rs`
   - You own: `tts.rs`
   - Both add to `Cargo.toml` — merge cleanly (alphabetize deps)
   - The shared cpal output device probably wants a `VoiceService::play_pcm(samples)` helper Pane 1 exposes

## Acceptance criteria

- Manual smoke: from Settings page (eventually), "Test voice" button speaks a sample sentence
- Output is perceptually equivalent to Python (per spike's metric)
- First-sample latency ≤ 200 ms after `voice_speak` invoked
- No deadlocks if `voice_speak` and `voice_start` happen concurrently (the user might trigger TTS while listening)

## Out of scope

- STT — Pane 1
- Voice cloning, custom voices beyond the bundled set
- Streaming TTS (full sentence at a time is fine)

## Reporting

Append to `agents/STATUS.md`. Commit to `wave2/tts`. Coordinate with Pane 1's branch on merge.
