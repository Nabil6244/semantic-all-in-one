"""Plan-level splice: turn chosen footage beats of a Hybrid plan (as plain data) into word-timed board beats.

    result = splice_board_beats(plan_dict, [{"beat_id": "b2", "cues": [...]}, ...], words, out_dir, sentences=..., dissolve_s=0.0)
    result.plan        a new plan dict (the input is not modified)
    result.builds      one BoardBuild per board beat
    result.notes       things the caller should know (never errors)
    result.problems    why something was left out (only when strict=False; strict=True raises BoardCueError first)

Pure data in, pure data out: this module imports nothing from the application and nothing protected. Pass `validate` (a callable that takes the
new plan dict and returns a list of problem strings, for example one built on hybrid.plan.validate_plan) to have the result checked.

Rules, each tested in explainer/spike/verify_splice.py:
  * only a beat whose mode is "footage" can become a board beat (a map beat's layers would be lost, so it is refused, not converted);
  * nothing is drawn until EVERY spec resolves (in strict mode a bad cue anywhere stops the whole splice before any clip is encoded);
  * `dissolve_s` is the plan-wide Hybrid setting: it is read from the plan (or given), applied to the board geometry, and a note says that it
    also governs every other footage join in the plan;
  * the plan's other beats are copied unchanged."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from .builder import BoardBuild, build_board_clip, clip_geometry
from .cues import BoardCueError, Cue, Word, resolve_cues
from ..narrator.timeline import build_track
from .render import layout


@dataclass
class SpliceResult:
    plan: Dict[str, Any]
    builds: List[BoardBuild]
    notes: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)


def _cues(raw: Sequence[Union[Cue, Dict[str, Any]]]) -> List[Cue]:
    return [c if isinstance(c, Cue) else Cue.from_dict(c) for c in raw]


def splice_board_beats(plan: Dict[str, Any], specs: Sequence[Dict[str, Any]], words: Sequence[Word], out_dir: "str | Path", *,
                       sentences: Optional[Sequence[Tuple[float, float]]] = None, dissolve_s: Optional[float] = None, fps: int = 30,
                       size: Tuple[int, int] = (1920, 1080), instrument: bool = False, strict: bool = True, tail_frames: int = 0,
                       validate: Optional[Callable[[Dict[str, Any]], List[str]]] = None, font_path: "str | Path | None" = None) -> SpliceResult:
    out_dir = Path(out_dir)
    new = copy.deepcopy(plan)
    settings = new.setdefault("settings", {})
    if dissolve_s is None:
        if "dissolve_s" not in settings:
            raise BoardCueError(["the plan does not set dissolve_s: pass it explicitly (0 = hard cuts, 0.5 = Hybrid's default dissolve)"])
        dissolve_s = float(settings["dissolve_s"])
    dissolve_s = float(dissolve_s)
    beats = {b.get("id"): b for b in new.get("beats", [])}
    notes: List[str] = []
    problems: List[str] = []
    todo: List[Tuple[Dict[str, Any], Dict[str, Any], List[Cue], Tuple[float, float]]] = []
    seen = set()
    for spec in specs:
        bid = spec.get("beat_id")
        if bid in seen:
            problems.append(f"beat {bid}: listed twice")
            continue
        seen.add(bid)
        beat = beats.get(bid)
        if beat is None:
            problems.append(f"beat {bid}: not in the plan")
            continue
        if beat.get("mode") != "footage":
            problems.append(f"beat {bid}: mode is {beat.get('mode')!r}; only a footage beat can become a board beat (a map beat's layers would be lost)")
            continue
        start, end = float(beat["start"]), float(beat["end"])
        if end <= start:
            problems.append(f"beat {bid}: ends before it starts")
            continue
        cues = _cues(spec.get("cues", []))
        origin, length = clip_geometry(start, end, dissolve_s)
        res = resolve_cues(cues, words, start, end, origin, fps, length, sentences)
        track = build_track(res, words, origin, length, fps, str(bid))
        layout(res, font_path and str(font_path), fps, narrator=track)          # pure: adds layout problems (slots, text fit, collisions) before anything is drawn
        for r in res:
            problems += [f"beat {bid}: {p}" for p in r.problems]
        todo.append((spec, beat, cues, (start, end)))
    if problems and strict:
        raise BoardCueError(problems)
    builds: List[BoardBuild] = []
    for spec, beat, cues, (start, end) in todo:
        bid = beat["id"]
        b = build_board_clip(cues, words, start, end, out_dir / f"{bid}_board.mp4", dissolve_s=dissolve_s, fps=fps, size=size, instrument=instrument,
                             strict=False, beat_id=bid, purpose=str(spec.get("purpose") or beat.get("purpose") or "board clip"), font_path=font_path,
                             manifest_path=out_dir / f"{bid}_board_manifest.json", sentences=sentences, tail_frames=tail_frames)
        builds.append(b)
        frag = b.plan_fragment["beat"]
        beat["footage"] = frag["footage"]
        beat["purpose"] = frag["purpose"]
        if b.resolved and b.resolved[0].sentence_source:
            notes.append(f"beat {bid}: sentence boundaries from {b.resolved[0].sentence_source}")
        notes += [f"beat {bid}: {p}" for p in b.problems if f"beat {bid}: {p}" not in problems]
    settings["dissolve_s"] = dissolve_s
    other_footage = [b["id"] for b in new.get("beats", []) if b.get("mode") == "footage" and b["id"] not in {x[1]["id"] for x in todo}]
    if dissolve_s == 0 and other_footage:
        notes.append(f"dissolve_s is 0 for the whole plan: the footage beats that are not board beats ({', '.join(other_footage)}) also cut instead of dissolving")
    if dissolve_s > 0:
        notes.append(f"dissolve_s is {dissolve_s}: each board clip is its beat plus {dissolve_s} s long and its first and last {dissolve_s / 2} s sit under the dissolve")
    if validate is not None:
        for p in validate(new):
            problems.append(f"validate: {p}")
        if problems and strict:
            raise BoardCueError(problems)
    return SpliceResult(new, builds, notes, problems)
