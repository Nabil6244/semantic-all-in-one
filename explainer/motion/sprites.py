"""Stamp and plate sprites and their animated drawing. Textures come from the prebuilt masks in assets/stamps (checked against manifest.json); a missing or damaged mask means a plain, clean
stamp (never an error). Everything is cached by its parameters; a frame depends only on the item and the time."""

from __future__ import annotations

import hashlib
import io
import json
import zlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw

from ..board import theme as T
from . import presets as P

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "stamps"
TH = T.THEME
INK = {"red": (186, 40, 48), "green": (38, 128, 78), "blue": (44, 84, 170), "gold": (176, 116, 22), "ink": (50, 50, 56)}
TILTS = (-7.0, -5.0, -3.0, 3.0, 4.0, 6.0)
STAMP_PAD_X, STAMP_PAD_Y, STAMP_MAX_W = 56, 26, 900
PLATE_PAD_X, PLATE_PAD_Y, PLATE_MAX_W = 26, 14, 700


class AssetError(Exception):
    pass


@lru_cache(maxsize=1)
def manifest() -> Dict[str, Any]:
    p = ASSET_DIR / "manifest.json"
    try:
        return json.loads(p.read_bytes())
    except (OSError, ValueError) as e:
        raise AssetError(f"stamp manifest.json is missing or unreadable ({e}); rebuild with: python3 -B explainer/motion/build_assets.py")


@lru_cache(maxsize=4)
def _mask(variant: str) -> Image.Image:
    slot = manifest()["masks"][variant]
    f = ASSET_DIR / slot["file"]
    try:
        b = f.read_bytes()
    except OSError as e:
        raise AssetError(f"stamp texture {f.name} is missing ({e})")
    if hashlib.sha256(b).hexdigest() != slot["sha256"] or len(b) != slot["bytes"]:
        raise AssetError(f"stamp texture {f.name} does not match manifest.json")
    return Image.open(io.BytesIO(b)).convert("L")


def available() -> bool:
    try:
        manifest.cache_clear()
        _mask.cache_clear()
        return all(_mask(v) is not None for v in manifest()["masks"])
    except (AssetError, KeyError):
        return False


def _crc(cue_id: str) -> int:
    return zlib.crc32(cue_id.encode("utf-8"))


def tilt_for(cue_id: str) -> float:
    return TILTS[_crc(cue_id) % len(TILTS)]


def variant_for(cue_id: str) -> str:
    return "ab"[(_crc(cue_id) >> 3) % 2]


def _cover(mask: Image.Image, w: int, h: int) -> Image.Image:
    s = max(w / mask.width, h / mask.height)
    m = mask.resize((max(w, round(mask.width * s)), max(h, round(mask.height * s))), Image.LANCZOS)
    x, y = (m.width - w) // 2, (m.height - h) // 2
    return m.crop((x, y, x + w, y + h))


def measure_stamp(text: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    text = " ".join(str(text).upper().split())
    if not text:
        return None
    for px in range(int(params.get("px", 120)), 55, -8):
        f = T.font("title", px)
        tw = int(T.tracked_width(f, text, px * 0.08))
        w = tw + 2 * STAMP_PAD_X
        if w <= STAMP_MAX_W:
            asc, desc = f.getmetrics()
            return {"w": w, "h": asc + desc + 2 * STAMP_PAD_Y, "px": px, "lines": [text]}
    return None


def measure_plate(text: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    text = " ".join(str(text).upper().split())
    if not text:
        return None
    for px in range(int(params.get("px", 40)), 27, -2):
        f = T.font("body", px)
        tw = int(T.tracked_width(f, text, px * 0.12))
        w = tw + 2 * PLATE_PAD_X + 10
        if w <= PLATE_MAX_W:
            asc, desc = f.getmetrics()
            return {"w": w + 6, "h": asc + desc + 2 * PLATE_PAD_Y + 6, "px": px, "lines": [text]}
    return None


@lru_cache(maxsize=48)
def stamp_base(text: str, role: str, w: int, h: int, px: int, variant: str, textured: bool) -> Image.Image:
    """The stamp, flat on a transparent canvas: a double rounded border and the word in tracked capitals, ink worn away by the mask."""
    ss = 2
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    col = INK.get(role, INK["red"]) + (232,)
    d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=20 * ss, outline=col, width=9 * ss)
    d.rounded_rectangle([15 * ss, 15 * ss, (w - 15) * ss - 1, (h - 15) * ss - 1], radius=10 * ss, outline=col, width=3 * ss)
    f = T.font("title", px * ss)
    T.draw_tracked(d, (w * ss / 2, STAMP_PAD_Y * ss), text, f, col, px * 0.08 * ss, anchor="m")
    sp = big.resize((w, h), Image.LANCZOS)
    if textured:
        a = ImageChops.multiply(sp.getchannel("A"), _cover(_mask(variant), w, h))
        sp.putalpha(a)
    return sp


@lru_cache(maxsize=48)
def plate_sprite(text: str, role: str, w: int, h: int, px: int) -> Image.Image:
    ss = 2
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    bw, bh = (w - 6) * ss, (h - 6) * ss
    d.rounded_rectangle([5 * ss, 5 * ss, 5 * ss + bw - 1, 5 * ss + bh - 1], radius=8 * ss, fill=(0, 0, 0, 70))                  # a soft drop shadow
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=8 * ss, fill=TH.paper + (255,), outline=TH.outline + (255,), width=4 * ss)
    d.rounded_rectangle([10 * ss, 12 * ss, 17 * ss, bh - 12 * ss], radius=3 * ss, fill=TH.roles.get(role, TH.roles["blue"]) + (255,))   # a role-coloured tick on the left
    sp = big.resize((w, h), Image.LANCZOS)
    d2 = ImageDraw.Draw(sp)
    f = T.font("body", px)
    T.draw_tracked(d2, (3 + (w - 6) / 2 + 8, PLATE_PAD_Y + 3), text, f, TH.ink, px * 0.12, anchor="m")
    return sp


