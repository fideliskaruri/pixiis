"""Main application window — sidebar, page stack, controller bridge."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from pixiis.core import get_config, bus
from pixiis.core.types import AppEntry, TranscriptionEvent
from pixiis.library.playtime import PlaytimeTracker
from pixiis.library.registry import AppRegistry, LibraryUpdatedEvent
from pixiis.ui.controller_bridge import ControllerBridge
from pixiis.ui.page_stack import PageStack
from pixiis.ui.widgets.quick_resume import QuickResume
from pixiis.ui.widgets.sidebar import Sidebar
from pixiis.ui.widgets.toast import Toast
from pixiis.ui.widgets.virtual_keyboard import VirtualKeyboard

if TYPE_CHECKING:
    pass


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
            logger.debug("Library scan failed", exc_info=True)
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
    _transcription_signal = Signal(str)  # marshals transcription text to main thread

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
            logger.debug("AsyncImageLoader unavailable", exc_info=True)
        try:
            from pixiis.services.rawg import RawgClient
            self._rawg_client = RawgClient(self)
        except Exception:
            logger.debug("RawgClient unavailable", exc_info=True)
        try:
            from pixiis.services.youtube import YouTubeClient
            self._youtube_client = YouTubeClient(self)
        except Exception:
            logger.debug("YouTubeClient unavailable", exc_info=True)
        try:
            from pixiis.services.twitch import TwitchClient
            self._twitch_client = TwitchClient(self)
        except Exception:
            logger.debug("TwitchClient unavailable", exc_info=True)
        try:
            from pixiis.services.vibration import VibrationService
            self._vibration = VibrationService(parent=self)
        except Exception:
            logger.debug("VibrationService unavailable", exc_info=True)

        try:
            from pixiis.ui.widgets.voice_overlay import VoiceOverlay
            self._voice_overlay = VoiceOverlay(self)
        except Exception:
            logger.debug("VoiceOverlay unavailable", exc_info=True)
            self._voice_overlay = None

        # Voice recording pipeline (faster-whisper)
        self._voice_pipeline = None
        self._voice_ready = False
        try:
            from pixiis.voice.pipeline import VoicePipeline
            self._voice_pipeline = VoicePipeline()
            self._voice_pipeline.start()  # start worker threads
            # Load Whisper model in background thread (3GB, takes seconds)
            import threading
            def _load_voice_model():
                try:
                    logger.info("Loading Whisper model in background...")
                    self._voice_pipeline._ensure_models()
                    self._voice_ready = True
                    logger.info("Whisper model loaded — voice search ready")
                except Exception:
                    logger.warning("Whisper model load failed", exc_info=True)
            threading.Thread(target=_load_voice_model, daemon=True).start()
        except Exception:
            logger.debug("Voice pipeline unavailable", exc_info=True)
            self._voice_pipeline = None

        # -- playtime tracking -----------------------------------------------
        self._playtime_tracker = PlaytimeTracker()
        self._launched_apps: dict[str, AppEntry] = {}  # app.id -> AppEntry
        self._launched_pids: dict[str, int | None] = {}  # app.id -> PID (if known)

        # Timer: every 30 seconds, check if launched games are still running
        self._playtime_timer = QTimer(self)
        self._playtime_timer.setInterval(30_000)
        self._playtime_timer.timeout.connect(self._check_running_games)

        # -- register pages --------------------------------------------------
        self._register_pages()

        # -- Quick Resume overlay (on central widget, above page stack) ------
        self._quick_resume = QuickResume(self.centralWidget())
        self._quick_resume.launch_requested.connect(self._on_launch_requested)

        # -- Virtual Keyboard overlay (on central widget) --------------------
        self._virtual_keyboard = VirtualKeyboard(parent=self.centralWidget())
        self._virtual_keyboard.dismissed.connect(self._on_keyboard_dismissed)
        self._virtual_keyboard.text_submitted.connect(self._on_keyboard_submitted)

        # -- First-run onboarding --------------------------------------------
        try:
            from pixiis.core.paths import cache_dir
            self._onboarded = (cache_dir() / ".onboarded").exists()
        except Exception:
            self._onboarded = False
        if not self._has_cache and not self._onboarded:
            # Stay on onboarding (it's the first registered page, already current)
            self._nav_stack = ["onboarding"]
            self._sidebar.set_active("")
        else:
            # Skip onboarding — jump to home (no animation at startup)
            home_widget = self._page_stack._pages.get("home")
            if home_widget is not None:
                self._page_stack.setCurrentWidget(home_widget)
                self._page_stack._current_name = "home"
            self._nav_stack = ["home"]
            self._sidebar.set_active("home")

        # -- navigation state ------------------------------------------------
        # (nav_stack already set above based on onboarding check)

        # -- signals ---------------------------------------------------------
        self._sidebar.page_requested.connect(self.navigate_to)
        self._sidebar.minimize_requested.connect(self.showMinimized)
        self._sidebar.maximize_requested.connect(self._toggle_maximize)
        self._sidebar.close_requested.connect(self.close)
        self._refresh_signal.connect(self._refresh_pages)
        self._transcription_signal.connect(self._apply_transcription)
        self._controller_bridge.tab_next.connect(self._nav_next_page)
        self._controller_bridge.tab_prev.connect(self._nav_prev_page)
        self._controller_bridge.voice_start.connect(self._on_voice_start)
        self._controller_bridge.voice_stop.connect(self._on_voice_stop)
        self._controller_bridge.toggle_app.connect(self._toggle_visibility)
        self._controller_bridge.keyboard_requested.connect(self._show_virtual_keyboard)
        self._controller_bridge.favorite_toggle.connect(self._on_controller_favorite_toggle)
        bus.subscribe(LibraryUpdatedEvent, self._on_library_updated)
        bus.subscribe(TranscriptionEvent, self._on_transcription)

    # -- page registration ---------------------------------------------------

    def _register_pages(self) -> None:
        """Create and register all pages.

        Pages are expected to be QWidget subclasses. If the actual page
        modules aren't available yet we insert simple placeholders.
        """
        page_defs: list[tuple[str, str]] = [
            ("onboarding", "Onboarding"),
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
            if name == "onboarding":
                from pixiis.ui.pages.onboarding_page import OnboardingPage
                page = OnboardingPage()
                page.lets_go.connect(self._on_onboarding_done)
                return page
            if name == "home":
                from pixiis.ui.pages.home_page import HomePage
                page = HomePage(self._registry, image_loader=self._image_loader)
                page.game_selected.connect(self._on_game_selected)
                if hasattr(page, '_grid') and page._grid and hasattr(page._grid, 'tile_favorite_toggled'):
                    page._grid.tile_favorite_toggled.connect(self._on_favorite_toggled)
                if hasattr(page, '_search') and page._search:
                    if hasattr(page._search, 'mic_clicked'):
                        page._search.mic_clicked.connect(self._on_voice_start)
                    if hasattr(page._search, 'mic_stopped'):
                        page._search.mic_stopped.connect(self._on_voice_stop)
                return page
            if name == "library":
                from pixiis.ui.pages.library_page import LibraryPage
                page = LibraryPage(self._registry, image_loader=self._image_loader)
                page.game_selected.connect(self._on_game_selected)
                if hasattr(page, '_grid') and page._grid and hasattr(page._grid, 'tile_favorite_toggled'):
                    page._grid.tile_favorite_toggled.connect(self._on_favorite_toggled)
                if hasattr(page, '_search') and page._search:
                    if hasattr(page._search, 'mic_clicked'):
                        page._search.mic_clicked.connect(self._on_voice_start)
                    if hasattr(page._search, 'mic_stopped'):
                        page._search.mic_stopped.connect(self._on_voice_stop)
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
        except Exception:
            logger.debug("Failed to load page '%s'", name, exc_info=True)

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
                logger.debug("Vibration pulse failed", exc_info=True)
        current = self._page_stack.current_page_name()
        if current in self._PAGE_ORDER:
            idx = (self._PAGE_ORDER.index(current) + 1) % len(self._PAGE_ORDER)
            self.navigate_to(self._PAGE_ORDER[idx])

    def _toggle_visibility(self) -> None:
        """Start button — show Quick Resume overlay or dismiss it."""
        if not self.isVisible():
            self.showFullScreen() if self._config.get("ui.fullscreen", True) else self.showNormal()
            self.activateWindow()
            self.raise_()
            return

        # If Quick Resume is already showing, dismiss it
        if self._quick_resume.is_showing():
            self._quick_resume.dismiss()
            return

        # Show Quick Resume with 5 most recent games
        recent = sorted(
            [a for a in self._registry.get_all() if a.metadata.get("last_played", 0) > 0],
            key=lambda a: a.metadata.get("last_played", 0),
            reverse=True,
        )[:5]
        self._quick_resume.show_overlay(recent)

    def _nav_prev_page(self) -> None:
        """LB — cycle to previous page."""
        if self._vibration:
            try:
                self._vibration.pulse(left=10000, right=10000, duration_ms=40)
            except Exception:
                logger.debug("Vibration pulse failed", exc_info=True)
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
        if settings and hasattr(settings, 'set_scanning'):
            settings.set_scanning(True)

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
        self._apply_favorites_from_config()
        for name in ("home", "library"):
            page = self._page_stack._pages.get(name)
            if page is not None and hasattr(page, "refresh"):
                page.refresh(apps)

        # Update onboarding page if it's showing
        onboarding = self._page_stack._pages.get("onboarding")
        if onboarding is not None and hasattr(onboarding, "update_stores"):
            onboarding.update_stores(apps)

        # Scan-complete feedback
        n_games = sum(1 for a in apps if a.is_game)
        n_apps = len(apps) - n_games
        if n_apps:
            self.show_toast(f"{n_games} games, {n_apps} apps found")
        else:
            self.show_toast(f"{n_games} games found")

        # Restore Scan Now button in settings
        settings = self._page_stack._pages.get("settings")
        if settings and hasattr(settings, 'set_scanning'):
            settings.set_scanning(False)

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
        if detail and hasattr(detail, 'focus_launch_button'):
            detail.focus_launch_button()

    def _on_voice_start(self) -> None:
        logger.debug("Voice start")

        # Vibration feedback
        if self._vibration:
            try:
                self._vibration.pulse(left=12000, right=12000, duration_ms=50)
            except Exception:
                logger.debug("Voice vibration pulse failed", exc_info=True)

        # Show overlay
        if self._voice_overlay:
            self._voice_overlay.show_text("Listening...", is_final=False)

        # Focus search bar and show mic recording state
        current = self._page_stack.current_page_name()
        if current in ("home", "library"):
            page = self._page_stack._pages.get(current)
            if page and hasattr(page, 'focus_search'):
                page.focus_search()
            if page and hasattr(page, 'set_mic_recording'):
                page.set_mic_recording(True)

        # Start actual voice recording
        if self._voice_pipeline is not None and self._voice_ready:
            try:
                self._voice_pipeline.start_recording()
                logger.debug("Voice recording started")
            except Exception:
                logger.warning("Voice recording start failed", exc_info=True)
        elif self._voice_pipeline is not None:
            logger.debug("Voice model still loading, try again in a moment")
        else:
            logger.debug("No voice pipeline available")

    def _on_voice_stop(self) -> None:
        logger.debug("Voice stop")

        # Stop recording — triggers final transcription
        if self._voice_pipeline is not None:
            try:
                self._voice_pipeline.stop_recording()
                logger.debug("Voice recording stopped, transcription queued")
            except Exception:
                logger.warning("Voice recording stop failed", exc_info=True)
        else:
            logger.debug("No voice pipeline to stop")

        # Reset search bar mic state
        current = self._page_stack.current_page_name()
        if current in ("home", "library"):
            page = self._page_stack._pages.get(current)
            if page and hasattr(page, 'set_mic_recording'):
                page.set_mic_recording(False)

        if self._voice_overlay:
            self._voice_overlay.show_text("Processing...", is_final=False)

    def _on_transcription(self, event: TranscriptionEvent) -> None:
        """Called from transcription worker thread — marshal to main thread via signal."""
        logger.debug("TranscriptionEvent: is_final=%s text='%s'", event.is_final, event.text)
        if not event.is_final:
            return
        # Signal is thread-safe — guaranteed to deliver on the main thread
        self._transcription_signal.emit(event.text)

    def _apply_transcription(self, text: str) -> None:
        """Main-thread handler: write transcribed text to the search bar."""
        current = self._page_stack.current_page_name()
        logger.debug("Writing transcription to search bar on page '%s': '%s'", current, text)
        if current in ("home", "library"):
            page = self._page_stack._pages.get(current)
            if page and hasattr(page, 'set_search_text'):
                page.set_search_text(text)
            else:
                logger.debug("No search bar found on page '%s'", current)
        else:
            logger.debug("Not on a searchable page")
        if self._voice_overlay:
            self._voice_overlay.dismiss()

    def show_toast(self, msg: str, icon: str = "success") -> None:
        """Show a floating toast notification."""
        self._toast.show_message(msg, icon=icon)

    # -- onboarding ----------------------------------------------------------

    def _on_onboarding_done(self) -> None:
        """User clicked 'Let's go!' on the onboarding page."""
        self._onboarded = True
        # Persist the onboarded flag so we never show onboarding again.
        # Config is TOML-based (read-only). Use a simple marker file instead.
        try:
            from pixiis.core.paths import cache_dir
            marker = cache_dir() / ".onboarded"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("1", encoding="utf-8")
        except Exception:
            logger.debug("Failed to write onboarding marker", exc_info=True)
        self.navigate_to("home")

    # -- virtual keyboard ----------------------------------------------------

    def _show_virtual_keyboard(self) -> None:
        """Show the on-screen keyboard when a search bar is focused via controller."""
        focus = QApplication.focusWidget()
        if not isinstance(focus, QLineEdit):
            return
        # Don't show if already visible
        if self._virtual_keyboard.isVisible():
            return
        self._virtual_keyboard.set_target(focus)
        # Position below the focused widget
        central = self.centralWidget()
        if central is None:
            return
        pos = focus.mapTo(central, focus.rect().bottomLeft())
        # Ensure keyboard stays within the window
        x = max(0, min(pos.x(), central.width() - self._virtual_keyboard.width()))
        y = pos.y() + 4
        if y + self._virtual_keyboard.height() > central.height():
            # Show above the widget instead
            y = focus.mapTo(central, focus.rect().topLeft()).y() - self._virtual_keyboard.height() - 4
        self._virtual_keyboard.show_at(x, y)

    def _on_keyboard_dismissed(self) -> None:
        """Virtual keyboard was dismissed."""
        pass  # focus is restored by the keyboard itself

    def _on_keyboard_submitted(self, text: str) -> None:
        """Virtual keyboard submitted text."""
        pass  # text is already synced to the target QLineEdit

    # -- favorites -----------------------------------------------------------

    def _on_controller_favorite_toggle(self) -> None:
        """Y button pressed -- toggle favorite on the currently focused tile."""
        from pixiis.ui.widgets.game_tile import GameTile

        widget = QApplication.focusWidget()
        if isinstance(widget, GameTile):
            widget._toggle_favorite()

    def _on_favorite_toggled(self, app: AppEntry, is_favorite: bool) -> None:
        """Handle favorite toggle from any tile (mouse click or controller Y)."""
        # Update the favorites list in config
        favorites: list[str] = list(self._config.get("library.favorites", []))
        if is_favorite and app.id not in favorites:
            favorites.append(app.id)
        elif not is_favorite and app.id in favorites:
            favorites.remove(app.id)

        # Persist to user config
        self._save_favorites(favorites)

        # Save updated metadata to cache
        self._registry._cache.save(self._registry.get_all())

        # Show feedback
        name = getattr(app, "display_name", "game")
        if is_favorite:
            self.show_toast(f"Added {name} to favorites")
        else:
            self.show_toast(f"Removed {name} from favorites")

        # Refresh pages so sort order updates
        self._refresh_pages(self._registry.get_all())

    def _save_favorites(self, favorites: list[str]) -> None:
        """Write the favorites list to the user config TOML file."""
        try:
            import tomli_w
        except ImportError:
            # tomli_w not installed -- fall back silently
            return
        user_path = self._config.ensure_user_config()
        try:
            with open(user_path, "rb") as f:
                import tomllib
                data = tomllib.load(f)
        except Exception:
            data = {}
        data.setdefault("library", {})["favorites"] = favorites
        try:
            with open(user_path, "wb") as f:
                tomli_w.dump(data, f)
        except Exception:
            pass
        # Update in-memory config
        self._config._data.setdefault("library", {})["favorites"] = favorites

    def _apply_favorites_from_config(self) -> None:
        """Sync the favorites list from config into app metadata."""
        favorites = set(self._config.get("library.favorites", []))
        for app in self._registry.get_all():
            app.metadata["favorite"] = app.id in favorites

    def _on_launch_requested(self, app) -> None:
        """Launch the selected game."""
        if self._vibration:
            try:
                self._vibration.rumble_launch()
            except Exception:
                logger.debug("Launch vibration failed", exc_info=True)
        name = getattr(app, "display_name", "game")
        self.show_toast(f"Launching {name}...", icon="info")

        # Update launch button text and disable to prevent double-press
        detail = self._page_stack._pages.get("game_detail")
        if detail and hasattr(detail, 'set_launch_button_enabled'):
            detail.set_launch_button_enabled(False)
            detail.set_launch_button_text("Launching...")

        def _restore_btn() -> None:
            if btn is not None:
                btn.setText("\u25b6  PLAY")
                btn.setEnabled(True)

        try:
            self._registry.launch(app)
            QTimer.singleShot(2000, _restore_btn)

            # Start playtime tracking
            import time
            self._playtime_tracker.start(app.id)
            self._launched_apps[app.id] = app
            app.last_played = time.time()
            # Try to find the PID of the launched process
            self._launched_pids[app.id] = self._find_game_pid(app)
            # Start the monitoring timer if not already running
            if not self._playtime_timer.isActive():
                self._playtime_timer.start()

        except Exception as e:
            self.show_toast(f"Launch failed: {e}", icon="error")
            _restore_btn()  # re-enable immediately on error

    # -- playtime monitoring -------------------------------------------------

    @staticmethod
    def _find_game_pid(app: AppEntry) -> int | None:
        """Try to find a running PID for *app*'s executable."""
        try:
            import psutil
            if app.exe_path:
                exe_name = app.exe_path.name.lower()
                for proc in psutil.process_iter(["name"]):
                    try:
                        if proc.info["name"] and proc.info["name"].lower() == exe_name:
                            return proc.pid
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
        except ImportError:
            pass
        return None

    def _check_running_games(self) -> None:
        """Periodic check: is each launched game still running?"""
        finished: list[str] = []

        for app_id, app in list(self._launched_apps.items()):
            pid = self._launched_pids.get(app_id)
            still_running = False

            # First try: check by PID if we have one
            if pid is not None:
                try:
                    import psutil
                    still_running = psutil.pid_exists(pid)
                except ImportError:
                    still_running = True  # can't check, assume running

            # Second try: find by exe name if no PID or PID gone
            if not still_running and pid is not None:
                new_pid = self._find_game_pid(app)
                if new_pid is not None:
                    self._launched_pids[app_id] = new_pid
                    still_running = True

            # If we never got a PID (no psutil), give up after 2 minutes
            if pid is None:
                import time
                start = self._playtime_tracker._active.get(app_id, 0)
                if start and (time.time() - start) > 120:
                    # Try one more time to find it
                    new_pid = self._find_game_pid(app)
                    if new_pid is not None:
                        self._launched_pids[app_id] = new_pid
                        still_running = True
                    else:
                        # Assume the game closed if we can't find it after 2 min
                        finished.append(app_id)
                        continue
                else:
                    still_running = True  # too early to tell

            if not still_running:
                finished.append(app_id)

        for app_id in finished:
            self._on_game_closed(app_id)

        # Stop the timer if nothing is being tracked
        if not self._launched_apps:
            self._playtime_timer.stop()

    def _on_game_closed(self, app_id: str) -> None:
        """Handle a game session ending: record playtime and save cache."""
        minutes = self._playtime_tracker.stop(app_id)
        app = self._launched_apps.pop(app_id, None)
        self._launched_pids.pop(app_id, None)

        if app is not None and minutes > 0:
            app.playtime_minutes = app.playtime_minutes + minutes
            # Save the updated metadata to cache
            self._registry._cache.save(self._registry.get_all())
            self.show_toast(
                f"Played {app.display_name} for {minutes} min", icon="info"
            )

    # -- cleanup -------------------------------------------------------------

    def cleanup(self) -> None:
        """Release event subscriptions and controller resources.

        Called by the daemon before shutdown, and also from *closeEvent*
        in standalone mode.  Safe to call more than once.
        """
        if self._cleaned_up:
            return
        self._cleaned_up = True
        # Stop playtime tracking and save final stats
        self._playtime_timer.stop()
        remaining = self._playtime_tracker.stop_all()
        for app_id, minutes in remaining.items():
            app = self._launched_apps.pop(app_id, None)
            if app is not None and minutes > 0:
                app.playtime_minutes = app.playtime_minutes + minutes
        if remaining:
            self._registry._cache.save(self._registry.get_all())
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
                logger.debug("Voice pipeline stop failed", exc_info=True)
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
