//! Voice command stubs — implemented in Phase 1B.

use crate::error::{AppError, AppResult};

#[tauri::command]
pub fn voice_start() -> AppResult<()> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn voice_stop() -> AppResult<()> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn voice_get_devices() -> AppResult<Vec<String>> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn voice_set_device(_name: String) -> AppResult<()> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn voice_speak(_text: String) -> AppResult<()> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn voice_inject_text(_text: String) -> AppResult<()> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn voice_get_transcript_log() -> AppResult<Vec<String>> {
    Err(AppError::NotImplemented)
}
