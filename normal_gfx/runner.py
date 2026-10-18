"""Client for gfx-overlay-engine: render gfx-core templates to transparent PNG sequences, reusing earlier results.

    render_overlays(jobs, width, height, fps, cache_root=None, log=print, cancel_check=None) -> {job.key: Result}

A job is a template drawn once: {template, slots, len, cues, images}. Its cache key covers the engine version, the gfx-core source (every lib module,
the template file and the fonts), the template JSON, slots, cues, images (by content), length, size and frame rate; the same job is never drawn twice,
and a cache hit starts no browser. One template failing (or a missing browser) gives that Result an `error`; it never raises, and the caller skips
the graphic. Results live in <cache_root>/<key>/ (00001.png ..., meta.json), written to <key>.part first and renamed when complete.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ENGINE_VERSION = "4"


@dataclass
class Job:
    template: Dict[str, Any]
    slots: Dict[str, Any] = field(default_factory=dict)
    len: float = 4.0
    cues: Dict[str, float] = field(default_factory=dict)
    images: Dict[str, str] = field(default_factory=dict)   # name -> file
    dy: float = 0.0                                        # the whole graphic moved by this share of the frame height (negative = up)
    scale: float = 1.0                                     # uniform scale about `anchor` (x, y as fractions of the frame): proportions are kept
    anchor: Tuple[float, float] = (0.0, 0.0)


@dataclass
class Result:
    key: str
    dir: Optional[Path] = None
    frames: int = 0
    box: Optional[List[int]] = None     # x0, y0, x1, y1 of everything the template draws
    ink: Optional[List[int]] = None     # the same for its opaque parts (type, bars, rings), not the soft backing
    band_max: int = 0                   # strongest alpha anywhere in the caption area (bottom 22 %, side margins 8 %)
    entry_s: Optional[float] = None     # seconds from the start until something is clearly visible (alpha >= 96): when the graphic really enters
    cached: bool = False
    error: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error and self.dir is not None

    @property
    def envelope(self) -> Path:
        return Path(self.dir) / "envelope.png"

    def frame(self, i: int) -> Path:
        return Path(self.dir) / f"{i + 1:05d}.png"


class OverlayError(RuntimeError):
    pass


def engine_dir() -> Path:
    from map_scene.render import _find

    found = _find("gfx-overlay-engine/render.mjs")
    if found is None:
        raise OverlayError("The graphics renderer (gfx-overlay-engine/render.mjs) is missing from this install.")
    return found.parent


def cache_root() -> Path:
    override = os.environ.get("VIDEOGEN_GFX_CACHE")
    if override:
        base = Path(override)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / "SemanticYTStudio" / "gfx_overlays"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "SemanticYTStudio" / "Cache" / "gfx_overlays"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "semantic-yt-studio" / "gfx_overlays"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_SOURCE_CACHE: Dict[str, str] = {}


def source_hash() -> str:
    """The drawing code and look of the templates: gfx-core lib modules and fonts, the engine page, and the Montserrat font. A change to any of
    them draws different frames, so it is part of every key."""
    eng = engine_dir()
    root = eng.parent
    files = sorted((root / "gfx-core" / "lib").glob("*.mjs")) + sorted((root / "gfx-core" / "fonts").glob("*.ttf")) \
        + [eng / "page.js", eng / "page.html", eng / "render.mjs", root / "pakmap-engine" / "assets" / "fonts" / "Montserrat-VF.ttf"]
    stamp = "|".join(f"{p.name}:{p.stat().st_size}:{int(p.stat().st_mtime_ns)}" for p in files if p.is_file())
    if stamp in _SOURCE_CACHE:
        return _SOURCE_CACHE[stamp]
    h = hashlib.sha1(ENGINE_VERSION.encode())
    for p in files:
        if p.is_file():
            h.update(p.name.encode())
            h.update(_file_hash(p).encode())
    _SOURCE_CACHE.clear()
    _SOURCE_CACHE[stamp] = h.hexdigest()
    return _SOURCE_CACHE[stamp]


def job_key(job: Job, width: int, height: int, fps: int) -> str:
    imgs = {name: _file_hash(Path(f)) for name, f in sorted(job.images.items()) if Path(f).is_file()}
    payload = json.dumps({"src": source_hash(), "t": job.template, "s": job.slots, "c": job.cues, "i": imgs, "len": round(float(job.len), 3), "dy": round(float(job.dy), 4), "k": round(float(job.scale), 4), "a": [round(float(v), 3) for v in job.anchor],
                          "w": int(width), "h": int(height), "fps": int(fps)}, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()[:24]


MAX_CACHE_BYTES = 3 * 1024 ** 3    # a long video's graphics are a few hundred MB of PNG; the oldest sequences go first beyond this


def prune(root: Path, keep: Sequence[str] = (), max_bytes: int = MAX_CACHE_BYTES) -> int:
    """Delete the least recently used sequences until the cache fits max_bytes (never those in `keep`). Returns how many were removed."""
    try:
        entries = []
        for d in Path(root).iterdir():
            if d.is_dir() and not d.name.endswith(".part"):
                size = sum(f.stat().st_size for f in d.iterdir() if f.is_file())
                entries.append((d.stat().st_mtime, d, size))
        total = sum(e[2] for e in entries)
        removed = 0
        for _mt, d, size in sorted(entries, key=lambda e: e[0]):
            if total <= max_bytes:
                break
            if d.name in keep:
                continue
            shutil.rmtree(d, ignore_errors=True)
            total -= size
            removed += 1
        return removed
    except OSError:
        return 0


def _touch(d: Path) -> None:
    try:
        os.utime(d, None)      # a cache hit counts as use (least recently used goes first)
    except OSError:
        pass


def _read_meta(d: Path) -> Optional[dict]:
    try:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        if meta.get("frames") and (d / f"{int(meta['frames']):05d}.png").is_file() and (d / "00001.png").is_file():
            return meta
    except (OSError, ValueError):
        pass
    return None


def _browser_job(width: int, height: int, fps: int) -> dict:
    from map_scene.render import _browser_channel, _ensure_browser, _node

    try:
        from providers.flow.engine_manager import _find_flow_engine_dir

        playwright_dir = str(_find_flow_engine_dir())
    except Exception:
        playwright_dir = None
    try:
        from providers.playwright_chromium import is_playwright_chromium_installed, system_chrome_available

        if not (is_playwright_chromium_installed() or system_chrome_available()):
            print("[GFX] First use of the template graphics: a browser (about 150 MB) is downloaded once, which can take a few minutes. "
                  "Nothing else needs to be installed.")
    except Exception:
        pass
    _ensure_browser()      # downloads Chromium once when there is neither Chrome nor Playwright's own (as Flow and pakMap do)
    _node()
    return {"width": width, "height": height, "fps": fps, "playwright_dir": playwright_dir, "browser_channel": _browser_channel()}


def render_overlays(jobs: Sequence[Job], width: int, height: int, fps: int, *, root: Optional[Path] = None, log: Callable[[str], None] = print,
                    cancel_check: Optional[Callable[[], bool]] = None, timeout_s: float = 1800.0) -> Dict[str, Result]:
    """Every job drawn (or found in the cache). Returns {key: Result}; keys come from job_key, equal jobs share one. Never raises."""
    root = Path(root) if root else None
    out: Dict[str, Result] = {}
    todo: List[tuple] = []
    try:
        root = root or cache_root()
        root.mkdir(parents=True, exist_ok=True)
        for job in jobs:
            key = job_key(job, width, height, fps)
            if key in out:
                continue
            meta = _read_meta(root / key)
            bad = root / f"{key}.fail"
            if not meta and bad.is_file():      # this template cannot draw these slots (a template-level failure, remembered); a browser problem is not
                out[key] = Result(key, error=bad.read_text(encoding="utf-8").strip() or "failed earlier")
                continue
            if meta:
                _touch(root / key)
                out[key] = Result(key, root / key, int(meta["frames"]), meta.get("box"), meta.get("ink"), int(meta.get("band_max") or 0), meta.get("entry_s"), cached=True,
                                  warnings=list(meta.get("warnings") or []))
            else:
                out[key] = Result(key, error="not drawn yet")
                todo.append((key, job))
    except Exception as exc:
        for job in jobs:
            out.setdefault(f"error{len(out)}", Result("", error=f"graphics cache unavailable: {exc}"))
        return out
    prune(root, keep=[k for k in out])
    if not todo:
        return out
    try:
        base = _browser_job(width, height, fps)
        eng = engine_dir()
        from map_scene.render import _node
    except Exception as exc:
        for key, _ in todo:
            out[key].error = f"graphics renderer unavailable: {exc}"
        log(f"[GFX] graphics renderer unavailable, these graphics are skipped: {exc}")
        return out
    items = []
    for key, job in todo:
        part = root / f"{key}.part"
        shutil.rmtree(part, ignore_errors=True)
        items.append({"key": key, "dir": str(part), "template": job.template, "slots": job.slots, "len": float(job.len), "cues": job.cues, "dy": float(job.dy), "scale": float(job.scale), "anchor": [float(v) for v in job.anchor],
                      "images": {n: str(Path(f).resolve()) for n, f in job.images.items() if Path(f).is_file()}})
    with tempfile.TemporaryDirectory(prefix="gfxov_") as tmp:
        jpath = Path(tmp) / "job.json"
        jpath.write_text(json.dumps(dict(base, items=items)), encoding="utf-8")
        from providers import hidden_subprocess as hs

        proc = hs.popen([_node(), str(eng / "render.mjs"), str(jpath)], cwd=str(eng), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        encoding="utf-8", errors="replace")
        stderr: List[str] = []
        err_thread = threading.Thread(target=lambda: stderr.extend(proc.stderr), daemon=True)
        err_thread.start()
        timer = threading.Timer(timeout_s, proc.kill)
        timer.start()
        fatal = ""
        try:
            for raw in proc.stdout:
                if cancel_check is not None and cancel_check():
                    proc.kill()
                    break
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                kind, key = ev.get("event"), ev.get("key")
                if kind == "item_done" and key in out:
                    part, final = root / f"{key}.part", root / key
                    shutil.rmtree(final, ignore_errors=True)
                    os.replace(part, final)
                    out[key] = Result(key, final, int(ev.get("frames") or 0), ev.get("box"), ev.get("ink"), int(ev.get("band_max") or 0), ev.get("entry_s"),
                                      warnings=list(ev.get("warnings") or []))
                elif kind == "item_error" and key in out:
                    out[key].error = str(ev.get("message") or "failed")
                    shutil.rmtree(root / f"{key}.part", ignore_errors=True)
                    try:
                        (root / f"{key}.fail").write_text(out[key].error, encoding="utf-8")
                    except OSError:
                        pass
                elif kind == "error":
                    fatal = str(ev.get("message") or "the graphics renderer failed")
            proc.wait()
            err_thread.join(timeout=3)
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
    for key, _ in todo:
        r = out[key]
        if not r.ok:
            if r.error == "not drawn yet":
                why = fatal or " ".join("".join(stderr[-5:]).split())[:240]
                # nothing came back at all: the browser did not start (missing, blocked or crashed)
                r.error = f"graphics renderer unavailable: {why or 'the browser did not start'}"
            shutil.rmtree(root / f"{key}.part", ignore_errors=True)
            log(f"[GFX] a graphic could not be drawn and is skipped: {r.error}")
    return out
