//! Running-game tracker.
//!
//! Records the spawn time + PID for every launched entry, then polls
//! `sysinfo::System::process_iter()` every five seconds to keep the live
//! list in sync with reality.
//!
//! Why a poller and not a child-process wait? Most storefront launches
//! go through a URL handler (`steam://`, `com.epicgames.launcher://`,
//! `shell:appsFolder\<AUMID>`) — the spawned child is the storefront
//! launcher, which forks the actual game and exits. We can't `wait()`
//! on a process we don't own. So we keep a list of "tracked" entries,
//! and on each tick we ask sysinfo whether any process matches the
//! entry's install dir (cmdline or cwd starts with `exe_path` parent).
//! When one is found we lock the PID in. When the PID later vanishes we
//! roll the elapsed time into the persisted overlay (playtime_minutes +
//! last_played) and drop the entry from the live list.
//!
//! The 30 s no-match grace window keeps the launcher-only case from
//! sticking forever in "Now Playing" — if Steam reports the game is
//! already running standalone (or the user closes the launcher before
//! the game starts), we just give up and prune.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime};

use parking_lot::RwLock;
use serde::Serialize;
use sysinfo::{Pid, ProcessRefreshKind, ProcessesToUpdate, System};
use tauri::{AppHandle, Emitter};
use ts_rs::TS;

use crate::error::{AppError, AppResult};
use crate::library::cache::{self, OverlayMap};
use crate::types::AppEntry;

/// Polling cadence for the background watcher. Five seconds is the floor
/// — the user-visible feedback is "the pill appears within ~10 s of a
/// Steam launch", which means at most two ticks.
const POLL_INTERVAL: Duration = Duration::from_secs(5);

/// How long we'll keep a tracked entry without matching a PID before
/// dropping it. URL-based launches (Steam etc.) typically attach within
/// 10–20 s; 30 s gives us comfortable headroom while still letting go
/// of "the launcher closed but we never saw the game" cases so the UI
/// stops showing a phantom Now-Playing pill.
const ATTACH_GRACE: Duration = Duration::from_secs(30);

/// Wire shape for the `library_running` command + the
/// `library:running:changed` event payload.
#[derive(Serialize, Clone, Debug, TS)]
#[ts(export, export_to = "../src/api/types/")]
pub struct RunningGame {
    pub id: String,
    pub name: String,
    /// Resolved PID of the actual game (NOT the launcher). Zero while we
    /// are still waiting to attach.
    pub pid: u32,
    /// Unix epoch seconds when we first started tracking the entry.
    /// Stored as `i64` server-side but serialised to a regular JS
    /// number — epoch seconds fit comfortably in 53 bits, so the
    /// bigint mapping ts-rs would otherwise emit is just noise here.
    #[ts(type = "number")]
    pub started_at: i64,
    /// True once we've attached to a real game process. Lets the UI
    /// distinguish "launching" from "running" if it wants to.
    pub attached: bool,
}

/// One tracked entry. Lives until the matched PID exits (or we give up
/// trying to attach inside `ATTACH_GRACE`).
struct Tracked {
    id: String,
    name: String,
    /// Install directory used to match a process. We compare this against
    /// every process's `cwd` and `cmd[0]` parent. `None` for entries with
    /// no known install path (Xbox/UWP fallback). For storefront entries
    /// the value is the directory containing the game exe.
    install_dir: Option<PathBuf>,
    /// Direct exe path when the launcher itself is the game (folder /
    /// manual / start-menu entries spawn the exe straight up).
    exe_path: Option<PathBuf>,
    /// Filled in once we've matched the game process.
    pid: Option<Pid>,
    /// When tracking began. Drives the playtime accumulator on stop.
    started: Instant,
    started_unix: i64,
}

#[derive(Default)]
struct State {
    /// Indexed by entry id so re-launching the same game doesn't double
    /// up rows in the live list.
    tracked: HashMap<String, Tracked>,
}

pub struct ProcessTracker {
    state: RwLock<State>,
    cache_path: PathBuf,
    /// Reference to the live overlay so playtime gets written through.
    /// Wrapped in Arc<RwLock> so the tracker and the LibraryService can
    /// both read/write without re-loading from disk.
    overlay: Arc<RwLock<OverlayMap>>,
}

impl ProcessTracker {
    pub fn new(cache_path: PathBuf, overlay: Arc<RwLock<OverlayMap>>) -> Self {
        Self {
            state: RwLock::new(State::default()),
            cache_path,
            overlay,
        }
    }

