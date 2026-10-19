"""No new wait without a time limit (the stuck-on-Windows freezes, 2026-10-19).

Counts, per source file, the calls that can wait forever: an outside program run with no timeout=, a web request with no timeout=,
.communicate() / .wait() / .result() / .join() with nothing to stop them. The counts may only go down. A file whose count goes up
fails here, on every OS in CI: give the new call a timeout= (and a fallback) instead of raising the baseline.

After lowering a count on purpose: python test_unbounded_waits.py --refresh"""

import ast
import json
import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASELINE = ROOT / "test_fixtures" / "unbounded_waits_baseline.json"
SKIP_DIRS = {".worktrees", ".git", "build", "dist", "out", "node_modules", "__pycache__", "test_fixtures", ".venv", "venv"}
RUNNERS = {"subprocess", "hidden_subprocess", "_hidden_subprocess", "sp"}
RUN_CALLS = {"run", "call", "check_call", "check_output"}
WEB = {"requests", "httpx"}
WEB_CALLS = {"get", "post", "put", "head", "delete", "patch", "request"}
WAITS = {"communicate", "wait", "result", "join"}


def _sources():
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        dirs = rel.parts[:-1]
        if (SKIP_DIRS & set(dirs) or any(d.startswith(".") or d.startswith("venv") or d == "site-packages" for d in dirs)
                or rel.name.startswith("test_") or rel.parts[0] == "scripts"):
            continue
        yield rel


def _unbounded(call: ast.Call) -> bool:
    f = call.func
    if not isinstance(f, ast.Attribute):
        return False
    kws = {k.arg for k in call.keywords}
    if "timeout" in kws or None in kws:          # timeout=…, or **kwargs that may carry one
        return False
    owner = f.value.id if isinstance(f.value, ast.Name) else None
    if owner in RUNNERS and f.attr in RUN_CALLS:
        return True
    if owner in WEB and f.attr in WEB_CALLS:
        return True
    if f.attr in WAITS and not call.args and owner not in {"os", "str", "path"}:
        return not (f.attr == "join" and isinstance(f.value, ast.Constant))
    return False


def count(rel: Path) -> int:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return 0
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call) and _unbounded(n))


def counts() -> dict:
    return {str(rel).replace("\\", "/"): c for rel in _sources() if (c := count(rel))}


class NoNewUnboundedWaits(unittest.TestCase):
    def test_no_file_waits_without_a_limit_more_than_before(self):
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        grew = {f: (base.get(f, 0), c) for f, c in counts().items() if c > base.get(f, 0)}
        self.assertEqual(grew, {}, "new call(s) that can wait forever — add timeout= and a fallback. file: (allowed, found) "
                                   + json.dumps(grew))

    def test_the_counter_finds_what_it_should(self):
        src = ("import subprocess, requests\n"
               "subprocess.run(['ffmpeg'])\nsubprocess.run(['ffmpeg'], timeout=60)\nrequests.get(u)\nrequests.get(u, timeout=20)\n"
               "p.communicate()\np.communicate(timeout=5)\nf.result()\nf.result(30)\nt.join()\n','.join(x)\nhidden_subprocess.run(c, **kw)\n")
        found = sum(1 for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call) and _unbounded(n))
        self.assertEqual(found, 5)


if __name__ == "__main__":
    if "--refresh" in sys.argv:
        BASELINE.write_text(json.dumps(counts(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {BASELINE} ({sum(counts().values())} calls)")
    else:
        unittest.main()
