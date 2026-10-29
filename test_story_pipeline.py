"""Tests for story_pipeline: remap helpers on fake data, build_story with fake step modules (cache / resume / cancel / missing modules), and one tiny
end-to-end render (6 fake clips over 20 s) through applied_story + the real vg.render_video, checked with story_audit.
Run: python3 -m unittest test_story_pipeline -v   (the render part takes ~20 s)"""
import contextlib
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np

import story_audit
import story_pipeline as sp

COLORS = [(220, 40, 40), (40, 200, 60), (50, 80, 230), (230, 220, 40), (210, 50, 200), (40, 210, 220)]
SHOT_STARTS = [0.0, 3.0, 6.5, 10.0, 14.0, 17.0]          # 6 shots, 20 s
SCENE_STARTS = [0.0, 6.5, 14.0]                          # 3 scenes: shots 0-1, 2-3, 4-5


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", *args], check=True, timeout=120)


def _fake_shots():
    shots = []
    for i, st in enumerate(SHOT_STARTS):
        en = SHOT_STARTS[i + 1] if i + 1 < len(SHOT_STARTS) else 20.0
        shots.append({"shot_id": f"sh{i}", "scene_no": i // 2 + 1, "start": st, "end": en, "text": f"shot {i} words", "motion_tier": 2,
                      "transition_in": "dissolve" if i == 3 else "cut", "character": "fox"})
    return shots


def _units(audio_end=20.0, timeline=None, clips=None):
    return sp.build_units(sp.tile_shots(_fake_shots(), audio_end), timeline, clips, audio_end)


