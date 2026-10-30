"""Automatic real-picture path of the Explainer (offline): period (era) awareness of the picture pass, the cheap period check of a fetched picture, and the hops from a plan's picture beat to the
Visual Plan row and to the compiled spec with the fetched file swapped in (exactly the application's own functions; the network step itself is exercised by hand, see the notes of the change)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from explainer.beats import relevance as REL
from explainer.director import compose_pictures as CP
from test_explainer_pictures import run_kinds, words_for
from explainer.director.options import DirectorOptions
from explainer.director.plan import direct

ANCIENT = ("Venice began as a place where people went to hide. In the fifth century the Western Roman Empire collapsed and invaders came. "
           "Torcello Marshes sheltered the families who fled the mainland. Torcello Marshes kept the invaders away. Later the Byzantine Empire ruled the coast. "
           "Today the Torcello Marshes are full of boats and tourists.")
MODERN = "Today the Torcello Marshes are full of boats and tourists. Torcello Marshes is a famous place now. Torcello Marshes has many islands."
WIDE = mock.patch.object(CP, "PICTURE_SHARE", 0.95)        # the tests are about WHICH beats are pictured, not about the share of the runtime


class Era(unittest.TestCase):
    def test_years(self):
        t = lambda s: CP.era_year(s.lower().split())      # noqa: E731
        self.assertEqual(t("during the fifth and sixth centuries"), 550)
        self.assertEqual(t("by the eleventh century"), 1050)
        self.assertEqual(t("in the 5th century"), 450)
        self.assertEqual(t("in 1204 ships sailed"), 1204)
        self.assertEqual(t("in the third century bc"), -250)
        self.assertEqual(t("ancient rome fell"), 200)
        self.assertEqual(t("rome fell but today it is a city"), 2026)         # the last mention wins: the narration is back in the present
        self.assertIsNone(t("the shallow water made it hard"))
        self.assertIsNone(t("in 12345 and 99"))

    def test_beat_lookback(self):
        words = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("during the fifth century people fled . the water was shallow".replace(".", "").split())]
        b = type("B", (), {"start": 3.0, "end": 5.0})()
        e = CP.era_of_beat(words, b)
        self.assertEqual(e["year"], 450)           # the middle of the fifth century
        self.assertIn("earlier", e["why"])

    def test_modifier(self):
        self.assertEqual(CP.era_modifier(550), ["historical", "painting"])
        self.assertEqual(CP.era_modifier(1650), ["antique", "engraving"])
        self.assertEqual(CP.era_modifier(1815), [])
        self.assertEqual(CP.era_modifier(None), [])
        self.assertEqual(CP.era_modifier(2026), [])


class Names(unittest.TestCase):
    def test_half_a_name_is_not_a_subject(self):
        toks = "look east across the adriatic and you will find the coast".split()
        q = CP.build_query(toks, ["Middle East", "Adriatic Sea"], {"east", "adriatic"}, {"east": "East", "adriatic": "Adriatic"})
        self.assertTrue(q is None or q["query"].lower() != "east", q)
        q2 = CP.build_query("the middle east was rich".split(), ["Middle East"], {"east", "middle"}, {"east": "East", "middle": "Middle"})
        self.assertEqual(q2["query"], "Middle East")


class PlanningByPeriod(unittest.TestCase):
    def kinds(self, script):
        opt = DirectorOptions(pictures=True, min_beat_s=1.0, max_beat_s=3.0, footage_share=0.0, cartoon_share=0.0)
        with WIDE:
            return run_kinds(script, opt)

    def test_ancient_photo_of_a_place_is_not_chosen(self):
        beats, info, words, total = self.kinds(ANCIENT)
        pic = info["pictures"]
        for r in pic["upgraded"]:
            if r["era"]["year"] < 1800:
                if "Torcello" in r["query"]:                          # a photo of the lagoon is today's lagoon: before 1800 the search must ask for old art instead
                    self.assertTrue(r["query"].endswith(("historical painting", "antique engraving")), r)
        self.assertTrue(any(r["era"]["year"] >= 1800 and "Torcello" in r["query"] for r in pic["upgraded"]), pic)       # ... but "Today the Torcello Marshes" may have its photograph
        for b in beats:
            if b.kind == "footage" and info["pictures"]["era"].get(b.id, {}).get("year", 2026) < 1800:
                self.assertTrue(CP.history_safe(CP._toks(b.picture_query)) or b.picture_query.endswith(("historical painting", "antique engraving")), b.picture_query)

    def test_ancient_empire_is_pictured_with_its_period_recorded(self):
        beats, info, words, total = self.kinds(ANCIENT)
        ups = [r for r in info["pictures"]["upgraded"] if "Roman" in r["query"]]
        self.assertTrue(ups, info["pictures"])
        self.assertLess(ups[0]["era"]["year"], 1800)
        self.assertIn(ups[0]["beat"], info["pictures"]["era"])

    def test_modern_narration_unchanged(self):
        beats, info, words, total = self.kinds(MODERN)
        for r in info["pictures"]["upgraded"]:
            self.assertGreaterEqual(r["era"]["year"] or 2026, 1800)
            self.assertNotIn("painting", r["query"])

    def test_era_words_added_only_when_relevance_accepts_them(self):
        with mock.patch.object(REL, "ERA_QUERY_WORDS", CP.ERA_QUERY_WORDS, create=True):
            self.assertTrue(CP.relevance_accepts_era())
            beats, info, words, total = self.kinds(ANCIENT)
            qs = [r["query"] for r in info["pictures"]["upgraded"]]
            self.assertTrue(any(q.endswith("historical painting") for q in qs), qs)
            for q in qs:
                spoken_or_era = [w for w in CP._toks(q) if w not in CP.ERA_QUERY_WORDS]
                self.assertTrue(spoken_or_era)
        self.assertTrue(CP.relevance_accepts_era())              # the relevance gate now knows the era words (explainer/beats/relevance.py: ERA_QUERY_WORDS)


class Vet(unittest.TestCase):
    FERRY = {"source_url": "https://www.pexels.com/photo/ferry-navigates-venetian-lagoon-waters-39487501/", "provider": "pexels"}
    RUINS = {"source_url": "https://www.pexels.com/photo/ancient-roman-forum-with-ruins-in-rome-36713239/"}
    ART = {"source_url": "https://commons.wikimedia.org/wiki/File:Roman_forum_oil_painting.jpg", "alt": "Roman Forum, oil painting on canvas"}      # says it is artwork AND names the subject
    TOYS = {"alt": "Roman army toy soldiers in a diorama", "tags": "roman, army, historical, antique"}
    PAINT = {"source_url": "https://www.pexels.com/photo/oil-painting-of-venice-lagoon-1/"}

    def test_modern_refused_for_old_narration(self):
        ok, why = CP.vet_picture(self.FERRY, 550)
        self.assertFalse(ok)
        self.assertIn("ferry", why)
        self.assertTrue(CP.vet_picture(self.ART, 550)[0])
        self.assertFalse(CP.vet_picture(self.RUINS, 550)[0])                  # a modern photo of ruins is not period artwork
        self.assertFalse(CP.vet_picture(self.TOYS, 550)[0])                   # "historical" and "antique" tags alone do not make a toy army old art
        self.assertTrue(CP.vet_picture(self.PAINT, 550)[0])

    def test_old_art_must_show_the_subject(self):
        tomb = {"source_url": "https://www.pexels.com/photo/close-up-shot-of-a-painting-7512535/"}
        q = "Western Roman Empire historical painting".rsplit(" ", 2)[0]
        self.assertFalse(CP.vet_picture(tomb, 476, q)[0])                      # old art, wrong subject
        self.assertTrue(CP.vet_picture(self.ART, 476, q)[0])                   # roman forum / rome
        self.assertFalse(CP.vet_picture({"source_url": "https://www.pexels.com/photo/scenic-view-of-nin-with-historical-ruins-1/"}, 476, "adriatic")[0])
        self.assertTrue(CP.vet_picture(tomb, 476)[0])                          # no subject given: era check only

    def test_unknown_is_refused_and_modern_narration_passes_all(self):
        self.assertFalse(CP.vet_picture({}, 550)[0])
        self.assertFalse(CP.vet_picture({"source_url": "https://www.pexels.com/photo/blue-sky-9/"}, 550)[0])       # nothing says it is old
        self.assertTrue(CP.vet_picture(self.FERRY, 2026)[0])
        self.assertTrue(CP.vet_picture(self.FERRY, None)[0])

    def plan(self, fallback=True):
        clip = {"asset": "stock_image:Venetian Lagoon", "kenburns": True, "reason": "x"}
        b = {"id": "e7", "mode": "footage", "footage": {"clips": [clip]}}
        if fallback:
            b["fallback_clip"] = {"asset": "/tmp/board.mp4", "reason": "the illustrated scene"}
        return {"beats": [b, {"id": "e8", "mode": "map"}]}

    def test_refused_picture_goes_back_to_the_illustration(self):
        p = self.plan()
        res = CP.vet_plan_pictures(p, {"era": {"e7": {"year": 550}}}, {"stock_image:Venetian Lagoon": self.FERRY})
        self.assertEqual(res["refused"][0]["beat"], "e7")
        self.assertTrue(res["refused"][0]["fallback"])
        self.assertEqual(p["beats"][0]["footage"]["clips"][0]["asset"], "/tmp/board.mp4")
        self.assertNotIn("kenburns", p["beats"][0]["footage"]["clips"][0])

    def test_refused_without_fallback_is_reported_not_kept_silently(self):
        p = self.plan(False)
        res = CP.vet_plan_pictures(p, {"era": {"e7": {"year": 550}}}, {"stock_image:Venetian Lagoon": self.FERRY})
        self.assertFalse(res["refused"][0]["fallback"])

    def test_accepted_stays(self):
        p = self.plan()
        res = CP.vet_plan_pictures(p, {"era": {"e7": {"year": 550}}}, {"stock_image:Venetian Lagoon": self.ART})
        self.assertEqual(res["refused"], [])
        self.assertEqual(p["beats"][0]["footage"]["clips"][0]["asset"], "stock_image:Venetian Lagoon")


class Hops(unittest.TestCase):
    """plan picture beat -> the application's Visual Plan row -> media_map -> compiled spec shows the file (the same functions the application calls)."""

    def test_plan_to_visual_row_to_compiled_file(self):
        from hybrid.app_integration import _scene_map, visual_dicts
        from hybrid.compile import compile_plan
        from hybrid.plan import HybridPlan
        from PIL import Image
        words = words_for(ANCIENT)
        with WIDE:
            res = direct(words, ANCIENT, DirectorOptions(pictures=True, min_beat_s=1.0, max_beat_s=3.0, cartoon_share=0.0, work_dir="/private/tmp/claude-501/s/pics_work"), materialize=False)
        self.assertEqual(res.problems, [])
        q = res.report["pictures"]["queries"]
        self.assertTrue(q, res.report["pictures"])
        hp = HybridPlan.from_dict(json.loads(json.dumps(res.plan)))
        rows = visual_dicts(hp)
        prompts = [r["prompt"] for r in rows if r["asset_type"] == "stock_image"]          # the picture beats AND the photo cards of the map beats
        for v in q.values():
            self.assertIn(v.partition(":")[2], prompts)
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "001.jpg"
            Image.new("RGB", (1920, 1080), (120, 90, 60)).save(f)
            media_map = {(i["occ"].line, i["occ"].part): str(f) for i in _scene_map(hp)}
            c = compile_plan(hp, validate=False, base_dir=td, media_map=media_map)
            self.assertIn(json.dumps(str(f))[1:-1], json.dumps(c.spec, default=str))
            self.assertNotIn("stock_image:", json.dumps(c.spec, default=str))


