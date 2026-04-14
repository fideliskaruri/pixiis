"""Controller backend abstraction — input capture without a window."""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class ControllerBackend(Protocol):
    """Protocol for controller input backends."""

    def poll(self) -> list:
        """Process pending events. Must be called regularly."""
        ...

    def get_button(self, index: int) -> bool:
        """Return True if button *index* is currently held down."""
        ...

    def get_axis(self, index: int) -> float:
        """Return axis value in [-1.0, 1.0]."""
        ...

    def get_name(self) -> str:
        """Human-readable controller name."""
        ...

    def is_connected(self) -> bool:
        """True when a controller is present and responsive."""
        ...


# ── InputsBackend ───────────────────────────────────────────────────────────


class InputsBackend:
    """Global gamepad capture via the *inputs* library (no window needed).

    Falls back gracefully when the ``inputs`` package is not installed.
    """

    def __init__(self) -> None:
        try:
            import inputs  # noqa: F401
            self._inputs = inputs
        except ImportError:
            raise RuntimeError("inputs library is not installed")

        self._buttons: dict[int, bool] = {}
        self._axes: dict[int, float] = {}
        self._name = "Unknown (inputs)"
        self._connected = False

        # inputs button-code → index mapping (common Xbox layout)
        self._btn_map: dict[str, int] = {
            "BTN_SOUTH": 0,   # A
            "BTN_EAST": 1,    # B
            "BTN_WEST": 2,    # X (on some systems NORTH/WEST swap)
            "BTN_NORTH": 3,   # Y
            "BTN_TL": 4,      # LB
            "BTN_TR": 5,      # RB
            "BTN_SELECT": 6,  # Back / View
            "BTN_START": 7,   # Start / Menu
            "BTN_THUMBL": 8,  # Left stick click
            "BTN_THUMBR": 9,  # Right stick click
        }
        self._axis_map: dict[str, int] = {
            "ABS_X": 0,
            "ABS_Y": 1,
            "ABS_RX": 2,
            "ABS_RY": 3,
            "ABS_Z": 4,   # LT
            "ABS_RZ": 5,  # RT
            "ABS_HAT0X": 6,
            "ABS_HAT0Y": 7,
        }

        # Try to detect a gamepad at init time
        try:
            gamepads = self._inputs.devices.gamepads
            if gamepads:
                self._name = gamepads[0].name
                self._connected = True
        except Exception:
            pass

    def poll(self) -> list:
        """Read all pending gamepad events (non-blocking)."""
        raw: list = []
        try:
            events = self._inputs.get_gamepad()
        except self._inputs.UnpluggedError:
            self._connected = False
            return raw
        except Exception:
            return raw

        self._connected = True
        for ev in events:
            if ev.ev_type == "Key":
                idx = self._btn_map.get(ev.code)
                if idx is not None:
                    self._buttons[idx] = bool(ev.state)
                    raw.append(ev)
            elif ev.ev_type == "Absolute":
                idx = self._axis_map.get(ev.code)
                if idx is not None:
                    # Normalize to [-1.0, 1.0].  inputs gives ints;
                    # typical range is -32768..32767 for sticks, 0..255 for triggers.
                    if ev.code in ("ABS_Z", "ABS_RZ"):
                        self._axes[idx] = ev.state / 255.0
                    elif ev.code in ("ABS_HAT0X", "ABS_HAT0Y"):
                        self._axes[idx] = float(ev.state)
                    else:
                        self._axes[idx] = max(-1.0, min(1.0, ev.state / 32767.0))
                    raw.append(ev)
        return raw

    def get_button(self, index: int) -> bool:
        return self._buttons.get(index, False)

    def get_axis(self, index: int) -> float:
        return self._axes.get(index, 0.0)

    def get_name(self) -> str:
        return self._name

    def is_connected(self) -> bool:
        return self._connected


# ── PygameBackend ───────────────────────────────────────────────────────────


class PygameBackend:
    """Fallback backend using pygame.joystick (requires a display/window)."""

    def __init__(self) -> None:
        try:
            import pygame  # noqa: F401
            self._pygame = pygame
        except ImportError:
            raise RuntimeError("pygame is not installed")

        # Only init joystick subsystem — pygame.init() inits display which
        # conflicts with PySide6's Qt event loop on Windows.
        if not self._pygame.joystick.get_init():
            self._pygame.joystick.init()

        self._joystick = None
        if self._pygame.joystick.get_count() > 0:
            self._joystick = self._pygame.joystick.Joystick(0)
            self._joystick.init()

    def poll(self) -> list:
        # pump() requires display init on some platforms. Use get/peek instead.
        try:
            self._pygame.event.get()
        except self._pygame.error:
            pass
        # Re-check connection (hot-plug)
        if self._joystick is None:
            self._pygame.joystick.quit()
            self._pygame.joystick.init()
            if self._pygame.joystick.get_count() > 0:
                self._joystick = self._pygame.joystick.Joystick(0)
                self._joystick.init()
        return []

    def get_button(self, index: int) -> bool:
        if self._joystick is None:
            return False
        try:
            return bool(self._joystick.get_button(index))
        except self._pygame.error:
            return False

    def get_axis(self, index: int) -> float:
        if self._joystick is None:
            return 0.0
        try:
            # Axes 6/7 = D-pad, which is a HAT in pygame, not a stick axis
            if index == 6:  # DPAD_X
                return float(self._joystick.get_hat(0)[0]) if self._joystick.get_numhats() > 0 else 0.0
            if index == 7:  # DPAD_Y
                # pygame hat Y: 1=up, -1=down. We invert to match XInput convention (neg=up)
                hat_y = self._joystick.get_hat(0)[1] if self._joystick.get_numhats() > 0 else 0
                return float(-hat_y)
            return float(self._joystick.get_axis(index))
        except (self._pygame.error, IndexError):
            return 0.0

    def get_name(self) -> str:
        if self._joystick is None:
            return "No controller (pygame)"
        return self._joystick.get_name()

    def is_connected(self) -> bool:
        return self._joystick is not None


# ── Factory ─────────────────────────────────────────────────────────────────


def get_backend() -> ControllerBackend:
    """Return the best available controller backend.

    Prefers PygameBackend (non-blocking poll, safe with Qt event loop).
    Falls back to InputsBackend (global capture, but poll() may block).
    """
    try:
        return PygameBackend()
    except RuntimeError:
        pass
    try:
        return PygameBackend()
    except RuntimeError:
        pass
    raise RuntimeError(
        "No controller backend available. Install 'inputs' or 'pygame'."
    )
