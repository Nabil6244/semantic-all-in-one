"""Automatic place boundary highlighting: when the narration discusses a place, its real boundary is outlined on the map at that moment.

A `focus` is an ordinary `fill` event of the map engine (drawn translucent with an outline, faded in and out), carrying the place's actual polygon:
  - countries: the engine's own country outline (`iso`),
  - states / provinces and US counties: the polygons of the app's boundary data (map_scene/data),
  - cities: the outline OpenStreetMap holds for that city (boundary_source: planning-time lookup, validated, cached; never during rendering).
Nothing is ever approximated: no circle, no box, no point. A place whose boundary cannot be established gets no highlight and a reason in `skipped`.

What counts as "discussing" a place, so a passing mention is not highlighted:
  - a motion or location cue just before it ("approaching Houston", "landfall in Florida", "flooding across Miami-Dade County"), or the place as the subject
    of the sentence ("Texas faces ..."); never a possessive ("Canada's east coast"), a part of a place ("the Texas coast", "northern Florida",
    "the Houston area") or a "city, State" tail (the state is then only evidence);
  - the name resolves to exactly one place, using the script as evidence: other places the script names (a state, a country, a county) decide between
    namesakes ("Portland" with Maine in the script); a bare name with several candidates and no evidence is skipped, never settled by "the biggest one".
    A city that nothing else supports is accepted only when it is a very large city (1 million people) that no other city of 10,000 or more shares its name.

The highlight is geographic focus only: a neutral cyan, tagged `geo_focus` with `official_warning: false`. Official warning areas stay a separate layer
with their own colours and are never produced here.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

import boundary_source as BS

FOCUS_COLOR = "#59D8FF"          # neutral light cyan: not a warning colour (reds, oranges, yellows) and visible on satellite imagery
FOCUS_OPACITY = 0.32
FOCUS_FADE_IN = 0.7
MIN_SHOW_S = 3.0
MAX_SHOW_S = 14.0
LEAD_S = 0.3                     # the outline starts just before the word
TAIL_S = 0.8                     # and stays a moment after the sentence
SAME_ENTITY_GAP_S = 45.0         # the same place is not highlighted again this soon after its last highlight
MIN_APART_S = 2.5                # two places in one sentence need this long between their words
BIG_CITY = 1_000_000
SMALL_TOWN = 100_000             # the project's convention (pakmap/geo.py): a country or state beats a town of this size or smaller that shares its name
NAMESAKE_MIN_POP = 10_000
WARNING_COLOURS = {"#df2721", "#8a2a20", "#d2641e", "#e6b83a", "#ff0000", "#ff6600", "#ffff00", "#ffa500"}


def fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").replace("’", "'"))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower().replace("&", " and ")
    t = re.sub(r"\bsaint\b", "st", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ---- entities and the name index ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Entity:
    kind: str                    # country | admin1 | county | city
    name: str
    iso: str = ""                # ISO3 of the country it is (or is in)
    country: str = ""            # that country's English name
    state: str = ""              # admin1 name (a county's state, a city's region)
    pop: int = 0
    lon: float = 0.0
    lat: float = 0.0
    idx: int = -1                # position in its dataset (countries, admin1, counties); -1 for a city

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.kind, self.iso, fold(self.state if self.kind != "admin1" else self.name) or fold(self.name))

    def supports(self) -> List[Tuple[str, ...]]:
        """What this entity's own context is made of, for matching against what the script says elsewhere (qualified by country, so Uruguay's Florida
        is not the state of Florida)."""
        out: List[Tuple[str, ...]] = [("country", self.iso)] if self.iso else []
        if self.kind in ("county", "city") and self.state:
            out.append(("admin1", self.iso, fold(self.state)))
        if self.kind == "admin1":
            out.append(("admin1", self.iso, fold(self.name)))
        return out


@lru_cache(maxsize=1)
def _features() -> Dict[str, list]:
    from map_scene.places import _dataset

    return {n: _dataset(n) for n in ("countries", "admin1", "us_counties")}


@lru_cache(maxsize=1)
def _index() -> Dict[str, List[Entity]]:
    from map_scene.places import _norm

    feats = _features()
    idx: Dict[str, List[Entity]] = {}

    def add(keys, ent):
        for k in {fold(x) for x in keys} | {_norm(x) for x in keys}:
            if k:
                idx.setdefault(k, [])
                if ent not in idx[k]:
                    idx[k].append(ent)

    for i, f in enumerate(feats["countries"]):
        add([f["n"], *f.get("alt", [])], Entity("country", f["n"], f.get("iso", ""), f["n"], idx=i))
    for i, f in enumerate(feats["admin1"]):
        add([f["n"], *f.get("alt", [])], Entity("admin1", f["n"], f.get("iso", ""), f.get("country", ""), f["n"], idx=i))
    for i, f in enumerate(feats["us_counties"]):
        add([f["n"], *[a for a in f.get("alt", []) if not a.lower().endswith(" county")]], Entity("county", f["n"], "USA", "United States of America", f.get("state", ""), idx=i))
    try:
        from pakmap.geo import _cities

        names_by_iso = {f.get("iso"): f["n"] for f in feats["countries"]}
        for keys, nm, lon, lat, pop, iso, region in _cities():
            if pop >= NAMESAKE_MIN_POP:
                add(list(keys), Entity("city", nm, iso, names_by_iso.get(iso, ""), region or "", int(pop), float(lon), float(lat)))
    except Exception:
        pass                                                      # no city list: only countries, states and counties can be found
    return idx


def iso_of_country_name(name: str) -> str:
    key = fold(name)
    for e in _index().get(key, []):
        if e.kind == "country":
            return e.iso
    return ""


def polygons_of(e: Entity) -> Optional[list]:
    f = {"admin1": "admin1", "county": "us_counties", "country": "countries"}.get(e.kind)
    return _features()[f][e.idx]["g"]["coordinates"] if f else None


# ---- reading the narration ---------------------------------------------------------------------------------------------------------------
_CAP = r"[A-Z][\w'’.-]*"
_SPAN = re.compile(rf"{_CAP}(?:\s+(?:of|de|del|la|the|and|{_CAP}))*")
_COUNTY_WORD = re.compile(r"^\s+(County|Parish|Borough)\b")
_CUE = re.compile(r"(?i)\b(?:approach(?:ing|es|ed)?|nearing|nears|near|toward|towards|heading (?:for|to|into)|head(?:s|ed) (?:for|to|into)|bears? down on|threaten(?:s|ed|ing)?|"
                  r"hits?|hitting|strikes?|striking|struck|slams?|slammed|slamming|batter(?:s|ed|ing)?|landfall (?:in|near|on|at)|made landfall (?:in|near|on|at)|"
                  r"across|over|throughout|around|into|through|affect(?:s|ed|ing)?|impact(?:s|ed|ing)?|in|at|for|inside|within|reaches|reached|reaching|"
                  r"move(?:s|d)? (?:into|over|across|toward|towards)|spread(?:s|ing)? (?:across|over|into)|flood(?:s|ing)? (?:across|in)|devastat(?:es|ed|ing)|"
                  r"warnings? (?:for|in)|evacuat(?:es|ed|ing)|(?:residents|people) (?:of|in))\s+(?:the\s+)?(?:city of\s+|state of\s+)?$")
_SUBJECT_VERB = re.compile(r"(?i)^\s*(?:is|are|was|were|will|could|may|might|has|have|had|faces|braces|prepares|expects|remains|sees|saw|records|reported|reports)\b")
_QUAL_BEFORE = re.compile(r"(?i)\b(?:north|south|east|west|northern|southern|eastern|western|northeast|northwest|southeast|southwest|northeastern|northwestern|southeastern|"
                          r"southwestern|central|upper|lower|coastal|inland|greater|downtown|metro|part of|parts of|edge of|outskirts of|border of)\s+(?:the\s+)?$")
_QUAL_AFTER = re.compile(r"(?i)^\s+(?:coast|coastline|coastal|shore|border|panhandle|metro|metropolitan|area|region|suburbs|outskirts|waters|gulf|bay|delta|valley|basin|"
                         r"plains|mountains|highlands|lowlands|peninsula)\b")
_POSSESSIVE = re.compile(r"^['’]s\b")
_APPOSITIVE_TAIL = re.compile(r",\s*(?:a|an|the)\s+(?:[a-z-]+\s+){0,4}$")


# place names that are also everyday words: capitalised at the start of a sentence they prove nothing ("Rivers are rising ...")
_COMMON_WORDS = {"rivers", "river", "mobile", "reading", "bath", "nice", "orange", "mercy", "hope", "victory", "union", "central", "north", "south", "east", "west",
                 "lake", "lakes", "island", "islands", "plains", "hills", "falls", "buffalo", "independence", "jackson", "charlotte", "phoenix", "friday", "paris"}


@dataclass
class Mention:
    entity_names: str            # the name as spoken
    start: int
    end: int
    county: bool = False
    qualifier_after: str = ""    # ", Texas" / ", Maine, USA": explicit parent words


def _mentions(raw: str, index: Dict[str, List[Entity]]) -> List[Mention]:
    out: List[Mention] = []
    for m in _SPAN.finditer(raw):
        words = list(re.finditer(r"\S+", m.group(0)))
        i = 0
        while i < len(words):
            hit = None
            for j in range(min(len(words), i + 5), i, -1):
                phrase = raw[m.start() + words[i].start(): m.start() + words[j - 1].end()].rstrip(".,;:")
                if phrase.lower() in ("the", "and", "of", "de", "la", "del"):
                    continue
                poss = re.sub(r"['’]s$", "", phrase)               # "Canada's": the place, then a possessive the sentence check looks at
                if fold(phrase) in index or (poss != phrase and fold(poss) in index):
                    key = fold(phrase) if fold(phrase) in index else fold(poss)
                    if len(key) <= 4 and not phrase.isupper() and not any(fold(e.name) == key for e in index[key]):
                        continue          # a short alias in ordinary writing ("Port" is not Portugal, "Arm" is not Armenia); "USA" and "UK" are written in capitals
                    hit = (j, phrase if fold(phrase) in index else poss)
                    break
            if hit:
                j, phrase = hit
                s = m.start() + words[i].start()
                e = s + len(phrase)
                cw = _COUNTY_WORD.match(raw[e:])
                mm = Mention(phrase, s, e + (cw.end() if cw else 0), county=bool(cw))
                out.append(mm)
                i = j
            else:
                i += 1
    return out


def _explicit_parent(raw: str, mention: Mention, index: Dict[str, List[Entity]]) -> Tuple[str, int]:
    """", Texas" / ", Maine" right after the mention: the words of the parent and where they end."""
    m = re.match(rf"\s*,\s*({_CAP}(?:\s+{_CAP}){{0,2}})", raw[mention.end:])
    if not m:
        return "", mention.end
    cand = m.group(1)
    for n in range(len(cand.split()), 0, -1):
        words = " ".join(cand.split()[:n])
        if fold(words) in index and any(e.kind in ("admin1", "country") for e in index[fold(words)]):
            return words, mention.end + m.start(1) + len(words)
    return "", mention.end


_TRIVIAL = ("only possessive", "is a part of the place", "named only as a description", "mentioned in passing", "highlighted a moment ago", "the plan already outlines")


@dataclass
class Skipped:
    place: str
    reason: str
    t: float = 0.0

    @property
    def notable(self) -> bool:
        """Worth telling the author (a place that was discussed but could not be outlined), as opposed to a mention that was never a focus."""
        return not any(self.reason.startswith(x) or x in self.reason for x in _TRIVIAL)


@dataclass
class FocusResult:
    events: List[Dict[str, Any]] = field(default_factory=list)
    skipped: List[Skipped] = field(default_factory=list)
    credits: List[str] = field(default_factory=list)


# ---- resolving a mention to one place -----------------------------------------------------------------------------------------------------
def _candidates(m: Mention, index: Dict[str, List[Entity]]) -> List[Entity]:
    allc = index.get(fold(m.entity_names), [])
    if m.county:
        return [e for e in allc if e.kind == "county"]
    c = [e for e in allc if e.kind != "county"]                  # a county is meant only when the narration says "County" (or "Parish")
    big = [e for e in c if e.kind in ("country", "admin1") or e.pop > SMALL_TOWN]
    if any(e.kind in ("country", "admin1") for e in c):
        c = big                                                    # "Florida" the state, not a town of that name (as pakmap/geo.py does)
    c = [e for e in c if not (e.kind == "admin1" and any(o.kind == "country" and o.iso == e.iso for o in c))]   # "Panama": the country, not its province
    return c


def _evidence(raw_sentences: Sequence[str], index: Dict[str, List[Entity]], skip: Optional[Tuple[str, int]] = None) -> Dict[Tuple[str, ...], int]:
    """What the script says about where it is: the countries and states of every place it names without ambiguity."""
    ev: Dict[Tuple[str, ...], int] = {}
    for si, raw in enumerate(raw_sentences):
        for m in _mentions(raw, index):
            _add_evidence(ev, _candidates(m, index), +1)
    return ev


def _add_evidence(ev: Dict[Tuple[str, ...], int], c: List[Entity], sign: int) -> None:
    """A place named without ambiguity says where the script is (its country and state); a name shared only by places of one country (a city and the
    region around it) still says which country, though not which of the two is meant."""
    if len(c) == 1:
        keys = c[0].supports()
    elif c and len({e.iso for e in c}) == 1 and c[0].iso:
        keys = [("country", c[0].iso)]
    else:
        return
    for k in keys:
        ev[k] = ev.get(k, 0) + sign
        if ev[k] <= 0:
            ev.pop(k, None)


def _supported(e: Entity, evidence: Dict[Tuple[str, ...], int], explicit: str, index) -> bool:
    if explicit:
        for p in index.get(fold(explicit), []):
            if p.kind == "admin1" and e.kind in ("county", "city") and fold(e.state) == fold(p.name) and (not p.iso or p.iso == e.iso):
                return True
            if p.kind == "admin1" and e.kind == "admin1" and p.iso == e.iso:
                return True
            if p.kind == "country" and p.iso == e.iso:
                return True
        return False
    return any(k in evidence for k in e.supports())


def resolve(m: Mention, raw: str, index: Dict[str, List[Entity]], evidence: Dict[Tuple[str, ...], int]) -> Tuple[Optional[Entity], str, str]:
    """-> (entity, how it was decided, or why not)."""
    c = _candidates(m, index)
    if not c:
        return None, "", f"{m.entity_names!r} is not a place with a boundary the app knows"
    explicit, _end = _explicit_parent(raw, m, index)
    if explicit:
        sup = [e for e in c if _supported(e, evidence, explicit, index)]
        if len(sup) == 1:
            return sup[0], f"named as {m.entity_names}, {explicit}", ""
        if len(sup) > 1:
            return None, "", f"{m.entity_names}, {explicit} still matches {len(sup)} places"
        return None, "", f"{m.entity_names} is not in {explicit}"
    if len(c) == 1:
        e = c[0]
        if e.kind != "city" or e.pop >= BIG_CITY:
            return e, "the only place of that name" if e.kind != "city" else "a city of over a million that no other city of 10,000 shares a name with", ""
        if _supported(e, evidence, "", index):
            return e, "the script names other places in the same country", ""
        return None, "", f"{m.entity_names} could be other towns of that name and nothing in the script says which: name the state or country"
    sup = [e for e in c if _supported(e, evidence, "", index)]
    if len(sup) == 1:
        return sup[0], "decided by the other places the script names", ""
    names = ", ".join(f"{e.name} ({e.country or e.state})" if e.kind in ("country", "admin1") else f"{e.name} ({e.state}, {e.country})" for e in c[:4])
    return None, "", f"{m.entity_names} is ambiguous ({names}) and the script does not say which"


# ---- is the sentence about it? -----------------------------------------------------------------------------------------------------------
def discusses(raw: str, m: Mention, parent_end: int) -> Tuple[bool, str]:
    before, after = raw[: m.start], raw[m.end:]
    if _POSSESSIVE.match(after):
        return False, "only possessive (its coast, its mayor), not the place itself"
    if _QUAL_AFTER.match(after):
        return False, f"{m.entity_names} {after.split()[0].strip('.,;:')} is a part of the place, not its boundary"
    if _QUAL_BEFORE.search(before):
        return False, f"{before.split()[-1]} {m.entity_names} is a part of the place, not its boundary"
    if _APPOSITIVE_TAIL.search(before):
        return False, "named only as a description of something else"
    if _CUE.search(before):
        return True, "location or motion cue"
    if not before.strip() and _SUBJECT_VERB.match(after.lstrip(", ")):
        return True, "subject of the sentence"
    if _SUBJECT_VERB.match(after) and re.search(r"(?i)\b(?:say|says|said|that|warn|warns|warned|expect|expects|expected|report|reports|reported)\s+(?:the\s+)?$", before):
        return True, "subject of a reported clause"
    if re.match(r"^[\"“]?\s*$", before) and _SUBJECT_VERB.match(raw[parent_end:]):
        return True, "subject of the sentence"
    return False, "mentioned in passing (no location or motion cue, not the subject)"


# ---- the planner -------------------------------------------------------------------------------------------------------------------------
def _overlap(a0: float, a1: float, wins: Sequence[Tuple[float, float]]) -> float:
    return sum(max(0.0, min(a1, y) - max(a0, x)) for x, y in wins)


def _bbox_iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def focus_events(words: Sequence[Tuple[str, float, float]], *, existing_events: Sequence[Dict[str, Any]] = (), footage: Sequence[Tuple[float, float]] = (),
                 store: Optional[BS.BoundaryStore] = None, id_prefix: str = "focus", total: Optional[float] = None,
                 script: Optional[str] = None) -> FocusResult:
    """Boundary highlights for the places the narration discusses. `existing_events` are the plan's own events (a place the plan already outlines is not
    outlined again); `footage` the windows of full-screen footage that hides the map; `store` the city-boundary lookup (planning only)."""
    import gfx_templates as G

    res = FocusResult()
    words = G.display_words(words, script)
    sents = G.sentences(words)
    toks = G._sentence_tokens(words)
    raws = [s[0] for s in sents]
    index = _index()
    store = store or BS.BoundaryStore(iso_of_name=iso_of_country_name, network=os.environ.get("VIDEOGEN_BOUNDARY_NETWORK", "1") != "0")
    evidence_all = _evidence(raws, index)
    # focus list in time order: (t, sentence end, entity, polys/iso, meta)
    picks: List[Dict[str, Any]] = []
    last_t = -1e9
    for si, (raw, a, b) in enumerate(sents):
        ctx = G._Ctx(None, sents, si, raw, toks[si] if si < len(toks) else [])
        consumed_to = -1
        for m in _mentions(raw, index):
            if m.start < consumed_to:
                continue                                           # the ", Texas" of "Houston, Texas": evidence for the city, not a place on its own
            _exp, parent_end = _explicit_parent(raw, m, index)
            if _exp:
                consumed_to = parent_end
            ok, why = discusses(raw, m, parent_end)
            if ok and not raw[: m.start].strip() and fold(m.entity_names) in _COMMON_WORDS and fold(m.entity_names) not in {fold(c.name) for c in _candidates(m, index) if c.kind == "country"}:
                ok, why = False, "mentioned in passing (a common word at the start of a sentence)"
            t = ctx.time_at(m.start)
            if not ok:
                if _candidates(m, index):
                    res.skipped.append(Skipped(m.entity_names, why, t))
                continue
            # evidence: the places named elsewhere, without this mention's own contribution
            ev = dict(evidence_all)
            for mm in _mentions(raw, index):
                _add_evidence(ev, _candidates(mm, index), -1)
            ent, how, why = resolve(m, raw, index, ev)
            if ent is None:
                res.skipped.append(Skipped(m.entity_names, why, t))
                continue
            if t - last_t < MIN_APART_S and picks and picks[-1]["si"] == si:
                res.skipped.append(Skipped(m.entity_names, "another place in the same sentence is highlighted a moment earlier", t))
                continue
            picks.append({"si": si, "t": t, "end": b, "ent": ent, "how": how, "word": m.entity_names, "counties": m.county})
            last_t = t
    # one event per focus: a place discussed again in the next sentence keeps the same outline; a new place replaces it
    events: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    recent: Dict[Tuple[str, str, str], float] = {}
    existing = [e for e in existing_events if e.get("type") == "fill"]
    for p in picks:
        ent: Entity = p["ent"]
        t0 = max(p["t"] - LEAD_S, sents[p["si"]][1])
        t1 = min(p["end"] + TAIL_S, t0 + MAX_SHOW_S)
        if current and current["ent"].key == ent.key and t0 <= current["event"]["t_out"] + 1.5:
            current["event"]["t_out"] = round(max(current["event"]["t_out"], min(p["end"] + TAIL_S, current["event"]["t_in"] + MAX_SHOW_S)), 3)
            continue
        if recent.get(ent.key, -1e9) > t0 - SAME_ENTITY_GAP_S:
            res.skipped.append(Skipped(p["word"], "highlighted a moment ago", p["t"]))
            continue
        t1 = max(t1, t0 + MIN_SHOW_S)
        if total is not None:
            t1 = min(t1, total)
        if t1 - t0 < 2.0:
            res.skipped.append(Skipped(p["word"], "no time left in the video", p["t"]))
            continue
        if footage and _overlap(t0, t1, footage) >= 0.7 * (t1 - t0):
            res.skipped.append(Skipped(p["word"], "the narration is over full-screen footage that hides the map", p["t"]))
            continue
        geo = _geometry(ent, store, res)
        if geo is None:
            continue
        if _already_outlined(ent, geo, existing, t0, t1):
            res.skipped.append(Skipped(p["word"], "the plan already outlines it", p["t"]))
            continue
        if current:
            current["event"]["t_out"] = round(min(current["event"]["t_out"], t0 + 0.3), 3)       # the new focus takes over (the old one fades as the new one comes in)
        ev = {"id": f"{id_prefix}_{len(events) + 1}_{re.sub(r'[^a-z0-9]+', '_', fold(ent.name))}", "type": "fill", "color": FOCUS_COLOR, "outline_color": FOCUS_COLOR,
              "opacity": FOCUS_OPACITY, "fade_in": FOCUS_FADE_IN, "t_in": round(t0, 3), "t_out": round(t1, 3), **geo["geom"],
              "geo_focus": {"entity": ent.name, "kind": ent.kind, "country": ent.iso, "state": ent.state, "source": geo["source"], "decided": p["how"],
                            "confidence": geo["confidence"], "official_warning": False, **({"osm": geo["osm"]} if geo.get("osm") else {})}}
        events.append(ev)
        current = {"ent": ent, "event": ev}
        recent[ent.key] = t1
        if geo.get("credit") and geo["credit"] not in res.credits:
            res.credits.append(geo["credit"])
    res.events = events
    return res


def _geometry(ent: Entity, store: BS.BoundaryStore, res: FocusResult) -> Optional[Dict[str, Any]]:
    if ent.kind == "country":
        return {"geom": {"iso": [ent.iso]}, "source": "app country outline", "confidence": "exact", "bbox": None}
    if ent.kind in ("admin1", "county"):
        polys = polygons_of(ent)
        if not polys:
            res.skipped.append(Skipped(ent.name, "the app's boundary data has no polygon for it"))
            return None
        return {"geom": {"polys": polys}, "source": "app boundary data (Natural Earth states/provinces)" if ent.kind == "admin1" else "app boundary data (US counties)", "confidence": "exact"}
    r = store.lookup(BS.CityQuery(ent.name, ent.country, ent.iso, ent.lon, ent.lat, ent.state))
    if not r.ok:
        res.skipped.append(Skipped(ent.name, f"no confirmed city boundary: {r.reason}"))
        return None
    return {"geom": {"polys": r.polys}, "source": "OpenStreetMap" + (" (cached)" if r.from_cache else ""), "confidence": "validated",
            "osm": f"{r.osm_type}/{r.osm_id}", "credit": BS.ATTRIBUTION}


def _already_outlined(ent: Entity, geo: Dict[str, Any], existing: Sequence[Dict[str, Any]], t0: float, t1: float) -> bool:
    for e in existing:
        if not (e["t_in"] < t1 and t0 < e["t_out"]):
            continue
        if ent.kind == "country" and ent.iso in (e.get("iso") or []):
            return True
        polys = geo["geom"].get("polys")
        if polys and e.get("polys"):
            try:
                if _bbox_iou(BS.bbox_of(polys), BS.bbox_of(e["polys"])) > 0.9:
                    return True
            except Exception:
                pass
    return False


# ---- framing: bring an outline the camera cannot show into view -----------------------------------------------------------------------------
FRAME_SAFE = 0.08                # an outline must sit this far (fraction of the frame) inside every edge, plus the idle drift, to count as visible
FRAME_MIN_W = 0.06               # ... and be at least this wide (fraction of the frame width) to be seen at all
FRAME_PAD = 0.25                 # room around the outline when the camera is moved to it
FRAME_MAX_ZOOM = 9.0             # a small town is framed with its surroundings (checked on a render: zoom 8 is muddy and tiny, 9 is crisp and legible)
FRAME_MAX_OUT = 2.0              # zoom levels the camera may pull back for a large region; a bigger one is left as it is
FRAME_LEAD_S = 0.8               # the move starts this long before the outline
FRAME_DUR_S = 1.2
FRAME_CHAIN_S = 2.5              # outlines closer together than this share one move: no return in between


def _world(lon: float, lat: float) -> Tuple[float, float]:
    import math

    s = math.sin(math.radians(max(-85.0, min(85.0, lat))))
    return (lon + 180.0) / 360.0, 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)


def _view_box(box, cam: Tuple[float, float, float], width: int, height: int) -> Tuple[float, float, float, float]:
    """Pixel box (x0, y0, x1, y1) of a (west, south, east, north) box under a camera (lon, lat, zoom)."""
    k = 512.0 * 2.0 ** cam[2]
    cx, cy = _world(cam[0], cam[1])
    (x0, y1), (x1, y0) = _world(box[0], box[1]), _world(box[2], box[3])
    return (width / 2 + (x0 - cx) * k, height / 2 + (y0 - cy) * k, width / 2 + (x1 - cx) * k, height / 2 + (y1 - cy) * k)


def _inside(px, width: int, height: int, drift_px: float) -> bool:
    """The whole box sits inside the safe margins (this alone decides whether a fitted view works: a narrow small town is fine)."""
    mx, my = FRAME_SAFE * width + drift_px, FRAME_SAFE * height + drift_px
    return px[0] >= mx and px[2] <= width - mx and px[1] >= my and px[3] <= height - my


def _shown(px, width: int, height: int, drift_px: float) -> bool:
    """Already visible enough that no move is needed: inside the safe margins and wide enough to see."""
    return _inside(px, width, height, drift_px) and (px[2] - px[0]) >= FRAME_MIN_W * width


def _unworld(x: float, y: float) -> Tuple[float, float]:
    import math

    n = math.pi - 2 * math.pi * y
    return x * 360.0 - 180.0, math.degrees(math.atan(0.5 * (math.exp(n) - math.exp(-n))))


def _fly_zoom(a: Tuple[float, float, float], b: Tuple[float, float, float], view_px: float):
    """Zoom along the engine's fly_to path (pakmap-engine/lib/camera.mjs flyPath, van Wijk & Nuij) as a function of k in 0..1.
    a and b are (world x, world y, zoom)."""
    import math

    rho = 1.42
    rho2 = rho * rho
    u1 = math.hypot(b[0] - a[0], b[1] - a[1]) * 512.0 * 2.0 ** a[2]
    w0 = view_px
    w1 = w0 / 2.0 ** (b[2] - a[2])
    if u1 < 1e-9:
        if abs(a[2] - b[2]) < 1e-12:
            return lambda k: a[2]
        sign = -1.0 if w1 < w0 else 1.0
        S = abs(math.log(w1 / w0)) / rho
        return lambda k: a[2] + math.log2(1.0 / math.exp(sign * rho * k * S))

    def r(i):
        bb = (w1 * w1 - w0 * w0 + (-1 if i else 1) * rho2 * rho2 * u1 * u1) / (2 * (w1 if i else w0) * rho2 * u1)
        return math.log(math.sqrt(bb * bb + 1) - bb)

    r0 = r(0)
    S = (r(1) - r0) / rho
    return lambda k: a[2] + math.log2(math.cosh(r0 + rho * k * S) / math.cosh(r0))


def _drift_since(a, b, t0: float, dur: float, t_eval: float, drift: Dict[str, Any], width: int, height: int) -> Tuple[float, float]:
    """World-unit drift the engine has added between the start of a move (a -> b, from t0 for dur seconds) and t_eval: this is where the camera
    sits relative to the move's target (the idle drift runs at a constant pixel speed, so it moves the map further at low zoom)."""
    import math

    pct = float(drift.get("pct_per_s", 0) or 0)
    if pct <= 0 or t_eval <= t0:
        return 0.0, 0.0
    h0 = math.radians(float(drift.get("heading_deg", 90)))
    turn = math.radians(float(drift.get("turn_deg_per_s", 0) or 0))
    zoom_at = _fly_zoom(a, b, float(max(width, height)))
    ox = oy = 0.0
    step = 1.0 / 120.0
    n = int(math.ceil((t_eval - t0) / step))
    for i in range(n):
        t = t0 + i * step
        k = min(1.0, (t - t0) / dur) if dur > 0 else 1.0
        e = 4 * k ** 3 if k < 0.5 else 1 - (-2 * k + 2) ** 3 / 2     # the engine's inOut easing
        z = zoom_at(e) if t < t0 + dur else b[2]
        v = pct / 100.0 * width / (512.0 * 2.0 ** z)
        th = h0 + turn * t
        dt = min(step, t_eval - t)
        ox += math.sin(th) * v * dt
        oy -= math.cos(th) * v * dt
    return ox, oy


