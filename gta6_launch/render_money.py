"""Renders '15 Ways to Get Rich in GTA 6' from gta6_money_scenes.csv with a recorded voiceover.
Run:  python3 gta6_launch/render_money.py [voiceover.mp3]   (no file = free Edge voice)"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from game_launch import plan as P, runner as R  # noqa: E402

VO = sys.argv[1] if len(sys.argv) > 1 else "/Users/muhammadnabil/Downloads/One bank. Ten minute.mp3"
CSV, TRAILERS, WORK = ROOT / "gta6_money_scenes.csv", ROOT / "footage/trailer", ROOT / "work_money"
OUT = ROOT / "out/gta6_15_ways_to_get_rich.mp4"


def log(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


if __name__ == "__main__":
    s = R.prepare(str(CSV), str(TRAILERS), str(WORK), log=log, voiceover=VO)
    log(f"prepared: {s['lines']} lines, {s['shots']} shots, {s['seconds']:.0f} s")
    r = R.render(str(WORK), str(OUT), P.local_files(P.read(str(CSV))), thumb_text="ONE BANK. $140K",
                 short_foot="GTA VI  ·  NOV 19", progress=lambda f, m="": log(f"{f * 100:5.1f}%  {m}"), log=log)
    log(f"DONE {OUT} {r['seconds']:.0f} s, shorts {len(r['shorts'])}, thumbnail {r['thumbnail']}")
