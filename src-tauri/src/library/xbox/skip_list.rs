//! Package-name prefix skip-list.
//!
//! Direct port of `_SKIP_PREFIXES` from `src/pixiis/library/xbox.py:81-103`.
//! Drift here makes the Rust scanner diverge from the Python contract on
//! the same machine, so changes should be deliberate and mirrored in the
//! Python file (or the Python file should be considered retired).
//!
//! New entries surfaced by the spike (`spike/uwp-detect/RESULTS.md`)
//! that the original PowerShell flow accidentally dropped via display-name
//! filtering — we drop them here on purpose so the Rust + PS outputs
//! stay equivalent on the dev machine.

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
    // ── Wave 3: broader Xbox heuristic catches these as "games" via
    // the has_significant_exe / capability paths, so block them
    // explicitly. All are Microsoft-shipped utilities, not titles.
    "Microsoft.MicrosoftEdge",
    "Microsoft.Edge",
    "MicrosoftEdge.",
    "Microsoft.Office.",
    "Microsoft.Office",
    "Microsoft.OneDrive",
    "Microsoft.OneNote",
    "Microsoft.Outlook",
    "Microsoft.Teams",
    "MSTeams",
    "MicrosoftTeams",
    "Microsoft.Skype",
    "Microsoft.MSPaint",
    "Microsoft.Paint",
    "Microsoft.WindowsTerminal",
    "Microsoft.PowerShell",
    "Microsoft.WindowsCalculator",
    "Microsoft.WindowsAlarms",
    "Microsoft.WindowsCamera",
    "Microsoft.WindowsFeedbackHub",
    "Microsoft.WindowsMaps",
    "Microsoft.WindowsNotepad",
    "Microsoft.WindowsSoundRecorder",
    "Microsoft.WindowsStore",
    "Microsoft.StorePurchase",
    "Microsoft.Photos",
    "Microsoft.MicrosoftStickyNotes",
    "Microsoft.MicrosoftOfficeHub",
    "Microsoft.GetHelp",
    "Microsoft.Getstarted",
    "Microsoft.People",
    "Microsoft.MixedReality",
    "Microsoft.YourPhone",
    "Microsoft.WidgetsPlatformRuntime",
    "Microsoft.ZuneMusic",
    "Microsoft.ZuneVideo",
    "Microsoft.MoCamera",
    "Microsoft.PowerAutomate",
    "Microsoft.Whiteboard",
    "Microsoft.Todos",
    "Microsoft.ScreenSketch",
    "Microsoft.MicrosoftFamilySafetyClient",
    "Microsoft.LanguageExperiencePack",
    "Microsoft.WindowsCommunicationsApps",
    "Microsoft.UI.",
    "Microsoft.Dev.",
    "Microsoft.PowerToys",
    "MicrosoftCorporationII.",
    "MicrosoftCorporationIII.",
    "Microsoft.Win32",
    "Microsoft.RemoteDesktop",
    "Microsoft.MicrosoftPCManager",
    "Microsoft.HostApps",
    // Visual Studio family — not games, sometimes ships as Appx.
    "Microsoft.VisualStudio",
    "MSIX.",
];

/// True when the package name starts with any prefix in the skip list.
pub fn is_skipped(package_name: &str) -> bool {
    SKIP_PREFIXES.iter().any(|p| package_name.starts_with(p))
}
