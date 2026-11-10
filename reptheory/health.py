"""Elder Health Theory's health cards, drawn in code from the sentence's own words (no assets, nothing generated):

    vitals    a heart monitor: a live ECG trace, a beating heart, the spoken number rolling up        ("your heart beats about 100,000 times a day")
    pressure  a blood-pressure gauge: zones, a needle that moves the way the sentence says, the pump    ("walking lowers your blood pressure", "120 over 80")
    sugar     a glucose meter + a blood-sugar curve that spikes after a meal and drops when it lowers   ("a short walk lowers blood sugar")
    body      a body map: the organ the sentence names lights up and pulses, a scan line, its label     ("your kidneys clean your blood")
    water     glasses filling one by one to the spoken count                                            ("drink six glasses of water")
    sleep     a night dial filling the spoken hours, a moon and stars                                   ("sleep seven hours")
    doctor    the warning card for this theme: the sign in an alert box, an arrow, the phone and what to do

evidence() offers them to the variety director (variety.evidence) only in the elder theme; draw() renders one on the left of the frame (the scene's words stay
on the right as callouts, scenes.py). Times in a payload are absolute (seconds into the video); draw() gets the scene start to make them relative."""
from __future__ import annotations
import math, re
from typing import Callable, Dict, Optional

from PIL import Image, ImageDraw, ImageFilter

from . import draw as D, theme as T, lexicon as LX

KINDS = ("vitals", "pressure", "sugar", "body", "water", "sleep")      # side cards (the scene's words as callouts on the right); "doctor" draws the elder warning card
GOOD, MID, BAD = (92, 178, 120), (240, 188, 70), (226, 98, 82)      # the zone colours: healthy, borderline, high

HEART_RX = re.compile(r"\b(heart\s*(?:beats?|rate)|heartbeats?|pulse|beats?\s+per\s+minute|bpm|your heart|the heart)\b", re.I)
BP_RX = re.compile(r"\b(blood pressure|hypertension|systolic|diastolic)\b", re.I)
SUGAR_RX = re.compile(r"\b(blood sugar|glucose|diabet\w*|insulin|a1c)\b", re.I)
DOWN_RX = re.compile(r"\b(lowers?|lowered|lowering|drops?|dropped|reduces?|reduced|cuts?|falls?|eases?|calms?|steadies|steady|controls?|brings? (?:it )?down|improves?)\b", re.I)
UP_RX = re.compile(r"\b(raises?|rises?|rising|spikes?|spiking|jumps?|climbs?|increases?|high(?:er)?|soars?)\b", re.I)
WATER_RX = re.compile(r"\b(glass(?:es)?|cups?|litres?|liters?)\s+of\s+water\b|\bwater\b", re.I)
SLEEP_RX = re.compile(r"\b(sleep\w*|bed|rest)\b", re.I)
OVER_RX = re.compile(r"\b(\d{2,3})\s*(?:over|/)\s*(\d{2,3})\b", re.I)

ORGANS = {      # word -> organ key on the body map
    "heart": "heart", "brain": "brain", "memory": "brain", "mind": "brain", "lungs": "lungs", "lung": "lungs", "breathing": "lungs", "liver": "liver",
    "kidney": "kidneys", "kidneys": "kidneys", "stomach": "stomach", "gut": "gut", "intestine": "gut", "intestines": "gut", "colon": "gut", "digestion": "gut",
    "bladder": "bladder", "prostate": "bladder", "spine": "spine", "back": "spine", "hip": "hips", "hips": "hips", "knee": "knees", "knees": "knees",
    "joints": "knees", "joint": "knees", "bones": "bones", "bone": "bones", "eyes": "eyes", "eye": "eyes", "vision": "eyes", "thyroid": "thyroid", "arteries": "heart", "blood vessels": "heart",
}
ORGAN_RX = re.compile(r"\b(" + "|".join(sorted(ORGANS, key=len, reverse=True)) + r")\b", re.I)


def _elder() -> bool: return T.THEME == "elder"

def _number(text: str):
    """(value, unit words as said, char pos) of the first spoken quantity, or None."""
    m = re.search(rf"\b{LX.NUM}\b(\s+(?:[a-z]+)(?:\s+(?:a|per|each|every)\s+[a-z]+)?)?", text, re.I)
    if not m: return None
    try: v = float(LX.num(m.group(1)))
    except ValueError: return None
    return v, (m.group(2) or "").strip(), m.start()

