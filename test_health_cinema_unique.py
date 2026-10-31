"""Unique 3D in every video: the part a sentence names is where its shot ends (parts.py), every 3D scene gets its own AI image card (engine.auto_cards),
and a finished video's clip that repeats an earlier video's clip is filmed another way (variety.too_similar / reroll)."""
import json
import subprocess
import tempfile
import types
import unittest
from pathlib import Path

from health_cinema import assets, clips, engine, framing, parts, variety

BX = lambda c, h: {"center": c, "min": [c[i] - h for i in range(3)], "max": [c[i] + h for i in range(3)]}


def anchors_file(d, extra_layers=None):
    A = {"heart": BX([0, 0, 1.3], 0.06), "obj:Left coronary artery": BX([0.03, -0.05, 1.33], 0.012), "obj:Posterior leaflet of left atrioventricular valve": BX([0.01, 0, 1.3], 0.006)}
    L = {"Layer_Heart": ["Left ventricle"], "Layer_Vessels": ["Left coronary artery"], "Layer_HeartInner": ["Posterior leaflet of left atrioventricular valve"]}
    p = Path(d) / "a.json"; p.write_text(json.dumps({"anchors": A, "layers": L})); return str(p), A


def spec(end_layers):
    return {"duration": 12.0, "camera": [{"t": 0, "target": "heart", "fill": 0.5, "az": 0, "el": 5, "fov": 30}, {"t": 12, "target": "heart", "fill": 0.7, "az": 10, "el": 5, "fov": 30}],
            "layers": {ln: [[0, 1.0], [12, a]] for ln, a in end_layers.items()}, "labels": [{"id": "l0", "text": "Heart", "anchor": "heart", "offset": [0, 0, 0], "t0": 3, "t1": 11.2, "side": "right"}]}


class Parts(unittest.TestCase):
    def setUp(self):
        self.ap, self.A = anchors_file(tempfile.mkdtemp())

    def test_the_named_part_is_where_the_shot_ends_and_it_is_labelled(self):
        s = parts.focus(spec({"Layer_Vessels": 1.0, "Layer_Heart": 1.0}), "Blocked coronary arteries starve the muscle.", self.ap)
        self.assertEqual(s["camera"][-1]["target"], "obj:Left coronary artery"); self.assertEqual(s["part"], "Coronary arteries")
        self.assertEqual(s["labels"][-1]["text"], "Coronary arteries"); self.assertLessEqual(s["labels"][0]["t1"], 12 * 0.68 + 1e-6)
        rows = framing.audit(s, self.A, settle=0.0); self.assertLessEqual(max(r["cut"] for r in rows), 0.02)

    def test_a_tiny_part_is_shown_in_place_not_from_inside(self):
        s = parts.focus(spec({"Layer_HeartInner": 1.0}), "The mitral valve leaks.", self.ap)
        from health_cinema import journey
        st = journey._key_state(self.A, s["camera"][-1]); import math
        self.assertGreater(math.exp(st["logd"]), 0.05)      # far enough to see three times the leaflet around it

    def test_a_part_whose_layer_is_gone_is_not_used(self):
        sp = spec({"Layer_Vessels": 0.0, "Layer_Heart": 1.0}); self.assertIs(parts.focus(sp, "coronary arteries", self.ap), sp)

    def test_no_part_named_no_change(self):
        sp = spec({"Layer_Heart": 1.0}); self.assertIs(parts.focus(sp, "Your heart beats all day.", self.ap), sp)


class AutoCards(unittest.TestCase):
    def scene(self, text, tpl="auto:liver:orbit", dur=9.0, **kw):
        return types.SimpleNamespace(kind="anatomy_3d", visual=dict({"template": tpl}, **kw), text=text, start=0.0, end=dur)

    def test_every_3d_scene_gets_its_own_image_from_its_sentence(self):
        a, b, c = self.scene("Fat builds up in the liver."), self.scene("The liver filters toxins."), self.scene("Cellulitis spreads fast.", "cond:cellulitis:orbit")
        self.assertEqual(engine.auto_cards([a, b, c]), 3)
        refs = [x.visual["cards"][0]["ref"] for x in (a, b, c)]; self.assertEqual(len(set(refs)), 3)
        self.assertIn("Fat builds up in the liver.", a.visual["cards"][0]["prompt"]); self.assertEqual(c.visual["cards"][0]["type"], "microscopic")
        self.assertTrue(all(x.visual["cards"][0]["auto"] for x in (a, b, c)))

    def test_short_scenes_body_maps_and_csv_cards_are_left_alone(self):
        short, body, csv = self.scene("x", dur=4.0), self.scene("y", body_rows=[{}]), self.scene("z", cards=[{"ref": "mine"}])
        self.assertEqual(engine.auto_cards([short, body, csv]), 0); self.assertEqual(csv.visual["cards"], [{"ref": "mine"}])

    def test_the_card_plays_early_on_the_left_and_labels_wait(self):
        import os
        from health_cinema import illustrations as ILL, conditions as CN
        d = tempfile.mkdtemp(); old = os.environ.get("HEALTH_CINEMA_ILLUSTRATION_DIR"); os.environ["HEALTH_CINEMA_ILLUSTRATION_DIR"] = d
        try:
            from PIL import Image
            Image.new("RGB", (64, 36), (40, 60, 90)).save(Path(d) / "x.png"); ILL.register(Path(d) / "x.png", id="auto_x", topic="x", view="m", kind="mechanism", prompt="p", source="flow")
            sp = CN.build_spec("cond:immune_response:orbit"); cards = clips.organ_cards([{"ref": "auto_x", "auto": True}], sp, sp["anchor_overrides"])
        finally:
            os.environ.pop("HEALTH_CINEMA_ILLUSTRATION_DIR") if old is None else os.environ.__setitem__("HEALTH_CINEMA_ILLUSTRATION_DIR", old)
        self.assertEqual(cards[0]["side"], "left"); self.assertEqual(cards[0]["t0"], 0.5); self.assertLessEqual(cards[0]["t1"], 4.2)
        self.assertTrue(all(l["t0"] >= cards[0]["t1"] for l in sp["labels"] if l["side"] == "left" and l["t1"] - l["t0"] > 1.0))


