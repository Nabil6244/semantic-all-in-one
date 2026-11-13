"""The sticker stage (docs/aviation/MASTER_PLAN.md section 3, step 1): one black stage that builds up across many lines instead of
cutting away. Elements pop / slide / drop in, float slowly while they stay, glide to new places when others arrive, and are pushed
out; the year badge keeps the story's time. A chapter is one Layer of kind `stage.lay_stage` whose params describe every element.

Build (in time order, times in seconds from the layer start):

    st = Stage()
    a = st.add("aircraft", at=0.4, args={"type": "b707", "airline": "msa", "width": 560})      # auto-placed in the row of slots
    st.year(0.4, 1966)
    f1 = st.add("flag", at=2.0, args={"code": "MY"}, enter="slide_left")                    # the row re-lays out, a glides aside
    st.move(a, at=4.0, pos=(640, 470), scale=0.8)                                           # pinned from here on
    st.remove(f1, at=6.0, exit="slide_left")
    st.clear(at=9.0)
    layer_params = st.params()          # JSON-safe dict for Layer("stage.lay_stage", start, end, layer_params)
    st.cues()                           # [(t, sound_name)] for the sound pass (style.SOUNDS)

Render: lay_stage(t, dur, params) -> RGBA W x H (the shared card contract). Each sprite is drawn once (cached by kind + args) and only
moved, scaled (quantised steps, cached) and slightly rotated per frame, so long chapters stay fast.

Sprite kinds: aircraft, flag, hand_flag, bubble, prop, tail, image, text, plus any kind added with register(kind, fn(args) -> RGBA).
A kind that fails or is unknown draws a labelled placeholder card: the stage never crashes and never goes empty.
Positions and widths are in 1280 x 720 units; style.scale() maps them to the real frame size.
"""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from cinematic_explainer.war import motion as M

from . import style as S

W, H = S.W, S.H
ENTERS = ("pop", "slide_left", "slide_right", "drop", "rise", "fade", "none")
EXITS = ("pop", "slide_left", "slide_right", "drop", "fade", "none")
ROW_Y = 380.0

_FACTORIES: Dict[str, Callable[[Dict[str, Any]], Image.Image]] = {}


def register(kind: str, fn: Callable[[Dict[str, Any]], Image.Image]) -> None:
    """Add a sprite kind (e.g. logo cards, split trees). fn(args) -> RGBA, drawn once and cached."""
    _FACTORIES[kind] = fn
    _sprite.cache_clear()
    _scaled.cache_clear()


# ---------------------------------------------------------------------------------------------------------------- layout

def slots(n: int) -> List[Tuple[float, float, float]]:
    """(x, y, scale) for n auto-placed elements in one row, centred; the more there are, the smaller and closer they sit."""
    if n <= 0:
        return []
    sc = {1: 1.0, 2: 0.82, 3: 0.68, 4: 0.56}.get(n, max(0.36, 2.2 / n))
    gap = min(1120.0 / n, 520.0 * sc + 60.0)
    return [(640.0 + (i - (n - 1) / 2.0) * gap, ROW_Y, sc) for i in range(n)]


# ---------------------------------------------------------------------------------------------------------------- builder

