"""build_board_clip: word-timed cues in, one grey-board clip and a Hybrid plan fragment out.

    build = build_board_clip(cues, words, beat_start=9.0, beat_end=17.0, out_path=..., dissolve_s=0.0)
    build.plan_fragment   {"beat": {... "mode": "footage", "footage": {"clips": [{"asset": <clip>}]}}, "settings": {"dissolve_s": ...}}

Timing model (measured in the Phase 1 spike, docs/explainer/explainer_spike_report.md):
  * hard cut (dissolve_s = 0): the clip is exactly the beat, clip second 0 is the beat start;
  * dissolve (dissolve_s > 0): Hybrid shows the footage from beat start - dissolve_s/2 to beat end + dissolve_s/2, so the clip is
    beat + dissolve_s long and clip second 0 is beat start - dissolve_s/2. Cues are mapped with that origin.

This module imports nothing from the application. The plan fragment is plain data; the caller (the spike's verification script today, an
integration later) puts it into a HybridPlan."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .cues import SCHEMA_VERSION, BoardCueError, Cue, ResolvedCue, Word, resolve_cues
from ..narrator.timeline import NarratorTrack, build_track
from .render import Item, encode, layout

DEFAULT_FONT = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Inter-Bold.ttf"   # a placeholder face so text can be drawn; NOT a font choice


@dataclass
class BoardBuild:
    clip_path: Path
    clip_origin_s: float
    clip_length_s: float
    n_frames: int
    fps: int
    size: Tuple[int, int]
    instrument: bool
    resolved: List[ResolvedCue]
    items: List[Item]
    problems: List[str]
    plan_fragment: Dict[str, Any]
    manifest_path: Optional[Path] = None
    tail_frames: int = 0
    narrator: Optional[NarratorTrack] = None

    def manifest(self) -> Dict[str, Any]:
        bb = {it.cue_id: list(it.bbox) for it in self.items}
        cues = []
        for r in self.resolved:
            d = r.to_dict()
            d["bbox"] = bb.get(r.cue.id)
            d["planned_video_frame"] = None if r.onset_abs is None else math.ceil(round(r.onset_abs * self.fps, 6) - 1e-9)
            cues.append(d)
        return {"schema_version": ("1.4" if any(r.cue.kind == "visual" and (r.cue.params or {}).get("style") in ("set", "figure", "crowd", "prop") and not r.problems for r in self.resolved) else "1.3" if any(r.cue.kind == "visual" and not r.problems for r in self.resolved) else "1.2" if any(r.cue.kind == "caption" and not r.problems for r in self.resolved) else "1.1" if self.narrator is not None else SCHEMA_VERSION), "clip": str(self.clip_path), "clip_origin_s": self.clip_origin_s, "clip_length_s": self.clip_length_s, "n_frames": self.n_frames, "fps": self.fps,
                "size": list(self.size), "instrument": self.instrument, "tail_frames": self.tail_frames, "problems": self.problems, "cues": cues, "plan_fragment": self.plan_fragment, **({"narrator": self.narrator.summary()} if self.narrator is not None else {})}


def clip_geometry(beat_start: float, beat_end: float, dissolve_s: float) -> Tuple[float, float]:
    """(clip origin in narration seconds, clip length in seconds)."""
    if dissolve_s and dissolve_s > 0:
        return beat_start - dissolve_s / 2.0, (beat_end - beat_start) + dissolve_s
    return beat_start, beat_end - beat_start


def build_board_clip(cues: Sequence[Cue], words: Sequence[Word], beat_start: float, beat_end: float, out_path: "str | Path", *, dissolve_s: float = 0.0,
                     fps: int = 30, size: Tuple[int, int] = (1920, 1080), instrument: bool = False, strict: bool = True, beat_id: str = "board",
                     purpose: str = "", font_path: "str | Path | None" = None, manifest_path: "str | Path | None" = None,
                     sentences: Optional[Sequence[Tuple[float, float]]] = None, tail_frames: int = 0) -> BoardBuild:
    """Resolve the cues against `words`, draw the clip, write it to `out_path`.

    strict=True  (default): any cue problem raises BoardCueError before anything is drawn (nothing is guessed).
    strict=False: a cue with a problem is left out and listed in `problems`; the clip is still made (the never-stop behaviour)."""
    if beat_end <= beat_start:
        raise BoardCueError([f"the beat ends ({beat_end}) before it starts ({beat_start})"])
    origin, length = clip_geometry(beat_start, beat_end, dissolve_s)
    n_frames = int(round(length * fps)) + max(0, int(tail_frames))   # tail frames: spare frames after the beat, in case the pipeline's slot is a frame longer than the beat
    resolved = resolve_cues(cues, words, beat_start, beat_end, origin, fps, length, sentences)
    font = str(font_path) if font_path else None            # None = the Phase 1 board theme; a path = the legacy placeholder look
    track = build_track(resolved, words, origin, length, fps, beat_id, tail_frames)   # narrator timeline (adds problems to narrator cues; None without a narrator)
    items = layout(resolved, font, fps, narrator=track)                      # pure: may add layout problems (no free slot, text too long, ...) to the cues; draws nothing
    problems = [p for r in resolved for p in r.problems]
    if problems and strict:
        raise BoardCueError(problems)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rc = encode(items, n_frames, fps, size, out_path, font, instrument, track)
    if rc != 0:
        raise RuntimeError(f"ffmpeg could not encode the board clip (exit {rc})")
    fragment = {"beat": {"id": beat_id, "mode": "footage", "start": beat_start, "end": beat_end, "purpose": purpose or "board clip",
                         "footage": {"clips": [{"asset": str(out_path), "reason": "Explainer board clip, word-timed"}]}},
                "settings": {"dissolve_s": float(dissolve_s)}}
    build = BoardBuild(out_path, origin, length, n_frames, fps, size, instrument, resolved, items, problems, fragment, tail_frames=max(0, int(tail_frames)), narrator=track)
    if manifest_path:
        build.manifest_path = Path(manifest_path)
        build.manifest_path.write_text(json.dumps(build.manifest(), indent=1, sort_keys=True))
    return build
