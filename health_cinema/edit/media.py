"""ffmpeg plumbing for the compositor: exact-count raw frame readers (with hold-on-EOF), poster stills, an encoder pipe, probing and pause detection."""
from __future__ import annotations
import functools, re, subprocess, threading
from pathlib import Path
from typing import Iterator, List, Optional, Tuple
from PIL import Image

FPS = 24

def ffmpeg() -> str:
    from .. import assets
    return assets.ffmpeg_path() or "ffmpeg"

def ffprobe() -> str:
    from .. import assets
    return assets.ffprobe_path() or "ffprobe"

class Cancelled(RuntimeError): pass

def probe(path: str) -> dict:
    try: r = subprocess.run([ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", path], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired: return {"w": 0, "h": 0, "duration": 0.0}
    import json
    try:
        j = json.loads(r.stdout); s = (j.get("streams") or [{}])[0]; return {"w": int(s.get("width", 0)), "h": int(s.get("height", 0)), "duration": float(j["format"]["duration"])}
    except Exception: return {"w": 0, "h": 0, "duration": 0.0}

def read_frames(path: str, W: int, H: int, start: float, count: int, loop: bool = False, cancel: Optional[threading.Event] = None) -> Iterator[Image.Image]:
    """Exactly `count` RGB frames at 24 fps, cover-scaled to W x H, from `start` seconds. Past the end of the file the last frame is held (or the file loops)."""
    cmd = [ffmpeg(), "-v", "error", "-ss", f"{max(0.0, start):.3f}"] + (["-stream_loop", "-1"] if loop else []) + ["-i", path, "-vf",
           f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=W * H * 3 * 2); n = W * H * 3; last = None; got = 0
    try:
        while got < count:
            if cancel is not None and cancel.is_set(): raise Cancelled("cancelled")
            b = p.stdout.read(n)
            if len(b) < n: break
            last = Image.frombytes("RGB", (W, H), b); got += 1; yield last
        if last is None: raise RuntimeError(f"no frames could be read from {path}")
        while got < count: got += 1; yield last
    finally:
        try: p.kill()
        except Exception: pass
        try: p.stdout.close()
        except Exception: pass
        try: p.wait(timeout=30)
        except Exception: pass

@functools.lru_cache(maxsize=64)
def poster(path: str, t: float, W: int = 640, H: int = 360) -> Image.Image:
    try: r = subprocess.run([ffmpeg(), "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", path, "-frames:v", "1", "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=120)
    except subprocess.TimeoutExpired: raise RuntimeError(f"poster from {path} timed out")
    if len(r.stdout) < W * H * 3: raise RuntimeError(f"no poster from {path}")
    return Image.frombytes("RGB", (W, H), r.stdout[: W * H * 3])

class Encoder:
    """libx264 pipe for intermediates (visually lossless crf) and the final (set crf/preset)."""
    def __init__(self, out: Path, W: int, H: int, crf: int = 12, preset: str = "fast", audio: Optional[str] = None, abr: str = "192k", extra: Optional[List[str]] = None, frames: Optional[int] = None):
        cmd = [ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
        if audio: cmd += ["-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", abr, "-shortest"]
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-g", "48", "-threads", "4", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                "-movflags", "+faststart"] + (extra or []) + [str(out)]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE); self.out = out; self.n = 0
        self._err: List[bytes] = []; threading.Thread(target=lambda: self._err.append(self.p.stderr.read()), daemon=True).start()
    def write(self, im: Image.Image) -> None:
        try: self.p.stdin.write(im.tobytes()); self.n += 1
        except BrokenPipeError: raise RuntimeError("ffmpeg encoder stopped: " + b"".join(self._err).decode("utf-8", "ignore")[-300:])
    def close(self) -> None:
        self.p.stdin.close()
        try: rc = self.p.wait(timeout=3600)
        except subprocess.TimeoutExpired: self.p.kill(); self.p.wait(timeout=30); raise RuntimeError('ffmpeg encoder timed out')
        if rc != 0: raise RuntimeError(f"ffmpeg exit {rc}: " + b"".join(self._err).decode("utf-8", "ignore")[-300:])
    def abort(self) -> None:
        try: self.p.kill()
        except Exception: pass
        try: self.p.stdin.close()
        except Exception: pass
        try: self.p.wait(timeout=30)
        except Exception: pass

def detect_pauses(wav: str, noise_db: int = -30, min_s: float = 0.08) -> List[Tuple[float, float]]:
    """(start, end) of near-silent gaps in the narration (breaths and comma pauses); used only to snap caption phrase boundaries."""
    try: r = subprocess.run([ffmpeg(), "-hide_banner", "-i", wav, "-af", f"silencedetect=noise={noise_db}dB:d={min_s}", "-f", "null", "-"], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired: return []
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]; ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends))

def read_frames_exact(path: str, W: int, H: int, first: int, count: int, cancel=None) -> Iterator[Image.Image]:
    """`count` frames of an intermediate clip (already 24 fps at W x H) starting at frame index `first`; errors if the clip is short."""
    cmd = [ffmpeg(), "-v", "error", "-ss", f"{max(0.0, (first - 0.25) / FPS):.4f}", "-i", path, "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=W * H * 3 * 2); n = W * H * 3
    try:
        for k in range(count):
            if cancel is not None and cancel.is_set(): raise Cancelled("cancelled")
            b = p.stdout.read(n)
            if len(b) < n: raise RuntimeError(f"{path}: expected {count} frames from index {first}, got {k}")
            yield Image.frombytes("RGB", (W, H), b)
    finally:
        try: p.kill()
        except Exception: pass
        try: p.stdout.close()
        except Exception: pass
        try: p.wait(timeout=30)
        except Exception: pass
