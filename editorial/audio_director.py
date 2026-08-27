"""Audio Director — scene-local ambience gain, silence, and purposeful SFX from EditorialPlan.

Does NOT alter Stage A (atrim → asetpts → volume → afade → adelay → amix).
Only adjusts volumes / which events exist before they reach the existing mixer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .schema import EditorialPlan, EditorialScene, HOOK_WINDOW_S

# Purpose → relative ambience gain multiplier (applied on top of settings base volume).
_PURPOSE_AMBIENCE_GAIN = {
    "hook": 1.05,
    "context": 1.0,
    "evidence": 0.85,
    "explanation": 0.80,
    "emotion": 0.90,
    "reveal": 0.88,
    "comparison": 0.92,
    "scale": 1.05,
    "process": 0.85,
    "timeline": 0.88,
    "location": 0.95,
    "character": 0.90,
    "transition": 0.70,
    "reflection": 0.72,
    "outro": 0.75,
}

# Purpose → SFX strength preference (0 = suppress, 1 = full).
_PURPOSE_SFX_WEIGHT = {
    "hook": 1.0,
    "context": 0.55,
    "evidence": 0.35,
    "explanation": 0.30,
    "emotion": 0.40,
    "reveal": 0.85,
    "comparison": 0.45,
    "scale": 0.30,
    "process": 0.50,
    "timeline": 0.35,
    "location": 0.40,
    "character": 0.40,
    "transition": 0.45,
    "reflection": 0.20,
    "outro": 0.25,
}

_MAX_AMBIENCE_VOL = 0.42
_MIN_AMBIENCE_VOL = 0.05
_SILENCE_DIP = 0.35  # multiply volume when allow_silence


def ambience_intensity_for_scene(scene: EditorialScene) -> float:
    """Derive per-scene ambience intensity multiplier (0.35–1.35)."""
    base = float(scene.ambience_intensity or 1.0)
    purpose_gain = _PURPOSE_AMBIENCE_GAIN.get(scene.purpose, 1.0)
    attention = float(scene.attention_score or 0.5)
    # High attention slightly lifts bed; low attention dips.
    attention_gain = 0.85 + 0.30 * attention
    pacing = str(scene.pacing_bias or "normal")
    pacing_gain = {"slow": 0.88, "normal": 1.0, "fast": 1.08}.get(pacing, 1.0)
    out = base * purpose_gain * attention_gain * pacing_gain
    if scene.start < HOOK_WINDOW_S and scene.purpose == "hook":
        out *= 1.08
    if scene.allow_silence:
        out *= _SILENCE_DIP
    return round(max(0.35, min(1.35, out)), 3)


def enrich_scene_audio_fields(plan: EditorialPlan) -> EditorialPlan:
    """Fill ambience_intensity, allow_silence, sfx_moments on each scene (in place)."""
    for i, scene in enumerate(plan.scenes):
        # Strategic silence: short reflective / outro / low-attention explanation.
        if scene.allow_silence:
            pass
        elif scene.purpose in ("outro", "emotion", "reflection", "reveal") and scene.attention_score <= 0.55:
            scene.allow_silence = True
        elif scene.purpose in ("explanation", "process") and scene.attention_score <= 0.4:
            scene.allow_silence = True
        elif scene.duration >= 4.5 and scene.attention_score <= 0.35:
            scene.allow_silence = True

        scene.ambience_intensity = ambience_intensity_for_scene(scene)
        scene.sfx_moments = plan_sfx_moments_for_scene(scene, index=i)
    return plan


def plan_sfx_moments_for_scene(scene: EditorialScene, *, index: int = 0) -> List[dict]:
    """Sparse intentional SFX moment hints (scene-local times, absolute timeline)."""
    weight = _PURPOSE_SFX_WEIGHT.get(scene.purpose, 0.5)
    if scene.allow_silence:
        weight *= 0.25
    if weight < 0.28:
        return []
    if scene.duration < 1.2:
        return []

    moments: List[dict] = []
    # Transition whoosh near scene entry (not first scene).
    if index > 0 and scene.transition_in and scene.transition_in != "cut":
        if weight >= 0.4:
            moments.append(
                {
                    "t": round(max(scene.start, scene.start - 0.05), 3),
                    "kind": "transition",
                    "strength": round(min(1.0, weight * 0.85), 3),
                }
            )
    # Mid-scene accent for hook / high attention.
    if scene.purpose in ("hook", "reveal") or scene.attention_score >= 0.78:
        mid = scene.start + scene.duration * 0.42
        moments.append(
            {
                "t": round(mid, 3),
                "kind": "impact",
                "strength": round(min(1.0, 0.55 + 0.4 * scene.attention_score), 3),
            }
        )
    elif scene.purpose in ("evidence", "explanation"):
        # Very sparse — only if high attention.
        if scene.attention_score >= 0.8 and scene.duration >= 2.5:
            moments.append(
                {
                    "t": round(scene.start + scene.duration * 0.5, 3),
                    "kind": "subtle",
                    "strength": 0.35,
                }
            )
    elif scene.purpose == "transition" and weight >= 0.4:
        moments.append(
            {
                "t": round(scene.start + min(0.15, scene.duration * 0.1), 3),
                "kind": "transition",
                "strength": 0.4,
            }
        )
    return moments


def apply_ambience_intensity_to_beds(
    beds: Sequence[dict],
    plan: EditorialPlan,
) -> List[dict]:
    """Multiply each bed's volume by scene ambience_intensity. Never changes start/end."""
    by_sn = plan.scene_by_number()
    out: List[dict] = []
    for bed in beds:
        b = dict(bed)
        sn = str(b.get("scene_number") or "")
        scene = by_sn.get(sn)
        base = float(b.get("volume") or 0.30)
        if scene is not None:
            mult = float(scene.ambience_intensity or 1.0)
            # Narration-relative soft envelope: slightly lower mid-scene for long VO.
            if scene.duration >= 3.0 and not scene.allow_silence:
                mult *= 0.92
            vol = base * mult
        else:
            vol = base
        b["volume"] = round(max(_MIN_AMBIENCE_VOL, min(_MAX_AMBIENCE_VOL, vol)), 3)
        out.append(b)
    return out


