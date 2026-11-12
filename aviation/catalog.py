"""Offline aviation catalog: airlines, aircraft types, airports. Data in aviation/data/*.json (extend by adding entries).

    find_airlines(text) / find_aircraft(text) / find_airports(text) -> [Match] in text order

Same matching contract as the War catalog: word-bounded, case- and diacritic-insensitive; an alias starting with '=' is
case-sensitive (codes such as BA, and names that are also common words: Delta, United, Condor). Airport IATA codes are always
matched case-sensitively. Where matches overlap the longest wins ('737 MAX' beats '737', '787-10' is one 787 match).
A generic aircraft word ('widebody', 'jets') gives a Match with entry None and class_id set. Nothing is guessed by similarity.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class Match:
    entry: Optional[Dict[str, Any]]
    matched: str
    confidence: str            # exact | ambiguous | generic
    start: int = 0
    end: int = 0
    class_id: str = ""


def _norm_char(ch: str) -> str:
    d = unicodedata.normalize("NFKD", ch)
    return "".join(c for c in d if not unicodedata.combining(c)).lower()


def normalise(text: str) -> str:
    return _span_map(text)[0]


def _span_map(text: str) -> Tuple[str, List[int]]:
    """Normalised text (lower, no diacritics, non-alphanumeric runs -> one space) and, per output char, its index in text."""
    out: List[str] = []
    idx: List[int] = []
    gap = True
    for i, ch in enumerate(str(text or "")):
        for c in _norm_char(ch):
            if c.isalnum():
                out.append(c); idx.append(i); gap = False
            elif not gap:
                out.append(" "); idx.append(i); gap = True
    while out and out[-1] == " ":
        out.pop(); idx.pop()
    return "".join(out), idx


def _load(name: str) -> dict:
    try:
        with open(DATA_DIR / name, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=None)
def _data(kind: str) -> Tuple[Tuple[dict, ...], Dict[str, List[str]]]:
    d = _load(f"{kind}.json")
    return tuple(d.get("entries") or ()), dict(d.get("generic") or {})


@lru_cache(maxsize=None)
def _patterns(kind: str) -> Tuple[Tuple[re.Pattern, bool, int], ...]:
    """(compiled pattern, case_sensitive, entry index). Insensitive patterns run on normalised text, sensitive ones on the original."""
    pats = []
    for i, e in enumerate(_data(kind)[0]):
        aliases = list(e.get("aliases") or [])
        if kind == "airports":
            aliases.append("=" + e["id"])
        for a in aliases:
            if a.startswith("="):
                pats.append((re.compile(r"(?<![A-Za-z0-9])" + re.escape(a[1:]) + r"(?![A-Za-z0-9])"), True, i))
            else:
                body = r" ".join(re.escape(p) for p in normalise(a).split())
                if body:
                    pats.append((re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])"), False, i))
    return tuple(pats)


def _find(kind: str, text: str) -> List[Match]:
    text = str(text or "")
    if not text.strip():
        return []
    entries, generic = _data(kind)
    norm, idx = _span_map(text)
    hits: List[Tuple[int, int, Optional[int], str]] = []          # (start, end, entry index or None, class)
    for pat, sensitive, i in _patterns(kind):
        if sensitive:
            for m in pat.finditer(text):
                hits.append((m.start(), m.end(), i, ""))
        else:
            for m in pat.finditer(norm):
                hits.append((idx[m.start()], idx[m.end() - 1] + 1, i, ""))
    for cls, words in generic.items():
        for w in words:
            body = r" ".join(re.escape(p) for p in normalise(w).split())
            for m in re.finditer(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])", norm):
                hits.append((idx[m.start()], idx[m.end() - 1] + 1, None, cls))
    # longest wins; a specific entry beats a generic word of the same span
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0]), h[2] is None))
    kept: List[Tuple[int, int, Optional[int], str]] = []
    for h in hits:
        same_span = [k for k in kept if (k[0], k[1]) == (h[0], h[1])]
        if same_span:
            # a second entry on the very same words -> ambiguous; a generic word never joins a specific one
            if h[2] is not None and all(k[2] is not None and k[2] != h[2] for k in same_span):
                kept.append(h)
            continue
        if any(k[0] < h[1] and h[0] < k[1] for k in kept):
            continue                       # overlaps a longer (or earlier) match
        kept.append(h)
    # several entries owning the same span -> ambiguous
    spans: Dict[Tuple[int, int], int] = {}
    for s, e, i, _ in kept:
        if i is not None:
            spans[(s, e)] = spans.get((s, e), 0) + 1
    out: List[Match] = []
    for s, e, i, cls in sorted(kept, key=lambda h: h[0]):
        if i is None:
            out.append(Match(None, text[s:e], "generic", s, e, cls))
        else:
            ent = entries[i]
            out.append(Match(ent, text[s:e], "exact" if spans[(s, e)] == 1 else "ambiguous", s, e, str(ent.get("body", ""))))
    return out


def find_airlines(text: str) -> List[Match]:
    return _find("airlines", text)


def find_aircraft(text: str) -> List[Match]:
    return _find("aircraft", text)


def find_airports(text: str) -> List[Match]:
    return _find("airports", text)


def _get(kind: str, entry_id: str) -> Optional[dict]:
    for e in _data(kind)[0]:
        if e.get("id") == entry_id:
            return e
    return None


def get_airline(entry_id: str) -> Optional[dict]:
    return _get("airlines", entry_id)


def get_aircraft(entry_id: str) -> Optional[dict]:
    return _get("aircraft", entry_id)


def get_airport(entry_id: str) -> Optional[dict]:
    return _get("airports", entry_id)


def all_airlines() -> List[dict]:
    return list(_data("airlines")[0])


def all_aircraft() -> List[dict]:
    return list(_data("aircraft")[0])


def all_airports() -> List[dict]:
    return list(_data("airports")[0])
