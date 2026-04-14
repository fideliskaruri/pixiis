"""Home page — default landing with search, sort, and tile grid."""

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

_SORT_BTN_STYLE = (
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


# ── HomePage ────────────────────────────────────────────────────────────────


class HomePage(QWidget):
    """Default landing page — search bar, A-Z / Recent sort, tile grid.

    Parameters
    ----------
    registry : AppRegistry
        The central app registry.
    image_loader : object | None
        An ``AsyncImageLoader`` (or compatible) used by the tile grid.
    services : dict | None
        Optional mapping of service clients (RawgClient, YouTubeClient, etc.).
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
        self._current_sort = "az"
        self._all_apps: list[AppEntry] = []

        self.setObjectName("HomePage")
        self.setStyleSheet("#HomePage { background-color: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(12)

        # -- top bar ----------------------------------------------------------
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        # search bar
        if SearchBar is not None:
            self._search = SearchBar()
            self._search.search_changed.connect(self._on_search)
            top_bar.addWidget(self._search, stretch=1)
        else:
            self._search = None
            top_bar.addStretch(1)

        # sort buttons
        self._sort_group = QButtonGroup(self)
        self._sort_group.setExclusive(True)

        self._btn_az = QPushButton("A-Z")
        self._btn_az.setCheckable(True)
        self._btn_az.setChecked(True)
        self._btn_az.setStyleSheet(_SORT_BTN_STYLE)
        self._sort_group.addButton(self._btn_az)
        top_bar.addWidget(self._btn_az)

        self._btn_recent = QPushButton("Recent")
        self._btn_recent.setCheckable(True)
        self._btn_recent.setStyleSheet(_SORT_BTN_STYLE)
        self._sort_group.addButton(self._btn_recent)
        top_bar.addWidget(self._btn_recent)

        self._btn_az.clicked.connect(lambda: self._set_sort("az"))
        self._btn_recent.clicked.connect(lambda: self._set_sort("recent"))

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
        self._load_apps()

    # -- public API -----------------------------------------------------------

    def refresh(self, apps: list[AppEntry] | None = None) -> None:
        """Refresh the tile grid with an updated app list."""
        if apps is not None:
            self._all_apps = list(apps)
        elif self._registry is not None:
            self._all_apps = self._registry.get_all()
        self._apply_sort_and_display()

    # -- internals ------------------------------------------------------------

    def _load_apps(self) -> None:
        if self._registry is not None:
            self._all_apps = self._registry.get_all()
        self._apply_sort_and_display()

    def _set_sort(self, mode: str) -> None:
        self._current_sort = mode
        self._apply_sort_and_display()

    def _sorted_apps(self, apps: list[AppEntry]) -> list[AppEntry]:
        if self._current_sort == "recent":
            return sorted(
                apps,
                key=lambda a: a.metadata.get("last_played", 0),
                reverse=True,
            )
        return sorted(apps, key=lambda a: a.name.lower())

    def _apply_sort_and_display(self) -> None:
        sorted_apps = self._sorted_apps(self._all_apps)
        if self._grid is not None and hasattr(self._grid, "set_apps"):
            self._grid.set_apps(sorted_apps)

    def _on_search(self, query: str) -> None:
        if not query.strip():
            self._all_apps = (
                self._registry.get_all() if self._registry else []
            )
            self._apply_sort_and_display()
            return
        if self._registry is not None:
            results = self._registry.search(query)
        else:
            q = query.lower()
            results = [a for a in self._all_apps if q in a.name.lower()]
        sorted_apps = self._sorted_apps(results)
        if self._grid is not None and hasattr(self._grid, "set_apps"):
            self._grid.set_apps(sorted_apps)

    def _on_tile_activated(self, app: object) -> None:
        self.game_selected.emit(app)
