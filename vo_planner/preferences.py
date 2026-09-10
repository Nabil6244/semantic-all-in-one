"""Map asset-mix preferences onto existing AllocationSettings (soft guidance only).

Also soft-assign provider preferences onto Script Analyzer scenes for Option 3
so mix percentages (including Flow Image %) actually reach the Claude handoff
and VisualPlan CSV path — still quality-protected, never inventing content.
"""

from __future__ import annotations

import dataclasses
import re
from typing import List, Sequence, Tuple

from visual_allocation.models import AllocationSettings
from visual_director.schema import VisualPlan, VisualScene

from .schema import AssetMixPreferences

_PROTECTED_PROVIDERS = frozenset({
    "archive",
    "archive_video",
    "nasa",
    "nasa_video",
})

_FACTUAL_RE = re.compile(
    r"\b(document|documentary evidence|newspaper|archive|archival|map|timeline|"
    r"photograph|passport|certificate|ledger|manuscript)\b",
    re.I,
)

_CONCEPT_RE = re.compile(
    r"\b(concept|conceptual|metaphor|abstract|diagram|visualization|impossible|"
    r"illustration|schematic|comparison|explain|mechanism|idea)\b",
    re.I,
)

_ACTION_RE = re.compile(
    r"\b(rush|run|fly|launch|explode|crash|chase|crowd|traffic|ocean|waves|"
    r"storm|fire|smoke|walk|drive|ship|crane|factory|worker|city)\b",
    re.I,
)

_PROVIDER_ASSET = {
    "stock_video": ("stock_video", "stock_video"),
    "flow_video": ("flow_video", "video"),
    "youtube": ("youtube", "youtube_video"),
    "flow_image": ("flow_image", "image"),
    "stock_image": ("stock_image", "stock_image"),
}


def allocation_settings_from_mix(
    mix: AssetMixPreferences,
    base: AllocationSettings | None = None,
) -> AllocationSettings:
    """Derive soft allocation strategy from mix targets.

    Does not force providers. Quality protection remains with the allocator.
    """
    mix = mix.normalized()
    base = base or AllocationSettings()
    video = mix.video_pct
    image = mix.image_pct
    # Normalize video/image if both provided
    total = video + image
    if total > 0:
        video = 100.0 * video / total
        image = 100.0 * image / total

    if video >= 70:
        strategy = "video_heavy"
    elif image >= 65:
        strategy = "image_heavy"
    elif 40 <= video <= 60:
        strategy = "balanced"
    else:
        strategy = base.visual_strategy or "automatic"

    # Prefer image-heavy when Flow Image dominates an image-forward mix
    img_bucket = mix.flow_image_pct + mix.stock_image_pct
    if image >= 45 and img_bucket > 0 and mix.flow_image_pct / img_bucket >= 0.7:
        if strategy == "automatic":
            strategy = "image_heavy"
        elif strategy == "balanced" and image >= 50:
            strategy = "image_heavy"

    # Flow video budget from flow_video_pct preference.
    # 15–24% used to leave Brand & Style on "normal" (≈12% cap), so a UI
    # target of 20% never raised the paid Flow video budget.
    flow = mix.flow_video_pct
    if mix.max_flow_video and mix.max_flow_video > 0 and mix.max_flow_video <= 6:
        budget = "custom"
        custom = mix.max_flow_video
    elif flow >= 20:
        budget = "high"
        custom = base.ai_video_budget_custom
    elif flow <= 8:
        budget = "conservative"
        custom = base.ai_video_budget_custom
    else:
        budget = base.ai_video_budget or "normal"
        custom = base.ai_video_budget_custom

    coverage = base.coverage_mode or "automatic"
    if mix.quality_protection:
        # Prefer anti-repetition when mix is aggressive on one provider
        if mix.stock_video_pct >= 50 or mix.youtube_video_pct >= 25:
            coverage = "minimize_repetition"

    return AllocationSettings(
        visual_strategy=strategy,
        ai_video_budget=budget,
        ai_video_budget_custom=int(custom or 20),
        coverage_mode=coverage,
    )


def mix_handoff_note(mix: AssetMixPreferences) -> dict:
    """Explicit targets-only contract for Claude / allocation consumers."""
    data = mix.normalized().to_dict()
    data["targets_only"] = True
    data["quality_protection"] = True
    data["rule"] = "never_sacrifice_critical_visual_for_provider_pct"
    return data


def mix_flow_video_target(scene_count: int, mix: AssetMixPreferences) -> int:
    """Paid Flow-video scene count implied by mix % (quality-protection aside)."""
    mix = mix.normalized()
    n = max(0, int(scene_count))
    if n <= 0 or mix.flow_video_pct <= 0:
        return 0
    return int(_target_counts(n, mix).get("flow_video") or 0)


