"""Diagrams that explain WHY (docs/rep_theory/PLAN_NEXT_GRAPHICS.md, Phase 3), each read from the sentence's own shape so any script gets them:
  lever      "weight times distance", "the further out, the heavier", "it's a lever" -> pivot, bar, weight arrow, distance bracket, an object pinned on the end, a formula box
  seesaw     "balance", "too far forward", "tips back" -> a plank on a pivot that tilts on the word, BALANCED / TIPS FORWARD under it
  gap        "muscles get stronger faster than tendons", "the gap between A and B" -> two curves over time with the gap between them shaded red
  split      "half strength, half balance", "part skill, part strength", "both strength and balance" -> one circle split in two, each half filling on its word
  panels     "turn X into Y", "from X to Y", "X becomes Y" -> two panels joined by a dashed arc drawn from the first to the second
  tearoff    two durations or one and "never" ("a few months ... one to two years, some never") -> calendar pads whose top page tears away on each duration
  battery    rest / recover with training ("training drains it, rest rebuilds it", "rest 2 days a week") -> a battery draining and charging on the words, a week strip under it
  clipboard  the plan said as a list ("Your plan: warm up, two holds, push-ups") -> a clipboard built row by row, ticked, with "N DAYS A WEEK ≈ M MIN" under it
  silrow     three or more poses named in order ("plank, frog stand, tuck planche") -> a row of grey silhouettes from the pose library, each lit orange on its word (Phase 4)
  road       "the road to the planche", "the path to your first pull-up" -> a road in perspective with signs along it and the goal flag at the horizon
All fill the frame (the narration's next phrase follows in a caption strip, scenes._caption_strip). Every payload carries `marks`: the absolute times something new lands
(cadence and cards.CARD_DONE read them). Drawing takes the absolute time."""
from __future__ import annotations
import math, re
from typing import Callable, Dict, List, Optional

from PIL import Image, ImageDraw

from . import draw as D, meters as M, narrative as N, theme as T

KINDS = ("lever", "seesaw", "gap", "split", "panels", "tearoff", "battery", "clipboard", "road", "silrow")
GREEN = (74, 222, 128)
W_ = r"[A-Za-z][A-Za-z'-]*"

def _words(s: str, n: int = 2, last: bool = False) -> str:
    """Up to n content words of a phrase (its last ones when `last`), upper case; "" when it has none."""
    ws = [w for w in re.findall(W_, s) if w.lower() not in N.STOP]
    ws = ws[-n:] if last else ws[:n]
    return " ".join(ws).upper()

def _done(c: dict) -> float: return max(c["marks"]) + 0.6

# ------------------------------------------------------------------ detectors: (scene, its text) -> payload with absolute times, or None
TIMES_RX = re.compile(rf"\b({W_})\s+(?:times|multiplied by|×)\s+(?:the\s+|your\s+)?({W_})", re.I)
FURTHER_RX = re.compile(r"\bthe\s+(further|farther|longer|more)\b[^.;]{0,40}?\bthe\s+(heavier|harder|more|bigger|greater)\b", re.I)
LEVER_RX = re.compile(r"\b(lever(?:age)?|pivot)\b", re.I)
OBJ_RX = re.compile(r"(\+?\s?\d+\s?(?:kg|kilos?|pounds?|lbs?))\b(?:\s+([A-Za-z]+))?", re.I)
OBJ_WORDS = ("backpack", "vest", "plate", "dumbbell", "kettlebell", "bag", "sandbag", "chain")

def lever(sc: dict, text: str) -> Optional[dict]:
    m = TIMES_RX.search(text)
    if m and (m.group(1).lower() in N.STOP or m.group(2).lower() in N.STOP or m.group(2).lower() in ("a", "per", "week", "day")): m = None
    f = FURTHER_RX.search(text); lv = LEVER_RX.search(text)
    if not (m or f or lv): return None
    a, b = (m.group(1).upper(), m.group(2).upper()) if m else ("WEIGHT", "DISTANCE")
    at = M._at(sc, (m or f or lv).start()); o = OBJ_RX.search(text); obj = ""
    if o: obj = re.sub(r"\s+", " ", o.group(1).replace("+", "").strip()).upper().replace("KILOS", "KG").replace("KILO", "KG"); obj = (obj if obj.startswith("+") else "+" + obj) + (" " + o.group(2).upper() if o.group(2) and o.group(2).lower() in OBJ_WORDS else "")
    else:
        w = next((w for w in OBJ_WORDS if re.search(rf"\b{w}\b", text, re.I)), "")
        if w: obj = w.upper(); o = re.search(rf"\b{w}\b", text, re.I)
    obj_at = M._at(sc, o.start()) if obj else None
    marks = [at, at + 0.5, at + 0.9, at + 1.4] + ([obj_at] if obj_at else [])
    return {"a": a, "b": b, "obj": obj, "at": at, "obj_at": obj_at, "marks": marks}

SEESAW_RX = re.compile(r"\b(balance[sd]?|balancing|seesaw|tips?\s+(?:over|forward|back)|tipping|too\s+far\s+(forward|back|ahead|behind)|lean(?:s|ing)?\s+(?:too\s+)?(?:far\s+)?(forward|back))\b", re.I)
TIP_RX = re.compile(r"\b(tip|tips|tipping|lean|leans|leaning|forward|backward|shift|fall|falls|off\s+balance|lose\s+(?:your\s+)?balance|balance\s+point)\b", re.I)
FWD_RX, BACK_RX = re.compile(r"\b(forward|ahead|over)\b", re.I), re.compile(r"\b(back|backward|behind)\b", re.I)
BETWEEN_RX = re.compile(rf"\bbetween\s+(?:your\s+|the\s+)?({W_})\s+and\s+(?:your\s+|the\s+)?({W_})", re.I)

