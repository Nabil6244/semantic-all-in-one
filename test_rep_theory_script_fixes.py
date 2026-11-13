"""Rules added 2026-11-12 from the tendon-holds script audit, checked on synthetic sentences (never on that script):
hyphen-number names kept whole, a sentence's result number picked over a scene-setting count, named tiers ("Tier 1, Starter Cable:") as one result board,
the script bible finding "Movement number one is ...", "the third movement: ...", a paired move after a colon and a drill named before its colon."""
import unittest

from reptheory import bible as BB, narrative as N, planner as P, variety as V


def _ws(text, t0=0.0):
    out = []
    for i, tok in enumerate(text.split()):
        core = tok.strip(".,;:!?"); out.append({"w": core.lower(), "p": tok[len(core):], "t0": t0 + i * 0.4, "t1": t0 + i * 0.4 + 0.35})
    return out


class Labels(unittest.TestCase):
    def test_key_phrase_keeps_a_number_joined_by_a_hyphen(self):
        self.assertNotEqual(N.key_phrase("step two is the 45-second wall press")[0], "SECOND WALL PRESS")

    def test_a_cut_number_word_is_shown_whole(self):
        ws = _ws("drill one is the 7-minute ladder walk,")
        self.assertEqual(P._hyphen_whole("MINUTE LADDER WALK", ws), "7-MINUTE LADDER WALK")

    def test_a_label_ending_on_a_preposition_is_mended(self):
        self.assertNotIn(P._mend("JOG LIGHTLY AROUND", "or jog lightly around the block.", P.LABELS).split()[-1:], [["AROUND"]])


class Numbers(unittest.TestCase):
    def test_the_result_beats_the_count_that_sets_the_scene(self):
        n = V.result_number("in a trial across 12 cities, walkers had 35% fewer falls and roughly 40% lower risk")
        self.assertEqual(n["unit"], "%")

    def test_a_hyphen_number_names_a_thing_not_a_result(self):
        self.assertIsNone(V.result_number("hold the 90-degree bend"))


class NamedTiers(unittest.TestCase):
    def test_tiers_said_one_per_sentence_make_one_board(self):
        texts = ["Level 1, Paper Knees: under 5 squats.", "Level 2, Oak Legs: 10 to 20 squats.", "Level 3, Steel Frame: 30 squats or more."]
        scenes = [{"no": i + 1, "text": t, "start": i * 4.0, "end": i * 4.0 + 3.8, "words": _ws(t, i * 4.0), "decisions": [], "kind": "callout"} for i, t in enumerate(texts)]
        self.assertEqual(V.bands_across(scenes), 3)
        self.assertEqual([x["text"] for x in scenes[0]["band_card"]["tiers"]], ["PAPER KNEES", "OAK LEGS", "STEEL FRAME"])


class Bible(unittest.TestCase):
    def test_movements_paired_moves_and_named_drills_are_sections(self):
        script = ("Movement number one is the 2-arm rope pull, and it trains the grip. Loop a rope over a door handle and lean back. "
                  "That brings us to the second movement: the bench dip. Sit on the edge of a bench and lower yourself. "
                  "Movement number three pairs two holds: the knee lock for your legs, and the toe press for your feet. Stand on one leg and lock the knee. "
                  "Then step onto a stair for the slow toe press. Lift your heels and lower them over four seconds. "
                  "For your arms (The Towel Snap): grab a towel and flick it hard. "
                  "Here is how all three movements fit into your week.")
        scenes = [{"text": s, "decisions": []} for _a, _b, s in BB.split_sentences(script)]
        names = [s["name"] for s in BB.build(scenes)["sections"]]
        for want in ("2-arm rope pull", "bench dip", "knee lock", "toe press", "towel snap"):
            self.assertTrue(any(want in n for n in names), f"{want} not in {names}")
        self.assertFalse(any(n.startswith("seconds") for n in names))

    def test_transcript_text_without_colons_or_hyphens(self):
        rows = ["movement number three pairs two holds that need no gear the long bridge for your hips and the slow toe press for your feet.",
                "lie on your back and lift your hips.", "then step onto a stair for the slow single leg toe press.", "lift your heels and lower them.",
                "for your arms and wrists the towel snap grab a towel and flick it hard."]
        names = [s["name"] for s in BB.build([{"text": t} for t in rows])["sections"]]
        for want in ("long bridge", "slow toe press", "towel snap"):
            self.assertIn(want, names)


if __name__ == "__main__":
    unittest.main()
