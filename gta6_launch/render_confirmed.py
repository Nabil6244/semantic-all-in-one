"""Renders 'Everything Confirmed About GTA 6' from gta6_confirmed_scenes.csv with the recorded voiceover.
Run:  python3 gta6_launch/render_confirmed.py [path/to/voiceover.mp3]"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from game_launch import plan as P, runner as R  # noqa: E402

VO = sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / "Downloads/Grand Theft Auto Six.mp3")
CSV, TRAILERS, WORK = ROOT / "gta6_confirmed_scenes.csv", ROOT / "footage/trailer", ROOT / "work_confirmed"
OUT = ROOT / "out/gta6_everything_confirmed.mp4"


def log(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def prog(f, m=""):
    log(f"{f * 100:5.1f}%  {m}")


if __name__ == "__main__":
    s = R.prepare(str(CSV), str(TRAILERS), str(WORK), log=log, voiceover=VO)
    log(f"prepared: {s['lines']} lines, {s['shots']} shots, {s['seconds']:.0f} s; warnings {len(s['warnings'])}")
    found = P.local_files(P.read(str(CSV)))
    r = R.render(str(WORK), str(OUT), found, thumb_text="EVERYTHING CONFIRMED", short_foot="GTA VI  ·  NOV 19",
                 progress=prog, log=log)
    log(f"DONE {OUT} {r['seconds']:.0f} s, shorts {len(r['shorts'])}, thumbnail {r['thumbnail']}")
