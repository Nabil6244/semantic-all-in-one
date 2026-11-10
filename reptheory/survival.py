"""Survival cards (theme "survival"), every one driven by the narration: nothing appears until the narrator says it, and it appears on the word that says it.

- number: "That's number 22." -> a big hand-drawn 22 with an ink circle on the word "twenty-two"; then a small badge with progress dots for the rest of the item.
  Only the real countdown counts: the announcements that run down one by one (a tease like "And number one is a sickness ..." in the opening is not an item).
- strip: what the item costs, how long it takes and how easy it is, each chip on the word that says it ("about $2", "takes three days", "a child can do it");
  never guessed: an item whose narration says none of them gets no strip.
- tracker: the teased ending ("number one", "remember that thing", "hold on to that", "at the end") -> a small locked box shakes in on that word; it opens when
  number one is announced (countdown) or when the payoff starts ("Remember that thing ...", in the last third).
- rule: "The one rule that matters: ..." / "Here's the rule ..." -> a field-notebook note whose words are written in as they are spoken.
Plan-only functions (plan) set sc["sv"]; draw() paints them over the frame. Pure Python + PIL, no render time beyond the overlay."""
from __future__ import annotations
import math, re
from typing import Dict, List, Optional

from PIL import Image, ImageDraw

from . import draw as D, lexicon as LX, theme as T

NUM = LX.NUM
ANNOUNCE_RX = re.compile(r"\b(?:number|no\.|#)\s*(" + NUM[1:-1] + r")\b", re.I)
CARD_S, BURST_S = 1.7, 0.5      # the big number holds this long on its word, then shrinks into the badge
TEASE_RX = re.compile(r"\b(?:number one\b|the number one\b|remember (?:that|this|the)\b|hold on to (?:that|this)\b|keep (?:that|this) in mind\b|at the (?:very )?end\b|by the end\b)", re.I)
PAYOFF_RX = re.compile(r"\bremember (?:that|this|the)\b", re.I)
TEASE_S = 3.0
RULE_RX = re.compile(r"\b(?:the one rule(?: that (?:matters|counts))?|one rule|the (?:golden |first |only )?rule (?:underneath (?:all )?(?:of )?(?:this|it)|here|is)|here'?s the (?:one |golden )?rule(?: underneath (?:all )?(?:of )?(?:this|it))?)\b\s*[:,]?\s*", re.I)
RULE_MAX_W, RULE_HOLD_S = 16, 2.5
UNIT = r"(seconds?|minutes?|hours?|days?|weeks?|months?|years?)"
TIME_RX = re.compile(r"\b(?:takes?|took|taking|in|for|within|after|learn(?:ed)? in)\s+(?:about|around|roughly|just|only|under|over|less than|maybe)?\s*(" + NUM[1:-1] + r"|an?|one)\s+" + UNIT + r"\b"
                     r"|\b(" + NUM[1:-1] + r"|an?|one)\s+" + UNIT + r"\s+to\s+(?:learn|make|build|set up|do|dry|sprout|cure|finish)\b", re.I)
COST_RX = re.compile(r"(\$\s?\d[\d,]*(?:\.\d+)?)|\b(" + NUM[1:-1] + r")\s+dollars?\b|\b(costs? (?:nothing|next to nothing)|for free|(?:doesn't|does not|won't) cost (?:a|you a)? ?(?:thing|dime|penny|cent|single (?:dime|penny|cent))|free\b(?! from| of))", re.I)
EASY_RX = re.compile(r"\b(?:a (?:child|kid)|kids|anyone|anybody|any(?:one|body) can)\b[^.]{0,30}\b(?:can|could)\b|\b(?:any(?:one|body)|a (?:child|kid)) can\b|\b(?:dead simple|easy|simplest|easiest)\b", re.I)
HARD_RX = re.compile(r"\b(?:takes (?:real )?practice|hardest|tricky|takes skill|goes wrong the first time)\b", re.I)


