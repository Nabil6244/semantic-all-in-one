"""Health Cinema as a style: registration and isolation (live app in a subprocess), five profiles, narration-aware planning, evidence flags,
landscape-only output, clip caching, 3D fallback, cancellation, packaging boundary, and (when the local evaluation asset and a narration are present)
a real render through the app's own Render button. No network."""
from __future__ import annotations

import json, os, re, shutil, subprocess, sys, tempfile, threading, unittest
from pathlib import Path

from health_cinema import assets, clips, engine, evidence, packaging, planner, profiles as P

ROOT = Path(__file__).resolve().parent
E2E_DIR = Path(os.environ.get("HEALTH_CINEMA_E2E_DIR", Path.home() / "HealthCinemaTools" / "e2e"))
ASSET_DIR = Path(os.environ.get("HEALTH_CINEMA_ASSET_DIR", Path.home() / "HealthCinemaTools" / "bench"))
HAVE_FFMPEG = bool(assets.ffmpeg_path())

_SCRIPT = r'''
import os, sys, tempfile, time, json
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
def shown(w): return bool(w.grid_info())

emit("not_loaded_at_start", not any(m.startswith("health_cinema") for m in sys.modules))
emit("choices_default_and_single_entry", inst.STYLE_CHOICES[0] == "Normal video" and inst.STYLE_CHOICES.count("Health Cinema") == 1
     and "Health Cinema" in inst.STYLE_BLURBS and "Health Cinema" in inst.STYLE_CARDS and "War Documentary" in inst.STYLE_CHOICES, str(inst.STYLE_CHOICES))
emit("starts_normal", inst._active_style() == "Normal video" and not getattr(inst, "_health_active", False))
inst._on_style_pick("Health Cinema"); inst.update_idletasks()
emit("picked", inst._active_style() == "Health Cinema" and inst._style_picker.get() == "Health Cinema" and shown(inst._health_block) and inst.generation_mode == "normal")
emit("loaded_only_now", any(m.startswith("health_cinema.app_section") for m in sys.modules))
emit("cta_needs_voiceover", inst._cta_action == "import_audio", str(getattr(inst, "_cta_action", None)))
emit("alone", not (shown(inst._overscaled_block) or shown(inst._pakmap_block) or shown(inst._hybrid_block) or shown(inst._starmap_block) or (getattr(inst, "_war_block", None) is not None and shown(inst._war_block))))
inst._on_style_pick("War Documentary"); inst.update_idletasks()
emit("war_replaces_health", inst._active_style() == "War Documentary" and not shown(inst._health_block) and not inst._health_active and shown(inst._war_block))
inst._on_style_pick("Health Cinema"); inst.update_idletasks()
emit("health_replaces_war", inst._active_style() == "Health Cinema" and not shown(inst._war_block) and shown(inst._health_block))
inst._on_style_pick("Normal video"); inst.update_idletasks()
emit("normal_replaces_health", inst._active_style() == "Normal video" and not shown(inst._health_block))
inst._on_style_pick("Health Cinema"); inst._health_running = True
inst._on_style_pick("Normal video"); inst.update_idletasks()
emit("running_keeps_style", inst._active_style() == "Health Cinema")
inst._health_running = False
inst._on_style_pick("Normal video"); inst.update_idletasks()

# real render through the app's own Render button (only when the e2e inputs exist)
e2e = os.environ.get("HEALTH_CINEMA_E2E_DIR")
if e2e and (Path(e2e) / "narration.wav").is_file():
    inst._on_style_pick("Health Cinema"); inst.update_idletasks()
    wav = ws.root / "audio" / "narration.wav"; wav.write_bytes((Path(e2e) / "narration.wav").read_bytes())
    inst.audio_var.set(str(wav)); inst._health_scenes_var.set(str(Path(e2e) / "sentences.json")); inst._health_preview_var.set(True)
    inst._health_profile_var.set("Medical Cinema")
    have_vo = inst._current_voiceover_path() is not None
    emit("e2e_voiceover_seen", have_vo, str(inst._current_voiceover_path()))
    if have_vo:
        inst._sync_primary_cta(); emit("e2e_cta_ready", inst._cta_action == "health_render", inst._cta_action)
        t0 = time.time(); inst._health_render_btn.invoke()
        def _poll():   # a real event loop (the worker reports through app.after); `update()` can spin forever on the app's own re-posting callbacks
            if (not inst._health_running and time.time() - t0 > 1) or time.time() - t0 > 300: inst.quit()
            else: inst.after(200, _poll)
        inst.after(200, _poll); inst.mainloop()
        out = Path(inst.output_var.get()); rep = Path(str(out) + ".health_cinema.json")
        emit("e2e_output_exists", out.is_file() and out.stat().st_size > 1000, f"{out} {inst._health_status_var.get()}")
        if out.is_file():
            import subprocess
            pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,codec_type", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout
            emit("e2e_is_720p_landscape", "video,1280,720" in pr and "audio" in pr, pr.replace("\n", " "))
        emit("e2e_report_written", rep.is_file(), str(rep))
        emit("e2e_status_done", inst._health_status_var.get().startswith("Done"), inst._health_status_var.get())
os._exit(0)
'''


class TestAppIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(tempfile.mkdtemp()) / "_health_picker_check.py"
        script.write_text(_SCRIPT, encoding="utf-8")
        env = dict(os.environ, HEALTH_CINEMA_ASSET_DIR=str(ASSET_DIR))
        if (E2E_DIR / "narration.wav").is_file() and HAVE_FFMPEG:
            env["HEALTH_CINEMA_E2E_DIR"] = str(E2E_DIR)
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, cwd=ROOT, env=env)
        cls._stdout, cls._stderr, cls._results = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[len("SKIP:"):])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1); name, _, detail = rest.partition(":"); cls._results[name] = (status == "PASS", detail)

    def _check(self, name):
        if name not in self._results:
            self.fail(f"subprocess never reported {name!r}\nstdout:\n{self._stdout[-1500:]}\nstderr:\n{self._stderr[-2500:]}")
        ok, detail = self._results[name]
        self.assertTrue(ok, f"{name} failed: {detail}\nstderr:\n{self._stderr[-2000:]}")

    def test_opt_in_lazy_and_default_unchanged(self):
        for n in ("not_loaded_at_start", "choices_default_and_single_entry", "starts_normal", "loaded_only_now"):
            with self.subTest(n): self._check(n)

    def test_picking_and_leaving(self):
        for n in ("picked", "cta_needs_voiceover", "alone", "war_replaces_health", "health_replaces_war", "normal_replaces_health", "running_keeps_style"):
            with self.subTest(n): self._check(n)

    def test_real_render_through_the_app_button(self):
        if "e2e_voiceover_seen" not in self._results: self.skipTest("end-to-end inputs not present on this machine")
        for n in ("e2e_voiceover_seen", "e2e_cta_ready", "e2e_output_exists", "e2e_is_720p_landscape", "e2e_report_written", "e2e_status_done"):
            with self.subTest(n): self._check(n)


class TestProfiles(unittest.TestCase):
    def test_five_profiles_share_one_engine(self):
        self.assertEqual(list(P.PROFILES), ["medical_cinema", "human_story", "future_science", "anatomy_explainer", "health_investigative"])
        for p in P.PROFILES.values():
            self.assertEqual(set(p.weights), set(P.SCENE_KINDS)); self.assertTrue(all(0 <= v <= 1 for v in p.weights.values()))
        self.assertEqual(P.get_profile("Medical Cinema").id, "medical_cinema")
        with self.assertRaises(KeyError): P.get_profile("nope")

    def test_profiles_differ_where_it_matters(self):
        self.assertEqual(max(P.PROFILES["medical_cinema"].weights, key=P.PROFILES["medical_cinema"].weights.get), "anatomy_3d")
        self.assertEqual(max(P.PROFILES["human_story"].weights, key=P.PROFILES["human_story"].weights.get), "footage")
        self.assertGreater(P.PROFILES["health_investigative"].weights["evidence_card"], P.PROFILES["medical_cinema"].weights["evidence_card"])
        self.assertTrue(P.PROFILES["health_investigative"].block_unsourced_stats)

    def test_accessible_type_sizes_at_1080p_and_scaling(self):
        for p in P.PROFILES.values():
            s = P.type_sizes(p, 1080)
            self.assertTrue(48 <= s["title"] <= 72 * 1.1, s); self.assertTrue(32 <= s["label"] <= 44 * 1.1, s); self.assertTrue(28 <= s["caption"] <= 36 * 1.1, s)
            self.assertLess(P.type_sizes(p, 720)["title"], s["title"]); self.assertGreaterEqual(P.type_sizes(p, 720)["caption"], 22)

    def test_motion_setting(self):
        self.assertEqual(P.with_motion(P.PROFILES["medical_cinema"], "still").motion, "still")
        with self.assertRaises(ValueError): P.with_motion(P.PROFILES["medical_cinema"], "wild")


