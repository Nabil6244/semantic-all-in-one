"""python -m weather <command> — Weather without the app (phase 1A), for testing a project end to end.

    fetch   --project DIR --contact EMAIL_OR_URL      fetch the data the layers need and write DIR/resolved.json
    check   --project DIR [--voiceover F] [--words W]  read beats.csv + weather_layers.csv + resolved.json; report problems
    render  --project DIR --voiceover F --out FILE [--words W] [--whisper MODEL] [--no-sound] [--pexels-key K] [--style S]
    prompt                                             print the Weather Forecast CSV prompt

--words is a JSON list of [word, start, end] (the narration's words); without it, render transcribes the voiceover with
faster-whisper (the app's own transcriber, video_generator.transcribe_audio)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _words(args) -> list:
    if args.words:
        return [(str(w), float(s), float(e)) for w, s, e in json.loads(Path(args.words).read_text(encoding="utf-8"))]
    if getattr(args, "voiceover", None):
        import video_generator as vg

        return [(str(w), float(s), float(e)) for w, s, e in vg.transcribe_audio(str(args.voiceover), args.whisper)]
    return []


def _project_style(project) -> str:
    """The editing style saved in the project's weather.json (the app's Weather card writes it), else classic."""
    try:
        return str(json.loads((project.root / "weather.json").read_text(encoding="utf-8")).get("edit_style") or "classic")
    except (OSError, ValueError):
        return "classic"


def main(argv=None) -> int:
    from .generate import WeatherProject

    ap = argparse.ArgumentParser(prog="python -m weather", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--project", required=True)
    f.add_argument("--contact", default="", help="your email or website, sent to the NWS as it asks (only needed for NWS rows)")
    c = sub.add_parser("check")
    c.add_argument("--project", required=True)
    c.add_argument("--voiceover")
    c.add_argument("--words")
    c.add_argument("--whisper", default="small")
    r = sub.add_parser("render")
    r.add_argument("--project", required=True)
    r.add_argument("--voiceover", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--words")
    r.add_argument("--whisper", default="small")
    r.add_argument("--no-sound", action="store_true", help="narration only (no sound design)")
    r.add_argument("--pexels-key", default=None, help="for stock footage (default: the PEXELS_API_KEY environment variable)")
    r.add_argument("--style", default=None, choices=["classic", "teamplate"],
                   help="editing style: classic (Weather) or teamplate (Weather Teamplate); default: the project's weather.json, else classic")
    pr = sub.add_parser("prompt")
    pr.add_argument("--style", default="classic", choices=["classic", "teamplate"], help="teamplate adds Weather Teamplate's footage-first rules")
    args = ap.parse_args(argv)

    if args.cmd == "prompt":
        sys.stdout.write((Path(__file__).resolve().parent / "prompts" / "forecast_csv_prompt.txt").read_text(encoding="utf-8"))
        if args.style == "teamplate":
            sys.stdout.write("\n" + (Path(__file__).resolve().parent / "prompts" / "teamplate_csv_addendum.txt").read_text(encoding="utf-8"))
        return 0
    project = WeatherProject(Path(args.project).resolve())
    if args.cmd == "fetch":
        from .generate import fetch

        snap = fetch(project, args.contact)
        print(f"wrote {project.resolved_json}")
        for k, v in snap.forecasts.items():
            print(f"  forecast {k}: issued {v['issued']} ({len(v['days'])} days)")
        for k, v in snap.observations.items():
            print(f"  observation {k}: {v['station']} {v['temp']['value']} F at {v['issued']}")
        for k, v in snap.alerts.items():
            print(f"  alerts {k}: {len(v['areas'])} area(s), {len(v['skipped'])} left out")
        for k, v in snap.satellite.items():
            print(f"  satellite {k}: {v['time']}")
        for k, v in snap.extra.items():
            print(f"  {k}: {v.get('issued') or v.get('fetched', '')}" if isinstance(v, dict) else f"  {k}")
        for n in snap.notes:
            print(f"  note: {n}")
        return 0
    if args.cmd == "check":
        from pakmap.app_integration import voiceover_duration

        from .generate import plan_layers

        words = _words(args)
        duration = voiceover_duration(Path(args.voiceover)) if args.voiceover else None
        try:
            plan, rows, snap, payload = plan_layers(project, words, duration or 600.0)
        except Exception as exc:
            for p in getattr(exc, "problems", [str(exc)]):
                print(f"problem: {p}")
            return 1
        print(f"ok: {len(plan.beats)} beat(s), {len(rows)} weather layer(s), {len(payload.report.lines)} number(s) on screen")
        print(payload.report.to_text())
        return 0
    if args.cmd == "render":
        from .generate import generate_forecast_video

        words = _words(args)

        def progress(msg, frac):
            print(f"  {frac * 100:5.1f}%  {msg}", flush=True)

        import os

        res = generate_forecast_video(project, Path(args.voiceover), Path(args.out), whisper_words=words, sound_design=not args.no_sound,
                                      progress_cb=progress, pexels_api_key=args.pexels_key or os.environ.get("PEXELS_API_KEY", ""),
                                      media_dir=project.work_dir / "media", edit_style=args.style or _project_style(project))
        if not res.ok:
            for e in res.errors:
                print(f"error: {e}")
            return 1
        for w in res.warnings:
            print(f"warning: {w}")
        print(f"wrote {args.out}")
        return 0
    return 2
