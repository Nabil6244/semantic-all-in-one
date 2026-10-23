"""Sentences of the narration with their words, story labels and script casing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from hybrid.narration import build_sentences
from . import lexicon as LX

Word = Tuple[str, float, float]


def norm(t: str) -> str:
    return re.sub(r"[^\w']+", "", str(t).lower())


@dataclass
class Sent:
    index: int
    start: float
    end: float
    text: str                       # the script's text when aligned, else the words joined
    para_end: bool
    widx: List[int]                 # indices into the word list
    label: str = "explain"
    trigger: str = ""               # the word that decided a label
    is_question: bool = False       # a question can also be the hook; the story report counts both
    explicit: bool = False          # the label came from a cue word or phrase of the narration, not from position
    breaks: set = field(default_factory=set)   # global word indices after which a clause ends (script punctuation, else a pause of at least 0.25 s)


def split_long(widx: List[int], words: Sequence[Word], max_s: float) -> List[List[int]]:
    """Split a run of words at its longest pause near the middle until every part is at most max_s long."""
    if not widx or words[widx[-1]][2] - words[widx[0]][1] <= max_s or len(widx) < 6:
        return [widx]
    a, b = words[widx[0]][1], words[widx[-1]][2]
    lo, hi = a + 0.25 * (b - a), a + 0.75 * (b - a)
    best, gap = None, 0.0
    for k in range(1, len(widx)):
        g = words[widx[k]][1] - words[widx[k - 1]][2]
        mid = words[widx[k]][1]
        if lo <= mid <= hi and g > gap:
            best, gap = k, g
    if best is None:
        for k in range(1, len(widx)):
            g = words[widx[k]][1] - words[widx[k - 1]][2]
            if g > gap:
                best, gap = k, g
    if best is None or gap < 0.25:
        best = len(widx) // 2
    return split_long(widx[:best], words, max_s) + split_long(widx[best:], words, max_s)


def sentences(words: Sequence[Word], script: Optional[str], duration: float, max_beat_s: float) -> List[Sent]:
    sents = build_sentences(words, script, duration)
    out: List[Sent] = []
    claimed = 0
    for s in sents:
        idx = [i for i in range(claimed, len(words)) if s.start - 1e-6 <= (words[i][1] + words[i][2]) / 2 < s.end + 1e-6]   # by midpoint: "island" ends where "that" starts, and "that" belongs to the next sentence
        if not idx:
            continue
        claimed = idx[-1] + 1
        parts = split_long(idx, words, max_beat_s)
        whole = _breaks_for(s.text, idx, words)             # computed on the whole sentence, so a split part keeps the script's punctuation
        for k, part in enumerate(parts):
            sent = Sent(len(out), words[part[0]][1], words[part[-1]][2], s.text if len(parts) == 1 else " ".join(words[i][0] for i in part), s.para_end and k == len(parts) - 1, part)
            sent.breaks = {g for g in whole if g in set(part)}
            out.append(sent)
    return out


def casing(script: Optional[str]) -> Dict[str, str]:
    """norm(token) -> the script's capitalised form, for words that are capitalised somewhere other than at a sentence start."""
    if not script:
        return {}
    out: Dict[str, str] = {}
    for sent in re.split(r"(?<=[.!?])\s+|\n+", script):
        toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", sent)
        for k, t in enumerate(toks):
            if k > 0 and t[0].isupper() and norm(t) not in LX.STOP:
                out.setdefault(norm(t), t)
    # a sentence-start name that never occurs in lower case and that the offline place lookup knows ("Rome") is capitalised too
    lower = {norm(t) for t in re.findall(r"[a-z][a-z'\-]*", script)}
    for sent in re.split(r"(?<=[.!?])\s+|\n+", script):
        toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", sent)
        if toks and toks[0][0].isupper() and norm(toks[0]) not in LX.STOP and norm(toks[0]) not in out and norm(toks[0]) not in lower:
            try:
                from hybrid import geo
                geo.resolve(toks[0])
                out[norm(toks[0])] = toks[0]
            except Exception:
                pass
    sents = [x for x in re.split(r"(?<=[.!?])\s+|\n+", script) if x.strip()]
    lower = {norm(t) for t in re.findall(r"[a-z][a-z'\-]*", script)}
    for sent in sents:
        toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", sent)
        if toks and toks[0][0].isupper() and norm(toks[0]) not in LX.STOP and norm(toks[0]) not in out and norm(toks[0]) not in lower:
            try:
                from hybrid import geo
                geo.resolve(toks[0])
                out[norm(toks[0])] = toks[0]
            except Exception:
                pass
    return out


