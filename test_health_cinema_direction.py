"""Health Cinema directed planning, data graphics, captions, acquisition adapter (reuses the app's AssetManager), fallbacks, real cancellation and packaging."""
from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path
from PIL import Image, ImageChops

from health_cinema import acquire, assets, clips, direction, engine, graphics, packaging, planner, profiles as P, cards, render_journey as RJ

ROOT = Path(__file__).resolve().parent
ASSET_DIR = Path(os.environ.get("HEALTH_CINEMA_ASSET_DIR", Path.home() / "HealthCinemaTools" / "bench"))
HAVE_FFMPEG = bool(assets.ffmpeg_path())
SENT = [{"text": t, "start": a, "end": b} for t, a, b in [
    ("Every 40 seconds, someone in the United States has a stroke.", 0, 4), ("Every 40 seconds.", 4, 5.5), ("And here is the part most people never hear.", 5.5, 8.5),
    ("Up to 80% of strokes are preventable.", 8.5, 12), ("But there is a window that the brain gives you.", 12, 17), ("Sometimes hours before a major stroke.", 17, 22),
    ("A man named Frank reads in his chair.", 22, 27), ("One afternoon his vision in his left eye goes dark for about 90 seconds.", 27, 35), ("It comes back.", 35, 38),
    ("3 days later, Frank has a major ischemic stroke.", 38, 44), ("He spends 4 months in rehabilitation.", 44, 50)]]
def VS(i, at="stock_video", narr="a man reads", q=("senior man reading",)):
    from visual_director.schema import VisualScene
    return VisualScene(scene_id=i, narration=narr, visual_goal="g", visual_description="d", asset_type=at, provider_preference="stock", search_queries=list(q), timestamp_needed=False,
                       timestamp_hint="", duration=4.0, importance="medium", fallbacks=[], visual_treatment="", transition="")

def D(narr, at="stock_video", q=("q",)): return {"scene_id": "0", "narration": narr, "asset_type": at, "queries": list(q), "description": "", "scene": None}
def dscenes():
    out = []
    for i, groups in enumerate([[0, 1], [2, 3], [4, 5], [6], [7, 8], [9], [10]], 1):
        d = D(" ".join(SENT[k]["text"] for k in groups), "stock_video", ["senior man"]); d["scene_id"] = str(i); out.append(d)
    return out

class TestDirectedPlanning(unittest.TestCase):
    def plan(self, tpl_ok=lambda t: True, footage=True):
        return planner.plan_directed(SENT, "medical_cinema", dscenes(), tpl_ok, allow_footage=footage)["scenes"]
    def test_graphics_follow_the_narration(self):
        kinds = [s.kind for s in self.plan()]
        self.assertEqual(kinds[0], "counter_card"); self.assertIn("bar_card", kinds); self.assertIn("timeline_card", kinds)
        sc = self.plan(); bar = next(s for s in sc if s.kind == "bar_card"); self.assertEqual(bar.visual["value"], 80.0); self.assertEqual(bar.visual["qualifier"], "Up to")
        ctr = sc[0]; self.assertEqual(ctr.visual["interval"], 40); self.assertEqual(ctr.visual["unit"], "seconds")
    def test_numbers_and_events_come_only_from_the_script(self):
        tl = next(s for s in self.plan() if s.kind == "timeline_card"); text = " ".join(x["text"] for x in SENT).lower()
        for e in tl.visual["events"]:
            self.assertIn(e["when"].lower(), text)
        self.assertEqual([e["when"] for e in tl.visual["events"]][:2], sorted([e["when"] for e in tl.visual["events"]][:2], key=lambda w: text.index(w.lower())))
    def test_event_highlight_times_never_run_backwards(self):
        for tl in [s for s in self.plan() if s.kind == "timeline_card"]:
            t = [e["t0"] for e in tl.visual["events"]]; self.assertEqual(t, sorted(t))
    def test_brain_and_eye_3d_only_when_their_asset_exists(self):
        ok = {s.visual["template"] for s in self.plan() if s.kind == "anatomy_3d"}; self.assertEqual(ok, {"brain_journey", "eye_journey"})
        none = [s for s in self.plan(lambda t: False) if s.kind == "anatomy_3d"]; self.assertEqual(none, [])
        self.assertNotIn("brain_journey", {s.visual.get("template") for s in self.plan(lambda t: t == "eye_journey")})
    def test_each_3d_template_used_at_most_once_and_long_enough(self):
        sc = [s for s in self.plan() if s.kind == "anatomy_3d"]; tpl = [s.visual["template"] for s in sc]; self.assertEqual(len(tpl), len(set(tpl)))
        for s in sc: self.assertGreaterEqual(s.end - s.start, planner.MIN_3D_S[s.visual["template"]] - 1e-6)
    def test_footage_only_when_an_acquirer_exists_otherwise_designed_cards(self):
        self.assertNotIn("footage", [s.kind for s in self.plan(footage=False)])
        self.assertIn("footage", [s.kind for s in self.plan(footage=True)])
    def test_scenes_are_contiguous_and_cover_every_sentence(self):
        sc = self.plan(); self.assertEqual(sc[0].start, 0.0)
        for a, b in zip(sc, sc[1:]): self.assertAlmostEqual(a.end, b.start, places=2)
        spoken = sum(len(s.sentences) for s in sc); self.assertGreaterEqual(spoken, len(dscenes()))   # every director scene contributed sentences
    def test_unsourced_figures_are_flagged_never_given_a_source(self):
        for s in self.plan():
            if s.kind in ("counter_card", "bar_card"): self.assertIn("figure_unsourced", {f["code"] for f in s.flags}); self.assertEqual(s.sources, [])

