"""Normal (non-Overscaled) workflow: READY must mean "media for THIS row's
current prompt/query", and Generate must reuse exactly what READY shows.

Reproduced before the fix: a project whose scene 1 was generated from
"red sports car" and whose CSV was then re-imported/edited to "blue fishing
boat" still showed scene 1 as READY, and Generate reused the red-car file —
the old visual silently ended up in the new video.

A user's own Alternative / Change Source pick is also recorded under text
that differs from the CSV row, so those records are flagged ``user_override``
by AssetManager and are kept (not treated as stale).
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from asset_manager import AssetManager
from providers.base import AssetSource, SceneRow
from test_asset_pipeline import FakeProvider


class TestUserOverrideFlag(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images = self.tmp / "Images"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_change_source_result_is_flagged_as_the_users_choice(self):
        stock = FakeProvider(AssetSource.STOCK_IMAGE, {})
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
        mgr = AssetManager(self.images, stock_provider=stock, flow_image_provider=flow, log=lambda *_: None)
        row = SceneRow.from_csv_row({"scene_number": "1", "script_segment": "x", "asset_type": "image", "prompt": "a dam"})
        result = mgr.change_source(row, "stock_image")
        self.assertTrue(result.ok)
        self.assertTrue(mgr.manifest.get("1").get("user_override"))

    def test_a_normal_resolve_is_not_flagged(self):
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
        mgr = AssetManager(self.images, flow_image_provider=flow, log=lambda *_: None)
        row = SceneRow.from_csv_row({"scene_number": "1", "script_segment": "x", "asset_type": "image", "prompt": "a dam"})
        self.assertTrue(mgr.resolve_scene(row).ok)
        self.assertFalse(mgr.manifest.get("1").get("user_override"))


class TestMatchRule(unittest.TestCase):
    def setUp(self):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(str(exc))
        self.match = _app._manifest_record_matches_row

    def test_changed_prompt_is_stale(self):
        row = SceneRow(scene_number="1", script_segment="x", asset_type="image", prompt="blue fishing boat")
        self.assertFalse(self.match({"status": "complete", "prompt": "red sports car"}, row))

    def test_same_prompt_or_stock_query_matches(self):
        row = SceneRow(scene_number="1", script_segment="x", asset_type="stock_image", stock="harbor")
        self.assertTrue(self.match({"status": "complete", "prompt": "", "stock_query": "harbor"}, row))

    def test_user_override_is_kept_even_though_its_text_differs(self):
        row = SceneRow(scene_number="1", script_segment="x", asset_type="image", prompt="blue fishing boat")
        self.assertTrue(self.match({"status": "complete", "prompt": "night timelapse", "user_override": True}, row))


_LIVE = r'''
import os, sys, csv, tempfile
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())
def emit(n, ok, d=""): print(f"{'PASS' if ok else 'FAIL'}:{n}:{str(d)[:400]}")
from tkinter import messagebox
messagebox.showerror = messagebox.showinfo = lambda *a, **k: None
try:
    import app as _app
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)
from project_workspace import ProjectWorkspace
from asset_manager import AssetManifest
tmp = Path(tempfile.mkdtemp())
ws = ProjectWorkspace(project_id="p", title="t", seq=1, root=tmp / "ws")
ws.ensure_dirs()
inst._workspace = ws
inst.generation_mode = "normal"

def import_csv(prompt1, prompt2):
    src = tmp / f"plan_{prompt1[:3]}.csv"
    with open(src, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["scene_number", "script_segment", "asset_type", "prompt"])
        w.writerow(["1", "Scene one.", "image", prompt1]); w.writerow(["2", "Scene two.", "image", prompt2])
    dest = ws.copy_csv_in(src)
    inst.csv_var.set(str(dest))
    inst._scene_preview_cache_sig = None
    inst._refresh_scene_preview()

import_csv("red sports car", "mountain lake")
images = Path(inst.images_var.get())
images.mkdir(parents=True, exist_ok=True)
for n, prompt in (("1", "red sports car"), ("2", "mountain lake")):
    f = images / f"00{n}.png"; f.write_bytes(b"x")
    AssetManifest(images).set(n, {"status": "complete", "source": "flow_image", "asset_type": "image",
                                  "prompt": prompt, "local_path": str(f)})
inst._scene_preview_cache_sig = None
inst._refresh_scene_preview()
emit("first_import_rows_ready", inst._asset_results.get("001") is not None and inst._asset_results["001"].ok, "")

# Re-import with scene 1's prompt changed; scene 2 unchanged.
import_csv("blue fishing boat", "mountain lake")
emit("changed_row_is_no_longer_ready", inst._asset_results.get("001") is None, repr(inst._asset_results.get("001")))
emit("unchanged_row_stays_ready", inst._asset_results.get("002") is not None and inst._asset_results["002"].ok, "")

# A user's own Alternative pick (different text, flagged) stays READY.
rec = AssetManifest(images).get("1"); rec.update(prompt="red sports car", user_override=True)
AssetManifest(images).set("1", rec)
inst._scene_preview_cache_sig = None
inst._refresh_scene_preview()
emit("user_override_stays_ready_across_reload", inst._asset_results.get("001") is not None, "")
os._exit(0)
'''


class TestNormalWorkflowReadyIsHonest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys

        script = Path(tempfile.mkdtemp()) / "_stale_live.py"
        script.write_text(_LIVE, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120,
                              cwd=Path(__file__).resolve().parent)
        cls._out, cls._err, cls._res = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[5:])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._res[name] = (status == "PASS", detail)

    def _check(self, name):
        if name not in self._res:
            self.fail(f"never reported {name}\n{self._out}\n{self._err[-2000:]}")
        ok, detail = self._res[name]
        self.assertTrue(ok, f"{name}: {detail}")

    def test_first_import_rows_ready(self):
        self._check("first_import_rows_ready")

    def test_changed_row_is_no_longer_ready(self):
        self._check("changed_row_is_no_longer_ready")

    def test_unchanged_row_stays_ready(self):
        self._check("unchanged_row_stays_ready")

    def test_user_override_stays_ready_across_reload(self):
        self._check("user_override_stays_ready_across_reload")


if __name__ == "__main__":
    unittest.main()
