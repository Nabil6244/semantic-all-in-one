"""Scenes CSV for Health Cinema: one row per narration sentence -> the same scene dicts the scenes JSON gives ({text, start, end, sources?, footage?, chapter?}).

Columns (header names are case-insensitive; `,` `;` or tab separated; Excel/Sheets exports with a BOM are fine):
  text (required; also: narration, sentence, script)   start, end (optional, seconds or m:ss; all rows or none)   chapter   footage
  source_title, source_citation, source_url, source_year, source_population, source_context   several sources in one row are separated by ` | `, lined up by position.
Visual direction columns (optional; when any row fills one, the app plans the visuals from the CSV itself and does NOT ask Gemini to plan them):
  visual   what the scene shows: auto (default) | footage | 3d | text | chapter | counter | bar | timeline | flow | youtube
  organ    the body part or region the scene is about (brain, eye, heart, lungs, liver, pancreas, stomach, intestines, knee, hip, shoulder, spine ...):
           picks the 3D model when `visual` is 3d, and is used to check that footage really shows that part
  shot     3D camera move: orbit | zoom | peel | isolate; or a condition: fatty | inflamed (the organ changes colour as it develops). Optional; default chosen from the narration
  footage  stock search for this scene (3 to 6 words);  footage_alt  other searches tried in order if the first finds nothing, separated by ` | `
  source   where footage comes from: stock (default) | youtube | flow
  visual=body  one beat of a continuous 3D body-map shot (consecutive body rows are ONE scene; the camera travels between their regions):
           body_region (an anchor of the body: body, head, neck, chest, heart, abdomen, pelvis, forearm_l/r, upper_arm_l/r, hand_l/r, thigh_l/r, shin_l/r, foot_l/r, shoulder_l ...)
           body_scale whole|region|close   body_focus body|skin|vessels|organ   body_effect none|skin_layers|spread   body_label (text pinned to the region)
           card_type none|lesion|microscopic|mechanism|anatomy|treatment|test   card_ref (id of an illustration in the library)   card_prompt (what to generate when card_ref is new)   card_at (seconds into the beat)
  Cards (from numbers and words IN the narration only): visual=stat with stat (the number as spoken), stat_unit (short: %, seconds), stat_label, stat_kicker, stat_source;
  visual=timeline with events (`when: what happens | when: what happens`); visual=chapter with card_title and card_kicker
  visual=checklist / steps with items (`item | item | item`, each shown as it is spoken) and an optional card_title;
  visual=compare with dont (`item | item`) and do (`item | item`) and an optional card_title
  On a footage, 3d or auto row: overlay stat|label|pulse puts a graphic over the picture (stat: the stat columns; label: overlay_text; pulse: a heart-rate line).
  On a 3d row, card_type / card_ref / card_prompt / card_at pin an illustration card to the organ, as on a body beat.
Paper-cutout puppet columns (optional, used only when the Puppet switch is on in the app; blank = the planner decides; a bad value is a warning, never an error):
  character_action  what the character does in this scene: walk | run | stand_idle | look_around | point | turn | pick_up | put_down | wave | stop, or a phrase like
                    walk_in_from_left, stand_and_look, pick_up_box (the verb is understood, left/right sets the direction); `none` keeps this scene plain
  character         which character (a name from the cast; blank = Auto)
Without start/end the rows are aligned to the voiceover's own word times (`align_to_words`), so the timings are the real ones, not estimates.
Nothing here invents text, numbers or sources: it only reads and validates what the file holds.
"""
from __future__ import annotations

