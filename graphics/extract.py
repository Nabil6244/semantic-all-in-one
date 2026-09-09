"""Deterministic extraction of graphic-worthy facts from narration.

Never fabricates data. Only surfaces numbers / locations / names that appear
in the spoken line — and only when they look editorially meaningful.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Meaningful statistic patterns — not every digit.
_STAT_RE = re.compile(
    r"""
    (?P<prefix>\$|€|£)?
    (?P<number>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+)
    (?P<suffix>\s*(?:%|percent|percentage|bn|billion|million|trillion|k|m|b))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_STAT_CONTEXT = re.compile(
    r"\b("
    r"increase|decrease|grow|growth|rise|fell|fall|drop|jump|surge|"
    r"reach|reached|expected|projected|nearly|almost|over|under|"
    r"more than|less than|up by|down by|by\s+\d|"
    r"demand|cost|revenue|capacity|population|percent|rate|share"
    r")\b",
    re.IGNORECASE,
)

# Weak / non-emphasis numbers (years alone, scene counts, tiny ints without %).
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_ORDINAL_RE = re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.IGNORECASE)

_LOCATION_HINT = re.compile(
    r"\b(?:in|from|across|near|outside|inside|toward|towards|between)\s+"
    r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})",
)
_KNOWN_PLACES = re.compile(
    r"\b("
    r"Texas|California|New York|Florida|Alaska|China|India|Europe|Asia|"
    r"Africa|Australia|Canada|Mexico|Brazil|Japan|Germany|France|UK|"
    r"United States|USA|America|London|Paris|Berlin|Tokyo|Beijing|"
    r"Middle East|Gulf Coast|Silicon Valley|Midwest"
    r")\b"
)

_NAME_RE = re.compile(
    r"\b([A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+){1,2})\b"
    r"(?:\s*,\s*|\s+—\s+|\s+-\s+|\s+)"
    r"([A-Z][a-zA-Z]+(?:\s+[a-zA-Z]+){0,4})"
)

# Proper names mentioned mid-sentence: "Malcolm McLean introduced…"
_PERSON_NAME_RE = re.compile(
    r"\b([A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+){1,2})\b"
)

_NAME_STOPWORDS = frozenset(
    {
        "then", "when", "while", "after", "before", "during", "until", "since",
        "but", "and", "or", "so", "yet", "for", "nor", "the", "this", "that",
        "these", "those", "from", "into", "onto", "over", "under", "across",
        "through", "between", "among", "with", "without", "about", "against",
        "toward", "towards", "within", "along", "around", "near", "inside",
        "outside", "upon", "today", "tomorrow", "yesterday", "here", "there",
        "now", "later", "next", "last", "first", "second", "third", "finally",
        "meanwhile", "however", "therefore", "thus", "hence", "also", "still",
        "even", "just", "only", "very", "more", "most", "some", "any", "all",
        "each", "every", "both", "either", "neither", "united", "states",
        "new", "north", "south", "east", "west", "modern", "shipping",
        "container", "industry", "global", "world", "american", "european",
    }
)

_TITLE_STOP_PREFIX = frozenset(
    {
        "introduced", "invented", "created", "built", "founded", "launched",
        "said", "says", "argued", "wrote", "claimed", "announced", "began",
        "started", "led", "ran", "owned", "designed", "developed", "discovered",
    }
)

_PROCESS_HINT = re.compile(
    r"\b(process|stage|step|then|next|finally|pipeline|supply chain|"
    r"from .+ to|production|transport|grid|factory|construction|"
    r"building|develop(?:ment|ing)?|completion|progress)\b",
    re.IGNORECASE,
)

_PROGRESS_HINT = re.compile(
    r"\b(\d{1,3}\s*%|percent complete|underway|in progress|completed|"
    r"halfway|almost done|nearly finished)\b",
    re.IGNORECASE,
)

_COMPARE_HINT = re.compile(
    r"\b(versus|vs\.?|compared (?:to|with)|before and after|"
    r"old .+ new|instead of|rather than|while .+ only)\b",
    re.IGNORECASE,
)

_CHRONOLOGY_HINT = re.compile(
    r"\b((?:19|20)\d{2}|decade|century|timeline|chronolog|"
    r"over the (?:next|past|last)|by\s+(?:19|20)\d{2})\b",
    re.IGNORECASE,
)


