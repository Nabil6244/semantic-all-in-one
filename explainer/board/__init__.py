"""Word-timed grey-board clip builder (feasibility stage; placeholder look, no narrator, no font decision)."""
from .builder import BoardBuild, build_board_clip, clip_geometry
from .cues import BoardCueError, Cue, ResolvedCue, resolve_cues, sentence_spans
from .splice import SpliceResult, splice_board_beats

__all__ = ["BoardBuild", "BoardCueError", "Cue", "ResolvedCue", "SpliceResult", "build_board_clip", "clip_geometry", "resolve_cues", "sentence_spans",
           "splice_board_beats"]
