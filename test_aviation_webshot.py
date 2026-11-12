"""Aviation step 2: website screenshots of a cited article / report (a real browser on a local page; no network), and the page card."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from aviation import cards as K
from aviation import webshot as WS

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta property="og:site_name" content="Example Times"><meta property="og:title" content="Air France launches Joon from Paris">
<meta property="article:published_time" content="2017-12-01T09:00:00Z"><title>Joon | Example Times</title>
<style>body{margin:0;font-family:Georgia;background:#fff} header{height:90px;background:#123} h1{font-size:44px;margin:40px 60px}
p{margin:20px 60px;font-size:20px;line-height:1.6} .hero{margin:0 60px;height:420px;background:linear-gradient(#69c,#036)}
#cookie{position:fixed;left:0;right:0;bottom:0;height:260px;background:rgb(255,0,200);z-index:9999}</style></head>
<body><header></header><h1>Air France launches Joon from Paris</h1><div class="hero"></div>
<p>""" + ("Air France has launched Joon, its new airline for younger travellers. " * 40) + """</p>
<div id="cookie">We use cookies <button>Accept all</button></div></body></html>"""


class WebshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        (cls.d / "page.html").write_text(PAGE, encoding="utf-8")
        cls.res = WS.shot((cls.d / "page.html").as_uri(), cls.d / "cache")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _need(self):
        if not self.res.get("ok") and "playwright" in self.res.get("reason", "").lower():
            self.skipTest(self.res["reason"])

    def test_reads_the_page_and_its_tags(self):
        self._need()
        r = self.res
        self.assertTrue(r["ok"], r)
        self.assertTrue(Path(r["path"]).is_file())
        self.assertEqual(r["site"], "Example Times")
        self.assertEqual(r["title"], "Air France launches Joon from Paris")
        self.assertEqual(r["date"], "December 1, 2017")

    def test_cookie_bar_is_hidden_not_accepted(self):
        self._need()
        a = np.asarray(Image.open(self.res["path"]).convert("RGB"), dtype=np.int32)
        magenta = ((a[..., 0] > 230) & (a[..., 1] < 30) & (a[..., 2] > 180)).mean()
        self.assertLess(magenta, 0.001)

    def test_headline_is_inside_the_shot(self):
        self._need()
        box = self.res["headline_box"]
        self.assertTrue(box and 0 <= box[1] < 400, box)

    def test_cached_by_url(self):
        self._need()
        again = WS.shot((self.d / "page.html").as_uri(), self.d / "cache")
        self.assertTrue(again.get("cached"))

    def test_a_dead_page_fails_cleanly(self):
        r = WS.shot((self.d / "missing.html").as_uri(), self.d / "cache2", timeout_s=8)
        self.assertFalse(r["ok"])
        self.assertTrue(r["reason"])

    def test_only_web_urls(self):
        self.assertFalse(WS.shot("javascript:alert(1)", self.d / "c3")["ok"])


class PageCardTests(unittest.TestCase):
    def test_page_card_scrolls_the_screenshot_and_marks_the_headline(self):
        with tempfile.TemporaryDirectory() as d:
            pg = Image.new("RGB", (1280, 1800), (255, 255, 255))
            dr = ImageDraw.Draw(pg)
            for x in range(60, 900, 18):                               # letter strokes with white between them, like real type
                dr.rectangle([x, 145, x + 7, 195], fill=(20, 20, 20))
            pg.save(Path(d) / "p.png")
            p = {"page": str(Path(d) / "p.png"), "headline_box": [60, 140, 840, 60], "outlet": "Example Times",
                 "headline": "Air France launches Joon", "date": "December 1, 2017"}
            a, b = K.lay_article(0.6, 5.0, p), K.lay_article(3.5, 5.0, p)
            self.assertIsNotNone(a)
            diff = np.abs(np.asarray(a.convert("RGB"), dtype=np.int32) - np.asarray(b.convert("RGB"), dtype=np.int32)).mean()
            self.assertGreater(diff, 1.0)                              # it moves
            arr = np.asarray(b.convert("RGB"), dtype=np.int32)
            self.assertGreater(((arr[..., 0] > 200) & (arr[..., 1] > 180) & (arr[..., 2] < 120)).sum(), 500)


