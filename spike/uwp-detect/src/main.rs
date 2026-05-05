//! UWP / Microsoft Store / Xbox Game Pass detection via Windows Runtime COM.
//!
//! Replaces the PowerShell sidecar at `src/pixiis/library/xbox.py:24-77`.
//! Output JSON shape matches the Python contract verbatim so downstream
//! consumers don't change.

use std::path::{Path, PathBuf};
use std::time::Instant;

use anyhow::{anyhow, Context, Result};
use quick_xml::events::Event;
use quick_xml::Reader;
use serde::Serialize;

use windows::core::HSTRING;
use windows::ApplicationModel::Package;
use windows::Management::Deployment::PackageManager;
use windows::Win32::System::Com::{CoInitializeEx, COINIT_MULTITHREADED};

/// Mirrors `_SKIP_PREFIXES` in src/pixiis/library/xbox.py:81-103. Drift here
/// would make the spike's count diverge from PowerShell's downstream-filtered
/// count.
const SKIP_PREFIXES: &[&str] = &[
    "Microsoft.Windows",
    "Microsoft.UI.Xaml",
    "Microsoft.VCLibs",
    "Microsoft.NET.",
    "Microsoft.Services",
    "Microsoft.DirectX",
    "Microsoft.Advertising",
    "Microsoft.DesktopAppInstaller",
    "Microsoft.StorePurchaseApp",
    "Microsoft.VP9VideoExtensions",
    "Microsoft.WebMediaExtensions",
    "Microsoft.HEIFImageExtension",
    "Microsoft.WebpImageExtension",
    "Microsoft.RawImageExtension",
    "Microsoft.AV1VideoExtension",
    "Microsoft.HEVCVideoExtension",
    "MicrosoftWindows.",
    "windows.",
    "NcsiUwpApp",
    "Microsoft.ECApp",
    "Microsoft.LockApp",
    "Microsoft.AsyncTextService",
    "Microsoft.AccountsControl",
    "Microsoft.AAD.",
    "Microsoft.BioEnrollment",
    "Microsoft.CredDialogHost",
    "Microsoft.Win32WebViewHost",
    "InputApp",
    "MicrosoftCorporationII.QuickAssist",
    "Microsoft.SecHealthUI",
];

#[derive(Serialize, Debug)]
#[serde(rename_all = "PascalCase")]
struct AppRecord {
    name: String,
    #[serde(rename = "AUMID")]
    aumid: String,
    family: String,
    package_name: String,
    exe: String,
    logo: String,
    install_location: String,
    is_game: bool,
}

#[derive(Default, Debug)]
struct ManifestApp {
    id: String,
    executable: Option<String>,
    logo: Option<String>,
}

fn local_name_str<'a>(bytes: &'a [u8]) -> &'a str {
    std::str::from_utf8(bytes).unwrap_or("")
}

fn parse_manifest(install_dir: &Path) -> Result<Vec<ManifestApp>> {
    let manifest_path = install_dir.join("AppxManifest.xml");
    let xml = std::fs::read_to_string(&manifest_path)
        .with_context(|| format!("reading {}", manifest_path.display()))?;

    let mut reader = Reader::from_str(&xml);
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
                            "Executable" => {
                                if !val.is_empty() {
                                    app.executable = Some(val);
                                }
                            }
                            _ => {}
                        }
                    }
                    current = Some(app);
                } else if (name == "VisualElements" || name == "DefaultTile") && current.is_some() {
                    capture_logo(&e.attributes().flatten().collect::<Vec<_>>(), &mut current);
                }
            }
            Ok(Event::Empty(e)) => {
                let local = e.local_name();
                let name = local_name_str(local.as_ref());
                if name == "Application" {
                    // Self-closing <Application/> — rare but possible.
                    let mut app = ManifestApp::default();
                    for attr in e.attributes().flatten() {
                        let key_local = attr.key.local_name();
                        let key = local_name_str(key_local.as_ref());
                        let val = attr.unescape_value().unwrap_or_default().to_string();
                        match key {
                            "Id" => app.id = val,
                            "Executable" => {
                                if !val.is_empty() {
                                    app.executable = Some(val);
                                }
                            }
                            _ => {}
                        }
                    }
                    if !app.id.is_empty() {
                        apps.push(app);
                    }
                } else if (name == "VisualElements" || name == "DefaultTile") && current.is_some() {
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
            Err(e) => {
                return Err(anyhow!(
                    "xml parse error in {}: {e}",
                    manifest_path.display()
                ))
            }
            _ => {}
        }
        buf.clear();
    }

    Ok(apps)
}

