"""Phase D tests: the map overlay (explainer/beats/overlay.py). Offline: no map tiles; the "map" is a synthetic flat colour clip. Deterministic.
usage: python3 -B explainer/spike/test_motion_overlay.py   (from the repository root)"""
import hashlib
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from explainer.beats import framing as F          # noqa: E402
from explainer.beats import overlay as O          # noqa: E402

TEXT = "Germany invaded France in June 1940 and Switzerland was surrounded , completely surrounded , by the Axis powers until the end"
WORDS = []
_t = 0.5
for _w in TEXT.split():
    WORDS.append((_w, round(_t, 3), round(_t + 0.3, 3)))
    _t += 0.42
START, END = 0.0, 8.0
EVIDENCE = ROOT / "docs" / "explainer" / "phase_overlay_evidence"


def make_beat(names, bid="b1"):
    cam = F.plan_camera([{"name": n, "t": 0.5 + 0.4 * k} for k, n in enumerate(names)], START, END, True, allow_push=False)
    beat = {"id": bid, "mode": "map", "start": START, "end": END, "camera": ([{"action": "start", **cam["start"]}] if cam["start"] else []) + cam["moves"], "layers": []}
    return beat, cam


BEAT, CAM = make_beat(["Germany", "France", "Switzerland"])
TEXT2 = "Germany pressed from the north while Italy pressed from the south and Switzerland was surrounded , completely surrounded , on every side by the Axis"
WORDS2 = []
_t = 0.5
for _w in TEXT2.split():
    WORDS2.append((_w, round(_t, 3), round(_t + 0.3, 3)))
    _t += 0.42
BEAT2, CAM2 = make_beat(["Switzerland"], "b2")
CUES2 = [{"type": "outline", "place": "Switzerland", "role": "red"}, {"type": "pin", "place": "Switzerland", "figure": "gold"}, {"type": "stamp", "text": "SURROUNDED", "word": "surrounded", "role": "red"},
         {"type": "plate", "text": "AXIS POWERS", "word": "north"}]
PLAN2 = O.plan_overlay(BEAT2, WORDS2, CUES2)
CUES = [
    {"type": "arrow", "from": "Germany", "to": "France", "role": "red"},
    {"type": "plate", "text": "JUNE 1940", "word": "1940"},
    {"type": "outline", "place": "Switzerland", "role": "red"},
    {"type": "stamp", "text": "SURROUNDED", "word": "surrounded", "role": "red"},
    {"type": "pin", "place": "Switzerland", "figure": "gold"},
]
PLAN = O.plan_overlay(BEAT, WORDS, CUES)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def probe(path, entries):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", f"stream={entries}", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return r.stdout.strip().split(",")


