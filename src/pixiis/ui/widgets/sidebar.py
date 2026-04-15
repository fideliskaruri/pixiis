"""Horizontal top navigation bar with Dark Cinema aesthetic."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

# ── Dark Cinema palette v2 ───────────────────────────────────────────────

_NAV_BG = QColor("#0e0d14")
_ACCENT = QColor(233, 69, 96)        # #e94560
_TEXT_MUTED = QColor("#7a7690")
_TEXT_SECONDARY = QColor("#8a8698")
_TEXT_PRIMARY = QColor("#f0eef5")
_HOVER_BG = QColor(233, 69, 96, 20)  # rgba(233,69,96,0.08)
_ACTIVE_BG = QColor(233, 69, 96, 38) # rgba(233,69,96,0.15)
_FOCUS_BG = QColor(233, 69, 96, 31)  # rgba(233,69,96,0.12)
_FOCUS_BORDER = QColor(233, 69, 96, 77)  # rgba(233,69,96,0.30)
_BORDER_COLOR = QColor(255, 255, 255, 10) # rgba(255,255,255,0.04)

_ICONS: dict[str, str] = {
    "home": "\u2302",
    "library": "\u25a6",
    "settings": "\u2699",
    "file_manager": "\U0001f4c1",
}

# ── Pre-built fonts (avoid re-creating in paintEvent) ─────────────────────

_NAV_ICON_FONT = QFont()
_NAV_ICON_FONT.setPixelSize(16)

_NAV_LABEL_FONT = QFont()
_NAV_LABEL_FONT.setPixelSize(13)
_NAV_LABEL_FONT.setWeight(QFont.Weight.Medium)


class NavButton(QWidget):
    """A custom-painted horizontal nav tab with bottom accent indicator."""

    clicked = Signal()

    def __init__(self, text: str, page_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_name = page_name
        self._label = text
        self._icon = _ICONS.get(page_name, "\u2022")
        self._active = False
        self._hovered = False
        self._hover_progress: float = 0.0

        self.setFixedHeight(52)
        self.setMinimumWidth(90)
        self.setAccessibleName(text)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Hover animation
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(100)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── Animated property ──────────────────────────────────────────────────

    def _get_hover_progress(self) -> float:
        return self._hover_progress

    def _set_hover_progress(self, value: float) -> None:
        self._hover_progress = value
        self.update()

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        focused = self.hasFocus()

        # Background — always reserve 2px ring space (inset rect)
        inset = 4.0
        rw, rh = w - inset * 2, h - inset * 2

        if self._active:
            # Active: tinted background
            bg_path = QPainterPath()
            bg_path.addRoundedRect(inset, inset, rw, rh, 6.0, 6.0)
            p.fillPath(bg_path, _ACTIVE_BG)
        elif focused:
            # Focused only (not active): subtle focus background
            bg_path = QPainterPath()
            bg_path.addRoundedRect(inset, inset, rw, rh, 6.0, 6.0)
            p.fillPath(bg_path, _FOCUS_BG)
        elif self._hover_progress > 0.0:
            hover_alpha = int(20 * self._hover_progress)
            hover_bg = QColor(233, 69, 96, hover_alpha)
            bg_path = QPainterPath()
            bg_path.addRoundedRect(inset, inset, rw, rh, 6.0, 6.0)
            p.fillPath(bg_path, hover_bg)

        # Focus ring — always painted when focused, regardless of active state
        # 2px accent border ring (always same rect, only color changes)
        if focused:
            pen = QPen(_ACCENT, 2.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(inset, inset, rw, rh, 6.0, 6.0)
        else:
            # Reserve 2px border space — transparent ring (no layout shift)
            pen = QPen(QColor(0, 0, 0, 0), 2.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(inset, inset, rw, rh, 6.0, 6.0)

        # Bottom accent bar (active only) — full width of text+padding, 2px tall
        if self._active:
            bar_w = w - 16.0
            bar_x = 8.0
            accent_path = QPainterPath()
            accent_path.addRoundedRect(bar_x, h - 3.0, bar_w, 2.0, 1.0, 1.0)
            p.fillPath(accent_path, _ACCENT)

        # Text color
        if self._active:
            text_color = _TEXT_PRIMARY
        elif self._hovered or focused:
            text_color = _TEXT_PRIMARY
        else:
            text_color = _TEXT_SECONDARY

        p.setPen(QPen(text_color))

        # Icon
        icon_rect_w = 20

        # Calculate centering
        p.setFont(_NAV_LABEL_FONT)
        label_w = p.fontMetrics().horizontalAdvance(self._label)
        total_w = icon_rect_w + 4 + label_w
        start_x = (w - total_w) / 2.0

        # Draw icon (use QRectF to avoid int truncation jitter)
        p.setFont(_NAV_ICON_FONT)
        p.drawText(QRectF(start_x, 0, icon_rect_w, h), Qt.AlignmentFlag.AlignCenter, self._icon)

        # Draw label
        p.setFont(_NAV_LABEL_FONT)
        p.drawText(
            QRectF(start_x + icon_rect_w + 4, 0, label_w + 4, h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._label,
        )

        p.end()


class Sidebar(QFrame):
    """Horizontal top navigation bar with Dark Cinema aesthetic.

    Emits :pyqt:`page_requested(str)` when the user clicks a nav tab.
    """

    page_requested = Signal(str)
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    _NAV_ITEMS: list[tuple[str, str]] = [
        ("Home", "home"),
        ("Library", "library"),
        ("Settings", "settings"),
        ("Files", "file_manager"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setObjectName("Sidebar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(0)

        # -- logo / title
        title = QLabel("PIXIIS")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        title.setFixedWidth(90)
        title.setStyleSheet(
            "QLabel {"
            "  font-size: 18px;"
            "  font-weight: bold;"
            "  color: #e94560;"
            "  letter-spacing: 2px;"
            "  background-color: transparent;"
            "}"
        )
        layout.addWidget(title)

        layout.addSpacing(24)

        # -- nav buttons
        self._buttons: dict[str, NavButton] = {}
        for label, page_name in self._NAV_ITEMS:
            btn = NavButton(label, page_name)
            btn.clicked.connect(self._on_button_clicked)
            layout.addWidget(btn)
            self._buttons[page_name] = btn

        layout.addStretch()

        # -- window control buttons (minimize, maximize, close)
        _BTN_BASE = (
            "QPushButton {"
            "  background: transparent;"
            "  border: none;"
            "  border-radius: 6px;"
            "  font-size: 14px;"
            "  padding: 0;"
            "}"
        )
        btn_min = QPushButton("\u2500")  # ─ minimize
        btn_min.setFixedSize(32, 32)
        btn_min.setStyleSheet(
            _BTN_BASE
            + "QPushButton { color: #7a7690; }"
            "QPushButton:hover { background: #252330; color: #8a8698; }"
        )
        btn_min.clicked.connect(self.minimize_requested.emit)
        btn_min.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(btn_min)

        layout.addSpacing(2)

        btn_max = QPushButton("\u25a1")  # □ maximize
        btn_max.setFixedSize(32, 32)
        btn_max.setStyleSheet(
            _BTN_BASE
            + "QPushButton { color: #7a7690; }"
            "QPushButton:hover { background: #252330; color: #8a8698; }"
        )
        btn_max.clicked.connect(self.maximize_requested.emit)
        btn_max.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(btn_max)

        layout.addSpacing(2)

        btn_close = QPushButton("\u2715")  # ✕ close
        btn_close.setFixedSize(32, 32)
        btn_close.setStyleSheet(
            _BTN_BASE
            + "QPushButton { color: #7a7690; }"
            "QPushButton:hover { background: #e94560; color: #ffffff; }"
        )
        btn_close.clicked.connect(self.close_requested.emit)
        btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(btn_close)

    def paintEvent(self, event) -> None:
        """Custom background with warm gradient and bottom border."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Warm gradient background
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor("#0e0d14"))
        grad.setColorAt(1.0, _NAV_BG)
        p.fillRect(0, 0, w, h, grad)

        # Bottom border — barely visible separator
        p.setPen(QPen(_BORDER_COLOR, 1.0))
        p.drawLine(0, h - 1, w, h - 1)

        p.end()

    # -- public API

    def set_active(self, page_name: str) -> None:
        """Highlight *page_name* and deactivate others."""
        for name, btn in self._buttons.items():
            btn.set_active(name == page_name)

    # -- internals

    def _on_button_clicked(self) -> None:
        btn = self.sender()
        if isinstance(btn, NavButton):
            self.page_requested.emit(btn.page_name)
