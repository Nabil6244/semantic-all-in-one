"""Overscaled SceneGraph generation from the EXISTING production CSV contract.

    Existing CSV (scene_number, script_segment, asset_type, prompt)
        -> providers.base.SceneRow (existing, unchanged)
        -> SceneGraph semantic intent (this module)
        -> [not implemented yet: layout / composition / EditorialTimeline]

This module does not read or parse CSV files itself — it consumes
``providers.base.SceneRow`` objects, the SAME normalized row type the
existing renderer/router already use, so the CSV contract and its parser
(``csv.DictReader`` + ``SceneRow.from_csv_row``) are untouched.

Three independent generation paths, all returning the same
``SceneGraphGenerationResult`` shape so callers never have to special-case:

  - ``generate_scene_graph_heuristic`` — deterministic, no network, no LLM.
    Maps each SceneRow's existing asset_type/prompt into a SceneNode, derives
    a semantic_role, and links a simple "design flaw -> consequence" causal
    edge when narration signals it. Always available; used as the safe
    fallback and for tests.

  - ``generate_scene_graph_local_planner`` — the Local Visual Planner MVP.
    Same deterministic/offline guarantee as the heuristic path, but drops the
    CSV-shaped expectations entirely: it needs only
    ``scene_number``/``script_segment`` per row (``asset_type``/``prompt``
    stay optional), assigns node ids from row POSITION rather than any
    external id, and infers three levels of narration-only semantic
    structure, all gated on explicit linguistic evidence so a weak/absent
    signal never fabricates a relationship: (1) pairwise causal/mechanism/
    comparison edges between adjacent rows, (2) related-collection or
    genuine-ordered-sequence GROUPS spanning 3-15 rows (reusing Exp Solar's
    own pre-existing "group"/"group_grid" edge-kind convention), and (3)
    continuation rows (short, low-opportunity, pronoun-led) that get no new
    node at all, so the previous visual simply stays on screen. It does not
    decide pixel layout, camera motion, or which composition "shape" (hero/
    two_panel/grid/...) a chapter renders as — that remains entirely the job
    of the unchanged ``scene_graph/layout.py``, which already infers
    chapter/slot structure from the resulting node/edge graph.

  - ``generate_scene_graph_with_llm`` — an ISOLATED Overscaled adapter around
    the existing ``visual_director.llm.LLMProvider`` protocol (the same
    ``complete(system, user) -> str`` seam ``GeminiLLM``/``StaticLLM`` already
    implement). It never imports or touches ``visual_director/director.py``,
    never changes its global prompt, and never touches the ``VisualScene``
    contract — this is a separate prompt/schema entirely. Model output is
    required to be SceneGraph-shaped JSON and is rejected (not silently
    accepted) unless it round-trips through ``SceneGraph.from_dict`` and
    passes ``SceneGraph.validate()`` cleanly.

``generate_scene_graph`` ties them together: try the injected LLM (if any),
fall back to the heuristic generator on ANY failure (bad JSON, invalid
SceneGraph, network/auth error). Nothing here can break the existing
pipeline — on failure it returns a result with ``ok=False`` and the caller
decides what to do; it never raises past this module and never fabricates a
SceneGraph from incomplete data.
"""

from __future__ import annotations

import dataclasses
import json
import re
from typing import Dict, List, Optional, Sequence, Tuple

from providers.base import SceneRow
from visual_director.llm import LLMError, LLMProvider

from .schema import (
    CameraKeyframe,
    CaptionSpec,
    SceneEdge,
    SceneGraph,
    SceneGraphAction,
    SceneGraphBeat,
    SceneNode,
    TitleCue,
)

# --- asset_type -> node.type -------------------------------------------------
# Preserves the EXISTING asset contract values verbatim in SceneNode.asset_source;
# this table only decides the composition node "shape", never the source itself.
_IMAGE_NODE_TYPES = frozenset(
    {"image", "flow_image", "stock_image", "commons_image", "local_image", "local", ""}
)
_VIDEO_LOOP_NODE_TYPES = frozenset(
    {
        "video",
        "flow_video",
        "stock_video",
        "youtube_video",
        "archive_video",
        "nasa_video",
        "commons_video",
        "local_video",
        "stock",
    }
)

_DIAGRAM_KEYWORDS = ("diagram", "schematic", "cross section", "cross-section", "blueprint")
_DESIGN_FLAW_KEYWORDS = (
    "but ", "however", "problem", "flaw", "too narrow", "too small", "too weak",
    "couldn't", "could not", "wasn't enough", "was not enough", "failed to",
    "not enough", "not strong enough",
)
_ARCHIVAL_ASSET_TYPES = frozenset(
    {"youtube_video", "archive_video", "nasa_video", "commons_video", "commons_image"}
)

WORDS_PER_SECOND = 2.5  # ~150 wpm narration pace; a placeholder ordering signal
MIN_ROW_DURATION_S = 1.5


def _node_type_for_asset_type(asset_type: str) -> str:
    key = str(asset_type or "").strip().lower()
    if key in _VIDEO_LOOP_NODE_TYPES:
        return "video_loop"
    return "image"  # covers _IMAGE_NODE_TYPES and any unrecognized value (safe default)


def _has_any(text: str, keywords: Sequence[str]) -> Optional[str]:
    lower = str(text or "").lower()
    for kw in keywords:
        if kw in lower:
            return kw
    return None


def _classify_semantic_role(
    *, index: int, total: int, script_segment: str, prompt: str, asset_type: str, node_type: str
) -> str:
    combined = f"{script_segment} {prompt}"
    if _has_any(combined, _DIAGRAM_KEYWORDS):
        return "diagram"
    if _has_any(script_segment, _DESIGN_FLAW_KEYWORDS):
        return "design_flaw"
    if index == 0:
        return "title"
    if total > 1 and index == total - 1:
        return "final_still"
    if str(asset_type or "").strip().lower() in _ARCHIVAL_ASSET_TYPES:
        return "archival"
    if node_type == "video_loop":
        return "video_loop"
    if index <= 2:
        return "establisher"
    return "detail"


def _short_caption_text(script_segment: str, *, max_chars: int = 90) -> str:
    text = str(script_segment or "").strip()
    # First sentence only, for a "short declarative caption" (style guidance,
    # not enforced elsewhere in this module).
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0] if text else ""
    first = first or text
    if len(first) <= max_chars:
        return first
    truncated = first[:max_chars].rsplit(" ", 1)[0]
    return (truncated or first[:max_chars]).rstrip(",;:") + "..."


def _caption_for_row(script_segment: str, *, highlight_keyword: Optional[str]) -> CaptionSpec:
    caption_text = _short_caption_text(script_segment)
    highlight = None
    if highlight_keyword:
        stripped = highlight_keyword.strip()
        # Only ever set a highlight that is a verbatim substring of the
        # caption we actually produced — never fabricate one.
        if stripped and stripped.lower() in caption_text.lower():
            start = caption_text.lower().index(stripped.lower())
            highlight = caption_text[start:start + len(stripped)]
    return CaptionSpec(text=caption_text, highlight=highlight)


@dataclasses.dataclass
class SceneGraphGenerationResult:
    """Uniform outcome for both the heuristic and LLM generation paths.

    ``ok=False`` means the caller should fall back to the existing pipeline
    unchanged — this never raises and never hands back a half-built graph.
    """

    ok: bool
    scene_graph: Optional[SceneGraph]
    errors: List[str]
    source: str  # "heuristic" | "local_planner" | "llm" | "heuristic_fallback_after_llm_failure"


def scene_rows_from_csv_rows(csv_rows: Sequence[dict]) -> List[SceneRow]:
    """Thin pass-through to the EXISTING row normalizer — no new CSV parsing."""

    return [SceneRow.from_csv_row(dict(r)) for r in csv_rows]


def generate_scene_graph_heuristic(
    segment_id: str,
    rows: Sequence[SceneRow],
    *,
    title: str = "",
    style_preset: str = "overscaled",
) -> SceneGraphGenerationResult:
    """Deterministic, network-free SceneGraph generation from existing SceneRows.

    One row maps to at most one SceneNode (this path does not attempt
    semantic decomposition of a sentence into several nodes — that's what
    the LLM path is for); a row with no asset_type and no prompt/stock query
    produces a beat with narration but no visual action ("no visual node").
    """

    total = len(rows)
    nodes: List[SceneNode] = []
    edges: List[SceneEdge] = []
    camera_keyframes: List[CameraKeyframe] = []
    beats: List[SceneGraphBeat] = []

    cursor = 0.0
    pending_flaw_node_id: Optional[str] = None
    pending_flaw_keyword: Optional[str] = None

    for index, row in enumerate(rows):
        script_segment = row.script_segment or ""
        word_count = len(script_segment.split())
        duration = max(MIN_ROW_DURATION_S, word_count / WORDS_PER_SECOND)
        start = cursor
        end = cursor + duration
        cursor = end

        asset_type = row.asset_type or ""
        prompt_or_stock = row.prompt or row.stock or ""
        has_asset_info = bool(asset_type) or bool(prompt_or_stock)

        actions: List[SceneGraphAction] = []
        node_id: Optional[str] = None

        if has_asset_info:
            node_type = _node_type_for_asset_type(asset_type)
            flaw_kw = _has_any(script_segment, _DESIGN_FLAW_KEYWORDS)
            semantic_role = _classify_semantic_role(
                index=index,
                total=total,
                script_segment=script_segment,
                prompt=prompt_or_stock,
                asset_type=asset_type,
                node_type=node_type,
            )

            # A row right after a design_flaw row is its narrative consequence.
            if pending_flaw_node_id is not None:
                semantic_role = "consequence"

            node_id = f"n{row.scene_number or index + 1}"
            caption = _caption_for_row(
                script_segment,
                highlight_keyword=flaw_kw if semantic_role == "design_flaw" else None,
            )
            node = SceneNode(
                id=node_id,
                type=node_type,
                semantic_role=semantic_role,
                asset_source=asset_type,
                asset_reference=prompt_or_stock,
                appear_at=round(start, 4),
            )
            if caption.text:
                node.caption = caption
            nodes.append(node)

            actions.append(SceneGraphAction(type="reveal_node", action_id=f"a_reveal_{node_id}", node_id=node_id))

            if semantic_role == "consequence" and pending_flaw_node_id is not None:
                edge_id = f"e_{pending_flaw_node_id}_{node_id}"
                edges.append(
                    SceneEdge(
                        id=edge_id,
                        from_node=pending_flaw_node_id,
                        to_node=node_id,
                        style="hand_drawn",
                        draw_at=round(start, 4),
                    )
                )
                actions.append(
                    SceneGraphAction(type="draw_edge", action_id=f"a_draw_{edge_id}", edge_id=edge_id)
                )
                pending_flaw_node_id = None
                pending_flaw_keyword = None

            if semantic_role == "design_flaw":
                pending_flaw_node_id = node_id
                pending_flaw_keyword = flaw_kw

            cam_id = f"cam_{row.scene_number or index + 1}"
            zoom = 1.2 if semantic_role in ("diagram", "design_flaw", "consequence", "detail") else 1.0
            camera_keyframes.append(
                CameraKeyframe(
                    keyframe_id=cam_id,
                    at=round(start, 4),
                    frame_nodes=[node_id],
                    zoom=zoom,
                )
            )
            actions.append(
                SceneGraphAction(type="move_camera", action_id=f"a_cam_{cam_id}", camera_keyframe_id=cam_id)
            )

        beats.append(
            SceneGraphBeat(
                beat_id=f"beat_{row.scene_number or index + 1}",
                narration=script_segment,
                start=round(start, 4),
                end=round(end, 4),
                actions=actions,
            )
        )

    scene_graph = SceneGraph(
        segment_id=segment_id,
        title=title,
        style_preset=style_preset,
        duration=round(cursor, 4),
        nodes=nodes,
        edges=edges,
        camera_keyframes=camera_keyframes,
        beats=beats,
    )
    errors = scene_graph.validate()
    return SceneGraphGenerationResult(
        ok=not errors, scene_graph=scene_graph, errors=errors, source="heuristic"
    )


