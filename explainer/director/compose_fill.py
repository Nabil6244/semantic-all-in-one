"""Fill pass (opt-in, DirectorOptions.fill): after a board beat is authored (and repaired), a moment of the beat that would be near-empty gets a STAGED build from the narration's own words.

A "moment" is one sentence of the beat: from its first word to the next sentence's first word (where the board clears) or the beat end. A moment is near-empty when
  * the share of the content area covered together at its busiest instant (the same measure as `peak_occupancy_share`) is below FILL_BELOW, or
  * it shows a lone fragment: at most two words of text/labels in total although the sentence has at least four words ("villagers", "small").
What the pass does, in this order, for one beat:
  1. DUPLICATES: a number (a year, a quantity) shown twice at the same time on one board. The bare-number element (chip, tag, plate) is removed when another element on the board shows the number; two
     typed lines are never touched. The words stay on screen in the other element, so nothing the narration says is lost.
  2. LONE FRAGMENT: a short typed line is extended to a longer contiguous quote of its sentence that contains it (never replaced by something else).
  3. FILL: a near-empty moment gets new elements, one at a time, each anchored on a spoken word of the moment and placed so the gap between two changes is cut at about FILL_SPACING_S (1.8 s): a picture
     tile or ring for a keyword that has no picture in the beat yet, a number tag, a box + arrow pair across a cause/twist word, an icon row (several pictures, each on its own word), or a typed line with
     the best unused contiguous quote of at least three words. Every text is a contiguous quote of the narration. Pictures already shown in the beat are not repeated.
Nothing existing is dropped (a removed duplicate is listed in the record and its text is still shown by the other element), nothing is random, and every addition is tested with dry_build: a candidate that
makes the beat report any problem is discarded. On any exception the original beat is restored and the record says so."""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..board import styles as ST
from ..board.builder import clip_geometry
from ..board.cues import Cue
from ..board.dry import dry_build
from . import lexicon as LX
from .compose import _disp, role_for, best_phrases
from .compose_ref import GENERIC, ICON_ROLE, RING_ROLE, _line_fit
from .segment import norm

FILL_BELOW = 0.65               # a moment whose busiest instant covers less than this share of the content area is near-empty
FILL_SPACING_S = 1.5            # target time between two new elements
MIN_AFTER_S = 0.6               # a new element is never earlier than this after the previous change
MIN_BEFORE_END_S = 0.45         # ... nor later than this before the moment ends (it must be seen)
MAX_ADD_MOMENT = 4
MAX_ADD_BEAT = 10
MAX_BUILDS = 70                 # dry builds per beat (cost cap)
CONTENT = 1104 * 780.0
X0, X1, Y0, Y1 = 720, 1824, 110, 880
GAP = 28                        # free space kept between a new element and the others of its moment
MAX_FRAGMENT_WORDS = 2
LONG_WORDS = 6                  # longest quote an extended fragment becomes
NUM = re.compile(r"\d[\d,.]*")
TEXT_KINDS = ("title", "caption", "card", "header")
UNITS = ("million", "billion", "thousand", "percent", "hundred", "trillion")
KIND_PENALTY = {"tile": 0.0, "tag": 0.3, "flow": 0.5, "line": 0.6}


# ------------------------------------------------------------------ measures
def _numbers(text: str) -> set:
    out = set()
    for m in NUM.findall(text or ""):
        d = re.sub(r"[^\d]", "", m)
        if d:
            out.add(d)
    return out


def _rect(it) -> Tuple[int, int, int, int]:
    return it.rect if it.rect != (0, 0, 0, 0) else it.bbox


def _area(it) -> float:
    r = _rect(it)
    return 760 * 170 if it.kind == "title" else max(0, r[2] - r[0]) * max(0, r[3] - r[1])


def _drawn(it) -> bool:
    return it.kind not in ("narrator", "arrow") and it.style != "set"


