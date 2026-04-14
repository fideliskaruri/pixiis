"""Central app registry — aggregates all library providers."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from pixiis.core.events import bus
from pixiis.core.types import AppEntry, AppSource

if TYPE_CHECKING:
    from pixiis.core.config import Config
    from pixiis.library.base import LibraryProvider


def _normalize_exe_path(path: str | os.PathLike[str] | None) -> str | None:
    """Normalize an executable path for deduplication."""
    if path is None:
        return None
    p = str(path)
    if sys.platform == "win32":
        p = p.lower()
    return os.path.normpath(p)


# Maps provider name -> lazy import factory
_PROVIDER_FACTORIES: dict[str, type] = {}


def _get_provider_class(name: str) -> type | None:
    """Lazily import and return the provider class for *name*."""
    if name == "steam":
        from pixiis.library.steam import SteamProvider
        return SteamProvider
    if name == "xbox":
        from pixiis.library.xbox import XboxProvider
        return XboxProvider
    if name == "startmenu":
        from pixiis.library.startmenu import StartMenuProvider
        return StartMenuProvider
    if name == "epic":
        from pixiis.library.epic import EpicProvider
        return EpicProvider
    if name == "gog":
        from pixiis.library.gog import GOGProvider
        return GOGProvider
    if name == "ea":
        from pixiis.library.ea import EAProvider
        return EAProvider
    if name == "manual":
        from pixiis.library.manual import ManualProvider
        return ManualProvider
    if name == "folders":
        from pixiis.library.folder_scanner import FolderScanProvider
        return FolderScanProvider
    return None


class LibraryUpdatedEvent:
    """Published on the event bus after a successful scan."""

    def __init__(self, apps: list[AppEntry]) -> None:
        self.apps = apps


class AppRegistry:
    """Aggregates apps from every enabled :class:`LibraryProvider`."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._providers: list[LibraryProvider] = []
        self._apps: list[AppEntry] = []

        provider_names: list[str] = config.get("library.providers", [])
        for name in provider_names:
            cls = _get_provider_class(name)
            if cls is None:
                continue
            try:
                provider = cls(config)
            except Exception:
                continue
            self._providers.append(provider)

    # -- public API ----------------------------------------------------------

    def scan_all(self) -> list[AppEntry]:
        """Run scan() on every available provider and merge results."""
        results: list[AppEntry] = []
        for provider in self._providers:
            if not provider.is_available():
                continue
            try:
                results.extend(provider.scan())
            except Exception:
                continue

        self._apps = _deduplicate(results)
        bus.publish(LibraryUpdatedEvent(self._apps))
        return self._apps

    def get_all(self) -> list[AppEntry]:
        """Return the cached app list (call :meth:`scan_all` first)."""
        return list(self._apps)

    def search(self, query: str) -> list[AppEntry]:
        """Fuzzy name match against cached apps."""
        q = query.lower()
        scored: list[tuple[int, AppEntry]] = []
        for app in self._apps:
            name_lower = app.name.lower()
            if q == name_lower:
                scored.append((0, app))
            elif q in name_lower:
                scored.append((1, app))
            elif _subsequence_match(q, name_lower):
                scored.append((2, app))
        scored.sort(key=lambda t: t[0])
        return [app for _, app in scored]

    def filter_by_source(self, source: AppSource) -> list[AppEntry]:
        """Return cached apps from a single source."""
        return [app for app in self._apps if app.source == source]

    def launch(self, app: AppEntry) -> None:
        """Delegate launch to the provider that owns *app*."""
        for provider in self._providers:
            if provider.name == app.source.value:
                provider.launch(app)
                return
        raise ValueError(f"No provider found for source {app.source!r}")


# -- helpers -----------------------------------------------------------------


def _deduplicate(apps: list[AppEntry]) -> list[AppEntry]:
    """Remove duplicates by normalized exe_path, keeping the first seen."""
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    unique: list[AppEntry] = []
    for app in apps:
        norm = _normalize_exe_path(app.exe_path)
        if norm and norm in seen_paths:
            continue
        key = f"{app.source.value}:{app.id}"
        if key in seen_ids:
            continue
        if norm:
            seen_paths.add(norm)
        seen_ids.add(key)
        unique.append(app)
    return unique


def _subsequence_match(query: str, text: str) -> bool:
    """Return True if every character in *query* appears in *text* in order."""
    it = iter(text)
    return all(ch in it for ch in query)
