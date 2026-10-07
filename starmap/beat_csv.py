"""The StarMap beat CSV: one row per beat, layer, photo card and footage clip, timed by the narrator's own words.

Written by an AI from the script with composition_styles/starmap_beats_prompt.txt (or by hand), loaded AS WRITTEN: nothing is
re-cut or guessed; a row the plan cannot hold is an error naming the row (as a spreadsheet numbers it: the header is row 1).

    row    what it is                      columns used
    plan   the plan (optional, first row)  label = video title, date = the reference "now" (what today means), end = duration,
                                           id = an optional starting context (a dataset id; nothing is selected by it)
    beat   opens a beat                    beat, vo_anchor | start, mode (map | map_footage | footage), place, frame, type,
                                           date, text (the narration), why
    layer  something on the map            type (title marker zone path craft orbit stat caption distance), vo_anchor | t,
                                           id, place, label, sub, text, value_from, value_to, format, anchor, until, hold
    card   a photo card (map_footage)      vo_anchor | t, asset, label, sub, anchor, hold
    clip   a clip (footage)                asset, dur, why
Times are narration seconds (start / t) OR the narrator's words (vo_anchor): a beat starts where its words are spoken and
ends where the next beat starts; its own rows appear on their words, searched from the beat's first words. The words are
found with PakMap's matcher (pakmap.anchor, used read-only) in the voiceover's transcript.
"""

from __future__ import annotations

import csv
import difflib
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

COLUMNS = ("beat", "row", "vo_anchor", "start", "end", "t", "mode", "type", "id", "place", "frame", "date", "label", "sub", "text",
           "value_from", "value_to", "format", "anchor", "until", "hold", "asset", "dur", "why", "extra")
ROWS = ("plan", "beat", "layer", "card", "clip")
MODES = ("map", "map_footage", "footage")
FRAMES = ("surface", "close", "body", "system", "inner", "solar", "heliosphere", "galaxy", "universe")
MOVES = ("", "hold", "push_in", "pull_out", "orbit")
LAYER_TYPES = ("title", "marker", "zone", "path", "craft", "orbit", "stat", "caption", "distance", "line", "rings", "pointer")
CARD_ANCHORS = ("tr", "mr", "ml", "bl")
DEFAULT_HOLD = {"stat": 4.5, "caption": 4.0, "card": 6.0}
# where a picture or clip comes from: the app's Visual Plan sources, NASA's image library, or file:<name> (a file of your own)
ASSET_SOURCES = ("nasa_image", "nasa_video", "stock_image", "stock_video", "flow_image", "flow_video", "youtube_video", "archive_video",
                 "commons_image", "commons_video", "file")


def asset_source(asset: str) -> str:
    """The source prefix of an asset ("nasa_image:..." -> "nasa_image"); raises ValueError for an unknown or missing one."""
    head, sep, rest = asset.partition(":")
    src = head.strip().lower()
    if not sep or src not in ASSET_SOURCES or not rest.strip():
        near = difflib.get_close_matches(src, ASSET_SOURCES, n=1, cutoff=0.6)
        raise ValueError(f"asset {asset!r} must be <source>:<what to find> with a source of {', '.join(ASSET_SOURCES)}"
                         + (f" (did you mean {near[0]}?)" if near else ""))
    return src
MAX_CARDS = 3


class PlanError(ValueError):
    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class Item:
    row: int
    kind: str                      # layer | card | clip
    type: str = ""
    t: Optional[float] = None
    id: str = ""
    place: str = ""
    label: str = ""
    sub: str = ""
    text: str = ""
    value_from: Optional[float] = None
    value_to: Optional[float] = None
    format: str = ""
    anchor: str = ""
    until: str = ""
    hold: Optional[float] = None
    asset: str = ""
    dur: Optional[float] = None
    why: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    timed_by_words: bool = False


@dataclass
class Beat:
    id: str
    row: int
    mode: str
    start: float
    end: float = -1.0
    place: str = ""
    frame: str = ""
    move: str = ""
    date: str = ""
    text: str = ""
    why: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    layers: List[Item] = field(default_factory=list)
    cards: List[Item] = field(default_factory=list)
    clips: List[Item] = field(default_factory=list)


@dataclass
class Plan:
    beats: List[Beat]
    duration: float
    pack: str = ""                                # the plan row's id: an optional starting context, never a selection
    title: str = ""
    notes: List[str] = field(default_factory=list)
    reference_now: str = ""                       # the plan row's date: what "now" and "today" mean for this video


