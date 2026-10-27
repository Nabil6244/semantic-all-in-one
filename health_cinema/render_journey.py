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
CODE_FILES = (HERE / "journey.py", HERE / "overlay.py", HERE / "threejs" / "page.js", HERE / "threejs" / "page.html", HERE / "threejs" / "render.mjs")

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
    spec = json.dumps(json.load(open(spec_path)), sort_keys=True, separators=(",", ":"))
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

def render_journey(spec_path, anchors_path, model_path, W, H, fps, cache_root, *, cancel: Optional[threading.Event] = None, settings: Optional[dict] = None,
                   frame_renderer: Callable = threejs_frames, code: Optional[str] = None, on_line=None) -> dict:
    cache_root = Path(cache_root); cache_root.mkdir(parents=True, exist_ok=True)
    key = cache_key(spec_path, anchors_path, model_path, W, H, fps, "threejs", settings, code)
    entry = cache_root / key; clip = entry / "journey.mp4"; man = entry / "manifest.json"
    if clip.exists() and clip.stat().st_size > 0 and man.exists():
        return {"path": str(clip), "cache_hit": True, "key": key, "seconds": 0.0}
    t0 = time.time(); tmp = cache_root / f".{key}.tmp{os.getpid()}"; shutil.rmtree(tmp, ignore_errors=True); (tmp / "frames").mkdir(parents=True)
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
