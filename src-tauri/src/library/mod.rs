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
pub mod manual;
pub mod process;
pub mod startmenu;
pub mod steam;
pub mod xbox;

use std::collections::HashMap;
use std::panic::AssertUnwindSafe;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Instant;

use parking_lot::RwLock;
use serde::Serialize;
use serde_json::{json, Map, Value};
use tauri::{AppHandle, Emitter};
use ts_rs::TS;

use crate::error::{AppError, AppResult};
use crate::types::{AppEntry, AppSource};

/// One library scanner. Implementations live in submodules.
pub trait Provider: Send + Sync {
    fn name(&self) -> &'static str;
    fn is_available(&self) -> bool;
    fn scan(&self) -> Vec<AppEntry>;
}

/// Per-provider outcome from a single scan pass. Emitted as a
/// `library:scan:progress` event and also returned in [`ScanReport`] so
/// the frontend can render a final summary even when it missed events.
#[derive(Serialize, TS, Clone, Debug)]
#[ts(export, export_to = "../src/api/types/")]
pub struct ProviderReport {
    /// Provider key — matches `Provider::name()` (e.g. `"steam"`).
    pub provider: String,
    pub state: ProviderState,
    pub count: usize,
    pub error: Option<String>,
    pub elapsed_ms: u64,
}

#[derive(Serialize, TS, Clone, Debug)]
#[serde(rename_all = "lowercase")]
#[ts(export, export_to = "../src/api/types/")]
pub enum ProviderState {
    Scanning,
    Done,
    Unavailable,
    Error,
}

/// Aggregate result of [`LibraryService::scan_with_progress`].
pub struct ScanReport {
    pub entries: Vec<AppEntry>,
    pub providers: Vec<ProviderReport>,
}

pub struct LibraryService {
    inner: RwLock<State>,
    /// Persisted state (favorite flag + playtime per id). Held in a
    /// separate Arc<RwLock> so the running-game tracker can write
    /// playtime independently — the tracker only ever needs the overlay,
    /// not the full library state.
    overlay: Arc<RwLock<cache::OverlayMap>>,
    cache_path: PathBuf,
    log_path: PathBuf,
    providers: Vec<Box<dyn Provider>>,
}

