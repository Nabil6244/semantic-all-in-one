"""Normal Video "Use Hybrid Map Graphics & Sound": off by default and then nothing changes; on, Hybrid Map's sound design is planned from the
graphics really on screen and the stronger transitions, with no map visuals."""

import inspect
import unittest

import normal_hybrid_style as hs
from graphics.schema import GraphicSpec, TextOverlaySpec


def _g(role, start, end, look=None):
    return GraphicSpec(graphic_id=f"{role}{start}", role=role, decision=role, start=start, end=end,
                       text=TextOverlaySpec(text="x"), payload={"doc_look": look} if look else {})


class Off(unittest.TestCase):
    def test_default_is_off(self):
        self.assertFalse(hs.is_on({}))
        self.assertFalse(hs.is_on(None))
        self.assertTrue(hs.is_on({"normal_hybrid_style": True}))

    def test_hook_is_restored_after_the_render(self):
        import graphics, graphics.doc_plan as dp, video_generator as vg

        before = (graphics.graphics_from_timeline, dp.plan_doc_extras, vg.run_final_mux)
        with hs.finishing(vg, "n.wav", "o.wav", 10.0, [0.0], {}):
            self.assertIsNot(vg.run_final_mux, before[2])
        self.assertEqual((graphics.graphics_from_timeline, dp.plan_doc_extras, vg.run_final_mux), before)

    def test_app_source_gates_everything_on_the_switch(self):
        try:
            import app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(str(exc))
        self.assertIn('self._settings.get("normal_hybrid_style", False)', inspect.getsource(app.VideoGeneratorApp._normal_hybrid_style_on))
        src = inspect.getsource(app.VideoGeneratorApp._run_pipeline)
        self.assertGreaterEqual(src.count('config.get("hybrid_style")'), 4)          # every use of the feature is behind the switch


class Events(unittest.TestCase):
    def test_graphics_and_strong_transitions_make_events_maps_make_none(self):
        specs = [_g("NAME", 1.0, 4.0), _g("STATISTIC", 10.0, 13.0), _g("MAP", 20.0, 24.0), _g("LABEL", 30, 33, "watermark"),
                 _g("CALLOUT", 40, 44, "panel"), _g("TITLE", 50, 53, "glitch")]
        ev = hs.sound_events(specs, [(5.0, "fade"), (9.0, "zoom_blur"), (12.0, "wipe"), (30.0, "dip_black")])
        sounds = sorted((e["t_in"], e["template"]["sfx"][0]["sound"]) for e in ev)
        self.assertEqual([s for t, s in sounds if t in (1.0, 9.0, 10.0, 30.0, 40.0)], ["ui_click", "fast_whoosh", "counter_ticks", "soft_transition", "paper_slide"])
        self.assertNotIn(20.0, [t for t, _ in sounds])      # the map graphic
        self.assertNotIn(5.0, [t for t, _ in sounds])       # a plain fade is quiet
        self.assertNotIn(12.0, [t for t, _ in sounds])      # a second transition inside 8 s of the first

    def test_plan_follows_the_pakmap_restraint_rules(self):
        specs = [_g("NAME", 1.0, 4.0), _g("NAME", 1.2, 4.0), _g("STATISTIC", 10.0, 13.0)]
        plan = hs.plan_sound(specs, [], 30.0, catalog=None)
        times = [round(c.t, 2) for c in plan.cues]
        self.assertEqual(len([t for t in times if t < 2]), 1)     # two effects 0.2 s apart: one plays, nothing doubled
        self.assertTrue(any(abs(t - 10.05) < 0.01 for t in times))

    def test_bad_spec_never_stops_the_rest(self):
        class Odd:
            start = "x"; end = None; role = "NAME"; payload = None
        ev = hs.sound_events([Odd(), _g("NAME", 2.0, 5.0)])
        self.assertEqual(len(ev), 1)


if __name__ == "__main__":
    unittest.main()