def is_starmap_csv(text: str) -> bool:
    """A StarMap beat CSV starts beat,row and has a date column (Hybrid's beat CSV has none)."""
    first = [c.strip().lower() for c in next(csv.reader(io.StringIO(text.lstrip("﻿"))), [])]
    return first[:2] == ["beat", "row"] and "date" in first


# Whisper writes numbers its own way: "the eleventh of April" comes back as "11th of april" or "11 april", "1:47" as "1 47".
# The CSV copies the script's words. Both sides are put in one form before matching (the shared matcher already turns
# spoken cardinals into digits): ordinals and "11th" become 11, a clock time becomes two numbers, and a date's
# "the ... of" around a number is dropped. Words that already match are unchanged by this.
_ORDINALS = {w: i for i, w in enumerate(
    "zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth "
    "sixteenth seventeenth eighteenth nineteenth".split())}
_ORDINALS.update({"twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50, "sixtieth": 60, "seventieth": 70,
                  "eightieth": 80, "ninetieth": 90})
_TENS_WORDS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_UNIT_ORDINALS = "first|second|third|fourth|fifth|sixth|seventh|eighth|ninth"


def number_form(text: str) -> str:
    """One spelling for the numbers in a phrase or a transcript word (see above)."""
    t = str(text)
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", r"\1 \2", t)                                         # 1:47 -> 1 47
    t = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", t, flags=re.I)                             # 11th -> 11
    t = re.sub(rf"\b({'|'.join(_TENS_WORDS)})[\s-]+({_UNIT_ORDINALS})\b",                     # twenty-eighth -> 28
               lambda m: str(_TENS_WORDS[m[1].lower()] + _ORDINALS[m[2].lower()]), t, flags=re.I)
    t = re.sub(rf"\b({'|'.join(_ORDINALS)})\b", lambda m: str(_ORDINALS[m[1].lower()]), t, flags=re.I)   # sixteenth -> 16
    t = re.sub(r"\bthe\s+(\d+)\s+of\b", r"\1", t, flags=re.I)                                 # the 16 of november -> 16 november
    return t


class WordClock:
    """The narrator's words -> seconds, in script order. Beat rows move the search on; a beat's own rows are searched from the
    beat's first words and never move it (an AI often anchors a label on a later sentence: it must not break later beats)."""

    def __init__(self, words: Sequence, notes: List[str]):
        from pakmap.anchor import Transcript     # the shared word matcher (read-only)

        self.tr = Transcript([(number_form(w), s, e) for w, s, e in words]) if words else None
        self.cursor = 0
        self.notes = notes

    def _find(self, words: str):
        words = number_form(words)
        hit = self.tr.find(words, self.cursor)
        if hit is not None:
            return hit
        split = re.sub(r"(?<=\d)\.(?=\d)", " ", words)            # Whisper writes 1.3 as "1 3"
        if split != words and (hit := self.tr.find(split, self.cursor)) is not None:
            return hit
        near = self.tr.nearest(words)
        if (near and len(words.split()) == 1 and len(near[0].split()) == 1 and words[:1].lower() == near[0][:1].lower()
                and difflib.SequenceMatcher(None, words.lower(), near[0].lower()).ratio() >= 0.72):
            if (hit := self.tr.find(near[0], self.cursor)) is not None:
                self.notes.append(f"vo_anchor {words!r} was matched to {near[0]!r} at {near[1]:.1f}s (how the narration spells it)")
                return hit
        parts = words.split()
        for size in range(len(parts) - 1, 1, -1):                 # one wrong word: the same start, or end, with fewer words
            for label, sub in (("start", parts[:size]), ("end", parts[-size:])):
                if (hit := self.tr.find(" ".join(sub), self.cursor)) is not None:
                    self.notes.append(f"vo_anchor {words!r}: not spoken exactly; its {label} words {' '.join(sub)!r} were found at {hit[0].t_start:.1f}s")
                    return hit
        return None

    def at(self, phrase: str, *, advance: bool) -> float:
        if self.tr is None or not len(self.tr):
            raise ValueError("vo_anchor needs the narration: choose the voiceover first (or give start / t in seconds)")
        words, _, mod = phrase.partition("|")
        hit = self._find(words.strip())
        if hit is None:
            near = self.tr.nearest(words.strip())
            raise ValueError(f"vo_anchor {words.strip()!r} is not in the narration" + (f" (closest: {near[0]!r} at {near[1]:.1f}s)" if near else ""))
        m, _ = hit
        if m.out_of_order:
            raise ValueError(f"vo_anchor {words.strip()!r} is only spoken before the previous beat's words ({m.t_start:.1f}s): rows must follow the script in order")
        if advance:
            from pakmap.compile import hit_first

            self.cursor = hit_first(self.tr, m)
        return round(m.t_end if mod.strip().lower() == "end" else m.t_start, 3)