    /// Register a freshly-launched entry. `child_pid` is the PID of the
    /// process we directly spawned (when we own one) — for URL-style
    /// launches we leave it `None` and let the poller resolve it.
    pub fn track_launch(&self, entry: &AppEntry, child_pid: Option<u32>) {
        let exe_path = entry.exe_path.clone();
        let install_dir = exe_path.as_ref().and_then(|p| {
            // For storefront entries `exe_path` is the install dir; for
            // folder-spawned exes it's the binary itself. canonicalize is
            // not used — sysinfo cwd values often don't go through the
            // same long-path / 8.3 normalization as our scanned paths,
            // and we match with starts_with for that reason.
            if p.is_dir() {
                Some(p.clone())
            } else {
                p.parent().map(|q| q.to_path_buf())
            }
        });
        let started = Instant::now();
        let started_unix = unix_now();
        let pid = child_pid.map(Pid::from_u32);

        let mut s = self.state.write();
        s.tracked.insert(
            entry.id.clone(),
            Tracked {
                id: entry.id.clone(),
                name: entry.name.clone(),
                install_dir,
                exe_path,
                pid,
                started,
                started_unix,
            },
        );
    }

    /// Snapshot of the live list — used by the `library_running` command.
    pub fn list(&self) -> Vec<RunningGame> {
        let s = self.state.read();
        s.tracked
            .values()
            .map(|t| RunningGame {
                id: t.id.clone(),
                name: t.name.clone(),
                pid: t.pid.map(|p| p.as_u32()).unwrap_or(0),
                started_at: t.started_unix,
                attached: t.pid.is_some(),
            })
            .collect()
    }

    /// True iff we are actively tracking the given entry id.
    pub fn is_running(&self, id: &str) -> bool {
        self.state.read().tracked.contains_key(id)
    }

    /// Kill the tracked process for an entry id. The poller will pick up
    /// the exit on the next tick and roll the elapsed time into the
    /// overlay. We don't write playtime here so the close-vs-stop paths
    /// share a single accounting hook.
    pub fn stop(&self, id: &str) -> AppResult<()> {
        let pid_opt = {
            let s = self.state.read();
            s.tracked.get(id).and_then(|t| t.pid)
        };
        let pid = pid_opt.ok_or_else(|| {
            AppError::NotFound(format!(
                "library: {id} is not running (or no PID attached yet)"
            ))
        })?;
        let mut sys = System::new();
        sys.refresh_processes_specifics(
            ProcessesToUpdate::Some(&[pid]),
            ProcessRefreshKind::new(),
        );
        let proc = sys.process(pid).ok_or_else(|| {
            // Process disappeared between list and kill — treat as already
            // stopped. The poller will reconcile on the next tick.
            AppError::Other(format!(
                "library: process {} for {id} is no longer alive",
                pid.as_u32()
            ))
        })?;
        if !proc.kill() {
            return Err(AppError::Other(format!(
                "library: failed to terminate process {} for {id}",
                pid.as_u32()
            )));
        }
        Ok(())
    }

    /// One pass of the poller: refresh sysinfo, attach unmatched
    /// trackers, prune dead ones. Returns `true` if the live list
    /// changed (a tracker attached, attached pid died, or we gave up).
    pub fn tick(&self, sys: &mut System) -> bool {
        sys.refresh_processes_specifics(
            ProcessesToUpdate::All,
            ProcessRefreshKind::new(),
        );

        let mut changed = false;
        let mut to_finalize: Vec<(String, u64)> = Vec::new();

        let mut s = self.state.write();
        let now = Instant::now();

        // Pre-compute a small index of (pid, exe_path, cwd, cmd[0]) so the
        // O(N*M) match loop below stays cheap. sysinfo's process map is
        // already a HashMap so we just iterate; on a typical desktop M is
        // a few hundred and N is < 5 trackers.
        let mut snapshot: Vec<ProcSnap> = Vec::with_capacity(64);
        for (pid, p) in sys.processes() {
            snapshot.push(ProcSnap {
                pid: *pid,
                exe: p.exe().map(|p| p.to_path_buf()),
                cwd: p.cwd().map(|p| p.to_path_buf()),
                cmd0: p.cmd().first().map(|s| PathBuf::from(s.clone())),
                name: p.name().to_string_lossy().to_string(),
            });
        }

        for tracker in s.tracked.values_mut() {
            match tracker.pid {
                Some(pid) => {
                    // Already attached — has the PID died?
                    if sys.process(pid).is_none() {
                        let mins = elapsed_minutes(tracker.started, now);
                        to_finalize.push((tracker.id.clone(), mins));
                        changed = true;
                    }
                }
                None => {
                    // Try to attach. We accept the first process whose
                    // exe / cwd / cmdline points inside the tracked
                    // entry's install directory.
                    if let Some(found) = match_process(tracker, &snapshot) {
                        tracker.pid = Some(found);
                        changed = true;
                    } else if now.duration_since(tracker.started) > ATTACH_GRACE {
                        // Couldn't find the game. Drop it without
                        // accumulating playtime — we never saw it run.
                        to_finalize.push((tracker.id.clone(), 0));
                        changed = true;
                    }
                }
            }
        }

        if !to_finalize.is_empty() {
            // Pull dropped entries out of the live list.
            for (id, _) in &to_finalize {
                s.tracked.remove(id);
            }
            drop(s);

            // Account playtime + last_played for the ones that actually ran.
            self.finalize(&to_finalize);
        }

        changed
    }