def evidence(sc: dict, text: str, at: Callable[[dict, str, int], float]) -> Dict[str, tuple]:
    """look -> (support 0..1, payload) for the health cards this sentence can honestly show. Empty outside the elder theme."""
    if not _elder() or not text.strip(): return {}
    ev: Dict[str, tuple] = {}; low = text.lower(); num = _number(text)
    trend = "down" if DOWN_RX.search(text) else "up" if UP_RX.search(text) else ""
    tm = (DOWN_RX.search(text) or UP_RX.search(text)); trend_at = at(sc, text, tm.start()) if tm else None
    m = BP_RX.search(text)
    if m:
        o = OVER_RX.search(text)
        ev["pressure"] = (0.93, {"at": at(sc, text, m.start()), "trend": trend, "trend_at": trend_at, "sys": int(o.group(1)) if o else None, "dia": int(o.group(2)) if o else None,
                                 "label": m.group(1).upper()})
    m = SUGAR_RX.search(text)
    if m: ev["sugar"] = (0.93, {"at": at(sc, text, m.start()), "trend": trend or "up", "trend_at": trend_at, "label": m.group(1).upper(), "meal": bool(re.search(r"\b(eat\w*|meals?|food|lunch|dinner|breakfast|carbs?|sugar)\b", low))})
    m = HEART_RX.search(text)
    if m and "pressure" not in ev:
        bpm = int(num[0]) if num and re.search(r"beats?\s+(?:a|per)\s+minute|bpm", text, re.I) and 30 <= num[0] <= 200 else 72
        p = {"at": at(sc, text, m.start()), "bpm": bpm}
        if num and num[0] >= 10: p.update(value=num[0], unit=num[1].upper(), value_at=at(sc, text, num[2]))
        ev["vitals"] = (0.92 if num else 0.86, p)
    m = WATER_RX.search(text)
    if m and num and 1 <= num[0] <= 12 and re.search(r"glass|cup", num[1] + " " + m.group(0), re.I):
        ev["water"] = (0.92, {"at": at(sc, text, num[2]), "n": int(num[0]), "label": f"{int(num[0])} {('GLASSES' if 'glass' in (num[1] + m.group(0)).lower() else 'CUPS')}" if int(num[0]) != 1 else "1 GLASS"})
    m = SLEEP_RX.search(text)
    if m and num and 3 <= num[0] <= 12 and re.match(r"hours?", num[1], re.I):
        ev["sleep"] = (0.92, {"at": at(sc, text, num[2]), "hours": num[0]})
    m = ORGAN_RX.search(text)
    if m:
        key = ORGANS[m.group(1).lower()]
        ev["body"] = (0.8 if ev else 0.86, {"at": at(sc, text, m.start()), "organ": key, "label": m.group(1).upper()})
    return ev

def doctor_payload(text: str, rules: list) -> dict:
    """The elder warning card's words: the sign (the clause before the advice, from the sentence) and the rules the warning card found."""
    first = rules[0]["text"].lower() if rules else ""
    i = text.lower().find(first.split()[0]) if first else -1
    sign = text[:i].strip(" ,;:-") if i > 0 else ""
    return {"sign": sign.upper()[:60], "rules": rules}

# ---------------------------------------------------------------- drawing helpers

