"""Button state tracking and event detection for Pixiis controllers."""

from __future__ import annotations

import time
from dataclasses import dataclass

from pixiis.core import (
    AxisEvent,
    ButtonState,
    ControllerEvent,
    bus,
    get_config,
)
from pixiis.controller.backend import ControllerBackend


@dataclass
class _ButtonTrack:
    """Internal per-button state tracker."""

    down: bool = False
    down_since: float = 0.0
    held_fired: bool = False


class ButtonMapper:
    """Wraps a ControllerBackend, detecting press/hold/release and combos.

    Publishes :class:`ControllerEvent` and :class:`AxisEvent` on the global
    event bus each time :meth:`poll` is called.
    """

    def __init__(self, backend: ControllerBackend, *, num_buttons: int = 16) -> None:
        self._backend = backend
        cfg = get_config()
        self._hold_threshold: float = cfg.get("controller.hold_threshold_ms", 200) / 1000.0
        self._combo_window: float = cfg.get("controller.combo_window_ms", 150) / 1000.0
        self._deadzone: float = cfg.get("controller.deadzone", 0.15)

        self._num_buttons = num_buttons
        self._tracks: list[_ButtonTrack] = [_ButtonTrack() for _ in range(num_buttons)]
        # Recent press-down timestamps for combo detection
        self._recent_downs: list[tuple[int, float]] = []

    # ── public API ──────────────────────────────────────────────────────────

    def poll(self) -> list[ControllerEvent | AxisEvent]:
        """Poll the backend and return new events (also published on the bus)."""
        self._backend.poll()
        now = time.monotonic()
        events: list[ControllerEvent | AxisEvent] = []

        # -- buttons --
        for idx in range(self._num_buttons):
            pressed = self._backend.get_button(idx)
            track = self._tracks[idx]

            if pressed and not track.down:
                # Button just went down
                track.down = True
                track.down_since = now
                track.held_fired = False
                self._recent_downs.append((idx, now))

            elif pressed and track.down:
                # Button still held — check for hold threshold
                if not track.held_fired and (now - track.down_since) >= self._hold_threshold:
                    track.held_fired = True
                    ev = ControllerEvent(
                        button=idx,
                        state=ButtonState.HELD,
                        timestamp=now,
                        duration=now - track.down_since,
                    )
                    events.append(ev)

            elif not pressed and track.down:
                # Button released
                duration = now - track.down_since
                track.down = False

                if track.held_fired:
                    # Was a hold — emit RELEASED after hold
                    ev = ControllerEvent(
                        button=idx,
                        state=ButtonState.RELEASED,
                        timestamp=now,
                        duration=duration,
                    )
                    events.append(ev)
                else:
                    # Short press (down→up within hold threshold)
                    ev = ControllerEvent(
                        button=idx,
                        state=ButtonState.PRESSED,
                        timestamp=now,
                        duration=duration,
                    )
                    events.append(ev)

        # -- combo detection --
        # Prune old entries outside the combo window
        self._recent_downs = [
            (b, t) for b, t in self._recent_downs if (now - t) < self._combo_window
        ]
        # Check for two-button combos among recent downs
        combo_events = self._detect_combos(now)
        events.extend(combo_events)

        # -- axes --
        for axis_idx in range(8):
            value = self._backend.get_axis(axis_idx)
            if abs(value) > self._deadzone:
                ev = AxisEvent(axis=axis_idx, value=value, timestamp=now)
                events.append(ev)

        # Publish all events on the global bus
        for ev in events:
            bus.publish(ev)

        return events

    # ── internals ───────────────────────────────────────────────────────────

    def _detect_combos(self, now: float) -> list[ControllerEvent]:
        """Detect two-button combos from recent down events.

        A combo fires once when two distinct buttons are pressed within the
        combo window. We encode the combo as a synthetic ControllerEvent whose
        button field is ``min_btn * 100 + max_btn`` (e.g. buttons 4+5 → 405).
        """
        events: list[ControllerEvent] = []
        seen: set[tuple[int, int]] = set()

        for i, (b1, t1) in enumerate(self._recent_downs):
            for b2, t2 in self._recent_downs[i + 1 :]:
                if b1 == b2:
                    continue
                pair = (min(b1, b2), max(b1, b2))
                if pair in seen:
                    continue
                if abs(t1 - t2) <= self._combo_window:
                    # Both buttons must still be held right now
                    if self._tracks[pair[0]].down and self._tracks[pair[1]].down:
                        seen.add(pair)
                        combo_id = pair[0] * 100 + pair[1]
                        events.append(
                            ControllerEvent(
                                button=combo_id,
                                state=ButtonState.PRESSED,
                                timestamp=now,
                            )
                        )
        # Clear recent downs after combo fires to avoid re-triggering
        if events:
            self._recent_downs.clear()
        return events

    @property
    def backend(self) -> ControllerBackend:
        return self._backend