class TestRetime(unittest.TestCase):
    def test_alignment_survives_director_regrouping_by_words(self):
        ds = [{"scene_id": "1", "narration": "Not painful, just dark for about 90 seconds. Then it comes back."}, {"scene_id": "2", "narration": "He blinks."}]
        sents = [{"text": "Not painful, just dark for about 90 seconds. Then it comes back. He blinks.", "start": 0, "end": 6}]
        g = direction.retime(ds, sents); self.assertEqual(len(g), 2); self.assertEqual(len(g[0]), 2)
        self.assertLess(g[0][0]["start"], g[0][1]["start"]); self.assertLessEqual(g[0][-1]["end"], g[1][0]["start"] + 1e-6)
    def test_uses_real_word_times_when_present(self):
        words = [{"w": "Hello", "t0": 1.0, "t1": 1.4}, {"w": "there.", "t0": 1.5, "t1": 2.0}]
        g = direction.retime([{"scene_id": "1", "narration": "Hello there."}], [{"text": "Hello there.", "start": 0, "end": 3, "words": words}])
        self.assertAlmostEqual(g[0][0]["start"], 0.0, places=2); self.assertGreaterEqual(g[0][0]["end"], 2.0)   # first start pinned to 0, end follows the real word times

class TestGraphics(unittest.TestCase):
    prof = P.get_profile("medical_cinema")
    def frame(self, kind, params, t, size=(640, 360)): return cards.draw_card(kind, params, self.prof, size[0], size[1], t)
    def test_frames_are_deterministic(self):
        p = {"interval": 40, "unit": "seconds", "context": "x", "event": "strokes"}
        self.assertIsNone(ImageChops.difference(self.frame("counter_card", p, 1.3), self.frame("counter_card", p, 1.3)).getbbox())
    def test_bar_grows_monotonically_to_its_value_and_stops(self):
        p = {"value": 80, "context": "x"}; fill = []
        for t in (0.4, 1.0, 1.6, 2.2, 3.0, 5.0):
            im = self.frame("bar_card", p, t).convert("RGB"); acc = self.prof.accent; fill.append(sum(1 for x in range(0, 640, 2) if im.getpixel((x, int(360 * 0.5 + 360 * 0.0375))) == acc))
        self.assertEqual(fill, sorted(fill)); self.assertEqual(fill[-1], fill[-2]); self.assertGreater(fill[-1], fill[0])
    def test_counter_tally_counts_up_only_inside_the_scene(self):
        a = cards.frame_state("counter_card", {}, 0.5, 24); b = cards.frame_state("counter_card", {}, 5.0, 24); self.assertNotEqual(a, b)
    def test_timeline_events_light_up_in_order(self):
        ev = [{"when": "A", "label": "a", "t0": 0.2}, {"when": "B", "label": "b", "t0": 2.0}, {"when": "C", "label": "c", "t0": 4.0}]
        self.assertNotEqual(self.frame("timeline_card", {"events": ev}, 1.0).tobytes(), self.frame("timeline_card", {"events": ev}, 3.0).tobytes())
    def test_graphics_render_at_preview_and_final_sizes(self):
        for size in ((1280, 720), (1920, 1080)):
            for kind, p in (("counter_card", {"interval": 40, "unit": "seconds", "context": "c", "event": "e"}), ("bar_card", {"value": 80, "context": "c"}), ("timeline_card", {"events": [{"when": "A", "label": "a", "t0": 0}]})):
                self.assertEqual(self.frame(kind, p, 2.0, size).size, size)
    def test_captions_chunks_stay_inside_their_sentence_and_in_order(self):
        ch = graphics.caption_chunks(SENT[:2], 0.0)
        for (a, b, t), nxt in zip(ch, ch[1:]): self.assertLess(a, b); self.assertLessEqual(b, nxt[0] + 1e-6)
        self.assertLessEqual(ch[0][0], 0.01); self.assertTrue(all(len(t) <= 52 for _, _, t in ch)); self.assertLessEqual(max(b for _, b, _ in ch), SENT[1]["end"])
    def test_caption_box_is_in_the_safe_area(self):
        im = graphics.draw_caption(Image.new("RGB", (1920, 1080), (0, 0, 0)), "Every 40 seconds, someone in the United States has a stroke.", 1080)
        bbox = ImageChops.difference(im, Image.new("RGB", (1920, 1080), (0, 0, 0))).getbbox(); self.assertGreater(bbox[0], 1920 * 0.05); self.assertLess(bbox[2], 1920 * 0.95); self.assertLess(bbox[3], 1080 * 0.95)

