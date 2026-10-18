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
                timeout_s: float = 4 * 3600.0, imagery: bool = True, parts: Optional[int] = None) -> RenderOutcome:
    """Render ``spec`` to ``output``. Raises PakmapRenderError (or ...Cancelled) with the engine's own message.

    A video longer than a minute is drawn in pieces (pakmap-engine/lib/segments.mjs cuts only where the pieces join into exactly the
    frames one render makes): ``parts`` renderers draw them at the same time, and a piece whose inputs are unchanged since the last
    render into this folder is reused. If anything about that fails, the video is drawn in one piece as before."""
    output = Path(output).resolve()   # the engine runs in its own folder
    output.parent.mkdir(parents=True, exist_ok=True)
    base = _base_job(spec, imagery)
    if os.environ.get("PAKMAP_SEGMENTS", "").strip() != "0" and spec.get("segments_enabled") is not False:
        try:
            return _render_in_segments(base, output, progress=progress, cancel_check=cancel_check, log=log, timeout_s=timeout_s,
                                       parts=render_parts(spec) if parts is None else max(1, int(parts)))
        except _OnePiece:
            pass
        except PakmapRenderCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 -- the single render below is the safe way
            if cancel_check is not None and cancel_check():
                raise PakmapRenderCancelled("pakMap render cancelled.") from exc
            log(f"[pakMap] drawing the map in pieces did not finish ({str(exc)[:300]}); drawing it in one piece instead")
            import shutil

            shutil.rmtree(output.parent / SEGMENT_DIR, ignore_errors=True)   # nothing doubtful is offered for reuse next time
    return _render_once(base, output, progress=progress, cancel_check=cancel_check, log=log, timeout_s=timeout_s)


class _OnePiece(Exception):
    """The video is short (or the plan could not be read): draw it in one piece."""


