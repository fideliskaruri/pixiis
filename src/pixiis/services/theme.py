"""Theme management and QSS generation for Pixiis UI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from pixiis.core import get_config
from pixiis.core.paths import config_file


def _resources_dir() -> Path:
    """Return the bundled resources/ directory."""
    return Path(__file__).parent.parent.parent.parent / "resources"


# ── Color helpers ───────────────────────────────────────────────────────────


def _clamp(value: int) -> int:
    return max(0, min(255, value))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{_clamp(r):02x}{_clamp(g):02x}{_clamp(b):02x}"


def lighter(hex_color: str, amount: int = 30) -> str:
    """Return a lighter variant of *hex_color*."""
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(r + amount, g + amount, b + amount)


def darker(hex_color: str, amount: int = 30) -> str:
    """Return a darker variant of *hex_color*."""
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(r - amount, g - amount, b - amount)


# ── Defaults ────────────────────────────────────────────────────────────────

_DEFAULTS = {
    "background": "#0b0a10",
    "primary": "#13121a",        # surface
    "secondary": "#1c1a24",      # surface_elevated
    "accent": "#e94560",
    "text_color": "#f0eef5",     # text_primary
    "text_secondary": "#8a8698",
    "font_family": "Segoe UI Variable",
    "border_radius": 10,
}

_FALLBACK_QSS = """\
QWidget {{
    background-color: {background};
    color: {text_color};
    font-family: "{font_family}";
}}
QPushButton {{
    background-color: {primary};
    border: 1px solid {accent};
    border-radius: {border_radius}px;
    padding: 8px 16px;
    color: {text_color};
}}
QPushButton:hover {{
    background-color: {primary_hover};
}}
QScrollBar:vertical {{
    background: {background};
    width: 8px;
}}
QScrollBar::handle:vertical {{
    background: {secondary};
    border-radius: 4px;
}}
"""


class ThemeManager(QObject):
    """Manages UI theme colors and generates QSS stylesheets.

    Reads theme configuration from ``[ui.colors]`` in the config TOML,
    generates QSS from a template (with ``{{variable}}`` placeholders),
    and applies it to the application.
    """

    theme_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._primary: str = _DEFAULTS["primary"]
        self._secondary: str = _DEFAULTS["secondary"]
        self._accent: str = _DEFAULTS["accent"]
        self._background: str = _DEFAULTS["background"]
        self._text_color: str = _DEFAULTS["text_color"]
        self._text_secondary: str = _DEFAULTS["text_secondary"]
        self._font_family: str = _DEFAULTS["font_family"]
        self._border_radius: int = _DEFAULTS["border_radius"]

    # ── properties ──────────────────────────────────────────────────────

    @property
    def primary(self) -> str:
        return self._primary

    @primary.setter
    def primary(self, value: str) -> None:
        if value != self._primary:
            self._primary = value
            self.theme_changed.emit()

    @property
    def secondary(self) -> str:
        return self._secondary

    @secondary.setter
    def secondary(self, value: str) -> None:
        if value != self._secondary:
            self._secondary = value
            self.theme_changed.emit()

    @property
    def accent(self) -> str:
        return self._accent

    @accent.setter
    def accent(self, value: str) -> None:
        if value != self._accent:
            self._accent = value
            self.theme_changed.emit()

    @property
    def background(self) -> str:
        return self._background

    @background.setter
    def background(self, value: str) -> None:
        if value != self._background:
            self._background = value
            self.theme_changed.emit()

    @property
    def text_color(self) -> str:
        return self._text_color

    @text_color.setter
    def text_color(self, value: str) -> None:
        if value != self._text_color:
            self._text_color = value
            self.theme_changed.emit()

    @property
    def text_secondary(self) -> str:
        return self._text_secondary

    @text_secondary.setter
    def text_secondary(self, value: str) -> None:
        if value != self._text_secondary:
            self._text_secondary = value
            self.theme_changed.emit()

    @property
    def font_family(self) -> str:
        return self._font_family

    @font_family.setter
    def font_family(self, value: str) -> None:
        if value != self._font_family:
            self._font_family = value
            self.theme_changed.emit()

    @property
    def border_radius(self) -> int:
        return self._border_radius

    @border_radius.setter
    def border_radius(self, value: int) -> None:
        if value != self._border_radius:
            self._border_radius = value
            self.theme_changed.emit()

    # ── config I/O ──────────────────────────────────────────────────────

    def load_from_config(self) -> None:
        """Read ``[ui.colors]`` section from config and apply values."""
        cfg = get_config()
        self._primary = cfg.get("ui.colors.primary", _DEFAULTS["primary"])
        self._secondary = cfg.get("ui.colors.secondary", _DEFAULTS["secondary"])
        self._accent = cfg.get("ui.colors.accent", _DEFAULTS["accent"])
        self._background = cfg.get("ui.colors.background", _DEFAULTS["background"])
        self._text_color = cfg.get("ui.colors.text_color", _DEFAULTS["text_color"])
        self._text_secondary = cfg.get(
            "ui.colors.text_secondary", _DEFAULTS["text_secondary"]
        )
        self._font_family = cfg.get("ui.colors.font_family", _DEFAULTS["font_family"])
        self._border_radius = int(
            cfg.get("ui.colors.border_radius", _DEFAULTS["border_radius"])
        )
        self.theme_changed.emit()

    def save_to_config(self) -> None:
        """Persist current theme values to the user config.toml."""
        path = config_file()
        lines: list[str] = []
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

        theme_block = (
            "\n[ui.colors]\n"
            f'background = "{self._background}"\n'
            f'primary = "{self._primary}"\n'
            f'secondary = "{self._secondary}"\n'
            f'accent = "{self._accent}"\n'
            f'text_color = "{self._text_color}"\n'
            f'text_secondary = "{self._text_secondary}"\n'
            f'font_family = "{self._font_family}"\n'
            f"border_radius = {self._border_radius}\n"
        )

        # Try to replace existing [ui.colors] section
        new_lines, replaced = self._replace_section(lines, "[ui.colors]", theme_block)
        if replaced:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(new_lines), encoding="utf-8")
        else:
            # Append to end
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(theme_block)

    # ── QSS generation ──────────────────────────────────────────────────

    def generate_qss(self) -> str:
        """Build a QSS stylesheet from the template or a built-in fallback."""
        template_path = _resources_dir() / "themes" / "dark_gaming.qss"
        variables = self._template_variables()

        if template_path.exists():
            try:
                template = template_path.read_text(encoding="utf-8")
                for key, value in variables.items():
                    template = template.replace("{{" + key + "}}", str(value))
                return template
            except OSError:
                pass

        # Fallback: use built-in minimal QSS
        return _FALLBACK_QSS.format(**variables)

    def apply(self, app: QApplication) -> None:
        """Generate and apply the QSS to the application."""
        app.setStyleSheet(self.generate_qss())

    # ── helpers ──────────────────────────────────────────────────────────

    def _template_variables(self) -> dict[str, str]:
        ar, ag, ab = _hex_to_rgb(self._accent)
        return {
            # Core palette
            "background": self._background,
            "primary": self._primary,             # surface
            "secondary": self._secondary,         # surface_elevated
            "accent": self._accent,
            "text_color": self._text_color,       # text_primary
            "text_secondary": self._text_secondary,
            "font_family": self._font_family,
            "border_radius": str(self._border_radius),
            # Semantic aliases
            "surface": self._primary,
            "surface_elevated": self._secondary,
            "text_primary": self._text_color,
            "text_muted": "#5c586a",
            # Computed variants
            "primary_hover": lighter(self._primary, 20),
            "primary_pressed": darker(self._primary, 15),
            "secondary_hover": lighter(self._secondary, 20),
            "surface_hover": "#252330",
            "accent_hover": "#ff5a78",
            "accent_pressed": "#c93a52",
            "accent_dark": darker(self._accent, 20),
            "background_lighter": lighter(self._background, 15),
            "navbar_bg": "#0e0d14",
            # Atmospheric extras
            "accent_dim": f"rgba({ar}, {ag}, {ab}, 0.10)",
            "accent_glow": f"rgba({ar}, {ag}, {ab}, 0.30)",
            "accent_atmospheric": f"rgba({ar}, {ag}, {ab}, 0.05)",
            "surface_border": "rgba(255, 255, 255, 0.06)",
            "border_hover": "rgba(255, 255, 255, 0.12)",
            "shadow_color": "rgba(0, 0, 0, 0.40)",
        }

    @staticmethod
    def _replace_section(
        lines: list[str], header: str, replacement: str
    ) -> tuple[list[str], bool]:
        """Replace a TOML section in *lines* with *replacement*.

        Returns (new_lines, True) on success or (original, False) if
        the section header was not found.
        """
        start = None
        for i, line in enumerate(lines):
            if line.strip() == header:
                start = i
                break
        if start is None:
            return lines, False

        # Find end of section (next [section] header or EOF)
        end = len(lines)
        for i in range(start + 1, len(lines)):
            stripped = lines[i].strip()
            if stripped.startswith("[") and not stripped.startswith("[["):
                end = i
                break

        new_lines = lines[:start] + [replacement] + lines[end:]
        return new_lines, True
