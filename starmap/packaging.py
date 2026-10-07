"""Which files of StarMap ship inside the packaged app (used by VideoGenerator.spec, tested by test_starmap_packaging.py).

The renderer (starmap-engine/): its scripts, page, modules and layers, the textures, star catalogue and font it loads, and from
node_modules only the three.js build, the glTF loader (with its one helper) and astronomy-engine's browser build. Tests, samples
and the rest of node_modules stay out. The Python side's data: the body and site catalogs and the mission packs."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

TOP_FILES = ("render.mjs", "cutter.mjs", "page.html", "page.js", "package.json")
NODE_FILES = ("three/package.json", "three/build/three.module.min.js", "three/examples/jsm/loaders/GLTFLoader.js",
              "three/examples/jsm/utils/BufferGeometryUtils.js", "astronomy-engine/package.json", "astronomy-engine/astronomy.browser.min.js")


def engine_data_files(root: Path) -> List[Tuple[str, str]]:
    """(source file, destination folder relative to the app root) for every shipped file."""
    root = Path(root)
    eng = root / "starmap-engine"
    out: List[Tuple[str, str]] = []

    def add(src: Path) -> None:
        out.append((str(src), str(src.parent.relative_to(root))))

    for name in TOP_FILES:
        if not (eng / name).is_file():
            raise FileNotFoundError(f"{eng / name} is missing: StarMap must ship with the app")
        add(eng / name)
    for sub, pattern in (("lib", "*.mjs"), ("layers", "*.mjs"), ("assets/textures", "*"), ("assets/catalogs", "*.json"), ("assets/fonts", "*")):
        files = sorted(f for f in (eng / sub).glob(pattern) if f.is_file())
        if not files:
            raise FileNotFoundError(f"{eng / sub} has no {pattern}: StarMap must ship with the app")
        for f in files:
            add(f)
    for name in NODE_FILES:
        f = eng / "node_modules" / name
        if not f.is_file():
            raise FileNotFoundError(f"{f} is missing: run `npm ci --omit=dev` in starmap-engine/ before building")
        add(f)
    for sub in ("starmap/catalog", "starmap/packs"):
        for f in sorted((root / sub).glob("*.json")):
            add(f)
    return out
