"""Aviation style step 2: the blue article card (browser window on a moving blue backdrop) and the 'Source:' tag."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from aviation import cards as K


def _photo(path: Path, color=(200, 120, 60)) -> str:
    im = Image.new("RGB", (800, 500), color)
    d = ImageDraw.Draw(im)
    d.rectangle([100, 200, 700, 300], fill=(240, 240, 240))       # something with edges, like a plane on a sky
    im.save(path)
    return str(path)


def _diff(a, b) -> int:
    return sum(ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L").histogram()[12:])


class ArticleCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        cls.img = _photo(d / "a.png")
        cls.imgs = [_photo(d / f"c{i}.png", (60 + 40 * i, 90, 160)) for i in range(4)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def card(self, t=2.0, dur=5.0, **p):
        return K.lay_article(t, dur, p)

    def test_full_frame_rgba(self):
        im = self.card(image=self.img, outlet="The Guardian", headline="Air France workers rip shirts from executives", date="October 6, 2015")
        self.assertEqual(im.size, (1280, 720))
        self.assertEqual(im.mode, "RGBA")

    def test_nothing_to_show_draws_nothing(self):
        self.assertIsNone(self.card())
        self.assertIsNone(self.card(image="/no/such/file.png"))

    def test_backdrop_is_brand_blue(self):
        im = self.card(image=self.img, headline="x").convert("RGB")
        for xy in ((20, 20), (1260, 700), (20, 700)):
            r, g, b = im.getpixel(xy)
            self.assertGreater(b, r + 60, xy)
            self.assertGreater(b, g + 40, xy)

    def test_window_holds_the_photo(self):
        im = self.card(image=self.img, headline="x").convert("RGB")
        # the photo's orange appears in the upper-middle where the window sits
        hits = sum(1 for x in range(400, 880, 20) for y in range(120, 360, 20) if im.getpixel((x, y))[0] > 150 and im.getpixel((x, y))[2] < 110)
        self.assertGreater(hits, 20)

    def test_it_never_sits_still(self):
        a, b, c = (self.card(t=t, image=self.img, headline="x") for t in (0.2, 2.0, 4.0))
        self.assertGreater(_diff(a, b), 1000)       # window slides in
        self.assertGreater(_diff(b, c), 1000)       # then the picture keeps pushing in and the light keeps moving

    def test_pure_function_of_t(self):
        self.assertEqual(_diff(self.card(t=1.5, image=self.img, headline="x"), self.card(t=1.5, image=self.img, headline="x")), 0)

    def test_headline_text_changes_the_frame(self):
        a = self.card(image=self.img, outlet="Simple Flying", headline="Air France To Shut Down Joon", date="January 10, 2019")
        b = self.card(image=self.img)
        self.assertGreater(_diff(a, b), 500)

    def test_headline_only_is_a_plain_page(self):
        im = self.card(outlet="TRAVELWEEKLY", headline="Air France launches Joon from Paris", date="December 1, 2017")
        self.assertIsNotNone(im)
        # a white page inside the window (mostly white; the headline is dark type on it)
        rgb = im.convert("RGB")
        pts = [rgb.getpixel((x, y)) for x in range(380, 840, 10) for y in range(140, 360, 10)]
        self.assertGreater(sum(1 for p in pts if min(p) > 200) / len(pts), 0.6)

    def test_fact_strip_and_name_tag(self):
        a = self.card(image=self.img, fact="Carried 3 million passengers from December 2017 to December 2018")
        b = self.card(image=self.img, name="Xavier Broseta", role="Former deputy director of HR, Air France")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertGreater(_diff(a, self.card(image=self.img)), 500)
        self.assertGreater(_diff(b, self.card(image=self.img)), 500)

    def test_collage_builds_one_window_at_a_time(self):
        early = K.lay_collage(0.3, 6.0, {"images": self.imgs})
        late = K.lay_collage(4.0, 6.0, {"images": self.imgs})
        self.assertIsNotNone(late)
        self.assertGreater(K.windows_shown(4.0, 4), K.windows_shown(0.3, 4))
        self.assertEqual(K.windows_shown(4.0, 4), 4)
        self.assertGreater(_diff(early, late), 5000)

    def test_collage_needs_two_pictures(self):
        self.assertIsNone(K.lay_collage(2.0, 5.0, {"images": self.imgs[:1]}))

    def test_wordmark_only_when_given(self):
        a = K.lay_collage(4.0, 6.0, {"images": self.imgs})
        b = K.lay_collage(4.0, 6.0, {"images": self.imgs, "brand": "skyline notes"})
        self.assertGreater(_diff(a, b), 200)


class SourceTagTests(unittest.TestCase):
    def test_tag_top_right_only(self):
        im = K.tag_source(1.0, 4.0, {"source": "Euronews"})
        self.assertEqual(im.size, (1280, 720))
        a = im.getchannel("A")
        box = a.getbbox()
        self.assertIsNotNone(box)
        self.assertGreater(box[0], 1280 * 0.6)
        self.assertLess(box[3], 720 * 0.12)

    def test_adds_prefix_once(self):
        self.assertEqual(K.source_text("Euronews"), "Source: Euronews")
        self.assertEqual(K.source_text("Source: CBS"), "Source: CBS")
        self.assertEqual(K.source_text("  "), "")

    def test_no_source_no_tag(self):
        self.assertIsNone(K.tag_source(1.0, 4.0, {"source": ""}))


if __name__ == "__main__":
    unittest.main()


class CardAnimationTests(unittest.TestCase):
    def test_numbers_count_up_in_a_fact(self):
        self.assertEqual(K.count_up("Carried 3 million passengers", 0.0, 0.6), "Carried 0 million passengers")
        self.assertEqual(K.count_up("Carried 3 million passengers", 5.0, 0.6), "Carried 3 million passengers")
        self.assertEqual(K.count_up("cut 2,900 jobs", 0.6 + 0.35, 0.6), "cut 1,450 jobs")

    def test_card_leaves_at_the_end(self):
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            Image.new("RGB", (800, 500), (200, 120, 60)).save(f"{d}/a.png")
            p = {"image": f"{d}/a.png", "headline": "x"}
            mid, end = K.lay_article(2.5, 5.0, p), K.lay_article(4.95, 5.0, p)
            px = lambda im: im.convert("RGB").getpixel((640, 230))
            self.assertNotEqual(px(mid), px(end))

    def test_card_window_is_reference_size(self):
        self.assertGreaterEqual(K.WIN_W, 1280 * 0.58)
