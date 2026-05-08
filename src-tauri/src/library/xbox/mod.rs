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
use std::sync::Arc;

use serde_json::{Map, Value};

use super::{ConfigLookup, EmptyConfig, Provider};
use crate::types::{AppEntry, AppSource};

mod manifest;
mod skip_list;

#[cfg(target_os = "windows")]
mod winrt;

#[cfg(target_os = "windows")]
pub use winrt::WinRtEnumerator;

/// File extensions the executable-presence heuristic accepts as "real"
/// game binaries. Excludes installers / updater / launcher shims.
const EXE_EXTENSIONS: &[&str] = &["exe"];

/// Lower-cased file-name fragments that look like a launcher / updater /
/// helper rather than the real game. If the only `.exe` we can find
/// matches one of these, the executable-presence heuristic does NOT fire.
const LAUNCHER_EXE_HINTS: &[&str] = &[
    "gamelaunchhelper",
    "launcher",
    "launch",
    "setup",
    "install",
    "update",
    "updater",
    "uninstall",
    "vc_redist",
    "vcredist",
    "directx",
    "dxsetup",
    "crashreport",
    "crashpad",
    "easyanticheat",
    "anticheat",
    "redistributable",
    "helper",
];

/// Lower-cased capability-name fragments that imply gaming. We match
/// case-insensitively because the manifest casing varies (`xboxLive` vs
/// `XboxLive` etc.) and we already lower-case capabilities at parse time.
const GAMING_CAPABILITY_HINTS: &[&str] = &[
    "xbox",
    "gamebarservices",
    "gameservices",
    "gamemonitor",
    "gameaccessory",
    "gamechat",
    "gamingdevice",
    "broadcastservices",
];

/// Family / package-name prefixes published by known game studios. The
/// list is conservative — we only add entries we've seen empirically
/// publishing UWP titles. Match is case-insensitive on the prefix.
const GAME_PUBLISHER_PREFIXES: &[&str] = &[
    "Microsoft.Xbox",
    "Microsoft.GamingApp",
    "Microsoft.MinecraftUWP",
    "Microsoft.Minecraft",
    "Microsoft.MicrosoftSolitaireCollection",
    "Microsoft.MicrosoftMahjong",
    "Microsoft.MicrosoftSudoku",
    "Microsoft.MicrosoftJackpot",
    "Microsoft.MicrosoftTreasureHunt",
    "Microsoft.MicrosoftBingo",
    "Microsoft.MicrosoftUltimateWordGames",
    "Microsoft.624F8B84B80",   // Forza Horizon 5
    "Microsoft.GameApps",
    "MojangStudios.",
    "Mojang.",
    "KingDigitalEntertainment.",
    "EAInc.",
    "ElectronicArts.",
    "TakeTwoInteractive.",
    "2K.",
    "2KGames.",
    "BethesdaSoftworks.",
    "BethesdaGameStudios.",
    "Ubisoft.",
    "UbisoftEntertainment.",
    "SquareEnix.",
    "Sega.",
    "SEGAofAmericaInc.",
    "BandaiNamco.",
    "BandaiNamcoEntertainment.",
    "Capcom.",
    "Activision.",
    "ActivisionPublishingInc.",
    "Blizzard.",
    "BlizzardEntertainment.",
    "RiotGames.",
    "ZeniMaxOnline.",
    "InnerSloth.",
    "ObsidianEntertainment.",
    "FromSoftware.",
];

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
    config: Arc<dyn ConfigLookup>,
}

impl XboxProvider {
    /// Construct the provider with the platform-default enumerator
    /// (real `PackageManager` on Windows, an always-empty stub elsewhere).
    pub fn new(config: Arc<dyn ConfigLookup>) -> Self {
        #[cfg(target_os = "windows")]
        {
            Self {
                enumerator: Box::new(WinRtEnumerator::new()),
                config,
            }
        }
        #[cfg(not(target_os = "windows"))]
        {
            Self {
                enumerator: Box::new(NullEnumerator),
                config,
            }
        }
    }

    /// Test/DI hook — pass a `PackageEnumerator` directly. Uses the
    /// no-op `EmptyConfig` so callers don't have to construct one.
    #[allow(dead_code)]
    pub fn with_enumerator(enumerator: Box<dyn PackageEnumerator>) -> Self {
        Self {
            enumerator,
            config: Arc::new(EmptyConfig),
        }
    }

    /// Test/DI hook — like [`Self::with_enumerator`] but lets the test
    /// pass a config lookup so it can exercise the
    /// `library.xbox.treat_all_as_games` override path.
    #[allow(dead_code)]
    pub fn with_enumerator_and_config(
        enumerator: Box<dyn PackageEnumerator>,
        config: Arc<dyn ConfigLookup>,
    ) -> Self {
        Self { enumerator, config }
    }
}