def _card(cv: Image.Image, ctx: D.Ctx, t: float, box=None) -> tuple:
    """The white health card on the left (soft shadow, teal edge), sliding in. Returns its box (x0, y0, x1, y1) in pixels."""
    e = T.ease_out(min(1.0, t / 0.5)); x0, y0, x1, y1 = box or (ctx.px(70), ctx.px(150), ctx.px(1050), ctx.px(930)); dx = int((1 - e) * -80 * ctx.S); x0 += dx; x1 += dx
    lay = Image.new("RGBA", (ctx.W, ctx.H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    d.rounded_rectangle((x0 + ctx.px(10), y0 + ctx.px(16), x1 + ctx.px(10), y1 + ctx.px(16)), radius=ctx.px(30), fill=(20, 40, 60, 60))
    lay = lay.filter(ImageFilter.GaussianBlur(ctx.px(12))); d = ImageDraw.Draw(lay)
    d.rounded_rectangle((x0, y0, x1, y1), radius=ctx.px(30), fill=(255, 255, 255, 255), outline=T.DIM + (255,), width=ctx.px(2))
    d.rounded_rectangle((x0, y0 + ctx.px(30), x0 + ctx.px(10), y1 - ctx.px(30)), radius=ctx.px(5), fill=T.ORANGE + (255,))
    D.overlay_paste(cv, lay, min(1.0, t / 0.3)); return x0, y0, x1, y1

def _label(d, ctx, xy, text, col=None, size=30, a=1.0, centre=False):
    f = ctx.font(T.BODY_FONT, size); w = D._text_w(d, text, f, ctx.px(3)); x = xy[0] - (w / 2 if centre else 0)
    D.text_spaced(d, (x, xy[1]), text, f, (col or T.ORANGE) + (int(255 * a),), ctx.px(3)); return w

def _big(d, ctx, xy, text, size, col, a=1.0, centre=True):
    f = ctx.font(T.HEAD_FONT, size); w = D._text_w(d, text, f, ctx.px(1)); D.text_spaced(d, (xy[0] - (w / 2 if centre else 0), xy[1]), text, f, col + (int(255 * a),), ctx.px(1)); return w

def _fmt(v: float) -> str: return f"{v:,.0f}" if v >= 1000 or float(v).is_integer() else f"{v:.1f}"

def _heart_pts(cx, cy, r, n=48):
    return [(cx + r * (16 * math.sin(a) ** 3) / 16, cy - r * (13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)) / 16) for a in (k * 2 * math.pi / n for k in range(n + 1))]

def _ecg(ph: float) -> float:
    """One heartbeat of an ECG, phase 0..1 -> height (-0.3..1): P wave, QRS spike, T wave."""
    ph %= 1.0; g = lambda c, w, h: h * math.exp(-((ph - c) / w) ** 2)
    return g(0.16, 0.035, 0.12) - g(0.29, 0.010, 0.18) + g(0.31, 0.012, 1.0) - g(0.335, 0.012, 0.32) + g(0.55, 0.06, 0.26)

def _rel(p: dict, k: str, t0: float):
    v = p.get(k); return None if v is None else float(v) - t0

# ---------------------------------------------------------------- the cards

def vitals(cv, ctx, p, t, t0):
    x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); bpm = p.get("bpm", 72); per = 60.0 / bpm
    sx0, sy0, sx1, sy1 = x0 + ctx.px(50), y0 + ctx.px(90), x1 - ctx.px(50), y0 + ctx.px(520)      # the monitor screen
    d.rounded_rectangle((sx0 - ctx.px(16), sy0 - ctx.px(16), sx1 + ctx.px(16), sy1 + ctx.px(16)), radius=ctx.px(26), fill=(196, 206, 214, 255))      # bezel
    d.rounded_rectangle((sx0, sy0, sx1, sy1), radius=ctx.px(16), fill=(14, 30, 44, 255))
    for gx in range(int(sx0), int(sx1), ctx.px(40)): d.line((gx, sy0, gx, sy1), fill=(30, 62, 74, 255), width=1)
    for gy in range(int(sy0), int(sy1), ctx.px(40)): d.line((sx0, gy, sx1, gy), fill=(30, 62, 74, 255), width=1)
    _label(d, ctx, (x0 + ctx.px(50), y0 + ctx.px(36)), "HEART RATE", size=28)
    tw = (sx1 - sx0) * 0.66; mid = sy0 + (sy1 - sy0) * 0.58; amp = (sy1 - sy0) * 0.36; SWEEP = 2.6; head = (t % SWEEP) / SWEEP; step = max(2, ctx.px(3))      # a bedside monitor: the trace is written left to right, the old one fades, a small gap runs ahead of the pen
    pts = []
    for k in range(int(tw / step) + 1):
        u = k * step / tw; age = ((head - u) % 1.0) * SWEEP; pts.append((sx0 + ctx.px(20) + u * tw, mid - _ecg((t - age) / per) * amp, age))
    for (xa, ya, aa), (xb, yb, ab) in zip(pts, pts[1:]):
        if aa > SWEEP * 0.94 or ab > SWEEP * 0.94 or abs(xb - xa) > ctx.px(20): continue
        al = int(255 * (1 - aa / SWEEP) ** 0.7); d.line((xa, ya, xb, yb), fill=(88, 236, 160, al), width=ctx.px(5))
    hx = sx0 + ctx.px(20) + head * tw; hy = mid - _ecg(t / per) * amp; d.ellipse((hx - ctx.px(9), hy - ctx.px(9), hx + ctx.px(9), hy + ctx.px(9)), fill=(220, 255, 230, 255))
    beat = math.exp(-((t % per) / 0.12) ** 2); cx, cy = sx1 - ctx.px(130), sy0 + ctx.px(120)      # the heart beats with the trace
    d.polygon(_heart_pts(cx, cy, ctx.px(52) * (1 + 0.16 * beat)), fill=(236, 92, 96, 255))
    _big(d, ctx, (cx, sy0 + ctx.px(200)), str(bpm), 92, (88, 236, 160)); _label(d, ctx, (cx, sy0 + ctx.px(310)), "BPM", (150, 220, 190), 26, centre=True)
    if p.get("value") is not None:      # the number the sentence says, rolling up under the monitor
        va = _rel(p, "value_at", t0) or 0.0; q = T.ease_in_out(min(1.0, max(0.0, (t - va) / 1.4))); a = min(1.0, max(0.0, (t - va + 0.2) / 0.3))
        if a > 0:
            cxm = (x0 + x1) / 2; _big(d, ctx, (cxm, sy1 + ctx.px(50)), _fmt(p["value"] * q), 120, T.WHITE, a)
            if p.get("unit"): _label(d, ctx, (cxm, sy1 + ctx.px(200)), p["unit"], T.SOFT_WHITE, 34, a, centre=True)
    else: _label(d, ctx, ((x0 + x1) / 2, sy1 + ctx.px(110)), "STEADY  ·  STRONG", T.GREEN, 34, min(1.0, max(0.0, t - 0.8)), centre=True)

