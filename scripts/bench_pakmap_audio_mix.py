#!/usr/bin/env python3
"""Benchmark pakMap's mixer (pakmap/audio_mix.py, also used by Hybrid Map and StarMap) on long narration.

Each run is a fresh process, so peak RSS is the mixer's own. For every length it records peak RAM, time, the output's
duration / sample rate / channels, and whether the effects and ambience are really in the file. With --old REV the mixer
from that git revision is run too, and the two outputs are compared sample by sample.

  python3 scripts/bench_pakmap_audio_mix.py --minutes 5 10 30 40 --old 19d5b8e --old-max 30
  python3 scripts/bench_pakmap_audio_mix.py --voiceover ~/voiceover.mp3 --minutes 30   # real speech, looped to length

The sound library is generated tones (test_pakmap_audio_stream._catalog), never the user's library.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHILD = r"""
import importlib.util, json, resource, sys, time
from pathlib import Path
root, work, minutes, which = Path(sys.argv[1]), Path(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
sys.path.insert(0, str(root))
import pakmap
if which == "new":
    from pakmap import audio_mix as am
else:
    spec = importlib.util.spec_from_file_location("pakmap._audio_mix_old", which, submodule_search_locations=None)
    am = importlib.util.module_from_spec(spec); am.__package__ = "pakmap"; sys.modules[spec.name] = am; spec.loader.exec_module(am)
import test_pakmap_audio_stream as t
cat = t._catalog(work / "lib")
plan = t._plan(cat, minutes * 60, cues_every=7.0, majors_every=40.0)
plan = am.resolve_assets(plan, cat)
t0 = time.time()
res = am.mix_pakmap_audio(plan, work / "vo.wav", work / f"out_{Path(which).stem}.wav", duration=minutes * 60)
secs = time.time() - t0
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
print(json.dumps({"rss_gb": rss / 1e9, "seconds": secs, "cues": len(plan.cues), "beds": len(plan.beds), "scale": res.bus_scale, "path": str(res.path)}))
"""


def probe(path: Path) -> dict:
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels,codec_name:format=duration", "-of", "json", str(path)],
                                     capture_output=True, text=True, check=True).stdout)
    s = info["streams"][0]
    return {"duration": float(info["format"]["duration"]), "sample_rate": int(s["sample_rate"]), "channels": int(s["channels"]), "codec": s["codec_name"]}


def window(path: Path, start: float, dur: float):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", "48000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)


def compare(a: Path, b: Path, total: float, step: float = 120.0) -> float:
    """The largest sample difference between two mixes, read 60 s at a time (never the whole files in memory)."""
    worst, t = 0.0, 0.0
    while t < total:
        x, y = window(a, t, 60.0), window(b, t, 60.0)
        n = min(len(x), len(y))
        if n:
            worst = max(worst, float(abs(x[:n] - y[:n]).max()))
        t += step / 2
    return worst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, nargs="+", default=[5, 10, 30, 40])
    ap.add_argument("--old", help="git revision whose pakmap/audio_mix.py is run as well, for comparison")
    ap.add_argument("--old-max", type=float, default=30.0, help="skip the old mixer above this many minutes (it needs ~0.22 GB/min)")
    ap.add_argument("--voiceover", help="a real narration, looped to each length (default: a speech-like test tone)")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        old_file = None
        if args.old:
            old_file = tmp / "audio_mix_old.py"
            old_file.write_text(subprocess.run(["git", "show", f"{args.old}:pakmap/audio_mix.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout)
        child = tmp / "child.py"
        child.write_text(CHILD)
        rows = []
        for minutes in args.minutes:
            work = tmp / f"m{minutes:g}"
            work.mkdir()
            secs = minutes * 60
            if args.voiceover:
                src = ["-stream_loop", "-1", "-i", str(Path(args.voiceover).expanduser())]
            else:
                src = ["-f", "lavfi", "-i", f"sine=f=190:d={secs}"]
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", *src, "-t", str(secs), "-af", "volume=0.6" if args.voiceover else "volume=0.25",
                            "-ar", "44100", "-ac", "2", str(work / "vo.wav")], check=True)
            for which in (["new"] + ([str(old_file)] if old_file and minutes <= args.old_max else [])):
                run = subprocess.run([sys.executable, str(child), str(ROOT), str(work), str(minutes), which], capture_output=True, text=True)
                if run.returncode != 0:
                    rows.append({"minutes": minutes, "mixer": "new" if which == "new" else "old", "error": run.stderr.strip().splitlines()[-1:]})
                    print(json.dumps(rows[-1]), flush=True)
                    continue
                r = json.loads(run.stdout.strip().splitlines()[-1])
                out = Path(r.pop("path"))
                r.update(probe(out))
                vo = window(work / "vo.wav", 60.7, 0.5)
                mix = window(out, 60.7, 0.5)
                r["bed_present"] = bool(float(abs(mix[:len(vo)] - vo[:len(mix)]).max()) > 1e-3)
                r.update(minutes=minutes, mixer="new" if which == "new" else "old")
                rows.append(r)
                print(json.dumps(r), flush=True)
            if old_file and minutes <= args.old_max and (work / "out_audio_mix_old.wav").is_file():
                d = compare(work / "out_new.wav", work / "out_audio_mix_old.wav", secs)
                rows.append({"minutes": minutes, "max_sample_difference_old_vs_new": d})
                print(json.dumps(rows[-1]), flush=True)
            for f in work.glob("*.wav"):
                f.unlink()
        print("\n| minutes | mixer | peak RAM | time | output | effects/ambience in file |")
        print("|---|---|---|---|---|---|")
        for r in rows:
            if "rss_gb" in r:
                print(f"| {r['minutes']:g} | {r['mixer']} | {r['rss_gb']:.2f} GB | {r['seconds']:.0f} s | {r['duration']:.1f} s, {r['sample_rate']} Hz, {r['channels']} ch, {r['codec']} | {'yes' if r['bed_present'] else 'NO'} |")
            elif "error" in r:
                print(f"| {r['minutes']:g} | {r['mixer']} | failed: {r['error']} | | | |")
        for r in rows:
            if "max_sample_difference_old_vs_new" in r:
                print(f"{r['minutes']:g} min: largest sample difference old vs new = {r['max_sample_difference_old_vs_new']:.2e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
