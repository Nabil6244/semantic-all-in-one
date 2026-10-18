"""The bugs found in What If render #016 (Voyager 1, 2026-10-17), each checked without rendering."""

import json
import tempfile
import unittest
from pathlib import Path

from whatif import compile as wc
from whatif import planner
from whatif.planner import Shot, ShotPlan


class ScreenNames(unittest.TestCase):
    def test_a_shot_direction_is_cut_to_the_name(self):
        f = planner.screen_name
        self.assertEqual(f("Voyager 1 drifting in deep space"), "VOYAGER 1")
        self.assertEqual(f("Voyager 1 transmitting, new angle"), "VOYAGER 1")
        self.assertEqual(f("Saturn approach footage"), "SATURN APPROACH")
        self.assertEqual(f("Interstellar crossing (NASA illustration)"), "INTERSTELLAR CROSSING")
        self.assertEqual(f("Jupiter's faint ring"), "JUPITER'S FAINT RING")
        self.assertEqual(f("Pale Blue Dot"), "PALE BLUE DOT")


class EmptyPlates(unittest.TestCase):
    def test_a_plate_with_nothing_on_it_carries_the_spoken_words(self):
        from whatif.narration import Word

        words = [Word(w, w.lower(), 10 + i * 0.4, 10.3 + i * 0.4) for i, w in enumerate("the magnetic field should point a different way".split())]
        plate = Shot(id="s1", start=10.0, end=16.0, kind="plate", title="Magnetic field direction", text=" ".join(w.text for w in words))
        notes = []
        added = wc._fill_empty_plates([plate], [], notes, words)
        self.assertEqual(len(added), 1)
        self.assertIn("MAGNETIC FIELD", added[0]["text"])

    def test_a_plate_with_its_diagram_is_left_alone(self):
        plate = Shot(id="s1", start=10.0, end=16.0, kind="plate", title="X", text="a b c d")
        self.assertEqual(wc._fill_empty_plates([plate], [{"type": "tm_bars", "start": 10.0, "end": 16.0}], []), [])


class Repeats(unittest.TestCase):
    def test_the_same_picture_is_not_shown_again_within_90_s(self):
        with tempfile.TemporaryDirectory() as d:
            from PIL import Image

            pic = Path(d) / "dot.jpg"
            Image.new("RGB", (64, 36)).save(pic)     # a real picture: a 1-byte file is (rightly) a broken one
            shots = [Shot(id="s1", start=0, end=6, kind="image", file=str(pic), text="the pale blue dot photo"),
                     Shot(id="s2", start=6, end=12, kind="plate", text="a plate between them"),
                     Shot(id="s3", start=12, end=18, kind="image", file=str(pic), text="earth as a tiny point of light")]
            spec = wc.compile_spec(ShotPlan(shots=shots, layers=[], duration=18.0), media_dir=None)
        kinds = [s["kind"] for s in spec["shots"]]
        self.assertEqual(kinds[0], "image")
        self.assertNotEqual(kinds[-1], "image", "the third shot used the same picture 6 s after it left the screen")


class StockForNasa(unittest.TestCase):
    def test_a_stock_photo_on_a_nasa_row_is_set_aside(self):
        from whatif.media import _set_aside_stock_for_nasa

        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "005.jpg"
            f.write_bytes(b"x")
            (Path(d) / ".asset_manifest.json").write_text(json.dumps({"005": {"source": "stock_image", "status": "complete", "local_path": str(f),
                "source_url": "https://pixabay.com/photos/astronomy-space-universe-titan-6924052/", "user_override": True}}))
            s = Shot(id="s13", start=60, end=66, kind="image", asset="nasa_video:Voyager 1 launch Titan IIIE Centaur")
            s.row = 5
            self.assertEqual(_set_aside_stock_for_nasa([s], Path(d), lambda m: None), 1)
            self.assertFalse(f.exists())
            self.assertTrue((Path(d) / "_set_aside" / "005.jpg.stock_for_nasa").exists())
            self.assertEqual(json.loads((Path(d) / ".asset_manifest.json").read_text())["005"]["status"], "failed")


class NasaChecks(unittest.TestCase):
    def test_a_generic_word_is_no_evidence(self):
        from starmap.nasa_images import contradicts

        desc = ("Huygens reaches Titan  After a journey of seven years and millions of miles, the European Space Agency's Huygens probe has "
                "touched down on Titan.  Images from the probe were relayed back to Cassini and received on Earth by NASA's Deep Space Network.")
        self.assertTrue(contradicts("Deep Space Network antenna tracking Voyager", "KSC-05-S-00034", desc, "2005-01-31"))

    def test_people_at_a_news_conference_are_not_the_subject(self):
        from starmap.nasa_images import contradicts

        desc = ("Suzanne Dodd, Voyager project manager, holds a replica of the golden record carried on Voyager at a news conference on "
                "NASA's Voyager 1 spacecraft, Thursday, Sept. 12, 2013 at NASA Headquarters in Washington.")
        self.assertTrue(contradicts("Voyager 1 interstellar space 2013", "Voyager in Interstellar Space", desc, "2013-09-12"))
        self.assertIsNone(contradicts("Voyager project manager at a news conference", "Voyager in Interstellar Space", desc, "2013-09-12"))


if __name__ == "__main__":
    unittest.main()
