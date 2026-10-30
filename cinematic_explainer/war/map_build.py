"""War Documentary map stretches: wherever the narration runs without footage, one political map stays up and builds with it.

Reference study (docs/war/REFERENCE_PATTERNS.md, items 1-5, 24-25): about half of a good war explainer is a map that stays on screen for
20-90 s while something new lands every 2-4 s. A scene-by-scene plan instead cuts between short maps, tags and an empty backdrop.

build(plan, rows, cat, log_by_no, counts, notes)   called by direction.apply (config "map_build", default True) before the gap fillers.
  For each run of consecutive scenes without footage (at least MIN_RUN_S long):
  - every country the run names gets a fill in its colour for the whole video (maps_tactical.country_roles), lit when it is named;
  - every town gets a marker when it is named (a pulsing ring when the sentence is about a strike), a route when the sentence moves from one
    named place to another, an explosion for a strike, small arrows flying in when drones are named;
  - the camera steps to what each sentence names (towns, else the countries), at the moment it is named;
  - each sentence adds one card to the stack on the right (dark for a date, red for an attack or loss, blue for allies and defence, white for
    a figure), its words taken from the narration; the stack clears after three cards;
  - nothing on screen sits unchanged for more than MAX_STILL_S: a pulse on the place in view is added where the narration gives nothing new.
  A run that names no place keeps the last map's countries and camera (the story's own map), and its cards. A video that names no place at
  all is left exactly as before. The map is split around the planner's own full-frame cards (one map in pieces, never restarted).
  The direction pass's short maps, tags and stickers inside the run are replaced by the long map; stamps, numbers and layouts are kept.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..render import Layer
from . import semantics as S

MIN_RUN_S = 6.0          # shorter stretches keep the scene-by-scene direction
MIN_PIECE_S = 1.5        # a free gap shorter than this between cards is not worth a map piece
MAX_STILL_S = 4.0        # the longest time nothing new lands on the map
CHIPS_PER_GROUP = 3
REPLACED = {"tac_map", "tac_route", "kit_tag", "kit_sticker", "map_card", "kit_scale"}

_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
_DATE = re.compile(rf"\b(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})|(?:{_MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?|(?:early|mid|late)[- ](?:{_MONTHS})|"
                   rf"(?:in|by|since|last|this)\s+(?:{_MONTHS})|(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b", re.IGNORECASE)
_THREAT = re.compile(r"\b(attack\w*|strike|strikes|struck|kill\w*|destroy\w*|threat\w*|shot down|sank|sunk|sink\w*|violat\w*|invad\w*|invasion|"
                     r"sabotage\w*|explosion\w*|exploded|bomb\w*|missile\w*|casualt\w*|losses|lost|dead|wounded|breach\w*|incursion\w*)\b", re.IGNORECASE)
_ALLY = re.compile(r"\b(nato|alliance|allies|ally|allied|member|members|defen[cs]e|defend\w*|support\w*|aid|protect\w*|deploy\w*|reinforc\w*|"
                   r"partners?|coalition|article (?:four|five|4|5)|treaty)\b", re.IGNORECASE)
_STRIKE = re.compile(r"\b(strike|strikes|struck|hit|hits|attack|attacked|attacks|shelled|bombed|targeted|exploded|explosion)\b", re.IGNORECASE)
_DRONES = re.compile(r"\b(drones?|uavs?|shaheds?|swarms?)\b", re.IGNORECASE)
_SKIP = re.compile(r"\b(subscribe|this channel|a quick word|like and share|comment below|notification bell|this is \w+ post)\b", re.IGNORECASE)
_VERB_END = {"went", "came", "have", "has", "had", "been", "is", "was", "were", "are", "made", "can", "could", "will", "would", "did", "do",
             "said", "got", "be", "being", "say", "says", "sits", "find"}
_BOUND = {"from", "to", "in", "on", "at", "with", "for", "by", "into", "over", "after", "before", "and", "but", "because", "while", "when",
          "which", "that", "who", "of", "across", "along", "without", "since"}
_STOP_END = {"of", "the", "a", "an", "to", "in", "on", "at", "with", "for", "by", "as", "from", "and", "or", "but", "that", "which", "is", "are", "it", "they", "we", "he", "she", "you", "how",
             "was", "were", "its", "their", "his", "her", "this", "these", "those", "into", "than"}


_ROLE = (r"(?:secretary(?: general)?|minister|president|chancellor|general|spokes(?:man|woman|person)|analyst|commander|chief|ambassador|admiral|"
         r"director|prime minister|foreign minister|defen[cs]e minister|researcher|professor|expert|official|envoy|senator)")
_NAME = r"((?:[A-Z][\w'-]+\s){1,2}[A-Z][\w'-]+)"
_SPK = [re.compile(r"\b((?:[A-Z][\w']*\s+)?(?:[a-z][\w-]*\s+){0,3}" + _ROLE + r"),\s+" + _NAME + r",", 0),      # Britain's defence secretary, Wes Streeting,
        re.compile(r"\b" + _NAME + r",\s+(?:a|an|the)\s+([^,]{0,40}?" + _ROLE + r"[^,]{0,30}),", 0),             # Michel Hofman, a Belgian analyst,
        re.compile(r"\b((?:NATO|EU|UN|US|U\.S\.|[A-Z][a-z]+(?:'s)?)\s+(?:[a-z]+\s+)?" + _ROLE + r")\s+" + _NAME + r"\b", 0)]   # NATO chief Mark Rutte
_NOT_NAME = {"The", "This", "That", "In", "On", "At", "And", "But", "When", "After", "Before", "So", "It", "He", "She", "They", "We"}
_CHAPTER = re.compile(r"^\W*(chapter|part)\s+(\w+)\b[\s,.:;—–-]*(.*)$", re.IGNORECASE)


def speaker_of(sentence: str) -> Optional[Tuple[str, str]]:
    """(name, role) when the sentence introduces a named person with a role, in its own words; else None."""
    for i, rx in enumerate(_SPK):
        m = rx.search(sentence)
        if not m:
            continue
        role, name = (m.group(1), m.group(2)) if i != 1 else (m.group(2), m.group(1))
        if name.split()[0] in _NOT_NAME or len(name) > 40:
            continue
        role = role.strip()
        return name.strip(), role[0].upper() + role[1:]
    return None


def chapter_of(sentence: str) -> Optional[Tuple[str, str]]:
    """("CHAPTER 1", "a rehearsal for the day after") for a sentence that opens a chapter or part; else None."""
    m = _CHAPTER.match(sentence.strip())
    if not m or not (m.group(2).isdigit() or m.group(2).lower() in ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")):
        return None
    sub = _clip_words(m.group(3).rstrip(".!?").split(), 2, 8)
    return f"{m.group(1)} {m.group(2)}".upper(), sub


_NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20, "hundred": 100}
_N = r"(\d[\d,]*|" + "|".join(_NUMW) + r")"
_RATIO = re.compile(r"\b" + _N + r"\s+(?:in|out of)\s+(?:every\s+)?" + _N + r"\s+((?:[a-zA-Z][\w'-]*\s?){1,5})", re.IGNORECASE)
_SOURCE = re.compile(r"\baccording to\s+((?:[A-Z][\w'.-]*\s?){1,4})")
_FOR_AGAINST = re.compile(r"\b(\d[\d,]*)\s+(for|in favou?r|yes)\b[^.]{0,12}?\b(\d[\d,]*)\s+(against|no|opposed)\b", re.IGNORECASE)
_VS = re.compile(r"\b(\d[\d,]*)\s+((?:[a-z][\w'-]*\s?){0,3}?),?\s*(?:compared (?:with|to)|versus|vs\.?|up from|down from|against)\s+(\d[\d,]*)\s*((?:[a-z][\w'-]*\s?){0,4})",
                 re.IGNORECASE)
_FROM_TO = re.compile(r"\bfrom\s+(\d[\d,]*%?)\s+(?:to|up to|down to)\s+(\d[\d,]*%?)(?![\w%])", re.IGNORECASE)


def _numtxt(x: str) -> str:
    return str(_NUMW.get(x.lower(), x))


def ratio_of(sentence: str) -> Optional[Dict[str, str]]:
    """'Eight in ten vessel strikes ...' -> {value: '8 in 10', label: 'vessel strikes', sub: 'according to Ambrey'}, in the narration's words."""
    m = _RATIO.search(sentence)
    if not m:
        return None
    a, b = _numtxt(m.group(1)), _numtxt(m.group(2))
    try:
        if not 0 < float(a.replace(",", "")) <= float(b.replace(",", "")):
            return None
    except ValueError:
        return None
    words = m.group(3).split()
    cut = next((i for i, w in enumerate(words) if w.lower() in _BOUND | {"were", "was", "are", "is", "had", "have"}), len(words))
    label = _clip_words(words[:cut], 1, 5)
    if not label:
        return None
    src = _SOURCE.search(sentence)
    return {"value": f"{a} in {b}", "label": label, "sub": ("according to " + src.group(1).strip(" .")) if src else ""}


