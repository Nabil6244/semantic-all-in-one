"""The Exp Solar CSV contract — a distinct, reference-editing-grammar CSV
format, separate from the Overscaled CSV (see overscaled_csv.py).

    Exp Solar CSV -> this module's adapter -> the same Overscaled-CSV-shaped
    row dicts -> compile_overscaled_csv() -> the SAME SceneGraph/layout/
    composition/render pipeline Overscaled already uses.

No new SceneGraph, no new renderer, no new asset pipeline: this file is
purely a translation layer. Overscaled's own parser/schema/behavior is not
touched by anything here.

    EXP SOLAR CSV                         OVERSCALED CSV (internal, unchanged)
    scene_number,script_segment,          scene_number,script_segment,node_id,
    node_id,beat,role,asset_type,         node_type,role,asset_type,prompt,
    prompt,caption,highlight,chapter,     caption,highlight,edge_from,edge_to,
    node_label,relationship_to,           edge_label,edge_style,chapter_title,
    relationship_type,relationship_label  node_label

``beat`` replaces Overscaled's raw ``node_type`` — it names the reference
editing-grammar composition the row belongs to (hero, title, two_panel,
reaction, cta — plus four_row/index_grid/checklist, named here so future
CSVs are already forward-compatible) rather than a renderer primitive.
``node_type``/``role`` are derived from ``beat``/``asset_type`` so authors
don't have to know the underlying renderer's vocabulary.

Overscaled's own layout engine only ever shows at most 3 simultaneous
cards (scene_graph/layout.py: MAX_ACTIVE_PER_CHAPTER=3), using only its
existing 1/2/3-slot templates. For the Exp Solar style specifically,
compute_layout now also accepts a 4-slot template (see layout.py's
``_SLOT_TEMPLATES_SYMMETRIC[4]``/``[4]`` WEIGHTED) and a raised cap, read
from composition_styles/exp_solar.json's ``metadata.max_active_per_chapter``
— Overscaled's own preset carries no such key, so its behavior is
byte-identical to before this existed. ``beat=four_row`` is therefore fully
SUPPORTED: consecutive four_row rows are chained together with invisible
"group" edges (kind="group" — a real graph edge for chaptering purposes,
never drawn as an arrow, see overscaled_csv.py/layout.py) so they land in
the same on-screen chapter and get the 4-slot layout.

``beat=index_grid`` is likewise SUPPORTED: consecutive index_grid rows
(up to 15) are chained together with invisible "group_grid" edges (kind=
"group_grid" — same never-drawn-as-an-arrow mechanism as "group", but a
distinct kind so layout.py can tell a four_row chapter from an index_grid
one) so they land in one chapter that always gets a real, fixed 3x5 grid
(layout.SLOT_TEMPLATE_GRID_15) regardless of the style's general
max_active_per_chapter — an index_grid chapter's own cap is always 15
(see layout._chapter_cap). A run longer than 15 rows only chains its
first 15 members; extras are left as independent single-card reveals
with a warning, since only 15 grid cells exist.

``beat=checklist`` is likewise SUPPORTED, but structurally different from
every other beat: a checklist row never becomes a visible content card at
all. It becomes a node of type "checklist_item" (see schema.KNOWN_NODE_TYPES),
which scene_graph.layout excludes from ordinary chaptering entirely (the
same exclusion "anchor" already gets) and instead collects into a
persistent header strip — see layout.CHECKLIST_BAND_PX/checklist_windows
and composition.render_checklist_strip_frame. No grouping edges are
needed (unlike four_row/index_grid): the strip is reserved and drawn for
the WHOLE segment regardless of which ordinary chapter is currently on
screen underneath it. A checklist row's item label comes from
``node_label`` if set, else its own ``chapter`` text, else a generic
"Item N" — reusing existing columns, no new CSV column. Only the first
CHECKLIST_MAX_ITEMS (15) checklist rows across the WHOLE CSV become
checklist items (they need not be consecutive — the realistic pattern is
one checklist row opening each later chapter); anything past the 15th
falls back to an ordinary card with a warning.

``relationship_to``/``relationship_type``/``relationship_label`` replace
Overscaled's raw ``edge_from``/``edge_to``/``edge_label``. Two things reuse
this one edge mechanism, because compute_layout's chaptering (see
layout._connected_chapters) is the ONLY existing way to put 2+ cards on
screen together: (1) a pure compositional pairing for a two_panel/reaction
beat, ``relationship_type`` left blank, and (2) a genuine causal
relationship named via ``relationship_type`` (causation, dependency,
consequence, transformation, mechanism, process). Per the reference plan's
explicit arrow-restraint rule ("do not put an arrow on every scene"), this
adapter NEVER promotes an edge to the renderer's rare, thick-red "callout"
style automatically — every Exp Solar edge renders as the default,
understated "sequential" connector. Reserving callout for a genuinely rare
proof-relationship is a human authoring decision on the underlying CSV,
not something this adapter infers.
"""

