"""War Documentary in the style picker: opt-in, lazy (nothing of cinematic_explainer.war is imported until it is picked), one entry, the
default and every other style unchanged, a running render cannot be switched away from. Live app in a subprocess (same convention as
test_style_picker.py). Scene-building helpers are tested in-process. No network, no rendering."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

_SCRIPT = r'''
import os, sys, tempfile, time
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())
OUT = sys.stdout

def emit(name, ok, detail=""):
    OUT.write(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}\n"); OUT.flush()

try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}"); os._exit(0)
from project_workspace import ProjectWorkspace
_iso = Path(tempfile.mkdtemp()) / "settings.json"
_app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)
_app.messagebox.showinfo = lambda *a, **k: None
tmp = Path(tempfile.mkdtemp())
ws = ProjectWorkspace(project_id="p1", title="Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow"):
    (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws
inst.update_idletasks()

def shown(w):
    return bool(w.grid_info())

def state():
    return (inst.generation_mode, inst._style_picker.get(), shown(inst._overscaled_block), shown(inst._pakmap_block), shown(inst._hybrid_block))


emit("war_not_loaded_at_start", not any(m.startswith("cinematic_explainer.war") for m in sys.modules))
emit("choices_default_and_single_entry", inst.STYLE_CHOICES[0] == "Normal video" and inst.STYLE_CHOICES.count("War Documentary") == 1
     and "War Documentary" in inst.STYLE_BLURBS and "War Documentary" in inst.STYLE_CARDS, str(inst.STYLE_CHOICES))
emit("starts_normal", inst._active_style() == "Normal video" and not getattr(inst, "_war_active", False))

inst._on_style_pick("War Documentary"); inst.update_idletasks()
emit("war_picked", inst._active_style() == "War Documentary" and inst._style_picker.get() == "War Documentary" and shown(inst._war_block)
     and inst.generation_mode == "normal", f"{inst._active_style()} {inst.generation_mode}")
emit("war_loaded_only_now", any(m.startswith("cinematic_explainer.war.app_section") for m in sys.modules))
emit("war_cta_needs_voiceover", inst._cta_action == "import_audio", str(getattr(inst, "_cta_action", None)))
emit("war_card_is_alone", not (shown(inst._overscaled_block) or shown(inst._pakmap_block) or shown(inst._hybrid_block) or shown(inst._starmap_block)))

inst._on_style_pick("pakMap"); inst.update_idletasks()
emit("other_style_replaces_war", inst._active_style() == "pakMap" and not shown(inst._war_block) and not inst._war_active, inst._active_style())
inst._on_style_pick("War Documentary"); inst.update_idletasks()
inst._on_style_pick("Normal video"); inst.update_idletasks()
emit("normal_replaces_war", inst._active_style() == "Normal video" and inst.generation_mode == "normal" and not shown(inst._war_block))

inst._on_style_pick("War Documentary"); inst._war_running = True
inst._on_style_pick("Normal video"); inst.update_idletasks()
emit("running_war_keeps_its_style", inst._active_style() == "War Documentary", inst._active_style())
inst._war_running = False
os._exit(0)
'''


class TestWarAppSection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(tempfile.mkdtemp()) / "_war_picker_check.py"
        script.write_text(_SCRIPT, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
                              cwd=Path(__file__).resolve().parent)
        cls._stdout, cls._stderr, cls._results = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[len("SKIP:"):])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._results[name] = (status == "PASS", detail)

    def _check(self, name):
        if name not in self._results:
            self.fail(f"subprocess never reported {name!r}\nstdout:\n{self._stdout[-1500:]}\nstderr:\n{self._stderr[-2500:]}")
        ok, detail = self._results[name]
        self.assertTrue(ok, f"{name} failed: {detail}\nstderr:\n{self._stderr[-2000:]}")

    def test_opt_in_lazy_and_default_unchanged(self):
        for n in ("war_not_loaded_at_start", "choices_default_and_single_entry", "starts_normal", "war_loaded_only_now"):
            with self.subTest(n):
                self._check(n)

    def test_picking_and_leaving(self):
        for n in ("war_picked", "war_cta_needs_voiceover", "war_card_is_alone", "other_style_replaces_war", "normal_replaces_war",
                  "running_war_keeps_its_style"):
            with self.subTest(n):
                self._check(n)


class TestSceneHelpers(unittest.TestCase):
    def test_sentences_from_words(self):
        from cinematic_explainer.war.app_section import sentences_from_words

        words = [("Ukraine", 0.5, 0.9), ("lies", 0.9, 1.1), ("on", 1.1, 1.2), ("the", 1.2, 1.3), ("coast.", 1.3, 1.8),
                 ("It", 2.0, 2.1), ("borders", 2.1, 2.5), ("Poland", 2.5, 2.9), ("and", 2.9, 3.0), ("Romania.", 3.0, 3.6)]
        sc = sentences_from_words(words, 4.0)
        self.assertEqual(len(sc), 2)
        self.assertEqual(sc[0]["start"], 0.0)
        self.assertEqual(sc[0]["end"], sc[1]["start"])          # contiguous
        self.assertEqual(sc[1]["end"], 4.0)                      # the last runs to the end of the narration
        self.assertEqual(sc[0]["text"], "Ukraine lies on the coast.")
        self.assertEqual([s["scene_no"] for s in sc], [1, 2])

    def test_pause_splits_and_bad_words_are_skipped(self):
        from cinematic_explainer.war.app_section import sentences_from_words

        sc = sentences_from_words([("a", 0, 1), ("b", 3, 4), ("bad",), (None, "x", "y")], 5.0)
        self.assertEqual([s["text"] for s in sc], ["a", "b"])
        self.assertEqual(sentences_from_words([], 5.0), [])

    def test_scenes_file_must_be_a_list(self):
        from cinematic_explainer.war.app_section import read_scenes_file

        d = Path(tempfile.mkdtemp())
        (d / "s.json").write_text('{"a": 1}', encoding="utf-8")
        with self.assertRaises(ValueError):
            read_scenes_file(str(d / "s.json"), d)
        (d / "t.json").write_text('[{"text": "x", "start": 0, "end": 1}]', encoding="utf-8")
        self.assertEqual(len(read_scenes_file(str(d / "t.json"), d)), 1)

    def test_scenes_csv_from_the_prompt_is_accepted_and_aligned(self):
        from cinematic_explainer.war.app_section import needs_alignment, read_scenes_file
        from health_cinema import scenes_csv

        d = Path(tempfile.mkdtemp())
        (d / "s.csv").write_text('﻿```csv\nScene_Number,script_segment,asset_type,prompt\n'
                                 '1,"Russia struck Kharkiv overnight, again.",youtube_video,Kharkiv strike || Ukraine missile\n'
                                 '3,Losses rose by ten percent.,none,\n```\n', encoding="utf-8")
        sc = read_scenes_file(str(d / "s.csv"), d)
        self.assertEqual([s["scene_no"] for s in sc], [1, 3])           # scene numbers kept: the Visuals tab's footage lines up
        self.assertEqual(sc[0]["text"], "Russia struck Kharkiv overnight, again.")
        self.assertEqual((sc[0]["asset_type"], sc[1]["asset_type"]), ("youtube_video", "none"))
        self.assertTrue(needs_alignment(sc))
        words = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("Russia struck Kharkiv overnight, again. Losses rose by ten percent.".split())]
        timed, frac = scenes_csv.align_to_words(sc, words, 6.0)
        self.assertEqual(frac, 1.0)
        self.assertEqual((timed[0]["start"], timed[1]["start"], timed[1]["end"]), (0.0, 2.5, 6.0))
        self.assertEqual(timed[1]["scene_no"], 3)
        (d / "bad.csv").write_text("scene_number,prompt\n1,x\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            read_scenes_file(str(d / "bad.csv"), d)
        (d / "timed.csv").write_text("text;start;end\nA b c.;0;1.5\n", encoding="utf-8")
        t = read_scenes_file(str(d / "timed.csv"), d)
        self.assertEqual((t[0]["start"], t[0]["end"]), (0.0, 1.5))
        self.assertFalse(needs_alignment(t))


class _FakeManager:
    """Stands in for the app's AssetManager: 'downloads' a clip per row into the manifest, records what it was asked for."""

    def __init__(self, images_dir: Path, fail=()):
        self.images_dir, self.fail, self.asked, self.settings = Path(images_dir), set(fail), [], {}

    def validate_rows(self, rows):
        return []

    def request_cancel(self):
        pass

    def resolve_all(self, rows, on_scene_start=None, on_scene_complete=None):
        from asset_manager import AssetManifest

        man = AssetManifest(self.images_dir)
        for r in rows:
            if on_scene_start:
                on_scene_start(r, None)
            self.asked.append((r.scene_number, r.asset_type, r.stock or r.prompt))
            if r.scene_number in self.fail:
                man.set(r.scene_number, {"scene_number": r.scene_number, "status": "failed", "error": "no result"})
                continue
            clip = self.images_dir / f"scene_{r.scene_number}.mp4"
            clip.write_bytes(b"x")
            man.set(r.scene_number, {"scene_number": r.scene_number, "status": "complete", "source": r.asset_type, "type": "video",
                                     "local_path": str(clip), "stock_query": r.stock or r.prompt, "provider": "pexels"})
            if on_scene_complete:
                on_scene_complete(r, "done")


