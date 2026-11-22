"""Renders 'What If GTA 6 Launch Night Blacked Out Your City' from gta6_blackout_scenes.csv with a recorded voiceover.
Run:  python3 gta6_launch/render_blackout.py [voiceover.mp3]   (no file = free Edge voice)"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from game_launch import plan as P, runner as R  # noqa: E402

VO = sys.argv[1] if len(sys.argv) > 1 else "/Users/muhammadnabil/Downloads/Midnight, November n.mp3"
CSV, TRAILERS, WORK = ROOT / "gta6_blackout_scenes.csv", ROOT / "footage/trailer", ROOT / "work_blackout"
OUT = ROOT / "out/gta6_launch_night_blackout.mp4"


def log(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


if __name__ == "__main__":
    s = R.prepare(str(CSV), str(TRAILERS), str(WORK), log=log, voiceover=VO)
    log(f"prepared: {s['lines']} lines, {s['shots']} shots, {s['seconds']:.0f} s")
    r = R.render(str(WORK), str(OUT), P.local_files(P.read(str(CSV))), thumb_text="FROZEN AT 80%",
                 short_foot="GTA VI  ·  NOV 19", progress=lambda f, m="": log(f"{f * 100:5.1f}%  {m}"), log=log)
    log(f"DONE {OUT} {r['seconds']:.0f} s, shorts {len(r['shorts'])}, thumbnail {r['thumbnail']}")
