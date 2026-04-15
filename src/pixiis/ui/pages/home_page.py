"""Home page — refined landing with Dark Cinema aesthetic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
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


# ── Dark Cinema palette v2 ─────────────────────────────────────────────────

_SURFACE = "#13121a"
_ACCENT = "#e94560"
_TEXT_SECONDARY = "#8a8698"
_TEXT_MUTED = "#5c586a"


# ── Sort pill button ───────────────────────────────────────────────────────


class _SortPill(QWidget):
    """Custom-painted pill toggle button."""

    clicked = Signal()

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self._checked = False
        self._hovered = False
        self.setFixedHeight(32)
        self.setMinimumWidth(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

    def isChecked(self) -> bool:  # noqa: N802
        return self._checked

    def setChecked(self, val: bool) -> None:  # noqa: N802
        self._checked = val
        self.update()

    def sizeHint(self):  # noqa: N802
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self._text)
        return self.minimumSize().expandedTo(
            type(self.minimumSize())(text_w + 28, 32)
        )

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        focused = self.hasFocus()

        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, float(w) - 1.0, float(h) - 1.0, 16.0, 16.0)

        if self._checked:
            # Active pill: accent-tinted bg
            p.fillPath(path, QColor(233, 69, 96, 38))  # rgba(accent, 0.15)
            p.setPen(QPen(QColor(233, 69, 96, 77), 1.0))  # accent 0.30 border
            p.drawPath(path)
            p.setPen(QColor(_ACCENT))
        elif focused:
            # Focus: accent border ring
            p.fillPath(path, QColor(233, 69, 96, 20))
            p.setPen(QPen(QColor(233, 69, 96, 77), 1.0))
            p.drawPath(path)
            p.setPen(QColor(_ACCENT))
        elif self._hovered:
            p.fillPath(path, QColor(37, 35, 48))  # surface_hover
            p.setPen(QPen(QColor(255, 255, 255, 15), 1.0))
            p.drawPath(path)
            p.setPen(QColor("#f0eef5"))
        else:
            p.fillPath(path, QColor(_SURFACE))
            p.setPen(QPen(QColor(255, 255, 255, 15), 1.0))  # border
            p.drawPath(path)
            p.setPen(QColor(_TEXT_SECONDARY))

        font = QFont()
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Medium)
        p.setFont(font)
        p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()


# ── HomePage ────────────────────────────────────────────────────────────────


class HomePage(QWidget):
    """Default landing page — search bar, A-Z / Recent sort pills, tile grid.

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
        root.setContentsMargins(32, 24, 32, 16)
        root.setSpacing(24)

        # -- top bar ----------------------------------------------------------
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        # search bar (stretches)
        if SearchBar is not None:
            self._search = SearchBar()
            self._search.search_changed.connect(self._on_search)
            top_bar.addWidget(self._search, stretch=1)
        else:
            self._search = None
            top_bar.addStretch(1)

        # sort pills
        self._btn_az = _SortPill("A-Z")
        self._btn_az.setChecked(True)
        self._btn_az.setFixedWidth(56)
        self._btn_az.clicked.connect(lambda: self._set_sort("az"))
        top_bar.addWidget(self._btn_az)

        self._btn_recent = _SortPill("Recent")
        self._btn_recent.setFixedWidth(72)
        self._btn_recent.clicked.connect(lambda: self._set_sort("recent"))
        top_bar.addWidget(self._btn_recent)

        self._sort_pills = [self._btn_az, self._btn_recent]

        root.addLayout(top_bar)

        # -- tile grid --------------------------------------------------------
        if TileGrid is not None:
            self._grid = TileGrid()
            if hasattr(self._grid, "tile_activated"):
                self._grid.tile_activated.connect(self._on_tile_activated)
            root.addWidget(self._grid, stretch=1)
        else:
            self._grid = None
            root.addStretch(1)

        # -- loading indicator ---------------------------------------------------
        self._loading = QLabel("Scanning your library...")
        self._loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading.setStyleSheet("color: #5c586a; font-size: 16px; padding: 40px; background: transparent;")
        root.addWidget(self._loading)

        # -- initial load -----------------------------------------------------
        self._load_apps()

    # -- public API -----------------------------------------------------------

    def refresh(self, apps: list[AppEntry] | None = None) -> None:
        """Refresh the tile grid with an updated app list."""
        if hasattr(self, '_loading') and self._loading.isVisible():
            self._loading.hide()
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
        for pill in self._sort_pills:
            pill.setChecked(False)
        if mode == "az":
            self._btn_az.setChecked(True)
        else:
            self._btn_recent.setChecked(True)
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
            self._grid.set_apps(sorted_apps, image_loader=self._image_loader)

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
            self._grid.set_apps(sorted_apps, image_loader=self._image_loader)

    def _on_tile_activated(self, app: object) -> None:
        self.game_selected.emit(app)