# --- Local Visual Planner MVP ------------------------------------------------
# Script-only, CSV-free, Gemini-free. Reuses the same asset-type/role/caption
# helpers as generate_scene_graph_heuristic above; the only genuinely new
# logic here is conservative relationship (edge) inference from narration
# language and an ending/CTA role tag. See module docstring for the contract.
#
# Deliberately NOT reusing vo_planner.quality/vo_planner.progression by
# import: vo_planner's package __init__ transitively imports vo_analyzer ->
# smart_editing (a large, GUI-adjacent module), which would drag a heavy,
# unrelated import chain into this small/offline planner path for no benefit
# (those modules' inputs are VisualScene/AlignedBeat objects tied to the
# Script-Analyzer/voiceover pipeline, not plain narration text anyway). The
# opportunity-tag technique below follows the same "keyword-family scoring"
# pattern as vo_planner/quality.py:detect_opportunity_tags and
# research/property_visual_intelligence.py's cue-regex approach, generalized
# to plain text with no other module's schema required.

_LOCAL_OPPORTUNITY_TAG_KEYWORDS = (
    "percent", "%", "million", "billion", "reveal", "secret", "truth",
    "finally", "actually", "discovery", "hidden", "explodes", "crashes",
    "launches", "collapses", "because", "therefore", "as a result",
    "compared", "unlike", "versus", "instead of",
)

_COMPARISON_CUES = (
    "unlike", "compared to", "compared with", " versus ", " vs ", " vs. ",
    "instead of", "different from", "in contrast", "on the other hand",
    "rather than",
)
_CAUSAL_CUES = (
    "because", "causes", "caused", "cause of", "leads to", "led to",
    "results in", "resulted in", "therefore", "as a result", "due to",
)
_MECHANISM_CUES = (
    "how it works", "works by", "the mechanism", "the process is",
    "here's how", "here is how", "the way it works",
)
_CTA_KEYWORDS = (
    "subscribe", "hit the bell", "comment below", "click the link",
    "learn more", "sign up", "follow us", "join us", "like and subscribe",
)

# --- PART 1: abbreviation-safe fallback prompt --------------------------------
# Local Visual Planner ONLY. `_short_caption_text` (used by BOTH generation
# paths for captions, and by the pre-hardening planner for its fallback
# prompt) intentionally stays untouched — it is exercised by
# test_scene_graph_generator.py and used for every node's caption regardless
# of which generation path produced it. This is a separate, planner-private
# helper used ONLY for the derived-prompt fallback.
_PLANNER_ABBREVIATIONS = (
    "u.s", "u.k", "u.n", "dr", "mr", "mrs", "ms", "prof", "e.g", "i.e", "etc",
)
_PLANNER_ABBREV_PERIOD_RE = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in _PLANNER_ABBREVIATIONS) + r")\.",
    re.IGNORECASE,
)


def _planner_first_sentence(text: str, *, max_chars: int = 140) -> str:
    """Same "short declarative first sentence" intent as
    ``_short_caption_text``, but abbreviation-safe: a period after a known
    abbreviation (U.S., Dr., etc.) is never mistaken for a sentence end.
    Deterministic, dependency-free (stdlib ``re`` only)."""

    raw = str(text or "").strip()
    if not raw:
        return ""
    # Temporarily swap a protected abbreviation's period for a sentinel byte
    # that the sentence-boundary split below never matches, then restore it —
    # same character count, so max_chars truncation positions stay correct.
    guarded = _PLANNER_ABBREV_PERIOD_RE.sub(lambda m: m.group(1) + "\x00", raw)
    first = re.split(r"(?<=[.!?])\s+", guarded, maxsplit=1)[0] if guarded else ""
    first = (first or guarded).replace("\x00", ".")
    if len(first) <= max_chars:
        return first
    truncated = first[:max_chars].rsplit(" ", 1)[0]
    return (truncated or first[:max_chars]).rstrip(",;:") + "..."


def _detect_relationship(script_segment: str) -> Optional[Tuple[str, str]]:
    """Return (kind, cue) if narration shows strong evidence of a pairwise
    relationship to the immediately preceding node (causal/mechanism/
    comparison); else None. A missing edge is always safer than a wrong one,
    so this only ever matches on explicit language — it never guesses from
    mere adjacency. Collection/sequence groups (3+ rows) are handled
    separately by ``_detect_semantic_groups`` below, not here."""

    lower = f" {str(script_segment or '').lower()} "
    cue = _has_any(lower, _CAUSAL_CUES)
    if cue:
        return "causal", cue
    cue = _has_any(lower, _MECHANISM_CUES)
    if cue:
        return "mechanism", cue
    cue = _has_any(lower, _COMPARISON_CUES)
    if cue:
        return "comparison", cue
    return None


def _conservative_prompt_for_segment(script_segment: str) -> str:
    """Relevance over creativity: a short, abbreviation-safe first-sentence
    extraction (see PART 1 above) rather than an elaborate AI prompt."""

    return _planner_first_sentence(script_segment, max_chars=140)


# --- Prompt intelligence (visual_hint + era grounding) -----------------------
# "Build prompts from semantic understanding... factual and tied to the
# narration. Do not hallucinate unnecessary details." A `visual_hint` CSV
# column (optional creative guidance — see providers.base.SceneRow.
# from_csv_row, which reads it into the existing `.visual_description`
# field) always wins when present, since it's the author's own explicit
# visual intent. Otherwise the derived prompt is the same conservative
# first-sentence extraction, with one small, strictly text-grounded
# addition: an era/year token already PRESENT in the narration (never
# invented) is appended if the truncation would otherwise have dropped it —
# a genuine documentary-realism cue (see final report) without fabricating
# any detail the narration didn't state.
_ERA_RE = re.compile(r"\b(1[6-9]\d0s?|20[0-4]\d0?s?|\d{4})\b")


def _derive_prompt(text: str, visual_hint: str = "") -> str:
    hint = str(visual_hint or "").strip()
    if hint:
        return hint
    base = _conservative_prompt_for_segment(text)
    era_match = _ERA_RE.search(str(text or ""))
    if era_match and era_match.group(0).lower() not in base.lower():
        return f"{base}, {era_match.group(0)}"
    return base


# --- Source-aware prompt derivation --------------------------------------
# "Do not blindly reuse a Flow prompt as a stock search query." A stock
# search box wants a short keyword phrase (what you'd actually type into
# Pexels), never cinematic/generation prose — this pulls the distinctive
# words out of the narration in their original order/casing instead of
# reusing the full-sentence prompt _derive_prompt builds for Flow.
_STOCK_QUERY_TOKEN_RE = re.compile(r"[A-Za-z]{3,}")
_STOCK_QUERY_MAX_WORDS = 6
# Function words that only dilute a stock search (never subject words);
# kept separate from _GENERIC_SUBJECT_WORDS, which also drives the subject-
# diversity memory and must not change behavior there.
_STOCK_QUERY_STOPWORDS = frozenset({
    "about", "above", "across", "after", "against", "along", "among",
    "around", "before", "behind", "below", "beneath", "beside", "between",
    "beyond", "but", "can", "could", "did", "does", "during", "each",
    "even", "ever", "had", "has", "just", "like", "many", "more", "most",
    "much", "nor", "not", "now", "off", "once", "only", "onto", "other",
    "over", "own", "same", "should", "since", "some", "such", "than",
    "through", "too", "toward", "towards", "under", "until", "upon",
    "very", "what", "when", "where", "while", "who", "whom", "why",
    "within", "without", "would", "yet", "been", "being", "who", "our",
    "you", "your", "all", "any", "both", "few", "how", "its", "it's",
})


def _derive_stock_query(text: str, visual_hint: str = "") -> str:
    hint = str(visual_hint or "").strip()
    if hint:
        return hint
    words = []
    for match in _STOCK_QUERY_TOKEN_RE.finditer(str(text or "")):
        word = match.group(0)
        if word.lower() in _GENERIC_SUBJECT_WORDS or word.lower() in _STOCK_QUERY_STOPWORDS:
            continue
        words.append(word)
        if len(words) >= _STOCK_QUERY_MAX_WORDS:
            break
    return " ".join(words) if words else _conservative_prompt_for_segment(text)


def _derive_source_aware_prompt(asset_type: str, text: str, visual_hint: str = "") -> str:
    if asset_type in ("stock_image", "stock_video"):
        return _derive_stock_query(text, visual_hint)
    return _derive_prompt(text, visual_hint)


# --- Visual diversity memory --------------------------------------------
# "If the narration still discusses Hoover Dam, that does NOT mean every
# beat should be another aerial Hoover Dam image." Tracks a small rolling
# window of recently used subject keywords (see _extract_subject_keyword)
# and, only for a DERIVED prompt (never an author-supplied one — an
# explicit CSV prompt/visual_hint is always respected verbatim), appends a
# rotating shot-angle qualifier once the same subject repeats — cheap,
# deterministic, no randomness, and never applied to a video asset (motion
# already differentiates those).
_GENERIC_SUBJECT_WORDS = frozenset({
    "the", "and", "for", "was", "are", "its", "his", "her", "him", "she",
    "this", "that", "these", "those", "then", "also", "meanwhile",
    "because", "therefore", "however", "first", "second", "third", "fourth",
    "fifth", "next", "finally", "here", "there", "with", "from", "into",
    "were", "have", "will", "which", "their", "they",
})
_SUBJECT_TOKEN_RE = re.compile(r"[a-zA-Z]{3,}")
_SHOT_ANGLE_QUALIFIERS = (
    "aerial view", "ground-level view", "close-up detail",
    "wide establishing view", "cross-section view", "worker's perspective",
)
_DIVERSITY_WINDOW = 4


