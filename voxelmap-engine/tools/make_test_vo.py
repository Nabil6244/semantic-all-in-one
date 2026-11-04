"""Test voiceover for a voxel map timeline: macOS `say` per sentence, placed at the sentence's start in a silent track.

    python3 tools/make_test_vo.py out/timeline.json out/audio/vo.wav out/audio/vo_timing.json [--voice Daniel]

A clip longer than (next start - start - 0.1 s) is sped up with atempo (max 1.15) and reported; if it still does not fit
it is reported as an overlap. Nothing is ever truncated. vo_timing.json holds the ACTUAL placed start/end of the speech.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

SR = 48000
MAX_TEMPO = 1.15
GAP = 0.1
SPEECH_THR = 10 ** (-50 / 20)


def trim_silence(x: np.ndarray, thr: float = SPEECH_THR) -> np.ndarray:
    idx = np.flatnonzero(np.abs(x) > thr)
    return x[idx[0]: idx[-1] + 1] if len(idx) else x[:0]


def plan_placement(starts, durs, total, gap: float = GAP, max_tempo: float = MAX_TEMPO):
    """Per sentence: tempo to apply and whether it still overlaps. durs are natural clip durations (s).
    -> [{start, tempo, new_dur, end, sped_up, overlap}]. The last sentence is bounded by `total` instead of a next start."""
    out = []
    for i, (s, d) in enumerate(zip(starts, durs)):
        limit = (starts[i + 1] - s - gap) if i + 1 < len(starts) else (total - s)
        tempo, sped, over = 1.0, False, False
        if d > limit:
            need = d / max(limit, 1e-6)
            tempo = min(max_tempo, need)
            sped = True
            over = d / tempo > limit + 1e-6
        nd = d / tempo
        out.append({"start": s, "tempo": round(tempo, 4), "new_dur": nd, "end": s + nd, "sped_up": sped, "overlap": over})
    return out


def synth(text: str, voice: str, work: Path, k: int) -> np.ndarray:
    aiff = work / f"s{k}.aiff"
    subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True, timeout=1800)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(aiff), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True, timeout=1800).stdout
    return trim_silence(np.frombuffer(raw, dtype=np.float32))


def atempo(x: np.ndarray, tempo: float) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-af", f"atempo={tempo:.4f}", "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         input=x.astype(np.float32).tobytes(), capture_output=True, check=True, timeout=1800).stdout
    return np.frombuffer(raw, dtype=np.float32)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("timeline"); p.add_argument("vo"); p.add_argument("timing")
    p.add_argument("--voice", default="Daniel")
    a = p.parse_args(argv)
    tl = json.loads(Path(a.timeline).read_text())
    narr = sorted(tl["narration"], key=lambda s: s["start"])
    total = float(tl["duration"])
    with tempfile.TemporaryDirectory() as td:
        clips = [synth(s["text"], a.voice, Path(td), k) for k, s in enumerate(narr)]
    plan = plan_placement([s["start"] for s in narr], [len(c) / SR for c in clips], total)
    track = np.zeros(int(round(total * SR)), np.float32)
    sentences, report = [], {"sped_up": [], "overlaps": [], "past_end": []}
    for k, (s, c, pl) in enumerate(zip(narr, clips, plan)):
        if pl["tempo"] != 1.0:
            c = atempo(c, pl["tempo"])
        i0 = int(round(s["start"] * SR)); i1 = i0 + len(c)
        if i1 > len(track):  # never truncate: grow the track and say so
            track = np.concatenate([track, np.zeros(i1 - len(track), np.float32)])
            report["past_end"].append(k)
        track[i0:i1] += c
        sentences.append({"start": round(i0 / SR, 4), "end": round(i1 / SR, 4), "text": s["text"]})
        if pl["sped_up"]:
            report["sped_up"].append({"i": k, "tempo": pl["tempo"], "natural_s": round(len(clips[k]) / SR, 3)})
        if pl["overlap"]:
            report["overlaps"].append({"i": k, "end": sentences[-1]["end"], "next_start": narr[k + 1]["start"] if k + 1 < len(narr) else None})
    raw = Path(a.vo).with_suffix(".raw.f32")
    raw.write_bytes(track.tobytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", str(raw), "-c:a", "pcm_s16le", a.vo], check=True, timeout=1800)
    raw.unlink()
    Path(a.timing).write_text(json.dumps({"sentences": sentences}, indent=1))
    print(json.dumps({"event": "done", "vo": a.vo, "sentences": len(sentences), **report}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
