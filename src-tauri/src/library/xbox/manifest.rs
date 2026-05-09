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
    /// `<uap:VisualElements AppListEntry="...">` value when present.
    /// `Some("none")` (case-insensitive) means the app is hidden from
    /// the All Apps list — Microsoft itself doesn't want it in any
    /// launcher. Stored as the original-cased string for diagnostics;
    /// use [`Self::is_hidden`] for the comparison.
    pub app_list_entry: Option<String>,
}

impl ManifestApp {
    /// True when `<uap:VisualElements AppListEntry="none">` is set on
    /// this `<Application>`. The platform hides these from the All Apps
    /// list — they're extension hosts / COM brokers / companion services
    /// that aren't meant to be user-launchable. Wave 6 anti-signal: even
    /// if a positive game-detection signal fires, hidden apps stay out
    /// of the library.
    pub fn is_hidden(&self) -> bool {
        matches!(
            self.app_list_entry.as_deref().map(str::trim),
            Some(s) if s.eq_ignore_ascii_case("none")
        )
    }
}

/// Subset of the manifest the gaming heuristic cares about. Returned
/// alongside the per-`<Application>` rows so we don't re-walk the XML.
#[derive(Default, Debug, Clone, PartialEq, Eq)]
pub struct ManifestSummary {
    /// Names of every `<Capability>` / `<rescap:Capability>` /
    /// `<DeviceCapability>` declared in the manifest, lowercased.
    /// We only inspect the local-name (the prefix is stripped) so the
    /// caller can match against e.g. `gameservices` regardless of the
    /// `uap`, `rescap`, `iot`, … namespace it appears in.
    pub capabilities: Vec<String>,
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
/// Used by unit tests; production paths call [`parse_manifest_full`].
#[allow(dead_code)]
pub fn parse_manifest(xml: &str) -> Result<Vec<ManifestApp>, ParseError> {
    parse_manifest_full(xml).map(|(apps, _)| apps)
}

/// Like [`parse_manifest`] but also returns a [`ManifestSummary`] of
/// the package-level signals (capabilities, …) the gaming heuristic
/// in `mod.rs` consumes.
pub fn parse_manifest_full(
    xml: &str,
) -> Result<(Vec<ManifestApp>, ManifestSummary), ParseError> {
    let mut reader = Reader::from_str(xml);
    reader.trim_text(true);

    let mut apps: Vec<ManifestApp> = Vec::new();
    let mut current: Option<ManifestApp> = None;
    let mut summary = ManifestSummary::default();
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
                    let attrs = e.attributes().flatten().collect::<Vec<_>>();
                    capture_logo(&attrs, &mut current);
                    if name == "VisualElements" {
                        capture_app_list_entry(&attrs, &mut current);
                    }
                } else if name == "Capability"
                    || name == "DeviceCapability"
                    || name == "CustomCapability"
                {
                    if let Some(c) = read_name_attr(e.attributes()) {
                        summary.capabilities.push(c.to_lowercase());
                    }
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
                    let attrs = e.attributes().flatten().collect::<Vec<_>>();
                    capture_logo(&attrs, &mut current);
                    if name == "VisualElements" {
                        capture_app_list_entry(&attrs, &mut current);
                    }
                } else if name == "Capability"
                    || name == "DeviceCapability"
                    || name == "CustomCapability"
                {
                    if let Some(c) = read_name_attr(e.attributes()) {
                        summary.capabilities.push(c.to_lowercase());
                    }
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

    Ok((apps, summary))
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

/// Capture `<uap:VisualElements AppListEntry="...">` onto the current
/// `<Application>` if present. Per the [VisualElements schema][1] this
/// attribute is `default` (visible) or `none` (hidden from All Apps).
/// Wave 6 reads it as an anti-signal — see [`ManifestApp::is_hidden`].
///
/// [1]: https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/element-uap-visualelements
fn capture_app_list_entry(
    attrs: &[quick_xml::events::attributes::Attribute],
    current: &mut Option<ManifestApp>,
) {
    let Some(app) = current.as_mut() else { return };
    if app.app_list_entry.is_some() {
        return;
    }
    for attr in attrs {
        let key_local = attr.key.local_name();
        if local_name_str(key_local.as_ref()) == "AppListEntry" {
            let val = attr.unescape_value().unwrap_or_default().to_string();
            if !val.is_empty() {
                app.app_list_entry = Some(val);
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

    #[test]
    fn parses_app_list_entry_when_present() {
        // AppListEntry="none" is the platform's "hide from All Apps"
        // signal — UWP packages use it for extension hosts and COM
        // brokers. Wave 6 reads it as an anti-signal in the gaming
        // detection chain.
        let xml = r#"<?xml version="1.0"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10">
  <Applications>
    <Application Id="HiddenApp" Executable="Hidden.exe">
      <uap:VisualElements AppListEntry="none" Square150x150Logo="Logo.png" />
    </Application>
    <Application Id="NormalApp" Executable="Normal.exe">
      <uap:VisualElements Square150x150Logo="Logo.png" />
    </Application>
  </Applications>
</Package>"#;
        let apps = parse_manifest(xml).unwrap();
        assert_eq!(apps.len(), 2);
        assert_eq!(apps[0].app_list_entry.as_deref(), Some("none"));
        assert!(apps[0].is_hidden());
        assert_eq!(apps[1].app_list_entry, None);
        assert!(!apps[1].is_hidden());
    }

    #[test]
    fn app_list_entry_is_case_insensitive() {
        let app = ManifestApp {
            id: "X".into(),
            app_list_entry: Some("NONE".into()),
            ..Default::default()
        };
        assert!(app.is_hidden());
        let app = ManifestApp {
            id: "X".into(),
            app_list_entry: Some(" none ".into()),
            ..Default::default()
        };
        assert!(app.is_hidden());
        let app = ManifestApp {
            id: "X".into(),
            app_list_entry: Some("default".into()),
            ..Default::default()
        };
        assert!(!app.is_hidden());
    }

    #[test]
    fn manifest_summary_collects_capabilities_across_namespaces() {
        // Real-world Xbox / Game Pass manifests scatter gaming signals
        // across the `uap`, `rescap`, and `iot` namespaces. The walker
        // only inspects the local-name, so any of them lands in the
        // capability list lower-cased.
        let xml = r#"<?xml version="1.0"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities">
  <Applications>
    <Application Id="App" Executable="Game.exe">
      <uap:VisualElements Square150x150Logo="Logo.png" />
    </Application>
  </Applications>
  <Capabilities>
    <Capability Name="internetClient" />
    <rescap:Capability Name="xboxAccessoryManagement" />
    <DeviceCapability Name="microphone" />
    <Capability Name="gameBarServices" />
  </Capabilities>
</Package>"#;
        let (apps, summary) = parse_manifest_full(xml).unwrap();
        assert_eq!(apps.len(), 1);
        assert!(summary
            .capabilities
            .iter()
            .any(|c| c == "xboxaccessorymanagement"));
        assert!(summary.capabilities.iter().any(|c| c == "gamebarservices"));
        assert!(summary.capabilities.iter().any(|c| c == "microphone"));
    }
}