import csv
import difflib
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ALIASES = {"text": ("text", "narration", "sentence", "script"), "start": ("start", "start_s", "start_time"), "end": ("end", "end_s", "end_time"),
           "chapter": ("chapter", "section"), "footage": ("footage", "footage_query", "clip"), "visual": ("visual", "scene_type", "kind"),
           "organ": ("organ", "anatomy", "body_part", "region"), "shot": ("shot", "camera"),
           "visual_subject": ("visual_subject", "subject", "visual_focus"), "visual_intent": ("visual_intent", "intent"),
           "biological_process": ("biological_process", "process", "mechanism"), "visual_action": ("visual_action", "action", "on_screen_action"), "footage_alt": ("footage_alt", "alt_footage", "footage_fallback"),
           "source": ("source", "footage_source", "asset_source"),
           "stat": ("stat", "number", "stat_value"), "stat_unit": ("stat_unit", "unit"), "stat_label": ("stat_label", "label"), "stat_kicker": ("stat_kicker", "kicker"), "stat_source": ("stat_source",),
           "events": ("events", "timeline_events"), "card_title": ("card_title", "title"), "card_kicker": ("card_kicker",),
           "body_region": ("body_region",), "body_scale": ("body_scale",), "body_focus": ("body_focus",), "body_effect": ("body_effect",), "body_label": ("body_label",),
           "items": ("items", "list_items"), "do": ("do", "do_items"), "dont": ("dont", "don't", "dont_items"), "overlay": ("overlay",), "overlay_text": ("overlay_text",),
           "card_type": ("card_type",), "card_ref": ("card_ref", "illustration"), "card_prompt": ("card_prompt",), "card_at": ("card_at",),
           "character_action": ("character_action", "puppet_action", "char_action"), "character": ("character", "puppet", "puppet_character"), "character_ground": ("character_ground", "ground", "ground_y")}
VISUALS = ("auto", "footage", "3d", "text", "chapter", "counter", "bar", "timeline", "stat", "flow", "youtube", "body", "checklist", "steps", "compare")
OVERLAYS = ("none", "stat", "label", "pulse")
SHOTS = ("orbit", "zoom", "peel", "cutaway", "isolate", "fatty", "inflamed")
SOURCES = ("stock", "youtube", "flow")
INTENT_COLUMNS = ("visual_subject", "visual_intent", "biological_process", "visual_action")      # what the viewer must see: the organ alone is not the subject
HINT_COLUMNS = ("visual", "organ", "shot", "visual_subject", "biological_process", "footage", "footage_alt", "source", "stat", "events", "card_title", "body_region", "items", "do", "dont", "overlay")
SOURCE_FIELDS = ("title", "citation", "url", "year", "population", "context")
MIN_MATCH = 0.5      # below this share of script words found in the voiceover, the CSV is not this narration
WARN_MATCH = 0.8
_TOK = re.compile(r"[a-z0-9%']+")


def _tokens(t: str) -> List[str]:
    return _TOK.findall(t.lower())


def parse_time(raw: str, where: str) -> float:
    """'12.5', '1:02', '1:02.5' or '0:01:02.5' -> seconds."""
    s = (raw or "").strip()
    try:
        parts = [float(p) for p in s.split(":")]
    except ValueError:
        raise ValueError(f"{where}: '{raw}' is not a time (use seconds like 12.5 or minutes:seconds like 1:02)") from None
    if not 1 <= len(parts) <= 3 or any(p < 0 for p in parts):
        raise ValueError(f"{where}: '{raw}' is not a time (use seconds like 12.5 or minutes:seconds like 1:02)")
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def _split(cell: str) -> List[str]:
    return [p.strip() for p in (cell or "").split("|")]


def _sources(row: Dict[str, str], where: str) -> List[dict]:
    cols = {f: _split(row.get(f"source_{f}", "")) for f in SOURCE_FIELDS}
    n = max((len(v) for v in cols.values() if any(v)), default=0)
    out: List[dict] = []
    for i in range(n):
        src: Dict[str, Any] = {}
        for f in SOURCE_FIELDS:
            v = cols[f][i] if i < len(cols[f]) else ""
            if not v:
                continue
            if f == "year":
                if not re.fullmatch(r"\d{4}", v):
                    raise ValueError(f"{where}: source_year '{v}' must be a 4-digit year")
                src[f] = int(v)
            else:
                src[f] = v
        if src.get("title") or src.get("citation") or src.get("url"):
            out.append(src)
        elif src:
            raise ValueError(f"{where}: source {i + 1} has details but no title, citation or url")
    return out


