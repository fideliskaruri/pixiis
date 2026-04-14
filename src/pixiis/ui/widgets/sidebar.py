"""Horizontal top navigation bar with Dark Cinema aesthetic."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

# ── Dark Cinema palette ────────────────────────────────────────────────────

_NAV_BG = QColor(12, 12, 18)  # #0c0c12
_ACCENT = QColor(233, 69, 96)  # #e94560
_TEXT_MUTED = QColor(107, 107, 128)  # #6b6b80
_TEXT_PRIMARY = QColor(232, 232, 240)  # #e8e8f0
_HOVER_BG = QColor(233, 69, 96, 20)  # rgba(233,69,96,0.08)
_ACTIVE_BG = QColor(233, 69, 96, 31)  # rgba(233,69,96,0.12)
_BORDER_COLOR = QColor(255, 255, 255, 10)  # rgba(255,255,255,0.04)

_ICONS: dict[str, str] = {
    "home": "\u2302",
    "library": "\u25a6",
    "settings": "\u2699",
    "file_manager": "\U0001f4c1",
}


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

        self.setFixedHeight(56)
        self.setMinimumWidth(100)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
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

        # Background on hover/active
        if self._active:
            bg = _ACTIVE_BG
        elif self._hovered:
            bg = _HOVER_BG
        else:
            bg = QColor(0, 0, 0, 0)

        if bg.alpha() > 0:
            path = QPainterPath()
            path.addRoundedRect(4.0, 4.0, w - 8.0, h - 8.0, 8.0, 8.0)
            p.fillPath(path, bg)

        # Bottom accent bar (active only) — centered horizontal pill
        if self._active:
            bar_w = min(w * 0.5, 40)
            bar_x = (w - bar_w) / 2.0
            accent_path = QPainterPath()
            accent_path.addRoundedRect(bar_x, h - 4.0, bar_w, 3.0, 1.5, 1.5)
            p.fillPath(accent_path, _ACCENT)

        # Icon + Label — centered horizontally
        if self._active:
            text_color = _ACCENT
        elif self._hovered:
            text_color = _TEXT_PRIMARY
        else:
            text_color = _TEXT_MUTED

        p.setPen(QPen(text_color))

        # Icon
        icon_font = QFont()
        icon_font.setPixelSize(16)
        p.setFont(icon_font)
        icon_rect_w = 22
        total_w = icon_rect_w + 6 + p.fontMetrics().horizontalAdvance(self._label)

        label_font = QFont()
        label_font.setPixelSize(13)
        label_font.setWeight(QFont.Weight.Medium)

        # Recalculate with label font for accurate centering
        p.setFont(label_font)
        label_w = p.fontMetrics().horizontalAdvance(self._label)
        total_w = icon_rect_w + 4 + label_w
        start_x = (w - total_w) / 2.0

        # Draw icon
        p.setFont(icon_font)
        p.drawText(int(start_x), 0, icon_rect_w, h, Qt.AlignmentFlag.AlignCenter, self._icon)

        # Draw label
        p.setFont(label_font)
        p.drawText(
            int(start_x + icon_rect_w + 4), 0,
            label_w + 4, h,
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
        self.setFixedHeight(60)
        self.setObjectName("Sidebar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)

        # -- logo / title
        title = QLabel("PIXIIS")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        title.setFixedWidth(120)
        title.setStyleSheet(
            "QLabel {"
            "  font-size: 20px;"
            "  font-weight: bold;"
            "  color: #e94560;"
            "  letter-spacing: 6px;"
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
        btn_min.setFixedSize(36, 36)
        btn_min.setStyleSheet(
            _BTN_BASE
            + "QPushButton { color: #6b6b80; }"
            "QPushButton:hover { background: rgba(255,255,255,0.08); color: #e8e8f0; }"
        )
        btn_min.clicked.connect(self.minimize_requested.emit)
        layout.addWidget(btn_min)

        btn_max = QPushButton("\u25a1")  # □ maximize
        btn_max.setFixedSize(36, 36)
        btn_max.setStyleSheet(
            _BTN_BASE
            + "QPushButton { color: #6b6b80; }"
            "QPushButton:hover { background: rgba(255,255,255,0.08); color: #e8e8f0; }"
        )
        btn_max.clicked.connect(self.maximize_requested.emit)
        layout.addWidget(btn_max)

        btn_close = QPushButton("\u2715")  # ✕ close
        btn_close.setFixedSize(36, 36)
        btn_close.setStyleSheet(
            _BTN_BASE
            + "QPushButton { color: #6b6b80; }"
            "QPushButton:hover { background: rgba(233,69,96,0.8); color: #ffffff; }"
        )
        btn_close.clicked.connect(self.close_requested.emit)
        layout.addWidget(btn_close)

    def paintEvent(self, event) -> None:
        """Custom background with subtle gradient and bottom border."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Gradient background
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor(14, 14, 22))
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
