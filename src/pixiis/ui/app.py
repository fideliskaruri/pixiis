"""Application entry point — creates QApplication, tray icon, and main window."""

from __future__ import annotations

import sys


def launch_ui() -> None:
    """Launch the Pixiis dashboard UI."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QAction, QIcon
        from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
    except ImportError:
        print(
            "PySide6 is required for the Pixiis UI.\n"
            "Install it with:  pip install PySide6"
        )
        sys.exit(1)

    # High-DPI scaling is automatic in Qt6 — no setAttribute needed

    # Allow Ctrl+C in terminal to kill the app
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("Pixiis")
    app.setOrganizationName("Pixiis")

    # -- theme ---------------------------------------------------------------
    try:
        from pixiis.services.theme import ThemeManager

        theme = ThemeManager()
        theme.load_from_config()
        theme.apply(app)
        app._theme_manager = theme  # store for MainWindow access
    except Exception:
        app.setStyleSheet(_FALLBACK_STYLESHEET)

    # -- main window ---------------------------------------------------------
    from pixiis.ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    # -- system tray ---------------------------------------------------------
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(window)
        tray.setToolTip("Pixiis")

        # Create a simple colored icon since we don't have an icon file
        from PySide6.QtGui import QPixmap, QPainter, QColor
        pm = QPixmap(32, 32)
        pm.fill(QColor(0, 0, 0, 0))
        _p = QPainter(pm)
        _p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _p.setBrush(QColor("#e94560"))
        _p.setPen(Qt.PenStyle.NoPen)
        _p.drawRoundedRect(2, 2, 28, 28, 6, 6)
        _p.setPen(QColor("white"))
        _f = _p.font()
        _f.setPixelSize(16)
        _f.setBold(True)
        _p.setFont(_f)
        _p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "P")
        _p.end()
        tray_icon = QIcon(pm)
        tray.setIcon(tray_icon)
        app.setWindowIcon(tray_icon)

        menu = QMenu()
        toggle_action = QAction("Show/Hide Dashboard", menu)
        toggle_action.triggered.connect(
            lambda: window.setVisible(not window.isVisible())
        )
        menu.addAction(toggle_action)
        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(app.quit)
        menu.addAction(quit_action)

        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: window.setVisible(not window.isVisible())
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        tray.show()

    sys.exit(app.exec())


# Hardcoded dark theme used when the ThemeManager service isn't available yet.
_FALLBACK_STYLESHEET = """
QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Segoe UI", "Roboto", sans-serif;
    font-size: 14px;
}
QMainWindow {
    background-color: #1a1a2e;
}
QPushButton {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 8px 16px;
}
QPushButton:hover {
    background-color: #0f3460;
}
QPushButton:pressed {
    background-color: #533483;
}
QPushButton:focus {
    border: 2px solid #e94560;
}
QLabel {
    background-color: transparent;
}
QScrollBar:vertical {
    background: #16213e;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #0f3460;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""
