"""Voice-over for review films: align the script's lines to the narrator's words, make subtitle chunks from real word times, and mix the
voice (with the music far below it) for the render.

`words` are (text, start, end) tuples, as the app's Whisper helper returns them. No Whisper is run here.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

CHUNK_WORDS = 7
MUSIC_UNDER_VOICE = 0.14      # music gain under a voice-over (about -17 dB)
SEARCH = 8                    # how far (in words) the alignment looks ahead for a line's first word


def norm(w: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(w).lower())


def tokens(text: str) -> List[str]:
    return [t for t in (norm(x) for x in str(text).split()) if t]


def _wtimes(words: Sequence[Any]) -> List[Tuple[str, float, float]]:
    out = []
    for w in words:
        if isinstance(w, dict):
            out.append((norm(w.get("text") or w.get("word")), float(w["start"]), float(w["end"])))
        else:
            out.append((norm(w[0]), float(w[1]), float(w[2])))
    return [x for x in out if x[0]]


def align_lines(lines: Sequence[str], words: Sequence[Any], duration: float) -> dict:
    """Each line's (start, end) in the voice-over, and each line's word index range, by walking the narrator's words in order.
    Falls back to an even split by word count when the words do not follow the script ('ok' is then False)."""
    W = _wtimes(words)
    toks = [tokens(t) for t in lines]
    total = sum(len(t) for t in toks) or 1
    spans: List[Tuple[float, float]] = []
    ranges: List[Tuple[int, int]] = []
    p, hits = 0, 0
    for t in toks:
        if not t or p >= len(W):
            spans.append((W[min(p, len(W) - 1)][1] if W else 0.0,) * 2)
            ranges.append((min(p, max(0, len(W) - 1)),) * 2)
            continue
        start = p
        for k in range(p, min(len(W), p + SEARCH)):
            if W[k][0] == t[0]:
                start, hits = k, hits + 1
                break
        end = min(len(W) - 1, start + len(t) - 1)
        for k in range(max(start, end - 3), min(len(W), end + 4)):
            if W[k][0] == t[-1]:
                end = k
                break
        spans.append((W[start][1], W[end][2]))
        ranges.append((start, end))
        p = end + 1
    ok = bool(W) and hits >= 0.6 * len([t for t in toks if t]) and p >= 0.6 * len(W)
    if not ok:
        t0 = W[0][1] if W else 0.0
        span = max(0.1, float(duration) - t0)
        spans, ranges, acc = [], [], 0
        for t in toks:
            a, b = t0 + span * acc / total, t0 + span * (acc + len(t)) / total
            spans.append((a, b))
            ranges.append((0, 0))
            acc += len(t)
    return {"spans": spans, "ranges": ranges, "ok": ok, "duration": float(duration)}


def chunks(text: str, span: Tuple[float, float], words: Sequence[Any], rng: Tuple[int, int], ok: bool) -> List[dict]:
    """Subtitle chunks of a line: the script's own words, timed from the narrator's words when they matched, else spread over the span."""
    parts = str(text).split()
    if not parts:
        return []
    n = max(1, round(len(parts) / CHUNK_WORDS))
    size = -(-len(parts) // n)
    groups = [parts[i:i + size] for i in range(0, len(parts), size)]
    W = _wtimes(words) if ok else []
    out, k = [], 0
    for g in groups:
        if W and rng[1] > rng[0]:
            i0 = min(rng[1], rng[0] + k)
            i1 = min(rng[1], rng[0] + k + len(g) - 1)
            a, b = W[i0][1], W[i1][2]
        else:
            per = (span[1] - span[0]) / len(parts)
            a, b = span[0] + k * per, span[0] + (k + len(g)) * per
        out.append({"start": round(a, 3), "end": round(max(b, a + 0.3), 3), "text": " ".join(g)})
        k += len(g)
    return out


def audio_seconds(path, ffprobe: Optional[str] = None) -> float:
    """Length of an audio file (ffprobe); 0.0 when it cannot be read."""
    if ffprobe is None:
        try:
            from map_scene.render import _ffmpeg

            ffprobe = str(Path(_ffmpeg()).with_name("ffprobe" + (".exe" if str(_ffmpeg()).endswith(".exe") else "")))
        except Exception:  # noqa: BLE001
            ffprobe = "ffprobe"
    try:
        r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except Exception:  # noqa: BLE001
        return 0.0


def mix_voiceover(voice: Path, music: Optional[Path], out_wav: Path, duration: float, ffmpeg: str) -> Path:
    """The voice-over at full level; music (when given) far below it, faded out at the end; cut to the film's length."""
    cmd = [ffmpeg, "-y", "-v", "error", "-nostdin", "-i", str(voice)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        fade = max(0.5, min(3.0, duration * 0.1))
        fl = (f"[1:a]volume={MUSIC_UNDER_VOICE},afade=t=out:st={max(0.0, duration - fade):.3f}:d={fade:.3f}[m];"
              f"[0:a][m]amix=inputs=2:duration=first:normalize=0[o]")
        cmd += ["-filter_complex", fl, "-map", "[o]"]
    else:
        cmd += ["-map", "0:a"]
    cmd += ["-t", f"{duration:.3f}", "-ac", "2", "-ar", "48000", str(out_wav)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("mixing the voice-over took too long") from exc
    if r.returncode != 0 or not Path(out_wav).is_file():
        raise RuntimeError(f"could not mix the voice-over: {r.stderr[-300:]}")
    return Path(out_wav)
