"""Variety director: each video films and lights its 3D scenes its own way, never repeats a combination an earlier video used, and a re-render of the
same video gets the same directions (so its clips stay cached). Camera moves keep the framing rules."""
import json
import tempfile
import unittest
from pathlib import Path

from health_cinema import assets, framing, library, variety

SUBJECTS = ["heart_journey", "auto:liver:orbit", "auto:liver:orbit", "body_map", "micro:plaque:orbit"]


class Choose(unittest.TestCase):
    def setUp(self):
        self.h = Path(tempfile.mkdtemp()) / "history.json"

    def test_a_new_video_never_reuses_an_earlier_videos_combination(self):
        seen = set()
        for n in range(6):
            d = variety.choose(SUBJECTS, variety.video_key(f"script number {n}"), body=[False, False, False, True, False], history=self.h)
            fps = {x["fp"] for x in d}
            self.assertFalse(fps & seen, n); seen |= fps

    def test_the_same_video_gets_the_same_directions_back(self):
        k = variety.video_key("one script"); a = variety.choose(SUBJECTS, k, history=self.h)
        variety.choose(SUBJECTS, variety.video_key("another script"), history=self.h)
        self.assertEqual(variety.choose(SUBJECTS, k, history=self.h), a)

    def test_neighbouring_scenes_differ_and_repeats_of_one_organ_differ(self):
        d = variety.choose(SUBJECTS, variety.video_key("x"), body=[False, False, False, True, False], history=self.h)
        for a, b in zip(d, d[1:]): self.assertNotEqual(a["look"], b["look"])
        self.assertNotEqual((d[1]["move"], d[1]["look"]), (d[2]["move"], d[2]["look"]))
        self.assertEqual(d[3]["move"], "as_designed")      # a body-map camera follows its beats

    def test_consecutive_videos_change_the_mood_and_the_move_of_an_organ(self):
        last = None
        for n in range(8):
            d = variety.choose(["heart_journey"], variety.video_key(f"heart video {n}"), history=self.h)[0]
            if last: self.assertNotEqual(d["look"], last["look"], n); self.assertNotEqual(d["move"], last["move"], n)
            last = d

    def test_used_up_combinations_fall_back_to_the_oldest(self):
        k0 = variety.video_key("first")
        for n in range(len(variety.MOVES) * len(variety.LOOKS) + 3):
            d = variety.choose(["micro:cell:orbit"], variety.video_key(f"v{n}"), history=self.h)
            self.assertEqual(len(d), 1)

    def test_an_edited_video_keeps_every_unchanged_scenes_direction(self):
        k = "project-folder"; a = variety.choose(["heart_journey", "auto:liver:orbit", "cond:asthma:orbit"], k, history=self.h)
        b = variety.choose(["heart_journey", "cond:acne:orbit", "auto:liver:orbit", "cond:asthma:orbit"], k, history=self.h)      # a 3D scene added in the middle
        self.assertEqual(b[0], a[0]); self.assertEqual(b[2], a[1]); self.assertEqual(b[3], a[2])

    def test_a_preview_is_not_remembered(self):
        variety.choose(["heart_journey"], "preview-only", history=self.h, record=False)
        self.assertFalse(self.h.exists())

    def test_unwritable_history_still_directs(self):
        d = variety.choose(SUBJECTS, "k", history=Path("/nonexistent-dir/x/history.json"))
        self.assertEqual(len(d), len(SUBJECTS))


class Apply(unittest.TestCase):
    BOX = {"organ": {"min": [-0.05, -0.04, 1.0], "max": [0.05, 0.04, 1.2], "center": [0.0, 0.0, 1.1]}}

    def spec(self):
        return {"duration": 12.0, "exposure": 0.62, "glow": [{"color": [0.72, 0.86, 1.0]}, {"color": [1.0, 0.3, 0.3]}],
                "camera": [{"t": 0, "target": "organ", "fill": 0.46, "az": 0, "el": 10, "fov": 30}, {"t": 6, "target": "organ", "fill": 0.7, "az": 0, "el": 12, "fov": 30},
                           {"t": 12, "target": "organ", "fill": library.FILL_MAX, "az": 36, "el": 9, "fov": 30}], "layers": {}}

    def test_every_move_keeps_the_organ_framed(self):
        for move in variety.MOVES:
            s = variety.apply(self.spec(), {"move": move, "look": "teal_lab"})
            self.assertTrue(all(k["fill"] <= library.FILL_MAX for k in s["camera"]), move)
            rows = framing.audit(s, self.BOX, settle=0.0)
            self.assertLessEqual(max(r["cut"] for r in rows), 0.01, move); self.assertGreaterEqual(min(r["fill"] for r in rows), 0.25, move)

    def test_look_sets_palette_light_and_cool_rims_only(self):
        s = variety.apply(self.spec(), {"move": "orbit_left", "look": "amber_dusk"})
        self.assertEqual(s["palette"], "amber"); self.assertEqual(s["key_rot"], 60)
        self.assertEqual(s["glow"][0]["color"], variety.LOOKS["amber_dusk"]["rim"]); self.assertEqual(s["glow"][1]["color"], [1.0, 0.3, 0.3])

    def test_a_lens_change_keeps_the_subject_size(self):
        A = {"organ": self.BOX["organ"]}
        base = {"duration": 12.0, "camera": [{"t": 0, "target": "organ", "dist": 0.6, "az": 0, "el": 5, "fov": 30}, {"t": 12, "target": "organ", "dist": 0.6, "az": 0, "el": 5, "fov": 30}], "layers": {}}
        ref = framing.measure(base, A, 6.0, "organ")["fill"]
        for lens in variety.LENSES:
            s = variety.apply(base, {"move": "as_designed", "look": "steel", "lens": lens})
            self.assertAlmostEqual(framing.measure(s, A, 6.0, "organ")["fill"], ref, delta=0.03, msg=lens)

    def test_no_direction_no_change(self):
        sp = self.spec(); self.assertEqual(variety.apply(sp, None), sp)

    def test_every_look_has_a_page_palette(self):
        js = (Path(__file__).resolve().parent / "health_cinema" / "threejs" / "atmosphere.js").read_text(encoding="utf-8")
        for lk in variety.LOOKS.values(): self.assertIn(f"  {lk['palette']}: {{", js)


@unittest.skipUnless(assets.anatomy_assets("abdomen") and assets.anatomy_assets("chest"), "3D models not installed")
class RealTemplates(unittest.TestCase):
    def test_moves_keep_real_organs_in_frame(self):
        from health_cinema import clips
        for tpl in ("auto:liver:orbit", "auto:kidney:peel", "heart_journey"):
            a = assets.anatomy_assets(library.model_of(tpl) or assets.TEMPLATE_ASSET[tpl]); A = json.loads(Path(a["anchors"]).read_text(encoding="utf-8"))["anchors"]
            for move in variety.MOVES:
                s = variety.apply(clips.template_spec(tpl), {"move": move, "look": "steel"}); rows = framing.audit(s, A, settle=0.0)
                self.assertLessEqual(max(r["cut"] for r in rows), 0.06, (tpl, move))


if __name__ == "__main__":
    unittest.main()
