"""story_character: sheet in every character prompt, request shape vs SceneRow, store/resume, plan order and counts, consistency check.
Fakes only: no Flow, no network."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import story_character as C

PROT = {"name": "Rahim", "age": "elderly", "gender": "man", "clothing": "a rust coat"}


def img(path, colour=(160, 90, 50), size=(512, 288)):
    im = Image.new("RGB", size, (240, 228, 200))
    ImageDraw.Draw(im).rectangle([size[0] // 3, size[1] // 5, size[0] // 2, size[1] - 20], fill=colour)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return str(path)


class FakeGen:
    def __init__(self, tmp):
        self.tmp, self.calls = Path(tmp), []

    def __call__(self, req):
        self.calls.append(req)
        return img(self.tmp / "gen" / f"{len(self.calls)}_{req['kind']}.png")


def shots():
    def s(i, pic, char, txt="the man walks home"):
        return {"shot_id": f"s{i:03d}", "scene_no": i, "text": txt, "prompt_en": f"scene {i} of a street", "picture": pic, "character": char}
    return [s(1, "new", False), s(2, "new", True), s(3, "existing", False), s(4, "new", True, "he picks up the letter"), s(5, "new", False)]


class Sheet(unittest.TestCase):
    def test_sheet_is_verbatim_in_every_character_prompt_and_absent_otherwise(self):
        sent = C.character_sheet(PROT)["sentence"]
        refs = {k: f"/x/{k}.png" for k in C.REFERENCE_KINDS}
        for i, sh in enumerate(shots()):
            r = C.build_character_request(sh, PROT, refs, ordinal=i)
            if sh["character"]:
                self.assertIn(sent, r["prompt"])
                self.assertIn("third of the frame", r["prompt"])
                self.assertIn("feet", r["prompt"])
                self.assertTrue(r["uses_character"])
            else:
                self.assertEqual(r["prompt"], sh["prompt_en"])
                self.assertEqual(r["reference_images"], [])
                self.assertNotIn("referenceImages", r["settings"])
        for rp in C.reference_prompts(PROT):
            self.assertIn(sent, rp["prompt"])
            self.assertIn("cream", rp["prompt"])

    def test_sheet_key_changes_with_wording_and_style_words_present(self):
        a, b = C.character_sheet(PROT), C.character_sheet({**PROT, "clothing": "a blue coat"})
        self.assertNotEqual(a["key"], b["key"])
        for w in ("engraved", "sepia", "terracotta", "cream", "cut"):
            self.assertIn(w, a["sentence"])
        self.assertEqual(len(C.reference_prompts(PROT)), 4)

    def test_request_matches_scenerow_and_flow_limits(self):
        refs = {k: f"/x/{k}.png" for k in C.REFERENCE_KINDS}
        r = C.build_character_request(shots()[3], PROT, refs)
        row = C.to_scene_row(r)
        self.assertEqual((row.scene_number, row.asset_type, row.prompt), ("s004", "image", r["prompt"]))
        self.assertLessEqual(len(r["reference_images"]), C.MAX_REFERENCES)
        self.assertEqual(r["settings"]["referenceImages"], r["reference_images"])
        self.assertEqual(r["settings"]["mediaKind"], "image")
        self.assertIn("hands", " ".join(r["reference_images"]))          # handling shot picks the hands reference
        w = C.build_character_request(shots()[1], PROT, refs)
        self.assertIn("sidewalk", " ".join(w["reference_images"]))      # walking shot picks the side view
        self.assertEqual(w["reference_images"][:2], ["/x/front34.png", "/x/fullbody.png"])

    def test_character_side_alternates_or_follows_shot(self):
        a = C.build_character_request(shots()[1], PROT, {}, ordinal=0)["prompt"]
        b = C.build_character_request(shots()[1], PROT, {}, ordinal=1)["prompt"]
        self.assertIn("left third", a)
        self.assertIn("right third", b)
        c = C.build_character_request({**shots()[1], "character_side": "right"}, PROT, {}, ordinal=0)["prompt"]
        self.assertIn("right third", c)


class Store(unittest.TestCase):
    def test_ensure_references_generates_once_and_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            store = C.ReferenceStore.for_project(d, PROT)
            self.assertEqual(store.dir, Path(d) / "state" / "story" / "character" / "rahim")
            gen = FakeGen(d)
            refs = C.ensure_references(PROT, gen, store)
            self.assertEqual(set(refs), set(C.REFERENCE_KINDS))
            self.assertEqual(len(gen.calls), 4)
            self.assertEqual(gen.calls[0]["reference_images"], [])                       # front alone
            self.assertEqual(gen.calls[1]["reference_images"], [refs["front34"]])        # the rest look like it
            self.assertEqual(store.validate(), [])
            gen2 = FakeGen(d)
            C.ensure_references(PROT, gen2, C.ReferenceStore.for_project(d, PROT))       # new process, same folder
            self.assertEqual(gen2.calls, [])
            C.ensure_references({**PROT, "clothing": "a blue coat"}, gen2, store)       # other character wording -> all again
            self.assertEqual(len(gen2.calls), 4)

    def test_resume_after_partial_run_and_damaged_file(self):
        with tempfile.TemporaryDirectory() as d:
            store = C.ReferenceStore.for_project(d, PROT)
            gen = FakeGen(d)
            C.ensure_references(PROT, gen, store, kinds=("front34", "fullbody"))
            gen2 = FakeGen(d)
            C.ensure_references(PROT, gen2, store)
            self.assertEqual([c["kind"] for c in gen2.calls], ["sidewalk", "hands"])
            Path(store.list()["hands"]).write_bytes(b"not a picture")
            self.assertTrue(store.validate("hands"))
            gen3 = FakeGen(d)
            C.ensure_references(PROT, gen3, store)
            self.assertEqual([c["kind"] for c in gen3.calls], ["hands"])

    def test_validate_catches_small_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            store = C.ReferenceStore(d, "k")
            store.add("front34", img(Path(d) / "a.png", size=(64, 64)), "h")
            self.assertTrue(any("smaller" in p for p in store.validate()))
            store.list()
            Path(store.dir / "front34.png").unlink()
            self.assertTrue(any("missing" in p for p in store.validate()))
            self.assertEqual(store.list(), {})
            with self.assertRaises(ValueError):
                store.add("x", Path(d) / "a.gif", "h")

    def test_generator_returning_nothing_stops(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                C.ensure_references(PROT, lambda r: None, C.ReferenceStore(d, "k"))

    def test_flow_generator_wrapper_with_fake_client(self):
        with tempfile.TemporaryDirectory() as d:
            class Client:
                def __init__(s): s.subs, s.sent = [], None
                def subscribe(s, fn): s.subs.append(fn); return lambda: s.subs.remove(fn)
                def generate(s, prompts, settings=None, prompt_keys=None): s.sent = (prompts, settings, prompt_keys)
                def wait_for(s, pred, timeout=0):
                    f = img(Path(s.sent[1]["outputDir"]) / "001.png")
                    for fn in list(s.subs):
                        fn({"type": "PROMPT_RESULT", "index": 0, "status": "done", "path": f})
                    return {"type": "GENERATE_DONE"}
            c = Client()
            gen = C.make_flow_generator(c, Path(d) / "flow")
            store = C.ReferenceStore(d, "k")
            C.ensure_references(PROT, gen, store, kinds=("front34", "fullbody"))
            self.assertEqual(len(store.list()), 2)
            self.assertEqual(c.sent[1]["mediaKind"], "image")
            self.assertEqual(len(c.sent[1]["referenceImages"]), 1)


class Plan(unittest.TestCase):
    def test_order_and_counts_with_empty_store(self):
        with tempfile.TemporaryDirectory() as d:
            store = C.ReferenceStore.for_project(d, PROT)
            plan = C.plan_generation(shots(), PROT, {}, store=store)
            c = plan["counts"]
            self.assertEqual((c["reference_images"], c["character_shots"], c["other_new_shots"], c["images"]), (4, 2, 2, 8))
            self.assertEqual(c["skipped"], 1)
            self.assertTrue(plan["refs_pending"])
            self.assertEqual(plan["reference_requests"][0]["kind"], "front34")
            self.assertEqual([r["shot_id"] for r in plan["character_requests"]], ["s002", "s004"])
            self.assertEqual([r["shot_id"] for r in plan["other_requests"]], ["s001", "s005"])
            self.assertEqual(plan["runs"][0]["shot_ids"][0], "s002")                     # character runs before the plain ones
            self.assertEqual(plan["runs"][-1]["references"], [])
            self.assertIn("images to generate: 8", plan["report"])

    def test_resume_skips_made_references_and_shots_and_budget_defers(self):
        with tempfile.TemporaryDirectory() as d:
            store = C.ReferenceStore.for_project(d, PROT)
            C.ensure_references(PROT, FakeGen(d), store)
            plan = C.plan_generation(shots(), PROT, {}, store=store)
            self.assertFalse(plan["refs_pending"])
            self.assertEqual(plan["counts"]["reference_images"], 0)
            self.assertEqual(plan["counts"]["images"], 4)
            plan2 = C.plan_generation(shots(), PROT, {"max_images": 2}, store=store, done_shot_ids=["s002"])
            self.assertEqual(plan2["counts"]["images"], 2)
            self.assertEqual(plan2["deferred"], ["s005"])
            plan3 = C.plan_generation(shots(), PROT, {"max_images": 2}, store=C.ReferenceStore(Path(d) / "empty", "z"))
            self.assertEqual(plan3["counts"]["reference_images"], 4)                     # references are never cut
            self.assertEqual(plan3["counts"]["images"], 4)

    def test_batches_respect_agent_limit(self):
        many = [{"shot_id": f"n{i}", "scene_no": i, "text": "", "prompt_en": "x" * 50, "picture": "new", "character": False} for i in range(60)]
        plan = C.plan_generation(many, PROT, {}, references={k: f"/x/{k}.png" for k in C.REFERENCE_KINDS})
        self.assertEqual([len(b) for b in plan["runs"][0]["batches"]], [24, 24, 12])
        self.assertEqual(plan["counts"]["agent_requests"], 3)


class Consistency(unittest.TestCase):
    def test_flags_wrong_palette_and_writes_contact_sheet(self):
        with tempfile.TemporaryDirectory() as d:
            good = [img(Path(d) / f"g{i}.png", (160 + i, 90, 50)) for i in range(5)]
            bad = img(Path(d) / "bad.png", (30, 60, 200))
            res = C.consistency_check(good + [bad], sheet_path=Path(d) / "sheet.png")
            self.assertEqual(res["flagged"], [5])
            self.assertTrue(Path(res["sheet"]).is_file())
            self.assertEqual(C.consistency_check(good)["flagged"], [])

    def test_bbox_ignores_the_rest_of_the_picture(self):
        with tempfile.TemporaryDirectory() as d:
            a = Image.new("RGB", (400, 200), (30, 60, 200))
            ImageDraw.Draw(a).rectangle([0, 0, 100, 200], fill=(160, 90, 50))
            a.save(Path(d) / "a.png")
            b = img(Path(d) / "b.png", (160, 90, 50))
            hist_whole = C.palette_histogram(Path(d) / "a.png")
            hist_box = C.palette_histogram(Path(d) / "a.png", (0, 0, 0.25, 1))
            self.assertGreater(C._intersect(hist_box, C.palette_histogram(b)), C._intersect(hist_whole, C.palette_histogram(b)))


if __name__ == "__main__":
    unittest.main()
