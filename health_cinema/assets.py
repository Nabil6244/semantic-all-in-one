"""Where Health Cinema finds its optional 3D assets and tools. Nothing here is bundled: the anatomy model (a Z-Anatomy derivative, licence review
pending) is looked up in a per-user folder or HEALTH_CINEMA_ASSET_DIR, and the 3D path is simply 'unavailable' when it is not there.

Runtime roots are the app's shared ones (dev checkout, PyInstaller bundle dir, next to the executable) so a packaged app never depends on a
developer-machine path. Everything the 3D path needs is checked up front: a missing piece means 'anatomy unavailable' and a text-card fallback,
never a crash."""
from __future__ import annotations

import os, shutil, sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
MODEL, ANCHORS = "chest.glb", "anchors.json"   # legacy names of the chest asset
ASSET_FILES = {"chest": ("chest.glb", "anchors.json"), "head": ("head.glb", "anchors_head.json"), "abdomen": ("abdomen.glb", "anchors_abdomen.json"), "msk": ("msk.glb", "anchors_msk.json")}   # see library.py
TEMPLATE_ASSET = {"heart_journey": "chest", "chest_journey": "chest", "brain_journey": "head", "eye_journey": "head"}
# three.js files page.js imports (GLTFLoader and the bloom post-processing chain), relative to three/examples/jsm: see packaging.py
THREE_ADDONS = ("loaders/GLTFLoader.js", "utils/BufferGeometryUtils.js", "postprocessing/EffectComposer.js", "postprocessing/MaskPass.js", "postprocessing/OutputPass.js",
                "postprocessing/Pass.js", "postprocessing/RenderPass.js", "postprocessing/ShaderPass.js", "postprocessing/UnrealBloomPass.js",
                "shaders/CopyShader.js", "shaders/LuminosityHighPassShader.js", "shaders/OutputShader.js")

def roots() -> List[Path]:
    try:
        from providers.flow.engine_manager import _candidate_roots
        return list(_candidate_roots())
    except Exception:
        return [ROOT]

def _find(rel: str) -> Optional[Path]:
    for r in roots():
        p = r / rel
        if p.exists(): return p
    return None

LOCAL_LIBRARY = Path.home() / "HealthCinemaTools" / "bench"     # where the prepped chest/head GLBs live on a dev machine (not shipped, not downloaded)

def asset_dirs() -> List[Path]:
    """Folders searched for the anatomy models, best first. HEALTH_CINEMA_ASSET_DIR is authoritative when set (tests and packaged installs point it
    somewhere exact); otherwise the per-user folder, then the local model library the models are prepared in."""
    env = os.environ.get("HEALTH_CINEMA_ASSET_DIR")
    if env: return [Path(env).expanduser()]
    return [Path.home() / ".semantic_yt_studio" / "health_cinema" / "assets", LOCAL_LIBRARY]

def asset_dir() -> Path:
    """The first searched folder that holds any anatomy model, else the first one (kept for callers that want a single path)."""
    ds = asset_dirs()
    for d in ds:
        if any((d / f).is_file() for pair in ASSET_FILES.values() for f in pair): return d
    return ds[0]

def anatomy_assets(kind: str = "chest") -> Optional[dict]:
    if kind == "micro":      # procedural scenes (blood flow, plaque, clot, cell): no model file, just their anchors, shipped with the templates
        p = ROOT / "health_cinema" / "templates" / "micro_anchors.json"
        return {"model": str(p), "anchors": str(p)} if p.is_file() else None
    mf, af = ASSET_FILES[kind]
    for d in asset_dirs():
        m, a = d / mf, d / af
        if m.is_file() and a.is_file(): return {"model": str(m), "anchors": str(a)}
    return None

def anatomy_status() -> dict:
    """What the 3D path can use right now, for the report and the log: which journeys are ready and why the others are not."""
    ready = {t: template_ready(t) for t in TEMPLATE_ASSET}; miss = missing_threejs_files()
    return {"ready": ready, "library": __import__("health_cinema.library", fromlist=["x"]).available(template_ready), "dirs": [str(d) for d in asset_dirs()], "threejs_missing": miss, "browser": browser_ready(), "usable": bool(any(ready.values()) and not miss and browser_ready())}

def model_for_template(template: str) -> Optional[str]:
    """Model kind a journey template needs: the four hand-authored ones, or a generated `auto:<organ>:<shot>` from the library."""
    if template in TEMPLATE_ASSET: return TEMPLATE_ASSET[template]
    from . import library
    return library.model_of(template)

def template_ready(template: str) -> bool:
    """The anatomy asset behind a journey template exists locally (the Three.js runtime is checked separately). For generated templates the organ's anchor and
    layers must also be in the prepared model."""
    kind = model_for_template(template)
    a = anatomy_assets(kind) if kind else None
    if not a: return False
    if template in TEMPLATE_ASSET: return True
    try:
        from . import library
        library.build_spec(template, a["anchors"]); return True
    except Exception: return False

def node_path() -> Optional[str]:
    name = "node.exe" if sys.platform == "win32" else "node"
    p = _find(f"bin/{name}")
    return str(p) if p else shutil.which("node")

def ffmpeg_path() -> Optional[str]:
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    p = _find(f"bin/{name}")
    return str(p) if p else shutil.which("ffmpeg")

def ffprobe_path() -> Optional[str]:
    name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    p = _find(f"bin/{name}")
    return str(p) if p else shutil.which("ffprobe")

def missing_threejs_files() -> List[str]:
    """Runtime files the Three.js path needs and cannot find (empty = ready). Names are relative, never machine paths."""
    miss: List[str] = []
    if not node_path(): miss.append("node")
    if _find("health_cinema/threejs/render.mjs") is None: miss.append("health_cinema/threejs/render.mjs")
    if _find("flow-engine/node_modules/playwright") is None: miss.append("flow-engine/node_modules/playwright")
    if _find("starmap-engine/node_modules/three/build/three.module.min.js") is None: miss.append("three/build/three.module.min.js")
    for a in THREE_ADDONS:
        if _find(f"starmap-engine/node_modules/three/examples/jsm/{a}") is None: miss.append(f"three/examples/jsm/{a}")
    return miss

def browser_channel() -> Optional[str]:
    """Playwright's own Chromium when installed, else the system Chrome (None = Playwright default). Never downloads anything."""
    try:
        from providers.playwright_chromium import is_playwright_chromium_installed, system_chrome_available
        if is_playwright_chromium_installed(): return None
        if system_chrome_available(): return "chrome"
    except Exception:
        pass
    return None

def browser_ready() -> bool:
    try:
        from providers.playwright_chromium import is_playwright_chromium_installed, system_chrome_available
        return bool(is_playwright_chromium_installed() or system_chrome_available())
    except Exception:
        return True      # cannot tell: let the render try, and fall back if it fails

def threejs_ready() -> bool:
    return not missing_threejs_files() and browser_ready()

def anatomy_ready(kind: str = "chest") -> bool:
    return anatomy_assets(kind) is not None and threejs_ready()