def setUpModule():
    """The real War library on this Mac (~/Downloads/VideoGenerator/war_library) is never asked here: an empty one stands in."""
    import os

    os.environ["WAR_LIBRARY_DIR"] = tempfile.mkdtemp()


class TestCsvFootage(unittest.TestCase):
    """A scenes CSV run fetches its footage with the CSV's own searches (the render with no footage at all was the bug), lists it in the
    Visuals tab, keeps what the user picked there, and leaves `none` scenes clear for their map or card."""

    def scenes(self):
        return [{"scene_no": 1, "text": "Russia struck Kharkiv overnight.", "start": 0.0, "end": 3.0, "asset_type": "youtube_video",
                 "prompt": "Kharkiv strike footage || Kharkiv missile"},
                {"scene_no": 2, "text": "Losses rose by ten percent.", "start": 3.0, "end": 6.0, "asset_type": "none"},
                {"scene_no": 3, "text": "Convoys moved along the road.", "start": 6.0, "end": 9.0, "asset_type": "stock_video",
                 "prompt": "military convoy road"},
                {"scene_no": 4, "text": "My own clip here.", "start": 9.0, "end": 12.0, "asset_type": "local"}]

    def test_footage_rows_are_fetched_with_the_csv_searches(self):
        from cinematic_explainer.war.app_section import fetch_csv_footage

        d = Path(tempfile.mkdtemp())
        mgr = _FakeManager(d)
        out, rows = fetch_csv_footage(self.scenes(), mgr, d, director=False)
        self.assertEqual([r.scene_number for r in rows], ["1", "3", "4"])          # none is not a Visuals row; local is (attach it there)
        self.assertEqual([a[:2] for a in mgr.asked], [("1", "youtube_video"), ("3", "stock_video")])
        self.assertIn("military convoy road", mgr.asked[1][2])
        self.assertTrue(out[0]["footage"].endswith("scene_1.mp4") and out[2]["footage"].endswith("scene_3.mp4"))
        self.assertTrue(out[1].get("no_footage") and not out[1].get("footage"))
        self.assertFalse(out[3].get("footage"))
        mgr2 = _FakeManager(d)
        fetch_csv_footage(self.scenes(), mgr2, d, director=False)
        self.assertEqual(mgr2.asked, [])                                          # already in the table: nothing fetched twice

    def test_the_visuals_tab_lists_every_scene_before_the_fetch_and_fills_in_live(self):
        """Owner (2026-11-07): the Visuals tab said 'No scenes yet' for the whole fetch of 17 scenes."""
        from cinematic_explainer.war.app_section import fetch_csv_footage

        d = Path(tempfile.mkdtemp())
        mgr, events = _FakeManager(d), []
        listed = lambda rows: events.append(("listed", [r.scene_number for r in rows], len(mgr.asked)))
        fetch_csv_footage(self.scenes(), mgr, d, director=False, listed=listed, on_start=lambda r, s: events.append(("start", r.scene_number)),
                          on_done=lambda r, res: events.append(("done", r.scene_number)))
        self.assertEqual(events[0], ("listed", ["1", "3", "4"], 0))              # listed before anything was fetched
        self.assertIn(("start", "1"), events)
        self.assertIn(("done", "3"), events)

    def test_a_failed_search_leaves_the_scene_on_graphics_and_the_users_pick_is_kept(self):
        from asset_manager import AssetManifest
        from cinematic_explainer.war.app_section import fetch_csv_footage

        d = Path(tempfile.mkdtemp())
        out, _rows = fetch_csv_footage(self.scenes(), _FakeManager(d, fail={"3"}), d, director=False)
        self.assertFalse(out[2].get("footage"))
        mine = d / "mine.mp4"
        mine.write_bytes(b"x")
        AssetManifest(d).set("4", {"scene_number": "4", "status": "complete", "source": "manual", "type": "video", "local_path": str(mine),
                                   "user_override": True})
        out, _rows = fetch_csv_footage(self.scenes(), _FakeManager(d), d, director=False)
        self.assertEqual(out[3]["footage"], str(mine))
        self.assertTrue(out[3]["footage_meta"].get("user_supplied"))
        self.assertTrue(out[2]["footage"].endswith("scene_3.mp4"))                 # the failed row is searched again on the next Render

    def test_none_scene_takes_no_manifest_or_pool_clip(self):
        from cinematic_explainer.war.integration import load_scenes

        d = Path(tempfile.mkdtemp())
        (d / "Images").mkdir()
        clip = d / "Images" / "scene_2.mp4"
        clip.write_bytes(b"x")
        import json      # json.dumps, not "%s": a Windows path's backslashes must be escaped in JSON
        (d / "Images" / ".asset_manifest.json").write_text(json.dumps({"2": {"status": "complete", "local_path": str(clip), "type": "video",
                                                                              "stock_query": "losses percent"}}), encoding="utf-8")
        sc = load_scenes(d, [{"scene_no": 2, "text": "Losses rose by ten percent.", "start": 0.0, "end": 3.0, "no_footage": True}])
        self.assertIsNone(sc[0]["footage"])
        sc = load_scenes(d, [{"scene_no": 2, "text": "Losses rose by ten percent.", "start": 0.0, "end": 3.0}])
        self.assertEqual(sc[0]["footage"], str(clip))                              # without the CSV flag the manifest clip is still used

    def test_war_owns_its_visuals_rows(self):
        import visual_bridge

        self.assertIn("war", visual_bridge.OWNERS)
        ws = type("W", (), {"root": "/p"})()
        self.assertEqual(visual_bridge.folder("war", ws), Path("/p/state/war/assets"))


