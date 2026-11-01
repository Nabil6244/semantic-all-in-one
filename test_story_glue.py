"""Tests for story_fast.glue (glued travel / push-through / torn wipe joins). Run: python3 test_story_glue.py"""
import os, sys, json, tempfile, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw
from story_fast import glue, runner

FAILS = []
def ok(name, cond, extra=""):
    if cond: print("ok", name)
    else: print("FAIL", name, extra); FAILS.append(name)

TMP = tempfile.mkdtemp(prefix="glue_")

def pic(i, size=(640, 360)):
    p = os.path.join(TMP, f"p{i}.png")
    if not os.path.exists(p):
        rng = np.random.default_rng(i)
        im = Image.fromarray((rng.random((size[1] // 8, size[0] // 8, 3)) * 255).astype(np.uint8)).resize(size, Image.BILINEAR)
        d = ImageDraw.Draw(im); d.rectangle([size[0] * .3, size[1] * .3, size[0] * .6, size[1] * .8], fill=(40 * (i % 6), 200, 255 - 30 * (i % 8)))
        im.save(p)
    return p

def P(text, prompt=""): return {"text": text, "prompt": prompt}

# ---- choosing joins
k = glue.choose_joins([P("Walt had a hit."), P("Oswald was popular."), P("Fans loved him."), P("But in 1928, Walt learned the truth.")])
ok("time jump -> torn wipe", k[-1] == "torn_wipe", k)
ok("plain narration -> travel right", k[0] == "travel_right", k)
k = glue.choose_joins([P("A small studio."), P("The company grew into an empire.")])
ok("rise words -> travel up", k == ["travel_up"], k)
k = glue.choose_joins([P("a"), P("b"), P("c"), P("d"), P("e"), P("f")])
ok("3 sideways travels -> the next goes up", k[:4] == ["travel_right"] * 3 + ["travel_up"], k)
k = glue.choose_joins([P("x", "a street with a cinema door"), P("Inside, the crowd waited.", "a packed cinema interior"), P("y"), P("z"), P("w")])
ok("portal in A + interior B -> push-through", k[0] == "push_through", k)
k = glue.choose_joins([P("x", "an open window")] + [P("they went inside", "a room")] * 8)
ok("push-throughs capped and spaced", k.count("push_through") <= max(1, int(glue.PUSH_MAX_SHARE * len(k))), k)
ok("never two ups in a row", all(not (a == b == "travel_up") for a, b in zip(k, k[1:])), k)
k = glue.choose_joins([P("In 1920 it began.")] + [P(f"But in {1921 + i} more.") for i in range(10)])
ok("torn wipes capped and spaced", k.count("torn_wipe") <= max(1, int(glue.TORN_MAX_SHARE * len(k))) and all(not (a == b == "torn_wipe") for a, b in zip(k, k[1:])), k)
ok("empty / single picture", glue.choose_joins([]) == [] and glue.choose_joins([P("a")]) == [])
ok("seats is not a portal or interior word", glue.choose_joins([P("x", "rows of seats"), P("y", "seated men"), P("a"), P("b"), P("c")])[0] != "push_through")

# ---- planning
def mk(n, d=3.0, graphic=(), same=()):
    shots, stills = [], []
    for i in range(n):
        shots.append(dict(shot_id=f"s{i:03d}", scene_no=i, start=i * d, end=(i + 1) * d, text="But in 1930" if i == 4 else "and then more",
                          prompt_en="", motion_tier="graphic" if i in graphic else "still_motion"))
        stills.append(pic(i - 1 if i in same else i))
    return shots, stills

shots, stills = mk(10, graphic=(6,), same=(3,))
usable = [s["motion_tier"] != "graphic" for s in shots]
segs, groups = glue.plan(shots, stills, usable, 30, (640, 360))
ok("graphic shot not glued", "s006" not in groups)
ok("every usable shot glued", all(s["shot_id"] in groups for s, u in zip(shots, usable) if u))
cov = sorted((s["start_frame"], s["end_frame"]) for s in segs.values())
ok("segments do not overlap", all(a[1] <= b[0] for a, b in zip(cov, cov[1:])), cov)
ok("segments cover their shots' frames", sum(e - s for s, e in cov) == 9 * 90, cov)
ok("same picture twice in a row = one panel", any(len(p["shots"]) == 2 for s in segs.values() for p in s["panels"]))
ok("a link only to a segment that follows", all((s["link"] is None) or s["end_frame"] in [t["start_frame"] for t in segs.values()] for s in segs.values()))
ok("time jump became a torn wipe", any(s["link"] and s["link"]["kind"] == "torn_wipe" for s in segs.values()))
shots, stills = mk(14)
segs, _ = glue.plan(shots, stills, [True] * 14, 30, (640, 360))
ok("no strip longer than MAX_PANELS", all(len(s["panels"]) <= glue.MAX_PANELS for s in segs.values()))
shots, stills = mk(3, d=0.9)
shots[1]["text"] = "But in 1931"
segs, _ = glue.plan(shots, stills, [True] * 3, 30, (640, 360))
ok("picture too short for a link -> plain cut", all(s["link"] is None or s["link"]["frames"] >= int(glue.MIN_LINK_S * 30) for s in segs.values()))
ok("summary counts every change", sum(glue.summary(glue.plan(*mk(8)[:2], [True] * 8, 30)[0]).values()) == 7)

# ---- calm speed: short pictures never make a fast move
st = [0.0, 2.0, 3.4, 5.0, 6.6, 10.0]; en = st[1:] + [13.0]
s = glue.calm_schedule(st, en, ["right"] * 5)
ok("no travel faster than MIN_TRAVEL_S", all(b - a >= glue.MIN_TRAVEL_S - 1e-6 for a, b in s.travels), s.travels)
ok("a short picture arrives at most LATE_S late", all(b - st[k + 1] <= glue.LATE_S + 1e-6 for k, (a, b) in enumerate(s.travels)), s.travels)
ok("a roomy picture arrives exactly when its words start, TRAVEL_S long", abs(s.travels[-1][1] - 10.0) < 1e-6 and abs(s.travels[-1][1] - s.travels[-1][0] - glue.TRAVEL_S) < 1e-6, s.travels)
ok("every picture rests before the camera moves on", all(a >= prev + glue.SHORT_DWELL_S - 1e-6 for prev, (a, b) in zip([0.0] + [t[1] for t in s.travels], s.travels)), s.travels)
shots, stills = mk(4, d=1.7)
shots[1]["text"] = "But in 1930 it changed"
segs, _ = glue.plan(shots, stills, [True] * 4, 30, (640, 360))
ok("no link after a picture shorter than LINK_MIN_PICTURE_S", not any(s["link"] for s in segs.values()), [(s["id"], s["link"]) for s in segs.values()])

# ---- zoom
ok("strip zoom sideways 1.16", abs(glue.strip_zoom(pic(0), (640, 360), False) - 1.16) < 1e-6)
ok("strip zoom with an up move 1.27", abs(glue.strip_zoom(pic(0), (640, 360), True) - 1.27) < 1e-6)

# ---- rendering: exact frames, no jump where the travel meets the link
def frames(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "scale=80:45,format=gray", "-f", "rawvideo", "-"], capture_output=True, timeout=120)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, 45, 80).astype(np.float32)

for kind, dirs in (("torn_wipe", ["right"]), ("push_through", ["up"])):
    seg = dict(id="t", panels=[dict(still=pic(1), start=0.0, end=1.5, shots=["a"]), dict(still=pic(2), start=1.5, end=3.0, shots=["b"])], dirs=dirs,
               start_frame=0, end_frame=60, frames=60, fps=20, size=[320, 180], seed=3,
               link=dict(kind=kind, frames=16, still_b=pic(3), vertical_b=False, dir="l"))
    out = glue.render_segment(seg, os.path.join(TMP, f"seg_{kind}.mp4"))
    f = frames(out)
    ok(f"{kind}: exact frame count", len(f) == 60, len(f))
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    j = 60 - 16 - 1
    ok(f"{kind}: no jump where the travel meets the link", d[j] < 6 * max(1.0, float(np.median(d[j - 6:j]))) and d[j] < 12, (round(float(d[j]), 2), [round(float(x), 2) for x in d[j - 4:j + 3]]))
    ok(f"{kind}: temp files cleaned", not any(n.startswith(f"seg_{kind}.mp4.") for n in os.listdir(TMP)))

# ---- runner: glued mode plans glue jobs and keeps graphics as their own jobs
shots, stills = mk(6, graphic=(2,))
imgs = {s["shot_id"]: p for s, p in zip(shots, stills)}
for s in shots: s["treatment"] = "push_in"
runner.SPEED_PATH = os.path.join(TMP, "speed.json")
jobs = runner.plan_clips(shots, imgs, {"strip": "glued", "size": (320, 180), "fps": 20})
ok("runner: glued jobs carry their segment", all(j.get("glue") for j in jobs if j["type"] == "shot"), [(j["shot_id"], j["type"], bool(j.get("glue"))) for j in jobs])
ok("runner: graphic stays a skip", [j["type"] for j in jobs if j["shot_id"] == "s002"] == ["skip"])
ok("runner: offsets start at 0 in each segment", sorted({j["glue_offset"] for j in jobs if j.get("glue") and j["strip_index"] == 0}) == [0.0])
jobs = runner.plan_clips(shots, imgs, {"size": (320, 180), "fps": 20})
ok("runner: default mode unchanged (no glue)", not any(j.get("glue") for j in jobs))

shutil.rmtree(TMP, ignore_errors=True)
if FAILS: print("FAILED:", FAILS); sys.exit(1)
print("ALL OK")

import unittest


class StoryGlueChecks(unittest.TestCase):
    """The checks above run when the file is loaded; this reports them to unittest (CI), which fails a module where no test ran."""
    def test_all_checks_passed(self):
        self.assertEqual(FAILS, [])
