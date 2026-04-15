"""Playtime tracker — monitors how long each game session lasts."""

from __future__ import annotations

import time


class PlaytimeTracker:
    """Tracks game playtime by monitoring launched processes.

    Usage:
        tracker.start(app_id)    # when a game launches
        mins = tracker.stop(app_id)  # when the game closes
    """

    def __init__(self) -> None:
        self._active: dict[str, float] = {}  # app_id -> start_time (epoch)

    def start(self, app_id: str) -> None:
        """Begin tracking playtime for *app_id*."""
        self._active[app_id] = time.time()

    def stop(self, app_id: str) -> int:
        """Stop tracking *app_id* and return minutes played this session.

        Returns 0 if the app was not being tracked.
        """
        start = self._active.pop(app_id, None)
        if start is None:
            return 0
        elapsed = time.time() - start
        return max(1, int(elapsed / 60))  # at least 1 minute if played at all

    def stop_all(self) -> dict[str, int]:
        """Stop all active tracking sessions.

        Returns a dict of ``{app_id: minutes_played}``.
        """
        results: dict[str, int] = {}
        now = time.time()
        for app_id, start in self._active.items():
            elapsed = now - start
            results[app_id] = max(1, int(elapsed / 60))
        self._active.clear()
        return results

    def is_tracking(self, app_id: str) -> bool:
        """Return True if *app_id* is currently being tracked."""
        return app_id in self._active

    @property
    def active_ids(self) -> list[str]:
        """Return list of app IDs currently being tracked."""
        return list(self._active.keys())