def _stream(scenes: List[dict]) -> list:
    """Every spoken word once, in time order, with its scene: [{w, t0, t1, p, sc}]."""
    out, seen = [], set()
    for sc in scenes:
        for w in sc.get("words") or []:
            k = (round(float(w["t0"]), 3), w["w"])
            if k in seen: continue
            seen.add(k); out.append(dict(w, sc=sc))
    out.sort(key=lambda w: float(w["t0"])); return out

def _sentences(ws: list) -> list:
    """[(first index, last index)] of the spoken sentences."""
    out, i0 = [], 0
    for i, w in enumerate(ws):
        if re.search(r"[.!?]", w.get("p", "")) or i == len(ws) - 1: out.append((i0, i)); i0 = i + 1
    return out

def _text_map(ws: list, a: int, b: int):
    """The words a..b as one text, and the word index each character belongs to."""
    txt, idx = "", []
    for i in range(a, b + 1):
        piece = ws[i]["w"] + ws[i].get("p", "") + " "; txt += piece; idx += [i] * len(piece)
    return txt, idx

def _num(tok: str) -> Optional[int]:
    v = LX.num(tok.strip().lower())
    try: return int(float(v))
    except (TypeError, ValueError): return {"a": 1, "an": 1, "one": 1}.get(tok.strip().lower())

def _scene_at(scenes: List[dict], t: float) -> Optional[dict]:
    for sc in scenes:
        if sc["start"] - 1e-6 <= t < sc["end"]: return sc
    return scenes[-1] if scenes and t >= scenes[-1]["start"] else None

def _sv(sc: dict) -> dict: return sc.setdefault("sv", {})

def countdown(ws: list, sents: list) -> List[dict]:
    """The real countdown: announcements whose number runs down by one ([{n, at, i}] in time order). The longest such run wins; fewer than 3 is no countdown."""
    cands = []
    for a, b in sents:
        txt, idx = _text_map(ws, a, b)
        for m in ANNOUNCE_RX.finditer(txt):
            if len(txt[:m.start()].split()) > 3: continue      # "That's number 22." / "Number 15 works like this." : said at the start of its sentence
            n = _num(m.group(1))
            if n is not None and 1 <= n <= 100: cands.append({"n": n, "at": float(ws[idx[m.start(1)]]["t0"]), "i": idx[m.start(1)]})
    best: List[dict] = []
    for k, c in enumerate(cands):
        run, want = [c], c["n"] - 1
        for d in cands[k + 1:]:
            if d["n"] == want: run.append(d); want -= 1
        if len(run) > len(best): best = run
    return best if len(best) >= 3 else []

def _facts(ws: list, sents: list, t0: float, t1: float) -> List[dict]:
    """What an item says it costs, how long it takes and how easy it is, each at its own word (the first of each kind only)."""
    out: Dict[str, dict] = {}
    for a, b in sents:
        if float(ws[b]["t0"]) < t0 - 1e-6 or float(ws[a]["t0"]) >= t1: continue
        txt, idx = _text_map(ws, a, b)
        inside = lambda m: m is not None and t0 - 1e-6 <= float(ws[idx[m.start()]]["t0"]) < t1      # the words said inside this item only (not the next item's "Number four takes ...")
        if "cost" not in out:
            m = COST_RX.search(txt)
            if inside(m):
                if m.group(1): label = m.group(1).replace(" ", "")
                elif m.group(2): label = f"${_num(m.group(2))}" if _num(m.group(2)) is not None else ""
                else: label = "FREE"
                if label: out["cost"] = {"kind": "cost", "text": label, "at": float(ws[idx[m.start()]]["t0"])}
        if "time" not in out:
            m = TIME_RX.search(txt)
            if inside(m):
                n_tok, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
                n = _num(n_tok)
                if n: out["time"] = {"kind": "time", "text": f"{n} {unit.rstrip('s') if n == 1 else (unit if unit.endswith('s') else unit + 's')}".upper(), "at": float(ws[idx[m.start()]]["t0"])}
        if "level" not in out:
            m = EASY_RX.search(txt) or HARD_RX.search(txt)
            if inside(m): out["level"] = {"kind": "level", "text": "EASY" if EASY_RX.search(m.group(0)) else "TAKES PRACTICE", "dots": 1 if EASY_RX.search(m.group(0)) else 3, "at": float(ws[idx[m.start()]]["t0"])}
    return sorted(out.values(), key=lambda f: f["at"])