def _f(r: Dict[str, str], col: str) -> Optional[float]:
    v = r.get(col, "")
    if v == "":
        return None
    try:
        return float(v.replace(",", "")) if col in ("value_from", "value_to") else float(v)
    except ValueError:
        raise ValueError(f"{col} must be a number (got {v!r})") from None


def read_plan(text: str, words: Sequence = (), duration: Optional[float] = None) -> Plan:
    """A StarMap beat CSV -> Plan. Raises PlanError listing every problem by row."""
    notes: List[str] = []
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows or not is_starmap_csv(text):
        raise PlanError(["this is not a StarMap beat CSV: the first row must be the header " + ",".join(c for c in COLUMNS if c not in ("start", "end", "t", "extra"))])
    head = [c.strip().lower() for c in rows[0]]
    problems: List[str] = [f"unknown column {c!r}" for c in head if c and c not in COLUMNS]
    clock = WordClock(words, notes)
    beats: List[Beat] = []
    pack, title, plan_end, ref_now = "", "", None, ""
    failed: set = set()
    for n, cells in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in cells):
            continue
        if len(cells) > len(head) and any(c.strip() for c in cells[len(head):]):
            problems.append(f"row {n}: has {len(cells)} cells but the header has {len(head)} (a comma inside a cell needs quotes)")
            continue
        r = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(head) if h}
        kind = r.get("row", "").lower()
        if kind in ("layer", "card", "clip") and r.get("beat") in failed:
            continue
        try:
            extra = json.loads(r.get("extra") or "{}")
            if not isinstance(extra, dict):
                raise ValueError("extra must be a JSON object")
            anchor = r.get("vo_anchor", "")
            if kind == "plan":
                pack, title, plan_end, ref_now = r.get("id", ""), r.get("label", ""), _f(r, "end"), r.get("date", "")
            elif kind == "beat":
                if not r.get("beat"):
                    raise ValueError("a beat row needs its beat id in the beat column (b1, b2 ...)")
                if any(b.id == r["beat"] for b in beats):
                    raise ValueError(f"beat {r['beat']} is used twice")
                mode = r.get("mode", "").lower()
                if mode not in MODES:
                    raise ValueError(f"mode must be one of {', '.join(MODES)} (got {r.get('mode')!r})")
                frame, move = r.get("frame", "").lower(), r.get("type", "").lower()
                if mode != "footage":
                    if not r.get("place"):
                        raise ValueError(f"a {mode} beat needs a place (what the camera looks at)")
                    if frame not in FRAMES:
                        raise ValueError(f"frame must be one of {', '.join(FRAMES)} (got {r.get('frame')!r})")
                    if move not in MOVES:
                        raise ValueError(f"type must be one of {', '.join(m for m in MOVES if m)} (got {r.get('type')!r})")
                start = _f(r, "start")
                if start is None and anchor:
                    start = clock.at(anchor, advance=True)
                if start is None:
                    if beats:
                        raise ValueError("a beat needs a vo_anchor (its first words) or a start in seconds")
                    start = 0.0
                if not beats and start > 0:
                    if start > 0.5:
                        notes.append(f"row {n}: the first beat starts at 0s (the video starts there), not at {start:.1f}s")
                    start = 0.0
                end = _f(r, "end")
                beats.append(Beat(id=r["beat"], row=n, mode=mode, start=start, end=end if end is not None else -1.0, place=r.get("place", ""),
                                  frame=frame, move=move, date=r.get("date", ""), text=r.get("text", ""), why=r.get("why", ""), extra=extra))
            elif kind in ("layer", "card", "clip"):
                if not beats:
                    raise ValueError(f"a {kind} row must come after the beat row it belongs to")
                b = beats[-1]
                if r.get("beat") and r["beat"] != b.id:
                    raise ValueError(f"says beat {r['beat']!r} but follows beat {b.id!r}: keep each beat's rows under its beat row")
                t = _f(r, "t")
                by_words = False
                if t is None and anchor and kind != "clip":
                    try:
                        t, by_words = clock.at(anchor, advance=False), True
                    except ValueError as exc:
                        notes.append(f"row {n}: {exc}; it appears at the start of beat {b.id}")
                it = Item(row=n, kind=kind, type=r.get("type", "").lower(), t=t, id=r.get("id", ""), place=r.get("place", ""),
                          label=r.get("label", ""), sub=r.get("sub", ""), text=r.get("text", ""), value_from=_f(r, "value_from"),
                          value_to=_f(r, "value_to"), format=r.get("format", ""), anchor=r.get("anchor", "").lower(), until=r.get("until", "").lower(),
                          hold=_f(r, "hold"), asset=r.get("asset", ""), dur=_f(r, "dur"), why=r.get("why", ""), extra=extra, timed_by_words=by_words)
                if kind == "layer":
                    if b.mode == "footage":
                        raise ValueError("a footage beat has only clip rows (the map is hidden)")
                    if it.type not in LAYER_TYPES:
                        raise ValueError(f"layer type must be one of {', '.join(LAYER_TYPES)} (got {r.get('type')!r})")
                    b.layers.append(it)
                elif kind == "card":
                    if b.mode != "map_footage":
                        raise ValueError(f"photo cards belong to map_footage beats (beat {b.id} is {b.mode})")
                    if len(b.cards) >= MAX_CARDS:
                        raise ValueError(f"beat {b.id} already has {MAX_CARDS} photo cards")
                    if not it.asset:
                        raise ValueError("a card needs an asset (stock_image:<what it shows>, nasa_image:<...>, a clip such as nasa_video:<...>, or file:<name>)")
                    asset_source(it.asset)
                    if it.anchor and it.anchor not in CARD_ANCHORS:
                        raise ValueError(f"card anchor must be one of {', '.join(CARD_ANCHORS)}")
                    b.cards.append(it)
                else:
                    if b.mode != "footage":
                        raise ValueError(f"clips belong to footage beats (beat {b.id} is {b.mode})")
                    if not it.asset:
                        raise ValueError("a clip needs an asset (stock_video:<what it shows>, nasa_video:<...>, flow_video:<...> or file:<name>)")
                    asset_source(it.asset)
                    b.clips.append(it)
            else:
                raise ValueError(f"row must be one of {', '.join(ROWS)} (got {kind!r})")
        except (ValueError, TypeError) as exc:
            problems.append(f"row {n}: {exc.args[0] if exc.args else exc}")
            if kind == "beat" and r.get("beat"):
                failed.add(r["beat"])
    if not beats and not problems:
        problems.append("the CSV has no beat rows")
    if problems:
        raise PlanError(problems)
    words_end = clock.tr.end if clock.tr is not None and len(clock.tr) else None
    total = plan_end or duration or words_end
    for i, b in enumerate(beats):
        if b.end < 0:
            if i + 1 < len(beats):
                b.end = beats[i + 1].start
            elif total:
                b.end = total
            else:
                problems.append(f"row {b.row}: the last beat needs an end (seconds), or load the CSV with the voiceover so the video's length is known")
                continue
        if b.end <= b.start:
            problems.append(f"row {b.row}: beat {b.id} would end at {b.end:.1f}s, not after it starts ({b.start:.1f}s): its words come before the previous beat's, or two beats start on the same words")
        if not (b.layers or b.cards or b.clips) and b.mode == "footage":
            problems.append(f"row {b.row}: footage beat {b.id} has no clip rows")
        if b.mode == "map_footage" and not b.cards:
            problems.append(f"row {b.row}: map_footage beat {b.id} has no card rows")
        for it in b.layers + b.cards:
            if it.t is None:
                it.t = b.start
            elif not (b.start - 1e-6 <= it.t < b.end - 1e-6):
                notes.append(f"row {it.row}: its words are spoken at {it.t:.1f}s, outside beat {b.id} ({b.start:.1f}-{b.end:.1f}s); it appears at the start of the beat")
                it.t = b.start
    if problems:
        raise PlanError(problems)
    return Plan(beats=beats, duration=float(total or beats[-1].end), pack=pack, title=title, notes=notes, reference_now=ref_now)
