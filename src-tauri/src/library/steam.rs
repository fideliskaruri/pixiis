//! Steam library provider — port of `src/pixiis/library/steam.py`.
//!
//! Detects Steam install via Windows registry (`HKLM\SOFTWARE\Wow6432Node\
//! Valve\Steam`), parses `steamapps/libraryfolders.vdf` for additional
//! library locations, then reads every `appmanifest_*.acf` to build
//! AppEntry rows.

use std::path::{Path, PathBuf};
use std::sync::Arc;

use serde_json::{Map, Value};

use super::{ConfigLookup, Provider};
use crate::types::{AppEntry, AppSource};

pub struct SteamProvider {
    config: Arc<dyn ConfigLookup>,
}

impl SteamProvider {
    pub fn new(config: Arc<dyn ConfigLookup>) -> Self {
        Self { config }
    }
}

impl Provider for SteamProvider {
    fn name(&self) -> &'static str {
        "steam"
    }

    fn is_available(&self) -> bool {
        cfg!(target_os = "windows") && find_steam_path(&*self.config).is_some()
    }

    fn scan(&self) -> Vec<AppEntry> {
        let Some(steam) = find_steam_path(&*self.config) else {
            return Vec::new();
        };
        let mut libs = parse_library_folders(&steam);
        let main_steamapps = steam.join("steamapps");
        if main_steamapps.is_dir() && !libs.contains(&main_steamapps) {
            libs.insert(0, main_steamapps);
        }
        let mut out = Vec::new();
        for lib in libs {
            scan_appmanifests(&lib, &mut out);
        }
        out
    }
}

fn find_steam_path(config: &dyn ConfigLookup) -> Option<PathBuf> {
    if let Some(over) = config.get_str("library.steam.install_path") {
        let p = PathBuf::from(over);
        if p.is_dir() {
            return Some(p);
        }
    }

    #[cfg(target_os = "windows")]
    {
        if let Some(p) = read_steam_registry() {
            return Some(p);
        }
    }

    for c in [
        "C:/Program Files (x86)/Steam",
        "C:/Program Files/Steam",
    ] {
        let p = PathBuf::from(c);
        if p.is_dir() {
            return Some(p);
        }
    }
    None
}

#[cfg(target_os = "windows")]
fn read_steam_registry() -> Option<PathBuf> {
    use winreg::enums::HKEY_LOCAL_MACHINE;
    use winreg::RegKey;

    let hklm = RegKey::predef(HKEY_LOCAL_MACHINE);
    let key = hklm
        .open_subkey(r"SOFTWARE\Wow6432Node\Valve\Steam")
        .or_else(|_| hklm.open_subkey(r"SOFTWARE\Valve\Steam"))
        .ok()?;
    let s: String = key.get_value("InstallPath").ok()?;
    let p = PathBuf::from(s);
    if p.is_dir() {
        Some(p)
    } else {
        None
    }
}

fn parse_library_folders(steam_path: &Path) -> Vec<PathBuf> {
    let vdf = steam_path.join("steamapps").join("libraryfolders.vdf");
    let Ok(text) = std::fs::read_to_string(&vdf) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    // VDF "key" "value" pairs are line-oriented in practice; this regex-free
    // walker is good enough for libraryfolders.vdf which uses one pair per
    // line (Valve's own writer normalises this).
    for line in text.lines() {
        let line = line.trim();
        if !line.starts_with("\"path\"") {
            continue;
        }
        // line is: "path"  "C:\\Path\\..."
        // splitn(3, '"') yields ["", "path", "  \"C:\\Path\\...\""].
        // The previous splitn(2, '"') only produced two pieces, so the
        // assignment to `rest` always ended up empty — which silently
        // dropped every additional Steam library folder. (#wave3-audit)
        let mut parts = line.splitn(3, '"');
        // skip the leading ""
        parts.next();
        // first " path"
        let _first = parts.next();
        let rest = parts.next().unwrap_or("");
        // rest is now: `  "C:\\Path\\..."`
        if let Some(start) = rest.find('"') {
            if let Some(end_off) = rest[start + 1..].find('"') {
                let raw = &rest[start + 1..start + 1 + end_off];
                let unescaped = raw.replace("\\\\", "\\");
                let p = PathBuf::from(unescaped).join("steamapps");
                if p.is_dir() {
                    out.push(p);
                }
            }
        }
    }
    out
}

fn scan_appmanifests(library_path: &Path, out: &mut Vec<AppEntry>) {
    let Ok(rd) = std::fs::read_dir(library_path) else {
        return;
    };
    for ent in rd.flatten() {
        let path = ent.path();
        let Some(name) = path.file_name().and_then(|s| s.to_str()) else {
            continue;
        };
        if !name.starts_with("appmanifest_") || !name.ends_with(".acf") {
            continue;
        }
        if let Some(entry) = parse_acf(&path, library_path) {
            out.push(entry);
        }
    }
}

fn parse_acf(acf_path: &Path, library_path: &Path) -> Option<AppEntry> {
    let text = std::fs::read_to_string(acf_path).ok()?;
    let appid = extract_quoted(&text, "appid")?;
    let name = extract_quoted(&text, "name")?;
    let installdir = extract_quoted(&text, "installdir");

    let exe_path = installdir.and_then(|d| {
        let p = library_path.join("common").join(d);
        if p.is_dir() {
            Some(p)
        } else {
            None
        }
    });

    let art_url = Some(format!(
        "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900_2x.jpg"
    ));

    let mut metadata = Map::new();
    metadata.insert("appid".into(), Value::String(appid.clone()));

    Some(AppEntry {
        id: appid.clone(),
        name,
        source: AppSource::Steam,
        launch_command: format!("steam://rungameid/{appid}"),
        exe_path,
        icon_path: None,
        art_url,
        metadata,
    })
}

/// Extract the value after a quoted key in VDF/ACF text. Looks for the
/// first occurrence of `"<key>"\s+"<value>"` and returns `<value>`.
fn extract_quoted(text: &str, key: &str) -> Option<String> {
    let needle = format!("\"{key}\"");
    let mut idx = 0;
    while let Some(pos) = text[idx..].find(&needle) {
        let abs = idx + pos + needle.len();
        let rest = &text[abs..];
        // Skip whitespace.
        let after = rest.trim_start();
        // After whitespace must come a quoted string.
        if let Some(stripped) = after.strip_prefix('"') {
            if let Some(end) = stripped.find('"') {
                return Some(stripped[..end].to_string());
            }
        }
        idx = abs;
    }
    None
}
