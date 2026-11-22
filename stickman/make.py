"""Plain script -> finished stickman video (voice, picture, captions, sound).

python3 -m stickman.make SCRIPT.txt|- OUT.mp4 [--csv rows.csv] [--shorts] [--title "..."] [--voice-file v.mp3] [--edge-voice en-US-AndrewNeural]
                         [--preview] [--workers N] [--look colour_pop|meme] [--host girl] [--no-paint]
The script's first line is the title when --title is not given and the line has no
sentence end. Steps: voice (+word times) -> director -> checker (repairs) -> render ->
mix (voice + calm bed + effects) -> mux. The final plan is saved next to the video.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stickman import runner  # noqa: E402
from stickman.runner import split_title  # noqa: E402,F401  (kept for older callers)


def make(script_text, out, title=None, voice_file=None, edge_voice="en-US-AndrewNeural",
         preview=False, workers=None, log=print, look="ink_paper", csv_path=None, shorts=False, host=None, paint=True):
    out = Path(out)
    p = runner.plan(script_text, csv_path=csv_path, voice_file=voice_file, edge_voice=edge_voice, look=look,
                    shorts=shorts, preview=preview, title=title, log=log, host=host, paint=paint)
    plan_path = runner.save(p["spec"], out.with_suffix(".plan.json"))
    log(f"stickman: {p['beats']} beats over {p['seconds']:.1f} s, plan -> {plan_path.name}")
    runner.render(p["spec"], out, log=log, workers=workers)
    log(f"stickman: done -> {out}")
    return {"video": str(out), "plan": str(plan_path), "notes": p["notes"], "left": p["left"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--title")
    ap.add_argument("--voice-file")
    ap.add_argument("--edge-voice", default="en-US-AndrewNeural")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--workers", type=int)
    ap.add_argument("--look", default=None, help="ink_paper, chalk_dark, colour_pop, retro_tv, night_thriller, meme")
    ap.add_argument("--host", default=None, help="your picture in the corner: a puppet folder name (girl); 'none' = off")
    ap.add_argument("--no-paint", action="store_true", help="Meme look: no Flow painting, drawn rooms where none is painted yet")
    ap.add_argument("--csv", help="a Stickman CSV (its lines are the narration; empty cells are filled by the director)")
    ap.add_argument("--shorts", action="store_true", help="native 9:16 Short (1080x1920)")
    a = ap.parse_args(argv)
    script = Path(a.script).read_text() if a.script != "-" else None
    make(script, a.out, a.title, a.voice_file, a.edge_voice, a.preview, a.workers, look=a.look, csv_path=a.csv, shorts=a.shorts,
         host="" if a.host == "none" else a.host, paint=not a.no_paint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
