# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Semantic YT Studio (onedir, windowed).

Build:
  # Put ffmpeg in bin/ first (see bin/README.md), then:
  pyinstaller VideoGenerator.spec

Outputs:
  Mac:    dist/Semantic YT Studio.app  (then scripts/make_dmg.sh)
  Windows: dist/Semantic YT Studio/Semantic YT Studio.exe

Icons are generated from assets/logo.png → AppIcon.ico / AppIcon.icns.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.building.osx import BUNDLE
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

try:
    ROOT = Path(SPECPATH).resolve()  # noqa: F821 — injected by PyInstaller
except NameError:
    ROOT = Path(__file__).resolve().parent if "__file__" in dir() else Path.cwd()

BIN = ROOT / "bin"

datas: list = []
binaries: list = []
hiddenimports: list = []

for pkg in ("customtkinter", "faster_whisper", "ctranslate2", "tokenizers", "onnxruntime", "PIL",
            "requests", "websockets", "yt_dlp"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

binaries += collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("onnxruntime")

# Bundle ffmpeg from bin/ (required for packaged builds)
if sys.platform == "win32":
    ffmpeg_src = BIN / "ffmpeg.exe"
else:
    ffmpeg_src = BIN / "ffmpeg"

if not ffmpeg_src.is_file():
    raise SystemExit(
        f"Missing {ffmpeg_src.name} — place it at {ffmpeg_src} before building.\n"
        "See bin/README.md"
    )

binaries += [(str(ffmpeg_src), "bin")]

# ffprobe probes MP3/M4A reference clips for voice clone (Windows has no system ffprobe).
if sys.platform == "win32":
    ffprobe_src = BIN / "ffprobe.exe"
    if ffprobe_src.is_file():
        binaries += [(str(ffprobe_src), "bin")]
    else:
        print(
            "WARNING: bin/ffprobe.exe not found — MP3/M4A reference audio may fail on Windows. "
            "Copy ffprobe.exe from the same ffmpeg essentials zip as ffmpeg.exe."
        )

# Qwen in-app Download + isolated worker subprocess need these on disk (not only in PYZ).
manifest = ROOT / "tts" / "install_manifest.json"
if not manifest.is_file():
    raise SystemExit(f"Missing {manifest}")
datas += [(str(manifest), "tts")]

for pkg_dir in ("tts", "installer"):
    pkg_path = ROOT / pkg_dir
    if not pkg_path.is_dir():
        continue
    for f in pkg_path.rglob("*.py"):
        rel_dir = f.parent.relative_to(ROOT)
        datas.append((str(f), str(rel_dir)))

# generation with zero Node.js install required. Optional: Stock and Manual scenes
# work fine without it, so we only warn (not fail the build) if it's missing.
node_src = BIN / ("node.exe" if sys.platform == "win32" else "node")
if node_src.is_file():
    binaries += [(str(node_src), "bin")]
else:
    print(f"WARNING: {node_src} not found — packaged app will not have Flow/AI "
          f"generation available (Stock and Manual scenes are unaffected). "
          f"See bin/README.md.")

# Bundle flow-engine/ (server.js, lib/*.js, config.js, package.json, and its
# pre-installed node_modules) as plain data files — Node/PyInstaller runs it
# with the bundled `node` binary above, no npm install needed at runtime.
FLOW_ENGINE_DIR = ROOT / "flow-engine"
if FLOW_ENGINE_DIR.is_dir():
    for f in FLOW_ENGINE_DIR.rglob("*"):
        if f.is_file():
            rel_dir = f.parent.relative_to(ROOT)
            datas.append((str(f), str(rel_dir)))
else:
    print(f"WARNING: {FLOW_ENGINE_DIR} not found — Flow/AI generation will not be available.")

YT_ACQ_DIR = ROOT / "providers" / "youtube" / "acquisition"
if YT_ACQ_DIR.is_dir():
    for f in YT_ACQ_DIR.rglob("*"):
        if f.is_file():
            rel_dir = f.parent.relative_to(ROOT)
            datas.append((str(f), str(rel_dir)))
else:
    print(f"WARNING: {YT_ACQ_DIR} not found — YouTube browser capture will not be available.")

# App logo (UI) + platform icons
logo_png = ROOT / "assets" / "logo.png"
if logo_png.is_file():
    datas += [(str(logo_png), "assets")]

if sys.platform == "win32":
    icon_file = ROOT / "assets" / "AppIcon.ico"
else:
    icon_file = ROOT / "assets" / "AppIcon.icns"
icon_path = str(icon_file) if icon_file.is_file() else None

a = Analysis(
    ["app.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "video_generator",
        "customtkinter",
        "darkdetect",
        "faster_whisper",
        "ctranslate2",
        "av",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFont",
        "multiprocessing",
        "asset_manager",
        "providers",
        "providers.base",
        "providers.router",
        "providers.local_provider",
        "providers.stock",
        "providers.stock.base",
        "providers.stock.pexels",
        "providers.stock.query",
        "providers.stock.ranking",
        "providers.stock.cache",
        "providers.stock.downloader",
        "providers.flow",
        "providers.flow.client",
        "providers.flow.engine_manager",
        "providers.flow.provider",
        "providers.youtube",
        "providers.youtube.base",
        "providers.youtube.matching",
        "providers.youtube.ranking",
        "providers.youtube.strategies",
        "providers.youtube.ytdlp_backend",
        "providers.youtube.acquisition",
        "providers.youtube.acquisition.browser_client",
        "visual_director",
        "visual_director.director",
        "visual_director.llm",
        "visual_director.schema",
        "yt_dlp",
        "requests",
        "websockets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

APP_NAME = "Semantic YT Studio"

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed — no terminal
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
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=icon_path,
        bundle_identifier="com.semantictystudio.app",
        info_plist={
            "CFBundleDisplayName": APP_NAME,
            "CFBundleName": APP_NAME,
            "NSHighResolutionCapable": True,
        },
    )
