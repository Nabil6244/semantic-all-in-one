"""Elder Health Theory's card library: 13 animated card types and 150+ health topics, all drawn in code from the sentence's own words (no assets, nothing generated).

    meter     a gauge with coloured zones, the needle moves the way the sentence says       cholesterol, LDL, HDL, oxygen, BMI, A1c, vitamin D, B12, kidney eGFR, bone density, stress, pain, hearing, ...
    tube      a tube that fills to the spoken amount against a limit or a goal line         fever, salt, added sugar, alcohol, caffeine, fibre, protein, calcium, saturated fat
    people    "1 in 3", "half of", "40 percent of older adults" as lit people icons          adults, women, men, older adults
    risk      the risk the sentence names, an arrow and before/after bars                   stroke, dementia, heart attack, cancer, diabetes, falls, fracture, early death, ...
    pills     a weekly pill box filling day by day, the pill's own shape and colour          medicine, vitamin D, B12, calcium, omega-3, magnesium, aspirin, statins, ...
    foods     every food the sentence names as a tile with a tick (eat more) or cross       33 foods: greens, berries, oats, beans, nuts, fish, ... processed meat, soda, fried food
    walk      a step ring counting up and footprints walking                                steps, minutes of walking, minutes of exercise, stairs
    breath    a breathing circle: in / hold / out with the spoken counts                    deep breathing, box breathing, relaxing
    clock     a clock sweeping the spoken minutes or hours                                  sunlight, nap, after meals, before bed, fasting, mornings
    weekly    the week's days lit N times                                                   strength, swimming, fish meals, yoga / tai chi, friends, walking, dancing, cycling
    inside    a magnifier inside the body, the process the sentence names                   arteries, bones, joints, muscle, brain cells, lungs, gut, blood flow, immune, eye lens, ...
    steady    a figure balancing on one leg, a level that settles                           balance, falls, dizziness on standing
    symptoms  the warning signs the sentence names, one tile each as it is said            chest pain, short breath, dizziness, numbness, slurred speech, ...
    disease   the condition named: what it does inside the body (magnifier), in plain words  arthritis, osteoporosis, diabetes, heart disease, stroke, dementia, Parkinson's, COPD, ... (34)

evidence() returns look -> (support, payload), one payload per card type, in the elder theme only (health.evidence adds it). forced() builds the card for a CSV
row that names a topic id ("cholesterol", "salmon"...). draw() renders a card on the left; the scene's words stay on the right as callouts (scenes.py)."""
from __future__ import annotations
import math, re
from typing import Callable, Dict, List, Optional

from PIL import Image, ImageDraw

ENGINES = ("meter", "tube", "people", "risk", "pills", "foods", "walk", "breath", "clock", "weekly", "inside", "steady", "symptoms", "disease")      # set before health is imported: health.py reads them
NUMBER_ENGINES = ("meter", "tube", "people", "risk", "walk", "clock", "weekly")      # the card shows the number: the callouts do not repeat it

from . import draw as D, theme as T, lexicon as LX
from .health import _card, _label, _big, _fmt, _rel, _heart_pts, GOOD, MID, BAD, DOWN_RX, UP_RX
INK, SKIN, CREAM, TEAL = (28, 44, 70), (246, 206, 176), (246, 238, 220), (22, 150, 150)

def _c(rgb, a=1.0): return tuple(int(v) for v in rgb[:3]) + (int(255 * max(0.0, min(1.0, a))),)
def _cl(x, lo=0.0, hi=1.0): return max(lo, min(hi, x))

# ---------------------------------------------------------------- icons: (d, x, y, s = half size, a = alpha)

ICONS: Dict[str, Callable] = {}
def _icon(name):
    def deco(f): ICONS[name] = f; return f
    return deco

def icon(d, name, x, y, s, a=1.0):
    if s > 1 and a > 0: ICONS.get(name, ICONS["plate"])(d, x, y, s, a)

def _w(s, k=0.09): return max(1, int(s * k))

@_icon("heart")
def _(d, x, y, s, a): d.polygon(_heart_pts(x, y + s * 0.12, s * 0.9), fill=_c((236, 92, 96), a))
@_icon("brain")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.95, y - s * 0.72, x + s * 0.95, y + s * 0.62), fill=_c((244, 172, 182), a)); col = _c((204, 112, 132), a)
    d.line((x, y - s * 0.68, x, y + s * 0.55), fill=col, width=_w(s))
    for k in (-1, 1):
        d.arc((x + k * s * 0.5 - s * 0.32, y - s * 0.5, x + k * s * 0.5 + s * 0.32, y), 0, 180, fill=col, width=_w(s, 0.07)); d.arc((x + k * s * 0.45 - s * 0.3, y - s * 0.05, x + k * s * 0.45 + s * 0.3, y + s * 0.45), 180, 360, fill=col, width=_w(s, 0.07))
@_icon("bone")
def _(d, x, y, s, a):
    f, o = _c(CREAM, a), _c((190, 172, 140), a); d.rounded_rectangle((x - s * 0.62, y - s * 0.17, x + s * 0.62, y + s * 0.17), radius=_w(s, 0.1), fill=f)
    for sx in (-1, 1):
        for sy in (-1, 1): d.ellipse((x + sx * s * 0.66 - s * 0.24, y + sy * s * 0.19 - s * 0.24, x + sx * s * 0.66 + s * 0.24, y + sy * s * 0.19 + s * 0.24), fill=f, outline=o, width=_w(s, 0.05))
    d.rounded_rectangle((x - s * 0.62, y - s * 0.17, x + s * 0.62, y + s * 0.17), radius=_w(s, 0.1), fill=f)
def _drop(d, x, y, s, a, col):
    d.ellipse((x - s * 0.58, y - s * 0.15, x + s * 0.58, y + s * 0.95), fill=_c(col, a)); d.polygon([(x - s * 0.5, y + s * 0.15), (x + s * 0.5, y + s * 0.15), (x, y - s * 0.95)], fill=_c(col, a))
@_icon("drop")
def _(d, x, y, s, a): _drop(d, x, y, s, a, (96, 168, 232))
@_icon("blood")
def _(d, x, y, s, a): _drop(d, x, y, s, a, (220, 70, 80))
@_icon("kidney")
def _(d, x, y, s, a):
    for k in (-1, 1): d.ellipse((x + k * s * 0.45 - s * 0.36, y - s * 0.62, x + k * s * 0.45 + s * 0.36, y + s * 0.62), fill=_c((184, 84, 96), a)); d.ellipse((x + k * s * 0.22 - s * 0.12, y - s * 0.14, x + k * s * 0.22 + s * 0.12, y + s * 0.14), fill=_c((255, 255, 255), a))
@_icon("lungs")
def _(d, x, y, s, a):
    for k in (-1, 1): d.ellipse((x + k * s * 0.46 - s * 0.38, y - s * 0.5, x + k * s * 0.46 + s * 0.38, y + s * 0.9), fill=_c((238, 140, 152), a))
    col = _c((176, 80, 96), a); d.line((x, y - s * 0.95, x, y - s * 0.15), fill=col, width=_w(s, 0.12)); d.line((x - s * 0.35, y + s * 0.15, x, y - s * 0.2, x + s * 0.35, y + s * 0.15), fill=col, width=_w(s, 0.09))
@_icon("eye")
def _(d, x, y, s, a):
    d.ellipse((x - s, y - s * 0.52, x + s, y + s * 0.52), fill=_c((255, 255, 255), a), outline=_c(INK, a), width=_w(s, 0.07))
    d.ellipse((x - s * 0.42, y - s * 0.42, x + s * 0.42, y + s * 0.42), fill=_c((70, 150, 160), a)); d.ellipse((x - s * 0.18, y - s * 0.18, x + s * 0.18, y + s * 0.18), fill=_c(INK, a))
@_icon("ear")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.55, y - s * 0.9, x + s * 0.55, y + s * 0.9), fill=_c(SKIN, a)); d.arc((x - s * 0.32, y - s * 0.6, x + s * 0.32, y + s * 0.3), 180, 450, fill=_c((200, 140, 110), a), width=_w(s, 0.1))
@_icon("tooth")
def _(d, x, y, s, a):
    f, o = _c((255, 255, 255), a), _c((150, 166, 180), a); d.polygon([(x - s * 0.55, y), (x - s * 0.42, y + s * 0.9), (x - s * 0.1, y + s * 0.9), (x, y + s * 0.4), (x + s * 0.1, y + s * 0.9), (x + s * 0.42, y + s * 0.9), (x + s * 0.55, y)], fill=f, outline=o)
    d.rounded_rectangle((x - s * 0.65, y - s * 0.85, x + s * 0.65, y + s * 0.2), radius=_w(s, 0.3), fill=f, outline=o, width=_w(s, 0.05))
@_icon("germ")
def _(d, x, y, s, a):
    col = _c((110, 180, 90), a)
    for k in range(8):
        an = k * math.pi / 4; ex, ey = x + s * 0.88 * math.cos(an), y + s * 0.88 * math.sin(an); d.line((x, y, ex, ey), fill=col, width=_w(s, 0.08)); d.ellipse((ex - s * 0.12, ey - s * 0.12, ex + s * 0.12, ey + s * 0.12), fill=col)
    d.ellipse((x - s * 0.55, y - s * 0.55, x + s * 0.55, y + s * 0.55), fill=col); d.ellipse((x - s * 0.2, y - s * 0.25, x, y - s * 0.05), fill=_c((70, 130, 60), a))
@_icon("ribbon")
def _(d, x, y, s, a):
    col = _c((236, 120, 160), a); w = _w(s, 0.2); d.line((x - s * 0.5, y + s * 0.9, x + s * 0.18, y - s * 0.2), fill=col, width=w); d.line((x + s * 0.5, y + s * 0.9, x - s * 0.18, y - s * 0.2), fill=col, width=w)
    d.ellipse((x - s * 0.36, y - s * 0.92, x + s * 0.36, y - s * 0.02), outline=col, width=w)
def _person(d, x, y, s, a, col, dress=False, cane=False):
    d.ellipse((x - s * 0.27, y - s * 0.92, x + s * 0.27, y - s * 0.38), fill=_c(col, a))
    if dress: d.polygon([(x - s * 0.18, y - s * 0.32), (x + s * 0.18, y - s * 0.32), (x + s * 0.5, y + s * 0.95), (x - s * 0.5, y + s * 0.95)], fill=_c(col, a))
    else: d.rounded_rectangle((x - s * 0.38, y - s * 0.32, x + s * 0.38, y + s * 0.95), radius=_w(s, 0.3), fill=_c(col, a))
    if cane: d.line((x + s * 0.55, y - s * 0.05, x + s * 0.62, y + s * 0.95), fill=_c((150, 110, 70), a), width=_w(s, 0.1)); d.arc((x + s * 0.4, y - s * 0.2, x + s * 0.7, y + s * 0.1), 180, 360, fill=_c((150, 110, 70), a), width=_w(s, 0.1))
@_icon("person")
def _(d, x, y, s, a): _person(d, x, y, s, a, (120, 140, 160))
@_icon("woman")
def _(d, x, y, s, a): _person(d, x, y, s, a, (120, 140, 160), dress=True)
@_icon("elder")
def _(d, x, y, s, a): _person(d, x - s * 0.1, y, s, a, (120, 140, 160), cane=True)
@_icon("fall")
def _(d, x, y, s, a):
    col = _c((226, 98, 82), a); d.ellipse((x + s * 0.3, y - s * 0.75, x + s * 0.8, y - s * 0.25), fill=col); d.line((x + s * 0.4, y - s * 0.3, x - s * 0.3, y + s * 0.4), fill=col, width=_w(s, 0.26))
    d.line((x - s * 0.3, y + s * 0.4, x - s * 0.85, y + s * 0.2), fill=col, width=_w(s, 0.16)); d.line((x - s * 0.3, y + s * 0.4, x - s * 0.5, y + s * 0.95), fill=col, width=_w(s, 0.16))
    for k in range(3): d.arc((x - s * 0.9 + k * s * 0.15, y - s * 0.9, x + s * 0.1 + k * s * 0.15, y + s * 0.1), 200, 250, fill=_c(INK, a * 0.5), width=_w(s, 0.05))
@_icon("cloud")
def _(d, x, y, s, a):
    for cx, cy, r in ((-0.4, 0.1, 0.38), (0.0, -0.15, 0.5), (0.42, 0.1, 0.38)): d.ellipse((x + (cx - r) * s, y + (cy - r) * s, x + (cx + r) * s, y + (cy + r) * s), fill=_c((150, 162, 178), a))
    d.rounded_rectangle((x - s * 0.78, y + s * 0.05, x + s * 0.8, y + s * 0.48), radius=_w(s, 0.2), fill=_c((150, 162, 178), a))
@_icon("hourglass")
def _(d, x, y, s, a):
    o = _c(INK, a); d.polygon([(x - s * 0.55, y - s * 0.85), (x + s * 0.55, y - s * 0.85), (x, y)], outline=o, fill=_c((255, 255, 255), a)); d.polygon([(x - s * 0.55, y + s * 0.85), (x + s * 0.55, y + s * 0.85), (x, y)], outline=o, fill=_c((240, 200, 110), a))
    d.line((x - s * 0.7, y - s * 0.88, x + s * 0.7, y - s * 0.88), fill=o, width=_w(s, 0.1)); d.line((x - s * 0.7, y + s * 0.88, x + s * 0.7, y + s * 0.88), fill=o, width=_w(s, 0.1))
@_icon("sun")
def _(d, x, y, s, a):
    col = _c((250, 196, 70), a)
    for k in range(8): an = k * math.pi / 4; d.line((x + s * 0.6 * math.cos(an), y + s * 0.6 * math.sin(an), x + s * 0.95 * math.cos(an), y + s * 0.95 * math.sin(an)), fill=col, width=_w(s, 0.12))
    d.ellipse((x - s * 0.45, y - s * 0.45, x + s * 0.45, y + s * 0.45), fill=col)
@_icon("moon")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.75, y - s * 0.75, x + s * 0.75, y + s * 0.75), fill=_c((250, 214, 120), a)); d.ellipse((x - s * 0.3, y - s * 0.95, x + s * 0.95, y + s * 0.4), fill=(255, 255, 255, int(255 * a)))
@_icon("clot")
def _(d, x, y, s, a):
    for cx, cy, r in ((-0.3, 0.0, 0.45), (0.25, -0.2, 0.4), (0.2, 0.3, 0.42)): d.ellipse((x + (cx - r) * s, y + (cy - r) * s, x + (cx + r) * s, y + (cy + r) * s), fill=_c((150, 40, 52), a))
@_icon("pill")
def _(d, x, y, s, a): _pill(d, x, y, s, a, "capsule", (236, 120, 110), (255, 255, 255))
@_icon("shield")
def _(d, x, y, s, a):
    d.polygon([(x, y - s * 0.95), (x + s * 0.8, y - s * 0.6), (x + s * 0.65, y + s * 0.4), (x, y + s * 0.95), (x - s * 0.65, y + s * 0.4), (x - s * 0.8, y - s * 0.6)], fill=_c(TEAL, a)); D.plus(d, x, y - s * 0.05, s * 0.42, _c((255, 255, 255), a))
@_icon("spiral")
def _(d, x, y, s, a):
    pts = [(x + s * 0.9 * (k / 60) * math.cos(k * 0.35), y + s * 0.9 * (k / 60) * math.sin(k * 0.35)) for k in range(61)]; d.line(pts, fill=_c((150, 120, 220), a), width=_w(s, 0.1), joint="curve")
@_icon("head")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.6, y - s * 0.8, x + s * 0.6, y + s * 0.6), fill=_c(SKIN, a)); d.rounded_rectangle((x - s * 0.25, y + s * 0.4, x + s * 0.25, y + s * 0.95), radius=_w(s, 0.1), fill=_c(SKIN, a))
    d.line((x - s * 0.35, y - s * 0.95, x - s * 0.15, y - s * 0.75, x - s * 0.3, y - s * 0.6, x - s * 0.05, y - s * 0.45), fill=_c((226, 98, 82), a), width=_w(s, 0.09))
@_icon("hand")
def _(d, x, y, s, a):
    f = _c(SKIN, a); d.rounded_rectangle((x - s * 0.45, y - s * 0.1, x + s * 0.45, y + s * 0.9), radius=_w(s, 0.25), fill=f)
    for k in range(4): d.rounded_rectangle((x - s * 0.45 + k * s * 0.24, y - s * (0.9 - 0.1 * abs(k - 1.5)), x - s * 0.27 + k * s * 0.24, y + s * 0.1), radius=_w(s, 0.08), fill=f)
    d.rounded_rectangle((x + s * 0.4, y + s * 0.1, x + s * 0.85, y + s * 0.32), radius=_w(s, 0.1), fill=f)
    for k in range(5): d.ellipse((x - s * 0.3 + k * s * 0.15 - s * 0.04, y + s * 0.5 - s * 0.04, x - s * 0.3 + k * s * 0.15 + s * 0.04, y + s * 0.5 + s * 0.04), fill=_c((150, 120, 220), a))
@_icon("question")
def _(d, x, y, s, a):
    col = _c((150, 120, 220), a); w = _w(s, 0.16); d.arc((x - s * 0.45, y - s * 0.9, x + s * 0.45, y), 180, 360, fill=col, width=w); d.arc((x - s * 0.45, y - s * 0.9, x + s * 0.45, y), 0, 80, fill=col, width=w)
    d.line((x + s * 0.05, y - s * 0.02, x, y + s * 0.38), fill=col, width=w); d.ellipse((x - s * 0.12, y + s * 0.62, x + s * 0.12, y + s * 0.86), fill=col)
@_icon("foot")
def _(d, x, y, s, a):
    f = _c(SKIN, a); d.ellipse((x - s * 0.4, y - s * 0.5, x + s * 0.4, y + s * 0.95), fill=f)
    for k in range(5): r = s * (0.16 - 0.02 * k); cx_ = x - s * 0.3 + k * s * 0.16; d.ellipse((cx_ - r, y - s * 0.85 + abs(k - 1) * s * 0.06 - r, cx_ + r, y - s * 0.85 + abs(k - 1) * s * 0.06 + r), fill=f)
@_icon("battery")
def _(d, x, y, s, a):
    d.rounded_rectangle((x - s * 0.85, y - s * 0.45, x + s * 0.7, y + s * 0.45), radius=_w(s, 0.12), outline=_c(INK, a), width=_w(s, 0.1)); d.rectangle((x + s * 0.72, y - s * 0.18, x + s * 0.9, y + s * 0.18), fill=_c(INK, a))
    d.rectangle((x - s * 0.72, y - s * 0.32, x - s * 0.42, y + s * 0.32), fill=_c(BAD, a))
@_icon("stomach")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.75, y - s * 0.45, x + s * 0.55, y + s * 0.8), fill=_c((240, 160, 150), a)); d.line((x + s * 0.2, y - s * 0.3, x + s * 0.35, y - s * 0.95), fill=_c((240, 160, 150), a), width=_w(s, 0.22))
    d.line([(x - s * 0.45 + k * s * 0.1, y + s * 0.2 + s * 0.1 * math.sin(k * 1.4)) for k in range(9)], fill=_c((200, 100, 100), a), width=_w(s, 0.06))
