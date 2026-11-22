"""Stickman Phase 5: the Host Explainer option (your picture in the corner) and the Meme look. No network, no Flow."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from stickman import backgrounds, checker, csvplan, director, draw, host, looks, timeline
from test_stickman_director import BODY, fake_words


def _spec(look="ink_paper", shorts=False, size=None):
    w, d = fake_words(BODY)
    s = director.direct(BODY, w, d, title="Why You're Always Tired", look=look, shorts=shorts)
    s, _, _ = checker.repair(s)
    s["size"] = size or ([320, 568] if shorts else [480, 270])
    return s


def _img(fr, spec, look):
    W, H = spec["size"]
    return np.asarray(Image.frombytes("RGB", (W, H), draw.frame(fr, spec, looks.get(look))), np.int16)


class HostTests(unittest.TestCase):
    def test_puppet_folder_is_a_host(self):
        self.assertIn("girl", host.hosts())

    def test_mouth_follows_words(self):
        sp = [[1.0, 1.5, 2], [2.0, 2.2, 1]]
        self.assertEqual(host.mouth_open(sp, 0.5), 0.0)
        self.assertGreater(host.mouth_open(sp, 1.12), 0.5)
        self.assertEqual(host.mouth_open(sp, 1.8), 0.0)
        self.assertGreater(host.talking(sp, 1.8), 0.3)
        self.assertEqual(host.talking(sp, 5.0), 0.0)

    def test_setup_moves_stage_and_captions(self):
        s = host.setup(_spec(), "girl", [{"word": "hello", "start": 0.2, "end": 0.6}])
        self.assertEqual(s["host_shift"], host.LAYOUT_16x9["host_shift"])
        self.assertLess(s["layout"]["caption_x"], 0.5)
        self.assertEqual(s["speech"][0][2], 2)
        sh = host.setup(_spec(shorts=True), "girl")
        self.assertEqual(sh["host_shift"], 0.0)
        self.assertGreater(sh["layout"]["caption_x"], 0.5)

    def test_host_is_drawn_bottom_right(self):
        plain = _spec()
        withh = host.setup(_spec(), "girl")
        fr = timeline.simulate(withh)[200]
        a, b = _img(fr, plain, "ink_paper"), _img(fr, withh, "ink_paper")
        H, W = a.shape[:2]
        diff = np.abs(a - b).sum(2) > 40
        self.assertGreater(diff[int(H * 0.6):, int(W * 0.82):].mean(), 0.25)      # the host is there
        self.assertLess(diff[: int(H * 0.4), : int(W * 0.15)].mean(), 0.2)

    def test_csv_host_in_look_cell(self):
        rows, problems = csvplan.read("line,look\nHello there.,meme+host\nBye now.,\n")
        self.assertEqual(problems, [])
        self.assertEqual(csvplan.look_of(rows), "meme")
        self.assertEqual(csvplan.host_of(rows), "girl")
        _, problems = csvplan.read("line,look\nHello there.,ink_paper+host:nobody\n")
        self.assertEqual(len(problems), 1)


class MemeTests(unittest.TestCase):
    def test_painted_room_shows_and_falls_back(self):
        s = _spec("meme")
        frs = timeline.simulate(s)
        fr = frs[120]
        drawn = _img(fr, s, "meme")
        with tempfile.TemporaryDirectory() as d:
            pic = Path(d) / "room.png"
            Image.new("RGB", (800, 450), (200, 40, 160)).save(pic)
            s2 = dict(s, backdrops={fr["place"] or "void": str(pic)})
            painted = _img(fr, s2, "meme")
            s3 = dict(s, backdrops={fr["place"] or "void": str(Path(d) / "missing.png")})
            broken = _img(fr, s3, "meme")
        corner = painted[5:20, 5:20].reshape(-1, 3).mean(0)
        self.assertLess(np.abs(corner - (200, 40, 160)).max(), 12)
        self.assertTrue(np.array_equal(broken, drawn))                            # unreadable picture: drawn room

    def test_prompts_cover_every_place(self):
        from stickman import places
        self.assertEqual(set(backgrounds.PROMPTS), set(places.PLACES))
        self.assertNotEqual(backgrounds.path_for("park", True), backgrounds.path_for("park", False))

    def test_no_flow_needed_when_all_painted(self):
        calls = []
        orig = backgrounds._flow_up
        backgrounds._flow_up = lambda: calls.append(1) or False
        try:
            old = backgrounds.STORE
            with tempfile.TemporaryDirectory() as d:
                backgrounds.STORE = Path(d)
                for pl in ("park", "office"):
                    backgrounds.path_for(pl, False).parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGB", (8, 8)).save(backgrounds.path_for(pl, False))
                got, missing = backgrounds.paint(["park", "office"], False, log=lambda m: None)
            backgrounds.STORE = old
        finally:
            backgrounds._flow_up = orig
        self.assertEqual((sorted(got), missing, calls), (["office", "park"], [], []))


if __name__ == "__main__":
    unittest.main()
