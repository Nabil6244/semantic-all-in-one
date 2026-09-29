"""The Audio & Effects switches must control the render: Visual Transitions
(on/off + Low/Medium/High, zoom-blur cuts included) and Sound Effects
Low/Medium/High (the final sound list, zoom-blur whooshes included)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


def _plan(n=37, every=2.65, zoom_every=2):
    from editorial.schema import EditorialPlan, EditorialScene

    scenes = []
    for i in range(n):
        s = EditorialScene(scene_number=str(i + 1), start=i * every, end=(i + 1) * every, duration=every)
        if i and i % zoom_every == 0:
            s.transition_in = "zoom_blur"
        scenes.append(s)
    return EditorialPlan(scenes=scenes)


class TestVisualTransitionsSetting(unittest.TestCase):
    def test_off_means_no_transitions_at_all(self):
        from editorial.pacing import apply_transition_settings

        plan = _plan()
        self.assertEqual(apply_transition_settings(plan, enabled=False, intensity="high"), {})
        self.assertFalse(any(s.transition_in not in (None, "cut") for s in plan.scenes))

    def test_low_medium_high_limit_count_and_spacing(self):
        from editorial.pacing import TRANSITION_SETTINGS, apply_transition_settings

        counts = {}
        for level in ("low", "medium", "high"):
            plan = _plan()
            tmap = apply_transition_settings(plan, enabled=True, intensity=level)
            tmap.pop("1", None)  # the opening fade-in isn't a scene change
            frac, gap = TRANSITION_SETTINGS[level]
            self.assertLessEqual(len(tmap), round(36 * frac))
            starts = sorted(s.start for s in plan.scenes if str(s.scene_number) in tmap)
            self.assertTrue(all(b - a >= gap for a, b in zip(starts, starts[1:])), level)
            counts[level] = len(tmap)
        self.assertLess(counts["low"], counts["medium"])
        self.assertLessEqual(counts["medium"], counts["high"])
        self.assertLessEqual(counts["low"], 7)  # a 37-scene video on Low: a handful, not 27

    def test_zoom_blur_cuts_are_kept_first(self):
        from editorial.pacing import apply_transition_settings

        plan = _plan()
        tmap = apply_transition_settings(plan, enabled=True, intensity="low")
        tmap.pop("1", None)  # the opening fade-in isn't a scene change
        self.assertTrue(tmap and all(v == "zoom_blur" for v in tmap.values()))

    def test_render_uses_the_setting_not_the_raw_pacing_map(self):
        src = (Path(__file__).resolve().parent / "app.py").read_text(encoding="utf-8")
        self.assertIn("transition_map = apply_transition_settings(", src)
        self.assertNotIn("transition_map = authoritative_transition_map(editorial_plan)", src)
        self.assertLess(src.index("apply_transition_settings("), src.index("smart_plan = build_plan("))


class TestSoundEffectsSetting(unittest.TestCase):
    def _events(self, n=30, every=3.2):
        out = []
        for i in range(n):
            ev = {"start": 1.0 + i * every, "duration": 0.5, "volume": 0.2, "file": "whoosh/w.wav"}
            if i % 2 == 0:
                ev["zoom_blur"] = True
            elif i % 5 == 0:
                ev["file"] = "impact/i.wav"
            out.append(ev)
        return out

    def test_low_is_sparse_spaced_and_spread(self):
        from smart_editing import SFX_DENSITY, limit_sfx_density

        kept, dropped = limit_sfx_density(self._events(), 98.0, "low")
        gap, per_min = SFX_DENSITY["low"]
        starts = [e["start"] for e in kept]
        self.assertLessEqual(len(kept), 12)
        self.assertEqual(dropped, 30 - len(kept))
        self.assertTrue(all(b - a >= gap for a, b in zip(starts, starts[1:])))
        for w in starts:
            self.assertLessEqual(sum(1 for t in starts if w <= t < w + 60), per_min)
        self.assertGreater(max(starts), 80.0)  # the ending still gets sounds

    def test_levels_are_ordered(self):
        from smart_editing import limit_sfx_density

        counts = [len(limit_sfx_density(self._events(), 98.0, lvl)[0]) for lvl in ("low", "medium", "high")]
        self.assertLess(counts[0], counts[1])
        self.assertLess(counts[1], counts[2])

    def test_mix_applies_the_limit_after_the_zoom_blur_whooshes(self):
        src = (Path(__file__).resolve().parent / "app.py").read_text(encoding="utf-8")
        self.assertLess(src.index("apply_zoom_blur_whooshes(sfx_for_mix"), src.index("limit_sfx_density("))
        self.assertLess(src.index("limit_sfx_density("), src.index("mix_sfx_with_narration(\n"))

    def test_whoosh_for_a_removed_zoom_blur_cut_is_dropped(self):
        from smart_editing import SmartEditingSettings, apply_zoom_blur_whooshes

        stale = [{"start": 20.0, "duration": 0.5, "volume": 0.3, "file": "whoosh/x.wav", "zoom_blur": True},
                 {"start": 40.0, "duration": 0.5, "volume": 0.2, "file": "impact/y.wav"}]
        out, _added, _raised = apply_zoom_blur_whooshes(stale, [], SmartEditingSettings())
        self.assertEqual([e["file"] for e in out], ["impact/y.wav"])

    def test_rejected_sound_is_never_loaded(self):
        from smart_editing import SfxCatalog

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "catalog.json").write_text(json.dumps({"sfx": [
                {"id": "transition_02", "file": "transition/transition_02.wav", "category": "transition"},
                {"id": "whoosh_05", "file": "whoosh/whoosh_05.wav", "category": "whoosh"},
            ]}), encoding="utf-8")
            self.assertEqual([e.id for e in SfxCatalog.load(root).entries], ["whoosh_05"])


if __name__ == "__main__":
    unittest.main()
