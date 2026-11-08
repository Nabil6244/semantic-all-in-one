"""War Documentary archive search (war/archive_fast.py): the CSV's own searches, relevant items only, never the shared provider's files."""

import unittest
from unittest import mock

from providers.archive.ia_backend import ArchiveCandidate
from providers.archive.provider import ArchiveProvider
from providers.base import SceneRow
from cinematic_explainer.war import archive_fast as AF


def row(prompt, n="7"):
    return SceneRow.from_csv_row({"scene_number": n, "script_segment": "Soldiers fought for single buildings.", "asset_type": "archive_video",
                                  "prompt": prompt})


class ArchiveFastTests(unittest.TestCase):
    def test_queries_are_the_csvs_never_single_words(self):
        q = AF.csv_queries(row("Stalingrad factory fighting 1942 || Red October factory Stalingrad"))
        self.assertEqual(q[0], "Stalingrad factory fighting 1942")
        self.assertTrue(all(len(x.split()) >= 2 for x in q))
        self.assertLessEqual(len(q), AF.MAX_QUERIES)
        self.assertFalse(any(x.lower() in ("in", "that", "german", "then 1942") for x in q))

    def test_relevance_rejects_junk_keeps_newsreels(self):
        names, plain = AF.key_terms(AF.csv_queries(row("Stalingrad factory fighting 1942 || Red October factory Stalingrad")))
        junk = [ArchiveCandidate("a", "Applebees Cheetos Boneless Wings"), ArchiveCandidate("b", "WE'RE FEELIN' BIPPY - GTA V - Snipers Vs Stunters"),
                ArchiveCandidate("c", "Trump supporters destroy media broadcast equipment")]
        for c in junk:
            self.assertEqual(AF.relevance(c, names, plain), 0.0, c.title)
        good = ArchiveCandidate("d", "Die Deutsche Wochenschau Nr. 633 (October 21, 1942) Battle of Stalingrad", width=1920, height=1080)
        self.assertGreater(AF.relevance(good, names, plain), 4)
        tiny = ArchiveCandidate("e", "Stalingrad 1942 newsreel", width=400, height=300)
        self.assertEqual(AF.relevance(tiny, names, plain), 0.0)

    def test_installed_only_on_the_war_downloader_and_shared_class_untouched(self):
        p = ArchiveProvider()
        mgr = type("M", (), {"archive_provider": p})()
        self.assertTrue(AF.install(mgr))
        self.assertIsInstance(mgr.archive_provider, AF.WarArchiveProvider)
        self.assertIsNot(ArchiveProvider._resolve, AF.WarArchiveProvider._resolve)
        self.assertFalse(AF.install(mgr))                             # once

    def test_nothing_relevant_fails_fast_without_downloading(self):
        p = ArchiveProvider()
        AF.install(type("M", (), {"archive_provider": p})())
        with mock.patch.object(AF.WarArchiveProvider, "_search_fast", return_value=[]), \
                mock.patch("providers.hidden_subprocess.run") as run:
            r = p.resolve(row("Stalingrad factory fighting 1942"), __import__("pathlib").Path("/tmp"), log=lambda m: None)
        self.assertEqual(r.status.name, "FAILED")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class StockFallbackTests(unittest.TestCase):
    def test_plain_stock_search_from_the_csv(self):
        from cinematic_explainer.war import app_section as A
        self.assertEqual(A.stock_query_for("Stalingrad 1942 city ruins Volga || Battle of Stalingrad archive footage"), "city ruins")
        self.assertEqual(A.stock_query_for("German soldiers Stalingrad winter starvation"), "soldiers winter")
        self.assertEqual(A.stock_query_for("Operation Uranus 1942 Soviet offensive"), "")            # nothing filmable: no stock

    def test_archive_and_youtube_rows_fall_back_to_stock(self):
        from cinematic_explainer.war import app_section as A
        rows = A.csv_rows([{"scene_no": 1, "text": "x", "asset_type": "archive_video", "prompt": "Stalingrad 1942 city ruins"},
                           {"scene_no": 2, "text": "y", "asset_type": "youtube_video", "prompt": "Kyiv", "stock": "burning city night"},
                           {"scene_no": 3, "text": "z", "asset_type": "stock_video", "prompt": "city ruins smoke"},
                           {"scene_no": 4, "text": "w", "asset_type": "archive_video", "prompt": "Operation Uranus 1942"}])
        self.assertEqual((rows[0].stock, rows[0].fallbacks), ("city ruins", ["youtube_video", "stock_video"]))   # archive -> YouTube -> stock
        self.assertEqual(rows[1].stock, "burning city night")                 # the CSV's own stock column wins
        self.assertEqual(rows[1].as_fallback("stock_video").asset_type, "stock_video")
        self.assertEqual(list(rows[2].fallbacks or []), [])
        self.assertEqual(list(rows[3].fallbacks or []), ["youtube_video"])      # nothing filmable for stock: YouTube only

    def test_csv_stock_column_is_read_and_explained(self):
        import tempfile
        from pathlib import Path
        from cinematic_explainer.war import app_section as A
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "s.csv")
            p.write_text('scene_number,script_segment,asset_type,prompt,graphic,stock\n1,"The city burned.",archive_video,Stalingrad 1942,,city fire night\n')
            self.assertEqual(A.read_scenes_csv(str(p))[0]["stock"], "city fire night")
        self.assertIn("- stock (optional column", A.csv_prompt_text("x"))