def _rule(ws: list, sents: list, k: int, m) -> Optional[dict]:
    a, b = sents[k]; txt, idx = _text_map(ws, a, b)
    i = idx[min(m.end(), len(idx) - 1)] if m.end() < len(txt.rstrip()) else b + 1
    words = ws[i:b + 1] if i <= b else []
    if len(words) < 3 and k + 1 < len(sents): a2, b2 = sents[k + 1]; words = ws[a2:b2 + 1]      # "Here's the rule underneath all of this." -> the next sentence is the rule
    if len(words) < 3: return None
    words = words[:RULE_MAX_W]
    return {"cue_at": float(ws[a]["t0"]), "words": [{"w": (w["w"] + w.get("p", "")).strip(), "t0": float(w["t0"])} for w in words], "end": float(words[-1]["t1"])}

def plan(scenes: List[dict]) -> Dict[str, int]:
    """Puts the survival cards on the scenes from the narration's words. Returns counts."""
    n = {"numbers": 0, "facts": 0, "teases": 0, "rules": 0}
    if not scenes: return n
    for sc in scenes: sc.pop("sv", None)
    tidy(scenes)
    ws = _stream(scenes)
    if not ws: return n
    sents = _sentences(ws); total_t = float(scenes[-1]["end"])
    run = countdown(ws, sents); total = run[0]["n"] if run else 0
    for j, c in enumerate(run):      # the big number on its word, then the badge until the next announcement
        nxt = run[j + 1]["at"] if j + 1 < len(run) else total_t
        sc = _scene_at(scenes, c["at"])
        if sc is None: continue
        _sv(sc).setdefault("numbers", []).append({"n": c["n"], "at": c["at"]}); n["numbers"] += 1      # two short items can share a scene
        badge = {"n": c["n"], "total": total, "from": c["at"] + CARD_S, "to": nxt}
        for x in scenes:
            if x["end"] > badge["from"] and x["start"] < nxt: _sv(x)["badge"] = badge
        facts = _facts(ws, sents, c["at"] - 2.5, nxt)      # the item starts at its hook, a sentence or so before the number
        if facts:
            strip = {"facts": facts, "to": nxt}
            for x in scenes:
                if x["end"] > facts[0]["at"] and x["start"] < nxt: _sv(x)["strip"] = strip
            n["facts"] += len(facts)
        _drop_repeats(sc, c["n"]); sc.pop("chapter_card", None)      # the big number opens the item: no second chapter card on top of it (fair test: "PART 03/03 · NUMBER 1" over the 1)
    one = next((c["at"] for c in run if c["n"] == 1), None)
    payoff = None
    if not run:      # one secret, many myths: the payoff is the last "Remember that thing ..." in the last third
        for a, b in sents:
            txt, idx = _text_map(ws, a, b); m = PAYOFF_RX.search(txt)
            if m and float(ws[a]["t0"]) >= total_t * 0.66: payoff = float(ws[idx[m.start()]]["t0"])
    end = one if one is not None else payoff
    if end is not None:
        label = "#1" if run else "STILL TO COME"
        for a, b in sents:
            txt, idx = _text_map(ws, a, b); m = TEASE_RX.search(txt); at = float(ws[idx[m.start()]]["t0"]) if m else None
            if at is None or at >= end - 1.0 or any(abs(at - c["at"]) < 0.5 for c in run): continue
            sc = _scene_at(scenes, at)
            if sc is not None and "tease" not in _sv(sc): _sv(sc)["tease"] = {"at": at, "label": label}; n["teases"] += 1
        sc = _scene_at(scenes, end)
        if sc is not None and n["teases"]: _sv(sc)["unlock"] = {"at": end, "label": label}
    for k, (a, b) in enumerate(sents):      # the one rule, written in as it is said
        txt, _ = _text_map(ws, a, b); m = RULE_RX.search(txt)
        if not m: continue
        r = _rule(ws, sents, k, m)
        if not r: continue
        r["to"] = r["end"] + RULE_HOLD_S; n["rules"] += 1
        for x in scenes:
            if x["end"] > r["cue_at"] and x["start"] < r["to"]:
                _sv(x)["rule"] = r
                for pg in x.get("pages", []):      # the note is where the words go: no headline or chip on top of it
                    if float(pg.get("headline_at", pg.get("at", 0))) >= r["cue_at"] - 0.2: pg["headline"] = ""
                    pg["chips"] = [ch for ch in pg.get("chips", []) if float(ch.get("at", 0)) < r["cue_at"] - 0.2]
                if x.get("stamp") and float(x["stamp"]["at"]) >= r["cue_at"] - 0.2: x.pop("stamp")
    from . import survival_formats as SF      # the extras of each format: thermal view, state map, timeline, name tag, price compare
    n.update(SF.plan(scenes, ws, sents, _text_map, run))
    return n

