"""What If: the reference's information block, from the narration.

Every few seconds the references (V1-V3) put the same three-part block in the left third of the frame, beside the subject:
a small cyan KICKER ("ALL SIX COMPUTERS TOGETHER / HOLD ABOUT"), a huge white HEADLINE or number ("70"), and a short SUB-LINE
("KILOBYTES"). Render #016 had such type on screen 41 % of the time and ten numbers in eighteen minutes.

This pass adds the block where the narration gives one and nothing else is being said on screen:
- a number the narrator says (narration.extract_metrics: the value and unit as spoken), its kicker the words before it in its clause
  and its sub-line the words after it;
- else a named thing or term the narrator says (a craft, a world, a mission term), with the words around it.
Nothing is invented: every word on screen is a word of the narration. A block never crosses a cut, never repeats a headline within
REPEAT_S, and is never put over a photograph or clip (those keep their own captions) or over a diagram.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import narration as nr

EVERY_S = 5.5          # a block at most this often (the references change something every ~5 s)
BLOCK_MAX_S = 6.5
BLOCK_MIN_S = 2.4
REPEAT_S = 90.0
KICKER_WORDS, SUB_WORDS = 6, 6
LINE_CHARS = 30        # a kicker line wraps at about this many characters (two lines at most)
TEXT_TYPES = ("tm_caption", "tm_metric", "tm_title", "tm_section", "tm_annotate")
# what a block may sit on: the subject is a model or a world, or the sky. A photo or a clip keeps its caption; a diagram owns its plate
HOSTS = ("craft", "globe", "hero")

# mission terms worth a headline when the narrator says them (lower case, as heard)
TERMS = ("interstellar space", "termination shock", "heliopause", "heliosphere", "solar wind", "oort cloud", "golden record", "pale blue dot",
         "family portrait", "asteroid belt", "deep space network", "astronomical unit", "light-day", "light day", "light-year", "light year",
         "plutonium", "radioisotope", "magnetometer", "plasma wave", "cosmic rays", "great red spot", "gravity assist", "slingshot",
         "grand tour", "bow shock", "kuiper belt", "termination", "magnetic field", "the sun's bubble", "red dwarf", "alpha centauri",
         "proxima centauri", "milky way")


# a line never starts or ends on these: "OR / ≈173 AU", "... THE PRESSURE OF THAT", "... THE INSTRUMENT DESIGNED"
_WEAK = set(nr.FILLER) | set(nr.TAIL_WORDS) | {"or", "because", "while", "when", "since", "if", "who", "whose", "where", "what", "are", "were",
                                                "be", "been", "being", "has", "have", "had", "his", "her", "they", "we", "you", "i", "he", "she",
                                                "there", "here", "would", "could", "should", "will", "can", "may", "might", "did", "does", "do",
                                                "designed", "called", "known", "made", "said", "not", "no", "one's", "these", "those", "very"}


def _clean(tokens: List[str]) -> List[str]:
    toks = [re.sub(r"[^\w'°%\-.,×]", "", t).strip(",.") for t in tokens]
    toks = [t for t in toks if t and (len(t) > 1 or t.isdigit() or t.lower() == "a")]     # a stray letter from the transcript ("outbursts t")
    while toks and toks[0].lower() in _WEAK:
        toks.pop(0)
    while toks and toks[-1].lower() in _WEAK:
        toks.pop()
    return toks


def _whole(toks: List[str], n: int) -> List[str]:
    """The next clause as a sub-line only when all of it fits: half a clause from elsewhere says something else."""
    return toks if 2 <= len(toks) <= n else []


def _cut(toks: List[str], n: int, *, from_end: bool = False) -> List[str]:
    """At most n words, then trimmed back to a line that does not start or end on a weak word."""
    part = toks[-n:] if from_end else toks[:n]
    return _clean(part)


def _lines(toks: List[str]) -> str:
    """A kicker in at most two lines of about LINE_CHARS (the reference's "ALL SIX COMPUTERS TOGETHER / HOLD ABOUT")."""
    words = " ".join(toks).upper().split()
    lines: List[List[str]] = [[]]
    for w in words:                                    # whole words only, two lines at most
        if lines[-1] and len(" ".join(lines[-1] + [w])) > LINE_CHARS:
            if len(lines) == 2:
                break
            lines.append([])
        lines[-1].append(w)
    return "\n".join(" ".join(ln) for ln in lines if ln)


def _names() -> List[Tuple[re.Pattern, str]]:
    from .planner import CRAFT, WORLDS

    out = [(re.compile(p, re.I), name) for p, _m, name in CRAFT] + [(re.compile(p, re.I), name) for p, _t, name, _c in WORLDS]
    out += [(re.compile(rf"\b{re.escape(t)}\b", re.I), t.upper()) for t in TERMS]
    for extra, name in ((r"\bsaturn\b", "SATURN"), (r"\btitan\b", "TITAN"), (r"\bio\b(?!n)", "IO"), (r"\beuropa\b", "EUROPA"),
                        (r"\bganymede\b", "GANYMEDE"), (r"\bpluto\b", "PLUTO")):
        out.append((re.compile(extra, re.I), name))
    return out


def _term_in(words: Sequence[nr.Word], a: int, b: int, names) -> Optional[Tuple[int, int, str]]:
    """(first word, last word, headline) of the most specific named thing said in words[a..b]: the longest match wins."""
    low = [w.norm for w in words]
    best = None
    for i in range(a, b + 1):
        for j in range(i, min(b, i + 3) + 1):
            phrase = " ".join(low[i:j + 1])
            for rx, name in names:
                if rx.fullmatch(phrase) and (best is None or j - i > best[1] - best[0]):
                    best = (i, j, name)
    return best


def _busy(layers: Sequence[Dict[str, Any]], t0: float, t1: float) -> bool:
    for L in layers:
        if L.get("type") in TEXT_TYPES or (L.get("type") == "tm_template" and not L.get("plate")):
            if float(L.get("start", 0)) < t1 and t0 < float(L.get("end", 0)):
                return True
    return False


def _diagram_over(layers: Sequence[Dict[str, Any]], s: Any) -> bool:
    from .planner import DIAGRAMS

    return any((L.get("type") in DIAGRAMS or (L.get("type") == "tm_template" and L.get("plate"))) and float(L.get("start", 0)) < s.end
               and s.start < float(L.get("end", 0)) for L in layers)


def typeset(shots: Sequence[Any], layers: List[Dict[str, Any]], words: Sequence[nr.Word], metrics: Sequence[nr.Metric],
            duration: float, notes: List[str]) -> int:
    """Add the information blocks (tm_metric with a kicker, or a large tm_caption, both at the left) to `layers`. Returns how many."""
    if not words:
        return 0
    cl = nr.clauses(list(words))
    names = _names()
    shown: Dict[str, float] = {}
    for L in layers:                                   # what is already on screen counts against repeats
        key = str(L.get("text") or L.get("value") or "").upper().strip()
        if key:
            shown[key] = float(L.get("start", 0))
    by_word = {m.i0: m for m in metrics}
    last = -1e9
    added = 0
    for s in shots:
        empty_plate = s.kind == "plate" and not _diagram_over(layers, s)
        # a real photograph takes a block too: it is then shown as a card on the right (compile.py), the block beside it (V3 1:46)
        photo = s.kind == "image" and getattr(s, "cite", ("",))[0] == "REAL IMAGE"
        if s.kind not in HOSTS and not empty_plate and not photo:
            continue
        for k, (a, b) in enumerate(cl):
            t_say = words[a].start
            if t_say < s.start + 0.2 or t_say > s.end - BLOCK_MIN_S or t_say - last < EVERY_S:
                continue
            block = _block(words, cl, k, by_word, names)
            if block is None:
                continue
            head = block["head"]
            if head in shown and t_say - shown[head] < REPEAT_S:
                continue
            t0 = max(s.start + 0.05, t_say - nr.LEAD_S - 0.15)
            nxt_end = words[cl[k + 1][1]].end if k + 1 < len(cl) else words[b].end
            t1 = min(s.end - 0.12, t0 + BLOCK_MAX_S, max(t0 + BLOCK_MIN_S + 0.6, nxt_end + 0.8), duration - 0.2)
            if t1 - t0 < BLOCK_MIN_S or _busy(layers, t0 - 0.2, t1):
                continue
            timing = {"start": round(t0, 3), "end": round(t1, 3), "fade_in": 0.05, "fade_out": 0.3, "z": 5, "typeset": True}
            if block["metric"] is not None:
                m = block["metric"]
                L = {"type": "tm_metric", "value": ("≈ " if m.approx else "") + m.shown + ("×" if m.kind == "ratio" else ""),
                     "unit": "" if m.kind == "ratio" else m.unit, "kicker": block["kicker"], "sub": block["sub"], "sub_color": "amber",
                     "anchor": "left", "size": "large" if len(m.shown + m.unit) <= 12 else "medium", **timing}
                m.extra["shown"] = True
            else:
                L = {"type": "tm_caption", "text": head, "kicker": block["kicker"], "sub": block["sub"], "sub_color": "amber",
                     "size": "large", "anchor": "ml", **timing}
            layers.append(L)
            shown[head] = t0
            last = t_say
            added += 1
    if added:
        notes.append(f"plan: {added} information block(s) from the narration (kicker, headline, sub-line at the left)")
    return added


def number_words(words: Sequence[nr.Word], cl, m: nr.Metric) -> Tuple[str, str]:
    """(kicker, sub-line) for a spoken number: the words before it in its clause and the words after it, as said."""
    k = next((i for i, (a, b) in enumerate(cl) if a <= m.i0 <= b), None)
    if k is None:
        return "", ""
    a, b = cl[k]
    nxt = words[cl[k + 1][0]:cl[k + 1][1] + 1] if k + 1 < len(cl) else []
    kicker = _cut(_clean([w.text for w in words[a:m.i0]]), KICKER_WORDS, from_end=True)
    sub = _cut(_clean([w.text for w in words[m.i1 + 1:b + 1]]), SUB_WORDS) or _whole(_clean([w.text for w in nxt]), SUB_WORDS)
    if any(re.search(r"\d", t) for t in sub):
        sub = []
    return _lines(kicker), " ".join(sub).upper()


def _block(words: Sequence[nr.Word], cl, k: int, by_word: Dict[int, nr.Metric], names) -> Optional[Dict[str, Any]]:
    """The block one clause gives (with the next clause for its sub-line), or None when it says nothing worth a headline."""
    a, b = cl[k]
    m = next((by_word[i] for i in range(a, b + 1) if i in by_word and not by_word[i].extra.get("shown")
              and not (by_word[i].kind == "duration" and by_word[i].value < 1.0)), None)
    nxt = words[cl[k + 1][0]:cl[k + 1][1] + 1] if k + 1 < len(cl) else []
    if m is not None:
        kicker = _cut(_clean([w.text for w in words[a:m.i0]]), KICKER_WORDS, from_end=True)
        sub = _cut(_clean([w.text for w in words[m.i1 + 1:b + 1]]), SUB_WORDS) or _whole(_clean([w.text for w in nxt]), SUB_WORDS)
        if any(re.search(r"\d", t) for t in sub):
            sub = []                                   # another number: it gets its own block
        return {"metric": m, "head": (m.shown + " " + m.unit).strip().upper(), "kicker": _lines(kicker), "sub": " ".join(sub).upper()}
    hit = _term_in(words, a, b, names)
    if hit is None:
        return None
    i, j, head = hit
    kicker = _cut(_clean([w.text for w in words[a:i]]), KICKER_WORDS, from_end=True)
    sub = _cut(_clean([w.text for w in words[j + 1:b + 1]]), SUB_WORDS) or _whole(_clean([w.text for w in nxt]), SUB_WORDS)
    if not kicker and not sub:
        return None                                    # a bare name says nothing the picture does not already say
    if any(re.search(r"\d", t) for t in sub):
        sub = [t for t in sub if not re.search(r"\d", t)]
    return {"metric": None, "head": head, "kicker": _lines(kicker), "sub": " ".join(sub[:SUB_WORDS]).upper()}
