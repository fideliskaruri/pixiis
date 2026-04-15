"""Async image downloader with memory and disk caching."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from PySide6.QtCore import QObject, QSize, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from pixiis.core.paths import cache_dir


def _image_cache_dir() -> Path:
    d = cache_dir() / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _url_to_filename(url: str) -> str:
    """Deterministic filename from a URL."""
    digest = hashlib.sha256(url.encode()).hexdigest()[:24]
    # Preserve extension if present
    suffix = ""
    dot = url.rfind(".")
    if dot != -1:
        ext = url[dot:].split("?", 1)[0].split("#", 1)[0]
        if 2 <= len(ext) <= 5 and ext.isascii():
            suffix = ext
    return digest + (suffix or ".img")


class AsyncImageLoader(QObject):
    """Downloads and caches images asynchronously.

    Emits *image_ready(url, pixmap)* when an image has been loaded.
    Pixmap will be null if the download failed.
    """

    image_ready = Signal(str, QPixmap)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._mem_cache: dict[str, QPixmap] = {}
        self._disk_dir = _image_cache_dir()

    # ── public API ──────────────────────────────────────────────────────

    def request(self, url: str, size: QSize | None = None) -> None:
        """Request an image by URL.

        Checks memory cache, then disk cache, then downloads.
        The *size* parameter, when given, scales the pixmap before emitting.
        """
        if not url:
            return

        cache_key = self._cache_key(url, size)

        # 1. Memory cache
        if cache_key in self._mem_cache:
            self.image_ready.emit(url, self._mem_cache[cache_key])
            return

        # 2. Disk cache
        disk_path = self._disk_dir / _url_to_filename(url)
        if disk_path.exists():
            pixmap = QPixmap(str(disk_path))
            if not pixmap.isNull():
                pixmap = self._maybe_scale(pixmap, size)
                self._mem_cache[cache_key] = pixmap
                self.image_ready.emit(url, pixmap)
                return

        # 3. Download
        request = QNetworkRequest(QUrl(url))
        reply = self._nam.get(request)
        reply.finished.connect(lambda: self._on_downloaded(reply, url, size))

    # ── slots / internal ────────────────────────────────────────────────

    def _on_downloaded(
        self, reply: QNetworkReply, url: str, size: QSize | None
    ) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.image_ready.emit(url, QPixmap())
                return

            data = reply.readAll().data()
            if not data:
                self.image_ready.emit(url, QPixmap())
                return

            # Save to disk
            disk_path = self._disk_dir / _url_to_filename(url)
            try:
                disk_path.write_bytes(data)
            except OSError:
                logger.debug("Disk cache write failed for %s", url, exc_info=True)

            # Decode
            pixmap = QPixmap()
            if not pixmap.loadFromData(data):
                self.image_ready.emit(url, QPixmap())
                return

            pixmap = self._maybe_scale(pixmap, size)
            cache_key = self._cache_key(url, size)
            self._mem_cache[cache_key] = pixmap
            self.image_ready.emit(url, pixmap)
        finally:
            reply.deleteLater()

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _maybe_scale(pixmap: QPixmap, size: QSize | None) -> QPixmap:
        if size is not None and size.isValid():
            return pixmap.scaled(size, aspectMode=1, mode=1)  # KeepAspectRatio, SmoothTransformation
        return pixmap

    @staticmethod
    def _cache_key(url: str, size: QSize | None) -> str:
        if size is not None and size.isValid():
            return f"{url}@{size.width()}x{size.height()}"
        return url