def versus_of(sentence: str) -> Optional[Dict[str, str]]:
    """Two stated figures set against each other -> {a, a_label, b, b_label}; None unless both numbers are in the sentence."""
    m = _FOR_AGAINST.search(sentence)
    if m:
        return {"a": m.group(1), "a_label": m.group(2), "b": m.group(3), "b_label": m.group(4)}
    m = _VS.search(sentence)
    if m and m.group(1) != m.group(3):
        return {"a": m.group(1), "a_label": _clip_words(m.group(2).split(), 1, 3), "b": m.group(3), "b_label": _clip_words(m.group(4).split(), 1, 4)}
    m = _FROM_TO.search(sentence)
    if m and m.group(1) != m.group(2):
        return {"a": m.group(2), "a_label": "now", "b": m.group(1), "b_label": "before"}
    return None


def _fr(t: float) -> float:
    return round(float(t) * 25) / 25


def _clip_words(words: List[str], lo: int, hi: int) -> str:
    """The longest prefix of lo..hi words that does not end on a little word or a bare verb; '' when there is none."""
    for n in range(min(hi, len(words)), lo - 1, -1):
        last = words[n - 1].strip(",;:.!?").lower()
        if last not in _STOP_END and last not in _VERB_END:
            return " ".join(words[:n]).strip(" ,;:")
    return ""


