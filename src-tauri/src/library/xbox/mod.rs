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
use std::path::{Component, Path, PathBuf};
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

/// Family / package-name prefixes published by known game studios. The
/// list is curated — Wave 6 narrowed it from the original Wave 4 set
/// (which included the bare `Microsoft.Xbox` prefix that matched
/// `XboxIdentityProvider`, `XboxGameOverlay`, … infrastructure
/// packages, none of which are games).
///
/// Match is case-insensitive on the prefix; see [`matches_game_publisher`].
/// Source: `agents/wave6-uwp-research.md` § 4 — every entry is a
/// publisher or title that has shipped a UWP / MSIXVC game to the
/// Microsoft Store. **Bare `Microsoft.Xbox` is intentionally absent;**
/// rely on the more-specific `Microsoft.624F8B84B80` (Forza-style
/// hashed publisher IDs) and the title-specific `Microsoft.SeaofThieves`
/// / `Microsoft.MicrosoftFlightSimulator` / etc. entries instead.
const GAME_PUBLISHER_PREFIXES: &[&str] = &[
    // Microsoft first-party titles (NOT bare Microsoft.Xbox*)
    "Microsoft.MinecraftUWP",
    "Microsoft.Minecraft",
    "Microsoft.MicrosoftSolitaireCollection",
    "Microsoft.MicrosoftMahjong",
    "Microsoft.MicrosoftSudoku",
    "Microsoft.MicrosoftJackpot",
    "Microsoft.MicrosoftTreasureHunt",
    "Microsoft.MicrosoftBingo",
    "Microsoft.MicrosoftUltimateWordGames",
    "Microsoft.MicrosoftFlightSimulator",
    "Microsoft.Halo",
    "Microsoft.HaloMCC",
    "Microsoft.SeaofThieves",
    "Microsoft.Forza",
    "Microsoft.AgeofEmpires",
    "Microsoft.AgeOfEmpires",
    "Microsoft.Flight",
    "Microsoft.StateofDecay",
    "Microsoft.GearsOfWar",
    "Microsoft.Wasteland",
    // Hashed publisher IDs Microsoft uses for individual titles
    "Microsoft.624F8B84B80", // Forza Horizon 5
    // Microsoft Game Studios subsidiaries / first-party studios
    "ArkaneStudios.",
    "ArkaneAustin.",
    "DoubleFineProductions.",
    "TheCoalition.",
    "Compulsion.",
    "CompulsionGames.",
    "Inxile.",
    "InxileEntertainment.",
    "Ninja.",
    "NinjaTheory.",
    "PlaygroundGames.",
    "RareLimited.",
    "TurnTen.",
    "Turn10Studios.",
    "UndeadLabs.",
    "WorldsEdge.",
    "MachineGames.",
    "MojangStudios.",
    "Mojang.",
    "ObsidianEntertainment.",
    // Major third-party publishers
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
    "SonicTeam.",
    "BandaiNamco.",
    "BandaiNamcoEntertainment.",
    "BandaiNamcoEntertainmentEurope.",
    "NamcoBandai.",
    "Capcom.",
    "Activision.",
    "ActivisionPublishingInc.",
    "Blizzard.",
    "BlizzardEntertainment.",
    "RiotGames.",
    "ZeniMaxOnline.",
    "InnerSloth.",
    "FromSoftware.",
    "505Games.",
    "AsobimoInc.",
    "AspyrMediaInc.",
    "AtlusUSA.",
    "CDPROJEKTRED.",
    "CDProjektRED.",
    "CodeMasters.",
    "DeepSilver.",
    "Devolver.",
    "DevolverDigital.",
    "DotEmu.",
    "Frontier.",
    "FocusEntertainment.",
    "FocusHomeInteractive.",
    "GameloftSE.",
    "GearboxPublishing.",
    "HelloGames.",
    "IOInteractive.",
    "Konami.",
    "KonamiDigitalEntertainment.",
    "LarianStudios.",
    "LucasfilmGames.",
    "ModiphiusEntertainment.",
    "NaconStudio.",
    "Paradox.",
    "ParadoxInteractive.",
    "PrivateDivision.",
    "RebellionDevelopments.",
    "RemedyEntertainment.",
    "RockstarGames.",
    "Rovio.",
    "SCSSoftware.",
    "SonyInteractiveEntertainment.",
    "TeamCherry.",
    "TheGameKitchen.",
    "ThunderfulPublishing.",
    "TripwireInteractive.",
    "WaybackEntertainment.",
    "WizardsoftheCoast.",
    "WolverineStudios.",
    "WoWoWoGames.",
    "XSEEDGames.",
    "A2Z4DOLLC.",
];

