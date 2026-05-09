//! Package-name prefix skip-list.
//!
//! Direct port of `_SKIP_PREFIXES` from `src/pixiis/library/xbox.py:81-103`,
//! extended in Wave 3 (broader Microsoft non-game UWPs) and Wave 6
//! (Xbox infrastructure packages, third-party non-game UWPs that ship
//! a real `.exe`). Drift here makes the Rust scanner diverge from the
//! Python contract on the same machine, so changes should be deliberate.
//!
//! Wave 6 context: see `agents/wave6-uwp-research.md` § 5 and
//! `agents/wave6-xbox-audit.md` § 3 for the audit. The skip-list runs
//! BEFORE the gaming-detection chain in `mod.rs::scan_with_options`, so
//! every entry here pre-empts both the publisher-prefix and
//! install-path checks. Critical when a package has the
//! `Microsoft.Xbox*` shape but is system infrastructure (Game Bar,
//! identity broker, …).

const SKIP_PREFIXES: &[&str] = &[
    // ── Microsoft platform / runtime ──────────────────────────────
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
    "Microsoft.HEIFImageExtensions",
    "Microsoft.WebpImageExtension",
    "Microsoft.WebpImageExtensions",
    "Microsoft.RawImageExtension",
    "Microsoft.AV1VideoExtension",
    "Microsoft.AV1ProfessionalEncoderExtension",
    "Microsoft.HEVCVideoExtension",
    "Microsoft.HEVCVideoExtensions",
    "Microsoft.MPEG2VideoExtension",
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
    // ── Wave 6: Xbox INFRASTRUCTURE packages — none of these are
    // games. They pre-install on every Win 11 box and previously
    // matched the bare `Microsoft.Xbox` family-prefix heuristic.
    // Per `wave6-xbox-audit.md` § 3 these are the dominant
    // false-positive cluster the user is reporting.
    "Microsoft.XboxIdentityProvider",
    "Microsoft.XboxGameOverlay",
    "Microsoft.XboxGamingOverlay",
    "Microsoft.XboxSpeechToTextOverlay",
    "Microsoft.Xbox.TCUI",
    "Microsoft.XboxApp",
    "Microsoft.GamingApp",
    "Microsoft.GamingServices",
    "Microsoft.GamingServicesNet",
    "GamingServices.",
    // ── Microsoft Store front + Bing/MSN family ──────────────────
    "Microsoft.MicrosoftEdge",
    "Microsoft.Edge",
    "MicrosoftEdge.",
    "Microsoft.MicrosoftEdgeDevToolsClient",
    "MicrosoftEdgeDevToolsClient.",
    "Microsoft.Bing",
    "Microsoft.BingNews",
    "Microsoft.BingWeather",
    "Microsoft.BingFinance",
    "Microsoft.BingSports",
    "Microsoft.BingTranslator",
    "Microsoft.MSN.",
    "Microsoft.News",
    // ── Microsoft Office / productivity / communications ─────────
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
    "Microsoft.MicrosoftToDoList",
    "Microsoft.Todos",
    "Microsoft.MicrosoftPowerBIForWindows",
    "Microsoft.MicrosoftPowerBIForWindows.",
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
    "Microsoft.ScreenSketch",
    "Microsoft.MicrosoftFamilySafetyClient",
    "Microsoft.LanguageExperiencePack",
    "Microsoft.WindowsCommunicationsApps",
    "microsoft.windowscommunicationsapps",
    "Microsoft.Wallet",
    "Microsoft.WindowsReadingList",
    "Microsoft.OneConnect",
    "Microsoft.PrintHelp",
    "Microsoft.PrintDialog",
    "Microsoft.Print3D",
    "Microsoft.3DBuilder",
    // ── Microsoft media / video editor ───────────────────────────
    "Microsoft.MicrosoftClipchamp",
    "Clipchamp.Clipchamp",
    "Clipchamp.",
    // ── UI / shell / corporate package buckets ───────────────────
    "Microsoft.UI.",
    "Microsoft.Dev.",
    "Microsoft.PowerToys",
    "MicrosoftCorporationII.",
    "MicrosoftCorporationIII.",
    "Microsoft.Win32",
    "Microsoft.RemoteDesktop",
    "Microsoft.MicrosoftPCManager",
    "Microsoft.HostApps",
    "Microsoft.WindowsClient.",
    // ── Visual Studio family ─────────────────────────────────────
    "Microsoft.VisualStudio",
    "MSIX.",
    // ── Wave 6: third-party non-game UWPs that ship a real .exe.
    // Pre-Wave-6 these were classified as games via the now-deleted
    // `has_significant_exe` heuristic. With that gone they would
    // simply land as `is_xbox_game = false`, but listing them here
    // also keeps them out of the broader UWP library list.
    // Source: `wave6-uwp-research.md` § 5.2.
    "SpotifyAB.SpotifyMusic",
    "Spotify.SpotifyMusic",
    "Spotify.",
    "Discord.Discord",
    "Discord.",
    "4DF9E0F8.Netflix",
    "Netflix.Netflix",
    "Netflix.",
    "WhatsAppInc.WhatsAppDesktop",
    "WhatsAppInc.",
    "5319275A.WhatsAppDesktop",
    "GitHub.GitHubDesktop",
    "GitHub.",
    "DisneyInteractive.DisneyPlus",
    "Disney.DisneyPlus",
    "HuluLLC.HuluPlus",
    "HuluLLC.",
    "Mozilla.Firefox",
    "GoogleLLC.GoogleChrome",
    "SlackTechnologies.Slack",
    "SonicWALLInc.NetExtender",
    "PaintdotNet.PaintdotNet",
    "PaintdotNet.",
    "AdobeSystemsIncorporated.",
    "AdobeAI",
    "AdobeReader",
    "Autodesk.",
    "NVIDIACorp.NVIDIAControlPanel",
    "NVIDIACorp.NVIDIAGeForceExperience",
    "NVIDIAControlPanel",
    "NVIDIACorp.",
    "Microsoft.GeforceNOW",
    // Anti-cheat / overlay components shipped as standalone packages
    // (the EAC service appears as a separate Appx; the games it
    // protects are matched by their own publisher prefixes).
    "EpicGames.EasyAntiCheat",
];

/// True when the package name starts with any prefix in the skip list.
pub fn is_skipped(package_name: &str) -> bool {
    SKIP_PREFIXES.iter().any(|p| package_name.starts_with(p))
}
