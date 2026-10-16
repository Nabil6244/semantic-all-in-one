"""The narrator's words -> seconds for a beat CSV's vo_anchor cells, shared by StarMap and Hybrid.

Whisper sometimes drops or mishears a few words ("that disturbance traveled outward" heard as just "that"). The old search then
fell back to part of the phrase anywhere later in the narration, found the same two words minutes on, and every beat after it
failed as "only spoken before the previous beat's words". Here a beat's words are only trusted near where the script puts them
(the previous beat's text, counted in words), a beat that cannot be heard there is placed by that count with a note, and
`keep_in_order` moves any word-timed beat that still lands out of order between its neighbours. A beat anchor never stops a plan.
"""

from __future__ import annotations

import difflib
import re
from typing import Callable, Dict, List, Optional, Sequence

DEFAULT_WORDS = 40          # a beat with no text: about this many words are assumed spoken before the next one
SLACK = 60                  # extra words a partly heard phrase may be found past its expected place
MIN_GAP = 0.5               # seconds between two beats moved back into order


class AnchorClock:
    """Beat rows (advance=True) move the search on; a beat's own rows are searched from the beat's first words and never move it.
    normalize puts the transcript and the CSV's words in one spelling (StarMap's number forms); unit = "beat" or "row" in messages."""

    def __init__(self, words: Sequence, notes: List[str], normalize: Callable[[str], str] = lambda s: s, unit: str = "beat"):
        from pakmap.anchor import Transcript     # the shared word matcher (read-only)

        self.norm, self.unit, self.notes = normalize, unit, notes
        self.tr = Transcript([(normalize(str(w)), s, e) for w, s, e in words]) if words else None
        self.cursor = 0             # token where the last heard beat starts
        self.skipped = 0            # words counted past the cursor for beats placed by estimate
        self.estimated = False      # the last beat was placed by estimate

    def _count(self, text: str) -> int:
        from pakmap.anchor import tokenize

        return len(tokenize(self.norm(text or "")))

    def _first(self, m) -> int:
        from pakmap.compile import hit_first

        return hit_first(self.tr, m)

    def _near(self, hit, reach: int) -> bool:
        return hit is not None and not hit[0].out_of_order and self._first(hit[0]) - self.cursor <= reach

    def _find(self, words: str, reach: int):
        exact = self.tr.find(words, self.cursor)
        if self._near(exact, reach * 3 + 200):                    # every word heard: a much wider reach
            return exact
        split = re.sub(r"(?<=\d)\.(?=\d)", " ", words)             # Whisper writes 1.3 as "1 3"
        if split != words and self._near(hit := self.tr.find(split, self.cursor), reach * 3 + 200):
            return hit
        near = self.tr.nearest(words) if len(words.split()) == 1 else None      # slow: only a one-word name uses it
        # one word only (a name): a longer phrase must be spoken as written, or a wrong place could be matched silently
        if (near and len(words.split()) == 1 and len(near[0].split()) == 1 and words[:1].lower() == near[0][:1].lower()
                and difflib.SequenceMatcher(None, words.lower(), near[0].lower()).ratio() >= 0.72):
            if self._near(hit := self.tr.find(near[0], self.cursor), reach):
                self.notes.append(f"vo_anchor {words!r} was matched to {near[0]!r} at {near[1]:.1f}s (how the narration spells it)")
                return hit
        parts = words.split()
        for size in range(len(parts) - 1, 1, -1):                  # one wrong word: the same start, or end, with fewer words
            for label, sub in (("start", parts[:size]), ("end", parts[-size:])):
                if self._near(hit := self.tr.find(" ".join(sub), self.cursor), reach):
                    self.notes.append(f"vo_anchor {words!r}: not spoken exactly; its {label} words {' '.join(sub)!r} were found at {hit[0].t_start:.1f}s")
                    return hit
        return exact if exact is not None and exact[0].out_of_order else None

    def _estimate(self, words: str, before_words: int) -> float:
        self.skipped += before_words
        i = min(self.cursor + self.skipped, len(self.tr._spans) - 1)
        self.estimated = True
        t = self.tr.words[self.tr._spans[i][0]][1]
        self.notes.append(f"vo_anchor {words!r} is not heard near where the script puts it (Whisper may have skipped or misheard those "
                          f"words): the {self.unit} starts at about {t:.1f}s, counted from the text before it")
        return round(t, 3)

    def at(self, phrase: str, *, advance: bool, before: str = "") -> float:
        """Seconds for phrase. before = the text spoken just before it (the previous beat's, or this beat's for its rows).
        A beat (advance=True) always gets a time; another row raises ValueError when its words are not heard in its beat."""
        if self.tr is None or not len(self.tr):
            raise ValueError("vo_anchor needs the narration: choose the voiceover first (or give start / t in seconds)")
        words, _, mod = phrase.partition("|")
        words = self.norm(words.strip())
        n = self._count(before) or DEFAULT_WORDS
        reach = 2 * (n + self.skipped) + SLACK if advance else 2 * n + SLACK
        if advance:
            self.estimated = False
        hit = self._find(words, reach)
        if hit is None or hit[0].out_of_order:
            if advance:
                return self._estimate(words, n)
            if hit is None:
                near = self.tr.nearest(words)
                raise ValueError(f"vo_anchor {words!r} is not in the narration" + (f" (closest: {near[0]!r} at {near[1]:.1f}s)" if near else ""))
            raise ValueError(f"vo_anchor {words!r} is only spoken before the previous {self.unit}'s words ({hit[0].t_start:.1f}s)")
        m = hit[0]
        if advance:
            self.cursor, self.skipped = self._first(m), 0
        return round(m.t_end if mod.strip().lower() == "end" else m.t_start, 3)


