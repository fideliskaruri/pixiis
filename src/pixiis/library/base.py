"""Library provider protocol for Pixiis."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pixiis.core.types import AppEntry


@runtime_checkable
class LibraryProvider(Protocol):
    """Interface that every library source must implement."""

    @property
    def name(self) -> str: ...

    def scan(self) -> list[AppEntry]: ...

    def launch(self, app: AppEntry) -> None: ...

    def get_icon(self, app: AppEntry) -> Path | None: ...

    def is_available(self) -> bool: ...
