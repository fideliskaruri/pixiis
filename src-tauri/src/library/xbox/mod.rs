//! Xbox / Microsoft Store / UWP library provider.
//!
//! Replaces the PowerShell sidecar in `src/pixiis/library/xbox.py:24-77`
//! with direct WinRT COM enumeration via the `windows` crate. The spike
//! at `spike/uwp-detect/` validated this path: 1.1 s vs 2.4 s warm,
//! 34 extra AUMIDs the PowerShell script's flow control silently dropped,
//! 0 field mismatches on common packages.
//!
//! Enumeration is hidden behind the `PackageEnumerator` trait so unit
//! tests can feed synthetic packages without a real `PackageManager`.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use serde_json::{Map, Value};

use super::Provider;
use crate::types::{AppEntry, AppSource};

mod manifest;
mod skip_list;

#[cfg(target_os = "windows")]
mod winrt;

#[cfg(target_os = "windows")]
pub use winrt::WinRtEnumerator;

/// Raw package shape produced by `PackageEnumerator`.
///
/// Mirrors the subset of `Windows.ApplicationModel.Package` we actually
/// read. `install_location` must point at the directory containing
/// `AppxManifest.xml` (and optionally `MicrosoftGame.Config`).
#[derive(Debug, Clone)]
pub struct RawPackage {
    pub package_name: String,
    pub family_name: String,
    pub display_name: String,
    pub install_location: PathBuf,
    pub is_framework: bool,
}

/// Abstraction over WinRT package enumeration so tests can swap in a
/// synthetic source on non-Windows hosts.
pub trait PackageEnumerator: Send + Sync {
    /// Enumerate all packages installed for the current user.
    fn enumerate(&self) -> Vec<RawPackage>;

    /// True when the underlying runtime / API is reachable.
    fn is_available(&self) -> bool;
}

pub struct XboxProvider {
    enumerator: Box<dyn PackageEnumerator>,
}

impl XboxProvider {
    /// Construct the provider with the platform-default enumerator
    /// (real `PackageManager` on Windows, an always-empty stub elsewhere).
    pub fn new() -> Self {
        #[cfg(target_os = "windows")]
        {
            Self { enumerator: Box::new(WinRtEnumerator::new()) }
        }
        #[cfg(not(target_os = "windows"))]
        {
            Self { enumerator: Box::new(NullEnumerator) }
        }
    }

    /// Test/DI hook — pass a `PackageEnumerator` directly.
    #[allow(dead_code)]
    pub fn with_enumerator(enumerator: Box<dyn PackageEnumerator>) -> Self {
        Self { enumerator }
    }
}

impl Default for XboxProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl Provider for XboxProvider {
    fn name(&self) -> &'static str {
        "xbox"
    }

    fn is_available(&self) -> bool {
        cfg!(target_os = "windows") && self.enumerator.is_available()
    }

    fn scan(&self) -> Vec<AppEntry> {
        scan_with(&*self.enumerator)
    }
}

/// Always-empty enumerator used on non-Windows targets so the provider
/// links cleanly without `cfg`-fencing the trait object.
#[cfg(not(target_os = "windows"))]
struct NullEnumerator;
#[cfg(not(target_os = "windows"))]
impl PackageEnumerator for NullEnumerator {
    fn enumerate(&self) -> Vec<RawPackage> {
        Vec::new()
    }
    fn is_available(&self) -> bool {
        false
    }
}