def occupancy(items, t0: float, t1: float) -> float:
    """The largest share of the content area covered together at one instant of [t0, t1) (clip seconds): same measure as the plan's peak_occupancy_share, restricted to a moment."""
    pts = {t0} | {it.onset for it in items if _drawn(it) and t0 - 1e-9 <= it.onset < t1 - 1e-9}
    peak = 0.0
    for t in pts:
        tot = sum(_area(it) for it in items if _drawn(it) and it.onset <= t + 1e-9 and not (it.hide_at is not None and it.hide_at <= t + 1e-9))
        peak = max(peak, tot)
    return round(min(1.0, peak / CONTENT), 3)


def beat_occupancy(items) -> float:
    pts = sorted({0.0, *[it.onset for it in items if _drawn(it)]})
    return occupancy(items, 0.0, (max(pts) if pts else 0.0) + 1.0)


def _shown_words(items, t0: float, t1: float) -> int:
    n = 0
    for it in items:
        if it.kind == "narrator" or it.kind == "arrow" or not (t0 - 1e-9 <= it.onset < t1 - 1e-9):
            continue
        txt = (it.text or "").strip()
        if txt and txt != "?" and it.style not in ("stamp", "plate", "cross", "tag") and it.kind != "chip":
            n += len(txt.split())
    return n


# ------------------------------------------------------------------ context
class _Ctx:
    def __init__(self, br, beat_id, start, end, sents, words, cased, opt, table, roles):
        self.br, self.beat_id, self.start, self.end, self.sents = br, beat_id, start, end, sents
        self.words, self.cased, self.opt, self.table, self.roles = words, cased, opt, table, roles
        self.bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
        self.pos = {g: k for k, g in enumerate(self.bw)}
        self.origin = clip_geometry(start, end, opt.dissolve_s)[0]
        self.builds = 0
        self.n = 0
        self._state = None

    def build(self, cues=None):
        self.builds += 1
        return dry_build(self.br.cues if cues is None else cues, self.words, self.start, self.end, dissolve_s=self.opt.dissolve_s, fps=self.opt.fps, beat_id=self.beat_id)

    def state(self):
        if self._state is None:
            self._state = self.build()
        return self._state

    def touch(self):
        self._state = None

    def new_id(self) -> str:
        self.n += 1
        return f"{self.beat_id}_fill{self.n}"

    def at(self, g: int) -> Dict[str, int]:
        return {"index": self.pos[g]}


def _moments(c: _Ctx):
    out = []
    for i, s in enumerate(c.sents):
        sidx = [g for g in s.widx if g in c.pos]
        if not sidx:
            continue
        nxt = next(([g for g in c.sents[j].widx if g in c.pos] for j in range(i + 1, len(c.sents)) if any(g in c.pos for g in c.sents[j].widx)), None)
        t1 = float(c.words[nxt[0]][1]) if nxt else float(c.end)
        out.append((s, sidx, float(c.words[sidx[0]][1]), t1))
    return out


def _covered(c: _Ctx) -> set:
    got = set(c.br.used_extra)
    for ph in c.br.phrases:
        got.update(range(ph["first"], ph["last"] + 1))
    return got


def _quote_ok(c: _Ctx, text: str, g0: int, g1: int) -> bool:
    """The text is the narration's own words words[g0..g1], compared without case and punctuation."""
    a = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in text.split()]
    b = [re.sub(r"[^a-z0-9]", "", str(c.words[g][0]).lower()) for g in range(g0, g1 + 1)]
    a, b = [x for x in a if x], [x for x in b if x]
    return a == b


