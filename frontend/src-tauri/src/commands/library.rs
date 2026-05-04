use crate::error::AppResult;
use serde_json::Value;

#[tauri::command]
pub async fn library_get_all() -> AppResult<Vec<Value>> {
    Ok(Vec::new())
}

#[tauri::command]
pub async fn library_scan() -> AppResult<Vec<Value>> {
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
pub async fn library_search(_query: String) -> AppResult<Vec<Value>> {
    Ok(Vec::new())
}

#[tauri::command]
pub async fn library_get_icon(_id: String) -> AppResult<Option<String>> {
    Ok(None)
}

#[tauri::command]
pub async fn library_get_metadata(_id: String) -> AppResult<Value> {
    Ok(Value::Null)
}

#[tauri::command]
pub async fn playtime_get(_id: String) -> AppResult<Value> {
    Ok(serde_json::json!({ "minutes": 0, "last_played": 0 }))
}
