"""Home page — refined landing with Dark Cinema aesthetic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from pixiis.core.types import AppEntry
    from pixiis.library.registry import AppRegistry

# Widgets built by another agent — may not exist yet.
try:
    from pixiis.ui.widgets import SearchBar, TileGrid
    from pixiis.ui.widgets.game_tile import GameTile
except ImportError:
    SearchBar = None  # type: ignore[assignment,misc]
    TileGrid = None  # type: ignore[assignment,misc]
    GameTile = None  # type: ignore[assignment,misc]


# ── Dark Cinema palette v2 ─────────────────────────────────────────────────

_SURFACE = "#13121a"
_ACCENT = "#e94560"
_TEXT_SECONDARY = "#8a8698"
_TEXT_MUTED = "#7a7690"

# ── Pre-built fonts (avoid re-creating in paintEvent) ─────────────────────

_PILL_FONT = QFont()
_PILL_FONT.setPixelSize(12)
_PILL_FONT.setWeight(QFont.Weight.Medium)

_SECTION_FONT = QFont()
_SECTION_FONT.setPixelSize(14)
_SECTION_FONT.setWeight(QFont.Weight.Bold)
_SECTION_FONT.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)

# Recently played carousel constants
_CAROUSEL_TILE_W = 280
_CAROUSEL_TILE_H = 160
_CAROUSEL_MAX_ITEMS = 5


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

        # Always reserve 2px border — use inset rect so border doesn't shift
        path = QPainterPath()
        path.addRoundedRect(1.0, 1.0, float(w) - 2.0, float(h) - 2.0, 15.0, 15.0)

        # Step 1: Background fill
        if self._checked:
            p.fillPath(path, QColor(233, 69, 96, 38))  # rgba(accent, 0.15)
        elif focused:
            p.fillPath(path, QColor(233, 69, 96, 20))
        elif self._hovered:
            p.fillPath(path, QColor(37, 35, 48))  # surface_hover
        else:
            p.fillPath(path, QColor(_SURFACE))

        # Step 2: Border — always 2px, only color changes
        if focused:
            # Focused (whether checked or not): solid accent border
            p.setPen(QPen(QColor(_ACCENT), 2.0))
        elif self._checked:
            # Checked but not focused: subtle accent border
            p.setPen(QPen(QColor(233, 69, 96, 77), 2.0))
        elif self._hovered:
            p.setPen(QPen(QColor(255, 255, 255, 15), 2.0))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 15), 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Step 3: Text color
        if self._checked or focused:
            p.setPen(QColor(_ACCENT))
        elif self._hovered:
            p.setPen(QColor("#f0eef5"))
        else:
            p.setPen(QColor(_TEXT_SECONDARY))

        p.setFont(_PILL_FONT)
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
    mic_clicked = Signal()   # forwarded from search bar
    mic_stopped = Signal()   # forwarded from search bar

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
            if hasattr(self._search, 'mic_clicked'):
                self._search.mic_clicked.connect(self.mic_clicked)
            if hasattr(self._search, 'mic_stopped'):
                self._search.mic_stopped.connect(self.mic_stopped)
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

        # -- "Continue Playing" carousel (recently played) --------------------
        self._carousel_label = QLabel("CONTINUE PLAYING")
        self._carousel_label.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: bold; "
            "letter-spacing: 2px; background: transparent; margin-bottom: 0px;"
        )
        self._carousel_label.setFont(_SECTION_FONT)
        self._carousel_label.hide()
        root.addWidget(self._carousel_label)

        self._carousel_scroll = QScrollArea()
        self._carousel_scroll.setFixedHeight(_CAROUSEL_TILE_H + 16)
        self._carousel_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._carousel_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._carousel_scroll.setWidgetResizable(True)
        self._carousel_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        self._carousel_scroll.hide()

        self._carousel_container = QWidget()
        self._carousel_layout = QHBoxLayout(self._carousel_container)
        self._carousel_layout.setContentsMargins(0, 0, 0, 0)
        self._carousel_layout.setSpacing(16)
        self._carousel_scroll.setWidget(self._carousel_container)

        root.addWidget(self._carousel_scroll)

        self._carousel_tiles: list[object] = []
        self._carousel_url_to_tile: dict[str, object] = {}

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
        self._loading.setStyleSheet("color: #7a7690; font-size: 14px; padding: 40px; background: transparent;")
        self._loading.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self._loading.setFixedHeight(60)
        root.addWidget(self._loading)

        # -- initial load -----------------------------------------------------
        self._load_apps()

    # -- public API -----------------------------------------------------------

    def set_search_text(self, text: str) -> None:
        """Set the search bar text and trigger the search signal."""
        if self._search is not None:
            self._search.setText(text)
            self._search.search_changed.emit(text)

    def focus_search(self) -> None:
        """Give keyboard focus to the search bar."""
        if self._search is not None:
            self._search.setFocus()

    def set_mic_recording(self, active: bool) -> None:
        """Update the search bar mic icon to show recording state."""
        if self._search is not None and hasattr(self._search, 'set_mic_recording'):
            self._search.set_mic_recording(active)

    def refresh(self, apps: list[AppEntry] | None = None) -> None:
        """Refresh the tile grid with an updated app list (games only)."""
        if hasattr(self, '_loading') and self._loading.isVisible():
            self._loading.hide()
        if apps is not None:
            self._all_apps = [a for a in apps if a.is_game]
        elif self._registry is not None:
            self._all_apps = [a for a in self._registry.get_all() if a.is_game]
        self._apply_sort_and_display()

    # -- internals ------------------------------------------------------------

    def _load_apps(self) -> None:
        if self._registry is not None:
            self._all_apps = [a for a in self._registry.get_all() if a.is_game]
        # Connect image loader for carousel (one-time)
        if (
            self._image_loader is not None
            and hasattr(self._image_loader, "image_ready")
            and not getattr(self, "_carousel_loader_connected", False)
        ):
            self._image_loader.image_ready.connect(self._on_carousel_image_ready)
            self._carousel_loader_connected = True
        if self._all_apps:
            self._loading.hide()
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
                key=lambda a: (not a.is_favorite, -a.metadata.get("last_played", 0)),
            )
        return sorted(apps, key=lambda a: (not a.is_favorite, a.name.lower()))

    def _apply_sort_and_display(self) -> None:
        sorted_apps = self._sorted_apps(self._all_apps)
        if self._grid is not None and hasattr(self._grid, "set_apps"):
            self._grid.set_apps(sorted_apps, image_loader=self._image_loader)
        self._rebuild_carousel()

    def _rebuild_carousel(self) -> None:
        """Rebuild the 'Continue Playing' carousel with recently played games."""
        # Clear existing carousel tiles
        while self._carousel_layout.count():
            item = self._carousel_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._carousel_tiles.clear()
        self._carousel_url_to_tile.clear()

        # Get recently played games (last_played > 0), sorted by most recent
        recent = sorted(
            [a for a in self._all_apps if a.last_played > 0],
            key=lambda a: a.last_played,
            reverse=True,
        )[:_CAROUSEL_MAX_ITEMS]

        if not recent or GameTile is None:
            self._carousel_label.hide()
            self._carousel_scroll.hide()
            return

        self._carousel_label.show()
        self._carousel_scroll.show()

        for app in recent:
            tile = GameTile(
                app,
                width=_CAROUSEL_TILE_W,
                height=_CAROUSEL_TILE_H,
                parent=self._carousel_container,
            )
            tile.activated.connect(self._on_tile_activated)
            self._carousel_tiles.append(tile)
            self._carousel_layout.addWidget(tile)

            # Request art for carousel tiles
            if self._image_loader is not None and app.art_url:
                self._carousel_url_to_tile[app.art_url] = tile
                self._image_loader.request(app.art_url)
            elif app.icon_path and app.icon_path.exists():
                pixmap = QPixmap(str(app.icon_path))
                if not pixmap.isNull():
                    tile.set_image(pixmap)

        self._carousel_layout.addStretch()

    def _on_carousel_image_ready(self, url: str, pixmap: QPixmap) -> None:
        """Deliver downloaded images to carousel tiles."""
        tile = self._carousel_url_to_tile.pop(url, None)
        if tile is not None:
            try:
                tile.set_image(pixmap)
            except RuntimeError:
                pass

    def _on_search(self, query: str) -> None:
        if not query.strip():
            self._all_apps = (
                [a for a in self._registry.get_all() if a.is_game]
                if self._registry else []
            )
            self._apply_sort_and_display()
            return
        if self._registry is not None:
            results = [a for a in self._registry.search(query) if a.is_game]
        else:
            q = query.lower()
            results = [a for a in self._all_apps if q in a.name.lower()]
        sorted_apps = self._sorted_apps(results)
        if self._grid is not None and hasattr(self._grid, "set_apps"):
            self._grid.set_apps(
                sorted_apps,
                image_loader=self._image_loader,
                empty_message="No matching games",
            )

    def _on_tile_activated(self, app: object) -> None:
        self.game_selected.emit(app)