def keep_in_order(starts: List[float], movable: Dict[int, bool], end: Optional[float], notes: List[str], names: Sequence[str]) -> List[float]:
    """Beat starts, each after the one before. movable: index -> True when placed by estimate (trusted least), False when heard;
    beats not in it (the first, or a start in seconds) never move. A movable beat out of order is spread evenly between the
    beats around it."""
    out, n = list(starts), len(starts)
    good = [movable.get(i) is not True for i in range(n)]
    # heard and fixed beats: keep the largest set already in order (one beat heard far ahead must not condemn every beat after it)
    idx = [i for i in range(n) if good[i]]
    weight = {i: (10 ** 6 if (i == 0 or i not in movable) else 1) for i in idx}     # fixed starts are always kept
    best: Dict[int, float] = {}
    prev: Dict[int, Optional[int]] = {}
    for a_, i in enumerate(idx):
        best[i], prev[i] = weight[i], None
        for j in idx[:a_]:
            if out[j] < out[i] - 1e-6 and best[j] + weight[i] > best[i]:
                best[i], prev[i] = best[j] + weight[i], j
    keep, k = set(), (max(idx, key=lambda i: best[i]) if idx else None)
    while k is not None:
        keep.add(k)
        k = prev[k]
    for i in idx:
        good[i] = i in keep
    last = None
    for i in range(n):                                  # an estimate must fit between the good beats around it
        if movable.get(i) is True:
            nxt = next((out[j] for j in range(i + 1, n) if good[j] and movable.get(j) is not True), None)
            if (last is not None and out[i] <= last + 1e-6) or (nxt is not None and out[i] >= nxt - 1e-6):
                good[i] = False
                continue
        if good[i]:
            last = out[i]
    i = 1
    while i < n:
        if good[i]:
            i += 1
            continue
        j = i
        while j < n and not good[j]:
            j += 1
        lo = out[i - 1]
        hi = out[j] if j < n else (end if end is not None and end > lo + MIN_GAP else lo + MIN_GAP * (j - i + 1))
        step = (hi - lo) / (j - i + 1)
        for k in range(i, j):
            out[k] = round(lo + step * (k - i + 1), 3)
            notes.append(f"{names[k]}: its words are heard out of order in the narration, so it starts at {out[k]:.1f}s, between the beats around it")
        i = j
    return out
