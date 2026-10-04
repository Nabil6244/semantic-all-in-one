"""Find where a phrase is spoken in the narration.

The narration is the usual Whisper word list: (word, start_s, end_s) tuples, the same shape
video_generator.transcribe_audio and scene_graph.voiceover_sync use. A CSV row says
"vo_anchor: elbrus" and the event lands on the word. Matching is forgiving about case,
punctuation, plurals, one-letter slips ("Kalinigrad"), a skipped word, and spoken numbers
("forty seven" matches 47); strict about order: phrases are searched forward from the last match,
so a name that is said twice is found where the script says it, in order.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Word = Tuple[str, float, float]

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SMALL = {w: i for i, w in enumerate(_ONES)}
_SMALL.update(_TENS)
_NUMBER_WORDS = set(_SMALL) | {"hundred", "thousand", "and"}


def norm_token(text: str) -> str:
    t = text.lower().replace("&", " and ")
    t = re.sub(r"(?<=\d)[,](?=\d{3})", "", t)  # 47,000 -> 47000
    t = re.sub(r"[^\w%\u00b0.]+", "", t).strip(".")
    return t


def tokenize(text: str) -> List[str]:
    out: List[str] = []
    for raw in re.split(r"\s+", text.strip()):
        parts = re.split(r"(?<=[A-Za-z])[-\u2013\u2014](?=[A-Za-z])", raw)  # split hyphenated words
        for p in parts:
            tok = norm_token(p)
            if tok:
                out.append(tok)
    return out


def _spoken_number(tokens: Sequence[str], i: int) -> Tuple[Optional[int], int]:
    """A spoken cardinal below a million starting at tokens[i]: ("two", "hundred", "and", "fifty") -> (250, 4),
    ("forty", "seven") -> (47, 2), ("two", "thousand") -> (2000, 2). Returns (None, 0) when there is none.
    "million"/"billion" are left alone: they stay separate words, as scripts write them ("47 million")."""
    total, current, seen, j = 0, 0, False, i
    while j < len(tokens):
        t = tokens[j]
        v = _SMALL.get(t)
        if v is not None:
            if v >= 10:  # a tens word or a teen starts a two-digit group
                if current % 100 != 0:
                    break
            elif current % 10 != 0 or 10 <= current % 100 < 20:  # a unit may follow a tens word ("forty seven"), nothing else
                break
            current += v
            seen = True
            j += 1
        elif t == "hundred" and seen and current < 100:
            current *= 100
            j += 1
        elif t == "thousand" and seen:
            total += current * 1000
            current = 0
            j += 1
        elif t == "and" and seen and j + 1 < len(tokens) and tokens[j + 1] in _SMALL and (current % 100 == 0 or current >= 100 or total):
            j += 1
        else:
            break
    return (total + current, j - i) if seen else (None, 0)


def _merge_numbers(tokens: Sequence[str]) -> List[Tuple[str, int]]:
    """Spoken numbers become digits so "two hundred and fifty" can meet "250". Returns (token, words_used)."""
    out: List[Tuple[str, int]] = []
    i = 0
    while i < len(tokens):
        value, used = _spoken_number(tokens, i)
        if value is not None and used > 0:
            # a year said as two numbers ("nineteen eighty four", "twenty twenty four") is written 1984 / 2024
            if out and out[-1][1] >= 1 and out[-1][0].isdigit() and 10 <= int(out[-1][0]) <= 20 and 10 <= value <= 99 and tokens[i - 1] in _SMALL and used <= 2:
                prev, pused = out.pop()
                out.append((f"{int(prev)}{value:02d}", pused + used)); i += used; continue
            out.append((str(value), used)); i += used; continue
        out.append((tokens[i], 1)); i += 1
    return out


def _stem(t: str) -> str:
    for suf in ("'s", "es", "s"):
        if len(t) > 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def same(a: str, b: str) -> bool:
    if a == b:
        return True
    if _stem(a) == _stem(b):
        return True
    if len(a) >= 5 and len(b) >= 5 and not a.isdigit() and not b.isdigit():
        return difflib.SequenceMatcher(None, a, b).ratio() >= 0.84
    return False


@dataclass
class Match:
    first: int  # index of the first matched word
    last: int  # index of the last matched word
    t_start: float
    t_end: float
    text: str  # the words as spoken
    fuzzy: bool = False  # a spelling variant or a skipped word was needed
    out_of_order: bool = False  # found only before the cursor, i.e. earlier in the narration than expected


class Transcript:
    def __init__(self, words: Sequence[Word]):
        self.words = [(str(w), float(s), float(e)) for w, s, e in words]
        kept = [(i, norm_token(w)) for i, (w, _, _) in enumerate(self.words)]
        kept = [(i, t) for i, t in kept if t]
        self._tokens: List[str] = []
        self._spans: List[Tuple[int, int]] = []  # token -> (first word idx, last word idx)
        pos = 0
        for tok, used in _merge_numbers([t for _, t in kept]):
            self._tokens.append(tok)
            self._spans.append((kept[pos][0], kept[pos + used - 1][0]))
            pos += used

    def __len__(self) -> int:
        return len(self.words)

    @property
    def end(self) -> float:
        return self.words[-1][2] if self.words else 0.0

    def find(self, phrase: str, start_token: int = 0) -> Optional[Tuple[Match, int]]:
        """First occurrence of phrase at or after start_token (else anywhere, flagged out of order).
        Returns (match, next_cursor_token)."""
        want = [t for t, _ in _merge_numbers(tokenize(phrase))]
        if not want or not self._tokens:
            return None
        for begin, ooo in ((start_token, False), (0, True)):
            if ooo and start_token == 0:
                break
            hit = self._search(want, begin, None if not ooo else start_token)
            if hit:
                i0, i1, fuzzy, used = hit
                f, l = self._spans[i0][0], self._spans[i1][1]
                m = Match(f, l, self.words[f][1], self.words[l][2], " ".join(w for w, _, _ in self.words[f:l + 1]), fuzzy, ooo)
                return m, i1 + 1
        return None

    def _joined(self, j: int, want: str) -> int:
        """How many transcript tokens from j, run together, sound like `want` (0 if none). Only for names long enough to be split."""
        if len(want) < 6 or want.isdigit():
            return 0
        for span in (2, 3):
            if j + span <= len(self._tokens):
                joined = "".join(self._tokens[j:j + span])
                # same first letter: otherwise a neighbouring word ("of" + "Marsa" + "Bit") slips into the match
                if not joined.isdigit() and joined[:1] == want[:1] and difflib.SequenceMatcher(None, joined, want).ratio() >= 0.78:
                    return span
        return 0

    def nearest(self, phrase: str) -> Optional[Tuple[str, float]]:
        """The words that sound most like `phrase` (for an error message): (text as spoken, time) or None."""
        want = " ".join(t for t, _ in _merge_numbers(tokenize(phrase)))
        if not want or not self._tokens:
            return None
        size = max(1, len(want.split()))
        best = (0.0, None)
        for i in range(len(self._tokens)):
            for span in {max(1, size - 1), size, size + 1}:
                if i + span > len(self._tokens):
                    continue
                cand = " ".join(self._tokens[i:i + span])
                r = difflib.SequenceMatcher(None, cand, want).ratio()
                if r > best[0]:
                    best = (r, i, span)
        if best[0] < 0.55:
            return None
        _, i, span = best
        f, l = self._spans[i][0], self._spans[i + span - 1][1]
        return " ".join(w for w, _, _ in self.words[f:l + 1]), self.words[f][1]

    def _search(self, want: List[str], begin: int, stop: Optional[int]):
        n = len(self._tokens)
        for i in range(begin, n if stop is None else min(n, stop)):
            j, k, skips, fuzzy = i, 0, 0, False
            while k < len(want) and j < n:
                if self._tokens[j] == want[k]:
                    k += 1; j += 1
                elif same(self._tokens[j], want[k]):
                    fuzzy = True; k += 1; j += 1
                elif k > 0 and skips < 1 and j + 1 < n and same(self._tokens[j + 1], want[k]):
                    skips += 1; fuzzy = True; j += 1  # one extra spoken word inside the phrase
                else:
                    span = self._joined(j, want[k])
                    if not span:
                        break
                    fuzzy = True; k += 1; j += span  # a name heard as two words ("Marsa Beat" for Marsabit)
            if k == len(want):
                return i, j - 1, fuzzy, skips
        return None
