"""Food Files: CSV, director rhythm, checker, maps, icons, and one frame of every shot kind (no network, no Flow)."""
import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from PIL import Image

from foodfiles import cards, check, csvplan, director, icons, maps
from foodfiles import render as ff_render
from prepper_host import render as ph_render

CSV = """line,shot,item,title,name,year,place,visual,stamp,note,rows,source
"From a gobstopper that exploded to a candy that stops your heart.",,,,,,,,,,,
"These are the deadliest candies ever sold.",title,,THE DEADLIEST | CANDY | EVER SOLD,,,,,,,,
"This is the everlasting gobstopper.",,1,A REAL-LIFE CANDY,EVERLASTING GOBSTOPPER,2003,,,,,,
"In two thousand three a girl in Starke, Florida bit into one.",,,,,2003,"Starke, Florida",,,,9-YEAR-OLD GIRL,
"Her family sued, and it settled out of court.",,,THE LAWSUIT,,,,,SETTLED,,"FILED BY = THE FAMILY; AGAINST = THE MAKER; OUTCOME = SETTLED",
"It was refrigerated, left in the sun, then put back in the fridge.",,,ACCORDING TO REPORTS,,,,,,,"fridge = REFRIGERATED; sun = LEFT IN THE SUN; fridge = BACK IN THE FRIDGE",
"Seventy million of them were recalled.",,,,,,,,,,"70,000,000 = RECALLED",
"So yeah, it can blow up in your face, and that is the part nobody ever wants to hear about at all, ever, really.",,,,,,,,,...KINDA,,
"But this next one took its time.",,,A SPLIT SECOND...,,,,,,,,
"This is black licorice.",number,2,THE CLASSIC,BLACK LICORICE,2020,,,,,,
"",thumbnail,,DEADLIEST | CANDY,,,,"{host} holding a jawbreaker",,,,
"""


def fake_words(rows, wps=2.6):
    words, t = [], 0.0
    for r in rows:
        for w in r["line"].split():
            words.append({"word": w, "start": round(t, 3), "end": round(t + 0.3, 3)})
            t += 1 / wps
        t += 0.15
    return words, t + 0.3


class TestCsv(unittest.TestCase):
    def test_read_aliases_and_thumbnail(self):
        rows, problems = csvplan.read("Narration,Type,Rank\nHello there.,countdown,1\n,thumbnail,\n")
        self.assertEqual(rows[0]["line"], "Hello there.")
        self.assertEqual(rows[0]["shot"], "number")
        self.assertEqual(rows[0]["item"], "1")
        self.assertEqual(rows[1]["shot"], "thumbnail")
        self.assertEqual(problems, [])

    def test_unknown_shot_reported(self):
        rows, problems = csvplan.read("line,shot\nHi.,sparkles\n")
        self.assertEqual(rows[0]["shot"], "")
        self.assertTrue(problems)

    def test_rows_and_highlights(self):
        it = csvplan.parse_rows("turkey = FROZEN SOLID; +bowling = BOWLING BALL !red")
        self.assertEqual(it[0]["label"], "turkey")
        self.assertTrue(it[1]["join"])
        self.assertEqual(it[1]["colour"], "red")
        text, spans = csvplan.highlights("A worker *died from* licorice")
        self.assertEqual(text, "A worker died from licorice")
        self.assertEqual(text[spans[0][0]:spans[0][1]], "died from")
        self.assertEqual(csvplan.name_bar("BILLY | sweet seller"), ("BILLY", "sweet seller"))


