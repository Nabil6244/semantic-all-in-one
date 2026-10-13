"""python -m weather.automation <command> — the daily forecast prep without the app.

    prep      --project DIR --contact EMAIL_OR_URL [--force] [--library DIR]   prepare the forecast into DIR
    changes   --project DIR --contact EMAIL_OR_URL                           what changed since the prep, lines to re-record
    due       --root DIR --contact EMAIL_OR_URL [--notify]                   prepare DIR/<Central date> if it is due (the OS task)
    schedule  --root DIR --contact EMAIL_OR_URL [--windows]                  print the OS task text (installs nothing)
    why       --project DIR                                                  print the story and why it was chosen"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m weather.automation", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep")
    p.add_argument("--project", required=True)
    p.add_argument("--contact", required=True, help="your email or website, sent to the NWS as it asks")
    p.add_argument("--force", action="store_true", help="replace a script.txt you edited")
    p.add_argument("--library", default=None, help="your own footage folder, used before stock where a clip matches")
    c = sub.add_parser("changes")
    c.add_argument("--project", required=True)
    c.add_argument("--contact", required=True)
    d = sub.add_parser("due")
    d.add_argument("--root", required=True)
    d.add_argument("--contact", required=True)
    d.add_argument("--notify", action="store_true")
    s = sub.add_parser("schedule")
    s.add_argument("--root", required=True)
    s.add_argument("--contact", required=True)
    s.add_argument("--windows", action="store_true")
    w = sub.add_parser("why")
    w.add_argument("--project", required=True)
    args = ap.parse_args(argv)

    from ..nws import NwsError
    from .fetch import PrepDataError
    from .plan import PlanBuildError
    from .prep import PrepError, prep

    if args.cmd == "prep":
        try:
            res = prep(args.project, args.contact, force=args.force, library_dir=args.library, log=lambda m: print(f"  {m}", flush=True))
        except (NwsError, PrepDataError, PrepError, PlanBuildError, ValueError) as exc:
            print(f"error: {exc}")
            return 1
        print(res.summary)
        print("Why this story:")
        print(res.story.why_text)
        for n in res.notes:
            print(f"note: {n}")
        print(f"wrote {Path(args.project).resolve()}: script.txt, beats.csv, weather_layers.csv, resolved.json, coverage.json, prep.json")
        return 0
    if args.cmd == "changes":
        from .changes import check

        try:
            rep = check(args.project, args.contact)
        except (NwsError, PrepDataError, FileNotFoundError) as exc:
            print(f"error: {exc}")
            return 1
        print(rep.text)
        return 0
    if args.cmd == "due":
        from .schedule import central_now, day_folder, is_due, notify

        if not is_due(args.root):
            print("not due: before 5:30 AM Central, or today is already prepared")
            return 0
        folder = day_folder(args.root, central_now().date())
        try:
            res = prep(folder, args.contact)
        except (NwsError, PrepDataError, PrepError, PlanBuildError, ValueError) as exc:
            print(f"error: {exc}")
            if args.notify:
                notify("Weather prep failed", str(exc)[:200])
            return 1
        print(res.summary)
        if args.notify:
            notify("Today's forecast script is ready", f"{res.story.lead_city} leads. Open the app to record it.")
        return 0
    if args.cmd == "schedule":
        from .schedule import command, launchd_plist, windows_task_xml

        cmd = command(args.root, args.contact)
        root = Path(__file__).resolve().parents[2]
        sys.stdout.write(windows_task_xml(cmd, root) if args.windows else launchd_plist(cmd, root, Path(args.root) / "prep.log"))
        return 0
    if args.cmd == "why":
        meta = json.loads((Path(args.project) / "prep.json").read_text(encoding="utf-8"))
        print(f"{meta['story']['kind']} — {meta['story']['lead_city']} ({meta['for_date']})")
        print("\n".join(f"- {w}" for w in meta["why"]))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
