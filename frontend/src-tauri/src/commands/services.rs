use crate::error::AppResult;
use serde_json::Value;

#[tauri::command]
pub async fn services_twitch_streams(_game_name: String) -> AppResult<Vec<Value>> {
    Ok(Vec::new())
}

#[tauri::command]
pub async fn services_youtube_trailer(_game_name: String) -> AppResult<Option<String>> {
    Ok(None)
}

#[tauri::command]
pub async fn services_oauth_start(_provider: String) -> AppResult<String> {
    Ok(String::new())
}

#[tauri::command]
pub async fn services_image_url(url: String) -> AppResult<String> {
    // Pass-through stub: real impl will proxy through Rust to dodge CORS.
    Ok(url)
}
