"""War Documentary: visual QA of the FINISHED video (docs/war/FOOTAGE_DIRECTOR_PLAN.md, problems 11 and 12).

Reads the rendered mp4 itself (ffmpeg decode, numpy), not the plan, and reports with exact timestamps:

  bare_plate    stretches where the neutral backdrop (state/war_backdrop_v3.mp4, the grey-blue grid) is all the viewer sees: less than
                BARE_MAX of the frame differs from the best-matching backdrop frame
  sparse_plate  stretches where graphics cover less than COVER_MIN of the grid (thin map outlines, one small card): the grid dominates
  blank         stretches of black or flat frames (luma spread under BLANK_STD), e.g. a clip that ran out, a failed piece
  shots         every shot (hard-cut detection) with its kind (footage / graphic / plate / blank) and length; footage shots under
                SHORT_S are listed as short shots (a deliberate montage cut is excluded only when the caller passes its window)

Nothing here changes a video. A stretch shorter than MIN_EVENT_S is not reported (a single odd frame at a cut). Offline, no models.

    python -m cinematic_explainer.war.render_qa <final.mp4> [--backdrop <war_backdrop_v3.mp4>] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

QW, QH = 160, 90             # analysis size (16:9)
FPS = 10.0                   # frames analysed per second
COVER_MIN = 0.30             # a frame where less than this share differs from the backdrop shows mostly grid: "sparse" (thin map lines, a small card)
BARE_MAX = 0.05              # ... and less than this: nothing at all on the grid, a "bare" plate
PLATE_TOL = 18               # per-pixel difference (0-255, RGB mean) still counted as "backdrop"
BLANK_STD = 6.0              # a frame whose luma spread is below this is black / flat
CUT_DIFF = 28.0              # mean absolute luma change between two analysed frames that marks a hard cut ...
CUT_SHARE = 0.45             # ... over at least this share of the frame (a card popping in over a corner is not a cut)
SHORT_S = 3.0                # footage shot shorter than this is a short shot (target 3-6 s)
FLASH_S = 1.5                # ... and shorter than this a flash (the "one-second clip")
MIN_EVENT_S = 0.3            # stretches shorter than this are not reported
GRAPHIC_FLAT = 0.55          # share of pixels in the 8 most common coarse colours above which a frame is a drawn graphic, not footage


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def decode(path: str, fps: float = FPS, w: int = QW, h: int = QH) -> np.ndarray:
    """(n, h, w, 3) uint8 frames at `fps`."""
    cmd = [_ffmpeg(), "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={w}:{h}:flags=area,format=rgb24", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True, timeout=1800).stdout      # a decode that hangs raises like a failed one (subprocess.TimeoutExpired)
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)


def _luma(f: np.ndarray) -> np.ndarray:
    return f[..., 0] * 0.299 + f[..., 1] * 0.587 + f[..., 2] * 0.114


def plate_cover(frames: np.ndarray, plate: Optional[np.ndarray]) -> np.ndarray:
    """Per frame: the share of pixels that differ from the best-matching backdrop frame (1.0 when there is no backdrop to compare with)."""
    if plate is None or not len(plate):
        return np.ones(len(frames))
    p = plate.astype(np.int16)
    out = np.empty(len(frames))
    for i, f in enumerate(frames.astype(np.int16)):
        d = np.abs(p - f[None]).mean(axis=3)                 # (k, h, w)
        out[i] = float((d > PLATE_TOL).mean(axis=(1, 2)).min())
    return out


def flatness(frames: np.ndarray) -> np.ndarray:
    """Share of pixels in the 8 most common coarse colours (drawn graphics are a few flat colours; footage spreads)."""
    q = (frames >> 5).astype(np.int32)
    keys = (q[..., 0] << 6) | (q[..., 1] << 3) | q[..., 2]
    out = np.empty(len(frames))
    for i, k in enumerate(keys.reshape(len(frames), -1)):
        counts = np.bincount(k, minlength=512)
        out[i] = float(np.sort(counts)[-8:].sum()) / k.size
    return out


def cuts(frames: np.ndarray) -> List[int]:
    """Indexes where a new shot starts (hard cuts)."""
    if len(frames) < 2:
        return []
    y = _luma(frames.astype(np.float32))
    d = np.abs(np.diff(y, axis=0))
    big = (d > CUT_DIFF).mean(axis=(1, 2))
    return [i + 1 for i, s in enumerate(big) if s >= CUT_SHARE]


def _runs(mask: Sequence[bool], fps: float) -> List[Tuple[float, float]]:
    out, start = [], None
    for i, m in enumerate(list(mask) + [False]):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if (i - start) / fps >= MIN_EVENT_S:
                out.append((round(start / fps, 2), round(i / fps, 2)))
            start = None
    return out


def _ts(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:05.2f}"


def analyse(frames: np.ndarray, plate: Optional[np.ndarray] = None, fps: float = FPS,
            montage: Sequence[Tuple[float, float]] = ()) -> Dict[str, Any]:
    n = len(frames)
    total = n / fps if fps else 0.0
    std = _luma(frames.astype(np.float32)).reshape(n, -1).std(axis=1) if n else np.zeros(0)
    blank = std < BLANK_STD
    cover = plate_cover(frames, plate)
    bare = (cover < BARE_MAX) & ~blank
    sparse = (cover < COVER_MIN) & ~bare & ~blank
    flat = flatness(frames) if n else np.zeros(0)
    starts = [0] + cuts(frames) + [n]
    shots = []
    for a, b in zip(starts[:-1], starts[1:]):
        if b <= a:
            continue
        seg = slice(a, b)
        if blank[seg].mean() > 0.5:
            kind = "blank"
        elif (bare[seg] | sparse[seg]).mean() > 0.5:
            kind = "plate"
        elif flat[seg].mean() > GRAPHIC_FLAT or cover[seg].mean() < 0.6:
            kind = "graphic"
        else:
            kind = "footage"
        t0, t1 = a / fps, b / fps
        shots.append({"start": round(t0, 2), "end": round(t1, 2), "seconds": round(t1 - t0, 2), "kind": kind})
    in_montage = lambda s: any(m0 - 0.05 <= s["start"] and s["end"] <= m1 + 0.05 for m0, m1 in montage)  # noqa: E731
    short = [dict(s, montage=in_montage(s)) for s in shots if s["kind"] == "footage" and s["seconds"] < SHORT_S]
    bare_runs = _runs(bare, fps)
    sparse_runs = _runs(sparse, fps)
    blank_runs = _runs(blank, fps)
    return {
        "seconds": round(total, 2),
        "bare_plate": [{"start": a, "end": b, "seconds": round(b - a, 2), "reason": "backdrop uncovered"} for a, b in bare_runs],
        "bare_plate_s": round(sum(b - a for a, b in bare_runs), 2),
        "sparse_plate": [{"start": a, "end": b, "seconds": round(b - a, 2), "reason": "graphics cover under 30% of the grid"} for a, b in sparse_runs],
        "sparse_plate_s": round(sum(b - a for a, b in sparse_runs), 2),
        "blank": [{"start": a, "end": b, "seconds": round(b - a, 2), "reason": "black or flat frames"} for a, b in blank_runs],
        "blank_s": round(sum(b - a for a, b in blank_runs), 2),
        "shots": shots,
        "short_shots": [s for s in short if not s["montage"]],
        "flash_shots": [s for s in short if not s["montage"] and s["seconds"] < FLASH_S],
        "montage_cuts": [s for s in short if s["montage"]],
    }


def check(video: str, backdrop: Optional[str] = None, montage: Sequence[Tuple[float, float]] = ()) -> Dict[str, Any]:
    frames = decode(video)
    plate = decode(backdrop, fps=2.0) if backdrop and Path(backdrop).is_file() else None
    out = analyse(frames, plate, FPS, montage)
    out["video"] = str(video)
    out["backdrop"] = str(backdrop or "")
    return out


def text(r: Dict[str, Any]) -> str:
    lines = [f"War render QA: {Path(r.get('video') or '').name} ({_ts(r['seconds'])})",
             f"  bare backdrop  {r['bare_plate_s']:.1f} s in {len(r['bare_plate'])} stretch(es)",
             f"  sparse grid    {r['sparse_plate_s']:.1f} s in {len(r['sparse_plate'])} stretch(es)",
             f"  blank frames   {r['blank_s']:.1f} s in {len(r['blank'])} stretch(es)",
             f"  shots          {len(r['shots'])}; footage under {SHORT_S:g} s: {len(r['short_shots'])}; under {FLASH_S:g} s: {len(r['flash_shots'])}"
             f"; montage cuts excluded: {len(r['montage_cuts'])}"]
    for e in r["bare_plate"]:
        lines.append(f"  BARE  {_ts(e['start'])}-{_ts(e['end'])} ({e['seconds']:.1f} s) {e['reason']}")
    for e in r["sparse_plate"]:
        lines.append(f"  GRID  {_ts(e['start'])}-{_ts(e['end'])} ({e['seconds']:.1f} s) {e['reason']}")
    for e in r["blank"]:
        lines.append(f"  BLANK {_ts(e['start'])}-{_ts(e['end'])} ({e['seconds']:.1f} s) {e['reason']}")
    for s in r["short_shots"]:
        lines.append(f"  SHORT {_ts(s['start'])}-{_ts(s['end'])} ({s['seconds']:.1f} s) footage shot")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="War render QA: bare backdrop, blank frames and short shots in a finished video")
    ap.add_argument("video")
    ap.add_argument("--backdrop")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    bd = a.backdrop
    if not bd:
        guess = Path(a.video).resolve().parent.parent / "state" / "war_backdrop_v3.mp4"
        bd = str(guess) if guess.is_file() else None
    r = check(a.video, bd)
    print(text(r))
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
