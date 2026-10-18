"""Template graphics over footage (Hybrid Map). A footage beat may carry template layers: drawn above the clip (over_footage), on the narration's own time, leaving
with their beat. Map layers (marker, line, fill, title chip, stat, caption) and graphics that sit on the map or need their own picture stay refused, with the
reason. Plan validation is not relaxed anywhere else: a layer outside its beat is still an error, never silently moved except before its beat starts."""

from __future__ import annotations

import copy
import csv
import io
import unittest

from hybrid.beat_csv import COLUMNS, plan_from_csv
from hybrid.compile import compile_plan, plan_to_rows
from hybrid.local_fix import clamp_layers
from hybrid.plan import Layer, validate_plan
from test_hybrid_layer_timing import _plan


def big(i="b3_big", t=22.0, **kw):
    return Layer(id=i, type="template", t=t, kind="big_number", label="COAL SEAMS", value_to=100.0, format="METRES", **kw)


def with_footage_layers(*layers):
    p = _plan()                       # map 0-10 | map+card 10-20 | footage 20-30 | map+card 30-40
    p.beats[2].layers = list(layers)
    return p


class TestFootageBeatLayers(unittest.TestCase):
    def test_a_template_over_footage_is_valid_and_compiles_above_the_clip_at_its_own_time(self):
        p = with_footage_layers(big(t=22.0))
        self.assertEqual(validate_plan(p), [])
        res = compile_plan(p, validate=False)
        ev = [e for e in res.result.spec["events"] if e["id"] == "b3_big"][0]
        self.assertIs(ev["over_footage"], True)
        self.assertEqual((ev["t_in"], ev["t_out"]), (22.0, 28.0))                 # its own time; its own length (6 s), inside the beat (ends 30)
        self.assertEqual(ev["slots"], {"label": "COAL SEAMS", "value": 100, "unit": "METRES"})

    def test_it_leaves_before_its_footage_ends(self):
        p = with_footage_layers(big(t=27.0, hold=10.0))
        ev = [e for e in compile_plan(p, validate=False).result.spec["events"] if e["id"] == "b3_big"][0]
        self.assertEqual(ev["t_out"], 29.8)                                       # beat end 30 - 0.2

    def test_spoken_in_the_last_words_it_comes_forward_so_it_can_be_read_and_says_so(self):
        p = with_footage_layers(big(t=29.0))
        rows, _lm, notes = plan_to_rows(p)
        row = [r for r in rows if r.layer_id == "b3_big"][0]
        self.assertEqual(row.t_start, 27.8)
        self.assertTrue(any("brought forward to 27.8s" in n for n in notes), notes)

    def test_example_text_of_the_library_is_not_shown(self):
        p = with_footage_layers(big())
        ev = [e for e in compile_plan(p, validate=False).result.spec["events"] if e["id"] == "b3_big"][0]
        self.assertEqual(ev["template"]["slots"]["sub"]["default"], "")           # was "SECOND LARGEST COUNTRY ON EARTH"
        self.assertEqual(ev["template"]["slots"]["unit"]["default"], "KM²" if ev["slots"].get("unit") else "")

    def test_a_graphic_that_sits_on_the_map_is_refused_with_its_reason(self):
        p = with_footage_layers(Layer(id="b3_loc", type="template", t=22.0, kind="location_card", label="X", place="Victoria"))
        problems = validate_plan(p)
        self.assertEqual(len(problems), 1)
        self.assertIn("b3_loc", problems[0])
        self.assertIn("drawn on the map", problems[0])
        self.assertIn("hidden under footage", problems[0])

    def test_map_layers_stay_on_map_beats(self):
        for lay in (Layer(id="mk", type="marker", t=22.0, place="Victoria", label="X"), Layer(id="st", type="stat", t=22.0, value_to=5.0),
                    Layer(id="cp", type="caption", t=22.0, text="HELLO"), Layer(id="ht", type="hud_title", t=22.0, label="TITLE")):
            problems = validate_plan(with_footage_layers(lay))
            self.assertEqual(len(problems), 1, problems)
            self.assertIn("belongs to a map beat", problems[0])

    def test_a_graphic_that_needs_its_own_picture_is_refused(self):
        p = with_footage_layers(Layer(id="b3_img", type="template", t=22.0, kind="photo_leader", label="X"))
        self.assertTrue(any("b3_img" in m and "map" in m for m in validate_plan(p)))
        p = with_footage_layers(Layer(id="b3_fr", type="template", t=22.0, kind="before_after_slider"))      # valid to place; its required slots are missing
        self.assertEqual(validate_plan(p), [])
        _rows, _lm, notes = plan_to_rows(p)                                                               # never a stop: left out, and said
        self.assertTrue(any("b3_fr left out" in n and "before" in n for n in notes), notes)
        self.assertFalse(any(r.layer_id == "b3_fr" for r in _rows))

    def test_timing_rules_are_not_relaxed(self):
        late = validate_plan(with_footage_layers(big(t=31.0)))
        self.assertEqual(len(late), 1)
        self.assertIn("layer b3_big: appears at 31s, outside its footage beat b3 (20-30s)", late[0])
        carried = validate_plan(with_footage_layers(big(until="after_footage")))
        self.assertEqual(len(carried), 1)
        self.assertIn("must leave with its beat", carried[0])
        dup = validate_plan(with_footage_layers(big("x"), big("x", t=24.0)))
        self.assertTrue(any("used more than once" in m for m in dup))

    def test_a_layer_timed_before_its_footage_beat_appears_with_it_and_a_repeat_changes_nothing(self):
        p = with_footage_layers(big(t=18.5))
        self.assertEqual(len(validate_plan(p)), 1)
        done = clamp_layers(p)
        self.assertEqual(len(done), 1)
        self.assertEqual(p.beats[2].layers[0].t, 20.0)
        self.assertEqual(validate_plan(p), [])
        once = copy.deepcopy(p).to_dict()
        self.assertEqual(clamp_layers(p), [])
        self.assertEqual(p.to_dict(), once)

    def test_footage_layers_survive_saving_and_loading(self):
        from hybrid.plan import HybridPlan

        p = with_footage_layers(big())
        again = HybridPlan.from_dict(p.to_dict())
        self.assertEqual([(l.id, l.kind, l.t) for l in again.beats[2].layers], [("b3_big", "big_number", 22.0)])
        self.assertEqual(validate_plan(again), [])


