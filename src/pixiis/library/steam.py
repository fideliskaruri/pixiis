"""Steam library provider — detects installed games via appmanifest files."""

from __future__ import annotations

import re
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from pixiis.core.types import AppEntry, AppSource

if TYPE_CHECKING:
    from pixiis.core.config import Config

# Steam art CDN template
_ART_URL = "https://steamcdn-a.akamaihd.net/steam/apps/{appid}/header.jpg"


class SteamProvider:
    """Discover and launch Steam games."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._steam_path: Path | None = None

    @property
    def name(self) -> str:
        return "steam"

    def is_available(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            self._steam_path = self._find_steam_path()
            return self._steam_path is not None
        except Exception:
            return False

    def scan(self) -> list[AppEntry]:
        steam = self._steam_path or self._find_steam_path()
        if steam is None:
            return []

        library_paths = self._parse_library_folders(steam)
        # The main steamapps folder is always a library
        main_steamapps = steam / "steamapps"
        if main_steamapps.is_dir() and main_steamapps not in library_paths:
            library_paths.insert(0, main_steamapps)

        apps: list[AppEntry] = []
        for lib_path in library_paths:
            apps.extend(self._scan_appmanifests(lib_path))
        return apps

    def launch(self, app: AppEntry) -> None:
        cmd = app.launch_command
        if cmd.startswith("steam://"):
            webbrowser.open(cmd)
        else:
            subprocess.Popen(cmd, shell=True)

    def get_icon(self, app: AppEntry) -> Path | None:
        return None  # Handled by IconCache via art_url

    # -- internals -----------------------------------------------------------

    def _find_steam_path(self) -> Path | None:
        """Try the Windows registry, then fall back to common locations."""
        # Config override
        override = self._config.get("library.steam.install_path")
        if override:
            p = Path(override)
            if p.is_dir():
                return p

        # Registry lookup (Windows only)
        if sys.platform == "win32":
            try:
                import winreg

                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Wow6432Node\Valve\Steam",
                )
                value, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                p = Path(value)
                if p.is_dir():
                    return p
            except Exception:
                pass

        # Common fallback paths
        candidates = [
            Path("C:/Program Files (x86)/Steam"),
            Path("C:/Program Files/Steam"),
        ]
        for c in candidates:
            if c.is_dir():
                return c

        return None

    def _parse_library_folders(self, steam_path: Path) -> list[Path]:
        """Parse steamapps/libraryfolders.vdf to find all library directories."""
        vdf_file = steam_path / "steamapps" / "libraryfolders.vdf"
        if not vdf_file.is_file():
            return []

        text = vdf_file.read_text(encoding="utf-8", errors="replace")
        paths: list[Path] = []

        # VDF format: "path"  "C:\\Program Files (x86)\\Steam"
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            raw = match.group(1).replace("\\\\", "\\")
            lib = Path(raw) / "steamapps"
            if lib.is_dir():
                paths.append(lib)

        return paths

    def _scan_appmanifests(self, library_path: Path) -> list[AppEntry]:
        """Read every appmanifest_*.acf in a steamapps directory."""
        apps: list[AppEntry] = []
        for acf in library_path.glob("appmanifest_*.acf"):
            entry = self._parse_acf(acf, library_path)
            if entry is not None:
                apps.append(entry)
        return apps

    def _parse_acf(self, acf_path: Path, library_path: Path) -> AppEntry | None:
        """Extract appid and name from an ACF manifest."""
        try:
            text = acf_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        appid_m = re.search(r'"appid"\s+"(\d+)"', text)
        name_m = re.search(r'"name"\s+"([^"]+)"', text)
        installdir_m = re.search(r'"installdir"\s+"([^"]+)"', text)

        if not appid_m or not name_m:
            return None

        appid = appid_m.group(1)
        app_name = name_m.group(1)

        exe_path: Path | None = None
        if installdir_m:
            game_dir = library_path / "common" / installdir_m.group(1)
            if game_dir.is_dir():
                exe_path = game_dir

        return AppEntry(
            id=appid,
            name=app_name,
            source=AppSource.STEAM,
            launch_command=f"steam://rungameid/{appid}",
            exe_path=exe_path,
            art_url=_ART_URL.format(appid=appid),
            metadata={"appid": appid},
        )
