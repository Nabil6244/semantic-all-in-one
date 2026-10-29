"""Per-element motion for board and cartoon clips (opt-in, pure functions of the element's age: a frame still depends only on the item and the time).

A visual cue may carry `params["motion"]`, a plain dict (JSON-friendly, so it is part of the cue and of the clip hash):

    {"enter":    {"from": "left|right|top|bottom|none", "dist": 140, "dur": 0.5, "ease": "out"},   # slides in from off-axis (and fades in when "fade" is set)
     "fade":     0.3,                                         # seconds of fade-in (alpha 0 -> 1); also the entrance's alpha ramp
     "scale":    [0.6, 1.0, 0.5],                             # start, end scale and the seconds the change takes (around the element's centre)
     "path":     [{"t": 0.0, "x": 0, "y": 0, "s": 1.0, "a": 1.0}, {"t": 1.2, "x": 300, "y": 0}],   # keyframes (offsets in px from the laid-out position), eased between
     "emphasis": {"at": 1.5, "kind": "pulse|shake", "dur": 0.4, "amp": 0.08},
     "exit":     {"at": 4.0, "to": "left|right|top|bottom|none", "dist": 140, "dur": 0.4},
     "wave":     {"span": 0.3, "dur": 0.3, "dist": 50},   # left-to-right entrance of one wide sprite (a crowd): each vertical slice rises and fades in a little after the one to its left
     "nopop":    true,                                        # the element's own pop-in scale (elements.scale_at) is replaced by this motion's entrance
     "layer":    "bg|mid|fg", "parallax": 0.3}                # draw order group, and a slow drift that grows with the layer's depth

`state(spec, age)` returns (dx, dy, scale, alpha). `draw_moving` draws any element through the existing draw function and composites it transformed, without the draw function knowing.
An element without a motion spec never reaches this module's drawing path: its pixels are exactly what the old code draws.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional, Tuple

from PIL import Image

LAYERS = {"bg": 0, "mid": 1, "fg": 2}
DEPTH = {"bg": 0.4, "mid": 1.0, "fg": 1.6}                       # parallax multiplier by layer
_DIR = {"left": (-1.0, 0.0), "right": (1.0, 0.0), "top": (0.0, -1.0), "bottom": (0.0, 1.0), "none": (0.0, 0.0)}


def ease(name: str, k: float) -> float:
    k = max(0.0, min(1.0, float(k)))
    if name == "linear":
        return k
    if name == "in":
        return k * k * k
    if name == "inout":
        return 3 * k * k - 2 * k * k * k
    if name == "back":
        s = 1.4
        return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2
    return 1 - (1 - k) ** 3                                        # "out" (the default: the reference's ease-out cubic)


def has_motion(vparams: Any) -> bool:
    return bool(isinstance(vparams, dict) and isinstance(vparams.get("motion"), dict) and vparams["motion"])


def layer_of(vparams: Any) -> int:
    if isinstance(vparams, dict) and isinstance(vparams.get("motion"), dict):
        return LAYERS.get(str(vparams["motion"].get("layer", "mid")), 1)
    return 1


def _keyframes(path, age: float) -> Tuple[float, float, float, float]:
    pts = sorted((p for p in path if isinstance(p, dict) and "t" in p), key=lambda p: float(p["t"]))
    if not pts:
        return 0.0, 0.0, 1.0, 1.0
    cur = {"x": 0.0, "y": 0.0, "s": 1.0, "a": 1.0}
    prev = {"t": 0.0, **cur}
    for p in pts:
        nxt = {"t": float(p["t"]), **{k: float(p.get(k, cur[k])) for k in cur}}
        if age <= nxt["t"]:
            span = max(1e-9, nxt["t"] - prev["t"])
            k = ease(str(p.get("ease", "inout")), (age - prev["t"]) / span)
            return tuple(prev[q] + (nxt[q] - prev[q]) * k for q in ("x", "y", "s", "a"))     # type: ignore[return-value]
        prev, cur = nxt, {k: nxt[k] for k in cur}
    return prev["x"], prev["y"], prev["s"], prev["a"]


def state(spec: Dict[str, Any], age: float) -> Tuple[float, float, float, float]:
    """(dx, dy, scale, alpha) of an element `age` seconds after it appeared."""
    dx = dy = 0.0
    s = a = 1.0
    en = spec.get("enter")
    if isinstance(en, dict):
        d = _DIR.get(str(en.get("from", "none")), (0.0, 0.0))
        k = ease(str(en.get("ease", "out")), age / max(1e-6, float(en.get("dur", 0.5))))
        dist = float(en.get("dist", 140))
        dx += d[0] * dist * (1 - k)
        dy += d[1] * dist * (1 - k)
    fade = float(spec.get("fade", 0) or 0)
    if fade > 0:
        a *= ease("out", age / fade)
    sc = spec.get("scale")
    if isinstance(sc, (list, tuple)) and len(sc) >= 2:
        dur = float(sc[2]) if len(sc) > 2 else 0.4
        s *= float(sc[0]) + (float(sc[1]) - float(sc[0])) * ease("out", age / max(1e-6, dur))
    if isinstance(spec.get("path"), (list, tuple)) and spec["path"]:
        px, py, ps, pa = _keyframes(spec["path"], age)
        dx, dy, s, a = dx + px, dy + py, s * ps, a * pa
    em = spec.get("emphasis")
    if isinstance(em, dict):
        t0, dur = float(em.get("at", 0)), max(1e-6, float(em.get("dur", 0.4)))
        if t0 <= age <= t0 + dur:
            k = (age - t0) / dur
            amp = float(em.get("amp", 0.08))
            if em.get("kind") == "shake":
                dx += 14 * amp * 10 * math.sin(k * math.pi * 6) * (1 - k)
            else:
                s *= 1 + amp * math.sin(k * math.pi)
    idle = spec.get("idle")
    if isinstance(idle, dict):                       # a living figure: a slow bob and sway with a breath of scale, each figure on its own phase; never needs a keyframe
        per, ph = max(0.5, float(idle.get("period", 2.4))), float(idle.get("phase", 0.0))
        dy += float(idle.get("bob", 5.0)) * math.sin(2 * math.pi * age / per + ph)
        dx += float(idle.get("sway", 3.0)) * math.sin(2 * math.pi * age / (per * 1.7) + ph)
        s *= 1 + 0.012 * math.sin(2 * math.pi * age / per + ph + 1.0)
    tk = spec.get("talk")
    if isinstance(tk, dict):                         # the speaker bounces on each syllable-sized beat while it speaks
        t0, dur = float(tk.get("at", 0)), max(1e-6, float(tk.get("dur", 1.5)))
        if t0 <= age <= t0 + dur:
            k = (age - t0) / dur
            dy -= float(tk.get("amp", 7.0)) * abs(math.sin(math.pi * (age - t0) / 0.34)) * min(1.0, 4 * k, 4 * (1 - k))
    ex = spec.get("exit")
    if isinstance(ex, dict):
        t0, dur = float(ex.get("at", 1e9)), max(1e-6, float(ex.get("dur", 0.4)))
        if age >= t0:
            k = ease("in", (age - t0) / dur)
            d = _DIR.get(str(ex.get("to", "none")), (0.0, 0.0))
            dx += d[0] * float(ex.get("dist", 140)) * k
            dy += d[1] * float(ex.get("dist", 140)) * k
            a *= 1 - k
    par = float(spec.get("parallax", 0) or 0)
    if par:
        dx += min(60.0, par * 12.0 * DEPTH.get(str(spec.get("layer", "mid")), 1.0) * age)
    return dx, dy, max(0.01, s), max(0.0, min(1.0, a))


def wave_active(spec: Dict[str, Any], age: float) -> bool:
    w = spec.get("wave")
    return isinstance(w, dict) and age < float(w.get("span", 0.3)) + float(w.get("dur", 0.3))


def nopop(vparams: Any) -> bool:
    return bool(isinstance(vparams, dict) and isinstance(vparams.get("motion"), dict) and vparams["motion"].get("nopop"))


def _wave(sprite: Image.Image, spec: Dict[str, Any], age: float) -> Image.Image:
    w = spec["wave"]
    span, dur, dist = float(w.get("span", 0.3)), max(1e-6, float(w.get("dur", 0.3))), int(w.get("dist", 50))
    out = Image.new("RGBA", (sprite.width, sprite.height + dist), (0, 0, 0, 0))
    ns = max(1, sprite.width // 16)
    for j in range(ns):
        x0, x1 = j * sprite.width // ns, (j + 1) * sprite.width // ns
        k = ease("out", (age - (j + 0.5) / ns * span) / dur)
        if k <= 0.0 or x1 <= x0:
            continue
        sl = sprite.crop((x0, 0, x1, sprite.height))
        if k < 1.0:
            sl.putalpha(sl.getchannel("A").point(lambda v, k=k: int(v * k)))
        out.paste(sl, (x0, int(round(dist * (1 - k)))), sl.getchannel("A"))
    return out


def is_identity(st: Tuple[float, float, float, float]) -> bool:
    return abs(st[0]) < 0.5 and abs(st[1]) < 0.5 and abs(st[2] - 1.0) < 1e-3 and st[3] > 0.999


def draw_moving(im: Image.Image, draw_fn: Callable[..., None], it, age: float, frame_no: int = 0) -> None:
    """Draw `it` with `draw_fn(im, it, age, frame_no)` and apply its motion state. The element is drawn twice (on black and on white) to recover its exact alpha, whatever the draw function does."""
    import numpy as np

    spec = (it.vparams or {}).get("motion") or {}
    dx, dy, s, a = state(spec, age)
    if a <= 0.0:
        return
    if is_identity((dx, dy, s, a)) and not wave_active(spec, age):
        draw_fn(im, it, age, frame_no)
        return
    W, H = im.size
    x0, y0, x1, y1 = it.bbox if getattr(it, "bbox", None) else it.rect
    pad = 24
    box = (max(0, int(x0) - pad), max(0, int(y0) - pad), min(W, int(x1) + pad), min(H, int(y1) + pad))
    if box[2] <= box[0] or box[3] <= box[1]:
        return
    renders = []
    for bg in ((0, 0, 0), (255, 255, 255)):
        tmp = Image.new("RGB", (W, H), bg)
        draw_fn(tmp, it, age, frame_no)
        renders.append(np.asarray(tmp.crop(box), dtype=np.float32))
    blk, wht = renders
    alpha = np.clip(1.0 - (wht - blk).mean(axis=2) / 255.0, 0.0, 1.0)
    safe = np.maximum(alpha, 1e-3)[..., None]
    rgb = np.clip(blk / safe, 0, 255)
    sprite = Image.fromarray(np.dstack([rgb, alpha * 255.0]).astype(np.uint8), "RGBA")
    if abs(s - 1.0) > 1e-3:
        nw, nh = max(1, int(round(sprite.width * s))), max(1, int(round(sprite.height * s)))
        sprite = sprite.resize((nw, nh), Image.LANCZOS)
    if wave_active(spec, age):
        sprite = _wave(sprite, spec, age)
    cx = (it.rect[0] + it.rect[2]) / 2.0 if getattr(it, "rect", None) else (box[0] + box[2]) / 2.0
    cy = (it.rect[1] + it.rect[3]) / 2.0 if getattr(it, "rect", None) else (box[1] + box[3]) / 2.0
    ox = cx + (box[0] - cx) * s + dx                                # scale about the element's centre, then move
    oy = cy + (box[1] - cy) * s + dy
    if a < 1.0:
        al = sprite.getchannel("A").point(lambda v: int(v * a))
        sprite.putalpha(al)
    im.paste(sprite.convert("RGB"), (int(round(ox)), int(round(oy))), sprite.getchannel("A"))
