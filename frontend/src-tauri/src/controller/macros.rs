//! Config-driven macro engine.
//!
//! Port of `src/pixiis/controller/macros.py:MacroEngine`. Loads
//! `[controller.macros]` from a TOML table and matches incoming
//! `ControllerEvent`s to produce `MacroAction`s.

use std::str::FromStr;

use parking_lot::RwLock;

use crate::types::{ActionKind, ButtonState, ControllerEvent, MacroAction, MacroMode};

/// What kind of trigger a macro listens for.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TriggerKind {
    Button(u8),
    /// Combo of two distinct buttons. Stored as `(min, max)`.
    Combo(u8, u8),
}

/// One parsed macro definition. Mirrors `_MacroDef` in macros.py.
#[derive(Debug, Clone)]
struct MacroDef {
    trigger: String,
    kind: TriggerKind,
    mode: MacroMode,
    action: ActionKind,
    target: String,
}

/// User-supplied macro values for `controller_register_macro`. Strings here
/// match the wire format in `default_config.toml` and Tauri command args.
#[derive(Debug, Clone)]
pub struct MacroDefRaw {
    pub trigger: String,
    pub mode: String,
    pub action: String,
    pub target: String,
}

#[derive(Debug, thiserror::Error)]
pub enum MacroParseError {
    #[error("trigger {0:?} must be of the form button:N or combo:A+B")]
    BadTrigger(String),
    #[error("unknown macro mode {0:?}")]
    BadMode(String),
    #[error("unknown action kind {0:?}")]
    BadAction(String),
}

pub struct MacroEngine {
    macros: RwLock<Vec<MacroDef>>,
}

impl MacroEngine {
    pub fn new() -> Self {
        Self {
            macros: RwLock::new(Vec::new()),
        }
    }

    /// Replace the macro table with definitions from a `[controller.macros]`
    /// TOML table. Invalid entries are silently dropped (matching the Python
    /// behaviour) so a single bad row never breaks the rest of the config.
    pub fn load_from_toml(&self, table: &toml::value::Table) {
        let mut out = Vec::with_capacity(table.len());
        for (trigger, value) in table {
            let Some(def_table) = value.as_table() else {
                continue;
            };
            let mode = def_table
                .get("mode")
                .and_then(|v| v.as_str())
                .unwrap_or("press");
            let action = def_table
                .get("action")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let target = def_table
                .get("target")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            if let Ok(def) = MacroDef::parse(trigger, mode, action, &target) {
                out.push(def);
            }
        }
        *self.macros.write() = out;
    }

    /// Register or replace a single macro by trigger string.
    pub fn register(&self, raw: MacroDefRaw) -> Result<(), MacroParseError> {
        let def = MacroDef::parse(&raw.trigger, &raw.mode, &raw.action, &raw.target)?;
        let mut macros = self.macros.write();
        macros.retain(|m| m.trigger != def.trigger);
        macros.push(def);
        Ok(())
    }

    /// Walk the macro table and return every `MacroAction` whose trigger
    /// matches `event`. Most events match zero macros; some match many
    /// (e.g. if the user binds two macros to the same button).
    pub fn match_event(&self, event: &ControllerEvent) -> Vec<MacroAction> {
        self.macros
            .read()
            .iter()
            .filter(|m| matches(m, event))
            .map(|m| MacroAction {
                action: m.action,
                mode: m.mode,
                trigger: m.trigger.clone(),
                target: m.target.clone(),
                chain: Vec::new(),
            })
            .collect()
    }

    /// For tests and `controller_get_state`-style introspection.
    #[cfg(test)]
    fn len(&self) -> usize {
        self.macros.read().len()
    }
}

impl Default for MacroEngine {
    fn default() -> Self {
        Self::new()
    }
}

impl MacroDef {
    fn parse(
        trigger: &str,
        mode: &str,
        action: &str,
        target: &str,
    ) -> Result<Self, MacroParseError> {
        let kind = parse_trigger(trigger)
            .ok_or_else(|| MacroParseError::BadTrigger(trigger.to_string()))?;
        let mode = MacroMode::from_str(mode)
            .map_err(|_| MacroParseError::BadMode(mode.to_string()))?;
        let action = ActionKind::from_str(action)
            .map_err(|_| MacroParseError::BadAction(action.to_string()))?;
        Ok(Self {
            trigger: trigger.to_string(),
            kind,
            mode,
            action,
            target: target.to_string(),
        })
    }
}

fn parse_trigger(trigger: &str) -> Option<TriggerKind> {
    let (kind, rest) = trigger.split_once(':')?;
    match kind.trim().to_ascii_lowercase().as_str() {
        "button" => rest.trim().parse::<u8>().ok().map(TriggerKind::Button),
        "combo" => {
            let (a, b) = rest.split_once('+')?;
            let a: u8 = a.trim().parse().ok()?;
            let b: u8 = b.trim().parse().ok()?;
            if a == b {
                return None;
            }
            let (lo, hi) = if a < b { (a, b) } else { (b, a) };
            Some(TriggerKind::Combo(lo, hi))
        }
        _ => None,
    }
}

