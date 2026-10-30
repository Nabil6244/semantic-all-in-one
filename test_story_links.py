"""Tests for health_cinema/puppet/links.py and story_motion.py (synthetic small stills, temp caches, no external assets)."""
import os, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_cinema.puppet import links, motion, scene
import story_motion as sm

TMP = Path(tempfile.mkdtemp(prefix="linktest_"))
links.CACHE_DIR = TMP / "links"; motion.CACHE_DIR = TMP / "motion"; scene.CACHE_DIR = TMP / "scene"
SIZE = (320, 180)

def still(name, seed=1, circle=None, door=None):
    r = np.random.default_rng(seed); a = (150 + r.integers(0, 70, (144, 256, 1))).repeat(3, 2).astype(np.uint8)
    im = Image.fromarray(a); d = ImageDraw.Draw(im)
    for i in range(10): d.rectangle([i * 24, 30 + i * 4, i * 24 + 16, 120], outline=(70, 50, 40))
    if circle: d.ellipse([circle[0] - 18, circle[1] - 18, circle[0] + 18, circle[1] + 18], fill=(25, 20, 18))
    if door: d.rectangle([door[0], 60, door[0] + 22, 122], fill=(15, 12, 10))
    p = TMP / name; im.save(p); return str(p)

def nframes(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", p], capture_output=True, text=True).stdout
    return int(out.strip().split(",")[0])

def leftovers():
    return [p for d in (links.CACHE_DIR, TMP) if d.exists() for p in d.glob("*.part*")]

A = still("a.png", 1, circle=(120, 70), door=(200, 0)); B = still("b.png", 2, circle=(130, 75), door=(40, 0)); C = still("c.png", 3)

# ---- every kind: frame count, no audio, determinism, cache hit
for kind in links.KINDS:
    o = links.render_link(A, B, kind, TMP / f"{kind}1.mp4", duration=1.0, fps=24, size=SIZE, seed=3)
    assert nframes(o) == 24, (kind, nframes(o))
    assert b"audio" not in subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", o], capture_output=True).stdout
    o2 = links.render_link(A, B, kind, TMP / f"{kind}2.mp4", duration=1.0, fps=24, size=SIZE, seed=3)
    assert Path(o).read_bytes() == Path(o2).read_bytes(), kind
n = len(list(links.CACHE_DIR.glob("*.mp4")))
links.render_link(A, B, "whip", TMP / "again.mp4", duration=1.0, fps=24, size=SIZE, seed=3)
assert len(list(links.CACHE_DIR.glob("*.mp4"))) == n                      # cache hit: nothing new rendered
links.render_link(A, B, "whip", TMP / "other_seed.mp4", duration=1.0, fps=24, size=SIZE, seed=4)
assert len(list(links.CACHE_DIR.glob("*.mp4"))) == n + 1                  # other seed, new entry
r1, _ = links.make_rig(A, B, "torn_wipe", 1.0, 24, SIZE, 5); r2, _ = links.make_rig(A, B, "torn_wipe", 1.0, 24, SIZE, 5)
assert np.array_equal(r1.frame(7), r2.frame(7))
# the cache key covers the source of puppet/*.py and both stills
assert links._key(A, B, "whip", 1.0, 24, SIZE, 3, {}) != links._key(B, A, "whip", 1.0, 24, SIZE, 3, {})

# ---- first frame looks like A, last like B (no flash at either end)
for kind in links.KINDS:
    rig, info = links.make_rig(A, B, kind, 1.0, 24, SIZE, 1)
    f0, f1 = rig.frame(0).astype(float), rig.frame(rig.n - 1).astype(float)
    ra, _ = links.make_rig(A, A, "dissolve_alive", 1.0, 24, SIZE, 1); rb, _ = links.make_rig(B, B, "dissolve_alive", 1.0, 24, SIZE, 1)
    da = np.abs(f0 - ra.frame(0)).mean(); db = np.abs(f1 - rb.frame(rb.n - 1)).mean()
    assert da < 22, (kind, "start is not A", da)
    assert db < 22, (kind, "end is not B", db)

# ---- no empty borders / flashes: border strips stay as bright as the picture, no frame jumps in brightness
for kind in links.KINDS:
    rig, info = links.make_rig(A, B, kind, 1.0, 24, SIZE, 2); prev = None
    for k in range(rig.n):
        f = rig.frame(k).astype(float); m = f.mean()
        edges = np.concatenate([f[:3].reshape(-1, 3), f[-3:].reshape(-1, 3), f[:, :3].reshape(-1, 3), f[:, -3:].reshape(-1, 3)]).mean()
        if kind != "push_through": assert edges > .55 * m and edges > 70, (kind, k, edges, m)     # push_through goes through a dark bridge on purpose
        if prev is not None: assert abs(m - prev) < (70 if kind == 'push_through' else 38), (kind, k, "brightness flash", m, prev)
        prev = m

# ---- cancel / cleanup
cnt = {"n": 0}
def cancel_after_3():
    cnt["n"] += 1; return cnt["n"] > 4
dst = TMP / "cancelled.mp4"
try: links.render_link(A, C, "push_through", dst, duration=1.0, fps=24, size=SIZE, seed=9, cancel=cancel_after_3); raise SystemExit("cancel did not raise")
except links.Cancelled: pass
assert not dst.exists() and not leftovers(), leftovers()
assert not list(links.CACHE_DIR.glob(f"{links._key(A, C, 'push_through', 1.0, 24, SIZE, 9, {})}.mp4"))
for bad in (dict(kind="nope"), dict(kind="whip", duration=0)):
    try: links.render_link(A, B, bad["kind"], TMP / "bad.mp4", duration=bad.get("duration", 1.0), fps=24, size=SIZE); raise SystemExit("no error")
    except links.LinkError: pass

# ---- match cut: shared blob found; no shared feature -> clear fallback to dissolve_alive; points can be given
r = links.resolve_link(A, B, "match_cut"); assert r["kind"] == "match_cut" and r["ok"] and r["feature"] in ("blob", "horizon"), r
N1 = TMP / "n1.png"; N2 = TMP / "n2.png"
rr = np.random.default_rng(4); Image.fromarray((150 + rr.integers(0, 6, (144, 256, 1))).repeat(3, 2).astype(np.uint8)).save(N1)
Image.fromarray((160 + rr.integers(0, 6, (144, 256, 1))).repeat(3, 2).astype(np.uint8)).save(N2)
f = links.resolve_link(str(N1), str(N2), "match_cut"); assert f["fallback"] and f["kind"] == "dissolve_alive", f
o = links.render_link(str(N1), str(N2), "match_cut", TMP / "fb.mp4", duration=1.0, fps=24, size=SIZE); assert nframes(o) == 24
g = links.resolve_link(A, B, "match_cut", {"points": ((.4, .4), (.6, .5))}); assert g["feature"] == "given" and g["a"] == (.4, .4)
# push_through finds the door in A and a point in B
p = links.resolve_link(A, B, "push_through"); assert 0 <= p["point_a"][0] <= 1 and p["source"] in ("door", "dark_blob", "centre", "given"), p
p2 = links.resolve_link(A, B, "push_through", {"point_a": (.3, .5), "point_b": (.7, .5)}); assert p2["point_a"] == (.3, .5) and p2["source"] == "given"

# ---- estimate
assert links.estimate_seconds("push_through", 1.2, 30, (1920, 1080)) > links.estimate_seconds("push_through", 1.2, 30, (960, 540)) > 0

# ================================================================== story_motion
ST = dict(size=SIZE, fps=24, seed=1, link_seconds=1.0, margin=.5)
def mk(sid, s, e, tier="still_motion", cam="push_in", tin="cut", link=None, no=None):
    return dict(shot_id=sid, scene_no=no or int(sid[1:]), start=s, end=e, text="t", subject="x", prompt_en="p", picture="new", character=False, motion_tier=tier, camera=cam, transition_in=tin, link_to_next=link)
imgs = {1: A, 2: B, 3: C, 4: A, 5: B}
shots = [mk("s1", 0.0, 3.0, "link", "push_in", "cut", {"kind": "torn_wipe", "note": ""}), mk("s2", 3.0, 5.43, "still_motion", "drift_l", "torn_wipe", None),
         mk("s3", 5.43, 8.0, "graphic"), mk("s4", 8.0, 10.5, "ai_video", "pull_out"), mk("s5", 10.5, 12.0, "puppet", "hold_alive", "dissolve")]
jobs = sm.plan_clips(shots, imgs, ST)
types = {j["shot_id"]: j["type"] for j in jobs}
assert types["s1"] == "motion" and types["s3"] == "skip" and types["s4"] == "ai_video_job" and types["s5"] == "puppet", types
assert "s1+link" in types and types["s1+link"] == "link" and [j for j in jobs if j["shot_id"] == "s1+link"][0]["kind"] == "torn_wipe"
assert "s2+link" not in types                                    # graphic neighbour: no link
av = sm.ai_video_jobs(jobs); assert len(av) == 1 and av[0]["shot_id"] == "s4" and av[0]["seconds"] == 2.5 and av[0]["first_picture"] == A and av[0]["last_picture"] == B and av[0]["prompt"] == "p"
assert [j for j in jobs if j["shot_id"] == "s1"][0]["duration"] == 3.5     # shot length + 0.5 margin
assert [j for j in jobs if j["shot_id"] == "s5"][0]["params"]["intensity"] == "low"
assert all(j["est_seconds"] >= 0 for j in jobs) and sm.estimate_total(jobs) > 0 and sm.estimate_total(jobs, workers=2) < sm.estimate_total(jobs)
# time budget drops links
tight = sm.plan_clips(shots, imgs, dict(ST, time_budget_s=1.0)); assert [j for j in tight if j["shot_id"] == "s1+link"][0]["type"] == "skip"

# render a small real set (tiny size) with the puppet tier injected and the ai_video fallback
logs = []; calls = []
def puppet(job): calls.append(job["shot_id"]); return str(sm._run_motion(job, TMP / "clips", None))
paths = sm.render_clips(jobs, TMP / "clips", logs.append, None, workers=2, puppet_renderer=puppet)
assert set(paths) == {"s1", "s2", "s4", "s5", "s1+link", "s4+link"} or set(paths) >= {"s1", "s2", "s4", "s5", "s1+link"}, set(paths)
assert calls == ["s5"] and "s3" not in paths
assert nframes(paths["s1+link"]) == 24 and nframes(paths["s1"]) == round(3.5 * 24)
tl = sm.assemble_timeline(shots, paths, ST)
assert tl["frames"] == round(12.0 * 24) and abs(tl["seconds"] - 12.0) < 1e-9, tl["frames"]
pos = tl["segments"][0]["start_frame"]
for s_ in tl["segments"]:
    assert s_["start_frame"] == pos and s_["frames"] > 0; pos = s_["end_frame"]
assert pos == round(12.0 * 24)
kinds = [(s_["kind"], s_["shot_id"]) for s_ in tl["segments"]]
assert ("link", "s1+link") in kinds and ("graphic", "s3") in kinds, kinds
lk = [s_ for s_ in tl["segments"] if s_["kind"] == "link"][0]; s2 = [s_ for s_ in tl["segments"] if s_["shot_id"] == "s2"][0]
assert lk["frames"] == 24 and s2["clip_in"] == .5                                  # half the link comes out of s2's head
# the cancel flag reaches render_clips
try: sm.render_clips(jobs, TMP / "clips2", None, lambda: True); raise SystemExit("no cancel")
except sm.Cancelled: pass
assert not leftovers()

# ---- timeline rule on awkward fractional times, including a shot too short for its link
import random
rng = random.Random(7)
for trial in range(40):
    t = 0.0; sh = []
    for i in range(rng.randint(2, 7)):
        L = rng.choice([.5, .9, 1.3, 2.4, 3.17, 4.0]); sh.append(mk(f"x{i}", round(t, 3), round(t + L, 3), "link", "push_in", "cut", {"kind": "whip", "note": ""})); t += L
    fake = {}
    for i, s_ in enumerate(sh):
        fake[s_["shot_id"]] = f"/x/{s_['shot_id']}.mp4"
        if i + 1 < len(sh): fake[s_["shot_id"] + "+link"] = f"/x/{s_['shot_id']}+link.mp4"
    tl = sm.assemble_timeline(sh, fake, dict(fps=30, link_seconds=1.2))
    assert tl["frames"] == round(sh[-1]["end"] * 30) - 0, (trial, tl["frames"])
    pos = 0
    for s_ in tl["segments"]: assert s_["start_frame"] == pos and s_["frames"] > 0; pos = s_["end_frame"]
    for s_ in tl["segments"]:
        if s_["kind"] == "shot": assert s_["frames"] >= .4 * 30 - 1, (trial, s_)
print("OK story links", TMP)


import unittest


class Ran(unittest.TestCase):
    def test_the_script_above_ran_to_the_end(self):      # its checks run (and assert) when the module is imported
        self.assertTrue(TMP)
