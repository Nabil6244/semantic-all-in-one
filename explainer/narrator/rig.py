"""Narrator asset loader and compositor. Loads the PNG layers written by build_assets.py and verifies each SHA-256 against manifest.json. It never draws the
character (no drawing code here and no import of the builder): composing is pasting loaded layers, scaling with LANCZOS and mirroring."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "narrator"
ASSET_DIRS = {"cartoon": ASSET_DIR, "serious": Path(__file__).resolve().parents[1] / "assets" / "narrator_serious"}      # the original explorer, and the serious look
BUILD_HINT = "run: python3 -B explainer/narrator/build_assets.py [--style serious]"


class AssetError(Exception):
    pass


@dataclass(frozen=True)
class Assets:
    manifest: dict
    manifest_sha256: str
    bodies: Dict[str, Image.Image]
    eyes: Dict[str, Image.Image]
    mouths: Dict[str, Image.Image]


def _load(name: str, expect_sha: str, expect_bytes: int, folder: Path = ASSET_DIR) -> Image.Image:
    p = folder / name
    if not p.is_file():
        raise AssetError(f"narrator asset {name} is missing ({BUILD_HINT})")
    b = p.read_bytes()
    if hashlib.sha256(b).hexdigest() != expect_sha or len(b) != expect_bytes:
        raise AssetError(f"narrator asset {name} does not match manifest.json (edited or damaged; {BUILD_HINT})")
    import io
    return Image.open(io.BytesIO(b)).convert("RGBA")


@lru_cache(maxsize=4)
def load_assets(style: str = "cartoon") -> Assets:
    if style not in ASSET_DIRS:
        raise AssetError(f"unknown narrator style {style!r} (use {', '.join(sorted(ASSET_DIRS))})")
    folder = ASSET_DIR if style == "cartoon" else ASSET_DIRS[style]       # the original set is read through ASSET_DIR (the verification redirects it to test missing and damaged files)
    mp = folder / "manifest.json"
    if not mp.is_file():
        raise AssetError(f"narrator manifest.json is missing ({BUILD_HINT})")
    raw = mp.read_bytes()
    try:
        m = json.loads(raw)
    except ValueError as e:
        raise AssetError(f"narrator manifest.json is unreadable: {e}")
    try:
        bodies = {k: _load(v["file"], v["sha256"], v["bytes"], folder) for k, v in m["poses"].items()}
        eyes = {k: _load(v["file"], v["sha256"], v["bytes"], folder) for k, v in m["eyes"].items()}
        mouths = {k: _load(v["file"], v["sha256"], v["bytes"], folder) for k, v in m["mouths"].items()}
    except KeyError as e:
        raise AssetError(f"narrator manifest.json lacks {e} ({BUILD_HINT})")
    return Assets(m, hashlib.sha256(raw).hexdigest(), bodies, eyes, mouths)


def canvas_size(style: str = "cartoon") -> Tuple[int, int]:
    c = load_assets(style).manifest["canvas"]
    return int(c[0]), int(c[1])


@lru_cache(maxsize=1024)
def sprite(pose: str, eyes: str, mouth: str, scale_pct: int, flip: bool, style: str = "cartoon") -> Image.Image:
    """The narrator at scale_pct percent (100 = 1.0), eyes and mouth in place, mirrored when flip."""
    a = load_assets(style)
    base = a.bodies[pose].copy()
    eo, mo = a.manifest["eyes"][eyes]["origin"], a.manifest["mouths"][mouth]["origin"]
    base.alpha_composite(a.eyes[eyes], (eo[0], eo[1]))
    base.alpha_composite(a.mouths[mouth], (mo[0], mo[1]))
    if scale_pct != 100:
        w, h = base.size
        base = base.resize((max(2, round(w * scale_pct / 100)), max(2, round(h * scale_pct / 100))), Image.LANCZOS)
    return base.transpose(Image.FLIP_LEFT_RIGHT) if flip else base


@lru_cache(maxsize=1024)
def faded(pose: str, eyes: str, mouth: str, scale_pct: int, flip: bool, alpha_q: int, style: str = "cartoon") -> Image.Image:
    """The same sprite with its alpha multiplied by alpha_q / 4 (cross-fade frames)."""
    sp = sprite(pose, eyes, mouth, scale_pct, flip, style).copy()
    a = sp.getchannel("A").point(lambda v: (v * alpha_q + 2) // 4)
    sp.putalpha(a)
    return sp
