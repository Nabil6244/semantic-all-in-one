"""Apply ResolvedStyle onto EditorialScene fields (does not touch CSV assets)."""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from editorial.schema import ALLOWED_CAMERA_STYLES, ALLOWED_TRANSITIONS, EditorialPlan, EditorialScene

from .schema import ResolvedStyle, VideoStyle

_PACING = frozenset({"slow", "normal", "fast"})
_MUSIC = frozenset({"hold", "lift", "drop", "none"})

_REVEAL = re.compile(
    r"\b(changed everything|this changed|revealed|suddenly|breakthrough|discovery|"
    r"turned out|nobody expected)\b",
    re.I,
)
_COMPARE = re.compile(
    r"\b(compared (with|to)|versus|vs\.?|larger than|smaller than|before and after|"
    r"side by side|difference between)\b",
    re.I,
)
_SCALE = re.compile(
    r"\b(scale|compared with|billions|light[- ]years|diameter|orders of magnitude|"
    r"earth compared|jupiter|size of)\b",
    re.I,
)
_PROCESS = re.compile(
    r"\b(step by step|process|how (it|they|we)|first,? then|in order to|mechanism)\b",
    re.I,
)
_TIMELINE = re.compile(
    r"\b(in \d{3,4}|by \d{3,4}|timeline|chronolog|years? (of|later|earlier)|"
    r"century|during the|era)\b",
    re.I,
)
_LOCATION = re.compile(
    r"\b(across (europe|asia|africa|america)|in (rome|paris|london|egypt|china)|"
    r"map of|borders? of|city of|region)\b",
    re.I,
)
_CHARACTER = re.compile(
    r"\b(emperor|king|queen|general|scientist|leader|portrait of|named )\b",
    re.I,
)
_EVIDENCE = re.compile(
    r"\b(evidence|document|manuscript|archive|photograph|inscription|records?|"
    r"sources? show|excavation)\b",
    re.I,
)
_REFLECT = re.compile(
    r"\b(today we|looking back|in the end|ultimately|reflect|legacy|"
    r"what remains|remember)\b",
    re.I,
)
_EXPLAIN = re.compile(
    r"\b(this means|in other words|explained|because|here's why|imagine)\b",
    re.I,
)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def _purpose_pacing(style: VideoStyle, purpose: str) -> str:
    p = style.pacing
    mapping = {
        "hook": p.hook,
        "context": p.exposition,
        "explanation": p.exposition,
        "evidence": p.evidence,
        "emotion": p.climax,
        "reveal": p.climax,
        "comparison": p.evidence,
        "scale": p.exposition,
        "process": p.exposition,
        "timeline": p.exposition,
        "location": p.exposition,
        "character": p.exposition,
        "transition": p.default,
        "reflection": p.reflection,
        "outro": p.reflection,
    }
    raw = str(mapping.get(purpose) or p.default or "normal").strip().lower()
    return raw if raw in _PACING else "normal"


def _remap_purpose(style_id: str, scene: EditorialScene, index: int) -> str:
    """Style-aware purpose enrichment. Preserves true hook openings; may refine outro."""
    cur = str(scene.purpose or "context")
    text = f"{scene.narration_excerpt} {scene.visual_goal} {scene.visual_description}"
    # Keep structural hook for first moments
    if cur == "hook" and scene.start < 3.0:
        return cur
    # Strong reveal beats may override a mechanical last-scene outro
    if cur == "outro" and _REVEAL.search(text) and not re.search(
        r"\b(thanks for watching|subscribe|next time|goodbye|farewell)\b", text, re.I
    ):
        cur = "context"
    elif cur == "outro":
        return cur

    sid = style_id

    if sid == "history_documentary":
        if _EVIDENCE.search(text):
            return "evidence"
        if _TIMELINE.search(text):
            return "timeline"
        if _LOCATION.search(text):
            return "location"
        if _CHARACTER.search(text):
            return "character"
        if _REFLECT.search(text):
            return "reflection"
        if cur == "context":
            return "context"
    elif sid == "space_documentary":
        if _SCALE.search(text):
            return "scale"
        if _COMPARE.search(text):
            return "comparison"
        if _EXPLAIN.search(text) or cur == "explanation":
            return "explanation"
        if _REFLECT.search(text):
            return "reflection"
    elif sid == "ai_narration":
        if _REVEAL.search(text):
            return "reveal"
        if _COMPARE.search(text):
            return "comparison"
        if _PROCESS.search(text):
            return "process"
        if _EXPLAIN.search(text) and cur in ("context", "explanation"):
            return "explanation"
        if index == 0 or scene.start < 8:
            return "hook" if cur != "outro" else cur
    elif sid == "premium_documentary":
        if _REVEAL.search(text) and scene.attention_score >= 0.55:
            return "reveal"
        if _REFLECT.search(text):
            return "reflection"
        if cur == "emotion":
            return "emotion"
        if _COMPARE.search(text):
            return "comparison"
    return cur


