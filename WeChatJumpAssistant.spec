# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
if not (root/'PreciseInput.exe').is_file():
    raise SystemExit('Run build.cmd before packaging.')
if not (root/'build/license-notices').is_dir():
    raise SystemExit('Run tools/collect_licenses.py before packaging.')

a = Analysis(
    [str(root/'jump_assistant.pyw')],
    pathex=[str(root)],
    binaries=[(str(root/'PreciseInput.exe'), '.')],
    datas=[(str(root/'third_party/score_templates.npz'), 'third_party'),
           (str(root/'build/license-notices'), 'THIRD_PARTY_LICENSES')],
    hiddenimports=['PIL._tkinter_finder'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest', 'unittest', 'IPython', 'matplotlib'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='WeChatJumpAssistant-Windows-x64',
    debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    version=str(root/'packaging/version_info.txt'),
)
