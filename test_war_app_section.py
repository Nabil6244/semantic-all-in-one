"""War Documentary in the style picker: opt-in, lazy (nothing of cinematic_explainer.war is imported until it is picked), one entry, the
default and every other style unchanged, a running render cannot be switched away from. Live app in a subprocess (same convention as
test_style_picker.py). Scene-building helpers are tested in-process. No network, no rendering."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
