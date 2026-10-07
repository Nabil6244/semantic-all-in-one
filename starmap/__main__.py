"""python3 -m starmap check plan.csv [--words words.json | --duration 90]        the Check plan report
   python3 -m starmap compile plan.csv --out spec.json [--words ...] [--media media.json] [--media-dir DIR] [--channel NAME]
   python3 -m starmap render plan.csv --out video.mp4 [same options]              compile, then render with starmap-engine
   python3 -m starmap words narration.txt --out words.json                         estimated word timing (to try a script)
   python3 -m starmap prompt [--pack apollo11] [--script script.txt] [--out prompt.txt]   the beat-plan prompt, filled in
   python3 -m starmap packs                                                        the mission packs available"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .beat_csv import PlanError, read_plan
from .catalog import Catalog, available_packs
from .check import check_csv
from .compile import CompileError, compile_plan, strip_private

ENGINE = Path(__file__).resolve().parent.parent / "starmap-engine"


def _words(path):
    if not path:
        return ()
    from pakmap.words import load_words   # the shared Whisper word-list reader (read-only)

    return load_words(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="starmap")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "compile", "render"):
        p = sub.add_parser(name)
        p.add_argument("csv")
        p.add_argument("--words", help="word timestamps JSON (the voiceover's transcript)")
        p.add_argument("--duration", type=float)
        p.add_argument("--pack", help="optional starting context (a dataset id); datasets are found from the CSV")
        p.add_argument("--now", help="the reference date \"now\" means (YYYY-MM-DD; the plan row's date wins)")
        p.add_argument("--media", help="JSON: asset description -> file (or {file, credit})")
        if name != "check":
            p.add_argument("--out", required=True)
            p.add_argument("--media-dir", help="where the pictures and clips are (default: next to the spec)")
            p.add_argument("--channel", help="channel name shown as a watermark")
            p.add_argument("--fps", type=int, default=30)
    w = sub.add_parser("words")
    w.add_argument("text")
    w.add_argument("--out", required=True)
    w.add_argument("--wps", type=float, default=2.5)
    pr = sub.add_parser("prompt")
    pr.add_argument("--pack", help="a dataset to list in full")
    pr.add_argument("--script")
    pr.add_argument("--out")
    sub.add_parser("packs", help="the datasets in the library (found automatically)")
    a = ap.parse_args(argv)
    if a.cmd == "packs":
        print("\n".join(available_packs()))
        return 0
    if a.cmd == "prompt":
        from .prompt import build_prompt

        text = build_prompt(a.pack, Path(a.script).read_text(encoding="utf-8") if a.script else None)
        if a.out:
            Path(a.out).write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0
    if a.cmd == "words":
        from pakmap.words import estimate_words, save_words

        save_words(estimate_words(Path(a.text).read_text(encoding="utf-8"), words_per_second=a.wps), a.out)
        return 0
    text = Path(a.csv).read_text(encoding="utf-8")
    media = json.loads(Path(a.media).read_text(encoding="utf-8")) if a.media else None
    if a.cmd == "check":
        rep = check_csv(text, _words(a.words), a.duration, pack=a.pack, media=media, reference_now=a.now)
        print(rep.to_text())
        return 0 if rep.ok else 1
    try:
        plan = read_plan(text, _words(a.words), a.duration)
        if a.pack and not plan.pack:
            plan.pack = a.pack
        comp = compile_plan(plan, Catalog(), media=media, fps=a.fps, watermark={"text": a.channel} if a.channel else None,
                            reference_now=plan.reference_now or a.now)
    except (PlanError, CompileError) as exc:
        print("\n".join(f"ERROR {p}" for p in exc.problems))
        return 1
    for n in comp.notes:
        print(f"NOTE {n}")
    spec = strip_private(comp.spec)
    if a.media_dir:
        spec["media_dir"] = str(Path(a.media_dir).resolve())
    out = Path(a.out)
    spec_path = out if a.cmd == "compile" else out.with_suffix(".spec.json")
    spec_path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    if a.cmd == "compile":
        print(f"wrote {spec_path}")
        return 0
    return subprocess.call(["node", str(ENGINE / "render.mjs"), str(spec_path), str(out)])


if __name__ == "__main__":
    sys.exit(main())
