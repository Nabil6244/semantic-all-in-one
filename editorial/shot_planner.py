"""Coverage / Shot Planner — narration duration → edit decisions.

Ranked strategies (least damaging first):
  1. SINGLE_SHOT when asset covers narration
  2. DUAL_ASSET — complementary real B-roll (preferred over transforming primary)
  3. MULTI_SHOT / additional section of primary
  4. REFRAME / PUNCH_IN on primary
  5. IMAGE_MOTION (Ken Burns) for stills
  6. RETIME (subtle speed)
  7. SAFE_LOOP only when loopability is high
  8. HOLD_TAIL (freeze) as last resort for small gaps

Ask first: is there a better real shot available before manipulating this one?
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .complements import (
    AssetCandidate,
    editorial_purpose_for_role,
    needs_complementary_coverage,
    select_complements,
)
from .continuity import (
    ContinuityTracker,
    attention_state_for_scene,
    camera_for_shot,
    reveal_phase_for_scene,
    scale_for_shot_size,
    shot_size_sequence,
    source_identity_key,
    visual_role_for_scene,
)
from .edit_decision import EditDecision, MediaEditability, ShotSpec
from .intent import CONF_MEDIUM, EditorialIntent
from .media_analysis import analyze_media_editability
from .schema import EditorialScene

# Minimum meaningful shot length (seconds)
_MIN_SHOT = 1.15
_MAX_SHOTS = 4


def _split_durations(total: float, n: int) -> List[float]:
    n = max(1, n)
    weights = [1.15] + [1.0] * (n - 1)
    if n >= 3:
        weights[-1] = 0.9
    s = sum(weights)
    parts = [max(_MIN_SHOT, total * (w / s)) for w in weights]
    drift = total - sum(parts)
    parts[-1] = max(_MIN_SHOT, parts[-1] + drift)
    if sum(parts) > total + 0.01 or any(p > total for p in parts):
        eq = total / n
        return [eq] * n
    return parts


def _n_shots_core(required: float, usable: float, role: str, pacing: str) -> int:
    # Stills (usable <= 0): one strong hold is the default. Multi-shot on the
    # *same* image (crop/zoom) is last-resort for long narration only.
    if usable <= 0:
        if required < 8.0:
            return 1
        if required < 12.0:
            return 2 if pacing == "fast" else 1
        return 3 if pacing == "fast" else 2
    ratio = usable / required if required > 0 else 1.0
    if ratio >= 0.88:
        return 1
    # Replay with punch-in / reframe rather than freeze the tail.
    n_replay = int(math.ceil(required / max(usable, _MIN_SHOT)))
    n_replay = min(_MAX_SHOTS, max(2, n_replay))
    if role in ("process", "scale", "reveal", "cause_effect") and required >= 8.0:
        n_replay = min(_MAX_SHOTS, max(n_replay, 3 if required >= 10.0 else 2))
    if required >= 8.0 and ratio < 0.65:
        n_replay = min(_MAX_SHOTS, max(n_replay, 3))
    return n_replay


def _n_shots_for_gap(
    required: float,
    usable: float,
    role: str,
    pacing: str,
    *,
    intent: Optional[EditorialIntent] = None,
) -> int:
    # Short VO beats: never invent multi-shot coverage.
    if required <= 2.5:
        return 1
    if intent and intent.confidence >= CONF_MEDIUM:
        if intent.prefer_single() and required < 10.0 and (
            usable <= 0 or usable >= required * 0.88
        ):
            return 1
        if intent.pacing == "fast" and required >= 6.0 and usable > 0 and usable < required * 0.88:
            return min(_MAX_SHOTS, max(2, _n_shots_core(required, usable, role, "fast")))
        if intent.pacing in ("hold", "reflective") and required < 12.0:
            if usable >= required * 0.88 or usable <= 0:
                return 1
            return min(_MAX_SHOTS, max(2, _n_shots_core(required, usable, role, "slow")))
        # prefer_multi only when primary cannot cover — do not chop a strong hold.
        if intent.prefer_multi() and required >= 7.0 and usable > 0 and usable < required * 0.88:
            return min(_MAX_SHOTS, max(2, _n_shots_core(required, usable, role, pacing)))
        if intent.prefer_multi() and usable <= 0 and required >= 10.0:
            return min(_MAX_SHOTS, max(2, _n_shots_core(required, usable, role, pacing)))
    return _n_shots_core(required, usable, role, pacing)


def _bind_source(shot: ShotSpec, cand: AssetCandidate) -> ShotSpec:
    shot.asset_id = cand.asset_id
    shot.source_path = str(cand.path)
    shot.visual_role = cand.visual_role or shot.visual_role
    shot.editorial_purpose = cand.editorial_purpose or shot.editorial_purpose
    return shot


def _single_shot_decision(
    *,
    scene: EditorialScene,
    required: float,
    role: str,
    usable: float,
    tracker: ContinuityTracker,
    primary: AssetCandidate,
) -> EditDecision:
    size = shot_size_sequence(role, 1, prev_size=tracker.prev_shot_size)[0]
    cam = camera_for_shot(
        size,
        purpose=scene.purpose,
        index=0,
        prev_camera=tracker.prev_camera,
        recent_cameras=tracker.recent_cameras,
        prefer_static=scene.purpose in ("evidence",) or role in ("claim_evidence", "historical"),
    )
    shot = ShotSpec(
        shot_id=f"{scene.scene_number}_s0",
        output_duration=round(required, 4),
        source_start=0.0,
        source_end=round(min(usable, required * 1.05), 3) if usable > 0 else None,
        scale=scale_for_shot_size(size),
        shot_size=size,  # type: ignore[arg-type]
        camera_style=cam,
        reason="source covers beat",
        visual_role=role,
        editorial_purpose=editorial_purpose_for_role(role),
    )
    _bind_source(shot, primary)
    return EditDecision(
        scene_number=str(scene.scene_number),
        required_duration=round(required, 4),
        strategy="SINGLE_SHOT",
        shots=[shot],
        source_asset=primary.label,
        visual_role=role,  # type: ignore[arg-type]
        confidence=0.9,
        reason=_reason("SINGLE_SHOT", usable, required, 1),
        avoid_blind_loop=False,
        attention_state=attention_state_for_scene(scene, 0, 1),
        reveal_phase=reveal_phase_for_scene(scene),
    )


def _dual_asset_decision(
    *,
    scene: EditorialScene,
    required: float,
    role: str,
    primary: AssetCandidate,
    primary_usable: float,
    complements: Sequence[AssetCandidate],
    tracker: ContinuityTracker,
) -> EditDecision:
    """Build A→B(→C) using real complementary files when they improve the beat.

    Primary keeps as much of its usable window as the beat allows. Complements
    cover the remainder — never chop a strong primary down to ~45% just because
    another coverage unit exists.
    """
    # Shot count: primary + up to N complements, capped
    n_comp = min(len(complements), 3)
    # Leave a meaningful floor for each complement, but let primary breathe.
    min_comp_room = _MIN_SHOT * n_comp
    if primary_usable > 0:
        # Use the full honest primary window; only trim to leave complement room.
        primary_share = min(primary_usable, required - min_comp_room)
        primary_share = max(_MIN_SHOT, primary_share)
    else:
        # Still primary — majority establish, then complementary cut when justified.
        primary_share = min(max(_MIN_SHOT, required * 0.62), required - min_comp_room)

    remaining = max(_MIN_SHOT, required - primary_share)
    n_shots = 1 + n_comp
    sizes = shot_size_sequence(role, n_shots, prev_size=tracker.prev_shot_size)
    comp_durs = _split_durations(remaining, n_comp) if n_comp else []

    shots: List[ShotSpec] = []
    # Shot 0 — primary (context)
    cam0 = camera_for_shot(
        sizes[0],
        purpose=scene.purpose,
        index=0,
        prev_camera=tracker.prev_camera,
        recent_cameras=tracker.recent_cameras,
        prefer_static=scene.purpose in ("evidence",) or role in ("claim_evidence", "historical"),
    )
    s0 = ShotSpec(
        shot_id=f"{scene.scene_number}_s0",
        output_duration=round(primary_share, 4),
        source_start=0.0,
        source_end=round(min(primary_usable, primary_share * 1.05), 3)
        if primary_usable > 0
        else None,
        scale=1.0 if sizes[0] in ("wide", "extreme_wide") else scale_for_shot_size(sizes[0]),
        shot_size=sizes[0],  # type: ignore[arg-type]
        camera_style=cam0,
        transition_in="cut",
        reason="primary establish",
        visual_role=primary.visual_role or role,
        editorial_purpose=primary.editorial_purpose or "context",
    )
    _bind_source(s0, primary)
    shots.append(s0)

    for i, (cand, dur, size) in enumerate(
        zip(complements[:n_comp], comp_durs, sizes[1:])
    ):
        cam = camera_for_shot(
            size,
            purpose=scene.purpose,
            index=i + 1,
            prev_camera=shots[-1].camera_style,
            recent_cameras=list(tracker.recent_cameras) + [s.camera_style for s in shots],
            prefer_static=cand.visual_role in ("evidence", "claim_evidence"),
        )
        # Mild punch only when complement is still + same framing risk
        scale = scale_for_shot_size(size) if cand.visual_role in ("detail", "object") else 1.0
        if scale < 1.08 and size in ("close", "extreme_close", "detail"):
            scale = scale_for_shot_size(size)
        edit = analyze_media_editability(cand.path, asset_type=cand.asset_class)
        src_end = None
        if edit.media_kind == "video" and edit.usable_duration > 0:
            src_end = round(min(edit.usable_duration, dur * 1.05), 3)
        shot = ShotSpec(
            shot_id=f"{scene.scene_number}_s{i + 1}",
            output_duration=round(dur, 4),
            source_start=0.0,
            source_end=src_end,
            scale=round(scale, 3),
            crop_x=0.5,
            crop_y=0.5,
            shot_size=size,  # type: ignore[arg-type]
            camera_style=cam if edit.media_kind == "image" else ("static" if cam == "hold" else cam),
            transition_in="cut",  # asset change → hard cut by default
            hold_tail=False,
            reason=f"complement {cand.visual_role or 'broll'}",
            visual_role=cand.visual_role,
            editorial_purpose=cand.editorial_purpose or editorial_purpose_for_role(cand.visual_role),
        )
        _bind_source(shot, cand)
        shots.append(shot)

    # Normalize exact total
    drift = required - sum(s.output_duration for s in shots)
    shots[-1].output_duration = round(max(0.05, shots[-1].output_duration + drift), 4)

    return EditDecision(
        scene_number=str(scene.scene_number),
        required_duration=round(required, 4),
        strategy="DUAL_ASSET",
        shots=shots,
        source_asset=primary.label,
        visual_role=role,  # type: ignore[arg-type]
        confidence=0.88,
        reason=(
            f"DUAL_ASSET: primary + {n_comp} complement(s) for {required:.1f}s "
            f"(roles: {' → '.join(s.editorial_purpose or s.visual_role or '?' for s in shots)})"
        ),
        avoid_blind_loop=True,
        attention_state=attention_state_for_scene(scene, 0, 1),
        reveal_phase=reveal_phase_for_scene(scene),
    )


def _video_multi_shot(
    *,
    scene: EditorialScene,
    editability: MediaEditability,
    required: float,
    role: str,
    tracker: ContinuityTracker,
    primary: AssetCandidate,
    intent: Optional[EditorialIntent] = None,
) -> EditDecision:
    usable = max(editability.usable_duration, editability.native_duration)
    play = max(0.2, usable) if usable > 0 else required
    n = _n_shots_for_gap(required, usable, role, scene.pacing_bias, intent=intent)
    if usable > 0 and n * play < required - 0.05:
        n = min(_MAX_SHOTS, max(n, int(math.ceil(required / play))))
    sizes = shot_size_sequence(role, n, prev_size=tracker.prev_shot_size)
    durs = _split_durations(required, n)
    leftover_hold = False
    if usable > 0:
        capped = [min(d, play) for d in durs]
        drift = required - sum(capped)
        if drift > 0.08:
            capped[-1] = round(capped[-1] + drift, 4)
            leftover_hold = capped[-1] > play + 0.08
        else:
            capped[-1] = round(capped[-1] + drift, 4)
        durs = capped
    shots: List[ShotSpec] = []
    src_cursor = 0.0
    window = usable if usable > 0 else required

    for i, (dur, size) in enumerate(zip(durs, sizes)):
        scale = scale_for_shot_size(size)
        cam = camera_for_shot(
            size,
            purpose=scene.purpose,
            index=i,
            prev_camera=tracker.prev_camera if i == 0 else shots[-1].camera_style,
            recent_cameras=list(tracker.recent_cameras)
            + [s.camera_style for s in shots],
        )
        if usable <= 0:
            src_start, src_end = 0.0, None
        elif usable >= required * 0.88 and n == 1:
            src_start, src_end = 0.0, min(usable, required)
        elif n == 1 or dur <= play + 0.02:
            # Replay the usable window (punch-in / reframe provides the cut).
            offset = min(0.12 * i, max(0.0, usable - min(dur, play)))
            src_start = round(offset, 3)
            src_end = round(min(usable, src_start + min(dur, play)), 3)
        elif usable >= sum(durs[: i + 1]) * 0.85:
            src_start = src_cursor
            src_end = min(usable, src_cursor + dur)
            src_cursor = src_end
            if src_end - src_start < 0.4 and usable > 0.5:
                src_start = max(0.0, usable - min(dur, play))
                src_end = usable
        else:
            src_start = 0.0
            src_end = min(usable, play)

        speed = 1.0
        hold = bool(leftover_hold and i == n - 1 and dur > play + 0.08)
        if hold:
            src_start = 0.0
            src_end = round(usable, 3) if usable > 0 else None

        shot = ShotSpec(
            shot_id=f"{scene.scene_number}_s{i}",
            output_duration=round(dur, 4),
            source_start=round(src_start, 3),
            source_end=round(src_end, 3) if src_end else None,
            scale=round(scale, 3),
            crop_x=0.5 + (0.06 if i % 2 else -0.04) * (1 if scale > 1.05 else 0),
            crop_y=0.48 + (0.03 if i % 2 else -0.02) * (1 if scale > 1.05 else 0),
            speed=round(speed, 3),
            shot_size=size,  # type: ignore[arg-type]
            camera_style=cam,
            transition_in="cut",
            hold_tail=hold,
            reason=f"{size} coverage from primary",
            visual_role=role,
            editorial_purpose=editorial_purpose_for_role(role),
        )
        _bind_source(shot, primary)
        shots.append(shot)

    strategy = "SINGLE_SHOT"
    if n > 1:
        strategy = "MULTI_SHOT"
        if any(s.scale >= 1.25 for s in shots):
            strategy = "PUNCH_IN"
        elif all(s.scale <= 1.05 for s in shots) and usable < required * 0.72:
            strategy = "MONTAGE"
    elif shots and shots[0].hold_tail:
        strategy = "HOLD_TAIL"
    elif shots and shots[0].speed != 1.0:
        strategy = "RETIME"
    elif shots and shots[0].scale > 1.05:
        strategy = "REFRAME"

    conf = 0.82 if strategy in ("SINGLE_SHOT", "MULTI_SHOT", "PUNCH_IN") else 0.65
    if strategy == "HOLD_TAIL":
        conf = 0.55

    return EditDecision(
        scene_number=str(scene.scene_number),
        required_duration=round(required, 4),
        strategy=strategy,  # type: ignore[arg-type]
        shots=shots,
        source_asset=primary.label,
        visual_role=role,  # type: ignore[arg-type]
        confidence=conf,
        reason=_reason(strategy, usable, required, n),
        avoid_blind_loop=strategy != "SAFE_LOOP",
        attention_state=attention_state_for_scene(scene, 0, 1),
        reveal_phase=reveal_phase_for_scene(scene),
    )


def _image_coverage(
    *,
    scene: EditorialScene,
    required: float,
    role: str,
    tracker: ContinuityTracker,
    primary: AssetCandidate,
    intent: Optional[EditorialIntent] = None,
) -> EditDecision:
    """Cover narration with a still — prefer one breathing hold over crop cuts."""
    n = _n_shots_for_gap(required, 0.0, role, scene.pacing_bias, intent=intent)
    sizes = shot_size_sequence(role, n, prev_size=tracker.prev_shot_size)
    durs = _split_durations(required, n)
    prefer_static = scene.purpose in ("evidence",) or role in (
        "claim_evidence",
        "historical",
        "statistic",
    )
    blob = f"{scene.narration_excerpt} {scene.visual_description}".lower()
    if any(w in blob for w in ("document", "archive", "photograph", "evidence", "report")):
        prefer_static = True
    shots: List[ShotSpec] = []
    for i, (dur, size) in enumerate(zip(durs, sizes)):
        cam = camera_for_shot(
            size,
            purpose=scene.purpose,
            index=i,
            prev_camera=tracker.prev_camera if i == 0 else shots[-1].camera_style,
            recent_cameras=list(tracker.recent_cameras)
            + [s.camera_style for s in shots],
            prefer_static=prefer_static and i == 0,
        )
        # Single hold: keep framing stable (no fake "new shot" via crop).
        # Multi-shot on same still is rare (long VO) — then mild reframe is OK.
        if n == 1:
            scale = 1.0 if size in ("wide", "extreme_wide", "medium") else scale_for_shot_size(size)
            if prefer_static:
                scale = 1.0
            crop_x, crop_y = 0.5, 0.5
            reason = f"image hold {size}" if cam in ("static", "hold") else f"image {cam} {size}"
        else:
            scale = round(scale_for_shot_size(size), 3)
            crop_x = 0.5 + (0.04 if i % 2 else -0.03)
            crop_y = 0.5 + (0.02 if i % 2 else -0.02)
            reason = f"image motion {size}"
        shot = ShotSpec(
            shot_id=f"{scene.scene_number}_s{i}",
            output_duration=round(dur, 4),
            source_start=0.0,
            source_end=None,
            scale=round(scale, 3),
            crop_x=crop_x,
            crop_y=crop_y,
            speed=1.0,
            shot_size=size,  # type: ignore[arg-type]
            camera_style=cam,
            transition_in="cut",
            hold_tail=False,
            reason=reason,
            visual_role=role,
            editorial_purpose=editorial_purpose_for_role(role),
        )
        _bind_source(shot, primary)
        shots.append(shot)
    strategy = "IMAGE_MOTION" if n == 1 else "MULTI_SHOT"
    return EditDecision(
        scene_number=str(scene.scene_number),
        required_duration=round(required, 4),
        strategy=strategy,  # type: ignore[arg-type]
        shots=shots,
        source_asset=primary.label,
        visual_role=role,  # type: ignore[arg-type]
        confidence=0.8,
        reason=(
            f"{strategy}: still covers {required:.1f}s"
            + (" with restrained motion" if any(s.camera_style not in ("static", "hold") for s in shots) else " (static/hold)")
        ),
        avoid_blind_loop=True,
        attention_state=attention_state_for_scene(scene, 0, 1),
        reveal_phase=reveal_phase_for_scene(scene),
    )


def _reason(strategy: str, usable: float, required: float, n: int) -> str:
    if strategy == "SINGLE_SHOT":
        return f"source ({usable:.1f}s) covers narration ({required:.1f}s)"
    if strategy == "HOLD_TAIL":
        return f"small shortfall — hold last frame ({usable:.1f}s → {required:.1f}s)"
    if strategy == "RETIME":
        return f"subtle retime to fit {required:.1f}s from {usable:.1f}s"
    if strategy == "DUAL_ASSET":
        return f"complementary assets cover {required:.1f}s"
    if strategy in ("MULTI_SHOT", "PUNCH_IN", "MONTAGE", "REFRAME"):
        return f"{n} editorial shot(s) for {required:.1f}s from {usable:.1f}s source"
    return strategy


_HOLD_TAIL_MAX_GAP = 1.2
_MAX_REPLAY_SHOTS = 6


def _shot_playable_duration(
    shot: ShotSpec,
    fallback: float,
    *,
    default_kind: str = "video",
) -> Optional[float]:
    """Max real-time playable length for this shot. None = still (Ken Burns)."""
    path = Path(shot.source_path) if shot.source_path else None
    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    video_exts = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
    if path and path.suffix.lower() in image_exts:
        return None
    if default_kind == "image" and not (path and path.suffix.lower() in video_exts):
        return None
    kind_hint = "video" if path and path.suffix.lower() in video_exts else default_kind
    edit = analyze_media_editability(
        path if path and path.is_file() else None,
        known_duration=fallback if not (path and path.is_file()) else None,
        asset_type=kind_hint or "video",
    )
    if edit.media_kind == "image":
        return None
    play = max(edit.usable_duration, edit.native_duration, 0.0)
    return play if play > 0 else (fallback if fallback > 0 else None)


def _normalize_shot_total(shots: List[ShotSpec], required: float) -> None:
    if not shots:
        return
    drift = required - sum(float(s.output_duration) for s in shots)
    shots[-1].output_duration = round(max(0.05, shots[-1].output_duration + drift), 4)


def _reconcile_playable_coverage(
    decision: EditDecision,
    *,
    primary: AssetCandidate,
    usable: float,
    required: float,
    media_kind: str,
) -> EditDecision:
    """Cap video shots to source length; replay punch-in instead of freezing.

    HOLD_TAIL remains only for a small leftover on the last shot.
    """
    shots = list(decision.shots)
    if not shots or required <= 0:
        return decision

    remainder = 0.0
    for shot in shots:
        play = _shot_playable_duration(shot, usable, default_kind=media_kind)
        if play is None:
            continue  # still — image motion covers any duration
        max_play = max(play, 0.4)
        if shot.hold_tail:
            # Keep intended tail, but the moving portion should not exceed source.
            if shot.source_end is None and max_play > 0:
                shot.source_end = round(min(max_play, float(shot.source_start or 0.0) + max_play), 3)
            continue
        if shot.output_duration > max_play + 0.08:
            remainder += shot.output_duration - max_play
            shot.output_duration = round(max_play, 4)
            start = float(shot.source_start or 0.0)
            shot.source_end = round(min(start + max_play, start + shot.output_duration + 0.05), 3)
            if shot.source_end - start + 0.02 < shot.output_duration:
                shot.source_start = 0.0
                shot.source_end = round(max_play, 3)

    if remainder > 0.08:
        while remainder > 0.08 and len(shots) < _MAX_REPLAY_SHOTS:
            prev = shots[-1]
            play = _shot_playable_duration(prev, usable, default_kind=media_kind) or usable or remainder
            if play is None:
                # Last shot is a still; let image motion absorb the rest.
                shots[-1].output_duration = round(shots[-1].output_duration + remainder, 4)
                remainder = 0.0
                break
            take = min(max(play, 0.4), remainder)
            extra = ShotSpec(
                shot_id=f"{decision.scene_number}_s{len(shots)}",
                output_duration=round(take, 4),
                source_start=0.0,
                source_end=round(min(play, take + 0.05), 3),
                scale=round(max(1.18, float(prev.scale or 1.0) * 1.08), 3),
                crop_x=0.42 if len(shots) % 2 else 0.58,
                crop_y=0.46 if len(shots) % 2 else 0.52,
                speed=1.0,
                shot_size="close" if prev.shot_size in ("wide", "medium") else "medium",
                camera_style="static",
                transition_in="cut",
                hold_tail=False,
                reason="replay punch-in covers remaining narration",
                visual_role=prev.visual_role or decision.visual_role,
                editorial_purpose=prev.editorial_purpose or "detail",
            )
            _bind_source(extra, primary)
            shots.append(extra)
            remainder -= take
        if remainder > 0.08:
            shots[-1].output_duration = round(shots[-1].output_duration + remainder, 4)
            shots[-1].hold_tail = True
            extra_note = " + hold last frame for leftover"
            shots[-1].reason = (shots[-1].reason or "").rstrip() + extra_note

    _normalize_shot_total(shots, required)
    decision.shots = shots

    if media_kind != "video":
        return decision

    if len(shots) == 1 and shots[0].hold_tail:
        decision.strategy = "HOLD_TAIL"
        decision.avoid_blind_loop = True
    elif len(shots) > 1 and decision.strategy == "SINGLE_SHOT":
        decision.strategy = "PUNCH_IN" if any(s.scale >= 1.18 for s in shots) else "MULTI_SHOT"
        decision.avoid_blind_loop = True
    elif len(shots) > 1 and any(s.scale >= 1.25 for s in shots) and decision.strategy in (
        "MULTI_SHOT",
        "SINGLE_SHOT",
    ):
        decision.strategy = "PUNCH_IN"

    return decision


def plan_edit_decision(
    scene: EditorialScene,
    *,
    media_path: Optional[Path | str] = None,
    editability: Optional[MediaEditability] = None,
    tracker: Optional[ContinuityTracker] = None,
    asset_label: str = "",
    candidates: Optional[Sequence[AssetCandidate]] = None,
    coverage_strategy: str = "",
    used_asset_ids: Optional[Sequence[str]] = None,
    recent_asset_ids: Optional[Sequence[str]] = None,
    intent: Optional[EditorialIntent] = None,
) -> EditDecision:
    """Plan coverage for one EditorialScene.

    When strong complementary candidates exist and primary coverage is thin,
    prefers DUAL_ASSET over punch-in / hold on the primary alone.

    Optional ``intent`` (AI Editorial Director) soft-biases role, shot count,
    and complement preference — never invents clip ranges.
    """
    tracker = tracker or ContinuityTracker()
    required = max(0.05, float(scene.duration))
    role = visual_role_for_scene(scene)
    if intent and intent.confidence >= CONF_MEDIUM:
        ai_role = intent.planner_visual_role()
        if ai_role:
            role = ai_role
    path = Path(media_path) if media_path else None
    label = asset_label or str(path or scene.scene_number)
    sn = str(scene.scene_number)
    primary_id = sn.zfill(3)

    if editability is None:
        known = scene.actual_asset_duration
        editability = analyze_media_editability(
            path,
            known_duration=known,
            asset_type=scene.asset_type_intent,
        )
    elif scene.actual_asset_duration and editability.native_duration <= 0:
        editability = analyze_media_editability(
            path,
            known_duration=scene.actual_asset_duration,
            asset_type=scene.asset_type_intent,
        )

    if editability.native_duration <= 0 and scene.actual_asset_duration:
        editability.native_duration = float(scene.actual_asset_duration)
        editability.usable_duration = max(0.4, float(scene.actual_asset_duration) - 0.25)

    usable = editability.usable_duration or editability.native_duration

    primary = AssetCandidate(
        asset_id=primary_id,
        path=path or Path(label),
        is_primary=True,
        asset_class=scene.asset_type_intent,
        query_hint=scene.visual_description or scene.narration_excerpt[:80],
        visual_role=role if role in ("context", "atmosphere") else "context",
        editorial_purpose="context",
        metadata={"actual_duration": scene.actual_asset_duration},
    )
    if role:
        primary.visual_role = "context" if role in ("process", "scale", "reveal") else role
        primary.editorial_purpose = editorial_purpose_for_role(primary.visual_role)

    prefer_dual = bool(
        intent
        and intent.confidence >= CONF_MEDIUM
        and intent.prefer_dual()
        and not intent.prefer_single()
    )
    prefs = list(intent.preferred_asset_ids) if intent and intent.confidence >= CONF_MEDIUM else []

    primary_covers = (
        editability.media_kind == "video" and usable >= required * 0.88
    ) or (
        # Stills can hold any VO duration; complements only for long beats.
        editability.media_kind == "image" and required < 10.0 and not prefer_dual
    )
    # Short VO: one visual is enough — never dual-cut a covering primary.
    short_vo = required <= 2.75

    comps: List[AssetCandidate] = []
    need_comp = needs_complementary_coverage(
        required=required,
        primary_usable=usable if editability.media_kind == "video" else 0.0,
        coverage_strategy=coverage_strategy,
        media_kind=editability.media_kind,
    )
    # prefer_dual may seek complements only when primary does not already cover
    # (or the beat is long enough that progression is editorially useful).
    if prefer_dual and candidates and not short_vo:
        if not primary_covers or required >= 8.0:
            need_comp = True
    if candidates and need_comp:
        comps = select_complements(
            list(candidates),
            scene=scene,
            primary=primary,
            beat_role=role,
            used_asset_ids=list(used_asset_ids or []),
            recent_asset_ids=list(recent_asset_ids or []),
            max_complements=3 if required >= 8.0 or prefer_dual else 2,
            preferred_asset_ids=prefs,
        )

    # Dual only when primary cannot cover OR a long beat with explicit dual intent.
    # Never: "complement exists → cut early." Never: stale strategy=dual alone.
    dual_justified = bool(comps) and not short_vo and (
        (editability.media_kind == "video" and usable < required * 0.88)
        or (
            editability.media_kind == "image"
            and required >= 7.0
            and (prefer_dual or coverage_strategy == "dual" or required >= 10.0)
        )
        or (
            prefer_dual
            and required >= 8.0
            and role in ("process", "scale", "cause_effect", "reveal")
            and not primary_covers
        )
    )

    if dual_justified:
        decision = _dual_asset_decision(
            scene=scene,
            required=required,
            role=role,
            primary=primary,
            primary_usable=usable if editability.media_kind == "video" else 0.0,
            complements=comps[: 2 if required < 10.0 else 3],
            tracker=tracker,
        )
    elif editability.media_kind == "image":
        decision = _image_coverage(
            scene=scene,
            required=required,
            role=role,
            tracker=tracker,
            primary=primary,
            intent=intent,
        )
    elif usable >= required * 0.88:
        # Strong video covers the beat — do not multi-cut for prefer_multi alone.
        decision = _single_shot_decision(
            scene=scene,
            required=required,
            role=role,
            usable=usable,
            tracker=tracker,
            primary=primary,
        )
    else:
        decision = _video_multi_shot(
            scene=scene,
            editability=editability,
            required=required,
            role=role,
            tracker=tracker,
            primary=primary,
            intent=intent,
        )

    if intent and intent.confidence >= CONF_MEDIUM:
        decision.visual_role = role  # type: ignore[assignment]
        if intent.reveal or intent.reveal_phase != "none":
            decision.reveal_phase = intent.reveal_phase
        if intent.emotional_state:
            decision.attention_state = intent.emotional_state
        if intent.reasoning and decision.confidence < 0.9:
            decision.reason = f"{decision.reason} | AI: {intent.reasoning[:120]}"

    decision = _reconcile_playable_coverage(
        decision,
        primary=primary,
        usable=usable if editability.media_kind == "video" else 0.0,
        required=required,
        media_kind=editability.media_kind,
    )

    for shot in decision.shots:
        key = source_identity_key(asset_id=shot.asset_id, source_path=shot.source_path)
        if key:
            tracker.note_asset(key)
    tracker.update_from_shots(
        [s.shot_size for s in decision.shots],
        decision.shots[-1].camera_style if decision.shots else "static",
        decision.strategy,
        scene.visual_variety_key,
        cameras=[s.camera_style for s in decision.shots],
    )
    return decision


def plan_all_edit_decisions(
    scenes: Sequence[EditorialScene],
    *,
    media_paths: Optional[dict] = None,
    candidates_by_scene: Optional[Dict[str, Sequence[AssetCandidate]]] = None,
    coverage_by_scene: Optional[Dict[str, dict]] = None,
    intents_by_scene: Optional[Dict[str, EditorialIntent]] = None,
) -> List[EditDecision]:
    """Plan edit decisions for every scene with continuity + asset-usage tracking."""
    media_paths = media_paths or {}
    candidates_by_scene = candidates_by_scene or {}
    coverage_by_scene = coverage_by_scene or {}
    intents_by_scene = intents_by_scene or {}
    tracker = ContinuityTracker()
    total = len(scenes)
    used: List[str] = []
    recent: List[str] = []
    out: List[EditDecision] = []
    for i, scene in enumerate(scenes):
        sn = str(scene.scene_number)
        path = (
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
        cands = (
            candidates_by_scene.get(sn)
            or candidates_by_scene.get(sn.zfill(3))
            or candidates_by_scene.get(sn.lstrip("0") or sn)
            or []
        )
        intent = (
            intents_by_scene.get(sn)
            or intents_by_scene.get(sn.zfill(3))
            or intents_by_scene.get(sn.lstrip("0") or sn)
        )
        decision = plan_edit_decision(
            scene,
            media_path=path,
            tracker=tracker,
            asset_label=str(path) if path else sn,
            candidates=list(cands),
            coverage_strategy=str(cov.get("strategy") or ""),
            used_asset_ids=used,
            recent_asset_ids=recent,
            intent=intent,
        )
        if not (intent and intent.confidence >= CONF_MEDIUM and intent.emotional_state):
            decision.attention_state = attention_state_for_scene(scene, i, total)
        if not (
            intent
            and intent.confidence >= CONF_MEDIUM
            and (intent.reveal or intent.reveal_phase != "none")
        ):
            decision.reveal_phase = reveal_phase_for_scene(scene)
        for shot in decision.shots:
            aid = source_identity_key(
                asset_id=shot.asset_id, source_path=shot.source_path
            ) or (shot.asset_id or "")
            if aid:
                used.append(aid)
                recent.append(aid)
                if len(recent) > 24:
                    recent = recent[-24:]
        out.append(decision)
    return out
