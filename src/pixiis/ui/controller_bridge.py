"""Bridge between the controller subsystem and the Qt event loop."""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject, QThread, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit

from pixiis.core import (
    ActionType,
    AxisEvent,
    ButtonState,
    ControllerEvent,
    Direction,
    MacroAction,
    NavigationEvent,
    bus,
)


# Axis indices for Xbox-style controllers (from backend.py mapping)
_RIGHT_STICK_Y = 3
_LEFT_STICK_X = 0
_LEFT_STICK_Y = 1
_DPAD_X = 6
_DPAD_Y = 7

# Navigation repeat timing
_INITIAL_DELAY_MS = 300
_REPEAT_DELAY_MS = 120

_DIRECTION_TO_KEY = {
    Direction.UP: 0x01000013,     # Qt.Key.Key_Up
    Direction.DOWN: 0x01000015,   # Qt.Key.Key_Down
    Direction.LEFT: 0x01000012,   # Qt.Key.Key_Left
    Direction.RIGHT: 0x01000014,  # Qt.Key.Key_Right
}

_KEY_RETURN = 0x01000004   # Qt.Key.Key_Return
_KEY_ESCAPE = 0x01000000   # Qt.Key.Key_Escape


class ControllerBridge(QObject):
    """Polls the controller and translates input events into Qt key/wheel events.

    Owns a 16ms QTimer (~60 Hz) that drives :meth:`ButtonMapper.poll`.
    Subscribes to :class:`NavigationEvent` and :class:`MacroAction` on the
    global event bus and injects synthetic Qt events into the focused widget.
    """

    search_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._mapper = None
        self._macro_engine = None

        # Try to set up the controller backend
        try:
            from pixiis.controller import ButtonMapper, MacroEngine, get_backend

            backend = get_backend()
            self._mapper = ButtonMapper(backend)
            self._macro_engine = MacroEngine()
        except Exception:
            # No controller available — bridge will be inert
            pass

        # Navigation repeat state
        self._nav_repeat_timer = QTimer(self)
        self._nav_repeat_timer.timeout.connect(self._on_nav_repeat)
        self._last_nav_direction: Direction | None = None
        self._nav_initial_fired = False

        # Poll on a background thread to avoid blocking the Qt event loop
        # (inputs.get_gamepad() is a blocking call)
        self._poll_thread: QThread | None = None
        self._poll_running = False
        if self._mapper is not None:
            self._start_poll_thread()

        # Subscribe to events
        bus.subscribe(NavigationEvent, self._on_navigation)
        bus.subscribe(MacroAction, self._on_macro)
        bus.subscribe(ControllerEvent, self._on_controller_button)
        bus.subscribe(AxisEvent, self._on_axis)

    # -- polling (background thread) -----------------------------------------

    def _start_poll_thread(self) -> None:
        """Start a daemon thread that polls the controller without blocking Qt."""
        import threading

        self._poll_running = True

        def _poll_loop():
            while self._poll_running:
                try:
                    if self._mapper is not None:
                        self._mapper.poll()
                except Exception:
                    pass
                time.sleep(0.016)  # ~60Hz

        t = threading.Thread(target=_poll_loop, daemon=True)
        t.start()

    # -- controller button events --------------------------------------------

    def _on_controller_button(self, event: ControllerEvent) -> None:
        if event.state != ButtonState.PRESSED:
            return

        if event.button == 0:
            # Xbox A → Enter
            self._post_key(_KEY_RETURN)
        elif event.button == 1:
            # Xbox B → Escape
            self._post_key(_KEY_ESCAPE)

    # -- axis events (right stick → scroll) ----------------------------------

    def _on_axis(self, event: AxisEvent) -> None:
        if event.axis == _RIGHT_STICK_Y and abs(event.value) > 0.3:
            self._post_scroll(event.value)

        # Left stick / D-pad → navigation with repeat
        direction: Direction | None = None
        if event.axis == _LEFT_STICK_Y or event.axis == _DPAD_Y:
            if event.value < -0.5:
                direction = Direction.UP
            elif event.value > 0.5:
                direction = Direction.DOWN
        elif event.axis == _LEFT_STICK_X or event.axis == _DPAD_X:
            if event.value < -0.5:
                direction = Direction.LEFT
            elif event.value > 0.5:
                direction = Direction.RIGHT

        if direction is not None:
            if direction != self._last_nav_direction:
                self._last_nav_direction = direction
                self._nav_initial_fired = False
                self._nav_repeat_timer.start(_INITIAL_DELAY_MS)
                # Fire immediately on first deflection
                self._post_nav_key(direction)
        else:
            # Axis returned to center
            if event.axis in (_LEFT_STICK_X, _LEFT_STICK_Y, _DPAD_X, _DPAD_Y):
                self._last_nav_direction = None
                self._nav_repeat_timer.stop()

    def _on_nav_repeat(self) -> None:
        if self._last_nav_direction is None:
            self._nav_repeat_timer.stop()
            return
        if not self._nav_initial_fired:
            self._nav_initial_fired = True
            self._nav_repeat_timer.setInterval(_REPEAT_DELAY_MS)
        self._post_nav_key(self._last_nav_direction)

    # -- navigation events ---------------------------------------------------

    def _on_navigation(self, event: NavigationEvent) -> None:
        self._post_nav_key(event.direction)

    # -- macro events --------------------------------------------------------

    def _on_macro(self, event: MacroAction) -> None:
        if event.action != ActionType.NAVIGATE_UI:
            return
        if event.target == "back":
            self._post_key(_KEY_ESCAPE)
        elif event.target == "search":
            self.search_requested.emit()

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _is_text_input_focused() -> bool:
        """Return True if the currently focused widget is a text input."""
        widget = QApplication.focusWidget()
        if widget is None:
            return False
        return isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit))

    @staticmethod
    def _post_key(key: int) -> None:
        widget = QApplication.focusWidget()
        if widget is None:
            return
        # Don't inject nav/action keys into text inputs — let them type normally
        if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
            # Only allow Escape (to leave the text field)
            if key != _KEY_ESCAPE:
                return
        press = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        release = QKeyEvent(QEvent.Type.KeyRelease, key, Qt.KeyboardModifier.NoModifier)
        QApplication.postEvent(widget, press)
        QApplication.postEvent(widget, release)

    @staticmethod
    def _post_nav_key(direction: Direction) -> None:
        # Don't inject arrow keys into text inputs
        if ControllerBridge._is_text_input_focused():
            return
        key = _DIRECTION_TO_KEY.get(direction)
        if key is not None:
            ControllerBridge._post_key(key)

    @staticmethod
    def _post_scroll(value: float) -> None:
        widget = QApplication.focusWidget()
        if widget is None:
            return
        from PySide6.QtCore import QPoint, QPointF

        # Negative value = stick pushed up = scroll up (positive delta)
        delta = int(-value * 120)
        angle_delta = QPoint(0, delta)
        event = QWheelEvent(
            QPointF(0, 0),           # pos
            QPointF(0, 0),           # globalPos
            QPoint(0, 0),            # pixelDelta
            angle_delta,             # angleDelta
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,                   # inverted
        )
        QApplication.postEvent(widget, event)

    def shutdown(self) -> None:
        """Stop polling and unsubscribe from the event bus."""
        self._poll_running = False
        self._nav_repeat_timer.stop()
        bus.unsubscribe(NavigationEvent, self._on_navigation)
        bus.unsubscribe(MacroAction, self._on_macro)
        bus.unsubscribe(ControllerEvent, self._on_controller_button)
        bus.unsubscribe(AxisEvent, self._on_axis)
        if self._macro_engine is not None:
            self._macro_engine.shutdown()
