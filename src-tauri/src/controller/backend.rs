//! gilrs-backed controller capture for the always-on background path.
//!
//! Translates raw gilrs events into the numeric button/axis indices that
//! `controller/mapping.py` historically used, so the same `[controller.macros]`
//! TOML keys keep working.

use gilrs::{Axis, Button, EventType, GamepadId, Gilrs};

/// Number of logical buttons we track. Matches the Python `ButtonMapper`
/// default (16) — covers Xbox-style pads with room for extras.
pub const NUM_BUTTONS: usize = 16;

/// Number of logical axes we track (LSx, LSy, RSx, RSy, LT, RT, DPadX, DPadY).
pub const NUM_AXES: usize = 8;

/// A normalised input event the rest of the controller pipeline understands.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum RawEvent {
    Button { index: u8, pressed: bool },
    Axis { index: u8, value: f32 },
    Connected,
    Disconnected,
}

pub struct Backend {
    gilrs: Gilrs,
    /// Currently-tracked gamepad. We follow the most recently connected
    /// pad, mirroring the single-controller assumption in the Python code.
    active: Option<GamepadId>,
    active_name: Option<String>,
}

impl Backend {
    // gilrs::Error is a 200+ byte enum we don't control. Boxing it here
    // would only push the cost to the heap for a 1-time init failure.
    #[allow(clippy::result_large_err)]
    pub fn new() -> Result<Self, gilrs::Error> {
        let gilrs = Gilrs::new()?;
        // Pick whichever pad is already plugged in at startup, if any.
        let (active, active_name) = gilrs
            .gamepads()
            .next()
            .map(|(id, gp)| (Some(id), Some(gp.name().to_string())))
            .unwrap_or((None, None));
        Ok(Self {
            gilrs,
            active,
            active_name,
        })
    }

    /// Drain the gilrs event queue and translate everything we care about.
    pub fn poll(&mut self) -> Vec<RawEvent> {
        let mut out = Vec::new();
        while let Some(ev) = self.gilrs.next_event() {
            match ev.event {
                EventType::Connected => {
                    // Adopt the new pad if we don't have one.
                    if self.active.is_none() {
                        self.active = Some(ev.id);
                        self.active_name =
                            Some(self.gilrs.gamepad(ev.id).name().to_string());
                    }
                    out.push(RawEvent::Connected);
                }
                EventType::Disconnected => {
                    if self.active == Some(ev.id) {
                        self.active = None;
                        self.active_name = None;
                    }
                    out.push(RawEvent::Disconnected);
                }
                EventType::ButtonPressed(btn, _)
                | EventType::ButtonRepeated(btn, _) => {
                    if let Some(idx) = button_to_index(btn) {
                        out.push(RawEvent::Button { index: idx, pressed: true });
                    } else if let Some(axis_evt) = button_to_dpad_axis(btn, true) {
                        out.push(axis_evt);
                    }
                }
                EventType::ButtonReleased(btn, _) => {
                    if let Some(idx) = button_to_index(btn) {
                        out.push(RawEvent::Button { index: idx, pressed: false });
                    } else if let Some(axis_evt) = button_to_dpad_axis(btn, false) {
                        out.push(axis_evt);
                    }
                }
                EventType::AxisChanged(axis, value, _) => {
                    if let Some((idx, normalised)) = axis_to_index(axis, value) {
                        out.push(RawEvent::Axis { index: idx, value: normalised });
                    }
                }
                EventType::ButtonChanged(btn, value, _) => {
                    // gilrs surfaces analogue triggers as ButtonChanged with
                    // a value in 0..=1. Map LT/RT here so trigger-level changes
                    // are visible even when AxisChanged isn't fired (some
                    // backends only emit one or the other).
                    match btn {
                        Button::LeftTrigger2 => {
                            out.push(RawEvent::Axis { index: 4, value });
                        }
                        Button::RightTrigger2 => {
                            out.push(RawEvent::Axis { index: 5, value });
                        }
                        _ => {}
                    }
                }
                _ => {}
            }
        }
        out
    }

    /// Names of every gamepad gilrs currently knows about.
    pub fn connected_gamepads(&self) -> Vec<String> {
        self.gilrs
            .gamepads()
            .map(|(_, gp)| gp.name().to_string())
            .collect()
    }

    pub fn active_name(&self) -> Option<&str> {
        self.active_name.as_deref()
    }

    pub fn is_connected(&self) -> bool {
        self.active.is_some()
    }
}

/// Map a gilrs `Button` to the numeric index used by Python's `mapping.py`.
fn button_to_index(btn: Button) -> Option<u8> {
    match btn {
        Button::South => Some(0),         // A
        Button::East => Some(1),          // B
        Button::West => Some(2),          // X
        Button::North => Some(3),         // Y
        Button::LeftTrigger => Some(4),   // LB (shoulder)
        Button::RightTrigger => Some(5),  // RB (shoulder)
        Button::Select => Some(6),        // Back / View
        Button::Start => Some(7),         // Start / Menu
        Button::LeftThumb => Some(8),     // LS click
        Button::RightThumb => Some(9),    // RS click
        _ => None,
    }
}

/// Some drivers expose D-pad as discrete buttons rather than as an axis.
/// Synthesize the matching `RawEvent::Axis` so downstream sees a single shape.
fn button_to_dpad_axis(btn: Button, pressed: bool) -> Option<RawEvent> {
    let value = if pressed { 1.0 } else { 0.0 };
    match btn {
        Button::DPadLeft => Some(RawEvent::Axis { index: 6, value: -value }),
        Button::DPadRight => Some(RawEvent::Axis { index: 6, value }),
        Button::DPadUp => Some(RawEvent::Axis { index: 7, value: -value }),
        Button::DPadDown => Some(RawEvent::Axis { index: 7, value }),
        _ => None,
    }
}

/// Map a gilrs `Axis` to its index. `value` is passed through; gilrs already
/// normalises sticks to `-1..=1` and triggers to `0..=1`.
fn axis_to_index(axis: Axis, value: f32) -> Option<(u8, f32)> {
    match axis {
        Axis::LeftStickX => Some((0, value)),
        Axis::LeftStickY => Some((1, value)),
        Axis::RightStickX => Some((2, value)),
        Axis::RightStickY => Some((3, value)),
        Axis::LeftZ => Some((4, value)),
        Axis::RightZ => Some((5, value)),
        Axis::DPadX => Some((6, value)),
        Axis::DPadY => Some((7, value)),
        _ => None,
    }
}
