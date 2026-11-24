"""Explainer splice: the picture clips are put into the video by the one encode after the render, not copied through the map engine.

A 37-minute Explainer is ~94 % picture clips (baked boards and push-in stills, explainer/bake.py). The map engine used to cut each clip into JPEG frames, read them
back and encode them again: ~27 ms a frame, about 10 of the map stage's 16 minutes, for frames that are exactly the clip. Now the spec lists those clips
(spec["footage_holes"]); the engine writes a blank frame wherever one of them alone fills the screen and reports the spans (sidecar "footage_holes"), and
explainer.beats.overlay.composite_chunked lays the clip itself back over its span in the same pass that lays on the boards and the presenter.
EXPLAINER_NO_SPLICE=1 turns it off (the engine then copies the clip frames as before)."""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

PREFIXES = ("baked_", "still_")
SLACK_FRAMES = 1.5          # bake rounds a slot to whole frames: a clip up to this much shorter shows its last frame (the engine slowed it by under 1 %)


def _duration(path: str) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip() or 0.0)
    except Exception:
        return 0.0


def choose(spec: Dict[str, Any], log=lambda m: None) -> int:
    """Lists in spec["footage_holes"] the Explainer clips the engine may leave blank: our own full-frame clips (no push-in to add, no loop),
    each at least as long as every slot it fills. Returns how many. Never raises."""
    try:
        if os.environ.get("EXPLAINER_NO_SPLICE") == "1":
            return 0
        fps = float(spec.get("fps") or 30)
        if int(spec.get("width") or 0) * float(spec.get("pixel_scale") or 1) != 1920 or int(spec.get("height") or 0) * float(spec.get("pixel_scale") or 1) != 1080:
            return 0                                  # the clips are drawn at 1920x1080 (explainer/bake.py)
        slots: Dict[str, float] = {}
        for e in spec.get("events") or []:
            m = str(e.get("media", ""))
            if e.get("type") != "media_full" or not Path(m).name.startswith(PREFIXES) or e.get("kenburns") is not False or e.get("loop"):
                continue
            if float(e.get("start_s") or 0) != 0.0:
                continue
            slots[m] = max(slots.get(m, 0.0), float(e["t_out"]) - float(e["t_in"]))
        if not slots:
            return 0
        with ThreadPoolExecutor(8) as ex:
            lens = dict(zip(slots, ex.map(_duration, list(slots))))
        ok = sorted(m for m, s in slots.items() if lens.get(m, 0.0) > 0 and lens[m] >= s - SLACK_FRAMES / fps)
        if ok:
            spec["footage_holes"] = ok
            log(f"[Explainer] {len(ok)} picture clip(s) go straight into the final encode (the map engine skips their frames)")
        return len(ok)
    except Exception:
        spec.pop("footage_holes", None)
        return 0


def clip_frame(frame: int, t_in: float, fps: float) -> int:
    """The clip frame the engine would show at video frame `frame` (pakmap-engine/lib/anim.mjs clipFrame, rate 1)."""
    return max(0, int((frame / fps - t_in) * fps + 1e-9))


def runs_from_sidecar(sidecar: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The engine's blank spans, checked: [{from, to, media, t_in, start_s}]."""
    out = []
    for r in (sidecar or {}).get("footage_holes") or []:
        try:
            a, b = int(r["from"]), int(r["to"])
            if b > a and Path(str(r["media"])).is_file():
                out.append({"from": a, "to": b, "media": str(r["media"]), "t_in": float(r["t_in"]), "start_s": float(r.get("start_s") or 0.0)})
            else:
                out.append({"from": a, "to": b, "media": "", "t_in": 0.0, "start_s": 0.0})   # kept so the caller sees a span it cannot fill
        except Exception:
            continue
    return out