if __name__ == "__main__":
    unittest.main()


class FetchVetsPeriodPictures(unittest.TestCase):
    """pakmap.sourcing.fetch_scenes (the app's own fetch) reports a modern-looking picture as missing when the prompt asked for old art, and leaves every other prompt alone."""

    def run_fetch(self, prompt, source_url):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace as NS
        from pakmap import sourcing as S
        d = Path(tempfile.mkdtemp())
        (d / "001.jpg").write_bytes(b"x")

        class Man:
            def __init__(self, images_dir): pass
            def get(self, n): return {"status": "complete", "source_url": source_url, "stock_query": prompt}
            def set(self, n, rec): pass

        sc = NS(scene_number=1, script_segment="x", asset_type="stock_image", prompt=prompt)
        return S.fetch_scenes([sc], d, resolver=lambda rows, dd, **k: None, find_file=lambda dd, n: (Path(dd) / "001.jpg"), manifest_cls=Man, log=lambda m: None)

    def test_modern_photo_for_old_art_prompt_is_reported_missing(self):
        r = self.run_fetch("Adriatic Sea historical painting", "https://www.pexels.com/photo/cityscape-of-piran-croatia-6726262/")
        self.assertEqual(r.paths, {})
        self.assertIn("1", r.missing)
        self.assertIn("Retry", r.missing["1"])

    def test_period_photo_is_kept(self):
        r = self.run_fetch("Western Roman Empire historical painting", "https://www.pexels.com/photo/roman-forum-oil-painting-on-canvas-36713239/")
        self.assertIn("1", r.paths)

    def test_modern_photo_of_ruins_is_refused(self):
        r = self.run_fetch("Western Roman Empire historical painting", "https://www.pexels.com/photo/ancient-roman-forum-with-ruins-in-rome-36713239/")
        self.assertEqual(r.paths, {})

    def test_prompt_without_era_words_is_untouched(self):
        r = self.run_fetch("Adriatic Sea", "https://www.pexels.com/photo/cityscape-of-piran-croatia-6726262/")
        self.assertIn("1", r.paths)


