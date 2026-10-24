"""Which files of the Explainer style ship inside the packaged app (for VideoGenerator.spec, after approval; tested by explainer/spike/verify_m4.py).

Data: the narrator PNG layers and manifest (the original explorer and the serious look), the cartoon kit (sets, cast, props and manifest), and the two OFL handwriting fonts with their licence texts (Inter ships with the application's own assets/fonts folder).
Python: every module of the package (app.py would import it only inside methods, so every module is named, as for What If and Weather)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

DATA_DIRS = ("assets/narrator", "assets/narrator_serious", "assets/cartoon", "assets/fonts")


def data_files(root: Path) -> List[Tuple[str, str]]:
    """(source file, destination folder relative to the app root) for every shipped file."""
    root = Path(root)
    out: List[Tuple[str, str]] = []
    for rel in DATA_DIRS:
        d = root / "explainer" / rel
        files = sorted(f for f in d.glob("*") if f.is_file())
        if not files:
            raise FileNotFoundError(f"{d} has no files: the Explainer style must ship with them")
        for f in files:
            out.append((str(f), str(f.parent.relative_to(root))))
    if not (root / "assets" / "fonts" / "Inter-SemiBold.ttf").is_file():
        raise FileNotFoundError("assets/fonts/Inter-SemiBold.ttf is missing: Explainer chips use it")
    return out


def python_modules(root: Path) -> List[str]:
    root = Path(root)
    mods = ["explainer"]
    for p in sorted((root / "explainer").rglob("*.py")):
        rel = p.relative_to(root).with_suffix("")
        parts = list(rel.parts)
        if "spike" in parts:                      # verification scripts are not part of the application
            continue
        if parts[-1] == "__init__":
            parts = parts[:-1]
        name = ".".join(parts)
        if name and name not in mods:
            mods.append(name)
    return mods
