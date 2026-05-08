//! Wire-format types for the Tauri ↔ React boundary.
//!
//! Ported from `src/pixiis/core/types.py` plus service DTOs from
//! `src/pixiis/services/{rawg,twitch,youtube}.py`.
//!
//! Every public struct/enum derives `Serialize, Deserialize, TS` and is
//! marked `#[ts(export, export_to = "../src/api/types/")]`, so the ts-rs
//! `cargo test` hooks emit one `.ts` declaration per type into
//! `frontend/src/api/types/` (the path is relative to `CARGO_MANIFEST_DIR`).

use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use ts_rs::TS;

// ── App / Library ────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, TS, Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[serde(rename_all = "lowercase")]
#[ts(export, export_to = "../src/api/types/")]
pub enum AppSource {
    Steam,
    Xbox,
    Epic,
    Gog,
    Ea,
    Startmenu,
    Manual,
    Folder,
}

#[derive(Serialize, Deserialize, TS, Debug, Clone)]
#[ts(export, export_to = "../src/api/types/")]
pub struct AppEntry {
    pub id: String,
    pub name: String,
    pub source: AppSource,
    pub launch_command: String,

    #[ts(type = "string | null")]
    pub exe_path: Option<PathBuf>,

    #[ts(type = "string | null")]
    pub icon_path: Option<PathBuf>,

    pub art_url: Option<String>,

    #[ts(type = "Record<string, unknown>")]
    pub metadata: Map<String, Value>,
}

impl AppEntry {
    /// True if the user has marked this entry as a favorite.
    pub fn is_favorite(&self) -> bool {
        self.metadata
            .get("favorite")
            .and_then(Value::as_bool)
            .unwrap_or(false)
    }

    /// Total tracked playtime in minutes (stored in metadata).
    pub fn playtime_minutes(&self) -> u32 {
        self.metadata
            .get("playtime_minutes")
            .and_then(Value::as_u64)
            .map(|v| v.min(u32::MAX as u64) as u32)
            .unwrap_or(0)
    }

    /// Epoch seconds of last play session (stored in metadata).
    pub fn last_played(&self) -> f64 {
        self.metadata
            .get("last_played")
            .and_then(Value::as_f64)
            .unwrap_or(0.0)
    }

    /// Human-readable playtime, e.g. "12.5 hrs" or "45 min".
    pub fn playtime_display(&self) -> String {
        let mins = self.playtime_minutes();
        if mins == 0 {
            return String::new();
        }
        if mins < 60 {
            return format!("{mins} min");
        }
        let hours = f64::from(mins) / 60.0;
        if (hours - hours.trunc()).abs() < f64::EPSILON {
            format!("{} hrs", hours as u32)
        } else {
            format!("{hours:.1} hrs")
        }
    }

    /// True if this entry is likely a game (vs. a regular app).
    ///
    /// Steam/Epic/GOG/EA always game; Xbox only if `metadata.is_xbox_game`;
    /// Manual entries opt in via `metadata.is_game` (the manual provider
    /// sets this to `true` by default — the user added them on purpose);
    /// folder-scanned and start-menu entries default to false.
    pub fn is_game(&self) -> bool {
        match self.source {
            AppSource::Steam | AppSource::Epic | AppSource::Gog | AppSource::Ea => true,
            AppSource::Xbox => self
                .metadata
                .get("is_xbox_game")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            AppSource::Manual => self
                .metadata
                .get("is_game")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            AppSource::Folder | AppSource::Startmenu => false,
        }
    }

    /// True if the entry appears installed on this machine.
    pub fn is_installed(&self) -> bool {
        if let Some(p) = &self.exe_path {
            if p.exists() {
                return true;
            }
        }
        if matches!(self.source, AppSource::Xbox) {
            return true;
        }
        !self.launch_command.is_empty()
    }
}

// ── Controller ───────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, TS, Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[serde(rename_all = "lowercase")]
#[ts(export, export_to = "../src/api/types/")]
pub enum ButtonState {
    Pressed,
    Held,
    Released,
}

#[derive(Serialize, Deserialize, TS, Debug, Clone, Copy)]
#[ts(export, export_to = "../src/api/types/")]
pub struct ControllerEvent {
    pub button: u32,
    pub state: ButtonState,
    pub timestamp: f64,
    #[serde(default)]
    pub duration: f64,
}

#[derive(Serialize, Deserialize, TS, Debug, Clone, Copy)]
#[ts(export, export_to = "../src/api/types/")]
pub struct AxisEvent {
    pub axis: u32,
    pub value: f32,
    pub timestamp: f64,
}

