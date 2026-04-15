"""Bridge between the controller subsystem and the Qt event loop.

Polls the controller on the main thread via QTimer. All Qt interactions
happen on the main thread — no cross-thread issues.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Qt, Signal
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QLineEdit,
    QPlainTextEdit,
    QSlider,
    QSpinBox,
    QTextEdit,
)

import time as _time

from pixiis.core import get_config, bus as _bus
from pixiis.core.types import NavigationEvent, Direction

# Xbox button indices (from backend.py)
_BTN_A = 0
_BTN_B = 1
_BTN_LB = 4
_BTN_RB = 5
_BTN_START = 7   # Menu/hamburger button
_BTN_SELECT = 6  # View/back button

# Axis indices
_LEFT_STICK_X = 0
_LEFT_STICK_Y = 1
_RIGHT_STICK_Y = 3
_LEFT_TRIGGER = 4   # LT — analog 0.0 to 1.0
_RIGHT_TRIGGER = 5  # RT — analog 0.0 to 1.0
_DPAD_X = 6
_DPAD_Y = 7

# Button indices for hold-style voice triggers
_BTN_X = 2
_BTN_Y = 3

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
    voice_start = Signal()   # RT — start voice recording
    voice_stop = Signal()    # RT release — stop voice recording
    toggle_app = Signal()    # Start button — hide/show app

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._backend = None
        self._prev_buttons: dict[int, bool] = {}
        self._prev_nav: str | None = None

        # Voice trigger config: "rt", "lt", "hold_y", "hold_x"
        cfg = get_config()
        self._voice_trigger_mode: str = str(cfg.get("controller.voice_trigger", "rt"))

        # Voice trigger state (works for both analog and button modes)
        self._rt_active = False

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

        self._process_voice_trigger()
        self._process_buttons()
        self._process_navigation()
        self._process_scroll()

    # ── Button handling (edge detection) ────────────────────────────────────

    def _process_buttons(self) -> None:
        """Detect button press edges."""
        # Determine which button is reserved for voice (if any)
        _voice_btn = {
            "hold_y": _BTN_Y,
            "hold_x": _BTN_X,
        }.get(self._voice_trigger_mode)

        # A = select/activate, B = back
        # A sends Space (activates QPushButton, QCheckBox, QComboBox etc.)
        # AND Return (activates QLineEdit submit, custom keyPressEvent handlers)
        a_now = self._backend.get_button(_BTN_A)
        a_was = self._prev_buttons.get(_BTN_A, False)
        if _BTN_A != _voice_btn and a_now and not a_was:
            self._post_key(Qt.Key.Key_Space)
            self._post_key(_KEY_RETURN)
        self._prev_buttons[_BTN_A] = a_now

        # B = back/escape
        b_now = self._backend.get_button(_BTN_B)
        b_was = self._prev_buttons.get(_BTN_B, False)
        if _BTN_B != _voice_btn and b_now and not b_was:
            self._post_key(_KEY_ESCAPE)
        self._prev_buttons[_BTN_B] = b_now

        # LB/RB = page switching
        for btn_idx, sig in ((_BTN_LB, self.tab_prev), (_BTN_RB, self.tab_next)):
            now = self._backend.get_button(btn_idx)
            was = self._prev_buttons.get(btn_idx, False)
            if now and not was:
                sig.emit()
            self._prev_buttons[btn_idx] = now

        # Start button = toggle hide/show app
        start_now = self._backend.get_button(_BTN_START)
        start_was = self._prev_buttons.get(_BTN_START, False)
        if start_now and not start_was:
            self.toggle_app.emit()
        self._prev_buttons[_BTN_START] = start_now

    def _process_voice_trigger(self) -> None:
        """Configurable voice trigger — analog trigger or button hold."""
        mode = self._voice_trigger_mode
        if mode in ("rt", "lt"):
            axis = _RIGHT_TRIGGER if mode == "rt" else _LEFT_TRIGGER
            val = self._backend.get_axis(axis)
            if val > 0.5 and not self._rt_active:
                self._rt_active = True
                self.voice_start.emit()
            elif val <= 0.3 and self._rt_active:
                self._rt_active = False
                self.voice_stop.emit()
        else:
            # hold_y or hold_x
            btn = _BTN_Y if mode == "hold_y" else _BTN_X
            pressed = self._backend.get_button(btn)
            if pressed and not self._rt_active:
                self._rt_active = True
                self.voice_start.emit()
            elif not pressed and self._rt_active:
                self._rt_active = False
                self.voice_stop.emit()

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
                _dir_map = {_KEY_UP: Direction.UP, _KEY_DOWN: Direction.DOWN, _KEY_LEFT: Direction.LEFT, _KEY_RIGHT: Direction.RIGHT}
                d = _dir_map.get(nav_key)
                if d:
                    _bus.publish(NavigationEvent(direction=d, timestamp=_time.monotonic()))
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
        """Move focus to the nearest focusable widget in the D-pad direction.

        Dead simple spatial navigation — no zones, no Tab/Backtab.
        Just finds the closest widget in the direction you pressed.
        """
        # Text inputs: UP/DOWN escape, LEFT/RIGHT stay for cursor
        if ControllerBridge._is_text_input():
            if key not in (_KEY_DOWN, _KEY_UP):
                return

        current = QApplication.focusWidget()
        if current is None:
            return

        # Value-editing controls need special D-pad handling:
        #   - QSlider, QSpinBox, QDoubleSpinBox consume arrow keys to change
        #     their value. LEFT/RIGHT should adjust value, but UP/DOWN must
        #     navigate away so the user isn't trapped on the control.
        if isinstance(current, (QSlider, QSpinBox, QDoubleSpinBox)):
            if key in (_KEY_UP, _KEY_DOWN):
                # Always navigate away — never let the widget eat UP/DOWN
                ControllerBridge._spatial_focus_move(current, key)
                return
            # LEFT/RIGHT: let the widget adjust its value normally
            ControllerBridge._post_key(key)
            return

        # Send arrow key synchronously to the focused widget first.
        press = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(current, press)

        # If focus moved, the widget handled it — done.
        new_focus = QApplication.focusWidget()
        if new_focus is not current and new_focus is not None:
            return

        # sendEvent does NOT propagate to parents. If the leaf widget
        # (e.g. GameTile) ignored the arrow, walk up to find a parent
        # container that does 2D navigation (TileGrid, QTreeView, etc.)
        from pixiis.ui.widgets.tile_grid import TileGrid
        from PySide6.QtWidgets import QTreeView
        parent = current.parentWidget()
        while parent is not None:
            if isinstance(parent, (TileGrid, QTreeView)):
                parent_press = QKeyEvent(
                    QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier
                )
                QApplication.sendEvent(parent, parent_press)
                new_focus = QApplication.focusWidget()
                if new_focus is not current and new_focus is not None:
                    return
                break
            parent = parent.parentWidget()

        # No parent handler moved focus — fall back to spatial search
        ControllerBridge._spatial_focus_move(current, key)

    @staticmethod
    def _spatial_focus_move(current: QWidget, direction: int) -> None:
        """Find the nearest focusable widget in the given direction and focus it.

        Pure geometry — no zones, no special cases. Works like a console.
        """
        from PySide6.QtWidgets import QWidget as QW
        from PySide6.QtCore import QRect

        window = current.window()
        if window is None:
            return

        # Get current widget's center in global coords
        cur_rect = current.rect()
        cur_center = current.mapToGlobal(cur_rect.center())
        cx, cy = cur_center.x(), cur_center.y()

        best = None
        best_dist = float("inf")

        # Skip nav bar widgets — they're reached via LB/RB, not D-pad
        from pixiis.ui.widgets.sidebar import Sidebar

        # Search all focusable, visible widgets in the window
        for child in window.findChildren(QW):
            if child is current:
                continue
            if not child.isVisibleTo(window):
                continue
            if child.focusPolicy() == Qt.FocusPolicy.NoFocus:
                continue
            # Exclude sidebar/nav bar children from spatial search
            p = child.parentWidget()
            in_sidebar = False
            while p is not None:
                if isinstance(p, Sidebar):
                    in_sidebar = True
                    break
                p = p.parentWidget()
            if in_sidebar:
                continue
            # Skip containers (scroll areas, frames) — only leaf widgets
            if child.findChildren(QW, options=Qt.FindChildOption.FindDirectChildrenOnly):
                # Has focusable children — skip the container itself
                has_focusable_child = False
                for sub in child.findChildren(QW):
                    if sub.focusPolicy() != Qt.FocusPolicy.NoFocus and sub.isVisibleTo(window):
                        has_focusable_child = True
                        break
                if has_focusable_child:
                    continue

            # Get candidate center in global coords
            c_rect = child.rect()
            c_center = child.mapToGlobal(c_rect.center())
            tx, ty = c_center.x(), c_center.y()

            # Check direction constraint
            if direction == _KEY_RIGHT and tx <= cx + 5:
                continue
            elif direction == _KEY_LEFT and tx >= cx - 5:
                continue
            elif direction == _KEY_DOWN and ty <= cy + 5:
                continue
            elif direction == _KEY_UP and ty >= cy - 5:
                continue

            # Distance: weight the perpendicular axis more to prefer
            # widgets in the same row/column
            if direction in (_KEY_LEFT, _KEY_RIGHT):
                dist = abs(tx - cx) + abs(ty - cy) * 3
            else:
                dist = abs(ty - cy) + abs(tx - cx) * 3

            if dist < best_dist:
                best_dist = dist
                best = child

        if best is not None:
            best.setFocus()

    @staticmethod
    def _post_scroll(value: float) -> None:
        """Send scroll event to the nearest parent QScrollArea."""
        widget = QApplication.focusWidget()
        if widget is None:
            return
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtWidgets import QScrollArea

        # Find the nearest parent scroll area — wheel events should go
        # there, not to the leaf widget which might swallow them.
        target = widget
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                target = parent
                break
            parent = parent.parentWidget()

        delta = int(-value * 120)
        QApplication.postEvent(
            target,
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