def _puppet_cells(row: Dict[str, str], sc: Dict[str, Any], where: str, notes: Optional[List[str]]) -> None:
    """Optional puppet columns -> sc['character_action'] (a known action, or 'none'), sc['character_direction'] and sc['character']. Anything unknown is
    dropped with a note: a bad cell here must never stop a CSV that otherwise works."""
    raw_a, raw_c = (row.get("character_action") or "").strip(), (row.get("character") or "").strip()
    raw_g = (row.get("character_ground") or "").strip()
    if raw_g:
        try:
            g = float(raw_g.rstrip("%")) / (100.0 if raw_g.endswith("%") or float(raw_g.rstrip("%")) > 1 else 1.0)
            if 0.5 <= g <= 0.97:
                sc["character_ground"] = g
            elif notes is not None:
                notes.append(f"{where}: character_ground {raw_g!r} must be between 50% and 97% of the picture height, ignored")
        except ValueError:
            if notes is not None:
                notes.append(f"{where}: character_ground {raw_g!r} is not a number, ignored")
    if not (raw_a or raw_c):
        return
    from . import puppet_plan
    if raw_a:
        action, direction, warn = puppet_plan.parse_action(raw_a)
        if warn and notes is not None:
            notes.append(f"{where}: {warn}")
        if action:
            sc["character_action"] = action
            if direction:
                sc["character_direction"] = direction
    if raw_c:
        name, warn = puppet_plan.parse_character(raw_c)
        if warn and notes is not None:
            notes.append(f"{where}: {warn}")
        if name:
            sc["character"] = name


def _header_map(fields: Sequence[str]) -> Dict[str, str]:
    norm = {re.sub(r"[\s\-]+", "_", (f or "").strip().lower()): f for f in fields}
    out: Dict[str, str] = {}
    for key, names in ALIASES.items():
        for n in names:
            if n in norm:
                out[key] = norm[n]
                break
    for f in SOURCE_FIELDS:
        if f"source_{f}" in norm:
            out[f"source_{f}"] = norm[f"source_{f}"]
    return out