def _extract_subject_keyword(text: str) -> str:
    for tok in _SUBJECT_TOKEN_RE.findall(str(text or "").lower()):
        if tok not in _GENERIC_SUBJECT_WORDS:
            return tok
    return ""


def _diversify_repeated_subject(prompt: str, subject: str, recent_subjects: List[str]) -> str:
    if not subject:
        return prompt
    repeat_count = recent_subjects.count(subject)
    if repeat_count == 0:
        return prompt
    qualifier = _SHOT_ANGLE_QUALIFIERS[(repeat_count - 1) % len(_SHOT_ANGLE_QUALIFIERS)]
    if qualifier.lower() in prompt.lower():
        return prompt
    return f"{prompt}, {qualifier}"


def _remember_subject(recent_subjects: List[str], subject: str) -> None:
    if not subject:
        return
    recent_subjects.append(subject)
    del recent_subjects[:-_DIVERSITY_WINDOW]


# --- Source/type diversity memory ----------------------------------------
# Extends the diversity-memory idea above to source (stock/flow) and visual
# type (image/video) repetition: "avoid stock_video, stock_video, stock_video,
# stock_video ... when meaningful alternatives exist." Only ever nudges a
# WEAK/default decision (see _select_source_intelligently's had_strong_signal)
# — a genuinely evidenced choice (an explicit CSV type, or real suitability
# keywords) is never overridden for variety's sake, matching "do not force
# artificial diversity" / "secondary optimization after semantic relevance".
_ASSET_TYPE_DIVERSITY_RUN = 3  # 3 identical weak defaults in a row -> nudge the 4th
_ASSET_TYPE_ALTERNATE = {
    "image": "stock_image",
    "stock_image": "image",
    "video": "stock_video",
    "stock_video": "video",
}


def _diversify_repeated_asset_type(
    asset_type: str, recent_asset_types: List[str], had_strong_signal: bool
) -> str:
    if had_strong_signal or len(recent_asset_types) < _ASSET_TYPE_DIVERSITY_RUN:
        return asset_type
    if not all(a == asset_type for a in recent_asset_types[-_ASSET_TYPE_DIVERSITY_RUN:]):
        return asset_type
    return _ASSET_TYPE_ALTERNATE.get(asset_type, asset_type)


def _remember_asset_type(recent_asset_types: List[str], asset_type: str) -> None:
    if not asset_type:
        return
    recent_asset_types.append(asset_type)
    del recent_asset_types[:-_ASSET_TYPE_DIVERSITY_RUN]


# --- PART 2B/2C: small/large related collections ------------------------------
# "The system has three main components: A, B, and C." / "Here are the seven
# technologies..." — an intro row announcing N related items, followed by the
# next N narration rows. This expresses SEMANTIC grouping only (which nodes
# belong together); the existing scene_graph/layout.py already has TWO
# distinct, pre-existing edge-kind conventions for exactly this distinction
# (see layout.py's `_is_grid_chapter`/`_chapter_cap`, unmodified here):
#   - kind="group"      -> Exp Solar's own four_row-equivalent grouping
#   - kind="group_grid" -> Exp Solar's own index_grid-equivalent grouping
# Both are INVISIBLE structural edges (no arrow drawn — see layout.py's own
# comment at its edge-window pass) purely used so _connected_chapters groups
# the members into one on-screen chapter; slot/pixel selection remains
# entirely layout.py's job, unchanged. Using these existing values (rather
# than inventing a new one) means zero schema/layout change is needed.
_NUMBER_WORDS: Dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
}
_COLLECTION_NOUNS = (
    "components", "stages", "steps", "forces", "systems", "technologies",
    "reasons", "ways", "factors", "elements", "types", "categories",
    "wonders", "principles", "methods", "tools", "features", "phases",
    "parts", "pillars", "rules", "laws", "stages",
    "challenges", "problems", "reasons", "questions", "ideas", "mistakes", "lessons",
    "secrets", "facts", "dangers", "obstacles", "problems", "phases", "keys", "signs",
)
_COLLECTION_NUMBER_NOUN_RE = re.compile(
    r"\b(" + "|".join(_NUMBER_WORDS) + r"|\d{1,2})\b\s+(?:\w+\s+){0,2}?("
    + "|".join(_COLLECTION_NOUNS) + r")\b",
    re.IGNORECASE,
)
# An announcement/copula phrase — required IN ADDITION to the number+noun
# match above, so a stray "three systems" mention doesn't alone qualify.
# Deliberately excludes "these"/"together"/"combined": those overwhelmingly
# refer BACKWARD to a group already introduced (e.g. a wrap-up sentence like
# "Together these four components allow...") rather than announcing a NEW
# one — including it caused exactly that false re-trigger in testing.
_COLLECTION_SIGNAL_WORDS = (
    "here are", "here is", "there are", "there is", "the following",
    "we will examine", "consists of", "made up of", " has ", " have ",
    " are ", " is ", "shape", "drive", "include", "comprise", "involve",
    "explain",
)


def _detect_collection_intro(script_segment: str) -> Optional[int]:
    """Return an item count (3-15) if this row announces a related
    collection; else None. Requires BOTH a number+collection-noun match AND
    an explicit announcement phrase/copula/colon — conservative by design."""

    lower = f" {str(script_segment or '').lower()} "
    match = _COLLECTION_NUMBER_NOUN_RE.search(lower)
    if not match:
        return None
    token = match.group(1)
    count = _NUMBER_WORDS.get(token)
    if count is None and token.isdigit():
        count = int(token)
    if count is None or count < 3 or count > 15:
        return None
    if ":" not in lower and not _has_any(lower, _COLLECTION_SIGNAL_WORDS):
        return None
    return count


# --- PART 2D: genuine ordered sequence -----------------------------------
# Deliberately NOT the old single-row "first/next/another" cue (removed) —
# that matched on any lone transition word, which is exactly the "every
# 'next' word becomes a new giant chapter" failure mode this hardening pass
# is meant to close. This instead requires a CONTIGUOUS run of ordinal
# markers (start -> continue* -> optional end), so a single stray "another"
# or "next" with no surrounding ordinal structure never creates a group.
_SEQ_START_MARKERS = ("first,", "firstly", "step one", "step 1", "to begin,", "initially,")
_SEQ_CONTINUE_MARKERS = (
    "second,", "secondly", "third,", "thirdly", "fourth,", "fourthly",
    "fifth,", "next,", "then,", "after that,", "step two", "step 2",
    "step three", "step 3", "step four", "step 4", "step five", "step 5",
)
_SEQ_END_MARKERS = ("finally,", "lastly,", "in the end,", "last,")


def _ordinal_marker_kind(script_segment: str) -> Optional[str]:
    lower = f" {str(script_segment or '').lower()} "
    if _has_any(lower, _SEQ_START_MARKERS):
        return "start"
    if _has_any(lower, _SEQ_CONTINUE_MARKERS):
        return "continue"
    if _has_any(lower, _SEQ_END_MARKERS):
        return "end"
    return None


def _detect_semantic_groups(rows: Sequence[SceneRow]) -> Dict[int, dict]:
    """Pre-scan pass over ALL rows: narration-level evidence for a related
    collection (2B/2C) or a genuine ordered sequence (2D) — the only
    multi-row "beat/treatment" structures this MVP infers beyond the single
    pairwise relationships in ``_detect_relationship``. Returns
    ``{row_index: {"role", "group_id", "kind", "relationship", "count"}}``; a
    row absent from the result belongs to no group. First-detected-wins — a
    row already claimed by one group is never reconsidered by the other
    pass, and collections are scanned before sequences.

    This function only produces node/edge INTENT (which rows belong
    together, and the kind of existing edge that expresses it); it computes
    no positions, slots, or coordinates — that remains layout.py's job.
    """

    total = len(rows)
    claimed: Dict[int, dict] = {}

    # --- 2B/2C: collection intro + the following N narration rows ---
    for i, row in enumerate(rows):
        if i in claimed:
            continue
        count = _detect_collection_intro(row.script_segment or "")
        if count is None:
            continue
        available = [j for j in range(i + 1, total) if j not in claimed][:count]
        if len(available) < 2:
            continue  # not enough real rows exist to actually form a group
        kind = "group" if count <= 4 else "group_grid"
        relationship = "collection_small" if count <= 4 else "collection_large"
        claimed[i] = {
            "role": "intro", "group_id": i, "kind": kind,
            "relationship": relationship, "count": count,
        }
        for j in available:
            claimed[j] = {
                "role": "member", "group_id": i, "kind": kind,
                "relationship": relationship, "count": count,
            }

    # --- 2D: genuine ordered sequence (contiguous ordinal markers only) ---
    seq_members: List[int] = []

    def _finalize_sequence() -> None:
        if len(seq_members) >= 3:
            first = seq_members[0]
            # Same size rule as collections: every step of a sequence is on
            # screen together, and a "group" chapter holds at most four
            # cards (Exp Solar's four_row / max_active_per_chapter=4) — a
            # 5+ step sequence as "group" overflowed its layout.
            kind = "group" if len(seq_members) <= 4 else "group_grid"
            claimed[first] = {
                "role": "intro", "group_id": first, "kind": kind,
                "relationship": "sequential_list", "count": len(seq_members),
            }
            for j in seq_members[1:]:
                claimed[j] = {
                    "role": "member", "group_id": first, "kind": kind,
                    "relationship": "sequential_list", "count": len(seq_members),
                }
        seq_members.clear()

    for i, row in enumerate(rows):
        if i in claimed:
            _finalize_sequence()
            continue
        marker = _ordinal_marker_kind(row.script_segment or "")
        if marker == "start":
            _finalize_sequence()
            seq_members.append(i)
        elif marker == "continue" and seq_members:
            seq_members.append(i)
        elif marker == "end" and seq_members:
            seq_members.append(i)
            _finalize_sequence()
        else:
            _finalize_sequence()
    _finalize_sequence()

    return claimed