def pressure(cv, ctx, p, t, t0):
    x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); cx, cy, r = (x0 + x1) / 2 + ctx.px(60), y0 + ctx.px(430), ctx.px(250)
    _label(d, ctx, (x0 + ctx.px(50), y0 + ctx.px(36)), p.get("label", "BLOOD PRESSURE"), size=28)
    d.ellipse((cx - r - ctx.px(22), cy - r - ctx.px(22), cx + r + ctx.px(22), cy + r + ctx.px(22)), fill=(226, 232, 236, 255))      # the gauge's metal rim
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(252, 253, 253, 255), outline=(170, 180, 188, 255), width=ctx.px(3))
    A0, A1 = 150, 390      # the scale runs from lower left round to lower right
    for a0, a1, col in ((A0, 270, GOOD), (270, 320, MID), (320, A1, BAD)): d.arc((cx - r * 0.86, cy - r * 0.86, cx + r * 0.86, cy + r * 0.86), a0, a1, fill=col + (255,), width=ctx.px(26))
    for k in range(13):
        a = math.radians(A0 + (A1 - A0) * k / 12); r0 = r * (0.66 if k % 2 == 0 else 0.7); d.line((cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r * 0.74 * math.cos(a), cy + r * 0.74 * math.sin(a)), fill=(80, 96, 116, 255), width=ctx.px(3))
    for txt, frac, col in (("NORMAL", 0.12, GOOD), ("HIGH", 0.9, BAD)):      # under the scale's two ends, clear of the needle
        a = math.radians(A0 + (A1 - A0) * frac); _label(d, ctx, (cx + r * 0.5 * math.cos(a), cy + r * 0.5 * math.sin(a) + ctx.px(14)), txt, col, 22, centre=True)
    hi, ok = 0.86, 0.36; trend = p.get("trend"); ta = _rel(p, "trend_at", t0)
    if trend == "down": frm, to = hi, ok
    elif trend == "up": frm, to = ok, hi
    else: frm, to = 0.0, ok
    k = T.ease_in_out(min(1.0, max(0.0, (t - (ta if ta is not None else 0.6)) / 1.2))) if trend else T.ease_back(min(1.0, max(0.0, (t - 0.4) / 1.0)))
    v = frm + (to - frm) * k + 0.008 * math.sin(t * 9); a = math.radians(A0 + (A1 - A0) * v)
    d.line((cx, cy, cx + r * 0.78 * math.cos(a), cy + r * 0.78 * math.sin(a)), fill=(28, 44, 70, 255), width=ctx.px(8)); d.ellipse((cx - ctx.px(22), cy - ctx.px(22), cx + ctx.px(22), cy + ctx.px(22)), fill=(28, 44, 70, 255))
    if trend: _big(d, ctx, (cx, cy + ctx.px(70)), "↓" if trend == "down" else "↑", 90, GOOD if trend == "down" else BAD, min(1.0, max(0.0, (t - (ta or 0)) / 0.4)))
    bx, by = x0 + ctx.px(120), y1 - ctx.px(150)      # the pump bulb and the cuff tube running to the gauge
    d.line([(bx + ctx.px(40), by - ctx.px(30)), (bx + ctx.px(60), cy + r * 0.2), (cx - r * 0.9, cy + r * 0.55)], fill=(60, 70, 84, 255), width=ctx.px(8), joint="curve")
    sq = 1 + 0.08 * math.sin(t * 5) * (1 if t < 2.5 else 0); d.ellipse((bx - ctx.px(55) * sq, by - ctx.px(70), bx + ctx.px(55) * sq, by + ctx.px(50)), fill=(40, 52, 66, 255))
    if p.get("sys"):
        _big(d, ctx, ((x0 + x1) / 2, y1 - ctx.px(130)), f"{p['sys']}/{p['dia']}", 86, T.WHITE, min(1.0, max(0.0, (t - 0.6) / 0.4)))

