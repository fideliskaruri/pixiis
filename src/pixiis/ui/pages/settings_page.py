"""Settings page — clean, scrollable settings organized in framed sections."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pixiis.core import get_config
from pixiis.ui.widgets.theme_editor import ThemeEditor

try:
    from pixiis.services.theme import ThemeManager
except ImportError:
    ThemeManager = None  # type: ignore[assignment,misc]

try:
    from pixiis import __version__
except ImportError:
    __version__ = "0.1.0"


# ── Design tokens (matches DESIGN_SPEC.md) ────────────────────────────────

_TEXT_SECONDARY = "#8a8698"
_TEXT_MUTED = "#5c586a"
_SUCCESS = "#4ade80"
_ERROR = "#f87171"


# ── Widget factories ──────────────────────────────────────────────────────


def _section_title(text: str) -> QLabel:
    """H3-level section title: 16px SemiBold, inherits text_primary from QSS."""
    lbl = QLabel(text)
    font = QFont()
    font.setPixelSize(20)
    font.setWeight(QFont.Weight.DemiBold)
    lbl.setFont(font)
    return lbl


def _form_label(text: str) -> QLabel:
    """Secondary-color form label."""
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {_TEXT_SECONDARY};")
    return lbl


def _value_label(text: str) -> QLabel:
    """Prominent slider value readout."""
    lbl = QLabel(text)
    font = QFont()
    font.setPixelSize(14)
    font.setWeight(QFont.Weight.DemiBold)
    lbl.setFont(font)
    lbl.setMinimumWidth(50)
    return lbl


def _slider(min_val: int, max_val: int, value: int) -> QSlider:
    """Horizontal slider with StrongFocus and sensible minimum width."""
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(min_val, max_val)
    s.setValue(value)
    s.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    s.setMinimumWidth(160)
    return s


# ── SettingsPage ──────────────────────────────────────────────────────────


class SettingsPage(QScrollArea):
    """Scrollable settings page with framed sections.

    Parameters
    ----------
    theme_manager : object | None
        An active ``ThemeManager`` instance for the theme-editor section.
    registry : object | None
        An ``AppRegistry`` for triggering library scans.
    """

    settings_saved = Signal()
    scan_requested = Signal()

    def __init__(
        self,
        theme_manager: object | None = None,
        registry: object | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme_manager
        self._registry = registry

        self.setObjectName("SettingsPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container.setObjectName("SettingsContainer")
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(32, 24, 32, 16)
        self._layout.setSpacing(24)

        # Page title (H1: 24px Bold)
        title = QLabel("Settings")
        title_font = QFont()
        title_font.setPixelSize(24)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)
        self._layout.addWidget(title)

        cfg = get_config()

        self._build_theme_section()
        self._build_controller_section(cfg)
        self._build_voice_section(cfg)
        self._build_library_section(cfg)
        self._build_services_section(cfg)
        self._build_system_section(cfg)

        # Apply button — right-aligned, accent style via objectName
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setObjectName("accentButton")
        self._apply_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._apply_btn.setMinimumWidth(120)
        self._apply_btn.clicked.connect(self._apply_settings)
        btn_row.addWidget(self._apply_btn)
        self._layout.addLayout(btn_row)

        self._layout.addStretch()
        self.setWidget(container)

    # ── Section helper ───────────────────────────────────────────────────

    def _add_section(self, title: str) -> QVBoxLayout:
        """Add a titled QFrame section and return its inner layout.

        A wrapper QWidget keeps the title label and frame together with tight
        8px spacing, while the main layout's 24px gap separates sections.
        """
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(8)

        wrapper_layout.addWidget(_section_title(title))

        frame = QFrame()
        frame.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(16, 16, 16, 16)
        inner.setSpacing(16)
        wrapper_layout.addWidget(frame)

        self._layout.addWidget(wrapper)
        return inner

    # ── Theme ────────────────────────────────────────────────────────────

    def _build_theme_section(self) -> None:
        inner = self._add_section("Theme")
        self._theme_editor = ThemeEditor(theme_manager=self._theme)
        self._theme_editor.setStyleSheet(
            "#ThemeEditor { background: transparent; border: none; }"
        )
        inner.addWidget(self._theme_editor)

    # ── Controller ───────────────────────────────────────────────────────

    def _build_controller_section(self, cfg: object) -> None:
        inner = self._add_section("Controller")

        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setColumnMinimumWidth(0, 100)
        grid.setColumnMinimumWidth(2, 100)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        # Row 0: Vibration | Voice Trigger
        grid.addWidget(
            _form_label("Vibration"), 0, 0, Qt.AlignmentFlag.AlignRight
        )
        self._vibration_cb = QCheckBox("Enabled")
        self._vibration_cb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._vibration_cb.setChecked(
            bool(cfg.get("controller.vibration_enabled", True))
        )
        grid.addWidget(self._vibration_cb, 0, 1)

        grid.addWidget(
            _form_label("Voice Trigger"), 0, 2, Qt.AlignmentFlag.AlignRight
        )
        self._voice_trigger = QComboBox()
        self._voice_trigger.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for label, value in [
            ("Right Trigger", "rt"),
            ("Left Trigger", "lt"),
            ("Hold Y", "hold_y"),
            ("Hold X", "hold_x"),
        ]:
            self._voice_trigger.addItem(label, value)
        idx = self._voice_trigger.findData(
            str(cfg.get("controller.voice_trigger", "rt"))
        )
        if idx >= 0:
            self._voice_trigger.setCurrentIndex(idx)
        grid.addWidget(self._voice_trigger, 0, 3)

        # Row 1: Deadzone slider | Hold slider
        grid.addWidget(
            _form_label("Deadzone"), 1, 0, Qt.AlignmentFlag.AlignRight
        )
        dz_val = int(float(cfg.get("controller.deadzone", 0.15)) * 100)
        self._deadzone_slider = _slider(0, 50, dz_val)
        self._deadzone_slider.setSingleStep(5)
        self._dz_label = _value_label(f"{dz_val / 100:.2f}")
        self._deadzone_slider.valueChanged.connect(
            lambda v: self._dz_label.setText(f"{v / 100:.2f}")
        )
        dz_row = QHBoxLayout()
        dz_row.addWidget(self._deadzone_slider)
        dz_row.addWidget(self._dz_label)
        grid.addLayout(dz_row, 1, 1)

        grid.addWidget(
            _form_label("Hold"), 1, 2, Qt.AlignmentFlag.AlignRight
        )
        hold_val = int(cfg.get("controller.hold_threshold_ms", 200))
        self._hold_slider = _slider(100, 500, hold_val)
        self._hold_slider.setSingleStep(10)
        self._hold_label = _value_label(f"{hold_val}ms")
        self._hold_slider.valueChanged.connect(
            lambda v: self._hold_label.setText(f"{v}ms")
        )
        hold_row = QHBoxLayout()
        hold_row.addWidget(self._hold_slider)
        hold_row.addWidget(self._hold_label)
        grid.addLayout(hold_row, 1, 3)

        inner.addLayout(grid)

    # ── Voice ────────────────────────────────────────────────────────────

    def _build_voice_section(self, cfg: object) -> None:
        inner = self._add_section("Voice")

        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setColumnMinimumWidth(0, 100)
        grid.setColumnMinimumWidth(2, 100)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        whisper_models = [
            "tiny", "base", "small", "medium", "large-v2", "large-v3",
        ]

        # Row 0: Live Model | Final Model
        grid.addWidget(
            _form_label("Live Model"), 0, 0, Qt.AlignmentFlag.AlignRight
        )
        self._live_model = QComboBox()
        self._live_model.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._live_model.addItems(whisper_models)
        self._live_model.setCurrentText(
            str(cfg.get("voice.live_model", "large-v3"))
        )
        grid.addWidget(self._live_model, 0, 1)

        grid.addWidget(
            _form_label("Final"), 0, 2, Qt.AlignmentFlag.AlignRight
        )
        self._final_model = QComboBox()
        self._final_model.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._final_model.addItems(whisper_models)
        self._final_model.setCurrentText(
            str(cfg.get("voice.final_model", "large-v3"))
        )
        grid.addWidget(self._final_model, 0, 3)

        # Row 1: Device | Energy slider
        grid.addWidget(
            _form_label("Device"), 1, 0, Qt.AlignmentFlag.AlignRight
        )
        self._device_combo = QComboBox()
        self._device_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._device_combo.addItems(["cuda", "cpu"])
        self._device_combo.setCurrentText(
            str(cfg.get("voice.device", "cuda"))
        )
        grid.addWidget(self._device_combo, 1, 1)

        grid.addWidget(
            _form_label("Energy"), 1, 2, Qt.AlignmentFlag.AlignRight
        )
        energy_val = int(float(cfg.get("voice.energy_threshold", 300)))
        self._energy_slider = _slider(50, 1000, energy_val)
        self._energy_slider.setSingleStep(10)
        self._energy_label = _value_label(str(energy_val))
        self._energy_slider.valueChanged.connect(
            lambda v: self._energy_label.setText(str(v))
        )
        energy_row = QHBoxLayout()
        energy_row.addWidget(self._energy_slider)
        energy_row.addWidget(self._energy_label)
        grid.addLayout(energy_row, 1, 3)

        inner.addLayout(grid)

    # ── Library ──────────────────────────────────────────────────────────

    def _build_library_section(self, cfg: object) -> None:
        inner = self._add_section("Library")

        enabled_providers: list[str] = cfg.get("library.providers", [])

        # Providers row
        prov_row = QHBoxLayout()
        prov_row.addWidget(_form_label("Providers"))
        prov_row.addSpacing(8)
        self._provider_cbs: dict[str, QCheckBox] = {}
        for name in ("steam", "xbox", "epic", "gog", "ea"):
            cb = QCheckBox(name.capitalize())
            cb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            cb.setChecked(name in enabled_providers)
            self._provider_cbs[name] = cb
            prov_row.addWidget(cb)
        prov_row.addStretch()
        inner.addLayout(prov_row)

        # Scan interval + Scan Now
        scan_row = QHBoxLayout()
        scan_row.addWidget(_form_label("Scan interval"))
        scan_row.addSpacing(8)
        self._scan_interval = QSpinBox()
        self._scan_interval.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._scan_interval.setRange(1, 1440)
        self._scan_interval.setSuffix(" min")
        self._scan_interval.setValue(
            int(cfg.get("library.scan_interval_minutes", 60))
        )
        scan_row.addWidget(self._scan_interval)
        scan_row.addSpacing(16)
        self._scan_btn = QPushButton("Scan Now")
        self._scan_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._scan_btn.clicked.connect(self._scan_now)
        scan_row.addWidget(self._scan_btn)
        scan_row.addStretch()
        inner.addLayout(scan_row)

    # ── Services ─────────────────────────────────────────────────────────

    def _build_services_section(self, cfg: object) -> None:
        inner = self._add_section("Services")

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnMinimumWidth(0, 100)
        grid.setColumnStretch(1, 1)

        row = 0

        # RAWG
        grid.addWidget(
            _form_label("RAWG"), row, 0, Qt.AlignmentFlag.AlignRight
        )
        self._rawg_key = QLineEdit(str(cfg.get("services.rawg.api_key", "")))
        self._rawg_key.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._rawg_key.setPlaceholderText("RAWG API key")
        self._rawg_key.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self._rawg_key, row, 1)
        rawg_link = QPushButton("Get Key")
        rawg_link.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        rawg_link.setCursor(Qt.CursorShape.PointingHandCursor)
        rawg_link.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://rawg.io/apidocs"))
        )
        grid.addWidget(rawg_link, row, 2)
        row += 1

        # YouTube
        grid.addWidget(
            _form_label("YouTube"), row, 0, Qt.AlignmentFlag.AlignRight
        )
        self._youtube_key = QLineEdit(
            str(cfg.get("services.youtube.api_key", ""))
        )
        self._youtube_key.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._youtube_key.setPlaceholderText("YouTube API key")
        self._youtube_key.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self._youtube_key, row, 1)
        yt_link = QPushButton("Get Key")
        yt_link.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        yt_link.setCursor(Qt.CursorShape.PointingHandCursor)
        yt_link.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://console.cloud.google.com/apis/credentials")
            )
        )
        grid.addWidget(yt_link, row, 2)
        row += 1

        # Twitch Client ID
        grid.addWidget(
            _form_label("Twitch ID"), row, 0, Qt.AlignmentFlag.AlignRight
        )
        self._twitch_id = QLineEdit(
            str(cfg.get("services.twitch.client_id", ""))
        )
        self._twitch_id.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._twitch_id.setPlaceholderText("Twitch Client ID")
        grid.addWidget(self._twitch_id, row, 1)
        row += 1

        # Twitch Client Secret + Connect
        grid.addWidget(
            _form_label("Twitch Secret"), row, 0, Qt.AlignmentFlag.AlignRight
        )
        self._twitch_secret = QLineEdit(
            str(cfg.get("services.twitch.client_secret", ""))
        )
        self._twitch_secret.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._twitch_secret.setPlaceholderText("Twitch Client Secret")
        self._twitch_secret.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self._twitch_secret, row, 1)

        connect_col = QHBoxLayout()
        self._twitch_connect_btn = QPushButton("Connect")
        self._twitch_connect_btn.setObjectName("accentButton")
        self._twitch_connect_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._twitch_connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._twitch_connect_btn.clicked.connect(self._connect_twitch)
        connect_col.addWidget(self._twitch_connect_btn)

        has_token = bool(cfg.get("services.twitch.access_token", ""))
        self._twitch_status = QLabel(
            "Connected" if has_token else "Not connected"
        )
        self._twitch_status.setStyleSheet(
            f"color: {_SUCCESS if has_token else _TEXT_SECONDARY};"
        )
        connect_col.addWidget(self._twitch_status)
        connect_col.addStretch()
        grid.addLayout(connect_col, row, 2)

        # OAuth state
        self._twitch_access_token = cfg.get("services.twitch.access_token", "")
        self._oauth_flow = None
        self._oauth_timer: QTimer | None = None

        inner.addLayout(grid)

    # ── System ───────────────────────────────────────────────────────────

    def _build_system_section(self, cfg: object) -> None:
        inner = self._add_section("System")

        row = QHBoxLayout()
        row.addWidget(_form_label("Start with Windows"))
        row.addSpacing(8)
        self._autostart_cb = QCheckBox()
        self._autostart_cb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        try:
            from pixiis.daemon.autostart import is_autostart_enabled

            self._autostart_cb.setChecked(is_autostart_enabled())
        except Exception:
            self._autostart_cb.setChecked(
                bool(cfg.get("daemon.autostart", False))
            )
        row.addWidget(self._autostart_cb)
        row.addStretch()
        inner.addLayout(row)

    # ── Twitch OAuth ─────────────────────────────────────────────────────

    def _connect_twitch(self) -> None:
        """Start the Twitch OAuth implicit-grant flow in the browser."""
        client_id = self._twitch_id.text().strip()
        if not client_id:
            self._twitch_status.setText("Enter Client ID first")
            self._twitch_status.setStyleSheet(f"color: {_ERROR};")
            return

        from pixiis.services.oauth import OAuthFlow
        from pixiis.services.twitch import TwitchClient

        self._twitch_connect_btn.setEnabled(False)
        self._twitch_connect_btn.setText("Waiting\u2026")
        self._twitch_status.setText("Check your browser")
        self._twitch_status.setStyleSheet(f"color: {_TEXT_SECONDARY};")

        flow = OAuthFlow()
        redirect_uri = f"http://localhost:{flow.port}/callback"
        auth_url = TwitchClient.authorize_url(client_id, redirect_uri)
        flow.start(auth_url)

        self._oauth_flow = flow
        self._oauth_timer = QTimer(self)
        self._oauth_timer.setInterval(500)
        self._oauth_timer.timeout.connect(self._check_twitch_oauth)
        self._oauth_timer.start()

    def _check_twitch_oauth(self) -> None:
        """Poll the OAuth flow for a result (non-blocking)."""
        if self._oauth_flow is None:
            return

        result = self._oauth_flow.get_result(timeout=0)
        if result is not None:
            if self._oauth_timer is not None:
                self._oauth_timer.stop()
                self._oauth_timer = None

            token = result.get("access_token", "")
            if token:
                self._twitch_access_token = token
                self._twitch_status.setText("Connected")
                self._twitch_status.setStyleSheet(f"color: {_SUCCESS};")
            else:
                self._twitch_status.setText("Failed \u2014 no token")
                self._twitch_status.setStyleSheet(f"color: {_ERROR};")

            self._twitch_connect_btn.setEnabled(True)
            self._twitch_connect_btn.setText("Connect")
            self._oauth_flow = None

    # ── Apply settings ───────────────────────────────────────────────────

    def _apply_settings(self) -> None:
        """Write current control values back to the user config file."""
        cfg = get_config()
        user_path = cfg.ensure_user_config()

        updates: dict[str, Any] = {}

        # Controller
        updates["controller.vibration_enabled"] = self._vibration_cb.isChecked()
        updates["controller.deadzone"] = self._deadzone_slider.value() / 100.0
        updates["controller.hold_threshold_ms"] = self._hold_slider.value()
        updates["controller.voice_trigger"] = self._voice_trigger.currentData()

        # System
        autostart_wanted = self._autostart_cb.isChecked()
        updates["daemon.autostart"] = autostart_wanted
        try:
            from pixiis.daemon.autostart import enable_autostart, disable_autostart

            if autostart_wanted:
                enable_autostart()
            else:
                disable_autostart()
        except Exception:
            pass

        # Voice
        updates["voice.live_model"] = self._live_model.currentText()
        updates["voice.final_model"] = self._final_model.currentText()
        updates["voice.device"] = self._device_combo.currentText()
        updates["voice.energy_threshold"] = float(self._energy_slider.value())

        # Library
        providers = [
            name for name, cb in self._provider_cbs.items() if cb.isChecked()
        ]
        updates["library.providers"] = providers
        updates["library.scan_interval_minutes"] = self._scan_interval.value()

        # Services
        twitch_cfg: dict[str, str] = {
            "client_id": self._twitch_id.text().strip(),
            "client_secret": self._twitch_secret.text().strip(),
        }
        if self._twitch_access_token:
            twitch_cfg["access_token"] = self._twitch_access_token

        updates["services"] = {
            "rawg": {"api_key": self._rawg_key.text().strip()},
            "youtube": {"api_key": self._youtube_key.text().strip()},
            "twitch": twitch_cfg,
        }

        self._write_config(user_path, updates)
        cfg.load()

        # Brief visual feedback
        self._apply_btn.setText("Saved \u2713")
        QTimer.singleShot(2000, self._restore_apply_btn)

        self.settings_saved.emit()

    def _restore_apply_btn(self) -> None:
        """Restore the Apply button text after save feedback."""
        self._apply_btn.setText("Apply")

    # ── Config persistence ───────────────────────────────────────────────

    @staticmethod
    def _write_config(path: Path, updates: dict[str, Any]) -> None:
        """Read the TOML file, apply dotted-key updates, and write back."""
        try:
            import tomlkit

            text = path.read_text(encoding="utf-8") if path.exists() else ""
            doc = tomlkit.parse(text)

            for dotted, value in updates.items():
                keys = dotted.split(".")
                node = doc
                for key in keys[:-1]:
                    if key not in node:
                        node[key] = tomlkit.table()
                    node = node[key]
                node[keys[-1]] = value

            path.write_text(tomlkit.dumps(doc), encoding="utf-8")
        except ImportError:
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                try:
                    import tomllib
                except ImportError:
                    import tomli as tomllib  # type: ignore[no-redef]

            data: dict[str, Any] = {}
            if path.exists():
                with open(path, "rb") as f:
                    data = tomllib.load(f)

            for dotted, value in updates.items():
                keys = dotted.split(".")
                node = data
                for key in keys[:-1]:
                    node = node.setdefault(key, {})
                node[keys[-1]] = value

            try:
                import tomli_w

                with open(path, "wb") as f:
                    tomli_w.dump(data, f)
            except ImportError:
                lines: list[str] = []
                SettingsPage._dict_to_toml(data, lines, [])
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _dict_to_toml(
        d: dict[str, Any], lines: list[str], prefix: list[str]
    ) -> None:
        """Minimal recursive TOML serializer (flat tables only)."""
        for key, val in d.items():
            if isinstance(val, dict):
                section = prefix + [key]
                lines.append(f"[{'.'.join(section)}]")
                SettingsPage._dict_to_toml(val, lines, section)
            elif isinstance(val, bool):
                lines.append(f"{key} = {'true' if val else 'false'}")
            elif isinstance(val, (int, float)):
                lines.append(f"{key} = {val}")
            elif isinstance(val, list):
                items = ", ".join(
                    f'"{v}"' if isinstance(v, str) else str(v) for v in val
                )
                lines.append(f"{key} = [{items}]")
            else:
                lines.append(f'{key} = "{val}"')

    def _scan_now(self) -> None:
        """Trigger an immediate library scan."""
        self.scan_requested.emit()
