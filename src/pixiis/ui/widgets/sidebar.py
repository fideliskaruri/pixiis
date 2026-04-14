"""Navigation sidebar with accent-bar active indicator."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class SidebarButton(QPushButton):
    """A sidebar navigation button with a left accent bar when active."""

    def __init__(self, text: str, page_name: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.page_name = page_name
        self._active = False

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(44)
        self._apply_style()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._apply_style()

    def _apply_style(self) -> None:
        if self._active:
            self.setStyleSheet(
                "QPushButton {"
                "  background-color: rgba(233, 69, 96, 0.15);"
                "  color: #e94560;"
                "  border: none;"
                "  border-left: 3px solid #e94560;"
                "  border-radius: 0;"
                "  text-align: left;"
                "  padding: 8px 16px 8px 13px;"
                "  font-weight: bold;"
                "  font-size: 14px;"
                "}"
                "QPushButton:focus {"
                "  border-left: 3px solid #e94560;"
                "  outline: 1px solid #e94560;"
                "}"
            )
        else:
            self.setStyleSheet(
                "QPushButton {"
                "  background-color: transparent;"
                "  color: #a0a0b0;"
                "  border: none;"
                "  border-left: 3px solid transparent;"
                "  border-radius: 0;"
                "  text-align: left;"
                "  padding: 8px 16px 8px 13px;"
                "  font-size: 14px;"
                "}"
                "QPushButton:hover {"
                "  background-color: rgba(255, 255, 255, 0.05);"
                "  color: #e0e0e0;"
                "}"
                "QPushButton:focus {"
                "  border-left: 3px solid #0f3460;"
                "  outline: 1px solid #0f3460;"
                "}"
            )


class Sidebar(QFrame):
    """Left-side navigation panel.

    Emits :pyqt:`page_requested(str)` when the user clicks a nav button.
    """

    page_requested = Signal(str)

    # (label, page_name)
    _NAV_ITEMS: list[tuple[str, str]] = [
        ("Home", "home"),
        ("Library", "library"),
        ("Settings", "settings"),
        ("Files", "file_manager"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setObjectName("Sidebar")
        self.setStyleSheet(
            "#Sidebar { background-color: #16213e; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- logo / title ----------------------------------------------------
        title = QLabel("PIXIIS")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFixedHeight(64)
        title.setStyleSheet(
            "QLabel {"
            "  font-size: 22px;"
            "  font-weight: bold;"
            "  color: #e94560;"
            "  letter-spacing: 4px;"
            "  background-color: transparent;"
            "}"
        )
        layout.addWidget(title)

        # -- navigation buttons ----------------------------------------------
        self._buttons: dict[str, SidebarButton] = {}
        for label, page_name in self._NAV_ITEMS:
            btn = SidebarButton(label, page_name)
            btn.clicked.connect(self._on_button_clicked)
            layout.addWidget(btn)
            self._buttons[page_name] = btn

        layout.addStretch()

    # -- public API ----------------------------------------------------------

    def set_active(self, page_name: str) -> None:
        """Highlight *page_name* and deactivate others."""
        for name, btn in self._buttons.items():
            btn.set_active(name == page_name)

    # -- internals -----------------------------------------------------------

    def _on_button_clicked(self) -> None:
        btn = self.sender()
        if isinstance(btn, SidebarButton):
            self.page_requested.emit(btn.page_name)
