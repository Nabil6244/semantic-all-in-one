"""The pakMap / Hybrid dry run: the same idea as What If's preflight (whatif/preflight.py + whatif/heal.py).

    CSV text (repaired in memory) -> compile -> the renderer's rule check -> every graphic made and drawn on a mock canvas (node)

Nothing here changes the file on disk and nothing stops over one bad row: a row the reader or compiler refuses, a graphic that cannot be
drawn, a text layer too many for the screen -- each is fixed when it can be (a misspelt template id, a ";" CSV) or LEFT OUT with a note
naming the row, and the plan is read again. Only when no usable row is left, or something that cannot be traced to a row remains, is it a stop.
"Check plan" shows the repairs and the stops; Generate uses the same path when its first compile fails, so what the check says is what Generate does.
"""

from __future__ import annotations

import csv
import difflib
import io
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .anchor import Word
from .compile import CompileError, CompileResult, Report, _engine_root, _find_node, compile_csv
from .schema import ALIASES, LAYER_TYPES, CsvError, parse_csv

MAX_PASSES = 40


@dataclass
class DryRun:
    stops: List[str] = field(default_factory=list)       # anything that would end Generate
    repairs: List[str] = field(default_factory=list)     # what was fixed or left out on the way
    result: Optional[CompileResult] = None
    text: str = ""                                        # the CSV after the repairs (in memory only)
    dropped: List[int] = field(default_factory=list)      # spreadsheet rows that were left out

    @property
    def ok(self) -> bool:
        return not self.stops and self.result is not None


# ---- repairs that are certain ---------------------------------------------------------------------------------------------------------
def heal_text(text: str) -> Tuple[str, List[str]]:
    """What can be fixed with certainty: a BOM, a ';' or tab separated file, CRLF, a misspelt layer_type or template id."""
    notes: List[str] = []
    text = (text or "").lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    head = next((ln for ln in lines if ln.strip()), "")
    if head.count(",") == 0 and (head.count(";") >= 2 or head.count("\t") >= 2):
        delim = ";" if head.count(";") >= head.count("\t") else "\t"
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        text = buf.getvalue()
        notes.append(f"the CSV was separated by {'semicolons' if delim == ';' else 'tabs'}: read as a comma CSV")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return text, notes
    head = [h.strip().lower().replace(" ", "_") for h in rows[0]]
    if "layer_type" not in head:
        return text, notes
    lt, pi = head.index("layer_type"), head.index("params") if "params" in head else -1
    try:
        import gfx_templates

        known = list(gfx_templates.load_library())
    except Exception:
        known = []
    allowed = list(LAYER_TYPES) + list(ALIASES)
    changed = False
    for n, row in enumerate(rows[1:], start=2):
        if len(row) <= lt:
            continue
        v = row[lt].strip().lower().replace(" ", "_")
        if v and v not in allowed:
            close = difflib.get_close_matches(v, allowed, n=1, cutoff=0.8)
            if close:
                row[lt] = close[0]; changed = True
                notes.append(f"row {n}: layer_type {v!r} read as {close[0]!r}")
        if pi >= 0 and len(row) > pi and row[pi].strip().startswith("{") and known:
            try:
                obj = json.loads(row[pi])
            except ValueError:
                continue
            tid = obj.get("template") if isinstance(obj, dict) else None
            if tid and tid not in known:
                close = difflib.get_close_matches(str(tid).lower().replace(" ", "_"), known, n=1, cutoff=0.75)
                if close:
                    obj["template"] = close[0]; row[pi] = json.dumps(obj); changed = True
                    notes.append(f"row {n}: template {tid!r} read as {close[0]!r}")
    if changed:
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        text = buf.getvalue()
    return text, notes


