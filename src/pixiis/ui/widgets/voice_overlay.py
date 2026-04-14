"""Floating voice-transcription overlay widget."""

from __future__ import annotations

from PySide6.QtCore import (
    QPoint,
    QPropertyAnimation,
    QEasingCurve,
    Qt,
    QTimer,
    Slot,
)
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from pixiis.core.events import bus
from pixiis.core.types import TranscriptionEvent


class VoiceOverlay(QWidget):
    """Semi-transparent overlay that shows live transcription text.

    Subscribes to :class:`TranscriptionEvent` on the global EventBus.
    Positioned at the bottom-centre of the primary screen by default,
    but can be dragged to a custom position.
    """

    _AUTO_HIDE_MS = 5000
    _FADE_IN_MS = 150
    _FADE_OUT_MS = 400

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ── window flags ────────────────────────────────────────────
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.0)

        # ── layout ──────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 14)

        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setMaximumWidth(600)
        self._label.setStyleSheet(
            "QLabel {"
            "  color: #ffffff;"
            "  font-size: 20pt;"
            "  background: transparent;"
            "}"
        )
        layout.addWidget(self._label)

        self.setStyleSheet(
            "VoiceOverlay {"
            "  background-color: rgba(26, 26, 46, 217);"  # #1a1a2e @ 85%
            "  border-radius: 16px;"
            "}"
        )

        # ── animations ──────────────────────────────────────────────
        self._fade_in = QPropertyAnimation(self, b"windowOpacity")
        self._fade_in.setDuration(self._FADE_IN_MS)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)

        self._fade_out = QPropertyAnimation(self, b"windowOpacity")
        self._fade_out.setDuration(self._FADE_OUT_MS)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.InCubic)
        self._fade_out.finished.connect(self.hide)

        # ── auto-hide timer ─────────────────────────────────────────
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._begin_fade_out)

        # ── dragging state ──────────────────────────────────────────
        self._drag_pos: QPoint | None = None
        self._custom_pos: QPoint | None = None

        # ── subscribe to transcription events ───────────────────────
        bus.subscribe(TranscriptionEvent, self._on_transcription)

    # ── public API ──────────────────────────────────────────────────

    def show_text(self, text: str, is_final: bool) -> None:
        """Display *text* in the overlay and restart the auto-hide timer."""
        if is_final:
            self._label.setStyleSheet(
                "QLabel {"
                "  color: #ffffff;"
                "  font-size: 20pt;"
                "  background: transparent;"
                "}"
            )
        else:
            self._label.setStyleSheet(
                "QLabel {"
                "  color: rgba(255, 255, 255, 178);"  # ~70% opacity
                "  font-size: 20pt;"
                "  background: transparent;"
                "}"
            )

        self._label.setText(text)
        self.adjustSize()
        self._position_on_screen()

        # Stop any running fade-out before showing.
        self._fade_out.stop()
        self._hide_timer.stop()

        if not self.isVisible():
            self.show()
            self._fade_in.stop()
            self.setWindowOpacity(0.0)
            self._fade_in.start()
        elif self.windowOpacity() < 1.0:
            self._fade_in.stop()
            self._fade_in.setStartValue(self.windowOpacity())
            self._fade_in.start()

        self._hide_timer.start(self._AUTO_HIDE_MS)

    def cleanup(self) -> None:
        """Unsubscribe from the event bus."""
        bus.unsubscribe(TranscriptionEvent, self._on_transcription)

    # ── internal ────────────────────────────────────────────────────

    @Slot()
    def _begin_fade_out(self) -> None:
        self._fade_out.setStartValue(self.windowOpacity())
        self._fade_out.start()

    def _on_transcription(self, event: TranscriptionEvent) -> None:
        # EventBus callbacks may arrive from non-GUI threads; use
        # QTimer.singleShot(0, ...) to marshal onto the main thread.
        QTimer.singleShot(0, lambda: self.show_text(event.text, event.is_final))

    def _position_on_screen(self) -> None:
        """Place the overlay at the bottom-centre of the primary screen,
        unless the user has dragged it elsewhere."""
        if self._custom_pos is not None:
            self.move(self._custom_pos)
            return

        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + geo.height() - self.height() - 80
        self.move(x, y)

    # ── dragging ────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            self._custom_pos = new_pos
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        event.accept()
