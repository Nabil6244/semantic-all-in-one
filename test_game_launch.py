"""Game Launch style: scenes CSV parsing, cut-safe trailer clipping, the timeline, Shorts spans and the app wiring (no rendering)."""
import tempfile
import unittest
from pathlib import Path

from game_launch import plan as P
from game_launch import runner as R

ROOT = Path(__file__).resolve().parent
HEAD = "narration,shot,game_clip,game_at,real,real_at,left,right,title,subtitle,place\n"


def write(text: str) -> str:
    d = Path(tempfile.mkdtemp())
    f = d / "scenes.csv"
    f.write_text(HEAD + text, encoding="utf-8")
    return str(f)


class PlanTests(unittest.TestCase):
    def test_lines_and_continuation_rows(self):
        p = P.read(write('Line one.,chapter,t1.mp4,4,,,,,Vice City,,\n'
                         'Line two.,map,,,,,,,,,Vice City=Miami@25.77,-80.19\n'
                         ',split,t1.mp4,1:02.5,miami skyline,,vice city,miami,,,\n'))
        self.assertEqual(p["errors"], [])
        self.assertEqual(len(p["lines"]), 2)
        self.assertEqual([s["kind"] for s in p["lines"][1]["shots"]], ["map", "split"])
        split = p["lines"][1]["shots"][1]
        self.assertAlmostEqual(split["game_at"], 62.5)
        self.assertEqual((split["left"], split["right"]), ("VICE CITY", "MIAMI"))
        self.assertEqual(p["pins"][0]["real"], "Miami")
        self.assertEqual(p["lines"][0]["shots"][0]["number"], "01")

    def test_errors_are_reported_not_raised(self):
        p = P.read(write(',game,t1.mp4,1,,,,,,,\n'
                         'A line.,dance,,,,,,,,,\n'
                         'B line.,split,,,,,,,,,\n'
                         'C line.,map,,,,,,,,,Nowhere\n'))
        text = "\n".join(p["errors"])
        self.assertIn("first row needs narration", text)
        self.assertIn("'dance'", text)
        self.assertIn("needs game_clip", text)
        self.assertIn("needs real", text)
        self.assertIn("should look like", text)

    def test_real_file_and_search_rows_both_go_to_the_visuals_tab(self):
        d = Path(tempfile.mkdtemp())
        (d / "clip.mp4").write_bytes(b"x")
        f = d / "s.csv"
        f.write_text(HEAD + 'One.,real,,,clip.mp4,2,,,,,\n,real,,,miami beach drone,,,,,,\n', encoding="utf-8")
        p = P.read(str(f))
        self.assertEqual(p["errors"], [])
        vs = P.visual_scenes(p)
        self.assertEqual([v["scene_no"] for v in vs], [1, 2])
        self.assertEqual(vs[1]["prompt"], "miami beach drone")
        self.assertEqual(P.local_files(p), {1: str(d / "clip.mp4")})


