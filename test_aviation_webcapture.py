"""Aviation web search + capture: queries, domain ranking, and a real headless browser on LOCAL pages (file://, no network)."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from aviation import router as R
from aviation import webcapture as WC

LOREM = "Operations continued across the network through the season with steady demand on most routes. " * 12
ARTICLE = """<!doctype html><html><head><meta charset="utf-8"><meta property="og:site_name" content="Example Aviation News">
<meta property="og:title" content="Air France launches Joon from Paris"><meta property="og:image" content="lead.png">
<meta property="article:published_time" content="2017-12-01T09:00:00Z"><title>Joon | Example</title>
<style>body{margin:0;font-family:Georgia}p{margin:20px 60px;font-size:20px;line-height:1.6}h1{margin:40px 60px}
#cookie{position:fixed;left:0;right:0;bottom:0;height:200px;background:rgb(255,0,200);z-index:9999}</style></head>
<body><h1>Air France launches Joon from Paris</h1><figure style="margin:0 60px"><img src="lead.png" width="800" height="400" alt="Joon A320">
<figcaption>A Joon Airbus A320 at Paris</figcaption></figure>
""" + "".join(f"<p>{LOREM}</p>" for _ in range(6)) + """
<p>Air France founded in 1933 now flies 70 Airbus A350 jets and carried 50 million passengers across 200 destinations.</p>
<p>Air France has launched Joon, its new airline for younger travellers, and the state owns a 14.3% stake in the group.</p>
""" + "".join(f"<p>{LOREM}</p>" for _ in range(4)) + """<div id="cookie">We use cookies <button>Accept all</button></div></body></html>"""

WIKI = """<!doctype html><html><head><meta charset="utf-8"><title>Vistara - Wiki</title></head><body>
<h1>Vistara</h1><table class="infobox"><caption>Vistara</caption><tr><th>Founded</th><td>2013</td></tr><tr><th>Hubs</th><td>Delhi</td></tr></table>
<p>""" + LOREM * 3 + """</p>
<table class="wikitable"><caption>Fleet</caption><tr><th>Aircraft</th><th>In service</th></tr><tr><td>Airbus A320neo</td><td>50</td></tr>
<tr><td>Boeing 787-9</td><td>3</td></tr></table>
<table class="wikitable"><tr><th>Year</th><th>Event</th></tr><tr><td>2015</td><td>Start</td></tr></table>
</body></html>"""

COOKIEWALL = """<!doctype html><html><body><div class="cookie-banner"><h2>We value your privacy</h2><p>We use cookies. Accept to continue.</p></div></body></html>"""
BLANK = "<!doctype html><html><body></body></html>"


def _cls(text):
    return R.classify(text)


class PureTests(unittest.TestCase):
    def test_queries_from_the_lines_names(self):
        c = _cls("Air France launched Joon in 2017 with the Airbus A320.")
        q = WC.queries(c, max_q=3)
        self.assertTrue(q and len(q) <= 3)
        self.assertTrue(any("Air France" in x for x in q), q)
        self.assertTrue(any("2017" in x for x in q), q)

    def test_csv_search_goes_first(self):
        q = WC.queries(_cls("Air France launched Joon."), csv_search="Joon Air France 2017 history")
        self.assertEqual(q[0], "Joon Air France 2017 history")

    def test_domain_ranking_and_csv_first(self):
        def fn(q, n):
            return [{"url": "https://random-blog.example/x", "title": "b"}, {"url": "https://www.reuters.com/a"},
                    {"url": "https://en.wikipedia.org/wiki/Air_France"}, "https://www.airfrance.com/history",
                    {"url": "https://simpleflying.com/x"}]
        r = WC.search(["q"], search_fn=fn, csv_urls=["https://csv.example/page"], airline_sites=["airfrance.com"])
        urls = [x["url"] for x in r]
        self.assertEqual(urls[0], "https://csv.example/page")
        self.assertEqual(urls[1], "https://www.airfrance.com/history")
        self.assertLess(urls.index("https://en.wikipedia.org/wiki/Air_France"), urls.index("https://www.reuters.com/a"))
        self.assertEqual(urls[-1], "https://random-blog.example/x")

    def test_search_dedupes_and_survives_errors(self):
        def fn(q, n):
            if q == "bad":
                raise RuntimeError("boom")
            return ["https://en.wikipedia.org/wiki/A", "https://en.wikipedia.org/wiki/A"]
        r = WC.search(["bad", "ok"], search_fn=fn)
        self.assertEqual(len(r), 1)

    def test_data_facts(self):
        text = ("Air France founded in 1933 now flies 70 Airbus A350 jets and carried 50 million passengers across 200 destinations. "
                "The state owns a 14.3% stake in the group.")
        d = WC.extract_data(text, "Example")
        kinds = {(f["kind"], f["value"]) for f in d}
        self.assertIn(("founded", 1933), kinds)
        self.assertIn(("fleet", 70), kinds)
        self.assertIn(("passengers", 50_000_000), kinds)
        self.assertIn(("destinations", 200), kinds)
        self.assertIn(("stake", 14.3), kinds)
        self.assertTrue(all(f["source"] == "Example" and f["text"] for f in d))

    def test_facts_agree_narration_wins(self):
        facts = [{"kind": "stake", "value": 14.3, "text": "", "source": "x"}, {"kind": "stake", "value": 9.0, "text": "", "source": "x"},
                 {"kind": "founded", "value": 1933, "text": "", "source": "x"}, {"kind": "founded", "value": 1945, "text": "", "source": "x"},
                 {"kind": "fleet", "value": 70, "type": "A350", "text": "", "source": "x"},
                 {"kind": "fleet", "value": 90, "type": "A350", "text": "", "source": "x"},
                 {"kind": "fleet", "value": 12, "type": "A220", "text": "", "source": "x"}]
        c = _cls("Air France, founded in 1933, flies 70 Airbus A350 jets and the state owns 14.3% of it.")
        got = WC.facts_agree(facts, c)
        vals = [(f["kind"], f["value"]) for f in got]
        self.assertIn(("stake", 14.3), vals); self.assertNotIn(("stake", 9.0), vals)
        self.assertIn(("founded", 1933), vals); self.assertNotIn(("founded", 1945), vals)
        self.assertIn(("fleet", 70), vals); self.assertNotIn(("fleet", 90), vals)
        self.assertIn(("fleet", 12), vals)                              # the narration says nothing about A220: kept

    def test_page_ok_rules(self):
        c = _cls("Air France launched Joon in 2017.")
        good = {"ok": True, "title": "Air France launches Joon", "site": "News", "text": "Air France said Joon will fly from Paris."}
        other = {"ok": True, "title": "Lufthansa strike", "site": "News", "text": "Lufthansa pilots walked out on Monday."}
        self.assertTrue(WC.page_ok(good, c)[0])
        ok, _, why = WC.page_ok(other, c)
        self.assertFalse(ok); self.assertIn("page", why)
        self.assertFalse(WC.page_ok({"ok": False, "reason": "paywall"}, c)[0])
        c2 = _cls("The Airbus A350 entered service in 2015.")
        self.assertFalse(WC.page_ok({"ok": True, "title": "Boeing 737 history", "site": "", "text": "The Boeing 737 is a jet."}, c2)[0])

    def test_photo_livery_check(self):
        c = _cls("Air France flew the Airbus A350.")
        red = Image.new("RGB", (200, 100), "#ED2939")
        grey = Image.new("RGB", (200, 100), (120, 120, 120))
        with tempfile.TemporaryDirectory() as t:
            red.save(Path(t) / "r.png"); grey.save(Path(t) / "g.png")
            self.assertTrue(WC.photo_ok({"path": str(Path(t) / "r.png")}, c)[0])
            self.assertFalse(WC.photo_ok({"path": str(Path(t) / "g.png")}, c)[0])
        self.assertTrue(WC.photo_ok({"path": "nope"}, _cls("A new runway opened."))[0])


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        for name, html in (("article.html", ARTICLE), ("wiki.html", WIKI), ("cookie.html", COOKIEWALL), ("blank.html", BLANK)):
            (cls.d / name).write_text(html, encoding="utf-8")
        Image.new("RGB", (800, 400), "#336699").save(cls.d / "lead.png")
        cls.cache = cls.d / "cache"
        cls.key = "Air France has launched Joon, its new airline for younger travellers"
        cls.art = WC.capture((cls.d / "article.html").as_uri(), cls.cache, key_sentence=cls.key)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _need(self, r=None):
        r = r or self.art
        low = (r.get("reason") or "").lower()
        if not r.get("ok") and ("playwright" in low or "node" in low or "no output" in low or "enoent" in low):
            self.skipTest(r["reason"])

    def test_article_capture(self):
        self._need()
        r = self.art
        self.assertTrue(r["ok"], r["reason"])
        self.assertEqual(r["site"], "Example Aviation News")
        self.assertEqual(r["title"], "Air France launches Joon from Paris")
        self.assertEqual(r["date"], "December 1, 2017")
        self.assertTrue(r["credit"])
        self.assertTrue(r["page"] and Path(r["page"]["path"]).is_file() and r["page"]["headline_box"])

    def test_scroll_video_is_3_to_5_seconds_with_the_highlight(self):
        self._need()
        s = self.art["scroll"]
        self.assertTrue(s and s["found"], s)
        p = Path(s["path"])
        self.assertTrue(p.is_file())
        pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate:format=duration",
                             "-of", "json", str(p)], capture_output=True, text=True)
        j = json.loads(pr.stdout)
        self.assertTrue(3.0 <= float(j["format"]["duration"]) <= 5.0, j)
        self.assertEqual((j["streams"][0]["width"], j["streams"][0]["height"]), (1280, 720))
        self.assertEqual(j["streams"][0]["r_frame_rate"], "30/1")
        png = self.d / "last.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.3", "-i", str(p), "-frames:v", "1", str(png)], check=True)
        im = Image.open(png).convert("RGB")
        yellow = sum(1 for px in im.getdata() if px[0] > 230 and px[1] > 210 and px[2] < 90)
        self.assertGreater(yellow, 400)

    def test_cookie_bar_hidden_and_elements(self):
        self._need()
        kinds = [e["kind"] for e in self.art["elements"]]
        self.assertIn("lead", kinds)
        lead = [e for e in self.art["elements"] if e["kind"] == "lead"][0]
        self.assertTrue(Path(lead["path"]).is_file())
        self.assertIn("A320", lead["caption"])
        self.assertTrue(lead["credit"])
        im = Image.open(self.art["page"]["path"]).convert("RGB")
        mag = sum(1 for px in im.getdata() if px[0] > 240 and px[1] < 20 and px[2] > 190)
        self.assertEqual(mag, 0)

    def test_data_from_the_page(self):
        self._need()
        kinds = {(f["kind"], f["value"]) for f in self.art["data"]}
        self.assertIn(("founded", 1933), kinds)
        self.assertIn(("fleet", 70), kinds)
        self.assertIn(("stake", 14.3), kinds)

    def test_page_ok_on_the_captured_article(self):
        self._need()
        self.assertTrue(WC.page_ok(self.art, _cls("Air France launched Joon in 2017."))[0])
        self.assertFalse(WC.page_ok(self.art, _cls("Qantas ordered the Airbus A350."))[0])

    def test_second_call_is_a_cache_hit(self):
        self._need()
        again = WC.capture((self.d / "article.html").as_uri(), self.cache, key_sentence=self.key)
        self.assertTrue(again["ok"] and again["cached"])
        self.assertEqual(again["scroll"]["path"], self.art["scroll"]["path"])
        self.assertTrue(again["page"]["cached"])

    def test_wikipedia_like_page_infobox_and_fleet_table(self):
        self._need()
        r = WC.capture((self.d / "wiki.html").as_uri(), self.cache, wants=("elements", "data"))
        self._need(r)
        self.assertTrue(r["ok"], r["reason"])
        kinds = [e["kind"] for e in r["elements"]]
        self.assertIn("infobox", kinds)
        self.assertEqual(kinds.count("table"), 1)                        # the Year/Event table is not a fleet table
        for e in r["elements"]:
            self.assertTrue(Path(e["path"]).is_file())
        self.assertIsNone(r["page"]); self.assertIsNone(r["scroll"])

    def test_cookie_wall_and_blank_are_refused(self):
        self._need()
        for name, word in (("cookie.html", "cookie"), ("blank.html", "blank")):
            r = WC.capture((self.d / name).as_uri(), self.cache)
            self.assertFalse(r["ok"], name)
            self.assertIn(word, r["reason"].lower())

    def test_capture_many_parallel(self):
        self._need()
        urls = [(self.d / n).as_uri() for n in ("article.html", "wiki.html", "blank.html")]
        r = WC.capture_many(urls, self.cache, wants=("elements", "data"), workers=3, total_timeout_s=90)
        self.assertEqual(set(r), set(urls))
        self.assertTrue(r[urls[0]]["ok"] and r[urls[1]]["ok"] and not r[urls[2]]["ok"])

    def test_not_a_web_address(self):
        self.assertFalse(WC.capture("ftp://x/y", self.cache)["ok"])


if __name__ == "__main__":
    unittest.main()