@_icon("drops")
def _(d, x, y, s, a):
    for dx, dy in ((-0.45, -0.3), (0.35, -0.5), (0.0, 0.35)): _drop(d, x + dx * s, y + dy * s, s * 0.42, a, (96, 168, 232))
@_icon("bubble")
def _(d, x, y, s, a):
    d.rounded_rectangle((x - s * 0.9, y - s * 0.7, x + s * 0.9, y + s * 0.45), radius=_w(s, 0.3), fill=_c((255, 255, 255), a), outline=_c(INK, a), width=_w(s, 0.07)); d.polygon([(x - s * 0.4, y + s * 0.42), (x - s * 0.1, y + s * 0.42), (x - s * 0.55, y + s * 0.9)], fill=_c(INK, a))
    d.line([(x - s * 0.6 + k * s * 0.1, y - s * 0.12 + s * 0.12 * math.sin(k * 1.6)) for k in range(13)], fill=_c(BAD, a), width=_w(s, 0.08))
@_icon("face")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.85, y - s * 0.85, x + s * 0.85, y + s * 0.85), fill=_c(SKIN, a)); ink = _c(INK, a)
    d.ellipse((x - s * 0.42, y - s * 0.3, x - s * 0.22, y - s * 0.1), fill=ink); d.line((x + s * 0.22, y - s * 0.12, x + s * 0.44, y - s * 0.05), fill=ink, width=_w(s, 0.08))
    d.line((x - s * 0.4, y + s * 0.35, x, y + s * 0.38, x + s * 0.4, y + s * 0.55), fill=ink, width=_w(s, 0.08))
@_icon("arm")
def _(d, x, y, s, a):
    f = _c(SKIN, a); d.line((x - s * 0.7, y - s * 0.6, x - s * 0.1, y - s * 0.1, x + s * 0.2, y + s * 0.6), fill=f, width=_w(s, 0.3), joint="curve"); d.ellipse((x + s * 0.05, y + s * 0.5, x + s * 0.45, y + s * 0.9), fill=f)
    d.polygon([(x + s * 0.6, y - s * 0.2), (x + s * 0.8, y - s * 0.2), (x + s * 0.7, y + s * 0.1)], fill=_c(BAD, a))
@_icon("shoe")
def _(d, x, y, s, a):
    d.polygon([(x - s * 0.9, y + s * 0.4), (x - s * 0.8, y - s * 0.5), (x - s * 0.2, y - s * 0.5), (x - s * 0.05, y - s * 0.05), (x + s * 0.8, y + s * 0.05), (x + s * 0.92, y + s * 0.4)], fill=_c(TEAL, a))
    d.rectangle((x - s * 0.92, y + s * 0.4, x + s * 0.94, y + s * 0.58), fill=_c(INK, a))
@_icon("plate")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.9, y - s * 0.9, x + s * 0.9, y + s * 0.9), fill=_c((255, 255, 255), a), outline=_c((170, 184, 196), a), width=_w(s, 0.05)); d.ellipse((x - s * 0.6, y - s * 0.6, x + s * 0.6, y + s * 0.6), outline=_c((200, 210, 220), a), width=_w(s, 0.04))
@_icon("weights")
def _(d, x, y, s, a):
    ink = _c(INK, a); d.rectangle((x - s * 0.7, y - s * 0.07, x + s * 0.7, y + s * 0.07), fill=ink)
    for k in (-1, 1): d.rounded_rectangle((x + k * s * 0.62 - s * 0.14, y - s * 0.55, x + k * s * 0.62 + s * 0.14, y + s * 0.55), radius=_w(s, 0.05), fill=_c(TEAL, a)); d.rounded_rectangle((x + k * s * 0.85 - s * 0.1, y - s * 0.35, x + k * s * 0.85 + s * 0.1, y + s * 0.35), radius=_w(s, 0.05), fill=_c(TEAL, a))
@_icon("wave")
def _(d, x, y, s, a):
    for k in range(2): d.line([(x - s * 0.9 + j * s * 0.1, y - s * 0.2 + k * s * 0.45 + s * 0.15 * math.sin(j * 0.9)) for j in range(19)], fill=_c((96, 168, 232), a), width=_w(s, 0.12))
    d.ellipse((x - s * 0.2, y - s * 0.85, x + s * 0.2, y - s * 0.45), fill=_c(SKIN, a))
@_icon("lotus")
def _(d, x, y, s, a):
    for an in (-50, -25, 0, 25, 50):
        r = math.radians(an - 90); px, py = x + s * 0.45 * math.cos(r), y + s * 0.2 + s * 0.45 * math.sin(r); d.ellipse((px - s * 0.2, py - s * 0.38, px + s * 0.2, py + s * 0.38), fill=_c((150, 120, 220), a))
    d.chord((x - s * 0.8, y - s * 0.1, x + s * 0.8, y + s * 0.8), 0, 180, fill=_c((92, 158, 104), a))
@_icon("friends")
def _(d, x, y, s, a): _person(d, x - s * 0.38, y, s * 0.7, a, (120, 140, 160)); _person(d, x + s * 0.38, y, s * 0.7, a, (22, 150, 150), dress=True)
@_icon("dance")
def _(d, x, y, s, a):
    col = _c((150, 120, 220), a); d.ellipse((x - s * 0.2, y - s * 0.95, x + s * 0.2, y - s * 0.55), fill=col); d.line((x, y - s * 0.5, x, y + s * 0.2), fill=col, width=_w(s, 0.18))
    d.line((x - s * 0.7, y - s * 0.75, x, y - s * 0.35, x + s * 0.6, y - s * 0.1), fill=col, width=_w(s, 0.12)); d.line((x - s * 0.4, y + s * 0.9, x, y + s * 0.2, x + s * 0.55, y + s * 0.7), fill=col, width=_w(s, 0.14))
@_icon("bike")
def _(d, x, y, s, a):
    ink = _c(INK, a)
    for k in (-1, 1): d.ellipse((x + k * s * 0.5 - s * 0.38, y + s * 0.1, x + k * s * 0.5 + s * 0.38, y + s * 0.86), outline=ink, width=_w(s, 0.08))
    d.line((x - s * 0.5, y + s * 0.48, x - s * 0.05, y - s * 0.1, x + s * 0.5, y + s * 0.48), fill=_c(TEAL, a), width=_w(s, 0.1)); d.line((x - s * 0.05, y - s * 0.1, x + s * 0.3, y - s * 0.3), fill=_c(TEAL, a), width=_w(s, 0.1))
@_icon("stairs")
def _(d, x, y, s, a):
    pts = [(x - s * 0.9, y + s * 0.8)]
    for k in range(4): pts += [(x - s * 0.9 + k * s * 0.45, y + s * 0.8 - (k + 1) * s * 0.4), (x - s * 0.45 + k * s * 0.45, y + s * 0.8 - (k + 1) * s * 0.4)]
    d.line(pts, fill=_c(TEAL, a), width=_w(s, 0.12))
@_icon("zzz")
def _(d, x, y, s, a):
    ink = _c((150, 140, 240), a)
    for k, (dx, dy, r) in enumerate(((-0.4, 0.35, 0.35), (0.15, -0.1, 0.28), (0.55, -0.5, 0.2))): cx, cy = x + dx * s, y + dy * s; r *= s; d.line((cx - r, cy - r, cx + r, cy - r, cx - r, cy + r, cx + r, cy + r), fill=ink, width=_w(s, 0.08))
@_icon("bed")
def _(d, x, y, s, a):
    d.rounded_rectangle((x - s * 0.9, y, x + s * 0.9, y + s * 0.35), radius=_w(s, 0.08), fill=_c((150, 140, 240), a)); d.rectangle((x - s * 0.9, y - s * 0.5, x - s * 0.78, y + s * 0.7), fill=_c(INK, a))
    d.rectangle((x + s * 0.78, y - s * 0.1, x + s * 0.9, y + s * 0.7), fill=_c(INK, a)); d.ellipse((x - s * 0.72, y - s * 0.3, x - s * 0.3, y + s * 0.02), fill=_c((255, 255, 255), a), outline=_c((190, 200, 210), a))
@_icon("thermo")
def _(d, x, y, s, a):
    d.rounded_rectangle((x - s * 0.18, y - s * 0.95, x + s * 0.18, y + s * 0.4), radius=_w(s, 0.18), fill=_c((255, 255, 255), a), outline=_c(INK, a), width=_w(s, 0.06))
    d.ellipse((x - s * 0.36, y + s * 0.25, x + s * 0.36, y + s * 0.95), fill=_c(BAD, a)); d.rectangle((x - s * 0.07, y - s * 0.4, x + s * 0.07, y + s * 0.4), fill=_c(BAD, a))
@_icon("scale")
def _(d, x, y, s, a):
    d.rounded_rectangle((x - s * 0.85, y - s * 0.6, x + s * 0.85, y + s * 0.8), radius=_w(s, 0.2), fill=_c((226, 234, 238), a), outline=_c(INK, a), width=_w(s, 0.05))
    d.rounded_rectangle((x - s * 0.5, y - s * 0.45, x + s * 0.5, y - s * 0.05), radius=_w(s, 0.08), fill=_c((206, 236, 222), a)); d.line((x, y - s * 0.4, x + s * 0.2, y - s * 0.15), fill=_c(INK, a), width=_w(s, 0.06))
@_icon("tape")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.6, y - s * 0.6, x + s * 0.6, y + s * 0.6), fill=_c((250, 214, 110), a)); d.ellipse((x - s * 0.2, y - s * 0.2, x + s * 0.2, y + s * 0.2), fill=_c((255, 255, 255), a))
    d.rectangle((x, y + s * 0.4, x + s * 0.95, y + s * 0.62), fill=_c((250, 214, 110), a))
@_icon("cell")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.9, y - s * 0.9, x + s * 0.9, y + s * 0.9), fill=_c((240, 200, 210), a), outline=_c((200, 120, 140), a), width=_w(s, 0.08)); d.ellipse((x - s * 0.3, y - s * 0.3, x + s * 0.3, y + s * 0.3), fill=_c((170, 110, 170), a))
@_icon("salt")
def _(d, x, y, s, a):
    d.rounded_rectangle((x - s * 0.45, y - s * 0.45, x + s * 0.45, y + s * 0.9), radius=_w(s, 0.2), fill=_c((255, 255, 255), a), outline=_c((150, 166, 180), a), width=_w(s, 0.06)); d.chord((x - s * 0.45, y - s * 0.95, x + s * 0.45, y - s * 0.1), 180, 360, fill=_c((170, 184, 196), a))
    for k in range(3): d.ellipse((x - s * 0.2 + k * s * 0.2 - s * 0.04, y - s * 0.7, x - s * 0.2 + k * s * 0.2 + s * 0.04, y - s * 0.62), fill=_c(INK, a))
@_icon("sugarcube")
def _(d, x, y, s, a):
    for dx, dy in ((-0.4, 0.3), (0.35, 0.3), (0.0, -0.35)): d.rounded_rectangle((x + (dx - 0.32) * s, y + (dy - 0.32) * s, x + (dx + 0.32) * s, y + (dy + 0.32) * s), radius=_w(s, 0.06), fill=_c((255, 255, 255), a), outline=_c((170, 184, 196), a), width=_w(s, 0.05))
@_icon("wine")
def _(d, x, y, s, a):
    o = _c(INK, a); d.chord((x - s * 0.5, y - s * 0.95, x + s * 0.5, y + s * 0.05), 0, 180, fill=_c((150, 40, 70), a)); d.arc((x - s * 0.5, y - s * 0.95, x + s * 0.5, y + s * 0.05), 0, 180, fill=o, width=_w(s, 0.05))
    d.line((x - s * 0.5, y - s * 0.45, x - s * 0.5, y - s * 0.95), fill=o, width=_w(s, 0.05)); d.line((x + s * 0.5, y - s * 0.45, x + s * 0.5, y - s * 0.95), fill=o, width=_w(s, 0.05))
    d.line((x, y + s * 0.05, x, y + s * 0.8), fill=o, width=_w(s, 0.07)); d.line((x - s * 0.35, y + s * 0.85, x + s * 0.35, y + s * 0.85), fill=o, width=_w(s, 0.08))
@_icon("cup")
def _(d, x, y, s, a): _cup(d, x, y, s, a, (120, 76, 50))
def _cup(d, x, y, s, a, col):
    d.rounded_rectangle((x - s * 0.6, y - s * 0.4, x + s * 0.4, y + s * 0.7), radius=_w(s, 0.18), fill=_c((255, 255, 255), a), outline=_c((150, 166, 180), a), width=_w(s, 0.06))
    d.ellipse((x - s * 0.52, y - s * 0.46, x + s * 0.32, y - s * 0.26), fill=_c(col, a)); d.arc((x + s * 0.2, y - s * 0.2, x + s * 0.75, y + s * 0.4), 270, 90, fill=_c((150, 166, 180), a), width=_w(s, 0.1))
    for k in range(2): d.line([(x - s * 0.3 + k * s * 0.3 + s * 0.06 * math.sin(j * 1.5), y - s * 0.6 - j * s * 0.08) for j in range(5)], fill=_c((180, 190, 200), a), width=_w(s, 0.05))
@_icon("protein")
def _(d, x, y, s, a): ICONS["chicken"](d, x, y, s, a)
@_icon("fiber")
def _(d, x, y, s, a):
    for k in range(3): r = math.radians(-60 + k * 30 - 90); d.line((x, y + s * 0.85, x + s * 0.85 * math.cos(r), y + s * 0.85 + s * 1.6 * math.sin(r) * 0.9), fill=_c((200, 160, 80), a), width=_w(s, 0.08))
    for k in range(3):
        r = math.radians(-60 + k * 30 - 90); ex, ey = x + s * 0.85 * math.cos(r), y + s * 0.85 + s * 1.6 * math.sin(r) * 0.9
        for j in range(3): d.ellipse((ex - s * 0.1 - (j * s * 0.06) * math.cos(r), ey - s * 0.14 - j * s * 0.16 * math.sin(r) * -1, ex + s * 0.1 - (j * s * 0.06) * math.cos(r), ey + s * 0.14 - j * s * 0.16 * math.sin(r) * -1), fill=_c((220, 184, 100), a))
@_icon("milkcarton")
def _(d, x, y, s, a): ICONS["dairy"](d, x, y, s, a)

# foods
def _leaf(d, cx, cy, rx, ry, a, col=(70, 156, 84)):
    d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=_c(col, a)); d.line((cx, cy - ry * 0.8, cx, cy + ry * 0.8), fill=_c((200, 236, 200), a), width=max(1, int(rx * 0.12)))
@_icon("leafy")
def _(d, x, y, s, a):
    for dx, dy in ((-0.4, 0.1), (0.4, 0.1), (0.0, -0.15)): _leaf(d, x + dx * s, y + dy * s, s * 0.32, s * 0.68, a)
@_icon("broccoli")
def _(d, x, y, s, a):
    d.polygon([(x - s * 0.18, y), (x + s * 0.18, y), (x + s * 0.25, y + s * 0.9), (x - s * 0.25, y + s * 0.9)], fill=_c((150, 200, 110), a))
    for dx, dy, r in ((-0.45, -0.1, 0.36), (0.45, -0.1, 0.36), (0.0, -0.45, 0.42), (-0.15, 0.05, 0.3), (0.2, 0.05, 0.3)): d.ellipse((x + (dx - r) * s, y + (dy - r) * s, x + (dx + r) * s, y + (dy + r) * s), fill=_c((56, 132, 70), a))
@_icon("berries")
def _(d, x, y, s, a):
    for dx, dy in ((-0.45, 0.3), (0.0, 0.35), (0.45, 0.3), (-0.22, -0.1), (0.22, -0.1), (0.0, -0.5)):
        cx, cy, r = x + dx * s, y + dy * s, s * 0.27; d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_c((84, 80, 170), a)); d.ellipse((cx - r * 0.35, cy - r * 0.55, cx + r * 0.05, cy - r * 0.2), fill=_c((170, 170, 230), a))
@_icon("apple")
def _(d, x, y, s, a):
    for k in (-1, 1): d.ellipse((x + k * s * 0.22 - s * 0.55, y - s * 0.5, x + k * s * 0.22 + s * 0.55, y + s * 0.85), fill=_c((214, 64, 64), a))
    d.line((x, y - s * 0.45, x + s * 0.08, y - s * 0.9), fill=_c((110, 80, 50), a), width=_w(s, 0.08)); _leaf(d, x + s * 0.3, y - s * 0.75, s * 0.15, s * 0.25, a)
@_icon("banana")
def _(d, x, y, s, a): d.arc((x - s * 0.9, y - s * 1.3, x + s * 0.9, y + s * 0.6), 30, 150, fill=_c((246, 210, 70), a), width=_w(s, 0.34))
@_icon("citrus")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.8, y - s * 0.8, x + s * 0.8, y + s * 0.8), fill=_c((250, 160, 50), a)); d.ellipse((x - s * 0.62, y - s * 0.62, x + s * 0.62, y + s * 0.62), fill=_c((255, 196, 100), a))
    for k in range(6): r = k * math.pi / 3; d.line((x, y, x + s * 0.6 * math.cos(r), y + s * 0.6 * math.sin(r)), fill=_c((255, 236, 200), a), width=_w(s, 0.05))
@_icon("bowl")
def _(d, x, y, s, a):
    d.chord((x - s * 0.9, y - s * 0.55, x + s * 0.9, y + s * 0.9), 0, 180, fill=_c((150, 196, 210), a))
    for k in range(9): d.ellipse((x - s * 0.7 + k * s * 0.17 - s * 0.08, y + s * 0.1 - s * 0.1 * math.sin(k) - s * 0.08, x - s * 0.7 + k * s * 0.17 + s * 0.08, y + s * 0.1 - s * 0.1 * math.sin(k) + s * 0.08), fill=_c((220, 196, 150), a))
@_icon("bread")
def _(d, x, y, s, a): _loaf(d, x, y, s, a, (186, 132, 80))
@_icon("whitebread")
def _(d, x, y, s, a): _loaf(d, x, y, s, a, (236, 214, 170))
def _loaf(d, x, y, s, a, col):
    d.rounded_rectangle((x - s * 0.85, y - s * 0.3, x + s * 0.85, y + s * 0.7), radius=_w(s, 0.2), fill=_c(col, a)); d.ellipse((x - s * 0.85, y - s * 0.7, x + s * 0.85, y + s * 0.2), fill=_c(col, a))
    for k in range(3): d.line((x - s * 0.4 + k * s * 0.35, y - s * 0.5, x - s * 0.25 + k * s * 0.35, y - s * 0.2), fill=_c((255, 236, 200), a), width=_w(s, 0.06))
@_icon("beans")
def _(d, x, y, s, a):
    for dx, dy, col in ((-0.4, 0.2, (150, 60, 50)), (0.1, 0.35, (170, 80, 60)), (0.45, 0.0, (150, 60, 50)), (-0.1, -0.25, (190, 110, 70)), (-0.5, -0.35, (170, 80, 60))):
        d.ellipse((x + (dx - 0.3) * s, y + (dy - 0.2) * s, x + (dx + 0.3) * s, y + (dy + 0.2) * s), fill=_c(col, a))