class PermanentArchiveTests(unittest.TestCase):
    """2026-11-08 Stalingrad render: modern items matched on a name, a newsreel cut on its credit roll, 3.5 s cuts that froze, and old junk
    clips reused from the Visuals table. Each is now caught by a rule, for every project."""

    @classmethod
    def setUpClass(cls):
        import subprocess
        import tempfile
        from pathlib import Path
        from PIL import Image, ImageDraw, ImageFont
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        img = Image.new("RGB", (640, 360), (18, 18, 18))
        dr = ImageDraw.Draw(img)
        try:
            f = ImageFont.truetype("assets/fonts/Inter-Bold.ttf", 26)
        except OSError:
            f = ImageFont.load_default()
        for i in range(9):
            dr.text((40, 20 + i * 37), "Bastanier, Benisch, Blume, Döring, Dreßler, Graf", font=f, fill=(235, 235, 235))
        img.save(d / "credits.png")
        cls.credits = str(d / "credits.mp4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", str(d / "credits.png"), "-t", "3", "-r", "25", "-pix_fmt", "yuv420p",
                        cls.credits], check=True)
        cls.footage = str(d / "footage.mp4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=3", "-r", "25", cls.footage], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_period_check(self):
        yrs = AF.query_years(["Field Marshal Paulus surrender Stalingrad 1943"])
        self.assertFalse(AF.period_ok("armin hampel zum skandal um das corona-papier 2020", yrs))
        self.assertFalse(AF.period_ok("trump supporters destroy media broadcast equipment at capitol 2021", yrs))
        self.assertTrue(AF.period_ok("die deutsche wochenschau nr. 650 (february 1943)", yrs))
        self.assertTrue(AF.period_ok("luftwaffe honor day", yrs))
        self.assertTrue(AF.period_ok("anything at all", AF.query_years(["Kyiv drone strike"])))       # no historical year: no period rule

    def test_frame_check_spots_credits_not_footage(self):
        self.assertEqual(AF.frame_problem(self.credits), "text / credits")
        self.assertEqual(AF.frame_problem(self.footage), "")

    def test_cut_point_avoids_credits_and_varies(self):
        c = ArchiveCandidate("x", "Wochenschau 1942", duration=900.0)
        a, ln = AF.pick_moment(None, c, 8.0, set(), 0, 4)
        b, _ = AF.pick_moment(None, c, 8.0, set(), 0, 6)
        self.assertEqual(ln, 8.0)
        self.assertGreaterEqual(a, 108.0)                              # past the opening credits (12 % of 900 s)
        self.assertLessEqual(a + ln, 855.0)                            # before the closing ones
        self.assertNotAlmostEqual(a, b)                                # two scenes, two moments
        self.assertEqual(AF.pick_moment(None, ArchiveCandidate("y", "short", duration=5.0), 8.0, set(), 0, 1)[0], 0.0)

    def test_srt_cues_parse(self):
        cues = AF._srt_cues("1\n00:01:02,500 --> 00:01:05,000\nThe Sixth Army reaches the Volga\n\n2\n00:02:00,000 --> 00:02:03,000\nPrisoners\n")
        self.assertEqual(cues[0], (62.5, "The Sixth Army reaches the Volga"))

    def test_install_sets_eight_second_cuts(self):
        p = ArchiveProvider(clip_duration=3.5)
        AF.install(type("M", (), {"archive_provider": p})())
        self.assertEqual(p.clip_duration, AF.CLIP_S)

    def test_archive_falls_back_to_youtube_then_stock(self):
        from cinematic_explainer.war import app_section as A
        r = A.csv_rows([{"scene_no": 1, "text": "x", "asset_type": "archive_video", "prompt": "Stalingrad 1942 city ruins"}])[0]
        self.assertEqual(r.fallbacks, ["youtube_video", "stock_video"])

    def test_generate_rechecks_held_clips(self):
        import json
        from pathlib import Path
        from cinematic_explainer.war import app_section as A
        d = Path(self.tmp.name) / "assets"
        d.mkdir(exist_ok=True)
        shell = d / "002.mp4"
        subprocess_run = __import__("subprocess").run
        subprocess_run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "60", "-i", self.footage, "-t", "2", "-c:v", "libx264", "-f", "mp4", str(shell)])
        recs = {"001": {"status": "complete", "provider": "archive", "title": "Applebees Cheetos Boneless Wings", "local_path": self.footage},
                "002": {"status": "complete", "provider": "archive", "title": "Stalingrad 1942 newsreel", "local_path": str(shell)},
                "003": {"status": "complete", "provider": "archive", "title": "Wochenschau Stalingrad 1942", "local_path": self.credits},
                "004": {"status": "complete", "provider": "archive", "title": "Wochenschau Stalingrad 1942", "local_path": self.footage},
                "005": {"status": "complete", "provider": "archive", "title": "Applebees", "local_path": self.footage, "user_override": True}}
        (d / ".asset_manifest.json").write_text(json.dumps(recs))
        rows = A.csv_rows([{"scene_no": i, "text": "The city burned.", "asset_type": "archive_video", "prompt": "Stalingrad 1942 newsreel"}
                           for i in range(1, 6)])
        self.assertEqual(sorted(A.audit_held(d, rows)), ["1", "2", "3"])

    def test_prompt_steers_archive_to_what_exists(self):
        from cinematic_explainer.war import app_section as A
        txt = A.csv_prompt_text("x")
        self.assertIn("exists on the Internet Archive", txt)
        self.assertIn("Always include the\n      year", txt)
