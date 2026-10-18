"""Hybrid Map: a layer is timed by the narrator's words, a beat by its own start. The two must never disagree (a layer under footage or before its
map beat stops the plan compiling). The beat CSV import is where they are made; the safety net behind it is hybrid.local_fix.clamp_layers, shared
by Generate and Check plan. The b27 / b71 cases are the two layers of a real 16-minute plan that stopped Generate."""

from __future__ import annotations

import copy
import csv
import io
import unittest

from hybrid.app_integration import check_plan, visual_dicts
from hybrid.beat_csv import COLUMNS, plan_from_csv
from hybrid.compile import HybridCompileError, plan_to_rows
from hybrid.local_fix import clamp_layers
from hybrid.plan import Beat, CameraStep, Clip, HybridPlan, Layer, Support, validate_plan


def _plan(layers_m2=(), layers_m3=(), m2=(10.0, 20.0), f=(20.0, 30.0), m3=(30.0, 40.0)) -> HybridPlan:
    """map 0-10 | map+card 10-20 | footage 20-30 | map+card 30-40."""
    b1 = Beat(id="b1", mode="map", start=0.0, end=m2[0], geo_intent="the region", camera=[CameraStep(action="start", place="Victoria", frame="region", t=0.0)])
    b2 = Beat(id="b2", mode="map_footage", start=m2[0], end=m2[1], layers=list(layers_m2), geo_intent="the lakes",
              support=Support(asset="stock_image:crater lake", t=m2[0] + 1.0, label="LAKE", hold=3.0))
    b3 = Beat(id="b3", mode="footage", start=f[0], end=f[1], footage_intent="salt crust", purpose="the crust", clips=[Clip(asset="stock_video:salt crust")])
    b4 = Beat(id="b4", mode="map_footage", start=m3[0], end=m3[1], layers=list(layers_m3), geo_intent="the salt lake",
              support=Support(asset="stock_image:salt lake", t=m3[0] + 1.0, label="TYRRELL", hold=3.0))
    return HybridPlan(duration=m3[1], beats=[b1, b2, b3, b4])


def _marker(i, t, **kw):
    return Layer(id=i, type="marker", t=t, place="-38.25,143.10", label="X", role="subject", **kw)


class TestPlanLevel(unittest.TestCase):
    def test_baseline_plan_is_valid(self):
        self.assertEqual(validate_plan(_plan([_marker("m", 12.0)])), [])

    def test_1_a_layer_before_its_beat_appears_with_the_beat_and_says_so(self):
        plan = _plan([_marker("b2_marker1", 8.5)])
        problems = validate_plan(plan)
        self.assertTrue(any("b2_marker1" in p and "outside its map beat" in p for p in problems), problems)
        done = clamp_layers(plan)
        self.assertEqual(plan.beats[1].layers[0].t, 10.0)
        self.assertEqual(len(done), 1)
        self.assertIn("b2_marker1", done[0])
        self.assertIn("8.5s", done[0])
        self.assertEqual(validate_plan(plan), [])

    def test_2_a_layer_inside_its_beat_is_untouched(self):
        plan = _plan([_marker("a", 13.37)])
        self.assertEqual(clamp_layers(plan), [])
        self.assertEqual(plan.beats[1].layers[0].t, 13.37)

    def test_3_a_layer_exactly_at_the_beat_start_is_untouched(self):
        plan = _plan([_marker("a", 10.0)])
        self.assertEqual(clamp_layers(plan), [])
        self.assertEqual(plan.beats[1].layers[0].t, 10.0)
        self.assertEqual(validate_plan(plan), [])

    def test_4_a_layer_after_its_beat_ends_is_never_pulled_back_and_the_error_names_it(self):
        plan = _plan([_marker("late", 21.5)])      # belongs to the footage beat's time: a wrong beat only a person can decide
        self.assertEqual(clamp_layers(plan), [])
        self.assertEqual(plan.beats[1].layers[0].t, 21.5)
        problems = validate_plan(plan)
        self.assertEqual(len(problems), 1)
        self.assertIn("layer late: appears at 21.5s, outside its map beat b2 (10-20s)", problems[0])
        with self.assertRaises(HybridCompileError) as ctx:
            plan_to_rows(plan)
        self.assertIn("late", str(ctx.exception))

    def test_5_several_layers_in_one_beat_move_only_when_they_are_early(self):
        plan = _plan([_marker("early1", 7.0), _marker("ok", 14.0), _marker("early2", 9.9), _marker("edge", 10.0)])
        done = clamp_layers(plan)
        got = {l.id: l.t for l in plan.beats[1].layers}
        self.assertEqual(got, {"early1": 10.0, "ok": 14.0, "early2": 10.0, "edge": 10.0})
        self.assertEqual(len(done), 2)
        self.assertEqual(validate_plan(plan), [])

    def test_6_a_valid_plan_is_unchanged(self):
        plan = _plan([_marker("a", 11.0), _marker("b", 15.0)], [_marker("c", 31.0)])
        before = copy.deepcopy(plan)
        self.assertEqual(clamp_layers(plan), [])
        self.assertEqual(plan.to_dict(), before.to_dict())

    def test_8_repeating_does_not_shift_anything(self):
        plan = _plan([_marker("early", 6.0)])
        self.assertEqual(len(clamp_layers(plan)), 1)
        once = copy.deepcopy(plan).to_dict()
        for _ in range(3):
            self.assertEqual(clamp_layers(plan), [])
        self.assertEqual(plan.to_dict(), once)

    def test_a_layer_never_crosses_into_footage(self):
        plan = _plan([_marker("a", 8.0)], [_marker("z", 28.0)])      # z's words fall in the footage beat's time, before its own map beat starts
        clamp_layers(plan)
        self.assertEqual(plan.beats[3].layers[0].t, 30.0)            # it waits for its own map beat; the footage beat never receives a layer
        self.assertEqual(plan.beats[2].layers, [])
        self.assertEqual(validate_plan(plan), [])


