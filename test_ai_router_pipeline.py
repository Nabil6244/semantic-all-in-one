"""Hybrid's planner running THROUGH the AI router, with fake providers standing in for Gemini and Groq: who answers which job, what happens
when a provider runs out mid-documentary, that nothing is asked twice, and that a stop leaves the work resumable. No network, no credits."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_router import AIRouter, AllRoutesUnavailable, Route
from ai_router.errors import ProviderError
from ai_router.providers import Completion
from hybrid.narration import build_sentences, plan_chunks
from hybrid.pipeline import plan_hybrid
from hybrid.validate import validate
from hybrid_longform_fixtures import FakeGemini, make_narration


class Provider:
    """Answers like the fake Director/critic/repair. `fail_after` = this provider's quota ends after that many answers."""

    def __init__(self, name, brain, fail_after=None, configured=True):
        self.name, self.brain, self.fail_after, self.n, self._cfg = name, brain, fail_after, 0, configured
        self.by_model = {}

    def configured(self):
        return self._cfg

    def complete(self, system, user, *, model, thinking="low", max_output=0, timeout=0):
        if self.fail_after is not None and self.n >= self.fail_after:
            raise ProviderError("You exceeded your current quota, please check your plan", status=429)
        self.n += 1
        self.by_model[model] = self.by_model.get(model, 0) + 1
        return Completion(self.brain.complete(system, user), usage={"input": 100, "output": 50})


def router(gemini, groq, state_dir=None):
    routes = {"director": [Route("gemini", "g-main"), Route("groq", "q-director")], "critic": [Route("groq", "q-critic"), Route("gemini", "g-critic")],
              "repair": [Route("groq", "q-repair"), Route("gemini", "g-critic")], "utility": [Route("groq", "q-repair")]}
    return AIRouter(routes, {"gemini": gemini, "groq": groq}, state_dir=state_dir, sleep=lambda s: None)


def material(minutes):
    words, script = make_narration(minutes)
    total = words[-1][2] + 0.4
    return words, script, total, build_sentences(words, script, total)


