# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for lp music player

import os
import sys
from pathlib import Path

import certifi
from PyQt5.QtCore import QLibraryInfo

block_cipher = None

qt_plugins = QLibraryInfo.location(QLibraryInfo.PluginsPath)

a = Analysis(
    ['src/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('icon.png', '.'),
        ('src/icons', 'icons'),
        (certifi.where(), 'certifi'),
        (os.path.join(qt_plugins, 'audio'), os.path.join('PyQt5', 'Qt5', 'plugins', 'audio')),
        (os.path.join(qt_plugins, 'mediaservice'), os.path.join('PyQt5', 'Qt5', 'plugins', 'mediaservice')),
        (os.path.join(qt_plugins, 'playlistformats'), os.path.join('PyQt5', 'Qt5', 'plugins', 'playlistformats')),
    ],
    hiddenimports=[
        'just_playback',
        'mutagen',
        'mutagen.mp3',
        'mutagen.flac',
        'mutagen.mp4',
        '_cffi_backend',
        'cffi',
        'requests',
        'dbus_fast',
        'dbus_fast.aio',
        'dbus_fast.service',
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

# On Linux, exclude bundled GStreamer core libs so Qt's mediaservice plugins
# use the system GStreamer (which has the full plugin registry and elements).
# Bundling partial GStreamer causes "no element" errors at runtime.
if sys.platform == 'linux':
    _gst_exclude = {'libgstreamer', 'libgstbase', 'libgstapp', 'libgsttag',
                    'libgstaudio', 'libgstvideo', 'libgstpbutils',
                    'libgstallocators'}
    a.binaries = [(name, path, typ) for name, path, typ in a.binaries
                  if not any(name.startswith(g) for g in _gst_exclude)]

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
    icon=None,  # icon set via QIcon at runtime; avoids platform format issues
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
        icon=None,
        bundle_identifier='com.lp.musicplayer',
        info_plist={
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )
