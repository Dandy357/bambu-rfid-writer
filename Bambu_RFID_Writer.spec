# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

root = Path(SPECPATH)
assets = root / "bambu_rfid_diag" / "assets"
locales = root / "bambu_rfid_diag" / "locales"

analysis = Analysis(
    [str(root / "Bambu_RFID_Writer.pyw")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(assets), "bambu_rfid_diag/assets"),
        (str(locales), "bambu_rfid_diag/locales"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="Bambu_RFID_Writer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(assets / "app_icon.ico"),
)
