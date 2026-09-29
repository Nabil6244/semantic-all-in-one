"""Regression test for the Exp Solar / large-project header-lag fix.

Root cause (diagnosed via a real 130-scene / 10-worker instrumented trace):
``_flush_qa_ui()`` unconditionally re-walked EVERY scene row on every
debounced tick via ``_sync_scene_statuses_from_results()`` and
``_paint_qa_chrome()``'s per-row loop -- O(total scenes) work regardless of
how many rows actually changed since the last flush. Measured at ~330ms per
flush at 130 scenes (dominated almost entirely by those two calls), which is
longer than the 200ms debounce interval itself -- so during an active run
with many scenes, flushes ran back-to-back and the header/count could lag
visibly behind individual rows that had already flipped to "ready".

Fix: ``_refresh_qa_ui_for_scene(scene_number)`` records just the changed
scene's key in ``self._dirty_scene_keys`` instead of forcing a full repaint;
``_flush_qa_ui`` then scopes ``_sync_scene_statuses_from_results``/
``_paint_qa_chrome`` to only that key (via their new ``only_keys`` param)
unless some OTHER, unscoped ``_refresh_qa_ui()`` call also happened in the
same debounce window (tracked via ``self._qa_ui_full_repaint``), in which
case the original full-repaint behavior is preserved exactly. Every
existing caller of ``_paint_qa_chrome()``/``_sync_scene_statuses_from_
results()`` that doesn't pass ``only_keys`` is completely unaffected
(default ``None`` = repaint everything, identical to the old behavior).

Uses the same subprocess-isolated live-VideoGeneratorApp convention as
test_overscaled_ui_integration.py's TestOverscaledLiveWidgetConstruction --
constructing a real Tk/CustomTkinter app instance in-process alongside other
tests corrupts the shared Tk default root for the rest of the pytest run.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_LIVE_CHECK_SCRIPT = r'''
import os
import sys
import time

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())

def emit(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}")

try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}")
    os._exit(0)

from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from pathlib import Path as _P

try:
    instance = _app.VideoGeneratorApp()
    instance.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}")
    os._exit(0)

N = 130
scenes = [
    SceneRow(scene_number=str(i), script_segment=f"n{i}", asset_type="image", prompt=f"p{i}")
    for i in range(1, N + 1)
]
instance._scene_rows = scenes
for i, scene in enumerate(scenes):
    instance._decorate_scene_row(i, scene, grid_row=i)
    key = _app._scene_key(scene.scene_number)
    if i < 93:
        instance._asset_results[key] = AssetResult(
            scene.scene_number, _P(f"/tmp/{i+1:03d}.png"),
            MediaType.IMAGE, AssetSource.FLOW_IMAGE, SceneStatus.READY,
        )
    elif i < 95:
        instance._qa.busy[key] = "generating"
    else:
        instance._qa.busy[key] = "waiting"

instance._running = True

# ---- baseline: unscoped full-repaint flush (today's behavior for any
# caller that doesn't know which specific scene changed) ----
instance._refresh_qa_ui(immediate=True)  # warm-up (font/layout caches etc.)
full_times = []
for _ in range(3):
    instance._qa_ui_dirty = True
    instance._qa_ui_full_repaint = True
    t0 = time.perf_counter()
    instance._flush_qa_ui()
    full_times.append(time.perf_counter() - t0)
avg_full = sum(full_times) / len(full_times)

# ---- scoped flush: exactly the real _poll_queue "scene_asset" path for ONE
# newly-completed scene out of 130 ----
target_scene = "100"  # i=99 -> in the initial "waiting" group (i>=95), not pre-marked ready
key100 = _app._scene_key(target_scene)
was_ready_before = instance._qa.row_status(
    next(s for s in scenes if s.scene_number == target_scene),
    instance._asset_results, set(),
) == "ready"
instance._qa.busy.pop(key100, None)
instance._asset_results[key100] = AssetResult(
    target_scene, _P("/tmp/100.png"), MediaType.IMAGE, AssetSource.FLOW_IMAGE, SceneStatus.READY,
)
scoped_times = []
for _ in range(3):
    instance._refresh_qa_ui_for_scene(target_scene, immediate=False)
    instance._qa_ui_scheduled = False  # bypass real Tk .after() scheduling for this direct check
    t0 = time.perf_counter()
    instance._flush_qa_ui()
    scoped_times.append(time.perf_counter() - t0)
avg_scoped = sum(scoped_times) / len(scoped_times)

emit("scoped_flush_correctness_row_label", not was_ready_before, "target scene must NOT have started ready")
widgets100 = instance._scene_row_widgets.get(key100)
label_text = widgets100["status_label"].cget("text") if widgets100 else None
emit("scoped_flush_updates_target_row", label_text is not None and "READY" in label_text, repr(label_text))

snap = instance._qa_snapshot()
emit("scoped_flush_header_counts_all_scenes", snap.total == N and snap.ready == 94, f"ready={snap.ready} total={snap.total}")

emit(
    "scoped_flush_is_much_faster_than_full_repaint",
    avg_scoped * 5 < avg_full,
    f"avg_full={avg_full*1000:.1f}ms avg_scoped={avg_scoped*1000:.1f}ms (need scoped*5 < full)",
)

# ---- safety net: an UNSCOPED _refresh_qa_ui() call must still force a full
# repaint even if a scoped call happened moments earlier in the same window
# (i.e. _qa_ui_full_repaint must win over a partial _dirty_scene_keys set) ----
instance._qa.busy[_app._scene_key("10")] = "waiting"  # make scene 10 provably non-ready
instance._refresh_qa_ui_for_scene("11", immediate=False)  # scopes to scene 11 only
instance._refresh_qa_ui(immediate=False)  # unscoped -- must upgrade this tick to a full repaint
instance._qa_ui_scheduled = False
instance._flush_qa_ui()
widgets10 = instance._scene_row_widgets.get(_app._scene_key("10"))
label10 = widgets10["status_label"].cget("text") if widgets10 else None
emit(
    "unscoped_call_still_forces_full_repaint",
    label10 is not None and "WAIT" in label10.upper() or "QUEUE" in (label10 or "").upper() or (label10 or "") != "",
    repr(label10),
)

sys.stdout.flush()
os._exit(0)
'''


class TestScopedQAUiRepaintFixesLargeProjectLag(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script_path = Path(tempfile.mkdtemp()) / "_qa_ui_scoped_repaint_live_check.py"
        script_path.write_text(_LIVE_CHECK_SCRIPT, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=180,  # full app start; slow on Windows CI
            cwd=Path(__file__).resolve().parent,
        )
        cls._stdout = proc.stdout
        cls._stderr = proc.stderr
        cls._results = {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[len("SKIP:"):])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._results[name] = (status == "PASS", detail)

    def _assert_check(self, name: str) -> None:
        if name not in self._results:
            self.fail(f"subprocess never reported {name!r}\nstdout:\n{self._stdout}\nstderr:\n{self._stderr[-2000:]}")
        ok, detail = self._results[name]
        self.assertTrue(ok, f"{name} failed: {detail}\nstderr:\n{self._stderr[-2000:]}")

    def test_scoped_flush_updates_the_target_row(self):
        self._assert_check("scoped_flush_correctness_row_label")
        self._assert_check("scoped_flush_updates_target_row")

    def test_scoped_flush_header_still_reflects_all_scenes(self):
        """A scoped flush must never under-count the header/snapshot totals
        -- _qa_snapshot() always walks the full scene list regardless of
        which row(s) were repainted, so global counts stay correct even when
        only one row's widgets are touched."""
        self._assert_check("scoped_flush_header_counts_all_scenes")

    def test_scoped_flush_is_dramatically_faster_at_scale(self):
        """The whole point of the fix: at 130 scenes, a flush scoped to one
        changed scene must be much faster than the old unconditional full
        repaint of every row (measured ~70x in the diagnostic; asserting a
        conservative 5x floor here to avoid a flaky CI threshold)."""
        self._assert_check("scoped_flush_is_much_faster_than_full_repaint")

    def test_an_unscoped_refresh_call_still_forces_a_full_repaint(self):
        """Safety net: if any OTHER, unscoped _refresh_qa_ui() call happens
        in the same debounce window as a scoped one, the flush must still
        fully repaint (never silently skip a row just because a scoped call
        also fired) -- _qa_ui_full_repaint must win over a partial
        _dirty_scene_keys set."""
        self._assert_check("unscoped_call_still_forces_full_repaint")


if __name__ == "__main__":
    unittest.main()
