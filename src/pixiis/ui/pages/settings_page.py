"""Settings page — scrollable settings organized in group-box sections."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
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
