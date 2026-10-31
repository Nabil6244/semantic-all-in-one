"""Cached, cancellable render of a Health Cinema 3D journey (Three.js backend by default).

Cache: one folder per deterministic key under the cache root holding journey.mp4 + manifest.json. The key covers the spec, the anchors, the
model file (content hash), resolution/fps, backend settings and the code that shapes the output (sampler, overlay, page/render scripts,
VERSION). A hit returns the stored clip without rendering; any change to those inputs produces a different key. Frames are rendered into
a temporary folder next to the entry and the finished clip is moved into place atomically, so a cancelled or failed render leaves nothing."""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, threading, time
from pathlib import Path
from typing import Callable, Optional

from . import journey, overlay

VERSION = "1"
DEFAULT_SIZE = (1920, 1080)   # Health Cinema is a landscape 16:9 style; this is the default export
PREVIEW_SIZE = (1280, 720)
HERE = Path(__file__).resolve().parent
CODE_FILES = (HERE / "journey.py", HERE / "overlay.py", HERE / "threejs" / "page.js", HERE / "threejs" / "procedural.js", HERE / "threejs" / "conditions.js", HERE / "threejs" / "atmosphere.js", HERE / "threejs" / "bodymap.js", HERE / "threejs" / "page.html", HERE / "threejs" / "render.mjs", HERE / "threejs" / "render_worker.mjs")

class Cancelled(RuntimeError): pass

def _kill_tree(p) -> None:
    """Kill a child and everything it started (node launches Chromium: killing node alone would orphan the browser)."""
    try:
        import psutil
        parent = psutil.Process(p.pid); procs = parent.children(recursive=True) + [parent]
        for q in procs:
            try: q.kill()
            except psutil.Error: pass
        psutil.wait_procs(procs, timeout=5)
    except Exception:
        try: p.kill()
        except Exception: pass

def _sha(b: bytes) -> str: return hashlib.sha256(b).hexdigest()

