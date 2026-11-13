"""Aviation Flow prompt builder v2 (docs/aviation/MASTER_PLAN.md section 5, STICKER_STORY_PLAN.md Part 2 B/C/E). Every prompt is built from the
film's bible (aviation/bible.py) plus one line, never from the line alone: the line's era look + the airline's livery of that era + the place
and its landmark + the chapter's mood, then the fixed no-text clause. aviation/flow.py (the older, simpler prompts) is untouched.

    image_prompt(bible, line_no, use, subject=None) -> {prompt, refs, look, chip, use} | None
        uses: sticker  era_plate  future_aircraft  explainer_plate  card_picture  place_plate  metaphor  cabin  thumbnail
    video_prompt(bible, line_no, use, subject=None) -> {prompt, refs, look, chip, use} | None
        uses: image_to_video  cast_moment  ops_broll  place_reconstruction  sticker_to_real
    why_not(bible, line_no, use, subject=None) -> ""  (allowed)  |  the reason a prompt is refused (what image_prompt / video_prompt returned None for)
    references(bible, line_no, subject=None) -> [ref ids, at most 3, most specific first]   ids: hero:<airline>:<era>  cast:<role>  place:<airport>
    hero_list(bible) / cast_list(bible) / place_list(bible) -> [{id, prompt, refs, lines, ...}]   everything the film needs made ONCE (library step)
    real_people(text) -> [names]    named_event(text) -> bool    the two refusal rules, usable on their own

`subject` per use: sticker = aircraft id or a prop ("ticket", "cash stack"); future_aircraft = aircraft id; place_plate = airport id;
cast_moment = role; metaphor = a motif phrase; cabin = "first class" / "economy"; explainer_plate / card_picture / thumbnail = a short phrase.
Rules that never bend: the prompt ends with END ("no text, no letters, no logos, no watermark"); people are invented and unnamed (a line that
names a real person gets no face use: None); a named real event (crash, hijack, disaster ...) is never staged as real (None); the chip is
"AI ILLUSTRATION". Flow paints, code states facts: no number, name or label is ever asked of Flow.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from . import bible as B
from . import catalog as C

END = "No text, no letters, no logos, no watermark."
PEOPLE = "Any people are invented, unnamed and generic, never a real person."
CHIP = "AI ILLUSTRATION"
IMAGE_USES = ("sticker", "era_plate", "future_aircraft", "explainer_plate", "card_picture", "place_plate", "metaphor", "cabin", "thumbnail")
VIDEO_USES = ("image_to_video", "cast_moment", "ops_broll", "place_reconstruction", "sticker_to_real")
FACE_USES = ("cast_moment", "card_picture", "cabin", "thumbnail")              # a real person's face could appear: refused when the line names one
EVENT_USES = ("cast_moment", "place_reconstruction", "image_to_video", "sticker_to_real", "ops_broll", "era_plate", "card_picture")
STICKER_LOOK = "clean die-cut sticker illustration, flat bold shapes, thin white outline, plain solid black background (#000000)"
EXPLAINER_LOOK = "clean isometric explainer illustration, soft flat shading, light neutral background"
THUMB_LOOK = "bold high-contrast poster composition, saturated colour, strong silhouette, empty area kept for a title"
SHEET_LOOK = "plain light grey studio background, even soft light, reference sheet"

# ------------------------------------------------------------------------------------------------------------ refusal rules
_TITLES = r"(?:Prime Minister|Deputy Prime Minister|Minister|President|Captain|Chairman|Chairwoman|Sir|Dr|Mr|Mrs|Ms|CEO|Chief Executive|Sultan|Tun|Tan Sri|Dato)"
_TITLE_NAME = re.compile(r"\b" + _TITLES + r"\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})")
_CAPSEQ = re.compile(r"\b([A-Z][a-z]+(?:\s+(?:bin|binti|van|de|al|von)\s+|\s+)(?:[A-Z][a-z]+)(?:\s+[A-Z][a-z]+){0,2})\b")
_NOT_NAME = set("""the a an in on at by of to and but or so as it its this that these those then today later when while after before once now first second third last
        prime minister deputy president captain chairman chairwoman chief executive officer officers government governments board airline airlines airways
        airport airports air force royal national international federation kingdom republic union united states state world war civil cold
        january february march april may june july august september october november december monday tuesday wednesday thursday friday saturday sunday
        boeing airbus douglas lockheed concorde jet jumbo comet british malaysian malayan singaporean american european asian african australian indian chinese
        japanese french german dutch swiss emirati saudi turkish qatari korean thai malaysia malaya singapore britain england france germany india china japan
        america europe asia africa australia kuala lumpur hong kong new york los angeles san francisco middle east southeast south north east west""".split())
_EVENT = re.compile(r"\b(?:crash\w*|hijack\w*|disaster\w*|accident\w*|shot down|shoot[- ]?down|disappear\w*|went missing|collision\w*|collid\w*|bomb\w*|"
                    r"terror\w*|attack\w*|explo(?:de|ded|sion)\w*|killed|fatalit\w*|MH\s?\d{3,4}|mid-?air|emergency landing|ditch\w*)\b", re.I)


def _blank_catalog(text: str) -> str:
    out = text
    spans = []
    for fn in (C.find_airlines, C.find_airports, C.find_aircraft):
        spans += [(m.start, m.end) for m in fn(text)]
    for s, e in sorted(spans, reverse=True):
        out = out[:s] + " " * (e - s) + out[e:]
    return out


def real_people(text: str) -> List[str]:
    """Names of real people a line seems to mention (title + name, or two or more capitalised name words). Over-cautious on purpose."""
    t = _blank_catalog(str(text or ""))
    found: List[str] = []
    for m in _TITLE_NAME.finditer(t):
        words = [w for w in m.group(1).split() if w.lower() not in _NOT_NAME]
        if words:
            found.append(" ".join(words))
    for m in _CAPSEQ.finditer(t):
        words = [w for w in m.group(1).split() if w.lower() not in _NOT_NAME and w not in ("bin", "binti", "van", "de", "al", "von")]
        if len(words) >= 2 and not any(" ".join(words) in f for f in found):
            found.append(" ".join(words))
    return found


def named_event(text: str) -> bool:
    return bool(_EVENT.search(str(text or "")))


# ------------------------------------------------------------------------------------------------------------ context
class _Ctx:
    def __init__(self, b: B.Bible, n: int):
        ln = b.lines[n]
        self.b, self.n, self.ln = b, n, ln
        self.text = ln["text"]
        self.year = ln["year"]
        self.era = ln["era"]
        self.look = B.era_look(self.era)
        self.airline_id = ln["airline"]
        self.airline = C.get_airline(self.airline_id) if self.airline_id else None
        self.livery = (b.livery.get(self.airline_id or "") or {}).get(self.era)
        fl = (b.fleet.get(self.airline_id or "") or {}).get(self.era)
        tid = (ln["aircraft"] or [None])[0] or (fl["types"][0] if fl else None)
        self.assumed = not ln["aircraft"] and (fl is None or fl["assumed"])
        if not tid:
            tid = B._story_era_type(self.year or 0)
        self.aircraft = B.aircraft_entry(tid) or {"id": tid, "name": "an airliner"}
        self.place = b.places.get(ln["place"] or "")
        self.mood = B.mood_words(ln["mood"])
        self.roles = ln["roles"]

    @property
    def airline_name(self) -> str:
        return (self.livery or {}).get("name") or (self.airline or {}).get("name") or ""

    @property
    def livery_text(self) -> str:
        if self.livery:
            return f"{self.airline_name} livery, {self.livery['text']}"
        return "a plain airline livery of the era"

    @property
    def place_text(self) -> str:
        if not self.place:
            return ""
        lm = B.landmark(self.place["id"], self.year) or self.place.get("landmark") or ""
        return f"{self.place['city'] or self.place['name']}" + (f" with {lm}" if lm else "")

    def aircraft_phrase(self) -> str:
        return f"{self.aircraft['name']} in {self.livery_text}"

    def tail(self, people: bool = True, place: bool = True) -> str:
        parts = [f"Period look: {self.look}."]
        if place and self.place_text:
            parts.append(f"Setting: {self.place_text}.")
        parts.append(f"Mood: {self.mood['words']}.")
        if people:
            parts.append(PEOPLE)
        return " ".join(parts)


def _ctx(b: B.Bible, n: int) -> Optional[_Ctx]:
    return _Ctx(b, n) if isinstance(n, int) and 0 <= n < len(b.lines) else None


def _topic(c: _Ctx, subject: Optional[str]) -> str:
    if subject:
        return str(subject)
    t = re.sub(r"\s+", " ", c.text).strip()
    t = re.sub(r"\d[\d,.:%]*", "", t)                    # numbers belong to code, never to Flow
    return t[:140].rstrip(" ,;:")


def why_not(b: B.Bible, line_no: int, use: str, subject: Optional[str] = None) -> str:
    c = _ctx(b, line_no)
    if c is None:
        return f"no line {line_no}"
    if use not in IMAGE_USES + VIDEO_USES:
        return f"unknown use '{use}'"
    people = real_people(c.text)
    if use in FACE_USES and people:
        return f"line names a real person ({', '.join(people)}): no face picture"
    if use in EVENT_USES and named_event(c.text):
        return "line is a named real event: never staged as real, use a card or footage"
    if use == "place_plate" and not (c.place or (subject and b.places.get(str(subject).replace("place:", "")))):
        return "no place named in or before this line"
    if use == "metaphor" and not (subject or b.motifs):
        return "the script has no repeated motif to draw"
    if use == "cast_moment":
        role = _role(b, c, subject)
        if not role:
            return "no unnamed role in or around this line"
    return ""


def _role(b: B.Bible, c: _Ctx, subject: Optional[str]) -> Optional[str]:
    s = str(subject or "").replace("cast:", "")
    if s and (s in b.cast or any(s == k for k, _, _ in B._ROLES)):
        return s
    if c.roles:
        return c.roles[0]
    return next(iter(b.cast), None)


def _motif(b: B.Bible, c: _Ctx, subject: Optional[str]) -> str:
    if subject:
        return str(subject)
    for m in b.motifs:
        if c.n in m["lines"]:
            return m["phrase"]
    return b.motifs[0]["phrase"] if b.motifs else ""


def _uniform(b: B.Bible, role: str, c: _Ctx) -> str:
    e = b.cast.get(role) or {}
    aid = e.get("airline") or c.airline_id
    lv = (b.livery.get(aid or "") or {}).get(e.get("era") or c.era)
    words = lv["color_words"] if lv else "dark navy"
    era = e.get("era") or c.era
    return f"a {words} uniform of the {'1950s' if era == 'pre1960' else era} period"


# ------------------------------------------------------------------------------------------------------------ references
def references(b: B.Bible, line_no: int, subject: Optional[str] = None) -> List[str]:
    """Reference image ids for a Flow prompt, at most 3, most specific first, only ids the library step makes (see *_list)."""
    c = _ctx(b, line_no)
    if c is None:
        return []
    refs: List[str] = []
    hero = B.hero_id(c.airline_id, c.era) if c.airline_id and c.era in (b.fleet.get(c.airline_id) or {}) else None
    s = str(subject or "")
    role = s.replace("cast:", "")
    pid = s.replace("place:", "")
    if role in b.cast:
        refs.append(B.cast_id(role))
    elif pid in b.places:
        refs.append(B.place_id(pid))
    elif s and (C.get_airline(s) or {}):
        a = s
        if c.era in (b.fleet.get(a) or {}):
            refs.append(B.hero_id(a, c.era))
    if hero:
        refs.append(hero)
    for r in c.roles:
        refs.append(B.cast_id(r))
    if c.place:
        refs.append(B.place_id(c.place["id"]))
    out: List[str] = []
    for r in refs:
        if r not in out and _known(b, r):
            out.append(r)
    return out[:3]


def _known(b: B.Bible, ref: str) -> bool:
    kind, _, rest = ref.partition(":")
    if kind == "hero":
        aid, _, era = rest.partition(":")
        return era in (b.fleet.get(aid) or {})
    if kind == "cast":
        return rest in b.cast
    if kind == "place":
        return rest in b.places
    return False


# ------------------------------------------------------------------------------------------------------------ images
def _pack(prompt: str, refs: List[str], look: str, use: str, line_no: int) -> Dict[str, Any]:
    return {"prompt": prompt.strip() + " " + END, "refs": refs[:3], "look": look, "chip": CHIP, "use": use, "line": line_no}


def image_prompt(b: B.Bible, line_no: int, use: str, subject: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if use not in IMAGE_USES or why_not(b, line_no, use, subject):
        return None
    c = _ctx(b, line_no)
    refs = references(b, line_no, subject)
    s = str(subject or "")
    if use == "sticker":
        ac = B.aircraft_entry(s) if s else None
        if ac or not s:
            ac = ac or c.aircraft
            body = (f"A die-cut sticker illustration of {ac['name']} in {c.livery_text}, flat side view, whole aircraft inside the frame, "
                    f"nose to the right, thin white outline and soft shadow, plain solid black background (#000000).")
        else:
            body = f"A die-cut sticker illustration of {s}, drawn as a simple object, thin white outline and soft shadow, plain solid black background (#000000)."
        return _pack(f"{body} {STICKER_LOOK}. Period detail: {c.look}. Mood: {c.mood['feel']}. {PEOPLE}", refs, STICKER_LOOK, use, line_no)
    if use == "era_plate":
        body = (f"An establishing photograph of an airport apron and terminal of the time{(' at ' + c.place_text) if c.place_text else ''}, "
                f"{c.aircraft_phrase()} parked, ground crew in clothes of the period seen from behind, wide shot.")
        return _pack(f"{body} {c.tail(place=False)}", refs, c.look, use, line_no)
    if use == "future_aircraft":
        ac = (B.aircraft_entry(s) if s else None) or c.aircraft
        body = f"A believable concept image of {ac['name']} at an airport gate at golden hour, three-quarter view, the aircraft whole and sharp, in {c.livery_text}."
        return _pack(f"{body} Period look: {B.era_look('modern')}. Mood: {c.mood['words']}. {PEOPLE}", refs, B.era_look("modern"), use, line_no)
    if use == "explainer_plate":
        body = (f"A clean explainer illustration of: {_topic(c, subject)}. Drawn without any labels, arrows, numbers or captions "
                f"(those are added later by code), one clear subject, room around it.")
        return _pack(f"{body} {EXPLAINER_LOOK}. Period detail: {c.look}. {PEOPLE}", refs, EXPLAINER_LOOK, use, line_no)
    if use == "card_picture":
        body = f"A picture to sit inside a news card about: {_topic(c, subject)}. {c.aircraft_phrase() if c.airline else 'An airliner of the time'} as the main subject, centred, calm background."
        return _pack(f"{body} {c.tail()}", refs, c.look, use, line_no)
    if use == "place_plate":
        p = b.places.get(s.replace("place:", "")) or c.place
        lm = B.landmark(p["id"], c.year) or p.get("landmark") or ""
        body = (f"An establishing view of {p['city'] or p['name']} airport area" + (f" with {lm}" if lm else "") +
                ", an airliner on the apron or climbing out, wide cinematic composition.")
        return _pack(f"{body} Period look: {c.look}. Mood: {c.mood['words']}. {PEOPLE}", refs, c.look, use, line_no)
    if use == "metaphor":
        m = _motif(b, c, subject)
        body = (f"A single symbolic image that makes the idea '{m}' visible: {c.aircraft_phrase()} as the main subject, "
                f"surrounded by simple objects that stand for the idea, bold composition, one clear focal point.")
        return _pack(f"{body} {c.tail(place=False)}", refs, c.look, use, line_no)
    if use == "cabin":
        cls = s or ("economy" if c.era in ("1980s", "1990s", "modern") else "first class")
        body = (f"The passenger cabin of {c.aircraft['name']} in {c.airline_name or 'an airline'} colours, {cls}, seats, carpet and lighting of the period, "
                f"seen along the aisle, passengers only as small silhouettes with faces turned away.")
        return _pack(f"{body} Livery colours in the decor: {(c.livery or {}).get('color_words', 'neutral')}. {c.tail(place=False)}", refs, c.look, use, line_no)
    idea = _motif(b, c, subject) or _topic(c, None)               # thumbnail
    body = (f"A thumbnail composition: {c.aircraft_phrase()} large in the frame at a dramatic angle, with one bold visual idea: {idea}. "
            f"{THUMB_LOOK}. Keep the left third empty.")
    return _pack(f"{body} Period look: {c.look}. Mood: {c.mood['words']}. {PEOPLE}", refs, THUMB_LOOK, use, line_no)


# ------------------------------------------------------------------------------------------------------------ videos
def video_prompt(b: B.Bible, line_no: int, use: str, subject: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if use not in VIDEO_USES or why_not(b, line_no, use, subject):
        return None
    c = _ctx(b, line_no)
    refs = references(b, line_no, subject)
    if use == "image_to_video":
        body = (f"Bring the reference picture to life with one slow camera push-in: subtle natural motion only (propellers or engines starting, people moving "
                f"in the distance, flags and dust moving), {c.aircraft_phrase()}, no cuts, the same framing and colours as the picture.")
    elif use == "cast_moment":
        role = _role(b, c, subject)
        refs = references(b, line_no, role)
        body = (f"A short quiet moment with the {B.role_label(role)} from the reference sheet, wearing {_uniform(b, role, c)}, doing their job "
                f"aboard or beside {c.aircraft_phrase()}, medium shot, slow handheld camera, faces natural and unremarkable.")
    elif use == "ops_broll":
        body = (f"Airport operations b-roll around {c.aircraft_phrase()}: ground crew, loading, refuelling or a hangar check as fits the scene, "
                f"workers seen mostly from behind, steady camera.")
    elif use == "place_reconstruction":
        body = (f"An illustrative reconstruction of a generic, unnamed scene{(' in ' + c.place_text) if c.place_text else ''}: a plain room or apron of the period "
                f"suggesting the story's setting, no identifiable real person, no real event, slow camera drift.")
    else:                                                                    # sticker_to_real
        body = (f"The camera pushes into a flat die-cut sticker illustration of {c.aircraft['name']} and lands on a real-looking shot of the same aircraft "
                f"in {c.livery_text}, taking off or in flight, smooth slow move.")
    look = c.look
    return _pack(f"{body} {c.tail()}", refs, look, use, line_no)


# ------------------------------------------------------------------------------------------------------------ the library list
def _first_ctx(b: B.Bible, lines: List[int]) -> _Ctx:
    return _Ctx(b, lines[0])


def hero_list(b: B.Bible) -> List[Dict[str, Any]]:
    """One hero aircraft per airline x era (the type the script names most, else the era guess): made once, attached to every later shot."""
    out: List[Dict[str, Any]] = []
    for aid, eras in b.fleet.items():
        for era in B.ERA_KEYS:
            e = eras.get(era)
            if not e:
                continue
            lv = b.livery[aid][era]
            ac = B.aircraft_entry(e["types"][0]) or {"id": e["types"][0], "name": "an airliner"}
            year = (b.lines[e["lines"][0]]["year"]) if e["lines"] else None
            prompt = (f"Reference sheet: {ac['name']} in {lv['name']} livery, {lv['text']}. Two views on one sheet, a side view and a three-quarter view, "
                      f"the whole aircraft inside the frame. {SHEET_LOOK}. Period look: {B.era_look(era)}. {PEOPLE} {END}")
            out.append({"id": B.hero_id(aid, era), "airline": aid, "era": era, "aircraft": ac["id"], "assumed": e["assumed"], "year": year,
                        "prompt": prompt, "refs": [], "lines": list(e["lines"])})
    return out


def cast_list(b: B.Bible) -> List[Dict[str, Any]]:
    """One cast sheet per unnamed role: an invented person, front and side, in the airline's uniform of the era."""
    out: List[Dict[str, Any]] = []
    for role, e in b.cast.items():
        c = _Ctx(b, e["lines"][0])
        prompt = (f"Character reference sheet of one invented, unnamed {e['label']}: front view and side view, head and shoulders to waist, wearing "
                  f"{_uniform(b, role, c)}, neutral friendly expression, an ordinary face that is not any real person. {SHEET_LOOK}. "
                  f"Period look: {B.era_look(e['era'])}. {END}")
        out.append({"id": B.cast_id(role), "role": role, "label": e["label"], "airline": e["airline"], "era": e["era"], "prompt": prompt, "refs": [],
                    "lines": list(e["lines"])})
    return out


def place_list(b: B.Bible) -> List[Dict[str, Any]]:
    """One place plate per airport named, in the look of the era it first appears in."""
    out: List[Dict[str, Any]] = []
    for pid, p in b.places.items():
        era = p["eras"][0] if p["eras"] else "modern"
        year = b.lines[p["lines"][0]]["year"]
        lm = B.landmark(pid, year) or p.get("landmark") or ""
        prompt = (f"Establishing plate of {p['city'] or p['name']} airport area" + (f" with {lm}" if lm else "") +
                  f", wide view, an airliner of the time on the apron. Period look: {B.era_look(era)}. {PEOPLE} {END}")
        out.append({"id": B.place_id(pid), "airport": pid, "era": era, "prompt": prompt, "refs": [], "lines": list(p["lines"])})
    return out
