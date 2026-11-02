"""Viewer questions (docs/rep_theory/PLAN_NEXT_GRAPHICS.md, Phase 5, tiles 31-32): a script that answers questions in turn ("Question one: how often should I train?",
"You asked: do I need weights?", "The most common question is ...") gets
  qlist    every question it will answer, as a list of comments with avatars, full screen at the line announcing them ("the five questions you ask most") or at the first question
  qtrack   a small Q tracker in the top-right corner from each question until the next one (done ticked, the current one lit, later ones grey)
It needs at least MIN_Q questions; a script without them is unchanged. The questions are the script's own words, never invented."""
from __future__ import annotations
import re
from typing import List

from PIL import ImageDraw, Image

from . import draw as D, theme as T

MIN_Q, LIST_S, LIST_MIN_S, MAX_CHARS = 2, 2.6, 1.8, 58
NUM = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|first|second|third|fourth|fifth|next|last|final)"
MARK_RX = re.compile(rf"\b(?:question\s+(?:number\s+)?{NUM}|(?:the\s+)?{NUM}\s+question|q\s*\d+|you\s+asked|(?:a\s+lot\s+of\s+)?(?:you|people)\s+(?:ask|asked|keep\s+asking)|someone\s+asked|the\s+most\s+common\s+question(?:\s+is)?)\b\s*[:,.-]?\s*", re.I)
ANNOUNCE_RX = re.compile(r"\b(?:\d+|two|three|four|five|six|seven|eight|nine|ten|your|top|common|biggest)\s+(?:most\s+)?(?:asked\s+)?questions\b", re.I)
AVATAR = ((96, 140, 220), (232, 120, 60), (90, 180, 120), (200, 90, 160), (220, 190, 70), (120, 120, 200))

def _question(text: str) -> tuple:
    """(question text, char position of its marker) for a sentence that poses a viewer question, else ("", -1)."""
    m = MARK_RX.search(text)
    if not m: return "", -1
    rest = text[m.end():]; q = re.match(r"\s*[\"“]?([^?]{4,120}\?)", rest)
    if not q: return "", -1
    s = re.sub(r"\s+", " ", q.group(1)).strip(" \"”"); s = s[0].upper() + s[1:]
    return (s if len(s) <= MAX_CHARS else s[:MAX_CHARS - 1].rsplit(" ", 1)[0] + "…?"), m.start()

def _at(sc: dict, pos: int) -> float:
    ws = sc.get("words") or []; i = len(sc.get("text", "")[:pos].split())
    return float(ws[min(i, len(ws) - 1)]["t0"]) if ws else float(sc["start"])

def plan(scenes: List[dict]) -> int:
    """Puts sc["qlist"] on the announcing (or first question's) scene and sc["qtrack"] on every scene from each question to the next. Returns how many overlays were placed."""
    qs = []
    for i, sc in enumerate(scenes):
        q, pos = _question(sc.get("text", ""))
        if q and not any(x["text"].lower() == q.lower() for x in qs): qs.append({"text": q, "i": i, "at": _at(sc, pos)})
    if len(qs) < MIN_Q: return 0
    items = [{"text": x["text"]} for x in qs]; n = 0
    host = next((i for i, sc in enumerate(scenes[:qs[0]["i"]]) if ANNOUNCE_RX.search(sc.get("text", ""))), qs[0]["i"])
    hs = scenes[host]
    at = float(hs["start"]) + 0.2 if host != qs[0]["i"] else max(float(hs["start"]), qs[0]["at"] - 0.2); dur = min(LIST_S, float(hs["end"]) - at - 0.3)
    if dur >= LIST_MIN_S and not hs.get("chain"):      # a short question scene still lists them, for less time
        hs["qlist"] = {"items": items, "at": at, "dur": dur}; hs["decisions"].append(f"questions: the {len(items)} questions listed"); n += 1
    for k, x in enumerate(qs):
        stop = qs[k + 1]["i"] if k + 1 < len(qs) else len(scenes)
        for sc in scenes[x["i"]:stop]:
            sc["qtrack"] = {"n": k + 1, "of": len(qs), "text": x["text"], "at": x["at"] if sc is scenes[x["i"]] else float(sc["start"]), "new": sc is scenes[x["i"]]}; n += 1
    return n

def _p(t: float, at: float, dur: float = 0.3) -> float: return min(1.0, max(0.0, (t - at) / dur))

def _avatar(d, ctx, cx, cy, r, col, a):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=tuple(col) + (int(255 * a),))
    hr = r * 0.36; d.ellipse((cx - hr, cy - r * 0.55, cx + hr, cy - r * 0.55 + 2 * hr), fill=(245, 245, 245, int(235 * a)))      # head and shoulders
    d.pieslice((cx - r * 0.62, cy + r * 0.12, cx + r * 0.62, cy + r * 1.3), 180, 360, fill=(245, 245, 245, int(235 * a)))

