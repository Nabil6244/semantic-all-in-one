"""Style Resolver — AUTO / MANUAL / CUSTOM (legacy → None)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .detect import detect_style
from .loader import load_brand_kit, load_style
from .schema import STYLE_MODES, BrandKit, ResolvedStyle, VideoStyle


def _normalize_mode(raw: Any) -> str:
    mode = str(raw or "").strip().lower()
    if mode in ("", "none", "legacy", "off", "unset"):
        return ""
    if mode not in STYLE_MODES:
        return ""
    return mode


def _run_detect(
    *,
    script: str = "",
    visual_plan: Any = None,
    rows: Optional[List[dict]] = None,
    title: str = "",
    state_dir: Any = None,
    gemini_settings: Optional[dict] = None,
) -> Tuple[VideoStyle, float, str, List[dict], dict, List[dict]]:
    style, conf, reason, alts, profile, scores = detect_style(
        script=script,
        visual_plan=visual_plan,
        rows=rows,
        title=title,
        state_dir=state_dir,
        gemini_settings=gemini_settings,
    )
    return (
        style,
        float(conf),
        reason,
        list(alts or []),
        profile.to_dict() if hasattr(profile, "to_dict") else {},
        list(scores or []),
    )


def merge_brand_overrides(style: VideoStyle, brand: BrandKit) -> VideoStyle:
    """CUSTOM: brand.overrides + soft caption/audio/typography fields when set.

    Brand must NOT silently rewrite core editorial philosophy keys unless present
    in brand.overrides (explicit configuration).
    """
    data = style.to_dict()
    overrides = dict(brand.overrides or {})
    # Soft brand surfaces (identity) — never wipe style intelligence weights.
    if isinstance(overrides.get("captions"), dict) or brand.captions:
        cap = dict(data.get("captions") or {})
        cap.update(dict(brand.captions or {}))
        if isinstance(overrides.get("captions"), dict):
            cap.update(overrides["captions"])
        data["captions"] = cap
    if isinstance(overrides.get("audio"), dict):
        audio = dict(data.get("audio") or {})
        audio.update(overrides["audio"])
        data["audio"] = audio
    if isinstance(overrides.get("visual"), dict):
        visual = dict(data.get("visual") or {})
        visual.update(overrides["visual"])
        data["visual"] = visual
    if isinstance(overrides.get("pacing"), dict):
        pacing = dict(data.get("pacing") or {})
        pacing.update(overrides["pacing"])
        data["pacing"] = pacing
    if isinstance(overrides.get("hook"), dict):
        hook = dict(data.get("hook") or {})
        hook.update(overrides["hook"])
        data["hook"] = hook
    if brand.ai_prompt_additions:
        ai = dict(data.get("ai_visual_prompt") or {})
        extra = str(brand.ai_prompt_additions).strip()
        if extra:
            base = str(ai.get("style") or "")
            ai["style"] = (base + " " + extra).strip() if base else extra
        data["ai_visual_prompt"] = ai
    if brand.preferred_visual_identity:
        visual = dict(data.get("visual") or {})
        visual["treatment"] = brand.preferred_visual_identity
        data["visual"] = visual
    return VideoStyle.from_dict(data)


def resolve_style(
    mode: Any = None,
    *,
    script: str = "",
    visual_plan: Any = None,
    brand_kit: Any = None,
    brand_kit_id: str = "",
    style_id: str = "",
    rows: Optional[List[dict]] = None,
    project_meta: Optional[Dict[str, Any]] = None,
    existing_settings: Optional[Dict[str, Any]] = None,
    title: str = "",
    state_dir: Any = None,
    gemini_settings: Optional[dict] = None,
) -> Optional[ResolvedStyle]:
    """
    Resolve a Video Style for EditorialPlan construction.

    Returns None when mode is unset/legacy so existing projects stay identical.
    AUTO works without Gemini; enrichment is optional and at most once per cache key.
    """
    del existing_settings  # reserved for future explicit project settings precedence
    meta = dict(project_meta or {})
    vs = meta.get("video_style") if isinstance(meta.get("video_style"), dict) else {}
    mode_n = _normalize_mode(mode if mode is not None and str(mode).strip() else vs.get("mode"))
    if not mode_n:
        return None

    style_id = str(style_id or vs.get("style_id") or "").strip()
    brand_kit_id = str(brand_kit_id or vs.get("brand_kit_id") or "").strip()

    kit: Optional[BrandKit] = None
    if isinstance(brand_kit, BrandKit):
        kit = brand_kit
    elif brand_kit_id:
        kit = load_brand_kit(brand_kit_id)

    if not style_id and kit and kit.default_style_id:
        style_id = kit.default_style_id

    detected_id = ""
    confidence = 1.0
    reason = ""
    alternatives: List[dict] = []
    content_profile: dict = {}
    style_scores: List[dict] = []
    style: Optional[VideoStyle] = None
    influences: List[str] = []

    detect_kw = dict(
        script=script,
        visual_plan=visual_plan,
        rows=rows,
        title=title,
        state_dir=state_dir,
        gemini_settings=gemini_settings if mode_n == "auto" else None,
    )

    if mode_n == "auto":
        detected, confidence, reason, alternatives, content_profile, style_scores = _run_detect(
            **detect_kw
        )
        style = detected
        detected_id = detected.id
        influences = list(detected.intelligence.influences or [])
        # Manual pin within AUTO: user chose another style after seeing detection
        if style_id and style_id != detected.id:
            pinned = load_style(style_id)
            if pinned is not None:
                style = pinned
                influences = list(pinned.intelligence.influences or [])
                reason = f"Auto detected {detected.id}; using selected {style_id}."
                confidence = max(float(confidence), 0.7)
    elif mode_n == "manual":
        style = load_style(style_id) if style_id else None
        if style is None:
            style, confidence, reason, alternatives, content_profile, style_scores = _run_detect(
                **detect_kw
            )
            detected_id = style.id
            influences = list(style.intelligence.influences or [])
            reason = "Manual style missing — fell back to detection: " + reason
            confidence = min(float(confidence), 0.5)
        else:
            reason = f"Manually selected {style.name}."
            detected_id = style.id
            influences = list(style.intelligence.influences or [])
            confidence = 1.0
    else:  # custom
        base_id = style_id or (kit.default_style_id if kit else "") or "premium_documentary"
        base = load_style(base_id)
        if base is None:
            base, confidence, reason, alternatives, content_profile, style_scores = _run_detect(
                **detect_kw
            )
            detected_id = base.id
            reason = "Custom base missing — " + reason
        else:
            detected_id = base.id
            reason = f"Custom style base {base.name}."
            confidence = 1.0
        if kit is not None:
            style = merge_brand_overrides(base, kit)
            reason = (reason + f" Brand kit '{kit.name or kit.id}' overrides applied.").strip()
        else:
            style = base
        influences = list(style.intelligence.influences or [])

    assert style is not None
    return ResolvedStyle(
        mode=mode_n,
        style=style,
        brand_kit=kit,
        confidence=float(confidence),
        reason=reason,
        detected_style_id=detected_id or style.id,
        alternatives=alternatives,
        influences=influences,
        content_profile=content_profile,
        style_scores=style_scores,
    )


def resolve_from_workspace(
    ws, *, script: str = "", visual_plan: Any = None, rows=None
) -> Optional[ResolvedStyle]:
    if ws is None:
        return None
    meta = ws.read_meta() if hasattr(ws, "read_meta") else {}
    state_dir = None
    if hasattr(ws, "state_dir"):
        state_dir = ws.state_dir
    elif hasattr(ws, "path"):
        state_dir = Path(ws.path) / "state"
    return resolve_style(
        script=script,
        visual_plan=visual_plan,
        rows=rows,
        project_meta=meta,
        state_dir=state_dir,
    )