@_icon("nuts")
def _(d, x, y, s, a):
    for dx, dy in ((-0.45, 0.2), (0.0, -0.2), (0.45, 0.25)):
        cx, cy = x + dx * s, y + dy * s; d.ellipse((cx - s * 0.25, cy - s * 0.4, cx + s * 0.25, cy + s * 0.4), fill=_c((190, 138, 86), a)); d.line((cx, cy - s * 0.3, cx, cy + s * 0.3), fill=_c((150, 100, 60), a), width=_w(s, 0.04))
@_icon("fish")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.75, y - s * 0.42, x + s * 0.45, y + s * 0.42), fill=_c((240, 140, 110), a)); d.polygon([(x + s * 0.35, y), (x + s * 0.95, y - s * 0.4), (x + s * 0.95, y + s * 0.4)], fill=_c((240, 140, 110), a))
    d.ellipse((x - s * 0.55, y - s * 0.14, x - s * 0.4, y + s * 0.01), fill=_c(INK, a)); d.arc((x - s * 0.3, y - s * 0.3, x + s * 0.05, y + s * 0.3), 300, 60, fill=_c((210, 100, 80), a), width=_w(s, 0.05))
@_icon("egg")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.85, y - s * 0.6, x + s * 0.85, y + s * 0.7), fill=_c((255, 255, 255), a), outline=_c((214, 220, 226), a), width=_w(s, 0.04)); d.ellipse((x - s * 0.32, y - s * 0.3, x + s * 0.32, y + s * 0.32), fill=_c((250, 190, 50), a))
@_icon("yogurt")
def _(d, x, y, s, a):
    d.polygon([(x - s * 0.6, y - s * 0.5), (x + s * 0.6, y - s * 0.5), (x + s * 0.45, y + s * 0.85), (x - s * 0.45, y + s * 0.85)], fill=_c((255, 255, 255), a), outline=_c((170, 184, 196), a))
    d.ellipse((x - s * 0.62, y - s * 0.68, x + s * 0.62, y - s * 0.32), fill=_c((236, 150, 180), a)); d.rectangle((x - s * 0.5, y + s * 0.05, x + s * 0.5, y + s * 0.3), fill=_c((150, 120, 220), a))
@_icon("oil")
def _(d, x, y, s, a):
    d.rectangle((x - s * 0.12, y - s * 0.95, x + s * 0.12, y - s * 0.5), fill=_c((120, 110, 40), a)); d.rounded_rectangle((x - s * 0.42, y - s * 0.55, x + s * 0.42, y + s * 0.9), radius=_w(s, 0.25), fill=_c((190, 184, 70), a))
    _leaf(d, x, y + s * 0.2, s * 0.15, s * 0.3, a, (90, 120, 40))
@_icon("avocado")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.62, y - s * 0.3, x + s * 0.62, y + s * 0.9), fill=_c((70, 120, 50), a)); d.ellipse((x - s * 0.4, y - s * 0.9, x + s * 0.4, y + s * 0.2), fill=_c((70, 120, 50), a))
    d.ellipse((x - s * 0.5, y - s * 0.2, x + s * 0.5, y + s * 0.78), fill=_c((200, 224, 120), a)); d.ellipse((x - s * 0.22, y + s * 0.1, x + s * 0.22, y + s * 0.55), fill=_c((140, 90, 50), a))
@_icon("tomato")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.82, y - s * 0.65, x + s * 0.82, y + s * 0.8), fill=_c((226, 70, 60), a))
    for k in range(5): r = math.radians(k * 72 - 90); d.line((x, y - s * 0.55, x + s * 0.35 * math.cos(r), y - s * 0.55 + s * 0.2 * math.sin(r)), fill=_c((70, 140, 60), a), width=_w(s, 0.1))
@_icon("carrot")
def _(d, x, y, s, a):
    d.polygon([(x - s * 0.3, y - s * 0.5), (x + s * 0.3, y - s * 0.5), (x + s * 0.05, y + s * 0.95), (x - s * 0.05, y + s * 0.95)], fill=_c((246, 140, 50), a))
    for k in (-1, 0, 1): _leaf(d, x + k * s * 0.18, y - s * 0.72, s * 0.1, s * 0.25, a)
@_icon("veg")
def _(d, x, y, s, a): ICONS["broccoli"](d, x - s * 0.3, y, s * 0.65, a); ICONS["carrot"](d, x + s * 0.45, y + s * 0.1, s * 0.6, a)
@_icon("fruit")
def _(d, x, y, s, a): ICONS["apple"](d, x - s * 0.35, y + s * 0.1, s * 0.6, a); ICONS["citrus"](d, x + s * 0.4, y + s * 0.15, s * 0.5, a)
@_icon("sweetpotato")
def _(d, x, y, s, a): d.ellipse((x - s * 0.9, y - s * 0.42, x + s * 0.9, y + s * 0.42), fill=_c((196, 106, 70), a)); d.ellipse((x - s * 0.5, y - s * 0.2, x - s * 0.4, y - s * 0.1), fill=_c((150, 70, 50), a))
@_icon("garlic")
def _(d, x, y, s, a):
    d.ellipse((x - s * 0.72, y - s * 0.45, x + s * 0.72, y + s * 0.85), fill=_c((250, 246, 236), a), outline=_c((200, 190, 170), a), width=_w(s, 0.04)); d.polygon([(x - s * 0.2, y - s * 0.35), (x + s * 0.2, y - s * 0.35), (x, y - s * 0.95)], fill=_c((250, 246, 236), a))
    for k in (-1, 1): d.arc((x + k * s * 0.2 - s * 0.4, y - s * 0.4, x + k * s * 0.2 + s * 0.4, y + s * 0.8), 240 if k < 0 else 300, 120 if k < 0 else 60, fill=_c((210, 200, 180), a), width=_w(s, 0.04))
@_icon("tea")
def _(d, x, y, s, a): _cup(d, x, y, s, a, (150, 176, 80))
@_icon("chicken")
def _(d, x, y, s, a):
    d.line((x + s * 0.1, y + s * 0.1, x + s * 0.75, y + s * 0.75), fill=_c(CREAM, a), width=_w(s, 0.16)); d.ellipse((x + s * 0.6, y + s * 0.55, x + s * 0.95, y + s * 0.9), fill=_c(CREAM, a))
    d.ellipse((x - s * 0.8, y - s * 0.8, x + s * 0.3, y + s * 0.3), fill=_c((200, 130, 70), a))
@_icon("dairy")
def _(d, x, y, s, a):
    d.rectangle((x - s * 0.5, y - s * 0.4, x + s * 0.5, y + s * 0.9), fill=_c((255, 255, 255), a), outline=_c((170, 184, 196), a)); d.polygon([(x - s * 0.5, y - s * 0.4), (x + s * 0.5, y - s * 0.4), (x, y - s * 0.9)], fill=_c((230, 236, 240), a), outline=_c((170, 184, 196), a))
    d.rectangle((x - s * 0.5, y + s * 0.1, x + s * 0.5, y + s * 0.45), fill=_c((96, 168, 232), a))
@_icon("cheese")
def _(d, x, y, s, a):
    d.polygon([(x - s * 0.85, y + s * 0.6), (x + s * 0.85, y + s * 0.6), (x + s * 0.85, y - s * 0.1), (x - s * 0.85, y + s * 0.0)], fill=_c((250, 206, 80), a)); d.polygon([(x - s * 0.85, y), (x + s * 0.85, y - s * 0.1), (x + s * 0.5, y - s * 0.6)], fill=_c((252, 226, 130), a))
    for dx, dy, r in ((-0.4, 0.3, 0.1), (0.2, 0.25, 0.13), (0.55, 0.4, 0.07)): d.ellipse((x + (dx - r) * s, y + (dy - r) * s, x + (dx + r) * s, y + (dy + r) * s), fill=_c((220, 170, 50), a))
@_icon("chocolate")
def _(d, x, y, s, a):
    d.rounded_rectangle((x - s * 0.7, y - s * 0.85, x + s * 0.7, y + s * 0.85), radius=_w(s, 0.08), fill=_c((96, 56, 40), a))
    for k in range(1, 3): d.line((x - s * 0.7 + k * s * 0.47, y - s * 0.85, x - s * 0.7 + k * s * 0.47, y + s * 0.85), fill=_c((130, 80, 56), a), width=_w(s, 0.05))
    for k in range(1, 4): d.line((x - s * 0.7, y - s * 0.85 + k * s * 0.42, x + s * 0.7, y - s * 0.85 + k * s * 0.42), fill=_c((130, 80, 56), a), width=_w(s, 0.05))
@_icon("bacon")
def _(d, x, y, s, a):
    for k, col in enumerate(((210, 90, 90), (250, 220, 200), (200, 80, 80))): d.line([(x - s * 0.9 + j * s * 0.15, y - s * 0.3 + k * s * 0.22 + s * 0.15 * math.sin(j * 1.2)) for j in range(13)], fill=_c(col, a), width=_w(s, 0.18))
@_icon("steak")
def _(d, x, y, s, a): d.ellipse((x - s * 0.85, y - s * 0.6, x + s * 0.85, y + s * 0.7), fill=_c((170, 60, 60), a)); d.arc((x - s * 0.5, y - s * 0.3, x + s * 0.4, y + s * 0.4), 200, 340, fill=_c((250, 230, 220), a), width=_w(s, 0.1))
@_icon("fries")
def _(d, x, y, s, a):
    for k in range(5): d.rectangle((x - s * 0.5 + k * s * 0.22, y - s * (0.9 - 0.12 * (k % 2)), x - s * 0.38 + k * s * 0.22, y + s * 0.1), fill=_c((250, 206, 80), a))
    d.polygon([(x - s * 0.65, y - s * 0.15), (x + s * 0.65, y - s * 0.15), (x + s * 0.5, y + s * 0.9), (x - s * 0.5, y + s * 0.9)], fill=_c((220, 60, 60), a))
@_icon("soda")
def _(d, x, y, s, a):
    d.rounded_rectangle((x - s * 0.45, y - s * 0.8, x + s * 0.45, y + s * 0.9), radius=_w(s, 0.12), fill=_c((214, 50, 56), a)); d.ellipse((x - s * 0.45, y - s * 0.95, x + s * 0.45, y - s * 0.65), fill=_c((200, 206, 212), a))
    d.line([(x - s * 0.45 + j * s * 0.1, y + s * 0.1 * math.sin(j)) for j in range(10)], fill=_c((255, 255, 255), a), width=_w(s, 0.07))
@_icon("chips")
def _(d, x, y, s, a):
    d.polygon([(x - s * 0.7, y - s * 0.8), (x + s * 0.7, y - s * 0.8), (x + s * 0.6, y + s * 0.9), (x - s * 0.6, y + s * 0.9)], fill=_c((250, 196, 60), a)); d.ellipse((x - s * 0.35, y - s * 0.25, x + s * 0.35, y + s * 0.35), fill=_c((214, 60, 60), a))
@_icon("cake")
def _(d, x, y, s, a):
    d.polygon([(x - s * 0.85, y - s * 0.1), (x + s * 0.85, y - s * 0.5), (x + s * 0.85, y + s * 0.7), (x - s * 0.85, y + s * 0.7)], fill=_c((236, 200, 150), a)); d.polygon([(x - s * 0.85, y - s * 0.1), (x + s * 0.85, y - s * 0.5), (x + s * 0.85, y - s * 0.25), (x - s * 0.85, y + s * 0.12)], fill=_c((240, 150, 180), a))
    d.ellipse((x + s * 0.3, y - s * 0.8, x + s * 0.55, y - s * 0.55), fill=_c((214, 50, 56), a))
@_icon("burger")
def _(d, x, y, s, a):
    d.chord((x - s * 0.85, y - s * 0.85, x + s * 0.85, y + s * 0.15), 180, 360, fill=_c((214, 150, 80), a)); d.rectangle((x - s * 0.9, y - s * 0.3, x + s * 0.9, y - s * 0.12), fill=_c((92, 158, 104), a))
    d.rounded_rectangle((x - s * 0.85, y - s * 0.12, x + s * 0.85, y + s * 0.2), radius=_w(s, 0.1), fill=_c((120, 70, 50), a)); d.rounded_rectangle((x - s * 0.85, y + s * 0.25, x + s * 0.85, y + s * 0.6), radius=_w(s, 0.15), fill=_c((214, 150, 80), a))

def _pill(d, x, y, s, a, shape, c1, c2):
    if shape == "round": d.ellipse((x - s * 0.6, y - s * 0.6, x + s * 0.6, y + s * 0.6), fill=_c(c1, a), outline=_c((150, 160, 170), a), width=_w(s, 0.05)); d.line((x - s * 0.42, y, x + s * 0.42, y), fill=_c((190, 196, 204), a), width=_w(s, 0.05))
    elif shape == "softgel": d.ellipse((x - s * 0.8, y - s * 0.45, x + s * 0.8, y + s * 0.45), fill=_c(c1, a)); d.ellipse((x - s * 0.45, y - s * 0.3, x - s * 0.05, y - s * 0.1), fill=_c((255, 255, 255), a * 0.6))
    else:
        r = _w(s, 0.42); d.rounded_rectangle((x - s * 0.9, y - s * 0.4, x + s * 0.02, y + s * 0.4), radius=r, fill=_c(c1, a)); d.rounded_rectangle((x - s * 0.02, y - s * 0.4, x + s * 0.9, y + s * 0.4), radius=r, fill=_c(c2, a))
        d.rectangle((x - s * 0.3, y - s * 0.4, x + s * 0.02, y + s * 0.4), fill=_c(c1, a)); d.rectangle((x - s * 0.02, y - s * 0.4, x + s * 0.3, y + s * 0.4), fill=_c(c2, a))

# ---------------------------------------------------------------- the catalogue: topic id -> its card type, trigger words, look and numbers

TOPICS: Dict[str, dict] = {}
def _t(tid: str, engine: str, rx: str, label: str, icon_: str, **kw) -> None:
    TOPICS[tid] = dict(id=tid, engine=engine, rx=re.compile(rx, re.I), label=label, icon=icon_, **kw)

G3 = lambda a, b, n=("NORMAL", "BORDERLINE", "HIGH"): [(a, GOOD, n[0]), (b, MID, n[1]), (1e9, BAD, n[2])]      # low is good
H3 = lambda a, b, n=("LOW", "BORDERLINE", "GOOD"): [(a, BAD, n[0]), (b, MID, n[1]), (1e9, GOOD, n[2])]      # high is good

# meter: range, zones (upto, colour, name), unit, a healthy and an unhealthy reading, hb = higher is better
_t("ldl", "meter", r"\b(ldl|bad cholesterol)\b", "LDL CHOLESTEROL", "blood", range=(50, 220), zones=G3(100, 160), unit="mg/dL", good=90, bad=180)
_t("hdl", "meter", r"\b(hdl|good cholesterol)\b", "HDL CHOLESTEROL", "blood", range=(20, 100), zones=H3(40, 60), unit="mg/dL", good=65, bad=35, hb=True)
_t("triglycerides", "meter", r"\b(triglycerides?)\b", "TRIGLYCERIDES", "blood", range=(50, 400), zones=G3(150, 200), unit="mg/dL", good=110, bad=260)
_t("cholesterol", "meter", r"\b(cholesterol)\b", "CHOLESTEROL", "blood", range=(120, 300), zones=G3(200, 240), unit="mg/dL", good=180, bad=260)
_t("oxygen", "meter", r"\b(oxygen (?:level|saturation)s?|blood oxygen|spo2|pulse ox\w*|oxygen in your blood)\b", "BLOOD OXYGEN", "lungs", range=(80, 100), zones=H3(90, 95), unit="%", good=97, bad=88, hb=True)
_t("bmi", "meter", r"\b(bmi|body mass index|overweight|obes\w*)\b", "BMI", "scale", range=(15, 40), zones=[(18.5, MID, "UNDER"), (25, GOOD, "HEALTHY"), (30, MID, "OVER"), (1e9, BAD, "HIGH")], unit="kg/m²", good=23, bad=32)
_t("a1c", "meter", r"\b(a1c|hba1c|average blood sugar)\b", "A1C", "drop", range=(4, 11), zones=G3(5.7, 6.5, ("NORMAL", "PRE-DIABETES", "DIABETES")), unit="%", good=5.4, bad=7.5)
_t("vitamin_d", "meter", r"\b(vitamin d)\b", "VITAMIN D", "sun", range=(0, 80), zones=H3(20, 30, ("LOW", "BORDERLINE", "HEALTHY")), unit="ng/mL", good=40, bad=14, hb=True)
_t("b12", "meter", r"\b(vitamin b-?12|b-?12)\b", "VITAMIN B12", "pill", range=(100, 1000), zones=H3(200, 300, ("LOW", "BORDERLINE", "HEALTHY")), unit="pg/mL", good=500, bad=160, hb=True)
_t("egfr", "meter", r"\b(egfr|kidney function|kidneys? (?:filter|work)\w*)\b", "KIDNEY FUNCTION", "kidney", range=(0, 120), zones=H3(60, 90, ("LOW", "MILD", "NORMAL")), unit="eGFR", good=95, bad=45, hb=True)
_t("bone_density", "meter", r"\b(bone density|bone mass|t-score|osteopor\w*|osteopenia|brittle bones?|thinning bones?)\b", "BONE DENSITY", "bone", range=(-4, 2), zones=H3(-2.5, -1, ("OSTEOPOROSIS", "LOW", "NORMAL")), unit="T-SCORE", good=0.2, bad=-2.9, hb=True)
_t("stress", "meter", r"\b(stress\w*|cortisol|anxiety|anxious|worr(?:y|ies|ying))\b", "STRESS LEVEL", "brain", range=(0, 10), zones=G3(4, 7, ("CALM", "TENSE", "HIGH")), unit="OUT OF 10", good=2.5, bad=8.5)
_t("pain", "meter", r"\b(pain|aches?|aching|sore(?:ness)?)\b", "PAIN LEVEL", "hand", range=(0, 10), zones=G3(4, 7, ("MILD", "MODERATE", "SEVERE")), unit="OUT OF 10", good=2, bad=8)
_t("hearing", "meter", r"\b(hearing loss|hard of hearing|hearing)\b", "HEARING LOSS", "ear", range=(0, 90), zones=G3(25, 40, ("NORMAL", "MILD", "MODERATE")), unit="dB", good=15, bad=55)
_t("eye_pressure", "meter", r"\b(eye pressure|glaucoma)\b", "EYE PRESSURE", "eye", range=(5, 40), zones=G3(21, 28), unit="mmHg", good=15, bad=30)
_t("inflammation", "meter", r"\b(inflammation|inflamed|crp|c-reactive)\b", "INFLAMMATION", "cell", range=(0, 10), zones=G3(1, 3, ("LOW", "AVERAGE", "HIGH")), unit="CRP mg/L", good=0.6, bad=6)
_t("waist", "meter", r"\b(waist(?:line)?|belly fat|visceral fat|tummy fat)\b", "WAIST SIZE", "tape", range=(25, 50), zones=G3(35, 40, ("HEALTHY", "WATCH", "HIGH RISK")), unit="INCHES", good=32, bad=43)
_t("grip", "meter", r"\b(grip strength|grip|hand strength)\b", "GRIP STRENGTH", "hand", range=(10, 60), zones=H3(20, 30, ("WEAK", "FAIR", "STRONG")), unit="kg", good=36, bad=16, hb=True)
_t("thyroid", "meter", r"\b(thyroid|tsh)\b", "THYROID (TSH)", "cell", range=(0, 10), zones=[(0.4, MID, "LOW"), (4, GOOD, "NORMAL"), (1e9, BAD, "HIGH")], unit="mIU/L", good=2, bad=7)
_t("uric_acid", "meter", r"\b(uric acid|gout)\b", "URIC ACID", "foot", range=(2, 12), zones=G3(6, 7), unit="mg/dL", good=5, bad=9)
_t("psa", "meter", r"\b(psa)\b", "PSA", "cell", range=(0, 12), zones=G3(4, 10, ("NORMAL", "CHECK", "HIGH")), unit="ng/mL", good=1.5, bad=8)
_t("hemoglobin", "meter", r"\b(an(?:a)?emi\w*|h(?:a)?emoglobin|iron levels?|low iron)\b", "HEMOGLOBIN", "blood", range=(8, 18), zones=H3(12, 13, ("LOW", "BORDERLINE", "NORMAL")), unit="g/dL", good=14.5, bad=10.5, hb=True)
_t("resting_pulse", "meter", r"\b(resting (?:heart rate|pulse))\b", "RESTING PULSE", "heart", range=(40, 120), zones=[(50, MID, "LOW"), (90, GOOD, "NORMAL"), (1e9, BAD, "FAST")], unit="BPM", good=66, bad=100)

