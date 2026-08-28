"""Structured visual plan: AI output adapted onto existing SceneRow fields."""

from __future__ import annotations

import csv
import dataclasses
import json
import re
from pathlib import Path
from typing import Any, List, Optional, Sequence

from providers.base import SceneRow
from providers.router import SceneAssetRouter

MIN_DURATION = 1.5
MAX_DURATION = 6.0
MIN_SCENES = 2

# Hard per-provider caps. Images, YouTube, and archival clips are short beats.
PROVIDER_MAX_DURATION = {
    "youtube": 3.0,
    "youtube_video": 3.0,
    "archive": 3.0,
    "archive_video": 3.0,
    "internet_archive": 3.0,
    "nasa": 3.0,
    "nasa_video": 3.0,
    "commons": 3.0,
    "commons_video": 3.0,
    "wikimedia": 3.0,
    "commons_image": 3.0,
    "wikimedia_image": 3.0,
    "flow_video": 6.0,
    "video": 6.0,
    "stock_video": 6.0,
    "stock": 6.0,
    "pexels": 6.0,
    "pixabay": 6.0,
    "openverse": 3.0,
    "flow_image": 3.0,
    "image": 3.0,
    "flow": 3.0,
    "stock_image": 3.0,
    "local": 6.0,
}

PROVIDER_DEFAULT_DURATION = {
    "youtube": 2.5,
    "youtube_video": 2.5,
    "archive": 2.5,
    "archive_video": 2.5,
    "internet_archive": 2.5,
    "nasa": 2.5,
    "nasa_video": 2.5,
    "commons": 2.5,
    "commons_video": 2.5,
    "wikimedia": 2.5,
    "commons_image": 2.5,
    "wikimedia_image": 2.5,
    "flow_image": 2.5,
    "image": 2.5,
    "flow": 2.5,
    "stock_image": 2.5,
    "flow_video": 4.0,
    "video": 4.0,
    "stock_video": 3.5,
    "stock": 3.5,
    "local": 3.0,
}

# Deprecated Wikimedia Commons aliases → stock (Commons API removed).
_COMMONS_PROVIDER_ALIASES = {
    "commons": "stock_video",
    "commons_video": "stock_video",
    "wikimedia": "stock_video",
    "commons_image": "stock_image",
    "wikimedia_image": "stock_image",
}

# Names the model may emit → existing CSV asset_type values.
PROVIDER_TO_ASSET_TYPE = {
    "youtube": "youtube_video",
    "youtube_video": "youtube_video",
    "archive": "archive_video",
    "archive_video": "archive_video",
    "internet_archive": "archive_video",
    "nasa": "nasa_video",
    "nasa_video": "nasa_video",
    "stock": "stock_video",
    "stock_video": "stock_video",
    "pexels": "stock_video",
    "stock_image": "stock_image",
    "openverse": "stock_image",
    "pixabay": "stock_video",
    "flow_image": "image",
    "image": "image",
    "flow": "image",
    "flow_video": "video",
    "video": "video",
    "local": "local",
}
# Legacy CSV / old plans may still mention commons — accept and remap to stock.
for _alias, _target in _COMMONS_PROVIDER_ALIASES.items():
    PROVIDER_TO_ASSET_TYPE[_alias] = _target

ASSET_TYPE_TO_PROVIDER = {
    "youtube_video": "youtube",
    "archive_video": "archive",
    "nasa_video": "nasa",
    "stock_video": "stock_video",
    "stock_image": "stock_image",
    "stock": "stock",
    "image": "flow_image",
    "video": "flow_video",
    "local": "local",
    # Legacy asset_type values from older plans → stock routing.
    "commons_video": "stock_video",
    "commons_image": "stock_image",
}

SEARCH_ASSET_TYPES = {
    "youtube_video", "archive_video", "nasa_video",
    "stock_video", "stock_image", "stock",
}
DOCUMENTARY_VIDEO_TYPES = {"youtube_video", "archive_video", "nasa_video"}
FLOW_ASSET_TYPES = {"image", "video"}
ALLOWED_ASSET_TYPES = set(PROVIDER_TO_ASSET_TYPE.values()) | {"stock"}
ALLOWED_IMPORTANCE = {"high", "medium", "low"}
ALLOWED_TRANSITIONS = {"cut", "dissolve", "fade", "match_cut"}
ALLOWED_QUALITY = {"720p", "1080p", "1440p", "2160p"}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class VisualPlanError(ValueError):
    """Raised when the model output cannot become an executable scene plan."""