class Stage:
    def __init__(self) -> None:
        self._els: List[Dict[str, Any]] = []
        self._years: List[List[Any]] = []
        self._cues: List[Tuple[float, str]] = []
        self._n = 0

    # elements -----------------------------------------------------------------------------------------------------------
    def _get(self, el_id: str) -> Dict[str, Any]:
        for e in self._els:
            if e["id"] == el_id:
                return e
        raise KeyError(el_id)

    def live(self, at: float) -> List[str]:
        return [e["id"] for e in self._els if e["t0"] <= at + 1e-9 and (e["t1"] is None or e["t1"] > at + 1e-9)]

    def add(self, kind: str, at: float, args: Optional[Dict[str, Any]] = None, *, id: Optional[str] = None,
            pos: Optional[Tuple[float, float]] = None, scale: float = 1.0, enter: str = "pop", z: Optional[int] = None,
            edge: Optional[bool] = None, float_: bool = True, anim: float = 0.0) -> str:
        """Add an element at `at`. Without pos it joins the auto row (slots) and the others glide to make room."""
        self._n += 1
        el_id = id or f"{kind}{self._n}"
        if edge is None:
            edge = kind in ("aircraft", "flag", "hand_flag", "prop", "tail", "image")
        e = {"id": el_id, "kind": kind, "args": dict(args or {}), "t0": float(at), "t1": None,
             "enter": enter if enter in ENTERS else "pop", "exit": "fade", "z": self._n if z is None else int(z),
             "edge": bool(edge), "float": bool(float_), "base": float(scale), "slot": pos is None, "keys": [],
             "anim": float(anim)}
        if pos is not None:
            e["keys"].append([float(at), float(pos[0]), float(pos[1]), float(scale), 0.0])
        self._els.append(e)
        self._relayout(at, new=el_id)
        self._cues.append((float(at), S.SOUNDS.get(e["enter"].split("_")[0], "")))
        return el_id

    def move(self, el_id: str, at: float, pos: Optional[Tuple[float, float]] = None, scale: Optional[float] = None,
             dur: float = S.MOVE_S) -> None:
        """Glide an element to pos / scale; a moved element leaves the auto row and stays where it was put."""
        e = self._get(el_id)
        x, y, s = _key_at(e["keys"], at) if e["keys"] else (640.0, ROW_Y, e["base"])
        nx, ny = pos if pos is not None else (x, y)
        e["keys"].append([float(at), float(nx), float(ny), float(scale if scale is not None else s), float(dur)])
        if e["slot"]:
            e["slot"] = False
            self._relayout(at)

    def remove(self, el_id: str, at: float, exit: str = "fade") -> None:
        e = self._get(el_id)
        if e["t1"] is not None:
            return
        e["t1"] = float(at)
        e["exit"] = exit if exit in EXITS else "fade"
        self._cues.append((float(at), S.SOUNDS["exit"] if exit.startswith("slide") else ""))
        if e["slot"]:
            self._relayout(at)

    def clear(self, at: float, exit: str = "slide_left", keep: Sequence[str] = ()) -> None:
        for el_id in self.live(at):
            if el_id in keep or self._get(el_id)["kind"] == "backdrop":     # the photo behind the stage stays
                continue
            e = self._get(el_id)
            e["t1"] = float(at)
            e["exit"] = exit if exit in EXITS else "fade"
        self._cues.append((float(at), S.SOUNDS["exit"]))

    def year(self, at: float, year: Any) -> None:
        y = str(year).strip()
        if not y or (self._years and self._years[-1][1] == y):
            return
        self._years.append([float(at), y])
        self._cues.append((float(at), S.SOUNDS["year"]))

    def _relayout(self, at: float, new: Optional[str] = None) -> None:
        row = [self._get(i) for i in self.live(at)]
        row = [e for e in row if e["slot"]]
        for e, (x, y, s) in zip(row, slots(len(row))):
            target = [float(at), x, y, s * e["base"], S.MOVE_S]
            if e["id"] == new or not e["keys"]:
                target[4] = 0.0
                e["keys"].append(target)
            elif _key_at(e["keys"], 1e9) != (x, y, s * e["base"]):
                e["keys"].append(target)

    # output -------------------------------------------------------------------------------------------------------------
    def params(self) -> Dict[str, Any]:
        return {"elements": [dict(e, keys=[list(k) for k in e["keys"]]) for e in self._els],
                "years": [list(y) for y in self._years]}

    def cues(self) -> List[Tuple[float, str]]:
        return sorted((t, s) for t, s in self._cues if s)


# ---------------------------------------------------------------------------------------------------------------- motion maths

def _key_at(keys: Sequence[Sequence[float]], t: float) -> Tuple[float, float, float]:
    """Position / scale at t: each key glides from the previous resting place over its own length (0 = jump)."""
    x, y, s = keys[0][1], keys[0][2], keys[0][3]
    for k in keys[1:]:
        if k[0] > t:
            break
        f = 1.0 if k[4] <= 0 else M.ease_in_out(M.clamp01((t - k[0]) / k[4]))
        x, y, s = M.lerp(x, k[1], f), M.lerp(y, k[2], f), M.lerp(s, k[3], f)
    return x, y, s


def _back_out(k: float) -> float:
    k = M.clamp01(k)
    c = 1.9
    return 1 + (c + 1) * (k - 1) ** 3 + c * (k - 1) ** 2


