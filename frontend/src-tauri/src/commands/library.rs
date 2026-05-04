//! Library command stubs — implemented in Phase 2 / 3.

use crate::error::{AppError, AppResult};

#[tauri::command]
pub fn library_get_all() -> AppResult<Vec<serde_json::Value>> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn library_scan() -> AppResult<u32> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn library_launch(_id: String) -> AppResult<()> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn library_toggle_favorite(_id: String) -> AppResult<bool> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn library_search(_query: String) -> AppResult<Vec<serde_json::Value>> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn library_get_icon(_id: String) -> AppResult<String> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn library_get_metadata(_id: String) -> AppResult<serde_json::Value> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn playtime_get(_id: String) -> AppResult<u64> {
    Err(AppError::NotImplemented)
}
