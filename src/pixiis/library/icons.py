"""Icon cache — download Steam art and extract exe icons."""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from pixiis.core.paths import icon_cache_dir
from pixiis.core.types import AppEntry, AppSource


class IconCache:
    """Manages cached icons for library entries."""

    def __init__(self) -> None:
        self._cache_dir = icon_cache_dir()

    def get_icon(self, app: AppEntry) -> Path | None:
        """Return a cached icon path, fetching/extracting if needed."""
        # Check if app already has an icon on disk
        if app.icon_path and app.icon_path.exists():
            return app.icon_path

        # Try Steam art download
        if app.source == AppSource.STEAM and app.art_url:
            appid = app.metadata.get("appid", app.id)
            cached = self._cache_dir / f"steam_{appid}.jpg"
            if cached.exists():
                return cached
            return self.download_steam_art(appid, app.art_url)

        # Try exe icon extraction
        if app.exe_path and app.exe_path.is_file():
            cached = self._cache_path_for_exe(app.exe_path)
            if cached.exists():
                return cached
            return self.extract_exe_icon(app.exe_path)

        return None

    def download_steam_art(self, appid: str, url: str) -> Path | None:
        """Download a Steam header image to the cache."""
        dest = self._cache_dir / f"steam_{appid}.jpg"
        try:
            urllib.request.urlretrieve(url, dest)
            return dest
        except Exception:
            return None

    def extract_exe_icon(self, exe_path: Path) -> Path | None:
        """Try to extract an icon from an executable using icoextract."""
        dest = self._cache_path_for_exe(exe_path)
        try:
            from icoextract import IconExtractor  # type: ignore[import-untyped]

            extractor = IconExtractor(str(exe_path))
            extractor.export_icon(str(dest), num=0)
            if dest.exists():
                return dest
        except Exception:
            pass
        return None

    def _cache_path_for_exe(self, exe_path: Path) -> Path:
        """Deterministic cache filename for an exe icon."""
        h = hashlib.md5(str(exe_path).lower().encode()).hexdigest()[:12]
        return self._cache_dir / f"exe_{h}.ico"
