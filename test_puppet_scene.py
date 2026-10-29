"""Plain-assert checks for the puppet scene layer (scene analysis, effects, transitions, render + cache). Run: python3 test_puppet_scene.py"""
import os, re, subprocess, sys, tempfile, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

from health_cinema.puppet import scene, effects, transitions, render

TMP = Path(tempfile.mkdtemp(prefix="puppet_test_"))
scene.CACHE_DIR = TMP / "cache"; render.CLIP_DIR = scene.CACHE_DIR / "clips"
SIZE = (320, 180)

def still(path, seed=1, post=True):
    """Synthetic collage-like still: sky/wall band, floor, a dark doorway, and a cream-edged brown 'gate' cut-out hanging from the bottom-left."""
    r = np.random.default_rng(seed); W, H = 688, 384
    a = np.zeros((H, W, 3), np.uint8); a[:] = (226, 214, 190)
    im = Image.fromarray(a); d = ImageDraw.Draw(im)
    d.rectangle([20, 20, W - 20, H - 20], fill=(176, 120, 80)); d.rectangle([20, 200, W - 20, H - 20], fill=(206, 170, 120))
    d.rectangle([300, 120, 350, 200], fill=(20, 12, 8))
    d.rectangle([40, 240, 200, H], fill=(244, 238, 222)); d.rectangle([48, 246, 192, H], fill=(120, 80, 40))
    n = (r.standard_normal((H, W, 1)) * 6).astype(np.int16)
    im = Image.fromarray(np.clip(np.asarray(im).astype(np.int16) + n, 0, 255).astype(np.uint8)); im.save(path); return str(path)

