use std::path::PathBuf;

use crate::error::{AppError, AppResult};
use serde_json::{Map, Value};
use tauri::{AppHandle, Manager};

#[tauri::command]
pub async fn config_get() -> AppResult<Map<String, Value>> {
    Ok(Map::new())
}

#[tauri::command]
pub async fn config_set(_patch: Map<String, Value>) -> AppResult<()> {
    Ok(())
}

#[tauri::command]
pub async fn config_reset() -> AppResult<()> {
    Ok(())
}

#[tauri::command]
pub async fn app_quit(app: AppHandle) -> AppResult<()> {
    app.exit(0);
    Ok(())
}

#[tauri::command]
pub async fn app_show(app: AppHandle) -> AppResult<()> {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
    Ok(())
}

#[tauri::command]
pub async fn app_set_autostart(_enabled: bool) -> AppResult<()> {
    // Phase 1A stub. Real impl will use the autostart plugin's manager.
    Ok(())
}

// ── First-launch onboarding marker ───────────────────────────────────
//
// Mirrors the Python original's `cache_dir() / .onboarded` sentinel —
// presence (any contents) means the user has finished or skipped the
// onboarding flow. Stored under Tauri's app_data_dir which on Windows
// resolves to `%APPDATA%/pixiis/`.

fn onboarded_marker_path(app: &AppHandle) -> AppResult<PathBuf> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| AppError::Other(format!("app_data_dir unavailable: {e}")))?;
    Ok(dir.join(".onboarded"))
}

#[tauri::command]
pub async fn app_get_onboarded(app: AppHandle) -> AppResult<bool> {
    Ok(onboarded_marker_path(&app)?.exists())
}

#[tauri::command]
pub async fn app_set_onboarded(app: AppHandle, value: bool) -> AppResult<()> {
    let path = onboarded_marker_path(&app)?;
    if value {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(&path, b"1")?;
    } else if path.exists() {
        std::fs::remove_file(&path)?;
    }
    Ok(())
}