def seesaw(sc: dict, text: str) -> Optional[dict]:
    hits = [h for h in SEESAW_RX.finditer(text) if not re.match(r"balance$", h.group(0), re.I) or TIP_RX.search(text)]      # "balance" as a noun ("half strength, half balance") is not a seesaw
    if not hits: return None
    steps = []
    for h in hits:
        s = h.group(0); tilt = 0 if re.match(r"balanc|seesaw", s, re.I) else 1 if FWD_RX.search(s) else -1 if BACK_RX.search(s) else 1
        steps.append({"tilt": tilt, "at": M._at(sc, h.start())})
    bt = BETWEEN_RX.search(text); left, right = (bt.group(1).upper(), bt.group(2).upper()) if bt else ("BACK", "FORWARD")
    return {"left": left, "right": right, "steps": steps, "at": steps[0]["at"], "marks": [s["at"] for s in steps]}

GAP_RX = (re.compile(rf"\b(?:your\s+|the\s+)?({W_})\s+(?:\w+\s+){{0,4}}?(?:faster|quicker|sooner|more\s+quickly)\s+than\s+(?:your\s+|the\s+|their\s+)?({W_})", re.I),
          re.compile(rf"\b(?:your\s+|the\s+)?({W_})\s+outpaces?\s+(?:your\s+|the\s+)?({W_})", re.I),
          re.compile(rf"\bthe\s+gap\s+between\s+(?:your\s+|the\s+)?({W_})\s+and\s+(?:your\s+|the\s+)?({W_})", re.I))
UNIT_RX = re.compile(r"\b(days?|weeks?|months?|years?)\b", re.I)

def gap(sc: dict, text: str) -> Optional[dict]:
    for rx in GAP_RX:
        m = rx.search(text)
        if m and m.group(1).lower() not in N.STOP and m.group(2).lower() not in N.STOP and m.group(1).lower() != m.group(2).lower():
            at = M._at(sc, m.start()); g = re.search(r"\b(gap|faster|outpace|quicker|sooner)\w*", text[m.start():], re.I); g_at = max(at + 0.8, M._at(sc, m.start() + g.start()) if g else at)
            u = UNIT_RX.search(text)
            return {"fast": m.group(1).upper(), "slow": m.group(2).upper(), "unit": (u.group(1).rstrip("s") + "s").upper() if u else "TIME", "at": at, "gap_at": g_at, "marks": [at, at + 0.6, g_at]}
    return None

SPLIT_RX = (re.compile(rf"\bhalf\s+({W_})[,]?\s+(?:and\s+)?half\s+({W_})", re.I), re.compile(rf"\bpart\s+({W_})[,]?\s+(?:and\s+)?part\s+({W_})", re.I),
            re.compile(rf"\b(?:as\s+much|just\s+as\s+much)\s+(?:about\s+)?({W_})\s+as\s+(?:it\s+is\s+)?(?:about\s+)?({W_})", re.I),
            re.compile(rf"\bboth\s+({W_})\s+and\s+({W_})\b", re.I))

def split(sc: dict, text: str) -> Optional[dict]:
    from .states import BODY_RX
    for rx in SPLIT_RX:
        m = rx.search(text)
        if not m: continue
        a, b = m.group(1), m.group(2)
        if a.lower() in N.STOP or b.lower() in N.STOP or a.lower() == b.lower(): continue
        if rx is SPLIT_RX[-1] and any(r.search(a) or r.search(b) for r in BODY_RX.values()): continue      # "both arms and legs" is two parts, not two ideas
        a_at = M._at(sc, m.start(1)); b_at = max(a_at + 0.4, M._at(sc, m.start(2)))
        return {"a": a.upper(), "b": b.upper(), "a_at": a_at, "b_at": b_at, "at": a_at, "marks": [a_at, b_at]}
    return None

PANELS_RX = (re.compile(r"\b(?:turns?|turned|transforms?|changes?)\s+(?:your\s+|the\s+|a\s+|an\s+)?([A-Za-z][\w' -]{1,30}?)\s+into\s+(?:a\s+|an\s+|your\s+|the\s+)?([A-Za-z][\w'-]*(?:\s[A-Za-z][\w'-]*)?)", re.I),
             re.compile(r"\bfrom\s+(?:a\s+|an\s+|your\s+|the\s+)?([A-Za-z][\w'-]*(?:\s[A-Za-z0-9][\w'-]*)?)\s+to\s+(?:a\s+|an\s+|your\s+|the\s+)?([A-Za-z][\w'-]*(?:\s[A-Za-z0-9][\w'-]*)?)", re.I),
             re.compile(rf"\b(?:your\s+|the\s+|a\s+)?({W_})\s+becomes?\s+(?:a\s+|an\s+|your\s+|the\s+)?({W_}(?:\s{W_})?)", re.I))

def panels(sc: dict, text: str) -> Optional[dict]:
    for rx in PANELS_RX:
        m = rx.search(text)
        if not m: continue
        a, b = _words(m.group(1), 2, last=True), _words(m.group(2), 2)
        if not a or not b or a == b: continue
        a_at = M._at(sc, m.start(1)); b_at = max(a_at + 0.6, M._at(sc, m.start(2)))
        return {"a": a, "b": b, "a_at": a_at, "b_at": b_at, "at": a_at, "marks": [a_at, (a_at + b_at) / 2, b_at]}
    return None

