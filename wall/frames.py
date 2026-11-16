"""Decoded clip frames for the wall's video prints.

A window of a clip (clip seconds a..b) is decoded ONCE with ffmpeg into JPEG frames (scaled and cropped to 16:9 exactly like the shared
renderer fills the frame), kept in the work dir, and read back one frame at a time. A few decoded frames stay in memory per clip, so a
long film on a 16 GB machine never holds more than a handful of pictures per print.

    window(path, a, b, res, work) -> Frames      shared per process (one decode even when several render threads ask at once)
    Frames.at(clip_t) -> PIL RGB or None         past the decoded window the clip plays back and forth (ping-pong), never a frozen frame
    pingpong(i, n) -> index in 0..n-1
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

FPS = 25
KEEP = 6                           # decoded pictures kept in memory per clip

_LOCK = threading.Lock()
_WINDOWS: Dict[str, "Frames"] = {}


def pingpong(i: int, n: int) -> int:
    if n <= 1:
        return 0
    period = 2 * n - 2
    p = i % period
    return p if p < n else period - p


def default_work() -> Path:
    return Path(tempfile.gettempdir()) / "wall_frames"


def _key(path: str, a: float, b: float, res: Tuple[int, int], graph: str = "") -> str:
    p = Path(path)
    try:
        st = p.stat()
        sig = f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    except OSError:
        sig = str(p)
    return hashlib.sha1(f"{sig}|{a:.3f}|{b:.3f}|{res[0]}x{res[1]}|{graph}".encode()).hexdigest()[:16]


class Frames:
    def __init__(self, path: str, a: float, b: float, res: Tuple[int, int], folder: Path, graph: str = ""):
        self.path, self.a, self.b, self.res, self.folder, self.graph = path, a, b, res, folder, graph
        self.files: Optional[List[Path]] = None
        self._mem: "OrderedDict[int, Image.Image]" = OrderedDict()
        self._lock = threading.Lock()

    def _ensure(self) -> List[Path]:
        if self.files is not None:
            return self.files
        with self._lock:
            if self.files is not None:
                return self.files
            done = self.folder / "done"
            if not done.is_file():
                # its own scratch folder per process and thread: several render processes may decode the same clip at once;
                # the first to finish publishes it, the others drop their copy
                tmp = self.folder.with_name(f"{self.folder.name}.part{os.getpid()}_{threading.get_ident()}")
                shutil.rmtree(tmp, ignore_errors=True)
                tmp.mkdir(parents=True, exist_ok=True)
                w, h = self.res
                head = ["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, self.a):.3f}", "-t", f"{max(0.04, self.b - self.a):.3f}", "-i", self.path]
                if self.graph:     # the style's own look of the shot ([0:v] -> [o]), then the print's size
                    body = ["-filter_complex", f"{self.graph};[o]scale={w}:{h},fps={FPS},setsar=1[q]", "-map", "[q]"]
                else:
                    body = ["-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},setsar=1"]
                try:
                    subprocess.run(head + body + ["-q:v", "3", str(tmp / "%05d.jpg")], check=True, capture_output=True, timeout=600)
                except Exception:  # noqa: BLE001 - a clip that will not decode leaves an empty print, never a stopped film
                    pass
                (tmp / "done").write_text("ok")
                if not done.is_file():
                    shutil.rmtree(self.folder, ignore_errors=True)      # a stale half-written folder from a stopped render
                    try:
                        tmp.replace(self.folder)
                    except OSError:            # another process published it first (the folder exists now)
                        pass
                shutil.rmtree(tmp, ignore_errors=True)
            self.files = sorted(self.folder.glob("*.jpg"))
            return self.files

    def __len__(self) -> int:
        return len(self._ensure())

    def at(self, clip_t: float) -> Optional[Image.Image]:
        files = self._ensure()
        if not files:
            return None
        i = pingpong(int(round((clip_t - self.a) * FPS)), len(files))
        with self._lock:
            im = self._mem.get(i)
            if im is not None:
                self._mem.move_to_end(i)
                return im
        try:
            im = Image.open(files[i]).convert("RGB")
        except Exception:  # noqa: BLE001
            return None
        with self._lock:
            self._mem[i] = im
            while len(self._mem) > KEEP:
                self._mem.popitem(last=False)
        return im


def window(path: str, a: float, b: float, res: Tuple[int, int] = (1280, 720), work: Optional[str] = None, graph: str = "") -> Frames:
    a = max(0.0, float(a))
    b = max(a + 0.04, float(b))
    root = Path(work) if work else default_work()
    k = _key(path, a, b, res, graph)
    with _LOCK:
        f = _WINDOWS.get(k)
        if f is None:
            root.mkdir(parents=True, exist_ok=True)
            f = _WINDOWS[k] = Frames(path, a, b, res, root / k, graph)
        return f


def forget() -> None:
    """Drop the in-memory windows (the JPEGs on disk stay until their work dir is removed)."""
    with _LOCK:
        _WINDOWS.clear()
