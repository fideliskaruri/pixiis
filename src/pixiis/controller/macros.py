"""Config-driven macro engine for controller inputs."""

from __future__ import annotations

from pixiis.core import (
    ActionType,
    ButtonState,
    ControllerEvent,
    MacroAction,
    MacroMode,
    bus,
    get_config,
)


class MacroEngine:
    """Loads macro definitions from TOML config and fires :class:`MacroAction`
    events when matching controller inputs arrive.

    Subscribes to :class:`ControllerEvent` on the global event bus.
    """

    def __init__(self) -> None:
        self._macros: list[_MacroDef] = []
        self._load_macros()
        bus.subscribe(ControllerEvent, self._on_controller_event)

    # ── config loading ──────────────────────────────────────────────────────

    def _load_macros(self) -> None:
        cfg = get_config()
        macros_section: dict = cfg.get("controller.macros", {})
        if not isinstance(macros_section, dict):
            return

        for trigger_str, definition in macros_section.items():
            if not isinstance(definition, dict):
                continue
            parsed = _parse_trigger(trigger_str)
            if parsed is None:
                continue

            mode_str = definition.get("mode", "press")
            try:
                mode = MacroMode(mode_str)
            except ValueError:
                continue

            action_str = definition.get("action", "")
            try:
                action_type = ActionType(action_str)
            except ValueError:
                # Allow unknown action types to be stored as-is for extensibility
                action_type = None

            target = definition.get("target", "")

            self._macros.append(
                _MacroDef(
                    trigger=trigger_str,
                    kind=parsed.kind,
                    buttons=parsed.buttons,
                    mode=mode,
                    action_type=action_type,
                    action_str=action_str,
                    target=target,
                )
            )

    # ── event handling ──────────────────────────────────────────────────────

    def _on_controller_event(self, event: ControllerEvent) -> None:
        for macro in self._macros:
            if not self._matches(macro, event):
                continue
            if macro.action_type is not None:
                action = MacroAction(
                    action=macro.action_type,
                    mode=macro.mode,
                    trigger=macro.trigger,
                    target=macro.target,
                )
                bus.publish(action)

    @staticmethod
    def _matches(macro: _MacroDef, event: ControllerEvent) -> bool:
        """Return True if *event* should trigger *macro*."""
        if macro.kind == "button":
            if event.button != macro.buttons[0]:
                return False
            if macro.mode == MacroMode.PRESS and event.state == ButtonState.PRESSED:
                return True
            if macro.mode == MacroMode.HOLD and event.state == ButtonState.HELD:
                return True
            return False

        if macro.kind == "combo":
            # Combo events use the synthetic id: min*100+max
            a, b = sorted(macro.buttons)
            combo_id = a * 100 + b
            if event.button != combo_id:
                return False
            if event.state == ButtonState.PRESSED:
                return True
            return False

        return False

    def shutdown(self) -> None:
        """Unsubscribe from the event bus."""
        bus.unsubscribe(ControllerEvent, self._on_controller_event)


# ── internal helpers ────────────────────────────────────────────────────────


class _ParsedTrigger:
    __slots__ = ("kind", "buttons")

    def __init__(self, kind: str, buttons: list[int]) -> None:
        self.kind = kind
        self.buttons = buttons


class _MacroDef:
    __slots__ = (
        "trigger", "kind", "buttons", "mode",
        "action_type", "action_str", "target",
    )

    def __init__(
        self,
        trigger: str,
        kind: str,
        buttons: list[int],
        mode: MacroMode,
        action_type: ActionType | None,
        action_str: str,
        target: str,
    ) -> None:
        self.trigger = trigger
        self.kind = kind
        self.buttons = buttons
        self.mode = mode
        self.action_type = action_type
        self.action_str = action_str
        self.target = target


def _parse_trigger(trigger: str) -> _ParsedTrigger | None:
    """Parse ``"button:0"`` or ``"combo:4+5"`` into structured form."""
    if ":" not in trigger:
        return None
    kind, _, rest = trigger.partition(":")
    kind = kind.strip().lower()

    if kind == "button":
        try:
            return _ParsedTrigger("button", [int(rest.strip())])
        except ValueError:
            return None

    if kind == "combo":
        parts = rest.split("+")
        if len(parts) != 2:
            return None
        try:
            return _ParsedTrigger("combo", [int(p.strip()) for p in parts])
        except ValueError:
            return None

    return None
