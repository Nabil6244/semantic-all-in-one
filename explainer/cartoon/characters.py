"""Loader for the "characters" pack built by explainer/cartoon/build_characters.py (soldier, officer, king, police, worker, farmer, merchant, sailor, doctor, revolutionary, guard, judge, woman, priest).
It only READS: every file is checked against manifest.json (SHA-256 and size) before it is used; a missing or damaged pack answers `problem()` with the reason (a cue problem: the beat keeps its
colour-coded villagers) and never stops a render. `explainer.cartoon.kit` asks this module for any `cast` name that is not one of its own four colours."""

from __future__ import annotations

import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Tuple

from PIL import Image

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "characters"
BUILD_HINT = "rebuild with: python3 -B explainer/cartoon/build_characters.py"


@lru_cache(maxsize=1)
def manifest() -> dict:
    p = ASSET_DIR / "manifest.json"
    if not p.is_file():
        raise FileNotFoundError(f"characters manifest.json is missing ({BUILD_HINT})")
    return json.loads(p.read_bytes())


def types() -> Tuple[str, ...]:
    try:
        return tuple(manifest()["types"])
    except Exception:
        return ()


def is_character(name) -> bool:
    return name in types()


def layers_digest() -> str:
    try:
        return manifest()["layers_digest"]
    except Exception:
        return ""


def problem(kind: str, pose: str) -> str:
    try:
        m = manifest()
    except Exception as exc:
        return str(exc)
    if kind not in m["characters"]:
        return f"unknown character {kind!r} (available: {', '.join(m['types'])})"
    if pose not in m["characters"][kind]:
        return f"unknown pose {pose!r} for {kind} (poses: {', '.join(m['poses'])})"
    slot = m["characters"][kind][pose]
    p = ASSET_DIR / slot["file"]
    if not p.is_file():
        return f"characters asset {slot['file']} is missing ({BUILD_HINT})"
    return ""


@lru_cache(maxsize=96)
def full(kind: str, pose: str) -> Image.Image:
    """The whole 440 x 560 canvas of the character (feet on the bottom edge)."""
    slot = manifest()["characters"][kind][pose]
    import hashlib
    b = (ASSET_DIR / slot["file"]).read_bytes()
    if hashlib.sha256(b).hexdigest() != slot["sha256"] or len(b) != slot["bytes"]:
        raise ValueError(f"characters asset {slot['file']} does not match manifest.json (edited or damaged; {BUILD_HINT})")
    return Image.open(io.BytesIO(b)).convert("RGBA")


_INSTALLED = False


def install() -> bool:
    """Idempotent. Wraps the v1 kit's lookups so a character name is answered here (the v1 files and kit.py are untouched; every other name goes to the v1 functions exactly as before)."""
    global _INSTALLED
    if _INSTALLED:
        return True
    from . import kit as K
    o_problem, o_full, o_crowd = K.problem, K._cast_full, K.crowd_sprite

    def problem_(style, params):
        if style == "figure" and is_character(params.get("cast")):
            return problem(params["cast"], params.get("pose", "idle"))
        if style == "crowd" and params.get("kind"):
            return "" if is_character(params["kind"]) else f"unknown crowd kind {params['kind']!r}"
        return o_problem(style, params)

    def full_(role, pose, kit):
        return full(role, pose) if is_character(role) else o_full(role, pose, kit)

    @lru_cache(maxsize=32)
    def crowd_(n, height, seed, kind=""):
        if not kind:
            return o_crowd(n, height, seed)
        calm = seed >= 1000                                  # a seed offset of 1000 (continuity beats) asks for idle poses only: no arms out sideways in a row
        seed = seed % 1000
        poses = ("idle",) * 4 if calm else ("idle", "point", "idle", "think")
        figs = [K.cast_sprite(kind, poses[(i + seed) % 4], "a", height, bool((i + seed) % 5 == 4)) for i in range(n)]
        step = int(figs[0].width * K.CROWD_STEP)
        out = Image.new("RGBA", (step * (n - 1) + figs[0].width, height), (0, 0, 0, 0))
        for i, f in enumerate(figs):
            out.alpha_composite(f, (i * step, 0))
        return out

    K.problem, K._cast_full, K.crowd_sprite = problem_, full_, crowd_
    _INSTALLED = True
    return True
