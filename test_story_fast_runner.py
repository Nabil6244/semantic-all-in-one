"""Tests for story_fast.runner / progress (stub compose). Run: python3 test_story_fast_runner.py"""
import os, sys, json, tempfile, time, shutil, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from story_fast import runner, progress

FAILS = []
def ok(name, cond, extra=""):
    if cond: print("ok", name)
    else: print("FAIL", name, extra); FAILS.append(name)

TMP = tempfile.mkdtemp(prefix="sfr_"); runner.SPEED_PATH = os.path.join(TMP, "speed.json")

class Stub:
    def __init__(self, fail=None, delay=0): self.calls = []; self.fail = fail or {}; self.delay = delay
    def job_key(self, job): return "k"
    def available_encoder(self): return "stub"
    def prepare(self, still, size, cache_dir=None): pass
    def render_shot(self, job, out, cancel=None, progress=None):
        sid = job["shot_id"]; self.calls.append((sid, job["treatment"]))
        if self.delay: time.sleep(self.delay)
        f = self.fail.get(sid)
        if f == "always": raise RuntimeError("boom")
        if isinstance(f, int) and sum(1 for c in self.calls if c[0] == sid) <= f: raise RuntimeError("boom")
        if isinstance(f, tuple) and job["treatment"] in f: raise RuntimeError("boom treat")
        with open(out, "wb") as fh: fh.write(b"x")
        return str(out)

def mkshots(n, d=3.0):
    imgs = {}; shots = []
    for i in range(n):
        p = os.path.join(TMP, f"img{i % 5}.png")
        if not os.path.exists(p): open(p, "wb").write(b"png%d" % (i % 5))
        sid = f"s{i:04d}"; imgs[sid] = p
        shots.append(dict(shot_id=sid, scene_no=i, start=i * d, end=(i + 1) * d + (0.0137 if i % 3 == 0 else 0), motion_tier="still_motion", treatment="push_in"))   # already directed: the runner must not re-direct (and drop the ai_video record)
    return shots, imgs

def fresh(stub):
    runner.set_compose(stub); runner._still_clip = lambda j, out: (open(out, "wb").write(b"s"), str(out))[1]
    return stub

# planning
shots, imgs = mkshots(6); shots[1]["motion_tier"] = "graphic"; del imgs["s0002"]; shots[3]["ai_video"] = {"kind": "x"}
S0 = {"fps": 30, "size": (960, 540)}
jobs = runner.plan_clips(shots, imgs, S0)
ok("one job per shot", len(jobs) == 6)
ok("margin 0.3", abs(jobs[0]["duration"] - jobs[0]["shot_seconds"] - 0.3) < 1e-6)
ok("graphic skip", jobs[1]["type"] == "skip" and "graphic" in jobs[1]["reason"])
ok("no picture skip", jobs[2]["type"] == "skip" and "picture" in jobs[2]["reason"])
ok("ai job", jobs[3]["type"] == "ai_video_job" and jobs[3]["ai_video"]["shot_id"] == "s0003")
ok("shot keys", all(k in jobs[0] for k in "type shot_id scene_no still duration shot_seconds fps size seed treatment tparams env intensity est_seconds".split()))
ok("treatments set", all(j["treatment"] for j in jobs))
ok("estimate", 0 < runner.estimate_total(jobs, 2) < runner.estimate_total(jobs, 1))

# render + resume
od = os.path.join(TMP, "o1"); st = fresh(Stub()); timer = progress.StageTimer(); runner.set_timer(timer); events = []
clips = runner.render_clips(jobs, od, progress=lambda *a: events.append(a))
ok("clips for non-skip", set(clips) == {"s0000", "s0003", "s0004", "s0005"} and all(os.path.getsize(p) > 0 for p in clips.values()))
ok("ai jobs file", json.load(open(os.path.join(od, "ai_video_jobs.json")))[0]["shot_id"] == "s0003")
ok("progress reaches total", events[-1][1] == events[-1][2] == 4 and events[-1][3] == 0)
ok("speed saved", os.path.exists(runner.SPEED_PATH))
n = len(st.calls); runner.render_clips(jobs, od)
ok("resume renders 0", len(st.calls) == n)
open(imgs["s0004"], "wb").write(b"changed-image-longer")
c2 = runner.plan_clips(shots, imgs, S0); runner.render_clips(c2, od)
ok("changed still re-renders only that shot (and others sharing it)", {c[0] for c in st.calls[n:]} == {s for s in ("s0004",)} | {f"s{i:04d}" for i in (0, 3, 5) if imgs[f"s{i:04d}"] == imgs["s0004"]})
n = len(st.calls); open(os.path.join(od, "s0005.mp4"), "wb").close(); runner.render_clips(c2, od)
ok("empty mp4 re-rendered", [c[0] for c in st.calls[n:]] == ["s0005"])
n = len(st.calls); open(os.path.join(od, "s0000.mp4"), "wb").write(b""); runner.render_clips(c2, od)
ok("corrupt mp4 re-rendered", [c[0] for c in st.calls[n:]] == ["s0000"])

# failure -> retry -> fallback -> still
sh, im = mkshots(4); jb = runner.plan_clips(sh, im, {"size": (960, 540)}); od = os.path.join(TMP, "o2")
st = fresh(Stub(fail={"s0000": 2, "s0001": "always", "s0002": (jb[2]["treatment"], "hold_alive")}))
r = runner.render_clips(jb, od)
ok("every shot has clip", len(r) == 4 and all(os.path.getsize(p) > 0 for p in r.values()))
ok("retry same inputs", [c for c in st.calls if c[0] == "s0000"] == [("s0000", jb[0]["treatment"])] * 3)
ok("fallback treatment", ("s0002", "push_in") in st.calls)
ok("final still clip", open(r["s0001"], "rb").read() == b"s")
ok("state records", json.load(open(os.path.join(od, "story_fast_state.json")))["shots"]["s0001"]["treatment"] == "still")