def filter_sfx_events(
    events: Sequence[dict],
    plan: EditorialPlan,
    *,
    aligned_rows: Optional[Sequence[dict]] = None,
) -> List[dict]:
    """Reshape SFX using purpose/attention/silence; keep events inside scene windows."""
    by_sn = plan.scene_by_number()
    windows = {sn: (s.start, s.end) for sn, s in by_sn.items()}
    out: List[dict] = []
    recent_scenes: List[str] = []

    for ev in events:
        e = dict(ev)
        sn = str(e.get("scene_number") or "")
        scene = by_sn.get(sn)
        t = float(e.get("start") or 0.0)

        # Bound to scene window when known — never bleed past visual cut.
        if sn in windows:
            start, end = windows[sn]
            if t < start - 0.12 or t >= end:
                # Transition SFX may sit just before start.
                if not (start - 0.12 <= t < start and e.get("type") in ("whoosh", "transition", "swoosh")):
                    continue
            # Clamp late events inside window.
            if t >= end:
                continue

        if scene is not None:
            if scene.allow_silence:
                # Suppress beat/impact SFX; allow soft transition whoosh only.
                kind = str(e.get("type") or e.get("kind") or "").lower()
                if kind not in ("whoosh", "transition", "swoosh", "soft_whoosh"):
                    continue
                e["volume"] = round(min(0.28, float(e.get("volume") or 0.3) * 0.55), 3)

            weight = _PURPOSE_SFX_WEIGHT.get(scene.purpose, 0.5)
            weight *= 0.7 + 0.5 * float(scene.attention_score or 0.5)
            if weight < 0.32 and str(e.get("type") or "") not in ("whoosh", "transition"):
                continue
            e["volume"] = round(
                min(0.55, float(e.get("volume") or 0.35) * (0.75 + 0.4 * weight)),
                3,
            )

            # Neighbor anti-repetition: skip beat SFX if previous scene also had one.
            if sn in recent_scenes[-1:] and scene.purpose in ("explanation", "evidence", "emotion"):
                kind = str(e.get("type") or "").lower()
                if kind not in ("whoosh", "transition", "swoosh"):
                    continue

        out.append(e)
        if sn:
            recent_scenes.append(sn)
            if len(recent_scenes) > 6:
                del recent_scenes[0]

    # sfx_moments are hints used upstream for scoring; only catalog-backed events mix.
    out.sort(key=lambda e: float(e.get("start") or 0.0))
    return out


def apply_audio_director(
    plan: EditorialPlan,
    *,
    ambience_beds: Optional[Sequence[dict]] = None,
    sfx_events: Optional[Sequence[dict]] = None,
) -> Tuple[List[dict], List[dict]]:
    """Enrich plan audio fields and return (beds, sfx) ready for the mixer."""
    enrich_scene_audio_fields(plan)
    beds = apply_ambience_intensity_to_beds(ambience_beds or [], plan)
    sfx = filter_sfx_events(sfx_events or [], plan)
    return beds, sfx
