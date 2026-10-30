"""Numbers and items as the narration says them, and when it says them. Used by the planner for list / compare cards and for graphics over footage.

    spoken_number(text) -> {"number", "unit", "word"} | None    "seventy times a minute" -> 70, "times a minute"; "twenty to thirty minutes" -> "20-30", "minutes"
    times_for(items, sentences, start, dur) -> [{"text", "t0"}]  each item appears when its first meaningful word is spoken (else evenly spaced)

Nothing is invented: a number is only ever one the sentence says, digits or words. "one" alone ("one ordinary morning") and ordinals ("second") are not numbers."""
from __future__ import annotations
import re
from typing import Dict, List, Optional

ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
        "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALE = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
STOP = {"and", "of", "the", "that", "which", "who", "is", "are", "was", "it", "in", "on", "for", "with", "or", "but", "so", "you", "your", "we", "they", "can", "will",
        "even", "every", "if", "when", "because", "as", "at", "by", "from", "this", "these", "those"}
_W = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*|\d[\d,.]*\d%?|\d%?|[,.;:!?]")


def _words(text: str) -> List[str]:
    return _W.findall(text)


def _value(tokens: List[str], i: int):
    """A number starting at tokens[i] -> (value, next index) or None. Digits, or words like 'one hundred thousand', 'twenty five', 'five-minute'."""
    t = tokens[i].lower()
    if t[0].isdigit():
        try:
            return float(t.rstrip("%").replace(",", "")), i + 1
        except ValueError:
            return None
    head = t.split("-")[0]
    if head not in ONES and head not in TENS:
        return None
    total, cur, j = 0, 0, i
    while j < len(tokens):
        w = tokens[j].lower(); parts = w.split("-")
        if parts[0] in TENS and j == i or (parts[0] in TENS and cur == 0):
            cur += TENS[parts[0]]
            if len(parts) > 1 and parts[1] in ONES: cur += ONES[parts[1]]
            elif len(parts) > 1: return (total + cur, j + 1) if cur else None      # "five-minute": the word after the hyphen is the unit
        elif parts[0] in ONES and cur % 10 == 0 and (cur == 0 or cur >= 20):
            cur += ONES[parts[0]]
            if len(parts) > 1: return total + cur, j + 1
        elif w in SCALE and (cur or total):
            cur = max(cur, 1) * SCALE[w]
            if SCALE[w] >= 1000: total += cur; cur = 0
        else:
            break
        j += 1
    return (total + cur, j) if j > i else None


def _fmt(v: float) -> str:
    return f"{int(v):,}" if v == int(v) else f"{v:,.1f}"


def spoken_number(text: str) -> Optional[Dict[str, str]]:
    toks = _words(text)
    for i in range(len(toks)):
        got = _value(toks, i)
        if not got or toks[i] in ",.;:!?":
            continue
        v, j = got
        if toks[i].lower() in ("one", "a") and j == i + 1 and not (j < len(toks) and toks[j].lower() in ("in", "percent", "%")):
            continue      # "one ordinary morning": a word, not a figure
        shown = _fmt(v)
        if j + 1 < len(toks) and toks[j].lower() in ("to", "or") and _value(toks, j + 1):      # a range: "twenty to thirty minutes", "two or three walks"
            v2, j = _value(toks, j + 1); shown = f"{shown}-{_fmt(v2)}"
        unit_bits: List[str] = []
        if toks[i].endswith("%") or (j < len(toks) and toks[j].lower() == "percent"):
            unit = "%"
        else:
            if "-" in toks[j - 1] and toks[j - 1].split("-")[-1].lower() not in ONES and not toks[j - 1][0].isdigit():
                unit_bits.append(toks[j - 1].split("-", 1)[1])      # "five-minute habit"
            k = j
            while k < len(toks) and len(unit_bits) < 2 and toks[k].lower() not in STOP and toks[k].lower() not in ("a", "an") and toks[k][0].isalpha():
                unit_bits.append(toks[k]); k += 1
            if k + 1 < len(toks) and toks[k].lower() == "a" and toks[k + 1][0].isalpha() and unit_bits:      # "times a minute"
                unit_bits += [toks[k], toks[k + 1]]
            unit = " ".join(unit_bits[:4])
            if not unit:
                continue      # "over fifty": a bare number says nothing on screen
        return {"number": shown, "unit": unit, "word": toks[i]}
    return None


def _key_word(item: str) -> str:
    ws = [w for w in re.findall(r"[a-z0-9']+", item.lower()) if len(w) > 2 and w not in STOP and w not in ("not", "don't", "do")]
    return ws[0] if ws else ""


def times_for(items: List[str], sentences: List[dict], start: float, dur: float) -> List[Dict]:
    """Each item gets the moment its key word is spoken in the scene's sentences (word position inside the sentence); never before the previous item,
    never in the last second. An item whose word is not found is spaced evenly."""
    out: List[Dict] = []; last = 0.2; n = max(1, len(items))
    for k, item in enumerate(items):
        key = _key_word(item); t = None
        for s in sentences:
            low = s["text"].lower(); pos = low.find(key) if key else -1
            if pos >= 0:
                t = float(s["start"]) - start + (pos / max(1, len(low))) * (float(s["end"]) - float(s["start"]))
                if t >= last - 0.01: break
                t = None
        if t is None:
            t = dur * (k + 0.4) / (n + 0.4)
        t = round(min(max(t, last + 0.45 if out else 0.3), max(0.3, dur - 1.0)), 2); last = t
        out.append({"text": item, "t0": t})
    return out


def number_time(word: str, sentences: List[dict], start: float) -> float:
    for s in sentences:
        low = s["text"].lower(); pos = low.find(word.lower())
        if pos >= 0:
            return round(max(0.3, float(s["start"]) - start + (pos / max(1, len(low))) * (float(s["end"]) - float(s["start"])) - 0.2), 2)
    return 0.6