class Remap(unittest.TestCase):
    def test_tile_closes_gaps_and_overlaps(self):
        shots = [{"shot_id": "a", "start": 0.4, "end": 2.0}, {"shot_id": "b", "start": 2.5, "end": 4.0}, {"shot_id": "c", "start": 3.8, "end": 6.0},
                 {"shot_id": "tiny", "start": 6.0, "end": 6.05}]
        t = sp.tile_shots(shots, 8.0)
        self.assertEqual([s["shot_id"] for s in t], ["a", "b", "c"])           # tiny merged away
        self.assertEqual(t[0]["start"], 0.0)
        for a, b in zip(t, t[1:]):
            self.assertAlmostEqual(a["end"], b["start"])
        self.assertEqual(t[-1]["end"], 8.0)

    def test_units_without_timeline_and_with_link_segments(self):
        u = _units()
        self.assertEqual([x["kind"] for x in u], ["shot"] * 6)
        self.assertEqual([x["_ix"] for x in u], list(range(6)))
        tl = {"segments": [
            {"kind": "shot", "shot_id": "sh0", "path": "a.mp4", "start": 0.0, "end": 3.0, "clip_in": 0.0},
            {"kind": "shot", "shot_id": "sh1", "path": "b.mp4", "start": 3.0, "end": 5.9, "clip_in": 0.0},
            {"kind": "link", "shot_id": "sh1+link", "path": "l.mp4", "start": 5.9, "end": 7.1, "clip_in": 0.0},
            {"kind": "shot", "shot_id": "sh2", "path": "c.mp4", "start": 7.1, "end": 10.0, "clip_in": 0.6},
            {"kind": "gap", "shot_id": "sh3", "path": None, "start": 10.0, "end": 14.0, "clip_in": 0.0},
            {"kind": "shot", "shot_id": "sh4", "path": "e.mp4", "start": 14.0, "end": 17.0, "clip_in": 0.0},
            {"kind": "shot", "shot_id": "sh5", "path": "f.mp4", "start": 17.0, "end": 19.9, "clip_in": 0.0}]}
        u = sp.build_units(sp.tile_shots(_fake_shots(), 20.0), tl, None, 20.0)
        self.assertEqual(len(u), 7)
        self.assertEqual(u[2]["kind"], "link")
        self.assertEqual(u[2]["text"], "shot 1 words")                          # a link keeps the text of the shot it leaves
        self.assertIsNone(u[2]["transition_in"])
        self.assertIsNone(u[3]["transition_in"])                               # the unit after a link: the link is the transition
        self.assertEqual(u[4]["transition_in"], "dissolve")
        self.assertEqual(u[3]["clip_in"], 0.6)
        self.assertEqual(u[0]["start"], 0.0)
        self.assertEqual(u[-1]["end"], 20.0)                                   # the last unit is stretched to audio_end

    def test_rows_and_ids(self):
        u = _units()
        scenes = [{"scene_number": str(n), "script_segment": f"scene {n}", "prompt": "p"} for n in (1, 2, 3)]
        rows = sp.shot_rows(u, scenes)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["scene_number"], "100001")
        self.assertTrue(all(sp.is_synthetic(r["scene_number"]) for r in rows))
        self.assertFalse(sp.is_synthetic("37"))
        self.assertEqual(rows[2]["_parent_scene"], "2")
        self.assertEqual(rows[4]["start_time"], 14.0)
        self.assertEqual(rows[1]["script_segment"], "shot 1 words")

    def test_transitions_camera(self):
        u = _units()
        tr = sp.expand_transitions({"1": "fade", "3": "flash"}, u)
        # scene 1 -> first unit; scene 3 -> unit 4; unit 3 has its own dissolve; other later units are hard cuts
        self.assertEqual(tr, {"100001": "fade", "100004": "dissolve", "100005": "flash"})
        cam = sp.expand_camera({"2": "push_in"}, u)
        self.assertEqual(cam, {"100003": "push_in", "100004": "push_in"})
        u[1]["camera"] = "pull_out"
        self.assertEqual(sp.expand_camera({"1": "push_in"}, u)["100002"], "pull_out")

    def test_text_effects_rebased_by_absolute_time(self):
        u = _units()
        old_win = [(0.0, 6.5), (6.5, 14.0), (14.0, 20.0)]
        fx = [[{"text": "A", "start": 4.0, "end": 5.0, "local_start": 4.0, "local_end": 5.0, "scene_number": "1"}],
              [{"text": "B", "start": 11.0, "end": 12.5, "local_start": 4.5, "local_end": 6.0, "scene_number": "2"}],
              [{"text": "C", "local_start": 1.0, "local_end": 2.0}]]            # no absolute times: old window start + local
        out = sp.expand_text_effects(fx, old_win, u)
        self.assertEqual([len(x) for x in out], [0, 1, 0, 1, 1, 0])
        a = out[1][0]
        self.assertAlmostEqual(a["local_start"], 1.0)                           # 4.0 - unit 1 start 3.0
        self.assertAlmostEqual(a["local_end"], 2.0)
        self.assertEqual(a["scene_number"], "100002")
        self.assertAlmostEqual(out[3][0]["local_start"], 1.0)                   # 11.0 - 10.0
        self.assertAlmostEqual(out[4][0]["local_start"], 1.0)                   # 14.0+1.0 - 14.0, from the old window start
        o2 = sp.expand_text_effects([[{"text": "L", "start": 5.0, "end": 9.0}]], [(0.0, 6.5)], u)
        self.assertAlmostEqual(o2[1][0]["local_end"], 3.5)                      # cut at the end of unit 1 (6.5 - 3.0)

    def test_edit_decisions(self):
        u = _units()
        dec = {"2": {"strategy": "MULTI_SHOT", "shots": [{}, {}], "broll": [{"overlay_start": 4.0, "overlay_duration": 1.0, "source_path": "x.mp4"}]}}
        out = sp.expand_edit_decisions(dec, {"2": (6.5, 14.0)}, u, clip_units=[0, 1, 2])
        self.assertEqual(out["100001"]["strategy"], "HOLD_TAIL")
        self.assertNotIn("strategy", out["100004"])                                       # unit 3 is not a clip unit
        self.assertNotIn("shots", out["100003"])                                          # the old multi-shot decision is dropped
        self.assertAlmostEqual(out["100004"]["broll"][0]["overlay_start"], 0.5)           # 6.5 + 4.0 = 10.5 -> unit 3 (10.0..14.0)


