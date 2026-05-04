use crate::error::AppResult;
use serde_json::Value;

#[tauri::command]
pub async fn voice_start() -> AppResult<()> {
    Ok(())
}

#[tauri::command]
pub async fn voice_stop() -> AppResult<Value> {
    Ok(serde_json::json!({ "text": "" }))
}

#[tauri::command]
pub async fn voice_get_devices() -> AppResult<Vec<Value>> {
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
pub async fn voice_get_transcript_log(_limit: Option<u32>) -> AppResult<Vec<Value>> {
    Ok(Vec::new())
}
