"""Measure decoded journey frames (not contact sheets): subject centring, border clipping, coverage, temporal stability.
Usage: measure.py FRAME_DIR OUT_JSON  (frames are the raw backend PNGs, before the label overlay)"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image

def measure(fd):
    files = sorted(Path(fd).glob("f*.png")); rows = []; prev = None
    for p in files:
        a = np.asarray(Image.open(p).convert("RGB")).astype(np.int16); H, W, _ = a.shape
        bg = a[2, 2]; mask = np.abs(a - bg).sum(2) > 24; cov = float(mask.mean())
        ys, xs = np.nonzero(mask)
        if len(xs) < 50: rows.append({"cov": cov, "cx": None, "cy": None, "clip": 0, "diff": 0}); prev = a; continue
        border = int(mask[0].sum() + mask[-1].sum() + mask[:, 0].sum() + mask[:, -1].sum())
        d = float(np.abs(a - prev).mean()) if prev is not None else 0.0
        rows.append({"cov": cov, "cx": float(xs.mean() / W), "cy": float(ys.mean() / H), "bx0": float(xs.min() / W), "bx1": float(xs.max() / W),
                     "by0": float(ys.min() / H), "by1": float(ys.max() / H), "clip": border, "diff": d}); prev = a
    return rows

def summarize(rows):
    ok = [r for r in rows if r["cx"] is not None]
    cx = np.array([r["cx"] for r in ok]); cy = np.array([r["cy"] for r in ok]); df = np.array([r["diff"] for r in rows])
    jump = np.abs(np.diff(cx)) + np.abs(np.diff(cy)); jerk = np.abs(np.diff(np.diff(cx))) + np.abs(np.diff(np.diff(cy)))
    med = np.median(df[df > 0]) if (df > 0).any() else 0
    return {"frames": len(rows), "centre_dx_max": float(np.abs(cx - 0.5).max()), "centre_dx_mean": float(np.abs(cx - 0.5).mean()),
            "centre_dy_mean": float(np.abs(cy - 0.5).mean()), "centroid_jump_max": float(jump.max()), "centroid_jerk_max": float(jerk.max()),
            "clip_frames": int(sum(1 for r in ok if r["clip"] > 6)), "diff_spikes(>4x median)": int((df > 4 * max(med, 1e-6)).sum()),
            "cov_min": float(min(r["cov"] for r in rows)), "cov_max": float(max(r["cov"] for r in rows))}

if __name__ == "__main__":
    rows = measure(sys.argv[1]); s = summarize(rows); print(json.dumps(s, indent=1))
    if len(sys.argv) > 2: Path(sys.argv[2]).write_text(json.dumps({"summary": s, "rows": rows}))