DUR_RX = re.compile(r"\b(a\s+few|few|several|a|an|\d+|one|two|three|four|five|six|eight|ten|twelve)(?:\s*(?:to|-|or)\s*(\d+|two|three|four|five|six|eight|ten|twelve))?\s+(days?|weeks?|months?|years?)\b", re.I)
NEVER_RX = re.compile(r"\b(?:some\s+(?:people\s+)?|others?\s+)?never\b", re.I)

def tearoff(sc: dict, text: str) -> Optional[dict]:
    pages = []
    for m in DUR_RX.finditer(text):
        q = m.group(1).upper().replace("  ", " "); q = {"A": "1", "AN": "1", "A FEW": "FEW"}.get(re.sub(r"\s+", " ", q), q)
        if q.lower() in M.NUMW: q = str(M.NUMW[q.lower()])
        if m.group(2): r = m.group(2).lower(); q += "-" + str(M.NUMW.get(r, r))
        pages.append({"text": f"{q} {m.group(3).upper()}", "at": M._at(sc, m.start())})
    nv = NEVER_RX.search(text)
    if nv and pages: pages.append({"text": "SOME NEVER" if re.match(r"some|other", nv.group(0), re.I) else "NEVER", "at": M._at(sc, nv.start()), "red": True})
    if len(pages) < 2 or len({p["text"] for p in pages}) < 2 or re.search(r"\b(?:a|per)\s+(?:day|week)\b", text, re.I) and not nv: return None      # "4 days a week" is a calendar, not durations
    pages = pages[:3]
    return {"pages": pages, "at": pages[0]["at"], "marks": [p["at"] + 0.3 for p in pages]}

REST_RX = re.compile(r"\b(rest(?:s|ing)?|recover(?:y|s|ing)?|rebuild(?:s|ing)?|recharges?|repairs?)\b", re.I)
DRAIN_RX = re.compile(r"\b(train(?:s|ing)?|drains?|tired|fatigue|wears?\s+(?:it|them|you)\s+down|breaks?\s+(?:\w+\s+)?down)\b", re.I)      # a workout named in passing ("how your workouts feel") is not a drain
WEEK_RX = re.compile(r"\b(\d|two|three|four|five|six)\s+days?\s+(?:a|per|each)\s+week\b", re.I)

def battery(sc: dict, text: str) -> Optional[dict]:
    rs, dr, wk = list(REST_RX.finditer(text)), list(DRAIN_RX.finditer(text)), WEEK_RX.search(text)
    if not rs or not (dr or wk or re.search(r"\b(days?|tendons?|between)\b", text, re.I)): return None
    ev = sorted([(m.start(), 1) for m in rs] + [(m.start(), -1) for m in dr])
    level = 0.85 if ev[0][1] < 0 else 0.25; start = level; steps = []
    for pos, k in ev[:5]: level = min(1.0, max(0.1, level + (0.55 if k > 0 else -0.5))); steps.append({"level": level, "charge": k > 0, "at": M._at(sc, pos)})
    if len(steps) < 2 and not wk: return None      # one "rest" alone ("rest 60 seconds") is not a drain and a recharge
    week = None
    if wk:
        n = M._n(wk.group(1)); idx = {1: [0], 2: [0, 3], 3: [0, 2, 4], 4: [0, 1, 3, 4], 5: [0, 1, 2, 3, 4], 6: [0, 1, 2, 3, 4, 5]}.get(n, [])
        week = {"train": idx, "at": M._at(sc, wk.start())}
    marks = [s["at"] for s in steps] + ([week["at"] + 0.3] if week else [])
    return {"start": start, "steps": steps, "week": week, "at": steps[0]["at"], "marks": marks}

PLAN_RX = re.compile(r"\b(?:here'?s\s+(?:the|your)\s+(?:plan|routine|week)|your\s+(?:plan|routine|session|week)\s*(?:is|looks\s+like)?|the\s+(?:plan|routine)\s*(?:is|looks\s+like)?|each\s+(?:session|workout)|every\s+(?:session|workout))\s*[:,]?", re.I)
MIN_RX = re.compile(r"\b(\d+|ten|fifteen|twenty|thirty|forty-five|sixty)\s+min(?:ute)?s?\b", re.I)

def clipboard(sc: dict, text: str) -> Optional[dict]:
    m = PLAN_RX.search(text)
    if not m: return None
    rest = re.split(r"[.!?](?:\s|$)", text[m.end():])[0]; parts = [p for p in re.split(r",|;|:|\bthen\b|\band\s+finally\b|\bfinally\b|\band\s+then\b|\.\s", rest, flags=re.I)]
    items, pos = [], m.end()
    for p in parts:
        k = text.find(p, pos); pos = max(pos, k + len(p)) if k >= 0 else pos
        q = re.sub(r"^\s*(?:and|then|first|start\s+with|do)\s+", "", p.strip(), flags=re.I).strip(" .!?")
        if 1 <= len(q.split()) <= 6 and _words(q, 1): items.append({"text": q.upper(), "at": M._at(sc, k if k >= 0 else m.end())})
    if len(items) < 3: return None
    items = items[:6]; wk, mn = WEEK_RX.search(text), MIN_RX.search(text)
    foot = " ≈ ".join(x for x in ((f"{M._n(wk.group(1))} DAYS A WEEK" if wk else ""), (f"{M._n(mn.group(1))} MIN" if mn else "")) if x)
    for i in range(1, len(items)): items[i]["at"] = max(items[i]["at"], items[i - 1]["at"] + 0.35)
    return {"items": items, "foot": foot, "at": M._at(sc, m.start()), "marks": [i["at"] for i in items]}

