"""Epic Games Store library provider — detects games via manifest files."""

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

_MANIFESTS_DIR = Path("C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests")


class EpicProvider:
    """Discover and launch Epic Games Store games."""

    def __init__(self, config: Config) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "epic"

    def is_available(self) -> bool:
        if sys.platform != "win32":
            return False
        return _MANIFESTS_DIR.is_dir()

    def scan(self) -> list[AppEntry]:
        if not _MANIFESTS_DIR.is_dir():
            return []

        apps: list[AppEntry] = []
        for item_file in _MANIFESTS_DIR.glob("*.item"):
            entry = self._parse_manifest(item_file)
            if entry is not None:
                apps.append(entry)
        return apps

    def launch(self, app: AppEntry) -> None:
        app_name = app.metadata.get("app_name", "")
        if app_name:
            webbrowser.open(
                f"com.epicgames.launcher://apps/{app_name}?action=launch"
            )
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
    def _parse_manifest(path: Path) -> AppEntry | None:
        """Parse a single .item manifest file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return None

        display_name = data.get("DisplayName", "").strip()
        app_name = data.get("AppName", "")
        install_location = data.get("InstallLocation", "")
        launch_exe = data.get("LaunchExecutable", "")

        if not display_name or not app_name:
            return None

        exe_path: Path | None = None
        if install_location and launch_exe:
            exe_path = Path(install_location) / launch_exe

        catalog_ns = data.get("CatalogNamespace", "")

        return AppEntry(
            id=f"epic:{app_name}",
            name=display_name,
            source=AppSource.EPIC,
            launch_command=f"com.epicgames.launcher://apps/{app_name}?action=launch",
            exe_path=exe_path,
            metadata={
                "app_name": app_name,
                "catalog_namespace": catalog_ns,
            },
        )