# --- PART 3: visual persistence (continuation vs new beat) -------------------
# Uses ONLY the existing "no asset info -> beat with no node/actions" shape
# generate_scene_graph_heuristic already has (see its
# `test_row_with_no_asset_info_has_no_visual_actions` test) — a continuation
# row simply doesn't get its own node, so the PREVIOUS node (which already
# has no fixed `duration`, i.e. "persists until segment/camera moves on" per
# its own schema docstring) keeps being shown. No schema field, no layout.py
# change: this is the smallest change that already fits the existing
# contract. See the final report for what a richer version would require.
_CONTINUATION_START_RE = re.compile(
    r"^(it|it's|its|this|that|these|those|they|also|additionally|meanwhile)\b",
    re.IGNORECASE,
)

# A pronoun/connector opening is NEVER enough on its own (adversarial testing
# found real false positives — "It was discovered decades later.",
# "They built a second tunnel nearby." — both start like a continuation but
# introduce a genuinely new event/entity). These two lexical signals catch
# that without any NLP: an indefinite "a/an <second|third|new|different|
# separate>" (or bare "another") noun phrase almost always names something
# NOT yet on screen, and a small set of unambiguous one-time EVENT verbs
# (discovered/abandoned/revealed/founded/...) describe a new narrative beat
# rather than an incidental supporting fact about the subject already shown.
# Deliberately narrow and verb-specific: ordinary/ambiguous verbs like
# "built"/"made"/"moved"/"changed" are NOT included here, because ordinary
# supporting details about the SAME subject also use them (e.g. "It was
# built in 1936." — a genuine continuation about the dam already on screen).
_NEW_ENTITY_MARKER_RE = re.compile(
    r"\b(a|an)\s+(second|third|fourth|fifth|sixth|new|different|separate|nearby)\b|\banother\b",
    re.IGNORECASE,
)
_PIVOTAL_EVENT_VERBS = (
    "discovered", "abandoned", "revealed", "founded", "established",
    "collapsed", "exploded", "launched", "vanished", "disappeared",
    "destroyed", "demolished",
)


def _has_strong_new_content_signal(script_segment: str) -> bool:
    lower = f" {str(script_segment or '').lower()} "
    if _NEW_ENTITY_MARKER_RE.search(lower):
        return True
    return bool(_has_any(lower, _PIVOTAL_EVENT_VERBS))


def _looks_like_continuation(script_segment: str, *, word_count: int) -> bool:
    if word_count > 8 or _local_opportunity_tags(script_segment):
        return False
    stripped = script_segment.strip()
    if not _CONTINUATION_START_RE.match(stripped):
        return False
    if _has_strong_new_content_signal(stripped):
        return False
    return True


def _local_opportunity_tags(text: str) -> List[str]:
    """Conservative visual-opportunity signal (see module note above)."""

    lower = f" {str(text or '').lower()} "
    return [kw for kw in _LOCAL_OPPORTUNITY_TAG_KEYWORDS if kw in lower]


def _classify_local_role(
    *,
    index: int,
    total: int,
    script_segment: str,
    prompt: str,
    asset_type: str,
    node_type: str,
    relationship_kind: Optional[str],
) -> str:
    """Reuses _classify_semantic_role's existing vocabulary (title/
    establisher/detail/diagram/design_flaw/archival/video_loop/final_still)
    and only layers on the two roles that vocabulary has no equivalent for:
    an explicit ending/CTA beat, and the causal/mechanism/comparison labels
    a detected relationship implies."""

    base_role = _classify_semantic_role(
        index=index,
        total=total,
        script_segment=script_segment,
        prompt=prompt,
        asset_type=asset_type,
        node_type=node_type,
    )
    lower = str(script_segment or "").lower()
    if index == total - 1 and _has_any(lower, _CTA_KEYWORDS):
        return "cta"
    if relationship_kind == "causal":
        return "consequence"
    if relationship_kind == "mechanism":
        return "mechanism"
    if relationship_kind == "comparison" and base_role in ("detail", "establisher"):
        return "comparison"
    return base_role


# --- Motion/action asset-type preference --------------------------------
# "Action/mechanism -> prefer flow_video/stock_video" (hardening pass 3):
# only ever fires when the CSV/row left asset_type blank — an explicit CSV
# asset_type always wins untouched. A small, unambiguous verb list (never
# state/persistence verbs like "remained"/"held"/"was" that the continuation
# detector above already treats as neutral) so this stays a high-confidence
# nudge, not a guess.
_MOTION_ACTION_VERBS = (
    "divert", "diverted", "diverting", "excavate", "excavated", "excavating",
    "pour", "poured", "pouring", "flow", "flows", "flowing", "spin", "spins",
    "spinning", "rotate", "rotates", "rotating", "operate", "operates",
    "operating", "launch", "launches", "launching", "explode", "explodes",
    "exploding", "build", "builds", "building", "construct", "constructs",
    "constructing", "collapse", "collapses", "collapsing", "crash", "crashes",
    "crashing", "erupt", "erupts", "erupting", "drill", "drills", "drilling",
    "weld", "welds", "welding", "lift", "lifts", "lifting", "generate",
    "generates", "generating", "convert", "converts", "converting", "shake",
    "shakes", "shaking", "vibrate", "vibrates", "vibrating", "twist",
    "twists", "twisting", "crack", "cracks", "cracking", "carve", "carves",
    "carving", "assemble", "assembles", "assembling",
)


def _infer_motion_asset_type(text: str) -> Optional[str]:
    lower = f" {str(text or '').lower()} "
    return "video" if _has_any(lower, _MOTION_ACTION_VERBS) else None


# --- Source intelligence: stock vs Flow ---------------------------------
# Separate from visual_type (image/video, decided above by
# _infer_motion_asset_type/an explicit CSV "video"/"image"): this decides
# WHICH acquisition source is most suitable for the concept, not merely
# whether motion is involved. Deliberately small/conservative (a handful of
# keyword families, not an exhaustive taxonomy) — ties always resolve to the
# existing, already-proven-safe default (flow_image for a still, flow_video
# for motion) rather than guessing toward stock.
#
# A fully explicit CSV asset_type (stock_image, stock_video, youtube_video,
# local, ...) is NEVER touched by this — see _resolve_asset_type. Only the
# genuinely ambiguous cases (blank, or the generic "image"/"video" legacy
# spelling that SceneRow.from_csv_row already collapses flow_image/
# flow_video down to) are where this intelligence applies at all — a
# generic "image"/"video" hint states the VISUAL TYPE the author wants, not
# which acquisition source, so refining it into a specific stock_*/flow_*
# choice is "improving an underspecified hint", never overriding an
# explicit stock_image/stock_video choice.
_STOCK_VIDEO_SUITABLE_WORDS = (
    "construction", "workers", "worker", "driving", "traffic", "walking",
    "running", "machinery", "manufacturing", "factory", "factories",
    "assembly line", "crowd", "crowds", "city", "cities", "street",
    "transportation", "highway", "train", "airplane", "aircraft", "ship",
    "harbor", "port", "flight", "swimming", "hiking", "wildlife", "animals",
    "forest", "river", "ocean", "waves", "farming", "harvest", "market",
)
_FLOW_IMAGE_SUITABLE_WORDS = (
    "cross section", "cross-section", "diagram", "schematic", "blueprint",
    "cutaway", "mechanism", "conceptual", "concept", "reconstruction",
    "visualization", "illustration", "impossible", "interior view",
    "x-ray", "microscopic", "molecular", "atomic", "abstract", "infographic",
)
_STOCK_IMAGE_SUITABLE_WORDS = (
    "historical photograph", "archival", "portrait", "photograph",
    "landmark", "monument", "skyline", "map", "postcard", "newspaper",
)


def _count_hits(text: str, keywords: Sequence[str]) -> int:
    lower = f" {str(text or '').lower()} "
    return sum(1 for kw in keywords if kw in lower)


def _select_source_intelligently(text: str, visual_hint: str, wants_video: bool) -> Tuple[str, bool]:
    """The suitability decision only — never an availability claim (no
    network/provider call happens here or anywhere in this module). Returns
    (asset_type, had_strong_signal) — the second value gates diversity
    rotation below: a genuinely evidenced choice is never overridden for
    variety's sake, only the weak/default fallback is."""

    blob = f"{text} {visual_hint}".strip()
    stock_video_score = _count_hits(blob, _STOCK_VIDEO_SUITABLE_WORDS)
    flow_image_score = _count_hits(blob, _FLOW_IMAGE_SUITABLE_WORDS)
    stock_image_score = _count_hits(blob, _STOCK_IMAGE_SUITABLE_WORDS)
    if stock_image_score and _ERA_RE.search(blob):
        # An era mention only REINFORCES an already-present documentary/
        # historical signal — it must never be the sole trigger on its own
        # (a plain sentence that happens to state a year, e.g. "Construction
        # began in 1931", is not by itself evidence of an archival photo).
        stock_image_score += 1

    # NOTE: the Flow-source branches deliberately return "video"/"image" —
    # NOT "flow_video"/"flow_image". Those are only CSV-INPUT aliases;
    # providers.base.SceneRow.from_csv_row collapses them to "video"/"image"
    # at parse time, and every downstream consumer (SceneRow.wants_flow_
    # image/wants_flow_video, SceneAssetRouter.classify, the real
    # resolve_scene_assets path) only recognizes the collapsed canonical
    # spelling. A SceneNode built directly (never re-parsed through
    # from_csv_row) must already use that same canonical spelling, or a
    # preview built straight from node.asset_source (see app.py's Visual
    # Plan backfill) would silently fail to classify as Flow at all.
    if wants_video:
        # Real-world action stock can plausibly represent -> stock_video.
        # A concept that ALSO carries a strong conceptual/impossible-shot
        # signal is too specific for stock -> flow video (the existing,
        # already-proven default for motion).
        if stock_video_score > 0 and flow_image_score == 0:
            return "stock_video", True
        return "video", stock_video_score > 0 or flow_image_score > 0

    # Still image: a technical/conceptual visual needs Flow's controlled
    # composition; a recognizable historical/documentary subject is
    # exactly what stock photo libraries are built for; anything else
    # keeps today's proven default.
    if flow_image_score > 0 and flow_image_score >= stock_image_score:
        return "image", True
    if stock_image_score > 0:
        return "stock_image", True
    return "image", False


