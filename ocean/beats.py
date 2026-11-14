"""Beat mode for Ocean Predators (the Depth Theory way of following the narration): a beat CSV made from the script by
any AI chat (ocean/beat_prompt.md, "Copy the beat prompt") says, for every 2-4 s of narration, the ONE picture on screen:

    type,text,visual,prompt
    cast,,LION,"adult male African lion, thick dark-brown mane ..."      one fixed look per recurring animal / person
    beat,"You weigh four hundred and twenty pounds.",graphic,"number: 420 LB | what you weigh"
    beat,"A lion kills by clamping its jaws",picture,"[LION] clamping its jaws on [BADGER]'s neck, low angle close-up"
    beat,"around an animal's windpipe",clip,"lion hunting"

    read(path_or_text)             -> (cast {TAG: look}, beats [{"text", "visual", "prompt"}])
    timed(beats, words, total)     -> beats with "start" / "end" from the voice-over's word times
    picture_prompt(prompt, cast)   -> the Flow prompt: [TAG] -> its look, + the channel's illustration style
    graphic(prompt)                -> (card kind, args) for ocean/cards*.py
    plan(beats, cast, total, ...)  -> the plan.json dict the runner renders (mode "beats")

picture beats are Flow illustrations (ocean/beat_flow.py) and clip beats stock clips, both listed in the Visuals tab and
cut in as moving shots (a picture gets a smooth camera move: push in / pull out / pan); graphic beats are drawn on the
dark stage. A beat whose picture or clip is missing shows its animal on the stage instead, so nothing is ever blank.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import reader as R

STYLE = ("Flat 2D vector illustration in the style of a modern animated YouTube explainer: clean flat colour shapes with "
         "soft subtle gradients, crisp smooth edges, simple stylised but accurate anatomy, bold readable silhouettes, "
         "markings drawn as clean tapered shapes, small clean face details; a dark moody scene (night, dusk or deep "
         "shadow) with a simple flat background and a soft vignette, lots of empty dark space, uncluttered, 16:9 wide "
         "frame. No outlines, no texture, no fur strands, no painterly brush work, no 3D render, no photo. No text, no "
         "letters, no numbers, no logos, no watermark.")
MOVES = ("push_in", "pan_right", "pull_out", "pan_left", "push_in_up")
PICTURE_SLOT_BASE = 0                     # beat N -> Visuals-tab scene N (pictures and clips share the beat numbers)
VISUALS = ("picture", "clip", "graphic")


# ---------------------------------------------------------------------------------------------------------------- read

def read(src: Any) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    is_file = isinstance(src, Path) or (isinstance(src, str) and "\n" not in src and len(src) < 1024 and Path(src).is_file())
    text = Path(src).read_text(encoding="utf-8-sig") if is_file else str(src)
    text = re.sub(r"^```\w*\s*|```\s*$", "", text.strip(), flags=re.M)
    cast: Dict[str, str] = {}
    beats: List[Dict[str, str]] = []
    for row in csv.reader(io.StringIO(text)):
        if not row or not "".join(row).strip():
            continue
        kind = row[0].strip().lower()
        if kind in ("type", ""):
            continue
        cells = (row + ["", "", "", ""])[:4]
        if kind == "cast":
            tag = re.sub(r"[^A-Z0-9_]", "", cells[2].strip().upper().replace(" ", "_"))
            if tag:
                cast[tag] = cells[3].strip()
        elif kind == "beat" and cells[1].strip():
            vis = cells[2].strip().lower()
            beats.append({"text": cells[1].strip(), "visual": vis if vis in VISUALS else "picture", "prompt": cells[3].strip()})
    return cast, beats


def timed(beats: Sequence[Dict[str, str]], words: Sequence[Any], total: float) -> List[Dict[str, Any]]:
    """Each beat starts when its first word is spoken (the beats' texts, joined, are the script the voice reads)."""
    from .runner import align_script

    script = " ".join(b["text"] for b in beats)
    aligned = align_script(script, words)
    out: List[Dict[str, Any]] = []
    i = 0
    for b in beats:
        n = len(re.sub(r"\s*[—–]\s*", " — ", b["text"]).replace(" — ", " ").split()) or 1
        seg = aligned[i: i + n]
        i += n
        t0 = float(seg[0][1]) if seg else (out[-1]["end"] if out else 0.0)
        out.append(dict(b, start=t0, end=t0))
    for a, nxt in zip(out, out[1:]):
        a["end"] = max(a["start"] + 0.4, float(nxt["start"]))
    if out:
        out[0]["start"] = 0.0
        out[-1]["end"] = max(out[-1]["start"] + 0.8, float(total))
    return out


CUTOUT = ("Clean semi-realistic digital illustration for a wildlife documentary explainer: accurate anatomy, soft cel shading "
          "with smooth gradients, crisp clean edges, muted natural colours. The whole subject inside the frame with space "
          "around it, full body. Plain flat solid bright green background (#00FF00) filling the whole picture, no ground, "
          "no scenery, no shadow, no other objects. No text, no letters, no logos, no watermark.")
SIDE_VIEW = {"walk", "run", "flee", "swim"}


def act_prompt(prompt: str, cast: Dict[str, str], action: str) -> str:
    """The actor alone on green (ocean/act.py animates it on its plain set): no background in the picture."""
    def sub(m: "re.Match") -> str:
        tag = re.sub(r"[^A-Z0-9_]", "", m.group(1).upper().replace(" ", "_"))
        return cast.get(tag) or m.group(1).lower()
    body = re.sub(r"\[([^\]]+)\]", sub, prompt).strip().rstrip(".")
    body = re.sub(r",?\s*\b(at|on|in|across|under|over|through) (the )?(golden )?(sunset|dusk|dawn|night|savanna|grass|sand|trail|"
                  r"plain|desert|scrubland)\b[^,.]*", "", body, flags=re.I)        # the set is drawn by the video
    view = " Seen exactly from the side, facing right, legs clearly apart." if action in SIDE_VIEW else ""
    return f"{body}.{view} {CUTOUT}"


def picture_prompt(prompt: str, cast: Dict[str, str]) -> str:
    def sub(m: "re.Match") -> str:
        tag = re.sub(r"[^A-Z0-9_]", "", m.group(1).upper().replace(" ", "_"))
        look = cast.get(tag)
        return f"{look}" if look else m.group(1).lower()
    body = re.sub(r"\[([^\]]+)\]", sub, prompt).strip().rstrip(".")
    for tag, look in cast.items():                     # "the badger" without its tag still gets the cast's look
        name = look.split(",")[0].strip().lower()
        words = {name, name.split()[-1]} if name else set()
        words |= {tag.lower().replace("_", " ")}
        if look and look not in body and any(re.search(r"\b" + re.escape(w) + r"s?\b", body, re.I) for w in words if len(w) > 2):
            body += f". The {name or tag.lower()} looks exactly like this: {look}"
    return f"{body}. {STYLE}"


# ---------------------------------------------------------------------------------------------------------------- graphics

def _num(s: str) -> float:
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", s)
    return float(m.group(0).replace(",", "")) if m else 0.0


def graphic(prompt: str, text: str = "") -> Tuple[str, Dict[str, Any]]:
    """'number: 420 LB | what you weigh' -> ('number_hero', {...}). Unknown forms become a number card of the prompt."""
    m = re.match(r"\s*(\w+)\s*:\s*(.*)$", prompt or "", re.S)
    kind, rest = (m.group(1).lower(), m.group(2)) if m else ("number", prompt or text)
    parts = [p.strip() for p in rest.split("|")]
    p0 = parts[0] if parts else ""
    if kind == "number":
        line = parts[1] if len(parts) > 1 else ""
        words = line.split()
        return "number_hero", {"number": p0.upper(), "line": " ".join(words[:-2]), "key": " ".join(words[-2:]).upper(),
                               "size": 120 if len(p0) < 8 else 90}
    if kind == "compare":
        sides = [p.split(None, 2) for p in parts[:2]]
        left = [" ".join(sides[0][:2]), sides[0][2] if len(sides[0]) > 2 else ""] if sides and sides[0] else ["", ""]
        right = [" ".join(sides[1][:2]), sides[1][2] if len(sides[1]) > 2 else ""] if len(sides) > 1 and sides[1] else ["", ""]
        return "standoff", {"left": left, "right": right}
    if kind == "bars":
        rows = []
        for p in parts[1:5]:
            mm = re.match(r"(.*?)\s+(-?\d[\d,.]*\s*\S*)\s*$", p)
            if mm:
                rows.append([mm.group(1).strip(), _num(mm.group(2)), mm.group(2).strip()])
        return "hud_bars", {"title": p0, "rows": rows}
    if kind == "percent":
        v = _num(p0)
        return "progress", {"value": v, "label": f"{v:g}%", "note": parts[1] if len(parts) > 1 else ""}
    if kind == "count":
        return "number_hero", {"number": p0.upper(), "line": "", "key": (parts[1] if len(parts) > 1 else "").upper(), "size": 130}
    if kind == "time":
        hours = _num(p0) / (60.0 if re.search(r"min", p0, re.I) else 3600.0 if re.search(r"sec", p0, re.I) else 1.0)
        if re.search(r"day|week|month|year", p0, re.I):
            return "number_hero", {"number": p0.upper(), "line": "", "key": "", "size": 110}
        return "clock", {"hours": min(12.0, max(0.05, hours)), "time": p0.upper()}
    if kind == "year":
        return "year_anchor", {"year": p0, "event": parts[1] if len(parts) > 1 else "", "line": ""}
    if kind == "map":
        from . import relations as REL
        ll = REL.place_latlon(p0)
        if ll:
            return "map_pin", {"place": p0, "lat": ll[0], "lon": ll[1], "line": parts[1] if len(parts) > 1 else ""}
        return "number_hero", {"number": p0.upper(), "line": "", "key": "", "size": 90}
    if kind == "size":
        a = re.match(r"(.*?)\s+(\d[\d.]*)\s*m\b", p0)
        b = re.match(r"(.*?)\s+(\d[\d.]*)\s*m\b", parts[1]) if len(parts) > 1 else None
        if a:
            f = R.read(a.group(1))
            animal = f.animals[0][0] if f.animals else "great_white"
            ref = (b.group(1).strip().lower() if b else "diver")
            ref = ref if ref in ("diver", "car", "bus") else ("car" if "car" in ref else "diver")
            return "size_compare", {"animal": animal, "metres": float(a.group(2)), "label": f"{a.group(2)} M",
                                    "ref": ref, "ref_label": {"diver": "DIVER · 1.8 M", "car": "CAR · 4.5 M", "bus": "BUS · 12 M"}[ref]}
    if kind == "list":
        return "mystery", {"slots": parts[:5], "animals": ["" for _ in parts[:5]], "lit": len(parts[:5]) - 1}
    if kind == "mystery":                                 # "mystery: HUMPBACK | SPERM WHALE | ?" - "?" slots stay hidden
        slots = [x if x not in ("?", "") else "" for x in parts[:5]] or ["", "", ""]
        return "mystery", {"slots": slots, "animals": ["" for _ in slots], "lit": next((i for i, x in enumerate(slots) if not x), None)}
    if kind == "title":                                   # "title: THE TSAVO LIONS | Kenya, 1898"
        return "title_banner", {"title": p0, "sub": parts[1] if len(parts) > 1 else "", "animal": _stage_animal(p0, "") or ""}
    if kind == "labels":                                  # "labels: LION | massive shoulders | no mane"
        return "labels", {"animal": _stage_animal(p0, "") or "great_white", "labels": parts[1:5]}
    if kind == "part":                                    # "part: LION | claws" - the close-up of one body part
        from . import relations as REL
        lab = parts[1] if len(parts) > 1 else ""
        part = next((n for rx, n in REL._PARTS if rx.search(lab)), "eye")
        return "anatomy", {"animal": _stage_animal(p0, "") or "great_white", "part": part, "label": lab}
    if kind in ("checklist", "tried", "survived"):       # "checklist: TRIED | soldiers | traps | poison | stamp ALL FAILED"
        title = p0 if kind == "checklist" else kind
        bad = bool(re.search(r"\b(tried|failed|didn'?t|can'?t|won'?t|never|not|no)\b", title, re.I))
        items, stamp = [], ""
        for x in parts[1:8]:
            m2 = re.match(r"(?i)stamp\s*:?\s*(.+)", x)
            if m2:
                stamp = m2.group(1)
                continue
            m3 = re.match(r"(?i)^(x|v|✓|✗|✔|✘)\s+(.+)", x)
            ok = (m3.group(1).lower() in ("v", "✓", "✔")) if m3 else not bad
            items.append([m3.group(2) if m3 else x, ok])
        return "checklist", {"title": title.rstrip(":") + ":", "items": items, "stamp": stamp}
    if kind == "dots":                                    # "dots: Rudraprayag | 400 | deaths" - a red cluster on the map
        from . import relations as REL
        ll = REL.place_latlon(p0)
        n = int(_num(parts[1])) if len(parts) > 1 else 30
        lab = " ".join(parts[1:3]) if len(parts) > 1 else ""
        if ll:
            return "map_pin", {"place": p0, "lat": ll[0], "lon": ll[1], "dots": max(8, min(60, n)), "count_label": lab}
        return "number_hero", {"number": (parts[1] if len(parts) > 1 else p0).upper(), "line": "", "key": lab.upper(), "size": 110}
    if kind == "text":                                    # "text: FOUR HUNDRED." - big words, the last one red
        return "statement", {"text": p0}
    if kind == "paper":                                   # "paper: ANIMAL BEHAVIOUR · 2017 | the study's title | authors"
        return "paper", {"journal": p0, "title": parts[1] if len(parts) > 1 else text, "authors": parts[2] if len(parts) > 2 else ""}
    if kind == "date":                                    # "date: NOV 1997 | Off California"
        mm = re.match(r"\s*([A-Za-z]{3,})\.?\s*(\d{1,2})?\s*,?\s*(\d{4})?", p0)
        month = mm.group(1)[:3].upper() if mm else ""
        return "calendar", {"month": month, "day": (mm.group(2) or mm.group(3) or "") if mm else p0,
                            "line": parts[1] if len(parts) > 1 else ""}
    if kind == "icons":                                   # "icons: 80 | orca | FEWER THAN 80 | 12" (count, animal, title, lit)
        n = int(_num(p0)) or 10
        return "icon_grid", {"count": n, "animal": (_stage_animal(parts[1], "") if len(parts) > 1 else None) or "great_white",
                             "title": parts[2] if len(parts) > 2 else p0, "lit": _num(parts[3]) if len(parts) > 3 else None}
    return "number_hero", {"number": (p0 or text)[:24].upper(), "line": "", "key": "", "size": 90}


# ---------------------------------------------------------------------------------------------------------------- upgrade

UNITS = {"pounds": "LB", "pound": "LB", "lb": "LB", "lbs": "LB", "kilograms": "KG", "kilogram": "KG", "kg": "KG", "tons": "TONS",
         "ton": "TON", "inches": "IN", "inch": "IN", "feet": "FT", "foot": "FT", "metres": "M", "meters": "M", "metre": "M",
         "meter": "M", "m": "M", "cm": "CM", "centimetres": "CM", "millimetres": "MM", "mm": "MM", "miles": "MILES", "mph": "MPH",
         "km/h": "KM/H", "percent": "%", "%": "%", "psi": "PSI", "calories": "CALORIES", "minutes": "MIN", "seconds": "SEC",
         "hours": "HOURS", "days": "DAYS", "years": "YEARS", "volts": "VOLTS"}


def _number_form(n: Any, text: str) -> str:
    """'You weigh 420 pounds' -> 'number: 420 LB | you weigh' (the words around the number say what it is)."""
    unit = UNITS.get(str(n.unit or "").lower(), str(n.unit or "").upper())
    v = f"{n.value:,.0f}" if n.value >= 100 else f"{n.value:g}"
    after = [re.sub(r"[^\w'-]", "", w) for w in text[n.end:].split()[:4]]
    while after and after[0].lower() in ("of", "from", "away", "to", "in", "a", "an", "the", "long", "and", "-"):
        after = after[1:]
    after = after[:3]
    before = [re.sub(r"[^\w'-]", "", w) for w in text[:n.pos].split()[-3:]]
    if not any(after):
        while before and before[-1].lower() in ("are", "is", "was", "were", "has", "have", "had", "weighs", "weigh", "about"):
            before = before[:-1]
    line = " ".join(w for w in (after if any(after) else before) if w)
    return f"number: {v} {unit}".strip() + (f" | {line}" if line else "")


STUDY = re.compile(r"\b(a (?:\d{4} )?study|studies|researchers?|scientists? (?:found|measured|sequenced|tested)|biologists?|"
                   r"published|journal|paper (?:by|from|in))\b", re.I)
PART_WORD = re.compile(r"\b(canine teeth|teeth|jaws?|claws?|skin|hide|eyes?|corneas?|tail|nose|snout|brain|heart)\b", re.I)


def upgrade(beats: Sequence[Dict[str, Any]], cast: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """The reference shows a graphic whenever the words carry a fact: a picture beat whose narration names a number, a
    year, a known place, speeds, a fraction, a study or a body part becomes that graphic (an older beat CSV written
    picture-first gets the reference's graphics-first mix without being remade). Clips and the opening beat stay."""
    from . import relations as REL

    out: List[Dict[str, Any]] = []
    for i, b in enumerate(beats):
        b = dict(b)
        if i == 0 or b.get("visual") != "picture":
            out.append(b)
            continue
        f = R.read(b["text"])
        rel = f.rel
        form = ""
        txt = f.text if hasattr(f, "text") else b["text"]

        def counted(n: Any) -> bool:                      # "six lions": a count of animals, not "option two is"
            nxt = " ".join(txt[n.end:].split()[:2])
            return bool(R.read(nxt).animals)
        nums = [n for n in f.numbers if n.kind != "year" and n.value not in (0, 1) and not txt[n.end:n.end + 1] == "-"
                and (str(n.unit or "").lower() in UNITS or counted(n))]
        years = [n for n in f.numbers if n.kind == "year"]
        named = [x[0] for x in f.animals if x[0] not in ("diver", "boat", "cage", "tooth", "hiker")]
        prev = out[-1] if out else {}
        if STUDY.search(b["text"]):
            form = f"paper: FIELD STUDY | {b['text'].strip(' ,.')}"
        elif rel.speed and len(rel.speed) >= 2:
            form = "bars: " + (rel.speed_title or "TOP SPEED") + "".join(f" | {lab} {kmh:.0f} km/h" for lab, kmh, _ in rel.speed[:4])
        elif years:
            form = f"year: {int(years[0].value)} | {b['text'].strip(' ,.')[:60]}"
        elif rel.place and REL.place_known(rel.place):
            form = f"map: {rel.place}"
        elif rel.fraction and named:
            lit, of = rel.fraction
            form = f"icons: {of} | {named[0] if named else 'lion'} | {lit} IN {of} | {lit}"
        elif nums:
            form = _number_form(nums[0], f.text if hasattr(f, "text") else b["text"])
        elif named and PART_WORD.search(b["text"]):
            form = f"part: {named[0]} | {PART_WORD.search(b['text']).group(0)}"
        same = prev.get("auto") and str(prev.get("prompt", "")).split(":")[0] == form.split(":")[0]
        if form and not same:                             # never the same auto card twice in a row
            b.update(visual="graphic", prompt=form, auto=True)
        out.append(b)
    return out


# ---------------------------------------------------------------------------------------------------------------- stage

PEOPLE = re.compile(r"\b(man|men|woman|women|people|person|scientists?|villagers?|hunters?|soldiers?|kids?|child(?:ren)?|humans?|"
                    r"farmers?|rangers?|tourists?)\b", re.I)
PROPS = re.compile(r"\b(computer|screen|monitor|phone|tablet|lab|dna|map|trees?|hive|beehive|nest|termite|tent|car|truck|jeep|"
                   r"plate|table|bag|kopje|rock|river|lake|bones?|skeleton|carcass|fire|village|hut|house|museum|trap|gun|"
                   r"rifle|cage|fence|book|paper|chart|molecule|cutaway|cross-section|x-ray|close-up|eyes? of)\b", re.I)


def _resolve(prompt: str, cast: Dict[str, str]) -> str:
    """[BADGER] -> 'honey badger' (the cast look's first phrase) so the catalogue reader knows the animal."""
    def sub(m: "re.Match") -> str:
        tag = re.sub(r"[^A-Z0-9_]", "", m.group(1).upper().replace(" ", "_"))
        look = cast.get(tag, "")
        return (look.split(",")[0].strip() if look else m.group(1)).replace("adult ", "").replace("male ", "")
    return re.sub(r"\[([^\]]+)\]", sub, prompt or "")


def stage_cast(prompt: str, cast: Dict[str, str], action: Optional[str]) -> List[str]:
    """The animals a picture beat can be DRAWN as on the dark stage (the reference's flat animals over a plain set), or []
    when the frame needs a painted picture: people, props, places, diagrams, or an animal with no library art."""
    from . import art_flow as AF
    if not action or action == "fall":
        return []
    text = _resolve(prompt, cast)
    if PEOPLE.search(text) or PROPS.search(text):
        return []
    names: List[str] = []
    for a in R.read(text).animals:
        if a[0] in ("diver", "boat", "cage", "tooth") or a[0] in names:
            continue
        names.append(a[0])
    if not names or len(names) > 2 or any(AF.path(n, "side") is None for n in names):
        return []
    if re.search(r"\b(pride|pack|herd|group|six|five|four|three|circle|surround)", text, re.I):
        return []                                         # a crowd: the painted picture shows it better
    return names


BODY_M = {"elephant": 6.0, "giraffe": 4.5, "cape_buffalo": 3.0, "lion": 2.6, "zebra": 2.4, "wildebeest": 2.3, "lioness": 2.2,
          "leopard": 1.9, "cobra": 1.8, "hiker": 1.8, "hyena": 1.5, "puff_adder": 1.0, "dog": 1.0, "eagle": 0.9,
          "honey_badger": 0.85, "porcupine": 0.8, "skunk": 0.6, "tortoise": 0.5, "bee": 0.15}


def _widths(names: Sequence[str], big: int = 560) -> List[int]:
    """Two animals drawn to the same scale: the bigger one `big` px wide, a small one never under 170 px."""
    m = [BODY_M.get(n, 1.5) for n in names]
    top = max(m)
    return [max(170, int(big * x / top)) for x in m]


def _stage_beat(st: Any, names: Sequence[str], action: str, dur: float, land: bool, seed: int) -> None:
    """The beat's action played by the drawn animals: walk / run cross the frame, flee runs out, attack lunges at the
    other one, approach comes closer, idle breathes and drifts. Two animals face each other."""
    gy = 470.0 if land else 380.0
    face0 = "right" if seed % 2 == 0 else "left"
    sgn = 1 if face0 == "right" else -1
    if len(names) == 2:
        wa, wb = _widths(names, 520)
        xa, xb = 330.0, 950.0
        a = st.add("animal", 0.0, {"name": names[0], "width": wa, "face": "right", "jaw": action == "attack", "flat": True},
                   pos=(xa, gy), enter="slide_left", float_=not land)
        b = st.add("animal", 0.1, {"name": names[1], "width": wb, "face": "left", "flat": True}, pos=(xb, gy), enter="slide_right",
                   float_=not land)
        if action == "attack":                            # the lunge stops just short of the other one: never inside it
            st.move(a, 0.6, pos=(xb + 40 - (wa + wb) / 2, gy - 10), dur=0.35)
            st.move(b, 0.7, pos=(xb + 50, gy + 6), dur=0.3)
        elif action in ("walk", "run", "approach", "swim"):
            st.move(a, 0.4, pos=(470.0, gy), dur=max(0.5, dur - 0.6))
        elif action == "flee":
            st.move(b, 0.6, pos=(1600.0, gy), dur=min(1.2, dur - 0.4))
        return
    n = names[0]
    if action in ("walk", "run", "swim"):
        x0, x1 = (640 - sgn * 330, 640 + sgn * 330) if action == "run" else (640 - sgn * 200, 640 + sgn * 200)
        e = st.add("animal", 0.0, {"name": n, "width": 560, "face": face0, "flat": True}, pos=(float(x0), gy), enter="fade", float_=not land)
        st.move(e, 0.1, pos=(float(x1), gy), dur=max(0.5, dur - 0.2))
    elif action == "flee":
        e = st.add("animal", 0.0, {"name": n, "width": 560, "face": face0, "flat": True}, pos=(640.0, gy), enter="fade", float_=not land)
        st.move(e, min(0.8, dur * 0.3), pos=(640.0 + sgn * 1000, gy), dur=min(1.2, dur * 0.6))
    elif action == "approach":
        e = st.add("animal", 0.0, {"name": n, "width": 560, "face": face0, "flat": True}, pos=(640.0, gy), scale=0.7, enter="fade",
                   float_=not land)
        st.move(e, 0.1, pos=(640.0, gy + 40), scale=1.25, dur=max(0.5, dur - 0.2))
    elif action == "attack":
        e = st.add("animal", 0.0, {"name": n, "width": 600, "face": face0, "jaw": True, "flat": True}, pos=(640.0 - sgn * 180, gy),
                   enter="pop", float_=not land)
        st.move(e, 0.5, pos=(640.0 + sgn * 120, gy - 12), scale=1.12, dur=0.3)
    else:
        e = st.add("animal", 0.0, {"name": n, "width": 600, "face": face0, "flat": True}, pos=(640.0, gy), enter="fade", float_=not land)
        st.move(e, 0.1, pos=(640.0 + sgn * 40, gy), scale=1.06, dur=max(0.5, dur - 0.2))


# ---------------------------------------------------------------------------------------------------------------- plan

def _stage_animal(text: str, prompt: str) -> Optional[str]:
    """The catalogue animal a beat is about (for the stage stand-in when its picture / clip is missing)."""
    for src in (prompt, text):
        f = R.read(src)
        names = [a[0] for a in f.animals if a[0] not in ("diver", "boat", "cage", "tooth")]
        if names:
            return names[0]
    return None


ANIMAL_CARDS = {"number_hero": (640.0, 480.0, 480), "clock": (470.0, 450.0, 520), "progress": (640.0, 500.0, 440),
                "year_anchor": (640.0, 560.0, 380)}          # card kind -> where its animal stands (x, y, width), clear of
                                                             # the card at the planner's CARD_POS


def _card_animals(kind: str, args: Dict[str, Any], text: str, prompt: str, last: Optional[str]) -> List[Tuple[str, float, float, int]]:
    """The animals a graphic beat shows with its card, like the reference's number cards (the shark above "5 m", the
    two sides of a compare): (name, x, y, width). A beat that names no animal keeps the one the film is on."""
    if kind == "standoff":
        out = []
        for side, x in (("left", 260.0), ("right", 1020.0)):
            lab = " ".join(str(v) for v in (args.get(side) or []))
            who = _stage_animal(lab, "")
            if who:
                out.append((who, x + (120.0 if side == "left" else -120.0), 450.0, 400))
        return out
    if kind not in ANIMAL_CARDS:
        return []
    who = _stage_animal(text, prompt) or last
    x, y, w = ANIMAL_CARDS[kind]
    return [(who, x, y, w)] if who else []


def captions(words: Sequence[Any], beats: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The reference's keyword captions (orange / red words) over the pictures and clips; none while a graphic card is
    up, so a number is never said twice on screen."""
    from . import captions as CAP

    if not words:
        return []
    cards = [(float(b["start"]), float(b["end"])) for b in beats if b.get("visual") == "graphic"]
    titles: List[Dict[str, Any]] = []
    seen: set = set()
    for b in beats:                                   # "HONEY BADGER" at the top the first time it is on screen
        if b.get("visual") == "graphic":
            continue
        who = _stage_animal(b["text"], b.get("prompt", ""))
        if not who or who in seen or who in ("hiker", "person"):
            continue
        seen.add(who)
        label = who.replace("_", " ")                     # the word as the beat writes it ("vulture", not its catalogue
        for src in (b.get("prompt", ""), b["text"]):      # stand-in "eagle")
            hit = next((x for x in R.read(src).animals if x[0] == who), None)
            if hit and len(hit) > 4 and hit[4]:
                label = str(hit[4])
                break
        a = float(b["start"]) + 0.2
        z = min(float(b["end"]), a + 2.6)
        if z - a >= 0.8:
            titles.append({"t0": round(a, 3), "t1": round(z, 3), "lead": "", "key": label.upper(),
                           "color": "orange", "pos": "top", "kind": "name", "score": 9})
    out = list(titles)
    for c in CAP.plan(words, every_s=2.5):            # the same phrase rhythm as the normal Ocean planner
        if any(c["t0"] < z - 0.2 and c["t1"] > a + 0.2 for a, z in cards):
            continue
        out.append(c)
    return sorted(out, key=lambda c: c["t0"])


def plan(beats: Sequence[Dict[str, Any]], cast: Dict[str, str], total: float, channel: str = "Ocean",
         clip_grade: str = "neutral", words: Sequence[Any] = ()) -> Dict[str, Any]:
    from .stage import OceanStage
    from .planner import _land_world

    beats = upgrade(beats, cast)
    feats = [R.read(b["text"] + " " + b.get("prompt", "")) for b in beats]
    land = _land_world(feats)
    home = "savanna" if land else "dark"
    layers: List[Dict[str, Any]] = []
    shots: List[Dict[str, Any]] = []
    slots: List[Dict[str, Any]] = []
    counts = {"picture": 0, "clip": 0, "graphic": 0}
    mi = 0
    drawn_beats: List[Dict[str, Any]] = []
    last_animal: Optional[str] = None
    for i, b in enumerate(beats):
        a, z = float(b["start"]), float(b["end"])
        no = str(PICTURE_SLOT_BASE + i + 1)
        st = OceanStage()
        st.set(0.0, "plain" if b["visual"] == "graphic" else home)
        if b["visual"] == "graphic":
            kind, args = graphic(b.get("prompt", ""), b["text"])
            from .cards_story import FULL as CS_FULL
            full = kind in CS_FULL or kind in ("size_compare", "mystery")
            dur = max(0.6, z - a - 0.2)
            from .planner import CARD_POS
            if kind == "size_compare" and land and args.get("ref") == "diver":
                args = dict(args, ref="person", ref_label="PERSON · 1.8 M", land=True)   # no scuba diver on the savanna
            if kind == "mystery":                         # a slot that names an animal shows it
                args = dict(args, animals=[_stage_animal(x, "") or "" for x in args.get("slots") or []])
            pos, scale = CARD_POS.get(kind, ((640, 330), 1.0)) if not full else ((640, 360), 1.0)
            el = st.add("ocean_" + kind, 0.05, dict(args, _flat=True, flat_art=True), pos=pos, scale=scale, enter="fade" if full else "pop",
                        anim=dur if full else min(1.2, dur), float_=not full)
            if full:
                st._get(el)["anim_steps"] = int(dur * 12)
                st._get(el)["anim_delay"] = 0.0
            else:
                for who, x, y, w in _card_animals(kind, args, b["text"], b.get("prompt", ""), last_animal):
                    st.add("animal", 0.15, {"name": who, "width": w, "face": "left" if x > 640 else "right", "flat": True},
                           pos=(x, y), enter="fade", float_=not land)
        else:
            who = _stage_animal(b["text"], b.get("prompt", ""))
            last_animal = who or last_animal
            if who:                                     # the stand-in, seen only when the picture / clip is missing
                st.add("animal", 0.0, {"name": who, "width": 560, "face": "right" if i % 2 else "left", "flat": True},
                       pos=(640.0, 470.0 if land else 400.0), enter="fade", float_=not land)
            from . import act as ACT
            kind = b["visual"]
            action = ACT.classify(b.get("prompt", "") or b["text"]) if kind == "picture" else None
            drawn = stage_cast(b.get("prompt", ""), cast, action) if kind == "picture" else []
            if drawn:                                   # the reference's way: the flat animals act on the plain dark set
                day = re.search(r"\b(midday|noon|daylight|bright|sunny)\b", b.get("prompt", ""), re.I)
                st = OceanStage()                       # the reference's land look is dark: night unless the words say day
                set_name = ("savanna" if day else "savanna_night") if land else home
                if land and len(drawn) == 1 and (action or "idle") in ("walk", "run", "idle", "approach"):
                    set_name = "stage_dark"             # one animal: the plain focus set, walking on the spot
                st.set(0.0, set_name)
                if not land:                            # sea animals swim on the stage; land animals walk on legs
                    _stage_beat(st, drawn, action or "idle", z - a, land, i)
                else:                                   # the leg rig (ocean/act.animate_cast) makes this beat's clip
                    drawn_beats.append({"scene_no": no, "start": round(a, 3), "end": round(z, 3), "names": list(drawn),
                                        "widths": _widths(drawn, 700 if len(drawn) == 1 else 600), "action": action or "idle", "set": set_name,
                                        "facing": "right" if i % 3 != 2 else "left", "seed": i})
                counts["picture"] += 1
                counts["drawn"] = counts.get("drawn", 0) + 1
                layers.append({"name": "ocean.lay_ocean", "start": round(a, 3), "end": round(z, 3), "params": st.params()})
                shots.append({"start": round(a, 3), "end": round(z, 3), "set": home, "cards": [], "animals": list(drawn),
                              "scenes": [], "visual": "drawn"})
                continue
            if kind == "clip":
                q = b.get("prompt", "")
            elif action:                                # an animal / person doing something: one full painted scene (the
                kind = "act"                            # animal and its own background together), moved in depth layers
                q = picture_prompt(b.get("prompt", "") or b["text"], cast)
            else:                                       # a diagram / cutaway / idea: the full illustration, gently moving
                q = picture_prompt(b.get("prompt", "") or b["text"], cast)
            slots.append({"scene_no": no, "start": round(a, 3), "end": round(z, 3), "text": b["text"], "why": b["visual"],
                          "kind": kind, "query": q, "move": MOVES[mi % len(MOVES)], "action": action or "",
                          "set": ACT.setting(b.get("prompt", ""), b["text"], land) if action else "",
                          "facing": "right" if i % 3 != 2 else "left",
                          "grade": clip_grade if kind == "clip" else "none"})
            mi += 1
        counts[b["visual"]] += 1
        if slots and slots[-1]["scene_no"] == no and slots[-1]["kind"] == "act":
            counts["act"] = counts.get("act", 0) + 1
        layers.append({"name": "ocean.lay_ocean", "start": round(a, 3), "end": round(z, 3), "params": st.params()})
        shots.append({"start": round(a, 3), "end": round(z, 3), "set": home, "cards": [], "animals": [],
                      "scenes": [no], "visual": b["visual"]})
    caps = captions(words, beats)
    if caps:
        layers.append({"name": "ocean.lay_captions", "start": 0.0, "end": round(float(total), 3), "params": {"items": caps}})
    lens = [s["end"] - s["start"] for s in shots] or [0.0]
    return {"version": 2, "mode": "beats", "channel": channel, "chapters": [], "total": float(total),
            "scenes": [{"scene_no": s["scene_no"], "text": s["text"], "start": s["start"], "end": s["end"]} for s in slots] or [],
            "beats": [dict(b) for b in beats], "cast": dict(cast), "layers": layers, "shots": shots, "clips": slots, "photos": [],
            "drawn": drawn_beats,
            "report": {"shots": len(shots), "shot_avg_s": round(sum(lens) / len(lens), 2), "shot_max_s": round(max(lens), 2),
                       "cards": {"graphic": counts["graphic"]}, "captions": len(caps), "longest_still_s": round(max(lens), 2),
                       "sets": [home], "species": 0, "pictures": counts["picture"], "clips": counts["clip"],
                       "acted": counts.get("act", 0), "drawn": counts.get("drawn", 0),
                       "auto_graphics": sum(1 for b in beats if b.get("auto"))}}
