//! Voice push-to-talk commands. Backed by [`crate::voice::VoiceService`],
//! set up in `lib.rs::run::setup` and stored in app state.
//!
//! `voice_start` opens the mic and emits `voice:state` + streaming
//! `voice:partial` events; `voice_stop` runs the final pass, emits
//! `voice:final`, and returns the transcript.

use std::sync::Arc;

use tauri::State;

use crate::error::{AppError, AppResult};
use crate::types::{TranscriptionEvent, VoiceDevice};
use crate::voice::{audio_capture, text_injection, VoiceService};

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
