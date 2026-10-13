"""weather-engine's upstream-drift check, and the Python names Weather imports from shared code (UPSTREAM.json python_uses).

Content drift is REPORTED (printed), never a failure; a name Weather imports that no longer exists IS a failure, because Weather
would break. Nothing here changes a file."""

import importlib
import inspect
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RECORD = json.loads((ROOT / "weather-engine" / "UPSTREAM.json").read_text(encoding="utf-8"))


class Upstream(unittest.TestCase):
    def test_the_js_check_runs_reports_drift_and_finds_no_missing_export(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not available")
        r = subprocess.run([node, str(ROOT / "weather-engine" / "tools" / "check_upstream.mjs"), "--json"], capture_output=True, text=True, timeout=120)
        self.assertIn(r.returncode, (0, 2), r.stderr)
        rep = json.loads(r.stdout)
        if rep["drift"]:
            print(f"\n[weather upstream drift, reported only] copied: {rep['copied_changed']} lib: {rep['lib_changed']} "
                  f"added: {rep['lib_added']} removed: {rep['lib_removed']}")
        self.assertEqual(rep["missing_exports"], [], "names weather-engine imports from pakmap-engine are gone")
        self.assertEqual(r.returncode, 0)

    def test_every_python_name_weather_imports_still_exists(self):
        missing = []
        for module, names in RECORD["python_uses"].items():
            try:
                mod = importlib.import_module(module)
            except Exception as exc:  # the module itself is gone or broken
                missing.append(f"{module} ({exc})")
                continue
            for name in names:
                if name.endswith("(render=)"):
                    fn = getattr(mod, name.split("(")[0], None)
                    if fn is None or "render" not in inspect.signature(fn).parameters:
                        missing.append(f"{module}.{name}")
                    continue
                head, _, attr = name.partition(".")
                obj = getattr(mod, head, None)
                if obj is None:
                    missing.append(f"{module}.{name}")
                elif attr == "_spans" or attr == "words":     # instance attributes of pakmap.anchor.Transcript
                    if not hasattr(obj([("a", 0.0, 0.1)]), attr):
                        missing.append(f"{module}.{name}")
                elif attr and not hasattr(obj, attr):
                    missing.append(f"{module}.{name}")
        self.assertEqual(missing, [])

    def test_hybrid_passes_extra_options_through_to_the_pakmap_generator(self):
        # Weather's renderer reaches pakMap's generator through generate_hybrid_video(**kw): that pass-through must stay
        from hybrid.generate import generate_hybrid_video

        kinds = [p.kind for p in inspect.signature(generate_hybrid_video).parameters.values()]
        self.assertIn(inspect.Parameter.VAR_KEYWORD, kinds)


if __name__ == "__main__":
    unittest.main()
