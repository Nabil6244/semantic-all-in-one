"""Big yellow keyword text — the reference style's "345 FT ABOVE SEA LEVEL",
"BILLION DOLLAR AIRFORCE BASE", "THE LOOMIS BROTHERS": short capitals that pop
in when the narrator says a number with a measure, a big money figure, or a
name.

Deliberately sparse: at most one per scene and one every ~7 s, never on top of
a countdown tag/hook, and never for a bare year ("in 1931") — those are
everywhere and would turn into noise. A callout replaces the plain
statistic/name panel the graphics director may have put at the same moment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

MIN_GAP_S = 7.0
CALLOUT_SECONDS = 2.2
MAX_WORDS = 5

_NUM_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
              "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
              "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}
_UNITS = {
    "feet": "FT", "foot": "FT", "ft": "FT", "miles": "MILES", "mile": "MILE", "meters": "METERS",
    "metres": "METERS", "kilometers": "KM", "kilometres": "KM", "km": "KM", "acres": "ACRES", "acre": "ACRE",
    "percent": "%", "degrees": "DEGREES", "tons": "TONS", "pounds": "POUNDS", "people": "PEOPLE",
    "years": "YEARS", "species": "SPECIES", "islands": "ISLANDS", "square miles": "SQUARE MILES",
    "gallons": "GALLONS", "workers": "WORKERS", "soldiers": "SOLDIERS",
}
_TAILS = ("above sea level", "below sea level", "tall", "deep", "long", "wide", "high", "old", "underground")
_WORDNUM_TOKEN = "|".join(sorted(list(_NUM_WORDS) + list(_SCALES) + ["and", "a"], key=len, reverse=True))
_SPELLED = re.compile(rf"\b(?:(?:{_WORDNUM_TOKEN})[\s-]+)*(?:{'|'.join(_NUM_WORDS)})(?:[\s-]+(?:{_WORDNUM_TOKEN}))*\b",
                      re.IGNORECASE)
_DIGITS = re.compile(r"\$?\b\d[\d,]*(?:\.\d+)?\b")
_MONEY = re.compile(r"\b((?:multi-|\d[\d,.]*\s*)?(?:million|billion|trillion)[- ]dollars?)\s+((?:[A-Za-z]+\s+){0,2}[A-Za-z]+)",
                    re.IGNORECASE)
_STOP = {"in", "of", "that", "which", "to", "and", "was", "is", "were", "are", "the", "a", "an", "for", "on", "at",
         "by", "with", "from", "it", "had", "has"}


@dataclass
class Callout:
    text: str
    position: int  # character offset in the narration where it's said


def spelled_to_number(text: str) -> Optional[int]:
    total, current, seen = 0, 0, False
    for word in re.split(r"[\s-]+", (text or "").lower()):
        if word in ("and", "a", ""):
            if word == "a" and not seen:
                current = 1
            continue
        if word in _NUM_WORDS:
            current += _NUM_WORDS[word]
            seen = True
        elif word in _SCALES:
            scale = _SCALES[word]
            current = max(current, 1) * scale
            if scale >= 1000:
                total, current = total + current, 0
            seen = True
        else:
            return None
    return total + current if seen else None


def _format_number(value: float) -> str:
    return f"{int(value):,}" if float(value).is_integer() else f"{value:,}"


def _measure_after(text: str, end: int) -> Tuple[str, int]:
    """(" FT ABOVE SEA LEVEL", end position) for the unit/tail right after a number."""
    rest = text[end:]
    unit_match = re.match(r"\s*(square miles|[A-Za-z%]+)", rest)
    if not unit_match:
        return "", end
    unit = unit_match.group(1).lower()
    if unit == "%":
        label, consumed = "%", unit_match.end()
    elif unit in _UNITS:
        mapped = _UNITS[unit]
        label, consumed = (mapped if mapped == "%" else " " + mapped), unit_match.end()
    else:
        return "", end
    tail_rest = rest[consumed:].lower()
    for tail in _TAILS:
        m = re.match(rf"\s+{tail}\b", tail_rest)
        if m:
            label += " " + tail.upper()
            consumed += m.end()
            break
    return label, end + consumed


def find_callouts(text: str) -> List[Callout]:
    """Candidates in priority order: measured numbers, money, names."""
    text = text or ""
    found: List[Callout] = []
    numbers: List[Callout] = []
    for m in list(_DIGITS.finditer(text)) + list(_SPELLED.finditer(text)):
        raw = m.group(0)
        if raw.startswith("$"):
            continue  # money is handled below with its noun
        value = spelled_to_number(raw) if not raw[0].isdigit() else float(raw.replace(",", ""))
        if value is None:
            continue
        measure, _ = _measure_after(text, m.end())
        if not measure:
            continue  # a bare number (or year) is not a callout
        numbers.append(Callout(text=f"{_format_number(value)}{measure}".strip(), position=m.start()))
    found.extend(sorted(numbers, key=lambda c: c.position))
    for m in _MONEY.finditer(text):
        noun = []
        for word in m.group(2).split():
            if word.lower() in _STOP:
                break
            noun.append(word)
        figure = re.sub(r"[- ]", " ", m.group(1)).replace("dollars", "dollar")
        figure = re.sub(r"^(\d[\d,.]*)\s*", r"$\1 ", figure).strip()
        found.append(Callout(text=" ".join([figure] + noun).upper(), position=m.start()))
    try:
        from scene_graph.generator import _proper_noun_phrases

        names = _proper_noun_phrases(text)
    except Exception:
        names = []
    for name in names:
        if len(name.split()) < 2 or len(name.split()) > MAX_WORDS:
            continue
        pos = text.find(name)
        if pos < 0:
            continue
        label = f"The {name}" if text[max(0, pos - 4):pos] == "The " and name.lower().endswith(("brothers", "sisters", "family")) else name
        found.append(Callout(text=label.upper(), position=pos))
    return [c for c in found if len(c.text.split()) <= MAX_WORDS + 3]


def callout_graphics(scenes: Sequence, narrations: Sequence[str], *, blocked: Sequence[Tuple[float, float]] = ()) -> list:
    """GraphicSpecs for the callouts, timed on the editorial scenes."""
    from graphics.schema import GraphicLifecycle, GraphicSpec, TextOverlaySpec

    specs = []
    last_at: Optional[float] = None
    for index, (scene, narration) in enumerate(zip(scenes, narrations)):
        text = str(narration or "")
        start, end = float(scene.start), float(scene.end)
        words = max(1, len(text.split()))
        for callout in find_callouts(text)[:3]:
            t0 = round(start + (end - start) * min(0.9, len(text[: callout.position].split()) / words), 4)
            t1 = t0 + CALLOUT_SECONDS
            if last_at is not None and t0 - last_at < MIN_GAP_S:
                break
            if any(t0 < b1 and t1 > b0 for b0, b1 in blocked):
                continue
            specs.append(GraphicSpec(
                graphic_id=f"callout_{scene.scene_number}", decision="TEXT", role="EMPHASIS",
                scene_number=str(scene.scene_number), start=t0, end=round(t1, 4), track="GRAPHICS",
                reason="keyword callout", importance="high", emphasis="strong", semantic_purpose="emphasize",
                text=TextOverlaySpec(role="EMPHASIS", text=callout.text, start=t0, end=t1, animation="POP",
                                     metadata={"template": "keyword_callout"}),
                payload={"template": "keyword_callout"}, animation="POP", z_index=76,
                lifecycle=GraphicLifecycle(enter_s=0.2, hold_s=CALLOUT_SECONDS - 0.35, exit_s=0.15),
            ))
            last_at = t0
            break
    return specs
