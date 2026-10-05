"""Fixing a beat CSV one cell at a time: every problem names its row and column, the app suggests values, and the change is written
back into the file (the original kept once)."""

import tempfile
import unittest
from pathlib import Path

from hybrid import cell_fix
from hybrid.beat_csv import import_beats, plan_from_csv
from hybrid.plan import PlanError
from hybrid.validate import validate

HEAD = "beat,row,vo_anchor,start,end,mode,type,id,place,frame,label,text,format,value_to,anchor,asset,why\n"
TEXT = (HEAD
        + "b1,beat,,0,8,map,,,Pennsylvania,region,,,,,,,a state that looks full\n"
        + "b1,layer,,,,,marker,m1,Pittsburgh,,PITTSBURGH,,,,,,\n"
        + "b2,beat,,8,16,map,,,Great Lakez,region,,,,,,,the lakes\n"
        + "b2,layer,,,,,fill,,Atlantis,,,,,,,,\n"
        + "b2,layer,,,,,stat,,,,,,1.3 MILLION,1.3,br,,\n")


class TestCells(unittest.TestCase):
    def test_a_bad_camera_place_points_to_its_beat_row_and_the_place_column(self):
        plan = plan_from_csv(TEXT)
        cells = [cell_fix.cell_for_finding(TEXT, plan, f) for f in validate(plan) if f.severity == "error"]
        where = {(c.row, c.column) for c in cells if c is not None}
        self.assertIn((4, "place"), where)   # b2's camera place
        self.assertIn((5, "place"), where)   # the fill
        self.assertIn((6, "format"), where)  # a stat format that types its number

    def test_a_place_suggestion_is_a_name_the_atlas_knows_and_the_previous_beats_place(self):
        plan = plan_from_csv(TEXT)
        f = next(f for f in validate(plan) if f.code == "unresolved_place" and "Great Lakez" in f.message)
        tips = cell_fix.suggestions(TEXT, cell_fix.cell_for_finding(TEXT, plan, f))
        self.assertIn("Great Lakes", tips)
        self.assertIn("Pennsylvania", tips)

    def test_a_stat_format_suggestion_puts_the_placeholder_back(self):
        plan = plan_from_csv(TEXT)
        f = next(f for f in validate(plan) if f.code == "stat_format")
        self.assertIn("0.0 MILLION", cell_fix.suggestions(TEXT, cell_fix.cell_for_finding(TEXT, plan, f)))

    def test_changing_the_cells_clears_the_errors(self):
        t = cell_fix.set_cell(TEXT, 4, "place", "Great Lakes")
        t = cell_fix.set_cell(t, 5, "place", "Michigan")
        t = cell_fix.set_cell(t, 6, "format", "0.0 MILLION")
        self.assertEqual([f.message for f in validate(plan_from_csv(t)) if f.severity == "error"], [])

    def test_removing_a_row(self):
        t = cell_fix.remove_row(TEXT, 5)
        self.assertNotIn("Atlantis", t)
        self.assertEqual(len(plan_from_csv(t).beats[1].layers), 1)

    def test_an_import_problem_names_its_row_and_column(self):
        from pakmap.words import estimate_words

        text = ("beat,row,vo_anchor,mode,place,frame,why\n"
                "b1,beat,In Polk,map,Florida,region,a\n"
                "b2,beat,Never said at all,map,Florida,region,b\n")
        words = estimate_words("In Polk the land is flat and wide and green and the story goes on for a while here")
        with self.assertRaises(PlanError) as cm:
            import_beats(text, words, 12.0)
        cell = cell_fix.cell_for_problem(text, cm.exception.problems[0])
        self.assertEqual((cell.row, cell.column, cell.value), (3, "vo_anchor", "Never said at all"))
        cell.value = "the lend is"
        self.assertIn("the land is", [t.lower() for t in cell_fix.suggestions(text, cell, words)])

    def test_the_original_is_kept_once(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "plan.csv"
            p.write_text(TEXT, encoding="utf-8")
            keep = cell_fix.backup(p)
            p.write_text("changed", encoding="utf-8")
            cell_fix.backup(p)
            self.assertEqual(keep.read_text(encoding="utf-8"), TEXT)

    def test_named_regions_the_ai_likes_to_use_are_known(self):
        from pakmap.geo import resolve

        for name in ("Great Lakes", "Rust Belt", "Sahara", "Amazon", "New England", "Appalachia"):
            self.assertEqual(resolve(name, "area").kind, "region", name)

    def test_a_csv_beat_with_a_why_is_not_nagged_for_its_intent(self):
        self.assertFalse([f for f in validate(plan_from_csv(TEXT)) if f.code == "map_no_intent"])


if __name__ == "__main__":
    unittest.main()
