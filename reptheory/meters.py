"""Meters and numbers (docs/rep_theory/PLAN_NEXT_GRAPHICS.md, Phase 2), each read from the sentence's own words so any script gets them:
  tokens   "three holds of 15 seconds", "6 x 2 s", "4 sets of 10 reps" -> the big "3 × 15 S" with one circle per set filling in turn       (a side card)
  share    "half your weight", "two thirds", "66% of your body weight", "all of it" -> a gauge whose needle steps to each share on its word  (a side card)
  meter    "heavier", "more load", "harder" / "lighter", "shorten", "easier" -> a small vertical load meter that rises or falls          (an overlay)
  effort   "as hard as you can", "to failure", "until you can't", "near your limit" -> an effort bar filling up to its LIMIT mark            (an overlay)
Times in card / overlay dicts are absolute; the drawing functions take the scene start to make them relative."""
from __future__ import annotations
import math, re
from typing import List, Optional

from PIL import Image, ImageDraw

from . import draw as D, theme as T

NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "sixty": 60}
N_ = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|thirty|forty|forty-five|sixty)"
TOKENS_RX = (re.compile(rf"\b{N_}\s+(holds?|sets?|rounds?)\s+of\s+{N_}\s*(seconds?|secs?|s|reps?|repetitions)\b", re.I),
             re.compile(rf"\b{N_}\s*(?:x|×|times)\s*{N_}\s*(seconds?|secs?|s|reps?)\b", re.I))
SHARE_RX = re.compile(r"\b(half|a third|one third|two thirds|three quarters|a quarter|all|\d{1,3}\s*(?:%|percent))\s+(?:of\s+)?(?:your|their|his|her|the)\s+(?:whole\s+)?(?:body\s*weight|bodyweight|weight|body)\b", re.I)
SHARE_V = {"half": 50, "a third": 33, "one third": 33, "two thirds": 66, "three quarters": 75, "a quarter": 25, "all": 100}
UP_RX = re.compile(r"\b(heavier|more load|more weight|harder|the load (?:goes|rises|grows)|load (?:goes up|rises)|further out|longer lever|adds? (?:\d+|ten|five) ?(?:kilos?|kg|pounds?))\b", re.I)
DOWN_RX = re.compile(r"\b(lighter|less load|less weight|easier|shorten(?:s|ed)? the (?:bar|lever)|shorter lever|closer to your hands)\b", re.I)
EFFORT_RX = re.compile(r"\b(as hard as (?:you|possible|you can)|all[- ]out|to failure|until you can'?t|near your limit|max(?:imum)? effort|everything you'?ve got)\b", re.I)

def _n(s: str) -> int:
    s = s.lower().strip(); return int(s) if s.isdigit() else NUMW.get(s, 0)

def _at(sc: dict, pos: int) -> float:
    ws = sc.get("words") or []; i = len(sc.get("text", "")[:pos].split())
    return float(ws[min(i, len(ws) - 1)]["t0"]) if ws else float(sc["start"]) + 0.3

def tokens(sc: dict, text: str) -> Optional[dict]:
    for k, rx in enumerate(TOKENS_RX):
        m = rx.search(text)
        if not m: continue
        if k == 0: sets, each, unit = _n(m.group(1)), _n(m.group(3)), m.group(4)
        else: sets, each, unit = _n(m.group(1)), _n(m.group(2)), m.group(3)
        if 1 <= sets <= 10 and each > 0: return {"sets": sets, "each": each, "unit": "S" if unit.lower().startswith("s") else "REPS", "at": _at(sc, m.start())}
    return None

def share(sc: dict, text: str) -> Optional[dict]:
    """Every share of the body weight said in the sentence, in order: the needle steps to each on its word."""
    steps = []
    for m in SHARE_RX.finditer(text):
        w = m.group(1).lower(); v = SHARE_V.get(w) or int(re.sub(r"\D", "", w) or 0)
        if 0 < v <= 100: steps.append({"value": v, "at": _at(sc, m.start())})
    return {"steps": steps, "at": steps[0]["at"]} if steps else None

def meter_steps(sc: dict) -> List[dict]:
    text = sc.get("text", ""); out = [{"dir": 1, "at": _at(sc, m.start())} for m in UP_RX.finditer(text)] + [{"dir": -1, "at": _at(sc, m.start())} for m in DOWN_RX.finditer(text)]
    return sorted(out, key=lambda x: x["at"])