from __future__ import annotations

import dataclasses
from typing import Dict, List, Mapping, Optional, Sequence

from .generator import SceneGraphGenerationResult
from .overscaled_csv import compile_overscaled_csv
from .schema import SceneGraph

REQUIRED_COLUMNS = ("scene_number", "script_segment")
OPTIONAL_COLUMNS = (
    "node_id", "beat", "role", "asset_type", "prompt", "caption", "highlight",
    "chapter", "node_label", "relationship_to", "relationship_type", "relationship_label",
)
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Reference editing-grammar beat vocabulary. Every beat is now SUPPORTED:
# hero/title/cta/two_panel/reaction render as a single or paired card,
# four_row as a real 4-slot layout, index_grid as a real 3x5 grid (see
# _chain_four_row_beats/_chain_index_grid_beats below), and checklist as a
# real persistent header strip (see _cap_checklist_items below / node type
# "checklist_item" — scene_graph.layout excludes it from ordinary
# chaptering entirely, so it needs no grouping edges of its own).
SUPPORTED_BEATS = ("hero", "title", "two_panel", "reaction", "cta", "four_row", "index_grid", "checklist")
DEFERRED_BEATS = ()
KNOWN_BEATS = SUPPORTED_BEATS + DEFERRED_BEATS

# Only this many grid cells exist (layout.SLOT_TEMPLATE_GRID_15).
INDEX_GRID_MAX_ITEMS = 15
# Matches layout.CHECKLIST_MAX_ITEMS — the checklist strip's own cap.
CHECKLIST_MAX_ITEMS = 15
# scene_graph.schema.KNOWN_NODE_TYPES' checklist-only type — excluded from
# ordinary chaptering by scene_graph.layout (same as "anchor").
_CHECKLIST_NODE_TYPE = "checklist_item"

RELATIONSHIP_TYPES = ("causation", "dependency", "consequence", "transformation", "mechanism", "process")

# beat -> default `role` when a row leaves `role` blank, so a hero/title/cta
# beat naturally claims the WEIGHTED template's wider slot when paired with
# a supporting node (see layout._ELEVATED_ROLE_KEYWORDS).
_BEAT_DEFAULT_ROLE = {"hero": "hero", "title": "hero", "cta": "hero", "reaction": "reaction"}

_VIDEO_ASSET_TYPES = {"flow_video", "stock_video", "youtube"}


def _get(row: Mapping[str, str], key: str) -> str:
    return str(row.get(key, "") or "").strip()


def _node_type_for(asset_type: str) -> str:
    return "video_loop" if asset_type.lower() in _VIDEO_ASSET_TYPES else "image"


@dataclasses.dataclass
class ExpSolarCompileResult:
    ok: bool
    scene_graph: Optional[SceneGraph]
    errors: List[str]
    warnings: List[str]
    source: str = "exp_solar_csv"


def validate_exp_solar_csv(csv_rows: Sequence[Mapping[str, str]]) -> List[str]:
    """Structural validation only: required columns + known-vocabulary
    checks for `beat`/`relationship_type`. Dangling edge references (e.g. a
    relationship_to that names a node_id that's never defined) are still
    caught downstream by compile_overscaled_csv/SceneGraph.validate() —
    not duplicated here."""
    errors: List[str] = []
    if not csv_rows:
        return ["Exp Solar CSV has no rows"]
    for col in REQUIRED_COLUMNS:
        if col not in csv_rows[0]:
            errors.append(f"Exp Solar CSV missing required column '{col}'")
    if errors:
        return errors
    for index, row in enumerate(csv_rows):
        beat = _get(row, "beat").lower()
        if beat and beat not in KNOWN_BEATS:
            errors.append(f"row {index + 1}: unknown beat {beat!r} — expected one of {', '.join(KNOWN_BEATS)}")
        rel_type = _get(row, "relationship_type").lower()
        if rel_type and rel_type not in RELATIONSHIP_TYPES:
            errors.append(
                f"row {index + 1}: unknown relationship_type {rel_type!r} — "
                f"expected one of {', '.join(RELATIONSHIP_TYPES)} (or leave blank)"
            )
    return errors


