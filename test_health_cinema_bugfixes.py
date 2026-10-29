import json
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace

from health_cinema import direction, render_journey
from health_cinema.render_journey import Cancelled


class StopDuringGeminiRetry(unittest.TestCase):
    def setUp(self):
        import visual_director.director as vd
        import visual_director.llm as vl
        self.calls = 0
        outer = self

        class FakeDirector:
            def __init__(self, **k): pass
            def plan(self, script, state_dir=None):
                outer.calls += 1
                return SimpleNamespace(warnings=["gemini_failure: Gemini API error: high demand"], scenes=[])

        self.saved = (vd.VisualDirector, vl.GeminiLLM, vl.gemini_configured)
        vd.VisualDirector, vl.GeminiLLM, vl.gemini_configured = FakeDirector, (lambda settings=None: object()), (lambda st: True)
        self.addCleanup(lambda: (setattr(vd, "VisualDirector", self.saved[0]), setattr(vl, "GeminiLLM", self.saved[1]), setattr(vl, "gemini_configured", self.saved[2])))

    def test_stop_ends_the_retry_wait_quickly(self):
        flag = {"stop": False}
        logs = []

        def log(m):
            logs.append(m)
            if "retrying" in m:
                flag["stop"] = True

        t0 = time.time()
        with self.assertRaises(Cancelled):
            direction.plan_visuals("A script.", {"gemini_enabled": True}, None, log, cancel=lambda: flag["stop"])
        self.assertLess(time.time() - t0, 2.0)
        self.assertEqual(self.calls, 1)

    def test_already_stopped_never_asks_gemini(self):
        with self.assertRaises(Cancelled):
            direction.plan_visuals("A script.", {"gemini_enabled": True}, None, cancel=lambda: True)
        self.assertEqual(self.calls, 0)


class GeminiIsOptional(unittest.TestCase):
    SCRIPT = ("Your heart pumps blood around the body every second of the day. It never rests, even when you sleep. "
              "Inside the arteries a smooth lining keeps blood moving freely. Over many years that lining can become damaged. "
              "High blood pressure and smoking are linked to this damage. A doctor can check your risk with simple tests.")

    def test_off_makes_no_gemini_call_and_still_plans(self):
        import visual_director.llm as vl
        saved = vl.GeminiLLM.complete
        vl.GeminiLLM.complete = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Gemini was called while switched off"))
        self.addCleanup(setattr, vl.GeminiLLM, "complete", saved)
        logs = []
        t0 = time.time()
        out = direction.plan_visuals(self.SCRIPT, {"gemini_enabled": False}, None, logs.append)
        self.assertLess(time.time() - t0, 5.0)
        self.assertTrue(out); self.assertTrue(all(d["plan_source"] == "deterministic-fallback" for d in out))
        self.assertTrue(any("built-in planner" in m for m in logs))

    def test_failed_gemini_gets_one_retry_only(self):
        import visual_director.director as vd
        import visual_director.llm as vl
        calls = []

        class Fail:
            def __init__(self, **k): pass
            def plan(self, script, state_dir=None):
                calls.append(1)
                return SimpleNamespace(warnings=["gemini_failure: high demand"], scenes=[])

        saved = (vd.VisualDirector, vl.GeminiLLM, vl.gemini_configured)
        vd.VisualDirector, vl.GeminiLLM, vl.gemini_configured = Fail, (lambda settings=None: object()), (lambda st: True)
        self.addCleanup(lambda: (setattr(vd, "VisualDirector", saved[0]), setattr(vl, "GeminiLLM", saved[1]), setattr(vl, "gemini_configured", saved[2])))
        time_mod = __import__("time"); orig = time_mod.sleep; time_mod.sleep = lambda s: None
        self.addCleanup(setattr, time_mod, "sleep", orig)
        direction.plan_visuals("A script.", {"gemini_enabled": True}, None)
        self.assertEqual(len(calls), 2)       # first try + one retry, then the built-in planner


class NoLeakedFiles(unittest.TestCase):
    def test_cache_key_closes_its_spec_file(self):
        d = Path(tempfile.mkdtemp())
        (d / "s.json").write_text(json.dumps({"duration": 1}))
        (d / "a.json").write_text("{}")
        (d / "m.glb").write_bytes(b"x")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            render_journey.cache_key(d / "s.json", d / "a.json", d / "m.glb", 64, 36, 8, code="c")
            import gc
            gc.collect()
        self.assertEqual([x for x in w if issubclass(x.category, ResourceWarning)], [])

    def test_child_process_pipe_is_closed_after_normal_exit_and_cancel(self):
        import gc, threading
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.assertEqual(render_journey.run_cancellable(["echo", "hi"]).strip(), "hi")
            ev = threading.Event(); threading.Timer(0.2, ev.set).start()
            with self.assertRaises(Cancelled):
                render_journey.run_cancellable(["sleep", "5"], ev)
            gc.collect()
        self.assertEqual([x for x in w if issubclass(x.category, ResourceWarning)], [])


if __name__ == "__main__":
    unittest.main()
