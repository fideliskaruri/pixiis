"""Build script — creates a distributable Pixiis package with PyInstaller."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Paths
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
RESOURCES = ROOT / "resources"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC_FILE = ROOT / "pixiis.spec"


def download_whisper_model() -> Path:
    """Download the Whisper 'base' model for bundling."""
    model_dir = ROOT / "models" / "whisper-base"
    if model_dir.exists() and any(model_dir.iterdir()):
        print(f"Whisper model already at {model_dir}")
        return model_dir

    print("Downloading Whisper 'base' model for bundling...")
    try:
        from faster_whisper import WhisperModel
        # This downloads to huggingface cache — we'll copy it
        model = WhisperModel("base", device="cpu", compute_type="int8")
        # Find where it was cached
        import huggingface_hub
        cache_path = Path(huggingface_hub.snapshot_download("Systran/faster-whisper-base"))
        model_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(cache_path, model_dir, dirs_exist_ok=True)
        print(f"Model saved to {model_dir}")
    except Exception as e:
        print(f"Failed to download model: {e}")
        print("Install faster-whisper first: pip install faster-whisper")
    return model_dir


def run_pyinstaller() -> None:
    """Build the application with PyInstaller in one-dir mode."""
    model_dir = download_whisper_model()

    add_data = [
        f"{RESOURCES}{os.pathsep}resources",
    ]
    if model_dir.exists():
        add_data.append(f"{model_dir}{os.pathsep}models/whisper-base")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "pixiis",
        "--windowed",
        "--onedir",
        "--noconfirm",
    ]
    for d in add_data:
        cmd.extend(["--add-data", d])
    cmd.append(str(SRC / "pixiis" / "__main__.py"))

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(ROOT))


def copy_extras() -> None:
    """Copy additional files into the dist folder."""
    dist_root = DIST / "pixiis"
    if not dist_root.exists():
        print("Warning: dist/pixiis not found — skipping extras copy")
        return

    # Ensure resources are present (PyInstaller --add-data should handle this,
    # but copy manually as a fallback)
    dist_res = dist_root / "resources"
    if not dist_res.exists() and RESOURCES.exists():
        shutil.copytree(RESOURCES, dist_res)
        print(f"Copied resources → {dist_res}")

    # Copy README
    readme = ROOT / "README.md"
    if readme.exists():
        shutil.copy2(readme, dist_root / "README.md")


def write_nsis_stub() -> None:
    """Write a skeleton NSIS installer script for future use."""
    nsis_path = ROOT / "installer.nsi"
    nsis_path.write_text(
        """; Pixiis NSIS Installer Script (stub)
; Requires NSIS 3.x — https://nsis.sourceforge.io

!include "MUI2.nsh"

Name "Pixiis"
OutFile "pixiis-setup.exe"
InstallDir "$PROGRAMFILES\\Pixiis"
RequestExecutionLevel user

; --- Pages ---
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

; --- Install ---
Section "Install"
    SetOutPath $INSTDIR
    File /r "dist\\pixiis\\*.*"

    ; Start-menu shortcut
    CreateDirectory "$SMPROGRAMS\\Pixiis"
    CreateShortcut "$SMPROGRAMS\\Pixiis\\Pixiis.lnk" "$INSTDIR\\pixiis.exe"

    ; Uninstaller
    WriteUninstaller "$INSTDIR\\uninstall.exe"
SectionEnd

; --- Uninstall ---
Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\\Pixiis"
SectionEnd
""",
        encoding="utf-8",
    )
    print(f"Wrote NSIS stub → {nsis_path}")


def main() -> None:
    print(f"Pixiis build script — root: {ROOT}")
    print()

    run_pyinstaller()
    copy_extras()
    write_nsis_stub()

    print()
    print("Build complete. Output in dist/pixiis/")


if __name__ == "__main__":
    main()