    /// Roll elapsed minutes into the persisted overlay for each id.
    /// Skips entries with zero minutes (failed attaches) so the
    /// last_played timestamp doesn't drift on a phantom session.
    fn finalize(&self, finalized: &[(String, u64)]) {
        let mut overlay = self.overlay.write();
        let now_secs = unix_now() as u64;
        let mut wrote_anything = false;
        for (id, mins) in finalized {
            if *mins == 0 {
                continue;
            }
            let entry = overlay.entry(id.clone()).or_default();
            entry.playtime_minutes = entry.playtime_minutes.saturating_add(*mins);
            entry.last_played = now_secs;
            wrote_anything = true;
        }
        if wrote_anything {
            let snapshot = overlay.clone();
            drop(overlay);
            let _ = cache::save(&self.cache_path, &snapshot);
        }
    }

    /// On app start, walk the process list once and attach to any
    /// running games we already know about. Useful when Pixiis was
    /// killed/restarted while a game was running.
    pub fn rehydrate(&self, library: &[AppEntry]) {
        let mut sys = System::new();
        sys.refresh_processes_specifics(
            ProcessesToUpdate::All,
            ProcessRefreshKind::new(),
        );
        let snapshot: Vec<ProcSnap> = sys
            .processes()
            .iter()
            .map(|(pid, p)| ProcSnap {
                pid: *pid,
                exe: p.exe().map(|p| p.to_path_buf()),
                cwd: p.cwd().map(|p| p.to_path_buf()),
                cmd0: p.cmd().first().map(|s| PathBuf::from(s.clone())),
                name: p.name().to_string_lossy().to_string(),
            })
            .collect();

        for entry in library {
            if !entry.is_game() {
                continue;
            }
            let install_dir = entry.exe_path.as_ref().and_then(|p| {
                if p.is_dir() {
                    Some(p.clone())
                } else {
                    p.parent().map(|q| q.to_path_buf())
                }
            });
            // Skip entries with no install dir we can match against.
            if install_dir.is_none() && entry.exe_path.is_none() {
                continue;
            }
            let probe = Tracked {
                id: entry.id.clone(),
                name: entry.name.clone(),
                install_dir,
                exe_path: entry.exe_path.clone(),
                pid: None,
                started: Instant::now(),
                started_unix: unix_now(),
            };
            if let Some(found) = match_process(&probe, &snapshot) {
                let mut s = self.state.write();
                s.tracked.insert(
                    entry.id.clone(),
                    Tracked {
                        pid: Some(found),
                        ..probe
                    },
                );
            }
        }
    }
}

/// Spawn the polling task. Fires `library:running:changed` whenever the
/// live list mutates so the frontend can refresh without polling itself.
///
/// Uses `tauri::async_runtime::spawn` rather than `tokio::spawn` because
/// Tauri's `setup` callback runs synchronously on the main thread before
/// the async runtime is established for direct `tokio::spawn` use; we
/// have to go through Tauri's runtime handle. `spawn_blocking` inside
/// the task body is fine since by then we're on a tokio worker.
pub fn spawn_watcher(app: AppHandle, tracker: Arc<ProcessTracker>) {
    tauri::async_runtime::spawn(async move {
        let mut sys = System::new();
        let mut interval = tokio::time::interval(POLL_INTERVAL);
        loop {
            interval.tick().await;
            // Off-load the sysinfo refresh + match loop to the blocking
            // pool — `process_iter` does syscalls that aren't async.
            let tracker_for_tick = tracker.clone();
            let (sys_back, changed) = tauri::async_runtime::spawn_blocking(move || {
                let mut sys = sys;
                let changed = tracker_for_tick.tick(&mut sys);
                (sys, changed)
            })
            .await
            .unwrap_or_else(|_| (System::new(), false));
            sys = sys_back;
            if changed {
                let _ = app.emit("library:running:changed", tracker.list());
            }
        }
    });
}

