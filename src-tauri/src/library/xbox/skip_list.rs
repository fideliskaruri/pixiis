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
];

/// True when the package name starts with any prefix in the skip list.
pub fn is_skipped(package_name: &str) -> bool {
    SKIP_PREFIXES.iter().any(|p| package_name.starts_with(p))
}
