"""Which files of the Normal Video graphics renderer ship inside the packaged app (used by VideoGenerator.spec, tested here).

gfx-overlay-engine/ is a thin page + driver; everything it draws with (gfx-core modules, templates, fonts, the Montserrat font) and the Playwright runtime
already ship with pakMap (pakmap/packaging.py) and Flow. Only these files are new."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

ENGINE_FILES = ("render.mjs", "page.html", "page.js", "package.json")


def engine_data_files(root: Path) -> List[Tuple[str, str]]:
    root = Path(root)
    out: List[Tuple[str, str]] = []
    for name in ENGINE_FILES:
        f = root / "gfx-overlay-engine" / name
        if not f.is_file():
            raise FileNotFoundError(f"{f} is missing: the Normal Video graphics renderer must ship with the app")
        out.append((str(f), "gfx-overlay-engine"))
    allow = root / "normal_gfx" / "allowlist.json"
    if not allow.is_file():
        raise FileNotFoundError(f"{allow} is missing")
    out.append((str(allow), "normal_gfx"))
    return out