def card_for(sentence: str) -> Optional[Dict[str, str]]:
    """One stack card from a sentence, in the narration's own words: {title, sub, variant} or None for a sentence too short to say anything."""
    text = sentence.strip().strip("\"'")
    if _SKIP.search(text) or chapter_of(text):
        return None                       # channel housekeeping is not a fact for the map; a chapter gets its own opener
    spk = speaker_of(text)
    if spk:
        return {"title": spk[0].upper(), "sub": spk[1], "variant": "white"}
    m = _DATE.search(text)
    if m:
        rest = (text[:m.start()] + " " + text[m.end():]).strip(" ,.;:")
        rest = re.sub(r"^(?:on|in|by|since|and|then)\s+", "", rest, flags=re.IGNORECASE)
        date = re.sub(r"^(?:in|by|since|last|this)\s+", "", m.group(0), flags=re.IGNORECASE)
        return {"title": date.upper(), "sub": _clip_words(rest.split(), 3, 9), "variant": "dark"}
    words = text.rstrip(".!?").split()
    if len(words) < 3:
        return None
    head = re.split(r"[,;:?!.—–]| - ", text.rstrip(".!?"))[0].split()
    if 2 <= len(head) <= 8 and len(" ".join(head)) <= 46:
        title = " ".join(head)                                           # a short clause is the whole title
    else:
        title = next((" ".join(head[:n]) for n in range(min(6, len(head) - 1), 2, -1)          # end where the clause breaks naturally
                      if head[n].lower() in _BOUND and head[n - 1].strip(",;:").lower() not in _STOP_END | _VERB_END), "")
        title = title or _clip_words(head, 3, 6) or _clip_words(words, 3, 6)
    if not title:
        return None
    rest_words = words[len(title.split()):]
    while rest_words and not re.search(r"\w", rest_words[0]):
        rest_words = rest_words[1:]
    sub = _clip_words([w.strip(",;:") for w in rest_words], 3, 10) if len(rest_words) >= 3 else ""
    variant = "red" if _THREAT.search(text) else "blue" if _ALLY.search(text) else "white" if re.search(r"\d", text) else "dark"
    return {"title": title.upper(), "sub": sub, "variant": variant}


def _place_names(sent: Any) -> List[str]:
    from .direction import _places

    return [e.name for e in _places(sent)]


def _country_names(sent: Any) -> List[str]:
    from .direction import _countries

    return [e.name for e in _countries(sent)]