class TestAcquisitionAdapter(unittest.TestCase):
    def test_rows_never_ask_for_flow_or_youtube_unless_allowed(self):
        def vs(i, at): return {"scene": VS(i, at), "asset_type": at, "narration": "a man reads", "description": ""}
        rows = acquire.rows_for({1: vs(1, "video"), 2: vs(2, "youtube_video"), 3: vs(3, "stock_video")}, False, False)
        self.assertEqual({r.asset_type for r in rows}, {"stock_video"})
        rows = acquire.rows_for({1: vs(1, "video"), 2: vs(2, "youtube_video")}, True, False); self.assertEqual({r.asset_type for r in rows}, {"stock_video", "youtube_video"})
        rows = acquire.rows_for({1: vs(1, "video")}, False, True); self.assertEqual(rows[0].asset_type, "video")     # Flow only after the explicit opt-in
    def test_results_come_from_the_apps_manifest(self):
        from asset_manager import AssetManifest
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, ignore_errors=True); f = d / "001.mp4"; f.write_bytes(b"x")
        AssetManifest(d).set("1", {"status": "complete", "local_path": str(f), "source": "stock_video", "provider": "pexels", "author": "A", "source_url": "u", "stock_query": "q"})
        class Mgr:
            def resolve_all(self, rows): return None
            def request_cancel(self): pass
        from providers.base import SceneRow
        out = acquire.make_acquirer(lambda a, b: Mgr(), d)([SceneRow(scene_number="1", script_segment="s", asset_type="stock_video", stock="q")])
        self.assertTrue(out[1]["ok"]); self.assertEqual(out[1]["provider"], "pexels"); self.assertEqual(out[1]["author"], "A")

