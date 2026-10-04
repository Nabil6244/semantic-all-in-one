"""Fact Map plays its hand-picked sounds for each text effect and scene change."""
import tempfile
import unittest
from pathlib import Path

import smart_editing as se


def _entry(i, category, duration):
    return {"id": i, "file": f"{category}/{i}.wav", "category": category, "tags": [],
            "intensity": "medium", "duration": duration, "source": "t", "license": "t",
            "commercial_use": True, "attribution_required": False}


IDS = [("ui_click_01", "ui", 0.17), ("impact_03", "impact", 0.47), ("cinematic_06", "cinematic", 0.69),
       ("whoosh_05", "whoosh", 0.5), ("whoosh_06", "whoosh", 5.2), ("text_pop_01", "text", 0.54),
       ("impact_01", "impact", 0.33), ("riser_01", "riser", 4.5), ("whoosh_other", "whoosh", 0.4)]


class CuratedSfx(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        se.write_test_sfx_library(root, [_entry(*x) for x in IDS])
        for i, c, _ in IDS:
            (root / c).mkdir(exist_ok=True)
            (root / c / f"{i}.wav").write_bytes(b"x")
        self.cat = se.SfxCatalog.load(root)
        self.settings = se.SmartEditingSettings.from_dict({})

    def tearDown(self):
        self.tmp.cleanup()

    def _plan(self, effect, **kw):
        rows = [{"scene_number": "1", "start_time": 0.0, "end_time": 8.0, "script_segment": "x"}]
        fx = [{"scene_number": "1", "text": "x", "start": 1.0, "end": 2.0, "effect": effect, "intensity": 0.7}]
        return se.plan_sfx_events(rows, fx, self.settings, self.cat, **kw)

    def test_each_text_effect_plays_its_pick(self):
        for effect, want in [("pop", "ui_click_01"), ("punch", "impact_03"), ("impact", "cinematic_06"),
                             ("fade", "whoosh_05"), ("highlight", "ui_click_01"),
                             ("scale", "whoosh_05"), ("word_reveal", "text_pop_01")]:
            ev = [e for e in self._plan(effect) if e["start"] == 1.0]
            self.assertEqual([e["sfx_id"] for e in ev], [want], effect)

    def test_rise_has_no_sound(self):
        self.assertEqual([e for e in self._plan("rise") if e["start"] == 1.0], [])

    def test_a_pick_missing_from_the_library_falls_back_to_the_matcher(self):
        cat = se.SfxCatalog(self.cat.root, [e for e in self.cat.entries if e.id != "impact_03"])
        rows = [{"scene_number": "1", "start_time": 0.0, "end_time": 8.0, "script_segment": "x"}]
        fx = [{"scene_number": "1", "text": "x", "start": 1.0, "end": 2.0, "effect": "punch", "intensity": 0.7}]
        ev = [e for e in se.plan_sfx_events(rows, fx, self.settings, cat) if e["start"] == 1.0]
        self.assertEqual(len(ev), 1)
        self.assertNotEqual(ev[0]["sfx_id"], "impact_03")

    def test_a_long_sound_is_cut_to_its_moment_with_a_fade(self):
        rows = [{"scene_number": str(n), "start_time": n * 6.0, "end_time": n * 6.0 + 6.0, "script_segment": "x"}
                for n in range(3)]
        ev = se.plan_sfx_events(rows, [], self.settings, self.cat,
                                scene_transitions=[{"scene_number": "1", "sfx": True}])
        tr = [e for e in ev if e["type"] == "scene_transition"]
        self.assertEqual(len(tr), 1)
        self.assertEqual(tr[0]["sfx_id"], "whoosh_06")
        self.assertAlmostEqual(tr[0]["duration"], 1.0, places=2)
        self.assertGreater(tr[0]["fade_out"], 0)

    def test_the_riser_slot_is_skipped(self):
        self.assertEqual(se._curated_transition_pick(4), ("cinematic_06", 0.95))


if __name__ == "__main__":
    unittest.main()
