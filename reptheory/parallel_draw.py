"""Rep Theory (and Cat / Carl Jung / Elder / Survival Theory) frames drawn on every CPU core.

A long video is ~34,000 frames; one process draws them one after another on one core (a 23-min Carl Jung video took hours on a
Windows PC, 2026-11-11). Every frame comes from the plan alone (engine.draw_frame), so the video is cut into stretches of frames;
each worker process draws its stretches into its own video-only file, and one last ffmpeg joins them (no re-encode) and adds the
sound. The picture is the same as the one-process render.

Safe by default: a short video, a one-core machine, too little free memory, or a pool that cannot start returns False and the
engine draws in one process exactly as before. A stretch that fails in a worker is drawn again here. Stop is seen within a second.
"""
from __future__ import annotations

import os
import pickle
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, List, Optional

MIN_FRAMES = 24 * 45            # under ~45 s one process is quicker than starting the pool
MAX_WORKERS = 12
MIN_CHUNK = 240                 # frames in one stretch, at least (10 s)
CHUNKS_PER_WORKER = 3           # a few stretches each, so a core that finishes early takes the next one
WORKER_RAM_GB = 1.2             # free memory one worker may need (its pictures + the encoder)
ENV = "REP_THEORY_WORKERS"      # "1" = one process; a number = that many workers (tests, a machine that needs it lower)


def workers(n_frames: int) -> int:
    """How many worker processes to use for this many frames (1 = draw in one process, as before)."""
    env = os.environ.get(ENV, "").strip()
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    if n_frames < MIN_FRAMES:
        return 1
    n = min(MAX_WORKERS, max(1, (os.cpu_count() or 1) - 1))
    try:
        import psutil
        n = min(n, max(1, int(psutil.virtual_memory().available / (WORKER_RAM_GB * 1024 ** 3))))
    except Exception:
        pass
    return n


