"""Application path resolution for Pixiis."""

import os
import sys
from pathlib import Path


def _appdata_dir() -> Path:
    """Return the platform-appropriate application data directory."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(base) / "pixiis"


def config_dir() -> Path:
    """Return the config directory, creating it if needed."""
    d = _appdata_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    """Return the cache directory (icons, art, etc.), creating it if needed."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
    d = Path(base) / "pixiis"
    d.mkdir(parents=True, exist_ok=True)
    return d


def icon_cache_dir() -> Path:
    """Return the icon cache directory."""
    d = cache_dir() / "icons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    """Return the path to the user's config.toml."""
    return config_dir() / "config.toml"


def default_config_file() -> Path:
    """Return the path to the bundled default config."""
    return Path(__file__).parent.parent.parent.parent / "resources" / "default_config.toml"
