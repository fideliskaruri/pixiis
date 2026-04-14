"""Xbox / Microsoft Store library provider."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pixiis.core.types import AppEntry, AppSource

if TYPE_CHECKING:
    from pixiis.core.config import Config

# Publishers / prefixes that are almost never games
_SYSTEM_PREFIXES = (
    "Microsoft.Windows",
    "Microsoft.MicrosoftEdge",
    "Microsoft.Office",
    "Microsoft.ScreenSketch",
    "Microsoft.GetHelp",
    "Microsoft.Getstarted",
    "Microsoft.MSPaint",
    "Microsoft.People",
    "Microsoft.Todos",
    "Microsoft.YourPhone",
    "Microsoft.StorePurchaseApp",
    "Microsoft.VP9VideoExtensions",
    "Microsoft.WebMediaExtensions",
    "Microsoft.HEIFImageExtension",
    "Microsoft.WebpImageExtension",
    "Microsoft.DesktopAppInstaller",
    "Microsoft.Services",
    "Microsoft.UI.Xaml",
    "Microsoft.VCLibs",
    "Microsoft.NET",
    "Microsoft.Advertising",
    "MicrosoftWindows.",
    "windows.",
    "Microsoft.549981C3F5F10",  # Cortana
    "Microsoft.BingWeather",
    "Microsoft.BingNews",
    "Microsoft.ZuneMusic",
    "Microsoft.ZuneVideo",
)

# Keywords that suggest a package is a game
_GAME_KEYWORDS = (
    "game", "xbox", "play", "entertainment", "ea.", "ubisoft",
    "bethesda", "activision", "mojang", "minecraft",
)


class XboxProvider:
    """Discover and launch Xbox / Microsoft Store games."""

    def __init__(self, config: Config) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "xbox"

    def is_available(self) -> bool:
        return sys.platform == "win32"

    def scan(self) -> list[AppEntry]:
        packages = self._get_appx_packages()
        if packages is None:
            return []

        apps: list[AppEntry] = []
        for pkg in packages:
            if not isinstance(pkg, dict):
                continue
            entry = self._package_to_entry(pkg)
            if entry is not None:
                apps.append(entry)
        return apps

    def launch(self, app: AppEntry) -> None:
        family = app.id
        subprocess.Popen(
            ["explorer.exe", f"shell:appsFolder\\{family}!App"],
        )

    def get_icon(self, app: AppEntry) -> Path | None:
        return None

    # -- internals -----------------------------------------------------------

    def _get_appx_packages(self) -> list[dict] | None:
        """Call PowerShell to enumerate installed Appx packages."""
        try:
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    "Get-AppxPackage | Select-Object Name,PackageFamilyName,Publisher,IsFramework,SignatureKind | ConvertTo-Json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

        if result.returncode != 0 or not result.stdout.strip():
            return None

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

        # PowerShell returns a single object (not list) when there's one item
        if isinstance(data, dict):
            data = [data]
        return data

    def _package_to_entry(self, pkg: dict) -> AppEntry | None:
        """Convert an Appx package dict to an AppEntry, or None if filtered."""
        pkg_name: str = pkg.get("Name", "")
        family: str = pkg.get("PackageFamilyName", "")

        if not pkg_name or not family:
            return None

        # Skip framework packages
        if pkg.get("IsFramework"):
            return None

        # Skip system/utility packages by prefix
        for prefix in _SYSTEM_PREFIXES:
            if pkg_name.startswith(prefix):
                return None

        # Heuristic: only include packages that look like games
        combined = f"{pkg_name} {family}".lower()
        if not any(kw in combined for kw in _GAME_KEYWORDS):
            return None

        display_name = self._humanize_name(pkg_name)

        return AppEntry(
            id=family,
            name=display_name,
            source=AppSource.XBOX,
            launch_command=f"shell:appsFolder\\{family}!App",
            metadata={"package_name": pkg_name, "family": family},
        )

    @staticmethod
    def _humanize_name(pkg_name: str) -> str:
        """Best-effort conversion of a package Name to a readable title."""
        # Strip publisher prefix (e.g. "Microsoft.MinecraftUWP" -> "MinecraftUWP")
        parts = pkg_name.rsplit(".", 1)
        raw = parts[-1] if len(parts) > 1 else pkg_name
        # Insert spaces before uppercase runs: "MinecraftUWP" -> "Minecraft UWP"
        import re
        spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)
        spaced = re.sub(r"(?<=[A-Z]+)(?=[A-Z][a-z])", " ", spaced)
        return spaced