def _runs(rows: Sequence[Dict[str, Any]], log_by_no: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
    out: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    for r in rows:
        dec = log_by_no.get(str(r["_no"]))
        if dec is not None and "no_footage" in dec.flags and str(r.get("text") or "").strip():
            if cur and r["_start"] - cur[-1]["_end"] > 0.6:
                out.append(cur)
                cur = []
            cur.append(r)
        else:
            if cur:
                out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _beats(run: Sequence[Dict[str, Any]], cat: Any) -> List[Dict[str, Any]]:
    """Per sentence of the run: absolute times, the places and countries it names, its card, strike/drone/motion cues."""
    beats = []
    for r in run:
        A = S.analyze_scene(str(r.get("text") or ""), cat, r.get("words"), r["_start"], r["_end"])
        for sent in A.sentences:
            a = max(r["_start"], A.time_at(sent.span[0]))
            b = min(r["_end"], max(a + 0.5, A.end_time_of(sent.span)))
            mo = sent.motion
            route = None
            if mo is not None and mo[0].kind == "place" and mo[1].kind == "place" and mo[0].name != mo[1].name and not (mo[0].country or mo[1].country):
                route = (mo[0].name, mo[1].name)
            beats.append({"a": a, "b": b, "text": sent.text, "places": _place_names(sent), "countries": _country_names(sent),
                          "card": card_for(sent.text), "strike": bool(_STRIKE.search(sent.text)), "drones": bool(_DRONES.search(sent.text)),
                          "route": route, "no": r["_no"]})
    return beats


def _plan_params(beats: List[Dict[str, Any]], t0: float, roles: Dict[str, str], context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """tac_map params for one run (times relative to t0), or None when neither the run nor an earlier map gives any geography."""
    from . import maps_tactical as MT

    rel = lambda t: _fr(max(0.0, t - t0))                                   # noqa: E731
    named_c: List[Tuple[str, float]] = []
    for bt in beats:
        for c in bt["countries"]:
            if c.lower() not in [x[0].lower() for x in named_c]:
                named_c.append((c, bt["a"]))
    MT.country_roles([c for c, _ in named_c], roles)
    places: List[Dict[str, Any]] = []
    seen_p: Dict[str, int] = {}
    glyphs: List[Dict[str, Any]] = []
    routes: List[Dict[str, Any]] = []
    focus: List[Any] = []
    focus_t: List[float] = []
    for bt in beats:
        for nm in bt["places"][:3]:
            if nm.lower() in seen_p or len(places) >= 8:
                continue
            p, _why = MT.resolve_place(nm)
            if p is None:
                continue
            seen_p[nm.lower()] = len(places)
            places.append({"name": nm, "kind": "ring" if bt["strike"] else "pin", "colour": "red" if bt["strike"] else "white", "start": rel(bt["a"]) + 0.3})
        here = [nm for nm in bt["places"] if nm.lower() in seen_p]
        if bt["strike"] and here:
            glyphs.append({"place": here[0], "kind": "explosion", "start": rel(bt["a"]) + 0.8})
        if bt["drones"] and here:
            glyphs.append({"place": here[0], "kind": "swarm", "start": rel(bt["a"]) + 0.5})
        if bt["route"] and all(x.lower() in seen_p for x in bt["route"]):
            routes.append({"from": bt["route"][0], "to": bt["route"][1], "style": "dashed_red" if bt["strike"] else "dashed_blue", "start": rel(bt["a"]) + 0.9})
        cs = [c for c in bt["countries"] if MT.G.find_country(c) is not None]
        if len(cs) > 1 or focus:
            cs = [c for c in cs if MT.G.find_country(c).iso != "RUS"] or cs[:0]   # Russia as the subject of a sentence is no place to fly to
        step: Any = here[:3] if here else [{"country": c} for c in cs[:2]]
        if step and (not focus or step != focus[-1]) and (not focus_t or rel(bt["a"]) - focus_t[-1] >= 3.0):
            focus.append(step)
            focus_t.append(rel(bt["a"]))
    if not places and not named_c and not routes:
        if not context:
            return None
        fills = [dict(f, start=0.0) for f in context.get("fills", [])]
        focus, focus_t = ([context["focus"][-1]], [0.0]) if context.get("focus") else ([], [])
        places = [dict(p, start=0.3) for p in context.get("places", [])[-3:]]
    else:
        fills = []
        iso_t: Dict[str, float] = {}
        for c, a in named_c:
            f = MT.G.find_country(c)
            if f is not None:
                iso_t.setdefault(f.iso, a)
        for iso, role in roles.items():
            name_t = iso_t.get(iso)
            if iso in ("RUS", "UKR"):
                fills.append({"iso3": iso, "role": role, "start": 0.0})     # the war's two sides stay in their colours on every map
            elif name_t is not None:
                fills.append({"iso3": iso, "role": role, "start": rel(name_t) if rel(name_t) > 0.4 else 0.0})
        if focus_t:
            focus_t[0] = 0.0
    chips: List[Dict[str, Any]] = []
    for bt in beats:
        if bt["card"] and (not chips or rel(bt["a"]) - chips[-1]["start"] >= 1.6):
            chips.append(dict(bt["card"], start=rel(bt["a"]) + 0.4, group=len(chips) // CHIPS_PER_GROUP))
    return {"theme": "political", "fills": fills, "places": places, "glyphs": glyphs, "routes": routes, "focus": focus, "focus_times": focus_t,
            "chips": chips}


def _still_fix(params: Dict[str, Any], total: float) -> int:
    """Pulses on the place in view wherever nothing new would land for more than MAX_STILL_S. Returns how many were added."""
    events = sorted({0.0, total} | {float(x.get("start") or 0.0) for k in ("places", "glyphs", "routes", "chips", "fills") for x in params.get(k) or []}
                    | {float(x) for x in params.get("focus_times") or []})
    anchors = [p["name"] for p in params.get("places") or []]
    added = 0
    for a, b in zip(events, events[1:]):
        t = a + MAX_STILL_S - 0.5
        while b - t > 0.5:
            live = [p["name"] for p in params.get("places") or [] if float(p.get("start") or 0.0) <= t] or anchors
            if not live:
                return added
            params.setdefault("glyphs", []).append({"place": live[-1], "kind": "ring", "start": _fr(t)})
            added += 1
            t += MAX_STILL_S - 0.5
    return added


def build(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any, log_by_no: Dict[str, Any], counts: Dict[str, int], notes: List[str],
          full_kinds: Sequence[str]) -> None:
    roles: Dict[str, str] = {}
    context: Optional[Dict[str, Any]] = None
    runs = _runs(rows, log_by_no)
    every = " ".join(str(r.get("text") or "") for r in rows)
    from . import maps_tactical as MT

    MT.country_roles([nm for nm, rx in (("Russia", r"\brussia\w*"), ("Ukraine", r"\bukrain\w*")) if re.search(rx, every, re.IGNORECASE)], roles)
    for run in runs:          # the whole video's countries get their colours in order of first mention, even before the first map
        for bt in _beats(run, cat):
            from . import maps_tactical as MT

            MT.country_roles(bt["countries"], roles)
    for run in runs:
        t0, t1 = run[0]["_start"], run[-1]["_end"]
        if t1 - t0 < MIN_RUN_S:
            continue
        beats = _beats(run, cat)
        params = _plan_params(beats, t0, roles, context)
        if params is None:
            continue
        total = _fr(t1 - t0)
        stills = _still_fix(params, total)
        inside = lambda ly: ly.start >= t0 - 0.05 and ly.end <= t1 + 0.6   # noqa: E731
        merged = [ly for ly in plan.layers if inside(ly) and ly.kind in REPLACED]
        plan.layers[:] = [ly for ly in plan.layers if ly not in merged]
        blocks = sorted((ly.start, ly.end) for ly in plan.layers if ly.kind in full_kinds and ly.end > t0 and ly.start < t1)
        cur, pieces = t0, []
        for a, b in blocks + [(t1, t1)]:
            if a - cur >= MIN_PIECE_S:
                pieces.append((cur, a))
            cur = max(cur, b)
        for a, b in pieces:
            plan.layers.append(Layer("tac_map", _fr(a), _fr(b), dict(params, t_offset=_fr(a - t0), total_dur=total), dim=False))
        for r in run:
            dec = log_by_no.get(str(r["_no"]))
            if dec is not None and pieces:
                dec.flags.append("dir:map_build")
                dec.candidates.append({"kind": "tac_map", "score": 0.0, "reason": f"direction: one map builds across {len(run)} scenes without footage "
                                       f"({len(params['chips'])} cards, {len(params['places'])} places)", "accepted": True, "start": _fr(t0), "end": _fr(t1)})
        if pieces:
            counts["map_build"] = counts.get("map_build", 0) + 1
            counts["map_build_s"] = round(counts.get("map_build_s", 0) + sum(b - a for a, b in pieces), 2)
            counts["map_build_replaced"] = counts.get("map_build_replaced", 0) + len(merged)
            counts["map_build_pulses"] = counts.get("map_build_pulses", 0) + stills
            if params.get("places") or params.get("fills"):
                context = params