class TestGenerateScenesFirst(unittest.TestCase):
    """A scenes CSV goes through the Visuals tab: Generate scenes fetches into it, Render fetches nothing and uses what it holds."""

    def app(self, csv="/p/scenes.csv", vo="/p/vo.mp3"):
        var = type("V", (), {"get": lambda self: csv})()
        return type("A", (), {"_war_scenes_var": var, "_current_voiceover_path": lambda self: vo})()

    def test_a_csv_needs_generate_scenes_until_its_footage_is_in_the_tab(self):
        from cinematic_explainer.war.app_section import _inputs_key, needs_scenes

        app = self.app()
        self.assertTrue(needs_scenes(app))
        app._war_ready_key = _inputs_key(app)
        self.assertFalse(needs_scenes(app))
        self.assertTrue(needs_scenes(self.app(csv="/p/other.csv")))                       # another CSV: Generate scenes again
        self.assertFalse(needs_scenes(self.app(csv="")))                                   # narration only: nothing to fetch
        self.assertFalse(needs_scenes(self.app(csv="/p/scenes.json")))

    def test_render_uses_the_table_and_fetches_nothing(self):
        from asset_manager import AssetManifest
        from cinematic_explainer.war.app_section import fetch_csv_footage

        d = Path(tempfile.mkdtemp())
        fetch_csv_footage(TestCsvFootage().scenes(), _FakeManager(d), d, director=False)
        AssetManifest(d).set("3", {"scene_number": "3", "status": "skipped"})          # the user skipped it in the Visuals tab
        mgr = _FakeManager(d)
        out, rows = fetch_csv_footage(TestCsvFootage().scenes(), mgr, d, director=False, fetch=False)
        self.assertEqual(mgr.asked, [])
        self.assertTrue(out[0]["footage"].endswith("scene_1.mp4"))
        self.assertFalse(out[2].get("footage"))
        self.assertEqual([r.scene_number for r in rows], ["1", "3", "4"])

    def test_generate_scenes_leaves_the_export_page_alone(self):
        text = (Path(__file__).resolve().parent / "cinematic_explainer" / "war" / "app_section.py").read_text(encoding="utf-8")
        self.assertIn('run = None if media_only else app._track_generation_start("war")', text)
        self.assertIn('_goto_workflow_view("visual_plan")', text)