def parse_csv_text(content: str, notes: Optional[List[str]] = None) -> List[dict]:
    """Rows -> [{text, start?, end?, chapter?, footage?, sources?}]. `start`/`end` are present on every row or on none. Raises ValueError naming the row.
    A row with more fields than the header almost always has an unquoted comma inside its text (an LLM forgot the quotes): the extra pieces are joined back
    into the text and the repair is appended to `notes`."""
    content = content.lstrip("\ufeff")
    if not content.strip():
        raise ValueError("the scenes CSV is empty")
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    table = list(csv.reader(io.StringIO(content), dialect=dialect))
    fieldnames = table[0] if table else []
    hm = _header_map(fieldnames)
    if "text" not in hm:
        raise ValueError("the scenes CSV needs a 'text' column (also accepted: narration, sentence, script); found: " + ", ".join(fieldnames or ["nothing"]))
    idx = {k: fieldnames.index(col) for k, col in hm.items()}
    rows: List[dict] = []
    for lineno, cells in enumerate(table[1:], start=2):
        if len(cells) > len(fieldnames):
            extra = len(cells) - len(fieldnames); ti = idx["text"]
            cells = cells[:ti] + [",".join(cells[ti:ti + extra + 1])] + cells[ti + extra + 1:]
            if notes is not None:
                notes.append(f"row {lineno}: an unquoted comma in the text was repaired (\"{cells[ti][:50]}\")")
        row = {k: (cells[i].strip() if i < len(cells) else "") for k, i in idx.items()}
        if not any(row.values()):
            continue
        where = f"row {lineno}"
        if not row["text"]:
            raise ValueError(f"{where}: the text is empty")
        sc: Dict[str, Any] = {"text": " ".join(row["text"].split())}
        if row.get("start") or row.get("end"):
            if not (row.get("start") and row.get("end")):
                raise ValueError(f"{where}: give both start and end, or neither")
            sc["start"], sc["end"] = parse_time(row["start"], f"{where} start"), parse_time(row["end"], f"{where} end")
            if sc["end"] <= sc["start"]:
                raise ValueError(f"{where}: end ({row['end']}) must be after start ({row['start']})")
        for k in ("chapter", "footage"):
            if row.get(k):
                sc[k] = row[k]
        for k, allowed in (("visual", VISUALS), ("shot", SHOTS), ("source", SOURCES)):
            v = (row.get(k) or "").strip().lower().replace(" ", "")
            if v:
                v = {"3d": "3d", "anatomy": "3d", "stock": "stock", "animation": "3d"}.get(v, v)
                if k == "shot" and v not in allowed:      # a described shot (internal_cross_section, molecular_closeup ...) is kept as a description, never an error
                    sc["shot_desc"] = " ".join(row[k].replace("_", " ").split()).lower(); continue
                if v not in allowed:
                    raise ValueError(f"{where}: {k} '{row[k]}' is not one of: {', '.join(allowed)}")
                sc[k] = v
        for k in INTENT_COLUMNS:      # snake_case or plain words, kept as plain words
            if row.get(k):
                sc[k] = " ".join(row[k].replace("_", " ").split()).lower()
        for k in ("stat", "stat_unit", "stat_label", "stat_kicker", "stat_source", "card_title", "card_kicker"):
            if row.get(k):
                sc[k] = " ".join(row[k].split())
        if row.get("events"):
            evs = []
            for part in _split(row["events"]):
                if not part:
                    continue
                if ":" not in part:
                    raise ValueError(f"{where}: each timeline event is 'when: what happens', events separated by ' | ' (got '{part[:40]}')")
                w_, l_ = part.split(":", 1)
                evs.append({"when": w_.strip(), "label": l_.strip()})
            sc["events"] = evs
        for k in ("body_region", "body_scale", "body_focus", "body_effect", "card_type"):      # body-map beats (visual=body): enumerations are checked against the body's anchors by bodymap.validate before rendering
            if row.get(k):
                sc[k] = row[k].strip().lower().replace(" ", "_")
        for k in ("body_label", "card_ref", "card_prompt"):
            if row.get(k):
                sc[k] = " ".join(row[k].split())
        if row.get("card_at"):
            try: sc["card_at"] = float(row["card_at"])
            except ValueError: raise ValueError(f"{where}: card_at '{row['card_at']}' must be seconds into the beat, like 0.8") from None
        for k in ("items", "do", "dont"):
            if row.get(k):
                sc[k] = [" ".join(x.split()) for x in _split(row[k]) if x.strip()]
        ov = (row.get("overlay") or "").strip().lower()
        if ov:
            if ov not in OVERLAYS:
                raise ValueError(f"{where}: overlay '{row['overlay']}' is not one of: {', '.join(OVERLAYS)}")
            sc["overlay"] = ov      # "none" is kept: it tells the planner not to add a figure over this picture
        if row.get("overlay_text"):
            sc["overlay_text"] = " ".join(row["overlay_text"].split())
        if sc.get("visual") in ("checklist", "steps") and len(sc.get("items") or []) < 2:
            raise ValueError(f"{where}: visual={sc['visual']} needs at least two items, separated by ' | '")
        if sc.get("visual") == "compare" and not (sc.get("do") and sc.get("dont")):
            raise ValueError(f"{where}: visual=compare needs both the dont and the do columns (items separated by ' | ')")
        if sc.get("overlay") == "stat" and not sc.get("stat"):
            raise ValueError(f"{where}: overlay=stat needs the number in the stat column (as spoken in the narration)")
        if sc.get("overlay") == "label" and not sc.get("overlay_text"):
            raise ValueError(f"{where}: overlay=label needs the words in overlay_text")
        if sc.get("visual") == "body" and not sc.get("body_region"):
            raise ValueError(f"{where}: visual=body needs body_region (forearm_l, heart, chest, head ...); see docs/health_cinema/CSV_GENERATOR_PROMPT.md")
        if sc.get("visual") == "stat" and not sc.get("stat"):
            raise ValueError(f"{where}: visual=stat needs the number in the stat column (as spoken in the narration)")
        if sc.get("visual") == "timeline" and "events" in sc and len(sc["events"]) < 2:
            raise ValueError(f"{where}: a timeline needs at least two events in the events column")
        if row.get("organ"):
            sc["organ"] = re.sub(r"\s+", " ", row["organ"].strip().lower())
        if row.get("footage_alt"):
            sc["footage_alt"] = [q for q in _split(row["footage_alt"]) if q]
        _puppet_cells(row, sc, where, notes)
        src = _sources(row, where)
        if src:
            sc["sources"] = src
        rows.append(sc)
    if not rows:
        raise ValueError("the scenes CSV has a header but no rows")
    timed = [("start" in r) for r in rows]
    if any(timed) and not all(timed):
        first_missing = timed.index(False) + 2
        raise ValueError(f"start/end are filled on some rows but not row {first_missing}: fill them on every row, or clear them on all rows to align to the voiceover")
    prev_end = None
    for i, r in enumerate(rows):
        if "start" in r:
            if prev_end is not None and r["start"] < prev_end - 0.05:
                raise ValueError(f"row {i + 2}: starts at {r['start']:.1f}s, before the previous row ends ({prev_end:.1f}s)")
            prev_end = r["end"]
    for i, r in enumerate(rows, start=1):
        r["scene_no"] = i
    if notes is not None: notes.extend(intent_notes(rows))      # checked once when the CSV is read: what each 3D row asks the viewer to see
    return rows


