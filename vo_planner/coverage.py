"""Visual Coverage Intelligence — when visuals should change (VO-timed)."""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from .memory import VisualMemory, entry_from_unit
from .progression import (
    camera_for_stage,
    motion_for_strategy,
    plan_progression,
    shot_scale_for_stage,
)
from .quality import (
    editability_for,
    generic_risk_score,
    location_from_text,
    meaningful_action_from_text,
    quality_requirements,
    specificity_score,
    subject_from_text,
)
from .schema import (
    AlignedBeat,
    CoverageContract,
    CoverageUnit,
)

# Soft comfort bounds — not arbitrary "cut every X seconds".
_MIN_UNIT = 1.35
_MAX_COMFORT_HOLD = 7.5
_LONG_BEAT = 5.5
_VERY_LONG = 9.0
_MAX_UNITS = 4


def _unit_count_for_beat(beat: AlignedBeat) -> Tuple[int, str]:
    """Decide how many coverage units a beat needs from VO-timed signals."""
    dur = beat.duration
    narr_imp = beat.narrative_importance
    vis_opp = beat.visual_opportunity
    density = beat.speech_density
    ideas = max(1, int(beat.idea_count or 1))
    tags = set(beat.opportunity_tags or [])
    pauses = [p for p in (beat.internal_pauses or []) if beat.start + 0.9 < p < beat.end - 0.9]

    # Short / simple → avoid over-cutting
    if dur <= 2.4:
        return 1, "single_shot"
    if dur <= 5.0 and ideas <= 1 and vis_opp < 0.7 and "reveal" not in tags:
        if density < 1.4 and dur >= 3.5:
            return 1, "hold"
        return 1, "single_shot"

    # Reveal / high-value → stronger treatment
    if "reveal" in tags and dur >= 3.8:
        return (2 if dur < 8.0 else 3), "multi_shot"
    if tags & {"dramatic_action", "statistic", "unusual_scale"} and dur >= 5.0:
        n = 2 if dur < 10.0 else 3
        return n, "multi_shot"

    # Pause-anchored opportunities (natural change points)
    if pauses and dur >= 5.0:
        n = min(_MAX_UNITS, max(2, len(pauses) + 1, ideas))
        if density < 1.5 and vis_opp < 0.5:
            n = min(n, 2)
        return n, "multi_shot"

    if dur <= _LONG_BEAT:
        if vis_opp >= 0.72 and narr_imp >= 0.65 and dur >= 4.0:
            return 2, "multi_shot"
        if density < 1.4 and dur >= 3.5:
            return 1, "hold"
        return 1, "single_shot"

    # Long beat: ideas + opportunity, not fixed chop rate
    if ideas >= 3 and dur >= 10.0:
        return min(_MAX_UNITS, max(3, ideas)), "multi_shot"
    if ideas >= 2 and dur >= 8.0:
        return min(_MAX_UNITS, max(2, ideas)), "multi_shot"
    if vis_opp >= 0.7 or narr_imp >= 0.75:
        if dur >= _VERY_LONG:
            return 3, "multi_shot"
        return 2, "multi_shot"
    if dur >= _VERY_LONG and vis_opp >= 0.45:
        return 2, "multi_shot"
    if density < 1.6 and vis_opp < 0.55:
        return 1, "hold" if dur <= _MAX_COMFORT_HOLD else "image_motion"
    if dur > _MAX_COMFORT_HOLD:
        # Dense long speech: enough changes to avoid staleness, not chaos
        if density >= 3.2:
            return 2, "multi_shot"
        return 2, "punch_in"
    return 1, "single_shot"


def _split_durations(total: float, n: int, *, front_weight: float = 1.15) -> List[float]:
    n = max(1, n)
    if n == 1:
        return [round(total, 3)]
    weights = [front_weight] + [1.0] * (n - 1)
    if n >= 3:
        weights[-1] = 0.92
    s = sum(weights)
    parts = [max(_MIN_UNIT, total * (w / s)) for w in weights]
    drift = total - sum(parts)
    parts[-1] = max(_MIN_UNIT, parts[-1] + drift)
    if sum(parts) > total + 0.02:
        eq = total / n
        return [round(eq, 3)] * n
    return [round(p, 3) for p in parts]