# tube: unit words, the scale, a limit (stay under) or a goal (reach), the reading used when the sentence gives none
_t("fever", "tube", r"\b(fever|temperature|feverish)\b", "TEMPERATURE", "thermo", unit="°F", unit_rx=r"degrees?|°", lo=96, max=104, mark=100.4, mode="limit", default=101.5, mark_txt="FEVER", decimals=1)
_t("salt", "tube", r"\b(salt|sodium|salty)\b", "SALT A DAY", "salt", unit="TSP", unit_rx=r"teaspoons?|tsp", max=3, mark=1, mode="limit", default=1.8, mark_txt="LIMIT", decimals=1)
_t("added_sugar", "tube", r"\b(added sugars?|sugary|sweets|sugar intake|too much sugar)\b", "ADDED SUGAR", "sugarcube", unit="TSP", unit_rx=r"teaspoons?|tsp|cubes?", max=15, mark=6, mode="limit", default=11, mark_txt="LIMIT")
_t("alcohol", "tube", r"\b(alcohol|drinking|wine|beer|liquor|spirits)\b", "DRINKS A WEEK", "wine", unit="DRINKS", unit_rx=r"drinks?|glasses|units?", max=21, mark=7, mode="limit", default=12, mark_txt="LIMIT")
_t("caffeine", "tube", r"\b(caffeine|coffee)\b", "COFFEE A DAY", "cup", unit="CUPS", unit_rx=r"cups?|mugs?", max=8, mark=4, mode="limit", default=3, mark_txt="LIMIT")
_t("fiber", "tube", r"\b(fib(?:er|re))\b", "FIBRE A DAY", "fiber", unit="g", unit_rx=r"grams?|g\b", max=40, mark=25, mode="goal", default=25, mark_txt="GOAL")
_t("protein", "tube", r"\b(protein)\b", "PROTEIN A DAY", "chicken", unit="g", unit_rx=r"grams?|g\b", max=120, mark=80, mode="goal", default=80, mark_txt="GOAL")
_t("calcium", "tube", r"\b(calcium)\b", "CALCIUM A DAY", "dairy", unit="mg", unit_rx=r"milligrams?|mg", max=1600, mark=1200, mode="goal", default=1200, mark_txt="GOAL")
_t("sat_fat", "tube", r"\b(saturated fats?|trans fats?|unhealthy fats?)\b", "SATURATED FAT", "burger", unit="g", unit_rx=r"grams?|g\b", max=40, mark=20, mode="limit", default=28, mark_txt="LIMIT")

# people: who the count is about
_t("people_women", "people", r"\b(women|woman|ladies|females?)\b", "WOMEN", "woman")
_t("people_men", "people", r"\b(men|man|males?)\b", "MEN", "person")
_t("people_older", "people", r"\b(older (?:adults|people|men|women|americans)|(?:over|above|past) (?:the age of )?(?:[5-9]\d|fifty|sixty|seventy|eighty|ninety)|seniors?|elderly|retirees|grandparents|people your age|aged? (?:60|65|70)\+?)\b", "OLDER ADULTS", "elder")
_t("people_adults", "people", r"\b(adults|people|patients|americans|of us|everyone|folks)\b", "ADULTS", "person")

# risk: the condition
_t("risk_stroke", "risk", r"\b(strokes?)\b", "STROKE RISK", "brain")
_t("risk_dementia", "risk", r"\b(dementia|alzheimer\w*|memory loss|cognitive decline)\b", "DEMENTIA RISK", "brain")
_t("risk_heart", "risk", r"\b(heart attacks?|heart disease|cardiac|heart failure|cardiovascular)\b", "HEART DISEASE RISK", "heart")
_t("risk_cancer", "risk", r"\b(cancers?|tumou?rs?)\b", "CANCER RISK", "ribbon")
_t("risk_diabetes", "risk", r"\b(diabetes|type 2)\b", "DIABETES RISK", "drop")
_t("risk_falls", "risk", r"\b(falls?|falling)\b", "FALL RISK", "fall")
_t("risk_fracture", "risk", r"\b(fractures?|broken (?:hip|bones?|wrist)|hip fractures?)\b", "FRACTURE RISK", "bone")
_t("risk_death", "risk", r"\b(early death|dying early|mortality|die (?:early|sooner)|live longer|lifespan|death)\b", "EARLY DEATH RISK", "hourglass")
_t("risk_depression", "risk", r"\b(depression|depressed|loneliness|lonely)\b", "DEPRESSION RISK", "cloud")
_t("risk_kidney", "risk", r"\b(kidney disease|kidney failure|kidney stones?)\b", "KIDNEY DISEASE RISK", "kidney")
_t("risk_infection", "risk", r"\b(infections?|pneumonia|flu|shingles|covid)\b", "INFECTION RISK", "germ")
_t("risk_clot", "risk", r"\b(blood clots?|clots?|dvt|deep vein)\b", "BLOOD CLOT RISK", "clot")
_t("risk_vision", "risk", r"\b(macular degeneration|vision loss|blindness|cataracts?)\b", "VISION LOSS RISK", "eye")

# pills: the pill's shape and colours
_t("pill_vitamin_d", "pills", r"\b(vitamin d(?:3)?)\b", "VITAMIN D", "sun", shape="softgel", c1=(250, 200, 70), c2=(250, 200, 70))
_t("pill_b12", "pills", r"\b(vitamin b-?12|b-?12)\b", "VITAMIN B12", "pill", shape="round", c1=(236, 120, 140), c2=(236, 120, 140))
_t("pill_calcium", "pills", r"\b(calcium)\b", "CALCIUM", "bone", shape="capsule", c1=(255, 255, 255), c2=(220, 226, 232))
_t("pill_omega3", "pills", r"\b(omega-?3s?|fish oil|krill oil)\b", "OMEGA-3", "fish", shape="softgel", c1=(240, 170, 60), c2=(240, 170, 60))
_t("pill_magnesium", "pills", r"\b(magnesium)\b", "MAGNESIUM", "pill", shape="capsule", c1=(150, 120, 220), c2=(255, 255, 255))
_t("pill_aspirin", "pills", r"\b(aspirin)\b", "ASPIRIN", "heart", shape="round", c1=(255, 255, 255), c2=(255, 255, 255))
_t("pill_statin", "pills", r"\b(statins?|atorvastatin|simvastatin|rosuvastatin|lipitor|crestor)\b", "STATIN", "blood", shape="round", c1=(236, 150, 120), c2=(236, 150, 120))
_t("pill_thinner", "pills", r"\b(blood thinners?|warfarin|eliquis|apixaban|xarelto)\b", "BLOOD THINNER", "clot", shape="round", c1=(250, 214, 110), c2=(250, 214, 110))
_t("pill_metformin", "pills", r"\b(metformin)\b", "METFORMIN", "drop", shape="capsule", c1=(255, 255, 255), c2=(96, 168, 232))
_t("pill_bp", "pills", r"\b(blood pressure (?:pills?|medicines?|medications?|tablets?)|lisinopril|amlodipine|losartan)\b", "BLOOD PRESSURE PILL", "heart", shape="round", c1=(140, 200, 230), c2=(140, 200, 230))
_t("pill_probiotic", "pills", r"\b(probiotics?)\b", "PROBIOTIC", "stomach", shape="capsule", c1=(92, 158, 104), c2=(220, 240, 220))
_t("pill_multi", "pills", r"\b(multivitamins?|vitamins?|supplements?)\b", "MULTIVITAMIN", "pill", shape="capsule", c1=(250, 160, 50), c2=(255, 230, 160))
_t("pill_iron", "pills", r"\b(iron (?:pills?|supplements?|tablets?))\b", "IRON", "blood", shape="round", c1=(160, 60, 60), c2=(160, 60, 60))
_t("pill_sleep", "pills", r"\b(sleeping pills?|sleep aids?|melatonin)\b", "SLEEP AID", "moon", shape="round", c1=(150, 140, 240), c2=(150, 140, 240))
_t("pill_pain", "pills", r"\b(painkillers?|pain relievers?|ibuprofen|nsaids?|paracetamol|acetaminophen|tylenol|advil)\b", "PAIN RELIEVER", "hand", shape="capsule", c1=(214, 60, 60), c2=(255, 255, 255))
_t("pill_med", "pills", r"\b(medicines?|medications?|meds|pills?|tablets?|prescriptions?|doses?)\b", "YOUR MEDICINE", "pill", shape="capsule", c1=(236, 120, 110), c2=(255, 255, 255))

# foods: bad = shown with a cross unless the sentence says to eat it
for _tid, _rx, _lab, _ic, _bad in (
        ("leafy_greens", r"spinach|kale|leafy greens?|greens|lettuce|chard|collards?", "LEAFY GREENS", "leafy", False), ("broccoli", r"broccoli|cabbage|cauliflower|brussels sprouts?", "BROCCOLI", "broccoli", False),
        ("berries", r"berr(?:y|ies)|blueberr(?:y|ies)|strawberr(?:y|ies)|raspberr(?:y|ies)", "BERRIES", "berries", False), ("apple", r"apples?|pears?", "APPLES", "apple", False),
        ("banana", r"bananas?", "BANANAS", "banana", False), ("citrus", r"oranges?|citrus|lemons?|kiwis?|grapefruits?", "CITRUS", "citrus", False),
        ("oats", r"oats|oatmeal|porridge", "OATS", "bowl", False), ("whole_grains", r"whole grains?|brown rice|whole[- ]wheat|wholegrains?|quinoa|barley", "WHOLE GRAINS", "bread", False),
        ("beans", r"beans|lentils|chickpeas|legumes|peas", "BEANS", "beans", False), ("nuts", r"nuts|almonds|walnuts|peanuts|seeds|flaxseeds?|chia", "NUTS", "nuts", False),
        ("fish", r"fish|salmon|sardines|mackerel|tuna|oily fish|seafood", "FISH", "fish", False), ("eggs", r"eggs?", "EGGS", "egg", False),
        ("yogurt", r"yog(?:h)?urt|kefir", "YOGURT", "yogurt", False), ("olive_oil", r"olive oil", "OLIVE OIL", "oil", False),
        ("avocado", r"avocados?", "AVOCADO", "avocado", False), ("tomato", r"tomato(?:es)?", "TOMATOES", "tomato", False),
        ("carrot", r"carrots?", "CARROTS", "carrot", False), ("sweet_potato", r"sweet potato(?:es)?|potato(?:es)?", "POTATOES", "sweetpotato", False),
        ("garlic", r"garlic|onions?|ginger", "GARLIC", "garlic", False), ("tea", r"green tea|tea", "TEA", "tea", False), ("coffee", r"coffee", "COFFEE", "cup", False),
        ("chicken", r"chicken|turkey|lean meat|lean protein", "CHICKEN", "chicken", False), ("dairy", r"milk|dairy", "MILK", "dairy", False), ("cheese", r"cheese", "CHEESE", "cheese", False),
        ("dark_chocolate", r"dark chocolate|cocoa", "DARK CHOCOLATE", "chocolate", False), ("vegetables", r"vegetables?|veggies", "VEGETABLES", "veg", False), ("fruit", r"fruits?", "FRUIT", "fruit", False),
        ("processed_meat", r"processed meats?|bacon|sausages?|hot dogs?|ham|deli meats?|salami", "PROCESSED MEAT", "bacon", True), ("red_meat", r"red meat|steak|beef", "RED MEAT", "steak", True),
        ("fried_food", r"fried foods?|fries|french fries|deep[- ]fried", "FRIED FOOD", "fries", True), ("soda", r"soda|sodas|soft drinks?|sugary drinks?|fizzy drinks?|juice", "SODA", "soda", True),
        ("chips", r"chips|crisps|snack foods?|junk food", "CHIPS", "chips", True), ("sweets", r"cakes?|pastr(?:y|ies)|cookies|biscuits|candy|sweets|desserts?|donuts?|doughnuts?", "SWEETS", "cake", True),
        ("white_bread", r"white bread|white rice|refined carbs?|white flour", "WHITE BREAD", "whitebread", True), ("fast_food", r"fast food|burgers?|takeaways?|pizza", "FAST FOOD", "burger", True)):
    _t(_tid, "foods", rf"\b({_rx})\b", _lab, _ic, bad=_bad)

# walk / breath / clock / weekly / steady
_t("walk_steps", "walk", r"\b(steps?)\b", "STEPS", "shoe", unit_rx=r"steps?", unit="STEPS")
_t("walk_stairs", "walk", r"\b(stairs|flights? of stairs|staircase)\b", "STAIRS", "stairs", unit_rx=r"flights?|stairs|steps", unit="FLIGHTS")
_t("walk_minutes", "walk", r"\b(walk\w*|stroll\w*)\b", "WALKING", "shoe", unit_rx=r"minutes?|mins?", unit="MINUTES")
_t("exercise_minutes", "walk", r"\b(exercis\w*|active|activity|workouts?|move more|moving)\b", "EXERCISE", "weights", unit_rx=r"minutes?|mins?", unit="MINUTES")
_t("breath_box", "breath", r"\b(box breathing|square breathing)\b", "BOX BREATHING", "lungs")
_t("breath_deep", "breath", r"\b(deep breath\w*|breathing exercises?|breathe (?:in|deeply|slowly)|slow breath\w*|belly breathing)\b", "DEEP BREATHING", "lungs")
_t("breath_relax", "breath", r"\b(meditat\w*|relax\w*|calm (?:down|your)|mindful\w*)\b", "RELAX", "lotus")
_t("clock_sun", "clock", r"\b(sun(?:light|shine)?|outside|outdoors|daylight)\b", "SUNLIGHT", "sun", ctx_txt="IN THE SUN")
_t("clock_nap", "clock", r"\b(naps?|napping)\b", "NAP", "zzz", ctx_txt="SHORT NAP")
_t("clock_meal", "clock", r"\b(after (?:a |each |every |your )?(?:meals?|eating|dinner|lunch|breakfast))\b", "AFTER MEALS", "plate", ctx_txt="AFTER MEALS")
_t("clock_bed", "clock", r"\b(before (?:bed|bedtime|sleep|sleeping)|bedtime)\b", "BEFORE BED", "bed", ctx_txt="BEFORE BED")
_t("clock_fast", "clock", r"\b(fasting|fast for|overnight fast|eating window|intermittent)\b", "FASTING", "plate", ctx_txt="FASTING")
_t("clock_morning", "clock", r"\b(every morning|in the morning|when you wake(?: up)?|first thing)\b", "MORNING", "sun", ctx_txt="EVERY MORNING")
_t("week_strength", "weekly", r"\b(strength|weights?|resistance|bands?|lift\w*|squats?|push-?ups?)\b", "STRENGTH TRAINING", "weights")
_t("week_swim", "weekly", r"\b(swim\w*|water aerobics|pool)\b", "SWIMMING", "wave")
_t("week_fish", "weekly", r"\b(fish|salmon|sardines|mackerel|oily fish)\b", "FISH MEALS", "fish")
_t("week_yoga", "weekly", r"\b(yoga|tai chi|stretch\w*|pilates)\b", "YOGA / TAI CHI", "lotus")
_t("week_social", "weekly", r"\b(friends?|family|visit\w*|social\w*|grandchildren|grandkids|neighbou?rs?)\b", "TIME WITH PEOPLE", "friends")
_t("week_dance", "weekly", r"\b(danc\w*)\b", "DANCING", "dance")
_t("week_bike", "weekly", r"\b(cycl\w*|bikes?|biking)\b", "CYCLING", "bike")
_t("week_walk", "weekly", r"\b(walk\w*|exercis\w*|active|workouts?|move)\b", "ACTIVE DAYS", "shoe")
_t("steady_dizzy", "steady", r"\b(stand(?:ing)? up too (?:fast|quickly)|get(?:ting)? up too (?:fast|quickly)|orthostatic|head rush)\b", "STAND UP SLOWLY", "spiral", mood="dizzy")
_t("steady_falls", "steady", r"\b(falls?|falling|trip\w*|slip\w*|grab bars?|handrails?)\b", "PREVENT FALLS", "fall", mood="falls")
_t("steady_balance", "steady", r"\b(balance|one leg|one foot|steady|stability|wobbl\w*|unsteady)\b", "BALANCE", "person", mood="balance")

