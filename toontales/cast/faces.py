"""Draw the flat face parts of a Toon Tales puppet (eyes, mouths, extras) as transparent PNGs.

Every image is a square that covers the front of the round head: the head circle is the
inscribed circle of the square. Eyes and mouths are separate images so any eye state can
play with any mouth shape (Rhubarb A-H/X for speech + expression mouths).

Run: python3 toontales/cast/faces.py <cast.json> <out dir>
"""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024            # drawing size; scaled down at the end for smooth edges
SS = 2              # supersampling
INK = (38, 24, 28, 255)
MOUTH = (96, 30, 42, 255)
TONGUE = (226, 110, 120, 255)
TEETH = (250, 250, 246, 255)
WHITE = (255, 255, 255, 255)
LW = 18             # main ink line width at S (before FEATURE_SCALE)
FEATURE_SCALE = 1.45  # eyes and mouth are drawn small, then scaled up about FEATURE_CENTER
FEATURE_CENTER = (512, 580)

EYE_Y = 470
EYE_DX = 112
MOUTH_Y = 690

EYES = ["open", "wide", "happy", "closed", "half", "angry", "worried", "shock", "wink", "sly",
        "sad", "up", "look_l", "look_r", "dizzy", "money"]
MOUTHS = ["X", "A", "B", "C", "D", "E", "F", "G", "H",
          "smile", "grin", "laugh", "frown", "smirk", "o_shock", "wavy", "grit", "flat"]
GOLD = (236, 176, 40, 255)


