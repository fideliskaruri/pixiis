"""TileGrid — scrollable grid of GameTile widgets with 2-D keyboard navigation."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QWidget

from pixiis.core.types import AppEntry
from pixiis.ui.widgets.flow_layout import FlowLayout
from pixiis.ui.widgets.game_tile import DEFAULT_TILE_HEIGHT, DEFAULT_TILE_WIDTH, GameTile

# Grid spacing — 20px gaps per design spec v2
H_SPACING = 20
V_SPACING = 20


class TileGrid(QScrollArea):
    """Scrollable area containing a FlowLayout of GameTile widgets.

    Image loading uses the **single dispatcher** pattern: one connection to
    ``image_ready`` for the lifetime of this widget, with a ``{url: tile}``
    dict that is cleared on every rebuild. This gives O(1) signal overhead,
    zero accumulation, and clean invalidation of stale downloads.
    """

    tile_activated = Signal(object)  # forwards GameTile.activated

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._container = QWidget()
        self._layout = FlowLayout(self._container, h_spacing=H_SPACING, v_spacing=V_SPACING)
        self._container.setLayout(self._layout)
        self.setWidget(self._container)

        self._tiles: list[GameTile] = []
        self._focused_index: int = -1

        # Image loading — single dispatcher pattern
        self._url_to_tile: dict[str, GameTile] = {}
        self._loader = None
        self._loader_connected = False

        # Smooth scroll animation
        self._scroll_anim = QPropertyAnimation(
            self.verticalScrollBar(), b"value", self
        )
        self._scroll_anim.setDuration(300)
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── Public API ──────────────────────────────────────────────────────────

    def set_apps(
        self,
        apps: list[AppEntry],
        image_loader=None,
    ) -> None:
        """Populate the grid with tiles for each *app*.

        If *image_loader* is provided it must be a QObject with:
          - ``request(url: str)`` method
          - ``image_ready(str, QPixmap)`` signal
        """
        prev_focus = QApplication.focusWidget()
        self.clear()

        # One-time connection to the image loader (never accumulates)
        if image_loader is not None and not self._loader_connected:
            self._loader = image_loader
            image_loader.image_ready.connect(self._on_image_ready)
            self._loader_connected = True

        if not apps:
            empty = QLabel(
                "No games found.\nCheck Settings \u2192 Library to configure providers,\n"
                "or add games manually in config.toml"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                "color: #8a8698; font-size: 15px; padding: 60px; background: transparent;"
            )
            empty.setWordWrap(True)
            self._layout.addWidget(empty)
            return

        for app in apps:
            tile = GameTile(app, parent=self._container)
            tile.activated.connect(self.tile_activated.emit)
            tile.tile_focused.connect(self._on_tile_focused)
            self._tiles.append(tile)
            self._layout.addWidget(tile)

            if image_loader is not None and app.art_url:
                self._url_to_tile[app.art_url] = tile
                image_loader.request(app.art_url)
            elif app.icon_path:
                # Fallback: load local icon (Xbox/UWP apps, etc.)
                icon_file = app.icon_path
                if not icon_file.exists():
                    # Try scale variants common in UWP/Xbox packages
                    for scale in ("scale-200", "scale-100", "scale-150"):
                        variant = icon_file.parent / f"{icon_file.stem}.{scale}{icon_file.suffix}"
                        if variant.exists():
                            icon_file = variant
                            break
                if icon_file.exists():
                    pixmap = QPixmap(str(icon_file))
                    if not pixmap.isNull():
                        tile.set_image(pixmap)

        # Restore focus: keep previous widget focused if still valid, otherwise first tile
        if prev_focus is not None and not prev_focus.isHidden():
            if prev_focus.focusPolicy() != Qt.FocusPolicy.NoFocus:
                prev_focus.setFocus()
            elif self._tiles:
                self._tiles[0].setFocus()
        elif self._tiles:
            self._tiles[0].setFocus()

    def set_sort_order(self, order: str) -> None:
        """Re-sort tiles in-place.  ``"az"`` = alphabetical, ``"recent"`` = last played."""
        if order == "az":
            self._tiles.sort(key=lambda t: t.app.display_name.lower())
        elif order == "recent":
            self._tiles.sort(
                key=lambda t: t.app.metadata.get("last_played", 0),
                reverse=True,
            )
        self._rebuild_layout()

    def clear(self) -> None:
        """Remove all tiles from the grid.

        Clears the url→tile dispatch dict so in-flight downloads for old
        tiles harmlessly no-op when they arrive.
        """
        self._url_to_tile.clear()
        self._layout.clear()
        self._tiles.clear()
        self._focused_index = -1

    def get_columns_count(self) -> int:
        """How many tiles fit in one row at the current width."""
        avail = self._container.width()
        col_w = DEFAULT_TILE_WIDTH + H_SPACING
        return max(1, avail // col_w)

    # ── Image delivery (single dispatcher) ─────────────────────────────────

    def _on_image_ready(self, url: str, pixmap) -> None:
        """Deliver a downloaded image to the tile that requested it.

        If the tile was destroyed by a grid rebuild, ``dict.pop`` returns
        ``None`` and we skip delivery. The ``try/except`` is a belt-and-
        suspenders guard for the edge case where ``deleteLater()`` runs
        between the dict check and the ``set_image`` call.
        """
        tile = self._url_to_tile.pop(url, None)
        if tile is not None:
            try:
                tile.set_image(pixmap)
            except RuntimeError:
                pass  # C++ object already deleted — safe to ignore

    # ── 2-D keyboard navigation ─────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        cols = self.get_columns_count()
        total = len(self._tiles)

        if total == 0 or self._focused_index < 0:
            super().keyPressEvent(event)
            return

        idx = self._focused_index
        new_idx: int | None = None

        if key == Qt.Key.Key_Right:
            new_idx = idx + 1 if idx + 1 < total else None
        elif key == Qt.Key.Key_Left:
            new_idx = idx - 1 if idx - 1 >= 0 else None
        elif key == Qt.Key.Key_Down:
            candidate = idx + cols
            new_idx = candidate if candidate < total else None
        elif key == Qt.Key.Key_Up:
            candidate = idx - cols
            new_idx = candidate if candidate >= 0 else None
        else:
            super().keyPressEvent(event)
            return

        if new_idx is not None:
            self._tiles[new_idx].setFocus()
        else:
            # At grid boundary — escape in the appropriate direction
            if key == Qt.Key.Key_Up:
                self.focusPreviousChild()
            elif key == Qt.Key.Key_Down:
                self.focusNextChild()
            else:
                event.ignore()

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_tile_focused(self, app: AppEntry) -> None:
        for i, tile in enumerate(self._tiles):
            if tile.app is app:
                self._focused_index = i
                self._scroll_to_tile(tile)
                break

    def _scroll_to_tile(self, widget: QWidget) -> None:
        """Smoothly scroll so *widget* is fully visible in the viewport."""
        # Use ensureWidgetVisible first for reliability, then animate
        self.ensureWidgetVisible(widget, 50, 50)

        # Now do an animated scroll to center the tile nicely
        # Get tile position relative to the scrollable content widget
        content = self.widget()
        if content is None:
            return
        pos = widget.mapTo(content, widget.rect().topLeft())
        tile_top = pos.y()
        tile_bottom = tile_top + widget.height()

        bar = self.verticalScrollBar()
        vp_h = self.viewport().height()
        vp_top = bar.value()
        vp_bottom = vp_top + vp_h

        # If tile is already fully visible, no animation needed
        if tile_top >= vp_top + 20 and tile_bottom <= vp_bottom - 20:
            return

        # Scroll to put the tile in the upper third of the viewport
        target = max(0, tile_top - vp_h // 4)
        target = min(target, bar.maximum())

        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(bar.value())
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()

    def _rebuild_layout(self) -> None:
        """Re-add tiles to the layout in their current order."""
        while self._layout.count():
            self._layout.takeAt(0)
        for tile in self._tiles:
            self._layout.addWidget(tile)
        self._container.updateGeometry()
