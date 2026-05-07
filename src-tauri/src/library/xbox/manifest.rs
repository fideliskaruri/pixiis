//! AppxManifest.xml + MicrosoftGame.Config parsing.
//!
//! Lifted from `spike/uwp-detect/src/main.rs` (commit ffb5ac1). We use
//! `local_name()` everywhere so we don't have to care about the
//! `xmlns:uap=...` / `xmlns:rescap=...` prefixes the manifest schema
//! pins on `<VisualElements>`, `<DefaultTile>`, and friends.

use std::fmt;

use quick_xml::events::Event;
use quick_xml::Reader;

#[derive(Default, Debug, Clone, PartialEq, Eq)]
pub struct ManifestApp {
    pub id: String,
    pub executable: Option<String>,
    /// `Square150x150Logo` if present, otherwise `Logo`. Stored
    /// manifest-relative — the caller joins it with the install dir.
    pub logo: Option<String>,
}

#[derive(Debug)]
pub enum ParseError {
    Xml(String),
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ParseError::Xml(s) => write!(f, "xml parse error: {s}"),
        }
    }
}

impl std::error::Error for ParseError {}

fn local_name_str(bytes: &[u8]) -> &str {
    std::str::from_utf8(bytes).unwrap_or("")
}

/// Walk the manifest and return one `ManifestApp` per `<Application>`
/// element. Self-closing `<Application/>` is handled (rare but legal).
pub fn parse_manifest(xml: &str) -> Result<Vec<ManifestApp>, ParseError> {
    let mut reader = Reader::from_str(xml);
    reader.trim_text(true);

    let mut apps: Vec<ManifestApp> = Vec::new();
    let mut current: Option<ManifestApp> = None;
    let mut buf = Vec::new();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Eof) => break,
            Ok(Event::Start(e)) => {
                let local = e.local_name();
                let name = local_name_str(local.as_ref());
                if name == "Application" {
                    let mut app = ManifestApp::default();
                    for attr in e.attributes().flatten() {
                        let key_local = attr.key.local_name();
                        let key = local_name_str(key_local.as_ref());
                        let val = attr.unescape_value().unwrap_or_default().to_string();
                        match key {
                            "Id" => app.id = val,
                            "Executable" if !val.is_empty() => {
                                app.executable = Some(val);
                            }
                            _ => {}
                        }
                    }
                    current = Some(app);
                } else if (name == "VisualElements" || name == "DefaultTile")
                    && current.is_some()
                {
                    capture_logo(&e.attributes().flatten().collect::<Vec<_>>(), &mut current);
                }
            }
            Ok(Event::Empty(e)) => {
                let local = e.local_name();
                let name = local_name_str(local.as_ref());
                if name == "Application" {
                    let mut app = ManifestApp::default();
                    for attr in e.attributes().flatten() {
                        let key_local = attr.key.local_name();
                        let key = local_name_str(key_local.as_ref());
                        let val = attr.unescape_value().unwrap_or_default().to_string();
                        match key {
                            "Id" => app.id = val,
                            "Executable" if !val.is_empty() => {
                                app.executable = Some(val);
                            }
                            _ => {}
                        }
                    }
                    if !app.id.is_empty() {
                        apps.push(app);
                    }
                } else if (name == "VisualElements" || name == "DefaultTile")
                    && current.is_some()
                {
                    capture_logo(&e.attributes().flatten().collect::<Vec<_>>(), &mut current);
                }
            }
            Ok(Event::End(e)) => {
                let local = e.local_name();
                if local_name_str(local.as_ref()) == "Application" {
                    if let Some(app) = current.take() {
                        if !app.id.is_empty() {
                            apps.push(app);
                        }
                    }
                }
            }
            Err(e) => return Err(ParseError::Xml(e.to_string())),
            _ => {}
        }
        buf.clear();
    }

    Ok(apps)
}

fn capture_logo(
    attrs: &[quick_xml::events::attributes::Attribute],
    current: &mut Option<ManifestApp>,
) {
    let Some(app) = current.as_mut() else { return };
    if app.logo.is_some() {
        return;
    }
    for attr in attrs {
        let key_local = attr.key.local_name();
        let key = local_name_str(key_local.as_ref());
        if key == "Square150x150Logo" || key == "Logo" {
            let val = attr.unescape_value().unwrap_or_default().to_string();
            if !val.is_empty() {
                app.logo = Some(val);
                return;
            }
        }
    }
}

