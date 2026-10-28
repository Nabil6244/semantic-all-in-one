"""Backend-neutral sampler for a Health Cinema 3D journey spec: deterministic per-frame camera, layer alphas, highlight strength and
projected label positions. Both render backends (Blender, Three.js) consume the same frames, so labels and timing match exactly.
Coordinates: Blender world (metres, Z up, body front = -Y). Vertical FOV, pinhole projection.

Camera path: each key is a target (anchor + optional offset), distance, azimuth, elevation and fov. Look point, log-distance, angles and fov are
interpolated per channel with monotone cubic (PCHIP) splines through the keys: continuous velocity, no overshoot past a key value,
so the dolly neither stops at every key nor swings beyond it."""
from __future__ import annotations
import json, math
from pathlib import Path

SAFE = 0.06      # label anchors must lie inside the frame minus this margin (fraction of each side)
LABEL_MIN_LAYER_ALPHA = 0.85   # a label whose layer is still fading in is not shown yet

def _smooth(x): x = min(1.0, max(0.0, x)); return x * x * (3 - 2 * x)
def _curve(keys, t):
    if t <= keys[0][0]: return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1: return v0 + (v1 - v0) * _smooth((t - t0) / max(1e-9, t1 - t0))
    return keys[-1][1]

def _end_slope(h0, h1, d0, d1):
    s = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
    if s * d0 <= 0: return 0.0
    if d0 * d1 <= 0 and abs(s) > 3 * abs(d0): return 3 * d0
    return s

def _pchip_slopes(ts, vs):
    n = len(ts)
    if n == 2: s = (vs[1] - vs[0]) / (ts[1] - ts[0]); return [s, s]
    h = [ts[i + 1] - ts[i] for i in range(n - 1)]; d = [(vs[i + 1] - vs[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    for i in range(1, n - 1):
        if d[i - 1] * d[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]; m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    m[0] = _end_slope(h[0], h[1], d[0], d[1]); m[-1] = _end_slope(h[-1], h[-2], d[-1], d[-2])
    return m

def _pchip(ts, vs, t):
    if t <= ts[0]: return vs[0]
    if t >= ts[-1]: return vs[-1]
    m = _pchip_slopes(ts, vs)
    for i in range(len(ts) - 1):
        if t <= ts[i + 1]:
            h = ts[i + 1] - ts[i]; u = (t - ts[i]) / h; u2, u3 = u * u, u * u * u
            return (2 * u3 - 3 * u2 + 1) * vs[i] + (u3 - 2 * u2 + u) * h * m[i] + (-2 * u3 + 3 * u2) * vs[i + 1] + (u3 - u2) * h * m[i + 1]

def _anchor(anchors, ref): return anchors[ref]["center"]

def _key_state(anchors, k):
    c = _anchor(anchors, k["target"]); off = k.get("off", [0, 0, 0]); look = [c[i] + off[i] for i in range(3)]
    return {"look": look, "logd": math.log(k["dist"]), "az": k["az"], "el": k["el"], "fov": k["fov"]}

def _cam_state(spec, anchors, t):
    """Interpolate look point, log-distance, azimuth, elevation and fov (monotone cubic), then place the camera on that orbit.
    Log-distance makes a long dolly feel evenly paced instead of rushing as it nears the subject."""
    ks = spec["camera"]; ts = [k["t"] for k in ks]; st = [_key_state(anchors, k) for k in ks]
    look = [_pchip(ts, [s["look"][i] for s in st], t) for i in range(3)]
    d = math.exp(_pchip(ts, [s["logd"] for s in st], t))
    az, el = math.radians(_pchip(ts, [s["az"] for s in st], t)), math.radians(_pchip(ts, [s["el"] for s in st], t))
    pos = [look[0] + d * math.sin(az) * math.cos(el), look[1] - d * math.cos(az) * math.cos(el), look[2] + d * math.sin(el)]
    return pos, look, _pchip(ts, [s["fov"] for s in st], t)

def project(cam, look, fov_deg, p, W, H):
    f = [look[i] - cam[i] for i in range(3)]; n = math.sqrt(sum(x * x for x in f)); f = [x / n for x in f]
    up = (0, 0, 1); r = [f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]]
    rn = math.sqrt(sum(x * x for x in r)); r = [x / rn for x in r]
    u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
    d = [p[i] - cam[i] for i in range(3)]
    z = sum(d[i] * f[i] for i in range(3))
    if z <= 1e-6: return None
    x = sum(d[i] * r[i] for i in range(3)); y = sum(d[i] * u[i] for i in range(3))
    s = (H / 2) / math.tan(math.radians(fov_deg) / 2)
    return (W / 2 + x / z * s, H / 2 - y / z * s)

def label_visible(xy, W, H, margin=SAFE):
    return xy is not None and W * margin <= xy[0] <= W * (1 - margin) and H * margin <= xy[1] <= H * (1 - margin)

def sample(spec_path, anchors_path, fps, W, H):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8")); A = json.loads(Path(anchors_path).read_text(encoding="utf-8"))["anchors"]
    for k, v in spec.get("anchor_overrides", {}).items(): A[k] = dict(A.get(k, {}), **v)
    n = int(round(spec["duration"] * fps)); frames = []
    for i in range(n):
        t = i / fps; cam, look, fov = _cam_state(spec, A, t)
        alpha = {k: _curve(v, t) for k, v in spec["layers"].items()}
        fr = {"i": i, "t": t, "cam": cam, "look": look, "fov": fov, "alpha": alpha,
              "highlight": {h["id"]: _curve(h["strength"], t) for h in spec.get("highlights", [])},
              "glow": {g["id"]: _curve(g["strength"], t) for g in spec.get("glow", [])}, "labels": []}
        for lb in spec.get("labels", []):
            if not (lb["t0"] <= t <= lb["t1"]): continue
            a = A[lb["anchor"]]["center"]; p = [a[j] + lb["offset"][j] for j in range(3)]
            q = project(cam, look, fov, p, W, H)
            fade = min(1.0, (t - lb["t0"]) / 0.4, (lb["t1"] - t) / 0.4)
            layer_a = alpha.get(lb.get("layer", ""), 1.0) if lb.get("layer") else 1.0
            if layer_a < LABEL_MIN_LAYER_ALPHA or not label_visible(q, W, H): continue
            fr["labels"].append({"id": lb["id"], "text": lb["text"], "xy": q, "a": max(0.0, fade), "t": t, "side": lb.get("side", "right")})
        frames.append(fr)
    return spec, A, frames

if __name__ == "__main__":
    import sys
    spec, A, fr = sample(sys.argv[1], sys.argv[2], 24, 1280, 720)
    for f in fr[::24]: print(round(f["t"], 1), [round(x, 2) for x in f["cam"]], round(f["fov"]), {k: round(v, 2) for k, v in f["alpha"].items() if v > 0.01})