def intent_notes(rows: Sequence[dict]) -> List[str]:
    """Warnings (never errors) about what the 3D rows ask the viewer to see:
    - consecutive 3D rows that name only an organ (the organ is not the visual subject: say what is seen),
    - one visual_subject used for different biological processes (each process needs its own subject),
    - a 3D row with a visual_subject but neither visual_intent nor visual_action (what must the picture show?).
    Row numbers are the CSV's own (row 2 is the first data row)."""
    out: List[str] = []; run: List[int] = []; organ = ""
    def flush():
        if len(run) >= 2: out.append(f"rows {run[0]}-{run[-1]}: {len(run)} 3D rows in a row name only the organ ({organ}); give each its visual_subject and biological_process (what is seen, not where)")
    for r in rows:
        n = int(r.get("scene_no") or 0) + 1
        if r.get("visual") == "3d" and r.get("organ") and not r.get("visual_subject"):
            if not run or r.get("organ") != organ: flush(); run, organ = [], r.get("organ")
            run.append(n)
        else:
            flush(); run = []
        if r.get("visual") == "3d" and r.get("visual_subject") and not (r.get("visual_intent") or r.get("visual_action")):
            out.append(f"row {n}: visual_subject '{r['visual_subject']}' has no visual_intent or visual_action: say what the picture must show or change")
    flush()
    procs: Dict[str, Dict[str, int]] = {}
    for r in rows:
        if r.get("visual_subject") and r.get("biological_process"): procs.setdefault(r["visual_subject"], {}).setdefault(r["biological_process"], int(r.get("scene_no") or 0) + 1)
    for subj, ps in procs.items():
        if len(ps) > 1: out.append(f"visual_subject '{subj}' is used for different processes ({', '.join(f'{p} (row {n})' for p, n in ps.items())}): give each process its own subject")
    return out


def read_scenes_csv(path: str, notes: Optional[List[str]] = None) -> List[dict]:
    raw = Path(path).read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252")      # older Excel exports
    return parse_csv_text(content, notes)


def needs_alignment(rows: Sequence[dict]) -> bool:
    return bool(rows) and "start" not in rows[0]