# inside: the process in a magnifier; good = what it looks like improving, bad = getting worse
for _tid, _rx, _lab, _ic, _gtxt, _btxt in (
        ("in_artery", r"arter(?:y|ies)|plaque|clog\w*|atheroscl\w*|blood vessels?", "YOUR ARTERIES", "heart", "CLEAR, OPEN ARTERY", "PLAQUE BUILDS UP"),
        ("in_bone", r"bones?|skeleton", "INSIDE THE BONE", "bone", "BONE GETS DENSER", "BONE GETS THINNER"),
        ("in_joint", r"joints?|cartilage|arthritis|knees?|hips?|stiff\w*", "INSIDE THE JOINT", "bone", "CARTILAGE CUSHIONS", "CARTILAGE WEARS THIN"),
        ("in_muscle", r"muscles?|sarcopenia|muscle mass", "INSIDE THE MUSCLE", "weights", "FIBRES GROW STRONGER", "FIBRES SHRINK"),
        ("in_neurons", r"brain|memory|neurons?|brain cells?|cognitive|mind sharp|mentally sharp|dementia|alzheimer\w*", "INSIDE THE BRAIN", "brain", "NEW CONNECTIONS FORM", "CONNECTIONS FADE"),
        ("in_lungs", r"lungs?|copd|asthma|breathing", "INSIDE THE LUNGS", "lungs", "LUNGS FILL WITH AIR", "LESS AIR GETS IN"),
        ("in_gut", r"gut|bacteria|microbiome|probiotics?|digest\w*|bowels?|constipat\w*", "INSIDE THE GUT", "stomach", "GOOD BACTERIA GROW", "BAD BACTERIA TAKE OVER"),
        ("in_flow", r"circulation|blood flow|blood flows?|veins?|varicose", "BLOOD FLOW", "blood", "BLOOD FLOWS FREELY", "BLOOD FLOW SLOWS"),
        ("in_immune", r"immune|immunity|germs?|virus\w*|vaccin\w*", "IMMUNE SYSTEM", "shield", "DEFENCES HOLD", "DEFENCES WEAKEN"),
        ("in_lens", r"cataracts?|vision|eyesight|eyes?|blurr\w*|lens", "INSIDE THE EYE", "eye", "A CLEAR LENS", "THE LENS CLOUDS"),
        ("in_ear", r"ears?|tinnitus|deaf\w*", "INSIDE THE EAR", "ear", "SOUND COMES THROUGH", "SOUND FADES"),
        ("in_teeth", r"teeth|tooth|gums?|dental|floss\w*", "TEETH AND GUMS", "tooth", "HEALTHY GUMS", "GERMS ON THE GUMS"),
        ("in_skin", r"skin|wrinkles?|collagen|bruis\w*", "INSIDE THE SKIN", "hand", "COLLAGEN HOLDS FIRM", "COLLAGEN BREAKS DOWN"),
        ("in_liver", r"liver|fatty liver", "INSIDE THE LIVER", "blood", "FAT CLEARS AWAY", "FAT BUILDS UP"),
        ("in_kidney", r"kidneys?|urine|filters? (?:your|the) blood", "INSIDE THE KIDNEY", "kidney", "CLEAN BLOOD OUT", "WASTE BUILDS UP"),
        ("in_insulin", r"insulin|insulin resistance|cells? (?:use|take in|absorb) (?:sugar|glucose)", "INSULIN AT WORK", "cell", "SUGAR ENTERS THE CELL", "THE CELL STAYS LOCKED")):
    _t(_tid, "inside", rf"\b({_rx})\b", _lab, _ic, variant=_tid[3:], good_txt=_gtxt, bad_txt=_btxt)

# symptoms: one tile each
for _tid, _rx, _lab, _ic in (
        ("sym_chest", r"chest (?:pain|pressure|tightness|hurts|feels tight)|tight(?:ness)? in (?:your|the) chest", "CHEST PAIN", "heart"),
        ("sym_breath", r"short(?:ness)? of breath|breathless\w*|can'?t catch your breath|trouble breathing|out of breath", "SHORT OF BREATH", "lungs"),
        ("sym_dizzy", r"dizz\w*|light-?headed\w*|vertigo|faint\w*", "DIZZINESS", "spiral"), ("sym_headache", r"headaches?|migraines?", "HEADACHE", "head"),
        ("sym_numb", r"numb\w*|tingl\w*|pins and needles", "NUMBNESS", "hand"), ("sym_confusion", r"confus\w*|disorient\w*", "CONFUSION", "question"),
        ("sym_swelling", r"swell\w*|swollen", "SWELLING", "foot"), ("sym_fatigue", r"tired(?:ness)?|fatigue|exhaust\w*|no energy", "TIREDNESS", "battery"),
        ("sym_vision", r"blurr\w* vision|blurry|double vision|trouble seeing", "BLURRED VISION", "eye"), ("sym_thirst", r"thirst\w*|dry mouth", "THIRST", "drop"),
        ("sym_nausea", r"nause\w*|sick to your stomach|vomit\w*", "NAUSEA", "stomach"), ("sym_sweat", r"cold sweats?|sweat\w*", "SWEATING", "drops"),
        ("sym_speech", r"slurr\w*|trouble speaking|speech", "SLURRED SPEECH", "bubble"), ("sym_face", r"face droop\w*|droop\w*|uneven smile", "FACE DROOPING", "face"),
        ("sym_arm", r"arm weakness|weak arm|one arm|arm drift\w*|weak(?:ness)? (?:in|on) one side", "ARM WEAKNESS", "arm")):
    _t(_tid, "symptoms", rf"\b({_rx})\b", _lab, _ic)

# disease: the named condition; variant = the inside-the-body process it shows, what = what it does (plain, accurate), part = where
for _tid, _rx, _lab, _var, _what, _part in (
        ("dz_rheumatoid", r"rheumatoid(?: arthritis)?", "RHEUMATOID ARTHRITIS", "joint", "THE IMMUNE SYSTEM ATTACKS THE JOINTS", "JOINTS"),
        ("dz_osteoarthritis", r"osteoarthritis|arthritis|wear and tear arthritis", "OSTEOARTHRITIS", "joint", "THE CARTILAGE IN A JOINT WEARS DOWN", "JOINTS"),
        ("dz_osteoporosis", r"osteoporosis|osteopenia", "OSTEOPOROSIS", "bone", "BONES LOSE DENSITY AND BREAK MORE EASILY", "BONES"),
        ("dz_gout", r"gout", "GOUT", "joint", "URIC ACID CRYSTALS FORM IN A JOINT", "JOINTS"),
        ("dz_sarcopenia", r"sarcopenia|muscle loss|muscle wasting", "SARCOPENIA", "muscle", "MUSCLE SHRINKS AND WEAKENS WITH AGE", "MUSCLES"),
        ("dz_diabetes", r"type 2 diabetes|type two diabetes|diabetes|prediabetes|pre-diabetes", "TYPE 2 DIABETES", "insulin", "CELLS STOP RESPONDING WELL TO INSULIN", "BLOOD SUGAR"),
        ("dz_hypertension", r"hypertension|high blood pressure", "HIGH BLOOD PRESSURE", "artery", "BLOOD PUSHES TOO HARD ON THE ARTERY WALLS", "ARTERIES"),
        ("dz_heart_failure", r"heart failure|congestive heart", "HEART FAILURE", "flow", "THE HEART PUMPS LESS STRONGLY", "HEART"),
        ("dz_afib", r"atrial fibrillation|afib|a-fib|irregular heartbeat|arrhythmia", "ATRIAL FIBRILLATION", "flow", "THE HEART BEATS OUT OF RHYTHM", "HEART"),
        ("dz_heart_disease", r"coronary (?:artery |heart )?disease|heart disease|atherosclerosis|clogged arteries", "HEART DISEASE", "artery", "PLAQUE NARROWS THE HEART'S ARTERIES", "ARTERIES"),
        ("dz_pad", r"peripheral artery disease|peripheral arterial disease|\bpad\b|poor circulation in (?:your|the) legs", "PERIPHERAL ARTERY DISEASE", "flow", "NARROW ARTERIES CUT BLOOD TO THE LEGS", "LEGS"),
        ("dz_dvt", r"deep vein thrombosis|dvt|blood clots? in (?:your|the) legs?", "DEEP VEIN THROMBOSIS", "flow", "A CLOT FORMS IN A DEEP VEIN", "VEINS"),
        ("dz_varicose", r"varicose veins?|spider veins?", "VARICOSE VEINS", "flow", "WEAK VEIN VALVES LET BLOOD POOL", "VEINS"),
        ("dz_anemia", r"an(?:a)?emia|an(?:a)?emic", "ANEMIA", "flow", "TOO FEW RED CELLS TO CARRY OXYGEN", "BLOOD"),
        ("dz_stroke", r"strokes?|mini-?stroke|tia", "STROKE", "neurons", "BLOOD FLOW TO PART OF THE BRAIN IS BLOCKED", "BRAIN"),
        ("dz_alzheimers", r"alzheimer'?s?(?: disease)?", "ALZHEIMER'S DISEASE", "neurons", "BRAIN CELLS LOSE THEIR CONNECTIONS", "BRAIN"),
        ("dz_dementia", r"dementia|cognitive decline", "DEMENTIA", "neurons", "MEMORY AND THINKING SLOWLY DECLINE", "BRAIN"),
        ("dz_parkinsons", r"parkinson'?s?(?: disease)?", "PARKINSON'S DISEASE", "neurons", "NERVE CELLS THAT CONTROL MOVEMENT FADE", "BRAIN"),
        ("dz_depression", r"depression|clinical depression", "DEPRESSION", "neurons", "MOOD AND ENERGY STAY LOW FOR WEEKS", "MIND"),
        ("dz_copd", r"copd|emphysema|chronic bronchitis", "COPD", "lungs", "AIRWAYS NARROW AND AIR GETS TRAPPED", "LUNGS"),
        ("dz_asthma", r"asthma", "ASTHMA", "lungs", "AIRWAYS SWELL AND TIGHTEN", "LUNGS"),
        ("dz_pneumonia", r"pneumonia", "PNEUMONIA", "lungs", "AN INFECTION FILLS THE AIR SACS", "LUNGS"),
        ("dz_sleep_apnea", r"sleep apn(?:o)?ea|apn(?:o)?ea", "SLEEP APNEA", "lungs", "BREATHING STOPS AGAIN AND AGAIN IN SLEEP", "AIRWAY"),
        ("dz_kidney", r"chronic kidney disease|kidney disease|ckd|kidney failure", "KIDNEY DISEASE", "kidney", "THE KIDNEYS FILTER LESS WASTE", "KIDNEYS"),
        ("dz_fatty_liver", r"fatty liver(?: disease)?|nafld|masld", "FATTY LIVER", "liver", "FAT BUILDS UP INSIDE THE LIVER", "LIVER"),
        ("dz_reflux", r"acid reflux|gerd|heartburn", "ACID REFLUX", "gut", "STOMACH ACID FLOWS BACK UP", "STOMACH"),
        ("dz_diverticulitis", r"diverticul\w+", "DIVERTICULITIS", "gut", "SMALL POUCHES IN THE COLON INFLAME", "COLON"),
        ("dz_constipation", r"constipation|constipated", "CONSTIPATION", "gut", "STOOL MOVES TOO SLOWLY", "BOWEL"),
        ("dz_cataracts", r"cataracts?", "CATARACTS", "lens", "THE EYE'S LENS GROWS CLOUDY", "EYES"),
        ("dz_glaucoma", r"glaucoma", "GLAUCOMA", "lens", "PRESSURE DAMAGES THE OPTIC NERVE", "EYES"),
        ("dz_macular", r"macular degeneration|amd", "MACULAR DEGENERATION", "lens", "THE CENTRE OF VISION BLURS", "EYES"),
        ("dz_hearing", r"age-related hearing loss|presbycusis|hearing loss", "HEARING LOSS", "ear", "INNER-EAR HAIR CELLS WEAR OUT", "EARS"),
        ("dz_gum", r"gum disease|gingivitis|periodontitis", "GUM DISEASE", "teeth", "GERMS INFLAME THE GUMS", "GUMS"),
        ("dz_shingles", r"shingles", "SHINGLES", "immune", "THE CHICKENPOX VIRUS WAKES UP AGAIN", "NERVES & SKIN"),
        ("dz_skin_cancer", r"skin cancer|melanoma", "SKIN CANCER", "skin", "SUN DAMAGE CHANGES SKIN CELLS", "SKIN")):
    _t(_tid, "disease", rf"\b({_rx})\b", _lab, "cell", variant=_var, what=_what, part=_part)

BY_ENGINE: Dict[str, List[dict]] = {e: [s for s in TOPICS.values() if s["engine"] == e] for e in ENGINES}

# ---------------------------------------------------------------- reading the sentence

NUM_RX = re.compile(rf"\b{LX.NUM}\b", re.I)
RISK_RX = re.compile(r"\b(risks?|chances?|odds|likel(?:y|ihood)|protects?|prevents?|halves?|doubles?|less likely|more likely|live longer)\b", re.I)
PCT_RX = re.compile(rf"\b{LX.NUM}\s*(?:%|percent\b|per cent\b)", re.I)
RATIO_RX = re.compile(rf"\b{LX.NUM}\s+(?:in|out\s+of)\s+(?:every\s+)?{LX.NUM}\b", re.I)
FRAC_RX = re.compile(r"\b(half|a third|one third|a quarter|one quarter|two thirds|three quarters)\s+of\b", re.I)
FREQ_RX = re.compile(rf"\b(once|twice|{LX.NUM}\s+times|{LX.NUM}\s+days)\s+(?:a|per|each|every)\s+week\b|\b(every\s+day|daily|each\s+day)\b", re.I)
TAKE_RX = re.compile(r"\b(take|taking|took|supplements?|pills?|tablets?|capsules?|doses?|prescribed|medicines?|medications?)\b", re.I)
AVOID_RX = re.compile(r"\b(avoid\w*|cut (?:back|down|out)|cut|limit\w*|less|fewer|skip\w*|stop\w*|instead of|swap\w* out|go easy on|too much|raise[sd]?|harm\w*|bad for)\b", re.I)
EAT_RX = re.compile(r"\b(eat\w*|add\w*|try|enjoy|choose|more|swap\w* (?:in|to)|instead|rich in|full of|protects?|helps?|good for)\b", re.I)
WORSE_RX = re.compile(r"\b(damag\w*|harm\w*|weaken\w*|los(?:e|es|ing|s)|shrink\w*|clog\w*|builds? up|thins?|thinner|wears?|worn|declin\w*|hurts?|inflam\w*|brittle|stiff\w*|without|lack\w*|cloud\w*|fades?|blocks?)\b", re.I)
BAD_PEOPLE_RX = re.compile(r"\b(falls?|die|dies|death|strokes?|dementia|disease|cancer|diabet\w*|pain|lonely|deficien\w*|lose|loss|suffer\w*|risk|don'?t|never|miss|lack|struggle|high)\b", re.I)
LOW_RX = re.compile(r"\b(low|deficien\w*|lack\w*|not enough|too little)\b", re.I)
HALF_RX = re.compile(r"\b(halves?|halved|cut (?:it |the risk )?in half|by half)\b", re.I)
DOUBLE_RX = re.compile(r"\b(doubles?|doubled|twice the risk|twice as likely)\b", re.I)
TIMES = {"once": 1, "twice": 2}

def _nums(text: str) -> List[tuple]:
    out = []
    for m in NUM_RX.finditer(text):
        try: out.append((float(LX.num(m.group(1))), m.start(), m.end()))
        except (ValueError, TypeError): pass
    return out

def _num_unit(text: str, unit_rx: str):
    """(value, start) of the first number said with this unit ("seven thousand steps", "20 minutes of sun"), or None."""
    for v, s, e in _nums(text):
        if re.match(rf"\s*(?:[a-z-]+\s+)?(?:{unit_rx})", text[e:], re.I): return v, s
    return None

def _val(s: str) -> Optional[float]:
    try: return float(LX.num(s))
    except (ValueError, TypeError): return None

def _trend(text: str) -> str:
    return "down" if DOWN_RX.search(text) or LOW_RX.search(text) else "up" if UP_RX.search(text) else ""

def _first(engine: str, text: str):
    for sp in BY_ENGINE[engine]:
        m = sp["rx"].search(text)
        if m: return sp, m
    return None, None

def _all(engine: str, text: str) -> List[tuple]:
    got, seen = [], set()
    for sp in BY_ENGINE[engine]:
        for m in sp["rx"].finditer(text):
            if any(m.start() < e and s < m.end() for s, e in seen): continue
            seen.add((m.start(), m.end())); got.append((m.start(), sp, m)); break
    return sorted(got, key=lambda g: g[0])

# one builder per card type: (sp, sc, text, at, m or None when a CSV row forces the topic) -> (support, payload) or None

def _b_meter(sp, sc, text, at, m):
    pos = m.start() if m else 0; lo, hi = sp["range"]; p = {"topic": sp["id"], "at": at(sc, text, pos), "trend": _trend(text)}
    tm = DOWN_RX.search(text) or LOW_RX.search(text) or UP_RX.search(text); p["move_at"] = at(sc, text, tm.start()) if tm else p["at"]
    for v, s, e in _nums(text):
        pct = re.match(r"\s*(?:%|percent|per cent)", text[e:], re.I)
        age = re.search(r"\b(over|above|aged?|past|after|before|turn(?:ing)?|in your|by)\s+(?:the age of\s+)?$", text[:s], re.I) and v >= 40      # "after seventy", "over 85": an age, not a reading
        if lo <= v <= hi and not age and abs(s - pos) < 70 and (not pct or sp["unit"] == "%") and not re.match(r"\s*(?:years?|times?|days?|weeks?|minutes?|hours?|glasses|cups|steps)", text[e:], re.I):
            p["value"] = v; p["move_at"] = at(sc, text, s); break
    return (0.91 if ("value" in p or p["trend"]) else 0.87), p

def _b_tube(sp, sc, text, at, m):
    got = _num_unit(text, sp["unit_rx"]); lo = sp.get("lo", 0); tr = _trend(text)
    if got and lo <= got[0] <= sp["max"] * 1.5: val, vat = got[0], at(sc, text, got[1])
    else:
        if not m is None and not (tr or re.search(r"\b(limit|no more than|at most|up to|at least|aim for|target|too much|enough|a day|daily|per day|a week)\b", text, re.I)): return None
        val = sp["default"] if not tr else (sp["mark"] * (0.6 if sp["mode"] == "limit" else 1.0) if tr == "down" else (sp["max"] * 0.85 if sp["mode"] == "limit" else sp["mark"]))
        vat = at(sc, text, m.start() if m else 0)
    return (0.9 if got else 0.85), {"topic": sp["id"], "at": at(sc, text, m.start() if m else 0), "value": min(val, sp["max"]), "said": bool(got), "value_at": vat}

