"""Twitch Helix API client for live stream data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from pixiis.core import get_config


@dataclass
class TwitchStream:
    """A live Twitch stream."""

    user_name: str = ""
    title: str = ""
    viewer_count: int = 0
    thumbnail_url: str = ""
    stream_url: str = ""


class TwitchClient(QObject):
    """Async Twitch Helix client using Qt networking.

    Uses client-credentials OAuth to fetch top live streams for a game.
    Requires ``services.twitch.client_id`` and ``services.twitch.client_secret``
    (or a pre-obtained ``access_token`` from the browser OAuth flow).
    """

    streams_ready = Signal(list)  # list[TwitchStream]

    _TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    _HELIX = "https://api.twitch.tv/helix"

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._access_token: str = ""
        self._pending_game: str = ""

        # If an access_token is already stored in config (from browser OAuth),
        # use it directly instead of doing client-credentials exchange.
        stored_token = get_config().get("services.twitch.access_token", "")
        if stored_token:
            self._access_token = stored_token

    # ── public API ──────────────────────────────────────────────────────

    @staticmethod
    def authorize_url(client_id: str, redirect_uri: str) -> str:
        """Return the Twitch OAuth authorize URL for implicit grant."""
        return (
            f"https://id.twitch.tv/oauth2/authorize"
            f"?client_id={quote(client_id)}"
            f"&redirect_uri={quote(redirect_uri)}"
            f"&response_type=token"
            f"&scope="
        )

    def get_top_streams(self, game_name: str) -> None:
        """Fetch top 5 live streams for *game_name*.  Emits *streams_ready*."""
        client_id, client_secret = self._credentials()
        if not client_id:
            self.streams_ready.emit([])
            return

        self._pending_game = game_name

        if self._access_token:
            self._resolve_category(game_name)
        elif client_secret:
            self._authenticate(client_id, client_secret)
        else:
            # No token and no secret — cannot authenticate
            self.streams_ready.emit([])

    # ── OAuth ───────────────────────────────────────────────────────────

    def _authenticate(self, client_id: str, client_secret: str) -> None:
        body = urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        }).encode()
        request = QNetworkRequest(QUrl(self._TOKEN_URL))
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/x-www-form-urlencoded",
        )
        reply = self._nam.post(request, body)
        reply.finished.connect(lambda: self._on_auth_finished(reply))

    def _on_auth_finished(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.streams_ready.emit([])
                return
            data = self._parse_json(reply)
            if data is None or "access_token" not in data:
                self.streams_ready.emit([])
                return
            self._access_token = data["access_token"]
            self._resolve_category(self._pending_game)
        finally:
            reply.deleteLater()

    # ── Category resolution ─────────────────────────────────────────────

    def _resolve_category(self, game_name: str) -> None:
        params = urlencode({"query": game_name})
        url = QUrl(f"{self._HELIX}/search/categories?{params}")
        request = self._helix_request(url)
        reply = self._nam.get(request)
        reply.finished.connect(lambda: self._on_category_resolved(reply))

    def _on_category_resolved(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self._handle_helix_error(reply)
                return
            data = self._parse_json(reply)
            if data is None:
                self.streams_ready.emit([])
                return
            categories = data.get("data", [])
            if not categories:
                self.streams_ready.emit([])
                return
            game_id = categories[0].get("id", "")
            if not game_id:
                self.streams_ready.emit([])
                return
            self._fetch_streams(game_id)
        finally:
            reply.deleteLater()

    # ── Stream fetch ────────────────────────────────────────────────────

    def _fetch_streams(self, game_id: str) -> None:
        params = urlencode({"game_id": game_id, "first": 5})
        url = QUrl(f"{self._HELIX}/streams?{params}")
        request = self._helix_request(url)
        reply = self._nam.get(request)
        reply.finished.connect(lambda: self._on_streams_fetched(reply))

    def _on_streams_fetched(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self._handle_helix_error(reply)
                return
            data = self._parse_json(reply)
            if data is None:
                self.streams_ready.emit([])
                return
            streams: list[TwitchStream] = []
            for s in data.get("data", []):
                user = s.get("user_name", "")
                streams.append(TwitchStream(
                    user_name=user,
                    title=s.get("title", ""),
                    viewer_count=int(s.get("viewer_count", 0)),
                    thumbnail_url=s.get("thumbnail_url", ""),
                    stream_url=f"https://twitch.tv/{user}" if user else "",
                ))
            self.streams_ready.emit(streams)
        finally:
            reply.deleteLater()

    # ── helpers ──────────────────────────────────────────────────────────

    def _helix_request(self, url: QUrl) -> QNetworkRequest:
        client_id, _ = self._credentials()
        request = QNetworkRequest(url)
        request.setRawHeader(b"Authorization", f"Bearer {self._access_token}".encode())
        request.setRawHeader(b"Client-Id", client_id.encode())
        return request

    def _handle_helix_error(self, reply: QNetworkReply) -> None:
        """On 401 (expired token) clear token so next call re-authenticates."""
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status == 401:
            self._access_token = ""
        self.streams_ready.emit([])

    @staticmethod
    def _credentials() -> tuple[str, str]:
        cfg = get_config()
        return (
            cfg.get("services.twitch.client_id", ""),
            cfg.get("services.twitch.client_secret", ""),
        )

    @staticmethod
    def _parse_json(reply: QNetworkReply) -> dict | None:
        raw = reply.readAll().data()
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