def sugar(cv, ctx, p, t, t0):
    x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); _label(d, ctx, (x0 + ctx.px(50), y0 + ctx.px(36)), p.get("label", "BLOOD SUGAR"), size=28)
    gx0, gy0, gx1, gy1 = x0 + ctx.px(300), y0 + ctx.px(130), x1 - ctx.px(50), y1 - ctx.px(110)      # the chart
    d.line((gx0, gy1, gx1, gy1), fill=(150, 160, 170, 255), width=ctx.px(3)); d.line((gx0, gy0, gx0, gy1), fill=(150, 160, 170, 255), width=ctx.px(3))
    band = (gy0 + (gy1 - gy0) * 0.45, gy0 + (gy1 - gy0) * 0.75); d.rectangle((gx0 + ctx.px(3), band[0], gx1, band[1]), fill=GOOD + (40,))      # the healthy range
    spike = lambda u: 0.62 - 0.55 * math.exp(-((u - 0.42) / 0.16) ** 2)      # after a meal: up, then slowly down
    calm = lambda u: 0.62 - 0.22 * math.exp(-((u - 0.40) / 0.18) ** 2)      # with the habit: a much smaller rise
    def path(f, frac): return [(gx0 + (gx1 - gx0) * u, gy0 + (gy1 - gy0) * f(u)) for u in (k / 60 * frac for k in range(61))]
    pa = min(1.0, max(0.0, (t - 0.3) / 1.6)); pts = path(spike, pa)
    if len(pts) > 1: d.line(pts, fill=BAD + (255 if p.get("trend") != "down" else 150,), width=ctx.px(7), joint="curve")
    if p.get("meal"):      # the meal: a plate with a fork at the start of the rise
        mx, my = gx0 + (gx1 - gx0) * 0.18, gy1 - ctx.px(46); d.ellipse((mx - ctx.px(30), my - ctx.px(14), mx + ctx.px(30), my + ctx.px(14)), outline=(120, 130, 140, 255), width=ctx.px(4)); d.line((mx + ctx.px(44), my - ctx.px(24), mx + ctx.px(44), my + ctx.px(20)), fill=(120, 130, 140, 255), width=ctx.px(4))
    if p.get("trend") == "down":
        ta = _rel(p, "trend_at", t0) or 1.0; q = min(1.0, max(0.0, (t - ta) / 1.4)); cp = path(calm, q)
        if len(cp) > 1: d.line(cp, fill=GOOD + (255,), width=ctx.px(9), joint="curve")
        if q > 0.5:
            ax = gx0 + (gx1 - gx0) * 0.42; d.line((ax, gy0 + (gy1 - gy0) * spike(0.42) + ctx.px(20), ax, gy0 + (gy1 - gy0) * calm(0.42) - ctx.px(24)), fill=GOOD + (255,), width=ctx.px(6))
            d.polygon([(ax - ctx.px(18), gy0 + (gy1 - gy0) * calm(0.42) - ctx.px(40)), (ax + ctx.px(18), gy0 + (gy1 - gy0) * calm(0.42) - ctx.px(40)), (ax, gy0 + (gy1 - gy0) * calm(0.42) - ctx.px(14))], fill=GOOD + (255,))
    mx0, my0 = x0 + ctx.px(60), y0 + ctx.px(170); mw, mh = ctx.px(190), ctx.px(330)      # the meter
    d.rounded_rectangle((mx0, my0, mx0 + mw, my0 + mh), radius=ctx.px(40), fill=(64, 84, 108, 255)); d.rounded_rectangle((mx0 + ctx.px(22), my0 + ctx.px(36), mx0 + mw - ctx.px(22), my0 + ctx.px(170)), radius=ctx.px(14), fill=(206, 236, 222, 255))
    d.rounded_rectangle((mx0 + mw / 2 - ctx.px(18), my0 + mh, mx0 + mw / 2 + ctx.px(18), my0 + mh + ctx.px(70)), radius=ctx.px(6), fill=(236, 236, 236, 255))      # the test strip
    hi, lo = 182, 128; down = p.get("trend") == "down"; ta = _rel(p, "trend_at", t0) or 1.0
    reading = (hi * min(1.0, pa * 1.6)) if not down or t < ta else hi + (lo - hi) * T.ease_in_out(min(1.0, (t - ta) / 1.2))
    _big(d, ctx, (mx0 + mw / 2, my0 + ctx.px(56)), f"{reading:.0f}", 66, (28, 44, 70)); _label(d, ctx, (mx0 + mw / 2, my0 + ctx.px(136)), "mg/dL", (60, 90, 80), 18, centre=True)
    for k in range(2): d.ellipse((mx0 + ctx.px(50) + k * ctx.px(60), my0 + ctx.px(220), mx0 + ctx.px(80) + k * ctx.px(60), my0 + ctx.px(250)), fill=(150, 170, 190, 255))

# the body map: positions as fractions of the body's height, x measured from the body's centre line
_OUTLINE_LEGS = (((-0.08, 0.58), (-0.07, 0.97)), ((0.08, 0.58), (0.07, 0.97)))
ORGAN_DRAW = {
    "brain": ("ell", (0.0, 0.075, 0.065, 0.045)), "eyes": ("dots", ((-0.028, 0.095), (0.028, 0.095), 0.012)), "thyroid": ("ell", (0.0, 0.16, 0.03, 0.012)),
    "lungs": ("pair", (0.07, 0.27, 0.06, 0.09)), "heart": ("heart", (0.03, 0.285, 0.04)), "liver": ("ell", (-0.06, 0.37, 0.085, 0.042)),
    "stomach": ("ell", (0.06, 0.375, 0.055, 0.04)), "kidneys": ("pair", (0.07, 0.43, 0.026, 0.04)), "gut": ("gut", (0.0, 0.475, 0.08, 0.055)),
    "bladder": ("ell", (0.0, 0.55, 0.03, 0.025)), "spine": ("spine", (0.0, 0.17, 0.56)), "hips": ("pair", (0.075, 0.565, 0.04, 0.03)),
    "knees": ("pair", (0.075, 0.76, 0.03, 0.03)), "bones": ("bones", None),
}

