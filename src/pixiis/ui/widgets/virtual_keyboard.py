"""On-screen virtual keyboard for controller input into text fields."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLineEdit, QWidget

# ── Dark Cinema palette ───────────────────────────────────────────────────

_BG = QColor(19, 18, 26, 240)           # surface @ 94%
_KEY_BG = QColor(37, 35, 48)            # surface_hover
_KEY_SELECTED = QColor("#e94560")        # accent
_KEY_TEXT = QColor("#f0eef5")            # text_primary
_KEY_TEXT_DIM = QColor("#8a8698")        # text_secondary
_BORDER = QColor(255, 255, 255, 15)

# ── Fonts ────────────────────────────────────────────────────────────────

_KEY_FONT = QFont()
_KEY_FONT.setPixelSize(16)
_KEY_FONT.setBold(True)

_SPECIAL_FONT = QFont()
_SPECIAL_FONT.setPixelSize(12)
_SPECIAL_FONT.setBold(True)

# ── Layout ───────────────────────────────────────────────────────────────

_ROWS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
    ["SPACE", "BKSP", "ENTER"],
]

_KEY_W = 48
_KEY_H = 44
_KEY_GAP = 4
_PADDING = 16


class VirtualKeyboard(QWidget):
    """Flat dark on-screen keyboard overlay for controller text input.

    D-pad navigates, A selects a key, B closes. Each key is a painted
    rectangle -- no QPushButtons involved.
    """

    text_submitted = Signal(str)  # emitted on Enter
    dismissed = Signal()          # emitted on B press / dismiss

    def __init__(self, target: QLineEdit | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target = target
        self._row = 0
        self._col = 0
        self._buffer: list[str] = []

        if target is not None:
            self._buffer = list(target.text())

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Calculate total size
        max_cols = max(len(r) for r in _ROWS)
        total_w = _PADDING * 2 + max_cols * (_KEY_W + _KEY_GAP) - _KEY_GAP
        total_h = _PADDING * 2 + len(_ROWS) * (_KEY_H + _KEY_GAP) - _KEY_GAP
        self.setFixedSize(total_w, total_h)

        self.hide()

    # -- public API ----------------------------------------------------------

    def show_at(self, x: int, y: int) -> None:
        """Position and show the keyboard overlay."""
        self.move(x, y)
        self.show()
        self.raise_()
        self.setFocus()

    def set_target(self, target: QLineEdit) -> None:
        """Change the line edit that receives typed text."""
        self._target = target
        self._buffer = list(target.text())
        self.update()

    # -- key input -----------------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Up:
            self._move_cursor(dr=-1, dc=0)
        elif key == Qt.Key.Key_Down:
            self._move_cursor(dr=1, dc=0)
        elif key == Qt.Key.Key_Left:
            self._move_cursor(dr=0, dc=-1)
        elif key == Qt.Key.Key_Right:
            self._move_cursor(dr=0, dc=1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            self._activate_key()
        elif key == Qt.Key.Key_Escape:
            self._dismiss()
        else:
            super().keyPressEvent(event)

    def _move_cursor(self, dr: int, dc: int) -> None:
        """Move selection cursor by delta row/col, wrapping as needed."""
        n_rows = len(_ROWS)
        self._row = (self._row + dr) % n_rows
        row_len = len(_ROWS[self._row])
        if dc != 0:
            self._col = (self._col + dc) % row_len
        else:
            # When moving vertically, clamp col to row length
            self._col = min(self._col, row_len - 1)
        self.update()

    def _activate_key(self) -> None:
        """Press the currently highlighted key."""
        label = _ROWS[self._row][self._col]
        if label == "SPACE":
            self._buffer.append(" ")
        elif label == "BKSP":
            if self._buffer:
                self._buffer.pop()
        elif label == "ENTER":
            text = "".join(self._buffer)
            self._sync_target()
            self.text_submitted.emit(text)
            self._dismiss()
            return
        else:
            self._buffer.append(label)

        self._sync_target()
        self.update()

    def _sync_target(self) -> None:
        """Write current buffer to the target QLineEdit."""
        if self._target is not None:
            text = "".join(self._buffer)
            self._target.setText(text)
            # Emit search_changed if the target is a SearchBar
            if hasattr(self._target, "search_changed"):
                self._target.search_changed.emit(text)

    def _dismiss(self) -> None:
        """Hide keyboard and emit dismissed signal."""
        self.hide()
        self.dismissed.emit()
        if self._target is not None:
            self._target.setFocus()

    # -- painting ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        bg_path = QPainterPath()
        bg_path.addRoundedRect(0.0, 0.0, float(w), float(h), 12.0, 12.0)
        p.fillPath(bg_path, _BG)
        p.setPen(QPen(_BORDER, 1.0))
        p.drawPath(bg_path)

        # Draw text buffer preview at the top would be complex — just draw keys
        for ri, row in enumerate(_ROWS):
            row_width = len(row) * (_KEY_W + _KEY_GAP) - _KEY_GAP
            # Center the row horizontally
            x_offset = _PADDING + (self._max_row_width() - row_width) // 2
            y = _PADDING + ri * (_KEY_H + _KEY_GAP)

            for ci, label in enumerate(row):
                x = x_offset + ci * (_KEY_W + _KEY_GAP)
                selected = ri == self._row and ci == self._col

                # Wider special keys
                kw = _KEY_W
                if label in ("SPACE", "BKSP", "ENTER"):
                    kw = _KEY_W * 2 + _KEY_GAP
                    # Recalculate x for wide keys in the bottom row
                    if ri == len(_ROWS) - 1:
                        x = x_offset
                        for prev_ci in range(ci):
                            prev_label = _ROWS[ri][prev_ci]
                            if prev_label in ("SPACE", "BKSP", "ENTER"):
                                x += _KEY_W * 2 + _KEY_GAP + _KEY_GAP
                            else:
                                x += _KEY_W + _KEY_GAP

                # Key background
                key_path = QPainterPath()
                key_path.addRoundedRect(
                    float(x), float(y), float(kw), float(_KEY_H), 6.0, 6.0
                )

                if selected:
                    p.fillPath(key_path, _KEY_SELECTED)
                else:
                    p.fillPath(key_path, _KEY_BG)

                # Key label
                if label in ("SPACE", "BKSP", "ENTER"):
                    p.setFont(_SPECIAL_FONT)
                    display = {"SPACE": "SPACE", "BKSP": "\u2190", "ENTER": "\u21b5"}[label]
                else:
                    p.setFont(_KEY_FONT)
                    display = label.upper()

                p.setPen(_KEY_TEXT if selected else _KEY_TEXT_DIM)
                p.drawText(x, y, kw, _KEY_H, Qt.AlignmentFlag.AlignCenter, display)

        p.end()

    def _max_row_width(self) -> int:
        """Calculate the widest row width (all keys same width for simplicity)."""
        max_w = 0
        for ri, row in enumerate(_ROWS):
            rw = 0
            for label in row:
                if label in ("SPACE", "BKSP", "ENTER"):
                    rw += _KEY_W * 2 + _KEY_GAP
                else:
                    rw += _KEY_W
                rw += _KEY_GAP
            rw -= _KEY_GAP  # no trailing gap
            max_w = max(max_w, rw)
        return max_w