class TestDirector(unittest.TestCase):
    def setUp(self):
        rows, _ = csvplan.read(CSV)
        self.rows = [r for r in rows if r["shot"] != "thumbnail"]
        words, dur = fake_words(self.rows)
        self.spec = director.direct(self.rows, words, dur, size=(1280, 720), host_meta={"name": "Theo"})

    def first_kind(self, row):
        return next(s["kind"] for s in self.spec["shots"] if s["row"] == row)

    def test_auto_picks(self):
        self.assertEqual(self.first_kind(0), "host")
        self.assertEqual(self.first_kind(1), "title")
        self.assertEqual(self.first_kind(2), "number")
        self.assertEqual(self.first_kind(3), "map")
        self.assertEqual(self.first_kind(4), "folder")
        self.assertEqual(self.first_kind(5), "explain")
        self.assertEqual(self.first_kind(6), "big")
        self.assertEqual(self.first_kind(8), "next")

    def test_cards_and_overlays(self):
        folder = next(s for s in self.spec["shots"] if s["kind"] == "folder")
        self.assertEqual(len(folder["card"]["items"]), 3)
        self.assertEqual(folder["stamp"]["text"], "SETTLED")
        ats = [it["at"] for it in folder["card"]["items"]]
        self.assertEqual(ats, sorted(ats))
        self.assertTrue(all(folder["t0"] <= a < folder["t1"] for a in ats))
        m = next(s for s in self.spec["shots"] if s["kind"] == "map")
        self.assertEqual(m["card"]["header"], "2003 · Starke, Florida")
        host = [s for s in self.spec["shots"] if s["kind"] == "host"]
        self.assertTrue(any(s.get("note") for s in host))
        self.assertTrue(any(s.get("punch") for s in host), "a long host line is cut into host + punch-in")

    def test_captions_short_with_key(self):
        for s in self.spec["shots"]:
            for c in s.get("caps", []):
                self.assertLessEqual(len(c["text"].split()), 5)
                self.assertGreaterEqual(c["t1"], c["t0"])

    def test_shots_cover_the_voice(self):
        sh = self.spec["shots"]
        self.assertEqual(sh[0]["t0"], 0.0)
        for a, b in zip(sh, sh[1:]):
            self.assertAlmostEqual(a["t1"], b["t0"], places=2)

    def test_unknown_icon_asks_flow_once(self):
        rows, _ = csvplan.read('line,shot,rows\n"Spaceship then fridge.",explain,"spaceship = UP; fridge = COLD"\n')
        words, dur = fake_words(rows)
        spec = director.direct(rows, words, dur, size=(1280, 720))
        stickers = [p for p in spec["pictures"].values() if p.get("sticker")]
        self.assertEqual(len(stickers), 1)

    def test_checker(self):
        rep = check.check(self.spec)
        self.assertIn("stats", rep)
        self.assertEqual(rep["stats"]["items"], 2)
        bare = {"shots": [{"t0": 0, "t1": 40, "kind": "host", "row": 0}], "rows": [{"line": "hi"}], "duration": 40}
        self.assertTrue(any("title card" in p for p in check.check(bare)["problems"]))


class TestMapsIcons(unittest.TestCase):
    def test_resolve(self):
        self.assertEqual(maps.resolve("Starke, Florida")["region"]["n"], "Florida")
        self.assertEqual(maps.resolve("Bradford, England")["region"]["n"], "United Kingdom")
        self.assertIsNone(maps.resolve("Nowhere Land"))
        base, fill, pin, label = maps.layers("Japan", (640, 360))
        self.assertEqual(base.size, (640, 360))
        self.assertIsNotNone(pin)

    def test_icons(self):
        self.assertEqual(icons.key_of("9-year-old girl"), "kid")
        self.assertEqual(icons.key_of("Refrigerator"), "fridge")
        self.assertIsNone(icons.key_of("spaceship"))
        for name in icons.ICONS:
            self.assertEqual(icons.icon(name, 64).size, (64, 64))