def plan(scenes: List[dict]) -> int:
    """Overlays: the load meter on scenes that say a load goes up or down (its level carries over to the next scenes that change it), the effort bar on all-out lines.
    Never on full cards that fill the frame. Returns how many overlays were placed."""
    level = 0.45; n = 0
    for sc in scenes:
        if sc["kind"] in ("slots", "race", "formula", "mechanism", "promise", "checklist", "steps", "versus", "mistake", "myth", "question", "timeline", "calendar", "result", "warning", "takeaway", "tier", "engage", "lever", "seesaw", "gap", "split", "panels", "tearoff", "battery", "clipboard", "road"): continue
        st = meter_steps(sc)
        if st:
            lv = []
            for s in st: level = min(0.95, max(0.1, level + 0.25 * s["dir"])); lv.append({"at": s["at"], "level": level})
            sc["meter"] = {"start": max(0.1, min(0.95, lv[0]["level"] - 0.25 * st[0]["dir"])), "steps": lv}; n += 1
        m = EFFORT_RX.search(sc.get("text", ""))
        if m: sc["effort"] = {"at": _at(sc, m.start())}; n += 1
    return n

# ------------------------------------------------------------------ drawing
def draw_tokens(cv: Image.Image, ctx: D.Ctx, tk: dict, t: float) -> None:
    """The big "N × M S" on the left and N circles under it, filling one after another from the sets word."""
    d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, t / 0.35); cx, cy = int(ctx.W * 0.28), int(ctx.H * 0.46); at = tk["at"]
    txt = f"{tk['sets']} × {tk['each']} {tk['unit']}"; f = ctx.font(T.HEAD_FONT, 150); w = D._text_w(d, txt, f, ctx.px(2)); e = T.ease_back(min(1.0, max(0.0, (t - at + 0.2) / 0.5)))
    D.text_spaced(d, (cx - w / 2, cy - ctx.px(110) + int((1 - e) * 30 * ctx.S)), txt, f, T.ORANGE + (int(255 * a * min(1, e * 1.5)),), ctx.px(2))
    n = tk["sets"]; r = ctx.px(28); gap = ctx.px(24); x0 = cx - (n * 2 * r + (n - 1) * gap) / 2 + r; y = cy + ctx.px(110)
    for i in range(n):
        q = min(1.0, max(0.0, (t - at - 0.3 - 0.25 * i) / 0.25)); x = x0 + i * (2 * r + gap)
        d.ellipse((x - r, y - r, x + r, y + r), outline=(110, 110, 116, int(255 * a)), width=ctx.px(4))
        if q > 0: rr = r * T.ease_back(q) * 0.78; d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=T.RED + (int(255 * a),))
        f2 = ctx.font(T.BODY_FONT, 22); lab = f"{tk['each']}{'S' if tk['unit'] == 'S' else ''}"; lw = D._text_w(d, lab, f2, ctx.px(1)); D.text_spaced(d, (x - lw / 2, y + r + ctx.px(10)), lab, f2, T.GREY + (int(255 * a),), ctx.px(1))

def draw_share(cv: Image.Image, ctx: D.Ctx, sh: dict, t: float) -> None:
    """A half-circle gauge from 0 to ALL; the needle steps to each share on its word, the number under it rolls to match, the scale is green to red."""
    d = ImageDraw.Draw(cv, "RGBA"); cx, cy, r = int(ctx.W * 0.28), int(ctx.H * 0.60), int(ctx.H * 0.28); a = min(1.0, t / 0.35)
    for i in range(40):
        f0 = i / 40; col = tuple(int(g + (rr - g) * f0) for g, rr in zip((74, 222, 128), (232, 64, 52)))
        d.arc((cx - r, cy - r, cx + r, cy + r), 180 + 180 * f0, 180 + 180 * (i + 0.8) / 40, fill=col + (int(255 * a),), width=ctx.px(22))
    v = 0.0
    for s in sh["steps"]:
        if t >= s["at"] - 0.1: v = v + (s["value"] - v) * T.ease_back(min(1.0, (t - s["at"] + 0.1) / 0.6))
    ang = math.radians(180 + 180 * v / 100); d.line((cx, cy, cx + (r - ctx.px(40)) * math.cos(ang), cy + (r - ctx.px(40)) * math.sin(ang)), fill=T.WHITE + (255,), width=ctx.px(8)); d.ellipse((cx - ctx.px(14), cy - ctx.px(14), cx + ctx.px(14), cy + ctx.px(14)), fill=T.WHITE + (255,))
    f = ctx.font(T.HEAD_FONT, 110); txt = f"{v:.0f} %"; w = D._text_w(d, txt, f, 0); D.text_spaced(d, (cx - w / 2, cy + ctx.px(20)), txt, f, T.ORANGE + (255,), 0)
    f2 = ctx.font(T.BODY_FONT, 30); lab = "OF YOUR WEIGHT"; lw = D._text_w(d, lab, f2, ctx.px(3)); D.text_spaced(d, (cx - lw / 2, cy + ctx.px(150)), lab, f2, T.GREY + (int(255 * a),), ctx.px(3))
    for x, lab in ((cx - r, "0"), (cx + r - ctx.px(40), "ALL")): D.text_spaced(d, (x, cy + ctx.px(20)), lab, ctx.font(T.BODY_FONT, 24), T.GREY + (int(255 * a),), ctx.px(2))

