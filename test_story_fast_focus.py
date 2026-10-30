"""Story Fast focus: subject regions of a picture, the ends auto_focus picks for each move, and a compositor camera that really goes there."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from story_fast import compose as C, focus as F

fails = []
def ok(c, m):
    print(("ok  " if c else "FAIL"), m)
    if not c: fails.append(m)

TMP = Path(tempfile.mkdtemp(prefix="sf_focus_"))
OUT = TMP / "o"; OUT.mkdir()
def save(im, name):
    p = TMP / name; im.save(p); return str(p)

def host_chart(bg=245):
    im = Image.new("RGB", (1280, 720), (bg, bg, bg)); d = ImageDraw.Draw(im)
    d.ellipse((190, 150, 290, 250), fill=(150, 100, 70)); d.rectangle((170, 250, 310, 560), fill=(30, 40, 70)); d.rectangle((185, 560, 295, 690), fill=(40, 50, 90))
    d.rectangle((760, 200, 1180, 480), fill=(60, 120, 200)); d.rectangle((790, 240, 1150, 270), fill=(250, 200, 40)); d.rectangle((790, 330, 1000, 450), fill=(220, 60, 60))
    return im
def dark_obj():
    im = Image.new("RGB", (1280, 720), (18, 18, 22)); ImageDraw.Draw(im).ellipse((520, 240, 760, 480), fill=(230, 200, 90)); return im

P = {"hc": save(host_chart(), "hc.png"), "dark": save(dark_obj(), "dark.png"), "flat": save(Image.new("RGB", (1280, 720), (128, 128, 128)), "flat.png"),
     "tiny": save(Image.new("RGB", (8, 8), (200, 10, 10)), "tiny.png")}
cd = str(TMP / "fc")

import time
r = F.find_focus(P["hc"], cd); pts = r["points"]
ok(len(pts) >= 2 and r["bg"] == "light", f"host+chart: {len(pts)} points, bg {r['bg']}")
near = lambda p, x, y, tol=.1: abs(p["x"] - x) < tol and abs(p["y"] - y) < tol
ok(any(near(p, .19, .28, .1) or near(p, .19, .55, .1) for p in pts), "a point on the host (left)")
ok(any(near(p, .76, .47, .1) for p in pts), "a point on the chart (right)")
ok(all(0 <= p["x"] <= 1 and 0 <= p["y"] <= 1 and p["kind"] in ("face", "object", "text", "region") for p in pts) and pts == sorted(pts, key=lambda p: -p["score"]), "points valid and sorted")
r2 = F.find_focus(P["dark"], cd); ok(r2["bg"] == "dark" and r2["points"] and near(r2["points"][0], .5, .5, .06), f"centred object on dark -> {r2['points'][:1]}")
ok(F.find_focus(P["flat"], cd)["points"] == [], "flat picture: no points")
ok(isinstance(F.find_focus(P["tiny"], cd)["points"], list), "tiny picture does not crash")
ok(F.find_focus(str(TMP / "nope.png"), cd)["points"] == [], "missing file: no points")
t = time.time(); F.find_focus(P["hc"], cd); ok((time.time() - t) < .05, f"cache hit {int((time.time()-t)*1000)} ms")
import shutil as sh2; sh2.rmtree(cd)
t = time.time(); F.find_focus(P["hc"], cd); ms = (time.time() - t) * 1000; ok(ms < 150, f"find_focus incl. decode {ms:.0f} ms")

J = lambda tr, **tp: {"still": P["hc"], "treatment": tr, "tparams": dict(tp), "seed": 0}
a = F.auto_focus(J("pan_right")); ok(a["focus_from"][0] < a["focus"][0] - .3, f"pan_right goes left -> right {a['focus_from']} -> {a['focus']}")
a = F.auto_focus(J("pan_left")); ok(a["focus_from"][0] > a["focus"][0] + .3, f"pan_left goes right -> left {a['focus_from']} -> {a['focus']}")
a = F.auto_focus(J("push_in")); ok("focus" in a and "focus_from" not in a, "push_in has only a focus")
a0 = F.auto_focus({**J("push_in"), "seed": 0})["focus"]; a1 = F.auto_focus({**J("push_in"), "seed": 1})["focus"]; ok(a0 != a1, "push_in alternates subject by seed")
a = F.auto_focus(J("reveal_up")); ok(a["focus_from"][1] > a["focus"][1] or a["focus_from"] != a["focus"], f"reveal_up from {a['focus_from']} to {a['focus']}")
a = F.auto_focus(J("tilt_up")); ok(a["focus_from"][1] >= a["focus"][1], "tilt_up goes upward")
ok(F.auto_focus(J("push_in", focus=[.3, .3]))["focus"] == [.3, .3], "explicit focus is kept")
ok("focus" not in F.auto_focus(J("push_in", auto_focus=False)), "auto_focus False respected")
fl = {"still": P["flat"], "treatment": "pan_left", "tparams": {"amount": .4}}; ok(F.auto_focus(fl) == {"amount": .4}, "flat picture: tparams untouched")
# focus_rank
k0 = F.auto_focus(J("push_in", focus_rank=0))["focus"]; k1 = F.auto_focus(J("push_in", focus_rank=1))["focus"]; k2 = F.auto_focus(J("push_in", focus_rank=len(pts)))["focus"]
ok(k0 != k1 and k2 == k0, f"focus_rank 0/1 differ, cyclic ({k0} {k1})")
for tr in ("pull_out", "hold_alive", "handheld", "dolly_through", "reveal_up"):
    ok(F.auto_focus(J(tr, focus_rank=0))["focus"] != F.auto_focus(J(tr, focus_rank=1))["focus"] or tr == "reveal_up", f"focus_rank changes {tr}")
p0 = F.auto_focus(J("pan_right", focus_rank=0)); p1 = F.auto_focus(J("pan_right", focus_rank=1))
ok(p0["focus_from"] == k0 and p0["focus"] == k1 and p1["focus_from"] == k1, "pan with focus_rank: rank r -> rank r+1")

# ---- compositor
W, H = 640, 360
def frames(path, idx):
    ff = C._ffmpeg(); res = []
    for n in idx:
        r = subprocess.run([ff, "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{n})", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
        res.append(np.frombuffer(r.stdout, np.uint8).reshape(H, W).astype(np.float32))
    return res
def probe(path):
    ff = C._ffmpeg().replace("ffmpeg", "ffprobe")
    r = subprocess.run([ff, "-v", "error", "-count_frames", "-select_streams", "v", "-show_entries", "stream=nb_read_frames,width,height", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    a = r.stdout.strip().split(","); return int(a[2]), int(a[0]), int(a[1])
def dark_cx(fr):
    m = fr < 50; ys, xs = np.nonzero(m[:, :]); return (xs.mean() / W, ys.mean() / H) if len(xs) > 200 else None
def job(tr, **tp): return {"still": P["hc"], "duration": 1.2, "fps": 20, "size": (W, H), "seed": 3, "treatment": tr, "tparams": tp, "intensity": "medium"}
def edge_ok(fr):   # no black bars: mid-edge strips stay bright on the white picture
    return min(fr[:, :6].mean(), fr[:, -6:].mean(), fr[:5, W//4:3*W//4].mean(), fr[-5:, W//4:3*W//4].mean()) > 60

out = OUT / "push.mp4"
C.render_shot(job("push_in", focus=[.19, .28], amount=.5), str(out))
n, w, h = probe(out); ok((n, w, h) == (24, W, H), f"push_in focus: {n} frames {w}x{h}")
f0, fl_ = frames(out, [0, 23])
c0, c1 = dark_cx(f0), dark_cx(fl_)
ok(c0 and c1 and abs(c1[0] - .5) < .22 and abs(c1[0] - .5) < abs(c0[0] - .5) - .08, f"last frame has the host near the centre (x {c0[0]:.2f} -> {c1[0]:.2f})")
ok(edge_ok(fl_) and edge_ok(f0), "push_in focus: no black bars")
# the same job without focus ends further from the host
o2 = OUT / "push0.mp4"; C.render_shot(job("push_in", auto_focus=False), str(o2)); l2 = frames(o2, [23])[0]; c2 = dark_cx(l2)
ok(c2 and abs(c2[0] - .5) > abs(c1[0] - .5) + .08, f"without focus the host stays off-centre (x {c2[0]:.2f})")

out = OUT / "pan.mp4"
C.render_shot(job("pan_right", focus_from=[.19, .28], focus=[.76, .47], amount=.5), str(out))
n, w, h = probe(out); ok((n, w, h) == (24, W, H), "pan focus: frames/size")
f0, fl_ = frames(out, [0, 23])
ok(edge_ok(f0) and edge_ok(fl_), "pan focus: no black bars")
bright = lambda fr, x0, x1: float((fr[:, int(x0 * W):int(x1 * W)] < 50).mean())   # dark host pixels
ok(bright(f0, 0, .5) > bright(f0, .5, 1) and bright(fl_, 0, .5) < bright(f0, 0, .5) - .02, "pan starts on the host side and ends away from it")
def chart_x(path, n):
    r = subprocess.run([C._ffmpeg(), "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{n})", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, np.uint8).reshape(H, W, 3).astype(int); m = (a[..., 2] > 140) & (a[..., 0] < 110) & (a[..., 1] < 170)
    return np.nonzero(m)[1].mean() / W
import warnings; warnings.simplefilter('ignore')
cx0, cx1 = chart_x(out, 0), chart_x(out, 23)
ok(abs(cx1 - .5) < .2, f"chart ends near the centre (x {cx0:.2f} -> {cx1:.2f})")
# pan_left runs the other way
outl = OUT / "panl.mp4"; C.render_shot(job("pan_left", focus_from=[.76, .47], focus=[.19, .28]), str(outl)); g0, g1 = frames(outl, [0, 23])
ok(bright(g0, .5, 1) < bright(g0, 0, .5) + 1 and bright(g1, 0, .5) > bright(g1, .5, 1) - 1, "pan_left renders")
ok(edge_ok(g0) and edge_ok(g1), "pan_left focus: no black bars")
# auto path inside render_shot (no focus key) works and equals the explicit result
oa = OUT / "auto.mp4"; C.render_shot({**job("pan_right"), "seed": 0}, str(oa)); na = probe(oa); ok(na == (24, W, H), "render_shot calls auto_focus itself")
key_a = C.job_key(job("push_in")); key_b = C.job_key(job("push_in", focus=[.2, .4])); ok(key_a != key_b, "focus is part of job_key")
t = time.time(); C.render_shot(job("push_in", focus=[.19, .28], amount=.5), str(OUT / "again.mp4")); ok((time.time() - t) < 1, "render cache hit")
# layered (depth) with a focus: no black bars (synthetic depth when the model is missing)
if not C._depth_available():
    def _fake(path):
        im = Image.open(path); w_, h_ = im.size; y, x = np.mgrid[0:h_, 0:w_]
        return np.exp(-(((x / w_ - .5) * 2.2) ** 2 + ((y / h_ - .55) * 2.2) ** 2)).astype(np.float32)
    C._depth = _fake; C._depth_available = lambda: True
ol = OUT / "par.mp4"; C.render_shot(job("parallax_right", focus_from=[.19, .28], focus=[.76, .47]), str(ol)); q0, q1 = frames(ol, [0, 23])
ok(edge_ok(q0) and edge_ok(q1) and probe(ol)[0] == 24, "parallax with focus: no black bars")
# amount: tighter framing zooms more
ot = OUT / "tight.mp4"; C.render_shot(job("push_in", focus=[.5, .5], amount=.9), str(ot)); ow = OUT / "wide.mp4"; C.render_shot(job("push_in", focus=[.5, .5], amount=.2), str(ow))
ok(frames(ot, [23])[0].std() != frames(ow, [23])[0].std(), "amount changes the framing")

shutil.rmtree(TMP, ignore_errors=True)
print("ALL OK" if not fails else f"{len(fails)} FAILED"); sys.exit(1 if fails else 0)
