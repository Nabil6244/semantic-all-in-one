"""Health Cinema shows information, not only pictures: numbers the narration says (digits or words), checklists, steps, do/don't comparisons, graphics over
footage and 3D (a figure, a label, a heart-rate line), and illustration cards pinned on organ 3D scenes, made through the Visuals tab."""
from __future__ import annotations
import json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace

_ILL = tempfile.mkdtemp(prefix="hc_ill_test_"); os.environ["HEALTH_CINEMA_ILLUSTRATION_DIR"] = _ILL

from PIL import Image

from health_cinema import assets, cards, clips, direction, engine, planner, profiles as P, scenes_csv as C, spoken as SP

HAVE_FFMPEG = bool(assets.ffmpeg_path())
PROF = P.get_profile(P.DEFAULT_PROFILE)


class SpokenNumbers(unittest.TestCase):
    def test_words_digits_ranges_and_units(self):
        cases = {"your heart is beating about seventy times a minute.": ("70", "times a minute"),
                 "through three main vessels called the coronary arteries.": ("3", "main vessels"),
                 "after roughly twenty to thirty minutes of a complete blockage": ("20-30", "minutes"),
                 "beats about one hundred thousand times a day.": ("100,000", "times a day"),
                 "Up to 80% of strokes are preventable.": ("80", "%"), "Every 40 seconds, someone has a stroke.": ("40", "seconds")}
        for text, (num, unit) in cases.items():
            got = SP.spoken_number(text)
            self.assertEqual((got["number"], got["unit"]), (num, unit), text)

    def test_words_that_are_not_figures(self):
        for text in ("Then, one ordinary morning, it can change everything.", "Second, do not drive yourself.", "a friend who is over fifty.", "every second of your life"):
            self.assertIsNone(SP.spoken_number(text), text)

    def test_items_appear_when_spoken_and_in_order(self):
        s = [{"text": "You may feel chest pressure, an ache in the jaw, and shortness of breath.", "start": 10.0, "end": 16.0}]
        got = SP.times_for(["Chest pressure", "Ache in the jaw", "Shortness of breath"], s, 10.0, 8.0)
        ts = [g["t0"] for g in got]
        self.assertEqual(ts, sorted(ts)); self.assertGreater(ts[2], ts[0] + 1.0); self.assertLessEqual(ts[-1], 7.0)


CSV = """text,visual,organ,items,do,dont,overlay,stat,stat_unit,overlay_text,card_type,card_ref,card_prompt,footage
Right now your heart is beating about seventy times a minute.,footage,,,,,,,,,,,,heart monitor
Watch for chest pressure and a strange ache in the jaw and shortness of breath.,checklist,,chest pressure | ache in the jaw | shortness of breath,,,,,,,,,,
Not a relative. Not a neighbor. Emergency services first.,compare,,,emergency services first,a relative | a neighbor,,,,,,,,
That supply comes through three main vessels called the coronary arteries.,3d,heart,,,,label,,,Coronary arteries,mechanism,plaque_test_v1,a plaque cracking inside an artery,
It can take twenty to thirty minutes.,footage,,,,,none,,,,,,,clock ticking
"""


def plan_of(csv_text):
    rows = C.parse_csv_text(csv_text); t = 0.0
    for r in rows: r["start"], r["end"] = t, t + 6.0; t += 6.0
    return planner.plan_directed(rows, P.DEFAULT_PROFILE, direction.dscenes_from_rows(rows), lambda tpl: True, allow_footage=True)["scenes"]


