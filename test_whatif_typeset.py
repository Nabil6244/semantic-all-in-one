"""Phase A of the reference-matched What If look (docs/whatif/REFERENCE_MATCH_PLAN.md): the narration's information blocks."""

import re
import unittest

from whatif import narration as nr
from whatif import typeset as ty
from whatif.planner import Shot


def timed(text, t=0.0, step=0.32, pause_every=9):
    out = []
    for i, w in enumerate(text.split()):
        out.append(nr.Word(w, re.sub(r"[^\w'-]", "", w.lower()), t, t + 0.28))
        t += step + (0.5 if (i + 1) % pause_every == 0 else 0.0)
    return out


SAID = ("by then voyager 1 had already crossed the termination shock where the solar wind suddenly slows "
        "all six computers together hold about 70 kilobytes less than one photo on your phone "
        "the spacecraft keeps coasting outward at about 17 kilometers per second through the dark")


class Blocks(unittest.TestCase):
    def setUp(self):
        self.words = timed(SAID)
        self.metrics = nr.extract_metrics(self.words)
        self.dur = self.words[-1].end + 0.5

    def run_on(self, shots):
        layers, notes = [], []
        ty.typeset(shots, layers, self.words, self.metrics, self.dur, notes)
        return layers

    def test_every_word_on_screen_was_said(self):
        layers = self.run_on([Shot(id="s1", start=0.0, end=self.dur, kind="craft")])
        self.assertTrue(layers)
        said = {w.norm for w in self.words} | {"≈"}
        for L in layers:
            text = " ".join(str(L.get(k) or "") for k in ("kicker", "text", "value", "sub")).lower().replace("\n", " ")
            for tok in re.findall(r"[\w'.-]+|≈", text):
                self.assertTrue(tok.strip(".") in said or tok.replace(".", "").isdigit(), (tok, L))

    def test_no_block_over_a_photograph_or_a_clip(self):
        self.assertEqual(self.run_on([Shot(id="s1", start=0.0, end=self.dur, kind="image"), ]), [])

    def test_a_block_never_crosses_a_cut(self):
        shots = [Shot(id="s1", start=0.0, end=6.0, kind="craft"), Shot(id="s2", start=6.0, end=self.dur, kind="globe")]
        for L in self.run_on(shots):
            host = next(s for s in shots if s.start <= L["start"] < s.end)
            self.assertLessEqual(L["end"], host.end)

    def test_the_same_headline_is_not_repeated_within_90_s(self):
        heads = [str(L.get("text") or L.get("value")) for L in self.run_on([Shot(id="s1", start=0.0, end=self.dur, kind="craft")])]
        self.assertEqual(len(heads), len(set(heads)))

    def test_kickers_and_sub_lines_never_start_or_end_on_a_weak_word(self):
        for L in self.run_on([Shot(id="s1", start=0.0, end=self.dur, kind="craft")]):
            for k in ("kicker", "sub"):
                toks = str(L.get(k) or "").lower().split()
                if toks:
                    self.assertNotIn(toks[0], ty._WEAK, L)
                    self.assertNotIn(toks[-1], ty._WEAK, L)


class Sentences(unittest.TestCase):
    def test_a_transcript_without_punctuation_still_has_sentences(self):
        words = timed(" ".join([SAID] * 6), pause_every=12)
        sn = nr.sentences(words)
        self.assertGreater(len(sn), 6)
        self.assertLessEqual(max(b - a + 1 for a, b in sn), nr.SENTENCE_MAX_WORDS)

    def test_a_punctuated_script_is_split_as_before(self):
        words = timed("Voyager left in 1977. It is still going. Nobody expected that.")
        self.assertEqual(len(nr.sentences(words)), 3)


class PlateHeadings(unittest.TestCase):
    def test_a_heading_shows_only_over_a_graphic(self):
        from whatif import compile as wc
        from whatif.planner import ShotPlan

        shots = [Shot(id="s1", start=0, end=6, kind="plate", title="Two routes compared", text="the two routes"),
                 Shot(id="s2", start=6, end=12, kind="plate", title="Ring comparison", text="the rings")]
        layers = [{"type": "tm_bars", "rows": [{"label": "A", "value": 1, "text": "1"}], "start": 6, "end": 12}]
        spec = wc.compile_spec(ShotPlan(shots=shots, layers=layers, duration=12.0), media_dir=None)
        self.assertEqual([s.get("title") for s in spec["shots"]], ["", "Ring comparison"])


if __name__ == "__main__":
    unittest.main()


