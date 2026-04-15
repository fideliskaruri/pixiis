"""Start Menu library provider — discovers .lnk shortcuts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pixiis.core.types import AppEntry, AppSource

if TYPE_CHECKING:
    from pixiis.core.config import Config


class StartMenuProvider:
    """Scan Windows Start Menu folders for .lnk shortcuts."""

    def __init__(self, config: Config) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "startmenu"

    def is_available(self) -> bool:
        return sys.platform == "win32"

    def scan(self) -> list[AppEntry]:
        lnk_files: list[Path] = []
        for folder in self._start_menu_dirs():
            if folder.is_dir():
                lnk_files.extend(folder.glob("**/*.lnk"))

        apps: list[AppEntry] = []
        for lnk in lnk_files:
            entry = self._parse_lnk(lnk)
            if entry is not None:
                apps.append(entry)
        return apps

    def launch(self, app: AppEntry) -> None:
        if app.exe_path and app.exe_path.exists():
            cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.Popen(
                [str(app.exe_path)],
                cwd=str(app.exe_path.parent),
                creationflags=cf,
            )
        else:
            os.startfile(app.launch_command)  # type: ignore[attr-defined]

    def get_icon(self, app: AppEntry) -> Path | None:
        return None  # Handled by IconCache extracting from exe

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _start_menu_dirs() -> list[Path]:
        """Return the two standard Start Menu program directories."""
        dirs: list[Path] = []

        # All users
        all_users = Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs")
        dirs.append(all_users)

        # Current user
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

        return dirs

    def _parse_lnk(self, lnk_path: Path) -> AppEntry | None:
        """Resolve a .lnk shortcut to an AppEntry."""
        target, working_dir = self._resolve_shortcut(lnk_path)
        if target is None:
            return None

        target_path = Path(target)

        # Skip non-exe targets (URLs, folders, uninstallers, etc.)
        if target_path.suffix.lower() not in (".exe", ".bat", ".cmd"):
            return None
        if "unins" in target_path.name.lower():
            return None

        display_name = lnk_path.stem

        return AppEntry(
            id=f"startmenu:{display_name.lower().replace(' ', '_')}",
            name=display_name,
            source=AppSource.STARTMENU,
            launch_command=str(target_path),
            exe_path=target_path,
            metadata={"lnk_path": str(lnk_path), "working_dir": working_dir or ""},
        )

    def _resolve_shortcut(self, lnk_path: Path) -> tuple[str | None, str | None]:
        """Resolve a .lnk file to (target_path, working_directory).

        Tries pylnk3 first, then falls back to PowerShell.
        """
        result = self._resolve_with_pylnk3(lnk_path)
        if result[0] is not None:
            return result
        return self._resolve_with_powershell(lnk_path)

    @staticmethod
    def _resolve_with_pylnk3(lnk_path: Path) -> tuple[str | None, str | None]:
        """Attempt to parse .lnk using pylnk3."""
        try:
            import pylnk3  # type: ignore[import-untyped]

            lnk = pylnk3.parse(str(lnk_path))
            target = lnk.path
            work_dir = lnk.work_dir or None
            if target:
                return (target, work_dir)
        except Exception:
            pass
        return (None, None)

    @staticmethod
    def _resolve_with_powershell(lnk_path: Path) -> tuple[str | None, str | None]:
        """Fall back to PowerShell to resolve a shortcut."""
        script = (
            f"$s = (New-Object -COM WScript.Shell).CreateShortcut('{lnk_path}');"
            "$s.TargetPath + '|' + $s.WorkingDirectory"
        )
        try:
            cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=cf,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return (None, None)

        if result.returncode != 0 or not result.stdout.strip():
            return (None, None)

        parts = result.stdout.strip().split("|", 1)
        target = parts[0].strip() if parts[0].strip() else None
        work_dir = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        return (target, work_dir)