def draw_list(cv: Image.Image, ctx: D.Ctx, c: dict, t: float) -> None:
    u = t - c["at"]
    if u < 0 or u > c["dur"]: return
    a = min(1.0, u / 0.25, (c["dur"] - u) / 0.3); back = Image.new("RGBA", cv.size, (8, 8, 10, int(235 * a))); cv.paste(back, (0, 0), back); d = ImageDraw.Draw(cv, "RGBA")
    W, H = ctx.W, ctx.H; items = c["items"][:6]; n = len(items); rh = min(H * 0.13, H * 0.66 / n); y0 = H * 0.5 - rh * n / 2 + ctx.px(40)
    title = f"{len(c['items'])} QUESTIONS"; f = ctx.font(T.HEAD_FONT, 80); tw = D._text_w(d, title, f, ctx.px(2)); D.text_spaced(d, (W / 2 - tw / 2, y0 - ctx.px(140)), title, f, T.WHITE + (int(255 * a),), ctx.px(2))
    for i, it in enumerate(items):
        q = T.ease_out(_p(u, 0.25 + 0.22 * i)) * a
        if q <= 0: continue
        y = y0 + i * rh + (1 - q) * ctx.px(24); x0, x1 = W * 0.16, W * 0.84; r = rh * 0.32
        d.rounded_rectangle((x0, y, x1, y + rh * 0.82), radius=ctx.px(18), fill=(30, 30, 34, int(240 * q)))
        _avatar(d, ctx, x0 + ctx.px(26) + r, y + rh * 0.41, r, AVATAR[i % len(AVATAR)], q)
        fs = 34 if len(it["text"]) < 40 else 28; D.text_spaced(d, (x0 + ctx.px(52) + 2 * r, y + rh * 0.41 - fs * ctx.S * 0.62), it["text"], ctx.font(T.BODY_FONT, fs), T.WHITE + (int(255 * q),), 0)
        tag = f"Q{i + 1}"; ft = ctx.font(T.HEAD_FONT, 30); D.text_spaced(d, (x1 - ctx.px(30) - D._text_w(d, tag, ft, 0), y + rh * 0.41 - ctx.px(20)), tag, ft, T.ORANGE + (int(255 * q),), 0)

def draw_track(cv: Image.Image, ctx: D.Ctx, c: dict, t: float) -> None:
    """Top right: "Q2 / 5" and one dot per question (done green with a tick, current orange, later grey); a new question pops in with its text under it for a moment."""
    a = _p(t, c["at"] - 0.1)
    if a <= 0: return      # text drawn at alpha 0 still showed (first render: "Q1 / 2" 2 s before the question)
    d = ImageDraw.Draw(cv, "RGBA"); W = ctx.W; r = ctx.px(13); gap = ctx.px(12); n = c["of"]
    x1, y = W - ctx.px(60), ctx.px(64); x0 = x1 - n * (2 * r) - (n - 1) * gap
    lab = f"Q{c['n']} / {n}"; f = ctx.font(T.HEAD_FONT, 34); lw = D._text_w(d, lab, f, ctx.px(1))
    d.rounded_rectangle((x0 - lw - ctx.px(46), y - ctx.px(30), x1 + ctx.px(20), y + ctx.px(30)), radius=ctx.px(30), fill=(14, 14, 16, int(210 * a)))
    D.text_spaced(d, (x0 - lw - ctx.px(24), y - ctx.px(22)), lab, f, T.WHITE + (int(255 * a),), ctx.px(1))
    for i in range(n):
        cx = x0 + r + i * (2 * r + gap); k = i + 1
        col = (74, 222, 128) if k < c["n"] else T.ORANGE if k == c["n"] else (90, 90, 96); rr = r * (1 + 0.35 * (1 - _p(t, c["at"], 0.4))) if k == c["n"] and c.get("new") else r
        d.ellipse((cx - rr, y - rr, cx + rr, y + rr), fill=tuple(col) + (int(255 * a),))
        if k < c["n"]: d.line((cx - r * 0.45, y, cx - r * 0.1, y + r * 0.4, cx + r * 0.5, y - r * 0.4), fill=(20, 20, 22, int(255 * a)), width=max(2, ctx.px(3)))
    if c.get("new"):
        u = t - c["at"]; q = min(_p(u, 0.15), max(0.0, min(1.0, (2.8 - u) / 0.4)))
        if q > 0:
            ft = ctx.font(T.BODY_FONT, 28); tw = D._text_w(d, c["text"], ft, 0); xr = x1 + ctx.px(20)
            d.rounded_rectangle((xr - tw - ctx.px(40), y + ctx.px(44), xr, y + ctx.px(100)), radius=ctx.px(14), fill=(30, 30, 34, int(230 * q))); D.text_spaced(d, (xr - tw - ctx.px(20), y + ctx.px(54)), c["text"], ft, T.WHITE + (int(255 * q),), 0)
