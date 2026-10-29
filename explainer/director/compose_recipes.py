"""Composition recipes (opt-in: DirectorOptions.recipes). A recipe is a reusable capability chosen by what a beat MEANS, not a fixed template: a cause chain, a before/after pair, a
two-sided comparison, a pictogram of a count, a pyramid of ranks, a dated timeline, an animated bar chart, an archival picture card. Each is built only from evidence in the beat's own
words (a recipe whose evidence is missing returns None and the beat keeps the ordinary reference composition); every element appears on its own spoken word (anchor {"index": k}); every
text is a contiguous quote of the narration; nothing is fetched and nothing is generated. The result goes through the same layout gate as any board: a recipe whose required elements
the gate would drop returns None instead of a half-drawn diagram."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..board import elements as E
from ..board.icons import ICONS
from ..board import styles as ST
from ..board.cues import Cue
from . import lexicon as LX
from .compose import BoardResult, Phrase, _disp, gate, role_for
from .compose_ref import best_phrases
from .options import DirectorOptions
from .segment import Sent, norm

RECIPES = ("cause_effect", "before_after", "two_column", "pictogram", "pyramid", "timeline", "bar_chart", "archival", "scarcity")      # also the tie-break order
CX = 1265                                    # the middle of the content area right of the narrator (x 720..1810)
X0, X1 = 720, 1810
GENERIC = frozenset("year years time day days age century decade way thing things".split())

CAUSE_FWD = ((("led", "to"), 2), (("leads", "to"), 2), (("leading", "to"), 2), (("which", "meant"), 2), (("which", "means"), 2), (("as", "a", "result"), 3), (("that", "is", "why"), 3),
             (("thats", "why"), 2), (("resulted", "in"), 2), (("meant", "that"), 2), (("therefore",), 1), (("consequently",), 1), (("thus",), 1), (("hence",), 1), (("caused",), 1),
             (("triggered",), 1), (("sparked",), 1), (("so",), 1),
             (("developed", "into"), 2), (("turned", "into"), 2), (("grew", "into"), 2), (("created",), 1), (("forced",), 1), (("made", "it"), 2), (("made", "them"), 2), (("prevented",), 1))
CAUSE_REV = ((("because", "of"), 2), (("due", "to"), 2), (("thanks", "to"), 2), (("because",), 1))
LACK = frozenset("little few scarce scarcity limited lack lacked lacking shortage shortages scant meagre meager".split())          # "very little farmland, limited natural resources": a lack, then what it limits
PAST = frozenset("before then once formerly previously earlier".split())
PRESENT = frozenset("now today nowadays currently after afterwards".split())
COMPARE_MARK = frozenset("versus vs while whereas than unlike".split())
TIER_RANK = {**{w: 1 for w in "emperor emperors king kings queen queens pharaoh sultan pope monarch monarchs tsar shogun".split()},
             **{w: 2 for w in "nobles noble nobility lords aristocrats aristocracy barons clergy bishops priests dukes".split()},
             **{w: 3 for w in "knights warriors samurai officers".split()},
             **{w: 4 for w in "merchants artisans craftsmen traders citizens townspeople".split()},
             **{w: 5 for w in "peasants serfs slaves commoners farmers laborers workers".split()}}
HIER = frozenset("top bottom rank ranks class classes hierarchy ladder above below".split())
SCALE = {"hundred": 1e2, "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12, "percent": 1.0}
NUMW = {w: float(v) for w, v in zip("two three four five six seven eight nine ten eleven twelve twenty thirty forty fifty sixty seventy eighty ninety".split(),
                                    [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 20, 30, 40, 50, 60, 70, 80, 90])}
NUM_RE = re.compile(r"\$?\d[\d,]*(\.\d+)?%?")
TIER_ROLE = ("gold", "red", "blue", "green")
KEEP_END = frozenset("more less fewer".split())          # "bread cost more": a closing comparative is part of the quote
TRAIL = frozenset("among between through across against toward towards during within upon into onto over under around".split())          # a phrase never ends on these
PRONOUN = frozenset("this that it these those they he she which".split())


# --------------------------------------------------------------------------------------------- token-level evidence (also used by pick_recipe)
def _is_year(t: str) -> bool:
    return t.isdigit() and len(t) == 4 and 1000 <= int(t) <= 2100


def find_markers(toks: Sequence[str], table=CAUSE_FWD + CAUSE_REV) -> List[Tuple[int, int, str]]:
    """(first, last, "fwd" | "rev") of each cause marker, longest match first, left to right. A marker needs two or more words on its left side (fwd) or right side (rev)."""
    fwd = {p for p, _ in CAUSE_FWD}
    out: List[Tuple[int, int, str]] = []
    i = 0
    while i < len(toks):
        hit = None
        for pat, n in sorted(table, key=lambda x: -x[1]):
            if tuple(toks[i:i + n]) == pat:
                hit = (i, i + n - 1, "fwd" if pat in fwd else "rev")
                break
        if hit and hit[1] + 2 <= len(toks) - 1 + 1 and (hit[0] >= 1 or hit[2] == "rev"):
            out.append(hit)
            i = hit[1] + 1
        else:
            i += 1
    return out


def _count_numbers(toks: Sequence[str]) -> int:
    n = 0
    for i, t in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if t.isdigit() and not (_is_year(t) and nxt not in SCALE):
            n += 1
        elif t in NUMW and (nxt in SCALE or (nxt and nxt not in LX.STOP and nxt not in LX.WEAK)):
            n += 1
    return n


def pick_recipe(tokens: Sequence[str], idea: str = "", has_image: bool = False) -> List[Tuple[str, int]]:
    """[(recipe, score)] best first (ties in RECIPES order); a recipe with less than its minimum evidence is not listed. Pure and deterministic: tokens in, scores out."""
    toks = [norm(t) for t in tokens if norm(t)]
    low = set(toks)
    sc: Dict[str, int] = {}
    mk = find_markers(toks)
    if mk:
        sc["cause_effect"] = 3 + 2 * min(len(mk), 2) + (2 if idea == "cause" else 0)
    past = [i for i, t in enumerate(toks) if t in PAST or (t == "used" and toks[i + 1:i + 2] == ["to"])]
    pres = [i for i, t in enumerate(toks) if t in PRESENT]
    if past and pres and set(past) != set(pres):
        sc["before_after"] = 4 + (1 if idea == "comparative" else 0)
    cm = [t for t in toks if t in COMPARE_MARK]
    if cm and (idea == "comparative" or len(cm) >= 2 or "while" in cm or "whereas" in cm or "versus" in cm):
        sc["two_column"] = 2 + 2 * min(len(cm), 2) + (2 if idea == "comparative" else 0)
    nn = _count_numbers(toks)
    if nn >= 2:
        sc["bar_chart"] = 4 + nn + (2 if idea == "quantitative" else 0)
    elif nn == 1:
        sc["pictogram"] = 3 + (3 if idea == "quantitative" else 0)
    lk = [i for i, t in enumerate(toks) if t in LACK]
    if "cause_effect" not in sc and len(lk) >= 2 and any(j - i >= 2 for i, j in zip(lk, lk[1:])):
        sc["scarcity"] = 4
    ranks = {TIER_RANK[t] for t in toks if t in TIER_RANK}
    if len(ranks) >= 3:
        sc["pyramid"] = 3 + len(ranks) + (1 if low & HIER else 0)
    years = {t for t in toks if _is_year(t)}
    if len(years) >= 2:
        sc["timeline"] = 4 + len(years)
    if has_image:
        sc["archival"] = 3 + (2 if idea == "evidence" else 0)
    return sorted(sc.items(), key=lambda kv: (-kv[1], RECIPES.index(kv[0])))


# --------------------------------------------------------------------------------------------- the working context of one beat
class _Ctx:
    def __init__(self, beat_id, start, end, sents, words, cased, table, roles, opt, narrator="only"):
        self.on = narrator != "none"                                  # the narrator figure is on screen: stay right of its zone; otherwise use the whole frame
        self.x0, self.x1 = (720, 1810) if self.on else (110, 1810)
        self.cx, self.w = (self.x0 + self.x1) // 2, self.x1 - self.x0
        self.beat_id, self.words, self.cased, self.table, self.roles, self.opt = beat_id, words, cased, table, roles, opt
        self.sents = list(sents)
        self.bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
        self.pos = {g: k for k, g in enumerate(self.bw)}
        self.tok = {g: norm(words[g][0]) for g in self.bw}
        self.sent_of: Dict[int, Sent] = {}
        self.breaks: set = set()
        for s in self.sents:
            self.breaks |= set(s.breaks)
            for g in s.widx:
                if g in self.pos:
                    self.sent_of[g] = s
        self.cues: List[Cue] = []
        self.required: set = set()
        self.phrases: List[Dict[str, Any]] = []
        self.used: set = set()
        self.n: Dict[str, int] = {}

    def cid(self, kind: str) -> str:
        self.n[kind] = self.n.get(kind, 0) + 1
        return f"{self.beat_id}_{kind}{self.n[kind]}"

    def at(self, g: int) -> Dict[str, int]:
        return {"index": self.pos[g]}

    def quote(self, a: int, b: int) -> str:
        return " ".join(_disp(self.tok[g], self.cased) for g in range(a, b + 1))

    def content(self, g: int) -> bool:
        t = self.tok[g]
        return bool(t) and (any(ch.isdigit() for ch in t) or (t not in LX.STOP and t not in LX.WEAK))

    def trim(self, seg: Sequence[int]) -> List[int]:
        seg = list(seg)
        while seg and not self.content(seg[0]):
            seg.pop(0)
        while seg and ((not self.content(seg[-1]) and self.tok[seg[-1]] not in KEEP_END) or self.tok[seg[-1]] in TRAIL):
            seg.pop()
        return seg

    def before(self, g: int, floor: int = -1, through_breaks: bool = False) -> List[int]:
        """Words left of g in its sentence back to the previous clause end (or the sentence start)."""
        out, j = [], g - 1
        while j in self.pos and self.sent_of.get(j) is self.sent_of.get(g) and j > floor:
            if j in self.breaks and not through_breaks:
                break
            out.append(j)
            j -= 1
        return out[::-1]

    def after(self, g: int, stop: int = 10 ** 9, through_breaks: bool = False) -> List[int]:
        out, j = [], g + 1
        while j in self.pos and self.sent_of.get(j) is self.sent_of.get(g) and j < stop:
            out.append(j)
            if j in self.breaks and not through_breaks:
                break
            j += 1
        return out

    def edge(self, region: Sequence[int], side: str, maxw: int, fit: Callable[[str], bool]) -> Optional[Phrase]:
        """The contiguous quote of up to maxw words at the `side` ("end" = nearest the marker on its left, "start" = nearest on its right) that starts and ends on content words and fits."""
        region = list(region)
        for n in range(min(len(region), maxw), 0, -1):
            seg = self.trim(region[-n:] if side == "end" else region[:n])
            if not seg or seg[-1] - seg[0] + 1 != len(seg):
                continue
            text = self.quote(seg[0], seg[-1])
            if fit(text):
                return Phrase(text, seg[0], seg[-1], [self.tok[g] for g in seg])
        return None

    def add(self, kind: str, g: int, text: str, pos: Optional[Tuple[int, int]], role: str = "blue", style: str = "", asset: str = "", required: bool = True,
            offset: Optional[float] = None, params: Optional[Dict[str, Any]] = None, first: Optional[int] = None, last: Optional[int] = None, label: str = "") -> str:
        cid = self.cid(style or kind)
        prm = dict(params or {})
        if style:
            prm["style"] = style
        self.cues.append(Cue(cid, kind, self.at(g), text=text, role=role, offset_s=offset, pos=pos, asset=asset, params=prm))
        if required:
            self.required.add(cid)
        if text and first is not None:
            self.used.update(range(first, (last if last is not None else first) + 1))
            s = self.sent_of.get(first)
            self.phrases.append({"sentence": s.index if s else -1, "label": s.label if s else "explain", "phrase": text, "asset": asset or None, "keyword": "", "role": role,
                                 "role_keyword": "", "first": first, "last": last if last is not None else first, "as": style or kind})
        return cid

    def arrow(self, g: int, src: str, dst: str, role: str = "blue", offset: float = 0.35, width: int = 16) -> str:
        cid = self.cid("arrow")
        self.cues.append(Cue(cid, "arrow", self.at(g), offset_s=offset, role=role, src=src, dst=dst, grow_s=0.5, params={"width": width}))
        self.required.add(cid)
        return cid

    def asset_for(self, first: int, last: int, used: set) -> str:
        """The picture of the first keyword the phrase says (from the metaphor table), not one already used in this composition; "" when none."""
        for g in range(first, last + 1):
            t = self.tok[g]
            a = self.table.get(t, "")
            if a and a in ICONS and a not in used and t not in LX.STOP and t not in LX.WEAK and t not in GENERIC:
                return a
        return ""

    def plan_node(self, ph: Phrase, wmax: int, used: set, solid: bool = False, px: int = 72, lines: int = 2, minw: int = 0, minpx: int = 48, minh: int = 0) -> Optional[Dict[str, Any]]:
        asset = self.asset_for(ph.first, ph.last, used)
        for a in ((asset, "") if asset else ("",)):
            prm = {"wmax": wmax, "solid": solid, "px": px, "minpx": minpx, "lines": lines, "minw": minw, "minh": minh}
            m = ST.measure("node", ph.text, prm, a)
            if m is not None:
                if a:
                    used.add(a)
                return {"ph": ph, "asset": a, "m": m, "prm": prm, "solid": solid}
        return None

    def emit_node(self, nd: Dict[str, Any], x: int, y: int, role: str) -> str:
        ph = nd["ph"]
        return self.add("visual", ph.first, ph.text, (x, y), role, "node", asset=nd["asset"], params=nd["prm"], first=ph.first, last=ph.last)

    def role_of(self, toks: Sequence[str]) -> str:
        r, _kw = role_for(list(toks), self.roles)
        return r if r in ("red", "green") else "blue"


def _fit_node(wmax: int, lines: int = 2, px: int = 60, minpx: int = 48) -> Callable[[str], bool]:
    def ok(text: str) -> bool:
        return ST.measure("node", text, {"wmax": wmax, "px": px, "minpx": minpx, "lines": lines}, "") is not None
    return ok


def _wp(wmax: int, **more: Any) -> Dict[str, Any]:
    """Params that keep a box or tag no wider than wmax px (text wrap = wmax minus its padding)."""
    return {"wrap": max(120, wmax - 84), **more}


def _fit_box(style: str, wmax: int) -> Callable[[str], bool]:
    def ok(text: str) -> bool:
        m = ST.measure(style, text, _wp(wmax))
        return m is not None and m["w"] <= wmax and len(m["lines"]) <= 2
    return ok


def _size(style: str, text: str, prm: Optional[Dict[str, Any]] = None) -> Tuple[int, int]:
    m = ST.measure(style, text, dict(prm or {}))
    return (m["w"], m["h"]) if m else (0, 0)


# --------------------------------------------------------------------------------------------- 1. cause and effect
REVEAL_STEP_S = 0.9


FIRST_NODE_LEAD_S = 1.0           # the first node of a chain is on the paper at most this long after its beat starts


def _chain_layout(c: _Ctx, nodes: List[Dict[str, Any]], roles_: List[str], later_first: List[int]) -> bool:
    """Nodes in a column (narrator on screen) or a row (whole frame), joined by arrows; the node order is the logical order."""
    n = len(nodes)
    ids: List[str] = []
    if c.on:
        gap = 120
        tot = sum(nd["m"]["h"] for nd in nodes) + gap * (n - 1)
        if tot > 790:
            return False
        y = max(110, 500 - tot // 2)
        for k, nd in enumerate(nodes):
            ids.append(c.emit_node(nd, c.cx - nd["m"]["w"] // 2, y, roles_[k]))
            y += nd["m"]["h"] + gap
    else:
        gap = 190 if n == 2 else 150
        tot = sum(nd["m"]["w"] for nd in nodes) + gap * (n - 1)
        if tot > c.w:
            return False
        x = c.cx - tot // 2
        for k, nd in enumerate(nodes):
            ids.append(c.emit_node(nd, x, 500 - nd["m"]["h"] // 2, roles_[k]))
            x += nd["m"]["w"] + gap
    # The cause and its effect are on the paper within about a second of each other, not only when their own words are spoken (a lone first node for 2-3 s reads as an empty board): a node
    # spoken late keeps its anchor word but its offset is negative so it arrives one beat after the node before it in speaking order.
    t_of = [float(c.words[nd["ph"].first][1]) for nd in nodes]
    order = sorted(range(n), key=lambda k: t_of[k])
    early: Dict[int, float] = {}
    t0 = float(c.words[c.bw[0]][1])
    shown = min(t_of[order[0]], t0 + FIRST_NODE_LEAD_S)          # a board is never empty for the first seconds of its beat while the first node waits for its spoken word
    if shown < t_of[order[0]] - 1e-6:
        early[order[0]] = shown - t_of[order[0]]
    for rank, k in enumerate(order[1:], 1):          # the second node follows the first by a beat; a third is brought forward by at most 1.2 s (never drawn before its sentence starts)
        show = min(t_of[k], shown + REVEAL_STEP_S) if rank == 1 else min(t_of[k], max(t_of[k] - 1.2, shown + REVEAL_STEP_S))
        early[k] = show - t_of[k]
        shown = show
    by_id = {q.id: q for q in c.cues}
    for k, off in early.items():
        if off < -1e-6:
            by_id[ids[k]].offset_s = round(off, 3)
    for k in range(1, n):
        later = max((k - 1, k), key=lambda q: t_of[q])
        c.arrow(later_first[k - 1], ids[k - 1], ids[k], role="red" if roles_[k] == "red" else "blue", offset=round(0.35 + early.get(later, 0.0), 3), width=18)
    return True


def _cause_effect(c: _Ctx) -> bool:
    toks = [c.tok[g] for g in c.bw]
    mk = [(c.bw[a], c.bw[b], d) for a, b, d in find_markers(toks)]
    if not mk:
        return False
    m1 = mk[0]
    nxt = next((m for m in mk[1:] if m[2] == "fwd" and c.sent_of.get(m[0]) is c.sent_of.get(m1[0])), None)       # a second link: cause -> effect -> consequence
    wm = 860 if c.on else 640
    fit = _fit_node(wm)
    left = c.edge(c.before(m1[0]), "end", 6, fit)
    if left is None and m1[2] == "fwd":                           # "taxes rose, which led to ...": the cause is the clause before the comma
        left = c.edge(c.before(m1[0], through_breaks=True), "end", 6, fit)
    if left is None and c.sent_of.get(m1[0]) is not None:        # "This led to ...": the cause is the end of the sentence before
        prev = [s for s in c.sents if s.index == c.sent_of[m1[0]].index - 1]
        if prev:
            tail = [g for g in prev[0].widx if g in c.pos]
            if tail:
                left = c.edge(tail[-6:], "end", 6, fit)
    right = c.edge(c.after(m1[1], stop=nxt[0] if nxt else 10 ** 9), "start", 6, fit)
    if left is None or right is None or left.text.lower() == right.text.lower() or left.first >= right.first:
        return False
    third = c.edge(c.after(nxt[1]), "start", 6, fit) if nxt else None
    if m1[2] == "rev":
        logical = [right, left] + ([third] if third and third.first > right.last else [])      # "prices rose because of the war": the war (spoken second) is the cause
    else:
        logical = [left, right] + ([third] if third and third.first > right.last else [])
    n = len(logical)
    for lines in (2, 1):
        wmax = wm if (c.on or n == 2) else (c.w - 300) // 3
        used: set = set()
        if not c.on and n == 3:
            logical = [c.edge(range(p.first, p.last + 1), "start", 4, _fit_node(wmax, lines)) or p for p in logical]
        nodes = [c.plan_node(ph, wmax, used, solid=(k > 0), lines=lines) for k, ph in enumerate(logical)]
        if any(x is None for x in nodes):
            continue
        roles_ = [c.role_of(p.tokens) for p in logical]
        order = sorted(range(n), key=lambda k: logical[k].first)
        later = [max(logical[k - 1].first, logical[k].first) for k in range(1, n)]
        if _chain_layout(c, nodes, roles_, later):
            return True
        c.cues.clear()
        c.required.clear()
        c.phrases.clear()
        c.used.clear()
    return False


def _scarcity(c: _Ctx) -> bool:
    """A lack and the limit it puts on something ("very little farmland, limited natural resources"): two nodes joined by an arrow, each a contiguous quote of the narration."""
    toks = [c.tok[g] for g in c.bw]
    lk = [c.bw[i] for i, t in enumerate(toks) if t in LACK]
    pair = next(((a, b) for a, b in zip(lk, lk[1:]) if b - a >= 2 and c.sent_of.get(a) is c.sent_of.get(b)), None)
    if pair is None:
        return False
    a, b = pair
    wm = 860 if c.on else 640
    fit = _fit_node(wm)
    left = c.edge(range(max(c.bw[0], a - 2), b), "start", 5, fit)
    left = c.edge(range(a, b), "start", 5, fit) if left is None else left
    right = c.edge(c.after(b - 1), "start", 5, fit)
    if left is None or right is None or left.last >= right.first or left.text.lower() == right.text.lower():
        return False
    for lines in (2, 1):
        used: set = set()
        nodes = [c.plan_node(ph, wm, used, solid=(k > 0), lines=lines) for k, ph in enumerate((left, right))]
        if any(x is None for x in nodes):
            continue
        if _chain_layout(c, nodes, [c.role_of(left.tokens), "red"], [right.first]):
            return True
        c.cues.clear(); c.required.clear(); c.phrases.clear(); c.used.clear()
    return False


# --------------------------------------------------------------------------------------------- 2. before and after
DET = frozenset("the a an this that these those his her their its our my".split())
AUX = frozenset("was were is are had has have did does became grew got been be will would".split())


def _clause_start(c: _Ctx, reg: List[int]) -> List[int]:
    """The panel quote starts at the clause the marker introduces: "before the war farms were small" gives "farms were small", never a stray noun of the marker phrase."""
    for i, g in enumerate(reg[:4]):
        if g in c.breaks and i < len(reg) - 1:
            return reg[i + 1:]
    if reg and c.tok[reg[0]] in DET:
        for k in range(2, min(len(reg), 6)):
            if c.tok[reg[k]] in AUX:
                return reg[k - 1:]
        if len(reg) >= 4 and sum(1 for g in reg[2:] if c.content(g)) >= 2:
            return reg[2:]
    return reg


def _before_after(c: _Ctx) -> bool:
    marks = []
    for g in c.bw:
        t = c.tok[g]
        if t in PAST or (t == "used" and c.tok.get(g + 1) == "to"):
            marks.append((g, g + 1 if t == "used" else g, "past"))
        elif t in PRESENT:
            marks.append((g, g, "present"))
    pair = None
    for a in marks:
        for b in marks:
            if a[2] == "past" and b[2] == "present" and a[0] != b[0] and abs(a[0] - b[0]) >= 3:
                pair = (a, b)
                break
        if pair:
            break
    if not pair:
        return False
    (pa, pb, _), (qa, qb, _) = pair
    wcol = (c.w - 330) if c.on else 700
    fit = _fit_node(wcol, 2, 80, 64)

    def side(last_m, stop) -> Optional[Phrase]:
        reg = c.after(last_m, stop=stop, through_breaks=True)
        cut = next((i for i, g in enumerate(reg) if g in c.breaks and i >= 2), len(reg) - 1)
        reg = _clause_start(c, reg[:cut + 1])
        ph = c.edge(reg, "start", 6, fit)
        if ph is not None and c.tok.get(ph.first - 1) in DET and ph.first - 1 > last_m:      # never begin on the noun of the marker phrase
            ph = c.edge([g for g in reg if g > ph.first], "start", 6, fit)
        return ph

    past = side(pb, qa if qa > pa else 10 ** 9)
    pres = side(qb, pa if pa > qa else 10 ** 9)
    if past is None or pres is None or past.text.lower() == pres.text.lower():
        return False
    used: set = set()
    mw, mh = (0, 210) if c.on else (620, 250)
    # the "before" panel is muted (grey, light), the "now" panel strong (solid colour)
    nl = c.plan_node(past, wcol, used, False, px=80, minpx=64, minw=mw, minh=mh)
    nr = c.plan_node(pres, wcol, used, True, px=80, minpx=64, minw=mw, minh=mh)
    if nl is None or nr is None:
        return False
    tag_l, tag_r = c.quote(pa, pb), c.quote(qa, qb)
    tp = {"px": 80, "wrap": 600}
    (twl, thl), (twr, thr) = _size("tag", tag_l, tp), _size("tag", tag_r, tp)
    if 0 in (twl, twr):
        return False
    if c.on:                                      # a column: tag and panel on one row, the present row below the past row, an arrow down between the panels
        tw = max(twl, twr)
        pw = max(nl["m"]["w"], nr["m"]["w"])
        x_tag = c.cx - (tw + 24 + pw) // 2
        x_pan = x_tag + tw + 24
        h1, h2 = max(nl["m"]["h"], thl), max(nr["m"]["h"], thr)
        gap = 150
        y1 = 500 - (h1 + gap + h2) // 2
        y2 = y1 + h1 + gap
        c.add("visual", pa, tag_l, (x_tag, y1 + (h1 - thl) // 2), "blue", "tag", params=tp, first=pa, last=pb)
        c.add("visual", qa, tag_r, (x_tag, y2 + (h2 - thr) // 2), "blue", "tag", params=tp, first=qa, last=qb)
        i1 = c.emit_node(nl, x_pan, y1 + (h1 - nl["m"]["h"]) // 2, "ink")
        i2 = c.emit_node(nr, x_pan, y2 + (h2 - nr["m"]["h"]) // 2, c.role_of(pres.tokens))
    else:                                         # side by side, tags above, the arrow centred between the panels
        gap = 240
        tot = nl["m"]["w"] + gap + nr["m"]["w"]
        xl = c.cx - tot // 2
        xr = xl + nl["m"]["w"] + gap
        hp = max(nl["m"]["h"], nr["m"]["h"])
        thm = max(thl, thr)
        ty = 500 - (thm + 60 + hp) // 2
        py = ty + thm + 60
        c.add("visual", pa, tag_l, (xl + (nl["m"]["w"] - twl) // 2, ty), "blue", "tag", params=tp, first=pa, last=pb)
        c.add("visual", qa, tag_r, (xr + (nr["m"]["w"] - twr) // 2, ty), "blue", "tag", params=tp, first=qa, last=qb)
        i1 = c.emit_node(nl, xl, py + (hp - nl["m"]["h"]) // 2, "ink")
        i2 = c.emit_node(nr, xr, py + (hp - nr["m"]["h"]) // 2, c.role_of(pres.tokens))
    c.arrow(max(past.first, pres.first), i1, i2, role="blue", width=22)
    return True


# --------------------------------------------------------------------------------------------- 3. two columns
def _two_column(c: _Ctx) -> bool:
    mk = next((g for g in c.bw if c.tok[g] in COMPARE_MARK and c.before(g) and c.after(g, through_breaks=True)), None)
    if mk is None:
        return False
    s = c.sent_of[mk]
    sidx = [g for g in s.widx if g in c.pos]
    lreg = [g for g in sidx if g < mk]
    rreg = [g for g in sidx if g > mk]
    colw, div = (500, 24) if c.on else (700, 220)
    fit_row = _fit_node(colw, 2, 64, 56)

    def header_of(reg: List[int]) -> Optional[List[int]]:
        reg = c.trim(reg)
        if not reg:
            return None
        h = [reg[0]]
        if len(reg) > 1 and reg[1] == reg[0] + 1 and c.content(reg[1]) and (c.tok[reg[0]] in c.cased or c.tok[reg[1]] in c.cased):
            h.append(reg[1])
        return h

    tp = {"px": 80, "wrap": 600}
    cols = []
    used: set = set()
    for reg in (lreg, rreg):
        hd = header_of(reg)
        if not hd or ST.measure("tag", c.quote(hd[0], hd[-1]), tp) is None:
            return False
        rest = [g for g in reg if g > hd[-1]]
        rows = best_phrases(rest, c.words, c.cased, c.table, c.breaks, k=3, max_words=4, fit=fit_row, min_score=3.0, min_words=2)
        if not rows:
            one = c.edge(rest, "end", 4, fit_row)
            rows = [one] if one else []
        rows = sorted(rows, key=lambda p: p.first)[:3]
        nodes = [c.plan_node(p, colw, used, False, px=64, minpx=56, minw=colw - 40, minh=170) for p in rows]
        nodes = [x for x in nodes if x]
        if not nodes:
            return False
        cols.append((hd, nodes))
    nrows = max(len(cols[0][1]), len(cols[1][1]))
    rowh = [max([cols[k][1][i]["m"]["h"] for k in (0, 1) if i < len(cols[k][1])]) for i in range(nrows)]
    th0 = max(_size("tag", c.quote(hd[0], hd[-1]), tp)[1] for hd, _n in cols)
    gap = 44
    tot = th0 + gap + sum(rowh) + gap * (nrows - 1)
    if tot > 800:
        return False
    top = max(110, 500 - tot // 2)
    xs = (c.cx - div // 2 - colw, c.cx + div // 2)                  # left edge of each column
    for k, (hd, nodes) in enumerate(cols):
        text = c.quote(hd[0], hd[-1])
        tw, th = _size("tag", text, tp)
        c.add("visual", hd[0], text, (xs[k] + (colw - tw) // 2, top + (th0 - th) // 2), "blue", "tag", params=tp, first=hd[0], last=hd[-1])
        y = top + th0 + gap
        for i, nd in enumerate(nodes):                                # rows share a baseline across the two columns
            c.emit_node(nd, xs[k] + (colw - nd["m"]["w"]) // 2, y + (rowh[i] - nd["m"]["h"]) // 2, "blue" if k == 0 else "gold")
            y += rowh[i] + gap
    c.add("visual", mk, c.tok[mk], (c.cx - div // 2, top), "ink", "bars", params={"divider": True, "box_w": div, "box_h": tot, "px": 56}, required=False, offset=0.0)
    return True


# --------------------------------------------------------------------------------------------- numbers (pictogram and bar chart)
def _numbers(c: _Ctx) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    g_list = c.bw
    i = 0
    while i < len(g_list):
        g = g_list[i]
        clean = re.sub(r"[^\w,.%$]", "", c.words[g][0])
        t = c.tok[g]
        nxt = c.tok.get(g + 1, "")
        v = None
        if NUM_RE.fullmatch(clean):
            try:
                v = float(clean.strip("$%").replace(",", ""))
            except ValueError:
                v = None
            if v is not None and _is_year(t) and nxt not in SCALE:
                v = None
            text = clean
        elif t in NUMW and (nxt in SCALE or (nxt and nxt not in LX.STOP and nxt not in LX.WEAK and g + 1 in c.pos)):
            v, text = NUMW[t], t
        if v is None or v <= 0:
            i += 1
            continue
        last = g
        if nxt in SCALE and g + 1 in c.pos:
            v *= SCALE[nxt]
            last = g + 1
            text = f"{text} {nxt}"
        noun = next((j for j in (last + 1, last + 2) if j in c.pos and c.sent_of.get(j) is c.sent_of.get(g) and c.content(j) and not NUM_RE.fullmatch(c.tok[j]) and c.tok[j] not in NUMW
                     and c.tok[j] not in SCALE), None)
        out.append({"g": g, "last": last, "v": v, "text": text, "noun": noun})
        i += 1 + (last - g)
    return out


VERBISH = frozenset("produced made had sold lost won earned paid cost grew fell rose reached counted numbered killed captured sent built exported imported spent gained owned used saw took gave".split())


def _verbish(c: _Ctx, g: int) -> bool:
    t = c.tok[g]
    return t in VERBISH or (len(t) > 4 and t.endswith("ed") and t not in c.cased)


def _pictogram(c: _Ctx) -> bool:
    nums = _numbers(c)
    if len(nums) != 1 or nums[0]["v"] < 2:
        return False
    nm = nums[0]
    n = int(min(12, round(nm["v"]))) if nm["v"] <= 12 else 12
    rows = -(-n // 6)
    sizes = [n // rows + (1 if r < n % rows else 0) for r in range(rows)]
    if any(s < 2 for s in sizes):
        return False
    text = c.quote(nm["g"], nm["noun"]) if nm["noun"] == nm["last"] + 1 else c.quote(nm["g"], nm["last"])
    last_word = nm["noun"] if nm["noun"] is not None else nm["last"]
    tp = {"px": 80, "wrap": min(c.w - 140, 900)}
    tw, th = _size("tag", text, tp)
    if tw == 0:
        return False
    kind = ""
    if nm["noun"] is not None:                                  # the character pack's type for the counted noun (soldiers -> soldier): one outfit across the whole grid
        try:
            from . import lexicon_v2 as LV
            from ..cartoon import characters as CH
            from ..cartoon import kit_v2
            t = c.tok[nm["noun"]]
            k = LV.CHARACTER_OF.get(t) or LV.CHARACTER_OF.get(t + "s") or LV.CHARACTER_OF.get(t[:-1] if t.endswith("s") else t)
            if k and kit_v2.install() and CH.is_character(k):
                kind = k
        except Exception:
            kind = ""
    h_fig = 250 if c.on else 280
    probe = {"n": 6, "height": h_fig, "seed": 1000, **({"kind": kind} if kind else {})}
    mh = (ST.measure("crowd", "", probe) or {"h": h_fig})["h"]
    tot = th + 50 + rows * mh + (rows - 1) * 40
    top = max(110, 500 - tot // 2)
    c.add("visual", nm["g"], text, (c.cx - tw // 2, top), "blue", "tag", params=tp, first=nm["g"], last=last_word)
    anchors = [g for g in c.bw if g >= nm["last"] and g != nm["g"]]
    for r, k in enumerate(sizes):
        a = anchors[min(r, len(anchors) - 1)] if anchors else nm["g"]
        if r > 0 and a == anchors[min(r - 1, len(anchors) - 1)]:
            a = c.bw[min(c.bw.index(a) + 1, len(c.bw) - 1)]
        prm = {"n": k, "height": h_fig, "seed": 1000 + r if kind else r, **({"kind": kind} if kind else {})}
        m = ST.measure("crowd", "", prm) or {"w": 600, "h": h_fig}
        c.add("visual", a, "", (c.cx - m["w"] // 2, top + th + 50 + r * (m["h"] + 40)), "blue", "crowd", params=prm, offset=0.1)
    return True


def _bar_chart(c: _Ctx) -> bool:
    nums = _numbers(c)
    if len(nums) < 2:
        return False
    nums = nums[:4]
    vmax, vmin = max(x["v"] for x in nums), min(x["v"] for x in nums)
    if vmax / vmin < 1.15:
        return False
    n = len(nums)
    gap = 80
    bw_ = min(380, (c.w - (n - 1) * gap) // n)
    x0 = c.cx - (n * bw_ + (n - 1) * gap) // 2
    nouns = [x["noun"] for x in nums]
    same = len({c.tok[g] for g in nouns if g is not None}) < n or any(g is None for g in nouns)      # "tons", "tons": the subject before each number says more
    for k, nm in enumerate(nums):
        label = None if same else nm["noun"]
        if label is None:
            run: List[int] = []
            for j in range(nm["g"] - 1, max(nm["g"] - 6, -1), -1):          # the words just before the number ("Britain produced"): the subject is a name or the farthest noun of the run
                if j not in c.pos or c.sent_of.get(j) is not c.sent_of.get(nm["g"]) or NUM_RE.fullmatch(c.tok[j]):
                    break
                if not c.content(j) or _verbish(c, j):
                    if run and not _verbish(c, j):
                        break
                    continue
                run.append(j)
            label = next((j for j in run if c.tok[j] in c.cased), run[-1] if run else None)
            if label is None and nm["noun"] is not None and not _verbish(c, nm["noun"]):
                label = nm["noun"]
        lab = _disp(c.tok[label], c.cased) if label is not None else ""
        c.add("visual", nm["g"], nm["text"], (x0 + k * (bw_ + gap), 110), ("blue", "gold", "green", "red")[k], "bars",
              params={"ratio": nm["v"] / vmax, "label": lab, "box_w": bw_, "box_h": 690, "bar_w": min(240, bw_ - 40), "px": 64}, first=nm["g"], last=nm["last"])
    return True


# --------------------------------------------------------------------------------------------- 5. pyramid
def _pyramid(c: _Ctx) -> bool:
    seen: Dict[int, int] = {}
    for g in c.bw:
        r = TIER_RANK.get(c.tok[g])
        if r is not None and r not in seen:
            seen[r] = g
    if len(seen) < 3:
        return False
    ranks = sorted(seen)[:4] if len(seen) <= 4 else [sorted(seen)[0], sorted(seen)[1], sorted(seen)[2], sorted(seen)[-1]]
    top_w = min(c.w, 1090 if c.on else 1620)
    widths = [int(top_w * f) for f in ((0.40, 0.70, 1.0) if len(ranks) == 3 else (0.34, 0.58, 0.80, 1.0))]
    used: set = set()
    nodes = []
    for k, r in enumerate(ranks):
        g = seen[r]
        ph = Phrase(_disp(c.tok[g], c.cased), g, g, [c.tok[g]])
        nd = c.plan_node(ph, widths[k], used, True, px=76, lines=1, minw=widths[k])
        if nd is None:
            return False
        nodes.append(nd)
    tot = sum(nd["m"]["h"] + 14 for nd in nodes) - 14
    y = 500 - tot // 2
    for k, nd in enumerate(nodes):
        c.emit_node(nd, c.cx - nd["m"]["w"] // 2, y, TIER_ROLE[k])
        y += nd["m"]["h"] + 14
    return True


# --------------------------------------------------------------------------------------------- 6. timeline
def _timeline(c: _Ctx) -> bool:
    yrs: List[int] = []
    for g in c.bw:
        if _is_year(c.tok[g]) and all(c.tok[g] != c.tok[x] for x in yrs):
            yrs.append(g)
    if len(yrs) < 2:
        return False
    px = 68
    cw, ch = E.chip_size("1815", px)
    n = min(4, len(yrs))
    while n >= 2 and (n - 1) * (cw + 110) > c.w - cw:
        n -= 1
    if n < 2:
        return False
    yrs = yrs[:n]
    step = min(460, (c.w - cw - 40) // (n - 1))
    lw = min(480, int(step * 1.55)) if n > 2 else 480
    fit = _fit_node(lw)
    labels: List[Optional[Phrase]] = []
    taken: set = set()
    PREP = ("in", "by", "on", "around", "until", "since", "from", "of")
    for k, g in enumerate(yrs):
        nxt = yrs[k + 1] if k + 1 < n else 10 ** 9
        floor = yrs[k - 1] if k else -1
        tail = c.tok.get(g - 1) in PREP                                   # "... rose in 1789": the label is what comes before the year
        reg_b = [x for x in c.before(g, floor=floor, through_breaks=True) if x not in taken]
        reg_b = reg_b[:-1] if reg_b and c.tok[reg_b[-1]] in PREP else reg_b
        reg_a = [x for x in c.after(g, stop=nxt) if x not in taken]
        order = ((reg_b, "end"), (reg_a, "start")) if tail else ((reg_a, "start"), (reg_b, "end"))
        lab = None
        for reg, side in order:
            lab = c.edge(reg, side, 4, fit)
            if lab is not None and not set(range(lab.first, lab.last + 1)) & taken:
                break
            lab = None
        if lab is not None:
            taken.update(range(lab.first, lab.last + 1))
        labels.append(lab)
    if sum(1 for x in labels if x) < 2:
        return False
    cx0 = c.cx - step * (n - 1) // 2
    axis_y = 500
    used: set = set()
    chip_ids = []
    for k, g in enumerate(yrs):
        cx = cx0 + k * step
        chip_ids.append(c.add("chip", g, c.tok[g], (cx - cw // 2, axis_y - ch // 2), "ink", params={"px": px}, first=g, last=g))
        lab = labels[k]
        if lab is not None:
            nd = c.plan_node(lab, lw, used, solid=(k % 2 == 1), px=60)
            if nd is None:
                continue
            w_, h_ = nd["m"]["w"], nd["m"]["h"]
            y = axis_y - ch // 2 - 60 - h_ if k % 2 == 0 else axis_y + ch // 2 + 60
            x = max(c.x0, min(c.x1 - w_, cx - w_ // 2))
            c.emit_node(nd, x, y, "blue" if k % 2 == 0 else "gold")
    for k in range(1, n):
        c.arrow(yrs[k], chip_ids[k - 1], chip_ids[k], role="ink", offset=0.3, width=14)
    return True


# --------------------------------------------------------------------------------------------- 8. archival picture card
def _archive_entries(opt: DirectorOptions) -> List[Dict[str, Any]]:
    d = getattr(opt, "archive_dir", None)
    if not d:
        return []
    try:
        data = json.loads((Path(d) / "archive.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for e in data if isinstance(data, list) else []:
        f = Path(str(e.get("file", "")))
        f = f if f.is_absolute() else Path(d) / f
        if f.is_file() and e.get("subjects"):
            out.append({"file": str(f), "subjects": [str(s) for s in e["subjects"]]})
    return out


def _archival(c: _Ctx) -> bool:
    toks = [c.tok[g] for g in c.bw]
    for e in _archive_entries(c.opt):
        for subj in e["subjects"]:
            sw = [norm(w) for w in subj.split() if norm(w)]
            if not sw:
                continue
            at = next((i for i in range(len(toks) - len(sw) + 1) if toks[i:i + len(sw)] == sw), None)
            if at is None:
                continue
            g0 = c.bw[at]
            g1 = g0 + len(sw) - 1
            try:
                from PIL import Image
                with Image.open(e["file"]) as im:
                    iw, ih = im.size
            except Exception:
                continue
            name = c.quote(g0, g1)
            w_ = 620 if c.on else 700
            h_ = int(max(520, min(790, (w_ - 44) * ih / iw + 44 + 64)))
            if ST.measure("photo", name, {"w": w_, "h": h_}) is None:
                continue
            x_ph = c.x0 + 20 if c.on else c.cx - (w_ + 80 + 700) // 2
            c.add("visual", g0, name, (x_ph, max(110, 500 - h_ // 2)), "blue", "photo", params={"w": w_, "h": h_, "image": e["file"]}, first=g0, last=g1)
            rest = [g for g in c.bw if g > g1]
            lw = c.x1 - (x_ph + w_ + 50)
            ph = best_phrases(rest, c.words, c.cased, c.table, c.breaks, k=1, max_words=7,
                              fit=lambda t: ST.measure("line", t, {"width": lw, "px": 60, "lines": 3}) is not None, min_score=4.0, min_words=2)
            if ph:
                c.add("visual", ph[0].first, ph[0].text, (x_ph + w_ + 50, 330), "ink", "line", required=False, offset=0.0, first=ph[0].first, last=ph[0].last,
                      params={"width": lw, "px": 60, "lines": 3, "tint": False, "sync": True})
            return True
    return False


BUILDERS: Dict[str, Callable[[_Ctx], bool]] = {"cause_effect": _cause_effect, "before_after": _before_after, "two_column": _two_column, "pictogram": _pictogram, "pyramid": _pyramid,
                                              "timeline": _timeline, "bar_chart": _bar_chart, "archival": _archival, "scarcity": _scarcity}
MIN_SCORE = 3


# --------------------------------------------------------------------------------------------- entry
def author_recipe(beat_id: str, start: float, end: float, sents: Sequence[Sent], words, cased: Dict[str, str], opt: DirectorOptions, table: Dict[str, str], roles: Dict[str, str],
                  narrator: str, carry_pose: str, variant: int = 0, idea: str = "") -> Optional[BoardResult]:
    """A BoardResult built by the best-scoring recipe whose evidence holds and whose required elements all survive the layout gate; None when no recipe applies (the caller then authors
    the beat as usual). Same inputs as compose_ref.author_ref plus the beat's idea."""
    if idea == "dialogue":
        return None
    c0 = _Ctx(beat_id, start, end, sents, words, cased, table, roles, opt, narrator)
    if not c0.bw:
        return None
    has_image = bool(_archive_entries(opt))
    for name, score in pick_recipe([c0.tok[g] for g in c0.bw], idea, has_image):
        if score < MIN_SCORE:
            continue
        c = _Ctx(beat_id, start, end, sents, words, cased, table, roles, opt, narrator)
        try:
            ok = BUILDERS[name](c)
        except Exception:                         # never stop: the beat keeps its ordinary composition
            if os.environ.get("EXPLAINER_RECIPES_DEBUG"):
                raise
            ok = False
        if not ok or not c.cues:
            continue
        res = _finish(c, name, narrator, carry_pose, start, end, words, opt)
        if res is not None:
            return res
    return None


