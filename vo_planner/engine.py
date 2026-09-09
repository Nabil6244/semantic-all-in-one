"""VO-Aware Visual Planner engine.

SCRIPT + VO → Script Analyzer (existing) + VO Analyzer → align → coverage →
memory/progression/QC → compact Claude handoff.

The planner itself adds no LLM/API calls. Script Analyzer is invoked as-is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional, Tuple

from visual_director.schema import VisualPlan

from .beat_align import align_beats_to_vo
from .bridge import to_visual_plan
from .cache import load_cached_plan, plan_cache_key, save_cached_plan
from .coverage import plan_coverage
from .errors import VoPlannerStageError
from .preferences import allocation_settings_from_mix, apply_asset_mix_to_plan
from .qc import validate_plan
from .schema import (
    VO_PLANNER_VERSION,
    AssetMixPreferences,
    VOAnalysis,
    VoAwarePlan,
)
from .vo_analyzer import analyze_voiceover

ProgressCallback = Callable[[str, Optional[float]], None]


def _emit(cb: Optional[ProgressCallback], message: str, fraction: Optional[float] = None) -> None:
    if cb:
        cb(message, fraction)


def analyze_vo_only(
    audio_path: Path | str,
    *,
    state_dir: Optional[Path] = None,
    whisper_model: str = "base",
    on_progress: Optional[ProgressCallback] = None,
    force: bool = False,
) -> VOAnalysis:
    return analyze_voiceover(
        audio_path,
        state_dir=state_dir,
        whisper_model=whisper_model,
        on_progress=on_progress,
        force=force,
    )


def build_vo_aware_plan(
    script: str,
    audio_path: Path | str,
    *,
    semantic_plan: VisualPlan,
    vo: Optional[VOAnalysis] = None,
    state_dir: Optional[Path] = None,
    whisper_model: str = "base",
    asset_mix: Optional[AssetMixPreferences] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> VoAwarePlan:
    """Core planner: align Script Analyzer beats to VO and build coverage."""
    mix = (asset_mix or AssetMixPreferences()).normalized()
    if vo is None:
        try:
            vo = analyze_voiceover(
                audio_path,
                state_dir=state_dir,
                whisper_model=whisper_model,
                on_progress=on_progress,
            )
        except VoPlannerStageError:
            raise
        except Exception as exc:
            raise VoPlannerStageError(
                "voiceover_analysis",
                str(exc) or "Could not analyze voiceover timing.",
                cause=exc,
            ) from exc

    n_scenes = len(semantic_plan.scenes or [])
    _emit(on_progress, f"Aligning {n_scenes} semantic beat(s) to voiceover…", 0.55)
    try:
        beats = align_beats_to_vo(semantic_plan.scenes, vo)
    except VoPlannerStageError:
        raise
    except Exception as exc:
        raise VoPlannerStageError(
            "beat_alignment",
            str(exc) or "Could not align script beats to voiceover timing.",
            cause=exc,
        ) from exc

    _emit(on_progress, f"Planning visual coverage for {len(beats)} beat(s)…", 0.7)
    try:
        units, contracts, memory, stages = plan_coverage(beats, on_progress=on_progress)
    except VoPlannerStageError:
        raise
    except Exception as exc:
        raise VoPlannerStageError(
            "coverage_planning",
            str(exc) or "Could not plan visual coverage.",
            cause=exc,
        ) from exc

    _emit(on_progress, "Running coverage QC…", 0.82)
    try:
        issues = validate_plan(beats, units, audio_duration=vo.audio_duration)
        warnings_extra: list[str] = []
    except Exception as exc:
        issues = []
        warnings_extra = [f"QC skipped: {exc}"]

    topic = semantic_plan.topic or "VO-Aware Plan"
    warnings = list(semantic_plan.warnings or []) + warnings_extra
    return VoAwarePlan(
        topic=topic,
        planner_version=VO_PLANNER_VERSION,
        audio_duration=vo.audio_duration,
        beats=beats,
        units=units,
        contracts=contracts,
        memory_summary=memory.summary(),
        progression=stages,
        qc_issues=issues,
        asset_mix=mix,
        vo_summary={
            "sentence_count": len(vo.sentences),
            "pause_count": len(vo.pauses),
            "mean_speech_density": vo.mean_speech_density,
            "word_count": len(vo.words),
            "whisper_model": vo.whisper_model,
        },
        warnings=warnings,
    )


def plan_from_voiceover(
    script: str,
    audio_path: Path | str,
    *,
    settings: Optional[dict] = None,
    state_dir: Optional[Path] = None,
    whisper_model: str = "base",
    style_guidance: str = "",
    asset_mix: Optional[AssetMixPreferences] = None,
    semantic_plan: Optional[VisualPlan] = None,
    vo: Optional[VOAnalysis] = None,
    on_progress: Optional[ProgressCallback] = None,
    use_cache: bool = True,
) -> Tuple[VisualPlan, VoAwarePlan]:
    """Full Option 3 pipeline → compact Claude handoff."""
    text = (script or "").strip()
    if not text:
        raise VoPlannerStageError("script_validation", "Paste your narration script first.")
    path = Path(audio_path)
    if not path.is_file():
        raise VoPlannerStageError(
            "voiceover_validation",
            f"Voiceover file not found: {path}",
        )

    mix = (asset_mix or AssetMixPreferences()).normalized()
    key = plan_cache_key(text, path, mix=mix, whisper_model=whisper_model)

    if use_cache and state_dir is not None:
        cached = load_cached_plan(state_dir, key)
        if cached and cached.get("compact") and semantic_plan is None and vo is None:
            visual_dict = cached.get("visual_plan")
            if isinstance(visual_dict, dict) and visual_dict.get("scenes"):
                _emit(on_progress, "Reusing cached Claude plan…", 0.9)
                try:
                    visual = _visual_plan_from_dict(visual_dict)
                    vo_plan = _vo_plan_from_compact(cached["compact"], mix)
                    visual.vo_aware = cached.get("compact")  # type: ignore[attr-defined]
                    visual.vo_aware_full = cached.get("full")  # type: ignore[attr-defined]
                    return visual, vo_plan
                except Exception as exc:
                    _emit(on_progress, f"Cache reuse failed — regenerating ({exc})", 0.08)

    if semantic_plan is None:
        _emit(on_progress, "Analyzing script into semantic beats…", 0.05)
        try:
            from visual_director import VisualDirector

            semantic_plan = VisualDirector(settings=settings or {}).plan(
                text,
                style_guidance=style_guidance,
                on_progress=on_progress,
                state_dir=state_dir,
                use_cache=use_cache,
            )
        except VoPlannerStageError:
            raise
        except Exception as exc:
            raise VoPlannerStageError(
                "script_analyzer",
                str(exc) or "Script Analyzer could not build semantic beats.",
                cause=exc,
            ) from exc

    if not semantic_plan.scenes:
        raise VoPlannerStageError(
            "script_analyzer",
            "Script Analyzer returned no beats. Check that the script has spoken narration.",
        )

    # Soft-apply asset mix (incl. Flow Image %) onto analyzer providers so the
    # Claude handoff / VisualPlan actually reflect the PLAN tab targets.
    _emit(on_progress, "Applying asset mix preferences…", 0.48)
    semantic_plan = apply_asset_mix_to_plan(semantic_plan, mix)

    vo_plan = build_vo_aware_plan(
        text,
        path,
        semantic_plan=semantic_plan,
        vo=vo,
        state_dir=state_dir,
        whisper_model=whisper_model,
        asset_mix=mix,
        on_progress=on_progress,
    )

    _emit(on_progress, "Building compact Claude handoff…", 0.9)
    try:
        visual = to_visual_plan(vo_plan, source_scenes=semantic_plan.scenes)
    except Exception as exc:
        raise VoPlannerStageError(
            "visual_plan",
            str(exc) or "Could not build Claude Visual Production Plan.",
            cause=exc,
        ) from exc

    if use_cache and state_dir is not None:
        try:
            save_cached_plan(
                state_dir,
                key,
                {
                    "compact": vo_plan.compact_handoff(),
                    "full": vo_plan.to_dict(),
                    "visual_plan": visual.to_dict(),
                },
            )
        except Exception:
            pass

    _emit(
        on_progress,
        f"Claude plan ready — {len(visual.scenes)} beats, {len(vo_plan.units)} units",
        0.98,
    )
    return visual, vo_plan


def _visual_plan_from_dict(data: dict) -> VisualPlan:
    from visual_director.schema import VisualScene

    scenes = []
    for s in data.get("scenes") or []:
        if not isinstance(s, dict):
            continue
        scenes.append(
            VisualScene(
                scene_id=int(s.get("scene_id") or len(scenes) + 1),
                narration=str(s.get("narration") or ""),
                visual_goal=str(s.get("visual_goal") or ""),
                visual_description=str(s.get("visual_description") or ""),
                asset_type=str(s.get("asset_type") or "stock_video"),
                provider_preference=str(s.get("provider_preference") or "stock_video"),
                search_queries=list(s.get("search_queries") or []),
                timestamp_needed=bool(s.get("timestamp_needed")),
                timestamp_hint=str(s.get("timestamp_hint") or ""),
                duration=float(s.get("duration") or 3.0),
                importance=str(s.get("importance") or "medium"),
                fallbacks=list(s.get("fallbacks") or []),
                visual_treatment=str(s.get("visual_treatment") or ""),
                transition=str(s.get("transition") or "cut"),
                minimum_quality=str(s.get("minimum_quality") or "1080p"),
            )
        )
    return VisualPlan(
        topic=str(data.get("topic") or "VO-Aware Plan"),
        scenes=scenes,
        warnings=list(data.get("warnings") or []),
        allocation=data.get("allocation"),
    )


def _vo_plan_from_compact(compact: dict, mix: AssetMixPreferences) -> VoAwarePlan:
    """Minimal VoAwarePlan for cache return (preview/export)."""
    from .schema import AlignedBeat, CoverageUnit, QCIssue

    beats = [
        AlignedBeat(
            beat_id=int(b.get("id") or 0),
            narration=str(b.get("narr") or ""),
            start=float((b.get("t") or [0, 0])[0]),
            end=float((b.get("t") or [0, 0])[1]),
            align_confidence=1.0,
            visual_goal=str(b.get("goal") or ""),
            narrative_importance=float(b.get("narr_imp") or 0.5),
            visual_opportunity=float(b.get("vis_opp") or 0.5),
            opportunity_tags=list(b.get("tags") or []),
            idea_count=int(b.get("ideas") or 1),
        )
        for b in (compact.get("beats") or [])
        if isinstance(b, dict)
    ]
    units = [
        CoverageUnit(
            unit_id=str(u.get("id") or ""),
            beat_id=int(u.get("beat") or 0),
            start=float((u.get("t") or [0, 0])[0]),
            end=float((u.get("t") or [0, 0])[1]),
            strategy=str(u.get("strat") or "single_shot"),
            visual_purpose=str(u.get("why") or u.get("purpose") or ""),
            evidence_type=str(u.get("evidence") or ""),
            subject=str(u.get("what") or u.get("subject") or ""),
            shot_scale=str(u.get("scale") or "medium"),
            camera=str(u.get("cam") or "eye_level"),
            motion=str(u.get("motion") or "static"),
            specificity=0.5,
            visual_importance=float(u.get("importance") or 0.5),
            novelty=float(u.get("novelty") or 0.5),
            repetition_risk=float(u.get("rep_risk") or 0.0),
            generic_risk=float(u.get("generic_risk") or 0.0),
            strong_opportunity=bool(u.get("strong")),
            quality_target=str(u.get("quality") or "1080p"),
            change_trigger=str(u.get("trigger") or ""),
            previous_relationship=str(u.get("prev") or ""),
            next_relationship=str(u.get("next") or ""),
            avoid=list(u.get("avoid") or []),
            progression_stage=str(u.get("stage") or "environment"),
            intentional_callback=bool(u.get("callback")),
            opportunity_tags=list(u.get("tags") or []),
            quality_requirements=dict(u.get("req") or {}) if isinstance(u.get("req"), dict) else {},
            location=str(u.get("where") or ""),
            meaningful_action=str(u.get("action") or ""),
            editability=str(u.get("editability") or "medium"),
        )
        for u in (compact.get("units") or [])
        if isinstance(u, dict)
    ]
    issues = [
        QCIssue(
            code=str(i.get("code") or ""),
            severity=str(i.get("sev") or "info"),
            message=str(i.get("msg") or ""),
            beat_id=i.get("beat"),
        )
        for i in (compact.get("qc") or [])
        if isinstance(i, dict)
    ]
    return VoAwarePlan(
        topic=str(compact.get("topic") or ""),
        planner_version=int(compact.get("v") or VO_PLANNER_VERSION),
        audio_duration=float(compact.get("audio_s") or 0),
        beats=beats,
        units=units,
        contracts=[],
        memory_summary=dict(compact.get("memory") or {}),
        progression=list(compact.get("progression") or []),
        qc_issues=issues,
        asset_mix=mix,
        vo_summary={},
    )


def format_plan_preview(vo_plan: VoAwarePlan, *, max_beats: int = 12, max_units: int = 16) -> str:
    """Short human summary for UI — not the Claude payload."""
    mins = vo_plan.audio_duration / 60.0
    lines = [
        "Claude Visual Production Plan",
        f"Topic: {vo_plan.topic}",
        f"Audio: {vo_plan.audio_duration:.1f}s ({mins:.1f} min) | "
        f"Beats: {len(vo_plan.beats)} | Units: {len(vo_plan.units)}",
        f"Progression: {' → '.join(vo_plan.progression[:10])}"
        + ("…" if len(vo_plan.progression) > 10 else ""),
        "",
    ]
    warn_qc = [i for i in vo_plan.qc_issues if i.severity in ("error", "warning")]
    if warn_qc:
        lines.append("Warnings:")
        for issue in warn_qc[:12]:
            lines.append(f"  • {issue.message}")
        if len(warn_qc) > 12:
            lines.append(f"  • … +{len(warn_qc) - 12} more")
        lines.append("")
    lines.append("Sample beats:")
    for beat in vo_plan.beats[:max_beats]:
        lines.append(
            f"  B{beat.beat_id:02d} [{beat.start:.1f}-{beat.end:.1f}s] "
            f"{beat.narration[:90]}{'…' if len(beat.narration) > 90 else ''}"
        )
    if len(vo_plan.beats) > max_beats:
        lines.append(f"  … +{len(vo_plan.beats) - max_beats} more beats in JSON")
    lines.append("")
    lines.append("Sample coverage:")
    for u in vo_plan.units[:max_units]:
        lines.append(
            f"  {u.unit_id} {u.duration:.1f}s {u.strategy} | {u.subject} | {u.visual_purpose}"
        )
    if len(vo_plan.units) > max_units:
        lines.append(f"  … +{len(vo_plan.units) - max_units} more units in JSON")
    lines.append("")
    lines.append("Use Copy / Export for the compact Claude JSON handoff.")
    return "\n".join(lines)


def compact_handoff_json(vo_plan: VoAwarePlan) -> str:
    return json.dumps(vo_plan.compact_handoff(), indent=2, ensure_ascii=False)


derive_allocation_settings = allocation_settings_from_mix
