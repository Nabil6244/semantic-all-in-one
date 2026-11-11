"""2026-11-12 owner: final War videos need video and images, not only graphics. Library fallback before graphics, facility photo cards built from
the narration, Flow pictures labelled as AI illustrations. No network, no Flow."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from cinematic_explainer.war import direction as D, library as LIB


class Fallback(unittest.TestCase):
    def test_subjects_follow_the_line(self):
        self.assertEqual(LIB.fallback_subjects("On the night of the ninth of November, drones attacked the Kirishi oil refinery.")[0], "refinery_fire")
        self.assertIn("factory_workers", LIB.fallback_subjects("It is going after the factories that build the weapons."))
        self.assertIn("missile_launch", LIB.fallback_subjects("That is a direct link between the oil war and the missiles that Russia fires at Ukrainian cities."))
        self.assertEqual(LIB.fallback_subjects("For thousands of families, that is the most important news."), [])

    def _lib(self, d):
        lib = Path(d) / "lib"
        (lib / "refinery_fire").mkdir(parents=True)
        clips = []
        for i, url in enumerate(["https://www.youtube.com/watch?v=aaaaaaaaaaa", "https://www.youtube.com/watch?v=aaaaaaaaaaa",
                                 "https://www.youtube.com/watch?v=bbbbbbbbbbb"]):
            f = lib / "refinery_fire" / f"refinery_fire_00{i + 1}.mp4"
            f.write_bytes(b"x")
            clips.append({"file": f"refinery_fire/{f.name}", "subject": "refinery_fire", "words": "refinery fire smoke", "url": url})
        (lib / "index.json").write_text(json.dumps({"clips": clips}))
        return lib

    def test_fills_empty_rows_with_illustrative_clips_and_respects_reuse(self):
        from asset_manager import AssetManifest

        with tempfile.TemporaryDirectory() as d:
            lib = self._lib(d)
            imgs = Path(d) / "assets"
            imgs.mkdir()
            scenes = [{"scene_no": i, "text": "Drones hit the oil refinery overnight.", "start": 100.0 * i, "end": 100.0 * i + 5} for i in (1, 2, 3, 4)]
            scenes.append({"scene_no": 5, "text": "For thousands of families, that is the news.", "start": 600.0, "end": 605.0})
            rows = [NS(scene_number=str(s["scene_no"]), script_segment=s["text"], asset_type="youtube_video", prompt="") for s in scenes]
            orig = LIB.usable_clips
            LIB.usable_clips = lambda clips, lib, log=None, **k: clips          # the frame check needs real video files
            try:
                got = LIB.fallback(scenes, rows, imgs, lib)
            finally:
                LIB.usable_clips = orig
            self.assertEqual(got, ["1", "2", "3"])                              # each library clip once per film; not the families line
            srcs = [AssetManifest(imgs).get(n)["source_url"] for n in got]
            self.assertTrue(all(srcs.count(u) <= LIB.MAX_USES for u in srcs))
            man = AssetManifest(imgs)
            rec = man.get("1")
            self.assertEqual(rec["match_level"], "illustrative")
            self.assertTrue(rec["library_fallback"])
            self.assertIsNone(man.get("5"))

    def test_switch_off(self):
        self.assertEqual(LIB.fallback([], [], Path("/nonexistent"), settings={LIB.FALLBACK_SETTING: False}), [])


class FacilityCard(unittest.TestCase):
    def test_facts_are_the_narrations_words(self):
        f = D.facility_facts("Kirishi is run by Surgutneftegas. It is Russia's second largest refinery, with a capacity of up to 21 million "
                             "tonnes of crude oil a year.")
        self.assertEqual(f["name"], "Kirishi refinery")
        self.assertEqual({s["label"]: s["value"] for s in f["specs"]}["Operator"], "Surgutneftegas")
        self.assertIn("21 million tonnes", {s["label"]: s["value"] for s in f["specs"]}["Capacity"])
        self.assertEqual(D.facility_facts("The Morozov plant belongs to Rostec, Russia's giant state defence corporation.")["specs"],
                         [{"label": "Owner", "value": "Rostec"}])
        self.assertIsNone(D.facility_facts("For Russia, defending against these attacks is a huge problem."))

    def test_csv_facility_card_with_a_flow_picture_is_labelled(self):
        from cinematic_explainer.war import planner as P

        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "k.png"
            from PIL import Image

            Image.new("RGB", (64, 36), (90, 90, 90)).save(img)
            r = {"_no": "1", "text": "Kirishi is run by Surgutneftegas.", "_start": 0.0, "_end": 6.0, "words": None, "images": str(img),
                 "subject": "Kirishi refinery"}
            ly, why = D._csv_layer("facility", r, dict(P.DEFAULTS), P._default_catalog())
            self.assertIsNotNone(ly, why)
            self.assertEqual(ly.kind, "lay_equipment_hero")
            self.assertEqual(ly.params["image_credit"], "AI illustration · Google Flow")
            self.assertEqual(ly.params["status"], "illustrative")
            self.assertEqual(ly.params["class_label"], "Oil refinery")          # never 'military equipment' over a refinery


class FlowLabels(unittest.TestCase):
    def test_flow_credit_and_style(self):
        from cinematic_explainer.war import flow_pictures as FP

        self.assertIn("AI illustration", FP.credit())
        self.assertIn("no text", FP.STYLE)


if __name__ == "__main__":
    unittest.main()


class PictureFloor(unittest.TestCase):
    def test_cards_over_a_clip_give_way_until_the_floor(self):
        from cinematic_explainer.render import Layer

        shot = NS(path="/x/clip.mp4", start=0.0, end=20.0, seek=0.0)
        plan = NS(shots=[shot], layers=[Layer("kit_kinetic", 0.0, 10.0, {}, dim=False), Layer("tac_map", 10.0, 20.0, {"csv_graphic": True}, dim=False),
                                        Layer("lay_timeline", 20.0, 30.0, {}, dim=False)])
        self.assertLess(D.picture_share(plan, 30.0), 0.30)
        D._picture_floor(plan, 30.0, {}, 0.30)
        self.assertGreaterEqual(D.picture_share(plan, 30.0), 0.30)
        kinds = [ly.kind for ly in plan.layers]
        self.assertIn("lay_timeline", kinds)                                     # never removed
        self.assertIn("tac_map", kinds)                                          # the CSV's map stays (as an insert if needed)


class Handoffs(unittest.TestCase):
    def test_two_cards_in_a_row_cross_fade_directly(self):
        """2026-11-12 slice: map -> 0.2 s of the clip underneath -> radar card (and card -> blank -> card): the first stays until the
        second has faded in."""
        from cinematic_explainer.render import Layer

        plan = NS(shots=[NS(path="/x/c.mp4", start=0.0, end=20.0, seek=0.0)],
                  layers=[Layer("tac_map", 0.0, 7.0, {}, dim=False), Layer("kit_radar", 7.2, 12.0, {}, dim=False),
                          Layer("kit_dossier", 12.0, 16.0, {}, dim=False)])
        c = {}
        D._handoffs(plan, c)
        m, r, dz = plan.layers
        self.assertGreaterEqual(m.end, r.start + 0.5)
        self.assertGreaterEqual(r.end, dz.start + 0.5)
        self.assertEqual(c["handoffs"], 2)