ROAD_RX = re.compile(r"\b(?:the\s+|your\s+|a\s+)?(?:road|path|journey|way)\s+to\s+(?:a\s+|an\s+|the\s+|your\s+)?([A-Za-z][\w'-]*(?:\s[A-Za-z][\w'-]*){0,2})", re.I)

def road(sc: dict, text: str) -> Optional[dict]:
    m = ROAD_RX.search(text)
    if not m: return None
    goal = _words(m.group(1), 2, last=True)      # "your first free handstand" -> FREE HANDSTAND (the thing, not its first adjectives)
    if not goal: return None
    at = M._at(sc, m.start()); signs = [{"text": d.group(0).upper(), "at": M._at(sc, d.start())} for d in DUR_RX.finditer(text)][:3]
    if not signs: signs = [{"text": "DAY 1", "at": at + 0.3}, {"text": "YOU", "at": at + 0.7}]
    goal_at = max(M._at(sc, m.start(1)), signs[-1]["at"] + 0.3)
    return {"goal": goal, "signs": signs, "at": at, "goal_at": goal_at, "marks": [s["at"] for s in signs] + [goal_at]}

def silrow(sc: dict, text: str) -> Optional[dict]:
    from . import library as L
    from .poses import POSE_RX, POSES
    seen, items = set(), []
    for pid, rx in POSE_RX.items():
        m = rx.search(text); lab = POSES[pid][1]
        if not m or lab in seen: continue
        try: ok = L.find(pid) is not None
        except Exception: ok = False
        if ok: seen.add(lab); items.append({"art": pid, "label": lab, "pos": m.start()})
    if len(items) < 3: return None
    items = sorted(items, key=lambda x: x["pos"])[:5]
    for i, it in enumerate(items): it["at"] = max(M._at(sc, it.pop("pos")), items[i - 1]["at"] + 0.3 if i else 0.0)
    return {"items": items, "at": items[0]["at"], "marks": [i["at"] for i in items]}

DETECT: Dict[str, Callable] = {"lever": lever, "seesaw": seesaw, "gap": gap, "split": split, "panels": panels, "tearoff": tearoff, "battery": battery, "clipboard": clipboard, "road": road, "silrow": silrow}
BASE = {"lever": 0.9, "seesaw": 0.84, "gap": 0.92, "split": 0.88, "panels": 0.8, "tearoff": 0.9, "battery": 0.84, "clipboard": 0.93, "road": 0.88, "silrow": 0.9}      # support in variety.evidence (cards sit 0.78-0.95)
DONE = {k: _done for k in KINDS}

def evidence(sc: dict, text: str) -> Dict[str, tuple]:
    out = {}
    for k, fn in DETECT.items():
        got = fn(sc, text)
        if got: got["open"] = float(sc["start"]); out[k] = (BASE[k], got)      # the diagram's frame is up from the scene's first frame, its parts land on their words
    return out

# ------------------------------------------------------------------ drawing (absolute time)
def _p(t: float, at: float, dur: float = 0.4) -> float: return min(1.0, max(0.0, (t - at) / dur))

def _open(c: dict) -> float: return min(c.get("open", c["at"]), c["at"] - 0.2)      # first render: a split circle waited 1.4 s on a blank screen for its first word

def _label(d, ctx, xy, text, size, col, a, centre=True, head=True):
    if a <= 0 or not text: return
    f = ctx.font(T.HEAD_FONT if head else T.BODY_FONT, size); w = D._text_w(d, text, f, ctx.px(2)); x, y = xy
    D.text_spaced(d, (x - w / 2 if centre else x, y), text, f, tuple(col) + (int(255 * min(1.0, a)),), ctx.px(2))

def _arrow(d, a, b, col, width, head):
    d.line((a, b), fill=col, width=width); ang = math.atan2(b[1] - a[1], b[0] - a[0])
    d.polygon([b, (b[0] - head * math.cos(ang - 0.45), b[1] - head * math.sin(ang - 0.45)), (b[0] - head * math.cos(ang + 0.45), b[1] - head * math.sin(ang + 0.45))], fill=col)

