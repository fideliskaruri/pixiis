//! Press / hold / release detection and combo recognition.
//!
//! Port of `src/pixiis/controller/mapping.py:ButtonMapper`. Consumes the
//! normalised `RawEvent`s from `controller::backend` and emits typed
//! `ControllerEvent` / `AxisEvent` values for the macro engine.

use std::time::{Duration, Instant};

use crate::controller::backend::{RawEvent, NUM_AXES, NUM_BUTTONS};
use crate::types::{AxisEvent, ButtonState, ControllerEvent};

/// Matches the Python `_ButtonTrack` private dataclass.
#[derive(Default, Clone, Copy)]
struct ButtonTrack {
    down: bool,
    down_since: Option<Instant>,
    held_fired: bool,
}

/// Per-controller mapper that converts low-level `RawEvent`s into typed
/// press / hold / release / combo events on each `tick()`.
pub struct ButtonMapper {
    tracks: [ButtonTrack; NUM_BUTTONS],
    /// Currently-held axis values, used for deadzone gating each tick.
    axis_values: [f32; NUM_AXES],
    /// Down-edge timestamps per button, pruned to the combo window each tick.
    recent_downs: Vec<(u8, Instant)>,
    hold_threshold: Duration,
    combo_window: Duration,
    deadzone: f32,
    /// Reference time for the `f64` timestamps emitted on events.
    epoch: Instant,
}

#[derive(Debug, Clone)]
pub enum MapperEvent {
    Button(ControllerEvent),
    Axis(AxisEvent),
}

#[derive(Debug, Clone, Copy)]
pub struct MapperConfig {
    pub hold_threshold_ms: u64,
    pub combo_window_ms: u64,
    pub deadzone: f32,
}

impl Default for MapperConfig {
    fn default() -> Self {
        Self {
            hold_threshold_ms: 200,
            combo_window_ms: 150,
            deadzone: 0.15,
        }
    }
}

impl ButtonMapper {
    pub fn new(cfg: MapperConfig) -> Self {
        Self {
            tracks: [ButtonTrack::default(); NUM_BUTTONS],
            axis_values: [0.0; NUM_AXES],
            recent_downs: Vec::new(),
            hold_threshold: Duration::from_millis(cfg.hold_threshold_ms),
            combo_window: Duration::from_millis(cfg.combo_window_ms),
            deadzone: cfg.deadzone,
            epoch: Instant::now(),
        }
    }

    /// Apply a batch of `RawEvent`s and run a tick of state-machine work.
    /// Returns every event the macro engine should see this tick.
    pub fn tick(&mut self, raw: &[RawEvent]) -> Vec<MapperEvent> {
        self.tick_at(raw, Instant::now())
    }

    /// Same as [`tick`] but with an explicit clock for tests.
    pub fn tick_at(&mut self, raw: &[RawEvent], now: Instant) -> Vec<MapperEvent> {
        let mut out = Vec::new();

        // 1. Apply edge events from this tick.
        for ev in raw {
            match *ev {
                RawEvent::Button { index, pressed } => {
                    let i = index as usize;
                    if i >= NUM_BUTTONS {
                        continue;
                    }
                    if pressed {
                        self.on_press(i, now);
                    } else if let Some(release) = self.on_release(i, now) {
                        out.push(MapperEvent::Button(release));
                    }
                }
                RawEvent::Axis { index, value } => {
                    let i = index as usize;
                    if i < NUM_AXES {
                        self.axis_values[i] = value;
                    }
                }
                _ => {}
            }
        }

        // 2. Hold detection — any track that's been down longer than the
        //    threshold and hasn't fired yet emits HELD once.
        for i in 0..NUM_BUTTONS {
            let t = &mut self.tracks[i];
            if !t.down || t.held_fired {
                continue;
            }
            if let Some(since) = t.down_since {
                if now.saturating_duration_since(since) >= self.hold_threshold {
                    t.held_fired = true;
                    out.push(MapperEvent::Button(ControllerEvent {
                        button: i as u32,
                        state: ButtonState::Held,
                        timestamp: self.timestamp(now),
                        duration: now.saturating_duration_since(since).as_secs_f64(),
                    }));
                }
            }
        }

        // 3. Combo detection — any pair of distinct down-edges inside the
        //    combo window where both buttons are still held emits a single
        //    synthetic PRESSED event with id = min*100 + max.
        self.recent_downs
            .retain(|(_, t)| now.saturating_duration_since(*t) < self.combo_window);
        let combos = self.detect_combos(now);
        if !combos.is_empty() {
            // Match the Python behaviour: clear once a combo fires so the
            // same pair doesn't re-trigger while still held.
            self.recent_downs.clear();
            out.extend(combos.into_iter().map(MapperEvent::Button));
        }

        // 4. Axis events — emit anything outside the deadzone.
        for (i, value) in self.axis_values.iter().enumerate() {
            if value.abs() > self.deadzone {
                out.push(MapperEvent::Axis(AxisEvent {
                    axis: i as u32,
                    value: *value,
                    timestamp: self.timestamp(now),
                }));
            }
        }

        out
    }

    fn on_press(&mut self, i: usize, now: Instant) {
        let t = &mut self.tracks[i];
        if !t.down {
            t.down = true;
            t.down_since = Some(now);
            t.held_fired = false;
            self.recent_downs.push((i as u8, now));
        }
    }

