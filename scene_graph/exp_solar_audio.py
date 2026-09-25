"""Exp Solar's sound design layer — deterministic SFX/ambience event
planning + a final audio mix, built ENTIRELY on the EXISTING smart_editing
SFX/ambience catalog and FFmpeg mixing pipeline (``smart_editing.SfxCatalog``,
``smart_editing.mix_sfx_with_narration``). No second audio engine, no
second FFmpeg renderer, no second asset/cache system — this module is
purely a small, Exp-Solar-specific EVENT PLANNER that hands off to
infrastructure the normal (non-Overscaled) pipeline already uses in
production.

    SceneGraph + SceneGraphLayout (already compiled/laid out for this
    segment, before rendering)
        -> plan_exp_solar_audio_events()   deterministic visual-event list,
                                            derived from data already on
                                            the SceneGraph/layout — never
                                            re-parses the CSV, never adds
                                            randomness
        -> _select_events_for_sfx()        budgeted + minimum-gap-enforced
                                            subset ("do not SFX every cut")
        -> smart_editing.SfxCatalog.match() a real catalog entry per event,
                                            reusing smart_editing's own
                                            tag/intensity scoring — an
                                            event with no match is simply
                                            dropped, never fabricated
        -> smart_editing.mix_sfx_with_narration()  the final mixed WAV,
                                            reusing the EXISTING loop/fade/
                                            duck/normalize FFmpeg pipeline
                                            (narration stays dominant by
                                            construction — see that
                                            function's own docstring)

Only ever called from scene_graph.app_integration.generate_overscaled_video,
gated on ``style_preset_id == "exp_solar"``. Overscaled's own plain
voiceover mux is completely untouched — nothing here runs for it.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import smart_editing as se

from .layout import SceneGraphLayout
from .schema import SceneGraph

# Visual-event kind -> (SFX category, intensity) — reuses smart_editing's
# EXISTING SFX_CATEGORIES vocabulary (see smart_editing.SFX_CATEGORIES),
# never a new taxonomy. "impact" for the major, rare moments (a new
# chapter/topic, the once-per-video index board); "transition"/"whoosh"
# for the more frequent four_row/reaction beats; "ui" for a checklist
# state tick — a small, distinct sound, not a whoosh.
_EVENT_SFX_CATEGORY: Dict[str, str] = {
    "chapter_entry": "impact",
    "index_grid": "impact",
    "four_row": "transition",
    "checklist": "ui",
    "reaction": "whoosh",
}
_EVENT_INTENSITY: Dict[str, str] = {
    "chapter_entry": "high",
    "index_grid": "high",
    "four_row": "medium",
    "checklist": "low",
    "reaction": "low",
}
# Higher-priority kinds win when the gap/budget rules below would
# otherwise have to choose between two nearby candidates.
_EVENT_PRIORITY: Dict[str, int] = {
    "chapter_entry": 0, "index_grid": 0, "four_row": 1, "checklist": 2, "reaction": 2,
}

MIN_SFX_GAP_S = 1.5  # never two SFX closer together than this
MAX_SFX_FRACTION = 0.6  # never SFX on every detected event
_MAX_AVOID_MEMORY = 4  # bounds repetition-avoidance lookback, not unlimited


@dataclasses.dataclass(frozen=True)
class ExpSolarAudioEvent:
    kind: str
    at: float


def plan_exp_solar_audio_events(scene_graph: SceneGraph, layout: SceneGraphLayout) -> List[ExpSolarAudioEvent]:
    """Deterministic list of meaningful visual events, derived entirely
    from data compile_overscaled_csv/compute_layout already produced for
    this segment — same SceneGraph + same layout always yields the same
    event list, in the same order."""
    events: List[ExpSolarAudioEvent] = []

    for cue in scene_graph.title_cues:
        events.append(ExpSolarAudioEvent("chapter_entry", max(0.0, float(cue.at))))

    node_by_id = {n.id: n for n in scene_graph.nodes}
    for members in layout.chapters:
        member_set = set(members)
        kinds = {
            e.kind for e in scene_graph.edges
            if e.from_node in member_set and e.to_node in member_set
        }
        starts = [float(node_by_id[m].appear_at) for m in members if m in node_by_id]
        if not starts:
            continue
        start = min(starts)
        if "group_grid" in kinds:
            events.append(ExpSolarAudioEvent("index_grid", start))
        elif "group" in kinds:
            events.append(ExpSolarAudioEvent("four_row", start))

    for _label, start, _end in layout.checklist_windows:
        events.append(ExpSolarAudioEvent("checklist", max(0.0, float(start))))

    for node in scene_graph.nodes:
        if str(node.semantic_role or "").lower() == "reaction":
            events.append(ExpSolarAudioEvent("reaction", max(0.0, float(node.appear_at))))

    events.sort(key=lambda e: (e.at, e.kind))
    return events


def _select_events_for_sfx(
    events: Sequence[ExpSolarAudioEvent],
    *,
    min_gap_s: float = MIN_SFX_GAP_S,
    max_fraction: float = MAX_SFX_FRACTION,
) -> List[ExpSolarAudioEvent]:
    """Restraint rules, applied deterministically: never SFX on every
    detected event (budgeted to at most ``max_fraction`` of them) and
    never two SFX closer together than ``min_gap_s`` — higher-priority
    kinds (chapter/index moments) are considered first, so a major moment
    always wins a nearby lower-priority one rather than being crowded out
    by scan order."""
    if not events:
        return []
    budget = max(1, round(len(events) * max_fraction))
    ordered = sorted(events, key=lambda e: (_EVENT_PRIORITY.get(e.kind, 3), e.at))

    selected: List[ExpSolarAudioEvent] = []
    selected_times: List[float] = []
    for event in ordered:
        if len(selected) >= budget:
            break
        if any(abs(event.at - t) < min_gap_s for t in selected_times):
            continue
        selected.append(event)
        selected_times.append(event.at)
    selected.sort(key=lambda e: e.at)
    return selected


def build_exp_solar_sfx_events(
    scene_graph: SceneGraph, layout: SceneGraphLayout, *, sfx_root: Optional[Path] = None,
) -> List[dict]:
    """Detected events -> budgeted subset -> real smart_editing catalog
    entries -> smart_editing-shaped SFX event dicts (see
    smart_editing._entry_to_event / mix_sfx_with_narration). An event with
    no matching catalog entry — including an entirely empty/missing
    catalog — is silently skipped; this never fails the render."""
    events = plan_exp_solar_audio_events(scene_graph, layout)
    selected = _select_events_for_sfx(events)
    if not selected:
        return []

    catalog = se.get_sfx_catalog(root=sfx_root)
    if len(catalog) == 0:
        return []

    # "low" on both axes — this is punctuation under narration, not a
    # second voice or a music bed; reuses smart_editing's own tuned
    # intensity->volume table rather than inventing new numbers.
    settings = se.SmartEditingSettings(intensity="low")
    volume = min(se._sfx_base_volume(settings), 0.22)

    sfx_events: List[dict] = []
    avoid_ids: List[str] = []
    for event in selected:
        category = _EVENT_SFX_CATEGORY.get(event.kind, "whoosh")
        intensity = _EVENT_INTENSITY.get(event.kind, "medium")
        request = se.SfxRequest(event.kind, category, (), intensity, None)
        entry = catalog.match(request, avoid_ids=avoid_ids)
        if entry is None:
            continue
        sfx_events.append(se._entry_to_event(entry, request, start=event.at, volume=volume))
        avoid_ids.append(entry.id)
        if len(avoid_ids) > _MAX_AVOID_MEMORY:
            avoid_ids.pop(0)
    return sfx_events


def build_exp_solar_ambience_beds(duration: float, *, sfx_root: Optional[Path] = None) -> List[dict]:
    """At most ONE continuous ambience/music bed spanning the whole
    segment — no per-scene profile switching (that is the normal
    pipeline's own, considerably larger feature; out of scope for this
    minimal layer). Returns [] whenever the catalog has no "ambience"
    entry at all — no music/ambience is required for a valid render."""
    if duration <= 0:
        return []
    catalog = se.get_sfx_catalog(root=sfx_root)
    if len(catalog) == 0:
        return []
    settings = se.SmartEditingSettings(intensity="low")
    request = se.SfxRequest("exp_solar_ambience", "ambience", (), settings.ambience_intensity(), duration)
    entry = catalog.match(request)
    if entry is None:
        return []
    # Ambience is a quiet bed under narration+SFX, not a competing layer —
    # cap it below smart_editing's own "low" tier (0.14) for good measure.
    volume = min(settings.ambience_volume(), 0.12)
    event = se._entry_to_event(entry, request, start=0.0, volume=volume)
    # Override the catalog entry's own (short) native duration with the
    # FULL segment length — smart_editing's ambience mixer already loops
    # the source file (-stream_loop -1) and trims to this "duration", so
    # this is what actually makes the bed span the whole segment rather
    # than just the asset's own few seconds.
    event["duration"] = round(duration, 3)
    event["end"] = round(duration, 3)
    return [event]


def build_exp_solar_audio_mix(
    scene_graph: SceneGraph,
    layout: SceneGraphLayout,
    *,
    voiceover_path: Path,
    output_path: Path,
    sfx_root: Optional[Path] = None,
) -> Path:
    """The single entry point scene_graph.app_integration calls: narration
    + selected SFX + an optional ambience bed -> ONE final mixed WAV, via
    the EXISTING smart_editing.mix_sfx_with_narration FFmpeg pipeline
    (which already keeps narration dominant, ducks/caps ambience and SFX
    volume, loops/fades the ambience bed, and falls back to a plain copy
    of the narration if nothing resolves or mixing itself fails — never
    raises past this function). Never alters narration timing: the output
    is always exactly the narration's own duration (plus the fixed 0.25s
    tail margin ``mix_sfx_with_narration`` already applies)."""
    sfx_events = build_exp_solar_sfx_events(scene_graph, layout, sfx_root=sfx_root)
    ambience_beds = build_exp_solar_ambience_beds(float(scene_graph.duration), sfx_root=sfx_root)
    return se.mix_sfx_with_narration(
        voiceover_path, sfx_events, output_path, sfx_root=sfx_root, ambience_beds=ambience_beds,
    )
