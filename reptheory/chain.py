"""The progression chain: the spine of a video whose script walks through numbered units (links, moves, moments, steps, levels, holds...), as in
docs/rep_theory/HOW_THE_CHANNEL_EDITS.md section 2 (the 7 links of the planche video, the 4 moments of the arm-wrestling video).
Built from the script itself, so every script gets its own chain:
  items    the names of a count card the script already shows ("four moments: the go, the wrist ...") when its count matches the units, else the units' own names
  targets  each unit's first stated target ("30 seconds" -> 30 S, "three holds of 15 seconds" -> 3 × 15 S)
  warning  a unit that warns (its section or sentences name a warning, pain, injury) gets a warning mark
Shown full screen for CHAIN_S at the start of every unit (done units ticked, the current one lit with YOU, later ones locked), and once more at the end of the
video with every unit done (the callback). It needs at least MIN_ITEMS units; a script without them is unchanged."""
from __future__ import annotations
import math, re
from typing import Dict, List, Optional

from PIL import Image, ImageDraw

from . import draw as D, theme as T

STEP_RX = re.compile(r"^(LINK|MOVE|MOMENT|STEP|LEVEL|HOLD|PHASE|STAGE|EXERCISE|DRILL|TIP|RULE|DAY|WEEK|PART)\s+(\d+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)\b\s*[·:\-–]?\s*(.*)$", re.I)
WORDS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10}
WARN_RX = re.compile(r"\b(warning|injur\w*|hurt\w*|pain|danger\w*|careful|risk\w*)\b", re.I)
SETS_RX = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:holds?|sets?|rounds?)\s+of\s+(\d+|ten|fifteen|twenty|thirty|forty|five|sixty)\s*(seconds?|s|reps?)\b", re.I)
MIN_ITEMS, CHAIN_S, END_S = 3, 1.8, 2.6

def _num(s: str) -> int:
    s = s.strip().upper(); return int(s) if s.isdigit() else WORDS.get(s, {"FIFTEEN": 15, "TWENTY": 20, "THIRTY": 30, "FORTY": 40, "SIXTY": 60}.get(s, 0))

def step_units(scenes: List[dict]) -> List[dict]:
    """[{n, word, name, scenes}] for the numbered units, in order (one entry per unit even when its scenes are split)."""
    out: List[dict] = []
    for sc in scenes:
        m = STEP_RX.match((sc.get("section") or "").strip())
        if not m: continue
        n = _num(m.group(2))
        if out and out[-1]["n"] == n and out[-1]["word"] == m.group(1).upper(): out[-1]["scenes"].append(sc); continue
        out.append({"n": n, "word": m.group(1).upper(), "name": (m.group(3) or "").strip().upper() or f"{m.group(1).upper()} {n}", "scenes": [sc]})
    return out

def _target(text: str) -> str:
    """A unit's first stated target, short ("3 × 15 S", "30 S", "10 REPS"), or ""."""
    m = SETS_RX.search(text)
    if m: return f"{_num(m.group(1))} × {_num(m.group(2))} {'S' if m.group(3).lower().startswith('s') else 'REPS'}"
    from . import narrative as N
    for e in N.entities(text)["numbers"]:
        u = str(e["unit"]).upper()
        if u in ("S", "SEC", "SECONDS", "SECOND"): return f"{e['value']} S"
        if u in ("REPS", "REP", "MIN", "MINUTES"): return f"{e['value']} {u[:4]}"
    return ""

