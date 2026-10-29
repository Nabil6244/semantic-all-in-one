"""Compile, look at what the viewer will see, repair, look again -- before a single frame is rendered.

The engine's screen audit (starmap-engine/lib/audit.mjs) projects the whole video a few times a second with the renderer's own
camera, clock and trajectories, and reports where it reads as broken or boring: an EMPTY frame (a speck in black space), a
STILL stretch (nothing moves or changes for seconds), a craft OFF the frame, a REPEATED view. Each finding names its beat.
This module answers each one on that beat only, with the smallest camera change that fixes it, keeps a change only if the
audit says the beat got better, and tries again -- a few passes, a second or so each, so it runs on every Generate:

    empty, nothing in frame   frame wider (scale 2.5) / an action shows a longer stretch of its path (stretch 6)
    empty, a speck            frame closer (scale 0.45) / an action shows a shorter stretch about its middle (stretch 0.35)
    offframe                  frame wider (scale 1.6) / an action's path framed wider (fit 1.5)
    cut                       frame wider (scale 1.5) / an action's path framed wider (fit 1.45), so the planet is whole
    flat                      the beat in the middle of a long stretch with no pattern interrupt is cut into shots (cuts 3)
    still                     a stronger push-in through the beat (creep 1.15) and a faster turn round the subject (spin 2.2)

What it cannot repair is reported (the app logs it), never hidden."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .compile import Compiled, compile_plan, strip_private

ENGINE = Path(__file__).resolve().parent.parent / "starmap-engine"
WEIGHT = {"empty": 3.0, "cut": 2.5, "offframe": 1.0, "still": 1.5, "repeat": 1.0, "track_off": 1.0, "flat": 0.5}   # track_off: review only
PASSES = 4


@dataclass
class RepairReport:
    before: Dict[str, float] = field(default_factory=dict)       # seconds per kind, as first compiled
    after: Dict[str, float] = field(default_factory=dict)        # ... after the repairs
    repairs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    remaining: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def lines(self) -> List[str]:
        if self.error:
            return [f"screen check skipped: {self.error}"]
        fmt = lambda d: ", ".join(f"{k} {d.get(k, 0):.0f} s" for k in WEIGHT)   # noqa: E731
        out = [f"screen check: before {fmt(self.before)}; after {fmt(self.after)}; {len(self.repairs)} beat(s) repaired"]
        for i in self.remaining:
            out.append(f"screen check: still {i['kind']} at {i['t0']:.1f}-{i['t1']:.1f} s (beat {i['beat']}): {i['detail']}")
        return out


def run_audit(spec: Dict[str, Any], node: str = "node") -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="starmap_audit_") as tmp:
        f = Path(tmp) / "spec.json"
        f.write_text(json.dumps(spec), encoding="utf-8")
        out = subprocess.run([node, str(ENGINE / "audit.mjs"), str(f), "--json"], capture_output=True, text=True, timeout=300)
        if out.returncode != 0:
            raise RuntimeError((out.stderr or out.stdout).strip().splitlines()[-1] if (out.stderr or out.stdout).strip() else "audit failed")
        return json.loads(out.stdout)


def _totals(issues: List[Dict[str, Any]]) -> Dict[str, float]:
    return {k: sum(i["t1"] - i["t0"] for i in issues if i["kind"] == k) for k in WEIGHT}


def _score(issues: List[Dict[str, Any]], beat: Optional[str] = None) -> float:
    return sum(WEIGHT.get(i["kind"], 1) * (i["t1"] - i["t0"]) for i in issues if beat is None or i["beat"] == beat)


def _remedies(issue: Dict[str, Any], is_action: bool) -> List[Dict[str, Any]]:
    """What to try for one finding, best guess first."""
    k = issue["kind"]
    nothing = "spans 0%" in issue.get("detail", "")
    if k == "empty":
        if is_action:
            return [{"stretch": 6.0}, {"fit": 2.0}] if nothing else [{"stretch": 0.35}, {"stretch": 0.15}, {"fit": 0.75}]
        return [{"scale": 2.5}, {"scale": 0.45}] if nothing else [{"scale": 0.45}, {"scale": 0.25}, {"scale": 0.02, "creep": 1.25, "spin": 3.0}, {"scale": 0.001, "creep": 1.3, "spin": 3.5}]
    if k == "flat":
        return [] if is_action else [{"cuts": 3}, {"cuts": 2}]
    if k == "cut":
        return [{"fit": 1.45}, {"fit": 1.9}] if is_action else [{"scale": 1.5}, {"scale": 0.7}]
    if k == "offframe":
        return [{"fit": 1.5}, {"stretch": 2.0}] if is_action else [{"scale": 1.6}, {"scale": 2.5}]
    if k == "still":
        return [{"creep": 1.15, "spin": 2.2}, {"creep": 1.25, "spin": 3.0}]
    return []


def compile_checked(plan, cat, *, node: str = "node", log: Callable[[str], None] = lambda s: None, **kw) -> "tuple[Compiled, RepairReport]":
    """compile_plan, then the screen audit and its repairs. Falls back to the plain compile if the audit cannot run."""
    rep = RepairReport()
    comp = compile_plan(plan, cat, **kw)
    try:
        issues = run_audit(strip_private(comp.spec), node)["issues"]
    except Exception as exc:                                        # no node, an engine error: never block a render on the check
        rep.error = str(exc)
        return comp, rep
    rep.before = _totals(issues)
    actions = set(comp.actions or {})
    repairs: Dict[str, Dict[str, Any]] = {}
    tried: Dict[str, int] = {}
    for _ in range(PASSES):
        worst: Dict[str, Dict[str, Any]] = {}
        for i in issues:
            if i["beat"] and (i["beat"] not in worst or WEIGHT[i["kind"]] * (i["t1"] - i["t0"]) > WEIGHT[worst[i["beat"]]["kind"]] * (worst[i["beat"]]["t1"] - worst[i["beat"]]["t0"])):
                worst[i["beat"]] = i
        trial = dict(repairs)
        attempt: Dict[str, Dict[str, Any]] = {}
        for bid, i in worst.items():
            options = _remedies(i, bid in actions)
            n = tried.get(bid, 0)
            if n >= len(options):
                continue
            tried[bid] = n + 1
            attempt[bid] = dict(options[n])                      # each remedy on its own (replacing a kept one if it does better)
            trial[bid] = attempt[bid]
        if not attempt:
            break
        cand = compile_plan(plan, cat, repairs=trial, **kw)
        try:
            new = run_audit(strip_private(cand.spec), node)["issues"]
        except Exception as exc:
            rep.error = str(exc)
            break
        # keep each beat's change only if that beat (and the video as a whole) got better
        kinds = lambda xs, b: {i["kind"] for i in xs if i["beat"] == b}   # noqa: E731
        # (and no new kind of problem there: a speck repaired into a planet sliced by the edge is not a repair)
        kept = {b: f for b, f in attempt.items() if _score(new, b) < _score(issues, b) and kinds(new, b) <= kinds(issues, b)}
        if not kept:
            continue
        repairs.update(kept)
        comp = compile_plan(plan, cat, repairs=repairs, **kw) if kept != attempt else cand
        final = run_audit(strip_private(comp.spec), node)["issues"] if kept != attempt else new
        if _score(final) <= _score(issues):
            issues = final
        else:
            for b in kept:
                repairs.pop(b, None)
            comp = compile_plan(plan, cat, repairs=repairs, **kw)
    rep.after = _totals(issues)
    rep.repairs = repairs
    rep.remaining = issues
    for line in rep.lines():
        log(line)
    return comp, rep
