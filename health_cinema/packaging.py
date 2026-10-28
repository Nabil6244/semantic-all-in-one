"""Build inputs for Health Cinema (same shape as whatif/packaging.py, tested by test_health_cinema_style.py).

Ships: the package's Python modules, the journey templates, the Three.js page/renderer scripts, and the three.js addon files page.js imports on top of
what StarMap already ships (GLTFLoader and BufferGeometryUtils are in starmap/packaging.py's list; the bloom post-processing chain is added here).
It reuses the app's own Node, ffmpeg, Playwright (flow-engine) and three.js (starmap-engine); it adds none of them.

Deliberately NOT shipped: any 3D model (the Z-Anatomy derivative is local-only until its licence review clears), Blender, bench/ scripts.
Without the model the 3D path is simply unavailable and every 3D scene becomes a text card (assets.anatomy_ready())."""
from __future__ import annotations
from pathlib import Path
from typing import List, Tuple

from .assets import THREE_ADDONS

DATA_FILES = ("templates/*.json", "threejs/page.html", "threejs/page.js", "threejs/procedural.js", "threejs/render.mjs")
EXCLUDED_SUFFIXES = (".glb", ".gltf", ".blend", ".blend1")

def python_modules(root) -> List[str]:
    pkg = Path(root) / "health_cinema"
    return ["health_cinema"] + sorted(f"health_cinema.{p.stem}" for p in pkg.glob("*.py") if p.stem != "__init__")

def data_files(root) -> List[Tuple[str, str]]:
    """(source file, destination folder relative to the app root)."""
    root = Path(root); base = root / "health_cinema"; out: List[Tuple[str, str]] = []
    for pattern in DATA_FILES:
        found = sorted(base.glob(pattern))
        if not found: raise FileNotFoundError(f"{base / pattern} matches nothing: Health Cinema must ship its scripts")
        for p in found:
            if p.suffix.lower() in EXCLUDED_SUFFIXES: continue
            out.append((str(p), str(Path("health_cinema") / p.parent.relative_to(base))))
    for a in THREE_ADDONS:
        f = root / "starmap-engine" / "node_modules" / "three" / "examples" / "jsm" / a
        if not f.is_file(): raise FileNotFoundError(f"{f} is missing: run `npm ci --omit=dev` in starmap-engine/ before building")
        out.append((str(f), str(f.parent.relative_to(root))))
    return out
