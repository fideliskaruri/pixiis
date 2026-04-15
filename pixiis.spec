# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Pixiis — unified game launcher & voice dashboard."""

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "src" / "pixiis" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "resources"), "resources"),
    ],
    hiddenimports=[
        "pixiis.controller.backend",
        "pixiis.library.steam",
        "pixiis.library.xbox",
        "pixiis.library.epic",
        "pixiis.library.gog",
        "pixiis.library.ea",
        "pixiis.library.startmenu",
        "pixiis.library.folder_scanner",
        "pixiis.library.manual",
        "pixiis.voice.transcriber",
        "pixiis.voice.audio_capture",
        "pixiis.services.rawg",
        "pixiis.services.twitch",
        "pixiis.services.youtube",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pixiis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # --windowed
    icon=str(ROOT / "resources" / "icons" / "pixiis.ico")
    if (ROOT / "resources" / "icons" / "pixiis.ico").exists()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="pixiis",
)