def plan(scenes: List[dict]) -> int:
    """Puts sc["chain"] on each unit's first scene and on the last scene. Returns how many chain moments were placed (0 when the script has no units)."""
    units = step_units(scenes)
    if len(units) < 1: return 0
    csv = next((sc["graphic_csv"] for sc in scenes if (sc.get("graphic_csv") or {}).get("kind") == "chain"), None)      # the CSV spelled the chain out: it wins
    slots = next((sc.get("slots") for sc in scenes if sc.get("kind") == "slots" and sc.get("slots")), None)
    words = {u["word"] for u in units}
    if csv and len(csv["items"]) >= len(units): items = [dict(it) for it in csv["items"]]; pos = {id(u): min(len(items) - 1, i) for i, u in enumerate(units)} if not all(1 <= u["n"] <= len(items) for u in units) else {id(u): u["n"] - 1 for u in units}
    elif slots and slots["noun"].upper() in words and all(it["text"] for it in slots["items"]):
        items = [{"name": it["text"], "target": "", "warn": False} for it in slots["items"]]; pos = {id(u): u["n"] - 1 for u in units}      # the count card's own names: the chain the viewer already met
    elif len(units) >= MIN_ITEMS: items = [{"name": u["name"], "target": "", "warn": False, "n": u["n"]} for u in units]; pos = {id(u): i for i, u in enumerate(units)}      # by position: a script may start at "rule two"
    else: return 0
    noun = next(iter(words)) if len(words) == 1 else "STEP"
    for u in units:      # each unit's target and warning go to its card
        k = pos[id(u)]
        if 0 <= k < len(items):
            text = " ".join(sc.get("script_text") or sc.get("text", "") for sc in u["scenes"]); items[k]["target"] = items[k]["target"] or _target(text)
            items[k]["warn"] = items[k]["warn"] or bool(WARN_RX.search(u["name"])) or bool(WARN_RX.search(text[:200]))
    n = 0
    for u in units:
        sc = u["scenes"][0]
        k = pos[id(u)]
        if sc["end"] - sc["start"] >= CHAIN_S + 1.0 and 0 <= k < len(items):
            sc["chain"] = {"noun": noun, "items": items, "current": k, "at": sc["start"], "dur": CHAIN_S}; sc["decisions"].append(f"chain: {noun} {k + 1} of {len(items)} opens the unit"); n += 1
    last = scenes[-1]
    if n and last["end"] - last["start"] >= 2.2 and not last.get("chain"):      # a short last scene still gets the callback, shorter
        dur = min(END_S, last["end"] - last["start"] - 0.4); last["chain"] = {"noun": noun, "items": items, "current": None, "at": last["end"] - dur, "dur": dur, "done": True}; last["decisions"].append("chain: the callback at the end, every unit done"); n += 1
    return n

def done_at(ch: dict) -> float: return ch["at"] + ch["dur"]

