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

# ffprobe probes audio/video metadata (required on Windows; also ship on mac/Linux
# when present so packaged builds never depend on a system ffprobe).
ffprobe_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
ffprobe_src = BIN / ffprobe_name
if ffprobe_src.is_file():
    binaries += [(str(ffprobe_src), "bin")]
else:
    raise SystemExit(
        f"Missing {ffprobe_src.name} — place it at {ffprobe_src} before building "
        "(same release zip / brew prefix as ffmpeg).\nSee bin/README.md"
    )

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
# Skip docs / Vite trace UI / agent skills — unused at runtime (~few MB).
_SKIP_NODE_MODULE_PARTS = (
    "/README",
    "/CHANGELOG",
    "/LICENSE",
    "/NOTICE",
    "/ThirdPartyNotices",
    "/lib/vite/",
    "/lib/tools/skills/",
    "/.github/",
    "/docs/",
)


def _should_bundle_data_file(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    if "/node_modules/" not in f"/{rel}":
        return True
    lowered = f"/{rel}"
    if any(part in lowered for part in _SKIP_NODE_MODULE_PARTS):
        return False
    # Drop markdown / typescript declaration bloat inside node_modules.
    if path.suffix.lower() in {".md", ".map", ".ts"} and "/node_modules/" in lowered:
        # Keep .d.ts out; keep package.json / js / mjs / cjs.
        if path.name.endswith(".d.ts") or path.suffix.lower() in {".md", ".map"}:
            return False
    return True


FLOW_ENGINE_DIR = ROOT / "flow-engine"
if FLOW_ENGINE_DIR.is_dir():
    for f in FLOW_ENGINE_DIR.rglob("*"):
        if f.is_file() and _should_bundle_data_file(f, ROOT):
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

# Brand Kit + Video Style JSON (required for Brand & Style in packaged builds)
for _data_dir_name in ("styles", "brand_kits"):
    _data_dir = ROOT / _data_dir_name
    if _data_dir.is_dir():
        for f in _data_dir.glob("*.json"):
            datas.append((str(f), _data_dir_name))
    else:
        print(f"WARNING: {_data_dir} missing — packaged Brand & Style menus may be empty.")

# Bundled typography fonts
_FONTS_DIR = ROOT / "assets" / "fonts"
if _FONTS_DIR.is_dir():
    for f in _FONTS_DIR.rglob("*"):
        if f.is_file():
            rel_dir = f.parent.relative_to(ROOT)
            datas.append((str(f), str(rel_dir)))
else:
    print(f"WARNING: {_FONTS_DIR} missing — typography will fall back to system fonts.")

# Bundled SFX + ambience library — REQUIRED for packaged builds.
# Categories: whoosh, impact, ui, text, transition, riser, cinematic,
# technology, ambience. Seeded into ~/.videogen/sfx on first launch.
BUNDLED_SFX_DIR = ROOT / "assets" / "bundled-sfx"
_REQUIRED_SFX_CATS = (
    "whoosh",
    "impact",
    "ui",
    "text",
    "transition",
    "riser",
    "cinematic",
    "technology",
    "ambience",
)
if not BUNDLED_SFX_DIR.is_dir() or not (BUNDLED_SFX_DIR / "catalog.json").is_file():
    raise SystemExit(
        f"Missing {BUNDLED_SFX_DIR} (catalog.json + wavs). "
        "SFX/ambience must ship with the app — see assets/bundled-sfx/."
    )
_bundled_wavs = list(BUNDLED_SFX_DIR.rglob("*.wav"))
if len(_bundled_wavs) < 40:
    raise SystemExit(
        f"Incomplete bundled SFX library: found {len(_bundled_wavs)} wavs under "
        f"{BUNDLED_SFX_DIR} (need >= 40 including ambience)."
    )
_missing_cats = [c for c in _REQUIRED_SFX_CATS if not (BUNDLED_SFX_DIR / c).is_dir()]
if _missing_cats:
    raise SystemExit(
        f"Bundled SFX missing category folders: {', '.join(_missing_cats)}"
    )
if not list((BUNDLED_SFX_DIR / "ambience").glob("*.wav")):
    raise SystemExit(f"No ambience wavs in {BUNDLED_SFX_DIR / 'ambience'}")
for f in BUNDLED_SFX_DIR.rglob("*"):
    if f.is_file() and f.name != ".DS_Store":
        rel_dir = f.parent.relative_to(ROOT)
        datas.append((str(f), str(rel_dir)))
print(f"Bundled SFX: {len(_bundled_wavs)} wavs + catalog.json")

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
        "providers.hidden_subprocess",
        "providers.playwright_chromium",
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
        "licensing",
        "licensing.auth_client",
        "licensing.config",
        "licensing.device",
        "licensing.embedded",
        "licensing.login_dialog",
        "licensing.session_store",
        "project_picker",
        "style_engine",
        "style_engine.apply",
        "style_engine.detect",
        "style_engine.loader",
        "style_engine.profile",
        "style_engine.resolver",
        "style_engine.schema",
        "style_engine.typography_map",
        "editorial",
        "editorial.builder",
        "editorial.schema",
        "editorial.persistence",
        "editorial.audio_director",
        "editorial.music_director",
        "editorial.pacing",
        "editorial.qa",
        "ui",
        "ui.views",
        "ui.theme",
        "ui.shell",
        "ui.widgets",
        "typography",
        "typography.fonts",
        "typography.render",
        "smart_editing",
        "sfx",
        "sfx.seed",
        "sfx.catalog_io",
        "sfx.ambience_profiles",
        "sfx.audio_probe",
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
