# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AscensionLauncher.exe, the packaged form of
launcher/ascension_launcher.py.

Build it with scripts\\windows\\build-launcher-exe.ps1, or directly:
    pyinstaller packaging\\windows\\AscensionLauncher.spec --noconfirm

The .exe is meant to be copied (or symlinked) to the repository root
(ascension\\), next to build\\, mods\\, docs\\ and launcher\\ -- see the
FROZEN branch in launcher/app/config.py, which then treats the .exe's own
folder as the repository root.

Nothing under launcher\\ (lang\\*.json, Cinzel-Black.ttf, assets\\) is
embedded here: they stay loose files the .exe reads at startup exactly as
the Python script does, so editing a translation or dropping in artwork
needs no rebuild.
"""

from pathlib import Path

root = Path(SPECPATH).resolve().parent.parent          # packaging/windows/ -> repo root
launcher_dir = root / 'launcher'
icon = root / 'packaging' / 'windows' / 'ascension.ico'

block_cipher = None

a = Analysis(
    [str(launcher_dir / 'ascension_launcher.py')],
    pathex=[str(launcher_dir)],
    binaries=[],
    datas=[],
    # Pillow's Tk image support (PhotoImage for backgrounds/logo) needs this
    # when PyInstaller's import scan misses it.
    hiddenimports=['PIL._tkinter_finder'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    # Passing binaries/zipfiles/datas straight to EXE (rather than through
    # COLLECT) is what makes this a single-file build instead of a folder.
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AscensionLauncher',
    icon=str(icon) if icon.is_file() else None,
    console=False,          # a Tk window, not a console app
)
