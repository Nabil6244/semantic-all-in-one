"""Ocean Predators is wired in as a style: the picker lists it, app.py routes its buttons (additions only), its render reports
to the Export page, nothing starts on a file pick, no Gemini anywhere, and a tiny film renders end to end."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _scenes(text, wps=2.6):
    import re
    out, t = [], 0.0
    for i, s in enumerate(x.strip() for x in re.split(r"(?<=[.?!])\s+", text) if x.strip()):
        d = len(s.split()) / wps
        words, k = [], t
        for w in s.split():
            dw = d / len(s.split())
            words.append((w, k, k + dw))
            k += dw
        out.append({"scene_no": i + 1, "text": s, "start": t, "end": t + d, "words": words})
        t += d
    return out


class OceanWiring(unittest.TestCase):
    def test_picker_lists_it(self):
        from ui import style_registry as R
        self.assertIn("Ocean Predators", dict(R.grouped(R.with_extras(("Normal video",)))).get("Explainers", []))
        self.assertIn("Ocean Predators", R.EXTRA_BLURBS)
        self.assertIn("Ocean Predators", R.EXTRA_CARDS)

    def test_app_routes_the_style(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        for needle in ("from ui import ocean_section as _oc_section", "_oc_section.activate(self)", "_oc_section.deactivate(self)",
                       "_oc_section.cta(self, action)", "_oc_section.sync_cta(self)", '"_oc_running"', 'return "Ocean Predators"',
                       '"oc_generate", "oc_render", "oc_cancel"', "_oc_section.resume_on_open(self)",
                       'oc_block.grid() if active == "Ocean Predators"'):
            self.assertIn(needle, src)
        self.assertIn('"Ocean Predators"', (ROOT / "ui" / "style_kit.py").read_text(encoding="utf-8"))

    def test_export_page(self):
        src = (ROOT / "ui" / "ocean_section.py").read_text(encoding="utf-8")
        self.assertIn('_track_generation_start("ocean")', src)
        self.assertIn("_track_generation_end(", src)
        import export_state
        self.assertEqual(export_state.STYLE_LABELS.get("ocean"), "Ocean Predators")

    def test_nothing_starts_on_pick(self):
        src = (ROOT / "ui" / "ocean_section.py").read_text(encoding="utf-8")
        browse = src.split("def _browse")[1].split("# ----")[0]
        for word in ("_pakmap_get_words", "plan_film", "render_film", "_start("):
            self.assertNotIn(word, browse)

    def test_no_gemini(self):
        for f in [ROOT / "ui" / "ocean_section.py", *sorted((ROOT / "ocean").glob("*.py"))]:
            self.assertNotRegex(f.read_text(encoding="utf-8"),
                                r"(?i)(import\s+\S*(gemini|genai))|from\s+\S*(gemini|genai)|generativeai|gemini_client", f.name)

    def test_app_py_lines_only_added(self):
        try:
            diff = subprocess.run(["git", "diff", "HEAD", "--", "app.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        except Exception:  # noqa: BLE001
            self.skipTest("no git")
        removed = [l for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
        self.assertEqual(removed, [], "Ocean Predators only adds lines to app.py")

    def test_live_app_page(self):
        """The real app, off screen in a subprocess: the page shows, the main button says Generate, Render waits for a plan,
        picking a voice-over starts nothing, and another style hides the page."""
        script = r'''
import os, sys, tempfile, threading
from pathlib import Path
sys.path.insert(0, os.getcwd())
try:
    import app as _app
except ModuleNotFoundError as exc:
    open(sys.argv[1], "w").write(f"SKIP|{exc}\n"); os._exit(0)
from project_workspace import ProjectWorkspace
_iso = Path(tempfile.mkdtemp()) / "settings.json"; _app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    open(sys.argv[1], "w").write(f"SKIP|{exc}\n"); os._exit(0)
_app.messagebox.showinfo = lambda *a, **k: None; _app.messagebox.showerror = lambda *a, **k: None
tmp = Path(tempfile.mkdtemp()); ws = ProjectWorkspace(project_id="p1", title="T", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow", "state"): (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws; inst.update_idletasks()
R = open(sys.argv[1], "w")
def put(k, v): R.write(f"{k}|{v}\n"); R.flush()
try:
    inst._on_style_pick("Ocean Predators"); inst._style_browsing = False; inst._sync_style_picker(); inst._sync_primary_cta(); inst.update_idletasks()
    put("active", inst._active_style())
    put("block", inst._oc_block.winfo_manager())
    put("cta", inst._cta_action)
    put("render", inst._oc_render_btn.cget("state"))
    threads = threading.active_count()
    voice = tmp / "v.mp3"; voice.write_bytes(b"x")
    inst._oc_voice_var.set(str(voice)); inst.update_idletasks()
    put("running_after_pick", inst._oc_running)
    put("new_threads", threading.active_count() - threads)
    inst._on_style_pick("Normal video"); inst.update_idletasks()
    put("block_after_switch", inst._oc_block.winfo_manager())
    put("active_after_switch", inst._active_style())
except Exception as exc:
    put("ERROR", f"{type(exc).__name__}: {exc}")
os._exit(0)
'''
        d = Path(tempfile.mkdtemp())
        (d / "s.py").write_text(script, encoding="utf-8")
        out = d / "out.txt"
        subprocess.run([sys.executable, str(d / "s.py"), str(out)], cwd=ROOT, timeout=600, capture_output=True)
        lines = out.read_text(encoding="utf-8").splitlines() if out.is_file() else []
        if lines and lines[0].startswith("SKIP|"):
            self.skipTest(lines[0][5:])
        got = dict(ln.split("|", 1) for ln in lines)
        self.assertNotIn("ERROR", got, got.get("ERROR"))
        self.assertEqual(got["active"], "Ocean Predators")
        self.assertEqual(got["block"], "grid")
        self.assertEqual(got["cta"], "oc_generate")
        self.assertEqual(got["render"], "disabled")
        self.assertEqual(got["running_after_pick"], "False")
        self.assertEqual(got["new_threads"], "0")
        self.assertEqual(got["block_after_switch"], "")
        self.assertNotEqual(got["active_after_switch"], "Ocean Predators")


class RunnerTest(unittest.TestCase):
    TEXT = ("Picture this. You're floating off the coast and below you is a great white shark. It has about 300 teeth. "
            "The first one is a bigger great white. The second one is the seal. Seals mob sharks in groups. "
            "The next one is the orca. In November 1997, two orcas killed a great white. Every shark fled the island. "
            "What would you do if you met one? Let us know in the comments.")

    def test_auto_chapters_follow_the_narration(self):
        from ocean import runner as RN
        sc = _scenes(self.TEXT, wps=1.2)          # slow, so chapters have room
        ch = RN.auto_chapters(sc)
        self.assertTrue(ch)
        starts = {round(s["start"], 3): s["text"] for s in sc}
        for c in ch:
            self.assertRegex(starts[round(c, 3)], r"(?i)^(the (first|second|next)|what would you)")

    def test_plan_saves_and_sound_plans(self):
        from ocean import runner as RN
        with tempfile.TemporaryDirectory() as td:
            r = RN.plan_film(_scenes(self.TEXT), td, "Test")
            self.assertGreater(r["shots"], 2)
            plan = RN.load_plan(td)
            self.assertEqual(plan["channel"], "Test")
            self.assertTrue(any(ly["name"] == "ocean.lay_captions" for ly in plan["layers"]))
            ev = RN.sound_events(plan)
            self.assertTrue(ev)
            for a, b in zip(ev, ev[1:]):
                self.assertLessEqual(a["t"], b["t"])
            beds = RN.music_plan(plan)
            self.assertTrue(beds)
            self.assertAlmostEqual(beds[0]["start"], 0.0)
            shots, layers = RN.timeline(plan, "black.mp4")
            self.assertAlmostEqual(shots[-1].end, plan["total"])
            self.assertEqual(len(layers), len(plan["layers"]))

    def test_tiny_film_renders_end_to_end(self):
        from ocean import runner as RN
        with tempfile.TemporaryDirectory() as td:
            sc = _scenes("A great white shark swims past. It has about 300 teeth.", wps=4.0)
            RN.plan_film(sc, td, "Test")
            voice = Path(td) / "voice.wav"
            total = sc[-1]["end"]
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={total + 0.5:.2f}",
                            str(voice)], check=True, timeout=60)
            out = Path(td) / "film.mp4"
            r = RN.render_film(td, str(voice), str(out), workers=2)
            self.assertTrue(out.is_file() and out.stat().st_size > 10000)
            self.assertAlmostEqual(r["seconds"], total, places=2)
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
                                   capture_output=True, text=True).stdout.split()
            self.assertEqual(sorted(probe), ["audio", "video"])
            self.assertTrue((Path(td) / "film_chapters.txt").is_file())


if __name__ == "__main__":
    unittest.main()
