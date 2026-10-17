"""Every stock clip in a Weather video is checked for where it was filmed and what it shows (weather/footage_geo.py).

The records below are real ones from the #007 render audit (2026-10-15): Oklahoma flood lines got rice fields filmed in Vietnam,
a Thames flood and a Dhaka street; a tornado line got a missile-damaged building in Ukraine; "tornado damage" got a forest fire."""

import json
import tempfile
import unittest
from pathlib import Path

from weather.footage_geo import check_scenes, make_resolver, verdict


def rec(slug, author="", **kw):
    return {"status": "complete", "provider": "pexels", "provider_asset_id": slug.rsplit("-", 1)[-1], "author": author,
            "source_url": f"https://www.pexels.com/video/{slug}/", **kw}


class TheVerdicts(unittest.TestCase):
    def test_foreign_war_and_unrelated_clips_are_rejected(self):
        for req, r in [("damaged mobile home after a storm", rec("destruction-after-a-missile-attack-in-ukraine-12734644", "Alex Moisieiev")),
                       ("aerial view of floodwater", rec("aerial-view-of-river-thames-flooded-landscape-34930882", "Mark Holmes")),
                       ("flooded street", rec("flooded-city-street-with-people-walking-38549951", "Somogro Bangladesh")),
                       ("tornado damage aerial view", rec("aerial-view-of-forest-fire-and-dense-smoke-30937715", "K")),
                       ("hailstones bouncing on the ground, wide shot", rec("time-lapse-of-ants-in-the-ground-4168762", "Aarif Patel")),
                       ("lake from above", rec("serene-aerial-view-of-a-vast-lake-landscape-32336987"))]:
            ok, why = verdict(req, r)
            self.assertFalse(ok, (req, why))

    def test_relevant_footage_is_kept_without_proof_of_where_it_was_filmed(self):
        # the owner's rule (2026-10-15): relevant footage, not verified footage; only a named foreign place, war or an unrelated
        # subject is refused
        self.assertFalse(verdict("aerial view of floodwater", rec("aerial-view-of-flooded-rural-landscape-35035439", "NGUYỄN THÀNH NHƠN"))[0])
        self.assertTrue(verdict("aerial view of floodwater", rec("aerial-view-of-flooded-rural-landscape-35035439", "Mark Holmes"))[0])
        self.assertTrue(verdict("dark clouds", rec("a-dark-storm-cloud-is-seen-in-the-sky-17311357", "Nguyễn Văn A"))[0])   # sky: anywhere
        self.assertTrue(verdict("flooded street", rec("flooded-street-in-houston-texas-after-harvey-8888"))[0])
        self.assertFalse(verdict("hailstones bouncing", rec("bouncing-fruits-2541966"))[0])
        self.assertFalse(verdict("lightning", rec("dramatic-night-lightning-over-samarkand-396646"))[0])

    def test_a_clip_that_shows_no_place_may_come_from_anywhere(self):
        for slug in ("a-dark-storm-cloud-is-seen-in-the-sky-17311357", "hail-storm-in-slow-motion-6040646", "raindrops-on-ground-13717835"):
            self.assertTrue(verdict("dark storm clouds rolling", rec(slug, "Vinay"))[0], slug)


class TheResolver(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.calls = []

    def manifest(self):
        return json.loads((self.dir / ".asset_manifest.json").read_text())

    def fake_base(self, answers):
        """A stand-in for the app's resolver: request text -> the clip record a provider would give."""
        from asset_manager import AssetManifest

        def base(rows, images_dir, log=print, **kw):
            m = AssetManifest(Path(images_dir))
            for r in rows:
                self.calls.append(r["prompt"])
                n = r["scene_number"]
                old = m.get(n)
                if old and old.get("status") == "complete":
                    continue   # the cache: a complete record is reused, as the app does
                f = Path(images_dir) / f"{int(n):03d}.mp4"
                f.write_bytes(b"x" * 2000)
                m.set(n, {**answers(r["prompt"]), "local_path": str(f), "stock_query": r["prompt"]})
        return base

    def test_a_foreign_clip_is_asked_again_as_a_placeless_shot_and_never_comes_back(self):
        def answers(prompt):
            if prompt == "flooded street":
                return rec("flooded-street-market-with-vendors-and-buyers-38542633", "Somogro Bangladesh")
            return rec("heavy-rain-falling-into-water-close-up-777")
        resolve = make_resolver(lambda m: None, base=self.fake_base(answers))
        rows = [{"scene_number": "1", "asset_type": "stock_video", "prompt": "flooded street"},
                {"scene_number": "2", "asset_type": "stock_video", "prompt": "dark storm clouds rolling"}]
        resolve(rows, self.dir)
        m = self.manifest()
        self.assertIn("heavy-rain-falling-into-water", m["001"]["source_url"])
        self.assertEqual(m["001"]["status"], "complete")
        rejected = json.loads((self.dir / ".geo_rejected.json").read_text())
        self.assertIn("pexels:38542633", rejected)
        # a later run that finds the rejected clip in its cache (a stale record) rejects it again, before it reaches the video
        from asset_manager import AssetManifest

        AssetManifest(self.dir).set("1", rec("flooded-street-market-with-vendors-and-buyers-38542633", "Somogro Bangladesh",
                                             local_path=str(self.dir / "001.mp4")))
        bad = check_scenes(rows, self.dir, lambda m: None)
        self.assertEqual([r["scene_number"] for r, _w in bad], ["1"])

    def test_with_no_clip_that_passes_the_scene_is_left_out_not_filled(self):
        resolve = make_resolver(lambda m: None, base=self.fake_base(lambda p: rec("aerial-view-of-forest-fire-with-smoke-30937710")))
        resolve([{"scene_number": "3", "asset_type": "stock_video", "prompt": "tornado damage aerial view"}], self.dir)
        m = self.manifest()
        self.assertEqual(m["003"]["status"], "failed")
        self.assertFalse((self.dir / "003.mp4").exists())
        self.assertEqual(len(self.calls), 4)   # the request, then the three placeless ones for a tornado

    def test_a_clip_you_chose_by_hand_is_yours(self):
        from asset_manager import AssetManifest

        f = self.dir / "001.mp4"
        f.write_bytes(b"x" * 2000)
        AssetManifest(self.dir).set("1", {**rec("aerial-view-of-flooded-rural-landscape-35035439"), "local_path": str(f), "user_override": True})
        self.assertEqual(check_scenes([{"scene_number": "1", "asset_type": "stock_video", "prompt": "flood"}], self.dir, lambda m: None), [])


class TheWiring(unittest.TestCase):
    def test_both_weather_render_paths_check_their_footage(self):
        for f in ("weather/generate.py", "weather/newsdoc/generate.py"):
            self.assertIn("make_resolver", Path(f).read_text(encoding="utf-8"), f)

    def test_news_doc_place_b_roll_is_vetted_and_its_last_resort_has_no_place(self):
        from weather.footage_geo import shows_place, verdict
        from weather.newsdoc.plan import DEFAULT_STOCK, stock_request

        self.assertFalse(any(shows_place(v) for v in DEFAULT_STOCK.values()))
        # a line about fields asks for fields (newsdoc.plan.SCENES); a clip of fields whose record points abroad is still refused
        req = stock_request("Water covered the fields and the roads near the river.", "flood")
        self.assertTrue(shows_place(req), req)
        abroad = {"source_url": "https://www.pexels.com/video/flooded-rice-paddy-fields-after-rain-123/", "author": "Nguyễn Văn"}
        self.assertFalse(verdict(req, abroad)[0])


if __name__ == "__main__":
    unittest.main()
