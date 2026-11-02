"""On-picture tricks (docs/rep_theory/PLAN_NEXT_GRAPHICS.md, Phase 4): small drawn touches put on the pictures we already show, each read from the sentence's own words:
  strike   "A planche isn't a strength trick" -> "STRENGTH TRICK?" written over the picture, struck out in red on the next clause ("it's a lever")
  bubble   "your body says stop", "your brain screams more", a quoted word -> a speech bubble popping up with that word
  aside    "(stupid easy)", "trust me", "no joke", "seriously" -> a handwritten aside with a drawn arrow pointing at the subject
  measure  "167 cm", "65 kg", "5 foot 6" -> a height bracket beside the subject and / or a weight tag, each on its word
  hazard   the first scene of a warning (a warning section, or "careful / danger / injury / tear" said) -> hazard tape sliding across the frame, then away
One top trick per scene (strike, else bubble, else aside); measurements and hazard tape sit apart and can join it. Never on the cards that fill the frame.
Times in the overlay dicts are absolute; draw() takes the absolute time."""
from __future__ import annotations
import math, re
from typing import Dict, List, Optional

from PIL import Image, ImageDraw

from . import draw as D, meters as M, narrative as N, theme as T

PICTURE_KINDS = {"illus", "pose", "trainee", "callout", "prop", "hold", "sketch", "anatomy"}
OVERLAYS = ("strike", "bubble", "aside", "measure", "hazard")
HAND_FONT = "ChalkboardSE.ttc"
YELLOW = (255, 214, 64)

NOT_RX = re.compile(r"\b(?:isn'?t|is\s+not|it'?s\s+not|aren'?t|are\s+not)\s+(?:just\s+|really\s+|actually\s+|only\s+)?(?:a\s+|an\s+|about\s+)([A-Za-z][\w'-]*(?:\s+[A-Za-z][\w'-]*){0,2})", re.I)
TURN_RX = re.compile(r"\b(it'?s|it\s+is|they'?re|but|instead|rather)\b", re.I)
SAY_RX = re.compile(r"\b(?:says?|said|tells?\s+you|yells?|shouts?|screams?|whispers?|begs?(?:\s+for)?)\b\s*[:,]?\s*[\"“']?([A-Za-z][\w'-]*(?:\s+[A-Za-z][\w'-]*){0,2})", re.I)
QUOTE_RX = re.compile(r"[\"“]([^\"”]{2,24})[\"”]")
ASIDE_RX = re.compile(r"\(([^)]{2,24})\)|\b(trust\s+me|no\s+joke|seriously|i\s+promise|not\s+a\s+typo|stupid(?:ly)?\s+easy|dead\s+simple|that'?s\s+it)\b", re.I)
MEAS_RX = re.compile(r"\b(\d{1,3}(?:[.,]\d)?)\s*(cm|centimet(?:er|re)s?|kg|kilos?|kilograms?|lbs?|pounds?|inch(?:es)?|foot|feet|ft|m|met(?:er|re)s?)\b(?:\s*(\d{1,2})\b)?", re.I)
WARN_RX = re.compile(r"\b(careful|danger(?:ous)?|injur(?:y|ies|ed)|tears?|torn|snap(?:s|ped)?|risk(?:y|s)?|warning|hurts?|pain)\b", re.I)
HEIGHT = ("cm", "cent", "inch", "foot", "feet", "ft", "m", "met")
HAZARD_GAP_S = 30.0

def _upper(s: str, n: int = 3) -> str:
    ws = [w for w in re.findall(r"[A-Za-z][\w'-]*", s)][:n]
    while ws and ws[-1].lower() in N.STOP: ws.pop()
    return " ".join(ws).upper()