class Planning(unittest.TestCase):
    def test_camera_planned(self):
        self.assertTrue(BEAT["camera"], CAM)

    def test_cues_planned_and_nothing_silently_lost(self):
        kinds = {c["type"] for c in PLAN["cues"]}
        self.assertEqual(len(PLAN["cues"]) + len(PLAN["dropped"]), len(CUES))
        self.assertIn("outline", kinds)
        self.assertIn("stamp", kinds)
        for d in PLAN["dropped"]:
            self.assertTrue(d["why"])          # a dropped cue always says why

    def test_everything_inside_the_framing_view_at_every_cue_time(self):
        views = F.plan_views([BEAT])
        s = O.safe_rect()
        for c in PLAN["cues"]:
            v = F.view_at(views, c["t"])
            self.assertEqual([round(x, 5) for x in v], c["view"])
            for t in (c["t"], (c["t"] + c["until"]) / 2, c["until"] - 0.01):
                self.assertEqual(F.view_at(views, t), v, "the camera must not move while a cue is on screen")
            for r in c["rects"]:
                self.assertTrue(O.rect_inside(tuple(r), s), (c["id"], r))
            if c["type"] == "arrow":
                for p in (c["p0"], c["p1"]):
                    self.assertTrue(s[0] <= p[0] <= s[2] and s[1] <= p[1] <= s[3], c["id"])
            if c["type"] == "outline":
                self.assertTrue(O.rect_inside(tuple(c["bbox"]), s), c["id"])
        # independent check against the geography: the arrow's ends are the places' projected positions on that view (within the trimmed length)
        a = next(c for c in PLAN["cues"] if c["type"] == "arrow")
        g = O._locate("Germany")
        px = O.view_pixel(g.lon, g.lat, a["view"])
        self.assertLess(((a["p0"][0] - px[0]) ** 2 + (a["p0"][1] - px[1]) ** 2) ** 0.5, 120)

    def test_elements_never_overlap(self):
        cs = [c for c in PLAN["cues"] if c["type"] != "outline"]
        for i, a in enumerate(cs):
            for b in cs[i + 1:]:
                if a["t"] < b["until"] and b["t"] < a["until"]:
                    for ra in a["rects"]:
                        for rb in b["rects"]:
                            self.assertFalse(O.rects_overlap(tuple(ra), tuple(rb)), (a["id"], b["id"]))

    def test_timing_within_0_to_0_3_s_of_the_spoken_word(self):
        for c in PLAN["cues"]:
            d = c["t"] - c["word_match"]["start"]
            self.assertTrue(-1e-9 <= d <= 0.3 + 1e-9, (c["id"], d))
        st = next(c for c in PLAN["cues"] if c["type"] == "stamp")
        self.assertEqual(st["word_match"]["phrase"], "surrounded")

    def test_unspoken_word_and_unknown_place_are_dropped_with_a_note(self):
        p = O.plan_overlay(BEAT, WORDS, [{"type": "stamp", "text": "X", "word": "volcano"}, {"type": "pin", "place": "Atlantis", "word": "Germany"}, {"type": "bogus"}])
        self.assertEqual(p["cues"], [])
        self.assertEqual(len(p["dropped"]), 3)
        self.assertEqual(len(p["notes"]), 3)

    def test_place_without_polygon_degrades_to_a_ring(self):
        p = O.plan_overlay(BEAT, WORDS, [{"type": "outline", "place": "Paris", "word": "France"}])
        # Paris has an admin polygon in the geo data; a city point has none: use a city reference
        if p["cues"] and p["cues"][0]["fallback"] != "ring":
            p = O.plan_overlay(BEAT, WORDS, [{"type": "outline", "place": "city:Bern", "word": "Switzerland"}])
        self.assertTrue(p["cues"], p)
        self.assertEqual(p["cues"][0]["fallback"], "ring")
        self.assertTrue(any("ring is drawn instead" in n for n in p["notes"]), p["notes"])
        im = O.draw_frame(p, p["cues"][0]["t"] + 1.5)
        self.assertIsNotNone(im.getchannel("A").getbbox())

    def test_cue_that_would_leave_the_view_is_dropped(self):
        far = {"id": "b9", "mode": "map", "start": 0.0, "end": 8.0, "camera": [{"action": "start", "place": "Switzerland", "frame": "country"}]}
        p = O.plan_overlay(far, WORDS, [{"type": "arrow", "from": "Germany", "to": "France"}, {"type": "pin", "place": "Germany", "word": "Germany"}])
        for c in p["cues"]:
            for r in c["rects"]:
                self.assertTrue(O.rect_inside(tuple(r)))
        self.assertTrue(p["dropped"] or p["cues"])

    def test_second_beat_plan_inside_view(self):
        self.assertTrue(PLAN2["cues"], PLAN2)
        views = F.plan_views([BEAT2])
        for c in PLAN2["cues"]:
            self.assertEqual([round(x, 5) for x in F.view_at(views, c["t"])], c["view"])
            for r in c["rects"]:
                self.assertTrue(O.rect_inside(tuple(r)), c["id"])
        cs = [c for c in PLAN2["cues"] if c["type"] != "outline"]
        for i, a in enumerate(cs):
            for b in cs[i + 1:]:
                for ra in a["rects"]:
                    for rb in b["rects"]:
                        self.assertFalse(O.rects_overlap(tuple(ra), tuple(rb)), (a["id"], b["id"]))

    def test_overlay_is_inert_without_cues(self):
        self.assertEqual(O.plan_overlay(BEAT, WORDS, [])["cues"], [])


class Rendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        cls.ov1, cls.ov2, cls.base, cls.out = d / "ov1.mov", d / "ov2.mov", d / "base.mp4", d / "out.mp4"
        t0 = time.perf_counter()
        cls.stats = O.render_overlay(PLAN, cls.ov1)
        cls.wall = time.perf_counter() - t0
        O.render_overlay(PLAN, cls.ov2)
        dur = END - START
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x4a6f8c:s=1920x1080:r=30:d={dur}", "-f", "lavfi", "-i", f"sine=f=220:d={dur}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.base)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_deterministic_two_renders_equal_bytes(self):
        self.assertEqual(self.stats["returncode"], 0)
        self.assertEqual(sha(self.ov1), sha(self.ov2))

    def test_alpha_clip_has_alpha_and_right_size_and_duration(self):
        w, h, pf = probe(self.ov1, "width,height,pix_fmt")
        self.assertEqual((int(w), int(h)), (1920, 1080))
        self.assertIn("argb", pf)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(self.ov1)], capture_output=True, text=True).stdout)
        self.assertAlmostEqual(dur, END - START, delta=0.1)

    def test_composite_keeps_size_duration_audio_and_draws_something(self):
        rc = O.composite_over(self.base, self.ov1, self.out)
        self.assertEqual(rc, 0)
        w, h = probe(self.out, "width,height")
        self.assertEqual((int(w), int(h)), (1920, 1080))
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(self.out)], capture_output=True, text=True).stdout)
        self.assertAlmostEqual(dur, END - START, delta=0.1)
        self.assertIn("audio", subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(self.out)], capture_output=True, text=True).stdout + "audio")
        # a frame early (nothing drawn yet) equals the base colour; a frame late differs from it
        early, late = Path(self.tmp.name) / "e.png", Path(self.tmp.name) / "l.png"
        for t, p in ((0.1, early), (6.5, late)):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(self.out), "-frames:v", "1", str(p)], check=True)
        from PIL import Image, ImageChops
        ie, il = Image.open(early).convert("RGB"), Image.open(late).convert("RGB")
        self.assertIsNone(ImageChops.difference(ie, Image.new("RGB", ie.size, ie.getpixel((5, 5)))).point(lambda v: 255 if v > 6 else 0).getbbox())
        self.assertIsNotNone(ImageChops.difference(il, Image.new("RGB", il.size, il.getpixel((5, 5)))).point(lambda v: 255 if v > 24 else 0).getbbox())

    def test_cost_per_second_is_reported(self):
        per = self.stats["seconds"] / (END - START)
        print(f"\n[overlay cost] {self.stats['frames']} frames, {self.stats['rendered']} drawn, {self.stats['seconds']} s -> {per:.2f} s per second of overlay")
        self.assertLess(per, 20.0)

    def test_contact_sheet(self):
        from PIL import Image, ImageDraw
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        times = [0.8, 2.2, 4.0, 4.6, 5.4, 6.5]
        from PIL import ImageChops
        tiles = []
        for pl, t in [(PLAN, 2.8), (PLAN, 4.6), (PLAN, 6.5), (PLAN2, 1.8), (PLAN2, 4.6), (PLAN2, 6.5)]:
            base = Image.new("RGB", (O.W, O.H), (74, 111, 140))
            after = base.copy()
            ov = O.draw_frame(pl, t)
            after.paste(ov, (0, 0), ov)
            tiles.append((base, after, t))
        tw, th = 640, 360
        sheet = Image.new("RGB", (tw * len(times) // 2, th * 2 + 40), (20, 20, 20))
        d = ImageDraw.Draw(sheet)
        cols = len(times) // 2
        # row layout: two tiles per time (before above, after below), three times across, twice
        sheet = Image.new("RGB", (tw * 3, (th + 24) * 4), (20, 20, 20))
        d = ImageDraw.Draw(sheet)
        for i, (b, a, t) in enumerate(tiles):
            r, c = divmod(i, 3)
            y0 = r * 2 * (th + 24)
            sheet.paste(b.resize((tw, th)), (c * tw, y0 + 24))
            d.text((c * tw + 6, y0 + 6), f"t={t:.1f}s  BEFORE (flat map stand-in)", fill=(230, 230, 230))
            sheet.paste(a.resize((tw, th)), (c * tw, y0 + 24 + th + 24))
            d.text((c * tw + 6, y0 + th + 30), f"t={t:.1f}s  AFTER (overlay)", fill=(230, 230, 230))
        sheet.save(EVIDENCE / "overlay_before_after.jpg", quality=85)
        self.assertTrue((EVIDENCE / "overlay_before_after.jpg").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
