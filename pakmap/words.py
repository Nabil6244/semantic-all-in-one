"""Narration words: load a transcript, or estimate one from text when there is no audio yet."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Sequence, Tuple

Word = Tuple[str, float, float]


def load_words(path: "str | Path") -> List[Word]:
    """Read a word list from JSON. Accepted shapes: [[word, start, end], ...], [{"word":..,"start":..,"end":..}, ...],
    {"words": [...]}, or Whisper-style {"segments": [{"words": [...]}]}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if "words" in data:
            data = data["words"]
        elif "segments" in data:
            data = [w for seg in data["segments"] for w in seg.get("words", [])]
        else:
            raise ValueError("word file: expected a list, or an object with 'words' or 'segments'")
    out: List[Word] = []
    for i, w in enumerate(data):
        try:
            if isinstance(w, dict):
                out.append((str(w.get("word", w.get("text", ""))).strip(), float(w["start"]), float(w["end"])))
            else:
                out.append((str(w[0]).strip(), float(w[1]), float(w[2])))
        except (KeyError, IndexError, TypeError, ValueError):
            raise ValueError(f"word file: entry {i + 1} is not a (word, start, end) triple")
    if not out:
        raise ValueError("word file has no words")
    for a, b in zip(out, out[1:]):
        if b[1] < a[1] - 1e-6:
            raise ValueError(f"word file: {b[0]!r} starts at {b[1]:.2f}s before the previous word {a[0]!r} ({a[1]:.2f}s); words must be in order")
    return out


def estimate_words(text: str, *, words_per_second: float = 2.6, start: float = 0.4) -> List[Word]:
    """A stand-in for a real transcript: word lengths set the pace, sentence ends get a short pause.
    Good for laying out a script before the voiceover exists; replace with real timestamps for the final render."""
    tokens = re.findall(r"\S+", text)
    base = 1.0 / words_per_second
    t, out = start, []
    for tok in tokens:
        letters = len(re.sub(r"\W", "", tok)) or 1
        dur = max(0.14, base * (0.55 + 0.09 * letters))
        out.append((tok, round(t, 3), round(t + dur, 3)))
        t += dur + 0.03
        if re.search(r"[.!?]$", tok):
            t += 0.35
        elif re.search(r"[,;:]$", tok):
            t += 0.15
    return out


def save_words(words: Sequence[Word], path: "str | Path") -> None:
    Path(path).write_text(json.dumps([[w, s, e] for w, s, e in words], indent=1), encoding="utf-8")