// ── Macros ───────────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, TS, Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[serde(rename_all = "lowercase")]
#[ts(export, export_to = "../src/api/types/")]
pub enum MacroMode {
    Press,
    Hold,
    Combo,
}

#[derive(Serialize, Deserialize, TS, Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
#[ts(export, export_to = "../src/api/types/")]
pub enum ActionKind {
    VoiceRecord,
    LaunchApp,
    SendKeys,
    NavigateUi,
    RunScript,
    Chain,
}

#[derive(Serialize, Deserialize, TS, Debug, Clone)]
#[ts(export, export_to = "../src/api/types/")]
pub struct MacroAction {
    pub action: ActionKind,
    pub mode: MacroMode,
    /// e.g. "button:0", "combo:4+5"
    pub trigger: String,
    /// app id, key sequence, page name, script path.
    #[serde(default)]
    pub target: String,
    #[serde(default)]
    pub chain: Vec<MacroAction>,
}

// ── Navigation ───────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, TS, Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[serde(rename_all = "lowercase")]
#[ts(export, export_to = "../src/api/types/")]
pub enum Direction {
    Up,
    Down,
    Left,
    Right,
    Activate,
    Back,
}

#[derive(Serialize, Deserialize, TS, Debug, Clone, Copy)]
#[ts(export, export_to = "../src/api/types/")]
pub struct NavigationEvent {
    pub direction: Direction,
    pub timestamp: f64,
}

// ── Transcription ────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, TS, Debug, Clone)]
#[ts(export, export_to = "../src/api/types/")]
pub struct TranscriptionEvent {
    pub text: String,
    pub is_final: bool,
    pub timestamp: f64,
}

// ── Service DTOs ─────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, TS, Debug, Clone, Default)]
#[ts(export, export_to = "../src/api/types/")]
pub struct RawgGameData {
    #[serde(default)]
    pub id: u32,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub rating: f32,
    #[serde(default)]
    pub metacritic: i32,
    #[serde(default)]
    pub genres: Vec<String>,
    #[serde(default)]
    pub platforms: Vec<String>,
    #[serde(default)]
    pub screenshots: Vec<String>,
    #[serde(default)]
    pub playtime: u32,
    #[serde(default)]
    pub background_image: String,
    #[serde(default)]
    pub released: String,
}

#[derive(Serialize, Deserialize, TS, Debug, Clone, Default)]
#[ts(export, export_to = "../src/api/types/")]
pub struct TwitchStream {
    #[serde(default)]
    pub user_name: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub viewer_count: u32,
    #[serde(default)]
    pub thumbnail_url: String,
    #[serde(default)]
    pub stream_url: String,
}

/// A single YouTube video search result (mapped from `services/youtube.py::YouTubeResult`).
#[derive(Serialize, Deserialize, TS, Debug, Clone, Default)]
#[ts(export, export_to = "../src/api/types/")]
pub struct YouTubeTrailer {
    #[serde(default)]
    pub video_id: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub thumbnail_url: String,
    #[serde(default)]
    pub channel: String,
}

// ── Boundary helpers ─────────────────────────────────────────────────────────
//
// These are not in `core/types.py` but are needed so Pane 5's IPC commands
// don't fall back to weakly-typed `serde_json::Value`. Each is the smallest
// shape that captures the stub's current fixture.

/// Result of `playtime_get` — total tracked minutes + epoch-seconds of last
/// session. Matches the keys Pane 5's stub returns and the helpers on
/// [`AppEntry`].
#[derive(Serialize, Deserialize, TS, Debug, Clone, Copy, Default)]
#[ts(export, export_to = "../src/api/types/")]
pub struct Playtime {
    #[serde(default)]
    pub minutes: u32,
    #[serde(default)]
    pub last_played: f64,
}

/// Result of `controller_get_state`. Pane 8 owns the gilrs-backed implementation
/// and may extend the shape; this is the minimum surface the IPC boundary
/// promises today (matches the stub fixture).
#[derive(Serialize, Deserialize, TS, Debug, Clone, Default)]
#[ts(export, export_to = "../src/api/types/")]
pub struct ControllerState {
    #[serde(default)]
    pub connected: bool,
    #[serde(default)]
    pub buttons: Vec<u32>,
    #[serde(default)]
    pub axes: Vec<f32>,
}

/// One audio input device, as returned by `voice_get_devices`.
#[derive(Serialize, Deserialize, TS, Debug, Clone, Default)]
#[ts(export, export_to = "../src/api/types/")]
pub struct VoiceDevice {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub is_default: bool,
}