def _b_people(sp, sc, text, at, m):
    k = n = None; lab = ""; pos = 0
    r = RATIO_RX.search(text)
    if r:
        a, b = _val(r.group(1)), _val(r.group(2))
        if a and b and a < b <= 10: k, n, lab, pos = int(a), int(b), f"{int(a)} IN {int(b)}", r.start()
    if k is None:
        f = FRAC_RX.search(text)
        if f:
            k, n = {"half": (1, 2), "a third": (1, 3), "one third": (1, 3), "a quarter": (1, 4), "one quarter": (1, 4), "two thirds": (2, 3), "three quarters": (3, 4)}[f.group(1).lower()]
            lab, pos = f.group(1).upper(), f.start()
    if k is None:
        pc = PCT_RX.search(text)
        if pc and (m is None or re.search(r"\bof\b", text[pc.end():pc.end() + 30], re.I)):
            v = _val(pc.group(1))
            if v and 0 < v < 100: k, n, lab, pos = int(round(v)), 100, f"{v:g}%", pc.start()
    if k is None:
        if m is not None: return None
        k, n, lab = 1, 3, sp["label"]
    if n == 100 and k % 10 == 0: k, n = k // 10, 10
    grid = n if n <= 10 else 100
    if 2 < n <= 5 and n == grid: pass
    elif n in (2, 4, 5): k, grid = k * (10 // n), 10      # "half" / "a quarter" / "1 in 5" read best on ten people
    return 0.9, {"topic": sp["id"], "at": at(sc, text, pos), "k": k, "grid": grid, "label": lab, "bad": bool(BAD_PEOPLE_RX.search(text))}

def _b_risk(sp, sc, text, at, m):
    rk = RISK_RX.search(text)
    if m is not None and not rk: return None
    pc = PCT_RX.search(text); pct = _val(pc.group(1)) if pc else None; tr = _trend(text)
    if HALF_RX.search(text) and pct is None: pct, tr = 50.0, "down"
    if DOUBLE_RX.search(text) and pct is None: pct, tr = 100.0, "up"
    if re.search(r"\b(protects?|prevents?|less likely|live longer|lowers?|reduces?|cuts?)\b", text, re.I): tr = "down"
    elif re.search(r"\b(more likely|raises?|increases?)\b", text, re.I): tr = "up"
    tr = tr or "down"
    p = {"topic": sp["id"], "at": at(sc, text, m.start() if m else 0), "trend": tr, "pct": pct, "pct_at": at(sc, text, pc.start()) if pc else at(sc, text, rk.start() if rk else 0)}
    return (0.92 if pct else 0.87), p

def _b_pills(sp, sc, text, at, m):
    if m is not None and sp["id"] != "pill_med" and not TAKE_RX.search(text): return None
    low = text.lower(); times = 2 if re.search(r"\btwice a day|two times a day|morning and (?:night|evening)|every twelve hours\b", low) else 1
    note = "WITH FOOD" if re.search(r"\bwith (?:food|a meal|meals|breakfast|dinner)\b", low) else "AT NIGHT" if re.search(r"\b(at night|before bed|bedtime|evening)\b", low) else "EVERY MORNING" if re.search(r"\b(morning|breakfast)\b", low) else "ON TIME, EVERY DAY" if re.search(r"\b(every day|daily|on time|same time|never miss|skip)\b", low) else ""
    return 0.88, {"topic": sp["id"], "at": at(sc, text, m.start() if m else 0), "times": times, "note": note}

def _b_foods(sp, sc, text, at, m, items=None):
    items = items or [(m.start() if m else 0, sp, m)]; out = []
    for pos, s2, mm in items[:6]:
        before = text[max(0, pos - 60):pos]; av = AVOID_RX.search(before); ea = EAT_RX.search(before)
        bad = (av.start() > ea.start() if (av and ea) else bool(av)) if (av or ea) else s2["bad"]
        out.append({"topic": s2["id"], "at": at(sc, text, pos), "bad": bad})
    return 0.83 + 0.03 * min(3, len(out)), {"topic": out[0]["topic"], "items": out}

def _b_walk(sp, sc, text, at, m):
    got = _num_unit(text, sp["unit_rx"])
    if sp["id"] == "walk_steps" and got and got[0] < 100: got = None      # "two steps" is not a step count
    if not got:
        if m is not None: return None
        return 0.8, {"topic": sp["id"], "at": at(sc, text, 0), "value": None, "unit": sp["unit"]}
    return 0.91, {"topic": sp["id"], "at": at(sc, text, m.start() if m else 0), "value": got[0], "value_at": at(sc, text, got[1]), "unit": sp["unit"]}

def _b_breath(sp, sc, text, at, m):
    ns = [int(v) for v, s, e in _nums(text) if 2 <= v <= 10 and re.match(r"\s*(?:seconds?|counts?|,|\.|$|and)", text[e:], re.I)][:3]
    inn, hold, out = (ns + [None] * 3)[:3]
    if sp["id"] == "breath_box": inn, hold, out = (ns[0] if ns else 4,) * 3
    return 0.88, {"topic": sp["id"], "at": at(sc, text, m.start() if m else 0), "inn": inn or 4, "hold": hold if hold is not None else (4 if ns else 0), "out": out or (6 if not ns else (inn or 4))}

def _b_clock(sp, sc, text, at, m):
    mins = _num_unit(text, r"minutes?|mins?"); hrs = _num_unit(text, r"hours?|hrs?")
    if m is not None and not (mins or hrs or sp["id"] in ("clock_meal", "clock_bed", "clock_morning")): return None
    p = {"topic": sp["id"], "at": at(sc, text, m.start() if m else 0)}
    if mins and mins[0] <= 120: p.update(minutes=mins[0], value_at=at(sc, text, mins[1]))
    elif hrs and hrs[0] <= 24: p.update(hours=hrs[0], value_at=at(sc, text, hrs[1]))
    return (0.89 if len(p) > 2 else 0.84), p

def _b_weekly(sp, sc, text, at, m):
    f = FREQ_RX.search(text)
    if not f:
        if m is not None: return None
        n, pos = 3, 0
    else:
        g = f.group(0).lower(); pos = f.start()
        if re.search(r"every\s+day|daily|each\s+day", g): n = 7
        elif g.split()[0] in TIMES: n = TIMES[g.split()[0]]
        else: n = int(_val(g.split()[0]) or 0) if _val(g.split()[0]) else 0
        if not 1 <= n <= 7: return None
    return 0.9, {"topic": sp["id"], "at": at(sc, text, m.start() if m else 0), "n": n, "n_at": at(sc, text, pos)}

def _b_inside(sp, sc, text, at, m):
    good = not WORSE_RX.search(text) or bool(re.search(r"\b(protects?|prevents?|repairs?|heals?|strengthens?|builds?|improves?|clears?|keeps?|helps?)\b", text, re.I) and not re.search(r"\b(damag\w*|harm\w*)\b", text, re.I))
    tm = (DOWN_RX.search(text) or UP_RX.search(text) or WORSE_RX.search(text))
    return (0.88 if tm else 0.84), {"topic": sp["id"], "at": at(sc, text, m.start() if m else 0), "good": good, "move_at": at(sc, text, tm.start()) if tm else None}

def _b_steady(sp, sc, text, at, m):
    return 0.88, {"topic": sp["id"], "at": at(sc, text, m.start() if m else 0)}

def _b_symptoms(sp, sc, text, at, m, items=None):
    items = items or [(m.start() if m else 0, sp, m)]
    if m is not None and len(items) < 2: return None
    return 0.86 + 0.02 * min(3, len(items)), {"topic": items[0][1]["id"], "items": [{"topic": s2["id"], "at": at(sc, text, pos)} for pos, s2, _ in items[:6]]}

HELP_RX = re.compile(r"\b(prevent\w*|protect\w*|treat\w*|manag\w*|control\w*|reverse\w*|improv\w*|help\w*|ease\w*|slow(?:s|ing)? (?:it|down)|lower\w*|reduc\w*|cut\w*|fight\w*|beat)\b", re.I)
WARN_RX = re.compile(r"\b(call (?:your doctor|911|999|an ambulance)|see (?:a|your) doctor|emergency|get checked|ask your doctor)\b", re.I)

def _b_disease(sp, sc, text, at, m):
    hm = HELP_RX.search(text); good = bool(hm) and not WORSE_RX.search(text[:hm.start()] if hm else "")
    return 0.9, {"topic": sp["id"], "at": at(sc, text, m.start() if m else 0), "good": good, "move_at": at(sc, text, hm.start()) if hm else None, "doctor": bool(WARN_RX.search(text))}

BUILD = {"disease": _b_disease, "meter": _b_meter, "tube": _b_tube, "people": _b_people, "risk": _b_risk, "pills": _b_pills, "foods": _b_foods, "walk": _b_walk, "breath": _b_breath, "clock": _b_clock,
         "weekly": _b_weekly, "inside": _b_inside, "steady": _b_steady, "symptoms": _b_symptoms}

def evidence(sc: dict, text: str, at: Callable[[dict, str, int], float]) -> Dict[str, tuple]:
    """engine -> (support, payload) for every card type this sentence has the shape of (one topic each)."""
    ev: Dict[str, tuple] = {}
    for eng in ENGINES:
        if eng in ("foods", "symptoms"):
            items = _all(eng, text)
            if not items: continue
            got = BUILD[eng](items[0][1], sc, text, at, items[0][2], items=items)
        elif eng == "people":
            if not (RATIO_RX.search(text) or FRAC_RX.search(text) or PCT_RX.search(text)): continue
            sp, m = _first(eng, text)
            if not sp: continue
            got = BUILD[eng](sp, sc, text, at, m)
        else:
            got = None
            for sp in BY_ENGINE[eng]:      # the most specific topic whose shape the sentence has (catalogue order)
                m = sp["rx"].search(text)
                if m: got = BUILD[eng](sp, sc, text, at, m)
                if got: break
        if got: ev[eng] = got
    return ev

def forced(tid: str, sc: dict, text: str, at: Callable) -> Optional[tuple]:
    """(engine, payload) for a CSV row that names a topic id: the topic is used even when the sentence does not name it; numbers still come from the sentence."""
    sp = TOPICS.get(tid)
    if not sp: return None
    eng = sp["engine"]
    if eng in ("foods", "symptoms"):
        items = _all(eng, text); items = [it for it in items if it[1]["id"] == tid] + [it for it in items if it[1]["id"] != tid] or [(0, sp, None)]
        if items[0][1]["id"] != tid: items.insert(0, (0, sp, None))
        got = BUILD[eng](sp, sc, text, at, None, items=items)
    else: got = BUILD[eng](sp, sc, text, at, sp["rx"].search(text) if eng in ("meter",) else None)
    return (eng, got[1]) if got else None

# ---------------------------------------------------------------- drawing helpers

def _head(d, ctx, x0, y0, sp, t, text=None):
    a = _cl(t / 0.4); icon(d, sp["icon"], x0 + ctx.px(84), y0 + ctx.px(68), ctx.px(34), a); _label(d, ctx, (x0 + ctx.px(136), y0 + ctx.px(52)), text or sp["label"], size=30, a=a)

def _chip(d, ctx, cx, y, text, col, a=1.0, size=34, fg=(255, 255, 255)):
    if a <= 0 or not text: return
    f = ctx.font(T.HEAD_FONT, size); w = D._text_w(d, text, f, ctx.px(1)); h = ctx.px(size + 26)
    d.rounded_rectangle((cx - w / 2 - ctx.px(26), y, cx + w / 2 + ctx.px(26), y + h), radius=h // 2, fill=_c(col, a)); D.text_spaced(d, (cx - w / 2, y + ctx.px(10)), text, f, _c(fg, a), ctx.px(1))

def _num_txt(v: float, dec: Optional[int] = None) -> str:
    if dec is not None: return f"{v:,.{dec}f}"
    return f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:.1f}"

def _since(p, k, t0, t, dur, default=0.0):
    a = _rel(p, k, t0); a = default if a is None else a; return _cl((t - a) / dur)

def _check(d, cx, cy, r, col, a=1.0):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_c(col, a)); d.line((cx - r * 0.45, cy, cx - r * 0.1, cy + r * 0.38, cx + r * 0.5, cy - r * 0.38), fill=_c((255, 255, 255), a), width=max(2, int(r * 0.22)))

def _cross(d, cx, cy, r, col, a=1.0):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_c(col, a)); w = max(2, int(r * 0.22))
    d.line((cx - r * 0.4, cy - r * 0.4, cx + r * 0.4, cy + r * 0.4), fill=_c((255, 255, 255), a), width=w); d.line((cx - r * 0.4, cy + r * 0.4, cx + r * 0.4, cy - r * 0.4), fill=_c((255, 255, 255), a), width=w)

# ---------------------------------------------------------------- the cards

def meter(cv, ctx, p, t, t0):
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; _head(d, ctx, x0, y0, sp, t)
    lo, hi = sp["range"]; cx, cy, r = (x0 + x1) / 2, y0 + P(480), P(290); fr = lambda v: (_cl(v, lo, hi) - lo) / (hi - lo)
    d.pieslice((cx - r - P(22), cy - r - P(22), cx + r + P(22), cy + r + P(22)), 180, 360, fill=(232, 238, 241, 255)); d.rectangle((cx - r - P(22), cy, cx + r + P(22), cy + P(10)), fill=(232, 238, 241, 255))
    prev = lo; box = (cx - r * 0.92, cy - r * 0.92, cx + r * 0.92, cy + r * 0.92)
    for upto, col, _ in sp["zones"]:
        if fr(upto) > fr(prev): d.arc(box, 180 + 180 * fr(prev), 180 + 180 * fr(upto), fill=col + (255,), width=P(40))
        prev = upto
    for k in range(11): a = math.radians(180 + 18 * k); d.line((cx + r * 0.66 * math.cos(a), cy + r * 0.66 * math.sin(a), cx + r * 0.73 * math.cos(a), cy + r * 0.73 * math.sin(a)), fill=_c(INK, 0.7), width=P(3))
    prev = lo
    for upto, col, name in sp["zones"]:
        if fr(upto) > fr(prev):
            am = math.radians(180 + 90 * (fr(prev) + fr(upto))); _label(d, ctx, (cx + (r + P(52)) * math.cos(am), cy + (r + P(52)) * math.sin(am) - P(12)), name, col, 18, centre=True)
        prev = upto
    good, bad, hb, tr = sp["good"], sp["bad"], sp.get("hb", False), p.get("trend", "")
    if p.get("value") is not None: vf, vt = (lo if not tr else (bad if (tr == "down") != hb else good)), p["value"]
    elif tr: vf, vt = ((bad, good) if (tr == "down") != hb else (good, bad))
    else: vf, vt = lo, good
    q = T.ease_in_out(_since(p, "move_at", t0, t, 1.4, 0.5)); v = vf + (vt - vf) * q; a = math.radians(180 + 180 * fr(v)) + 0.01 * math.sin(t * 8)
    d.line((cx, cy, cx + r * 0.8 * math.cos(a), cy + r * 0.8 * math.sin(a)), fill=_c(INK), width=P(10)); d.ellipse((cx - P(24), cy - P(24), cx + P(24), cy + P(24)), fill=_c(INK))
    dec = 1 if (hi - lo) <= 20 else 0; _big(d, ctx, (cx, cy + P(36)), _num_txt(v, dec), 84, INK); _label(d, ctx, (cx, cy + P(140)), sp["unit"], (110, 124, 140), 24, centre=True)
    zc, zn = next(((col, n) for upto, col, n in sp["zones"] if v < upto), sp["zones"][-1][1:])
    _chip(d, ctx, cx, y1 - P(96), zn, zc, _cl((q - 0.6) / 0.3) if (p.get("value") is not None or tr) else _cl((t - 1.6) / 0.4), 30)

def tube(cv, ctx, p, t, t0):
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; _head(d, ctx, x0, y0, sp, t)
    lo, hi, mark = sp.get("lo", 0), sp["max"], sp["mark"]; tx0, tx1, ty0, ty1 = x0 + P(200), x0 + P(320), y0 + P(140), y1 - P(130)
    Y = lambda v: ty1 - (ty1 - ty0) * (_cl(v, lo, hi) - lo) / (hi - lo)
    d.rounded_rectangle((tx0 - P(10), ty0 - P(10), tx1 + P(10), ty1 + P(60)), radius=P(70), fill=(232, 238, 241, 255)); d.rounded_rectangle((tx0, ty0, tx1, ty1 + P(50)), radius=P(60), fill=(255, 255, 255, 255), outline=_c((170, 184, 196)), width=P(3))
    for k in range(6): v = lo + (hi - lo) * k / 5; yy = Y(v); d.line((tx0 - P(40), yy, tx0 - P(12), yy), fill=_c(INK, 0.6), width=P(3)); _label(d, ctx, (tx0 - P(56) - P(len(_num_txt(v, sp.get('decimals'))) * 15), yy - P(14)), _num_txt(v, sp.get("decimals")), (110, 124, 140), 20)
    q = T.ease_in_out(_since(p, "value_at", t0, t, 1.6, 0.4)); v = lo + (p["value"] - lo) * q; over = v > mark
    col = (BAD if over else GOOD) if sp["mode"] == "limit" else (GOOD if v >= mark * 0.98 else MID)
    d.rounded_rectangle((tx0 + P(14), Y(v), tx1 - P(14), ty1 + P(36)), radius=P(44), fill=_c(col)); d.rectangle((tx0 + P(24), Y(v) + P(6), tx0 + P(36), ty1), fill=(255, 255, 255, 90)) if Y(v) + P(6) < ty1 else None
    my = Y(mark)      # the limit / goal line, dashed across
    for k in range(14): xx = tx0 - P(20) + k * P(34); d.line((xx, my, xx + P(20), my), fill=_c(INK), width=P(5))
    _label(d, ctx, (tx1 + P(30), my - P(46)), f"{sp['mark_txt']}  {_num_txt(mark, sp.get('decimals'))} {sp['unit']}", INK, 22)
    cx = x0 + P(740); icon(d, sp["icon"], cx, y0 + P(270), P(95), _cl(t / 0.5))
    if p.get("said", True) or q > 0: _big(d, ctx, (cx, y0 + P(440)), _num_txt(v, sp.get("decimals")), 104, INK, _cl((t - 0.3) / 0.3)); _label(d, ctx, (cx, y0 + P(560)), sp["unit"], (110, 124, 140), 26, centre=True)
    st = ("OVER THE LIMIT" if over else "UNDER THE LIMIT") if sp["mode"] == "limit" else ("GOAL REACHED" if v >= mark * 0.98 else "BELOW THE GOAL")
    if sp["id"] == "fever": st = "FEVER" if over else "NORMAL"
    _chip(d, ctx, cx, y1 - P(110), st, col, _cl((q - 0.85) / 0.15), 28)

def people(cv, ctx, p, t, t0):
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; _head(d, ctx, x0, y0, sp, t)
    k, g = int(p.get("k", 1)), int(p.get("grid", 3)); at = _rel(p, "at", t0) or 0.0; lit = BAD if p.get("bad") else TEAL
    if g <= 5: cols, rows, s = g, 1, P(80)
    elif g <= 10: cols, rows, s = math.ceil(g / 2), 2, P(66)
    else: cols, rows, s = 10, 10, P(21)
    gapx = (x1 - x0 - P(120)) / cols; gy0 = y0 + P(150); gh = (P(470) / rows) if rows > 1 else P(380); ic = sp["icon"]
    for i in range(g):
        r_, c_ = divmod(i, cols); cx = x0 + P(60) + gapx * (c_ + 0.5); cy = gy0 + gh * (r_ + 0.5) + (P(60) if rows == 1 else 0)
        a = _cl((t - 0.1 - i * (0.04 if g <= 10 else 0.005)) / 0.3); on = i < k and t >= at + 0.2 + i * (0.25 if g <= 10 else 0.015)
        if a <= 0: continue
        if ic == "woman": _person(d, cx, cy, s, a, lit if on else (200, 210, 218), dress=True)
        elif ic == "elder": _person(d, cx, cy, s, a, lit if on else (200, 210, 218), cane=True)
        else: _person(d, cx, cy, s, a, lit if on else (200, 210, 218))
    la = _cl((t - at - 0.3) / 0.4); _big(d, ctx, ((x0 + x1) / 2, y1 - P(200)), p.get("label", ""), 92, lit, la); _label(d, ctx, ((x0 + x1) / 2, y1 - P(84)), sp["label"], (110, 124, 140), 26, la, centre=True)

