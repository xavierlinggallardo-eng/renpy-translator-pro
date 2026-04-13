# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Ren'Py Translator Pro.
Build with: pyinstaller RenPyTranslator.spec
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect customtkinter theme/image assets
ctk_datas = collect_data_files('customtkinter')

# Optional: argostranslate assets
try:
    from PyInstaller.utils.hooks import collect_data_files as cdf
    argos_datas = cdf('argostranslate')
except Exception:
    argos_datas = []

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=ctk_datas + argos_datas,
    hiddenimports=[
        # CustomTkinter
        'customtkinter',
        'customtkinter.windows',
        'customtkinter.windows.widgets',
        'customtkinter.windows.widgets.theme',
        'customtkinter.windows.widgets.scaling',
        'PIL',
        'PIL._tkinter_finder',
        # Tkinter
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        # Our modules
        'core',
        'core.parser',
        'core.translator',
        'core.memory',
        'core.reinserter',
        'engines',
        'engines.base',
        'engines.argos_engine',
        'engines.libre_engine',
        'engines.gemini_engine',
        'engines.openai_engine',
        'engines.deepl_engine',
        'engines.registry',
        'gui',
        'gui.main_window',
        'utils',
        'utils.config',
        'utils.zip_handler',
        # Optional deps (imported at runtime)
        'argostranslate',
        'argostranslate.translate',
        'argostranslate.package',
        'requests',
        'google.generativeai',
        'openai',
        'deepl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='RenPyTranslator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # windowed — no terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows manifest for high-DPI awareness
    manifest=None,
    # Icon — optional, place icon.ico in project root
    # icon='icon.ico',
)