def frames_in(path):
    out = subprocess.run([render._ffmpeg(), "-v", "info", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True).stderr
    return int(re.findall(r"frame=\s*(\d+)", out)[-1])

A, B = still(TMP / "a.png", 1), still(TMP / "b.png", 2)

# ---- scene
t = time.time(); sc = scene.analyse(A); t1 = time.time() - t
assert 0.25 < sc.horizon < 0.6 and 0.6 < sc.walk_y < 0.92 and sc.horizon < sc.walk_y, (sc.horizon, sc.walk_y)
assert sc.depth.shape[0] > 100 and 0 <= sc.depth.min() and sc.depth.max() <= 1.0
assert sc.scale_at(sc.walk_y) == 1.0 and sc.scale_at(sc.horizon + .02) < 1.0 < sc.scale_at(1.0) + 1e-9 or sc.scale_at(1.0) >= 1.0
assert len(list(scene.CACHE_DIR.glob("scene_*.npz"))) == 1
t = time.time(); sc2 = scene.analyse(A); assert time.time() - t < t1 + 0.05 and sc2.key == sc.key and np.allclose(sc2.depth, sc.depth, atol=2e-3)
assert set(sc.light) >= {"tone", "dark", "tint", "shadow_dx"} and len(sc.light["tint"]) == 3
assert sc.doors and abs(sc.doors[0][0] - 325 / 688) < .1, sc.doors      # the dark doorway is found
f = sc.fit(SIZE); assert f.rgb.size == SIZE and f.depth.shape == (SIZE[1], SIZE[0]) and f.occ.size == SIZE
f2 = sc.fit(SIZE, shapes=[("rect", .1, .5, .3, 1.0), ("poly", [(.6, .5), (.8, .5), (.7, 1.0)])])
m = np.asarray(f2.occ); assert m[int(.8 * SIZE[1]), int(.2 * SIZE[0])] == 255 and m[int(.8 * SIZE[1]), int(.7 * SIZE[0])] == 255 and m[5, 5] < 255
assert transitions.mirror_fit(f).rgb.size == SIZE
lay = scene.tint_character(Image.new("RGBA", (10, 10), (20, 20, 20, 255)), sc.light); assert lay.mode == "RGBA"
assert scene.ground_shadow((60, 20), (30, 10), 100, sc.light).size == (60, 20)
try: scene.analyse(TMP / "missing.png"); raise SystemExit("missing still not rejected")
except scene.SceneError: pass

# ---- effects
w = effects.Warper(SIZE, boil_px=0.0); sx, sy = w.source(0.0)
same = np.asarray(w.warp(f.rgb, sx, sy), dtype=np.float32); assert np.abs(same - np.asarray(f.rgb, dtype=np.float32)).mean() < 2.5
wb = effects.Warper(SIZE, boil_px=30.0); sx, sy = wb.source(0.0); sx2, _ = wb.source(0.15)
assert np.abs(sx - wb.vx).max() > .5 and not np.allclose(sx, sx2)                      # boil moves every tick
sx3, _ = wb.source(0.02); assert np.allclose(sx, sx3)                                  # ...but holds within a tick
assert wb.warp(f.rgb, *wb.source(0.3, 1.1, (3, 2), f.depth, (6, 0))).size == SIZE
p = effects.Post(SIZE); o = p.apply(f.rgb, 0.1, 3); assert o.shape == (SIZE[1], SIZE[0], 3) and o.dtype == np.uint8
assert np.median(p.apply(f.rgb, 0.1, 3, dark=1.0)) == 0 and np.median(p.apply(f.rgb, 0.1, 3, fade=1.0)) == 0 and np.median(p.apply(f.rgb, 0.1, 3)) > 40
assert not np.array_equal(p.apply(f.rgb, 0.1, 3), p.apply(f.rgb, 0.1, 4))              # grain changes frame to frame

# ---- transitions
fa, fb = scene.analyse(A).fit(SIZE), scene.analyse(B).fit(SIZE)
assert set(transitions.list_transitions()) >= {"tear_seam", "door_walk", "page_flip", "behind_object"}
for name in transitions.list_transitions():
    tr = transitions.make(name, fa, fb, SIZE, {"stride_ratio": .62}); ph = []
    for u in (0, .25, .5, .75, 1.0):
        tf = tr.frame(u); assert tf.img.size == SIZE and tf.img.mode == "RGB", name
        assert tf.occ is None or tf.occ.size == SIZE
        ph.append(tf.char["phase"]); assert tf.char["h"] > 5 and 0 <= tf.char["alpha"] <= 1
    assert all(b >= a - 1e-6 for a, b in zip(ph, ph[1:])) and ph[-1] > ph[0] + .5, (name, ph)
try: transitions.make("nope", fa, fb, SIZE); raise SystemExit("bad transition accepted")
except ValueError: pass
tr = transitions.make("tear_seam", fa, fb, SIZE); assert tr.frame(0).light_w == 0 and tr.frame(1).light_w == 1   # light follows the seam
tr = transitions.make("tear_seam", fa, fb, SIZE); assert abs(tr.frame(.5).char["x"] - tr.frame(.1).char["x"]) < 1e-6   # fixed screen x

# ---- render + cache
out = TMP / "o"; out.mkdir()
t = time.time(); r1 = render.render_shot(A, "suit_man", "walk", out / "s.mp4", duration=1.0, fps=10, size=SIZE, params={"occluders": [("rect", .1, .5, .3, 1.0)]})
t_first = time.time() - t; assert Path(r1).exists() and frames_in(r1) == 10
clips = list(render.CLIP_DIR.glob("*.mp4")); assert len(clips) == 1; mt = clips[0].stat().st_mtime_ns
t = time.time(); render.render_shot(A, "suit_man", "walk", out / "s2.mp4", duration=1.0, fps=10, size=SIZE, params={"occluders": [("rect", .1, .5, .3, 1.0)]})
assert clips[0].stat().st_mtime_ns == mt and Path(out / "s2.mp4").read_bytes() == Path(r1).read_bytes() and time.time() - t < t_first / 2   # unchanged shot is not re-rendered
render.render_shot(A, "suit_man", "walk", out / "s3.mp4", duration=1.0, fps=10, size=SIZE, direction="left"); assert len(list(render.CLIP_DIR.glob("*.mp4"))) == 2
render.render_shot(A, "woman", "stand_idle", out / "s4.mp4", duration=0.5, fps=10, size=SIZE); assert frames_in(out / "s4.mp4") == 5
for name in transitions.list_transitions():
    o = render.render_transition(A, B, "worker", name, out / f"t_{name}.mp4", 1.0, fps=10, size=SIZE); assert frames_in(o) == 10, name

# ---- timeline mode: beats, enter/exit, links
assert isinstance(sc.floor_conf, float) and 0 <= sc.floor_conf <= 1 and isinstance(sc.floor_ok, bool)
assert scene.analyse(A).floor_conf == sc.floor_conf                                   # survives the cache round trip
P_ = render._puppet(); bank = render.SpriteBank(P_, "suit_man"); SZ = (1920, 1080)
pa, pb = render.link_params(A, B, "right", character="suit_man", size=SZ, phase=.3)
assert pa["exit"] == "right" and pb["enter"] == "left" and pa["link_out"] == pb["link_in"] and pa["link_out"]["facing"] == "right"
la = pa["link_out"]; assert 0.74 <= la["y"] <= .93 and .38 <= la["char_h"] <= .50 and la["speed"] > 0
tlA = render.Timeline(P_, bank, dict(pa, beats=[{"t0": 1.5, "t1": 3.0, "action": "point", "x0": .5}]), 6.0, SZ, sc.walk_y, sc.horizon, None, "right")
tlB = render.Timeline(P_, bank, dict(pb), 6.0, SZ, sc.walk_y, sc.horizon, None, "right")
sA, sB = tlA.state(6.0 - .6 - 1e-3), tlB.state(0.0)                                          # A's exit has just finished / B's walk-in is about to start
assert sA["x"] > SZ[0] and sB["x"] < 0 and sA["facing"] == sB["facing"] == "right"       # off the right edge / off the left edge
assert abs(sA["y"] - sB["y"]) < 1 and abs(sA["h"] - sB["h"]) < 1 and abs(sA["y"] / SZ[1] - la["y"]) < 1e-3 and abs(sA["h"] / SZ[1] - la["char_h"]) < 1e-3
gap = la["speed"] * SZ[0] * (.6 + 1e-3); st = bank.stride_ratio("walk", {"step_scale": 1.4}) * sA["h"]       # the walk carries on through the 0.6 s the character is off-screen
dphi = (sA["phase"] + gap / st - sB["phase"]) % 1.0; assert min(dphi, 1 - dphi) < .06, dphi
assert abs(sB["phase"] % 1.0 - la["phase"]) < .01
for tt in (.2, .8, 1.5):                                                                # B keeps walking in from the left at the link height
    s_ = tlB.state(tt); assert s_["action"] in ("walk", "stop") and abs(s_["y"] / SZ[1] - la["y"]) < .02 and s_["x"] > tlB.state(tt - .1)["x"] - 1e-6
mid = tlA.state(2.2); assert mid["action"] == "point" and abs(mid["x"] - .5 * SZ[0]) < 1                # stand beat holds x
xs_ = [tlA.state(t_)["x"] for t_ in np.arange(0, 6, .1)]; assert xs_[-1] > SZ[0] and max(xs_) > .9 * SZ[0] and all(b >= a - 1e-6 for a, b in zip(xs_[15:], xs_[16:]))
tlC = render.Timeline(P_, bank, {"enter": "right", "exit": "left"}, 6.0, SZ, sc.walk_y, sc.horizon, "walk", "left")   # crossing: one continuous walk, never turns around
xc = [tlC.state(t_)["x"] for t_ in np.arange(0, 5.4, .1)]; assert all(b < a for a, b in zip(xc, xc[1:])) and tlC.state(3.0)["facing"] == "left"
tlD = render.Timeline(P_, bank, {"beats": [{"t0": 0, "t1": 2, "action": "walk", "x0": -.1, "x1": .5}, {"t0": 3, "t1": 4.5, "action": "wave"}], "exit": "right"}, 8.0, SZ, sc.walk_y, sc.horizon, None, "right")
assert tlD.state(1.0)["action"] in ("walk", "stop") and tlD.state(2.6)["action"] == "stand_idle" and tlD.state(3.5)["action"] == "wave" and tlD.state(7.35)["x"] > SZ[0]
try: render.Timeline(P_, bank, {"beats": [{"t0": 0, "t1": 1, "action": "moonwalk"}]}, 3.0, SZ, .88, .4, None, "right"); raise SystemExit("bad beat action accepted")
except render.RenderError: pass
o2 = render.render_shot(A, "suit_man", None, out / "tl.mp4", duration=2.5, fps=10, size=SIZE, params=dict(pb, beats=[{"t0": 1.2, "t1": 2.0, "action": "wave", "x0": .5}]))
assert frames_in(o2) == 25; assert Path(o2).read_bytes() == Path(render.render_shot(A, "suit_man", None, out / "tl2.mp4", duration=2.5, fps=10, size=SIZE, params=dict(pb, beats=[{"t0": 1.2, "t1": 2.0, "action": "wave", "x0": .5}]))).read_bytes()
# ---- lanes (params["lane"]): clamp, avoid shifting, soft-end fades, 'none', smooth joins
TLm = lambda p_, d=8.0: render.Timeline(P_, bank, p_, d, SZ, sc.walk_y, sc.horizon, None, "right")
lane = dict(x0=.2, x1=.7, y=.85, h_hint=.42, avoid=[])
tl1 = TLm({"lane": lane, "beats": [{"t0": 0, "t1": 3, "action": "walk", "x0": .05, "x1": 1.2}, {"t0": 4, "t1": 5, "action": "wave", "x0": .9}]})
xs1 = [tl1.state(t_)["x"] / SZ[0] for t_ in np.arange(0, 8, .1)]
assert min(xs1) >= .2 - 1e-6 and max(xs1) <= .7 + 1e-6, (min(xs1), max(xs1))                 # every x clamped into the lane
assert abs(tl1.state(2.0)["y"] / SZ[1] - .85) < 1e-6 and abs(tl1.state(2.0)["h"] / SZ[1] - .42) < 1e-6   # feet row and height from the lane
ta = TLm({"lane": dict(lane, x0=0, x1=1, avoid=[[.4, .6]]), "beats": [{"t0": 0, "t1": 1, "action": "wave", "x0": .5}, {"t0": 2, "t1": 3, "action": "walk", "x0": .1, "x1": .9}]})
hw = .15 * ta.hmid * SZ[1] / SZ[0] + .01
for t_ in np.arange(0, 8, .1):
    x_ = ta.state(t_)["x"] / SZ[0]; assert not (.4 - hw + 1e-6 < x_ < .6 + hw - 1e-6), (t_, x_)    # never inside a span (grown by half a body)
assert abs(ta.state(.5)["x"] / SZ[0] - .5) > .08 and ta.state(.5)["action"] == "wave"             # the stand moved to the nearest clear x
assert ta.state(2.99)["x"] / SZ[0] < .4 - hw + 1e-3                                                  # the walk stops short of the span instead of crossing it
tf = TLm({"lane": dict(lane, x0=.55, x1=.97), "enter": "right", "exit": "right"}, 8.0)
s0 = tf.state(0.0); assert s0["alpha"] < .02 and abs(s0["x"] / SZ[0] - .97) < 1e-6              # appears AT the lane end, fading in (not off-frame, no pop)
al = [tf.state(t_)["alpha"] for t_ in np.arange(0, .5, .05)]; assert all(b >= a - 1e-9 for a, b in zip(al, al[1:])) and tf.state(.5)["alpha"] > .99 and tf.state(1.0)["x"] < s0["x"]
te_ = tf.exit_start; assert tf.state(te_ - .1)["alpha"] > .95
xe_ = [tf.state(t_)["x"] / SZ[0] for t_ in np.arange(te_, 7.4, .1)]; assert max(xe_) <= .97 + 1e-6 and tf.state(7.45)["alpha"] < .02    # walks to the lane end, then fades out there
assert all(.55 - 1e-6 <= tf.state(t_)["x"] / SZ[0] <= .97 + 1e-6 for t_ in np.arange(0, 8, .1))
th = TLm({"lane": dict(lane, x0=0, x1=1), "enter": "left", "exit": "right"}, 8.0)                  # lane reaching both frame edges: off-frame entry as before, alpha stays 1
assert th.state(0)["x"] < 0 and th.state(0)["alpha"] == 1.0 and th.state(7.9)["x"] > SZ[0]
for bad in ("none", dict(x0=.5, x1=.52)):
    try: TLm({"lane": bad}); raise SystemExit(f"lane {bad!r} accepted")
    except render.RenderError as e: assert "no usable lane" in str(e)
try: render.render_shot(A, "suit_man", None, out / "n.mp4", duration=1.0, fps=10, size=SIZE, params={"lane": "none", "enter": "left"}); raise SystemExit("lane none rendered")
except render.RenderError as e: assert "no usable lane" in str(e)
try: render.render_shot(A, "suit_man", "walk", out / "n.mp4", duration=1.0, fps=10, size=SIZE, params={"lane": "none"}); raise SystemExit("lane none rendered (legacy)")
except render.RenderError: pass
tj = TLm({"beats": [{"t0": 1, "t1": 4, "action": "walk", "x0": .2, "x1": .8}]}, 8.0)               # smooth join: stand -> walk cross-fades and eases in
j = tj.state(1.05); assert "prev" in j and 0 < j["w"] < .5 and j["prev"]["action"] == "stand_idle"
assert "prev" not in tj.state(1.4)
d1 = tj.state(1.1)["x"] - tj.state(1.0)["x"]; d2 = tj.state(2.1)["x"] - tj.state(2.0)["x"]; assert 0 <= d1 < .6 * d2                  # no velocity snap
tg = TLm({"beats": [{"t0": 1, "t1": 3, "action": "wave", "x0": .5}]}, 8.0)
assert tg.state(1.1)["t"] < 1e-6 and tg.state(1.6)["t"] > 0                                           # anticipation hold before the gesture
sm = render._mul_rgb(Image.new("RGBA", (2, 2), (200, 100, 50, 255)), render._tint_mul([.5, 1, 1])); assert sm.getpixel((0, 0)) == (100, 100, 50, 255)
o3 = render.render_shot(A, "suit_man", None, out / "lane.mp4", duration=2.5, fps=10, size=SIZE, params=dict(pb, lane=dict(x0=.5, x1=.95, y=.85, h_hint=.42, avoid=[]), enter="right", exit="right", tint=[1, .9, .8]))
assert frames_in(o3) == 25
cancelled = []
try: render.render_shot(B, "child", "walk", out / "c.mp4", duration=2.0, fps=10, size=SIZE, cancel=lambda: bool(cancelled.append(1)) or True); raise SystemExit("cancel ignored")
except render.Cancelled: pass
assert not list(render.CLIP_DIR.glob("*.part.mp4")) and not (out / "c.mp4").exists()    # nothing left behind
# errors are clear
for bad in (dict(character="nobody"), dict(action="fly"), dict(duration=0), dict(size=(321, 180)), dict(direction="up")):
    kw = dict(still_path=A, character="suit_man", action="walk", out_path=out / "e.mp4", duration=1.0, size=SIZE); kw.update(bad)
    try: render.render_shot(**kw); raise SystemExit(f"accepted {bad}")
    except render.RenderError: pass
try: render.render_transition(A, B, "suit_man", "teleport", out / "e.mp4", 1.0, size=SIZE); raise SystemExit("bad transition accepted")
except render.RenderError: pass
try: render.render_shot(TMP / "nope.png", "suit_man", "walk", out / "e.mp4", size=SIZE); raise SystemExit("missing still accepted")
except render.RenderError: pass
print("test_puppet_scene: ok", round(t_first, 2), "s first render")
