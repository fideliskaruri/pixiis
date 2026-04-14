"""SearchBar — premium search input with custom-painted visuals and debounced signal."""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLineEdit, QWidget

# Dark cinema palette
ACCENT = QColor("#e94560")
BG_NORMAL = QColor("#161620")
BG_FOCUS = QColor("#1a1a24")
BORDER_NORMAL = QColor(255, 255, 255, 15)  # rgba(255,255,255,0.06)
TEXT_COLOR = QColor("#e8e8f0")
PLACEHOLDER_COLOR = QColor("#6b6b80")

BAR_HEIGHT = 44
RADIUS = 22.0
ICON_AREA = 44  # left padding for magnifying glass


class SearchBar(QLineEdit):
    """Rounded search field with custom-painted magnifying glass and accent focus glow."""

    search_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(BAR_HEIGHT)
        self.setMinimumWidth(200)
        self.setPlaceholderText("Search games...")
        self.setClearButtonEnabled(True)

        # Transparent base — we paint everything ourselves
        self.setStyleSheet(
            "QLineEdit {"
            "  background: transparent;"
            "  border: none;"
            f"  color: {TEXT_COLOR.name()};"
            "  font-size: 14px;"
            f"  padding-left: {ICON_AREA}px;"
            "  padding-right: 16px;"
            "}"
        )

        # Debounce timer
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._emit_search)
        self.textChanged.connect(self._on_text_changed)

    # ── Custom paint ────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        focused = self.hasFocus()

        # ── Background pill ─────────────────────────────────────────────
        bg = BG_FOCUS if focused else BG_NORMAL
        pill = QPainterPath()
        pill.addRoundedRect(rect, RADIUS, RADIUS)
        p.fillPath(pill, bg)

        # ── Border ──────────────────────────────────────────────────────
        if focused:
            pen = QPen(ACCENT, 1.5)
        else:
            pen = QPen(BORDER_NORMAL, 1.0)
        p.setPen(pen)
        p.drawRoundedRect(rect, RADIUS, RADIUS)

        # ── Focus accent glow at bottom ─────────────────────────────────
        if focused:
            glow_pen = QPen(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 60), 2.0)
            p.setPen(glow_pen)
            glow_rect = rect.adjusted(4, 4, -4, -4)
            p.drawRoundedRect(glow_rect, RADIUS - 2, RADIUS - 2)

        # ── Magnifying glass icon ───────────────────────────────────────
        icon_color = ACCENT if focused else PLACEHOLDER_COLOR
        p.setPen(QPen(icon_color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

        # Circle part
        cx = 22.0
        cy = rect.height() / 2.0
        r = 7.0
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # Handle (line from bottom-right of circle at 45 degrees)
        handle_start_x = cx + r * math.cos(math.radians(45))
        handle_start_y = cy + r * math.sin(math.radians(45))
        handle_len = 5.0
        p.drawLine(
            int(handle_start_x), int(handle_start_y),
            int(handle_start_x + handle_len), int(handle_start_y + handle_len),
        )

        p.end()

        # Let QLineEdit paint text on top
        super().paintEvent(event)

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_text_changed(self, _text: str) -> None:
        self._debounce.start()

    def _emit_search(self) -> None:
        self.search_changed.emit(self.text().strip())

    # ── Key overrides ───────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
            self.search_changed.emit("")
            parent = self.parentWidget()
            if parent is not None:
                parent.setFocus()
        else:
            super().keyPressEvent(event)
