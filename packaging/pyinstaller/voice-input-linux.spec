# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


ROOT = Path(SPECPATH).parents[1]

datas = []
datas += collect_data_files("voice_input", includes=["resources/*"])
datas += collect_data_files("sounddevice")

binaries = []
binaries += collect_dynamic_libs("sounddevice")

hiddenimports = []
for package in ("dbus_next", "evdev", "pynput", "websockets"):
    hiddenimports += collect_submodules(package)
hiddenimports += [
    "_cffi_backend",
    "cffi",
    "pynput._util.xorg",
    "pynput._util.xorg_keysyms",
    "pynput.keyboard._base",
    "pynput.keyboard._xorg",
    "pynput.mouse._base",
    "pynput.mouse._xorg",
]

metadata = []
for package in ("PySide6", "sounddevice", "numpy", "websockets", "pynput", "evdev", "dbus-next"):
    try:
        metadata += copy_metadata(package)
    except Exception:
        pass


a = Analysis(
    [str(ROOT / "packaging" / "pyinstaller" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas + metadata,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    noarchive=True,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="voice-input-linux",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="voice-input-linux",
)
