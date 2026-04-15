"""Manual library provider — user-configured apps from config.toml."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pixiis.core.types import AppEntry, AppSource

if TYPE_CHECKING:
    from pixiis.core.config import Config


class ManualProvider:
    """Wraps manually configured apps from [library.manual.apps]."""

    def __init__(self, config: Config) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "manual"

    def is_available(self) -> bool:
        return True  # Always available — just reads config

    def scan(self) -> list[AppEntry]:
        raw_apps = self._config.get("library.manual.apps", [])
        if not isinstance(raw_apps, list):
            return []

        entries: list[AppEntry] = []
        for item in raw_apps:
            if not isinstance(item, dict):
                continue
            entry = self._item_to_entry(item)
            if entry is not None:
                entries.append(entry)
        return entries

    def launch(self, app: AppEntry) -> None:
        if app.exe_path and app.exe_path.exists():
            cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.Popen(
                [str(app.exe_path)],
                cwd=str(app.exe_path.parent),
                creationflags=cf,
            )

    def get_icon(self, app: AppEntry) -> Path | None:
        return app.icon_path

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _item_to_entry(item: dict) -> AppEntry | None:
        """Convert a config dict to an AppEntry."""
        name = item.get("name", "").strip()
        path_str = item.get("path", "").strip()
        if not name or not path_str:
            return None

        exe_path = Path(path_str)
        icon_str = item.get("icon", "")
        icon_path = Path(icon_str) if icon_str else None

        return AppEntry(
            id=f"manual:{name.lower().replace(' ', '_')}",
            name=name,
            source=AppSource.MANUAL,
            launch_command=str(exe_path),
            exe_path=exe_path,
            icon_path=icon_path,
        )