@dataclass
class ExtractedStat:
    raw: str
    value: float
    display: str
    unit: str
    label: str
    meaningful: bool


@dataclass
class ExtractedLocation:
    name: str
    confidence: float


@dataclass
class ExtractedName:
    name: str
    title: str


def extract_statistics(narration: str) -> List[ExtractedStat]:
    text = (narration or "").strip()
    if not text:
        return []
    has_context = bool(_STAT_CONTEXT.search(text))
    out: List[ExtractedStat] = []
    for m in _STAT_RE.finditer(text):
        raw = m.group(0).strip()
        if _YEAR_RE.fullmatch(raw.strip()) and "%" not in raw.lower() and "percent" not in raw.lower():
            # Bare year — only meaningful with chronology intent elsewhere.
            continue
        if _ORDINAL_RE.fullmatch(raw):
            continue
        prefix = m.group("prefix") or ""
        number = (m.group("number") or "").replace(",", "")
        suffix = (m.group("suffix") or "").strip()
        try:
            value = float(number)
        except ValueError:
            continue
        # Skip trivial lone small integers without % / money / context.
        unit = ""
        if prefix:
            unit = prefix
        elif "percent" in suffix.lower() or suffix.strip() == "%":
            unit = "%"
        elif suffix:
            unit = suffix.strip()

        meaningful = False
        if unit in ("%", "$", "€", "£") or "percent" in unit.lower():
            meaningful = True
        elif unit and value >= 1:
            meaningful = True
        elif has_context and (value >= 10 or "." in number):
            meaningful = True
        elif value >= 100 and has_context:
            meaningful = True

        if not meaningful:
            continue

        # Display: prefer +N% style when narration says increase/grow.
        display = raw
        if unit == "%" or "percent" in (suffix or "").lower():
            num_txt = number.rstrip("0").rstrip(".") if "." in number else number
            if re.search(r"\b(increase|grow|rise|up by|surge|jump)\b", text, re.I):
                display = f"+{num_txt}%"
            elif re.search(r"\b(decrease|fall|fell|drop|down by)\b", text, re.I):
                display = f"-{num_txt}%"
            else:
                display = f"{num_txt}%"
        elif prefix:
            display = f"{prefix}{number}"

        label = _stat_label(text, m.start(), m.end())
        out.append(
            ExtractedStat(
                raw=raw,
                value=value,
                display=display,
                unit=unit,
                label=label,
                meaningful=True,
            )
        )
    # Prefer one strongest stat per beat.
    out.sort(key=lambda s: (_stat_score(s), len(s.display)), reverse=True)
    return out[:2]


def extract_locations(narration: str) -> List[ExtractedLocation]:
    text = (narration or "").strip()
    if not text:
        return []
    found: List[ExtractedLocation] = []
    seen = set()
    for m in _KNOWN_PLACES.finditer(text):
        name = m.group(1)
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(ExtractedLocation(name=name, confidence=0.85))
    for m in _LOCATION_HINT.finditer(text):
        name = m.group(1).strip()
        if name.lower() in seen:
            continue
        # Filter common false positives
        if name.lower() in {"the", "this", "that", "these", "those", "our", "their"}:
            continue
        seen.add(name.lower())
        found.append(ExtractedLocation(name=name, confidence=0.55))
    return found[:3]