KICK_SAID = {"MISTAKE": re.compile(r"\bmistakes?\b", re.I), "STUDY": re.compile(r"\b(?:study|studies|researchers?|scientists?|trial)\b", re.I), "TEST": re.compile(r"\btest", re.I)}
UNIT_WORDS = {"S": "SECOND", "SEC": "SECOND", "MIN": "MINUTE", "H": "HOUR", "HR": "HOUR"}

def tidy(scenes: List[dict]) -> Dict[str, int]:
    """The gym explainer's habits that do not fit a field guide (fair test, 2026-11-10), each fixed as a rule:
    - a small kicker only when the narration says it: MISTAKE needs "mistake", STUDY a study, TEST a test; KEY and CUE are dropped ("MISTAKE · WOODS WEREN'T LOST" had no mistake in it);
    - a value with a one-letter unit is written out ("2 S" -> "2 SECONDS");
    - no red warning tint over the pictures: the one-rule note carries a danger, on its own words ("go wrong" tinted three shots red)."""
    n = {"kickers": 0, "values": 0, "tints": 0}
    for sc in scenes:
        text = sc.get("script_text") or sc.get("text", "")
        if sc.pop("tint", None) is not None: n["tints"] += 1
        for pg in sc.get("pages", []):
            k = (pg.get("kicker") or "").upper()
            if k and not (k in KICK_SAID and KICK_SAID[k].search(text)): pg["kicker"] = ""; n["kickers"] += 1
            m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(S|SEC|MIN|H|HR)\s*", str(pg.get("value") or ""), re.I)
            if m:
                w = UNIT_WORDS[m.group(2).upper()]; pg["value"] = f"{m.group(1)} {w if float(m.group(1)) == 1 else w + 'S'}"; n["values"] += 1
    return n

def _drop_repeats(sc: dict, num: int) -> None:
    """The big number says it: a headline, chip or stamp of the same number ("#22", "NUMBER TWENTY-TWO", "THAT'S NUMBER 22") is left out of its scene."""
    from . import gate as G
    said = {f"#{num}"}
    for pg in sc.get("pages", []):
        if pg.get("headline") and G.repeats(pg["headline"], said): pg["headline"] = ""
        pg["chips"] = [ch for ch in pg.get("chips", []) if not G.repeats(ch.get("text", ""), said)]
    if sc.get("stamp") and G.repeats(sc["stamp"]["text"], said): sc.pop("stamp")


