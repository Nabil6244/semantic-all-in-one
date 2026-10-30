"""Near-identical pictures: finds stretches of the timeline that keep showing (almost) the same picture so the director can reframe instead of repeating.

    fingerprint(path) -> 16x9 RGB float array (box-filtered; cached by file size+mtime)
    distance(a, b)    -> mean absolute difference 0..1 (identical = 0; two different explainer pictures are usually 0.12+)
    annotate(shots, images, threshold=0.07) -> shots (copies) with "same_run": {"id", "pos", "size", "seconds"} on every shot that belongs to a stretch of >= 2 shots
                                                  showing the same or near-identical picture; the other shots get no key.
images: {scene_no | str(scene_no) | shot_id: path}. Pure numpy + PIL, ~5 ms per picture, nothing is generated or sent anywhere."""
from __future__ import annotations

import copy
import os
from typing import Dict, List, Optional, Sequence

import numpy as np
from PIL import Image

THRESHOLD = 0.07
_FP: Dict[tuple, np.ndarray] = {}


def fingerprint(path: str) -> Optional[np.ndarray]:
    try:
        st = os.stat(path)
        key = (str(path), st.st_size, int(st.st_mtime))
    except OSError:
        return None
    if key not in _FP:
        try:
            with Image.open(path) as im:
                _FP[key] = np.asarray(im.convert("RGB").resize((16, 9), Image.BOX), np.float32) / 255.0
        except Exception:       # noqa: BLE001
            return None
    return _FP[key]


def distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())


def _picture(images: Dict, sh: dict) -> Optional[str]:
    for k in (sh.get("shot_id"), sh.get("scene_no"), str(sh.get("scene_no"))):
        if k is not None and images.get(k):
            return str(images[k])
    return None


def annotate(shots: Sequence[dict], images: Dict, threshold: float = THRESHOLD) -> List[dict]:
    out = [copy.deepcopy(s) for s in shots]
    runs: List[List[int]] = []
    cur: List[int] = []
    anchor = None                      # fingerprint the stretch started with: a slow drift of look-alikes still ends a stretch
    for i, sh in enumerate(out):
        p = _picture(images, sh)
        fp = fingerprint(p) if p else None
        same = bool(cur) and ((p is not None and p == _picture(images, out[cur[-1]])) or (fp is not None and anchor is not None and distance(fp, anchor) < threshold))
        if same:
            cur.append(i)
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur, anchor = [i], fp
    if len(cur) >= 2:
        runs.append(cur)
    for n, idx in enumerate(runs):
        secs = sum(max(0.0, float(out[i].get("end", 0)) - float(out[i].get("start", 0))) for i in idx)
        for pos, i in enumerate(idx):
            out[i]["same_run"] = {"id": f"run{n}", "pos": pos, "size": len(idx), "seconds": round(secs, 2)}
    return out