class TestAiFootage(unittest.TestCase):
    """AI clips (Flow, 10 credits each) only for flow_video rows, within the user's limit, priced before anything is made, labelled as AI."""

    def scenes(self):
        return [{"scene_no": i, "text": f"Scene {i} words here.", "start": i * 3.0, "end": i * 3.0 + 3, "asset_type": "flow_video",
                 "prompt": f"a chess king toppling {i}"} for i in range(1, 5)] + \
               [{"scene_no": 5, "text": "Convoys moved.", "start": 15.0, "end": 18.0, "asset_type": "stock_video", "prompt": "convoy road"}]

    def test_cap_and_price(self):
        from cinematic_explainer.war.app_section import AI_LOOK, ai_plan, csv_rows

        d = Path(tempfile.mkdtemp())
        plan = ai_plan(self.scenes(), d, cap=3)
        self.assertEqual((plan["make"], plan["over"], plan["credits"]), (["1", "2", "3"], ["4"], 30))
        self.assertIn(AI_LOOK, csv_rows(self.scenes())[0].prompt)                    # one documentary look for every AI clip
        self.assertEqual(ai_plan(self.scenes(), d, cap=0)["credits"], 0)

    def test_only_within_the_cap_and_labelled_ai(self):
        from cinematic_explainer.war.app_section import ai_plan, fetch_csv_footage

        d = Path(tempfile.mkdtemp())
        mgr = _FakeManager(d)
        out, _rows = fetch_csv_footage(self.scenes(), mgr, d, director=False, ai_cap=2)
        self.assertEqual(sorted(a[0] for a in mgr.asked), ["1", "2", "5"])          # scenes 3 and 4 are over the limit: no credits spent
        self.assertTrue(out[0]["footage_meta"].get("ai_generated"))
        self.assertFalse(out[2].get("footage"))
        self.assertEqual(ai_plan(self.scenes(), d, cap=2), {"make": ["3", "4"], "over": [], "have": 2, "credits": 20})   # made clips are free next time