def _with_alpha(sp: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return sp
    out = sp.copy()
    out.putalpha(sp.getchannel("A").point(lambda v: int(v * alpha)))
    return out


@lru_cache(maxsize=96)
def stamp_frame(text: str, role: str, w: int, h: int, px: int, variant: str, textured: bool, tilt: float, frame: int, sv: int = 0) -> Tuple[Image.Image, Tuple[int, int]]:
    """(sprite, (dx, dy)) for animation frame `frame` (SLAM_FRAMES - 1 is the settled stamp)."""
    scale, alpha, extra, dx, dy = P.slam_frame(frame, sv)
    base = stamp_base(text, role, w, h, px, variant, textured)
    sc = base if abs(scale - 1.0) < 1e-6 else base.resize((max(2, round(w * scale)), max(2, round(h * scale))), Image.BICUBIC)
    rot = sc.rotate(tilt + extra, resample=Image.BICUBIC, expand=True)
    return _with_alpha(rot, alpha), (dx, dy)


def measure_cross(text: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from ..board import styles as ST
    n = int(params.get("size", ST.TILE))
    return {"w": n, "h": n, "px": 0, "lines": []}


@lru_cache(maxsize=32)
def cross_sprite(w: int, h: int, p1: float, p2: float) -> Image.Image:
    """Two red strokes over a w x h picture, the first from top-left to bottom-right and the second from top-right to bottom-left, each drawn to its progress."""
    ss = 3
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    m = int(w * 0.14)
    lines = (((m, m), (w - m, h - m), p1), ((w - m, m), (m, h - m), p2))
    for (a, b, p) in lines:
        if p <= 0:
            continue
        end = (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)
        for wd, col in ((26, (60, 20, 24, 255)), (18, INK["red"] + (255,))):
            d.line([(a[0] * ss, a[1] * ss), (end[0] * ss, end[1] * ss)], fill=col, width=wd * ss)
            for q in (a, end):
                r = wd * ss / 2
                d.ellipse([q[0] * ss - r, q[1] * ss - r, q[0] * ss + r, q[1] * ss + r], fill=col)
    return big.resize((w, h), Image.LANCZOS)


def draw_cross(im: Image.Image, it, age: float) -> None:
    p1, p2 = P.cross_out(age)
    w, h = it.rect[2] - it.rect[0], it.rect[3] - it.rect[1]
    sp = cross_sprite(w, h, round(p1, 3), round(p2, 3))
    im.paste(sp, (it.rect[0], it.rect[1]), sp)


def draw(im: Image.Image, it, age: float) -> None:
    """Draw a motion item (style stamp or plate) centred on its rect."""
    text = it.lines[0] if it.lines else " ".join(str(it.text).upper().split())
    w, h = it.rect[2] - it.rect[0], it.rect[3] - it.rect[1]
    cx, cy = (it.rect[0] + it.rect[2]) // 2, (it.rect[1] + it.rect[3]) // 2
    if it.style == "cross":
        draw_cross(im, it, age)
        return
    if it.style == "stamp":
        textured = available_cached()
        sp, (dx, dy) = stamp_frame(text, it.role, w, h, it.px, variant_for(it.cue_id), textured, tilt_for(it.cue_id), min(P.frame_of(age), P.SLAM_FRAMES - 1), int((it.vparams or {}).get("sv", 0)))
        x, y = cx - sp.width // 2 + dx, cy - sp.height // 2 + dy
        im.paste(sp, (min(max(x, 0), im.width - sp.width), min(max(y, 0), im.height - sp.height)), sp)          # the large approach frames stay whole inside the frame
        return
    dx, dy, alpha = P.plate_motion(age, int((it.vparams or {}).get("pv", 0)))
    sp = _with_alpha(plate_sprite(text, it.role, w, h, it.px), alpha)
    im.paste(sp, (it.rect[0] + dx, it.rect[1] + dy), sp)


_AVAILABLE: Dict[str, bool] = {}


def available_cached() -> bool:
    if "v" not in _AVAILABLE:
        _AVAILABLE["v"] = available()
    return _AVAILABLE["v"]