/// Pure-Rust scan loop — no Windows API, no I/O beyond reading the
/// manifest files referenced by `RawPackage::install_location`. This is
/// the function the unit tests exercise.
fn scan_with(enumerator: &dyn PackageEnumerator) -> Vec<AppEntry> {
    let mut out: Vec<AppEntry> = Vec::new();
    // Dedup by display name — matches xbox.py's `seen` set so a package
    // with multiple <Application> entries (e.g. MSTeams) collapses to one
    // library row, the first-resolved AUMID winning.
    let mut seen: HashSet<String> = HashSet::new();

    for pkg in enumerator.enumerate() {
        if pkg.is_framework {
            continue;
        }
        if skip_list::is_skipped(&pkg.package_name) {
            continue;
        }

        let display_name = pkg.display_name.trim().to_string();
        if display_name.is_empty()
            || display_name.contains("ms-resource")
            || display_name.contains("DisplayName")
        {
            continue;
        }

        let manifest_path = pkg.install_location.join("AppxManifest.xml");
        let Ok(manifest_xml) = std::fs::read_to_string(&manifest_path) else {
            continue;
        };
        let apps = match manifest::parse_manifest(&manifest_xml) {
            Ok(a) => a,
            Err(_) => continue,
        };
        if apps.is_empty() {
            continue;
        }

        let game_config_path = pkg.install_location.join("MicrosoftGame.Config");
        let is_game = game_config_path.is_file();
        let game_config_exe = if is_game {
            std::fs::read_to_string(&game_config_path)
                .ok()
                .and_then(|t| manifest::parse_microsoft_game_config(&t))
        } else {
            None
        };

        for app in apps {
            // Resolve exe — Game Pass titles store `GameLaunchHelper.exe`
            // in their manifest and the real exe in MicrosoftGame.Config.
            let mut exe = app.executable.clone().unwrap_or_default();
            if exe.is_empty() || exe.eq_ignore_ascii_case("GameLaunchHelper.exe") {
                match game_config_exe.as_ref() {
                    Some(g) => exe = g.clone(),
                    None => continue,
                }
            }

            let aumid = format!("{}!{}", pkg.family_name, app.id);
            let logo_full = app
                .logo
                .as_ref()
                .map(|rel| pkg.install_location.join(rel));
            let icon_path = logo_full.as_ref().and_then(|p| resolve_logo_path(p));

            let exe_candidate = pkg.install_location.join(&exe);
            let exe_path = if exe_candidate.is_file() {
                Some(exe_candidate)
            } else {
                None
            };

            if !seen.insert(display_name.clone()) {
                continue;
            }

            let mut metadata: Map<String, Value> = Map::new();
            metadata.insert("aumid".into(), Value::String(aumid.clone()));
            metadata.insert(
                "package_name".into(),
                Value::String(pkg.package_name.clone()),
            );
            metadata.insert("family".into(), Value::String(pkg.family_name.clone()));
            if let Some(l) = &logo_full {
                metadata.insert(
                    "logo".into(),
                    Value::String(l.to_string_lossy().into_owned()),
                );
            }
            metadata.insert("is_xbox_game".into(), Value::Bool(is_game));

            out.push(AppEntry {
                id: pkg.family_name.clone(),
                name: display_name.clone(),
                source: AppSource::Xbox,
                launch_command: format!("shell:appsFolder\\{aumid}"),
                exe_path,
                icon_path,
                art_url: None,
                metadata,
            });
        }
    }

    out
}