def draw_meter(cv: Image.Image, ctx: D.Ctx, mt: dict, t_abs: float, start: float) -> None:
    """A small LOAD meter at the right edge: its level moves to each step on the word that says the load goes up or down; red above two thirds."""
    d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, (t_abs - start) / 0.3); x, y0, h, w = int(ctx.W * 0.935), int(ctx.H * 0.30), int(ctx.H * 0.40), ctx.px(46)
    lv = mt["start"]
    for s in mt["steps"]:
        if t_abs >= s["at"]: lv = lv + (s["level"] - lv) * T.ease_out(min(1.0, (t_abs - s["at"]) / 0.6))
    d.rounded_rectangle((x - w / 2, y0, x + w / 2, y0 + h), radius=ctx.px(10), fill=(24, 24, 27, int(230 * a)), outline=(90, 90, 96, int(255 * a)), width=ctx.px(3))
    fh = int((h - ctx.px(10)) * lv); col = T.RED if lv > 0.66 else T.ORANGE
    d.rounded_rectangle((x - w / 2 + ctx.px(6), y0 + h - ctx.px(5) - fh, x + w / 2 - ctx.px(6), y0 + h - ctx.px(5)), radius=ctx.px(6), fill=col + (int(255 * a),))
    f = ctx.font(T.BODY_FONT, 24); lw = D._text_w(d, "LOAD", f, ctx.px(2)); D.text_spaced(d, (x - lw / 2, y0 - ctx.px(36)), "LOAD", f, T.SOFT_WHITE + (int(255 * a),), ctx.px(2))

def draw_effort(cv: Image.Image, ctx: D.Ctx, ef: dict, t_abs: float) -> None:
    """An effort bar at the bottom, green to red, filling up to its LIMIT mark from the word that says all-out; the mark pulses when it is reached."""
    u = t_abs - ef["at"]
    if u < 0: return
    d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, u / 0.3); x0, x1, y = int(ctx.W * 0.30), int(ctx.W * 0.70), int(ctx.H * 0.90); h = ctx.px(18); p = T.ease_in_out(min(1.0, u / 1.2))
    d.rounded_rectangle((x0, y, x1, y + h), radius=h // 2, fill=(30, 30, 33, int(230 * a)))
    xe = x0 + (x1 - x0) * 0.92 * p
    for i in range(30):
        f0 = i / 30; xa = x0 + (x1 - x0) * 0.92 * f0; xb = x0 + (x1 - x0) * 0.92 * (i + 1) / 30
        if xa < xe: d.rectangle((xa, y + 3, min(xb, xe), y + h - 3), fill=tuple(int(g + (rr - g) * f0) for g, rr in zip((74, 222, 128), (232, 64, 52))) + (int(255 * a),))
    xl = x0 + (x1 - x0) * 0.92; d.line((xl, y - ctx.px(14), xl, y + h + ctx.px(14)), fill=T.WHITE + (int(255 * a),), width=ctx.px(3))
    f = ctx.font(T.BODY_FONT, 22); D.text_spaced(d, (xl - ctx.px(28), y - ctx.px(44)), "LIMIT", f, T.WHITE + (int(255 * a),), ctx.px(2)); D.text_spaced(d, (x0, y - ctx.px(44)), "EFFORT", f, T.GREY + (int(255 * a),), ctx.px(2))
    if p >= 1: q = min(1.0, (u - 1.2) / 0.5); rr = ctx.px(10) + ctx.px(30) * q; d.ellipse((xl - rr, y + h / 2 - rr, xl + rr, y + h / 2 + rr), outline=T.RED + (int(200 * (1 - q)),), width=ctx.px(3))