def _split_at_pauses(beat: AlignedBeat, n: int) -> List[float]:
    """Prefer pause-anchored boundaries; fall back to weighted durations."""
    if n <= 1:
        return [round(beat.duration, 3)]
    pauses = sorted(
        p for p in (beat.internal_pauses or [])
        if beat.start + _MIN_UNIT <= p <= beat.end - _MIN_UNIT
    )
    if not pauses:
        return _split_durations(beat.duration, n)

    if len(pauses) <= n - 1:
        cuts = list(pauses)
    else:
        step = len(pauses) / float(n - 1)
        raw = [pauses[min(len(pauses) - 1, int(i * step))] for i in range(n - 1)]
        seen = set()
        cuts = []
        for c in raw:
            key = round(c, 2)
            if key not in seen:
                seen.add(key)
                cuts.append(c)

    bounds = [beat.start] + cuts + [beat.end]
    durs = [round(max(0.05, bounds[i + 1] - bounds[i]), 3) for i in range(len(bounds) - 1)]

    while len(durs) > 1 and min(durs) < _MIN_UNIT:
        i = durs.index(min(durs))
        if i == 0:
            durs[1] = round(durs[0] + durs[1], 3)
            durs.pop(0)
        else:
            durs[i - 1] = round(durs[i - 1] + durs[i], 3)
            durs.pop(i)

    while len(durs) < n:
        i = durs.index(max(durs))
        if durs[i] < _MIN_UNIT * 2.05:
            break
        half = round(durs[i] / 2.0, 3)
        durs[i] = half
        durs.insert(i + 1, half)

    while len(durs) > n:
        i = durs.index(min(durs))
        if i == len(durs) - 1:
            durs[i - 1] = round(durs[i - 1] + durs[i], 3)
            durs.pop(i)
        else:
            durs[i] = round(durs[i] + durs[i + 1], 3)
            durs.pop(i + 1)

    drift = beat.duration - sum(durs)
    durs[-1] = round(max(_MIN_UNIT * 0.8, durs[-1] + drift), 3)
    return durs


def _evidence_for_stage(stage: str, tags: Sequence[str]) -> str:
    if "historical_evidence" in tags:
        return "archive"
    if "statistic" in tags:
        return "data"
    if "reveal" in tags:
        return "reveal"
    return {
        "environment": "establishing",
        "scale": "establishing",
        "object": "object",
        "person": "person",
        "action": "process",
        "mechanism": "process",
        "consequence": "consequence",
        "reveal": "reveal",
    }.get(stage, "documentary")


def _purpose_for_unit(stage: str, unit_index: int, strategy: str, tags: Sequence[str]) -> str:
    if strategy == "transition":
        return "bridge"
    if unit_index == 0:
        if "reveal" in tags:
            return "setup_for_reveal"
        return {
            "environment": "establish_world",
            "scale": "show_scale",
            "object": "feature_object",
            "person": "introduce_person",
            "action": "show_action",
            "mechanism": "explain_mechanism",
            "consequence": "show_consequence",
            "reveal": "deliver_reveal",
        }.get(stage, "support_narration")
    if "reveal" in tags:
        return "deliver_reveal"
    if unit_index == 1:
        return "deepen_or_contrast"
    return "punctuate_or_reveal"


def _change_trigger(beat: AlignedBeat, unit_index: int, strategy: str, at_time: float) -> str:
    if unit_index == 0:
        if beat.pause_before >= 0.45:
            return "post_pause_entry"
        return "beat_start"
    # Did we cut near an internal pause?
    for p in beat.internal_pauses or []:
        if abs(p - at_time) <= 0.35:
            return "mid_pause_shift"
    if strategy == "punch_in":
        return "attention_renewal"
    if beat.visual_opportunity >= 0.7:
        return "opportunity_peak"
    if "reveal" in (beat.opportunity_tags or []):
        return "reveal_beat"
    return "semantic_advance"


def _quality_label(vis_imp: float, strong: bool, gen_risk: float, tags: Sequence[str]) -> str:
    if "reveal" in tags or strong or vis_imp >= 0.8:
        return "must_be_specific_evidence"
    if vis_imp >= 0.65:
        return "prefer_specific_over_decorative"
    if gen_risk >= 0.65:
        return "reject_generic_stock"
    return "clear_readable_subject"


