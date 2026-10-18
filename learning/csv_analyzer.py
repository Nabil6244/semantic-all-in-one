"""Read-only analysis of CSVs already imported into projects -> ``csv_analysis`` ledger events (structure only, no text).

* Reads only; never rewrites a CSV or any project file. Original bytes are hashed, so an unchanged CSV produces the same event id
  (``csv_analysis:<project>:<slot>:<sha>``) and a re-scan adds nothing (no inflated evidence). Per-project (mtime,size,sha)
  fingerprints in the ledger's meta table make a re-scan skip unchanged files without even re-reading them.
* Only the real schemas it understands are analysed: the normal ``visual_plan.csv`` and the Overscaled/Exp Solar slot, both
  ``scene_number, script_segment[, asset_type, prompt, ...]``. pakMap / StarMap / Hybrid / What If / Weather CSVs are counted as
  ``unsupported_schema`` and never interpreted. Fields a CSV lacks are reported as None (unavailable), never guessed.
"""

from __future__ import annotations

import csv
import io
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import events as ev
from . import ledger as _ledger
from .scope import resolve_scope

# (slot/mode, file of the project). Hybrid keeps its final plan as hybrid/plan.json (the imported CSV itself is not stored in the
# project), so that plan is what is measured for Hybrid. pakMap and Weather are not analysed.
SLOTS = (("normal", lambda ws: ws.csv_path), ("overscaled", lambda ws: ws.overscaled_csv_path),
         ("starmap", lambda ws: ws.starmap_csv_path), ("whatif", lambda ws: Path(ws.root) / "whatif" / "shots.csv"),
         ("hybrid", lambda ws: ws.hybrid_plan_path))
UNSUPPORTED_SLOTS = ("pakmap_csv_path",)


def _pct(vals: List[float], q: float) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(q * len(s)))], 2)


def features(text: str) -> Dict[str, Any]:
    """Measured facts from one CSV's text (structure only). Missing columns -> None."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    cols = [c for c in (reader.fieldnames or []) if c]
    rows, malformed = [], 0
    for r in reader:
        if None in r or any(v is None for v in r.values()):
            malformed += 1
        rows.append(r)
    words = [len((r.get("script_segment") or "").split()) for r in rows]
    out: Dict[str, Any] = {"rows": len(rows), "columns": cols[:30], "malformed_rows": malformed,
                           "empty_narration_rows": sum(1 for w in words if w == 0),
                           "words_mean": round(statistics.fmean(words), 2) if words else None,
                           "words_p90": _pct([float(w) for w in words], 0.9), "words_max": max(words) if words else None,
                           "words_cv": round(statistics.pstdev(words) / statistics.fmean(words), 3) if words and statistics.fmean(words) else None}
    if "asset_type" in cols:
        types = [(r.get("asset_type") or "").strip().lower() for r in rows]
        counts: Dict[str, int] = {}
        for t in types:
            if t:
                counts[t] = counts.get(t, 0) + 1
        run = best = 0
        prev = None
        for t in types:
            run = run + 1 if t and t == prev else 1
            prev = t
            best = max(best, run)
        out.update(asset_counts=counts, max_same_type_run=best if types else None)
    else:
        out.update(asset_counts=None, max_same_type_run=None)
    if "prompt" in cols:
        prompts = [(r.get("prompt") or "").strip().lower() for r in rows]
        filled = [p for p in prompts if p]
        out.update(prompt_words_mean=round(statistics.fmean(len(p.split()) for p in filled), 2) if filled else None,
                   empty_prompt_rows=len(rows) - len(filled),
                   duplicate_prompt_share=round(1 - len(set(filled)) / len(filled), 3) if filled else None)
    else:
        out.update(prompt_words_mean=None, empty_prompt_rows=None, duplicate_prompt_share=None)
    return out


def _runs(values: List[str]) -> int:
    best = run = 0
    prev = None
    for v in values:
        run = run + 1 if v and v == prev else 1
        prev = v
        best = max(best, run)
    return best if values else 0


def _num(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _unit_features(units: List[Dict[str, Any]], mode_key: str, with_times: bool = True) -> Dict[str, Any]:
    modes = [str(u.get(mode_key) or "").strip().lower() for u in units]
    counts: Dict[str, int] = {}
    for m in modes:
        if m:
            counts[m] = counts.get(m, 0) + 1
    secs = [e - s for u in units for s, e in [(_num(u.get("start")), _num(u.get("end")))] if with_times and s is not None and e is not None and e > s]
    return {"beats": len(units), "mode_counts": counts or None, "max_same_mode_run": _runs(modes) if counts else None,
            "beat_s_mean": round(statistics.fmean(secs), 2) if secs else None, "beats_with_times": len(secs)}


def features_starmap(text: str) -> Dict[str, Any]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows = list(reader)
    beats = [r for r in rows if (r.get("row") or "").strip().lower() == "beat"]
    out = {"rows": len(rows), "columns": [c for c in (reader.fieldnames or []) if c][:30], **_unit_features(beats, "mode")}
    out["layers"] = sum(1 for r in rows if (r.get("row") or "").strip().lower() == "layer")
    out["cards"] = sum(1 for r in rows if (r.get("row") or "").strip().lower() == "card")
    out["beats_missing_anchor_share"] = round(sum(1 for r in beats if not (r.get("vo_anchor") or "").strip()) / len(beats), 3) if beats else None
    return out


def features_whatif(text: str) -> Dict[str, Any]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows = list(reader)
    shots = [r for r in rows if (r.get("kind") or "").strip()]
    out = {"rows": len(rows), "columns": [c for c in (reader.fieldnames or []) if c][:30], **_unit_features(shots, "kind", with_times=False)}
    out["layers"] = sum(1 for r in rows if (r.get("type") or "").strip())
    assets: Dict[str, int] = {}
    for r in shots:
        a = (r.get("asset") or "").strip().lower().split(":", 1)[0]
        if a:
            assets[a] = assets.get(a, 0) + 1
    out["asset_counts"] = assets or None
    return out


def features_hybrid(text: str) -> Dict[str, Any]:
    plan = json.loads(text)
    beats = [b for b in (plan.get("beats") or []) if isinstance(b, dict)]
    out = {"rows": len(beats), "duration_s": _num(plan.get("duration")), **_unit_features(beats, "mode")}
    out["layers"] = sum(len(b.get("layers") or []) for b in beats)
    out["cards"] = sum(len(b.get("cards") or []) for b in beats)
    return out


def _extract(slot: str, text: str) -> Dict[str, Any]:
    if slot == "starmap":
        return features_starmap(text)
    if slot == "whatif":
        return features_whatif(text)
    if slot == "hybrid":
        return features_hybrid(text)
    return features(text)


def _scope_for(ws: Any, slot: str, led: _ledger.Ledger) -> str:
    """The scope captured when the user actually imported/rendered this project in this mode (so analysis, renders and ratings
    share one scope); falls back to resolving it from the project's own saved settings."""
    try:
        for e in led.events(event_type="csv_import", project_id=ws.project_id, newest_first=True, limit=20):
            if e["style_scope"].startswith(slot + "/"):
                return e["style_scope"]
    except Exception:
        pass
    return resolve_scope(None, slot, workspace=ws)


