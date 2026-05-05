use crate::error::AppResult;
use crate::types::{AppEntry, Playtime};
use serde_json::{Map, Value};

#[tauri::command]
pub async fn library_get_all() -> AppResult<Vec<AppEntry>> {
    Ok(Vec::new())
}

#[tauri::command]
pub async fn library_scan() -> AppResult<Vec<AppEntry>> {
    Ok(Vec::new())
}

#[tauri::command]
pub async fn library_launch(_id: String) -> AppResult<()> {
    Ok(())
}

#[tauri::command]
pub async fn library_toggle_favorite(_id: String) -> AppResult<bool> {
    Ok(false)
}

#[tauri::command]
pub async fn library_search(_query: String) -> AppResult<Vec<AppEntry>> {
    Ok(Vec::new())
}

#[tauri::command]
pub async fn library_get_icon(_id: String) -> AppResult<Option<String>> {
    Ok(None)
}

#[tauri::command]
pub async fn library_get_metadata(_id: String) -> AppResult<Map<String, Value>> {
    Ok(Map::new())
}

#[tauri::command]
pub async fn playtime_get(_id: String) -> AppResult<Playtime> {
    Ok(Playtime::default())
}
