"""Shared data types for Pixiis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any


# ── App / Library ────────────────────────────────────────────────────────────


class AppSource(Enum):
    STEAM = "steam"
    XBOX = "xbox"
    EPIC = "epic"
    GOG = "gog"
    EA = "ea"
    STARTMENU = "startmenu"
    MANUAL = "manual"


@dataclass
class AppEntry:
    """A launchable application or game."""

    id: str
    name: str
    source: AppSource
    launch_command: str
    exe_path: Path | None = None
    icon_path: Path | None = None
    art_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def playtime_minutes(self) -> int:
        """Total tracked playtime in minutes (stored in metadata)."""
        return int(self.metadata.get("playtime_minutes", 0))

    @playtime_minutes.setter
    def playtime_minutes(self, value: int) -> None:
        self.metadata["playtime_minutes"] = value

    @property
    def playtime_display(self) -> str:
        """Human-readable playtime string, e.g. '12.5 hrs' or '45 min'."""
        mins = self.playtime_minutes
        if mins <= 0:
            return ""
        if mins < 60:
            return f"{mins} min"
        hours = mins / 60
        if hours == int(hours):
            return f"{int(hours)} hrs"
        return f"{hours:.1f} hrs"

    @property
    def last_played(self) -> float:
        """Epoch timestamp of last play session (stored in metadata)."""
        return float(self.metadata.get("last_played", 0))

    @last_played.setter
    def last_played(self, value: float) -> None:
        self.metadata["last_played"] = value

    @property
    def is_installed(self) -> bool:
        """True if the game/app appears to be installed on this machine."""
        if self.exe_path and self.exe_path.exists():
            return True
        # Xbox/UWP games are always "installed" if they show up in scan
        if self.source == AppSource.XBOX:
            return True
        # If we have a launch command, assume installed
        return bool(self.launch_command)

    @property
    def is_favorite(self) -> bool:
        """True if the user has marked this entry as a favorite."""
        return bool(self.metadata.get("favorite", False))

    @is_favorite.setter
    def is_favorite(self, value: bool) -> None:
        self.metadata["favorite"] = value

    @property
    def is_game(self) -> bool:
        """True if this entry is likely a game (not a regular app).

        Steam, Epic, GOG, EA items are always games (those launchers only have games).
        Xbox/UWP items are games only if they have MicrosoftGame.Config.
        Start Menu, Folder Scanner, and Manual items are apps by default.
        """
        if self.source in (AppSource.STEAM, AppSource.EPIC, AppSource.GOG, AppSource.EA):
            return True
        if self.source == AppSource.XBOX:
            return bool(self.metadata.get("is_xbox_game", False))
        return False


# ── Controller ───────────────────────────────────────────────────────────────


class ButtonState(Enum):
    PRESSED = auto()
    RELEASED = auto()
    HELD = auto()


@dataclass
class ControllerEvent:
    """A controller input event."""

    button: int
    state: ButtonState
    timestamp: float
    duration: float = 0.0  # For RELEASED/HELD: how long was it held


@dataclass
class AxisEvent:
    """A controller axis/stick event."""

    axis: int
    value: float
    timestamp: float


# ── Macros ───────────────────────────────────────────────────────────────────


class MacroMode(Enum):
    PRESS = "press"
    HOLD = "hold"
    COMBO = "combo"


class ActionType(Enum):
    VOICE_RECORD = "voice_record"
    LAUNCH_APP = "launch_app"
    SEND_KEYS = "send_keys"
    NAVIGATE_UI = "navigate_ui"
    RUN_SCRIPT = "run_script"
    CHAIN = "chain"


@dataclass
class MacroAction:
    """A macro action triggered by a controller input."""

    action: ActionType
    mode: MacroMode
    trigger: str  # e.g. "button:0", "combo:4+5"
    target: str = ""  # app id, key sequence, page name, script path
    chain: list[MacroAction] = field(default_factory=list)


# ── Navigation ───────────────────────────────────────────────────────────────


class Direction(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()


@dataclass
class NavigationEvent:
    """A navigation direction from controller input."""

    direction: Direction
    timestamp: float


# ── Transcription ───────────────────────────────────────────────────────────


@dataclass
class TranscriptionEvent:
    """Published when voice transcription produces text."""

    text: str
    is_final: bool
    timestamp: float