class TestMapBeatsAreUnchanged(unittest.TestCase):
    def test_a_template_on_a_map_beat_is_not_flagged_over_footage(self):
        p = _plan()
        p.beats[1].layers = [big("b2_big", t=12.0)]
        ev = [e for e in compile_plan(p, validate=False).result.spec["events"] if e["id"] == "b2_big"][0]
        self.assertNotIn("over_footage", ev)

    def test_a_map_template_still_works_on_a_map_beat(self):
        p = _plan()
        p.beats[1].layers = [Layer(id="b2_loc", type="template", t=12.0, kind="location_card", label="CAMPERDOWN", place="Victoria")]
        self.assertEqual(validate_plan(p), [])
        ev = [e for e in compile_plan(p, validate=False).result.spec["events"] if e["id"] == "b2_loc"][0]
        self.assertIn("follow", ev)
        self.assertEqual(ev["slots"]["label"], "CAMPERDOWN")

    def test_example_text_is_blanked_on_map_beats_too(self):
        p = _plan()
        p.beats[1].layers = [big("b2_big", t=12.0)]
        ev = [e for e in compile_plan(p, validate=False).result.spec["events"] if e["id"] == "b2_big"][0]
        self.assertEqual(ev["template"]["slots"]["sub"]["default"], "")


class TestBeatCsvWithFootageGraphics(unittest.TestCase):
    def test_a_template_row_under_a_footage_beat_imports_anchored_to_its_words(self):
        words = [(f"w{i}x", i * 0.5, i * 0.5 + 0.4) for i in range(80)]

        def row(**k):
            return [k.get(c, "") for c in COLUMNS]

        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(COLUMNS)
        text = lambda a, b: " ".join(f"w{i}x" for i in range(a, b))      # noqa: E731
        w.writerow(row(beat="b1", row="beat", vo_anchor="w0x w1x w2x", mode="map", place="Victoria", frame="region", text=text(0, 10), why="x"))
        w.writerow(row(beat="b2", row="beat", vo_anchor="w10x w11x w12x", mode="footage", text=text(10, 30), why="salt crust"))
        w.writerow(row(beat="b2", row="clip", asset="stock_video:salt crust"))
        w.writerow(row(beat="b2", row="layer", vo_anchor="w20x w21x", type="template", id="b2_big", kind="big_number", label="COAL SEAMS", value_to="100", format="METRES"))
        w.writerow(row(beat="b3", row="beat", vo_anchor="w30x w31x w32x", mode="map", place="Victoria", frame="region", text=text(30, 40)))
        notes = []
        plan = plan_from_csv(out.getvalue(), words, 40.0, notes=notes)
        lay = plan.beats[1].layers[0]
        self.assertEqual((plan.beats[1].mode, lay.kind, lay.t), ("footage", "big_number", 10.0))      # w20x is spoken at 10.0 s: its own words, not the beat's start
        self.assertEqual(validate_plan(plan), [])


if __name__ == "__main__":
    unittest.main()
