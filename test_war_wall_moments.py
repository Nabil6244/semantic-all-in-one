"""Wall Moments in War Documentary (cinematic_explainer/war/wall_moments.py, segments._compose, audio.build_mix): docs/wall/PLAN.md Phase 4."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import segments as SG
from cinematic_explainer.war import wall_moments as WW
from wall import frames as FR

TEXTS = [
    "Russian forces crossed the border before dawn.",                                   # 0 footage
    "Ukraine had 209 tanks ready in the north, about a third of what it needed.",        # 1 card
    "By March, Russia had lost 1,600 armoured vehicles, 40 percent more than expected.",  # 2 card
    "Here is the strange part.",                                                         # 3 card
    "The convoy stopped for three weeks.",                                               # 4 footage
    "Its supply line stretched 64 kilometres.",                                          # 5 map
    "The offensive never reached Kyiv.",                                                 # 6 footage
]


def timeline(repeat: int = 6):
    scenes, shots, layers, words, t, k = [], [], [], [], 0.0, 0
    for r in range(repeat):
        for i, text in enumerate(TEXTS):
            d = 6.0 if i in (1, 2) else 4.0
            no = k + 1
            scenes.append({"scene_no": no, "text": text, "start": t, "end": t + d})
            toks = text.replace(",", "").replace(".", "").split()
            words += [[w.lower(), round(t + d * j / len(toks), 3), round(t + d * (j + 1) / len(toks), 3)] for j, w in enumerate(toks)]
            if i in (0, 4, 6):
                shots.append(Shot(f"/clips/{no}.mp4", t, t + d, 1.0, {"motion": "push_in", "z0": 1.0, "z1": 1.06, "grade": "film"}, 0.4))
            else:
                shots.append(Shot("/state/war_backdrop_v3.mp4", t, t + d, 0.0))
                kind = {1: "kit_bignum", 2: "lay_stat_split", 3: "kit_kinetic", 5: "tac_map"}[i]
                layers.append(Layer(kind, t, t + d, {}))
            if i == 0:
                layers.append(Layer("bc_label", t + 0.5, t + 2.0, {}))
            t += d
            k += 1
    return scenes, shots, layers, words, t


class WarAdapterTest(unittest.TestCase):
    def setUp(self):
        self.sc, self.sh, self.ly, self.w, self.total = timeline()
        self.shots, self.layers, self.rep = WW.apply(self.sh, self.ly, self.sc, self.w, pct=20)

    def test_band_and_war_theme(self):
        self.assertTrue(self.rep["spans"])
        self.assertGreaterEqual(self.rep["share"], 15.0)
        self.assertLessEqual(self.rep["share"], 22.0)
        for s in self.rep["plan"]["segments"]:
            self.assertEqual(s["params"]["theme"], "war")

    def test_footage_maps_never_covered(self):
        for a, b in self.rep["spans"]:
            for s in self.sh:
                if s.path.startswith("/clips/"):
                    self.assertLessEqual(min(b, s.end) - max(a, s.start), 1e-6, ("footage", s.start))
            for ly in self.ly:
                if ly.kind == "tac_map":
                    self.assertLessEqual(min(b, ly.end) - max(a, ly.start), 1e-6, ("map", ly.start))

    def test_cards_replaced_only_inside(self):
        walls = [ly for ly in self.layers if ly.kind == "wall.lay_wall"]
        self.assertEqual(len(walls), len(self.rep["spans"]))
        for ly in self.layers:
            if ly.kind != "wall.lay_wall":
                for a, b in self.rep["spans"]:
                    self.assertLessEqual(min(ly.end, b) - max(ly.start, a), 1e-6)

    def test_clip_after_a_moment_cuts_in(self):
        ends = {round(b, 3) for _a, b in self.rep["spans"]}
        for s in self.shots:
            if round(s.start, 3) in ends:
                self.assertEqual(s.dissolve_in, 0.0)
        self.assertTrue(any(s.dissolve_in > 0 for s in self.shots))                  # the other cross-fades stay

    def test_prints_carry_the_war_look(self):
        seg = self.rep["plan"]["segments"][0]["params"]
        vids = [i for i in seg["items"] if i["type"] == "video" and i["clip"]["path"].startswith("/clips/")]
        self.assertTrue(vids)
        self.assertTrue(all("eq=contrast" in v["clip"].get("graph", "") for v in vids))


class HandOffTest(unittest.TestCase):
    def test_graph_decodes_with_the_end_zoom(self):
        td = Path(tempfile.mkdtemp())
        try:
            clip = td / "c.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=25:d=3", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", str(clip)], check=True, timeout=60)
            shot = Shot(str(clip), 10.0, 13.0, 0.0, {"motion": "push_in", "z0": 1.0, "z1": 1.08, "grade": "cold", "vignette": 0.2})
            g = WW._hand_off(shot, 13.0)["graph"]
            self.assertIn("crop=w=iw/1.08000", g)
            self.assertLess(g.index("crop=w=iw/"), g.index("vignette"))
            fr = FR.window(str(clip), 0.0, 1.0, (320, 180), str(td / "f"), g)
            self.assertGreaterEqual(len(fr), 20)
            self.assertEqual(fr.at(0.5).size, (320, 180))
            self.assertEqual(WW._hand_off(Shot(str(clip), 0, 3, 0), 0.0), {})
        finally:
            FR.forget()
            shutil.rmtree(td, ignore_errors=True)


class ComposeTest(unittest.TestCase):
    def test_wall_is_drawn_last_and_not_lifted(self):
        from PIL import Image

        black = lambda t, d, p: Image.new("RGBA", (1280, 720), (0, 0, 0, 255))
        cards = {"wall.lay_wall": black, "kit_bignum": lambda t, d, p: Image.new("RGBA", (1280, 720), (200, 200, 200, 255))}
        img = SG._compose(1.0, [Layer("wall.lay_wall", 0, 5, {}), Layer("kit_bignum", 0, 5, {})], cards, lambda ly, e: None)
        self.assertEqual(img.getpixel((10, 10))[:3], (0, 0, 0))                 # the wall on top, its black not lifted
        lifted = SG._compose(1.0, [Layer("kit_bignum", 0, 5, {}), Layer("x", 0, 5, {})], {"kit_bignum": black}, lambda ly, e: None)
        self.assertGreater(lifted.getpixel((10, 10))[0], 0)                      # cards keep their lift
        self.assertIn("wall.lay_wall", SG.all_cards())


class SoundTest(unittest.TestCase):
    def test_wall_track(self):
        from wall import sfx as SX

        tr = SX.track(5.0, [(1.0, "stamp"), (1.1, "pop"), (3.0, "ticks:1.0")], 48000)
        self.assertGreater(np.abs(tr[48000:48000 + 4800]).max(), 0.01)
        self.assertLess(np.abs(tr[int(2.5 * 48000):int(2.9 * 48000)]).max(), 1e-4)
        self.assertEqual([e["file"].endswith("pop.wav") for e in SX.events([(1.0, "stamp"), (1.1, "pop")])], [False])


if __name__ == "__main__":
    unittest.main()
