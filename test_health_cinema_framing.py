import json
import os
import unittest
from pathlib import Path

from health_cinema import assets, framing, journey, library, overlay

BOX = {"min": [-0.05, -0.04, 1.0], "max": [0.05, 0.04, 1.2], "center": [0.0, 0.0, 1.1]}      # a 10 x 8 x 20 cm organ


def spec_with(keys, duration=12.0):
    return {"duration": duration, "camera": keys, "layers": {}}


class FitDistance(unittest.TestCase):
    def test_a_key_asking_for_a_fill_gets_that_fill_at_any_angle(self):
        A = {"organ": BOX}
        for az, el in ((0, 5), (-38, 10), (36, 9), (70, 20)):
            for fill in (0.4, 0.6, 0.84):
                spec = spec_with([{"t": 0, "target": "organ", "fill": fill, "az": az, "el": el, "fov": 30}, {"t": 12, "target": "organ", "fill": fill, "az": az, "el": el, "fov": 30}])
                m = framing.measure(spec, A, 6.0, "organ")
                self.assertAlmostEqual(max(m["fill"], m["w_fill"]), fill, delta=0.01, msg=(az, el, fill))
                self.assertLess(m["cut"], 0.01)

    def test_a_distance_key_is_unchanged(self):
        A = {"organ": BOX}
        a = journey._key_state(A, {"target": "organ", "dist": 0.5, "az": 0, "el": 5, "fov": 30})
        self.assertAlmostEqual(a["logd"], __import__("math").log(0.5))

    def test_tighter_fill_means_a_closer_camera(self):
        A = {"organ": BOX}; ds = [journey._key_state(A, {"target": "organ", "fill": f, "az": 10, "el": 8, "fov": 30})["logd"] for f in (0.4, 0.6, 0.84)]
        self.assertGreater(ds[0], ds[1]); self.assertGreater(ds[1], ds[2])


class LabelBeside(unittest.TestCase):
    W, H = 1920, 1080

    def test_the_label_sits_clear_of_the_organ_on_its_side(self):
        organ = [700, 150, 1220, 930]
        for side in ("right", "left"):
            box, _ = overlay.label_box(300, 40, 960, 500, side, self.W, self.H, organ)
            self.assertTrue(box[0] >= organ[2] or box[2] <= organ[0], (side, box))

    def test_a_side_without_room_flips_to_the_other(self):
        organ = [500, 150, 1600, 930]          # nothing fits on the right
        box, _ = overlay.label_box(300, 40, 1400, 500, "right", self.W, self.H, organ)
        self.assertLessEqual(box[2], organ[0])

    def test_no_room_anywhere_keeps_the_label_inside_the_frame(self):
        organ = [100, 50, 1820, 1030]
        box, _ = overlay.label_box(300, 40, 960, 500, "right", self.W, self.H, organ)
        self.assertGreaterEqual(box[0], self.W * 0.03 - 1); self.assertLessEqual(box[2], self.W * 0.97 + 1)

    def test_without_a_subject_nothing_changes(self):
        self.assertEqual(overlay.label_box(300, 40, 960, 500, "right", self.W, self.H), overlay.label_box(300, 40, 960, 500, "right", self.W, self.H, None))


def _anchors(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))["anchors"]


def _models_available():
    return all(assets.anatomy_assets(k) for k in ("chest", "head", "abdomen", "msk"))


@unittest.skipUnless(_models_available(), "the prepared 3D models are not installed")
class EveryTemplateIsFramed(unittest.TestCase):
    """The framing gate: whatever the organ, the camera keeps it a decent size, in frame, in every settled moment."""

    def _spec(self, t):
        if t in assets.TEMPLATE_ASSET:
            p = Path(__file__).resolve().parent / "health_cinema" / "templates" / f"{t}.json"
            if not p.exists(): return None, None
            return json.loads(p.read_text(encoding="utf-8")), _anchors(assets.anatomy_assets(assets.TEMPLATE_ASSET[t])["anchors"])
        a = assets.anatomy_assets(library.model_of(t))
        return library.build_spec(t, a["anchors"]), _anchors(a["anchors"])

    def test_generated_organ_shots_fill_the_frame_and_are_never_cropped(self):
        n = 0
        for organ, o in library.ORGANS.items():
            if not assets.anatomy_assets(o.model): continue
            for shot in ("orbit", "zoom", "peel", "isolate"):
                spec, A = self._spec(f"auto:{organ}:{shot}")
                rows = framing.audit(spec, A, settle=0.0)
                s = framing.summary(rows); n += 1
                self.assertLessEqual(s["cut_share"], 0.0, (organ, shot, s)); self.assertLessEqual(s["small_share"], 0.0, (organ, shot, s))
                self.assertGreaterEqual(rows[-1]["fill"], 0.75, (organ, shot)); self.assertLessEqual(max(r["fill"] for r in rows), 0.9, (organ, shot))
        self.assertGreater(n, 40)

    def test_authored_journeys_settle_on_a_decent_size_without_cropping(self):
        for t in ("heart_journey", "brain_journey", "eye_journey"):
            spec, A = self._spec(t)
            if spec is None: continue
            rows = framing.audit(spec, A, settle=0.0)
            self.assertLessEqual(max(r["cut"] for r in rows), 0.05, t)
            hero = [r for r in rows if r["t"] >= spec["duration"] * 0.5]
            self.assertGreaterEqual(min(r["fill"] for r in hero), 0.3, t)      # the second half of a journey is never a distant shot


class OrganFramingBox(unittest.TestCase):
    """An organ is framed and labelled by its own box when the model has one (the stomach's anchor also holds the oesophagus up to the neck)."""

    def _anchors(self, names, layers):
        import tempfile
        bx = lambda z0, z1: {"center": [0, 0, (z0 + z1) / 2], "min": [-0.05, -0.05, z0], "max": [0.05, 0.05, z1]}
        A = {n: bx(1.1, 1.48) for n in names}
        d = tempfile.mkdtemp(); p = Path(d) / "a.json"; p.write_text(json.dumps({"anchors": A, "layers": {l: [] for l in layers}})); return str(p)

    def test_stomach_uses_its_own_box_when_present(self):
        o = library.ORGANS["stomach"]
        with_own = self._anchors(["stomach", "obj:Stomach.001"], list(o.hero) + list(o.context))
        spec = library.build_spec("auto:stomach:peel", with_own)
        self.assertEqual({k["target"] for k in spec["camera"]}, {"obj:Stomach.001"}); self.assertEqual(spec["labels"][0]["anchor"], "obj:Stomach.001")
        without = self._anchors(["stomach"], list(o.hero) + list(o.context))
        self.assertEqual({k["target"] for k in library.build_spec("auto:stomach:peel", without)["camera"]}, {"stomach"})      # older models still work

    def test_generated_organs_are_drawn_from_both_sides(self):
        o = library.ORGANS["stomach"]
        spec = library.build_spec("auto:stomach:orbit", self._anchors(["stomach"], list(o.hero) + list(o.context)))
        self.assertEqual(spec["double_sided"], list(o.hero))


if __name__ == "__main__":
    unittest.main()
