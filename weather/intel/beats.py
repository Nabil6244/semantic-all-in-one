"""Beats from the narration itself, for a Weather project with no beat plan (mode A without beats.csv).

The narration's sentences (hybrid.narration.build_sentences: the script when there is one, else the transcript's pauses) are
grouped into map beats of about BEAT_TARGET_S seconds, each ending on a sentence end. Each beat's camera target is the place its
words name (a county or city the story names: its point, close up; otherwise the story's state), and Hybrid's own
director.derive_cameras turns the targets into camera moves. The result is an ordinary hybrid.plan.HybridPlan built through the
existing interfaces — no CSV is written."""

from __future__ import annotations

from typing import List, Optional, Sequence

BEAT_TARGET_S = 14.0
BEAT_MAX_S = 24.0


def plan_from_narration(words: Sequence, duration: float, notes: List[str], *, script: str = ""):
    from hybrid.director import derive_cameras
    from hybrid.narration import build_sentences
    from hybrid.plan import Beat, HybridPlan

    from .understand import Segment, understand

    sents = build_sentences(list(words), script or None, duration)
    if not sents:
        raise ValueError("the narration has no sentences to build beats from")
    groups: List[list] = [[]]
    for s in sents:
        cur = groups[-1]
        span = (s.end - cur[0].start) if cur else 0.0
        if cur and (span > BEAT_MAX_S or (cur[-1].end - cur[0].start) >= BEAT_TARGET_S):
            groups.append([s])
        else:
            cur.append(s)
    beats = []
    for i, g in enumerate(groups):
        start = 0.0 if i == 0 else g[0].start
        end = duration if i == len(groups) - 1 else groups[i + 1][0].start
        beats.append(Beat(id=f"b{i + 1}", mode="map", start=round(start, 3), end=round(end, 3), narration=" ".join(x.text for x in g)))
    segs = [Segment(b.id, b.mode, b.narration, b.start, b.end) for b in beats]
    u = understand(segs)
    state = u.states[0] if u.states else ""
    from .catalog import state_name

    region = state_name(state) if state else "United States"
    for b in beats:
        local = next((p for p in u.places if p.seg == b.id and p.kind in ("county", "city") and p.lat is not None), None)
        if local is not None:
            b.cam_place, b.cam_frame = f"{local.lat:.2f},{local.lon:.2f}", "local"
        else:
            b.cam_place, b.cam_frame = region, ("region" if state else "continental")
    plan = HybridPlan(duration=duration, beats=beats, settings={"drift_pct_per_s": 0.0})
    derive_cameras(plan)
    notes.append(f"the project has no beat plan, so {len(beats)} map beats were made from the narration's {len(sents)} sentences")
    return plan
