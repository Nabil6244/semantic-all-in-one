"""Weather fixes a plan's small problems itself, and says what it did, instead of stopping the user for each one.

An AI-written plan (beats.csv + weather_layers.csv) often has a word the transcriber did not hear, a row under the wrong beat, a
city written without its state, a JSON cell with single quotes, a footage source Weather does not use ... None of these needs the
user: each is repaired the way a person would repair it, and a note ("Fixed for you") names the row and what changed. Only what
cannot be guessed still stops the video (no beat rows at all, no weather data and no way to fetch it).

The fixes never change what the user wrote on disk: they run every time the plan is read (Check plan and Generate), so the result
is the same each time. Hybrid's own reader (hybrid.beat_csv) is used unchanged; beats.csv is repaired as text before it reads it."""

from __future__ import annotations

import ast
import csv
import io
import json
import re
from typing import Dict, List, Optional, Sequence, Tuple

ROW_RE = re.compile(r"^row (\d+): (.*)$", re.S)
ID_RE = re.compile(r"row \d+ \(([^)]+)\)")


# ---- beats.csv (the story and the camera) ------------------------------------------------------------------------------------

def _csv_rows(text: str) -> List[List[str]]:
    return list(csv.reader(io.StringIO(str(text).lstrip("﻿"))))