fn matches(def: &MacroDef, event: &ControllerEvent) -> bool {
    match def.kind {
        TriggerKind::Button(idx) => {
            if event.button != u32::from(idx) {
                return false;
            }
            matches!(
                (def.mode, event.state),
                (MacroMode::Press, ButtonState::Pressed)
                    | (MacroMode::Hold, ButtonState::Held)
            )
        }
        TriggerKind::Combo(a, b) => {
            let combo_id = u32::from(a) * 100 + u32::from(b);
            event.button == combo_id && event.state == ButtonState::Pressed
        }
    }
}

// FromStr impls for the shared enums — kept in this module so we can swap
// to `crate::types::*` `FromStr` once Pane 7 lands without breaking this
// engine. The string forms match the JSON tags on the enum.

impl FromStr for MacroMode {
    type Err = ();
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.trim().to_ascii_lowercase().as_str() {
            "press" => Ok(MacroMode::Press),
            "hold" => Ok(MacroMode::Hold),
            "combo" => Ok(MacroMode::Combo),
            _ => Err(()),
        }
    }
}

impl FromStr for ActionKind {
    type Err = ();
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.trim().to_ascii_lowercase().as_str() {
            "voice_record" => Ok(ActionKind::VoiceRecord),
            "launch_app" => Ok(ActionKind::LaunchApp),
            "send_keys" => Ok(ActionKind::SendKeys),
            "navigate_ui" => Ok(ActionKind::NavigateUi),
            "run_script" => Ok(ActionKind::RunScript),
            "chain" => Ok(ActionKind::Chain),
            _ => Err(()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::ButtonState;

    fn press(button: u32) -> ControllerEvent {
        ControllerEvent {
            button,
            state: ButtonState::Pressed,
            timestamp: 0.0,
            duration: 0.0,
        }
    }

    #[test]
    fn combo_4_plus_5_matches_synthetic_id_405() {
        let engine = MacroEngine::new();
        engine
            .register(MacroDefRaw {
                trigger: "combo:4+5".into(),
                mode: "combo".into(),
                action: "send_keys".into(),
                target: "alt+tab".into(),
            })
            .unwrap();

        let actions = engine.match_event(&press(4 * 100 + 5));
        assert_eq!(actions.len(), 1, "expected one macro to fire");
        let action = &actions[0];
        assert_eq!(action.action, ActionKind::SendKeys);
        assert_eq!(action.target, "alt+tab");
        assert_eq!(action.trigger, "combo:4+5");

        // Pressing only one of the two buttons must not fire the combo.
        assert!(engine.match_event(&press(4)).is_empty());
        assert!(engine.match_event(&press(5)).is_empty());
    }

    #[test]
    fn button_press_macro_only_fires_on_pressed() {
        let engine = MacroEngine::new();
        engine
            .register(MacroDefRaw {
                trigger: "button:0".into(),
                mode: "press".into(),
                action: "voice_record".into(),
                target: String::new(),
            })
            .unwrap();

        // Pressed → fires.
        let actions = engine.match_event(&press(0));
        assert_eq!(actions.len(), 1);
        assert_eq!(actions[0].action, ActionKind::VoiceRecord);

        // Held with mode=press should NOT fire.
        let held = ControllerEvent {
            button: 0,
            state: ButtonState::Held,
            timestamp: 0.0,
            duration: 0.5,
        };
        assert!(engine.match_event(&held).is_empty());
    }

    #[test]
    fn loads_macros_from_toml_table() {
        let raw = r#"
[controller.macros]
"button:0" = { mode = "hold", action = "voice_record", target = "" }
"combo:4+5" = { mode = "combo", action = "navigate_ui", target = "file_manager" }
"button:99" = { mode = "press", action = "garbage", target = "" }
"#;
        let parsed: toml::Value = raw.parse().unwrap();
        let table = parsed["controller"]["macros"].as_table().unwrap();

        let engine = MacroEngine::new();
        engine.load_from_toml(table);

        // The garbage row should have been dropped.
        assert_eq!(engine.len(), 2);

        // Button:0 with mode=hold matches HELD.
        let held = ControllerEvent {
            button: 0,
            state: ButtonState::Held,
            timestamp: 0.0,
            duration: 0.3,
        };
        assert_eq!(engine.match_event(&held).len(), 1);
    }

    #[test]
    fn register_replaces_existing_trigger() {
        let engine = MacroEngine::new();
        engine
            .register(MacroDefRaw {
                trigger: "button:1".into(),
                mode: "press".into(),
                action: "navigate_ui".into(),
                target: "back".into(),
            })
            .unwrap();
        engine
            .register(MacroDefRaw {
                trigger: "button:1".into(),
                mode: "press".into(),
                action: "navigate_ui".into(),
                target: "search".into(),
            })
            .unwrap();
        assert_eq!(engine.len(), 1);
        let actions = engine.match_event(&press(1));
        assert_eq!(actions[0].target, "search");
    }
}
