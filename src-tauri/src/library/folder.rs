//! Folder scanner — port of `src/pixiis/library/folder_scanner.py`.
//!
//! Catch-all for games that aren't owned by a storefront. Walks
//! `C:\Program Files`, `C:\Program Files (x86)`, every other drive's
//! well-known game directories, and any extra paths configured by the
//! user. Applies a skip-list for system folders + uninstaller exes,
//! and picks the largest exe per folder (preferring exes whose name
//! matches the folder name).

use std::path::{Path, PathBuf};

use serde_json::{Map, Value};

use super::Provider;
use crate::types::{AppEntry, AppSource};

const MIN_EXE_BYTES: u64 = 1_000_000;

const SKIP_DIRS: &[&str] = &[
    "windows", "system32", "syswow64", "winsxs", "microsoft",
    "common files", "windowsapps", "microsoft.net", "dotnet",
    "uninstall", "redist", "redistributable", "directx",
    "support", "driver", "drivers", "installer", "installers",
    "msbuild", "reference assemblies", "windows defender",
    "windows mail", "windows media player", "windows multimedia platform",
    "windows nt", "windows photo viewer", "windows portable devices",
    "windows security", "windows sidebar", "windowspowershell",
    "internet explorer", "microsoft office", "microsoft update",
    "pkg", "temp", "tmp", "cache", "logs", "backup",
    "$recycle.bin", "system volume information", "recovery",
    "perflogs", "intel", "nvidia", "nvidia corporation", "amd",
    "realtek", "dell", "hp", "lenovo", "asus",
];

const SKIP_EXES: &[&str] = &[
    "uninstall", "unins000", "unins001", "uninst", "uninstaller",
    "crashhandler", "crashreporter", "crashdump", "crashpad_handler",
    "vc_redist", "vcredist", "dxsetup", "dxwebsetup",
    "setup", "install", "installer", "updater", "update",
    "launcher", "bootstrapper", "prereq",
    "ue4prereqsetup_x64", "ue4prereqsetup",
    "dotnetfx", "ndp", "windowsdesktop-runtime",
];

/// Well-known game directory names under drive roots.
const GAME_DIR_NAMES: &[&str] = &["Games", "SteamLibrary", "GOG Games", "Epic Games"];

pub struct FolderProvider {
    extra_paths: Vec<PathBuf>,
}

impl FolderProvider {
    pub fn new(extra_paths: Vec<PathBuf>) -> Self {
        Self { extra_paths }
    }
}

impl Provider for FolderProvider {
    fn name(&self) -> &'static str {
        "folders"
    }

    fn is_available(&self) -> bool {
        cfg!(target_os = "windows")
    }

    fn scan(&self) -> Vec<AppEntry> {
        let roots = gather_scan_roots(&self.extra_paths);
        let mut out = Vec::new();
        let mut seen: std::collections::HashSet<String> = Default::default();

        for root in &roots {
            if !root.is_dir() {
                continue;
            }
            scan_directory(root, root, 2, &mut out, &mut seen);
        }
        out
    }
}

fn gather_scan_roots(extra: &[PathBuf]) -> Vec<PathBuf> {
    let mut roots: Vec<PathBuf> = Vec::new();
    roots.push(PathBuf::from("C:/Program Files"));
    roots.push(PathBuf::from("C:/Program Files (x86)"));

    // Drive letters B..Z (skip A floppy).
    for letter in b'B'..=b'Z' {
        let drive = format!("{}:/", letter as char);
        let dpath = PathBuf::from(&drive);
        if !dpath.exists() {
            continue;
        }
        for name in GAME_DIR_NAMES {
            let candidate = dpath.join(name);
            if candidate.is_dir() {
                roots.push(candidate);
            }
        }
    }

    for p in extra {
        if p.is_dir() {
            roots.push(p.clone());
        }
    }
    roots
}

fn scan_directory(
    scan_root: &Path,
    dir: &Path,
    depth_remaining: u32,
    out: &mut Vec<AppEntry>,
    seen: &mut std::collections::HashSet<String>,
) {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return;
    };
    let mut children: Vec<_> = rd.flatten().collect();
    children.sort_by_key(|d| d.file_name());

    for child in children {
        let child_path = child.path();
        let Ok(meta) = child.metadata() else { continue };
        if !meta.is_dir() {
            continue;
        }

        let Some(name) = child_path.file_name().and_then(|s| s.to_str()) else {
            continue;
        };
        let lower = name.to_lowercase();
        if SKIP_DIRS.contains(&lower.as_str()) {
            continue;
        }

        if let Some(main_exe) = find_main_exe(&child_path) {
            let exe_str = main_exe.to_string_lossy().to_lowercase();
            if seen.insert(exe_str) {
                let id = format!(
                    "folder:{}",
                    name.to_lowercase().replace(' ', "_")
                );
                let mut metadata = Map::new();
                metadata.insert(
                    "scan_root".into(),
                    Value::String(scan_root.to_string_lossy().into_owned()),
                );
                out.push(AppEntry {
                    id,
                    name: name.to_string(),
                    source: AppSource::Folder,
                    launch_command: main_exe.to_string_lossy().into_owned(),
                    exe_path: Some(main_exe),
                    icon_path: None,
                    art_url: None,
                    metadata,
                });
            }
        } else if depth_remaining > 1 {
            scan_directory(scan_root, &child_path, depth_remaining - 1, out, seen);
        }
    }
}

fn find_main_exe(folder: &Path) -> Option<PathBuf> {
    let rd = std::fs::read_dir(folder).ok()?;
    let mut sized: Vec<(PathBuf, u64)> = Vec::new();
    let folder_lower: String = folder
        .file_name()
        .and_then(|s| s.to_str())
        .map(|s| s.to_lowercase().replace(' ', ""))
        .unwrap_or_default();

    for ent in rd.flatten() {
        let path = ent.path();
        let Ok(md) = ent.metadata() else { continue };
        if !md.is_file() {
            continue;
        }
        let Some(name) = path.file_name().and_then(|s| s.to_str()) else {
            continue;
        };
        let lower = name.to_lowercase();
        if !lower.ends_with(".exe") {
            continue;
        }
        let stem = &lower[..lower.len() - 4];
        if SKIP_EXES.contains(&stem) {
            continue;
        }
        if matches_setup_prefix(stem) {
            continue;
        }
        let size = md.len();
        if size < MIN_EXE_BYTES {
            continue;
        }
        sized.push((path, size));
    }

    if sized.is_empty() {
        return None;
    }

    // Prefer exe whose stem matches the folder name (after lowercase + space-strip).
    for (p, _) in &sized {
        let stem = p
            .file_stem()
            .and_then(|s| s.to_str())
            .map(|s| s.to_lowercase().replace(' ', ""))
            .unwrap_or_default();
        if stem == folder_lower {
            return Some(p.clone());
        }
    }
    // Otherwise, the largest exe wins.
    sized.sort_by(|a, b| b.1.cmp(&a.1));
    Some(sized.remove(0).0)
}

/// Mirrors the Python `^(unins\d+|crash|vc_?redist|dxsetup|setup|install|update)`
/// regex without pulling in a regex crate.
fn matches_setup_prefix(stem: &str) -> bool {
    if stem.starts_with("unins") {
        return stem[5..].chars().next().map_or(false, |c| c.is_ascii_digit());
    }
    for prefix in &["crash", "vcredist", "vc_redist", "dxsetup", "setup", "install", "update"] {
        if stem.starts_with(prefix) {
            return true;
        }
    }
    false
}
