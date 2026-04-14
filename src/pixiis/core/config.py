"""TOML-based configuration for Pixiis."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

from pixiis.core.paths import config_file, default_config_file


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Application configuration loaded from TOML.

    Loads defaults from resources/default_config.toml, then overlays
    user config from %APPDATA%/pixiis/config.toml.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Load default config, then overlay user config."""
        defaults_path = default_config_file()
        if defaults_path.exists():
            with open(defaults_path, "rb") as f:
                self._data = tomllib.load(f)

        user_path = config_file()
        if user_path.exists():
            with open(user_path, "rb") as f:
                user_data = tomllib.load(f)
            self._data = _deep_merge(self._data, user_data)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Get a config value by dotted key path.

        Example: config.get("voice.live_model") -> "large-v3"
        """
        keys = dotted_key.split(".")
        node = self._data
        for key in keys:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return default
        return node

    def section(self, name: str) -> dict[str, Any]:
        """Get a whole config section as a dict."""
        return dict(self._data.get(name, {}))

    @property
    def data(self) -> dict[str, Any]:
        """Raw config data."""
        return self._data

    def ensure_user_config(self) -> Path:
        """Copy default config to user config location if it doesn't exist."""
        user_path = config_file()
        if not user_path.exists():
            defaults_path = default_config_file()
            if defaults_path.exists():
                user_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(defaults_path, user_path)
        return user_path


# Singleton config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global Config instance, creating it on first call."""
    global _config
    if _config is None:
        _config = Config()
    return _config
