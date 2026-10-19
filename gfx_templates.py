"""The universal graphics template library (gfx-core/templates/<family>/<id>.json) on the planner's side.

Any niche can use it: a CSV row (or the auto planner) picks a template, this module fills its slots and gives back the event the niche's
renderer draws (pakMap: a `map_template` event). A template names, per slot, which CSV column fills it (`from`); a slot marked `required`
is never drawn from its example default: a row that leaves it empty is an error naming the slot (the examples are for the preview only).

  rows    "CARNARVON=230; SYDNEY=1200"  or  "A|B|C"           -> [{"label": "CARNARVON", "value": 230}, ...]
  values  "181;178;99"                                         -> [181, 178, 99]
  labels  "J;F;M"                                              -> ["J", "F", "M"]

Auto planner: `auto_events(words, ...)` reads the narration sentence by sentence and, where a sentence states one number with its meaning
(a share, a size, a count), adds the matching template with the slots taken from the sentence, within a pacing budget (gap, spacing, no
repeats). Only templates that have an extractor here are ever placed automatically, so a template can never show content nobody said.
"""

from __future__ import annotations

import collections
import copy
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

COLUMNS = ("label", "sub", "text", "value_from", "value_to", "format", "rows", "values", "labels", "geo", "geo_area")
NICHES = ("map", "travel", "geopolitics", "history", "space", "weather", "tech", "any")


def library_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "gfx-core" / "templates"


@lru_cache(maxsize=1)
def load_library() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    root = library_dir()
    if not root.is_dir():
        return out
    for f in sorted(root.rglob("*.json")):
        if f.name == "index.json":
            continue
        t = json.loads(f.read_text(encoding="utf-8"))
        out[t["id"]] = t
    return out


def get(template_id: str) -> Dict[str, Any]:
    lib = load_library()
    tid = str(template_id or "").strip().lower().replace(" ", "_").replace("-", "_")
    if tid in lib:
        return lib[tid]
    import difflib
    hint = difflib.get_close_matches(tid, list(lib), n=1)
    raise ValueError(f"unknown template {template_id!r}" + (f" (did you mean {hint[0]!r}?)" if hint else f" (there are {len(lib)}: see catalog_text())"))


def validate(t: Dict[str, Any]) -> List[str]:
    """The contract gfx-core/lib/library.mjs checks too (its test also draws every template)."""
    p: List[str] = []
    for k in ("id", "family", "use", "items", "niches"):
        if k not in t:
            p.append(f"{t.get('id', '?')}: {k!r} is missing")
    slots = t.get("slots", {})
    used = set(re.findall(r"\{([a-zA-Z_]\w*)(?:\.[\w.]+)?\}", json.dumps(t.get("items", []))))
    for k in sorted(used - set(slots) - {"it", "i", "n", "len"}):
        p.append(f"{t.get('id')}: uses {{{k}}} but has no slot {k!r}")
    for k, s in slots.items():
        if s.get("from") and s["from"] not in COLUMNS:
            p.append(f"{t.get('id')}: slot {k!r} comes from an unknown column {s['from']!r}")
    for n in t.get("niches", []):
        if n not in NICHES:
            p.append(f"{t.get('id')}: unknown niche {n!r}")
    if t.get("triggers"):
        try:
            re.compile(t["triggers"])
        except re.error as exc:
            p.append(f"{t.get('id')}: triggers is not a valid pattern ({exc})")
    return p


