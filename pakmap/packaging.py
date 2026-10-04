"""Which files of pakmap-engine ship inside the packaged app (used by VideoGenerator.spec, tested here).

Only what the renderer loads at run time: its own modules, the page, the font, the small bundled
datasets, the MapLibre runtime files, and the GeoTIFF reader with its (tiny) dependencies. The
Node modules for tests, the samples and the dataset build tool stay out (the plan check's validator tool ships)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Set, Tuple

MAPLIBRE_FILES = ("package.json", "dist/maplibre-gl.mjs", "dist/maplibre-gl-shared.mjs", "dist/maplibre-gl-worker.mjs", "dist/maplibre-gl.css")
TOP_FILES = ("render.mjs", "page.html", "page.js", "package.json", "tools/validate_spec.mjs")


def npm_closure(node_modules: Path, package: str) -> Set[str]:
    """`package` and everything it depends on (flat node_modules layout)."""
    seen: Set[str] = set()
    todo = [package]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        pj = node_modules / name / "package.json"
        if not pj.is_file():
            raise FileNotFoundError(f"{pj} is missing: run `npm ci --omit=dev` in pakmap-engine/ before building")
        seen.add(name)
        todo += list(json.loads(pj.read_text(encoding="utf-8")).get("dependencies", {}))
    return seen


def engine_data_files(root: Path) -> List[Tuple[str, str]]:
    """(source file, destination folder relative to the app root) for every shipped file."""
    eng = Path(root) / "pakmap-engine"
    out: List[Tuple[str, str]] = []

    def add(src: Path) -> None:
        out.append((str(src), str(src.parent.relative_to(root))))

    for name in TOP_FILES:
        if not (eng / name).is_file():
            raise FileNotFoundError(f"{eng / name} is missing: pakMap must ship with the app")
        add(eng / name)
    for sub, pattern in (("lib", "*.mjs"), ("assets/fonts", "*"), ("data", "*.json"), ("data", "*.gz")):
        for f in sorted((eng / sub).glob(pattern)):
            if f.is_file():
                add(f)
    nm = eng / "node_modules"
    for name in MAPLIBRE_FILES:
        f = nm / "maplibre-gl" / name
        if not f.is_file():
            raise FileNotFoundError(f"{f} is missing: run `npm ci --omit=dev` in pakmap-engine/ before building")
        add(f)
    for pkg in sorted(npm_closure(nm, "geotiff")):
        for f in sorted((nm / pkg).rglob("*")):
            if f.is_file() and "/test" not in f.as_posix() and not f.name.endswith((".map", ".md", ".d.ts")):
                add(f)
    return out
