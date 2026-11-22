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


RUN_FLAG = "--run-script"


def command(script, args: Sequence = ()) -> list:
    """The command line that runs a tool script in its own process: a child Python from source; in the installed app
    the app itself with --run-script (dispatch() below runs it before any window opens). For work that must run
    several processes at once (the 2D cartoon renderer draws pieces of a video side by side)."""
    if frozen():
        return [sys.executable, RUN_FLAG, str(script), *map(str, args)]
    return [sys.executable, str(script), *map(str, args)]


def dispatch(argv=None) -> bool:
    """Called first thing by the app's entry: `<app> --run-script <file.py> args...` runs that script as __main__ in this
    process and exits, without opening the app's window. Returns False when this is a normal start."""
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 3 or argv[1] != RUN_FLAG:
        return False
    script = Path(argv[2])
    for name, fd in (("stdout", 1), ("stderr", 2)):   # a windowed app (no console) may start without them: use the
        if getattr(sys, name) is None:                 # pipe the parent handed over, else nowhere
            try:
                setattr(sys, name, io.TextIOWrapper(io.FileIO(fd, "w", closefd=False), line_buffering=True))
            except Exception:   # noqa: BLE001
                setattr(sys, name, open(os.devnull, "w"))
    sys.argv = [str(script), *argv[3:]]
    sys.path.insert(0, str(script.parent))
    code = 0
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    sys.stdout.flush()
    raise SystemExit(code)