def _adapt_row(row: Mapping[str, str], index: int, warnings: List[str]) -> Dict[str, str]:
    scene_number = _get(row, "scene_number") or str(index + 1)
    beat = _get(row, "beat").lower() or "hero"
    if beat in DEFERRED_BEATS:
        warnings.append(
            f"row {index + 1} (scene {scene_number}): beat={beat!r} is not renderable yet "
            f"(the layout engine supports at most 3 simultaneous cards) — treated as an "
            f"independent single-card reveal for now."
        )

    node_id = _get(row, "node_id") or f"n{scene_number}"
    role = _get(row, "role") or _BEAT_DEFAULT_ROLE.get(beat, "")
    asset_type = _get(row, "asset_type")
    node_type = _node_type_for(asset_type) if asset_type else "image"
    node_label = _get(row, "node_label")

    if beat == "checklist":
        # A checklist row declares ONE of the persistent strip's items —
        # never an ordinary visible card (scene_graph.layout excludes
        # "checklist_item" nodes from chaptering entirely). Reuses existing
        # columns for identity, per spec: node_label if given (the
        # existing "short 1-3 word tag" column — the natural fit for a
        # compact strip cell), else the row's own chapter text, else a
        # generic "Item N" — never fabricated beyond that.
        node_type = _CHECKLIST_NODE_TYPE
        if not node_label:
            node_label = _get(row, "chapter") or f"Item {scene_number}"

    out: Dict[str, str] = {
        "scene_number": scene_number,
        "script_segment": _get(row, "script_segment"),
        "node_id": node_id,
        "node_type": node_type,
        "role": role,
        "asset_type": asset_type,
        "prompt": _get(row, "prompt"),
        "caption": _get(row, "caption"),
        "highlight": _get(row, "highlight"),
        "node_label": node_label,
        "chapter_title": _get(row, "chapter"),
    }

    relationship_to = _get(row, "relationship_to")
    if relationship_to:
        out["edge_from"] = node_id
        out["edge_to"] = relationship_to
        out["edge_style"] = "sequential"  # never auto-promoted to "callout" — see module docstring
        rel_label = _get(row, "relationship_label") or _get(row, "relationship_type")
        if rel_label:
            out["edge_label"] = rel_label

    return out


def _chain_four_row_beats(csv_rows: Sequence[Mapping[str, str]], adapted_rows: List[Dict[str, str]]) -> None:
    """Consecutive rows sharing beat='four_row' are chained together with
    invisible "group" edges (kind="group" — see overscaled_csv.py's
    edge_kind handling / layout.py's edge-window loop) so
    layout.compute_layout's chaptering (connected components of the edge
    graph — see layout._connected_chapters) puts them on screen together
    as one 4-slot composition, instead of 4 unrelated single cards.

    A row that already defines its own relationship (relationship_to) is
    left untouched — any edge, causal or group, already groups its
    endpoints into one chapter, so an explicit author-chosen relationship
    naturally does the same job and is never overwritten."""
    prev_node_id: Optional[str] = None
    for index, raw in enumerate(csv_rows):
        beat = _get(raw, "beat").lower() or "hero"
        if beat != "four_row":
            prev_node_id = None
            continue
        node_id = adapted_rows[index]["node_id"]
        if prev_node_id is not None and "edge_to" not in adapted_rows[index]:
            adapted_rows[index]["edge_from"] = node_id
            adapted_rows[index]["edge_to"] = prev_node_id
            adapted_rows[index]["edge_style"] = "group"
        prev_node_id = node_id


