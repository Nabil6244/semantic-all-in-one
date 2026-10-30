"""Story Motion sound plan + mix, and the project grade (story_fast/sound.py, story_fast/grade.py). Needs ffmpeg; no network, no Whisper."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from story_fast import sound, grade, film_qa   # noqa: E402

HAVE_FF = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def shots(n=60, dur=3.0, kind="mix"):
    out = []
    for i in range(n):
        tr = "cut"
        if i % 11 == 5: tr = "flash"
        elif i % 7 == 3: tr = "fade"
        elif i % 9 == 4: tr = "zoom_blur"
        out.append({"shot_id": f"{i:03d}a", "scene_no": str(i), "start": i * dur, "end": (i + 1) * dur, "text": "The debt was a trap." if i < 20 else "Finally she felt free.",
                    "genre": "emotional" if 25 <= i < 30 else "neutral", "energy": (2 if 25 <= i < 30 else 4 if i % 13 == 0 else 3), "treatment": "dolly_through" if i % 5 == 0 else "push_in",
                    "transition_in": tr, "env": ["embers"], "continuity": {"location": ("room", "market", "road")[(i // 8) % 3], "same_location_as_prev": i % 8 != 0}})
    return out


class PlanTests(unittest.TestCase):
    def test_deterministic_and_obeys_own_limits(self):
        sh = shots()
        a = sound.build_plan(sh, 180.0, seed=3)
        b = sound.build_plan(sh, 180.0, seed=3)
        self.assertEqual(a, b)
        self.assertEqual(sound.check_plan(a), [])

    def test_sfx_rules(self):
        p = sound.build_plan(shots(120), 360.0)
        ev = [e for e in p["sfx"] if e["kind"] != "riser"]
        self.assertTrue(ev)
        self.assertTrue(all(e["t"] >= 2.0 for e in ev), "nothing in the first 2 s")
        self.assertTrue(all(b["t"] - a["t"] >= sound.MIN_GAP_S - 1e-6 for a, b in zip(ev, ev[1:])))
        calm = [s for s in shots(120) if s["genre"] == "emotional"]
        for e in ev:   # never in the calm emotional passage
            self.assertFalse(any(abs(e["t"] - s["start"]) < 1e-6 for s in calm))
        # a plain cut never gets a sound unless it is a strong move / step up (the reason says so)
        for e in ev:
            self.assertTrue(e["why"])
        self.assertLessEqual(max(sum(1 for e in ev if int(e["t"] // 60) == m) for m in range(7)), sound.MAX_PER_MIN)

    def test_variety(self):
        p = sound.build_plan(shots(300, 3.0), 900.0)
        last = {}
        for e in p["sfx"]:
            if e["sample"] in last and len(sound.sfx_catalog().get(e["kind"], [])) > 6:
                self.assertGreaterEqual(e["t"] - last[e["sample"]], 100, f"{e['sample']} repeated too soon")
            last[e["sample"]] = e["t"]
        beds = p["ambience"]
        self.assertTrue(all(b["sample"] != a["sample"] for a, b in zip(beds, beds[1:])), "same bed twice in a row")
        segs = p["music"]
        self.assertTrue(all(a["stem"] != b["stem"] for a, b in zip(segs, segs[1:])))

    def test_music_follows_energy_and_opens_calm(self):
        sh = []
        for i in range(100):   # 5 min: calm first half, strong second half
            sh.append({"shot_id": str(i), "start": i * 3.0, "end": i * 3.0 + 3.0, "text": "x", "genre": "neutral", "energy": 2 if i < 50 else 5, "transition_in": "cut",
                       "continuity": {"location": "room"}, "env": []})
        p = sound.build_plan(sh, 300.0, sfx=False, ambience=False)
        m = p["music"]
        self.assertGreaterEqual(len(m), 2)
        en = {t["stem"]: t["energy"] for t in sound.music_tracks()}
        self.assertLess(en[m[0]["stem"]], en[m[-1]["stem"]])
        self.assertLessEqual(m[0]["target_lufs"], m[-1]["target_lufs"] - 3)

    def test_empty_inputs_are_safe(self):
        p = sound.build_plan([], 30.0)
        self.assertEqual(p["sfx"], [])
        p = sound.build_plan(shots(5), 15.0, catalog={}, tracks=[])
        self.assertEqual((p["music"], p["sfx"], p["ambience"]), ([], [], []))

    def test_excerpt_clipping(self):
        p = sound.build_plan(shots(60), 60.0)
        self.assertTrue(all(b["end"] <= 60.01 for b in p["ambience"]))
        self.assertTrue(all(m["end"] <= 60.01 for m in p["music"]))
        self.assertTrue(all(e["t"] <= 60.0 for e in p["sfx"]))


def make_voice(path, secs):
    # speech-like: 0.8 s of modulated tone, 0.4 s of silence, repeating
    expr = f"sin(2*PI*180*t)*0.28*(1+0.6*sin(2*PI*3*t))*lt(mod(t\\,1.2)\\,0.8)"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={secs}", "-ac", "1", path], check=True)


@unittest.skipUnless(HAVE_FF, "ffmpeg missing")
class MixTests(unittest.TestCase):
    def test_mix_keeps_voice_and_adds_bed(self):
        with tempfile.TemporaryDirectory() as d:
            v, out = os.path.join(d, "v.wav"), os.path.join(d, "m.wav")
            make_voice(v, 40)
            plan = sound.build_plan(shots(14, 3.0), 40.0)
            r = sound.render_mix(plan, v, out, work_dir=d)
            self.assertTrue(r["ok"], r)
            self.assertFalse(r["fallback"], r)
            self.assertAlmostEqual(sound._probe_duration(out), 40.0, delta=0.05)
            a = film_qa.audio_report(out, 0, 40, v)["voice_vs_mix"]
            self.assertEqual(a["voice_lag_ms"], 0.0)                 # timing untouched
            self.assertAlmostEqual(a["voice_gain_in_mix"], 1.0, delta=0.01)   # level untouched
            self.assertTrue(a["bed_present"])
            self.assertGreater(a["ducking_depth_db"] or 0, 3.0)
            self.assertLess(a["bed_to_voice_db"], -12.0)
            lo = film_qa.audio_report(out, 0, 40, None)["loudness"]
            self.assertLess(lo["true_peak_dbfs"], -1.0)             # never clips
            self.assertTrue(r["credits"])

    def test_fallback_is_the_narration(self):
        with tempfile.TemporaryDirectory() as d:
            v, out = os.path.join(d, "v.wav"), os.path.join(d, "m.wav")
            make_voice(v, 6)
            r = sound.render_mix({"duration": 6.0, "music": [], "ambience": [], "sfx": []}, v, out, work_dir=d)
            self.assertTrue(r["ok"] and r["fallback"], r)
            a = film_qa.audio_report(out, 0, 6, v)["voice_vs_mix"]
            self.assertFalse(a["bed_present"])
            # a plan pointing at a missing music file must still give the narration
            bad = {"duration": 6.0, "music": [{"start": 0, "end": 6, "stem": "x", "title": "x", "path": "/nope.opus", "offset": 0, "cls": "mid", "energy": 3, "tense": False, "target_lufs": -30}],
                   "ambience": [], "sfx": []}
            out2 = os.path.join(d, "m2.wav")
            r = sound.render_mix(bad, v, out2, work_dir=d)
            self.assertTrue(r["ok"] and r["fallback"], r)
            self.assertTrue(os.path.isfile(out2))


class GradeTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        import numpy as np
        self.d = tempfile.mkdtemp()
        self.paths = []
        rng = np.random.default_rng(1)
        for i in range(30):
            a = np.full((90, 160, 3), 255, np.uint8)
            a[30:60, 40:120] = (rng.integers(40, 200), rng.integers(40, 200), rng.integers(40, 200))
            if i == 29:                       # one batch with a yellow cast on the paper
                a[..., 2] = 190
            p = os.path.join(self.d, f"{i:03d}.png")
            Image.fromarray(a).save(p)
            self.paths.append(p)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_reference_is_robust_and_corrections_clamped(self):
        g = grade.compute_project_grade(self.paths)
        self.assertEqual(g.stills, 30)
        typical = g.correction(self.paths[0])
        self.assertLess(max(abs(typical[k] - 1) for k in typical), 0.13)
        odd = g.correction(self.paths[29])
        self.assertTrue(odd["gb"] != 1.0, "the yellow-cast picture gets a blue-channel correction")
        for k in ("gr", "gg", "gb"):
            self.assertLessEqual(abs(odd[k] - 1), grade.CLAMP_CAST + 1e-6)
        self.assertLessEqual(abs(odd["gl"] - 1), grade.CLAMP_EXPOSURE + 1e-6)

    def test_filter_is_valid_ffmpeg_and_never_empty(self):
        g = grade.compute_project_grade(self.paths)
        for p in (self.paths[0], self.paths[29], None, "/missing.png"):
            f = g.filter_for(p)
            self.assertTrue(f and not f.startswith(",") and not f.endswith(","))
            if HAVE_FF:
                r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", self.paths[0], "-vf", f + ",format=yuv420p", "-frames:v", "1", os.path.join(self.d, "o.png")], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_roundtrip_and_empty(self):
        g = grade.compute_project_grade(self.paths)
        grade.save(g, os.path.join(self.d, "g.json"))
        g2 = grade.load(os.path.join(self.d, "g.json"))
        self.assertEqual(g2.filter_for(self.paths[3]), g.filter_for(self.paths[3]))
        e = grade.compute_project_grade([])
        self.assertTrue(e.filter_for("/x.png"))          # finish only, no crash
        self.assertEqual(e.color_filter("/x.png"), "")


if __name__ == "__main__":
    unittest.main()