def _resolve_asset_type_verbose(
    csv_asset_type: str, text: str, visual_hint: str = "", *, has_supplied_prompt: bool = False
) -> Tuple[str, bool]:
    """Returns (asset_type, had_strong_signal). An explicit, fully-specific
    CSV asset_type (stock_image/stock_video/youtube_video/...) is always
    treated as a strong signal and never touched.

    ``has_supplied_prompt``: an "image"/"video" row that ALSO carries its
    own prompt is a fully specified Flow request (this is exactly what the
    Visual Plan's Change Source -> flow_image/flow_video writes into the
    CSV, since SceneRow.from_csv_row collapses the flow_* aliases), never
    a generic hint — refining or diversity-rotating it would make Generate
    silently disagree with what the Visual Plan showed and the user chose."""

    normalized = str(csv_asset_type or "").strip().lower()
    if normalized and normalized not in ("image", "video"):
        return csv_asset_type, True
    if normalized in ("image", "video") and has_supplied_prompt:
        return normalized, True

    wants_video = bool(_infer_motion_asset_type(text) or _infer_motion_asset_type(visual_hint))
    if normalized == "video":
        wants_video = True
    elif normalized == "image":
        wants_video = False
    elif not text and not visual_hint:
        return normalized, True  # nothing to reason about — preserve prior blank behavior, never rotated

    return _select_source_intelligently(text, visual_hint, wants_video)


def _resolve_asset_type(csv_asset_type: str, text: str, visual_hint: str = "") -> str:
    return _resolve_asset_type_verbose(csv_asset_type, text, visual_hint)[0]



# --- Engagement intelligence (captions, highlights, labels, chapters) -------
# Every one of these is an EXISTING renderer/audio feature that a CSV author
# can switch on by hand (Exp Solar/Overscaled CSV: caption, highlight,
# node_label, chapter, relationship_label, beat=reaction). The planner used
# to leave them all empty, so a planner-built video had almost no chapter
# titles, no highlighted keywords, no name tags, unlabeled arrows and no
# reaction beats. Everything below is deterministic and text-grounded: it
# only ever reuses words already present in the narration.
_CAPTION_MAX_WORDS = 14
_GROUP_CAPTION_MAX_WORDS = 9  # narrow cards in a 3-4-up group row
_LEADING_CONNECTOR_RE = re.compile(
    r"^(?:but|and|so|yet|now|then|still|also|meanwhile|however|instead|finally|first|second|third|next|lastly)\b,?\s+",
    re.IGNORECASE,
)
_CLAUSE_BREAK_RE = re.compile(r"[,;:—]|\s(?:which|while|because|so that|where|who|and|or|but)\s", re.IGNORECASE)
_CAPTION_CUT_PREPOSITIONS = frozenset({
    "around", "through", "across", "into", "over", "under", "from", "with", "for", "to", "in", "on",
    "at", "by", "between", "near", "above", "below", "behind", "toward", "towards", "along",
})
# A caption must never END on one of these (a cut mid-phrase reads as broken).
_DANGLING_END_WORDS = frozenset({
    "a", "an", "the", "of", "to", "in", "on", "for", "with", "by", "at", "from", "into", "and", "or",
    "but", "could", "would", "should", "can", "will", "was", "were", "is", "are", "had", "has",
    "have", "be", "been", "its", "their", "his", "her", "that", "which", "who", "made", "very",
})


def _planner_caption(text: str, max_words: int = 14) -> str:
    """A short on-card caption (the renderer wants 6-14 words) cut at a
    natural clause boundary — never mid-phrase with a dangling "for...". The
    first sentence only, without a leading connector ("Then, ...")."""
    sentence = _planner_first_sentence(text, max_chars=400).rstrip(".!?…").strip()
    if sentence.endswith("..."):
        sentence = sentence[:-3].rstrip()
    trimmed = _LEADING_CONNECTOR_RE.sub("", sentence)
    if len(trimmed.split()) >= 3:
        sentence = trimmed[:1].upper() + trimmed[1:]
    sentence = sentence.rstrip(" ,;:")
    words = sentence.split()
    if len(words) <= max_words:
        return sentence
    head = " ".join(words[:max_words])
    min_words = 4 if max_words < _CAPTION_MAX_WORDS else 5
    cuts = [m.start() for m in _CLAUSE_BREAK_RE.finditer(head) if len(head[:m.start()].split()) >= min_words]
    if cuts:
        kept = head[:cuts[-1]].rstrip(" ,;:").split()
    else:
        # No clause break: end before the last prepositional phrase, which
        # keeps a complete thought ("...carried the Colorado River") instead
        # of stopping mid noun phrase ("...around the construction").
        kept = words[:max_words - 1]
        preps = [i for i, w in enumerate(kept) if w.lower() in _CAPTION_CUT_PREPOSITIONS and i >= min_words]
        if preps:
            kept = kept[:preps[-1]]
    # Never end on a dangling modal/article/preposition/participle.
    while len(kept) > min_words and (
        kept[-1].lower().strip(",;:") in (_DANGLING_END_WORDS | _GENERIC_SUBJECT_WORDS)
        or kept[-1].lower().strip(",;:").endswith("ing")
    ):
        kept.pop()
    return " ".join(kept).rstrip(",;:")


_SENTENCE_STARTERS = frozenset({
    "The", "This", "That", "These", "Those", "It", "Its", "A", "An", "But", "And", "So", "Yet",
    "In", "On", "At", "By", "For", "From", "When", "While", "Before", "After", "During", "Once",
    "Here", "There", "Then", "Now", "Today", "Unlike", "Because", "If", "As", "Instead", "What",
    "Why", "How", "Who", "Where", "They", "We", "You", "He", "She", "Some", "Many", "Most",
    "Finally", "First", "Second", "Third", "Next", "Also", "Meanwhile", "However", "Still",
    "Four", "Three", "Two", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Every", "Each",
})
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-zA-Z'\-]+(?:\s+(?:of\s+|the\s+)?[A-Z][a-zA-Z'\-]+)*")
_NUMBER_RE = re.compile(
    r"\b\d[\d,.]*(?:\s?(?:%|percent|million|billion|thousand|tons|feet|foot|km|miles|meters|metres|"
    r"years|degrees|mph|kilometres|kilometers|gallons|acres|people|workers))?\b"
)
_NUMBER_WORD_RE = re.compile(
    r"\b(?:two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|hundred|hundreds|thousand|"
    r"thousands|million|millions|billion|billions)\b(?:\s+(?!of\b|the\b|a\b)[a-z]{3,})?",
    re.IGNORECASE,
)


def _proper_noun_phrases(text: str) -> List[str]:
    """Capitalised names in the narration ("Hoover Dam", "Colorado River",
    "Arizona"). A lone capitalised word at the START of a sentence is just an
    ordinary word ("Engineers", "Giant", "Diverting") and never counts."""
    text = str(text or "")
    found: List[str] = []
    for match in _PROPER_NOUN_RE.finditer(text):
        words = match.group(0).split()
        at_sentence_start = match.start() == 0 or bool(re.search(r"[.!?:]\s*$", text[:match.start()]))
        if words and words[0] in _SENTENCE_STARTERS:
            words = words[1:]
            at_sentence_start = False
        while words and words[-1].lower() in ("of", "the"):
            words = words[:-1]
        if len(words) == 1 and at_sentence_start:
            continue
        if words and words[0].endswith(("'s", "\u2019s")) and len(words) == 1:
            continue
        phrase = " ".join(words)
        if phrase and len(phrase) >= 3 and phrase not in found:
            found.append(phrase)
    return found


_WEAK_EMPHASIS_WORDS = frozenset({
    "therefore", "however", "instead", "extremely", "carefully", "actually", "simply", "almost",
    "something", "everything", "anything", "nothing", "through", "without", "between", "another",
    "because", "although", "whether", "different", "enormous", "massive", "important",
    "behind", "beyond", "around", "across", "toward", "towards", "within", "against", "during",
    "before", "inside", "outside", "beneath", "throughout", "rather", "itself", "themselves",
    "entire", "entirely", "several", "really", "should", "itself", "whole", "always",
})
_NOUN_SUFFIXES = ("tion", "sion", "ment", "ance", "ence", "ity", "ure", "ism", "ness", "ship", "age", "ogy")


def _distinctive_terms(caption: str) -> List[str]:
    """Content words worth emphasising, best first: noun-like words (typical
    noun suffixes, plurals) over others, later in the sentence (usually the
    object) over earlier, longer over shorter. Never -ly/-ing words or filler."""
    words = [w.strip(",.;:!?\"'()") for w in caption.split()]
    scored = []
    for position, word in enumerate(words):
        low = word.lower()
        if (len(word) < 6 or low in _GENERIC_SUBJECT_WORDS or low in _WEAK_EMPHASIS_WORDS
                or low.endswith(("ly", "ing", "ed")) or not word.isalpha()):
            continue
        noun_like = low.endswith(_NOUN_SUFFIXES) or (low.endswith("s") and not low.endswith("ss"))
        # Position dominates (the object near the end usually carries the
        # meaning); a noun-like word gets a few words' head start.
        scored.append((-position - (3 if noun_like else 0), -len(word), word))
    ordered: List[str] = []
    for *_, word in sorted(scored):
        if word not in ordered:
            ordered.append(word)
    return ordered


def _pick_highlight(caption: str, recent: Optional[List[str]] = None) -> Optional[str]:
    """One keyword to emphasise in the caption: a number/year first, then a
    proper name, then the most distinctive long word — skipping whatever the
    previous two captions already highlighted, so emphasis keeps moving."""
    recent_lower = {r.lower() for r in (recent or [])[-2:]}
    recent_words = {w for r in recent_lower for w in r.split()}
    candidates: List[str] = []
    candidates += [m.group(0).strip() for m in _NUMBER_RE.finditer(caption)]
    candidates += [m.group(0).strip() for m in _NUMBER_WORD_RE.finditer(caption)]
    candidates += _proper_noun_phrases(caption)
    candidates += _distinctive_terms(caption)
    for cand in candidates:
        if (cand and cand.lower() not in recent_lower and cand.lower() in caption.lower()
                and not (set(cand.lower().split()) & recent_words)):
            return cand
    return None


_TIME_CLAUSE_RE = re.compile(
    r"^(?:before|after|when|during|once|by|in|until|since|decades later|years later|centuries later|today)\b[^,:;.!?]{2,60}[,:]",
    re.IGNORECASE,
)
_CHAPTER_OPENER_RE = re.compile(
    r"^(?:but the real|but the|before |after |when |during |once |by (?:the )?1\d{3}|in 1\d{3}|"
    r"in the (?:end|beginning)|today|decades later|years later|meanwhile,|the first|the second|the third|"
    r"the next|the final|the last|here's how|here is how|so how|so why|why |what |how did|how does|"
    r"the answer|the problem|the challenge|the solution|the result|the story)",
    re.IGNORECASE,
)
_TITLE_STOP_WORDS = frozenset({
    "is", "was", "were", "are", "be", "been", "had", "has", "have", "could", "would", "will", "can",
    "did", "does", "do", "began", "became", "looks", "look", "seemed", "stood", "happened", "made",
    "created", "carried", "allowed", "changed", "faced", "flowed", "remained", "required", "needed",
    "used", "built", "protects", "generate", "generates", "controlled", "took", "came", "went",
    "moved", "meant", "means", "gave", "helped", "shaped", "holds", "held", "sits", "lies", "runs",
    "ran", "reached", "started", "ended", "turned", "got", "said", "that", "which", "who", "to",
    "must", "should", "might", "may", "work", "works", "it", "they",
    "therefore", "also", "then", "still", "however", "instead", "thus", "soon", "later", "now",
})
_WEAK_TITLE_OPENERS = frozenset({
    "unlike", "because", "if", "although", "while", "since", "whereas", "though", "as",
    "it", "this", "that", "they", "there", "these", "those",
})
_BY_GERUND_RE = re.compile(r"\bby\s+([a-z]+ing\b(?:\s+(?!instead\b|rather\b|which\b|and\b)[\w'\u2019-]+){0,4})", re.IGNORECASE)
_TITLE_SMALL_WORDS = frozenset({"a", "an", "the", "of", "in", "on", "and", "to", "for", "at", "by", "or", "with"})