if __name__ == "__main__":
    unittest.main()


class CsvUrlTests(unittest.TestCase):
    def test_url_column_and_page_preparation(self):
        from aviation import csv_rows as V
        from aviation import runner as RN
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.csv"
            p.write_text("scene_number,script_segment,asset_type,prompt,mode,article,url\n"
                         '1,"Air France launched Joon.",none,,news,"Travel Weekly | Air France launches Joon from Paris | December 1, 2017",https://example.com/joon\n'
                         '2,"The report found the crew used old weather.",none,,evidence,,https://example.com/report\n'
                         '3,"No page here.",none,,news,,\n', encoding="utf-8")
            rows = V.read_rows(p)
            self.assertEqual(rows[0]["url"], "https://example.com/joon")
            shots = {"https://example.com/joon": {"ok": True, "path": "/x/joon.png", "site": "travelweekly.com", "title": "Air France launches Joon",
                                                  "date": "December 1, 2017", "headline_box": [10, 20, 300, 40]},
                     "https://example.com/report": {"ok": True, "path": "/x/rep.png", "site": "aaib.gov.in", "title": "Final report VT-TNC",
                                                    "date": "", "headline_box": None}}
            n = RN.prepare_pages(rows, Path(d) / "pages", shot=lambda url, cache: shots[url])
            self.assertEqual(n, 2)
            art = rows[0]["article"]
            self.assertEqual(art["page"], "/x/joon.png")
            self.assertEqual(art["outlet"], "Travel Weekly")              # the CSV's own words win over the page's tags
            self.assertEqual(rows[1]["article"]["outlet"], "aaib.gov.in")
            self.assertIsNone(rows[2]["article"])

    def test_failed_page_keeps_the_typeset_card(self):
        from aviation import runner as RN
        rows = [{"url": "https://example.com/paywall", "article": {"outlet": "X", "headline": "Y", "date": ""}}]
        RN.prepare_pages(rows, Path(tempfile.mkdtemp()), shot=lambda url, cache: {"ok": False, "reason": "HTTP 403"})
        self.assertNotIn("page", rows[0]["article"])

    def test_evidence_line_with_a_page_shows_the_page(self):
        from aviation import planner as P
        sc = [{"scene_no": 1, "text": "The investigation report found the crew used old weather.", "start": 0.0, "end": 5.0}]
        rows = [{"mode": "evidence", "article": {"outlet": "AAIB", "headline": "Final report", "date": "", "page": "/x/rep.png"},
                 "queries": [], "radio": [], "from": "", "to": "", "fuel": None, "time": "", "altitude": None}]
        p = P.plan(sc, rows=rows)
        self.assertEqual([s["layer"] for s in p.shots if s.get("layer")], ["cards.lay_article"])


LOGO_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta property="og:title" content="Emirates SkyCargo reports 52 percent revenue growth after challenging six months">
<style>body{margin:0;font-family:Arial} .top{height:700px;background:#c00} .top h1{margin:0;color:#fff;font-size:60px}
h2.entry-title{font-size:40px;margin:40px 60px} p{margin:20px 60px;height:1500px}</style></head>
<body><div class="top"><h1>ACW</h1><div>ADVERTISE HERE</div></div>
<h2 class="entry-title">Emirates SkyCargo reports 52 percent revenue growth after challenging six months</h2><p>text</p></body></html>"""


class HeadlinePickTests(unittest.TestCase):
    def test_the_real_headline_is_found_not_the_logo(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "acw.html").write_text(LOGO_PAGE, encoding="utf-8")
            r = WS.shot((Path(d) / "acw.html").as_uri(), Path(d) / "c")
            if not r.get("ok") and "playwright" in r.get("reason", "").lower():
                self.skipTest(r["reason"])
            self.assertTrue(r["ok"], r)
            self.assertTrue(r["title"].startswith("Emirates SkyCargo reports 52 percent"))
            self.assertTrue(0 <= r["headline_box"][1] < 400, r["headline_box"])     # the crop starts near the headline, below the banner
