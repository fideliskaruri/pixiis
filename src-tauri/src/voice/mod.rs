//! Voice subsystem — push-to-talk recording, VAD-gated rolling
//! transcription, final whisper pass, and optional `SendInput` typing.
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
//!   bundled `ggml-base.en-q5_1.bin` to the user's `%APPDATA%`.

pub mod audio_capture;
pub mod model;
pub mod pipeline;
pub mod text_injection;
pub mod transcriber;
pub mod vad;

pub use pipeline::VoiceService;