class TemplateData(unittest.TestCase):
    """Phase B: a template never shows a value or an example list the narration / CSV did not give."""

    def row(self, tid, **cols):
        from whatif import templates as tpl

        return type("Row", (), {"id": tid, "hold": 5.0, "extra": {}, **{c: None for c in tpl.COLUMNS}, **cols})()

    def test_a_missing_headline_value_leaves_the_row_out(self):
        from whatif import templates as tpl

        with self.assertRaises(ValueError) as cm:
            tpl.layer_for(self.row("day_night_strip"), 10.0, 15.0)      # it counted to its default of 12 days (#016)
        self.assertIn("days", str(cm.exception))

    def test_the_planner_concept_templates_keep_their_defaults(self):
        from whatif import templates as tpl

        it = self.row("day_night_strip")
        it._auto = True
        L, _ = tpl.layer_for(it, 10.0, 15.0)
        self.assertEqual(L["template"]["id"], "day_night_strip")

    def test_an_example_list_is_never_shown(self):
        from whatif import templates as tpl

        L, _ = tpl.layer_for(self.row("callout_object", label="Voyager 1"), 10.0, 15.0)
        self.assertEqual(L["slots"].get("callouts"), [])

    def test_a_dish_probe_is_drawn_as_a_probe(self):
        from whatif import templates as tpl

        words = timed("the spacecraft voyager 1 carries a big white dish antenna")
        L, _ = tpl.layer_for(self.row("callout_object", text="DISH=TALKS TO EARTH"), 1.0, 5.0, words)
        self.assertEqual(L["slots"]["object"], "probe")


class CraftIdentity(unittest.TestCase):
    """Phase C: the journey's craft carries its marker; the subject slides right of a left information block."""

    def shots(self, n=3):
        return [{"id": f"s{i}", "kind": "craft", "model": "voyager.glb", "start": i * 6.0, "end": i * 6.0 + 6.0} for i in range(n)]

    def test_the_marker_names_the_craft_the_narration_says(self):
        from whatif import compile as wc

        shots = self.shots()
        wc._identity(shots, [], timed("voyager 1 keeps going and voyager 1 is far " * 4), [])
        self.assertEqual({d.get("marker") for d in shots}, {"VOYAGER 1"})       # voyager.glb is Voyager 1 and 2: never the wrong one

    def test_you_on_board_only_when_the_viewer_is_the_traveller(self):
        from whatif import compile as wc

        shots = self.shots()
        wc._identity(shots, [], timed("you are aboard voyager 1 and your ship is fast you feel it " * 6), [])
        self.assertEqual(shots[0].get("marker"), "YOU\nON BOARD")

    def test_no_marker_while_a_caption_already_names_the_craft(self):
        from whatif import compile as wc

        shots = self.shots()
        wc._identity(shots, [{"type": "tm_caption", "text": "VOYAGER 1", "start": 0.5, "end": 5.0}], timed("voyager 1 " * 10), [])
        self.assertNotIn("marker", shots[0])
        self.assertEqual(shots[1].get("marker"), "VOYAGER 1")

    def test_a_left_block_slides_the_subject_right(self):
        from whatif import compile as wc

        shots = self.shots(1)
        wc._identity(shots, [{"type": "tm_metric", "anchor": "left", "start": 1.0, "end": 5.0}], [], [])
        self.assertEqual(shots[0].get("frame_x"), wc.FRAME_X)


class EvolvingShots(unittest.TestCase):
    """Phase D: one subject is one evolving shot; one number is on screen once; a real photo becomes a card beside its block."""

    def test_neighbouring_shots_of_one_model_become_one_shot(self):
        from whatif import planner

        shots = [Shot(id="a", start=0, end=6, kind="craft", model="voyager.glb"), Shot(id="b", start=6, end=12, kind="craft", model="voyager.glb"),
                 Shot(id="c", start=12, end=18, kind="craft", model="voyager.glb", cam={"dist": 2.0}),       # the CSV asks for a new camera: a cut
                 Shot(id="d", start=18, end=24, kind="globe", texture="2k_saturn.jpg")]
        out = planner.merge_beats(shots, [])
        self.assertEqual([(s.start, s.end) for s in out], [(0, 12), (12, 18), (18, 24)])

    def test_a_merged_shot_never_runs_past_20_s(self):
        from whatif import planner

        shots = [Shot(id=str(i), start=i * 8.0, end=i * 8.0 + 8.0, kind="craft", model="voyager.glb") for i in range(4)]
        self.assertTrue(all(s.length <= planner.EVOLVE_MAX_S for s in planner.merge_beats(shots, [])))

    def test_the_same_number_is_not_shown_twice_at_once(self):
        from whatif import compile as wc

        layers = [{"type": "tm_metric", "value": "124,000", "unit": "KM", "start": 1.0, "end": 5.0},
                  {"type": "tm_caption", "text": "124,000 KM ABOVE SATURN'S CLOUDS", "start": 2.0, "end": 6.0},
                  {"type": "tm_caption", "text": "124,000 KM", "start": 9.0, "end": 12.0}]
        self.assertEqual([L["start"] for L in wc._one_number_at_a_time(layers, [])], [1.0, 9.0])
