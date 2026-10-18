"""Run whatif-engine (the Node renderer) for one spec: its own process and throwaway browser (Playwright from flow-engine, never
the Flow engine's port or Chrome profiles), progress as JSON lines, Stop kills it (owner "whatif_render")."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from starmap.engine_runner import RenderOutcome

OWNER = "whatif_render"


class WhatifRenderError(RuntimeError):
    pass


class WhatifRenderCancelled(WhatifRenderError):
    pass


def engine_dir() -> Path:
    from map_scene.render import _find

    found = _find("whatif-engine/render.mjs")
    if found is None:
        raise WhatifRenderError("The What If renderer (whatif-engine/render.mjs) is missing from this install.")
    return found.parent


def render_spec(spec: dict, output: Path, *, progress: Optional[Callable[[int, int], None]] = None,
                cancel_check: Optional[Callable[[], bool]] = None, log: Callable[[str], None] = print,
                timeout_s: float = 6 * 3600.0, software_gl: bool = False, parts: Optional[int] = None) -> RenderOutcome:
    """software_gl: draw 3D on the CPU (SwiftShader) -- the second attempt after a GPU / driver failure.
    parts: how many pieces of the video are drawn at the same time (None: as many as the machine holds, see render_parts()).
    A part that fails falls back to one ordinary render of the whole video, so a parallel render is never worse than before."""
    n = render_parts(spec) if parts is None else max(1, int(parts))
    ranges = part_ranges(spec, n) if n > 1 else []
    if len(ranges) > 1:
        try:
            return _render_parallel(spec, Path(output), ranges, progress=progress, cancel_check=cancel_check, log=log,
                                    timeout_s=timeout_s, software_gl=software_gl)
        except WhatifRenderCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 -- the single render below is the safe way
            log(f"[What If] the parallel render did not finish ({str(exc)[:200]}); drawing it in one piece instead")
    return _render_once(spec, output, progress=progress, cancel_check=cancel_check, log=log, timeout_s=timeout_s, software_gl=software_gl)


MIN_PART_FRAMES = 900          # 30 s at 30 fps: shorter parts spend more time starting a browser than drawing


def render_parts(spec: dict) -> int:
    """Parts drawn at once: WHATIF_RENDER_PARTS when set, else by memory (a part is a browser page, its GPU process and an encoder,
    about 3 GB at 1080p; 6 GB left for the app and the system) and performance cores, at most 4."""
    env = os.environ.get("WHATIF_RENDER_PARTS", "").strip()
    if env.isdigit():
        return max(1, int(env))
    try:
        from hardware.governor import _ram_bytes

        mem_gb = _ram_bytes()[0] / 2 ** 30 or 8.0
    except Exception:
        mem_gb = 8.0
    cores = os.cpu_count() or 2
    try:
        import subprocess as sp

        cores = int(sp.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"], capture_output=True, text=True, timeout=5).stdout.strip() or cores)
    except Exception:
        pass
    scale = (int(spec.get("width", 1920)) * int(spec.get("height", 1080))) / (1920 * 1080)
    return max(1, min(4, cores, int((mem_gb - 6) // (3 * max(1.0, scale)))))


def part_ranges(spec: dict, n: int) -> list:
    """[from, to) frame ranges for n parts, each cut where a shot starts (a join always falls on a cut, never inside a shot)."""
    fps = int(spec.get("fps", 30))
    total = int(round(float(spec["duration"]) * fps))
    if n <= 1 or total < 2 * MIN_PART_FRAMES:
        return [[0, total]]
    n = min(n, total // MIN_PART_FRAMES)
    cuts = sorted({int(round(float(s["start"]) * fps)) for s in spec.get("shots", []) if 0 < float(s.get("start", 0)) * fps < total})
    edges = [0]
    for k in range(1, n):
        want = total * k / n
        best = min((c for c in cuts if c - edges[-1] >= MIN_PART_FRAMES and total - c >= MIN_PART_FRAMES), key=lambda c: abs(c - want), default=None)
        if best is not None and best > edges[-1]:
            edges.append(best)
    edges.append(total)
    return [[a, b] for a, b in zip(edges, edges[1:])]


def _render_parallel(spec: dict, output: Path, ranges: list, *, progress, cancel_check, log, timeout_s: float, software_gl: bool) -> RenderOutcome:
    """Draw each range in its own renderer at the same time, with exactly the same encoder settings, then join the parts without
    re-encoding (ffmpeg concat, stream copy): the joined file is the parts' frames, as drawn."""
    from map_scene.render import _ffmpeg

    total = sum(b - a for a, b in ranges)
    done = [0] * len(ranges)
    lock = threading.Lock()
    stop = threading.Event()
    log(f"[What If] drawing the video in {len(ranges)} parts at the same time (cut at shot changes: "
        + ", ".join(f"{a / int(spec.get('fps', 30)):.0f}s" for a, _b in ranges[1:]) + ")")

    def part_progress(k):
        def cb(frame, _n):
            with lock:
                done[k] = frame
                if progress is not None:
                    progress(sum(done), total)
        return cb

    said_gpu = threading.Event()

    def part_log(msg):
        if msg.startswith("[What If] Rendering ("):      # every part says it: once is enough
            if said_gpu.is_set():
                return
            said_gpu.set()
        log(msg)

    stopped = lambda: stop.is_set() or bool(cancel_check is not None and cancel_check())  # noqa: E731
    work = Path(tempfile.mkdtemp(prefix=".whatif_parts_", dir=str(output.parent)))
    results: list = [None] * len(ranges)
    errors: list = []

    def run(k, rng):
        try:
            results[k] = _render_once(dict(spec, frame_range=rng), work / f"part{k:02d}.mp4", progress=part_progress(k), cancel_check=stopped,
                                      log=part_log, timeout_s=timeout_s, software_gl=software_gl)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
            stop.set()                                   # one part failed: the others stop, the caller draws it in one piece

    try:
        threads = [threading.Thread(target=run, args=(k, r), daemon=True) for k, r in enumerate(ranges)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if cancel_check is not None and cancel_check():
            raise WhatifRenderCancelled("What If render cancelled.")
        if errors:
            raise errors[0]
        lst = work / "parts.txt"
        lst.write_text("".join(f"file '{r.output.name}'\n" for r in results), encoding="utf-8")
        tmp_out = output.with_name(f".{output.stem}.joining{output.suffix}")
        r = subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                            "-movflags", "+faststart", str(tmp_out)], capture_output=True, text=True, cwd=str(work), timeout=3600)
        if r.returncode != 0 or not tmp_out.is_file():
            tmp_out.unlink(missing_ok=True)
            raise WhatifRenderError(f"joining the parts failed: {(r.stderr or '').strip()[-300:]}")
        got = _frame_count(tmp_out)
        if got is not None and got != total:
            tmp_out.unlink(missing_ok=True)
            raise WhatifRenderError(f"the joined parts have {got} frames, not {total}")
        os.replace(tmp_out, output)
        warnings = [w for res in results for w in (res.warnings or [])]
        return RenderOutcome(output=output, frames=total, seconds=max(res.seconds for res in results), warnings=warnings)
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)


