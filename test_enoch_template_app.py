"""Enoch Template in the live app (same subprocess convention as test_style_picker.py): the picker card, persistence and
restore, exclusivity with Modern Tech, project-creation selection, the CSV-import path and the plan path, the Smart Editing
override, the prompt buttons -- and that other projects (Normal, Book of Enoch, Modern Tech) see none of it.
No network, no rendering, no paid call (the subprocess runs under NoPaidCalls)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = r'''
import json, os, sys, tempfile
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
from enoch_template_testutil import NoPaidCalls
from project_workspace import ProjectWorkspace
_iso = Path(tempfile.mkdtemp()) / "settings.json"
_app._settings_path = lambda: _iso
guard = NoPaidCalls().__enter__()
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)
_app.messagebox.showinfo = lambda *a, **k: None

def project(name, style=None):
    ws = ProjectWorkspace(project_id=name, title=name, seq=1, root=Path(tempfile.mkdtemp()) / name)
    for d in ("csv", "assets", "audio", "logs", "final", "flow", "state"):
        (ws.root / d).mkdir(parents=True, exist_ok=True)
    ws.set_video_style_settings(mode="manual" if style else "", style_id=style)
    return ws

def shown(w):
    return bool(w.grid_info())

ws = project("enoch_a")
inst._workspace = ws
inst.update_idletasks()
emit("card_exists", "Enoch Template" in inst.STYLE_CHOICES and "Enoch Template" in inst._style_cards, str(inst.STYLE_CHOICES))
emit("starts_normal", inst._active_style() == "Normal video" and not shown(inst._enoch_template_bar), inst._active_style())

inst._on_style_pick("Enoch Template"); inst.update_idletasks()
reread = ProjectWorkspace(project_id="enoch_a", title="enoch_a", seq=1, root=ws.root).video_style_settings()
emit("picked_sets_project_style", ws.video_style_settings()["style_id"] == "enoch_template" and reread["style_id"] == "enoch_template",
     str(reread))
emit("picked_is_normal_workflow", inst.generation_mode == "normal" and ws.editing_system() == "" and inst._active_style() == "Enoch Template"
     and inst._style_picker.get() == "Enoch Template", f"{inst.generation_mode} {ws.editing_system()!r} {inst._active_style()}")
emit("bar_shown_only_for_enoch", shown(inst._enoch_template_bar))

inst._on_style_pick("Modern Tech News"); inst.update_idletasks()
emit("modern_tech_is_exclusive_and_restores", ws.editing_system() == "modern_tech" and ws.video_style_settings()["style_id"] is None
     and inst._active_style() == "Modern Tech News" and not shown(inst._enoch_template_bar), str(ws.video_style_settings()))

boe = project("boe", "book_of_enoch")
inst._workspace = boe
emit("book_of_enoch_project_is_not_enoch_template", inst._active_style() == "Normal video" and not _app._enoch_template_active(inst))
inst._on_style_pick("Enoch Template"); inst._on_style_pick("Normal video")
emit("leaving_restores_the_previous_style", boe.video_style_settings()["style_id"] == "book_of_enoch", str(boe.video_style_settings()))

created = project("created", "enoch_template")
inst._workspace = created
inst._sync_style_picker(); inst.update_idletasks()
emit("project_creation_selection_is_followed", inst._active_style() == "Enoch Template" and inst._style_picker.get() == "Enoch Template")

# CSV path (the main path): refine runs inside _enforce_asset_mix_on_csv, cards land in the project's Images folder
rows = [("The Watchers descended in a storm of fire.", "flow_video", "winged figures descending"),
        ("Ethiopic manuscripts kept the book alive for centuries.", "flow_image", "old book"),
        ("A house of crystal stood among flames.", "flow_image", "crystal house in flames"),
        ("In 1947 shepherds found jars in a cave near the Dead Sea.", "flow_image", "cave"),
        ("The stars of heaven were imprisoned in the dark.", "flow_video", "stars in darkness"),
        ("Snow lay on the summit of Mount Hermon.", "flow_image", "snowy summit"),
        ("Light filled the hall.", "flow_image", "light"),
        ("The giants fought among themselves in the night.", "flow_video", "giants"),
        ("Scholars studied the Dead Sea Scrolls in Jerusalem.", "stock_video", "scholars"),
        ("A great abyss opened with pillars of fire.", "flow_video", "abyss")]
def write_csv(path):
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["scene_number", "script_segment", "asset_type", "prompt"])
        for i, (t, a, p) in enumerate(rows, 1):
            w.writerow([i, t, a, p])
def flows(path):
    import csv
    return sum(1 for r in csv.DictReader(open(path, encoding="utf-8")) if r["asset_type"] in ("flow_video", "flow_image", "video", "image"))

csv_a = created.root / "csv" / "plan.csv"; write_csv(csv_a)
inst._vo_mix_visual_plan = None; inst._visual_plan = None
before = flows(csv_a)
inst._enforce_asset_mix_on_csv(csv_a)
rep_path = created.state_dir / "enoch_template" / "plan_report.json"
rep = json.loads(rep_path.read_text(encoding="utf-8"))["report"] if rep_path.is_file() else {}
after = flows(csv_a)
emit("csv_path_refines_and_reports", rep_path.is_file() and rep.get("eligible_visual_scenes") == len(rows) and after <= before
     and after == rep.get("ai_scenes"), f"before={before} after={after} rep={rep}")
emit("csv_path_meets_ceiling_or_says_not", rep.get("ai_ceiling_met") == (rep.get("ai_scenes", 99) <= rep.get("ai_allowed", -1)), str(rep))

normal = project("normal_csv")
inst._workspace = normal
csv_n = normal.root / "csv" / "plan.csv"; write_csv(csv_n)
inst._vo_mix_visual_plan = None; inst._visual_plan = None
inst._enforce_asset_mix_on_csv(csv_n)
with_layer = csv_n.read_bytes()
write_csv(csv_n)
inst._vo_mix_visual_plan = None; inst._visual_plan = None
_real = _app._enoch_template_active
_app._enoch_template_active = lambda app: False          # the app exactly as it was before Enoch Template existed
try:
    inst._enforce_asset_mix_on_csv(csv_n)
finally:
    _app._enoch_template_active = _real
emit("csv_path_untouched_for_other_styles", not (normal.state_dir / "enoch_template").exists() and csv_n.read_bytes() == with_layer,
     "the CSV differs from the app without the Enoch layer")

# plan path: the same pass on a VisualDirector plan
from visual_director.schema import parse_visual_plan
inst._workspace = created
plan = parse_visual_plan({"title": "t", "scenes": [{"scene_id": i + 1, "narration": t, "visual_goal": t, "visual_description": p,
                          "asset_type": "image", "provider_preference": "flow_image"} for i, (t, a, p) in enumerate(rows)]})
inst._enoch_template_refine(plan, " ".join(r[0] for r in rows))
ai = sum(1 for s in plan.scenes if s.asset_type in ("image", "video"))
emit("plan_path_refines", ai <= len(rows) and ai < len(rows), f"ai={ai}")

# smart editing and prompts
s_on = inst._render_smart_editing_settings()
inst._workspace = normal
s_off = inst._render_smart_editing_settings()
emit("smart_editing_override_only_for_enoch", (s_on.scene_ambience, s_on.intensity) == (False, "low")
     and s_off == inst._smart_editing_settings(), f"{s_on} / {s_off}")
inst._workspace = created
inst._copy_csv_prompt("normal")
enoch_prompt = inst.clipboard_get()
inst._workspace = normal
inst._copy_csv_prompt("normal")
normal_prompt = inst.clipboard_get()
emit("csv_prompt_follows_the_style", "Enoch Template" in enoch_prompt and "Enoch Template" not in normal_prompt)
inst._workspace = created
inst._copy_enoch_template_prompt("research")
emit("research_prompt_copies_with_open_questions", "W-01" in inst.clipboard_get() and "ALWAYS \"unchecked\"" in inst.clipboard_get())
guard.__exit__(None, None, None)
emit("no_paid_or_network_calls", not guard.attempts, "; ".join(guard.attempts))
os._exit(0)
'''


class TestEnochTemplateApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(tempfile.mkdtemp()) / "_enoch_template_app_check.py"
        script.write_text(_SCRIPT, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                              cwd=Path(__file__).resolve().parent)
        cls._stdout, cls._stderr, cls._results = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[len("SKIP:"):])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._results[name] = (status == "PASS", detail)

    def _check(self, *names):
        for name in names:
            with self.subTest(name):
                if name not in self._results:
                    self.fail(f"subprocess never reported {name!r}\nstdout:\n{self._stdout[-1500:]}\nstderr:\n{self._stderr[-2500:]}")
                ok, detail = self._results[name]
                self.assertTrue(ok, f"{name} failed: {detail}\nstderr:\n{self._stderr[-1500:]}")

    def test_picker_selection_and_persistence(self):
        self._check("card_exists", "starts_normal", "picked_sets_project_style", "picked_is_normal_workflow", "bar_shown_only_for_enoch",
                    "modern_tech_is_exclusive_and_restores", "book_of_enoch_project_is_not_enoch_template",
                    "leaving_restores_the_previous_style", "project_creation_selection_is_followed")

    def test_both_planning_paths(self):
        self._check("csv_path_refines_and_reports", "csv_path_meets_ceiling_or_says_not", "csv_path_untouched_for_other_styles",
                    "plan_path_refines")

    def test_editing_prompts_and_cost(self):
        self._check("smart_editing_override_only_for_enoch", "csv_prompt_follows_the_style", "research_prompt_copies_with_open_questions",
                    "no_paid_or_network_calls")


if __name__ == "__main__":
    unittest.main()