def _trim_narration_query(narration: str, max_words: int = 12) -> str:
    words = (narration or "").split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words])


def normalize_provider(name: str) -> str:
    key = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    key = _COMMONS_PROVIDER_ALIASES.get(key, key)
    if key not in PROVIDER_TO_ASSET_TYPE:
        raise VisualPlanError(f"invalid asset type/provider: {name!r}")
    return key


def provider_to_asset_type(name: str) -> str:
    return PROVIDER_TO_ASSET_TYPE[normalize_provider(name)]


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


@dataclasses.dataclass
class VisualScene:
    scene_id: int
    narration: str
    visual_goal: str
    visual_description: str
    asset_type: str
    provider_preference: str
    search_queries: List[str]
    timestamp_needed: bool
    timestamp_hint: str
    duration: float
    importance: str
    fallbacks: List[str]
    visual_treatment: str
    transition: str
    minimum_quality: str = "1080p"

    @property
    def primary_query(self) -> str:
        return self.search_queries[0] if self.search_queries else ""

    def to_scene_row(self, provider: Optional[str] = None) -> SceneRow:
        """Map this planned scene onto the existing CSV/AssetManager SceneRow."""
        pref = provider or self.provider_preference
        if provider is not None:
            asset_type = provider_to_asset_type(pref)
        elif self.asset_type:
            asset_type = self.asset_type
        else:
            asset_type = provider_to_asset_type(pref)
        narration = self.narration.strip()
        query = self.primary_query
        description = self.visual_description.strip()
        if not query and asset_type in SEARCH_ASSET_TYPES:
            query = description or self.visual_goal.strip() or _trim_narration_query(narration)
        if asset_type == "youtube_video":
            queries = list(self.search_queries)
            return SceneRow(
                scene_number=str(self.scene_id),
                script_segment=narration,
                asset_type=asset_type,
                prompt=query,
                search_queries=queries,
                fallbacks=list(self.fallbacks),
                visual_description=description,
            )
        if asset_type in DOCUMENTARY_VIDEO_TYPES:
            queries = list(self.search_queries)
            return SceneRow(
                scene_number=str(self.scene_id),
                script_segment=narration,
                asset_type=asset_type,
                prompt=query,
                search_queries=queries,
                fallbacks=list(self.fallbacks),
                visual_description=description,
            )
        if asset_type in ("stock_video", "stock_image", "stock"):
            return SceneRow(
                scene_number=str(self.scene_id),
                script_segment=narration,
                asset_type=asset_type,
                prompt=query,
                stock=query,
            )
        if asset_type in FLOW_ASSET_TYPES:
            return SceneRow(
                scene_number=str(self.scene_id),
                script_segment=narration,
                asset_type=asset_type,
                prompt=description or query,
            )
        hint = description or self.visual_goal.strip() or _trim_narration_query(narration)
        return SceneRow(
            scene_number=str(self.scene_id),
            script_segment=narration,
            asset_type="stock_video",
            prompt=hint,
            stock=hint,
        )

    def provider_chain(self) -> List[str]:
        chain = [self.provider_preference]
        for name in self.fallbacks:
            if name not in chain:
                chain.append(name)
        return chain

    def fallback_rows(self) -> List[SceneRow]:
        return [self.to_scene_row(provider) for provider in self.fallbacks]

    def scene_row_at(self, attempt: int = 0) -> SceneRow:
        chain = self.provider_chain()
        if attempt < 0 or attempt >= len(chain):
            raise VisualPlanError(f"no provider attempt {attempt} for scene {self.scene_id}")
        return self.to_scene_row(chain[attempt])


