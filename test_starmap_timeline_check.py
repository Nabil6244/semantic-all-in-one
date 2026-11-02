"""The finished plan's rules (starmap/timeline_check.py): checked and repaired before render, from plan arithmetic alone."""

import time
import unittest
from unittest import mock

from starmap import timeline_check as tc


def spec(layers=(), footage=(), duration=60.0):
    return {"duration": duration, "layers": [dict(L) for L in layers], "footage": [dict(f) for f in footage], "shots": []}


class Rules(unittest.TestCase):
    def test_a_plate_whose_number_was_removed_goes_and_one_drawn_late_is_trimmed(self):
        """Project #001 0:25: declutter removed "2,800 LIGHT-DAYS" and left its plate (5 s of blank navy); at 2:49 a section diagram
        arrived 3.5 s into its plate."""
        s = spec([{"type": "cinema_plate", "start": 24.58, "end": 29.58},
                  {"type": "tm_caption", "text": "NOT HIDDEN AT", "start": 26.9, "end": 30.9},
                  {"type": "cinema_plate", "start": 169.44, "end": 175.44},
                  {"type": "tm_section", "start": 172.92, "end": 175.44},
                  {"type": "cinema_plate", "start": 40.0, "end": 45.0},
                  {"type": "tm_metric", "value": "4", "start": 40.0, "end": 45.0}], duration=200.0)
        self.assertEqual(sorted(i["kind"] for i in tc.check(s)), ["blank_plate", "blank_plate"])
        notes = []
        tc.enforce(s, notes)
        plates = [(L["start"], L["end"]) for L in s["layers"] if L["type"] == "cinema_plate"]
        self.assertEqual(plates, [(172.92, 175.44), (40.0, 45.0)])
        self.assertIn("tm_caption", [L["type"] for L in s["layers"]], "the caption stays, on the map")
        self.assertEqual(s["shots"], [{"start": 172.92, "end": 175.44, "kind": "plate"}, {"start": 40.0, "end": 45.0, "kind": "plate"}])
        self.assertEqual(tc.check(s), [])
        self.assertTrue(any("plate" in n for n in notes))

    def test_footage_never_overlaps_nor_runs_past_the_end(self):
        s = spec(footage=[{"id": "b29_1", "start": 283.16, "end": 289.16}, {"id": "b30_1", "start": 288.12, "end": 294.12},
                          {"id": "b31_1", "start": 298.0, "end": 305.0}], duration=300.0)
        self.assertEqual(sorted(i["kind"] for i in tc.check(s)), ["footage_overlap", "footage_past_end"])
        tc.enforce(s, [])
        self.assertEqual([(f["start"], f["end"]) for f in s["footage"]], [(283.16, 288.12), (288.12, 294.12), (298.0, 300.0)])

    def test_same_date_jumps_flashes_and_timeless_layers_go(self):
        s = spec([{"type": "time_jump", "text": "15 NOV 2026 → 15 NOV 2026 · TODAY", "start": 26.45, "end": 28.7},
                  {"type": "time_jump", "text": "1977 → 2026", "start": 30.0, "end": 32.0},
                  {"type": "tm_title", "line2": "X", "start": 0.0, "end": 0.59},
                  {"type": "tm_caption", "text": "OK", "start": 5.0, "end": 9.0},
                  {"type": "stat_chip", "start": 12.0, "end": 11.5}])
        tc.enforce(s, [])
        self.assertEqual([(L["type"], L.get("text")) for L in s["layers"]], [("time_jump", "1977 → 2026"), ("tm_caption", "OK")])

    def test_it_costs_milliseconds_on_a_long_video(self):
        layers = [{"type": "tm_caption", "text": "x", "start": i * 2.0, "end": i * 2.0 + 3} for i in range(1500)]
        layers += [{"type": "cinema_plate", "start": i * 9.0, "end": i * 9.0 + 4} for i in range(300)]
        layers += [{"type": "tm_metric", "start": i * 9.0, "end": i * 9.0 + 4} for i in range(300)]
        s = spec(layers, [{"id": f"f{i}", "start": i * 5.0, "end": i * 5.0 + 4} for i in range(400)], duration=3000.0)
        t = time.perf_counter()
        tc.enforce(s, [])
        self.assertLess(time.perf_counter() - t, 0.5)


class EmptyGlideCuts(unittest.TestCase):
    def test_an_empty_glide_into_a_new_subject_is_marked_and_repaired_by_a_cut(self):
        """Project #001: Wolf 359 <-> the Sun glided across 7.9 light-years, 4 s of black each time, five times."""
        from starmap import repair

        sp = {"camera": {"start": {"target": "sun"}, "moves": [{"t": 446.94, "dur": 4.1, "to": {"target": "wolf359"}},
                                                              {"t": 451.0, "dur": 3.9, "to": {"target": "wolf359"}}]},
              "starmap": {"beat_times": [{"id": "b47", "start": 446.94, "end": 461.4}]}}
        found = {"issues": [{"kind": "empty", "t0": 447.0, "t1": 451.2, "beat": "b47", "detail": "the content spans 0% of the frame"}]}
        with mock.patch.object(repair, "run_audit", return_value=found):
            got = repair._issues(sp, "node")
        self.assertTrue(got[0].get("in_glide"))
        self.assertEqual(repair._remedies(got[0], False)[0], {"cut": True})

    def test_a_cut_repair_makes_the_beat_cut_in(self):
        from starmap import Catalog, compile_plan, read_plan
        from test_starmap_beats import csv_of

        said = "the sun sits at the centre of the solar system far away is jupiter the giant planet with its moons and storms"
        words = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(said.split())]
        text = csv_of({"beat": "b1", "row": "beat", "vo_anchor": "the sun sits", "mode": "map", "place": "sun", "frame": "inner"},
                      {"beat": "b2", "row": "beat", "vo_anchor": "far away is", "mode": "map", "place": "jupiter", "frame": "body"})
        plan = read_plan(text, words)
        b2 = plan.beats[1].start
        glide = [m for m in compile_plan(plan, Catalog()).spec["camera"]["moves"] if abs(m["t"] - b2) < 0.05]
        cut = [m for m in compile_plan(plan, Catalog(), repairs={"b2": {"cut": True}}).spec["camera"]["moves"] if abs(m["t"] - b2) < 0.05]
        self.assertGreater(glide[0]["dur"], 0.5)
        self.assertEqual(cut[0]["dur"], 0.0)


if __name__ == "__main__":
    unittest.main()