def draw(cv: Image.Image, ctx: D.Ctx, ch: dict, t_abs: float) -> None:
    """The chain full screen over the scene for its moment: a dark backdrop, the cards popping in, done ticked, the current one lit and lifted with YOU over it,
    later ones locked, warnings marked; it fades out into the scene."""
    u = t_abs - ch["at"]
    if u < 0 or u > ch["dur"]: return
    a = min(1.0, u / 0.25, (ch["dur"] - u) / 0.3); items = ch["items"]; n = len(items); cur = ch.get("current"); all_done = ch.get("done")
    back = Image.new("RGBA", cv.size, (8, 8, 10, int(235 * a))); cv.paste(back, (0, 0), back); d = ImageDraw.Draw(cv, "RGBA")
    title = ("EVERY " + ch["noun"] + " DONE") if all_done else f"{ch['noun']} {items[cur].get('n', cur + 1)}" if cur is not None else f"{n} {ch['noun']}S"      # the script's own numbers ("rule two")
    f_t = ctx.font(T.HEAD_FONT, 96); tw = D._text_w(d, title, f_t, ctx.px(2)); D.text_spaced(d, (ctx.W / 2 - tw / 2, ctx.H * 0.16), title, f_t, T.WHITE + (int(255 * a),), ctx.px(2))
    if cur is not None and items[cur]["name"]:
        f_s = ctx.font(T.BODY_FONT, 40); sw = D._text_w(d, items[cur]["name"], f_s, ctx.px(4)); D.text_spaced(d, (ctx.W / 2 - sw / 2, ctx.H * 0.16 + ctx.px(112)), items[cur]["name"], f_s, T.ORANGE + (int(255 * a),), ctx.px(4))
    gap = ctx.px(22); cw = min(ctx.px(230), int((ctx.W * 0.86 - gap * (n - 1)) / n)); ch_h = int(cw * 1.15); x0 = (ctx.W - (n * cw + (n - 1) * gap)) / 2; y0 = int(ctx.H * 0.50)
    for i, it in enumerate(items):
        p = T.ease_back(min(1.0, max(0.0, (u - 0.06 * i) / 0.35))); done = all_done or (cur is not None and i < cur); live = cur == i
        lift = int(ctx.px(26) * T.ease_out(min(1.0, max(0.0, (u - 0.4) / 0.4)))) if live else 0; s = 0.9 + 0.1 * p + (0.08 if live else 0.0)
        cx, cy = x0 + i * (cw + gap) + cw / 2, y0 + ch_h / 2 - lift; w2, h2 = cw * s / 2, ch_h * s / 2
        col = (74, 222, 128) if done else T.RED if live else (250, 196, 40) if it["warn"] else (70, 70, 76)
        d.rounded_rectangle((cx - w2, cy - h2, cx + w2, cy + h2), radius=ctx.px(16), fill=(26, 26, 29, int(255 * a * min(1.0, p * 2))), outline=col + (int(255 * a * min(1.0, p * 2)),), width=ctx.px(6 if live else 3))
        if live:
            for k in range(3): rr = ctx.px(6) * (k + 1); d.rounded_rectangle((cx - w2 - rr, cy - h2 - rr, cx + w2 + rr, cy + h2 + rr), radius=ctx.px(18), outline=T.RED + (int(70 * a / (k + 1)),), width=ctx.px(3))
        dim = 1.0 if (live or done) else 0.5
        f_h = ctx.font(T.BODY_FONT, 24); hd = f"{ch['noun']} {it.get('n', i + 1)}"; hw = D._text_w(d, hd, f_h, ctx.px(3)); D.text_spaced(d, (cx - hw / 2, cy - h2 + ctx.px(16)), hd, f_h, T.GREY + (int(255 * a * dim),), ctx.px(3))
        if it["warn"] and not done:      # a warning triangle in place of the number
            r = ctx.px(34); d.polygon([(cx, cy - r - ctx.px(10)), (cx - r, cy + r * 0.6 - ctx.px(10)), (cx + r, cy + r * 0.6 - ctx.px(10))], fill=(250, 196, 40, int(255 * a * dim)))
        else:
            f_n = ctx.font(T.HEAD_FONT, 84); nn = str(it.get("n", i + 1)); nw = D._text_w(d, nn, f_n, 0); D.text_spaced(d, (cx - nw / 2, cy - ctx.px(66)), nn, f_n, ((74, 222, 128) if done else T.ORANGE if live else T.SOFT_WHITE) + (int(255 * a * dim),), 0)
        f_m = ctx.font(T.HEAD_FONT, 30); lines = D._wrap(d, it["name"], f_m, cw * s - ctx.px(24)) or [""]
        for k, ln in enumerate(lines[:2]): lw = D._text_w(d, ln, f_m, ctx.px(1)); D.text_spaced(d, (cx - lw / 2, cy + ctx.px(34) + k * ctx.px(36)), ln, f_m, T.WHITE + (int(255 * a * dim),), ctx.px(1))
        by = cy + h2 + ctx.px(14)      # under the card: its target with a tick (done) or a lock (to come)
        if it["target"] or not done:
            lab = it["target"] or ""; f_b = ctx.font(T.BODY_FONT, 24); lw = D._text_w(d, lab, f_b, ctx.px(2)) + ctx.px(34)
            if done: d.line((cx - lw / 2, by + ctx.px(14), cx - lw / 2 + ctx.px(8), by + ctx.px(22)), fill=(74, 222, 128, int(255 * a)), width=ctx.px(4)); d.line((cx - lw / 2 + ctx.px(8), by + ctx.px(22), cx - lw / 2 + ctx.px(22), by + ctx.px(4)), fill=(74, 222, 128, int(255 * a)), width=ctx.px(4))
            else: d.rectangle((cx - lw / 2, by + ctx.px(10), cx - lw / 2 + ctx.px(16), by + ctx.px(26)), fill=(232, 64, 52, int(255 * a * dim))); d.arc((cx - lw / 2 + ctx.px(2), by, cx - lw / 2 + ctx.px(14), by + ctx.px(16)), 180, 360, fill=(232, 64, 52, int(255 * a * dim)), width=ctx.px(3))
            if lab: D.text_spaced(d, (cx - lw / 2 + ctx.px(30), by + ctx.px(2)), lab, f_b, T.SOFT_WHITE + (int(255 * a * dim),), ctx.px(2))
        if live and u > 0.5:
            D.pill(cv, ctx, cx - ctx.px(46), cy - h2 - ctx.px(64), "YOU", min(1.0, (u - 0.5) / 0.3), accent=T.RED)
        if i < n - 1:      # the link between cards
            lx = cx + w2 + ctx.px(2); d.line((lx, cy, lx + gap - ctx.px(4), cy), fill=((74, 222, 128) if done else (70, 70, 76)) + (int(220 * a),), width=ctx.px(3))
