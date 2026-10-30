"""story_fast.animate with a stub animator (no Flow, no network). Run: python3 -m unittest test_story_animate -v"""
import json
import os
import subprocess
import tempfile
import time
import unittest

from story_fast import animate as an


def _ff(*a):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)


def _png(path, color="red"):
    _ff("-f", "lavfi", "-i", f"color=c={color}:s=640x360:d=0.1", "-frames:v", "1", path)


def _mp4(path, secs, size="1280x720", fps=24):
    _ff("-f", "lavfi", "-i", f"testsrc=s={size}:r={fps}:d={secs}", "-pix_fmt", "yuv420p", path)


class Stub:
    def __init__(self, mode="ok", secs=5.0):
        self.mode, self.secs, self.calls, self.cancelled = mode, secs, [], False

    def animate(self, image, prompt, seconds, out_path, should_stop):
        self.calls.append((image, prompt, seconds))
        if self.mode == "quota":
            raise RuntimeError("Quota exceeded for today")
        if self.mode == "hold":
            raise RuntimeError("unusual activity detected")
        if self.mode == "hang":
            while not should_stop():
                time.sleep(0.05)
            raise RuntimeError("stopped")
        _mp4(out_path, self.secs)
        return out_path

    def cancel(self):
        self.cancelled = True


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.addCleanup(self.d.cleanup); self.dir = self.d.name
        self.pics = {}
        for i, c in enumerate(("red", "blue", "green", "yellow")):
            p = os.path.join(self.dir, f"s{i}.png"); _png(p, c); self.pics[f"s{i}"] = p
        self.clips = {k: os.path.join(self.dir, f"{k}_local.mp4") for k in self.pics}

    def job(self, sid, prompt="A man walks across the street", dur=3.3, prio=2.0, typ="ai_video_job"):
        return dict(shot_id=sid, type=typ, still=self.pics[sid], duration=dur, shot_seconds=dur - 0.3, fps=30, size=(1920, 1080), treatment="push_in",
                    ai_video=dict(reason="real movement", prompt=prompt, seconds=3.0, priority=prio, shot_id=sid, first_picture=self.pics[sid]))

    def out(self):
        o = os.path.join(self.dir, "clips"); os.makedirs(o, exist_ok=True); return o

    def recs(self):
        return {r["shot_id"]: r for r in json.loads(open(os.path.join(self.out(), "ai_video_jobs.json")).read())}

    def run_(self, jobs, st, animator, cancel=None):
        return an.animate_jobs(jobs, dict(self.clips), self.out(), st, animator=animator, cancel=cancel)

    def test_gate_off_never_submits_and_reports(self):
        stub = Stub(); jobs = [self.job("s0"), self.job("s1")]
        r = self.run_(jobs, {}, stub)
        self.assertEqual(stub.calls, []); self.assertEqual(r["clips"], self.clips)
        self.assertEqual(r["report"]["would_animate"], 2); self.assertIn("would animate 2 shots", r["report"]["text"])
        self.assertEqual(self.recs()["s0"]["status"], "dry_run")

    def test_success_and_exact_duration(self):
        stub = Stub(secs=5.0); r = self.run_([self.job("s0", dur=3.3)], {"story_ai_video_live": True}, stub)
        p = r["clips"]["s0"]; self.assertNotEqual(p, self.clips["s0"])
        self.assertEqual(an.frame_count(p), 99)                       # 3.3 s * 30 fps, frame exact
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "1920,1080,30/1"); self.assertEqual(self.recs()["s0"]["status"], "animated")
        self.assertEqual(stub.calls[0][2], 4)                          # smallest Flow length covering the shot
        self.assertIn("Same character", stub.calls[0][1])

    def test_short_source_is_stretched_and_held_to_length(self):
        r = self.run_([self.job("s0", dur=6.3)], {"story_ai_video_live": True}, Stub(secs=4.0))
        self.assertEqual(an.frame_count(r["clips"]["s0"]), 189)

    def test_cache_hit_does_not_resubmit(self):
        st = {"story_ai_video_live": True}; jobs = [self.job("s0")]
        self.run_(jobs, st, Stub()); stub2 = Stub(); r = self.run_(jobs, st, stub2)
        self.assertEqual(stub2.calls, []); self.assertEqual(self.recs()["s0"]["status"], "cached"); self.assertEqual(r["report"]["cached"], 1)
        self.assertEqual(an.frame_count(r["clips"]["s0"]), 99)

    def test_changed_prompt_is_a_new_request(self):
        st = {"story_ai_video_live": True}
        self.run_([self.job("s0")], st, Stub()); stub2 = Stub(); self.run_([self.job("s0", prompt="A man runs")], st, stub2)
        self.assertEqual(len(stub2.calls), 1)

    def test_quota_falls_back_and_stops_submitting(self):
        stub = Stub("quota"); r = self.run_([self.job("s0"), self.job("s1")], {"story_ai_video_live": True}, stub)
        self.assertEqual(len(stub.calls), 1); self.assertEqual(r["clips"], self.clips)
        rc = self.recs(); self.assertEqual(rc["s0"]["reason"], "quota"); self.assertEqual(rc["s0"]["fallback"], "local camera clip")
        self.assertEqual(rc["s1"]["status"], "skipped"); self.assertEqual(r["report"]["stopped_early"], "quota")

    def test_hold_is_classified(self):
        r = self.run_([self.job("s0")], {"story_ai_video_live": True}, Stub("hold"))
        self.assertEqual(self.recs()["s0"]["reason"], "hold"); self.assertEqual(r["clips"], self.clips)

    def test_timeout_keeps_local_clip_and_does_not_resend_blindly(self):
        stub = Stub("hang"); st = {"story_ai_video_live": True, "story_ai_video_timeout": 0.5}
        r = self.run_([self.job("s0")], st, stub)
        self.assertEqual(self.recs()["s0"]["reason"], "timeout"); self.assertTrue(stub.cancelled); self.assertEqual(r["clips"], self.clips)
        stub2 = Stub(); self.run_([self.job("s0")], st, stub2)         # a sent-but-unanswered request may have billed: not sent again
        self.assertEqual(stub2.calls, []); self.assertEqual(self.recs()["s0"]["status"], "unknown")
        stub3 = Stub(); self.run_([self.job("s0")], dict(st, story_ai_video_resubmit=True), stub3)
        self.assertEqual(len(stub3.calls), 1)

    def test_cancel_stops_promptly(self):
        stub = Stub("hang"); flag = {"c": False}
        import threading
        threading.Timer(0.4, lambda: flag.update(c=True)).start()
        t = time.time(); r = self.run_([self.job("s0"), self.job("s1")], {"story_ai_video_live": True}, stub, cancel=lambda: flag["c"])
        self.assertLess(time.time() - t, 6); self.assertTrue(r["report"]["cancelled"]); self.assertEqual(len(stub.calls), 1)
        self.assertEqual(r["clips"], self.clips); self.assertEqual(self.recs()["s0"]["status"], "cancelled")

    def test_budget_and_ranking_prefer_character_action(self):
        jobs = [self.job("s0", prompt="Waves roll over the beach", prio=9.0), self.job("s1", prompt="A woman turns and runs", prio=1.0),
                self.job("s2", prompt="The train leaves the station", prio=5.0)]
        stub = Stub(); r = self.run_(jobs, {"story_ai_video_live": True, "story_ai_video_live_max": 2}, stub)
        self.assertEqual(r["report"]["shots"], ["s1", "s2"]); self.assertEqual(len(stub.calls), 2)
        self.assertEqual(self.recs()["s0"]["status"], "not_selected")

    def test_non_ai_jobs_untouched(self):
        stub = Stub(); r = self.run_([self.job("s0", typ="shot")], {"story_ai_video_live": True}, stub)
        self.assertEqual(stub.calls, []); self.assertEqual(r["clips"], self.clips)

    def test_default_flow_animator_refuses_without_engine_support(self):
        r = self.run_([self.job("s0")], {"story_ai_video_live": True}, None)
        self.assertEqual(self.recs()["s0"]["reason"], "unsupported"); self.assertEqual(r["clips"], self.clips)

    def test_continuity_seed_uses_last_frame_of_previous_clip(self):
        j0 = self.job("s0"); j0["ai_video"].update(seed_next=True, next_shot_id="s1"); j1 = self.job("s1")
        stub = Stub(); self.run_([j0, j1], {"story_ai_video_live": True}, stub)
        self.assertTrue(stub.calls[1][0].endswith("_last.png"))

    def test_bad_file_from_animator(self):
        class Bad(Stub):
            def animate(self, image, prompt, seconds, out_path, should_stop):
                with open(out_path, "wb") as f:
                    f.write(b"not a video")
                return out_path
        r = self.run_([self.job("s0")], {"story_ai_video_live": True}, Bad())
        self.assertEqual(self.recs()["s0"]["status"], "failed"); self.assertEqual(r["clips"], self.clips)


if __name__ == "__main__":
    unittest.main()