def _csv_text(rows: List[List[str]]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def repair_beats(text: str, words: Sequence, duration: Optional[float], notes: List[str], *, passes: int = 12):
    """(plan, aliases): Hybrid's plan of `text`, after repairing the rows its reader refuses. `aliases` maps a beat id that was
    merged into the beat before it to that beat's id (weather rows naming it follow it there)."""
    from hybrid.beat_csv import plan_from_csv
    from hybrid.plan import PlanError

    rows = _csv_rows(text)
    aliases: Dict[str, str] = {}
    if not rows:
        return plan_from_csv(text, list(words), duration), aliases
    head = [c.strip().lower() for c in rows[0]]
    col = {h: i for i, h in enumerate(head)}

    def get(r: List[str], name: str) -> str:
        i = col.get(name)
        return r[i].strip() if i is not None and i < len(r) else ""

    def put(r: List[str], name: str, value: str) -> None:
        i = col.get(name)
        if i is None:
            return
        while len(r) <= i:
            r.append("")
        r[i] = value

    def is_beat(r: List[str]) -> bool:
        return bool(r) and get(r, "row").lower() == "beat"

    def merge_into_previous(n: int) -> bool:
        """Row n (a beat row) joins the beat before it: its words, and the rows under it."""
        prev = next((k for k in range(n - 1, 0, -1) if is_beat(rows[k])), None)
        if prev is None:
            return False
        me, into = get(rows[n], "beat"), get(rows[prev], "beat")
        put(rows[prev], "text", (get(rows[prev], "text") + " " + get(rows[n], "text")).strip())
        rows[n] = []
        footage = get(rows[prev], "mode").lower() == "footage"
        for k in range(n + 1, len(rows)):
            if is_beat(rows[k]):
                break
            if rows[k]:
                if footage and get(rows[k], "row").lower() in ("layer", "camera", "card"):
                    notes.append(f"beat {me}: its {get(rows[k], 'row')} row was left out (the beat it joined, {into}, is full-screen footage)")
                    rows[k] = []
                    continue
                put(rows[k], "beat", into)
        aliases[me] = into
        for k, v in list(aliases.items()):
            if v == me:
                aliases[k] = into
        notes.append(f"beat {me}: its first words could not be found in your recording, so it is part of beat {into} now")
        return True

    def first_words() -> str:
        return " ".join(str(w[0]) for w in list(words)[:3])

    _straight_quotes(rows, get, put)
    _normalize_layers(rows, get, put, notes)
    tried: Dict[int, List[str]] = {}

    def other_anchor(n: int) -> bool:
        """A beat whose first words were not heard: start it on other words of its own text (each sentence's first words, then
        three-word runs from its opening) before giving up on it."""
        import re as _re

        text = get(rows[n], "text").translate(QUOTES)
        sents = [x for x in _re.split(r"(?<=[.!?])\s+", text) if x.strip()]
        words_ = text.split()
        cands = [" ".join(x.split()[:4]) for x in sents] + [" ".join(words_[k:k + 3]) for k in range(1, min(8, len(words_) - 2))]
        seen = tried.setdefault(n, [get(rows[n], "vo_anchor")])
        later = " ".join(get(x, "text").translate(QUOTES).lower() for x in rows[n + 1:] if x and is_beat(x))
        for c in cands:
            c = c.strip(" ,;:")
            # never words a later beat also says: they could be heard THERE, and this beat would swallow the next one
            if c and c not in seen and not _re.search(r"\d", c) and len(c.split()) >= 3 and c.lower() not in later:
                seen.append(c)
                old_a = get(rows[n], "vo_anchor")
                put(rows[n], "vo_anchor", c)
                for k in range(n + 1, len(rows)):   # its own rows that started on the same words follow it
                    if is_beat(rows[k]):
                        break
                    if rows[k] and get(rows[k], "vo_anchor") == old_a:
                        put(rows[k], "vo_anchor", c)
                notes.append(f"beat {get(rows[n], 'beat')}: its first words ({old_a!r}) were not heard, so it starts on {c!r}")
                return True
        return False
    last_err = None
    for _ in range(passes):
        try:
            plan = plan_from_csv(_csv_text(rows), list(words), duration)
            fix_places(plan, notes)
            return plan, aliases
        except PlanError as exc:
            last_err = exc
            fixed = False
            for prob in exc.problems:
                m = ROW_RE.match(str(prob))
                if not m:
                    continue
                n, msg = int(m.group(1)) - 1, m.group(2)
                if not (0 < n < len(rows)) or not rows[n]:
                    continue
                r = rows[n]
                if "mode must be one of" in msg:
                    kids = [get(x, "row").lower() for x in rows[n + 1:] if x and not is_beat(x)][:3]
                    put(r, "mode", "footage" if "clip" in kids else ("map_footage" if "card" in kids else "map"))
                    notes.append(f"beat {get(r, 'beat')}: mode {get(r, 'mode')!r} set")
                    fixed = True
                elif "says beat" in msg and "but follows beat" in msg:
                    owner = re.search(r"follows beat '([^']+)'", msg)
                    if owner:
                        put(r, "beat", owner.group(1))
                        fixed = True
                elif "extra cell" in msg:
                    put(r, "extra", "")
                    fixed = True
                elif is_beat(r):
                    first_beat = next(k for k in range(1, len(rows)) if is_beat(rows[k])) == n
                    if first_beat and words:
                        if get(r, "vo_anchor") != first_words():
                            put(r, "vo_anchor", first_words())
                            notes.append(f"beat {get(r, 'beat')}: starts on the first words of your recording")
                            fixed = True
                    elif other_anchor(n):
                        fixed = True
                    elif merge_into_previous(n):
                        fixed = True
                else:
                    what = get(r, "row") or "row"
                    owner = next((rows[k] for k in range(n - 1, 0, -1) if is_beat(rows[k])), None)
                    safe = get(owner, "vo_anchor") if owner else ""
                    if ("vo_anchor" in msg or "outside beat" in msg) and safe and get(r, "vo_anchor") != safe and what in ("layer", "card"):
                        put(r, "vo_anchor", safe)   # its own words were not heard: it appears as its beat starts
                        notes.append(f"beat {get(r, 'beat')}: a {what}'s words were not heard, so it appears as the beat starts")
                    else:
                        notes.append(f"beat {get(r, 'beat')}: a {what} row was left out ({msg.split(':')[0].strip()})")
                        rows[n] = []
                    fixed = True
            if not fixed:
                raise PlanError([plain_problem(x) for x in exc.problems]) from None
    raise PlanError([plain_problem(x) for x in last_err.problems])


PLACE_WORDS = re.compile(r"^(?:the|southern|northern|eastern|western|central|coastal|south|north|east|west|southeast|southwest|northeast|"
                         r"northwest|upper|lower|inland|greater|downtown|metro|metropolitan|interior|far|deep)[\s-]+", re.I)


def _place_ok(place: str, cache: Dict[str, bool]) -> bool:
    from pakmap.geo import resolve

    if place not in cache:
        try:
            resolve(place)
            cache[place] = True
        except Exception:
            cache[place] = False
    return cache[place]


def _nearest_place(place: str, cache: Dict[str, bool]) -> Optional[str]:
    """A place name the map knows for one it does not: 'Southern California' -> 'California', 'Miami, FL' -> 'Miami'."""
    tries, p = [], place.strip()
    while True:
        q = PLACE_WORDS.sub("", p).strip()
        if q == p:
            break
        tries.append(q)
        p = q
    for part in re.split(r"\s*[,/]\s*|\s+and\s+", place):
        tries += [part.strip(), PLACE_WORDS.sub("", part).strip()]
    tries += [f"city:{t}" for t in list(tries) if t]
    return next((t for t in tries if t and t != place and _place_ok(t, cache)), None)


def fix_places(plan, notes: List[str]) -> None:
    """Every place the map cannot find is replaced by one it can (the same name without 'Southern', 'coastal'..., then the place the
    camera was last at); a graphic with no usable place is left out. Never a reason to stop: each change is a note."""
    cache: Dict[str, bool] = {}
    said: Dict[str, str] = {}
    last = ""

    def fixed(place: str, where: str, fallback: str = "") -> str:
        if not place or _place_ok(place, cache):
            return place
        new = _nearest_place(place, cache) or fallback
        if new and said.get(place) != new:
            said[place] = new
            notes.append(f"{where}: the map does not know {place!r}, so it uses {new!r}" + (" (and everywhere else it is named)" if new != fallback else ""))
        return new

    for b in plan.beats:
        keep = []
        for c in b.camera:
            if c.place:
                c.place = fixed(c.place, f"beat {b.id}: camera {c.action}", last)
                if not c.place:
                    notes.append(f"beat {b.id}: a camera {c.action} was left out (the map does not know its place)")
                    continue
                last = c.place
            keep.append(c)
        b.camera = keep
        if getattr(b, "cam_place", ""):
            b.cam_place = fixed(b.cam_place, f"beat {b.id}: camera", last)
        lays = []
        for lay in b.layers:
            if lay.place:
                lay.place = fixed(lay.place, f"beat {b.id}: {lay.type} {lay.id}")
                if not lay.place:
                    notes.append(f"beat {b.id}: {lay.type} {lay.id} was left out (the map does not know its place)")
                    continue
            if lay.places:
                lay.places = [q for q in (fixed(x, f"beat {b.id}: {lay.type} {lay.id}") for x in lay.places) if q]
                if len(lay.places) < 2:
                    notes.append(f"beat {b.id}: {lay.type} {lay.id} was left out (the map does not know its places)")
                    continue
            lays.append(lay)
        b.layers = lays
        for sp in getattr(b, "cards", []) or []:
            if sp.place:
                sp.place = fixed(sp.place, f"beat {b.id}: a photo card's pointer")


LAYER_KINDS = ("hud_title", "marker", "zone_label", "fill", "line", "stat", "caption")
LAYER_ALIASES = {"title": "hud_title", "hud": "hud_title", "headline": "hud_title", "heading": "hud_title", "label": "hud_title",
                 "text": "caption", "subtitle": "caption", "pin": "marker", "point": "marker", "zone": "zone_label", "area": "fill",
                 "route": "line", "path": "line", "number": "stat", "statistic": "stat"}


QUOTES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-"})


def _straight_quotes(rows: List[List[str]], get, put) -> None:
    """Curly quotes and dashes in vo_anchor cells become straight ones: the transcript writes them straight, so "it’s" in an
    AI-written plan would never be heard."""
    for r in rows[1:]:
        if r and get(r, "vo_anchor"):
            put(r, "vo_anchor", get(r, "vo_anchor").translate(QUOTES))


def _normalize_layers(rows: List[List[str]], get, put, notes: List[str]) -> None:
    """Before Hybrid reads the plan: every layer row gets a type it knows and an id. A title with no type is a title card
    (hud_title); a type it does not know but can guess is renamed; a layer that is nothing it can show is left out. Each
    change goes to the notes ("Fixed for you"), so an AI's small slip never stops a video."""
    n_by_beat: Dict[str, int] = {}
    for k in range(1, len(rows)):
        r = rows[k]
        if not r or get(r, "row").lower() != "layer":
            continue
        beat = get(r, "beat")
        n_by_beat[beat] = n_by_beat.get(beat, 0) + 1
        typ = get(r, "type").lower().strip()
        what = get(r, "label") or get(r, "text") or get(r, "sub")
        if typ not in LAYER_KINDS:
            new = LAYER_ALIASES.get(typ) or ("hud_title" if get(r, "label") else "caption" if get(r, "text") else "")
            if not new:
                notes.append(f"beat {beat}: a layer row with no type and nothing to show was left out")
                rows[k] = []
                continue
            put(r, "type", new)
            notes.append(f"beat {beat}: the layer {what!r} had " + (f"the type {typ!r}" if typ else "no type") + f", so it is a {new} now")
        if not get(r, "id"):
            put(r, "id", f"{beat}_layer{n_by_beat[beat]}")


def plain_problem(msg: str) -> str:
    """Hybrid's short messages in plain words ("beat 2: type" -> which beat, which cell, what to do)."""
    m = re.match(r"^beat (\d+): (\w+)$", str(msg).strip())
    if m:
        return (f"beat number {m.group(1)} of the plan has a row whose {m.group(2)!r} cell is missing or not readable: open the plan "
                f"(Open plan folder), fill that cell, and load it again")
    return str(msg)


# ---- weather_layers.csv (the weather graphics) ---------------------------------------------------------------------------------

TYPE_ALIASES = {
    "temp": "temp_marker", "temperature": "temp_marker", "temp_marker": "temp_marker", "city_temp": "temp_marker",
    "strip": "forecast_strip", "forecast": "forecast_strip", "five_day": "forecast_strip", "5_day": "forecast_strip",
    "now": "now_card", "current": "now_card", "conditions": "now_card",
    "alert": "alert_area", "alerts": "alert_area", "warning": "alert_area", "warnings": "alert_area",
    "sat": "satellite", "satellite_image": "satellite",
    "source": "source_line", "sources": "source_line", "credit_line": "source_line",
    "title": "headline", "lower_third": "headline", "lowerthird": "headline",
    "label": "place_label", "city_label": "place_label", "place": "place_label",
}


def _json_cell(raw: str):
    raw = str(raw or "").strip()
    if not raw:
        return {}, False
    for attempt in (raw, raw.replace("'", '"')):
        try:
            v = json.loads(attempt)
            return (v if isinstance(v, dict) else {}), attempt != raw or not isinstance(v, dict)
        except ValueError:
            pass
    try:
        v = ast.literal_eval(raw)
        return (v if isinstance(v, dict) else {}), True
    except (ValueError, SyntaxError):
        return {}, True


def _loose_city(name: str):
    """find_city, also for a covered city written without its state ("Dallas", "dallas tx"); None when it is not one."""
    from .cities import cities, find_city

    try:
        return find_city(name)
    except (KeyError, ValueError):
        pass
    want = re.sub(r"[^a-z ]+", " ", str(name).lower()).split()
    if not want:
        return None
    hits = [c for c in cities().values() if c.name.lower().split() == want[:len(c.name.split())]]
    return hits[0] if len(hits) == 1 else None


def _city_target(place: str) -> Optional[str]:
    c = _loose_city(place)
    return c.key.replace(", ", ",") if c else None


def _default_source(typ: str, place: str, old) -> Optional[str]:
    target = _city_target(place) or (_city_target(old.target) if old is not None else None)
    if typ == "temp_marker" and target:
        return f"nws:forecast@{target}#day1"
    if typ == "forecast_strip" and target:
        return f"nws:forecast@{target}#day1-5"
    if typ == "now_card" and target:
        return f"nws:obs@{target}"
    if typ == "satellite":
        return "gibs:geocolor@latest"
    if typ == "alert_area":
        from .cities import US_STATES

        for cand in (place, old.target if old is not None else ""):
            s = str(cand).strip().upper()
            if s in US_STATES or s == "US":
                return f"nws:alerts@{s}"
            t = _city_target(cand)
            if t:
                return f"nws:alerts@{t.rsplit(',', 1)[-1].strip()}"
        return "nws:alerts@US"
    return None


def repair_layers(text: str, notes: List[str], aliases: Optional[Dict[str, str]] = None):
    """weather_layers.csv read the forgiving way: every row is repaired where the intent is clear, else left out with a note.
    Only a file with no usable row at all raises."""
    from .sidecar import SidecarError, WxRow, _check, extra_keys, known_types, parse_data_source

    aliases = aliases or {}
    rows = _csv_rows(text)
    if not rows:
        raise SidecarError(["the plan has no weather graphics (no weather rows)"])
    head = [c.strip().lower() for c in rows[0]]
    types = set(known_types())
    out: List[WxRow] = []
    ids: Dict[str, int] = {}
    prev_beat = ""
    for n, cells in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in cells):
            continue
        r = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(head) if h}
        what = r.get("id") or f"row {n}"

        def skip(why: str) -> None:
            notes.append(f"weather graphic {what}: left out ({why})")

        typ = re.sub(r"[\s-]+", "_", r.get("type", "").lower())
        typ = typ if typ in types else TYPE_ALIASES.get(typ, typ)
        if typ not in types:
            skip(f"Weather has no graphic called {r.get('type')!r}")
            continue
        beat = aliases.get(r.get("beat", ""), r.get("beat", "")) or prev_beat
        if not beat:
            skip("it names no beat")
            continue
        prev_beat = beat
        rid = re.sub(r"[^A-Za-z0-9_]+", "_", r.get("id", "")).strip("_") or f"{typ}{n}"
        if rid in ids:
            k = 2
            while f"{rid}_{k}" in ids:
                k += 1
            rid = f"{rid}_{k}"
        extra, changed = _json_cell(r.get("extra", ""))
        allowed = extra_keys(typ)
        if set(extra) - allowed:
            extra = {k: v for k, v in extra.items() if k in allowed}
            changed = True
        if changed:
            notes.append(f"weather graphic {rid}: its extra cell was tidied")
        try:
            t = float(r["t"]) if r.get("t") else None
        except ValueError:
            t = None
        try:
            hold = float(r["hold"]) if r.get("hold") else None
        except ValueError:
            hold = None
        if hold is not None and hold <= 0:
            hold = None
        u = r.get("until", "").lower().replace(" ", "_")
        try:
            until = float(u) if u else "beat_end"
        except ValueError:
            # "end", "until the end", "video_end", "forever" -> the video's end; "beat_end", "end of beat", anything else -> its beat
            until = "end" if ("beat" not in u and ("end" in u or u in ("forever", "always"))) else "beat_end"
        ds = None
        if r.get("data_source"):
            try:
                ds = parse_data_source(re.sub(r"\s*,\s*", ",", r["data_source"]))
            except ValueError:
                ds = None
        place = r.get("place", "")
        city = _loose_city(place) if place else None
        if city is not None and place != city.key:
            place = city.key
        if ds is not None and ds.provider == "nws" and ds.product in ("forecast", "obs"):
            target = _city_target(ds.target)
            if target and target != ds.target.replace(", ", ","):
                ds = parse_data_source(f"{ds.provider}:{ds.product}@{target}" + (f"#{ds.selector}" if ds.selector else ""))
        row = WxRow(line=n, beat=beat, id=rid, type=typ, vo_anchor=r.get("vo_anchor", ""), t=t, place=place,
                    data_source=ds, hold=hold, until=until, extra=extra)
        ok, why = _settle(row, _check, parse_data_source)
        if not ok:
            skip(why)
            continue
        ids[rid] = n
        out.append(row)
    if not out:
        raise SidecarError(["the plan has no weather graphics Weather can show (every weather row was left out: see the notes)"])
    return out


