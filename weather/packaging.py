"""Which Weather files ship inside the packaged app (for VideoGenerator.spec in phase 1B; tested in test_weather_render.py).

Only what runs: weather-engine's page and renderer (it uses pakmap-engine's modules, MapLibre and font, which pakMap ships),
its fork record, and the weather package's data and prompts. The tests, the recorded responses and the drift tool stay out."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

ENGINE_FILES = ("render.mjs", "page.html", "page.js", "package.json", "UPSTREAM.json")


def data_files(root: Path) -> List[Tuple[str, str]]:
    """(source file, destination folder relative to the app root) for every shipped file."""
    root = Path(root)
    eng = root / "weather-engine"
    out: List[Tuple[str, str]] = []

    def add(src: Path) -> None:
        out.append((str(src), str(src.parent.relative_to(root))))

    for name in ENGINE_FILES:
        if not (eng / name).is_file():
            raise FileNotFoundError(f"{eng / name} is missing: Weather must ship with the app")
        add(eng / name)
    for f in sorted((eng / "lib").glob("*.mjs")) + sorted((eng / "lib" / "layers").glob("*.mjs")):   # graphics plugins too
        add(f)
    for sub, pattern in (("data", "*.json"), ("prompts", "*.txt"), ("data", "*.csv")):
        for f in sorted((root / "weather" / sub).glob(pattern)):
            add(f)
    return out


def python_modules(root: Path) -> List[str]:
    """Every module of the weather package (app.py imports it only inside methods, so the build names them all)."""
    base = Path(root) / "weather"
    out = []
    for f in sorted(base.rglob("*.py")):
        rel = f.relative_to(base.parent).with_suffix("")
        if "testdata" in rel.parts or "__pycache__" in rel.parts:
            continue
        parts = rel.parts[:-1] if rel.name == "__init__" else rel.parts
        out.append(".".join(parts))
    return sorted(set(out))   # the package, its sub-packages (layers, automation, news, post) and every module in them
