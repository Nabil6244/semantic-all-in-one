"""Game Launch 'hud' cards: animated mock-ups of game systems (minimap, wanted stars, heat icons, lock tiers, carry limits, trunk
space, cash, phone scanner, weak points). Every card carries an ILLUSTRATION tag: they explain a system, they are not game footage.

layers(template, params, folder, stem) -> [{"png", "at", "blink"}]: full-frame transparent PNGs; `at` is when the layer fades in
as a share of the shot (0..1), `blink` makes it flash. The renderer lays them over the row's trailer shot (blurred) or navy.

CSV: shot=hud, title=template, subtitle=params ("gta5", "upto=3", "lit=face,outfit", "focus=3"...), game_clip = background."""
from __future__ import annotations

import math
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw

from . import look as L

W, H = L.W, L.H
PINK, TEAL, NAVY, WHITE = L.PINK, L.TEAL, L.NAVY, L.WHITE
RED, BLUE, GREEN, AMBER = (235, 40, 50), (40, 110, 255), (40, 200, 120), (255, 190, 40)
TEMPLATES = ("minimap", "stars", "heat", "tiers", "carry", "capacity", "cash", "waink", "focus", "economy", "safe", "agencies",
             "profile", "checklist", "cards", "stats", "download", "scam", "unlock", "nodisc", "garage", "loop", "saves", "controller", "archive")


def parse(params: str) -> Dict[str, str]:
    out = {}
    for part in str(params or "").replace(";", " ").split():
        k, _, v = part.partition("=")
        out[k.strip().lower()] = v.strip() if v else "1"
    return out


def _new(alpha=0) -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, alpha))


def _save(img: Image.Image, folder: Path, stem: str, k: int) -> str:
    f = folder / f"{stem}_hud{k:02d}.png"
    img.save(f)
    return str(f)


