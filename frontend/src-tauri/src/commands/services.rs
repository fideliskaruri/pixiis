//! Services command stubs — owned by Pane 9 (`wave1/services`) /Phase 5.

use crate::error::{AppError, AppResult};

#[tauri::command]
pub fn services_twitch_streams(_game: String) -> AppResult<Vec<serde_json::Value>> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn services_youtube_trailer(_game: String) -> AppResult<Option<serde_json::Value>> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn services_oauth_start(_provider: String) -> AppResult<String> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn services_image_url(_url: String) -> AppResult<String> {
    Err(AppError::NotImplemented)
}
