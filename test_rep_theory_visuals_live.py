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


class SettingsOnProjectOpen(unittest.TestCase):      # 2026-11-02: saved choices were only restored on a style switch; reopening the app showed an empty page
    def _app(self, meta):
        class Var:
            def __init__(self, v): self.v = v
            def get(self): return self.v
            def set(self, v): self.v = v
        class WS:
            root = "/p/1"
            def __init__(self): self.meta = dict(meta)
            def read_meta(self): return dict(self.meta)
            def _write_meta(self, d): self.meta = dict(d)
        class App: pass
        app = App(); app._workspace = WS()
        for k, a in A.SETTINGS.items(): setattr(app, a, Var("leftover" if k == "scenes" else A.DEFAULTS[k]))
        return app

    def test_open_restores_saved_choices(self):
        app = self._app({A.SETTINGS_KEY: {"scenes": "/x/scenes.csv", "flow": True}})
        A.on_workspace(app); self.assertEqual((app._rt_scenes_var.get(), app._rt_flow_var.get()), ("/x/scenes.csv", True))

    def test_a_project_without_choices_gets_the_defaults_not_the_last_projects(self):
        app = self._app({}); A.on_workspace(app); self.assertEqual(app._rt_scenes_var.get(), "")


class ElderHostAndQualityCheck(unittest.TestCase):      # Elder Health Theory (elder_art.py): host pictures carry the reference; a failed picture is redrawn once, the better kept
    def test_refs_and_redraw(self):
        import contextlib
        from unittest import mock
        from PIL import Image, ImageDraw
        from asset_manager import AssetManifest
        from reptheory import beat_art as BA
        sent = []
        class FP:
            def __init__(self): self.flow_settings = {"model": "x"}; self.engine_manager = None; self.account_ids = None
            @contextlib.contextmanager
            def confirming_resubmit(self): yield
        class M:
            def __init__(self, folder): self.folder = folder; self.man = AssetManifest(folder); self.flow_image_provider = FP(); self.round = 0
            def resolve_all(self, rows, on_scene_complete=None):
                self.round += 1; sent.append(([r.scene_number for r in rows], "referenceImages" in self.flow_image_provider.flow_settings, [r.prompt for r in rows]))
                for r in rows:
                    p = self.folder / f"{int(r.scene_number):03d}_{self.round}.png"; good = "plain solid pure white (#FFFFFF) from edge to edge" in r.prompt or r.scene_number == "1"
                    im = Image.new("RGB", (300, 200), "white" if good else (150, 120, 90))
                    if good: ImageDraw.Draw(im).ellipse((180, 40, 280, 160), fill=(40, 120, 120))
                    im.save(p); self.man.set(r.scene_number, {"scene_number": r.scene_number, "status": "complete", "local_path": str(p), "prompt": r.prompt})
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "ref.png"; Image.new("RGB", (300, 300), "white").save(ref)
            reqs = [{"no": 1, "text": "a", "prompt": "organ", "cached": None, "refs": False, "qc": True}, {"no": 2, "text": "b", "prompt": "host", "cached": None, "refs": True, "qc": True}]
            m = M(Path(d))
            with mock.patch.object(BA, "_refs_for", return_value=[str(ref)]):
                A.fetch_pictures(m, Path(d), reqs, lambda: False, lambda msg: None)
            self.assertEqual(sent[0][:2], (["1"], False)); self.assertEqual(sent[1][:2], (["2"], True))   # the host's picture went with the reference
            self.assertEqual(sent[2][:2], (["2"], True)); self.assertTrue(sent[2][2][0].startswith("The background must be plain"))   # redrawn once, in stronger wording
            self.assertEqual(len(sent), 3); self.assertNotIn("referenceImages", m.flow_image_provider.flow_settings)   # settings restored
            self.assertTrue(m.man.get("2")["local_path"].endswith("_3.png"))   # the better picture is kept


class SentencesWithoutPunctuation(unittest.TestCase):      # the app's Whisper words carry no punctuation: a smooth 22 s voiceover was one scene (pipeline check 2026-11-10)
    def test_cut_at_pauses(self):
        def say(*parts, gap=0.55):
            out, t = [], 0.0
            for k, p in enumerate(parts):
                for w in p.split(): out.append((w, t, t + 0.3)); t += 0.3
                t += gap
            return out
        words = say("do your knees feel stiff in the morning", "walk for twenty minutes after dinner", "eat", "keep salt under one teaspoon a day")
        got = [s["text"] for s in A.sentences_from_words(words, 15.0)]
        self.assertEqual(len(got), 3); self.assertTrue(got[1].startswith("walk") and "eat" in got[1])   # a one-word piece joins the one before
        long_one = say(" ".join(["word"] * 50))      # no pause at all for 15 s: cut again at its longest pause
        self.assertGreaterEqual(len(A.sentences_from_words(long_one, 15.0)), 1)
        punct = [("Hello", 0.0, 0.3), ("there", 0.3, 0.6), ("my", 0.6, 0.8), ("friend.", 0.8, 1.0), ("Bye", 1.6, 1.9), ("now", 1.9, 2.1), ("my", 2.1, 2.3), ("friend.", 2.3, 2.6)]
        from health_cinema.app_section import sentences_from_words as shared
        self.assertEqual(A.sentences_from_words(punct, 3.0), shared(punct, 3.0))   # punctuated words: the shared cutter, unchanged