def _frame(head: str, sub: str = "") -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, H), fill=NAVY + (120,))
    L.shadow_text(img, (W // 2, 120), head, L.fit(head, L.F_HEAD, 104, W - 400))
    if sub:
        L.shadow_text(img, (W // 2, 200), sub, L.fit(sub, L.F_TAG, 36, W - 400), fill=TEAL)
    L.pill(img, (60, 56), "ILLUSTRATION", (90, 90, 110), 30)
    return img


def _star(d: ImageDraw.ImageDraw, cx, cy, r, fill=None, outline=WHITE, width=5):
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill, outline=outline + (255,) if len(outline) == 3 else outline, width=width)


def _label(img, xy, text, size=40, fill=WHITE, anchor="mm"):
    L.shadow_text(img, xy, text, L.font(L.F_HEAD, size), fill=fill, anchor=anchor, blur=6)


def _small(img, xy, text, size=26, fill=(225, 225, 235), anchor="mm"):
    L.shadow_text(img, xy, text, L.font(L.F_TAG, size), fill=fill, anchor=anchor, blur=5)


# ---------------------------------------------------------------------------------------------------------------- icons

def icon(d: ImageDraw.ImageDraw, kind: str, cx: float, cy: float, s: float, col) -> None:
    c = col + (255,)
    w = max(4, int(s * 0.07))
    if kind == "face":
        d.ellipse((cx - s * .38, cy - s * .45, cx + s * .38, cy + s * .4), outline=c, width=w)
        for ex in (-.14, .14):
            d.ellipse((cx + s * ex - s * .05, cy - s * .12, cx + s * ex + s * .05, cy - s * .02), fill=c)
        d.arc((cx - s * .18, cy - s * .02, cx + s * .18, cy + s * .24), 20, 160, fill=c, width=w)
    elif kind == "outfit":
        d.polygon([(cx - s * .45, cy - s * .3), (cx - s * .18, cy - s * .45), (cx - s * .08, cy - s * .35), (cx + s * .08, cy - s * .35),
                   (cx + s * .18, cy - s * .45), (cx + s * .45, cy - s * .3), (cx + s * .35, cy - s * .1), (cx + s * .25, cy - s * .15),
                   (cx + s * .25, cy + s * .45), (cx - s * .25, cy + s * .45), (cx - s * .25, cy - s * .15), (cx - s * .35, cy - s * .1)],
                  outline=c, width=w)
    elif kind == "weapon":
        d.polygon([(cx - s * .45, cy - s * .25), (cx + s * .45, cy - s * .25), (cx + s * .45, cy - s * .05), (cx - s * .05, cy - s * .05),
                   (cx - s * .1, cy + s * .4), (cx - s * .35, cy + s * .4), (cx - s * .3, cy - s * .05), (cx - s * .45, cy - s * .05)],
                  outline=c, width=w)
    elif kind == "vehicle":
        d.rounded_rectangle((cx - s * .48, cy - s * .05, cx + s * .48, cy + s * .25), radius=int(s * .08), outline=c, width=w)
        d.polygon([(cx - s * .28, cy - s * .05), (cx - s * .15, cy - s * .3), (cx + s * .2, cy - s * .3), (cx + s * .32, cy - s * .05)],
                  outline=c, width=w)
        for wx in (-.28, .28):
            d.ellipse((cx + s * wx - s * .11, cy + s * .14, cx + s * wx + s * .11, cy + s * .36), fill=c)
    elif kind == "partner":
        for ox in (-.2, .2):
            d.ellipse((cx + s * ox - s * .13, cy - s * .4, cx + s * ox + s * .13, cy - s * .14), outline=c, width=w)
            d.arc((cx + s * ox - s * .25, cy - s * .05, cx + s * ox + s * .25, cy + s * .55), 180, 360, fill=c, width=w)
    elif kind == "lock":
        d.rounded_rectangle((cx - s * .32, cy - s * .05, cx + s * .32, cy + s * .42), radius=int(s * .06), outline=c, width=w)
        d.arc((cx - s * .22, cy - s * .4, cx + s * .22, cy + s * .1), 180, 360, fill=c, width=w)
    elif kind == "camera":
        d.rounded_rectangle((cx - s * .42, cy - s * .2, cx + s * .2, cy + s * .14), radius=int(s * .05), outline=c, width=w)
        d.polygon([(cx + s * .2, cy - s * .08), (cx + s * .42, cy - s * .2), (cx + s * .42, cy + s * .14), (cx + s * .2, cy + s * .02)],
                  outline=c, width=w)
        d.line([(cx - s * .1, cy + s * .14), (cx - s * .1, cy + s * .42)], fill=c, width=w)
        d.ellipse((cx - s * .22, cy - s * .1, cx - s * .02, cy + s * .06), outline=c, width=w)
    elif kind == "build":
        d.ellipse((cx - s * .14, cy - s * .46, cx + s * .14, cy - s * .18), outline=c, width=w)
        d.polygon([(cx - s * .3, cy - s * .1), (cx + s * .3, cy - s * .1), (cx + s * .22, cy + s * .2), (cx + s * .15, cy + s * .46),
                   (cx - s * .15, cy + s * .46), (cx - s * .22, cy + s * .2)], outline=c, width=w)
    elif kind == "bag":
        d.rounded_rectangle((cx - s * .45, cy - s * .15, cx + s * .45, cy + s * .3), radius=int(s * .15), outline=c, width=w)
        d.arc((cx - s * .2, cy - s * .38, cx + s * .2, cy - s * .02), 180, 360, fill=c, width=w)


ICON_NAMES = {"face": "FACE", "outfit": "CLOTHING", "weapon": "WEAPON", "vehicle": "VEHICLE", "partner": "PARTNER",
              "camera": "CAMERAS", "build": "BUILD"}
HEAT = [("face", "FACE"), ("outfit", "OUTFIT"), ("weapon", "WEAPON"), ("vehicle", "VEHICLE"), ("partner", "PARTNER")]


# ---------------------------------------------------------------------------------------------------------------- templates

def _minimap(p, folder, stem):
    """GTA V radar (blips + vision cones) or GTA VI radar (empty) with red/blue flashes at the screen edges."""
    gta5 = p.get("game", p.get("mode", "gta6")) in ("gta5", "5", "v") or "gta5" in p
    out = []
    base = _frame("THE MINIMAP", "GTA V" if gta5 else "GTA VI")
    d = ImageDraw.Draw(base)
    x0, y0, s = W // 2 - 330, 300, 660
    d.rounded_rectangle((x0 - 10, y0 - 10, x0 + s + 10, y0 + s + 10), radius=40, fill=(10, 14, 30, 255), outline=WHITE + (200,), width=6)
    rnd = random.Random(7)
    for _ in range(14):                                    # roads
        if rnd.random() < .5:
            yy = y0 + rnd.randint(30, s - 30)
            d.line([(x0 + 10, yy), (x0 + s - 10, yy + rnd.randint(-60, 60))], fill=(70, 80, 105, 255), width=rnd.choice((6, 10, 14)))
        else:
            xx = x0 + rnd.randint(30, s - 30)
            d.line([(xx, y0 + 10), (xx + rnd.randint(-60, 60), y0 + s - 10)], fill=(70, 80, 105, 255), width=rnd.choice((6, 10, 14)))
    cx, cy = x0 + s / 2, y0 + s / 2
    d.polygon([(cx, cy - 26), (cx + 18, cy + 20), (cx, cy + 10), (cx - 18, cy + 20)], fill=WHITE + (255,))
    out.append({"png": _save(base, folder, stem, 0), "at": 0.0})
    if gta5:
        cops = [(x0 + 150, y0 + 170, 30), (x0 + 500, y0 + 230, 200), (x0 + 420, y0 + 520, 120), (x0 + 120, y0 + 480, 300)]
        for k, (bx, by, ang) in enumerate(cops):
            img = _new()
            dd = ImageDraw.Draw(img)
            a = math.radians(ang)
            pts = [(bx, by)] + [(bx + 210 * math.cos(a + da), by + 210 * math.sin(a + da)) for da in (-0.45, -0.2, 0, 0.2, 0.45)]
            dd.polygon(pts, fill=(255, 60, 60, 70))
            dd.ellipse((bx - 14, by - 14, bx + 14, by + 14), fill=RED + (255,), outline=WHITE + (255,), width=3)
            out.append({"png": _save(img, folder, stem, k + 1), "at": 0.15 + 0.12 * k})
        img = _new()
        _small(img, (W // 2, y0 + s + 60), "EVERY COP AND WHERE THEY'RE LOOKING", 30, fill=(255, 150, 150))
        out.append({"png": _save(img, folder, stem, 9), "at": 0.65})
    else:
        img = _new()
        _small(img, (W // 2, y0 + s + 60), "NO POLICE BLIPS  ·  NO VISION CONES", 30, fill=(150, 255, 230))
        out.append({"png": _save(img, folder, stem, 1), "at": 0.25})
        for k, col in enumerate((RED, BLUE)):              # screen-edge flashes, alternating
            img = _new()
            dd = ImageDraw.Draw(img)
            for i in range(60):
                a = int(150 * (1 - i / 60))
                side = (i, 0, i + 1, H) if k == 0 else (W - i - 1, 0, W - i, H)
                dd.rectangle(side, fill=col + (a,))
            out.append({"png": _save(img, folder, stem, 2 + k), "at": 0.45, "blink": k})
    return out


STAR_STATES = [("HOLLOW", "Silent alarm  ·  they don't know your look", "hollow"),
               ("SOLID WHITE", "Officers can see you right now", "solid"),
               ("FLASHING WHITE", "You broke line of sight", "flash"),
               ("RED", "Search perimeter locked down", "red")]


def _stars(p, folder, stem):
    upto = max(1, min(4, int(p.get("upto", 4))))
    out = [{"png": _save(_frame("THE WANTED STARS", "FOUR STATES"), folder, stem, 0), "at": 0.0}]
    for k in range(upto):
        name, what, kind = STAR_STATES[k]
        img = _new()
        d = ImageDraw.Draw(img)
        y = 330 + k * 165
        cur = k == upto - 1
        if cur:
            d.rounded_rectangle((300, y - 70, W - 300, y + 70), radius=24, fill=(255, 255, 255, 28), outline=PINK + (255,), width=4)
        for j in range(5):
            cx = 400 + j * 78
            if kind == "hollow":
                _star(d, cx, y, 32, None, WHITE, 5)
            elif kind == "red":
                _star(d, cx, y, 32, RED + (255,), RED, 2)
            else:
                _star(d, cx, y, 32, WHITE + (255,), WHITE, 2)
        _label(img, (840, y - 18), name, 54, anchor="lm", fill=RED if kind == "red" else WHITE)
        _small(img, (842, y + 30), what, 28, anchor="lm")
        out.append({"png": _save(img, folder, stem, k + 1), "at": 0.0 if not cur else 0.15,
                    "blink": 0 if kind == "flash" and cur else None})
    return out


def _heat(p, folder, stem):
    HEAT_ = [(k, ICON_NAMES.get(k, k.upper())) for k in p.get("icons", "face,outfit,weapon,vehicle,partner").split(",") if k]
    lit = [x for x in p.get("lit", ",".join(k for k, _n in HEAT_)).split(",") if x]
    off = [x for x in p.get("off", "").split(",") if x]
    out = [{"png": _save(_frame("THE HEAT BAR", "WHAT THE POLICE KNOW ABOUT YOU"), folder, stem, 0), "at": 0.0}]
    img = _new()
    d = ImageDraw.Draw(img)
    for k, (kind, name) in enumerate(HEAT_):
        cx = W // 2 + (k - (len(HEAT_) - 1) / 2) * 300
        d.rounded_rectangle((cx - 120, 380, cx + 120, 620), radius=30, fill=(20, 24, 50, 230), outline=(255, 255, 255, 60), width=3)
        icon(d, kind, cx, 490, 150, (90, 95, 120))
        _small(img, (cx, 680), name, 30, fill=(150, 150, 170))
    out.append({"png": _save(img, folder, stem, 1), "at": 0.0})
    order = [k for k, (kind, _n) in enumerate(HEAT_) if kind in lit]
    for n, k in enumerate(order):
        kind, name = HEAT_[k]
        img = _new()
        d = ImageDraw.Draw(img)
        cx = W // 2 + (k - (len(HEAT_) - 1) / 2) * 300
        gone = kind in off
        col = (90, 95, 120) if gone else RED
        d.rounded_rectangle((cx - 120, 380, cx + 120, 620), radius=30, fill=(60, 10, 20, 240) if not gone else (20, 24, 50, 240),
                            outline=(RED if not gone else (255, 255, 255)) + (255,), width=5)
        icon(d, kind, cx, 490, 150, col)
        _small(img, (cx, 680), name, 30, fill=WHITE if not gone else (150, 150, 170))
        if gone:
            d.line([(cx - 110, 610), (cx + 110, 390)], fill=GREEN + (255,), width=10)
        at = 0.12 + 0.7 * n / max(1, len(order)) if not off else 0.0
        out.append({"png": _save(img, folder, stem, 2 + k), "at": at})
    if off:
        for k, (kind, _n) in enumerate(HEAT_):
            if kind in off:
                img = _new()
                d = ImageDraw.Draw(img)
                cx = W // 2 + (k - (len(HEAT_) - 1) / 2) * 300
                d.rounded_rectangle((cx - 120, 380, cx + 120, 620), radius=30, fill=(20, 24, 50, 255), outline=GREEN + (255,), width=5)
                icon(d, kind, cx, 490, 150, (90, 95, 120))
                d.line([(cx - 100, 600), (cx + 100, 400)], fill=GREEN + (255,), width=10)
                d.rectangle((cx - 140, 650, cx + 140, 712), fill=(18, 24, 50, 255))
                _small(img, (cx, 680), "CLEARED", 30, fill=GREEN)
                out.append({"png": _save(img, folder, stem, 20 + k), "at": 0.4})
    return out


def _tiers(p, folder, stem):
    focus = p.get("focus", "both")
    out = [{"png": _save(_frame("VEHICLE SECURITY TIERS"), folder, stem, 0), "at": 0.0}]
    cols = [("TIER 1", "OLDER CARS", ["SLIM JIM OPENS THE DOOR", "HOTWIRE BY HAND", "EASY  ·  QUIET"], GREEN, "1"),
            ("TIER 3", "LUXURY CARS", ["DIGITAL IMMOBILIZER", "NO MANUAL HOTWIRE", "NEEDS A KEY CLONER"], RED, "3")]
    for k, (t, sub, rows, col, key) in enumerate(cols):
        img = _new()
        d = ImageDraw.Draw(img)
        x = 260 + k * 720
        dim = focus not in ("both", key)
        a = 120 if dim else 255
        d.rounded_rectangle((x, 300, x + 680, 900), radius=36, fill=(16, 20, 44, 235), outline=col + (a,), width=6)
        icon(d, "lock", x + 110, 400, 120, col)
        _label(img, (x + 200, 380), t, 72, fill=col, anchor="lm")
        _small(img, (x + 202, 440), sub, 30, anchor="lm")
        for j, r in enumerate(rows):
            _label(img, (x + 70, 560 + j * 100), r, 44, anchor="lm", fill=(255, 255, 255) if not dim else (150, 150, 165))
        out.append({"png": _save(img, folder, stem, k + 1), "at": 0.1 + 0.35 * k})
    return out


def _carry(p, folder, stem):
    out = [{"png": _save(_frame("WHAT YOU CAN CARRY"), folder, stem, 0), "at": 0.0}]
    boxes = [("ON YOUR BODY", [("2 HANDGUNS", "hidden under your jacket"), ("LONG GUNS", "visible  ·  people panic")], PINK),
             ("IN YOUR TRUNK", [("ARMOR + RIFLES", "your real arsenal"), ("LOOT", "limited by the car's space")], TEAL)]
    for k, (head, rows, col) in enumerate(boxes):
        img = _new()
        d = ImageDraw.Draw(img)
        x = 260 + k * 720
        d.rounded_rectangle((x, 300, x + 680, 880), radius=36, fill=(16, 20, 44, 235), outline=col + (255,), width=6)
        _label(img, (x + 340, 380), head, 64, fill=col)
        icon(d, "weapon" if k == 0 else "vehicle", x + 340, 500, 140, col)
        for j, (a, b) in enumerate(rows):
            _label(img, (x + 340, 640 + j * 120), a, 50)
            _small(img, (x + 340, 690 + j * 120), b, 28)
        out.append({"png": _save(img, folder, stem, k + 1), "at": 0.1 + 0.4 * k})
    return out


def _capacity(p, folder, stem):
    out = [{"png": _save(_frame("LOOT SPACE", "DUFFEL BAGS BY VEHICLE"), folder, stem, 0), "at": 0.0}]
    rows = [("MOTORCYCLE", 0, "ALMOST NOTHING"), ("COUPE", 2, "A LITTLE"), ("VAN", 8, "A FORTUNE")]
    if p.get("rows"):                                       # rows=motorcycle:0:zero-bags,car:2:in-the-trunk,van:5:three-to-five
        rows = []
        for r in p["rows"].split(","):
            name, n, note = (r.split(":") + ["0", ""])[:3]
            rows.append((name.replace("-", " ").upper(), int(n or 0), note.replace("-", " ").upper()))
    for k, (name, n, note) in enumerate(rows):
        img = _new()
        d = ImageDraw.Draw(img)
        y = 380 + k * 200
        _label(img, (300, y), name, 64, anchor="lm")
        _small(img, (302, y + 52), note, 28, anchor="lm", fill=TEAL)
        for j in range(max(1, n)):
            col = AMBER if n else (110, 110, 130)
            icon(d, "bag", 820 + j * 120, y + 10, 100, col)
        if not n:
            d.line([(760, y + 60), (880, y - 40)], fill=RED + (255,), width=8)
        out.append({"png": _save(img, folder, stem, k + 1), "at": 0.1 + 0.28 * k})
    return out


def _cash(p, folder, stem):
    out = [{"png": _save(_frame("YOUR MONEY", "TWO KINDS"), folder, stem, 0), "at": 0.0}]
    boxes = [("POCKET CASH", "$ 48,250", "LOST WHEN YOU DIE", RED), ("BANK  ·  BUCKME APP", "$ 312,900", "SAFE ONCE DEPOSITED AT AN ATM", GREEN)]
    for k, (head, amt, note, col) in enumerate(boxes):
        img = _new()
        d = ImageDraw.Draw(img)
        x = 260 + k * 720
        d.rounded_rectangle((x, 320, x + 680, 820), radius=36, fill=(16, 20, 44, 235), outline=col + (255,), width=6)
        _label(img, (x + 340, 410), head, 56, fill=col)
        _label(img, (x + 340, 560), amt, 110)
        _small(img, (x + 340, 700), note, 30, fill=col)
        out.append({"png": _save(img, folder, stem, k + 1), "at": 0.1 + 0.35 * k})
    img = _new()
    d = ImageDraw.Draw(img)
    _label(img, (W // 2, 900), "ATM  =  THE ONLY WAY TO PROTECT IT", 44, fill=AMBER)
    out.append({"png": _save(img, folder, stem, 5), "at": 0.75})
    return out


def _waink(p, folder, stem):
    """Phone mock-up scanning a parked car: the four fields appear one by one."""
    out = []
    img = _new()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, H), fill=NAVY + (70,))
    L.pill(img, (60, 56), "ILLUSTRATION", (90, 90, 110), 30)
    px, py, pw, ph = 1180, 110, 480, 880
    d.rounded_rectangle((px, py, px + pw, py + ph), radius=60, fill=(12, 12, 20, 245), outline=(200, 200, 215, 255), width=8)
    d.rounded_rectangle((px + 180, py + 24, px + 300, py + 42), radius=9, fill=(40, 40, 50, 255))
    _label(img, (px + pw // 2, py + 110), "WAINK", 64, fill=AMBER)
    _small(img, (px + pw // 2, py + 160), "VEHICLE SCAN", 26)
    d.rectangle((140, 260, 1060, 820), outline=AMBER + (255,), width=5)
    for (cx, cy) in ((140, 260), (1060, 260), (140, 820), (1060, 820)):
        d.rectangle((cx - 16, cy - 16, cx + 16, cy + 16), fill=AMBER + (255,))
    out.append({"png": _save(img, folder, stem, 0), "at": 0.0})
    img = _new()
    d = ImageDraw.Draw(img)
    for yy in range(270, 815, 18):
        d.line([(150, yy), (1050, yy)], fill=AMBER + (40,), width=2)
    _small(img, (600, 860), "SCANNING ...", 30, fill=AMBER)
    out.append({"png": _save(img, folder, stem, 1), "at": 0.05, "blink": 0})
    fields = [("LOCK TIER", "TIER 3  ·  IMMOBILIZER", RED), ("CHOP SHOP VALUE", "$ 64,000", GREEN),
              ("REGISTRATION FEE", "$ 2,450", WHITE), ("GPS TRACKER", "CLASS A  ·  ACTIVE", RED)]
    for k, (a, b, col) in enumerate(fields):
        img = _new()
        d = ImageDraw.Draw(img)
        y = py + 240 + k * 150
        d.rounded_rectangle((px + 30, y, px + pw - 30, y + 125), radius=18, fill=(30, 30, 44, 255))
        _small(img, (px + 60, y + 38), a, 24, anchor="lm", fill=(170, 170, 190))
        _label(img, (px + 60, y + 88), b, 40, anchor="lm", fill=col)
        out.append({"png": _save(img, folder, stem, 2 + k), "at": 0.2 + 0.16 * k})
    return out


def _focus(p, folder, stem):
    """Focus mode: a car outline with its weak points marked (tires, engine block, fuel tank)."""
    out = []
    img = _new()
    ImageDraw.Draw(img).rectangle((0, 0, W, H), fill=(0, 30, 40, 90))
    img.alpha_composite(_frame("FOCUS MODE", "WEAK POINTS"))
    d = ImageDraw.Draw(img)
    body = [(360, 700), (380, 600), (560, 560), (760, 430), (1160, 430), (1360, 560), (1560, 590), (1580, 700)]
    d.line(body + [body[0]], fill=(150, 255, 240, 255), width=6, joint="curve")
    for wx in (600, 1340):
        d.ellipse((wx - 95, 620, wx + 95, 810), outline=(150, 255, 240, 255), width=6)
    out.append({"png": _save(img, folder, stem, 0), "at": 0.0})
    marks = [("TIRES", 600, 715, AMBER), ("ENGINE BLOCK", 1450, 600, RED), ("FUEL TANK", 820, 640, RED), ("TIRES", 1340, 715, AMBER)]
    for k, (name, x, y, col) in enumerate(marks):
        img = _new()
        d = ImageDraw.Draw(img)
        d.ellipse((x - 60, y - 60, x + 60, y + 60), outline=col + (255,), width=8)
        d.ellipse((x - 16, y - 16, x + 16, y + 16), fill=col + (255,))
        below = name == "FUEL TANK"
        d.line([(x, y + (60 if below else -60)), (x, y + (190 if below else -170))], fill=col + (255,), width=4)
        _label(img, (x, y + (225 if below else -200)), name, 46, fill=col)
        out.append({"png": _save(img, folder, stem, 1 + k), "at": 0.15 + 0.18 * k})
    return out


def _boxes(head, sub, boxes, folder, stem, focus=""):
    """2-3 side-by-side boxes: (title, big, note, colour, key); the focused key is lit, the others dimmed."""
    out = [{"png": _save(_frame(head, sub), folder, stem, 0), "at": 0.0}]
    n = len(boxes)
    bw = 520 if n == 3 else 680
    gap = 60
    x0 = (W - (n * bw + (n - 1) * gap)) // 2
    for k, (t, big, note, col, key) in enumerate(boxes):
        img = _new()
        d = ImageDraw.Draw(img)
        x = x0 + k * (bw + gap)
        dim = bool(focus) and focus != key
        a = 110 if dim else 255
        d.rounded_rectangle((x, 320, x + bw, 860), radius=36, fill=(16, 20, 44, 235), outline=col + (a,), width=6)
        _label(img, (x + bw // 2, 410), t, 50, fill=col if not dim else (140, 140, 155))
        _label(img, (x + bw // 2, 570), big, 84 if len(big) < 12 else 56, fill=WHITE if not dim else (150, 150, 165))
        words, lines, cur = note.split(), [], ""
        for w_ in words:
            tt = (cur + " " + w_).strip()
            if len(tt) > 24 and cur:
                lines.append(cur)
                cur = w_
            else:
                cur = tt
        if cur:
            lines.append(cur)
        for j, ln in enumerate(lines[:3]):
            _small(img, (x + bw // 2, 690 + j * 44), ln, 30, fill=col if not dim else (140, 140, 155))
        out.append({"png": _save(img, folder, stem, k + 1), "at": 0.08 + 0.28 * k})
    return out


def _economy(p, folder, stem):
    return _boxes("YOUR MONEY", "THREE BUCKETS", [
        ("BANK", "SAFE", "Deposit only at an ATM or a bank teller", (170, 90, 255), "bank"),
        ("CASH ON HAND", "CAPPED", "Lost if you are busted or killed", GREEN, "cash"),
        ("DUFFEL BAG", "LOOT", "Gold, diamonds, drugs. Needs a fence", AMBER, "bag")], folder, stem, p.get("focus", ""))


def _safe(p, folder, stem):
    return _boxes("CRACKING THE SAFE", "", [
        ("EXPLOSIVES", "DAMAGED", "Loot destroyed and the cloud CCTV keeps your face", RED, "loud"),
        ("THE QUIET WAY", "FULL PAYOUT", "Snap gun, alarm box first, code from the desk", GREEN, "quiet")], folder, stem, p.get("focus", ""))


AGENCIES = ["VICE CITY PD", "VICE BEACH PD", "PORT GELLHORN PD", "LEONIDA HIGHWAY PATROL", "COUNTY SHERIFFS", "MARINE UNITS",
            "WILDLIFE POACHING PATROLS"]


def _agencies(p, folder, stem):
    out = [{"png": _save(_frame("7 POLICE FORCES", "ONE STATE"), folder, stem, 0), "at": 0.0}]
    for k, name in enumerate(AGENCIES):
        img = _new()
        d = ImageDraw.Draw(img)
        col, row = (0, k) if k < 4 else (1, k - 4)
        x, y = (300 if col == 0 else 1000), 330 + row * 120
        d.rounded_rectangle((x, y, x + 640, y + 92), radius=20, fill=(16, 20, 44, 235), outline=(BLUE if k % 2 else RED) + (255,), width=4)
        _label(img, (x + 40, y + 46), f"{k + 1}", 54, fill=BLUE if k % 2 else RED, anchor="lm")
        _label(img, (x + 110, y + 46), name, 44, anchor="lm")
        out.append({"png": _save(img, folder, stem, k + 1), "at": 0.06 + 0.09 * k})
    img = _new()
    _label(img, (W // 2, 880), "K-9  ·  HELICOPTERS  ·  ARMORED TRUCKS  ·  SPIKE STRIPS", 46, fill=AMBER)
    out.append({"png": _save(img, folder, stem, 9), "at": 0.75})
    return out


PROFILE = [("PROFESSIONAL", GREEN), ("AGGRESSIVE", AMBER), ("VIOLENT", (255, 120, 40)), ("PSYCHO", RED), ("SHATTERED", (150, 0, 20))]


def _profile(p, folder, stem):
    level = max(0, min(4, int(p.get("level", 4))))
    out = [{"png": _save(_frame("CRIMINAL PROFILE", "ONE FOR JASON  ·  ONE FOR LUCIA"), folder, stem, 0), "at": 0.0}]
    img = _new()
    d = ImageDraw.Draw(img)
    seg = 300
    x0 = (W - 5 * seg) // 2
    for r, who in enumerate(("JASON", "LUCIA")):
        y = 430 + r * 260
        _label(img, (x0, y - 70), who, 50, anchor="lm")
        for k, (name, col) in enumerate(PROFILE):
            d.rounded_rectangle((x0 + k * seg + 6, y, x0 + (k + 1) * seg - 6, y + 60), radius=14, fill=col + (230,))
            _small(img, (x0 + k * seg + seg // 2, y + 100), name, 26)
    out.append({"png": _save(img, folder, stem, 1), "at": 0.0})
    for r in range(2):
        img = _new()
        d = ImageDraw.Draw(img)
        y = 430 + r * 260
        x = x0 + level * seg + seg // 2
        d.polygon([(x - 26, y - 40), (x + 26, y - 40), (x, y - 6)], fill=WHITE + (255,))
        d.rounded_rectangle((x0 + level * seg + 2, y - 4, x0 + (level + 1) * seg - 2, y + 64), radius=16, outline=WHITE + (255,), width=6)
        out.append({"png": _save(img, folder, stem, 2 + r), "at": 0.25 + 0.15 * r})
    if level == 4:
        img = _new()
        _label(img, (W // 2, 960), "SHATTERED  =  NO WAY BACK FOR THAT SAVE", 50, fill=RED)
        out.append({"png": _save(img, folder, stem, 9), "at": 0.7, "blink": None})
    return out


def _checklist(p, folder, stem, raw=""):
    head, raw = _split_head(raw, "")                     # optional 'HEAD/SUB::item|item'
    head, _s, sub = head.partition("/")
    items = [x.strip() for x in raw.split("|") if x.strip()] or ["SCAN EVERY CAR WITH WAINK"]
    out = [{"png": _save(_frame((head or "BEFORE MIDNIGHT").upper(), (sub or ("" if head else "YOUR FIRST-HOUR CHECKLIST")).upper()),
                         folder, stem, 0), "at": 0.0}]
    rh = min(120, 560 // max(1, len(items)))
    for k, it in enumerate(items):
        img = _new()
        d = ImageDraw.Draw(img)
        y = 330 + k * rh
        d.rounded_rectangle((360, y, W - 360, y + rh - 18), radius=20, fill=(16, 20, 44, 235), outline=(255, 255, 255, 70), width=3)
        cx, cy, r = 430, y + (rh - 18) / 2, (rh - 18) * 0.32
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GREEN + (255,))
        d.line([(cx - r * .45, cy), (cx - r * .1, cy + r * .38), (cx + r * .5, cy - r * .35)], fill=WHITE + (255,), width=6)
        _label(img, (500, cy), it.upper(), int(rh * 0.42), anchor="lm")
        out.append({"png": _save(img, folder, stem, k + 1), "at": 0.08 + 0.8 * k / max(1, len(items))})
    return out



def _split_head(raw: str, default: str):
    head, sep, rest = str(raw or "").partition("::")
    return (head.strip() or default, rest) if sep else (default, head)


def _cards(p, folder, stem, raw=""):
    """Up to 6 cards in a 3x2 grid, appearing one by one: 'HEAD::VICE CITY=East coast art deco|LEONIDA KEYS=Island chain'."""
    head, rest = _split_head(raw, "")
    items = [x.split("=", 1) + [""] for x in rest.split("|") if x.strip()][:6]
    out = [{"png": _save(_frame(head.upper()), folder, stem, 0), "at": 0.0}]
    cols = 3 if len(items) > 4 else max(1, len(items))
    rows = -(-len(items) // cols)
    cw, chh, gap = 500, 250 if rows > 1 else 320, 40
    x0 = (W - (cols * cw + (cols - 1) * gap)) // 2
    y0 = 300 + (620 - (rows * chh + (rows - 1) * gap)) // 2
    pal = [PINK, TEAL, AMBER, GREEN, (170, 90, 255), BLUE]
    for k, it in enumerate(items):
        name, sub = it[0].strip(), it[1].strip()
        img = _new()
        d = ImageDraw.Draw(img)
        x, y = x0 + (k % cols) * (cw + gap), y0 + (k // cols) * (chh + gap)
        col = pal[k % len(pal)]
        d.rounded_rectangle((x, y, x + cw, y + chh), radius=28, fill=(16, 20, 44, 235), outline=col + (255,), width=5)
        d.rectangle((x + 30, y + 34, x + 90, y + 42), fill=col + (255,))
        _label(img, (x + 30, y + 100), name.upper(), 52 if len(name) < 16 else 40, anchor="lm")
        words, lines, cur = sub.split(), [], ""
        for w_ in words:
            tt = (cur + " " + w_).strip()
            if len(tt) > 30 and cur:
                lines.append(cur)
                cur = w_
            else:
                cur = tt
        if cur:
            lines.append(cur)
        for j, ln in enumerate(lines[:3]):
            _small(img, (x + 32, y + 160 + j * 38), ln, 28, anchor="lm", fill=col)
        out.append({"png": _save(img, folder, stem, k + 1), "at": 0.06 + 0.8 * k / max(1, len(items))})
    return out


def _stats(p, folder, stem, raw=""):
    """Big numbers side by side: 'HEAD::2x=Leonida vs GTA V|700+=enterable interiors'."""
    head, rest = _split_head(raw, "BY THE NUMBERS")
    items = [x.split("=", 1) + [""] for x in rest.split("|") if x.strip()][:4]
    out = [{"png": _save(_frame(head.upper()), folder, stem, 0), "at": 0.0}]
    n = max(1, len(items))
    cw, gap = min(420, (W - 200 - (n - 1) * 40) // n), 40
    x0 = (W - (n * cw + (n - 1) * gap)) // 2
    pal = [PINK, TEAL, AMBER, GREEN]
    for k, it in enumerate(items):
        big, sub = it[0].strip(), it[1].strip()
        img = _new()
        d = ImageDraw.Draw(img)
        x = x0 + k * (cw + gap)
        col = pal[k % 4]
        d.rounded_rectangle((x, 330, x + cw, 820), radius=32, fill=(16, 20, 44, 235), outline=col + (255,), width=5)
        _label(img, (x + cw // 2, 520), big, 150 if len(big) < 5 else 100, fill=col)
        words, lines, cur = sub.split(), [], ""
        for w_ in words:
            tt = (cur + " " + w_).strip()
            if len(tt) > 18 and cur:
                lines.append(cur)
                cur = w_
            else:
                cur = tt
        if cur:
            lines.append(cur)
        for j, ln in enumerate(lines[:3]):
            _small(img, (x + cw // 2, 680 + j * 42), ln.upper(), 30)
        out.append({"png": _save(img, folder, stem, k + 1), "at": 0.08 + 0.75 * k / n})
    return out

def _download(p, folder, stem, raw=""):
    """Download time per line speed, bars filling in steps: 'HEAD::100 MBPS=4.7|50 MBPS=9.4|25 MBPS=18.8' (hours)."""
    head, rest = _split_head(raw, "212 GB  ·  HOW LONG IT TAKES")
    items = []
    for x in rest.split("|"):
        if "=" in x:
            a, b = x.split("=", 1)
            m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(.*)$", b)
            if m:                                          # '9.4' -> 9.4 H; '602 MB' / '10%' keep their own unit
                items.append((a.strip(), float(m.group(1)), m.group(2).strip()))
    items = items[:4] or [("100 MBPS", 4.7, ""), ("50 MBPS", 9.4, ""), ("25 MBPS", 18.8, "")]
    head, _s, sub = head.partition("/")                  # 'HEAD/SUB::...'
    timing = "GB" in head.upper() and not any(u for _n, _h, u in items)   # a download-time chart gets its own sub and footer
    out = [{"png": _save(_frame(head.upper(), (sub or ("SAME FILE  ·  DIFFERENT NIGHT" if timing else "")).upper()), folder, stem, 0),
            "at": 0.0}]
    top = max(h for _n, h, _u in items)
    pal = [GREEN, AMBER, RED, PINK]
    x0, x1, rh = 520, W - 330, 150
    y0 = 330 + (560 - rh * len(items)) // 2
    k = 1
    for i, (name, hrs, unit) in enumerate(items):
        y = y0 + i * rh
        col = pal[i % len(pal)]
        base = _new()
        d = ImageDraw.Draw(base)
        _label(base, (x0 - 40, y + 45), name.upper(), 56, anchor="rm")
        d.rounded_rectangle((x0, y + 15, x1, y + 75), radius=30, fill=(16, 20, 44, 235), outline=(255, 255, 255, 80), width=3)
        out.append({"png": _save(base, folder, stem, k), "at": 0.05 + 0.25 * i})
        k += 1
        full = (x1 - x0 - 8) * hrs / top
        for step in range(1, 5):
            img = _new()
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((x0 + 4, y + 19, x0 + 4 + max(60, full * step / 4), y + 71), radius=26, fill=col + (255,))
            if step == 4:
                _label(img, (min(x0 + full + 30, x1 + 20), y + 45), f"{hrs:g}{(unit if unit.startswith('%') else ' ' + unit) if unit else ' H'}", 56, fill=col, anchor="lm")
            out.append({"png": _save(img, folder, stem, k), "at": 0.08 + 0.25 * i + 0.045 * step})
            k += 1
    if timing:
        img = _new()
        _label(img, (W // 2, 960), "AND THAT IS IF THE SERVERS KEEP UP", 44, fill=AMBER)
        out.append({"png": _save(img, folder, stem, k), "at": 0.85})
    return out


def _scam(p, folder, stem, raw=""):
    """A made-up fake 'early access' page, then the tells light up and a SCAM stamp flashes."""
    out = [{"png": _save(_frame("HOW THE FAKE PAGES LOOK", "MADE-UP EXAMPLE"), folder, stem, 0), "at": 0.0}]
    img = _new()
    d = ImageDraw.Draw(img)
    bx = (330, 270, W - 330, 900)
    d.rounded_rectangle(bx, radius=26, fill=(236, 238, 244, 250))
    d.rounded_rectangle((bx[0], bx[1], bx[2], bx[1] + 64), radius=26, fill=(60, 64, 80, 255))
    for j, c in enumerate([(235, 90, 80), (240, 190, 60), (90, 200, 110)]):
        d.ellipse((bx[0] + 30 + j * 40, bx[1] + 22, bx[0] + 52 + j * 40, bx[1] + 44), fill=c + (255,))
    d.rounded_rectangle((bx[0] + 170, bx[1] + 14, bx[2] - 40, bx[1] + 52), radius=18, fill=(235, 236, 240, 255))
    d.text((bx[0] + 200, bx[1] + 33), "vip-early-access-gta6.example", font=L.font(L.F_TAG, 26), fill=(80, 80, 90), anchor="lm")
    d.text((W // 2, 430), "VIP EARLY ACCESS", font=L.font(L.F_HEAD, 96), fill=(30, 30, 40), anchor="mm")
    d.text((W // 2, 520), "PLAY 3 DAYS BEFORE EVERYONE", font=L.font(L.F_TAG, 38), fill=(70, 70, 90), anchor="mm")
    d.rounded_rectangle((W // 2 - 260, 580, W // 2 + 260, 680), radius=20, fill=(30, 30, 40, 255))
    d.text((W // 2, 630), "OFFER ENDS 00:04:59", font=L.font(L.F_HEAD, 54), fill=(255, 90, 90), anchor="mm")
    d.rounded_rectangle((W // 2 - 300, 720, W // 2 + 300, 820), radius=50, fill=(250, 170, 30, 255))
    d.text((W // 2, 770), "PAY $299 IN CRYPTO", font=L.font(L.F_HEAD, 58), fill=(30, 30, 40), anchor="mm")
    out.append({"png": _save(img, folder, stem, 1), "at": 0.04})
    tells = [((W // 2, 630), 300, 70, "TIMER THAT NEVER ENDS"), ((W // 2, 770), 330, 70, "CRYPTO ONLY  ·  NO REFUNDS"),
             ((W // 2, 440), 330, 60, "NO EARLY ACCESS EXISTS")]
    for i, ((cx, cy), rx, ry, txt) in enumerate(tells):
        img = _new()
        d = ImageDraw.Draw(img)
        d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=RED + (255,), width=9)
        side = 1 if i % 2 == 0 else -1
        tx = cx + side * (rx + 40)
        d.rounded_rectangle((tx - (0 if side > 0 else 380), cy - 34, tx + (380 if side > 0 else 0), cy + 34), radius=16, fill=RED + (240,))
        _small(img, (tx + side * 190, cy), txt, 26, fill=WHITE)
        out.append({"png": _save(img, folder, stem, 2 + i), "at": 0.3 + 0.15 * i})
    img = _new()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((W // 2 - 330, 430, W // 2 + 330, 640), radius=24, outline=RED + (255,), width=16, fill=(235, 40, 50, 60))
    _label(img, (W // 2, 535), "SCAM", 190, fill=RED)
    out.append({"png": _save(img, folder, stem, 6), "at": 0.8, "blink": 0})
    return out


def _unlock(p, folder, stem, raw=""):
    """Unlock windows around the world on one line, lighting in order: 'HEAD::15|19|New Zealand|Mexico & Central America'."""
    head, rest = _split_head(raw, "THERE IS NO SINGLE MIDNIGHT")
    parts = [x.strip() for x in rest.split("|")] + ["", "", "", ""]
    n = int(parts[0]) if parts[0].isdigit() else 15
    hours = float(parts[1]) if parts[1].replace(".", "").isdigit() else 19
    first, last = parts[2] or "NEW ZEALAND", parts[3] or "MEXICO  ·  CENTRAL AMERICA"
    out = [{"png": _save(_frame(head.upper(), f"{n} UNLOCK WINDOWS  ·  NEARLY {hours:g} HOURS"), folder, stem, 0), "at": 0.0}]
    x0, x1, y = 220, W - 220, 600
    img = _new()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((x0 - 20, y - 8, x1 + 20, y + 8), radius=8, fill=(255, 255, 255, 90))
    for h in range(int(hours) + 1):
        x = x0 + (x1 - x0) * h / hours
        d.line([(x, y + 20), (x, y + 40)], fill=(255, 255, 255, 120), width=3)
        if h % 3 == 0:
            _small(img, (x, y + 70), f"+{h}H", 24, fill=(200, 200, 215))
    out.append({"png": _save(img, folder, stem, 1), "at": 0.02})
    rnd = random.Random(7)
    pos = [0.0] + [min(1.0, (j + rnd.uniform(-0.3, 0.3)) / max(1, n - 1)) for j in range(1, n - 1)] + [1.0]
    pal = [PINK, TEAL, AMBER, GREEN, (170, 90, 255), BLUE]
    for i, t in enumerate(pos):
        img = _new()
        d = ImageDraw.Draw(img)
        x = x0 + (x1 - x0) * t
        col = pal[i % len(pal)]
        d.ellipse((x - 22, y - 22, x + 22, y + 22), fill=col + (255,), outline=WHITE + (255,), width=4)
        h = 120 + (i % 3) * 55
        d.line([(x, y - 26), (x, y - h)], fill=col + (200,), width=4)
        _small(img, (x, y - h - 24), f"{i + 1}", 30, fill=col)
        if i == 0:
            _label(img, (x - 10, 820), first.upper(), 46, fill=col, anchor="lm")
            _small(img, (x - 10, 870), "UNLOCKS FIRST", 26, anchor="lm")
        if i == len(pos) - 1:
            _label(img, (x + 10, 820), last.upper(), 46, fill=col, anchor="rm")
            _small(img, (x + 10, 870), "UNLOCKS LAST", 26, anchor="rm")
        out.append({"png": _save(img, folder, stem, 2 + i), "at": 0.08 + 0.72 * i / max(1, len(pos) - 1)})
    return out


def _nodisc(p, folder, stem, raw=""):
    """The open game case: no disc inside, only a download code card."""
    head, rest = _split_head(raw, "WHAT IS IN THE BOX")
    out = [{"png": _save(_frame(head.upper(), rest.strip().upper() or "STANDARD EDITION  ·  $79.99"), folder, stem, 0), "at": 0.0}]
    img = _new()
    d = ImageDraw.Draw(img)
    lx, rx, top, bot = 380, W // 2 + 20, 290, 930
    d.rounded_rectangle((lx, top, rx - 10, bot), radius=20, fill=(20, 60, 140, 245), outline=WHITE + (180,), width=4)
    d.rounded_rectangle((rx + 10, top, W - 380, bot), radius=20, fill=(14, 18, 36, 250), outline=WHITE + (180,), width=4)
    cx, cy, r = (lx + rx) // 2, (top + bot) // 2, 210
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, 110), width=6)
    d.ellipse((cx - 40, cy - 40, cx + 40, cy + 40), outline=(255, 255, 255, 110), width=4)
    _small(img, (cx, cy + r + 50), "WHERE THE DISC USED TO GO", 26)
    out.append({"png": _save(img, folder, stem, 1), "at": 0.03})
    img = _new()
    d = ImageDraw.Draw(img)
    d.line([(cx - 170, cy - 170), (cx + 170, cy + 170)], fill=RED + (255,), width=16)
    out.append({"png": _save(img, folder, stem, 2), "at": 0.3})
    img = _new()
    d = ImageDraw.Draw(img)
    qx = (rx + W - 380) // 2
    d.rounded_rectangle((qx - 230, cy - 150, qx + 230, cy + 150), radius=18, fill=(245, 245, 250, 255))
    d.text((qx, cy - 80), "DOWNLOAD CODE", font=L.font(L.F_HEAD, 58), fill=(20, 20, 30), anchor="mm")
    d.rounded_rectangle((qx - 190, cy - 20, qx + 190, cy + 50), radius=10, fill=(220, 222, 230, 255))
    d.text((qx, cy + 15), "XXXX-XXXX-XXXX", font=L.font(L.F_HEAD, 46), fill=(60, 60, 80), anchor="mm")
    d.text((qx, cy + 100), "INTERNET REQUIRED", font=L.font(L.F_TAG, 26), fill=(200, 40, 50), anchor="mm")
    out.append({"png": _save(img, folder, stem, 3), "at": 0.5})
    img = _new()
    _label(img, (W // 2, 990), "A VERY EXPENSIVE RECEIPT", 50, fill=AMBER)
    out.append({"png": _save(img, folder, stem, 4), "at": 0.8})
    return out

def _garage(p, folder, stem, raw=""):
    """Garage slots filling one by one, then one more car that does not fit: 'HEAD::3|Coupe|Pickup|Muscle car|Supercar'."""
    head, rest = _split_head(raw, "YOUR FIRST GARAGE")
    parts = [x.strip() for x in rest.split("|") if x.strip()]
    n = int(parts[0]) if parts and parts[0].isdigit() else 3
    cars = (parts[1:] if parts and parts[0].isdigit() else parts) or ["COUPE", "PICKUP", "MUSCLE CAR", "SUPERCAR"]
    out = [{"png": _save(_frame(head.upper(), f"ROOM FOR {n} CARS"), folder, stem, 0), "at": 0.0}]
    sw, gap = 400, 50
    x0 = (W - (n * sw + (n - 1) * gap)) // 2
    img = _new()
    d = ImageDraw.Draw(img)
    for i in range(n):
        x = x0 + i * (sw + gap)
        d.rounded_rectangle((x, 330, x + sw, 760), radius=20, outline=(255, 255, 255, 140), width=5, fill=(16, 20, 44, 200))
        _small(img, (x + sw // 2, 800), f"SLOT {i + 1}", 28, fill=(200, 200, 215))
    out.append({"png": _save(img, folder, stem, 1), "at": 0.02})
    pal = [TEAL, AMBER, PINK]
    for i in range(min(n, len(cars))):
        img = _new()
        d = ImageDraw.Draw(img)
        x = x0 + i * (sw + gap)
        d.rounded_rectangle((x + 8, 338, x + sw - 8, 752), radius=16, fill=pal[i % 3] + (60,))
        icon(d, "vehicle", x + sw // 2, 520, 220, pal[i % 3])
        _label(img, (x + sw // 2, 690), cars[i].upper(), 44)
        out.append({"png": _save(img, folder, stem, 2 + i), "at": 0.12 + 0.18 * i})
    if len(cars) > n:
        img = _new()
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((W // 2 - 420, 860, W // 2 + 420, 1010), radius=24, fill=(16, 20, 44, 240), outline=RED + (255,), width=6)
        _label(img, (W // 2, 915), f"{cars[n].upper()}  ·  NO ROOM", 56, fill=RED)
        _small(img, (W // 2, 970), "PUSH ONE OUT  ·  OR SELL IT TO A FENCE", 28)
        out.append({"png": _save(img, folder, stem, 2 + n), "at": 0.72, "blink": 0})
    return out


def _loop(p, folder, stem, raw=""):
    """Steps around a ring lighting one by one, an arrow between each: 'HEAD::STEAL|ESCAPE|FENCE|BANK'."""
    head, rest = _split_head(raw, "THE NIGHT-ONE LOOP")
    steps = [x.strip() for x in rest.split("|") if x.strip()] or ["STEAL", "ESCAPE", "FENCE", "BANK"]
    out = [{"png": _save(_frame(head.upper(), "  ·  ".join(st.upper() for st in steps)), folder, stem, 0), "at": 0.0}]
    cx, cy, R = W // 2, 650, 260
    n = len(steps)
    pal = [PINK, AMBER, TEAL, GREEN, (170, 90, 255), BLUE]
    pts = [(cx + R * 1.5 * math.cos(-math.pi / 2 + 2 * math.pi * i / n), cy + R * math.sin(-math.pi / 2 + 2 * math.pi * i / n)) for i in range(n)]
    for i, (x, y) in enumerate(pts):
        img = _new()
        d = ImageDraw.Draw(img)
        col = pal[i % len(pal)]
        if i:
            px, py = pts[i - 1]
            a = math.atan2(y - py, x - px)
            sx, sy = px + 150 * math.cos(a), py + 150 * math.sin(a) * 0.6
            ex, ey = x - 150 * math.cos(a), y - 150 * math.sin(a) * 0.6
            d.line([(sx, sy), (ex, ey)], fill=WHITE + (200,), width=8)
            d.polygon([(ex, ey), (ex - 34 * math.cos(a - 0.45), ey - 34 * math.sin(a - 0.45)),
                       (ex - 34 * math.cos(a + 0.45), ey - 34 * math.sin(a + 0.45))], fill=WHITE + (230,))
        d.rounded_rectangle((x - 170, y - 70, x + 170, y + 70), radius=35, fill=(16, 20, 44, 240), outline=col + (255,), width=6)
        _label(img, (x, y + 2), steps[i].upper(), 64, fill=col)
        _small(img, (x - 150, y - 92), f"{i + 1}", 30, fill=col, anchor="lm")
        out.append({"png": _save(img, folder, stem, 1 + i), "at": 0.06 + 0.7 * i / max(1, n)})
    img = _new()
    d = ImageDraw.Draw(img)
    (x, y), (px, py) = pts[0], pts[-1]
    d.line([(px + 60, py - 80), (x - 170, y + 20)], fill=GREEN + (200,), width=6)
    _small(img, (cx, cy), "REPEAT", 40, fill=GREEN)
    out.append({"png": _save(img, folder, stem, 1 + n), "at": 0.85})
    return out

def _saves(p, folder, stem, raw=""):
    """The 15 manual save slots in a 5x3 grid, filling in order. 'HEAD::1=PROLOGUE|2-13=EVERY 5-10%|14=PRE-FINALE|15=CHAOS'
    gives each run of slots its label and colour; 'focus=15' style params are not needed - a slot range listed last is lit last."""
    head, rest = _split_head(raw, "15 MANUAL SAVE SLOTS")
    groups = []
    for x in rest.split("|"):
        if "=" in x:
            a, b = x.split("=", 1)
            lo, _d, hi = a.strip().partition("-")
            if lo.isdigit():
                groups.append((int(lo), int(hi) if hi.isdigit() else int(lo), b.strip()))
    groups = groups or [(1, 1, "PROLOGUE"), (2, 13, "EVERY 5-10%"), (14, 14, "PRE-FINALE"), (15, 15, "CHAOS")]
    pal = [TEAL, (90, 140, 255), AMBER, RED, PINK, GREEN]
    out = [{"png": _save(_frame(head.upper(), "YOUR ONLY CHAPTER SELECT"), folder, stem, 0), "at": 0.0}]
    cw, chh, gx, gy = 300, 150, 26, 26
    x0, y0 = (W - (5 * cw + 4 * gx)) // 2, 290
    img = _new()
    d = ImageDraw.Draw(img)
    for n in range(15):
        x, y = x0 + (n % 5) * (cw + gx), y0 + (n // 5) * (chh + gy)
        d.rounded_rectangle((x, y, x + cw, y + chh), radius=18, fill=(16, 20, 44, 220), outline=(255, 255, 255, 70), width=3)
        _small(img, (x + 24, y + 30), f"SLOT {n + 1}", 24, fill=(150, 150, 170), anchor="lm")
    out.append({"png": _save(img, folder, stem, 1), "at": 0.02})
    k = 2
    total = sum(hi - lo + 1 for lo, hi, _n in groups)
    done = 0
    for gi, (lo, hi, name) in enumerate(groups):
        col = pal[gi % len(pal)]
        for n in range(lo - 1, min(15, hi)):
            img = _new()
            d = ImageDraw.Draw(img)
            x, y = x0 + (n % 5) * (cw + gx), y0 + (n // 5) * (chh + gy)
            d.rounded_rectangle((x, y, x + cw, y + chh), radius=18, fill=col + (70,), outline=col + (255,), width=5)
            _small(img, (x + 24, y + 30), f"SLOT {n + 1}", 24, fill=WHITE, anchor="lm")
            _label(img, (x + cw // 2, y + 95), name.upper(), 40 if len(name) < 13 else 30, fill=col)
            out.append({"png": _save(img, folder, stem, k), "at": 0.06 + 0.8 * done / max(1, total)})
            k += 1
            done += 1
    return out


def _controller(p, folder, stem, raw=""):
    """A game-pad outline with buttons called out one by one: 'HEAD::L3=SPRINT|X=HANDBRAKE|L1=AIM|R1=FIRE'."""
    head, rest = _split_head(raw, "THE NEW CONTROLS")
    calls = [tuple(y.strip() for y in x.split("=", 1)) for x in rest.split("|") if "=" in x] or \
        [("L3", "SPRINT"), ("X", "HANDBRAKE"), ("L1", "AIM"), ("R1", "FIRE")]
    out = []
    img = _frame(head.upper(), "ILLUSTRATED PAD  ·  PLAYSTATION LAYOUT")
    d = ImageDraw.Draw(img)
    cx, cy = W // 2, 640
    body = (cx - 420, cy - 200, cx + 420, cy + 130)
    d.rounded_rectangle(body, radius=150, fill=(26, 30, 56, 245), outline=WHITE + (200,), width=6)
    d.ellipse((cx - 470, cy - 60, cx - 230, cy + 300), fill=(26, 30, 56, 245), outline=WHITE + (200,), width=6)
    d.ellipse((cx + 230, cy - 60, cx + 470, cy + 300), fill=(26, 30, 56, 245), outline=WHITE + (200,), width=6)
    d.rounded_rectangle((cx - 400, cy - 175, cx + 400, cy + 110), radius=140, fill=(26, 30, 56, 255))
    pos = {"L1": (cx - 300, cy - 225), "R1": (cx + 300, cy - 225), "L2": (cx - 300, cy - 265), "R2": (cx + 300, cy - 265),
           "L3": (cx - 150, cy + 40), "R3": (cx + 150, cy + 40), "X": (cx + 300, cy - 20), "O": (cx + 370, cy - 90),
           "SQUARE": (cx + 230, cy - 90), "TRIANGLE": (cx + 300, cy - 160), "DPAD": (cx - 300, cy - 90)}
    for name in ("L1", "R1"):
        x, y = pos[name]
        d.rounded_rectangle((x - 90, y - 22, x + 90, y + 22), radius=18, fill=(60, 64, 96, 255), outline=WHITE + (160,), width=3)
    for name in ("L3", "R3"):
        x, y = pos[name]
        d.ellipse((x - 62, y - 62, x + 62, y + 62), fill=(14, 16, 30, 255), outline=WHITE + (160,), width=4)
    for name in ("X", "O", "SQUARE", "TRIANGLE"):
        x, y = pos[name]
        d.ellipse((x - 34, y - 34, x + 34, y + 34), fill=(14, 16, 30, 255), outline=WHITE + (160,), width=3)
    x, y = pos["DPAD"]
    for dx, dy in ((0, -45), (0, 45), (-45, 0), (45, 0)):
        d.rounded_rectangle((x + dx - 22, y + dy - 22, x + dx + 22, y + dy + 22), radius=6, fill=(60, 64, 96, 255))
    out.append({"png": _save(img, folder, stem, 0), "at": 0.0})
    pal = [GREEN, AMBER, TEAL, RED, PINK, BLUE]
    for i, (btn, what) in enumerate(calls[:6]):
        x, y = pos.get(btn.upper(), (cx, cy))
        col = pal[i % len(pal)]
        img = _new()
        d = ImageDraw.Draw(img)
        r = 70 if btn.upper() in ("L3", "R3") else (95 if btn.upper() in ("L1", "R1") else 44)
        d.ellipse((x - r, y - r * (0.45 if btn.upper() in ("L1", "R1") else 1), x + r, y + r * (0.45 if btn.upper() in ("L1", "R1") else 1)),
                  outline=col + (255,), width=8)
        left = x < cx
        lx = 250 if left else W - 250
        ly = 330 + i * 0 if btn.upper() in ("L1", "R1") else (y + 230 if btn.upper() in ("L3", "R3") else y)
        ly = min(max(ly, 300), 1000)
        d.line([(x + (-r if left else r), y), (lx + (170 if left else -170), ly)], fill=col + (230,), width=5)
        d.rounded_rectangle((lx - 170, ly - 48, lx + 170, ly + 48), radius=20, fill=(16, 20, 44, 240), outline=col + (255,), width=5)
        _label(img, (lx, ly - 8), f"{btn.upper()}  =  {what.upper()}", 40 if len(what) < 10 else 32, fill=col)
        out.append({"png": _save(img, folder, stem, 1 + i), "at": 0.1 + 0.75 * i / max(1, len(calls))})
    return out


def _archive(p, folder, stem, raw=""):
    """The pause-menu mission list as a wall of still thumbnails; a cursor clicks one and 'REPLAY UNAVAILABLE' flashes."""
    head, rest = _split_head(raw, "COMPLETED MISSIONS")
    out = []
    img = _frame(head.upper(), rest.strip().upper() or "PAUSE MENU  ·  ILLUSTRATION")
    d = ImageDraw.Draw(img)
    rnd = random.Random(11)
    tw, th, g_ = 330, 160, 24
    x0, y0 = (W - (4 * tw + 3 * g_)) // 2, 280
    for n in range(12):
        x, y = x0 + (n % 4) * (tw + g_), y0 + (n // 4) * (th + g_)
        top = tuple(rnd.randint(30, 120) for _ in range(3))
        for yy in range(th):
            t = yy / th
            col = tuple(int(top[c] * (1 - t) + (200, 120, 160)[c] * t * 0.6) for c in range(3))
            d.line([(x, y + yy), (x + tw, y + yy)], fill=col + (255,))
        d.rectangle((x, y, x + tw, y + th), outline=(255, 255, 255, 90), width=3)
        d.rectangle((x, y + th - 44, x + tw, y + th), fill=(0, 0, 0, 170))
        _small(img, (x + 16, y + th - 22), f"MISSION {n + 1:02d}", 22, anchor="lm")
    out.append({"png": _save(img, folder, stem, 0), "at": 0.0})
    x, y = x0 + 2 * (tw + g_), y0 + (tw + g_) * 0 + (th + g_)
    for k, (dx, at) in enumerate(((0, 0.25), (1, 0.45))):
        img = _new()
        d = ImageDraw.Draw(img)
        if dx:
            d.rectangle((x - 6, y - 6, x + tw + 6, y + th + 6), outline=PINK + (255,), width=8)
        mx, my = x + tw * 0.6, y + th * 0.55
        d.polygon([(mx, my), (mx, my + 60), (mx + 16, my + 46), (mx + 30, my + 74), (mx + 42, my + 68), (mx + 28, my + 40), (mx + 50, my + 40)],
                  fill=WHITE + (255,), outline=(0, 0, 0, 255))
        out.append({"png": _save(img, folder, stem, 1 + k), "at": at})
    img = _new()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((W // 2 - 400, 900, W // 2 + 400, 1010), radius=20, fill=(60, 10, 20, 240), outline=RED + (255,), width=6)
    _label(img, (W // 2, 955), "REPLAY UNAVAILABLE", 64, fill=RED)
    out.append({"png": _save(img, folder, stem, 3), "at": 0.6, "blink": 0})
    return out


_FN = {"minimap": _minimap, "stars": _stars, "heat": _heat, "tiers": _tiers, "carry": _carry, "capacity": _capacity,
       "cash": _cash, "waink": _waink, "focus": _focus, "economy": _economy, "safe": _safe, "agencies": _agencies,
       "profile": _profile, "checklist": _checklist, "cards": _cards, "stats": _stats,
       "download": _download, "scam": _scam, "unlock": _unlock, "nodisc": _nodisc,
       "garage": _garage, "loop": _loop,
       "saves": _saves, "controller": _controller, "archive": _archive}


def layers(template: str, params: str, folder: Path, stem: str) -> List[Dict[str, Any]]:
    fn = _FN.get(str(template or "").strip().lower())
    if fn is None:
        raise ValueError(f"unknown hud card '{template}' (use one of: {', '.join(TEMPLATES)})")
    if fn in (_checklist, _cards, _stats, _download, _scam, _unlock, _nodisc, _garage, _loop, _saves, _controller, _archive):
        return fn(parse(""), folder, stem, str(params or ""))
    return fn(parse(params), folder, stem)


# ---------------------------------------------------------------------------------------------------------------- tracker

ROUTE = [(25.79, -80.20), (25.62, -80.34), (25.47, -80.48), (25.20, -80.43), (25.07, -80.49), (24.93, -80.62), (24.82, -80.80),
         (24.71, -81.08), (24.65, -81.35)]


def tracker_frame(base_small: Image.Image, to_px, t: float, L_: float, title: str, toll: str = "TOLL BRIDGE") -> Image.Image:
    """One frame of the speed-tracker story on the satellite map: the car races down the Keys road at 140 mph (no alarm), slows to
    25 at the bridge toll, the tracker beeps and pings, police dots close in."""
    frame = base_small.copy()
    d = ImageDraw.Draw(frame)
    pts = [to_px(la, lo) for la, lo in ROUTE]
    d.line(pts, fill=(0, 0, 0, 150), width=12, joint="curve")
    d.line(pts, fill=(255, 255, 255, 170), width=6, joint="curve")
    slow_at = 0.55
    u = t / max(0.1, L_)
    prog = min(1.0, (u / slow_at) * 0.72) if u < slow_at else 0.72 + min(0.06, (u - slow_at) * 0.12)
    seg = prog * (len(pts) - 1)
    i = min(int(seg), len(pts) - 2)
    f = seg - i
    cx = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f
    cy = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f
    done = pts[: i + 1] + [(cx, cy)]
    if len(done) >= 2:
        d.line(done, fill=PINK + (255,), width=8, joint="curve")
    pinging = u >= slow_at
    if pinging:
        k = (t * 1.6) % 1.0
        for ring in (k, (k + 0.5) % 1.0):
            r = 30 + 260 * ring
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=RED + (int(230 * (1 - ring)),), width=6)
        q = min(1.0, (u - slow_at) / 0.4)
        for ang in (20, 110, 200, 290):
            a = math.radians(ang)
            dist = 420 * (1 - 0.75 * q)
            px, py = cx + dist * math.cos(a), cy + dist * math.sin(a)
            col = RED if int(t * 4) % 2 else BLUE
            d.ellipse((px - 13, py - 13, px + 13, py + 13), fill=col + (255,), outline=WHITE + (255,), width=3)
    d.ellipse((cx - 16, cy - 16, cx + 16, cy + 16), fill=(PINK if not pinging else RED) + (255,), outline=WHITE + (255,), width=4)
    # speedometer
    mph = 140 if u < slow_at * 0.85 else max(25, int(140 - (u - slow_at * 0.85) / (slow_at * 0.15) * 115))
    gx, gy, gr = W - 260, H - 250, 170
    d.ellipse((gx - gr, gy - gr, gx + gr, gy + gr), fill=(10, 14, 30, 230), outline=WHITE + (220,), width=6)
    a = math.radians(150 + 240 * mph / 160)
    d.line([(gx, gy), (gx + (gr - 30) * math.cos(a), gy + (gr - 30) * math.sin(a))], fill=(RED if pinging else AMBER) + (255,), width=8)
    L.shadow_text(frame, (gx, gy + 60), f"{mph}", L.font(L.F_HEAD, 84), fill=WHITE)
    L.shadow_text(frame, (gx, gy + 115), "MPH", L.font(L.F_TAG, 26), fill=(200, 200, 215))
    if pinging and int(t * 4) % 2 == 0:
        L.pill(frame, (gx - 150, gy - gr - 80), "TRACKER ACTIVE", RED, 32)
    elif not pinging:
        L.pill(frame, (gx - 150, gy - gr - 80), "TRACKER SILENT", (60, 70, 90), 32)
    if title:
        L.shadow_text(frame, (W // 2, 110), title, L.fit(title, L.F_HEAD, 96, W - 300))
    L.pill(frame, (60, 56), "ILLUSTRATION", (90, 90, 110), 30)
    return frame
