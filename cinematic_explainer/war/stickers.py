"""Flat pictogram library for the War Documentary kit cards (cards_kit.py): generic symbols only, drawn with PIL, cached.

    draw_sticker(name, size, colour=None, accent=None) -> RGBA size x size   (transparent background, anti-aliased by 4x supersampling)
    soldiers(n, height, colour=None, accent=None, gap=0.12) -> RGBA          (n generic soldier pictograms in a row, for scale diagrams)
    NAMES                                                                    (every name draw_sticker knows)

Names: soldier person column snowflake drone tank truck missile explosion tree pipe flame shield clock magnifier question check cross, plus apc howitzer mlrs
helicopter jet ship radar aa_launcher crate barrel tanker train shell bomb rifle mortar binoculars medic radio tent fpv convoy.
Every symbol is a deliberately generic silhouette: no real insignia, flags, unit marks or identifiable vehicle models. An unknown name draws a
plain question mark (never raises). Colours are (r, g, b) or (r, g, b, a); None takes the symbol's own default pair (fill, accent).
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from . import tokens as T

SS = 4                                   # supersampling factor
Colour = Tuple[int, int, int, int]

DEFAULTS: Dict[str, Tuple[Colour, Colour]] = {
    "soldier": ((84, 140, 226, 255), (28, 52, 104, 255)),
    "person": ((176, 182, 192, 255), (92, 98, 108, 255)),
    "column": ((84, 140, 226, 255), (28, 52, 104, 255)),
    "snowflake": ((246, 250, 255, 255), (170, 200, 236, 255)),
    "drone": ((226, 230, 236, 255), (110, 120, 138, 255)),
    "tank": ((118, 150, 100, 255), (52, 68, 48, 255)),
    "truck": ((150, 160, 124, 255), (58, 64, 52, 255)),
    "missile": ((226, 228, 232, 255), (214, 60, 56, 255)),
    "explosion": ((255, 190, 40, 255), (255, 118, 30, 255)),
    "tree": ((84, 160, 92, 255), (122, 84, 52, 255)),
    "pipe": ((196, 204, 214, 255), (118, 130, 146, 255)),
    "flame": ((255, 140, 40, 255), (255, 214, 90, 255)),
    "shield": ((204, 210, 220, 255), (84, 110, 160, 255)),
    "clock": ((242, 242, 242, 255), (214, 60, 56, 255)),
    "magnifier": ((242, 242, 242, 255), (120, 160, 220, 255)),
    "question": ((255, 213, 0, 255), (24, 24, 28, 255)),
    "check": ((84, 170, 116, 255), (255, 255, 255, 255)),
    "cross": ((214, 60, 56, 255), (255, 255, 255, 255)),
}
NAMES = tuple(DEFAULTS)


def _rgba(c, default: Colour) -> Colour:
    if c is None:
        return default
    c = tuple(int(v) for v in c)
    return (c[0], c[1], c[2], c[3] if len(c) > 3 else 255)  # type: ignore[return-value]


class _Pen:
    """Draws in a 100x100 design box, with an optional offset/scale so a pictogram can be placed inside another."""

    def __init__(self, size: int):
        self.n = size * SS
        self.im = Image.new("RGBA", (self.n, self.n), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)
        self.ox, self.oy, self.sc = 0.0, 0.0, 1.0

    def set_t(self, ox: float = 0.0, oy: float = 0.0, sc: float = 1.0) -> None:
        self.ox, self.oy, self.sc = ox, oy, sc

    def _p(self, x: float, y: float) -> Tuple[float, float]:
        k = self.n / 100.0
        return ((self.ox + x * self.sc) * k, (self.oy + y * self.sc) * k)

    def poly(self, pts: Sequence[Tuple[float, float]], fill: Colour) -> None:
        self.d.polygon([self._p(x, y) for x, y in pts], fill=fill)

    def rrect(self, x0, y0, x1, y1, r, fill: Colour) -> None:
        a, b = self._p(x0, y0), self._p(x1, y1)
        self.d.rounded_rectangle([a, b], radius=r * self.sc * self.n / 100.0, fill=fill)

    def ellipse(self, x0, y0, x1, y1, fill: Optional[Colour] = None, outline: Optional[Colour] = None, w: float = 0) -> None:
        a, b = self._p(x0, y0), self._p(x1, y1)
        self.d.ellipse([a, b], fill=fill, outline=outline, width=int(round(w * self.sc * self.n / 100.0)))

    def circle(self, cx, cy, r, fill: Optional[Colour] = None, outline: Optional[Colour] = None, w: float = 0) -> None:
        self.ellipse(cx - r, cy - r, cx + r, cy + r, fill, outline, w)

    def line(self, pts: Sequence[Tuple[float, float]], w: float, fill: Colour) -> None:
        ps = [self._p(x, y) for x, y in pts]
        pw = max(1, int(round(w * self.sc * self.n / 100.0)))
        self.d.line(ps, fill=fill, width=pw, joint="curve")
        r = pw / 2.0
        for x, y in (ps[0], ps[-1]):
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    def pieslice(self, x0, y0, x1, y1, a0, a1, fill: Colour) -> None:
        a, b = self._p(x0, y0), self._p(x1, y1)
        self.d.pieslice([a, b], a0, a1, fill=fill)

    def finish(self, size: int) -> Image.Image:
        return self.im.resize((size, size), Image.LANCZOS)


def _rot(pts: Sequence[Tuple[float, float]], deg: float, cx: float = 50.0, cy: float = 50.0) -> List[Tuple[float, float]]:
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


# ------------------------------------------------------------------------------------------------ symbols --------------------------

def _soldier(p: _Pen, c: Colour, a: Colour, ox: float = 0.0, oy: float = 0.0, sc: float = 1.0) -> None:
    p.set_t(ox, oy, sc)
    p.rrect(20, 40, 31, 72, 5, c)                         # arms
    p.rrect(69, 40, 80, 72, 5, c)
    p.rrect(29, 36, 71, 77, 8, c)                         # torso
    p.rrect(31, 74, 48, 99, 4, c)                         # legs
    p.rrect(52, 74, 69, 99, 4, c)
    p.circle(50, 24, 10, c)                               # head
    p.pieslice(37, 9, 63, 35, 180, 360, a)                # helmet dome
    p.rrect(35, 21, 65, 25, 2, a)                         # brim
    p.line([(66, 56), (92, 34)], 5, a)                    # rifle (a generic long gun shape)
    p.set_t()


def _person(p: _Pen, c: Colour, a: Colour) -> None:
    p.circle(50, 24, 14, c)
    p.rrect(26, 42, 74, 98, 20, c)
    p.rrect(44, 70, 56, 98, 3, a)


def _snowflake(p: _Pen, c: Colour, a: Colour) -> None:
    for ang in (0, 60, 120):
        tip = _rot([(50, 4), (50, 96)], ang)
        p.line(tip, 6, c)
    for ang in range(0, 360, 60):
        for d in (-1, 1):
            base = _rot([(50, 18), (50 + d * 11, 8)], ang)
            p.line(base, 4, c)
    p.circle(50, 50, 7, a)


def _drone(p: _Pen, c: Colour, a: Colour) -> None:
    for (x0, y0, x1, y1) in ((42, 46, 20, 28), (58, 46, 80, 28), (42, 56, 20, 74), (58, 56, 80, 74)):
        p.line([(x0, y0), (x1, y1)], 5, c)
        p.ellipse(x1 - 14, y1 - 4, x1 + 14, y1 + 4, fill=a)
    p.rrect(38, 42, 62, 60, 7, c)
    p.circle(50, 64, 4.5, a)


def _tank(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(8, 62, 92, 86, 11, a)                         # tracks
    for cx in (22, 38, 54, 70, 84):
        p.circle(cx, 74, 5, c)
    p.rrect(14, 48, 86, 66, 5, c)                         # hull
    p.rrect(32, 30, 68, 52, 7, c)                         # turret
    p.rrect(62, 37, 99, 43, 2, c)                         # gun
    p.circle(46, 38, 4, a)


def _truck(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(6, 32, 60, 68, 3, c)                          # cargo
    p.poly([(62, 44), (80, 44), (93, 57), (93, 68), (62, 68)], c)
    p.poly([(66, 48), (78, 48), (87, 57), (66, 57)], a)   # cab window
    for cx in (22, 42, 76):
        p.circle(cx, 72, 9, a)
        p.circle(cx, 72, 3.5, c)


def _missile(p: _Pen, c: Colour, a: Colour) -> None:
    rot = lambda pts: _rot(pts, 40)
    p.poly(rot([(45, 16), (55, 16), (55, 76), (45, 76)]), c)
    p.poly(rot([(45, 18), (50, 2), (55, 18)]), a)         # nose
    p.poly(rot([(45, 58), (33, 80), (45, 76)]), a)        # fins
    p.poly(rot([(55, 58), (67, 80), (55, 76)]), a)
    p.poly(rot([(46, 78), (50, 97), (54, 78)]), (255, 170, 50, 255))   # exhaust


def _star(cx: float, cy: float, r_out: float, r_in: float, n: int, start: float = -90.0) -> List[Tuple[float, float]]:
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        ang = math.radians(start + i * 180.0 / n)
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _explosion(p: _Pen, c: Colour, a: Colour) -> None:
    p.poly(_star(50, 50, 48, 25, 11), c)
    p.poly(_star(50, 50, 30, 15, 9, -80), a)
    p.circle(50, 50, 8, (255, 244, 200, 255))


def _tree(p: _Pen, c: Colour, a: Colour) -> None:
    p.poly([(50, 4), (74, 38), (26, 38)], c)
    p.poly([(50, 22), (80, 62), (20, 62)], c)
    p.poly([(50, 42), (88, 84), (12, 84)], c)
    p.rrect(43, 82, 57, 98, 2, a)


def _pipe(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(8, 33, 92, 67, 6, c)
    p.rrect(2, 26, 16, 74, 3, a)
    p.rrect(84, 26, 98, 74, 3, a)
    p.line([(20, 42), (80, 42)], 4, (255, 255, 255, 120))


def _flame(p: _Pen, c: Colour, a: Colour) -> None:
    p.poly([(50, 3), (64, 26), (80, 50), (76, 76), (62, 94), (38, 94), (24, 76), (20, 50), (34, 32), (42, 48)], c)
    p.poly([(50, 44), (62, 62), (66, 78), (56, 92), (44, 92), (34, 78), (38, 62)], a)


def _shield(p: _Pen, c: Colour, a: Colour) -> None:
    p.poly([(50, 5), (88, 18), (85, 56), (50, 95), (15, 56), (12, 18)], c)
    p.poly([(50, 16), (76, 26), (74, 54), (50, 82), (26, 54), (24, 26)], a)


def _clock(p: _Pen, c: Colour, a: Colour) -> None:
    p.circle(50, 50, 44, outline=c, w=8)
    p.line([(50, 50), (50, 24)], 7, c)
    p.line([(50, 50), (70, 60)], 7, a)
    p.circle(50, 50, 5, c)


def _magnifier(p: _Pen, c: Colour, a: Colour) -> None:
    p.circle(42, 42, 28, outline=c, w=9)
    p.line([(63, 63), (90, 90)], 12, c)
    p.line([(28, 36), (36, 28)], 5, a)


def _question(p: _Pen, c: Colour, a: Colour) -> None:
    p.circle(50, 50, 46, c)
    f = T.font("bold", int(78 * p.n / 100))
    p.d.text((p.n / 2, p.n * 0.53), "?", font=f, fill=a, anchor="mm")


def _check(p: _Pen, c: Colour, a: Colour) -> None:
    p.circle(50, 50, 46, c)
    p.line([(28, 52), (44, 68), (74, 34)], 11, a)


def _cross(p: _Pen, c: Colour, a: Colour) -> None:
    p.circle(50, 50, 46, c)
    p.line([(32, 32), (68, 68)], 11, a)
    p.line([(68, 32), (32, 68)], 11, a)


def _column(p: _Pen, c: Colour, a: Colour) -> None:
    for i in range(4):                                    # four soldiers in single file, shrinking into the distance
        sc = 0.5 - i * 0.05
        _soldier(p, c, a, ox=2 + i * 25, oy=88 - 99 * sc - i * 4, sc=sc)


_DRAW = {"soldier": _soldier, "person": _person, "snowflake": _snowflake, "drone": _drone, "tank": _tank, "truck": _truck, "missile": _missile,
         "explosion": _explosion, "tree": _tree, "pipe": _pipe, "flame": _flame, "shield": _shield, "clock": _clock, "magnifier": _magnifier,
         "question": _question, "check": _check, "cross": _cross, "column": _column}


# ---- second set: vehicles, aircraft, ships, weapons, air defence, field kit --------------------------------------------------------------
def _wheels(p: _Pen, xs, y: float, r: float, c: Colour, a: Colour) -> None:
    for x in xs:
        p.circle(x, y, r, a)
        p.circle(x, y, r * 0.4, c)


def _apc(p: _Pen, c: Colour, a: Colour) -> None:
    p.poly([(6, 66), (12, 44), (70, 40), (92, 56), (94, 66)], c)           # hull
    p.poly([(16, 46), (28, 46), (28, 56), (14, 56)], a)                    # side hatch
    p.rrect(44, 28, 64, 42, 4, c)                                          # small turret
    p.rrect(62, 32, 88, 36, 2, a)                                          # cannon
    _wheels(p, (22, 40, 58, 78), 72, 9, c, a)


def _howitzer(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(8, 62, 88, 82, 9, a)                                           # tracks
    for cx in (20, 36, 52, 68, 80):
        p.circle(cx, 72, 4.5, c)
    p.rrect(14, 46, 66, 66, 5, c)                                          # hull
    p.rrect(24, 28, 62, 50, 6, c)                                          # big turret
    p.line([(56, 36), (98, 12)], 7, a)                                     # long barrel raised
    p.rrect(88, 8, 99, 16, 2, a)


def _mlrs(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(6, 62, 94, 70, 3, c)
    p.poly([(62, 46), (80, 46), (94, 58), (94, 64), (62, 64)], c)
    p.poly([(66, 50), (78, 50), (87, 58), (66, 58)], a)
    p.poly([(10, 58), (60, 26), (66, 34), (16, 62)], a)                    # launcher frame, raised
    for i in range(4):
        o = i * 3.5
        p.line([(14 + o, 54 - o * 0.4), (60 + o, 26 - o * 0.2)], 3, c)
    _wheels(p, (22, 40, 78), 74, 9, c, a)


def _helicopter(p: _Pen, c: Colour, a: Colour) -> None:
    p.line([(12, 24), (88, 24)], 4, a)                                     # main rotor
    p.line([(50, 24), (50, 34)], 4, c)
    p.rrect(26, 34, 70, 62, 14, c)                                         # body
    p.poly([(66, 42), (96, 40), (96, 46), (66, 54)], c)                    # tail boom
    p.poly([(90, 30), (97, 30), (97, 48), (92, 46)], a)                    # tail fin
    p.poly([(30, 38), (44, 38), (44, 50), (28, 50)], a)                    # canopy
    p.line([(26, 70), (74, 70)], 4, a)                                     # skids
    p.line([(36, 62), (34, 70)], 3, a)
    p.line([(62, 62), (64, 70)], 3, a)


def _jet(p: _Pen, c: Colour, a: Colour) -> None:
    pts = [(50, 4), (57, 30), (96, 62), (96, 70), (57, 60), (54, 84), (68, 94), (68, 98), (50, 92), (32, 98), (32, 94), (46, 84), (43, 60), (4, 70), (4, 62), (43, 30)]
    p.poly(pts, c)
    p.poly([(46, 18), (54, 18), (52, 36), (48, 36)], a)                    # canopy


def _ship(p: _Pen, c: Colour, a: Colour) -> None:
    p.poly([(4, 62), (96, 62), (84, 80), (16, 80)], c)                     # hull
    p.rrect(34, 46, 62, 62, 2, c)                                          # superstructure
    p.rrect(44, 36, 54, 48, 2, a)
    p.line([(60, 56), (86, 50)], 3, a)                                     # deck gun
    p.line([(49, 22), (49, 38)], 2.5, a)                                   # mast
    p.line([(2, 88), (98, 88)], 3, a)


def _radar(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(38, 66, 62, 82, 3, c)
    p.rrect(14, 82, 86, 90, 3, a)
    p.pieslice(14, 10, 86, 74, 180, 360, a)                                # dish
    p.line([(50, 42), (50, 66)], 4, c)
    p.circle(50, 40, 4, c)
    for r in (18, 30):
        p.line([(76 + r * 0.2, 14 - r * 0.1), (82 + r * 0.2, 8 - r * 0.1)], 2, c)


def _aa_launcher(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(6, 62, 94, 70, 3, c)
    p.poly([(66, 48), (82, 48), (94, 58), (94, 64), (66, 64)], c)
    p.poly([(70, 52), (80, 52), (88, 58), (70, 58)], a)
    for i in range(3):
        o = i * 7
        p.poly(_rot([(16 + o, 20), (22 + o, 20), (22 + o, 60), (16 + o, 60)], 28, 30, 62), a)   # canisters tilted up
        p.poly(_rot([(16 + o, 14), (19 + o, 6), (22 + o, 14)], 28, 30, 62), c)
    _wheels(p, (22, 42, 78), 74, 9, c, a)


def _crate(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(14, 30, 86, 82, 3, c)
    p.rrect(14, 30, 86, 40, 2, a)
    p.line([(14, 56), (86, 56)], 3, a)
    p.line([(50, 40), (50, 82)], 3, a)
    p.rrect(40, 18, 60, 30, 3, a)


def _barrel(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(26, 14, 74, 88, 12, c)
    for y in (28, 50, 72):
        p.rrect(26, y, 74, y + 5, 2, a)
    p.rrect(40, 8, 60, 16, 3, a)


def _tanker(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(8, 34, 64, 66, 15, c)                                          # cylindrical tank
    p.poly([(66, 46), (82, 46), (94, 58), (94, 66), (66, 66)], c)
    p.poly([(70, 50), (80, 50), (88, 58), (70, 58)], a)
    p.rrect(26, 28, 38, 36, 2, a)
    p.circle(48, 50, 4, a)
    _wheels(p, (22, 40, 78), 72, 9, c, a)


def _train(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(6, 34, 36, 68, 3, c)                                           # wagon
    p.rrect(40, 34, 70, 68, 3, c)
    p.poly([(74, 40), (94, 40), (98, 68), (74, 68)], c)                    # loco
    p.rrect(78, 44, 90, 54, 2, a)
    p.line([(2, 78), (98, 78)], 3, a)
    _wheels(p, (16, 28, 50, 62, 82), 72, 5.5, c, a)


def _shell(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(38, 36, 62, 90, 3, c)
    p.poly([(38, 38), (50, 6), (62, 38)], a)
    p.rrect(36, 80, 64, 90, 2, a)


def _bomb(p: _Pen, c: Colour, a: Colour) -> None:
    p.ellipse(22, 40, 78, 70, fill=c)
    p.poly([(76, 46), (96, 36), (96, 74), (76, 64)], c)
    p.poly([(88, 36), (98, 28), (98, 40)], a)
    p.poly([(88, 74), (98, 82), (98, 70)], a)
    p.rrect(44, 34, 56, 42, 2, a)


def _rifle(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(6, 42, 70, 52, 3, c)
    p.rrect(66, 44, 98, 49, 2, a)
    p.poly([(30, 52), (42, 52), (46, 74), (36, 74)], c)                    # magazine
    p.poly([(6, 42), (6, 62), (18, 52), (18, 42)], a)                      # stock
    p.rrect(46, 36, 60, 42, 2, a)


def _mortar(p: _Pen, c: Colour, a: Colour) -> None:
    p.poly(_rot([(44, 8), (56, 8), (56, 70), (44, 70)], 22, 50, 70), c)
    p.poly([(20, 90), (80, 90), (66, 74), (34, 74)], a)
    p.line([(40, 78), (24, 66)], 3, a)
    p.line([(60, 78), (76, 66)], 3, a)


def _binoculars(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(12, 34, 40, 82, 10, c)
    p.rrect(60, 34, 88, 82, 10, c)
    p.rrect(38, 46, 62, 60, 3, a)
    p.circle(26, 30, 11, a)
    p.circle(74, 30, 11, a)
    p.circle(26, 30, 6, c)
    p.circle(74, 30, 6, c)


def _medic(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(10, 22, 90, 82, 10, c)
    p.rrect(42, 32, 58, 72, 2, a)
    p.rrect(30, 47, 70, 57, 2, a)
    p.rrect(38, 14, 62, 24, 4, a)


def _radio(p: _Pen, c: Colour, a: Colour) -> None:
    p.rrect(24, 36, 76, 90, 7, c)
    p.rrect(32, 44, 68, 60, 3, a)
    p.circle(40, 74, 6, a)
    p.circle(60, 74, 6, a)
    p.line([(66, 36), (74, 6)], 3.5, a)


def _tent(p: _Pen, c: Colour, a: Colour) -> None:
    p.poly([(4, 84), (50, 14), (96, 84)], c)
    p.poly([(40, 84), (50, 54), (60, 84)], a)
    p.line([(0, 86), (100, 86)], 3, a)


def _fpv(p: _Pen, c: Colour, a: Colour) -> None:
    for (x1, y1) in ((14, 16), (86, 16), (14, 84), (86, 84)):
        p.line([(50, 50), (x1, y1)], 4, c)
        p.circle(x1, y1, 10, a)
        p.circle(x1, y1, 3, c)
    p.rrect(38, 40, 62, 62, 5, c)
    p.rrect(44, 62, 56, 74, 3, a)                                          # payload under the body


def _convoy(p: _Pen, c: Colour, a: Colour) -> None:
    for i, sc in enumerate((0.56, 0.44, 0.34)):
        ox, oy = 2 + i * 34, 58 - i * 6
        p.set_t(ox, oy, sc)
        _truck(p, c, a)
    p.set_t()


_DRAW.update({"apc": _apc, "howitzer": _howitzer, "mlrs": _mlrs, "helicopter": _helicopter, "jet": _jet, "ship": _ship, "radar": _radar,
              "aa_launcher": _aa_launcher, "crate": _crate, "barrel": _barrel, "tanker": _tanker, "train": _train, "shell": _shell, "bomb": _bomb,
              "rifle": _rifle, "mortar": _mortar, "binoculars": _binoculars, "medic": _medic, "radio": _radio, "tent": _tent, "fpv": _fpv, "convoy": _convoy})
_MORE_DEFAULTS: Dict[str, Tuple[Colour, Colour]] = {
    "apc": ((118, 150, 100, 255), (52, 68, 48, 255)), "howitzer": ((118, 150, 100, 255), (52, 68, 48, 255)), "mlrs": ((150, 160, 124, 255), (58, 64, 52, 255)),
    "helicopter": ((150, 160, 170, 255), (52, 58, 68, 255)), "jet": ((196, 204, 214, 255), (84, 110, 160, 255)), "ship": ((150, 164, 180, 255), (62, 78, 100, 255)),
    "radar": ((196, 204, 214, 255), (84, 110, 160, 255)), "aa_launcher": ((150, 160, 124, 255), (226, 228, 232, 255)),
    "crate": ((176, 140, 88, 255), (96, 70, 40, 255)), "barrel": ((214, 60, 56, 255), (118, 30, 30, 255)), "tanker": ((196, 204, 214, 255), (84, 90, 100, 255)),
    "train": ((150, 160, 124, 255), (58, 64, 52, 255)), "shell": ((214, 190, 120, 255), (150, 110, 50, 255)), "bomb": ((90, 98, 112, 255), (214, 60, 56, 255)),
    "rifle": ((120, 126, 138, 255), (60, 64, 72, 255)), "mortar": ((120, 126, 138, 255), (60, 64, 72, 255)),
    "binoculars": ((90, 98, 112, 255), (196, 204, 214, 255)), "medic": ((242, 242, 242, 255), (214, 60, 56, 255)),
    "radio": ((118, 150, 100, 255), (28, 36, 28, 255)), "tent": ((118, 150, 100, 255), (52, 68, 48, 255)),
    "fpv": ((226, 230, 236, 255), (214, 60, 56, 255)), "convoy": ((150, 160, 124, 255), (58, 64, 52, 255)),
}
DEFAULTS.update(_MORE_DEFAULTS)
NAMES = tuple(DEFAULTS)


@lru_cache(maxsize=192)
def _sticker(name: str, size: int, c: Colour, a: Colour) -> Image.Image:
    p = _Pen(size)
    _DRAW.get(name, _question)(p, c, a)
    return p.finish(size)


def draw_sticker(name: str, size: int = 160, colour=None, accent=None) -> Image.Image:
    """RGBA size x size pictogram. Never raises; an unknown name draws a question mark."""
    name = str(name or "").lower()
    key = name if name in DEFAULTS else "question"
    dc, da = DEFAULTS[key]
    size = max(8, min(1024, int(size)))
    return _sticker(key, size, _rgba(colour, dc), _rgba(accent, da)).copy()


@lru_cache(maxsize=64)
def _soldiers(n: int, height: int, c: Colour, a: Colour, gap: float) -> Image.Image:
    unit = max(8, int(height))
    step = int(unit * (0.56 + gap))
    w = step * (n - 1) + int(unit * 0.62)
    out = Image.new("RGBA", (max(1, w), unit), (0, 0, 0, 0))
    one = _sticker("soldier", unit, c, a)
    crop = one.crop((int(unit * 0.16), 0, int(unit * 0.82), unit))      # trim the empty sides of the design box
    for i in range(n):
        out.alpha_composite(crop, (i * step, 0))
    return out


def soldiers(n: int, height: int = 120, colour=None, accent=None, gap: float = 0.12) -> Image.Image:
    dc, da = DEFAULTS["soldier"]
    return _soldiers(max(1, min(40, int(n))), int(height), _rgba(colour, dc), _rgba(accent, da), float(gap)).copy()