#[derive(Default)]
struct State {
    /// Indexed by AppEntry::id.
    entries: HashMap<String, AppEntry>,
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
        let log_path = cache_dir.join("scan_debug.log");
        let overlay = cache::load(&cache_path).unwrap_or_default();
        let providers = build_providers(config, extra_folder_paths);
        Self {
            inner: RwLock::new(State {
                entries: HashMap::new(),
            }),
            overlay: Arc::new(RwLock::new(overlay)),
            cache_path,
            log_path,
            providers,
        }
    }

    /// Path to the overlay JSON — used by the running-game tracker to
    /// persist playtime through the same file.
    pub fn cache_path(&self) -> &Path {
        &self.cache_path
    }

    /// Shared handle on the favorites/playtime overlay. Lets the running-
    /// game tracker accumulate playtime without going through the
    /// LibraryService at every tick.
    pub fn overlay_handle(&self) -> Arc<RwLock<cache::OverlayMap>> {
        self.overlay.clone()
    }

    /// Return all currently-known entries (the result of the last `scan`,
    /// or empty before the first scan).
    pub fn list(&self) -> Vec<AppEntry> {
        let s = self.inner.read();
        let overlay = self.overlay.read();
        let mut out: Vec<AppEntry> = s
            .entries
            .values()
            .map(|e| Self::merge_overlay(e, &overlay))
            .collect();
        out.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));
        out
    }

    /// Backwards-compatible thin wrapper around [`Self::scan_with_progress`]
    /// for callers (tests, future schedulers) that have no `AppHandle`.
    pub fn scan(&self) -> Vec<AppEntry> {
        self.scan_with_progress(None).entries
    }

    /// Run every provider's scan in isolation, dedupe entries by id, replace
    /// state, and return a per-provider report. Each provider is wrapped in
    /// `catch_unwind` so a single misbehaving scanner can no longer collapse
    /// the whole pass — the panic is recorded as `ProviderState::Error` with
    /// the panic message and execution continues with the remaining
    /// providers.
    ///
    /// When `app` is `Some`, three things happen for each provider:
    /// 1. A `library:scan:progress` event with `state = "scanning"` fires
    ///    before the call.
    /// 2. A second event fires after the call with the terminal state
    ///    (`done` / `unavailable` / `error`) and the entry count or error
    ///    message.
    /// 3. The same record is appended to `<app_data_dir>/scan_debug.log`
    ///    (rotated at ~1 MB, keeping the most recent ~100 KB) so the user
    ///    can paste it for triage.
    pub fn scan_with_progress(&self, app: Option<&AppHandle>) -> ScanReport {
        let mut by_id: HashMap<String, AppEntry> = HashMap::new();
        let mut reports: Vec<ProviderReport> = Vec::with_capacity(self.providers.len());

        for p in &self.providers {
            let name = p.name().to_string();

            if !p.is_available() {
                let r = ProviderReport {
                    provider: name.clone(),
                    state: ProviderState::Unavailable,
                    count: 0,
                    error: None,
                    elapsed_ms: 0,
                };
                emit_progress(app, &r);
                append_scan_log(&self.log_path, &r);
                reports.push(r);
                continue;
            }

            // Tell the UI the provider is starting so it can show a spinner.
            emit_progress(
                app,
                &ProviderReport {
                    provider: name.clone(),
                    state: ProviderState::Scanning,
                    count: 0,
                    error: None,
                    elapsed_ms: 0,
                },
            );

            let started = Instant::now();
            // `Provider` only requires Send + Sync; AssertUnwindSafe lets us
            // catch panics without imposing UnwindSafe on every provider impl.
            let outcome = std::panic::catch_unwind(AssertUnwindSafe(|| p.scan()));
            let elapsed_ms = started.elapsed().as_millis() as u64;

            let r = match outcome {
                Ok(entries) => {
                    let count = entries.len();
                    for entry in entries {
                        // First-write-wins so storefront entries take
                        // precedence over the catch-all folder scanner if the
                        // same exe shows up under both.
                        by_id.entry(entry.id.clone()).or_insert(entry);
                    }
                    ProviderReport {
                        provider: name,
                        state: ProviderState::Done,
                        count,
                        error: None,
                        elapsed_ms,
                    }
                }
                Err(payload) => {
                    let msg = panic_message(payload);
                    eprintln!("[library] provider '{}' panicked: {msg}", p.name());
                    ProviderReport {
                        provider: name,
                        state: ProviderState::Error,
                        count: 0,
                        error: Some(msg),
                        elapsed_ms,
                    }
                }
            };

            emit_progress(app, &r);
            append_scan_log(&self.log_path, &r);
            reports.push(r);
        }

        let mut s = self.inner.write();
        s.entries = by_id;
        drop(s);

        let report = ScanReport {
            entries: self.list(),
            providers: reports,
        };

        // Tell anyone who cares (the running-game tracker) that the
        // entry table refreshed, so they can rehydrate against the new
        // list. Emitting via the AppHandle keeps the dependency one-way:
        // the LibraryService never has to know about the tracker.
        if let Some(handle) = app {
            let _ = handle.emit("library:entries:changed", report.entries.len());
        }

        // Tell the frontend to refetch the library. LibraryContext listens
        // for this event so Home + Library auto-update after any scan, no
        // matter who triggered it (Settings, Onboarding, FileManager).
        if let Some(handle) = app {
            let _ = handle.emit("library:scan:done", report.entries.len());
        }

        report
    }

    /// Look up an entry by id (with overlay merged).
    pub fn get(&self, id: &str) -> Option<AppEntry> {
        let s = self.inner.read();
        let overlay = self.overlay.read();
        s.entries.get(id).map(|e| Self::merge_overlay(e, &overlay))
    }

    /// Toggle favorite, persist, return new value.
    pub fn toggle_favorite(&self, id: &str) -> AppResult<bool> {
        {
            let s = self.inner.read();
            if !s.entries.contains_key(id) {
                return Err(AppError::NotFound(format!("library: {id}")));
            }
        }
        let mut overlay = self.overlay.write();
        let entry = overlay.entry(id.to_string()).or_default();
        entry.favorite = !entry.favorite;
        let new = entry.favorite;
        let snapshot = overlay.clone();
        drop(overlay);
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
        self.launch_with_pid(id).map(|_| ())
    }

    /// Launch and return the spawned PID alongside the entry. For
    /// URL-style launches the PID is the launcher (Steam, Epic, …) and
    /// the running-game tracker resolves the actual game in its
    /// background loop. For direct exe launches the PID is the game.
    pub fn launch_with_pid(&self, id: &str) -> AppResult<(AppEntry, Option<u32>)> {
        let entry = self
            .get(id)
            .ok_or_else(|| AppError::NotFound(format!("library: {id}")))?;
        let pid = launcher::launch_capture(&entry)?;
        Ok((entry, pid))
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
        Box::new(xbox::XboxProvider::new(config.clone())),
        Box::new(epic::EpicProvider::new()),
        Box::new(gog::GogProvider::new()),
        Box::new(ea::EaProvider::new()),
        // User-curated entries from `library.manual.apps`. The provider
        // is registered unconditionally; once the config service starts
        // delivering structured lists, the entries will flow in here.
        Box::new(manual::ManualProvider::new(Vec::new())),
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

    /// Same shape as `launch` but also returns the spawned PID when we
    /// can capture one. URL / shell launches return `None` because the
    /// process we spawn is the launcher / shim, not the game itself —
    /// the running-game tracker resolves the actual PID asynchronously
    /// by walking sysinfo.
    pub fn launch_capture(entry: &AppEntry) -> AppResult<Option<u32>> {
        let cmd = &entry.launch_command;
        if is_launcher_url(cmd) {
            // Storefront URL handlers — we drop the launcher PID on the
            // floor on purpose. Killing the launcher doesn't kill the
            // game, and the launcher's PID is ephemeral (Steam often
            // re-execs itself after handling the URL).
            open_url(cmd)?;
            return Ok(None);
        }
        if cmd.starts_with("shell:") {
            open_shell_uri(cmd)?;
            return Ok(None);
        }

        let cwd = entry
            .exe_path
            .as_ref()
            .and_then(|p| p.parent().map(|p| p.to_path_buf()));

        let mut command = Command::new(cmd);
        if let Some(c) = cwd {
            command.current_dir(c);
        }
        let child = command
            .spawn()
            .map_err(|e| AppError::Other(format!("launch failed: {e}")))?;
        Ok(Some(child.id()))
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
            AppSource::Manual => "manual",
            AppSource::Folder => "folder",
        }
    }
}

