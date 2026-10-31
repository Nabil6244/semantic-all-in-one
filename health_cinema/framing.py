"""Framing audit for a Health Cinema 3D journey: how big the subject is on screen, how much of it is cut off, and how it sits in the frame, per second.
Pure geometry (the sampler's own camera and projection, no render), so it runs on every template in a second and the same numbers can gate a scene.

The subject is each camera key's own target anchor, judged around the key's time (where the camera has arrived). Its box is projected to the screen:
  fill   share of the frame height the box covers (1.0 = fills it); w_fill the same for width
  cut    share of the box's screen area outside the frame (0 = fully in view)
  cx, cy the box centre as a fraction of the frame (0.5, 0.5 = centred)"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional

from . import journey

def _box(anchors: dict, ref: str) -> Optional[dict]:
    a = anchors.get(ref)
    return a if a and "min" in a and "max" in a else None

def measure(spec: dict, anchors: dict, t: float, ref: str, W: int = 1920, H: int = 1080) -> Optional[dict]:
    """Screen metrics of the anchor `ref` at time t, or None when it has no box."""
    box = _box(anchors, ref)
    if box is None: return None
    cam, look, fov = journey._cam_state(spec, anchors, t, W / H)
    e = journey.extent(cam, look, fov, journey.box_points(box), W, H)
    if e is None: return {"t": t, "fill": 9.0, "w_fill": 9.0, "cut": 1.0, "cx": 0.5, "cy": 0.5, "behind": True}      # a corner is behind the camera: nothing sensible is in frame
    x0, y0, x1, y1 = e
    area = max(1e-9, (x1 - x0) * (y1 - y0)); vx, vy = max(0.0, min(x1, W) - max(x0, 0)), max(0.0, min(y1, H) - max(y0, 0))
    return {"t": t, "fill": (y1 - y0) / H, "w_fill": (x1 - x0) / W, "cut": 1 - (vx * vy) / area, "cx": (x0 + x1) / 2 / W, "cy": (y0 + y1) / 2 / H, "behind": False}

def audit(spec: dict, anchors: dict, settle: float = 0.5, W: int = 1920, H: int = 1080) -> List[dict]:
    """Measurements where the camera has arrived: at each key and `settle` seconds either side of it, against that key's own target. (Between two keys the
    camera is travelling and the subject is ambiguous, so those moments are not judged.)"""
    out, seen = [], set()
    for k in spec["camera"]:
        for t in (k["t"] - settle, k["t"], k["t"] + settle):
            t = min(max(0.0, t), spec["duration"])
            if (round(t, 3), k["target"]) in seen: continue
            seen.add((round(t, 3), k["target"])); m = measure(spec, anchors, t, k["target"], W, H)
            if m: m["target"] = k["target"]; out.append(m)
    return out

def summary(rows: List[dict]) -> Dict[str, float]:
    """One line per scene: the median size of the subject, the share of time it is small (under 35% of the frame height) or cut off (over 15%), and the worst offset from centre."""
    if not rows: return {}
    fills = sorted(min(r["fill"], 3.0) for r in rows); n = len(rows)
    return {"median_fill": round(fills[n // 2], 2), "small_share": round(sum(r["fill"] < 0.35 for r in rows) / n, 2), "cut_share": round(sum(r["cut"] > 0.15 for r in rows) / n, 2),
            "max_off_centre": round(max(max(abs(r["cx"] - 0.5), abs(r["cy"] - 0.5)) for r in rows), 2)}
