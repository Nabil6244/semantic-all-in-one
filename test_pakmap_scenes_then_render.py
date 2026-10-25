"""pakMap: Generate gets the scenes and stops, Render draws (like Hybrid). The button says Render only once every scene row is ready.
The fetch itself is pakmap.app_integration's media_only (tested through Hybrid in test_hybrid_scenes_then_render); this guards the app wiring."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from types import SimpleNamespace

SRC = (Path(__file__).resolve().parent / "app.py").read_text(encoding="utf-8")


def _body(name: str) -> str:
    m = re.search(rf"    def {name}\(.*?(?=\n    def )", SRC, re.S)
    assert m, name
    return m.group(0)


class Wiring(unittest.TestCase):
    def test_the_button_follows_the_scenes(self):
        b = _body("_sync_primary_cta_pakmap")
        self.assertIn('_scenes_all_ready("pakmap")', b)
        self.assertIn('text="Render"', b)
        self.assertIn('text="Generate scenes"', b)

    def test_generate_fetches_only_until_every_scene_is_ready(self):
        b = _body("_run_pakmap_generation")
        self.assertIn('pakmap_media_only = bool(plan_rows) and not self._scenes_all_ready("pakmap")', b)
        self.assertIn("media_only=True", b)
        self.assertIn("need attention", b)               # a scene that is not ready is reported, not rendered over

    def test_ready_check_needs_a_table_of_this_style_with_every_row_done(self):
        import app

        check = getattr(getattr(app, "VideoGeneratorApp", None), "_scenes_all_ready", None)
        if check is None:
            self.skipTest("app class not importable here")
        rows = [SimpleNamespace(scene_number=str(i)) for i in range(3)]
        st = {"0": "ready", "1": "skipped", "2": "queued"}
        me = SimpleNamespace(_scene_rows_owner="pakmap", _scene_rows=rows, _row_status_from_result=lambda r: st[r.scene_number])
        self.assertFalse(check(me, "pakmap"))
        st["2"] = "ready"
        self.assertTrue(check(me, "pakmap"))
        self.assertFalse(check(me, "starmap"))
        st["2"] = "cancelled"
        self.assertFalse(check(me, "pakmap"))
        me._scene_rows = []
        self.assertFalse(check(me, "pakmap"))


if __name__ == "__main__":
    unittest.main()
