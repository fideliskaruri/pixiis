"""SearchBar — styled search input with debounced signal."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QLineEdit, QWidget

ACCENT = "#e94560"
BG = "#16213e"
TEXT = "#e0e0e0"
BORDER = "#0f3460"


class SearchBar(QLineEdit):
    """Rounded search field with 300 ms debounced ``search_changed`` signal."""

    search_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("\U0001f50d  Search games...")
        self.setClearButtonEnabled(True)
        self.setMinimumHeight(40)

        self.setStyleSheet(
            f"QLineEdit {{"
            f"  background: {BG}; color: {TEXT}; border: 1px solid {BORDER};"
            f"  border-radius: 20px; padding: 8px 20px; font-size: 14px;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border: 2px solid {ACCENT};"
            f"}}"
        )

        # Debounce timer
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._emit_search)

        self.textChanged.connect(self._on_text_changed)

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_text_changed(self, _text: str) -> None:
        self._debounce.start()

    def _emit_search(self) -> None:
        self.search_changed.emit(self.text().strip())

    # ── Key overrides ───────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
            self.search_changed.emit("")
            # Return focus to parent so tiles can be navigated
            parent = self.parentWidget()
            if parent is not None:
                parent.setFocus()
        else:
            super().keyPressEvent(event)
