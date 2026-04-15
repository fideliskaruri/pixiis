"""Shared fixtures for Pixiis tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the src directory is importable
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from pixiis.core.types import AppEntry, AppSource


@pytest.fixture
def make_app():
    """Factory fixture that returns a helper to create AppEntry objects."""

    def _make(
        name: str = "TestGame",
        source: AppSource = AppSource.STEAM,
        app_id: str | None = None,
        exe_path: Path | None = None,
        metadata: dict | None = None,
    ) -> AppEntry:
        return AppEntry(
            id=app_id or f"{source.value}:{name.lower().replace(' ', '_')}",
            name=name,
            source=source,
            launch_command=str(exe_path or "test.exe"),
            exe_path=exe_path,
            metadata=metadata or {},
        )

    return _make


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Return a temporary directory to use as the config root."""
    return tmp_path / "pixiis_config"
