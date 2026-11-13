"""Shared transitions between the three looks (docs/aviation/MASTER_PLAN.md section 2, step 13): sticker stage, flight map, news.

    look_of(shot) -> 'stage' | 'map' | 'news'
    add(plan) -> [transition shots]     at every cut where the look changes:
        out of a stage / map / full-frame card   'transitions.lay_out': its last frame shrinks into a white-edged sticker card and
                                                 flies off over the incoming look (the map shrinks into a sticker, the stage
                                                 leaves as one), OUT_S long, just after the cut
        out of footage                           the stage-colour wipe (retention.lay_rehook, style 'wipe') across the cut
    Cuts inside one look stay hard cuts (the references cut hard inside a look); nothing is added at the film's start or end.
    lay_out(t, dur, params) -> RGBA W x H       params {from_layer, from_params, from_t, from_dur}
The outgoing frame is drawn once (cached) and only scaled / moved per frame.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from cinematic_explainer.war import motion as M

from . import style as S

W, H = S.W, S.H
OUT_S = 0.6
WIPE_S = 0.6
EXIT_GUARD_S = 1.0          # the outgoing frame is taken before its own exit fade (a card's last frame is empty)
_CACHE: Dict[Tuple[str, int, float], Image.Image] = {}


def look_of(shot: Dict[str, Any]) -> str:
    lay = str(shot.get("layer") or "")
    if lay == "stage.lay_stage":
        return "stage"
    if lay == "flightmap.lay_flight_map":
        return "map"
    return "news"


def _base(plan: Any) -> List[Dict[str, Any]]:
    b = [s for s in plan.shots if s.get("kind") == "footage" or s.get("full_frame")]
    return sorted(b, key=lambda s: (float(s["start"]), -float(s["end"])))


def add(plan: Any) -> List[Dict[str, Any]]:
    base = _base(plan)
    added: List[Dict[str, Any]] = []
    for a, b in zip(base, base[1:]):
        cut = float(b["start"])
        if abs(float(a["end"]) - cut) > 0.05 or look_of(a) == look_of(b):
            continue
        if a.get("layer") and a.get("kind") != "footage":
            dur = float(a["end"]) - float(a["start"])
            sh = {"layer": "transitions.lay_out", "start": cut, "end": min(float(b["end"]), cut + OUT_S), "scene": b.get("scene"),
                  "transition": f"{look_of(a)}->{look_of(b)}",
                  "params": {"from_layer": a["layer"], "from_params": a.get("params") or {}, "from_t": max(0.0, min(dur * 0.8, dur - EXIT_GUARD_S)),
                             "from_dur": dur}}
        else:
            sh = {"layer": "retention.lay_rehook", "start": max(float(a["start"]), cut - WIPE_S / 2),
                  "end": min(float(b["end"]), cut + WIPE_S / 2), "scene": b.get("scene"), "transition": f"{look_of(a)}->{look_of(b)}",
                  "params": {"style": "wipe"}}
        if sh["end"] - sh["start"] > 0.1:
            added.append(sh)
    plan.shots.extend(added)
    return added


def _frame(p: Dict[str, Any]) -> Optional[Image.Image]:
    key = (str(p.get("from_layer")), id(p.get("from_params")), round(float(p.get("from_t", 0)), 3))
    if key in _CACHE:
        return _CACHE[key]
    from . import bridge as BR
    fn = BR.card_table().get(key[0])
    im = None
    if fn is not None:
        try:
            im = fn(float(p.get("from_t", 0)), float(p.get("from_dur", 1)), p.get("from_params") or {})
        except Exception:
            im = None
    if im is not None:
        im = im.convert("RGBA")
        if im.size != (W, H):
            im = im.resize((W, H), Image.BILINEAR)
        edge = int(26 * S.scale())
        card = Image.new("RGBA", (W + 2 * edge, H + 2 * edge), (0, 0, 0, 0))
        ImageDraw.Draw(card).rounded_rectangle((0, 0, card.width - 1, card.height - 1), radius=edge * 2, fill=S.WHITE)
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=edge * 2 - edge // 2, fill=255)
        card.paste(im, (edge, edge), mask)
        im = card
    if len(_CACHE) > 16:
        _CACHE.clear()
    _CACHE[key] = im
    return im


def card_at(k: float) -> Tuple[float, float, float, float, float]:
    """(scale, centre x, centre y, rotation, alpha) of the leaving card at progress k (0..1): shrink, tilt, fly off left-up."""
    e = M.ease_in_out(M.clamp01(k))
    sc = 1.0 - 0.72 * M.ease_out(M.clamp01(k * 1.4))
    x = W / 2 - e * e * W * 0.95
    y = H / 2 - e * H * 0.18
    rot = 7.0 * e
    alpha = 1.0 - M.clamp01((k - 0.75) / 0.25)
    return sc, x, y, rot, alpha


def lay_out(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    card = _frame(p)
    if card is None or dur <= 0:
        return None
    k = t / dur
    if k >= 1.0:
        return None
    sc, x, y, rot, alpha = card_at(k)
    w = max(2, int(card.width * sc))
    h = max(2, int(card.height * sc))
    im = card.resize((w, h), Image.BILINEAR)
    if abs(rot) > 0.1:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sh.putalpha(im.getchannel("A").point(lambda v: v * 120 // 255))
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    ox, oy = int(x - im.width / 2), int(y - im.height / 2)
    out.alpha_composite(_clip(sh, out, ox + 8, oy + 12)[0], _clip(sh, out, ox + 8, oy + 12)[1])
    if alpha < 0.999:
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    c, d = _clip(im, out, ox, oy)
    out.alpha_composite(c, d)
    return out


def _clip(im: Image.Image, canvas: Image.Image, x: int, y: int):
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(im.width, canvas.width - x), min(im.height, canvas.height - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0)), (0, 0)
    return im.crop((sx0, sy0, sx1, sy1)), (x + sx0, y + sy0)