def _organ(d, kind, spec, cx, top, h, fill, outline, w, grow=1.0):
    X = lambda fx: cx + fx * h; Y = lambda fy: top + fy * h
    if kind == "ell":
        x, y, rx, ry = spec; d.ellipse((X(x - rx * grow), Y(y - ry * grow), X(x + rx * grow), Y(y + ry * grow)), fill=fill, outline=outline, width=w)
    elif kind == "pair":
        x, y, rx, ry = spec
        for sx in (-1, 1): d.ellipse((X(sx * x - rx * grow), Y(y - ry * grow), X(sx * x + rx * grow), Y(y + ry * grow)), fill=fill, outline=outline, width=w)
    elif kind == "dots":
        a, b, r = spec
        for x, y in (a, b): d.ellipse((X(x - r * grow), Y(y - r * grow), X(x + r * grow), Y(y + r * grow)), fill=fill, outline=outline, width=w)
    elif kind == "heart":
        x, y, r = spec; pts = _heart_pts(X(x), Y(y), r * h * grow); d.polygon(pts, fill=fill); d.line(pts, fill=outline, width=w) if outline else None
    elif kind == "gut":
        x, y, rx, ry = spec; pts = [(X(x + rx * grow * math.sin(k * 0.55) * (1 - k / 40)), Y(y - ry + 2 * ry * k / 28 * grow)) for k in range(29)]
        d.rounded_rectangle((X(x - rx * grow), Y(y - ry * grow), X(x + rx * grow), Y(y + ry * grow)), radius=int(ry * h * 0.6), fill=fill, outline=outline, width=w)
        d.line(pts, fill=(outline or fill), width=max(2, w))
    elif kind == "spine":
        x, y0, y1 = spec
        for k in range(14): yy = y0 + (y1 - y0) * k / 13; d.rounded_rectangle((X(x - 0.014 * grow), Y(yy - 0.011), X(x + 0.014 * grow), Y(yy + 0.011)), radius=max(1, int(h * 0.006)), fill=fill, outline=outline, width=1 if h < 600 else max(1, w // 2))
    elif kind == "bones":
        for k2 in ("spine", "hips", "knees"): kk, sp = ORGAN_DRAW[k2]; _organ(d, kk, sp, cx, top, h, fill, outline, w, grow)

def body(cv, ctx, p, t, t0):
    x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); h = (y1 - y0) - ctx.px(120); top = y0 + ctx.px(60); cx = x0 + (x1 - x0) * 0.40
    sil, edge = (212, 230, 232, 255), (160, 196, 200, 255); X = lambda fx: cx + fx * h; Y = lambda fy: top + fy * h; lw = int(h * 0.075)
    for (a, b) in _OUTLINE_LEGS: d.line((X(a[0]), Y(a[1]), X(b[0]), Y(b[1])), fill=sil, width=lw)      # legs
    for sx in (-1, 1): d.line([(X(sx * 0.15), Y(0.2)), (X(sx * 0.2), Y(0.38)), (X(sx * 0.22), Y(0.55))], fill=sil, width=int(h * 0.05), joint="curve")      # arms
    d.polygon([(X(-0.16), Y(0.18)), (X(0.16), Y(0.18)), (X(0.12), Y(0.42)), (X(0.13), Y(0.6)), (X(-0.13), Y(0.6)), (X(-0.12), Y(0.42))], fill=sil)      # torso
    d.rounded_rectangle((X(-0.03), Y(0.13), X(0.03), Y(0.19)), radius=4, fill=sil); d.ellipse((X(-0.065), Y(0.02), X(0.065), Y(0.155)), fill=sil)      # neck, head
    for k2, (kind, spec) in ORGAN_DRAW.items():      # every organ as a faint outline: the body reads as a body
        if k2 in ("bones", "eyes", "thyroid"): continue
        _organ(d, kind, spec, cx, top, h, None if kind != "spine" else (226, 238, 240, 255), edge, max(1, ctx.px(2)))
    key = p.get("organ", "heart"); kind, spec = ORGAN_DRAW.get(key, ORGAN_DRAW["heart"]); a = min(1.0, max(0.0, (t - (_rel(p, "at", t0) or 0) + 0.3) / 0.5))
    sy = top + h * min(1.0, t / 1.2)      # the scan line runs down the body once
    if t < 1.3: d.rectangle((X(-0.3), sy - ctx.px(3), X(0.3), sy + ctx.px(3)), fill=T.ORANGE + (160,)); d.rectangle((X(-0.3), sy - ctx.px(40), X(0.3), sy), fill=T.ORANGE + (26,))
    if a > 0:
        pulse = 1 + 0.08 * math.sin(t * (7.5 if key == "heart" else 3.5))
        for k in range(3):      # glow rings spreading out from the organ
            ph = (t * 0.8 + k / 3) % 1.0; gl = Image.new("RGBA", cv.size, (0, 0, 0, 0)); _organ(ImageDraw.Draw(gl), kind, spec, cx, top, h, None, (236, 92, 96, int(150 * (1 - ph) * a)), ctx.px(4), 1.0 + ph * 0.9); cv.alpha_composite(gl) if cv.mode == "RGBA" else cv.paste(gl, (0, 0), gl)
        d = ImageDraw.Draw(cv, "RGBA"); _organ(d, kind, spec, cx, top, h, (236, 104, 100, int(255 * a)), (180, 50, 60, int(255 * a)), ctx.px(3), pulse)
        if kind in ("ell", "heart", "gut"): ox, oy = X(spec[0]), Y(spec[1])
        elif kind == "pair": ox, oy = X(spec[0]), Y(spec[1])
        elif kind == "dots": ox, oy = X(spec[1][0]), Y(spec[1][1])
        elif kind == "spine": ox, oy = X(0.015), Y(0.36)
        else: ox, oy = X(0.075), Y(0.76)
        lx = x0 + (x1 - x0) * 0.72; ly = oy; q = T.ease_out(min(1.0, max(0.0, (t - (_rel(p, "at", t0) or 0) - 0.2) / 0.4)))      # the label on a leader line
        d.line((ox, oy, ox + (lx - ox) * q, ly), fill=T.WHITE + (255,), width=ctx.px(3)); d.ellipse((ox - ctx.px(8), oy - ctx.px(8), ox + ctx.px(8), oy + ctx.px(8)), fill=T.WHITE + (255,))
        if q >= 1:
            f = ctx.font(T.HEAD_FONT, 44); w = D._text_w(d, p.get("label", key.upper()), f, ctx.px(1)); d.rounded_rectangle((lx, ly - ctx.px(36), lx + w + ctx.px(44), ly + ctx.px(36)), radius=ctx.px(36), fill=(236, 92, 96, 255))
            D.text_spaced(d, (lx + ctx.px(22), ly - ctx.px(28)), p.get("label", key.upper()), f, (255, 255, 255, 255), ctx.px(1))

def water(cv, ctx, p, t, t0):
    x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); n = max(1, min(12, int(p.get("n", 6)))); cols = n if n <= 6 else math.ceil(n / 2); rows = 1 if n <= 6 else 2
    gw = min(ctx.px(120), (x1 - x0 - ctx.px(120)) / cols - ctx.px(20)); gh = gw * 1.45; gap = ctx.px(20); sx = (x0 + x1) / 2 - (cols * gw + (cols - 1) * gap) / 2
    sy = y0 + ctx.px(140) if rows == 2 else y0 + ctx.px(220); at = _rel(p, "at", t0) or 0.0
    for i in range(n):
        r, c = divmod(i, cols); gx, gy = sx + c * (gw + gap), sy + r * (gh + ctx.px(50)); f = T.ease_in_out(min(1.0, max(0.0, (t - at - i * 0.22) / 0.5)))
        top, bot = (gx, gy, gx + gw, gy), (gx + gw * 0.12, gy + gh, gx + gw * 0.88, gy + gh)
        if f > 0:
            lvl = gy + gh - (gh * 0.82) * f; pts = [(gx + gw * 0.12 * (1 - (lvl - gy) / gh) + (gw * (1 - 0.24 * (lvl - gy) / gh)) * k / 16, lvl + ctx.px(4) * math.sin(t * 6 + k * 0.8 + i)) for k in range(17)]
            d.polygon(pts + [(bot[2], bot[3]), (bot[0], bot[1])], fill=(110, 186, 236, 220))
        d.line([(top[0], top[1]), (bot[0], bot[1]), (bot[2], bot[3]), (top[2], top[3])], fill=(90, 120, 150, 255), width=ctx.px(5), joint="curve")
        d.line((gx + gw * 0.2, gy + gh * 0.15, gx + gw * 0.26, gy + gh * 0.8), fill=(255, 255, 255, 170), width=ctx.px(5))
    done = n * 0.22 + 0.5; a = min(1.0, max(0.0, (t - at - done * 0.6) / 0.4))
    if a > 0: _big(d, ctx, ((x0 + x1) / 2, y1 - ctx.px(190)), p.get("label", f"{n} GLASSES"), 96, T.WHITE, a)

