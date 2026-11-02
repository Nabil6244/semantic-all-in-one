"""Generate scenes (reptheory.app_section.fetch_pictures): the scenes are listed in the Visuals tab before Flow makes any picture, and each finished
picture is reported as it lands (2026-11-02: 54 pictures were being made while the tab still said "No scenes yet")."""
import tempfile, unittest
from pathlib import Path

from reptheory import app_section as A


class FakeManager:      # every picture comes back (the manifest says complete)
    def __init__(self, order, folder): self.order = order; self.folder = folder
    def resolve_all(self, rows, on_scene_complete=None):
        from asset_manager import AssetManifest
        self.order.append("resolve"); man = AssetManifest(self.folder)
        for r in rows:
            man.set(r.scene_number, {"scene_number": r.scene_number, "status": "complete"})
            if on_scene_complete: on_scene_complete(r)


class ListedBeforeFlow(unittest.TestCase):
    def test_listed_first_then_each_done(self):
        order, done = [], []
        reqs = [{"no": i, "text": f"line {i}", "prompt": f"p{i}", "cached": None} for i in (1, 2, 3)]
        with tempfile.TemporaryDirectory() as d:
            rows = A.fetch_pictures(FakeManager(order, Path(d)), Path(d), reqs, lambda: False, lambda m: None,
                                    on_listed=lambda rs: order.append(("listed", len(rs))), on_done=lambda r: done.append(r.scene_number))
        self.assertEqual(order[0], ("listed", 3)); self.assertEqual(order[1], "resolve"); self.assertEqual(done, ["1", "2", "3"]); self.assertEqual(len(rows), 3)

    def test_still_works_without_callbacks(self):
        order = []
        with tempfile.TemporaryDirectory() as d:
            A.fetch_pictures(FakeManager(order, Path(d)), Path(d), [{"no": 1, "text": "a", "prompt": "p", "cached": None}], lambda: False, lambda m: None)
        self.assertEqual(order, ["resolve"])


if __name__ == "__main__":
    unittest.main()


class SaferRetry(unittest.TestCase):      # some Flow pictures were refused ("might violate our policies"), 2026-11-02
    def test_safe_prompt_keeps_the_look(self):
        from reptheory import beat_art as BA
        p = BA.prompt_for("In an arm wrestle against a bigger guy, your forearm takes the pain first and the tendons can tear.")
        s = BA.safe_prompt(p)
        for w in ("young", "pain", "tear", "glowing red"): self.assertNotIn(w, s.lower())
        for w in ("bare torso", "orange waistband", "adult man", "highlighted in red"): self.assertIn(w, s)

    def test_only_failed_rows_are_retried_in_a_safer_wording(self):
        from asset_manager import AssetManifest
        calls = []
        class M:
            def __init__(self, folder): self.man = AssetManifest(folder)
            def resolve_all(self, rows, on_scene_complete=None):
                calls.append([(r.scene_number, r.prompt) for r in rows])
                for r in rows: self.man.set(r.scene_number, {"scene_number": r.scene_number, "status": "complete" if r.scene_number == "1" or len(calls) > 1 else "failed"})
        reqs = [{"no": 1, "text": "a", "prompt": "Show a young man.", "cached": None}, {"no": 2, "text": "b", "prompt": "Show a young man, the tendons tear.", "cached": None}]
        with tempfile.TemporaryDirectory() as d:
            A.fetch_pictures(M(Path(d)), Path(d), reqs, lambda: False, lambda m: None)
        self.assertEqual(len(calls), 2); self.assertEqual([n for n, _ in calls[1]], ["2"]); self.assertNotIn("young", calls[1][0][1]); self.assertNotIn("tear", calls[1][0][1])


class SettingsKeptWithProject(unittest.TestCase):      # 2026-11-02: after a restart the scenes CSV and the Flow switch were reset; Render made 4 scenes, no pictures
    def test_page_choices_saved_and_restored(self):
        class Var:
            def __init__(self, v): self.v = v
            def get(self): return self.v
            def set(self, v): self.v = v
        class WS:
            meta = {}
            def read_meta(self): return dict(self.meta)
            def _write_meta(self, d): WS.meta = dict(d)
        class App: pass
        app = App(); app._workspace = WS()
        for k, a in A.SETTINGS.items(): setattr(app, a, Var(False if k in ("preview", "smart", "3d", "flow", "variety", "end") else ""))
        app._rt_scenes_var.set("/x/scenes.csv"); app._rt_flow_var.set(True); app._rt_ready_key = ("/x/scenes.csv", "vo.mp3", True, True, True, "")
        A.save_settings(app)
        fresh = App(); fresh._workspace = app._workspace
        for k, a in A.SETTINGS.items(): setattr(fresh, a, Var(False if k in ("preview", "smart", "3d", "flow", "variety", "end") else ""))
        self.assertTrue(A.restore_settings(fresh))
        self.assertEqual((fresh._rt_scenes_var.get(), fresh._rt_flow_var.get(), fresh._rt_ready_key), ("/x/scenes.csv", True, app._rt_ready_key))