def drop_rows(text: str, lines: Set[int], items: Optional[Set[int]] = None) -> str:
    """The CSV without the given spreadsheet rows (the header is row 1) and, when given, without every row of the given items."""
    rows = list(csv.reader(io.StringIO(text)))
    head = [h.strip().lower().replace(" ", "_") for h in rows[0]] if rows else []
    ii = head.index("item_no") if "item_no" in head else -1
    keep = [rows[0]] if rows else []
    for n, row in enumerate(rows[1:], start=2):
        if n in lines:
            continue
        if items and ii >= 0 and len(row) > ii and row[ii].strip():
            try:
                if int(float(row[ii])) in items:
                    continue
            except ValueError:
                pass
        if any(c.strip() for c in row):
            keep.append(row)
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(keep)
    return buf.getvalue()


# ---- the mock-canvas check of every graphic (node) -------------------------------------------------------------------------------------------
def check_gfx(spec: dict, timeout: float = 120.0) -> Dict[str, Dict[str, Any]]:
    """{event id: {"repairs": [...], "fatal": None | str}} for the map_template events (pakmap-engine/tools/check_gfx.mjs); {} when there are none
    or node is not available (the check is skipped, never a stop)."""
    if not any(e.get("type") == "map_template" for e in spec.get("events", [])):
        return {}
    node, tool = _find_node(), _engine_root() / "tools" / "check_gfx.mjs"
    if not node or not tool.exists():
        return {}
    with tempfile.TemporaryDirectory(prefix="pakmap_gfx_") as d:
        f = Path(d) / "spec.json"
        f.write_text(json.dumps(spec), encoding="utf-8")
        try:
            r = subprocess.run([node, str(tool), str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
            return json.loads(r.stdout.strip().splitlines()[-1]).get("events", {})
        except Exception:
            return {}


def _rows_in(messages: Sequence[str]) -> Tuple[Set[int], Set[int]]:
    rows: Set[int] = set()
    items: Set[int] = set()
    for m in messages:
        for n in re.findall(r"\brow (\d+)\b", m):
            rows.add(int(n))
        for n in re.findall(r"^item (\d+):", m):
            items.add(int(n))
    return rows, items


def _row_of_event(report: Optional[Report], event_id: str) -> Optional[int]:
    for e in (report.events if report else []):
        if e.id == event_id and e.row:
            return e.row
    return None


def dry_run(source: "str | Path | None", words: Sequence[Word], *, text: Optional[str] = None, duration: Optional[float] = None,
            engine: bool = True, **compile_kw: Any) -> DryRun:
    """Heal, compile and check. `source` is the CSV path (or `text` the CSV itself). compile_kw goes to compile_csv (base_dir, watermark,
    width, height, fps, doc_style, auto_templates, media_map, spec_extra ...)."""
    dr = DryRun()
    try:
        raw = text if text is not None else Path(source).read_text(encoding="utf-8-sig")
    except OSError as exc:
        dr.stops.append(f"read: could not read the CSV: {exc}")
        return dr
    cur, notes = heal_text(raw)
    dr.repairs += notes
    if source is not None and "base_dir" not in compile_kw:
        compile_kw["base_dir"] = Path(source).resolve().parent
    for _ in range(MAX_PASSES):
        try:
            res = compile_csv(text=cur, words=words, duration=duration, validate=engine, **compile_kw)
        except CsvError as exc:
            rows, items = _rows_in(exc.problems)
            if not rows and not items:
                dr.stops += [f"read: {p}" for p in exc.problems]
                return dr
            dr.repairs += [f"left out: {p}" for p in exc.problems]
            dr.dropped += sorted(rows)
            cur = drop_rows(cur, rows, items)
            continue
        except CompileError as exc:
            rows, items = _rows_in(exc.report.errors)
            # a renderer rule that names layers ("3 stat chips are on screen at 5.00s (max 2): a, b, c. Shorten ..."): the last one named gives way
            for m in exc.report.errors:
                named = re.search(r"\(max \d+\): ([^.]+(?:\.\d+)?[^.]*)\.", m)
                ids = [t.strip().split(" ")[0] for t in named.group(1).split(",")] if named else []
                row = _row_of_event(exc.report, ids[-1]) if len(ids) > 1 else None
                if row:
                    rows.add(row)
                two = re.search(r"two (\w+) events overlap at ([\d.]+)s", m)      # the later one gives way
                if two:
                    t0 = float(two.group(2))
                    live = sorted((e for e in exc.report.events if e.type == two.group(1) and e.t_in <= t0 + 1e-6 < e.t_out), key=lambda e: e.t_in)
                    rows.update(e.row for e in live[1:] if e.row)
            if not rows and not items:
                dr.stops += [f"compile: {p}" for p in exc.report.errors]
                return dr
            dr.repairs += [f"left out: {p}" for p in exc.report.errors]
            dr.dropped += sorted(rows)
            cur = drop_rows(cur, rows, items)
            continue
        except Exception as exc:  # noqa: BLE001 -- never escape into the UI
            dr.stops.append(f"compile: {exc!r}")
            return dr
        # compiled: draw every graphic once on a mock canvas
        if engine:
            checked = check_gfx(res.spec)
            fatal = {i: r["fatal"] for i, r in checked.items() if r.get("fatal")}
            for i, r in checked.items():
                dr.repairs += [f"graphic {i}: {m}" for m in r.get("repairs", [])]
            if fatal:
                rows = set()
                for i, why in fatal.items():
                    row = _row_of_event(res.report, i)
                    dr.repairs.append(f"left out: graphic {i}" + (f" (row {row})" if row else " (added from the narration)") + f" could not be drawn: {why}")
                    if row:
                        rows.add(row)
                gone = {i for i in fatal if _row_of_event(res.report, i) is None}
                if gone:                                    # auto graphics have no row: they are simply not placed
                    res.spec["events"] = [e for e in res.spec["events"] if e["id"] not in gone]
                if rows:
                    dr.dropped += sorted(rows)
                    cur = drop_rows(cur, rows)
                    compile_kw = {**compile_kw, "auto_templates": False} if gone else compile_kw
                    continue
        dr.result, dr.text = res, cur
        return dr
    dr.stops.append("the plan still had problems after repairing it 40 times")
    return dr


def format_report(dr: DryRun) -> str:
    """The Check plan text part: what was repaired, and what would stop. (The compile's own plan text follows it in the app.)"""
    lines: List[str] = []
    if dr.repairs:
        lines.append(f"REPAIRED ({len(dr.repairs)}): Generate does the same on its own; your CSV file is not changed")
        lines += [f"  - {r}" for r in dr.repairs[:40]]
        if len(dr.repairs) > 40:
            lines.append(f"  ... and {len(dr.repairs) - 40} more")
    if dr.stops:
        lines += ["WOULD STOP:"] + [f"  ERROR {s}" for s in dr.stops]
    return "\n".join(lines)


def compile_guarded(csv_path: "str | Path", words: Sequence[Word], *, duration: Optional[float] = None, **compile_kw: Any) -> Tuple[Optional[CompileResult], List[str], List[str], bool]:
    """compile_csv, and the guard's repairs only when it is needed: (result, repairs, stops, repaired). The plain compile runs first (the file
    exactly as written); when it fails, or a graphic cannot be drawn, the dry run repairs the CSV in memory and the result comes from that
    (repaired = True: the callers then skip what reads the file by row number)."""
    validate = compile_kw.get("validate", True)
    try:
        res = compile_csv(csv_path, words, duration=duration, **compile_kw)
    except (CsvError, CompileError):
        res = None
    if res is not None:
        checked = check_gfx(res.spec) if validate else {}
        if not any(r.get("fatal") for r in checked.values()):
            return res, [f"graphic {i}: {m}" for i, r in checked.items() for m in r.get("repairs", [])], [], False
    dr = dry_run(csv_path, words, duration=duration, engine=validate, **{k: v for k, v in compile_kw.items() if k != "validate"})
    return dr.result, dr.repairs, dr.stops, True
