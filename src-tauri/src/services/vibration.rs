//! Controller vibration. Windows-only via `XInputSetState`; no-op elsewhere.
//!
//! Mirrors `src/pixiis/services/vibration.py`. We deliberately do *not* own a
//! `Gilrs` here — Pane 8 owns the gamepad runtime. We use XInput directly
//! because gilrs's force-feedback story on XInput is patchy across drivers
//! and `Gilrs::ff_effect_factory` is not consistently available. The brief
//! suggests taking `&Gilrs` to avoid double-init; we sidestep entirely by
//! talking to XInput. If Pane 8 later exposes a vibration method on its
//! controller wrapper, this module can be replaced.
//!
//! `pulse` schedules the motors-off state on the current Tokio runtime, so
//! it must be called from inside an async context (Tauri commands satisfy
//! this).

#[cfg(windows)]
use std::time::Duration;

#[cfg(windows)]
mod win {
    use windows::Win32::UI::Input::XboxController::{XInputSetState, XINPUT_VIBRATION};

    pub fn set_state(index: u32, left: u16, right: u16) {
        let mut v = XINPUT_VIBRATION {
            wLeftMotorSpeed: left,
            wRightMotorSpeed: right,
        };
        // SAFETY: XInputSetState is a thread-safe Win32 call; we pass a
        // pointer to a stack-allocated XINPUT_VIBRATION that lives for the
        // duration of the call.
        unsafe {
            let _ = XInputSetState(index, &mut v as *mut _);
        }
    }
}

/// Fire-and-forget pulse: set both motors for `duration_ms`, then stop.
///
/// `left` / `right` are 0..=65535. Non-Windows targets are no-ops.
pub fn pulse(controller_index: u32, left: u16, right: u16, duration_ms: u32) {
    #[cfg(windows)]
    {
        win::set_state(controller_index, left, right);
        let dur = Duration::from_millis(duration_ms as u64);
        // tokio::spawn is fine if we're inside a runtime (Tauri cmd context).
        // If somebody calls this from a non-async context, the spawn panics —
        // make that explicit by relying on Handle::try_current.
        if let Ok(h) = tokio::runtime::Handle::try_current() {
            h.spawn(async move {
                tokio::time::sleep(dur).await;
                win::set_state(controller_index, 0, 0);
            });
        } else {
            // No runtime: best-effort blocking sleep on a worker thread.
            std::thread::spawn(move || {
                std::thread::sleep(dur);
                win::set_state(controller_index, 0, 0);
            });
        }
    }
    #[cfg(not(windows))]
    {
        let _ = (controller_index, left, right, duration_ms);
    }
}

/// Common presets — match the Python `VibrationService.rumble_*` helpers.
pub mod presets {
    use super::pulse;

    pub fn confirm(idx: u32) {
        pulse(idx, 20_000, 20_000, 80);
    }

    pub fn back(idx: u32) {
        pulse(idx, 0, 25_000, 50);
    }

    pub fn launch(idx: u32) {
        pulse(idx, 45_000, 45_000, 200);
    }

    pub fn nav(idx: u32) {
        pulse(idx, 8_000, 8_000, 40);
    }
}
