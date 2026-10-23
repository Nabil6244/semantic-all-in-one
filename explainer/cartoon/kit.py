"""Loader for the cartoon kit built by explainer/cartoon/build_assets.py. It only READS: every file is checked against manifest.json (SHA-256 and size) before it is used, and a missing,
edited or damaged file is an AssetError that names the build command. Nothing is generated during a render."""

from __future__ import annotations

import hashlib
import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "cartoon"
BUILD_HINT = "rebuild with: python3 -B explainer/cartoon/build_assets.py"
CANVAS_H = 560


class AssetError(Exception):
    pass


def check_file(path: Path, sha256: str, size: int) -> bytes:
    if not path.is_file():
        raise AssetError(f"cartoon asset {path.name} is missing ({BUILD_HINT})")
    b = path.read_bytes()
    if hashlib.sha256(b).hexdigest() != sha256 or len(b) != size:
        raise AssetError(f"cartoon asset {path.name} does not match manifest.json (edited or damaged; {BUILD_HINT})")
    return b


@lru_cache(maxsize=1)
def manifest() -> dict:
    p = ASSET_DIR / "manifest.json"
    if not p.is_file():
        raise AssetError(f"cartoon manifest.json is missing ({BUILD_HINT})")
    try:
        return json.loads(p.read_bytes())
    except ValueError as e:
        raise AssetError(f"cartoon manifest.json is unreadable: {e}")


def sets() -> Tuple[str, ...]:
    return tuple(sorted(manifest()["sets"]))


def problem(style: str, params: Dict) -> str:
    """'' when the visual cue's params name things the kit has; otherwise why not (a cue problem, never a crash)."""
    try:
        m = manifest()
    except AssetError as e:
        return str(e)
    if style == "set":
        if params.get("set") not in m["sets"]:
            return f"unknown set {params.get('set')!r} (available: {', '.join(sorted(m['sets']))})"
        if params.get("tod", "day") not in ("day", "dusk"):
            return f"unknown time of day {params.get('tod')!r} (day or dusk)"
    elif style in ("figure", "crowd"):
        role = params.get("cast", "blue")
        if style == "figure" and role not in m["cast"]:
            return f"unknown cast colour {role!r} (available: {', '.join(m['roles'])})"
        pose = params.get("pose", "idle")
        if style == "figure" and (pose not in m["poses"] or params.get("kit", "a") not in m["cast"]["blue"].get(pose, {})):
            return f"unknown pose or look {pose!r}/{params.get('kit', 'a')!r} (poses: {', '.join(m['poses'])}; looks: a, b, c for idle)"
        if style == "crowd" and not 2 <= int(params.get("n", 6)) <= 14:
            return "a crowd has 2 to 14 figures"
    elif style == "prop":
        if params.get("prop") not in m["props"]:
            return f"unknown prop {params.get('prop')!r} (available: {', '.join(sorted(m['props']))})"
    return ""


def _img(name: str, slot: dict, mode: str) -> Image.Image:
    return Image.open(io.BytesIO(check_file(ASSET_DIR / name, slot["sha256"], slot["bytes"]))).convert(mode)


@lru_cache(maxsize=16)
def set_image(name: str, tod: str = "day") -> Image.Image:
    return _img(f"set_{name}_{tod}.png", manifest()["sets"][name]["tod"][tod], "RGB")


def ground_y(name: str) -> int:
    return int(manifest()["sets"][name]["ground_y"])


@lru_cache(maxsize=96)
def _cast_full(role: str, pose: str, kit: str) -> Image.Image:
    return _img(f"cast_{role}_{pose}_{kit}.png", manifest()["cast"][role][pose][kit], "RGBA")


@lru_cache(maxsize=96)
def cast_sprite(role: str, pose: str, kit: str, height: int, flip: bool) -> Image.Image:
    """The whole 440 x 560 canvas of the figure scaled so that the canvas is `height` tall (the feet are on its bottom edge)."""
    im = _cast_full(role, pose, kit)
    s = height / CANVAS_H
    im = im.resize((max(2, round(im.width * s)), max(2, round(im.height * s))), Image.LANCZOS)
    return im.transpose(Image.FLIP_LEFT_RIGHT) if flip else im


def cast_bbox(role: str, pose: str, kit: str, height: int, flip: bool) -> Tuple[int, int, int, int]:
    return cast_sprite(role, pose, kit, height, flip).getchannel("A").getbbox()


@lru_cache(maxsize=32)
def prop_sprite(name: str, height: int) -> Image.Image:
    im = _img(f"prop_{name}.png", manifest()["props"][name], "RGBA")
    s = height / im.height
    return im.resize((max(2, round(im.width * s)), max(2, round(im.height * s))), Image.LANCZOS)


CROWD_STEP = 0.5            # a crowd figure stands this fraction of a figure's canvas width after the previous one


@lru_cache(maxsize=32)
def crowd_sprite(n: int, height: int, seed: int) -> Image.Image:
    """A row of n small figures, deterministic in (n, height, seed): colours cycle blue, green, red, gold and looks cycle a, b, c, shifted by the seed."""
    roles = ("blue", "green", "red", "gold")
    figs = [cast_sprite(roles[(i + seed) % 4], "idle", "abc"[(i * 2 + seed) % 3], height, bool((i + seed) % 5 == 4)) for i in range(n)]
    step = int(figs[0].width * CROWD_STEP)
    out = Image.new("RGBA", (step * (n - 1) + figs[0].width, height), (0, 0, 0, 0))
    for i, f in enumerate(figs):                       # painted left to right: each figure overlaps the one before
        out.alpha_composite(f, (i * step, 0))
    return out
