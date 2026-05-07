//! EA App (formerly Origin) library provider — port of
//! `src/pixiis/library/ea.py`.
//!
//! Two paths:
//! 1. EA Desktop's `InstallData/*.json` manifests — the real source of
//!    truth, includes the `contentId` we need for the
//!    `origin2://game/launch?offerIds=…` URL.
//! 2. A best-effort scan of `C:/Program Files/EA Games/<folder>/*.exe`
//!    for installs not (yet) tracked by InstallData.
//!
//! Whichever runs first wins on duplicate ids.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use serde::Deserialize;
use serde_json::{Map, Value};

use super::Provider;
use crate::types::{AppEntry, AppSource};

const EA_INSTALL_DATA: &str = "C:/ProgramData/EA Desktop/InstallData";
const EA_GAMES_DIR: &str = "C:/Program Files/EA Games";
#[cfg(target_os = "windows")]
const EA_REG_KEY: &str = r"SOFTWARE\Electronic Arts";

const MIN_EXE_BYTES: u64 = 1_000_000;

pub struct EaProvider {
    install_data: PathBuf,
    games_dir: PathBuf,
}

impl EaProvider {
    pub fn new() -> Self {
        Self {
            install_data: PathBuf::from(EA_INSTALL_DATA),
            games_dir: PathBuf::from(EA_GAMES_DIR),
        }
    }

    #[cfg(test)]
    fn with_dirs(install_data: PathBuf, games_dir: PathBuf) -> Self {
        Self {
            install_data,
            games_dir,
        }
    }
}

impl Default for EaProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl Provider for EaProvider {
    fn name(&self) -> &'static str {
        "ea"
    }

    fn is_available(&self) -> bool {
        if !cfg!(target_os = "windows") {
            return false;
        }
        self.install_data.is_dir() || self.games_dir.is_dir() || ea_in_registry()
    }

    fn scan(&self) -> Vec<AppEntry> {
        let mut out = Vec::new();
        let mut seen: HashSet<String> = HashSet::new();

        for entry in scan_install_data(&self.install_data) {
            if seen.insert(entry.id.clone()) {
                out.push(entry);
            }
        }
        for entry in scan_games_dir(&self.games_dir) {
            if seen.insert(entry.id.clone()) {
                out.push(entry);
            }
        }
        out
    }
}

#[cfg(target_os = "windows")]
fn ea_in_registry() -> bool {
    use winreg::enums::HKEY_LOCAL_MACHINE;
    use winreg::RegKey;
    RegKey::predef(HKEY_LOCAL_MACHINE)
        .open_subkey(EA_REG_KEY)
        .is_ok()
}

#[cfg(not(target_os = "windows"))]
fn ea_in_registry() -> bool {
    false
}

#[derive(Deserialize, Default)]
struct EaInstallManifest {
    #[serde(default, rename = "displayName")]
    display_name: String,
    #[serde(default)]
    title: String,
    #[serde(default, rename = "contentId")]
    content_id: String,
    #[serde(default, rename = "softwareId")]
    software_id: String,
    #[serde(default, rename = "installLocation")]
    install_location: String,
    #[serde(default, rename = "baseInstallPath")]
    base_install_path: String,
}

fn scan_install_data(dir: &Path) -> Vec<AppEntry> {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for ent in rd.flatten() {
        let path = ent.path();
        let Some(ext) = path.extension().and_then(|s| s.to_str()) else {
            continue;
        };
        if !ext.eq_ignore_ascii_case("json") {
            continue;
        }
        if let Some(entry) = parse_install_manifest(&path) {
            out.push(entry);
        }
    }
    out
}

