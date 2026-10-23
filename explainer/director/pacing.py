"""Narrator runs, pacing metrics and the metaphor consistency check. Metrics are computed from the produced beats and reported against the scorecard targets (not forced)."""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .options import DirectorOptions


def plan_narrator(kinds: Sequence[Tuple[str, float, float]], opt: DirectorOptions) -> List[str]:
    """kinds: (kind, start, end) per beat. Returns per beat: 'none' for non-board beats or beats without the narrator, else 'only' | 'start' | 'mid' | 'end'."""
    if not opt.narrator:
        return ["none"] * len(kinds)
    want: List[bool] = []
    present = 0.0
    last_end = 0.0
    run_len = 0
    for k, (kind, a, b) in enumerate(kinds):
        if kind != "board":
            want.append(False)
            run_len = 0
            continue
        elapsed = max(b, 1e-6)
        w = (present / elapsed) < opt.narrator_share or (a - last_end) >= opt.narrator_every_s - 6.0
        if k == 0 or (want and want[-1] and run_len < 2 and kind == "board" and present / elapsed < 0.5):      # a run lasts at least 2 beats unless the narrator is already past half the runtime
            w = True
        want.append(w)
        if w:
            present += b - a
            last_end = b
            run_len += 1
        else:
            run_len = 0
    modes = []
    for k, w in enumerate(want):
        if not w:
            modes.append("none")
            continue
        prev = k > 0 and want[k - 1]
        nxt = k + 1 < len(want) and want[k + 1]
        modes.append("mid" if prev and nxt else "end" if prev else "start" if nxt else "only")
    return modes


def metrics(beats: Sequence[Dict[str, Any]], events: Sequence[float], narrator_spans: Sequence[Tuple[float, float]], duration: float, opt: DirectorOptions,
            meaningful: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    durs = [b["end"] - b["start"] for b in beats]
    mix: Dict[str, float] = {}
    for b in beats:
        mix[b["kind"]] = mix.get(b["kind"], 0.0) + b["end"] - b["start"]
    win_hits = []
    t = 0.0
    ev = sorted(events)
    while t + 2.0 <= duration + 1e-9:
        win_hits.append(any(t <= e < t + 2.0 for e in ev))
        t += 2.0
    mwin = []
    if meaningful is not None:
        t = 0.0
        mev = sorted(meaningful)
        while t + 2.0 <= duration + 1e-9:
            mwin.append(any(t <= e < t + 2.0 for e in mev))
            t += 2.0
    spans = sorted(narrator_spans)
    absent, cur = [], 0.0
    for a, b in spans:
        absent.append(a - cur)
        cur = max(cur, b)
    absent.append(duration - cur)
    share = sum(b - a for a, b in spans) / duration if duration else 0.0
    out = {
        "beats": len(beats), "duration_s": round(duration, 2),
        "layer_mix_s": {k: round(v, 2) for k, v in mix.items()}, "layer_mix_share": {k: round(v / duration, 3) for k, v in mix.items()},
        "shot_length": {"median_s": round(statistics.median(durs), 2), "min_s": round(min(durs), 2), "max_s": round(max(durs), 2),
                        "share_between_2_and_8_s": round(sum(1 for d in durs if 2.0 - 1e-9 <= d <= 8.0 + 1e-9) / len(durs), 3)},
        "change_density": {"windows_2s": len(win_hits), "windows_with_a_change": sum(win_hits), "share": round(sum(win_hits) / max(1, len(win_hits)), 3)},
        "meaningful_change_density": ({"windows_2s": len(mwin), "windows_with_a_change": sum(mwin), "share": round(sum(mwin) / max(1, len(mwin)), 3),
                                       "counts": "element starts (picture, title, line, box, tag, scroll, chip, arrow, card, caption), map layers and camera steps, archive start, beat cuts; not narrator poses, clears or per-word growth"}
                                      if meaningful is not None else None),
        "narrator": {"share": round(share, 3), "longest_absence_s": round(max(absent), 2) if absent else round(duration, 2), "target_share": opt.narrator_share, "target_longest_absence_s": opt.narrator_every_s},
    }
    out["targets"] = {"median_shot_near_4.6s": 3.4 <= out["shot_length"]["median_s"] <= 5.8, "90pct_shots_2_to_8s": out["shot_length"]["share_between_2_and_8_s"] >= 0.9,
                      "change_in_95pct_of_2s_windows": out["change_density"]["share"] >= 0.95, "narrator_absence_le_30s": out["narrator"]["longest_absence_s"] <= opt.narrator_every_s + 1e-9,
                      "narrator_share_35_to_60pct": 0.35 <= share <= 0.60 if opt.narrator else None}
    return out


def metaphor_report(uses: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    by: Dict[str, Dict[str, Any]] = {}
    for u in uses:
        d = by.setdefault(u["keyword"], {"assets": set(), "roles": set(), "count": 0, "beats": []})
        d["assets"].add(u["asset"])
        d["roles"].add(u["role"])
        d["count"] += 1
        d["beats"].append(u["beat"])
    rows = {k: {"assets": sorted(v["assets"]), "roles": sorted(v["roles"]), "count": v["count"], "beats": v["beats"]} for k, v in sorted(by.items())}
    return {"keywords": rows, "asset_consistent": all(len(v["assets"]) == 1 for v in by.values()),
            "recurring_keywords": sorted(k for k, v in by.items() if v["count"] >= 2)}
