"""Scene pack (product_trailer/scenepack.py): planning rules, credit estimate and the Flow runner with a fake client. No network, no credits."""
import tempfile
import unittest
from pathlib import Path

from product_trailer import scenepack as S

FEATURES = [{"feature": f} for f in ["design", "display", "camera", "camera", "chip", "battery", "charging", "display", "durability", "os", "other", "camera"]]
COLS = ["Black", "Sky Blue", "Pink", "White"]


class Plan(unittest.TestCase):
    def setUp(self):
        self.pack = S.plan_scene_pack(FEATURES, "galaxy s27 ultra", COLS)

    def test_one_scene_per_feature_in_order(self):
        self.assertEqual([s["n"] for s in self.pack["scenes"]], list(range(1, len(FEATURES) + 1)))

    def test_the_chip_stays_3d_and_everything_else_gets_an_ai_scene(self):
        by = {s["n"]: s for s in self.pack["scenes"]}
        self.assertEqual(by[5]["source"], "3d")
        self.assertIsNone(by[5]["type"])
        self.assertTrue(all(s["source"] in ("ai_still", "ai_clip") for n, s in by.items() if n != 5))

    def test_a_scene_type_never_repeats_back_to_back(self):
        types = [s["type"] for s in self.pack["scenes"] if s["source"] != "3d"]
        for a, b in zip(types, types[1:]):
            self.assertNotEqual(a, b)

    def test_camera_features_get_the_macro_or_a_back_scene(self):
        for s in self.pack["scenes"]:
            if s["feature"] == "camera":
                self.assertIn(s["type"], ("macro_camera", "row_backs", "hands_fan", "single_table"))

    def test_every_prompt_names_the_references_and_forbids_text(self):
        for s in self.pack["scenes"]:
            if s["source"] == "3d":
                continue
            self.assertIn("reference images", s["prompt"])
            self.assertIn("exactly", s["prompt"])
            self.assertIn("no text and no logo", s["prompt"])
            self.assertLessEqual(len(s["refs"]), S.FLOW_REF_LIMIT)
            self.assertNotIn("{", s["prompt"], "no unfilled placeholder")

    def test_keys_are_unique_and_stable(self):
        keys = [s["key"] for s in self.pack["scenes"] if s["source"] != "3d"]
        self.assertEqual(len(keys), len(set(keys)))
        again = S.plan_scene_pack(FEATURES, "galaxy s27 ultra", COLS)
        self.assertEqual(self.pack, again, "deterministic")

    def test_settings_rotate(self):
        rooms = [s["setting"] for s in self.pack["scenes"] if s["source"] != "3d"]
        self.assertGreater(len(set(rooms)), 3)

    def test_clips_are_few_and_never_back_to_back(self):
        sc = self.pack["scenes"]
        self.assertLessEqual(sum(1 for s in sc if s["source"] == "ai_clip"), 3)
        for a, b in zip(sc, sc[1:]):
            self.assertFalse(a["source"] == "ai_clip" and b["source"] == "ai_clip")
        self.assertEqual(S.plan_scene_pack(FEATURES, "x", COLS, max_clips=0)["estimate"]["ai_clips"], 0)


class Estimate(unittest.TestCase):
    def test_images_are_free_clips_cost_ten_each(self):
        pack = S.plan_scene_pack(FEATURES, "x", COLS, max_clips=3)
        e = pack["estimate"]
        self.assertEqual(e["image_credits"], 0)
        self.assertEqual(e["clip_credits"], e["ai_clips"] * S.CLIP_CREDITS)
        self.assertEqual(e["ai_images"] + e["three_d_shots"], len(FEATURES))
        self.assertEqual(e["days_needed"], 1)
        self.assertEqual(S.plan_scene_pack(FEATURES, "x", COLS, max_clips=0)["estimate"]["days_needed"], 0)

    def test_describe_lists_every_scene(self):
        text = S.describe(S.plan_scene_pack(FEATURES, "x", COLS))
        self.assertEqual(text.count("\n"), len(FEATURES))
        self.assertIn("3D", text)