def extract_name_title(narration: str) -> Optional[ExtractedName]:
    text = (narration or "").strip()
    if not text:
        return None

    # Prefer "Name, Title" / "Name — Title" patterns.
    m = _NAME_RE.search(text)
    if m:
        name, title = m.group(1).strip(), m.group(2).strip()
        name = _clean_person_name(name)
        if name and not _KNOWN_PLACES.search(name):
            title_l = title.split()[0].lower() if title else ""
            if title_l not in _TITLE_STOP_PREFIX:
                return ExtractedName(name=name, title=title[:60])

    # Collect candidate proper-name spans (2–3 capitalized tokens), then clean
    # leading discourse words ("Then Malcolm McLean" → "Malcolm McLean").
    candidates: List[Tuple[str, int, int]] = []
    for m in _PERSON_NAME_RE.finditer(text):
        raw = m.group(1)
        name = _clean_person_name(raw)
        if not name or len(name.split()) < 2:
            # Try expanding: if raw started with a stopword, take following tokens.
            words = raw.split()
            # Also try raw + next capitalized token from the line.
            after = text[m.end() :]
            extra = re.match(r"\s+([A-Z][a-zA-Z'-]+)", after)
            if extra:
                name = _clean_person_name(f"{raw} {extra.group(1)}")
            elif len(words) >= 2:
                name = _clean_person_name(" ".join(words))
        if not name or len(name.split()) < 2:
            continue
        if _KNOWN_PLACES.search(name):
            continue
        # Locate cleaned name in the original text for context after it.
        pos = text.find(name)
        if pos < 0:
            pos = m.start()
        end = pos + len(name)
        candidates.append((name, pos, end))

    if not candidates:
        return None

    # Prefer longer names (Malcolm McLean over Malcolm X-style shorts).
    candidates.sort(key=lambda c: (-len(c[0].split()), c[1]))
    name, _pos, end = candidates[0]
    after = text[end:].strip(" ,.-–—:")
    title = _supporting_title(after)
    return ExtractedName(name=name, title=title)


def _clean_person_name(raw: str) -> str:
    words = (raw or "").split()
    while words and words[0].lower().strip(".,") in _NAME_STOPWORDS:
        words.pop(0)
    while words and words[-1].lower().strip(".,") in _NAME_STOPWORDS:
        words.pop()
    if len(words) < 2:
        return ""
    # Require all tokens look like name parts (capitalized, not stopwords).
    cleaned: List[str] = []
    for w in words:
        core = w.strip(".,'\"")
        if not core or core.lower() in _NAME_STOPWORDS:
            break
        if not core[0].isupper():
            break
        cleaned.append(core)
    if len(cleaned) < 2:
        return ""
    return " ".join(cleaned[:3])


def _supporting_title(after: str) -> str:
    """Short context under a name — never a full narration dump."""
    after = (after or "").strip()
    if not after:
        return ""
    # Drop leading verbs like "introduced the…"
    words = after.split()
    if words and words[0].lower().strip(".,") in _TITLE_STOP_PREFIX:
        # Use a noun phrase after the verb if short enough.
        rest = " ".join(words[1:6]).strip(" .,;:")
        rest = re.sub(r"^(the|a|an)\s+", "", rest, flags=re.I)
        if 3 <= len(rest) <= 36:
            return rest[:36].title() if rest.islower() else rest[:36]
        return ""
    phrase = " ".join(words[:5]).strip(" .,;:")
    if len(phrase) > 36:
        phrase = phrase[:33].rstrip() + "…"
    return phrase if len(phrase) >= 3 else ""


def narration_signals(narration: str) -> dict:
    text = narration or ""
    return {
        "has_statistic": bool(extract_statistics(text)),
        "has_location": bool(extract_locations(text)),
        "has_name": extract_name_title(text) is not None,
        "has_process": bool(_PROCESS_HINT.search(text)),
        "has_progress": bool(_PROGRESS_HINT.search(text)),
        "has_comparison": bool(_COMPARE_HINT.search(text)),
        "has_chronology": bool(_CHRONOLOGY_HINT.search(text)),
        "word_count": len(text.split()),
    }


def _stat_label(text: str, start: int, end: int) -> str:
    """Grab a short supporting label near the number."""
    window = text[max(0, start - 40) : min(len(text), end + 50)]
    # Prefer noun phrases before the number.
    before = text[max(0, start - 48) : start].strip(" ,.-–—:")
    words = before.split()
    if len(words) >= 2:
        candidate = " ".join(words[-4:])
        candidate = re.sub(r"^(by|to|of|at|in|a|an|the)\s+", "", candidate, flags=re.I)
        if 3 <= len(candidate) <= 42:
            return candidate.title() if candidate.islower() else candidate
    # Fallback: strip the number from a short clause.
    clause = re.split(r"[.!?]", window)[0].strip()
    clause = _STAT_RE.sub("", clause).strip(" ,.-")
    if 3 <= len(clause) <= 42:
        return clause[:42]
    return ""


def _stat_score(stat: ExtractedStat) -> float:
    score = 1.0
    if stat.unit == "%":
        score += 2.0
    if stat.unit in ("$", "€", "£"):
        score += 1.5
    if abs(stat.value) >= 10:
        score += 0.5
    if stat.label:
        score += 0.4
    return score