fn capture_logo(attrs: &[quick_xml::events::attributes::Attribute], current: &mut Option<ManifestApp>) {
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

/// Read the first `<Executable Name="...">` from a MicrosoftGame.Config file.
/// Mirrors the PowerShell branch at xbox.py:38-44 — Game Pass titles use
/// GameLaunchHelper.exe in their manifest and store the real exe here.
fn parse_microsoft_game_config(path: &Path) -> Option<String> {
    let xml = std::fs::read_to_string(path).ok()?;
    let mut reader = Reader::from_str(&xml);
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
                } else if (name == "Executable") && in_executable_list {
                    if let Some(v) = read_name_attr(e.attributes()) {
                        return Some(v);
                    }
                }
            }
            Event::Empty(ref e) => {
                let local = e.local_name();
                let name = local_name_str(local.as_ref());
                if (name == "Executable") && in_executable_list {
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

fn process_package(pkg: &Package) -> Result<Vec<AppRecord>> {
    if pkg.IsFramework().unwrap_or(false) {
        return Ok(vec![]);
    }

    let id = pkg.Id()?;
    let pkg_name = id.Name()?.to_string();
    let family = id.FamilyName()?.to_string();

    if SKIP_PREFIXES.iter().any(|p| pkg_name.starts_with(p)) {
        return Ok(vec![]);
    }

    let install_loc = pkg.InstalledLocation()?;
    let install_path: String = install_loc.Path()?.to_string();
    let install_pathbuf = PathBuf::from(&install_path);

    let display_name = pkg.DisplayName().map(|s| s.to_string()).unwrap_or_default();
    if display_name.is_empty()
        || display_name.contains("ms-resource")
        || display_name.contains("DisplayName")
    {
        return Ok(vec![]);
    }

    let manifest_apps = match parse_manifest(&install_pathbuf) {
        Ok(a) => a,
        Err(_) => return Ok(vec![]),
    };

    let game_config_path = install_pathbuf.join("MicrosoftGame.Config");
    let is_game = game_config_path.exists();
    let game_config_exe = if is_game {
        parse_microsoft_game_config(&game_config_path)
    } else {
        None
    };

    let mut out = Vec::new();
    for app in manifest_apps {
        let mut exe = app.executable.clone().unwrap_or_default();
        if exe.is_empty() || exe.eq_ignore_ascii_case("GameLaunchHelper.exe") {
            match game_config_exe.as_ref() {
                Some(g) => exe = g.clone(),
                None => continue, // skip apps with no resolvable exe (matches xbox.py:42-44)
            }
        }

        let aumid = format!("{family}!{}", app.id);
        let logo_full = match app.logo {
            Some(rel) => install_pathbuf.join(&rel).to_string_lossy().to_string(),
            None => String::new(),
        };

        out.push(AppRecord {
            name: display_name.clone(),
            aumid,
            family: family.clone(),
            package_name: pkg_name.clone(),
            exe,
            logo: logo_full,
            install_location: install_path.clone(),
            is_game,
        });
    }

    Ok(out)
}

fn main() -> Result<()> {
    let t0 = Instant::now();

    // Multi-threaded apartment so WinRT factories (PackageManager) work without
    // marshaling overhead. Returns S_FALSE if already initialized — both OK.
    unsafe {
        let hr = CoInitializeEx(None, COINIT_MULTITHREADED);
        if hr.is_err() {
            hr.ok()?;
        }
    }

    let manager = PackageManager::new()?;
    let empty = HSTRING::new();
    let iter = manager.FindPackagesByUserSecurityId(&empty)?;

    let mut all = Vec::new();
    let mut errors = 0usize;
    for pkg in iter {
        match process_package(&pkg) {
            Ok(records) => all.extend(records),
            Err(_) => errors += 1,
        }
    }

    let elapsed = t0.elapsed();
    eprintln!(
        "uwp-detect: {} entries, {} package errors, {:?}",
        all.len(),
        errors,
        elapsed
    );

    println!("{}", serde_json::to_string_pretty(&all)?);
    Ok(())
}
