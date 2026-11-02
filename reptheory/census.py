"""Feature count: how often every graphic Rep Theory can show actually appears, across the new-topic test scripts (test_fixtures/rep_theory_topics).
It guards against a change that quietly stops a graphic from appearing (render final 2: Flow pictures replaced the figure, the plate and their overlays, and nothing failed).
Plan-level only (no render, no Flow, no network: about a second). `python -m reptheory.census` prints the counts; `--write-baseline` records them after a deliberate change.
A test (test_rep_theory_census.py) fails when a feature in the baseline drops to 0 or below half its baseline count."""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path
from typing import Dict

from . import topic_eval as E

BASELINE = E.TOPICS / "features_baseline.json"
OVERLAYS = ("glows", "tint", "stamp", "morph", "beam", "teaser", "chapter_card", "stopwatch", "lock", "safety", "equations", "sketch", "flow_prompt", "chain", "meter", "effort", "strike", "bubble", "aside", "measure", "hazard", "asset", "qlist", "qtrack")

def count(scenes) -> Counter:
    """Feature -> count for one planned video: each scene's look (cards, pictures, 3D, poses, figure, plate, text), each overlay it carries, each picture cue kind,
    page kickers and values."""
    from . import picture as PIC
    c: Counter = Counter()
    for sc in scenes:
        look = E.look_of(sc); look = "flow" if look.startswith("flow:") else "pose" if look.startswith("pose:") else look
        c[f"look:{look}"] += 1
        for k in OVERLAYS:
            if sc.get(k): c[f"overlay:{k}"] += 1
        if sc.get("look") == "flow" or sc["kind"] == "illus":
            for cue in PIC.plan_cues(dict(sc)) or []: c[f"cue:{cue['kind']}"] += 1
        for pg in sc.get("pages", []):
            if pg.get("kicker"): c["text:kicker"] += 1
            if pg.get("value"): c["text:value"] += 1
            if pg.get("chips"): c["text:chips"] += 1
    return c

def measure() -> Dict[str, int]:
    total: Counter = Counter()
    for _name, text in E.scripts().items():
        _t, _ss, _res, scenes = E.plan(text); total.update(count(scenes))
    return dict(sorted(total.items()))

def check(now: Dict[str, int], base: Dict[str, int]) -> list:
    """Features that disappeared or fell below half of their baseline count."""
    return [f"{k}: {base[k]} -> {now.get(k, 0)}" for k in sorted(base) if base[k] > 0 and now.get(k, 0) < max(1, base[k] // 2)]

def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv; now = measure()
    for k, v in now.items(): print(f"{k:34s} {v}")
    if "--write-baseline" in argv: BASELINE.write_text(json.dumps(now, indent=1)); print(f"baseline written: {BASELINE}"); return 0
    if BASELINE.is_file():
        lost = check(now, json.loads(BASELINE.read_text())); print("lost or halved:", lost or "none"); return 1 if lost else 0
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
