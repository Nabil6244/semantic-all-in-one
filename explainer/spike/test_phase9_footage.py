"""Phase 9 tests: real footage through the application's own sources (opt-in). The director only WRITES the reference (a source and a query quoted from the narration, e.g. stock_video:ships at sea);
the application's existing "Get the scenes" step fetches it. Offline, deterministic, no network. usage: python3 -B explainer/spike/test_phase9_footage.py   (from the repository root)"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

from test_director_real_material import synth, run, TEXT_KINDS                       # noqa: E402
from explainer.beats.relevance import beat_tokens, check_plan                        # noqa: E402
from explainer.director import lexicon as LX                                         # noqa: E402

SCRIPT = ("In the sixteenth century Spanish ships crossed the ocean loaded with silver and gold. England was poor and small and left out of the race. "
          "Queen Elizabeth gave tough sea captains a special licence to attack those treasure ships. The pirates sailed from small harbours on the south coast. "
          "Later the company built an army twice the size of the royal army and ruled whole cities. Railways and factories followed the soldiers across the continent. "
          "Millions of workers crowded into the markets and the streets of the new cities. In the end the empire lost almost everything in only a few decades. "
          "Today the old harbours are quiet and the factories are museums.")
SOURCES = ("stock_video", "youtube_video", "flow_video", "stock_image", "flow_image")


def footage_beats(plan):
    return [b for b in plan["beats"] if b["mode"] == "footage" and "footage" in b.get("purpose", "") and b["footage"]["clips"][0]["asset"].split(":")[0] in SOURCES]


class Selection(unittest.TestCase):
    def test_default_has_no_footage_and_is_unchanged(self):
        words, dur = synth(SCRIPT)
        a = run(words, SCRIPT, dur)
        b = run(words, SCRIPT, dur, footage_share=0.0)
        self.assertEqual(footage_beats(a.plan), [])
        self.assertEqual(json.dumps(a.plan, sort_keys=True), json.dumps(b.plan, sort_keys=True))

    def test_footage_is_opt_in_capped_and_spaced(self):
        words, dur = synth(SCRIPT)
        r = run(words, SCRIPT, dur, footage_share=0.35)
        self.assertIsNotNone(r.plan, r.problems)
        kinds = [b["kind"] for b in r.report["selection"]["beats"]]
        self.assertIn("footage", kinds)
        share = sum(b["end"] - b["start"] for b in r.report["selection"]["beats"] if b["kind"] == "footage") / dur
        self.assertLessEqual(share, 0.35 + 1e-6)
        self.assertNotIn(("footage", "footage", "footage"), list(zip(kinds, kinds[1:], kinds[2:])))

    def test_only_beats_that_name_something_you_can_film_become_footage(self):
        words, dur = synth(SCRIPT)
        r = run(words, SCRIPT, dur, footage_share=0.5)
        for b in r.report["selection"]["beats"]:
            if b["kind"] == "footage":
                toks = [t["tok"] for t in beat_tokens(words, b["start"], b["end"])]
                self.assertTrue(set(toks) & LX.CONCRETE, f"{b['id']}: nothing concrete is said: {toks}")
        self.assertTrue(r.report["selection"].get("footage_skipped") is not None)

    def test_a_question_or_a_number_beat_stays_a_board(self):
        s = ("How did a small island end up ruling a quarter of the planet? In 1922 it ruled 458 million people across the whole world. "
             "To understand that we have to go back and ask what happened in the sixteenth century to the ships and the sailors who crossed the sea.")
        words, dur = synth(s)
        r = run(words, s, dur, footage_share=0.6)
        first = r.report["selection"]["beats"][0]
        self.assertNotEqual(first["kind"], "footage", "the opening question is the narrator's board, not a clip")


class Reference(unittest.TestCase):
    def setUp(self):
        self.words, self.dur = synth(SCRIPT)
        self.r = run(self.words, SCRIPT, self.dur, footage_share=0.4)
        self.assertIsNotNone(self.r.plan, self.r.problems)
        self.fb = footage_beats(self.r.plan)
        self.assertTrue(self.fb)

    def test_each_clip_reference_is_a_source_and_a_query_spoken_in_its_own_beat(self):
        for b in self.fb:
            c = b["footage"]["clips"][0]
            src, query = c["asset"].split(":", 1)
            self.assertEqual(src, "stock_video")
            q = [t for t in query.lower().split() if t]
            self.assertTrue(1 <= len(q) <= 4, query)
            toks = {t["tok"] for t in beat_tokens(self.words, b["start"], b["end"])}
            self.assertTrue(set(q) <= toks, f"{b['id']}: {q} is not all spoken inside the beat")
            self.assertFalse(set(q) <= LX.STOP, "a query of function words only")
            self.assertTrue(c["reason"].strip())
            self.assertTrue(b["footage"].get("footage_intent", "").strip())

    def test_the_caption_is_a_hybrid_template_over_the_clip_quoting_the_narration(self):
        from explainer.beats.relevance import find_phrase
        for b in self.fb:
            lays = b.get("layers", [])
            self.assertTrue(lays, f"{b['id']}: the words are not shown")
            tk = beat_tokens(self.words, b["start"], b["end"])
            for l in lays:
                self.assertEqual(l["type"], "template")
                self.assertIn(l.get("kind"), ("typed_caption", "yellow_tag", "year_wipe"))
                self.assertTrue(b["start"] <= l["t"] < b["end"] - 1.0, "it must be readable before the beat ends")
                if l["kind"] == "typed_caption":
                    self.assertIsNotNone(find_phrase(tk, l["text"]), l["text"])

    def test_the_other_sources_can_be_chosen_and_nonsense_is_refused(self):
        for src in ("youtube_video", "flow_video", "stock_image"):
            r = run(self.words, SCRIPT, self.dur, footage_share=0.4, footage_source=src)
            self.assertIsNotNone(r.plan, r.problems)
            self.assertTrue(all(b["footage"]["clips"][0]["asset"].startswith(src + ":") for b in footage_beats(r.plan)), src)
        bad = run(self.words, SCRIPT, self.dur, footage_share=0.4, footage_source="tiktok")
        self.assertIsNone(bad.plan)
        self.assertTrue(any("footage source" in p for p in bad.problems), bad.problems)

    def test_a_still_picture_source_gets_a_slow_zoom(self):
        r = run(self.words, SCRIPT, self.dur, footage_share=0.4, footage_source="stock_image")
        self.assertTrue(all(b["footage"]["clips"][0].get("kenburns") for b in footage_beats(r.plan)))


class Gates(unittest.TestCase):
    def setUp(self):
        self.words, self.dur = synth(SCRIPT)
        self.r = run(self.words, SCRIPT, self.dur, footage_share=0.4)

    def test_the_plan_passes_the_hybrid_validators_and_the_relevance_gate(self):
        self.assertIsNotNone(self.r.plan, self.r.problems)
        self.assertEqual(self.r.problems, [])
        self.assertEqual(self.r.report["hybrid_validate"].get("errors"), [])

    def test_the_plain_relevance_gate_still_refuses_remote_references(self):
        rep = check_plan(self.r.plan, self.words)
        self.assertTrue(any("stock_video" in p for p in rep.problems), "without the opt-in, remote references stay refused")

    def test_a_query_word_that_is_not_spoken_is_a_problem(self):
        plan = json.loads(json.dumps(self.r.plan))
        b = footage_beats(plan)[0]
        b["footage"]["clips"][0]["asset"] = "stock_video:unicorns dancing"
        rep = check_plan(plan, self.words, allow_sources=SOURCES)
        self.assertTrue(any("unicorns" in p for p in rep.problems), rep.problems)

    def test_rows_for_the_visual_plan_appear_only_with_footage(self):
        from hybrid import identity
        from hybrid.plan import HybridPlan
        with_f = identity.row_descriptors(HybridPlan.from_dict(json.loads(json.dumps(self.r.plan))))
        without = identity.row_descriptors(HybridPlan.from_dict(json.loads(json.dumps(run(self.words, SCRIPT, self.dur).plan))))
        self.assertGreaterEqual(len(with_f), len(footage_beats(self.r.plan)))
        self.assertEqual(without, [])

    def test_footage_beats_carry_no_narrator_and_the_plan_is_deterministic(self):
        for b in self.r.report["selection"]["beats"]:
            if b["kind"] == "footage":
                self.assertEqual(self.r.report["beat_details"][b["id"]].get("narrator", "none"), "none")
        again = run(self.words, SCRIPT, self.dur, footage_share=0.4)
        self.assertEqual(json.dumps(self.r.plan, sort_keys=True), json.dumps(again.plan, sort_keys=True))

    def test_the_hybrid_compiler_accepts_it(self):
        from hybrid.compile import compile_plan
        from hybrid.plan import HybridPlan
        c = compile_plan(HybridPlan.from_dict(json.loads(json.dumps(self.r.plan))), base_dir=str(ROOT), validate=False)
        self.assertEqual(c.report.errors, [])


class Settings(unittest.TestCase):
    def test_the_two_settings_are_optional_and_clamped(self):
        from explainer.integration import footage_settings
        self.assertEqual(footage_settings({}), (0.0, "stock_video"))
        self.assertEqual(footage_settings(None), (0.0, "stock_video"))
        self.assertEqual(footage_settings({"explainer_footage_share": "0.25", "explainer_footage_source": "youtube_video"}), (0.25, "youtube_video"))
        self.assertEqual(footage_settings({"explainer_footage_share": 9, "explainer_footage_source": "nonsense"}), (0.6, "stock_video"))
        self.assertEqual(footage_settings({"explainer_footage_share": -1}), (0.0, "stock_video"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