struct ProcSnap {
    pid: Pid,
    exe: Option<PathBuf>,
    cwd: Option<PathBuf>,
    cmd0: Option<PathBuf>,
    name: String,
}

/// Heuristic: a process belongs to `tracker` iff its exe or cwd lives
/// under the tracker's install dir (storefront launches), or its exe
/// path equals the tracker's exe (direct launches).
fn match_process(tracker: &Tracked, snapshot: &[ProcSnap]) -> Option<Pid> {
    // Direct exe match wins — it disambiguates two games shipped from
    // the same publisher dir. We compare file_name() because the cwd
    // path may not equal the exe path verbatim.
    if let Some(exe) = &tracker.exe_path {
        if exe.is_file() {
            for p in snapshot {
                if let Some(p_exe) = &p.exe {
                    if path_eq(p_exe, exe) {
                        return Some(p.pid);
                    }
                }
            }
        }
    }

    // Install-dir match. Exclude obvious storefront launchers so a
    // matching `steam.exe` running out of the steam dir doesn't get
    // attributed to whichever Steam game we just launched. Same idea for
    // the Epic, GOG, and EA launchers.
    let dir = tracker.install_dir.as_ref()?;
    for p in snapshot {
        if is_launcher_process(&p.name) {
            continue;
        }
        if let Some(exe) = &p.exe {
            if path_starts_with(exe, dir) {
                return Some(p.pid);
            }
        }
        if let Some(cwd) = &p.cwd {
            if path_starts_with(cwd, dir) {
                return Some(p.pid);
            }
        }
        if let Some(cmd0) = &p.cmd0 {
            if path_starts_with(cmd0, dir) {
                return Some(p.pid);
            }
        }
    }
    None
}

fn is_launcher_process(name: &str) -> bool {
    let lower = name.to_ascii_lowercase();
    matches!(
        lower.as_str(),
        "steam.exe"
            | "steamwebhelper.exe"
            | "steamservice.exe"
            | "epicgameslauncher.exe"
            | "epicwebhelper.exe"
            | "galaxyclient.exe"
            | "galaxyclient helper.exe"
            | "easteamproxy.exe"
            | "ealauncher.exe"
            | "eadesktop.exe"
            | "origin.exe"
            | "originwebhelperservice.exe"
    )
}

/// Case-insensitive on Windows, exact elsewhere. We don't canonicalize
/// because sysinfo and our scanners can return different normalisations
/// (8.3 vs long-path) for the same file — `Path::starts_with` works with
/// component equality, which sidesteps that mismatch as long as the
/// prefix portion is the same length.
fn path_starts_with(needle: &Path, prefix: &Path) -> bool {
    #[cfg(target_os = "windows")]
    {
        let n = needle.to_string_lossy().to_ascii_lowercase();
        let p = prefix.to_string_lossy().to_ascii_lowercase();
        // Tolerate both forward and back slashes — sysinfo on Windows
        // sometimes hands back forward slashes for cwd values.
        let n = n.replace('/', "\\");
        let p = p.replace('/', "\\");
        n.starts_with(&p)
    }
    #[cfg(not(target_os = "windows"))]
    {
        needle.starts_with(prefix)
    }
}

fn path_eq(a: &Path, b: &Path) -> bool {
    #[cfg(target_os = "windows")]
    {
        a.to_string_lossy().to_ascii_lowercase()
            == b.to_string_lossy().to_ascii_lowercase()
    }
    #[cfg(not(target_os = "windows"))]
    {
        a == b
    }
}

fn unix_now() -> i64 {
    SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

fn elapsed_minutes(started: Instant, now: Instant) -> u64 {
    now.saturating_duration_since(started).as_secs() / 60
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn path_starts_with_matches_exact_dir() {
        let dir = PathBuf::from("/games/steamapps/common/Elden Ring");
        let exe = PathBuf::from("/games/steamapps/common/Elden Ring/eldenring.exe");
        assert!(path_starts_with(&exe, &dir));
    }

    #[test]
    fn path_starts_with_rejects_unrelated() {
        let dir = PathBuf::from("/games/steamapps/common/Elden Ring");
        let exe = PathBuf::from("/games/steamapps/common/Other Game/launcher.exe");
        assert!(!path_starts_with(&exe, &dir));
    }
}
