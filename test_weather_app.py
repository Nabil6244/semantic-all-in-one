"""Weather in the app (phase 1B). Live VideoGeneratorApp in a subprocess (the convention of test_style_picker.py), twice:

  OFF (the default, settings without weather_enabled): the picker is exactly the 8 styles, no Weather card is built, the weather
       package is not even imported.
  ON  (weather_enabled true): the Weather card is a 9th card; picking it steps every other style aside and picking any other style
       steps Weather aside; a running Weather render keeps its style; reopening a project restores Weather; the shared Generate
       button routes to Weather; Load plan splits the AI's answer into the two files; the plan's full-screen footage becomes rows of
       the Visual Plan table; the main button walks voiceover -> plan -> data -> Generate.
No network, no rendering."""

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
ON = sys.argv[1] == "on"

def emit(name, ok, detail=""):
    sys.stdout.write(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}\n"); sys.stdout.flush()

try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}"); os._exit(0)
from project_workspace import ProjectWorkspace
_iso = Path(tempfile.mkdtemp()) / "settings.json"
if ON:   # unlocked the way the Settings switch does it: a test password's hash and its token
    from weather import lock as _lock
    _lock.UNLOCK_HASH = _lock.hash_password("test password")
    _iso.write_text(json.dumps({"weather_enabled": True, "weather_unlock": _lock.token(), "weather_nws_contact": "me@example.com"}), encoding="utf-8")
_app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)
_app.messagebox.showinfo = lambda *a, **k: None
_app.messagebox.showerror = lambda *a, **k: None
tmp = Path(tempfile.mkdtemp())
ws = ProjectWorkspace(project_id="p1", title="Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow", "state"):
    (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws
inst.update_idletasks()
shown = lambda w: bool(w.grid_info())

if not ON:
    emit("off_picker_is_the_nine_styles", tuple(inst._style_cards) == inst.STYLE_CHOICES and "Weather" not in inst.STYLE_CHOICES, str(tuple(inst._style_cards)))
    emit("off_no_weather_card", getattr(inst, "_weather_block", None) is None and inst._style_choices() == inst.STYLE_CHOICES)
    emit("off_weather_not_imported", not any(m == "weather" or m.startswith("weather.") for m in sys.modules), [m for m in sys.modules if m.startswith("weather")])
    inst._on_style_pick("pakMap")
    inst._on_style_pick("Normal video")
    emit("off_other_styles_still_switch", inst.generation_mode == "normal" and inst._style_picker.get() == "Normal video", inst.generation_mode)
    os._exit(0)

from weather import app_section as wx
emit("on_weather_is_the_ninth_card", tuple(inst._style_cards) == inst.STYLE_CHOICES + ("Weather",), str(tuple(inst._style_cards)))
emit("on_card_hidden_until_picked", not shown(inst._weather_block) and inst.generation_mode == "normal")

inst._on_style_pick("Weather")
emit("weather_picked", inst.generation_mode == "weather" and inst._style_picker.get() == "Weather" and shown(inst._weather_block)
     and shown(inst._weather_controls) and not shown(inst._pakmap_block) and not shown(inst._starmap_block), inst.generation_mode)
emit("weather_saves_its_state", json.loads((ws.root / "weather" / "weather.json").read_text()).get("active") is True)

inst._on_style_pick("Hybrid Map")
emit("other_style_steps_weather_aside", inst.generation_mode == "hybrid" and not inst._weather_enabled_var.get() and not shown(inst._weather_block)
     and json.loads((ws.root / "weather" / "weather.json").read_text()).get("active") is False, inst.generation_mode)

inst._on_style_pick("Weather")
inst._weather_running = True
inst._on_style_pick("pakMap")
emit("running_render_keeps_weather", inst.generation_mode == "weather", inst.generation_mode)
inst._weather_running = False

inst._on_style_pick("Normal video")
emit("normal_steps_weather_aside", inst.generation_mode == "normal" and not inst._weather_enabled_var.get(), inst.generation_mode)

# reopening a project whose style is Weather
(ws.root / "weather").mkdir(parents=True, exist_ok=True)
(ws.root / "weather" / "weather.json").write_text(json.dumps({"active": True, "sound_design": False}))
inst._restore_weather(ws)
emit("reopen_restores_weather", inst.generation_mode == "weather" and inst._weather_sound_var.get() is False, inst.generation_mode)

# Load plan: the AI's whole answer, both parts after their marker lines
BEATS = ("beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"
         'b1,beat,good morning everyone,map,hold,,Texas,region,,,"good morning everyone dallas stays hot this week",,,,,,,,,,,one\n'
         'b2,beat,feel the heat,footage,,,,,,,"feel the heat on the streets today",,,,,,,,,,,heat\n'
         "b2,clip,,,,,,,,,,,,,,,,,,stock_video:heat haze over a busy city street,,the heat\n")
LAYERS = ("beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n"
          'b1,dallas stays hot,,dal,temp_marker,"Dallas, TX","nws:forecast@Dallas,TX#day1",,,\n')
answer = tmp / "ai_answer.txt"
answer.write_text("Here is your plan.\n=== beats.csv ===\n```\n" + BEATS + "```\n=== weather_layers.csv ===\n" + LAYERS, encoding="utf-8")
ok = wx.load_plan(inst, [str(answer)])
p = wx.project(inst)
emit("load_plan_splits_the_answer", ok and p.beats_csv.read_text().strip() == BEATS.strip() and p.layers_csv.read_text().strip() == LAYERS.strip(),
     p.beats_csv.read_text()[:80] if p.beats_csv.is_file() else "no file")

# the main button walks the steps
inst._current_voiceover_path = lambda: None
inst._sync_primary_cta()
emit("cta_asks_for_the_voiceover", inst._cta_action == "import_audio", inst._cta_action)
vo = tmp / "vo.wav"; vo.write_bytes(b"x")
inst._current_voiceover_path = lambda: vo
inst._sync_primary_cta()
emit("cta_asks_for_the_data", inst._cta_action == "weather_fetch", inst._cta_action)
p.resolved_json.write_text("{}")
inst._sync_primary_cta()
emit("cta_ready_to_generate", inst._cta_action == "generate", inst._cta_action)

# the Generate button routes to Weather
called = []
wx.run_generation = lambda app: called.append(app)
inst._uhd_disk_ok = lambda: True
inst._on_generate()
emit("generate_routes_to_weather", called == [inst], str(called))

# the plan's footage becomes Visual Plan rows
from hybrid.beat_csv import plan_from_csv
words = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("good morning everyone dallas stays hot this week feel the heat on the streets today".split())]
plan = plan_from_csv(BEATS, words, 9.0)
wx.populate_visual_plan(inst, plan)
emit("footage_is_in_the_visual_plan", inst._scene_rows_owner == "weather" and len(inst._scene_rows) == 1
     and "heat haze" in (inst._scene_rows[0].stock or inst._scene_rows[0].prompt or ""), [(r.asset_type, r.stock, r.prompt) for r in inst._scene_rows])
