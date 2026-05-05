//! On-disk overlay for per-entry user state (favorites + playtime).
//!
//! Sits next to the scanned-entry list in memory; merged into AppEntry
//! at read time. Stored as a small JSON map keyed by AppEntry::id.

use std::collections::HashMap;
use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

#[derive(Clone, Default, Debug, Serialize, Deserialize)]
pub struct OverlayEntry {
    #[serde(default)]
    pub favorite: bool,
    #[serde(default)]
    pub playtime_minutes: u64,
    /// Unix seconds.
    #[serde(default)]
    pub last_played: u64,
}

pub type OverlayMap = HashMap<String, OverlayEntry>;

pub fn load(path: &Path) -> Option<OverlayMap> {
    let bytes = fs::read(path).ok()?;
    serde_json::from_slice(&bytes).ok()
}

pub fn save(path: &Path, map: &OverlayMap) -> Result<(), std::io::Error> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let bytes = serde_json::to_vec_pretty(map)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
    fs::write(path, bytes)
}