def chunks(n_frames: int, n_workers: int) -> List[tuple]:
    """[(first, end)] stretches covering 0..n_frames, in order."""
    k = max(1, min(n_workers * CHUNKS_PER_WORKER, n_frames // MIN_CHUNK))
    edges = [round(i * n_frames / k) for i in range(k + 1)]
    return [(a, b) for a, b in zip(edges, edges[1:]) if b > a]


def _popen(cmd, **kw):
    try:
        from providers import hidden_subprocess      # Windows: no black console box from the worker's ffmpeg
        return hidden_subprocess.popen(cmd, **kw)
    except ImportError:
        return subprocess.Popen(cmd, **kw)


def _run(cmd, **kw):
    try:
        from providers import hidden_subprocess
        return hidden_subprocess.run(cmd, **kw)
    except ImportError:
        return subprocess.run(cmd, **kw)


_STATE: dict = {}


def draw_chunk(state_path: str, a: int, b: int, out_path: str, prog_path: str, stop_path: str, ff: str) -> str:
    """In a worker (or here, for a retry): frames a..b-1 into a video-only mp4 at out_path; progress (frames done) in prog_path."""
    from . import draw as D, engine as E, theme as T
    if _STATE.get("path") != state_path:
        st = pickle.loads(Path(state_path).read_bytes())
        T.set_theme(st["theme"])
        _STATE.clear(); _STATE.update(st, path=state_path, ctx=D.Ctx(st["W"], st["H"]))
    st = _STATE; W, H = st["W"], st["H"]
    part = out_path + ".part"
    cmd = [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(T.FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-threads", "2", "-f", "mp4", part]
    with open(out_path + ".log", "wb") as errf:
        proc = _popen(cmd, stdin=subprocess.PIPE, stderr=errf)
        try:
            for f in range(a, b):
                if (f - a) % 24 == 0:
                    if os.path.exists(stop_path):
                        raise RuntimeError("stopped")
                    Path(prog_path).write_text(str(f - a))
                proc.stdin.write(E.draw_frame(f, st["scenes"], st["starts"], st["n_narr"], st["ctx"], st["card"]).tobytes())
            proc.stdin.close(); rc = proc.wait(timeout=3600)
        except BaseException:
            try:
                proc.kill(); proc.wait(5)
            except Exception:
                pass
            raise
    if rc != 0:
        raise RuntimeError("ffmpeg failed: " + Path(out_path + ".log").read_text(errors="replace")[-300:])
    os.replace(part, out_path); Path(prog_path).write_text(str(b - a))
    return out_path


def _done_frames(jobs: list) -> int:
    n = 0
    for j in jobs:
        try:
            n += int(Path(j["prog"]).read_text() or 0)
        except (OSError, ValueError):
            pass
    return n


def render(scenes: List[dict], starts: List[int], n_narr: int, n_frames: int, card: Optional[dict], W: int, H: int, audio: Optional[str],
           out_tmp: Path, cancelled: Callable[[], bool], prog: Callable[[float, str], None], log: Callable[[str], None], ff: str) -> bool:
    """Draws the whole video into out_tmp on several cores and adds the sound. False = not done here (the engine draws in one process)."""
    from . import engine as E, theme as T
    n = workers(n_frames)
    if n < 2:
        return False
    work = Path(str(out_tmp) + ".frames"); shutil.rmtree(work, ignore_errors=True); work.mkdir(parents=True, exist_ok=True)
    try:
        state = work / "plan.pkl"
        try:
            state.write_bytes(pickle.dumps({"scenes": scenes, "starts": starts, "n_narr": n_narr, "card": card, "W": W, "H": H, "theme": T.THEME}))
        except Exception as ex:
            log(f"[REP THEORY SPEED] one core: the plan could not be handed to the workers ({type(ex).__name__}: {ex})"); return False
        stop = str(work / "STOP")
        jobs = [{"a": a, "b": b, "out": str(work / f"part_{i:04d}.mp4"), "prog": str(work / f"part_{i:04d}.prog")} for i, (a, b) in enumerate(chunks(n_frames, n))]
        n = min(n, len(jobs))
        log(f"[REP THEORY SPEED] drawing {n_frames} frames on {n} CPU cores ({len(jobs)} stretches)")
        t0 = time.time(); failed: List[dict] = []
        try:
            import multiprocessing as mp
            from concurrent.futures import ProcessPoolExecutor
            ex = ProcessPoolExecutor(max_workers=n, mp_context=mp.get_context("spawn"))
        except Exception as e:
            log(f"[REP THEORY SPEED] one core: the worker processes could not start ({type(e).__name__}: {e})"); return False
        try:
            futs = {ex.submit(draw_chunk, str(state), j["a"], j["b"], j["out"], j["prog"], stop, ff): j for j in jobs}
            last = -1
            while True:
                if cancelled():
                    Path(stop).write_text("stop")
                    for fu in futs: fu.cancel()
                    raise E.Cancelled("cancelled")
                pending = [fu for fu in futs if not fu.done()]
                d = _done_frames(jobs)
                if d != last:
                    last = d; el = time.time() - t0; left = el / d * (n_frames - d) if d else 0
                    prog(0.10 + 0.85 * d / n_frames, f"drawing on {n} cores: {d}/{n_frames} frames" + (f", about {left / 60:.0f} min left" if d and el > 20 else ""))
                if not pending:
                    break
                time.sleep(1.0)
            for fu, j in futs.items():
                try:
                    fu.result(timeout=5.0)   # every worker is already done here (the loop above waited for them)
                except Exception as e:
                    failed.append(j); log(f"[REP THEORY SPEED] frames {j['a']}-{j['b']} failed in a worker ({type(e).__name__}: {str(e)[:160]}); drawing them again here")
        finally:
            ex.shutdown(wait=True, cancel_futures=True)
        for j in failed:      # a stretch that broke in a worker is drawn again in this process; a second failure fails the render as one process would
            if cancelled():
                raise E.Cancelled("cancelled")
            Path(j["out"]).unlink(missing_ok=True); draw_chunk(str(state), j["a"], j["b"], j["out"], j["prog"], stop, ff)
        log(f"[REP THEORY SPEED] frames drawn in {(time.time() - t0) / 60:.1f} min on {n} cores")
        prog(0.96, "joining the video and adding the sound")
        lst = work / "parts.txt"
        lst.write_text("".join("file '" + Path(j["out"]).resolve().as_posix().replace("'", "'\\''") + "'\n" for j in jobs), encoding="utf-8")
        cmd = [ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst)]
        if audio:
            cmd += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-af", "apad", "-t", f"{n_frames / T.FPS:.3f}"]
        cmd += ["-c:v", "copy", "-movflags", "+faststart", "-f", "mp4", str(out_tmp)]
        r = _run(cmd, capture_output=True, timeout=3600)
        if r.returncode != 0:
            raise RuntimeError("joining the video failed: " + (r.stderr or b"").decode(errors="replace")[-400:])
        return True
    finally:
        shutil.rmtree(work, ignore_errors=True)
