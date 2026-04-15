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
    def is_game(self) -> bool:
        """True if this entry comes from a game launcher (Steam, Epic, GOG, EA, Xbox)."""
        return self.source in (
            AppSource.STEAM,
            AppSource.EPIC,
            AppSource.GOG,
            AppSource.EA,
            AppSource.XBOX,
        )


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