def allocation_settings_for_plan(
    mix: AssetMixPreferences,
    scene_count: int,
    base: AllocationSettings | None = None,
) -> AllocationSettings:
    """Soft Brand & Style settings + explicit Flow-video custom budget from mix %."""
    settings = allocation_settings_from_mix(mix, base)
    target = mix_flow_video_target(scene_count, mix)
    if mix.normalized().flow_video_pct <= 0:
        return settings
    custom = target
    # Small plans can round to 0 even when the user asked for Flow video.
    if custom <= 0 and scene_count >= 5 and mix.normalized().flow_video_pct >= 10:
        custom = 1
    return dataclasses.replace(
        settings,
        ai_video_budget="custom",
        ai_video_budget_custom=max(0, int(custom)),
    )


def _blob(scene: VisualScene) -> str:
    return " ".join(
        [
            scene.narration or "",
            scene.visual_goal or "",
            scene.visual_description or "",
            scene.visual_treatment or "",
        ]
    )


def _is_protected(scene: VisualScene) -> bool:
    pref = (scene.provider_preference or "").strip().lower()
    at = (scene.asset_type or "").strip().lower()
    if pref in _PROTECTED_PROVIDERS or at in ("archive_video", "nasa_video"):
        return True
    return False


def _is_factual(scene: VisualScene) -> bool:
    return bool(_FACTUAL_RE.search(_blob(scene)))


def _image_suitability(scene: VisualScene) -> float:
    """Higher = better Flow/stock image candidate."""
    text = _blob(scene)
    score = 0.35
    if _CONCEPT_RE.search(text):
        score += 0.35
    if _ACTION_RE.search(text):
        score -= 0.25
    if _is_factual(scene):
        score -= 0.45
    pref = (scene.provider_preference or "").lower()
    if pref in ("flow_image", "image", "stock_image"):
        score += 0.2
    if pref in ("stock_video", "flow_video", "youtube"):
        score -= 0.05
    imp = (scene.importance or "medium").lower()
    if imp == "low":
        score += 0.08
    if imp == "high" and _ACTION_RE.search(text):
        score -= 0.1
    return score


def _distribute(counts: Sequence[Tuple[str, int]]) -> List[str]:
    """Expand (provider, count) into a flat assignment list."""
    out: List[str] = []
    for provider, n in counts:
        out.extend([provider] * max(0, int(n)))
    return out


def _target_counts(n: int, mix: AssetMixPreferences) -> dict:
    """Compute provider target counts among n eligible scenes."""
    if n <= 0:
        return {
            "flow_image": 0,
            "stock_image": 0,
            "stock_video": 0,
            "flow_video": 0,
            "youtube": 0,
        }

    vi = mix.video_pct + mix.image_pct
    image_share = (mix.image_pct / vi) if vi > 0 else 0.4
    n_image = int(round(n * image_share))
    n_image = max(0, min(n, n_image))
    n_video = n - n_image

    img_parts = mix.flow_image_pct + mix.stock_image_pct
    if n_image <= 0:
        n_flow_img = n_stock_img = 0
    elif img_parts <= 0:
        n_flow_img, n_stock_img = n_image, 0
    else:
        n_flow_img = int(round(n_image * mix.flow_image_pct / img_parts))
        n_flow_img = max(0, min(n_image, n_flow_img))
        n_stock_img = n_image - n_flow_img

    vid_parts = mix.stock_video_pct + mix.flow_video_pct + mix.youtube_video_pct
    if n_video <= 0:
        n_stock_v = n_flow_v = n_yt = 0
    elif vid_parts <= 0:
        n_stock_v, n_flow_v, n_yt = n_video, 0, 0
    else:
        n_stock_v = int(round(n_video * mix.stock_video_pct / vid_parts))
        n_flow_v = int(round(n_video * mix.flow_video_pct / vid_parts))
        n_stock_v = max(0, min(n_video, n_stock_v))
        n_flow_v = max(0, min(n_video - n_stock_v, n_flow_v))
        n_yt = n_video - n_stock_v - n_flow_v

    # Rounding repair
    total = n_flow_img + n_stock_img + n_stock_v + n_flow_v + n_yt
    if total < n:
        n_stock_v += n - total
    elif total > n:
        overflow = total - n
        for key in ("n_yt", "n_stock_v", "n_flow_v", "n_stock_img", "n_flow_img"):
            if overflow <= 0:
                break
            if key == "n_yt" and n_yt > 0:
                cut = min(overflow, n_yt)
                n_yt -= cut
                overflow -= cut
            elif key == "n_stock_v" and n_stock_v > 0:
                cut = min(overflow, n_stock_v)
                n_stock_v -= cut
                overflow -= cut
            elif key == "n_flow_v" and n_flow_v > 0:
                cut = min(overflow, n_flow_v)
                n_flow_v -= cut
                overflow -= cut
            elif key == "n_stock_img" and n_stock_img > 0:
                cut = min(overflow, n_stock_img)
                n_stock_img -= cut
                overflow -= cut
            elif key == "n_flow_img" and n_flow_img > 0:
                cut = min(overflow, n_flow_img)
                n_flow_img -= cut
                overflow -= cut

    return {
        "flow_image": n_flow_img,
        "stock_image": n_stock_img,
        "stock_video": n_stock_v,
        "flow_video": n_flow_v,
        "youtube": n_yt,
    }