class TestGenerateAndCheckPlanShareTheRepair(unittest.TestCase):
    def test_7_check_plan_repairs_exactly_as_generate_does(self):
        a, b = _plan([_marker("early", 8.0)]), _plan([_marker("early", 8.0)])
        clamp_layers(a)                                   # Generate's call
        text, ok = check_plan(b, engine=False)            # Check plan's call
        self.assertTrue(ok, text)
        self.assertEqual(a.beats[1].layers[0].t, b.beats[1].layers[0].t)
        self.assertEqual(b.beats[1].layers[0].t, 10.0)
        self.assertIn("note: b2: marker early is timed at 8s, before its beat starts", text)

    def test_9_an_invalid_plan_gives_an_actionable_message_and_never_raises(self):
        plan = _plan([_marker("late", 25.0)])
        text, ok = check_plan(plan, engine=False)
        self.assertFalse(ok)
        self.assertIn("ERROR: layer late: appears at 25s, outside its map beat b2 (10-20s)", text)
        self.assertIn("Errors must be fixed before rendering.", text)
        self.assertEqual(visual_dicts(plan), [])      # the Visual Plan table is empty for a plan that does not compile, not a crash


# ---- the source: how the beat CSV import times a beat and the layers copied from its text ------------------------------------------------
def _words(n=80, misheard=(), step=0.5):
    return [("zzz" if i in misheard else f"w{i}x", i * step, i * step + 0.4) for i in range(n)]


def _text(a, b):
    return " ".join(f"w{i}x" for i in range(a, b))


def _csv(rows):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(COLUMNS)
    for r in rows:
        w.writerow([r.get(c, "") for c in COLUMNS])
    return out.getvalue()


def _beat(bid, anchor, text, mode="map"):
    return dict(beat=bid, row="beat", vo_anchor=anchor, mode=mode, place="Victoria", frame="region", text=text)


def _layer(bid, anchor, lid, t=""):
    return dict(beat=bid, row="layer", vo_anchor=anchor, type="marker", id=lid, place="-38.25,143.10", label="X", role="subject", t=t)