def analyze_project(ws: Any, led: _ledger.Ledger, summary: Dict[str, Any]) -> None:
    pid = ws.project_id
    for slot, getter in SLOTS:
        path = Path(getter(ws))
        if not path.is_file():
            continue
        st = path.stat()
        fp_key = f"csvscan:{pid}:{slot}"
        stamp = f"{st.st_mtime_ns}:{st.st_size}"
        known = led.get_meta(fp_key)
        if known and known.split("|")[0] == stamp:
            summary["unchanged"] += 1
            continue
        raw = path.read_bytes()
        sha = ev.sha256_bytes(raw)
        led.set_meta(fp_key, f"{stamp}|{sha}")
        try:
            feats = _extract(slot, raw.decode("utf-8-sig", errors="replace"))
        except Exception:
            summary["skipped"].append(f"{pid}:{slot}:unreadable")
            continue
        scope = _scope_for(ws, slot, led)
        new = ev.record_event("csv_analysis", style_scope=scope, project_id=pid, csv_sha256=sha,
                              event_id=f"csv_analysis:{pid}:{slot}:{sha}", payload={**feats, "slot": slot}, ledger=led)
        summary["analyzed_new" if new else "unchanged"] += 1
    for attr in UNSUPPORTED_SLOTS:
        if Path(getattr(ws, attr, "")).is_file():
            summary["unsupported_schema"] += 1


def scan_projects(projects_root: Path, *, ledger: Optional[_ledger.Ledger] = None, cancel: Any = None,
                  progress: Optional[Callable[[float, str], None]] = None) -> Dict[str, Any]:
    """Incrementally analyse every eligible project. Returns a summary; never raises; honours ``cancel`` (threading.Event)."""
    led = ledger or _ledger.default_ledger()
    summary: Dict[str, Any] = {"projects": 0, "analyzed_new": 0, "unchanged": 0, "unsupported_schema": 0, "skipped": [],
                               "cancelled": False, "error": None}
    try:
        from project_workspace import list_projects
        projects = list_projects(Path(projects_root))
        n = len(projects)
        for i, ws in enumerate(projects, 1):
            if cancel is not None and cancel.is_set():
                summary["cancelled"] = True
                break
            summary["projects"] += 1
            try:
                analyze_project(ws, led, summary)
            except Exception as exc:
                summary["skipped"].append(f"{getattr(ws, 'project_id', '?')}:{type(exc).__name__}")
            if progress and (i % 10 == 0 or i == n):
                progress(i / max(1, n), f"Analyzed {i}/{n} projects")
        if not summary["cancelled"]:
            led.set_meta("analysis_last_run", datetime.now(timezone.utc).isoformat(timespec="seconds"))
            led.set_meta("analysis_stale", "0")
        led.set_meta("analysis_summary", json.dumps({k: v for k, v in summary.items() if k != "skipped"} | {"skipped": len(summary["skipped"])}))
    except Exception as exc:
        summary["error"] = type(exc).__name__
    return summary


def status(led: Optional[_ledger.Ledger] = None) -> Dict[str, Any]:
    led = led or _ledger.default_ledger()
    try:
        summ = json.loads(led.get_meta("analysis_summary") or "{}")
    except ValueError:
        summ = {}
    return {"last_run": led.get_meta("analysis_last_run"), "stale": led.get_meta("analysis_stale", "1") == "1", "summary": summ}