emit("footage_folder_is_weathers", str(inst._scene_action_images_dir()).endswith(str(Path("weather") / "_work" / "media")),
     str(inst._scene_action_images_dir()))
inst._on_style_pick("Normal video")
emit("leaving_weather_clears_its_rows", inst._scene_rows_owner != "weather")
os._exit(0)
'''


def _run(mode: str) -> dict:
    script = Path(tempfile.mkdtemp()) / f"_weather_app_{mode}.py"
    script.write_text(_SCRIPT, encoding="utf-8")
    proc = subprocess.run([sys.executable, str(script), mode], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
                          cwd=Path(__file__).resolve().parent)
    results = {}
    for line in proc.stdout.splitlines():
        if line.startswith("SKIP:"):
            raise unittest.SkipTest(line[len("SKIP:"):])
        if line.startswith(("PASS:", "FAIL:")):
            status, rest = line.split(":", 1)
            name, _, detail = rest.partition(":")
            results[name] = (status == "PASS", detail)
    return {"results": results, "stdout": proc.stdout, "stderr": proc.stderr}


class _Base(unittest.TestCase):
    MODE = ""
    RUN: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.RUN = _run(cls.MODE)

    def check(self, name):
        r = self.RUN["results"]
        if name not in r:
            self.fail(f"subprocess never reported {name!r}\nstdout:\n{self.RUN['stdout'][-1500:]}\nstderr:\n{self.RUN['stderr'][-2500:]}")
        ok, detail = r[name]
        self.assertTrue(ok, f"{name} failed: {detail}\nstderr:\n{self.RUN['stderr'][-2000:]}")


class WeatherOff(_Base):
    MODE = "off"

    def test_the_app_is_as_before(self):
        for n in ("off_picker_is_the_nine_styles", "off_no_weather_card", "off_weather_not_imported", "off_other_styles_still_switch"):
            with self.subTest(n):
                self.check(n)


class WeatherOn(_Base):
    MODE = "on"

    def test_style_switching(self):
        for n in ("on_weather_is_the_ninth_card", "on_card_hidden_until_picked", "weather_picked", "weather_saves_its_state",
                  "other_style_steps_weather_aside", "running_render_keeps_weather", "normal_steps_weather_aside", "reopen_restores_weather"):
            with self.subTest(n):
                self.check(n)

    def test_plan_button_and_footage(self):
        for n in ("load_plan_splits_the_answer", "cta_asks_for_the_voiceover", "cta_asks_for_the_data", "cta_ready_to_generate",
                  "generate_routes_to_weather", "footage_is_in_the_visual_plan", "footage_folder_is_weathers", "leaving_weather_clears_its_rows"):
            with self.subTest(n):
                self.check(n)


if __name__ == "__main__":
    unittest.main()
