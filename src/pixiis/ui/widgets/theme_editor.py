"""Theme editor widget — color pickers, font, border-radius, live preview."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

if TYPE_CHECKING:
    pass

# Try importing ThemeManager — may not be available yet.
try:
    from pixiis.services.theme import ThemeManager
except ImportError:
    ThemeManager = None  # type: ignore[assignment,misc]


# ── Defaults ────────────────────────────────────────────────────────────────

_DEFAULT_COLORS = {
    "primary": QColor("#1a1a2e"),
    "secondary": QColor("#16213e"),
    "accent": QColor("#e94560"),
    "background": QColor("#0f3460"),
}

_DEFAULT_FONT = "Segoe UI"
_DEFAULT_BORDER_RADIUS = 6


# ── ColorPickerButton ───────────────────────────────────────────────────────


class ColorPickerButton(QPushButton):
    """A 40x40 button that shows the current colour and opens a QColorDialog."""

    color_changed = Signal(QColor)

    def __init__(self, color: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick_color)
        self._apply_style()

    # -- public API -----------------------------------------------------------

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor) -> None:
        if color != self._color:
            self._color = QColor(color)
            self._apply_style()
            self.color_changed.emit(self._color)

    # -- internals ------------------------------------------------------------

    def _pick_color(self) -> None:
        chosen = QColorDialog.getColor(
            self._color, self, "Pick a colour",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if chosen.isValid():
            self.set_color(chosen)

    def _apply_style(self) -> None:
        hex_color = self._color.name()
        self.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {hex_color};"
            f"  border: 2px solid #555;"
            f"  border-radius: 6px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  border: 2px solid #e0e0e0;"
            f"}}"
        )


# ── ThemeEditor ─────────────────────────────────────────────────────────────


class ThemeEditor(QFrame):
    """Embeddable theme-editing panel with live preview.

    Provides colour pickers for primary/secondary/accent/background, a font
    family combo, a border-radius slider, and Reset / Save buttons.
    """

    def __init__(
        self,
        theme_manager: object | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme_manager
        self._building = True  # suppress change signals during init

        self.setObjectName("ThemeEditor")
        self.setStyleSheet(
            "#ThemeEditor { background-color: transparent; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # -- colour pickers ---------------------------------------------------
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._color_buttons: dict[str, ColorPickerButton] = {}
        for key, label in [
            ("primary", "Primary"),
            ("secondary", "Secondary"),
            ("accent", "Accent"),
            ("background", "Background"),
        ]:
            initial = self._read_theme_color(key, _DEFAULT_COLORS[key])
            btn = ColorPickerButton(initial)
            btn.color_changed.connect(lambda _c, _k=key: self._on_color_changed(_k))
            self._color_buttons[key] = btn
            form.addRow(self._make_label(label), btn)

        layout.addLayout(form)

        # -- font family ------------------------------------------------------
        font_form = QFormLayout()
        font_form.setSpacing(10)
        font_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._font_combo = QComboBox()
        families = QFontDatabase.families()
        self._font_combo.addItems(families)
        current_font = self._read_theme_attr("font_family", _DEFAULT_FONT)
        idx = self._font_combo.findText(current_font)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        self._font_combo.currentTextChanged.connect(self._on_font_changed)
        self._style_combo(self._font_combo)
        font_form.addRow(self._make_label("Font"), self._font_combo)

        layout.addLayout(font_form)

        # -- border radius slider ---------------------------------------------
        radius_form = QFormLayout()
        radius_form.setSpacing(10)
        radius_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        radius_row = QHBoxLayout()
        self._radius_slider = QSlider(Qt.Orientation.Horizontal)
        self._radius_slider.setRange(0, 30)
        current_radius = int(self._read_theme_attr("border_radius", _DEFAULT_BORDER_RADIUS))
        self._radius_slider.setValue(current_radius)
        self._radius_slider.setFixedWidth(180)
        self._radius_label = QLabel(f"{current_radius}px")
        self._radius_label.setFixedWidth(40)
        self._radius_label.setStyleSheet("color: #e0e0e0; background: transparent;")
        self._radius_slider.valueChanged.connect(self._on_radius_changed)
        radius_row.addWidget(self._radius_slider)
        radius_row.addWidget(self._radius_label)
        radius_form.addRow(self._make_label("Border Radius"), radius_row)

        layout.addLayout(radius_form)

        # -- action buttons ---------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._reset_btn = QPushButton("Reset to Default")
        self._reset_btn.setStyleSheet(
            "QPushButton { background-color: #16213e; color: #e0e0e0; "
            "border: 1px solid #0f3460; border-radius: 6px; padding: 6px 14px; }"
            "QPushButton:hover { background-color: #0f3460; }"
        )
        self._reset_btn.clicked.connect(self._reset_defaults)
        btn_row.addWidget(self._reset_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.setStyleSheet(
            "QPushButton { background-color: #e94560; color: #ffffff; "
            "border: none; border-radius: 6px; padding: 6px 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #c73652; }"
        )
        self._save_btn.clicked.connect(self._save_theme)
        btn_row.addWidget(self._save_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._building = False

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _make_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #a0a0b0; background: transparent; font-size: 13px;")
        return lbl

    @staticmethod
    def _style_combo(combo: QComboBox) -> None:
        combo.setStyleSheet(
            "QComboBox { background-color: #16213e; color: #e0e0e0; "
            "border: 1px solid #0f3460; border-radius: 4px; padding: 4px 8px; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { background-color: #16213e; color: #e0e0e0; "
            "selection-background-color: #0f3460; }"
        )

    def _read_theme_color(self, key: str, default: QColor) -> QColor:
        if self._theme is not None and hasattr(self._theme, key):
            val = getattr(self._theme, key)
            if isinstance(val, QColor):
                return val
            if isinstance(val, str):
                return QColor(val)
        return QColor(default)

    def _read_theme_attr(self, key: str, default: object) -> object:
        if self._theme is not None and hasattr(self._theme, key):
            return getattr(self._theme, key)
        return default

    # -- change handlers (live preview) ---------------------------------------

    def _on_color_changed(self, key: str) -> None:
        if self._building:
            return
        color = self._color_buttons[key].color()
        if self._theme is not None and hasattr(self._theme, key):
            setattr(self._theme, key, color)
        self._apply_live_preview()

    def _on_font_changed(self, family: str) -> None:
        if self._building:
            return
        if self._theme is not None and hasattr(self._theme, "font_family"):
            self._theme.font_family = family
        self._apply_live_preview()

    def _on_radius_changed(self, value: int) -> None:
        if self._building:
            return
        self._radius_label.setText(f"{value}px")
        if self._theme is not None and hasattr(self._theme, "border_radius"):
            self._theme.border_radius = value
        self._apply_live_preview()

    def _apply_live_preview(self) -> None:
        if self._theme is not None and hasattr(self._theme, "apply"):
            try:
                self._theme.apply()
            except Exception:
                pass

    # -- reset / save ---------------------------------------------------------

    def _reset_defaults(self) -> None:
        self._building = True
        for key, default_color in _DEFAULT_COLORS.items():
            self._color_buttons[key].set_color(default_color)
            if self._theme is not None and hasattr(self._theme, key):
                setattr(self._theme, key, default_color)

        idx = self._font_combo.findText(_DEFAULT_FONT)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        if self._theme is not None and hasattr(self._theme, "font_family"):
            self._theme.font_family = _DEFAULT_FONT

        self._radius_slider.setValue(_DEFAULT_BORDER_RADIUS)
        self._radius_label.setText(f"{_DEFAULT_BORDER_RADIUS}px")
        if self._theme is not None and hasattr(self._theme, "border_radius"):
            self._theme.border_radius = _DEFAULT_BORDER_RADIUS

        self._building = False
        self._apply_live_preview()

    def _save_theme(self) -> None:
        if self._theme is not None and hasattr(self._theme, "save_to_config"):
            try:
                self._theme.save_to_config()
            except Exception:
                pass