class Uniqueness(unittest.TestCase):
    def setUp(self):
        self.h = Path(tempfile.mkdtemp()) / "h.json"; self.ff = assets.ffmpeg_path() or "ffmpeg"

    def clip(self, color, name):
        p = Path(tempfile.mkdtemp()) / f"{name}.mp4"
        subprocess.run([self.ff, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=320x180:rate=24:duration=3", "-vf", f"hue=h={color}", "-pix_fmt", "yuv420p", str(p)], check=True); return str(p)

    def test_a_repeat_of_an_earlier_videos_clip_is_caught_and_refilmed_differently(self):
        d1 = dict(variety.choose(["heart_journey"], "video-1", history=self.h)[0], video="video-1", record=True)
        same = self.clip(0, "a"); variety.remember_frames(d1, variety.frame_hashes(same, self.ff), history=self.h)
        d2 = dict(variety.choose(["heart_journey"], "video-2", history=self.h)[0], video="video-2", record=True)
        self.assertEqual(variety.too_similar(d2, variety.frame_hashes(same, self.ff), history=self.h), d1["fp"])
        new = variety.reroll(d2, [d2["fp"]], history=self.h)
        self.assertNotEqual(new["fp"], d2["fp"]); self.assertNotEqual(new["look"], d2["look"]); self.assertNotEqual(new["move"], d2["move"])

    def test_its_own_video_and_other_subjects_are_never_a_repeat(self):
        d1 = dict(variety.choose(["heart_journey"], "v1", history=self.h)[0], video="v1", record=True); hs = variety.frame_hashes(self.clip(0, "b"), self.ff)
        variety.remember_frames(d1, hs, history=self.h)
        self.assertIsNone(variety.too_similar(d1, hs, history=self.h))
        self.assertIsNone(variety.too_similar(dict(d1, subject="brain_journey", video="v2"), hs, history=self.h))

    def test_different_pictures_are_not_a_repeat(self):
        d1 = dict(variety.choose(["heart_journey"], "v1", history=self.h)[0], video="v1", record=True)
        variety.remember_frames(d1, variety.frame_hashes(self.clip(0, "c"), self.ff), history=self.h)
        blank = Path(tempfile.mkdtemp()) / "k.mp4"; subprocess.run([self.ff, "-v", "error", "-y", "-f", "lavfi", "-i", "mandelbrot=size=320x180:rate=24", "-t", "3", "-pix_fmt", "yuv420p", str(blank)], check=True)
        self.assertIsNone(variety.too_similar(dict(d1, video="v2"), variety.frame_hashes(str(blank), self.ff), history=self.h))

    def test_previews_are_not_remembered(self):
        d = dict(variety.choose(["heart_journey"], "p", history=self.h, record=False)[0], video="p", record=False)
        variety.remember_frames(d, [1, 2, 3], history=self.h); self.assertFalse(self.h.exists())


class CardsInTheVisualsTab(unittest.TestCase):
    """Generate scenes lists the illustration cards in the Visuals tab before Flow makes them, and each finished picture refreshes the tab."""

    def test_listed_before_the_pictures_are_made_and_refreshed_as_each_lands(self):
        import os
        from health_cinema import app_section
        events = []

        class Mgr:
            def resolve_all(self, rows, on_scene_complete=None):
                events.append(("make", len(rows)))
                for r in rows: on_scene_complete(r, None)

        d = tempfile.mkdtemp(); old = os.environ.get("HEALTH_CINEMA_ILLUSTRATION_DIR"); os.environ["HEALTH_CINEMA_ILLUSTRATION_DIR"] = d
        try:
            wanted = [{"ref": f"auto_x_{i}", "prompt": f"picture {i}", "type": "mechanism", "topic": "liver", "narration": f"Sentence {i}."} for i in range(3)]
            rows = app_section.illustration_rows(wanted, Mgr(), Path(d) / "imgs", lambda: False, lambda m: None,
                                                 on_listed=lambda rs: events.append(("listed", len(rs))), on_done=lambda *a: events.append(("done",)))
        finally:
            os.environ.pop("HEALTH_CINEMA_ILLUSTRATION_DIR") if old is None else os.environ.__setitem__("HEALTH_CINEMA_ILLUSTRATION_DIR", old)
        self.assertEqual(len(rows), 3)
        self.assertEqual(events[0], ("listed", 3)); self.assertEqual(events[1], ("make", 3)); self.assertEqual(events[2:], [("done",)] * 3)

    def test_the_worker_lists_the_cards_before_making_them(self):
        src = (Path(__file__).resolve().parent / "health_cinema" / "app_section.py").read_text(encoding="utf-8")
        self.assertIn("on_listed=listed, on_done=one_done", src); self.assertIn("visual_bridge.fill(app, OWNER, footage_rows + ill_rows)", src)


if __name__ == "__main__":
    unittest.main()
