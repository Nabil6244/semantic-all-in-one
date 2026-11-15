"""Ocean beat mode (ocean/beats.py): the beat CSV -> timed beats -> pictures / clips / graphics, and the smooth picture move."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ocean import beats as BT
from ocean import clips as CL

CSV = '''type,text,visual,prompt
cast,,LION,"adult male lion, dark mane"
beat,"You weigh four hundred and twenty pounds.",graphic,"number: 420 LB | what you weigh"
beat,"A lion kills by pouncing on prey",picture,"[LION] clamping its jaws on a zebra's throat"
beat,"around an animal's windpipe.",clip,"lion hunting"
'''


def _words(text, step=0.4):
    out, t = [], 0.0
    for w in text.split():
        out.append((w, t, t + step * 0.8))
        t += step
    return out


class BeatsTest(unittest.TestCase):
    def test_read_and_time(self):
        cast, beats = BT.read(CSV)
        self.assertEqual(cast, {"LION": "adult male lion, dark mane"})
        self.assertEqual([b["visual"] for b in beats], ["graphic", "picture", "clip"])
        words = _words(" ".join(b["text"] for b in beats))
        tb = BT.timed(beats, words, 9.0)
        self.assertEqual(tb[0]["start"], 0.0)
        self.assertAlmostEqual(tb[1]["start"], 7 * 0.4, places=3)          # "A" is the 8th word
        self.assertEqual(tb[-1]["end"], 9.0)

    def test_picture_prompt_uses_the_cast_look(self):
        p = BT.picture_prompt("[LION] roaring", {"LION": "adult male lion, dark mane"})
        self.assertTrue(p.startswith("adult male lion, dark mane roaring"))
        self.assertIn("illustration", p)

    def test_graphics(self):
        self.assertEqual(BT.graphic("number: 420 LB | what you weigh")[0], "number_hero")
        k, a = BT.graphic("bars: TOP SPEED | human 18 mph | honey badger 19 mph")
        self.assertEqual(k, "hud_bars")
        self.assertEqual([r[1] for r in a["rows"]], [18.0, 19.0])
        self.assertEqual(BT.graphic("percent: 50 | of cubs")[0], "progress")
        self.assertEqual(BT.graphic("time: 45 minutes")[1]["hours"], 0.75)
        self.assertEqual(BT.graphic("map: Kalahari")[0], "map_pin")
        self.assertEqual(BT.graphic("year: 1966 | first record")[0], "year_anchor")
        self.assertEqual(BT.graphic("title: THE TSAVO LIONS | Kenya, 1898")[0], "title_banner")
        k, a = BT.graphic("checklist: TRIED | soldiers | v poison | stamp ALL FAILED")
        self.assertEqual((k, a["items"], a["stamp"]), ("checklist", [["soldiers", False], ["poison", True]], "ALL FAILED"))
        self.assertEqual(BT.graphic("text: FOUR HUNDRED.")[0], "statement")
        self.assertEqual(BT.graphic("labels: LION | massive shoulders")[1]["animal"], "lion")
        self.assertEqual(BT.graphic("dots: Kalahari | 400 | deaths")[1]["dots"], 60)

    def test_rig_steps_its_legs(self):
        import numpy as np
        from ocean import rig as RG
        rg = RG.rig_for("lion", 400)
        self.assertTrue(rg.ok)
        self.assertEqual(len(rg.legs), 4)
        a, b = np.asarray(rg.pose(0.0, "walk")), np.asarray(rg.pose(0.25, "walk"))
        self.assertGreater(np.abs(a.astype(int) - b.astype(int)).sum(), 0)        # the legs moved between the frames

    def test_puppet_walks_on_jointed_legs(self):
        import numpy as np
        from ocean import puppet as PU
        for name in ("lion", "tiger", "honey_badger", "cape_buffalo"):
            p = PU.Puppet(name, 300)
            a, b = p.pose(0.0, "walk"), p.pose(0.25, "walk")
            self.assertEqual(a.size, b.size)                                       # one frame size the whole cycle
            self.assertGreater(np.abs(np.asarray(a).astype(int) - np.asarray(b).astype(int)).sum(), 0)
            self.assertIsNotNone(a.getbbox())
        self.assertTrue(PU.has("jaguar") and not PU.has("great_white"))

    def test_generate_asks_for_missing_vector_art(self):
        from ocean import art_flow as AF
        plan = {"drawn": [{"names": ["lion", "wildebeest"]}],
                "layers": [{"params": {"elements": [{"kind": "ocean_number_hero", "args": {"flat_art": True, "animal": "skunk"}}]}}]}
        need = dict(AF.vector_needs_for_plan(plan))
        self.assertNotIn("lion", need)                                           # already in the library
        self.assertEqual(need.get("wildebeest"), "vector")
        self.assertIn("vector", AF.prompt("wildebeest", "vector").lower())

    def test_upgrade_turns_fact_beats_into_graphics(self):
        beats = [{"text": "Picture this.", "visual": "picture", "prompt": "x"},
                 {"text": "You weigh four hundred and twenty pounds.", "visual": "picture", "prompt": "[LION] standing"},
                 {"text": "Option two is climbing a tree.", "visual": "picture", "prompt": "a man climbing a tree"},
                 {"text": "Lions hunt in Kenya.", "visual": "clip", "prompt": "lion hunting"}]
        up = BT.upgrade(beats)
        self.assertEqual([b["visual"] for b in up], ["picture", "graphic", "picture", "clip"])
        self.assertTrue(up[1]["prompt"].startswith("number: 420 LB"))

    def test_plan_lists_pictures_and_clips_for_the_visuals_tab(self):
        cast, beats = BT.read(CSV)
        tb = BT.timed(beats, _words(" ".join(b["text"] for b in beats)), 9.0)
        p = BT.plan(tb, cast, 9.0)
        self.assertEqual(p["mode"], "beats")
        self.assertEqual([s["kind"] for s in p["clips"]], ["clip"])                # two library animals: drawn on the stage
        self.assertEqual([s["visual"] for s in p["shots"]], ["graphic", "drawn", "clip"])
        self.assertEqual([d["names"] for d in p["drawn"]], [["lion", "zebra"]])      # acted on legs, not a sliding sticker
        rows = CL.visual_scenes(p["clips"])
        self.assertEqual([r["asset_type"] for r in rows], ["stock_video"])
        _c, more = BT.read(CSV.replace("on a zebra's throat", "next to a termite mound"))
        p2 = BT.plan(BT.timed(more, _words(" ".join(b["text"] for b in more)), 9.0), cast, 9.0)
        self.assertEqual(p2["clips"][0]["kind"], "act")                         # a prop in the frame: a painted picture
        self.assertIn("adult male lion", p2["clips"][0]["query"])
        kinds = [e["kind"] for ly in p["layers"] for e in ly["params"].get("elements") or []]
        self.assertIn("ocean_number_hero", kinds)

    def test_picture_move_is_smooth(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "p.png"
            im = Image.new("RGB", (1600, 900), (20, 40, 60))
            for x in range(0, 1600, 40):
                im.paste((200, 200, 200), (x, 0, x + 4, 900))
            im.save(src)
            dst = Path(d) / "m.mp4"
            CL.motion(str(src), str(dst), 1.2, "pan_right")
            n = subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                                         "stream=nb_read_frames", "-of", "csv=p=0", str(dst)]).decode().strip()
            self.assertEqual(int(n), 30)


class ActTest(unittest.TestCase):
    def test_classify(self):
        from ocean import act as AC
        self.assertEqual(AC.classify("[BADGER] trotting forward through dry grass"), "walk")
        self.assertEqual(AC.classify("[LIONESS] leaping onto the back of a Cape buffalo"), "attack")
        self.assertEqual(AC.classify("[LION] walking away into the sunset"), "flee")
        self.assertIsNone(AC.classify("cutaway of a zebra's neck with the windpipe squeezed shut"))
        self.assertIsNone(AC.classify("extreme close-up of [LION] snarling"))
        self.assertEqual(AC.classify("[LION] standing on a rock"), "idle")
        self.assertEqual(AC.setting("[BADGER] trotting across moonlit desert sand at night"), "savanna_night")

    def test_walk_moves_the_legs(self):
        import numpy as np
        from ocean import act as AC
        sp = Image.new("RGBA", (200, 120), (0, 0, 0, 0))
        from PIL import ImageDraw
        d = ImageDraw.Draw(sp)
        d.rectangle((20, 20, 180, 70), fill=(120, 90, 60, 255))
        for x in (30, 60, 140, 165):
            d.rectangle((x, 70, x + 10, 118), fill=(90, 70, 50, 255))
        legs = AC._legs(sp)
        a = np.asarray(AC._gait(sp, 0.5 * np.pi, 8, legs).getchannel("A"))
        b = np.asarray(AC._gait(sp, 1.5 * np.pi, 8, legs).getchannel("A"))
        self.assertTrue((a[110] != b[110]).any())                   # the feet are in different places
        self.assertTrue((a[30] == b[30]).all())                     # the body stays

    def test_animate_writes_a_clip(self):
        from ocean import act as AC
        with tempfile.TemporaryDirectory() as d:
            sp = Image.new("RGBA", (300, 160), (0, 0, 0, 0))
            from PIL import ImageDraw
            ImageDraw.Draw(sp).ellipse((10, 20, 290, 150), fill=(150, 120, 80, 255))
            src = Path(d) / "a.png"
            sp.save(src)
            dst = Path(d) / "a.mp4"
            AC.animate(str(src), str(dst), 0.8, "attack", "savanna", "right", 1)
            self.assertGreater(dst.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
