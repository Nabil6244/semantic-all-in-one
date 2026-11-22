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
             "profile", "checklist", "cards", "stats", "download", "scam", "unlock", "nodisc", "garage", "loop", "saves", "controller", "archive", "firsts", "wasted", "stuck", "quote", "void", "launch",
             "dpad", "grind", "grid", "prefix", "pyramid", "lockout", "filter")


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


def _firsts(p, folder, stem, raw=""):
    """A 'world firsts' board, rows ticking in one by one: 'HEAD/SUB::FIRST GLITCH=0:41|FIRST TIGER DEATH=1:12|FIRST 100%=?'
    (a value of '?' stays open, blinking)."""
    head, rest = _split_head(raw, "GTA VI WORLD FIRSTS")
    head, _s, sub = head.partition("/")
    items = [(x.split("=", 1) + [""])[:2] for x in rest.split("|") if x.strip()][:6]
    out = [{"png": _save(_frame(head.upper(), (sub or "LAUNCH NIGHT LOG").upper()), folder, stem, 0), "at": 0.0}]
    rh = min(124, 600 // max(1, len(items)))
    for k, (name, val) in enumerate(items):
        name, val = name.strip(), val.strip()
        open_ = val in ("", "?")
        img = _new()
        d = ImageDraw.Draw(img)
        y = 300 + (640 - rh * len(items)) // 2 + k * rh
        col = AMBER if open_ else GREEN
        d.rounded_rectangle((300, y, W - 300, y + rh - 20), radius=22, fill=(16, 20, 44, 235), outline=col + (200,), width=4)
        cx, cy, r = 370, y + (rh - 20) / 2, (rh - 20) * 0.32
        if open_:
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=AMBER + (255,), width=6)
            _label(img, (cx, cy + 2), "?", int(r * 1.5), fill=AMBER)
        else:
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GREEN + (255,))
            d.line([(cx - r * .45, cy), (cx - r * .1, cy + r * .38), (cx + r * .5, cy - r * .35)], fill=WHITE + (255,), width=6)
        _label(img, (440, cy), name.upper(), int(rh * 0.40), anchor="lm")
        _label(img, (W - 340, cy), "UNCLAIMED" if open_ else val.upper(), int(rh * 0.36), fill=col, anchor="rm")
        item = {"png": _save(img, folder, stem, k + 1), "at": 0.06 + 0.8 * k / max(1, len(items))}
        if open_:
            item["blink"] = 1
        out.append(item)
    return out