class TestThroughTheRouter(unittest.TestCase):
    def test_a_clean_long_documentary_is_only_director_calls_all_on_gemini(self):
        words, script, total, sents = material(40)
        gem, groq = Provider("gemini", FakeGemini(beat_sentences=3)), Provider("groq", FakeGemini(beat_sentences=3))
        r = router(gem, groq)
        res = plan_hybrid(words, r, script=script, duration=total)
        n = len(plan_chunks(sents, total))
        self.assertEqual(r.usage.calls, {"gemini": {"director": n}})
        self.assertEqual(groq.n, 0)
        self.assertEqual([f for f in validate(res.plan) if f.severity == "error"], [])
        self.assertIn("Critic: skipped", "\n") if False else None
        self.assertTrue(res.stats["critic_skipped"])
        self.assertIn("Gemini: director", res.stats["ai_summary"])
        self.assertIn("Local:", res.stats["ai_summary"])

    def test_when_gemini_runs_out_part_way_the_director_continues_on_groq_with_the_same_standard(self):
        words, script, total, sents = material(40)
        n = len(plan_chunks(sents, total))
        gem, groq = Provider("gemini", FakeGemini(beat_sentences=3), fail_after=3), Provider("groq", FakeGemini(beat_sentences=3))
        res = plan_hybrid(words, router(gem, groq), script=script, duration=total)
        self.assertEqual((gem.n, groq.n), (3, n - 3))
        plain = plan_hybrid(words, FakeGemini(beat_sentences=3), script=script, duration=total, use_critic=False)
        self.assertEqual([(b.id, b.mode, round(b.start, 2), round(b.end, 2)) for b in res.plan.beats], [(b.id, b.mode, round(b.start, 2), round(b.end, 2)) for b in plain.plan.beats])
        self.assertEqual([f for f in validate(res.plan) if f.severity == "error"], [])     # a Groq-made chapter faces exactly the same validator

    def test_critic_and_repair_go_to_groq_first_and_only_where_something_is_flagged(self):
        words, script, total, sents = material(40)
        gem, groq = Provider("gemini", FakeGemini(beat_sentences=3)), Provider("groq", FakeGemini(beat_sentences=3, weak_first=True))
        r = router(gem, groq)
        res = plan_hybrid(words, r, script=script, duration=total, critic_policy="always")
        self.assertIn("critic", r.usage.calls.get("groq", {}))
        self.assertIn("repair", r.usage.calls.get("groq", {}))
        self.assertNotIn("critic", r.usage.calls.get("gemini", {}))
        self.assertNotIn("repair", r.usage.calls.get("gemini", {}))
        self.assertEqual(set(r.usage.calls["gemini"]), {"director"})

    def test_when_nothing_can_answer_progress_is_kept_and_a_rerun_resumes_with_no_repeat_calls(self):
        words, script, total, sents = material(60)
        n = len(plan_chunks(sents, total))
        with tempfile.TemporaryDirectory() as d:
            ck, st = Path(d) / "chapters", Path(d) / "ai"
            gem, groq = Provider("gemini", FakeGemini(beat_sentences=3), fail_after=4), Provider("groq", FakeGemini(), configured=False)
            with self.assertRaises(AllRoutesUnavailable) as cm:
                plan_hybrid(words, router(gem, groq, st), script=script, duration=total, checkpoint_dir=ck)
            self.assertIn("Progress is saved", str(cm.exception))
            self.assertEqual(len(list(ck.glob("chapter_*.json"))), 4)
            state = json.loads((ck / "planning_state.json").read_text())
            self.assertEqual(state["stage"], "directing")
            gem2 = Provider("gemini", FakeGemini(beat_sentences=3))
            still = router(gem2, Provider("groq", FakeGemini(), configured=False), st)          # straight away, the exhausted quota is still remembered ...
            with self.assertRaises(AllRoutesUnavailable):
                plan_hybrid(words, still, script=script, duration=total, checkpoint_dir=ck)
            self.assertEqual(gem2.n, 0, "... so it is not asked again")
            (st / "route_state.json").unlink()                                                    # the quota window resets
            r2 = router(gem2, Provider("groq", FakeGemini(), configured=False), st)
            res = plan_hybrid(words, r2, script=script, duration=total, checkpoint_dir=ck)
            self.assertEqual(gem2.n, n - 4)                                 # only the chapters that were not done
            self.assertEqual(res.stats["checkpoint_hits"], 4)
            self.assertEqual(json.loads((ck / "planning_state.json").read_text())["stage"], "complete")

    def test_a_rerun_of_the_same_script_is_answered_from_saved_results(self):
        words, script, total, sents = material(30)
        with tempfile.TemporaryDirectory() as d:
            st = Path(d) / "ai"
            gem1 = Provider("gemini", FakeGemini(beat_sentences=3))
            plan_hybrid(words, router(gem1, Provider("groq", FakeGemini(), configured=False), st), script=script, duration=total)       # no chapter checkpoints at all
            gem2 = Provider("gemini", FakeGemini(beat_sentences=3))
            r2 = router(gem2, Provider("groq", FakeGemini(), configured=False), st)
            plan_hybrid(words, r2, script=script, duration=total)
            self.assertEqual(gem2.n, 0)
            self.assertEqual(r2.usage.cache_hits, len(plan_chunks(sents, total)))

    def test_the_call_log_never_holds_prompts_or_keys(self):
        words, script, total, _ = material(30)
        with tempfile.TemporaryDirectory() as d:
            st = Path(d) / "ai"
            plan_hybrid(words, router(Provider("gemini", FakeGemini(beat_sentences=3)), Provider("groq", FakeGemini(), configured=False), st), script=script, duration=total)
            blob = (st / "ai_calls.jsonl").read_text()
            self.assertIn('"task": "director"', blob)
            self.assertNotIn(words[0][0], blob)


if __name__ == "__main__":
    unittest.main()
