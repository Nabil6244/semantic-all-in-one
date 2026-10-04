"""A Hybrid CSV (the format of composition_styles/hybrid_csv_prompt.txt: pakMap's columns with footage and photo-card rows) -> a HybridPlan.

The CSV says WHAT appears WHEN, row by row, tied to the narrator's words. pakMap's own compiler resolves every anchor and every layer's time;
this module re-reads that timeline as a Hybrid plan: each run of full-screen clips becomes a FOOTAGE beat, the stretches between them become MAP
beats (a map beat that has a photo card is a MAP+CARD beat), layers and camera moves go to the beat they fall in. After that it is an ordinary
plan: the Visual Tab, the validator, repair and the Hybrid renderer (map frozen under footage, dissolves, short clips slowed) all apply."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .narration import Word, words_between
from .plan import Beat, CameraStep, Clip, HybridPlan, Layer, Support, free_interval

SUPPORTED_LAYERS = ("hud_title", "marker", "zone_label", "fill", "line", "stat", "caption")
IGNORED_LAYERS = ("filmstrip", "sticker", "dots", "cluster", "value_overlay", "ghost_shape", "streak")
JOIN_GAP_S = 1.2        # footage clips closer than this are one footage beat
MIN_MAP_GAP_S = 1.0     # a gap between footage shorter than this is absorbed by the footage before it
MIN_CARD_SEGMENT_S = 3.0
DEFAULT_MOVE_S = 2.4
OPENING_MOVE_S = 2.2


class CsvImportError(ValueError):
    """The CSV cannot become a plan; .problems lists every issue with its row number."""

    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class CsvImport:
    plan: HybridPlan
    notes: List[str] = field(default_factory=list)      # what the importer decided (a layer moved off footage, a card skipped ...)
    warnings: List[str] = field(default_factory=list)   # the CSV compiler's own warnings, with row numbers


def _row_times(rows: Sequence[Any], words: Sequence[Word]) -> Dict[int, float]:
    """Each row's start time, resolved the way pakMap resolves it (narrator's words in order; offset_s; explicit t_start wins)."""
    from pakmap.anchor import Transcript

    tr = Transcript(list(words))
    cursor, out = 0, {}
    for r in rows:
        if r.t_start is not None:
            out[r.line] = r.t_start + r.offset_s
            continue
        if not r.vo_anchor or not len(tr):
            continue
        phrase, _, mod = r.vo_anchor.partition("|")
        hit = tr.find(phrase, cursor)
        if not hit:
            continue
        m, nxt = hit
        cursor = min(nxt, _first(tr, m))
        out[r.line] = max(0.0, (m.t_end if mod.strip().lower() == "end" else m.t_start) + r.offset_s)
    return out


def _first(tr: Any, m: Any) -> int:
    for i, (f, _l) in enumerate(tr._spans):
        if tr.words[f][1] >= m.t_start - 1e-9:
            return i
    return 0


def plan_from_csv(text: str, words: Sequence[Word], duration: Optional[float] = None, *, settings: Optional[Dict[str, Any]] = None) -> CsvImport:
    from pakmap.compile import CompileError, compile_rows
    from pakmap.schema import CsvError, parse_csv

    try:
        rows, parse_warnings = parse_csv("", text=text)
    except CsvError as exc:
        raise CsvImportError(list(exc.problems)) from exc
    try:
        res = compile_rows(rows, list(words), duration=duration, validate=False)
    except CompileError as exc:
        raise CsvImportError(list(exc.report.errors)) from exc
    if res.report.errors:
        raise CsvImportError(list(res.report.errors))
    total = float(res.spec["duration"])
    by_line = {r.line: r for r in rows}
    notes: List[str] = []
    warnings = list(parse_warnings) + list(res.report.warnings)

    # ---- the compiled events, with the CSV row each came from --------------------------------------------------------------
    clips, cards, layers = [], [], []
    for e in res.report.events:
        row = by_line.get(e.row)
        if row is None:
            continue
        if e.type == "media_full":
            clips.append((e, row))
        elif e.type == "pip":
            cards.append((e, row))
        elif e.type in SUPPORTED_LAYERS:
            layers.append((e, row))
        elif e.type in IGNORED_LAYERS:
            notes.append(f"row {e.row}: a {e.type} is not supported in Hybrid plans yet, so it was left out")
    clips.sort(key=lambda x: x[0].t_in)
    cards.sort(key=lambda x: x[0].t_in)
    layers.sort(key=lambda x: (x[0].t_in, x[0].row))

    # ---- footage windows: runs of clips that follow each other ---------------------------------------------------------------
    windows: List[Dict[str, Any]] = []
    for e, row in clips:
        if windows and e.t_in - windows[-1]["end"] < JOIN_GAP_S:
            w = windows[-1]
            if e.t_in < w["end"]:
                notes.append(f"row {e.row}: this clip started before the previous one ended; the previous clip was shortened to hand over")
            w["clips"].append((e, row))
            w["end"] = max(w["end"], e.t_out)
        else:
            windows.append({"start": e.t_in, "end": e.t_out, "clips": [(e, row)]})
    for a, b in zip(windows, windows[1:]):      # a gap too short to be a map beat belongs to the footage before it
        if 0 < b["start"] - a["end"] < MIN_MAP_GAP_S:
            notes.append(f"the {b['start'] - a['end']:.1f}s between two footage beats was absorbed by the first")
            a["end"] = b["start"]
    if windows and windows[0]["start"] < MIN_MAP_GAP_S and windows[0]["start"] > 0:
        windows[0]["start"] = 0.0
    if windows and total - windows[-1]["end"] < MIN_MAP_GAP_S:
        windows[-1]["end"] = total

    # ---- beat skeleton: footage windows and the map gaps between them --------------------------------------------------------
    segments: List[Tuple[str, float, float, Any]] = []
    t = 0.0
    for w in windows:
        if w["start"] - t > 0.05:
            segments.append(("gap", t, w["start"], None))
        segments.append(("footage", w["start"], w["end"], w))
        t = w["end"]
    if total - t > 0.05:
        segments.append(("gap", t, total, None))
    if not segments:
        segments.append(("gap", 0.0, total, None))

    skeleton: List[Tuple[str, float, float, Any]] = []
    for kind, a, b, w in segments:
        if kind == "footage":
            skeleton.append((kind, a, b, w))
            continue
        inside = [(e, r) for e, r in cards if a - 1e-6 <= e.t_in < b - 1e-6]
        cuts = [a]
        for e, r in inside[1:]:
            if e.t_in - cuts[-1] >= MIN_CARD_SEGMENT_S and b - e.t_in >= MIN_CARD_SEGMENT_S:
                cuts.append(e.t_in)
            else:
                notes.append(f"row {e.row}: a second photo card within {MIN_CARD_SEGMENT_S:g}s of another cannot get a map beat of its own, so it was left out")
        cuts.append(b)
        used = {id(x) for x in []}
        for i in range(len(cuts) - 1):
            lo, hi = cuts[i], cuts[i + 1]
            card = next(((e, r) for e, r in inside if lo - 1e-6 <= e.t_in < hi - 1e-6), None)
            skeleton.append(("map_footage" if card else "map", lo, hi, card))

    beats: List[Beat] = []
    for i, (kind, a, b, extra) in enumerate(skeleton):
        bid = f"b{i + 1}"
        narration = " ".join(w[0] for w in words_between(words, a, b))
        beat = Beat(id=bid, mode="footage" if kind == "footage" else kind, start=round(a, 3), end=round(b, 3), narration=narration, confidence=1.0)
        if kind == "footage":
            cl = extra["clips"]
            for k, (e, row) in enumerate(cl):
                nxt = cl[k + 1][0].t_in if k + 1 < len(cl) else None
                asset = row.asset_path.strip()
                still = asset.split(":", 1)[0].lower() in ("stock_image", "flow_image") or asset.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                beat.clips.append(Clip(asset=asset, dur=None, kenburns=still, reason=""))
            if len(beat.clips) > 1:
                # clips follow each other: give each the time from its start to the next one's start (plus the dissolve the compiler adds)
                x = float((settings or {}).get("dissolve_s", 0.5))
                for k in range(len(beat.clips) - 1):
                    beat.clips[k].dur = round(cl[k + 1][0].t_in - cl[k][0].t_in + x, 3)
            first_row = cl[0][1]
            beat.footage_intent = (first_row.asset_path.split(":", 1)[-1] or "footage").strip()[:90]
            beat.purpose = "footage from the CSV"
        else:
            if kind == "map_footage" and extra is not None:
                e, row = extra
                beat.support = Support(asset=row.asset_path.strip(), t=round(max(e.t_in, a + 0.2), 3), place=row.geo_ref, label=(row.label_text or "").upper(),
                                       hold=round(max(1.0, e.t_out - e.t_in), 3))
            beat.purpose = "map from the CSV"
        beats.append(beat)

    plan = HybridPlan(duration=round(total, 3), beats=beats, settings=dict(settings or {}))

    # ---- layers go to the map beat they fall in (never under footage) -------------------------------------------------------
    def beat_at(t: float) -> Optional[int]:
        for i, b in enumerate(beats):
            if b.start - 1e-6 <= t < b.end - 1e-6:
                return i
        return len(beats) - 1 if beats and t >= beats[-1].end - 1e-6 else None

    for e, row in layers:
        i = beat_at(e.t_in)
        t_in = e.t_in
        if i is None:
            continue
        if beats[i].mode == "footage":
            j = next((k for k in range(i + 1, len(beats)) if beats[k].mode != "footage"), None)
            if j is None:
                notes.append(f"row {e.row}: the {e.type} would appear under footage at the end of the video, so it was left out")
                continue
            t_in = beats[j].start + 0.3
            notes.append(f"row {e.row}: the {e.type} {e.id!r} would have appeared under footage; it now appears just after it, at {t_in:.1f}s")
            i = j
        lay = Layer(id=e.id, type=e.type, t=round(t_in, 3))
        if e.type == "hud_title":
            lay.label, lay.sub = row.label_text, row.sub_text
        elif e.type in ("marker", "zone_label"):
            lay.place, lay.label, lay.sub, lay.role = row.geo_ref, row.label_text, row.sub_text, row.color_role
        elif e.type == "fill":
            lay.place, lay.role = row.geo_ref, row.color_role
        elif e.type == "line":
            lay.places = [p.strip() for p in row.geo_ref.split(";") if p.strip()]
            lay.kind = row.line_kind or "flow"
        elif e.type == "stat":
            lay.value_from, lay.value_to, lay.format, lay.sub, lay.anchor = row.value_from, row.value_to, row.value_format, row.sub_text, (row.anchor or "br")
        elif e.type == "caption":
            lay.text, lay.anchor = row.label_text, (row.anchor or "bc")
        # how long it stays, in the CSV's own terms: until the second pakMap ended it (clipped to its item); Hybrid then holds it past footage as it does for any layer
        lay.until = "end" if e.t_out >= total - 0.05 else round(max(e.t_out, lay.t + 1.0), 3)
        beats[i].layers.append(lay)

    # ---- camera ------------------------------------------------------------------------------------------------------------
    times = _row_times(rows, words)
    steps: List[CameraStep] = []
    for r in rows:
        if r.layer_type != "camera" or not r.camera_action or r.camera_action == "drift":
            continue
        t0 = times.get(r.line)
        if t0 is None:
            t0 = 0.0 if r.camera_action == "start" else None
        if t0 is None:
            warnings.append(f"row {r.line}: the camera row has no vo_anchor, so it was left out")
            continue
        place = r.geo_ref or (f"{r.lat},{r.lon}" if r.lat is not None and r.lon is not None else "")
        if r.camera_action in ("start", "fly_to") and not place:
            warnings.append(f"row {r.line}: the camera {r.camera_action} has no geo_ref, so it was left out")
            continue
        frame = r.frame or ("country" if r.camera_action in ("start", "fly_to") else "")
        dur = r.camera_dur
        if r.camera_action == "fly_to" and dur is None:
            dur = OPENING_MOVE_S if t0 < 3.0 else DEFAULT_MOVE_S
        if r.camera_action in ("push_in", "pull_back") and dur is None:
            dur = 6.0
        steps.append(CameraStep(action=r.camera_action, place=place, frame=frame, t=round(t0, 3), dur=dur, zoom_delta=0.6 if r.camera_action == "push_in" else None))
    steps.sort(key=lambda s: s.t)
    starts = [s for s in steps if s.action == "start"]
    if len(starts) > 1:
        for s in starts[1:]:
            s.action = "fly_to"
            s.dur = s.dur or DEFAULT_MOVE_S
            notes.append("more than one camera start: the later ones became fly_to moves")
    if not starts:
        first = next((s for s in steps if s.place), None)
        place = first.place if first else next((l.place for b in beats for l in b.layers if l.place), "")
        if place:
            steps.insert(0, CameraStep(action="start", place=place, frame=(first.frame if first and first.frame else "country"), t=0.0))
            notes.append(f"the CSV has no camera start; the video opens on {place}")
    elif starts[0].t > 0.0:
        starts[0].t = 0.0
    # each step goes into a map beat, clear of the footage dissolves; steps never overlap
    last_end: Dict[int, float] = {}
    for s in steps:
        i = beat_at(s.t)
        if i is None:
            continue
        if beats[i].mode == "footage":
            j = next((k for k in range(i + 1, len(beats)) if beats[k].mode != "footage"), None)
            if j is None:
                notes.append(f"the camera {s.action} at {s.t:.1f}s would be under footage at the end, so it was left out")
                continue
            i = j
        lo, hi = free_interval(plan, i)
        t = max(s.t, lo + (0.3 if s.action != "start" else 0.0), last_end.get(i, lo))
        if s.action == "start":
            t = max(0.0, min(s.t, beats[i].start))
        if t > hi - 0.4 and s.action != "start":
            notes.append(f"the camera {s.action} to {s.place} had no room in its beat and was left out")
            continue
        if s.dur is not None:
            s.dur = round(max(0.8, min(float(s.dur), hi - t - 0.2)), 3) if s.action != "start" else s.dur
        s.t = round(t, 3)
        beats[i].camera.append(s)
        last_end[i] = s.t + (s.dur or 0.0) + 0.1

    for b in beats:
        if b.mode != "footage":
            places = [c.place for c in b.camera if c.place]
            titles = [l.label for l in b.layers if l.type == "hud_title" and l.label]
            b.geo_intent = (titles[0] if titles else "") or (b.layers[0].label if b.layers and b.layers[0].label else "") or (places[-1] if places else "") or "map"
    return CsvImport(plan=plan, notes=notes, warnings=warnings)
