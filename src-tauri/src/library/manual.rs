//! Manual library provider — emits entries the user explicitly registered
//! via `library.manual.apps` (the FileManagerPage flow).
//!
//! Distinct from [`crate::library::folder::FolderProvider`], which walks
//! `Program Files`/drive roots looking for unowned executables. Manual
//! entries are user-curated, so we set `metadata.is_game = true` on every
//! row by default — they wouldn't be in the config if the user didn't
//! mean it as a game.

use std::path::PathBuf;

use serde_json::{json, Map, Value};

use super::Provider;
use crate::types::{AppEntry, AppSource};

/// One entry parsed from `library.manual.apps[*]`. Mirrors the wire shape
/// the React FileManagerPage writes into config.
#[derive(Debug, Clone, Default)]
pub struct ManualEntry {
    pub name: String,
    pub exe_path: String,
    pub args: String,
    pub icon_path: String,
    pub working_dir: String,
}

pub struct ManualProvider {
    entries: Vec<ManualEntry>,
}

impl ManualProvider {
    pub fn new(entries: Vec<ManualEntry>) -> Self {
        Self { entries }
    }
}

impl Provider for ManualProvider {
    fn name(&self) -> &'static str {
        "manual"
    }

    fn is_available(&self) -> bool {
        !self.entries.is_empty()
    }

    fn scan(&self) -> Vec<AppEntry> {
        let mut out = Vec::with_capacity(self.entries.len());
        for raw in &self.entries {
            if raw.exe_path.trim().is_empty() {
                continue;
            }
            let display_name = if raw.name.trim().is_empty() {
                PathBuf::from(&raw.exe_path)
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| raw.exe_path.clone())
            } else {
                raw.name.clone()
            };

            let id = format!(
                "manual:{}",
                display_name.to_lowercase().replace(' ', "_")
            );

            let launch_command = if raw.args.trim().is_empty() {
                raw.exe_path.clone()
            } else {
                format!("{} {}", raw.exe_path, raw.args)
            };

            let mut metadata: Map<String, Value> = Map::new();
            // User added this on purpose — default to game-shaped so it
            // shows up on Home alongside storefront titles.
            metadata.insert("is_game".into(), json!(true));
            if !raw.working_dir.trim().is_empty() {
                metadata.insert("working_dir".into(), json!(raw.working_dir));
            }
            if !raw.args.trim().is_empty() {
                metadata.insert("args".into(), json!(raw.args));
            }

            let exe_path = if raw.exe_path.trim().is_empty() {
                None
            } else {
                Some(PathBuf::from(&raw.exe_path))
            };
            let icon_path = if raw.icon_path.trim().is_empty() {
                None
            } else {
                Some(PathBuf::from(&raw.icon_path))
            };

            out.push(AppEntry {
                id,
                name: display_name,
                source: AppSource::Manual,
                launch_command,
                exe_path,
                icon_path,
                art_url: None,
                metadata,
            });
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manual_scan_marks_entries_as_games() {
        let provider = ManualProvider::new(vec![ManualEntry {
            name: "Cool Game".into(),
            exe_path: "C:/Games/cool/cool.exe".into(),
            args: String::new(),
            icon_path: String::new(),
            working_dir: String::new(),
        }]);
        let entries = provider.scan();
        assert_eq!(entries.len(), 1);
        let entry = &entries[0];
        assert_eq!(entry.source, AppSource::Manual);
        assert_eq!(
            entry.metadata.get("is_game").and_then(|v| v.as_bool()),
            Some(true),
            "manual entries must default to is_game = true"
        );
        assert!(entry.is_game(), "AppEntry::is_game() should agree");
    }

    #[test]
    fn empty_exe_path_is_skipped() {
        let provider = ManualProvider::new(vec![ManualEntry::default()]);
        assert!(provider.scan().is_empty());
    }
}
