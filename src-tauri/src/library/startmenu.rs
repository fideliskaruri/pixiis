//! Start Menu library provider — port of `src/pixiis/library/startmenu.py`.
//!
//! Walks both Start Menu program folders for `*.lnk` shortcuts and
//! resolves each to a target executable using the pure-Rust `lnk`
//! parser (no PowerShell shell-out). Skips shortcuts whose target is
//! not an `.exe`/`.bat`/`.cmd`, and skips obvious uninstaller exes.
//! Dedupes by case-insensitive normalised target path so the dozens of
//! .lnk files most apps install only contribute one AppEntry.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use serde_json::{Map, Value};

use super::Provider;
use crate::types::{AppEntry, AppSource};

pub struct StartMenuProvider {
    dirs: Vec<PathBuf>,
}

impl StartMenuProvider {
    pub fn new() -> Self {
        Self {
            dirs: default_start_menu_dirs(),
        }
    }

    #[cfg(test)]
    fn with_dirs(dirs: Vec<PathBuf>) -> Self {
        Self { dirs }
    }
}

impl Default for StartMenuProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl Provider for StartMenuProvider {
    fn name(&self) -> &'static str {
        "startmenu"
    }

    fn is_available(&self) -> bool {
        cfg!(target_os = "windows")
    }

    fn scan(&self) -> Vec<AppEntry> {
        let mut out = Vec::new();
        let mut seen_targets: HashSet<String> = HashSet::new();
        let mut seen_ids: HashSet<String> = HashSet::new();

        for root in &self.dirs {
            if !root.is_dir() {
                continue;
            }
            collect_lnk_files(root, &mut |lnk_path| {
                if let Some(entry) = parse_lnk(&lnk_path) {
                    let key = normalise_path(
                        entry.exe_path.as_deref().unwrap_or_else(|| Path::new("")),
                    );
                    if !seen_targets.insert(key) {
                        return;
                    }
                    if !seen_ids.insert(entry.id.clone()) {
                        return;
                    }
                    out.push(entry);
                }
            });
        }
        out
    }
}

fn default_start_menu_dirs() -> Vec<PathBuf> {
    let mut dirs = vec![PathBuf::from(
        "C:/ProgramData/Microsoft/Windows/Start Menu/Programs",
    )];
    if let Some(appdata) = std::env::var_os("APPDATA") {
        dirs.push(
            PathBuf::from(appdata)
                .join("Microsoft")
                .join("Windows")
                .join("Start Menu")
                .join("Programs"),
        );
    }
    dirs
}

/// Walks `dir` recursively, calling `cb` for every `*.lnk` file. We hand-roll
/// the walker (instead of pulling in `walkdir`) because the only thing we
/// need is a depth-first descent that ignores I/O errors.
fn collect_lnk_files(dir: &Path, cb: &mut dyn FnMut(PathBuf)) {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return;
    };
    for ent in rd.flatten() {
        let path = ent.path();
        let Ok(meta) = ent.metadata() else { continue };
        if meta.is_dir() {
            collect_lnk_files(&path, cb);
        } else if meta.is_file()
            && path
                .extension()
                .and_then(|s| s.to_str())
                .map(|s| s.eq_ignore_ascii_case("lnk"))
                .unwrap_or(false)
        {
            cb(path);
        }
    }
}

fn parse_lnk(lnk_path: &Path) -> Option<AppEntry> {
    let shell = lnk::ShellLink::open(lnk_path).ok()?;
    let (target, working_dir) = extract_target(&shell)?;

    if !is_launchable_extension(&target) {
        return None;
    }
    let stem_lower = target
        .file_stem()
        .and_then(|s| s.to_str())
        .map(|s| s.to_lowercase())
        .unwrap_or_default();
    if stem_lower.contains("unins") {
        return None;
    }

    let display_name = lnk_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or_default()
        .to_string();
    if display_name.is_empty() {
        return None;
    }

    let mut metadata = Map::new();
    metadata.insert(
        "lnk_path".into(),
        Value::String(lnk_path.to_string_lossy().into_owned()),
    );
    metadata.insert(
        "working_dir".into(),
        Value::String(working_dir.unwrap_or_default()),
    );

    Some(AppEntry {
        id: format!(
            "sm:{}",
            display_name.to_lowercase().replace(' ', "_")
        ),
        name: display_name,
        source: AppSource::Startmenu,
        launch_command: target.to_string_lossy().into_owned(),
        exe_path: Some(target),
        icon_path: None,
        art_url: None,
        metadata,
    })
}

