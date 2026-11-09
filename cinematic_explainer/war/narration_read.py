"""War Footage Director, Stage 1: what a narration scene SAYS, as data the footage search and the graphics can both act on.

docs/war/FOOTAGE_DIRECTOR_PLAN.md (Part B). Deterministic rules on top of semantics.analyze_scene and the War catalogues; no network, no models.

    read(text, prev=None) -> Reading

Sentence types (a scene can carry several):
    EVENT       something happened to something concrete: a strike on a facility or place, a shutdown / halt / ban / seizure of a named
                place, a visible civilian scene (queues at petrol stations, blackouts), an actor country doing it ("Russia is hitting back")
    LOCATION    a specific place or site is named (a refinery, a town, an air base; a country alone is not a location)
    MOVEMENT    forces / ships / trains moving, advancing, attacking near, retreating, changing course, importing by rail from ...
    SUBJECT     a concrete thing the sentence is about (equipment, a facility class) without a place
    CLAIM       somebody says / reports / counts / assesses it
    STATISTIC   a figure: a number with a referent, a percent, a fraction ("a fourth of capacity"), an area
    ANALYSIS    an evaluation or a conclusion ("so the picture is ...", "far from decided"); also what is left when nothing else fits
    QUESTION    a question
    TRANSITION  a structure line ("First, ...", "There are three parts ...") or the outro ("Subscribe ...")

A tally is not an event: "counted 11 such strikes", "seized 104.5 square kilometres", "had not been hit" carry no footage of their own.
footage_wanted is true only for EVENT, LOCATION, MOVEMENT and SUBJECT. Graphics are planned for every sentence (graphic_intents).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

FOOTAGE_TYPES = ("EVENT", "LOCATION", "MOVEMENT", "SUBJECT")
TYPES = ("EVENT", "LOCATION", "MOVEMENT", "SUBJECT", "CLAIM", "STATISTIC", "ANALYSIS", "QUESTION", "TRANSITION")
SIDES = {"Ukraine": ("ukraine", "ukraine's", "ukrainian", "ukrainians", "kyiv", "kyiv's", "kiev"),
         "Russia": ("russia", "russia's", "russian", "russians", "moscow's", "kremlin")}
COUNTRIES = ("Ukraine", "Russia", "Belarus", "Poland", "Romania", "Moldova", "Turkey", "Georgia", "Germany", "France", "Finland", "Estonia",
             "Latvia", "Lithuania", "Hungary", "Slovakia", "Bulgaria", "Kazakhstan", "Iran", "China", "United States", "US", "United Kingdom",
             "UK", "North Korea", "Israel", "Syria")
OUTLETS = ("Reuters", "AP", "AFP", "BBC", "CNN", "ISW", "IEA", "DeepState", "Rosstat", "DTEK", "Financial Times", "FT", "Euromaidan Press",
           "Bloomberg", "Kyiv Independent", "Meduza", "Guardian", "New York Times", "Washington Post", "Wall Street Journal", "General Staff",
           "Pentagon", "Kremlin", "NATO", "UN", "IAEA", "Ukrinform", "TASS", "RIA", "Interfax")

_W = r"[A-Za-z][A-Za-z'’\-]*"
_KINETIC = re.compile(r"\b(struck|strike[sd]?|striking|hit|hits|hitting|attack(?:s|ed|ing)?|set\b[^.]{0,40}\bon fire|ablaze|explo(?:ded|sion|sions)|"
                      r"burn(?:ed|ing|s)?|bomb(?:ed|ing|s)?|shell(?:ed|ing)|shot down|downed|destroy(?:ed|s)?|damag(?:ed|ing)|fired|launch(?:ed|es)|"
                      r"pound(?:ed|ing)|torched|drone attack|missile attack|assaults?)\b", re.I)
_STATE = re.compile(r"\b(shut down|shut|halted|halt|offline|banned|bans?|seized|captured|cleared|freed|liberated|changed course|rerouted|"
                    r"sank|sunk|evacuated|stopped|suspended|closed)\b", re.I)
_MOVE = re.compile(r"\b(advanc(?:e|es|ed|ing)|push(?:ed|ing|es)?|attacking near|assaults? near|kept attacking|retreat(?:ed|ing|s)?|withdr[ae]w|"
                   r"pulled back|changed course|rerouted|heading (?:to|toward|for)|toward|towards|import(?:ing|ed|s)? [^.]{0,40}\bby (?:rail|sea|truck|pipeline)|"
                   r"by rail from|convoy|moved|moving|cross(?:ed|ing))\b", re.I)
_VISIBLE = re.compile(r"\b((?:queue|queues|line|lines|wait(?:ed|ing)?)\b[^.]{0,60}\b(?:station|stations|pumps?|shops?|stores?)|blackouts?|power cuts?|"
                      r"evacuat\w+|refugees|protest(?:s|ers|ed)?|funeral|rubble|wreckage)\b", re.I)
_TALLY = re.compile(r"\b(counted|tallied|estimated|calculated|recorded|square kilometers|square kilometres|sq km|km2|km²)\b", re.I)
_NEG = re.compile(r"\b(no|not|never|without|n't)\b[^.]{0,30}$", re.I)
_CLAIM = re.compile(r"\b(says?|said|saying|report(?:s|ed)?|noted|notes|claim(?:s|ed)?|counted|assess(?:ed|es)|estimat(?:es|ed)|according to|"
                    r"show(?:s|ed)|announced|told|stated|denied|warned|accused|called|blamed|insisted|admitted)\b", re.I)
_QUESTION_END = re.compile(r"\?\s*$")
_ORDINAL = re.compile(r"^\s*(first|second|third|fourth|fifth|finally|next|lastly|last|to start|to begin|meanwhile)\b[,:]", re.I)
_PARTS = re.compile(r"\b(there are (?:two|three|four|five) (?:parts|reasons|things|questions|answers)|the answer has|here is why)\b", re.I)
_OUTRO = re.compile(r"\b(subscribe|in the comments|tell me what you think|like and share|see you (?:next|in))\b", re.I)
_ANALYSIS = re.compile(r"^\s*(so|still|yet|but|overall|in short|that means|which means)\b|\b(the picture is|far from decided|the evidence|conclusion|"
                       r"real and costly|which is still|matters because|the point is|in other words)\b", re.I)
_NUMBER = re.compile(r"\b(\d[\d,.]*\s*(?:%|percent|per cent)|\d[\d,.]*\s+(?:" + _W + r")|(?:one|two|three|four|five|six|seven|eight|nine|ten|"
                     r"eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand|million|billion)\s+(?:of\s+)?(?:" + _W + r"))", re.I)
_FRACTION = re.compile(r"\b(a (?:third|fourth|quarter|fifth|half)|half of|two thirds|three quarters)\b", re.I)
# a month is a capitalised whole word ('marched on Moscow' is no March, 'Russia may' is no May)
_MONTH = r"(?-i:January|February|March|April|May|June|July|August|September|October|November|December)\b"
_DATE = re.compile(r"\b((?:on |in |since |by |to |until |from )?(?:early |late |mid-?)?" + _MONTH +
                   r"(?: \d{1,2}\b(?:\s*(?:and|-|–)\s*\d{1,2})?)?(?:,? (?:19|20)\d\d)?|(?:the )?(?:summer|winter|spring|autumn|fall) of (?:19|20)\d\d|"
                   r"overnight|last night|this week|this year|\b(?:19|20)\d\d\b)", re.I)
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
# 'the largest warship lost in combat since 1982' compares with a past year: it is not when the story happens (Moskva 2026-11-09: it stretched
# the story period back to 1982, so a 2024 Odesa clip passed the date check)
_COMPARISON_YEAR = re.compile(r"\b(?:largest|biggest|first|worst|most|deadliest|heaviest|longest|highest|lowest|greatest|only|last)\b[^.]*?"
                              r"\bsince\s+(?:the\s+)?(?:\w+\s+)?(?:19|20)\d\d\s*$", re.I)
_REL_DATE = {"the next day": 1, "a day later": 1, "the following day": 1, "two days later": 2, "days later": 3, "a week later": 7,
             "the next week": 7, "weeks later": 21, "a month later": 30, "the following month": 30, "months later": 90, "a year later": 365,
             "the following year": 365}
# who a name stands for when a catalogue does not know it (subject position decides the actor)
NAME_SIDE = {"wagner": "Russia", "prigozhin": "Russia", "putin": "Russia", "shoigu": "Russia", "gerasimov": "Russia", "kadyrov": "Russia",
             "peskov": "Russia", "lavrov": "Russia", "belousov": "Russia", "surovikin": "Russia", "akhmat": "Russia", "rosgvardia": "Russia",
             "zelensky": "Ukraine", "zelenskyy": "Ukraine", "syrskyi": "Ukraine", "zaluzhnyi": "Ukraine", "budanov": "Ukraine", "azov": "Ukraine",
             "umerov": "Ukraine", "kuleba": "Ukraine", "sybiha": "Ukraine", "kyrylo budanov": "Ukraine"}
_ACTION = re.compile(r"\b(visited|toured|gave|handed|presented|recruited|stood|marched|retook|retaken|recaptured|took|taken|entered|crossed|landed|"
                     r"fought|defended|stormed|surrounded|encircled|withdrew|evacuated|executed|mobili[sz]ed|signed|met|arrived|flew|began|begun|"
                     r"started|ended|lasted|captured|seized|attacked|blamed|raided|ambushed|shot|sank|blew up|occupied)\b", re.I)
_GROUP_SUBJ = re.compile(r"^\s*(?:\w+,\s*)?(?:the\s+)?(?:Ukrainian|Russian|Wagner|local|its|his|their)?\s*(soldiers|troops|fighters|residents|"
                         r"civilians|prisoners|volunteers|crews|sailors|refugees|marines|paratroopers|convicts|mercenaries|men)\b", re.I)
_BATTLE_SUBJ = re.compile(r"^\s*(?:\w+,\s*)?the (battle|siege|fighting|offensive|counteroffensive|assault|war|invasion)\b", re.I)
_NATIONALITY = {"russians", "ukrainians", "americans", "russian", "ukrainian", "american", "british", "belarusian", "chechen", "polish", "german", "french", "iranian", "chinese",
                "korean", "north", "south", "western", "eastern"}
_FACILITY = re.compile(r"\b(refiner(?:y|ies)|oil depot|fuel depot|depots?|power plants?|power stations?|power lines?|substations?|grid|air ?bases?|airfields?|"
                       r"ports?|terminals?|bridges?|dams?|factory|factories|plants?|tankers?|ships?|vessels?|trains?|rail|pipeline|gas(?:oline)? stations?|"
                       r"petrol stations?|warehouse|equipment|distillation unit|units?|drones?|missiles?|tanks?|artillery|positions?|trenches?)\b", re.I)
_EVENT_NOUN = re.compile(r"\b(fire|strike|attack|explosion|shutdown|queue|repair|ban|exports?|imports?|advance|assault|offensive|retreat|blackout|"
                         r"evacuation|course)\b", re.I)
_PRONOUN_SUBJ = re.compile(r"^\s*(?:[\w ]{1,30},\s*)?(they|it|its|his|her|their|he|she)\b", re.I)
_TARGET_PREP = re.compile(r"\b(of|into|on|in|against|from|to|toward|towards|across|inside|over)\s*$", re.I)


@dataclass
class Place:
    name: str
    kind: str                 # site | city | region | unresolved
    country: str = ""
    site_type: str = ""


@dataclass
class Reading:
    text: str
    types: List[str]
    footage_wanted: bool
    places: List[Place] = field(default_factory=list)
    countries: List[str] = field(default_factory=list)
    actor: str = ""
    equipment: List[str] = field(default_factory=list)
    figures: List[str] = field(default_factory=list)
    speaker: str = ""
    outlet: str = ""
    date: str = ""
    event_nouns: List[str] = field(default_factory=list)
    facilities: List[str] = field(default_factory=list)
    key_terms: List[str] = field(default_factory=list)
    graphic_intents: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    names: List[str] = field(default_factory=list)            # people / organisations no catalogue knows (Prigozhin, Wagner Group, Congress)
    context_places: List[str] = field(default_factory=list)   # the story's place carried from earlier sentences ("the city")
    date_source: str = ""                  # stated (the sentence names it) | carried (an earlier sentence did) | relative ("a month later")

    @property
    def primary(self) -> str:
        return self.types[0] if self.types else "ANALYSIS"

    def as_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["places"] = [p.__dict__ for p in self.places]
        return d


def fold(text: Any) -> str:
    t = str(text or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")


def spelling_variants(name: str) -> List[str]:
    """Transliteration twins seen in war reporting: Hulyaipole / Huliaipole, Dobropillya / Dobropillia, Zaporizhia / Zaporizhzhia."""
    n = fold(name)
    out = {n}
    for a, b in (("ya", "ia"), ("yi", "i"), ("iy", "i"), ("zhzh", "zh"), ("y", "i")):
        for v in list(out):
            if a in v.lower():
                out.add(re.sub(a, b, v, flags=re.I))
    if "zhia" in n.lower() and "zhzh" not in n.lower():
        out.add(re.sub("zhia", "zhzhia", n, flags=re.I))
    return sorted(out, key=lambda x: (x != n, x))


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"“'])", str(text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _known_places(text: str) -> List[Place]:
    out: List[Place] = []
    seen = set()
    try:
        from .map_events import sites_in
        for _off, s in sites_in(text):
            if s["id"] not in seen:
                seen.add(s["id"])
                out.append(Place(s["name"], "site", s.get("country", ""), s.get("type", "")))
    except Exception:  # noqa: BLE001 - a missing catalogue only means fewer places
        pass
    site_words = " ".join(p.name for p in out).lower()
    try:
        from .catalog import find_place
        for m in find_place(text):
            e = m.entry or {}
            name = e.get("name") or m.matched_alias
            if not name or name.lower() in seen or (name.lower() in site_words and len(name) > 3):
                continue
            if (e.get("type") or "") == "country" or name in COUNTRIES:
                continue                                   # a country is a side, not a location
            ends = [mm.end() for mm in re.finditer(rf"\b{re.escape(m.matched_alias)}\b", text)]
            if ends and all(re.match(r"['’]s\s+(claim|government|forces|army|figure|office|view|position|account)", text[x:x + 20]) for x in ends):
                continue                                   # "Kyiv's claim": the government speaking, not the place
            seen.add(name.lower())
            out.append(Place(name, e.get("type") or "city", e.get("region", ""), ""))
    except Exception:  # noqa: BLE001
        pass
    return out


_CAP_SEQ = re.compile(r"\b([A-Z][a-z’'\-]+(?:\s+[A-Z][a-z’'\-]+){0,2})\b")
_NOT_PLACE = set(w.lower() for w in COUNTRIES + OUTLETS) | _NATIONALITY | {m for m in ("january february march april may june july august september october "
                                                                        "november december monday tuesday wednesday thursday friday saturday "
                                                                        "sunday").split()}
_PLACE_CUE = re.compile(r"\b(near|in|at|of|outside|around|cleared most of|southeast of|southwest of|northeast of|northwest of|north of|"
                        r"south of|east of|west of|towards?|from)\s*$", re.I)


def _unresolved_places(sentence: str, known: Sequence[Place], figures: Sequence[str]) -> List[Place]:
    """Proper names after a place cue that no catalogue knows (Mala Tokmachka, Borova): kept as places, never guessed on a map."""
    out = []
    taken = " ".join(p.name.lower() for p in known) + " " + " ".join(f.lower() for f in figures)
    for m in _CAP_SEQ.finditer(sentence):
        name = re.sub(r"['’]s$", "", m.group(1))
        if m.start() == 0 or name.lower() in _NOT_PLACE or name.lower().split()[0] in _NOT_PLACE or name.lower() in taken:
            continue
        before = sentence[:m.start()]
        # a list of places ("near Lyman, Borova, Hulyaipole and Dobropillya") keeps the cue of its first member
        if _PLACE_CUE.search(before) or (re.search(r"(,|\band)\s*$", before) and _PLACE_CUE.search(re.sub(r"(?:[A-Z][\w’'\-]+(?:,\s*|\s+and\s+))+$", "", before))):
            out.append(Place(name, "unresolved"))
    return out


_NAME_STOP = {"the", "so", "but", "in", "on", "by", "before", "after", "its", "his", "her", "their", "do", "tell", "there", "that", "this",
              "first", "second", "third", "fourth", "finally", "still", "yet", "overnight", "president", "prime", "minister", "general",
              "subscribe", "and", "a", "an", "it", "he", "she", "they", "we", "you", "i", "what", "why", "how", "where", "when", "who", "is"}


def _proper_names(sentence: str) -> List[str]:
    """Capitalised names that are not places, countries, outlets, months or sentence-openers: 'Yevgeny Prigozhin', 'Wagner Group', 'Congress'."""
    out = []
    for m in re.finditer(r"\b([A-Z][a-z’'\-]+(?:\s+[A-Z][a-z’'\-]+){0,2})\b", fold(sentence)):
        if m.start() == 0 and " " not in m.group(1) and m.group(1).lower() not in NAME_SIDE:
            continue                                   # 'Drones hit ...': a capital that only starts the sentence
        words = [w for w in re.sub(r"['’]s$", "", m.group(1)).split() if w.lower() not in _NAME_STOP]
        while words and (words[0].lower() in _NOT_PLACE or words[0].lower() in MONTHS):
            words.pop(0)
        while words and (words[-1].lower() in _NOT_PLACE or words[-1].lower() in MONTHS):
            words.pop()
        name = " ".join(words)
        if not name or name.lower() in _NOT_PLACE or name.lower() in _NAME_STOP or len(name) < 3:
            continue
        if name not in out:
            out.append(name)
    return out


_ROLE_BEFORE = re.compile(r"\b(blam(?:ed|es|ing)|accus(?:ed|es|ing)|criticis(?:ed|es)|criticiz(?:ed|es)|condemn(?:ed|s)|warned|urged|pressed|"
                          r"sanctions on|talks with|relations with|ties with|deal with|pressure on|support from|aid from|demands of|"
                          r"orders from|approval from|ally of|allies of|backed by|funded by|ordered by|according to)\s+(?:the\s+)?$", re.I)
_ROLE_AFTER = re.compile(r"^(?:['’]s)?\s+(?:says?|said|claim(?:s|ed)?|denied|denies|insist(?:s|ed)|announced|ordered|decided|demanded|"
                         r"warned|accused|blamed|responded|refused|agreed|threatened|government|officials?|leadership|authorities|"
                         r"military command|commanders?|generals|regime|response|position|claim)\b", re.I)


_REF_BEFORE = re.compile(r"\b(?:(?:north|south|east|west)(?:-?(?:east|west))?(?:ern)?\s+of|near|off|outside|close to|not far from|"
                         r"miles from|kilometres from|kilometers from|km from)\s+(?:the\s+)?(?:(?:coast|shore|port|city)\s+(?:of|near)\s+)?$", re.I)


def reference_only(text: str, name: str) -> bool:
    """The place is named only as a reference point for somewhere else ('struck the ship south of Odesa', 'the coast near Odesa'): the
    sentence is not about it, so footage that only names it is not footage of the sentence (Moskva 2026-11-09: Odesa strike clips)."""
    ms = list(re.finditer(rf"\b{re.escape(name)}\b", text or ""))
    return bool(ms) and all(_REF_BEFORE.search(text[:m.start()]) for m in ms)


def place_roles(text: str, name: str) -> List[str]:
    """How each mention of a place name is used: 'location' (where something is / happens) or 'actor' (a government speaking, deciding,
    being blamed: 'blamed Moscow', 'Moscow said', 'Kyiv's claim'). A place used only as an actor is not where the footage should be."""
    out = []
    for m in re.finditer(rf"\b{re.escape(name)}\b", text):
        before, after = text[:m.start()], text[m.end():m.end() + 40]
        out.append("actor" if (_ROLE_BEFORE.search(before) or _ROLE_AFTER.match(after)) else "location")
    return out


def _side_of(word: str) -> str:
    w = word.lower()
    for side, marks in SIDES.items():
        if w in marks:
            return side
    return ""


def _actor(sentence: str, places: Sequence[Place], prev_actor: str = "") -> str:
    """Who acts: an explicit side in subject position ('Russian forces kept attacking', 'Russia is hitting back', 'Ukraine says its drones'),
    else the side opposite the struck target's country ('drones set the Ryazan refinery on fire' -> Ukraine), else a pronoun's antecedent."""
    s = fold(sentence)
    for m in re.finditer(r"\b(Ukraine's|Ukraine|Ukrainian|Ukrainians|Kyiv's|Kyiv|Russia's|Russia|Russian|Russians|Moscow's|Kremlin)\b", s):
        before = s[:m.start()]
        if _TARGET_PREP.search(before):
            continue                               # "into Russia", "of Russia's oil": the target, not the actor
        after = s[m.end():m.end() + 40].lower()
        if re.fullmatch(r"\s*(?:(?:first|second|third|fourth|finally|then|still|but|and|so|yet|meanwhile|in [\w ]{3,20}),\s*)?", before, re.I) \
                and m.group(1) not in ("Moscow's",):
            return _side_of(m.group(1))           # the sentence's subject ("Ukraine denied it", "First, Russia banned ...")
        if re.match(r"\s*(forces|troops|army|military|drones|strikes|missiles|units|soldiers|navy|air force|says|said|claimed|is|has|had|was|"
                    r"kept|seized|banned|began|freed|cleared|launched|fired|struck|hit|attacked|gaining|losing|pushing|advanc|retreat|"
                    r"repair|import|captured)", after):
            # "Moscow's" alone is a city; only count it as the side when followed by forces/army
            if m.group(1) in ("Moscow's",) and not re.match(r"\s*(forces|troops|army|military)", after):
                continue
            return _side_of(m.group(1))
    low_s = s.lower()
    for name, side in sorted(NAME_SIDE.items(), key=lambda kv: -len(kv[0])):
        for m in re.finditer(rf"\b{re.escape(name)}\b", low_s):
            if _TARGET_PREP.search(low_s[:m.start()]) or re.search(r"\bwith\s*$", low_s[:m.start()]):
                continue                           # "paid for with Wagner": not the actor of this clause
            return side
    if _KINETIC.search(s):
        targets = [p.country for p in places if p.country in SIDES]
        if not targets:
            for side, marks in SIDES.items():
                for mk in marks:
                    if re.search(rf"\b(?:of|into|on|in|against|inside)\s+{re.escape(mk)}\b", s.lower()) or \
                            re.search(rf"\b{re.escape(mk)}\s+(refiner|oil|power|energy|depot|airbase|air base|port|city|cities|plant)", s.lower()):
                        targets.append(side)
        if targets:
            return "Ukraine" if targets[0] == "Russia" else "Russia"
    if _PRONOUN_SUBJ.search(s) and prev_actor:
        return prev_actor
    return ""


def _statistic(sentence: str) -> bool:
    s = re.sub(_DATE, " ", sentence)                    # 'November 5' or '2022' is a date, not a figure
    s = re.sub(r"\b(?:after|for|within|over|in)\s+(?:about\s+)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve)\s+"
               r"(?:days?|weeks?|months?|years?|hours?)\b", " ", s, flags=re.I)        # 'after six months': a duration, not a figure
    if _FRACTION.search(s):
        return True
    for m in _NUMBER.finditer(s):
        tok = m.group(1).lower()
        if re.match(r"^(one|two|three|four|five|six)\s+(parts|reasons|things|questions)", tok):
            continue
        if re.match(r"^(one|a)\s+of\b", tok):
            continue
        return True
    return False


def read(text: str, prev: Optional["Reading"] = None) -> Reading:
    from .catalog import find_equipment, find_figure
    sents = _sentences(text)
    types: List[str] = []
    reasons: List[str] = []
    add = lambda t, why: (t not in types and types.append(t), reasons.append(f"{t}: {why}"))  # noqa: E731
    places = _known_places(text)
    figures = [m.entry.get("name") for m in find_figure(text) if m.entry] if text else []
    equipment = [m.entry.get("name") for m in find_equipment(text) if m.entry and m.confidence == "exact"] if text else []
    for s in sents:
        places += [p for p in _unresolved_places(s, places, figures) if p.name not in [q.name for q in places]]
    as_actor = [p.name for p in places if place_roles(text, p.name.split(" (")[0]) and
                set(place_roles(text, p.name.split(" (")[0])) == {"actor"}]
    if as_actor:
        places = [p for p in places if p.name not in as_actor]          # "blamed Moscow for a shortage": Moscow is not the scene's place
        reasons.append(f"place used as a political actor, not a location: {', '.join(as_actor)}")
    specific = [p for p in places if p.kind != "region" or p.site_type]
    actor = ""
    date = ""
    outlet = ""
    speaker = ""
    nouns: List[str] = []
    facilities: List[str] = []
    for s in sents:
        low = s.lower()
        if _QUESTION_END.search(s):
            add("QUESTION", "ends with a question mark")
        if _ORDINAL.search(s) or _PARTS.search(s) or _OUTRO.search(s):
            add("TRANSITION", "structure / outro line")
        claim = _CLAIM.search(s) or next((re.search(rf"\b{re.escape(o)}['’]s\b", s) for o in OUTLETS if re.search(rf"\b{re.escape(o)}['’]s\b", s)), None)
        if claim:
            add("CLAIM", f"'{claim.group(0)}'")
            for o in OUTLETS:
                if re.search(rf"\b{re.escape(o)}\b", s):
                    outlet = outlet or o
                    break
        stat = _statistic(s)
        tally = bool(_TALLY.search(s))
        if stat:
            add("STATISTIC", "a figure with its referent")
        here = [p for p in specific if re.search(rf"\b{re.escape(fold(p.name).split(' (')[0].split()[0])}", fold(s), re.I)]
        kin = _KINETIC.search(s)
        state = _STATE.search(s)
        move = _MOVE.search(s)
        visible = _VISIBLE.search(s)
        fac = _FACILITY.findall(s)
        facilities += [f.lower() for f in fac if f.lower() not in facilities]
        negated = lambda m: bool(m) and bool(re.search(r"\b(no|not|never|without)\b", s[max(0, m.start() - 25):m.start()], re.I))  # noqa: E731
        a = _actor(s, here or specific, prev.actor if prev else "")
        actor = actor or a
        group = _GROUP_SUBJ.search(s)
        names_here = [n for n in _proper_names(s) if n.lower() not in [p.name.lower() for p in places]]
        named_subject = any(re.match(rf"^\s*(?:\w+,\s*)?(?:In [^,]+,\s*)?(?:the\s+)?(?:President |Prime Minister |General )?{re.escape(n)}\b", s)
                            or re.search(rf"\b{re.escape(n)}(?:'s)?(?:\s+\w+){{0,3}},?\s+(?:said|stood|visited|recruited|marched|gave|blamed)\b", s)
                            for n in names_here)
        agent = bool(group or named_subject or _PRONOUN_SUBJ.search(s) or _BATTLE_SUBJ.search(s))
        action = _ACTION.search(s)
        subj_country = bool(re.match(r"^\s*(?:\w+,\s*)?(?:Third, |Second, |First, )?(Russia|Ukraine|Russian forces|Ukrainian forces|"
                                     r"Russian troops|Ukrainian troops)\b", s))
        if _QUESTION_END.search(s):
            pass                                                           # a question asks; it shows nothing of its own
        elif tally and (stat or "counted" in low):
            pass                                                           # a tally of strikes / km2 is a figure, not an event
        else:
            if kin and not negated(kin) and (here or fac or (a and (subj_country or re.search(r"\b(Russian|Ukrainian) (strikes|attacks)", s)))):
                add("EVENT", f"'{kin.group(1)}' on {', '.join(p.name for p in here) or (fac[0] if fac else a)}")
            elif state and not negated(state) and (here or subj_country or (move and fac)):
                add("EVENT", f"'{state.group(1)}' of {', '.join(p.name for p in here) or a or fac[0]}")
            if action and not negated(action) and (agent or a) and "EVENT" not in types and not (stat and not here and not names_here):
                add("EVENT", f"'{action.group(1)}' by {a or (names_here[0] if names_here else 'the narrated side')}")
            elif kin and not negated(kin) and agent and "EVENT" not in types:
                add("EVENT", f"'{kin.group(1)}' by {a or 'the narrated side'}")
            if visible and not negated(visible):
                add("EVENT", f"visible scene: '{visible.group(1)[:30]}'")
            if move and not negated(move) and (here or a or fac or re.search(r"\bin the (north|south|east|west)\b", low)):
                if not (stat and not here) or re.search(r"\bby rail|tankers?|ships?|convoy", low):
                    add("MOVEMENT", f"'{move.group(1)}'")
        if here and not (tally and stat) and not _QUESTION_END.search(s) and \
                (not stat or any(p.site_type for p in here) or "EVENT" in types or "MOVEMENT" in types):
            add("LOCATION", ", ".join(p.name for p in here))
        if fac and not here and "EVENT" not in types and not stat and not negated(_FACILITY.search(s)) and claim and \
                re.search(r"\b(equipment|units?|tankers?|drones?|missiles?)\b", low) and not _ANALYSIS.search(s):
            add("SUBJECT", fac[0])
        if group and not stat and "EVENT" not in types and not _QUESTION_END.search(s):
            add("SUBJECT", group.group(1).lower())
        if equipment and "SUBJECT" not in types and not stat:
            add("SUBJECT", equipment[0])
        if _ANALYSIS.search(s) or ("TRANSITION" in types and not any(t in types for t in FOOTAGE_TYPES + ("CLAIM", "STATISTIC"))):
            add("ANALYSIS", "evaluation / conclusion")
        dm = next((m for m in _DATE.finditer(s) if not _COMPARISON_YEAR.search(s[:m.end()])), None)
        if dm and not date:
            date = dm.group(1).strip()
        nouns += [n.lower() for n in _EVENT_NOUN.findall(s) if n.lower() not in nouns]
        if claim and figures and not speaker:
            for f in figures:
                if f and fold(f).split()[-1].lower() in fold(s[:claim.start() + 1]).lower():
                    speaker = f
    if not types:
        types.append("ANALYSIS")
        reasons.append("ANALYSIS: nothing concrete named")
    order = {t: i for i, t in enumerate(("TRANSITION", "QUESTION", "EVENT", "MOVEMENT", "LOCATION", "SUBJECT", "CLAIM", "STATISTIC", "ANALYSIS"))}
    types.sort(key=lambda t: order[t])
    countries = []
    for c in COUNTRIES:
        if re.search(rf"\b{re.escape(c)}(?:'s|n|ns)?\b", text) and c not in countries:
            countries.append({"US": "United States", "UK": "United Kingdom"}.get(c, c))
    wanted = any(t in FOOTAGE_TYPES for t in types)
    keys: List[str] = []
    for p in places:
        for v in ([p.name.split(" (")[0]] + ([p.name.split(" (")[1].rstrip(")")] if " (" in p.name else [])):
            if p.site_type:
                v = re.sub(r"\s+(Refinery|Air Base|Naval Base|Port|Oil Port|Oil Terminal)$", "", v)
            for x in spelling_variants(v):
                if x not in keys:
                    keys.append(x)
    keys += [e for e in equipment if e not in keys] + [f for f in figures if f and f not in keys]
    names = []
    for s_ in sents:
        for n in _proper_names(s_):
            if n.lower() not in [k.lower() for k in keys] and n not in names and n.lower() not in [p.name.lower() for p in places] \
                    and n not in as_actor:
                names.append(n)
    keys += names
    if wanted and prev is not None and not places and re.search(r"\b(there|the area|the town|the village|the city|nearby)\b", text, re.I):
        keys = [k for k in prev.key_terms]                  # "But Russia is still pushing there": the place of the sentence before
        places = list(prev.places)
    side = re.search(r"\bin the (north|south|east|west|north-?east|south-?east|north-?west|south-?west)\b", text, re.I)
    if wanted and side:
        keys.append(side.group(1).lower())
    if wanted and not keys:
        kin = _KINETIC.search(text)
        air = re.search(r"\bfrom the air\b|\bair ?strikes?\b|\bmissiles?\b|\bdrones?\b", text, re.I)
        keys = facilities[:3] or nouns[:2] or ([("air strike" if air else kin.group(1).lower())] if kin else [])
    return Reading(text=str(text or ""), types=types, footage_wanted=wanted, places=places, names=names,
                   countries=[c for c in countries if c], actor=actor, equipment=equipment, figures=[f for f in figures if f],
                   speaker=speaker, outlet=outlet, date=date, event_nouns=nouns, facilities=facilities, key_terms=keys,
                   graphic_intents=graphic_intents(types, speaker), reasons=reasons)


def graphic_intents(types: Sequence[str], speaker: str = "") -> List[str]:
    """Which existing War graphics fit the sentence (direction.py builds them; this only says which family): every type has one."""
    m = {"QUESTION": "question_card", "TRANSITION": "chapter", "STATISTIC": "stat_panel", "CLAIM": "source_card", "MOVEMENT": "map_route",
         "LOCATION": "map_site", "EVENT": "headline", "SUBJECT": "subject_card", "ANALYSIS": "keyword_card"}
    out = [m[t] for t in types if t in m]
    if speaker:
        out.insert(0, "portrait")
    return out


def parse_date(text: str) -> Optional[Tuple[int, int, int, str]]:
    """(year, month, day, precision 'day'|'month'|'season'|'year') of a date phrase with a year; None without a year."""
    t = text or ""
    y = re.search(r"\b((?:19|20)\d\d)\b", t)
    if not y:
        return None
    year = int(y.group(1))
    se = re.search(r"\b(summer|winter|spring|autumn|fall)\b", t, re.I)
    for i, m in enumerate(MONTHS, start=1):
        mm = re.search(rf"\b{m}\b(?:\s+(\d{{1,2}})\b)?", t, re.I)
        if mm:
            return (year, i, int(mm.group(1)), "day") if mm.group(1) else (year, i, 1, "month")
    if se:
        return year, {"spring": 3, "summer": 6, "autumn": 9, "fall": 9, "winter": 12}[se.group(1).lower()], 1, "season"
    return year, 1, 1, "year"


def shift_date(text: str, days: int) -> str:
    import datetime as _dt
    p = parse_date(text)
    if not p:
        return ""
    d = _dt.date(p[0], p[1], p[2]) + _dt.timedelta(days=days)
    if p[3] == "day" or days < 28:
        return f"{d.strftime('%B')} {d.day}, {d.year}"
    return f"{d.strftime('%B')} {d.year}"


def read_scenes(scenes: Sequence[Dict[str, Any]]) -> Dict[str, Reading]:
    """{scene_no: Reading} for a War scene list, each reading the one before it (pronouns: 'They made no confirmed advances')."""
    out: Dict[str, Reading] = {}
    prev = None
    last_date = ""
    last_places: List[str] = []
    for sc in scenes:
        r = read(str(sc.get("text") or ""), prev)
        if r.date:
            r.date_source = "stated"
        rel = next((d for k, d in _REL_DATE.items() if re.search(rf"\b{k}\b", r.text, re.I)), None)
        if rel is not None and last_date:
            shifted = shift_date(last_date, rel)
            if shifted:
                r.date = shifted                   # "The next day" after December 20, 2022 -> December 21, 2022
                r.date_source = "relative"         # an estimate: never used to reject footage
        if r.date_source == "stated" and not re.search(r"\b(19|20)\d\d\b", r.date) and last_date:
            ref = parse_date(last_date)
            mine = parse_date(r.date + " 2000")
            if ref and mine:
                year = ref[0] - 1 if (re.match(r"\s*since\b", r.date, re.I) and mine[1] > ref[1]) else ref[0]
                r.date = f"{r.date} {year}"        # "since December" told in May 2023 is December 2022
        specific = [p.name for p in r.places if p.kind != "region" or p.site_type]
        if specific:
            last_places = specific[:2]
        elif r.footage_wanted and last_places:
            r.context_places = list(last_places)   # "Its fighters attacked street by street": still Bakhmut
            r.key_terms += [p for p in last_places if p not in r.key_terms]
        if not r.date and last_date and re.search(r"\b(19|20)\d\d\b", last_date):
            r.date = last_date
            r.date_source = "carried"
        if r.date and re.search(r"\b(19|20)\d\d\b", r.date):
            last_date = r.date
        out[str(sc.get("scene_no"))] = r
        prev = r if r.actor else (prev or r)
    return out
