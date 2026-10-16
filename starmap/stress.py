#!/usr/bin/env python3
"""Stress test for StarMap: hundreds of broken versions of real beat CSVs through the stages Generate runs before the render.

    python -m starmap.stress ~/Downloads/VideoGenerator/Video_*      (projects with starmap/beats.csv and state/narration_words.json)
    python -m starmap.stress PROJECTS --mutants 200 --seed 2 --out /tmp/starmap_stress

Each plan is broken on purpose the ways an AI-written CSV or a re-recorded voiceover breaks it (row typos, unknown modes / frames /
places / layer types / sources, broken dates and JSON, words in number columns, anchors nobody says, rows out of order, a semicolon
CSV, a transcript that ends early ...), then read and matched to the catalog with the repairs Generate uses (starmap/heal.py), then
compiled. A STOP is anything that would end Generate before the pictures. Nothing is fetched, nothing is rendered, no project changes.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whatif.stress import C, pick  # noqa: E402  (the CSV-as-rows helper is shared)


def load_base(project: Path) -> Optional[Dict[str, Any]]:
    csv_p, words_p = project / "starmap" / "beats.csv", project / "state" / "narration_words.json"
    if not (csv_p.is_file() and words_p.is_file()):
        return None
    w = json.loads(words_p.read_text(encoding="utf-8"))
    words = w.get("words") if isinstance(w, dict) else w
    end = words[-1][2] if isinstance(words[-1], (list, tuple)) else words[-1].get("end", 0)
    return {"name": project.name, "csv": csv_p.read_text(encoding="utf-8"), "words": words, "duration": float(end) + 1.0}


def m_row(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    c.put(r, "row", rng.choice(["beats", "Layer", "crd", "clips", "", "??", "scene"])); return "row type"

def m_mode(c, rng):
    r = pick(rng, c.of("beat"))
    if r is None:
        return None
    c.put(r, "mode", rng.choice(["Map", "mapfootage", "video", "", "footage", "map_footage"])); return "mode"

def m_frame(c, rng):
    r = pick(rng, c.of("beat"))
    if r is None:
        return None
    c.put(r, "frame", rng.choice(["galactic", "", "space", "solar", "zoom", "surface"])); return "frame"

def m_place(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    c.put(r, "place", rng.choice(["Planet X", "", "voyager", "Sun", "Alpha Centauri", "the void", "Earth's moon"])); return "place"

def m_type(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    c.put(r, "type", rng.choice(["flybyy", "", "push_in", "stat", "sparkle", "launch", "orbit", "caption"])); return "type"

def m_date(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    c.put(r, "date", rng.choice(["1977-13-45", "next year", "", "2026-11-18", "3000-01-01", "1800-01-01", "18/11/2026"])); return "date"

def m_asset(c, rng):
    r = pick(rng, c.of("card") + c.of("clip"))
    if r is None:
        return None
    a = c.get(r, "asset")
    c.put(r, "asset", rng.choice([a.split(":", 1)[-1], "", "google:" + a.split(":", 1)[-1], "file:missing.mp4", "nasa_image:"])); return "asset"

def m_numbers(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    k = rng.choice(["value_from", "value_to", "hold", "dur", "t", "start", "end"])
    c.put(r, k, rng.choice(["ten", "4.2 km", "-3", "99999", "nan", "inf", "1,200", "0"])); return f"number {k}"

def m_extra(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    c.put(r, "extra", rng.choice(["{broken", "[1]", "{'a': 1}", '{"cam": "wild"}', "x"])); return "extra"

def m_anchor(c, rng):
    r = pick(rng, c.rows[1:])
    if r is None:
        return None
    c.put(r, "vo_anchor", rng.choice(["zebra crossing blue piano", "", "the", "26 billion kilometers"])); return "anchor"

def m_order(c, rng):
    if len(c.rows) < 4:
        return None
    r = rng.choice(c.rows[1:]); c.rows.remove(r); c.rows.insert(rng.randrange(len(c.rows)), r); return "row moved"

def m_blank(c, rng):
    for _ in range(rng.randint(1, 8)):
        r = pick(rng, c.rows)
        if r:
            r[rng.randrange(len(r))] = ""
    return "blank cells"

def m_dupe(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    c.rows.insert(c.rows.index(r), list(r)); return "duplicate row"

def m_beat_id(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    c.put(r, "beat", rng.choice(["", "b999", "B1", "beat one"])); return "beat id"

ROW_MUTATIONS: List[Callable] = [m_row, m_mode, m_frame, m_place, m_type, m_date, m_asset, m_numbers, m_extra, m_anchor, m_order, m_blank,
                                 m_dupe, m_beat_id]


def mutate(base, seed):
    rng = random.Random(seed)
    c = C(base["csv"])
    what = [d for d in (rng.choice(ROW_MUTATIONS)(c, rng) for _ in range(rng.randint(1, 4))) if d]
    text = c.text(";" if rng.random() < 0.05 else ",")
    if rng.random() < 0.05:
        text = "﻿" + text.replace("\n", "\r\n"); what.append("BOM + CRLF")
    words = list(base["words"])
    if rng.random() < 0.1:
        words = words[: max(5, int(len(words) * rng.uniform(0.3, 0.8)))]; what.append("transcript ends early")
    return text, words, what


def run_one(job):
    base, seed = job
    from starmap.beat_csv import PlanError, read_plan
    from starmap.catalog import Catalog
    from starmap.compile import CompileError, compile_plan
    from starmap.heal import HealedCsv, heal_until_clean, media_numbers
    from starmap.resolve import resolve

    text, words, what = mutate(base, seed)
    res = {"seed": seed, "base": base["name"], "what": what, "stop": None, "csv": text}
    duration = base["duration"]
    try:
        cat = Catalog()
        numbers = media_numbers(text)
        healed = HealedCsv(text)

        def load(t):                     # the same steps as generate_starmap_video's load()
            try:
                p = read_plan(t, words, duration)
            except PlanError as exc:
                return None, list(exc.problems)
            p.duration = duration
            if p.beats and p.beats[-1].end > duration:
                p.beats[-1].end = max(p.beats[-1].start + 0.5, duration)
            p.media_numbers = numbers
            r = resolve(p, cat, reference_now=p.reference_now)
            return (p, r), list(r.errors)

        loaded, problems = heal_until_clean(healed, load, lambda s: None)
        if problems or loaded is None:
            res["stop"] = "read: " + "; ".join(problems[:2])[:220] if problems else "read: the plan could not be read"
            return res
        plan, r = loaded
        state = {"plan": plan, "res": r, "first": True}

        def build(t):
            if not state["first"]:
                lo, pr = load(t)
                if pr:
                    return None, pr
                state["plan"], state["res"] = lo
            state["first"] = False
            try:
                return compile_plan(state["plan"], cat, media={}, resolution=state["res"]), []
            except CompileError as exc:
                return None, list(exc.problems)

        built, problems = heal_until_clean(healed, build, lambda s: None)
        if problems or built is None:
            res["stop"] = "compile: " + "; ".join(problems[:2])[:220] if problems else "compile: the plan could not be compiled"
    except Exception as exc:              # noqa: BLE001
        res["stop"] = f"crash: {type(exc).__name__}: {str(exc)[:200]}"
    return res


def group(msg: str) -> str:
    return re.sub(r"\d+(\.\d+)?", "N", re.sub(r"'[^']*'", "'…'", msg))[:150]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projects", nargs="+", type=Path)
    ap.add_argument("--mutants", type=int, default=150)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--workers", type=int, default=0)
    a = ap.parse_args(argv)
    bases = [b for b in (load_base(p) for p in a.projects) if b]
    if not bases:
        print("no StarMap project with starmap/beats.csv and state/narration_words.json")
        return 2
    out = a.out or Path(tempfile.mkdtemp(prefix="starmap_stress_"))
    out.mkdir(parents=True, exist_ok=True)
    print(f"bases: {', '.join(b['name'] for b in bases)}; {a.mutants} broken plans each")
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers or None) as ex:
        results = list(ex.map(run_one, [(b, a.seed * 100000 + i) for b in bases for i in range(a.mutants)], chunksize=1))
    stops = [r for r in results if r["stop"]]
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in stops:
        groups[group(r["stop"])].append(r)
    lines = [f"StarMap stress test: {len(results)} broken plans from {len(bases)} project(s) in {time.time() - t0:.0f} s, {len(stops)} stopped "
             f"({100 * len(stops) / max(1, len(results)):.1f} %)"]
    for g, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        p = out / f"stop_{len(lines):02d}.csv"
        p.write_text(rs[0]["csv"], encoding="utf-8")
        lines.append(f"  {len(rs):4d}  {g}   e.g. {rs[0]['base']} seed {rs[0]['seed']} ({', '.join(rs[0]['what'])}) -> {p.name}")
    report = "\n".join(lines)
    (out / "report.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    return 1 if stops else 0


if __name__ == "__main__":
    sys.exit(main())
