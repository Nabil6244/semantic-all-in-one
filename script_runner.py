"""Run one of the engines' Python tool scripts (for example tools/mix_audio.py).

From source: a child Python, as before. In the installed app there is no Python: sys.executable is the app itself, so a child process
would start the app again. There the script runs inside this process (runpy, as __main__), one at a time, with its own argv,
its folder on sys.path, and its output captured."""
from __future__ import annotations

import io
import os
import runpy
import subprocess
import sys
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Optional, Sequence, Tuple

_LOCK = threading.Lock()


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def run_script(script, args: Sequence = (), *, cwd: Optional[str] = None, timeout: float = 3600.0) -> Tuple[int, str]:
    """Returns (exit code, output). In the installed app the timeout cannot stop the script (it runs in this process)."""
    script = Path(script)
    if not frozen():
        p = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True, cwd=cwd, timeout=timeout)
        return p.returncode, (p.stderr or "") + (p.stdout or "")
    with _LOCK:
        old_argv, old_path, old_cwd = sys.argv[:], sys.path[:], os.getcwd()
        buf = io.StringIO()
        rc = 0
        try:
            sys.argv = [str(script), *map(str, args)]
            sys.path.insert(0, str(script.parent))
            if cwd:
                os.chdir(cwd)
            with redirect_stdout(buf), redirect_stderr(buf):
                runpy.run_path(str(script), run_name="__main__")
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        except BaseException:   # noqa: BLE001 -- reported like a failed child process
            rc = 1
            buf.write(traceback.format_exc())
        finally:
            sys.argv, sys.path[:] = old_argv, old_path
            os.chdir(old_cwd)
        return rc, buf.getvalue()
