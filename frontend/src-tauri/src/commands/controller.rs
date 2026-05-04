use crate::error::AppResult;
use serde_json::Value;

#[tauri::command]
pub async fn controller_register_macro(_name: String, _sequence: Value) -> AppResult<()> {
    Ok(())
}

#[tauri::command]
pub async fn controller_get_state() -> AppResult<Value> {
    Ok(serde_json::json!({
        "connected": false,
        "buttons": [],
        "axes": []
    }))
}

#[tauri::command]
pub async fn vibration_pulse(
    _left: f32,
    _right: f32,
    _duration_ms: u32,
) -> AppResult<()> {
    Ok(())
}
