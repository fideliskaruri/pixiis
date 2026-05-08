//! System power commands — sleep, lock, restart.
//!
//! Each command shells out to a built-in Windows binary; on non-Windows
//! targets the call is a clean `Err(AppError::Other)` so the UI can
//! surface a message instead of silently failing. The frontend is
//! responsible for confirming destructive actions (Restart) before
//! invoking these — the Rust side does not double-confirm.

use crate::error::{AppError, AppResult};

#[cfg(target_os = "windows")]
fn run_windows(cmd: &str, args: &[&str]) -> AppResult<()> {
    use std::process::Command;
    Command::new(cmd)
        .args(args)
        .spawn()
        .map_err(|e| AppError::Other(format!("failed to spawn {cmd}: {e}")))?;
    Ok(())
}

#[cfg(not(target_os = "windows"))]
fn run_windows(_cmd: &str, _args: &[&str]) -> AppResult<()> {
    Err(AppError::Other(
        "system power commands are only implemented on Windows".into(),
    ))
}

/// Suspend the machine. Uses `rundll32 powrprof.dll,SetSuspendState`.
/// The `0,1,0` argument set means "no hibernate, force, no wake events".
#[tauri::command]
pub async fn system_sleep() -> AppResult<()> {
    run_windows("rundll32.exe", &["powrprof.dll,SetSuspendState", "0,1,0"])
}

/// Lock the workstation (Win+L equivalent).
#[tauri::command]
pub async fn system_lock() -> AppResult<()> {
    run_windows("rundll32.exe", &["user32.dll,LockWorkStation"])
}

/// Restart the machine immediately. The frontend MUST confirm before
/// calling this — there is no built-in delay.
#[tauri::command]
pub async fn system_restart() -> AppResult<()> {
    run_windows("shutdown.exe", &["/r", "/t", "0"])
}