def _fake_modules(counter, shots=None):
    """Injects fake story_align / shot_director / story_character / story_motion into sys.modules; returns the originals to restore.
    story_motion keeps the REAL assemble_timeline (frame-exact tiling with link tails/heads); planning and clip rendering are faked."""
    import story_motion as real_motion
    saved = {}

    def put(name, mod):
        saved[name] = sys.modules.get(name, "absent")
        sys.modules[name] = mod

    align = types.ModuleType("story_align")

    def align_story(rows, words, **kw):
        counter["align"] = counter.get("align", 0) + 1
        aligned = [dict(r, start_time=SCENE_STARTS[i], end_time=(SCENE_STARTS[i + 1] if i + 1 < len(SCENE_STARTS) else 20.0), confidence=1.0) for i, r in enumerate(rows)]
        return aligned, 20.0, {"ok": True}
    align.align_story = align_story
    put("story_align", align)

    sd = types.ModuleType("shot_director")

    def plan_shots(scenes, words=None, settings=None, log=print):
        counter["shots"] = counter.get("shots", 0) + 1
        return {"protagonist": {"name": "fox", "look": "red fox", "reference_key": "fox"}, "shots": [dict(s) for s in (shots or _fake_shots())], "stats": {}}
    sd.plan_shots = plan_shots
    put("shot_director", sd)

    sc = types.ModuleType("story_character")

    def plan_generation(shots, protagonist=None, budget=None, **kw):
        counter["gen"] = counter.get("gen", 0) + 1
        return {"counts": {"images": 2, "reference_images": 1, "flow_runs": 3}}
    sc.plan_generation = plan_generation
    put("story_character", sc)

    sm = types.ModuleType("story_motion")

    def plan_clips(shots, images, settings=None):
        counter["plan_clips"] = counter.get("plan_clips", 0) + 1
        jobs = []
        for s in shots:
            jobs.append({"shot_id": s["shot_id"], "type": "motion", "start": s["start"], "end": s["end"], "est_seconds": 1.5})
            if s["shot_id"] == "sh1":
                jobs.append({"shot_id": "sh1+link", "type": "link", "est_seconds": 2.0})
        return jobs

    def render_clips(jobs, out_dir, log=None, cancel=None, workers=1, puppet_renderer=None):
        counter["render_clips"] = counter.get("render_clips", 0) + 1
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        res, i = {}, 0
        for j in jobs:
            if j["type"] == "link":
                r, g, b, dur = 128, 128, 128, 1.2
                p = out_dir / "sh1+link.mp4"
            else:
                r, g, b = COLORS[i]
                dur = j["end"] - j["start"] + 0.5
                p = out_dir / f"{j['shot_id']}.mp4"
                i += 1
            _ff("-f", "lavfi", "-i", f"color=c=0x{r:02x}{g:02x}{b:02x}:s=320x180:r=30:d={dur:.2f}", "-f", "lavfi", "-i", f"color=c=white:s=80x60:r=30:d={dur:.2f}",
                "-filter_complex", "[0][1]overlay=x='mod(t*90,240)':y=60", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", str(p))
            res[j["shot_id"]] = str(p)
        return res
    sm.plan_clips, sm.render_clips, sm.assemble_timeline = plan_clips, render_clips, real_motion.assemble_timeline
    put("story_motion", sm)
    return saved


def _restore(saved):
    for k, v in saved.items():
        if v == "absent":
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


def _make_project(root: Path) -> Path:
    proj = root / "proj"
    (proj / "csv").mkdir(parents=True)
    (proj / "assets").mkdir()
    (proj / "audio").mkdir()
    with open(proj / "csv" / "visual_plan.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scene_number", "script_segment", "asset_type", "prompt"])
        for n in (1, 2, 3):
            w.writerow([n, f"scene {n} words go here", "image", "a picture"])
    for n in (1, 2, 3):
        _ff("-f", "lavfi", "-i", "color=c=gray:s=320x180:d=1", "-frames:v", "1", str(proj / "assets" / f"{n:03d}.png"))
    _ff("-f", "lavfi", "-i", "sine=f=220:d=20", "-c:a", "libmp3lame", str(proj / "audio" / "vo.mp3"))
    return proj


WORDS = [[f"w{i}", i * 0.5, i * 0.5 + 0.4] for i in range(40)]