class TestEvidence(unittest.TestCase):
    def codes(self, text, sources=None): return {f["code"] for f in evidence.analyze(text, sources)["flags"]}
    def test_unsourced_statistic_flagged_sourced_is_not(self):
        self.assertIn("stat_unsourced", self.codes("Thirty percent of adults, or 40% of men, have it."))
        self.assertNotIn("stat_unsourced", self.codes("About 40% of adults have it.", [{"title": "x", "population": "adults"}]))
    def test_medication_and_supplement_and_causal_and_preliminary(self):
        self.assertIn("medication_advice", self.codes("You can stop taking your pills if you eat this."))
        self.assertIn("supplement_claim", self.codes("This supplement helps."))
        self.assertIn("causal_wording", self.codes("Salt causes strokes."))
        self.assertIn("absolute_wording", self.codes("It always works."))
        self.assertEqual(evidence.analyze("In mice, an early study suggested a benefit.")["evidence_level"], "preliminary")
    def test_plain_sentence_has_no_flags_and_labels_are_honest(self):
        self.assertEqual(evidence.analyze("The heart has four chambers.")["flags"], [])
        self.assertIn("Not clinical", evidence.illustrative_label("anatomy_3d")); self.assertEqual(evidence.illustrative_label("text_card"), "")


def S(text, a, b, **kw): return dict(text=text, start=a, end=b, **kw)

class TestPlanner(unittest.TestCase):
    def test_heart_becomes_3d_only_when_the_asset_exists(self):
        s = [S("Your heart pumps blood through the arteries.", 0, 6)]
        self.assertEqual(planner.plan(s, "medical_cinema", assets_ok=True)["scenes"][0].kind, "anatomy_3d")
        sc = planner.plan(s, "medical_cinema", assets_ok=False)["scenes"][0]; self.assertEqual(sc.kind, "text_card")
    def test_organ_without_asset_is_not_faked(self):
        sc = planner.plan([S("The brain stores memory in many regions.", 0, 6)], "anatomy_explainer", assets_ok=True)["scenes"][0]
        self.assertNotEqual(sc.kind, "anatomy_3d"); self.assertIn("no_anatomy_asset:brain", {f["code"] for f in sc.flags})
    def test_statistics_need_a_source_to_become_a_stat_card(self):
        txt = "A study found 30% of adults had high blood pressure."
        sc = planner.plan([S(txt, 0, 6, sources=[{"title": "t", "population": "adults"}])], "health_investigative", assets_ok=True)["scenes"][0]
        self.assertEqual(sc.kind, "stat_card"); self.assertEqual(sc.visual["number"], "30")      # the number comes from the narration, never invented
        un = planner.plan([S(txt, 0, 6)], "health_investigative", assets_ok=True)["scenes"][0]
        self.assertNotEqual(un.kind, "stat_card"); self.assertIn("stat_unsourced", {f["code"] for f in un.flags})
    def test_claims_become_evidence_cards_in_investigative_profile(self):
        sc = planner.plan([S("Some people claim this herb cures everything.", 0, 6)], "health_investigative")["scenes"][0]
        self.assertEqual(sc.kind, "evidence_card")
    def test_profile_changes_the_visual_for_the_same_narration(self):
        s = [S("Patients walking each morning say they sleep better.", 0, 6, footage="/x.mp4")]
        self.assertEqual(planner.plan(s, "human_story")["scenes"][0].kind, "footage")
    def test_scenes_are_sentence_aligned_contiguous_and_not_too_short(self):
        s = [S("Your heart pumps blood.", 0, 2.0), S("It never rests.", 2.0, 3.5), S("The heart has valves.", 3.5, 9.0), S("Memory fades with age.", 9.0, 15.0)]
        sc = planner.plan(s, "medical_cinema", assets_ok=True)["scenes"]
        starts = {x["start"] for x in s}; ends = {x["end"] for x in s}
        for a in sc: self.assertIn(a.start, starts); self.assertIn(a.end, ends)
        for a, b in zip(sc, sc[1:]): self.assertEqual(a.end, b.start)
        self.assertEqual(sc[0].start, 0); self.assertEqual(sc[-1].end, 15.0)
    def test_anatomy_scenes_carry_the_illustrative_label_and_decision_log(self):
        r = planner.plan([S("The heart has four chambers.", 0, 6)], "medical_cinema", assets_ok=True)
        self.assertIn("illustration", r["scenes"][0].illustrative.lower()); self.assertTrue(r["scenes"][0].decisions)


