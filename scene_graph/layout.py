"""Deterministic layout: SceneGraph (semantic intent) -> TIME-SCOPED canvas geometry.

This is a timed editorial composition, not a mind-map/storyboard renderer: the
fixed 1920x1080 canvas never changes size, but WHAT'S ON IT changes over time.
Nodes are grouped into narrative "chapters" — connected components of the
causal edge graph, in narration order (isolated nodes are their own
one-member chapter) — and only one chapter's nodes are ever meant to be on
screen at once. A chapter's members occupy the SAME small set of screen
positions ("slots") that every other chapter reuses, since chapters never
overlap in time; positions are deliberate/diagonal per slot-count (1, 2 or 3
slots), never a uniform grid. A chapter with more members than the active
cap slides: member i is evicted once that many later chapter-mates have
appeared, so at most ``compute_layout``'s ``max_active_per_chapter``
members of any one chapter are ever simultaneously visible. Defaults to 3
(module ``MAX_ACTIVE_PER_CHAPTER``) — Overscaled's own, unchanged behavior.
A style that needs a 4-in-a-row beat (Exp Solar's ``four_row``) passes 4
explicitly; only a 1/2/3/4-slot template exists for that general cap, so
it is still never a free-form grid. The one deliberate exception is Exp
Solar's ``index_grid`` beat: a chapter whose own edges are tagged
kind="group_grid" always gets a real, fixed 3x5 grid (``SLOT_TEMPLATE_GRID_15``)
regardless of the style's general cap — a one-time index/menu board, not
a wider row.

Each node still gets exactly ONE fixed ``NodeRect`` for its entire life (it
never moves while visible — only appears/holds/disappears), so nothing
downstream (scene_graph.render/composition) needs to know about chapters at
all; they just also read this module's new ``active_windows`` to know when
that fixed rect is actually on screen.

``anchor`` nodes are excluded from chaptering entirely: pinned to a fixed
corner and visible for the whole segment once introduced, matching their own
persistent-identifier semantics (see scene_graph/overscaled_csv.py).

No LLM, no randomness: same SceneGraph + same resolved_media -> byte-identical
layout every time.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .schema import SceneGraph, SceneNode

DEFAULT_CANVAS_WIDTH = 1920
DEFAULT_CANVAS_HEIGHT = 1080
MARGIN_PX = 60  # outer canvas margin
GUTTER_PX = 48  # spacing reserved between anchors / anchor band and the stage
ANCHOR_SIZE_PX = 160  # a small corner icon, not a content card — kept modest so it doesn't eat stage space
TITLE_BAND_PX = 130  # vertical room reserved at the top when the segment has any TitleCue
# Exp Solar's persistent checklist header strip only (scene_graph.exp_solar_csv's
# beat="checklist" — see _CHECKLIST_ITEM_TYPE below). Reserved ABOVE the
# anchor/title bands (it is the topmost element) only when the SceneGraph
# actually has any "checklist_item" nodes — zero for Overscaled and for
# every other Exp Solar beat, so this never shifts anything by default.
CHECKLIST_BAND_PX = 110
_CHECKLIST_ITEM_TYPE = "checklist_item"
# A run of checklist_item nodes longer than this many is impossible to
# reach today — scene_graph.exp_solar_csv caps a CSV's own checklist beat
# count at this same number before it ever reaches compute_layout — but
# the layout itself never hard-fails on more; the strip just gets one
# narrower cell per extra item.
CHECKLIST_MAX_ITEMS = 15

# At most this many members of one chapter (connected component) are ever
# simultaneously visible. Matches the real "Overscaled" reference footage,
# which routinely holds 3 cards on screen at once (a hero image plus two
# supporting ones) as long as they stay LOCAL — close together, short
# connectors — rather than pushed into far opposite corners. See the
# asymmetric 3-slot template below, which keeps a tight triangular
# footprint instead of a wide corner-to-corner spread.
MAX_ACTIVE_PER_CHAPTER = 3
# At most this many causal arrows are ever simultaneously visible, globally —
# an arrow is a brief "look at this connection" callout, not a permanent
# fixture; it hard-cuts away once enough newer ones have been drawn. Matches
# MAX_ACTIVE_PER_CHAPTER - 1: a chain of N simultaneous cards needs at most
# N-1 connectors to link them.
MAX_ACTIVE_EDGES = 2
MIN_HOLD_S = 1.5  # a node always gets at least this much screen time

# Deliberate slot centers + box size, as fractions of the stage rect, keyed
# by how many slots are in play (1, 2 or 3 — see MAX_ACTIVE_PER_CHAPTER).
#
# SINGLE HORIZONTAL ROW, not a 2D grid or diagonal spread: the stage itself
# is wide-but-short (a 1920x1080 canvas minus margins/anchor/title bands —
# roughly 2:1 in practice), so a box tall enough to also stack vertically
# ends up starved of the height it needs after the caption/label reserves
# are subtracted — a real bug: those reserves used to be a FRACTION of
# box_h (CAPTION_RESERVE_FRAC), which shrinks disproportionately for a
# short box, so a typical 16:9 photo ended up height-constrained and used
# as little as 17-30% of its box's actual width. Fixed two ways: (1) the
# caption reserve is now a FIXED pixel amount (CAPTION_RESERVE_PX, same
# convention as LABEL_RESERVE_PX) so it no longer scales down with a
# shorter box, and (2) every box here uses nearly the FULL stage height in
# one row, sized so a typical landscape source (~1.6 aspect) is
# width-constrained (fills the box's width) rather than height-constrained
# (stranded with empty side margins).
#
# Two variants per slot count, chosen once per chapter (see
# _choose_template_variant): SYMMETRIC (equal-sized slots) when no member
# has an elevated role, WEIGHTED (one wider "hero" slot) when one does —
# see _ELEVATED_ROLE_KEYWORDS. 1 slot has only one sensible shape either way.
_SLOT_TEMPLATES_SYMMETRIC: Dict[int, List[Tuple[float, float, float, float]]] = {
    1: [(0.50, 0.50, 0.98, 0.97)],
    2: [(0.235, 0.50, 0.47, 0.90), (0.765, 0.50, 0.47, 0.90)],
    3: [
        (0.155, 0.50, 0.31, 0.90),
        (0.500, 0.50, 0.31, 0.90),
        (0.845, 0.50, 0.31, 0.90),
    ],
    # 4-in-a-row (Exp Solar's "four_row" beat only — see
    # exp_solar_csv.SUPPORTED_BEATS and compute_layout's own
    # max_active_per_chapter param below; Overscaled's own
    # MAX_ACTIVE_PER_CHAPTER=3 default never reaches a 4-member chapter,
    # so this entry is simply unused dead data for the default style).
    # Four equal columns, same full-height single-row shape as 1/2/3 above.
    4: [
        (0.125, 0.50, 0.22, 0.90),
        (0.375, 0.50, 0.22, 0.90),
        (0.625, 0.50, 0.22, 0.90),
        (0.875, 0.50, 0.22, 0.90),
    ],
}
_SLOT_TEMPLATES_WEIGHTED: Dict[int, List[Tuple[float, float, float, float]]] = {
    1: [(0.50, 0.50, 0.98, 0.97)],
    2: [
        (0.71, 0.50, 0.58, 0.90),  # hero: right, wider
        (0.18, 0.50, 0.36, 0.90),  # supporting: left
    ],
    3: [
        (0.79, 0.50, 0.42, 0.90),  # hero: right, widest
        (0.13, 0.50, 0.26, 0.90),  # supporting: left
        (0.42, 0.50, 0.26, 0.90),  # supporting: middle
    ],
    # No hero-weighted 4-row variant defined by the reference (a four_row
    # beat is a set of visual peers, e.g. recolored copies of one asset —
    # never a hero + 3 supporting shot) — reuse the symmetric shape so
    # _slot_rect never KeyErrors if a role happens to be elevated anyway.
    4: [
        (0.125, 0.50, 0.22, 0.90),
        (0.375, 0.50, 0.22, 0.90),
        (0.625, 0.50, 0.22, 0.90),
        (0.875, 0.50, 0.22, 0.90),
    ],
}
# Slot index 0 is always the "hero" (widest) slot in the WEIGHTED variant —
# _slot_assignment_order below puts whichever member has an elevated role
# there, regardless of arrival order.
_HERO_SLOT_INDEX = 0

# A member whose CSV `role` column contains one of these (case-insensitive
# substring) is treated as the chapter's visual lead and preferentially
# gets the widest ("hero") slot when a WEIGHTED template is in play — the
# user's own examples ("a hero or proof visual can receive more space").
# No new CSV field: reuses the existing role -> SceneNode.semantic_role
# column verbatim.
_ELEVATED_ROLE_KEYWORDS = ("hero", "proof", "subject", "establisher")


def _is_elevated_role(node: SceneNode) -> bool:
    role = str(node.semantic_role or "").lower()
    return any(keyword in role for keyword in _ELEVATED_ROLE_KEYWORDS)


def _choose_template_variant(members: List[SceneNode]) -> Dict[int, List[Tuple[float, float, float, float]]]:
    """WEIGHTED (one wider hero slot) if any member of this chapter has an
    elevated role; SYMMETRIC (equal slots) otherwise. A simple, cheap,
    deterministic choice — not a numeric optimizer — made ONCE per chapter."""
    return _SLOT_TEMPLATES_WEIGHTED if any(_is_elevated_role(n) for n in members) else _SLOT_TEMPLATES_SYMMETRIC


def _slot_assignment_order(members: List[SceneNode]) -> List[SceneNode]:
    """The order members fill slot indices 0, 1, 2, ... in. Elevated-role
    members sort first (so one of them lands in slot 0 == the WEIGHTED
    template's hero slot); everyone else keeps their original chronological
    (appear_at) order. When no member is elevated this is a no-op — the
    same order compute_layout already sorted ``members`` into — so chapters
    without role signals render identically to before."""
    indexed = sorted(enumerate(members), key=lambda pair: (0 if _is_elevated_role(pair[1]) else 1, pair[0]))
    return [node for _, node in indexed]


def _peak_concurrent(windows: List[Tuple[float, float]]) -> int:
    """Max number of ``windows`` (half-open [start, end) intervals) ever
    simultaneously active — a cheap O(n log n) sweep-line event count, run
    ONCE per chapter (never per frame) to size that chapter's template to
    how crowded it actually gets, not just its raw member count."""
    if not windows:
        return 0
    events: List[Tuple[float, int]] = []
    for start, end in windows:
        events.append((start, 1))
        events.append((end, -1))
    # Ties: process an END before a START at the same instant, so two
    # merely-touching windows don't get counted as overlapping.
    events.sort(key=lambda ev: (ev[0], ev[1]))
    current = peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


@dataclasses.dataclass
class NodeRect:
    node_id: str
    x: float
    y: float
    width: float
    height: float

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> Tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    def to_dict(self) -> dict:
        return {"node_id": self.node_id, "x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: dict) -> "NodeRect":
        return cls(
            node_id=str(data.get("node_id") or ""),
            x=float(data.get("x") or 0.0),
            y=float(data.get("y") or 0.0),
            width=float(data.get("width") or 0.0),
            height=float(data.get("height") or 0.0),
        )

    def intersects(self, other: "NodeRect", *, tolerance: float = 0.0) -> bool:
        return not (
            self.x2 - tolerance <= other.x
            or other.x2 - tolerance <= self.x
            or self.y2 - tolerance <= other.y
            or other.y2 - tolerance <= self.y
        )


Window = Tuple[float, float]


@dataclasses.dataclass
class SceneGraphLayout:
    canvas_width: int
    canvas_height: int
    node_rects: Dict[str, NodeRect] = dataclasses.field(default_factory=dict)
    # node_id / edge_id -> (visible_from, visible_until) — the ONLY source of
    # truth for "is this on screen right now"; scene_graph.render reads these
    # instead of assuming a node persists from appear_at to the segment end.
    active_windows: Dict[str, Window] = dataclasses.field(default_factory=dict)
    edge_windows: Dict[str, Window] = dataclasses.field(default_factory=dict)
    # Narrative chapters (connected components), in time order — debugging/
    # testing aid, not consumed by the renderer.
    chapters: List[List[str]] = dataclasses.field(default_factory=list)
    # Persistent chapter/subject header text -> (visible_from, visible_until),
    # derived from SceneGraph.title_cues — one bold centered text overlay per
    # subject, independent of any image node (see scene_graph.render).
    title_windows: List[Tuple[str, float, float]] = dataclasses.field(default_factory=list)
    # Exp Solar's persistent checklist strip only (see CHECKLIST_BAND_PX):
    # ALL checklist_item nodes, in order, each as (label, becomes_current_at,
    # becomes_completed_at) — the FULL ordered list, not just whichever one
    # is current, so the renderer can always draw every cell's state (grey /
    # highlighted / completed) for any point in time. Empty for Overscaled
    # and for every non-checklist Exp Solar segment.
    checklist_windows: List[Tuple[str, float, float]] = dataclasses.field(default_factory=list)
    # Reserved top-band height in pixels when checklist_windows is non-empty
    # (else 0) — read by scene_graph.render to draw the strip and to push
    # the persistent chapter TitleCue (title_windows) down below it, so the
    # two never overlap.
    checklist_band_px: float = 0.0
    # edge_id -> the ALREADY-SOLVED arrow route (a clean, pre-jitter
    # polyline — see scene_graph.routing.solve_edge_route), computed once
    # per edge here at layout time, bent around any third-party card
    # between the two endpoints. scene_graph.composition only ever samples
    # this into pixels per frame (applying its small cosmetic jitter on
    # top); it never re-solves or re-searches a route.
    edge_routes: Dict[str, List[Tuple[float, float]]] = dataclasses.field(default_factory=dict)
    # edge_id -> (x, y) — the ALREADY-SOLVED label anchor for edges that
    # have a label (see scene_graph.routing.solve_label_position); no
    # per-frame search.
    edge_label_positions: Dict[str, Tuple[float, float]] = dataclasses.field(default_factory=dict)
    # node_id -> {"zoom_end", "pan_x", "pan_y"} — deterministic Ken Burns
    # parameters for image/diagram nodes, generated once here (see
    # compute_layout) and consumed by scene_graph.render's FFmpeg zoompan
    # wiring, never regenerated per frame.
    node_ken_burns: Dict[str, Dict[str, float]] = dataclasses.field(default_factory=dict)
    # node_id -> (dx, dy) offset from the caption's PRIMARY (existing
    # default) position — see scene_graph.routing.solve_caption_position.
    # (0, 0) means "no conflict found, render exactly where it always did";
    # scene_graph.composition._draw_caption only ever adds this offset, it
    # never solves anything itself.
    caption_positions: Dict[str, Tuple[float, float]] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "node_rects": {nid: r.to_dict() for nid, r in self.node_rects.items()},
            "active_windows": {nid: list(w) for nid, w in self.active_windows.items()},
            "edge_windows": {eid: list(w) for eid, w in self.edge_windows.items()},
            "chapters": [list(c) for c in self.chapters],
            "title_windows": [[text, start, end] for text, start, end in self.title_windows],
            "checklist_windows": [[text, start, end] for text, start, end in self.checklist_windows],
            "checklist_band_px": self.checklist_band_px,
            "edge_routes": {eid: [list(p) for p in pts] for eid, pts in self.edge_routes.items()},
            "edge_label_positions": {eid: list(p) for eid, p in self.edge_label_positions.items()},
            "node_ken_burns": {nid: dict(p) for nid, p in self.node_ken_burns.items()},
            "caption_positions": {nid: list(p) for nid, p in self.caption_positions.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SceneGraphLayout":
        data = data or {}
        rects = {
            nid: NodeRect.from_dict(r) for nid, r in (data.get("node_rects") or {}).items()
        }
        active_windows = {
            nid: (float(w[0]), float(w[1])) for nid, w in (data.get("active_windows") or {}).items()
        }
        edge_windows = {
            eid: (float(w[0]), float(w[1])) for eid, w in (data.get("edge_windows") or {}).items()
        }
        chapters = [list(c) for c in (data.get("chapters") or [])]
        title_windows = [
            (str(t[0]), float(t[1]), float(t[2])) for t in (data.get("title_windows") or [])
        ]
        checklist_windows = [
            (str(t[0]), float(t[1]), float(t[2])) for t in (data.get("checklist_windows") or [])
        ]
        checklist_band_px = float(data.get("checklist_band_px") or 0.0)
        edge_routes = {
            eid: [(float(p[0]), float(p[1])) for p in pts]
            for eid, pts in (data.get("edge_routes") or {}).items()
        }
        edge_label_positions = {
            eid: (float(p[0]), float(p[1])) for eid, p in (data.get("edge_label_positions") or {}).items()
        }
        node_ken_burns = {
            nid: {k: float(v) for k, v in (p or {}).items()}
            for nid, p in (data.get("node_ken_burns") or {}).items()
        }
        caption_positions = {
            nid: (float(p[0]), float(p[1])) for nid, p in (data.get("caption_positions") or {}).items()
        }
        return cls(
            canvas_width=int(data.get("canvas_width") or DEFAULT_CANVAS_WIDTH),
            canvas_height=int(data.get("canvas_height") or DEFAULT_CANVAS_HEIGHT),
            node_rects=rects,
            active_windows=active_windows,
            edge_windows=edge_windows,
            chapters=chapters,
            title_windows=title_windows,
            checklist_windows=checklist_windows,
            checklist_band_px=checklist_band_px,
            edge_routes=edge_routes,
            edge_label_positions=edge_label_positions,
            node_ken_burns=node_ken_burns,
            caption_positions=caption_positions,
        )

    def bounds_for(self, node_ids: List[str]) -> Optional[Tuple[float, float, float, float]]:
        """Union bounding box (x0, y0, x1, y1) of the given nodes, or None."""
        rects = [self.node_rects[n] for n in node_ids if n in self.node_rects]
        if not rects:
            return None
        x0 = min(r.x for r in rects)
        y0 = min(r.y for r in rects)
        x1 = max(r.x2 for r in rects)
        y1 = max(r.y2 for r in rects)
        return (x0, y0, x1, y1)


def _probe_media_size(path: Optional[str]) -> Optional[Tuple[int, int]]:
    """Best-effort (width, height) of a resolved media file. Never raises."""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    suffix = p.suffix.lower()
    try:
        if suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
            from PIL import Image

            with Image.open(p) as im:
                return (int(im.width), int(im.height))
        # Video: probe with ffprobe (resolved the same way media_duration.py does).
        import json
        import shutil
        import subprocess

        ffprobe = shutil.which("ffprobe") or "ffprobe"
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "json", str(p)],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(proc.stdout or "{}")
        streams = data.get("streams") or []
        if streams:
            return (int(streams[0]["width"]), int(streams[0]["height"]))
    except Exception:
        return None
    return None


def _fit_within(box_w: float, box_h: float, aspect: float) -> Tuple[float, float]:
    """Largest (w, h) with the given aspect ratio that fits inside box_w x box_h."""
    if aspect <= 0:
        aspect = 1.0
    candidate_h = box_w / aspect
    if candidate_h <= box_h:
        return box_w, candidate_h
    return box_h * aspect, box_h


def _connected_chapters(scene_graph: SceneGraph) -> List[List[SceneNode]]:
    """Group non-anchor, non-checklist_item nodes into chapters (connected
    components of the causal edge graph), each chapter's members sorted by
    appear_at, and chapters themselves ordered by their earliest member's
    appear_at — a node with no edges is simply a one-member chapter."""

    flow_nodes = [n for n in scene_graph.nodes if n.type not in ("anchor", _CHECKLIST_ITEM_TYPE)]
    by_id = {n.id: n for n in flow_nodes}
    adjacency: Dict[str, set] = {n.id: set() for n in flow_nodes}
    for edge in scene_graph.edges:
        if edge.from_node in by_id and edge.to_node in by_id:
            adjacency[edge.from_node].add(edge.to_node)
            adjacency[edge.to_node].add(edge.from_node)

    seen: set = set()
    chapters: List[List[SceneNode]] = []
    for node in flow_nodes:  # narration order -> deterministic component discovery order
        if node.id in seen:
            continue
        queue = [node.id]
        seen.add(node.id)
        member_ids: List[str] = []
        while queue:
            cur = queue.pop(0)
            member_ids.append(cur)
            for neighbor in sorted(adjacency[cur]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        members = sorted((by_id[m] for m in member_ids), key=lambda n: (n.appear_at, n.id))
        chapters.append(members)

    chapters.sort(key=lambda members: (members[0].appear_at, members[0].id))
    return chapters


# Fixed pixel room reserved BELOW the media rect for its caption (up to 3
# wrapped lines) — the layout engine, not the caption renderer, is what has
# to guarantee this clearance actually exists so a caption is never clipped
# by canvas edge, an arrow, or (across different chapters, which never
# overlap in time so this is about absolute space, not neighbors) its own
# card boundary. FIXED pixels, not a fraction of box_h: a fraction shrinks
# disproportionately for a short, wide box (exactly the shape a landscape
# photo wants — see _SLOT_TEMPLATES), starving the media area and leaving
# the fitted image stranded well short of the box's actual width.
CAPTION_RESERVE_PX = 150
# Fixed pixel room reserved ABOVE the media rect for a node's `label` (see
# composition._draw_node_label) — a FRACTION doesn't fit here either, for
# the same reason as CAPTION_RESERVE_PX: the label is one short line at a
# near-constant pixel height regardless of the card's own size. Matches
# composition._LABEL_RESERVE_PX's own font height (up to 32px) plus the
# ~28px gap it draws with, plus a little headroom.
# This MUST be reserved here, in the slot's own box_h, not just locally in
# composition.render_node_reveal_frame's sub-canvas padding — otherwise nothing
# stops the label from bleeding upward into whatever sits above the slot
# (a neighboring card, or the chapter title band).
LABEL_RESERVE_PX = 90

# Every slot template centers on cy_frac=0.50 — deliberate for a single
# chapter (a clean, predictable grid), but across a WHOLE video where every
# chapter reuses the exact same templates, it reads as monotonous: nothing
# ever varies vertically, chapter after chapter (a real complaint — cards
# always sit in "the same line"). CHAPTER_Y_OFFSET_MAX_FRAC bounds a small,
# per-CHAPTER (not per-node — every member of one chapter still shares the
# same offset, preserving their relative geometry) deterministic vertical
# nudge, solved once here and never touched again. Kept well inside the
# templates' own ~5% top/bottom margin (cy_frac=0.50 +/- bh_frac/2=0.45) so
# there's no risk of crowding the anchor/title bands or the stage edge —
# _slot_rect's hard clamp below is a second, unconditional safety net on
# top of this bound regardless.
CHAPTER_Y_OFFSET_MAX_FRAC = 0.025


# Exp Solar's "index_grid" beat only (scene_graph.exp_solar_csv) — a real
# 3-row x 5-column grid, structurally separate from the 1/2/3/4-slot ROW
# templates above (this module's own docstring's "never a uniform grid"
# rule is about those; the reference's one-time 15-item index/menu board
# is a genuinely different composition, not a wider row). Reading order:
# row-major, top-left -> bottom-right, matching CSV authoring order.
# Chosen ONLY when a chapter's own edges include kind="group_grid" (see
# _chapter_cap/_is_grid_chapter below) — never reachable via Overscaled's
# own CSV (which never emits that edge kind) or via Exp Solar's four_row
# (which uses kind="group" instead).
_GRID_COLS = 5
_GRID_ROWS = 3
_GRID_CELL_W_FRAC = 0.18
_GRID_CELL_H_FRAC = 0.30
SLOT_TEMPLATE_GRID_15: Dict[int, List[Tuple[float, float, float, float]]] = {
    15: [
        ((c + 0.5) / _GRID_COLS, (r + 0.5) / _GRID_ROWS, _GRID_CELL_W_FRAC, _GRID_CELL_H_FRAC)
        for r in range(_GRID_ROWS)
        for c in range(_GRID_COLS)
    ]
}

# A 15-cell grid box is much smaller than a 1/2/3/4-slot ROW box, but
# LABEL_RESERVE_PX/CAPTION_RESERVE_PX above are FIXED pixel amounts sized
# for those much taller boxes — applying them unchanged to a small grid
# cell would leave almost no room for the actual thumbnail (composition.py
# already scales its label/caption FONT SIZE down with rect.height, e.g.
# _draw_node_label / _draw_caption's ``rect.height * 0.09``-based sizing,
# so a smaller cell genuinely needs less reserved room, not the same fixed
# amount). These compact constants are sized generously for the smaller
# font a ~200px-tall media rect actually renders at (see _slot_rect's
# ``compact`` param) — comfortably covers composition.py's real usage
# without needing to touch composition.py itself.
GRID_LABEL_RESERVE_PX = 40
GRID_CAPTION_RESERVE_PX = 90


def _is_grid_chapter(members: List[SceneNode], scene_graph: SceneGraph) -> bool:
    member_ids = {n.id for n in members}
    return any(
        e.kind == "group_grid" and e.from_node in member_ids and e.to_node in member_ids
        for e in scene_graph.edges
    )


def _chapter_cap(members: List[SceneNode], scene_graph: SceneGraph, default_cap: int) -> int:
    """Per-chapter active-card cap: an index_grid chapter (kind="group_grid"
    edges) always gets 15, regardless of the style's general cap, so a
    four_row chapter in the SAME segment still slides at its own (smaller)
    cap — one style-wide number can't serve both beats correctly."""
    return 15 if _is_grid_chapter(members, scene_graph) else default_cap


def _chapter_y_offset_frac(chapter_seed: str) -> float:
    """A small, deterministic per-chapter vertical nudge in
    [-CHAPTER_Y_OFFSET_MAX_FRAC, +CHAPTER_Y_OFFSET_MAX_FRAC] — same node-id
    hash-seeding convention as routing.deterministic_unit's other callers
    (Ken Burns params, jitter): same seed -> same offset, always."""
    from .routing import deterministic_unit

    return CHAPTER_Y_OFFSET_MAX_FRAC * deterministic_unit(chapter_seed, 20)


def _slot_rect(
    template: Dict[int, List[Tuple[float, float, float, float]]], template_size: int, slot_index: int, *,
    stage_x: float, stage_y: float, stage_w: float, stage_h: float,
    resolved_media: Dict[str, str], node: SceneNode, y_offset_frac: float = 0.0,
    compact: bool = False,
) -> NodeRect:
    cx_frac, cy_frac, bw_frac, bh_frac = template[template_size][slot_index]
    box_w = bw_frac * stage_w
    box_h = bh_frac * stage_h
    box_cx = stage_x + cx_frac * stage_w
    box_top = stage_y + (cy_frac + y_offset_frac) * stage_h - box_h / 2.0
    # Unconditional safety clamp — independent of CHAPTER_Y_OFFSET_MAX_FRAC's
    # own bound above — so the caption zone reserved below the media (which
    # relies on the box's bottom edge staying within the stage; see
    # CAPTION_RESERVE_PX's containment math) can never be pushed out of
    # bounds by this offset, however it's computed.
    box_top = max(stage_y, min(stage_y + stage_h - box_h, box_top))
    label_reserve_px = GRID_LABEL_RESERVE_PX if compact else LABEL_RESERVE_PX
    caption_reserve_px = GRID_CAPTION_RESERVE_PX if compact else CAPTION_RESERVE_PX
    label_reserve = label_reserve_px if (node.type != "anchor" and node.label) else 0.0
    media_top = box_top + label_reserve
    media_h = max(10.0, box_h - label_reserve - caption_reserve_px)

    size = _probe_media_size(resolved_media.get(node.id))
    aspect = (size[0] / size[1]) if size and size[1] else 16.0 / 9.0
    fit_w, fit_h = _fit_within(box_w, media_h, aspect)
    final_x = box_cx - fit_w / 2.0
    final_y = media_top + (media_h - fit_h) / 2.0
    return NodeRect(node_id=node.id, x=final_x, y=final_y, width=fit_w, height=fit_h)


def compute_layout(
    scene_graph: SceneGraph,
    *,
    resolved_media: Optional[Dict[str, str]] = None,
    canvas_width: Optional[int] = None,
    canvas_height: Optional[int] = None,
    max_active_per_chapter: Optional[int] = None,
) -> SceneGraphLayout:
    """Time-scoped editorial layout: chapters (causal chains / singles) take
    turns on a small, fixed set of non-grid stage slots, capped at
    ``max_active_per_chapter`` (default: module ``MAX_ACTIVE_PER_CHAPTER``,
    i.e. 3 — Overscaled's own, unchanged behavior when this argument is
    omitted) simultaneous cards — never the whole graph at once. A style
    that needs more (e.g. Exp Solar's four_row beat) passes a higher value
    explicitly; nothing about the default path changes. Same SceneGraph +
    same resolved_media + same cap -> byte-identical layout.
    """

    width = int(canvas_width or scene_graph.canvas.width or DEFAULT_CANVAS_WIDTH)
    height = int(canvas_height or scene_graph.canvas.height or DEFAULT_CANVAS_HEIGHT)
    resolved_media = resolved_media or {}
    duration = float(scene_graph.duration) or 1.0
    active_cap = int(max_active_per_chapter) if max_active_per_chapter else MAX_ACTIVE_PER_CHAPTER
    if active_cap > 4 or active_cap < 1:
        # Only 1/2/3/4-slot templates exist — clamp rather than KeyError
        # on an unsupported template size.
        active_cap = max(1, min(4, active_cap))

    anchors = [n for n in scene_graph.nodes if n.type == "anchor"]
    rects: Dict[str, NodeRect] = {}
    active_windows: Dict[str, Window] = {}
    edge_windows: Dict[str, Window] = {}

    # Anchors are per-subject (like a chapter title's icon): a LATER anchor
    # replaces an EARLIER one rather than stacking alongside it, matching the
    # reference style's "current subject" thumbnail — so, being time-disjoint,
    # they all share the exact same top-left slot rather than stacking.
    anchors_sorted = sorted(anchors, key=lambda n: (float(n.appear_at), n.id))
    for i, node in enumerate(anchors_sorted):
        rects[node.id] = NodeRect(
            node_id=node.id, x=MARGIN_PX, y=MARGIN_PX, width=ANCHOR_SIZE_PX, height=ANCHOR_SIZE_PX,
        )
        own_start = max(0.0, float(node.appear_at))
        next_start = anchors_sorted[i + 1].appear_at if i + 1 < len(anchors_sorted) else duration
        active_windows[node.id] = (own_start, max(next_start, own_start + MIN_HOLD_S))

    anchor_band = (ANCHOR_SIZE_PX + GUTTER_PX) if anchors else 0
    # A persistent chapter TitleCue renders centered near the very top
    # (render_title_reveal_frame, top_margin — see checklist_band_px below)
    # independent of any node — the stage must reserve room for it too,
    # exactly like the anchor band above, or a node's own label (drawn
    # ABOVE its rect, see composition._draw_node_label) can collide with
    # title text when a slot sits close to the top (e.g. the 3-slot
    # template's top-right hero).
    title_band = TITLE_BAND_PX if scene_graph.title_cues else 0
    # Exp Solar's persistent checklist strip (see CHECKLIST_BAND_PX) is the
    # TOPMOST reserved band — it stacks BEFORE anchor/title, pushing both
    # further down, so the strip is never covered by the chapter title or
    # an anchor icon.
    checklist_items = sorted(
        (n for n in scene_graph.nodes if n.type == _CHECKLIST_ITEM_TYPE),
        key=lambda n: (float(n.appear_at), n.id),
    )
    checklist_band = CHECKLIST_BAND_PX if checklist_items else 0
    stage_x = float(MARGIN_PX)
    stage_y = float(MARGIN_PX + checklist_band + anchor_band + title_band)
    stage_w = float(width - 2 * MARGIN_PX)
    stage_h = float(height - MARGIN_PX - stage_y)

    # Full ordered checklist state (label, becomes_current_at,
    # becomes_completed_at) — same windowing convention as title_windows
    # below: each item's window runs from its own appear_at to the NEXT
    # item's appear_at (or the segment duration for the last one). ALL
    # items are included, even ones whose window hasn't started yet — the
    # renderer needs the full list to draw every cell's grey/highlighted/
    # completed state at any point in time, not just whichever is current.
    checklist_windows: List[Tuple[str, float, float]] = []
    for i, node in enumerate(checklist_items):
        own_start = max(0.0, float(node.appear_at))
        next_start = checklist_items[i + 1].appear_at if i + 1 < len(checklist_items) else duration
        label = str(node.label or "").strip() or node.id
        checklist_windows.append((label, own_start, max(next_start, own_start + MIN_HOLD_S)))

    chapters = _connected_chapters(scene_graph)
    node_id_chapters: List[List[str]] = [[n.id for n in members] for members in chapters]
    chapter_index_of_node: Dict[str, int] = {
        node.id: c_index for c_index, members in enumerate(chapters) for node in members
    }
    # Per-chapter cap: normally ``active_cap`` for every chapter, but an
    # index_grid chapter (kind="group_grid" edges — see _is_grid_chapter)
    # always gets 15, regardless of the style's general cap, so a four_row
    # chapter sharing the same segment still slides at ITS own (smaller)
    # cap. Computed once, read by both the eviction sweep below and the
    # per-chapter rect assignment further down.
    chapter_caps: List[int] = [_chapter_cap(members, scene_graph, active_cap) for members in chapters]

    # ACTIVE WINDOWS (when each node is actually on screen) are computed in
    # ONE GLOBAL chronological sweep across every node, not chapter by
    # chapter. A per-chapter "chapter_end = next chapter in the chapters
    # list" boundary assumes chapters occupy non-overlapping contiguous
    # time blocks IN THAT SAME ORDER — false whenever a chapter's own
    # members are spread far apart in time (a deliberate, supported
    # pattern: set something up early, pay it off much later via a causal
    # arrow) and another chapter's entire span happens to fit in that gap.
    # A real CSV hit exactly this: an isolated node with no causal edges
    # (so its own one-member "chapter") was authored chronologically
    # between two members of an unrelated, ongoing causal chain, and the
    # old per-chapter logic let both chapters render simultaneously —
    # exactly the unrelated-cards-overlapping bug this replaces. Here, only
    # ONE chapter ever owns the screen at a time: whichever chapter the
    # most-recently-reached node (by appear_at) belongs to. A chapter that
    # was interrupted, or that pays off much later, simply becomes current
    # again the moment one of its own members' appear_at is reached — its
    # members between then and now stay correctly hidden.
    flow_nodes_by_time = sorted(
        (n for n in scene_graph.nodes if n.type not in ("anchor", _CHECKLIST_ITEM_TYPE)),
        key=lambda n: (float(n.appear_at), n.id),
    )
    current_chapter: Optional[int] = None
    current_run: List[str] = []  # node ids from the CURRENT chapter, active now

    for node in flow_nodes_by_time:
        own_start = max(0.0, float(node.appear_at))
        node_chapter = chapter_index_of_node[node.id]

        if node_chapter != current_chapter:
            # Hard cut: a different chapter takes the screen NOW. No
            # MIN_HOLD_S grace period across this boundary — extending a
            # window past a foreign chapter's start is exactly what
            # produced the overlap bug this replaces.
            for prev_id in current_run:
                prev_start, _ = active_windows[prev_id]
                active_windows[prev_id] = (prev_start, own_start)
            current_run = []
            current_chapter = node_chapter

        current_run.append(node.id)
        active_windows[node.id] = (own_start, duration)  # provisional; closed on eviction/cut/end

        if len(current_run) > chapter_caps[current_chapter]:
            evicted_id = current_run.pop(0)
            evicted_start, _ = active_windows[evicted_id]
            # MIN_HOLD_S still applies here: this is same-chapter sliding
            # eviction, not a foreign interruption, so a brief overlap past
            # the evicting member's own start (same as the pre-existing
            # per-chapter behavior) is an accepted, minor trade-off.
            active_windows[evicted_id] = (evicted_start, max(own_start, evicted_start + MIN_HOLD_S))

    # ADAPTIVE SIZING: slot RECTS are assigned per chapter AFTER the sweep
    # above (not before, like the old fixed-size version) — sizing needs to
    # know how crowded a chapter ACTUALLY gets, which is a function of the
    # real active_windows the sweep just produced, not raw member count. A
    # 5-member chapter that (thanks to pacing/eviction) never shows more
    # than 2 at once gets the bigger 2-slot template for every one of its
    # members, not the smaller 3-slot one — lightweight, deterministic,
    # computed once (see _peak_concurrent), never re-solved per frame.
    for c_index, members in enumerate(chapters):
        is_grid = _is_grid_chapter(members, scene_graph)
        chapter_cap = chapter_caps[c_index]
        peak = _peak_concurrent([active_windows[n.id] for n in members])
        # SLOT_TEMPLATE_GRID_15 has exactly ONE entry, keyed 15 (a fixed
        # 3x5 board — see its own definition) — it is never "adaptively"
        # smaller like the 1/2/3/4-slot row templates below. Sizing a grid
        # chapter from peak/chapter_cap/len(members) (as every non-grid
        # chapter correctly is) looks up template[6] or similar and raises
        # KeyError the moment a real index_grid chapter has fewer than 15
        # simultaneously-active members — i.e. always, since index_grid is
        # authored with far fewer than 15 rows in practice. Pre-existing,
        # independent of any timing fix: reproduced with this exact
        # KeyError before touching node timing at all.
        template_size = 15 if is_grid else max(1, min(peak, chapter_cap, len(members)))
        template = SLOT_TEMPLATE_GRID_15 if is_grid else _choose_template_variant(members)
        # Role-based reordering (put an elevated-role member in the hero
        # slot) is only SAFE when every member gets its own dedicated slot
        # (len(members) <= template_size) — a chapter with MORE members
        # than template_size relies on slot index i % template_size lining
        # up EXACTLY with the sliding-eviction order above (member i and
        # member i+template_size only ever share a slot because eviction
        # already guarantees they're never simultaneously active); silently
        # reordering by role there would let two genuinely-concurrent
        # members collide onto the same physical rect. So: reorder freely
        # in the common (no sliding) case, otherwise keep natural order.
        # An index_grid chapter is never role-reordered either way — a
        # 15-item index board has no "hero" slot to steer a member into.
        ordered = (
            members if is_grid
            else (_slot_assignment_order(members) if len(members) <= template_size else members)
        )
        slot_index_of_node = {node.id: i % template_size for i, node in enumerate(ordered)}
        # One offset per CHAPTER (seeded by its first member's own id, so
        # it's stable regardless of chapter-list ordering), shared by every
        # member — see CHAPTER_Y_OFFSET_MAX_FRAC. Skipped for a grid chapter:
        # the whole point of a 3x5 index board is a stable, predictable
        # grid — nudging it defeats that.
        y_offset_frac = 0.0 if is_grid else (_chapter_y_offset_frac(members[0].id) if members else 0.0)
        for node in members:
            rects[node.id] = _slot_rect(
                template, template_size, slot_index_of_node[node.id],
                stage_x=stage_x, stage_y=stage_y, stage_w=stage_w, stage_h=stage_h,
                resolved_media=resolved_media, node=node, y_offset_frac=y_offset_frac,
                compact=is_grid,
            )

    # An arrow's NATURAL window is the intersection of its two endpoints'
    # windows (it can't outlive either node) — but arrows are a momentary
    # "look at this connection" cue, not a permanent web, so a further
    # global sliding cap (like MAX_ACTIVE_PER_CHAPTER for content cards)
    # retires an older arrow once MAX_ACTIVE_EDGES newer ones have been
    # drawn, so the canvas is never criss-crossed with every causal link
    # drawn so far.
    edge_draw_at: Dict[str, float] = {}
    edge_natural_end: Dict[str, float] = {}
    valid_edges = []
    for edge in scene_graph.edges:
        if edge.kind in ("group", "group_grid"):
            # Exp Solar's four_row/index_grid grouping edges: real graph
            # edges (so _connected_chapters above already grouped their
            # endpoints into one on-screen chapter) but never a visible
            # arrow — no window is ever built for them, so
            # render._edge_reveal_layers (which requires
            # layout.edge_windows.get(edge.id) to be non-None) always skips
            # them. They also never consume the MAX_ACTIVE_EDGES budget
            # real arrows share.
            continue
        from_window = active_windows.get(edge.from_node)
        to_window = active_windows.get(edge.to_node)
        if from_window is None or to_window is None:
            continue
        edge_draw_at[edge.id] = max(0.0, float(edge.draw_at))
        edge_natural_end[edge.id] = min(from_window[1], to_window[1])
        valid_edges.append(edge)

    valid_edges.sort(key=lambda e: edge_draw_at[e.id])
    for i, edge in enumerate(valid_edges):
        draw_at = edge_draw_at[edge.id]
        window_end = edge_natural_end[edge.id]
        if i + MAX_ACTIVE_EDGES < len(valid_edges):
            window_end = min(window_end, edge_draw_at[valid_edges[i + MAX_ACTIVE_EDGES].id])
        window_end = max(window_end, draw_at + MIN_HOLD_S * 0.5)
        edge_windows[edge.id] = (draw_at, window_end)

    cues_sorted = sorted(scene_graph.title_cues, key=lambda c: float(c.at))
    # Collapse a RUN of consecutive cues sharing the IDENTICAL text into ONE
    # persistent window (the run's first cue's own start -> the next
    # DIFFERENT cue's start, or duration) instead of starting a brand-new
    # reveal-in animation on every row that merely repeats the same
    # chapter text. Setting `chapter`/`chapter_title` on every row of a
    # section (rather than only its first row) is a common CSV-authoring
    # pattern the compiler has never rejected — TitleCue creation
    # (overscaled_csv.py) appends one per non-empty value with no
    # deduplication — and without this collapse it produced a title that
    # kept restarting its own reveal every few seconds, never staying
    # settled long enough to read (looked like "no title at all"). A CSV
    # that already sets chapter_title on only the first row of each
    # section (as documented) never has two consecutive cues with the
    # same text, so this is a no-op there — provably inert for both
    # Overscaled and any already-correct Exp Solar CSV.
    collapsed_cues: List[Tuple[str, float]] = []
    for cue in cues_sorted:
        if collapsed_cues and collapsed_cues[-1][0] == cue.text:
            continue
        collapsed_cues.append((cue.text, max(0.0, float(cue.at))))

    title_windows: List[Tuple[str, float, float]] = []
    for i, (text, own_start) in enumerate(collapsed_cues):
        next_start = collapsed_cues[i + 1][1] if i + 1 < len(collapsed_cues) else duration
        title_windows.append((text, own_start, max(next_start, own_start + MIN_HOLD_S)))

    # ARROW ROUTING + LABEL POSITIONS — solved ONCE per edge, right here,
    # never per frame (scene_graph.composition only SAMPLES the cached
    # shape/position at render time). An edge's obstacles are every OTHER
    # node's rect whose own active window overlaps this edge's window (in
    # practice: its chapter-mates and/or a persistent anchor) — a third
    # card sitting between the edge's two endpoints must be routed around,
    # not drawn through (see scene_graph.routing.solve_edge_route).
    # Already-solved earlier arrows are added as soft obstacles too, so a
    # later edge prefers not to cross an existing one either.
    from .routing import (
        ObstacleRect,
        deterministic_unit,
        keep_out_exit_point as _solve_keep_out_exit_point,
        polyline_bbox,
        rect_obstacle,
        solve_caption_position,
        solve_edge_route,
        solve_label_position,
    )

    edge_routes: Dict[str, List[Tuple[float, float]]] = {}
    edge_label_positions: Dict[str, Tuple[float, float]] = {}
    solved_arrow_bboxes: List = []
    # Every solved edge label's own box, collected here so the narration
    # caption pass below (which runs after every edge is solved) can treat
    # edge labels as obstacles too — not fed back into edge/label solving
    # itself, which is unchanged.
    solved_label_boxes: List = []
    # (window, box) pairs for the caption pass below — unlike
    # solved_arrow_bboxes/solved_label_boxes (used ONLY to keep later edges
    # from crossing earlier ones, order-dependent, no window needed), a
    # node's caption must only avoid an edge that's actually on screen AT
    # THE SAME TIME as it is, so its own window is kept alongside each box.
    caption_edge_obstacles: List[Tuple[Window, "ObstacleRect"]] = []

    for edge in valid_edges:  # already sorted by draw_at — a fixed, deterministic processing order
        from_rect = rects.get(edge.from_node)
        to_rect = rects.get(edge.to_node)
        window = edge_windows.get(edge.id)
        if from_rect is None or to_rect is None or window is None:
            continue

        obstacles = [
            rect_obstacle(r.x, r.y, r.x2, r.y2 + CAPTION_RESERVE_PX, margin=16.0)
            for nid, r in rects.items()
            if nid not in (edge.from_node, edge.to_node)
            and active_windows.get(nid) is not None
            and _windows_overlap(active_windows[nid], window)
        ]
        obstacles.extend(solved_arrow_bboxes)

        from_cx, from_cy = from_rect.center
        to_cx, to_cy = to_rect.center
        from_box = rect_obstacle(from_rect.x, from_rect.y, from_rect.x2, from_rect.y2 + CAPTION_RESERVE_PX)
        to_box = rect_obstacle(to_rect.x, to_rect.y, to_rect.x2, to_rect.y2 + CAPTION_RESERVE_PX)
        x0, y0 = _solve_keep_out_exit_point(from_cx, from_cy, to_cx, to_cy, from_box, pad=16.0)
        x1, y1 = _solve_keep_out_exit_point(to_cx, to_cy, from_cx, from_cy, to_box, pad=16.0)

        route = solve_edge_route(x0, y0, x1, y1, obstacles)
        edge_routes[edge.id] = list(route.points)
        route_bbox = polyline_bbox(route.points, margin=14.0)
        solved_arrow_bboxes.append(route_bbox)
        caption_edge_obstacles.append((window, route_bbox))

        label = str((edge.metadata or {}).get("label") or "").strip()
        if label:
            # A generous fixed estimate of the label's own footprint — this
            # only needs to be big enough to search a SAFE clearance around
            # (the real Pillow glyph measurement happens once, at draw
            # time, in composition.py); it does not need to be pixel-exact.
            half_w = max(40.0, len(label) * 6.5)
            half_h = 16.0
            label_x, label_y = solve_label_position(
                route.points, half_w, half_h, obstacles + [from_box, to_box],
            )
            edge_label_positions[edge.id] = (label_x, label_y)
            label_box = ObstacleRect(label_x - half_w, label_y - half_h, label_x + half_w, label_y + half_h)
            solved_label_boxes.append(label_box)
            caption_edge_obstacles.append((window, label_box))

    # NARRATION CAPTION PLACEMENT — solved ONCE per node, right here, same
    # "solve once, sample at render time" contract as the arrow routing
    # above (never re-searched per frame; scene_graph.composition only
    # draws at the returned offset). The PRIMARY zone is today's existing
    # default position (directly below the media, left-aligned) — tried
    # FIRST, so a caption with no real conflict renders in EXACTLY the same
    # place as before this pass existed. Only on an actual conflict does it
    # fall back to a nearby alternate (see routing.solve_caption_position).
    #
    # Obstacles checked, matching the six categories a narration caption
    # must avoid: (1) every OTHER simultaneously-active node's own rect +
    # its own caption band ("active visual clips/cards" / "graphics"); (2)
    # every solved arrow route whose window overlaps this node's own window,
    # regardless of which two nodes it connects — including THIS node's own
    # edges, since an edge passing right next to its own endpoint's caption
    # is just as real a collision as an unrelated one ("arrows/edge lines");
    # (3) every solved edge label, same window filter ("edge labels"); (4)
    # every ALREADY-solved caption from an earlier node in this same pass,
    # again window-filtered ("another narration caption"); (5) the full
    # canvas bounds ("screen boundaries"). Processed in the SceneGraph's own
    # stable node order, so the result is fully deterministic.
    caption_positions: Dict[str, Tuple[float, float]] = {}
    canvas_bounds = ObstacleRect(0.0, 0.0, float(width), float(height))
    solved_caption_obstacles: List[Tuple[Window, "ObstacleRect"]] = []

    for node in scene_graph.nodes:
        if not node.caption or not str(node.caption.text or "").strip():
            continue
        rect = rects.get(node.id)
        node_window = active_windows.get(node.id)
        if rect is None or node_window is None:
            continue

        card_obstacles = [
            rect_obstacle(r.x, r.y, r.x2, r.y2 + CAPTION_RESERVE_PX, margin=8.0)
            for nid, r in rects.items()
            if nid != node.id
            and active_windows.get(nid) is not None
            and _windows_overlap(active_windows[nid], node_window)
        ]
        edge_obstacles = [
            box for edge_window, box in caption_edge_obstacles if _windows_overlap(edge_window, node_window)
        ]
        other_caption_obstacles = [
            box for cap_window, box in solved_caption_obstacles if _windows_overlap(cap_window, node_window)
        ]

        primary_x, primary_y = rect.x, rect.y2 + 10.0
        cap_width = max(10.0, rect.width)
        cap_height = max(10.0, CAPTION_RESERVE_PX - 10.0)
        solved_x, solved_y = solve_caption_position(
            primary_x, primary_y, cap_width, cap_height,
            card_obstacles + edge_obstacles + other_caption_obstacles,
            bounds=canvas_bounds,
        )
        caption_positions[node.id] = (round(solved_x - primary_x, 2), round(solved_y - primary_y, 2))
        solved_caption_obstacles.append(
            (node_window, ObstacleRect(solved_x, solved_y, solved_x + cap_width, solved_y + cap_height))
        )

    # KEN BURNS — deterministic per-node pan/zoom parameters, generated
    # ONCE here (never per frame; see scene_graph.render's zoompan wiring,
    # which only ever READS these) for image/diagram nodes only —
    # video_loop already has real motion, and anchors stay static by
    # design. Small and slow per spec: ~100% -> 104-108% scale, a small pan.
    node_ken_burns: Dict[str, Dict[str, float]] = {}
    for node in scene_graph.nodes:
        if node.type not in ("image", "diagram"):
            continue
        zoom_end = 1.04 + 0.04 * (0.5 + 0.5 * deterministic_unit(node.id, 10))
        pan_x = 0.05 * deterministic_unit(node.id, 11)
        pan_y = 0.05 * deterministic_unit(node.id, 12)
        node_ken_burns[node.id] = {
            "zoom_end": round(zoom_end, 4), "pan_x": round(pan_x, 4), "pan_y": round(pan_y, 4),
        }

    return SceneGraphLayout(
        canvas_width=width, canvas_height=height, node_rects=rects,
        active_windows=active_windows, edge_windows=edge_windows, chapters=node_id_chapters,
        title_windows=title_windows, checklist_windows=checklist_windows, checklist_band_px=float(checklist_band),
        edge_routes=edge_routes, edge_label_positions=edge_label_positions,
        node_ken_burns=node_ken_burns, caption_positions=caption_positions,
    )


def _windows_overlap(a: Window, b: Window) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def find_overlaps(layout: SceneGraphLayout, *, tolerance: float = 0.5) -> List[Tuple[str, str]]:
    """Pairs of node ids whose rects intersect AND whose active windows
    overlap in time — nodes from different (time-disjoint) chapters are
    expected and allowed to reuse the same screen position."""
    ids = list(layout.node_rects.keys())
    pairs = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a_id, b_id = ids[i], ids[j]
            a, b = layout.node_rects[a_id], layout.node_rects[b_id]
            if not a.intersects(b, tolerance=tolerance):
                continue
            a_window = layout.active_windows.get(a_id)
            b_window = layout.active_windows.get(b_id)
            if a_window is None or b_window is None or _windows_overlap(a_window, b_window):
                pairs.append((a_id, b_id))
    return pairs
