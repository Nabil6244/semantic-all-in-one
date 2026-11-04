"""QA fixes from the S27 review audit (2026-11-03): the encoder converts to standard range BT.709 and tags it, a voiced film is normalised to
-14 LUFS, a phone looks the same on every card (lens count, layout, colour by model), a price card is one phone at two prices, and the plan
summary counts what is in the film. Synthetic data; ffmpeg only for the loudness check."""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from product_trailer import director, studio

ROOT = Path(__file__).resolve().parent


class Encode(unittest.TestCase):
    def test_the_encoder_converts_and_tags_bt709_standard_range(self):
        js = (ROOT / "whatif-engine" / "render.mjs").read_text(encoding="utf-8")
        self.assertIn("out_range=tv:out_color_matrix=bt709", js)
        for tag in ("'-color_range', 'tv'", "'-colorspace', 'bt709'", "'-color_primaries', 'bt709'", "'-color_trc', 'bt709'", "video_full_range_flag=0"):
            self.assertIn(tag, js)


class Loudness(unittest.TestCase):
    def test_a_voiced_film_is_normalised_to_minus_14_lufs(self):
        from map_scene.render import _ffmpeg
        from product_trailer import render

        ff = _ffmpeg()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            voice = d / "voice.wav"
            subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=6", "-af", "volume=-30dB", str(voice)], check=True)
            spec = {"width": 64, "height": 36, "fps": 30, "duration": 6.0, "shots": [], "layers": [], "product_trailer": {"voiceover": str(voice)}}
            sp = d / "spec.json"
            sp.write_text(json.dumps(spec), encoding="utf-8")

            def fake_render(engine_spec, out, **_):
                subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "color=black:s=64x36:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)], check=True)

            with mock.patch("whatif.engine_runner.render_spec", fake_render):
                out = render(sp, d / "out.mp4", log=lambda m: None)
            e = subprocess.run([ff, "-i", out, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
            lufs = float(re.findall(r"I:\s+(-?[0-9.]+) LUFS", e)[-1])
        self.assertLess(abs(lufs - (-14.0)), 1.0, lufs)


class Phones(unittest.TestCase):
    def test_a_price_card_is_one_phone_at_two_prices(self):
        sc = director.scene_for("The S26 Ultra dropped to $919.99 at Amazon on Prime Day, compared to a $1,299.99 list price.", "Galaxy S27 Ultra")
        a, b = sc["layer"]["phones"]
        self.assertEqual(a["label"], b["label"])
        self.assertEqual(a["color"], b["color"])
        self.assertEqual({a["top"], b["top"]}, {"Now", "List price"})

    def test_the_same_model_looks_the_same_on_every_card(self):
        spec = {"layers": [
            {"type": "pt_flatphones", "phones": [{"label": "Galaxy S26 Ultra", "color": "#5b5a86", "cams": 3}, {"label": "iPhone 18 Pro", "color": "#5b5a86", "cams": 4}]},
            {"type": "pt_flatphones", "phones": [{"label": "S26 Ultra", "color": "#2b2b2e", "cams": 3}, {"label": "Pixel 11 Pro", "color": "#333", "cams": 4}]},
            {"type": "pt_flatphones", "phones": [{"label": "Earlier leak", "color": "#123", "cams": 3}]}]}
        studio.consistent_phones(spec)
        s26 = [p for L in spec["layers"] for p in L["phones"] if "S26" in p["label"]]
        self.assertEqual({(p["color"], p["cams"]) for p in s26}, {("#5b5a86", 4)})          # one colour, an Ultra's four lenses
        iph = spec["layers"][0]["phones"][1]
        self.assertEqual((iph["design"], iph["cams"]), ("iphone", 3))
        self.assertEqual(spec["layers"][1]["phones"][1]["design"], "pixel")
        self.assertEqual(spec["layers"][2]["phones"][0], {"label": "Earlier leak", "color": "#123", "cams": 3})   # not a model: untouched


class Summary(unittest.TestCase):
    def test_the_summary_counts_the_film_not_the_plan(self):
        script = "\n".join(["## Design", "First, the design.", "The phone is slightly bigger than the S26 Ultra.", "## Battery", "The battery is 5,534 milliamp hours."])
        with tempfile.TemporaryDirectory() as d:
            r = studio.plan_film("Review", out_dir=d, script=script, phone="Galaxy S27 Ultra", use_ai=False, disclaimer_on=False, log=lambda m: None)
        self.assertNotIn("AI scenes", r["summary"])
        self.assertIn("3D", r["summary"])
        self.assertFalse([n for n in r["notes"] if "had no AI picture" in n])


if __name__ == "__main__":
    unittest.main()