def _chain_two_panel_beats(
    csv_rows: Sequence[Mapping[str, str]], adapted_rows: List[Dict[str, str]], warnings: List[str],
) -> None:
    """A two_panel split is inherently PAIRWISE — always exactly 2 cards,
    never a longer chain like four_row/index_grid. Consecutive beat=
    'two_panel' rows are paired off two at a time (row i + row i+1, then
    row i+2 + row i+3, ...) with an invisible "group" edge (same kind
    four_row uses — never drawn as an arrow), so each pair becomes its
    own 2-panel chapter. This is what actually makes two_panel usable
    without forcing the author to invent a fake causal relationship just
    to get two cards on screen together — a real comparison (e.g. "Mars's
    atmosphere" vs "Earth's atmosphere") has no cause/effect relationship
    at all, so relationship_to should correctly stay blank; grouping still
    has to happen somehow, and this is that somehow.

    A row that already defines its own relationship (relationship_to) is
    left untouched. An odd one out at the end of a run (no partner) is
    left as an independent single card, with a warning — never silently
    dropped."""
    i = 0
    n = len(csv_rows)
    while i < n:
        beat = _get(csv_rows[i], "beat").lower() or "hero"
        if beat != "two_panel":
            i += 1
            continue
        run_start = i
        while i < n and (_get(csv_rows[i], "beat").lower() or "hero") == "two_panel":
            i += 1
        run = list(range(run_start, i))
        for pair_index in range(0, len(run) - 1, 2):
            first_idx, second_idx = run[pair_index], run[pair_index + 1]
            if "edge_to" in adapted_rows[second_idx]:
                continue
            first_node_id = adapted_rows[first_idx]["node_id"]
            second_node_id = adapted_rows[second_idx]["node_id"]
            adapted_rows[second_idx]["edge_from"] = second_node_id
            adapted_rows[second_idx]["edge_to"] = first_node_id
            adapted_rows[second_idx]["edge_style"] = "group"
        if len(run) % 2 == 1:
            leftover = run[-1]
            scene_number = _get(csv_rows[leftover], "scene_number") or str(leftover + 1)
            warnings.append(
                f"row {leftover + 1} (scene {scene_number}): beat='two_panel' has no pairing "
                f"partner (odd number of two_panel rows in this run) — rendered as an "
                f"independent single card."
            )


def _chain_index_grid_beats(
    csv_rows: Sequence[Mapping[str, str]], adapted_rows: List[Dict[str, str]], warnings: List[str],
) -> None:
    """Consecutive rows sharing beat='index_grid' are chained together
    with invisible "group_grid" edges (kind="group_grid" — see
    overscaled_csv.py's edge_kind handling / layout.py's edge-window loop
    and _is_grid_chapter) so layout.compute_layout puts all of them on
    screen together in a real, fixed 3x5 grid, instead of 15 unrelated
    single cards. Caps a run at INDEX_GRID_MAX_ITEMS (15, matching the
    number of grid cells that actually exist) — any further consecutive
    index_grid rows start a fresh, separate grid chapter instead of
    silently overflowing one that has no 16th cell.

    A row that already defines its own relationship (relationship_to) is
    left untouched — same convention as _chain_four_row_beats."""
    prev_node_id: Optional[str] = None
    run_length = 0
    for index, raw in enumerate(csv_rows):
        beat = _get(raw, "beat").lower() or "hero"
        if beat != "index_grid":
            prev_node_id = None
            run_length = 0
            continue
        run_length += 1
        if run_length > INDEX_GRID_MAX_ITEMS:
            scene_number = _get(raw, "scene_number") or str(index + 1)
            warnings.append(
                f"row {index + 1} (scene {scene_number}): beat='index_grid' run exceeds "
                f"{INDEX_GRID_MAX_ITEMS} items — only the first {INDEX_GRID_MAX_ITEMS} "
                f"consecutive index_grid rows form one 3x5 grid; this row starts a new, "
                f"separate grid instead."
            )
            prev_node_id = None
            run_length = 1
        node_id = adapted_rows[index]["node_id"]
        if prev_node_id is not None and "edge_to" not in adapted_rows[index]:
            adapted_rows[index]["edge_from"] = node_id
            adapted_rows[index]["edge_to"] = prev_node_id
            adapted_rows[index]["edge_style"] = "group_grid"
        prev_node_id = node_id