fn parse_install_manifest(path: &Path) -> Option<AppEntry> {
    let bytes = std::fs::read(path).ok()?;
    let m: EaInstallManifest = serde_json::from_slice(&bytes).ok()?;

    let display_name = if !m.display_name.is_empty() {
        m.display_name.trim().to_string()
    } else if !m.title.is_empty() {
        m.title.trim().to_string()
    } else {
        return None;
    };

    let content_id = if !m.content_id.is_empty() {
        m.content_id
    } else {
        m.software_id
    };

    let install_path = if !m.install_location.is_empty() {
        m.install_location
    } else {
        m.base_install_path
    };

    let exe_path = if !install_path.is_empty() {
        let p = PathBuf::from(&install_path);
        if p.is_dir() {
            Some(p)
        } else {
            None
        }
    } else {
        None
    };

    let entry_id = if !content_id.is_empty() {
        format!("ea:{content_id}")
    } else {
        format!("ea:{}", path.file_stem().and_then(|s| s.to_str()).unwrap_or(""))
    };

    let launch_command = if !content_id.is_empty() {
        format!("origin2://game/launch?offerIds={content_id}")
    } else {
        exe_path
            .as_ref()
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_default()
    };

    let mut metadata = Map::new();
    metadata.insert("content_id".into(), Value::String(content_id));

    Some(AppEntry {
        id: entry_id,
        name: display_name,
        source: AppSource::Ea,
        launch_command,
        exe_path,
        icon_path: None,
        art_url: None,
        metadata,
    })
}

fn scan_games_dir(dir: &Path) -> Vec<AppEntry> {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for folder_ent in rd.flatten() {
        let folder = folder_ent.path();
        let Ok(meta) = folder_ent.metadata() else {
            continue;
        };
        if !meta.is_dir() {
            continue;
        }
        let Some(folder_name) = folder.file_name().and_then(|s| s.to_str()) else {
            continue;
        };

        let mut exes = collect_exes(&folder, 1);
        if exes.is_empty() {
            exes = collect_exes(&folder, 2);
        }
        if exes.is_empty() {
            continue;
        }
        let main_exe = exes
            .into_iter()
            .max_by_key(|(_, size)| *size)
            .map(|(p, _)| p)
            .unwrap();

        let id = format!(
            "ea:{}",
            folder_name.to_lowercase().replace(' ', "_")
        );
        out.push(AppEntry {
            id,
            name: folder_name.to_string(),
            source: AppSource::Ea,
            launch_command: main_exe.to_string_lossy().into_owned(),
            exe_path: Some(main_exe),
            icon_path: None,
            art_url: None,
            metadata: Map::new(),
        });
    }
    out
}

fn collect_exes(root: &Path, depth: u32) -> Vec<(PathBuf, u64)> {
    let mut out = Vec::new();
    walk_for_exes(root, depth, &mut out);
    out
}