def draw_lever(cv, ctx, c, t):
    d = ImageDraw.Draw(cv, "RGBA"); W, H = ctx.W, ctx.H; a = _p(t, _open(c), 0.35); px, py = W * 0.18, H * 0.56
    load = 0.6 + (0.4 * _p(t, c["obj_at"], 0.6) if c.get("obj_at") else 0.0); tilt = math.radians(2 + 5 * load * T.ease_out(_p(t, c["at"] + 0.5, 0.8)))
    L = W * 0.42 * T.ease_out(_p(t, c["at"], 0.5))
    ex, ey = px + L * math.cos(tilt), py + L * math.sin(tilt)
    s = ctx.px(46); d.polygon([(px, py + ctx.px(8)), (px - s, py + s * 1.6), (px + s, py + s * 1.6)], fill=T.SOFT_WHITE + (int(255 * a),))      # pivot
    _label(d, ctx, (px, py + s * 1.6 + ctx.px(14)), "PIVOT", 26, T.GREY, a, head=False)
    rr = ctx.px(24) + ctx.px(18) * (1 - _p(t, c["at"], 0.6)); d.ellipse((px - rr, py - rr, px + rr, py + rr), outline=T.ORANGE + (int(220 * a),), width=ctx.px(4))
    if L > 1: d.line((px, py, ex, ey), fill=T.WHITE + (int(255 * a),), width=ctx.px(14))
    q = T.ease_back(_p(t, c["at"] + 0.5, 0.45))      # weight arrow down at the far end
    if q > 0:
        ln = ctx.px(150) * q * load; _arrow(d, (ex, ey + ctx.px(14)), (ex, ey + ctx.px(14) + ln), T.RED + (255,), ctx.px(10), ctx.px(34)); _label(d, ctx, (ex + ctx.px(28), ey + ctx.px(40)), c["a"], 40, T.RED, q, centre=False)
    q = _p(t, c["at"] + 0.9, 0.45)      # distance bracket over the bar
    if q > 0:
        y = min(py, ey) - ctx.px(70); xe = px + (ex - px) * T.ease_out(q); col = T.ORANGE + (int(255 * q),)
        d.line((px, y, xe, y), fill=col, width=ctx.px(4)); d.line((px, y - ctx.px(14), px, y + ctx.px(14)), fill=col, width=ctx.px(4)); d.line((xe, y - ctx.px(14), xe, y + ctx.px(14)), fill=col, width=ctx.px(4))
        _label(d, ctx, ((px + xe) / 2, y - ctx.px(52)), c["b"], 40, T.ORANGE, q)
    if c.get("obj_at"):      # the object pinned on the end, dropping in
        q = T.ease_back(_p(t, c["obj_at"], 0.45))
        if q > 0:
            bw, bh = ctx.px(120), ctx.px(96); y1 = ey - ctx.px(8) - (1 - q) * ctx.px(120)
            d.rounded_rectangle((ex - bw / 2, y1 - bh, ex + bw / 2, y1), radius=ctx.px(16), fill=(60, 60, 66, int(255 * min(1, q))), outline=T.ORANGE + (int(255 * min(1, q)),), width=ctx.px(4))
            _label(d, ctx, (ex, y1 - bh - ctx.px(48)), c["obj"], 34, T.ORANGE, q)
    q = _p(t, c["at"] + 1.4, 0.45)      # the formula box
    if q > 0:
        x0, y0, x1, y1 = W * 0.70, H * 0.26, W * 0.95, H * 0.60; d.rounded_rectangle((x0, y0, x1, y1), radius=ctx.px(20), fill=(24, 24, 27, int(235 * q)), outline=(90, 90, 96, int(255 * q)), width=ctx.px(3))
        cx = (x0 + x1) / 2; _label(d, ctx, (cx, y0 + ctx.px(30)), "LOAD", 64, T.RED if load > 0.8 else T.WHITE, q); _label(d, ctx, (cx, y0 + ctx.px(110)), "=", 48, T.GREY, _p(t, c["at"] + 1.6, 0.3))
        _label(d, ctx, (cx, y0 + ctx.px(170)), f"{c['a']} × {c['b']}", 38 if len(c["a"] + c["b"]) < 16 else 28, T.ORANGE, _p(t, c["at"] + 1.8, 0.3))

def draw_seesaw(cv, ctx, c, t):
    d = ImageDraw.Draw(cv, "RGBA"); W, H = ctx.W, ctx.H; a = _p(t, _open(c), 0.35); cx, cy = W * 0.5, H * 0.52; tilt = 0.0; last = None
    for s in c["steps"]:
        if t >= s["at"]: tilt = tilt + (s["tilt"] - tilt) * T.ease_back(_p(t, s["at"], 0.6)); last = s
    ang = math.radians(10 * tilt); L = W * 0.30; dx, dy = L * math.cos(ang), L * math.sin(ang)
    s = ctx.px(60); d.polygon([(cx, cy + ctx.px(6)), (cx - s, cy + s * 1.7), (cx + s, cy + s * 1.7)], fill=T.SOFT_WHITE + (int(255 * a),))
    d.line((cx - dx, cy - dy, cx + dx, cy + dy), fill=T.WHITE + (int(255 * a),), width=ctx.px(14))
    for k, (x, y, lab) in enumerate(((cx - dx, cy - dy, c["left"]), (cx + dx, cy + dy, c["right"]))):
        r = ctx.px(52); col = T.ORANGE if (tilt > 0.3 and k == 1) or (tilt < -0.3 and k == 0) else (110, 110, 118)
        d.ellipse((x - r, y - 2 * r - ctx.px(6), x + r, y - ctx.px(6)), fill=tuple(col) + (int(255 * a),)); _label(d, ctx, (x, y - 2 * r - ctx.px(64)), lab, 40, T.WHITE, a)
    if last:
        q = _p(t, last["at"] + 0.3, 0.3); bal = abs(tilt) < 0.25
        _label(d, ctx, (cx, cy + s * 1.7 + ctx.px(30)), "BALANCED" if bal else f"TIPS {c['right'] if tilt > 0 else c['left']}", 56, GREEN if bal else T.RED, q)

def draw_gap(cv, ctx, c, t):
    d = ImageDraw.Draw(cv, "RGBA"); W, H = ctx.W, ctx.H; a = _p(t, _open(c), 0.35); x0, x1, y0, y1 = W * 0.14, W * 0.80, H * 0.16, H * 0.70
    d.line((x0, y0, x0, y1, x1, y1), fill=T.GREY + (int(255 * a),), width=ctx.px(4)); _label(d, ctx, (x1, y1 + ctx.px(16)), c["unit"], 28, T.GREY, a, head=False); _label(d, ctx, (x0 - ctx.px(10), y0 - ctx.px(46)), "STRENGTH", 26, T.GREY, a, centre=False, head=False)
    p = T.ease_in_out(_p(t, c["at"], 1.4)); n = 48
    fa = lambda u: 1 - math.exp(-3.2 * u); fb = lambda u: 0.55 * u ** 1.4
    pt = lambda u, f: (x0 + (x1 - x0) * u, y1 - (y1 - y0) * 0.92 * f(u))
    k = max(2, int(n * p))
    if p > 0:
        g = _p(t, c["gap_at"], 0.6)
        if g > 0:
            poly = [pt(i / n, fa) for i in range(k)] + [pt(i / n, fb) for i in range(k - 1, -1, -1)]; d.polygon(poly, fill=T.RED + (int(90 * g),))
            u = (k - 1) / n * 0.6; mx, my = x0 + (x1 - x0) * u, y1 - (y1 - y0) * 0.92 * (fa(u) + fb(u)) / 2; _label(d, ctx, (mx, my - ctx.px(26)), "THE GAP", 44, T.RED, g)
        for f, col, lab in ((fa, T.ORANGE, c["fast"]), (fb, (150, 160, 176), c["slow"])):
            ps = [pt(i / n, f) for i in range(k)]; d.line(ps, fill=tuple(col) + (int(255 * a),), width=ctx.px(8), joint="curve")
            ex, ey = ps[-1]; _label(d, ctx, (ex + ctx.px(18), ey - ctx.px(26)), lab, 40, col, a, centre=False)