@dataclasses.dataclass
class VisualPlan:
    topic: str
    scenes: List[VisualScene]
    warnings: List[str] = dataclasses.field(default_factory=list)
    allocation: Optional[dict] = None

    def to_scene_rows(self) -> List[SceneRow]:
        return [scene.to_scene_row() for scene in self.scenes]

    def to_csv_dicts(self) -> List[dict]:
        rows = []
        for scene in self.scenes:
            row = scene.to_scene_row()
            asset_type = scene.asset_type or row.asset_type
            prompt = row.prompt or row.stock
            if scene.search_queries:
                if asset_type == "youtube_video" or asset_type in DOCUMENTARY_VIDEO_TYPES:
                    prompt = " || ".join(scene.search_queries)
                elif asset_type in ("stock_video", "stock_image", "stock") and not prompt:
                    prompt = scene.search_queries[0]
            if not prompt and asset_type in FLOW_ASSET_TYPES:
                prompt = (scene.visual_description or "").strip()
            if not prompt and asset_type in SEARCH_ASSET_TYPES.union(DOCUMENTARY_VIDEO_TYPES):
                prompt = (
                    scene.visual_description
                    or scene.visual_goal
                    or _trim_narration_query(scene.narration)
                ).strip()
            rows.append(
                {
                    "scene_number": row.scene_number,
                    "script_segment": row.script_segment,
                    "asset_type": asset_type,
                    "prompt": prompt,
                }
            )
        return rows

    def write_csv(self, path: Path) -> None:
        path = Path(path)
        rows = self.to_csv_dicts()
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f, fieldnames=["scene_number", "script_segment", "asset_type", "prompt"]
            )
            w.writeheader()
            w.writerows(rows)

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "warnings": list(self.warnings),
            "scenes": [dataclasses.asdict(s) for s in self.scenes],
            "allocation": self.allocation,
        }

    def set_allocation(self, bundle_dict: dict) -> None:
        self.allocation = bundle_dict

    def format_preview(self) -> str:
        blocks = [f"TOPIC: {self.topic}", ""]
        for scene in self.scenes:
            fb = " → ".join(scene.fallbacks) if scene.fallbacks else "(none)"
            queries = "; ".join(scene.search_queries) if scene.search_queries else "(none)"
            blocks.append(
                f"SCENE {scene.scene_id:02d}\n"
                f"Narration:\n{scene.narration}\n\n"
                f"Visual:\n{scene.visual_description}\n\n"
                f"Goal: {scene.visual_goal}\n"
                f"Type: {scene.provider_preference}\n"
                f"Search:\n{queries}\n\n"
                f"Duration:\n{scene.duration:.1f}s\n"
                f"Quality: {scene.minimum_quality}\n"
                f"Importance: {scene.importance}\n"
                f"Timestamp needed: {scene.timestamp_needed}"
                + (f" ({scene.timestamp_hint})" if scene.timestamp_hint else "")
                + f"\nTreatment: {scene.visual_treatment}\n"
                f"Transition: {scene.transition}\n"
                f"Fallback:\n{fb}"
            )
            blocks.append("")
        if self.warnings:
            blocks.append("WARNINGS:")
            blocks.extend(f"- {w}" for w in self.warnings)
        return "\n".join(blocks).rstrip() + "\n"


def extract_json_payload(text: str) -> Any:
    if text is None:
        raise VisualPlanError("empty AI response")
    raw = text.strip()
    if not raw:
        raise VisualPlanError("empty AI response")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError as exc:
                raise VisualPlanError(f"malformed AI response: {exc}") from exc
        raise VisualPlanError("malformed AI response: not JSON")


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()] if str(value).strip() else []