// ── Scan progress plumbing ───────────────────────────────────────────

const SCAN_PROGRESS_EVENT: &str = "library:scan:progress";
const SCAN_LOG_MAX_BYTES: u64 = 1024 * 1024;
const SCAN_LOG_KEEP_BYTES: u64 = 100 * 1024;

fn emit_progress(app: Option<&AppHandle>, report: &ProviderReport) {
    if let Some(handle) = app {
        let _ = handle.emit(SCAN_PROGRESS_EVENT, report);
    }
}

/// Best-effort extraction of a human-readable message from a `catch_unwind`
/// payload. Falls back to a placeholder when the payload isn't a string.
fn panic_message(payload: Box<dyn std::any::Any + Send>) -> String {
    if let Some(s) = payload.downcast_ref::<&'static str>() {
        return (*s).to_string();
    }
    if let Some(s) = payload.downcast_ref::<String>() {
        return s.clone();
    }
    "panic with non-string payload".to_string()
}

/// Append one line per provider outcome to `scan_debug.log`. Keeps the file
/// from growing unbounded by truncating to the most recent ~100 KB once it
/// crosses ~1 MB. Failures are swallowed because logging is strictly
/// best-effort — we never want logging issues to mask scan output.
fn append_scan_log(path: &Path, report: &ProviderReport) {
    let line = format_log_line(report);
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    rotate_if_needed(path);
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        use std::io::Write;
        let _ = f.write_all(line.as_bytes());
    }
}

fn format_log_line(r: &ProviderReport) -> String {
    let state = match r.state {
        ProviderState::Scanning => "scanning",
        ProviderState::Done => "done",
        ProviderState::Unavailable => "unavailable",
        ProviderState::Error => "error",
    };
    let suffix = match &r.error {
        Some(e) => format!("  {e}"),
        None => String::new(),
    };
    format!(
        "{ts}  {provider:<12} {state:<12} {count:>3} entries   ({elapsed:>4}ms){suffix}\n",
        ts = iso_utc_now(),
        provider = r.provider,
        state = state,
        count = r.count,
        elapsed = r.elapsed_ms,
    )
}

fn rotate_if_needed(path: &Path) {
    let Ok(meta) = std::fs::metadata(path) else {
        return;
    };
    if meta.len() <= SCAN_LOG_MAX_BYTES {
        return;
    }
    // Read the trailing window, truncate, write it back. This is the
    // simplest rotation that avoids losing the most recent context — we
    // don't need a rolling-file scheme for a single-user diag log.
    let Ok(mut bytes) = std::fs::read(path) else {
        return;
    };
    let keep = SCAN_LOG_KEEP_BYTES as usize;
    if bytes.len() > keep {
        let drop = bytes.len() - keep;
        bytes.drain(..drop);
        // Skip the partial first line so we don't leave a torn entry.
        if let Some(nl) = bytes.iter().position(|&b| b == b'\n') {
            bytes.drain(..=nl);
        }
    }
    let _ = std::fs::write(path, bytes);
}

/// Format `SystemTime::now()` as `YYYY-MM-DDTHH:MM:SSZ` without pulling in
/// `chrono`. Uses Howard Hinnant's days-from-civil algorithm.
fn iso_utc_now() -> String {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let days = (secs / 86_400) as i64;
    let tod = (secs % 86_400) as u32;
    let hour = tod / 3600;
    let min = (tod % 3600) / 60;
    let sec = tod % 60;
    let (y, m, d) = civil_from_days(days);
    format!("{y:04}-{m:02}-{d:02}T{hour:02}:{min:02}:{sec:02}Z")
}

fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719_468;
    let z_floor = if z >= 0 { z } else { z - 146_096 };
    let era = z_floor / 146_097;
    let doe = (z - era * 146_097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = (yoe as i64) + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m_u64: u64 = if mp < 10 { mp + 3 } else { mp - 9 };
    let m = m_u64 as u32;
    let y = if m <= 2 { y + 1 } else { y };
    (y, m, d)
}
