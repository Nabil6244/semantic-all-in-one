"""Per-scene recovery: retry vs alternative vs skip, without a second AssetManager.

Tracks failed queries/providers for the current project so Alternative never
repeats the exact approach that just failed.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set

from providers.base import AssetResult, AssetSource, SceneRow, SceneStatus

# 1x1 black PNG — skip placeholder so the renderer still has a file.
PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300000002000100cf00015d0a2db40000000049454e44ae426082"
)

CHANGE_SOURCE_ORDER = (
    "stock_video",
    "youtube",
    "archive",
    "nasa",
    "flow_video",
    "flow_image",
    "stock_image",
    "research",
    "local",
)


def scene_key(scene_number) -> str:
    try:
        return f"{int(str(scene_number).strip()):03d}"
    except ValueError:
        return str(scene_number).strip()


def allow_final_render(
    scene_numbers: Iterable[str],
    results: Dict[str, AssetResult],
    skipped: Optional[Set[str]] = None,
) -> bool:
    """Final render is allowed only when every required scene is READY or skipped."""
    skipped = skipped or set()
    for raw in scene_numbers:
        key = scene_key(raw)
        if key in skipped:
            continue
        result = results.get(key)
        if result is None or not result.ok:
            return False
    return True


def summarize_assets(
    scene_numbers: Iterable[str],
    results: Dict[str, AssetResult],
    skipped: Optional[Set[str]] = None,
) -> dict:
    skipped = skipped or set()
    keys = [scene_key(n) for n in scene_numbers]
    ready = 0
    attention: List[str] = []
    for key in keys:
        if key in skipped:
            ready += 1
            continue
        result = results.get(key)
        if result is not None and result.ok:
            ready += 1
        else:
            attention.append(key)
    return {
        "total": len(keys),
        "ready": ready,
        "needs_attention": len(attention),
        "attention_scenes": attention,
        "allow_render": allow_final_render(keys, results, skipped),
    }


class SceneRecoveryTracker:
    """Remember failed approaches per scene for one desktop session."""

    def __init__(self) -> None:
        self.failed_queries: Dict[str, Set[str]] = defaultdict(set)
        self.failed_providers: Dict[str, Set[str]] = defaultdict(set)
        self.failed_asset_ids: Dict[str, Set[str]] = defaultdict(set)
        self.skipped: Set[str] = set()
        self.status: Dict[str, str] = {}

    def mark_query(self, scene_number, query: str) -> None:
        q = " ".join((query or "").split()).lower()
        if q:
            self.failed_queries[scene_key(scene_number)].add(q)

    def mark_provider(self, scene_number, provider: str) -> None:
        name = (provider or "").strip().lower().replace(" ", "_").replace("-", "_")
        if name:
            self.failed_providers[scene_key(scene_number)].add(name)

    def mark_asset_id(self, scene_number, asset_id: str) -> None:
        if asset_id:
            self.failed_asset_ids[scene_key(scene_number)].add(str(asset_id))

    def remaining_youtube_queries(self, scene: SceneRow) -> List[str]:
        from providers.youtube.base import unique_youtube_queries

        used = self.failed_queries[scene_key(scene.scene_number)]
        out = []
        for query in unique_youtube_queries(scene):
            if query.lower() not in used:
                out.append(query)
        return out

    def remaining_providers(self, scene: SceneRow) -> List[str]:
        used = self.failed_providers[scene_key(scene.scene_number)]
        current = (scene.asset_type or "").strip().lower()
        names: List[str] = []
        for name in list(scene.fallbacks or []):
            key = str(name).strip().lower().replace(" ", "_")
            if key and key not in used and key not in names:
                names.append(key)
        if current in ("youtube_video", "youtube") and "youtube" not in names:
            pass
        return names

    def change_source_options(self, scene: SceneRow) -> List[str]:
        """Always offer every provider so Source works anytime (not only declared fallbacks)."""
        used = self.failed_providers[scene_key(scene.scene_number)]
        return [name for name in CHANGE_SOURCE_ORDER if name not in used]

    def next_alternative(self, scene: SceneRow) -> dict:
        """One step: unused YouTube query, else unused declared fallback provider."""
        key = scene_key(scene.scene_number)
        queries = self.remaining_youtube_queries(scene) if scene.wants_youtube else []
        if queries:
            return {"kind": "youtube_query", "query": queries[0], "queries": queries, "scene": key}
        providers = self.remaining_providers(scene)
        if providers:
            return {"kind": "provider", "provider": providers[0], "scene": key}
        if scene.wants_stock or scene.wants_flow:
            return {"kind": "regenerate_exclude", "scene": key}
        return {"kind": "exhausted", "scene": key}


def mark_needs_action(result: AssetResult) -> AssetResult:
    if result.ok or result.status in (SceneStatus.CANCELLED, SceneStatus.SKIPPED):
        return result
    result.status = SceneStatus.NEEDS_ACTION
    return result
