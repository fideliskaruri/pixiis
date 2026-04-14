"""GameDetailPanel — cinematic game detail view with Dark Cinema aesthetic."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, QSize, QUrl, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pixiis.core.types import AppEntry

# ── Dark Cinema palette ────────────────────────────────────────────────────

_BASE = "#08080c"
_SURFACE = "#0f0f15"
_SURFACE_LIGHT = "#161620"
_ACCENT = "#e94560"
_ACCENT_HOVER = "#d13a52"
_AMBER = "#f0a030"
_TEXT_PRIMARY = "#e8e8f0"
_TEXT_BODY = "#c0c0cc"
_TEXT_MUTED = "#6b6b80"
_TEXT_DIM = "#3a3a4a"


# ── Helper factories ───────────────────────────────────────────────────────


def _pill(text: str) -> QLabel:
    """Small rounded info badge."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background: {_SURFACE_LIGHT}; color: {_TEXT_MUTED}; "
        "border-radius: 8px; padding: 4px 10px; font-size: 12px;"
    )
    lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return lbl


def _section_title(text: str) -> QLabel:
    """Uppercase section label."""
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {_TEXT_MUTED}; font-size: 12px; font-weight: bold; "
        "letter-spacing: 2px; background: transparent; margin-top: 16px;"
    )
    return lbl


def _placeholder_header(width: int, height: int) -> QPixmap:
    pix = QPixmap(width, height)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    grad = QLinearGradient(0, 0, 0, height)
    grad.setColorAt(0.0, QColor(30, 30, 40))
    grad.setColorAt(1.0, QColor(8, 8, 12))
    p.fillRect(pix.rect(), grad)
    p.end()
    return pix


# ── Clickable thumbnail ───────────────────────────────────────────────────


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


# ── Media card ─────────────────────────────────────────────────────────────


class _MediaCard(QFrame):
    """Thumbnail card for trailers / streams with hover glow."""

    def __init__(
        self, thumb_w: int, thumb_h: int, title: str, subtitle: str, url: str, parent=None
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(thumb_w + 24, thumb_h + 70)
        self.setMouseTracking(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.thumb = QLabel()
        self.thumb.setFixedSize(thumb_w, thumb_h)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setStyleSheet(
            f"background: {_BASE}; border-radius: 8px;"
        )
        layout.addWidget(self.thumb)

        t = QLabel(title)
        t.setWordWrap(True)
        t.setMaximumWidth(thumb_w)
        t.setStyleSheet(
            f"color: {_TEXT_PRIMARY}; font-size: 12px; font-weight: bold; "
            "background: transparent;"
        )
        layout.addWidget(t)

        s = QLabel(subtitle)
        s.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 11px; background: transparent;"
        )
        layout.addWidget(s)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 12.0, 12.0)

        # Background
        bg = QColor(_SURFACE_LIGHT) if self._hovered else QColor(_SURFACE)
        p.fillPath(path, bg)

        # Hover glow border
        if self._hovered:
            pen = QPen(QColor(233, 69, 96, 50), 1.0)
            p.setPen(pen)
            p.drawPath(path)

        p.end()
        super().paintEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._url and event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mouseReleaseEvent(event)


# ── Hero section ───────────────────────────────────────────────────────────


