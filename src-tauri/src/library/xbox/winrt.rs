//! Real `PackageEnumerator` impl backed by `Windows.Management.Deployment.PackageManager`.
//!
//! Enumeration approach lifted from `spike/uwp-detect/src/main.rs:317-340`
//! — `FindPackagesByUserSecurityId(empty)` returns the packages installed
//! for the current user, which matches the PowerShell `Get-AppxPackage`
//! default behaviour exactly. COM init is run once per process via
//! `std::sync::Once`; subsequent constructions are no-ops.

use std::path::PathBuf;
use std::sync::Once;

use windows::core::HSTRING;
use windows::Management::Deployment::PackageManager;
use windows::Win32::System::Com::{CoInitializeEx, COINIT_MULTITHREADED};

use super::{PackageEnumerator, RawPackage};

static COM_INIT: Once = Once::new();

fn ensure_com_initialised() {
    COM_INIT.call_once(|| {
        // Multi-threaded apartment so WinRT factories (PackageManager)
        // work without marshaling overhead. Returns S_FALSE if already
        // initialised by Tauri/another module — that's fine.
        unsafe {
            let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
        }
    });
}

pub struct WinRtEnumerator;

impl WinRtEnumerator {
    pub fn new() -> Self {
        ensure_com_initialised();
        Self
    }
}

impl PackageEnumerator for WinRtEnumerator {
    fn is_available(&self) -> bool {
        // Constructing a PackageManager exercises the
        // Management.Deployment runtime; if WinRT activation fails (e.g.
        // sandboxed VM with the Appx APIs blocked) we want is_available
        // to report false rather than enumerate to crash later.
        ensure_com_initialised();
        PackageManager::new().is_ok()
    }

    fn enumerate(&self) -> Vec<RawPackage> {
        ensure_com_initialised();
        let manager = match PackageManager::new() {
            Ok(m) => m,
            Err(_) => return Vec::new(),
        };
        let empty = HSTRING::new();
        let iter = match manager.FindPackagesByUserSecurityId(&empty) {
            Ok(i) => i,
            Err(_) => return Vec::new(),
        };

        let mut out = Vec::new();
        for pkg in iter {
            // Per-package errors (e.g. orphaned packages whose install
            // dir was reaped) are swallowed — the spike showed ~0-2
            // such errors on a typical dev machine and the Python
            // version silently swallows them inside the PS try/catch.
            let Ok(id) = pkg.Id() else { continue };
            let Ok(package_name) = id.Name().map(|s| s.to_string()) else {
                continue;
            };
            let Ok(family_name) = id.FamilyName().map(|s| s.to_string()) else {
                continue;
            };
            let is_framework = pkg.IsFramework().unwrap_or(false);
            let display_name = pkg
                .DisplayName()
                .map(|s| s.to_string())
                .unwrap_or_default();
            let install_location = match pkg.InstalledLocation() {
                Ok(loc) => match loc.Path() {
                    Ok(p) => PathBuf::from(p.to_string()),
                    Err(_) => continue,
                },
                Err(_) => continue,
            };

            out.push(RawPackage {
                package_name,
                family_name,
                display_name,
                install_location,
                is_framework,
            });
        }
        out
    }
}
