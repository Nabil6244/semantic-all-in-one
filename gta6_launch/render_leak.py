"""Renders 'GTA 6 on PC in a Week? 5 Reasons to Doubt It' (Vice Ranked) from gta6_leak_scenes.csv with the recorded voiceover.
Run:  python3 gta6_launch/render_leak.py [voiceover.mp3]"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from game_launch import plan as P, runner as R  # noqa: E402

VO = sys.argv[1] if len(sys.argv) > 1 else "/Users/muhammadnabil/Downloads/Somebody says GTA 6 .mp3"
CSV, TRAILERS, WORK = ROOT / "gta6_leak_scenes.csv", ROOT / "footage/trailer", ROOT / "work_leak"
OUT = ROOT / "out/gta6_pc_in_a_week_5_reasons.mp4"


def log(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


if __name__ == "__main__":
    s = R.prepare(str(CSV), str(TRAILERS), str(WORK), log=log, voiceover=VO)
    log(f"prepared: {s['lines']} lines, {s['shots']} shots, {s['seconds']:.0f} s")
    r = R.render(str(WORK), str(OUT), P.local_files(P.read(str(CSV))), thumb_text="PC IN A WEEK?",
                 short_foot="GTA VI  ·  NOV 23", progress=lambda f, m="": log(f"{f * 100:5.1f}%  {m}"), log=log)
    log(f"DONE {OUT} {r['seconds']:.0f} s, shorts {len(r['shorts'])}, thumbnail {r['thumbnail']}")
