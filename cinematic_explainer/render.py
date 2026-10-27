"""Cinematic Explainer prototype renderer: footage in ffmpeg, cards drawn by cards.py and piped in as RGBA frames.

The dim + blur backdrop is made by ffmpeg itself (footage scaled down and back up, brightness x0.24, vignette) and blended with the clear
footage by one expression K(T), so it moves with the footage, costs no per-frame Python work and is the same on every run.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image

from . import cards, look as L
from .look import FPS, H, W


@dataclass
class Shot:
    path: str
    start: float
    end: float
    seek: float = 0.0
    treat: Optional[dict] = None      # War Documentary only (see war/segments.py): slow push/pan, grade, vignette, grain; None = untouched
    dissolve_in: float = 0.0          # War Documentary only: seconds the previous shot cross-fades into this one


@dataclass
class Layer:
    kind: str                    # key of cards.CARDS
    start: float
    end: float
    params: dict = field(default_factory=dict)
    dim: bool = False            # footage dims under this layer


def dim_spans(layers: Sequence[Layer]) -> List[Tuple[float, float]]:
    """Merged (start, end) spans where footage is dimmed; overlapping or touching spans become one."""
    spans = sorted((ly.start, ly.end) for ly in layers if ly.dim)
    merged: List[Tuple[float, float]] = []
    for a, b in spans:
        if merged and a - L.DIM_IN_S <= merged[-1][1] + L.DIM_IN_S:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def filter_graph(shots: Sequence[Shot], layers: Sequence[Layer]) -> str:
    n = len(shots)
    parts = []
    for i, s in enumerate(shots):
        parts.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,"
                     f"trim=duration={s.end - s.start:.3f},setpts=PTS-STARTPTS[v{i}]")
    parts.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[base]")
    spans = dim_spans(layers)
    last = "base"
    if spans:
        m = len(spans)
        parts.append(f"[base]split={m + 1}[clear]" + "".join(f"[t{j}]" for j in range(m)))
        # the dimmed plate: footage scaled down and back up (blur), luma x0.24, chroma slightly desaturated, then a vignette
        last = "clear"
        for j, (a, b) in enumerate(spans):
            a0, b0 = max(0.0, a - L.DIM_IN_S), b + L.DIM_IN_S
            parts.append(f"[t{j}]trim=start={a0:.3f}:end={b0:.3f},setpts=PTS-STARTPTS+{a0:.3f}/TB,"
                         f"scale=iw/{L.BACKDROP_SHRINK}:ih/{L.BACKDROP_SHRINK},scale={W}:{H}:flags=bicubic,"
                         f"lutyuv=y='val*{L.BACKDROP_BRIGHTNESS}':u='(val-128)*0.8+128':v='(val-128)*0.8+128',vignette=PI/5,"
                         f"format=yuva420p,fade=t=in:st={a0:.3f}:d={L.DIM_IN_S}:alpha=1,fade=t=out:st={b:.3f}:d={L.DIM_IN_S}:alpha=1[dm{j}]")
            parts.append(f"[{last}][dm{j}]overlay=enable='between(t,{a0:.3f},{b0:.3f})':eof_action=pass[o{j}]")
            last = f"o{j}"
    parts.append(f"[{last}][{n}:v]overlay=format=auto,format=yuv420p[out]")
    return ";\n".join(p for p in parts if p)


def _frame_bytes(t: float, layers: Sequence[Layer], blank: bytes) -> Tuple[bytes, int]:
    active = [ly for ly in layers if ly.start <= t < ly.end]
    if not active:
        return blank, 0
    img = L.blank()
    for ly in active:
        fn = cards.CARDS[ly.kind]
        out = fn(t - ly.start, ly.end - ly.start, ly.params)
        if out is not None:
            img = Image.alpha_composite(img, out)
    return img.tobytes(), len(active)


def render(shots: Sequence[Shot], layers: Sequence[Layer], out_path: str, *, crf: int = 20) -> Dict[str, float]:
    """Render the timeline. Returns timing stats {frames, seconds, fps_render, card_frames}."""
    import time

    total = shots[-1].end
    frames = int(round(total * FPS))
    blank = bytes(W * H * 4)
    graph = filter_graph(shots, layers)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write(graph)
        script = fh.name
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for s in shots:
        cmd += ["-ss", f"{s.seek:.3f}", "-t", f"{s.end - s.start + 0.5:.3f}", "-i", s.path]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
            "-filter_complex_script", script, "-map", "[out]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-movflags", "+faststart", "-frames:v", str(frames), out_path]
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    card_frames = 0
    try:
        assert proc.stdin is not None
        for f in range(frames):
            data, n = _frame_bytes(f / FPS, layers, blank)
            card_frames += 1 if n else 0
            proc.stdin.write(data)
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        try: rc = proc.wait(timeout=3600)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=30); raise RuntimeError('ffmpeg timed out after 3600 s')
    finally:
        Path(script).unlink(missing_ok=True)
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed: {err[-800:]}")
    dt = time.time() - t0
    return {"frames": frames, "seconds": dt, "fps_render": frames / dt if dt else 0.0, "card_frames": card_frames}