def apply_asset_mix_to_plan(plan: VisualPlan, mix: AssetMixPreferences) -> VisualPlan:
    """Soft-assign provider_preference from mix targets onto a VisualPlan.

    Quality protection:
    - archive / NASA scenes keep analyzer preference
    - factual document/map/evidence beats are not forced onto Flow Image
    - does not invent new scenes; only rewrites provider fields
    """
    mix = mix.normalized()
    scenes = list(plan.scenes or [])
    if not scenes:
        return plan

    protected: List[VisualScene] = []
    eligible: List[VisualScene] = []
    for s in scenes:
        if _is_protected(s):
            protected.append(s)
        else:
            eligible.append(s)

    targets = _target_counts(len(eligible), mix)
    # Sort most image-suitable first for image slots
    ranked = sorted(eligible, key=_image_suitability, reverse=True)

    image_slots = targets["flow_image"] + targets["stock_image"]
    image_ranked = ranked[:image_slots]
    video_ranked = ranked[image_slots:]

    # Quality protection: swap factual beats out of Flow Image into stock image/video
    flow_quota = targets["flow_image"]
    stock_img_quota = targets["stock_image"]
    flow_queue: List[VisualScene] = []
    stock_img_queue: List[VisualScene] = []
    demoted: List[VisualScene] = []

    for s in image_ranked:
        if mix.quality_protection and _is_factual(s):
            demoted.append(s)
            continue
        if len(flow_queue) < flow_quota:
            flow_queue.append(s)
        elif len(stock_img_queue) < stock_img_quota:
            stock_img_queue.append(s)
        else:
            demoted.append(s)

    # Fill remaining image quotas from leftover image_ranked / demoted non-factual
    leftovers = [s for s in image_ranked if s not in flow_queue and s not in stock_img_queue]
    leftovers.extend(demoted)
    for s in leftovers:
        if s in flow_queue or s in stock_img_queue:
            continue
        if len(flow_queue) < flow_quota and not (mix.quality_protection and _is_factual(s)):
            flow_queue.append(s)
        elif len(stock_img_queue) < stock_img_quota:
            stock_img_queue.append(s)

    assigned_ids = {s.scene_id for s in flow_queue} | {s.scene_id for s in stock_img_queue}
    video_pool = [s for s in video_ranked if s.scene_id not in assigned_ids]
    video_pool.extend([s for s in leftovers if s.scene_id not in assigned_ids])

    video_providers = _distribute(
        [
            ("stock_video", targets["stock_video"]),
            ("flow_video", targets["flow_video"]),
            ("youtube", targets["youtube"]),
        ]
    )
    # Match length
    while len(video_providers) < len(video_pool):
        video_providers.append("stock_video")
    video_providers = video_providers[: len(video_pool)]

    by_id = {s.scene_id: s for s in scenes}
    updates = {}
    for s in flow_queue:
        updates[s.scene_id] = "flow_image"
    for s in stock_img_queue:
        updates[s.scene_id] = "stock_image"
    for s, prov in zip(video_pool, video_providers):
        updates[s.scene_id] = prov

    new_scenes: List[VisualScene] = []
    for s in scenes:
        provider = updates.get(s.scene_id)
        if provider is None:
            new_scenes.append(s)
            continue
        pref, asset = _PROVIDER_ASSET[provider]
        fallbacks = list(s.fallbacks or [])
        if provider == "flow_image" and "stock_image" not in fallbacks:
            fallbacks = ["stock_image"] + [f for f in fallbacks if f != "stock_image"]
        elif provider == "flow_video" and "stock_video" not in fallbacks:
            fallbacks = ["stock_video"] + [f for f in fallbacks if f != "stock_video"]
        new_scenes.append(
            dataclasses.replace(
                s,
                provider_preference=pref,
                asset_type=asset,
                fallbacks=fallbacks,
            )
        )

    warnings = list(plan.warnings or [])
    n_flow_img = sum(1 for s in new_scenes if (s.provider_preference or "") == "flow_image")
    n_flow_vid = sum(1 for s in new_scenes if (s.provider_preference or "") == "flow_video")
    warnings.append(
        f"asset_mix_applied: flow_image={n_flow_img}/{len(new_scenes)} "
        f"flow_video={n_flow_vid}/{len(new_scenes)} "
        f"(targets image={mix.image_pct:.0f}% flow_image={mix.flow_image_pct:.0f}% "
        f"flow_video={mix.flow_video_pct:.0f}%)"
    )
    return VisualPlan(
        topic=plan.topic,
        scenes=new_scenes,
        warnings=warnings,
        allocation=plan.allocation,
    )
