"""Xbox controller vibration via XInput (Windows-only)."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer

from pixiis.core import ActionType, MacroAction, NavigationEvent, bus

if TYPE_CHECKING:
    from ctypes import Structure


def _load_xinput() -> tuple | None:
    """Load XInput and return (set_state_fn, VibrationStruct) or None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import Structure, WinDLL, c_ushort

        class XINPUT_VIBRATION(Structure):
            _fields_ = [
                ("wLeftMotorSpeed", c_ushort),
                ("wRightMotorSpeed", c_ushort),
            ]

        xinput = WinDLL("xinput1_4.dll")
        set_state = xinput.XInputSetState
        set_state.argtypes = [ctypes.c_uint, ctypes.POINTER(XINPUT_VIBRATION)]
        set_state.restype = ctypes.c_uint
        return set_state, XINPUT_VIBRATION
    except (OSError, AttributeError):
        return None


class VibrationService(QObject):
    """Haptic feedback via Xbox controller rumble motors.

    On non-Windows platforms (or when XInput is unavailable) all methods
    are silent no-ops.
    """

    def __init__(self, controller_index: int = 0, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._index = controller_index
        self._xinput = _load_xinput()

        bus.subscribe(NavigationEvent, self._on_navigation)
        bus.subscribe(MacroAction, self._on_macro)

    # ── public API ──────────────────────────────────────────────────────

    def pulse(self, left: int = 0, right: int = 0, duration_ms: int = 100) -> None:
        """Set motors for *duration_ms* then stop.

        Motor values range 0-65535.
        """
        self._set_motors(left, right)
        QTimer.singleShot(duration_ms, self.stop)

    def stop(self) -> None:
        """Stop both rumble motors."""
        self._set_motors(0, 0)

    # ── presets ──────────────────────────────────────────────────────────

    def rumble_confirm(self) -> None:
        """Light pulse for confirmations."""
        self.pulse(left=20000, right=20000, duration_ms=80)

    def rumble_back(self) -> None:
        """Short right-motor tap for back/cancel."""
        self.pulse(left=0, right=25000, duration_ms=50)

    def rumble_launch(self) -> None:
        """Strong pulse for app launch."""
        self.pulse(left=45000, right=45000, duration_ms=200)

    # ── event handlers ──────────────────────────────────────────────────

    def _on_navigation(self, _event: NavigationEvent) -> None:
        """Micro pulse on d-pad / stick navigation."""
        self.pulse(left=8000, right=8000, duration_ms=40)

    def _on_macro(self, event: MacroAction) -> None:
        if event.action == ActionType.LAUNCH_APP:
            self.rumble_launch()
        elif event.action == ActionType.NAVIGATE_UI:
            if event.target == "back":
                self.rumble_back()
            else:
                self.rumble_confirm()

    # ── internal ────────────────────────────────────────────────────────

    def _set_motors(self, left: int, right: int) -> None:
        if self._xinput is None:
            return
        set_state, XINPUT_VIBRATION = self._xinput
        vibration = XINPUT_VIBRATION(left, right)
        set_state(self._index, vibration)

    def shutdown(self) -> None:
        """Unsubscribe from EventBus and stop motors."""
        bus.unsubscribe(NavigationEvent, self._on_navigation)
        bus.unsubscribe(MacroAction, self._on_macro)
        self.stop()