def _camera_at(camera: Dict[str, Any], t: float) -> Optional[Tuple[float, float, float]]:
    """The planned camera (lon, lat, zoom) at t, or None while one of the script's own moves is under way."""
    s = camera["start"]
    cur = (s["lon"], s["lat"], s["zoom"])
    for m in camera.get("moves", []):
        if t < m["t"]:
            break
        if t < m["t"] + m["dur"]:
            return None
        to = m.get("to", {})
        cur = (to.get("lon", cur[0]), to.get("lat", cur[1]), to.get("zoom", cur[2]))
    return cur


def frame_camera(camera: Dict[str, Any], events: Sequence[Dict[str, Any]], authored: bool, total: float, width: int, height: int) -> List[str]:
    """Move the camera so each boundary outline (an event tagged `geo_focus`) is in view while it shows, then back to where it was.
    `authored` is True when the script has camera rows of its own: then nothing is moved and a note says which outlines are not fully in view.
    Appends `fly_to` moves to camera["moves"]; touches no event (so no warning polygon or style); never raises a camera-spacing error.
    Returns plan warnings."""
    from pakmap.geo import fit

    notes: List[str] = []
    foc = sorted((e for e in events if e.get("geo_focus") and e.get("polys") and not e["geo_focus"].get("official_warning")), key=lambda e: e["t_in"])
    if not foc:
        return notes
    drift = (camera.get("drift") or {}).get("pct_per_s", 0) or 0
    base = _camera_at(camera, 0.0) if not authored else None
    prev_end = 0.0                                       # when our last move ends
    at_focus = False                                     # the camera is currently on a fitted view
    last_t_out = -1e9
    last = None                                          # the last fitted move: where it started from and aimed
    moves = camera.setdefault("moves", [])
    for i, e in enumerate(foc):
        name, t0, t1 = e["geo_focus"].get("entity", "a place"), e["t_in"], e["t_out"]
        try:
            box = BS.bbox_of(e["polys"])
            if not all(v == v and abs(v) < 1e9 for v in box) or box[2] <= box[0] or box[3] <= box[1] or box[2] - box[0] > 180 or box[3] > 85:
                raise ValueError("no usable extent")
        except Exception:
            notes.append(f"place focus: {name} not framed: its outline has no usable extent")
            continue
        cam = _camera_at(camera, t0) if (authored or not at_focus) else None
        if authored:
            if cam is not None:
                px = _view_box(box, cam, width, height)
                if not _shown(px, width, height, drift / 100.0 * width * t1):
                    notes.append(f"place focus: {name} is not fully in view of your camera at {t0:.1f}s (the camera was left as written)")
            continue
        dcfg = camera.get("drift") or {}
        view = cam
        if at_focus and last is not None:               # a previous outline is still framed: where the camera really is now (landing plus drift)
            ox, oy = _drift_since(last["a"], last["to"], last["t"], last["dur"], t0, dcfg, width, height)
            lon, lat = _unworld(last["to"][0] + ox, min(0.9999, max(0.0001, last["to"][1] + oy)))
            view = (lon, lat, last["to"][2])
        if view is None or _shown(_view_box(box, view, width, height), width, height, 0.0 if at_focus else drift / 100.0 * width * t1):
            continue
        cx, cy, z = fit((box[0], box[1], box[2], box[3]), width, height, FRAME_PAD, 1.5, FRAME_MAX_ZOOM)
        if z < base[2] - FRAME_MAX_OUT:
            notes.append(f"place focus: {name} is too large to frame ({FRAME_MAX_OUT:g}+ zoom levels out); the camera was left as it is")
            continue
        start = max(t0 - FRAME_LEAD_S, prev_end + 0.05, 0.0)
        dur = min(FRAME_DUR_S, max(0.0, t0 + 0.4 - start))
        if dur < 0.5 or start + dur > total:
            notes.append(f"place focus: {name} not framed: no time to move the camera")
            continue
        # the engine's idle drift moves the map while the camera flies in (further, in map units, the lower the zoom), so a move lands off its
        # target by more the closer it zooms: aim so that the outline is centred in the middle of its showing, then check the whole showing
        prev = moves[-1]["to"] if moves else {"lon": base[0], "lat": base[1], "zoom": base[2]}
        a_w = (*_world(prev["lon"], prev["lat"]), prev["zoom"])
        c_w = _world(cx, cy)
        t_in_view = max(t0, start + dur)
        t_mid = (t_in_view + t1) / 2
        tx, ty = c_w
        for _ in range(4):
            ox, oy = _drift_since(a_w, (tx, ty, z), start, dur, t_mid, dcfg, width, height)
            tx, ty = c_w[0] - ox, min(0.9999, max(0.0001, c_w[1] - oy))
        to_w = (tx, ty, z)
        fits = True
        for tt in (t_in_view, t_mid, t1):
            ox, oy = _drift_since(a_w, to_w, start, dur, tt, dcfg, width, height)
            lon, lat = _unworld(tx + ox, min(0.9999, max(0.0001, ty + oy)))
            fits = fits and _inside(_view_box(box, (lon, lat, z), width, height), width, height, 0.0)   # containment only: a narrow small town is fine
        if not fits:
            notes.append(f"place focus: {name} cannot be framed: its outline does not stay inside the frame at zoom {z:g}; the camera was left as it is")
            continue
        tlon, tlat = _unworld(tx, ty)
        moves.append({"type": "fly_to", "t": round(start, 3), "dur": round(dur, 3), "to": {"lon": round(tlon, 4), "lat": round(tlat, 4), "zoom": round(z, 3)}})
        last = {"a": a_w, "to": to_w, "t": round(start, 3), "dur": round(dur, 3)}
        prev_end, at_focus, last_t_out = start + dur, True, t1
        nxt = foc[i + 1]["t_in"] if i + 1 < len(foc) else 1e9
        if nxt - t1 >= FRAME_CHAIN_S:                    # back to the shot it was
            rdur = min(FRAME_DUR_S, nxt - FRAME_LEAD_S - t1 - 0.05, total - t1)
            if rdur >= 0.5:
                moves.append({"type": "fly_to", "t": round(t1, 3), "dur": round(rdur, 3), "to": {"lon": base[0], "lat": base[1], "zoom": base[2]}})
                prev_end, at_focus = t1 + rdur, False
    return notes
