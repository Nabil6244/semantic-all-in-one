"""War Documentary kit cards: the editorial "sticker" layer (tags, stamps, note chips, recap labels, pictograms, section ribbon, big numbers,
scale diagrams, provenance badge, film grain). Every card is fn(t, dur, params) -> RGBA 1280x720 (a pure function of t and params), the same
contract as cards.WAR_CARDS; KIT_CARDS maps layer kind -> function and registry.all_cards() imports it lazily.

Rules: nothing here states a fact. Text comes from the planner (narration-derived), status colours reuse tokens.STATUS_COLOUR semantics, and
anything that is a drawn picture of a thing (pictograms, scale diagrams) is labelled ILLUSTRATIVE. A missing or odd param never raises.
Cards are readable over bright and dark footage (a plate or soft shadow behind every element) and keep inside the frame.

PARAMS (all optional unless marked *; colours are (r,g,b[,a]) tuples; x/y are fractions of the frame):

kit_tag      text*  sub ""  pos "top-left"|"top-centre"|"top-right"|"lower-left"  size 34  tilt -1.5
             Yellow tilted label, 1-2 lines, wipes in from the left. `sub` is a smaller line inside the tag.
kit_stamp    text (default = status label)  status "unverified"|"claimed"|"disputed"|"illustrative"  sub ""
             pos "centre"|"left"|"right"|"upper-right"|"upper-left" or x,y   angle -6   size 54
             Outlined rotated stamp that slams in with a small overshoot.
kit_chips    chips*[{title, sub, variant "dark"|"red"|"blue"|"paper"}] (1-4)  side "right"|"left"  y 64  width 300  step 0.35
             Stack of note chips revealed one by one from the side.
kit_recap    items*[str | {text, sub}] (3-5)  title ""  step 0.4
             Stacked, slightly rotated paper labels (red outline) in the middle of the frame, with an optional yellow tag above.
kit_sticker  name* (stickers.NAMES)  x 0.5  y 0.5  size 170  colour accent  label ""  label_style "tape"|"tag"
             Pictogram that pops in, with an optional tape label under it. Always drawn flat/generic: it is an illustration, not a depiction.
kit_ribbon   text*  colour "red"|"yellow"|"ink"  angle -8
             Torn-paper section ribbon: slides across (0.45 s), holds, slides out. Fully transparent at t=0 and at t=dur.
kit_bignum   value*  (int, "46,000+", "≈26,000" ...)  label  sub  colour "yellow"|"red"|"cream"  x 0.06  y 0.42  count true
             Huge counted number with label and sub line over a soft left scrim; sits on dimmed footage or a map.
kit_scale    n* (pictograms, max 20)  label ""  bar_label ""  bar "pipe"|"bar"  colour
             Row of generic soldier pictograms standing against a labelled bar (scale diagram); carries an ILLUSTRATIVE chip.
kit_badge    kind "ai"|"illustrative"|"archive"|"user" or text  channel ""
             Small bottom-right provenance badge; `channel` adds a bottom-left text mark (never a logo).
kit_grain    strength 0.05  vignette 0.35
             Deterministic film grain + vignette (8 grain frames cycled), very low alpha.
"""

from __future__ import annotations

import json
import math
import random
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .. import look as L
from . import motion as M
from . import stickers as S
from . import tokens as T

W, H = T.W, T.H
YELLOW = (255, 213, 0, 255)
INK = (22, 22, 26, 255)
KRED = (214, 36, 44, 255)
PAPER = (244, 239, 228, 255)
GLASS = (14, 18, 26, 228)
_D = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
_CACHE: Dict[str, Any] = {}


# ------------------------------------------------------------------------------------------------ helpers -------------------------

def _memo(key: str, build: Callable[[], Any]) -> Any:
    v = _CACHE.get(key)
    if v is None:
        if len(_CACHE) > 160:
            _CACHE.clear()
        v = _CACHE[key] = build()
    return v


def _key(kind: str, p: dict, *names: str) -> str:
    return kind + json.dumps({n: (p or {}).get(n) for n in names}, sort_keys=True, default=str)


def _canvas() -> Image.Image:
    return L.blank()


def _sw(text: str, f, sp: float = 0.04) -> float:
    return L.spaced_width(_D, text, f, sp)


def _wrap(text: str, f, width: int, sp: float = 0.04, max_lines: int = 2) -> List[str]:
    lines: List[str] = []
    cur = ""
    for w in str(text).split():
        trial = (cur + " " + w).strip()
        if cur and _sw(trial, f, sp) > width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        keep = lines[:max_lines]
        keep[-1] = _fit(" ".join(lines[max_lines - 1:]), f, width, sp)
        lines = keep
    return lines or [""]


