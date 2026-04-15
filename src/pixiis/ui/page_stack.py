"""Animated stacked-widget page container."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    Qt,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget


class PageStack(QStackedWidget):
    """A :class:`QStackedWidget` that slides pages in/out with animation.

    Pages are registered by name and switched via :meth:`switch_to`.
    """

    DURATION_MS = 250

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pages: dict[str, QWidget] = {}
        self._current_name: str = ""
        self._animating = False
        self._focus_memory: dict[str, QWidget] = {}  # page name -> last focused widget

    # -- public API ----------------------------------------------------------

    def register_page(self, name: str, widget: QWidget) -> None:
        """Add a page by *name*."""
        self._pages[name] = widget
        self.addWidget(widget)
        if not self._current_name:
            self._current_name = name
            self.setCurrentWidget(widget)

    def switch_to(self, name: str, direction: str = "right") -> None:
        """Animate a transition to the page registered as *name*.

        *direction* controls slide direction: ``"right"`` slides the new
        page in from the right, ``"left"`` from the left.
        """
        if name == self._current_name or name not in self._pages:
            return
        if self._animating:
            return

        outgoing = self._pages.get(self._current_name)
        incoming = self._pages[name]

        if outgoing is None:
            self.setCurrentWidget(incoming)
            self._current_name = name
            return

        # Save the currently focused widget for the outgoing page
        from PySide6.QtWidgets import QApplication
        focus_widget = QApplication.focusWidget()
        if focus_widget is not None and self._current_name:
            self._focus_memory[self._current_name] = focus_widget

        self._animating = True
        width = self.width()

        # Direction multiplier: +1 for "right" (new comes from right),
        # -1 for "left" (new comes from left).
        sign = 1 if direction == "right" else -1

        # Ensure both widgets are visible for the animation
        incoming.show()
        incoming.raise_()
        outgoing.show()

        # -- outgoing slide out ----------------------------------------------
        out_anim = QPropertyAnimation(outgoing, b"pos", self)
        out_anim.setDuration(self.DURATION_MS)
        out_anim.setStartValue(QPoint(0, 0))
        out_anim.setEndValue(QPoint(-sign * width, 0))
        out_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # -- outgoing fade ---------------------------------------------------
        opacity_effect = QGraphicsOpacityEffect(outgoing)
        outgoing.setGraphicsEffect(opacity_effect)

        fade_anim = QPropertyAnimation(opacity_effect, b"opacity", self)
        fade_anim.setDuration(self.DURATION_MS)
        fade_anim.setStartValue(1.0)
        fade_anim.setEndValue(0.0)
        fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # -- incoming slide in -----------------------------------------------
        in_anim = QPropertyAnimation(incoming, b"pos", self)
        in_anim.setDuration(self.DURATION_MS)
        in_anim.setStartValue(QPoint(sign * width, 0))
        in_anim.setEndValue(QPoint(0, 0))
        in_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # -- run together ----------------------------------------------------
        group = QParallelAnimationGroup(self)
        group.addAnimation(out_anim)
        group.addAnimation(fade_anim)
        group.addAnimation(in_anim)

        def _on_finished() -> None:
            self.setCurrentWidget(incoming)
            outgoing.move(0, 0)
            outgoing.setGraphicsEffect(None)
            self._current_name = name
            self._animating = False
            # Restore remembered focus widget, or fall back to first focusable child
            remembered = self._focus_memory.get(name)
            if remembered is not None and remembered.isVisible():
                remembered.setFocus()
            else:
                for child in incoming.findChildren(QWidget):
                    if child.focusPolicy() != Qt.FocusPolicy.NoFocus and child.isVisibleTo(incoming):
                        child.setFocus()
                        break

        group.finished.connect(_on_finished)
        group.start()

    def current_page_name(self) -> str:
        """Return the name of the currently visible page."""
        return self._current_name