impl Default for XboxProvider {
    fn default() -> Self {
        Self::new(Arc::new(EmptyConfig))
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
        let opts = ScanOptions {
            treat_all_as_games: parse_bool(
                self.config.get_str("library.xbox.treat_all_as_games"),
            ),
        };
        scan_with_options(&*self.enumerator, opts)
    }
}

/// Scan-time switches sourced from `ConfigLookup`. Bundled into a
/// single struct so the test entry points (`scan_with` / `scan_with_options`)
/// don't grow new positional arguments every time we add a knob.
#[derive(Default, Debug, Clone, Copy)]
struct ScanOptions {
    /// `library.xbox.treat_all_as_games` — when true, every package
    /// that survived the skip-list / framework / display-name filters
    /// is reported with `is_xbox_game = true`. Last-resort override
    /// for users whose Game Pass titles still slip through the
    /// layered heuristic below.
    treat_all_as_games: bool,
}

/// Parse `"true"` / `"1"` / `"yes"` (case-insensitive) into `true`,
/// everything else into `false`. The config service stores booleans
/// as JSON natives, but the dotted-path `ConfigLookup` is `String`-shaped
/// — we accept the common stringified forms so users can hand-edit.
fn parse_bool(v: Option<String>) -> bool {
    match v {
        None => false,
        Some(s) => matches!(
            s.trim().to_ascii_lowercase().as_str(),
            "true" | "1" | "yes" | "on",
        ),
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

/// Test wrapper — runs the scan loop with default options. Production
/// flow goes through [`Provider::scan`] / [`scan_with_options`] so the
/// `library.xbox.treat_all_as_games` flag is honoured.
#[cfg(test)]
fn scan_with(enumerator: &dyn PackageEnumerator) -> Vec<AppEntry> {
    scan_with_options(enumerator, ScanOptions::default())
}

/// Pure-Rust scan loop — no Windows API, no I/O beyond reading the
/// manifest files referenced by `RawPackage::install_location`. This is
/// the function the unit tests exercise.
fn scan_with_options(
    enumerator: &dyn PackageEnumerator,
    opts: ScanOptions,
) -> Vec<AppEntry> {
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
        let (apps, summary) = match manifest::parse_manifest_full(&manifest_xml) {
            Ok(parsed) => parsed,
            Err(_) => continue,
        };
        if apps.is_empty() {
            continue;
        }

        let game_config_path = pkg.install_location.join("MicrosoftGame.Config");
        let game_config_exists = game_config_path.is_file();
        let game_config_exe = if game_config_exists {
            std::fs::read_to_string(&game_config_path)
                .ok()
                .and_then(|t| manifest::parse_microsoft_game_config(&t))
        } else {
            None
        };

        // Layered gaming heuristic — any one positive signal is enough.
        // Order matters only for the cheapness of the check (filesystem
        // scan is last because it's the most expensive). All four
        // signals are documented in `agents/wave3-xbox-fix.md`.
        let is_game = game_config_exists
            || has_gaming_capability(&summary)
            || matches_game_publisher(&pkg.package_name, &pkg.family_name)
            || has_significant_exe(&pkg.install_location)
            || opts.treat_all_as_games;

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

/// True when the manifest declared at least one capability whose
/// (already lower-cased) name contains a [`GAMING_CAPABILITY_HINTS`]
/// fragment. Substring match is intentional — `xboxLive`,
/// `xboxAccessoryManagement` and the dozen other Xbox-prefixed
/// capabilities all collapse to the same `xbox` hit.
fn has_gaming_capability(summary: &manifest::ManifestSummary) -> bool {
    summary
        .capabilities
        .iter()
        .any(|c| GAMING_CAPABILITY_HINTS.iter().any(|h| c.contains(h)))
}

/// True when the package or family name starts with one of the known
/// game-publisher prefixes. Match is case-insensitive: package family
/// names are technically case-sensitive but the publisher tokens we
/// care about (`Microsoft.Xbox*`, `MojangStudios.*`, …) are stable.
fn matches_game_publisher(package_name: &str, family_name: &str) -> bool {
    let pn = package_name.to_ascii_lowercase();
    let fn_ = family_name.to_ascii_lowercase();
    GAME_PUBLISHER_PREFIXES.iter().any(|p| {
        let lp = p.to_ascii_lowercase();
        pn.starts_with(&lp) || fn_.starts_with(&lp)
    })
}

/// Heuristic: does the install dir contain at least one `.exe` whose
/// file-name doesn't look like a launcher / updater / installer? Real
/// Xbox PC games ship a `*.exe` (or several); pure system / utility
/// UWP apps tend to ship only AppX-side activations and no native exe,
/// or only a launcher shim.
///
/// Walks at most ~64 entries one level deep to stay cheap on packages
/// whose install dir holds thousands of asset files.
fn has_significant_exe(install_dir: &Path) -> bool {
    let Ok(entries) = std::fs::read_dir(install_dir) else {
        return false;
    };
    for entry in entries.flatten().take(64) {
        let path = entry.path();
        let Some(ext) = path.extension().and_then(|e| e.to_str()) else {
            continue;
        };
        if !EXE_EXTENSIONS.iter().any(|e| ext.eq_ignore_ascii_case(e)) {
            continue;
        }
        let Some(stem) = path.file_stem().and_then(|s| s.to_str()) else {
            continue;
        };
        let lower = stem.to_ascii_lowercase();
        if LAUNCHER_EXE_HINTS.iter().any(|h| lower.contains(h)) {
            continue;
        }
        return true;
    }
    false
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
            // ── Wave 3: extended skip-list catches these UWP utilities
            // before the loosened gaming heuristic mis-classifies them.
            "Microsoft.MicrosoftEdge.Stable",
            "Microsoft.Office.Desktop",
            "Microsoft.OneDrive",
            "Microsoft.WindowsTerminal",
            "Microsoft.WindowsCalculator",
            "Microsoft.MicrosoftStickyNotes",
            "Microsoft.Photos",
            "Microsoft.PowerToys",
            "MSTeams",
            "Microsoft.VisualStudio.Code",
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
            "BethesdaSoftworks.Starfield",
            "KingDigitalEntertainment.CandyCrushSaga",
            "EAInc.EAappinstaller",
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
        // Launcher-shaped exe name + non-publisher package family, so
        // none of the layered gaming heuristics fire and the entry
        // still lands with `is_xbox_game = false`. This is the
        // canonical "UWP utility" shape — surfaces in the library list
        // but not on the Home grid.
        write_simple_manifest(tmp.path(), "App", "AppLauncher.exe", "Assets/Logo.png");
        fs::write(tmp.path().join("AppLauncher.exe"), b"MZ").unwrap();
        fs::create_dir_all(tmp.path().join("Assets")).unwrap();
        fs::write(tmp.path().join("Assets/Logo.png"), b"\x89PNG").unwrap();

        let pkg = RawPackage {
            // `Microsoft.Windows*` is in the skip-list; pick a name
            // outside that prefix and outside our publisher list.
            package_name: "ContosoUtility.AppX".into(),
            family_name: "ContosoUtility.AppX_8wekyb3d8bbwe".into(),
            display_name: "Contoso Utility".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert_eq!(entries.len(), 1);
        let e = &entries[0];
        assert_eq!(e.name, "Contoso Utility");
        assert_eq!(e.id, "ContosoUtility.AppX_8wekyb3d8bbwe");
        assert!(matches!(e.source, AppSource::Xbox));
        assert_eq!(
            e.launch_command,
            "shell:appsFolder\\ContosoUtility.AppX_8wekyb3d8bbwe!App"
        );
        assert_eq!(
            e.metadata.get("aumid").and_then(Value::as_str),
            Some("ContosoUtility.AppX_8wekyb3d8bbwe!App"),
        );
        assert_eq!(
            e.metadata.get("is_xbox_game").and_then(Value::as_bool),
            Some(false),
            "no MicrosoftGame.Config + no gaming capability + non-publisher name + only a launcher-shaped exe → not a game",
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
        // Pre-Wave-3 this test used `MSTeams`, which now lives in the
        // extended skip-list. Switch to a vendor name outside both the
        // skip-list and the publisher list so the dedup behaviour is
        // what's under test.
        let pkg = RawPackage {
            package_name: "Contoso.MultiApp".into(),
            family_name: "Contoso.MultiApp_8wekyb3d8bbwe".into(),
            display_name: "Contoso Multi App".into(),
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
            .ends_with("Contoso.MultiApp_8wekyb3d8bbwe!App"));
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

    // ── Layered gaming heuristic ─────────────────────────────────────

    /// Gaming capability declared in the manifest flips `is_xbox_game`
    /// to true even when there's no MicrosoftGame.Config — covers the
    /// Game Pass titles the spike found ship one but not the other.
    fn write_manifest_with_capability(dir: &Path, capability: &str) {
        let xml = format!(
            r#"<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities">
  <Applications>
    <Application Id="App" Executable="GameLauncher.exe">
      <uap:VisualElements Square150x150Logo="Logo.png" />
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="{capability}" />
  </Capabilities>
</Package>"#,
        );
        fs::write(dir.join("AppxManifest.xml"), xml).unwrap();
    }

    #[test]
    fn xbox_capability_marks_package_as_game() {
        let tmp = TempDir::new().unwrap();
        write_manifest_with_capability(tmp.path(), "xboxAccessoryManagement");
        // Launcher-shaped exe so has_significant_exe doesn't fire and
        // we know the *capability* is what flipped the flag.
        fs::write(tmp.path().join("GameLauncher.exe"), b"MZ").unwrap();
        let pkg = RawPackage {
            package_name: "ContosoStudios.SomeTitle".into(),
            family_name: "ContosoStudios.SomeTitle_x".into(),
            display_name: "Some Title".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert_eq!(entries.len(), 1);
        assert_eq!(
            entries[0]
                .metadata
                .get("is_xbox_game")
                .and_then(Value::as_bool),
            Some(true),
            "xboxAccessoryManagement capability is the gaming signal",
        );
    }

    #[test]
    fn known_publisher_prefix_marks_package_as_game() {
        // Mojang.Minecraft has no MicrosoftGame.Config in the wild and
        // doesn't always declare an Xbox capability; the publisher
        // prefix is what saves it.
        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "GameLauncher.exe", "Logo.png");
        fs::write(tmp.path().join("GameLauncher.exe"), b"MZ").unwrap();
        let pkg = RawPackage {
            package_name: "Mojang.MinecraftDungeons".into(),
            family_name: "Mojang.MinecraftDungeons_8wekyb3d8bbwe".into(),
            display_name: "Minecraft Dungeons".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert_eq!(entries.len(), 1);
        assert_eq!(
            entries[0]
                .metadata
                .get("is_xbox_game")
                .and_then(Value::as_bool),
            Some(true),
        );
    }

    #[test]
    fn significant_exe_marks_package_as_game() {
        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "ContosoRPG.exe", "Logo.png");
        fs::write(tmp.path().join("ContosoRPG.exe"), b"MZ").unwrap();
        let pkg = RawPackage {
            package_name: "Contoso.IndieGame".into(),
            family_name: "Contoso.IndieGame_x".into(),
            display_name: "Contoso RPG".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert_eq!(entries.len(), 1);
        assert_eq!(
            entries[0]
                .metadata
                .get("is_xbox_game")
                .and_then(Value::as_bool),
            Some(true),
            "non-launcher exe in install dir is enough on its own",
        );
    }

    #[test]
    fn launcher_only_install_dir_is_not_a_game() {
        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "Updater.exe", "Logo.png");
        fs::write(tmp.path().join("Updater.exe"), b"MZ").unwrap();
        fs::write(tmp.path().join("Setup.exe"), b"MZ").unwrap();
        let pkg = RawPackage {
            package_name: "Contoso.WindowsTool".into(),
            family_name: "Contoso.WindowsTool_x".into(),
            display_name: "Contoso Tool".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert_eq!(entries.len(), 1);
        assert_eq!(
            entries[0]
                .metadata
                .get("is_xbox_game")
                .and_then(Value::as_bool),
            Some(false),
            "only launcher-shaped exes → no significant-exe signal",
        );
    }

    /// `library.xbox.treat_all_as_games` flips every surviving package
    /// (skip-list / framework / display-name filters still run) into
    /// a game. Last-resort override.
    #[test]
    fn treat_all_as_games_override_flips_non_game_uwp() {
        struct YesConfig;
        impl ConfigLookup for YesConfig {
            fn get_str(&self, key: &str) -> Option<String> {
                if key == "library.xbox.treat_all_as_games" {
                    Some("true".into())
                } else {
                    None
                }
            }
        }

        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "AppLauncher.exe", "Logo.png");
        fs::write(tmp.path().join("AppLauncher.exe"), b"MZ").unwrap();

        let pkg = RawPackage {
            package_name: "Contoso.NotAGame".into(),
            family_name: "Contoso.NotAGame_x".into(),
            display_name: "Not A Game".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };

        let provider = XboxProvider::with_enumerator_and_config(
            Box::new(MockEnumerator {
                packages: vec![pkg],
                available: true,
            }),
            Arc::new(YesConfig),
        );
        let entries = provider.scan();
        assert_eq!(entries.len(), 1);
        assert_eq!(
            entries[0]
                .metadata
                .get("is_xbox_game")
                .and_then(Value::as_bool),
            Some(true),
            "override forces is_xbox_game=true regardless of heuristics",
        );
    }

    #[test]
    fn parse_bool_accepts_common_truthy_strings() {
        assert!(parse_bool(Some("true".into())));
        assert!(parse_bool(Some("TRUE".into())));
        assert!(parse_bool(Some(" yes ".into())));
        assert!(parse_bool(Some("1".into())));
        assert!(parse_bool(Some("on".into())));
        assert!(!parse_bool(None));
        assert!(!parse_bool(Some("false".into())));
        assert!(!parse_bool(Some("0".into())));
        assert!(!parse_bool(Some("nope".into())));
    }
}