def _cap_checklist_items(
    csv_rows: Sequence[Mapping[str, str]], adapted_rows: List[Dict[str, str]], warnings: List[str],
) -> None:
    """Only the first CHECKLIST_MAX_ITEMS (15) beat='checklist' rows across
    the WHOLE CSV become checklist_item nodes. Unlike four_row/index_grid,
    checklist rows don't need to be consecutive — the realistic authoring
    pattern is one checklist row opening each later chapter's content
    elsewhere in the CSV (e.g. "checklist row for item 3" then several
    ordinary hero/two_panel rows for item 3's actual content, then the
    checklist row for item 4, ...), so this scans the whole CSV in order
    rather than looking for a run. A row beyond the 15th falls back to an
    ordinary node (per its own asset_type, same as if beat had been left
    unset) with a warning — never silently dropped."""
    seen = 0
    for index, raw in enumerate(csv_rows):
        beat = _get(raw, "beat").lower() or "hero"
        if beat != "checklist":
            continue
        seen += 1
        if seen > CHECKLIST_MAX_ITEMS:
            scene_number = _get(raw, "scene_number") or str(index + 1)
            warnings.append(
                f"row {index + 1} (scene {scene_number}): beat='checklist' exceeds "
                f"{CHECKLIST_MAX_ITEMS} items — only the first {CHECKLIST_MAX_ITEMS} "
                f"checklist rows become checklist items; this row is treated as an "
                f"ordinary hero-style reveal instead."
            )
            asset_type = adapted_rows[index].get("asset_type", "")
            adapted_rows[index]["node_type"] = _node_type_for(asset_type) if asset_type else "image"


@dataclasses.dataclass
class ExpSolarAdaptedRows:
    ok: bool
    rows: List[Dict[str, str]]
    errors: List[str]
    warnings: List[str]


def adapt_exp_solar_csv_rows(csv_rows: Sequence[Mapping[str, str]]) -> ExpSolarAdaptedRows:
    """Validate + adapt Exp Solar CSV rows into Overscaled-CSV-shaped row
    dicts, WITHOUT compiling them — exactly the shape compile_overscaled_csv
    (and anything that calls it, e.g. scene_graph.pipeline.run_overscaled_pipeline
    via scene_graph.app_integration.generate_overscaled_video) expects
    directly as its own ``csv_rows`` input. This is the single shared
    adaptation step: both compile_exp_solar_csv (the Visual Plan preview
    path) and the real render path use these exact same adapted rows, so
    what the operator reviews in the Visual Plan is what actually renders."""
    errors = validate_exp_solar_csv(csv_rows)
    if errors:
        return ExpSolarAdaptedRows(ok=False, rows=[], errors=errors, warnings=[])

    warnings: List[str] = []
    adapted_rows = [_adapt_row(row, i, warnings) for i, row in enumerate(csv_rows)]
    _chain_two_panel_beats(csv_rows, adapted_rows, warnings)
    _chain_four_row_beats(csv_rows, adapted_rows)
    _chain_index_grid_beats(csv_rows, adapted_rows, warnings)
    _cap_checklist_items(csv_rows, adapted_rows, warnings)
    return ExpSolarAdaptedRows(ok=True, rows=adapted_rows, errors=[], warnings=warnings)


def compile_exp_solar_csv(
    csv_rows: Sequence[Mapping[str, str]],
    *,
    segment_id: str,
    title: str = "",
) -> ExpSolarCompileResult:
    """Exp Solar CSV -> adapt_exp_solar_csv_rows() -> compile_overscaled_csv()
    -> SceneGraph.

    Never raises. Structural problems are returned as ok=False with clear
    error strings, exactly like compile_overscaled_csv. Always compiles
    under style_preset="exp_solar" — an Exp Solar CSV is only ever meant to
    render with the Exp Solar style."""
    adapted = adapt_exp_solar_csv_rows(csv_rows)
    if not adapted.ok:
        return ExpSolarCompileResult(ok=False, scene_graph=None, errors=adapted.errors, warnings=[])

    result: SceneGraphGenerationResult = compile_overscaled_csv(
        adapted.rows, segment_id=segment_id, title=title, style_preset="exp_solar",
    )
    return ExpSolarCompileResult(
        ok=result.ok, scene_graph=result.scene_graph, errors=result.errors,
        warnings=adapted.warnings, source="exp_solar_csv",
    )
