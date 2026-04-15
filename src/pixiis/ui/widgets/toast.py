"""Toast — floating notification that fades in, stays, and fades out."""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QFontMetrics
from PySide6.QtWidgets import QWidget

_BG = QColor("#1c1a24")
_TEXT = QColor("#f0eef5")
_ACCENT = QColor("#e94560")
_ICONS = {"success": "\u2713", "error": "\u2717", "info": "\u2139"}
_ICON_COLORS = {
    "success": QColor("#4ade80"),
    "error": QColor("#f87171"),
    "info": QColor("#60a5fa"),
}

# ── Pre-built fonts (avoid re-creating in paintEvent) ─────────────────────

_TOAST_ICON_FONT = QFont()
_TOAST_ICON_FONT.setPixelSize(16)
_TOAST_ICON_FONT.setBold(True)

_TOAST_TEXT_FONT = QFont()
_TOAST_TEXT_FONT.setPixelSize(13)
_TOAST_TEXT_FONT.setWeight(QFont.Weight.Normal)


class Toast(QWidget):
    """Floating notification that appears at the bottom-center of its parent."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedHeight(44)
        self.hide()

        self._message = ""
        self._icon = "success"
        self._opacity = 0.0

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.finished.connect(self._on_fade_done)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    def show_message(
        self, text: str, duration_ms: int = 2000, icon: str = "success"
    ) -> None:
        self._message = text
        self._icon = icon

        # Size to fit text
        fm = QFontMetrics(_TOAST_TEXT_FONT)
        text_w = fm.horizontalAdvance(text)
        self.setFixedWidth(text_w + 60)  # icon + padding

        self._reposition()
        self.update()  # repaint with new text

        # If called during a fade-out, stop the animation and snap visible
        if self.isVisible():
            self._fade_anim.stop()
            self.setWindowOpacity(1.0)

        if self.isVisible() and self.windowOpacity() > 0.1:
            # Already showing — just update text and restart the timer
            self._hide_timer.stop()
            self._hide_timer.start(duration_ms)
        else:
            # Fresh show
            self.show()
            self.raise_()
            self._fade_in()
            self._hide_timer.start(duration_ms)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 60
        self.move(x, y)

    def _fade_in(self) -> None:
        self._fade_anim.stop()
        self._opacity = 0.0
        self._fade_anim.setDuration(150)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

    def _fade_out(self) -> None:
        self._fade_anim.stop()
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_anim.start()

    def _on_fade_done(self) -> None:
        # windowOpacity may not work for SubWindow widgets on all platforms.
        # Always hide when the fade-out animation finishes going toward 0.
        end = self._fade_anim.endValue()
        if end is not None and float(end) < 0.1:
            self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rounded background
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(self.width()), float(self.height()), 10.0, 10.0)
        p.fillPath(path, _BG)

        # Icon
        p.setFont(_TOAST_ICON_FONT)
        p.setPen(_ICON_COLORS.get(self._icon, _ACCENT))
        p.drawText(16, 0, 20, self.height(), Qt.AlignmentFlag.AlignCenter, _ICONS.get(self._icon, ""))

        # Text
        p.setFont(_TOAST_TEXT_FONT)
        p.setPen(_TEXT)
        p.drawText(42, 0, self.width() - 54, self.height(), Qt.AlignmentFlag.AlignVCenter, self._message)

        p.end()