class Planning(unittest.TestCase):
    def test_every_new_kind_and_overlay(self):
        sc = plan_of(CSV)
        self.assertEqual([s.kind for s in sc], ["footage", "list_card", "compare_card", "anatomy_3d", "footage"])
        self.assertEqual(sc[0].visual["overlays"][0]["number"], "70"); self.assertTrue(sc[0].visual["overlays"][0]["auto"])      # a figure the narration says, over the footage
        self.assertEqual([i["text"] for i in sc[1].visual["items"]], ["chest pressure", "ache in the jaw", "shortness of breath"])
        self.assertEqual([i["text"] for i in sc[2].visual["dont"]], ["a relative", "a neighbor"])
        self.assertEqual(sc[3].visual["overlays"], [{"type": "label", "text": "Coronary arteries", "t0": 0.6}])
        self.assertEqual(sc[3].visual["cards"][0]["ref"], "plaque_test_v1")
        self.assertNotIn("overlays", sc[4].visual)      # overlay=none: no figure, although the sentence says one

    def test_bad_rows_name_the_problem(self):
        for bad, why in (("text,visual,items\nA b.,checklist,only one\n", "two items"), ("text,visual,do\nA b.,compare,x\n", "dont"),
                         ("text,overlay\nA b.,stat\n", "stat column"), ("text,overlay\nA b.,sparkle\n", "not one of")):
            with self.assertRaises(ValueError) as c: C.parse_csv_text(bad)
            self.assertIn(why, str(c.exception))

    def test_illustration_cards_are_listed_once(self):
        got = engine.illustrations_wanted(plan_of(CSV))
        self.assertEqual([g["ref"] for g in got], ["plaque_test_v1"]); self.assertIn("plaque", got[0]["prompt"])


    def test_joined_3d_rows_keep_both_overlays_and_cards(self):
        two = ("text,visual,organ,overlay,stat,stat_unit,overlay_text,card_type,card_ref,card_prompt\n"
               "Your heart beats about seventy times a minute.,3d,heart,stat,70,beats a minute,,,,\n"
               "Plaque builds up inside its arteries.,3d,heart,label,,,Plaque,mechanism,plaque_two_v1,a plaque in an artery\n")
        sc = plan_of(two)
        self.assertEqual(len(sc), 1); ovs = sc[0].visual["overlays"]
        self.assertEqual([o["type"] for o in ovs], ["stat", "label"]); self.assertLessEqual(ovs[0]["t1"], ovs[1]["t0"]); self.assertGreaterEqual(ovs[1]["t0"], 6.0)
        self.assertEqual(sc[0].visual["cards"][0]["ref"], "plaque_two_v1"); self.assertGreaterEqual(sc[0].visual["cards"][0]["at"], 6.0)


