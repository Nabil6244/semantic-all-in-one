"""Run starmap-engine (the Node renderer) for one compiled spec, the same way pakMap runs its engine: its own process and
throwaway browser (Playwright from flow-engine, never the Flow engine's port or Chrome profiles), progress as JSON lines,
Stop kills it (registered with the app's process registry under owner "starmap_render")."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

OWNER = "starmap_render"


class StarmapRenderError(RuntimeError):
    pass


class StarmapRenderCancelled(StarmapRenderError):
    pass


@dataclass
class RenderOutcome:
    output: Path
    frames: int
    seconds: float = 0.0
    warnings: list = field(default_factory=list)


def engine_dir() -> Path:
    from map_scene.render import _find

    found = _find("starmap-engine/render.mjs")
    if found is None:
        raise StarmapRenderError("The StarMap renderer (starmap-engine/render.mjs) is missing from this install.")
    return found.parent


def render_spec(spec: dict, output: Path, *, progress: Optional[Callable[[int, int], None]] = None,
                cancel_check: Optional[Callable[[], bool]] = None, log: Callable[[str], None] = print,
                timeout_s: float = 6 * 3600.0) -> RenderOutcome:
    """Render ``spec`` to ``output``. Raises StarmapRenderError (or ...Cancelled) with the engine's own message."""
    from map_scene.render import _browser_channel, _ensure_browser, _ffmpeg, _node

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    engine = engine_dir()
    try:
        from providers.flow.engine_manager import _find_flow_engine_dir

        playwright_dir = str(_find_flow_engine_dir())
    except Exception:
        playwright_dir = None
    try:
        _ensure_browser()
        node, ffmpeg = _node(), _ffmpeg()
    except Exception as exc:
        raise StarmapRenderError(str(exc)) from exc
    tmp_out = output.with_name(f".{output.stem}.rendering{output.suffix}")
    job = dict(spec, ffmpeg=ffmpeg, playwright_dir=playwright_dir, browser_channel=_browser_channel())
    with tempfile.TemporaryDirectory(prefix="starmap_") as tmp:
        spec_path = Path(tmp) / "spec.json"
        spec_path.write_text(json.dumps(job), encoding="utf-8")
        from providers import hidden_subprocess as hs

        proc = hs.popen([node, str(engine / "render.mjs"), str(spec_path), str(tmp_out)], cwd=str(engine), stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        pid = 0
        try:
            from hardware.process_registry import get_registry

            pid = get_registry().register(proc, owner=OWNER, kind="render", command="starmap-engine render")
        except Exception:
            pass
        stderr_lines: list = []
        threading.Thread(target=lambda: stderr_lines.extend(proc.stderr), daemon=True).start()
        done = error = None
        warnings: list = []
        timer = threading.Timer(timeout_s, proc.kill)
        timer.start()
        try:
            for raw in proc.stdout:
                if cancel_check is not None and cancel_check():
                    proc.kill()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        pass
                    for _ in range(6):        # the engine's ffmpeg may still be writing: remove the partial file once they stop
                        tmp_out.unlink(missing_ok=True)
                        time.sleep(0.25)
                    raise StarmapRenderCancelled("StarMap render cancelled.")
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                kind = event.get("event")
                if kind == "progress" and progress is not None:
                    progress(int(event["frame"]), int(event["total"]))
                elif kind == "warning":
                    warnings.append(str(event.get("message")))
                    log(f"[StarMap] {event.get('message')}")
                elif kind == "cache":
                    reused, chunks = int(event.get("reused") or 0), int(event.get("chunks") or 0)
                    if reused:
                        log(f"[StarMap] {reused} of {chunks} parts are unchanged since the last render and are reused; "
                            f"drawing the other {chunks - reused}")
                elif kind == "gpu":
                    log(f"[StarMap] Rendering with {event.get('renderer')} ({event.get('mode')})")
                elif kind == "done":
                    done = event
                elif kind == "error":
                    error = event.get("message")
            proc.wait()
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
            if pid:
                try:
                    from hardware.process_registry import get_registry

                    get_registry().unregister(pid)
                except Exception:
                    pass
    if cancel_check is not None and cancel_check():
        tmp_out.unlink(missing_ok=True)
        raise StarmapRenderCancelled("StarMap render cancelled.")
    if done is None or proc.returncode != 0 or not tmp_out.is_file():
        tmp_out.unlink(missing_ok=True)
        detail = error or "".join(stderr_lines[-20:]).strip() or f"exit code {proc.returncode}"
        raise StarmapRenderError(f"StarMap render failed: {detail}")
    os.replace(tmp_out, output)
    return RenderOutcome(output=output, frames=int(done.get("frames") or 0), seconds=float(done.get("seconds") or 0), warnings=warnings)