def _settle(row, check, parse_data_source) -> Tuple[bool, str]:
    """Try the row; on each refusal, change the one thing the refusal names, up to a few times."""
    from .cities import find_city

    why = ""
    for _ in range(6):
        try:
            check(row)
            return True, ""
        except KeyError as exc:
            return False, f"{str(exc).strip(chr(39))}"
        except ValueError as exc:
            why = str(exc)
        if "takes no data_source" in why:
            row.data_source = None
        elif "needs a data_source" in why or " takes " in why:
            src = _default_source(row.type, row.place, row.data_source)
            if not src or (row.data_source is not None and src == row.data_source.text):
                return False, why
            row.data_source = parse_data_source(src)
        elif "is not the city of the data_source" in why:
            try:
                row.place = find_city(row.data_source.target).key
            except (KeyError, ValueError):
                return False, why
        elif "needs a place" in why:
            if row.data_source is None or not _city_target(row.data_source.target):
                return False, why
            row.place = find_city(row.data_source.target).key
        elif "forecast_strip shows 3 to 7 days" in why or "day range must go forward" in why or "#day1 .. #day7" in why:
            ds = row.data_source
            row.data_source = parse_data_source(f"{ds.provider}:{ds.product}@{ds.target}#day1-5" if row.type == "forecast_strip"
                                                else f"{ds.provider}:{ds.product}@{ds.target}#day1")
        elif "temp_marker shows one day" in why:
            ds = row.data_source
            row.data_source = parse_data_source(f"{ds.provider}:{ds.product}@{ds.target}#day{ds.days()[0]}")
        elif "nws:alerts@ takes a state" in why:
            row.data_source = parse_data_source(_default_source("alert_area", row.place, row.data_source))
        elif "gibs:geocolor@ takes latest" in why:
            row.data_source = parse_data_source("gibs:geocolor@latest")
        else:
            return False, why
    return False, why


