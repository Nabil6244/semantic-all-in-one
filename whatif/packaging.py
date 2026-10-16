"""Which files of What If ship inside the packaged app (used by VideoGenerator.spec, tested by test_whatif.py).

The renderer (whatif-engine/): its scripts, page, modules and layers, the template library, fonts, the NASA models and textures it draws, and from the
sibling starmap-engine's node_modules the three.js pieces it needs beyond StarMap's own (the Draco decoder NASA's models use).
The Python side: every module of the package (app.py imports it only inside methods) and the shot-CSV prompt."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

TOP_FILES = ("render.mjs", "cutter.mjs", "page.html", "page.js", "package.json")
THREE_EXTRA = ("three/examples/jsm/loaders/DRACOLoader.js", "three/examples/jsm/libs/draco/gltf/draco_decoder.js",
               "three/examples/jsm/libs/draco/gltf/draco_decoder.wasm", "three/examples/jsm/libs/draco/gltf/draco_wasm_wrapper.js")


def data_files(root: Path) -> List[Tuple[str, str]]:
    """(source file, destination folder relative to the app root) for every shipped file."""
    root = Path(root)
    eng = root / "whatif-engine"
    out: List[Tuple[str, str]] = []

    def add(src: Path) -> None:
        out.append((str(src), str(src.parent.relative_to(root))))

    for name in TOP_FILES:
        if not (eng / name).is_file():
            raise FileNotFoundError(f"{eng / name} is missing: What If must ship with the app")
        add(eng / name)
    for sub, pattern in (("lib", "*.mjs"), ("layers", "*.mjs"), ("tools", "*.mjs"), ("assets/fonts", "*.ttf"), ("assets/models", "*.glb"), ("assets/textures", "*")):
        files = sorted(f for f in (eng / sub).glob(pattern) if f.is_file())
        if not files:
            raise FileNotFoundError(f"{eng / sub} has no {pattern}: What If must ship with the app")
        for f in files:
            add(f)
    templates = sorted((eng / "templates").rglob("*.json"))      # the template library (whatif/templates.py reads it at plan time)
    if not templates:
        raise FileNotFoundError(f"{eng / 'templates'} has no templates: What If must ship with the app")
    for f in templates:
        add(f)
    for name in THREE_EXTRA:
        f = root / "starmap-engine" / "node_modules" / name
        if not f.is_file():
            raise FileNotFoundError(f"{f} is missing: run `npm ci --omit=dev` in starmap-engine/ before building")
        add(f)
    for f in sorted((root / "composition_styles").glob("whatif_*.txt")):
        add(f)
    return out


def python_modules(root: Path) -> List[str]:
    return ["whatif"] + [f"whatif.{p.stem}" for p in sorted((Path(root) / "whatif").glob("*.py")) if p.stem != "__init__"]
