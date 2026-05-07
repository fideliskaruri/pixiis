//! Game library subsystem.
//!
//! Owns scanning, in-memory state, persistence (favorites + playtime), and
//! launch. The first integration ships Steam + a generic folder scanner;
//! the other storefronts (Epic, GOG, EA, Xbox/UWP, Start Menu) hook in
//! later via the same `Provider` shape.

pub mod cache;
pub mod folder;
pub mod steam;
pub mod xbox;

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

use parking_lot::RwLock;
use serde_json::{json, Map, Value};

use crate::error::{AppError, AppResult};
use crate::types::{AppEntry, AppSource};

/// One library scanner. Implementations live in submodules.
pub trait Provider: Send + Sync {
    fn name(&self) -> &'static str;
    fn is_available(&self) -> bool;
    fn scan(&self) -> Vec<AppEntry>;
}

pub struct LibraryService {
    inner: RwLock<State>,
    cache_path: PathBuf,
    providers: Vec<Box<dyn Provider>>,
}

#[derive(Default)]
struct State {
    /// Indexed by AppEntry::id.
    entries: HashMap<String, AppEntry>,
    /// Persisted state: favorite flag + playtime per id.
    overlay: cache::OverlayMap,
}

impl LibraryService {
    /// Build the service using a config-bearing object that can resolve
    /// dotted-path lookups (e.g. `library.steam.install_path`).
    /// `cache_dir` is where the favorites/playtime overlay JSON lives.
    pub fn new(
        config: Arc<dyn ConfigLookup>,
        cache_dir: PathBuf,
        extra_folder_paths: Vec<PathBuf>,
    ) -> Self {
        let cache_path = cache_dir.join("library_overlay.json");
        let overlay = cache::load(&cache_path).unwrap_or_default();
        let providers: Vec<Box<dyn Provider>> = vec![
            Box::new(steam::SteamProvider::new(config.clone())),
            Box::new(xbox::XboxProvider::new()),
            Box::new(folder::FolderProvider::new(extra_folder_paths)),
        ];
        Self {
            inner: RwLock::new(State {
                entries: HashMap::new(),
                overlay,
            }),
            cache_path,
            providers,
        }
    }

    /// Return all currently-known entries (the result of the last `scan`,
    /// or empty before the first scan).
    pub fn list(&self) -> Vec<AppEntry> {
        let s = self.inner.read();
        let mut out: Vec<AppEntry> = s
            .entries
            .values()
            .map(|e| Self::merge_overlay(e, &s.overlay))
            .collect();
        out.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));
        out
    }

    /// Run every available provider's scan, dedupe by id, replace state.
    pub fn scan(&self) -> Vec<AppEntry> {
        let mut by_id: HashMap<String, AppEntry> = HashMap::new();
        for p in &self.providers {
            if !p.is_available() {
                continue;
            }
            for entry in p.scan() {
                // First-write-wins so storefront entries take precedence
                // over the catch-all folder scanner if the same exe shows up
                // under both.
                by_id.entry(entry.id.clone()).or_insert(entry);
            }
        }
        let mut s = self.inner.write();
        s.entries = by_id;
        drop(s);
        self.list()
    }

    /// Look up an entry by id (with overlay merged).
    pub fn get(&self, id: &str) -> Option<AppEntry> {
        let s = self.inner.read();
        s.entries.get(id).map(|e| Self::merge_overlay(e, &s.overlay))
    }

    /// Toggle favorite, persist, return new value.
    pub fn toggle_favorite(&self, id: &str) -> AppResult<bool> {
        let mut s = self.inner.write();
        if !s.entries.contains_key(id) {
            return Err(AppError::NotFound(format!("library: {id}")));
        }
        let entry = s.overlay.entry(id.to_string()).or_default();
        entry.favorite = !entry.favorite;
        let new = entry.favorite;
        let snapshot = s.overlay.clone();
        drop(s);
        let _ = cache::save(&self.cache_path, &snapshot);
        Ok(new)
    }

    pub fn search(&self, query: &str) -> Vec<AppEntry> {
        let q = query.to_lowercase();
        if q.trim().is_empty() {
            return self.list();
        }
        self.list()
            .into_iter()
            .filter(|e| e.name.to_lowercase().contains(&q))
            .collect()
    }

    /// Launch the underlying entry. Steam URLs are handed to the OS
    /// shell; everything else is started as a detached process.
    pub fn launch(&self, id: &str) -> AppResult<()> {
        let entry = self
            .get(id)
            .ok_or_else(|| AppError::NotFound(format!("library: {id}")))?;
        launcher::launch(&entry)
    }

    fn merge_overlay(entry: &AppEntry, overlay: &cache::OverlayMap) -> AppEntry {
        let mut out = entry.clone();
        if let Some(o) = overlay.get(&entry.id) {
            let m = &mut out.metadata;
            if o.favorite {
                m.insert("favorite".into(), json!(true));
            }
            if o.playtime_minutes > 0 {
                m.insert("playtime_minutes".into(), json!(o.playtime_minutes));
            }
            if o.last_played > 0 {
                m.insert("last_played".into(), json!(o.last_played));
            }
        }
        out
    }
}