class BuildStory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proj = _make_project(self.root)
        self.counter = {}
        self.saved = _fake_modules(self.counter)
        self.settings = {"words": WORDS, "audio_end": 20.0, "story_video": True}

    def tearDown(self):
        _restore(self.saved)
        self.tmp.cleanup()

    def test_dry_run_plans_but_renders_nothing_and_caches(self):
        run = sp.build_story(self.proj, self.settings, log=lambda m: None, dry_run=True)
        self.assertEqual({k: v.status for k, v in run.steps.items()},
                         {"inputs": "done", "align": "done", "shots": "done", "generate": "done", "clips": "done", "audit": "done"})
        self.assertEqual(len(run.shots), 6)
        self.assertNotIn("render_clips", self.counter)                 # dry run: jobs planned, nothing rendered
        self.assertEqual(run.clips, {})
        self.assertIn("would generate", run.report())
        self.assertIn("new pictures (Flow, free) 2", run.report())
        self.assertTrue((self.proj / "state" / "story" / "shots.json").is_file())
        # second run: every step cached, no module called again (resumable)
        before = dict(self.counter)
        run2 = sp.build_story(self.proj, self.settings, log=lambda m: None, dry_run=True)
        self.assertEqual([run2.steps[k].status for k in ("align", "shots", "generate", "clips")], ["cached"] * 4)
        self.assertEqual(self.counter, before)
        # a changed story setting invalidates the shots (and what depends on them) but not the alignment
        run3 = sp.build_story(self.proj, dict(self.settings, story_pace="fast"), log=lambda m: None, dry_run=True)
        self.assertEqual(run3.steps["align"].status, "cached")
        self.assertEqual(run3.steps["shots"].status, "done")

    def test_cancel_stops_between_steps(self):
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 3            # inputs, align, shots run; generate is cancelled
        run = sp.build_story(self.proj, self.settings, log=lambda m: None, cancel=cancel, dry_run=True)
        self.assertTrue(run.cancelled)
        self.assertEqual(run.steps["generate"].status, "cancelled")
        self.assertNotIn("clips", run.steps)
        self.assertEqual(len(run.shots), 6)

    def test_missing_modules_degrade(self):
        saved = {}
        for n in ("shot_director", "story_character", "story_motion", "health_cinema.puppet.story_motion"):
            saved[n] = sys.modules.get(n)
            sys.modules[n] = None            # import raises ImportError -> module "missing"
        try:
            run = sp.build_story(self.proj, self.settings, log=lambda m: None, dry_run=True)
        finally:
            for n, v in saved.items():
                sys.modules[n] = v
        self.assertEqual(run.steps["shots"].status, "done")
        self.assertIn("one shot per scene", run.steps["shots"].note)
        self.assertEqual(run.steps["generate"].status, "skipped")
        self.assertEqual(run.steps["clips"].status, "skipped")
        self.assertFalse(run.usable())                                   # nothing to apply: the render stays as it is

    def test_app_aligned_rows_are_used_as_given(self):
        aligned = [{"scene_number": str(i + 1), "script_segment": "x", "start_time": st, "end_time": st + 5.0} for i, st in enumerate(SCENE_STARTS)]
        run = sp.build_story(self.proj, dict(self.settings, aligned=aligned), log=lambda m: None, dry_run=True)
        self.assertNotIn("align", self.counter)
        self.assertEqual(run.aligned[1]["start_time"], 6.5)

    def test_no_transcript_is_a_skip_not_a_crash(self):
        run = sp.build_story(self.proj, {}, log=lambda m: None, dry_run=True)
        self.assertEqual(run.steps["inputs"].status, "skipped")
        self.assertTrue(run.risks)


