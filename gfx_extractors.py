"""What the narration itself supplies for the universal graphics beyond a single number (gfx_templates.auto_events calls these).

Each extractor takes (sentence, ctx) and returns the template's slots, or None. It only ever copies what the narration says: the exact words of a
quotation, a name and the role the narrator gives it, a place the map can find, the values of a comparison. A required slot the narration does not
fill means no graphic (the planner drops it), never an invented line. Reserved keys in the result: `_t0` / `_t1` = the seconds the graphic belongs to
(the planner keeps its own pacing rules), `_key` is not used by the planner.

ctx: .resolve (place name -> (lon, lat) or None, may be None), .raw (the sentence as spoken, with its punctuation), .time_at(char) / .end_at(char) (seconds of
the word at that character of ctx.raw), .sents ([(text, start, end)] of the whole narration), .index (this sentence's place in it), .mentions(name).

Templates covered: quote_card, quote_boxed, name_bar, place_lowerthird, fact_card, record_badge, timeline_strip, versus_numbers, checklist_card, three_rings,
tag_fact, end_question, heading_card, punchline, rank_bars (the same two numbers as versus_numbers, drawn as bars).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_PRONOUNS = {"he", "she", "they", "it", "we", "i", "you", "there", "then", "the", "a", "an", "this", "that", "his", "her", "their", "its", "our", "who"}
_TITLES = r"(?:Dr|Mr|Mrs|Ms|Prof|Professor|President|Captain|King|Queen|Sir|Admiral|General|Mayor|Senator|Prime Minister|Chancellor|Emperor)\.?"
_WORD = r"[A-Z][a-zA-Z'’-]+"
_CONNECTORS = {"then", "but", "and", "so", "later", "meanwhile", "today", "now", "there", "here", "when", "after", "while", "yet", "also", "finally", "next", "still", "once", "soon", "if", "because", "although"}
_NAME = rf"(?:{_TITLES}\s+)?{_WORD}(?:\s+{_WORD}){{0,2}}"
_SAY = r"(?:said|says|wrote|declared|told\s+\w+|added|noted|warned|insisted|recalled|explained|remarked|argued|announced|replied|whispered|admitted)"
_QUOTE = re.compile(r"[“\"]([^“”\"]{12,240}?)[”\"]")


def _name_ok(name: str) -> bool:
    words = re.sub(rf"^{_TITLES}\s+", "", name).split()
    return bool(words) and words[0].lower() not in _PRONOUNS


# ---- quotes ----------------------------------------------------------------------------------------------------------------------------
def _attribution(before: str, after: str) -> str:
    """Who said it, only when the sentence says so: `"..." said Dr. Smith`, `Smith said: "..."`, `according to Smith, "..."`. Pronouns say nothing."""
    for pat, text in ((rf"^\s*[,.]?\s*{_SAY}\s*[,:]?\s*(?P<n>{_NAME})", after), (rf"^\s*[,.]?\s*(?P<n>{_NAME})\s+{_SAY}\b", after),
                      (rf"(?P<n>{_NAME})\s+{_SAY}\s*[,:]?\s*$", before), (rf"(?i:according to)\s+(?P<n>{_NAME})\s*[,:]?\s*$", before)):
        m = re.search(pat, text)
        if m and _name_ok(m.group("n")):
            return m.group("n").upper().rstrip(".")
    return ""


def _parse_quote(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    m = _QUOTE.search(ctx.raw)
    if not m:
        return None
    q = m.group(1).strip().rstrip(",;:").strip()
    n = len(q.split())
    if n < 4 or n > 30 or len(q) > 170:
        return None                                   # a quotation is never shortened: one that does not fit the card gets no card
    by = _attribution(ctx.raw[:m.start()], ctx.raw[m.end():])
    return {"q": q, "words": n, "by": by, "_t0": ctx.time_at(m.start() + 1), "_t1": ctx.end_at(m.end() - 2) + 1.0}


def _lines(q: str, width: int = 26) -> str:
    out, cur = [], ""
    for w in q.split():
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    out.append(cur)
    return "|".join(out)


def quote_card(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """A quoted passage with its speaker, or a longer quotation: the exact words, the speaker only when the narration names one."""
    p = _parse_quote(sentence, ctx)
    if not p or not (p["by"] or p["words"] >= 8):
        return None
    return {"text": _lines(p["q"]), "by": p["by"], "_t0": p["_t0"], "_t1": p["_t1"]}


def quote_boxed(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """A short, unattributed quotation in heavy capitals (the narrator quoting a phrase)."""
    p = _parse_quote(sentence, ctx)
    if not p or p["by"] or p["words"] >= 8:
        return None
    return {"text": p["q"].upper(), "mark": "", "_t0": p["_t0"], "_t1": p["_t1"]}


# ---- named people ------------------------------------------------------------------------------------------------------------------------
_ROLES = ("scientist|biologist|geologist|engineer|professor|researcher|historian|author|writer|explorer|mayor|president|minister|director|captain|general|king|queen|"
          "emperor|pilot|farmer|fisherman|resident|spokesperson|astronaut|doctor|physicist|chemist|ecologist|oceanographer|climatologist|meteorologist|economist|"
          "journalist|photographer|guide|ranger|archaeologist|anthropologist|geographer|surveyor|governor|senator|chief|elder|curator|officer|commander|expert|"
          "forecaster|hydrologist|glaciologist|volcanologist|seismologist")
_PERSON = re.compile(rf"(?P<name>{_NAME})\s*,\s*(?P<role>(?:a|an|the)\s+(?:[a-z-]+\s+){{0,4}}?(?:{_ROLES})s?(?:\s+(?:at|of|from|with|in)\s+[^,;.]{{3,45}})?)\s*[,.;]")
_TITLED = re.compile(rf"(?P<title>Dr|Prof|Professor|Captain|Mayor|President|Admiral|General|Senator)\.?\s+(?P<name>{_WORD}(?:\s+{_WORD})?)\s+(?:said|says|explains|explained|told|noted|warned)\b")


def _trim_name(name: str) -> str:
    """The name without the sentence's own connecting word ("Then Jane Smith" -> "Jane Smith") and without a title."""
    words = name.split()
    while words and words[0].lower() in _CONNECTORS:
        words.pop(0)
    return re.sub(rf"^{_TITLES}\s+", "", " ".join(words)).strip()