fn walk_for_exes(dir: &Path, depth_remaining: u32, out: &mut Vec<(PathBuf, u64)>) {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return;
    };
    for ent in rd.flatten() {
        let path = ent.path();
        let Ok(md) = ent.metadata() else { continue };
        if md.is_file() {
            if path
                .extension()
                .and_then(|s| s.to_str())
                .map(|s| s.eq_ignore_ascii_case("exe"))
                .unwrap_or(false)
                && md.len() >= MIN_EXE_BYTES
            {
                out.push((path, md.len()));
            }
        } else if md.is_dir() && depth_remaining > 1 {
            walk_for_exes(&path, depth_remaining - 1, out);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn write(dir: &Path, name: &str, contents: &str) {
        fs::write(dir.join(name), contents).unwrap();
    }

    #[test]
    fn install_data_parses_real_fixture() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/ea/InstallData/Apex.json");
        let entry = parse_install_manifest(&path).expect("fixture parses");
        assert_eq!(entry.id, "ea:Origin.OFR.50.0001234");
        assert_eq!(entry.name, "Apex Legends");
        assert!(matches!(entry.source, AppSource::Ea));
        assert_eq!(
            entry.launch_command,
            "origin2://game/launch?offerIds=Origin.OFR.50.0001234"
        );
        assert_eq!(
            entry.metadata.get("content_id").and_then(Value::as_str),
            Some("Origin.OFR.50.0001234")
        );
    }

    #[test]
    fn install_data_uses_title_when_display_name_missing() {
        let tmp = TempDir::new().unwrap();
        write(
            tmp.path(),
            "x.json",
            r#"{"title":"Sims 4","softwareId":"OFR.SIMS4"}"#,
        );
        let entries = scan_install_data(tmp.path());
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].name, "Sims 4");
        assert_eq!(entries[0].id, "ea:OFR.SIMS4");
        assert_eq!(
            entries[0].launch_command,
            "origin2://game/launch?offerIds=OFR.SIMS4"
        );
    }

    #[test]
    fn install_data_skips_when_no_name() {
        let tmp = TempDir::new().unwrap();
        write(tmp.path(), "x.json", r#"{"contentId":"x"}"#);
        assert!(scan_install_data(tmp.path()).is_empty());
    }

    #[test]
    fn install_data_falls_back_to_filename_when_no_id() {
        let tmp = TempDir::new().unwrap();
        write(
            tmp.path(),
            "battlefield_2042.json",
            r#"{"displayName":"Battlefield 2042"}"#,
        );
        let entries = scan_install_data(tmp.path());
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].id, "ea:battlefield_2042");
    }

    #[test]
    fn install_data_skips_non_json_files() {
        let tmp = TempDir::new().unwrap();
        write(tmp.path(), "readme.txt", "hi");
        assert!(scan_install_data(tmp.path()).is_empty());
    }

    #[test]
    fn games_dir_picks_largest_exe() {
        let tmp = TempDir::new().unwrap();
        let game = tmp.path().join("Mass Effect");
        fs::create_dir(&game).unwrap();
        // Two exes: small launcher + big main game. Largest must win.
        fs::write(game.join("launcher.exe"), vec![0u8; 2_000_000]).unwrap();
        fs::write(game.join("masseffect.exe"), vec![0u8; 8_000_000]).unwrap();

        let entries = scan_games_dir(tmp.path());
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].id, "ea:mass_effect");
        assert_eq!(entries[0].name, "Mass Effect");
        assert!(entries[0]
            .exe_path
            .as_ref()
            .unwrap()
            .file_name()
            .unwrap()
            .to_string_lossy()
            .ends_with("masseffect.exe"));
    }

    #[test]
    fn games_dir_finds_exe_one_level_deeper() {
        let tmp = TempDir::new().unwrap();
        let game = tmp.path().join("FIFA 24");
        let bin = game.join("Bin");
        fs::create_dir_all(&bin).unwrap();
        fs::write(bin.join("fifa24.exe"), vec![0u8; 5_000_000]).unwrap();

        let entries = scan_games_dir(tmp.path());
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].id, "ea:fifa_24");
    }

    #[test]
    fn unavailable_when_no_dirs() {
        let p = EaProvider::with_dirs(
            PathBuf::from("/nonexistent/ea/installdata"),
            PathBuf::from("/nonexistent/ea/games"),
        );
        assert!(!p.is_available());
        assert!(p.scan().is_empty());
    }

    #[test]
    fn dedupes_install_data_winning_over_games_dir() {
        // Two scanners can't share state in a tempdir-only test cleanly without
        // doctoring paths; we instead verify the merge logic on the EaProvider.
        let tmp_install = TempDir::new().unwrap();
        let tmp_games = TempDir::new().unwrap();
        write(
            tmp_install.path(),
            "x.json",
            r#"{"displayName":"Apex","contentId":"apex"}"#,
        );
        let game = tmp_games.path().join("Apex");
        fs::create_dir(&game).unwrap();
        fs::write(game.join("apex.exe"), vec![0u8; 2_000_000]).unwrap();

        let p = EaProvider::with_dirs(
            tmp_install.path().to_path_buf(),
            tmp_games.path().to_path_buf(),
        );
        let entries = p.scan();
        let ids: Vec<&str> = entries.iter().map(|e| e.id.as_str()).collect();
        assert!(ids.contains(&"ea:apex"));
        // Folder fallback is "ea:apex" too (lowercase folder name) — dedup keeps one.
        assert_eq!(ids.iter().filter(|i| **i == "ea:apex").count(), 1);
        // The InstallData entry wins (URL launch_command, not raw exe).
        let apex = entries.iter().find(|e| e.id == "ea:apex").unwrap();
        assert!(apex.launch_command.starts_with("origin2://"));
    }
}