/// Trait used by providers to look up dotted-path config values without
/// pulling in the whole config crate. The `services::ServicesConfig`
/// already uses the same `from_lookup` shape.
pub trait ConfigLookup: Send + Sync {
    fn get_str(&self, key: &str) -> Option<String>;
    fn get_strs(&self, key: &str) -> Vec<String> {
        self.get_str(key)
            .map(|s| s.split(',').map(|p| p.trim().to_string()).collect())
            .unwrap_or_default()
    }
}

/// A no-op config lookup — used until the real config service lands.
#[derive(Default)]
pub struct EmptyConfig;
impl ConfigLookup for EmptyConfig {
    fn get_str(&self, _key: &str) -> Option<String> {
        None
    }
}

mod launcher {
    use super::*;
    use std::process::Command;

    pub fn launch(entry: &AppEntry) -> AppResult<()> {
        let cmd = &entry.launch_command;
        if cmd.starts_with("steam://") {
            // Use the OS shell — Tauri's tauri-plugin-shell can also do this,
            // but since Steam URLs don't need the plugin's allowlist, going
            // direct keeps the launch path local.
            return open_url(cmd);
        }
        // Xbox / UWP entries carry `shell:appsFolder\<AUMID>` from
        // `library/xbox.rs` — same UWPHook pattern the Python wrapper used.
        if cmd.starts_with("shell:") {
            return open_shell_uri(cmd);
        }

        let cwd = entry
            .exe_path
            .as_ref()
            .and_then(|p| p.parent().map(|p| p.to_path_buf()));

        let mut command = Command::new(cmd);
        if let Some(c) = cwd {
            command.current_dir(c);
        }
        command
            .spawn()
            .map(|_| ())
            .map_err(|e| AppError::Other(format!("launch failed: {e}")))
    }

    fn open_url(url: &str) -> AppResult<()> {
        #[cfg(target_os = "windows")]
        let res = Command::new("cmd").args(["/c", "start", "", url]).spawn();
        #[cfg(target_os = "linux")]
        let res = Command::new("xdg-open").arg(url).spawn();
        #[cfg(target_os = "macos")]
        let res = Command::new("open").arg(url).spawn();

        res.map(|_| ())
            .map_err(|e| AppError::Other(format!("open url failed: {e}")))
    }

    /// Hand a `shell:` URI to Explorer. UWPHook's reference launch path
    /// — more reliable for `shell:appsFolder\<AUMID>` than `cmd /c start`,
    /// which occasionally swallows the AUMID argument when it contains a
    /// `!` character (cmd's history expansion) on some locales.
    fn open_shell_uri(uri: &str) -> AppResult<()> {
        #[cfg(target_os = "windows")]
        let res = Command::new("explorer.exe").arg(uri).spawn();
        // Non-Windows: `shell:` is meaningless; treat as a no-op error so
        // tests fail loudly if the launcher is exercised cross-platform.
        #[cfg(not(target_os = "windows"))]
        let res: std::io::Result<std::process::Child> = Err(std::io::Error::new(
            std::io::ErrorKind::Unsupported,
            "shell: URIs are Windows-only",
        ));

        res.map(|_| ())
            .map_err(|e| AppError::Other(format!("launch shell uri failed: {e}")))
    }
}

#[allow(dead_code)] // unused until commands wire metadata through
pub(crate) fn metadata_for(id: &str, library: &LibraryService) -> Map<String, Value> {
    library.get(id).map(|e| e.metadata).unwrap_or_default()
}

impl AppSource {
    /// Stable string key for `id` prefixes.
    pub fn slug(&self) -> &'static str {
        match self {
            AppSource::Steam => "steam",
            AppSource::Xbox => "xbox",
            AppSource::Epic => "epic",
            AppSource::Gog => "gog",
            AppSource::Ea => "ea",
            AppSource::Startmenu => "sm",
            AppSource::Manual => "folder",
        }
    }
}
