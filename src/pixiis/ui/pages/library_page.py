"""Library page — full library with source filtering and search."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pixiis.core.types import AppSource

if TYPE_CHECKING:
    from pixiis.core.types import AppEntry
    from pixiis.library.registry import AppRegistry

# Widgets built by another agent — may not exist yet.
try:
    from pixiis.ui.widgets import SearchBar, TileGrid
except ImportError:
    SearchBar = None  # type: ignore[assignment,misc]
    TileGrid = None  # type: ignore[assignment,misc]


# ── Style constants ─────────────────────────────────────────────────────────

_FILTER_BTN_STYLE = (
    "QPushButton {"
    "  background-color: #16213e;"
    "  color: #a0a0b0;"
    "  border: 1px solid #0f3460;"
    "  border-radius: 4px;"
    "  padding: 6px 14px;"
    "  font-size: 13px;"
    "}"
    "QPushButton:hover {"
    "  background-color: #0f3460;"
    "  color: #e0e0e0;"
    "}"
    "QPushButton:checked {"
    "  background-color: #e94560;"
    "  color: #ffffff;"
    "  border: none;"
    "  font-weight: bold;"
    "}"
)

# Maps UI label → source filter spec.
# None means "all", a list means union of those sources.
_FILTER_MAP: dict[str, list[AppSource] | None] = {
    "All": None,
    "Steam": [AppSource.STEAM],
    "Xbox": [AppSource.XBOX],
    "Apps": [AppSource.STARTMENU, AppSource.MANUAL],
}


# ── LibraryPage ─────────────────────────────────────────────────────────────


class LibraryPage(QWidget):
    """Full library view with source filter tabs and search.

    Parameters
    ----------
    registry : AppRegistry
        The central app registry.
    image_loader : object | None
        An ``AsyncImageLoader`` (or compatible) used by the tile grid.
    services : dict | None
        Optional mapping of service clients.
    """

    game_selected = Signal(object)  # AppEntry

    def __init__(
        self,
        registry: AppRegistry | None = None,
        image_loader: object | None = None,
        services: dict | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry
        self._image_loader = image_loader
        self._services = services or {}
        self._active_filter: str = "All"
        self._search_query: str = ""

        self.setObjectName("LibraryPage")
        self.setStyleSheet("#LibraryPage { background-color: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(12)

        # -- top bar ----------------------------------------------------------
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        # filter tabs
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_buttons: dict[str, QPushButton] = {}

        for label in _FILTER_MAP:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(_FILTER_BTN_STYLE)
            if label == "All":
                btn.setChecked(True)
            btn.clicked.connect(lambda _checked, _l=label: self._set_filter(_l))
            self._filter_group.addButton(btn)
            self._filter_buttons[label] = btn
            top_bar.addWidget(btn)

        top_bar.addStretch(1)

        # search bar
        if SearchBar is not None:
            self._search = SearchBar()
            self._search.search_changed.connect(self._on_search)
            top_bar.addWidget(self._search)
        else:
            self._search = None

        root.addLayout(top_bar)

        # -- tile grid --------------------------------------------------------
        if TileGrid is not None:
            self._grid = TileGrid(image_loader=image_loader)
            if hasattr(self._grid, "tile_activated"):
                self._grid.tile_activated.connect(self._on_tile_activated)
            root.addWidget(self._grid, stretch=1)
        else:
            self._grid = None
            root.addStretch(1)

        # -- initial load -----------------------------------------------------
        self._apply_filter_and_display()

    # -- public API -----------------------------------------------------------

    def refresh(self, apps: list[AppEntry] | None = None) -> None:
        """Re-apply current filter against latest data."""
        self._apply_filter_and_display()

    # -- internals ------------------------------------------------------------

    def _set_filter(self, label: str) -> None:
        self._active_filter = label
        self._apply_filter_and_display()

    def _filtered_apps(self) -> list[AppEntry]:
        """Return apps matching the current source filter."""
        if self._registry is None:
            return []

        sources = _FILTER_MAP.get(self._active_filter)
        if sources is None:
            apps = self._registry.get_all()
        else:
            apps = []
            for src in sources:
                apps.extend(self._registry.filter_by_source(src))

        # Apply search within filter
        if self._search_query:
            q = self._search_query.lower()
            apps = [a for a in apps if q in a.name.lower()]

        # Always A-Z
        return sorted(apps, key=lambda a: a.name.lower())

    def _apply_filter_and_display(self) -> None:
        apps = self._filtered_apps()
        if self._grid is not None and hasattr(self._grid, "set_apps"):
            self._grid.set_apps(apps)

    def _on_search(self, query: str) -> None:
        self._search_query = query.strip()
        self._apply_filter_and_display()

    def _on_tile_activated(self, app: object) -> None:
        self.game_selected.emit(app)