def _frame_count(video: Path) -> Optional[int]:
    from map_scene.render import _ffmpeg

    probe = Path(_ffmpeg()).with_name("ffprobe")
    try:
        r = subprocess.run([str(probe) if probe.is_file() else "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                            "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(video)], capture_output=True, text=True, timeout=600)
        return int(r.stdout.strip().strip(","))
    except Exception:
        return None


def _render_once(spec: dict, output: Path, *, progress: Optional[Callable[[int, int], None]] = None,
                 cancel_check: Optional[Callable[[], bool]] = None, log: Callable[[str], None] = print,
                 timeout_s: float = 6 * 3600.0, software_gl: bool = False) -> RenderOutcome:
    """One renderer for the spec (or its frame_range)."""
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
        raise WhatifRenderError(str(exc)) from exc
    tmp_out = output.with_name(f".{output.stem}.rendering{output.suffix}")
    job = dict(spec, ffmpeg=ffmpeg, playwright_dir=playwright_dir, browser_channel=_browser_channel())
    with tempfile.TemporaryDirectory(prefix="whatif_") as tmp:
        spec_path = Path(tmp) / "spec.json"
        spec_path.write_text(json.dumps(job), encoding="utf-8")
        from providers import hidden_subprocess as hs

        env = dict(os.environ, WHATIF_GL="software") if software_gl else None
        proc = hs.popen([node, str(engine / "render.mjs"), str(spec_path), str(tmp_out)], cwd=str(engine), stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
        pid = 0
        try:
            from hardware.process_registry import get_registry

            pid = get_registry().register(proc, owner=OWNER, kind="render", command="whatif-engine render")
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
                        time.sleep(0.25)
                    raise WhatifRenderCancelled("What If render cancelled.")
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                kind = event.get("event")
                if kind == "progress" and progress is not None:
                    progress(int(event["frame"]), int(event["total"]))
                elif kind == "warning":
                    warnings.append(str(event.get("message")))
                    log(f"[What If] {event.get('message')}")
                elif kind == "gpu":
                    log(f"[What If] Rendering ({event.get('mode')})")
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
        raise WhatifRenderCancelled("What If render cancelled.")
    if done is None or proc.returncode != 0 or not tmp_out.is_file():
        tmp_out.unlink(missing_ok=True)
        raise WhatifRenderError(f"What If render failed: {error or ''.join(stderr_lines[-20:]).strip() or f'exit code {proc.returncode}'}")
    os.replace(tmp_out, output)
    return RenderOutcome(output=output, frames=int(done.get("frames") or 0), seconds=float(done.get("seconds") or 0), warnings=warnings)
