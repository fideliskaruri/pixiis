"""Main application window — sidebar, page stack, controller bridge."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
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
from pixiis.core.types import TranscriptionEvent
from pixiis.library.registry import AppRegistry, LibraryUpdatedEvent
from pixiis.ui.controller_bridge import ControllerBridge
from pixiis.ui.page_stack import PageStack
from pixiis.ui.widgets.sidebar import Sidebar
from pixiis.ui.widgets.toast import Toast

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

        # Console experience — fullscreen by default
        if self._config.get("ui.fullscreen", True):
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

        # -- toast notification ----------------------------------------------
        self._toast = Toast(central)

        # -- registry & scanning ---------------------------------------------
        self._registry = registry or AppRegistry(self._config)
        self._scan_thread: QThread | None = None
        self._has_cache = bool(self._registry.get_all())
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
            self._vibration = VibrationService(parent=self)
        except Exception:
            pass

        try:
            from pixiis.ui.widgets.voice_overlay import VoiceOverlay
            self._voice_overlay = VoiceOverlay(self)
        except Exception:
            self._voice_overlay = None

        # Voice recording pipeline (faster-whisper)
        self._voice_pipeline = None
        try:
            from pixiis.voice.pipeline import VoicePipeline
            self._voice_pipeline = VoicePipeline()
            print("[Pixiis] Voice pipeline created OK")
        except Exception as e:
            print(f"[Pixiis] Voice pipeline unavailable: {e}")
            self._voice_pipeline = None

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
        bus.subscribe(TranscriptionEvent, self._on_transcription)

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
                if hasattr(page, '_search') and page._search and hasattr(page._search, 'mic_clicked'):
                    page._search.mic_clicked.connect(self._on_voice_start)
                return page
            if name == "library":
                from pixiis.ui.pages.library_page import LibraryPage
                page = LibraryPage(self._registry, image_loader=self._image_loader)
                page.game_selected.connect(self._on_game_selected)
                if hasattr(page, '_search') and page._search and hasattr(page._search, 'mic_clicked'):
                    page._search.mic_clicked.connect(self._on_voice_start)
                return page
            if name == "settings":
                from pixiis.ui.pages.settings_page import SettingsPage
                tm = getattr(QApplication.instance(), '_theme_manager', None)
                page = SettingsPage(theme_manager=tm, registry=self._registry)
                page.settings_saved.connect(
                    lambda: self.show_toast("Settings saved")
                )
                page.scan_requested.connect(self._start_scan)
                return page
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
        lbl.setStyleSheet("font-size: 24px; color: #7a7690;")
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
        if self._vibration:
            try:
                self._vibration.pulse(left=10000, right=10000, duration_ms=40)
            except Exception:
                pass
        current = self._page_stack.current_page_name()
        if current in self._PAGE_ORDER:
            idx = (self._PAGE_ORDER.index(current) + 1) % len(self._PAGE_ORDER)
            self.navigate_to(self._PAGE_ORDER[idx])

    def _nav_prev_page(self) -> None:
        """LB — cycle to previous page."""
        if self._vibration:
            try:
                self._vibration.pulse(left=10000, right=10000, duration_ms=40)
            except Exception:
                pass
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
            # Only drag from the top nav bar area
            if event.position().y() <= 52:
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
        if event.position().y() <= 52:
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
        if not self._has_cache:
            self.show_toast("Scanning library...", icon="info")

        # Disable Scan Now button in settings if available
        settings = self._page_stack._pages.get("settings")
        if settings and hasattr(settings, '_scan_btn'):
            settings._scan_btn.setText("Scanning...")
            settings._scan_btn.setEnabled(False)

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

        # Scan-complete feedback
        n_games = sum(1 for a in apps if a.is_game)
        n_apps = len(apps) - n_games
        if n_apps:
            self.show_toast(f"{n_games} games, {n_apps} apps found")
        else:
            self.show_toast(f"{n_games} games found")

        # Restore Scan Now button in settings
        settings = self._page_stack._pages.get("settings")
        if settings and hasattr(settings, '_scan_btn'):
            settings._scan_btn.setText("Scan Now")
            settings._scan_btn.setEnabled(True)

    def _on_game_selected(self, app) -> None:
        """Navigate to game detail when a tile is activated."""
        detail = self._page_stack._pages.get("game_detail")
        if detail is not None and hasattr(detail, "set_game"):
            detail.set_game(
                app,
                rawg_client=self._rawg_client,
                youtube_client=self._youtube_client,
                twitch_client=self._twitch_client,
                image_loader=self._image_loader,
            )
        self.navigate_to("game_detail")
        # Focus the launch button for immediate A-press
        if detail and hasattr(detail, '_hero') and hasattr(detail._hero, '_launch_btn'):
            detail._hero._launch_btn.setFocus()

    def _on_voice_start(self) -> None:
        print("[Pixiis Voice] === VOICE START ===")

        # Vibration feedback
        if self._vibration:
            try:
                self._vibration.pulse(left=12000, right=12000, duration_ms=50)
                print("[Pixiis Voice] Vibration pulse sent")
            except Exception as e:
                print(f"[Pixiis Voice] Vibration failed: {e}")

        # Show overlay
        if self._voice_overlay:
            self._voice_overlay.show_text("Listening...", is_final=False)
            print("[Pixiis Voice] Overlay shown: Listening...")

        # Focus search bar and show mic recording state
        current = self._page_stack.current_page_name()
        if current in ("home", "library"):
            page = self._page_stack._pages.get(current)
            if page and hasattr(page, '_search') and page._search:
                page._search.setFocus()
                if hasattr(page._search, 'set_mic_recording'):
                    page._search.set_mic_recording(True)
                print("[Pixiis Voice] Search bar focused + mic icon active")

        # Start actual voice recording
        if self._voice_pipeline is not None:
            print("[Pixiis Voice] Starting recording...")
            try:
                # Ensure workers are running
                if not self._voice_pipeline._threads:
                    self._voice_pipeline.start()
                    print("[Pixiis Voice] Pipeline workers started")
                # Start mic capture + rolling transcription
                self._voice_pipeline._start_recording()
                print("[Pixiis Voice] Recording from mic — speak now")
            except Exception as e:
                print(f"[Pixiis Voice] Recording start FAILED: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("[Pixiis Voice] WARNING: No voice pipeline available!")
            print("[Pixiis Voice] Check: pip install faster-whisper sounddevice numpy")

    def _on_voice_stop(self) -> None:
        print("[Pixiis Voice] === VOICE STOP ===")

        # Stop recording — triggers final transcription
        if self._voice_pipeline is not None:
            print("[Pixiis Voice] Stopping recording...")
            try:
                self._voice_pipeline._stop_recording()
                print("[Pixiis Voice] Final transcription queued — waiting for result...")
            except Exception as e:
                print(f"[Pixiis Voice] Recording stop FAILED: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("[Pixiis Voice] WARNING: No voice pipeline to stop")

        # Reset search bar mic state
        current = self._page_stack.current_page_name()
        if current in ("home", "library"):
            page = self._page_stack._pages.get(current)
            if page and hasattr(page, '_search') and page._search:
                if hasattr(page._search, 'set_mic_recording'):
                    page._search.set_mic_recording(False)

        if self._voice_overlay:
            self._voice_overlay.show_text("Processing...", is_final=False)

    def _on_transcription(self, event: TranscriptionEvent) -> None:
        """Write final transcription text into the active search bar."""
        print(f"[Pixiis Voice] TranscriptionEvent: is_final={event.is_final} text='{event.text}'")
        if not event.is_final:
            # Show interim text in overlay
            if self._voice_overlay:
                self._voice_overlay.show_text(event.text, is_final=False)
            return
        text = event.text

        def _apply() -> None:
            current = self._page_stack.current_page_name()
            print(f"[Pixiis Voice] Writing to search bar on page '{current}': '{text}'")
            if current in ("home", "library"):
                page = self._page_stack._pages.get(current)
                if page and hasattr(page, "_search") and page._search:
                    page._search.setText(text)
                    page._search.search_changed.emit(text)
                    print(f"[Pixiis Voice] Text written to search bar OK")
                else:
                    print(f"[Pixiis Voice] No search bar found on page")
            else:
                print(f"[Pixiis Voice] Not on a searchable page")
            if self._voice_overlay:
                self._voice_overlay.dismiss()

        QTimer.singleShot(0, _apply)

    def show_toast(self, msg: str, icon: str = "success") -> None:
        """Show a floating toast notification."""
        self._toast.show_message(msg, icon=icon)

    def _on_launch_requested(self, app) -> None:
        """Launch the selected game."""
        if self._vibration:
            try:
                self._vibration.rumble_launch()
            except Exception:
                pass
        name = getattr(app, "display_name", "game")
        self.show_toast(f"Launching {name}...", icon="info")

        # Update launch button text and disable to prevent double-press
        detail = self._page_stack._pages.get("game_detail")
        btn = None
        if detail and hasattr(detail, '_hero') and hasattr(detail._hero, '_launch_btn'):
            btn = detail._hero._launch_btn
            btn.setEnabled(False)
            btn.setText("Launching...")

        def _restore_btn() -> None:
            if btn is not None:
                btn.setText("\u25b6  LAUNCH")
                btn.setEnabled(True)

        try:
            self._registry.launch(app)
            QTimer.singleShot(2000, _restore_btn)
        except Exception as e:
            self.show_toast(f"Launch failed: {e}", icon="error")
            _restore_btn()  # re-enable immediately on error

    # -- cleanup -------------------------------------------------------------

    def cleanup(self) -> None:
        """Release event subscriptions and controller resources.

        Called by the daemon before shutdown, and also from *closeEvent*
        in standalone mode.  Safe to call more than once.
        """
        if self._cleaned_up:
            return
        self._cleaned_up = True
        # Stop background scan thread if still running
        if self._scan_thread is not None and self._scan_thread.isRunning():
            self._scan_thread.quit()
            self._scan_thread.wait(3000)
        if self._owns_controller:
            self._controller_bridge.shutdown()
        if hasattr(self, '_voice_overlay') and self._voice_overlay:
            self._voice_overlay.cleanup()
            self._voice_overlay.close()
        if self._voice_pipeline is not None:
            try:
                self._voice_pipeline.stop()
            except Exception:
                pass
        bus.unsubscribe(LibraryUpdatedEvent, self._on_library_updated)
        bus.unsubscribe(TranscriptionEvent, self._on_transcription)

    def closeEvent(self, event) -> None:
        if not self._owns_controller:
            # Daemon mode — hide to tray instead of quitting
            event.ignore()
            self.hide()
            return
        # Standalone mode — full cleanup and close
        self.cleanup()
        super().closeEvent(event)