def _title_case(words: List[str]) -> str:
    out = []
    for i, word in enumerate(words):
        low = word.lower()
        if i and low in _TITLE_SMALL_WORDS:
            out.append(low)
        elif word[:1].isupper() and not word.isupper():
            out.append(word)
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out)


def _chapter_title(text: str) -> str:
    """A short chapter title (2-6 words) from a section's opening line:
    "Before construction began, engineers..." -> "Before Construction Began";
    "But the real story is far more complicated" -> "The Real Story";
    "Here's how it works: ..." -> "Here's How It Works"."""
    sentence = _planner_first_sentence(text, max_chars=400).strip()
    clause = _TIME_CLAUSE_RE.match(sentence)
    if clause and 2 <= len(clause.group(0).split()) <= 6:
        return _title_case(clause.group(0).rstrip(",:").split())
    if re.match(r"^here(?:'s| is)\b", sentence, re.IGNORECASE) and ":" in sentence[:60]:
        return _title_case(sentence.split(":", 1)[0].split())
    by_gerund = _BY_GERUND_RE.search(sentence)
    if by_gerund:
        return _title_case(by_gerund.group(1).strip(" ,.;:").split())
    body = _LEADING_CONNECTOR_RE.sub("", sentence)
    words: List[str] = []
    for raw in body.split():
        word = raw.strip(",.;:!?\"'()")
        if not word:
            continue
        if words and (word.lower() in _TITLE_STOP_WORDS or (len(words) >= 2 and word.lower().endswith("ed"))):
            break
        words.append(word)
        if raw.endswith((",", ";", ":")) or len(words) >= 6:
            break
    if len(words) >= 2:
        return _title_case(words)
    names = _proper_noun_phrases(sentence)
    if names:
        return names[0]
    return _title_case(body.rstrip(".!?").split()[:5])


def _collection_title(text: str) -> str:
    """A list intro's chapter title: its subject plus the announced count —
    "The tunnel project happened in four stages:" -> "The Tunnel Project:
    Four Stages"; "Black Canyon itself created three major challenges:" ->
    "Black Canyon: Three Major Challenges"."""
    subject = _chapter_title(text)
    subject_words = [w for w in subject.split() if w.lower() not in ("itself", "themselves", "itself:")]
    match = _COLLECTION_NUMBER_NOUN_RE.search(str(text or ""))
    if not match:
        return " ".join(subject_words) or subject
    count_phrase = _title_case(match.group(0).split())
    if len(subject_words) >= 2 and count_phrase.lower() not in " ".join(subject_words).lower():
        combined = f"{' '.join(subject_words)}: {count_phrase}"
        if len(combined.split()) <= 8:
            return combined
    return count_phrase


def _decent_title(title: str) -> bool:
    words = title.split()
    return len(words) >= 2 and words[0].lower().strip(",") not in _WEAK_TITLE_OPENERS


_TAB_DROP_WORDS = frozenset({
    "the", "a", "an", "of", "in", "on", "and", "to", "for", "at", "by", "or", "with", "its", "their",
    "before", "after", "when", "during", "once", "until", "since", "today", "began", "begin", "begins",
    "here's", "how", "it", "works", "what", "why", "this", "that", "is", "was", "were", "are",
})
_CHAPTER_TAB_MIN = 3   # a 1-2 tab strip isn't a meaningful progress bar
_CHAPTER_TAB_MAX = 15  # the strip's own capacity (layout.CHECKLIST_MAX_ITEMS)


def _chapter_tab_label(title: str) -> str:
    """1-2 word name for a chapter's tab in the progress strip:
    "Black Canyon: Three Major Challenges" -> "Black Canyon";
    "Changing the River's Path" -> "River's Path"; "Before Construction
    Began" -> "Construction"; "Hoover Dam" -> "Hoover Dam"."""
    head = str(title or "").split(":", 1)[0].strip()
    # (Titles are Title Case, so every word LOOKS like a name — only a head
    # that is already 1-2 words is kept whole; otherwise keep content words.)
    if len(head.split()) <= 2 and not (set(w.lower() for w in head.split()) & _TAB_DROP_WORDS):
        return head
    content = [
        w for w in head.split()
        if w.lower().strip(",.") not in _TAB_DROP_WORDS and not w.lower().endswith("ing")
    ]
    if not content:
        # Only function words ("Here's How It Works"): keep the phrase itself.
        return " ".join(re.sub(r"^here(?:'s| is)\s+", "", head, flags=re.IGNORECASE).split()[:3])
    return " ".join(content[-2:])


def _is_chapter_opener(text: str) -> bool:
    sentence = _planner_first_sentence(text, max_chars=400).strip()
    return bool(_CHAPTER_OPENER_RE.match(sentence)) or sentence.endswith("?")


_REACTION_OPENERS = (
    "imagine", "think about", "picture this", "that's", "that is", "and yet", "but that",
    "it worked", "it failed", "it didn't", "nobody", "no one", "incredibly", "surprisingly",
)


def _is_reaction_line(text: str, word_count: int) -> bool:
    """A short, emphatic beat worth a reaction treatment (Exp Solar adds its
    reaction SFX for this role): an exclamation, a rhetorical question, or a
    punchy "Imagine..."/"That's..." line."""
    stripped = str(text or "").strip()
    if not stripped or word_count > 12:
        return False
    return stripped.endswith(("!", "?")) or stripped.lower().startswith(_REACTION_OPENERS)


_EDGE_LABELS = {"causal": "leads to", "mechanism": "how it works", "comparison": "vs"}
_MIN_ROWS_PER_CHAPTER = 4   # never a new title band every other scene
_MAX_ROWS_PER_CHAPTER = 9   # ...nor a whole section with no title at all

def _build_scene_node(
    *,
    node_id: str,
    index: int,
    total: int,
    text: str,
    appear_at: float,
    csv_asset_type: str,
    csv_prompt: str,
    csv_stock: str,
    scene_number: str,
    relationship_kind: Optional[str],
    visual_hint: str = "",
    recent_subjects: Optional[List[str]] = None,
    recent_asset_types: Optional[List[str]] = None,
    recent_highlights: Optional[List[str]] = None,
    seen_names: Optional[set] = None,
    allow_label: bool = True,
    reaction: bool = False,
    caption_max_words: int = 14,
) -> SceneNode:
    """Shared node-construction body for both the one-node-per-row case and
    each sub-clause of a split compound row (see
    _split_compound_visual_ideas) — identical role/prompt/caption/asset-type
    logic either way, just parameterized on which text/appear_at to use.

    ``visual_hint`` (optional CSV creative guidance) always wins as the
    prompt basis and also feeds asset-type/source inference alongside the
    row's own text. ``recent_subjects``/``recent_asset_types``, when
    passed, enable the two visual-diversity rotations (see module notes
    above) — omitted entirely (e.g. tests that don't care about them)
    simply skips that step, never an error."""

    supplied_prompt = str(csv_prompt or csv_stock or "").strip()
    asset_type, had_strong_signal = _resolve_asset_type_verbose(
        csv_asset_type, text, visual_hint, has_supplied_prompt=bool(supplied_prompt)
    )
    if recent_asset_types is not None:
        asset_type = _diversify_repeated_asset_type(asset_type, recent_asset_types, had_strong_signal)
        _remember_asset_type(recent_asset_types, asset_type)
    prompt = supplied_prompt or _derive_source_aware_prompt(asset_type, text, visual_hint)
    if not supplied_prompt and recent_subjects is not None:
        subject = _extract_subject_keyword(text)
        prompt = _diversify_repeated_subject(prompt, subject, recent_subjects)
        _remember_subject(recent_subjects, subject)
    node_type = _node_type_for_asset_type(asset_type)
    semantic_role = _classify_local_role(
        index=index, total=total, script_segment=text, prompt=prompt,
        asset_type=asset_type, node_type=node_type, relationship_kind=relationship_kind,
    )
    if reaction and semantic_role in ("detail", "establisher", "consequence"):
        semantic_role = "reaction"
    caption_text = _planner_caption(text, max_words=caption_max_words)
    label = ""
    if allow_label and seen_names is not None and semantic_role != "cta":
        # Only a name the card's own caption shows — a tag naming something
        # the viewer can't see on the card reads as an error.
        for name in _proper_noun_phrases(caption_text):
            if name.lower() not in seen_names and len(name) <= 24:
                label = name
                break
    if seen_names is not None:
        seen_names.update(n.lower() for n in _proper_noun_phrases(text))
    highlight = _pick_highlight(caption_text, (recent_highlights or []) + ([label] if label else []))
    if recent_highlights is not None and highlight:
        recent_highlights.append(highlight)
    node = SceneNode(
        id=node_id, type=node_type, semantic_role=semantic_role,
        asset_source=asset_type, asset_reference=prompt, appear_at=round(appear_at, 4),
        label=label,
        metadata={"scene_number": scene_number},
    )
    if caption_text:
        node.caption = CaptionSpec(text=caption_text, highlight=highlight)
    return node


# --- Compound multi-idea row splitting ---------------------------------
# "Hoover Dam required engineers to divert the river, excavate the
# foundation, and manage concrete" describes THREE distinct visual ideas in
# one narration row — the pre-hardening planner produced one static node for
# the whole sentence (part of the "feels like a slideshow" problem). This
# conservatively detects a genuine coordinated list (requires the word
# "and" AND 3-4 sufficiently long resulting clauses, never a simple
# appositive comma like "In 1931, construction began") and, only then,
# turns ONE row into several sub-nodes chained by the SAME invisible
# "group" edge kind collections already use — the existing layout is what
# decides whether they show one-at-a-time or together, exactly like any
# other group; this function only expresses that they belong to one idea.
_COMPOUND_SPLIT_RE = re.compile(r",\s*(?:and\s+)?|\s+and\s+", re.IGNORECASE)
_MIN_COMPOUND_CLAUSE_WORDS = 3
_MIN_COMPOUND_PARTS = 3
_MAX_COMPOUND_PARTS = 4
_MIN_COMPOUND_ROW_WORDS = 14


