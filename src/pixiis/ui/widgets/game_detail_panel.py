"""GameDetailPanel — expanded game card with metadata, media, and launch button."""

from __future__ import annotations

from PySide6.QtCore import QSize, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pixiis.core.types import AppEntry

ACCENT = "#e94560"
BG_PRIMARY = "#1a1a2e"
BG_SECONDARY = "#16213e"
TEXT_PRIMARY = "#e0e0e0"
TEXT_SECONDARY = "#aaaaaa"


# ── Helpers ─────────────────────────────────────────────────────────────────


def _pill(text: str) -> QLabel:
    """Small rounded badge / pill."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY}; "
        "border-radius: 10px; padding: 4px 12px; font-size: 12px;"
    )
    lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return lbl


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: bold; "
        "background: transparent; margin-top: 12px;"
    )
    return lbl


def _placeholder_header(width: int, height: int) -> QPixmap:
    pix = QPixmap(width, height)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    grad = QLinearGradient(0, 0, 0, height)
    grad.setColorAt(0.0, Qt.GlobalColor.darkGray)
    grad.setColorAt(1.0, Qt.GlobalColor.black)
    p.fillRect(pix.rect(), grad)
    p.end()
    return pix


# ── Clickable thumbnail used for screenshots / media cards ──────────────────


class _ClickableImage(QLabel):
    """A QLabel that opens a URL when clicked."""

    def __init__(self, url: str = "", parent=None) -> None:
        super().__init__(parent)
        self.url = url
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.url and event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self.url))
        super().mouseReleaseEvent(event)


# ── Media card (thumbnail + title + subtitle) ──────────────────────────────


class _MediaCard(QFrame):
    """Small card: thumbnail on top, text below.  Click opens *url*."""

    def __init__(
        self, thumb_w: int, thumb_h: int, title: str, subtitle: str, url: str, parent=None
    ) -> None:
        super().__init__(parent)
        self._url = url
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"_MediaCard {{ background: {BG_SECONDARY}; border-radius: 8px; }}"
        )
        self.setFixedWidth(thumb_w + 16)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.thumb = QLabel()
        self.thumb.setFixedSize(thumb_w, thumb_h)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setStyleSheet("background: #0d0d0f; border-radius: 4px;")
        layout.addWidget(self.thumb)

        t = QLabel(title)
        t.setWordWrap(True)
        t.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: bold;")
        layout.addWidget(t)

        s = QLabel(subtitle)
        s.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(s)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._url and event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mouseReleaseEvent(event)


# ── Main panel ──────────────────────────────────────────────────────────────


class GameDetailPanel(QScrollArea):
    """Expanded game detail card — header art, info bar, description, media."""

    launch_requested = Signal(object)  # AppEntry
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._app: AppEntry | None = None

        # Root container
        self._root = QWidget()
        self._root_layout = QVBoxLayout(self._root)
        self._root_layout.setContentsMargins(0, 0, 0, 24)
        self._root_layout.setSpacing(0)
        self.setWidget(self._root)

        # ── Header area (image + overlay) ───────────────────────────────
        self._header = QWidget()
        self._header.setFixedHeight(300)
        self._header.setStyleSheet("background: #0d0d0f;")
        header_layout = QVBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self._header_img = QLabel()
        self._header_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header_img.setStyleSheet("background: transparent;")
        header_layout.addWidget(self._header_img)

        # Overlay sits on top of the header image (absolute positioned)
        self._header_overlay = QWidget(self._header)
        overlay_layout = QHBoxLayout(self._header_overlay)
        overlay_layout.setContentsMargins(24, 0, 24, 16)

        overlay_left = QVBoxLayout()
        self._title_label = QLabel()
        self._title_label.setStyleSheet(
            "color: white; font-size: 28px; font-weight: bold; background: transparent;"
        )
        overlay_left.addStretch()
        overlay_left.addWidget(self._title_label)
        self._rating_label = QLabel()
        self._rating_label.setStyleSheet(
            "color: #ffd700; font-size: 14px; background: transparent;"
        )
        overlay_left.addWidget(self._rating_label)
        overlay_layout.addLayout(overlay_left, 1)

        self._launch_btn = QPushButton("Launch")
        self._launch_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: white; font-size: 16px; "
            "font-weight: bold; border-radius: 8px; padding: 12px 32px; border: none; }}"
            f"QPushButton:hover {{ background: #c73550; }}"
        )
        self._launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._launch_btn.clicked.connect(self._on_launch)
        overlay_layout.addWidget(self._launch_btn, 0, Qt.AlignmentFlag.AlignBottom)

        self._root_layout.addWidget(self._header)

        # ── Body (below header) ─────────────────────────────────────────
        body = QWidget()
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(24, 16, 24, 0)
        self._body_layout.setSpacing(12)

        # Info bar (genre pills, platform, date, playtime)
        self._info_bar = QHBoxLayout()
        self._info_bar.setSpacing(8)
        self._info_bar_widget = QWidget()
        self._info_bar_widget.setLayout(self._info_bar)
        self._body_layout.addWidget(self._info_bar_widget)

        # Description
        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        self._desc_label.setTextFormat(Qt.TextFormat.RichText)
        self._desc_label.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY}; "
            "border-radius: 8px; padding: 16px; font-size: 13px;"
        )
        self._body_layout.addWidget(self._desc_label)

        # Screenshots
        self._body_layout.addWidget(_section_title("Screenshots"))
        self._screenshots_scroll = QScrollArea()
        self._screenshots_scroll.setFixedHeight(140)
        self._screenshots_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._screenshots_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._screenshots_scroll.setWidgetResizable(True)
        self._screenshots_scroll.setStyleSheet("border: none; background: transparent;")
        self._screenshots_container = QWidget()
        self._screenshots_layout = QHBoxLayout(self._screenshots_container)
        self._screenshots_layout.setContentsMargins(0, 0, 0, 0)
        self._screenshots_layout.setSpacing(10)
        self._screenshots_scroll.setWidget(self._screenshots_container)
        self._body_layout.addWidget(self._screenshots_scroll)

        # Trailers
        self._body_layout.addWidget(_section_title("Trailers"))
        self._trailers_scroll = QScrollArea()
        self._trailers_scroll.setFixedHeight(220)
        self._trailers_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._trailers_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._trailers_scroll.setWidgetResizable(True)
        self._trailers_scroll.setStyleSheet("border: none; background: transparent;")
        self._trailers_container = QWidget()
        self._trailers_layout = QHBoxLayout(self._trailers_container)
        self._trailers_layout.setContentsMargins(0, 0, 0, 0)
        self._trailers_layout.setSpacing(10)
        self._trailers_scroll.setWidget(self._trailers_container)
        self._body_layout.addWidget(self._trailers_scroll)

        # Live Streams
        self._body_layout.addWidget(_section_title("Live Streams"))
        self._streams_scroll = QScrollArea()
        self._streams_scroll.setFixedHeight(220)
        self._streams_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._streams_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._streams_scroll.setWidgetResizable(True)
        self._streams_scroll.setStyleSheet("border: none; background: transparent;")
        self._streams_container = QWidget()
        self._streams_layout = QHBoxLayout(self._streams_container)
        self._streams_layout.setContentsMargins(0, 0, 0, 0)
        self._streams_layout.setSpacing(10)
        self._streams_scroll.setWidget(self._streams_container)
        self._body_layout.addWidget(self._streams_scroll)

        # Custom Fan Profile — coming soon
        fan_frame = QFrame()
        fan_frame.setStyleSheet(
            f"background: {BG_SECONDARY}; border: 2px dashed #555; "
            "border-radius: 8px; padding: 20px;"
        )
        fan_layout = QVBoxLayout(fan_frame)
        fan_label = QLabel("Custom Fan Profile  —  Coming Soon")
        fan_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fan_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 14px; border: none; background: transparent;"
        )
        fan_layout.addWidget(fan_label)
        self._body_layout.addWidget(fan_frame)

        self._body_layout.addStretch()
        self._root_layout.addWidget(body, 1)

    # ── Public API ──────────────────────────────────────────────────────────

    def set_game(
        self,
        app: AppEntry,
        rawg_client=None,
        youtube_client=None,
        twitch_client=None,
    ) -> None:
        """Populate the panel for *app*.  Optionally pass service clients for
        async metadata loading."""
        self._app = app
        self._title_label.setText(app.display_name)
        self._rating_label.clear()
        self._desc_label.setText("Loading...")

        # Reset media sections
        self._clear_layout(self._screenshots_layout)
        self._clear_layout(self._trailers_layout)
        self._clear_layout(self._streams_layout)
        self._clear_info_bar()

        # Placeholder header
        w = self._header.width() or 800
        self._header_img.setPixmap(
            _placeholder_header(w, 300).scaled(
                w, 300,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        # Kick off async fetches
        if rawg_client is not None:
            rawg_client.game_found.connect(self._on_rawg_data)
            rawg_client.search(app.display_name)

        if youtube_client is not None:
            youtube_client.results_ready.connect(self._on_youtube_data)
            youtube_client.search(f"{app.display_name} trailer")

        if twitch_client is not None:
            twitch_client.streams_ready.connect(self._on_twitch_data)
            twitch_client.search(app.display_name)

    def set_header_image(self, pixmap: QPixmap) -> None:
        w = self._header.width() or 800
        self._header_img.setPixmap(
            pixmap.scaled(
                w, 300,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    # ── Service callbacks ───────────────────────────────────────────────────

    def _on_rawg_data(self, data: dict) -> None:
        """Slot for RawgClient.game_found."""
        if self._app is None:
            return

        # Description
        desc = data.get("description", "") or data.get("description_raw", "")
        if desc:
            self._desc_label.setText(desc)
        else:
            self._desc_label.setText("<i>No description available.</i>")

        # Rating
        rating = data.get("rating")
        if rating:
            stars = int(round(float(rating)))
            self._rating_label.setText(f"{'★' * stars}{'☆' * (5 - stars)}  {rating}/5")

        # Info bar: genres, platforms, release date, playtime
        self._clear_info_bar()
        for genre in data.get("genres", [])[:4]:
            self._info_bar.addWidget(_pill(genre.get("name", "")))
        released = data.get("released")
        if released:
            self._info_bar.addWidget(_pill(f"Released: {released}"))
        playtime = data.get("playtime")
        if playtime:
            self._info_bar.addWidget(_pill(f"{playtime}h avg"))
        self._info_bar.addStretch()

        # Screenshots
        for shot in data.get("short_screenshots", [])[:6]:
            img_url = shot.get("image", "")
            if img_url:
                thumb = _ClickableImage(img_url)
                thumb.setFixedSize(220, 124)
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb.setStyleSheet("background: #0d0d0f; border-radius: 6px;")
                thumb.setText("Loading...")
                self._screenshots_layout.addWidget(thumb)

    def _on_youtube_data(self, results: list) -> None:
        """Slot for YouTubeClient.results_ready."""
        self._clear_layout(self._trailers_layout)
        for item in results[:6]:
            title = item.get("title", "")
            channel = item.get("channel", "")
            url = item.get("url", "")
            card = _MediaCard(320, 180, title, channel, url)
            self._trailers_layout.addWidget(card)
        self._trailers_layout.addStretch()

    def _on_twitch_data(self, streams: list) -> None:
        """Slot for TwitchClient.streams_ready."""
        self._clear_layout(self._streams_layout)
        for stream in streams[:6]:
            title = stream.get("user_name", "")
            viewers = stream.get("viewer_count", 0)
            url = stream.get("url", "")
            card = _MediaCard(320, 180, title, f"{viewers:,} viewers", url)
            self._streams_layout.addWidget(card)
        self._streams_layout.addStretch()

    # ── Navigation ──────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.back_requested.emit()
        else:
            super().keyPressEvent(event)

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_launch(self) -> None:
        if self._app is not None:
            self.launch_requested.emit(self._app)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Keep overlay pinned to bottom of header
        self._header_overlay.setGeometry(
            0,
            self._header.height() - 80,
            self._header.width(),
            80,
        )

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _clear_info_bar(self) -> None:
        self._clear_layout(self._info_bar)