class Drawing(unittest.TestCase):
    LIST = {"style": "checklist", "title": "", "items": [{"text": "chest pressure", "t0": 0.5}, {"text": "jaw ache", "t0": 2.0}]}
    CMP = {"title": "Who to call", "dont": [{"text": "a relative", "t0": 0.5}], "do": [{"text": "emergency services", "t0": 2.0}]}

    def test_items_appear_on_cue(self):
        before, after = cards.draw_card("list_card", self.LIST, PROF, 640, 360, 1.5), cards.draw_card("list_card", self.LIST, PROF, 640, 360, 3.0)
        self.assertNotEqual(before.tobytes(), after.tobytes())
        self.assertNotEqual(cards.frame_state("list_card", self.LIST, 1.5, 24), cards.frame_state("list_card", self.LIST, 3.0, 24))
        self.assertEqual(cards.frame_state("list_card", self.LIST, 3.0, 24), cards.frame_state("list_card", self.LIST, 3.5, 24))      # still between items: not redrawn
        for style in ("steps", "checklist"): cards.draw_card("list_card", dict(self.LIST, style=style), PROF, 640, 360, 3.0)
        cards.draw_card("compare_card", self.CMP, PROF, 640, 360, 3.0)

    def test_high_end_shots(self):
        from health_cinema.edit import shots
        base = {"t0": 0, "t1": 4, "accent": [255, 112, 90], "seed": 1, "scene_no": 1, "role": "x", "intensity": 1, "overlays": []}
        shots.KINDS["list"](dict(base, kind="list", gfx=self.LIST), 640, 360, 0).frame(3.0, 72)
        shots.KINDS["compare"](dict(base, kind="compare", gfx=self.CMP), 640, 360, 0).frame(3.0, 72)
        ov = [{"type": "pic_stat", "number": "70", "unit": "bpm", "t0": 0.2, "t1": 3.5}, {"type": "pic_pulse", "t0": 0.2, "t1": 3.5}, {"type": "pic_label", "text": "Heart", "t0": 0.2, "t1": 3.5}]
        a = shots.KINDS["statement"](dict(base, kind="statement", gfx={"beats": [{"text": "x", "t0": 0}]}), 640, 360, 0).frame(2.0, 48)
        b = shots.KINDS["statement"](dict(base, kind="statement", gfx={"beats": [{"text": "x", "t0": 0}]}, overlays=ov), 640, 360, 0).frame(2.0, 48)
        self.assertNotEqual(a.tobytes(), b.tobytes())


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class OverPicture(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.d, ignore_errors=True); self.ff = assets.ffmpeg_path()
        self.src = self.d / "s.mp4"; subprocess.run([self.ff, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=24:d=3", "-pix_fmt", "yuv420p", str(self.src)], check=True)

    def _frame(self, clip, t=2.0):
        png = self.d / f"{clip.stem}.png"; subprocess.run([self.ff, "-y", "-v", "error", "-ss", str(t), "-i", str(clip), "-frames:v", "1", str(png)], check=True)
        return Image.open(png).convert("RGB")

    def test_each_overlay_is_drawn_over_footage_and_3d(self):
        plain = self.d / "plain.mp4"; clips._footage_clip(str(self.src), 640, 360, 72, plain, self.ff)
        for ov in ({"type": "stat", "number": "70", "unit": "bpm", "t0": 0.3}, {"type": "label", "text": "Coronary arteries", "t0": 0.3}, {"type": "pulse", "bpm": "70", "t0": 0.3}):
            out = self.d / f"{ov['type']}.mp4"; clips._footage_clip(str(self.src), 640, 360, 72, out, self.ff, overlay=ov, accent=PROF.accent)
            self.assertNotEqual(self._frame(out).tobytes(), self._frame(plain).tobytes(), ov["type"])
        out = self.d / "3d.mp4"; clips._with_overlay(str(self.src), {"type": "stat", "number": "3", "unit": "vessels", "t0": 0.3}, 640, 360, 72, out, self.ff, PROF.accent)
        self.assertTrue(out.is_file())


class OrganCards(unittest.TestCase):
    def test_a_library_picture_is_pinned_where_the_camera_looks(self):
        from health_cinema import illustrations as ILL
        p = Path(_ILL) / "src.png"; Image.new("RGB", (64, 40), (20, 90, 160)).save(p)
        ILL.register(p, id="plaque_test_v1", topic="plaque", view="mechanism", kind="mechanism", prompt="x", source="flow")
        spec = {"duration": 10.0, "camera": [{"t": 0, "target": "body"}, {"t": 4, "target": "heart"}], "labels": []}
        got = clips.organ_cards([{"ref": "plaque_test_v1"}, {"ref": "not_made_yet_v1"}], spec, {"body": {}, "heart": {}})
        self.assertEqual(len(got), 1); self.assertEqual(got[0]["anchor"], "heart"); self.assertLess(got[0]["t0"], got[0]["t1"])

    def test_visuals_rows_file_the_picture_in_the_library(self):
        import visual_bridge
        from health_cinema import app_section as A, illustrations as ILL
        folder = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        made = folder / "made.png"; Image.new("RGB", (64, 40), (200, 50, 50)).save(made)
        class Mgr:
            def resolve_all(self, rows):
                for r in rows: visual_bridge.seed(folder, r.scene_number, str(made), "flow_image", prompt=r.prompt)
        rows = A.illustration_rows([{"ref": "new_card_v1", "prompt": "a blocked artery", "type": "mechanism", "topic": "artery", "narration": "n"}], Mgr(), folder, lambda: False, lambda m: None)
        self.assertEqual(rows[0].scene_number, "5001"); self.assertTrue(rows[0].visual_description.startswith("illustration:new_card_v1"))
        A.to_library(rows, folder, lambda m: None)
        self.assertEqual(ILL.find("new_card_v1")["sha256"], ILL.sha256(made))


if __name__ == "__main__":
    unittest.main()
