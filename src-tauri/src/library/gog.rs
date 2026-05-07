//! GOG Galaxy library provider — port of `src/pixiis/library/gog.py`.
//!
//! Walks `HKLM\SOFTWARE\WOW6432Node\GOG.com\Games\<id>`, reads
//! `gameName`, `gameID`, `exe`, `path`, and produces one AppEntry per
//! installed game whose launch_command is the
//! `goggalaxy://openGameView/{game_id}` URL Galaxy already advertises.

use std::path::PathBuf;

use serde_json::{Map, Value};

use super::Provider;
use crate::types::{AppEntry, AppSource};

#[cfg(target_os = "windows")]
const GOG_REG_KEY: &str = r"SOFTWARE\WOW6432Node\GOG.com\Games";

pub struct GogProvider;

impl GogProvider {
    pub fn new() -> Self {
        Self
    }
}

impl Default for GogProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl Provider for GogProvider {
    fn name(&self) -> &'static str {
        "gog"
    }

    fn is_available(&self) -> bool {
        #[cfg(target_os = "windows")]
        {
            registry::root_exists()
        }
        #[cfg(not(target_os = "windows"))]
        {
            false
        }
    }

    fn scan(&self) -> Vec<AppEntry> {
        #[cfg(target_os = "windows")]
        {
            registry::scan_games()
                .into_iter()
                .filter_map(|f| build_entry(&f))
                .collect()
        }
        #[cfg(not(target_os = "windows"))]
        {
            Vec::new()
        }
    }
}

/// Raw fields read from a single GOG registry game key. Split out so the
/// AppEntry-building logic (and its tests) does not depend on the
/// Windows registry being present.
#[derive(Debug, Default, Clone)]
#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
pub(crate) struct GogGameFields {
    pub game_name: String,
    pub game_id: String,
    pub exe: String,
    pub install_path: String,
}

#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
pub(crate) fn build_entry(f: &GogGameFields) -> Option<AppEntry> {
    if f.game_name.trim().is_empty() || f.game_id.trim().is_empty() {
        return None;
    }

    let exe_path: Option<PathBuf> = if !f.exe.is_empty() {
        Some(PathBuf::from(&f.exe))
    } else if !f.install_path.is_empty() {
        Some(PathBuf::from(&f.install_path))
    } else {
        None
    };

    let mut metadata = Map::new();
    metadata.insert("game_id".into(), Value::String(f.game_id.clone()));

    Some(AppEntry {
        id: format!("gog:{}", f.game_id),
        name: f.game_name.trim().to_string(),
        source: AppSource::Gog,
        launch_command: format!("goggalaxy://openGameView/{}", f.game_id),
        exe_path,
        icon_path: None,
        art_url: None,
        metadata,
    })
}

#[cfg(target_os = "windows")]
mod registry {
    use super::{GogGameFields, GOG_REG_KEY};
    use winreg::enums::HKEY_LOCAL_MACHINE;
    use winreg::RegKey;

    pub fn root_exists() -> bool {
        let hklm = RegKey::predef(HKEY_LOCAL_MACHINE);
        hklm.open_subkey(GOG_REG_KEY).is_ok()
    }

    pub fn scan_games() -> Vec<GogGameFields> {
        let hklm = RegKey::predef(HKEY_LOCAL_MACHINE);
        let Ok(root) = hklm.open_subkey(GOG_REG_KEY) else {
            return Vec::new();
        };

        let mut out = Vec::new();
        for sub in root.enum_keys().flatten() {
            let Ok(key) = root.open_subkey(&sub) else {
                continue;
            };
            let fields = GogGameFields {
                game_name: read_string(&key, "gameName"),
                game_id: read_string(&key, "gameID"),
                exe: read_string(&key, "exe"),
                install_path: read_string(&key, "path"),
            };
            out.push(fields);
        }
        out
    }

    fn read_string(key: &RegKey, name: &str) -> String {
        key.get_value::<String, _>(name)
            .unwrap_or_default()
            .trim()
            .to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_entry_requires_name_and_id() {
        let f = GogGameFields {
            game_name: "".into(),
            game_id: "1207".into(),
            exe: "C:/Games/x.exe".into(),
            install_path: "".into(),
        };
        assert!(build_entry(&f).is_none());

        let f = GogGameFields {
            game_name: "Witcher".into(),
            game_id: "".into(),
            exe: "".into(),
            install_path: "".into(),
        };
        assert!(build_entry(&f).is_none());
    }

    #[test]
    fn build_entry_picks_exe_then_path() {
        let f = GogGameFields {
            game_name: "Witcher 3".into(),
            game_id: "1207664663".into(),
            exe: "C:/Games/Witcher3/witcher3.exe".into(),
            install_path: "C:/Games/Witcher3".into(),
        };
        let entry = build_entry(&f).unwrap();
        assert_eq!(entry.id, "gog:1207664663");
        assert_eq!(entry.name, "Witcher 3");
        assert!(matches!(entry.source, AppSource::Gog));
        assert_eq!(
            entry.launch_command,
            "goggalaxy://openGameView/1207664663"
        );
        assert_eq!(
            entry.exe_path.as_ref().unwrap().to_string_lossy(),
            "C:/Games/Witcher3/witcher3.exe"
        );
        assert_eq!(
            entry.metadata.get("game_id").and_then(Value::as_str),
            Some("1207664663")
        );
    }

    #[test]
    fn build_entry_falls_back_to_path_when_exe_empty() {
        let f = GogGameFields {
            game_name: "Stardew".into(),
            game_id: "1453375253".into(),
            exe: "".into(),
            install_path: "C:/GOG Games/Stardew Valley".into(),
        };
        let entry = build_entry(&f).unwrap();
        assert_eq!(
            entry.exe_path.as_ref().unwrap().to_string_lossy(),
            "C:/GOG Games/Stardew Valley"
        );
    }

    #[test]
    fn build_entry_trims_name_whitespace() {
        let f = GogGameFields {
            game_name: "  Cyberpunk 2077  ".into(),
            game_id: "1423049311".into(),
            exe: "".into(),
            install_path: "".into(),
        };
        let entry = build_entry(&f).unwrap();
        assert_eq!(entry.name, "Cyberpunk 2077");
        assert!(entry.exe_path.is_none());
    }

    #[test]
    fn provider_unavailable_offline_when_not_windows() {
        // Smoke: scan() must not panic when registry isn't there.
        let p = GogProvider::new();
        let _ = p.is_available();
        let _ = p.scan();
    }
}
