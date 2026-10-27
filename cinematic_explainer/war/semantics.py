"""Lightweight, deterministic narration semantics for the War Documentary planner. No network, no models, no randomness.

    analyze_scene(text, catalog=None, words=None, t0=0.0, t1=0.0) -> SceneAnalysis

A scene is split into sentences; each sentence is read for entities (equipment, figures, institutions, places, generic weapon words), numbers with
their referent, years, quotations with a speaker, source citations, motion ("from A to B"), location cues, territorial-change verbs, comparisons,
claims (who says it) and disputes. Context matters: a place in a possessive ("Russia's economy") is not a location, a person named only in a
comparison is not a speaker, the word "missile" without a system is a class mention only.

The catalog is optional. When given, it supplies find_equipment / find_figure / find_institution / find_place (each: text -> list of entries as
dicts or objects with at least `name`; `id`, `aliases`, `klass`, `generic` are used when present). A missing method is an empty answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ----------------------------------------------------------------------------------------------------------------------------
# small vocabularies (kept deliberately short and explicit)
# ----------------------------------------------------------------------------------------------------------------------------

GENERIC_WEAPON_WORDS = ("missiles", "missile", "drones", "drone", "tanks", "tank", "launchers", "launcher", "aircraft", "jets", "jet",
                        "helicopters", "helicopter", "artillery", "rockets", "rocket", "radars", "radar", "air defense", "air defence",
                        "warships", "warship", "ships", "ship", "submarines", "submarine", "howitzers", "howitzer", "bombers", "bomber")
MOTION_VERBS = ("moved", "advanced", "flew", "shipped", "withdrew", "travelled", "traveled", "launched", "transported", "sailed", "drove",
                "retreated", "marched", "redeployed", "was flown", "were flown", "was sent", "were sent", "delivered", "headed", "pushed")
TERRITORIAL_VERBS = ("took control of", "captured", "seized", "lost", "retook", "recaptured", "liberated", "occupied", "withdrew from",
                     "encircled", "regained", "advanced on", "took", "overran", "surrounded")
CLAIM_VERBS = ("claimed", "claims", "claim", "said", "says", "reported", "reports", "stated", "states", "announced", "alleged", "insists",
               "insisted", "maintains", "asserted", "told")
DISPUTE_CUES = ("disputed", "denied", "denies", "deny", "rejected the claim", "rejects the claim", "contradicted", "contradicts",
                "contradict", "refuted", "refutes", "dismissed the claim", "no evidence", "could not be verified", "unverified")
LOCATION_CUES = ("in", "near", "outside", "around", "south of", "north of", "east of", "west of", "approaching", "across", "toward",
                 "towards", "reached", "entered", "inside", "at", "from", "into", "over", "along", "close to", "south-east of", "north-east of")
GEO_VERBS = ("lies", "lie", "located", "situated", "borders", "bordering", "bordered", "shore", "coast", "coastline", "neighbours", "neighbors",
             "adjacent", "stretches", "extends", "shares a border", "north of", "south of", "east of", "west of", "lies between", "washed by")
INSTITUTION_VERBS = ("met", "meets", "said", "says", "issued", "adopted", "voted", "declared", "announced", "imposed", "approved", "condemned",
                     "called", "discussed", "discuss", "statement", "statements", "resolution", "resolutions", "ruled", "decided", "warned",
                     "reported", "published", "confirmed", "denied", "agreed")
PART_WORDS = ("northern", "southern", "eastern", "western", "central", "north", "south", "east", "west", "outskirts of", "suburbs of")
SOURCE_NOUNS = ("report", "statement", "bulletin", "communique", "communiqué", "briefing", "filing", "memo", "order", "document", "assessment",
                "update", "release", "dispatch", "analysis", "survey", "transcript")
SPEECH_VERBS = ("said", "says", "told", "stated", "announced", "declared", "added", "warned", "wrote", "replied", "argued", "insisted",
                "claimed", "explained", "noted", "confirmed")
ROLE_WORDS = ("minister", "president", "prime minister", "chief", "general", "commander", "spokesperson", "spokesman", "spokeswoman",
              "secretary", "chancellor", "ambassador", "director", "chairman", "governor", "mayor", "defence minister", "defense minister",
              "head of", "leader")
ATTRIBUTE_WORDS = ("range", "km", "kilometres", "kilometers", "crew", "calibre", "caliber", "tubes", "carries", "carried", "fires", "fired",
                   "launches", "launched", "weighs", "speed", "payload", "armed", "armoured", "armored", "in service", "deployed", "operates",
                   "operated", "entered service", "role", "protects", "intercepts", "detects", "warhead", "engine", "mm")
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
                "twelve": 12, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100}
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
PERIOD_WORDS = ("a day", "per day", "a week", "per week", "a month", "per month", "a year", "per year", "an hour", "per hour", "a night")

# a minimal gazetteer, used ONLY when no catalog with find_place is given
_COUNTRIES = ("Ukraine", "Russia", "Belarus", "Poland", "Romania", "Moldova", "Turkey", "Georgia", "Germany", "France", "Finland", "Estonia",
              "Latvia", "Lithuania", "Hungary", "Slovakia", "Bulgaria", "Kazakhstan", "Iran", "China", "United States", "United Kingdom")
_PLACES = ("Crimea", "Donbas", "Donetsk", "Luhansk", "Kherson", "Zaporizhzhia", "Kharkiv", "Kyiv", "Odesa", "Mariupol", "Bakhmut", "Sevastopol",
           "Moscow", "St Petersburg", "Black Sea", "Sea of Azov", "Dnipro", "Kursk", "Belgorod", "Bryansk", "Avdiivka", "Kerch")


def builtin_places() -> List[Dict[str, Any]]:
    out = [{"name": n, "id": "geo:" + n.lower().replace(" ", "-"), "kind": "country"} for n in _COUNTRIES]
    out += [{"name": n, "id": "geo:" + n.lower().replace(" ", "-"), "kind": "place"} for n in _PLACES]
    return out


# ----------------------------------------------------------------------------------------------------------------------------
# data classes
# ----------------------------------------------------------------------------------------------------------------------------

@dataclass
class Entity:
    kind: str                      # equipment | figure | institution | place | generic_weapon
    name: str
    id: str = ""
    span: Tuple[int, int] = (0, 0)  # in scene text
    entry: Any = None
    specific: bool = True
    subject: bool = False
    country: bool = False
    ambiguous: bool = False
    class_id: str = ""


@dataclass
class Number:
    value: float
    raw: str
    unit: str                      # referent noun / unit ("drones", "km", "%"); "" when none
    span: Tuple[int, int]
    period: str = ""               # "a day", "per month"
    is_year: bool = False
    complete: bool = False         # value + referent present


@dataclass
class Quote:
    text: str
    speaker: str                   # as written; "" when none
    verb: str = ""
    span: Tuple[int, int] = (0, 0)


@dataclass
class Citation:
    outlet: str
    kind: str                      # "according_to" | "outlet_says" | "source_noun"
    span: Tuple[int, int] = (0, 0)


@dataclass
class Comparison:
    kind: str                      # "from_to" | "versus"
    a: Number
    b: Number
    span: Tuple[int, int] = (0, 0)


@dataclass
class SentenceInfo:
    index: int
    text: str
    span: Tuple[int, int]
    entities: List[Entity] = field(default_factory=list)
    numbers: List[Number] = field(default_factory=list)
    years: List[Tuple[int, Tuple[int, int]]] = field(default_factory=list)
    quote: Optional[Quote] = None
    citation: Optional[Citation] = None
    motion: Optional[Tuple[Entity, Entity, str]] = None      # origin, destination, verb
    location: List[Entity] = field(default_factory=list)      # places named with a location cue (not possessive, not a part)
    territorial: Optional[Tuple[str, List[Entity]]] = None
    comparison: Optional[Comparison] = None
    claimant: str = ""
    claim: bool = False
    disputed: bool = False
    dispute_parties: List[str] = field(default_factory=list)
    generic_weapons: List[str] = field(default_factory=list)
    intro_figure: Optional[Tuple[Entity, str]] = None         # "X, the minister of Y": (figure, role phrase)
    explanatory: bool = False
    geography: bool = False                                    # a geography sentence: lies / borders / shore ... with places named
    inst_subject: Optional[Entity] = None                      # an institution that is the subject of an action sentence
    dated_events: List[Tuple[str, str, int]] = field(default_factory=list)   # (date text, label, char offset in scene text)
    dated_clause: Optional[Tuple[str, str]] = None            # (date text, label) for a timeline clause such as "In 2014, ..."


@dataclass
class SceneAnalysis:
    text: str
    sentences: List[SentenceInfo]
    token_times: List[Tuple[int, int, float, float]]           # (char start, char end, t0, t1) per token

    def time_at(self, char: int) -> float:
        for s, e, a, _b in self.token_times:
            if s <= char < e or char < s:
                return a
        return self.token_times[-1][3] if self.token_times else 0.0

    def end_time_of(self, span: Tuple[int, int]) -> float:
        last = None
        for s, e, _a, b in self.token_times:
            if s < span[1]:
                last = b
        return last if last is not None else (self.token_times[-1][3] if self.token_times else 0.0)


# ----------------------------------------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------------------------------------

def _get(entry: Any, key: str, default: Any = None) -> Any:
    if entry is None:
        return default
    if isinstance(entry, dict):
        return entry.get(key, default)
    return getattr(entry, key, default)


def _entries(catalog: Any, method: str, text: str) -> List[Any]:
    fn = getattr(catalog, method, None) if catalog is not None else None
    if fn is None:
        return []
    try:
        res = fn(text)
    except Exception:
        return []
    if res is None:
        return []
    if isinstance(res, (list, tuple)):
        return list(res)
    return [res]


def _names_of(entry: Any) -> List[str]:
    names = []
    n = _get(entry, "name")
    if n:
        names.append(str(n))
    for a in _get(entry, "aliases", None) or []:
        if a:
            names.append(str(a))
    return sorted(set(names), key=lambda s: (-len(s), s))


_SENT_SPLIT = re.compile(r"(?<=[.!?])([\"”’')\]]*)\s+(?=[\"“‘'(\[]?[A-Z0-9])")
_ABBR = ("Mr.", "Mrs.", "Ms.", "Dr.", "St.", "Gen.", "Col.", "Lt.", "Sgt.", "Maj.", "No.", "U.S.", "U.K.", "vs.", "Prof.", "Cmdr.", "Adm.")


def split_sentences(text: str) -> List[Tuple[str, Tuple[int, int]]]:
    """Sentences with their (start, end) offsets. Known abbreviations do not end a sentence; a closing quote stays with its sentence."""
    out: List[Tuple[str, Tuple[int, int]]] = []
    pos = 0
    for m in _SENT_SPLIT.finditer(text):
        seg_end = m.end(1)
        seg = text[pos:seg_end]
        if any(seg.rstrip().endswith(a) for a in _ABBR):
            continue
        s = seg.strip()
        if s:
            ls = text.find(s, pos)
            out.append((s, (ls, ls + len(s))))
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        ls = text.find(tail, pos)
        out.append((tail, (ls, ls + len(tail))))
    return out


_TOKEN = re.compile(r"\S+")


def _norm(tok: str) -> str:
    return re.sub(r"[^\w%]", "", tok.lower())


def token_times(text: str, words: Optional[Sequence[Dict[str, Any]]], t0: float, t1: float) -> List[Tuple[int, int, float, float]]:
    """(char start, char end, t0, t1) for every whitespace token. Real word times when `words` align with the text, else proportional."""
    toks = [(m.start(), m.end(), m.group(0)) for m in _TOKEN.finditer(text)]
    if not toks:
        return []
    times: List[Optional[Tuple[float, float]]] = [None] * len(toks)
    if words:
        wlist = []
        for w in words:
            try:
                wlist.append((_norm(str(w.get("w", w.get("word", "")))), float(w["t0"]), float(w.get("t1", w["t0"]))))
            except (KeyError, TypeError, ValueError):
                continue
        j = 0
        for i, (_s, _e, tok) in enumerate(toks):
            nt = _norm(tok)
            if not nt:
                continue
            for k in range(j, min(len(wlist), j + 6)):
                if wlist[k][0] == nt:
                    times[i] = (wlist[k][1], wlist[k][2])
                    j = k + 1
                    break
    if all(t is None for t in times):
        total = max(1, toks[-1][1])
        span = max(0.0, t1 - t0)
        return [(s, e, t0 + span * s / total, t0 + span * e / total) for s, e, _ in toks]
    # fill gaps by interpolation between known neighbours
    known = [i for i, t in enumerate(times) if t is not None]
    for i in range(len(toks)):
        if times[i] is not None:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        if prev is None and nxt is None:
            times[i] = (t0, t0)
        elif prev is None:
            times[i] = (times[nxt][0], times[nxt][0])  # type: ignore[index]
        elif nxt is None:
            times[i] = (times[prev][1], times[prev][1])  # type: ignore[index]
        else:
            a, b = times[prev][1], times[nxt][0]  # type: ignore[index]
            f = (i - prev) / (nxt - prev)
            times[i] = (a + (b - a) * f, a + (b - a) * f)
    return [(s, e, times[i][0], times[i][1]) for i, (s, e, _t) in enumerate(toks)]  # type: ignore[index]


def _find_all(text: str, name: str) -> List[Tuple[int, int]]:
    out = []
    for m in re.finditer(r"(?<![\w])" + re.escape(name) + r"(?![\w])", text, flags=re.IGNORECASE):
        out.append((m.start(), m.end()))
    return out


def _is_possessive(text: str, end: int) -> bool:
    return text[end:end + 2] in ("'s", "’s") or text[end:end + 1] in ("’",) and text[end:end + 2] == "’s"


def _is_part(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 14):start].lower()
    after = text[end:end + 8].lower()
    if any(before.rstrip().endswith(p) for p in PART_WORDS):
        return True
    return after.lstrip().startswith(("area", "region area", "suburb"))


def _has_cue_before(text: str, start: int) -> bool:
    before = text[max(0, start - 24):start].lower().rstrip()
    before = re.sub(r"\b(the|a|an)$", "", before).rstrip()
    return any(before.endswith(c) for c in LOCATION_CUES)


def _subject_ok(text: str, span: Tuple[int, int], sent_start: int) -> bool:
    """True when the entity sits before the first verb-like word of the sentence (a cheap subject-of-sentence test)."""
    lead = text[sent_start:span[0]]
    words = re.findall(r"[A-Za-z']+", lead)
    if len(words) > 4:
        return False
    return not any(w.lower() in MOTION_VERBS or w.lower() in ("is", "was", "are", "were", "has", "had") for w in words)


# ----------------------------------------------------------------------------------------------------------------------------
# numbers, quotes, citations
# ----------------------------------------------------------------------------------------------------------------------------

_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(\s?(?:%|percent|per cent))?(?:\s+(million|billion|thousand|hundred))?", re.IGNORECASE)
_WORDNUM = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)
_STOP_REF = {"of", "the", "a", "an", "and", "in", "on", "at", "to", "from", "by", "with", "for", "were", "was", "is", "are", "has", "had",
             "that", "which", "who", "as", "per", "than", "more", "less", "over", "under", "about", "around", "nearly", "almost"}


def _referent(text: str, end: int) -> Tuple[str, str]:
    """(unit/referent noun phrase, period) following a number."""
    tail = text[end:end + 60]
    period = ""
    low = tail.lower()
    for p in PERIOD_WORDS:
        k = low.find(p)
        if 0 <= k <= 40:
            period = p
            break
    words = re.findall(r"[A-Za-z%'’-]+", tail)
    ref: List[str] = []
    for w in words[:3]:
        lw = w.lower()
        if lw in _STOP_REF and not ref:
            if lw in ("of",):
                continue
            break
        if lw in _STOP_REF:
            break
        ref.append(w)
        if len(ref) == 2:
            break
    return " ".join(ref), period


def find_numbers(sentence: str, offset: int = 0) -> Tuple[List[Number], List[Tuple[int, Tuple[int, int]]]]:
    numbers: List[Number] = []
    years: List[Tuple[int, Tuple[int, int]]] = []
    for m in _NUM.finditer(sentence):
        raw = m.group(0)
        val = float(m.group(1).replace(",", ""))
        mult = (m.group(3) or "").lower()
        if mult:
            val *= {"million": 1e6, "billion": 1e9, "thousand": 1e3, "hundred": 1e2}[mult]
        span = (offset + m.start(), offset + m.end())
        is_pct = bool(m.group(2))
        if not is_pct and not mult and 1900 <= val <= 2099 and float(m.group(1)) == int(float(m.group(1))) and "," not in m.group(1):
            years.append((int(val), span))
            continue
        unit = "%" if is_pct else ""
        ref, period = _referent(sentence, m.end())
        if not unit:
            unit = ref
        n = Number(value=val, raw=raw.strip(), unit=unit, span=span, period=period, complete=bool(unit or period))
        numbers.append(n)
    for m in _WORDNUM.finditer(sentence):
        ref, period = _referent(sentence, m.end())
        if ref:
            numbers.append(Number(value=float(NUMBER_WORDS[m.group(1).lower()]), raw=m.group(0), unit=ref, span=(offset + m.start(), offset + m.end()),
                                  period=period, complete=True))
    numbers.sort(key=lambda n: n.span)
    return numbers, years


_QUOTE_RE = re.compile(r"[\"“]([^\"”]{6,400})[\"”]")


def find_quote(sentence: str, offset: int = 0) -> Optional[Quote]:
    m = _QUOTE_RE.search(sentence)
    if not m:
        return None
    around = sentence[:m.start()] + " " + sentence[m.end():]
    speaker = ""
    verb = ""
    # '..." said Minister Dorrin Vale'  or  'Dorrin Vale said: "..."'
    after = sentence[m.end():]
    mm = re.match(r"[,.]?\s*(?:" + "|".join(SPEECH_VERBS) + r")\s+([A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*){0,4})", after)
    if mm:
        verb = re.match(r"[,.]?\s*(\w+)", after).group(1) if re.match(r"[,.]?\s*(\w+)", after) else ""
        speaker = mm.group(1).strip()
    else:
        before = sentence[:m.start()]
        mb = re.search(r"([A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*){0,4}),?\s+(" + "|".join(SPEECH_VERBS) + r")\b[:,]?\s*$", before)
        if mb:
            speaker = mb.group(1).strip()
            verb = mb.group(2)
        else:
            ma = re.search(r"\b(?:according to)\s+([A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*){0,4})", around)
            if ma:
                speaker = ma.group(1).strip()
    speaker = speaker.strip(" .,;:")
    # pronoun attribution never names a speaker
    if speaker.lower() in ("he", "she", "they", "it", "i", "we"):
        speaker = ""
    return Quote(text=m.group(1).strip(), speaker=speaker, verb=verb, span=(offset + m.start(), offset + m.end()))


_NAME = r"[A-Z][\w&.'’-]*(?:\s+(?:(?:of|for|the|and|de)\s+)?[A-Z][\w&.'’-]*){0,4}"
_CITE_ACC = re.compile(r"\b(?i:according to) (?:the )?(" + _NAME + r")")
_CITE_SAYS = re.compile(r"\b(?:the )?(" + _NAME + r")\s+(?:" + "|".join(CLAIM_VERBS) + r")\b")
_CITE_NOUN = re.compile(r"\b(?:a|the)\s+(?:" + "|".join(SOURCE_NOUNS) + r")\s+(?:by|from|of)\s+(?:the )?(" + _NAME + r")")
_CITE_POSS = re.compile(r"\b(?:the )?([A-Z][\w&.'’-]*(?:\s+[A-Z][\w&.'’-]*){0,3})['’]s\s+(?:" + "|".join(SOURCE_NOUNS) + r")\b")
_NOT_OUTLET = {"He", "She", "It", "They", "We", "The", "This", "That", "There", "But", "And", "Analysts", "Experts", "Critics", "Officials", "Sources"}


def find_citation(sentence: str, offset: int = 0) -> Optional[Citation]:
    for rx, kind in ((_CITE_ACC, "according_to"), (_CITE_NOUN, "source_noun"), (_CITE_POSS, "source_noun"), (_CITE_SAYS, "outlet_says")):
        m = rx.search(sentence)
        if m:
            name = m.group(1).strip()
            first = name.split()[0]
            if first in _NOT_OUTLET and len(name.split()) == 1:
                continue
            if name.split()[0] in _NOT_OUTLET:
                name = " ".join(name.split()[1:])
                if not name:
                    continue
            return Citation(outlet=name, kind=kind, span=(offset + m.start(1), offset + m.end(1)))
    return None


# ----------------------------------------------------------------------------------------------------------------------------
# the main entry
# ----------------------------------------------------------------------------------------------------------------------------

def _unwrap(item: Any) -> Tuple[Any, str, Optional[Tuple[int, int]], str, str]:
    """(entry, confidence, (start, end) in the searched text or None, class id, matched alias) for a catalog Match or a plain entry."""
    if hasattr(item, "matched_alias") and hasattr(item, "confidence"):
        st, en = int(getattr(item, "start", 0) or 0), int(getattr(item, "end", 0) or 0)
        return (item.entry, str(item.confidence), (st, en) if en > st else None, str(getattr(item, "class_id", "") or ""),
                str(getattr(item, "matched_alias", "") or ""))
    return item, "exact", None, str(_get(item, "class", "") or _get(item, "klass", "") or ""), ""


def _collect_entities(catalog: Any, sentence: str, s_off: int, scene_text: str) -> List[Entity]:
    ents: List[Entity] = []
    seen = set()

    def add(kind: str, item: Any, aliases_extra: Sequence[str] = ()) -> None:
        entry, conf, span0, class_id, alias = _unwrap(item)
        if entry is None:
            if conf == "generic" and span0:
                span = (s_off + span0[0], s_off + span0[1])
                ents.append(Entity(kind="generic_weapon", name=alias or class_id, id=class_id, span=span, specific=False, class_id=class_id))
            return
        spans: List[Tuple[int, int]] = [span0] if span0 else []
        if not spans:
            for nm in _names_of(entry) + [a for a in aliases_extra if a]:
                spans = _find_all(sentence, nm)[:1]
                if spans:
                    break
        if not spans:
            return
        a, b = spans[0]
        key = (kind, _get(entry, "id") or _get(entry, "name"), a)
        if key in seen:
            return
        seen.add(key)
        span = (s_off + a, s_off + b)
        ambiguous = conf == "ambiguous"
        generic = bool(_get(entry, "generic", False)) or str(_get(entry, "confidence", "")).lower() == "uncertain"
        etype = str(_get(entry, "type", "") or _get(entry, "kind", "")).lower()
        ents.append(Entity(kind=kind, name=str(_get(entry, "name") or alias), id=str(_get(entry, "id") or ""), span=span, entry=entry,
                           specific=(not generic) and not ambiguous, subject=_subject_ok(scene_text, span, max(0, s_off)),
                           country=(etype == "country"), ambiguous=ambiguous, class_id=class_id))

    for e in _entries(catalog, "find_equipment", sentence):
        add("equipment", e)
    for e in _entries(catalog, "find_figure", sentence):
        extra = []
        entry = _unwrap(e)[0]
        nm = str(_get(entry, "name") or "")
        if nm and len(nm.split()) > 1 and len(nm.split()[-1]) >= 4:
            extra.append(nm.split()[-1])
        add("figure", e, extra)
    for e in _entries(catalog, "find_institution", sentence):
        add("institution", e)
    if catalog is not None and hasattr(catalog, "find_place"):
        for e in _entries(catalog, "find_place", sentence):
            add("place", e)
        have = {x.name.lower() for x in ents if x.kind == "place"}
        for e in builtin_places():            # countries the catalog does not carry (no coordinates, fills only)
            if e["kind"] == "country" and e["name"].lower() not in have:
                add("place", e)
    else:
        for e in builtin_places():
            add("place", e)
    ents.sort(key=lambda x: (x.span[0], x.kind, x.name))
    return _merge_adjacent_institutions(ents, scene_text)


def _merge_adjacent_institutions(ents: List[Entity], text: str) -> List[Entity]:
    """'United Nations' + 'Security Council' matched as two fragments of one name: keep the longer match."""
    out: List[Entity] = []
    for e in ents:
        if out and e.kind == "institution" and out[-1].kind == "institution" and e.span[0] - out[-1].span[1] <= 1:
            prev = out[-1]
            if (e.span[1] - e.span[0]) > (prev.span[1] - prev.span[0]):
                out[-1] = e
            continue
        out.append(e)
    return out


def _generic_weapons(sentence: str, ents: Sequence[Entity]) -> List[str]:
    out = [e.name.lower() for e in ents if e.kind == "generic_weapon"]
    low = sentence.lower()
    for w in GENERIC_WEAPON_WORDS:
        if re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", low):
            # a generic word inside a specific equipment name is not a separate class mention
            if any(w in e.name.lower() for e in ents if e.kind == "equipment"):
                continue
            if any(w in e.name.lower() for e in ents if e.kind == "generic_weapon"):
                continue
            out.append(w)
    return sorted(set(out))


def _location_entities(text: str, sent_text: str, s_off: int, ents: Sequence[Entity]) -> List[Entity]:
    out = []
    for e in ents:
        if e.kind != "place":
            continue
        a, b = e.span
        if _is_possessive(text, b):
            continue
        if _is_part(text, a, b):
            continue
        if not _has_cue_before(text, a):
            continue
        out.append(e)
    return out


def _motion(text: str, ents: Sequence[Entity], sentence_span: Tuple[int, int]) -> Optional[Tuple[Entity, Entity, str]]:
    places = [e for e in ents if e.kind == "place" and not _is_possessive(text, e.span[1])]
    if len(places) < 2:
        return None
    seg = text[sentence_span[0]:sentence_span[1]].lower()
    verb = next((v for v in MOTION_VERBS if re.search(r"\b" + re.escape(v) + r"\b", seg)), "")
    for i, a in enumerate(places):
        for b in places[i + 1:]:
            between = text[a.span[1]:b.span[0]].lower()
            if re.search(r"\bfrom\s*$", text[max(0, a.span[0] - 6):a.span[0]].lower()) or re.search(r"\bfrom\b", text[max(0, a.span[0] - 12):a.span[0]].lower()):
                if re.match(r"^\s*(?:,?\s*(?:to|toward|towards|into)\b|\s*and on to\b)", between) and verb:
                    return a, b, verb
    return None


def _territorial(text: str, ents: Sequence[Entity], sentence_span: Tuple[int, int]) -> Optional[Tuple[str, List[Entity]]]:
    seg = text[sentence_span[0]:sentence_span[1]]
    low = seg.lower()
    for v in sorted(TERRITORIAL_VERBS, key=lambda s: -len(s)):
        k = low.find(v)
        if k < 0 or not re.search(r"(?<![\w])" + re.escape(v) + r"(?![\w])", low):
            continue
        after = sentence_span[0] + k + len(v)
        places = [e for e in ents if e.kind == "place" and e.span[0] >= after - 1 and e.span[0] - after < 60 and not _is_possessive(text, e.span[1])]
        if places:
            return v, places[:3]
    return None


def _claim(sentence: str) -> Tuple[bool, str, bool, List[str]]:
    low = sentence.lower()
    claimant = ""
    m = re.search(r"\b(?i:according to) (?:the )?(" + _NAME + r")", sentence)
    if m:
        claimant = m.group(1)
    else:
        m = re.search(r"\b(?:the )?(" + _NAME + r")\s+(?:" + "|".join(CLAIM_VERBS) + r")\b", sentence)
        if m and m.group(1).split()[0] not in _NOT_OUTLET:
            claimant = m.group(1)
        else:
            m = re.search(r"\b(?:the\s+)?(ministry|army|military|government|kremlin|general staff|air force|navy|agency)\b[^.]{0,30}\b(?:" + "|".join(CLAIM_VERBS) + r")\b", low)
            if m:
                claimant = "the " + m.group(1) if not m.group(1).startswith("the") else m.group(1)
    claim = bool(claimant) or any(re.search(r"\b" + c + r"\b", low) for c in ("claimed", "claims", "alleged", "reportedly", "reported"))
    disputed = any(c in low for c in DISPUTE_CUES)
    parties: List[str] = []
    if disputed:
        parties = [p for p in re.findall(r"\b([A-Z][\w&.'’-]*(?:\s+[A-Z][\w&.'’-]*){0,3})\s+(?:" + "|".join(CLAIM_VERBS + ("denied", "denies", "rejected", "disputed")) + r")\b", sentence)
                   if p.split()[0] not in _NOT_OUTLET][:2]
    return claim, claimant, disputed, parties


def _intro_figure(text: str, ents: Sequence[Entity]) -> Optional[Tuple[Entity, str]]:
    for e in ents:
        if e.kind != "figure":
            continue
        tail = text[e.span[1]:e.span[1] + 70]
        m = re.match(r",\s+(?:the\s+)?(?:[A-Z][\w-]+(?:'s|\u2019s)\s+)?((?:" + "|".join(ROLE_WORDS) + r")\b[^,.;]{0,50})", tail, flags=re.IGNORECASE)
        if m:
            return e, m.group(1).strip()
        before = text[max(0, e.span[0] - 40):e.span[0]]
        m = re.search(r"\b((?:" + "|".join(ROLE_WORDS) + r")(?:\s+of\s+\w+)?)\s*$", before, flags=re.IGNORECASE)
        if m:
            return e, m.group(1).strip()
    return None


_COMP_FROM_TO = re.compile(r"\bfrom\s+(?:about\s+|around\s+|roughly\s+)?(\d[\d,]*(?:\.\d+)?)\s*([A-Za-z%][\w%]*(?:\s+(?:a|per)\s+\w+)?)?\s+to\s+(?:about\s+|around\s+|roughly\s+)?(\d[\d,]*(?:\.\d+)?)\s*([A-Za-z%][\w%]*(?:\s+(?:a|per)\s+\w+)?)?", re.IGNORECASE)
_COMP_VS = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([A-Za-z%][\w%]*)?\s*(?:versus|vs\.?|compared (?:with|to)|against)\s+(\d[\d,]*(?:\.\d+)?)\s*([A-Za-z%][\w%]*)?", re.IGNORECASE)


def _comparison(sentence: str, offset: int) -> Optional[Comparison]:
    for rx, kind in ((_COMP_FROM_TO, "from_to"), (_COMP_VS, "versus")):
        m = rx.search(sentence)
        if not m:
            continue
        try:
            v1 = float(m.group(1).replace(",", ""))
            v2 = float(m.group(3).replace(",", ""))
        except ValueError:
            continue
        u1 = (m.group(2) or "").strip()
        u2 = (m.group(4) or "").strip()
        unit = u2 or u1
        if not unit and kind == "from_to":
            ref, per = _referent(sentence, m.end())
            unit = ref
        a = Number(v1, m.group(1), u1 or unit, (offset + m.start(1), offset + m.end(1)), complete=bool(u1 or unit))
        b = Number(v2, m.group(3), u2 or unit, (offset + m.start(3), offset + m.end(3)), complete=bool(u2 or unit))
        if kind == "from_to" and (a.unit.lower() != b.unit.lower() and u1 and u2):
            continue
        return Comparison(kind=kind, a=a, b=b, span=(offset + m.start(), offset + m.end()))
    return None


_DATED_CLAUSE = re.compile(r"^(?:In|By|On|Since)\s+((?:\d{1,2}\s+)?(?:(?:" + "|".join(m.capitalize() for m in MONTHS) + r")\s+)?(?:19|20)\d\d)\s*,?\s+(.{8,120})$")


_DATE = re.compile(r"(?:\b\d{1,2}\s+)?(?:\b(?:" + "|".join(m.capitalize() for m in MONTHS) + r")\s+)?\b(?:19|20)\d\d\b")
_CLAUSE_SPLIT = re.compile(r",\s+(?:and|but|while|whereas)\s+|;\s+|\s+and then\s+")


def _dated_events(sentence: str, offset: int) -> List[Tuple[str, str, int]]:
    """Clauses of one sentence that carry exactly their own date: (date, the clause's own words without the date, offset). No words are added."""
    body = sentence.rstrip(".!? ")
    if ":" in body:
        body = body.split(":", 1)[1].strip()
    out: List[Tuple[str, str, int]] = []
    pos = sentence.find(body) if body else 0
    cursor = 0
    pieces: List[Tuple[str, int]] = []
    for m in _CLAUSE_SPLIT.finditer(body):
        pieces.append((body[cursor:m.start()], cursor))
        cursor = m.end()
    pieces.append((body[cursor:], cursor))
    for piece, at in pieces:
        dm = _DATE.search(piece)
        if not dm:
            continue
        date = dm.group(0).strip()
        before = piece[:dm.start()].rstrip()
        after = piece[dm.end():].lstrip(" ,")
        before = re.sub(r"\b(?:in|on|by|since|during)$", "", before, flags=re.IGNORECASE).rstrip(" ,")
        label = (before + (" " + after if after else "")).strip(" ,")
        words = label.split()
        if len(words) < 3:
            continue
        label = label[0].upper() + label[1:]
        out.append((date, label, offset + max(0, pos) + at))
    return out


def analyze_scene(text: str, catalog: Any = None, words: Optional[Sequence[Dict[str, Any]]] = None, t0: float = 0.0, t1: float = 0.0) -> SceneAnalysis:
    text = text or ""
    infos: List[SentenceInfo] = []
    for i, (stext, span) in enumerate(split_sentences(text)):
        ents = _collect_entities(catalog, stext, span[0], text)
        numbers, years = find_numbers(stext, span[0])
        quote = find_quote(stext, span[0])
        citation = find_citation(stext, span[0])
        claim, claimant, disputed, parties = _claim(stext)
        info = SentenceInfo(index=i, text=stext, span=span, entities=ents, numbers=numbers, years=years, quote=quote, citation=citation,
                            claim=claim, claimant=claimant, disputed=disputed, dispute_parties=parties)
        info.generic_weapons = _generic_weapons(stext, ents)
        info.location = _location_entities(text, stext, span[0], ents)
        info.motion = _motion(text, ents, span)
        info.territorial = _territorial(text, ents, span)
        info.comparison = _comparison(stext, span[0])
        info.intro_figure = _intro_figure(text, ents)
        low = stext.lower()
        info.explanatory = any(k in low for k in ("works by", "in stages", "layered", "how it works", "in three stages", "consists of"))
        dm = _DATED_CLAUSE.match(stext)
        if dm:
            info.dated_clause = (dm.group(1), dm.group(2).rstrip(".!?"))
        info.geography = any(re.search(r"(?<![\w])" + re.escape(g) + r"(?![\w])", low) for g in GEO_VERBS) and \
            len({e.name.lower() for e in ents if e.kind == "place" and not _is_possessive(text, e.span[1])}) >= 2
        for e in ents:
            if e.kind == "institution" and e.subject and not e.ambiguous and any(re.search(r"\b" + v + r"\b", low) for v in INSTITUTION_VERBS):
                info.inst_subject = e
                break
        info.dated_events = _dated_events(stext, span[0])
        infos.append(info)
    return SceneAnalysis(text=text, sentences=infos, token_times=token_times(text, words, t0, t1))
