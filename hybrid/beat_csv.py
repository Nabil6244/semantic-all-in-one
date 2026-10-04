"""The Hybrid plan as a spreadsheet: one row per thing, grouped under its beat, and back again WITHOUT losing anything.

The plan (hybrid.plan.HybridPlan) stays the source of truth; this is another way to write it down, so a plan the Director made
can be read and edited like the PakMap CSV and loaded back exactly. Unlike the Hybrid CSV import (hybrid.csv_import, which turns
pakMap rows into beats and has to drop what it cannot place), nothing here is guessed: a row the plan cannot hold is an error that
names the row.

    row      what it is                         columns used
    plan     the plan itself (first row)        end = duration; extra = {"settings": ..., "version": ...}
    chapter  a long-form chapter                id, start, end, label = title, extra = anything else
    beat     a story beat (opens a beat)        beat, mode, start, end, place/frame = camera target, type = camera move
                                                (push_in | hold | empty), text = narration, why = purpose
    camera   a camera step of the beat          type = action, place, frame, t, dur
    layer    a map layer of the beat            type, id, t, place (a line: places separated by ;), label, sub, text, role, kind,
                                                value_from, value_to, format, anchor, until, hold
    clip     a footage clip of the beat         asset, dur, why = what it shows
    card     a map_footage beat's photo card    asset, t, place, label, hold
Times are narration seconds, OR the narrator's own words in vo_anchor (a CSV written by an AI from the script with
composition_styles/hybrid_beats_prompt.txt): a beat starts where its words are spoken and ends where the next beat starts; a
layer, card or camera step appears on its words. The words are found with pakMap's matcher in the voiceover's transcript, in
order. A beat with a camera target (place/frame) and no camera rows gets its moves from hybrid.director.derive_cameras, exactly
like a Director plan. Anything rarely edited (a beat's intents, confidence, findings; a layer's params; a clip's kenburns)
sits in the row's `extra` cell as JSON."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Optional

from .plan import MODES, Beat, CameraStep, Clip, HybridPlan, Layer, PlanError, Support

COLUMNS = ("beat", "row", "vo_anchor", "mode", "start", "end", "t", "dur", "id", "type", "place", "frame", "label", "sub", "text", "role", "kind",
           "value_from", "value_to", "format", "anchor", "until", "hold", "asset", "why", "extra")
ROWS = ("plan", "chapter", "beat", "camera", "layer", "clip", "card")
# beat fields kept in `extra` (with their defaults: a default is not written)
BEAT_EXTRA = {"geo_intent": "", "footage_intent": "", "overlay_intent": "", "transition": "dissolve", "keep_overlays": False,
              "transition_sound": "", "confidence": 1.0, "validation": "", "findings": [], "chapter": 0}


def is_beat_csv(text: str) -> bool:
    """True when `text` starts with this format's header (a Hybrid CSV for import starts with pakMap's columns instead)."""
    first = next(csv.reader(io.StringIO(text.lstrip("﻿"))), [])
    return [c.strip().lower() for c in first[:2]] == ["beat", "row"]


# ---- plan -> CSV ----------------------------------------------------------------------------------------------------

def _num(v: Optional[float]) -> str:
    if v is None:
        return ""
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def _extra(d: Dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False, sort_keys=True) if d else ""


def plan_to_csv(plan: HybridPlan) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    put = lambda **kw: w.writerow({k: kw.get(k, "") for k in COLUMNS})  # noqa: E731
    put(row="plan", end=_num(plan.duration), extra=_extra({k: v for k, v in (("settings", plan.settings), ("version", plan.version)) if v not in ({}, 1)}))
    for c in plan.chapters:
        rest = {k: v for k, v in c.items() if k not in ("id", "title", "start", "end")}
        put(row="chapter", id=str(c.get("id", "")), start=_num(c.get("start")), end=_num(c.get("end")), label=str(c.get("title", "")), extra=_extra(rest))
    for b in plan.beats:
        extra = {k: getattr(b, k) for k, dflt in BEAT_EXTRA.items() if getattr(b, k) != dflt}
        put(beat=b.id, row="beat", mode=b.mode, start=_num(b.start), end=_num(b.end), place=b.cam_place, frame=b.cam_frame, type=b.cam_move, text=b.narration,
            why=b.purpose, extra=_extra(extra))
        for c in b.camera:
            put(beat=b.id, row="camera", type=c.action, place=c.place, frame=c.frame, t=_num(c.t), dur=_num(c.dur),
                extra=_extra({"zoom_delta": c.zoom_delta} if c.zoom_delta is not None else {}))
        for lay in b.layers:
            put(beat=b.id, row="layer", type=lay.type, id=lay.id, t=_num(lay.t), place=";".join(lay.places) if lay.places else lay.place,
                label=lay.label, sub=lay.sub, text=lay.text, role=lay.role, kind=lay.kind, value_from=_num(lay.value_from), value_to=_num(lay.value_to),
                format=lay.format, anchor=lay.anchor, until="" if lay.until == "beat_end" else (_num(lay.until) if isinstance(lay.until, (int, float)) else str(lay.until)),
                hold=_num(lay.hold), extra=_extra(_layer_extra(lay)))
        for c in b.clips:
            put(beat=b.id, row="clip", asset=c.asset, dur=_num(c.dur), why=c.reason,
                extra=_extra({k: True for k in ("kenburns", "loop") if getattr(c, k)}))
        if b.support is not None:
            s = b.support
            put(beat=b.id, row="card", asset=s.asset, t=_num(s.t), place=s.place, label=s.label, hold=_num(s.hold))
    return buf.getvalue()


def _layer_extra(lay: Layer) -> Dict[str, Any]:
    out: Dict[str, Any] = {"params": lay.params} if lay.params else {}
    if lay.places and lay.place:  # a line keeps its waypoints in the place column; a place it also has goes here
        out["place"] = lay.place
    return out


# ---- CSV -> plan ----------------------------------------------------------------------------------------------------

def needs_words(text: str) -> bool:
    """True when some row is timed only by the narrator's words (so the voiceover's transcript is needed to read it)."""
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows:
        return False
    head = [c.strip().lower() for c in rows[0]]
    if "vo_anchor" not in head:
        return False
    col = {h: i for i, h in enumerate(head)}
    cell = lambda cells, h: cells[col[h]].strip() if h in col and col[h] < len(cells) else ""  # noqa: E731
    for cells in rows[1:]:
        kind = cell(cells, "row").lower()
        timed = cell(cells, "start") if kind == "beat" else cell(cells, "t")
        if cell(cells, "vo_anchor") and not timed:
            return True
    return False


class _Clock:
    """The narrator's words -> seconds, in script order (pakMap's matcher: "47 million" finds "forty seven million")."""

    def __init__(self, words):
        from pakmap.anchor import Transcript

        self.tr = Transcript(list(words)) if words else None
        self.cursor = 0

    def at(self, phrase: str) -> float:
        from pakmap.compile import hit_first

        if self.tr is None or not len(self.tr):
            raise ValueError("vo_anchor needs the narration: choose the voiceover first, then load the CSV")
        words, _, mod = phrase.partition("|")
        hit = self.tr.find(words.strip(), self.cursor)
        if hit is None:
            near = self.tr.nearest(words.strip())
            raise ValueError(f"vo_anchor {words.strip()!r} is not in the narration" + (f" (closest: {near[0]!r} at {near[1]:.1f}s)" if near else ""))
        m, _nxt = hit
        if m.out_of_order:
            raise ValueError(f"vo_anchor {words.strip()!r} is only spoken before the previous row's words ({m.t_start:.1f}s): rows must follow the script in order")
        self.cursor = hit_first(self.tr, m)  # the next row may reuse the same words
        return round(m.t_end if mod.strip().lower() == "end" else m.t_start, 3)


def import_beats(text: str, words=(), duration: Optional[float] = None):
    """A beat CSV read against the narration: (plan, notes) in the same shape as the Hybrid CSV import (hybrid.csv_import.CsvImport)."""
    from .csv_import import CsvImport

    notes: List[str] = []
    plan = plan_from_csv(text, words, duration, notes=notes)
    return CsvImport(plan=plan, notes=notes)


def plan_from_csv(text: str, words=(), duration: Optional[float] = None, *, notes: Optional[List[str]] = None) -> HybridPlan:
    """Read a beat CSV into a plan. Every problem names its row (as a spreadsheet numbers it: the header is row 1). `words`
    (the voiceover's transcript) and `duration` are needed only when rows are timed by vo_anchor."""
    notes = notes if notes is not None else []
    clock = _Clock(words)
    open_ends: Dict[int, int] = {}          # beat index -> its CSV row (end to be filled from the next beat)
    anchored: List[tuple] = []              # (beat index, row number, what, time) to check against the beat's span
    any_camera = False
    failed_beats = set()                    # a beat row with a problem: its own rows are not reported again
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows or not is_beat_csv(text):
        raise PlanError(["this is not a Hybrid beat CSV: the first row must be the header " + ",".join(COLUMNS)])
    head = [c.strip().lower() for c in rows[0]]
    unknown = [c for c in head if c and c not in COLUMNS]
    problems: List[str] = [f"unknown column {c!r}" for c in unknown]
    plan_duration: Optional[float] = None
    settings: Dict[str, Any] = {}
    version = 1
    chapters: List[Dict[str, Any]] = []
    beats: List[Beat] = []
    for n, cells in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in cells):
            continue
        r = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(head) if h}
        at = f"row {n}"
        try:
            extra = json.loads(r.get("extra") or "{}")
            if not isinstance(extra, dict):
                raise ValueError("extra must be a JSON object")
        except ValueError as exc:
            problems.append(f"{at}: the extra cell is not valid JSON ({exc})")
            continue
        kind = r.get("row", "").lower()
        if kind in ("camera", "layer", "clip", "card") and r.get("beat") in failed_beats:
            continue
        try:
            anchor = r.get("vo_anchor", "")

            def when(col: str) -> Optional[float]:
                return _f(r, col) if r.get(col) else (clock.at(anchor) if anchor else None)

            if kind == "plan":
                plan_duration = _f(r, "end", required=True)
                settings, version = dict(extra.pop("settings", {}) or {}), int(extra.pop("version", 1))
                _no_more(extra)
            elif kind == "chapter":
                chapters.append({"id": _int_or_str(r.get("id", "")), "title": r.get("label", ""), "start": _f(r, "start"), "end": _f(r, "end"), **extra})
            elif kind == "beat":
                if not r.get("beat"):
                    raise ValueError("a beat row needs its beat id in the beat column")
                if r.get("mode") not in MODES:
                    raise ValueError(f"mode must be one of {', '.join(MODES)} (got {r.get('mode')!r})")
                start = when("start")
                if start is None:
                    if beats:
                        raise ValueError("a beat row needs a start (seconds) or a vo_anchor (the words it starts on)")
                    start = 0.0
                if not beats and start > 0:
                    if start > 0.5:
                        notes.append(f"row {n}: the first beat starts at 0s (the video starts there), not at {start:.1f}s")
                    start = 0.0
                end = _f(r, "end")
                b = Beat(id=r["beat"], mode=r.get("mode", ""), start=start, end=end if end is not None else -1.0,
                         purpose=r.get("why", ""), narration=r.get("text", ""), cam_place=r.get("place", ""), cam_frame=r.get("frame", ""),
                         cam_move=r.get("type", ""))
                if end is None:
                    open_ends[len(beats)] = n
                for k, dflt in BEAT_EXTRA.items():
                    if k in extra:
                        v = extra.pop(k)
                        setattr(b, k, type(dflt)(v) if not isinstance(dflt, list) else [str(x) for x in v])
                _no_more(extra)
                beats.append(b)
            elif kind in ("camera", "layer", "clip", "card"):
                if not beats:
                    raise ValueError(f"a {kind} row must come after the beat row it belongs to")
                b = beats[-1]
                if r.get("beat") and r["beat"] != b.id:
                    raise ValueError(f"says beat {r['beat']!r} but follows beat {b.id!r}: keep each beat's rows under its beat row")
                t = when("t")
                if t is not None and anchor and not r.get("t"):
                    anchored.append((len(beats) - 1, n, f"{kind} {r.get('id') or r.get('type') or ''}".strip(), t))
                if kind == "camera":
                    any_camera = True
                    b.camera.append(CameraStep(action=r.get("type", ""), place=r.get("place", ""), frame=r.get("frame", ""),
                                               t=t if t is not None else b.start, dur=_f(r, "dur"), zoom_delta=_opt(extra.pop("zoom_delta", None))))
                elif kind == "layer":
                    places = [p.strip() for p in r.get("place", "").split(";") if p.strip()]
                    is_line = r.get("type") == "line" or len(places) > 1
                    until: Any = r.get("until") or "beat_end"
                    try:
                        until = float(until)
                    except ValueError:
                        pass
                    b.layers.append(Layer(
                        id=r.get("id") or f"{b.id}_{r.get('type') or 'layer'}{len(b.layers) + 1}", type=r.get("type", ""), t=t if t is not None else b.start,
                        place=extra.pop("place", "") if is_line else r.get("place", ""), places=places if is_line else [],
                        label=r.get("label", ""), sub=r.get("sub", ""), text=r.get("text", ""), role=r.get("role", ""), kind=r.get("kind", ""),
                        value_from=_f(r, "value_from"), value_to=_f(r, "value_to"), format=r.get("format", ""), anchor=r.get("anchor", ""),
                        until=until, hold=_f(r, "hold"), params=dict(extra.pop("params", {}) or {})))
                elif kind == "clip":
                    b.clips.append(Clip(asset=r.get("asset", ""), dur=_f(r, "dur"), reason=r.get("why", ""),
                                        kenburns=bool(extra.pop("kenburns", False)), loop=bool(extra.pop("loop", False))))
                else:
                    if b.support is not None:
                        raise ValueError(f"beat {b.id} already has a photo card (a map_footage beat has one)")
                    b.support = Support(asset=r.get("asset", ""), t=t, place=r.get("place", ""), label=r.get("label", ""), hold=_f(r, "hold"))
                _no_more(extra)
            else:
                raise ValueError(f"row must be one of {', '.join(ROWS)} (got {kind!r})")
        except (ValueError, TypeError) as exc:
            problems.append(f"{at}: {exc.args[0] if exc.args else exc}")
            if kind == "beat" and r.get("beat"):
                failed_beats.add(r["beat"])
    if not beats and not problems:
        problems.append("the CSV has no beat rows")
    if problems:
        raise PlanError(problems)
    total = plan_duration if plan_duration is not None else duration
    # a beat with no end runs to where the next beat starts (the last one to the end of the narration)
    for i, n in open_ends.items():
        if i + 1 < len(beats):
            beats[i].end = beats[i + 1].start
        elif total is not None:
            beats[i].end = total
        else:
            problems.append(f"row {n}: the last beat needs an end (seconds), or load the CSV with the voiceover so the video's length is known")
        if beats[i].end <= beats[i].start:
            problems.append(f"row {n}: beat {beats[i].id} would end at {beats[i].end:.1f}s, not after it starts ({beats[i].start:.1f}s): "
                            f"the next beat's words come too soon, or are earlier in the script")
    for i, n, what, t in anchored:
        b = beats[i]
        if not (b.start - 1e-6 <= t < b.end - 1e-6):
            problems.append(f"row {n}: the {what} words are spoken at {t:.1f}s, outside beat {b.id} ({b.start:.1f}-{b.end:.1f}s): put the row under the beat it belongs to")
    if problems:
        raise PlanError(problems)
    plan = HybridPlan(duration=total if total is not None else beats[-1].end, beats=beats, settings=settings, version=version, chapters=chapters)
    if not any_camera and any(b.cam_place for b in beats):
        from .director import derive_cameras

        derive_cameras(plan)  # camera moves from each beat's target, clear of the footage dissolves (as for a Director plan)
    # the same checks a plan file gets when it is loaded: mode names, numbers and shapes
    HybridPlan.from_dict(plan.to_dict())
    return plan


def _f(r: Dict[str, str], col: str, required: bool = False) -> Optional[float]:
    v = r.get(col, "")
    if v == "":
        if required:
            raise ValueError(f"{col} is required")
        return None
    try:
        return float(v)
    except ValueError:
        raise ValueError(f"{col} must be a number of seconds or a value (got {v!r})") from None


def _opt(v: Any) -> Optional[float]:
    return None if v is None else float(v)


def _int_or_str(v: str) -> Any:
    try:
        return int(v)
    except ValueError:
        return v


def _no_more(extra: Dict[str, Any]) -> None:
    if extra:
        raise ValueError(f"the extra cell has {', '.join(sorted(extra))}, which this row cannot hold")
