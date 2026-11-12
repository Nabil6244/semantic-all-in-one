"""Aviation style: the Tk-free runner behind the app page (scenes, footage requests, clip picking, chunked render with the voice)."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from aviation import planner as P
from aviation import runner as RN
from test_aviation_map import fake_tile
from test_aviation_planner import FLIGHT, NEWS, scenes


def _clip(path: Path, seconds: float = 6.0) -> str:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=30:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return str(path)


def _voice(path: Path, seconds: float) -> str:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}", "-c:a", "aac", str(path)], check=True)
    return str(path)


CSV = ("scene_number,script_segment,asset_type,prompt,graphic,mode,airline,aircraft,from,to,time,fuel,altitude,article,radio\n"
       '1,"Air France launched Joon in 2017.",youtube_video,"Joon launch 2017 || Joon A321",,news,Air France,,,,,,,,\n'
       '2,"Vistara 611 takes off from Srinagar for Jammu.",none,,,flight,Vistara,A320,SXR,IXJ,13:24,4900,,,\n')


class SceneTests(unittest.TestCase):
    def test_csv_scenes_keep_the_csv_columns(self):
        d = tempfile.mkdtemp()
        p = Path(d) / "s.csv"
        p.write_text(CSV, encoding="utf-8")
        sc, rows = RN.scenes_from_csv(p)
        self.assertEqual([s["scene_no"] for s in sc], [1, 2])
        self.assertEqual(sc[0]["asset_type"], "youtube_video")
        self.assertEqual(sc[0]["prompt"], "Joon launch 2017 || Joon A321")
        self.assertEqual(rows[1]["from"], "SXR")
        self.assertNotIn("start", sc[0])                               # untimed: aligned to the voice-over later

    def test_narration_scenes_ask_for_footage_only_where_the_plan_needs_it(self):
        sc = scenes(NEWS + FLIGHT)
        plan = P.plan(sc)
        RN.request_footage(sc, plan)
        news = [s for s in sc if s["scene_no"] <= 5]
        flight = [s for s in sc if s["scene_no"] > 5]
        self.assertTrue(all(s["asset_type"] in ("youtube_video", "none") for s in sc))
        self.assertTrue(any(s["asset_type"] == "youtube_video" and s["prompt"] for s in news))
        self.assertTrue(all(s["asset_type"] == "none" for s in flight))     # a 20 s map needs no clip

    def test_csv_asset_type_is_kept(self):
        sc = [{"scene_no": 1, "text": "Air France launched Joon.", "start": 0.0, "end": 4.0, "asset_type": "stock_video", "prompt": "x"}]
        RN.request_footage(sc, P.plan(sc))
        self.assertEqual(sc[0]["asset_type"], "stock_video")


class PickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.a = _clip(Path(cls.tmp.name) / "a.mp4", 8.0)
        cls.b = _clip(Path(cls.tmp.name) / "b.mp4", 8.0)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_slices_of_one_clip_start_at_different_points(self):
        sc = scenes(NEWS[:1])
        sc[0]["footage"] = self.a
        sc[0]["footage_meta"] = {"channel": "Euronews", "duration": 8.0}
        plan = P.plan(sc)
        pick = RN.clip_picker(sc, plan)
        slots = [s for s in plan.shots if s.get("kind") == "footage"]
        got = [pick(s) for s in slots]
        self.assertTrue(all(g and g["path"] == self.a for g in got))
        self.assertEqual(len({round(g["seek"], 2) for g in got}), len(got))
        self.assertEqual(got[0]["source"], "Euronews")

    def test_wrong_aircraft_in_the_title_is_not_used(self):
        sc = scenes(["The A350 seats 292 passengers in a three-class cabin."])
        sc[0]["footage"] = self.a
        sc[0]["footage_meta"] = {"video_title": "Boeing 737 landing at Paris", "duration": 8.0}
        plan = P.plan(sc)
        pick = RN.clip_picker(sc, plan, log=lambda m: None)
        slot = [s for s in plan.shots if s.get("kind") == "footage"][0]
        self.assertIsNone(pick(slot))

    def test_scene_without_a_clip_borrows_a_neighbour_in_its_stretch(self):
        sc = scenes(NEWS[:3])
        sc[0]["footage"] = self.a
        sc[0]["footage_meta"] = {"duration": 8.0}
        plan = P.plan(sc)
        pick = RN.clip_picker(sc, plan)
        slot = [s for s in plan.shots if s.get("kind") == "footage" and s["scene"] == 3][0]
        self.assertEqual(pick(slot)["path"], self.a)


class ChunkTests(unittest.TestCase):
    def test_chunks_cover_the_film_and_keep_layer_time(self):
        from cinematic_explainer.render import Layer, Shot

        shots = [Shot("a", 0.0, 50.0, 1.0), Shot("b", 50.0, 130.0, 0.0)]
        layers = [Layer("x", 40.0, 70.0, {}), Layer("y", 100.0, 125.0, {})]
        chunks = RN.split_timeline(shots, layers, chunk_s=60.0)
        self.assertEqual([round(c[0], 3) for c in chunks], [0.0, 60.0, 120.0])
        s0, l0 = chunks[0][1], chunks[0][2]
        s1, l1 = chunks[1][1], chunks[1][2]
        self.assertAlmostEqual(sum(s.end - s.start for c in chunks for s in c[1]), 130.0)
        # the shot that crosses 60 s goes on with the right seek
        self.assertEqual(s1[0].path, "b")
        self.assertAlmostEqual(s1[0].seek, 10.0)
        # a layer crossing the cut keeps its own clock: start before 0 in the second chunk
        x1 = [ly for ly in l1 if ly.kind == "x"][0]
        self.assertAlmostEqual(x1.start, -20.0)
        self.assertAlmostEqual(x1.end, 10.0)
        self.assertTrue(all(s.start >= 0 for s in s1))


class RenderTests(unittest.TestCase):
    def test_film_with_voice(self):
        with tempfile.TemporaryDirectory() as d:
            sc = [{"scene_no": 1, "text": "Air France confirmed plans to cut 2,900 jobs in 2015.", "start": 0.0, "end": 3.0},
                  {"scene_no": 2, "text": "Vistara 611 takes off from Srinagar for Jammu with 4,900 kg of fuel.", "start": 3.0, "end": 6.0}]
            sc[0]["footage"] = _clip(Path(d) / "c.mp4", 6.0)
            voice = _voice(Path(d) / "v.m4a", 6.0)
            plan = P.plan(sc)
            out = Path(d) / "film.mp4"
            r = RN.render_film(plan, sc, voice, str(out), work=str(Path(d) / "work"), chunk_s=3.0, workers=2,
                               map_extra={"fetch_tile": fake_tile, "cache": d})
            self.assertTrue(out.is_file())
            probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)]).decode()
            self.assertIn("video", probe)
            self.assertIn("audio", probe)
            dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)]).strip())
            self.assertAlmostEqual(dur, 6.0, delta=0.25)
            self.assertEqual(r["chunks"], 2)

    def test_cancel_stops_before_writing(self):
        with tempfile.TemporaryDirectory() as d:
            sc = [{"scene_no": 1, "text": "Air France confirmed plans to cut jobs.", "start": 0.0, "end": 3.0}]
            voice = _voice(Path(d) / "v.m4a", 3.0)
            with self.assertRaises(RN.Cancelled):
                RN.render_film(P.plan(sc), sc, voice, str(Path(d) / "f.mp4"), work=str(Path(d) / "w"), cancel=lambda: True)
            self.assertFalse((Path(d) / "f.mp4").exists())


if __name__ == "__main__":
    unittest.main()


class IntroSkipTests(unittest.TestCase):
    def test_first_slice_skips_the_start_of_the_cut(self):
        with tempfile.TemporaryDirectory() as d:
            sc = scenes(NEWS[:1])
            sc[0]["footage"] = _clip(Path(d) / "a.mp4", 8.0)
            sc[0]["footage_meta"] = {"duration": 8.0}
            plan = P.plan(sc)
            pick = RN.clip_picker(sc, plan)
            first = pick([s for s in plan.shots if s.get("kind") == "footage"][0])
            self.assertGreaterEqual(first["seek"], 1.0)


class ExtraClipTests(unittest.TestCase):
    def test_burst_cuts_between_the_main_clip_and_its_extras(self):
        with tempfile.TemporaryDirectory() as d:
            sc = scenes(NEWS[:1])
            sc[0]["footage"] = _clip(Path(d) / "a.mp4", 8.0)
            sc[0]["footage_meta"] = {"duration": 8.0, "channel": "euronews"}
            b, c = _clip(Path(d) / "b.mp4", 8.0), _clip(Path(d) / "c.mp4", 8.0)
            extras = {"1": [{"path": b, "duration": 8.0, "channel": "AFP"}, {"path": c, "duration": 8.0, "channel": "Reuters"}]}
            plan = P.plan(sc)
            pick = RN.clip_picker(sc, plan, extras=extras)
            got = [pick(s) for s in plan.shots if s.get("kind") == "footage"]
            self.assertEqual(len({g["path"] for g in got}), min(3, len(got)))
            self.assertIn("AFP", {g["source"] for g in got})


class StillTests(unittest.TestCase):
    def test_flow_image_becomes_a_moving_clip(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "p.png"
            Image.new("RGB", (1376, 768), (40, 90, 160)).save(img)
            out = RN.still_to_clip(str(img), str(Path(d) / "p.mp4"), seconds=4.0)
            dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out]).strip())
            self.assertAlmostEqual(dur, 4.0, delta=0.2)

    def test_attach_images_sets_footage_for_image_scenes(self):
        from PIL import Image
        from asset_manager import AssetManifest
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "005.png"
            Image.new("RGB", (640, 360), (10, 10, 10)).save(img)
            AssetManifest(Path(d)).set("5", {"status": "complete", "local_path": str(img), "source": "flow_image", "type": "image"})
            sc = [{"scene_no": 5, "asset_type": "flow_image", "text": "x"}, {"scene_no": 6, "asset_type": "none", "text": "y"}]
            RN.attach_images(sc, Path(d))
            self.assertTrue(sc[0]["footage"].endswith(".mp4"))
            self.assertTrue(Path(sc[0]["footage"]).is_file())
            self.assertNotIn("footage", sc[1])


class RealLengthTests(unittest.TestCase):
    def test_slices_never_run_past_the_real_end_of_a_clip(self):
        with tempfile.TemporaryDirectory() as d:
            sc = scenes(NEWS[:1])
            sc[0]["footage"] = _clip(Path(d) / "a.mp4", 3.5)
            sc[0]["footage_meta"] = {"duration": 8.0}                  # what the record says; the file is shorter
            plan = P.plan(sc)
            pick = RN.clip_picker(sc, plan)
            for s in [x for x in plan.shots if x.get("kind") == "footage"]:
                g = pick(s)
                self.assertLessEqual(g["seek"] + (s["end"] - s["start"]), 3.5 + 0.05)
