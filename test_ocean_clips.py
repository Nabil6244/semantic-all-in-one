"""Ocean style step 6: real clips (slots, searches, credits, timeline cut-ins, Visuals-tab wiring, end-to-end render)."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import ImageStat

from ocean import clips as CL
from ocean import reader as R
from ocean import runner as RN
from ocean import stage as OS

ROOT = Path(__file__).resolve().parent

SCRIPT = ("Picture this. You're floating off the coast and below you is a great white shark. It has about 300 teeth. "
          "Great whites patrol the island every autumn looking for seals. The seals know it and stay close to the rocks. "
          "Researchers filmed a great white breaching right next to the boat. Then the orcas arrived in a pod of five. "
          "Within hours every shark was gone. Drones caught the orcas circling the island for days. "
          "The sharks did not come back that year. Seals filled the beaches again. The orca pod moved on along the coast. "
          "A humpback whale swam past the same island a week later. Nobody knows when the sharks will return. "
          "Let us know in the comments.")


def _scenes(text, wps=1.6):
    out, t = [], 0.0
    for i, s in enumerate(x.strip() for x in re.split(r"(?<=[.?!])\s+", text) if x.strip()):
        d = len(s.split()) / wps
        out.append({"scene_no": i + 1, "text": s, "start": t, "end": t + d})
        t += d
    return out


def _testclip(path, seconds=8):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True, timeout=60)
    return str(path)


class QueryAndCredit(unittest.TestCase):
    def test_queries_follow_the_animal_and_place(self):
        self.assertEqual(CL.query_for(R.read("A great white shark swims."), "surface"), "great white shark ocean surface")
        self.assertEqual(CL.query_for(R.read("Orcas hunt in pods."), ""), "orca killer whale swimming group")
        self.assertEqual(CL.query_for(R.read("A blue whale feeds."), ""), "blue whale underwater")
        self.assertEqual(CL.query_for(R.read("The vampire squid drifts."), "abyss"), "vampire squid deep sea")
        self.assertEqual(CL.query_for(R.read("Nothing here moves."), ""), "")

    def test_credit_line(self):
        self.assertEqual(CL.credit({"author": "Jane Doe", "provider": "pexels"}), "Footage: Jane Doe / Pexels")
        self.assertEqual(CL.credit({"provider": "pixabay"}), "Footage: Pixabay")
        self.assertEqual(CL.credit({"author": "NOAA", "provider": "commons", "license": "CC BY 2.0"}), "Footage: NOAA / Commons (CC BY 2.0)")
        self.assertEqual(CL.credit({"user_supplied": True}), "")
        self.assertEqual(CL.credit(None), "")


class Slots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.scenes = _scenes(SCRIPT * 2)
        RN.plan_film(cls.scenes, cls.td.name, "Test")
        cls.plan = RN.load_plan(cls.td.name)

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def test_slots_are_spaced_sized_and_numbered(self):
        clips = self.plan["clips"]
        self.assertTrue(clips)
        self.assertLessEqual(len(clips), max(1, round(self.plan["total"] / CL.CLIP_EVERY_S)))
        for a, b in zip(clips, clips[1:]):
            self.assertGreaterEqual(b["start"] - a["start"], CL.CLIP_GAP_S)
        for c in clips:
            self.assertGreaterEqual(c["end"] - c["start"], CL.CLIP_MIN_S - 1e-6)
            self.assertLessEqual(c["end"] - c["start"], CL.CLIP_MAX_S + 0.6)
            self.assertTrue(c["query"])

    def test_slots_avoid_text_cards_and_stay_in_one_shot(self):
        busy = CL._busy(self.plan["layers"])
        shots = [l for l in self.plan["layers"] if l["name"] == "ocean.lay_ocean"]
        for c in self.plan["clips"]:
            for a, b in busy:
                self.assertLessEqual(min(c["end"], b) - max(c["start"], a), 1e-6)
            self.assertTrue(any(s["start"] <= c["start"] and c["end"] <= s["end"] + 1e-6 for s in shots))

    def test_real_footage_lines_are_preferred(self):
        self.assertTrue(any(c["why"] == "real" for c in self.plan["clips"]))

    def test_no_clips_when_turned_off(self):
        with tempfile.TemporaryDirectory() as td:
            RN.plan_film(self.scenes, td, "Test", real_clips=False)
            self.assertEqual(RN.load_plan(td)["clips"], [])
            self.assertEqual(RN.clip_scenes(RN.load_plan(td)), [])

    def test_visual_rows_are_stock_searches(self):
        rows = RN.clip_scenes(self.plan)
        self.assertEqual(len(rows), len(self.plan["clips"]))
        self.assertTrue(all(r["asset_type"] == "stock_video" and r["prompt"] for r in rows))


class CutIn(unittest.TestCase):
    def test_apply_cuts_clips_in_and_hides_the_stage(self):
        with tempfile.TemporaryDirectory() as td:
            RN.plan_film(_scenes(SCRIPT), td, "Test")
            plan = RN.load_plan(td)
            slot = plan["clips"][0]
            src = _testclip(Path(td) / "src.mp4")
            shots, layers, used = CL.apply(plan, {slot["scene_no"]: {"path": src, "meta": {"author": "A", "provider": "pexels"}}},
                                           "black.mp4", td)
            self.assertEqual(len(used), 1)
            self.assertAlmostEqual(shots[0].start, 0.0)
            self.assertAlmostEqual(shots[-1].end, plan["total"], places=3)
            for a, b in zip(shots, shots[1:]):
                self.assertAlmostEqual(a.end, b.start, places=3)
            clip_shot = [s for s in shots if s.path == used[0]["path"]][0]
            self.assertAlmostEqual(clip_shot.start, slot["start"], places=3)
            holed = [l for l in layers if l.params.get("holes")]
            self.assertEqual(len(holed), 1)
            ly = holed[0]
            mid = (slot["start"] + slot["end"]) / 2 - ly.start
            img = OS.lay_ocean(mid, ly.end - ly.start, ly.params)
            self.assertLess(ImageStat.Stat(img.getchannel("A")).mean[0], 5)          # only the credit line is drawn
            self.assertIsNotNone(img.getchannel("A").crop((0, OS.H - 60, 600, OS.H)).getbbox())

    def test_missing_clip_keeps_the_stage(self):
        with tempfile.TemporaryDirectory() as td:
            RN.plan_film(_scenes(SCRIPT), td, "Test")
            plan = RN.load_plan(td)
            shots, layers, used = CL.apply(plan, {plan["clips"][0]["scene_no"]: {"path": str(Path(td) / "nope.mp4")}}, "black.mp4", td)
            self.assertEqual(used, [])
            self.assertEqual(len(shots), 1)
            self.assertFalse(any(l.params.get("holes") for l in layers))

    def test_tiny_film_with_a_clip_renders(self):
        with tempfile.TemporaryDirectory() as td:
            sc = _scenes("A great white shark swims past the island. It has about 300 teeth. Seals watch from the rocks.", wps=3.0)
            RN.plan_film(sc, td, "Test")
            plan = RN.load_plan(td)
            plan["clips"] = [{"scene_no": "2", "start": 1.0, "end": 3.0, "query": "great white shark", "text": "x", "why": "animal"}]
            (Path(td) / "plan.json").write_text(__import__("json").dumps(plan), encoding="utf-8")
            voice = Path(td) / "v.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=200:duration={plan['total'] + 0.5:.2f}",
                            str(voice)], check=True, timeout=60)
            out = Path(td) / "film.mp4"
            r = RN.render_film(td, str(voice), str(out), workers=2,
                               found={"2": {"path": _testclip(Path(td) / "src.mp4"), "meta": {"author": "Jane", "provider": "pexels"}}})
            self.assertEqual(r["clips"], 1)
            self.assertTrue(out.is_file() and out.stat().st_size > 10000)
            self.assertIn("Jane / Pexels", (Path(td) / "film_chapters.txt").read_text(encoding="utf-8"))


class Wiring(unittest.TestCase):
    def test_visuals_tab_owner(self):
        import visual_bridge
        self.assertEqual(visual_bridge.OWNERS["ocean"][0], "_oc_active")

    def test_generate_fetches_and_render_does_not(self):
        src = (ROOT / "ui" / "ocean_section.py").read_text(encoding="utf-8")
        gen = src.split("def on_generate")[1].split("def on_render")[0]
        ren = src.split("def on_render")[1]
        self.assertIn("fetch=True", gen)
        self.assertIn("visual_bridge.fill(app, OWNER", gen)
        self.assertNotIn("fetch=True", ren)
        flat = src.replace("\n", " ")
        calls = [seg.split("library=")[0] for seg in flat.split("fetch_csv_footage(")[1:] if "library=" in seg]
        self.assertGreaterEqual(len(calls), 4)
        for call in calls:
            self.assertIn("ai_cap=0", call)
            self.assertIn("director=False", call)
        self.assertEqual(flat.count("library=False"), len(calls))
        self.assertIn("visual_bridge.restore(app, OWNER)", src)
        self.assertIn("visual_bridge.clear(app, OWNER)", src)


if __name__ == "__main__":
    unittest.main()