class TestImportSource(unittest.TestCase):
    def test_a_beat_spread_between_its_neighbours_starts_where_its_own_layer_is_heard(self):
        """The b27 case. The beat's own words are misheard, so its start is an estimate and keep_in_order spreads it evenly between its neighbours
        (halfway between b1 and b3: 5.0 s). Its layer's words ARE heard, at 4.0 s. The layer cannot come before the beat it was copied from, so the
        beat starts at 4.0 s, where its own words are spoken, and the layer is in sync."""
        words = _words(60, misheard={9})
        rows = [_beat("b1", "w0x w1x w2x", _text(0, 8)),
                _beat("b2", "w8x w9x", _text(8, 20)),                  # w9x misheard and a 2-word anchor: no fallback, estimate 4.0 -> spread 5.0
                _layer("b2", "w8x", "b2_marker1"),
                _beat("b3", "w20x w21x w22x", _text(20, 30))]
        notes = []
        plan = plan_from_csv(_csv(rows), words, 30.0, notes=notes)
        b1, b2, b3 = plan.beats
        self.assertTrue(any("heard out of order" in n and "starts at 5.0s" in n for n in notes), notes)   # the guess that caused the mismatch
        self.assertEqual(b2.layers[0].t, 4.0)                  # the voice time of the layer, never delayed
        self.assertEqual(b2.start, 4.0)                        # the beat boundary was corrected, not the layer
        self.assertEqual(b1.end, 4.0)
        self.assertEqual(b3.start, 10.0)                       # heard beats do not move
        self.assertTrue(any("its start was a guess (5.0s)" in n and "heard at 4.0s" in n for n in notes), notes)
        self.assertEqual(validate_plan(plan), [])

    def test_a_beat_after_footage_is_corrected_too_when_the_footage_end_was_only_a_guess(self):
        """The b71 case. The footage beat ends where the next beat's guessed start is, so that end is a guess as well: the layer's heard time wins."""
        words = _words(80, misheard={21})
        rows = [_beat("b1", "w0x w1x w2x", _text(0, 10)),
                dict(beat="b2", row="beat", vo_anchor="w10x w11x w12x", mode="footage", text=_text(10, 20)),
                dict(beat="b2", row="clip", asset="stock_video:salt crust"),
                _beat("b3", "w20x w21x", _text(20, 30)),                # w21x misheard: estimated, spread halfway between b2 (5.0) and b4 (20.0) = 12.5
                _layer("b3", "w22x", "b3_zone_label1"),                 # heard at 11.0
                _beat("b4", "w40x w41x w42x", _text(40, 50))]
        notes = []
        plan = plan_from_csv(_csv(rows), words, 40.0, notes=notes)
        b2, b3 = plan.beats[1], plan.beats[2]
        self.assertEqual(b2.mode, "footage")
        self.assertEqual(b3.layers[0].t, 11.0)
        self.assertEqual(b3.start, 11.0)
        self.assertEqual(b2.end, 11.0)
        self.assertEqual(validate_plan(plan), [])

    def test_a_heard_beat_start_is_a_measurement_and_is_never_pulled(self):
        words = _words(60)
        rows = [_beat("b1", "w0x w1x w2x", _text(0, 10)),
                _beat("b2", "w10x w11x w12x", _text(10, 20)),
                _layer("b2", "w12x w13x w14x", "b2_marker1"),
                _beat("b3", "w20x w21x w22x", _text(20, 30))]
        notes = []
        plan = plan_from_csv(_csv(rows), words, 30.0, notes=notes)
        self.assertEqual([(b.start, b.end) for b in plan.beats], [(0.0, 5.0), (5.0, 10.0), (10.0, 30.0)])
        self.assertEqual(plan.beats[1].layers[0].t, 6.0)
        self.assertFalse(any("guess" in n for n in notes), notes)

    def test_there_is_no_room_to_pull_so_the_layer_waits_for_its_beat_and_the_note_says_so(self):
        """The beat before keeps at least MIN_PULL_BEAT_S: a layer heard 0.5 s after that beat starts cannot take the boundary, so it appears with its beat."""
        words = _words(60, misheard={9})
        rows = [_beat("b1", "w0x w1x w2x", _text(0, 1)),               # b1 runs 0 - 5.0 once b2 is placed
                _beat("b2", "w8x w9x", _text(1, 20)),
                _layer("b2", "w1x", "b2_marker1"),                      # heard at 0.5 s: before the beat, closer than 1 s to b1's start
                _beat("b3", "w20x w21x w22x", _text(20, 30))]
        notes = []
        plan = plan_from_csv(_csv(rows), words, 30.0, notes=notes)
        b2 = plan.beats[1]
        self.assertEqual(b2.start, 5.0)                                 # unchanged
        self.assertEqual(b2.layers[0].t, 5.0)                           # waits for its beat
        self.assertTrue(any("words are spoken at 0.5s, outside beat b2" in n for n in notes), notes)
        self.assertEqual(validate_plan(plan), [])

    def test_a_layer_whose_words_are_not_heard_follows_the_beats_final_start(self):
        """The second half of the b27 bug. 'It appears with its beat' used the start the beat had while the CSV was being read; the later spread moved
        the beat and left the layer stranded before it, and the plan stopped compiling."""
        words = _words(60)
        rows = [_beat("b1", "w0x w1x w2x", _text(0, 30)),               # claims 30 words before b2: the estimate (15 s) lands past b3 (10 s)
                _beat("b2", "nowhere spoken here", _text(10, 20)),
                _layer("b2", "also not spoken", "b2_marker1"),
                _beat("b3", "w20x w21x w22x", _text(20, 30))]
        notes = []
        plan = plan_from_csv(_csv(rows), words, 30.0, notes=notes)
        b2 = plan.beats[1]
        self.assertEqual(b2.start, 5.0)                                 # spread between b1 (0) and b3 (10)
        self.assertEqual(b2.layers[0].t, 5.0)                           # not the 15 s the beat had when the row was read
        self.assertEqual(validate_plan(plan), [])

    def test_10_the_real_plan_cases_with_their_real_numbers(self):
        """b27_marker1 (voice 246.56 s) and b71_zone_label1 (voice 626.24 s) in the plan that stopped Generate, repaired by the safety net alone."""
        plan = _plan_real()
        b27, b71 = plan.beats[2], plan.beats[4]
        self.assertEqual((b27.start, b27.layers[0].t, b71.start, b71.layers[0].t), (248.7, 246.56, 626.56, 626.24))
        self.assertEqual(len(validate_plan(plan)), 2)
        done = clamp_layers(plan)
        self.assertEqual((b27.layers[0].t, b27.layers[1].t, b71.layers[0].t), (248.7, 248.7, 626.56))
        self.assertEqual(len(done), 2)
        self.assertEqual(validate_plan(plan), [])
        self.assertEqual(clamp_layers(plan), [])