def draw_split(cv, ctx, c, t):
    d = ImageDraw.Draw(cv, "RGBA"); W, H = ctx.W, ctx.H; a = _p(t, _open(c), 0.35); cx, cy, r = W * 0.5, H * 0.46, H * 0.30
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(90, 90, 96, int(255 * a)), width=ctx.px(5))
    for k, (key, col, a0) in enumerate((("a", T.ORANGE, 90), ("b", (96, 140, 220), 270))):
        q = T.ease_out(_p(t, c[key + "_at"], 0.5))
        if q > 0:
            rr = r - ctx.px(10); d.pieslice((cx - rr, cy - rr, cx + rr, cy + rr), a0, a0 + 180 * q, fill=tuple(col) + (230,))
            _label(d, ctx, (cx + (-1 if k == 0 else 1) * r * 0.5, cy - ctx.px(30)), c[key], 52 if len(c[key]) < 9 else 38, T.WHITE, q)
    q = _p(t, _open(c), 0.5); d.line((cx, cy - r * q, cx, cy + r * q), fill=T.WHITE + (int(255 * a),), width=ctx.px(6))

def draw_panels(cv, ctx, c, t):
    d = ImageDraw.Draw(cv, "RGBA"); W, H = ctx.W, ctx.H; pw, ph, y0 = W * 0.30, H * 0.36, H * 0.32
    for key, x0, col in (("a", W * 0.12, (110, 110, 118)), ("b", W * 0.58, T.ORANGE)):
        q = T.ease_back(_p(t, c[key + "_at"], 0.45))
        if q <= 0:      # an empty slot waits for its word
            e = _p(t, _open(c), 0.35)
            if e > 0: d.rounded_rectangle((x0, y0, x0 + pw, y0 + ph), radius=ctx.px(24), outline=(70, 70, 76, int(200 * e)), width=ctx.px(3))
            continue
        off = (1 - q) * ctx.px(40); d.rounded_rectangle((x0, y0 + off, x0 + pw, y0 + ph + off), radius=ctx.px(24), fill=(28, 28, 32, int(235 * min(1, q))), outline=tuple(col) + (int(255 * min(1, q)),), width=ctx.px(5))
        _label(d, ctx, (x0 + pw / 2, y0 + ph / 2 - ctx.px(34) + off), c[key], 60 if len(c[key]) < 10 else 42, col if key == "b" else T.WHITE, q)
    p = _p(t, c["a_at"] + 0.3, max(0.4, c["b_at"] - c["a_at"]))      # the dashed arc from the first panel to the second
    if p > 0:
        ax, bx, ty = W * 0.12 + pw / 2, W * 0.58 + pw / 2, y0 - ctx.px(20); mx, h = (ax + bx) / 2, H * 0.14; n = 30; pts = []
        for i in range(int(n * p) + 1):
            u = i / n; pts.append(((1 - u) ** 2 * ax + 2 * (1 - u) * u * mx + u * u * bx, (1 - u) ** 2 * ty + 2 * (1 - u) * u * (ty - 2 * h) + u * u * ty))
        for i in range(0, len(pts) - 1, 2): d.line((pts[i], pts[i + 1]), fill=T.WHITE + (230,), width=ctx.px(5))
        if p >= 1: _arrow(d, pts[-2], pts[-1], T.WHITE + (255,), ctx.px(5), ctx.px(30))

def draw_tearoff(cv, ctx, c, t):
    d = ImageDraw.Draw(cv, "RGBA"); W, H = ctx.W, ctx.H; n = len(c["pages"]); pw, ph = W * 0.22, H * 0.42; gap = W * 0.05; x0 = (W - n * pw - (n - 1) * gap) / 2; y0 = H * 0.22
    for i, pg in enumerate(c["pages"]):
        a = _p(t, _open(c) + 0.1 * i, 0.35); x = x0 + i * (pw + gap)
        d.rounded_rectangle((x, y0, x + pw, y0 + ph), radius=ctx.px(14), fill=(236, 233, 226, int(255 * a)))
        d.rectangle((x, y0, x + pw, y0 + ctx.px(46)), fill=T.RED + (int(255 * a),))
        for k in range(4): rx = x + pw * (0.2 + 0.2 * k); d.ellipse((rx - ctx.px(8), y0 - ctx.px(12), rx + ctx.px(8), y0 + ctx.px(12)), fill=(40, 40, 44, int(255 * a)))
        q = _p(t, pg["at"], 0.3); words = pg["text"].split(" ", 1)
        _label(d, ctx, (x + pw / 2, y0 + ph * 0.30), words[0], 96 if len(words[0]) < 5 else 64, T.RED if pg.get("red") else (30, 30, 34), q)
        if len(words) > 1: _label(d, ctx, (x + pw / 2, y0 + ph * 0.64), words[1], 40, (70, 70, 76), q)
        tp = _p(t, pg["at"] - 0.05, 0.6)      # the blank top page tears off and falls away
        if tp < 1:
            pg_im = Image.new("RGBA", (int(pw), int(ph - ctx.px(46))), (246, 244, 238, int(255 * a)))
            if tp > 0: pg_im = pg_im.rotate(-25 * tp, expand=True, resample=Image.BICUBIC); pg_im.putalpha(pg_im.getchannel("A").point(lambda v: int(v * (1 - tp))))
            cv.paste(pg_im, (int(x + ctx.px(30) * tp), int(y0 + ctx.px(46) + H * 0.25 * tp * tp)), pg_im); d = ImageDraw.Draw(cv, "RGBA")