def align_to_words(rows: Sequence[dict], words: Sequence[Any], total_s: float = 0.0):
    """Untimed rows + the voiceover's word times [(word, start, end), ...] -> (timed scene dicts, matched share). The scenes are contiguous and each carries its own `words`.
    Rows are matched to the transcript by their words, in order; a row the transcript missed is placed between its neighbours. Raises ValueError if the
    script is clearly not what the voiceover says."""
    wl: List[dict] = []
    for item in words or []:
        try:
            wl.append({"w": str(item[0]), "t0": float(item[1]), "t1": float(item[2])})
        except (TypeError, ValueError, IndexError):
            continue
    if not wl:
        raise ValueError("the voiceover has no recognised words to align the scenes CSV to")
    wtok, widx = [], []                                   # transcript tokens -> index of the word they came from
    for i, w in enumerate(wl):
        for tk in _tokens(w["w"]):
            wtok.append(tk)
            widx.append(i)
    stok, srow = [], []
    for r_i, r in enumerate(rows):
        for tk in _tokens(r["text"]):
            stok.append(tk)
            srow.append(r_i)
    if not stok:
        raise ValueError("the scenes CSV has no words")
    match: Dict[int, int] = {}                            # script token -> transcript token
    for blk in difflib.SequenceMatcher(None, stok, wtok, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            match[blk.a + k] = blk.b + k
    frac = len(match) / len(stok)
    if frac < MIN_MATCH:
        raise ValueError(f"only {frac:.0%} of the CSV's words are in the voiceover: this CSV does not look like this narration "
                         f"(CSV: {len(stok)} words, opens \"{' '.join(stok[:8])}…\"; voiceover: {len(wtok)} words, opens \"{' '.join(wtok[:8])}…\"). "
                         f"Record the voiceover from the CSV's text column, or fill start and end")
    first: List[Optional[int]] = [None] * len(rows)       # transcript word index at each row's first/last matched token
    last: List[Optional[int]] = [None] * len(rows)
    for si, wi in sorted(match.items()):
        r = srow[si]
        w = widx[wi]
        if first[r] is None:
            first[r] = w
        last[r] = w
    n_words = len(wl)
    starts: List[float] = [0.0] * len(rows)
    for i in range(len(rows)):
        if first[i] is not None:
            starts[i] = float(first[i])
    known = [i for i in range(len(rows)) if first[i] is not None]
    for i in range(len(rows)):                            # unmatched rows: share the gap between known neighbours by their word counts
        if first[i] is not None:
            continue
        lo = max((k for k in known if k < i), default=None)
        hi = min((k for k in known if k > i), default=None)
        a = (last[lo] + 1) if lo is not None else 0
        b = float(first[hi]) if hi is not None else float(n_words)
        run = [j for j in range(lo + 1 if lo is not None else 0, hi if hi is not None else len(rows)) if first[j] is None]
        weights = [max(1, len(_tokens(rows[j]["text"]))) for j in run]
        before = sum(weights[:run.index(i)])
        starts[i] = a + (b - a) * before / sum(weights)
    for i in range(1, len(rows)):                         # rows stay in order
        starts[i] = max(starts[i], starts[i - 1])
    starts[0] = 0.0
    out: List[dict] = []
    for i, r in enumerate(rows):
        a = int(starts[i])
        b = int(starts[i + 1]) if i + 1 < len(rows) else n_words
        chunk = wl[a:max(b, a + 1)] if a < n_words else wl[-1:]
        sc = {k: v for k, v in r.items()}
        sc["words"] = [dict(w) for w in chunk]
        sc["start"] = chunk[0]["t0"] if i else 0.0
        sc["end"] = chunk[-1]["t1"]
        out.append(sc)
    for i, sc in enumerate(out):                          # contiguous in time, like the transcript-cut sentences
        sc["end"] = out[i + 1]["start"] if i + 1 < len(out) else max(sc["end"], float(total_s or 0.0))
        if sc["end"] <= sc["start"]:
            sc["end"] = sc["start"] + 0.3
    return out, frac


def match_note(frac: float) -> str:
    return f"{frac:.0%} of the CSV's words matched the voiceover" + ("" if frac >= WARN_MATCH else ": some scenes were placed by estimate, check their timing")


def has_direction(rows: Sequence[dict]) -> bool:
    """True when the CSV itself directs the visuals (any row fills a visual direction column): the app then plans from it instead of asking Gemini."""
    return any(any(r.get(k) for k in HINT_COLUMNS) for r in rows)
