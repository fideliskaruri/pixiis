"""RAWG.io API client for game metadata and screenshots."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from pixiis.core import get_config

_BASE_URL = "https://api.rawg.io/api"


@dataclass
class RawgGameData:
    """Game metadata from the RAWG API."""

    id: int = 0
    name: str = ""
    description: str = ""
    rating: float = 0.0
    metacritic: int = 0
    genres: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    playtime: int = 0
    background_image: str = ""
    released: str = ""


class RawgClient(QObject):
    """Async RAWG API client using Qt networking.

    Fetches game metadata, ratings, screenshots, and details.
    Requires an API key configured at ``services.rawg.api_key``.
    """

    game_found = Signal(object)      # RawgGameData
    details_ready = Signal(object)   # RawgGameData

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._cache: dict[str, RawgGameData] = {}

    # ── public API ──────────────────────────────────────────────────────

    def search_game(self, name: str) -> None:
        """Search for a game by name.  Emits *game_found* with the top result."""
        key = self._api_key()
        if not key:
            self.game_found.emit(RawgGameData())
            return

        # Check cache first
        cache_key = name.lower().strip()
        if cache_key in self._cache:
            self.game_found.emit(self._cache[cache_key])
            return

        params = urlencode({"search": name, "key": key, "page_size": 1})
        url = QUrl(f"{_BASE_URL}/games?{params}")
        request = QNetworkRequest(url)
        reply = self._nam.get(request)
        reply.finished.connect(lambda: self._on_search_finished(reply, cache_key))

    def get_game_details(self, game_id: int) -> None:
        """Fetch full details for a game by RAWG id.  Emits *details_ready*."""
        key = self._api_key()
        if not key:
            self.details_ready.emit(RawgGameData())
            return

        cache_key = f"__id_{game_id}"
        if cache_key in self._cache:
            self.details_ready.emit(self._cache[cache_key])
            return

        params = urlencode({"key": key})
        url = QUrl(f"{_BASE_URL}/games/{game_id}?{params}")
        request = QNetworkRequest(url)
        reply = self._nam.get(request)
        reply.finished.connect(lambda: self._on_details_finished(reply, cache_key))

    # ── slots / internal ────────────────────────────────────────────────

    def _on_search_finished(self, reply: QNetworkReply, cache_key: str) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.game_found.emit(RawgGameData())
                return
            data = self._parse_json(reply)
            if data is None:
                self.game_found.emit(RawgGameData())
                return
            results = data.get("results", [])
            if not results:
                self.game_found.emit(RawgGameData())
                return
            game = self._parse_game(results[0])
            self._cache[cache_key] = game
            self.game_found.emit(game)
        finally:
            reply.deleteLater()

    def _on_details_finished(self, reply: QNetworkReply, cache_key: str) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.details_ready.emit(RawgGameData())
                return
            data = self._parse_json(reply)
            if data is None:
                self.details_ready.emit(RawgGameData())
                return
            game = self._parse_game(data)
            self._cache[cache_key] = game
            self.details_ready.emit(game)
        finally:
            reply.deleteLater()

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _api_key() -> str:
        return get_config().get("services.rawg.api_key", "")

    @staticmethod
    def _parse_json(reply: QNetworkReply) -> dict | None:
        raw = reply.readAll().data()
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def _parse_game(obj: dict) -> RawgGameData:
        genres = [g["name"] for g in obj.get("genres", []) if "name" in g]
        platforms = [
            p["platform"]["name"]
            for p in obj.get("platforms", [])
            if isinstance(p, dict) and "platform" in p and "name" in p["platform"]
        ]
        screenshots = [
            s["image"]
            for s in obj.get("short_screenshots", [])
            if "image" in s
        ]
        return RawgGameData(
            id=obj.get("id", 0),
            name=obj.get("name", ""),
            description=obj.get("description_raw", obj.get("description", "")),
            rating=float(obj.get("rating", 0)),
            metacritic=int(obj.get("metacritic") or 0),
            genres=genres,
            platforms=platforms,
            screenshots=screenshots,
            playtime=int(obj.get("playtime") or 0),
            background_image=obj.get("background_image", "") or "",
            released=obj.get("released", "") or "",
        )
