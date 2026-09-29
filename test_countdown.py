"""Countdown ("35 wild facts") structure: detection from narration, the fact
tags + hook graphics (timing, look, editorial compile), fact-opening maps in
AI plans, and the map rule for a country parent."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from editorial.countdown import countdown_graphics, detect_countdown, word_to_number

SCRIPT = [
    "Florida is a strange state. Here are 35 wild facts about it that most people never learn.",
    "35. The Roof of Florida. Britton Hill is the highest point in the state.",
    "It stands just 345 feet above sea level.",
    "Number 34: The Island of Strange Company. St. Vincent Island hides a secret.",
    "Fact 33 - Florida's Rust Belt. Paper mills once ruled the Panhandle.",
    "Number thirty-two. The Oldest City. St. Augustine was founded in 1565.",
]


class TestDetection(unittest.TestCase):
    def test_all_heading_styles_and_the_hook(self):
        c = detect_countdown(SCRIPT)
        self.assertEqual([(f.number, f.title, f.scene_index) for f in c.facts], [
            (35, "The Roof of Florida", 1), (34, "The Island of Strange Company", 3),
            (33, "Florida's Rust Belt", 4), (32, "The Oldest City", 5)])
        self.assertEqual(c.facts[0].tag_text, "35. THE ROOF OF FLORIDA")
        self.assertEqual((c.hook.text, c.hook.scene_index), ("35 WILD FACTS", 0))
        self.assertGreater(c.hook.offset, 0.3)  # said mid-line, not at its start

    def test_spoken_number_words(self):
        self.assertEqual(word_to_number("thirty-four"), 34)
        self.assertEqual(word_to_number("twelve"), 12)
        self.assertIsNone(word_to_number("seventy-zero"))
        c = detect_countdown(["Here are thirty five crazy things about Mars.", "Number three. Dust.",
                              "Number two. Ice.", "Number one. Moons."])
        self.assertEqual(([f.number for f in c.facts], c.hook.text), ([3, 2, 1], "35 CRAZY THINGS"))

    def test_ordinary_scripts_are_not_countdowns(self):
        self.assertIsNone(detect_countdown(["3 men died. The river rose.", "In 1931, crews arrived.",
                                            "Thirty people lived there.", "2. It was hot."]))
        self.assertIsNone(detect_countdown(["1. First.", "2. Second.", "7. Random."]))  # not in order
        self.assertIsNone(detect_countdown(["10. Ten.", "9. Nine."]))  # fewer than three


def _scenes(n, length=5.0):
    return [SimpleNamespace(scene_number=str(i + 1), start=i * length, end=(i + 1) * length) for i in range(n)]


class TestGraphics(unittest.TestCase):
    def test_tags_start_when_the_heading_is_said_and_end_before_the_next(self):
        c = detect_countdown(SCRIPT)
        specs = {g.graphic_id: g for g in countdown_graphics(_scenes(len(SCRIPT)), c)}
        tag35, tag34 = specs["countdown_tag_35"], specs["countdown_tag_34"]
        # A heading at the very start of a scene: the tag waits 0.3 s for the cut to settle.
        self.assertEqual((tag35.start, tag35.text.text, tag35.payload["template"]), (5.3, "35. THE ROOF OF FLORIDA", "countdown_tag"))
        self.assertAlmostEqual(tag35.end - tag35.start, 3.8, places=3)
        self.assertGreater(tag34.start, 15.0)  # "Number 34" is said just after the scene starts
        hook = specs["countdown_hook"]
        self.assertTrue(0 < hook.start < 5.0)
        self.assertEqual((hook.text.text, hook.animation), ("35 WILD FACTS", "POP"))

    def test_the_look_orange_tag_bottom_left_yellow_hook_centred(self):
        from PIL import Image

        from graphics.render import _render_countdown_hook, _render_countdown_tag

        with tempfile.TemporaryDirectory() as tmp:
            tag = Image.open(_render_countdown_tag("34. The Roof of Florida", Path(tmp) / "t.png", 1920, 1080)).convert("RGBA")
            x0, y0, x1, y1 = tag.getbbox()
            self.assertTrue(x0 < 1920 * 0.05 and x1 < 1920 * 0.62 and y0 > 1080 * 0.7 and y1 <= 1080 * 0.85)
            r, g, b, a = tag.getpixel((x0 + 3, y0 + 3))
            self.assertEqual((r, g, b), (246, 146, 30))
            hook = Image.open(_render_countdown_hook("35 wild facts", Path(tmp) / "h.png", 1920, 1080)).convert("RGBA")
            hx0, hy0, hx1, hy1 = hook.getbbox()
            self.assertAlmostEqual((hx0 + hx1) / 2, 960, delta=40)
            self.assertAlmostEqual((hy0 + hy1) / 2, 540, delta=60)
            yellow = sum(1 for px in hook.getdata() if px[0] > 240 and px[1] > 200 and px[2] < 80 and px[3] > 200)
            self.assertGreater(yellow, 5000)

    def test_animations_map_to_real_overlay_motions(self):
        from graphics.schema import ANIMATION_TO_OVERLAY

        self.assertEqual((ANIMATION_TO_OVERLAY["SLIDE_IN"], ANIMATION_TO_OVERLAY["POP"]), ("slide_in", "scale_fade"))

    def test_editorial_compile_adds_tags_and_drops_clashing_panels(self):
        from editorial.engine import _add_countdown_graphics
        from graphics.schema import GraphicSpec, GraphicsPlan, TextOverlaySpec

        plan = SimpleNamespace(scenes=[SimpleNamespace(scene_number=str(i + 1), start=i * 5.0, end=(i + 1) * 5.0,
                                                       narration_excerpt=t[:40]) for i, t in enumerate(SCRIPT)],
                               narrations_by_scene={str(i + 1): t for i, t in enumerate(SCRIPT)})
        clash = GraphicSpec(graphic_id="lt", role="LOWER_THIRD", start=5.5, end=7.0,
                            text=TextOverlaySpec(role="LOWER_THIRD", text="Britton Hill"))
        keep = GraphicSpec(graphic_id="stat", role="STATISTIC", start=5.5, end=7.0,
                           text=TextOverlaySpec(role="STATISTIC", text="345 FT"))
        gplan = GraphicsPlan(specs=[clash, keep])
        _add_countdown_graphics(plan, gplan)
        ids = [g.graphic_id for g in gplan.specs]
        self.assertNotIn("lt", ids)
        self.assertIn("stat", ids)
        self.assertIn("countdown_tag_35", ids)
        self.assertIn("countdown_hook", ids)

    def test_a_normal_script_gets_no_countdown_graphics(self):
        from editorial.engine import _add_countdown_graphics
        from graphics.schema import GraphicsPlan

        plan = SimpleNamespace(scenes=[SimpleNamespace(scene_number="1", start=0.0, end=5.0, narration_excerpt="The dam rose.")],
                               narrations_by_scene={"1": "The dam rose."})
        gplan = GraphicsPlan(specs=[])
        _add_countdown_graphics(plan, gplan)
        self.assertEqual(gplan.specs, [])


def _vs(i, text):
    from visual_director.schema import VisualScene

    return VisualScene(scene_id=i, narration=text, visual_goal="g", visual_description="d", asset_type="stock_video",
                       provider_preference="stock_video", search_queries=["q"], timestamp_needed=False,
                       timestamp_hint="", duration=4, importance="medium", fallbacks=[], visual_treatment="",
                       transition="cut")


class TestFactOpeningMaps(unittest.TestCase):
    def test_each_fact_opens_on_its_place_title_first(self):
        from visual_director.map_pass import add_map_scenes
        from visual_director.schema import VisualPlan

        plan = VisualPlan(topic="t", scenes=[
            _vs(1, "Here are 35 wild facts about Florida."),
            _vs(2, "35. The Roof of Florida."),
            _vs(3, "Britton Hill sits near the Alabama border."),     # the title's place wins
            _vs(4, "34. The Island of Strange Company."),
            _vs(5, "An island off the coast hides zebras."),          # no known place: no map
            _vs(6, "33. The Rust Belt."),
            _vs(7, "Paper mills ruled towns across Georgia and Florida."),
        ])
        add_map_scenes(plan)
        maps = {s.scene_id: s.visual_description for s in plan.scenes if s.asset_type == "map"}
        self.assertEqual(maps, {2: "United States of America > Florida",
                                6: "United States of America > Georgia"})  # the US state, in a script about Florida

    def test_country_parent_only_disambiguates(self):
        from map_scene.places import find_place
        from map_scene.render import _drawn_places

        usa, florida = find_place("United States of America"), find_place("Florida")
        self.assertEqual(list(_drawn_places({"parent": usa, "focus": florida})), ["focus"])
        panhandle = find_place("Florida Panhandle")
        self.assertEqual(list(_drawn_places({"parent": florida, "focus": panhandle})), ["parent", "focus"])


if __name__ == "__main__":
    unittest.main()