def _split_compound_visual_ideas(script_segment: str) -> Optional[List[str]]:
    text = str(script_segment or "").strip()
    if " and " not in f" {text.lower()} ":
        return None
    core = text.rstrip(".!?")
    parts = [p.strip() for p in _COMPOUND_SPLIT_RE.split(core) if p.strip()]
    parts = [p for p in parts if len(p.split()) >= _MIN_COMPOUND_CLAUSE_WORDS]
    if not (_MIN_COMPOUND_PARTS <= len(parts) <= _MAX_COMPOUND_PARTS):
        return None
    return parts


def _chapter_label_for_segment(text: str, *, max_chars: int = 48) -> str:
    """Short label for a persistent chapter TitleCue — reuses the same
    abbreviation-safe first-sentence helper as the fallback prompt (PART 1),
    just truncated tighter to read as a title band, not a caption."""

    return _planner_first_sentence(text, max_chars=max_chars)


def generate_scene_graph_local_planner(
    segment_id: str,
    rows: Sequence[SceneRow],
    *,
    title: str = "",
    style_preset: str = "overscaled",
) -> SceneGraphGenerationResult:
    """The Local Visual Planner MVP: script/narration rows -> SceneGraph,
    with no CSV beat/node_id/relationship/chapter columns and no Gemini call.

    Each row needs only ``scene_number``/``script_segment``; ``asset_type``/
    ``prompt`` stay optional (``SceneRow`` defaults both to ``""``). Node ids
    are assigned from row POSITION ("n1", "n2", ...), never from an external
    CSV node id.

    Semantic structure is inferred at three levels, all gated on explicit
    linguistic evidence — a missing signal is always safer than a wrong one:
      - pairwise causal/mechanism/comparison relationships between adjacent
        rows (``_detect_relationship``) -> a visible "sequential" arrow, the
        same edge shape ``generate_scene_graph_heuristic`` already produces;
      - related-collection / genuine-ordered-sequence groups spanning 3+ rows
        (``_detect_semantic_groups``) -> invisible "group"/"group_grid"
        edges, the SAME pre-existing edge-kind convention Exp Solar's own
        four_row/index_grid beats already use, so no schema/layout change is
        needed for the existing chaptering/grid logic to pick them up;
      - a single row that narrates several distinct visual ideas in one
        coordinated list (``_split_compound_visual_ideas``) -> several
        sub-nodes chained by the same "group" edge kind, instead of one
        static node covering the whole idea.
      - a short, low-opportunity, pronoun-led row is treated as a
        CONTINUATION of the previous visual rather than a new one
        (``_looks_like_continuation``) — no new node is created for it, so
        the previous node (which already "persists until segment/camera
        moves on" per its own schema default) simply stays on screen.

    A persistent chapter ``TitleCue`` is emitted at the segment's own
    opening (using the supplied ``title``, or the first row's own text when
    none is given) and at every collection/sequence group's intro row — the
    SAME ``scene_graph.title_cues``/title-band mechanism the CSV-authored
    ``chapter``/``chapter_title`` columns already drive; this is the only
    thing that was missing before (the planner produced zero TitleCues, so
    the existing, unmodified title renderer had nothing to show).

    Node asset_type is left exactly as the CSV/row supplied UNLESS it is
    blank, in which case a small, high-confidence motion/action verb list
    nudges it to "video" (-> flow_video/stock_video) instead of always
    defaulting to an image — never overrides an explicit CSV asset_type.

    This function performs NO pixel-layout, camera, or motion computation;
    those stay exactly where they already live, in
    ``scene_graph/layout.py``/``composition.py``/``render.py``, unchanged and
    untouched by this module.
    """

    total = len(rows)
    nodes: List[SceneNode] = []
    edges: List[SceneEdge] = []
    beats: List[SceneGraphBeat] = []
    title_cues: List[TitleCue] = []

    semantic_groups = _detect_semantic_groups(rows)
    group_last_node: Dict[int, str] = {}
    recent_subjects: List[str] = []
    recent_asset_types: List[str] = []
    recent_highlights: List[str] = []
    seen_names: set = set()
    rows_since_title = 0
    # The video's subject: the name mentioned most across the whole script
    # (at least twice) — the natural opening chapter title.
    name_counts: Dict[str, int] = {}
    for row in rows:
        for name in _proper_noun_phrases(row.script_segment or ""):
            name_counts[name] = name_counts.get(name, 0) + 1
    # Prefer a name the OPENING line introduces (the video presents its
    # subject first); otherwise the script's most-mentioned name.
    opening_names = _proper_noun_phrases(rows[0].script_segment or "") if rows else []
    pool = [n for n in opening_names if name_counts.get(n, 0) >= 2] or list(name_counts)
    main_subject = max(pool, key=lambda n: (name_counts[n], len(n.split()))) if pool else ""
    if name_counts.get(main_subject, 0) < 2:
        main_subject = ""
    after_group = False  # the previous row ended a list chapter

    cursor = 0.0
    prev_node_id: Optional[str] = None

    for index, row in enumerate(rows):
        script_segment = (row.script_segment or "").strip()
        word_count = len(script_segment.split())
        duration = max(MIN_ROW_DURATION_S, word_count / WORDS_PER_SECOND)
        start = cursor
        end = cursor + duration
        cursor = end

        node_id = f"n{index + 1}"
        csv_asset_type = str(row.asset_type or "")
        supplied_prompt = str(row.prompt or row.stock or "").strip()
        visual_hint = str(getattr(row, "visual_description", "") or "").strip()
        scene_number = str(row.scene_number or index + 1)

        group_info = semantic_groups.get(index)
        # A row already claimed by a collection/sequence group expresses its
        # relationship to the group, not to whatever immediately precedes it
        # in narration order — never both, to avoid double/competing edges.
        relationship = None if group_info is not None else _detect_relationship(script_segment)
        relationship_kind = relationship[0] if relationship else None

        # A row carrying its own explicit asset_type/prompt (author-supplied,
        # or written by the Visual Plan's Change Source) has asked for its
        # OWN visual — folding it into the previous node would silently
        # discard that choice at Generate while the Visual Plan shows it.
        # (A bare generic "image"/"video" with no prompt is only a hint.)
        has_explicit_asset = bool(
            supplied_prompt or csv_asset_type.strip().lower() not in ("", "image", "video")
        )
        is_continuation = (
            group_info is None
            and relationship is None
            and not has_explicit_asset
            and prev_node_id is not None
            and _looks_like_continuation(script_segment, word_count=word_count)
        )

        # A compound row (several coordinated visual ideas in one sentence)
        # is only ever considered for a PLAIN row — one that isn't already
        # part of a group/relationship or a continuation, and that has no
        # single author-supplied prompt/visual_hint overriding the whole
        # row (a visual_hint expresses ONE specific intended shot for this
        # row, so splitting it into several would contradict the author).
        compound_parts: Optional[List[str]] = None
        if (
            group_info is None
            and relationship is None
            and not is_continuation
            and not supplied_prompt
            and not visual_hint
            and word_count >= _MIN_COMPOUND_ROW_WORDS
        ):
            compound_parts = _split_compound_visual_ideas(script_segment)

        actions: List[SceneGraphAction] = []
        created_node_ids: List[str] = []

        if is_continuation or not (script_segment or supplied_prompt):
            pass  # no node for this row — see module note above
        elif compound_parts:
            sub_duration = duration / len(compound_parts)
            prev_sub_id: Optional[str] = None
            for k, clause in enumerate(compound_parts):
                sub_id = f"{node_id}_{k + 1}"
                sub_start = start + k * sub_duration
                node = _build_scene_node(
                    node_id=sub_id, index=index, total=total, text=clause,
                    appear_at=sub_start, csv_asset_type=csv_asset_type,
                    csv_prompt="", csv_stock="", scene_number=scene_number,
                    relationship_kind=None, recent_subjects=recent_subjects,
                    recent_asset_types=recent_asset_types, recent_highlights=recent_highlights,
                    seen_names=seen_names, allow_label=(k == 0),
                    caption_max_words=_GROUP_CAPTION_MAX_WORDS,
                )
                nodes.append(node)
                created_node_ids.append(sub_id)
                actions.append(
                    SceneGraphAction(type="reveal_node", action_id=f"a_reveal_{sub_id}", node_id=sub_id)
                )
                if prev_sub_id is not None:
                    edge_id = f"e_{prev_sub_id}_{sub_id}"
                    edges.append(
                        SceneEdge(
                            id=edge_id, from_node=prev_sub_id, to_node=sub_id,
                            kind="group", draw_at=round(sub_start, 4),
                            metadata={"relationship": "compound_idea_split"},
                        )
                    )
                    actions.append(
                        SceneGraphAction(type="draw_edge", action_id=f"a_draw_{edge_id}", edge_id=edge_id)
                    )
                prev_sub_id = sub_id
            prev_node_id = prev_sub_id
        else:
            node = _build_scene_node(
                node_id=node_id, index=index, total=total, text=script_segment,
                appear_at=start, csv_asset_type=csv_asset_type,
                csv_prompt=row.prompt, csv_stock=row.stock, scene_number=scene_number,
                relationship_kind=relationship_kind, visual_hint=visual_hint,
                recent_subjects=recent_subjects, recent_asset_types=recent_asset_types,
                recent_highlights=recent_highlights, seen_names=seen_names,
                reaction=group_info is None and _is_reaction_line(script_segment, word_count),
                # 3-4 cards side by side are narrow: a full 14-word caption no
                # longer fits their 3 lines and got cut off mid-sentence.
                caption_max_words=(
                    _GROUP_CAPTION_MAX_WORDS if group_info is not None and group_info["role"] == "member"
                    else _CAPTION_MAX_WORDS
                ),
            )
            nodes.append(node)
            created_node_ids.append(node_id)
            actions.append(
                SceneGraphAction(type="reveal_node", action_id=f"a_reveal_{node_id}", node_id=node_id)
            )

            # Never link across the end of a list chapter: layout keeps linked
            # cards on screen together, so an arrow from the list's last card
            # dragged the finished list into the next section's chapter.
            if relationship is not None and prev_node_id is not None and not after_group:
                kind_label, cue = relationship
                edge_id = f"e_{prev_node_id}_{node_id}"
                edges.append(
                    SceneEdge(
                        id=edge_id,
                        from_node=prev_node_id,
                        to_node=node_id,
                        style="hand_drawn",
                        kind="sequential",
                        draw_at=round(start, 4),
                        metadata={"relationship": kind_label, "cue": cue,
                                  "label": _EDGE_LABELS.get(kind_label, "")},
                    )
                )
                actions.append(
                    SceneGraphAction(type="draw_edge", action_id=f"a_draw_{edge_id}", edge_id=edge_id)
                )
            elif group_info is not None:
                group_id = group_info["group_id"]
                if group_info["role"] == "member":
                    prev_group_node = group_last_node.get(group_id)
                    if prev_group_node is not None:
                        edge_id = f"e_{prev_group_node}_{node_id}"
                        edges.append(
                            SceneEdge(
                                id=edge_id,
                                from_node=prev_group_node,
                                to_node=node_id,
                                kind=group_info["kind"],
                                draw_at=round(start, 4),
                                metadata={
                                    "relationship": group_info["relationship"],
                                    "count": group_info["count"],
                                },
                            )
                        )
                        actions.append(
                            SceneGraphAction(
                                type="draw_edge", action_id=f"a_draw_{edge_id}", edge_id=edge_id
                            )
                        )
                # A COLLECTION intro ("...happened in four stages:") is the
                # chapter's title (its TitleCue above) and its own card — not
                # a member of the group it announces. Chaining it in made an
                # announced four-item group five cards, which overflowed
                # Exp Solar's four-per-chapter layout ("overlapping nodes")
                # on every such script. A SEQUENCE's first row ("First, ...")
                # is a real step, so it stays in its group.
                if group_info["role"] == "member" or group_info["relationship"] == "sequential_list":
                    group_last_node[group_id] = node_id

            prev_node_id = node_id

        rows_since_title += 1
        if created_node_ids:
            is_group_intro = group_info is not None and group_info["role"] == "intro"
            chapter_text = None
            if index == 0 and not is_group_intro:
                chapter_text = title.strip() or main_subject or _chapter_title(script_segment)
            elif is_group_intro:
                chapter_text = _collection_title(script_segment)
            elif group_info is None and after_group:
                # A list chapter just ended: its title ("...: Four Stages")
                # must not stay on screen over the next, unrelated section.
                # Title this section from its own first lines.
                for j in range(index, min(index + 3, total)):
                    candidate = _chapter_title(rows[j].script_segment or "")
                    if _decent_title(candidate):
                        chapter_text = candidate
                        break
            elif group_info is None and rows_since_title > _MIN_ROWS_PER_CHAPTER and (
                _is_chapter_opener(script_segment) or rows_since_title > _MAX_ROWS_PER_CHAPTER
            ) and not any(
                # A list intro right after this row titles the chapter itself —
                # two title bands a few seconds apart would just flash.
                semantic_groups.get(j, {}).get("role") == "intro" for j in (index + 1, index + 2)
            ):
                # A section boundary in the narration ("Before construction
                # began, ...", "The first major challenge ...", a question),
                # or a long stretch with no title — a chapter title band
                # (and Exp Solar's chapter-entry SFX) marks the new section.
                candidate = _chapter_title(script_segment)
                if len(candidate.split()) >= 2:
                    chapter_text = candidate
            after_group = bool(group_info) and group_info["role"] == "member" and not (
                semantic_groups.get(index + 1, {}).get("group_id") == group_info["group_id"]
            )
            # Never re-show the title band already on screen.
            if chapter_text and not (title_cues and title_cues[-1].text == chapter_text):
                title_cues.append(TitleCue(text=chapter_text, at=0.0 if index == 0 else round(start, 4)))
                rows_since_title = 0

        beats.append(
            SceneGraphBeat(
                beat_id=f"beat_{index + 1}",
                narration=script_segment,
                start=round(start, 4),
                end=round(end, 4),
                actions=actions,
            )
        )

    # Exp Solar's chapter progress strip (the numbered tabs across the top,
    # current chapter highlighted): one checklist_item per chapter title, made
    # current when its chapter starts. The renderer/layout/audio already
    # support it (a hand-written Exp Solar CSV can author beat=checklist);
    # the planner simply never produced it, so planner videos had no strip.
    if style_preset == "exp_solar" and len(title_cues) >= _CHAPTER_TAB_MIN:
        for i, cue in enumerate(title_cues[:_CHAPTER_TAB_MAX]):
            nodes.append(SceneNode(
                id=f"chapter_tab_{i + 1}", type="checklist_item",
                label=_chapter_tab_label(cue.text), appear_at=cue.at,
                metadata={"chapter_title": cue.text},
            ))

    scene_graph = SceneGraph(
        segment_id=segment_id,
        title=title,
        style_preset=style_preset,
        duration=round(cursor, 4),
        nodes=nodes,
        edges=edges,
        beats=beats,
        title_cues=title_cues,
    )
    errors = scene_graph.validate()
    return SceneGraphGenerationResult(
        ok=not errors, scene_graph=scene_graph, errors=errors, source="local_planner"
    )


