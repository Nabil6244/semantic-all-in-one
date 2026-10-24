"""Director options (all defaults are provisional and live here, in one place)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

EXPLAINER_VERSION = 1            # part of every board-clip cache key: bump when drawing or authoring rules change


@dataclass
class DirectorOptions:
    # ---- pacing (scorecard T02 to T05; provisional) ----
    min_beat_s: float = 3.2             # close a beat once it is at least this long
    max_beat_s: float = 8.0             # never longer (a longer sentence is split at its longest pause)
    split_over_s: float = 6.4           # a sentence longer than this is split in two at its longest pause near the middle
    max_still_s: float = 2.0            # the longest a board may sit without a change (repair adds a card, else a caption)
    narrator_every_s: float = 30.0      # the narrator is back at least this often
    narrator_share: float = 0.45        # the narrator starts a new run while its share of the runtime so far is below this (runs of at least 2 beats overshoot it a little; scorecard target 35 to 60%)
    # ---- mix ----
    max_map_share: float = 0.30
    max_archive_share: float = 0.12
    map_min_beat_s: float = 2.8
    narrator: bool = True
    footage_share: float = 0.0          # 0 = none (the default). Otherwise the largest share of the runtime board beats may be turned into FOOTAGE beats: a source and a query for the application's own "Get the scenes" step
    footage_source: str = "stock_video"  # stock_video | youtube_video | flow_video | stock_image | flow_image: which of the application's sources the references name (the Visual Plan lets you change a row)
    background: str = "paper"           # grey (the reference's flat board) | paper | grid | warm: light textures behind the board; every earlier look used grey
    narrator_style: str = "serious"     # serious | cartoon (the original round-faced explorer)
    cartoon_share: float = 0.0          # 0 = no cartoon beats (the default: nothing changes); otherwise the largest share of the runtime that board beats may be turned into cartoon beats (scene set, cast, one prop; no narrator)
    look: str = "reference"             # "reference": large picture tiles, boxes, titles and typed lines (schema v1.3); "classic": the cream cards of Milestones 1 to 4a (kept, unchanged)
    # ---- plan ----
    dissolve_s: float = 0.0             # 0 = hard cuts everywhere (the reference); 0.5 = Hybrid's dissolve everywhere. Plan-wide in Hybrid
    fps: int = 30
    size: Tuple[int, int] = (1920, 1080)
    # ---- inputs the caller may supply ----
    places: List[str] = field(default_factory=list)          # place names to look for in the narration (besides capitalised script words)
    fallback_place: str = "Europe"                           # the mandatory opening map when no place is spoken (arbitrary: a warning says so)
    archive_dir: Optional[str] = None                        # folder with archive.json: [{"file", "subjects": [...], "reason"}]
    metaphors: Dict[str, str] = field(default_factory=dict)  # keyword -> icon:/prop: asset, added to the default table
    roles: Dict[str, str] = field(default_factory=dict)      # keyword -> colour role (blue green gold red), added to the default table
    work_dir: Optional[str] = None                           # where board clips are written (cached by content hash)