class EngineTests(unittest.TestCase):
    def test_clip_never_freezes(self):
        inp, f = R._clip("x.mp4", 10.0, 3.0, cuts=[11.0, 20.0], seconds=60.0)
        self.assertIn("setpts=(PTS-STARTPTS)/1.0000", f)      # plays on through the next cut at normal speed ...
        self.assertNotIn("tpad", f)                           # ... never a held last frame
        self.assertEqual(inp[inp.index("-t") + 1], "3.000")
        inp, _f = R._clip("x.mp4", 75.0, 4.0, cuts=[30.0, 76.5], seconds=90.0)
        self.assertLessEqual(float(inp[1]) + 4.0, 76.5)        # moved earlier: never into the end logo
        _inp, f = R._clip("x.mp4", 10.0, 3.0, cuts=[12.7, 20.0], seconds=60.0)
        self.assertNotIn("tpad", f)                           # nearly fits: a touch slower, no freeze
        inp, f = R._clip("x.mp4", 10.0, 3.0, cuts=[20.0], seconds=60.0)
        self.assertIn("/1.0000", f)
        self.assertNotIn("tpad", f)
        self.assertEqual(inp[inp.index("-t") + 1], "3.000")

    def test_timeline_shares_line_time_and_fills_to_the_end(self):
        plan = {"lines": [{"text": "a", "vo_dur": 2.0, "shots": [{"kind": "title"}]},
                          {"text": "b", "vo_dur": 4.0, "shots": [{"kind": "map"}, {"kind": "split"}]},
                          {"text": "c", "vo_dur": 3.0, "shots": [{"kind": "chapter", "title": "X"}]}]}
        shots, vo, total = R.timeline(plan)
        self.assertEqual(shots[0]["start"], 0.0)
        for a, b in zip(shots, shots[1:]):
            self.assertAlmostEqual(a["start"] + a["len"], b["start"], places=2)
        self.assertLess(shots[1]["len"], shots[2]["len"])        # a map shares less of its line
        self.assertAlmostEqual(shots[-1]["start"] + shots[-1]["len"], total, places=2)
        self.assertGreater(vo[2][1] - (vo[1][1] + 4.0 + 0.32), 0.4)   # a breath before a chapter

    def test_short_spans_one_per_chapter_under_a_minute(self):
        lines = []
        for c in range(2):
            lines.append({"text": "chapter", "vo_dur": 2.0, "shots": [{"kind": "chapter", "title": f"Part {c}"}]})
            for _ in range(12):
                lines.append({"text": "x", "vo_dur": 6.0, "shots": [{"kind": "split", "right": "MIAMI"}]})
        shots, vo, total = R.timeline({"lines": lines})
        spans = R.short_spans(shots, vo, total)
        self.assertEqual(len(spans), 2)
        for sp in spans:
            self.assertLessEqual(sp["end"] - sp["start"], 58.5)
            self.assertEqual(sp["second"], "= MIAMI")

    def test_speakable_rewords_on_later_attempts(self):
        self.assertEqual(R._speakable("GTA 6.", 0), "GTA 6.")
        self.assertEqual(R._speakable("Is it real? GTA 6.", 3), "Is it real, GTA six.")

    def test_trailer_lookup_by_name_or_stem(self):
        d = Path(tempfile.mkdtemp())
        (d / "Trailer2.MP4").write_bytes(b"x")
        self.assertEqual(R.trailer_path(str(d), "trailer2.mp4").name.lower(), "trailer2.mp4")
        self.assertEqual(R.trailer_path(str(d), "trailer2").name, "Trailer2.MP4")
        self.assertIsNone(R.trailer_path(str(d), "trailer3.mp4"))

    def test_example_csv_parses(self):
        p = P.read(str(ROOT / "game_launch" / "example_scenes.csv"))
        self.assertEqual(p["errors"], [])
        self.assertGreaterEqual(len(p["pins"]), 2)


class AppWiringTests(unittest.TestCase):
    def test_registered_and_wired(self):
        from ui import style_registry as SR
        import export_state
        import visual_bridge

        self.assertIn("Game Launch", dict(SR.grouped(SR.with_extras(("Normal video",)))).get("Documentary", []))
        self.assertIn("Game Launch", SR.EXTRA_BLURBS)
        self.assertIn("Game Launch", SR.EXTRA_CARDS)
        self.assertIn("game_launch", visual_bridge.OWNERS)
        self.assertEqual(export_state.STYLE_LABELS.get("game_launch"), "Game Launch")
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        for needle in ("from ui import game_launch_section as _gl_section", "_gl_section.activate(self)", "_gl_section.deactivate(self)",
                       "_gl_section.cta(self, action)", "_gl_section.sync_cta(self)", '"_gl_running"', 'return "Game Launch"',
                       '"gl_generate", "gl_render", "gl_cancel"', "_gl_section.resume_on_open(self)",
                       'gl_block.grid() if active == "Game Launch"'):
            self.assertIn(needle, src)
        self.assertIn('"Game Launch"', (ROOT / "ui" / "style_kit.py").read_text(encoding="utf-8"))