class TestNoEmptyStretch(unittest.TestCase):
    def test_a_long_sentence_without_commas_still_gives_a_tag(self):
        from cinematic_explainer.war.direction import _phrase_or_lead

        self.assertEqual(_phrase_or_lead("Over the same few weeks Russia moved battalions toward the southern front near the river."),
                         "Over the same few weeks Russia")
        self.assertEqual(_phrase_or_lead("150 km up."), "150 km up")              # a natural phrase is still preferred
        self.assertEqual(_phrase_or_lead("Go now."), "")                          # too short: nothing invented


class TestBackdropGaps(unittest.TestCase):
    def test_gaps_are_filled_and_nothing_is_invented_over_footage(self):
        from cinematic_explainer.render import Shot
        from cinematic_explainer.war.backdrop import fill_gaps

        out = fill_gaps([Shot("a.mp4", 2.0, 4.0), Shot("b.mp4", 6.0, 8.0)], 10.0, "bd.mp4")
        self.assertEqual([(s.path, s.start, s.end) for s in out],
                         [("bd.mp4", 0.0, 2.0), ("a.mp4", 2.0, 4.0), ("bd.mp4", 4.0, 6.0), ("b.mp4", 6.0, 8.0), ("bd.mp4", 8.0, 10.0)])
        self.assertEqual(fill_gaps([], 5.0, "bd.mp4")[0].end, 5.0)          # no footage at all: one backdrop shot, not an empty timeline
        self.assertEqual([s.path for s in fill_gaps([Shot("a.mp4", 0.0, 4.0)], 4.0, "bd.mp4")], ["a.mp4"])   # no gap: nothing added
        self.assertEqual(fill_gaps([Shot("a.mp4", 1.0, 2.0)], 3.0, None)[0].path, "a.mp4")   # no backdrop available: unchanged

    def test_backdrop_clip_is_made_once(self):
        from cinematic_explainer.war.backdrop import ensure_backdrop

        d = Path(tempfile.mkdtemp())
        p1 = ensure_backdrop(d)
        self.assertTrue(p1 and Path(p1).is_file())
        m = Path(p1).stat().st_mtime_ns
        self.assertEqual(ensure_backdrop(d), p1)
        self.assertEqual(Path(p1).stat().st_mtime_ns, m)



