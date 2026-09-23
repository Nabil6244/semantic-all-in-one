"""Deterministic layout: SceneGraph (semantic intent) -> TIME-SCOPED canvas geometry.

This is a timed editorial composition, not a mind-map/storyboard renderer: the
fixed 1920x1080 canvas never changes size, but WHAT'S ON IT changes over time.
Nodes are grouped into narrative "chapters" — connected components of the
causal edge graph, in narration order (isolated nodes are their own
one-member chapter) — and only one chapter's nodes are ever meant to be on
screen at once. A chapter's members occupy the SAME small set of screen
positions ("slots") that every other chapter reuses, since chapters never
overlap in time; positions are deliberate/diagonal per slot-count (1, 2 or 3
slots), never a uniform grid. A chapter with more than 3 members slides:
member i is evicted once 3 later chapter-mates have appeared, so at most 3
members of any one chapter — and thus at most 3 content cards overall,
across the whole segment — are ever simultaneously visible.

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
    1: [(0.50, 0.50, 0.62, 0.90)],
    2: [(0.235, 0.50, 0.47, 0.90), (0.765, 0.50, 0.47, 0.90)],
    3: [
        (0.155, 0.50, 0.31, 0.90),
        (0.500, 0.50, 0.31, 0.90),
        (0.845, 0.50, 0.31, 0.90),
    ],
}
_SLOT_TEMPLATES_WEIGHTED: Dict[int, List[Tuple[float, float, float, float]]] = {
    1: [(0.50, 0.50, 0.62, 0.90)],
    2: [
        (0.71, 0.50, 0.58, 0.90),  # hero: right, wider
        (0.18, 0.50, 0.36, 0.90),  # supporting: left
    ],
    3: [
        (0.79, 0.50, 0.42, 0.90),  # hero: right, widest
        (0.13, 0.50, 0.26, 0.90),  # supporting: left
        (0.42, 0.50, 0.26, 0.90),  # supporting: middle
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

    def to_dict(self) -> dict:
        return {
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "node_rects": {nid: r.to_dict() for nid, r in self.node_rects.items()},
            "active_windows": {nid: list(w) for nid, w in self.active_windows.items()},
            "edge_windows": {eid: list(w) for eid, w in self.edge_windows.items()},
            "chapters": [list(c) for c in self.chapters],
            "title_windows": [[text, start, end] for text, start, end in self.title_windows],
            "edge_routes": {eid: [list(p) for p in pts] for eid, pts in self.edge_routes.items()},
            "edge_label_positions": {eid: list(p) for eid, p in self.edge_label_positions.items()},
            "node_ken_burns": {nid: dict(p) for nid, p in self.node_ken_burns.items()},
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
        return cls(
            canvas_width=int(data.get("canvas_width") or DEFAULT_CANVAS_WIDTH),
            canvas_height=int(data.get("canvas_height") or DEFAULT_CANVAS_HEIGHT),
            node_rects=rects,
            active_windows=active_windows,
            edge_windows=edge_windows,
            chapters=chapters,
            title_windows=title_windows,
            edge_routes=edge_routes,
            edge_label_positions=edge_label_positions,
            node_ken_burns=node_ken_burns,
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
    """Group non-anchor nodes into chapters (connected components of the
    causal edge graph), each chapter's members sorted by appear_at, and
    chapters themselves ordered by their earliest member's appear_at — a
    node with no edges is simply a one-member chapter."""

    flow_nodes = [n for n in scene_graph.nodes if n.type != "anchor"]
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
CAPTION_RESERVE_PX = 170
# Fixed pixel room reserved ABOVE the media rect for a node's `label` (see
# composition._draw_node_label) — a FRACTION doesn't fit here either, for
# the same reason as CAPTION_RESERVE_PX: the label is one short line at a
# near-constant pixel height regardless of the card's own size. Matches
# composition._LABEL_RESERVE_PX (56) plus the same ~14px gap it draws with.
# This MUST be reserved here, in the slot's own box_h, not just locally in
# composition.render_node_reveal_frame's sub-canvas padding — otherwise nothing
# stops the label from bleeding upward into whatever sits above the slot
# (a neighboring card, or the chapter title band).
LABEL_RESERVE_PX = 70


def _slot_rect(
    template: Dict[int, List[Tuple[float, float, float, float]]], template_size: int, slot_index: int, *,
    stage_x: float, stage_y: float, stage_w: float, stage_h: float,
    resolved_media: Dict[str, str], node: SceneNode,
) -> NodeRect:
    cx_frac, cy_frac, bw_frac, bh_frac = template[template_size][slot_index]
    box_w = bw_frac * stage_w
    box_h = bh_frac * stage_h
    box_cx = stage_x + cx_frac * stage_w
    box_top = stage_y + cy_frac * stage_h - box_h / 2.0
    label_reserve = LABEL_RESERVE_PX if (node.type != "anchor" and node.label) else 0.0
    media_top = box_top + label_reserve
    media_h = max(10.0, box_h - label_reserve - CAPTION_RESERVE_PX)

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
) -> SceneGraphLayout:
    """Time-scoped editorial layout: chapters (causal chains / singles) take
    turns on a small, fixed set of non-grid stage slots, capped at
    ``MAX_ACTIVE_PER_CHAPTER`` simultaneous cards — never the whole graph at
    once. Same SceneGraph + same resolved_media -> byte-identical layout.
    """

    width = int(canvas_width or scene_graph.canvas.width or DEFAULT_CANVAS_WIDTH)
    height = int(canvas_height or scene_graph.canvas.height or DEFAULT_CANVAS_HEIGHT)
    resolved_media = resolved_media or {}
    duration = float(scene_graph.duration) or 1.0

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
    # (render_title_reveal_frame, top_margin=MARGIN_PX) independent of any
    # node — the stage must reserve room for it too, exactly like the anchor
    # band above, or a node's own label (drawn ABOVE its rect, see
    # composition._draw_node_label) can collide with title text when a slot
    # sits close to the top (e.g. the 3-slot template's top-right hero).
    title_band = TITLE_BAND_PX if scene_graph.title_cues else 0
    stage_x = float(MARGIN_PX)
    stage_y = float(MARGIN_PX + anchor_band + title_band)
    stage_w = float(width - 2 * MARGIN_PX)
    stage_h = float(height - MARGIN_PX - stage_y)

    chapters = _connected_chapters(scene_graph)
    node_id_chapters: List[List[str]] = [[n.id for n in members] for members in chapters]
    chapter_index_of_node: Dict[str, int] = {
        node.id: c_index for c_index, members in enumerate(chapters) for node in members
    }

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
        (n for n in scene_graph.nodes if n.type != "anchor"),
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

        if len(current_run) > MAX_ACTIVE_PER_CHAPTER:
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
    for members in chapters:
        peak = _peak_concurrent([active_windows[n.id] for n in members])
        template_size = max(1, min(peak, MAX_ACTIVE_PER_CHAPTER, len(members)))
        template = _choose_template_variant(members)
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
        ordered = _slot_assignment_order(members) if len(members) <= template_size else members
        slot_index_of_node = {node.id: i % template_size for i, node in enumerate(ordered)}
        for node in members:
            rects[node.id] = _slot_rect(
                template, template_size, slot_index_of_node[node.id],
                stage_x=stage_x, stage_y=stage_y, stage_w=stage_w, stage_h=stage_h,
                resolved_media=resolved_media, node=node,
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
    title_windows: List[Tuple[str, float, float]] = []
    for i, cue in enumerate(cues_sorted):
        own_start = max(0.0, float(cue.at))
        next_start = cues_sorted[i + 1].at if i + 1 < len(cues_sorted) else duration
        title_windows.append((cue.text, own_start, max(next_start, own_start + MIN_HOLD_S)))

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
        deterministic_unit,
        keep_out_exit_point as _solve_keep_out_exit_point,
        polyline_bbox,
        rect_obstacle,
        solve_edge_route,
        solve_label_position,
    )

    edge_routes: Dict[str, List[Tuple[float, float]]] = {}
    edge_label_positions: Dict[str, Tuple[float, float]] = {}
    solved_arrow_bboxes: List = []

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
        solved_arrow_bboxes.append(polyline_bbox(route.points, margin=14.0))

        label = str((edge.metadata or {}).get("label") or "").strip()
        if label:
            # A generous fixed estimate of the label's own footprint — this
            # only needs to be big enough to search a SAFE clearance around
            # (the real Pillow glyph measurement happens once, at draw
            # time, in composition.py); it does not need to be pixel-exact.
            half_w = max(40.0, len(label) * 6.5)
            half_h = 16.0
            edge_label_positions[edge.id] = solve_label_position(
                route.points, half_w, half_h, obstacles + [from_box, to_box],
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
        title_windows=title_windows, edge_routes=edge_routes, edge_label_positions=edge_label_positions,
        node_ken_burns=node_ken_burns,
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
