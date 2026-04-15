"""Folder scanner library provider — catch-all for games in common directories."""

from __future__ import annotations

import re
import string
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pixiis.core.types import AppEntry, AppSource

if TYPE_CHECKING:
    from pixiis.core.config import Config

# Minimum exe size to consider (skip tiny launchers/tools)
_MIN_EXE_BYTES = 1_000_000  # 1 MB

# System/non-game directories to skip (case-insensitive)
_SKIP_DIRS = frozenset({
    "windows", "system32", "syswow64", "winsxs", "microsoft",
    "common files", "windowsapps", "microsoft.net", "dotnet",
    "uninstall", "redist", "redistributable", "directx",
    "support", "driver", "drivers", "installer", "installers",
    "msbuild", "reference assemblies", "windows defender",
    "windows mail", "windows media player", "windows multimedia platform",
    "windows nt", "windows photo viewer", "windows portable devices",
    "windows security", "windows sidebar", "windowspowershell",
    "internet explorer", "microsoft office", "microsoft update",
    "pkg", "temp", "tmp", "cache", "logs", "backup",
    "$recycle.bin", "system volume information", "recovery",
    "perflogs", "intel", "nvidia", "nvidia corporation", "amd",
    "realtek", "dell", "hp", "lenovo", "asus",
})

# Exe filenames to always skip (case-insensitive, without extension)
_SKIP_EXES = frozenset({
    "uninstall", "unins000", "unins001", "uninst", "uninstaller",
    "crashhandler", "crashreporter", "crashdump", "crashpad_handler",
    "vc_redist", "vcredist", "dxsetup", "dxwebsetup",
    "setup", "install", "installer", "updater", "update",
    "launcher", "bootstrapper", "prereq",
    "ue4prereqsetup_x64", "ue4prereqsetup",
    "dotnetfx", "ndp", "windowsdesktop-runtime",
})

# Regex for exe names that are likely not the main game
_SKIP_EXE_RE = re.compile(
    r"^(unins\d+|crash|vc_?redist|dxsetup|setup|install|update)", re.IGNORECASE
)

# Well-known game directory names under drive roots
_GAME_DIR_NAMES = ("Games", "SteamLibrary", "GOG Games", "Epic Games")


class FolderScanProvider:
    """Scan common directories for game executables."""

    def __init__(self, config: Config) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "folders"

    def is_available(self) -> bool:
        return sys.platform == "win32"

    def scan(self) -> list[AppEntry]:
        scan_roots = self._gather_scan_roots()
        apps: list[AppEntry] = []
        seen_paths: set[str] = set()

        for root in scan_roots:
            if not root.is_dir():
                continue
            for entry in self._scan_directory(root, max_depth=2):
                norm = str(entry.exe_path).lower() if entry.exe_path else ""
                if norm and norm not in seen_paths:
                    seen_paths.add(norm)
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

    def get_icon(self, app: AppEntry) -> Path | None:
        return None

    # -- internals -----------------------------------------------------------

    def _gather_scan_roots(self) -> list[Path]:
        """Build the list of directories to scan."""
        roots: list[Path] = []

        # Standard Program Files
        roots.append(Path("C:/Program Files"))
        roots.append(Path("C:/Program Files (x86)"))

        # Check all drive letters for known game directories
        for letter in string.ascii_uppercase:
            if letter == "A":
                continue  # skip floppy
            drive = Path(f"{letter}:/")
            if not drive.exists():
                continue
            for dirname in _GAME_DIR_NAMES:
                candidate = drive / dirname
                if candidate.is_dir():
                    roots.append(candidate)

        # User-configured extra paths
        extra: list[str] = self._config.get("library.folders.extra_paths", [])
        for p in extra:
            ep = Path(p)
            if ep.is_dir():
                roots.append(ep)

        return roots

    def _scan_directory(self, root: Path, max_depth: int) -> list[AppEntry]:
        """Scan a directory up to *max_depth* levels for game folders."""
        apps: list[AppEntry] = []

        try:
            entries = sorted(root.iterdir())
        except OSError:
            return apps

        for child in entries:
            if not child.is_dir():
                continue

            if child.name.lower() in _SKIP_DIRS:
                continue

            # Try to find a main exe in this folder
            main_exe = self._find_main_exe(child)
            if main_exe is not None:
                apps.append(AppEntry(
                    id=f"folder:{child.name.lower().replace(' ', '_')}",
                    name=child.name,
                    source=AppSource.MANUAL,
                    launch_command=str(main_exe),
                    exe_path=main_exe,
                    metadata={"scan_root": str(root)},
                ))
            elif max_depth > 1:
                # Go one level deeper
                apps.extend(self._scan_directory(child, max_depth - 1))

        return apps

    @staticmethod
    def _find_main_exe(folder: Path) -> Path | None:
        """Find the most likely main executable in a folder."""
        try:
            exes = [
                f for f in folder.iterdir()
                if f.is_file()
                and f.suffix.lower() == ".exe"
                and f.stem.lower() not in _SKIP_EXES
                and not _SKIP_EXE_RE.match(f.stem)
            ]
        except OSError:
            return None

        if not exes:
            return None

        # Filter by minimum size
        sized: list[tuple[Path, int]] = []
        for exe in exes:
            try:
                size = exe.stat().st_size
            except OSError:
                continue
            if size >= _MIN_EXE_BYTES:
                sized.append((exe, size))

        if not sized:
            return None

        # Prefer exe whose name matches the folder name
        folder_lower = folder.name.lower().replace(" ", "")
        for exe, _ in sized:
            if exe.stem.lower().replace(" ", "") == folder_lower:
                return exe

        # Otherwise, return the largest exe
        sized.sort(key=lambda t: t[1], reverse=True)
        return sized[0][0]