def draw_battery(cv, ctx, c, t):
    d = ImageDraw.Draw(cv, "RGBA"); W, H = ctx.W, ctx.H; a = _p(t, _open(c), 0.35); bw, bh = W * 0.40, H * 0.26; x0, y0 = (W - bw) / 2, H * 0.16 if c.get("week") else H * 0.28
    lv, charging = c["start"], False
    for s in c["steps"]:
        if t >= s["at"]: lv = lv + (s["level"] - lv) * T.ease_in_out(_p(t, s["at"], 0.8)); charging = s["charge"] and t < s["at"] + 1.2
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=ctx.px(24), outline=T.WHITE + (int(255 * a),), width=ctx.px(8)); d.rounded_rectangle((x0 + bw, y0 + bh * 0.32, x0 + bw + ctx.px(28), y0 + bh * 0.68), radius=ctx.px(8), fill=T.WHITE + (int(255 * a),))
    col = T.RED if lv < 0.35 else T.ORANGE if lv < 0.7 else GREEN; m = ctx.px(18)
    if lv > 0.02: d.rounded_rectangle((x0 + m, y0 + m, x0 + m + (bw - 2 * m) * lv, y0 + bh - m), radius=ctx.px(12), fill=tuple(col) + (int(255 * a),))
    if charging:
        cx, cy, s = x0 + bw / 2, y0 + bh / 2, bh * 0.36; d.polygon([(cx + s * 0.15, cy - s), (cx - s * 0.45, cy + s * 0.1), (cx - s * 0.02, cy + s * 0.1), (cx - s * 0.15, cy + s), (cx + s * 0.45, cy - s * 0.1), (cx + s * 0.02, cy - s * 0.1)], fill=T.WHITE + (255,))
    _label(d, ctx, (W / 2, y0 + bh + ctx.px(20)), f"{lv * 100:.0f} %" + ("  RECHARGING" if charging else ""), 44, col, a)
    wk = c.get("week")
    if wk:
        cw, gap = W * 0.085, W * 0.012; xs = (W - 7 * cw - 6 * gap) / 2; y = H * 0.60
        for i, lab in enumerate("MTWTFSS"):
            q = _p(t, wk["at"] + 0.06 * i, 0.3); x = xs + i * (cw + gap); tr = i in wk["train"]
            d.rounded_rectangle((x, y, x + cw, y + cw), radius=ctx.px(12), fill=(T.ORANGE if tr else (32, 52, 40)) + (int(235 * q),)); _label(d, ctx, (x + cw / 2, y + ctx.px(14)), lab, 40, T.WHITE, q)
            _label(d, ctx, (x + cw / 2, y + cw - ctx.px(40)), "TRAIN" if tr else "REST", 20, T.WHITE if tr else GREEN, q, head=False)

def draw_clipboard(cv, ctx, c, t):
    d = ImageDraw.Draw(cv, "RGBA"); W, H = ctx.W, ctx.H; a = _p(t, _open(c), 0.35); bw, bh = W * 0.40, H * 0.72; x0, y0 = (W - bw) / 2, H * 0.06 + (1 - T.ease_out(a)) * ctx.px(60)
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=ctx.px(22), fill=(120, 84, 52, int(255 * a)))
    m = ctx.px(28); d.rounded_rectangle((x0 + m, y0 + m * 2, x0 + bw - m, y0 + bh - m), radius=ctx.px(10), fill=(240, 237, 230, int(255 * a)))
    d.rounded_rectangle((x0 + bw * 0.33, y0 - ctx.px(14), x0 + bw * 0.67, y0 + m * 2 + ctx.px(10)), radius=ctx.px(12), fill=(150, 150, 158, int(255 * a)))
    _label(d, ctx, (x0 + bw / 2, y0 + m * 2 + ctx.px(26)), "THE PLAN", 48, (30, 30, 34), a)
    rh = (bh - ctx.px(250)) / max(4, len(c["items"])); ry = y0 + m * 2 + ctx.px(110)
    for i, it in enumerate(c["items"]):
        q = _p(t, it["at"], 0.35); y = ry + i * rh; bx = x0 + m + ctx.px(26); s = ctx.px(34)
        if q <= 0: continue
        d.rounded_rectangle((bx, y, bx + s, y + s), radius=ctx.px(6), outline=(60, 60, 66, int(255 * q)), width=ctx.px(4))
        tk = _p(t, it["at"] + 0.25, 0.3)
        if tk > 0: d.line((bx + s * 0.18, y + s * 0.55, bx + s * 0.42, y + s * 0.8, bx + s * (0.18 + 0.75 * tk), y + s * (0.8 - 0.75 * tk)), fill=(34, 160, 80, 255), width=ctx.px(6))
        _label(d, ctx, (bx + s + ctx.px(22), y - ctx.px(4)), it["text"], 34 if len(it["text"]) < 22 else 26, (34, 34, 38), q, centre=False)
    if c.get("foot"):
        q = T.ease_back(_p(t, c["marks"][-1] + 0.4, 0.4)); _label(d, ctx, (x0 + bw / 2, y0 + bh - m - ctx.px(80)), c["foot"], 36, T.ORANGE_DEEP, q)

