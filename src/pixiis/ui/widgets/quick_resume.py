"""Quick Resume overlay — recent games list triggered by Start button."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

if TYPE_CHECKING:
    from pixiis.core.types import AppEntry

# ── Dark Cinema palette ───────────────────────────────────────────────────

_OVERLAY_BG = QColor(13, 12, 20, 200)   # deep dark @ 78%
_CARD_BG = QColor(28, 26, 36)           # #1c1a24
_CARD_SELECTED = QColor(37, 35, 48)     # surface_hover
_ACCENT = QColor("#e94560")
_TEXT_PRIMARY = QColor("#f0eef5")
_TEXT_SECONDARY = QColor("#8a8698")
_TEXT_MUTED = QColor("#7a7690")

# ── Fonts ────────────────────────────────────────────────────────────────

_TITLE_FONT = QFont()
_TITLE_FONT.setPixelSize(14)
_TITLE_FONT.setBold(True)

_NAME_FONT = QFont()
_NAME_FONT.setPixelSize(16)
_NAME_FONT.setBold(True)

_TIME_FONT = QFont()
_TIME_FONT.setPixelSize(12)

_HINT_FONT = QFont()
_HINT_FONT.setPixelSize(11)

# ── Layout constants ─────────────────────────────────────────────────────

_CARD_W = 400
_CARD_H = 56
_CARD_GAP = 6
_ICON_SIZE = 36


def _time_ago(epoch: float) -> str:
    """Return a human-readable 'X ago' string."""
    if epoch <= 0:
        return "Never played"
    delta = time.time() - epoch
    if delta < 60:
        return "Just now"
    if delta < 3600:
        mins = int(delta / 60)
        return f"{mins} min ago"
    if delta < 86400:
        hours = int(delta / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(delta / 86400)
    if days == 1:
        return "Yesterday"
    if days < 30:
        return f"{days} days ago"
    months = int(days / 30)
    return f"{months} month{'s' if months != 1 else ''} ago"


class QuickResume(QWidget):
    """Semi-transparent overlay showing 5 most recently played games.

    D-pad UP/DOWN navigates, A launches, B dismisses.
    Fade in/out animation (200ms).
    """

    launch_requested = Signal(object)  # AppEntry
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._games: list[AppEntry] = []
        self._selected = 0

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Opacity effect for fade animation
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_in_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_in_anim.setDuration(200)
        self._fade_in_anim.setStartValue(0.0)
        self._fade_in_anim.setEndValue(1.0)
        self._fade_in_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_out_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_out_anim.setDuration(200)
        self._fade_out_anim.setStartValue(1.0)
        self._fade_out_anim.setEndValue(0.0)
        self._fade_out_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out_anim.finished.connect(self._on_fade_out_done)

        self.hide()

    # -- public API ----------------------------------------------------------

    def show_overlay(self, games: list[AppEntry]) -> None:
        """Show with the given list of recent games."""
        self._games = games[:5]
        self._selected = 0

        # Resize to fill parent
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(0, 0, parent.width(), parent.height())

        self._fade_out_anim.stop()
        self._opacity_effect.setOpacity(0.0)
        self.show()
        self.raise_()
        self.setFocus()
        self._fade_in_anim.start()
        self.update()

    def dismiss(self) -> None:
        """Fade out and hide."""
        self._fade_in_anim.stop()
        self._fade_out_anim.setStartValue(self._opacity_effect.opacity())
        self._fade_out_anim.start()

    def is_showing(self) -> bool:
        """Return True if overlay is visible and not fading out."""
        return self.isVisible() and self._opacity_effect.opacity() > 0.01

    # -- key input -----------------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Up:
            if self._games:
                self._selected = (self._selected - 1) % len(self._games)
                self.update()
        elif key == Qt.Key.Key_Down:
            if self._games:
                self._selected = (self._selected + 1) % len(self._games)
                self.update()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            if self._games:
                self.launch_requested.emit(self._games[self._selected])
                self.dismiss()
        elif key == Qt.Key.Key_Escape:
            self.dismiss()
            self.dismissed.emit()
        else:
            super().keyPressEvent(event)

    # -- internal ------------------------------------------------------------

    def _on_fade_out_done(self) -> None:
        self.hide()

    # -- painting ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Full-screen semi-transparent background
        p.fillRect(0, 0, w, h, _OVERLAY_BG)

        if not self._games:
            # No recent games message
            p.setPen(_TEXT_MUTED)
            p.setFont(_NAME_FONT)
            p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "No recently played games")
            p.end()
            return

        # Center the card list vertically
        n = len(self._games)
        total_h = n * _CARD_H + (n - 1) * _CARD_GAP + 60  # 60 for title + hint
        y_start = (h - total_h) // 2
        x_start = (w - _CARD_W) // 2

        # Title
        p.setPen(_TEXT_SECONDARY)
        p.setFont(_TITLE_FONT)
        p.drawText(x_start, y_start, _CARD_W, 24, Qt.AlignmentFlag.AlignLeft, "QUICK RESUME")
        y_start += 30

        # Cards
        for i, game in enumerate(self._games):
            y = y_start + i * (_CARD_H + _CARD_GAP)
            selected = i == self._selected

            # Card background
            card_path = QPainterPath()
            card_path.addRoundedRect(
                float(x_start), float(y),
                float(_CARD_W), float(_CARD_H),
                8.0, 8.0,
            )

            if selected:
                p.fillPath(card_path, _CARD_SELECTED)
                # Accent left edge
                edge = QPainterPath()
                edge.addRoundedRect(
                    float(x_start), float(y),
                    4.0, float(_CARD_H),
                    2.0, 2.0,
                )
                p.fillPath(edge, _ACCENT)
            else:
                p.fillPath(card_path, _CARD_BG)

            # Game icon placeholder (first letter in a circle)
            icon_x = x_start + 12
            icon_y = y + (_CARD_H - _ICON_SIZE) // 2
            icon_path = QPainterPath()
            icon_path.addRoundedRect(
                float(icon_x), float(icon_y),
                float(_ICON_SIZE), float(_ICON_SIZE),
                6.0, 6.0,
            )
            p.fillPath(icon_path, QColor(45, 43, 58))
            p.setPen(_ACCENT if selected else _TEXT_SECONDARY)
            p.setFont(_NAME_FONT)
            first_char = game.name[0].upper() if game.name else "?"
            p.drawText(
                icon_x, icon_y, _ICON_SIZE, _ICON_SIZE,
                Qt.AlignmentFlag.AlignCenter, first_char,
            )

            # Game name
            text_x = icon_x + _ICON_SIZE + 12
            text_w = _CARD_W - _ICON_SIZE - 36
            p.setPen(_TEXT_PRIMARY if selected else _TEXT_SECONDARY)
            p.setFont(_NAME_FONT)
            p.drawText(
                text_x, y + 8, text_w, 22,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                game.name,
            )

            # Time ago
            p.setPen(_TEXT_MUTED)
            p.setFont(_TIME_FONT)
            last = game.metadata.get("last_played", 0)
            p.drawText(
                text_x, y + 30, text_w, 18,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                _time_ago(float(last)),
            )

        # Hints at bottom
        hint_y = y_start + n * (_CARD_H + _CARD_GAP) + 8
        p.setPen(_TEXT_MUTED)
        p.setFont(_HINT_FONT)
        p.drawText(
            x_start, hint_y, _CARD_W, 20,
            Qt.AlignmentFlag.AlignCenter,
            "A  Launch    B  Dismiss",
        )

        p.end()