# ---- slot values from a row's fields -------------------------------------------------------------------------------------------------
def _num(v: Any) -> Optional[float]:
    m = re.search(r"-?\d[\d,]*\.?\d*", str(v if v is not None else ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def parse_rows(text: Any) -> List[Dict[str, Any]]:
    """"A=230; B=1200" -> bars. "A|B|C" -> bars with no number (a list). A list of dicts/strings is accepted as is."""
    if isinstance(text, (list, tuple)):
        out = []
        for x in text:
            if isinstance(x, dict):
                out.append({**x, "label": str(x.get("label", x.get("name", ""))), "value": _num(x.get("value", 0)) or 0})
            else:
                k, _, v = str(x).partition("=")
                out.append({"label": k.strip(), "value": _num(v) or 0})
        return out
    t = str(text or "")
    parts = [p for p in (t.split(";") if ";" in t or "=" in t else t.split("|")) if p.strip()]
    out = []
    for part in parts:
        k, _, v = part.partition("=")
        row: Dict[str, Any] = {"label": k.strip(), "value": _num(v) or 0, "text": v.strip()}
        if "@" in k:                              # "SYDNEY@green=1200": a palette colour for the bar
            name, _, colour = k.partition("@")
            row["label"], row["color"] = name.strip(), colour.strip()
        out.append(row)
    return out


def parse_list(text: Any, numbers: bool = False) -> List[Any]:
    if isinstance(text, (list, tuple)):
        items = list(text)
    else:
        t = str(text or "")
        items = [x.strip() for x in re.split(r"[;|]", t) if x.strip()] if re.search(r"[;|]", t) else [x.strip() for x in t.split(",") if x.strip()]
    return [(_num(x) or 0) for x in items] if numbers else [str(x) for x in items]


def slots_from_fields(t: Dict[str, Any], fields: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Slot values from {label, sub, text, value_from, value_to, format, rows, values, labels} (a CSV row's columns), then `extra` slots
    (a JSON object that names slots directly). Raises ValueError naming every required slot left empty."""
    out: Dict[str, Any] = {}
    for name, spec in (t.get("slots") or {}).items():
        frm = spec.get("from")
        raw = fields.get(frm) if frm else None
        if (raw is None or raw == "") and frm in ("label", "text"):
            raw = fields.get("text" if frm == "label" else "label")      # a heading may come from either column
        if raw is None or raw == "" or raw == []:
            continue
        if frm in ("geo", "geo_area"):
            out[name] = raw
        elif frm == "rows":
            out[name] = parse_rows(raw)
        elif frm == "values":
            out[name] = parse_list(raw, numbers=True)
        elif frm == "labels":
            out[name] = parse_list(raw)
        elif isinstance(raw, float) and raw.is_integer():
            out[name] = int(raw)
        else:
            out[name] = raw
    for k, v in (extra or {}).items():
        if k in (t.get("slots") or {}):
            out[k] = parse_rows(v) if k == "rows" and not isinstance(v, list) else v   # (a slot named in params.slots, any JSON value)
    if "rows" in (t.get("slots") or {}) and "rows" not in out and fields.get("text") and re.search(r"[=|;]", str(fields["text"])):
        out["rows"] = parse_rows(fields["text"])      # the text column may carry the bars when there is no rows column
    missing = [n for n, s in (t.get("slots") or {}).items() if s.get("required") and out.get(n) in (None, "", [])]
    if missing:
        cols = ", ".join(f"{n} ({t['slots'][n].get('from') or 'slots'})" for n in missing)
        raise ValueError(f"template {t['id']} needs {cols}")
    return out


def slim_polys(polys: Any, max_pts: int = 420) -> List[Any]:
    """A MultiPolygon's rings with fewer points (every n-th), rounded, so a country outline costs a few KB in the spec."""
    out = []
    for poly in polys or []:
        rings = []
        for ring in poly:
            step = max(1, len(ring) // max_pts)
            pts = [[round(p[0], 3), round(p[1], 3)] for p in ring[::step]]
            if pts and pts[0] != pts[-1]:
                pts.append(pts[0])
            if len(pts) >= 4:
                rings.append(pts)
        if rings:
            out.append(rings)
    out.sort(key=lambda p: -len(p[0]))
    return out[:150]            # the biggest pieces (a country's islands beyond the 150th are a few pixels)


def problem(template_id: str, fields: Dict[str, Any], extra: Optional[Dict[str, Any]] = None, *, has_geo: bool = False) -> Optional[str]:
    """Why a row cannot make this graphic (an unknown id, a required slot left empty, places missing), or None. The guard and Hybrid use it to
    leave such a layer out with a note instead of stopping."""
    try:
        t = get(template_id)
    except ValueError as exc:
        return str(exc)
    wants = {s.get("from") for s in (t.get("slots") or {}).values()}
    f = dict(fields)
    if has_geo:
        f.setdefault("geo", [[0.0, 0.0]]); f.setdefault("geo_area", [[[[0, 0], [0, 1], [1, 1], [0, 0]]]])
    try:
        slots_from_fields(t, f, extra)
    except ValueError as exc:
        return str(exc)
    if not has_geo and (wants & {"geo", "geo_area"}):
        return f"template {t['id']} needs a place in geo_ref" + (" (places joined with ;)" if "geo" in wants else " (an area)")
    return None


def _all_items(t: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = list(t.get("items", []))
    for ph in t.get("phases") or []:
        items += ph.get("items", [])
    return items


def map_bound(t: Dict[str, Any]) -> bool:
    """True for a graphic drawn ON the map: its points or outline are places (geo / geo_area slots) or it follows a place across the screen
    (`follow`). Under full-screen footage the map is hidden, so such a graphic has nothing to sit on there."""
    wants = {s.get("from") for s in (t.get("slots") or {}).values()}
    return bool(wants & {"geo", "geo_area"}) or any(it.get("follow") for it in _all_items(t))


def needs_picture(t: Dict[str, Any]) -> bool:
    return any(k == "image" and s.get("required") for k, s in (t.get("slots") or {}).items())


def over_footage_problem(template_id: str) -> Optional[str]:
    """Why this graphic cannot be drawn over full-screen footage (an unknown id, one that sits on the map, one that needs a picture), or None."""
    try:
        t = get(template_id)
    except ValueError as exc:
        return str(exc)
    if map_bound(t):
        return f"template {t['id']} is drawn on the map (it needs a place on it), and the map is hidden under footage"
    if needs_picture(t):
        return f"template {t['id']} needs a picture of its own"
    return None


def cue_names(t: Dict[str, Any]) -> List[str]:
    return sorted(set(re.findall(r"@([A-Za-z][\w'-]*)", json.dumps(t.get("items", [])))))


def find_cues(t: Dict[str, Any], words: Sequence[Tuple[str, float, float]], start: float, end: float) -> Dict[str, float]:
    """Seconds from `start` at which the narrator says each cue word ("@photon" in a template) inside [start, end]."""
    cues: Dict[str, float] = {}
    for name in cue_names(t):
        for tok, a, _b in words:
            if start - 0.5 <= a <= end and re.sub(r"\W", "", tok).lower() == name.lower():
                cues[name.lower()] = round(max(0.0, a - start), 3)
                break
    return cues


def event_for(template_id: str, fields: Dict[str, Any], *, event_id: str, t_in: float, t_out: Optional[float] = None, follow: Optional[Dict[str, float]] = None,
              extra: Optional[Dict[str, Any]] = None, words: Sequence[Tuple[str, float, float]] = ()) -> Tuple[Dict[str, Any], float]:
    """The pakMap `map_template` event for a template and a row's fields, and the template's own length (its natural hold)."""
    t = get(template_id)
    slots = slots_from_fields(t, fields, extra)
    end = t_out if t_out is not None else t_in + float(t.get("hold", 6))
    ev: Dict[str, Any] = {"id": event_id, "type": "map_template", "template": without_example_text(_public(t), slots), "slots": slots, "t_in": round(t_in, 3), "t_out": round(end, 3)}
    cues = find_cues(t, words, t_in, end) if words else {}
    if cues:
        ev["cues"] = cues
    if follow:
        ev["follow"] = follow
    return ev, float(t.get("hold", 6))


def _public(t: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in t.items() if not k.startswith("_") and k not in ("triggers", "use", "tags")}


# Optional slots whose default is not example text but how the graphic works (a corner, a colour, the words BEFORE / AFTER, a generic kicker).
_FUNCTIONAL_DEFAULTS = {("counter_corner", "anchor"), ("flow_route", "color"), ("before_after_slider", "before_label"), ("before_after_slider", "after_label"),
                        ("fact_card", "kicker"), ("chapter_next", "kicker")}


def without_example_text(tpl: Dict[str, Any], slots: Dict[str, Any]) -> Dict[str, Any]:
    """A copy of the template for one event with the library's EXAMPLE text blanked in every optional slot the event does not fill ("SECOND LARGEST
    COUNTRY ON EARTH", "NEW SOUTH WALES · POP. 17,000", "SOURCE: NATIONAL STATISTICS", a unit like KM² or mm). The renderer fills an empty slot from the
    template's default, which is fine in the library's preview and a made-up fact in a video."""
    out = copy.deepcopy(tpl)
    for k, spec in (out.get("slots") or {}).items():
        if spec.get("required") or not isinstance(spec.get("default"), str) or (out.get("id"), k) in _FUNCTIONAL_DEFAULTS:
            continue
        if slots.get(k, "") in ("", None):
            spec["default"] = ""
    return out


# ---- auto planner: one stated number -> the template that shows it -------------------------------------------------------------------------
_SCALE = {"million": ("M", "MILLION"), "billion": ("B", "BILLION"), "trillion": ("T", "TRILLION"), "thousand": ("K", "THOUSAND")}
_UNITS = {   # longer phrases first: the first pattern that matches the whole phrase names the unit
    r"square kilomet(?:re|er)s?": "KM²", r"sq\.? ?km": "KM²", r"km²": "KM²", r"square miles?": "MI²", r"hectares?": "HA", r"acres?": "ACRES",
    r"kilomet(?:re|er)s? (?:per|an) hour": "KM/H", r"km/h|kph|kmh": "KM/H", r"miles (?:per|an) hour|mph": "MPH", r"met(?:re|er)s? per second|m/s": "M/S",
    r"nautical miles?": "NM", r"knots?|kts?": "KT",
    r"kilomet(?:re|er)s?": "KM", r"miles": "MILES", r"years": "YEARS", r"met(?:re|er)s?": "M", r"feet|foot|ft": "FT", r"inch(?:es)?": "IN",
    r"centimet(?:re|er)s?|cm": "CM", r"millimet(?:re|er)s?|mm": "MM", r"kilograms?|kg": "KG", r"tonnes?|tons?": "TONNES", r"ounces?|oz": "OUNCES",
}
_SPEED_OR_TEMP = ("KM/H", "MPH", "M/S", "KT", "°C", "°F")          # units that are a measurement by themselves: no further context needed
_NEG = r"(?:(-|−|minus\s+)\s*)?"
_TEMP_RE = re.compile(rf"(?i){_NEG}(\d{{1,3}}(?:\.\d+)?)\s*(?:°\s*([CF])\b|degrees?\s+(celsius|fahrenheit|centigrade)\b|degrees?\s*([CF])\b)")
# a small measurement (16 metres, 5 miles) is a fact only when the sentence says what is being measured
_MEASURE_CONTEXT = re.compile(r"(?i)\b(rise[sn]?|rising|reach(?:es|ed)?|tall|high|higher|deep|deeper|long|longer|wide|wider|thick|fast|faster|speeds?|winds?|gusts?|temperatures?|"
                              r"drops?|dropped|falls?|fell|climb\w*|height|depth|length|width|distance|rainfall|snowfall|waves?|measures?|stretch\w*|span\w*|weigh\w*|below|above)\b")
_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"


def _before(sentence: str, start: int, n: int = 4) -> str:
    words = re.findall(r"[A-Za-z][\w'-]*", sentence[:start])
    stop = {"a", "an", "the", "of", "is", "are", "was", "were", "has", "have", "about", "around", "over", "than", "and", "in", "to", "with", "for", "that",
            "it", "its", "this", "they", "covers", "spans", "measures", "reaches", "holds", "makes", "up", "nearly", "almost", "roughly", "just", "only",
            "more", "less", "least", "most", "over", "under", "approximately", "exactly", "close", "at"}
    while words and words[-1].lower() in stop:
        words.pop()
    return " ".join(words[-n:]).upper()


_ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}


_BIG_SCALE = {"thousand": 10 ** 3, "million": 10 ** 6, "billion": 10 ** 9, "trillion": 10 ** 12}
_NUM_WORD = re.compile(r"(?i)\b(?:(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
                       r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion|and)(?:[ -]+|\b))+")


def _number_words(sentence: str) -> str:
    """A narration written in words states its numbers in words: "a hundred metres" -> "100 metres", "twenty million ounces" -> "20 million ounces",
    "thirty-five thousand years" -> "35,000 years". Only a run that holds a hundred / thousand / million / billion / trillion or a tens word is turned
    into digits ("one of the" and "a few" stay words); a scale of a million or more stays a word after its digits, the way the graphics read it."""
    def conv(m) -> str:
        raw = m.group(0)
        toks = [t for t in re.split(r"[ -]+", raw.strip().lower()) if t]
        while toks and toks[-1] == "and":
            toks.pop()
        while toks and toks[0] == "and":
            toks.pop(0)
        if not toks or not any(t in _BIG_SCALE or t == "hundred" or t in _TENS for t in toks):
            return raw
        if toks[0] in _BIG_SCALE or toks[0] == "hundred":      # "10 million": the scale word has its digits already; "a hundred" has its "a"
            return raw
        if not any(t in _BIG_SCALE or t == "hundred" for t in toks):      # "twenty five" is 25; "nineteen fifty" is a year said in words, never 69
            if not (toks[0] in _TENS and (len(toks) == 1 or (len(toks) == 2 and 0 < _ONES.get(toks[1], 0) < 10))):
                return raw
        for k, t in enumerate(toks):          # "and" joins only inside one number ("a hundred and five"); "five and nine million" is two numbers, left as the narrator said them
            if t == "and" and (k == 0 or toks[k - 1] not in ("hundred", "thousand")):
                return raw
        total, cur, scaled = 0, 0, None
        for t in toks:
            if t in ("a", "an"):
                cur = cur or 1
            elif t == "and":
                continue
            elif t in _ONES:
                cur += _ONES[t]
            elif t in _TENS:
                cur += _TENS[t]
            elif t == "hundred":
                cur = max(cur, 1) * 100
            elif t in _BIG_SCALE:
                scale = _BIG_SCALE[t]
                if scale >= 10 ** 6:
                    scaled = (total + max(cur, 1), t)
                    total = cur = 0
                else:
                    total += max(cur, 1) * scale
                    cur = 0
        trail = raw[len(raw.rstrip()):]
        if scaled is not None:
            return f"{scaled[0] + total + cur if (total or cur) else scaled[0]} {scaled[1]}{trail}"
        return f"{total + cur:,}{trail}"
    return _NUM_WORD.sub(conv, sentence)


def _spoken_number(sentence: str) -> str:
    """"sixty percent" / "forty five percent" -> "60 percent" / "45 percent" (a narration written in words; a transcript usually has digits).
    Other numbers written in words become digits too (_number_words)."""
    sentence = _number_words(sentence)
    def one(m):
        a, b = m.group(1).lower(), (m.group(2) or "").lower()
        v = _TENS.get(a, _ONES.get(a, 0)) + (_ONES.get(b, 0) if a in _TENS and b else 0)
        return f"{v} percent"
    words = "|".join(list(_ONES) + list(_TENS))
    return re.sub(rf"\b({words})(?:[ -]({'|'.join(_ONES)}))?\s+(?:percent|per cent)\b", one, sentence, flags=re.I)


def _percent(sentence: str) -> Optional[Dict[str, Any]]:
    sentence = _spoken_number(sentence)
    m = re.search(_NUM + r"\s*(?:%|percent|per cent)", sentence, re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    if not 0 <= v <= 100:
        return None
    return {"value": int(v) if v.is_integer() else v, "label": _before(sentence, m.start()) or "SHARE", "title": "SHARE"}


def _big(sentence: str) -> Optional[Dict[str, Any]]:
    """A stated quantity as a big number with its unit, as the narration says it (no unit is converted). A bare small number is not a headline; a
    small measurement (16 metres) is, when the sentence says what is measured; a speed or a temperature always is."""
    t = _TEMP_RE.search(sentence)
    if t:
        neg, raw, c1, word, c2 = t.groups()
        fahrenheit = (c1 or c2 or "").upper() == "F" or (word or "").lower() == "fahrenheit"
        value = float(raw)
        out = {"value": int(value) if value.is_integer() else value, "unit": "°F" if fahrenheit else "°C", "label": _before(sentence, t.start()) or "TEMPERATURE", "sub": ""}
        if neg:
            out["prefix"] = "−"
        return out
    scale = "|".join(_SCALE)
    unit_pat = "|".join(_UNITS)
    for m in re.finditer(_NUM + rf"\s*(?:({scale})\b)?\s*(?:({unit_pat})(?![A-Za-z]))?", sentence, re.I):
        raw, sc, un = m.group(1), (m.group(2) or "").lower(), m.group(3)
        if re.search(r"(?i)(?:\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred))\s*(?:to|or|and|[-–])\s*$", sentence[:m.start()].rstrip() + " "):
            continue                                           # "8 to 10,000 years": a range is not one number, and showing its end would misstate it
        value = float(raw.replace(",", ""))
        if not sc and not un and value < 1000:
            continue                                           # a bare small number is not a headline
        if not sc and not un and 1900 <= value <= 2100 and "," not in raw:
            continue                                           # a year
        unit = _SCALE[sc][1] if sc else ""
        if un:
            u = next(v for pat, v in _UNITS.items() if re.fullmatch(pat, un, re.I))
            if u == "M":
                u = "METERS" if "meter" in un.lower() else "METRES"     # a bare "M" would read as millions; the narrator's own spelling
            unit = f"{unit} {u}".strip()
        if not sc and value < 1000 and unit not in _SPEED_OR_TEMP and not (_MEASURE_CONTEXT.search(sentence) or _significant(sentence)):
            continue                                           # "a 5 mile walk": a number with a unit, but not a fact worth a graphic
        default = "TOTAL AREA" if "KM²" in unit else "KEY NUMBER"
        return {"value": int(value) if value.is_integer() else value, "unit": unit, "label": _before(sentence, m.start()) or default, "sub": ""}
    return None


_TIMES = {"twice": 2, "two times": 2, "three times": 3, "four times": 4, "five times": 5, "six times": 6, "ten times": 10}
_TIMES_RE = re.compile(r"\b(twice|two times|three times|four times|five times|six times|ten times)\s+(?:as\s+)?(?:large|big|bigger|larger|long|longer|wide|wider|heavy|heavier|tall|taller|many|much|more|populous)\b(?:\s+as|\s+than)?\s+(?:the\s+)?([A-Z][\w'.-]*(?:\s+(?:of\s+)?[A-Z][\w'.-]*){0,3})")
_YEAR_RE = re.compile(r"\b(?i:in|since|by|during|until|before|after|back in|from)\s+(?:the\s+)?(1[0-9]{3}s?|20[0-3][0-9]s?)\b")
_FROM_TO_RE = re.compile(r"\bfrom\s+((?:[A-Z][\w'.-]*)(?:\s+[A-Z][\w'.-]*){0,2})\s+(?:all the way\s+)?to\s+((?:[A-Z][\w'.-]*)(?:\s+[A-Z][\w'.-]*){0,2})")


def _times(sentence: str) -> Optional[Dict[str, Any]]:
    """"twice as large as France" -> a 2x number with what it is compared to."""
    m = _TIMES_RE.search(sentence)
    if not m:
        return None
    return {"value": _TIMES[m.group(1).lower()], "unit": "×", "label": f"THE SIZE OF {m.group(2).upper()}", "sub": ""}


def _year(sentence: str) -> Optional[Dict[str, Any]]:
    """"in 1947" -> the year wiping in."""
    m = _YEAR_RE.search(sentence)
    return {"text": m.group(1).upper(), "sub": ""} if m else None


def _route(sentence: str, resolve: Optional[Callable[[str], Optional[Tuple[float, float]]]] = None) -> Optional[Dict[str, Any]]:
    """"from Vancouver to Halifax" -> a route between the two places (both must be found on the map)."""
    if resolve is None:
        return None
    m = _FROM_TO_RE.search(sentence)
    if not m:
        return None
    a, b = resolve(m.group(1)), resolve(m.group(2))
    if not a or not b or a == b:
        return None
    return {"points": [[round(a[0], 4), round(a[1], 4)], [round(b[0], 4), round(b[1], 4)]], "from_label": m.group(1).upper(), "to_label": m.group(2).upper(), "label": ""}


# (template id, trigger pattern or None = the template's own "triggers", extractor)
_MEASURE_TRIGGER = r"(?i)\d[\d,.]*\s*(?:million|billion|trillion|thousand|square|%|(?:" + "|".join(_UNITS) + r")(?![A-Za-z])|°\s*[CF]\b|degrees?\s+(?:celsius|fahrenheit|centigrade)\b|degrees?\s*[CF]\b)"
import gfx_extractors as X   # noqa: E402  (extractors that need the sentence's words, its place in the narration and the map's place finder)

for _fn in (X.quote_card, X.quote_boxed, X.name_bar, X.place_lowerthird, X.fact_card, X.record_badge, X.timeline_strip, X.versus_numbers, X.checklist_card, X.three_rings, X.tag_fact, X.end_question, X.heading_card, X.punchline):
    _fn.ctx = True
_ANY = r"(?s)."


DOC_STYLE_TWINS = {"yellow_tag": "hud_title", "typed_caption": "caption", "counter_corner": "stat"}    # apply_doc_style: the News Doc look of a plan's own layers


def _big_gold(sentence: str) -> Optional[Dict[str, Any]]:
    """The same stated quantity as big_number, for the editorial serif numeral (gold_stat): value, unit and the narrator's label."""
    b = _big(sentence)
    if not b or b.get("prefix") or b["unit"] in ("°C", "°F"):
        return None
    v = float(b["value"])
    return {"value": b["value"], "dec": 0 if v.is_integer() else min(2, len(str(v).split(".")[1])), "unit": b["unit"], "label": b["label"]}


def _percent_dial(sentence: str) -> Optional[Dict[str, Any]]:
    """The same share as ring_percent, on a gauge (needle to the value out of 100)."""
    p = _percent(sentence)
    return {"value": p["value"], "max": 100, "unit": "%", "label": p["label"]} if p else None


def _versus_bars(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """The same two numbers as versus_numbers (two named things, one unit, stated side by side), drawn as two bars."""
    v = X.versus_numbers(sentence, ctx)
    if not v or not v.get("unit"):
        return None
    return {"title": f"{v['a_label']} VS {v['b_label']}", "rows": [{"label": v["a_label"], "value": v["a_value"]}, {"label": v["b_label"], "value": v["b_value"]}],
            "unit": v["unit"], "_t0": v.get("_t0")}


_versus_bars.ctx = True


def _big_count(sentence: str) -> Optional[Dict[str, Any]]:
    """The same quantity as big_number for stat_countup (a white number counting up with its label typed beside it): the unit goes in front of the label."""
    b = _big(sentence)
    if not b or b.get("prefix") or b["unit"] in ("°C", "°F"):
        return None
    return {"value": b["value"], "label": f"{b['unit']} {b['label']}".strip()}


def _big_corner(sentence: str) -> Optional[Dict[str, Any]]:
    """The same quantity as a counter in a corner panel (it leaves the middle of the picture alone): value, the narrator's label, the unit on the small line."""
    b = _big(sentence)
    if not b or b.get("prefix") or b["unit"] in ("°C", "°F"):
        return None
    return {"value": b["value"], "label": b["label"], "sub": b["unit"]}


def _versus_rows(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    v = X.versus_numbers(sentence, ctx)
    if not v or not v.get("unit"):
        return None
    return {"title": v["unit"], "rows": [{"label": v["a_label"], "value": v["a_value"]}, {"label": v["b_label"], "value": v["b_value"]}], "_t0": v.get("_t0")}


_versus_rows.ctx = True


def _name_kicker(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """The person of name_bar on a lower third with no bar: what they are as the kicker, their name as the title."""
    n = X.name_bar(sentence, ctx)
    return {"kicker": n["sub"], "title": n["label"], "_t0": n.get("_t0")} if n and n.get("sub") else None


_name_kicker.ctx = True


def _three_panel(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """`three kinds of habitat: wetland, forest and grassland` on the side panel: what the three are (the narrator's words) as its title."""
    r = X.three_rings(sentence, ctx)
    return {"title": r["_what"], "bullets": [x.capitalize() for x in r["items"]], "_t0": r["_t0"]} if r else None


_three_panel.ctx = True


def _steps_panel(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """A spoken sequence of three steps on the side panel (it holds up to three bullets)."""
    c = X.checklist_card(sentence, ctx)
    return {"title": c["title"], "bullets": c["items"], "_t0": c["_t0"], "_t1": c["_t1"]} if c and len(c["items"]) == 3 else None


_steps_panel.ctx = True


def _heading_words(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    h = X.heading_card(sentence, ctx)
    return {"text": h["kicker"], "_t0": h["_t0"]} if h and not h["title"] else None


def _heading_serif(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    h = X.heading_card(sentence, ctx)
    return {"kicker": h["kicker"], "title": h["title"], "_t0": h["_t0"], **({"_t1": h["_t1"]} if "_t1" in h else {})} if h and h["title"] else None


_heading_words.ctx = _heading_serif.ctx = True


def _punch_text(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    p = X.punchline(sentence, ctx)
    return {"text": p["text"], "_t0": p["_t0"]} if p else None


def _punch_keywords(sentence: str, ctx) -> Optional[Dict[str, Any]]:
    """The same short sentence as heavy words one after another with the longest word boxed in red (keyword_title)."""
    p = X.punchline(sentence, ctx)
    if not p or len(p["words"]) > 5:
        return None
    return {"words": p["words"], "accent": max(range(len(p["words"])), key=lambda i: len(p["words"][i])), "_t0": p["_t0"]}


_punch_text.ctx = _punch_keywords.ctx = True
TEXT_STYLES = ("text_slam", "text_typewriter", "text_stamp", "text_word_pop", "text_glow", "text_outline", "text_box", "text_sweep", "text_split", "text_stack", "text_underline", "tag_headline")
# Every graphic the planner can place on its own. One row = one rule: the template, the words that make a sentence a candidate, and the extractor that reads
# its slots from the narration (None = the sentence does not hold what the template needs: nothing is drawn). Several rows may read the same fact (a
# number as a big number or an editorial numeral); the scoring in auto_events picks the one that adds variety and fits where it goes.
AUTO = [("quote_card", _ANY, X.quote_card), ("quote_boxed", _ANY, X.quote_boxed), ("record_badge", _ANY, X.record_badge), ("fact_card", _ANY, X.fact_card),
        ("versus_numbers", _ANY, X.versus_numbers), ("rank_bars", _ANY, _versus_bars), ("timeline_strip", _ANY, X.timeline_strip), ("checklist_card", _ANY, X.checklist_card),
        ("three_rings", _ANY, X.three_rings), ("ring_percent", None, _percent), ("dial_gauge", None, _percent_dial),
        ("big_number", _MEASURE_TRIGGER, _big), ("gold_stat", _MEASURE_TRIGGER, _big_gold), ("big_number", _TIMES_RE.pattern, _times), ("year_wipe", _YEAR_RE.pattern, _year),
        ("route_travel", _FROM_TO_RE.pattern, _route), ("name_bar", _ANY, X.name_bar), ("place_lowerthird", _ANY, X.place_lowerthird), ("end_question", _ANY, X.end_question),
        ("stat_countup", _MEASURE_TRIGGER, _big_count), ("counter_corner", _MEASURE_TRIGGER, _big_corner), ("bubble_compare", _ANY, _versus_rows), ("stacked_compare", _ANY, _versus_rows),
        ("lower_kicker", _ANY, _name_kicker), ("side_panel", _ANY, _three_panel), ("side_panel", _ANY, _steps_panel),
        ("chapter_words", _ANY, _heading_words), ("chapter_serif", _ANY, _heading_serif), ("keyword_title", _ANY, _punch_keywords)] + [(tid, _ANY, _punch_text) for tid in TEXT_STYLES]
# tag_fact (gfx_extractors.tag_fact) is deliberately NOT a rule: on the real project every tag it drew restated a caption, counter or marker the plan already showed
# ("THE HIGHEST PEAK" beside the 1,167 counter that says HIGHEST PEAK), and a small text tag is the generic effect this planner is meant to move beyond.
# The definition of each rule, in words (read by gfx_inventory and checked by the tests): what it requires, when it is eligible, where it is placed, how it is
# timed and what happens when the narration does not give enough. weight = how much the fact adds when it is on screen (scoring); where = the contexts it may
# be drawn in ("map" = over the map, "footage" = above full-screen footage).
RULES: Dict[str, Dict[str, Any]] = {
    "quote_card": dict(weight=9, where=("map", "footage"), requires="a quotation in quote marks of 4-30 words, a speaker named in the sentence or 8+ words",
                       eligible="the sentence quotes someone", placement="left block, soft backing over footage", timing="from the first quoted word to the last, +1 s",
                       fallback="a quotation is never shortened: too long or too short = no card"),
    "quote_boxed": dict(weight=6, where=("map", "footage"), requires="a short (under 8 words) unattributed quotation", eligible="the narrator quotes a phrase",
                        placement="centre, heavy capitals", timing="from the quoted words", fallback="no quote marks = nothing"),
    "record_badge": dict(weight=9, where=("map", "footage"), requires="what record, where, new value and date, old value and date, all in one sentence",
                         eligible="a broken record is stated in full", placement="badge", timing="from the record words", fallback="anything missing = no badge"),
    "fact_card": dict(weight=7, where=("map", "footage"), requires="'Fact/Number N' and a headline of 2-7 words, in the same sentence or as the whole next sentence", eligible="a numbered fact or countdown item is announced",
                      placement="numbered card", timing="from 'Fact N'", fallback="no headline in the sentence = no card"),
    "versus_numbers": dict(weight=8, where=("map", "footage"), requires="two named things with two numbers in one unit, stated side by side", eligible="a comparison of two figures",
                           placement="plate with two numbers (backing over footage)", timing="from the first name", fallback="different units or scales = nothing"),
    "rank_bars": dict(weight=7, where=("map", "footage"), requires="the same two numbers and one unit as versus_numbers", eligible="a comparison of two figures",
                      placement="two bars", timing="from the first name", fallback="no unit = nothing"),
    "timeline_strip": dict(weight=8, where=("map", "footage"), requires="three or more consecutive sentences that each date one event, in order, within 14 s; or, across the whole narration, four or more sentences that each state one date (a year or a decade)",
                           eligible="a run of dated events, and a recap of all the dates after the last is spoken (first free moment within 45 s)", placement="strip (backing over footage)", timing="from the first date to the last, +1 s",
                           fallback="fewer than three, or out of order = nothing"),
    "checklist_card": dict(weight=7, where=("map", "footage"), requires="three to five consecutive sentences opening with First/Second/Third or Step one/two/three, each clause of 7 words and 24 characters or fewer",
                           eligible="a spoken sequence", placement="paper card on the right", timing="from the first step to the last, +1 s",
                           fallback="a longer clause = no card (it is never cut)"),
    "three_rings": dict(weight=6, where=("map", "footage"), requires="'three <things>:' and exactly three names of one or two words", eligible="three things are named together",
                        placement="three rings, centre", timing="from 'three'", fallback="two or four names = nothing"),
    "ring_percent": dict(weight=7, where=("map", "footage"), requires="a share stated as a percentage between 0 and 100", eligible="'60 percent' / 'sixty percent'",
                         placement="ring with its tag (own tag dropped beside a title chip)", timing="from the sentence start", fallback="no percentage = nothing"),
    "dial_gauge": dict(weight=5, where=("map", "footage"), requires="the same percentage as ring_percent", eligible="a share, when the ring was just shown",
                       placement="half-circle gauge", timing="from the sentence start", fallback="no percentage = nothing"),
    "big_number": dict(weight=6, where=("map", "footage"), requires="a quantity with a scale word or a unit (a small number only with what it measures), or 'twice as large as X'",
                       eligible="a measurement, a size, a count", placement="centre, count-up", timing="from the number words, held as the template says",
                       fallback="a bare small number, a year or no unit = nothing"),
    "gold_stat": dict(weight=5, where=("map", "footage"), requires="the same quantity as big_number", eligible="a quantity, when a big number was just shown",
                      placement="serif numeral, gold", timing="from the number words", fallback="a temperature is left to big_number"),
    "year_wipe": dict(weight=4, where=("map", "footage"), requires="a year or decade after in/since/by/during/until/before/after/from", eligible="a date is stated",
                      placement="large year wiped in", timing="from the sentence", fallback="no year = nothing"),
    "route_travel": dict(weight=7, where=("map",), requires="'from A to B' with both places found on the map", eligible="a journey",
                         placement="route drawn on the map", timing="from the sentence start", fallback="a place the atlas cannot find = nothing; never over footage (the map is hidden)"),
    "name_bar": dict(weight=6, where=("map", "footage"), requires="a person with what they are ('Jane Smith, a glaciologist,' / 'Dr. Smith said' / 'the painter Eugene von Guerard')",
                     eligible="the narrator introduces a person", placement="lower-left bar", timing="from the name", fallback="a bare name or a place name = nothing"),
    "place_lowerthird": dict(weight=4, where=("map", "footage"), requires="a place the narrator introduces that the map can find, not the subject of the whole video",
                             eligible="'In/At/Near X' or 'X is a <kind>'", placement="lower-left bar", timing="from the place name", fallback="unfindable place = nothing"),
    "stat_countup": dict(weight=5, where=("map", "footage"), requires="the same quantity as big_number", eligible="a quantity, when another number layout was just shown",
                         placement="white number counting up, label typed beside it (dims the frame)", timing="from the sentence start", fallback="a temperature is left to big_number"),
    "counter_corner": dict(weight=5, where=("map", "footage"), requires="the same quantity as big_number", eligible="a quantity, when the middle of the picture should stay clear",
                           placement="corner panel, top right", timing="from the sentence start", fallback="a temperature is left to big_number"),
    "bubble_compare": dict(weight=6, where=("map", "footage"), requires="the same two numbers and one unit as versus_numbers", eligible="a comparison of two figures",
                           placement="two proportional bubbles on a plate (backing over footage)", timing="from the first name", fallback="no unit = nothing"),
    "stacked_compare": dict(weight=6, where=("map", "footage"), requires="the same two numbers and one unit as versus_numbers", eligible="a comparison of two figures",
                            placement="stacked bars on a plate (backing over footage)", timing="from the first name", fallback="no unit = nothing"),
    "lower_kicker": dict(weight=5, where=("map", "footage"), requires="a person with what they are, as for name_bar", eligible="the narrator introduces a person",
                         placement="lower third with a kicker (the role) and the name", timing="from the name", fallback="no role = nothing (name_bar needs one too)"),
    "side_panel": dict(weight=6, where=("map", "footage"), requires="'three <things>:' with three names, or a spoken sequence of exactly three steps", eligible="three things or steps are listed",
                       placement="panel on the right 44% with a title and bullets", timing="from 'three' / the first step", fallback="two or four items = nothing"),
    "chapter_words": dict(weight=5, where=("map", "footage"), requires="'Part/Chapter/Section/Act N' announced with no title after it", eligible="the narrator announces a section",
                          placement="huge words on a dimmed frame", timing="from the announcement", fallback="a title after it goes to chapter_serif"),
    "chapter_serif": dict(weight=6, where=("map", "footage"), requires="'Part/Chapter N' and a title of 2-7 words in the same or the next sentence", eligible="a titled section is announced",
                          placement="serif kicker over a tracked title", timing="from the announcement to the end of the title", fallback="no title = chapter_words"),
    "keyword_title": dict(weight=2.5, group="punchline", group_gap_s=75.0, where=("map", "footage"), requires="a punchline (below) of at most five words", eligible="a short sentence lands as a beat",
                          placement="heavy words one by one, the longest boxed in red", timing="from the sentence start", fallback="six or more words = a text style instead"),
    "end_question": dict(weight=5, where=("map", "footage"), requires="one of the narration's last two sentences, a question of 3-14 words", eligible="the narrator closes with a question",
                         placement="centre, words popping in on a dimmed frame (backing over footage)", timing="from the question's first word", fallback="no question = nothing"),
}

for _tid in TEXT_STYLES:
    RULES[_tid] = dict(weight=2.5, group="punchline", group_gap_s=75.0, where=("map", "footage"),
                       requires="a punchline: a declarative sentence of 3-8 words, no figures, no question, right after a sentence of 14+ words, not a heading and not already said by the plan's own text",
                       eligible="a short sentence lands as a beat of its own", placement="centre, the style's own animation (dim or backing over footage)",
                       timing="from the sentence start, as long as the style holds", fallback="shown word for word: never reworded or shortened; at most one text effect in 75 s")
EXTRACTORS = {"ring_percent": _percent, "big_number": _big, "year_wipe": _year, "route_travel": _route}
_IDENTITY = {"quote_card", "quote_boxed", "name_bar", "place_lowerthird", "lower_kicker"}   # who/where/what was said: another one is a different fact, not a repeat of a look
LATE_START_S = 2.0         # a graphic that waits for a layer to end may start at most this long after its sentence began
MIN_VISIBLE_S = 3.0
MIN_SPACING_S = 6.0       # clear time between one auto template ending and the next starting
MIN_GAP_AFTER_S = 1.0     # after another graphic on screen
# The same template again (it was a flat 45 s): never the same fact twice close together, never the same layout right after itself, and within two
# minutes only for a fact that stands out (a superlative or a record) and only so often. Further apart than that it is free: the other limits
# (MIN_SPACING_S, MAX_PER_MINUTE) already keep a 20-40 minute video from filling with graphics.
NEAR_DUPLICATE_S = 240.0   # the same fact (same number, or nearly the same caption) is not shown again inside this
SAME_TEMPLATE_GAP_S = 12.0 # clear time between two uses of one template
SAME_TEMPLATE_WINDOW_S = 120.0
SAME_TEMPLATE_MAX = 2      # uses of one template per SAME_TEMPLATE_WINDOW_S
_SIGNIFICANT = re.compile(r"\b(as (?:tall|high|long|deep|big|large|wide|heavy|fast|strong) as|up to|(?:taller|higher|longer|deeper|bigger|larger|wider|heavier|faster|stronger) than|equal to|equivalent to|longest|largest|biggest|highest|tallest|deepest|oldest|fastest|most|record|only|first|worst|best|half|majority|more than|than the rest|than all)\b", re.I)
MAX_PER_MINUTE = 3
MIN_SPACING_FOOTAGE_S = 3.0   # over footage the map's own layers are hidden, so graphics may follow each other closer ...
MAX_PER_MINUTE_FOOTAGE = 5    # ... and more of them fit in a minute
FOOTAGE_PULL_S = 3.0          # a graphic whose moment falls on the map but whose footage starts within this long moves onto the footage
FIRST_AT_S = 4.0          # nothing in the opening seconds


_ABBREVIATIONS = {"dr.", "mr.", "mrs.", "ms.", "prof.", "st.", "jr.", "sr.", "vs.", "mt.", "gen.", "capt.", "col.", "lt.", "sgt.", "u.s.", "u.k.", "e.g.", "i.e."}


def _ends_sentence(tok: str) -> bool:
    """A word that ends a sentence: it ends in . ! or ?, and is not a title or abbreviation ("Dr." in "Dr. Santos said ...")."""
    return bool(re.search(r"[.!?][\"”’')]*$", tok)) and tok.lower().strip("\"“‘'(") not in _ABBREVIATIONS


def _trailing_stop(raw: str) -> str:
    m = re.search(r"[.!?][\"”’')]*$", raw)
    return m.group(0) if m else "."


def display_words(words: Sequence[Tuple[str, float, float]], script: Optional[str] = None) -> List[Tuple[str, float, float]]:
    """The transcript as the sentence planners can read it. Whisper's word list has no punctuation and no capitals, so `sentences()` saw one
    sentence for the whole video and no graphic was ever planned (all 11 real projects, 2026-10-19). Same words, same times, but:
    with the script, every word it heard is the script's own token again (capitals, quote marks, the full stop that ends the sentence);
    without it, a full stop goes after the words that end a pause. A transcript that already has sentence punctuation is returned unchanged.
    Only for planning what to draw; captions and anchors keep using the plain words."""
    words = list(words)
    if not words:
        return words
    ends = sum(1 for tok, _a, _b in words if _ends_sentence(tok))
    if ends >= max(2, len(words) // 40):      # about one stop per 40 words or more: punctuated (a plain transcript has none; one stray "?" does not count)
        return words
    if script and script.strip():
        got = _words_from_script(words, script)
        if got:
            return got
    out = list(words)
    run = 0
    for i, (tok, a, b) in enumerate(words):
        run += 1
        gap = (words[i + 1][1] - b) if i + 1 < len(words) else 99.0
        if i + 1 == len(words) or (gap >= 0.55 and run >= 5) or run >= 32:
            out[i] = (tok + ".", a, b)
            run = 0
    return out


def _words_from_script(words: List[Tuple[str, float, float]], script: str) -> Optional[List[Tuple[str, float, float]]]:
    """The script's own tokens with the times of the words that were heard. Where Whisper split or misspelled what the script has ("35,000" heard as
    "35" "000", a name heard as another word) the script's tokens take the span of the heard words, spread across it."""
    from difflib import SequenceMatcher

    from hybrid.narration import split_script

    def norm(t: str) -> str:
        return re.sub(r"[^0-9a-z]+", "", t.lower())

    flat: List[str] = []
    raw_tok: List[str] = []
    for text in split_script(script):
        for tok in text.split():
            if norm(tok):
                flat.append(norm(tok)); raw_tok.append(tok)
    wtok = [norm(w[0]) for w in words]
    ops = SequenceMatcher(None, flat, wtok, autojunk=False).get_opcodes()
    if sum(i2 - i1 for tag, i1, i2, _j1, _j2 in ops if tag == "equal") < 0.3 * max(1, len(flat)):
        return None                                           # the script is not what was spoken
    out: List[Tuple[str, float, float]] = []

    def put(tok: str, a: float, b: float) -> None:
        out.append((tok, a, b))

    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            for k in range(i2 - i1):
                put(raw_tok[i1 + k], words[j1 + k][1], words[j1 + k][2])
        elif tag == "insert":                                  # heard, not in the script: kept as heard
            for j in range(j1, j2):
                put(words[j][0], words[j][1], words[j][2])
        elif tag == "delete":                                  # in the script, not heard: no time of its own, but its sentence stop is kept
            stop = _trailing_stop(raw_tok[i2 - 1]) if _ends_sentence(raw_tok[i2 - 1]) else ""
            if stop and out and not _ends_sentence(out[-1][0]):
                out[-1] = (out[-1][0] + stop, out[-1][1], out[-1][2])
        else:                                                  # replace: m script tokens over the span of n heard words
            m, t0, t1 = i2 - i1, words[j1][1], words[j2 - 1][2]
            for k in range(m):
                put(raw_tok[i1 + k], t0 + (t1 - t0) * k / m, t0 + (t1 - t0) * (k + 1) / m)
    return out


def sentences(words: Sequence[Tuple[str, float, float]]) -> List[Tuple[str, float, float]]:
    out, cur, t0 = [], [], None
    for tok, a, b in words:
        if t0 is None:
            t0 = a
        cur.append(tok)
        if _ends_sentence(tok):
            out.append((" ".join(cur), t0, b)); cur, t0 = [], None
    if cur:
        out.append((" ".join(cur), t0 if t0 is not None else 0.0, words[-1][2]))
    return out


_SCALE_WORDS = (("TRILLION", 1e12), ("BILLION", 1e9), ("MILLION", 1e6), ("THOUSAND", 1e3))


class _Ctx:
    """What an extractor that needs more than a sentence's text gets (see gfx_extractors)."""

    def __init__(self, resolve, sents, index, raw, toks):
        self.resolve, self.sents, self.index, self.raw, self._toks = resolve, sents, index, raw, toks
        self._starts, pos = [], 0
        for tok, _a, _b in toks:
            self._starts.append(pos); pos += len(tok) + 1

    def _tok(self, char: int) -> int:
        k = 0
        for i, st in enumerate(self._starts):
            if st <= max(0, char):
                k = i
        return k

    def time_at(self, char: int) -> float:
        return self._toks[self._tok(char)][1] if self._toks else self.sents[self.index][1]

    def end_at(self, char: int) -> float:
        return self._toks[self._tok(char)][2] if self._toks else self.sents[self.index][2]

    def mentions(self, name: str) -> int:
        key = name.lower()
        return sum(1 for text, _a, _b in self.sents if key in text.lower())


def _sentence_tokens(words: Sequence[Tuple[str, float, float]]) -> List[List[Tuple[str, float, float]]]:
    out, cur = [], []
    for w in words:
        cur.append(w)
        if _ends_sentence(w[0]):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def _scaled(value: Any, text: Any) -> Optional[float]:
    """A number with the scale word of its unit or format ("0 MILLION KM²" -> x 1,000,000), None when it is not a number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    up = str(text or "").upper()
    for word, k in _SCALE_WORDS:
        if word in up:
            return v * k
    return v


def stat_is_redundant(stat: Dict[str, Any], template_id: str, slots: Dict[str, Any]) -> bool:
    """True when a plain `stat` box shows the very number a graphic made from the narration would show (so the graphic may replace it)."""
    shown = _scaled(stat.get("value_to"), stat.get("format"))
    new = _scaled(slots.get("value"), slots.get("unit"))
    if template_id not in ("big_number", "ring_percent") or shown is None or new is None:
        return False
    return abs(shown - new) <= 1e-9 * max(1.0, abs(new)) or (stat.get("value_to") is not None and float(stat["value_to"]) == float(slots.get("value")))


CHIP_TEMPLATES = ("yellow_tag",)     # the Doc Style title chip (a small pill, top-left): it does not block a graphic that leaves that corner free


def _uses_top_left(t: Dict[str, Any]) -> bool:
    """True when the template draws a tag or pill in the top-left corner, where the title chip sits."""
    for it in t.get("items", []):
        at = it.get("at")
        if it.get("p") in ("tag", "pill") and isinstance(at, list) and len(at) == 2 and all(isinstance(v, (int, float)) for v in at) and at[0] < 0.3 and at[1] < 0.2:
            return True
    return False


def _fact(slots: Dict[str, Any]) -> Dict[str, Any]:
    """What a graphic states: its number (scaled by its unit) and the words of its caption, to tell a repeat from a different fact."""
    words = set(re.findall(r"[a-z0-9]{3,}", " ".join(str(slots.get(k, "")) for k in ("label", "text", "title", "a_label", "b_label", "headline", "place")).lower()))
    return {"value": _scaled(slots.get("value"), slots.get("unit")), "words": words, "text": str(slots.get("text", "")).strip().lower()}


def _same_fact(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    if a["value"] is not None and b["value"] is not None:
        return abs(a["value"] - b["value"]) <= 1e-9 * max(1.0, abs(b["value"]))
    if a["text"] or b["text"]:
        return a["text"] == b["text"]
    union = a["words"] | b["words"]
    return bool(union) and len(a["words"] & b["words"]) / len(union) >= 0.6


def _significant(sentence: str) -> bool:
    return bool(_SIGNIFICANT.search(sentence))


_SMALL_TYPE_ON_FOOTAGE = {"name_bar"}


def _footage_backing(tpl: Dict[str, Any]) -> Dict[str, Any]:
    """The template as it is drawn over footage: a full-screen plate or dim would darken or hide the clip, so it gives way to a soft dark backing
    under the type only (gfx-core `shade`), which keeps small captions readable on a bright picture and leaves the rest of the frame untouched.
    A template with neither (a tag, a caption) is returned as it is."""
    if tpl.get("id") in _SMALL_TYPE_ON_FOOTAGE and not (tpl.get("plate") or tpl.get("dim")):
        # a name bar's second line is small and has no box of its own: a soft backing just behind the bar, nothing else on the frame
        x, y = next((it["at"] for it in tpl.get("items", []) if isinstance(it.get("at"), list) and len(it["at"]) == 2), [0.05, 0.7])
        return dict(tpl, shade={"at": [min(0.5, x + 0.14), y + 0.02], "rx": 0.30, "ry": 0.13, "a": 0.50})
    if not (tpl.get("plate") or tpl.get("dim")):
        return tpl
    at = next((it["at"] for it in tpl.get("items", []) if it.get("p") not in ("tag", "pill") and isinstance(it.get("at"), list) and len(it["at"]) == 2
               and all(isinstance(v, (int, float)) for v in it["at"])), [0.5, 0.5])
    at = [min(0.5, at[0] + 0.30) if at[0] < 0.3 else at[0], at[1]]      # a block set from the left edge (a quote) is backed where its text is
    plate = bool(tpl.get("plate"))                   # a plate template (a timeline, two numbers face to face) has more small type to carry
    out = {k: v for k, v in tpl.items() if k not in ("plate", "dim")}
    out["plate"] = False
    out["shade"] = {"at": list(at), "rx": 0.5 if plate else 0.44, "ry": 0.4 if plate else 0.34, "a": 0.52 if plate else 0.40}
    return out


def _chip_safe(tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A copy of the template that leaves the Doc Style title chip alone: its own top-left tag is dropped (the chip already names the topic) and a
    full-screen plate becomes a light dim, so the map, the photo cards and the chip stay visible under the graphic. None when nothing is left to draw."""
    keep = [it for it in tpl.get("items", []) if not _uses_top_left({"items": [it]})]
    if not keep:
        return None
    out = dict(tpl, items=keep)
    if out.get("plate"):
        out["plate"] = False
        out["dim"] = out.get("dim") or 0.4
    return out


def _required_slots_filled(t: Dict[str, Any], slots: Dict[str, Any]) -> bool:
    return all(slots.get(k) not in (None, "", []) for k, s in (t.get("slots") or {}).items() if s.get("required"))


# Where on the frame each graphic draws (a 3 x 3 grid: T/M/B rows, L/C/R columns). Two graphics may share the screen when their zones do not meet: a counter in the
# top-right corner and a number in the middle, a caption along the bottom and a title chip top-left. A graphic not listed, and any full-screen plate, takes the
# whole frame, so it is never drawn beside anything.
_ALL_ZONES = frozenset(r + c for r in "TMB" for c in "LCR")
ZONES: Dict[str, "frozenset[str]"] = {
    "end_question": frozenset({"MC"}),
    "typed_caption": frozenset({"BL", "BC"}), "counter_corner": frozenset({"TR"}), "yellow_tag": frozenset({"TL"}),
    "name_bar": frozenset({"ML", "BL"}), "place_lowerthird": frozenset({"BL"}), "tag_fact": frozenset({"MC"}),
    "big_number": frozenset({"MC"}), "gold_stat": frozenset({"MC"}), "year_wipe": frozenset({"MC"}), "three_rings": frozenset({"MC"}),
    "quote_boxed": frozenset({"MC"}), "quote_card": frozenset({"ML", "MC"}), "fact_card": frozenset({"ML", "MC"}), "record_badge": frozenset({"MC"}),
    "checklist_card": frozenset({"TR", "MR", "BR"}), "side_panel": frozenset({"TR", "MR", "BR"}), "lower_kicker": frozenset({"BL", "ML"}),
}


def zones_of(template: Dict[str, Any]) -> "frozenset[str]":
    if template.get("plate") or template.get("dim"):
        return ZONES.get(template.get("id"), _ALL_ZONES) if template.get("shade") else _ALL_ZONES
    return ZONES.get(template.get("id"), _ALL_ZONES)


COMPACT_ON_FOOTAGE = {"name_bar", "place_lowerthird", "lower_kicker", "counter_corner", "tag_headline", "ring_percent", "big_number", "gold_stat", "year_wipe", "dial_gauge"}   # little of the picture is covered
# ---- every other clip: a graphic made of the narration's own words ---------------------------------------------------------------------------
FOOTAGE_SHARE = 0.6          # about this share of the full-screen clips carry a graphic (the ones with a number, a year or a person already have theirs)
FILL_LOOKS = (                # (template, slots from a clause, longest clause in characters): cards and text layouts that read over a picture
    ("headline_wash", lambda c, hl: {"title": c.upper(), "sub": ""}, 34), ("subtitle_gold", lambda c, hl: {"text": c, "highlight": hl}, 56),
    ("lower_kicker", lambda c, hl: {"title": c.upper(), "kicker": "", "sub": ""}, 30), ("tag_headline", lambda c, hl: {"text": c.upper()}, 42),
    ("text_slam", lambda c, hl: {"text": c.upper()}, 22), ("text_typewriter", lambda c, hl: {"text": c.upper()}, 24), ("text_stamp", lambda c, hl: {"text": c.upper()}, 22),
    ("text_word_pop", lambda c, hl: {"text": c.upper()}, 22), ("text_glow", lambda c, hl: {"text": c.upper()}, 22), ("text_outline", lambda c, hl: {"text": c.upper()}, 22),
    ("text_box", lambda c, hl: {"text": c.upper()}, 22), ("text_sweep", lambda c, hl: {"text": c.upper()}, 22), ("text_split", lambda c, hl: {"text": c.upper()}, 22),
    ("text_underline", lambda c, hl: {"text": c.upper()}, 22), ("keyword_title", lambda c, hl: {"words": c.upper().split(), "accent": max(range(len(c.split())), key=lambda i: len(c.split()[i]))}, 26),
)
# cards built from SEVERAL consecutive clauses of the narration, each word as spoken: (template, how many clauses, longest clause in characters, slots)
CARD_LOOKS = (
    ("side_panel", 3, 30, lambda cs: {"title": cs[0].upper(), "bullets": [c[:1].upper() + c[1:] for c in cs[1:]]}),
    ("checklist_card", 3, 24, lambda cs: {"title": "AS WE GO", "items": [c[:1].upper() + c[1:] for c in cs]}),
    ("chapter_serif", 2, 30, lambda cs: {"kicker": cs[0].upper(), "title": cs[1].upper()}),
    ("quote_card", 1, 60, lambda cs: {"text": _wrap_quote(cs[0]), "by": ""}),
    ("headline_wash", 2, 30, lambda cs: {"title": cs[0].upper(), "sub": cs[1].upper()}),
)


def _wrap_quote(text: str, width: int = 26) -> str:
    out, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    out.append(cur)
    return "|".join(out)


_CLAUSE_LEAD = {"and", "but", "so", "then", "yet", "now", "also", "or", "because", "while", "when", "if", "which", "that", "who"}


def _clauses(words: Sequence[Tuple[str, float, float]]) -> List[Tuple[str, float, float]]:
    """The narration cut at its commas and stops: (clause as spoken, start, end). A clause is only ever used whole, with its own words."""
    out, cur = [], []
    for tok, a, b in words:
        cur.append((tok, a, b))
        if tok.rstrip("\"'”’)").endswith((",", ";", ":", ".", "!", "?")):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    res = []
    for c in out:
        toks = [t for t, _a, _b in c]
        while toks and toks[0].lower().strip(",.;:!?") in _CLAUSE_LEAD:
            toks.pop(0); c = c[1:]
        text = " ".join(toks).strip().rstrip(",;:.!?").strip()
        if text and c:
            res.append((text, c[0][1], c[-1][2]))
    return res


def _clause_score(text: str) -> float:
    n = len(text.split())
    sc = 0.0
    if 2 <= n <= 5:
        sc += 1.0
    if re.search(r"\d", text):
        sc += 1.0
    if re.search(r"(?i)\b(highest|largest|biggest|oldest|deepest|longest|first|only|last|most)\b", text):
        sc += 1.5
    if any(w[:1].isupper() for w in text.split()[1:]):
        sc += 2.0                                            # a named place or person
    return sc




def auto_events(words: Sequence[Tuple[str, float, float]], *, niche: str = "map", taken: Sequence[Tuple[float, float]] = (), total: Optional[float] = None,
                id_prefix: str = "auto", enabled: Optional[Sequence[str]] = None,
                resolve: Optional[Callable[[str], Optional[Tuple[float, float]]]] = None,
                stats: Sequence[Dict[str, Any]] = (), replaced: Optional[List[str]] = None, chips: Sequence[Tuple[float, float]] = (),
                footage: Sequence[Tuple[float, float]] = (), script: Optional[str] = None, report: Optional[List[Dict[str, Any]]] = None,
                hidden_under_footage: Sequence[Tuple[float, float]] = (), texts: Sequence[Tuple[float, float, str]] = (),
                narration_fill: bool = True) -> List[Dict[str, Any]]:
    """Graphics for what the narration states, chosen by score, within the pacing budget.

    For each sentence every rule in AUTO that reads something from it makes a candidate (its slots come only from the narration; a required slot left empty
    means no candidate). A candidate must clear the hard rules (nothing else on screen, spacing, the same fact or layout not just shown, the per-minute
    budget, and over footage no graphic that sits on the map); the best-scoring one is placed, or none: a sentence never gets a graphic just because it
    can. The score is the rule's weight (what the fact adds), plus variety (a layout not used recently, a different family from the last graphic), plus
    fit (a compact layout over footage), minus repetition.

    `taken` = windows of anything that is on screen when it says so (a graphic above footage, a picture that hides the map); `hidden_under_footage` = windows
    of map-layer graphics (a title chip, a caption, a counter): they are drawn UNDER full-screen footage, so where footage covers them they do not count. `stats` = the plan's plain stat events: one that shows the same number
    as the graphic about to be placed is replaced by it (its id goes to `replaced`), any other blocks. `chips` = the Doc Style title chips (they block only a
    graphic that draws its own tag in their corner). `footage` = windows of full-screen footage that covers every map layer (Hybrid cover_ui): a graphic whose
    time falls on one is drawn above it (event flag over_footage) with a soft backing instead of a plate. `report` collects why a graphic was not drawn."""
    lib = load_library()
    entries = [(tid, pat, fn) for tid, pat, fn in AUTO if tid in lib and (enabled is None or tid in enabled)
               and (niche in lib[tid].get("niches", []) or "any" in lib[tid].get("niches", []))]
    events: List[Dict[str, Any]] = []
    def win3(x):    # (from, to) or (from, to, zones): a window without zones takes the whole frame
        return (x[0], x[1], frozenset(x[2]) if len(x) > 2 and x[2] is not None else _ALL_ZONES)

    hidden = sorted(win3(x) for x in hidden_under_footage)   # map-layer windows: not visible where footage covers the map
    shown = sorted(win3(x) for x in taken)                   # always visible: what the caller lists, and the graphics this planner places
    cover = sorted(tuple(f) for f in footage)
    last_end = -1e9
    used: Dict[str, List[Dict[str, Any]]] = {}               # template id -> its earlier uses here: start, end, the fact it showed
    recent: List[str] = []                                   # template ids in the order placed
    group_last: Dict[str, float] = {}                        # rule group -> when its last graphic ended (text effects are rationed as a group)

    def _bag(text: str) -> "set[str]":
        return set(re.findall(r"[a-z0-9]{3,}", str(text).lower()))

    def why(reason: str, tid: str, at: float) -> None:      # `report`: one row per template the narration called for that was not drawn, and why
        if report is not None:
            report.append({"t": round(at, 1), "template": tid, "reason": reason})

    def visible_busy(w: Tuple[float, float]) -> List[Tuple[float, float]]:
        """Windows that really are on screen in w: a map-layer window loses the parts that footage covers."""
        out = list(shown)
        for x, y, zn in hidden:
            if not (w[0] < y + MIN_GAP_AFTER_S and x - MIN_GAP_AFTER_S < w[1]):
                continue
            cur = [(x, y)]
            for fs, fe in cover:
                nxt = []
                for cx, cy in cur:
                    if fe <= cx or fs >= cy:
                        nxt.append((cx, cy))
                    else:
                        if cx < fs:
                            nxt.append((cx, fs))
                        if fe < cy:
                            nxt.append((fe, cy))
                cur = nxt
            out += [(c[0], c[1], zn) for c in cur if c[1] - c[0] > 0.05]
        return out

    def consider(tid: str, pat: Optional[str], fn: Callable, si: int, text: str, raw: str, a: float, b: float) -> Optional[Dict[str, Any]]:
        t = lib[tid]
        if not re.search(pat or t.get("triggers") or "(?!)", text, re.I if pat is None else 0):
            return None
        if getattr(fn, "ctx", False):
            slots = fn(text, _Ctx(resolve, sents, si, raw, toks[si] if si < len(toks) else []))
        else:
            slots = fn(text, resolve) if fn is _route else fn(text)
        if not slots:
            why("not_enough_in_the_sentence", tid, a)
            return None
        slots = dict(slots)
        t_from, t_to = slots.pop("_t0", None), slots.pop("_t1", None)
        slots = {k: v for k, v in slots.items() if k in t.get("slots", {})}
        for k, spec in (t.get("slots") or {}).items():       # an optional text line the narration gave nothing for is blank, never the template's example
            if k not in slots and not spec.get("required") and spec.get("from") in ("sub", "label", "text") and isinstance(spec.get("default"), str):
                slots[k] = ""
        if not _required_slots_filled(t, slots):
            why("required_slot_empty", tid, a)
            return None                                    # cannot be drawn as it is: whatever is there stays
        hold = min(float(t.get("hold", 6)), max(3.0, (b - a) + 2.0))
        win = (a, a + hold)
        if t_from is not None:                             # an extractor that knows the very words (a quotation, a name, a number) times it to them
            t0 = max(a, t_from - 0.2)
            t1 = t_to if t_to is not None else t0 + hold
            win = (t0, min(t0 + 16.0, max(t1, t0 + MIN_VISIBLE_S)))

        if cover and not map_bound(t) and not any(f[0] <= win[0] < f[1] for f in cover):
            f = next((f for f in cover if win[0] < f[0] <= win[0] + FOOTAGE_PULL_S and f[1] - f[0] >= MIN_VISIBLE_S + 0.5), None)
            if f is not None:                              # the footage that follows the words is where a graphic reads best: it comes in with the clip
                start = f[0] + 0.4
                win = (start, min(start + (win[1] - win[0]), f[1] - 0.2))
        on_clip = any(win[0] < f[1] and f[0] < win[1] for f in cover)

        def stats_in(w):
            return [st for st in stats if st.get("id") not in (replaced or []) and w[0] < st["t_out"] + MIN_GAP_AFTER_S and st["t_in"] - MIN_GAP_AFTER_S < w[1]]

        over = stats_in(win)
        if over and all(stat_is_redundant(st, tid, slots) for st in over):
            # the plan already timed that number on the words that say it: the graphic takes its moment (and its caption), not the sentence start
            t0 = max(a, min(st["t_in"] for st in over) - 0.3)
            win = (t0, min(t0 + 8.0, max(max(st["t_out"] for st in over), t0 + 2.4)))
            over = stats_in(win)
            lab = str(over[0].get("sub") or "").strip() if len(over) == 1 else ""
            if lab and "label" in slots:
                slots["label"] = lab.upper()
        if any(not stat_is_redundant(st, tid, slots) for st in over):
            why("another_stat_on_screen", tid, a)
            return None                                    # a different stat is on screen: it stays and the graphic waits

        zones = zones_of(t)

        def clashes(w):      # something visible in that time AND in a part of the frame this graphic uses
            return [(x, y) for x, y, zn in visible_busy(w) if w[0] < y + MIN_GAP_AFTER_S and x - MIN_GAP_AFTER_S < w[1] and zn & zones]

        clash = clashes(win)
        if clash:
            # something already on screen is only just ending (a title or caption of the beat): the graphic comes in after it, if that is soon
            # enough for the words it belongs to and leaves it time to be read; anything that starts inside its window still blocks it
            start = max(y for _x, y in clash) + MIN_GAP_AFTER_S
            if any(x > win[0] for x, _y in clash) or start - a > LATE_START_S or win[1] - start < MIN_VISIBLE_S:
                why("something_else_on_screen", tid, a)
                return None
            win = (start, win[1])
            if clashes(win):
                why("something_else_on_screen", tid, a)
                return None
            over = stats_in(win)
            if any(not stat_is_redundant(st, tid, slots) for st in over):
                why("another_stat_on_screen", tid, a)
                return None
        if win[0] - last_end < (MIN_SPACING_FOOTAGE_S if on_clip else MIN_SPACING_S):
            why("spacing", tid, a)
            return None
        rule = RULES.get(tid, {})
        grp = rule.get("group")
        if grp and grp in group_last and win[0] - group_last[grp] < float(rule.get("group_gap_s", 75.0)):
            why("too_soon_for_another_text_effect", tid, a)
            return None
        if grp == "punchline":
            mine = _bag(" ".join(str(v) for v in slots.values()))
            for tf, tt, tx in texts:
                theirs = _bag(tx)
                if mine and theirs and tf - 20 < win[1] and win[0] < tt + 20 and len(mine & theirs) / len(mine | theirs) >= 0.5:
                    why("the_plan_already_says_it", tid, a)
                    return None
        fact = _fact(slots)
        earlier = used.get(tid, [])
        if any(_same_fact(fact, u["fact"]) and win[0] - u["end"] < NEAR_DUPLICATE_S for us in used.values() for u in us):
            why("same_fact_again", tid, a)
            return None                                    # the same fact again, in this template or another: essentially the same picture
        if earlier:
            if win[0] - earlier[-1]["end"] < SAME_TEMPLATE_GAP_S:
                why("same_layout_again", tid, a)
                return None                                # the same layout right after itself, even for another fact
            near = [u for u in earlier if win[0] - u["start"] < SAME_TEMPLATE_WINDOW_S]
            if near and (len(near) >= SAME_TEMPLATE_MAX or (tid not in _IDENTITY and not _significant(text))):
                why("same_layout_again", tid, a)
                return None                                # again soon only for a fact that stands out, and only so often
        if sum(1 for e in events if win[0] - 60 < e["t_in"] <= win[0]) >= (MAX_PER_MINUTE_FOOTAGE if on_clip else MAX_PER_MINUTE):
            why("per_minute_limit", tid, a)
            return None
        if total is not None and win[1] > total:
            win = (win[0], total)
            if win[1] - win[0] < 2.0:
                why("video_ends", tid, a)
                return None
        over_clip = any(win[0] < f[1] and f[0] < win[1] for f in cover)
        if over_clip and map_bound(t):
            why("map_hidden_under_footage", tid, a)
            return None                                    # a route or outline has nothing to sit on while footage covers the map
        tpl = without_example_text(_public(t), slots)
        if _uses_top_left(t) and any(win[0] < y and x < win[1] for x, y in chips):
            tpl = _chip_safe(tpl)
            if tpl is None:
                why("no_safe_layout_beside_the_title", tid, a)
                return None                                # no safe layout next to the title chip: nothing is added, the stat stays
        if tid == "end_question":                          # its one line has a fixed size: shrunk so the whole question fits the width of the frame (about 0.62 em per capital)
            n = max(1, len(str(slots.get("text", ""))))
            tpl = copy.deepcopy(tpl)
            for it in tpl.get("items", []):
                if it.get("text") == "{text}":
                    it["size"] = int(max(40, min(it.get("size", 96), 1700 / (0.62 * n))))
        if over_clip:
            tpl = _footage_backing(tpl)
        score = float(rule.get("weight", 4))
        score += sum(0.5 for k, s in (t.get("slots") or {}).items() if not s.get("required") and slots.get(k) not in (None, "", []))   # a fuller graphic says more
        last3 = recent[-3:]
        score += 2.0 if tid not in last3 else -2.0 * last3.count(tid)                  # a layout not used lately
        if recent and lib[recent[-1]].get("family") == t.get("family"):
            score -= 1.0                                                                  # not the same family twice running
        score -= 1.0 * sum(1 for u in earlier if win[0] - u["start"] < SAME_TEMPLATE_WINDOW_S)
        score -= 0.4 * len(earlier)                                                       # a layout used often in this video gives way to one not yet used
        if over_clip:
            score += 1.0 + (1.5 if tid in COMPACT_ON_FOOTAGE else -1.0 if (t.get("plate") or t.get("dim")) else 0.0)      # footage first: the map already carries its own layers
        elif cover and not map_bound(t):
            score -= 0.5                                                                  # on the map only when it is the better place for it
        return {"tid": tid, "slots": slots, "win": win, "tpl": tpl, "over_clip": over_clip, "over": over, "fact": fact, "score": round(score, 3)}

    words = display_words(words, script)
    sents = sentences(words)
    toks = _sentence_tokens(words)
    for si, (text, a, b) in enumerate(sents):
        raw = text
        text = _spoken_number(text)
        if a < FIRST_AT_S or a - last_end < MIN_SPACING_FOOTAGE_S:
            continue
        cands = [c for c in (consider(tid, pat, fn, si, text, raw, a, b) for tid, pat, fn in entries) if c]
        if not cands:
            continue
        best = max(cands, key=lambda c: c["score"])        # a tie keeps the rule listed first (the more specific one)
        for c in cands:
            if c is not best:
                why(f"a better layout was chosen ({best['tid']})", c["tid"], a)
        win, tid = best["win"], best["tid"]
        ev = {"id": f"{id_prefix}_{tid}_{len(events) + 1}", "type": "map_template", "template": best["tpl"], "slots": best["slots"], "t_in": round(win[0], 3), "t_out": round(win[1], 3)}
        if best["over_clip"]:
            ev["over_footage"] = True
        events.append(ev); shown.append((win[0], win[1], zones_of(best["tpl"]))); shown.sort(); last_end = win[1]
        used.setdefault(tid, []).append({"start": win[0], "end": win[1], "fact": best["fact"]})
        recent.append(tid)
        if RULES.get(tid, {}).get("group"):
            group_last[RULES[tid]["group"]] = win[1]
        if replaced is not None:
            replaced.extend(st["id"] for st in best["over"])
    # footage first: about half of the full-screen clips get a graphic from their own narration (the clips that already have one count)
    # narration_fill=False (Normal Video: its whole video is one 'footage' window) keeps the planner as it was: no fill cards, no dates recap
    clauses = _clauses(words) if (cover and narration_fill) else []
    seen_text: "set[str]" = set()
    taken0 = [win3(x) for x in taken]
    done_clips = 0
    uses: Dict[str, int] = collections.Counter(e["template"]["id"] for e in events)
    eligible = [f for f in cover if f[1] - f[0] >= 3.0]
    for idx, (f0, f1) in enumerate(eligible):
        have = any(e.get("over_footage") and e["t_in"] < f1 and f0 < e["t_out"] for e in events) or any(w[0] < f1 and f0 < w[1] for w in taken0)
        if have:
            done_clips += 1
            continue
        if done_clips >= FOOTAGE_SHARE * (idx + 1):
            continue
        cands = [(c, t0, t1) for c, t0, t1 in clauses if f0 - 0.6 <= t0 <= f1 - 2.0 and 2 <= len(c.split()) <= 8 and c.lower() not in seen_text]
        cands.sort(key=lambda x: (-_clause_score(x[0]), x[1]))
        placed = False
        order = sorted([("card", k) for k in range(len(CARD_LOOKS))] + [("text", k) for k in range(len(FILL_LOOKS))],
                       key=lambda x: (uses.get((CARD_LOOKS if x[0] == "card" else FILL_LOOKS)[x[1]][0], 0) + (0 if x[0] == "card" else 1), x[0] != "card", x[1]))
        for c, t0, t1 in cands:
            mine = _bag(c)
            if any(tf - 20 < t1 and t0 < tt + 20 and mine and _bag(tx) and len(mine & _bag(tx)) / len(mine | _bag(tx)) >= 0.5 for tf, tt, tx in texts):
                why("the_plan_already_says_it", "footage_fill", t0)
                continue
            hl = max(c.split(), key=len).strip(",.;:!?")
            for kind, k in order:
                if kind == "card":
                    tid, need, limit, mk = CARD_LOOKS[k]
                    run = [x for x in clauses if x[1] >= t0 - 0.01][:need]
                    if len(run) < need or run[-1][2] - t0 > 14.0 or any(len(r[0]) > limit or not 1 <= len(r[0].split()) <= 8 for r in run) or any(r[0].lower() in seen_text for r in run):
                        continue
                    make, texts_used = (lambda _c, _h, mk=mk, run=run: mk([r[0] for r in run])), [r[0] for r in run]
                else:
                    tid, make, limit = FILL_LOOKS[k]
                    texts_used = [c]
                    if len(c) > limit:
                        continue
                if tid not in lib or (enabled is not None and tid not in enabled):
                    continue
                t = lib[tid]
                start = max(f0 + 0.3, t0 - 0.2)
                win = (start, min(f1 + 1.0 + (3.0 if kind == "card" else 0.0), start + min(float(t.get("hold", 4)), 7.0 if kind == "card" else 4.5)))      # may run on into the next clip: the graphic stays above the dissolve
                if win[1] - win[0] < 2.4 or (total is not None and win[1] > total):
                    continue
                zn = zones_of(t)
                if any(w[0] < win[1] + MIN_GAP_AFTER_S and win[0] - MIN_GAP_AFTER_S < w[1] and (len(w) < 3 or w[2] & zn) for w in visible_busy(win)):
                    why("something_else_on_screen", tid, t0)
                    continue
                slots = make(c, hl)
                if not _required_slots_filled(t, slots):
                    continue
                tpl = _footage_backing(without_example_text(_public(t), slots))
                ev = {"id": f"{id_prefix}_{tid}_{len(events) + 1}", "type": "map_template", "template": tpl, "slots": slots, "t_in": round(win[0], 3), "t_out": round(win[1], 3), "over_footage": True}
                events.append(ev); shown.append((win[0], win[1], zones_of(tpl))); shown.sort()
                uses[tid] = uses.get(tid, 0) + 1; seen_text.update(x.lower() for x in texts_used); done_clips += 1; placed = True
                break
            if placed:
                break
    # a recap of every date the narration states, as one timeline (its own words per date), shown right after the last of them is spoken
    dated, seen_year = [], set()
    for si, (stext, sa, sb) in enumerate(sents):
        ms = list(re.finditer(r"\b(1[0-9]{3}|20[0-3][0-9])(s?)\b", stext))
        if len(ms) == 1 and ms[0].group(0) not in seen_year:
            ev_text = X._event_text(stext, ms[0])
            if ev_text:
                seen_year.add(ms[0].group(0))
                dated.append((int(ms[0].group(1)), ms[0].group(0).upper(), ev_text, sa, sb))
    dated.sort()
    if narration_fill and len(dated) >= 4 and (enabled is None or "timeline_strip" in enabled) and "timeline_strip" in lib:
        rows = dated[:6]
        t = lib["timeline_strip"]
        slots = {"title": "THE DATES", "rows": [{"label": lab, "text": tx} for _y, lab, tx, _a, _b in rows], "dur": 6.0}
        for delay in (0.6, 4.0, 8.0, 13.0, 20.0, 30.0, 45.0):          # right after the last date is spoken, or the first time after that the screen is free
            start = max(r[4] for r in rows) + delay
            win = (start, start + 7.0)
            if total is not None and win[1] > total:
                break
            on_clip = any(win[0] < f[1] and f[0] < win[1] for f in cover)
            tpl = without_example_text(_footage_backing(_public(t)) if on_clip else _public(t), slots)
            if any(w[0] < win[1] + MIN_GAP_AFTER_S and win[0] - MIN_GAP_AFTER_S < w[1] for w in visible_busy(win)):
                continue
            ev = {"id": f"{id_prefix}_timeline_strip_{len(events) + 1}", "type": "map_template", "template": tpl, "slots": slots, "t_in": round(win[0], 3), "t_out": round(win[1], 3)}
            if on_clip:
                ev["over_footage"] = True
            events.append(ev); shown.append((win[0], win[1], zones_of(tpl)))
            break
    events.sort(key=lambda e: (e["t_in"], e["id"]))
    return events


def catalog_text(niche: Optional[str] = None, footage: bool = False) -> str:
    """The template list a script writer (or an AI prompt) can pick from: id [family] reads the columns it uses (* = required), then the
    extra slots it takes in params {"slots": {...}} (also * = required), then what it is for. footage=True marks each graphic as `[map only]` (it sits on the
    map, so it cannot go under a footage beat) or `[map or footage]`."""
    lines = []
    for t in load_library().values():
        if niche and niche not in t.get("niches", []) and "any" not in t.get("niches", []):
            continue
        sl = (t.get("slots") or {}).values()
        names = list((t.get("slots") or {}).items())
        cols = ", ".join(f"{s['from']}{'*' if s.get('required') else ''}" for _n, s in names if s.get("from"))
        extra = ", ".join(f"{n}{'*' if s.get('required') else ''}" for n, s in names if not s.get("from"))
        mark = (" [map only]" if map_bound(t) else " [needs its own picture]" if needs_picture(t) else " [map or footage]") if footage else ""
        lines.append(f"{t['id']} [{t['family']}] reads {cols or 'nothing'}" + (f"; params.slots {extra}" if extra else "") + f": {t['use']}{mark}")
    return "\n".join(lines)


# ---- Doc Style: the News Doc look for a map video's own tags, titles and numbers ------------------------------------------------------------
_PLAIN_NUMBER = re.compile(r"^[#0,.\s]*$")
_UNIT_FORMAT = re.compile(r"^[#0,]+\s+([A-Za-z][A-Za-z²³/° ]{0,23})$")      # "#,##0 KM", "0 MILLION KM²": a whole number and a unit in words


def _template_event(template_id: str, ev: Dict[str, Any], slots: Dict[str, Any]) -> Dict[str, Any]:
    out = {"id": ev["id"], "type": "map_template", "template": _public(get(template_id)), "slots": slots, "t_in": ev["t_in"], "t_out": ev["t_out"]}
    if ev.get("over_footage") is True:      # the author asked for this title or caption to stay on screen over full-screen footage
        out["over_footage"] = True
    if template_id == "counter_corner":     # the count-up must finish well inside the time the stat is on screen (a 1.4 s stat counted for 2 s ended at 1,643 of 9,000)
        out["template"] = copy.deepcopy(out["template"])
        for it in out["template"]["items"]:
            if it.get("p") == "countercard":
                it["count_s"] = round(max(0.4, min(2.0, (float(ev["t_out"]) - float(ev["t_in"])) * 0.3)), 2)
    return out


def apply_doc_style(events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Redraw a map video's title chips, captions and whole-number counters in the News Doc look (the gfx-core "news" templates).
    Same ids, same times; only what has a faithful News Doc twin is changed:
      hud_title -> yellow_tag (label, and the subtitle after a dot)      caption -> typed_caption
      stat counting 0 -> a whole number (its sub-line names it) -> counter_corner; a whole number with a unit ("#,##0 KM") -> the same compact card, the unit on its small line
    Everything else (markers, lines, fills, photo cards, footage, a stat that counts from another value or has a unit format) is left as it is."""
    out: List[Dict[str, Any]] = []
    for ev in events:
        t = ev.get("type")
        try:
            if t == "hud_title" and ev.get("label"):
                text = ev["label"] + (f" · {ev['sub']}" if ev.get("sub") else "")
                out.append(_template_event("yellow_tag", ev, {"text": str(text).upper()}))
                continue
            if t == "caption" and ev.get("text"):
                out.append(_template_event("typed_caption", ev, {"text": str(ev["text"]).replace("\n", " ")}))
                continue
            v, f = ev.get("value_to"), ev.get("value_from")
            unit = _UNIT_FORMAT.match(str(ev.get("format", "")).strip())
            if (t == "stat" and unit and isinstance(v, (int, float)) and float(v).is_integer() and v >= 0 and (f in (None, 0) or f == v) and ev.get("sub")):
                # a number with its unit ("#,##0 KM"): the native card is large; the compact corner card carries the unit on its small line
                anchor = ev.get("anchor") if ev.get("anchor") in ("tr", "tl", "br", "bl") else "tr"
                out.append(_template_event("counter_corner", ev, {"value": int(v), "label": str(ev["sub"]).upper(), "sub": unit.group(1).strip().upper(), "anchor": anchor}))
                continue
            if (t == "stat" and isinstance(v, (int, float)) and float(v).is_integer() and v >= 0 and (f in (None, 0) or f == v)
                    and _PLAIN_NUMBER.match(str(ev.get("format", "")).strip()) and ev.get("sub")):
                anchor = ev.get("anchor") if ev.get("anchor") in ("tr", "tl", "br", "bl") else "tr"
                out.append(_template_event("counter_corner", ev, {"value": int(v), "label": str(ev["sub"]).upper(), "anchor": anchor}))
                continue
        except ValueError:
            pass            # the library has no such template: the native layer stays
        out.append(ev)
    return out


# ---- sound: the effect each graphic makes when it appears (the pakMap sound vocabulary, pakmap/sounds.py) ------------------------------------------
PRIM_SOUND = {
    "tag": "ui_click", "pill": "ui_click", "ctxtag": "ui_click", "lowerthird": "ui_click", "lowerkick": "ui_click", "nametag": "ui_click",
    "hbars": "counter_ticks", "columns": "bubble_pluck", "trend": "draw_zap", "number": "counter_ticks", "statbig": "counter_ticks", "countercard": "counter_ticks",
    "ring": "counter_ticks", "versus": "deep_thud", "ranklist": "ui_click", "fact": "deep_thud", "region_label": "bubble_pluck", "chapter": "deep_thud",
    "chaptercard": "deep_thud", "kwtitle": "deep_thud", "quote": "paper_slide", "boxquote": "paper_slide", "photocards": "ui_click", "yearwipe": "deep_thud",
    "checklist": "ui_click", "panel": "paper_slide", "glitch": "fast_whoosh", "polaroids": "paper_slide", "dossier": "paper_slide", "framed": "paper_slide",
    "timeline": "draw_zap", "threerings": "marker_pop", "placepulse": "marker_pop", "valuechip": "marker_pop", "cardsrow": "ui_click", "recordcard": "ui_click",
    "badge": "deep_thud", "beforeafter": "ui_click", "route": "directional_whoosh", "flowarrows": "directional_whoosh", "ruler": "draw_zap", "chokepoint": "marker_pop",
    "heat": "bubble_pluck", "spotlight": "draw_zap", "yearclock": "clock_ticking", "locationcard": "marker_pop", "photoleader": "ui_click", "dial": "counter_ticks",
    "bubbles": "bubble_pluck", "tally": "counter_ticks", "numberline": "draw_zap", "stackbars": "bubble_pluck", "barrace": "counter_ticks", "slider": "paper_slide",
    "scoreboard": "deep_thud", "headline": "deep_thud", "subtitle": "paper_slide", "scalebar": "draw_zap", "typedcaption": "ui_click",
}
TEXT_STYLE_SOUND = {"slam": "deep_thud", "stamp": "deep_thud", "typewriter": "ui_click", "word_pop": "marker_pop", "glow": "ui_click", "stack": "paper_slide",
                    "box": "ui_click", "outline": "ui_click", "split": "fast_whoosh", "sweep": "fast_whoosh", "underline": "draw_zap"}


def sfx_cues(ev: Dict[str, Any]) -> List[Tuple[float, str, str]]:
    """[(seconds after the event starts, sound id, why)] for a map_template event: the template's own "sfx" list when it has one
    ([{"at": 0.3, "sound": "deep_thud"}], [] = silent), else one effect per kind of piece it draws, at the moment that piece comes in
    (at most two: the title thud and one more). The planner's restraint rules (spacing, no repeats, ducking under narration) still apply."""
    t = ev.get("template") or {}
    if "sfx" in t:
        return [(float(c.get("at", 0.2)), str(c["sound"]), f"graphic {t.get('id')}") for c in t["sfx"] or []]
    out: List[Tuple[float, str, str]] = []
    for it in t.get("items", []):
        sound = TEXT_STYLE_SOUND.get(it.get("style", "")) if it.get("p") == "text" else PRIM_SOUND.get(it.get("p"))
        if not sound or any(s == sound for _a, s, _w in out):
            continue
        at = it.get("in", 0.2)
        at = float(at) if isinstance(at, (int, float)) else 0.3
        out.append((max(0.0, at), sound, f"graphic {t.get('id')}: {it.get('p')}"))
    return out[:2]
