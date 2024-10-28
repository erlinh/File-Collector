# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('presets.json', '.'),  # Include presets.json in the bundle
    ],
    hiddenimports=[
        'customtkinter',
        'watchdog',
        'watchdog.observers',
        'watchdog.events',
        'tkinter',
        'json',
        'logging',
        'threading',
        'platform',
        'subprocess'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='file_collector_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None
)

# Create the macOS app bundle
app = BUNDLE(
    exe,
    name='File Collector.app',
    icon=None,  # No icon for now
    bundle_identifier='com.filecollector.app',
    info_plist={
        'CFBundleName': 'File Collector',
        'CFBundleDisplayName': 'File Collector',
        'CFBundleGetInfoString': "File collection utility",
        'CFBundleVersion': "1.0.0",
        'CFBundleShortVersionString': "1.0.0",
        'NSHighResolutionCapable': 'True',
        'LSMinimumSystemVersion': '10.13',
        'NSRequiresAquaSystemAppearance': 'False'  # Enable dark mode support
    }
)
