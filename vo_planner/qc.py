"""Gap / staleness QC for VO-aware visual plans."""

from __future__ import annotations

from typing import List, Sequence

from .schema import AlignedBeat, CoverageUnit, QCIssue


def validate_plan(
    beats: Sequence[AlignedBeat],
    units: Sequence[CoverageUnit],
    *,
    audio_duration: float,
) -> List[QCIssue]:
    issues: List[QCIssue] = []
    if not beats:
        issues.append(QCIssue("no_beats", "error", "No semantic beats to cover"))
        return issues
    if not units:
        issues.append(QCIssue("no_units", "error", "No coverage units produced"))
        return issues

    # Coverage gaps / overlaps across units
    ordered = sorted(units, key=lambda u: (u.start, u.end, u.unit_id))
    if ordered[0].start > 0.2:
        issues.append(
            QCIssue(
                "leading_gap",
                "warning",
                f"Coverage starts at {ordered[0].start:.2f}s — leading gap",
                unit_id=ordered[0].unit_id,
            )
        )
    cursor = ordered[0].start
    for i, unit in enumerate(ordered):
        if unit.start > cursor + 0.15:
            issues.append(
                QCIssue(
                    "coverage_gap",
                    "error",
                    f"Unexplained gap {cursor:.2f}–{unit.start:.2f}s",
                    beat_id=unit.beat_id,
                    unit_id=unit.unit_id,
                )
            )
        if unit.start < cursor - 0.12 and i > 0:
            issues.append(
                QCIssue(
                    "coverage_overlap",
                    "warning",
                    f"Overlap near {unit.start:.2f}s",
                    beat_id=unit.beat_id,
                    unit_id=unit.unit_id,
                )
            )
        cursor = max(cursor, unit.end)
        if unit.duration < 0.9:
            issues.append(
                QCIssue(
                    "micro_unit",
                    "warning",
                    f"Very short unit ({unit.duration:.2f}s)",
                    beat_id=unit.beat_id,
                    unit_id=unit.unit_id,
                )
            )
        if unit.strategy == "hold" and unit.duration > 8.5:
            issues.append(
                QCIssue(
                    "excessive_hold",
                    "warning",
                    f"Hold lasts {unit.duration:.1f}s — risk of staleness",
                    beat_id=unit.beat_id,
                    unit_id=unit.unit_id,
                )
            )

    if audio_duration and cursor + 0.35 < audio_duration:
        issues.append(
            QCIssue(
                "trailing_gap",
                "error",
                f"Coverage ends at {cursor:.2f}s but VO runs to {audio_duration:.2f}s",
            )
        )

    # Excessive cuts: many sub-2s units in a row
    short_run = 0
    for unit in ordered:
        if unit.duration < 2.0 and unit.strategy in ("multi_shot", "punch_in", "single_shot"):
            short_run += 1
            if short_run >= 4:
                issues.append(
                    QCIssue(
                        "excessive_cuts",
                        "warning",
                        "Four+ consecutive short cuts — may feel frantic",
                        beat_id=unit.beat_id,
                        unit_id=unit.unit_id,
                    )
                )
                short_run = 0
        else:
            short_run = 0

    # Repetition / weak support / generic risk
    for unit in units:
        if unit.repetition_risk >= 0.7 and not unit.intentional_callback:
            issues.append(
                QCIssue(
                    "repetitive_visual",
                    "warning",
                    f"High repetition risk for '{unit.subject}'",
                    beat_id=unit.beat_id,
                    unit_id=unit.unit_id,
                )
            )
        if unit.generic_risk >= 0.65:
            issues.append(
                QCIssue(
                    "generic_visual_risk",
                    "warning",
                    f"Generic-stock risk high for '{unit.subject}'",
                    beat_id=unit.beat_id,
                    unit_id=unit.unit_id,
                )
            )
        if unit.generic_risk >= 0.7 and unit.visual_importance >= 0.55:
            issues.append(
                QCIssue(
                    "weak_visual_support",
                    "warning",
                    "Important moment has high generic-risk coverage",
                    beat_id=unit.beat_id,
                    unit_id=unit.unit_id,
                )
            )

    units_by_beat = {}
    for u in units:
        units_by_beat.setdefault(u.beat_id, []).append(u)

    for beat in beats:
        beat_units = units_by_beat.get(beat.beat_id) or []
        n = len(beat_units)
        if beat.narrative_importance >= 0.75 and beat.visual_opportunity >= 0.65 and n < 2 and beat.duration >= 5.0:
            issues.append(
                QCIssue(
                    "under_covered_important",
                    "warning",
                    "High-importance / high-opportunity narration may need richer coverage",
                    beat_id=beat.beat_id,
                )
            )
        if beat.narrative_importance <= 0.35 and beat.visual_opportunity <= 0.4 and n >= 3:
            issues.append(
                QCIssue(
                    "over_covered_simple",
                    "warning",
                    "Simple narration has many coverage units",
                    beat_id=beat.beat_id,
                )
            )
        if beat.duration <= 5.0 and beat.idea_count <= 1 and n >= 3:
            issues.append(
                QCIssue(
                    "over_cut_simple",
                    "warning",
                    "Short simple beat was over-cut",
                    beat_id=beat.beat_id,
                )
            )

    return issues