def risk(cv, ctx, p, t, t0):
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; _head(d, ctx, x0, y0, sp, t)
    down = p.get("trend", "down") == "down"; col = GOOD if down else BAD; q = T.ease_in_out(_since(p, "pct_at", t0, t, 1.2, 0.5))
    cx, cy, R = x0 + P(260), y0 + P(320), P(150); d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=(236, 244, 244, 255), outline=_c(col, 0.6 + 0.4 * q), width=P(8)); icon(d, sp["icon"], cx, cy, P(95), _cl(t / 0.4))
    ax, ay = x0 + P(640), y0 + P(320); L = P(170) * T.ease_out(q)      # the arrow grows down (lower) or up (higher)
    if L > P(10):
        dirn = 1 if down else -1; d.line((ax, ay - dirn * P(85), ax, ay - dirn * P(85) + dirn * L), fill=_c(col), width=P(34)); tip = ay - dirn * P(85) + dirn * L
        d.polygon([(ax - P(60), tip), (ax + P(60), tip), (ax, tip + dirn * P(70))], fill=_c(col))
    pct = p.get("pct"); txt = (("−" if down else "+") + f"{(pct or 0) * q:.0f}%") if pct else ("LOWER" if down else "HIGHER")
    _big(d, ctx, (x0 + P(820), y0 + P(250)), txt, 84 if pct else 60, col, _cl(q * 2), centre=True)
    by = y0 + P(540); bw = (x1 - x0) - P(330); bx = x0 + P(250)      # before / after bars
    after = (1 - (pct or 40) / 100) if down else min(1.6, 1 + (pct or 50) / 100); scale = 1 / max(1.0, after)
    for i, (lab, frac, c) in enumerate((("BEFORE", 1.0, (190, 200, 210)), ("AFTER", 1.0 + (after - 1.0) * q, col))):
        yy = by + i * P(100); _label(d, ctx, (x0 + P(60), yy + P(14)), lab, INK, 26); d.rounded_rectangle((bx, yy, bx + max(P(20), bw * frac * scale), yy + P(64)), radius=P(32), fill=_c(c))

def pills(cv, ctx, p, t, t0):
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; _head(d, ctx, x0, y0, sp, t)
    rows = 2 if p.get("times", 1) == 2 else 1; at = _rel(p, "at", t0) or 0.0; bx0, bx1 = x0 + P(70), x1 - P(60); cw = (bx1 - bx0) / 7
    top = y0 + P(230); ch = P(170) if rows == 2 else P(230)
    d.rounded_rectangle((bx0 - P(16), top - P(16), bx1 + P(16), top + rows * ch + (rows - 1) * P(20) + P(16)), radius=P(26), fill=(214, 226, 230, 255))
    for r_ in range(rows):
        for i, day in enumerate("MTWTFSS"):
            cx0 = bx0 + i * cw + P(6); cy0 = top + r_ * (ch + P(20)); tint = (236, 248, 246) if r_ == 0 else (236, 236, 252)
            d.rounded_rectangle((cx0, cy0, cx0 + cw - P(12), cy0 + ch), radius=P(18), fill=_c(tint), outline=_c((170, 184, 196)), width=P(2))
            if r_ == 0: _label(d, ctx, (cx0 + (cw - P(12)) / 2, top - P(64)), day, INK, 28, centre=True)
            k = r_ * 7 + i; land = at + 0.3 + k * 0.16; ft = _cl((t - land + 0.45) / 0.45)
            if ft > 0:
                ey = cy0 + ch * 0.62; sy = top - P(160); yy = sy + (ey - sy) * T.ease_back(ft) if ft < 1 else ey
                _pill(d, cx0 + (cw - P(12)) / 2, yy, P(36), _cl(ft * 3), sp.get("shape", "capsule"), sp.get("c1", (236, 120, 110)), sp.get("c2", (255, 255, 255)))
    if rows == 2: _label(d, ctx, (bx0 - P(10), top + ch + P(2)), "AM / PM", (110, 124, 140), 18)
    _chip(d, ctx, (x0 + x1) / 2, y1 - P(150), p.get("note") or "EVERY DAY", TEAL, _cl((t - at - 1.6) / 0.4), 34)

def foods(cv, ctx, p, t, t0):
    items = p.get("items") or [{"topic": p["topic"], "at": 0, "bad": TOPICS[p["topic"]].get("bad", False)}]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px
    nb = sum(1 for i in items if i["bad"]); head = "EAT LESS" if nb == len(items) else "EAT MORE" if nb == 0 else "SWAP"
    _head(d, ctx, x0, y0, dict(TOPICS[items[0]["topic"]], icon="plate"), t, head)
    n = len(items); cols = n if n <= 3 else 3; rows = 1 if n <= 3 else 2; tw = (x1 - x0 - P(100)) / cols; th = P(560) / rows if rows == 2 else P(440)
    for i, it in enumerate(items):
        sp = TOPICS[it["topic"]]; r_, c_ = divmod(i, cols); tx = x0 + P(50) + c_ * tw; ty = y0 + P(140) + r_ * th + (P(60) if rows == 1 else 0)
        e = T.ease_back(_cl((t - max(0.1 + i * 0.25, float(it["at"]) - t0 - 0.15)) / 0.45))
        if e <= 0: continue
        a = _cl(e); d.rounded_rectangle((tx + P(12), ty, tx + tw - P(12), ty + th - P(24)), radius=P(26), fill=_c((246, 250, 250), a), outline=_c(BAD if it["bad"] else (190, 214, 214), a), width=P(4 if it["bad"] else 2))
        s = min(tw, th) * 0.26 * e; icon(d, sp["icon"], tx + tw / 2, ty + (th - P(24)) * 0.42, s, a)
        f = ctx.font(T.HEAD_FONT, 30 if rows == 2 else 36); lab = sp["label"]; w = D._text_w(d, lab, f, ctx.px(1))
        if w > tw - P(40): f = ctx.font(T.HEAD_FONT, 24); w = D._text_w(d, lab, f, ctx.px(1))
        D.text_spaced(d, (tx + tw / 2 - w / 2, ty + th - P(24) - P(66 if rows == 2 else 80)), lab, f, _c(INK, a), ctx.px(1))
        (_cross if it["bad"] else _check)(d, tx + tw - P(44), ty + P(34), P(26), BAD if it["bad"] else GOOD, a)

def walk(cv, ctx, p, t, t0):
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; _head(d, ctx, x0, y0, sp, t)
    cx, cy, r = x0 + P(310), y0 + P(420), P(220); q = T.ease_in_out(_since(p, "value_at", t0, t, 1.8, 0.4))
    d.arc((cx - r, cy - r, cx + r, cy + r), 0, 360, fill=(226, 234, 238, 255), width=P(40))
    if q > 0: d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * q, fill=_c(TEAL), width=P(40))
    icon(d, sp["icon"], cx, cy - P(100), P(54), _cl(t / 0.4))
    if p.get("value") is not None: _big(d, ctx, (cx, cy - P(40)), _num_txt(p["value"] * q), 84, INK); _label(d, ctx, (cx, cy + P(70)), p.get("unit", ""), (110, 124, 140), 26, centre=True)
    else: _label(d, ctx, (cx, cy - P(10)), "KEEP MOVING", INK, 34, centre=True)
    n = int(_cl((t - 0.3) / 3.2) * 8)      # footprints walking up the right side
    for i in range(n):
        fx = x0 + P(640) + i * P(36) + (P(40) if i % 2 else 0); fy = y1 - P(120) - i * P(70); ff = _cl((t - 0.3 - i * 0.4) / 0.3)
        d.ellipse((fx - P(20), fy - P(34), fx + P(20), fy + P(24)), fill=_c(INK, 0.75 * ff)); d.ellipse((fx - P(16), fy + P(30), fx + P(16), fy + P(54)), fill=_c(INK, 0.75 * ff))

def breath(cv, ctx, p, t, t0):
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; _head(d, ctx, x0, y0, sp, t)
    inn, hold, out = float(p.get("inn", 4)), float(p.get("hold", 4)), float(p.get("out", 6)); box = sp["id"] == "breath_box"; phases = [("BREATHE IN", inn), ("HOLD", hold), ("BREATHE OUT", out)] + ([("HOLD", hold)] if box else [])
    phases = [ph for ph in phases if ph[1] > 0]; cyc = sum(x for _, x in phases); tt = max(0.0, t - 0.3) % cyc; acc = 0.0; idx = 0
    for idx, (name, dur) in enumerate(phases):
        if tt < acc + dur: break
        acc += dur
    u = (tt - acc) / dur; size = T.ease_in_out(u) if name == "BREATHE IN" else 1 - T.ease_in_out(u) if name == "BREATHE OUT" else (1.0 if idx > 0 and phases[idx - 1][0] == "BREATHE IN" else 0.0)      # a hold after breathing in stays full, after breathing out stays small
    cx, cy = (x0 + x1) / 2, y0 + P(370); R = P(110) + P(140) * size
    for k in range(3): rr = R + P(26) * (k + 1); d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=_c(TEAL, 0.25 - 0.07 * k), width=P(4))
    d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=_c((206, 236, 232))); icon(d, "lungs", cx, cy - P(10), P(60) + P(40) * size, 0.9)
    _big(d, ctx, (cx, y1 - P(250)), name, 56, INK, _cl(t / 0.5)); _label(d, ctx, (cx, y1 - P(176)), str(max(1, math.ceil(dur - (tt - acc)))), TEAL, 40, centre=True)
    seq = "  ·  ".join(f"{int(x)}" for _, x in phases); _label(d, ctx, (cx, y1 - P(100)), f"COUNT  {seq}", (110, 124, 140), 24, centre=True)

def clock(cv, ctx, p, t, t0):
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; _head(d, ctx, x0, y0, sp, t)
    cx, cy, r = x0 + P(320), y0 + P(410), P(230); hrs = p.get("hours"); mins = p.get("minutes")
    frac = (mins / 60.0) if mins is not None else (hrs / (24.0 if hrs > 12 else 12.0)) if hrs is not None else 0.25
    q = T.ease_in_out(_since(p, "value_at", t0, t, 1.6, 0.5)); d.ellipse((cx - r - P(16), cy - r - P(16), cx + r + P(16), cy + r + P(16)), fill=(214, 226, 230, 255)); d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255))
    if q > 0: d.pieslice((cx - r * 0.9, cy - r * 0.9, cx + r * 0.9, cy + r * 0.9), -90, -90 + 360 * min(1.0, frac) * q, fill=_c(TEAL, 0.35))
    for k in range(12): a = math.radians(-90 + 30 * k); d.line((cx + r * 0.82 * math.cos(a), cy + r * 0.82 * math.sin(a), cx + r * 0.94 * math.cos(a), cy + r * 0.94 * math.sin(a)), fill=_c(INK), width=P(5 if k % 3 == 0 else 3))
    a = math.radians(-90 + 360 * min(1.0, frac) * q); d.line((cx, cy, cx + r * 0.78 * math.cos(a), cy + r * 0.78 * math.sin(a)), fill=_c(TEAL), width=P(9)); d.line((cx, cy, cx, cy - r * 0.5), fill=_c(INK), width=P(11))
    d.ellipse((cx - P(16), cy - P(16), cx + P(16), cy + P(16)), fill=_c(INK)); rx = x0 + P(760); icon(d, sp["icon"], rx, y0 + P(260), P(90), _cl(t / 0.5))
    if mins is not None or hrs is not None:
        v = (mins if mins is not None else hrs) * q; _big(d, ctx, (rx, y0 + P(410)), _num_txt(v), 104, INK, _cl((t - 0.4) / 0.3)); _label(d, ctx, (rx, y0 + P(530)), "MINUTES" if mins is not None else "HOURS", (110, 124, 140), 26, centre=True)
    _chip(d, ctx, rx, y1 - P(130), sp.get("ctx_txt", sp["label"]), TEAL, _cl((t - 1.2) / 0.4), 28)

def weekly(cv, ctx, p, t, t0):
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; _head(d, ctx, x0, y0, sp, t)
    n = int(p.get("n", 3)); on = {1: [2], 2: [1, 4], 3: [0, 2, 4], 4: [0, 2, 4, 6], 5: [0, 1, 2, 3, 4], 6: [0, 1, 2, 3, 4, 5], 7: list(range(7))}[max(1, min(7, n))]
    at = _rel(p, "n_at", t0) or 0.4; cw = (x1 - x0 - P(100)) / 7; cy = y0 + P(330); r = min(cw * 0.42, P(58))
    for i, day in enumerate(("M", "T", "W", "T", "F", "S", "S")):
        cx = x0 + P(50) + cw * (i + 0.5); _label(d, ctx, (cx, cy - r - P(60)), day, INK, 30, centre=True); j = on.index(i) if i in on else -1; e = T.ease_back(_cl((t - at - j * 0.28) / 0.4)) if j >= 0 else 0
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=_c((190, 204, 214)), width=P(4), fill=(255, 255, 255, 255))
        if e > 0: rr = r * e; d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=_c(TEAL)); d.ellipse((cx - rr * 0.78, cy - rr * 0.78, cx + rr * 0.78, cy + rr * 0.78), fill=(255, 255, 255, 255)); icon(d, sp["icon"], cx, cy, rr * 0.55, 1.0)
    la = _cl((t - at - len(on) * 0.28) / 0.4); txt = "EVERY DAY" if n == 7 else ("ONCE A WEEK" if n == 1 else "TWICE A WEEK" if n == 2 else f"{n} TIMES A WEEK")
    _big(d, ctx, ((x0 + x1) / 2, y0 + P(480)), txt, 80, INK, la); _chip(d, ctx, (x0 + x1) / 2, y1 - P(120), sp["label"], TEAL, la, 28)

def steady(cv, ctx, p, t, t0):
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; _head(d, ctx, x0, y0, sp, t); mood = sp.get("mood", "balance")
    amp = (14 if mood == "dizzy" else 12) * (math.exp(-max(0.0, t - 0.6) / 1.4) if mood != "dizzy" else max(0.25, math.exp(-max(0.0, t - 1.5) / 2.0))); ang = math.radians(amp * math.sin(t * 3.2))
    fx, fy = x0 + P(330), y1 - P(130); col = INK
    def R(dx, dy): return (fx + dx * math.cos(ang) - dy * math.sin(ang), fy + dx * math.sin(ang) + dy * math.cos(ang))
    if mood == "falls": d.line((fx + P(150), y0 + P(260), fx + P(150), fy), fill=_c((150, 110, 70)), width=P(14)); d.line((fx + P(60), y0 + P(270), fx + P(240), y0 + P(270)), fill=_c((150, 110, 70)), width=P(14))
    d.line((x0 + P(80), fy + P(6), x0 + P(580), fy + P(6)), fill=_c((190, 204, 214)), width=P(8))
    hip, neck = R(0, -P(220)), R(0, -P(400)); d.line((*R(0, 0), *hip), fill=_c(col), width=P(18)); d.line((*hip, *R(P(70), -P(140)), *R(P(40), -P(70))), fill=_c(col), width=P(16), joint="curve")
    d.line((*hip, *neck), fill=_c(col), width=P(22)); hd = R(0, -P(460)); d.ellipse((hd[0] - P(46), hd[1] - P(46), hd[0] + P(46), hd[1] + P(46)), fill=_c(col))
    arm_l, arm_r = (R(-P(170), -P(390)), R(P(150), -P(400))) if mood != "falls" else (R(-P(150), -P(330)), R(P(150), -P(390)))
    d.line((*arm_l, *R(0, -P(380)), *arm_r), fill=_c(col), width=P(14), joint="curve")
    if mood == "dizzy": icon(d, "spiral", hd[0], hd[1] - P(90), P(40), 0.9)
    lx0, lx1, ly = x0 + P(620), x1 - P(70), y0 + P(380)      # a spirit level: the bubble follows the sway and settles in the middle
    d.rounded_rectangle((lx0, ly - P(50), lx1, ly + P(50)), radius=P(50), fill=(226, 244, 236, 255), outline=_c(INK, 0.6), width=P(4)); mid = (lx0 + lx1) / 2
    d.line((mid - P(50), ly - P(50), mid - P(50), ly + P(50)), fill=_c(INK, 0.5), width=P(3)); d.line((mid + P(50), ly - P(50), mid + P(50), ly + P(50)), fill=_c(INK, 0.5), width=P(3))
    bx = mid + (lx1 - lx0) * 0.4 * math.sin(ang) / math.sin(math.radians(14)); d.ellipse((bx - P(40), ly - P(32), bx + P(40), ly + P(32)), fill=_c((140, 214, 120)))
    ok = abs(amp) < 3.5; _chip(d, ctx, mid, ly + P(120), ("STEADY" if ok else "SWAYING") if mood != "dizzy" else ("PAUSE, THEN STAND" if ok else "DIZZY"), GOOD if ok else MID, _cl(t / 0.5), 28)

def symptoms(cv, ctx, p, t, t0):
    items = p.get("items") or [{"topic": p["topic"], "at": 0}]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px
    a0 = _cl(t / 0.4); tx, ty, s = x0 + P(84), y0 + P(70), P(30); d.polygon([(tx, ty - s), (tx + s * 1.1, ty + s * 0.85), (tx - s * 1.1, ty + s * 0.85)], fill=_c(BAD, a0)); _label(d, ctx, (x0 + P(136), y0 + P(52)), "WARNING SIGNS", BAD, 30, a0)
    n = len(items); cols = n if n <= 3 else 3; rows = 1 if n <= 3 else 2; tw = (x1 - x0 - P(100)) / cols; th = P(560) / rows if rows == 2 else P(440)
    for i, it in enumerate(items):
        sp = TOPICS[it["topic"]]; r_, c_ = divmod(i, cols); x = x0 + P(50) + c_ * tw; y = y0 + P(140) + r_ * th + (P(60) if rows == 1 else 0)
        e = T.ease_back(_cl((t - max(0.1 + i * 0.3, float(it["at"]) - t0 - 0.1)) / 0.45)); a = _cl(e)
        if e <= 0: continue
        pulse = 0.5 + 0.5 * math.sin(t * 5 + i); d.rounded_rectangle((x + P(12), y, x + tw - P(12), y + th - P(24)), radius=P(26), fill=_c((255, 240, 236), a), outline=_c(BAD, a * (0.6 + 0.4 * pulse)), width=P(5))
        icon(d, sp["icon"], x + tw / 2, y + (th - P(24)) * 0.4, min(tw, th) * 0.24 * e, a)
        f = ctx.font(T.HEAD_FONT, 28 if rows == 2 else 32); w = D._text_w(d, sp["label"], f, ctx.px(1))
        if w > tw - P(40): f = ctx.font(T.HEAD_FONT, 22); w = D._text_w(d, sp["label"], f, ctx.px(1))
        D.text_spaced(d, (x + tw / 2 - w / 2, y + th - P(24) - P(62 if rows == 2 else 76)), sp["label"], f, _c((150, 40, 34), a), ctx.px(1))

# ---------------------------------------------------------------- inside the body: one process per topic, drawn in a magnifier (local coords: centre R, R)

