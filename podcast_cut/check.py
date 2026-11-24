"""Clip-plan checker: run before anything is rendered. Errors stop the run; warnings are shown.

Errors:   end before start, outside the episode, body clips out of order or overlapping, more than one hook,
          hook not first, nothing to play.
Warnings: total far from the target, a clip shorter than 3 s, a cut that lands inside a word, a kept clip that
          reads like an ad / plug, a hook outside 8-35 s, a question left without its answer.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .picker import Clip, PRESENTS_CARD, Word, junk_reason


def total_length(clips: Sequence[Clip]) -> float:
    hook = [c for c in clips if c.role == "hook"]
    return sum(c.length for c in clips) + (PRESENTS_CARD if hook else 0.0)


def _inside_word(t: float, words: Sequence[Word]) -> Optional[Word]:
    lo, hi = 0, len(words)
    while lo < hi:            # last word starting at or before t
        mid = (lo + hi) // 2
        if words[mid][1] <= t:
            lo = mid + 1
        else:
            hi = mid
    k = lo - 1
    if 0 <= k < len(words):
        w = words[k]
        if w[1] + 0.06 < t < w[2] - 0.06:
            return w
    return None


def check(clips: Sequence[Clip], duration: float = 0.0, target_min: float = 0.0,
          words: Sequence[Word] = ()) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warns: List[str] = []
    if not clips:
        return ["The plan has no clips."], []
    hooks = [k for k, c in enumerate(clips) if c.role == "hook"]
    if len(hooks) > 1:
        errors.append(f"{len(hooks)} hook rows; keep one.")
    if hooks and hooks[0] != 0:
        errors.append("The hook must be the first row.")
    body = [(k, c) for k, c in enumerate(clips) if c.role != "hook"]
    if not body:
        errors.append("The plan has a hook but no body clips.")
    for k, c in enumerate(clips, 1):
        if c.end <= c.start:
            errors.append(f"row {k}: end {c.end:.2f} is not after start {c.start:.2f}.")
        if duration and c.end > duration + 0.5:
            errors.append(f"row {k}: ends at {c.end:.0f} s but the episode is {duration:.0f} s long.")
        if 0 < c.length < 3.0 and c.role != "question":
            warns.append(f"row {k}: only {c.length:.1f} s long.")
        why = junk_reason(c.text)
        if why:
            warns.append(f"row {k}: reads like {why}: \"{c.text[:70]}…\"")
        if words:
            for edge, t in (("starts", c.start), ("ends", c.end)):
                w = _inside_word(t, words)
                if w:
                    warns.append(f"row {k}: {edge} inside the word \"{w[0]}\" ({w[1]:.2f}-{w[2]:.2f} s).")
    for (ka, a), (kb, b) in zip(body, body[1:]):
        if b.start < a.start:
            errors.append(f"rows {ka + 1}-{kb + 1}: body clips must stay in the order they were said.")
        elif b.start < a.end - 0.05:
            errors.append(f"rows {ka + 1}-{kb + 1}: clips overlap ({b.start:.2f} < {a.end:.2f}).")
    for (ka, a), nxt in zip(body, body[1:] + [(None, None)]):
        if a.role == "question" and (nxt[1] is None or nxt[1].start - a.end > 2.0):
            warns.append(f"row {ka + 1}: a question with no answer right after it.")
    if hooks:
        h = clips[hooks[0]]
        if not 8.0 <= h.length <= 35.0:
            warns.append(f"The hook is {h.length:.0f} s; 12-28 s works best.")
    if target_min:
        tot = total_length(clips)
        if abs(tot - target_min * 60) > 90:
            warns.append(f"The cut is {tot / 60:.1f} min; the target was {target_min:g} min.")
    return errors, warns
