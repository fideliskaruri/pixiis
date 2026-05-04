//! Config + app lifecycle command stubs — implemented in Phase 4.

use tauri::{AppHandle, Manager, Runtime};

use crate::error::{AppError, AppResult};

#[tauri::command]
pub fn config_get(_key: String) -> AppResult<serde_json::Value> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn config_set(_key: String, _value: serde_json::Value) -> AppResult<()> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn config_reset() -> AppResult<()> {
    Err(AppError::NotImplemented)
}

#[tauri::command]
pub fn app_quit<R: Runtime>(app: AppHandle<R>) -> AppResult<()> {
    app.exit(0);
    Ok(())
}

#[tauri::command]
pub fn app_show<R: Runtime>(app: AppHandle<R>) -> AppResult<()> {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
    Ok(())
}

#[tauri::command]
pub fn app_set_autostart(_enabled: bool) -> AppResult<()> {
    Err(AppError::NotImplemented)
}
