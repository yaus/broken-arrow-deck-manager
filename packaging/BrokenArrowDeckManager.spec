# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


PROJECT_ROOT = Path.cwd().resolve()
OPTIONAL_DECK_SETS = PROJECT_ROOT / 'deck_sets'
datas = [
    ('..\\assets\\icons\\broken_arrow_deck_manager_icon.ico', '.'),
    ('..\\locales', 'locales'),
]

if OPTIONAL_DECK_SETS.exists():
    datas.append(('..\\deck_sets', 'deck_sets'))


a = Analysis(
    ['..\\src\\broken_arrow_deck_manager.py'],
    pathex=[],
    binaries=[],
    datas=datas,
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
    [],
    exclude_binaries=True,
    name='BrokenArrowDeckManager',
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
    icon=['..\\assets\\icons\\broken_arrow_deck_manager_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BrokenArrowDeckManager',
)
