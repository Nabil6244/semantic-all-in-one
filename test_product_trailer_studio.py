"""The page's back end (product_trailer/studio.py): film types, results record, references reuse, scene making with fakes. No UI, no Flow."""
import json
import tempfile
import unittest
from pathlib import Path

from product_trailer import studio, scenepack as S

CSV = Path(__file__).resolve().parent / "docs" / "product_trailer" / "samples" / "galaxy_s27_ultra_reveal.csv"
SCRIPT = "## Design\nThe frame is flat and the back is matte.\n[stat: 30W | Fast charging]\n## Hinge\nWe folded it three thousand times.\n[xray: Inside the hinge]\n"


class FakeClient:
    def __init__(self):
        self.requests, self._subs = [], []

    def subscribe(self, fn):
        self._subs.append(fn)
        return lambda: self._subs.remove(fn)

    def generate(self, prompts, settings=None, account_ids=None, prompt_keys=None):
        self.requests.append((list(prompts), settings))
        self._p = (list(prompts), settings)

    def wait_for(self, predicate, timeout=600.0):
        prompts, settings = self._p
        for i in range(len(prompts)):
            f = Path(settings["outputDir"]) / f"{i + 1:03d}.png"
            f.write_bytes(b"\x89PNG" + bytes([i]))
            for fn in list(self._subs):
                fn({"type": "PROMPT_RESULT", "index": i, "status": "done", "path": str(f)})
        for fn in list(self._subs):
            fn({"type": "GENERATE_DONE"})
        return {"type": "GENERATE_DONE"}


def fake_refs(spec, times, work, log):
    out = []
    for i, t in enumerate(times):
        p = Path(work) / f"refs.mp4.t{t:g}.jpg"
        p.write_bytes(b"jpg" + bytes([i]))
        out.append(p)
    return out


class Plan(unittest.TestCase):
    def test_trailer_and_reveal_without_ai_use_the_existing_planner(self):
        with tempfile.TemporaryDirectory() as d:
            for ft in ("Trailer", "Reveal"):
                r = studio.plan_film(ft, out_dir=Path(d) / ft, csv=str(CSV), phone="galaxy s27 ultra")
                spec = json.loads(Path(r["spec_path"]).read_text(encoding="utf-8"))
                self.assertGreater(len(spec["shots"]), 5)
                self.assertIsNone(r["pack"])
                self.assertIn(ft, r["summary"])

    def test_reveal_with_ai_is_the_mixed_film_and_falls_back_to_3d_without_pictures(self):
        with tempfile.TemporaryDirectory() as d:
            r = studio.plan_film("Reveal", out_dir=d, csv=str(CSV), phone="galaxy s27 ultra", use_ai=True)
            spec = json.loads(Path(r["spec_path"]).read_text(encoding="utf-8"))
            self.assertEqual(spec["product_trailer"]["pace"], "mixed")
            self.assertTrue(r["pack"]["estimate"]["ai_images"] > 0)
            self.assertTrue(r["notes"], "every AI scene without a picture is noted")
            self.assertEqual({s["kind"] for s in spec["shots"]}, {"product", "black"})

    def test_review_needs_a_script_and_builds_the_review_spec(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                studio.plan_film("Review", out_dir=d, script="  ")
            r = studio.plan_film("Review", out_dir=d, script=SCRIPT, phone="galaxy s27 ultra", disclaimer="Concept.")
            spec = json.loads(Path(r["spec_path"]).read_text(encoding="utf-8"))
            self.assertEqual(spec["product_trailer"]["pace"], "review")
            types = [L["type"] for L in spec["layers"]]
            self.assertIn("pt_subtitle", types)
            self.assertIn("tm_title", types)

    def test_csv_missing_and_unknown_type_are_clear_errors(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                studio.plan_film("Trailer", out_dir=d, csv=None)
            with self.assertRaises(ValueError):
                studio.plan_film("Nope", out_dir=d, csv=str(CSV))

    def test_the_estimate_line_says_images_are_free_and_clips_are_not_made(self):
        pack, _ = studio.plan_pack("Reveal", csv=str(CSV), phone="galaxy s27 ultra")
        text = studio.estimate_text(pack)
        self.assertIn("0 credits", text)
        self.assertIn("not made here", text)


class Scenes(unittest.TestCase):
    def test_make_scenes_renders_references_once_generates_and_saves_results_that_the_next_plan_uses(self):
        with tempfile.TemporaryDirectory() as d:
            pack, _ = studio.plan_pack("Reveal", csv=str(CSV), phone="galaxy s27 ultra")
            client = FakeClient()
            res = studio.make_scenes(pack, d, client, phone="galaxy s27 ultra", ref_runner=fake_refs, log=lambda m: None)
            self.assertTrue(all(r["status"] == "done" for r in res.values()))
            self.assertEqual(len(studio.load_results(d)), len(res))
            self.assertEqual(len(list((studio.refs_dir(d)).glob("ref*.jpg"))), 5)
            for prompts, settings in client.requests:
                self.assertTrue(1 <= len(settings["referenceImages"]) <= 3)
            r = studio.plan_film("Reveal", out_dir=d, csv=str(CSV), phone="galaxy s27 ultra", use_ai=True)
            spec = json.loads(Path(r["spec_path"]).read_text(encoding="utf-8"))
            self.assertTrue(any(s["kind"] in ("image", "video") for s in spec["shots"]))
            self.assertEqual((Path(d) / "media").is_dir(), True)

    def test_references_are_reused_not_rendered_twice(self):
        with tempfile.TemporaryDirectory() as d:
            calls = []

            def runner(spec, times, work, log):
                calls.append(1)
                return fake_refs(spec, times, work, log)

            studio.ensure_references("galaxy s27 ultra", d, runner=runner, log=lambda m: None)
            studio.ensure_references("galaxy s27 ultra", d, runner=runner, log=lambda m: None)
            self.assertEqual(len(calls), 1)

    def test_results_whose_picture_vanished_are_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            studio.save_results(d, {1: {"status": "done", "path": str(Path(d) / "gone.png")}, 2: {"status": "failed", "error": "x"}})
            self.assertEqual(set(studio.load_results(d)), {2})


if __name__ == "__main__":
    unittest.main()