class TestDraw(unittest.TestCase):
    def test_every_kind_draws(self):
        with tempfile.TemporaryDirectory() as td:
            pic = os.path.join(td, "p.png")
            Image.new("RGB", (800, 600), (120, 90, 60)).save(pic)
            rows, _ = csvplan.read(CSV + '"A post.",tweet,,@someone,Some One,OCT 2017,,,,,"this is *teaching kids*",\n'
                                   '"A headline.",headline,,NEWS · SEP 2020,,,,"a photo",,,"A *worker* died",\n'
                                   '"A quote.",quote,,THE COMPANY,,,,,,,"we did *not* do it",\n'
                                   '"A photo.",photo,,,,,,"a candy",,,A REAL CANDY,\n'
                                   '"Dates.",timeline,,,,,,,,,"2003 = A; 2004 = B",\n'
                                   '"Boxes.",flow,,,,,,,,,"A = 1; B; C = 3",\n'
                                   '"Here I am beside the factory that made all of them.",split,,,,,,"a scene",,,,\n'
                                   '"And here is the factory floor where it all went wrong.",pip,,,,,,"a scene",,,,\n')
            rows = [r for r in rows if r["shot"] != "thumbnail"]
            words, dur = fake_words(rows)
            spec = director.direct(rows, words, dur, size=(640, 360))
            spec["assets"] = {"pictures": {k: pic for k in spec["pictures"]}, "fallback": pic}
            dr = cards.FoodDrawer(spec, spec["assets"])
            seen = set()
            for i, s in enumerate(spec["shots"]):
                for f in (0.05, 0.6, 0.98):
                    im = dr.frame(dict(s, i=i), s["t0"] + (s["t1"] - s["t0"]) * f)
                    self.assertEqual(im.size, (640, 360))
                seen.add(s["kind"])
            dr.close()
            for k in ("host", "title", "number", "map", "folder", "explain", "big", "next", "tweet", "headline", "quote",
                      "photo", "timeline", "flow", "split", "pip"):
                self.assertIn(k, seen)
            out = os.path.join(td, "t.jpg")
            ff_render.thumbnail(pic, ["DEADLIEST", "CANDY"], out)
            self.assertTrue(os.path.getsize(out) > 0)

    def test_mix_lends_cues_and_restores(self):
        before = dict(ph_render.SFX)
        with tempfile.TemporaryDirectory() as td:
            wav = os.path.join(td, "v.wav")
            import wave
            with wave.open(wav, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(48000)
                w.writeframes(b"\x00\x01" * 48000)
            spec = {"voice_path": wav, "duration": 1.0, "sfx": [{"t": 0.1, "name": "stamp"}]}
            ff_render.mix(spec, os.path.join(td, "m.wav"), sound="fx")
        self.assertEqual(ph_render.SFX, before)


class TestAppWiring(unittest.TestCase):
    def test_app_hooks(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parent / "app.py").read_text(encoding="utf-8")
        for hook in ("from ui import foodfiles_section as _ff_section", "_ff_section.activate(self)", "_ff_section.cta(self, action)",
                     "_ff_section.sync_cta(self)", "_ff_section.resume_on_open(self)", "_ff_section.deactivate(self, remember=False)",
                     'return "Food Files"', '("ff_generate", "ff_render", "ff_cancel")'):
            self.assertIn(hook, src)

    def test_style_card_and_labels(self):
        from ui import style_registry as R, visual_director as VD
        import export_state
        self.assertIn("Food Files", R.STANDALONE)
        self.assertEqual(R.group_of("Food Files"), "Explainers")
        self.assertIn("Food Files", R.EXTRA_CARDS)
        self.assertIn("Food Files", R.EXTRA_BLURBS)
        self.assertEqual(export_state.STYLE_LABELS["foodfiles"], "Food Files")
        self.assertTrue(any("Food Files" in fam[3] for fam in VD.FAMILIES))

    def test_page_module_loads(self):
        from ui import foodfiles_section as S
        self.assertEqual(S.STYLE, "Food Files")
        self.assertEqual(next(iter(S.TALKING.values())), "budget")    # fewest Flow clips, front-loaded, is the default
        self.assertEqual(next(iter(S.HOSTS.values())), "theo")
        self.assertEqual(next(iter(S.SOUND.values())), "music")

    def test_autorun_job(self):
        from pathlib import Path
        from autorun import job as J
        import make_video as MV
        self.assertEqual(J.STYLES["food-files"]["fields"]["csv"], "_ff_csv_var")
        self.assertEqual(MV.STYLES["food-files"][2], "foodfiles/csv_prompt.txt")
        sample = Path(__file__).resolve().parent / "foodfiles" / "samples" / "sweets_two_items.csv"
        j = J.make_job("food-files", csv=str(sample))
        self.assertEqual(j["voice"], "")
        with self.assertRaises(J.JobError):
            J.make_job("food-files")


class TestRealImagery(unittest.TestCase):
    """Phase 1: Commons photos (licence + words checked), page screenshots, clips, credits; all without the network."""

    def fake_commons(self, params):
        self.assertEqual(params.get("generator"), "search")          # one request per photo
        def page(t, lic, mime="image/jpeg", w=2000, index=1):
            return {"title": t, "index": index, "imageinfo": [{"thumburl": "https://x/" + t, "width": w, "height": 1400, "mime": mime,
                                                "descriptionurl": "https://c/" + t,
                                                "extmetadata": {"LicenseShortName": {"value": lic}, "Artist": {"value": "<a>Jane Doe</a>"},
                                                                "ImageDescription": {"value": "striped mint sweets"}}}]}
        return {"query": {"pages": {"1": page("File:Logo of candy.svg", "CC0", "image/svg+xml", index=1),
                                    "2": page("File:Nc only humbugs.jpg", "CC BY-NC 2.0", index=2),
                                    "3": page("File:Peppermint humbugs on a plate.jpg", "CC BY-SA 4.0", index=3)}}}

    def test_commons_pick_licence_words_and_credit(self):
        from foodfiles import sources
        c = sources.pick_commons("peppermint humbugs", sources.commons_candidates("peppermint humbugs", get_json=self.fake_commons))
        self.assertEqual(c["title"], "File:Peppermint humbugs on a plate.jpg")     # svg logo and NC licence skipped
        self.assertEqual(sources.credit_of(c), "Photo: Jane Doe / Wikimedia Commons / CC BY-SA 4.0")
        self.assertIsNone(sources.pick_commons("black licorice", sources.commons_candidates("x", get_json=self.fake_commons)))

    def test_commons_stores_once_with_credit(self):
        from foodfiles import sources
        from prepper_host import flow
        import io
        buf = io.BytesIO()
        Image.new("RGB", (40, 30), (200, 10, 10)).save(buf, "JPEG")
        with tempfile.TemporaryDirectory() as td, unittest.mock.patch.object(flow, "LIB", Path(td)):
            r = sources.commons("k1", "peppermint humbugs", get_json=self.fake_commons, get_bytes=lambda url: buf.getvalue())
            self.assertTrue(os.path.isfile(r["path"]))
            self.assertEqual(Image.open(r["path"]).format, "PNG")
            again = sources.commons("k1", "peppermint humbugs", get_json=lambda p: 1 / 0, get_bytes=lambda u: 1 / 0)
            self.assertEqual(again["credit"], r["credit"])                         # from the library, no network

    def test_clip_window(self):
        from foodfiles import sources

        class Seg:
            def __init__(self, start, text):
                self.start, self.duration, self.text = start, 3.0, text
        segs = [Seg(0, "welcome back"), Seg(20, "they microwaved the jawbreaker"), Seg(23, "and it burst in the jaw"),
                Seg(60, "thanks for watching")]
        self.assertEqual(sources.best_window(segs, "microwaved jawbreaker burst", 7), 20.0)
        self.assertIsNone(sources.best_window(segs, "licorice potassium heart", 7))

    def test_director_real_keys(self):
        rows, _ = csvplan.read('''line,shot,item,name,find,url,title,rows
"This is the gobstopper.",number,1,EVERLASTING GOBSTOPPER,Everlasting Gobstopper,,,
"Here it is up close.",photo,,,,,,A REAL CANDY
"The recall notice said it all.",,,,,https://www.fda.gov/recall,FDA · 2023,"*Recall* of candy"
"They tested it on TV and it burst.",clip,,,MythBusters jawbreaker,,DISCOVERY · 2004,
''')
        words, dur = fake_words(rows)
        spec = director.direct(rows, words, dur, size=(640, 360))
        shots = {s["row"]: s for s in spec["shots"]}
        num, photo, page, clip = shots[0], shots[1], shots[2], shots[3]
        self.assertEqual(spec["pictures"][num["card"]["pic"]]["find"], "Everlasting Gobstopper")
        self.assertTrue(spec["pictures"][num["card"]["pic"]]["optional"])
        self.assertEqual(spec["pictures"][photo["pic"]]["find"], "Everlasting Gobstopper")   # empty find = the item's name
        self.assertEqual(page["kind"], "page")
        self.assertEqual(spec["pictures"][page["page"]]["page"], "https://www.fda.gov/recall")
        self.assertEqual(spec["pictures"][clip["clip"]]["clip"], "MythBusters jawbreaker")
        self.assertEqual(clip["card"]["strap"], "DISCOVERY · 2004")

    def test_real_cards_draw_and_credit(self):
        from foodfiles import runner, sources
        from prepper_host import flow
        with tempfile.TemporaryDirectory() as td, unittest.mock.patch.object(flow, "LIB", Path(td)):
            rows, _ = csvplan.read('''line,shot,item,name,find,url,title
"This is the gobstopper candy.",number,1,GOBSTOPPER,Gobstopper,,
"The recall notice said it all.",page,,,,https://www.fda.gov/recall,FDA
"They tested it on TV and it burst.",clip,,,jawbreaker test,,TV · 2004
''')
            words, dur = fake_words(rows)
            spec = director.direct(rows, words, dur, size=(640, 360))
            num = spec["shots"][0]
            pk = num["card"]["pic"]
            Image.new("RGB", (900, 700), (230, 40, 40)).save(flow.lib_path(pk))
            sources.meta_path(pk).write_text('{"credit": "Photo: A / Wikimedia Commons / CC0"}')
            page = next(s for s in spec["shots"] if s["kind"] == "page")
            Image.new("RGB", (1280, 2400), (250, 250, 250)).save(flow.lib_path(page["page"]))
            sources.meta_path(page["page"]).write_text('{"site": "fda.gov", "headline_box": [40, 300, 700, 60], "credit": "Source: fda.gov"}')
            runner.credits(spec)
            self.assertEqual(num["source"], "Photo: A / Wikimedia Commons / CC0")
            self.assertEqual(page["source"], "Source: fda.gov")
            spec["assets"] = {"pictures": {k: flow.have(k) for k in spec["pictures"] if flow.have(k)}, "clips": {}, "fallback": None}
            dr = cards.FoodDrawer(spec, spec["assets"])
            for i, s in enumerate(spec["shots"]):
                for f in (0.1, 0.9):
                    self.assertEqual(dr.frame(dict(s, i=i), s["t0"] + (s["t1"] - s["t0"]) * f).size, (640, 360))
            dr.close()


class TestNoDeadAir(unittest.TestCase):
    """Owner, 2026-11-22: no pause 'like he completed the sentence' - long pauses cut, lips kept in sync by jump cuts."""

    def test_squeeze_cuts_long_pauses_only(self):
        import numpy as np
        from prepper_host import flowvoice as fv
        sr = fv.SR
        tone = lambda sec: (0.3 * np.sin(np.arange(int(sr * sec)) * 0.2)).astype(np.float32)
        quiet = lambda sec: np.zeros(int(sr * sec), dtype=np.float32)
        y = np.concatenate([tone(1.0), quiet(0.6), tone(1.0), quiet(0.15), tone(0.5)])
        out, cuts = fv.squeeze(y)
        self.assertEqual(len(cuts), 1)                       # the 0.6 s pause, not the 0.15 s one
        self.assertAlmostEqual(cuts[0][1], 0.6 - 0.14, delta=0.05)
        self.assertAlmostEqual(len(out) / sr, len(y) / sr - cuts[0][1], delta=0.03)

    def test_jump_cut_keeps_lips_in_sync(self):
        from foodfiles import runner
        spec = {"shots": [{"t0": 0.0, "t1": 6.0, "kind": "host", "row": 0, "talk": "c.mp4", "talk_at": 0.4,
                           "caps": [{"t0": 0.5, "t1": 2.0, "text": "a"}, {"t0": 3.5, "t1": 5.0, "text": "b"}]},
                          {"t0": 6.0, "t1": 9.0, "kind": "title", "row": 1}]}
        said = {0: ("c.mp4", 0.4, 0.0)}
        n = runner.jump_cuts(spec, said, {0: [(3.0, 0.45)]})
        self.assertEqual(n, 1)
        a, b = spec["shots"][0], spec["shots"][1]
        self.assertEqual((a["t1"], b["t0"]), (3.0, 3.0))
        self.assertAlmostEqual(b["talk_at"], 0.4 + 3.0 + 0.45)  # the clip jumps over the pause it no longer speaks
        self.assertNotEqual(bool(a.get("punch")), bool(b.get("punch")))
        self.assertEqual([c["text"] for c in b["caps"]], ["b"])
        # a cut right at a shot's start moves the edge instead of leaving a sliver
        spec2 = {"shots": [{"t0": 0.0, "t1": 2.0, "kind": "photo", "row": 0},
                           {"t0": 2.0, "t1": 6.0, "kind": "host", "row": 1, "talk": "c.mp4", "talk_at": 0.0, "caps": []}]}
        runner.jump_cuts(spec2, {1: ("c.mp4", 0.0, 2.0)}, {1: [(2.3, 0.4)]})
        self.assertEqual(len(spec2["shots"]), 2)
        self.assertEqual(spec2["shots"][1]["t0"], 2.3)


class TestCardFill(unittest.TestCase):
    """Phase 2: cards fill the frame (no small boxes on big empty backgrounds); a number card stays <= 3 s."""

    def test_cards_fill_the_frame(self):
        rows, _ = csvplan.read('''line,shot,title,rows,place,year
"Sugar was expensive, so they bulked it up with a cheap white powder.",flow,CUTTING CORNERS,"SUGAR = EXPENSIVE; BULK IT UP; DAFF = CHEAP FILLER",,
"The chemist reached into the wrong barrel and handed over arsenic.",explain,THE SHOP,"barrel = DAFF; +skull = ARSENIC",,
"Around twenty people died and two hundred fell seriously ill.",big,,"~20 = DEAD; 200+ = SERIOUSLY ILL",,
"Ten years later the law changed and poisons had to be labelled.",timeline,WHAT CHANGED,"1858 = POISONING; 1868 = PHARMACY ACT; TODAY = LABELS",,
"In the town of Bradford, one sweet seller had a problem.",map,,A MARKET TOWN,"Bradford, England",1858
''')
        words, dur = fake_words(rows)
        spec = director.direct(rows, words, dur, size=(960, 540))
        spec["subscribe"] = False
        spec["assets"] = {"pictures": {}, "clips": {}, "fallback": None}
        dr = cards.FoodDrawer(spec, spec["assets"])
        for i, s in enumerate(spec["shots"]):
            if s["kind"] in ("host",):
                continue
            fr = dr.frame(dict(s, i=i), s["t0"] + (s["t1"] - s["t0"]) * 0.97)
            share = cards.fill_share(fr, cards.background((960, 540), s.get("tone") or "dark"))
            self.assertGreaterEqual(share, 0.40, f"{s['kind']} fills only {share:.0%} of the frame")
        dr.close()

    def test_number_card_is_short(self):
        rows, _ = csvplan.read('''line,item,name
"This is the everlasting gobstopper, the candy that was made to last forever and somehow never really did.",1,GOBSTOPPER
''')
        words, dur = fake_words(rows)
        spec = director.direct(rows, words, dur, size=(640, 360))
        num = next(s for s in spec["shots"] if s["kind"] == "number")
        self.assertLessEqual(num["t1"] - num["t0"], 3.01)
        # the rest of the line shows what it says (a Flow picture), not a still of the host (owner, 2026-11-23)
        self.assertTrue(any(s["kind"] == "scene" and s.get("pic") for s in spec["shots"]))

    def test_next_card_gets_next_food_icon(self):
        rows, _ = csvplan.read('''line,shot,item,name,find,title
"One.",host,,,,
"Two.",host,,,,
"Three.",host,,,,
"But this next one took its time.",next,,,,A SLOW ONE
"This is black licorice.",number,2,BLACK LICORICE,black licorice,
''')
        words, dur = fake_words(rows)
        spec = director.direct(rows, words, dur, size=(640, 360))
        nxt = next(s for s in spec["shots"] if s["kind"] == "next")
        self.assertEqual(nxt["card"]["icon"], "candy")


class TestPhase3Cards(unittest.TestCase):
    """Phase 3: the reference's other card types, our own drawing; each builds, fills the frame and draws without assets."""
    CSV = '''line,shot,title,name,place,rows
"Franchise owners were paying for everything, while corporate kept collecting the money.",compare,WHO PAID,,,"FRANCHISE OWNERS = man; CORPORATE = money"
"Inside the home, police found two things that should never be near a candy bowl.",evidence,FOUND INSIDE THE HOME,,,"METH = pill; MARIJUANA = germ"
"The kids were dealing with shortness of breath, nausea and a racing heart.",symptoms,WHAT KIDS WERE DEALING WITH,kid,,"SHORTNESS OF BREATH; NAUSEA; RACING HEART"
"Then the states piled on, starting with Illinois, then Connecticut, then Texas.",states,THE STATES PILED ON,,"Illinois; Connecticut; Texas","A; B; C"
"Even the company's own website admitted how much caffeine was in one bottle.",browser,company site,FAQ,,"Each bottle has *200 mg of caffeine*."
"And the box itself got a lot heavier over the years, even though the price went up too.",scale,,box,,A LOT HEAVIER
"This is what the store shelf looked like before, and this is what it looked like after the recall.",beforeafter,,,,"BEFORE; AFTER"
"Four kids ended up in the hospital in a single afternoon, all from the same school lunch.",tally,,,,"kid x 4 = KIDS HOSPITALIZED"
"But it still wasn't enough to save the company, and the worst part was still coming.",host,BUT IT STILL WASN'T ENOUGH,,,
'''

    def plan(self):
        rows, problems = csvplan.read(self.CSV)
        self.assertEqual(problems, [])
        words, dur = fake_words(rows)
        spec = director.direct(rows, words, dur, size=(960, 540))
        spec["subscribe"] = False
        return spec

    def test_kinds_and_cards(self):
        spec = self.plan()
        first = {}
        for s in spec["shots"]:
            first.setdefault(s["row"], s)
        kinds = [first[k]["kind"] for k in sorted(first)]
        self.assertEqual(kinds, ["compare", "evidence", "symptoms", "states", "browser", "scale", "beforeafter", "tally", "host"])
        self.assertEqual([it["icon"] for it in first[0]["card"]["items"]], ["man", "money"])
        self.assertEqual(len(first[3]["card"]["places"]), 3)
        self.assertEqual((first[7]["card"]["icon"], first[7]["card"]["count"]), ("kid", 4))
        self.assertEqual(first[8]["banner"]["text"], "BUT IT STILL WASN'T ENOUGH")

    def test_draw_and_fill(self):
        with tempfile.TemporaryDirectory() as td:
            host = os.path.join(td, "set.png")
            Image.new("RGB", (800, 450), (90, 70, 50)).save(host)
            spec = self.plan()
            spec["host"] = {"set_image": host}
            spec["assets"] = {"pictures": {}, "clips": {}, "fallback": host}
            dr = cards.FoodDrawer(spec, spec["assets"])
            for i, s in enumerate(spec["shots"]):
                fr = dr.frame(dict(s, i=i), s["t0"] + (s["t1"] - s["t0"]) * 0.95)
                if s["kind"] != "host" and s["kind"] != "compare":
                    share = cards.fill_share(fr, cards.background((960, 540), s.get("tone") or "dark"))
                    self.assertGreaterEqual(share, 0.40, f"{s['kind']} fills only {share:.0%}")
            dr.close()


class TestFlatScenes(unittest.TestCase):
    """Phase 4: flat cartoon mini scenes - places made once by Flow, code-drawn people acting it out."""

    def test_parse(self):
        from foodfiles import scene2d as S2
        sc = S2.parse("man: carry turkey; kid: sick; say = HEAVY!; list = A | B; monitor; count; label = 2 HURT")
        self.assertEqual([(a["who"], a["action"], a["prop"]) for a in sc["actors"]], [("man", "carry", "turkey"), ("kid", "sick", None)])
        self.assertEqual((sc["say"], sc["list"], sc["monitor"], sc["count"], sc["label"]), ("HEAVY!", ["A", "B"], True, True, "2 HURT"))
        self.assertEqual(S2.norm_place("School Classroom"), "classroom")
        self.assertEqual(S2.parse("alien: dance")["actors"][0]["who"], "man")   # unknown names fall back, never fail

    def test_every_pose_draws(self):
        from foodfiles import scene2d as S2
        for who in S2.WHO:
            for act in S2.ACTIONS:
                im = S2.person(who, act, 0.5, 160, prop="apple")
                self.assertGreater(im.getbbox()[3] - im.getbbox()[1], 40, (who, act))

    def test_scene_shot_and_place_picture(self):
        from foodfiles import scene2d as S2
        rows, problems = csvplan.read('''line,shot,place,rows
"Four kids got sick at the school feast that same afternoon, one after another.",cartoon,classroom,"kid: sick; kid: sick; count; label = 2 KIDS"
''')
        self.assertEqual(problems, [])
        words, dur = fake_words(rows)
        spec = director.direct(rows, words, dur, size=(640, 360))
        s = spec["shots"][0]
        self.assertEqual(s["kind"], "scene2d")
        self.assertEqual(s["card"]["pic"], S2.place_key("classroom"))
        self.assertIn("classroom", spec["pictures"][s["card"]["pic"]]["prompt"])
        self.assertIn("no people", spec["pictures"][s["card"]["pic"]]["prompt"])   # Flow paints the empty place only
        spec["subscribe"] = False
        spec["assets"] = {"pictures": {}, "clips": {}, "fallback": None}
        dr = cards.FoodDrawer(spec, spec["assets"])
        fr = dr.frame(dict(s, i=0), s["t0"] + (s["t1"] - s["t0"]) * 0.8)    # no Flow picture yet: the drawn stand-in
        self.assertEqual(fr.size, (640, 360))
        dr.close()


class TestScriptCheck(unittest.TestCase):
    """docs/food_files/SCRIPT_STUDY.md: scripts are measured against the top videos' format before they become a CSV."""

    def item(self, n, bridge=True):
        body = (f"This is candy number {n}, a sweet that every kid knew. And it looked harmless, right? Well, in 2003 a "
                f"9-year-old girl in Starke, Florida bit into one and it burst. So what happened? The outer layers stay hard "
                f"while the middle turns to molten sugar, and to put that in perspective it was hotter than boiling water. "
                f"But here's the part nobody expected: it happened again a year later to two more kids. And in the end the "
                f"family sued, the company settled, and 70 million were recalled. So, yeah, that one hurt. ")
        body = body * 3
        return body + ("But while that one burst in a second, this next one took its time." if bridge else "")

    def good(self):
        open_ = ("From a gobstopper that burned a girl's face to a gummy that got toddlers high, these are the deadliest "
                 "candies ever sold. But first, we're starting with the gobstopper.")
        items = [self.item(i, bridge=i < 9) for i in range(1, 10)]
        items[4] = items[4].replace("this next one took its time.", "this next one took its time. But if you think that is as "
                                    "bad as it gets, we still got two more.")
        outro = ("So the next time you open a candy bag, check the label. And the next time you grab a snack, be careful there "
                 "too, because these are the deadliest snacks ever sold. So click this video right here, and I'll catch you "
                 "in the next one.")
        return "\n\n".join([open_] + items + [outro])

    def test_a_script_in_the_format_passes(self):
        from foodfiles import scriptcheck as SC
        r = SC.check(self.good())
        self.assertEqual(r["problems"], [], r["problems"])
        self.assertEqual(r["stats"]["items"], 9)

    def test_missing_pieces_are_named(self):
        from foodfiles import scriptcheck as SC
        bad = self.good().replace("From a gobstopper", "Hi everyone, today a gobstopper").replace("click this video right here", "bye")
        bad = bad.replace("in 2003 a 9-year-old girl in Starke, Florida", "once somebody somewhere")
        probs = " | ".join(SC.check(bad)["problems"])
        self.assertIn("cold open", probs)
        self.assertIn("outro", probs)

    def test_our_old_sample_is_too_short(self):
        from foodfiles import scriptcheck as SC
        rows, _ = csvplan.read(str(Path(__file__).resolve().parent / "foodfiles" / "samples" / "sweets_two_items.csv"))
        r = SC.check(" ".join(x["line"] for x in rows if x["line"]))
        self.assertFalse(r["ok"])


class TestHostStills(unittest.TestCase):
    """Free test mode (owner, 2026-11-22): Flow pictures of the host instead of video clips while testing."""

    def test_poses_cycle_without_repeats(self):
        from foodfiles import runner, host
        spec = {"shots": [{"kind": k} for k in ("host", "host", "big", "host", "split", "host")]}
        runner.assign_stills(spec, ["p1", "p2", "p3"])
        got = [s.get("still") for s in spec["shots"]]
        self.assertIsNone(got[2])
        seq = [g for g in got if g]
        self.assertTrue(all(a != b for a, b in zip(seq, seq[1:])))
        jobs = host.pose_jobs(host.THEO)
        self.assertEqual(len(jobs), 8)
        self.assertTrue(all("reference pictures" in p for p in jobs.values()))


class TestCommonsBreaker(unittest.TestCase):
    def test_two_refusals_stop_the_requests(self):
        from foodfiles import sources
        sources.BREAKER.update(refused=0, open_until=0.0)
        for _ in range(2):
            sources._refused(RuntimeError("429 Client Error: Too Many Requests"))
        self.assertTrue(sources.breaker_open())
        self.assertIsNone(sources.commons("kx", "anything"))      # no request while it is open
        sources.BREAKER.update(refused=0, open_until=0.0)


class TestCommonsMisses(unittest.TestCase):
    def test_a_miss_is_not_asked_again_for_a_week(self):
        from foodfiles import sources
        from prepper_host import flow
        with tempfile.TemporaryDirectory() as td, unittest.mock.patch.object(flow, "LIB", Path(td)):
            self.assertFalse(sources.missed_lately("Peppermint  Humbugs"))
            sources.remember_miss("peppermint humbugs")
            self.assertTrue(sources.missed_lately("Peppermint  Humbugs"))
            sources.BREAKER.update(refused=0, open_until=0.0)
            with unittest.mock.patch.object(sources, "_get_json", side_effect=AssertionError("asked again")):
                self.assertIsNone(sources.commons("k2", "peppermint humbugs"))
        self.assertNotIn("github", sources.UA.lower())      # owner: no repo link in requests


class TestFrontLoadedClips(unittest.TestCase):
    """Owner, 2026-11-22: fewest Flow videos - more at the start, less at the end; poses fit the line's mood."""

    def test_budget_goes_to_the_opening(self):
        from foodfiles import runner
        rows = [{"n": i + 1, "line": f"Line number {i} is a short host line here.", "shot": "host", "visual": ""} for i in range(40)]
        rows2 = [dict(r, say=True) for r in rows]
        spec = {"duration": 600.0, "shots": [{"row": i, "t0": i * 15.0, "kind": "host"} for i in range(40)]}
        out = runner.front_load(rows2, rows, spec, budget=10, log=lambda m: None)
        said = [r["n"] for r in out if r.get("say")]
        self.assertEqual(len(said), 10)
        early = sum(1 for n in said if (n - 1) * 15.0 < 150)
        late = sum(1 for n in said if (n - 1) * 15.0 > 360)
        self.assertGreaterEqual(early, 6)
        self.assertLessEqual(late, 1)
        self.assertTrue(any(r["shot"] == "scene" for r in out if (r["n"] - 1) * 15.0 > 360))   # late lines become pictures

    def test_no_laughing_on_grave_lines(self):
        from foodfiles import runner
        poses = [f"ff_host_theo_pose_{i}" for i in range(1, 9)]
        for line in ("And by the end, more than a hundred people were dead.", "He died the next day.",
                     "Fourteen kids developed kidney failure."):
            self.assertNotEqual(runner.pose_for(line, poses), "ff_host_theo_pose_4", line)   # pose 4 = laughing
        self.assertEqual(runner.pose_for("Pretty ironic.", poses), "ff_host_theo_pose_4")


if __name__ == "__main__":
    unittest.main()
