"""What a sentence gives the wall: numbers with their units, percents, money, dates and years, verdict words and twist lines, each timed
by the Whisper words. Only what the narration says is used; nothing is invented, so a sentence with nothing in it gives nothing.

    words_of(data) -> [(word, start, end)]                       narration_words.json ({"words": [[w, s, e], ...]}) or a plain list
    Timer(text, t0, t1, words)                                   the sentence's own words matched to the Whisper words in its window
        .at(char) -> start of the word at that character; .end(char) -> its end
    facts(text) -> [Fact]                                        in reading order
        kind: money | percent | count | year | date | change | verdict | twist | approx
        value, fmt ({pre, dec, suf, comma, sign}), caption, bad, span (c0, c1), at (char of the word it lands on), text (for stamps / notes)
    has_number(text) -> int                                      how many number facts (money, percent, count, year, date)
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

MONTHS = "january february march april may june july august september october november december".split()
ORDINALS = {w: i + 1 for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth "
    "seventeenth eighteenth nineteenth twentieth".split())}
ORDINALS.update({"twenty-first": 21, "twenty-second": 22, "twenty-third": 23, "twenty-fourth": 24, "twenty-fifth": 25,
                 "twenty-sixth": 26, "twenty-seventh": 27, "twenty-eighth": 28, "twenty-ninth": 29, "thirtieth": 30, "thirty-first": 31})
CURRENCY = {"€": "€", "$": "$", "£": "£", "euro": "€", "euros": "€", "dollar": "$", "dollars": "$", "pound": "£", "pounds": "£", "usd": "$", "eur": "€"}
SCALE = {"trillion": " TN", "billion": " BN", "bn": " BN", "million": " M", "m": " M", "thousand": "K", "k": "K"}
CHANGE_UP = {"more", "higher", "up", "bigger", "larger", "greater", "worse", "better", "increase", "rise", "jump", "growth"}
CHANGE_DOWN = {"less", "lower", "down", "fewer", "smaller", "cheaper", "drop", "fall", "decline", "cut"}
BAD_WORDS = re.compile(r"\b(lost|loss|losses|debt|deficit|fell|fall|dropped|down|cut|cuts|owed|owes|bankrupt\w*|crash\w*|died|killed|fewer)\b", re.I)
VERDICTS = ("no majority", "majority", "record", "bankrupt", "bankruptcy", "collapsed", "collapse", "failed", "worst", "biggest", "largest",
            "smallest", "never", "only one", "banned", "grounded", "sold", "rejected", "approved", "illegal", "doubled", "tripled", "halved")
TWIST = re.compile(r"^\s*(here is|here's|but here|and here|the strange|the problem|the catch|the twist|and yet|but there is|but there's|"
                   r"that is when|that's when|this is where|it gets worse|there is a catch|there's a catch|but that|now the)\b", re.I)
APPROX = re.compile(r"\b(about|around|nearly|almost|roughly|some|over|more than|up to|close to)\s*$", re.I)
STOP = {"a", "an", "the", "and", "or", "but", "if", "that", "which", "who", "for", "than", "to", "with", "while", "as", "so", "when",
        "was", "is", "were", "are", "be", "been", "it", "its", "this", "these", "those", "by", "at"}

_NUM = re.compile(r"(?<![A-Za-z\-])(?P<cur>[€$£])?\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d])"
                  r"(?:\s?(?P<pct>%|percent\b|per cent\b))?"
                  r"(?:\s(?P<scale>trillion|billion|million|thousand)\b|(?P<sx>bn|m|k)\b)?"
                  r"(?:\s(?P<cur2>euros?|dollars?|pounds?|usd|eur)\b)?", re.I)
_DATE = re.compile(r"\b(?:the\s+)?(?P<day>\d{1,2}|" + "|".join(sorted(ORDINALS, key=len, reverse=True)) +
                   r")(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<mon>" + "|".join(MONTHS) + r")\b(?:,?\s+(?P<year>\d{4})\b)?"
                   r"|\b(?P<mon2>" + "|".join(MONTHS) + r")\s+(?P<day2>\d{1,2})(?:st|nd|rd|th)?\b(?![%\d.,]\d)(?:,?\s+(?P<year2>\d{4})\b)?", re.I)
# the year is optional: "On November 7 power failed" is one date, never a count 7 labelled "power failed" (War render 2026-11-16)
_TOKEN = re.compile(r"[A-Za-z0-9’'\-]+")


_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                                       "sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_SCALES = {"hundred": 100, "thousand": 1000}
_BIG = ("million", "billion", "trillion")
_SPELLED = re.compile(r"\b(?:a|(?:(?:" + "|".join(list(_UNITS) + list(_TENS)) + r")(?:[\s-]+(?:and\s+)?)?)+)"
                      r"(?:(?:hundred|thousand)(?:[\s-]+(?:and\s+)?(?:" + "|".join(list(_UNITS) + list(_TENS)) + r")(?:[\s-]+)?)*)*"
                      r"(?=\s+(?:million|billion|trillion|percent|per cent)\b|\b)", re.I)


def _spelled_value(words: List[str]) -> Optional[int]:
    total = cur = 0
    seen = False
    for w in words:
        w = w.lower()
        if w == "and":
            continue
        if w == "a" and not seen:
            cur, seen = 1, True
        elif w in _UNITS:
            cur += _UNITS[w]
            seen = True
        elif w in _TENS:
            cur += _TENS[w]
            seen = True
        elif w == "hundred":
            cur = max(1, cur) * 100
        elif w == "thousand":
            total += max(1, cur) * 1000
            cur = 0
        else:
            return None
    return total + cur if seen else None


def normalize(text: str) -> str:
    """Spelled numbers as digits ('four billion' -> '4 billion', 'forty-two percent' -> '42 percent'), the way Whisper writes them.
    A lone 'one' / 'a' stays a word unless a scale (million, billion, percent ...) follows it."""
    def rep(m: "re.Match[str]") -> str:
        raw = m.group(0)
        words = [w for w in re.split(r"[\s-]+", raw.strip()) if w]
        if not words:
            return raw
        v = _spelled_value(words)
        if v is None:
            return raw
        nxt = text[m.end():m.end() + 12].lower().lstrip()
        scaled = nxt.startswith(_BIG + ("percent", "per cent"))
        if v < 2 and not scaled:
            return raw
        if words[0].lower() == "a" and not scaled:
            return raw
        tail = raw[len(raw.rstrip()):]
        return (f"{v:,}" if v >= 10000 else str(v)) + tail
    return _SPELLED.sub(rep, text)


def words_of(data: Any) -> List[Tuple[str, float, float]]:
    items = data.get("words", []) if isinstance(data, dict) else (data or [])
    out = []
    for w in items:
        try:
            if isinstance(w, dict):
                out.append((str(w.get("word") or w.get("text") or ""), float(w["start"]), float(w["end"])))
            else:
                out.append((str(w[0]), float(w[1]), float(w[2])))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return out


def _norm(tok: str) -> str:
    t = re.sub(r"[’'\-]", "", tok.lower())
    if t.isdigit():
        t = t.lstrip("0") or "0"
    return t


def _text_tokens(text: str) -> List[Tuple[int, int, str]]:
    """(char start, char end, normalised) per spoken token. The token pattern stops at '.' and ',', so "1.025" arrives as "1" + "025"
    (normalised "25"), the way Whisper writes the spoken number."""
    return [(m.start(), m.end(), _norm(m.group())) for m in _TOKEN.finditer(text)]


class Timer:
    def __init__(self, text: str, t0: float, t1: float, words: Sequence[Tuple[str, float, float]]):
        text = normalize(text)
        self.text, self.t0, self.t1 = text, float(t0), float(max(t1, t0 + 0.1))
        self.toks = _text_tokens(text)
        win = [(w, s, e) for w, s, e in words if self.t0 - 0.35 <= s < self.t1 + 0.05]
        a = [t for _c0, _c1, t in self.toks]
        b = [_norm(w) for w, _s, _e in win]
        times: List[Optional[Tuple[float, float]]] = [None] * len(a)
        if a and b:
            sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
            for blk in sm.get_matching_blocks():
                for k in range(blk.size):
                    _w, s, e = win[blk.b + k]
                    times[blk.a + k] = (s, e)
        # unmatched tokens: interpolate between matched neighbours (or across the window)
        n = len(a)
        known = [i for i, x in enumerate(times) if x is not None]
        for i in range(n):
            if times[i] is not None:
                continue
            lo = max((k for k in known if k < i), default=None)
            hi = min((k for k in known if k > i), default=None)
            ta = times[lo][1] if lo is not None else self.t0
            tb = times[hi][0] if hi is not None else self.t1
            ia = lo if lo is not None else -1
            ib = hi if hi is not None else n
            u = (i - ia) / max(1, ib - ia)
            s = ta + (tb - ta) * u
            times[i] = (s, s + max(0.05, (tb - ta) / max(1, ib - ia)))
        self.times = [x if x is not None else (self.t0, self.t0) for x in times]

    def _idx(self, char: int) -> int:
        for i, (c0, c1, _t) in enumerate(self.toks):
            if c1 > char:
                return i
        return max(0, len(self.toks) - 1)

    def at(self, char: int) -> float:
        return self.times[self._idx(char)][0] if self.toks else self.t0

    def end(self, char: int) -> float:
        return self.times[self._idx(char)][1] if self.toks else self.t0


@dataclass
class Fact:
    kind: str
    span: Tuple[int, int]
    at: int                                  # character the hit lands on
    value: float = 0.0
    fmt: Dict[str, Any] = field(default_factory=dict)
    caption: str = ""
    bad: bool = False
    text: str = ""
    start: int = 0                           # character where the build-up starts (the counter starts rolling)


def _caption(text: str, c0: int, c1: int) -> str:
    before = re.split(r"[,.;:!?]", text[:c0])[-1].split()
    after = re.split(r"[,.;:!?]", text[c1:])[0].split()
    after = [w for w in after if not w.lower() in ("euros", "euro", "dollars", "pounds")]
    if len(before) >= 2 and before[-1].lower() in ("was", "is", "were", "are", "of", "at", "cost", "costs", "reached", "hit", "totalled"):
        cap = [w for w in before[:-1] if w.lower() not in ("and", "but")][-2:]
    elif after and after[0].lower() in ("for", "than", "if", "to", "and", "but", "that", "a", "which"):
        cap = [w for w in before if w.lower() not in STOP][-2:]
    else:
        cap = after[:4]
        while cap and cap[-1].lower() in STOP:
            cap.pop()
    cut = next((k for k, w in enumerate(cap) if re.search(r"\d", w)), None)
    cap = cap[:cut] if cut is not None else cap
    while cap and cap[-1].lower() in STOP | {"in", "of", "on"}:
        cap.pop()
    s = " ".join(cap).strip(" '’\"").upper()
    return s if len(s) <= 24 else " ".join(s.split()[:3])


def _decimals(num: str) -> int:
    return len(num.split(".")[1]) if "." in num else 0


def facts(text: str) -> List[Fact]:
    """Facts of normalize(text): spans and characters refer to the normalised text (Timer works on the same text)."""
    text = normalize(text)
    out: List[Fact] = []
    taken: List[Tuple[int, int]] = []
    for m in _DATE.finditer(text):
        day = m.group("day") or m.group("day2")
        mon = (m.group("mon") or m.group("mon2")).upper()
        yr = m.group("year") or m.group("year2")
        d = int(day) if day.isdigit() else ORDINALS.get(day.lower(), 0)
        if not yr and (d < 1 or d > 31 or mon == "MAY"):
            continue                                       # "4 may be", "may 4 times", "November 40": not a date
        out.append(Fact("date", (m.start(), m.end()), m.start(), text=" ".join(x for x in (str(d) if d else "", mon, yr or "") if x),
                        start=m.start()))
        taken.append((m.start(), m.end()))
    for m in _NUM.finditer(text):
        c0, c1 = m.start("num"), m.end()
        while c1 > c0 and text[c1 - 1] == " ":
            c1 -= 1
        if any(a <= c0 < b for a, b in taken):
            continue
        num = m.group("num")
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        cur = CURRENCY.get((m.group("cur") or m.group("cur2") or "").lower(), "")
        scale = SCALE.get((m.group("scale") or m.group("sx") or "").lower(), "")
        pct = bool(m.group("pct"))
        before = text[:m.start()]
        if not cur and not scale and not pct and re.fullmatch(r"1[5-9]\d\d|20\d\d", num):
            out.append(Fact("year", (m.start(), c1), m.start("num"), value=v, text=num, start=m.start("num")))
            continue
        after = text[c1:c1 + 40].lower()
        nxt = re.match(r"\s*(\w+)", after)
        nw = nxt.group(1) if nxt else ""
        bad = bool(BAD_WORDS.search(text[max(0, m.start() - 25):m.start()]))
        if APPROX.search(before) and out and out[-1].kind in ("money", "count", "percent"):
            sym = "≈ "
            out.append(Fact("approx", (m.start(), c1), c1 - 1, value=v,
                            text=sym + (cur + (f"{v:g}" if not scale else num) + scale if cur or scale else (num + ("%" if pct else ""))),
                            start=m.start()))
            continue
        if pct and nw in CHANGE_UP | CHANGE_DOWN:
            sign = "−" if nw in CHANGE_DOWN else "+"
            out.append(Fact("change", (m.start(), c1 + len(nxt.group(0))), c1 + len(nxt.group(0)) - 1, value=v,
                            text=f"{sign}{num}% {nw.upper()}", start=m.start()))
            continue
        land = m.start("scale") if m.group("scale") else (m.start("sx") if m.group("sx") else m.end("num") - 1)   # the number word itself
        kind = "percent" if pct else ("money" if cur else "count")
        if kind == "count" and v < 3 and not scale:
            continue                                   # "one", "1" on its own: nothing to count
        fmt = {"pre": cur, "dec": _decimals(num), "suf": ("%" if pct else scale), "comma": "," in num}
        if bad and kind == "money":
            fmt["sign"] = "−"
        cap = _caption(text, m.start(), c1)
        out.append(Fact(kind, (m.start(), c1), land, value=v, fmt=fmt, caption=cap, bad=bad and kind == "money", start=m.start()))
        if pct and re.match(r"\s*of\s+\w", text[c1:]):
            out[-1].text = "of"                       # "44.9 percent of TAP": pen ring on "of"
    low = text.lower()
    for v in VERDICTS:
        i = low.find(v)
        if i >= 0 and not any(a <= i < b for a, b in [f.span for f in out]):
            j = i
            pre = re.search(r"(\b(?:no|only|not|a|the)\s+)$", low[:i])
            word = v.upper()
            if v == "majority" and re.search(r"\bnot\b[\w\s]{0,24}\ba\s+$", low[:i]):
                word = "NO MAJORITY"
            elif pre and pre.group(1).strip() in ("no", "only", "not") and " " not in v:
                word = pre.group(1).strip().upper() + " " + word
                j = pre.start()
            out.append(Fact("verdict", (j, i + len(v)), i, text=word, start=j))
            break
    if TWIST.match(text) and len(text.split()) <= 9:
        out.append(Fact("twist", (0, len(text)), 0, text=re.sub(r"[.!?,:;]+$", "", text.strip()).upper(), start=0))
    out.sort(key=lambda f: f.at)
    return out


def has_number(text: str) -> int:
    return sum(1 for f in facts(text) if f.kind in ("money", "percent", "count", "year", "date", "change"))
