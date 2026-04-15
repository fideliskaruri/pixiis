"""Tests for pixiis.core.registry — AppRegistry search, filter, dedup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from pixiis.core.types import AppEntry, AppSource
from pixiis.library.registry import AppRegistry, _deduplicate


# -- Deduplication -----------------------------------------------------------


def test_deduplicate_by_exe_path(make_app):
    exe = Path("/games/game.exe")
    a = make_app(name="Game A", source=AppSource.STEAM, exe_path=exe)
    b = make_app(name="Game B", source=AppSource.STARTMENU, exe_path=exe)
    result = _deduplicate([a, b])
    assert len(result) == 1
    assert result[0].name == "Game A"


def test_deduplicate_by_source_id(make_app):
    a = make_app(name="Same", source=AppSource.STEAM, app_id="steam:same")
    b = make_app(name="Same", source=AppSource.STEAM, app_id="steam:same")
    result = _deduplicate([a, b])
    assert len(result) == 1


def test_deduplicate_no_exe_path(make_app):
    a = make_app(name="A", source=AppSource.STEAM, app_id="steam:a")
    b = make_app(name="B", source=AppSource.STEAM, app_id="steam:b")
    result = _deduplicate([a, b])
    assert len(result) == 2


# -- AppRegistry with ManualProvider ----------------------------------------


def _make_registry(apps: list[AppEntry]) -> AppRegistry:
    """Create a registry with a mock config and pre-loaded apps."""
    mock_config = MagicMock()
    mock_config.get.return_value = []  # no providers

    with patch("pixiis.library.cache.LibraryCache") as MockCache:
        MockCache.return_value.load.return_value = apps
        registry = AppRegistry(mock_config)

    return registry


def test_registry_get_all(make_app):
    apps = [make_app(name="A"), make_app(name="B")]
    reg = _make_registry(apps)
    assert len(reg.get_all()) == 2


def test_registry_search(make_app):
    apps = [
        make_app(name="Halo Infinite", app_id="steam:halo"),
        make_app(name="Forza Horizon", app_id="steam:forza"),
        make_app(name="Half-Life 2", app_id="steam:hl2"),
    ]
    reg = _make_registry(apps)

    results = reg.search("halo")
    assert len(results) >= 1
    assert results[0].name == "Halo Infinite"


def test_registry_search_subsequence(make_app):
    apps = [make_app(name="Grand Theft Auto V", app_id="steam:gta")]
    reg = _make_registry(apps)

    results = reg.search("gta")
    assert len(results) == 1


def test_registry_search_no_results(make_app):
    apps = [make_app(name="Halo", app_id="steam:halo")]
    reg = _make_registry(apps)
    assert reg.search("zzzznotexist") == []


def test_registry_filter_by_source(make_app):
    apps = [
        make_app(name="Steam Game", source=AppSource.STEAM, app_id="steam:sg"),
        make_app(name="Xbox Game", source=AppSource.XBOX, app_id="xbox:xg"),
        make_app(name="Epic Game", source=AppSource.EPIC, app_id="epic:eg"),
    ]
    reg = _make_registry(apps)

    steam = reg.filter_by_source(AppSource.STEAM)
    assert len(steam) == 1
    assert steam[0].name == "Steam Game"

    xbox = reg.filter_by_source(AppSource.XBOX)
    assert len(xbox) == 1

    gog = reg.filter_by_source(AppSource.GOG)
    assert len(gog) == 0


def test_registry_scan_all_with_mock_provider(make_app):
    mock_config = MagicMock()
    mock_config.get.return_value = []  # no providers via config

    with patch("pixiis.library.registry.LibraryCache") as MockCache:
        MockCache.return_value.load.return_value = None
        registry = AppRegistry(mock_config)

    # Inject a mock provider
    mock_provider = MagicMock()
    mock_provider.is_available.return_value = True
    mock_provider.scan.return_value = [
        make_app(name="Scanned Game", app_id="mock:sg"),
    ]
    registry._providers = [mock_provider]

    result = registry.scan_all()
    assert len(result) == 1
    assert result[0].name == "Scanned Game"