class FakeClient:
    """Stands in for providers.flow.client: records the request and answers with one picture per scene (except those in `fail`)."""

    def __init__(self, tmp, fail=()):
        self.tmp, self.fail, self.requests, self._subs = Path(tmp), set(fail), [], []

    def subscribe(self, fn):
        self._subs.append(fn)
        return lambda: self._subs.remove(fn)

    def generate(self, prompts, settings=None, account_ids=None, prompt_keys=None):
        self.requests.append({"prompts": list(prompts), "settings": settings, "keys": prompt_keys})
        self._pending = (list(prompts), settings, prompt_keys)

    def wait_for(self, predicate, timeout=600.0):
        prompts, settings, _ = self._pending
        for i, _p in enumerate(prompts):
            if prompts[i] in self.fail:
                msg = {"type": "PROMPT_RESULT", "index": i, "status": "failed", "error": "Reference images were not attached"}
            else:
                f = Path(settings["outputDir"]) / f"{i + 1:03d}.png"
                f.write_bytes(b"\x89PNG" + bytes([i]))
                msg = {"type": "PROMPT_RESULT", "index": i, "status": "done", "path": str(f)}
            for fn in list(self._subs):
                fn(msg)
        done = {"type": "GENERATE_DONE"}
        for fn in list(self._subs):
            fn(done)
        assert predicate(done)
        return done


class Generate(unittest.TestCase):
    def _refs(self, d):
        r = Path(d) / "refs"
        r.mkdir()
        for stem in {x for t in S.SCENE_TYPES.values() for x in t["refs"]}:
            (r / f"{stem}.jpg").write_bytes(b"jpg")
        return r

    def test_scenes_with_the_same_references_share_one_request_with_the_pictures_attached(self):
        with tempfile.TemporaryDirectory() as d:
            pack = S.plan_scene_pack(FEATURES, "x", COLS)
            client = FakeClient(d)
            res = S.generate_scene_pack(pack, self._refs(d), Path(d) / "pack", client, log=lambda m: None)
            ai = [s for s in pack["scenes"] if s["source"] != "3d"]
            self.assertEqual(set(res), {s["n"] for s in ai})
            self.assertTrue(all(r["status"] == "done" and Path(r["path"]).is_file() for r in res.values()))
            self.assertEqual(sum(len(r["prompts"]) for r in client.requests), len(ai))
            for r in client.requests:
                refs = r["settings"]["referenceImages"]
                self.assertTrue(1 <= len(refs) <= S.FLOW_REF_LIMIT and all(Path(p).is_absolute() and Path(p).is_file() for p in refs))
                self.assertEqual(r["settings"]["mediaKind"], "image")
            keys = [k for r in client.requests for k in r["keys"]]
            self.assertEqual(len(keys), len(set(keys)))

    def test_a_failed_scene_is_reported_not_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            pack = S.plan_scene_pack(FEATURES, "x", COLS)
            first = next(s for s in pack["scenes"] if s["source"] != "3d")
            res = S.generate_scene_pack(pack, self._refs(d), Path(d) / "pack", FakeClient(d, fail=[first["prompt"]]), log=lambda m: None)
            self.assertEqual(res[first["n"]]["status"], "failed")
            self.assertIn("not attached", res[first["n"]]["error"])
            self.assertTrue(any(r["status"] == "done" for r in res.values()))

    def test_missing_references_stop_before_anything_is_sent(self):
        with tempfile.TemporaryDirectory() as d:
            pack = S.plan_scene_pack(FEATURES, "x", COLS)
            client = FakeClient(d)
            with self.assertRaises(FileNotFoundError):
                S.generate_scene_pack(pack, Path(d) / "none", Path(d) / "pack", client, log=lambda m: None)
            self.assertEqual(client.requests, [])

    def test_the_pack_file_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            p = S.write_pack(S.plan_scene_pack(FEATURES, "x", COLS), d)
            self.assertTrue(p.is_file() and p.name == "scene_pack.json")


if __name__ == "__main__":
    unittest.main()
