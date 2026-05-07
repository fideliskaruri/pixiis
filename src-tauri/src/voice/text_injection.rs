//! Type a string into the foreground window via Win32 `SendInput`.
//!
//! Port of `text_injection.py::TextInjector._inject_win32` (the `SendInput`
//! / `KEYEVENTF_UNICODE` path). On non-Windows targets this is a no-op so
//! the rest of the voice subsystem stays portable for tests.

use std::thread;
use std::time::Duration;

use crate::error::AppResult;

/// Per-keystroke pacing — matches `text_injection.py::KEYSTROKE_DELAY`.
const KEYSTROKE_DELAY: Duration = Duration::from_millis(5);

/// Type `text` into whatever window currently has focus.
pub fn inject(text: &str) -> AppResult<()> {
    if text.is_empty() {
        return Ok(());
    }
    #[cfg(target_os = "windows")]
    {
        inject_win32(text)
    }
    #[cfg(not(target_os = "windows"))]
    {
        // Useful for `cargo test` on Linux / macOS — keep the surface
        // available so commands compile cross-platform.
        eprintln!("[voice/inject] non-Windows host, would type: {text}");
        Ok(())
    }
}

#[cfg(target_os = "windows")]
fn inject_win32(text: &str) -> AppResult<()> {
    use windows::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS,
        KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, VIRTUAL_KEY,
    };

    let utf16: Vec<u16> = text.encode_utf16().collect();
    if utf16.is_empty() {
        return Ok(());
    }

    let size = std::mem::size_of::<INPUT>() as i32;

    for code in utf16 {
        // Surrogates can come through as two u16s — both go via SendInput
        // unchanged; Windows reassembles them at the receiver.
        let down = INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: VIRTUAL_KEY(0),
                    wScan: code,
                    dwFlags: KEYEVENTF_UNICODE,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        };
        let up = INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: VIRTUAL_KEY(0),
                    wScan: code,
                    dwFlags: KEYBD_EVENT_FLAGS(KEYEVENTF_UNICODE.0 | KEYEVENTF_KEYUP.0),
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        };
        let pair = [down, up];
        // SAFETY: pair is a valid, aligned, properly-typed INPUT slice for
        // the window of this call; SendInput reads it synchronously.
        unsafe {
            SendInput(&pair, size);
        }
        if !KEYSTROKE_DELAY.is_zero() {
            thread::sleep(KEYSTROKE_DELAY);
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_string_is_noop() {
        assert!(inject("").is_ok());
    }
}
