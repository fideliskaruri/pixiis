"""First-run onboarding page — welcome screen with store detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from pixiis.core.types import AppEntry

# ── Dark Cinema palette ───────────────────────────────────────────────────

_SURFACE = "#13121a"
_ACCENT = "#e94560"
_TEXT_PRIMARY = "#f0eef5"
_TEXT_SECONDARY = "#8a8698"
_TEXT_MUTED = "#7a7690"
_CHECK_GREEN = "#4ade80"
_CROSS_RED = "#f87171"

# ── Pre-built fonts ──────────────────────────────────────────────────────

_TITLE_FONT = QFont()
_TITLE_FONT.setPixelSize(32)
_TITLE_FONT.setBold(True)

_SUBTITLE_FONT = QFont()
_SUBTITLE_FONT.setPixelSize(16)

_STORE_FONT = QFont()
_STORE_FONT.setPixelSize(15)

_BTN_FONT = QFont()
_BTN_FONT.setPixelSize(16)
_BTN_FONT.setBold(True)


# ── Accent button (custom painted) ───────────────────────────────────────


class _AccentButton(QWidget):
    """A simple accent-colored button with custom paint."""

    clicked = Signal()

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._hovered = False
        self.setFixedSize(200, 48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        focused = self.hasFocus()

        path = QPainterPath()
        path.addRoundedRect(1.0, 1.0, w - 2.0, h - 2.0, 12.0, 12.0)

        if focused or self._hovered:
            p.fillPath(path, QColor(233, 69, 96, 230))
        else:
            p.fillPath(path, QColor(_ACCENT))

        if focused:
            p.setPen(QPen(QColor(255, 255, 255, 100), 2.0))
            p.drawPath(path)

        p.setPen(QColor(_TEXT_PRIMARY))
        p.setFont(_BTN_FONT)
        p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)


# ── Onboarding Page ──────────────────────────────────────────────────────


class OnboardingPage(QWidget):
    """Welcome screen shown on first launch before any cache exists."""

    lets_go = Signal()  # emitted when user clicks the button

    # Store display order
    _STORES = ["steam", "xbox", "epic", "gog", "ea"]
    _STORE_LABELS = {
        "steam": "Steam",
        "xbox": "Xbox",
        "epic": "Epic Games",
        "gog": "GOG Galaxy",
        "ea": "EA App",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("OnboardingPage")
        self.setStyleSheet("#OnboardingPage { background-color: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Vertical centering
        root.addStretch(2)

        # Title
        title = QLabel("Welcome to Pixiis")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(_TITLE_FONT)
        title.setStyleSheet(f"color: {_TEXT_PRIMARY}; background: transparent;")
        root.addWidget(title)

        root.addSpacing(8)

        # Subtitle
        subtitle = QLabel("Your games, one launcher")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setFont(_SUBTITLE_FONT)
        subtitle.setStyleSheet(f"color: {_TEXT_SECONDARY}; background: transparent;")
        root.addWidget(subtitle)

        root.addSpacing(40)

        # Scanning status label
        self._status_label = QLabel("Scanning for game stores...")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 13px; background: transparent;"
        )
        root.addWidget(self._status_label)

        root.addSpacing(16)

        # Store detection list (centered container)
        self._store_container = QWidget()
        store_layout = QVBoxLayout(self._store_container)
        store_layout.setContentsMargins(0, 0, 0, 0)
        store_layout.setSpacing(8)
        store_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._store_labels: dict[str, QLabel] = {}
        for store in self._STORES:
            lbl = QLabel(f"  ...  {self._STORE_LABELS[store]}")
            lbl.setFont(_STORE_FONT)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {_TEXT_MUTED}; background: transparent;")
            lbl.setFixedWidth(320)
            store_layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
            self._store_labels[store] = lbl

        root.addWidget(self._store_container, alignment=Qt.AlignmentFlag.AlignHCenter)

        root.addSpacing(40)

        # "Let's go!" button
        self._go_btn = _AccentButton("Let's go!")
        self._go_btn.clicked.connect(self.lets_go.emit)
        root.addWidget(self._go_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        root.addStretch(3)

    # -- public API ----------------------------------------------------------

    def update_stores(self, apps: list[AppEntry]) -> None:
        """Update the store list with detected game counts from scan results."""
        from pixiis.core.types import AppSource

        source_map = {
            "steam": AppSource.STEAM,
            "xbox": AppSource.XBOX,
            "epic": AppSource.EPIC,
            "gog": AppSource.GOG,
            "ea": AppSource.EA,
        }

        for store_key, label in self._store_labels.items():
            source = source_map.get(store_key)
            if source is None:
                continue
            count = sum(1 for a in apps if a.source == source and a.is_game)
            display_name = self._STORE_LABELS[store_key]
            if count > 0:
                label.setText(f"  \u2713  {display_name} detected ({count} games)")
                label.setStyleSheet(f"color: {_CHECK_GREEN}; background: transparent;")
            else:
                label.setText(f"  \u2717  {display_name} not found")
                label.setStyleSheet(f"color: {_CROSS_RED}; background: transparent;")

        self._status_label.setText("Scan complete!")
        self._status_label.setStyleSheet(
            f"color: {_TEXT_SECONDARY}; font-size: 13px; background: transparent;"
        )

        # Focus the button for controller use
        self._go_btn.setFocus()