class _HeroWidget(QWidget):
    """Full-width hero with background image, gradient overlay, title, and launch button."""

    launch_clicked = Signal()
    back_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(400)
        self._pixmap: QPixmap | None = None
        self._title = ""
        self._rating_text = ""

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def set_title(self, title: str) -> None:
        self._title = title
        self.update()

    def set_rating(self, text: str) -> None:
        self._rating_text = text
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        # Background image (scaled to cover)
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x_off = (scaled.width() - w) // 2
            y_off = (scaled.height() - h) // 2
            p.drawPixmap(0, 0, scaled, x_off, y_off, w, h)
        else:
            # Fallback dark gradient
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(30, 30, 40))
            grad.setColorAt(1.0, QColor(8, 8, 12))
            p.fillRect(0, 0, w, h, grad)

        # Heavy gradient overlay: transparent top → base bottom
        overlay = QLinearGradient(0, 0, 0, h)
        overlay.setColorAt(0.0, QColor(8, 8, 12, 0))
        overlay.setColorAt(0.4, QColor(8, 8, 12, 30))
        overlay.setColorAt(0.7, QColor(8, 8, 12, 160))
        overlay.setColorAt(1.0, QColor(8, 8, 12, 245))
        p.fillRect(0, 0, w, h, overlay)

        # Back arrow — top left
        back_font = QFont()
        back_font.setPixelSize(22)
        back_font.setWeight(QFont.Weight.Bold)
        p.setFont(back_font)
        p.setPen(QPen(QColor(232, 232, 240, 180)))
        p.drawText(20, 20, 40, 40, Qt.AlignmentFlag.AlignCenter, "←")

        # Title — bottom left
        title_font = QFont()
        title_font.setPixelSize(36)
        title_font.setWeight(QFont.Weight.Bold)
        p.setFont(title_font)
        p.setPen(QPen(QColor(255, 255, 255)))
        title_rect = p.boundingRect(0, 0, w - 260, 50, Qt.TextFlag.TextWordWrap, self._title)
        title_y = h - 60 - title_rect.height()
        p.drawText(28, int(title_y), w - 260, title_rect.height() + 10,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                    self._title)

        # Rating — below title
        if self._rating_text:
            rating_font = QFont()
            rating_font.setPixelSize(15)
            p.setFont(rating_font)
            p.setPen(QPen(QColor(240, 160, 48)))  # amber
            p.drawText(28, h - 52, w - 260, 24,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        self._rating_text)

        # Launch button — bottom right, pill shape
        btn_w, btn_h = 200, 48
        btn_x, btn_y = w - btn_w - 28, h - btn_h - 28

        btn_path = QPainterPath()
        btn_path.addRoundedRect(QRectF(btn_x, btn_y, btn_w, btn_h), 22.0, 22.0)

        # Gradient fill for the button
        btn_grad = QLinearGradient(btn_x, btn_y, btn_x + btn_w, btn_y + btn_h)
        btn_grad.setColorAt(0.0, QColor(233, 69, 96))
        btn_grad.setColorAt(1.0, QColor(200, 50, 80))
        p.fillPath(btn_path, btn_grad)

        # Button text
        btn_font = QFont()
        btn_font.setPixelSize(16)
        btn_font.setWeight(QFont.Weight.Bold)
        btn_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        p.setFont(btn_font)
        p.setPen(QPen(QColor(255, 255, 255)))
        p.drawText(btn_x, btn_y, btn_w, btn_h, Qt.AlignmentFlag.AlignCenter, "LAUNCH")

        # Store rects for click detection
        self._back_rect = QRectF(10, 10, 60, 60)
        self._launch_rect = QRectF(btn_x, btn_y, btn_w, btn_h)

        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        pos = event.position() if hasattr(event, 'position') else event.pos()
        pt = QRectF(pos.x(), pos.y(), 1, 1)
        if hasattr(self, '_back_rect') and self._back_rect.intersects(pt):
            self.back_clicked.emit()
        elif hasattr(self, '_launch_rect') and self._launch_rect.intersects(pt):
            self.launch_clicked.emit()
        super().mousePressEvent(event)


# ── Main panel ─────────────────────────────────────────────────────────────


