"""Wrapping flow layout — items flow left-to-right and wrap to the next row."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QWidget


class FlowLayout(QLayout):
    """Custom layout that arranges child widgets left-to-right, wrapping rows."""

    def __init__(
        self,
        parent: QWidget | None = None,
        h_spacing: int = 16,
        v_spacing: int = 16,
    ) -> None:
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items: list[QLayoutItem] = []

    # ── QLayout interface ───────────────────────────────────────────────────

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    # ── Spacing helpers ─────────────────────────────────────────────────────

    def horizontal_spacing(self) -> int:
        return self._h_spacing

    def vertical_spacing(self) -> int:
        return self._v_spacing

    # ── Core layout algorithm ───────────────────────────────────────────────

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """Position items within *rect*.  Returns the total height used.

        When *test_only* is True, items are not moved — only the height is
        calculated (used by heightForWidth).
        """
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())

        x = effective.x()
        y = effective.y()
        row_height = 0

        for item in self._items:
            widget = item.widget()
            if widget is not None and not widget.isVisible():
                continue

            item_size = item.sizeHint()
            next_x = x + item_size.width() + self._h_spacing

            # Wrap to next row if the item exceeds the available width.
            if next_x - self._h_spacing > effective.right() + 1 and row_height > 0:
                x = effective.x()
                y += row_height + self._v_spacing
                next_x = x + item_size.width() + self._h_spacing
                row_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))

            x = next_x
            row_height = max(row_height, item_size.height())

        return y + row_height - rect.y() + margins.bottom()

    # ── Utilities ───────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove and delete all items and their widgets."""
        while self._items:
            item = self._items.pop()
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def widgets(self) -> list[QWidget]:
        """Return a list of all managed widgets."""
        return [item.widget() for item in self._items if item.widget() is not None]
