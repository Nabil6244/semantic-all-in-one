"""War Footage Director, Stages 3 and 6: hard rejection rules, ranking, and the film-wide no-repeat registry.

docs/war/FOOTAGE_DIRECTOR_PLAN.md. A candidate is REJECTED (with a reason that names the rule) when it cannot be footage of what the sentence
says, whatever its keyword overlap:

  entity      the scene's key place / site / equipment is not named in the title, description or tags
  geography   another known place or site is the subject and the scene's own is not named
  side        the narration's actor is reversed (Ukrainian drones for 'Russia is hitting back')
  subject     a different subject class (warehouse vs refinery, natural gas vs gasoline, US prices vs Russian supply)
  time        uploaded before the dated event, or years away from the film's date for an EVENT
  format      live / stream / compilation / game / simulation / AI / animation / reaction / podcast / long commentary

Ranking of what is left: channel tier (data/channels.json), short raw uploads first, entity coverage, how many queries found it, date closeness.
Pure and offline (works on Candidate objects from director_search).
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .narration_read import Reading, fold, spelling_variants, _actor as reading_actor

DATA = Path(__file__).resolve().parent / "data" / "channels.json"
TIER_SCORE = {"agency": 4.0, "broadcaster": 3.0, "regional": 2.0, "aggregator": 0.6, "unknown": 0.3, "commentary": -2.0}
LONG_EVENT_S = 20 * 60          # an EVENT clip from a video longer than this is a narrated programme, not footage
SHORT_RAW_S = 180               # uploads up to this long are usually raw news clips
MIN_VIDEO_S = 8                 # shorter cannot hold an 8 s window with a margin

_FORMAT = re.compile(r"\b(live|livestream|live stream|stream(?:ing)?|24/7|compilation|gameplay|arma ?3|war thunder|dcs world|simulation|"
                     r"simulated|animation|animated|3d animation|cgi|\bai\b|ai[- ]generated|reaction|reacts?|podcast|interview|full interview|"
                     r"full speech|press conference|briefing|explained|explainer|analysis|map update|frontline changes|breakdown|q ?& ?a|"
                     r"#shorts|shorts|tiktok|then this happened|this happened next|lecture|documentary|full episode|mini[- ]doc|"
                     r"see what .{0,50}(?:said|says)|what .{0,40} (?:purportedly|reportedly) said|anchor|panel discussion|talks to)\b", re.I)
_OTHER_COUNTRIES = {"Cuba": r"\bcuban?s?\b", "Venezuela": r"\bvenezuela", "Lithuania": r"\blithuania", "Latvia": r"\blatvia", "Estonia": r"\bestonia",
                    "Nigeria": r"\bnigeria", "India": r"\bindia\b|\bindian\b", "China": r"\bchina\b|\bchinese\b", "Iran": r"\biran", "Israel": r"\bisrael",
                    "Syria": r"\bsyria", "Spain": r"\bspain|\bspanish\b", "Norway": r"\bnorway|\bnorwegian", "Poland": r"\bpoland|\bpolish\b",
                    "Moldova": r"\bmoldova", "Georgia": r"\btbilisi|\bgeorgian\b", "Taiwan": r"\btaiwan", "North Korea": r"\bnorth korea",
                    "Gaza": r"\bgaza\b", "Yemen": r"\byemen|\bhouthi", "Belarus": r"\bbelarus", "Kazakhstan": r"\bkazakh",
                    "United States": r"\bu\.?s\.?\b|\bamerica|\bwashington\b|\btrump\b|\bnew jersey\b|\btexas\b"}
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")


@lru_cache(maxsize=1)
def _tiers() -> Tuple[Dict[str, str], Tuple[str, ...]]:
    try:
        raw = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, ()
    idx = {}
    for tier, names in (raw.get("tiers") or {}).items():
        for n in names:
            idx[fold(n).lower().strip()] = tier
    return idx, tuple(raw.get("commentary_name_hints") or ())


def channel_tier(channel: str) -> str:
    idx, hints = _tiers()
    k = fold(channel).lower().strip()
    if k in idx:
        return idx[k]
    for name, tier in idx.items():                 # "DPA War (Defense Politics Asia) and Defense Politics Asia (DPA)": a collab of a listed one
        if len(name) > 5 and name in k:
            return tier
    if any(h in k for h in hints):
        return "commentary"
    return "unknown"


def _hay(c: Any) -> str:
    d = getattr(c, "details", None) or {}
    tags = " ".join(d.get("tags") or [])
    return fold(f"{c.title} {c.description} {tags}").lower()


_SYN = {"gasoline": ("gasoline", "gas", "petrol", "fuel"), "station": ("station", "stations", "pump", "pumps", "queue", "queues"),
        "strike": ("strike", "strikes", "struck", "attack", "attacks", "hit", "missile", "missiles", "drone", "drones", "salvo", "bomb"),
        "air": ("air", "missile", "missiles", "drone", "drones", "salvo", "strike", "strikes"),
        "power": ("power", "energy", "grid", "electricity", "blackout", "plant", "plants"), "plant": ("plant", "plants", "station", "facility"),
        "tanker": ("tanker", "tankers", "ship", "ships", "vessel", "vessels", "shipment", "cargo"), "refinery": ("refinery", "refineries", "oil plant"),
        "rail": ("rail", "railway", "train", "trains", "tank cars"), "queue": ("queue", "queues", "line", "lines", "wait")}


def _has(hay: str, term: str) -> bool:
    """A proper name (any transliteration, possessive allowed; a person's or body's last word: 'Yevgeny Prigozhin' -> 'Prigozhin',
    'United States Congress' -> 'Congress') or, for a generic term, any of its words or their synonyms."""
    if term[:1].isupper():
        forms = list(spelling_variants(term))
        parts = term.split()
        if len(parts) > 1 and len(parts[-1]) >= 5 and parts[-1][:1].isupper() and parts[-1].lower() not in ("group", "forces", "army", "refinery"):
            forms += spelling_variants(parts[-1])
        if len(parts) > 1 and parts[-1].lower() == "group":
            forms += spelling_variants(parts[0])           # "Wagner Group" -> "Wagner"
        return any(re.search(rf"\b{re.escape(fold(v).lower())}(?:'s)?\b", hay) for v in forms)
    for w in re.findall(r"[a-z]+", fold(term).lower()):
        stem = re.sub(r"(ies)$", "y", w)
        stem = re.sub(r"s$", "", stem)
        for x in _SYN.get(stem, (w, stem)):
            if re.search(rf"\b{re.escape(x)}\b", hay):
                return True
    return False


def _known_places_in(text: str) -> List[Tuple[str, str]]:
    """(name, country) of catalogue places and strategic sites a title names."""
    out = []
    try:
        from .map_events import sites_in
        out += [(s["name"], s.get("country", "")) for _o, s in sites_in(text)]
    except Exception:  # noqa: BLE001
        pass
    try:
        from .catalog import find_place
        out += [((m.entry or {}).get("name") or m.matched_alias, (m.entry or {}).get("region", "")) for m in find_place(text)
                if m.confidence == "exact" and (m.entry or {}).get("type") not in ("country", "region")]
    except Exception:  # noqa: BLE001
        pass
    return out


def event_date(r: Reading, film_date: Optional[_dt.date]) -> Optional[Tuple[_dt.date, _dt.date]]:
    """(earliest, latest) day the narrated event can be, from the reading's date words and the film's date; None when undated."""
    if not film_date or not r.date:
        return None
    d = r.date.lower()
    y = re.search(r"\b(19|20)\d\d\b", d)
    year = int(y.group(0)) if y else film_date.year
    if d in ("overnight", "last night"):
        return film_date - _dt.timedelta(days=4), film_date
    if d in ("this week",):
        return film_date - _dt.timedelta(days=8), film_date
    for i, m in enumerate(_MONTHS, start=1):
        if m in d:
            yy = year if (y or i <= film_date.month) else year - 1
            day = re.search(rf"{m}\s+(\d{{1,2}})\b", d)
            if day:
                try:
                    x = _dt.date(yy, i, int(day.group(1)))
                    return x - _dt.timedelta(days=1), x + _dt.timedelta(days=1)
                except ValueError:
                    return None
            start = _dt.date(yy, i, 1)
            end = (_dt.date(yy + (i == 12), (i % 12) + 1, 1) - _dt.timedelta(days=1))
            return start, end
    if y:
        return _dt.date(year, 1, 1), _dt.date(year, 12, 31)
    return None


def _upload(c: Any) -> Optional[_dt.date]:
    u = str((getattr(c, "details", None) or {}).get("upload_date") or "")
    try:
        return _dt.datetime.strptime(u, "%Y%m%d").date() if len(u) == 8 else None
    except ValueError:
        return None


def story_period(readings: Sequence[Reading]) -> Optional[Tuple[_dt.date, _dt.date]]:
    """(first, last) day the script's STATED dates cover, for a historical film (Bakhmut: Aug 2022 .. Sep 2023); None for a news brief
    whose sentences name no years."""
    from .narration_read import parse_date
    days = []
    for r in readings:
        if getattr(r, "date_source", "stated") != "stated" or not r.date:
            continue
        p = parse_date(r.date)
        if not p:
            continue
        d0 = _dt.date(p[0], p[1], p[2])
        span = {"day": 1, "month": 31, "season": 92, "year": 366}[p[3]]
        days += [d0, d0 + _dt.timedelta(days=span)]
    return (min(days), max(days)) if days else None


STORY_SLACK = _dt.timedelta(days=30)


def _names_context(c: Any, r: Reading) -> bool:
    hay = _hay(c)
    return any(_has(hay, k) for k in (r.context_places or []) + [p.name for p in r.places])


# Stage B.3 (live slice 2026-11-12: an Abu Dhabi business panel for the talks, Putin meeting Kushner for the Ryazan refinery, St Petersburg
# protest arrests for its fuel supply): a place name alone never makes a clip footage of the line's event. Place, event and subject are
# judged separately; exact = the line's event AND its place or subject in the title, filmed no earlier than the event.
EVENT_CLASSES = {
    "talks": r"\b(talks?|negotiat\w*|peace|summit|trilateral|three-way|delegations?|diplomac\w*|diplomats?|ceasefire|envoys?|mediat\w*|"
             r"deal|meets?|meeting|met with)\b",
    "prisoners": r"\b(prisoners?|pows?|captiv\w*|swaps?|exchang\w*|released|freed)\b",
    "strike": r"\b(strikes?|struck|attack\w*|drones?|missiles?|explosions?|blasts?|shell(?:ing|ed)|bomb\w*|debris|hit|hits|shot down)\b",
    "fire": r"\b(fires?|blaze|burn\w*|smoke|flames?|ablaze)\b",
    "oil": r"\b(refiner\w*|oil|fuel|petrol|gasoline|diesel|jet fuel|depots?|pipelines?|tankers?|pumping station)\b",
    "combat": r"\b(front ?lines?|soldiers|troops|trench\w*|counter-?offensive|offensive|invasion|fighting|battles?|assault\w*)\b",
    "protest": r"\b(protest\w*|protesters|demonstrat\w*|rall(?:y|ies)|arrest\w*|detain\w*|riot\w*)\b",
    "economy": r"\b(growth|investment|investors?|economy|business|forum|partnerships?|startups?|real estate|tourism)\b",
}
_EVENT_RX = {k: re.compile(v, re.I) for k, v in EVENT_CLASSES.items()}
EVENT_FAMILY = {"talks": "diplomacy", "prisoners": "diplomacy", "strike": "attack", "fire": "attack", "oil": "attack", "combat": "attack",
                "protest": "protest", "economy": "economy"}


_EXCLUSIVE = {"protest", "economy"}     # a title about one of these is about that, whatever else it mentions ('protest against the invasion')


def events_in(text: str) -> set:
    """The event classes a text names ('talks', 'strike', 'oil', ...)."""
    t = fold(text or "")
    return {k for k, rx in _EVENT_RX.items() if rx.search(t)}


def _families(ev: set) -> set:
    return {EVENT_FAMILY[e] for e in ev}


def _title_hay(c: Any) -> str:
    d = getattr(c, "details", None) or {}
    return fold(f"{c.title} {' '.join(d.get('tags') or [])}").lower()


def line_places(r: Reading) -> List[str]:
    """The places the line is about: specific places (not whole regions) it does not name only as a reference point ('south-east of Moscow')."""
    from .narration_read import reference_only

    return [p.name for p in r.places if (p.kind != "region" or p.site_type) and not reference_only(r.text, p.name)]


def stale(c: Any, r: Reading) -> bool:
    """Uploaded before the event the line narrates (its own stated date, else its section's latest stated date): an earlier event."""
    up = _upload(c)
    anchor = getattr(r, "date", "") if getattr(r, "date_source", "") == "stated" else ""
    anchor = anchor or getattr(r, "section_date", "")
    if not up or not anchor:
        return False
    from .narration_read import parse_date

    d = parse_date(anchor if re.search(r"\b(19|20)\d\d\b", anchor) else "")
    if not d:
        return False
    try:
        start = _dt.date(d[0], d[1] or 1, d[2] if len(d) > 2 and d[2] and d[3] == "day" else 1)
    except (ValueError, TypeError, IndexError):
        return False
    return up < start - _dt.timedelta(days=2)


def dimensions(c: Any, r: Reading) -> Dict[str, Any]:
    """Place, event and subject judged separately on the clip's title (strong) and description (weak)."""
    hay_t, hay = _title_hay(c), _hay(c)
    places = line_places(r)
    subj = [k for k in r.key_terms if k[:1].isupper() and k not in places and k not in (r.context_places or [])
            and not any(fold(k).lower() == fold(p).lower() for p in [x.name for x in r.places])]
    line_ev = events_in(r.text)
    t_ev, d_ev = events_in(c.title or ""), events_in(hay)
    return {"place_title": any(_has(hay_t, p) for p in places), "place": any(_has(hay, p) for p in places),
            "context": _names_context(c, r),
            "subject_title": any(_has(hay_t, k) for k in subj), "subject": any(_has(hay, k) for k in subj),
            "line_events": sorted(line_ev), "title_events": sorted(t_ev),
            "event_title": bool(line_ev & t_ev), "event_family": bool(_families(line_ev) & _families(d_ev)),
            "event_conflict": bool(line_ev and t_ev and (not (_families(line_ev) & _families(t_ev))
                                                         or (_families(t_ev) & _EXCLUSIVE) - _families(line_ev))),
            "stale": stale(c, r)}


def match_level(c: Any, r: Reading) -> str:
    """exact: the title names the line's event AND its place or subject, and the clip was not uploaded before the event;
    contextual: the line's place / subject / story place with an event of the same family (or a line that names no event), or an exact
    match filmed earlier; atmospheric (= illustrative): anything else. A place name alone is never exact (Stage B.3)."""
    if getattr(c, "level_hint", "") == "contextual":
        return "contextual"
    dm = dimensions(c, r)
    anchored = dm["place_title"] or dm["subject_title"]
    if dm["line_events"] and dm["event_title"] and anchored and not dm["stale"]:
        return "exact"
    where = dm["place"] or dm["subject"] or dm["context"]
    if where and (dm["event_family"] or not dm["line_events"]):
        return "contextual"
    return "atmospheric"


def reject(c: Any, r: Reading, film_date: Optional[_dt.date] = None, story: Optional[Tuple[_dt.date, _dt.date]] = None) -> List[str]:
    """Reasons this candidate cannot illustrate the reading ([] = it may). Dates: only a date the sentence STATES can reject footage filmed
    before it; footage of the story's place from inside the story's period is kept as contextual instead (a historical film)."""
    why: List[str] = []
    hay = _hay(c)
    title = fold(c.title)
    places = [p.name for p in r.places if p.kind != "region" or p.site_type]
    specific = [k for k in r.key_terms if k[:1].isupper()]
    tier = channel_tier(c.channel)
    # format
    fm = _FORMAT.search(c.title or "")
    if fm:
        why.append(f"format: '{fm.group(0)}' in the title")
    dur = c.duration
    if dur is None and (getattr(c, "details", None) or {}).get("is_live"):
        why.append("format: live stream")
    if dur is not None and dur < MIN_VIDEO_S:
        why.append(f"format: only {dur:.0f} s long")
    if dur and dur > LONG_EVENT_S and ({"EVENT", "MOVEMENT"} & set(r.types)):
        why.append(f"format: {dur / 60:.0f}-minute programme for an event scene")
    if tier == "commentary":
        why.append(f"format: commentary channel ({c.channel})")
    elif tier in ("aggregator", "unknown") and dur and dur > 360 and ({"EVENT", "MOVEMENT"} & set(r.types)):
        why.append(f"format: {dur / 60:.0f}-minute programme from a re-upload channel")
    # the CSV prompt: what the writer asked to see. The clip must name its subject AND show one more thing it asks for ('Moskva' +
    # 'sinking'; 'Snake Island' + 'stamp'), for at least one '||' alternative (Moskva 043/044: Odesa building strikes passed on 'Snake
    # Island' or 'Odesa' alone)
    parts = [p_ for p_ in (getattr(r, "prompt_parts", None) or []) if p_.get("names") or p_.get("words")]
    if any(p_.get("words") for p_ in parts):
        parts = [p_ for p_ in parts if p_.get("words")]     # a name-only alternative ('Snake Island February 2022') says nothing about the picture
    if parts:
        def has_form(w: str) -> bool:                       # 'launch' ~ 'launches', 'confirm' ~ 'confirmed', 'sink' ~ 'sinking'
            stem = re.sub(r"(?:ing|ed|es|s)$", "", w) if len(w) > 5 else w
            return _has(hay, w) or bool(re.search(r"\b" + re.escape(stem) + r"(?:s|es|ed|d|ing)?\b", hay))

        def fits(p_: Dict[str, List[str]]) -> bool:
            nm = [n for n in p_.get("names", []) if _has(hay, n)]
            wd = [w for w in p_.get("words", []) if has_form(w)]
            if p_.get("names") and not nm:
                return False
            return bool(wd) or len(nm) >= 2 or not p_.get("words")
        if not any(fits(p_) for p_ in parts):
            why.append("prompt: the clip does not show what the CSV prompt asks for")
    # entity (a generic CSV prompt, no names, was matched above: troops / jets / winter need no sentence noun spelled the same way)
    generic_prompt = bool(parts) and not any(p_.get("names") for p_ in parts)
    if generic_prompt:
        pass
    elif specific:
        if not any(_has(hay, k) for k in specific):
            why.append(f"entity: none of {', '.join(specific[:4])} named")
        else:
            from .narration_read import reference_only

            refs = [k for k in specific if reference_only(r.text, k)]
            if refs and not any(_has(hay, k) for k in specific if k not in refs):
                why.append(f"entity: names only {', '.join(refs[:2])}, which the sentence uses as a reference point, not its subject")
    elif r.key_terms:
        if not any(_has(hay, k) for k in r.key_terms):
            why.append(f"entity: none of {', '.join(r.key_terms[:3])} named")
    # geography: the title is about another place
    if places:
        own = {fold(p).lower() for p in places}
        from .narration_read import COUNTRIES
        other = [(n, co) for n, co in _known_places_in(fold(c.title or "")) if fold(n).lower() not in own and n not in COUNTRIES and
                 not any(fold(n).lower() in o or o in fold(n).lower() for o in own)]
        if other and not any(_has(fold(c.title).lower(), k) for k in specific or places):
            why.append(f"geography: about {other[0][0]}, not {places[0]}")
    # country: the title is about a country the narration never names
    named = set(r.countries) | {"Russia", "Ukraine"}
    foreign = [n for n, pats in _OTHER_COUNTRIES.items() if n not in named and re.search(pats, title, re.I)]
    if foreign:
        why.append(f"country: about {foreign[0]}, which the narration does not name")
    # side
    if r.actor:
        t_actor = reading_actor(c.title or "", [])
        if t_actor and t_actor != r.actor and not re.search(r"\b(repel|repelled|shot down|intercept|destroy(ed|s)? .{0,20}(attack|assault))", title, re.I):
            why.append(f"side: the title's actor is {t_actor}, the narration's is {r.actor}")
    # subject class
    low = r.text.lower()
    if re.search(r"\brefiner", low) and re.search(r"\b(warehouse|logistics|wildberries|ozon)\b", title, re.I) and not re.search(r"refiner", title, re.I):
        why.append("subject: a warehouse, not a refinery")
    if re.search(r"\b(gasoline|petrol|diesel)\b", low) and re.search(r"\b(natural gas|lng|gas imports|gas pipeline|russian gas)\b", title, re.I):
        why.append("subject: natural gas, not motor fuel")
    if re.search(r"\b(us|u\.s\.|american)\b.{0,15}\b(gas|gasoline) prices\b|\$\s?\d", title, re.I) and "Russia" in (r.countries or []):
        why.append("subject: US prices, not Russia's")
    if re.search(r"\brepair", low) and re.search(r"\b(explosion|explodes|blast|flies off|erupts|hit|strike|struck|attack)\b", title, re.I) \
            and not re.search(r"repair", title, re.I):
        why.append("subject: an attack, the narration is about repairs")
    # event (Stage B.3): the title is about another kind of event (a business forum, a protest, a meeting) than the line, or an event
    # line's clip names its place / subject but nothing of its event
    dm = dimensions(c, r)
    if dm["event_conflict"]:
        why.append(f"event: the title is about {'/'.join(dm['title_events'])}, the line about {'/'.join(dm['line_events'])}")
    elif dm["line_events"] and ({"EVENT", "MOVEMENT"} & set(r.types)) and not dm["event_family"] and (dm["place"] or dm["subject"]):
        why.append(f"event: names the place or subject but nothing of the {'/'.join(dm['line_events'])}")
    # time (event date = what the sentence says; upload date = when the clip appeared; film date = when this documentary is made)
    up = _upload(c)
    parts_ = [p_ for p_ in (getattr(r, "prompt_parts", None) or []) if p_.get("names") or p_.get("words")]
    generic = bool(parts_) and not any(p_.get("names") for p_ in parts_)
    if up and film_date and not generic:      # a generic picture (troops, jets, a refinery fire, winter) has no date to keep
        stated = getattr(r, "date_source", "stated") in ("stated", "")
        win = event_date(r, film_date) if stated else None
        if win and up < win[0]:
            if story and story[0] - STORY_SLACK <= up and _names_context(c, r):
                c.level_hint = "contextual"        # filmed earlier in the same story (the battle before this sentence's date)
            else:
                why.append(f"time: uploaded {up} before the event ({win[0]}), and not footage of the story's earlier events")
        elif story and up < story[0] - STORY_SLACK:
            why.append(f"time: uploaded {up}, before anything this film narrates ({story[0]})")
        elif not win and not story and "EVENT" in r.types and abs((film_date - up).days) > 730:
            why.append(f"time: uploaded {up}, years away from this news film")
    return why


def score(c: Any, r: Reading, film_date: Optional[_dt.date] = None) -> float:
    hay = _hay(c)
    s = TIER_SCORE.get(channel_tier(c.channel), 0.3)
    s += {"exact": 1.5, "contextual": 0.5, "atmospheric": -1.0}[match_level(c, r)]
    s += 1.2 * sum(1 for k in r.key_terms[:4] if _has(hay, k))
    s += 0.6 * min(3, len(getattr(c, "queries", []) or []))
    s += 0.4 * (1.0 / max(1, getattr(c, "rank", 5)))
    if c.duration:
        s += 1.0 if c.duration <= SHORT_RAW_S else (0.3 if c.duration <= 600 else -0.5)
    if getattr(c, "verified", False):
        s += 0.3
    parts = [p_ for p_ in (getattr(r, "prompt_parts", None) or []) if p_.get("names") or p_.get("words")]
    if parts:                       # the clip that shows more of what the CSV prompt asks for wins
        terms = {x for p_ in parts for x in list(p_.get("names", [])) + list(p_.get("words", []))}
        s += 0.8 * min(4, sum(1 for x in terms if _has(hay, x)))
    generic = bool(parts) and not any(p_.get("names") for p_ in parts)
    if generic:
        # reference 2026-11-10 ("GIANT FIREBALLS"): generic pictures are clean b-roll, never a news programme or a talk
        title = fold(c.title or "")
        if _BROLL.search(title):
            s += 1.0
        if _TALK.search(title):
            s -= 1.0
    up = _upload(c)
    win = event_date(r, film_date) if film_date and not generic else None
    if up and win:
        lag = (up - win[0]).days
        s += 1.0 if 0 <= lag <= 10 else (0.3 if 0 <= lag <= 45 else -0.3)
    return round(s, 3)


_BROLL = re.compile(r"\b(footage|b-?roll|combat|drone video|drone footage|training|exercises?|drills?|in action|pov|helmet ?cam|4k)\b", re.I)
_TALK = re.compile(r"\b(news|live|interview|explained|analysis|update|briefing|podcast|debate|reacts?|breaking|what we know)\b", re.I)


def rank(cands: Sequence[Any], r: Reading, film_date: Optional[_dt.date] = None,
         story: Optional[Tuple[_dt.date, _dt.date]] = None) -> Tuple[List[Tuple[float, Any]], List[Tuple[Any, List[str]]]]:
    """(accepted sorted best first as (score, candidate), rejected as (candidate, reasons))."""
    ok, bad = [], []
    for c in cands:
        why = reject(c, r, film_date, story)
        if why:
            bad.append((c, why))
        else:
            ok.append((score(c, r, film_date), c))
    ok.sort(key=lambda x: -x[0])
    return ok, bad


# ------------------------------------------------------------------------------------------------------------------ no repeats -----
HASH_NEAR = 10
HASH_MIN_TILES = 2
MAX_MOMENTS_PER_VIDEO = 1          # Moskva 044: two moments of one Reuters video in scenes 3 and 10 read as the same clip twice


def hamming(a: str, b: str) -> int:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except (TypeError, ValueError):
        return 64


@dataclass
class Used:
    """Every moment placed in the film so far: a new one may not overlap one (same video) or show the same picture (another URL)."""
    moments: List[Dict[str, Any]] = field(default_factory=list)

    def conflict(self, video_id: str, start: float, end: float, hashes: Sequence[str] = ()) -> str:
        same = [m for m in self.moments if m["video_id"] == video_id]
        for m in same:
            if start < m["end"] - 1.0 and m["start"] < end - 1.0:
                return f"repeat: same seconds as scene {m['scene']}"
        if len(same) >= MAX_MOMENTS_PER_VIDEO:
            return f"repeat: {MAX_MOMENTS_PER_VIDEO} moments of this video already used"
        if hashes:
            for m in self.moments:
                if not m.get("hashes"):
                    continue                           # another moment of the SAME video can still show the same picture (render 041)
                near = sum(1 for h in hashes if any(hamming(h, x) <= HASH_NEAR for x in m["hashes"]))
                if near >= HASH_MIN_TILES:
                    return f"repeat: same picture as scene {m['scene']} ({m['video_id']}" + (", another moment)" if m["video_id"] == video_id else ", another upload)")
        return ""

    def add(self, scene: str, video_id: str, start: float, end: float, hashes: Sequence[str] = ()) -> None:
        self.moments.append({"scene": scene, "video_id": video_id, "start": start, "end": end, "hashes": list(hashes)})
