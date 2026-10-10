# -*- mode: python ; coding: utf-8 -*-
"""Phase 11 — PyInstaller build for AI Companion (Windows, windowed, one-dir).

Build:  python -m PyInstaller ai-companion.spec --noconfirm
Output: dist/AI-Companion/AI-Companion.exe
Requires (not bundled): Tesseract OCR binary on PATH or TESSERACT_PATH.
"""

block_cipher = None


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets'), ('.env.example', '.')],
    hiddenimports=[
        'mss',
        'mss.windows',
        'pytesseract',
        'PIL',
        'openai',
        'dotenv',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'test', 'tests'],
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
    name='AI-Companion',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='AI-Companion',
)