# ---- drawing -------------------------------------------------------------------------------------------

def _ink(a: float) -> tuple: return T.WHITE + (int(255 * max(0.0, min(1.0, a))),)

def _hand_circle(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, p: float, col: tuple, w: int, seed: int) -> None:
    """An ink circle drawn by hand: one stroke that runs a little past its start, slightly wobbly, grown to p (0..1)."""
    pts, steps = [], max(2, int(72 * p))
    for i in range(steps + 1):
        u = i / 72; ang = -math.pi * 0.62 + u * math.pi * 2.18; wob = 1.0 + 0.035 * math.sin(u * 9 + seed) + 0.02 * math.sin(u * 23 + seed * 2)
        pts.append((cx + math.cos(ang) * r * 1.12 * wob, cy + math.sin(ang) * r * 0.92 * wob))
    if len(pts) > 1: d.line(pts, fill=col, width=w, joint="curve")

def _number_card(cv: Image.Image, ctx: D.Ctx, num: dict, t: float) -> None:
    ts = t - num["at"]
    if ts < 0 or ts > CARD_S + BURST_S: return
    lay = Image.new("RGBA", cv.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    fade = 1.0 if ts < CARD_S else max(0.0, 1.0 - (ts - CARD_S) / BURST_S)
    d.rectangle((0, 0, ctx.W, ctx.H), fill=T.BG_TOP + (int(150 * min(1.0, ts / 0.2) * fade),))      # the picture steps back behind the number
    s = 0.86 + 0.14 * T.ease_back(min(1.0, ts / 0.35)); f = ctx.font(T.HEAD_FONT, int(300 * s)); txt = str(num["n"])
    cx, cy = ctx.W / 2, ctx.H * 0.5; bb = d.textbbox((0, 0), txt, font=f); tw = bb[2] - bb[0]
    d.text((cx - (bb[0] + bb[2]) / 2, cy - (bb[1] + bb[3]) / 2), txt, font=f, fill=_ink(fade))      # centred on its own ink, so the circle sits round it
    _hand_circle(d, cx, cy, max(tw / 2 + ctx.px(70), ctx.px(190)), min(1.0, max(0.0, (ts - 0.15) / 0.55)), T.ORANGE + (int(255 * fade),), ctx.px(9), num["n"])
    fs = ctx.font(T.BODY_FONT, 30); lab = "NUMBER"; lw = D._text_w(d, lab, fs, ctx.px(6))
    D.text_spaced(d, (cx - lw / 2, cy - max(tw / 2 + ctx.px(70), ctx.px(190)) - ctx.px(60)), lab, fs, T.SOFT_WHITE + (int(255 * fade * min(1.0, ts / 0.3)),), ctx.px(6))
    cv.alpha_composite(lay) if cv.mode == "RGBA" else cv.paste(lay, (0, 0), lay)

def _badge(cv: Image.Image, ctx: D.Ctx, b: dict, t: float) -> None:
    if not (b["from"] <= t < b["to"]): return
    d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, (t - b["from"]) / 0.35, (b["to"] - t) / 0.25); r = ctx.px(44); cx, cy = ctx.W - ctx.px(96), ctx.px(92)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=T.PLATE + (int(235 * a),)); _hand_circle(d, cx, cy, r * 0.93, 1.0, T.ORANGE + (int(255 * a),), ctx.px(4), b["n"])
    f = ctx.font(T.HEAD_FONT, 46 if b["n"] < 10 else 40); bb = d.textbbox((0, 0), str(b["n"]), font=f); d.text((cx - (bb[0] + bb[2]) / 2, cy - (bb[1] + bb[3]) / 2), str(b["n"]), font=f, fill=_ink(a))
    tot = b.get("total") or 0
    if tot >= 5:      # how far through the countdown: one dot per item, the done ones filled, counting down from the top number
        done = tot - b["n"] + 1; gap = ctx.px(26 if tot <= 30 else 16); dr = ctx.px(7 if tot <= 30 else 5); x0 = ctx.W / 2 - (tot - 1) * gap / 2; y = ctx.H - ctx.px(34)
        for k in range(tot):
            x = x0 + k * gap; on = k < done
            d.ellipse((x - dr, y - dr, x + dr, y + dr), fill=(T.ORANGE if k == done - 1 else T.WHITE if on else T.DIM) + (int(255 * a * (1.0 if on else 0.7)),))

