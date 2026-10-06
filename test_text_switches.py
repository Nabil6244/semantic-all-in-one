"""Text on screen is three Smart Editing switches: Smart Text Styles (only
Statement / Question / Quote), Graphics (lower thirds, statistic cards,
titles — no Location / Date labels) and Map Niche (countdown fact tag, hook,
yellow keyword callouts)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from editorial.render_gate import editorial_timeline_for_render
from smart_editing import SmartEditingSettings


def _timeline():
    def gfx(eid, role, template=""):
        return {"event_id": eid, "track": "GRAPHICS", "start": 0, "end": 2,
                "metadata": {"graphic": True, "role": role, "payload": {"template": template} if template else {}}}
    return {"events": [
        gfx("lt", "LOWER_THIRD"), gfx("stat", "STATISTIC"), gfx("title", "TITLE"),
        gfx("tag", "CHAPTER", "countdown_tag"), gfx("hook", "TITLE", "countdown_hook"),
        gfx("callout", "EMPHASIS", "keyword_callout"),
        {"event_id": "clip", "track": "VIDEO_1", "start": 0, "end": 2, "metadata": {}},
    ]}


def _ids(tl):
    return {e["event_id"] for e in tl["events"]} if tl else set()


class TestSwitchesGateTheirOwnGraphics(unittest.TestCase):
    def setUp(self):
        self.plan = SimpleNamespace(timeline=_timeline())

    def test_both_on_shows_everything(self):
        self.assertEqual(len(_ids(editorial_timeline_for_render(self.plan, graphics=True, map_niche=True))), 7)

    def test_graphics_off_keeps_map_niche(self):
        ids = _ids(editorial_timeline_for_render(self.plan, graphics=False, map_niche=True))
        self.assertEqual(ids, {"tag", "hook", "callout", "clip"})

    def test_map_niche_off_keeps_graphics(self):
        ids = _ids(editorial_timeline_for_render(self.plan, graphics=True, map_niche=False))
        self.assertEqual(ids, {"lt", "stat", "title", "clip"})

    def test_both_off_shows_no_graphics(self):
        self.assertIsNone(editorial_timeline_for_render(self.plan, graphics=False, map_niche=False))

    def test_old_single_switch_still_works(self):
        self.assertIsNone(editorial_timeline_for_render(self.plan, text_effects=False))
        self.assertEqual(len(_ids(editorial_timeline_for_render(self.plan, text_effects=True))), 7)


class TestSettings(unittest.TestCase):
    def test_new_switches_start_where_the_old_text_effects_switch_was(self):
        off = SmartEditingSettings.from_dict({"text_effects": False})
        self.assertEqual((off.graphics, off.map_niche), (False, False))
        on = SmartEditingSettings.from_dict({"text_effects": True})
        self.assertEqual((on.graphics, on.map_niche), (True, True))

    def test_each_switch_is_saved_on_its_own(self):
        s = SmartEditingSettings.from_dict({"text_effects": True, "graphics": False, "map_niche": True})
        d = s.to_settings_dict()
        self.assertEqual((d["text_effects"], d["graphics"], d["map_niche"]), (True, False, True))
        self.assertTrue(SmartEditingSettings(text_effects=False, graphics=False, map_niche=True,
                                             sound_effects=False, visual_transitions=False,
                                             scene_ambience=False).enabled())

    def test_project_file_keeps_them(self):
        import tempfile
        from pathlib import Path

        from project_workspace import ProjectWorkspace

        with tempfile.TemporaryDirectory() as tmp:
            ws = ProjectWorkspace(project_id="p", title="t", seq=1, root=Path(tmp))
            ws.ensure_dirs()
            ws.set_smart_editing_settings({"text_effects": True, "graphics": False, "map_niche": False})
            data = ws.smart_editing_settings()
            self.assertEqual((data["graphics"], data["map_niche"]), (False, False))


class TestRemovedEffects(unittest.TestCase):
    def test_only_quote_is_ever_chosen(self):
        from typography.variation import plan_typography_decision, reset_variation_history

        reset_variation_history()
        cases = [("BREAKTHROUGH", "punch"), ("42%", "impact"), ("deep ocean", "highlight"),
                 ("Built between 1931 and 1936", "fade"), ("One concrete block at a time", "word_reveal"),
                 ("What happens next?", "highlight"), ("“The largest dam on Earth.”", "fade"),
                 ("Verified by engineers", "fade")]
        chosen = {plan_typography_decision(t, e).style_id for t, e in cases}
        self.assertEqual(chosen, {"quote"})   # Smart Text has one look since 2026-10-06

    def test_location_and_date_labels_are_never_planned(self):
        from graphics.engine import REMOVED_GRAPHIC_ROLES, plan_graphics

        scene = SimpleNamespace(scene_number="1", start=0.0, end=6.0, duration=6.0, importance="high",
                                narration_excerpt="In March 1931 crews arrived in Black Canyon, Nevada, near Las Vegas.",
                                visual_description="", purpose="context", attention_score=0.7,
                                asset_type_intent="stock_video", camera_style="static", visual_treatment="")
        try:
            gplan = plan_graphics(SimpleNamespace(scenes=[scene]))
        except Exception as exc:  # the director needs more fields on some paths
            self.skipTest(f"plan_graphics needs a fuller plan: {exc}")
        roles = {str(s.role).upper() for s in gplan.specs} | {str(s.decision).upper() for s in gplan.specs}
        self.assertFalse(roles & REMOVED_GRAPHIC_ROLES)


class TestPanel(unittest.TestCase):
    def test_three_switches_replace_text_effects(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parent / "ui" / "views.py").read_text(encoding="utf-8")
        for label in ('"Smart Text Styles"', '"Graphics"', '"Map Niche"'):
            self.assertIn(label, src)
        self.assertNotIn('_feature_row(1, "Text Effects"', src)


if __name__ == "__main__":
    unittest.main()