/// Try the literal manifest-relative logo path, then the standard
/// MRT scale variants (`*.scale-200.png` etc.). Returns `None` if no
/// concrete file exists — UI falls back to its own placeholder.
fn resolve_logo_path(p: &Path) -> Option<PathBuf> {
    if p.is_file() {
        return Some(p.to_path_buf());
    }
    let parent = p.parent()?;
    let stem = p.file_stem()?.to_str()?;
    let ext = p.extension().and_then(|e| e.to_str()).unwrap_or("");
    for scale in &["scale-200", "scale-100", "scale-150", "scale-400"] {
        let variant = if ext.is_empty() {
            format!("{stem}.{scale}")
        } else {
            format!("{stem}.{scale}.{ext}")
        };
        let cand = parent.join(variant);
        if cand.is_file() {
            return Some(cand);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    /// Synthetic enumerator fed by individual tests.
    struct MockEnumerator {
        packages: Vec<RawPackage>,
        available: bool,
    }
    impl PackageEnumerator for MockEnumerator {
        fn enumerate(&self) -> Vec<RawPackage> {
            self.packages.clone()
        }
        fn is_available(&self) -> bool {
            self.available
        }
    }

    /// Write a minimal AppxManifest.xml (single `<Application>`) into `dir`.
    fn write_simple_manifest(dir: &Path, app_id: &str, exe: &str, logo: &str) {
        let xml = format!(
            r#"<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10">
  <Applications>
    <Application Id="{app_id}" Executable="{exe}">
      <uap:VisualElements DisplayName="Test" Square150x150Logo="{logo}" />
    </Application>
  </Applications>
</Package>"#,
        );
        fs::write(dir.join("AppxManifest.xml"), xml).unwrap();
    }

    fn write_multi_app_manifest(dir: &Path) {
        let xml = r#"<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10">
  <Applications>
    <Application Id="App" Executable="MSTeams.exe">
      <uap:VisualElements Square150x150Logo="Assets\app.png" />
    </Application>
    <Application Id="Update" Executable="Update.exe">
      <uap:VisualElements Square150x150Logo="Assets\update.png" />
    </Application>
    <Application Id="Container" Executable="Container.exe">
      <uap:VisualElements Square150x150Logo="Assets\container.png" />
    </Application>
  </Applications>
</Package>"#;
        fs::write(dir.join("AppxManifest.xml"), xml).unwrap();
    }

    fn write_game_config(dir: &Path, exe: &str) {
        let xml = format!(
            r#"<?xml version="1.0" encoding="UTF-8"?>
<Game configVersion="1">
  <ExecutableList>
    <Executable Name="{exe}" Id="Game" />
  </ExecutableList>
</Game>"#,
        );
        fs::write(dir.join("MicrosoftGame.Config"), xml).unwrap();
    }

    #[test]
    fn skip_list_drops_system_packages() {
        // Each name is guaranteed by SKIP_PREFIXES.
        for name in &[
            "Microsoft.Windows.StartMenuExperienceHost",
            "Microsoft.UI.Xaml.2.8",
            "Microsoft.VCLibs.140.00",
            "Microsoft.NET.Native.Framework",
            "Microsoft.BioEnrollment",
            "Microsoft.AAD.BrokerPlugin",
            "Microsoft.SecHealthUI",
            "MicrosoftWindows.Client.CBS",
            "windows.immersivecontrolpanel",
            "Microsoft.WebpImageExtension",
            "InputApp",
            "Microsoft.LockApp",
        ] {
            assert!(
                skip_list::is_skipped(name),
                "expected `{name}` to be skipped by SKIP_PREFIXES",
            );
        }
        // Real apps must NOT be skipped.
        for name in &[
            "Microsoft.MinecraftUWP",
            "Microsoft.GamingApp",
            "78F8E0F2.ForzaHorizon5",
            "Mojang.Minecraft",
            "Microsoft.PowerToys",
        ] {
            assert!(
                !skip_list::is_skipped(name),
                "expected `{name}` NOT to be skipped",
            );
        }
    }

    #[test]
    fn framework_packages_are_excluded() {
        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "fake.exe", "Logo.png");
        let pkg = RawPackage {
            package_name: "Some.Library".into(),
            family_name: "Some.Library_x".into(),
            display_name: "Some Library".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: true,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert!(entries.is_empty(), "framework packages must be skipped");
    }

    #[test]
    fn unresolved_resource_display_names_are_dropped() {
        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "fake.exe", "Logo.png");
        let pkg = RawPackage {
            package_name: "Vendor.Thing".into(),
            family_name: "Vendor.Thing_y".into(),
            display_name: "ms-resource:DisplayName".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert!(entries.is_empty());
    }

    #[test]
    fn normal_package_emits_app_entry() {
        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "Calculator.exe", "Assets/Logo.png");
        // Make the exe + logo real files so resolve_logo_path + exe_path
        // return Some.
        fs::write(tmp.path().join("Calculator.exe"), b"MZ").unwrap();
        fs::create_dir_all(tmp.path().join("Assets")).unwrap();
        fs::write(tmp.path().join("Assets/Logo.png"), b"\x89PNG").unwrap();

        let pkg = RawPackage {
            // Anything starting with `Microsoft.Windows` is in the
            // skip-list by design (matches xbox.py:81); use a real
            // package name that lives outside it.
            package_name: "Microsoft.PowerToys".into(),
            family_name: "Microsoft.PowerToys_8wekyb3d8bbwe".into(),
            display_name: "Calculator".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert_eq!(entries.len(), 1);
        let e = &entries[0];
        assert_eq!(e.name, "Calculator");
        assert_eq!(e.id, "Microsoft.PowerToys_8wekyb3d8bbwe");
        assert!(matches!(e.source, AppSource::Xbox));
        assert_eq!(
            e.launch_command,
            "shell:appsFolder\\Microsoft.PowerToys_8wekyb3d8bbwe!App"
        );
        assert_eq!(
            e.metadata.get("aumid").and_then(Value::as_str),
            Some("Microsoft.PowerToys_8wekyb3d8bbwe!App"),
        );
        assert_eq!(
            e.metadata.get("is_xbox_game").and_then(Value::as_bool),
            Some(false),
        );
        assert!(e.exe_path.is_some());
        assert!(e.icon_path.is_some());
    }

    #[test]
    fn game_pass_pulls_exe_from_microsoft_game_config() {
        let tmp = TempDir::new().unwrap();
        // Manifest declares GameLaunchHelper.exe — real exe is in the
        // game config (matches xbox.py:38-44 and the spike's branch).
        write_simple_manifest(tmp.path(), "App", "GameLaunchHelper.exe", "Logo.png");
        write_game_config(tmp.path(), "ForzaHorizon5.exe");
        fs::write(tmp.path().join("ForzaHorizon5.exe"), b"MZ").unwrap();

        let pkg = RawPackage {
            package_name: "Microsoft.624F8B84B80_8wekyb3d8bbwe".into(),
            family_name: "Microsoft.624F8B84B80_8wekyb3d8bbwe".into(),
            display_name: "Forza Horizon 5".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert_eq!(entries.len(), 1);
        let e = &entries[0];
        assert_eq!(e.name, "Forza Horizon 5");
        assert_eq!(
            e.metadata.get("is_xbox_game").and_then(Value::as_bool),
            Some(true),
        );
        // exe_path should resolve to the real Forza exe, not the shim.
        let exe = e.exe_path.as_ref().unwrap();
        assert!(exe.ends_with("ForzaHorizon5.exe"));
    }

    #[test]
    fn multi_application_package_dedupes_by_display_name() {
        let tmp = TempDir::new().unwrap();
        write_multi_app_manifest(tmp.path());
        let pkg = RawPackage {
            package_name: "MSTeams".into(),
            family_name: "MSTeams_8wekyb3d8bbwe".into(),
            display_name: "Microsoft Teams".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        // Three <Application> entries → one row (matches xbox.py:143-145).
        assert_eq!(entries.len(), 1);
        // First app wins: id="App".
        assert!(entries[0]
            .launch_command
            .ends_with("MSTeams_8wekyb3d8bbwe!App"));
    }

    #[test]
    fn missing_exe_and_no_game_config_drops_entry() {
        let tmp = TempDir::new().unwrap();
        // Manifest has GameLaunchHelper.exe and no MicrosoftGame.Config.
        write_simple_manifest(tmp.path(), "App", "GameLaunchHelper.exe", "Logo.png");
        let pkg = RawPackage {
            package_name: "Vendor.NoExe".into(),
            family_name: "Vendor.NoExe_z".into(),
            display_name: "No Exe App".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert!(entries.is_empty(), "no resolvable exe → drop (xbox.py:42-44)");
    }

    #[test]
    fn missing_manifest_skips_package_silently() {
        let tmp = TempDir::new().unwrap();
        // No AppxManifest.xml written.
        let pkg = RawPackage {
            package_name: "Vendor.Broken".into(),
            family_name: "Vendor.Broken_z".into(),
            display_name: "Broken".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert!(entries.is_empty());
    }

    #[test]
    fn logo_resolves_through_scale_variants() {
        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "Game.exe", "Assets/Tile.png");
        fs::write(tmp.path().join("Game.exe"), b"MZ").unwrap();
        fs::create_dir_all(tmp.path().join("Assets")).unwrap();
        // Only the scale-200 variant exists, not the literal Tile.png.
        fs::write(tmp.path().join("Assets/Tile.scale-200.png"), b"\x89PNG").unwrap();

        let pkg = RawPackage {
            package_name: "Vendor.GameWithScales".into(),
            family_name: "Vendor.GameWithScales_z".into(),
            display_name: "Game With Scales".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert_eq!(entries.len(), 1);
        let icon = entries[0].icon_path.as_ref().unwrap();
        assert!(
            icon.ends_with("Tile.scale-200.png"),
            "expected scale variant fallback, got {icon:?}",
        );
    }
}
