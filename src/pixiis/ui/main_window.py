"""Main application window — sidebar, page stack, controller bridge."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from pixiis.core import get_config, bus
from pixiis.library.registry import AppRegistry, LibraryUpdatedEvent
from pixiis.ui.controller_bridge import ControllerBridge
from pixiis.ui.page_stack import PageStack
from pixiis.ui.widgets.sidebar import Sidebar

if TYPE_CHECKING:
    from pixiis.core.types import AppEntry


# ── Background scanner ─────────────────────────────────────────────────────


class _ScanWorker(QObject):
    """Runs AppRegistry.scan_all() off the main thread."""

    finished = Signal(list)

    def __init__(self, registry: AppRegistry) -> None:
        super().__init__()
        self._registry = registry

    def run(self) -> None:
        try:
            apps = self._registry.scan_all()
        except Exception:
            apps = []
        self.finished.emit(apps)


# ── Main window ────────────────────────────────────────────────────────────


class MainWindow(QMainWindow):
    """Top-level frameless window containing sidebar and page stack."""

    def __init__(self) -> None:
        super().__init__()
        self._config = get_config()

        # -- window chrome ---------------------------------------------------
        self.setWindowTitle("Pixiis")
        self.setMinimumSize(1280, 720)

        if self._config.get("ui.fullscreen", False):
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | self.windowFlags()
            )
            self.showFullScreen()

        # -- central layout --------------------------------------------------
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Top navigation bar (fixed height)
        self._sidebar = Sidebar()
        root_layout.addWidget(self._sidebar)

        # Page stack (fills remaining space)
        self._page_stack = PageStack()
        root_layout.addWidget(self._page_stack, stretch=1)

        # -- registry & scanning ---------------------------------------------
        self._registry = AppRegistry(self._config)
        self._scan_thread: QThread | None = None
        self._start_scan()

        # -- services --------------------------------------------------------
        self._controller_bridge = ControllerBridge(self)

        # -- register pages --------------------------------------------------
        self._register_pages()

        # -- navigation state ------------------------------------------------
        self._nav_stack: list[str] = ["home"]
        self._sidebar.set_active("home")

        # -- signals ---------------------------------------------------------
        self._sidebar.page_requested.connect(self.navigate_to)
        bus.subscribe(LibraryUpdatedEvent, self._on_library_updated)

    # -- page registration ---------------------------------------------------

    def _register_pages(self) -> None:
        """Create and register all pages.

        Pages are expected to be QWidget subclasses. If the actual page
        modules aren't available yet we insert simple placeholders.
        """
        page_defs: list[tuple[str, str]] = [
            ("home", "Home"),
            ("library", "Library"),
            ("settings", "Settings"),
            ("file_manager", "File Manager"),
            ("game_detail", "Game Detail"),
        ]

        for name, label in page_defs:
            page = self._try_load_page(name, label)
            self._page_stack.register_page(name, page)

    def _try_load_page(self, name: str, label: str) -> QWidget:
        """Attempt to import a real page; fall back to a placeholder."""
        try:
            if name == "home":
                from pixiis.ui.pages.home import HomePage
                return HomePage(self._registry)
            if name == "library":
                from pixiis.ui.pages.library import LibraryPage
                return LibraryPage(self._registry)
            if name == "settings":
                from pixiis.ui.pages.settings import SettingsPage
                return SettingsPage()
            if name == "file_manager":
                from pixiis.ui.pages.file_manager import FileManagerPage
                return FileManagerPage()
            if name == "game_detail":
                from pixiis.ui.pages.game_detail import GameDetailPage
                return GameDetailPage(self._registry)
        except Exception:
            pass

        return self._make_placeholder(label)

    @staticmethod
    def _make_placeholder(label: str) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size: 24px; color: #555;")
        layout.addWidget(lbl)
        return page

    # -- navigation ----------------------------------------------------------

    def navigate_to(self, page_name: str) -> None:
        """Switch the page stack to *page_name* and update the sidebar."""
        current = self._page_stack.current_page_name()
        if page_name == current:
            return

        # Determine slide direction based on nav stack
        direction = "right"
        if self._nav_stack and page_name in self._nav_stack:
            direction = "left"

        self._page_stack.switch_to(page_name, direction=direction)
        self._sidebar.set_active(page_name)

        # Update nav stack
        if self._nav_stack and self._nav_stack[-1] != page_name:
            self._nav_stack.append(page_name)

    def go_back(self) -> None:
        """Pop the navigation stack and return to the previous page."""
        if len(self._nav_stack) > 1:
            self._nav_stack.pop()
            prev = self._nav_stack[-1]
            self._page_stack.switch_to(prev, direction="left")
            self._sidebar.set_active(prev)

    # -- keyboard shortcuts --------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.go_back()
        elif key == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        else:
            super().keyPressEvent(event)

    # -- library scanning ----------------------------------------------------

    def _start_scan(self) -> None:
        thread = QThread(self)
        worker = _ScanWorker(self._registry)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._scan_thread = thread
        # Keep a reference so the worker isn't GC'd
        self._scan_worker = worker
        thread.start()

    def _on_library_updated(self, event: LibraryUpdatedEvent) -> None:
        """Refresh pages when the library finishes scanning."""
        # Pages that care about the app list can subscribe to the event
        # themselves. This is a hook point if we need window-level updates.
        pass

    # -- cleanup -------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._controller_bridge.shutdown()
        bus.unsubscribe(LibraryUpdatedEvent, self._on_library_updated)
        super().closeEvent(event)
