"""Tests for pixiis.core.types — AppEntry properties."""

from __future__ import annotations

from pathlib import Path

from pixiis.core.types import AppEntry, AppSource


def test_display_name(make_app):
    app = make_app(name="Halo Infinite")
    assert app.display_name == "Halo Infinite"


def test_is_game_steam(make_app):
    app = make_app(source=AppSource.STEAM)
    assert app.is_game is True


def test_is_game_epic(make_app):
    app = make_app(source=AppSource.EPIC)
    assert app.is_game is True


def test_is_game_gog(make_app):
    app = make_app(source=AppSource.GOG)
    assert app.is_game is True


def test_is_game_ea(make_app):
    app = make_app(source=AppSource.EA)
    assert app.is_game is True


def test_is_game_xbox_without_flag(make_app):
    app = make_app(source=AppSource.XBOX)
    assert app.is_game is False


def test_is_game_xbox_with_flag(make_app):
    app = make_app(source=AppSource.XBOX, metadata={"is_xbox_game": True})
    assert app.is_game is True


def test_is_game_startmenu(make_app):
    app = make_app(source=AppSource.STARTMENU)
    assert app.is_game is False


def test_is_game_manual(make_app):
    app = make_app(source=AppSource.MANUAL)
    assert app.is_game is False


def test_is_installed_with_launch_command(make_app):
    app = make_app()
    assert app.is_installed is True


def test_is_installed_no_command():
    app = AppEntry(
        id="test:empty",
        name="Empty",
        source=AppSource.STEAM,
        launch_command="",
        exe_path=None,
    )
    assert app.is_installed is False


def test_is_installed_xbox_always_true(make_app):
    app = make_app(source=AppSource.XBOX)
    assert app.is_installed is True


def test_is_favorite_default(make_app):
    app = make_app()
    assert app.is_favorite is False


def test_is_favorite_set(make_app):
    app = make_app(metadata={"favorite": True})
    assert app.is_favorite is True


def test_is_favorite_setter(make_app):
    app = make_app()
    assert app.is_favorite is False
    app.is_favorite = True
    assert app.is_favorite is True
    assert app.metadata["favorite"] is True
    app.is_favorite = False
    assert app.is_favorite is False


def test_playtime_display(make_app):
    app = make_app()
    assert app.playtime_display == ""

    app.playtime_minutes = 30
    assert app.playtime_display == "30 min"

    app.playtime_minutes = 120
    assert app.playtime_display == "2 hrs"

    app.playtime_minutes = 150
    assert app.playtime_display == "2.5 hrs"
