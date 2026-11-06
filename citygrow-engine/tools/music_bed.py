#!/usr/bin/env python3
"""Music bed for a City Timelapse film (music only, like the reference format): one bundled track, looped with a
crossfade when the film is longer, faded in and out, levelled to -14 LUFS (two-pass loudnorm, true peak <= -1.5 dBTP).

    python3 tools/music_bed.py <seconds> out.wav [--track ascending_the_vale] [--voice vo.wav]

Tracks: assets/music (Kevin MacLeod, incompetech.com, CC BY 4.0). The credit line is printed as JSON ({"event": "credit"}).
With --voice the voice is laid over the music, which ducks under it (sidechain compressor), then the whole mix is levelled.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MUSIC = ROOT / "assets" / "music"
TITLES = {"ascending_the_vale": "Ascending the Vale", "echoes_of_time_v2": "Echoes of Time v2", "despair_and_triumph": "Despair and Triumph",
          "lost_frontier": "Lost Frontier", "long_note_four": "Long Note Four", "dark_fog": "Dark Fog", "interloper": "Interloper", "stormfront": "Stormfront"}
DEFAULT = "ascending_the_vale"
TARGET_I, TARGET_TP = -14.0, -1.5


def credit(stem: str) -> str:
    return (f'Music: "{TITLES.get(stem, stem)}" by Kevin MacLeod (incompetech.com), licensed under Creative Commons: By Attribution 4.0 '
            f"(http://creativecommons.org/licenses/by/4.0/)")


def ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def duration_of(path: Path) -> float:
    out = subprocess.run([ffmpeg(), "-i", str(path)], capture_output=True, text=True, timeout=1800).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def bed_filter(n_copies: int, track_len: float, seconds: float, xfade: float = 6.0, voice: bool = False) -> str:
    """ffmpeg filter graph: n copies joined with crossfades, cut to length, faded; [v] ducks it when a voice is given."""
    parts, last = [], "[0:a]"
    for k in range(1, n_copies):
        nxt = f"[x{k}]"
        parts.append(f"{last}[{k}:a]acrossfade=d={xfade}:c1=tri:c2=tri{nxt}")
        last = nxt
    fade_out = max(0.0, seconds - 3.5)
    parts.append(f"{last}atrim=0:{seconds:.3f},asetpts=N/SR/TB,afade=t=in:d=2.0,afade=t=out:st={fade_out:.3f}:d=3.5[m]")
    if voice:
        v = n_copies
        parts.append(f"[{v}:a]aresample=48000,apad,atrim=0:{seconds:.3f},asplit=2[vo][sc]")
        parts.append("[m][sc]sidechaincompress=threshold=0.04:ratio=8:attack=40:release=600[md]")
        parts.append("[md][vo]amix=inputs=2:normalize=0[out]")
    else:
        parts.append("[m]anull[out]")
    return ";".join(parts)


def make(seconds: float, out: Path, track: str = DEFAULT, voice: str | None = None) -> dict:
    src = MUSIC / f"{track}.opus"
    if not src.is_file():
        raise FileNotFoundError(f"music track missing: {src}")
    tl = duration_of(src) or 240.0
    n = 1
    while n * tl - (n - 1) * 6.0 < seconds:
        n += 1
    inputs = sum([["-i", str(src)] for _ in range(n)], [])
    if voice:
        inputs += ["-i", voice]
    graph = bed_filter(n, tl, seconds, voice=bool(voice))
    tmp = out.with_suffix(".pre.wav")
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[out]", "-ar", "48000", "-ac", "2", str(tmp)], check=True, timeout=1800)
    # loudnorm pass 1 (measure) and pass 2 (apply, linear)
    meas = subprocess.run([ffmpeg(), "-i", str(tmp), "-af", f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA=11:print_format=json", "-f", "null", "-"],
                          capture_output=True, text=True, timeout=1800).stderr
    j = json.loads(meas[meas.rindex("{"):meas.rindex("}") + 1])
    af = (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}"
          f":measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(tmp), "-af", af, "-ar", "48000", str(out)], check=True, timeout=1800)
    tmp.unlink(missing_ok=True)
    return {"file": str(out), "seconds": seconds, "track": track, "copies": n, "credit": credit(track)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("seconds", type=float)
    p.add_argument("out")
    p.add_argument("--track", default=DEFAULT)
    p.add_argument("--voice", default=None)
    a = p.parse_args(argv)
    r = make(a.seconds, Path(a.out), a.track, a.voice)
    print(json.dumps({"event": "credit", "text": r["credit"]}))
    print(json.dumps({"event": "done", **r}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
