"""EA App (formerly Origin) library provider."""

from __future__ import annotations

import json
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from pixiis.core.types import AppEntry, AppSource

if TYPE_CHECKING:
    from pixiis.core.config import Config

_EA_INSTALL_DATA = Path("C:/ProgramData/EA Desktop/InstallData")
_EA_GAMES_DIR = Path("C:/Program Files/EA Games")
_EA_REG_KEY = r"SOFTWARE\Electronic Arts"


class EAProvider:
    """Discover and launch EA App games."""

    def __init__(self, config: Config) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "ea"

    def is_available(self) -> bool:
        if sys.platform != "win32":
            return False
        return _EA_INSTALL_DATA.is_dir() or _EA_GAMES_DIR.is_dir() or self._ea_in_registry()

    def scan(self) -> list[AppEntry]:
        apps: list[AppEntry] = []
        seen_ids: set[str] = set()

        # Primary source: EA Desktop InstallData JSON files
        for entry in self._scan_install_data():
            if entry.id not in seen_ids:
                seen_ids.add(entry.id)
                apps.append(entry)

        # Fallback: scan EA Games directory for executables
        for entry in self._scan_ea_games_dir():
            if entry.id not in seen_ids:
                seen_ids.add(entry.id)
                apps.append(entry)

        return apps

    def launch(self, app: AppEntry) -> None:
        content_id = app.metadata.get("content_id", "")
        if content_id:
            webbrowser.open(f"origin2://game/launch?offerIds={content_id}")
        elif app.exe_path and app.exe_path.exists():
            subprocess.Popen([str(app.exe_path)], cwd=str(app.exe_path.parent))

    def get_icon(self, app: AppEntry) -> Path | None:
        return None

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _ea_in_registry() -> bool:
        """Check if EA registry key exists."""
        if sys.platform != "win32":
            return False
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _EA_REG_KEY)
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    @staticmethod
    def _scan_install_data() -> list[AppEntry]:
        """Read EA Desktop InstallData JSON files."""
        if not _EA_INSTALL_DATA.is_dir():
            return []

        apps: list[AppEntry] = []
        for json_file in _EA_INSTALL_DATA.glob("*.json"):
            try:
                data = json.loads(
                    json_file.read_text(encoding="utf-8", errors="replace")
                )
            except (OSError, json.JSONDecodeError):
                continue

            display_name = data.get("displayName", "") or data.get("title", "")
            content_id = data.get("contentId", "") or data.get("softwareId", "")
            install_path = data.get("installLocation", "") or data.get("baseInstallPath", "")

            if not display_name:
                continue

            exe_path: Path | None = None
            if install_path:
                p = Path(install_path)
                if p.is_dir():
                    exe_path = p

            entry_id = f"ea:{content_id}" if content_id else f"ea:{json_file.stem}"

            apps.append(AppEntry(
                id=entry_id,
                name=display_name.strip(),
                source=AppSource.EA,
                launch_command=f"origin2://game/launch?offerIds={content_id}" if content_id else str(exe_path or ""),
                exe_path=exe_path,
                metadata={"content_id": content_id},
            ))
        return apps

    @staticmethod
    def _scan_ea_games_dir() -> list[AppEntry]:
        """Fall back to scanning C:\\Program Files\\EA Games for game folders."""
        if not _EA_GAMES_DIR.is_dir():
            return []

        apps: list[AppEntry] = []
        try:
            for folder in _EA_GAMES_DIR.iterdir():
                if not folder.is_dir():
                    continue

                # Find the largest .exe as the likely game executable
                exes = list(folder.glob("*.exe"))
                if not exes:
                    # Check one level deeper (e.g. EA Games/Game/Binaries/game.exe)
                    exes = list(folder.glob("*/*.exe"))

                if not exes:
                    continue

                main_exe = max(exes, key=lambda e: e.stat().st_size)
                game_name = folder.name

                apps.append(AppEntry(
                    id=f"ea:{game_name.lower().replace(' ', '_')}",
                    name=game_name,
                    source=AppSource.EA,
                    launch_command=str(main_exe),
                    exe_path=main_exe,
                    metadata={},
                ))
        except OSError:
            pass

        return apps