_ROLES2 = (_ROLES + "|painter|artist|prospector|naturalist|botanist|sculptor|architect|poet|composer|inventor|navigator|missionary|settler|miner|trader|monk|"
           "priest|bishop|judge|sheriff|soldier|general|admiral|pioneer|geologist|paleontologist|palaeontologist|cartographer|explorer|surveyor")
_PARTICLE = r"(?:von|van|de|der|den|di|da|del|la|le|bin|al|el)"
_NAME_P = rf"{_WORD}(?:\s+(?:{_PARTICLE}\s+)?{_WORD}){{1,2}}"
_ROLE_NAME = re.compile(rf"\b(?:the|a|an)\s+(?P<role>(?:[a-z-]+\s+)?(?:{_ROLES2}))\s+(?P<name>{_NAME_P})")


def name_bar(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """A person the narrator introduces with what they are: `Jane Smith, a glaciologist at the University of X,` or `Dr. Smith said`. A bare name, or
    a name that is a place the map knows, gets nothing."""
    for m in _PERSON.finditer(ctx.raw):
        name = _trim_name(m.group("name"))
        if len(name.split()) >= 2 and _name_ok(name) and not (ctx.resolve and ctx.resolve(name)):
            role = re.sub(r"^(?:a|an|the)\s+", "", m.group("role")).strip()
            return {"label": name.upper(), "sub": role.upper(), "_t0": ctx.time_at(m.start("name") + len(m.group("name")) - len(m.group("name").lstrip()))}
    t = _TITLED.search(ctx.raw)
    if t and not (ctx.resolve and ctx.resolve(t.group("name"))):
        return {"label": t.group("name").upper(), "sub": t.group("title").upper().rstrip("."), "_t0": ctx.time_at(t.start("title"))}
    for r in _ROLE_NAME.finditer(ctx.raw):      # "the painter Eugene von Guerard had recorded...": the narrator says who and what they were
        name = _trim_name(r.group("name"))
        if len(name.split()) >= 2 and _name_ok(name) and not (ctx.resolve and ctx.resolve(name)):
            return {"label": name.upper(), "sub": r.group("role").strip().upper(), "_t0": ctx.time_at(r.start("name"))}
    return None


# ---- places ----------------------------------------------------------------------------------------------------------------------------
_PLACE = rf"{_WORD}(?:\s+(?:of\s+|de\s+|la\s+)?{_WORD}){{0,3}}"
_KINDS = "city|town|village|island|port|region|province|state|capital|peninsula|bay|lake|river|mountain|range|desert|valley|harbour|harbor|park|strait|canal|dam|reserve"
_PLACE_INTRO = re.compile(rf"^\s*(?:(?P<prep>In|At|Near|Inside|Outside|Welcome to|Here in)\s+)?(?:The\s+)?(?P<p>{_PLACE})"
                          rf"(?P<tail>\s*,\s*(?:on|in|at|near|off|along|beside|within)\s+[^,]{{3,60}}\s*,|\s*,\s*{_PLACE}\s*[,.]|\s+is\s+(?:a|an|the)\s+(?:[a-z-]+\s+){{0,3}}?(?:{_KINDS})|\s*,)")


def place_lowerthird(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """A place the narration introduces (first words of a sentence, then where it is or what it is) that the map can find, and that is not the subject
    of the whole video (named in three sentences or more). The second line is another place the sentence itself names, never a fact."""
    if ctx.resolve is None:
        return None
    m = _PLACE_INTRO.match(ctx.raw)
    if not m:
        return None
    place = m.group("p").strip()
    tail = m.group("tail") or ""
    if tail.strip() == "," and not m.group("prep"):
        return None                                   # "Canada, ..." at the start of a sentence introduces nothing; "In Halifax, ..." does
    if place.split()[0].lower() in _PRONOUNS or not ctx.resolve(place):
        return None
    if ctx.mentions(place) >= 3:
        return None
    sub = ""
    for cand in re.findall(_PLACE, tail):
        c = cand.strip()
        if c and c.lower() != place.lower() and c.lower() not in _PRONOUNS and ctx.resolve(c):
            sub = c.upper(); break
    return {"label": place.upper(), "sub": sub, "_t0": ctx.time_at(m.start("p"))}


# ---- numbered facts and records --------------------------------------------------------------------------------------------------------
_WORD_NUMS = {w: i + 1 for i, w in enumerate("one two three four five six seven eight nine ten eleven twelve".split())}
_FACT = re.compile(r"^\s*(?P<k>fact|number|reason|tip|myth|step|lesson)\s*(?:number\s*)?(?P<n>\d{1,2}|" + "|".join(_WORD_NUMS) + r")\b[\s:,.\-–—]*(?P<rest>.*)$", re.I | re.S)


def fact_card(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """`Fact 3: ...` / `Number seven, ...`: the numbered card with the headline the narrator gives, nothing made up for the body."""
    m = _FACT.match(ctx.raw)
    if not m:
        return None
    n = m.group("n").lower()
    num = int(n) if n.isdigit() else _WORD_NUMS[n]
    rest = re.split(r"[.!?:;]|,\s", m.group("rest").strip())[0].strip()
    words = rest.split()
    if len(words) < 2 or len(words) > 7 or len(rest) > 30:
        return None                                   # the headline bar holds about 30 characters; a longer one is not cut, it gets no card
    return {"n": num, "kicker": m.group("k").upper(), "title": rest.upper(), "_t0": ctx.time_at(m.start("k"))}


_MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_DATE = rf"(?:{_MONTH}\s+\d{{4}}|\d{{4}})"
_RECORD_WORD = re.compile(r"(?i)\b(?:the\s+)?(hottest|coldest|wettest|driest|windiest|highest|lowest|deepest|warmest|snowiest|strongest)\s+"
                          r"(day|night|month|year|temperature|reading|tide|wind|gust|snowfall|rainfall|winter|summer)(?:\s+ever)?(?:\s+(?:recorded|on record))?\b")
_QTY_UNIT = r"(?:°\s*[CF]|degrees\s+(?:Celsius|Fahrenheit)|millimet(?:re|er)s|mm|kilomet(?:re|er)s per hour|km/h|mph|knots|met(?:re|er)s|feet|inches|centimet(?:re|er)s)"
_PREV = re.compile(rf"(?i)\b(?:beating|broke|breaking|surpassing|topping|beat|passing|eclipsing)\s+(?:the\s+)?(?:previous|old|earlier)\s+record\s+of\s+(?P<q>[-−]?\d[\d,.]*\s*{_QTY_UNIT})\s*,?\s*(?:set|from|in|recorded)\s+(?:in\s+)?(?P<d>{_DATE})")
_NEWDATE = re.compile(rf"\b(?:in|on|during)\s+(?P<d>{_DATE})\b")
_NEWQ = re.compile(rf"(?P<q>[-−]?\d[\d,.]*\s*{_QTY_UNIT})", re.I)


def record_badge(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """A broken record, only when the sentence gives all of it: what the record is, where, the new value and when, and the old value and when. The badge has
    no way to show less, so anything missing means no badge."""
    rw, prev = _RECORD_WORD.search(ctx.raw), _PREV.search(ctx.raw)
    if not rw or not prev:
        return None
    head = ctx.raw[: prev.start()]
    newq, newd = _NEWQ.search(head), None
    for d in _NEWDATE.finditer(head):
        newd = d
    place = re.search(rf"\b(?i:in|at|near)\s+(?P<p>{_PLACE})\b", head)
    if not (newq and newd and place):
        return None
    p = place.group("p").strip()
    if ctx.resolve is not None and not ctx.resolve(p):
        return None
    norm = lambda s: re.sub(r"\s+", " ", s.strip().replace("degrees Celsius", "°C").replace("degrees Fahrenheit", "°F")).upper()
    return {"headline": re.sub(r"(?i)^the\s+", "", rw.group(0)).upper().strip(),
            "place": p.upper(), "value": norm(newq.group("q")), "date": newd.group("d").upper(), "prev_value": norm(prev.group("q")),
            "prev_date": prev.group("d").upper(), "_t0": ctx.time_at(rw.start())}


# ---- timelines --------------------------------------------------------------------------------------------------------------------------
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-3][0-9])\b")


def _event_text(sentence: str, m) -> str:
    """The first words after the year, as spoken (or the last words before it when nothing follows): the narrator's own words, not a rewrite."""
    after = re.split(r"[.,;:!?]", sentence[m.end():])[0].split()
    before = re.split(r"[.,;:!?]", sentence[: m.start()])[-1].split()
    words = after[:5] if len(after) >= 2 else before[-5:]
    while len(words) > 2 and words[-1].lower() in {"at", "the", "of", "to", "in", "and", "a", "an", "on", "by", "for", "with", "from", "that", "was", "were"}:
        words.pop()                                   # a prefix of the spoken words, never ending on a connecting word
    text = " ".join(words).strip()
    return (text[:1].upper() + text[1:]) if text else ""


def timeline_strip(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """Three or more consecutive sentences that each date an event, in order, within a short stretch of narration: one strip, years as stated, the
    event in the narrator's own words. Fires on the first sentence of the run only."""
    sents = ctx.sents
    i = ctx.index
    if i > 0 and _YEAR.search(sents[i - 1][0]):
        return None
    rows, last = [], None
    for text, a, b in sents[i:]:
        ms = list(_YEAR.finditer(text))
        if len(ms) != 1:
            break
        m = ms[0]
        year = int(m.group(1))
        ev = _event_text(text, m)
        if (last is not None and year <= last) or not ev:
            break
        rows.append({"label": str(year), "text": ev, "_a": a, "_b": b})
        last = year
    if len(rows) < 3 or rows[-1]["_b"] - rows[0]["_a"] > 14.0:
        return None
    t0, t1 = rows[0]["_a"], rows[-1]["_b"] + 1.0
    return {"title": "TIMELINE", "rows": [{"label": r["label"], "text": r["text"]} for r in rows[:8]], "dur": round(max(4.0, min(8.0, t1 - t0 - 2.0)), 1), "_t0": t0, "_t1": t1}


# ---- two numbers face to face ---------------------------------------------------------------------------------------------------------
_VERB = r"(?:(?i:covers?|has|have|is|are|measures?|reaches|spans|stretches|holds|with|at|stands?|weighs|runs|stands at|comes to|totals?)\s+)?(?:(?i:about|around|nearly|almost|roughly|over|up to|just)\s+)?"
_VS = r"(?:[,;]\s*(?:(?i:while|whereas|but|and)\s+)?|\s+(?i:while|whereas|compared\s+(?:with|to)|versus|vs\.?|against|and|but)\b\s*)"


def _vs_pattern() -> "re.Pattern[str]":
    import gfx_templates as G
    scale = "|".join(G._SCALE)
    unit = "|".join(list(G._UNITS) + ["people|inhabitants|residents"])
    q = rf"{G._NUM}(?:\s+(?i:{scale})\b)?(?:\s+(?i:{unit})(?![A-Za-z]))?"
    return re.compile(rf"(?P<a>{_NAME})\s+{_VERB}(?P<qa>{q})\s*{_VS}(?P<b>{_NAME})\s+{_VERB}(?P<qb>{q})", re.S)


_VS_RE: Optional["re.Pattern[str]"] = None


def versus_numbers(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """`Canada covers 10 million square kilometres, Russia 17 million`: two named things, two numbers in the same unit, stated side by side."""
    global _VS_RE
    import gfx_templates as G
    if _VS_RE is None:
        _VS_RE = _vs_pattern()
    for m in _VS_RE.finditer(ctx.raw):
        a, b = m.group("a").strip(), m.group("b").strip()
        if not (_name_ok(a) and _name_ok(b)) or a.lower() == b.lower():
            continue
        qa, qb = _quantity(G, m.group("qa")), _quantity(G, m.group("qb"))
        if not qa or not qb:
            continue
        (va, ua, sa), (vb, ub, sb) = qa, qb
        if not (ua or ub) or (ua and ub and ua != ub) or sa != sb:
            continue                                  # two bare numbers say nothing about what is compared; units and scales must agree
        if not ub and not re.match(r"\s*(?:[.,;!?]|$)", ctx.raw[m.end():]):
            continue                                  # "Russia has 140 million people": a second number with a noun of its own is not in the first one's unit
        unit = (f"{G._SCALE[sa][1]} " if sa else "") + (ua or ub)
        return {"title": "HEAD TO HEAD", "a_label": a.upper(), "a_value": va, "b_label": b.upper(), "b_value": vb, "unit": unit.strip(), "_t0": ctx.time_at(m.start("a"))}
    return None


def _quantity(G, text: str):
    m = re.fullmatch(rf"\s*{G._NUM}(?:\s+({'|'.join(G._SCALE)})\b)?(?:\s+({'|'.join(list(G._UNITS) + ['people|inhabitants|residents'])})(?![A-Za-z]))?\s*", text, re.I)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    scale = (m.group(2) or "").lower()
    unit = ""
    if m.group(3):
        u = next((v for pat, v in G._UNITS.items() if re.fullmatch(pat, m.group(3), re.I)), "PEOPLE")
        unit = u
    return (int(value) if value.is_integer() else value, unit, scale)


# ---- a spoken sequence: First ... Second ... Third ... -----------------------------------------------------------------------------------
_ORD = {"first": 1, "firstly": 1, "second": 2, "secondly": 2, "third": 3, "thirdly": 3, "fourth": 4, "fifth": 5}
_ORD_START = re.compile(r"^\s*(?:(?P<w>First|Firstly|Second|Secondly|Third|Thirdly|Fourth|Fifth)\b|(?P<s>Step)\s+(?P<n>one|two|three|four|five|\d))\s*[,:.\-–—]?\s*(?P<rest>.*)$", re.I | re.S)
_STEP_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _step(text: str):
    m = _ORD_START.match(text)
    if not m:
        return None
    n = _ORD[m.group("w").lower()] if m.group("w") else (int(m.group("n")) if m.group("n").isdigit() else _STEP_N[m.group("n").lower()])
    clause = re.split(r"[.;:!?]|,\s", m.group("rest").strip())[0].strip()
    return n, bool(m.group("s")), clause


def checklist_card(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """Three to five consecutive sentences that each open with an ordinal (First, ... Second, ... Third, ...) or "Step one/two/three": one ticked list, each
    item the sentence's first clause as spoken (a clause longer than seven words is not cut: no card). Fires on the first sentence of the run only."""
    sents, i = ctx.sents, ctx.index
    if i > 0 and _step(sents[i - 1][0]):
        return None
    rows, last = [], 0
    for text, a, b in sents[i:i + 6]:
        st = _step(text)
        if not st or st[0] != last + 1 or not st[2] or len(st[2].split()) > 7 or len(st[2]) > 24:      # (the card clips what is wider than 24 characters: no card, never a cut item)
            break
        rows.append((st, a, b)); last = st[0]
    if len(rows) < 3 or rows[-1][2] - rows[0][1] > 50.0:
        return None
    items = [r[0][2][:1].upper() + r[0][2][1:] for r in rows[:5]]
    return {"title": "STEPS" if rows[0][0][1] else "IN ORDER", "items": items, "_t0": rows[0][1], "_t1": rows[-1][2] + 1.0}


# ---- three things named together -----------------------------------------------------------------------------------------------------------
_THREE = re.compile(r"(?i)\b(?:three|3)\s+(?P<what>(?:[a-z-]+\s+){0,3}?[a-z-]+)\s*[:,]\s*(?P<a>[A-Za-z][\w'-]*(?:\s[A-Za-z][\w'-]*)?)\s*,\s*(?P<b>[A-Za-z][\w'-]*(?:\s[A-Za-z][\w'-]*)?)\s*,?\s+and\s+(?P<c>[A-Za-z][\w'-]*(?:\s[A-Za-z][\w'-]*)?)(?=\s*[.;!?,]|\s*$)")


def three_rings(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """`three causes: heat, drought and wind`: the sentence says three and names three, each of one or two words."""
    m = _THREE.search(ctx.raw)
    if not m:
        return None
    items = [m.group(k).strip().upper() for k in "abc"]
    if len({x.lower() for x in items}) < 3 or any(x.split()[0].lower() in _PRONOUNS | {"and", "or"} for x in items):
        return None
    return {"items": items, "_what": m.group("what").strip().upper(), "_t0": ctx.time_at(m.start())}


# ---- one plain statement of rank -----------------------------------------------------------------------------------------------------------
_KEY = re.compile(r"\b(?P<sup>the\s+(?:highest|largest|biggest|smallest|oldest|deepest|longest|tallest|driest|wettest|hottest|coldest|first|only|last))\s+(?P<rest>(?:[A-Za-z][\w'-]*(?:\s+|(?=[,.;:!?]|$))){1,4})", re.I)
_KEY_STOP = {"in", "of", "on", "at", "to", "and", "that", "which", "who", "was", "is", "are", "were", "has", "had", "have", "with", "from", "for", "by", "ever", "as", "than",
             "listed", "found", "known", "called", "built", "made", "recorded", "it", "its", "this", "these", "those", "when", "where", "while", "after", "before", "but", "or", "so"}


def tag_fact(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """`the highest peak`, `the oldest rock`: the narrator's own words for what is superlative, whole: the superlative, then one to three words up to where the
    phrase ends (a comma, a stop word or the end of the sentence). A phrase that runs on is not cut to fit: no tag."""
    for m in _KEY.finditer(ctx.raw):
        words = m.group("rest").split()
        after = ctx.raw[m.end():].lstrip()
        keep, ended = [], False
        for w in words:
            bare = w.lower().strip(",.;:!?")
            if bare in _KEY_STOP or (bare.endswith("ed") and len(bare) > 4):      # a stop word, or a verb in the past tense: the phrase has ended
                ended = True
                break
            keep.append(w.strip(",.;:!?"))
        if not ended:
            nxt = re.match(r"[A-Za-z][\w'-]*", after)
            ended = after == "" or after[0] in ",.;:!?" or (nxt is not None and nxt.group(0).lower() in _KEY_STOP)
        if keep and len(keep) <= 3 and ended:
            return {"text": f"{m.group('sup')} {' '.join(keep)}".upper(), "_t0": ctx.time_at(m.start("sup"))}
    return None


# ---- the closing question ------------------------------------------------------------------------------------------------------------------
def end_question(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """The narration's own last question (`So which one would you visit first?`): one of the last two sentences, ending in a question mark, 3-14 words."""
    sents, i = ctx.sents, ctx.index
    if i < len(sents) - 2:
        return None
    text = ctx.raw.strip()
    if not text.endswith("?") or not 3 <= len(text.split()) <= 14:
        return None
    return {"text": text.upper()}


# ---- section headings: "Part two." / "Chapter 3: The long road" -----------------------------------------------------------------------------
_NUMWORD = {w: i + 1 for i, w in enumerate("one two three four five six seven eight nine ten eleven twelve".split())}
_HEADING = re.compile(r"^\s*(?P<kind>Chapter|Part|Section|Act)\s+(?P<n>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d{1,2})\b\s*[.:,\-–—]?\s*(?P<rest>.*)$", re.I | re.S)


def heading_card(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """`Part two.` / `Chapter 3: The long road`: the narrator announces a section. kicker = the announcement as spoken ("PART TWO"); title = what follows it in the
    same sentence, or the whole next sentence when that is a short title (2-7 words); empty when neither is there."""
    m = _HEADING.match(ctx.raw)
    if not m:
        return None
    kicker = f"{m.group('kind')} {m.group('n')}".upper()
    title = m.group("rest").strip().rstrip(".!")
    if not title and ctx.index + 1 < len(ctx.sents):
        nxt = ctx.sents[ctx.index + 1][0].strip().rstrip(".!")
        if 2 <= len(nxt.split()) <= 7 and not nxt.endswith("?") and not _HEADING.match(nxt):
            title = nxt
    if title and not 2 <= len(title.split()) <= 7:
        title = ""
    out: Dict[str, Any] = {"kicker": kicker, "title": title.upper(), "_t0": ctx.time_at(m.start("kind"))}
    if title and ctx.index + 1 < len(ctx.sents) and not m.group("rest").strip():
        out["_t1"] = ctx.sents[ctx.index + 1][2] + 0.5
    return out


# ---- a short sentence that lands as a beat of its own ---------------------------------------------------------------------------------------
_LEAD_CONJ = {"but", "and", "so", "then", "yet", "now", "also", "or", "because", "while", "when", "if", "although", "still", "later", "meanwhile", "there", "here"}


def punchline(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """A short declarative sentence that lands as a beat of its own: 3-6 words, no figures, no comma, no question, not opening with a connecting word, and at
    most 40% as long as the sentence before it (which has 14+ words). Shown word for word, never reworded or shortened; a heading is not one."""
    text = ctx.raw.strip()
    words = text.split()
    if not 3 <= len(words) <= 6 or not text.endswith((".", "!")) or "," in text or re.search(r"\d", text) or _FACT.match(text) or _HEADING.match(text):
        return None
    if words[0].lower().strip(",.") in _LEAD_CONJ or ctx.index == 0:
        return None
    prev = len(ctx.sents[ctx.index - 1][0].split())
    if prev < 14 or len(words) > 0.4 * prev:
        return None
    return {"text": text.rstrip(".!").upper(), "words": [w.strip(",.;:!?").upper() for w in words if w.strip(",.;:!?")], "_t0": ctx.time_at(0)}
