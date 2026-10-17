"""Audit many beat plans at once, without rendering: compile each with the current code (word timing estimated from its
beat texts unless a words file sits next to it as <name>.words.json) and run the engine's screen audit on the spec.

    python3 -m starmap.corpus_audit plan.csv [plan2.csv ...] [--out DIR]

Prints, per plan, the seconds of empty / still / off-frame / repeated picture, then every finding."""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from pakmap.words import estimate_words, load_words

from .beat_csv import read_plan
from .catalog import Catalog
from .compile import CompileError, compile_plan, strip_private

ENGINE = Path(__file__).resolve().parent.parent / "starmap-engine"
KINDS = ("empty", "cut", "still", "offframe", "repeat", "track_off", "flat")


def plan_words(path: Path):
    side = path.with_suffix(".words.json")
    if side.is_file():
        return load_words(side)
    text = " ".join(r.get("text", "") for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))) if r.get("row") == "beat")
    return estimate_words(text, words_per_second=2.5)


def audit_spec(spec: dict) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(spec, f)
    try:
        out = subprocess.run(["node", str(ENGINE / "audit.mjs"), f.name, "--json"], capture_output=True, text=True, check=True).stdout
    finally:
        Path(f.name).unlink(missing_ok=True)
    return json.loads(out)


def audit_plan(path: Path, out_dir: Path | None = None, repair: bool = False) -> dict:
    plan = read_plan(path.read_text(encoding="utf-8"), plan_words(path))
    kw = dict(media=None, resolve_media=False, reference_now=plan.reference_now or "2026-10-15")
    if repair:
        from .repair import compile_checked

        comp, _ = compile_checked(plan, Catalog(), **kw)
    else:
        comp = compile_plan(plan, Catalog(), **kw)
    spec = strip_private(comp.spec)
    if out_dir:
        (out_dir / f"{path.stem}.spec.json").write_text(json.dumps(spec), encoding="utf-8")
    return audit_spec(spec)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="starmap.corpus_audit")
    ap.add_argument("plans", nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--quiet", action="store_true", help="totals only")
    ap.add_argument("--repair", action="store_true", help="compile with the screen check's repairs (as Generate does)")
    a = ap.parse_args(argv)
    out_dir = Path(a.out) if a.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    grand = dict.fromkeys(KINDS, 0.0)
    total_s = 0.0
    for p in map(Path, a.plans):
        try:
            r = audit_plan(p, out_dir, a.repair)
        except (CompileError, ValueError) as exc:
            print(f"{p.name}: could not compile: {exc}")
            continue
        sums = {k: sum(i["t1"] - i["t0"] for i in r["issues"] if i["kind"] == k) for k in KINDS}
        total_s += r["duration"]
        for k in KINDS:
            grand[k] += sums[k]
        print(f"{p.name:42s} {r['duration']:6.0f} s  " + "  ".join(f"{k} {sums[k]:5.0f}" for k in KINDS))
        if not a.quiet:
            for i in r["issues"]:
                print(f"    {i['kind']:8s} {i['t0']:7.1f}-{i['t1']:<7.1f} {i['beat']:5s} {i['detail']}")
    print(f"{'ALL':42s} {total_s:6.0f} s  " + "  ".join(f"{k} {grand[k]:5.0f}" for k in KINDS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
