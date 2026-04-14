"""File manager page — thin wrapper around the FileBrowser widget."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from pixiis.ui.widgets.file_browser import FileBrowser


class FileManagerPage(QWidget):
    """Page that embeds a :class:`FileBrowser` filling the available space.

    Navigation back is handled by the controller (B / Escape) at the
    MainWindow level, so this page only provides the browser itself.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FileManagerPage")
        self.setStyleSheet("#FileManagerPage { background-color: transparent; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(10)

        # -- header -----------------------------------------------------------
        title = QLabel("File Manager")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title.setStyleSheet(
            "QLabel {"
            "  font-size: 20px;"
            "  font-weight: bold;"
            "  color: #e0e0e0;"
            "  background: transparent;"
            "  padding-bottom: 2px;"
            "}"
        )
        layout.addWidget(title)

        # -- browser ----------------------------------------------------------
        self._browser = FileBrowser()
        layout.addWidget(self._browser, stretch=1)

    # -- public API -----------------------------------------------------------

    @property
    def browser(self) -> FileBrowser:
        return self._browser
