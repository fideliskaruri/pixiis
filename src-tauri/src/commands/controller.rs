//! Controller-related Tauri commands.
//!
//! Pane 8 only fully implements `controller_get_state` and
//! `controller_register_macro`. `vibration_pulse` is owned by Pane 9 and
//! left as `unimplemented!()` here so `lib.rs`'s invoke_handler list keeps
//! resolving until that branch is integrated.

use std::sync::Arc;

use tauri::State;

use crate::controller::macros::MacroDefRaw;
use crate::controller::{ControllerService, ControllerStateView};
use crate::error::{AppError, AppResult};

#[tauri::command]
pub fn controller_get_state(
    svc: State<'_, Arc<ControllerService>>,
) -> ControllerStateView {
    svc.snapshot()
}

#[tauri::command]
pub fn controller_register_macro(
    svc: State<'_, Arc<ControllerService>>,
    trigger: String,
    mode: String,
    action: String,
    target: Option<String>,
) -> AppResult<()> {
    svc.register_macro(MacroDefRaw {
        trigger,
        mode,
        action,
        target: target.unwrap_or_default(),
    })
    .map_err(|e| AppError::InvalidArg(e.to_string()))
}

#[tauri::command]
pub fn vibration_pulse(
    _strong: f32,
    _weak: f32,
    _duration_ms: u32,
) -> AppResult<()> {
    // Owned by Pane 9 (services::vibration). Leaving the body unimplemented
    // so the invoke_handler list compiles until that branch lands.
    Err(AppError::NotImplemented)
}