def strike(sc: dict, text: str) -> Optional[dict]:
    m = NOT_RX.search(text)
    if not m: return None
    raw = m.group(1).lower().split()
    if any(w in ("where", "that", "which", "who", "when", "you", "to", "for", "of") for w in raw[1:]): return None      # "isn't a place where you ..." is a clause, not a claim to strike
    ph = _upper(m.group(1))
    if not ph or ph.lower() in N.STOP or len(ph) > 22: return None
    at = M._at(sc, m.start(1)); t2 = TURN_RX.search(text, m.end()); s_at = M._at(sc, t2.start()) if t2 else at + 1.0
    return {"text": ph + "?", "at": at, "strike_at": min(max(at + 0.6, s_at), float(sc["end"]) - 0.5)}      # the answer may fall in the next scene: struck before this one ends

def bubble(sc: dict, text: str) -> Optional[dict]:
    m = QUOTE_RX.search(text) or SAY_RX.search(text)
    if not m: return None
    first = m.group(1).split()[0].lower()
    if first in N.STOP or first in ("to", "that", "it"): return None      # reported speech ("tells you to eat more") is not a line said
    w = _upper(m.group(1), 3)
    if not w or w.lower() in N.STOP or w.lower() in ("that", "this", "it", "so"): return None
    return {"text": w.rstrip("!?.") + "!", "at": M._at(sc, m.start(1))}

def aside(sc: dict, text: str) -> Optional[dict]:
    m = ASIDE_RX.search(text)
    if not m: return None
    return {"text": "(" + (m.group(1) or m.group(2)).lower().strip() + ")", "at": M._at(sc, m.start())}

def measure(sc: dict, text: str) -> Optional[dict]:
    out = {}
    for m in MEAS_RX.finditer(text):
        u = m.group(2).lower(); h = u.startswith(HEIGHT) and not u.startswith("min")
        if u == "m" and float(m.group(1).replace(",", ".")) > 3: continue      # "30 m" is a distance, not a height
        lab = f"{m.group(1)} {'FT' if u in ('foot', 'feet', 'ft') else 'IN' if u.startswith('inch') else 'CM' if u.startswith('c') else 'M' if u.startswith('m') else 'KG' if u.startswith('k') else 'LB'}" + (f" {m.group(3)} IN" if m.group(3) and u in ("foot", "feet", "ft") else "")
        k = "height" if h else "weight"
        if k not in out: out[k] = {"text": lab, "at": M._at(sc, m.start())}
    return out or None

def plan(scenes: List[dict]) -> Dict[str, int]:
    """Puts the tricks on the picture scenes (in place). Returns counts per trick."""
    n = {k: 0 for k in OVERLAYS}; last_hazard = -1e9
    for sc in scenes:
        text = sc.get("text", "")
        if not text.strip(): continue
        pic = sc["kind"] in PICTURE_KINDS or sc.get("look") == "flow"
        warn = sc.get("section_kind") == "warning" or WARN_RX.search(text)
        if warn and pic and float(sc["start"]) - last_hazard >= HAZARD_GAP_S:
            sc["hazard"] = {"at": float(sc["start"]) + 0.15}; last_hazard = float(sc["start"]); n["hazard"] += 1
        if not pic: continue
        for k, fn in (("strike", strike), ("bubble", bubble), ("aside", aside)):
            got = fn(sc, text)
            if got and got["at"] < float(sc["end"]) - 0.6: sc[k] = got; n[k] += 1; break
        ms = measure(sc, text)
        if ms: sc["measure"] = ms; n["measure"] += 1
    return n

def marks(sc: dict) -> List[float]:
    """When something new lands from the tricks on this scene (cadence)."""
    out = []
    if sc.get("strike"): out += [sc["strike"]["at"], sc["strike"]["strike_at"]]
    for k in ("bubble", "aside", "hazard"):
        if sc.get(k): out.append(sc[k]["at"])
    for v in (sc.get("measure") or {}).values(): out.append(v["at"])
    return out

# ------------------------------------------------------------------ drawing (absolute time)
def _p(t: float, at: float, dur: float = 0.35) -> float: return min(1.0, max(0.0, (t - at) / dur))

