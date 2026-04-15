"""Tests for pixiis.core.config — Config loading and dotted-key access."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

from pixiis.core.config import Config, _deep_merge


# -- _deep_merge -------------------------------------------------------------


def test_deep_merge_flat():
    base = {"a": 1, "b": 2}
    override = {"b": 3, "c": 4}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": 3, "c": 4}


def test_deep_merge_nested():
    base = {"s": {"x": 1, "y": 2}}
    override = {"s": {"y": 99}}
    result = _deep_merge(base, override)
    assert result == {"s": {"x": 1, "y": 99}}


# -- Config ------------------------------------------------------------------


def test_config_loads_defaults(tmp_path):
    """Config should load the bundled default_config.toml."""
    default = tmp_path / "default.toml"
    default.write_text('[voice]\nlive_model = "base"\n')

    user = tmp_path / "user.toml"  # does not exist

    with (
        patch("pixiis.core.config.default_config_file", return_value=default),
        patch("pixiis.core.config.config_file", return_value=user),
    ):
        cfg = Config()
        assert cfg.get("voice.live_model") == "base"


def test_config_merges_user_overrides(tmp_path):
    default = tmp_path / "default.toml"
    default.write_text('[voice]\nlive_model = "base"\ndevice = "cuda"\n')

    user = tmp_path / "user.toml"
    user.write_text('[voice]\nlive_model = "large-v3"\n')

    with (
        patch("pixiis.core.config.default_config_file", return_value=default),
        patch("pixiis.core.config.config_file", return_value=user),
    ):
        cfg = Config()
        assert cfg.get("voice.live_model") == "large-v3"
        assert cfg.get("voice.device") == "cuda"


def test_config_handles_corrupted_user_toml(tmp_path):
    default = tmp_path / "default.toml"
    default.write_text('[ui]\ntile_size = "large"\n')

    user = tmp_path / "user.toml"
    user.write_text("this is not valid [[[ TOML !!!!")

    with (
        patch("pixiis.core.config.default_config_file", return_value=default),
        patch("pixiis.core.config.config_file", return_value=user),
    ):
        cfg = Config()
        # Should keep defaults when user config is corrupt
        assert cfg.get("ui.tile_size") == "large"


def test_config_handles_corrupted_default_toml(tmp_path):
    default = tmp_path / "default.toml"
    default.write_text("CORRUPT DATA {{{")

    user = tmp_path / "user.toml"  # does not exist

    with (
        patch("pixiis.core.config.default_config_file", return_value=default),
        patch("pixiis.core.config.config_file", return_value=user),
    ):
        cfg = Config()
        assert cfg.data == {}


def test_config_no_files(tmp_path):
    default = tmp_path / "nonexistent_default.toml"
    user = tmp_path / "nonexistent_user.toml"

    with (
        patch("pixiis.core.config.default_config_file", return_value=default),
        patch("pixiis.core.config.config_file", return_value=user),
    ):
        cfg = Config()
        assert cfg.data == {}


def test_get_dotted_key(tmp_path):
    default = tmp_path / "default.toml"
    default.write_text('[voice.transcription]\nfast_beam_size = 3\n')

    user = tmp_path / "user.toml"

    with (
        patch("pixiis.core.config.default_config_file", return_value=default),
        patch("pixiis.core.config.config_file", return_value=user),
    ):
        cfg = Config()
        assert cfg.get("voice.transcription.fast_beam_size") == 3
        assert cfg.get("voice.transcription.missing", 42) == 42
        assert cfg.get("nonexistent.key", "default") == "default"


def test_section(tmp_path):
    default = tmp_path / "default.toml"
    default.write_text('[controller]\ndeadzone = 0.15\nvibration_enabled = true\n')

    user = tmp_path / "user.toml"

    with (
        patch("pixiis.core.config.default_config_file", return_value=default),
        patch("pixiis.core.config.config_file", return_value=user),
    ):
        cfg = Config()
        sec = cfg.section("controller")
        assert sec["deadzone"] == 0.15
        assert sec["vibration_enabled"] is True
        assert cfg.section("missing") == {}
