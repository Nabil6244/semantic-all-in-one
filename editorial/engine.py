"""Editorial Decision Engine — orchestration after Whisper alignment.

Pipeline:
  EditorialPlan (VO windows)
    → beat/intent enrichment (deterministic)
    → media editability
    → shot / coverage planning (EditDecision)
    → layered timeline
    → editorial events (AV sync cues)
    → QC + high-confidence auto-fixes
    → render-ready maps
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .complements import (
    AssetCandidate,
    editorial_purpose_for_role,
    infer_complement_role,
)
from .continuity import visual_role_for_scene
from .edit_decision import EditDecision, EditorialEvent
from .schema import EditorialPlan, EditorialScene
from .shot_planner import plan_all_edit_decisions
from .timeline import EditorialTimeline, TimelineEvent, validate_visual_timeline


def _resolve_media_paths(
    scenes: Sequence[EditorialScene],
    images_dir: Optional[Path],
) -> Dict[str, Path]:
    if images_dir is None or not Path(images_dir).is_dir():
        return {}
    try:
        from video_generator import find_image_for_scene
    except Exception:
        return {}
    out: Dict[str, Path] = {}
    for scene in scenes:
        sn = str(scene.scene_number)
        path = find_image_for_scene(Path(images_dir), sn)
        if path is not None:
            out[sn] = path
            out[sn.zfill(3)] = path
            out[sn.lstrip("0") or sn] = path
    return out


def _coverage_by_scene(images_dir: Optional[Path]) -> Dict[str, dict]:
    if images_dir is None or not Path(images_dir).is_dir():
        return {}
    try:
        from video_generator import manifest_coverage_flags

        return manifest_coverage_flags(Path(images_dir))
    except Exception:
        return {}


def _candidates_for_scene(
    scene: EditorialScene,
    *,
    images_dir: Path,
    primary: Optional[Path],
    coverage: Optional[dict],
) -> List[AssetCandidate]:
    """Build primary + on-disk / manifest complementary candidates."""
    from video_generator import (
        complement_asset_id,
        find_complement_assets_for_scene,
        manifest_scene_record,
    )

    sn = str(scene.scene_number)
    beat_role = visual_role_for_scene(scene)
    cands: List[AssetCandidate] = []
    if primary and primary.is_file():
        cands.append(
            AssetCandidate(
                asset_id=sn.zfill(3),
                path=primary,
                is_primary=True,
                asset_class=scene.asset_type_intent,
                query_hint=scene.visual_description or scene.narration_excerpt[:80],
                visual_role="context",
                editorial_purpose="context",
            )
        )

    record = manifest_scene_record(images_dir, sn)
    meta_comps = record.get("complement_assets") if isinstance(record, dict) else None
    seen: set[str] = set()

    def _add(path: Path, *, asset_class: str = "", query: str = "", role: str = "", index: int = 0) -> None:
        if not path.is_file():
            return
        key = str(path.resolve())
        if key in seen:
            return
        if primary and path.resolve() == primary.resolve():
            return
        seen.add(key)
        aid = complement_asset_id(sn, path)
        vrole = role or infer_complement_role(
            primary_role=beat_role,
            asset_class=asset_class,
            query_hint=query,
            index=index,
        )
        cands.append(
            AssetCandidate(
                asset_id=aid,
                path=path,
                is_primary=False,
                asset_class=asset_class or "",
                query_hint=query or "",
                visual_role=vrole,
                editorial_purpose=editorial_purpose_for_role(vrole),
                metadata={},
            )
        )

    if isinstance(meta_comps, list):
        for i, item in enumerate(meta_comps):
            if not isinstance(item, dict):
                continue
            p = Path(str(item.get("path") or ""))
            if not p.is_file():
                # Relative to images_dir
                alt = images_dir / Path(str(item.get("path") or "")).name
                p = alt if alt.is_file() else p
            _add(
                p,
                asset_class=str(item.get("asset_class") or ""),
                query=str(item.get("query_hint") or item.get("semantic_query_hint") or ""),
                role=str(item.get("visual_role") or ""),
                index=i,
            )

    # Disk complements (001_b, 001_c, …) — fill any gaps
    for i, path in enumerate(find_complement_assets_for_scene(images_dir, sn)):
        segs = (coverage or {}).get("segments") or []
        seg = segs[min(i + 1, len(segs) - 1)] if isinstance(segs, list) and segs else {}
        if not isinstance(seg, dict):
            seg = {}
        _add(
            path,
            asset_class=str(seg.get("asset_class") or ""),
            query=str(seg.get("semantic_query_hint") or ""),
            role=str(seg.get("visual_role") or ""),
            index=i,
        )
    return cands


def _build_candidates_by_scene(
    scenes: Sequence[EditorialScene],
    images_dir: Optional[Path],
    media_paths: Dict[str, Path],
    coverage_by_scene: Dict[str, dict],
) -> Dict[str, List[AssetCandidate]]:
    if images_dir is None or not Path(images_dir).is_dir():
        return {}
    root = Path(images_dir)
    out: Dict[str, List[AssetCandidate]] = {}
    for scene in scenes:
        sn = str(scene.scene_number)
        primary = (
            media_paths.get(sn)
            or media_paths.get(sn.zfill(3))
            or media_paths.get(sn.lstrip("0") or sn)
        )
        cov = (
            coverage_by_scene.get(sn)
            or coverage_by_scene.get(sn.zfill(3))
            or coverage_by_scene.get(sn.lstrip("0") or sn)
            or {}
        )
        cands = _candidates_for_scene(
            scene, images_dir=root, primary=primary, coverage=cov
        )
        if cands:
            out[sn] = cands
            out[sn.zfill(3)] = cands
            out[sn.lstrip("0") or sn] = cands
    return out


def build_timeline_from_decisions(
    plan: EditorialPlan,
    decisions: Sequence[EditDecision],
    *,
    events: Optional[Sequence[EditorialEvent]] = None,
) -> EditorialTimeline:
    """Materialize layer events from edit decisions + editorial events."""
    timeline = EditorialTimeline(audio_end=float(plan.audio_end))
    by_sn = {str(d.scene_number): d for d in decisions}
    for scene in plan.scenes:
        decision = by_sn.get(str(scene.scene_number))
        if decision is None:
            continue
        t = float(scene.start)
        for i, shot in enumerate(decision.shots):
            end = t + float(shot.output_duration)
            track = "VIDEO_1" if i % 2 == 0 else "VIDEO_2"
            if decision.strategy == "IMAGE_MOTION" or (
                decision.shots and shot.scale >= 1.0 and "image" in (decision.source_asset or "").lower()
            ):
                # Prefer IMAGE track label for stills; renderer still uses path
                if str(decision.source_asset).lower().endswith(
                    (".png", ".jpg", ".jpeg", ".webp")
                ):
                    track = "IMAGE"
            timeline.add(
                TimelineEvent(
                    event_id=shot.shot_id,
                    track=track,  # type: ignore[arg-type]
                    start=round(t, 4),
                    end=round(end, 4),
                    scene_number=str(scene.scene_number),
                    source=shot.source_path or decision.source_asset,
                    scale=float(shot.scale),
                    position_x=float(shot.crop_x),
                    position_y=float(shot.crop_y),
                    z_index=10 + i,
                    animation=shot.camera_style,
                    transition_in=shot.transition_in,
                    metadata={
                        "shot_size": shot.shot_size,
                        "source_start": shot.source_start,
                        "source_end": shot.source_end,
                        "speed": shot.speed,
                        "hold_tail": shot.hold_tail,
                        "strategy": decision.strategy,
                        "visual_role": shot.visual_role or decision.visual_role,
                        "editorial_purpose": shot.editorial_purpose,
                        "asset_id": shot.asset_id,
                        "transition_duration": shot.transition_duration,
                        "transition_direction": shot.transition_direction,
                    },
                )
            )
            t = end

        # Voiceover bed for the scene window
        timeline.add(
            TimelineEvent(
                event_id=f"vo_{scene.scene_number}",
                track="VOICEOVER",
                start=float(scene.start),
                end=float(scene.end),
                scene_number=str(scene.scene_number),
                z_index=0,
                metadata={"purpose": scene.purpose},
            )
        )
        if scene.ambience_profile and scene.ambience_profile != "none":
            timeline.add(
                TimelineEvent(
                    event_id=f"amb_{scene.scene_number}",
                    track="AMBIENCE",
                    start=float(scene.start),
                    end=float(scene.end),
                    scene_number=str(scene.scene_number),
                    opacity=float(scene.ambience_intensity),
                    z_index=1,
                    metadata={"profile": scene.ambience_profile},
                )
            )

    for ev in events or []:
        track = "GRAPHICS"
        if ev.kind in ("statistic", "emphasis", "chapter"):
            track = "TEXT"
        elif ev.sfx_action and not (ev.text_action or ev.visual_action):
            track = "SFX"
        meta = {
            "kind": ev.kind,
            "visual_action": ev.visual_action,
            "text_action": ev.text_action,
            "sfx_action": ev.sfx_action,
            "music_action": ev.music_action,
        }
        payload = getattr(ev, "payload", None)
        if isinstance(payload, dict) and payload:
            meta["payload"] = dict(payload)
        timeline.add(
            TimelineEvent(
                event_id=ev.event_id,
                track=track,  # type: ignore[arg-type]
                start=float(ev.start),
                end=float(ev.end),
                scene_number=ev.scene_number,
                source=str((payload or {}).get("text") or "") if isinstance(payload, dict) else "",
                animation=ev.text_action or ev.visual_action,
                z_index=50,
                metadata=meta,
            )
        )
    return timeline


def plan_editorial_events(
    plan: EditorialPlan,
    *,
    intents: Optional[Mapping[str, Any]] = None,
) -> List[EditorialEvent]:
    """Deterministic AV sync cues, optionally biased by AI EditorialIntent."""
    from .intent import CONF_MEDIUM, EditorialIntent

    events: List[EditorialEvent] = []
    intent_map = intents or {}
    for scene in plan.scenes:
        sn = str(scene.scene_number)
        intent = intent_map.get(sn) or intent_map.get(sn.zfill(3))
        if isinstance(intent, dict):
            intent = EditorialIntent.from_dict(intent)
        if not isinstance(intent, EditorialIntent):
            intent = None

        role = visual_role_for_scene(scene)
        if intent and intent.confidence >= CONF_MEDIUM:
            role = intent.planner_visual_role() or role

        mid = scene.start + scene.duration * 0.45
        want_stat = role in ("statistic", "claim_evidence") or scene.purpose == "evidence"
        if intent and intent.confidence >= CONF_MEDIUM:
            if intent.text_strategy in ("statistic", "data_graphic") or intent.graphic_strategy in (
                "chart",
                "data_graphic",
            ):
                want_stat = True
            if intent.text_strategy == "none" and intent.evidence_level == "none":
                want_stat = False

        if want_stat:
            events.append(
                EditorialEvent(
                    event_id=f"stat_{scene.scene_number}",
                    start=round(mid - 0.15, 3),
                    end=round(min(scene.end, mid + 1.8), 3),
                    kind="statistic",
                    scene_number=str(scene.scene_number),
                    visual_action="emphasis",
                    text_action="punch" if not intent or intent.text_strategy != "none" else "",
                    sfx_action=(
                        "subtle_hit"
                        if not intent or intent.sound_strategy not in ("none", "silence")
                        else ""
                    ),
                    music_action="hold",
                    confidence=0.7 if not intent else float(intent.confidence),
                )
            )

        want_reveal = scene.purpose == "reveal" or (
            scene.attention_score >= 0.82 and scene.purpose in ("hook", "emotion")
        )
        if intent and intent.confidence >= CONF_MEDIUM:
            want_reveal = bool(intent.reveal or intent.reveal_phase in ("reveal", "emphasize"))
        if want_reveal:
            reveal_at = scene.start + min(scene.duration * 0.55, max(0.8, scene.duration - 0.6))
            sfx = "impact"
            music = "lift"
            if intent and intent.confidence >= CONF_MEDIUM:
                if intent.sound_strategy in ("none", "silence"):
                    sfx = ""
                elif intent.sound_strategy == "impact":
                    sfx = "impact"
                if intent.sound_strategy == "music_drop":
                    music = "drop"
                elif intent.sound_strategy == "music_hold":
                    music = "hold"
            events.append(
                EditorialEvent(
                    event_id=f"reveal_{scene.scene_number}",
                    start=round(reveal_at, 3),
                    end=round(min(scene.end, reveal_at + 1.2), 3),
                    kind="reveal",
                    scene_number=str(scene.scene_number),
                    visual_action="reveal",
                    text_action="fade",
                    sfx_action=sfx,
                    music_action=music,
                    confidence=0.75 if not intent else float(intent.confidence),
                )
            )

        want_loc = scene.purpose == "location" or role == "geography"
        if intent and intent.confidence >= CONF_MEDIUM:
            want_loc = intent.text_strategy == "location" or intent.visual_role == "geography"
        if want_loc:
            events.append(
                EditorialEvent(
                    event_id=f"loc_{scene.scene_number}",
                    start=round(scene.start + 0.2, 3),
                    end=round(min(scene.end, scene.start + 2.5), 3),
                    kind="location",
                    scene_number=str(scene.scene_number),
                    visual_action="establish",
                    text_action="label",
                    sfx_action="",
                    music_action="hold",
                    confidence=0.65 if not intent else float(intent.confidence),
                )
            )

        # Explicit emphasis / callout without statistic
        if (
            intent
            and intent.confidence >= CONF_MEDIUM
            and intent.text_strategy in ("emphasis", "callout", "quote", "name", "chapter")
            and not want_stat
        ):
            events.append(
                EditorialEvent(
                    event_id=f"text_{scene.scene_number}",
                    start=round(scene.start + min(0.4, scene.duration * 0.2), 3),
                    end=round(min(scene.end, scene.start + min(2.8, scene.duration * 0.7)), 3),
                    kind="emphasis",
                    scene_number=str(scene.scene_number),
                    visual_action="",
                    text_action=intent.text_strategy,
                    sfx_action="subtle_hit" if intent.sound_strategy == "impact" else "",
                    music_action="hold",
                    confidence=float(intent.confidence),
                )
            )
    return events


def qc_edit_decisions(
    plan: EditorialPlan,
    decisions: Sequence[EditDecision],
) -> List[dict]:
    """Pre-render QC on edit decisions. Returns issue dicts; may mutate decisions."""
    issues: List[dict] = []
    by_sn = {str(d.scene_number): d for d in decisions}
    recent_strategies: List[str] = []
    recent_assets: List[str] = []

    for scene in plan.scenes:
        d = by_sn.get(str(scene.scene_number))
        if d is None:
            issues.append(
                {
                    "scene_number": scene.scene_number,
                    "severity": "WARN",
                    "category": "coverage",
                    "message": "Missing edit decision",
                }
            )
            continue
        total = d.total_output_duration()
        if abs(total - scene.duration) > 0.12:
            # Auto-fix: scale last shot to absorb drift
            if d.shots:
                drift = scene.duration - (total - d.shots[-1].output_duration)
                d.shots[-1].output_duration = round(max(0.05, drift), 4)
                issues.append(
                    {
                        "scene_number": scene.scene_number,
                        "severity": "INFO",
                        "category": "coverage",
                        "message": f"Normalized shot durations to scene ({scene.duration:.2f}s)",
                        "fixed": True,
                    }
                )
        if d.strategy == "SAFE_LOOP":
            issues.append(
                {
                    "scene_number": scene.scene_number,
                    "severity": "WARN",
                    "category": "coverage",
                    "message": "SAFE_LOOP is last-resort — prefer multi-shot/punch-in",
                }
            )
        if len(d.shots) == 1 and d.shots[0].hold_tail and scene.duration >= 6.0:
            issues.append(
                {
                    "scene_number": scene.scene_number,
                    "severity": "WARN",
                    "category": "coverage",
                    "message": "Long hold_tail on extended narration — consider multi-shot",
                }
            )
        # Repetition
        if d.source_asset and recent_assets.count(d.source_asset) >= 2:
            issues.append(
                {
                    "scene_number": scene.scene_number,
                    "severity": "WARN",
                    "category": "repetition",
                    "message": "Same source asset reused heavily",
                }
            )
        if recent_strategies[-3:].count(d.strategy) >= 3 and d.strategy == "HOLD_TAIL":
            issues.append(
                {
                    "scene_number": scene.scene_number,
                    "severity": "WARN",
                    "category": "pacing",
                    "message": "Excessive HOLD_TAIL strategies in a row",
                }
            )
        recent_strategies.append(d.strategy)
        if d.source_asset:
            recent_assets.append(d.source_asset)
            if len(recent_assets) > 12:
                recent_assets = recent_assets[-12:]

        # Cut frequency vs pacing — don't collapse replay coverage for short sources
        short_source = bool(
            scene.actual_asset_duration
            and float(scene.actual_asset_duration) < float(scene.duration) * 0.88
        )
        if scene.pacing_bias == "slow" and len(d.shots) >= 4 and not short_source:
            # Auto-fix: merge to 2 shots
            if len(d.shots) > 2:
                first = d.shots[0]
                rest_dur = sum(s.output_duration for s in d.shots[1:])
                first.output_duration = round(first.output_duration + rest_dur * 0.5, 4)
                last = d.shots[-1]
                last.output_duration = round(scene.duration - first.output_duration, 4)
                d.shots = [first, last]
                d.strategy = "MULTI_SHOT"
                issues.append(
                    {
                        "scene_number": scene.scene_number,
                        "severity": "INFO",
                        "category": "pacing",
                        "message": "Reduced cut frequency for slow explanation beat",
                        "fixed": True,
                    }
                )

        for shot in d.shots:
            src_span = None
            if shot.source_end is not None:
                src_span = max(0.0, float(shot.source_end) - float(shot.source_start or 0.0))
            planned = float(shot.output_duration or 0.0)
            if planned <= 0.001:
                issues.append(
                    {
                        "scene_number": scene.scene_number,
                        "severity": "WARN",
                        "category": "coverage",
                        "message": f"zero-duration shot {shot.shot_id}",
                    }
                )
            if (
                shot.hold_tail
                and src_span is not None
                and planned > src_span + 1.25
            ):
                issues.append(
                    {
                        "scene_number": scene.scene_number,
                        "severity": "WARN",
                        "category": "coverage",
                        "status": "suspicious hold",
                        "message": (
                            f"Scene {scene.scene_number} asset: "
                            f"{Path(shot.source_path or d.source_asset or '?').name} "
                            f"source duration: {src_span:.1f}s "
                            f"planned duration: {planned:.1f}s "
                            f"strategy: {d.strategy} status: suspicious hold"
                        ),
                    }
                )
            if (
                not shot.hold_tail
                and src_span is not None
                and planned > src_span + 0.15
            ):
                issues.append(
                    {
                        "scene_number": scene.scene_number,
                        "severity": "WARN",
                        "category": "freeze_risk",
                        "message": (
                            f"{shot.shot_id} planned {planned:.2f}s from "
                            f"{src_span:.2f}s source window "
                            f"({d.strategy}, hold={shot.hold_tail})"
                        ),
                        "asset": shot.source_path or d.source_asset,
                    }
                )
    return issues


class EditorialEngine:
    """Compile post-alignment editorial decisions into a render-ready plan."""

    def __init__(self, plan: EditorialPlan) -> None:
        self.plan = plan
        self.decisions: List[EditDecision] = []
        self.timeline: Optional[EditorialTimeline] = None
        self.events: List[EditorialEvent] = []
        self.qc_issues: List[dict] = []
        self.intents: Dict[str, Any] = {}

    def compile(
        self,
        *,
        images_dir: Optional[Path] = None,
        gemini_settings: Optional[Mapping[str, Any]] = None,
        reasoner: Any = None,
        skip_ai: bool = False,
    ) -> EditorialPlan:
        media_paths = _resolve_media_paths(self.plan.scenes, images_dir)
        coverage = _coverage_by_scene(images_dir)
        candidates = _build_candidates_by_scene(
            self.plan.scenes, images_dir, media_paths, coverage
        )

        # ★ AI Editorial Director — soft intents before shot planning
        self.intents = {}
        if not skip_ai:
            try:
                from .reasoner import enrich_plan_with_editorial_ai

                self.intents = enrich_plan_with_editorial_ai(
                    self.plan,
                    candidates_by_scene=candidates,
                    settings=gemini_settings,
                    reasoner=reasoner,
                )
            except Exception:
                self.intents = {}

        self.decisions = plan_all_edit_decisions(
            self.plan.scenes,
            media_paths=media_paths,
            candidates_by_scene=candidates,
            coverage_by_scene=coverage,
            intents_by_scene=self.intents or None,
        )
        self.qc_issues = qc_edit_decisions(self.plan, self.decisions)
        self.events = plan_editorial_events(self.plan, intents=self.intents or None)
        self.timeline = build_timeline_from_decisions(
            self.plan, self.decisions, events=self.events
        )
        if self.timeline is not None:
            self.qc_issues.extend(
                validate_visual_timeline(
                    self.timeline, audio_end=float(self.plan.audio_end)
                )
            )

        # ★ Graphics + Motion Design Engine — timeline-native TEXT/GRAPHICS
        try:
            from graphics import (
                attach_graphics_plan,
                materialize_graphics_on_timeline,
                plan_graphics,
            )

            graphics_plan = plan_graphics(self.plan, intents=self.intents or None)
            if self.timeline is not None and graphics_plan.specs:
                materialize_graphics_on_timeline(self.timeline, graphics_plan)
            attach_graphics_plan(self.plan, graphics_plan)
            if graphics_plan.qc_issues:
                self.qc_issues.extend(graphics_plan.qc_issues)
        except Exception:
            # Graphics are additive — never block editorial compile.
            pass

        attach_editorial_compile(
            self.plan,
            decisions=self.decisions,
            timeline=self.timeline,
            events=self.events,
            qc_issues=self.qc_issues,
        )
        return self.plan

    def decision_map(self) -> Dict[str, EditDecision]:
        return {str(d.scene_number): d for d in self.decisions}

    def primary_camera_map(self) -> Dict[str, str]:
        """Camera style from first shot — may refine EditorialPlan.camera_style."""
        out: Dict[str, str] = {}
        for d in self.decisions:
            if d.shots:
                out[str(d.scene_number)] = d.shots[0].camera_style
        return out


def attach_editorial_compile(
    plan: EditorialPlan,
    *,
    decisions: Sequence[EditDecision],
    timeline: Optional[EditorialTimeline],
    events: Sequence[EditorialEvent],
    qc_issues: Optional[Sequence[dict]] = None,
) -> None:
    """Store compile outputs on the plan object (and sync camera hints)."""
    setattr(plan, "edit_decisions", [d.to_dict() for d in decisions])
    if timeline is not None:
        setattr(plan, "timeline", timeline.to_dict())
    setattr(plan, "editorial_events", [e.to_dict() for e in events])
    if qc_issues is not None:
        setattr(plan, "editorial_qc", list(qc_issues))

    # Sync camera_style on scenes from first shot when present
    by_sn = {str(d.scene_number): d for d in decisions}
    for scene in plan.scenes:
        d = by_sn.get(str(scene.scene_number))
        if d and d.shots:
            scene.camera_style = d.shots[0].camera_style  # type: ignore[assignment]


def compile_editorial_plan(
    plan: EditorialPlan,
    *,
    images_dir: Optional[Path] = None,
    gemini_settings: Optional[Mapping[str, Any]] = None,
    reasoner: Any = None,
    skip_ai: bool = False,
) -> EditorialPlan:
    """Convenience: run EditorialEngine.compile on an existing plan."""
    return EditorialEngine(plan).compile(
        images_dir=images_dir,
        gemini_settings=gemini_settings,
        reasoner=reasoner,
        skip_ai=skip_ai,
    )


def edit_decisions_from_plan(plan: EditorialPlan) -> List[EditDecision]:
    raw = getattr(plan, "edit_decisions", None)
    if not isinstance(raw, list):
        return []
    out: List[EditDecision] = []
    for item in raw:
        if isinstance(item, dict):
            try:
                out.append(EditDecision.from_dict(item))
            except Exception:
                continue
    return out


def decision_map_from_plan(plan: EditorialPlan) -> Dict[str, dict]:
    """Render-facing map scene_number → edit decision dict."""
    out: Dict[str, dict] = {}
    for d in edit_decisions_from_plan(plan):
        payload = d.to_dict()
        out[str(d.scene_number)] = payload
        out[str(d.scene_number).zfill(3)] = payload
        stripped = str(d.scene_number).lstrip("0") or str(d.scene_number)
        out[stripped] = payload
    return out