def _rot_text(cv, ctx, xy, text, font, fill, angle):
    d0 = ImageDraw.Draw(cv); w = int(d0.textlength(text, font=font)) + ctx.px(20); h = int(font.size * 1.5)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); ImageDraw.Draw(im).text((ctx.px(10), 0), text, font=font, fill=fill)
    im = im.rotate(angle, expand=True, resample=Image.BICUBIC); cv.paste(im, (int(xy[0] - im.width / 2), int(xy[1] - im.height / 2)), im)

def draw_strike(cv, ctx, c, t):
    a = _p(t, c["at"] - 0.1); s = _p(t, c["strike_at"], 0.3); fade = 1 - _p(t, c["strike_at"] + 1.1, 0.4)
    if a <= 0 or fade <= 0: return
    d = ImageDraw.Draw(cv, "RGBA"); f = ctx.font(T.HEAD_FONT, 84 if len(c["text"]) < 14 else 64); w = D._text_w(d, c["text"], f, ctx.px(2)); x, y = (ctx.W - w) / 2, ctx.H * 0.09
    d.rounded_rectangle((x - ctx.px(30), y - ctx.px(14), x + w + ctx.px(30), y + f.size * 1.25), radius=ctx.px(16), fill=(14, 14, 16, int(200 * a * fade)))
    D.text_spaced(d, (x, y), c["text"], f, T.WHITE + (int(255 * a * fade),), ctx.px(2))
    if s > 0:
        yl = y + f.size * 0.62; d.line((x - ctx.px(16), yl + ctx.px(8), x - ctx.px(16) + (w + ctx.px(32)) * T.ease_out(s), yl - ctx.px(8) * s), fill=T.RED + (int(255 * fade),), width=ctx.px(12))

def draw_bubble(cv, ctx, c, t):
    q = T.ease_back(_p(t, c["at"], 0.35))
    if q <= 0: return
    d = ImageDraw.Draw(cv, "RGBA"); f = ctx.font(T.HEAD_FONT, int(64 * min(1.0, q) + 1)); w = D._text_w(d, c["text"], f, ctx.px(1)); cx, cy = ctx.W * 0.46, ctx.H * 0.16
    bw, bh = (w + ctx.px(70)) * q, (f.size + ctx.px(50)) * q
    d.rounded_rectangle((cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2), radius=int(bh / 2), fill=(250, 250, 248, 255), outline=(20, 20, 22, 255), width=ctx.px(4))
    d.polygon([(cx - bw * 0.15, cy + bh / 2 - ctx.px(4)), (cx - bw * 0.02, cy + bh / 2 - ctx.px(4)), (cx - bw * 0.22, cy + bh / 2 + ctx.px(46) * q)], fill=(250, 250, 248, 255))
    if q > 0.6: D.text_spaced(d, (cx - w / 2, cy - f.size * 0.62), c["text"], f, (20, 20, 22, 255), ctx.px(1))

def draw_aside(cv, ctx, c, t):
    a = _p(t, c["at"], 0.3)
    if a <= 0: return
    f = ctx.font(HAND_FONT, 54); x, y = ctx.W * 0.40, ctx.H * 0.10; _rot_text(cv, ctx, (x, y), c["text"], f, YELLOW + (int(255 * a),), 6)
    p = T.ease_out(_p(t, c["at"] + 0.15, 0.5))      # the arrow draws itself from the note down toward the subject
    if p > 0:
        d = ImageDraw.Draw(cv, "RGBA"); x0, y0, x1, y1 = x + ctx.px(40), y + ctx.px(50), x + ctx.px(110), ctx.H * 0.30; pts = []
        for i in range(int(20 * p) + 1):
            u = i / 20; pts.append((x0 + (x1 - x0) * u + ctx.px(60) * math.sin(math.pi * u), y0 + (y1 - y0) * u))
        if len(pts) > 1: d.line(pts, fill=YELLOW + (255,), width=ctx.px(6), joint="curve")
        if p >= 1:
            (ax, ay), (bx, by) = pts[-2], pts[-1]; ang = math.atan2(by - ay, bx - ax); h = ctx.px(26)
            for s in (-0.5, 0.5): d.line((bx, by, bx - h * math.cos(ang + s), by - h * math.sin(ang + s)), fill=YELLOW + (255,), width=ctx.px(6))