# --- LLM-backed path ---------------------------------------------------------

_SYSTEM_PROMPT = """You generate Overscaled-style composition intent as strict JSON.

Overscaled is a whiteboard-collage documentary style: one large persistent
canvas per segment holds image/diagram/video_loop/anchor nodes that appear
over time, connected by causal arrows, with short captions and a camera that
pans/zooms across the canvas.

Output ONE JSON object matching this shape exactly (no prose, no markdown
fences, no extra commentary):

{
  "segment_id": string,
  "title": string,
  "style_preset": string,
  "duration": number,
  "nodes": [{"id": string, "type": "image"|"diagram"|"video_loop"|"anchor",
             "semantic_role": string, "asset_source": string,
             "asset_reference": string, "appear_at": number,
             "caption": {"text": string, "highlight": string|null} | null}],
  "edges": [{"id": string, "from": string, "to": string, "style": string,
             "color": string, "draw_at": number, "duration": number}],
  "camera_keyframes": [{"keyframe_id": string, "at": number,
                          "frame_nodes": [string], "zoom": number}],
  "beats": [{"beat_id": string, "narration": string, "start": number,
              "end": number,
              "actions": [{"type": "reveal_node"|"draw_edge"|"move_camera"|"set_caption",
                            "action_id": string, "node_id": string|null,
                            "edge_id": string|null,
                            "camera_keyframe_id": string|null,
                            "caption": object|null}]}]
}

Hard rules:
- Every node's "asset_source" MUST be copied verbatim from the scene's
  existing asset_type (do not invent a new asset provider vocabulary).
- "semantic_role" is a separate, free-text concept from "asset_source" —
  never put the asset type into semantic_role or vice versa.
- A "highlight" must be a verbatim substring of that caption's "text".
- Do NOT output pixel coordinates, canvas x/y, width/height, FFmpeg filters,
  Pillow/drawing instructions, or timeline events of any kind. Positions and
  final layout are decided by a later stage, not by you.
- Not every scene needs a node; not every sentence needs exactly one node.
- Output valid JSON only.
"""


def _build_user_prompt(
    segment_id: str, rows: Sequence[SceneRow], *, title: str, style_preset: str
) -> str:
    scene_lines = []
    for row in rows:
        scene_lines.append(
            json.dumps(
                {
                    "scene_number": row.scene_number,
                    "script_segment": row.script_segment,
                    "asset_type": row.asset_type,
                    "prompt": row.prompt or row.stock,
                }
            )
        )
    return (
        f"segment_id: {segment_id}\n"
        f"title: {title}\n"
        f"style_preset: {style_preset}\n"
        "Existing CSV scenes (scene_number, script_segment, asset_type, prompt):\n"
        + "\n".join(scene_lines)
    )


def _extract_json_object(text: str) -> str:
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"```\s*$", "", stripped).strip()
    return stripped


def generate_scene_graph_with_llm(
    segment_id: str,
    rows: Sequence[SceneRow],
    *,
    llm: LLMProvider,
    title: str = "",
    style_preset: str = "overscaled",
) -> SceneGraphGenerationResult:
    """Isolated Overscaled adapter over the existing LLMProvider seam.

    Never imports visual_director.director, never touches its prompt or the
    VisualScene contract. Any failure (network, bad JSON, invalid SceneGraph)
    is returned as ``ok=False`` — it is never raised past this function and
    never produces a half-valid SceneGraph.
    """

    user_prompt = _build_user_prompt(segment_id, rows, title=title, style_preset=style_preset)
    try:
        raw = llm.complete(_SYSTEM_PROMPT, user_prompt)
    except LLMError as exc:
        return SceneGraphGenerationResult(ok=False, scene_graph=None, errors=[f"LLM error: {exc}"], source="llm")
    except Exception as exc:  # never let an LLM/transport failure escape this module
        return SceneGraphGenerationResult(
            ok=False, scene_graph=None, errors=[f"LLM call failed unexpectedly: {exc}"], source="llm"
        )

    try:
        parsed = json.loads(_extract_json_object(raw))
    except (json.JSONDecodeError, TypeError) as exc:
        return SceneGraphGenerationResult(
            ok=False, scene_graph=None, errors=[f"LLM did not return valid JSON: {exc}"], source="llm"
        )
    if not isinstance(parsed, dict):
        return SceneGraphGenerationResult(
            ok=False, scene_graph=None, errors=["LLM JSON must be an object, not a list/scalar"], source="llm"
        )

    scene_graph = SceneGraph.from_dict(parsed)
    errors = scene_graph.validate()
    if errors:
        return SceneGraphGenerationResult(ok=False, scene_graph=None, errors=errors, source="llm")
    return SceneGraphGenerationResult(ok=True, scene_graph=scene_graph, errors=[], source="llm")


def generate_scene_graph(
    segment_id: str,
    rows: Sequence[SceneRow],
    *,
    title: str = "",
    style_preset: str = "overscaled",
    llm: Optional[LLMProvider] = None,
) -> SceneGraphGenerationResult:
    """Try the injected LLM (if any); always fall back to the safe heuristic.

    With no ``llm`` supplied this is 100% deterministic and offline — the
    default for tests and for any caller that hasn't wired up Gemini yet.
    """

    if llm is not None:
        llm_result = generate_scene_graph_with_llm(
            segment_id, rows, llm=llm, title=title, style_preset=style_preset
        )
        if llm_result.ok:
            return llm_result
        fallback = generate_scene_graph_heuristic(
            segment_id, rows, title=title, style_preset=style_preset
        )
        fallback.errors = list(llm_result.errors) + list(fallback.errors)
        fallback.source = "heuristic_fallback_after_llm_failure"
        return fallback
    return generate_scene_graph_heuristic(segment_id, rows, title=title, style_preset=style_preset)
