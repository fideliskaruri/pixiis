"""SearchBar — premium search input with custom-painted visuals and debounced signal."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLineEdit, QWidget

# Dark cinema palette v2
ACCENT = QColor("#e94560")
BG_NORMAL = QColor("#13121a")       # surface
BG_FOCUS = QColor("#13121a")        # same bg, border changes
BORDER_NORMAL = QColor(255, 255, 255, 15)   # rgba(255,255,255,0.06)
BORDER_HOVER = QColor(255, 255, 255, 31)    # rgba(255,255,255,0.12)
TEXT_COLOR = QColor("#f0eef5")       # text_primary
PLACEHOLDER_COLOR = QColor("#7a7690") # text_muted

BAR_HEIGHT = 44
RADIUS = 22.0
ICON_AREA = 44  # left padding for magnifying glass


class SearchBar(QLineEdit):
    """Rounded search field with custom-painted magnifying glass, mic button, and accent focus glow."""

    search_changed = Signal(str)
    mic_clicked = Signal()  # emitted when the mic button is clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(BAR_HEIGHT)
        self.setMinimumWidth(200)
        self.setPlaceholderText("Search games...")
        self.setClearButtonEnabled(True)
        self.setAccessibleName("Search games")

        # Transparent base — we paint everything ourselves
        self.setStyleSheet(
            "QLineEdit {"
            "  background: transparent;"
            "  border: none;"
            f"  color: {TEXT_COLOR.name()};"
            "  font-size: 14px;"
            f"  padding-left: {ICON_AREA}px;"
            "  padding-right: 40px;"  # room for mic icon
            "}"
        )

        # Mic button — trailing action on the line edit
        self._mic_icon = self._create_mic_icon(PLACEHOLDER_COLOR)
        self._mic_icon_active = self._create_mic_icon(ACCENT)
        self._mic_action = QAction(self._mic_icon, "Voice search", self)
        self._mic_action.setToolTip("Voice search (RT on controller)")
        self._mic_action.triggered.connect(self.mic_clicked.emit)
        self.addAction(self._mic_action, QLineEdit.ActionPosition.TrailingPosition)

        self._mic_recording = False

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

        # ── Border — always 2px, only color changes (no layout shift) ──
        if focused:
            pen = QPen(ACCENT, 2.0)
        else:
            pen = QPen(BORDER_NORMAL, 2.0)
        p.setPen(pen)
        p.drawRoundedRect(rect, RADIUS, RADIUS)

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
            QPointF(handle_start_x, handle_start_y),
            QPointF(handle_start_x + handle_len, handle_start_y + handle_len),
        )

        p.end()

        # Let QLineEdit paint text on top
        super().paintEvent(event)

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_text_changed(self, _text: str) -> None:
        self._debounce.start()

    def _emit_search(self) -> None:
        self.search_changed.emit(self.text().strip())

    # ── Mic recording state ───────────────────────────────────────────────

    def set_mic_recording(self, active: bool) -> None:
        """Update the mic icon to show recording state."""
        self._mic_recording = active
        self._mic_action.setIcon(self._mic_icon_active if active else self._mic_icon)
        if active:
            self.setPlaceholderText("Listening...")
        else:
            self.setPlaceholderText("Search games...")

    @staticmethod
    def _create_mic_icon(color: QColor) -> QIcon:
        """Paint a simple mic icon as a QIcon."""
        size = 16
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        # Mic body (rounded rect)
        p.drawRoundedRect(QRectF(5, 1, 6, 9), 3, 3)
        # Mic base arc
        p.drawArc(QRectF(3, 5, 10, 8), 0, -180 * 16)
        # Stem
        p.drawLine(QPointF(8, 13), QPointF(8, 15))
        # Base
        p.drawLine(QPointF(5, 15), QPointF(11, 15))
        p.end()
        return QIcon(pm)

    # ── Key overrides ───────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._debounce.stop()  # prevent double-fire
            self.clear()
            self.search_changed.emit("")
            parent = self.parentWidget()
            if parent is not None:
                parent.setFocus()
        else:
            super().keyPressEvent(event)
