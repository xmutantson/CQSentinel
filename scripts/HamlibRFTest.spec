# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['test_hamlib_levels_standalone.py'],
    pathex=[],
    binaries=[('external\\hamlib\\bin\\rigctld.exe', '.'), ('external\\hamlib\\bin\\libgcc_s_sjlj-1.dll', '.'), ('external\\hamlib\\bin\\libhamlib-4.dll', '.'), ('external\\hamlib\\bin\\libusb-1.0.dll', '.'), ('external\\hamlib\\bin\\libwinpthread-1.dll', '.')],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HamlibRFTest',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
