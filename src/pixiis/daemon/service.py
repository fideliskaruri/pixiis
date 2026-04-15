"""Pixiis background daemon — owns the event loop, tray, and controller.

The daemon is the long-lived QApplication process.  The UI window is
created on demand and hidden (not destroyed) when the user closes it.
Controller polling and voice triggers remain active at all times.
"""

from __future__ import annotations

import signal
import sys

from pixiis.daemon.ipc import DaemonIPC


class DaemonService:
    """Persistent background service that owns the Qt event loop.

    Lifecycle::

        svc = DaemonService()
        sys.exit(svc.start(show_ui=True))

    Only one daemon may run at a time (enforced via :class:`DaemonIPC`).
    If another instance is already running, ``start()`` sends it the
    *show* command and returns immediately.
    """

    def __init__(self) -> None:
        self._app = None
        self._tray = None
        self._tray_menu = None  # prevent GC of QMenu
        self._window = None
        self._registry = None
        self._controller_bridge = None
        self._ipc = DaemonIPC()

    # ── Public entry point ─────────────────────────────────────────────

    def start(self, *, show_ui: bool = False) -> int:
        """Acquire the instance lock and enter the Qt event loop.

        Returns the process exit code.
        """
        if not self._ipc.acquire(self._on_ipc_command):
            # Another daemon is already running
            if show_ui:
                DaemonIPC.send_command("show")
            return 0

        try:
            return self._run(show_ui=show_ui)
        finally:
            self._ipc.release()

    # ── Core setup & event loop ────────────────────────────────────────

    def _run(self, *, show_ui: bool) -> int:
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            print(
                "PySide6 is required for the Pixiis daemon.\n"
                "Install it with:  pip install PySide6"
            )
            return 1

        # Allow Ctrl+C in terminal to kill the daemon
        signal.signal(signal.SIGINT, signal.SIG_DFL)

        self._app = QApplication(sys.argv)
        self._app.setApplicationName("Pixiis")
        self._app.setOrganizationName("Pixiis")
        self._app.setQuitOnLastWindowClosed(False)  # keep running after window close

        # -- theme ---------------------------------------------------------------
        try:
            from pixiis.services.theme import ThemeManager

            theme = ThemeManager()
            theme.load_from_config()
            theme.apply(self._app)
            self._app._theme_manager = theme
        except Exception:
            from pixiis.ui.app import _FALLBACK_STYLESHEET

            self._app.setStyleSheet(_FALLBACK_STYLESHEET)

        # -- library registry ----------------------------------------------------
        from pixiis.core import get_config
        from pixiis.library.registry import AppRegistry

        self._registry = AppRegistry(get_config())

        # -- controller (always-on, even without a window) -----------------------
        from pixiis.ui.controller_bridge import ControllerBridge

        self._controller_bridge = ControllerBridge()

        # -- system tray ---------------------------------------------------------
        self._create_tray()

        # -- optionally show the dashboard ---------------------------------------
        if show_ui:
            self._show_ui()

        return self._app.exec()

    # ── System tray ────────────────────────────────────────────────────

    def _create_tray(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        # Build the red "P" icon used everywhere in Pixiis
        pm = QPixmap(32, 32)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#e94560"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(2, 2, 28, 28, 6, 6)
        p.setPen(QColor("white"))
        f = p.font()
        f.setPixelSize(16)
        f.setBold(True)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "P")
        p.end()

        icon = QIcon(pm)
        self._app.setWindowIcon(icon)

        self._tray = QSystemTrayIcon()
        self._tray.setIcon(icon)
        self._tray.setToolTip("Pixiis")

        # Context menu
        menu = QMenu()

        open_action = QAction("Open Dashboard", menu)
        open_action.triggered.connect(self._show_ui)
        menu.addAction(open_action)

        scan_action = QAction("Scan Library", menu)
        scan_action.triggered.connect(self._rescan_library)
        menu.addAction(scan_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray_menu = menu  # prevent GC

        # Double-click / single-click toggles the dashboard
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon

        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self._window is not None and self._window.isVisible():
                self._window.hide()
            else:
                self._show_ui()

    # ── Window lifecycle ───────────────────────────────────────────────

    def _show_ui(self) -> None:
        """Create the dashboard window if needed and bring it to front."""
        if self._window is not None:
            self._window.show()
            self._window.raise_()
            self._window.activateWindow()
            return

        from pixiis.ui.main_window import MainWindow

        self._window = MainWindow(
            registry=self._registry,
            controller_bridge=self._controller_bridge,
        )
        self._window.destroyed.connect(self._on_window_destroyed)
        self._window.show()

    def _on_window_destroyed(self) -> None:
        """Safety net — clear our reference if Qt destroys the window."""
        self._window = None

    # ── Library rescan ─────────────────────────────────────────────────

    def _rescan_library(self) -> None:
        if self._registry is not None:
            import threading

            threading.Thread(
                target=self._registry.scan_all,
                name="rescan",
                daemon=True,
            ).start()

    # ── IPC command handler (called from IPC thread) ───────────────────

    def _on_ipc_command(self, cmd: str) -> str:
        """Handle commands arriving from other ``pixiis`` processes.

        Commands arrive on the IPC thread so we marshal to the main
        thread via ``QTimer.singleShot(0, …)``.
        """
        from PySide6.QtCore import QTimer

        cmd = cmd.lower()
        if cmd == "show":
            QTimer.singleShot(0, self._show_ui)
            return "ok"
        if cmd == "scan":
            QTimer.singleShot(0, self._rescan_library)
            return "ok"
        if cmd == "quit":
            QTimer.singleShot(0, self._quit)
            return "ok"
        return "unknown"

    # ── Shutdown ───────────────────────────────────────────────────────

    def _quit(self) -> None:
        """Clean shutdown of every subsystem."""
        if self._controller_bridge is not None:
            self._controller_bridge.shutdown()

        if self._window is not None:
            self._window.cleanup()
            self._window = None

        if self._tray is not None:
            self._tray.hide()

        self._ipc.release()

        if self._app is not None:
            self._app.quit()
