//! Voice push-to-talk + TTS commands. STT backed by [`crate::voice::VoiceService`]
//! and TTS by [`crate::voice::TtsEngine`]; both are set up in
//! `lib.rs::run::setup` and stored in app state.
//!
//! `voice_start` opens the mic and emits `voice:state` + streaming
//! `voice:partial` events; `voice_stop` runs the final pass, emits
//! `voice:final`, and returns the transcript. `voice_speak` runs Kokoro
//! synthesis and plays the audio on the default output device.

use std::sync::Arc;

use tauri::State;

use crate::error::{AppError, AppResult};
use crate::types::{TranscriptionEvent, VoiceDevice};
use crate::voice::{audio_capture, text_injection, TtsEngine, VoiceService, DEFAULT_VOICE};

/// `Option<Arc<VoiceService>>` so the command surface degrades gracefully
/// when the whisper model wasn't found at startup — `voice_start` returns
/// `Other("voice unavailable: ...")` and the rest no-op or report `[]`.
pub type VoiceState<'a> = State<'a, Arc<VoiceServiceSlot>>;

/// Wrapper Tauri can `manage()`. Holds either a live service or the reason
/// startup failed (so the UI can surface it).
pub struct VoiceServiceSlot {
    pub service: Option<Arc<VoiceService>>,
    pub init_error: Option<String>,
}

impl VoiceServiceSlot {
    fn get(&self) -> AppResult<Arc<VoiceService>> {
        self.service.clone().ok_or_else(|| {
            AppError::Other(format!(
                "voice unavailable: {}",
                self.init_error
                    .clone()
                    .unwrap_or_else(|| "service not initialised".into())
            ))
        })
    }
}

#[tauri::command]
pub async fn voice_start(state: VoiceState<'_>) -> AppResult<()> {
    let svc = state.get()?;
    svc.start()
}

#[tauri::command]
pub async fn voice_stop(state: VoiceState<'_>) -> AppResult<TranscriptionEvent> {
    let svc = state.get()?;
    // Final pass blocks the calling thread on whisper — push it onto the
    // blocking pool so the async runtime stays responsive.
    tokio::task::spawn_blocking(move || svc.stop())
        .await
        .map_err(|e| AppError::Other(format!("voice_stop join: {e}")))?
}

#[tauri::command]
pub async fn voice_get_devices() -> AppResult<Vec<VoiceDevice>> {
    tokio::task::spawn_blocking(audio_capture::list_devices)
        .await
        .map_err(|e| AppError::Other(format!("voice_get_devices join: {e}")))?
}

#[tauri::command]
pub async fn voice_set_device(state: VoiceState<'_>, device_id: String) -> AppResult<()> {
    let svc = state.get()?;
    svc.set_device(if device_id.is_empty() {
        None
    } else {
        Some(device_id)
    });
    Ok(())
}

#[tauri::command]
pub async fn voice_inject_text(text: String) -> AppResult<()> {
    tokio::task::spawn_blocking(move || text_injection::inject(&text))
        .await
        .map_err(|e| AppError::Other(format!("voice_inject_text join: {e}")))?
}

#[tauri::command]
pub async fn voice_get_transcript_log(
    state: VoiceState<'_>,
    limit: Option<u32>,
) -> AppResult<Vec<TranscriptionEvent>> {
    Ok(state
        .service
        .as_ref()
        .map(|s| s.transcript_log(limit))
        .unwrap_or_default())
}

/// Speak `text` using the bundled Kokoro v1.0 engine.
///
/// Fire-and-forget: returns as soon as the synthesis task is queued. Audio
/// playback continues on the engine's dedicated cpal output thread, so a
/// concurrent `voice_start` (Pane 1's input pipeline) shares neither the
/// stream handle nor any lock with this path — they cannot deadlock.
///
/// Errors that happen *after* the command returns (model load failure,
/// device disconnect, etc.) are logged to stderr; the UI sees only an
/// immediate `Ok(())`. Callers that need synchronous feedback should add a
/// `voice_speak_blocking` companion in a follow-up.
#[tauri::command]
pub async fn voice_speak(
    state: tauri::State<'_, Arc<TtsEngine>>,
    text: String,
    voice: Option<String>,
) -> AppResult<()> {
    let engine = state.inner().clone();
    // ORT inference + cpal enqueue are blocking; offload from the tokio
    // multi-thread runtime so we never starve other commands while a long
    // utterance synthesises (a 5 s prompt is ~3.7 s of CPU per spike).
    tokio::task::spawn_blocking(move || {
        let voice = voice.as_deref().unwrap_or(DEFAULT_VOICE);
        if let Err(e) = engine.speak(&text, voice, 1.0) {
            eprintln!("[voice_speak] {e}");
        }
    });
    Ok(())
}