def _variety_family(style: VideoStyle, scene: EditorialScene) -> str:
    family = str(style.intelligence.variety_family or "").strip()
    if not family:
        family = {
            "history_documentary": "archival",
            "premium_documentary": "cinematic",
            "ai_narration": "explainer",
            "space_documentary": "cosmic",
        }.get(style.id, "general")
    base = (scene.visual_variety_key or scene.asset_type_intent or "visual").strip()
    # Keep existing token but prefix family so anti-repeat is style-aware
    token = base.split("|")[0][:48] if base else "plate"
    return f"{family}:{token}"


def _pick_camera(
    style: VideoStyle,
    scene: EditorialScene,
    index: int,
    *,
    recent: Sequence[str],
) -> str:
    if str(scene.visual_treatment or "").strip():
        return scene.camera_style
    preferred = [c for c in style.visual.camera.preferred if c in ALLOWED_CAMERA_STYLES]
    if not preferred:
        return scene.camera_style
    intensity = _clamp(style.visual.camera.intensity)
    purpose = scene.purpose

    # Purpose-driven camera within style palette
    purpose_pref = {
        "reveal": "push_in",
        "scale": "pull_out",
        "emotion": "subtle_drift",
        "reflection": "hold",
        "evidence": "push_in" if style.id == "history_documentary" else "hold",
        "hook": preferred[0],
    }.get(purpose)

    if intensity < 0.35:
        for c in ("static", "hold", "subtle_drift"):
            if c in preferred:
                candidate = c
                break
        else:
            candidate = preferred[0]
        if purpose_pref and purpose_pref in preferred and purpose in ("reveal", "evidence"):
            candidate = purpose_pref
    else:
        candidate = purpose_pref if purpose_pref in preferred else preferred[index % len(preferred)]

    # Avoid mechanical alternation / immediate repeats of same camera
    if recent and candidate == recent[-1]:
        alts = [c for c in preferred if c != candidate]
        if alts:
            candidate = alts[index % len(alts)]
    # Avoid repeating identical camera+family triples
    if len(recent) >= 2 and recent[-1] == recent[-2] == candidate:
        alts = [c for c in preferred if c != candidate]
        if alts:
            candidate = alts[0]
    return candidate


def _seed_transition(style: VideoStyle, scene: EditorialScene, index: int) -> Optional[str]:
    if index == 0:
        default = style.transitions.default
        return default if default in ALLOWED_TRANSITIONS else scene.transition_in
    avoid = {str(a).lower() for a in style.transitions.avoid}
    preferred = [
        t for t in style.transitions.preferred if t in ALLOWED_TRANSITIONS and t not in avoid
    ]
    if not preferred:
        return scene.transition_in
    density = _clamp(style.pacing.transition_density)
    if (index * 0.37) % 1.0 > density and scene.transition_in:
        if scene.transition_in in avoid:
            return preferred[0]
        return scene.transition_in
    pick = preferred[index % len(preferred)]
    if pick in avoid:
        return style.transitions.default if style.transitions.default in ALLOWED_TRANSITIONS else None
    return pick


def _music_role(style: VideoStyle, scene: EditorialScene) -> str:
    intensity = _clamp(style.audio.music_intensity)
    if scene.purpose in ("hook", "reveal") and intensity >= 0.55:
        return "lift"
    if scene.purpose in ("outro", "emotion", "reflection"):
        return "drop" if intensity >= 0.4 else "hold"
    if intensity >= 0.7 and scene.attention_score >= 0.7:
        return "lift"
    if intensity <= 0.35:
        return "hold"
    return scene.music_role if scene.music_role in _MUSIC else "hold"


