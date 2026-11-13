"""Aviation bible: one reading of the WHOLE script before any Flow picture is described (docs/aviation/MASTER_PLAN.md section 5,
STICKER_STORY_PLAN.md Part 2 A). Rules only, no Gemini, no network, the same on every machine. Same idea as reptheory/bible.py.

    read(lines, rows=None) -> Bible          lines = the narration, one string per scene; rows = the CSV rows (optional, only `airline` /
                                             `aircraft` columns are used as hints when the line names nothing)
    Bible.to_dict() / Bible.from_dict(d)     plain JSON (lists / dicts / strings / numbers only)

A Bible holds (every entry keeps `lines`, the 0-based line numbers it came from):
    lines   [{no, text, year, year_kind(own|decade|carried|none), era, mode, airlines[], airline, aircraft[], airports[], place, roles[], mood}]
    eras    contiguous runs of one era: [{key, look, y0, y1, lines}]            (era keys: pre1960 1960s 1970s 1980s 1990s modern)
    fleet   {airline_id: {era: {types[], assumed, lines}}}                       types named by the script; none named -> story.era_type, assumed=True
    livery  {airline_id: {era: {name, colors[], color_words, notes, text, lines}}}  catalog colours + livery_notes; a historic name keeps its own
                                             catalog entry (Malaysian Airways is not Singapore Airlines); a line with its own year is mapped
                                             to the airline of that year (catalog previous_names) when that name has its own entry
    places  {airport_id: {id, name, city, country, landmark, lines, eras}}       landmark = a phrase for the ~20 common hubs (era aware)
    cast    {role: {role, label, lines, airline, era}}                           UNNAMED people by role only (captain, first_officer,
                                             cabin_crew, atc, engineer, dispatcher, official, executive, passenger); never a real name
    motifs  [{phrase, count, lines}]                                             the script's own repeated noun phrases (2+ lines)
    moods   contiguous chapter runs [{mood, lines, light, palette, weather, words}]   mood: rise | crisis | split | recovery | steady

Helpers: era_of(year), era_look(key), color_name(hex), landmark(airport_id, year), mood_words(mood), hero_id(airline, era),
cast_id(role), place_id(airport), FALLBACK_TYPES. Line numbers are 0-based indexes into `lines`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence

from . import catalog as C
from . import router as R

try:                                            # the story director's era guess when a line names an airline but no type
    from .story import era_type as _story_era_type
except Exception:                               # pragma: no cover - story.py is optional here
    def _story_era_type(year: int) -> str:
        if not year:
            return "a350"
        return "dc3" if year < 1958 else "b707" if year < 1972 else "b747" if year < 1995 else "b777" if year < 2010 else "a350"

# ------------------------------------------------------------------------------------------------------------------ eras
ERAS = (("pre1960", 1960, "late-1940s and 1950s archive photograph, sepia tone, heavy film grain"),
        ("1960s", 1970, "Kodachrome 1960s colour photograph, saturated warm film colour, soft grain"),
        ("1970s", 1980, "1970s colour photograph, faded orange and brown tones, film grain"),
        ("1980s", 1990, "1980s colour photograph, slightly washed colour, soft focus, flash-lit snapshot feel"),
        ("1990s", 2000, "1990s colour film photograph, neutral colour, mild grain"),
        ("modern", 10 ** 6, "clean modern digital photograph, natural light, sharp detail"))
ERA_KEYS = tuple(e[0] for e in ERAS)

# an aircraft the catalog does not carry but story.era_type can return
FALLBACK_TYPES = {"dc3": {"id": "dc3", "name": "Douglas DC-3", "maker": "Douglas", "body": "narrow2", "engines": 2, "glb": "prop"}}


def era_of(year: Optional[int]) -> str:
    if not year:
        return "modern"
    for key, until, _ in ERAS:
        if year < until:
            return key
    return "modern"


def era_look(key: str) -> str:
    for k, _, look in ERAS:
        if k == key:
            return look
    return ERAS[-1][2]


def aircraft_entry(type_id: str) -> Optional[dict]:
    return C.get_aircraft(type_id) or FALLBACK_TYPES.get(type_id)


# ------------------------------------------------------------------------------------------------------------------ colours
_PALETTE = (("black", (20, 20, 20)), ("white", (245, 245, 245)), ("silver", (190, 195, 200)), ("grey", (120, 120, 120)),
            ("red", (210, 30, 40)), ("maroon", (110, 20, 40)), ("orange", (245, 150, 30)), ("yellow", (245, 200, 0)),
            ("gold", (212, 175, 55)), ("green", (30, 140, 70)), ("teal", (0, 130, 130)), ("light blue", (110, 180, 230)),
            ("blue", (35, 70, 160)), ("dark blue", (20, 45, 100)), ("purple", (110, 50, 150)), ("pink", (235, 120, 170)),
            ("brown", (110, 70, 40)))


def color_name(hex_code: str) -> str:
    h = str(hex_code or "").lstrip("#")
    if len(h) != 6:
        return "white"
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return "white"
    return min(_PALETTE, key=lambda p: (p[1][0] - r) ** 2 + (p[1][1] - g) ** 2 + (p[1][2] - b) ** 2)[0]


def color_words(colors: Sequence[str]) -> str:
    names: List[str] = []
    for c in colors or ():
        n = color_name(c)
        if n not in names:
            names.append(n)
    if not names:
        return "white"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


# ------------------------------------------------------------------------------------------------------------------ places
# (until_year, phrase) per IATA code; the last entry has no limit. Only hubs the films mention most.
_LANDMARKS: Dict[str, Sequence] = {
    "SIN": ((1955, "the Kallang airport terminal building"), (1981, "the Paya Lebar airport terminal"),
            (10 ** 6, "the Changi control tower beside the Jewel waterfall dome")),
    "DXB": ((10 ** 6, "the Burj Khalifa skyline beyond the terminal")),
    "KUL": ((10 ** 6, "the Petronas Towers on the skyline")),
    "LHR": ((10 ** 6, "the Heathrow control tower and a Terminal 5 canopy")),
    "JFK": ((10 ** 6, "the curved TWA Flight Center terminal and the Manhattan skyline")),
    "LAX": ((10 ** 6, "the Theme Building arches")),
    "SFO": ((10 ** 6, "the Golden Gate Bridge in the distance")),
    "CDG": ((10 ** 6, "the round concrete Terminal 1 with its tube walkways")),
    "AMS": ((10 ** 6, "the Schiphol control tower on flat green polders")),
    "FRA": ((10 ** 6, "the Frankfurt skyline of glass towers behind the apron")),
    "HKG": ((10 ** 6, "Victoria Harbour skyline and the Lantau hills")),
    "HND": ((10 ** 6, "Tokyo Bay with the Tokyo Tower skyline")),
    "NRT": ((10 ** 6, "green Chiba countryside around a long terminal")),
    "SYD": ((10 ** 6, "the Sydney Opera House and Harbour Bridge on the horizon")),
    "IST": ((10 ** 6, "the Istanbul skyline of domes and minarets")),
    "DOH": ((10 ** 6, "the West Bay towers of Doha")),
    "AUH": ((10 ** 6, "the white domes of the Sheikh Zayed Grand Mosque")),
    "BKK": ((10 ** 6, "a glass terminal with a Bangkok temple spire behind")),
    "DEL": ((10 ** 6, "India Gate under a hazy sky")),
    "BOM": ((10 ** 6, "the Gateway of India by the harbour")),
    "YYZ": ((10 ** 6, "the CN Tower rising over Toronto")),
    "ICN": ((10 ** 6, "a vast glass terminal and control tower by the sea")),
}


def landmark(airport_id: str, year: Optional[int] = None) -> str:
    rows = _LANDMARKS.get(airport_id)
    if not rows:
        return ""
    if rows and isinstance(rows[0], int):               # single (until, phrase) pair written without the outer tuple
        rows = (rows,)
    for until, phrase in rows:
        if not year or year < until:
            return phrase if year else rows[-1][1]
    return rows[-1][1]


# ------------------------------------------------------------------------------------------------------------------ cast
_ROLES = (("captain", "captain", r"\b(?:captains?|pilots?|flight deck|cockpit)\b"),
          ("first_officer", "first officer", r"\b(?:first officers?|co-?pilots?)\b"),
          ("cabin_crew", "cabin crew member", r"\b(?:cabin crew|flight attendants?|stewardess(?:es)?|air hostess(?:es)?|stewards?|hostess(?:es)?)\b"),
          ("atc", "air traffic controller", r"\b(?:air traffic control(?:lers?)?|controllers?|the tower|control tower|ATC)\b"),
          ("engineer", "aircraft engineer", r"\b(?:engineers?|mechanics?|technicians?|ground crew|maintenance crew)\b"),
          ("dispatcher", "flight dispatcher", r"\bdispatchers?\b"),
          ("official", "government official", r"\b(?:prime ministers?|ministers?|officials?|regulators?|ambassadors?|governors?)\b"),
          ("executive", "airline executive", r"\b(?:chief executives?|CEOs?|chairm[ae]n|chairwom[ae]n|executives?|founders?|the board)\b"),
          ("passenger", "passenger", r"\b(?:passengers?|travell?ers?|tourists?)\b"))
_ROLE_RX = [(k, label, re.compile(rx, re.I if k != "atc" else 0)) for k, label, rx in _ROLES]
_ATC_RX = re.compile(r"\b(?:air traffic control(?:lers?)?|controllers?|the tower|control tower|ATC)\b", re.I)


def roles_in(text: str) -> List[str]:
    out = []
    for k, _, rx in _ROLE_RX:
        if (_ATC_RX if k == "atc" else rx).search(text):
            out.append(k)
    return out


def role_label(role: str) -> str:
    return next((label for k, label, _ in _ROLES if k == role), role.replace("_", " "))


# ------------------------------------------------------------------------------------------------------------------ moods
MOODS = {"rise": ("bright clear morning light", "warm golden and fresh blue palette", "clear blue sky with a few white clouds", "hopeful"),
         "crisis": ("heavy flat overcast light", "desaturated cold grey-blue palette", "dark storm clouds and rain", "tense"),
         "split": ("hard low dusk light with long shadows", "two contrasting colour halves, cool blue against warm amber", "a sky divided between cloud and clear", "divided"),
         "recovery": ("soft sunrise breaking through cloud", "fresh clean palette with warm highlights", "clearing sky after rain", "calm and optimistic"),
         "steady": ("even natural daylight", "balanced neutral palette", "light high cloud", "measured")}
_MOOD_WORDS = {
    "rise": r"found(?:ed|ing)|launch\w*|began|begin|birth|born|grew|grow\w*|expan\w*|record|profit\w*|opened|boom\w*|soar\w*|inaugura\w*|first|new|proud|famous|success\w*|won|wins",
    "crisis": r"crash\w*|collaps\w*|loss(?:es)?|debt\w*|bankrupt\w*|strike\w*|crisis|war|grounded|fear\w*|shortage\w*|recession|pandemic|covid|cancel\w*|row|argu\w*|disput\w*|tension\w*|quarrel\w*|disagree\w*|fell|fail\w*|trouble|could not agree|clash\w*|fight\w*|fought",
    "split": r"split|divorce\w*|separat\w*|broke|break-?up|divid\w*|demerge\w*|parted|independen\w*|dissolv\w*|ended|went their own ways?",
    "recovery": r"recover\w*|rebuil\w*|return\w*|comeback|rebound\w*|restart\w*|surviv\w*|resum\w*|restructur\w*|turnaround|revived?|bounced back"}
_MOOD_RX = {k: re.compile(r"\b(?:" + v + r")\b", re.I) for k, v in _MOOD_WORDS.items()}


def mood_words(mood: str) -> Dict[str, str]:
    light, palette, weather, feel = MOODS.get(mood, MOODS["steady"])
    return {"light": light, "palette": palette, "weather": weather, "feel": feel,
            "words": f"{light}, {palette}, {weather}, {feel} mood"}


def _mood_of(text: str) -> Optional[str]:
    scores = {k: len(rx.findall(text)) for k, rx in _MOOD_RX.items()}
    best = max(scores.values())
    if not best:
        return None
    top = [k for k, v in scores.items() if v == best]
    for pref in ("split", "crisis", "recovery", "rise"):        # a tie goes to the turn of the story
        if pref in top:
            return pref
    return top[0]


# ------------------------------------------------------------------------------------------------------------------ motifs
_STOP = set("""a an the and or but nor so yet for of to in on at by as with without from into onto over under about after before between through during until since
because though although while when where which who whom whose what this that these those there here their they them its his her our your you we he she it i me my is are
was were be been being am do does did done have has had having will would shall should can could may might must not no yes also just still only very more most many much
some any every each other another such same than then too even ever never always often again once now today tonight one two three four five six seven eight nine ten
first second third last next new old long short big small high low good bad great little own all both few less least off up down out back away around across against
year years time times way day days thing things lot lots part said says say made make makes making took take taken takes gave give gives given went go goes going gone came
come comes coming got get gets getting began begin begun start started starts ended end ends called named renamed joined join built build ran run kept keep held hold
flew fly flies flying formed form became become becomes grew grown knew know known saw see seen seemed seem let put set turned turn left right found find
airline airlines airways aircraft flight flights plane jet jets company story world how why what's it's that's if whether either neither rather quite already soon later
famous because behind beside among toward towards within along beyond""".split())
_BRIDGE = {"and", "of"}
_PUNCT_GAP = re.compile(r"[^\sA-Za-z'\-]|\.\s")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-]*")


@lru_cache(maxsize=1)
def _name_tokens() -> frozenset:
    out = set("""malaysia malaya singapore britain british england france germany india china japan america american europe asia australia africa
        federation kingdom states united sydney london paris tokyo dubai kuala lumpur hong kong new york los angeles""".split())
    for e in C.all_airlines() + C.all_airports() + C.all_aircraft():
        for s in [e.get("name", ""), e.get("city", ""), e.get("maker", "")] + list(e.get("aliases") or []):
            for t in _TOKEN.findall(str(s).lstrip("=")):
                out.add(t.lower())
        for p in e.get("previous_names") or ():
            for t in _TOKEN.findall(str(p.get("name", ""))):
                out.add(t.lower())
    return frozenset(out)


def _lemma(w: str) -> str:
    w = w.lower()
    return w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w


def _runs(text: str) -> List[List[str]]:
    toks = list(_TOKEN.finditer(text))
    names = _name_tokens()
    runs: List[List[str]] = []
    cur: List[str] = []
    prev_end = None
    sentence_start = True
    for m in toks:
        w = m.group(0)
        low = w.lower()
        if prev_end is not None and _PUNCT_GAP.search(text[prev_end:m.start()]):
            if cur:
                runs.append(cur)
            cur = []
            sentence_start = bool(re.search(r"[.!?]\s*$", text[prev_end:m.start()]) or re.search(r"[.!?]\s", text[prev_end:m.start()]))
        proper = w[0].isupper() and not sentence_start and prev_end is not None
        if (low in _STOP and low not in _BRIDGE) or low in names or proper or len(low) < 3 and low not in _BRIDGE:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(w)
        prev_end = m.end()
        sentence_start = False
    if cur:
        runs.append(cur)
    return runs


def _motifs(lines: Sequence[str]) -> List[dict]:
    seen: Dict[str, dict] = {}
    for n, text in enumerate(lines):
        grams = set()
        for run in _runs(text):
            for size in (1, 2, 3):
                for i in range(len(run) - size + 1):
                    g = run[i:i + size]
                    if g[0].lower() in _BRIDGE or g[-1].lower() in _BRIDGE:
                        continue
                    if size == 1 and (len(g[0]) < 4 or g[0].lower() in _BRIDGE):
                        continue
                    if size == 3 and g[1].lower() not in _BRIDGE and (g[0].lower() in _BRIDGE or g[2].lower() in _BRIDGE):
                        continue
                    key = " ".join(_lemma(x) for x in g)
                    grams.add((key, " ".join(x.lower() for x in g)))
        for key, surface in grams:
            e = seen.setdefault(key, {"phrase": surface, "tokens": key.split(), "lines": []})
            e["lines"].append(n)
    cand = [e for e in seen.values() if len(e["lines"]) >= 2]
    keep = []
    for e in cand:
        t = e["tokens"]
        inside = False
        for o in cand:
            if o is e or len(o["tokens"]) <= len(t) or len(o["lines"]) < len(e["lines"]):
                continue
            ot = o["tokens"]
            if any(ot[i:i + len(t)] == t for i in range(len(ot) - len(t) + 1)):
                inside = True
                break
        if not inside:
            keep.append(e)
    keep.sort(key=lambda e: (-(len(e["lines"]) + 0.5 * (len(e["tokens"]) - 1)), e["lines"][0], e["phrase"]))
    return [{"phrase": e["phrase"], "count": len(e["lines"]), "lines": e["lines"]} for e in keep[:8]]


# ------------------------------------------------------------------------------------------------------------------ the Bible
def hero_id(airline: str, era: str) -> str:
    return f"hero:{airline}:{era}"


def cast_id(role: str) -> str:
    return f"cast:{role}"


def place_id(airport: str) -> str:
    return f"place:{airport}"


@dataclass
class Bible:
    lines: List[dict] = field(default_factory=list)
    eras: List[dict] = field(default_factory=list)
    fleet: Dict[str, Dict[str, dict]] = field(default_factory=dict)
    livery: Dict[str, Dict[str, dict]] = field(default_factory=dict)
    places: Dict[str, dict] = field(default_factory=dict)
    cast: Dict[str, dict] = field(default_factory=dict)
    motifs: List[dict] = field(default_factory=list)
    moods: List[dict] = field(default_factory=list)
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        import copy
        return copy.deepcopy({k: getattr(self, k) for k in self.__dataclass_fields__})

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "Bible":
        import copy
        d = d or {}
        return cls(**{k: copy.deepcopy(d[k]) for k in cls.__dataclass_fields__ if k in d})


def _spans(ms) -> List[tuple]:
    return [(m.start, m.end) for m in ms]


def _inside(m, spans) -> bool:
    return any(s <= m.start and m.end <= e for s, e in spans)


def _as_of(entry: dict, year: int) -> dict:
    """The catalog entry of the airline AS IT WAS NAMED in `year` when that name has its own entry, else the entry itself."""
    name = C.name_in_year(entry["id"], year)
    if not name or name == entry.get("name"):
        return entry
    for e in C.all_airlines():
        if e.get("name") == name:
            return e
    return entry


def _year_of(text: str, years: Sequence[int]) -> tuple:
    if not years:
        return None, "none"
    y = years[0]
    if re.search(rf"\b{y}s\b", text):
        return y + 5, "decade"
    return y, "own"


def read(lines: Sequence[str], rows: Optional[Sequence[dict]] = None) -> Bible:
    lines = [str(x or "") for x in lines]
    routed = R.route_script(lines)
    recs: List[dict] = []
    year: Optional[int] = None
    focus: Optional[str] = None
    place: Optional[str] = None
    mood = "steady"
    for n, (text, c) in enumerate(zip(lines, routed)):
        row = (rows[n] if rows and n < len(rows) and rows[n] else {}) or {}
        y, kind = _year_of(text, c.values.get("years", ()))
        if y:
            year = y
        else:
            y, kind = (year, "carried") if year else (None, "none")
        a_spans = _spans(C.find_airlines(text))
        names: List[str] = []
        for m in C.find_airlines(text):
            if m.entry is None:
                continue
            ent = _as_of(m.entry, y) if kind == "own" else m.entry
            if ent["id"] not in names:
                names.append(ent["id"])
        if not names and row.get("airline") and C.get_airline(str(row["airline"])):
            names.append(str(row["airline"]))
        airports: List[str] = []
        for m in C.find_airports(text):
            if m.entry is not None and not _inside(m, a_spans) and m.entry["id"] not in airports:
                airports.append(m.entry["id"])
        craft = [a["id"] for a in c.aircraft]
        if not craft and row.get("aircraft") and aircraft_entry(str(row["aircraft"])):
            craft = [str(row["aircraft"])]
        if names:
            focus = names[0]
        if airports:
            place = airports[-1]
        m_ = _mood_of(text)
        if m_:
            mood = m_
        recs.append({"no": n, "text": text, "year": y, "year_kind": kind, "era": era_of(y), "mode": c.mode, "airlines": names, "airline": focus,
                     "aircraft": craft, "airports": airports, "place": place, "roles": roles_in(text), "mood": mood,
                     "_mood_own": bool(m_)})
    first_own = next((r["mood"] for r in recs if r["_mood_own"]), None)
    seen_own = False
    for r in recs:                                    # lines before the first mood word take the first chapter's mood
        seen_own = seen_own or r["_mood_own"]
        if first_own and r["mood"] == "steady" and not seen_own:
            r["mood"] = first_own
    for r in recs:                                    # the helper flag goes only after every line was looked at
        r.pop("_mood_own", None)

    b = Bible(lines=recs)
    # eras: contiguous runs
    for r in recs:
        if b.eras and b.eras[-1]["key"] == r["era"]:
            e = b.eras[-1]
            e["lines"].append(r["no"])
            if r["year"]:
                e["y0"] = min(e["y0"] or r["year"], r["year"])
                e["y1"] = max(e["y1"] or r["year"], r["year"])
        else:
            b.eras.append({"key": r["era"], "look": era_look(r["era"]), "y0": r["year"], "y1": r["year"], "lines": [r["no"]]})
    # fleet + livery
    first_year: Dict[tuple, Optional[int]] = {}
    for r in recs:
        ids = r["airlines"] or ([r["airline"]] if r["airline"] and r["aircraft"] else [])
        for aid in ids:
            e = b.fleet.setdefault(aid, {}).setdefault(r["era"], {"types": [], "assumed": False, "lines": []})
            e["lines"].append(r["no"])
            first_year.setdefault((aid, r["era"]), r["year"])
            for t in r["aircraft"]:
                if t not in e["types"]:
                    e["types"].append(t)
    for aid, eras in b.fleet.items():
        ent = C.get_airline(aid) or {}
        for era, e in eras.items():
            if not e["types"]:
                e["types"] = [_story_era_type(first_year.get((aid, era)) or 0)]
                e["assumed"] = True
            words = color_words(ent.get("colors") or [])
            notes = str(ent.get("livery_notes") or "")
            text = (f"{notes} (colours: {words})" if notes else f"painted in {words}")
            b.livery.setdefault(aid, {})[era] = {"name": ent.get("name", aid), "colors": list(ent.get("colors") or []), "color_words": words,
                                                 "notes": notes, "text": text, "lines": list(e["lines"])}
    # places
    for r in recs:
        for pid in r["airports"]:
            ap = C.get_airport(pid) or {}
            p = b.places.setdefault(pid, {"id": pid, "name": ap.get("name", pid), "city": ap.get("city", ""), "country": ap.get("country", ""),
                                          "landmark": "", "lines": [], "eras": []})
            p["lines"].append(r["no"])
            if r["era"] not in p["eras"]:
                p["eras"].append(r["era"])
            if not p["landmark"]:
                p["landmark"] = landmark(pid, r["year"])
    # cast: roles only
    for r in recs:
        for role in r["roles"]:
            e = b.cast.setdefault(role, {"role": role, "label": role_label(role), "lines": [], "airline": r["airline"], "era": r["era"]})
            e["lines"].append(r["no"])
    b.motifs = _motifs(lines)
    # chapter moods: contiguous runs
    for r in recs:
        if b.moods and b.moods[-1]["mood"] == r["mood"]:
            b.moods[-1]["lines"].append(r["no"])
        else:
            b.moods.append(dict(mood=r["mood"], lines=[r["no"]], **mood_words(r["mood"])))
    return b
