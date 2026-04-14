"""TileGrid — scrollable grid of GameTile widgets with 2-D keyboard navigation."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtWidgets import QScrollArea, QWidget

from pixiis.core.types import AppEntry
from pixiis.ui.widgets.flow_layout import FlowLayout
from pixiis.ui.widgets.game_tile import DEFAULT_TILE_HEIGHT, DEFAULT_TILE_WIDTH, GameTile


class TileGrid(QScrollArea):
    """Scrollable area containing a FlowLayout of GameTile widgets."""

    tile_activated = Signal(object)  # forwards GameTile.activated

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._container = QWidget()
        self._layout = FlowLayout(self._container, h_spacing=20, v_spacing=20)
        self._container.setLayout(self._layout)
        self.setWidget(self._container)

        self._tiles: list[GameTile] = []
        self._focused_index: int = -1

        # Smooth scroll animation
        self._scroll_anim = QPropertyAnimation(
            self.verticalScrollBar(), b"value", self
        )
        self._scroll_anim.setDuration(200)
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
        self.clear()
        for app in apps:
            tile = GameTile(app, parent=self._container)
            tile.activated.connect(self.tile_activated.emit)
            tile.tile_focused.connect(self._on_tile_focused)
            self._tiles.append(tile)
            self._layout.addWidget(tile)

            if image_loader is not None and app.art_url:
                # Connect the loader once per tile using a closure.
                _connect_loader(tile, app.art_url, image_loader)

        if self._tiles:
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
        """Remove all tiles from the grid."""
        self._layout.clear()
        self._tiles.clear()
        self._focused_index = -1

    def get_columns_count(self) -> int:
        """How many tiles fit in one row at the current width."""
        avail = self._container.width()
        col_w = DEFAULT_TILE_WIDTH + self._layout.horizontal_spacing()
        return max(1, avail // col_w)

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

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_tile_focused(self, app: AppEntry) -> None:
        for i, tile in enumerate(self._tiles):
            if tile.app is app:
                self._focused_index = i
                self._smooth_scroll_to(tile)
                break

    def _smooth_scroll_to(self, widget: QWidget) -> None:
        """Ensure *widget* is visible with a smooth scroll animation."""
        # Map widget position to scroll area coordinates.
        y = widget.mapTo(self._container, widget.rect().topLeft()).y()
        bar = self.verticalScrollBar()
        viewport_h = self.viewport().height()

        target = y - viewport_h // 3  # show tile in upper third
        target = max(0, min(target, bar.maximum()))

        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(bar.value())
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()

    def _rebuild_layout(self) -> None:
        """Re-add tiles to the layout in their current order."""
        # Detach without destroying widgets.
        while self._layout.count():
            self._layout.takeAt(0)
        for tile in self._tiles:
            self._layout.addWidget(tile)
        self._container.updateGeometry()


def _connect_loader(tile: GameTile, url: str, loader) -> None:
    """Wire *loader.image_ready* to deliver the pixmap for *url* to *tile*."""

    def _on_image(loaded_url, pixmap):
        if loaded_url == url:
            tile.set_image(pixmap)

    loader.request(url)
    loader.image_ready.connect(_on_image)