def transform(e: Dict[str, Any], t: float) -> Optional[Tuple[float, float, float, float, float]]:
    """(x, y, scale, rotation_deg, alpha) of an element at t, or None when it is not on screen."""
    if t < e["t0"] or not e["keys"]:
        return None
    t1 = e.get("t1")
    if t1 is not None and t >= t1 + S.EXIT_S:
        return None
    x, y, s = _key_at(e["keys"], t)
    rot, alpha = 0.0, 1.0
    if e.get("float", True):
        ph = (int(hashlib.md5(e["id"].encode()).hexdigest()[:6], 16) % 628) / 100.0
        y += S.FLOAT_PX * math.sin(2 * math.pi * t / S.FLOAT_S + ph)
        rot = S.FLOAT_DEG * math.sin(2 * math.pi * t / (S.FLOAT_S * 1.3) + ph)
    k = (t - e["t0"]) / S.ENTER_S
    if k < 1:
        how = e.get("enter", "pop")
        if how == "pop":
            s *= max(0.0, _back_out(k))
            alpha = M.clamp01(k * 2.5)
        elif how in ("slide_left", "slide_right"):
            d = -1 if how == "slide_left" else 1
            x += d * 900.0 * (1 - M.ease_out(M.clamp01(k)))
            rot += d * -6.0 * (1 - M.clamp01(k))
        elif how == "drop":
            y -= 420.0 * (1 - _back_out(k))
        elif how == "rise":
            y += 420.0 * (1 - M.ease_out(M.clamp01(k)))
        elif how == "fade":
            alpha = M.clamp01(k)
    if t1 is not None and t >= t1:
        q = M.clamp01((t - t1) / S.EXIT_S)
        how = e.get("exit", "fade")
        if how == "pop":
            s *= 1 - M.ease_in_out(q)
        elif how in ("slide_left", "slide_right"):
            x += (-1 if how == "slide_left" else 1) * 1000.0 * (q * q)
        elif how == "drop":
            y += 600.0 * q * q
        elif how == "none":
            return None
        alpha *= 1 - q if how in ("fade", "pop") else 1.0
    for h in e.get("hide") or []:                 # a re-hook / callback beat: out for a moment, then back where it was
        ha, hb = float(h[0]), float(h[1])
        if ha <= t < hb:
            q = M.clamp01((t - ha) / S.EXIT_S)
            if q >= 1:
                return None
            x -= 1000.0 * q * q
        elif hb <= t < hb + S.ENTER_S:
            s *= max(0.0, _back_out((t - hb) / S.ENTER_S))
    if s <= 0.01 or alpha <= 0.01:
        return None
    return x, y, s, rot, alpha


# ---------------------------------------------------------------------------------------------------------------- sprites

def _fallback_die_cut(img: Image.Image, edge: int) -> Image.Image:
    pad = edge + S.SHADOW_BLUR * 2 + max(S.SHADOW_OFFSET)
    w, h = img.size
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    a = Image.new("L", out.size, 0)
    a.paste(img.getchannel("A"), (pad, pad))
    rim = a.filter(ImageFilter.MaxFilter(edge * 2 + 1)) if edge > 0 else a
    sh = rim.filter(ImageFilter.GaussianBlur(S.SHADOW_BLUR)).point(lambda v: v * S.SHADOW_ALPHA // 255)
    out.paste((0, 0, 0, 255), S.SHADOW_OFFSET, sh)
    out.paste(S.WHITE, (0, 0), rim)
    out.alpha_composite(img, (pad, pad))
    return out


def _shadow_only(img: Image.Image) -> Image.Image:
    return _fallback_die_cut(img, 0)


def _placeholder(label: str, width: int = 360) -> Image.Image:
    h = int(width * 0.6)
    im = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, width - 1, h - 1), radius=28, fill=(44, 46, 54, 255))
    f = S.font("body", 30)
    tw = d.textlength(label, font=f)
    d.text(((width - tw) / 2, h / 2 - 18), label, font=f, fill=S.WHITE)
    return im


