"""Map scenes (map_scene/ + map-engine/): place lookup, prompt format, AI
fallback cache, sea mask, and the renderer itself.

Renderer tests run offline (no satellite tiles: imagery=False) and are
skipped only when the map-engine's Node packages or a browser aren't
installed on this machine.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from map_scene.ai_places import cached_resolver
from map_scene.places import PlaceNotFound, _point_in_ring, find_place, sea_polygon
from map_scene.spec import MapPromptError, parse_map_prompt

ROOT = Path(__file__).resolve().parent


def _in_multipolygon(x, y, geom) -> bool:
    for poly in geom["coordinates"]:
        if _point_in_ring(x, y, poly[0]) and not any(_point_in_ring(x, y, h) for h in poly[1:]):
            return True
    return False


class TestPromptFormat(unittest.TestCase):
    def test_big_to_small_levels(self):
        spec = parse_map_prompt("Florida > Florida Panhandle > Okaloosa")
        self.assertEqual((spec.parent, spec.focus, spec.inner), ("Florida", "Florida Panhandle", "Okaloosa"))
        self.assertEqual(parse_map_prompt("Egypt").focus, "Egypt")

    def test_options(self):
        spec = parse_map_prompt("Florida > Florida Panhandle | camera: zoom_out | style: natural | label: First Capital")
        self.assertEqual((spec.camera, spec.style, spec.label_text), ("zoom_out", "natural", "FIRST CAPITAL"))
        self.assertEqual(parse_map_prompt("Florida > Florida Panhandle").label_text, "FLORIDA PANHANDLE")

    def test_bad_prompts_explain_themselves(self):
        for bad, words in (("", "empty"), ("A > B > C > D", "three levels"), ("Egypt | camera: spin", "Unknown camera"),
                           ("Egypt | zoom", "should look like"), ("Egypt | colour: red", "Unknown map option")):
            with self.assertRaises(MapPromptError) as ctx:
                parse_map_prompt(bad)
            self.assertIn(words, str(ctx.exception))


class TestPlaceLookup(unittest.TestCase):
    def test_state(self):
        florida = find_place("Florida")
        self.assertEqual((florida.kind, florida.country), ("admin1", "USA"))
        minx, miny, maxx, maxy = florida.bbox()
        self.assertTrue(-88 < minx < -87 and 24.5 < miny < 25.5 and -80.5 < maxx < -79.5 and 30.5 < maxy < 31.5)

    def test_county_by_full_name_and_inside_a_parent(self):
        self.assertEqual(find_place("Escambia County, Florida").state, "Florida")
        bay = find_place("Bay", parent=find_place("Florida"))
        self.assertEqual((bay.kind, bay.name, bay.state), ("county", "Bay", "Florida"))

    def test_named_region_is_its_counties_with_one_outer_border(self):
        region = find_place("Florida Panhandle")
        self.assertEqual((region.kind, region.source, len(region.polygons)), ("region", "named_region", 17))
        inner_edges = sum(len(ring) - 1 for poly in region.polygons for ring in poly)
        outline_edges = sum(len(line) - 1 for line in region.outline())
        self.assertLess(outline_edges, inner_edges * 0.8)  # borders between its counties are gone
        fx0, fy0, fx1, fy1 = find_place("Florida").bbox()
        x, y = region.anchor()
        self.assertTrue(fx0 < x < fx1 and fy0 < y < fy1 and y > 29.5)  # label points inside the Panhandle

    def test_country_wins_a_bare_ambiguous_name_but_a_parent_disambiguates(self):
        self.assertEqual(find_place("Georgia").kind, "country")
        us_georgia = find_place("Georgia", parent=find_place("United States of America"))
        self.assertEqual((us_georgia.kind, us_georgia.country), ("admin1", "USA"))

    def test_province_outside_the_us(self):
        self.assertEqual(find_place("Ontario").country, "CAN")

    def test_ai_resolved_region_and_point(self):
        def ai(name, parent):
            if name == "Test Coast":
                return {"type": "us_counties", "items": ["Florida|Gulf", "Florida|Franklin"]}
            if name == "Eglin Air Force Base":
                return {"type": "point", "lat": 30.46, "lon": -86.55, "radius_km": 12}
            return {"type": "unknown"}

        coast = find_place("Test Coast", ai=ai)
        self.assertEqual((coast.kind, coast.source), ("region", "ai"))
        self.assertGreaterEqual(len(coast.polygons), 2)  # Gulf + Franklin (and its island)
        base = find_place("Eglin Air Force Base", ai=ai)
        self.assertEqual((base.kind, base.point), ("point", (-86.55, 30.46)))
        with self.assertRaises(PlaceNotFound):
            find_place("Nowhere Special", ai=ai)

    def test_unknown_place_fails_clearly_even_if_ai_breaks(self):
        def broken(name, parent):
            raise RuntimeError("network down")

        with self.assertRaises(PlaceNotFound) as ctx:
            find_place("Atlantis Plateau", ai=broken)
        self.assertIn('"Atlantis Plateau"', str(ctx.exception))
        self.assertIn("another source", str(ctx.exception))

    def test_ai_answers_are_cached_and_failures_are_retried(self):
        calls = []

        def ask(name, parent):
            calls.append(name)
            return None if name == "flaky" else {"type": "point", "lat": 1, "lon": 2}

        with tempfile.TemporaryDirectory() as tmp:
            resolve = cached_resolver(ask, Path(tmp) / "ai.json")
            resolve("Some Base", None)
            resolve("Some Base", None)
            resolve("flaky", None)
            resolve("flaky", None)
            self.assertEqual(calls, ["Some Base", "flaky", "flaky"])
            self.assertIn(">some base", json.loads((Path(tmp) / "ai.json").read_text()))


class TestSeaMask(unittest.TestCase):
    def test_sea_and_land_around_florida(self):
        sea = sea_polygon((-95, 20, -75, 36))
        self.assertTrue(_in_multipolygon(-86.0, 28.0, sea))       # Gulf of Mexico
        self.assertFalse(_in_multipolygon(-84.28, 30.44, sea))    # Tallahassee

    def test_sea_and_land_around_egypt_including_an_inland_sea(self):
        sea = sea_polygon((-6, -2, 67, 56))
        self.assertTrue(_in_multipolygon(20.0, 35.0, sea))        # Mediterranean
        self.assertTrue(_in_multipolygon(38.0, 20.0, sea))        # Red Sea
        self.assertTrue(_in_multipolygon(51.0, 42.0, sea))        # Caspian Sea (inside land)
        self.assertFalse(_in_multipolygon(31.24, 30.04, sea))     # Cairo
        self.assertFalse(_in_multipolygon(45.0, 24.0, sea))       # Saudi Arabia
        self.assertFalse(_in_multipolygon(28.5, -29.5, sea))      # Lesotho (enclave) is land


def _renderer_available() -> str:
    if not (ROOT / "map-engine" / "node_modules" / "maplibre-gl" / "package.json").is_file():
        return "map-engine Node packages not installed (cd map-engine && npm install)"
    try:
        from map_scene.render import _ffmpeg, _node

        _node()
        _ffmpeg()
    except Exception as exc:
        return str(exc)
    from providers.playwright_chromium import is_playwright_chromium_installed, system_chrome_available

    if not (is_playwright_chromium_installed() or system_chrome_available()):
        return "no Chromium/Chrome for the map renderer"
    return ""


def _frames(path: Path, width: int, height: int):
    import numpy as np

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, height, width, 3)


@unittest.skipIf(_renderer_available(), _renderer_available() or "ok")
class TestRenderer(unittest.TestCase):
    W, H, FPS, DUR = 480, 270, 10, 1.5

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.cache = tempfile.mkdtemp()
        import os

        os.environ["VIDEOGEN_MAP_CACHE"] = cls.cache

    @classmethod
    def tearDownClass(cls):
        import os

        os.environ.pop("VIDEOGEN_MAP_CACHE", None)
        shutil.rmtree(cls.tmp, ignore_errors=True)
        shutil.rmtree(cls.cache, ignore_errors=True)

    def _render(self, prompt: str, name: str):
        from map_scene.render import render_map

        out = self.tmp / f"{name}.mp4"
        render_map(prompt, out, duration=self.DUR, fps=self.FPS, width=self.W, height=self.H, imagery=False)
        return out, _frames(out, self.W, self.H)

    def test_render_is_not_blank_has_red_focus_in_frame_and_a_label(self):
        out, frames = self._render("Florida > Florida Panhandle", "panhandle")
        self.assertEqual(len(frames), round(self.DUR * self.FPS))
        last = frames[-1].astype(int)
        self.assertGreater(last.std(), 20)  # not a blank frame
        r, g, b = last[..., 0], last[..., 1], last[..., 2]
        red = (r > 200) & (g < 90) & (b < 90)
        self.assertGreater(red.mean(), 0.05)
        ys, xs = red.nonzero()
        self.assertTrue(self.W * 0.15 < xs.mean() < self.W * 0.85 and self.H * 0.15 < ys.mean() < self.H * 0.85)
        # The label is drawn: a longer label adds more bright-white pixels.
        _, short = self._render("Florida > Florida Panhandle | label: A", "short_label")
        white = lambda f: ((f[..., 0] > 235) & (f[..., 1] > 235) & (f[..., 2] > 235)).sum()
        self.assertGreater(white(frames[-1]), white(short[-1]) + 150)

    def test_same_input_gives_the_same_video_frames(self):
        _, a = self._render("Mississippi > Mississippi Delta", "det_a")
        _, b = self._render("Mississippi > Mississippi Delta", "det_b")
        self.assertEqual(hashlib.md5(a.tobytes()).hexdigest(), hashlib.md5(b.tobytes()).hexdigest())

    def test_a_point_place_renders_a_disc(self):
        from map_scene import render as R

        ai = lambda name, parent: {"type": "point", "lat": 30.46, "lon": -86.55, "radius_km": 12}
        out = self.tmp / "point.mp4"
        R.render_map("Florida Panhandle > Eglin Air Force Base", out, duration=self.DUR, fps=self.FPS,
                     width=self.W, height=self.H, imagery=False, ai=ai)
        last = _frames(out, self.W, self.H)[-1].astype(int)
        red = (last[..., 0] > 200) & (last[..., 1] < 90) & (last[..., 2] < 90)
        self.assertGreater(red.sum(), 30)

    def test_unknown_place_never_starts_the_browser(self):
        from map_scene.render import render_map

        with self.assertRaises(PlaceNotFound):
            render_map("Atlantis Plateau", self.tmp / "none.mp4", duration=1, imagery=False)
        self.assertFalse((self.tmp / "none.mp4").exists())


class TestKeptApartFromFlow(unittest.TestCase):
    def test_no_flow_port_no_persistent_profile(self):
        src = (ROOT / "map-engine" / "render.mjs").read_text(encoding="utf-8")
        self.assertNotIn("8787", src)
        self.assertIn("listen(0, '127.0.0.1'", src)  # a random free local port
        self.assertIn("chromium.launch(", src)
        self.assertNotIn("launchPersistentContext", src)
        self.assertNotIn("userDataDir", src)
        self.assertNotIn("profiles", src)


if __name__ == "__main__":
    unittest.main()
