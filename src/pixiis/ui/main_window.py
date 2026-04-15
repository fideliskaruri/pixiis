"""Main application window — sidebar, page stack, controller bridge."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
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
    """Top-level frameless window containing sidebar and page stack.

    When *registry* and/or *controller_bridge* are provided (daemon mode)
    the window uses them instead of creating its own.  In that case the
    close button hides the window to the system tray rather than quitting.
    """

    _refresh_signal = Signal(list)  # emitted from any thread, handled on main

    def __init__(
        self,
        *,
        registry: AppRegistry | None = None,
        controller_bridge: ControllerBridge | None = None,
    ) -> None:
        super().__init__()
        self._config = get_config()
        self._owns_controller = controller_bridge is None
        self._cleaned_up = False

        # -- window chrome (always frameless) --------------------------------
        self.setWindowTitle("Pixiis")
        self.setMinimumSize(1280, 720)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._dragging = False
        self._drag_offset = None

        if self._config.get("ui.fullscreen", False):
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
        self._registry = registry or AppRegistry(self._config)
        self._scan_thread: QThread | None = None
        self._start_scan()

        # -- services --------------------------------------------------------
        self._controller_bridge = controller_bridge or ControllerBridge(self)

        self._image_loader = None
        self._rawg_client = None
        self._youtube_client = None
        self._twitch_client = None
        self._vibration = None

        try:
            from pixiis.services.image_loader import AsyncImageLoader
            self._image_loader = AsyncImageLoader(self)
        except Exception:
            pass
        try:
            from pixiis.services.rawg import RawgClient
            self._rawg_client = RawgClient(self)
        except Exception:
            pass
        try:
            from pixiis.services.youtube import YouTubeClient
            self._youtube_client = YouTubeClient(self)
        except Exception:
            pass
        try:
            from pixiis.services.twitch import TwitchClient
            self._twitch_client = TwitchClient(self)
        except Exception:
            pass
        try:
            from pixiis.services.vibration import VibrationService
            self._vibration = VibrationService(self)
        except Exception:
            pass

        try:
            from pixiis.ui.widgets.voice_overlay import VoiceOverlay
            self._voice_overlay = VoiceOverlay()
        except Exception:
            self._voice_overlay = None

        # -- register pages --------------------------------------------------
        self._register_pages()

        # -- navigation state ------------------------------------------------
        self._nav_stack: list[str] = ["home"]
        self._sidebar.set_active("home")

        # -- signals ---------------------------------------------------------
        self._sidebar.page_requested.connect(self.navigate_to)
        self._sidebar.minimize_requested.connect(self.showMinimized)
        self._sidebar.maximize_requested.connect(self._toggle_maximize)
        self._sidebar.close_requested.connect(self.close)
        self._refresh_signal.connect(self._refresh_pages)
        self._controller_bridge.tab_next.connect(self._nav_next_page)
        self._controller_bridge.tab_prev.connect(self._nav_prev_page)
        self._controller_bridge.voice_start.connect(self._on_voice_start)
        self._controller_bridge.voice_stop.connect(self._on_voice_stop)
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
                from pixiis.ui.pages.home_page import HomePage
                page = HomePage(self._registry, image_loader=self._image_loader)
                page.game_selected.connect(self._on_game_selected)
                return page
            if name == "library":
                from pixiis.ui.pages.library_page import LibraryPage
                page = LibraryPage(self._registry, image_loader=self._image_loader)
                page.game_selected.connect(self._on_game_selected)
                return page
            if name == "settings":
                from pixiis.ui.pages.settings_page import SettingsPage
                tm = getattr(QApplication.instance(), '_theme_manager', None)
                return SettingsPage(theme_manager=tm, registry=self._registry)
            if name == "file_manager":
                from pixiis.ui.pages.file_manager_page import FileManagerPage
                return FileManagerPage()
            if name == "game_detail":
                from pixiis.ui.widgets.game_detail_panel import GameDetailPanel
                panel = GameDetailPanel()
                panel.back_requested.connect(self.go_back)
                panel.launch_requested.connect(self._on_launch_requested)
                return panel
        except Exception as e:
            print(f"[Pixiis] Failed to load page '{name}': {e}")

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

    # -- bumper page cycling -------------------------------------------------

    _PAGE_ORDER = ["home", "library", "settings", "file_manager"]

    def _nav_next_page(self) -> None:
        """RB — cycle to next page."""
        current = self._page_stack.current_page_name()
        if current in self._PAGE_ORDER:
            idx = (self._PAGE_ORDER.index(current) + 1) % len(self._PAGE_ORDER)
            self.navigate_to(self._PAGE_ORDER[idx])

    def _nav_prev_page(self) -> None:
        """LB — cycle to previous page."""
        current = self._page_stack.current_page_name()
        if current in self._PAGE_ORDER:
            idx = (self._PAGE_ORDER.index(current) - 1) % len(self._PAGE_ORDER)
            self.navigate_to(self._PAGE_ORDER[idx])

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # -- frameless window drag -----------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Only drag from the top nav bar area (first 60px)
            if event.position().y() <= 60:
                self._dragging = True
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        # Double-click on nav bar toggles fullscreen
        if event.position().y() <= 60:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

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
        worker.finished.connect(self._refresh_pages)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._scan_thread = thread
        # Keep a reference so the worker isn't GC'd
        self._scan_worker = worker
        thread.start()

    def _on_library_updated(self, event: LibraryUpdatedEvent) -> None:
        """Called from scan thread — marshal to main thread via signal."""
        self._refresh_signal.emit(event.apps)

    def _refresh_pages(self, apps: list) -> None:
        """Refresh pages on the main thread (safe for UI updates)."""
        for name in ("home", "library"):
            page = self._page_stack._pages.get(name)
            if page is not None and hasattr(page, "refresh"):
                page.refresh(apps)

    def _on_game_selected(self, app) -> None:
        """Navigate to game detail when a tile is activated."""
        detail = self._page_stack._pages.get("game_detail")
        if detail is not None and hasattr(detail, "set_game"):
            detail.set_game(
                app,
                rawg_client=self._rawg_client,
                youtube_client=self._youtube_client,
                twitch_client=self._twitch_client,
            )
        self.navigate_to("game_detail")
        # Focus the launch button for immediate A-press
        if detail and hasattr(detail, '_hero') and hasattr(detail._hero, '_launch_btn'):
            detail._hero._launch_btn.setFocus()

    def _on_voice_start(self) -> None:
        if self._voice_overlay:
            self._voice_overlay.show_text("Listening...", is_final=False)
        # Focus search bar on searchable pages
        current = self._page_stack.current_page_name()
        if current in ("home", "library"):
            page = self._page_stack._pages.get(current)
            if page and hasattr(page, '_search') and page._search:
                page._search.setFocus()

    def _on_voice_stop(self) -> None:
        if self._voice_overlay:
            self._voice_overlay.show_text("Processing...", is_final=True)

    def _on_launch_requested(self, app) -> None:
        """Launch the selected game."""
        try:
            self._registry.launch(app)
        except Exception as e:
            print(f"[Pixiis] Launch failed: {e}")

    # -- cleanup -------------------------------------------------------------

    def cleanup(self) -> None:
        """Release event subscriptions and controller resources.

        Called by the daemon before shutdown, and also from *closeEvent*
        in standalone mode.  Safe to call more than once.
        """
        if self._cleaned_up:
            return
        self._cleaned_up = True
        if self._owns_controller:
            self._controller_bridge.shutdown()
        if hasattr(self, '_voice_overlay') and self._voice_overlay:
            self._voice_overlay.close()
        bus.unsubscribe(LibraryUpdatedEvent, self._on_library_updated)

    def closeEvent(self, event) -> None:
        if not self._owns_controller:
            # Daemon mode — hide to tray instead of quitting
            event.ignore()
            self.hide()
            return
        # Standalone mode — full cleanup and close
        self.cleanup()
        super().closeEvent(event)
