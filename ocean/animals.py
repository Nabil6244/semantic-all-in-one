"""Code-drawn animals for the ocean stage (docs/ocean/PATTERNS.md section 3, plan step 2): flat 2D, side-on, thick dark
outline, two tones (dark back / light belly), one cartoon eye. Our own drawings, made from simple shapes, no reference art.

    draw(name, width=520, ph=0, **args) -> RGBA, facing right
    stage kind "animal": args {"name", "width", "face": "left"|"right", "jaw": bool, "silhouette": bool,
                               "color": [r,g,b], "eye": "red"|None, "scars": bool}

`ph` (0..PHASES-1) is the swim phase: the tail / flukes swing, squid arms wave, diver fins kick. ocean.stage feeds it from
the frame time, so every animal on screen keeps swimming while it floats.
Names: great_white, shark, megalodon, orca, humpback, sperm_whale, dolphin, seal, squid, colossal_squid, diver, boat, cage, tooth.
Unknown names draw a dark silhouette shark (never a blank).
Every shape is in units where the animal is ~100 long; points are smoothed (Chaikin) and drawn at SS x then reduced, so edges
are soft at any size.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from . import look as L

PHASES = 8
SS = 3                                   # supersampling
OUTLINE = (18, 24, 30, 255)
Pt = Tuple[float, float]


# ------------------------------------------------------------------------------------------------------------------ geometry

def _smooth(pts: Sequence[Pt], n: int = 2) -> List[Pt]:
    p = list(pts)
    for _ in range(n):
        q: List[Pt] = []
        for i in range(len(p)):
            a, b = p[i], p[(i + 1) % len(p)]
            q += [(a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25), (a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75)]
        p = q
    return p


def _rot(pts: Sequence[Pt], pivot: Pt, deg: float) -> List[Pt]:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    px, py = pivot
    return [(px + (x - px) * c - (y - py) * s, py + (x - px) * s + (y - py) * c) for x, y in pts]


def _ellipse(cx: float, cy: float, rx: float, ry: float, n: int = 20) -> List[Pt]:
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _swing(ph: int, amp: float, off: float = 0.0) -> float:
    return amp * math.sin(2 * math.pi * ph / PHASES + off)


# ------------------------------------------------------------------------------------------------------------------ specs
# A spec: body (outline pts), color, belly (pts, clipped to body), belly_color, patches [(pts, color)] clipped to body,
# back [(pts, color, pivot, amp)] behind the body, front [(pts, color, pivot, amp)] over it, eye (x, y, r), lines [(pts, w)],
# extra(draw, T, ph, args) for special bits (teeth, arms, bubbles).

def _shark(args: Dict[str, Any]) -> Dict[str, Any]:
    col = tuple(args.get("color") or (112, 126, 138)) + (255,)
    body = [(100, 20), (93, 13), (80, 9), (62, 7), (45, 8), (30, 11), (18, 15), (10, 18.5),
            (10, 22), (18, 24), (32, 28), (50, 31), (68, 30), (84, 27), (94, 24)]
    belly = [(99, 21), (86, 22.5), (70, 21.5), (52, 23), (36, 24.5), (20, 22.5), (6, 21), (6, 40), (100, 40)]
    tail = [(13, 16.5), (1, -3), (-2.5, -2), (4, 19.5), (-1, 33), (2.5, 33.5), (13, 24)]
    spec = {
        "body": body, "color": col, "belly": belly, "belly_color": (232, 236, 236, 255),
        "back": [(tail, col, (12, 20), 9.0)],
        "front": [([(63, 10), (53, -9), (49.5, -8.5), (44.5, 10.5)], col, None, 0.0),
                  ([(67, 27), (57, 41), (53.5, 40), (58, 27)], col, (62, 27), 4.0),
                  ([(24, 13.5), (21, 9), (19.5, 9.5), (19, 15)], col, None, 0.0)],
        "eye": (83, 15.5, 1.7),
        "lines": [([(72, 17), (71, 24)], 0.8), ([(69.5, 17.5), (68.5, 24.5)], 0.8), ([(67, 18), (66, 25)], 0.8),
                  ([(96, 23.5), (86, 25.5)], 1.0)],
    }
    if args.get("scars"):
        spec["lines"] += [([(48, 12), (40, 17)], 0.7), ([(44, 11), (37, 15)], 0.7), ([(58, 13), (54, 18)], 0.7)]
    return spec


def _megalodon(args: Dict[str, Any]) -> Dict[str, Any]:
    a = dict(args)
    a.setdefault("color", (78, 86, 96))
    a.setdefault("scars", True)
    spec = _shark(a)
    spec["body"] = [(100, 21), (94, 12), (80, 7), (62, 5), (45, 6.5), (30, 10), (18, 15), (10, 18.5),
                    (10, 22), (18, 25), (32, 30), (50, 34), (68, 33), (84, 30), (95, 26)]
    spec["jaw_default"] = True
    return spec


def _toothed_whale(args: Dict[str, Any], col: Tuple[int, ...]) -> Dict[str, Any]:
    flukes = [(11, 19), (1, 13.5), (-4, 14), (2, 20.5), (-4, 27), (1, 27.5), (11, 23)]
    return {"back": [(flukes, col, (11, 21), 10.0)]}


def _orca(args: Dict[str, Any]) -> Dict[str, Any]:
    black = (20, 22, 26, 255)
    white = (236, 238, 238, 255)
    spec = _toothed_whale(args, black)
    spec.update({
        "body": [(100, 22), (98, 16), (90, 11), (75, 8), (58, 7), (40, 9), (25, 13), (14, 17), (9, 19),
                 (9, 22.5), (16, 24.5), (30, 29), (48, 33), (66, 33), (82, 30), (94, 27)],
        "color": black,
        "belly": [(97, 25.5), (86, 27.5), (72, 28.5), (58, 29.5), (46, 29.5), (40, 28), (33, 21), (26, 21.5), (29, 28),
                  (29, 40), (100, 40)],
        "belly_color": white,
        "patches": [(_ellipse(80, 16.5, 7, 2.8), white), (_ellipse(52, 9.5, 9, 3.2), (120, 126, 132, 255))],
        "front": [([(62, 10.5), (57, -17), (54.5, -16.5), (49, 11)], black, None, 0.0),
                  ([(77, 30), (71, 42), (65, 42), (69, 30)], black, (73, 30), 5.0)],
        "eye": (86.5, 18.5, 1.2),
        "eye_color": (10, 10, 12, 255),
    })
    return spec


def _humpback(args: Dict[str, Any]) -> Dict[str, Any]:
    col = tuple(args.get("color") or (66, 74, 86)) + (255,)
    pale = (214, 220, 224, 255)
    spec = _toothed_whale(args, col)
    spec["back"][0] = ([(11, 19), (0, 12), (-6, 12.5), (1, 20.5), (-6, 29), (0, 29.5), (11, 23)], col, (11, 21), 8.0)
    spec.update({
        "body": [(100, 20), (96, 15), (86, 11), (70, 9), (52, 9), (35, 11), (20, 15), (10, 19),
                 (10, 22), (22, 25), (40, 30), (60, 32), (78, 30), (90, 27), (97, 24)],
        "color": col,
        "belly": [(98, 23), (88, 26), (74, 28), (60, 29), (44, 28), (44, 40), (100, 40)],
        "belly_color": (150, 158, 168, 255),
        "front": [([(40, 10.5), (36, 5.5), (33, 6), (31, 11.5)], col, None, 0.0),
                  ([(74, 28), (52, 49), (47, 47.5), (67, 28)], pale, (71, 28), 4.0)],
        "eye": (80, 22.5, 1.3),
        "lines": [([(95, 25), (66, 30.5)], 0.6), ([(93, 26.5), (66, 31.5)], 0.6), ([(90, 28), (68, 32)], 0.6)],
        "knobs": [(92, 13), (95.5, 16), (88, 11.5), (85, 11), (90, 15)],
    })
    return spec


def _sperm_whale(args: Dict[str, Any]) -> Dict[str, Any]:
    col = tuple(args.get("color") or (92, 96, 106)) + (255,)
    spec = _toothed_whale(args, col)
    spec.update({
        "body": [(100, 11), (100, 25), (97, 28), (84, 28.5), (70, 29), (55, 30), (40, 28), (24, 25), (10, 22),
                 (10, 19), (20, 16), (35, 12.5), (50, 10), (65, 8.5), (85, 8), (98, 9)],
        "color": col,
        "front": [([(36, 12.5), (32, 8.5), (29, 9), (28, 13.5)], col, None, 0.0),
                  ([(66, 28), (60, 35), (57, 34), (61, 28)], col, (63, 28), 5.0)],
        "eye": (70, 22, 1.2),
        "lines": [([(95, 27.5), (72, 27.5)], 0.9), ([(90, 12), (84, 14)], 0.5), ([(80, 11), (74, 13)], 0.5),
                  ([(56, 14), (48, 18)], 0.5), ([(46, 16), (40, 20)], 0.5)],
    })
    return spec


def _dolphin(args: Dict[str, Any]) -> Dict[str, Any]:
    col = tuple(args.get("color") or (120, 134, 150)) + (255,)
    spec = _toothed_whale(args, col)
    spec.update({
        "body": [(100, 21.5), (92, 19.5), (88, 16), (84, 13), (72, 11), (55, 11), (40, 13), (25, 16), (12, 19),
                 (12, 22), (28, 25), (46, 28), (64, 28), (80, 25), (90, 23)],
        "color": col,
        "belly": [(99, 22.5), (90, 22), (80, 21.5), (64, 23), (46, 24.5), (30, 23), (30, 40), (100, 40)],
        "belly_color": (226, 232, 236, 255),
        "front": [([(57, 13), (49, 0), (46.5, 0.5), (41.5, 14)], col, None, 0.0),
                  ([(74, 25), (66, 33), (63.5, 32), (68, 25)], col, (71, 25), 5.0)],
        "eye": (85.5, 18, 1.1),
    })
    return spec


def _seal(args: Dict[str, Any]) -> Dict[str, Any]:
    col = tuple(args.get("color") or (122, 92, 64)) + (255,)
    flip = [(16, 21), (0, 16), (-2.5, 18.5), (8, 23), (-2.5, 28), (0.5, 30), (16, 25)]
    return {
        "body": [(100, 20), (97, 14), (91, 12), (85, 13), (80, 15.5), (70, 14.5), (55, 14), (40, 16), (25, 19), (14, 21),
                 (14, 24), (30, 27), (50, 29), (70, 27.5), (84, 24.5), (92, 24.5), (98, 23)],
        "color": col,
        "belly": [(99, 21.5), (92, 21.5), (84, 22), (70, 24), (50, 26), (30, 25), (30, 40), (100, 40)],
        "belly_color": (172, 142, 106, 255),
        "back": [(flip, col, (15, 23), 12.0)],
        "front": [([(71, 26), (63, 36), (60, 35), (65, 26)], col, (68, 26), 8.0)],
        "eye": (92.5, 16, 1.3),
        "lines": [([(99, 19.5), (104, 18)], 0.35), ([(99, 20.5), (104, 21)], 0.35)],
    }


def _squid(args: Dict[str, Any]) -> Dict[str, Any]:
    col = tuple(args.get("color") or (180, 54, 52)) + (255,)
    dark = tuple(max(0, c - 28) for c in col[:3]) + (255,)
    return {
        "body": [(100, 20), (92, 12), (75, 10), (55, 11), (42, 13), (42, 27), (55, 29), (75, 30), (92, 28)],
        "color": col,
        "patches": [(_ellipse(68, 13, 26, 3.2), dark)],
        "back": [([(97, 16), (88, 2), (79, 11)], col, None, 0.0), ([(97, 24), (88, 38), (79, 29)], col, None, 0.0)],
        "front": [(_ellipse(37, 20, 7.5, 8), col, None, 0.0)],
        "eye": (38, 18.5, 3.6),
        "eye_white": True,
        "arms": {"root": (32, 20), "col": col, "n": 8, "len": 26, "tentacle": 42},
    }


def _colossal(args: Dict[str, Any]) -> Dict[str, Any]:
    a = dict(args)
    a.setdefault("color", (150, 40, 44))
    spec = _squid(a)
    spec["hooks"] = True
    return spec


def _diver(args: Dict[str, Any]) -> Dict[str, Any]:
    suit = (24, 26, 30, 255)
    fin = (238, 128, 34, 255)
    return {
        "body": [(78, 13), (78, 22), (36, 21.5), (34, 14)],
        "color": suit,
        "back": [([(36, 15), (10, 13), (10, 16), (36, 18)], suit, (36, 16), 7.0),
                 ([(36, 18), (10, 21), (10, 24), (36, 21)], suit, (36, 20), -7.0),
                 ([(11, 12), (-6, 9), (-6, 17), (11, 16)], fin, (36, 16), 7.0),
                 ([(11, 20.5), (-6, 21), (-6, 28), (11, 24.5)], fin, (36, 20), -7.0)],
        "front": [([(44, 9), (70, 9), (70, 14), (44, 14)], (160, 168, 176, 255), None, 0.0),
                  (_ellipse(85, 15.5, 6.5, 6), suit, None, 0.0),
                  ([(87, 12), (92, 12.5), (92, 17), (87, 17)], fin, None, 0.0),
                  ([(74, 19), (92, 24), (91, 26.5), (73, 22)], suit, (74, 20), 3.0)],
        "eye": None,
        "bubbles": [(96, 8), (99, 2), (95, -4)],
    }


def _boat(args: Dict[str, Any]) -> Dict[str, Any]:
    hull = (26, 30, 36, 255)
    return {"body": [(0, 10), (100, 10), (93, 20), (6, 20)], "color": hull,
            "front": [([(28, 1), (62, 1), (62, 10), (28, 10)], hull, None, 0.0),
                      ([(0, 12.5), (100, 12.5), (99, 14), (1, 14)], (190, 60, 50, 255), None, 0.0)],
            "eye": None, "static": True}


def _cage(args: Dict[str, Any]) -> Dict[str, Any]:
    bar = (22, 26, 32, 255)
    lines = [([(x, 0), (x, 60)], 1.4) for x in range(0, 101, 10)] + [([(0, y), (100, y)], 1.4) for y in range(0, 61, 12)]
    return {"body": [(0, 0), (100, 0), (100, 60), (0, 60)], "color": (0, 0, 0, 0), "outline_w": 2.2, "lines": lines,
            "line_color": bar, "eye": None, "static": True}


def _tooth(args: Dict[str, Any]) -> Dict[str, Any]:
    enamel = tuple(args.get("color") or (84, 92, 104)) + (255,)
    return {"body": [(50, 0), (82, 78), (18, 78)], "color": enamel,
            "back": [([(10, 72), (90, 72), (96, 96), (62, 90), (50, 100), (38, 90), (4, 96)], (150, 112, 72, 255), None, 0.0)],
            "patches": [([(46, 6), (52, 6), (40, 74), (32, 74)], (126, 136, 148, 255))],
            "eye": None, "static": True, "serrated": True}


SPECS = {"great_white": _shark, "shark": _shark, "megalodon": _megalodon, "orca": _orca, "humpback": _humpback,
         "sperm_whale": _sperm_whale, "dolphin": _dolphin, "seal": _seal, "sea_lion": _seal, "squid": _squid,
         "colossal_squid": _colossal, "diver": _diver, "boat": _boat, "cage": _cage, "tooth": _tooth}
SWIMMERS = tuple(n for n in SPECS if n not in ("boat", "cage", "tooth"))
NAMES = tuple(SPECS)
SLOW = ("humpback", "sperm_whale", "orca")


# ------------------------------------------------------------------------------------------------------------------ drawing

class _T:
    """Unit -> pixel transform for one drawing."""

    def __init__(self, x0: float, y0: float, u: float, pad: float) -> None:
        self.x0, self.y0, self.u, self.pad = x0, y0, u, pad

    def __call__(self, pts: Sequence[Pt]) -> List[Pt]:
        return [((x - self.x0) * self.u + self.pad, (y - self.y0) * self.u + self.pad) for x, y in pts]


def _all_pts(spec: Dict[str, Any]) -> List[Pt]:
    pts = list(spec["body"])
    for key in ("back", "front"):
        for part in spec.get(key) or []:
            pts += list(part[0])
    if spec.get("arms"):
        r = spec["arms"]["root"]
        pts += [(r[0] - spec["arms"]["tentacle"] - 4, r[1] - 12), (r[0] - spec["arms"]["tentacle"] - 4, r[1] + 12)]
    for b in spec.get("bubbles") or []:
        pts.append(b)
    return pts


def _poly(d: ImageDraw.ImageDraw, pts: Sequence[Pt], fill, ow: float, smooth: bool = True) -> None:
    p = _smooth(pts) if smooth and len(pts) > 3 else list(pts)
    d.polygon(p, fill=fill)
    if ow > 0:
        d.line(p + [p[0]], fill=OUTLINE, width=max(1, int(round(ow))), joint="curve")


def _part_pts(part, ph: int, static: bool) -> List[Pt]:
    pts, _col, pivot, amp = part
    if pivot is None or amp == 0 or static:
        return list(pts)
    return _rot(pts, pivot, _swing(ph, amp))


def _arms(d: ImageDraw.ImageDraw, T: _T, spec: Dict[str, Any], ph: int, ow: float, silhouette: bool) -> None:
    a = spec["arms"]
    rx, ry = a["root"]
    col = (6, 10, 16, 255) if silhouette else a["col"]
    for i in range(a["n"] + 2):
        tentacle = i >= a["n"]
        ln = a["tentacle"] if tentacle else a["len"] * (0.85 + 0.3 * ((i * 37) % 10) / 10)
        spread = (i - (a["n"] - 1) / 2) / a["n"] * 18 if not tentacle else (-6 if i == a["n"] else 6)
        pts: List[Pt] = []
        steps = 10
        for s in range(steps + 1):
            k = s / steps
            wave = math.sin(2 * math.pi * ph / PHASES + i * 0.8 + k * 3.0) * 2.4 * k
            pts.append((rx - ln * k, ry + spread * k * 0.8 + spread * 0.12 + wave))
        px = T(pts)
        base_w = (4.6 if not tentacle else 2.4) * T.u
        for s in range(steps):
            w = max(1.0, base_w * (1 - s / steps * 0.75))
            d.line([px[s], px[s + 1]], fill=OUTLINE, width=int(w + ow))
        for s in range(steps):
            w = max(1.0, base_w * (1 - s / steps * 0.75))
            d.line([px[s], px[s + 1]], fill=col, width=int(w))
        if not silhouette:
            for s in range(1, steps, 2):
                x, y = px[s]
                r = max(1.0, T.u * 0.55 * (1 - s / steps * 0.6))
                fill = (238, 226, 214, 255) if not spec.get("hooks") else (244, 236, 220, 255)
                d.ellipse((x - r, y - r, x + r, y + r), fill=fill)
                if spec.get("hooks"):
                    d.line([(x - r, y), (x + r * 0.6, y - r * 1.8)], fill=fill, width=max(1, int(r * 0.7)))


def _teeth(d: ImageDraw.ImageDraw, T: _T, spec: Dict[str, Any], ow: float) -> None:
    mouth = T([(99.5, 22), (84, 25.5), (96, 30)])
    d.polygon(mouth, fill=(90, 22, 30, 255))
    d.line(mouth + [mouth[0]], fill=OUTLINE, width=max(1, int(ow * 0.7)))
    for i in range(6):
        k = i / 6
        top = T([(97 - 12 * k, 22.4 + 3 * k)])[0]
        bot = T([(95.5 - 10.5 * k, 29.6 - 3.8 * k)])[0]
        s = T.u * 1.2
        d.polygon([(top[0] - s * 0.6, top[1]), (top[0] + s * 0.6, top[1]), (top[0], top[1] + s * 1.6)], fill=(246, 244, 236, 255))
        d.polygon([(bot[0] - s * 0.6, bot[1]), (bot[0] + s * 0.6, bot[1]), (bot[0], bot[1] - s * 1.6)], fill=(246, 244, 236, 255))


@lru_cache(maxsize=512)
def _draw_cached(name: str, width: int, ph: int, face: str, jaw: bool, silhouette: bool, color: Tuple[int, ...],
                 eye: str, scars: bool) -> Image.Image:
    args: Dict[str, Any] = {"scars": scars}
    if color:
        args["color"] = color
    spec = SPECS.get(name, _shark)(args)
    if name not in SPECS:
        silhouette = True
    static = bool(spec.get("static"))
    pts = _all_pts(spec)
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    u = width * SS / max(1.0, x1 - x0)
    pad = 6 * SS
    T = _T(x0, y0, u, pad)
    img = Image.new("RGBA", (int((x1 - x0) * u + 2 * pad), int((y1 - y0) * u + 2 * pad)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ow = float(spec.get("outline_w", 1.1)) * u
    shade = (6, 10, 16, 255)

    def C(c):
        return shade if silhouette else c

    for part in spec.get("back") or []:
        _poly(d, T(_part_pts(part, ph, static)), C(part[1]), ow, smooth=not static)
    if spec.get("arms"):
        _arms(d, T, spec, ph, ow, silhouette)

    body = T(spec["body"])
    body_s = _smooth(body) if not static else body
    if silhouette or not (spec.get("belly") or spec.get("patches")):
        _poly(d, body, C(spec["color"]), ow, smooth=not static)
    else:
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.polygon(body_s, fill=spec["color"])
        if spec.get("belly"):
            ld.polygon(_smooth(T(spec["belly"])), fill=spec["belly_color"])
        for pp, pc in spec.get("patches") or []:
            ld.polygon(_smooth(T(pp)) if len(pp) > 4 else T(pp), fill=pc)
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).polygon(body_s, fill=255)
        img.paste(layer, (0, 0), mask)
        d = ImageDraw.Draw(img)
        d.line(body_s + [body_s[0]], fill=OUTLINE, width=max(1, int(round(ow))), joint="curve")

    if not silhouette:
        lc = spec.get("line_color", OUTLINE)
        for lp, lw in spec.get("lines") or []:
            d.line(T(lp), fill=lc, width=max(1, int(lw * u)))
        for kx, ky in spec.get("knobs") or []:
            c = T([(kx, ky)])[0]
            r = u * 0.9
            d.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill=(110, 118, 128, 255), outline=OUTLINE)
        if spec.get("serrated"):
            for side in ((50, 0, 82, 78), (50, 0, 18, 78)):
                for i in range(1, 12):
                    k = i / 12
                    x, y = side[0] + (side[2] - side[0]) * k, side[1] + (side[3] - side[1]) * k
                    c = T([(x, y)])[0]
                    d.ellipse((c[0] - u * 0.6, c[1] - u * 0.6, c[0] + u * 0.6, c[1] + u * 0.6), fill=OUTLINE)
    if (jaw or spec.get("jaw_default")) and name in ("great_white", "shark", "megalodon") and not silhouette:
        _teeth(d, T, spec, ow)

    for part in spec.get("front") or []:
        _poly(d, T(_part_pts(part, ph, static)), C(part[1]), ow, smooth=not static)

    e = spec.get("eye")
    if e:
        cx, cy = T([(e[0], e[1])])[0]
        r = e[2] * u
        if silhouette:
            if eye == "red":
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(236, 50, 40, 255))
        elif spec.get("eye_white"):
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(240, 232, 214, 255), outline=OUTLINE, width=max(1, int(ow * 0.6)))
            pr = r * 0.55
            d.ellipse((cx + r * 0.1 - pr, cy - pr, cx + r * 0.1 + pr, cy + pr), fill=(14, 12, 12, 255))
            d.ellipse((cx + r * 0.25, cy - r * 0.45, cx + r * 0.5, cy - r * 0.2), fill=(255, 255, 255, 255))
        else:
            fill = (236, 50, 40, 255) if eye == "red" else spec.get("eye_color", (8, 10, 12, 255))
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
            g = r * 0.38
            d.ellipse((cx + r * 0.15, cy - r * 0.55, cx + r * 0.15 + g, cy - r * 0.55 + g), fill=(255, 255, 255, 230))
    for i, b in enumerate(spec.get("bubbles") or []):
        if silhouette:
            break
        cx, cy = T([b])[0]
        r = u * (1.2 + 0.5 * i) * (0.8 + 0.2 * math.sin(2 * math.pi * ph / PHASES + i))
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(220, 238, 246, 220), width=max(1, int(u * 0.4)))

    out = img.resize((max(1, img.width // SS), max(1, img.height // SS)), Image.LANCZOS)
    if face == "left":
        out = out.transpose(Image.FLIP_LEFT_RIGHT)
    return out


def draw(name: str, width: int = 520, ph: int = 0, **args: Any) -> Image.Image:
    color = tuple(int(c) for c in (args.get("color") or ())[:3])
    return _draw_cached(str(name), int(width), int(ph) % PHASES, str(args.get("face", "right")), bool(args.get("jaw")),
                        bool(args.get("silhouette")), color, str(args.get("eye") or ""), bool(args.get("scars")))


def phase_at(name: str, t: float, seed: str = "") -> int:
    """Swim phase for an animal at time t (whales beat slower; each element gets its own offset)."""
    cycle = 2.4 if name in SLOW else 1.3
    off = (sum(map(ord, seed)) % 97) / 97.0
    return int(((t / cycle) + off) * PHASES) % PHASES


def stage_kind(a: Dict[str, Any]) -> Image.Image:
    """Factory for the stage kind 'animal'."""
    a = dict(a)
    return draw(a.pop("name", "great_white"), int(a.pop("width", 520)), int(a.pop("_ph", 0)), **a)