def _wasted(p, folder, stem, raw=""):
    """Death screens side by side: GTA V's grey 'WASTED' banner vs GTA VI's red wash: 'HEAD::LEFT WORD|RIGHT WORD|footer'."""
    head, rest = _split_head(raw, "HOW YOU DIE NOW")
    parts = [x.strip() for x in rest.split("|")] + ["", "", ""]
    lw, rw, foot = parts[0] or "WASTED", parts[1] or "WASTED", parts[2]
    out = [{"png": _save(_frame(head.upper(), "DEATH SCREEN  ·  ILLUSTRATION"), folder, stem, 0), "at": 0.0}]
    bw, bh, y0 = 760, 430, 300
    for k, (x, tag, word, grey) in enumerate(((150, "GTA V  ·  2013", lw, True), (W - 150 - bw, "GTA VI  ·  2026", rw, False))):
        img = _new()
        d = ImageDraw.Draw(img)
        for yy in range(bh):
            t = yy / bh
            c = (int(70 + 40 * t),) * 3 if grey else (int(150 - 60 * t), int(20 + 10 * t), int(40 + 10 * t))
            d.line([(x, y0 + yy), (x + bw, y0 + yy)], fill=c + (255,))
        d.rectangle((x, y0, x + bw, y0 + bh), outline=(255, 255, 255, 120), width=4)
        if grey:
            d.rectangle((x, y0 + bh // 2 - 60, x + bw, y0 + bh // 2 + 60), fill=(0, 0, 0, 170))
            _label(img, (x + bw // 2, y0 + bh // 2), word.upper(), 110, fill=(200, 30, 30))
        else:
            L.shadow_text(img, (x + bw // 2, y0 + bh // 2), word.lower(), L.font(L.F_HEAD, 120), fill=WHITE)
        L.pill(img, (x, y0 + bh + 26), tag, (60, 70, 90) if grey else RED, 32)
        out.append({"png": _save(img, folder, stem, k + 1), "at": 0.08 + 0.32 * k})
    if foot:
        img = _new()
        _label(img, (W // 2, 960), foot.upper(), 50, fill=AMBER)
        out.append({"png": _save(img, folder, stem, 3), "at": 0.7})
    return out


def _stuck(p, folder, stem, raw=""):
    """Top-down breakdown of a car beached in a hedge: rocks under the frame, wheels spinning in the air, the camera inside the
    leaves. Callouts light one by one: 'HEAD::ROCKS LIFT THE FRAME|WHEELS SPIN IN THE AIR|CAMERA CLIPS INTO THE HEDGE'."""
    head, rest = _split_head(raw, "WHY THE TRUCK WON'T MOVE")
    calls = [x.strip() for x in rest.split("|") if x.strip()][:3] or ["ROCKS LIFT THE FRAME", "WHEELS SPIN IN THE AIR",
                                                                    "CAMERA CLIPS INTO THE HEDGE"]
    img = _frame(head.upper(), "TOP-DOWN X-RAY VIEW")
    d = ImageDraw.Draw(img)
    rnd = random.Random(5)
    for _ in range(90):                                    # hedge blobs
        x, y, r = rnd.randint(330, 1590), rnd.randint(300, 1000), rnd.randint(30, 70)
        g = rnd.randint(60, 120)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(20, g, 40, 230))
    cx, cy, cw, ch = W // 2, 640, 300, 560                # the truck from above
    d.rounded_rectangle((cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2), radius=50, fill=(45, 55, 60, 255), outline=WHITE + (200,), width=5)
    d.rectangle((cx - cw / 2 + 30, cy - 20, cx + cw / 2 - 30, cy + ch / 2 - 40), fill=(25, 30, 35, 255), outline=(255, 255, 255, 90), width=3)
    d.rounded_rectangle((cx - cw / 2 + 40, cy - ch / 2 + 50, cx + cw / 2 - 40, cy - ch / 2 + 140), radius=16, fill=(90, 120, 140, 255))
    out = [{"png": _save(img, folder, stem, 0), "at": 0.0}]
    wheels = [(cx - cw / 2 - 18, cy - ch / 2 + 110), (cx + cw / 2 + 18, cy - ch / 2 + 110),
              (cx - cw / 2 - 18, cy + ch / 2 - 110), (cx + cw / 2 + 18, cy + ch / 2 - 110)]
    # 1: rocks under the frame
    a = _new()
    d = ImageDraw.Draw(a)
    for rx, ry in ((cx - 60, cy + 40), (cx + 70, cy - 90), (cx - 10, cy + 200)):
        d.polygon([(rx - 70, ry + 20), (rx - 40, ry - 45), (rx + 30, ry - 55), (rx + 75, ry + 5), (rx + 40, ry + 50), (rx - 30, ry + 48)],
                  fill=(150, 145, 135, 235), outline=AMBER + (255,))
    for wx, wy in wheels:
        d.rounded_rectangle((wx - 22, wy - 52, wx + 22, wy + 52), radius=10, fill=(15, 15, 18, 255), outline=(255, 255, 255, 120), width=2)
    L.pill(a, (180, 360), "1  " + calls[0].upper(), AMBER, 30)
    out.append({"png": _save(a, folder, stem, 1), "at": 0.15})
    # 2: wheels spin (two frames swapped by blink)
    b = _new()
    d = ImageDraw.Draw(b)
    for wx, wy in wheels:
        for r in (70, 95):
            d.arc((wx - r, wy - r, wx + r, wy + r), 200, 320, fill=TEAL + (255,), width=6)
            d.arc((wx - r, wy - r, wx + r, wy + r), 20, 140, fill=TEAL + (255,), width=6)
    L.pill(b, (180, 460), "2  " + calls[1].upper(), TEAL, 30)
    out.append({"png": _save(b, folder, stem, 2), "at": 0.4, "blink": 1})
    # 3: camera icon inside the leaves
    c = _new()
    d = ImageDraw.Draw(c)
    kx, ky = cx + 420, cy - 200
    d.rounded_rectangle((kx - 70, ky - 45, kx + 70, ky + 45), radius=14, fill=(20, 20, 30, 255), outline=PINK + (255,), width=5)
    d.ellipse((kx - 30, ky - 30, kx + 30, ky + 30), outline=PINK + (255,), width=6)
    for _ in range(14):
        x, y, r = kx + rnd.randint(-110, 110), ky + rnd.randint(-90, 90), rnd.randint(18, 34)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(30, 140, 60, 200))
    L.pill(c, (kx - 200, ky + 110), "3  " + calls[2].upper(), PINK, 30)
    out.append({"png": _save(c, folder, stem, 3), "at": 0.65})
    return out


def _wrap(text, n):
    words, lines, cur = str(text).split(), [], ""
    for w_ in words:
        tt = (cur + " " + w_).strip()
        if len(tt) > n and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = tt
    if cur:
        lines.append(cur)
    return lines


def _quote(p, folder, stem, raw=""):
    """A big pull quote with its source: 'HEAD::quote text|who said it|where it ran'. Not a mock post: plain quote card."""
    head, rest = _split_head(raw, "WHAT PLAYERS ARE SAYING")
    parts = [x.strip() for x in rest.split("|")] + ["", "", ""]
    q, who, where = parts[0], parts[1], parts[2]
    out = [{"png": _save(_frame(head.upper()), folder, stem, 0), "at": 0.0}]
    img = _new()
    d = ImageDraw.Draw(img)
    lines = _wrap(q.upper(), 26)[:4]
    bh = 150 + 110 * len(lines)
    y0 = 300 + (600 - bh) // 2
    d.rounded_rectangle((260, y0, W - 260, y0 + bh), radius=36, fill=(16, 20, 44, 240), outline=PINK + (255,), width=6)
    L.shadow_text(img, (330, y0 + 70), "“", L.font(L.F_HEAD, 200), fill=PINK, anchor="mm")
    for j, ln in enumerate(lines):
        _label(img, (W // 2, y0 + 120 + j * 110), ln, 88 if len(lines) < 3 else 74)
    out.append({"png": _save(img, folder, stem, 1), "at": 0.08})
    if who or where:
        img = _new()
        _label(img, (W // 2, y0 + bh + 60), who.upper(), 46, fill=TEAL)
        if where:
            _small(img, (W // 2, y0 + bh + 112), where.upper(), 30)
        out.append({"png": _save(img, folder, stem, 2), "at": 0.35})
    return out


def _void(p, folder, stem, raw=""):
    """Under the map: black void, a falling figure lit by a phone, a 'no way back' warning: 'HEAD::warning|footer'."""
    head, rest = _split_head(raw, "THE SHADOW REALM")
    parts = [x.strip() for x in rest.split("|")] + ["", ""]
    img = _new()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, H), fill=(0, 0, 0, 245))
    rnd = random.Random(3)
    for _ in range(60):                                    # a few broken world triangles drifting overhead
        x, y = rnd.randint(0, W), rnd.randint(0, 260)
        s_ = rnd.randint(20, 70)
        d.polygon([(x, y), (x + s_, y + rnd.randint(-20, 20)), (x + rnd.randint(-20, 20), y + s_)], fill=(40, 46, 60, 200))
    L.shadow_text(img, (W // 2, 120), head.upper(), L.fit(head.upper(), L.F_HEAD, 104, W - 400))
    L.pill(img, (60, 56), "ILLUSTRATION", (90, 90, 110), 30)
    out = [{"png": _save(img, folder, stem, 0), "at": 0.0}]
    fig = _new()
    d = ImageDraw.Draw(fig)
    cx, cy = W // 2, 600
    for r, a in ((260, 30), (180, 50), (110, 80)):
        d.ellipse((cx + 40 - r, cy - 40 - r, cx + 40 + r, cy - 40 + r), fill=(80, 160, 255, a))
    d.ellipse((cx - 34, cy - 170, cx + 34, cy - 102), fill=(30, 30, 36, 255), outline=(120, 170, 255, 255), width=3)
    d.rounded_rectangle((cx - 50, cy - 100, cx + 50, cy + 60), radius=24, fill=(30, 30, 36, 255), outline=(120, 170, 255, 255), width=3)
    d.line([(cx - 30, cy + 55), (cx - 60, cy + 200)], fill=(30, 30, 36, 255), width=34)
    d.line([(cx + 30, cy + 55), (cx + 50, cy + 200)], fill=(30, 30, 36, 255), width=34)
    d.line([(cx + 40, cy - 70), (cx + 70, cy - 30)], fill=(30, 30, 36, 255), width=24)
    d.rounded_rectangle((cx + 58, cy - 70, cx + 98, cy - 4), radius=8, fill=(170, 210, 255, 255))
    out.append({"png": _save(fig, folder, stem, 1), "at": 0.1})
    if parts[0]:
        w_ = _new()
        dd = ImageDraw.Draw(w_)
        dd.rounded_rectangle((W // 2 - 520, 860, W // 2 + 520, 960), radius=20, fill=(60, 10, 20, 240), outline=RED + (255,), width=6)
        _label(w_, (W // 2, 910), parts[0].upper(), 54, fill=RED)
        out.append({"png": _save(w_, folder, stem, 2), "at": 0.45, "blink": 1})
    if parts[1]:
        f_ = _new()
        _small(f_, (W // 2, 1010), parts[1].upper(), 30)
        out.append({"png": _save(f_, folder, stem, 3), "at": 0.6})
    return out


def _launch(p, folder, stem, raw=""):
    """Launch arcs: an object hits a trap and the car flies along an arc that draws in steps.
    'HEAD::2008=SWINGSET|2026=TREE' (one or two arcs)."""
    head, rest = _split_head(raw, "LAUNCHED INTO ORBIT")
    items = [(x.split("=", 1) + [""])[:2] for x in rest.split("|") if x.strip()][:2] or [["2008", "SWINGSET"], ["2026", "TREE"]]
    out = [{"png": _save(_frame(head.upper(), "SAME PHYSICS MEME  ·  18 YEARS APART"), folder, stem, 0), "at": 0.0}]
    k = 1
    pal = [AMBER, PINK]
    n = len(items)
    for i, (year, trap) in enumerate(items):
        col = pal[i % 2]
        x0 = 220 if n == 2 else 560
        span = 700 if n == 2 else 900
        x0 += i * 820
        gy = 900
        base = _new()
        d = ImageDraw.Draw(base)
        d.line([(x0 - 60, gy), (x0 + span + 40, gy)], fill=(255, 255, 255, 140), width=4)
        if "SWING" in trap.upper():
            d.line([(x0 - 30, gy), (x0 + 10, gy - 150), (x0 + 50, gy)], fill=WHITE + (230,), width=6)
            d.line([(x0 + 10, gy - 150), (x0 + 10, gy - 60)], fill=WHITE + (230,), width=3)
            d.rectangle((x0 - 5, gy - 62, x0 + 25, gy - 54), fill=WHITE + (230,))
        else:
            d.rectangle((x0 + 2, gy - 90, x0 + 18, gy), fill=(120, 80, 40, 255))
            d.ellipse((x0 - 50, gy - 210, x0 + 70, gy - 80), fill=(30, 140, 60, 255))
        L.pill(base, (x0 - 60, gy + 24), f"{year}  ·  {trap}".upper(), col, 30)
        out.append({"png": _save(base, folder, stem, k), "at": 0.05 + 0.4 * i})
        k += 1
        pts = []
        for j in range(41):
            t = j / 40
            pts.append((x0 + 40 + span * t, gy - 40 - 560 * 4 * t * (1 - t)))
        for step in range(1, 5):
            img = _new()
            d = ImageDraw.Draw(img)
            seg = pts[: 1 + step * 10]
            d.line(seg, fill=col + (255,), width=8, joint="curve")
            cx_, cy_ = seg[-1]
            d.rounded_rectangle((cx_ - 46, cy_ - 22, cx_ + 46, cy_ + 22), radius=10, fill=WHITE + (255,), outline=col + (255,), width=4)
            out.append({"png": _save(img, folder, stem, k), "at": 0.1 + 0.4 * i + 0.07 * step})
            k += 1
    return out



# ---------------------------------------------------------------------------------------------------------------- cheat cards

_DIRS = {"U": 0, "R": 90, "D": 180, "L": 270}


def _arrow(d, cx, cy, s, dirn, col, cap=(16, 20, 44, 240), edge=None):
    """One D-pad keycap with an arrow pointing up/right/down/left (drawn, so no font glyphs are needed)."""
    d.rounded_rectangle((cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2), radius=int(s * .18), fill=cap,
                        outline=(edge or col) + (255,), width=max(3, int(s * .05)))
    if dirn not in _DIRS:
        return
    a = math.radians(_DIRS[dirn])
    pts = [(0, -.32), (.26, -.02), (.11, -.02), (.11, .3), (-.11, .3), (-.11, -.02), (-.26, -.02)]
    out = []
    for x, y in pts:
        out.append((cx + s * (x * math.cos(a) - y * math.sin(a)), cy + s * (x * math.sin(a) + y * math.cos(a))))
    d.polygon(out, fill=col + (255,))


def _seq(code: str) -> List[str]:
    return [c for c in str(code or "").upper() if c in "URDL?"]


def _dpad(p, folder, stem, raw=""):
    """A cheat code typed in arrow by arrow: 'NAME::URDLULDR|unlock rule|CONFIRMED|7' (code '?' = still unknown,
    last part = how many opening arrows to tint as the shared prefix)."""
    head, rest = _split_head(raw, "CHEAT CODE")
    parts = [x.strip() for x in rest.split("|")] + ["", "", "", ""]
    seq = _seq(parts[0]) or list("?" * 10)
    rule, status = parts[1], (parts[2] or ("CODE TBC" if "?" in seq else "CODE CONFIRMED")).upper()
    pre = int(parts[3]) if parts[3].isdigit() else 0
    out = [{"png": _save(_frame(head.upper(), rule.upper()), folder, stem, 0), "at": 0.0}]
    n = len(seq)
    s = min(150, int((W - 260) / n) - 18)
    gap = s + 18
    x0 = W // 2 - gap * (n - 1) / 2
    y = 560
    base = _new()
    d = ImageDraw.Draw(base)
    for i in range(n):
        d.rounded_rectangle((x0 + i * gap - s / 2, y - s / 2, x0 + i * gap + s / 2, y + s / 2), radius=int(s * .18),
                            outline=(255, 255, 255, 70), width=3)
    _small(base, (W // 2, y + s / 2 + 60), "D-PAD ONLY  ·  SAME ON PS5 AND XBOX", 28, fill=(200, 200, 215))
    out.append({"png": _save(base, folder, stem, 1), "at": 0.02})
    for i, c in enumerate(seq):
        img = _new()
        d = ImageDraw.Draw(img)
        col = TEAL if i < pre else (AMBER if c == "?" else PINK)
        _arrow(d, x0 + i * gap, y, s, c, col)
        if c == "?":
            _label(img, (x0 + i * gap, y), "?", int(s * .6), fill=AMBER)
        out.append({"png": _save(img, folder, stem, 2 + i), "at": 0.08 + 0.6 * i / max(1, n), "blink": 1 if c == "?" else 0})
    if pre:
        img = _new()
        d = ImageDraw.Draw(img)
        xa, xb = x0 - s / 2, x0 + (pre - 1) * gap + s / 2
        d.line([(xa, y - s / 2 - 30), (xa, y - s / 2 - 50), (xb, y - s / 2 - 50), (xb, y - s / 2 - 30)], fill=TEAL + (255,), width=6)
        _small(img, ((xa + xb) / 2, y - s / 2 - 85), f"SHARED FIRST {pre}", 30, fill=TEAL)
        out.append({"png": _save(img, folder, stem, 30), "at": 0.72})
    img = _new()
    col = AMBER if "TBC" in status or "?" in seq else GREEN
    L.pill(img, (W // 2, 880), status, col, 44, anchor="mt")
    out.append({"png": _save(img, folder, stem, 40), "at": 0.78, "blink": 1 if col == AMBER else 0})
    return out


def _grind(p, folder, stem, raw=""):
    """A challenge counter filling to its target, then the cheat it unlocks: 'NAME::100|GYM WORKOUTS|BODY ARMOR'."""
    head, rest = _split_head(raw, "THE GRIND")
    parts = [x.strip() for x in rest.split("|")] + ["", "", ""]
    goal, what, prize = parts[0] or "100", parts[1] or "CHALLENGES", parts[2]
    num = float(re.sub(r"[^0-9.]", "", goal) or 100)
    out = [{"png": _save(_frame(head.upper(), "UNLOCK REQUIREMENT"), folder, stem, 0), "at": 0.0}]
    cx, cy, r = W // 2, 600, 250
    base = _new()
    d = ImageDraw.Draw(base)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, 60), width=34)
    _small(base, (cx, cy + 90), what.upper(), 34 if len(what) < 22 else 26)
    out.append({"png": _save(base, folder, stem, 1), "at": 0.02})
    steps = 5
    for k in range(1, steps + 1):
        img = _new()
        d = ImageDraw.Draw(img)
        frac = k / steps
        d.rounded_rectangle((cx - 205, cy - 105, cx + 205, cy + 55), radius=30, fill=(22, 28, 58, 255))
        d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * frac, fill=(GREEN if k == steps else PINK) + (255,), width=34)
        v = num * frac
        txt = goal if k == steps else (f"{v:,.0f}" if num >= 10 else f"{v:.1f}")
        if goal.startswith("$"):
            txt = goal if k == steps else f"${v:,.0f}"
        _label(img, (cx, cy - 20), txt, 130 if len(txt) < 6 else 96, fill=GREEN if k == steps else WHITE)
        out.append({"png": _save(img, folder, stem, 1 + k), "at": 0.06 + 0.13 * (k - 1)})
    if prize:
        img = _new()
        L.pill(img, (W // 2, 935), f"UNLOCKS  ·  {prize.upper()}", GREEN, 46, anchor="mt")
        out.append({"png": _save(img, folder, stem, 20), "at": 0.72})
    return out


def _grid(p, folder, stem, raw=""):
    """61 cheat tiles, a few lit and the rest locked: 'HEAD::61|4|UNLOCKED AT THE CREDITS|LOCKED BEHIND CHALLENGES'."""
    head, rest = _split_head(raw, "ALL 61 CHEATS")
    parts = [x.strip() for x in rest.split("|")] + ["", "", "", ""]
    total = int(parts[0]) if parts[0].isdigit() else 61
    lit = int(parts[1]) if parts[1].isdigit() else 4
    out = [{"png": _save(_frame(head.upper(), f"{lit} OF {total}"), folder, stem, 0), "at": 0.0}]
    cols = 13
    s, gap = 92, 112
    x0 = W // 2 - gap * (cols - 1) / 2
    y0 = 330
    base = _new()
    d = ImageDraw.Draw(base)
    for i in range(total):
        x, y = x0 + (i % cols) * gap, y0 + (i // cols) * gap
        d.rounded_rectangle((x - s / 2, y - s / 2, x + s / 2, y + s / 2), radius=14, fill=(16, 20, 44, 230), outline=(255, 255, 255, 60), width=3)
        icon(d, "lock", x, y, s * .62, (120, 125, 150))
    out.append({"png": _save(base, folder, stem, 1), "at": 0.03})
    batch = max(1, lit // 6 + 1)
    k = 2
    for b in range(0, lit, batch):
        img = _new()
        d = ImageDraw.Draw(img)
        for i in range(b, min(lit, b + batch)):
            x, y = x0 + (i % cols) * gap, y0 + (i // cols) * gap
            d.rounded_rectangle((x - s / 2, y - s / 2, x + s / 2, y + s / 2), radius=14, fill=GREEN + (255,), outline=WHITE + (255,), width=4)
            d.line([(x - 22, y + 2), (x - 6, y + 18), (x + 24, y - 16)], fill=WHITE + (255,), width=9)
        out.append({"png": _save(img, folder, stem, k), "at": 0.15 + 0.4 * b / max(1, lit)})
        k += 1
    img = _new()
    rows = (total - 1) // cols + 1
    yb = y0 + rows * gap + 10
    if parts[2]:
        _label(img, (W // 2 - 420, yb), f"{lit}  ·  {parts[2].upper()}", 38, fill=GREEN)
    if parts[3]:
        _label(img, (W // 2 + 420, yb), f"{total - lit}  ·  {parts[3].upper()}", 38, fill=(190, 190, 205))
    out.append({"png": _save(img, folder, stem, 40), "at": 0.65})
    return out


def _prefix(p, folder, stem, raw=""):
    """Codes stacked so their shared opening arrows line up: 'HEAD::MAX AMMO=DURDLLUUDL|INFINITE AMMO=DURDLLUDDD'."""
    head, rest = _split_head(raw, "THE CODE FAMILY")
    items = [(a.strip(), _seq(b)) for a, b in (x.split("=", 1) for x in rest.split("|") if "=" in x)][:4]
    pre = 0
    if items:
        while all(len(q) > pre for _n, q in items) and len({q[pre] for _n, q in items}) == 1:
            pre += 1
    out = [{"png": _save(_frame(head.upper(), f"SAME FIRST {pre} ARROWS" if pre else ""), folder, stem, 0), "at": 0.0}]
    s, gap = 88, 102
    x0 = 720
    for r, (name, q) in enumerate(items):
        y = 360 + r * 165
        img = _new()
        d = ImageDraw.Draw(img)
        _label(img, (x0 - 90, y), name.upper(), 44 if len(name) < 14 else 34, anchor="rm")
        for i, c in enumerate(q):
            _arrow(d, x0 + i * gap, y, s, c, TEAL if i < pre else PINK)
        out.append({"png": _save(img, folder, stem, 1 + r), "at": 0.08 + 0.17 * r})
    if pre and items:
        img = _new()
        d = ImageDraw.Draw(img)
        y1, y2 = 360 - s / 2 - 22, 360 + (len(items) - 1) * 165 + s / 2 + 22
        d.rounded_rectangle((x0 - s / 2 - 16, y1, x0 + (pre - 1) * gap + s / 2 + 16, y2), radius=20, outline=TEAL + (255,), width=7)
        _small(img, (x0 + (pre - 1) * gap / 2, y2 + 45), "SAME PREFIX", 32, fill=TEAL)
        _small(img, (x0 + pre * gap + (max(len(q) for _n, q in items) - pre - 1) * gap / 2, y2 + 45), "PICKS THE CHEAT", 32, fill=PINK)
        out.append({"png": _save(img, folder, stem, 20), "at": 0.1 + 0.17 * len(items), "blink": 0})
    return out


def _pyramid(p, folder, stem, raw=""):
    """A ladder of tiers built from the bottom up, top tier glowing: 'HEAD::P-996 LAZER=Every challenge|...|DISCOVER=Bulldozer'."""
    head, rest = _split_head(raw, "THE UNLOCK LADDER")
    tiers = [(x.split("=", 1) + [""])[:2] for x in rest.split("|") if x.strip()][:6]
    n = len(tiers)
    out = [{"png": _save(_frame(head.upper(), "BOTTOM RUNG TO SUMMIT"), folder, stem, 0), "at": 0.0}]
    top, bottom = 280, 1010
    th = (bottom - top) / max(1, n)
    pal = [AMBER, PINK, (170, 90, 255), TEAL, BLUE, GREEN]
    for j in range(n):            # j = 0 bottom rung
        name, note = tiers[n - 1 - j]
        y2 = bottom - j * th
        y1 = y2 - th + 14
        half = 300 + (n - 1 - j) * 110
        col = pal[(n - 1 - j) % len(pal)]
        img = _new()
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((W // 2 - half, y1, W // 2 + half, y2), radius=18, fill=(16, 20, 44, 235), outline=col + (255,), width=6)
        ym = (y1 + y2) / 2
        _label(img, (W // 2, ym - (16 if note else 0)), name.upper(), 46 if len(name) < 22 else 34, fill=col)
        if note:
            _small(img, (W // 2, ym + 30), note.upper(), 26)
        out.append({"png": _save(img, folder, stem, 1 + j), "at": 0.06 + 0.7 * j / max(1, n), "blink": 1 if j == n - 1 else 0})
    return out


def _lockout(p, folder, stem, raw=""):
    """What a cheat switches off, each stamped with a red X: 'HEAD::TROPHIES|ACHIEVEMENTS|MANUAL SAVES|reload a clean save'."""
    head, rest = _split_head(raw, "CHEAT ACTIVE")
    parts = [x.strip() for x in rest.split("|") if x.strip()]
    items, foot = (parts[:-1], parts[-1]) if len(parts) > 3 else (parts or ["TROPHIES", "ACHIEVEMENTS", "SAVING"], "")
    out = [{"png": _save(_frame(head.upper(), "FOR THE WHOLE SESSION"), folder, stem, 0), "at": 0.0}]
    n = len(items)
    bw = 460
    x0 = W // 2 - (bw + 40) * (n - 1) / 2
    for i, it in enumerate(items):
        x = x0 + i * (bw + 40)
        img = _new()
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((x - bw / 2, 380, x + bw / 2, 760), radius=30, fill=(16, 20, 44, 235), outline=(255, 255, 255, 120), width=5)
        _label(img, (x, 712), it.upper(), 44 if len(it) < 12 else 34)
        out.append({"png": _save(img, folder, stem, 1 + i), "at": 0.05 + 0.08 * i})
        img = _new()
        d = ImageDraw.Draw(img)
        d.line([(x - 110, 420), (x + 110, 650)], fill=RED + (255,), width=26)
        d.line([(x + 110, 420), (x - 110, 650)], fill=RED + (255,), width=26)
        out.append({"png": _save(img, folder, stem, 10 + i), "at": 0.3 + 0.12 * i})
    img = _new()
    L.pill(img, (W // 2, 880), "DISABLED", RED, 56, anchor="mt")
    out.append({"png": _save(img, folder, stem, 20), "at": 0.3 + 0.12 * n, "blink": 1})
    if foot:
        img = _new()
        _small(img, (W // 2, 990), foot.upper(), 32, fill=AMBER)
        out.append({"png": _save(img, folder, stem, 21), "at": 0.75})
    return out


FILTERS = {  # kind -> (tint rgba, label colour)
    "dark": ((0, 0, 0, 200), (200, 200, 215)), "bubblegum": ((190, 60, 230, 110), (255, 230, 60)),
    "golden": ((255, 170, 60, 80), AMBER), "dollhouse": ((255, 120, 200, 60), PINK), "migraine": ((255, 255, 255, 40), RED),
    "pixel": ((40, 200, 120, 40), GREEN), "hellscape": ((200, 20, 10, 120), RED), "fisheye": ((40, 110, 255, 40), BLUE),
    "videotape": ((30, 40, 60, 60), WHITE), "pinhole": ((0, 0, 0, 0), WHITE), "powdered": ((255, 255, 255, 140), (40, 60, 120)),
    "neon": ((30, 230, 120, 70), (255, 60, 200)), "yesteryear": ((150, 110, 60, 110), (255, 220, 160)),
    "faded": ((150, 150, 150, 120), WHITE), "cataclysm": ((230, 80, 20, 110), AMBER), "fast": ((60, 200, 255, 50), TEAL),
}


def _filter(p, folder, stem, raw=""):
    """A screen-filter preview laid over the shot: 'NAME::kind|how to unlock' (kinds in FILTERS)."""
    head, rest = _split_head(raw, "SCREEN FILTER")
    parts = [x.strip() for x in rest.split("|")] + ["", ""]
    kind = parts[0].lower() or "golden"
    tint, col = FILTERS.get(kind, FILTERS["golden"])
    out = []
    img = _new()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, H), fill=tint)
    if kind == "golden":
        d.rectangle((0, 0, W, 170), fill=(0, 0, 0, 255)); d.rectangle((0, H - 170, W, H), fill=(0, 0, 0, 255))
    elif kind == "dollhouse":
        d.rectangle((0, 0, 420, H), fill=(0, 0, 0, 255)); d.rectangle((W - 420, 0, W, H), fill=(0, 0, 0, 255))
    elif kind in ("pinhole", "fisheye"):
        r = 470 if kind == "pinhole" else 640
        mask = Image.new("L", (W, H), 255)
        ImageDraw.Draw(mask).ellipse((W // 2 - r, H // 2 - r, W // 2 + r, H // 2 + r), fill=0)
        black = Image.new("RGBA", (W, H), (0, 0, 0, 245))
        img.paste(black, (0, 0), mask)
    elif kind == "videotape":
        for y in range(0, H, 6):
            d.line([(0, y), (W, y)], fill=(0, 0, 0, 70), width=2)
        L.pill(img, (80, 130), "REC", RED, 40)
    elif kind == "pixel":
        for x in range(0, W, 48):
            d.line([(x, 0), (x, H)], fill=(0, 0, 0, 80), width=3)
        for y in range(0, H, 48):
            d.line([(0, y), (W, y)], fill=(0, 0, 0, 80), width=3)
    elif kind == "migraine":
        for k in range(9):
            r = 120 + k * 110
            d.ellipse((W // 2 - r, H // 2 - r, W // 2 + r, H // 2 + r), outline=(255, 60, 60, 70 - k * 6), width=26)
    out.append({"png": _save(img, folder, stem, 0), "at": 0.0})
    t = _new()
    if kind == "dark":
        txt = _new()
        L.shadow_text(txt, (W // 2, 520), "THE WORLD FLIPS UPSIDE DOWN", L.fit("THE WORLD FLIPS UPSIDE DOWN", L.F_HEAD, 84, W - 500))
        t.alpha_composite(txt.rotate(180))
    L.shadow_text(t, (W // 2, 150 if kind not in ("golden",) else 260), head.upper(), L.fit(head.upper(), L.F_HEAD, 120, W - 500), fill=col)
    L.pill(t, (60, 56), "ILLUSTRATION  ·  FILTER PREVIEW", (90, 90, 110), 30)
    out.append({"png": _save(t, folder, stem, 1), "at": 0.05})
    if parts[1]:
        u = _new()
        L.pill(u, (W // 2, H - 250 if kind != "golden" else H - 260), f"UNLOCK  ·  {parts[1].upper()}", (16, 20, 44), 40, anchor="mt")
        out.append({"png": _save(u, folder, stem, 2), "at": 0.35})
    return out

_FN = {"minimap": _minimap, "stars": _stars, "heat": _heat, "tiers": _tiers, "carry": _carry, "capacity": _capacity,
       "cash": _cash, "waink": _waink, "focus": _focus, "economy": _economy, "safe": _safe, "agencies": _agencies,
       "profile": _profile, "checklist": _checklist, "cards": _cards, "stats": _stats,
       "download": _download, "scam": _scam, "unlock": _unlock, "nodisc": _nodisc,
       "garage": _garage, "loop": _loop,
       "saves": _saves, "controller": _controller, "archive": _archive,
       "firsts": _firsts, "wasted": _wasted, "stuck": _stuck,
       "quote": _quote, "void": _void, "launch": _launch,
       "dpad": _dpad, "grind": _grind, "grid": _grid, "prefix": _prefix, "pyramid": _pyramid, "lockout": _lockout, "filter": _filter}


def layers(template: str, params: str, folder: Path, stem: str) -> List[Dict[str, Any]]:
    fn = _FN.get(str(template or "").strip().lower())
    if fn is None:
        raise ValueError(f"unknown hud card '{template}' (use one of: {', '.join(TEMPLATES)})")
    if fn in (_checklist, _cards, _stats, _download, _scam, _unlock, _nodisc, _garage, _loop, _saves, _controller, _archive, _firsts, _wasted, _stuck, _quote, _void, _launch,
              _dpad, _grind, _grid, _prefix, _pyramid, _lockout, _filter):
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
