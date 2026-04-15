"""Tests for pixiis.core.events — EventBus publish/subscribe."""

from __future__ import annotations

import threading

from pixiis.core.events import EventBus


class _DummyEvent:
    def __init__(self, value: int = 0) -> None:
        self.value = value


class _OtherEvent:
    pass


def test_subscribe_and_publish():
    bus = EventBus()
    received = []
    bus.subscribe(_DummyEvent, lambda e: received.append(e.value))
    bus.publish(_DummyEvent(42))
    assert received == [42]


def test_multiple_handlers():
    bus = EventBus()
    a, b = [], []
    bus.subscribe(_DummyEvent, lambda e: a.append(e.value))
    bus.subscribe(_DummyEvent, lambda e: b.append(e.value))
    bus.publish(_DummyEvent(7))
    assert a == [7]
    assert b == [7]


def test_unsubscribe():
    bus = EventBus()
    received = []
    handler = lambda e: received.append(e.value)
    bus.subscribe(_DummyEvent, handler)
    bus.publish(_DummyEvent(1))
    bus.unsubscribe(_DummyEvent, handler)
    bus.publish(_DummyEvent(2))
    assert received == [1]


def test_unsubscribe_nonexistent():
    bus = EventBus()
    # Should not raise
    bus.unsubscribe(_DummyEvent, lambda e: None)


def test_handler_exception_does_not_crash_others(capsys):
    bus = EventBus()
    results = []

    def bad_handler(e):
        raise ValueError("boom")

    def good_handler(e):
        results.append(e.value)

    bus.subscribe(_DummyEvent, bad_handler)
    bus.subscribe(_DummyEvent, good_handler)
    bus.publish(_DummyEvent(99))

    # Good handler still ran despite bad_handler raising
    assert results == [99]
    captured = capsys.readouterr()
    assert "boom" in captured.out


def test_different_event_types_isolated():
    bus = EventBus()
    dummy_received = []
    other_received = []
    bus.subscribe(_DummyEvent, lambda e: dummy_received.append(True))
    bus.subscribe(_OtherEvent, lambda e: other_received.append(True))
    bus.publish(_DummyEvent(0))
    assert dummy_received == [True]
    assert other_received == []


def test_clear():
    bus = EventBus()
    received = []
    bus.subscribe(_DummyEvent, lambda e: received.append(True))
    bus.clear()
    bus.publish(_DummyEvent(0))
    assert received == []


def test_thread_safety():
    bus = EventBus()
    received = []
    bus.subscribe(_DummyEvent, lambda e: received.append(e.value))

    def bg_publish():
        for i in range(100):
            bus.publish(_DummyEvent(i))

    t = threading.Thread(target=bg_publish)
    t.start()
    t.join()

    assert len(received) == 100
    assert received == list(range(100))
