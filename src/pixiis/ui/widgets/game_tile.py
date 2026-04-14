"""GameTile — cinematic portrait tile with custom-painted visuals and hover animations."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Property,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QWidget,
)

from pixiis.core.types import AppEntry

# ── Constants ───────────────────────────────────────────────────────────────

DEFAULT_TILE_WIDTH = 300
DEFAULT_TILE_HEIGHT = 420
CORNER_RADIUS = 14.0
ACCENT_COLOR = QColor("#e94560")

# Dark cinema palette
BG_BASE = QColor("#08080c")
BG_SURFACE = QColor("#0f0f15")
BG_LIGHTER = QColor("#161620")
TEXT_PRIMARY = QColor("#e8e8f0")
TEXT_SECONDARY = QColor("#6b6b80")

# Animation
HOVER_EXPAND_PX = 12
ANIM_DURATION_MS = 200

# Source badge labels
_SOURCE_LABELS = {
    "steam": "STEAM",
    "xbox": "XBOX",
    "startmenu": "PC",
    "manual": "CUSTOM",
}


class GameTile(QWidget):
    """A cinematic portrait tile showing game art with animated hover/focus effects.

    All visuals are rendered in ``paintEvent`` for full control over rounded
    corners, gradient overlays, text, and badges.
    """

    activated = Signal(object)    # emits AppEntry on click / Enter
    tile_focused = Signal(object) # emits AppEntry on focus

    def __init__(
        self,
        app: AppEntry,
        width: int = DEFAULT_TILE_WIDTH,
        height: int = DEFAULT_TILE_HEIGHT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.app = app
        self._tile_w = width
        self._tile_h = height
        self._pixmap: QPixmap | None = None
        self._hover_progress: float = 0.0

        self.setFixedSize(width, height)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        # ── Drop-shadow glow (accent colored, starts invisible) ─────────
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(ACCENT_COLOR)
        self._shadow.setBlurRadius(0)
        self.setGraphicsEffect(self._shadow)

        # ── Animations ──────────────────────────────────────────────────
        self._glow_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._glow_anim.setDuration(ANIM_DURATION_MS)
        self._glow_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._scale_anim = QPropertyAnimation(self, b"geometry", self)
        self._scale_anim.setDuration(ANIM_DURATION_MS)
        self._scale_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(ANIM_DURATION_MS)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._base_geo = None

    # ── hover_progress property for animation ───────────────────────────────

    def _get_hover_progress(self) -> float:
        return self._hover_progress

    def _set_hover_progress(self, value: float) -> None:
        self._hover_progress = value
        self.update()  # trigger repaint

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    # ── Public API ──────────────────────────────────────────────────────────

    def set_image(self, pixmap: QPixmap) -> None:
        """Called by image loader when game art arrives."""
        self._pixmap = pixmap
        self.update()

    # ── Paint ───────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect())
        hp = self._hover_progress  # 0.0 → 1.0

        # ── Clip to rounded rect ────────────────────────────────────────
        clip = QPainterPath()
        clip.addRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)
        p.setClipPath(clip)

        # ── Background / Image ──────────────────────────────────────────
        if self._pixmap and not self._pixmap.isNull():
            # Scale image to fill the tile, center-crop
            scaled = self._pixmap.scaled(
                self.width(),
                self.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            cropped = scaled.copy(x, y, self.width(), self.height())
            p.drawPixmap(0, 0, cropped)
        else:
            # Placeholder gradient
            grad = QLinearGradient(0, 0, 0, rect.height())
            grad.setColorAt(0.0, BG_LIGHTER)
            grad.setColorAt(1.0, BG_SURFACE)
            p.fillRect(rect, grad)
            # Centered game name as placeholder text
            p.setPen(TEXT_SECONDARY)
            font = QFont()
            font.setPixelSize(16)
            font.setBold(True)
            p.setFont(font)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.app.display_name)

        # ── Brightness overlay on hover ─────────────────────────────────
        if hp > 0.0:
            overlay_alpha = int(12 * hp)  # subtle: max ~0.05 opacity
            p.fillRect(rect, QColor(255, 255, 255, overlay_alpha))

        # ── Bottom gradient overlay ─────────────────────────────────────
        grad_h = rect.height() * 0.45
        grad_rect = QRectF(0, rect.height() - grad_h, rect.width(), grad_h)
        grad = QLinearGradient(0, grad_rect.top(), 0, grad_rect.bottom())
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(0.4, QColor(0, 0, 0, 80))
        grad.setColorAt(1.0, QColor(0, 0, 0, 216))  # ~0.85 opacity
        p.fillRect(grad_rect, grad)

        # ── Game name text ──────────────────────────────────────────────
        name_font = QFont()
        name_font.setPixelSize(15)
        name_font.setBold(True)
        p.setFont(name_font)
        p.setPen(TEXT_PRIMARY)

        text_pad = 16
        text_rect = QRectF(
            text_pad,
            rect.height() - 52,
            rect.width() - text_pad * 2,
            36,
        )
        fm = QFontMetrics(name_font)
        elided = fm.elidedText(
            self.app.display_name, Qt.TextElideMode.ElideRight, int(text_rect.width())
        )
        p.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        # ── Source badge (top-right pill) ───────────────────────────────
        source_key = self.app.source.name.lower() if hasattr(self.app.source, "name") else str(self.app.source).lower()
        badge_text = _SOURCE_LABELS.get(source_key, source_key.upper())

        badge_font = QFont()
        badge_font.setPixelSize(10)
        badge_font.setBold(True)
        p.setFont(badge_font)
        bfm = QFontMetrics(badge_font)
        badge_w = bfm.horizontalAdvance(badge_text) + 14
        badge_h = 20
        badge_x = rect.width() - badge_w - 10
        badge_y = 10.0
        badge_rect = QRectF(badge_x, badge_y, badge_w, badge_h)

        badge_path = QPainterPath()
        badge_path.addRoundedRect(badge_rect, 4, 4)
        p.fillPath(badge_path, QColor(0, 0, 0, 153))  # ~0.6 opacity
        p.setPen(QColor(255, 255, 255, 200))
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # ── Focus / hover border ────────────────────────────────────────
        if hp > 0.0:
            border_alpha = int(255 * hp)
            pen = QPen(QColor(ACCENT_COLOR.red(), ACCENT_COLOR.green(), ACCENT_COLOR.blue(), border_alpha))
            pen.setWidthF(2.0)
            p.setClipping(False)
            p.setPen(pen)
            # Inset border so it doesn't clip
            border_rect = rect.adjusted(1, 1, -1, -1)
            p.drawRoundedRect(border_rect, CORNER_RADIUS, CORNER_RADIUS)

        p.end()

    # ── Focus / hover animation helpers ─────────────────────────────────────

    def _animate_in(self) -> None:
        # Hover progress
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()

        # Glow
        self._glow_anim.stop()
        self._glow_anim.setStartValue(self._shadow.blurRadius())
        self._glow_anim.setEndValue(30)
        self._glow_anim.start()

        # Scale-up via geometry
        self._base_geo = self.geometry()
        target = self._base_geo.adjusted(
            -HOVER_EXPAND_PX, -HOVER_EXPAND_PX, HOVER_EXPAND_PX, HOVER_EXPAND_PX
        )
        self._scale_anim.stop()
        self._scale_anim.setStartValue(self.geometry())
        self._scale_anim.setEndValue(target)
        self._scale_anim.start()

    def _animate_out(self) -> None:
        # Hover progress
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()

        # Glow
        self._glow_anim.stop()
        self._glow_anim.setStartValue(self._shadow.blurRadius())
        self._glow_anim.setEndValue(0)
        self._glow_anim.start()

        # Scale back
        if self._base_geo is not None:
            self._scale_anim.stop()
            self._scale_anim.setStartValue(self.geometry())
            self._scale_anim.setEndValue(self._base_geo)
            self._scale_anim.start()

    # ── Event overrides ─────────────────────────────────────────────────────

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._animate_in()
        self.tile_focused.emit(self.app)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self._animate_out()

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        if not self.hasFocus():
            self._animate_in()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        if not self.hasFocus():
            self._animate_out()

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
