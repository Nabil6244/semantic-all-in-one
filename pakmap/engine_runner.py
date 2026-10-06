"""Run pakmap-engine (the Node renderer) for one compiled spec.

Mirrors map_scene.render: its own process and throwaway browser, never the Flow engine's port or
Chrome profiles. Progress arrives as JSON lines; Stop kills the process (it is also registered with
the app's process registry under owner "pakmap_render" so the shared cleanup can find it)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


class PakmapRenderError(RuntimeError):
    pass


class PakmapRenderCancelled(PakmapRenderError):
    pass


OWNER = "pakmap_render"


@dataclass
class RenderOutcome:
    output: Path
    frames: int
    sidecar: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def engine_dir() -> Path:
    from map_scene.render import _find

    found = _find("pakmap-engine/render.mjs")
    if found is None:
        raise PakmapRenderError("The pakMap renderer (pakmap-engine/render.mjs) is missing from this install.")
    return found.parent


def cache_dir() -> Path:
    """Per-user cache for the NASA imagery tiles (downloaded on first use, reused afterwards)."""
    override = os.environ.get("VIDEOGEN_PAKMAP_CACHE")
    if override:
        base = Path(override)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / "SemanticYTStudio" / "pakmap"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "SemanticYTStudio" / "Cache" / "pakmap"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "semantic-yt-studio" / "pakmap"
    base.mkdir(parents=True, exist_ok=True)
    return base


def render_spec(spec: dict, output: Path, *, progress: Optional[Callable[[int, int], None]] = None,
                cancel_check: Optional[Callable[[], bool]] = None, log: Callable[[str], None] = print,
                timeout_s: float = 4 * 3600.0, imagery: bool = True) -> RenderOutcome:
    """Render ``spec`` to ``output``. Raises PakmapRenderError (or ...Cancelled) with the engine's own message."""
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
        raise PakmapRenderError(str(exc)) from exc
    tmp_out = output.with_name(f".{output.stem}.rendering{output.suffix}")
    job = dict(spec, output=str(tmp_out), ffmpeg=ffmpeg, cache_dir=str(cache_dir()), playwright_dir=playwright_dir,
               browser_channel=_browser_channel())
    if not imagery:
        job.update(imagery_enabled=False, flat_only=True)
    with tempfile.TemporaryDirectory(prefix="pakmap_") as tmp:
        spec_path = Path(tmp) / "spec.json"
        spec_path.write_text(json.dumps(job), encoding="utf-8")
        from providers import hidden_subprocess as hs

        proc = hs.popen([node, str(engine / "render.mjs"), str(spec_path)], cwd=str(engine), stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        pid = 0
        try:
            from hardware.process_registry import get_registry

            pid = get_registry().register(proc, owner=OWNER, kind="render", command="pakmap-engine render")
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
                    # The engine (and the ffmpeg it started) may already be writing the file: remove it, and again once they have stopped.
                    for _ in range(6):
                        tmp_out.unlink(missing_ok=True)
                        Path(str(tmp_out) + ".pakmap.json").unlink(missing_ok=True)
                        time.sleep(0.25)
                    tmp_out.unlink(missing_ok=True)
                    raise PakmapRenderCancelled("pakMap render cancelled.")
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                kind = event.get("event")
                if kind == "progress" and progress is not None:
                    progress(int(event["frame"]), int(event["total"]))
                elif kind == "warning":
                    warnings.append(str(event.get("message")))
                    log(f"[pakMap] {event.get('message')}")
                elif kind == "tiles":   # map imagery health, every render: failed downloads and what stood in for them
                    log(f"[pakMap] Map imagery: {int(event.get('failed') or 0)} map tile(s) failed to download; "
                        f"{int(event.get('drawn_from_coarser_zoom') or 0)} drawn from a coarser zoom, "
                        f"{int(event.get('drawn_from_coarser_layer') or 0)} from a coarser imagery layer "
                        f"({int(event.get('download_failures') or 0)} failed download(s) and "
                        f"{int(event.get('invalid') or 0)} unreadable or blank tile(s) in all).")
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
        raise PakmapRenderCancelled("pakMap render cancelled.")
    if done is None or proc.returncode != 0 or not tmp_out.is_file():
        tmp_out.unlink(missing_ok=True)
        detail = error or "".join(stderr_lines[-20:]).strip() or f"exit code {proc.returncode}"
        raise PakmapRenderError(f"pakMap render failed: {detail}")
    side_src = Path(str(tmp_out) + ".pakmap.json")
    sidecar = {}
    if side_src.is_file():
        try:
            sidecar = json.loads(side_src.read_text(encoding="utf-8"))
        except ValueError:
            sidecar = {}
        side_src.unlink(missing_ok=True)
    os.replace(tmp_out, output)
    return RenderOutcome(output=output, frames=int(done.get("frames") or 0), sidecar=sidecar, warnings=warnings)
