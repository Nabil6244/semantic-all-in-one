"""Zoom-blur transition (maps + countdown facts, with whoosh) and big yellow
keyword callouts ("345 FT ABOVE SEA LEVEL")."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from editorial.keyword_callouts import callout_graphics, find_callouts, spelled_to_number
from editorial.zoom_blur import ZOOM_BLUR, apply_zoom_blur, mark_zoom_blur_transitions, zoom_blur_filter


def _plan(n, length=5.0, narrations=None):
    scenes = [SimpleNamespace(scene_number=str(i + 1), start=i * length, end=(i + 1) * length, duration=length,
                              narration_excerpt=(narrations or [""] * n)[i], transition_in=None) for i in range(n)]
    return SimpleNamespace(scenes=scenes)


class TestWhereZoomBlurGoes(unittest.TestCase):
    def test_into_and_out_of_maps_never_the_first_scene(self):
        plan = _plan(6)
        marked = mark_zoom_blur_transitions(plan, map_scene_numbers={"1", "4"})
        self.assertEqual(marked, ["2", "4", "5"])  # out of map 1, into map 4, out of map 4
        self.assertEqual(plan.scenes[3].transition_in, ZOOM_BLUR)
        self.assertIsNone(plan.scenes[0].transition_in)

    def test_at_each_countdown_fact(self):
        narr = ["Here are 35 wild facts.", "35. The Roof. A hill.", "It is tall.", "34. The Island. Zebras.",
                "More zebras.", "33. The Mills. Paper."]
        plan = _plan(6, narrations=narr)
        self.assertEqual(mark_zoom_blur_transitions(plan, narrations_by_scene=None), ["2", "4", "6"])

    def test_very_short_clips_keep_a_plain_cut(self):
        plan = _plan(3, length=0.6)
        self.assertEqual(mark_zoom_blur_transitions(plan, map_scene_numbers={"2"}), [])

    def test_a_zoom_blur_cut_has_no_fade(self):
        import video_generator as vg

        self.assertEqual(vg.transition_fade_params("zoom_blur", 5.0), (0.0, 0.0, "black"))

    def test_every_zoom_blur_cut_gets_a_whoosh(self):
        from smart_editing import _with_zoom_blur_whooshes

        plan = _plan(4)
        plan.scenes[2].transition_in = ZOOM_BLUR
        picks = _with_zoom_blur_whooshes([{"scene_number": "2", "style": "fade", "sfx": False}], plan)
        self.assertIn({"scene_number": "3", "style": ZOOM_BLUR, "sfx": True, "source": "zoom_blur"}, picks)
        self.assertEqual(picks[0]["style"], "fade")  # other transitions untouched


class TestZoomBlurFilter(unittest.TestCase):
    def test_head_and_tail_windows(self):
        vf = zoom_blur_filter(5.0, head=True, tail=True, width=1920, height=1080, fps=30)
        self.assertIn("zoompan=", vf)
        self.assertIn("rgbashift=rh=-48:bh=48", vf)
        self.assertIn("gte(t,4.8650)", vf)  # strong blur in the tail's second half
        self.assertIn("lt(t,0.1350)", vf)  # and in the head's first half
        self.assertTrue(vf.startswith("zoompan") and "format=gbrp" in vf and vf.endswith("format=yuv420p"))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not available")
    def test_pass_keeps_the_duration_and_blurs_only_the_edges(self):
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "c.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=2",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
            before = self._frames(clip)
            self.assertTrue(apply_zoom_blur(clip, head=False, tail=True, width=320, height=180, fps=30))
            after = self._frames(clip)
            self.assertEqual(len(before), len(after))
            self.assertLess(abs(after[15] - before[15]).mean(), 3.0)       # middle unchanged
            self.assertGreater(abs(after[-2] - before[-2]).mean(), 15.0)   # tail zoomed + blurred

    def test_too_short_or_missing_clip_is_left_alone(self):
        self.assertFalse(apply_zoom_blur(Path("/nonexistent.mp4"), head=True, tail=False, width=320, height=180, fps=30))

    @staticmethod
    def _frames(path):
        import numpy as np

        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(raw, dtype=np.uint8).reshape(-1, 180, 320).astype(int)


class TestCallouts(unittest.TestCase):
    def test_measures_money_and_names(self):
        cases = {
            "Britton Hill stands just 345 feet above sea level.": "345 FT ABOVE SEA LEVEL",
            "It stands only three hundred and forty-five feet above sea level.": "345 FT ABOVE SEA LEVEL",
            "The island covers 12,492 acres.": "12,492 ACRES",
            "About 40 percent of workers left.": "40%",
            "Eglin is a billion-dollar air force base on the coast.": "BILLION DOLLAR AIR FORCE BASE",
            "The Loomis Brothers bought the island in 1908.": "THE LOOMIS BROTHERS",
        }
        for text, want in cases.items():
            self.assertEqual(find_callouts(text)[0].text, want, text)

    def test_years_and_bare_numbers_are_not_callouts(self):
        self.assertEqual(find_callouts("In 1931 crews arrived and 3 men watched."), [])

    def test_spelled_numbers(self):
        self.assertEqual(spelled_to_number("twelve thousand four hundred ninety-two"), 12492)
        self.assertIsNone(spelled_to_number("banana"))

    def test_sparse_timed_and_never_over_a_countdown_tag(self):
        scenes = [SimpleNamespace(scene_number=str(i + 1), start=i * 3.0, end=(i + 1) * 3.0) for i in range(5)]
        narr = ["It is 345 feet tall.", "It covers 900 acres.", "It is 20 miles long.", "Now 40 percent left.",
                "The Loomis Brothers came."]
        specs = callout_graphics(scenes, narr, blocked=[(12.0, 15.0)])
        starts = [g.start for g in specs]
        self.assertTrue(all(b - a >= 7.0 for a, b in zip(starts, starts[1:])))
        self.assertTrue(all(not (12.0 <= s < 15.0) for s in starts))
        self.assertEqual((specs[0].text.text, specs[0].payload["template"], specs[0].animation),
                         ("345 FT TALL", "keyword_callout", "POP"))

    def test_callout_replaces_the_plain_panel_at_that_moment(self):
        from editorial.engine import _add_keyword_callouts
        from graphics.schema import GraphicSpec, GraphicsPlan, TextOverlaySpec

        plan = SimpleNamespace(scenes=[SimpleNamespace(scene_number="1", start=0.0, end=6.0, narration_excerpt="")],
                               narrations_by_scene={"1": "Britton Hill stands just 345 feet above sea level."})
        stat = GraphicSpec(graphic_id="stat", role="STATISTIC", start=3.0, end=5.0,
                           text=TextOverlaySpec(role="STATISTIC", text="345"))
        gplan = GraphicsPlan(specs=[stat])
        _add_keyword_callouts(plan, gplan)
        self.assertEqual([g.graphic_id for g in gplan.specs], ["callout_1"])

    def test_the_look_is_yellow_and_centred_high(self):
        from PIL import Image

        from graphics.render import render_graphic_overlay
        from graphics.schema import GraphicSpec, TextOverlaySpec

        spec = GraphicSpec(graphic_id="c", role="EMPHASIS", payload={"template": "keyword_callout"},
                           text=TextOverlaySpec(role="EMPHASIS", text="345 FT ABOVE SEA LEVEL"))
        with tempfile.TemporaryDirectory() as tmp:
            img = Image.open(render_graphic_overlay(spec, Path(tmp) / "c.png", 1920, 1080)).convert("RGBA")
            x0, y0, x1, y1 = img.getbbox()
            self.assertAlmostEqual((x0 + x1) / 2, 960, delta=40)
            self.assertAlmostEqual((y0 + y1) / 2, 1080 * 0.42, delta=60)


if __name__ == "__main__":
    unittest.main()
