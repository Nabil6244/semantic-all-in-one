"""Timed narration for the Hybrid Director: sentences with real start and end times.

Whisper's words carry no punctuation, so when the script text is available it is split into sentences and aligned to the words
(difflib on normalised tokens, so a spoken "forty seven" for a written "47" simply is not matched and is interpolated). With no
script, sentences are inferred from pauses. The Director sees these sentences and chooses beats as RANGES OF SENTENCES: it never
guesses a time."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Optional, Sequence, Tuple

Word = Tuple[str, float, float]


@dataclass
class Sentence:
    index: int
    text: str
    start: float
    end: float
    para_end: bool = False  # the script's paragraph (or heading block) ends with this sentence: the best place to cut a long narration

    @property
    def words(self) -> int:
        return len(self.text.split())

    def to_dict(self) -> dict:
        return {"index": self.index, "text": self.text, "start": round(self.start, 3), "end": round(self.end, 3)}


_SENT_END = re.compile(r"(?<=[.!?…])[\"'”’)\]]*\s+(?=[\"'“‘(\[]?[A-Z0-9])")


def split_script(text: str) -> List[str]:
    """Sentences of the script, in order. A numbered heading line ("35. The Roof of Florida") stays with the sentence that follows it."""
    out: List[str] = []
    for para in re.split(r"\n\s*\n|\r\n\s*\r\n", text.strip()):
        para = " ".join(para.split())
        if not para:
            continue
        parts = [p.strip() for p in _SENT_END.split(para) if p.strip()]
        out.extend(parts)
    return out


def paragraph_ends(text: str) -> List[bool]:
    """For each sentence `split_script(text)` returns: does a paragraph end with it?"""
    flags: List[bool] = []
    for para in re.split(r"\n\s*\n|\r\n\s*\r\n", text.strip()):
        para = " ".join(para.split())
        if not para:
            continue
        n = len([p for p in _SENT_END.split(para) if p.strip()])
        flags.extend([False] * (n - 1) + [True])
    return flags


def _norm(token: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", token.lower())


def _tokens(text: str) -> List[str]:
    return [t for t in (_norm(x) for x in text.split()) if t]


def build_sentences(words: Sequence[Word], script: Optional[str] = None, duration: Optional[float] = None) -> List[Sentence]:
    words = [(str(w[0]), float(w[1]), float(w[2])) for w in words]
    if not words:
        return []
    total = float(duration) if duration else words[-1][2]
    sentences = _from_script(words, script) if script and script.strip() else None
    if not sentences:
        sentences = _from_pauses(words)
    # clean monotonic, non-overlapping times inside the narration
    prev_end = 0.0
    for s in sentences:
        s.start = max(prev_end, min(s.start, total))
        s.end = max(s.start + 0.05, min(s.end, total))
        prev_end = s.end
    return sentences


def _from_script(words: List[Word], script: str) -> Optional[List[Sentence]]:
    texts = split_script(script)
    if not texts:
        return None
    flat: List[str] = []
    owner: List[int] = []
    for i, t in enumerate(texts):
        for tok in _tokens(t):
            flat.append(tok)
            owner.append(i)
    wtok = [_norm(w[0]) for w in words]
    matched: List[List[int]] = [[] for _ in texts]
    for block in SequenceMatcher(None, flat, wtok, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            matched[owner[block.a + k]].append(block.b + k)
    if sum(len(m) for m in matched) < 0.3 * max(1, len(flat)):
        return None  # the script is not what was spoken: do not pretend to align it
    ends = paragraph_ends(script)
    out: List[Sentence] = []
    for i, t in enumerate(texts):
        if matched[i]:
            out.append(Sentence(i, t, words[min(matched[i])][1], words[max(matched[i])][2], para_end=i < len(ends) and ends[i]))
        else:
            out.append(Sentence(i, t, -1.0, -1.0, para_end=i < len(ends) and ends[i]))
    # interpolate sentences with no matched word between their neighbours
    for i, s in enumerate(out):
        if s.start >= 0:
            continue
        lo = next((out[j].end for j in range(i - 1, -1, -1) if out[j].end >= 0), 0.0)
        j2 = next((j for j in range(i + 1, len(out)) if out[j].start >= 0), None)
        hi = out[j2].start if j2 is not None else words[-1][2]
        gap = [k for k in range(i, j2 if j2 is not None else len(out)) if out[k].start < 0]
        w = [max(1, len(out[k].text.split())) for k in gap]
        span, t0 = max(0.1, hi - lo), lo
        for k, wk in zip(gap, w):
            out[k].start, out[k].end = t0, t0 + span * wk / sum(w)
            t0 = out[k].end
    return out


def _from_pauses(words: List[Word]) -> List[Sentence]:
    out: List[Sentence] = []
    cur: List[Word] = []
    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        gap = (nxt[1] - w[2]) if nxt else 99.0
        if nxt is None or (gap >= 0.55 and len(cur) >= 5) or len(cur) >= 32:
            out.append(Sentence(len(out), " ".join(x[0] for x in cur).capitalize() + ".", cur[0][1], cur[-1][2]))
            cur = []
    return out


def words_between(words: Sequence[Word], a: float, b: float) -> List[Word]:
    return [w for w in words if w[1] >= a - 1e-6 and w[2] <= b + 0.3]


# ---- long narrations: chapters ---------------------------------------------------------------------------------------

@dataclass
class Chunk:
    """A run of whole sentences planned in one Director request. `start`/`end` are the narration seconds it owns: chunks tile the
    video exactly (each starts where the previous one ends), so the master timeline has no gap and no overlap by construction."""
    index: int          # 1-based chapter number
    first: int          # first sentence index
    last: int           # last sentence index (inclusive)
    start: float
    end: float


SINGLE_REQUEST_S = 540.0   # a narration up to this long is planned in one request, exactly as before
CHAPTER_TARGET_S = 360.0   # otherwise: chapters of about this many seconds, cut at story boundaries


def plan_chunks(sentences: Sequence[Sentence], total: float, *, target_s: float = CHAPTER_TARGET_S, single_s: float = SINGLE_REQUEST_S) -> List[Chunk]:
    """Split a long narration into chapters at sentence boundaries. Equal-ish lengths, but each cut moves (within +/- a quarter of
    the target) to the best nearby boundary: a paragraph end beats a mid-paragraph sentence end, a longer silence beats a shorter one.
    Never cuts inside a sentence, so a story beat is never split by the planner. A narration of `single_s` or less is one chunk."""
    if not sentences:
        return []
    n = len(sentences)
    if total <= single_s or n < 4:
        return [Chunk(1, 0, n - 1, 0.0, float(total))]
    parts = max(2, int(round(total / target_s)))
    cuts: List[int] = []   # sentence index AFTER which a chunk ends
    lo_i = 0
    for k in range(1, parts):
        ideal = total * k / parts
        window = 0.25 * (total / parts)
        best, best_score = None, -1e9
        for i in range(max(lo_i, 0), n - 1):
            mid = (sentences[i].end + sentences[i + 1].start) / 2
            if mid < ideal - window:
                continue
            if mid > ideal + window:
                break
            gap = max(0.0, sentences[i + 1].start - sentences[i].end)
            score = gap + (1.5 if sentences[i].para_end else 0.0) - abs(mid - ideal) / max(window, 1e-6) * 0.6
            if score > best_score:
                best, best_score = i, score
        if best is None:   # no sentence boundary inside the window (very long sentences): the nearest one to the ideal point
            best = min(range(max(lo_i, 0), n - 1), key=lambda i: abs((sentences[i].end + sentences[i + 1].start) / 2 - ideal), default=None)
        if best is None or (cuts and best <= cuts[-1]):
            continue
        cuts.append(best)
        lo_i = best + 1
    out: List[Chunk] = []
    first, t0 = 0, 0.0
    for c in cuts + [n - 1]:
        t1 = float(total) if c == n - 1 else round((sentences[c].end + sentences[c + 1].start) / 2, 3)
        out.append(Chunk(len(out) + 1, first, c, t0, t1))
        first, t0 = c + 1, t1
    return out