def sleep(cv, ctx, p, t, t0):
    x0, y0, x1, y1 = _card(cv, ctx, t); d = ImageDraw.Draw(cv, "RGBA"); cx, cy, r = (x0 + x1) / 2, y0 + ctx.px(330), ctx.px(225)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(30, 40, 78, 255))      # the night dial
    for k in range(12): a = math.radians(-90 + 30 * k); d.line((cx + r * 0.84 * math.cos(a), cy + r * 0.84 * math.sin(a), cx + r * 0.94 * math.cos(a), cy + r * 0.94 * math.sin(a)), fill=(180, 190, 230, 255), width=ctx.px(4))
    hrs = float(p.get("hours", 7)); at = _rel(p, "at", t0) or 0.0; q = T.ease_in_out(min(1.0, max(0.0, (t - at) / 1.6))); start = -90 + 30 * 10      # from 10 o'clock round
    if q > 0: d.arc((cx - r * 0.72, cy - r * 0.72, cx + r * 0.72, cy + r * 0.72), start, start + 30 * hrs * q, fill=(150, 140, 240, 255), width=ctx.px(40))
    mx, my, mr = cx, cy - ctx.px(10), ctx.px(70); d.ellipse((mx - mr, my - mr, mx + mr, my + mr), fill=(255, 226, 140, 255)); d.ellipse((mx - mr * 0.5, my - mr * 1.15, mx + mr * 1.35, my + mr * 0.6), fill=(30, 40, 78, 255))      # the moon
    for k in range(6): sx_, sy_ = cx + r * 0.5 * math.cos(k * 1.7), cy + r * 0.5 * math.sin(k * 2.3); tw = 0.5 + 0.5 * math.sin(t * 3 + k); d.ellipse((sx_ - ctx.px(4) * tw, sy_ - ctx.px(4) * tw, sx_ + ctx.px(4) * tw, sy_ + ctx.px(4) * tw), fill=(255, 255, 255, 230))
    if q > 0.3: _big(d, ctx, (cx, y1 - ctx.px(170)), f"{_fmt(hrs * min(1.0, q * 1.2))} HOURS", 96, T.WHITE, min(1.0, (q - 0.3) / 0.3))

