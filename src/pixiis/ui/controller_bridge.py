"""Bridge between the controller subsystem and the Qt event loop.

Polls the controller on the main thread via QTimer. All Qt interactions
happen on the main thread — no cross-thread issues.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Qt, Signal
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit

from pixiis.core import get_config

# Xbox button indices (from backend.py)
_BTN_A = 0
_BTN_B = 1
_BTN_LB = 4
_BTN_RB = 5

# Axis indices
_LEFT_STICK_X = 0
_LEFT_STICK_Y = 1
_RIGHT_STICK_Y = 3
_DPAD_X = 6
_DPAD_Y = 7

# Qt key codes
_KEY_UP = Qt.Key.Key_Up
_KEY_DOWN = Qt.Key.Key_Down
_KEY_LEFT = Qt.Key.Key_Left
_KEY_RIGHT = Qt.Key.Key_Right
_KEY_RETURN = Qt.Key.Key_Return
_KEY_ESCAPE = Qt.Key.Key_Escape

# Thresholds
_STICK_DEADZONE = 0.4
_SCROLL_DEADZONE = 0.3

# Nav repeat
_INITIAL_DELAY_MS = 300
_REPEAT_DELAY_MS = 100

# Hot-plug check interval
_HOTPLUG_CHECK_MS = 2000


class ControllerBridge(QObject):
    """Polls the controller on the main thread and injects Qt key events.

    Features:
    - Hot-plug detection (checks for new controllers every 2 seconds)
    - Nav repeat on stick/dpad hold
    - Protects text inputs from synthetic key injection
    - Right stick scrolling
    """

    search_requested = Signal()
    tab_next = Signal()      # RB — next page/tab
    tab_prev = Signal()      # LB — previous page/tab

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._backend = None
        self._prev_buttons: dict[int, bool] = {}
        self._prev_nav: str | None = None  # "up"/"down"/"left"/"right" or None

        # Try to connect a controller
        self._try_connect()

        # Main poll timer — 16ms (~60Hz), always on main thread
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(16)
        self._poll_timer.timeout.connect(self._poll)

        # Nav repeat timer
        self._nav_repeat_timer = QTimer(self)
        self._nav_repeat_timer.setSingleShot(False)
        self._nav_repeat_timer.timeout.connect(self._fire_nav_repeat)
        self._nav_repeat_key: int | None = None
        self._nav_repeat_started = False

        # Hot-plug timer — check for new controllers periodically
        self._hotplug_timer = QTimer(self)
        self._hotplug_timer.setInterval(_HOTPLUG_CHECK_MS)
        self._hotplug_timer.timeout.connect(self._check_hotplug)
        self._hotplug_timer.start()

        # Start polling if connected
        if self._backend is not None:
            self._poll_timer.start()

    def _try_connect(self) -> None:
        """Try to find and connect to a controller backend."""
        try:
            from pixiis.controller.backend import get_backend
            self._backend = get_backend()
            if not self._backend.is_connected():
                self._backend = None
        except Exception:
            self._backend = None

    def _check_hotplug(self) -> None:
        """Periodically check if a controller was plugged in or unplugged."""
        if self._backend is None:
            # No controller — try to find one
            self._try_connect()
            if self._backend is not None:
                self._prev_buttons.clear()
                self._poll_timer.start()
        else:
            # Have a controller — check if still connected
            if not self._backend.is_connected():
                self._backend = None
                self._poll_timer.stop()
                self._nav_repeat_timer.stop()
                self._prev_buttons.clear()

    # ── Polling (main thread, non-blocking) ─────────────────────────────────

    def _poll(self) -> None:
        if self._backend is None:
            return

        try:
            self._backend.poll()
        except Exception:
            self._backend = None
            self._poll_timer.stop()
            return

        if not self._backend.is_connected():
            self._backend = None
            self._poll_timer.stop()
            return

        self._process_buttons()
        self._process_navigation()
        self._process_scroll()

    # ── Button handling (edge detection) ────────────────────────────────────

    def _process_buttons(self) -> None:
        """Detect button press edges (was up, now down)."""
        # A = select, B = back
        for btn_idx, qt_key in ((_BTN_A, _KEY_RETURN), (_BTN_B, _KEY_ESCAPE)):
            now = self._backend.get_button(btn_idx)
            was = self._prev_buttons.get(btn_idx, False)
            if now and not was:
                self._post_key(qt_key)
            self._prev_buttons[btn_idx] = now

        # LB = previous tab, RB = next tab
        for btn_idx, sig in ((_BTN_LB, self.tab_prev), (_BTN_RB, self.tab_next)):
            now = self._backend.get_button(btn_idx)
            was = self._prev_buttons.get(btn_idx, False)
            if now and not was:
                sig.emit()
            self._prev_buttons[btn_idx] = now

    # ── Stick/DPad navigation ──────────────────────────────────────────────

    def _process_navigation(self) -> None:
        """Read sticks/dpad and manage nav repeat."""
        nav_key = self._read_nav_direction()

        if nav_key is not None:
            if nav_key != self._prev_nav:
                # New direction — fire immediately, start repeat timer
                self._prev_nav = nav_key
                self._nav_repeat_key = nav_key
                self._nav_repeat_started = False
                self._post_nav(nav_key)
                self._nav_repeat_timer.start(_INITIAL_DELAY_MS)
        else:
            # Released — stop repeat
            if self._prev_nav is not None:
                self._prev_nav = None
                self._nav_repeat_key = None
                self._nav_repeat_timer.stop()

    def _read_nav_direction(self) -> int | None:
        """Return the Qt key for the current stick/dpad direction, or None."""
        # DPad takes priority
        dx = self._backend.get_axis(_DPAD_X)
        dy = self._backend.get_axis(_DPAD_Y)

        if abs(dx) > 0.5 or abs(dy) > 0.5:
            if abs(dx) > abs(dy):
                return _KEY_LEFT if dx < 0 else _KEY_RIGHT
            else:
                return _KEY_UP if dy < 0 else _KEY_DOWN

        # Left stick
        sx = self._backend.get_axis(_LEFT_STICK_X)
        sy = self._backend.get_axis(_LEFT_STICK_Y)

        if abs(sx) > _STICK_DEADZONE or abs(sy) > _STICK_DEADZONE:
            if abs(sx) > abs(sy):
                return _KEY_LEFT if sx < 0 else _KEY_RIGHT
            else:
                return _KEY_UP if sy < 0 else _KEY_DOWN

        return None

    def _fire_nav_repeat(self) -> None:
        """Fire repeated navigation while stick/dpad is held."""
        if self._nav_repeat_key is None:
            self._nav_repeat_timer.stop()
            return
        if not self._nav_repeat_started:
            self._nav_repeat_started = True
            self._nav_repeat_timer.setInterval(_REPEAT_DELAY_MS)
        self._post_nav(self._nav_repeat_key)

    # ── Right stick scroll ─────────────────────────────────────────────────

    def _process_scroll(self) -> None:
        ry = self._backend.get_axis(_RIGHT_STICK_Y)
        if abs(ry) > _SCROLL_DEADZONE:
            self._post_scroll(ry)

    # ── Key injection helpers ──────────────────────────────────────────────

    @staticmethod
    def _is_text_input() -> bool:
        w = QApplication.focusWidget()
        return w is not None and isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit))

    @staticmethod
    def _post_key(key: int) -> None:
        widget = QApplication.focusWidget()
        if widget is None:
            return
        # Don't inject into text inputs (except Escape to leave)
        if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
            if key != _KEY_ESCAPE:
                return
        QApplication.postEvent(
            widget, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        )
        QApplication.postEvent(
            widget, QKeyEvent(QEvent.Type.KeyRelease, key, Qt.KeyboardModifier.NoModifier)
        )

    @staticmethod
    def _post_nav(key: int) -> None:
        if ControllerBridge._is_text_input():
            return
        widget = QApplication.focusWidget()
        if widget is None:
            return

        # If the focused widget is inside a TileGrid, send arrow keys
        # (TileGrid handles 2D grid navigation internally)
        from pixiis.ui.widgets.tile_grid import TileGrid
        parent = widget
        in_grid = False
        while parent is not None:
            if isinstance(parent, TileGrid):
                in_grid = True
                break
            parent = parent.parentWidget()

        if in_grid:
            ControllerBridge._post_key(key)
        else:
            # Outside grid: use Tab/Shift+Tab for linear focus navigation
            if key in (_KEY_DOWN, _KEY_RIGHT):
                ControllerBridge._post_key(Qt.Key.Key_Tab)
            elif key in (_KEY_UP, _KEY_LEFT):
                ControllerBridge._post_key(Qt.Key.Key_Backtab)

    @staticmethod
    def _post_scroll(value: float) -> None:
        widget = QApplication.focusWidget()
        if widget is None:
            return
        from PySide6.QtCore import QPoint, QPointF
        delta = int(-value * 120)
        QApplication.postEvent(
            widget,
            QWheelEvent(
                QPointF(0, 0), QPointF(0, 0),
                QPoint(0, 0), QPoint(0, delta),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            ),
        )

    # ── Cleanup ────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        self._poll_timer.stop()
        self._nav_repeat_timer.stop()
        self._hotplug_timer.stop()