# ---- timing ------------------------------------------------------------------------------------------------------------------

def windows(rows, plan, words: Sequence, notes: List[str]):
    """(rows kept, id -> Window): weather.timing.layer_windows, with each refusal turned into the nearest sensible timing."""
    from .sidecar import SidecarError
    from .timing import Window, layer_windows

    beats = {b.id: b for b in plan.beats}
    kept = []
    for r in rows:
        if r.beat not in beats:
            notes.append(f"weather graphic {r.id}: beat {r.beat} is not in the plan, so it is left out")
            continue
        kept.append(r)
    out = {}
    for r in kept:
        try:
            out.update(layer_windows([r], plan, words))
            continue
        except SidecarError as exc:
            why = exc.problems[0] if exc.problems else ""
        b = beats[r.beat]
        t = b.start + min(0.3, max(0.0, (b.end - b.start) / 4))
        if r.hold is not None:
            end = t + r.hold
        elif r.until == "end":
            end = plan.duration
        elif r.until == "beat_end":
            end = b.end
        else:
            end = float(r.until)
        end = min(max(end, t + 2.0), plan.duration)
        if end <= t + 0.2:
            notes.append(f"weather graphic {r.id}: no time left for it at the end of the video, so it is left out")
            continue
        if "not spoken" in why or "needs the narration" in why:
            notes.append(f"weather graphic {r.id}: its words ({r.vo_anchor!r}) were not heard in beat {r.beat}, so it appears as the beat starts")
        elif "outside its beat" in why:
            notes.append(f"weather graphic {r.id}: its time was outside beat {r.beat}, so it appears as the beat starts")
        else:
            notes.append(f"weather graphic {r.id}: timing adjusted ({why.split(': ', 1)[-1]})")
        out[r.id] = Window(round(t, 3), round(end, 3))
    return [r for r in kept if r.id in out], out


