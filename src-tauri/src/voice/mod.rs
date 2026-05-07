//! Voice subsystem.
//!
//! Wave 2 split: Pane 1 owns STT (`pipeline`, `audio_capture`, `vad`,
//! `transcriber`, `text_injection`); Pane 2 owns TTS (`tts`). Both panes
//! touch this file at integration time — extend the `pub mod` list and
//! merge the re-exports.

pub mod tts;

pub use tts::{ensure_model_files, TtsConfig, TtsEngine, DEFAULT_VOICE};
