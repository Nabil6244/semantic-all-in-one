"""Numbers as a narrator writes them: "one hundred sixty", "forty-one point nine", "twenty twenty two", "August twenty-fifth".

Weather scripts write numbers out in words (they are read aloud), so the engine reads them back:

    number_at(tokens, i)  -> (value, tokens used) for the number that starts at token i, or None
    year_at(tokens, i)    -> (year, tokens used): "2022", "twenty twenty two", "two thousand seventeen", "twenty seventeen"
    ordinal_at(tokens, i) -> (day, tokens used): "28", "28th", "twenty eighth", "twenty-eighth", "first"

Tokens are lower-case words with hyphens split ("twenty-fifth" -> "twenty", "fifth"); tokens() makes them."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

UNITS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
         "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
ORD_UNITS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
             "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
             "seventeenth": 17, "eighteenth": 18, "nineteenth": 19}
ORD_TENS = {"twentieth": 20, "thirtieth": 30}
TOKEN = re.compile(r"\d+(?:[.,]\d+)*(?:st|nd|rd|th)?|[a-z]+(?:'[a-z]+)?|[.,;:!?]")


def tokens(text: str) -> List[str]:
    """Lower-case words, digit groups ("1,234" -> "1234", "41.9" stays), and sentence punctuation as its own token."""
    out = []
    for t in TOKEN.findall(str(text).lower().replace("-", " ").replace("’", "'")):
        if t[0].isdigit():
            t = t.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+(?:st|nd|rd|th)?", t) else t
        out.append(t)
    return out


def _digits(t: str) -> Optional[float]:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:st|nd|rd|th)?", t)
    return float(m.group(1)) if m else None


def _below_100(toks: List[str], i: int) -> Optional[Tuple[int, int]]:
    if i >= len(toks):
        return None
    t = toks[i]
    if t in UNITS and t != "oh":
        return UNITS[t], 1
    if t in TENS:
        if i + 1 < len(toks) and toks[i + 1] in UNITS and 0 < UNITS[toks[i + 1]] < 10 and toks[i + 1] != "oh":
            return TENS[t] + UNITS[toks[i + 1]], 2
        return TENS[t], 1
    return None


def _integer(toks: List[str], i: int) -> Optional[Tuple[int, int]]:
    """A whole number in words up to the millions ("one hundred sixty", "two thousand three hundred and five")."""
    total, cur, j, used_any = 0, 0, i, False
    while j < len(toks):
        t = toks[j]
        if t == "a" and j + 1 < len(toks) and toks[j + 1] in ("hundred", "thousand", "million") and not used_any:
            cur, j, used_any = 1, j + 1, True
            continue
        b = _below_100(toks, j)
        if b is not None and (not used_any or cur % 100 == 0 or cur == 0):
            if used_any and cur % 100 != 0 and cur != 0:
                break
            cur += b[0]
            j += b[1]
            used_any = True
            continue
        if t == "hundred" and used_any:
            cur = (cur or 1) * 100
            j += 1
            continue
        if t in ("thousand", "million") and used_any:
            total += (cur or 1) * (1000 if t == "thousand" else 1_000_000)
            cur = 0
            j += 1
            continue
        if t == "and" and used_any and j + 1 < len(toks) and _below_100(toks, j + 1) is not None and (cur % 100 == 0 and cur or total):
            j += 1
            continue
        break
    if not used_any:
        return None
    return total + cur, j - i


def number_at(toks: List[str], i: int) -> Optional[Tuple[float, int]]:
    """The number starting at token i: digits ("41.9", "115"), or words with an optional "point" decimal part
    ("forty one point nine", "sixteen point zero seven")."""
    if i >= len(toks):
        return None
    d = _digits(toks[i])
    if d is not None:
        return d, 1
    whole = _integer(toks, i)
    if whole is None:
        return None
    value, n = float(whole[0]), whole[1]
    j = i + n
    if j < len(toks) and toks[j] == "point":
        digs, k = "", j + 1
        while k < len(toks) and toks[k] in UNITS and UNITS[toks[k]] < 10:
            digs += str(UNITS[toks[k]])
            k += 1
        if digs:
            value = float(f"{int(value)}.{digs}")
            n = k - i
    return value, n


def year_at(toks: List[str], i: int) -> Optional[Tuple[int, int]]:
    """A year from 1850 to 2099: "2022", "twenty twenty two", "twenty twenty-two", "two thousand seventeen", "nineteen eighty nine",
    "twenty seventeen", "twenty oh five"."""
    if i >= len(toks):
        return None
    t = toks[i]
    if re.fullmatch(r"(18[5-9]\d|19\d\d|20\d\d)", t):
        return int(t), 1
    if t == "two" and i + 1 < len(toks) and toks[i + 1] == "thousand":
        rest = _below_100(toks, i + 2) if i + 2 < len(toks) and toks[i + 2] != "and" else _below_100(toks, i + 3)
        skip = 1 if i + 2 < len(toks) and toks[i + 2] == "and" else 0
        if rest:
            return 2000 + rest[0], 2 + skip + rest[1]
        return 2000, 2
    if t in ("eighteen", "nineteen", "twenty"):
        century = {"eighteen": 1800, "nineteen": 1900, "twenty": 2000}[t]
        j = i + 1
        if j < len(toks) and toks[j] == "oh" and j + 1 < len(toks) and toks[j + 1] in UNITS and 0 < UNITS[toks[j + 1]] < 10:
            return century + UNITS[toks[j + 1]], 3
        rest = _below_100(toks, j)
        if rest and rest[0] >= 10:
            y = century + rest[0]
            if 1850 <= y <= 2099:
                return y, 1 + rest[1]
    return None


def ordinal_at(toks: List[str], i: int) -> Optional[Tuple[int, int]]:
    """A day of the month: "28", "28th", "first", "twenty eighth", "thirtieth", "thirty first"; also a plain "twenty five"."""
    if i >= len(toks):
        return None
    t = toks[i]
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?", t)
    if m and 1 <= int(m.group(1)) <= 31:
        return int(m.group(1)), 1
    if t in ORD_UNITS:
        return ORD_UNITS[t], 1
    if t in ORD_TENS:
        return ORD_TENS[t], 1
    if t in ("twenty", "thirty") and i + 1 < len(toks):
        n = toks[i + 1]
        if n in ORD_UNITS and ORD_UNITS[n] < 10:
            v = TENS[t] + ORD_UNITS[n]
            return (v, 2) if v <= 31 else None
    b = _below_100(toks, i)
    if b and 1 <= b[0] <= 31:
        return b[0], b[1]
    return None
