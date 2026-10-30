"""Semantic Intelligence Engine: core (cache, batches, modes) and the scene-cached editorial reasoner. Fake LLM, no network."""
import copy, json, tempfile, threading, time, unittest
from pathlib import Path

import editorial
from editorial.persistence import load_editorial_plan
from editorial import reasoner as R
from semantic_intel import core
from semantic_intel.editorial import SceneCachedEditorialReasoner

PLAN047 = Path.home() / "Downloads/VideoGenerator/Video_2026-10-30_047_ff/state/editorial_plan.json"
TEMPLATE = {"visual_role": "context", "visual_strategy": "single", "evidence_level": "medium", "shot_strategy": "single", "pacing": "normal",
            "confidence": 0.9, "emotional_state": "curiosity", "primary_claim": "x", "viewer_goal": "y"}


def make_plan(n=40):
    scenes = []
    for i in range(1, n + 1):
        scenes.append({"scene_number": str(i), "start": i * 4.0, "end": i * 4.0 + 4.0, "duration": 4.0, "narration_excerpt": f"narration number {i} about topic {i}",
                       "purpose": "context", "attention_score": 0.5, "importance": "medium", "asset_type_intent": "image", "camera_style": "static",
                       "visual_variety_key": "k", "visual_goal": "", "visual_description": "", "visual_treatment": ""})
    return editorial.EditorialPlan.from_dict({"version": 1, "audio_key": "a", "settings_key": "s", "audio_end": n * 4.0, "scenes": scenes})


class FakeLLM:
    """Answers every beat of a request; counts calls; can fail or truncate chosen requests."""
    def __init__(self, fail_scenes=(), truncate_over=None, delay=0.0):
        self.calls, self.fail_scenes, self.truncate_over, self.delay = [], set(fail_scenes), truncate_over, delay
        self.live = self.peak = 0
        self.lock = threading.Lock()

    def complete(self, system, user, **kw):
        beats = json.loads(user.split("\n\n", 1)[1])["beats"]
        ids = [b["scene_number"] for b in beats]
        with self.lock:
            self.calls.append(ids); self.live += 1; self.peak = max(self.peak, self.live)
        try:
            time.sleep(self.delay)
            if self.fail_scenes & set(ids):
                raise RuntimeError("busy")
            if self.truncate_over and len(ids) > self.truncate_over:
                return '{"intents":[{"scene_number":"1","visual_role":"con'   # cut off mid-JSON
            return json.dumps({"intents": [dict(TEMPLATE, scene_number=i) for i in ids]})
        finally:
            with self.lock:
                self.live -= 1


def reasoner(llm, cache_dir, **kw):
    return SceneCachedEditorialReasoner({}, cache_dir=cache_dir, llm_factory=lambda: llm, sleep=lambda s: None, **kw)


class CoreTests(unittest.TestCase):
    def test_modes_and_keys(self):
        self.assertEqual(core.ai_mode({}), "auto")
        self.assertEqual(core.ai_mode({"ai_planning": "OFF"}), "off")
        self.assertEqual(core.ai_mode({"ai_planning": "bogus"}), "auto")
        self.assertFalse(core.ai_allowed({"ai_planning": "off", "gemini_api_key": "k"}, "ambience"))
        self.assertFalse(core.ai_allowed({"editorial_ai": False, "gemini_api_key": "k"}, "editorial"))
        self.assertTrue(core.ai_allowed({"gemini_api_key": "k"}, "editorial"))
        self.assertEqual(core.stable_key("a", {"b": 1, "c": 2}), core.stable_key("a", {"c": 2, "b": 1}))

    def test_missing_key_is_offline(self):
        import os
        old = os.environ.pop("GEMINI_API_KEY", None)
        try:
            self.assertFalse(core.ai_allowed({}, "editorial"))
        finally:
            if old: os.environ["GEMINI_API_KEY"] = old

    def test_cache_roundtrip_and_atomic(self):
        d = Path(tempfile.mkdtemp()) / "c.json"
        c = core.DecisionCache(d); c.put("k", {"a": 1}); c.put("none", None); c.flush()
        c2 = core.DecisionCache(d)
        self.assertEqual(c2.get("k"), {"a": 1}); self.assertTrue(c2.has("none")); self.assertIsNone(c2.get("none"))
        d.write_text("{broken", encoding="utf-8"); self.assertEqual(len(core.DecisionCache(d)), 0)

    def test_batches_bounded_independent_ordered(self):
        live = peak = 0; lock = threading.Lock(); tries = {}
        def call(b):
            nonlocal live, peak
            with lock: live += 1; peak = max(peak, live)
            time.sleep(0.03)
            with lock: live -= 1; tries[b] = tries.get(b, 0) + 1
            if b == 3: raise RuntimeError("always")
            if b == 5 and tries[b] < 2: raise RuntimeError("once")
            return b * 10
        res = core.run_batches(list(range(8)), call, workers=3, retries=2, sleep=lambda s: None)
        self.assertLessEqual(peak, 3)
        self.assertEqual([r.index for r in res], list(range(8)))
        self.assertFalse(res[3].ok); self.assertEqual(res[3].attempts, 3)
        self.assertTrue(res[5].ok and res[5].attempts == 2)
        self.assertEqual([r.value for r in res if r.ok], [0, 10, 20, 40, 50, 60, 70])


