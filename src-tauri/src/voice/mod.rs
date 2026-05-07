//! Voice subsystem — push-to-talk recording, VAD-gated rolling
//! transcription, final whisper pass, optional `SendInput` typing, and
//! Kokoro TTS.
//!
//! Wave 2 split: Pane 1 owns STT (`pipeline`, `audio_capture`, `vad`,
//! `transcriber`, `text_injection`); Pane 2 owns TTS (`tts`). Both panes
//! touch this file at integration time — extend the `pub mod` list and
//! merge the re-exports.
//!
//! Lifted from `spike/whisper-bench/` and the Python original at
//! `src/pixiis/voice/`. Public surface:
//!
//! - [`VoiceService`] — owned by Tauri state, instantiated once in
//!   `lib.rs::run::setup`. Coordinates `voice_start` / `voice_stop`.
//! - [`audio_capture::list_devices`] — for the `voice_get_devices`
//!   command.
//! - [`text_injection::inject`] — for the `voice_inject_text` command.
//! - [`model::ensure_default_whisper_model`] — first-run copy of the
//!   bundled `ggml-base.en-q5_0.bin` to the user's `%APPDATA%`.
//! - [`TtsEngine`] — Kokoro v1.0 ONNX engine for `voice_speak`.

pub mod audio_capture;
pub mod model;
pub mod pipeline;
pub mod text_injection;
pub mod transcriber;
pub mod tts;
pub mod vad;

pub use pipeline::VoiceService;
pub use tts::{ensure_model_files, TtsConfig, TtsEngine, DEFAULT_VOICE};
