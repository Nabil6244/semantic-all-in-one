"""Aviation footage director (docs/aviation/PLAN.md section 7, step 1): YouTube clips that show the sentence, checked by title and by
their storyboard frames before capture; news lines get extra clips from other videos; nothing passes -> no clip (never a wrong one).
No network: search, frames and capture are fakes."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from aviation import director as D
from cinematic_explainer.war import director_frames as F
from cinematic_explainer.war.director_search import Candidate


def tiles(kind_by_second, step=2.0, n=60, seed=""):
    """Storyboard tiles; kind_by_second(t) -> 'footage' | 'studio' | ...; footage tiles move, so no 'static' flag."""
    import hashlib
    out = []
    for i in range(n):
        t = i * step
        img = np.full((90, 160, 3), (i * 37) % 255, dtype=np.uint8)
        tl = F.Tile(t=t, img=img, kind=kind_by_second(t), hash=hashlib.md5(f"{seed}{i}".encode()).hexdigest()[:16], cut_before=(i % 10 == 0), detail=5.0)
        out.append(tl)
    return out


class Fakes:
    def __init__(self, results, frames):
        self.results = results          # query -> [Candidate]
        self.frames = frames            # video_id -> tiles
        self.captured = []

    def search(self, queries):
        seen, out = set(), []
        for q in queries:
            for c in self.results.get(q, []) + self.results.get("*", []):
                if c.video_id not in seen:
                    seen.add(c.video_id)
                    out.append(c)
        return out

    def tiles(self, c):
        return self.frames.get(c.video_id, [])

    def capture(self, video_id, start, seconds, dest, tl):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"clip")
        self.captured.append((video_id, start, seconds, str(dest)))
        return {"ok": True, "path": str(dest), "reasons": [], "seconds": 1.0}


def cand(vid, title, channel="Some Channel", duration=600.0):
    return Candidate(video_id=vid, title=title, channel=channel, duration=duration, queries=["q"], rank=1)


GOOD = lambda t: "footage"
STUDIO = lambda t: "studio"


class RulesTests(unittest.TestCase):
    def test_junk_titles_are_rejected(self):
        for title in ("Air France Joon | Official Trailer", "Air France Safety Video 1998", "Joon airline REACTION",
                      "Joon airline explained | podcast", "Air France animated safety cartoon", "Joon #shorts"):
            self.assertTrue(D.title_reject(title, D.classify_line("Air France launched Joon in 2017.")), title)

    def test_named_type_must_be_in_the_title(self):
        c = D.classify_line("The A350 seats 292 passengers in a three-class cabin.")
        self.assertTrue(D.title_reject("Boeing 737 landing in Paris", c))
        self.assertFalse(D.title_reject("Air France A350-900 cabin tour", c))

    def test_english_titles_rank_first(self):
        c = D.classify_line("Air France launched Joon in 2017.")
        en = D.title_score(cand("a", "Air France launches Joon, its new airline"), c)
        fr = D.title_score(cand("b", "Air France fait décoller Joon, sa nouvelle compagnie"), c)
        self.assertGreater(en, fr)


class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_director(self, scenes, fakes):
        return D.run(scenes, self.d / "assets", self.d / "state", search=fakes.search, tiles=fakes.tiles, capture=fakes.capture)

    def test_studio_video_is_skipped_for_a_filmed_one(self):
        fk = Fakes({"*": [cand("studio1", "Air France strike debate"), cand("film1", "Air France strike Paris 2015 workers")]},
                   {"studio1": tiles(STUDIO, seed="s"), "film1": tiles(GOOD, seed="f")})
        sc = [{"scene_no": 1, "text": "In 2015 Air France workers went on strike over job cuts.", "asset_type": "youtube_video",
               "prompt": "Air France strike 2015", "mode": "news"}]
        rep = self.run_director(sc, fk)
        self.assertEqual(rep["scenes"]["1"]["video_id"], "film1")
        self.assertEqual(fk.captured[0][0], "film1")

    def test_window_avoids_the_start_of_the_video(self):
        fk = Fakes({"*": [cand("film1", "Air France strike Paris 2015 workers", duration=120.0)]}, {"film1": tiles(GOOD, n=60)})
        sc = [{"scene_no": 1, "text": "In 2015 Air France workers went on strike.", "asset_type": "youtube_video", "prompt": "x", "mode": "news"}]
        self.run_director(sc, fk)
        self.assertGreaterEqual(fk.captured[0][1], 120.0 * 0.05)

    def test_news_line_gets_extra_clips_from_other_videos(self):
        fk = Fakes({"*": [cand("v1", "Air France strike Paris 2015"), cand("v2", "Air France workers strike Orly 2015"),
                          cand("v3", "Air France strike 2015 protest Roissy")]},
                   {"v1": tiles(GOOD, seed="1"), "v2": tiles(GOOD, seed="2"), "v3": tiles(GOOD, seed="3")})
        sc = [{"scene_no": 1, "text": "In 2015 Air France workers went on strike over job cuts.", "asset_type": "youtube_video", "prompt": "x",
               "mode": "news"}]
        rep = self.run_director(sc, fk)
        extra = json.loads((self.d / "state" / D.EXTRAS).read_text())["1"]
        self.assertEqual(len(extra), 2)
        vids = {rep["scenes"]["1"]["video_id"]} | {e["video_id"] for e in extra}
        self.assertEqual(len(vids), 3)

    def test_nothing_passes_means_no_clip(self):
        fk = Fakes({"*": [cand("t1", "Joon Official Trailer"), cand("s1", "Joon debate")]}, {"s1": tiles(STUDIO)})
        sc = [{"scene_no": 1, "text": "Air France launched Joon in 2017.", "asset_type": "youtube_video", "prompt": "x", "mode": "news"}]
        rep = self.run_director(sc, fk)
        self.assertEqual(rep["scenes"]["1"]["decision"], "none")
        self.assertFalse(fk.captured)
        self.assertIn("1", rep["unfilled"])

    def test_same_video_seconds_are_not_reused(self):
        fk = Fakes({"*": [cand("v1", "Air France strike Paris 2015 workers")]}, {"v1": tiles(GOOD)})
        sc = [{"scene_no": i, "text": "In 2015 Air France workers went on strike.", "asset_type": "youtube_video", "prompt": "x", "mode": "fleet"}
              for i in (1, 2)]
        self.run_director(sc, fk)
        (a_vid, a0, a_len, _), (b_vid, b0, b_len, _) = fk.captured[:2]
        self.assertTrue(b0 >= a0 + a_len or b0 + b_len <= a0)

    def test_record_says_where_it_came_from(self):
        fk = Fakes({"*": [cand("film1", "Air France strike Paris 2015 workers", channel="euronews")]}, {"film1": tiles(GOOD)})
        sc = [{"scene_no": 1, "text": "In 2015 Air France workers went on strike.", "asset_type": "youtube_video", "prompt": "x", "mode": "news"}]
        self.run_director(sc, fk)
        from asset_manager import AssetManifest
        rec = AssetManifest(self.d / "assets").get("1") or AssetManifest(self.d / "assets").get("001")
        self.assertEqual(rec["selection_method"], "aviation_director")
        self.assertEqual(rec["channel"], "euronews")
        self.assertEqual(rec["status"], "complete")

    def test_only_youtube_rows_are_directed(self):
        fk = Fakes({}, {})
        sc = [{"scene_no": 1, "text": "x", "asset_type": "none"}, {"scene_no": 2, "text": "y", "asset_type": "flow_video", "prompt": "p"}]
        rep = self.run_director(sc, fk)
        self.assertEqual(rep["scenes"], {})


if __name__ == "__main__":
    unittest.main()


class RelevanceTests(unittest.TestCase):
    """Found in the first real run of the director (2026-11-13): off-topic extras passed because the line named no event or type."""

    def test_a_named_airline_must_be_in_the_title(self):
        c = D.classify_line("Within hours, angry Air France workers stormed a meeting near Paris.")
        self.assertTrue(D.title_reject("92 News Headlines | Imran Khan rally", c))
        self.assertFalse(D.title_reject("Air France workers clash with police during demo", c))

    def test_the_csv_airline_counts_too(self):
        c = D.classify_line("In its first year, it carried 3 million passengers.")
        self.assertTrue(D.title_reject("Paris airport walking tour 4K", c, airlines=["joon"]))
        self.assertFalse(D.title_reject("Air France unveils first Joon aircraft", c, airlines=["joon"]))
        self.assertFalse(D.title_reject("Air France A320 takeoff Paris", c, airlines=["joon"]))      # the parent airline is fine

    def test_unnamed_line_needs_an_aviation_word(self):
        c = D.classify_line("The message was clear.")
        self.assertTrue(D.title_reject("My day in Seoul vlog", c))
        self.assertFalse(D.title_reject("Busy airport terminal timelapse", c))

    def test_non_latin_titles_are_rejected(self):
        c = D.classify_line("Air France confirmed plans to cut 2,900 jobs.")
        self.assertTrue(D.title_reject("에어프랑스 Air France 승무원 브이로그", c))
        self.assertTrue(D.title_reject("ایئر فرانس Air France خبریں", c))

    def test_trip_reports_stay_out_of_news_lines(self):
        c = D.classify_line("Air France launched Joon in 2017.")
        self.assertTrue(D.title_reject("Joon A321 Paris-CDG to Barcelona Economy Flight Experience | TRIP REPORT", c))
        f = D.classify_line("The A321 cabin has 200 seats.")
        self.assertFalse(D.title_reject("Joon A321 Paris-CDG to Barcelona Economy Flight Experience | TRIP REPORT", f))


class SpecificityTests(unittest.TestCase):
    def test_the_exact_airline_beats_its_parent(self):
        c = D.classify_line("Air France launched Joon, a new airline.")
        own = D.title_score(cand("a", "Air France unveils first Joon aircraft"), c, airlines=["joon"])
        parent = D.title_score(cand("b", "Air France and the Patrouille de France, the movie"), c, airlines=["joon"])
        self.assertGreater(own, parent + 2)

    def test_the_csv_aircraft_type_is_required(self):
        c = D.classify_line("But a cheap airline is only as safe as the decisions made in its cockpit.")
        self.assertTrue(D.title_reject("Glider cockpit decision-making", c, aircraft=["a320"]))
        self.assertFalse(D.title_reject("A320 cockpit takeoff Paris", c, aircraft=["a320"]))


class SubBrandTests(unittest.TestCase):
    def test_news_about_a_sub_brand_needs_its_own_name(self):
        c = D.classify_line("So on December 1st, 2017, Air France launched a new airline called Joon.")
        self.assertTrue(D.title_reject("Air France and the Patrouille de France, the movie", c, airlines=["air_france"]))
        self.assertFalse(D.title_reject("Air France unveils first Joon aircraft", c, airlines=["air_france"]))


class EmiratesRenderFixes(unittest.TestCase):
    def test_podcast_channel_is_rejected_even_with_a_clean_title(self):
        c = D.classify_line("In the six months to September, Emirates carried 21.8 million passengers.")
        self.assertTrue(D.title_reject("The Bizarre Case Of Emirates Flight 203", c, channel="The Just Interesting Podcast"))

    def test_freighter_line_needs_a_freighter_video(self):
        c = D.classify_line("Five new Boeing 777 freighters joined the fleet.")
        self.assertTrue(D.title_reject("The NEW Emirates Boeing 777-300ER | Cabin & Airframe", c))
        self.assertFalse(D.title_reject("Emirates SkyCargo Boeing 777F takeoff Dubai", c))
        self.assertFalse(D.title_reject("Emirates Boeing 777 Freighter delivery flight", c))

    def test_news_lines_accept_a_shorter_clean_stretch(self):
        self.assertEqual(D.min_stretch("news"), 2.0)
        self.assertGreaterEqual(D.min_stretch("fleet"), 3.0)

    def test_search_cache_is_shared_between_projects(self):
        a, b = D.cache_dir(Path("/p1/state")), D.cache_dir(Path("/p2/state"))
        self.assertEqual(a, b)

    def test_capture_tries_are_capped_at_two(self):
        self.assertEqual(D.CAPTURE_TRIES, 2)
