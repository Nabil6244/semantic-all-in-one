# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the tiny online installer stub.

Bundles installer/ + tts/install_manifest.json only (no Torch, no Qwen, no app payload).

Build:
  pyinstaller Installer.spec

Outputs:
  Windows: dist/VideoGenerator-Setup.exe  (onefile)
  macOS:   dist/VideoGenerator-Installer.app  (then scripts/make_installer_dmg.sh)
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.building.osx import BUNDLE
from PyInstaller.utils.hooks import collect_all

try:
    ROOT = Path(SPECPATH).resolve()  # noqa: F821
except NameError:
    ROOT = Path(__file__).resolve().parent if "__file__" in dir() else Path.cwd()

datas: list = []
binaries: list = []
hiddenimports: list = []

for pkg in ("customtkinter", "darkdetect", "requests", "PIL"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

manifest = ROOT / "tts" / "install_manifest.json"
if not manifest.is_file():
    raise SystemExit(f"Missing {manifest}")
datas += [(str(manifest), "tts")]

# Include installer package modules as data is unnecessary — Analysis finds them via import.
# Also ship empty __init__ tree if needed via hiddenimports.

if sys.platform == "win32":
    icon_file = ROOT / "assets" / "AppIcon.ico"
else:
    icon_file = ROOT / "assets" / "AppIcon.icns"
icon_path = str(icon_file) if icon_file.is_file() else None

a = Analysis(
    ["installer/__main__.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "installer",
        "installer.platform",
        "installer.manifest",
        "installer.download",
        "installer.extract",
        "installer.paths",
        "installer.pipeline",
        "installer.ui",
        "customtkinter",
        "darkdetect",
        "requests",
        "PIL",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "torchaudio",
        "torchvision",
        "qwen_tts",
        "faster_whisper",
        "ctranslate2",
        "onnxruntime",
        "yt_dlp",
        "av",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

if sys.platform == "win32":
    # onefile stub named toward VideoGenerator-Setup.exe
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="VideoGenerator-Setup",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_path,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="VideoGenerator-Installer",
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
        icon=icon_path,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="VideoGenerator-Installer",
    )
    app = BUNDLE(
        coll,
        name="VideoGenerator-Installer.app",
        icon=icon_path,
        bundle_identifier="com.semanticallinone.installer",
        info_plist={
            "CFBundleDisplayName": "Video Generator Setup",
            "CFBundleName": "Video Generator Setup",
            "NSHighResolutionCapable": True,
        },
    )
