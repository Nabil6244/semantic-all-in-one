"""Senior Trivia: plan (CSV -> pictures, host clips, voice, timeline) then render (frames + mix -> mp4).

  python -m senior_trivia.runner plan  show.csv  out/senior_trivia/show.json [--no-flow] [--voice en-US-AndrewNeural]
  python -m senior_trivia.runner render out/senior_trivia/show.json out/senior_trivia/show.mp4
A supplied CSV makes no Gemini calls. Nothing renders at plan time.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from prepper_host import flow

from senior_trivia import csvplan, pictures, render as _render, timeline
from senior_trivia import host as st_host

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "senior_trivia"


class Stopped(Exception):
    pass


def plan(csv_path, voice=timeline.DEFAULT_VOICE, use_flow=True, host_clips=True, title=None, preview=False,
         log=print, cancel=None):
    rows, problems = csvplan.read(csv_path)
    if not rows:
        raise ValueError("; ".join(problems) or "the CSV has no rows")
    for p in problems:
        log(f"senior trivia: CSV note: {p}")
    thumb = next((r for r in rows if r["type"] == "thumbnail"), None)
    rows = [r for r in rows if r["type"] != "thumbnail"]
    intro = next((r for r in rows if r["type"] == "intro"), None)
    title = (title or (intro or {}).get("question") or (" ".join(s.strip() for s in thumb["question"].split("|")) if thumb else "")
             or Path(str(csv_path)).stem.replace("_", " ").title())
    made = pictures.make(rows + ([thumb] if thumb else []), use_flow=use_flow, log=log, cancel=cancel)
    pics = {i: pictures.picture_keys(r) for i, r in enumerate(rows)}
    meta = st_host.load()
    clips = pictures.host_clips(rows, meta, use_flow=use_flow and host_clips, log=log, cancel=cancel)
    sc, voiced = timeline.voice_all(rows, voice=voice, skip_host=set(clips), log=log)
    size = (1280, 720) if preview else (1920, 1080)
    spec = timeline.build(rows, voiced, sc, clips=clips, pics=pics, size=size, title=title)
    spec["host"] = {k: meta.get(k) for k in ("name", "tagline")}
    spec["pictures"] = {k: {"prompt": p} for k, p in pictures.jobs(rows).items()}   # visual_bridge reads {key: {"prompt"}}
    spec["assets"] = {"pictures": made}
    spec["problems"] = problems
    if thumb:
        spec["thumbnail"] = {"pic": pictures.picture_keys(thumb)[0],
                             "lines": [s.strip() for s in thumb["question"].split("|") if s.strip()]}
    log(f"senior trivia: planned {len(spec['segs'])} parts, {spec['duration'] / 60:.1f} min, "
        f"{len(clips)} host clip(s), {len(made)}/{len(spec['pictures'])} pictures")
    return spec


def save(spec, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def refresh_assets(spec):
    """Pictures made after the plan (a retry, another run) are picked up at render."""
    pics = spec.setdefault("assets", {}).setdefault("pictures", {})
    for k in spec.get("pictures", {}):
        if k not in pics and flow.have(k):
            pics[k] = flow.have(k)
    return spec


def render(spec, out, progress=None, cancel=None, log=print, workers=None):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    say = progress or (lambda f, m="": None)
    spec = refresh_assets(spec)
    with tempfile.TemporaryDirectory() as wd:
        silent, wav = Path(wd) / "picture.mp4", Path(wd) / "mix.wav"
        _render.render_picture(spec, spec["assets"], silent, workers=workers, cancel=cancel,
                               progress=lambda f, m: say(0.02 + 0.9 * f, m))
        if cancel and cancel():
            raise Stopped("Stopped.")
        say(0.93, "mixing the sound")
        _render.mix(spec, wav)
        say(0.97, "writing the video")
        part = out.with_name(out.stem + ".part.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(part)],
                       check=True, timeout=3600)
        part.replace(out)
    say(1.0, "done")
    log(f"senior trivia: wrote {out} ({spec['duration'] / 60:.1f} min)")
    return {"video": str(out), "seconds": spec["duration"]}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="senior_trivia")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("csv")
    p.add_argument("spec")
    p.add_argument("--voice", default=timeline.DEFAULT_VOICE)
    p.add_argument("--no-flow", action="store_true")
    p.add_argument("--no-host-clips", action="store_true")
    p.add_argument("--preview", action="store_true")
    r = sub.add_parser("render")
    r.add_argument("spec")
    r.add_argument("out")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)   # the log file shows progress as it happens
    if a.cmd == "plan":
        spec = plan(a.csv, voice=a.voice, use_flow=not a.no_flow, host_clips=not a.no_host_clips, preview=a.preview)
        print(save(spec, a.spec))
    else:
        render(load(a.spec), a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
