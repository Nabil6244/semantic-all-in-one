"""The ocean stage: the Aviation sticker stage (aviation/stage.py) played over a moving ocean set instead of the black stage.

    st = OceanStage()
    st.set(0.0, "open_water")
    shark = st.add("image", at=0.4, args={"path": "great_white.png", "width": 520})     # animals have no white sticker edge
    st.set(6.0, "seafloor")                                                             # sets cross-fade (SET_FADE_S)
    layer_params = st.params()      # Layer("ocean.lay_ocean", start, end, layer_params)

lay_ocean(t, dur, p) -> RGBA W x H. Element motion (enter / glide / float / exit), sprite caching and placeholders are the
Aviation stage's own, so both styles keep one motion language; only the world behind them differs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PIL import Image

from aviation import stage as AV
from cinematic_explainer.war import motion as M

from . import animals as A
from . import backdrop as B
from . import look as L

W, H = L.W, L.H
SET_FADE_S = 0.6
OVER_CLIP = {"number_hero", "standoff", "progress", "calendar", "clock", "counter"}   # cards drawn over a real clip
AV.register("animal", A.stage_kind)          # args {"name", "width", "face", "jaw", "silhouette", "color", "eye", "scars"}
from . import cards as _cards  # noqa: E402

_cards.register_all()                        # card kinds "ocean_<name>" (ocean/cards.py KINDS)


class OceanStage(AV.Stage):
    def __init__(self) -> None:
        super().__init__()
        self._sets: List[List[Any]] = []

    def set(self, at: float, name: str, args: Optional[Dict[str, Any]] = None) -> None:
        """Change the world behind the elements from `at` (a same-set call with the same args is ignored)."""
        name = name if name in B.SETS else "open_water"
        entry = [float(at), name, dict(args or {})]
        if self._sets and self._sets[-1][1:] == entry[1:]:
            return
        self._sets.append(entry)

    def add(self, kind: str, at: float, args: Optional[Dict[str, Any]] = None, **kw: Any) -> str:
        kw.setdefault("edge", False)                 # drawn animals sit in the water: no die-cut edge ...
        a = dict(args or {})
        a.setdefault("_flat", True)                  # ... and no drop shadow
        return super().add(kind, at, a, **kw)

    def params(self) -> Dict[str, Any]:
        p = super().params()
        p["sets"] = [list(s) for s in sorted(self._sets, key=lambda s: s[0])] or [[0.0, "open_water", {}]]
        return p


def set_at(sets: Sequence[Sequence[Any]], t: float):
    """(current set, previous set or None, fade 0..1) at t."""
    cur, prev, since = None, None, -1e9
    for s in sets:
        if float(s[0]) > t:
            break
        prev, cur, since = cur, s, float(s[0])
    if cur is None:
        cur = sets[0] if sets else [0.0, "open_water", {}]
    k = 1.0 if prev is None else M.clamp01((t - since) / SET_FADE_S)
    return cur, prev, k


def world(sets: Sequence[Sequence[Any]], t: float) -> Image.Image:
    cur, prev, k = set_at(sets, t)
    img = B.draw(cur[1], t, cur[2] if len(cur) > 2 else None)
    if prev is not None and k < 1:
        old = B.draw(prev[1], t, prev[2] if len(prev) > 2 else None)
        img = Image.blend(old, img, M.ease_in_out(k))
    return img


def _credit_layer(text: str) -> Optional[Image.Image]:
    """During a real clip the stage steps aside; only the clip's small credit line stays (bottom-left)."""
    if not text:
        return None
    from PIL import ImageDraw
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = L.font("regular", 15)
    sc = L.scale()
    x, y = 26 * sc, H - 28 * sc
    d.text((x + 1, y + 1), text, font=f, fill=(0, 0, 0, 150))
    d.text((x, y), text, font=f, fill=(236, 240, 242, 200))
    return img


def lay_ocean(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    t = t + float(p.get("t_offset", 0.0))
    for h in p.get("holes") or []:              # a real clip plays here (ocean/clips.py)
        if float(h[0]) <= t < float(h[1]):
            img = _credit_layer(str(h[2] if len(h) > 2 else "")) or Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sc = L.scale()
            for e in p.get("elements") or []:   # number cards stay over the footage ("~300 TEETH" on the real shark)
                if str(e.get("kind", ""))[6:] not in OVER_CLIP:
                    continue
                tr = AV.transform(e, t)
                if tr is not None:
                    x, y, s, rot, alpha = tr
                    AV._paste(img, AV.sprite(e, s, AV.anim_k(e, t)), x * sc, y * sc, rot, alpha)
            return img
    canvas = world(p.get("sets") or [[0.0, "open_water", {}]], t)
    sc = L.scale()
    for e in sorted(p.get("elements") or [], key=lambda e: e.get("z", 0)):
        tr = AV.transform(e, t)
        if tr is None:
            continue
        x, y, s, rot, alpha = tr
        if e.get("kind") == "animal":            # keeps swimming: tail / arms / fins at this moment's phase
            a = e.get("args") or {}
            e = dict(e, args=dict(a, _ph=A.phase_at(str(a.get("name", "")), t, e.get("id", ""))))
        AV._paste(canvas, AV.sprite(e, s, AV.anim_k(e, t)), x * sc, y * sc, rot, alpha)
    return canvas


CARDS = {"ocean.lay_ocean": lay_ocean}