class EditorialTests(unittest.TestCase):
    def test_second_run_makes_no_calls_and_same_result(self):
        d = Path(tempfile.mkdtemp()); plan = make_plan(40)
        a = FakeLLM(); first = reasoner(a, d).reason(plan)
        self.assertEqual(len(a.calls), 4)   # 40 scenes, batches of 12
        b = FakeLLM(); second = reasoner(b, d).reason(make_plan(40))
        self.assertEqual(b.calls, [])
        self.assertEqual({k: v.to_dict() for k, v in first.items()}, {k: v.to_dict() for k, v in second.items()})

    def test_changed_scene_only_reasks_that_scene(self):
        d = Path(tempfile.mkdtemp()); reasoner(FakeLLM(), d).reason(make_plan(40))
        plan = make_plan(40); plan.scenes[20].narration_excerpt = "completely different line"
        llm = FakeLLM(); reasoner(llm, d).reason(plan)
        asked = sorted({s for c in llm.calls for s in c}, key=int)
        # the changed scene (21) and its neighbours, whose beat carries its text as prev/next, are asked again; nothing else
        self.assertEqual(asked, ["20", "21", "22"])

    def test_failed_batch_keeps_the_others(self):
        d = Path(tempfile.mkdtemp()); llm = FakeLLM(fail_scenes={"15"})
        r = reasoner(llm, d); out = r.reason(make_plan(36))
        self.assertTrue(all(str(i) in out for i in list(range(1, 13)) + list(range(25, 37))))
        self.assertNotIn("15", out)
        self.assertEqual(r.provenance["15"], "rules"); self.assertEqual(r.provenance["1"], "ai")
        # the survivors were cached: the next run only asks the failed batch again
        llm2 = FakeLLM(); reasoner(llm2, d).reason(make_plan(36))
        self.assertEqual({s for c in llm2.calls for s in c}, {str(i) for i in range(13, 25)})

    def test_truncated_answer_is_split_not_lost(self):
        d = Path(tempfile.mkdtemp()); llm = FakeLLM(truncate_over=3)
        out = reasoner(llm, d, batch_size=12).reason(make_plan(12))
        self.assertEqual(sorted(k for k in out if k.isdigit() and not k.startswith("0")), sorted(str(i) for i in range(1, 13)))

    def test_bounded_concurrency_and_order(self):
        d = Path(tempfile.mkdtemp()); llm = FakeLLM(delay=0.02)
        out = reasoner(llm, d, workers=3).reason(make_plan(120))
        self.assertLessEqual(llm.peak, 3); self.assertGreater(llm.peak, 1)
        order = [int(k) for k in out if k.isdigit() and not k.startswith("0")]
        self.assertEqual(order, sorted(order))

    def test_same_decisions_as_the_original_reasoner(self):
        plan = make_plan(30)
        legacy = R.GeminiEditorialReasoner(settings={}, llm=FakeLLM(), batch_size=28).reason(plan)
        new = reasoner(FakeLLM(), Path(tempfile.mkdtemp())).reason(make_plan(30))
        self.assertEqual({k: v.to_dict() for k, v in legacy.items() if k.isdigit()}, {k: v.to_dict() for k, v in new.items() if k.isdigit()})

    def test_spent_quota_stops_asking_and_never_retries(self):
        from semantic_intel import run_batches
        calls = []
        def call(b):
            calls.append(b); raise RuntimeError("Gemini API error: You exceeded your current quota")
        res = run_batches([[1], [2], [3], [4]], call, workers=1, retries=2, backoff=0, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)                       # one attempt, no retries, the rest skipped
        self.assertEqual([r.ok for r in res], [False] * 4)

    @unittest.skipUnless(PLAN047.is_file(), "project 047 not on this machine")
    def test_real_047_plan_is_cacheable(self):
        plan = editorial.EditorialPlan.from_dict(load_editorial_plan(PLAN047.parent))
        d = Path(tempfile.mkdtemp()); a = FakeLLM(); reasoner(a, d).reason(plan)
        n = len(plan.scenes); self.assertEqual(sum(len(c) for c in a.calls), n)
        b = FakeLLM(); reasoner(b, d).reason(plan); self.assertEqual(b.calls, [])


if __name__ == "__main__":
    unittest.main()
