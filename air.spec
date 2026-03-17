# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["air/__main__.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("air/prompts/*.md", "air/prompts"),
    ],
    hiddenimports=[
        "air.config",
        "air.agent",
        "air.channel",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="air",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
