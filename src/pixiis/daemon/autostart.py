"""Windows auto-start management via the Run registry key."""

from __future__ import annotations

import sys
from pathlib import Path

_REG_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
_REG_KEY = "Pixiis"


def _get_launch_command() -> str:
    """Build the command that Windows will execute on login.

    Uses the current Python interpreter (or packaged exe) so that
    auto-start works even when Python is not on PATH.
    """
    exe = Path(sys.executable)
    # If running from a PyInstaller bundle, sys.executable is the .exe itself
    if getattr(sys, "frozen", False):
        return f'"{exe}" --daemon'
    # Otherwise, use pythonw.exe (no console window) if available
    pythonw = exe.parent / "pythonw.exe"
    interpreter = str(pythonw) if pythonw.exists() else str(exe)
    return f'"{interpreter}" -m pixiis --daemon'


def enable_autostart() -> None:
    """Add Pixiis to the Windows startup registry."""
    import winreg

    cmd = _get_launch_command()
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, _REG_KEY, 0, winreg.REG_SZ, cmd)


def disable_autostart() -> None:
    """Remove Pixiis from the Windows startup registry."""
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _REG_KEY)
    except FileNotFoundError:
        pass  # Already removed


def is_autostart_enabled() -> bool:
    """Check whether Pixiis is registered to start on login."""
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, _REG_KEY)
            return True
    except FileNotFoundError:
        return False
