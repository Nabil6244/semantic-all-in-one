"""python3 -m pakmap compile script.csv --words words.json --out spec.json
   python3 -m pakmap words narration.txt --out words.json     (estimated timing, for laying out a script)
   python3 -m pakmap check script.csv --words words.json      (the plan report only)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compile import CompileError, compile_csv
from .schema import CsvError
from .words import estimate_words, load_words, save_words


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pakmap", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("compile", "check"):
        p = sub.add_parser(name)
        p.add_argument("csv")
        p.add_argument("--words", required=True, help="word timestamps JSON")
        p.add_argument("--duration", type=float, help="video length in seconds (default: end of the narration + 1)")
        p.add_argument("--watermark", help="channel name shown bottom right")
        p.add_argument("--no-validate", action="store_true")
        p.add_argument("--no-sound", action="store_true", help="do not print the sound-design plan")
        if name == "compile":
            p.add_argument("--out", required=True)
    w = sub.add_parser("words")
    w.add_argument("text")
    w.add_argument("--out", required=True)
    w.add_argument("--wps", type=float, default=2.6)
    args = ap.parse_args(argv)
    if args.cmd == "words":
        save_words(estimate_words(Path(args.text).read_text(encoding="utf-8"), words_per_second=args.wps), args.out)
        print(f"wrote {args.out} (estimated timing)")
        return 0
    try:
        res = compile_csv(args.csv, load_words(args.words), duration=args.duration, validate=not args.no_validate,
                          watermark={"text": args.watermark} if args.watermark else None)
    except CsvError as exc:
        print("\n".join(f"ERROR: {p}" for p in exc.problems), file=sys.stderr)
        return 2
    except CompileError as exc:
        print(exc.report.to_text(), file=sys.stderr)
        return 2
    print(res.report.to_text())
    if not args.no_sound:
        from .app_integration import plan_pakmap_sound

        print()
        print(plan_pakmap_sound(res).to_text())
    if args.cmd == "compile":
        Path(args.out).write_text(json.dumps(res.spec, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
