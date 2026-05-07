//! Epic Games Store library provider — port of `src/pixiis/library/epic.py`.
//!
//! Reads JSON manifests from
//! `C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests/*.item`. Each
//! manifest yields one `AppEntry` whose launch_command is the
//! `com.epicgames.launcher://apps/{AppName}?action=launch` URL the
//! Epic launcher already advertises.

use std::path::{Path, PathBuf};

use serde::Deserialize;
use serde_json::{Map, Value};

use super::Provider;
use crate::types::{AppEntry, AppSource};

const MANIFESTS_DIR: &str = "C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests";

pub struct EpicProvider {
    manifests_dir: PathBuf,
}

impl EpicProvider {
    pub fn new() -> Self {
        Self {
            manifests_dir: PathBuf::from(MANIFESTS_DIR),
        }
    }

    #[cfg(test)]
    fn with_dir(dir: PathBuf) -> Self {
        Self { manifests_dir: dir }
    }
}

impl Default for EpicProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl Provider for EpicProvider {
    fn name(&self) -> &'static str {
        "epic"
    }

    fn is_available(&self) -> bool {
        cfg!(target_os = "windows") && self.manifests_dir.is_dir()
    }

    fn scan(&self) -> Vec<AppEntry> {
        scan_dir(&self.manifests_dir)
    }
}

fn scan_dir(dir: &Path) -> Vec<AppEntry> {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for ent in rd.flatten() {
        let path = ent.path();
        let Some(ext) = path.extension().and_then(|s| s.to_str()) else {
            continue;
        };
        if !ext.eq_ignore_ascii_case("item") {
            continue;
        }
        if let Some(entry) = parse_manifest(&path) {
            out.push(entry);
        }
    }
    out
}

#[derive(Deserialize, Default)]
struct EpicManifest {
    #[serde(default, rename = "DisplayName")]
    display_name: String,
    #[serde(default, rename = "AppName")]
    app_name: String,
    #[serde(default, rename = "InstallLocation")]
    install_location: String,
    #[serde(default, rename = "LaunchExecutable")]
    launch_executable: String,
    #[serde(default, rename = "CatalogNamespace")]
    catalog_namespace: String,
}

fn parse_manifest(path: &Path) -> Option<AppEntry> {
    let bytes = std::fs::read(path).ok()?;
    let manifest: EpicManifest = serde_json::from_slice(&bytes).ok()?;

    let display_name = manifest.display_name.trim().to_string();
    if display_name.is_empty() || manifest.app_name.is_empty() {
        return None;
    }

    let exe_path = if !manifest.install_location.is_empty()
        && !manifest.launch_executable.is_empty()
    {
        Some(PathBuf::from(&manifest.install_location).join(&manifest.launch_executable))
    } else {
        None
    };

    let mut metadata = Map::new();
    metadata.insert("app_name".into(), Value::String(manifest.app_name.clone()));
    metadata.insert(
        "catalog_namespace".into(),
        Value::String(manifest.catalog_namespace),
    );

    Some(AppEntry {
        id: format!("epic:{}", manifest.app_name),
        name: display_name,
        source: AppSource::Epic,
        launch_command: format!(
            "com.epicgames.launcher://apps/{}?action=launch",
            manifest.app_name
        ),
        exe_path,
        icon_path: None,
        art_url: None,
        metadata,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn write_manifest(dir: &Path, name: &str, contents: &str) {
        fs::write(dir.join(name), contents).unwrap();
    }

    #[test]
    fn unavailable_when_dir_missing() {
        let p = EpicProvider::with_dir(PathBuf::from("/nonexistent/epic/manifests"));
        // is_available is gated by cfg!(windows), so on non-Windows it's false anyway.
        // The dir branch matters on Windows: confirm we don't panic and return false.
        assert!(!p.is_available());
        assert!(p.scan().is_empty());
    }

    #[test]
    fn parses_real_fixture() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/epic/Manifests/Fortnite.item");
        let entry = parse_manifest(&path).expect("fixture parses");
        assert_eq!(entry.id, "epic:Fortnite");
        assert_eq!(entry.name, "Fortnite");
        assert!(matches!(entry.source, AppSource::Epic));
        assert_eq!(
            entry.launch_command,
            "com.epicgames.launcher://apps/Fortnite?action=launch"
        );
        assert_eq!(
            entry.metadata.get("app_name").and_then(Value::as_str),
            Some("Fortnite")
        );
    }

    #[test]
    fn scan_dir_picks_only_item_files() {
        let tmp = TempDir::new().unwrap();
        write_manifest(
            tmp.path(),
            "good.item",
            r#"{"DisplayName":"Good Game","AppName":"GoodApp","InstallLocation":"C:/Games/Good","LaunchExecutable":"good.exe"}"#,
        );
        write_manifest(tmp.path(), "ignore.txt", "not a manifest");
        write_manifest(
            tmp.path(),
            "missing_name.item",
            r#"{"AppName":"NoDisplay"}"#,
        );

        let entries = scan_dir(tmp.path());
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].name, "Good Game");
        assert_eq!(entries[0].id, "epic:GoodApp");
    }

    #[test]
    fn skips_invalid_json() {
        let tmp = TempDir::new().unwrap();
        write_manifest(tmp.path(), "bad.item", "{not json");
        assert!(scan_dir(tmp.path()).is_empty());
    }

    #[test]
    fn exe_path_built_when_both_fields_present() {
        let tmp = TempDir::new().unwrap();
        write_manifest(
            tmp.path(),
            "x.item",
            r#"{"DisplayName":"X","AppName":"X","InstallLocation":"C:/Games/X","LaunchExecutable":"bin/x.exe"}"#,
        );
        let entries = scan_dir(tmp.path());
        let exe = entries[0].exe_path.as_ref().unwrap();
        assert!(exe.to_string_lossy().contains("bin"));
        assert!(exe.to_string_lossy().ends_with("x.exe"));
    }
}
