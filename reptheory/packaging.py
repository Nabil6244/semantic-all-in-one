"""Build inputs for Rep Theory (same shape as health_cinema/packaging.py, tested by test_rep_theory.py): the package's Python modules and the four bundled pictures (assets/reptheory). It reuses the app's own ffmpeg, Pillow, numpy and bundled
fonts (assets/fonts); a user library (~/RepTheoryAssets or REP_THEORY_ASSET_DIR) is optional and overrides the bundled set."""
from __future__ import annotations
from pathlib import Path
from typing import List, Tuple

def python_modules(root) -> List[str]:
    pkg = Path(root) / "reptheory"
    return ["reptheory"] + sorted(f"reptheory.{p.stem}" for p in pkg.glob("*.py") if p.stem != "__init__")

def data_files(root) -> List[Tuple[str, str]]:
    """The bundled pictures (assets/reptheory: the four originals and their index) land in the app at assets/reptheory, where library.bundled_root() looks."""
    src = Path(root) / "assets" / "reptheory"
    return [(str(p), "assets/reptheory") for p in sorted(src.glob("*")) if p.is_file() and p.suffix.lower() in (".png", ".json")]

def model_data_files(root) -> List[Tuple[str, str]]:
    """The 3D gym body (assets/reptheory_3d: model, anchors, Z-Anatomy licence and notice, CC BY-SA 4.0) for the build; clip3d.model_dirs() looks there at run time. Without it 3D scenes keep their normal look."""
    src = Path(root) / "assets" / "reptheory_3d"
    return [(str(p), "assets/reptheory_3d") for p in sorted(src.glob("*")) if p.is_file() and p.suffix.lower() in (".glb", ".json", ".txt")]
