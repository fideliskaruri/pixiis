use std::sync::Arc;

use crate::error::AppResult;
use crate::types::{TranscriptionEvent, VoiceDevice};
use crate::voice::{TtsEngine, DEFAULT_VOICE};

#[tauri::command]
pub async fn voice_start() -> AppResult<()> {
    Ok(())
}

#[tauri::command]
pub async fn voice_stop() -> AppResult<TranscriptionEvent> {
    Ok(TranscriptionEvent {
        text: String::new(),
        is_final: true,
        timestamp: 0.0,
    })
}

#[tauri::command]
pub async fn voice_get_devices() -> AppResult<Vec<VoiceDevice>> {
    Ok(Vec::new())
}

#[tauri::command]
pub async fn voice_set_device(_device_id: String) -> AppResult<()> {
    Ok(())
}

#[tauri::command]
pub async fn voice_inject_text(_text: String) -> AppResult<()> {
    Ok(())
}

#[tauri::command]
pub async fn voice_get_transcript_log(_limit: Option<u32>) -> AppResult<Vec<TranscriptionEvent>> {
    Ok(Vec::new())
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
