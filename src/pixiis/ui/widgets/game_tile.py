"""GameTile — large visual tile displaying game header art with hover/focus animations."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QVBoxLayout,
)

from pixiis.core.types import AppEntry

# ── Constants ───────────────────────────────────────────────────────────────

DEFAULT_TILE_WIDTH = 460
DEFAULT_TILE_HEIGHT = 215
ACCENT_COLOR = QColor("#e94560")
BG_DARK = QColor("#0d0d0f")
BG_MID = QColor("#1a1a2e")

FOCUS_BORDER_SS = (
    "GameTile {{ border: 2px solid {accent}; border-radius: 8px; }}"
)
IDLE_BORDER_SS = (
    "GameTile { border: 2px solid transparent; border-radius: 8px; }"
)


def _placeholder_pixmap(width: int, height: int, text: str) -> QPixmap:
    """Create a dark gradient placeholder with centered game name."""
    pix = QPixmap(width, height)
    pix.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    grad = QLinearGradient(0, 0, 0, height)
    grad.setColorAt(0.0, BG_MID)
    grad.setColorAt(1.0, BG_DARK)
    painter.fillRect(pix.rect(), grad)

    painter.setPen(QColor("#aaaaaa"))
    font = painter.font()
    font.setPointSize(13)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return pix


class GameTile(QFrame):
    """A large tile showing game header art with animated hover/focus effects."""

    activated = Signal(object)    # emits AppEntry on click / Enter
    tile_focused = Signal(object) # emits AppEntry on focus

    def __init__(
        self,
        app: AppEntry,
        width: int = DEFAULT_TILE_WIDTH,
        height: int = DEFAULT_TILE_HEIGHT,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.app = app
        self._tile_w = width
        self._tile_h = height

        self.setFixedSize(width, height)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(IDLE_BORDER_SS)
        self.setObjectName("GameTile")

        # ── Image label (fills entire tile) ─────────────────────────────
        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setGeometry(0, 0, width, height)
        self._image_label.setStyleSheet("background: transparent; border: none;")

        # ── Bottom overlay: gradient + game name ────────────────────────
        self._overlay = QLabel(self)
        self._overlay.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom
        )
        overlay_h = 60
        self._overlay.setGeometry(0, height - overlay_h, width, overlay_h)
        self._overlay.setStyleSheet(
            "background: qlineargradient("
            "x1:0, y1:0, x2:0, y2:1, "
            "stop:0 rgba(0,0,0,0), stop:1 rgba(0,0,0,200));"
            "color: white; font-weight: bold; font-size: 14px;"
            "padding: 6px 10px; border: none;"
        )
        self._overlay.setText(app.display_name)

        # Show placeholder until real image arrives.
        self._set_pixmap(_placeholder_pixmap(width, height, app.display_name))

        # ── Drop-shadow glow effect (always present, starts invisible) ──
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(ACCENT_COLOR)
        self._shadow.setBlurRadius(0)
        self.setGraphicsEffect(self._shadow)

        # ── Animations (created once, reused) ───────────────────────────
        self._glow_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._glow_anim.setDuration(150)
        self._glow_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        self._scale_anim = QPropertyAnimation(self, b"geometry", self)
        self._scale_anim.setDuration(150)
        self._scale_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        # Store the base geometry (set by layout); updated on first show.
        self._base_geo = None

    # ── Public API ──────────────────────────────────────────────────────────

    def set_image(self, pixmap: QPixmap) -> None:
        """Called by image loader when game art arrives."""
        self._set_pixmap(pixmap)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _set_pixmap(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            self._tile_w,
            self._tile_h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Centre-crop if the scaled image is larger than the tile.
        if scaled.width() > self._tile_w or scaled.height() > self._tile_h:
            x = (scaled.width() - self._tile_w) // 2
            y = (scaled.height() - self._tile_h) // 2
            scaled = scaled.copy(x, y, self._tile_w, self._tile_h)
        self._image_label.setPixmap(scaled)

    def _animate_focus_in(self) -> None:
        """Glow + slight scale-up."""
        self.setStyleSheet(FOCUS_BORDER_SS.format(accent=ACCENT_COLOR.name()))

        # Glow
        self._glow_anim.stop()
        self._glow_anim.setStartValue(self._shadow.blurRadius())
        self._glow_anim.setEndValue(25)
        self._glow_anim.start()

        # Scale-up via geometry
        self._base_geo = self.geometry()
        target = self._base_geo.adjusted(-8, -8, 8, 8)
        self._scale_anim.stop()
        self._scale_anim.setStartValue(self.geometry())
        self._scale_anim.setEndValue(target)
        self._scale_anim.start()

    def _animate_focus_out(self) -> None:
        """Reverse glow + restore geometry."""
        self.setStyleSheet(IDLE_BORDER_SS)

        # Glow out
        self._glow_anim.stop()
        self._glow_anim.setStartValue(self._shadow.blurRadius())
        self._glow_anim.setEndValue(0)
        self._glow_anim.setDuration(100)
        self._glow_anim.start()

        # Scale back
        if self._base_geo is not None:
            self._scale_anim.stop()
            self._scale_anim.setStartValue(self.geometry())
            self._scale_anim.setEndValue(self._base_geo)
            self._scale_anim.setDuration(100)
            self._scale_anim.start()

        # Restore original durations after animation fires.
        self._glow_anim.setDuration(150)
        self._scale_anim.setDuration(150)

    # ── Event overrides ─────────────────────────────────────────────────────

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._animate_focus_in()
        self.tile_focused.emit(self.app)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self._animate_focus_out()

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        if not self.hasFocus():
            self._animate_focus_in()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        if not self.hasFocus():
            self._animate_focus_out()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.activated.emit(self.app)
        else:
            super().keyPressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.app)
        super().mouseReleaseEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._tile_w, self._tile_h)
