"""Settings page — scrollable settings organized in group-box sections."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
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

# ThemeEditor built alongside this file.
from pixiis.ui.widgets.theme_editor import ThemeEditor

# ThemeManager may not exist yet.
try:
    from pixiis.services.theme import ThemeManager
except ImportError:
    ThemeManager = None  # type: ignore[assignment,misc]

# Version
try:
    from pixiis import __version__
except ImportError:
    __version__ = "0.1.0"


# ── Style helpers ───────────────────────────────────────────────────────────

_GROUP_STYLE = (
    "QGroupBox {"
    "  font-size: 15px;"
    "  font-weight: bold;"
    "  color: #e94560;"
    "  border: 1px solid #0f3460;"
    "  border-radius: 8px;"
    "  margin-top: 14px;"
    "  padding: 18px 12px 12px 12px;"
    "}"
    "QGroupBox::title {"
    "  subcontrol-origin: margin;"
    "  left: 14px;"
    "  padding: 0 6px;"
    "}"
)

_LABEL_STYLE = "color: #a0a0b0; background: transparent; font-size: 13px;"

_COMBO_STYLE = (
    "QComboBox { background-color: #16213e; color: #e0e0e0; "
    "border: 1px solid #0f3460; border-radius: 4px; padding: 4px 8px; }"
    "QComboBox::drop-down { border: none; }"
    "QComboBox QAbstractItemView { background-color: #16213e; color: #e0e0e0; "
    "selection-background-color: #0f3460; }"
)

_CHECKBOX_STYLE = (
    "QCheckBox { color: #e0e0e0; spacing: 6px; background: transparent; }"
    "QCheckBox::indicator { width: 16px; height: 16px; }"
)

_SPINBOX_STYLE = (
    "QSpinBox { background-color: #16213e; color: #e0e0e0; "
    "border: 1px solid #0f3460; border-radius: 4px; padding: 4px 6px; }"
)

_APPLY_STYLE = (
    "QPushButton { background-color: #e94560; color: #ffffff; "
    "border: none; border-radius: 6px; padding: 8px 24px; "
    "font-weight: bold; font-size: 14px; }"
    "QPushButton:hover { background-color: #c73652; }"
)

_SECONDARY_BTN_STYLE = (
    "QPushButton { background-color: #16213e; color: #e0e0e0; "
    "border: 1px solid #0f3460; border-radius: 6px; padding: 6px 14px; }"
    "QPushButton:hover { background-color: #0f3460; }"
)

_CONNECT_BTN_STYLE = (
    "QPushButton { background-color: #9146FF; color: #ffffff; "
    "border: none; border-radius: 6px; padding: 6px 14px; font-weight: bold; }"
    "QPushButton:hover { background-color: #7c3aed; }"
    "QPushButton:disabled { background-color: #4a4a5a; color: #888; }"
)

_LINK_BTN_STYLE = (
    "QPushButton { background: transparent; color: #e94560; "
    "border: none; padding: 2px 0; text-decoration: underline; "
    "font-size: 12px; text-align: left; }"
    "QPushButton:hover { color: #ff6b8a; }"
)

_STATUS_CONNECTED = "color: #4ade80; background: transparent; font-size: 12px;"
_STATUS_DISCONNECTED = "color: #a0a0b0; background: transparent; font-size: 12px;"


def _make_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_LABEL_STYLE)
    return lbl


def _make_slider_row(slider: QSlider, suffix: str = "") -> tuple[QHBoxLayout, QLabel]:
    """Return (layout, value_label) for a slider + value readout."""
    row = QHBoxLayout()
    slider.setFixedWidth(200)
    value_label = QLabel(f"{slider.value()}{suffix}")
    value_label.setFixedWidth(50)
    value_label.setStyleSheet("color: #e0e0e0; background: transparent;")
    slider.valueChanged.connect(lambda v: value_label.setText(f"{v}{suffix}"))
    row.addWidget(slider)
    row.addWidget(value_label)
    row.addStretch()
    return row, value_label


# ── SettingsPage ────────────────────────────────────────────────────────────


class SettingsPage(QScrollArea):
    """Scrollable settings page with grouped sections.

    Parameters
    ----------
    theme_manager : object | None
        An active ``ThemeManager`` instance for the theme-editor section.
    registry : object | None
        An ``AppRegistry`` for triggering library scans.
    """

    def __init__(
        self,
        theme_manager: object | None = None,
        registry: object | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme_manager
        self._registry = registry

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(
            "QScrollArea { background-color: transparent; border: none; }"
        )

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(16, 12, 16, 16)
        self._layout.setSpacing(16)

        cfg = get_config()

        self._build_theme_section()
        self._build_controller_section(cfg)
        self._build_voice_section(cfg)
        self._build_library_section(cfg)
        self._build_services_section(cfg)
        self._build_about_section()

        # -- apply button -----------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet(_APPLY_STYLE)
        apply_btn.clicked.connect(self._apply_settings)
        btn_row.addWidget(apply_btn)
        self._layout.addLayout(btn_row)

        self._layout.addStretch()
        self.setWidget(container)

    # -- Section builders -----------------------------------------------------

    def _build_theme_section(self) -> None:
        group = QGroupBox("Theme")
        group.setStyleSheet(_GROUP_STYLE)
        inner = QVBoxLayout(group)
        inner.setContentsMargins(8, 8, 8, 8)
        self._theme_editor = ThemeEditor(theme_manager=self._theme)
        inner.addWidget(self._theme_editor)
        self._layout.addWidget(group)

    def _build_controller_section(self, cfg: object) -> None:
        group = QGroupBox("Controller")
        group.setStyleSheet(_GROUP_STYLE)
        form = QFormLayout(group)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # vibration enabled
        self._vibration_cb = QCheckBox("Vibration enabled")
        self._vibration_cb.setStyleSheet(_CHECKBOX_STYLE)
        self._vibration_cb.setChecked(bool(cfg.get("controller.vibration_enabled", True)))
        form.addRow(_make_label("Vibration"), self._vibration_cb)

        # deadzone slider (0–50 mapped to 0.0–0.5)
        self._deadzone_slider = QSlider(Qt.Orientation.Horizontal)
        self._deadzone_slider.setRange(0, 50)
        dz_val = int(float(cfg.get("controller.deadzone", 0.15)) * 100)
        self._deadzone_slider.setValue(dz_val)
        dz_row, self._dz_label = _make_slider_row(self._deadzone_slider)
        self._dz_label.setText(f"{dz_val / 100:.2f}")
        self._deadzone_slider.valueChanged.connect(
            lambda v: self._dz_label.setText(f"{v / 100:.2f}")
        )
        form.addRow(_make_label("Deadzone"), dz_row)

        # hold threshold slider (100–500 ms)
        self._hold_slider = QSlider(Qt.Orientation.Horizontal)
        self._hold_slider.setRange(100, 500)
        self._hold_slider.setValue(int(cfg.get("controller.hold_threshold_ms", 200)))
        hold_row, _ = _make_slider_row(self._hold_slider, "ms")
        form.addRow(_make_label("Hold Threshold"), hold_row)

        self._layout.addWidget(group)

    def _build_voice_section(self, cfg: object) -> None:
        group = QGroupBox("Voice")
        group.setStyleSheet(_GROUP_STYLE)
        form = QFormLayout(group)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        whisper_models = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]

        # live model
        self._live_model = QComboBox()
        self._live_model.addItems(whisper_models)
        self._live_model.setCurrentText(str(cfg.get("voice.live_model", "large-v3")))
        self._live_model.setStyleSheet(_COMBO_STYLE)
        form.addRow(_make_label("Live Model"), self._live_model)

        # final model
        self._final_model = QComboBox()
        self._final_model.addItems(whisper_models)
        self._final_model.setCurrentText(str(cfg.get("voice.final_model", "large-v3")))
        self._final_model.setStyleSheet(_COMBO_STYLE)
        form.addRow(_make_label("Final Model"), self._final_model)

        # device
        self._device_combo = QComboBox()
        self._device_combo.addItems(["cuda", "cpu"])
        self._device_combo.setCurrentText(str(cfg.get("voice.device", "cuda")))
        self._device_combo.setStyleSheet(_COMBO_STYLE)
        form.addRow(_make_label("Device"), self._device_combo)

        # energy threshold
        self._energy_slider = QSlider(Qt.Orientation.Horizontal)
        self._energy_slider.setRange(50, 1000)
        self._energy_slider.setValue(int(float(cfg.get("voice.energy_threshold", 300))))
        energy_row, _ = _make_slider_row(self._energy_slider)
        form.addRow(_make_label("Energy Threshold"), energy_row)

        self._layout.addWidget(group)

    def _build_library_section(self, cfg: object) -> None:
        group = QGroupBox("Library")
        group.setStyleSheet(_GROUP_STYLE)
        form = QFormLayout(group)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        enabled_providers: list[str] = cfg.get("library.providers", [])

        # provider checkboxes
        self._provider_cbs: dict[str, QCheckBox] = {}
        providers_row = QHBoxLayout()
        for name in ("steam", "xbox", "startmenu", "manual"):
            cb = QCheckBox(name.capitalize())
            cb.setStyleSheet(_CHECKBOX_STYLE)
            cb.setChecked(name in enabled_providers)
            self._provider_cbs[name] = cb
            providers_row.addWidget(cb)
        providers_row.addStretch()
        form.addRow(_make_label("Providers"), providers_row)

        # scan interval
        self._scan_interval = QSpinBox()
        self._scan_interval.setRange(1, 1440)
        self._scan_interval.setSuffix(" min")
        self._scan_interval.setValue(int(cfg.get("library.scan_interval_minutes", 60)))
        self._scan_interval.setStyleSheet(_SPINBOX_STYLE)
        form.addRow(_make_label("Scan Interval"), self._scan_interval)

        # scan now button
        self._scan_btn = QPushButton("Scan Now")
        self._scan_btn.setStyleSheet(_SECONDARY_BTN_STYLE)
        self._scan_btn.clicked.connect(self._scan_now)
        form.addRow(_make_label(""), self._scan_btn)

        self._layout.addWidget(group)

    def _build_services_section(self, cfg: object) -> None:
        group = QGroupBox("Services / API Keys")
        group.setStyleSheet(_GROUP_STYLE)
        form = QFormLayout(group)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        line_style = (
            "QLineEdit { background-color: #16213e; color: #e0e0e0; "
            "border: 1px solid #0f3460; border-radius: 4px; padding: 4px 8px; }"
        )

        # ── RAWG ────────────────────────────────────────────────────────
        self._rawg_key = QLineEdit(str(cfg.get("services.rawg.api_key", "")))
        self._rawg_key.setStyleSheet(line_style)
        self._rawg_key.setPlaceholderText("RAWG API key")
        form.addRow(_make_label("RAWG API Key"), self._rawg_key)

        rawg_link = QPushButton("Get API Key")
        rawg_link.setStyleSheet(_LINK_BTN_STYLE)
        rawg_link.setCursor(Qt.CursorShape.PointingHandCursor)
        rawg_link.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://rawg.io/apidocs"))
        )
        form.addRow(_make_label(""), rawg_link)

        # ── YouTube ─────────────────────────────────────────────────────
        self._youtube_key = QLineEdit(str(cfg.get("services.youtube.api_key", "")))
        self._youtube_key.setStyleSheet(line_style)
        self._youtube_key.setPlaceholderText("YouTube API key")
        form.addRow(_make_label("YouTube API Key"), self._youtube_key)

        yt_link = QPushButton("Get API Key (Google Cloud Console)")
        yt_link.setStyleSheet(_LINK_BTN_STYLE)
        yt_link.setCursor(Qt.CursorShape.PointingHandCursor)
        yt_link.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://console.cloud.google.com/apis/credentials")
            )
        )
        form.addRow(_make_label(""), yt_link)

        # ── Twitch ──────────────────────────────────────────────────────
        self._twitch_id = QLineEdit(str(cfg.get("services.twitch.client_id", "")))
        self._twitch_id.setStyleSheet(line_style)
        self._twitch_id.setPlaceholderText("Twitch Client ID")
        form.addRow(_make_label("Twitch Client ID"), self._twitch_id)

        self._twitch_secret = QLineEdit(str(cfg.get("services.twitch.client_secret", "")))
        self._twitch_secret.setStyleSheet(line_style)
        self._twitch_secret.setPlaceholderText("Twitch Client Secret (optional with OAuth)")
        self._twitch_secret.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(_make_label("Twitch Client Secret"), self._twitch_secret)

        # Connect button + status
        twitch_row = QHBoxLayout()
        self._twitch_connect_btn = QPushButton("Connect with Twitch")
        self._twitch_connect_btn.setStyleSheet(_CONNECT_BTN_STYLE)
        self._twitch_connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._twitch_connect_btn.clicked.connect(self._connect_twitch)
        twitch_row.addWidget(self._twitch_connect_btn)

        has_token = bool(cfg.get("services.twitch.access_token", ""))
        self._twitch_status = QLabel("Connected" if has_token else "Not connected")
        self._twitch_status.setStyleSheet(
            _STATUS_CONNECTED if has_token else _STATUS_DISCONNECTED
        )
        twitch_row.addWidget(self._twitch_status)
        twitch_row.addStretch()
        form.addRow(_make_label(""), twitch_row)

        # Hidden field to hold the OAuth access token
        self._twitch_access_token = cfg.get("services.twitch.access_token", "")

        # Timer / flow state (created on demand)
        self._oauth_flow = None
        self._oauth_timer: QTimer | None = None

        self._layout.addWidget(group)

    def _build_about_section(self) -> None:
        group = QGroupBox("About")
        group.setStyleSheet(_GROUP_STYLE)
        form = QFormLayout(group)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        version_label = QLabel(f"Pixiis v{__version__}")
        version_label.setStyleSheet(
            "color: #e0e0e0; font-size: 14px; font-weight: bold; background: transparent;"
        )
        form.addRow(_make_label("Version"), version_label)

        link_label = QLabel("github.com/pixiis")
        link_label.setStyleSheet(
            "color: #e94560; font-size: 13px; background: transparent;"
        )
        form.addRow(_make_label("Project"), link_label)

        self._layout.addWidget(group)

    # -- Twitch OAuth ---------------------------------------------------------

    def _connect_twitch(self) -> None:
        """Start the Twitch OAuth implicit-grant flow in the browser."""
        client_id = self._twitch_id.text().strip()
        if not client_id:
            self._twitch_status.setText("Enter your Twitch Client ID first")
            self._twitch_status.setStyleSheet(
                "color: #f87171; background: transparent; font-size: 12px;"
            )
            return

        from pixiis.services.oauth import OAuthFlow
        from pixiis.services.twitch import TwitchClient

        self._twitch_connect_btn.setEnabled(False)
        self._twitch_connect_btn.setText("Waiting for browser...")
        self._twitch_status.setText("Check your browser")
        self._twitch_status.setStyleSheet(_STATUS_DISCONNECTED)

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
            # Got a result — stop polling
            if self._oauth_timer is not None:
                self._oauth_timer.stop()
                self._oauth_timer = None

            token = result.get("access_token", "")
            if token:
                self._twitch_access_token = token
                self._twitch_status.setText("Connected")
                self._twitch_status.setStyleSheet(_STATUS_CONNECTED)
            else:
                self._twitch_status.setText("Failed — no token received")
                self._twitch_status.setStyleSheet(
                    "color: #f87171; background: transparent; font-size: 12px;"
                )

            self._twitch_connect_btn.setEnabled(True)
            self._twitch_connect_btn.setText("Connect with Twitch")
            self._oauth_flow = None

    # -- Actions --------------------------------------------------------------

    def _apply_settings(self) -> None:
        """Write current control values back to the user config file."""
        from pixiis.core.paths import config_file

        cfg = get_config()
        user_path = cfg.ensure_user_config()

        # Build updated values
        updates: dict[str, Any] = {}

        # Controller
        updates["controller.vibration_enabled"] = self._vibration_cb.isChecked()
        updates["controller.deadzone"] = self._deadzone_slider.value() / 100.0
        updates["controller.hold_threshold_ms"] = self._hold_slider.value()

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

        # Read existing TOML, patch, and write back
        self._write_config(user_path, updates)

        # Reload config singleton
        cfg.load()

    @staticmethod
    def _write_config(path: Path, updates: dict[str, Any]) -> None:
        """Read the TOML file, apply dotted-key updates, and write back.

        Uses tomlkit if available (preserves comments/formatting), otherwise
        falls back to a simple re-serialization with tomli_w / manual approach.
        """
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
            # Fallback: load, patch raw dict, write with tomli_w
            import sys as _sys

            if _sys.version_info >= (3, 11):
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
                # Last resort: manual TOML (flat sections only)
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
                items = ", ".join(f'"{v}"' if isinstance(v, str) else str(v) for v in val)
                lines.append(f"{key} = [{items}]")
            else:
                lines.append(f'{key} = "{val}"')

    def _scan_now(self) -> None:
        """Trigger an immediate library scan."""
        if self._registry is not None and hasattr(self._registry, "scan_all"):
            self._registry.scan_all()
