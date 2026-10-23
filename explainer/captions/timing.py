"""Caption timing: when does each word of a key phrase appear? The four-rung ladder of docs/explainer/explainer_cue_schema_v1_2.md.

resolve_caption() takes the phrase, the narration words of the anchor's sentence (inside the beat) and returns the reveal time of every displayed word, the rung used
and everything needed to reproduce the decision. It imports nothing from the application and nothing from explainer.board (the board package imports this)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

Word = Tuple[str, float, float]
MAX_WORDS, POLICY_WORDS = 12, 8
MAX_SKIP = 6                     # a match must lie within this many narration words after the previous match (or the anchor)
MAX_CLAMPS = 2
RUNG_NAMES = {1: "all_matched", 2: "partial", 3: "anchor_only", 4: "unresolvable"}


def norm(token: str) -> str:
    return re.sub(r"[^\w']+", "", token.lower())


@dataclass
class CaptionTiming:
    rung: int = 4
    mode: str = "words"
    display_words: List[str] = field(default_factory=list)
    reveal_times: List[float] = field(default_factory=list)       # narration seconds, one per display word, before offset_s
    matched: List[Dict[str, Any]] = field(default_factory=list)
    spread: List[Dict[str, Any]] = field(default_factory=list)
    clamped: int = 0
    stacked: int = 0
    over_policy: bool = False
    notes: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    window: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"rung": self.rung, "rung_name": RUNG_NAMES[self.rung], "mode": self.mode, "phrase_words": self.display_words, "matched": self.matched,
                "reveal_times_abs": [round(t, 4) for t in self.reveal_times], "spread": self.spread, "clamped": self.clamped, "stacked": self.stacked,
                "over_policy": self.over_policy, "window": self.window, "notes": self.notes}


def resolve_caption(cue_id: str, text: str, mode: str, anchor_time: float, words: Sequence[Word], window_idx: Sequence[int], anchor_pos: Optional[int],
                    sentence_end: Optional[float], beat_end: float, clip_end_abs: float, fps: int) -> CaptionTiming:
    """words: all narration words; window_idx: indices (into words) of the anchor's sentence from the anchor word, inside the beat; anchor_pos: 0 when the anchor is a
    word (window_idx[0] is the anchor word), None for a time anchor. sentence_end None = use the beat end. clip_end_abs: where the clip ends in narration seconds."""
    out = CaptionTiming(mode=mode)
    out.display_words = [w for w in str(text).split() if w.strip()]
    toks = [norm(w) for w in out.display_words]
    out.over_policy = len([t for t in toks if t]) > POLICY_WORDS
    out.window = {"anchor_time": round(anchor_time, 4), "window_words": len(window_idx), "sentence_end": None if sentence_end is None else round(sentence_end, 4),
                  "beat_end": round(beat_end, 4), "clip_end_abs": round(clip_end_abs, 4), "fps": fps}
    if not out.display_words or not any(toks):
        out.problems.append(f"cue {cue_id}: the caption has no visible text")
        return out
    if len(out.display_words) > MAX_WORDS:
        out.problems.append(f"cue {cue_id}: a caption is a key phrase of at most {MAX_WORDS} words (this has {len(out.display_words)})")
        return out
    end_s = min(sentence_end if sentence_end is not None else beat_end, beat_end)
    last_ok = clip_end_abs - 1.0 / fps                       # no reveal at or after the clip's end
    n = len(out.display_words)
    if mode == "typed":
        out.rung = 3
        out.reveal_times = [anchor_time] * n
        out.notes.append("mode typed was requested: the whole phrase is typed from the anchor (not a fallback)")
        return out
    # ---- match, leftmost within MAX_SKIP words after the previous match ----
    match_of: Dict[int, int] = {}                             # display word index -> position in window_idx
    prev_pos = -1
    prev_t = anchor_time
    clamped = 0
    for k, tk in enumerate(toks):
        if not tk:
            continue
        found = None
        for p in range(prev_pos + 1, min(len(window_idx), prev_pos + MAX_SKIP + 1)):
            if norm(words[window_idx[p]][0]) == tk:
                found = p
                break
        if found is None:
            continue
        t = float(words[window_idx[found]][1])
        if t < prev_t - 1e-9:
            clamped += 1
            t = prev_t
        match_of[k] = found
        prev_pos, prev_t = found, t
    out.clamped = clamped
    if clamped > MAX_CLAMPS:
        out.notes.append(f"{clamped} out-of-order word times: the matches are not trusted and are discarded")
        match_of = {}
    matchable = [k for k, tk in enumerate(toks) if tk]
    if not match_of:
        out.rung = 3
        out.reveal_times = [anchor_time] * n
        out.notes.append("no phrase word was found in the anchor's sentence: typed from the anchor (rung 3)")
        return out
    # reveal times of matched words (monotone)
    times: Dict[int, float] = {}
    last = anchor_time
    for k in sorted(match_of):
        t = max(float(words[window_idx[match_of[k]]][1]), last, anchor_time)
        times[k] = t
        last = t
        w = words[window_idx[match_of[k]]]
        out.matched.append({"phrase_word": out.display_words[k], "narration_word": w[0], "narration_index": window_idx[match_of[k]], "start": round(float(w[1]), 4), "end": round(float(w[2]), 4)})
    out.rung = 1 if all(k in match_of for k in matchable) else 2
    # unmatched matchable words: spread inside the interval between the neighbouring matched words (or anchor / sentence end)
    ordered = sorted(match_of)
    k = 0
    while k < n:
        if k in times or not toks[k]:
            k += 1
            continue
        j = k
        while j < n and (j not in times) and True:
            j += 1
        run = [x for x in range(k, j) if toks[x]]
        prev_k = max([x for x in ordered if x < k] or [-1])
        next_k = min([x for x in ordered if x > k] or [10 ** 6])
        a = times[prev_k] if prev_k >= 0 else anchor_time
        b = times[next_k] if next_k < 10 ** 6 else end_s
        b = min(b, last_ok)
        m = len(run)
        if b - a < (m + 1) / fps or b <= a:
            for x in run:
                times[x] = a
            out.stacked += m
            out.spread.append({"words": [out.display_words[x] for x in run], "from": round(a, 4), "to": round(b, 4), "stacked": True})
        else:
            for i, x in enumerate(run, 1):
                times[x] = a + (b - a) * i / (m + 1)
            out.spread.append({"words": [out.display_words[x] for x in run], "from": round(a, 4), "to": round(b, 4), "stacked": False})
        k = j
    # display-only words (dashes) share the time of the previous word, or of the next one when first
    for k in range(n):
        if k not in times:
            prev_k = max([x for x in times if x < k] or [-1])
            nxt = min([x for x in times if x > k] or [-1])
            times[k] = times[prev_k] if prev_k >= 0 else times[nxt]
    t_list = [times[k] for k in range(n)]
    for k in range(1, n):                                         # monotone
        t_list[k] = max(t_list[k], t_list[k - 1])
    out.reveal_times = t_list
    if any(t > last_ok + 1e-9 for t in t_list):
        out.problems.append(f"cue {cue_id}: a caption word would be revealed at or after the clip's end")
        out.rung = 4
    return out