# cancel + resume
sh, im = mkshots(10); jb = runner.plan_clips(sh, im, {"size": (960, 540)}); od = os.path.join(TMP, "o3"); st = fresh(Stub())
try: runner.render_clips(jb, od, cancel=lambda: len(st.calls) >= 4); raised = False
except runner.Cancelled: raised = True
ok("cancel raises", raised and len(st.calls) == 4)
n = len(st.calls); r = runner.render_clips(jb, od)
ok("resume finishes only the rest", len(st.calls) - n == 6 and len(r) == 10)
st = fresh(Stub(delay=0.01)); od = os.path.join(TMP, "o3b")
try: runner.render_clips(jb, od, workers=3, cancel=lambda: len(st.calls) >= 3)
except runner.Cancelled: pass
n = len(st.calls); r = runner.render_clips(jb, od, workers=3); ok("parallel cancel then resume", len(r) == 10 and len(st.calls) - n <= 8)

# worker cap
runner._available_ram = lambda: 2 * 700 * (1 << 20) / 0.8 + 10
ok("worker cap by memory", runner.cap_workers(8) == 2 and runner.cap_workers(1) == 1)
runner._available_ram = lambda: 1 << 20; ok("cap min 1", runner.cap_workers(8) == 1)
runner._available_ram = lambda: 64 << 30; ok("cap not above request", runner.cap_workers(4) == 4)
live = {"n": 0, "max": 0}; lk = threading.Lock()
class Par(Stub):
    def render_shot(self, job, out, cancel=None, progress=None):
        with lk: live["n"] += 1; live["max"] = max(live["max"], live["n"])
        time.sleep(0.02)
        with lk: live["n"] -= 1
        return Stub.render_shot(self, job, out)
fresh(Par()); runner._available_ram = lambda: 3 * 175 * (1 << 20) / 0.8 + 10
runner.render_clips(jb, os.path.join(TMP, "o4"), workers=8); ok("in-flight never above cap", 2 <= live["max"] <= 3, live)
runner._available_ram = lambda: 64 << 30

# assemble 700 shots
sh, im = mkshots(700, d=2.77); sh[5]["motion_tier"] = "graphic"
cl = {s["shot_id"]: "/x/%s.mp4" % s["shot_id"] for s in sh if s["shot_id"] not in ("s0005", "s0009")}
a = runner.assemble_timeline(sh, cl, {"fps": 30}); S = a["segments"]
ok("tiles exactly", S[0]["start_frame"] == round(sh[0]["start"] * 30) and S[-1]["end_frame"] == round(sh[-1]["end"] * 30) and all(S[i]["end_frame"] == S[i + 1]["start_frame"] for i in range(len(S) - 1)))
ok("frames sum", a["frames"] == sum(g["frames"] for g in S) == S[-1]["end_frame"] - S[0]["start_frame"])
ok("kinds", S[5]["kind"] == "graphic" and S[5]["path"] is None and S[9]["kind"] == "gap" and S[0]["kind"] == "shot" and S[0]["clip_in"] == 0.0)

# progress ETA
sh, im = mkshots(12); jb = runner.plan_clips(sh, im, {"size": (960, 540)}); fresh(Stub(delay=0.03)); ev = []
runner.render_clips(jb, os.path.join(TMP, "o5"), workers=2, progress=lambda *a: ev.append(a))
etas = [e[3] for e in ev]
ok("eta ends at 0 and is sane", ev[-1][1] == ev[-1][2] == 12 and etas[-1] == 0 and etas[4] < 2)
ok("done monotone", all(b[1] >= a_[1] for a_, b in zip(ev, ev[1:])))

# timer
t = progress.StageTimer()
with t.stage("csv"): time.sleep(0.01)
t.add("flow_wait", 120.0); t.add("scene_render", 5.0)
rep = t.report(); ok("report separates flow wait", "Flow waiting time (not local work)" in rep and rep.index("Local total") < rep.index("Waiting on Google Flow"))
ok("local excludes flow", abs(t.local_seconds() - 5.01) < 0.2)
p = t.save(os.path.join(TMP, "state", "story", "bench.json")); ok("bench saved", json.load(open(p))["flow_wait_seconds"] == 120.0)
ok("stage order", progress.STAGES == ("csv", "flow_wait", "image_prep", "animation", "scene_render", "assemble"))
ok("runner fills timer", timer.counts["scene_render"] > 0 and timer.counts["image_prep"] > 0)

# 900-shot speed
sh, im = mkshots(900); t0 = time.time(); jb = runner.plan_clips(sh, im, {}); runner.assemble_timeline(sh, {j["shot_id"]: "/x" for j in jb})
ok("900 plan+assemble < 2s", time.time() - t0 < 2, time.time() - t0)

shutil.rmtree(TMP, ignore_errors=True)
if FAILS: print("FAILED:", FAILS); sys.exit(1)
print("ALL OK")

import unittest


class StoryFastRunnerChecks(unittest.TestCase):
    """The checks above run when the file is loaded; this reports them to unittest (CI), which fails a module where no test ran."""
    def test_all_checks_passed(self):
        self.assertEqual(FAILS, [])