# ------------------------------------------------------------------ 1. duplicates
def _dedupe(c: _Ctx, rec: Dict[str, Any]) -> None:
    for _ in range(4):
        probs, resolved, items = c.state()
        refs = {x.src for x in c.br.cues if x.src} | {x.dst for x in c.br.cues if x.dst} | {i for x in c.br.cues for i in (x.params or {}).get("over", [])}
        shown = [it for it in items if it.kind in ("visual", "chip", "title", "card", "header", "caption") and it.style not in ("stamp", "cross") and _numbers(it.text)]
        victim = None
        for i, a in enumerate(shown):
            for b in shown[i + 1:]:
                if not (_numbers(a.text) & _numbers(b.text)):
                    continue
                if not (a.onset < (b.hide_at if b.hide_at is not None else 1e9) and b.onset < (a.hide_at if a.hide_at is not None else 1e9)):
                    continue                                    # not on the board together
                bare = [x for x in (a, b) if (x.kind == "chip" or x.style in ("tag", "plate")) and x.cue_id not in refs]
                if not bare:
                    rec["notes"].append(f"number {sorted(_numbers(a.text) & _numbers(b.text))[0]} is in two texts ({a.cue_id}, {b.cue_id}); both are typed text, kept")
                    continue
                victim = min(bare, key=lambda x: (len(x.text), -x.onset))          # the shorter text goes; a tie loses the later one
                keep = b if victim is a else a
                break
            if victim:
                break
        if victim is None:
            return
        keep_cues = [x for x in c.br.cues if x.id != victim.cue_id]
        probs2, _r, _i = c.build(keep_cues)
        if probs2:
            rec["notes"].append(f"duplicate {victim.cue_id} kept: removing it makes the beat report {probs2[0][:60]}")
            return
        c.br.cues[:] = keep_cues
        c.br.phrases[:] = [p for p in c.br.phrases if p.get("phrase") != victim.text or p.get("as") not in ("tag", "chip", "plate")]
        c.touch()
        rec["removed"].append({"cue": victim.cue_id, "text": victim.text, "why": f"its number is also shown by {keep.cue_id} ({keep.text!r}) on the same board"})


# ------------------------------------------------------------------ 2. lone fragment
def _extend_fragment(c: _Ctx, s, sidx: List[int], rec: Dict[str, Any], w0: float, w1: float) -> bool:
    items = c.state()[2]
    for cue in list(c.br.cues):
        prm = cue.params or {}
        if cue.kind != "visual" or prm.get("style") != "line" or len((cue.text or "").split()) > MAX_FRAGMENT_WORDS:
            continue
        a = (cue.anchor or {}).get("index")
        if a is None or a >= len(c.bw):
            continue
        g0 = c.bw[a]
        if g0 not in sidx:
            continue
        g1 = g0 + len(cue.text.split()) - 1
        if g1 not in sidx or not _quote_ok(c, cue.text, g0, g1):
            continue
        fit = _line_fit(int(prm.get("width", 900)), int(prm.get("px", 56)), int(prm.get("lines", 1)))
        got = best_phrases(sidx, c.words, c.cased, c.table, set().union(*[x.breaks for x in c.sents]), k=4, max_words=LONG_WORDS, fit=fit, min_score=3.0, min_words=3)
        for ph in got:
            if not (ph.first <= g0 and g1 <= ph.last) or not _quote_ok(c, ph.text, ph.first, ph.last):
                continue
            new = dataclasses.replace(cue, text=ph.text, anchor=c.at(ph.first))
            trial = [new if x is cue else x for x in c.br.cues]
            probs, _r, _i = c.build(trial)
            if probs:
                continue
            c.br.cues[:] = trial
            for p in c.br.phrases:
                if p.get("as") == "line" and p.get("first") == g0 and p.get("phrase") == cue.text:
                    p.update(phrase=ph.text, first=ph.first, last=ph.last)
            c.br.used_extra.update(range(ph.first, ph.last + 1))
            c.touch()
            rec["extended"].append({"cue": cue.id, "was": cue.text, "now": ph.text})
            return True
    return False


# ------------------------------------------------------------------ 3. fill
def _free_spots(w: int, h: int, others: Sequence[Tuple[int, int, int, int]]) -> List[Tuple[int, int]]:
    """Candidate top-left corners, best first: the largest distance to every other rectangle visible with the new element (none may overlap within GAP)."""
    cands = []
    for y in range(Y0, Y1 - h + 1, 70):
        for x in range(X0, X1 - w + 1, 70):
            d = 10 ** 6
            ok = True
            for r in others:
                dx = max(r[0] - (x + w), x - r[2], 0)
                dy = max(r[1] - (y + h), y - r[3], 0)
                dd = max(dx, dy) if (dx or dy) else -1
                if dd < GAP:
                    ok = False
                    break
                d = min(d, dd)
            if ok:
                cands.append((-(min(d, 420)) + 0.08 * abs((y + h / 2) - 500) + 0.02 * abs((x + w / 2) - 1272), y, x))
    cands.sort()
    return [(x, y) for _s, y, x in cands]


