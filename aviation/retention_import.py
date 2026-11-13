"""Retention data import (docs/aviation/MASTER_PLAN.md section 6 'after publishing', step 15): YouTube Studio's audience-retention
export -> where viewers left -> what was on screen then -> this channel's planner limits, tuned a little.

    read_curve(csv_path, total_s) -> [(t_seconds, retention_pct)]   lenient: a position column (percent 0-100, 'm:ss', or seconds)
                                                                    and a retention column ('Audience retention', 'Absolute ...', '%')
    dips(curve, min_drop=1.5) -> [{start, end, drop}]               falls steeper than the film's usual slope, merged
    analyze(curve, plan) -> report                                  each dip with the picture on screen (look, kind, layer, scene) and
                                                                    a cause: same_kind_long, stage_idle, card_long, slow_opening,
                                                                    no_rehook, look_change; plus per-kind drop rates
    tune(report, path=None) -> limits                               nudges MAX_SAME_S / CARD_MAX / REHOOK_MAX_S / OPEN_AVG_S a step
                                                                    toward faster pictures where the dips say so (never past floors),
                                                                    saved in tuning.json (per install = per channel, next to the library)
    limits(path=None) -> {name: value}                              the saved limits; retention.apply uses them on the next film
Nothing about the script changes: the data only tunes how long pictures hold.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULTS = {"MAX_SAME_S": 8.0, "CARD_MAX": 6.0, "REHOOK_MAX_S": 90.0, "OPEN_AVG_S": 2.0}
FLOORS = {"MAX_SAME_S": 5.0, "CARD_MAX": 4.0, "REHOOK_MAX_S": 45.0, "OPEN_AVG_S": 1.2}
STEP = {"MAX_SAME_S": 1.0, "CARD_MAX": 0.5, "REHOOK_MAX_S": 10.0, "OPEN_AVG_S": 0.2}
CAUSE_LIMIT = {"same_kind_long": "MAX_SAME_S", "stage_idle": "MAX_SAME_S", "card_long": "CARD_MAX", "no_rehook": "REHOOK_MAX_S",
               "slow_opening": "OPEN_AVG_S"}


def tuning_path(path: Any = None) -> Path:
    if path:
        return Path(path)
    from . import library as LIB
    return LIB.root() / "tuning.json"


def limits(path: Any = None) -> Dict[str, float]:
    out = dict(DEFAULTS)
    try:
        saved = json.loads(tuning_path(path).read_text(encoding="utf-8"))
        for k in DEFAULTS:
            if k in saved:
                out[k] = max(FLOORS[k], float(saved[k]))
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------------------------------------------- reading

def _num(s: str) -> Optional[float]:
    s = str(s or "").strip().replace("%", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _secs(s: str) -> Optional[float]:
    m = re.match(r"^\s*(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\s*$", str(s or ""))
    if m:
        return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return None


def read_curve(csv_path: Any, total_s: float) -> List[Tuple[float, float]]:
    text = Path(csv_path).read_text(encoding="utf-8-sig", errors="replace")
    rows = [r for r in csv.reader(text.splitlines()) if any(c.strip() for c in r)]
    if not rows:
        return []
    head = [h.strip().lower() for h in rows[0]]
    pos_i = next((i for i, h in enumerate(head) if "position" in h or h in ("time", "moment", "elapsed")), 0)
    ret_i = next((i for i, h in enumerate(head) if "absolute" in h and "retention" in h), None)
    if ret_i is None:
        ret_i = next((i for i, h in enumerate(head) if "retention" in h or "watching" in h), 1 if len(head) > 1 else 0)
    pct_pos = "%" in head[pos_i] or "percent" in head[pos_i] or "(%)" in rows[0][pos_i]
    out = []
    for r in rows[1:]:
        if len(r) <= max(pos_i, ret_i):
            continue
        ret = _num(r[ret_i])
        raw = r[pos_i]
        t = _secs(raw)
        if t is None:
            v = _num(raw)
            if v is None:
                continue
            t = v / 100.0 * total_s if pct_pos else v          # '(%)' column -> share of the film, else seconds
        if ret is None:
            continue
        if ret <= 1.5 and all(_num(x[ret_i]) is None or _num(x[ret_i]) <= 1.5 for x in rows[1:6] if len(x) > ret_i):
            ret *= 100.0                                   # a 0-1 ratio column
        out.append((float(t), float(ret)))
    out.sort()
    return out


def dips(curve: Sequence[Tuple[float, float]], min_drop: float = 1.5, skip_s: float = 3.0) -> List[Dict[str, float]]:
    """Stretches that fall faster than the film's usual slope by at least min_drop points (the first skip_s, the normal intro
    drop, is left out)."""
    pts = [p for p in curve if p[0] >= skip_s]
    if len(pts) < 3:
        return []
    total_fall = pts[0][1] - pts[-1][1]
    span = max(1e-6, pts[-1][0] - pts[0][0])
    usual = max(0.0, total_fall / span)
    raw = []
    for (t0, r0), (t1, r1) in zip(pts, pts[1:]):
        extra = (r0 - r1) - usual * (t1 - t0)
        if extra > 0:
            raw.append([t0, t1, extra])
    merged: List[List[float]] = []
    for a in raw:
        if merged and a[0] - merged[-1][1] <= 2.0:
            merged[-1][1], merged[-1][2] = a[1], merged[-1][2] + a[2]
        else:
            merged.append(list(a))
    return [{"start": a, "end": b, "drop": round(d, 2)} for a, b, d in merged if d >= min_drop]


# ---------------------------------------------------------------------------------------------------------------- analysis

def _on_screen(plan: Any, t: float) -> Dict[str, Any]:
    from . import transitions as TR
    base = [s for s in plan.shots if (s.get("kind") == "footage" or s.get("full_frame")) and s["start"] <= t < s["end"]]
    s = base[-1] if base else {}
    over = [x for x in plan.shots if not (x.get("kind") == "footage" or x.get("full_frame")) and x["start"] <= t < x["end"]]
    return {"look": TR.look_of(s) if s else "", "layer": s.get("layer") or s.get("kind") or "", "scene": s.get("scene"),
            "held_s": round(t - float(s.get("start", t)), 1), "since_start": s.get("start"), "overlays": [o.get("layer") for o in over],
            "shot": s}


def _cause(plan: Any, d: Dict[str, float], at: Dict[str, Any], lim: Dict[str, float], rehooks: Sequence[float]) -> str:
    t = d["start"]
    if t <= 30.0:
        return "slow_opening"
    sh = at.get("shot") or {}
    if sh.get("layer") == "stage.lay_stage":
        rel = t - float(sh["start"])
        last_new = max([float(e["t0"]) for e in sh["params"].get("elements") or [] if float(e["t0"]) <= rel] or [0.0])
        if rel - last_new >= lim["MAX_SAME_S"] * 0.6:
            return "stage_idle"
    elif str(at.get("layer", "")).startswith(("cards.", "war.", "gfx.")) and at["held_s"] >= lim["CARD_MAX"] * 0.7:
        return "card_long"
    elif at["held_s"] >= lim["MAX_SAME_S"] * 0.7:
        return "same_kind_long"
    prev = max([r for r in rehooks if r <= t] or [0.0])
    if t - prev >= lim["REHOOK_MAX_S"] * 0.7:
        return "no_rehook"
    if any(x.get("transition") and abs(float(x["start"]) - t) < 1.5 for x in plan.shots):
        return "look_change"
    return "other"


def analyze(curve: Sequence[Tuple[float, float]], plan: Any, lim: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    lim = lim or limits()
    rehooks = sorted(float(s["start"]) for s in plan.shots if s.get("layer") == "retention.lay_rehook")
    out = []
    for d in dips(curve):
        at = _on_screen(plan, d["start"])
        out.append(dict(d, look=at["look"], layer=at["layer"], scene=at["scene"], held_s=at["held_s"],
                        cause=_cause(plan, d, at, lim, rehooks)))
    by_look: Dict[str, float] = {}
    for d in out:
        by_look[d["look"]] = round(by_look.get(d["look"], 0.0) + d["drop"], 2)
    causes: Dict[str, float] = {}
    for d in out:
        causes[d["cause"]] = round(causes.get(d["cause"], 0.0) + d["drop"], 2)
    return {"dips": out, "drop_by_look": by_look, "drop_by_cause": causes, "limits_used": lim}


def tune(report: Dict[str, Any], path: Any = None, min_points: float = 3.0) -> Dict[str, float]:
    """One step faster for every limit whose cause lost at least min_points of retention; floors are never crossed.
    Small, one film at a time, so a single odd video cannot swing the channel's pacing."""
    cur = limits(path)
    for cause, pts in (report.get("drop_by_cause") or {}).items():
        k = CAUSE_LIMIT.get(cause)
        if k and pts >= min_points:
            cur[k] = max(FLOORS[k], round(cur[k] - STEP[k], 2))
    p = tuning_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(cur, last_report={k: v for k, v in report.items() if k != "limits_used"}), indent=1,
                              default=str), encoding="utf-8")
    tmp.replace(p)
    return cur