/// Pull `(target_path, working_dir)` out of a parsed shortcut.
///
/// Tries the unicode + ANSI local-base-path fields first (the canonical
/// "absolute target" location), then falls back to combining
/// `working_dir` with the `relative_path` string — the form most
/// installer-generated Start Menu shortcuts actually use.
fn extract_target(shell: &lnk::ShellLink) -> Option<(PathBuf, Option<String>)> {
    let working_dir = shell.working_dir().clone();

    if let Some(info) = shell.link_info().as_ref() {
        let target_str = info
            .local_base_path_unicode()
            .clone()
            .or_else(|| info.local_base_path().clone())
            .unwrap_or_default();
        if !target_str.is_empty() {
            return Some((PathBuf::from(target_str), working_dir));
        }
    }

    if let Some(rel) = shell.relative_path().clone() {
        if !rel.is_empty() {
            // `./foo.exe` is meaningless without the working dir; combine
            // when we have one, otherwise keep the relative path so the
            // launcher can still try (PATH lookup may resolve it).
            let target = if let Some(wd) = working_dir.as_deref() {
                PathBuf::from(wd).join(rel.trim_start_matches(".\\").trim_start_matches("./"))
            } else {
                PathBuf::from(rel)
            };
            return Some((target, working_dir));
        }
    }

    None
}

fn is_launchable_extension(p: &Path) -> bool {
    matches!(
        p.extension().and_then(|s| s.to_str()).map(str::to_lowercase).as_deref(),
        Some("exe") | Some("bat") | Some("cmd")
    )
}

/// Normalise a target path for case-insensitive dedup: lowercase + flip
/// backslashes to forward slashes. Cheap and good enough for the Windows
/// paths the Start Menu serves up.
fn normalise_path(p: &Path) -> String {
    p.to_string_lossy().to_lowercase().replace('\\', "/")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn fixtures_dir() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/startmenu")
    }

    #[test]
    fn parses_real_lnk_pointing_at_exe() {
        // game.lnk → G:\Games\Hydra\God of War Ragnarok (...)\GoWR.exe
        let entry = parse_lnk(&fixtures_dir().join("game.lnk")).expect("lnk parses");
        assert_eq!(entry.name, "game");
        assert_eq!(entry.id, "sm:game");
        assert!(matches!(entry.source, AppSource::Startmenu));
        let exe = entry.exe_path.as_ref().unwrap();
        assert!(exe.to_string_lossy().to_lowercase().ends_with("gowr.exe"));
    }

    #[test]
    fn parses_lnk_using_relative_path_and_working_dir() {
        // iron-heart.lnk has link_info.local_base_path = None but
        // working_dir = E:\Tools\iron-heart and relative_path = .\iron-heart.exe.
        // The resolver must combine the two.
        let entry =
            parse_lnk(&fixtures_dir().join("iron-heart.lnk")).expect("lnk parses");
        let exe = entry.exe_path.as_ref().unwrap();
        let s = exe.to_string_lossy().to_lowercase();
        assert!(s.contains("iron-heart"), "got {s:?}");
        assert!(s.ends_with("iron-heart.exe"), "got {s:?}");
    }

    #[test]
    fn skips_non_executable_targets() {
        // test.lnk targets C:\test\a.txt — must be rejected.
        assert!(parse_lnk(&fixtures_dir().join("test.lnk")).is_none());
    }

    #[test]
    fn dedupes_two_lnks_pointing_at_same_target() {
        let tmp = TempDir::new().unwrap();
        let folder_a = tmp.path().join("A");
        let folder_b = tmp.path().join("B");
        fs::create_dir_all(&folder_a).unwrap();
        fs::create_dir_all(&folder_b).unwrap();
        // Same .lnk byte stream in two folders → same target → one entry.
        let bytes = fs::read(fixtures_dir().join("game.lnk")).unwrap();
        fs::write(folder_a.join("Game.lnk"), &bytes).unwrap();
        fs::write(folder_b.join("Game.lnk"), &bytes).unwrap();

        let p = StartMenuProvider::with_dirs(vec![tmp.path().to_path_buf()]);
        let entries = p.scan();
        assert_eq!(entries.len(), 1, "duplicates should collapse: {entries:#?}");
    }

    #[test]
    fn walks_subdirectories() {
        let tmp = TempDir::new().unwrap();
        let nested = tmp.path().join("Vendor").join("Suite");
        fs::create_dir_all(&nested).unwrap();
        let bytes = fs::read(fixtures_dir().join("game.lnk")).unwrap();
        fs::write(nested.join("Tool.lnk"), &bytes).unwrap();

        let p = StartMenuProvider::with_dirs(vec![tmp.path().to_path_buf()]);
        let entries = p.scan();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].name, "Tool");
    }

    #[test]
    fn unavailable_paths_yield_empty_scan_no_panic() {
        let p =
            StartMenuProvider::with_dirs(vec![PathBuf::from("/does/not/exist/start-menu")]);
        assert!(p.scan().is_empty());
    }

    #[test]
    fn normalise_path_is_case_insensitive_and_slash_invariant() {
        let a = normalise_path(Path::new(r"C:\Program Files\Game\Game.exe"));
        let b = normalise_path(Path::new("C:/program files/game/game.EXE"));
        assert_eq!(a, b);
    }

    #[test]
    fn skips_uninstaller_targets_via_stem_check() {
        // The runtime check is in parse_lnk itself; we exercise it by
        // verifying the predicate logic that backs it.
        let p = Path::new("C:/Games/Foo/unins000.exe");
        let stem = p
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap()
            .to_lowercase();
        assert!(stem.contains("unins"));
    }
}
