"""Thread-safe typed event bus for Pixiis."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class EventBus:
    """Publish/subscribe event bus with thread-safe dispatch.

    Usage:
        bus = EventBus()
        bus.subscribe(ControllerEvent, my_handler)
        bus.publish(ControllerEvent(button=0, state=ButtonState.PRESSED, timestamp=0))
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event_type: type[T], handler: Callable[[T], None]) -> None:
        """Register a handler for an event type."""
        with self._lock:
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[T], handler: Callable[[T], None]) -> None:
        """Remove a handler for an event type."""
        with self._lock:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    def publish(self, event: Any) -> None:
        """Dispatch an event to all registered handlers.

        Handlers are called synchronously in the publishing thread.
        If a handler raises, it is caught and printed so other handlers still run.
        """
        with self._lock:
            handlers = list(self._handlers.get(type(event), []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"[EventBus] Handler {handler.__name__} failed for {type(event).__name__}: {e}")

    def clear(self) -> None:
        """Remove all handlers."""
        with self._lock:
            self._handlers.clear()


# Global application event bus
bus = EventBus()
