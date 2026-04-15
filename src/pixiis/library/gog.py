"""GOG Galaxy library provider — detects games via Windows registry."""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from pixiis.core.types import AppEntry, AppSource

if TYPE_CHECKING:
    from pixiis.core.config import Config

_GOG_REG_KEY = r"SOFTWARE\WOW6432Node\GOG.com\Games"


class GOGProvider:
    """Discover and launch GOG Galaxy games."""

    def __init__(self, config: Config) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "gog"

    def is_available(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _GOG_REG_KEY)
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    def scan(self) -> list[AppEntry]:
        if sys.platform != "win32":
            return []

        try:
            import winreg

            root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _GOG_REG_KEY)
        except Exception:
            return []

        apps: list[AppEntry] = []
        try:
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(root, index)
                    entry = self._read_game_key(root, subkey_name)
                    if entry is not None:
                        apps.append(entry)
                except OSError:
                    break
                index += 1
        finally:
            winreg.CloseKey(root)

        return apps

    def launch(self, app: AppEntry) -> None:
        game_id = app.metadata.get("game_id", "")
        if game_id:
            webbrowser.open(f"goggalaxy://openGameView/{game_id}")
        elif app.exe_path and app.exe_path.exists():
            cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.Popen(
                [str(app.exe_path)],
                cwd=str(app.exe_path.parent),
                creationflags=cf,
            )

    def get_icon(self, app: AppEntry) -> Path | None:
        return None

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _read_game_key(root, subkey_name: str) -> AppEntry | None:
        """Read a single game entry from the GOG registry."""
        try:
            import winreg

            key = winreg.OpenKey(root, subkey_name)
        except OSError:
            return None

        try:
            game_name = _reg_value(key, "gameName")
            game_id = _reg_value(key, "gameID")
            exe = _reg_value(key, "exe")
            install_path = _reg_value(key, "path")

            if not game_name or not game_id:
                return None

            exe_path: Path | None = None
            if exe:
                exe_path = Path(exe)
            elif install_path:
                exe_path = Path(install_path)

            return AppEntry(
                id=f"gog:{game_id}",
                name=game_name,
                source=AppSource.GOG,
                launch_command=f"goggalaxy://openGameView/{game_id}",
                exe_path=exe_path,
                metadata={"game_id": game_id},
            )
        finally:
            import winreg

            winreg.CloseKey(key)


def _reg_value(key, value_name: str) -> str:
    """Safely read a string value from a registry key."""
    try:
        import winreg

        val, _ = winreg.QueryValueEx(key, value_name)
        return str(val).strip()
    except Exception:
        return ""
