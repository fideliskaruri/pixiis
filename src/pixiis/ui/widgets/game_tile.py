"""GameTile — cinematic portrait tile with custom-painted visuals and hover animations."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Property,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from pixiis.core.types import AppEntry

# ── Constants ───────────────────────────────────────────────────────────────

DEFAULT_TILE_WIDTH = 220
DEFAULT_TILE_HEIGHT = 308
CORNER_RADIUS = 10.0
ACCENT_COLOR = QColor("#e94560")

# Warm plum-touched dark palette
BG_BASE = QColor("#0b0a10")
BG_SURFACE = QColor("#13121a")
BG_ELEVATED = QColor("#1c1a24")
TEXT_PRIMARY = QColor("#f0eef5")
TEXT_SECONDARY = QColor("#8a8698")
TEXT_MUTED = QColor("#7a7690")

# Animation
ANIM_DURATION_MS = 180

# ── Pre-built fonts (avoid re-creating in paintEvent) ─────────────────────

_ICON_FONT = QFont()
_ICON_FONT.setPixelSize(48)

_NAME_FONT = QFont()
_NAME_FONT.setPixelSize(16)
_NAME_FONT.setWeight(QFont.Weight.DemiBold)

_BADGE_FONT = QFont()
_BADGE_FONT.setPixelSize(10)
_BADGE_FONT.setBold(True)
_BADGE_FONT.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)

# Source badge labels
_SOURCE_LABELS = {
    "steam": "STEAM",
    "xbox": "XBOX",
    "startmenu": "PC",
    "manual": "CUSTOM",
    "gog": "GOG",
    "epic": "EPIC",
}


class GameTile(QWidget):
    """A cinematic portrait tile showing game art with animated hover/focus effects.

    All visuals are rendered in ``paintEvent`` for full control over rounded
    corners, gradient overlays, text, and badges.

    Three visual states:
    - Default: subtle border
    - Hover: faint accent border + brightness overlay
    - Focus: strong accent border + glow + scale(1.03)
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
        self._focus_progress: float = 0.0
        self._press_progress: float = 0.0

        self.setFixedSize(width, height)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAccessibleName(app.display_name)

        # ── Animations ──────────────────────────────────────────────────
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(ANIM_DURATION_MS)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._focus_anim = QPropertyAnimation(self, b"focusProgress", self)
        self._focus_anim.setDuration(200)
        self._focus_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._press_anim = QPropertyAnimation(self, b"pressProgress", self)
        self._press_anim.setDuration(80)
        self._press_anim.setEasingCurve(QEasingCurve.Type.InCubic)

    # ── Animated properties ────────────────────────────────────────────────

    def _get_hover_progress(self) -> float:
        return self._hover_progress

    def _set_hover_progress(self, value: float) -> None:
        self._hover_progress = value
        self.update()

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    def _get_focus_progress(self) -> float:
        return self._focus_progress

    def _set_focus_progress(self, value: float) -> None:
        self._focus_progress = value
        self.update()

    focusProgress = Property(float, _get_focus_progress, _set_focus_progress)

    def _get_press_progress(self) -> float:
        return self._press_progress

    def _set_press_progress(self, value: float) -> None:
        self._press_progress = value
        self.update()

    pressProgress = Property(float, _get_press_progress, _set_press_progress)

    # ── Public API ──────────────────────────────────────────────────────────

    def set_image(self, pixmap: QPixmap) -> None:
        """Called by image loader when game art arrives."""
        self._pixmap = pixmap
        self.update()

    # ── Paint ───────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(self.rect())
        hp = self._hover_progress   # 0.0 → 1.0 (mouse hover)
        fp = self._focus_progress   # 0.0 → 1.0 (keyboard/controller focus)
        pp = self._press_progress   # 0.0 → 1.0 (pressed)

        # ── Scale transform for focus/press ─────────────────────────────
        scale = 1.0 + 0.03 * fp - 0.02 * pp
        if scale != 1.0:
            cx, cy = rect.width() / 2, rect.height() / 2
            p.translate(cx, cy)
            p.scale(scale, scale)
            p.translate(-cx, -cy)

        # ── Clip to rounded rect ────────────────────────────────────────
        clip = QPainterPath()
        clip.addRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)
        p.setClipPath(clip)

        # ── Background / Image ──────────────────────────────────────────
        if self._pixmap and not self._pixmap.isNull():
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
            grad.setColorAt(0.0, BG_ELEVATED)
            grad.setColorAt(1.0, BG_SURFACE)
            p.fillRect(rect, grad)
            # Controller icon placeholder
            p.setPen(TEXT_MUTED)
            p.setFont(_ICON_FONT)
            p.drawText(rect.adjusted(0, -20, 0, 0), Qt.AlignmentFlag.AlignCenter, "\U0001f3ae")
            # Centered game name
            p.setPen(TEXT_SECONDARY)
            p.setFont(_NAME_FONT)
            name_rect = rect.adjusted(12, rect.height() * 0.55, -12, 0)
            p.drawText(name_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.app.display_name)

        # ── Brightness overlay on hover ─────────────────────────────────
        if hp > 0.0 and fp == 0.0:
            overlay_alpha = int(20 * hp)  # subtle ~3% white overlay
            p.fillRect(rect, QColor(255, 255, 255, overlay_alpha))

        # ── Bottom gradient overlay (lower 35%) ─────────────────────────
        grad_h = rect.height() * 0.35
        grad_rect = QRectF(0, rect.height() - grad_h, rect.width(), grad_h)
        grad = QLinearGradient(0, grad_rect.top(), 0, grad_rect.bottom())
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(0, 0, 0, 216))  # ~0.85 opacity
        p.fillRect(grad_rect, grad)

        # ── Game name text (16px SemiBold, max 2 lines) ─────────────────
        p.setFont(_NAME_FONT)
        p.setPen(TEXT_PRIMARY)

        text_pad = 12
        text_rect = QRectF(
            text_pad,
            rect.height() - 50,
            rect.width() - text_pad * 2,
            38,
        )
        fm = QFontMetrics(_NAME_FONT)
        elided = fm.elidedText(
            self.app.display_name, Qt.TextElideMode.ElideRight,
            int(text_rect.width()) * 2  # allow ~2 lines
        )
        p.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom | Qt.TextFlag.TextWordWrap,
            elided,
        )

        # ── Source badge (top-right, 8px from edges) ────────────────────
        source_key = self.app.source.name.lower() if hasattr(self.app.source, "name") else str(self.app.source).lower()
        badge_text = _SOURCE_LABELS.get(source_key, source_key.upper())

        p.setFont(_BADGE_FONT)
        bfm = QFontMetrics(_BADGE_FONT)
        badge_w = bfm.horizontalAdvance(badge_text) + 12
        badge_h = 18
        badge_x = rect.width() - badge_w - 8
        badge_y = 8.0
        badge_rect = QRectF(badge_x, badge_y, badge_w, badge_h)

        badge_path = QPainterPath()
        badge_path.addRoundedRect(badge_rect, 4, 4)
        p.fillPath(badge_path, QColor(0, 0, 0, 166))  # ~0.65 opacity
        p.setPen(TEXT_SECONDARY)
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # ── Border rendering ────────────────────────────────────────────
        p.setClipping(False)

        if fp > 0.0:
            # Focus state: strong accent border + outer glow
            for i in range(4, 0, -1):
                glow_alpha = int(60 * fp * (5 - i) / 4)
                pen = QPen(QColor(ACCENT_COLOR.red(), ACCENT_COLOR.green(), ACCENT_COLOR.blue(), glow_alpha))
                pen.setWidthF(float(i) * 1.5)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                glow_rect = rect.adjusted(-i, -i, i, i)
                p.drawRoundedRect(glow_rect, CORNER_RADIUS + i, CORNER_RADIUS + i)

            # Inner 2px accent border
            pen = QPen(QColor(ACCENT_COLOR.red(), ACCENT_COLOR.green(), ACCENT_COLOR.blue(), int(255 * fp)))
            pen.setWidthF(2.0)
            p.setPen(pen)
            border_rect = rect.adjusted(1, 1, -1, -1)
            p.drawRoundedRect(border_rect, CORNER_RADIUS, CORNER_RADIUS)

        elif hp > 0.0:
            # Hover state: faint accent border (no glow)
            border_alpha = int(64 * hp)  # rgba(233,69,96,0.25)
            pen = QPen(QColor(ACCENT_COLOR.red(), ACCENT_COLOR.green(), ACCENT_COLOR.blue(), border_alpha))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            border_rect = rect.adjusted(1, 1, -1, -1)
            p.drawRoundedRect(border_rect, CORNER_RADIUS, CORNER_RADIUS)

        else:
            # Default: subtle white border — always 2px (no layout shift)
            pen = QPen(QColor(255, 255, 255, 15))  # rgba(255,255,255,0.06)
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            border_rect = rect.adjusted(1, 1, -1, -1)
            p.drawRoundedRect(border_rect, CORNER_RADIUS, CORNER_RADIUS)

        p.end()

    # ── Animation helpers ──────────────────────────────────────────────────

    def _animate_hover(self, target: float) -> None:
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(target)
        self._hover_anim.start()

    def _animate_focus(self, target: float) -> None:
        self._focus_anim.stop()
        self._focus_anim.setStartValue(self._focus_progress)
        self._focus_anim.setEndValue(target)
        self._focus_anim.start()

    def _animate_press(self, target: float) -> None:
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press_progress)
        self._press_anim.setEndValue(target)
        self._press_anim.start()

    # ── Event overrides ─────────────────────────────────────────────────────

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._animate_focus(1.0)
        self._animate_hover(0.0)  # focus supersedes hover
        self.tile_focused.emit(self.app)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self._animate_focus(0.0)

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        if not self.hasFocus():
            self._animate_hover(1.0)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        if not self.hasFocus():
            self._animate_hover(0.0)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._animate_press(1.0)
            self.activated.emit(self.app)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._animate_press(0.0)
        else:
            super().keyReleaseEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._animate_press(1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._animate_press(0.0)
            self.activated.emit(self.app)
        super().mouseReleaseEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._tile_w, self._tile_h)
