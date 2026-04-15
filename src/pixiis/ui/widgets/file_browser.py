"""File browser widget — QTreeView backed by QFileSystemModel."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QDir, QEvent, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileSystemModel,
    QFrame,
    QHeaderView,
    QLabel,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


def _default_root() -> str:
    """Return a sensible root directory for the current platform."""
    if sys.platform == "win32":
        return "C:/"
    return str(Path.home())


class FileBrowser(QFrame):
    """A file-system browser with breadcrumb path bar and tree view.

    Uses :class:`QFileSystemModel` so the tree is populated asynchronously
    and handles large directories without blocking the UI.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FileBrowser")
        self.setStyleSheet(
            "#FileBrowser { background-color: #13121a; border-radius: 6px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # -- path bar (breadcrumb) -------------------------------------------
        self._path_label = QLabel(_default_root())
        self._path_label.setStyleSheet(
            "QLabel {"
            "  color: #8a8698;"
            "  background-color: #1c1a24;"
            "  border: 1px solid #e94560;"
            "  border-radius: 4px;"
            "  padding: 4px 8px;"
            "  font-size: 13px;"
            "}"
        )
        self._path_label.setWordWrap(False)
        layout.addWidget(self._path_label)

        # -- file system model ------------------------------------------------
        self._model = QFileSystemModel()
        self._model.setRootPath(_default_root())
        self._model.setFilter(
            QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot
        )
        self._model.setNameFilterDisables(False)

        # -- tree view --------------------------------------------------------
        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setRootIndex(self._model.index(_default_root()))
        self._tree.setAnimated(False)
        self._tree.setSortingEnabled(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)

        # Column sizing
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        # Style
        self._tree.setStyleSheet(
            "QTreeView {"
            "  background-color: #13121a;"
            "  color: #f0eef5;"
            "  border: none;"
            "  font-size: 13px;"
            "}"
            "QTreeView::item {"
            "  padding: 4px 2px;"
            "}"
            "QTreeView::item:alternate {"
            "  background-color: #1c1a24;"
            "}"
            "QTreeView::item:selected {"
            "  background-color: #e94560;"
            "}"
            "QTreeView::item:hover {"
            "  background-color: rgba(233, 69, 96, 0.12);"
            "}"
            "QHeaderView::section {"
            "  background-color: #1c1a24;"
            "  color: #8a8698;"
            "  border: none;"
            "  border-bottom: 1px solid #e94560;"
            "  padding: 4px 6px;"
            "  font-weight: bold;"
            "}"
        )

        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.installEventFilter(self)
        layout.addWidget(self._tree, stretch=1)

    # -- public API -----------------------------------------------------------

    def navigate_to(self, path: str) -> None:
        """Set the tree root to *path* and update the path bar."""
        idx = self._model.index(path)
        if idx.isValid():
            self._tree.setRootIndex(idx)
            self._path_label.setText(path)

    def go_parent(self) -> None:
        """Navigate to the parent directory of the current root."""
        current = self._path_label.text()
        parent = str(Path(current).parent)
        if parent != current:
            self.navigate_to(parent)

    # -- event filter ---------------------------------------------------------

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._tree and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Backspace:
                self.go_parent()
                return True
        return super().eventFilter(obj, event)

    # -- internals ------------------------------------------------------------

    def _on_double_click(self, index: object) -> None:
        path = self._model.filePath(index)
        if not path:
            return
        info = self._model.fileInfo(index)
        if info.isDir():
            self.navigate_to(path)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Backspace:
            self.go_parent()
        else:
            super().keyPressEvent(event)