def _strip(cv: Image.Image, ctx: D.Ctx, s: dict, t: float) -> None:
    if t >= s["to"]: return
    d = ImageDraw.Draw(cv, "RGBA"); x = ctx.W - ctx.px(60); y = ctx.px(160); f = ctx.font(T.BODY_FONT, 26)
    names = {"cost": "COSTS", "time": "TAKES", "level": ""}
    for fa in s["facts"]:      # top right under the badge, one chip per fact, each from the word that says it
        ts = t - fa["at"]
        if ts < 0: continue
        a = min(1.0, ts / 0.3, (s["to"] - t) / 0.25); e = T.ease_back(min(1.0, ts / 0.4))
        label = fa["text"] if fa["text"] == "FREE" else (names[fa["kind"]] + " " + fa["text"]).strip()
        dots = fa.get("dots"); w = D._text_w(d, label, f, ctx.px(2)) + ctx.px(36) + (ctx.px(64) if dots else 0); h = ctx.px(46)
        x0 = x - w + int((1 - e) * ctx.px(40))
        d.rounded_rectangle((x0, y, x0 + w, y + h), radius=ctx.px(10), fill=T.PLATE + (int(235 * a),), outline=T.DIM + (int(255 * a),), width=ctx.px(2))
        D.text_spaced(d, (x0 + ctx.px(18), y + ctx.px(8)), label, f, (T.ORANGE if fa["kind"] == "cost" else T.WHITE) + (int(255 * a),), ctx.px(2))
        if dots:
            for k in range(3):
                cx = x0 + w - ctx.px(56) + k * ctx.px(16); cy = y + h / 2; r = ctx.px(5)
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(T.ORANGE if k < dots else T.DIM) + (int(255 * a),))
        y += h + ctx.px(12)

def _lock(d: ImageDraw.ImageDraw, ctx: D.Ctx, x: float, y: float, s: float, open_p: float, a: float) -> None:
    col = T.ORANGE + (int(255 * a),); lift = s * 0.55 * open_p
    d.arc((x - s * 0.62, y - s * 1.25 - lift, x + s * 0.62, y + s * 0.15 - lift), 180, 360, fill=col, width=ctx.px(5))
    d.rounded_rectangle((x - s, y - s * 0.4, x + s, y + s * 1.05), radius=ctx.px(5), fill=col)

def _tracker(cv: Image.Image, ctx: D.Ctx, sv: dict, t: float) -> None:
    d = ImageDraw.Draw(cv, "RGBA"); f = ctx.font(T.HEAD_FONT, 44)
    if sv.get("tease"):
        ts = t - sv["tease"]["at"]
        if 0 <= ts < TEASE_S:
            a = min(1.0, ts / 0.25, (TEASE_S - ts) / 0.3); shake = math.sin(ts * 38) * ctx.px(5) * max(0.0, 1.0 - ts / 0.9)
            x, y = ctx.px(110) + shake, ctx.H - ctx.px(120); _lock(d, ctx, x, y, ctx.px(34), 0.0, a)
            D.text_spaced(d, (x + ctx.px(56), y - ctx.px(8)), sv["tease"]["label"], f, _ink(a), ctx.px(2))
    if sv.get("unlock"):
        ts = t - sv["unlock"]["at"]
        if 0 <= ts < 1.6:
            a = min(1.0, ts / 0.2, (1.6 - ts) / 0.4); x, y = ctx.px(110), ctx.H - ctx.px(120); _lock(d, ctx, x, y, ctx.px(34), min(1.0, ts / 0.4), a)
            for k in range(8):      # a small burst as it opens
                ang = k * math.pi / 4; r0, r1 = ctx.px(40), ctx.px(40) + ctx.px(26) * min(1.0, ts / 0.5)
                d.line((x + math.cos(ang) * r0, y + math.sin(ang) * r0, x + math.cos(ang) * r1, y + math.sin(ang) * r1), fill=T.ORANGE + (int(255 * a),), width=ctx.px(4))