def unique_search_queries(queries: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for query in queries:
        cleaned = " ".join((query or "").split())
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def provider_max_duration(provider: str) -> float:
    key = (provider or "").strip().lower().replace(" ", "_").replace("-", "_")
    return float(PROVIDER_MAX_DURATION.get(key, MAX_DURATION))


def _as_duration(value: Any, provider: str = "", scene_id: Optional[int] = None) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        raise VisualPlanError(f"invalid duration: {value!r}")
    duration = round(duration, 2)
    cap = provider_max_duration(provider)
    label = f"scene {scene_id}: " if scene_id is not None else ""
    if duration < MIN_DURATION:
        raise VisualPlanError(
            f"{label}duration {duration}s is below the {MIN_DURATION}s minimum"
        )
    if duration > cap:
        duration = round(cap, 2)
    if duration > MAX_DURATION:
        duration = round(MAX_DURATION, 2)
    return duration


def _as_quality(value: Any) -> str:
    q = str(value or "1080p").strip().lower().replace(" ", "")
    if q in ("4k", "uhd"):
        q = "2160p"
    if q not in ALLOWED_QUALITY:
        raise VisualPlanError(f"invalid minimum_quality: {value!r}")
    return q


def _parse_scene(raw: dict, index: int) -> VisualScene:
    if not isinstance(raw, dict):
        raise VisualPlanError(f"scene {index} is not an object")
    missing = [
        key
        for key in (
            "narration",
            "visual_goal",
            "visual_description",
            "provider_preference",
        )
        if not str(raw.get(key) or "").strip()
    ]
    # asset_type may be omitted if provider_preference is present
    if missing:
        raise VisualPlanError(
            f"scene {raw.get('scene_id', index)} missing required field(s): {', '.join(missing)}"
        )

    scene_id_raw = raw.get("scene_id", index)
    try:
        scene_id = int(scene_id_raw)
    except (TypeError, ValueError):
        raise VisualPlanError(f"invalid scene_id: {scene_id_raw!r}")
    if scene_id < 1:
        raise VisualPlanError(f"scene_id must be >= 1, got {scene_id}")

    provider = normalize_provider(str(raw.get("provider_preference")))
    declared = raw.get("asset_type")
    # Legacy plans used provider_preference "flow" for both image and video scenes.
    if provider == "flow":
        if declared:
            dt = provider_to_asset_type(str(declared))
            provider = "flow_video" if dt == "video" else "flow_image"
        else:
            provider = "flow_image"
    if declared:
        declared_type = provider_to_asset_type(str(declared))
        preferred_type = provider_to_asset_type(provider)
        if declared_type != preferred_type:
            raise VisualPlanError(
                f"scene {scene_id}: asset_type {declared!r} does not match "
                f"provider_preference {provider!r}"
            )
        asset_type = declared_type
    else:
        asset_type = provider_to_asset_type(provider)

    importance = str(raw.get("importance") or "medium").strip().lower()
    if importance not in ALLOWED_IMPORTANCE:
        raise VisualPlanError(f"scene {scene_id}: invalid importance {importance!r}")

    transition = str(raw.get("transition") or "cut").strip().lower().replace(" ", "_")
    if transition not in ALLOWED_TRANSITIONS:
        raise VisualPlanError(f"scene {scene_id}: invalid transition {transition!r}")

    queries = unique_search_queries(_as_str_list(raw.get("search_queries")))
    if not queries:
        queries = unique_search_queries(_as_str_list(raw.get("search_query")))

    if asset_type == "local":
        hint = (
            str(raw.get("visual_description") or raw.get("visual_goal") or "").strip()
            or _trim_narration_query(str(raw.get("narration") or ""))
        )
        asset_type = "stock_video"
        provider = "stock_video"
        if not queries and hint:
            queries = unique_search_queries([hint])

    if asset_type in SEARCH_ASSET_TYPES and not queries:
        raise VisualPlanError(f"scene {scene_id}: search query required for {asset_type}")
    if asset_type in DOCUMENTARY_VIDEO_TYPES:
        if len(queries) < 2:
            raise VisualPlanError(
                f"scene {scene_id}: {asset_type} needs at least 2 search_queries "
                "(specific query plus a broader fallback query)"
            )
        if len(set(q.lower() for q in queries)) < 2:
            raise VisualPlanError(
                f"scene {scene_id}: {asset_type} search_queries must be distinct"
            )
    if asset_type in FLOW_ASSET_TYPES and not str(raw.get("visual_description") or "").strip():
        raise VisualPlanError(f"scene {scene_id}: visual_description required for {asset_type}")

    fallbacks: List[str] = []
    for item in _as_str_list(raw.get("fallbacks")):
        fb = normalize_provider(item)
        if fb == provider:
            continue
        if fb not in fallbacks:
            fallbacks.append(fb)
    if asset_type == "youtube_video" and not fallbacks:
        fallbacks = ["archive", "stock_video", "flow_image"]
    if asset_type == "archive_video" and not fallbacks:
        fallbacks = ["youtube", "stock_video", "flow_image"]
    if asset_type == "nasa_video" and not fallbacks:
        fallbacks = ["archive", "youtube", "flow_video"]

    default_duration = PROVIDER_DEFAULT_DURATION.get(provider, 3.0)
    duration = _as_duration(
        raw.get("duration", default_duration), provider=provider, scene_id=scene_id
    )
    timestamp_needed = _as_bool(raw.get("timestamp_needed"))
    timestamp_hint = str(
        raw.get("timestamp_hint") or raw.get("timestamp_moment") or ""
    ).strip()
    if timestamp_needed and asset_type != "youtube_video":
        timestamp_needed = False
        timestamp_hint = ""

    return VisualScene(
        scene_id=scene_id,
        narration=str(raw["narration"]).strip(),
        visual_goal=str(raw["visual_goal"]).strip(),
        visual_description=str(raw["visual_description"]).strip(),
        asset_type=asset_type,
        provider_preference=provider,
        search_queries=queries,
        timestamp_needed=timestamp_needed,
        timestamp_hint=timestamp_hint,
        duration=duration,
        importance=importance,
        fallbacks=fallbacks,
        visual_treatment=str(raw.get("visual_treatment") or "static").strip(),
        transition=transition,
        minimum_quality=_as_quality(raw.get("minimum_quality")),
    )


_GENERIC_QUERY = re.compile(
    r"^(tired person|people walking|busy city|man thinking|woman thinking|"
    r"person using phone|people at work|person sleeping)$",
    re.I,
)
_ABSTRACT_MARKERS = (
    "social jet lag",
    "biological clock",
    "circadian",
    "time zone",
    "time zones",
    "hormones",
    "not lazy",
    "never quite knows what time",
)
_YOUTUBE_JUSTIFIED = re.compile(
    r"hospital|nurse|launch|keynote|protest|interview|documentary|concert|"
    r"stadium|spacecraft|wildfire|president|macworld|spacex|falcon",
    re.I,
)
_ARCHIVE_JUSTIFIED = re.compile(
    r"19\d\d|20[01]\d|apollo|moon landing|newsreel|archive|historical|"
    r"world war|vietnam|president|inaugur|news broadcast|old film",
    re.I,
)
_NASA_JUSTIFIED = re.compile(
    r"nasa|apollo|saturn|shuttle|iss|space station|mars|rover|pluto|"
    r"jupiter|satellite|orbit|launch pad|mission control|hubble|james webb|"
    r"new horizons|artemis|spacewalk|astronaut",
    re.I,
)


def detect_planning_issues(scenes: Sequence[VisualScene]) -> List[str]:
    """Soft quality checks — never reject a parse, only warn."""
    warnings: List[str] = []
    youtube_scenes = [s for s in scenes if s.provider_preference in ("youtube", "youtube_video")]
    archive_scenes = [s for s in scenes if s.provider_preference in ("archive", "archive_video", "internet_archive")]
    nasa_scenes = [s for s in scenes if s.provider_preference in ("nasa", "nasa_video")]
    if len(youtube_scenes) > 1:
        warnings.append(
            f"{len(youtube_scenes)} YouTube scenes; lifestyle narration rarely needs more than one"
        )
    for scene in youtube_scenes:
        blob = " ".join([scene.primary_query, scene.visual_description, scene.timestamp_hint])
        if not _YOUTUBE_JUSTIFIED.search(blob) and not scene.timestamp_needed:
            warnings.append(
                f"scene {scene.scene_id}: YouTube used without a unique real-world event/person/place"
            )
        if _ARCHIVE_JUSTIFIED.search(f"{scene.narration} {scene.visual_description}"):
            warnings.append(
                f"scene {scene.scene_id}: historical beat may fit archive_video better than YouTube"
            )
        for query in scene.search_queries:
            words = query.split()
            if len(words) > 8:
                warnings.append(
                    f"scene {scene.scene_id}: YouTube query is over-specific ({len(words)} words): {query!r}"
                )
    for scene in archive_scenes:
        blob = " ".join([scene.primary_query, scene.visual_description, scene.narration])
        if not _ARCHIVE_JUSTIFIED.search(blob):
            warnings.append(
                f"scene {scene.scene_id}: archive_video used without clear historical/public-domain context"
            )
    for scene in nasa_scenes:
        blob = " ".join([scene.primary_query, scene.visual_description, scene.narration])
        if not _NASA_JUSTIFIED.search(blob):
            warnings.append(
                f"scene {scene.scene_id}: nasa_video used without clear space/science context"
            )
    for scene in scenes:
        if scene.primary_query and _GENERIC_QUERY.match(scene.primary_query.strip()):
            warnings.append(f"scene {scene.scene_id}: generic search query {scene.primary_query!r}")
        text = f"{scene.narration} {scene.visual_goal}".lower()
        if scene.provider_preference in (
            "youtube", "youtube_video", "stock_video", "archive", "archive_video",
            "nasa", "nasa_video",
        ):
            for marker in _ABSTRACT_MARKERS:
                if marker in text and scene.provider_preference != "stock_video":
                    warnings.append(
                        f"scene {scene.scene_id}: {marker!r} usually wants Flow, not {scene.provider_preference}"
                    )
                    break
                if marker in text and scene.provider_preference == "stock_video" and marker != "not lazy":
                    # weekday/weekend sleep can be stock; timezone/clock language should not
                    if marker in ("social jet lag", "biological clock", "circadian", "time zone", "time zones"):
                        warnings.append(
                            f"scene {scene.scene_id}: {marker!r} is a concept — prefer flow_image over stock_video"
                        )
                        break
    return warnings


def detect_repetition(scenes: Sequence[VisualScene]) -> List[str]:
    warnings: List[str] = []
    by_query: dict[str, List[int]] = {}
    for scene in scenes:
        key = scene.primary_query.lower()
        if not key:
            continue
        by_query.setdefault(key, []).append(scene.scene_id)
    for query, ids in by_query.items():
        if len(ids) > 1:
            warnings.append(
                f"duplicate search query {query!r} on scenes {ids}"
            )

    for i, a in enumerate(scenes):
        for b in scenes[i + 1 :]:
            if a.asset_type != b.asset_type:
                continue
            score = _jaccard(a.visual_description, b.visual_description)
            if score >= 0.72:
                warnings.append(
                    f"repetitive visuals on scenes {a.scene_id} and {b.scene_id} "
                    f"(overlap {score:.2f})"
                )
    return warnings


def parse_visual_plan(payload: Any) -> VisualPlan:
    if isinstance(payload, str):
        payload = extract_json_payload(payload)
    if not isinstance(payload, dict):
        raise VisualPlanError("AI response must be a JSON object")
    scenes_raw = payload.get("scenes")
    if not isinstance(scenes_raw, list) or not scenes_raw:
        raise VisualPlanError("AI response missing scenes[]")
    if len(scenes_raw) < MIN_SCENES:
        raise VisualPlanError(f"need at least {MIN_SCENES} scenes, got {len(scenes_raw)}")

    scenes = [_parse_scene(item, i + 1) for i, item in enumerate(scenes_raw)]
    scenes.sort(key=lambda s: s.scene_id)
    ids = [s.scene_id for s in scenes]
    if ids != list(range(1, len(scenes) + 1)):
        # Renumber only when ids are unique but not 1..n; reject duplicates.
        if len(set(ids)) != len(ids):
            raise VisualPlanError(f"duplicate scene_id values: {ids}")
        for i, scene in enumerate(scenes, start=1):
            scene.scene_id = i

    topic = str(payload.get("topic") or "").strip()
    if not topic:
        topic = scenes[0].visual_goal

    warnings = list(detect_repetition(scenes)) + list(detect_planning_issues(scenes))
    extra = payload.get("warnings")
    if isinstance(extra, list):
        warnings.extend(str(w) for w in extra if str(w).strip())
    allocation = payload.get("allocation") if isinstance(payload.get("allocation"), dict) else None
    return VisualPlan(topic=topic, scenes=scenes, warnings=warnings, allocation=allocation)


def assert_pipeline_compatible(plan: VisualPlan, images_dir: Optional[Path] = None) -> List[str]:
    """Confirm the plan produces SceneRows the existing router understands."""
    rows = plan.to_scene_rows()
    errors = []
    for row, scene in zip(rows, plan.scenes):
        if (scene.asset_type or "").strip().lower() == "local":
            errors.append(
                f"scene {scene.scene_id}: local is manual-only; use stock or Flow in analyzed plans"
            )
            continue
        source = SceneAssetRouter.classify(row)
        if source is None:
            errors.append(f"scene {scene.scene_id} does not route to a provider")
    if images_dir is not None:
        errors.extend(SceneAssetRouter.validate(rows, images_dir))
    return errors
