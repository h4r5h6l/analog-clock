# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('analogclock/fonts', 'analogclock/fonts')],
    hiddenimports=[
        'analogclock',
        'analogclock.bootstrap',
        'analogclock.config',
        'analogclock.colors',
        'analogclock.timezones',
        'analogclock.hardware',
        'analogclock.background_sheet',
        'analogclock.drawing',
        'analogclock.settings_dialog',
        'analogclock.analog_clock_widget',
    ],
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
    name='clock',
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