def apply_style_to_scenes(
    scenes: Sequence[EditorialScene],
    resolved: ResolvedStyle,
) -> None:
    """Mutate scenes in place. Never changes asset_type_intent / prompts."""
    style = resolved.style
    hook_w = float(style.hook.window_seconds or 30.0)
    attn_target = _clamp(style.hook.attention_target)
    amb = _clamp(style.audio.ambience_intensity, 0.15, 1.35)
    sfx_i = _clamp(style.audio.sfx_intensity)
    recent_cams: List[str] = []
    recent_families: List[str] = []

    for i, scene in enumerate(scenes):
        scene.purpose = _remap_purpose(style.id, scene, i)  # type: ignore[assignment]

        if scene.start < hook_w:
            scene.attention_score = _clamp(
                scene.attention_score * 0.55 + attn_target * 0.45
            )
            if style.hook.prefer_visual_change and scene.attention_score < attn_target - 0.05:
                scene.attention_score = _clamp(scene.attention_score + 0.08)
            if style.id == "ai_narration" and scene.start < 30:
                scene.attention_score = _clamp(scene.attention_score + 0.06)

        # Style-aware visual variety key (anti-repeat family)
        family_key = _variety_family(style, scene)
        if recent_families and family_key == recent_families[-1]:
            # Soft diversify suffix so QA / pacing sees a change signal
            family_key = f"{family_key}|alt{i % 3}"
        scene.visual_variety_key = family_key
        recent_families.append(family_key)

        scene.pacing_bias = _purpose_pacing(style, scene.purpose)  # type: ignore[assignment]
        scene.camera_style = _pick_camera(style, scene, i, recent=recent_cams)  # type: ignore[assignment]
        recent_cams.append(scene.camera_style)

        tr = _seed_transition(style, scene, i)
        if tr:
            scene.transition_in = tr
        scene.ambience_intensity = round(amb * (0.85 + 0.3 * scene.attention_score), 4)
        scene.music_role = _music_role(style, scene)  # type: ignore[assignment]

        # Selective silence around reveals (history / space / premium)
        if scene.purpose in ("reveal", "reflection") and style.id in (
            "history_documentary",
            "space_documentary",
            "premium_documentary",
        ):
            scene.allow_silence = True

        if sfx_i >= 0.65 and scene.purpose in ("hook", "emotion", "reveal") and not scene.sfx_moments:
            scene.sfx_moments = [
                {
                    "at": round(scene.start + min(0.4, scene.duration * 0.15), 3),
                    "kind": "accent",
                    "strength": round(0.45 + 0.4 * sfx_i, 3),
                }
            ]
        elif sfx_i <= 0.3 and scene.purpose not in ("reveal", "hook"):
            scene.sfx_moments = []


def apply_resolved_style(plan: EditorialPlan, resolved: Optional[ResolvedStyle]) -> EditorialPlan:
    """Apply style to plan scenes + metadata. No-op when resolved is None."""
    if resolved is None:
        return plan
    plan.hook_window_s = float(resolved.style.hook.window_seconds or plan.hook_window_s)
    apply_style_to_scenes(plan.scenes, resolved)
    plan.music = dict(plan.music or {})
    plan.music.setdefault("style_duck_db", float(resolved.style.audio.music_duck_db))
    plan.music.setdefault("style_music_intensity", float(resolved.style.audio.music_intensity))
    # Asset preferences are ranking signals only — never mutate scene.asset_type_intent
    plan.music.setdefault(
        "style_asset_preferences",
        list(resolved.style.assets.preferred or []),
    )

    meta = {
        "style_id": resolved.style_id,
        "style_confidence": round(float(resolved.confidence), 3),
        "style_reason": resolved.reason,
        "style_influences": list(
            resolved.influences or resolved.style.intelligence.influences or []
        ),
        "mode": resolved.mode,
        "brand_kit_id": resolved.brand_kit_id or None,
        "alternatives": list(resolved.alternatives or []),
        "asset_preferences": list(resolved.style.assets.preferred or []),
    }
    setattr(plan, "style", meta)
    return plan


def style_prompt_adornment(resolved: Optional[ResolvedStyle]) -> str:
    """Extra VisualDirector guidance text (Analyze Script only)."""
    if resolved is None:
        return ""
    parts: List[str] = []
    ai = resolved.style.ai_visual_prompt
    if ai.style:
        parts.append(f"Visual style: {ai.style}.")
    if ai.composition:
        parts.append(f"Composition: {ai.composition}.")
    if ai.avoid:
        parts.append("Avoid: " + ", ".join(ai.avoid) + ".")
    sg = resolved.style.search_guidance
    if sg.prefer_terms:
        parts.append("Prefer visual subjects: " + ", ".join(sg.prefer_terms[:8]) + ".")
    if sg.avoid_terms:
        parts.append("Avoid visual subjects: " + ", ".join(sg.avoid_terms[:8]) + ".")
    vr = resolved.style.visual_roles
    if vr.weights:
        top_roles = sorted(vr.weights.items(), key=lambda kv: kv[1], reverse=True)[:4]
        parts.append(
            "Visual roles to prioritize: "
            + ", ".join(r.replace("_", " ") for r, _ in top_roles)
            + "."
        )
    story = resolved.style.storytelling
    if story.hook_strategy:
        parts.append(f"Hook strategy: {story.hook_strategy}.")
    if resolved.brand_kit and resolved.brand_kit.ai_prompt_additions:
        parts.append(str(resolved.brand_kit.ai_prompt_additions).strip())
    return " ".join(p for p in parts if p).strip()


def asset_preference_rank(resolved: Optional[ResolvedStyle], asset_type: str) -> float:
    """Non-destructive ranking signal (higher = preferred). Does not select assets."""
    if resolved is None:
        return 0.0
    preferred = [str(x).lower() for x in (resolved.style.assets.preferred or [])]
    key = str(asset_type or "").lower()
    if not preferred or not key:
        return 0.0
    try:
        idx = preferred.index(key)
        return float(len(preferred) - idx) / float(len(preferred))
    except ValueError:
        return 0.0
