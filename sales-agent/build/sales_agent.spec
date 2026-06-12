# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Ragnarok Sales Agent

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('.env', '.')],
    hiddenimports=['win32com', 'pythoncom', 'win32com.client'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name='RagnarokSalesAgent',
    console=True,
    icon=None,
    onefile=True,
)
