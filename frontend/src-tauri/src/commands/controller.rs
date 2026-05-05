use crate::error::AppResult;
use crate::types::{ControllerState, MacroAction};

#[tauri::command]
pub async fn controller_register_macro(_name: String, _sequence: MacroAction) -> AppResult<()> {
    Ok(())
}

#[tauri::command]
pub async fn controller_get_state() -> AppResult<ControllerState> {
    Ok(ControllerState::default())
}

#[tauri::command]
pub async fn vibration_pulse(
    _left: f32,
    _right: f32,
    _duration_ms: u32,
) -> AppResult<()> {
    Ok(())
}
