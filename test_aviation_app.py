"""Aviation is wired in as a style: the picker lists it, app.py routes its buttons (additions only), its footage goes through the Visuals
tab, its render reports to the Export page, nothing starts on a file pick, and no Gemini anywhere."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class AviationWiring(unittest.TestCase):
    def test_picker_lists_it(self):
        from ui import style_registry as R
        self.assertIn("Aviation", dict(R.grouped(R.with_extras(("Normal video",)))).get("Documentary", []))
        self.assertIn("Aviation", R.EXTRA_BLURBS)
        self.assertIn("Aviation", R.EXTRA_CARDS)

    def test_app_routes_the_style(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        for needle in ("from ui import aviation_section as _av_section", "_av_section.activate(self)", "_av_section.deactivate(self)",
                       "_av_section.cta(self, action)", "_av_section.sync_cta(self)", '"_av_running"', 'return "Aviation"',
                       '"av_generate", "av_render", "av_cancel"', "_av_section.resume_on_open(self)", 'av_block.grid() if active == "Aviation"'):
            self.assertIn(needle, src)
        self.assertIn('"Aviation"', (ROOT / "ui" / "style_kit.py").read_text(encoding="utf-8"))

    def test_visuals_tab_and_export(self):
        import visual_bridge
        self.assertIn("aviation", visual_bridge.OWNERS)
        self.assertEqual(visual_bridge.OWNERS["aviation"][0], "_av_active")
        src = (ROOT / "ui" / "aviation_section.py").read_text(encoding="utf-8")
        self.assertIn("visual_bridge.fill(app, OWNER", src)
        self.assertIn('_track_generation_start("aviation")', src)
        self.assertIn("_track_generation_end(", src)
        self.assertIn("fetch=False", src)                     # Render uses what the Visuals tab holds, fetches nothing
        import export_state
        self.assertEqual(export_state.STYLE_LABELS.get("aviation"), "Aviation")

    def test_nothing_starts_on_pick(self):
        src = (ROOT / "ui" / "aviation_section.py").read_text(encoding="utf-8")
        browse = src.split("def _browse")[1].split("def copy_csv_prompt")[0]
        for word in ("_pakmap_get_words", "plan(", "fetch_csv_footage", "_start("):
            self.assertNotIn(word, browse)

    def test_war_only_parts_are_off(self):
        src = (ROOT / "ui" / "aviation_section.py").read_text(encoding="utf-8")
        for call in re.findall(r"fetch_csv_footage\([^)]*\)", src.replace("\n", " ")):
            self.assertIn("director=False", call)
            self.assertIn("library=False", call)
            self.assertIn("ai_cap=0", call)

    def test_no_gemini(self):
        for f in [ROOT / "ui" / "aviation_section.py", *sorted((ROOT / "aviation").glob("*.py"))]:
            self.assertNotRegex(f.read_text(encoding="utf-8"), r"(?i)(import\s+\S*(gemini|genai))|from\s+\S*(gemini|genai)|generativeai|gemini_client", f.name)

    def test_live_app_page(self):
        """The real app, off screen in a subprocess: the page shows, the main button says Generate scenes, Render waits for scenes,
        picking a voice-over starts nothing, and another style hides the page."""
        import sys
        import tempfile

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
    inst._on_style_pick("Aviation"); inst._style_browsing = False; inst._sync_style_picker(); inst._sync_primary_cta(); inst.update_idletasks()
    put("active", inst._active_style())
    put("block", inst._av_block.winfo_manager())
    put("cta", inst._cta_action)
    put("render", inst._av_render_btn.cget("state"))
    threads = threading.active_count()
    voice = tmp / "v.mp3"; voice.write_bytes(b"x")
    inst._av_voice_var.set(str(voice)); inst.update_idletasks()
    put("running_after_pick", inst._av_running)
    put("new_threads", threading.active_count() - threads)
    inst._on_style_pick("Normal video"); inst.update_idletasks()
    put("block_after_switch", inst._av_block.winfo_manager())
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
        self.assertEqual(got["active"], "Aviation")
        self.assertEqual(got["block"], "grid")
        self.assertEqual(got["cta"], "av_generate")
        self.assertEqual(got["render"], "disabled")
        self.assertEqual(got["running_after_pick"], "False")
        self.assertEqual(got["new_threads"], "0")
        self.assertEqual(got["block_after_switch"], "")
        self.assertNotEqual(got["active_after_switch"], "Aviation")

    def test_app_py_lines_only_added(self):
        try:
            diff = subprocess.run(["git", "diff", "HEAD", "--", "app.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        except Exception:  # noqa: BLE001
            self.skipTest("no git")
        removed = [l for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
        self.assertEqual(removed, [], "Aviation only adds lines to app.py")


if __name__ == "__main__":
    unittest.main()


class FlowRowPromptTests(unittest.TestCase):
    def test_visuals_flow_rows_get_the_aviation_look(self):
        from providers.base import SceneRow
        from ui import aviation_section as S
        from aviation import flow as FL
        r = SceneRow.from_csv_row({"scene_number": "9", "script_segment": "x", "asset_type": "flow_video",
                                   "prompt": "Vistara A320 taking off. cinematic documentary shot, desaturated muted colours, 35mm film grain"})
        S._aviation_prompts([r], [{"scene_no": 9, "text": "x", "asset_type": "flow_video", "prompt": "Vistara A320 taking off"}])
        self.assertIn(FL.LOOK, r.prompt)
        self.assertNotIn("film grain", r.prompt)
