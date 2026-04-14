"""YouTube Data API v3 client for game trailer search."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from pixiis.core import get_config


@dataclass
class YouTubeResult:
    """A single YouTube video result."""

    video_id: str = ""
    title: str = ""
    thumbnail_url: str = ""
    channel: str = ""


class YouTubeClient(QObject):
    """Async YouTube search client using Qt networking.

    Searches for game trailers via the YouTube Data API v3.
    Requires an API key configured at ``services.youtube.api_key``.
    """

    results_ready = Signal(list)  # list[YouTubeResult]

    _ENDPOINT = "https://www.googleapis.com/youtube/v3/search"

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._cache: dict[str, list[YouTubeResult]] = {}

    # ── public API ──────────────────────────────────────────────────────

    def search_trailers(self, game_name: str) -> None:
        """Search YouTube for official trailers.  Emits *results_ready*."""
        key = self._api_key()
        if not key:
            self.results_ready.emit([])
            return

        cache_key = game_name.lower().strip()
        if cache_key in self._cache:
            self.results_ready.emit(self._cache[cache_key])
            return

        params = urlencode({
            "part": "snippet",
            "q": f"{game_name} official trailer",
            "type": "video",
            "maxResults": 5,
            "key": key,
        })
        url = QUrl(f"{self._ENDPOINT}?{params}")
        request = QNetworkRequest(url)
        reply = self._nam.get(request)
        reply.finished.connect(lambda: self._on_finished(reply, cache_key))

    # ── slots / internal ────────────────────────────────────────────────

    def _on_finished(self, reply: QNetworkReply, cache_key: str) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.results_ready.emit([])
                return
            data = self._parse_json(reply)
            if data is None:
                self.results_ready.emit([])
                return
            results: list[YouTubeResult] = []
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                vid_id = item.get("id", {}).get("videoId", "")
                if not vid_id:
                    continue
                thumbs = snippet.get("thumbnails", {})
                thumb_url = (
                    thumbs.get("high", {}).get("url")
                    or thumbs.get("medium", {}).get("url")
                    or thumbs.get("default", {}).get("url", "")
                )
                results.append(YouTubeResult(
                    video_id=vid_id,
                    title=snippet.get("title", ""),
                    thumbnail_url=thumb_url,
                    channel=snippet.get("channelTitle", ""),
                ))
            self._cache[cache_key] = results
            self.results_ready.emit(results)
        finally:
            reply.deleteLater()

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _api_key() -> str:
        return get_config().get("services.youtube.api_key", "")

    @staticmethod
    def _parse_json(reply: QNetworkReply) -> dict | None:
        raw = reply.readAll().data()
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