def _plan_real() -> HybridPlan:
    b25 = Beat(id="b25", mode="map", start=0.0, end=238.76, geo_intent="Victoria", camera=[CameraStep(action="start", place="Victoria", frame="region", t=0.0)])
    b26 = Beat(id="b26", mode="map", start=238.76, end=248.7, geo_intent="Camperdown")
    b27 = Beat(id="b27", mode="map_footage", start=248.7, end=258.64, geo_intent="two craters",
               layers=[Layer(id="b27_marker1", type="marker", t=246.56, place="-38.25,143.10", label="BULLEN MERRI", role="subject"),
                       Layer(id="b27_marker2", type="marker", t=248.7, place="-38.22,143.10", label="GNOTUK", role="featured", hold=9.0)],
               support=Support(asset="stock_image:two crater lakes", t=249.72, label="TWO CRATERS"))
    b70 = Beat(id="b70", mode="footage", start=258.64, end=626.56, footage_intent="salt", purpose="salt", clips=[Clip(asset="stock_video:salt crust")])
    b71 = Beat(id="b71", mode="map_footage", start=626.56, end=638.1, geo_intent="the country",
               layers=[Layer(id="b71_zone_label1", type="zone_label", t=626.24, place="-35.6,142.6", label="WEMBA WEMBA AND WERGAIA COUNTRY")],
               support=Support(asset="stock_image:person on a salt lake", t=632.26, label="LAKE TYRRELL"))
    return HybridPlan(duration=638.1, beats=[b25, b26, b27, b70, b71])


if __name__ == "__main__":
    unittest.main()