def _fit(text: str, f, width: int, sp: float = 0.04) -> str:
    text = str(text)
    if _sw(text, f, sp) <= width:
        return text
    while text and _sw(text + "…", f, sp) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _ease_back(x: float) -> float:
    x = M.clamp01(x)
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def _num(v: Any, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _col(c: Any, default) -> Tuple[int, int, int, int]:
    try:
        c = tuple(int(x) for x in c)
        return (c[0], c[1], c[2], c[3] if len(c) > 3 else 255)  # type: ignore[return-value]
    except Exception:
        return default


def _shadowed(im: Image.Image, blur: int = 6, off: Tuple[int, int] = (0, 4), alpha: int = 120) -> Image.Image:
    """The element with a soft drop shadow (a plate that keeps it readable on bright footage); grows by a padding on every side."""
    pad = blur * 3
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    a = im.getchannel("A").point(lambda v: v * alpha // 255)
    sh.paste((0, 0, 0, 255), (pad + off[0], pad + off[1]), a)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(sh)
    out.alpha_composite(im, (pad, pad))
    return out


def _blit(canvas: Image.Image, im: Image.Image, x: int, y: int) -> None:
    """alpha_composite im at (x, y), clipped to the canvas."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(canvas.width, x + im.width), min(canvas.height, y + im.height)
    if x1 <= x0 or y1 <= y0:
        return
    canvas.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def _place(canvas: Image.Image, im: Image.Image, cx: float, cy: float, angle: float = 0.0, scale: float = 1.0, alpha: float = 1.0) -> None:
    """Draw im centred on (cx, cy), optionally scaled and rotated (counter-clockwise degrees), with an overall alpha."""
    if alpha <= 0.003 or scale <= 0.01:
        return
    if abs(scale - 1.0) > 0.004:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BICUBIC)
    if abs(angle) > 0.01:
        im = im.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 0.999:
        im = L.fade(im, alpha)
    _blit(canvas, im, int(round(cx - im.width / 2)), int(round(cy - im.height / 2)))


def _rotated_cache(key: str, im: Image.Image, angle: float) -> Image.Image:
    return _memo(key, lambda: im.rotate(angle, resample=Image.BICUBIC, expand=True))


def _out_alpha(t: float, dur: float) -> float:
    return M.card_alpha(t, dur)


# ------------------------------------------------------------------------------------------------ tag -------------------------------

def _hook_element(text: str, size: int, max_w: int) -> Image.Image:
    """The reference look for a short hook phrase: white label, thick red border, dark type (REFERENCE_PATTERNS item 14)."""
    f = T.font("display", size)
    padx, pady, bd = 20, 10, 4
    lines = _wrap(text.upper(), f, max_w - 2 * padx, 0.06, 2)
    lh = int(size * 1.02)
    w = int(max(_sw(ln, f, 0.06) for ln in lines)) + 2 * padx
    h = lh * len(lines) + 2 * pady
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=5, fill=(214, 36, 52, 255))
    d.rounded_rectangle([bd, bd, w - 1 - bd, h - 1 - bd], radius=3, fill=(250, 248, 244, 255))
    y = pady - 2
    for ln in lines:
        L.spaced(d, (padx, y), ln, f, (196, 30, 46, 255), 0.06)
        y += lh
    return im


def _tag_element(text: str, sub: str, size: int, max_w: int) -> Image.Image:
    f = T.font("display", size)
    padx, pady = 22, 11
    lines = _wrap(text.upper(), f, max_w - 2 * padx, 0.05, 2)
    fs = T.font("bold", max(15, int(size * 0.5)))
    subtxt = _fit(sub.upper(), fs, max_w - 2 * padx, 0.06) if sub else ""
    lh = int(size * 1.02)
    w = int(max(_sw(ln, f, 0.05) for ln in lines)) + 2 * padx
    if subtxt:
        w = max(w, int(_sw(subtxt, fs, 0.06)) + 2 * padx)
    h = lh * len(lines) + 2 * pady + (int(fs.size * 1.5) if subtxt else 0)
    im = Image.new("RGBA", (w, h + 3), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 3, w - 1, h + 2], radius=4, fill=(176, 142, 0, 255))      # darker lower edge: a thick sticker
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=4, fill=YELLOW)
    y = pady - 2
    for ln in lines:
        L.spaced(d, (padx, y), ln, f, INK, 0.05)
        y += lh
    if subtxt:
        L.spaced(d, (padx, y + 1), subtxt, fs, (60, 56, 30, 255), 0.06)
    return im


def kit_tag(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    text = str((p or {}).get("text") or "").strip()
    if not text:
        return None
    size = int(_num(p.get("size"), 34))
    hook = str(p.get("style") or "") == "hook" and not p.get("sub")
    tilt = _num(p.get("tilt"), -3.0 if hook else -1.5)
    build = (lambda: _hook_element(text, size, int(W * 0.56))) if hook else (lambda: _tag_element(text, str(p.get("sub") or ""), size, int(W * 0.62)))
    el = _memo(_key("tag", p, "text", "sub", "size", "tilt", "style"), lambda: _shadowed(_rotated_cache("tagr" + text + str(size) + str(tilt) + str(p.get("sub")) + str(hook), build(), tilt), 5, (0, 4), 110))
    k = M.ease_out(t / 0.42)
    cw = max(1, int(el.width * k))
    part = el.crop((0, 0, cw, el.height))
    pos = str(p.get("pos") or "top-left")
    top = 52
    if pos == "top-centre":
        x = (W - el.width) // 2
    elif pos == "top-right":
        x = W - T.MARGIN_X - el.width + 12
    else:
        x = T.MARGIN_X - 12
    y = top if pos != "lower-left" else int(H * 0.77) - el.height
    img = _canvas()
    _blit(img, part, x - int(26 * (1 - k)), y)
    return L.fade(img, _out_alpha(t, dur) if dur > 0 else 1.0)


# ------------------------------------------------------------------------------------------------ stamp -----------------------------

_STAMP_COL = {"unverified": (232, 64, 58, 255), "claimed": (255, 200, 40, 255), "disputed": (244, 148, 40, 255), "illustrative": (196, 206, 220, 255)}
_STAMP_TXT = {"unverified": "CAN'T BE VERIFIED", "claimed": "CLAIMED", "disputed": "DISPUTED", "illustrative": "ILLUSTRATIVE"}
_STAMP_POS = {"centre": (0.5, 0.5), "left": (0.3, 0.5), "right": (0.7, 0.5), "upper-right": (0.72, 0.3), "upper-left": (0.28, 0.3)}


def _stamp_element(text: str, sub: str, colour, size: int) -> Image.Image:
    f = T.font("display", size)
    fs = T.font("bold", max(15, int(size * 0.34)))
    padx, pady = 30, 14
    tw = int(_sw(text, f, 0.07))
    sw = int(_sw(sub.upper(), fs, 0.08)) if sub else 0
    w = max(tw, sw) + 2 * padx
    h = int(size * 1.0) + 2 * pady + (int(fs.size * 1.5) if sub else 0)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=8, fill=(10, 12, 16, 150), outline=colour, width=5)
    d.rounded_rectangle([9, 9, w - 10, h - 10], radius=4, outline=colour[:3] + (200,), width=2)
    L.spaced(d, ((w - tw) // 2, pady - 2), text, f, colour, 0.07)
    if sub:
        L.spaced(d, ((w - sw) // 2, pady + int(size * 0.98)), sub.upper(), fs, colour[:3] + (230,), 0.08)
    return im


def kit_stamp(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    st = str(p.get("status") or "unverified").lower()
    st = st if st in _STAMP_COL else "unverified"
    text = str(p.get("text") or _STAMP_TXT[st]).upper()
    angle = _num(p.get("angle"), -6.0)
    size = int(_num(p.get("size"), 54))
    el = _memo(_key("stamp", p, "text", "sub", "status", "size", "angle"), lambda: _shadowed(_rotated_cache("stampr" + text + st + str(size) + str(angle) + str(p.get("sub")), _stamp_element(text, str(p.get("sub") or ""), _STAMP_COL[st], size), angle), 5, (0, 3), 120))
    fx, fy = _STAMP_POS.get(str(p.get("pos") or "centre"), (0.5, 0.5))
    fx, fy = _num(p.get("x"), fx), _num(p.get("y"), fy)
    k = M.clamp01(t / 0.24)
    scale = 1.0 + 0.7 * (1.0 - _ease_back(k))
    img = _canvas()
    _place(img, el, W * fx, H * fy, 0.0, scale, M.ramp(t, 0.0, 0.1) * (_out_alpha(t, dur) if dur > 0 else 1.0))
    return img


# ------------------------------------------------------------------------------------------------ chips ----------------------------

_CHIP_STYLE = {
    "dark": {"fill": GLASS, "line": (98, 108, 128, 255), "title": T.CREAM, "sub": T.CREAM_DIM},
    "red": {"fill": (206, 38, 48, 246), "line": (150, 22, 30, 255), "title": (255, 255, 255, 255), "sub": (255, 224, 224, 255)},
    "blue": {"fill": (38, 92, 176, 246), "line": (24, 64, 132, 255), "title": (255, 255, 255, 255), "sub": (214, 228, 250, 255)},
    "paper": {"fill": PAPER, "line": (190, 182, 166, 255), "title": INK, "sub": (78, 74, 66, 255)},
}


def _chip_element(title: str, sub: str, variant: str, width: int) -> Image.Image:
    st = _CHIP_STYLE.get(variant, _CHIP_STYLE["dark"])
    ft = T.font("bold", 20)
    fs = T.font("regular", 17)
    inner = width - 32
    tl = _wrap(title.upper(), ft, inner, 0.04, 2)
    sl = _wrap(sub, fs, inner, 0.0, 3) if sub else []
    h = 14 + 25 * len(tl) + (6 + 22 * len(sl) if sl else 0) + 14
    im = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, width - 1, h - 1], radius=9, fill=st["fill"], outline=st["line"], width=1)
    y = 14
    for ln in tl:
        L.spaced(d, (16, y), ln, ft, st["title"], 0.04)
        y += 25
    y += 6
    for ln in sl:
        d.text((16, y), ln, font=fs, fill=st["sub"])
        y += 22
    return _shadowed(im, 5, (0, 4), 110)


def kit_chips(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    chips = [c for c in (p.get("chips") or []) if isinstance(c, dict) and str(c.get("title") or "").strip()][:4]
    if not chips:
        return None
    width = int(_num(p.get("width"), 300))
    step = _num(p.get("step"), 0.35)
    side = str(p.get("side") or "right")
    y = int(_num(p.get("y"), 64))
    els = [_memo(_key("chip", c, "title", "sub", "variant") + str(width), lambda c=c: _chip_element(str(c.get("title")), str(c.get("sub") or ""), str(c.get("variant") or "dark"), width)) for c in chips]
    pad = 15
    total = sum(e.height - 2 * pad for e in els)
    gap = 12 if total + 12 * (len(els) - 1) + y <= T.LOWER_ZONE_Y - 12 else 4
    img = _canvas()
    ob = _out_alpha(t, dur) if dur > 0 else 1.0
    for i, e in enumerate(els):
        k = M.ease_out((t - T.IN_S * 0.0 - i * step) / 0.34)
        if k > 0:
            slide = int(70 * (1 - k)) * (1 if side == "right" else -1)
            x = (W - T.MARGIN_X - width - pad + slide) if side == "right" else (T.MARGIN_X - pad + slide)
            _blit(img, L.fade(e, k * ob), x, y - pad)
        y += e.height - 2 * pad + gap
    return img


# ------------------------------------------------------------------------------------------------ recap ---------------------------

def _recap_element(text: str, sub: str, max_w: int) -> Image.Image:
    f = T.font("display", 42)
    fs = T.font("bold", 18)
    padx, pady = 28, 10
    line = _fit(text.upper(), f, max_w - 2 * padx, 0.06)
    sline = _fit(sub, fs, max_w - 2 * padx, 0.04) if sub else ""
    w = max(int(_sw(line, f, 0.06)), int(_sw(sline, fs, 0.04)) if sline else 0) + 2 * padx
    h = 46 + 2 * pady + (22 if sline else 0)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=5, fill=PAPER, outline=KRED, width=4)
    L.spaced(d, (padx, pady - 1), line, f, KRED, 0.06)
    if sline:
        L.spaced(d, (padx, pady + 44), sline, fs, (96, 70, 62, 255), 0.04)
    return im


def kit_recap(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    raw = p.get("items") or []
    items = []
    for it in raw[:5]:
        if isinstance(it, dict):
            tx, sb = str(it.get("text") or "").strip(), str(it.get("sub") or "")
        else:
            tx, sb = str(it or "").strip(), ""
        if tx:
            items.append((tx, sb))
    if not items:
        return None
    step = _num(p.get("step"), 0.4)
    title = str(p.get("title") or "").strip()
    angles = (-2.0, 1.4, -1.0, 1.8, -1.6)
    els = [_memo("recap" + tx + "|" + sb + str(i), lambda tx=tx, sb=sb, i=i: _shadowed(_rotated_cache("recapr" + tx + sb + str(i), _recap_element(tx, sb, int(W * 0.78)), angles[i]), 5, (0, 4), 120))
           for i, (tx, sb) in enumerate(items)]
    tag = _memo(_key("recaptag", p, "title"), lambda: _shadowed(_rotated_cache("recaptr" + title, _tag_element(title, "", 34, int(W * 0.6)), -1.5), 5, (0, 4), 110)) if title else None
    pad = 15
    gap = 6
    heights = [e.height - 2 * pad for e in els]
    total = sum(heights) + gap * (len(els) - 1) + ((tag.height - 2 * pad + 14) if tag else 0)
    y = (H - total) // 2
    img = _canvas()
    ob = _out_alpha(t, dur) if dur > 0 else 1.0
    if tag is not None:
        k = M.ease_out(t / 0.3)
        _place(img, tag, W / 2, y + (tag.height - 2 * pad) / 2, 0, 1.0, k * ob)
        y += tag.height - 2 * pad + 14
    for i, e in enumerate(els):
        k = M.ease_out((t - 0.2 - i * step) / 0.3)
        if k > 0:
            _place(img, e, W / 2 + (1 - k) * 36 * (1 if i % 2 else -1), y + heights[i] / 2, 0, 1.0 + 0.12 * (1 - k), k * ob)
        y += heights[i] + gap
    return img


# ------------------------------------------------------------------------------------------------ sticker + tape -------------------

def _tape_element(text: str, style: str) -> Image.Image:
    f = T.font("display", 28)
    padx, pady = 22, 8
    tw = int(_sw(text.upper(), f, 0.06))
    w, h = tw + 2 * padx, 28 + 2 * pady
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if style == "tag":
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=4, fill=YELLOW)
        ink = INK
    else:
        tape = (224, 184, 96, 255)
        rnd = random.Random(w * 31 + len(text))
        top = [(0, 0)] + [(x, rnd.randint(0, 3)) for x in range(8, w, 8)] + [(w, 0)]
        bot = [(w, h)] + [(x, h - rnd.randint(0, 3)) for x in range(w - 8, 0, -8)] + [(0, h)]
        d.polygon(top + bot, fill=tape)
        ink = (60, 44, 20, 255)
    L.spaced(d, (padx, pady - 3), text.upper(), f, ink, 0.06)
    return im


def kit_sticker(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    name = str(p.get("name") or "").lower()
    size = max(40, min(420, int(_num(p.get("size"), 170))))
    base = _memo("stk" + json.dumps([name, size, p.get("colour"), p.get("accent")], default=str),
                 lambda: _shadowed(S.draw_sticker(name, size, p.get("colour"), p.get("accent")), 6, (0, 5), 110))
    label = str(p.get("label") or "").strip()
    tape = _memo("tape" + label + str(p.get("label_style")), lambda: _shadowed(_tape_element(label, str(p.get("label_style") or "tape")), 4, (0, 3), 100)) if label else None
    cx, cy = W * _num(p.get("x"), 0.5), H * _num(p.get("y"), 0.5)
    k = M.clamp01(t / 0.36)
    scale = _ease_back(k)
    bob = 3.0 * math.sin(2 * math.pi * t / 2.4) * M.ramp(t, 0.4, 0.3)
    ob = _out_alpha(t, dur) if dur > 0 else 1.0
    img = _canvas()
    _place(img, base, cx, cy + bob, 0, max(0.01, scale), M.ramp(t, 0, 0.12) * ob)
    if tape is not None:
        kt = M.ease_out((t - 0.25) / 0.3)
        _place(img, tape, cx, cy + size * 0.64 + (1 - kt) * 14, -2.0, 1.0, kt * ob)
    return img


# ------------------------------------------------------------------------------------------------ ribbon -------------------------

_RIB_COL = {"red": ((214, 36, 44, 255), (255, 255, 255, 255)), "yellow": (YELLOW, INK), "ink": ((20, 22, 28, 255), (255, 255, 255, 255))}


def _torn_strip(width: int, height: int, fill, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    top = [(0, 10)] + [(x, 8 + rnd.randint(-8, 8)) for x in range(0, width + 18, 18)]
    bot = [(width, height - 10)] + [(x, height - 8 + rnd.randint(-8, 8)) for x in range(width, -18, -18)]
    ImageDraw.Draw(im).polygon(top + bot, fill=fill)
    return im


def _ribbon_strip(text: str, colour: str, period_px: int, width: int) -> Tuple[Image.Image, int]:
    fill, ink = _RIB_COL.get(colour, _RIB_COL["red"])
    h = 170
    f = T.font("display", 108)
    unit = text.upper()
    tw = int(_sw(unit, f, 0.05))
    uw = tw + 110
    strip = _torn_strip(width + uw, h, fill, sum(map(ord, text)) + 7)
    d = ImageDraw.Draw(strip)
    x = 0
    while x < strip.width:
        L.spaced(d, (x, 22), unit, f, ink, 0.05)
        d.rectangle([x + tw + 46, h // 2 - 11, x + tw + 68, h // 2 + 11], fill=ink)      # the separator is drawn, so no font needs the glyph
        x += uw
    return strip, uw


def kit_ribbon(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    text = str(p.get("text") or "").strip()
    if not text or dur <= 0:
        return None
    colour = str(p.get("colour") or "red")
    angle = _num(p.get("angle"), -8.0)
    sweep = min(0.45, dur * 0.4)
    # progress: -1 (off to the left) .. 0 (centred) .. +1 (off to the right)
    if t < sweep:
        pr = -(1 - M.ease_in_out(t / sweep))
    elif t > dur - sweep:
        pr = M.ease_in_out((t - (dur - sweep)) / sweep)
    else:
        pr = 0.0
    if abs(pr) >= 0.999:
        return _canvas()
    span = W + 760
    strip, uw = _memo("ribs" + text + colour, lambda: _ribbon_strip(text, colour, 0, 2400))
    off = int((t * 90) % uw)
    win = strip.crop((off, 0, off + 2000, strip.height))
    back = _memo("ribb", lambda: _torn_strip(2400, 190, (16, 18, 24, 255), 3))
    img = _canvas()
    # the dark ribbon trails behind the coloured one (a little later, a little steeper)
    pb = max(-1.0, min(1.0, pr * 1.12 + (0.1 if pr < 0 else 0.0)))
    if abs(pb) < 0.999:
        rb = back.crop((0, 0, 2000, back.height)).rotate(angle + 3.5, resample=Image.BICUBIC, expand=True)
        _blit(img, rb, int(W / 2 - rb.width / 2 + pb * span), int(H / 2 - rb.height / 2 + 24))
    rs = win.rotate(angle, resample=Image.BICUBIC, expand=True)
    _blit(img, _shadowed(rs, 6, (0, 6), 110), int(W / 2 - rs.width / 2 + pr * span) - 18, int(H / 2 - rs.height / 2) - 18)
    return img


# ------------------------------------------------------------------------------------------------ big number ----------------------

_NUM_RE = re.compile(r"^\s*([^\d\-]*)(-?[\d][\d,\.]*)(.*)$")
_BN_COL = {"yellow": YELLOW, "red": (236, 56, 56, 255), "cream": T.CREAM}


def _parse_value(v: Any) -> Tuple[str, Optional[float], str, bool, int]:
    """(prefix, number, suffix, has_commas, decimals). Unparseable text comes back with number None and the text as prefix."""
    if isinstance(v, (int, float)):
        return "", float(v), "", abs(v) >= 1000, 0 if float(v).is_integer() else 1
    s = str(v or "").strip()
    m = _NUM_RE.match(s)
    if not m:
        return s, None, "", False, 0
    pre, num, suf = m.group(1), m.group(2), m.group(3)
    dec = len(num.split(".")[1]) if "." in num else 0
    try:
        val = float(num.replace(",", ""))
    except ValueError:
        return s, None, "", False, 0
    return pre, val, suf, "," in num, dec


def _scrim(width: int) -> Image.Image:
    g = Image.linear_gradient("L").rotate(90).resize((width, H))          # 255 at the left edge fading to 0
    g = g.transpose(Image.FLIP_LEFT_RIGHT).point(lambda v: int(v * 0.58))
    im = Image.new("RGBA", (width, H), (6, 8, 12, 0))
    im.putalpha(g)
    return im


def kit_bignum(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    if p.get("value") in (None, ""):
        return None
    pre, val, suf, commas, dec = _parse_value(p.get("value"))
    col = _BN_COL.get(str(p.get("colour") or "yellow"), YELLOW)
    count = bool(p.get("count", True)) and val is not None
    if val is None:
        shown = pre
    else:
        cur = val * (M.ease_out(M.ramp(t, 0.1, 0.7)) if count else 1.0)
        n = f"{cur:,.{dec}f}" if commas else f"{cur:.{dec}f}"
        shown = f"{pre}{n}{suf}"
    full = f"{pre}{(f'{val:,.{dec}f}' if commas else f'{val:.{dec}f}') if val is not None else ''}{suf}" if val is not None else pre
    size = 210
    f = T.font("display", size)
    maxw = int(W * 0.56)
    while size > 90 and _sw(full, f, 0.02) > maxw:
        size -= 10
        f = T.font("display", size)
    x = int(W * _num(p.get("x"), 0.06))
    y = int(H * _num(p.get("y"), 0.42)) - size // 2
    ob = _out_alpha(t, dur) if dur > 0 else 1.0
    kin = M.ease_out(t / 0.35)
    img = _canvas()
    img.alpha_composite(_memo("scrim", lambda: _scrim(int(W * 0.72))), (0, 0))
    layer = _canvas()
    d = ImageDraw.Draw(layer)
    L.spaced(d, (x + 4, y + 5), shown, f, (0, 0, 0, 150), 0.02)
    L.spaced(d, (x, y), shown, f, col, 0.02)
    ty = y + int(size * 0.98)
    label = str(p.get("label") or "").strip()
    if label:
        fl = T.font("display", 46)
        for i, ln in enumerate(_wrap(label.upper(), fl, int(W * 0.5), 0.05, 2)):
            L.spaced(d, (x + 4, ty + 3 + i * 48), ln, fl, (0, 0, 0, 150), 0.05)
            L.spaced(d, (x, ty + i * 48), ln, fl, (255, 255, 255, 255), 0.05)
        ty += 48 * min(2, len(_wrap(label.upper(), fl, int(W * 0.5), 0.05, 2)))
    sub = str(p.get("sub") or "").strip()
    if sub:
        fs = T.font("regular", 26)
        d.text((x + 2, ty + 10), _fit(sub, fs, int(W * 0.5), 0.0), font=fs, fill=(0, 0, 0, 150))
        d.text((x, ty + 8), _fit(sub, fs, int(W * 0.5), 0.0), font=fs, fill=T.CREAM)
    rule = M.draw_fraction(t, 0.35, T.DRAW_S)
    if rule > 0:
        ry = ty + (50 if sub else 14)
        d.rectangle([x, ry, x + int(260 * rule), ry + 5], fill=col)
    layer = ImageChops.offset(layer, int(-30 * (1 - kin)), 0)
    img.alpha_composite(L.fade(layer, kin * ob))
    return L.fade(img, 1.0) if ob >= 0.999 else L.fade(img, ob)


def kit_versus(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Two stated figures side by side (18 VS 6), each with its own label, an optional title above: the reference's comparison card."""
    p = p or {}
    a, b = str(p.get("a") or "").strip(), str(p.get("b") or "").strip()
    if not a or not b:
        return None
    ob = _out_alpha(t, dur) if dur > 0 else 1.0
    img = _canvas()
    img.alpha_composite(_memo("scrim", lambda: _scrim(int(W * 0.72))), (0, 0))
    layer = _canvas()
    d = ImageDraw.Draw(layer)
    x, y = int(W * 0.06), int(H * 0.30)
    title = str(p.get("title") or "").strip().upper()
    if title:
        ft = T.font("display", 36)
        L.spaced(d, (x, y - 58), _fit(title, ft, int(W * 0.55), 0.05), ft, (236, 56, 56, 255), 0.05)
    f, fl, fv = T.font("display", 150), T.font("bold", 26), T.font("display", 54)
    cols = (YELLOW, (250, 248, 244, 255))
    cx = x
    for i, (val, lab) in enumerate(((a, str(p.get("a_label") or "")), (b, str(p.get("b_label") or "")))):
        k = M.ease_out(M.ramp(t, 0.1 + 0.5 * i, 0.4))
        if k <= 0:
            break
        w_ = int(_sw(val, f, 0.02))
        part = _canvas()
        pd_ = ImageDraw.Draw(part)
        L.spaced(pd_, (cx + 4, y + 5), val, f, (0, 0, 0, 150), 0.02)
        L.spaced(pd_, (cx, y), val, f, cols[i], 0.02)
        if lab:
            for j, ln in enumerate(_wrap(lab.upper(), fl, max(w_, 150), 0.05, 2)):
                L.spaced(pd_, (cx, y + 160 + j * 30), ln, fl, (250, 248, 244, 255), 0.05)
        layer.alpha_composite(L.fade(ImageChops.offset(part, 0, int(20 * (1 - k))), k))
        cx += max(w_, 150) + 24
        if i == 0 and t >= 0.5:
            L.spaced(d, (cx - 10, y + 50), "VS", fv, (236, 56, 56, 255), 0.04)
            cx += int(_sw("VS", fv, 0.04)) + 30
    sub = str(p.get("sub") or "").strip()
    if sub:
        fs = T.font("regular", 24)
        d.text((x, y + 236), _fit(sub, fs, int(W * 0.55), 0.0), font=fs, fill=T.CREAM)
    img.alpha_composite(L.fade(layer, M.ease_out(t / 0.35) * ob))
    return img


# ------------------------------------------------------------------------------------------------ scale diagram -------------------

def kit_scale(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    n = int(_num(p.get("n"), 0))
    if n < 1:
        return None
    shown = min(n, 20)
    colour = p.get("colour")
    bw = int(W * 0.7)
    x0 = (W - bw) // 2
    by = int(H * 0.60)
    ob = _out_alpha(t, dur) if dur > 0 else 1.0
    img = _canvas()
    d = ImageDraw.Draw(img)
    kind = str(p.get("bar") or "pipe")
    bk = M.draw_fraction(t, 0.1, 0.6)
    bl = int(bw * bk)
    if bl > 4:
        if kind == "bar":
            d.rounded_rectangle([x0, by, x0 + bl, by + 22], radius=6, fill=(214, 220, 228, 255))
        else:
            d.rounded_rectangle([x0 + 10, by + 2, x0 + bl - 10 if bl > 24 else x0 + bl, by + 40], radius=7, fill=(188, 198, 210, 255))
            d.line([(x0 + 24, by + 12), (x0 + max(26, bl - 24), by + 12)], fill=(255, 255, 255, 130), width=4)
            d.rounded_rectangle([x0, by - 6, x0 + 16, by + 48], radius=3, fill=(122, 134, 150, 255))
            if bl > 40:
                d.rounded_rectangle([x0 + bl - 16, by - 6, x0 + bl, by + 48], radius=3, fill=(122, 134, 150, 255))
    ph = int(min(150, (bw - 40) / (shown * 0.68 + 0.04)))
    row = _memo("srow" + str(shown) + str(ph) + str(colour), lambda: S.soldiers(shown, ph, colour))
    step = row.width / shown if shown else 1
    top = by - row.height + 8
    for i in range(shown):
        k = M.ease_out((t - 0.5 - i * 0.07) / 0.25)
        if k <= 0:
            continue
        cell = row.crop((int(i * (row.width - 1) / shown), 0, int((i + 1) * (row.width - 1) / shown) + 1, row.height))
        cx = x0 + (bw - row.width) // 2 + int(i * (row.width / shown))
        _blit(img, L.fade(cell, k), cx, top + int((1 - k) * 18))
    img = _shadowed(img, 4, (0, 3), 90) if False else img
    label = str(p.get("label") or "").strip()
    if label:
        tag = _memo(_key("scaletag", p, "label"), lambda: _shadowed(_rotated_cache("scaletr" + label, _tag_element(label, "", 32, int(W * 0.7)), -1.5), 5, (0, 4), 110))
        _place(img, tag, W / 2, top - 52, 0, 1.0, M.ease_out((t - 0.1) / 0.3))
    bar_label = str(p.get("bar_label") or "").strip()
    if bar_label:
        fb = T.font("bold", 20)
        bt = _fit(bar_label, fb, bw, 0.0)
        d.rounded_rectangle([x0, by + 58, x0 + int(d.textlength(bt, font=fb)) + 24, by + 90], radius=4, fill=(10, 12, 16, 220))
        d.text((x0 + 12, by + 62), bt, font=fb, fill=T.CREAM)
    # honesty: the picture is a drawn illustration, whatever it stands for
    fc = T.font("bold", 15)
    chip = "ILLUSTRATIVE · NOT TO SCALE"
    cw = int(_sw(chip, fc, 0.1)) + 40
    cy = by + 102
    d.rounded_rectangle([x0, cy, x0 + cw, cy + 28], radius=4, fill=(10, 12, 16, 235), outline=T.STATUS_COLOUR["illustrative"], width=1)
    d.ellipse([x0 + 10, cy + 9, x0 + 20, cy + 19], fill=T.STATUS_COLOUR["illustrative"])
    L.spaced(d, (x0 + 30, cy + 5), chip, fc, T.CREAM, 0.1)
    return L.fade(img, ob)


# ------------------------------------------------------------------------------------------------ badge ------------------------------

_BADGE = {"ai": "AI-GENERATED ILLUSTRATION", "illustrative": "ILLUSTRATIVE FOOTAGE", "archive": "ARCHIVE FOOTAGE", "user": "USER FOOTAGE"}


def kit_badge(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    kind = str(p.get("kind") or "illustrative")
    text = _BADGE.get(kind.lower(), kind).upper()
    chan = str(p.get("channel") or "").strip()
    if not text and not chan:
        return None

    def build() -> Image.Image:
        im = _canvas()
        d = ImageDraw.Draw(im)
        f = T.font("bold", 14)
        w = int(_sw(text, f, 0.1)) + 22
        x1, y1 = W - 22, H - 22
        d.rounded_rectangle([x1 - w, y1 - 26, x1, y1], radius=4, fill=(10, 12, 16, 170), outline=(176, 182, 192, 150), width=1)
        L.spaced(d, (x1 - w + 11, y1 - 21), text, f, (226, 228, 232, 235), 0.1)
        if chan:
            fc = T.font("display", 20)
            cw = int(_sw(chan.upper(), fc, 0.08)) + 24
            d.rounded_rectangle([22, y1 - 30, 22 + cw, y1], radius=15, fill=(10, 12, 16, 190), outline=YELLOW, width=2)
            L.spaced(d, (34, y1 - 26), chan.upper(), fc, T.CREAM, 0.08)
        return im

    im = _memo(_key("badge", p, "kind", "channel"), build)
    return L.fade(im, M.ramp(t, 0.0, 0.3) * (1.0 - M.ramp(t, dur - 0.2, 0.2) if dur > 0 else 1.0))


# ------------------------------------------------------------------------------------------------ grain ---------------------------

_GRAIN_FRAMES = 8


def _grain_tile(i: int, strength: float, vignette: float) -> Image.Image:
    rnd = random.Random(1000 + i)
    noise = Image.frombytes("L", (W, H), rnd.randbytes(W * H))
    k = max(0.0, strength) * 2.0
    light = noise.point(lambda v: int(max(0, v - 128) * k))
    dark = noise.point(lambda v: int(max(0, 128 - v) * k))
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    wh = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    wh.putalpha(light)
    bl = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    bl.putalpha(dark)
    im.alpha_composite(wh)
    im.alpha_composite(bl)
    if vignette > 0:
        g = Image.radial_gradient("L").resize((W, H), Image.BICUBIC)
        va = g.point(lambda v: int(max(0, v - 90) * vignette * 1.1))
        vg = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        vg.putalpha(va)
        im.alpha_composite(vg)
    return im


def kit_grain(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    s, v = _num(p.get("strength"), 0.05), _num(p.get("vignette"), 0.35)
    i = int(round(t * T.FPS)) % _GRAIN_FRAMES
    im = _memo(f"grain{i}:{s:.3f}:{v:.3f}", lambda: _grain_tile(i, s, v))
    a = M.ramp(t, 0.0, 0.3) * ((1.0 - M.ramp(t, dur - 0.2, 0.2)) if dur > 0 else 1.0)
    return L.fade(im, a) if a < 0.999 else im


# ------------------------------------------------------------------------------------------------ icon explainer / flag ------------

def _bokeh_plate(seed: int) -> Image.Image:
    """A soft out-of-focus dark plate (the reference's blurred photo behind flat icons), deterministic per seed."""
    import random

    from PIL import ImageFilter

    rnd = random.Random(seed)
    im = Image.new("RGBA", (W // 4, H // 4), (20, 24, 32, 255))
    d = ImageDraw.Draw(im)
    for _ in range(26):
        x, y, r = rnd.uniform(0, W / 4), rnd.uniform(0, H / 4), rnd.uniform(6, 30)
        c = rnd.choice(((70, 84, 100), (96, 92, 80), (52, 64, 84), (120, 110, 90)))
        d.ellipse([x - r, y - r, x + r, y + r], fill=c + (rnd.randint(60, 140),))
    im = im.filter(ImageFilter.GaussianBlur(9)).resize((W, H), Image.BICUBIC)
    vg = Image.radial_gradient("L").resize((W, H)).point(lambda v: int(v * 0.75))
    shade = Image.new("RGBA", (W, H), (6, 8, 12, 255))
    shade.putalpha(vg)
    im.alpha_composite(shade)
    return im


def kit_icons(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Flat icons over a blurred plate, for an idea that is not a place or a number (REFERENCE_PATTERNS item 19).
    params: icons [{name, label, start}] (2-4, sticker names), link "arrow" | "vs" | "" between them, title (the narration's words)."""
    from . import stickers as ST

    p = p or {}
    icons = [i for i in (p.get("icons") or []) if isinstance(i, dict) and i.get("name") in ST.NAMES][:4]
    if len(icons) < 2:
        return None
    img = _memo("bokeh" + str(p.get("seed", 0)), lambda: _bokeh_plate(int(p.get("seed", 0) or 0))).copy()
    n = len(icons)
    gap = W * 0.62 / max(1, n - 1)
    x0, cy = W / 2 - gap * (n - 1) / 2, H * 0.52
    link = str(p.get("link") or "")
    d = ImageDraw.Draw(img)
    fl = T.font("display", 30)
    for i, ic in enumerate(icons):
        k = _ease_back(min(1.0, max(0.0, (t - float(ic.get("start", 0.3 + 0.5 * i))) / 0.45)))
        if k <= 0:
            continue
        cx = x0 + gap * i
        if i > 0 and link:
            mx = cx - gap / 2
            a = min(1.0, k * 1.5)
            if link == "vs":
                L.spaced(d, (mx - 26, cy - 30), "VS", T.font("display", 54), (236, 56, 56, int(255 * a)), 0.04)
            else:
                d.line([(mx - gap * 0.22, cy), (mx + gap * 0.18 * a, cy)], fill=(236, 56, 56, int(255 * a)), width=7)
                tip = mx + gap * 0.18 * a
                d.polygon([(tip + 22, cy), (tip - 4, cy - 16), (tip - 4, cy + 16)], fill=(236, 56, 56, int(255 * a)))
        disc = _memo("icdisc" + ic["name"], lambda: _shadowed(_icon_disc(ST.draw_sticker(ic["name"], 150)), 8, (0, 6), 140))
        _place(img, disc, cx, cy, 0.0, 0.6 + 0.4 * k, min(1.0, k))
        lab = str(ic.get("label") or "").upper()
        if lab and k >= 0.6:
            tw = _sw(lab, fl, 0.06)
            L.spaced(d, (int(cx - tw / 2), int(cy + 112)), lab, fl, (250, 248, 244, 255), 0.06)
    title = str(p.get("title") or "").strip()
    if title and t >= 0.2:
        el = _memo(_key("ictitle", p, "title"), lambda: _shadowed(_rotated_cache("ict" + title, _hook_element(title, 34, int(W * 0.6)), -2.0), 5, (0, 4), 110))
        _blit(img, el, (W - el.width) // 2, 60)
    return L.fade(img, _out_alpha(t, dur) if dur > 0 else 1.0)


def _icon_disc(icon: Image.Image) -> Image.Image:
    size = icon.width + 60
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, size - 1, size - 1], fill=(246, 244, 238, 255), outline=(255, 255, 255, 255), width=3)
    im.alpha_composite(icon, (30, 30))
    return im


FLAGS = {   # stripe flags only (drawn exactly from their stripes): (orientation, colours, weights)
    "UKR": ("h", ((0, 87, 183), (255, 215, 0)), (1, 1)), "RUS": ("h", ((255, 255, 255), (0, 57, 166), (213, 43, 30)), (1, 1, 1)),
    "POL": ("h", ((255, 255, 255), (220, 20, 60)), (1, 1)), "DEU": ("h", ((0, 0, 0), (221, 0, 0), (255, 206, 0)), (1, 1, 1)),
    "FRA": ("v", ((0, 85, 164), (255, 255, 255), (239, 65, 53)), (1, 1, 1)), "LTU": ("h", ((253, 185, 19), (0, 106, 68), (193, 39, 45)), (1, 1, 1)),
    "ROU": ("v", ((0, 43, 127), (252, 209, 22), (206, 17, 38)), (1, 1, 1)), "BGR": ("h", ((255, 255, 255), (0, 150, 110), (214, 38, 18)), (1, 1, 1)),
    "EST": ("h", ((0, 114, 206), (0, 0, 0), (255, 255, 255)), (1, 1, 1)), "LVA": ("h", ((158, 48, 57), (255, 255, 255), (158, 48, 57)), (2, 1, 2)),
    "NLD": ("h", ((174, 28, 40), (255, 255, 255), (33, 70, 139)), (1, 1, 1)), "BEL": ("v", ((0, 0, 0), (253, 218, 36), (239, 51, 64)), (1, 1, 1)),
    "ITA": ("v", ((0, 146, 70), (255, 255, 255), (206, 43, 55)), (1, 1, 1)), "HUN": ("h", ((206, 41, 57), (255, 255, 255), (71, 112, 80)), (1, 1, 1)),
    "AUT": ("h", ((200, 16, 46), (255, 255, 255), (200, 16, 46)), (1, 1, 1)),
}


def _flag_base(iso: str) -> Image.Image:
    o, cols, wts = FLAGS[iso]
    w, h = W + 160, H + 160
    im = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(im)
    tot, pos = sum(wts), 0.0
    for c, wt in zip(cols, wts):
        a, b = pos / tot, (pos + wt) / tot
        if o == "h":
            d.rectangle([0, int(a * h), w, int(b * h) + 1], fill=c + (255,))
        else:
            d.rectangle([int(a * w), 0, int(b * w) + 1, h], fill=c + (255,))
        pos += wt
    return im


def kit_flag(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """A full-screen waving flag between chapters (REFERENCE_PATTERNS item 20): stripe flags only; an unknown country draws nothing."""
    iso = str((p or {}).get("iso3") or "").upper()
    if iso not in FLAGS:
        return None
    base = _memo("flag" + iso, lambda: _flag_base(iso))
    img = _canvas()
    strip = 16
    ph = t * 5.0
    for x in range(0, W, strip):
        u = x / W
        dy = 34 * math.sin(u * 5.2 - ph) * (0.35 + 0.65 * u)
        shade = 0.82 + 0.18 * math.cos(u * 5.2 - ph)
        col = base.crop((x + 80, int(80 - dy), x + 80 + strip, int(80 - dy) + H))
        if shade < 0.999:
            col = Image.eval(col.convert("RGB"), lambda v, s_=shade: int(v * s_)).convert("RGBA")
        img.paste(col, (x, 0))
    a = min(1.0, t / 0.18, max(0.0, (dur - t) / 0.18)) if dur > 0 else 1.0
    return L.fade(img, a)


# ------------------------------------------------------------------------------------------------ chapter / speaker -----------------

def kit_chapter(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """A chapter opener over whatever is on screen: yellow chip (CHAPTER TWO) and a short white subtitle, centred in the upper third."""
    label = str((p or {}).get("label") or "").strip().upper()
    if not label:
        return None
    sub = str(p.get("sub") or "").strip()

    def build() -> Image.Image:
        f, fs = T.font("display", 40), T.font("bold", 24)
        tw = int(_sw(label, f, 0.08))
        sub_l = _wrap(sub.upper(), fs, int(W * 0.6), 0.06, 1) if sub else []
        sw = int(_sw(sub_l[0], fs, 0.06)) if sub_l else 0
        w = max(tw + 48, sw + 20)
        im = Image.new("RGBA", (w, 120), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        x0 = (w - tw - 48) // 2
        d.rounded_rectangle([x0, 0, x0 + tw + 47, 58], radius=6, fill=YELLOW)
        L.spaced(d, (x0 + 24, 8), label, f, INK, 0.08)
        if sub_l:
            L.spaced(d, ((w - sw) // 2, 74), sub_l[0], fs, (250, 248, 244, 255), 0.06)
        return _shadowed(im, 8, (0, 4), 150)
    el = _memo(_key("chapter", p, "label", "sub"), build)
    k = _ease_back(min(1.0, t / 0.5))
    img = _canvas()
    _place(img, el, W / 2, H * 0.36, 0.0, 0.9 + 0.1 * k, min(1.0, t / 0.3))
    return L.fade(img, _out_alpha(t, dur) if dur > 0 else 1.0)


def kit_speaker(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Who is speaking: white card, name in bold, role underneath, top right (sliding in from the edge)."""
    name = str((p or {}).get("name") or "").strip().upper()
    if not name:
        return None
    role = str(p.get("role") or "").strip()

    def build() -> Image.Image:
        fn, fr_ = T.font("bold", 24), T.font("regular", 18)
        lines = _wrap(role, fr_, 300, 0.0, 2) if role else []
        w = int(max([_sw(name, fn, 0.04)] + [_sw(x, fr_, 0.0) for x in lines])) + 40
        h = 24 + 30 + 24 * len(lines) + 12
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=8, fill=(248, 246, 240, 250), outline=(255, 255, 255, 255), width=2)
        L.spaced(d, (20, 14), name, fn, (20, 20, 24, 255), 0.04)
        y = 48
        for x in lines:
            d.text((20, y), x, font=fr_, fill=(70, 70, 76, 255))
            y += 24
        return _shadowed(im, 6, (0, 4), 130)
    el = _memo(_key("speaker", p, "name", "role"), build)
    k = M.ease_out(min(1.0, t / 0.4))
    img = _canvas()
    _blit(img, el, W - T.MARGIN_X - el.width + int((1 - k) * 60), 64)
    return L.fade(img, (_out_alpha(t, dur) if dur > 0 else 1.0) * k)


KIT_CARDS = {"kit_icons": kit_icons, "kit_flag": kit_flag, "kit_versus": kit_versus, "kit_chapter": kit_chapter, "kit_speaker": kit_speaker, "kit_tag": kit_tag, "kit_stamp": kit_stamp, "kit_chips": kit_chips, "kit_recap": kit_recap, "kit_sticker": kit_sticker,
             "kit_ribbon": kit_ribbon, "kit_bignum": kit_bignum, "kit_scale": kit_scale, "kit_badge": kit_badge, "kit_grain": kit_grain}