def draw_measure(cv, ctx, c, t):
    d = ImageDraw.Draw(cv, "RGBA"); h = c.get("height"); w = c.get("weight")
    if h:
        p = T.ease_out(_p(t, h["at"], 0.6))
        if p > 0:
            x, y0, y1 = ctx.W * 0.07, ctx.H * 0.18, ctx.H * 0.80; ym = (y0 + y1) / 2; ya, yb = ym - (ym - y0) * p, ym + (y1 - ym) * p; col = T.SOFT_WHITE + (240,)
            d.line((x, ya, x, yb), fill=col, width=ctx.px(4))
            for yy in (ya, yb): d.line((x - ctx.px(18), yy, x + ctx.px(18), yy), fill=col, width=ctx.px(4))
            if p >= 0.9:
                f = ctx.font(T.HEAD_FONT, 40); tw = D._text_w(d, h["text"], f, ctx.px(1)); d.rounded_rectangle((x + ctx.px(18), ym - ctx.px(30), x + ctx.px(46) + tw, ym + ctx.px(32)), radius=ctx.px(10), fill=(14, 14, 16, 220))
                D.text_spaced(d, (x + ctx.px(32), ym - ctx.px(26)), h["text"], f, T.ORANGE + (255,), ctx.px(1))
    if w:
        q = T.ease_back(_p(t, w["at"], 0.4))
        if q > 0:
            f = ctx.font(T.HEAD_FONT, 44); tw = D._text_w(d, w["text"], f, ctx.px(1)); x, y = ctx.W * 0.07 + (ctx.px(18) if h else 0), ctx.H * (0.56 if h else 0.46)      # under the height label, clear of the safety chip
            d.rounded_rectangle((x, y, x + tw + ctx.px(40), y + ctx.px(66)), radius=ctx.px(12), fill=T.ORANGE + (int(255 * min(1, q)),)); D.text_spaced(d, (x + ctx.px(20), y + ctx.px(8)), w["text"], f, (20, 20, 22, 255), ctx.px(1))

def draw_hazard(cv, ctx, c, t):
    u = t - c["at"]
    if u < 0 or u > 3.0: return
    e = T.ease_out(min(1.0, u / 0.4)) - T.ease_in_out(max(0.0, (u - 2.4) / 0.6)); y0, hh = ctx.H * 0.12, ctx.px(84); W = ctx.W
    band = Image.new("RGBA", (W + ctx.px(200), hh), YELLOW + (255,)); bd = ImageDraw.Draw(band); s = ctx.px(70)
    for x in range(-hh, band.width + hh, 2 * s): bd.polygon([(x, hh), (x + s, hh), (x + s + hh, 0), (x + hh, 0)], fill=(20, 20, 22, 255))
    f = ctx.font(T.HEAD_FONT, 52); tw = bd.textlength("WARNING", font=f); bx = band.width / 2 - tw / 2
    bd.rectangle((bx - ctx.px(30), 0, bx + tw + ctx.px(30), hh), fill=YELLOW + (255,)); bd.text((bx, (hh - f.size) / 2 - ctx.px(6)), "WARNING", font=f, fill=(20, 20, 22, 255))
    band = band.rotate(-2.5, expand=True, resample=Image.BICUBIC); x = int(-band.width + (band.width - ctx.px(100)) * e)
    cv.paste(band, (x, int(y0)), band)

DRAW = {"strike": draw_strike, "bubble": draw_bubble, "aside": draw_aside, "measure": draw_measure, "hazard": draw_hazard}

def draw(cv: Image.Image, ctx: D.Ctx, sc: dict, t_abs: float) -> None:
    for k in OVERLAYS:
        if sc.get(k): DRAW[k](cv, ctx, sc[k], t_abs)