def plan_coverage(
    beats: Sequence[AlignedBeat],
    *,
    on_progress: Optional[Callable[[str, Optional[float]], None]] = None,
) -> Tuple[List[CoverageUnit], List[CoverageContract], VisualMemory, List[str]]:
    stages = plan_progression(beats)
    memory = VisualMemory()
    units: List[CoverageUnit] = []
    contracts: List[CoverageContract] = []
    prev_scale: Optional[str] = None
    prev_camera: Optional[str] = None
    prev_motion: Optional[str] = None
    prev_subject = ""
    prev_purpose = ""
    total = max(1, len(beats))

    for i, beat in enumerate(beats):
        if on_progress and (i == 0 or i + 1 == total or (i + 1) % 25 == 0):
            on_progress(
                f"Coverage {i + 1}/{total}…",
                0.7 + 0.12 * ((i + 1) / total),
            )
        stage = stages[i] if i < len(stages) else "environment"
        tags = list(beat.opportunity_tags or [])
        n_units, strategy = _unit_count_for_beat(beat)

        # Critical narration with strong opportunity → prefer multi coverage
        if beat.narrative_importance >= 0.8 and beat.visual_opportunity >= 0.65 and beat.duration >= 4.2:
            n_units = max(n_units, 2)
            if strategy in ("single_shot", "hold"):
                strategy = "multi_shot"
        # Weak / simple narration → avoid over-cutting
        if beat.narrative_importance <= 0.35 and beat.visual_opportunity <= 0.4 and beat.idea_count <= 1:
            n_units = 1
            strategy = "single_shot" if beat.duration < 6.0 else "hold"
        # Dense but not chaotic
        if beat.speech_density >= 3.5 and beat.duration >= 8.0:
            n_units = max(n_units, 2)
            n_units = min(n_units, 3)
        # Low density → allow holds
        if beat.speech_density < 1.5 and beat.visual_opportunity < 0.55 and beat.duration <= _MAX_COMFORT_HOLD:
            if "reveal" not in tags and beat.idea_count <= 1:
                n_units = 1
                strategy = "hold" if beat.duration >= 3.5 else "single_shot"

        durs = _split_at_pauses(beat, n_units)
        n_units = len(durs)
        if any(d < _MIN_UNIT for d in durs) and n_units > 1:
            n_units = 1
            durs = [round(beat.duration, 3)]
            strategy = "single_shot" if beat.duration <= _MAX_COMFORT_HOLD else "hold"

        subject = subject_from_text(beat.visual_goal, beat.visual_description, beat.narration)
        location = location_from_text(beat.visual_goal, beat.visual_description, beat.narration)
        action = meaningful_action_from_text(beat.narration, beat.visual_goal, beat.visual_description)
        unit_purposes: List[str] = []
        triggers: List[str] = []
        avoid = memory.avoid_list()
        t = beat.start
        beat_units: List[CoverageUnit] = []

        for ui, dur in enumerate(durs):
            u_strategy = strategy
            if n_units == 1 and strategy == "multi_shot":
                u_strategy = "single_shot"
            elif n_units > 1 and ui > 0 and strategy == "punch_in":
                u_strategy = "punch_in"
            elif n_units > 1 and ui == 0:
                u_strategy = "single_shot" if strategy != "image_motion" else "image_motion"
            elif n_units > 1 and ui == n_units - 1 and "reveal" in tags:
                u_strategy = "punch_in" if strategy != "image_motion" else "image_motion"

            unit_stage = stage if ui == 0 else _advance_within_beat(stage, ui)
            scale = shot_scale_for_stage(unit_stage, unit_index=ui, prev_scale=prev_scale)
            camera = camera_for_stage(unit_stage, prev_camera=prev_camera)
            motion = motion_for_strategy(u_strategy, unit_stage, prev_motion=prev_motion)
            purpose = _purpose_for_unit(unit_stage, ui, u_strategy, tags)
            evidence = _evidence_for_stage(unit_stage, tags)
            trigger = _change_trigger(beat, ui, u_strategy, at_time=t)

            sem_rep = memory.semantic_repetition(subject, beat.visual_goal, purpose)
            vis_rep = memory.visual_repetition(
                scale, camera, motion, unit_stage, strategy=u_strategy
            )
            purpose_changed = bool(prev_purpose and purpose != prev_purpose)
            callback = False
            if sem_rep >= 0.55 and memory.intentional_callback_ok(
                subject,
                narrative_importance=beat.narrative_importance,
                purpose_changed=purpose_changed,
            ):
                callback = True
                sem_rep = max(0.0, sem_rep - 0.35)

            # Repeated subject/look → evolve grammar (unless intentional callback keeps motif lightly)
            if sem_rep >= 0.5 or vis_rep >= 0.45:
                scale, camera, motion, evolved_strat = memory.evolve_grammar(
                    scale, camera, motion, strategy=u_strategy, force=not callback
                )
                if evolved_strat:
                    u_strategy = evolved_strat
                vis_rep = memory.visual_repetition(
                    scale, camera, motion, unit_stage, strategy=u_strategy
                )

            specificity = specificity_score(beat.visual_description, subject)
            gen_risk = generic_risk_score(None, subject, beat.visual_description)
            novelty = round(max(0.05, 1.0 - max(sem_rep, vis_rep)), 3)
            vis_imp = round(
                min(1.0, 0.45 * beat.narrative_importance + 0.55 * beat.visual_opportunity),
                3,
            )
            if "reveal" in tags:
                vis_imp = min(1.0, vis_imp + 0.08)
            strong = (
                beat.visual_opportunity >= 0.68 and specificity >= 0.5 and gen_risk <= 0.55
            ) or ("reveal" in tags and beat.visual_opportunity >= 0.55)

            quality = _quality_label(vis_imp, strong, gen_risk, tags)
            editability = editability_for(u_strategy, motion, tags)
            req = quality_requirements(
                subject=subject,
                action=action,
                evidence=evidence,
                motion=motion,
                specificity=specificity,
                generic_risk=gen_risk,
                repetition_risk=max(sem_rep, vis_rep),
                strong=strong,
                tags=tags,
                editability=editability,
            )

            prev_rel = "new_open" if not memory.entries else (
                "callback" if callback else (
                    "contrast" if subject != prev_subject else "continue_motif_evolved"
                )
            )
            unit_id = f"b{beat.beat_id}_u{ui}"
            unit = CoverageUnit(
                unit_id=unit_id,
                beat_id=beat.beat_id,
                start=round(t, 3),
                end=round(t + dur, 3),
                strategy=u_strategy,
                visual_purpose=purpose,
                evidence_type=evidence,
                subject=subject,
                shot_scale=scale,
                camera=camera,
                motion=motion,
                specificity=specificity,
                visual_importance=vis_imp,
                novelty=novelty,
                repetition_risk=round(max(sem_rep, vis_rep), 3),
                generic_risk=gen_risk,
                strong_opportunity=strong,
                quality_target=quality,
                change_trigger=trigger,
                previous_relationship=prev_rel,
                next_relationship="",
                avoid=list(avoid),
                progression_stage=unit_stage,
                intentional_callback=callback,
                opportunity_tags=list(tags),
                quality_requirements=req,
                location=location,
                meaningful_action=action,
                editability=editability,
            )
            beat_units.append(unit)
            unit_purposes.append(purpose)
            triggers.append(trigger)
            memory.remember(
                entry_from_unit(unit, location=location, concept=beat.visual_goal),
                strategy=u_strategy,
            )
            prev_scale, prev_camera, prev_motion = scale, camera, motion
            prev_subject = subject
            prev_purpose = purpose
            t += dur

        for ui, unit in enumerate(beat_units):
            if ui + 1 < len(beat_units):
                nxt = beat_units[ui + 1]
                unit.next_relationship = f"{nxt.strategy}:{nxt.shot_scale}"
            elif i + 1 < len(beats):
                unit.next_relationship = f"next_beat:{beats[i + 1].beat_id}"
            else:
                unit.next_relationship = "video_end"

        units.extend(beat_units)
        contracts.append(
            CoverageContract(
                beat_id=beat.beat_id,
                total_duration=round(beat.duration, 3),
                required_units=len(beat_units),
                unit_durations=[u.duration for u in beat_units],
                unit_purposes=unit_purposes,
                change_triggers=triggers,
                previous_visual_relationship=beat_units[0].previous_relationship if beat_units else "",
                next_visual_relationship=beat_units[-1].next_relationship if beat_units else "",
                avoid=list(avoid),
                strategy=strategy,
            )
        )

    return units, contracts, memory, stages


def _advance_within_beat(stage: str, unit_index: int) -> str:
    from .schema import PROGRESSION_STAGES

    if stage not in PROGRESSION_STAGES:
        return stage
    idx = PROGRESSION_STAGES.index(stage)
    return PROGRESSION_STAGES[min(len(PROGRESSION_STAGES) - 1, idx + min(unit_index, 2))]