class ExportPage(unittest.TestCase):
    def test_the_render_reports_to_the_export_page(self):
        text = (Path(__file__).resolve().parent / "cinematic_explainer" / "war" / "app_section.py").read_text(encoding="utf-8")
        for call in ("_track_generation_start(", "_track_generation_end(", "_export_progress("):
            self.assertIn(call, text)


if __name__ == "__main__":
    unittest.main()


class TestReopenedApp(unittest.TestCase):
    """Owner (2026-11-07): after reopening the app the Visuals tab stayed empty: the scenes CSV field was blank, so Render ran without it
    and planned the whole unpunctuated voiceover as one scene."""

    def test_the_project_remembers_its_scenes_file(self):
        from types import SimpleNamespace
        from cinematic_explainer.war.app_section import recall_scenes, remember_scenes

        root = Path(tempfile.mkdtemp())
        csv = root / "scenes.csv"
        csv.write_text("scene_no,text\n1,a\n", encoding="utf-8")
        app = SimpleNamespace(_workspace=SimpleNamespace(root=str(root)))
        self.assertEqual(recall_scenes(app), "")
        remember_scenes(app, str(csv))
        self.assertEqual(recall_scenes(app), str(csv))
        csv.unlink()
        self.assertEqual(recall_scenes(app), "")                              # a file that is gone is not brought back

    def test_whisper_words_without_punctuation_still_make_short_scenes(self):
        from cinematic_explainer.war.app_section import sentences_from_words

        words, t = [], 0.0
        for i in range(200):
            words.append([f"word{i}", t, t + 0.3])
            t += 0.3 + (0.4 if i % 15 == 14 else 0.02)                          # a breath every 15 words, no full stops
        sc = sentences_from_words(words, t)
        self.assertGreaterEqual(len(sc), 10)
        self.assertTrue(all(len(x["words"]) <= 28 for x in sc))
        self.assertTrue(all(abs(a["end"] - b["start"]) < 1e-9 for a, b in zip(sc, sc[1:])))


