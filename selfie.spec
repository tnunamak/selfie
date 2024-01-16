# -*- mode: python ; coding: utf-8 -*-

# Run poetry shell, then pyinstaller cli.spec --noconfirm

import os
a = Analysis(
    ['selfie/__main__.py'],
    debug=True,
    pathex=[os.path.abspath(SPECPATH)],
    binaries=[],
    datas=[
        ('./selfie/data_processing/parsers/chat/blacklist_patterns.yaml', 'selfie/data_processing/parsers/chat/'),
        ('./selfie/web/', 'selfie/web/'),
    ],
    hiddenimports=[
        'tiktoken_ext',
        'tiktoken_ext.openai_public',
        'onnxconverter_common',
    ],
    hookspath=['./hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    module_collection_mode={
        'onnxconverter_common': 'pyz+py',
    },
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='selfie',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='selfie',
)