def _canvas():
    im = Image.new("RGBA", (S * SS, S * SS), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _k(v):
    return v * SS


def _line(d, pts, w=LW, fill=INK):
    pts = [(_k(x), _k(y)) for x, y in pts]
    d.line(pts, fill=fill, width=int(round(_k(w))), joint="curve")
    r = _k(w) / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def _arc_pts(cx, cy, rx, ry, a0, a1, n=24):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _ellipse(d, cx, cy, rx, ry, fill=None, outline=INK, w=LW):
    box = [_k(cx - rx), _k(cy - ry), _k(cx + rx), _k(cy + ry)]
    if fill is None:
        d.ellipse([box[0] - _k(w) / 2, box[1] - _k(w) / 2, box[2] + _k(w) / 2, box[3] + _k(w) / 2],
                  outline=outline, width=int(_k(w)))
        return
    if outline is not None:
        d.ellipse([box[0] - _k(w) / 2, box[1] - _k(w) / 2, box[2] + _k(w) / 2, box[3] + _k(w) / 2], fill=outline)
    if fill is not None:
        d.ellipse([box[0] + _k(w) / 2, box[1] + _k(w) / 2, box[2] - _k(w) / 2, box[3] - _k(w) / 2], fill=fill)


def _dot(d, cx, cy, r, shine=True):
    d.ellipse([_k(cx - r), _k(cy - r), _k(cx + r), _k(cy + r)], fill=INK)
    if shine:
        s = r * 0.3
        d.ellipse([_k(cx + r * 0.25 - s), _k(cy - r * 0.35 - s), _k(cx + r * 0.25 + s), _k(cy - r * 0.35 + s)], fill=WHITE)


def _brow(d, cx, cy, tilt, side, w=LW * 0.9):
    """tilt > 0 = inner end lower (angry); < 0 = inner end higher (worried)."""
    inner = cx - side * 44
    outer = cx + side * 44
    _line(d, [(outer, cy - tilt * 0.4), (cx, cy - 6), (inner, cy + tilt)], w=w)


def _finish(im, scale=1.0):
    if scale != 1.0:
        cx, cy = _k(FEATURE_CENTER[0]), _k(FEATURE_CENTER[1])
        a = 1.0 / scale  # output -> input mapping
        im = im.transform(im.size, Image.AFFINE, (a, 0, cx - a * cx, 0, a, cy - a * cy), resample=Image.BICUBIC)
    return im.resize((S, S), Image.LANCZOS)


def draw_eyes(state, traits):
    im, d = _canvas()
    brows = traits.get("brows", True)
    by = EYE_Y - 78
    for side in (-1, 1):
        cx = 512 + side * EYE_DX
        cy = EYE_Y
        st = state
        if state == "wink":
            st = "open" if side < 0 else "happy"
        if state == "sly":
            st = "half"
        if st == "open":
            _dot(d, cx, cy, 34)
        elif st == "wide":
            _ellipse(d, cx, cy, 50, 58, fill=WHITE)
            _dot(d, cx + 4, cy + 6, 24)
        elif st == "shock":
            _ellipse(d, cx, cy, 58, 66, fill=WHITE)
            _dot(d, cx, cy, 13, shine=False)
        elif st == "happy":
            _line(d, _arc_pts(cx, cy + 14, 42, 34, 200, 340))
        elif st == "closed":
            _line(d, _arc_pts(cx, cy - 14, 40, 22, 20, 160))
        elif st == "half":
            _dot(d, cx, cy + 6, 32)
            # lid: white cover over the top half, then the lid line
            d.rectangle([_k(cx - 50), _k(cy - 60), _k(cx + 50), _k(cy + 2)], fill=(0, 0, 0, 0))
            _line(d, [(cx - 46, cy + 2), (cx + 46, cy - 2)])
        elif st == "angry":
            _dot(d, cx, cy + 6, 32)
        elif st == "worried":
            _dot(d, cx, cy + 4, 30)
        elif st == "sad":
            _dot(d, cx, cy + 12, 28)
            _line(d, [(cx - side * 44, cy - 30), (cx + side * 40, cy - 12)], w=LW * 0.8)  # heavy droopy lid
        elif st == "up":
            _dot(d, cx + side * 4, cy - 22, 30)
        elif st in ("look_l", "look_r"):
            _dot(d, cx + (-26 if st == "look_l" else 26), cy + 2, 32)
        elif st == "dizzy":
            pts = [(cx + (6 + 5.2 * a) * math.cos(a * 1.0 + side), cy + (6 + 5.2 * a) * math.sin(a * 1.0 + side))
                   for a in [i * 0.25 for i in range(36)]]
            _line(d, pts, w=LW * 0.8)
        elif st == "money":
            _ellipse(d, cx, cy, 54, 60, fill=GOLD)
            # S: upper loop from its right side over the top to the middle, lower loop on round to the left
            _line(d, _arc_pts(cx, cy - 15, 22, 15, 345, 90) + _arc_pts(cx, cy + 15, 22, 15, 270, 525), w=LW * 0.75)
            _line(d, [(cx, cy - 46), (cx, cy + 46)], w=LW * 0.6)
        if brows:
            if st == "angry":
                _brow(d, cx, by + 18, 26, side)
            elif st == "worried":
                _brow(d, cx, by + 6, -22, side)
            elif st in ("shock", "wide"):
                _line(d, _arc_pts(cx, by - 20, 42, 16, 200, 340))
            elif state == "sly" and side > 0:
                _line(d, _arc_pts(cx, by - 18, 42, 16, 200, 340))
            elif st == "sad":
                _brow(d, cx, by + 4, -18, side)
            elif st in ("dizzy", "money"):
                pass
            elif st in ("open", "half", "happy", "closed", "up", "look_l", "look_r"):
                _line(d, _arc_pts(cx, by + 4, 40, 10, 205, 335), w=LW * 0.8)
    if traits.get("glasses"):
        for side in (-1, 1):
            cx = 512 + side * EYE_DX
            d.arc([_k(cx - 70), _k(EYE_Y - 66), _k(cx + 70), _k(EYE_Y + 66)], 0, 360, fill=INK, width=_k(14))
        _line(d, [(512 - EYE_DX + 70, EYE_Y - 8), (512 + EYE_DX - 70, EYE_Y - 8)], w=12)
    return _finish(im, FEATURE_SCALE)


def _mouth_open(d, w, h, teeth_top=False, teeth_bot=False, tongue=False, y=MOUTH_Y, shape="oval"):
    cx = 512
    if shape == "d":       # D-shaped big smile: flat top, round bottom
        pts = [(cx - w, y - h * 0.25)] + _arc_pts(cx, y - h * 0.25, w, h * 1.25, 0, 180)[::-1][::-1]
        pts = [(cx - w, y - h * 0.25), (cx + w, y - h * 0.25)] + _arc_pts(cx, y - h * 0.25, w, h * 1.25, 0, 180)
        kp = [(_k(x), _k(yy)) for x, yy in pts]
        d.polygon(kp, fill=MOUTH)
        top = y - h * 0.25
        if tongue:
            d.ellipse([_k(cx - w * 0.55), _k(top + h * 0.55), _k(cx + w * 0.55), _k(top + h * 1.45)], fill=TONGUE)
        if teeth_top:
            d.rectangle([_k(cx - w * 0.85), _k(top), _k(cx + w * 0.85), _k(top + h * 0.32)], fill=TEETH)
        # re-clip to the D shape by redrawing the outline thick
        _line(d, pts + [pts[0]])
        return
    if shape == "rect":    # rounded box of teeth with a bite line and tooth gaps
        box = [_k(cx - w), _k(y - h), _k(cx + w), _k(y + h)]
        d.rounded_rectangle(box, radius=_k(h * 0.7), fill=TEETH, outline=INK, width=_k(LW))
        _line(d, [(cx - w + 8, y), (cx + w - 8, y)], w=LW * 0.6)
        for i in range(1, 4):
            x = cx - w + 2 * w * i / 4
            _line(d, [(x, y - h + 6), (x, y + h - 6)], w=LW * 0.5)
        return
    box = [_k(cx - w), _k(y - h), _k(cx + w), _k(y + h)]
    d.ellipse(box, fill=MOUTH)
    if tongue:
        d.ellipse([_k(cx - w * 0.6), _k(y + h * 0.05), _k(cx + w * 0.6), _k(y + h * 1.1)], fill=TONGUE)
    if teeth_top:
        d.chord([_k(cx - w), _k(y - h), _k(cx + w), _k(y + h)], 200, 340, fill=TEETH)
    if teeth_bot:
        d.chord([_k(cx - w), _k(y - h), _k(cx + w), _k(y + h)], 25, 155, fill=TEETH)
    _ellipse(d, cx, y, w, h, fill=None)


def draw_mouth(state, traits):
    im, d = _canvas()
    cx, y = 512, MOUTH_Y
    if state == "X":                       # rest: small easy smile
        _line(d, _arc_pts(cx, y - 30, 58, 30, 35, 145))
    elif state == "A":                     # M B P: pressed lips
        _line(d, [(cx - 52, y), (cx, y + 4), (cx + 52, y)])
    elif state == "B":                     # K S T: teeth slightly apart
        _mouth_open(d, 56, 18, teeth_top=True, teeth_bot=True)
    elif state == "C":                     # EH AE
        _mouth_open(d, 58, 32, teeth_top=True)
    elif state == "D":                     # AA wide open
        _mouth_open(d, 66, 50, teeth_top=True, tongue=True)
    elif state == "E":                     # AO ER rounded
        _mouth_open(d, 42, 40)
    elif state == "F":                     # UW OW W pucker
        _mouth_open(d, 24, 26)
    elif state == "G":                     # F V: top teeth on lip
        _mouth_open(d, 52, 20, teeth_top=True)
        _line(d, [(cx - 50, y + 14), (cx + 50, y + 14)], w=LW * 0.8)
    elif state == "H":                     # L: tongue up
        _mouth_open(d, 52, 38, tongue=True)
    elif state == "smile":
        _line(d, _arc_pts(cx, y - 60, 100, 70, 30, 150))
    elif state == "grin":
        _mouth_open(d, 110, 44, teeth_top=True, shape="d")
    elif state == "laugh":
        _mouth_open(d, 104, 62, tongue=True, teeth_top=True, shape="d")
    elif state == "frown":
        _line(d, _arc_pts(cx, y + 50, 76, 46, 210, 330))
    elif state == "smirk":
        _line(d, [(cx - 60, y + 8), (cx + 10, y + 10)] + _arc_pts(cx + 40, y - 20, 40, 30, 90, 0)[::-1][-8:])
    elif state == "o_shock":
        _mouth_open(d, 46, 58)
    elif state == "grit":                  # clenched teeth, nervous
        _mouth_open(d, 84, 30, teeth_top=True, teeth_bot=True, shape="rect")
    elif state == "flat":                  # unimpressed straight line
        _line(d, [(cx - 54, y + 4), (cx + 54, y + 4)])
    elif state == "wavy":
        pts = [(cx - 70 + i * 140 / 24, y + 10 * math.sin(i / 24 * math.pi * 3)) for i in range(25)]
        _line(d, pts)
    return _finish(im, FEATURE_SCALE)


def draw_extras(traits):
    """back: drawn behind eyes/mouth (hair, beard, freckles, ears); front: over them (mustache)."""
    back, db = _canvas()
    front, df = _canvas()
    hair = tuple(traits.get("hair", [60, 40, 30])) + (255,)
    if traits.get("hair_style", "fringe") == "fringe":
        # hair band hugging the top of the head (the hat sits on it); lower edge is a row of
        # rounded locks (scallops) with an ink line, a few big ones for straight hair, many
        # small ones for curls; a side part tips the locks one way.
        curly = traits.get("curly", False)
        locks = 11 if curly else 6
        depth = 34 if curly else 52
        a0, a1 = 196, 344
        outer = _arc_pts(512, 512, 500, 500, a0, a1, 48)
        edge = []
        n = locks * 12
        for i in range(n + 1):
            t = i / n
            a = math.radians(a1 - (a1 - a0) * t)
            ph = (t * locks) % 1.0
            if not curly:
                ph = ph ** 0.75  # lean the locks towards the part
            r = 458 - depth * math.sin(math.pi * ph)
            edge.append((512 + r * math.cos(a), 512 + r * math.sin(a) + 34))
        db.polygon([(_k(x), _k(y)) for x, y in outer + edge], fill=hair)
        _line(db, edge, fill=INK, w=9)
        # side locks down past the ears so the hat never floats on a bald rim
        for side in (-1, 1):
            cx = 512 + side * 438
            db.ellipse([_k(cx - 40), _k(330), _k(cx + 40), _k(460)], fill=hair)
    sb = traits.get("sideburns")
    if sb:
        for side in (-1, 1):
            x = 512 + side * 330
            db.polygon([(_k(x - 34), _k(300)), (_k(x + 34), _k(300)), (_k(x + side * 10), _k(470))], fill=hair)
    if traits.get("freckles"):
        for side in (-1, 1):
            for dx, dy in ((-20, 0), (15, -12), (5, 22)):
                cx = 512 + side * (EYE_DX + 30) + dx
                cy = EYE_Y + 110 + dy
                db.ellipse([_k(cx - 9), _k(cy - 9), _k(cx + 9), _k(cy + 9)], fill=(200, 120, 90, 255))
    if traits.get("cheeks"):
        for side in (-1, 1):
            cx = 512 + side * (EYE_DX + 60)
            db.ellipse([_k(cx - 46), _k(EYE_Y + 80), _k(cx + 46), _k(EYE_Y + 130)], fill=(245, 170, 160, 150))
    beard = traits.get("beard")
    if beard:
        bc = tuple(beard) + (255,)
        # chin beard: lower part of the head below a scalloped line under the eyes
        low = _arc_pts(512, 512, 500, 500, 28, 152, 40)
        top = []
        for i in range(17):
            x = 512 + 500 * math.cos(math.radians(152)) + (2 * 500 * math.cos(math.radians(28))) * i / 16
            top.append((x, 752 + (16 if i % 2 else -6)))
        poly = low + top
        db.polygon([(_k(x), _k(y)) for x, y in poly], fill=bc)
        _line(db, top, fill=INK, w=10)
    mus = traits.get("mustache")
    if mus:
        mc = tuple(mus) + (255,)
        y = 676
        for side in (-1, 1):
            pts = [(512, y - 10)] + _arc_pts(512 + side * 70, y, 78, 40, 270 - side * 90 + 90 * (1 - side), 270 + 180 * side + 90 * (1 - side), 20)
            lobe = _arc_pts(512 + side * 66, y + 4, 74, 38, 0, 360, 36)
            df.polygon([(_k(x), _k(yy)) for x, yy in lobe], fill=mc)
            _line(df, lobe, fill=INK, w=10)
        df.ellipse([_k(512 - 30), _k(y - 30), _k(512 + 30), _k(y + 26)], fill=mc)
    nose = traits.get("nose")
    if nose:  # big round cartoon nose over the mustache (Wobbly-style cast)
        nc = tuple(nose) + (255,)
        ny, nr = 615, traits.get("nose_size", 92)
        pts = _arc_pts(512, ny, nr * 0.9, nr, 0, 360, 40)
        df.polygon([(_k(x), _k(yy)) for x, yy in pts], fill=nc)
        _line(df, pts, fill=INK, w=10)
        df.ellipse([_k(512 - nr * 0.45), _k(ny - nr * 0.62), _k(512 - nr * 0.1), _k(ny - nr * 0.28)], fill=(255, 255, 255, 150))
    return _finish(back), _finish(front)


def outfit_image(cfg, out_dir):
    """Front-projected outfit picture for the bean body (x across, y up)."""
    b = cfg["body"]
    W = H = 512
    im = Image.new("RGB", (W, H), tuple(b["color"]))
    d = ImageDraw.Draw(im)
    ink = (38, 24, 28)
    if b.get("style") == "overalls":
        shirt = tuple(b.get("shirt", [236, 226, 204]))
        # shirt everywhere above the bib line and at the sides
        d.rectangle([0, 0, W, int(H * 0.42)], fill=shirt)
        d.rectangle([0, 0, int(W * 0.17), H], fill=shirt)
        d.rectangle([int(W * 0.83), 0, W, H], fill=shirt)
        # bib + straps in denim
        den = tuple(b["color"])
        d.rectangle([int(W * 0.30), int(H * 0.30), int(W * 0.70), int(H * 0.45)], fill=den)
        for x0 in (0.31, 0.62):
            d.rectangle([int(W * x0), 0, int(W * (x0 + 0.07)), int(H * 0.32)], fill=den)
        # buttons + bib pocket
        for x0 in (0.345, 0.655):
            d.ellipse([int(W * x0) - 10, int(H * 0.29) - 10, int(W * x0) + 10, int(H * 0.29) + 10], fill=(200, 180, 120), outline=ink, width=3)
        d.rectangle([int(W * 0.40), int(H * 0.47), int(W * 0.60), int(H * 0.60)], outline=(36, 58, 96), width=5)
        # stitching line at the waist
        d.line([int(W * 0.17), int(H * 0.45), int(W * 0.83), int(H * 0.45)], fill=(36, 58, 96), width=4)
    elif b.get("style") == "sweater":
        st = tuple(b.get("stripe", [150, 84, 40]))
        for k in range(3):
            y = int(H * (0.42 + k * 0.12))
            d.rectangle([0, y, W, y + int(H * 0.045)], fill=st)
        # ribbed hem + collar
        d.rectangle([0, int(H * 0.88), W, H], fill=st)
        d.ellipse([int(W * 0.40), -int(H * 0.04), int(W * 0.60), int(H * 0.06)], fill=st)
    elif b.get("style") in ("frock", "railway", "redcoat"):
        main = tuple(b["color"])
        dark = tuple(max(0, int(c * 0.72)) for c in main)
        gold = tuple(b.get("buttons", [226, 190, 80]))
        if b["style"] == "frock":  # long Victorian coat: wide lapels, white shirt, cravat, watch chain
            shirt = tuple(b.get("shirt", [240, 236, 226]))
            d.rectangle([0, 0, W, H], fill=main)
            d.polygon([(int(W * 0.38), 0), (int(W * 0.62), 0), (int(W * 0.56), int(H * 0.42)), (int(W * 0.44), int(H * 0.42))], fill=shirt)
            d.polygon([(int(W * 0.38), 0), (int(W * 0.44), int(H * 0.42)), (int(W * 0.26), int(H * 0.34)), (int(W * 0.24), 0)], fill=dark, outline=ink)
            d.polygon([(int(W * 0.62), 0), (int(W * 0.56), int(H * 0.42)), (int(W * 0.74), int(H * 0.34)), (int(W * 0.76), 0)], fill=dark, outline=ink)
            cr = tuple(b.get("tie", [150, 30, 40]))
            d.polygon([(int(W * 0.44), int(H * 0.03)), (int(W * 0.56), int(H * 0.03)), (int(W * 0.53), int(H * 0.16)), (int(W * 0.47), int(H * 0.16))], fill=cr, outline=ink)
            d.arc([int(W * 0.30), int(H * 0.45), int(W * 0.50), int(H * 0.62)], 20, 160, fill=gold, width=5)
            d.line([int(W * 0.5), int(H * 0.42), int(W * 0.5), H], fill=ink, width=4)
        elif b["style"] == "railway":  # navy double-breasted uniform, two rows of gold buttons, collar
            d.rectangle([0, 0, W, H], fill=main)
            d.rectangle([int(W * 0.36), 0, int(W * 0.64), int(H * 0.08)], fill=dark)
            for x0 in (0.40, 0.60):
                for k in range(4):
                    cy = int(H * (0.20 + k * 0.15))
                    d.ellipse([int(W * x0) - 11, cy - 11, int(W * x0) + 11, cy + 11], fill=gold, outline=ink, width=2)
            d.rectangle([int(W * 0.18), int(H * 0.56), int(W * 0.32), int(H * 0.60)], fill=gold)
        else:  # redcoat: red tunic, white cross belts, gold buttons, white belt
            d.rectangle([0, 0, W, H], fill=main)
            white = (240, 238, 230)
            d.line([int(W * 0.18), 0, int(W * 0.82), int(H * 0.80)], fill=white, width=34)
            d.line([int(W * 0.82), 0, int(W * 0.18), int(H * 0.80)], fill=white, width=34)
            d.ellipse([int(W * 0.5) - 22, int(H * 0.40) - 22, int(W * 0.5) + 22, int(H * 0.40) + 22], fill=gold, outline=ink, width=3)
            d.rectangle([0, int(H * 0.80), W, int(H * 0.88)], fill=white)
            for k in range(3):
                cy = int(H * (0.12 + k * 0.2))
                d.ellipse([int(W * 0.5) - 9, cy - 9, int(W * 0.5) + 9, cy + 9], fill=gold)
    elif b.get("style") in ("vest", "duster", "suit"):
        shirt = tuple(b.get("shirt", [236, 226, 204]))
        main = tuple(b["color"])
        dark = tuple(max(0, int(c * 0.72)) for c in main)
        if b["style"] == "vest":  # shirt with an open vest, optional star badge and belt
            d.rectangle([0, 0, W, H], fill=shirt)
            d.polygon([(int(W * 0.14), 0), (int(W * 0.46), 0), (int(W * 0.46), int(H * 0.30)), (int(W * 0.40), int(H * 0.78)), (int(W * 0.14), int(H * 0.78))], fill=main, outline=ink)
            d.polygon([(int(W * 0.86), 0), (int(W * 0.54), 0), (int(W * 0.54), int(H * 0.30)), (int(W * 0.60), int(H * 0.78)), (int(W * 0.86), int(H * 0.78))], fill=main, outline=ink)
            for k in range(3):
                d.ellipse([int(W * 0.37) - 7, int(H * (0.42 + k * 0.11)) - 7, int(W * 0.37) + 7, int(H * (0.42 + k * 0.11)) + 7], fill=dark)
            if b.get("star"):
                cx, cy, R = int(W * 0.29), int(H * 0.38), 34
                import math as _m
                pts = [(cx + (R if i % 2 == 0 else R * 0.45) * _m.sin(i * _m.pi / 5), cy - (R if i % 2 == 0 else R * 0.45) * _m.cos(i * _m.pi / 5)) for i in range(10)]
                d.polygon(pts, fill=(236, 196, 70), outline=ink)
            d.rectangle([0, int(H * 0.78), W, int(H * 0.86)], fill=tuple(b.get("belt", [70, 46, 30])))
            d.rectangle([int(W * 0.45), int(H * 0.775), int(W * 0.55), int(H * 0.865)], fill=(210, 180, 90), outline=ink, width=3)
        elif b["style"] == "duster":  # long dark coat, lapels, a sliver of shirt
            d.rectangle([0, 0, W, H], fill=main)
            d.polygon([(int(W * 0.40), 0), (int(W * 0.60), 0), (int(W * 0.53), int(H * 0.40)), (int(W * 0.47), int(H * 0.40))], fill=shirt)
            d.polygon([(int(W * 0.40), 0), (int(W * 0.47), int(H * 0.40)), (int(W * 0.32), int(H * 0.30)), (int(W * 0.30), 0)], fill=dark, outline=ink)
            d.polygon([(int(W * 0.60), 0), (int(W * 0.53), int(H * 0.40)), (int(W * 0.68), int(H * 0.30)), (int(W * 0.70), 0)], fill=dark, outline=ink)
            d.line([int(W * 0.5), int(H * 0.40), int(W * 0.5), H], fill=ink, width=4)
            for k in range(3):
                d.ellipse([int(W * 0.46) - 8, int(H * (0.50 + k * 0.12)) - 8, int(W * 0.46) + 8, int(H * (0.50 + k * 0.12)) + 8], fill=(180, 160, 110), outline=ink, width=2)
        else:  # suit: jacket, white shirt V, tie
            d.rectangle([0, 0, W, H], fill=main)
            d.polygon([(int(W * 0.38), 0), (int(W * 0.62), 0), (int(W * 0.5), int(H * 0.46))], fill=shirt)
            tie = tuple(b.get("tie", [150, 30, 40]))
            d.polygon([(int(W * 0.47), int(H * 0.04)), (int(W * 0.53), int(H * 0.04)), (int(W * 0.55), int(H * 0.38)), (int(W * 0.5), int(H * 0.45)), (int(W * 0.45), int(H * 0.38))], fill=tie, outline=ink)
            d.line([int(W * 0.38), 0, int(W * 0.5), int(H * 0.46), int(W * 0.62), 0], fill=ink, width=4)
    p = Path(out_dir) / "outfit.png"
    im.save(p)
    return p


def build(cast, out):
    out = Path(out)
    for ch in cast["characters"]:
        if ch.get("actor"):  # a realistic 3D actor (Channel 3 dioramas) has no drawn face parts
            continue
        t = ch.get("face", {})
        cd = out / ch["id"]
        cd.mkdir(parents=True, exist_ok=True)
        for e in EYES:
            draw_eyes(e, t).save(cd / f"eyes_{e}.png")
        for m in MOUTHS:
            draw_mouth(m, t).save(cd / f"mouth_{m}.png")
        outfit_image(ch, cd)
        b, f = draw_extras(t)
        b.save(cd / "extra_back.png")
        f.save(cd / "extra_front.png")
    return out


def board(face_dir, out_png, eyes=None, mouths=None):
    """Quick 2D check board: white head discs with each eye state + each mouth."""
    face_dir = Path(face_dir)
    eyes = eyes or EYES
    mouths = mouths or MOUTHS
    cell = 220
    cols = max(len(eyes), 8)
    rows = 1 + math.ceil(len(mouths) / cols)
    im = Image.new("RGB", (cols * cell, rows * cell), (205, 190, 170))
    back = Image.open(face_dir / "extra_back.png")
    front = Image.open(face_dir / "extra_front.png")

    def head(e, m):
        h = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(h).ellipse([8, 8, S - 8, S - 8], fill=(255, 255, 255, 255), outline=INK, width=24)
        for layer in (back, Image.open(face_dir / f"mouth_{m}.png"), Image.open(face_dir / f"eyes_{e}.png"), front):
            h = Image.alpha_composite(h, layer)
        return h.resize((cell - 20, cell - 20), Image.LANCZOS)

    for i, e in enumerate(eyes):
        im.paste(head(e, "X"), (i * cell + 10, 10), head(e, "X"))
    for i, m in enumerate(mouths):
        r, c = divmod(i, cols)
        hh = head("open", m)
        im.paste(hh, (c * cell + 10, (r + 1) * cell + 10), hh)
    im.save(out_png)


if __name__ == "__main__":
    cast = json.loads(Path(sys.argv[1]).read_text())
    o = build(cast, sys.argv[2])
    for ch in cast["characters"]:
        if not ch.get("actor"):  # realistic actors have no drawn face
            board(o / ch["id"], o / f"{ch['id']}_board.jpg")
    print("faces ->", o)
