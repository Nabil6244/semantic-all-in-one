"""Dry build of a board beat: cue resolution, narrator track and layout, without drawing or encoding. Used by the director as its gate (same code path as build_board_clip)."""

from __future__ import annotations

from typing import List, Sequence, Tuple

from ..narrator.timeline import build_track
from .builder import clip_geometry
from .cues import Cue, ResolvedCue, Word, resolve_cues
from .render import Item, layout


def dry_build(cues: Sequence[Cue], words: Sequence[Word], beat_start: float, beat_end: float, *, dissolve_s: float = 0.0, fps: int = 30,
              beat_id: str = "board", sentences=None) -> Tuple[List[str], List[ResolvedCue], List[Item]]:
    """(problems, resolved cues, layout items). Never raises for a bad cue: problems are returned."""
    origin, length = clip_geometry(beat_start, beat_end, dissolve_s)
    resolved = resolve_cues(cues, words, beat_start, beat_end, origin, fps, length, sentences)
    track = build_track(resolved, words, origin, length, fps, beat_id)
    items = layout(resolved, None, fps, narrator=track)
    return [p for r in resolved for p in r.problems], resolved, items
