"""Hybrid Map: Generate gets the scenes and stops, Render draws; no Visual Plan row stays QUEUED; nothing is drawn without its scene;
titles and captions take turns between looks and the narration gets more graphics (Hybrid only).

Every provider and the renderer are fakes: nothing is downloaded, generated or drawn and no Flow credit is spent."""

from __future__ import annotations

import unittest
from pathlib import Path

import gfx_templates as G
from pakmap import sourcing as sc
from test_hybrid import TestGenerate as _Gen, plan
from test_pakmap_sourcing import FakeManifest, FakeProviders, Row


class TestScenesThenRender(_Gen):
    def test_media_only_fetches_every_scene_and_draws_nothing(self):
        r = self.run_gen(plan(), media_only=True)
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.media_ready, 1)
        self.assertEqual(self.specs, [])                       # the renderer was never called
        self.assertIsNone(r.output_path)
        self.assertEqual([x["asset_type"] for x in self.fake.calls[0]], ["stock_video"])

    def test_render_after_the_scenes_reuses_them(self):
        self.assertTrue(self.run_gen(plan(), media_only=True).ok)
        r = self.run_gen(plan())
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(len(self.specs), 1)
        self.assertEqual(self.fake.calls[-1], [])              # nothing fetched again

    def test_a_scene_missing_from_the_table_is_fetched_not_dropped(self):
        r = self.run_gen(plan(), scene_rows=[Row(99, "stock_video", "unrelated")])   # a table from another plan
        self.assertTrue(r.ok, r.errors)
        self.assertEqual([x["prompt"] for x in self.fake.calls[0]], ["farmers in a field"])
        ev = {e["id"]: e for e in self.specs[0]["events"]}
        self.assertTrue(ev["b2_c1"]["media"].endswith("001.mp4"))

    def test_a_scene_that_failed_stops_before_drawing(self):
        self.fake.fail = {"farmers in a field"}
        r = self.run_gen(plan())
        self.assertFalse(r.ok)
        self.assertEqual(r.unresolved, ["1"])
        self.assertEqual(self.specs, [])


class TestNoRowStaysQueued(unittest.TestCase):
    def setUp(self):
        import tempfile

        FakeManifest.store = {}
        self.tmp = tempfile.TemporaryDirectory()
        self.media = Path(self.tmp.name) / "media"

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_scene_gets_its_final_state_even_when_the_provider_never_reported_it(self):
        done = {}
        fake = FakeProviders(fail={"B"})       # the fake never calls on_scene_complete, like a repeat or a retry that failed again
        rows = [Row(1, "stock_image", "A"), Row(2, "stock_image", "B"), Row(3, "stock_image", "A")]
        sc.fetch_scenes(rows, self.media, resolver=fake.resolve, find_file=fake.find, manifest_cls=FakeManifest, log=lambda m: None, dedupe=True,
                        on_scene_complete=lambda s, res: done.__setitem__(str(s.scene_number), res))
        self.assertEqual(sorted(done), ["1", "2", "3"])
        self.assertTrue(done["1"].ok and done["3"].ok)
        self.assertFalse(done["2"].ok)

    def test_a_scene_the_provider_reported_is_not_reported_twice(self):
        calls = []

        def resolve(rows, images_dir, on_scene_complete=None, **kw):
            FakeProviders().resolve(rows, images_dir)
            for r in rows:
                on_scene_complete(Row(r["scene_number"], r["asset_type"], r["prompt"]), None)

        sc.fetch_scenes([Row(1, "stock_image", "A")], self.media, resolver=resolve, find_file=FakeProviders().find, manifest_cls=FakeManifest,
                        log=lambda m: None, on_scene_complete=lambda s, res: calls.append(s.scene_number))
        self.assertEqual(calls, ["1"])


class TestGraphicsVariety(unittest.TestCase):
    EVENTS = [{"id": f"t{i}", "type": "hud_title", "label": f"PLACE {i}", "t_in": 10.0 * i, "t_out": 10.0 * i + 4} for i in range(4)] + \
             [{"id": f"c{i}", "type": "caption", "text": f"caption {i}", "t_in": 10.0 * i + 5, "t_out": 10.0 * i + 8} for i in range(4)]

    def test_hybrid_titles_and_captions_take_turns(self):
        out = {e["id"]: e["template"]["id"] for e in G.apply_doc_style(self.EVENTS, rotate=True)}
        self.assertEqual([out[f"t{i}"] for i in range(4)], ["yellow_tag", "tag_headline"] * 2)
        self.assertEqual([out[f"c{i}"] for i in range(4)], ["typed_caption", "subtitle_gold"] * 2)
        self.assertEqual([e["id"] for e in G.apply_doc_style(self.EVENTS, rotate=True)], [e["id"] for e in self.EVENTS])   # draw order kept

    def test_other_styles_keep_one_look(self):
        out = {e["template"]["id"] for e in G.apply_doc_style(self.EVENTS)}
        self.assertEqual(out, {"yellow_tag", "typed_caption"})

    def test_the_same_plan_always_gets_the_same_looks(self):
        a = [e["template"]["id"] for e in G.apply_doc_style(self.EVENTS, rotate=True)]
        b = [e["template"]["id"] for e in G.apply_doc_style(list(reversed(self.EVENTS)), rotate=True)][::-1]
        self.assertEqual(a, b)

    def test_rich_allows_more_than_normal(self):
        self.assertGreater(G.RICH["max_per_minute"], G.NORMAL["max_per_minute"])
        self.assertGreater(G.RICH["footage_share"], G.NORMAL["footage_share"])
        self.assertEqual(G.NORMAL["max_per_minute"], G.MAX_PER_MINUTE)       # pakMap and Normal Video are unchanged


if __name__ == "__main__":
    unittest.main()