def _finish(c: _Ctx, name: str, narrator: str, carry_pose: str, start: float, end: float, words, opt: DirectorOptions) -> Optional[BoardResult]:
    cues = list(c.cues)
    res = BoardResult([])
    last_pose = carry_pose
    if narrator != "none":
        first_pose = carry_pose if narrator in ("mid", "end") else "explain"
        enter = "slide" if narrator in ("only", "start") else "none"
        cues.insert(0, Cue(f"{c.beat_id}_n_show", "narrator", {"index": 0}, params={"action": "show", "pose": first_pose, "side": "left", "scale": 1.0, "enter": enter,
                                                                                       **({"style": opt.narrator_style} if opt.narrator_style != "cartoon" else {})}))
        last_pose = first_pose
        if narrator in ("only", "end"):
            late = [k for k, g in enumerate(c.bw) if words[g][1] <= end - 0.45]
            cues.append(Cue(f"{c.beat_id}_n_hide", "narrator", {"index": late[-1] if late else len(c.bw) - 1}, params={"action": "hide", "exit": "slide"}))
    res.cues = cues
    res.authored = list(cues)
    res.phrases = list(c.phrases)
    res.used_extra = set(c.used)
    res.last_pose = last_pose
    first = next(iter(c.phrases), None)
    res.subject = first["phrase"] if first else " ".join(c.tok[g] for g in c.bw[:2])
    gate(res, c.beat_id, start, end, words, opt)
    kept = {q.id for q in res.cues}
    if not c.required <= kept or res.problems:
        return None                                # the layout gate would have dropped a required element: a half-drawn diagram is worse than the ordinary board
    res.repairs.append(f"{c.beat_id}: recipe {name}")
    res.recipe = name                              # type: ignore[attr-defined]
    return res