def build(rows, snap, wins, notes: List[str]):
    """weather.events.build; a graphic the data cannot fill (a forecast day that is not there, a city not fetched) is left out."""
    from .events import build as build_events

    rows = list(rows)
    while True:
        try:
            return rows, build_events(rows, snap, wins)
        except (ValueError, KeyError) as exc:
            m = ID_RE.search(str(exc))
            rid = m.group(1) if m else None
            if rid is None:
                # a KeyError from the data names no row: find the row by building each alone
                for r in rows:
                    try:
                        build_events([r], snap, {r.id: wins[r.id]})
                    except (ValueError, KeyError):
                        rid = r.id
                        break
            if rid is None or not any(r.id == rid for r in rows):
                raise
            notes.append(f"weather graphic {rid}: the weather data has nothing for it, so it is left out ({str(exc).strip(chr(39))})")
            rows = [r for r in rows if r.id != rid]


# ---- footage sources ---------------------------------------------------------------------------------------------------------

def fix_footage(plan, project_root, notes: List[str]) -> int:
    """A clip or card from a source Weather never uses (generated video, an unapproved event clip, YouTube) becomes a stock request
    for what the beat's narration describes. Returns how many were changed."""
    from .footage import footage_problems
    from .teamplate.cutaways import request_for

    bad = footage_problems(plan, project_root)
    if not bad:
        return 0
    changed = 0
    for b in plan.beats:
        items = list(b.clips) + ([b.support] if getattr(b, "support", None) is not None else []) + list(getattr(b, "more_cards", []) or [])
        for item in items:
            if not any(repr(item.asset) in p or str(item.asset) in p for p in bad):
                continue
            want = request_for(b.narration or "") or "dark storm clouds rolling"
            kind = "stock_video" if any(item is c for c in b.clips) else "stock_image"
            old = item.asset
            item.asset = f"{kind}:{want}"
            changed += 1
            notes.append(f"beat {b.id}: footage {old!r} cannot be used in a weather video, so it asks for stock footage of {want!r}")
    return changed
