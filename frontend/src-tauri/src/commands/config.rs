use crate::error::AppResult;
use serde_json::Value;
use tauri::{AppHandle, Manager};

#[tauri::command]
pub async fn config_get() -> AppResult<Value> {
    Ok(serde_json::json!({}))
}

#[tauri::command]
pub async fn config_set(_patch: Value) -> AppResult<()> {
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
