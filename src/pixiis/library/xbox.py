"""Xbox / Microsoft Store / UWP game library provider.

Uses the same proven detection approach as UWPHook (github.com/BrianLima/UWPHook):
enumerate all AppxPackages, read their manifests for display names and AUMIDs,
skip framework/system packages, and detect Xbox Game Pass titles via
MicrosoftGame.Config.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pixiis.core.types import AppEntry, AppSource

if TYPE_CHECKING:
    from pixiis.core.config import Config

# PowerShell script based on UWPHook's GetAUMIDScript.ps1
# Gets ALL non-framework UWP apps with their real display names and AUMIDs
_PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$apps = @()
foreach ($pkg in Get-AppxPackage) {
    if ($pkg.IsFramework) { continue }
    try {
        $manifest = Get-AppxPackageManifest $pkg
        foreach ($appId in $manifest.Package.Applications.Application.Id) {
            $displayName = $manifest.Package.Properties.DisplayName
            $exe = $manifest.Package.Applications.Application.Executable

            # Xbox Game Pass games may have no exe but have MicrosoftGame.Config
            if ([string]::IsNullOrWhiteSpace($exe) -or $exe -eq 'GameLaunchHelper.exe') {
                $configPath = Join-Path $pkg.InstallLocation 'MicrosoftGame.Config'
                if (Test-Path $configPath) {
                    [xml]$gc = Get-Content $configPath
                    $exe = $gc.Game.ExecutableList.Executable.Name
                    if ($exe -is [Object[]]) { $exe = $exe[0].ToString() }
                } else {
                    continue
                }
            }

            # Skip entries with unresolved resource names
            if ($displayName -like '*ms-resource*' -or $displayName -like '*DisplayName*') {
                continue
            }

            # Get logo path
            $logo = ''
            $vis = $manifest.Package.Applications.Application.VisualElements
            if ($vis.Square150x150Logo) {
                $logo = Join-Path $pkg.InstallLocation $vis.Square150x150Logo
            }

            $aumid = $pkg.PackageFamilyName + '!' + $appId
            $installDir = $pkg.InstallLocation

            $apps += @{
                Name = $displayName
                AUMID = $aumid
                Family = $pkg.PackageFamilyName
                PackageName = $pkg.Name
                Exe = $exe
                Logo = $logo
                InstallLocation = $installDir
            }
        }
    } catch {}
}
$apps | ConvertTo-Json -Depth 3
"""

# Package name prefixes that are definitely NOT games/apps users want to see
_SKIP_PREFIXES = (
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
)


class XboxProvider:
    """Discover and launch UWP / Xbox / Microsoft Store apps and games.

    Uses PowerShell + Get-AppxPackageManifest (same approach as UWPHook)
    to enumerate ALL installed UWP apps with their real display names,
    AUMIDs, and logo paths.
    """

    def __init__(self, config: Config) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "xbox"

    def is_available(self) -> bool:
        return sys.platform == "win32"

    def scan(self) -> list[AppEntry]:
        raw = self._run_detection_script()
        if not raw:
            return []

        apps: list[AppEntry] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            entry = self._item_to_entry(item)
            if entry is not None and entry.name not in seen:
                seen.add(entry.name)
                apps.append(entry)
        return apps

    def launch(self, app: AppEntry) -> None:
        aumid = app.metadata.get("aumid", "")
        if aumid:
            # Use explorer with shell:appsFolder for reliable UWP launch
            subprocess.Popen(["explorer.exe", f"shell:appsFolder\\{aumid}"])
        elif app.launch_command:
            subprocess.Popen(["explorer.exe", app.launch_command])

    def get_icon(self, app: AppEntry) -> Path | None:
        logo = app.metadata.get("logo", "")
        if logo:
            # The logo path may have a qualifier like .scale-200
            # Try the exact path first, then common variants
            p = Path(logo)
            if p.exists():
                return p
            # Try scale variants
            for scale in ("scale-200", "scale-100", "scale-150"):
                variant = p.parent / (p.stem + f".{scale}" + p.suffix)
                if variant.exists():
                    return variant
        return None

    # -- internals -----------------------------------------------------------

    def _run_detection_script(self) -> list[dict] | None:
        """Run the PowerShell script to detect installed UWP apps."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-Command", _PS_SCRIPT],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

        if result.returncode != 0 or not result.stdout.strip():
            return None

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

        if isinstance(data, dict):
            data = [data]
        return data

    def _item_to_entry(self, item: dict) -> AppEntry | None:
        """Convert a script result dict to AppEntry, filtering system apps."""
        display_name = item.get("Name", "")
        aumid = item.get("AUMID", "")
        pkg_name = item.get("PackageName", "")
        family = item.get("Family", "")
        logo = item.get("Logo", "")
        install_loc = item.get("InstallLocation", "")
        exe = item.get("Exe", "")

        if not display_name or not aumid:
            return None

        # Skip known system/framework packages
        for prefix in _SKIP_PREFIXES:
            if pkg_name.startswith(prefix):
                return None

        # Build exe path if possible
        exe_path = None
        if exe and install_loc:
            candidate = Path(install_loc) / exe
            if candidate.exists():
                exe_path = candidate

        return AppEntry(
            id=family,
            name=display_name,
            source=AppSource.XBOX,
            launch_command=f"shell:appsFolder\\{aumid}",
            exe_path=exe_path,
            icon_path=Path(logo) if logo else None,
            metadata={
                "aumid": aumid,
                "package_name": pkg_name,
                "family": family,
                "logo": logo,
            },
        )