class TestLandscapeAndBoundaries(unittest.TestCase):
    def test_only_16_9_sizes(self):
        for q, (w, h) in clips.SIZES.items(): self.assertAlmostEqual(w / h, 16 / 9, places=2)
        self.assertEqual(clips.SIZES["final"], (1920, 1080)); self.assertEqual(clips.SIZES["preview"], (1280, 720)); self.assertEqual(clips.FPS, 24)
    def test_portrait_quality_is_rejected(self):
        with self.assertRaises(ValueError): engine.run_health_cinema(tempfile.mkdtemp(), [S("Hi there you.", 0, 3)], "", "x.mp4", quality="portrait")
    def test_no_model_files_in_the_package_or_build_inputs(self):
        bad = [p for p in (ROOT / "health_cinema").rglob("*") if p.suffix.lower() in packaging.EXCLUDED_SUFFIXES]; self.assertEqual(bad, [])
        self.assertFalse([d for d, _ in packaging.data_files(ROOT) if Path(d).suffix.lower() in packaging.EXCLUDED_SUFFIXES])
        self.assertIn("health_cinema.engine", packaging.python_modules(ROOT))
    def test_only_app_and_tests_import_health_cinema(self):
        offenders = []
        for p in ROOT.glob("*.py"):
            if p.name in ("app.py",) or p.name.startswith("test_health_cinema"): continue
            if re.search(r"^\s*(from|import)\s+health_cinema\b", p.read_text(encoding="utf-8", errors="ignore"), re.M): offenders.append(p.name)
        self.assertEqual(offenders, [])
    def test_health_cinema_imports_no_other_style_package(self):
        pat = re.compile(r"^\s*(from|import)\s+(whatif|weather|hybrid|explainer|starmap|pakmap|cinematic_explainer|map_scene)\b", re.M)
        offenders = [p.name for p in (ROOT / "health_cinema").glob("*.py") if pat.search(p.read_text(encoding="utf-8"))]
        # app_section reaches pakmap word timings through the app object / a guarded import (documented), nothing else may
        self.assertEqual([o for o in offenders if o != "app_section.py"], [])
    def test_app_py_additions_only_for_health_cinema(self):
        r = subprocess.run(["git", "diff", "--unified=0", "--", "app.py"], capture_output=True, text=True, cwd=ROOT)
        removed = [l for l in r.stdout.splitlines() if l.startswith("-") and not l.startswith("---")]
        self.assertLessEqual(len(removed), 4, removed)            # one-line extensions of STYLE_CHOICES, a guard and _RUN_FLAGS only
        for l in removed: self.assertTrue(any(k in l for k in ("STYLE_CHOICES", "_war_running", "_RUN_FLAGS")) or l.strip().startswith('"_war_running"'), l)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class TestClipsCachingFallbackCancel(unittest.TestCase):
    def setUp(self): self.d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
    def scene(self, text="The heart has four chambers.", kind="text_card", **vis):
        return planner.Scene(1, 0.0, 2.0, text, kind, "medical_cinema", visual=vis or {"text": text})
    def test_card_clip_is_cached_and_invalidated(self):
        prof = P.get_profile("medical_cinema"); a = clips.render_scene(self.scene(), prof, self.d, quality="preview")
        self.assertFalse(a["cache_hit"]); self.assertTrue(Path(a["path"]).stat().st_size > 0)
        self.assertTrue(clips.render_scene(self.scene(), prof, self.d, quality="preview")["cache_hit"])
        b = clips.render_scene(self.scene("A different sentence entirely."), prof, self.d, quality="preview"); self.assertFalse(b["cache_hit"]); self.assertNotEqual(a["path"], b["path"])
        c = clips.render_scene(self.scene(), prof, self.d, quality="final"); self.assertFalse(c["cache_hit"])
    def test_clip_has_exact_frames_and_landscape_size(self):
        r = clips.render_scene(self.scene(), P.get_profile("medical_cinema"), self.d, quality="preview")
        out = subprocess.run([assets.ffmpeg_path().replace("ffmpeg", "ffprobe") if "ffmpeg" in assets.ffmpeg_path() else "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                              "-show_entries", "stream=width,height,nb_read_frames", "-of", "csv=p=0", r["path"]], capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "1280,720,48")
    def test_3d_scene_falls_back_to_a_card_without_assets(self):
        old = os.environ.get("HEALTH_CINEMA_ASSET_DIR"); os.environ["HEALTH_CINEMA_ASSET_DIR"] = str(self.d / "none")
        try:
            r = clips.render_scene(self.scene(kind="anatomy_3d", organ="heart", template="heart_journey"), P.get_profile("medical_cinema"), self.d, quality="preview")
        finally:
            os.environ.pop("HEALTH_CINEMA_ASSET_DIR") if old is None else os.environ.__setitem__("HEALTH_CINEMA_ASSET_DIR", old)
        self.assertEqual(r["used_kind"], "text_card"); self.assertIn("not available", r["fallback"]); self.assertTrue(Path(r["path"]).is_file())
    def test_3d_worker_failure_falls_back_instead_of_stopping(self):
        (self.d / "a").mkdir(); (self.d / "a" / "chest.glb").write_bytes(b"x"); (self.d / "a" / "anchors.json").write_text(json.dumps({"anchors": {"body": {"center": [0, 0, 0.9]}, "chest": {"center": [0, 0, 1.2]}, "heart": {"center": [0, 0, 1.3]}, "lungs": {"center": [0, 0, 1.3]}}}))
        old = os.environ.get("HEALTH_CINEMA_ASSET_DIR"); os.environ["HEALTH_CINEMA_ASSET_DIR"] = str(self.d / "a")
        def boom(*a, **k): raise RuntimeError("renderer died")
        try:
            r = clips.render_scene(self.scene(kind="anatomy_3d", organ="heart", template="heart_journey"), P.get_profile("medical_cinema"), self.d, quality="preview", frame_renderer=boom)
        finally:
            os.environ.pop("HEALTH_CINEMA_ASSET_DIR") if old is None else os.environ.__setitem__("HEALTH_CINEMA_ASSET_DIR", old)
        self.assertEqual(r["used_kind"], "text_card"); self.assertIn("3D render failed", r["fallback"])
    def test_engine_cancel_leaves_no_output_and_no_temp(self):
        wav = self.d / "v.wav"; subprocess.run([assets.ffmpeg_path(), "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "10", str(wav)], check=True)
        sents = [S("First plain sentence is here today.", 0, 5), S("Second plain sentence follows right after.", 5, 10)]
        calls = {"n": 0}
        def cancel(): calls["n"] += 1; return calls["n"] > 1
        out = self.d / "o.mp4"
        with self.assertRaises(engine.Cancelled): engine.run_health_cinema(self.d, sents, str(wav), str(out), quality="preview", cancel_check=cancel)
        self.assertFalse(out.exists()); self.assertFalse(list((self.d / "state" / "health_cinema" / "preview").glob("hc_*")))
    def test_engine_end_to_end_text_only_and_second_run_is_all_cache_hits(self):
        wav = self.d / "v.wav"; subprocess.run([assets.ffmpeg_path(), "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "8", str(wav)], check=True)
        sents = [S("The brain stores memory in many regions.", 0, 4), S("A large study found that 30% of adults agreed.", 4, 8, sources=[{"title": "t", "population": "adults"}])]
        r1 = engine.run_health_cinema(self.d, sents, str(wav), str(self.d / "o.mp4"), profile="health_investigative", quality="preview")
        self.assertEqual(r1["size"], [1280, 720]); self.assertFalse(any(s["cache_hit"] for s in r1["scenes"]))
        r2 = engine.run_health_cinema(self.d, sents, str(wav), str(self.d / "o2.mp4"), profile="health_investigative", quality="preview")
        self.assertTrue(all(s["cache_hit"] for s in r2["scenes"])); self.assertTrue(Path(str(self.d / "o.mp4") + ".health_cinema.json").is_file())
        self.assertIn("no_anatomy_asset:brain", {f["code"] for f in r1["review_flags"]})


@unittest.skipUnless(HAVE_FFMPEG and (ASSET_DIR / "chest.glb").is_file() and assets.threejs_ready(), "local 3D evaluation asset or Node/three.js not present")
class TestReal3DScene(unittest.TestCase):
    def test_heart_scene_renders_through_threejs_and_is_cached(self):
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        old = os.environ.get("HEALTH_CINEMA_ASSET_DIR"); os.environ["HEALTH_CINEMA_ASSET_DIR"] = str(ASSET_DIR)
        try:
            sc = planner.Scene(1, 0.0, 5.0, "The heart.", "anatomy_3d", "medical_cinema", visual={"organ": "heart", "template": "heart_journey"}, illustrative="3D illustration. Not clinical imagery.")
            a = clips.render_scene(sc, P.get_profile("medical_cinema"), d, quality="preview"); b = clips.render_scene(sc, P.get_profile("medical_cinema"), d, quality="preview")
        finally:
            os.environ.pop("HEALTH_CINEMA_ASSET_DIR") if old is None else os.environ.__setitem__("HEALTH_CINEMA_ASSET_DIR", old)
        self.assertEqual(a["used_kind"], "anatomy_3d", a); self.assertFalse(a["cache_hit"]); self.assertTrue(b["cache_hit"])


if __name__ == "__main__":
    unittest.main()