def _text_sprite(a: Dict[str, Any]) -> Image.Image:
    text = str(a.get("text", "")).strip() or " "
    f = S.font(a.get("role", "title"), int(a.get("size", 72)))
    col = tuple(a.get("color", S.WHITE))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = text.split("\n")
    wmax = max(probe.textlength(ln, font=f) for ln in lines)
    lh = int(f.size * 1.15)
    im = Image.new("RGBA", (int(wmax) + 8, lh * len(lines) + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, ln in enumerate(lines):
        d.text((4 + (wmax - d.textlength(ln, font=f)) / 2, 4 + i * lh), ln, font=f, fill=col)
    return im


def _image_sprite(a: Dict[str, Any]) -> Image.Image:
    im = Image.open(a["path"]).convert("RGBA")
    w = int(a.get("width", 520))
    return im.resize((w, max(1, int(im.height * w / im.width))), Image.LANCZOS)


def _sticker_kit():
    from . import stickers  # built in step 3; the stage falls back to placeholders until it exists
    return stickers


KIND_MODULES = ("storycards", "story_relations", "story_maps", "story_cards2", "gfx_sticker")


def load_kinds() -> None:
    """Import every module that registers stage kinds (a render worker starts with none). Missing modules are skipped."""
    import importlib
    for m in KIND_MODULES:
        try:
            importlib.import_module(f"{__package__}.{m}")
        except ImportError:
            pass


def _make(kind: str, a: Dict[str, Any]) -> Image.Image:
    if kind not in _FACTORIES:
        load_kinds()
    if kind in _FACTORIES:
        return _FACTORIES[kind](a)
    if kind == "text":
        return _text_sprite(a)
    if kind == "image":
        return _image_sprite(a)
    k = _sticker_kit()
    if kind == "aircraft":                       # the Flow sticker from the library when made, else the code-drawn one
        from . import sticker_flow as SF
        return SF.aircraft_image(a.get("type", ""), a.get("airline", ""), int(a.get("width", 560)), a.get("era", ""))
    if kind == "flag":
        return k.flag(a.get("code", ""), int(a.get("width", 240)))
    if kind == "hand_flag":
        return k.hand_flag(a.get("code", ""), int(a.get("width", 260)), a.get("side", "left"))
    if kind == "bubble":
        return k.bubble(a.get("text", ""), int(a.get("width", 520)), tuple(a.get("bold", ())), a.get("tail", "left"))
    if kind == "prop":
        return k.prop(a.get("name", ""), int(a.get("size", 220)))
    if kind == "tail":
        return k.tail_mark(a.get("airline", ""), int(a.get("size", 160)))
    raise KeyError(kind)


def _key(e: Dict[str, Any]) -> str:
    return json.dumps([e["kind"], e.get("args", {}), bool(e.get("edge"))], sort_keys=True, default=str)


@lru_cache(maxsize=256)
def _sprite(key: str) -> Image.Image:
    kind, a, edge = json.loads(key)
    try:
        im = _make(kind, a).convert("RGBA")
    except Exception:
        im = _placeholder(str(a.get("label") or a.get("text") or a.get("type") or a.get("code") or kind)[:18])
    if edge:
        try:
            im = _sticker_kit().die_cut(im, S.EDGE)
        except Exception:
            im = _fallback_die_cut(im, S.EDGE)
    elif kind not in NO_SHADOW and not a.get("_flat"):      # cards, bubbles, type: a soft shadow lifts them off the stage
        im = _shadow_only(im)
    return im


@lru_cache(maxsize=1024)
def _scaled(key: str, q: int) -> Image.Image:
    base = _sprite(key)
    f = q / 50.0
    w, h = max(1, int(base.width * f)), max(1, int(base.height * f))
    return base if (w, h) == base.size else base.resize((w, h), Image.BILINEAR)


ANIM_STEPS = 24
NO_SHADOW = ("timeline_bar", "timeline_dot", "caption", "backdrop", "photo_full")


def anim_k(e: Dict[str, Any], t: float) -> Optional[float]:
    """Progress 0..1 of an animated element (anim = seconds after it enters, anim_delay = wait), quantised to ANIM_STEPS so
    each step is drawn once. None for a static element."""
    dur = float(e.get("anim") or 0)
    if dur <= 0:
        return None
    k = M.clamp01((t - e["t0"] - float(e.get("anim_delay", S.ENTER_S * 0.5))) / dur)
    return round(k * ANIM_STEPS) / ANIM_STEPS


def sprite(e: Dict[str, Any], scale: float, k: Optional[float] = None) -> Image.Image:
    """The element's sprite at a scale quantised to 2 % steps (cached), in real frame pixels. An animated kind gets its progress
    as args['_k'] (0..1): its factory draws that moment (a name being written, bars growing, a tree branching)."""
    key = _key(e) if k is None else _key(dict(e, args=dict(e.get("args", {}), _k=k)))
    return _scaled(key, max(1, int(round(scale * S.scale() * 50))))


# ---------------------------------------------------------------------------------------------------------------- render

@lru_cache(maxsize=4)
def _background(w: int, h: int) -> Image.Image:
    bg = Image.new("RGBA", (w, h), S.STAGE_BG)
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse((w * 0.12, h * 0.05, w * 0.88, h * 1.05), fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.12))
    bg.paste(S.STAGE_LIFT, (0, 0), glow.point(lambda v: v * 120 // 255))
    return bg


def _paste(canvas: Image.Image, im: Image.Image, cx: float, cy: float, rot: float, alpha: float) -> None:
    if abs(rot) >= 0.1:
        im = im.rotate(round(rot * 5) / 5.0, resample=Image.BICUBIC, expand=True)
    if alpha < 0.999:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    x0, y0 = int(round(cx - im.width / 2)), int(round(cy - im.height / 2))
    sx0, sy0 = max(0, -x0), max(0, -y0)
    sx1, sy1 = min(im.width, canvas.width - x0), min(im.height, canvas.height - y0)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    if (sx0, sy0, sx1, sy1) != (0, 0, im.width, im.height):
        im = im.crop((sx0, sy0, sx1, sy1))
    canvas.alpha_composite(im, (x0 + sx0, y0 + sy0))


def badge_digits(years: Sequence[Sequence[Any]], t: float) -> Tuple[str, str, float]:
    """(previous year, current year, roll 0..1) of the year badge at t."""
    prev, cur, since = "", "", -1e9
    for at, y in years:
        if at > t:
            break
        prev, cur, since = cur, str(y), float(at)
    return prev, cur, M.clamp01((t - since) / 0.38) if prev else 1.0


def _draw_badge(canvas: Image.Image, years: Sequence[Sequence[Any]], t: float) -> None:
    prev, cur, k = badge_digits(years, t)
    if not cur:
        return
    sc = S.scale()
    f = S.font("badge", 44)
    sp = 0.55
    d = ImageDraw.Draw(canvas)
    from cinematic_explainer import look as L
    tw = L.spaced_width(d, cur, f, sp)
    bw, bh = tw + 44 * sc, 70 * sc
    x1, y0 = W - 48 * sc, 40 * sc
    x0 = x1 - bw
    box = Image.new("RGBA", (int(bw), int(bh)), (0, 0, 0, 0))
    ImageDraw.Draw(box).rounded_rectangle((0, 0, bw - 1, bh - 1), radius=int(10 * sc), fill=S.NAVY)
    bd = ImageDraw.Draw(box)
    tx = 22 * sc
    ty = (bh - f.size) / 2 - 4 * sc
    e = M.ease_out(k)
    for i, ch in enumerate(cur):
        old = prev[i] if i < len(prev) else ""
        cw = bd.textlength(ch, font=f) + f.size * sp
        if old and old != ch and k < 1:
            bd.text((tx, ty - e * bh), old, font=f, fill=S.WHITE)
            bd.text((tx, ty + (1 - e) * bh), ch, font=f, fill=S.YELLOW if k < 0.9 else S.WHITE)
        else:
            bd.text((tx, ty), ch, font=f, fill=S.WHITE)
        tx += cw
    canvas.alpha_composite(box, (int(x0), int(y0)))


def lay_stage(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    t = t + float(p.get("t_offset", 0.0))           # a stage split around a full-screen clip resumes on its own clock
    els = p.get("elements") or []
    years = p.get("years") or []
    if not els and not years:
        return None
    canvas = _background(W, H).copy()
    sc = S.scale()
    order = sorted(els, key=lambda e: (e.get("z", 0)))
    for e in order:
        tr = transform(e, t)
        if tr is None:
            continue
        x, y, s, rot, alpha = tr
        _paste(canvas, sprite(e, s, anim_k(e, t)), x * sc, y * sc, rot, alpha)
    _draw_badge(canvas, years, t)
    return canvas
