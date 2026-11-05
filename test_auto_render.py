"""Roblox Cinema / Voxel Map: Render starts by itself 30 s after Generate unless the user acts (ui/auto_render.py)."""
import unittest

from ui import auto_render


class Var:
    def __init__(self, v=""):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


class FakeApp:
    """after() queues callbacks; run(n) fires n seconds of them."""
    def __init__(self):
        self.jobs, self.log, self.n = {}, [], 0

    def after(self, ms, fn):
        self.n += 1
        self.jobs[self.n] = fn
        return self.n

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def run(self, seconds):
        for _ in range(seconds):
            if not self.jobs:
                return
            k = min(self.jobs)
            self.jobs.pop(k)()

    def _append_log(self, m):
        self.log.append(m)

    def _sync_primary_cta(self):
        pass


class AutoRenderTest(unittest.TestCase):
    def setUp(self):
        self.app, self.status, self.renders = FakeApp(), Var("Planned 12 scenes."), []

    def go(self, ok=""):
        auto_render.start(self.app, "vm", status_var=self.status, still_ok=lambda: ok, render=lambda: self.renders.append(1), tag="[T]")

    def test_render_starts_after_30_seconds(self):
        self.go()
        self.assertIn("30 s", self.status.get())
        self.app.run(29)
        self.assertEqual(self.renders, [])
        self.assertIn("1 s", self.status.get())
        self.app.run(5)
        self.assertEqual(self.renders, [1])
        self.assertFalse(auto_render.pending(self.app, "vm"))
        self.assertEqual(self.status.get(), "Planned 12 scenes.")

    def test_stop_or_render_click_cancels(self):
        self.go()
        self.app.run(10)
        self.assertTrue(auto_render.stop(self.app, "vm", note="cancelled"))
        self.app.run(40)
        self.assertEqual(self.renders, [])
        self.assertEqual(self.status.get(), "Planned 12 scenes.  cancelled")
        self.assertFalse(auto_render.stop(self.app, "vm"))

    def test_changed_plan_does_not_render(self):
        self.go(ok="the plan changed; click Generate again.")
        self.app.run(40)
        self.assertEqual(self.renders, [])
        self.assertIn("did not start", self.status.get())

    def test_new_generate_restarts_the_countdown(self):
        self.go()
        self.app.run(20)
        self.go()
        self.app.run(20)
        self.assertEqual(self.renders, [])
        self.app.run(15)
        self.assertEqual(self.renders, [1])


if __name__ == "__main__":
    unittest.main()