def _v_artery(d, R, t, k, good):
    pl = (1 - k if good else k) * 0.75 + 0.06; d.rectangle((0, 0, 2 * R, 2 * R), fill=(250, 226, 222, 255))
    d.rectangle((0, 0, 2 * R, R * 0.5), fill=(232, 150, 150, 255)); d.rectangle((0, R * 1.5, 2 * R, 2 * R), fill=(232, 150, 150, 255))
    for cx_, top in ((R * 0.75, True), (R * 1.3, False)):
        h = R * 0.55 * pl; d.ellipse((cx_ - R * 0.45, (R * 0.5 - h) if top else (R * 1.5 - h), cx_ + R * 0.45, (R * 0.5 + h) if top else (R * 1.5 + h)), fill=(246, 214, 120, 255))
    sp = 0.18 + 0.4 * (1 - pl)
    for i in range(14):
        x = ((t * sp + i / 14) % 1.0) * 2.4 * R - 0.2 * R; yy = R + R * 0.28 * (1 - pl * 0.7) * math.sin(i * 2.1); d.ellipse((x - R * 0.09, yy - R * 0.06, x + R * 0.09, yy + R * 0.06), fill=(214, 60, 70, 255))

def _v_bone(d, R, t, k, good):
    por = (1 - k if good else k) * 0.9 + 0.1; d.rectangle((0, 0, 2 * R, 2 * R), fill=CREAM + (255,))
    for i in range(9):
        for j in range(9):
            x = R * 0.1 + i * R * 0.23 + (R * 0.11 if j % 2 else 0); y = R * 0.1 + j * R * 0.23; h = R * 0.035 * (1 + 2.0 * por) * (0.8 + 0.4 * math.sin(i * 3.1 + j * 1.7) ** 2)
            d.ellipse((x - h, y - h * 0.8, x + h, y + h * 0.8), fill=(206, 186, 156, 255))

def _v_joint(d, R, t, k, good):
    wear = (1 - k if good else k) * 0.85; bob = R * 0.03 * math.sin(t * 2.2); d.rectangle((0, 0, 2 * R, 2 * R), fill=(236, 244, 248, 255))
    d.rectangle((R * 0.55, 0, R * 1.45, R * 0.7 + bob), fill=CREAM + (255,)); d.ellipse((R * 0.4, R * 0.45 + bob, R * 1.6, R * 0.95 + bob), fill=CREAM + (255,))
    d.rectangle((R * 0.55, R * 1.3, R * 1.45, 2 * R), fill=CREAM + (255,)); d.ellipse((R * 0.4, R * 1.05, R * 1.6, R * 1.5), fill=CREAM + (255,))
    th = R * 0.1 * (1 - wear * 0.85) + 1
    d.arc((R * 0.4, R * 0.45 + bob, R * 1.6, R * 0.95 + bob), 0, 180, fill=(120, 190, 230, 255), width=max(1, int(th))); d.arc((R * 0.4, R * 1.05, R * 1.6, R * 1.5), 180, 360, fill=(120, 190, 230, 255), width=max(1, int(th)))
    if wear > 0.5:
        for i in range(3): d.line((R * (0.8 + 0.2 * i), R * 0.98, R * (0.85 + 0.2 * i), R * 1.04), fill=(226, 98, 82, int(255 * (wear - 0.5) * 2)), width=max(1, int(R * 0.02)))

def _v_muscle(d, R, t, k, good):
    st = (k if good else 1 - k) * 0.8 + 0.2; d.rectangle((0, 0, 2 * R, 2 * R), fill=(250, 232, 228, 255)); n = 6
    for i in range(n):
        cx_ = R * 0.25 + i * R * 1.5 / (n - 1); w = R * 0.09 * (0.5 + st) * (1 + 0.04 * math.sin(t * 3 + i)); d.rounded_rectangle((cx_ - w, R * 0.1, cx_ + w, R * 1.9), radius=int(w), fill=(206, 80, 84, 255))
        for j in range(12): yy = R * 0.2 + j * R * 0.14; d.line((cx_ - w * 0.8, yy, cx_ + w * 0.8, yy), fill=(232, 130, 130, 255), width=max(1, int(R * 0.01)))

_NODES = [(0.35, 0.4), (0.8, 0.3), (1.3, 0.35), (1.65, 0.7), (0.5, 0.95), (1.0, 0.85), (1.45, 1.15), (0.4, 1.45), (0.95, 1.4), (1.35, 1.65), (0.75, 1.75), (1.7, 1.3)]
def _v_neurons(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, 2 * R), fill=(240, 236, 252, 255)); nodes = [(x * R, y * R) for x, y in _NODES]
    edges = [(i, j) for i in range(len(nodes)) for j in range(i + 1, len(nodes)) if math.dist(nodes[i], nodes[j]) < R * 0.62]; show = int(len(edges) * ((0.45 + 0.55 * k) if good else (1 - 0.6 * k)))
    for n_, (i, j) in enumerate(edges[:show]):
        (ax, ay), (bx, by) = nodes[i], nodes[j]; d.line((ax, ay, bx, by), fill=(186, 168, 240, 255), width=max(2, int(R * 0.025)))
        u = (t * 0.7 + n_ * 0.37) % 1.0; px, py = ax + (bx - ax) * u, ay + (by - ay) * u; d.ellipse((px - R * 0.035, py - R * 0.035, px + R * 0.035, py + R * 0.035), fill=(255, 226, 120, 255))
    for x, y in nodes: d.ellipse((x - R * 0.07, y - R * 0.07, x + R * 0.07, y + R * 0.07), fill=(140, 110, 220, 255))

def _v_lungs(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, 2 * R), fill=(236, 246, 250, 255)); br = math.sin(t * 1.6); sc_ = 1 + (0.12 if good else 0.05) * br
    for s in (-1, 1): cx_ = R + s * R * 0.42; d.ellipse((cx_ - R * 0.36 * sc_, R * 0.55 - R * 0.1 * sc_, cx_ + R * 0.36 * sc_, R * 1.6 * sc_ - R * 0.0), fill=(240, 150, 160, 255))
    d.line((R, R * 0.1, R, R * 0.7), fill=(200, 100, 110, 255), width=max(2, int(R * 0.07)))
    for s in (-1, 1): d.line((R, R * 0.7, R + s * R * 0.35, R * 0.95, R + s * R * 0.45, R * 1.3), fill=(200, 100, 110, 255), width=max(2, int(R * 0.04)))
    if br > 0:
        for i in range(8): u = (t * 0.8 + i / 8) % 1.0; d.ellipse((R - R * 0.03 + R * 0.05 * math.sin(i), R * 0.1 + u * R * 0.6, R + R * 0.03 + R * 0.05 * math.sin(i), R * 0.16 + u * R * 0.6), fill=(150, 200, 240, 200))

def _v_gut(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, 2 * R), fill=(250, 236, 228, 255)); pts = [(x, R + R * 0.35 * math.sin(x / R * 3.0)) for x in range(0, int(2 * R) + 1, max(1, int(R / 30)))]
    d.polygon([(x, y - R * 0.35) for x, y in pts] + [(x, y + R * 0.35) for x, y in reversed(pts)], fill=(244, 196, 176, 255)); g = int(4 + 14 * (k if good else 1 - k)); b = int(4 + 10 * (1 - k if good else k))
    for i in range(g + b):
        x = (i * 0.137 * R * 7 + t * R * 0.12 * (1 if i % 2 else -1)) % (2 * R); y = R + R * 0.35 * math.sin(x / R * 3.0) + R * 0.18 * math.sin(i * 2.3); col = (92, 170, 110) if i < g else (196, 110, 90)
        d.rounded_rectangle((x - R * 0.06, y - R * 0.025, x + R * 0.06, y + R * 0.025), radius=max(1, int(R * 0.025)), fill=col + (255,))

def _v_flow(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, 2 * R), fill=(252, 238, 236, 255)); path = [(x, R + R * 0.45 * math.sin(x / R * 2.2)) for x in range(0, int(2 * R) + 1, max(1, int(R / 30)))]
    d.line(path, fill=(220, 120, 130, 255), width=int(R * 0.5), joint="curve"); d.line(path, fill=(236, 160, 166, 255), width=int(R * 0.36), joint="curve"); sp = 0.12 + (0.35 * k if good else 0.35 * (1 - k))
    for i in range(16):
        u = (t * sp + i / 16) % 1.0; x = u * 2 * R; y = R + R * 0.45 * math.sin(x / R * 2.2) + R * 0.08 * math.sin(i * 1.9); d.ellipse((x - R * 0.07, y - R * 0.05, x + R * 0.07, y + R * 0.05), fill=(200, 40, 56, 255))

def _v_immune(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, 2 * R), fill=(236, 248, 246, 255)); icon(d, "shield", R, R, R * 0.38 * (1 + 0.05 * math.sin(t * 4)), 1.0 if good else 0.5 + 0.5 * (1 - k))
    for i in range(7):
        an = i * 2 * math.pi / 7 + t * 0.2; dist = R * (0.62 + 0.25 * abs(math.sin(t * 1.5 + i))) if good else R * (0.9 - 0.4 * k * abs(math.sin(t + i))); icon(d, "germ", R + dist * math.cos(an), R + dist * math.sin(an), R * 0.12, 1.0)
        if good and dist < R * 0.66: d.arc((R - R * 0.5, R - R * 0.5, R + R * 0.5, R + R * 0.5), math.degrees(an) - 20, math.degrees(an) + 20, fill=(22, 150, 150, 200), width=max(2, int(R * 0.03)))

def _v_lens(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, 2 * R), fill=(250, 240, 232, 255)); icon(d, "eye", R, R, R * 0.85, 1.0); cloud = (1 - k if good else k) * 0.8 + 0.05
    lay_a = int(220 * cloud)
    for i in range(5): rr = R * (0.28 + 0.04 * i); d.ellipse((R - rr, R - rr, R + rr, R + rr), fill=(236, 236, 230, int(lay_a / (i + 1.5))))

def _v_ear(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, 2 * R), fill=(240, 246, 250, 255)); icon(d, "ear", R * 0.55, R, R * 0.6, 1.0); strength = (k if good else 1 - k) * 0.8 + 0.2
    for i in range(5):
        u = (t * 0.6 + i / 5) % 1.0; x = R * 1.8 - u * R * 1.0; rr = R * (0.15 + 0.5 * (1 - u)); a = int(255 * strength * (1 - u * (0.3 if good else 0.9)))
        d.arc((x - rr * 0.4, R - rr, x + rr * 0.4, R + rr), 120, 240, fill=(22, 150, 150, max(0, a)), width=max(2, int(R * 0.04)))

def _v_teeth(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, 2 * R), fill=(252, 236, 236, 255)); d.rectangle((0, 0, 2 * R, R * 0.7), fill=(240, 150, 160, 255))
    for i in range(5): x = R * 0.25 + i * R * 0.38; d.rounded_rectangle((x, R * 0.55, x + R * 0.32, R * 1.45), radius=int(R * 0.1), fill=(255, 255, 255, 255), outline=(200, 206, 214, 255))
    germs = int(10 * ((1 - k) if good else k)) + (0 if good else 2)
    for i in range(germs): x = R * 0.25 + (i * 0.37 % 1) * R * 1.6; icon(d, "germ", x, R * 0.68 + R * 0.04 * math.sin(t * 3 + i), R * 0.06, 1.0)

def _v_skin(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, R * 0.45), fill=(250, 214, 190, 255)); d.rectangle((0, R * 0.45, 2 * R, R * 1.45), fill=(240, 184, 172, 255)); d.rectangle((0, R * 1.45, 2 * R, 2 * R), fill=(252, 232, 166, 255))
    n = int(4 + 6 * ((k if good else 1 - k)))
    for j in range(n): y = R * 0.6 + j * R * 0.8 / max(1, n); d.line([(x, y + R * 0.04 * math.sin(x / R * 6 + t + j)) for x in range(0, int(2 * R) + 1, max(1, int(R / 25)))], fill=(255, 246, 240, 255), width=max(2, int(R * 0.025)))
    for i in range(6): d.ellipse((i * R * 0.36, R * 1.5, i * R * 0.36 + R * 0.3, R * 1.8), fill=(246, 214, 130, 255))

def _v_liver(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, 2 * R), fill=(250, 238, 232, 255)); d.polygon([(R * 0.2, R * 0.7), (R * 1.0, R * 0.45), (R * 1.85, R * 0.6), (R * 1.6, R * 1.0), (R * 1.0, R * 1.5), (R * 0.4, R * 1.25)], fill=(166, 70, 64, 255))
    fat = (1 - k if good else k) * 0.85 + 0.1
    for i in range(12): x = R * 0.5 + (i * 0.29 % 1) * R * 1.1; y = R * 0.75 + ((i * 0.53) % 1) * R * 0.5; rr = R * 0.07 * fat * (0.7 + 0.5 * math.sin(i)); d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(250, 220, 120, 255))

def _v_kidney(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, 2 * R), fill=(244, 240, 248, 255)); d.ellipse((R * 0.45, R * 0.3, R * 1.55, R * 1.7), fill=(184, 84, 96, 255)); d.ellipse((R * 1.2, R * 0.8, R * 1.7, R * 1.2), fill=(244, 240, 248, 255))
    for i in range(10):
        u = (t * 0.4 + i / 10) % 1.0
        if u < 0.5: x, y = R * 0.1 + u * 2 * R * 0.6, R * 0.6 + R * 0.08 * math.sin(i); d.ellipse((x - R * 0.04, y - R * 0.04, x + R * 0.04, y + R * 0.04), fill=(90, 70, 60, 255))
        else: x, y = R * 1.0, R * 1.0 + (u - 0.5) * 2 * R * 0.9; d.ellipse((x - R * 0.035, y - R * 0.05, x + R * 0.035, y + R * 0.05), fill=(96, 168, 232, 255) if good else (160, 140, 80, 255))

def _v_insulin(d, R, t, k, good):
    d.rectangle((0, 0, 2 * R, 2 * R), fill=(252, 244, 236, 255)); d.ellipse((R * 0.55, R * 0.45, R * 1.65, R * 1.55), fill=(240, 200, 210, 255), outline=(200, 120, 140, 255), width=max(2, int(R * 0.03)))
    d.ellipse((R * 0.95, R * 0.85, R * 1.25, R * 1.15), fill=(170, 110, 170, 255)); opened = good and k > 0.4
    d.rectangle((R * 0.5, R * 0.9, R * 0.62, R * 1.1), fill=(22, 150, 150, 255) if opened else (120, 110, 110, 255))
    for i in range(8):
        u = (t * 0.35 + i / 8) % 1.0; x = R * 0.05 + u * R * (1.2 if opened else 0.45); y = R + R * 0.3 * math.sin(i * 1.7) * (1 - u if opened else 1)
        d.regular_polygon((x, y, R * 0.045), 6, fill=(250, 214, 110, 255))

VARIANTS = {"artery": _v_artery, "bone": _v_bone, "joint": _v_joint, "muscle": _v_muscle, "neurons": _v_neurons, "lungs": _v_lungs, "gut": _v_gut, "flow": _v_flow, "immune": _v_immune,
            "lens": _v_lens, "ear": _v_ear, "teeth": _v_teeth, "skin": _v_skin, "liver": _v_liver, "kidney": _v_kidney, "insulin": _v_insulin}

def _magnifier(cv, ctx, variant, cx, cy, R, t, k, good):
    """The process drawn in a round magnifier (teal ring, handle); returns a fresh draw handle on the canvas."""
    P = ctx.px; lay = Image.new("RGBA", (2 * R, 2 * R), (0, 0, 0, 0)); VARIANTS[variant](ImageDraw.Draw(lay, "RGBA"), R, t, k, good)
    mask = Image.new("L", (2 * R, 2 * R), 0); ImageDraw.Draw(mask).ellipse((0, 0, 2 * R - 1, 2 * R - 1), fill=255); lay.putalpha(Image.composite(lay.getchannel("A"), mask, mask))
    D.overlay_paste(cv, lay, _cl(t / 0.5), (int(cx - R), int(cy - R))); d = ImageDraw.Draw(cv, "RGBA")
    d.ellipse((cx - R, cy - R, cx + R, cy + R), outline=_c(TEAL), width=P(14)); hx, hy = cx + R * 0.72, cy + R * 0.72; d.line((hx, hy, hx + P(70), hy + P(70)), fill=_c(INK), width=P(24)); return d

def disease(cv, ctx, p, t, t0):
    """A named condition: the magnifier shows what it does (getting worse, or easing when the sentence says what helps), its name, what it does in plain words, where."""
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; good = p.get("good", False)
    _head(d, ctx, x0, y0, dict(sp, icon="shield" if good else "cell"), t, "CONDITION")
    R = P(190); cx, cy = x0 + P(250), y0 + P(380); k = T.ease_in_out(_since(p, "move_at", t0, t, 2.2, (_rel(p, "at", t0) or 0) + 0.6))
    d = _magnifier(cv, ctx, sp["variant"], cx, cy, R, t, k, good)
    tx, tw = x0 + P(500), (x1 - x0) - P(540); a1 = _cl((t - 0.2) / 0.4); a2 = _cl((t - 0.9) / 0.5); y = y0 + P(150)
    for size in (62, 52, 44, 38, 32):      # the largest size at which the name fits in two lines (one long word: "OSTEOARTHRITIS")
        f = ctx.font(T.HEAD_FONT, size); lines = D._wrap(d, sp["label"], f, tw) or [sp["label"]]
        if len(lines) <= 2 and all(D._text_w(d, ln, f, ctx.px(1)) <= tw for ln in lines): break
    for ln in lines[:3]: D.text_spaced(d, (tx, y), ln, f, _c(INK, a1), ctx.px(1)); y += P(size + 10)
    d.rectangle((tx, y + P(14), tx + P(90) * a1, y + P(22)), fill=_c(TEAL, a1)); y += P(54)
    f2 = ctx.font(T.BODY_FONT, 30)
    for ln in (D._wrap(d, sp["what"], f2, tw) or [sp["what"]])[:3]: D.text_spaced(d, (tx, y), ln, f2, _c((78, 96, 120), a2), ctx.px(2)); y += P(44)
    _label(d, ctx, (tx, y + P(20)), "AFFECTS  ·  " + sp["part"], TEAL, 24, a2)
    chip = "SEE YOUR DOCTOR" if p.get("doctor") else ("WHAT HELPS" if good else "")
    if chip: _chip(d, ctx, tx + P(150), y1 - P(110), chip, BAD if p.get("doctor") else GOOD, _cl((t - 1.4) / 0.4), 28)

def inside(cv, ctx, p, t, t0):
    sp = TOPICS[p["topic"]]; x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); P = ctx.px; _head(d, ctx, x0, y0, sp, t)
    R = P(270); cx, cy = (x0 + x1) / 2 - P(40), y0 + P(380); good = p.get("good", True); k = T.ease_in_out(_since(p, "move_at", t0, t, 2.2, (_rel(p, "at", t0) or 0) + 0.6))
    d = _magnifier(cv, ctx, sp["variant"], cx, cy, R, t, k, good)
    _chip(d, ctx, cx, y1 - P(104), sp["good_txt"] if good else sp["bad_txt"], GOOD if good else BAD, _cl((k - 0.5) / 0.3) if p.get("move_at") is not None else _cl((t - 1.4) / 0.4), 28)

DRAW = {"meter": meter, "tube": tube, "people": people, "risk": risk, "pills": pills, "foods": foods, "walk": walk, "breath": breath, "clock": clock, "weekly": weekly, "inside": inside,
        "steady": steady, "symptoms": symptoms, "disease": disease}