class NewShotTests(unittest.TestCase):
    """Scoreboard, character file, timeline, storm map, trailer receipts and the chapter bar (no rendering)."""

    def test_board_items_keep_an_equals_sign_in_the_label(self):
        items = P.parse_items("+Leonida = Florida=yes; Map size=no; Lucia", board=True)
        self.assertEqual([(i["label"], i["value"], i["new"]) for i in items],
                         [("Leonida = Florida", True, True), ("Map size", False, False), ("Lucia", True, False)])
        self.assertEqual(P.parse_items("DEC 2023=Trailer 1; NOV 19 2026=Launch", board=False)[1]["value"], "Launch")

    def test_new_kinds_parse_and_complain(self):
        p = P.read(write('A.,board,,,,,,,Score,Six regions=yes; Map size=no,\n'
                         'B.,dossier,t2.mp4,14,,,,,Brian Heder,Keys drug runner | Old school.,\n'
                         'C.,timeline,,,,,,,Road,DEC 2023=Trailer 1; NOV 2026=Launch,\n'
                         'D.,storms,,,,,,,Storms,,AL041992; AL092022\n'))
        self.assertEqual(p["errors"], [])
        d = p["lines"][1]["shots"][0]
        self.assertEqual((d["role"], d["line_text"]), ("Keys drug runner", "Old school."))
        self.assertEqual(p["lines"][3]["shots"][0]["storms"], ["AL041992", "AL092022"])
        bad = P.read(write('A.,board,,,,,,,Score,,\nB.,dossier,,,,,,,Brian,,\nC.,storms,,,,,,,S,,hurricane\n'))
        self.assertEqual(len(bad["errors"]), 3)

    def test_receipt_names_the_trailer_and_time(self):
        from game_launch import look as L
        self.assertEqual(L.receipt("gta6_trailer2.mp4", 74.6), "TRAILER 2  ·  1:14")
        self.assertEqual(L.receipt("gta6_launch_trailer.mp4", 8), "LAUNCH TRAILER  ·  0:08")

    def test_chapter_bar_ends_at_the_recap_board(self):
        new_board = {"kind": "board", "items": [{"label": "a", "value": True, "new": True}]}
        recap = {"kind": "board", "items": [{"label": "a", "value": True, "new": False}]}
        shots = [dict(kind="chapter", title="A", start=0, len=1), dict(new_board, start=3, len=2),
                 dict(kind="chapter", title="B", start=5, len=1), dict(recap, start=9, len=3), dict(kind="game", start=12, len=2)]
        spans = R.chapter_spans(shots, 14.0)
        self.assertEqual([(s["start"], s["end"]) for s in spans], [(1, 5), (6, 9)])
        self.assertEqual(R.chapter_spans(shots[:2], 5.0), [])

    def test_shot_never_plays_into_a_title_card(self):
        self.assertEqual(R._dodge(10.0, 5.0, [[13.6, 18.4]]), 13.6 - 5.0 - 0.05)   # would run into it: starts earlier
        self.assertEqual(R._dodge(14.3, 3.0, [[13.6, 18.4]]), 14.3)                 # placed on the card on purpose: kept
        self.assertEqual(R._dodge(30.0, 4.0, [[13.6, 18.4]]), 30.0)

    def test_chapter_bar_hides_over_cards(self):
        shots = [dict(kind="game", start=0, len=2), dict(kind="hud", start=2, len=3), dict(kind="game", start=5, len=2)]
        self.assertEqual(R._bar_windows(shots, 0.0, 7.0), [(0.0, 2), (5, 7.0)])

class GuideTests(unittest.TestCase):
    def test_example_guide_parses_with_countdown_money_and_spot(self):
        p = P.read(str(ROOT / "game_launch/example_guide_scenes.csv"))
        self.assertEqual(p["errors"], [])
        self.assertFalse(any("split" in w for w in p["warnings"]))
        shots = [s for ln in p["lines"] for s in ln["shots"]]
        self.assertEqual([s["number"] for s in shots if s["kind"] == "rank"], ["#5", "#4", "#3", "#2", "#1"])
        pay = next(s for s in shots if s["kind"] == "payout")
        self.assertEqual([it["amount"] for it in pay["items"]], [2400, 9000, 15000])
        self.assertEqual(next(s for s in shots if s["kind"] == "spot")["spot"], (0.64, 0.52))
        self.assertEqual(len(next(s for s in shots if s["kind"] == "steps")["items"]), 4)

    def test_guide_rows_complain(self):
        p = P.read(write('A.,steps,,,,,,,,,\nB.,rank,g.mp4,1,,,,,,,\nC.,spot,g.mp4,1,,,,,,,elsewhere\nD.,payout,g.mp4,1,,,,,,,\n'))
        text = "\n".join(p["errors"])
        self.assertIn("steps shot needs game_clip", text)
        self.assertIn("steps needs the steps", text)
        self.assertIn("rank shot needs the entry's name", text)
        self.assertIn("should be x,y", text)
        self.assertIn("payout needs items", text)

    def test_money_and_spot_parsing(self):
        self.assertEqual(P.money("$2,400"), 2400)
        self.assertEqual(P.money("1.2M"), 1200000)
        self.assertIsNone(P.money("a lot"))
        self.assertEqual(P.parse_spot("62%, 41%"), (0.62, 0.41))
        self.assertIsNone(P.parse_spot("150,20"))

    def test_guide_cards_draw(self):
        from game_launch import look as L
        d = Path(tempfile.mkdtemp())
        self.assertEqual(len(L.steps_pngs("How", ["One", "Two a much longer step that has to wrap onto a second line", "Three"],
                                          d, "s")), 3)
        items = [{"label": "Store", "value": "$2400", "amount": 2400.0}, {"label": "Car", "value": "lots", "amount": None}]
        self.assertEqual(len(L.payout_pngs("Money", items, d, "p")), 3)
        L.rank_png("#1", "The casino vault", "Late game", d / "r.png")
        self.assertTrue(all(f.is_file() for f in L.spot_pngs("Here", "Behind the pier", (0.9, 0.1), d, "x")))
        self.assertEqual(L.money_text(1200000), "$1.2M")


if __name__ == "__main__":
    unittest.main()