class GameDetailPanel(QScrollArea):
    """Cinematic game detail panel — hero header, info bar, description, media."""

    launch_requested = Signal(object)  # AppEntry
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical {"
            "  background: transparent; width: 6px; margin: 0;"
            "}"
            "QScrollBar::handle:vertical {"
            f"  background: {_TEXT_DIM}; border-radius: 3px; min-height: 30px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "  height: 0; background: none;"
            "}"
        )

        self._app: AppEntry | None = None

        # Root container
        self._root = QWidget()
        self._root_layout = QVBoxLayout(self._root)
        self._root_layout.setContentsMargins(0, 0, 0, 32)
        self._root_layout.setSpacing(0)
        self.setWidget(self._root)

        # ── Hero section ───────────────────────────────────────────────
        self._hero = _HeroWidget()
        self._hero.back_clicked.connect(self._on_back)
        self._hero.launch_clicked.connect(self._on_launch)
        self._root_layout.addWidget(self._hero)

        # ── Body (below hero) ──────────────────────────────────────────
        body = QWidget()
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(28, 20, 28, 0)
        self._body_layout.setSpacing(12)

        # Info bar (genre pills, platform, date, playtime)
        self._info_bar = QHBoxLayout()
        self._info_bar.setSpacing(8)
        self._info_bar_widget = QWidget()
        self._info_bar_widget.setLayout(self._info_bar)
        self._info_bar_widget.setStyleSheet("background: transparent;")
        self._body_layout.addWidget(self._info_bar_widget)

        # Description card
        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        self._desc_label.setTextFormat(Qt.TextFormat.RichText)
        self._desc_label.setStyleSheet(
            f"background: {_SURFACE}; color: {_TEXT_BODY}; "
            "border-radius: 12px; padding: 20px; font-size: 14px; "
            "line-height: 1.6;"
        )
        self._body_layout.addWidget(self._desc_label)

        # Screenshots
        self._body_layout.addWidget(_section_title("Screenshots"))
        self._screenshots_scroll = self._make_horizontal_scroll(150)
        self._screenshots_container = QWidget()
        self._screenshots_layout = QHBoxLayout(self._screenshots_container)
        self._screenshots_layout.setContentsMargins(0, 0, 0, 0)
        self._screenshots_layout.setSpacing(12)
        self._screenshots_scroll.setWidget(self._screenshots_container)
        self._body_layout.addWidget(self._screenshots_scroll)

        # Media: Trailers + Streams side-by-side
        media_row = QHBoxLayout()
        media_row.setSpacing(24)

        # Trailers column
        trailers_col = QVBoxLayout()
        trailers_col.setSpacing(8)
        trailers_col.addWidget(_section_title("Trailers"))
        self._trailers_scroll = self._make_horizontal_scroll(240)
        self._trailers_container = QWidget()
        self._trailers_layout = QHBoxLayout(self._trailers_container)
        self._trailers_layout.setContentsMargins(0, 0, 0, 0)
        self._trailers_layout.setSpacing(12)
        self._trailers_scroll.setWidget(self._trailers_container)
        trailers_col.addWidget(self._trailers_scroll)
        media_row.addLayout(trailers_col, 1)

        # Streams column
        streams_col = QVBoxLayout()
        streams_col.setSpacing(8)
        streams_col.addWidget(_section_title("Live Streams"))
        self._streams_scroll = self._make_horizontal_scroll(240)
        self._streams_container = QWidget()
        self._streams_layout = QHBoxLayout(self._streams_container)
        self._streams_layout.setContentsMargins(0, 0, 0, 0)
        self._streams_layout.setSpacing(12)
        self._streams_scroll.setWidget(self._streams_container)
        streams_col.addWidget(self._streams_scroll)
        media_row.addLayout(streams_col, 1)

        self._body_layout.addLayout(media_row)

        # Fan Profile — coming soon
        fan_frame = QFrame()
        fan_frame.setStyleSheet(
            f"background: {_SURFACE}; "
            f"border: 1px dashed {_TEXT_DIM}; "
            "border-radius: 12px; padding: 28px;"
        )
        fan_layout = QVBoxLayout(fan_frame)
        fan_title = QLabel("CUSTOM FAN PROFILE")
        fan_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fan_title.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 12px; letter-spacing: 2px; "
            "font-weight: bold; border: none; background: transparent;"
        )
        fan_layout.addWidget(fan_title)
        fan_sub = QLabel("Coming Soon")
        fan_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fan_sub.setStyleSheet(
            f"color: {_TEXT_DIM}; font-size: 13px; border: none; background: transparent;"
        )
        fan_layout.addWidget(fan_sub)
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
        self._hero.set_title(app.display_name)
        self._hero.set_rating("")
        self._desc_label.setText(
            f"<span style='color: {_TEXT_DIM}'>Loading game details…</span>"
        )

        # Reset media sections
        self._clear_layout(self._screenshots_layout)
        self._clear_layout(self._trailers_layout)
        self._clear_layout(self._streams_layout)
        self._clear_info_bar()

        # Placeholder header
        w = self._hero.width() or 800
        self._hero.set_pixmap(_placeholder_header(w, 400))

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
        self._hero.set_pixmap(pixmap)

    # ── Service callbacks ───────────────────────────────────────────────────

    def _on_rawg_data(self, data: dict) -> None:
        if self._app is None:
            return

        # Description
        desc = data.get("description", "") or data.get("description_raw", "")
        if desc:
            self._desc_label.setText(desc)
        else:
            self._desc_label.setText(
                f"<i style='color: {_TEXT_DIM}'>No description available.</i>"
            )

        # Rating
        rating = data.get("rating")
        if rating:
            stars = int(round(float(rating)))
            self._hero.set_rating(f"{'★' * stars}{'☆' * (5 - stars)}  {rating}/5")

        # Info bar
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

        # Screenshots — rounded thumbnail cards
        for shot in data.get("short_screenshots", [])[:6]:
            img_url = shot.get("image", "")
            if img_url:
                thumb = _ClickableImage(img_url)
                thumb.setFixedSize(240, 135)
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb.setStyleSheet(
                    f"background: {_BASE}; border-radius: 8px;"
                )
                thumb.setText(f"<span style='color: {_TEXT_DIM}; font-size: 11px'>Loading…</span>")
                thumb.setTextFormat(Qt.TextFormat.RichText)
                self._screenshots_layout.addWidget(thumb)

    def _on_youtube_data(self, results: list) -> None:
        self._clear_layout(self._trailers_layout)
        for item in results[:6]:
            title = item.get("title", "")
            channel = item.get("channel", "")
            url = item.get("url", "")
            card = _MediaCard(280, 158, title, channel, url)
            self._trailers_layout.addWidget(card)
        self._trailers_layout.addStretch()

    def _on_twitch_data(self, streams: list) -> None:
        self._clear_layout(self._streams_layout)
        for stream in streams[:6]:
            title = stream.get("user_name", "")
            viewers = stream.get("viewer_count", 0)
            url = stream.get("url", "")
            card = _MediaCard(280, 158, title, f"{viewers:,} viewers", url)
            self._streams_layout.addWidget(card)
        self._streams_layout.addStretch()

    # ── Navigation ──────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.back_requested.emit()
        else:
            super().keyPressEvent(event)

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_back(self) -> None:
        self.back_requested.emit()

    def _on_launch(self) -> None:
        if self._app is not None:
            self.launch_requested.emit(self._app)

    def _make_horizontal_scroll(self, height: int) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setFixedHeight(height)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        return scroll

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
