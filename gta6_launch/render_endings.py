"""Renders 'GTA 6 All Endings Explained' from gta6_endings_scenes.csv with the free Edge voice (Andrew), no Shorts.
Run:  python3 gta6_launch/render_endings.py"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from game_launch import plan as P, runner as R  # noqa: E402

CSV, TRAILERS, WORK = ROOT / "gta6_endings_scenes.csv", ROOT / "footage/trailer", ROOT / "work_endings"
OUT = ROOT / "out/gta6_all_endings_explained.mp4"


def log(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


if __name__ == "__main__":
    s = R.prepare(str(CSV), str(TRAILERS), str(WORK), "en-US-AndrewNeural", log=log)
    log(f"prepared: {s['lines']} lines, {s['shots']} shots, {s['seconds']:.0f} s")
    r = R.render(str(WORK), str(OUT), P.local_files(P.read(str(CSV))), shorts=False, thumb_text="2 OF 3 DIE",
                 short_foot="GTA VI", progress=lambda f, m="": log(f"{f * 100:5.1f}%  {m}"), log=log)
    log(f"DONE {OUT} {r['seconds']:.0f} s, thumbnail {r['thumbnail']}")