    fn on_release(&mut self, i: usize, now: Instant) -> Option<ControllerEvent> {
        let t = &mut self.tracks[i];
        if !t.down {
            return None;
        }
        let since = t.down_since.unwrap_or(now);
        let duration = now.saturating_duration_since(since);
        let state = if t.held_fired {
            ButtonState::Released
        } else {
            ButtonState::Pressed
        };
        t.down = false;
        t.down_since = None;
        t.held_fired = false;

        Some(ControllerEvent {
            button: i as u32,
            state,
            timestamp: self.timestamp(now),
            duration: duration.as_secs_f64(),
        })
    }

    fn detect_combos(&self, now: Instant) -> Vec<ControllerEvent> {
        let mut out = Vec::new();
        let mut seen: Vec<(u8, u8)> = Vec::new();

        for (i, &(b1, t1)) in self.recent_downs.iter().enumerate() {
            for &(b2, t2) in self.recent_downs.iter().skip(i + 1) {
                if b1 == b2 {
                    continue;
                }
                let pair = if b1 < b2 { (b1, b2) } else { (b2, b1) };
                if seen.contains(&pair) {
                    continue;
                }
                let dt = if t1 > t2 {
                    t1.saturating_duration_since(t2)
                } else {
                    t2.saturating_duration_since(t1)
                };
                if dt > self.combo_window {
                    continue;
                }
                if !(self.tracks[pair.0 as usize].down
                    && self.tracks[pair.1 as usize].down)
                {
                    continue;
                }
                seen.push(pair);
                let combo_id = pair.0 as u32 * 100 + pair.1 as u32;
                out.push(ControllerEvent {
                    button: combo_id,
                    state: ButtonState::Pressed,
                    timestamp: self.timestamp(now),
                    duration: 0.0,
                });
            }
        }
        out
    }

    fn timestamp(&self, now: Instant) -> f64 {
        now.saturating_duration_since(self.epoch).as_secs_f64()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn press(btn: u8) -> RawEvent {
        RawEvent::Button { index: btn, pressed: true }
    }

    fn release(btn: u8) -> RawEvent {
        RawEvent::Button { index: btn, pressed: false }
    }

    fn button_event(events: &[MapperEvent]) -> Vec<(u32, ButtonState)> {
        events
            .iter()
            .filter_map(|e| match e {
                MapperEvent::Button(b) => Some((b.button, b.state)),
                _ => None,
            })
            .collect()
    }

    #[test]
    fn short_press_then_release_emits_pressed() {
        let mut m = ButtonMapper::new(MapperConfig::default());
        let t0 = Instant::now();

        // Press at t0, no events yet (we only fire on edges + holds).
        let evs = m.tick_at(&[press(0)], t0);
        assert!(button_event(&evs).is_empty());

        // Release 50ms later, well under the 200ms hold threshold.
        let t1 = t0 + Duration::from_millis(50);
        let evs = m.tick_at(&[release(0)], t1);
        let buttons = button_event(&evs);
        assert_eq!(buttons, vec![(0, ButtonState::Pressed)]);
    }

    #[test]
    fn long_hold_then_release_emits_held_and_released() {
        let mut m = ButtonMapper::new(MapperConfig::default());
        let t0 = Instant::now();

        m.tick_at(&[press(3)], t0);

        // Tick again past the hold threshold — should fire HELD once.
        let t1 = t0 + Duration::from_millis(250);
        let evs = m.tick_at(&[], t1);
        let buttons = button_event(&evs);
        assert_eq!(buttons, vec![(3, ButtonState::Held)]);

        // Tick again — HELD must NOT re-fire while still held.
        let t2 = t1 + Duration::from_millis(50);
        let evs = m.tick_at(&[], t2);
        assert!(button_event(&evs).is_empty());

        // Release — should now emit RELEASED, not PRESSED, because we held.
        let t3 = t2 + Duration::from_millis(10);
        let evs = m.tick_at(&[release(3)], t3);
        let buttons = button_event(&evs);
        assert_eq!(buttons, vec![(3, ButtonState::Released)]);
    }

    #[test]
    fn combo_within_window_emits_synthetic_pressed() {
        let mut m = ButtonMapper::new(MapperConfig::default());
        let t0 = Instant::now();

        // Press LB then RB, both inside the 150ms combo window.
        let evs = m.tick_at(&[press(4)], t0);
        assert!(button_event(&evs).is_empty());

        let t1 = t0 + Duration::from_millis(40);
        let evs = m.tick_at(&[press(5)], t1);

        // Expect the synthetic combo id 4*100+5 == 405 with PRESSED.
        let buttons = button_event(&evs);
        assert!(
            buttons.contains(&(405, ButtonState::Pressed)),
            "expected combo 405 in {buttons:?}"
        );
    }

    #[test]
    fn axis_inside_deadzone_is_suppressed() {
        let mut m = ButtonMapper::new(MapperConfig::default());
        let t0 = Instant::now();

        let evs = m.tick_at(
            &[RawEvent::Axis { index: 0, value: 0.05 }],
            t0,
        );
        let any_axis = evs
            .iter()
            .any(|e| matches!(e, MapperEvent::Axis(_)));
        assert!(!any_axis, "0.05 is inside the 0.15 deadzone");
    }

    #[test]
    fn axis_outside_deadzone_emits_event() {
        let mut m = ButtonMapper::new(MapperConfig::default());
        let t0 = Instant::now();

        let evs = m.tick_at(
            &[RawEvent::Axis { index: 1, value: 0.7 }],
            t0,
        );
        let axes: Vec<_> = evs
            .iter()
            .filter_map(|e| match e {
                MapperEvent::Axis(a) => Some((a.axis, a.value)),
                _ => None,
            })
            .collect();
        assert_eq!(axes.len(), 1);
        assert_eq!(axes[0].0, 1);
        assert!((axes[0].1 - 0.7).abs() < f32::EPSILON);
    }
}
