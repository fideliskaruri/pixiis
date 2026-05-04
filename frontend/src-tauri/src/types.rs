//! Minimal Wave-1 type stubs needed by the controller subsystem.
//!
//! Pane 7 (`wave1/types`) owns the canonical, fully-decorated version of this
//! module (with `ts-rs` derives and full service DTOs). When that branch is
//! merged in, this file is expected to be replaced wholesale — the struct
//! shapes here mirror that draft so the controller modules continue to
//! compile after the swap.
//!
//! Keep this file deliberately small: only the symbols `controller/*` and
//! `commands/controller.rs` need today.

use serde::{Deserialize, Serialize};

// ── Controller ──────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[serde(rename_all = "lowercase")]
pub enum ButtonState {
    Pressed,
    Held,
    Released,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy)]
pub struct ControllerEvent {
    pub button: u32,
    pub state: ButtonState,
    pub timestamp: f64,
    #[serde(default)]
    pub duration: f64,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy)]
pub struct AxisEvent {
    pub axis: u32,
    pub value: f32,
    pub timestamp: f64,
}

// ── Macros ──────────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[serde(rename_all = "lowercase")]
pub enum MacroMode {
    Press,
    Hold,
    Combo,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum ActionKind {
    VoiceRecord,
    LaunchApp,
    SendKeys,
    NavigateUi,
    RunScript,
    Chain,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct MacroAction {
    pub action: ActionKind,
    pub mode: MacroMode,
    /// e.g. `"button:0"`, `"combo:4+5"`.
    pub trigger: String,
    /// app id, key sequence, page name, script path.
    #[serde(default)]
    pub target: String,
    #[serde(default)]
    pub chain: Vec<MacroAction>,
}