class PeriodGateAtPick(unittest.TestCase):
    """The stock picker drops candidates that are not period artwork of the subject BEFORE ranking, so the next real result wins instead of a toy army or a modern photo."""

    def cand(self, i, alt, tags="", url=""):
        from types import SimpleNamespace
        return SimpleNamespace(asset_id=str(i), source_url=url, extra={"alt": alt, "tags": tags})

    def gate(self, stock, cands):
        from providers.stock.base import StockProvider
        from types import SimpleNamespace
        sp = StockProvider.__new__(StockProvider)
        sc = SimpleNamespace(stock=stock, stock_media_type="image", scene_number="1")
        return [c.asset_id for c in sp._period_gate(sc, cands, lambda m: None)]

    def test_only_artwork_of_the_subject_passes(self):
        cs = [self.cand(1, "Colorful fresco depicting ancient Roman life in Pompeii"), self.cand(2, "Miniature toy soldiers in a battle diorama", "roman, historical"),
              self.cand(3, "Aerial view of Rome skyline"), self.cand(4, "Oil painting of the Mongol cavalry")]
        self.assertEqual(self.gate("Western Roman Empire historical painting", cs), ["1"])

    def test_commons_result_needs_subject_and_nothing_modern_not_an_art_word(self):
        a = self.cand(1, "Siege of Constantinople 1453 - Byzantine Empire")
        a.extra["collection"] = "wikimedia"
        b = self.cand(2, "Byzantine Empire souvenir shop")
        b.extra["collection"] = "wikimedia"
        c = self.cand(3, "Siege of Rome 1527")
        c.extra["collection"] = "wikimedia"
        self.assertEqual(self.gate("Byzantine Empire historical painting", [a, b, c]), ["1"])

    def test_requests_without_era_words_are_untouched(self):
        cs = [self.cand(1, "Aerial view of Rome skyline")]
        self.assertEqual(self.gate("Rome skyline", cs), ["1"])