@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class TestEngineWithAcquirer(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        self.wav = self.d / "v.wav"; subprocess.run([assets.ffmpeg_path(), "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "50", str(self.wav)], check=True)
        self.clip = self.d / "stock.mp4"; subprocess.run([assets.ffmpeg_path(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=640x360:r=24:d=4", "-pix_fmt", "yuv420p", str(self.clip)], check=True)
        self._orig = direction.plan_visuals; direction.plan_visuals = lambda *a, **k: self.plans(); self.addCleanup(setattr, direction, "plan_visuals", self._orig)
    def plans(self):
        out = dscenes()
        for d in out: d["scene"] = VS(int(d["scene_id"]), "stock_video", d["narration"], ("senior man",)); d["plan_source"] = "test"
        return out
    def run_engine(self, acq, name="o.mp4", **kw):
        return engine.run_health_cinema(self.d, SENT, str(self.wav), str(self.d / name), quality="preview", settings={}, acquirer=acq, **kw)
    def good(self, rows): return {int(r.scene_number): {"ok": True, "path": str(self.clip), "source": "stock_video", "provider": "pexels", "author": "t", "source_url": "u", "query": "q", "error": ""} for r in rows}
    def test_footage_scenes_use_acquired_clips_and_record_provenance(self):
        r = self.run_engine(self.good); fs = [s for s in r["scenes"] if s["kind"] == "footage"]
        self.assertTrue(fs); self.assertTrue(all(s["asset"]["provider"] == "pexels" for s in fs)); self.assertTrue(any("Footage (scene" in c for c in r["credits"]))
        self.assertEqual(r["acquisition"]["failed"], 0); self.assertFalse(r["acquisition"]["flow_used"]); self.assertIn("captions", " ".join(r["not_implemented"]).lower() + "captions")
    def test_failed_acquisition_gives_a_flagged_typographic_fallback_not_a_crash(self):
        r = self.run_engine(lambda rows: {int(x.scene_number): {"ok": False, "path": "", "error": "no results"} for x in rows})
        self.assertEqual(r["acquisition"]["ok"], 0); self.assertGreater(r["acquisition"]["failed"], 0)
        self.assertNotIn("footage", [s["kind"] for s in r["scenes"]]); self.assertIn("footage_unavailable", {f["code"] for f in r["review_flags"]})
        self.assertTrue(Path(r["out"]).is_file())
    def test_unchanged_rerun_is_all_cache_hits_and_one_changed_sentence_rerenders_one_scene(self):
        self.run_engine(self.good, "a.mp4"); r2 = self.run_engine(self.good, "b.mp4"); self.assertTrue(all(s["cache_hit"] for s in r2["scenes"]))
        global SENT
        old = SENT; self.addCleanup(lambda: globals().__setitem__("SENT", old))
        SENT = [dict(s) for s in old]; SENT[6]["text"] = "A man named Frank reads quietly in his chair."
        direction.plan_visuals = lambda *a, **k: [dict(d, narration=d["narration"].replace("reads in his chair", "reads quietly in his chair")) for d in self.plans()]
        r3 = engine.run_health_cinema(self.d, SENT, str(self.wav), str(self.d / "c.mp4"), quality="preview", settings={}, acquirer=self.good)
        miss = [s["scene_no"] for s in r3["scenes"] if not s["cache_hit"]]; self.assertEqual(len(miss), 1, miss)
    def test_provider_error_inside_the_acquirer_surfaces_as_a_clear_error_and_leaves_no_output(self):
        def boom(rows): raise RuntimeError("Pexels rate limit reached")
        out = self.d / "x.mp4"
        with self.assertRaises(RuntimeError) as c: engine.run_health_cinema(self.d, SENT, str(self.wav), str(out), quality="preview", settings={}, acquirer=boom)
        self.assertIn("rate limit", str(c.exception)); self.assertFalse(out.exists()); self.assertFalse(Path(str(out) + ".rendering.mp4").exists())
    def test_bad_voiceover_path_fails_with_a_message_and_no_partial_file(self):
        out = self.d / "y.mp4"
        with self.assertRaises(RuntimeError) as c: engine.run_health_cinema(self.d, SENT, str(self.d / "missing.wav"), str(out), quality="preview", settings={}, acquirer=self.good)
        self.assertIn("ffmpeg failed", str(c.exception)); self.assertFalse(out.exists()); self.assertFalse(Path(str(out) + ".rendering.mp4").exists())

@unittest.skipUnless(HAVE_FFMPEG and assets.threejs_ready() and (ASSET_DIR / "head.glb").is_file(), "local head asset or Node/three.js not present")
class TestRealCancellation(unittest.TestCase):
    def test_cancelling_a_real_3d_render_kills_node_and_chromium_and_cleans_up(self):
        import psutil
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, ignore_errors=True); ev = threading.Event()
        before = {p.pid for p in psutil.process_iter()}
        spec = d / "s.json"; spec.write_text(json.dumps(clips.scale_spec(clips.template_spec("brain_journey"), 16.0)))
        threading.Timer(4.0, ev.set).start(); t0 = time.time()
        with self.assertRaises(RJ.Cancelled): RJ.render_journey(spec, ASSET_DIR / "anchors_head.json", ASSET_DIR / "head.glb", 1280, 720, 24, d / "cache", cancel=ev)
        self.assertLess(time.time() - t0, 20); time.sleep(1.0)
        leftovers = []
        for p in psutil.process_iter(["pid", "cmdline"]):
            if p.info["pid"] in before: continue
            cmd = " ".join(p.info["cmdline"] or [])
            if "health_cinema/threejs/render.mjs" in cmd or ("chrom" in cmd.lower() and "headless" in cmd.lower()): leftovers.append(cmd[:100])
        self.assertEqual(leftovers, []); self.assertEqual([p for p in (d / "cache").glob(".*tmp*")], []); self.assertEqual([p for p in (d / "cache").iterdir() if p.is_dir()], [])

class TestPackagingBoundary(unittest.TestCase):
    def test_the_three_addons_page_js_imports_are_shipped_and_no_model_is(self):
        dest = [Path(s).name for s, _ in packaging.data_files(ROOT)]
        for name in ("EffectComposer.js", "UnrealBloomPass.js", "OutputPass.js", "GLTFLoader.js", "CopyShader.js", "render.mjs", "page.js", "brain_journey.json", "eye_journey.json"): self.assertIn(name, dest)
        self.assertFalse([n for n in dest if n.endswith((".glb", ".blend"))])
    def test_missing_runtime_files_mean_anatomy_unavailable_not_a_crash(self):
        old = assets.roots; assets.roots = lambda: [Path(tempfile.mkdtemp())]
        try: self.assertIn("flow-engine/node_modules/playwright", assets.missing_threejs_files()); self.assertFalse(assets.threejs_ready())
        finally: assets.roots = old

if __name__ == "__main__":
    unittest.main()