def _rule_note(cv: Image.Image, ctx: D.Ctx, sc: dict, r: dict, t: float) -> None:
    if not (r["cue_at"] <= t < r["to"]): return
    d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, (t - r["cue_at"]) / 0.3, (r["to"] - t) / 0.35); e = T.ease_back(min(1.0, (t - r["cue_at"]) / 0.45))
    side = (sc.get("_layout") or ("right",))[0]; w = int(ctx.W * 0.40); x0 = ctx.W - w - ctx.px(70) if side == "right" else ctx.px(70)
    f = ctx.font(T.HEAD_FONT, 50); fk = ctx.font(T.BODY_FONT, 26); lh = ctx.px(66)
    words = [x for x in r["words"] if x["t0"] <= t]; lines, cur = [], ""
    for x in r["words"]:      # wrap the whole rule once (so lines never reflow), then show the words already said
        test = (cur + " " + x["w"]).strip()
        if cur and D._text_w(d, test.upper(), f, ctx.px(1)) > w - ctx.px(80): lines.append(cur); cur = x["w"]
        else: cur = test
    if cur: lines.append(cur)
    h = ctx.px(120) + len(lines) * lh; y0 = int(ctx.H * 0.5 - h / 2 + (1 - e) * ctx.px(30))
    d.rounded_rectangle((x0 + ctx.px(8), y0 + ctx.px(10), x0 + w + ctx.px(8), y0 + h + ctx.px(10)), radius=ctx.px(6), fill=(0, 0, 0, int(28 * a)))      # soft shadow
    d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=ctx.px(6), fill=T.PLATE + (int(250 * a),), outline=T.RED + (int(255 * a),), width=ctx.px(4))
    for k in range(len(lines)): d.line((x0 + ctx.px(30), y0 + ctx.px(104) + (k + 1) * lh - ctx.px(6), x0 + w - ctx.px(30), y0 + ctx.px(104) + (k + 1) * lh - ctx.px(6)), fill=(150, 190, 220, int(110 * a)), width=ctx.px(2))      # notebook lines
    D.text_spaced(d, (x0 + ctx.px(36), y0 + ctx.px(34)), "THE ONE RULE", fk, T.RED + (int(255 * a),), ctx.px(5))
    said = len(words); k = 0; y = y0 + ctx.px(104)
    for ln in lines:
        shown = []
        for wd in ln.split():
            if k < said: shown.append(wd)
            k += 1
        if shown: D.text_spaced(d, (x0 + ctx.px(36), y), " ".join(shown).upper(), f, _ink(a), ctx.px(1))
        y += lh

def draw(cv: Image.Image, ctx: D.Ctx, sc: dict, t: float) -> None:
    """The survival cards on this frame (t: the video's own time, like tricks.draw)."""
    sv = sc.get("sv") or {}
    if sv.get("rule"): _rule_note(cv, ctx, sc, sv["rule"], t)
    if sv.get("strip"): _strip(cv, ctx, sv["strip"], t)
    if sv.get("badge"): _badge(cv, ctx, sv["badge"], t)
    if sv.get("tease") or sv.get("unlock"): _tracker(cv, ctx, sv, t)
    if any(k in sv for k in ("thermal", "state", "timeline", "persona", "prices")):
        from . import survival_formats as SF; SF.draw(cv, ctx, sc, t)
    for num in sv.get("numbers", []): _number_card(cv, ctx, num, t)
