"""Run weather-engine (Weather's Node renderer) for one compiled spec, the way pakmap.engine_runner runs pakmap-engine.

make_render(payload) returns a function with the signature pakmap.app_integration.generate_pakmap_video expects for its
`render=` option: it adds the weather layers to the spec Hybrid compiled (alert areas as ordinary `fill` events, everything else
under spec["weather"]) and renders with weather-engine instead of pakmap-engine. Errors and cancels are raised as pakMap's own
exception types, so the generator reports them exactly as it reports a pakMap render's."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

OWNER = "weather_render"


def engine_dir() -> Path:
    from map_scene.render import _find
    from pakmap.engine_runner import PakmapRenderError

    found = _find("weather-engine/render.mjs")
    if found is None:
        raise PakmapRenderError("The Weather renderer (weather-engine/render.mjs) is missing from this install.")
    return found.parent


def with_weather(spec: Dict[str, Any], part: Dict[str, Any], fills: list) -> Dict[str, Any]:
    """The compiled spec plus the weather layers (a new dict; the caller's spec is not changed)."""
    out = dict(spec)
    out["events"] = list(spec.get("events") or []) + list(fills)
    out["weather"] = part
    return out


def make_render(payload, *, timeout_s: float = 4 * 3600.0, look: str = "classic") -> Callable[..., Any]:
    """`payload` is a weather.events.WeatherPayload. `look` "teamplate" restyles the spec for Weather Teamplate (weather.teamplate)."""

    def render(spec: dict, output: Path, *, progress: Optional[Callable[[int, int], None]] = None,
               cancel_check: Optional[Callable[[], bool]] = None, log: Callable[[str], None] = print, imagery: bool = True):
        part = payload.spec_part()
        if look == "teamplate":
            from .teamplate import apply_spec

            spec, part = apply_spec(spec, part)
        return render_spec(with_weather(spec, part, payload.fills), output, progress=progress, cancel_check=cancel_check,
                           log=log, timeout_s=timeout_s, imagery=imagery)

    return render


def render_spec(spec: dict, output: Path, *, progress: Optional[Callable[[int, int], None]] = None,
                cancel_check: Optional[Callable[[], bool]] = None, log: Callable[[str], None] = print,
                timeout_s: float = 4 * 3600.0, imagery: bool = True):
    from map_scene.render import _browser_channel, _ensure_browser, _ffmpeg, _node
    from pakmap.engine_runner import PakmapRenderCancelled, PakmapRenderError, RenderOutcome, cache_dir

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
    # the same tile cache as pakMap (imagery is keyed by provider, and every satellite picture has its own provider id)
    job = dict(spec, output=str(tmp_out), ffmpeg=ffmpeg, cache_dir=str(cache_dir()), playwright_dir=playwright_dir, browser_channel=_browser_channel())
    if not imagery:
        job.update(imagery_enabled=False, flat_only=True)
    side_src = Path(str(tmp_out) + ".weather.json")
    with tempfile.TemporaryDirectory(prefix="weather_") as tmp:
        spec_path = Path(tmp) / "spec.json"
        spec_path.write_text(json.dumps(job), encoding="utf-8")
        from providers import hidden_subprocess as hs

        proc = hs.popen([node, str(engine / "render.mjs"), str(spec_path)], cwd=str(engine), stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        pid = 0
        try:
            from hardware.process_registry import get_registry

            pid = get_registry().register(proc, owner=OWNER, kind="render", command="weather-engine render")
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
                    for _ in range(6):
                        tmp_out.unlink(missing_ok=True)
                        side_src.unlink(missing_ok=True)
                        time.sleep(0.25)
                    raise PakmapRenderCancelled("Weather render cancelled.")
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                kind = event.get("event")
                if kind == "progress" and progress is not None:
                    progress(int(event["frame"]), int(event["total"]))
                elif kind == "warning":
                    warnings.append(str(event.get("message")))
                    log(f"[Weather] {event.get('message')}")
                elif kind == "tiles":
                    log(f"[Weather] Map imagery: {int(event.get('failed') or 0)} tile(s) failed; satellite tiles missing: "
                        f"{int(event.get('satellite_missing') or 0)}.")
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
        raise PakmapRenderCancelled("Weather render cancelled.")
    if done is None or proc.returncode != 0 or not tmp_out.is_file():
        tmp_out.unlink(missing_ok=True)
        detail = error or "".join(stderr_lines[-20:]).strip() or f"exit code {proc.returncode}"
        raise PakmapRenderError(f"Weather render failed: {detail}")
    sidecar = {}
    if side_src.is_file():
        try:
            sidecar = json.loads(side_src.read_text(encoding="utf-8"))
        except ValueError:
            sidecar = {}
        side_src.unlink(missing_ok=True)
    os.replace(tmp_out, output)
    return RenderOutcome(output=output, frames=int(done.get("frames") or 0), sidecar=sidecar, warnings=warnings)