class EndToEnd(unittest.TestCase):
    """build_story(dry_run=False) with fake clip rendering, then the real vg.render_video through applied_story."""

    def test_render_6_shots_over_20s(self):
        import video_generator as vg
        tmp = tempfile.TemporaryDirectory()
        saved = _fake_modules({})
        old_cwd = os.getcwd()
        try:
            root = Path(tmp.name)
            proj = _make_project(root)
            run = sp.build_story(proj, {"words": WORDS, "audio_end": 20.0}, log=lambda m: None, dry_run=False)
            self.assertEqual(len(run.clips), 7)                            # 6 shot clips + the link between sh1 and sh2
            self.assertEqual([g["kind"] for g in run.timeline["segments"]], ["shot", "shot", "link", "shot", "shot", "shot", "shot"])
            self.assertAlmostEqual(run.timeline["seconds"], 20.0, delta=0.05)
            self.assertTrue(run.usable())
            aligned = run.aligned
            work = root / "work"
            work.mkdir()
            os.chdir(work)
            out = root / "out.mp4"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), sp.applied_story(vg, run):
                vg.render_video(aligned, 20.0, proj / "assets", str(proj / "audio" / "vo.mp3"), str(out), resolution="320x180", fps=15, zoom=True,
                                visual_transitions=True, transition_by_scene={"1": "fade"}, camera_by_scene={"2": "push_in"},
                                render_cache_state_dir=proj / "state")
            self.assertIn("3 scenes -> 7 units", buf.getvalue())
            self.assertTrue(list((proj / "state" / "story" / "trims").glob("*.mp4")))      # sh2 starts 0.6 s into its clip: played from a trimmed copy
            self.assertTrue(out.is_file())
            # restored afterwards
            self.assertIsNot(vg.render_video.__name__, "render")
            dur = story_audit._probe_duration(out)
            self.assertAlmostEqual(dur, 20.0, delta=0.15)
            # shot order: the base colour in the middle of each shot is that shot's clip colour
            for i, st in enumerate(SHOT_STARTS):
                en = SHOT_STARTS[i + 1] if i + 1 < len(SHOT_STARTS) else 20.0
                im = story_audit._grab(out, (st + en) / 2, 160)
                arr = np.asarray(im).reshape(-1, 3)
                med = np.median(arr, axis=0)
                nearest = int(np.argmin([np.abs(med - np.array(c)).sum() for c in COLORS]))
                self.assertEqual(nearest, i, f"shot {i}: median colour {med}")
            link = np.median(np.asarray(story_audit._grab(out, 6.5, 160)).reshape(-1, 3), axis=0)       # the link clip is grey, centred on the sh1/sh2 cut
            self.assertLess(np.abs(link - 128).max(), 25, link)
            res = story_audit.audit_all(out, plan={"shots": run.shots}, aligned=aligned, words=WORDS, print_fn=None, flash_check=False)
            still = [c for c in res["checks"] if c["check"] == "still stretches"][0]
            self.assertTrue(still["ok"], still)
            self.assertEqual(res["still_spans"], [])
        finally:
            os.chdir(old_cwd)
            _restore(saved)
            tmp.cleanup()

    def test_dry_run_plan_renders_shot_stills_without_clips(self):
        """A dry run has no clips: the render still splits scenes at the shot cuts, each shot showing its scene's picture."""
        import video_generator as vg
        tmp = tempfile.TemporaryDirectory()
        saved = _fake_modules({})
        old_cwd = os.getcwd()
        try:
            root = Path(tmp.name)
            proj = _make_project(root)
            run = sp.build_story(proj, {"words": WORDS, "audio_end": 20.0}, log=lambda m: None, dry_run=True)
            self.assertEqual(run.clips, {})
            self.assertTrue(run.usable())
            (root / "work").mkdir()
            os.chdir(root / "work")
            out = root / "o.mp4"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), sp.applied_story(vg, run):
                vg.render_video(run.aligned, 20.0, proj / "assets", str(proj / "audio" / "vo.mp3"), str(out), resolution="320x180", fps=15, zoom=True)
            self.assertIn("3 scenes -> 6 units (0 clips, 6 own pictures)", buf.getvalue())
            self.assertAlmostEqual(story_audit._probe_duration(out), 20.0, delta=0.15)
        finally:
            os.chdir(old_cwd)
            _restore(saved)
            tmp.cleanup()

    def test_restore_when_not_usable(self):
        import video_generator as vg
        before = (vg.render_video, vg.find_image_for_scene)
        with sp.applied_story(vg, None):
            self.assertEqual((vg.render_video, vg.find_image_for_scene), before)
        run = sp.StoryRun(project_dir=Path("."), settings={})
        with sp.applied_story(vg, run):
            self.assertEqual((vg.render_video, vg.find_image_for_scene), before)
        run.plan = {"shots": sp.tile_shots(_fake_shots(), 20.0)}
        run.aligned = [{}] * 3
        with sp.applied_story(vg, run):
            self.assertIsNot(vg.render_video, before[0])
        self.assertEqual((vg.render_video, vg.find_image_for_scene), before)


if __name__ == "__main__":
    unittest.main()
