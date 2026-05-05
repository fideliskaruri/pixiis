use crate::error::AppResult;
use crate::types::{TranscriptionEvent, VoiceDevice};

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
pub async fn voice_speak(_text: String, _voice: Option<String>) -> AppResult<()> {
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
