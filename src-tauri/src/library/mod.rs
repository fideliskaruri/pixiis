//! Game library subsystem.
//!
//! Owns scanning, in-memory state, persistence (favorites + playtime), and
//! launch. The first integration ships Steam + a generic folder scanner;
//! the other storefronts (Epic, GOG, EA, Xbox/UWP, Start Menu) hook in
//! later via the same `Provider` shape.

pub mod cache;
pub mod ea;
pub mod epic;
pub mod folder;
pub mod gog;
pub mod startmenu;
pub mod steam;

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
        let providers = build_providers(config, extra_folder_paths);
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

/// Build the provider list, honouring the optional `library.providers`
/// allow-list in user config. When unset (the default), every provider
/// is enabled and each one's `is_available()` decides whether it
/// actually contributes entries on this machine.
fn build_providers(
    config: Arc<dyn ConfigLookup>,
    extra_folder_paths: Vec<PathBuf>,
) -> Vec<Box<dyn Provider>> {
    // All providers we know how to construct, in scan-priority order.
    // Storefronts come first so their entries win the first-write-wins
    // dedup over the catch-all folder + start-menu scanners.
    let candidates: Vec<Box<dyn Provider>> = vec![
        Box::new(steam::SteamProvider::new(config.clone())),
        Box::new(epic::EpicProvider::new()),
        Box::new(gog::GogProvider::new()),
        Box::new(ea::EaProvider::new()),
        Box::new(folder::FolderProvider::new(extra_folder_paths)),
        Box::new(startmenu::StartMenuProvider::new()),
    ];

    let allow = config.get_strs("library.providers");
    if allow.is_empty() {
        return candidates;
    }
    let allow_set: std::collections::HashSet<String> =
        allow.into_iter().map(|s| s.to_lowercase()).collect();
    candidates
        .into_iter()
        .filter(|p| allow_set.contains(p.name()))
        .collect()
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
        // All storefront launchers register their own URL scheme (Steam,
        // Epic, GOG Galaxy, EA / Origin). Hand any URL-shaped command
        // straight to the OS shell — the launcher then takes over.
        if is_launcher_url(cmd) {
            return open_url(cmd);
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

    fn is_launcher_url(cmd: &str) -> bool {
        const SCHEMES: &[&str] = &[
            "steam://",
            "com.epicgames.launcher://",
            "goggalaxy://",
            "origin2://",
        ];
        SCHEMES.iter().any(|s| cmd.starts_with(s))
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
