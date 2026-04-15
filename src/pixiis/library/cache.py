"""Disk cache for the scanned library — enables instant startup."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pixiis.core.paths import cache_dir
from pixiis.core.types import AppEntry, AppSource

log = logging.getLogger(__name__)


class LibraryCache:
    """Persists scanned :class:`AppEntry` objects to a JSON file.

    On startup the registry can load from cache so the UI has data
    immediately, then refresh in the background.
    """

    def __init__(self) -> None:
        self._cache_file = cache_dir() / "library_cache.json"

    # -- public API ----------------------------------------------------------

    def exists(self) -> bool:
        """Return True if the cache file exists on disk."""
        return self._cache_file.exists()

    def load(self) -> list[AppEntry] | None:
        """Load cached apps.  Returns *None* if cache is missing or corrupt."""
        if not self._cache_file.exists():
            return None
        try:
            raw = self._cache_file.read_text(encoding="utf-8")
            data: list[dict[str, Any]] = json.loads(raw)
            return [self._dict_to_entry(item) for item in data]
        except Exception:
            log.warning("Library cache corrupt or unreadable — ignoring")
            return None

    def save(self, apps: list[AppEntry]) -> None:
        """Serialize *apps* to the cache file."""
        try:
            data = [self._entry_to_dict(app) for app in apps]
            self._cache_file.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            log.warning("Failed to write library cache", exc_info=True)

    # -- serialization helpers -----------------------------------------------

    @staticmethod
    def _entry_to_dict(app: AppEntry) -> dict[str, Any]:
        """Convert an AppEntry to a JSON-safe dict."""
        return {
            "id": app.id,
            "name": app.name,
            "source": app.source.value,
            "launch_command": app.launch_command,
            "exe_path": str(app.exe_path) if app.exe_path else None,
            "icon_path": str(app.icon_path) if app.icon_path else None,
            "art_url": app.art_url,
            "metadata": app.metadata,
        }

    @staticmethod
    def _dict_to_entry(d: dict[str, Any]) -> AppEntry:
        """Reconstruct an AppEntry from a cached dict."""
        exe_raw = d.get("exe_path")
        icon_raw = d.get("icon_path")
        return AppEntry(
            id=d["id"],
            name=d["name"],
            source=AppSource(d["source"]),
            launch_command=d["launch_command"],
            exe_path=Path(exe_raw) if exe_raw else None,
            icon_path=Path(icon_raw) if icon_raw else None,
            art_url=d.get("art_url"),
            metadata=d.get("metadata", {}),
        )