def _breaks_for(text: str, widx: List[int], words: Sequence[Word]) -> set:
    """Clause ends inside one sentence (global word indices after which a clause ends). With the script's text: after a word followed by , ; : or a dash (script tokens aligned to the
    words with difflib; used when at least 60% of the words align). Always also: after a word followed by a pause of at least 0.25 s."""
    import difflib

    out: set = set()
    wn = [norm(words[g][0]) for g in widx]
    if text and re.search(r"[,;:\u2014\u2013]", text):
        toks, after = [], []
        for m in re.finditer(r"[\w'\u2019]+|[,;:\u2014\u2013]", text):
            t = m.group(0)
            if re.match(r"[\w']", t):
                toks.append(norm(t))
                after.append(False)
            elif toks:
                after[-1] = True
        sm = difflib.SequenceMatcher(None, toks, wn, autojunk=False)
        if sum(b.size for b in sm.get_matching_blocks()) >= 0.6 * max(1, len(wn)):
            for b in sm.get_matching_blocks():
                for k in range(b.size):
                    if after[b.a + k]:
                        out.add(widx[b.b + k])
    for a, b in zip(widx, widx[1:]):
        if words[b][1] - words[a][2] >= 0.25:
            out.add(a)
    return out


def compute_breaks(sents: List[Sent], words: Sequence[Word]) -> None:
    """Kept for callers: the breaks are computed in sentences() on the whole sentence, before a long one is split, so a split part keeps the script's punctuation."""
    for s in sents:
        if not s.breaks:
            s.breaks = _breaks_for("", s.widx, words)


def label_sentences(sents: List[Sent], words: Sequence[Word], script: Optional[str]) -> None:
    """hook / question / twist / conclusion / explain, first match wins (docs/explainer/explainer_director_spec.md section 4)."""
    qends = set()
    if script:
        for t in re.split(r"(?<=[.!?])\s+|\n+", script):
            if t.strip().endswith("?"):
                qends.add(" ".join(norm(w) for w in t.split() if norm(w))[:60])
    last = len(sents) - 1
    for k, s in enumerate(sents):
        toks = [norm(words[i][0]) for i in s.widx]
        joined = " " + " ".join(toks) + " "
        s.label, s.trigger = "explain", ""
        key = " ".join(toks)[:60]
        s.is_question = (key in qends) if script else bool(toks and toks[0] in LX.QUESTION_START)
        if k == 0:
            s.label = "hook"
            continue
        key = " ".join(toks)[:60]
        is_q = (key in qends) if script else bool(toks and toks[0] in LX.QUESTION_START)      # a script says it with '?'; without one a question word starts it
        if is_q:
            s.label, s.trigger, s.explicit = "question", toks[0] if toks else "", True
        else:
            tw = next((t for t in toks if t in LX.TWIST), None)
            if tw and (toks[0] in LX.TWIST or toks.index(tw) <= 3):
                s.label, s.trigger, s.explicit = "twist", tw, True
            else:
                cw = next((t for t in toks if t in LX.CONCLUSION), None) or next((p for p in LX.CONCLUSION_PHRASES if f" {p} " in joined), None)
                if cw is None and toks and toks[0] == "so" and s.start >= 0.75 * words[-1][2]:
                    cw = "so (sentence-initial, last quarter)"
                if cw:
                    s.label, s.trigger, s.explicit = "conclusion", cw, True
                # the last sentence is NOT labelled a conclusion without such a cue: nothing is invented
