# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for lp music player

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['src/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('icon.png', '.'),
    ],
    hiddenimports=[
        'just_playback',
        'mutagen',
        'mutagen.mp3',
        'mutagen.flac',
        'mutagen.mp4',
        '_cffi_backend',
        'cffi',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'keyboard',
        'pynput',
        'pydbus',
        'evdev',
        'Xlib',
        'tkinter',
    ],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='lp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='icon.png' if sys.platform != 'darwin' else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='lp',
)

# macOS app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='lp.app',
        icon='icon.png',
        bundle_identifier='com.lp.musicplayer',
        info_plist={
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )
