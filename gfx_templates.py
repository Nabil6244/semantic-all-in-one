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
    ev: Dict[str, Any] = {"id": event_id, "type": "map_template", "template": _public(t), "slots": slots, "t_in": round(t_in, 3), "t_out": round(end, 3)}
    cues = find_cues(t, words, t_in, end) if words else {}
    if cues:
        ev["cues"] = cues
    if follow:
        ev["follow"] = follow
    return ev, float(t.get("hold", 6))


def _public(t: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in t.items() if not k.startswith("_") and k not in ("triggers", "use", "tags")}


# ---- auto planner: one stated number -> the template that shows it -------------------------------------------------------------------------
_SCALE = {"million": ("M", "MILLION"), "billion": ("B", "BILLION"), "trillion": ("T", "TRILLION"), "thousand": ("K", "THOUSAND")}
_UNITS = {r"square kilomet(?:re|er)s?": "KM²", r"sq\.? ?km": "KM²", r"km²": "KM²", r"kilomet(?:re|er)s?": "KM", r"miles": "MILES", r"years": "YEARS", r"metres|meters": "M"}
_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"


def _before(sentence: str, start: int, n: int = 4) -> str:
    words = re.findall(r"[A-Za-z][\w'-]*", sentence[:start])
    stop = {"a", "an", "the", "of", "is", "are", "was", "were", "has", "have", "about", "around", "over", "than", "and", "in", "to", "with", "for", "that",
            "it", "its", "this", "they", "covers", "spans", "measures", "reaches", "holds", "makes", "up", "nearly", "almost", "roughly", "just", "only"}
    while words and words[-1].lower() in stop:
        words.pop()
    return " ".join(words[-n:]).upper()


_ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}


def _spoken_number(sentence: str) -> str:
    """"sixty percent" / "forty five percent" -> "60 percent" / "45 percent" (a narration written in words; a transcript usually has digits)."""
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
    scale = "|".join(_SCALE)
    unit_pat = "|".join(_UNITS)
    m = re.search(_NUM + rf"\s*(?:({scale})\b)?\s*(?:({unit_pat}))?", sentence, re.I)
    if not m:
        return None
    raw, sc, un = m.group(1), (m.group(2) or "").lower(), m.group(3)
    value = float(raw.replace(",", ""))
    if not sc and not un and value < 1000:
        return None                                            # a bare small number is not a headline
    if not sc and not un and 1900 <= value <= 2100 and "," not in raw:
        return None                                            # a year
    unit = _SCALE[sc][1] if sc else ""
    if un:
        u = next(v for pat, v in _UNITS.items() if re.fullmatch(pat, un, re.I))
        unit = f"{unit} {u}".strip()
    default = "TOTAL AREA" if "KM²" in unit else "KEY NUMBER"
    return {"value": int(value) if value.is_integer() else value, "unit": unit, "label": _before(sentence, m.start()) or default, "sub": ""}


_TIMES = {"twice": 2, "two times": 2, "three times": 3, "four times": 4, "five times": 5, "six times": 6, "ten times": 10}
_TIMES_RE = re.compile(r"\b(twice|two times|three times|four times|five times|six times|ten times)\s+(?:as\s+)?(?:large|big|bigger|larger|long|longer|wide|wider|heavy|heavier|tall|taller|many|much|more|populous)\b(?:\s+as|\s+than)?\s+(?:the\s+)?([A-Z][\w'.-]*(?:\s+(?:of\s+)?[A-Z][\w'.-]*){0,3})")
_YEAR_RE = re.compile(r"\b(?i:in|since|by|during|until|before|after|back in|from)\s+(1[0-9]{3}|20[0-3][0-9])\b")
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
    return {"text": m.group(1), "sub": ""} if m else None


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
AUTO = [("ring_percent", None, _percent), ("big_number", None, _big), ("big_number", _TIMES_RE.pattern, _times), ("year_wipe", _YEAR_RE.pattern, _year), ("route_travel", _FROM_TO_RE.pattern, _route)]
EXTRACTORS = {"ring_percent": _percent, "big_number": _big, "year_wipe": _year, "route_travel": _route}
MIN_SPACING_S = 6.0       # clear time between one auto template ending and the next starting
MIN_GAP_AFTER_S = 1.0     # after another graphic on screen
REPEAT_S = 45.0           # the same template is not used twice inside this
MAX_PER_MINUTE = 3
FIRST_AT_S = 4.0          # nothing in the opening seconds


def sentences(words: Sequence[Tuple[str, float, float]]) -> List[Tuple[str, float, float]]:
    out, cur, t0 = [], [], None
    for tok, a, b in words:
        if t0 is None:
            t0 = a
        cur.append(tok)
        if re.search(r"[.!?]$", tok):
            out.append((" ".join(cur), t0, b)); cur, t0 = [], None
    if cur:
        out.append((" ".join(cur), t0 if t0 is not None else 0.0, words[-1][2]))
    return out


def auto_events(words: Sequence[Tuple[str, float, float]], *, niche: str = "map", taken: Sequence[Tuple[float, float]] = (), total: Optional[float] = None,
                id_prefix: str = "auto", enabled: Optional[Sequence[str]] = None,
                resolve: Optional[Callable[[str], Optional[Tuple[float, float]]]] = None) -> List[Dict[str, Any]]:
    """Template events for what the narration states, within the pacing budget: a share ("60 percent"), a size ("9,984,670 square kilometres"),
    a comparison ("twice as large as France"), a year ("in 1947") and, when `resolve` (place name -> (lon, lat)) is given, a journey
    ("from Vancouver to Halifax"). `taken` = windows another graphic or footage holds."""
    lib = load_library()
    entries = [(tid, pat, fn) for tid, pat, fn in AUTO if tid in lib and (enabled is None or tid in enabled)
               and (niche in lib[tid].get("niches", []) or "any" in lib[tid].get("niches", []))]
    events: List[Dict[str, Any]] = []
    busy = sorted(tuple(x) for x in taken)
    last_end, used_at = -1e9, {}
    for text, a, b in sentences(words):
        text = _spoken_number(text)
        if a < FIRST_AT_S or a - last_end < MIN_SPACING_S:
            continue
        for tid, pat, fn in entries:
            t = lib[tid]
            if not re.search(pat or t.get("triggers") or "(?!)", text, re.I if pat is None else 0):
                continue
            slots = fn(text, resolve) if fn is _route else fn(text)
            if not slots:
                continue
            if a - used_at.get(tid, -1e9) < REPEAT_S:
                continue
            hold = min(float(t.get("hold", 6)), max(3.0, (b - a) + 2.0))
            win = (a, a + hold)
            if any(win[0] < y + MIN_GAP_AFTER_S and x - MIN_GAP_AFTER_S < win[1] for x, y in busy):
                continue
            if sum(1 for e in events if a - 60 < e["t_in"] <= a) >= MAX_PER_MINUTE:
                continue
            slots = {k: v for k, v in slots.items() if k in t.get("slots", {})}
            if total is not None and win[1] > total:
                win = (a, total)
                if win[1] - win[0] < 2.0:
                    continue
            ev = {"id": f"{id_prefix}_{tid}_{len(events) + 1}", "type": "map_template", "template": _public(t), "slots": slots, "t_in": round(win[0], 3), "t_out": round(win[1], 3)}
            events.append(ev); busy.append(win); busy.sort(); last_end = win[1]; used_at[tid] = a
            break
    return events


def catalog_text(niche: Optional[str] = None) -> str:
    """The template list a script writer (or an AI prompt) can pick from: id [family] reads the columns it uses (* = required), then the
    extra slots it takes in params {"slots": {...}} (also * = required), then what it is for."""
    lines = []
    for t in load_library().values():
        if niche and niche not in t.get("niches", []) and "any" not in t.get("niches", []):
            continue
        sl = (t.get("slots") or {}).values()
        names = list((t.get("slots") or {}).items())
        cols = ", ".join(f"{s['from']}{'*' if s.get('required') else ''}" for _n, s in names if s.get("from"))
        extra = ", ".join(f"{n}{'*' if s.get('required') else ''}" for n, s in names if not s.get("from"))
        lines.append(f"{t['id']} [{t['family']}] reads {cols or 'nothing'}" + (f"; params.slots {extra}" if extra else "") + f": {t['use']}")
    return "\n".join(lines)


# ---- Doc Style: the News Doc look for a map video's own tags, titles and numbers ------------------------------------------------------------
_PLAIN_NUMBER = re.compile(r"^[#0,.\s]*$")


def _template_event(template_id: str, ev: Dict[str, Any], slots: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": ev["id"], "type": "map_template", "template": _public(get(template_id)), "slots": slots, "t_in": ev["t_in"], "t_out": ev["t_out"]}


def apply_doc_style(events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Redraw a map video's title chips, captions and whole-number counters in the News Doc look (the gfx-core "news" templates).
    Same ids, same times; only what has a faithful News Doc twin is changed:
      hud_title -> yellow_tag (label, and the subtitle after a dot)      caption -> typed_caption
      stat counting 0 -> a whole number (its sub-line names it) -> counter_corner
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
    "scoreboard": "deep_thud",
}
TEXT_STYLE_SOUND = {"slam": "deep_thud", "stamp": "deep_thud", "typewriter": "ui_click", "word_pop": "marker_pop", "glow": "ui_click", "stack": "paper_slide"}


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