/// Read the first `<Executable Name="...">` from a MicrosoftGame.Config.
/// Mirrors the PowerShell branch at `xbox.py:38-44` — Game Pass titles
/// declare `GameLaunchHelper.exe` in their AppxManifest and store the
/// real exe here.
pub fn parse_microsoft_game_config(xml: &str) -> Option<String> {
    let mut reader = Reader::from_str(xml);
    reader.trim_text(true);
    let mut buf = Vec::new();
    let mut in_executable_list = false;

    loop {
        let evt = reader.read_event_into(&mut buf).ok()?;
        match evt {
            Event::Eof => return None,
            Event::Start(ref e) => {
                let local = e.local_name();
                let name = local_name_str(local.as_ref());
                if name == "ExecutableList" {
                    in_executable_list = true;
                } else if name == "Executable" && in_executable_list {
                    if let Some(v) = read_name_attr(e.attributes()) {
                        return Some(v);
                    }
                }
            }
            Event::Empty(ref e) => {
                let local = e.local_name();
                let name = local_name_str(local.as_ref());
                if name == "Executable" && in_executable_list {
                    if let Some(v) = read_name_attr(e.attributes()) {
                        return Some(v);
                    }
                }
            }
            Event::End(ref e) => {
                let local = e.local_name();
                if local_name_str(local.as_ref()) == "ExecutableList" {
                    in_executable_list = false;
                }
            }
            _ => {}
        }
        buf.clear();
    }
}

fn read_name_attr(attrs: quick_xml::events::attributes::Attributes) -> Option<String> {
    for attr in attrs.flatten() {
        let key_local = attr.key.local_name();
        if local_name_str(key_local.as_ref()) == "Name" {
            let v = attr.unescape_value().ok()?.to_string();
            if !v.is_empty() {
                return Some(v);
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_single_application_with_namespaced_visualelements() {
        let xml = r#"<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10">
  <Applications>
    <Application Id="App" Executable="Game.exe">
      <uap:VisualElements DisplayName="X" Square150x150Logo="Assets\Logo.png" />
    </Application>
  </Applications>
</Package>"#;
        let apps = parse_manifest(xml).unwrap();
        assert_eq!(apps.len(), 1);
        assert_eq!(apps[0].id, "App");
        assert_eq!(apps[0].executable.as_deref(), Some("Game.exe"));
        assert_eq!(apps[0].logo.as_deref(), Some("Assets\\Logo.png"));
    }

    #[test]
    fn iterates_each_application_in_multi_app_manifest() {
        // This is the PowerShell-bug case from the spike: PS auto-flattens
        // the .Application array and corrupts the loop. The Rust walker
        // must return one row per <Application>.
        let xml = r#"<?xml version="1.0"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10">
  <Applications>
    <Application Id="A" Executable="A.exe">
      <uap:VisualElements Square150x150Logo="A.png" />
    </Application>
    <Application Id="B" Executable="B.exe">
      <uap:VisualElements Square150x150Logo="B.png" />
    </Application>
    <Application Id="C" Executable="C.exe">
      <uap:VisualElements Square150x150Logo="C.png" />
    </Application>
  </Applications>
</Package>"#;
        let apps = parse_manifest(xml).unwrap();
        let ids: Vec<_> = apps.iter().map(|a| a.id.as_str()).collect();
        assert_eq!(ids, vec!["A", "B", "C"]);
    }

    #[test]
    fn falls_back_to_logo_attribute_when_square150_missing() {
        let xml = r#"<?xml version="1.0"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">
  <Applications>
    <Application Id="App" Executable="X.exe">
      <VisualElements Logo="Logo.png" />
    </Application>
  </Applications>
</Package>"#;
        let apps = parse_manifest(xml).unwrap();
        assert_eq!(apps[0].logo.as_deref(), Some("Logo.png"));
    }

    #[test]
    fn empty_executable_attribute_yields_none() {
        let xml = r#"<?xml version="1.0"?>
<Package>
  <Applications>
    <Application Id="App" Executable="" />
  </Applications>
</Package>"#;
        let apps = parse_manifest(xml).unwrap();
        assert_eq!(apps[0].executable, None);
    }

    #[test]
    fn microsoft_game_config_returns_first_executable_name() {
        let xml = r#"<?xml version="1.0"?>
<Game configVersion="1">
  <ExecutableList>
    <Executable Name="ForzaHorizon5.exe" Id="Game" />
    <Executable Name="ForzaHorizon5_Tools.exe" Id="Tools" />
  </ExecutableList>
</Game>"#;
        assert_eq!(
            parse_microsoft_game_config(xml).as_deref(),
            Some("ForzaHorizon5.exe"),
        );
    }

    #[test]
    fn microsoft_game_config_without_executable_list_returns_none() {
        let xml = r#"<?xml version="1.0"?><Game configVersion="1"/>"#;
        assert_eq!(parse_microsoft_game_config(xml), None);
    }
}
