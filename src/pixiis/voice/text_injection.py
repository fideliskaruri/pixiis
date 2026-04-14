"""Text injection into the focused window via platform APIs."""

from __future__ import annotations

import sys
import time


class TextInjector:
    """Types text into the currently focused application.

    On Windows, uses ctypes + Win32 SendInput with KEYEVENTF_UNICODE
    (VK_PACKET approach) so every Unicode character is supported.
    On other platforms, falls back to printing to stdout.
    """

    # Delay between keystrokes to avoid overwhelming target apps.
    KEYSTROKE_DELAY: float = 0.005

    def inject(self, text: str) -> None:
        """Type *text* character-by-character into the focused window."""
        if not text:
            return
        if sys.platform == "win32":
            self._inject_win32(text)
        else:
            print(text)

    def inject_clipboard(self, text: str) -> None:
        """Copy *text* to the clipboard and paste with Ctrl+V."""
        if not text:
            return
        if sys.platform == "win32":
            self._inject_clipboard_win32(text)
        else:
            print(text)

    # ── Windows implementation ───────────────────────────────────────────

    def _inject_win32(self, text: str) -> None:
        import ctypes
        from ctypes import wintypes

        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002
        INPUT_KEYBOARD = 1

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT(ctypes.Structure):
            class _INPUT(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]

            _fields_ = [
                ("type", wintypes.DWORD),
                ("_input", _INPUT),
            ]

        def _send_char(char: str) -> None:
            code = ord(char)
            inputs = (INPUT * 2)()

            # Key down
            inputs[0].type = INPUT_KEYBOARD
            inputs[0]._input.ki.wVk = 0
            inputs[0]._input.ki.wScan = code
            inputs[0]._input.ki.dwFlags = KEYEVENTF_UNICODE

            # Key up
            inputs[1].type = INPUT_KEYBOARD
            inputs[1]._input.ki.wVk = 0
            inputs[1]._input.ki.wScan = code
            inputs[1]._input.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP

            ctypes.windll.user32.SendInput(2, inputs, ctypes.sizeof(INPUT))

        for char in text:
            _send_char(char)
            if self.KEYSTROKE_DELAY > 0:
                time.sleep(self.KEYSTROKE_DELAY)

    def _inject_clipboard_win32(self, text: str) -> None:
        import ctypes
        from ctypes import wintypes

        # ── copy to clipboard ────────────────────────────────────────
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        data = text.encode("utf-16-le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        ptr = kernel32.GlobalLock(h_mem)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h_mem)

        user32.OpenClipboard(0)
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        user32.CloseClipboard()

        # ── send Ctrl+V ──────────────────────────────────────────────
        KEYEVENTF_KEYUP = 0x0002
        INPUT_KEYBOARD = 1
        VK_CONTROL = 0x11
        VK_V = 0x56

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT(ctypes.Structure):
            class _INPUT(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]

            _fields_ = [
                ("type", wintypes.DWORD),
                ("_input", _INPUT),
            ]

        inputs = (INPUT * 4)()

        # Ctrl down
        inputs[0].type = INPUT_KEYBOARD
        inputs[0]._input.ki.wVk = VK_CONTROL

        # V down
        inputs[1].type = INPUT_KEYBOARD
        inputs[1]._input.ki.wVk = VK_V

        # V up
        inputs[2].type = INPUT_KEYBOARD
        inputs[2]._input.ki.wVk = VK_V
        inputs[2]._input.ki.dwFlags = KEYEVENTF_KEYUP

        # Ctrl up
        inputs[3].type = INPUT_KEYBOARD
        inputs[3]._input.ki.wVk = VK_CONTROL
        inputs[3]._input.ki.dwFlags = KEYEVENTF_KEYUP

        ctypes.windll.user32.SendInput(4, inputs, ctypes.sizeof(INPUT))
