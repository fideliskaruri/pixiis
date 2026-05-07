# Wave 2 Pane 1 — Voice integration (whisper-rs + audio + VAD)

**Branch:** `wave2/voice`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/wave2-voice/`

> Read `agents/CONTEXT_WAVE2.md` first.

## Mission

Lift the **whisper-rs spike** (`spike/whisper-bench/`) into the production Tauri crate at `src-tauri/src/voice/` and wire the `voice_*` commands. Voice push-to-talk should work end-to-end: hold the mic button → live partial transcription streams → release → final transcription replaces the partial.

## Reference

- Python original: `src/pixiis/voice/{pipeline,audio_capture,vad,transcriber,text_injection}.py`
- Spike crate: `spike/whisper-bench/` (committed in Wave 1 — passing benchmark, code is clean)
- Spike results: `spike/whisper-bench/RESULTS.md` — read it. Recommends **Q5_0 quantized base.en (~31 MB)** for production. Don't ship the f16 GGUF.
- Types: `src-tauri/src/types.rs::TranscriptionEvent` (already defined)
- Stub commands to replace: `src-tauri/src/commands/voice.rs`

## Deliverables

1. **`src-tauri/src/voice/`** modules:
   - `mod.rs` — re-exports + `VoiceService` orchestrator struct
   - `pipeline.rs` — port `pipeline.py` topology (recording → VAD → live + final transcription threads). Use tokio + crossbeam channels.
   - `audio_capture.rs` — `cpal` input stream, configurable device, 16 kHz mono f32 buffer
   - `vad.rs` — Silero ONNX (via `ort`) primary, energy threshold fallback. Trait + impl per Wave 1 design.
   - `transcriber.rs` — wraps whisper-rs from spike, adapted for streaming chunks. Include the spike's hallucination filter (`is_hallucination`) and energy gate.
   - `text_injection.rs` — Win32 `SendInput` via `windows` crate (port `text_injection.py:40-87`)
2. **`Cargo.toml`** additions:
   - `whisper-rs = "0.13"` (or current latest)
   - `cpal = "0.15"`
   - `ort = "2.0"` (already used by Pane 9 for image? probably already in tree — check)
   - `crossbeam-channel = "0.5"`
3. **`src-tauri/src/commands/voice.rs`** — implement (not stub):
   - `voice_start()` → starts recording, emits `voice:state { listening }`, streams `voice:partial { text }` events as live model produces chunks
   - `voice_stop()` → stops recording, runs final pass, emits `voice:final { text }` and `voice:state { idle }`, returns final text
   - `voice_get_devices()` → `cpal` enumerate devices
   - `voice_set_device(id)` → switches device on next start
   - `voice_get_transcript_log()` → reads accumulated transcript (in-memory for now; persistence is later)
4. **Model bundling decision** in `src-tauri/build.rs` or `src-tauri/resources/`:
   - Bundle `ggml-base.en-q5_0.bin` (~31 MB) into the installer at `resources/models/whisper/`
   - On first run, copy to `%APPDATA%/pixiis/models/whisper/` if not present
   - Larger models download on demand to the same path (Settings page button — Pane 5 will wire it)
5. **Integration with `lib.rs`:** instantiate `VoiceService` in `setup`, store in app state, pass to commands. Spawn the pipeline worker tasks.

## Acceptance criteria

- `cargo check` passes (run on Windows if WSL libs missing; document gap in STATUS otherwise)
- Manual smoke (user attaches and tests): hold the mic button on Home → see "Listening..." → release → see transcribed text in the search bar
- TTFB on partial transcription ≤ 800 ms (per spike results)
- Transcript matches Wave 1 baselines on the test WAV

## Out of scope

- TTS — that's Pane 2
- VAD model bundling beyond the Silero ONNX file (~2 MB, can bundle)
- Voice activation / wake-word — push-to-talk only

## Reporting

Append to `agents/STATUS.md`. Commit to `wave2/voice`. If the Q5_0 GGUF isn't easily downloadable, document and ask the user.
