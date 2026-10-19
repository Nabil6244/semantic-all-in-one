"""No two graphics on top of each other: the frame-by-frame overlap check (whatif-engine/tools/overlap_audit.mjs) and its repair.

Render 024 (2026-10-19): "17 KM/S" over "3.6 AU", "6 LIGHT-YEARS" over the list of stars, "THE BAR" over "THE CENTRAL BULGE", a card under
the corner instrument ... each layer was placed by its own rule, and nothing looked at the frame they make together. The audit draws every
layer of the spec at 10 frames a second on a recording canvas and reports each pair whose text runs into the other's text or card; the
repair works on timing only (positions are the layers' own):

  two graphics          the later one takes over: the earlier ends just before it (when it has had 1.5 s), else the later waits for the
                        earlier to end (when it keeps 1.5 s), else the later one is left out
  a graphic and a       the instrument (light clock, "where are we" panel, citation line) steps back while the graphic is up, as it
  corner instrument     already does over diagrams (spec "mute" windows, lib/timing.mjs)

and checks again, up to three times. A failure of the check never stops a video (the spec is left as it was).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

INSTRUMENTS = {"tm_clock", "tm_mission", "tm_cite"}
MIN_SHOWN_S = 1.5          # a graphic cut or delayed keeps at least this long on screen, else the later one is left out
HANDOFF_S = 0.05
MUTE_PAD_S = 0.15
ROUNDS = 3


def audit(spec: Dict[str, Any], *, fps: int = 10, timeout: float = 180.0) -> List[Dict[str, Any]]:
    """The clashes in a spec (see overlap_audit.mjs). Raises RuntimeError when the check cannot run."""
    from .preflight import engine_dir, node_bin

    eng = engine_dir()
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "spec.json"
        f.write_text(json.dumps(spec), encoding="utf-8")
        r = subprocess.run([node_bin(), str(eng / "tools" / "overlap_audit.mjs"), str(f), "--fps", str(fps)], cwd=str(eng),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    try:
        out = json.loads((r.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError(f"the overlap check gave no answer ({(r.stderr or '').strip()[-300:] or f'exit {r.returncode}'})")
    if "error" in out:
        raise RuntimeError(out["error"])
    return list(out.get("clashes") or [])


def _timed(L: Dict[str, Any]) -> bool:
    return L.get("start") is not None and L.get("end") is not None


def _mute(L: Dict[str, Any], a: float, b: float) -> None:
    ws = [list(map(float, w)) for w in (L.get("mute") or [])] + [[round(a - MUTE_PAD_S, 3), round(b + MUTE_PAD_S, 3)]]
    ws.sort()
    merged: List[List[float]] = []
    for w in ws:
        if merged and w[0] <= merged[-1][1] + 0.6:          # two windows this close are one step back, not a flicker
            merged[-1][1] = max(merged[-1][1], w[1])
        else:
            merged.append(w)
    L["mute"] = merged


def _label(L: Dict[str, Any], text: str) -> str:
    return text if text and text != "[card]" else str(L.get("type", "graphic"))


def resolve(spec: Dict[str, Any], clashes: List[Dict[str, Any]], notes: List[str]) -> int:
    """Apply the timing repairs for one round of clashes (in place). Returns how many clashes it acted on."""
    layers = spec.get("layers") or []
    drop: set = set()
    acted = 0
    for c in sorted(clashes, key=lambda c: (c["start"], c["a"], c["b"])):
        a, b = int(c["a"]), int(c["b"])
        if a in drop or b in drop or a >= len(layers) or b >= len(layers):
            continue
        A, B = layers[a], layers[b]
        inst_a, inst_b = A.get("type") in INSTRUMENTS or not _timed(A), B.get("type") in INSTRUMENTS or not _timed(B)
        if inst_a and inst_b:
            continue                                         # two instruments: their own layout, nothing timed to move
        if inst_a or inst_b:
            inst, other = (A, B) if inst_a else (B, A)
            _mute(inst, float(c["start"]), float(c["end"]))
            notes.append(f"{c['start']:.1f}-{c['end']:.1f}s: {_label(inst, '')} steps back while "
                         f"{_label(other, c['b_text'] if inst_a else c['a_text'])} is on screen (they overlapped)")
            acted += 1
            continue
        first, then = (A, B) if float(A["start"]) <= float(B["start"]) else (B, A)
        i_then = b if then is B else a
        f0, f1, t0, t1 = float(first["start"]), float(first["end"]), float(then["start"]), float(then["end"])
        what = f"{_label(first, c['a_text'] if first is A else c['b_text'])} and {_label(then, c['b_text'] if then is B else c['a_text'])}"
        if t0 - f0 >= MIN_SHOWN_S:
            first["end"] = round(t0 - HANDOFF_S, 3)
            first["fade_out"] = min(float(first.get("fade_out", 0.3) or 0.3), 0.25)
            notes.append(f"{t0:.1f}s: {what} overlapped; the first ends as the second comes in")
        elif t1 - (f1 + HANDOFF_S) >= MIN_SHOWN_S:
            then["start"] = round(f1 + HANDOFF_S, 3)
            notes.append(f"{t0:.1f}s: {what} overlapped; the second waits until the first has gone ({f1:.1f}s)")
        else:
            drop.add(i_then)
            notes.append(f"{t0:.1f}s: {what} overlapped and there was no room for both; the second is left out")
        acted += 1
    if drop:
        spec["layers"] = [L for i, L in enumerate(layers) if i not in drop]
    return acted


def repair_overlaps(spec: Dict[str, Any], log: Callable[[str], None] = print, *,
                    run_audit: Optional[Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """Check the spec frame by frame and repair what overlaps (in place, also returned). Never raises."""
    run_audit = run_audit or audit
    notes = spec.setdefault("whatif", {}).setdefault("notes", [])
    try:
        before = run_audit(spec)
    except Exception as exc:                                 # noqa: BLE001 -- the check is help, never a reason to stop
        log(f"[What If] overlap check skipped ({exc})")
        return spec
    if not before:
        log("[What If] overlap check: no text or graphic overlaps another in any frame")
        return spec
    clashes, fixed = before, 0
    for _ in range(ROUNDS):
        mine: List[str] = []
        acted = resolve(spec, clashes, mine)
        notes.extend(mine)
        for m in mine:
            log(f"[What If] {m}")
        fixed += acted
        if not acted:
            break
        try:
            clashes = run_audit(spec)
        except Exception as exc:                             # noqa: BLE001
            log(f"[What If] overlap re-check skipped ({exc})")
            return spec
        if not clashes:
            break
    left = f"; {len(clashes)} small overlap(s) left (no timing change separates them)" if clashes else ""
    log(f"[What If] overlap check: {len(before)} overlap(s) found frame by frame, {fixed} repaired{left}")
    return spec