def draw_road(cv, ctx, c, t):
    d = ImageDraw.Draw(cv, "RGBA"); W, H = ctx.W, ctx.H; a = _p(t, _open(c), 0.35); hy = H * 0.30; cx = W * 0.5
    d.polygon([(cx - W * 0.02, hy), (cx + W * 0.02, hy), (cx + W * 0.42, H), (cx - W * 0.42, H)], fill=(44, 44, 48, int(255 * a)))
    for e in (-1, 1): d.line((cx + e * W * 0.02, hy, cx + e * W * 0.42, H), fill=T.SOFT_WHITE + (int(200 * a),), width=ctx.px(4))
    off = (t * 0.6) % 1.0      # the centre dashes keep moving toward the viewer
    for k in range(9):
        u0 = ((k + off) / 9) ** 2; u1 = ((k + off + 0.45) / 9) ** 2; y_0, y_1 = hy + (H - hy) * u0, hy + (H - hy) * min(1.0, u1)
        d.polygon([(cx - ctx.px(2) - 10 * u0 * ctx.S, y_0), (cx + ctx.px(2) + 10 * u0 * ctx.S, y_0), (cx + ctx.px(2) + 10 * u1 * ctx.S, y_1), (cx - ctx.px(2) - 10 * u1 * ctx.S, y_1)], fill=T.ORANGE + (int(220 * a),))
    n = len(c["signs"])
    for i, s in enumerate(c["signs"]):
        q = T.ease_back(_p(t, s["at"], 0.4))
        if q <= 0: continue
        u = 0.85 - 0.55 * i / max(1, n); y = hy + (H - hy) * u * u; e = -1 if i % 2 == 0 else 1; x = cx + e * (W * 0.02 + W * 0.40 * u * u + W * 0.06 * u); k = 0.5 + 0.6 * u
        d.line((x, y, x, y - ctx.px(130) * k * q), fill=(150, 150, 158, 255), width=max(2, int(ctx.px(8) * k)))
        f = ctx.font(T.HEAD_FONT, int(40 * k)); tw = D._text_w(d, s["text"], f, ctx.px(2)) + ctx.px(36) * k; top = y - ctx.px(130) * k * q - ctx.px(64) * k
        d.rounded_rectangle((x - tw / 2, top, x + tw / 2, top + ctx.px(64) * k), radius=ctx.px(10), fill=(32, 120, 70, int(255 * min(1, q))))
        D.text_spaced(d, (x - tw / 2 + ctx.px(18) * k, top + ctx.px(10) * k), s["text"], f, T.WHITE + (int(255 * min(1, q)),), ctx.px(2))
    q = T.ease_back(_p(t, c["goal_at"], 0.5))      # the goal flag at the horizon
    if q > 0:
        fx, fy = cx + W * 0.03, hy; d.line((fx, fy, fx, fy - ctx.px(150) * q), fill=T.WHITE + (255,), width=ctx.px(5))
        d.polygon([(fx, fy - ctx.px(150) * q), (fx + ctx.px(70) * q, fy - ctx.px(125) * q), (fx, fy - ctx.px(100) * q)], fill=T.RED + (255,))
        _label(d, ctx, (fx + ctx.px(20), fy - ctx.px(230) * q), c["goal"], 64, T.ORANGE, q, centre=False)

def draw_silrow(cv, ctx, c, t):
    W, H = ctx.W, ctx.H; n = len(c["items"]); bw = W * 0.84 / n; bh = H * 0.46; x0 = W * 0.08; y1 = H * 0.66; d = ImageDraw.Draw(cv, "RGBA")
    cur = max([i for i, it in enumerate(c["items"]) if t >= it["at"]], default=-1)
    for i, it in enumerate(c["items"]):
        q = _p(t, it["at"] - 0.15, 0.35)
        if q <= 0: continue
        try: im = ctx.art(it["art"])
        except Exception: continue
        k = min((bw - ctx.px(30)) / im.width, bh / im.height); im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
        col = T.ORANGE if i == cur else (120, 120, 128); sil = Image.new("RGBA", im.size, tuple(col) + (255,)); sil.putalpha(im.getchannel("A").point(lambda v, q=q: int(v * q)))
        cx = x0 + bw * (i + 0.5); cv.paste(sil, (int(cx - im.width / 2), int(y1 - im.height + (1 - T.ease_out(q)) * ctx.px(30))), sil); d = ImageDraw.Draw(cv, "RGBA")
        _label(d, ctx, (cx, y1 + ctx.px(20)), it["label"], 32 if len(it["label"]) < 12 else 24, T.WHITE if i == cur else T.GREY, q)
        if i: _arrow(d, (cx - bw * 0.62, y1 - bh * 0.4), (cx - bw * 0.42, y1 - bh * 0.4), T.GREY + (int(220 * q),), ctx.px(4), ctx.px(16))

DRAW = {"silrow": draw_silrow, "lever": draw_lever, "seesaw": draw_seesaw, "gap": draw_gap, "split": draw_split, "panels": draw_panels, "tearoff": draw_tearoff, "battery": draw_battery, "clipboard": draw_clipboard, "road": draw_road}

def draw(cv: Image.Image, ctx: D.Ctx, kind: str, c: dict, t_abs: float) -> None:
    DRAW[kind](cv, ctx, c, t_abs)