class TestStopReachesTheDownload(unittest.TestCase):
    """Owner (2026-11-07): scene 7 stayed PROCESSING (an archive.org download) and Stop / Change source waited on it: a run-level stop
    never aborts a download in flight, a scene stop does."""

    def test_war_stop_cancels_every_scene_it_is_fetching(self):
        import threading, time
        from cinematic_explainer.war.app_section import fetch_csv_footage

        class Slow(_FakeManager):
            def __init__(self, d):
                super().__init__(d)
                self.scene_stops, self.stopped = set(), threading.Event()

            def request_cancel_scene(self, n):
                self.scene_stops.add(str(n))
                self.stopped.set()

            def resolve_all(self, rows, **kw):          # a download that only ends when its scene is stopped
                self.stopped.wait(5)

        d = Path(tempfile.mkdtemp())
        mgr, t0 = Slow(d), time.time()
        fetch_csv_footage(TestCsvFootage().scenes(), mgr, d, director=False, cancel=lambda: True)
        self.assertLess(time.time() - t0, 3)
        self.assertEqual(mgr.scene_stops, {"1", "3"})

    def test_the_app_passes_a_rows_stop_to_the_style_fetch_manager(self):
        src = (Path(__file__).resolve().parent / "app.py").read_text(encoding="utf-8")
        self.assertIn('getattr(self, "_style_fetch_manager", None)', src)


class StyleRulesOnRetry(unittest.TestCase):
    """Ahmed test project (2026-11-08): Retry in the Visuals tab recorded 3.5 s YouTube clips (War needs 8 s) and reopened YouTube rows read
    'Local — Cancelled'."""

    def test_reopened_failed_scene_keeps_its_source(self):
        import app as A
        from providers.base import AssetSource

        row = SimpleNamespace(asset_type="youtube_video", prompt="x", stock=None)
        self.assertEqual(A._hydrated_failed_source({"status": "failed", "source": "youtube_video"}, row), AssetSource.YOUTUBE_VIDEO)

    def test_retry_manager_gets_war_rules_and_loses_them_after_war(self):
        import app as A
        from cinematic_explainer.war.app_section import WAR_YT_CLIP_S

        def build(*_a, **_k):
            return SimpleNamespace(images_dir=Path(tempfile.gettempdir()), settings={"gemini_enabled": True}, youtube_provider=SimpleNamespace(clip_duration=3.5),
                                   flow_video_provider=None, flow_image_provider=None, archive_provider=1, nasa_provider=1,
                                   local_provider=SimpleNamespace(library_dir=None), recovery=SimpleNamespace(skipped=set()))

        fake = SimpleNamespace(_asset_manager=None, _scene_rows=[], _war_active=True, _hydrated_skipped=set(), _build_asset_manager=build,
                               _production_mode_is_local=lambda: False, _local_assets_dir=lambda: None, _apply_footage_quality=lambda m: None)
        fake.youtube_provider = None
        m = A.VideoGeneratorApp._ensure_asset_manager(fake, Path(tempfile.gettempdir()))
        self.assertEqual(m.youtube_provider.clip_duration, WAR_YT_CLIP_S)
        self.assertFalse(m.settings["gemini_enabled"])
        fake._war_active = False
        m2 = A.VideoGeneratorApp._ensure_asset_manager(fake, Path(tempfile.gettempdir()))
        self.assertIsNot(m2, m)                                  # rebuilt with the app's own rules
        self.assertEqual(m2.youtube_provider.clip_duration, 3.5)
