"""What a sentence is about and what it says, from its words only (no niche vocabulary)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

STOP = set("""a an the and or but if so of to in on at by for with from as is are was were be been being it its this that these those there here he she they them
his her their our your you we i not no yes do does did done have has had will would can could may might must should than then also just very more most much
many some any all each every both other another such only own same too into onto over under about after before between through during while when where which
who whom whose what why how up down out off again once because until against among within without around across per via""".split())
DISCOURSE = {"first", "second", "third", "next", "finally", "however", "meanwhile", "today", "yesterday", "now", "imagine", "suddenly", "later", "soon", "still", "yet", "even", "once", "last"}
ICONS = (("heart", r"heart|cardiac|love|health"), ("brain", r"brain|mind|think\w*|memory|intelligen\w*|learn\w*"), ("cell", r"cells?|bacteri\w*|virus\w*|disease|biolog\w*"),
         ("atom", r"atoms?|molecul\w*|chemi\w*|particle\w*|physics"), ("tree", r"trees?|forest|plants?|nature|crops?|farm\w*|food|wood"),
         ("drop", r"water|rain|ocean|sea|river|flood\w*|drink\w*|liquid"), ("flame", r"fire|burn\w*|heat|hot|flame\w*|fuel|oil|coal"),
         ("car", r"cars?|vehicles?|driving|drivers?|traffic|road\w*|trucks?"), ("plane", r"planes?|aircraft|flights?|fly\w*|airline\w*|airport\w*"),
         ("ship", r"ships?|boats?|navy|fleet|sail\w*|ports?|shipping"), ("building", r"city|cities|building\w*|company|companies|office\w*|bank\w*|market\w*|business\w*|economy|factory|factories|government|housing"),
         ("battery", r"battery|batteries|energy|power|electric\w*|grid"), ("camera", r"camera\w*|photo\w*|film\w*|video\w*|footage|cinema"),
         ("eye", r"eyes?|vision|see|seen|watch\w*|look\w*|surveillance"), ("letter", r"email\w*|letters?|messages?|mail|text\w*|news|press|report\w*"),
         ("lightning", r"lightning|electricity|storm\w*|shock\w*|spark\w*|voltage"), ("magnet", r"magnet\w*|attract\w*"),
         ("skull", r"death|die[sd]?|dead|kill\w*|war|deadly|fatal\w*|murder\w*|poison\w*"), ("thermometer", r"temperature\w*|degrees|fever|climate|warming|cold|freez\w*"),
         ("warning", r"danger\w*|risk\w*|threat\w*|warning|crisis|collapse\w*|crash\w*|fraud|scam\w*"), ("question", r"mystery|unknown|secret\w*|why|how|puzzle\w*"),
         ("check", r"success\w*|solved|won|win|approved|correct|proof|prove\w*"), ("cross", r"fail\w*|lost|lose|ban\w*|rejected|wrong|myth\w*"),
         ("human", r"people|person|population|humans?|workers?|students?|citizens?|men|women|children|users?|customers?|everyone|society"),
         ("earth", r"world|global\w*|planet|countr\w+|nations?|international|earth"), ("hourglass", r"time|years?|decades?|centur\w*|history|era|age|days?|hours?"),
         ("rocket", r"rockets?|launch\w*|space|orbit\w*|startup\w*|growth"), ("cube", r"block\w*|chain|data|code|software|system\w*|network\w*|digital|computer\w*|chip\w*|ai|algorithm\w*"))
UP = r"rose|rises?|rising|grew|grow\w*|increas\w+|jump\w*|climb\w*|surg\w+|soar\w*|rall(?:y|ied|ies)|spik\w+|doubl\w+|tripl\w+|boom\w*|gain\w*"
DOWN = r"fell|falls?|falling|drop\w*|decreas\w+|declin\w+|plung\w+|slump\w*|shr[aou]nk|shrink\w*|collaps\w+|crash\w*|halv\w+|lost|loses|losing|cut|cuts"
QUANT = re.compile(r"(?P<cur>[$€£¥])?\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?(?P<mag>trillion|billion|million|thousand|hundred|k\b|m\b|bn\b)?\s?(?P<unit>%|percent|per ?cent|x\b|times|[a-z°]{2,})?", re.I)
ERA = re.compile(r"\b(\d{1,4})\s?(BCE?|AD|CE)\b")
YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b(?!\s?(?:%|percent|km|kg|people|dollars|per))")
SEQ = re.compile(r"\b(first(?:ly)?|second(?:ly)?|third(?:ly)?|then|next|after that|afterwards|finally|lastly|step (?:one|two|three|\d)|to begin|once)\b", re.I)
COMPARE = re.compile(r"\b(\d+(?:\.\d+)?|twice|double|triple|half)\s*(?:times|x|fold)?\s*(?:as\s+)?(?:more|less|larger|bigger|smaller|faster|slower|higher|lower|longer|heavier|stronger|cheaper|richer|older|younger|as much|as many|as)\b|\b(?:more|less|larger|bigger|smaller|faster|slower|higher|lower|longer|heavier|stronger|cheaper|richer|older|younger)\s+than\b|\bversus\b|\bvs\.?\b", re.I)
QUOTE = re.compile(r"[\"“]([^\"”]{12,160})[\"”]")
DEFINE = re.compile(r"^(?:an?\s+|the\s+)?(?P<term>[A-Za-z][\w' -]{1,32}?)\s+(?:is|are|means|refers to|is called|are called|is known as|are known as|is defined as)\s+(?:an?\s+|the\s+)?(?P<what>[^.;]{8,120})", re.I)
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
           "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100}


@dataclass
class Concept:
    kind: str                         # quote | change | compare | percent | timeline | process | list | stat | term | keyword
    headline: str = ""                # the short label (a few words, from the sentence)
    sub: str = ""
    strength: float = 0.0             # 0..1: how much there is to show (a bare keyword is weak)
    icon: str = ""
    values: List[float] = field(default_factory=list)
    unit: str = ""
    prefix: str = ""
    years: List[int] = field(default_factory=list)
    items: List[str] = field(default_factory=list)
    direction: int = 0                # +1 up, -1 down
    subject: str = ""                 # the main noun phrase: what a picture of this must show
    names: List[str] = field(default_factory=list)    # compare: the two things compared, smaller side first
    terms: List[str] = field(default_factory=list)   # content words (lower case) a relevant picture/model must overlap


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[{}\[\]<>]", "", s or "")).strip(" ,;:.-–—\"'“”")


def content_words(text: str) -> List[str]:
    return [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text or "") if w.lower() not in STOP]


def subject_of(text: str) -> str:
    """The main thing the sentence is about: the longest run of capitalised words (not at the start of the sentence), else the first noun-like
    content words."""
    caps = re.findall(r"\b([A-Z][\w'-]+(?: (?:of |the |de |von )?[A-Z][\w'-]+){0,3})", text or "")
    caps = [re.sub(r"^(?:(?:%s) )+" % "|".join(sorted(STOP | DISCOURSE)), "", c, flags=re.I) for c in caps]
    caps = [c for c in caps if c and c.lower() not in STOP | DISCOURSE and c.split()[0].lower() not in STOP | DISCOURSE]
    if caps:
        return max(caps, key=len)
    cw = content_words(text)
    return " ".join(cw[:3])


def _num(m: "re.Match[str]") -> float:
    v = float(m.group("num").replace(",", ""))
    mag = (m.group("mag") or "").lower()
    return v * {"trillion": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3, "hundred": 100}.get(mag, 1)


def quantities(text: str) -> List[Tuple[float, str, str, str]]:
    """[(value, unit text, prefix, raw)] of every figure in the sentence (digits, with k/million/billion and %, currency)."""
    t = text or ""
    for w, n in WORDNUM.items():
        t = re.sub(rf"\b{w}\b(?=\s+(?:percent|per ?cent|times|million|billion|thousand))", str(n), t, flags=re.I)
    out = []
    for m in QUANT.finditer(t):
        if YEAR.fullmatch(m.group("num")) and not (m.group("cur") or m.group("unit") in ("%", "percent")):
            continue
        unit = (m.group("unit") or "").strip()
        if unit.lower() in STOP or unit.lower() in ("last", "year", "years", "ago", "later", "earlier", "next", "again", "alone", "overall", "total", "now", "today", "later"):
            unit = ""
        if m.group("mag") and unit.lower() not in ("%", "percent", "per cent"):
            unit = unit if unit.lower() in ("dollars", "euros", "people", "users", "customers", "miles", "km", "kg", "tons", "tonnes", "years", "units", "jobs", "barrels", "lives") else ""
        pct = unit.lower() in ("%", "percent", "per cent", "percent")
        mag = (m.group("mag") or "").lower()
        shown_unit = "%" if pct else (unit.upper() if unit and not mag else "")
        if mag and not pct:
            shown_unit = {"trillion": "TRILLION", "billion": "BILLION", "bn": "BILLION", "million": "MILLION", "m": "MILLION", "thousand": "THOUSAND", "k": "K", "hundred": "HUNDRED"}[mag] + (f" {unit.upper()}" if unit else "")
            val = float(m.group("num").replace(",", ""))
        else:
            val = float(m.group("num").replace(",", ""))
        out.append((val, shown_unit.strip(), m.group("cur") or "", m.group(0).strip()))
    return out


def _items(text: str) -> List[str]:
    """A spoken list: "A, B, and C" with short items."""
    m = re.search(r"((?:[\w'-]+(?: [\w'-]+){0,3}, ){2,}(?:and |or )?[\w'-]+(?: [\w'-]+){0,3})", text or "")
    if not m:
        return []
    raw = [_clean(re.sub(r"^(?:and|or) ", "", p.strip())) for p in m.group(1).split(",")]
    raw[-1] = re.split(r"\b(?:all|are|is|were|was|depend\w*|have|has|can|will|would|need\w*|use\w*|rely|rel\w+)\b", raw[-1])[0].strip()
    parts = []
    for p in raw:
        parts += [x.strip() for x in re.split(r"\s+(?:and|or)\s+", p) if x.strip()]
    parts = [p for p in parts if p and len(p.split()) <= 4]
    return parts[:6] if len(parts) >= 3 else []


def _icon(text: str) -> str:
    low = (text or "").lower()
    best = ("", 0)
    for name, rx in ICONS:
        n = len(re.findall(rf"\b(?:{rx})\b", low))
        if n > best[1]:
            best = (name, n)
    return best[0]


def _headline(text: str, drop: str = "") -> str:
    ws = [w for w in content_words(re.sub(drop, " ", text, flags=re.I) if drop else text)]
    return " ".join(ws[:4]).upper()


def analyze(text: str) -> Concept:
    """The concept of one sentence (or two). Order: quote, change, comparison, percent, timeline, sequence, list, plain figure, definition, keyword."""
    t = _clean_sentence(text)
    qs = quantities(ERA.sub(" ", t))
    years = [-int(n) if e.upper().startswith("BC") else int(n) for n, e in ERA.findall(t)] + [int(y) for y in YEAR.findall(ERA.sub(" ", t))]
    if ERA.search(t):
        t_q = ERA.sub(" ", t)
        qs = quantities(t_q)
    subj, icon = subject_of(t), _icon(t)
    terms = [w.lower() for w in content_words(t)]
    base = dict(subject=subj, icon=icon, terms=terms)
    q = QUOTE.search(t)
    if q:
        who = _clean(re.sub(QUOTE, " ", t))
        return Concept("quote", headline=_clean(q.group(1)), sub=" ".join(who.split()[:7]).upper(), strength=0.8, **base)
    up, down = re.search(rf"\b(?:{UP})\b", t, re.I), re.search(rf"\b(?:{DOWN})\b", t, re.I)
    span = re.search(r"\bfrom\b.*\bto\b", t, re.I)
    if (up or down or (span and len(qs) >= 2 and not len(set(years)) >= 2)) and (qs or span):
        vals = [v for v, *_ in qs]
        d = (1 if (up and (not down or up.start() < down.start())) else -1) if (up or down) else (1 if len(vals) < 2 or vals[1] >= vals[0] else -1)
        pct = next((x for x in qs if x[1] == "%"), None)
        if pct:
            return Concept("change", headline=f"{'+' if d > 0 else '-'}{_fmt(pct[0])}%", sub=_headline(t, r"\d[\d,.]*|percent|%"), strength=0.9, values=[pct[0]], unit="%", direction=d, **base)
        if len(vals) >= 2:
            return Concept("change", headline=f"{_fmt(vals[0])} TO {_fmt(vals[1])}", sub=_headline(t, r"\d[\d,.]*"), strength=0.85, values=vals[:2], unit=qs[1][1], prefix=qs[1][2], direction=d, **base)
    if COMPARE.search(t) and qs:
        vals = [v for v, *_ in qs][:2]
        if len(vals) == 1:
            vals = [1.0, vals[0]]
        mt = re.search(r"\b(?:than|versus|vs\.?|as)\s+(?:the\s+|in\s+|on\s+|that of\s+)?([A-Za-z][\w'-]*(?: [A-Z][\w'-]*)?)", t)
        big = subject_of(t[:mt.start()] if mt else t) or subj
        small = (mt.group(1) if mt else "") or "THE REST"
        return Concept("compare", headline=_headline(t, r"\d[\d,.]*|times|than"), strength=0.8, values=vals, unit=qs[0][1] if qs[0][1] not in ("TIMES", "X") else "",
                       names=[small.upper(), big.upper()], **base)
    pct = next((x for x in qs if x[1] == "%" and 0 < x[0] <= 100), None)
    if pct:
        return Concept("percent", headline=f"{_fmt(pct[0])}%", sub=_headline(t, r"\d[\d,.]*|percent|%"), strength=0.85, values=[pct[0]], unit="%", **base)
    if len(set(years)) >= 2:
        ys = sorted(set(years))[:5]
        return Concept("timeline", headline="", strength=0.8, years=ys, items=_year_events(t, ys), **base)
    if len(SEQ.findall(t)) >= 2:
        steps = [_headline(s) for s in re.split(r"\b(?:first(?:ly)?|then|next|after that|afterwards|finally|lastly|second(?:ly)?|third(?:ly)?)\b[,]?", t, flags=re.I) if len(content_words(s)) >= 1]
        steps = [s for s in (" ".join(x.split()[:3]) for x in steps) if s][:5]
        if len(steps) >= 2:
            return Concept("process", headline=steps[0], strength=0.75, items=steps, **base)
    items = _items(t)
    if items:
        return Concept("list", headline="", strength=0.7, items=[i.upper() for i in items], **base)
    if qs:
        v, unit, cur, raw = qs[0]
        return Concept("stat", headline=_fmt(v), sub=_headline(t, re.escape(raw)), strength=0.7, values=[v], unit=unit, prefix=cur, **base)
    if len(set(years)) == 1 and re.search(r"\b(?:in|by|since|until|during|around|from)\s+" + str(years[0]), t):
        return Concept("timeline", headline=_headline(t, r"\b\d{4}\b"), strength=0.5, years=years, **base)
    d = DEFINE.match(t)
    if d and len(d.group("term").split()) <= 3:
        return Concept("term", headline=_clean(d.group("term")).upper(), sub=_clean(d.group("what")).upper()[:90], strength=0.6, **base)
    return Concept("keyword", headline=_headline(t), strength=0.2, **base)


def _year_events(t: str, ys: List[int]) -> List[str]:
    """The few words said around each year (after it, else before it), to label its tick."""
    marks = sorted((m.start(), m.end(), -int(m.group(1)) if m.group(2).upper().startswith("BC") else int(m.group(1))) for m in ERA.finditer(t))
    marks += [(m.start(), m.end(), int(m.group(1))) for m in YEAR.finditer(ERA.sub(lambda m: " " * len(m.group(0)), t))]
    marks.sort()
    out = {}
    for i, (a, b, y) in enumerate(marks):
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(t)
        prv = marks[i - 1][1] if i else 0
        for seg in (t[b:nxt], t[prv:a]):
            cw = content_words(re.sub(r"\b(?:from|until|since|in|by|and|to)\b", " ", seg))
            if cw:
                out[y] = " ".join(cw[:3]).upper()
                break
    return [out.get(y, "") for y in ys]


def _clean_sentence(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _fmt(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}"
    return f"{v:,.1f}".rstrip("0").rstrip(".")
