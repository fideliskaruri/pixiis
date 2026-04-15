"""Library page — refined library with Dark Cinema aesthetic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QHBoxLayout,
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


# ── Dark Cinema palette v2 ─────────────────────────────────────────────────

_SURFACE = "#13121a"
_ACCENT = "#e94560"
_TEXT_SECONDARY = "#8a8698"
_TEXT_MUTED = "#5c586a"

# Maps UI label → source filter spec.
# None means "all", a list means union of those sources.
_FILTER_MAP: dict[str, list[AppSource] | None] = {
    "All": None,
    "Steam": [AppSource.STEAM],
    "Xbox": [AppSource.XBOX],
    "Apps": [AppSource.STARTMENU, AppSource.MANUAL],
}


# ── Filter pill button ─────────────────────────────────────────────────────


class _FilterPill(QWidget):
    """Custom-painted pill toggle for source filtering."""

    clicked = Signal()

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self._checked = False
        self._hovered = False
        self.setFixedHeight(32)
        self.setMinimumWidth(52)
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
            p.fillPath(path, QColor(233, 69, 96, 38))  # rgba(accent, 0.15)
            p.setPen(QPen(QColor(233, 69, 96, 77), 1.0))
            p.drawPath(path)
            p.setPen(QColor(_ACCENT))
        elif focused:
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
            p.setPen(QPen(QColor(255, 255, 255, 15), 1.0))
            p.drawPath(path)
            p.setPen(QColor(_TEXT_SECONDARY))

        font = QFont()
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Medium)
        p.setFont(font)
        p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()


# ── LibraryPage ─────────────────────────────────────────────────────────────


class LibraryPage(QWidget):
    """Full library view with source filter pills and search.

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
        root.setContentsMargins(32, 24, 32, 16)
        root.setSpacing(24)

        # -- top bar ----------------------------------------------------------
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # filter pills (left)
        self._filter_pills: dict[str, _FilterPill] = {}
        for label in _FILTER_MAP:
            pill = _FilterPill(label)
            pill.setFixedWidth(max(52, len(label) * 10 + 20))
            if label == "All":
                pill.setChecked(True)
            pill.clicked.connect(lambda _l=label: self._set_filter(_l))
            self._filter_pills[label] = pill
            top_bar.addWidget(pill)

        top_bar.addStretch(1)

        # search bar (right)
        if SearchBar is not None:
            self._search = SearchBar()
            self._search.search_changed.connect(self._on_search)
            top_bar.addWidget(self._search)
        else:
            self._search = None

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

        # -- initial load -----------------------------------------------------
        self._apply_filter_and_display()

    # -- public API -----------------------------------------------------------

    def refresh(self, apps: list[AppEntry] | None = None) -> None:
        """Re-apply current filter against latest data."""
        self._apply_filter_and_display()

    # -- internals ------------------------------------------------------------

    def _set_filter(self, label: str) -> None:
        self._active_filter = label
        for name, pill in self._filter_pills.items():
            pill.setChecked(name == label)
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
            self._grid.set_apps(apps, image_loader=self._image_loader)

    def _on_search(self, query: str) -> None:
        self._search_query = query.strip()
        self._apply_filter_and_display()

    def _on_tile_activated(self, app: object) -> None:
        self.game_selected.emit(app)