def file_hash(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def code_version(files=CODE_FILES) -> str:
    return _sha((VERSION + "".join(file_hash(f) for f in files if Path(f).exists())).encode())[:16]

def cache_key(spec_path, anchors_path, model_path, W, H, fps, backend="threejs", settings: Optional[dict] = None, code: Optional[str] = None) -> str:
    spec = json.dumps(json.loads(Path(spec_path).read_text(encoding="utf-8")), sort_keys=True, separators=(",", ":"))
    parts = [spec, file_hash(anchors_path), file_hash(model_path), f"{int(W)}x{int(H)}@{int(fps)}", backend,
             json.dumps(settings or {}, sort_keys=True), code or code_version()]
    return _sha("\x1f".join(parts).encode())[:24]

def run_cancellable(cmd, cancel: Optional[threading.Event] = None, timeout: Optional[float] = None, on_line: Optional[Callable[[str], None]] = None, cwd=None, env=None) -> str:
    """Run a child process, killing it on cancel or timeout. Returns stdout. Raises Cancelled / TimeoutError / RuntimeError(exit code)."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=cwd, env=env)
    lines: list = []
    def pump():
        for ln in p.stdout:
            lines.append(ln)
            if on_line: on_line(ln)
    th = threading.Thread(target=pump, daemon=True); th.start(); t0 = time.time()
    try:
        while p.poll() is None:
            if cancel is not None and cancel.is_set(): raise Cancelled("cancelled")
            if timeout is not None and time.time() - t0 > timeout: raise TimeoutError(f"timed out after {timeout}s")
            time.sleep(0.05)
    except BaseException:
        _kill_tree(p)
        try: p.wait(timeout=30)
        except Exception: pass
        raise
    finally:
        th.join(timeout=2)
        if not th.is_alive():      # the reader is done: release the pipe now instead of leaving one open per child process until GC
            try: p.stdout.close()
            except Exception: pass
    out = "".join(lines)
    if p.returncode != 0: raise RuntimeError(f"exit {p.returncode}: {out[-800:]}")
    return out

def _node() -> str:
    from . import assets
    return assets.node_path() or "node"

def _ffmpeg() -> str:
    from . import assets
    return assets.ffmpeg_path() or "ffmpeg"

def threejs_frames(frames_json, model_path, out_dir, W, H, cancel=None, timeout=1800, on_line=None) -> None:
    """Default frame renderer: node + Playwright Chromium + three.js (health_cinema/threejs/render.mjs)."""
    from . import assets
    miss = assets.missing_threejs_files()
    if miss: raise RuntimeError("Three.js renderer files missing: " + ", ".join(miss[:4]))
    script = assets._find("health_cinema/threejs/render.mjs") or (HERE / "threejs" / "render.mjs")
    env = dict(os.environ); ch = assets.browser_channel()
    if ch: env["HC_BROWSER_CHANNEL"] = ch
    run_cancellable([_node(), str(script), str(frames_json), str(model_path), str(out_dir), str(W), str(H)], cancel, timeout, on_line, env=env)

# ---- one browser for many clips: a small pool of render_worker.mjs processes (each keeps its Chromium open between clips) ----
class _Worker:
    def __init__(self):
        import queue
        from . import assets
        script = assets._find("health_cinema/threejs/render_worker.mjs") or (HERE / "threejs" / "render_worker.mjs")
        env = dict(os.environ); ch = assets.browser_channel()
        if ch: env["HC_BROWSER_CHANNEL"] = ch
        self.p = subprocess.Popen([_node(), str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env)
        self.q: "queue.Queue" = queue.Queue(); self.n = 0
        threading.Thread(target=self._pump, daemon=True).start()
        self._wait(lambda m: m.get("event") == "ready", None, 90)

    def _pump(self):
        for ln in self.p.stdout:
            try: self.q.put(json.loads(ln))
            except ValueError: pass
        self.q.put({"event": "exit"})

    def _wait(self, want, cancel, timeout):
        import queue
        t0 = time.time()
        while True:
            if cancel is not None and cancel.is_set(): raise Cancelled("cancelled")
            if timeout is not None and time.time() - t0 > timeout: raise TimeoutError(f"timed out after {timeout}s")
            try: m = self.q.get(timeout=0.1)
            except queue.Empty: continue
            if m.get("event") == "exit": raise RuntimeError("the 3D render worker stopped")
            if want(m): return m

    def render(self, frames_json, model_path, out_dir, W, H, cancel, timeout) -> dict:
        self.n += 1; jid = self.n
        self.p.stdin.write(json.dumps({"id": jid, "frames": str(frames_json), "glb": str(model_path), "out": str(out_dir), "w": int(W), "h": int(H)}) + "\n"); self.p.stdin.flush()
        m = self._wait(lambda m: m.get("id") == jid and m.get("event") in ("done", "error"), cancel, timeout)
        if m["event"] == "error": raise RuntimeError(m.get("message", "3D render failed")[-800:])
        return m

    def kill(self):
        try: self.p.stdin.close()
        except Exception: pass
        _kill_tree(self.p)


_POOL: list = []; _POOL_LOCK = threading.Lock(); _POOL_LIVE = [0]
POOL_MAX = max(1, int(os.environ.get("HEALTH_CINEMA_3D_WORKERS", 2)))


def pooled_frames(frames_json, model_path, out_dir, W, H, cancel=None, timeout=1800, on_line=None) -> None:
    """The default frame renderer: the same page and frames as threejs_frames, from a worker whose browser stays open between clips."""
    from . import assets
    miss = assets.missing_threejs_files()
    if miss: raise RuntimeError("Three.js renderer files missing: " + ", ".join(miss[:4]))
    with _POOL_LOCK:
        w = _POOL.pop() if _POOL else None
        if w is None: _POOL_LIVE[0] += 1
    try:
        if w is None: w = _Worker()
        w.render(frames_json, model_path, out_dir, W, H, cancel, timeout)
    except BaseException:
        if w is not None: w.kill()      # a failed or cancelled worker is never reused
        with _POOL_LOCK: _POOL_LIVE[0] -= 1
        raise
    with _POOL_LOCK: _POOL.append(w)


def close_pool() -> None:
    """Stop every idle worker and its browser (the engine calls this when a render ends)."""
    with _POOL_LOCK:
        ws = list(_POOL); _POOL.clear(); _POOL_LIVE[0] -= len(ws)
    for w in ws: w.kill()


import atexit
atexit.register(close_pool)

_KEY_LOCKS: dict = {}; _KEY_LOCKS_GUARD = threading.Lock()


def _key_lock(key: str) -> threading.Lock:
    """One lock per clip: two scenes asking for the same clip at once (parallel render) make it once; the second takes the cached file."""
    with _KEY_LOCKS_GUARD:
        return _KEY_LOCKS.setdefault(key, threading.Lock())


def render_journey(spec_path, anchors_path, model_path, W, H, fps, cache_root, **kw) -> dict:
    cache_root = Path(cache_root); cache_root.mkdir(parents=True, exist_ok=True)
    key = cache_key(spec_path, anchors_path, model_path, W, H, fps, "threejs", kw.get("settings"), kw.get("code"))
    with _key_lock(key):
        return _render_journey(spec_path, anchors_path, model_path, W, H, fps, cache_root, key, **kw)


def _render_journey(spec_path, anchors_path, model_path, W, H, fps, cache_root, key, *, cancel: Optional[threading.Event] = None, settings: Optional[dict] = None,
                    frame_renderer: Callable = threejs_frames, code: Optional[str] = None, on_line=None) -> dict:
    entry = cache_root / key; clip = entry / "journey.mp4"; man = entry / "manifest.json"
    if clip.exists() and clip.stat().st_size > 0 and man.exists():
        return {"path": str(clip), "cache_hit": True, "key": key, "seconds": 0.0}
    t0 = time.time(); tmp = cache_root / f".{key}.tmp{os.getpid()}_{threading.get_ident()}"; shutil.rmtree(tmp, ignore_errors=True); (tmp / "frames").mkdir(parents=True)      # one folder per render, also when scenes render in parallel
    try:
        spec, A, frames = journey.sample(spec_path, anchors_path, fps, W, H)
        fj = tmp / "frames.json"; fj.write_text(json.dumps({"spec": spec, "anchors": A, "frames": frames}))
        if cancel is not None and cancel.is_set(): raise Cancelled("cancelled")
        frame_renderer(fj, model_path, tmp / "frames", W, H, cancel=cancel, on_line=on_line)
        if cancel is not None and cancel.is_set(): raise Cancelled("cancelled")
        n = len(list((tmp / "frames").glob("f*.png")))
        if n != len(frames): raise RuntimeError(f"renderer produced {n} of {len(frames)} frames")
        overlay.run(fj, tmp / "frames", tmp / "journey.mp4", fps, ffmpeg=_ffmpeg())
        shutil.rmtree(tmp / "frames", ignore_errors=True); (tmp / "frames.json").unlink(missing_ok=True)
        (tmp / "manifest.json").write_text(json.dumps({"key": key, "W": W, "H": H, "fps": fps, "frames": n, "version": VERSION, "seconds": round(time.time() - t0, 2)}))
        shutil.rmtree(entry, ignore_errors=True); os.replace(tmp, entry)
        return {"path": str(clip), "cache_hit": False, "key": key, "seconds": time.time() - t0}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":   # render_journey.py SPEC ANCHORS GLB CACHE_ROOT [W H FPS]   (default 1920x1080 @ 24; refuses non-16:9)
    a = sys.argv[1:]; W, H, fps = (int(a[4]), int(a[5]), int(a[6])) if len(a) >= 7 else (*DEFAULT_SIZE, 24)
    if abs(W / H - 16 / 9) > 0.01: raise SystemExit("Health Cinema renders 16:9 landscape only")
    print(json.dumps(render_journey(a[0], a[1], a[2], W, H, fps, a[3])))
