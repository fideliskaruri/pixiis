//! Library Tauri commands — backed by `crate::library::LibraryService`.

use std::sync::Arc;

use serde::Serialize;
use serde_json::{Map, Value};
use tauri::{AppHandle, Emitter, State};
use ts_rs::TS;

use crate::error::{AppError, AppResult};
use crate::library::process::{ProcessTracker, RunningGame};
use crate::library::{LibraryService, ProviderReport};
use crate::types::{AppEntry, Playtime};

#[tauri::command]
pub async fn library_get_all(svc: State<'_, Arc<LibraryService>>) -> AppResult<Vec<AppEntry>> {
    Ok(svc.list())
}

/// Wire shape returned by `library_scan` — entries plus the per-provider
/// report so the frontend can render what actually ran (and what failed)
/// even when the live `library:scan:progress` event stream was missed.
#[derive(Serialize, TS)]
#[ts(export, export_to = "../src/api/types/")]
pub struct ScanResult {
    pub entries: Vec<AppEntry>,
    pub providers: Vec<ProviderReport>,
}

#[tauri::command]
pub async fn library_scan(
    app: AppHandle,
    svc: State<'_, Arc<LibraryService>>,
) -> AppResult<ScanResult> {
    let svc = svc.inner().clone();
    let app_for_task = app.clone();
    // Scanning hits the disk; offload it from the async runtime thread.
    // scan_with_progress catches per-provider panics internally, so the
    // only way spawn_blocking's JoinHandle fails is a defect in the
    // scheduler itself — surface that as an explicit error rather than
    // silently returning an empty list (the bug this command had before).
    let report = tokio::task::spawn_blocking(move || {
        svc.scan_with_progress(Some(&app_for_task))
    })
    .await
    .map_err(|e| AppError::Other(format!("scan task failed: {e}")))?;
    Ok(ScanResult {
        entries: report.entries,
        providers: report.providers,
    })
}

#[tauri::command]
pub async fn library_launch(
    app: AppHandle,
    svc: State<'_, Arc<LibraryService>>,
    tracker: State<'_, Arc<ProcessTracker>>,
    id: String,
) -> AppResult<()> {
    let (entry, pid) = svc.launch_with_pid(&id)?;
    tracker.track_launch(&entry, pid);
    // Tell the UI immediately so the Now-Playing pill mounts even before
    // the watcher's first tick — it'll flip from "launching" to
    // "running" once a real PID resolves.
    let _ = app.emit("library:running:changed", tracker.list());
    Ok(())
}

#[tauri::command]
pub async fn library_running(
    tracker: State<'_, Arc<ProcessTracker>>,
) -> AppResult<Vec<RunningGame>> {
    Ok(tracker.list())
}

#[tauri::command]
pub async fn library_stop(
    app: AppHandle,
    tracker: State<'_, Arc<ProcessTracker>>,
    id: String,
) -> AppResult<()> {
    tracker.stop(&id)?;
    // Don't wait on the watcher's poll cycle — emit immediately so the
    // pill disappears as soon as the kill signal goes out. The watcher
    // will reconcile playtime on its next tick.
    let _ = app.emit("library:running:changed", tracker.list());
    Ok(())
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