def doctor(cv, ctx, p, t, t0):
    """The elder warning card (full frame): the sign in a coral alert box, an arrow down, then a ringing phone and what to do in a teal box."""
    d = ImageDraw.Draw(cv, "RGBA"); W, H = ctx.W, ctx.H; rules = p.get("rules") or []; sign = p.get("sign", "")
    a1 = T.ease_back(min(1.0, max(0.0, t / 0.5))); bx0, bx1 = int(W * 0.12), int(W * 0.88)
    if sign and a1 > 0:
        y = int(H * 0.16); h = ctx.px(170); d.rounded_rectangle((bx0, y, bx1, y + h), radius=ctx.px(28), fill=(255, 236, 232, int(255 * min(1, a1))), outline=BAD + (255,), width=ctx.px(5))
        tx, ty, s = bx0 + ctx.px(90), y + h / 2, ctx.px(52)      # the alert triangle
        d.polygon([(tx, ty - s), (tx + s * 1.05, ty + s * 0.8), (tx - s * 1.05, ty + s * 0.8)], fill=BAD + (255,)); _big(d, ctx, (tx, ty - s * 0.55), "!", 70, (255, 255, 255))
        f = ctx.font(T.HEAD_FONT, 56); lines = D._wrap(d, sign, f, bx1 - bx0 - ctx.px(240)) or [sign]
        for i, ln in enumerate(lines[:2]): D.text_spaced(d, (bx0 + ctx.px(190), y + h / 2 - len(lines[:2]) * ctx.px(34) + i * ctx.px(68)), ln, f, (150, 40, 34, 255), ctx.px(1))
    rule = rules[0] if rules else None
    if rule:
        ra = float(rule["at"]) - t0; q = T.ease_out(min(1.0, max(0.0, (t - ra) / 0.5)))
        ay0, ay1 = int(H * 0.16) + ctx.px(190), int(H * 0.47)
        if q > 0:
            d.line((W / 2, ay0, W / 2, ay0 + (ay1 - ay0 - ctx.px(30)) * q), fill=(28, 44, 70, 255), width=ctx.px(8))
            if q >= 1: d.polygon([(W / 2 - ctx.px(26), ay1 - ctx.px(36)), (W / 2 + ctx.px(26), ay1 - ctx.px(36)), (W / 2, ay1)], fill=(28, 44, 70, 255))
            y = int(H * 0.50); h = ctx.px(250); d.rounded_rectangle((bx0, y, bx1, y + h), radius=ctx.px(28), fill=(226, 244, 242, int(255 * q)), outline=T.ORANGE + (255,), width=ctx.px(5))
            px_, py_ = bx0 + ctx.px(130), y + h / 2; shake = math.sin(t * 40) * ctx.px(4) if (t - ra) % 1.2 < 0.6 else 0      # the phone rings
            for k in range(3):
                rr = ctx.px(60 + 26 * k); ph = ((t * 1.5) + k / 3) % 1.0; d.arc((px_ - rr, py_ - rr, px_ + rr, py_ + rr), -60, 60, fill=T.ORANGE + (int(220 * (1 - ph)),), width=ctx.px(6))
            d.rounded_rectangle((px_ - ctx.px(38) + shake, py_ - ctx.px(68), px_ + ctx.px(38) + shake, py_ + ctx.px(68)), radius=ctx.px(14), fill=(28, 44, 70, 255))
            d.rounded_rectangle((px_ - ctx.px(28) + shake, py_ - ctx.px(52), px_ + ctx.px(28) + shake, py_ + ctx.px(42)), radius=ctx.px(6), fill=(140, 220, 210, 255)); D.plus(d, px_ + shake, py_ - ctx.px(6), ctx.px(18), BAD + (255,))
            f = ctx.font(T.HEAD_FONT, 64); lines = D._wrap(d, rule["text"], f, bx1 - bx0 - ctx.px(300)) or [rule["text"]]
            for i, ln in enumerate(lines[:2]): D.text_spaced(d, (bx0 + ctx.px(260), y + h / 2 - len(lines[:2]) * ctx.px(40) + i * ctx.px(80)), ln, f, T.WHITE + (int(255 * q),), ctx.px(1))

DRAW = {"vitals": vitals, "pressure": pressure, "sugar": sugar, "body": body, "water": water, "sleep": sleep, "doctor": doctor}

def draw(cv: Image.Image, ctx: D.Ctx, kind: str, payload: dict, t: float, t0: float) -> None:
    """One health card for time t (seconds into the scene); t0 = the scene's start (payload times are absolute)."""
    DRAW[kind](cv, ctx, payload, t, t0)