def _others(c: _Ctx, w1_clip: float, t_clip: float) -> List[Tuple[int, int, int, int]]:
    out = []
    for it in c.state()[2]:
        if it.kind == "narrator" or it.style == "set":
            continue
        if it.onset < w1_clip - 1e-9 and not (it.hide_at is not None and it.hide_at <= t_clip + 1e-9):
            out.append(_rect(it))
    return out


def _try_place(c: _Ctx, protos: List[Cue], sizes: List[Tuple[int, int]], w1: float, t_abs: float, tries: int = 6) -> Optional[List[Cue]]:
    """protos[0] is placed (free-space order, each tested with dry_build); the optional protos[1:] are boxes of a flow: placed one after the other, then the arrow."""
    others = _others(c, w1 - c.origin, t_abs - c.origin)
    base = list(c.br.cues)
    chosen: List[Cue] = []
    extra: List[Tuple[int, int, int, int]] = []
    for k, proto in enumerate(protos):
        w, h = sizes[k]
        placed = None
        for (x, y) in _free_spots(w, h, others + extra)[:tries]:
            if c.builds >= MAX_BUILDS:
                return None
            cue = dataclasses.replace(proto, pos=(x + w // 2, y + h // 2) if proto.kind == "title" else (x, y))
            probs, _r, _i = c.build(base + chosen + [cue])
            if not probs:
                placed = cue
                break
        if placed is None:
            return None
        chosen.append(placed)
        px0, py0 = (placed.pos[0] - w // 2, placed.pos[1] - h // 2) if placed.kind == "title" else placed.pos
        extra.append((px0, py0, px0 + w, py0 + h))
    return chosen


def _moment_numbers(items, t0: float, t1: float) -> set:
    out = set()
    for it in items:
        if it.kind != "narrator" and it.onset < t1 - 1e-9 and not (it.hide_at is not None and it.hide_at <= t0 + 1e-9):
            out |= _numbers(it.text)
    return out


def _candidates(c: _Ctx, s, sidx: List[int], w0: float, w1: float, lo: float, hi: float, items, covered: set) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    win = [g for g in sidx if lo <= float(c.words[g][1]) <= hi]
    if not win:
        return out
    stoks = [norm(c.words[g][0]) for g in sidx]
    role_s, _kw = role_for(stoks, c.roles)
    ring = RING_ROLE.get(role_s, "gold")
    used_assets = {x.asset for x in c.br.cues if x.kind == "visual" and x.asset}
    pics = sum(1 for x in c.br.cues if x.kind == "visual" and (x.params or {}).get("style") in ("tile", "circle"))
    nums_here = _moment_numbers(items, w0 - c.origin, w1 - c.origin)
    # pictures
    seen = set()
    for g in win:
        t = norm(c.words[g][0])
        a = c.table.get(t)
        if not a or a in used_assets or a in seen or t in LX.STOP or t in LX.WEAK or t in GENERIC:
            continue
        seen.add(a)
        style = "circle" if pics % 2 else "tile"
        lab = _disp(t, c.cased)
        role = ring if style == "tile" else ICON_ROLE.get(a, "blue")
        m = ST.measure(style, lab, {"style": style}, a)
        if m is None:
            continue
        out.append({"kind": "tile", "t": float(c.words[g][1]) + 0.1, "pen": KIND_PENALTY["tile"] + (0.7 if g in covered else 0.0),
                    "protos": [Cue(c.new_id(), "visual", c.at(g), text=lab, role=role, asset=a, params={"style": style})], "sizes": [(m["w"], m["h"])],
                    "info": {"kind": style, "text": lab, "asset": a, "g": g}})
    # a number tag
    for g in win:
        if not any(ch.isdigit() for ch in str(c.words[g][0])):
            continue
        rest = [x for x in sidx if x > g]
        take = [g] + (rest[:1] if rest and norm(c.words[rest[0]][0]) in UNITS else [])
        nxt = [x for x in sidx if x > take[-1]][:1]
        if nxt and norm(c.words[nxt[0]][0]) not in LX.STOP and norm(c.words[nxt[0]][0]) not in LX.WEAK:
            take.append(nxt[0])
        ttext = " ".join(re.sub(r"[^\w,.%$]", "", str(c.words[x][0])) for x in take)
        if _numbers(ttext) & nums_here or not _quote_ok(c, ttext, take[0], take[-1]):
            continue
        m = ST.measure("tag", ttext, {"style": "tag"})
        if m is None:
            continue
        out.append({"kind": "tag", "t": float(c.words[g][1]) + 0.1, "pen": KIND_PENALTY["tag"], "protos": [Cue(c.new_id(), "visual", c.at(g), text=ttext, role="blue", params={"style": "tag"})],
                    "sizes": [(m["w"], m["h"])], "info": {"kind": "tag", "text": ttext, "g": g}})
        break
    # a box -> box flow across a cause / twist word
    pool = [g for g in sidx if g not in covered and not any(ch.isdigit() for ch in str(c.words[g][0]))]
    brk = set().union(*[x.breaks for x in c.sents])
    two = best_phrases(pool, c.words, c.cased, c.table, brk, k=2, max_words=4, fit=_line_fit(560, 52), min_score=5.0, min_words=2)
    if len(two) == 2 and two[0].last < two[1].first and lo <= float(c.words[two[0].first][1]) and float(c.words[two[1].first][1]) <= hi + 1.2:
        between = [norm(c.words[g][0]) for g in sidx if two[0].last < g < two[1].first]
        link = next((t for t in between if t in LX.CAUSE or t in LX.TWIST), None)
        ma, mb = ST.measure("lite", two[0].text, {}), ST.measure("box", two[1].text, {})
        if link and ma and mb and _quote_ok(c, two[0].text, two[0].first, two[0].last) and _quote_ok(c, two[1].text, two[1].first, two[1].last):
            ia, ib = c.new_id(), c.new_id()
            out.append({"kind": "flow", "t": float(c.words[two[0].first][1]), "pen": KIND_PENALTY["flow"],
                        "protos": [Cue(ia, "visual", c.at(two[0].first), text=two[0].text, role="blue", params={"style": "lite"}),
                                   Cue(ib, "visual", c.at(two[1].first), text=two[1].text, role="red" if link in LX.TWIST else "blue", params={"style": "box"})],
                        "sizes": [(ma["w"], ma["h"]), (mb["w"], mb["h"])], "arrow": c.new_id(), "info": {"kind": "flow", "text": f"{two[0].text} -> {two[1].text}", "g": two[0].first}})
    # a typed line: the best contiguous quote of at least three words that starts inside the window; unused words first, then (relaxed) unused words with up to two covered neighbours
    unc = set(pool)
    near = sorted({g + d for g in unc for d in (-2, -1, 0, 1, 2)} & {g for g in sidx if not any(ch.isdigit() for ch in str(c.words[g][0]))})
    found = None
    for (src, ms) in ((pool, 4.0), (pool, 3.0), (near, 2.0), (near, 1.0)):
        inner = [g for g in src if float(c.words[g][1]) >= lo - 0.1]
        for (lw, ln, px) in ((560, 2, 64), (900, 1, 56), (1080, 1, 48)):
            got = best_phrases(inner, c.words, c.cased, c.table, brk, k=3, max_words=6, fit=_line_fit(lw, px, ln), min_score=ms, min_words=3 if ms >= 3.0 else 2)
            for ph in got:
                if not (lo <= float(c.words[ph.first][1]) <= hi) or not _quote_ok(c, ph.text, ph.first, ph.last) or _numbers(ph.text) & nums_here:
                    continue
                if sum(1 for g in range(ph.first, ph.last + 1) if g in unc) < 2:
                    continue                                    # at least two words nobody shows yet
                prm = {"style": "line", "width": lw, "px": px, "lines": ln, "tint": False, "sync": True}
                m = ST.measure("line", ph.text, prm)
                if m is None:
                    continue
                found = {"kind": "line", "t": float(c.words[ph.first][1]), "pen": KIND_PENALTY["line"], "protos": [Cue(c.new_id(), "visual", c.at(ph.first), text=ph.text, role="ink", cps=34.0, offset_s=0.0, params=prm)],
                         "sizes": [(lw, m["h"])], "info": {"kind": "line", "text": ph.text, "g": ph.first, "last": ph.last}}
                break
            if found:
                break
        if found:
            break
    if found:
        out.append(found)
    # last resort: the sentence's key phrase (at most three words) as a display title, once per moment when the moment has no title yet
    has_title = any(x.kind == "title" for x in c.br.cues if x.anchor.get("index", -1) in [c.pos[g] for g in sidx])
    if not has_title and not any(x.kind == "title" for x in c.br.cues):
        particles = {"apart", "away", "up", "down", "out", "off", "back", "over", "again", "together"}
        tt = best_phrases([g for g in sidx if float(c.words[g][1]) >= lo - 0.1], c.words, c.cased, c.table, brk, k=1, max_words=3,
                          fit=lambda t: len(t) <= 22 and norm(t.split()[-1]) not in particles, min_score=5.0, min_words=2, strict_edges=True, require_clause_end=True)
        if tt and lo <= float(c.words[tt[0].first][1]) <= hi and not (_numbers(tt[0].text) & nums_here) and _quote_ok(c, tt[0].text, tt[0].first, tt[0].last):
            out.append({"kind": "title", "t": float(c.words[tt[0].first][1]) + 0.1, "pen": 1.2, "centre": True, "protos": [Cue(c.new_id(), "title", c.at(tt[0].first), text=tt[0].text.upper())],
                        "sizes": [(760, 180)], "info": {"kind": "title", "text": tt[0].text.upper(), "g": tt[0].first, "last": tt[0].last}})
    return out


def _commit(c: _Ctx, cand: Dict[str, Any], chosen: List[Cue], rec: Dict[str, Any], sid: int, label: str) -> None:
    info = cand["info"]
    if cand["kind"] == "flow":
        arrow = Cue(cand["arrow"], "arrow", dict(chosen[1].anchor), offset_s=0.5, role="blue", src=chosen[0].id, dst=chosen[1].id, params={"width": 16})
        probs, _r, _i = c.build(list(c.br.cues) + chosen + [arrow])
        if probs:
            raise _Reject(probs[0])
        chosen = chosen + [arrow]
    c.br.cues.extend(chosen)
    for cu in chosen:
        if cu.kind == "title":
            g = c.bw[cu.anchor["index"]]
            c.br.phrases.append({"sentence": sid, "label": "fill", "phrase": cu.text, "asset": None, "keyword": "", "role": "yellow", "role_keyword": "", "first": g, "last": g + len(cu.text.split()) - 1, "as": "title"})
            continue
        if cu.kind != "visual":
            continue
        st = (cu.params or {}).get("style")
        g = c.bw[cu.anchor["index"]]
        last = g + (len(cu.text.split()) - 1 if st in ("line", "lite", "box") else 0)
        c.br.phrases.append({"sentence": sid, "label": "fill", "phrase": cu.text, "asset": cu.asset or None, "keyword": norm(c.words[g][0]) if st in ("tile", "circle") else "", "role": cu.role,
                             "role_keyword": "", "first": g, "last": last, "as": st})
        if st in ("line", "lite", "box", "tag"):
            c.br.used_extra.update(range(g, last + 1))
        if st in ("tile", "circle"):
            c.br.metaphor_uses.append({"keyword": norm(c.words[g][0]), "asset": cu.asset, "role": ICON_ROLE.get(cu.asset, "blue"), "beat": c.beat_id})
    c.touch()
    t_first = min(float(c.words[c.bw[cu.anchor["index"]]][1]) for cu in chosen)
    rec["added"].append({"cues": [cu.id for cu in chosen], "kind": cand["kind"], "text": info["text"], "t": round(t_first, 3), "sentence": sid})


class _Reject(Exception):
    pass


def _events(c: _Ctx, w0: float, w1: float) -> List[float]:
    resolved = c.state()[1]
    ev = [w0, w1]
    for r in resolved:
        if r.cue.kind in ("narrator", "clear") or r.problems or r.onset_abs is None:
            continue
        if w0 - 1e-6 <= r.onset_abs < w1 - 1e-6:
            ev.append(float(r.onset_abs))
    return sorted(set(round(t, 4) for t in ev))


ENLARGE = ((1000, 76, 2), (900, 68, 2), (760, 64, 2))          # (width, px, lines): the heavier display size of the reference, tried largest first


def _enlarge(c: _Ctx, sidx: List[int], w0: float, w1: float, rec: Dict[str, Any]) -> None:
    """Still near-empty and nothing more to add: the moment's typed lines are set larger (same text, same word, same colour). Each change is tested with dry_build."""
    in_moment = {c.pos[g] for g in sidx}
    for cue in sorted([x for x in c.br.cues if x.kind == "visual" and (x.params or {}).get("style") == "line" and x.anchor.get("index") in in_moment and len((x.text or "").split()) >= 4],
                      key=lambda x: -len(x.text)):
        prm = cue.params or {}
        cur = ST.measure("line", cue.text, prm)
        if cur is None:
            continue
        for (lw, px, ln) in ENLARGE:
            new_prm = {**prm, "width": lw, "px": px, "lines": ln}
            m = ST.measure("line", cue.text, new_prm)
            if m is None or m["px"] <= cur["px"] or c.builds >= MAX_BUILDS:
                continue
            x, y = cue.pos
            x = min(x, X1 - lw)
            y = min(y, Y1 - m["h"])
            new = dataclasses.replace(cue, params=new_prm, pos=(max(X0, x), max(Y0, y)))
            probs, _r, _i = c.build([new if z is cue else z for z in c.br.cues])
            if probs:
                continue
            c.br.cues[:] = [new if z is cue else z for z in c.br.cues]
            c.touch()
            rec["enlarged"].append({"cue": cue.id, "text": cue.text, "px": [cur["px"], m["px"]], "width": [int(prm.get("width", 900)), lw]})
            break
        if occupancy(c.state()[2], w0 - c.origin, w1 - c.origin) >= FILL_BELOW:
            return


def _fill_moment(c: _Ctx, mi: int, s, sidx: List[int], w0: float, w1: float, rec: Dict[str, Any], budget: List[int]) -> None:
    mrec = {"sentence": s.index, "start": round(w0, 2), "end": round(w1, 2)}
    items = c.state()[2]
    mrec["peak_before"] = occupancy(items, w0 - c.origin, w1 - c.origin)
    lone = len(sidx) >= 4 and _shown_words(items, w0 - c.origin, w1 - c.origin) <= MAX_FRAGMENT_WORDS
    mrec["lone_fragment"] = bool(lone)
    if mrec["peak_before"] >= FILL_BELOW and not lone:
        mrec["action"] = "none: enough on screen"
        rec["moments"].append(mrec)
        return
    if lone and _extend_fragment(c, s, sidx, rec, w0, w1):
        items = c.state()[2]
        lone = len(sidx) >= 4 and _shown_words(items, w0 - c.origin, w1 - c.origin) <= MAX_FRAGMENT_WORDS
    n_here, failed = 0, set()
    while n_here < MAX_ADD_MOMENT and budget[0] < MAX_ADD_BEAT and c.builds < MAX_BUILDS:
        items = c.state()[2]
        peak = occupancy(items, w0 - c.origin, w1 - c.origin)
        if peak >= FILL_BELOW and not (lone and n_here == 0):
            break
        ev = _events(c, w0, w1)
        gaps = sorted(((b - a, a, b) for a, b in zip(ev, ev[1:])), reverse=True)
        placed = False
        for g_len, a, b in gaps:
            lo, hi = a + MIN_AFTER_S, b - MIN_BEFORE_END_S
            if hi - lo < 0.0:
                continue
            cands = [x for x in _candidates(c, s, sidx, w0, w1, lo, hi, items, _covered(c)) if x["info"]["g"] not in failed and lo - 0.2 <= x["t"] <= hi]
            cands.sort(key=lambda x: (abs(x["t"] - (a + FILL_SPACING_S)) + x["pen"], x["t"]))
            for cand in cands[:4]:
                chosen = _try_place(c, cand["protos"], cand["sizes"], w1, cand["t"])
                if chosen is None:
                    failed.add(cand["info"]["g"])
                    continue
                try:
                    _commit(c, cand, chosen, rec, s.index, s.label)
                except _Reject as e:
                    failed.add(cand["info"]["g"])
                    rec["notes"].append(f"{cand['kind']} {cand['info']['text']!r} rejected: {e}")
                    continue
                n_here += 1
                budget[0] += 1
                placed = True
                break
            if placed:
                break
        if not placed:
            mrec["stopped"] = "no further candidate fits the board" if gaps else "no gap"
            break
        lone = len(sidx) >= 4 and _shown_words(c.state()[2], w0 - c.origin, w1 - c.origin) <= MAX_FRAGMENT_WORDS
    if c.builds < MAX_BUILDS and occupancy(c.state()[2], w0 - c.origin, w1 - c.origin) < FILL_BELOW:
        _enlarge(c, sidx, w0, w1, rec)
    items = c.state()[2]
    mrec["peak_after"] = occupancy(items, w0 - c.origin, w1 - c.origin)
    mrec["added"] = n_here
    rec["moments"].append(mrec)


def fill_pass(br, beat_id: str, start: float, end: float, sents: Sequence[Any], words, cased: Dict[str, str], opt, table: Dict[str, str], roles: Dict[str, str]) -> Dict[str, Any]:
    """Runs the fill on one authored board beat in place and returns a record for the plan report. Never raises: on any exception the beat is restored."""
    rec: Dict[str, Any] = {"added": [], "removed": [], "extended": [], "enlarged": [], "moments": [], "notes": [], "changed": False}
    snap = (list(br.cues), [dict(p) for p in br.phrases], set(br.used_extra), list(br.metaphor_uses), list(br.repairs))
    try:
        c = _Ctx(br, beat_id, start, end, sents, words, cased, opt, table, roles)
        probs, _r, items = c.state()
        if probs:
            rec["notes"].append(f"skipped: the beat already reports {probs[0][:80]}")
            return rec
        rec["peak_before"] = beat_occupancy(items)
        n_cues = len(br.cues)
        _dedupe(c, rec)
        budget = [0]
        for mi, (s, sidx, w0, w1) in enumerate(_moments(c)):
            _fill_moment(c, mi, s, sidx, w0, w1, rec, budget)
        probs, _r, items = c.build()
        if probs:
            raise RuntimeError(f"the filled beat reports {probs[0][:100]}")
        rec["changed"] = bool(rec["added"] or rec["removed"] or rec["extended"] or rec["enlarged"])
        rec["peak_after"] = beat_occupancy(items)
        rec["dry_builds"] = c.builds
        if rec["changed"]:
            br.repairs.append(f"{beat_id}: fill added {len(rec['added'])} element(s), removed {len(rec['removed'])} duplicate(s), extended {len(rec['extended'])} fragment(s), enlarged {len(rec['enlarged'])} line(s)")
        return rec
    except Exception as exc:                                              # never-stop: keep the original beat
        br.cues[:] = snap[0]
        br.phrases[:] = snap[1]
        br.used_extra.clear()
        br.used_extra.update(snap[2])
        br.metaphor_uses[:] = snap[3]
        br.repairs[:] = snap[4]
        return {"added": [], "removed": [], "extended": [], "enlarged": [], "moments": [], "changed": False, "notes": [f"fill failed, the original beat is kept: {exc!r}"]}
