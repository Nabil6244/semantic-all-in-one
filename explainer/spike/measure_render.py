"""Read-back helpers for instrumented board clips (frame-number cells, red border) inside a rendered video. Used by the verification scripts.
Read-only: decodes the video with ffmpeg, writes nothing."""
import io
import subprocess
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

FPS = 30


def raw(path, vf, pix, size_bytes):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf, "-f", "rawvideo", "-pix_fmt", pix, "-"], capture_output=True, check=True, timeout=1800)
    return np.frombuffer(p.stdout, dtype=np.uint8).reshape(-1, size_bytes)


def frame_png(path, n):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{n})", "-vframes", "1", "-f", "image2pipe", "-c:v", "png", "-"],
                       capture_output=True, check=True, timeout=1800)
    return Image.open(io.BytesIO(p.stdout)).convert("RGB")


def n_frames(video) -> int:
    return int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "csv=p=0", str(video)],
                              capture_output=True, text=True, timeout=1800).stdout.strip().strip(","))


def board_runs(video, probe: Tuple[int, int] = (1700, 300)) -> Tuple[List[Dict], int]:
    """Runs of pure instrumented-board frames: [{first, last, code_first, code_last, steps, offset (video frame minus clip frame, None if not constant)}]."""
    nb = n_frames(video)
    p_int = raw(video, f"crop=2:2:{probe[0]}:{probe[1]}", "rgb24", 12)[:, :3].astype(int)   # a pixel the clip leaves empty (Milestone 1 content fills the legacy default)
    p_top = raw(video, "crop=2:2:960:22", "rgb24", 12)[:, :3].astype(int)
    code = raw(video, "crop=320:20:0:0,format=gray", "gray", 320 * 20).reshape(-1, 20, 320)
    frames, codes = [], {}
    for i in range(nb):
        cells = code[i][10, 10::20][:16]
        if np.all((cells < 40) | (cells > 215)) and np.abs(p_int[i] - 192).max() <= 8 and p_top[i][0] > 190 and p_top[i][1] < 40:
            frames.append(i)
            codes[i] = int("".join("1" if c > 128 else "0" for c in cells), 2)
    runs, cur = [], []
    for i in frames:
        if cur and (i != cur[-1] + 1 or codes[i] - codes[cur[-1]] not in (0, 1)):    # a repeated code (a held frame) is kept inside the run and counted
            runs.append(cur)
            cur = []
        cur.append(i)
    if cur:
        runs.append(cur)
    out = []
    for r in runs:
        steps = [codes[r[k + 1]] - codes[r[k]] for k in range(len(r) - 1)]
        offs = [i - codes[i] for i in r if codes[i] >= 1] or [r[0] - codes[r[0]]]
        modal = max(set(offs), key=offs.count)
        foc = {}
        for i in r:
            foc.setdefault(codes[i], i)           # the first video frame that shows each clip frame
        holds = [(r[k + 1], codes[r[k + 1]]) for k in range(len(r) - 1) if steps[k] == 0]
        out.append({"first": r[0], "last": r[-1], "frames": len(r), "code_first": codes[r[0]], "code_last": codes[r[-1]], "steps": sorted(set(steps)),
                    "held_frames": sum(1 for x in steps if x == 0), "skipped_frames": sum(1 for x in steps if x > 1),
                    "held_at": [{"video_frame": f, "clip_frame": c} for f, c in holds][:6],
                    "offset": modal if len(set(offs)) == 1 else None, "offset_values": sorted(set(offs))[:4], "frame_of_code": foc})
    return out, nb


def onset_frame(video, bbox, expect: int, nb: int, last_board: int, dev: int = 50, thr: int = 12, window: Tuple[int, int] = (8, 10)) -> Tuple[Optional[int], np.ndarray]:
    """First frame near `expect` whose region (bbox) goes from fewer than `thr` to at least `thr` pixels that differ from the board grey by more than `dev`."""
    x0, y0, x1, y1 = [int(v) for v in bbox]
    x0, y0, x1, y1 = x0 // 2 * 2, y0 // 2 * 2, (x1 + 1) // 2 * 2, (y1 + 1) // 2 * 2
    w, h = max(2, x1 - x0), max(2, y1 - y0)
    reg = raw(video, f"crop={w}:{h}:{x0}:{y0},format=gray", "gray", w * h)
    cnt = (np.abs(reg.astype(int) - 192) > dev).sum(axis=1)
    for i in range(max(1, expect - window[0]), min(last_board, expect + window[1]) + 1):
        if cnt[i] >= thr and cnt[i - 1] < thr:
            return i, cnt
    return None, cnt
