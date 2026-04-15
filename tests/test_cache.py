"""Tests for pixiis.library.cache — LibraryCache save/load round-trip."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from pixiis.core.types import AppEntry, AppSource
from pixiis.library.cache import LibraryCache


def _make_cache(tmp_path: Path) -> LibraryCache:
    """Create a LibraryCache using a temp directory."""
    cache = LibraryCache()
    cache._cache_file = tmp_path / "library_cache.json"
    return cache


def test_save_and_load_roundtrip(tmp_path, make_app):
    cache = _make_cache(tmp_path)
    apps = [
        make_app(name="Halo", source=AppSource.STEAM, app_id="steam:halo"),
        make_app(name="Forza", source=AppSource.XBOX, app_id="xbox:forza"),
    ]
    apps[0].metadata["playtime_minutes"] = 120
    apps[1].metadata["favorite"] = True

    cache.save(apps)
    assert cache.exists()

    loaded = cache.load()
    assert loaded is not None
    assert len(loaded) == 2
    assert loaded[0].name == "Halo"
    assert loaded[0].source == AppSource.STEAM
    assert loaded[0].playtime_minutes == 120
    assert loaded[1].name == "Forza"
    assert loaded[1].is_favorite is True


def test_load_missing_file(tmp_path):
    cache = _make_cache(tmp_path)
    assert cache.exists() is False
    assert cache.load() is None


def test_load_corrupted_json(tmp_path):
    cache = _make_cache(tmp_path)
    cache._cache_file.write_text("NOT VALID JSON {{{", encoding="utf-8")
    assert cache.load() is None


def test_load_empty_file(tmp_path):
    cache = _make_cache(tmp_path)
    cache._cache_file.write_text("", encoding="utf-8")
    assert cache.load() is None


def test_save_with_none_paths(tmp_path, make_app):
    cache = _make_cache(tmp_path)
    app = make_app(name="NoPath")
    app.exe_path = None
    app.icon_path = None
    cache.save([app])

    loaded = cache.load()
    assert loaded is not None
    assert len(loaded) == 1
    assert loaded[0].exe_path is None
    assert loaded[0].icon_path is None


def test_save_with_exe_path(tmp_path, make_app):
    cache = _make_cache(tmp_path)
    app = make_app(name="WithPath", exe_path=Path("/games/test.exe"))
    cache.save([app])

    loaded = cache.load()
    assert loaded is not None
    assert loaded[0].exe_path == Path("/games/test.exe")