/// Path component name (case-insensitive) that signals a Microsoft
/// Store / Game Pass game install root. Per
/// `agents/wave6-uwp-research.md` § 1.3, the GDK March 2022+ packaging
/// pipeline installs every Game Pass / Xbox PC title to
/// `[drive]:\XboxGames\<TitleName>\Content\` for content protection.
/// Presence of this component anywhere in the install path is a
/// high-confidence "this is a game" signal — false-positive rate is
/// effectively zero because the folder name is reserved by the Xbox
/// app and not used for non-game UWP installs.
const XBOX_GAMES_PATH_COMPONENT: &str = "XboxGames";

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
        // `_summary` (capabilities) is parsed but unused for the gaming
        // flag in Wave 6 — see comment on the inverted detection chain
        // below. Kept reachable so a future tiebreaker can resurrect it.
        let (apps, _summary) = match manifest::parse_manifest_full(&manifest_xml) {
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

        // Anti-signal: every <Application> entry in the manifest is
        // marked AppListEntry="none". The platform itself hides these
        // from the All Apps list — they're extension hosts / COM
        // brokers / companion services, not user-launchable. We honor
        // that even if a positive game signal would otherwise fire,
        // unless MicrosoftGame.Config is present (a real game with all
        // entries hidden is implausible, but the config file is
        // authoritative enough to override).
        // Ref: wave6-uwp-research.md § 1.6 / § 7 anti-signals.
        if !apps.is_empty()
            && apps.iter().all(|a| a.is_hidden())
            && !game_config_exists
        {
            continue;
        }

        // Wave 6 inverted detection chain — DEFAULT NO. Only flip to
        // game when at least one strict positive signal fires:
        //   1. MicrosoftGame.Config file at install root (GDK pipeline)
        //   2. install path contains an `XboxGames` component
        //      (Game Pass / Xbox PC default install root)
        //   3. family or package name matches the curated
        //      GAME_PUBLISHER_PREFIXES list
        // Anti-signals (skip-list, framework, AppListEntry="none")
        // already pre-empt above. The treat_all_as_games override
        // remains as the user-facing escape hatch for false negatives.
        // Dropped per wave6-{uwp-research,xbox-audit}.md:
        //   - has_significant_exe (matched every UWP with a real .exe
        //     — Spotify, Discord, Netflix, GitHub Desktop, …)
        //   - has_gaming_capability (matched non-game apps that
        //     integrate with Game Bar / capture infrastructure)
        let is_game = game_config_exists
            || installs_under_xbox_games(&pkg.install_location)
            || matches_game_publisher(&pkg.package_name, &pkg.family_name)
            || opts.treat_all_as_games;

        for app in apps {
            // Drop hidden child entries even if the package as a
            // whole is a game — `AppListEntry="none"` apps are not
            // user-launchable.
            if app.is_hidden() {
                continue;
            }
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

/// True when the package or family name starts with one of the known
/// game-publisher prefixes. Match is case-insensitive: package family
/// names are technically case-sensitive but the publisher tokens we
/// care about (`MojangStudios.*`, `BethesdaSoftworks.*`, …) are stable.
///
/// Wave 6 note: the bare `Microsoft.Xbox` prefix was REMOVED — it
/// matched system infrastructure (`Microsoft.XboxIdentityProvider`,
/// `Microsoft.XboxGameOverlay`, …) at much higher rate than real
/// Xbox-published titles, and Microsoft titles ship under hashed IDs
/// (`Microsoft.624F8B84B80`) or title-specific names instead.
fn matches_game_publisher(package_name: &str, family_name: &str) -> bool {
    let pn = package_name.to_ascii_lowercase();
    let fn_ = family_name.to_ascii_lowercase();
    GAME_PUBLISHER_PREFIXES.iter().any(|p| {
        let lp = p.to_ascii_lowercase();
        pn.starts_with(&lp) || fn_.starts_with(&lp)
    })
}

/// True when any path component of `install_location` equals
/// `XboxGames` (case-insensitive). Microsoft Store / Game Pass titles
/// install to `[drive]:\XboxGames\<TitleName>\Content\` from GDK March
/// 2022 onward. The folder name is reserved for game installs by the
/// Xbox app, so a package living under it is a Game Pass / Xbox PC
/// title with very high probability — false-positive rate < 0.5 %.
///
/// Pure path manipulation, no I/O.
///
/// We split on **both** `/` and `\` regardless of the host OS so that
/// (a) production WinRT-sourced paths (`C:\XboxGames\Halo\Content`)
/// match on Windows, and (b) tests cross-compiled on Linux still
/// recognise the same shape. `Path::components` on POSIX treats `\`
/// as a literal character inside a single component, which would
/// silently break the check on a non-Windows test host.
fn installs_under_xbox_games(install_location: &Path) -> bool {
    // Fast path for native components (drives, prefixes, separators).
    if install_location.components().any(|c| match c {
        Component::Normal(os) => os
            .to_str()
            .map(|s| s.eq_ignore_ascii_case(XBOX_GAMES_PATH_COMPONENT))
            .unwrap_or(false),
        _ => false,
    }) {
        return true;
    }
    // Fallback: split the lossy string form on both separators so a
    // Windows-shaped path read on POSIX (and vice versa) still matches.
    let s = install_location.to_string_lossy();
    s.split(|c| c == '\\' || c == '/')
        .any(|seg| seg.eq_ignore_ascii_case(XBOX_GAMES_PATH_COMPONENT))
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
        // Real apps / games must NOT be skipped.
        // Wave 6: `Microsoft.GamingApp` (Xbox storefront) is now in the
        // skip-list — it's a launcher, not a game; the user can still
        // launch it via Start Menu. See wave6-uwp-research.md § 4.4.
        for name in &[
            "Microsoft.MinecraftUWP",
            "78F8E0F2.ForzaHorizon5",
            "Mojang.Minecraft",
            "BethesdaSoftworks.Starfield",
            "KingDigitalEntertainment.CandyCrushSaga",
            "EAInc.EAappinstaller",
            "Microsoft.624F8B84B80",
            "Microsoft.MicrosoftSolitaireCollection",
            "MojangStudios.MinecraftUWP",
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
        // Non-publisher family, no MicrosoftGame.Config, install path
        // not under \XboxGames\. Wave 6 default-NO chain → entry
        // still surfaces in the library list with `is_xbox_game = false`,
        // but is filtered off the Home grid (which keys on is_game).
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
            "Wave 6 default-NO: no MicrosoftGame.Config + no XboxGames path + no publisher prefix → not a game",
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

    // ── Wave 6 inverted gaming heuristic ─────────────────────────────
    // Default-NO chain. Only flip to game on a strict positive:
    //   1. MicrosoftGame.Config
    //   2. install path under \XboxGames\
    //   3. curated GAME_PUBLISHER_PREFIXES match
    // Anti-signals: skip-list, framework flag, AppListEntry="none".

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

    fn write_manifest_with_app_list_entry(dir: &Path, entry: &str) {
        let xml = format!(
            r#"<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10">
  <Applications>
    <Application Id="App" Executable="App.exe">
      <uap:VisualElements AppListEntry="{entry}" Square150x150Logo="Logo.png" />
    </Application>
  </Applications>
</Package>"#,
        );
        fs::write(dir.join("AppxManifest.xml"), xml).unwrap();
    }

    /// Wave 6 regression test: bare `Microsoft.Xbox*` infrastructure
    /// packages (XboxGamingOverlay, XboxIdentityProvider, …) MUST NOT
    /// be classified as games. Pre-Wave-6 the `Microsoft.Xbox` family
    /// prefix matched them all — the user's complaint of "all xbox
    /// apps show up" is exactly this cluster. They're now skip-listed,
    /// so we exercise both ends: `is_skipped` + `matches_game_publisher`.
    #[test]
    fn xbox_infrastructure_packages_are_skipped() {
        for name in &[
            "Microsoft.XboxIdentityProvider",
            "Microsoft.XboxGameOverlay",
            "Microsoft.XboxGamingOverlay",
            "Microsoft.XboxSpeechToTextOverlay",
            "Microsoft.Xbox.TCUI",
            "Microsoft.XboxApp",
            "Microsoft.GamingApp",
            "Microsoft.GamingServices",
            "Microsoft.Bing",
            "Microsoft.BingNews",
            "Microsoft.BingWeather",
            "Microsoft.MicrosoftClipchamp",
            "Clipchamp.Clipchamp",
            "SpotifyAB.SpotifyMusic",
            "Discord.Discord",
            "4DF9E0F8.Netflix",
            "WhatsAppInc.WhatsAppDesktop",
            "GitHub.GitHubDesktop",
            "NVIDIACorp.NVIDIAControlPanel",
        ] {
            assert!(
                skip_list::is_skipped(name),
                "expected `{name}` to be in the skip-list (Wave 6 expansion)",
            );
        }
        // The family-prefix list MUST NOT match infrastructure either,
        // even if a future skip-list change accidentally drops them.
        for (pn, fname) in &[
            (
                "Microsoft.XboxIdentityProvider",
                "Microsoft.XboxIdentityProvider_8wekyb3d8bbwe",
            ),
            (
                "Microsoft.XboxGamingOverlay",
                "Microsoft.XboxGamingOverlay_8wekyb3d8bbwe",
            ),
            ("Microsoft.Xbox.TCUI", "Microsoft.Xbox.TCUI_8wekyb3d8bbwe"),
        ] {
            assert!(
                !matches_game_publisher(pn, fname),
                "publisher-prefix list must not match {pn} (would re-introduce Wave 4 bug)",
            );
        }
    }

    /// Capability-only signal MUST NOT flip the flag in Wave 6 — the
    /// chain is now positive-list. A package with `xboxAccessoryManagement`
    /// but no MicrosoftGame.Config, no XboxGames install path, and no
    /// publisher-prefix match falls through to "not a game".
    #[test]
    fn xbox_capability_alone_does_not_mark_as_game() {
        let tmp = TempDir::new().unwrap();
        write_manifest_with_capability(tmp.path(), "xboxAccessoryManagement");
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
            Some(false),
            "Wave 6: capability dropped from positive signals — package surfaces as non-game",
        );
    }

    #[test]
    fn known_publisher_prefix_marks_package_as_game() {
        // Mojang.* is in the curated publisher list — primary path
        // for older UWP titles that lack MicrosoftGame.Config.
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

    /// Forza-style hashed publisher ID — the family-name allowlist
    /// pattern recommended by `wave6-uwp-research.md` § 4.
    #[test]
    fn forza_hashed_publisher_id_marks_package_as_game() {
        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "ForzaHorizon5.exe", "Logo.png");
        fs::write(tmp.path().join("ForzaHorizon5.exe"), b"MZ").unwrap();
        let pkg = RawPackage {
            package_name: "Microsoft.624F8B84B80".into(),
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
        assert_eq!(
            entries[0]
                .metadata
                .get("is_xbox_game")
                .and_then(Value::as_bool),
            Some(true),
        );
    }

    /// Wave 6 regression: a package with a real .exe but no
    /// MicrosoftGame.Config, no XboxGames path, and no publisher-prefix
    /// match (the Spotify / Netflix / Discord shape) MUST NOT be
    /// classified as a game. Pre-Wave-6 the `has_significant_exe`
    /// heuristic flipped these to `is_xbox_game = true`; the user's
    /// complaint of "all xbox apps show up" is partially this cluster.
    #[test]
    fn third_party_uwp_with_real_exe_is_not_a_game() {
        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "ContosoRPG.exe", "Logo.png");
        fs::write(tmp.path().join("ContosoRPG.exe"), b"MZ").unwrap();
        let pkg = RawPackage {
            // NOT in skip-list, NOT in publisher-prefix list, NOT under
            // \XboxGames\, NO MicrosoftGame.Config — exactly the
            // Spotify / Discord / Netflix shape per audit § 1, table D.
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
            Some(false),
            "Wave 6: has_significant_exe dropped — non-launcher exe alone no longer a signal",
        );
    }

    /// Install path under `\XboxGames\` flips a package to a game
    /// even without MicrosoftGame.Config / publisher-prefix match.
    /// This catches Game Pass / Xbox PC titles whose package family
    /// uses a non-publisher hash that's not in our curated list.
    #[test]
    fn xbox_games_install_path_marks_package_as_game() {
        // Synthesize a path with a literal `XboxGames` component. We
        // don't write this to a real `C:\XboxGames\…` because tests
        // run on Linux/Mac; the manifest still has to load, so we use
        // a tempdir for the file content but inject the synthetic
        // `install_location` separately.
        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "Halo.exe", "Logo.png");
        fs::write(tmp.path().join("Halo.exe"), b"MZ").unwrap();

        // installs_under_xbox_games is path-only, so the path passed
        // to RawPackage just needs the component. We point it at a
        // subdirectory of tmp so the manifest read works on POSIX.
        let xbox_root = tmp.path().join("XboxGames").join("Halo").join("Content");
        fs::create_dir_all(&xbox_root).unwrap();
        write_simple_manifest(&xbox_root, "App", "Halo.exe", "Logo.png");
        fs::write(xbox_root.join("Halo.exe"), b"MZ").unwrap();

        let pkg = RawPackage {
            // Vendor name NOT in skip-list, NOT in publisher-prefix.
            package_name: "Vendor.RandomGameSku".into(),
            family_name: "Vendor.RandomGameSku_x".into(),
            display_name: "Some Game".into(),
            install_location: xbox_root.clone(),
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
            "install path under XboxGames is a strong positive signal on its own",
        );
    }

    /// MicrosoftGame.Config presence flips a package even when the
    /// publisher prefix and install path don't match. This is the
    /// strongest signal; preserved from Wave 4.
    #[test]
    fn microsoft_game_config_alone_marks_package_as_game() {
        let tmp = TempDir::new().unwrap();
        write_simple_manifest(tmp.path(), "App", "Game.exe", "Logo.png");
        fs::write(tmp.path().join("Game.exe"), b"MZ").unwrap();
        write_game_config(tmp.path(), "Game.exe");
        let pkg = RawPackage {
            // Vendor not in any list — the .config file alone carries it.
            package_name: "Vendor.Untracked".into(),
            family_name: "Vendor.Untracked_x".into(),
            display_name: "Untracked Game".into(),
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

    /// Anti-signal: AppListEntry="none" on every <Application> drops
    /// the entire package — the platform itself hides it from All
    /// Apps. Honored even when the family-name matches a game
    /// publisher (avoids surfacing an extension host that happens to
    /// share a family-name root with a real title).
    #[test]
    fn app_list_entry_none_drops_package() {
        let tmp = TempDir::new().unwrap();
        write_manifest_with_app_list_entry(tmp.path(), "none");
        fs::write(tmp.path().join("App.exe"), b"MZ").unwrap();
        let pkg = RawPackage {
            // In publisher-prefix list — but should still drop because
            // every <Application> is hidden and there's no game config.
            package_name: "Mojang.HiddenChild".into(),
            family_name: "Mojang.HiddenChild_x".into(),
            display_name: "Hidden Child".into(),
            install_location: tmp.path().to_path_buf(),
            is_framework: false,
        };
        let entries = scan_with(&MockEnumerator {
            packages: vec![pkg],
            available: true,
        });
        assert!(
            entries.is_empty(),
            "AppListEntry=\"none\" + no MicrosoftGame.Config → drop entirely",
        );
    }

    /// Bare `Microsoft.Xbox*` packages are NOT in the publisher
    /// prefix list anymore, so even if they somehow slip past the
    /// skip-list (e.g. a new XboxFooBar package Microsoft adds in
    /// 2026), they fall through to "not a game" by default.
    #[test]
    fn future_microsoft_xbox_infrastructure_does_not_match_publisher() {
        // Hypothetical not-yet-shipping package; not in skip-list, but
        // also must not be classified as a game by family-prefix alone.
        assert!(!matches_game_publisher(
            "Microsoft.XboxSomeFutureWidget",
            "Microsoft.XboxSomeFutureWidget_8wekyb3d8bbwe",
        ));
    }

    #[test]
    fn installs_under_xbox_games_helper_is_case_insensitive() {
        use std::path::PathBuf;
        assert!(installs_under_xbox_games(&PathBuf::from(
            "C:\\XboxGames\\Halo\\Content"
        )));
        assert!(installs_under_xbox_games(&PathBuf::from(
            "/mnt/d/xboxgames/halo/content"
        )));
        assert!(installs_under_xbox_games(&PathBuf::from(
            "D:\\XBOXGAMES\\Forza"
        )));
        assert!(!installs_under_xbox_games(&PathBuf::from(
            "C:\\Program Files\\WindowsApps\\Foo"
        )));
        // Substring match must NOT trigger — we want a full component.
        assert!(!installs_under_xbox_games(&PathBuf::from(
            "C:\\MyXboxGamesArchive\\Foo"
        )));
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