def render_parts(spec: dict) -> int:
    """Renderers drawing at the same time: PAKMAP_RENDER_PARTS when set, else by performance cores and memory (a renderer is a
    browser, its GPU process and an encoder, about 3 GB at 1080p; 6 GB left for the app). On a 4-core M2, 2 renderers measured
    1.7x and 4 were slower than 2 (the CPU was full), so it is at most 2 there."""
    env = os.environ.get("PAKMAP_RENDER_PARTS", "").strip()
    if env.isdigit():
        return max(1, int(env))
    try:
        from hardware.governor import _ram_bytes

        mem_gb = _ram_bytes()[0] / 2 ** 30 or 8.0
    except Exception:
        mem_gb = 8.0
    cores = os.cpu_count() or 2
    if sys.platform == "darwin":
        try:
            cores = int(subprocess.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"], capture_output=True, text=True, timeout=5).stdout.strip() or cores)
        except Exception:
            pass
    by_cores = 2 if cores <= 5 else 3 if cores <= 9 else 4
    scale = (int(spec.get("width", 1920)) * int(spec.get("height", 1080)) * float(spec.get("pixel_scale") or 1) ** 2) / (1920 * 1080)
    return max(1, min(by_cores, int((mem_gb - 6) // (3 * max(1.0, scale)))))


def _base_job(spec: dict, imagery: bool) -> dict:
    from map_scene.render import _browser_channel, _ensure_browser, _ffmpeg, _node

    engine_dir()
    try:
        from providers.flow.engine_manager import _find_flow_engine_dir

        playwright_dir = str(_find_flow_engine_dir())
    except Exception:
        playwright_dir = None
    try:
        _ensure_browser()
        _node()
        ffmpeg = _ffmpeg()
    except Exception as exc:
        raise PakmapRenderError(str(exc)) from exc
    job = dict(spec, ffmpeg=ffmpeg, cache_dir=str(cache_dir()), playwright_dir=playwright_dir, browser_channel=_browser_channel())
    if not imagery:
        job.update(imagery_enabled=False, flat_only=True)
    return job


def _run_engine(job: dict, *, on_event: Callable[[dict], None], cancel_check: Optional[Callable[[], bool]], timeout_s: float,
                on_cancel: Callable[[], None] = lambda: None) -> tuple:
    """Run render.mjs for ``job``; every JSON line goes to on_event. Returns (done event or None, error message, exit code, stderr tail)."""
    from map_scene.render import _node

    engine = engine_dir()
    with tempfile.TemporaryDirectory(prefix="pakmap_") as tmp:
        spec_path = Path(tmp) / "spec.json"
        spec_path.write_text(json.dumps(job), encoding="utf-8")
        from providers import hidden_subprocess as hs

        proc = hs.popen([_node(), str(engine / "render.mjs"), str(spec_path)], cwd=str(engine), stdout=subprocess.PIPE,
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
                    # The engine (and the ffmpeg it started) may already be writing its files: remove them, and again once they have stopped.
                    for _ in range(6):
                        on_cancel()
                        time.sleep(0.25)
                    on_cancel()
                    raise PakmapRenderCancelled("pakMap render cancelled.")
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                kind = event.get("event")
                if kind == "done":
                    done = event
                elif kind == "error":
                    error = event.get("message")
                else:
                    on_event(event)
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
    return done, error, proc.returncode, "".join(stderr_lines[-20:]).strip()


def _log_tiles(log: Callable[[str], None], event: dict) -> None:
    """Map imagery health, every render: failed downloads and what stood in for them."""
    log(f"[pakMap] Map imagery: {int(event.get('failed') or 0)} map tile(s) failed to download; "
        f"{int(event.get('drawn_from_coarser_zoom') or 0)} drawn from a coarser zoom, "
        f"{int(event.get('drawn_from_coarser_layer') or 0)} from a coarser imagery layer "
        f"({int(event.get('download_failures') or 0)} failed download(s) and "
        f"{int(event.get('invalid') or 0)} unreadable or blank tile(s) in all).")


def _render_once(job: dict, output: Path, *, progress, cancel_check, log, timeout_s: float) -> RenderOutcome:
    """The whole video in one renderer."""
    tmp_out = output.with_name(f".{output.stem}.rendering{output.suffix}")
    warnings: list = []

    def on_event(event: dict) -> None:
        kind = event.get("event")
        if kind == "progress" and progress is not None:
            progress(int(event["frame"]), int(event["total"]))
        elif kind == "warning":
            warnings.append(str(event.get("message")))
            log(f"[pakMap] {event.get('message')}")
        elif kind == "tiles":
            _log_tiles(log, event)

    def drop() -> None:
        tmp_out.unlink(missing_ok=True)
        Path(str(tmp_out) + ".pakmap.json").unlink(missing_ok=True)

    done, error, code, stderr = _run_engine(dict(job, output=str(tmp_out)), on_event=on_event, cancel_check=cancel_check,
                                            timeout_s=timeout_s, on_cancel=drop)
    if cancel_check is not None and cancel_check():
        drop()
        raise PakmapRenderCancelled("pakMap render cancelled.")
    if done is None or code != 0 or not tmp_out.is_file():
        drop()
        raise PakmapRenderError(f"pakMap render failed: {error or stderr or f'exit code {code}'}")
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


SEGMENT_DIR = ".pakmap_segments"   # next to the render's output: the pieces of the last render, reused while their inputs are unchanged


def _segment_file(store: Path, key: str) -> Path:
    return store / f"{key}.mp4"


def _reusable(store: Path, seg: dict) -> bool:
    """A piece from an earlier render is reused only with its record (written once it was complete) and the right length."""
    f, meta = _segment_file(store, seg["key"]), store / f"{seg['key']}.json"
    if not (f.is_file() and meta.is_file() and f.stat().st_size > 0):
        return False
    try:
        m = json.loads(meta.read_text(encoding="utf-8"))
    except ValueError:
        return False
    return int(m.get("frames") or -1) == seg["to"] - seg["from"]


def _groups(todo: list, n: int) -> list:
    """The pieces to draw shared out between n renderers in order (neighbouring pieces stay together: the map is already
    loaded where the next one starts), by their estimated cost."""
    n = max(1, min(n, len(todo)))
    total = sum(max(1, s["cost"]) for s in todo)
    groups, cur, acc = [], [], 0.0
    for s in todo:
        c = max(1, s["cost"])
        target = total * (len(groups) + 1) / n
        # close the group before this piece when that lands nearer the even share than taking it does
        if cur and len(groups) < n - 1 and acc + c > target and target - acc < acc + c - target:
            groups.append(cur)
            cur = []
        cur.append(s)
        acc += c
        if len(groups) < n - 1 and acc >= total * (len(groups) + 1) / n:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def _render_in_segments(job: dict, output: Path, *, progress, cancel_check, log, timeout_s: float, parts: int) -> RenderOutcome:
    from map_scene.render import _ffmpeg

    # ---- 1. the pieces and their reuse keys (no browser: a second or two) ----
    planned: dict = {}
    plan_warnings: list = []

    def on_plan(event: dict) -> None:
        if event.get("event") == "segments":
            planned.update(event)
        elif event.get("event") == "warning":
            plan_warnings.append(str(event.get("message")))

    done, error, code, _stderr = _run_engine(dict(job, plan_only=True, output=str(output)), on_event=on_plan, cancel_check=cancel_check, timeout_s=600)
    segs = planned.get("segments") or []
    if code != 0 or not segs or len(segs) < 2:
        raise _OnePiece(error or "one piece")   # a short video, or a spec the single render reports properly
    for w in plan_warnings:
        log(f"[pakMap] {w}")
    total = segs[-1]["to"]
    store = output.parent / SEGMENT_DIR
    store.mkdir(parents=True, exist_ok=True)
    reused = [s for s in segs if _reusable(store, s)]
    todo = [s for s in segs if not _reusable(store, s)]
    groups = _groups(todo, parts) if todo else []
    said = f"[pakMap] drawing the map in {len(segs)} pieces"
    if reused:
        said += f"; {len(reused)} unchanged since the last render are reused ({sum(s['to'] - s['from'] for s in reused) / job['fps']:.0f}s)"
    if groups:
        said += f"; {len(todo)} drawn by {len(groups)} renderer(s) at the same time"
    log(said)

    # ---- 2. draw the pieces that changed, `parts` renderers at once ----
    base_done = sum(s["to"] - s["from"] for s in reused)
    counts = [0] * len(groups)
    lock = threading.Lock()
    stop = threading.Event()
    errors: list = []
    warnings: list = []
    seen_warnings: set = set()
    tiles: dict = {}
    clips = {s["key"]: 0 for s in segs}
    for s in reused:
        try:
            clips[s["key"]] = int(json.loads((store / f"{s['key']}.json").read_text(encoding="utf-8")).get("frames_from_clips") or 0)
        except Exception:
            pass
    paths = {s["key"]: _segment_file(store, s["key"]) for s in reused}
    work = Path(tempfile.mkdtemp(prefix=".pakmap_parts_", dir=str(output.parent)))
    if progress is not None and base_done:
        progress(base_done, total)
    stopped = lambda: stop.is_set() or bool(cancel_check is not None and cancel_check())  # noqa: E731

    def run(k: int, group: list) -> None:
        by_out = {}
        for s in group:
            by_out[str(store / f".{s['key']}.partial.mp4")] = s

        def on_event(event: dict) -> None:
            kind = event.get("event")
            if kind == "progress":
                with lock:
                    counts[k] = int(event["frame"])
                    if progress is not None:
                        progress(base_done + sum(counts), total)
            elif kind == "warning":
                msg = str(event.get("message"))
                with lock:
                    if msg not in seen_warnings and msg not in plan_warnings:
                        seen_warnings.add(msg)
                        warnings.append(msg)
                        log(f"[pakMap] {msg}")
            elif kind == "tiles":
                with lock:
                    for key, v in event.items():
                        if key != "event":
                            tiles[key] = tiles.get(key, 0) + int(v or 0)
            elif kind == "segment":
                s = by_out.get(str(event.get("output")))
                if s is None:
                    return
                part = Path(event["output"])
                with lock:
                    clips[s["key"]] = int(event.get("frames_from_clips") or 0)
                if int(event.get("tiles_failed") or 0) == 0:   # drawn with all of its own imagery: kept for the next render
                    final = _segment_file(store, s["key"])
                    os.replace(part, final)
                    (store / f"{s['key']}.json").write_text(json.dumps({"frames": s["to"] - s["from"], "from": s["from"], "to": s["to"],
                                                                         "frames_from_clips": clips[s["key"]]}), encoding="utf-8")
                else:   # stand-in imagery somewhere in it: used this time, drawn again next time
                    final = work / f"{s['key']}.mp4"
                    os.replace(part, final)
                with lock:
                    paths[s["key"]] = final

        def drop() -> None:
            for p in by_out:
                Path(p).unlink(missing_ok=True)

        try:
            wjob = dict(job, output=str(work / f"renderer{k}.mp4"),
                        segments=[{"from": s["from"], "to": s["to"], "output": out} for out, s in by_out.items()])
            done, error, code, stderr = _run_engine(wjob, on_event=on_event, cancel_check=stopped, timeout_s=timeout_s, on_cancel=drop)
            if done is None or code != 0:
                drop()
                raise PakmapRenderError(f"pakMap render failed: {error or stderr or f'exit code {code}'}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
            stop.set()                                   # one renderer failed: the others stop

    try:
        threads = [threading.Thread(target=run, args=(k, g), daemon=True) for k, g in enumerate(groups)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if cancel_check is not None and cancel_check():
            raise PakmapRenderCancelled("pakMap render cancelled.")
        if errors:
            first = next((e for e in errors if not isinstance(e, PakmapRenderCancelled)), errors[0])
            raise first if not isinstance(first, PakmapRenderCancelled) else PakmapRenderError("a renderer stopped")
        missing = [s for s in segs if s["key"] not in paths or not Path(paths[s["key"]]).is_file()]
        if missing:
            raise PakmapRenderError(f"{len(missing)} piece(s) were not drawn")

        # ---- 3. join the pieces without re-encoding: the joined file is the pieces' frames, as drawn ----
        lst = work / "pieces.txt"
        lst.write_text("".join(f"file '{Path(paths[s['key']]).resolve().as_posix()}'\n" for s in segs), encoding="utf-8")
        tmp_out = output.with_name(f".{output.stem}.joining{output.suffix}")
        r = subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                            "-metadata", "comment=semantic-yt-studio:pakmap-scene", "-movflags", "+faststart", str(tmp_out)],
                           capture_output=True, text=True, timeout=3600)
        if r.returncode != 0 or not tmp_out.is_file():
            tmp_out.unlink(missing_ok=True)
            raise PakmapRenderError(f"joining the pieces failed: {(r.stderr or '').strip()[-300:]}")
        got = _frame_count(tmp_out)
        if got is not None and got != total:
            tmp_out.unlink(missing_ok=True)
            raise PakmapRenderError(f"the joined pieces have {got} frames, not {total}")
        os.replace(tmp_out, output)
        if tiles:
            _log_tiles(log, tiles)
        # only this render's pieces are kept: the folder never grows past one video's worth
        keep = {s["key"] for s in segs}
        for f in store.iterdir():
            if f.name.split(".")[0] not in keep or f.name.startswith("."):
                f.unlink(missing_ok=True)
        sidecar = dict(planned.get("sidecar") or {}, frames=total, frames_from_clips=sum(clips.values()),
                       tiles=tiles or {"failed": 0, "drawn_from_coarser_zoom": 0, "drawn_from_coarser_layer": 0, "invalid": 0, "download_failures": 0},
                       pieces={"total": len(segs), "reused": len(reused), "renderers": len(groups)})
        return RenderOutcome(output=output, frames=total, sidecar=sidecar, warnings=plan_warnings + warnings)
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)
        for f in store.glob(".*.partial.mp4"):
            f.unlink(missing_ok=True)


def _frame_count(video: Path) -> Optional[int]:
    from map_scene.render import _ffmpeg

    probe = Path(_ffmpeg()).with_name("ffprobe")
    try:
        r = subprocess.run([str(probe) if probe.is_file() else "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                            "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(video)], capture_output=True, text=True, timeout=600)
        return int(r.stdout.strip().strip(","))
    except Exception:
        return None
