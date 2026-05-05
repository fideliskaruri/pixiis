//! Library Tauri commands — backed by `crate::library::LibraryService`.

use std::sync::Arc;

use serde_json::{Map, Value};
use tauri::State;

use crate::error::AppResult;
use crate::library::LibraryService;
use crate::types::{AppEntry, Playtime};

#[tauri::command]
pub async fn library_get_all(svc: State<'_, Arc<LibraryService>>) -> AppResult<Vec<AppEntry>> {
    Ok(svc.list())
}

#[tauri::command]
pub async fn library_scan(svc: State<'_, Arc<LibraryService>>) -> AppResult<Vec<AppEntry>> {
    let svc = svc.inner().clone();
    // Scanning hits the disk; offload it from the async runtime thread.
    Ok(tokio::task::spawn_blocking(move || svc.scan())
        .await
        .unwrap_or_default())
}

#[tauri::command]
pub async fn library_launch(
    svc: State<'_, Arc<LibraryService>>,
    id: String,
) -> AppResult<()> {
    svc.launch(&id)
}

#[tauri::command]
pub async fn library_toggle_favorite(
    svc: State<'_, Arc<LibraryService>>,
    id: String,
) -> AppResult<bool> {
    svc.toggle_favorite(&id)
}

#[tauri::command]
pub async fn library_search(
    svc: State<'_, Arc<LibraryService>>,
    query: String,
) -> AppResult<Vec<AppEntry>> {
    Ok(svc.search(&query))
}

#[tauri::command]
pub async fn library_get_icon(
    _svc: State<'_, Arc<LibraryService>>,
    _id: String,
) -> AppResult<Option<String>> {
    // Icons are served via the `art_url` field on AppEntry today;
    // the Phase 2 icon cache hooks in here later.
    Ok(None)
}

#[tauri::command]
pub async fn library_get_metadata(
    svc: State<'_, Arc<LibraryService>>,
    id: String,
) -> AppResult<Map<String, Value>> {
    Ok(svc.get(&id).map(|e| e.metadata).unwrap_or_default())
}

#[tauri::command]
pub async fn playtime_get(
    svc: State<'_, Arc<LibraryService>>,
    id: String,
) -> AppResult<Playtime> {
    let entry = svc.get(&id);
    let minutes = entry
        .as_ref()
        .and_then(|e| e.metadata.get("playtime_minutes").and_then(|v| v.as_u64()))
        .unwrap_or(0) as u32;
    let last_played = entry
        .as_ref()
        .and_then(|e| e.metadata.get("last_played").and_then(|v| v.as_f64()))
        .unwrap_or(0.0);
    Ok(Playtime {
        minutes,
        last_played,
    })
}
