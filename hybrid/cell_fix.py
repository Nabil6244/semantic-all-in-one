"""Fix a beat CSV one cell at a time. Every problem the importer or the validator finds is traced back to the CSV row and column that
caused it, so the app can show just that cell, suggest values for it, and write the change back into the file (keeping the original).

    cell_for_problem(text, message)        an import problem ("row 13: vo_anchor ...") -> Cell
    cell_for_finding(text, plan, finding)  a validator finding on the imported plan -> Cell
    suggestions(text, cell, words)         up to a few values that would fix it
    set_cell(text, row, column, value)     the CSV with one cell changed
    remove_row(text, row)                  the CSV without one row
    backup(path)                           keep the file as it was first loaded, once

Rows are numbered as a spreadsheet numbers them: the header is row 1."""

from __future__ import annotations

import csv
import io
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

CARD_CORNERS = ("tr", "ml", "br", "bl", "mr")


@dataclass
class Cell:
    row: int            # spreadsheet row number (the header is row 1)
    column: str         # "" when the problem is the whole row (the user picks the column, or removes the row)
    value: str
    cells: Dict[str, str]  # the whole row, for context
    message: str = ""


# ---- reading and writing ------------------------------------------------------------------------------------------------------------

def _rows(text: str) -> List[List[str]]:
    return list(csv.reader(io.StringIO(text.lstrip("﻿"))))


def _write(rows: Sequence[Sequence[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    width = len(rows[0]) if rows else 0
    for r in rows:
        w.writerow(list(r) + [""] * (width - len(r)))
    return buf.getvalue()


def header(text: str) -> List[str]:
    rows = _rows(text)
    return [c.strip().lower() for c in rows[0]] if rows else []


def row_cells(text: str, row: int) -> Dict[str, str]:
    rows = _rows(text)
    head = [c.strip().lower() for c in rows[0]] if rows else []
    if not (2 <= row <= len(rows)):
        return {}
    cells = rows[row - 1]
    return {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(head) if h}


def set_cell(text: str, row: int, column: str, value: str) -> str:
    rows = _rows(text)
    head = [c.strip().lower() for c in rows[0]]
    if column not in head:
        raise ValueError(f"the CSV has no column {column!r}")
    if not (2 <= row <= len(rows)):
        raise ValueError(f"the CSV has no row {row}")
    i = head.index(column)
    r = rows[row - 1]
    r.extend([""] * (i + 1 - len(r)))
    r[i] = value
    return _write(rows)


def remove_row(text: str, row: int) -> str:
    rows = _rows(text)
    if not (2 <= row <= len(rows)):
        raise ValueError(f"the CSV has no row {row}")
    del rows[row - 1]
    return _write(rows)


def backup(path: "str | Path") -> Optional[Path]:
    """Keep the file as it was before the first edit in the app (name.original.csv next to it). Returns the backup's path."""
    p = Path(path)
    keep = p.with_name(p.stem + ".original" + p.suffix)
    if p.is_file() and not keep.exists():
        shutil.copy2(p, keep)
    return keep if keep.exists() else None


# ---- which cell caused a problem ----------------------------------------------------------------------------------------------------

_COLUMN_HINTS = (
    ("vo_anchor", "vo_anchor"), ("words are spoken", "vo_anchor"), ("is only spoken before", "vo_anchor"),
    ("mode must be", "mode"), ("row must be one of", "row"), ("the extra cell", "extra"), ("extra cell", "extra"),
    ("end must be", "end"), ("start must be", "start"), ("a beat row needs a start", "vo_anchor"), ("would end at", "vo_anchor"),
    ("says beat", "beat"), ("beat id", "beat"), ("unknown column", ""),
)


def cell_for_problem(text: str, message: str) -> Optional[Cell]:
    """An import problem names its row ("row 13: ..."); the column comes from what it says."""
    m = re.match(r"\s*row (\d+):", message or "")
    if not m:
        return None
    row = int(m.group(1))
    cells = row_cells(text, row)
    if not cells:
        return None
    low = message.lower()
    column = next((col for hint, col in _COLUMN_HINTS if hint in low), "")
    if not column:
        for col in ("place", "asset", "format", "anchor", "hold", "type", "dur", "value_to"):
            if f"{col} " in low or f"{col}:" in low or f"'{col}'" in low:
                column = col
                break
    return Cell(row=row, column=column, value=cells.get(column, ""), cells=cells, message=message)


def index(text: str) -> Dict[Tuple, int]:
    """Plan object -> CSV row, assigning ids exactly as hybrid.beat_csv.plan_from_csv does: ("beat", id), ("layer", id),
    ("card", beat id, k), ("clip", beat id, k), ("camera", beat id, k)."""
    rows = _rows(text)
    if not rows:
        return {}
    head = [c.strip().lower() for c in rows[0]]
    out: Dict[Tuple, int] = {}
    beat = ""
    counts: Dict[str, int] = {}
    for n, cells in enumerate(rows[1:], start=2):
        r = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(head) if h}
        kind = r.get("row", "").lower()
        if kind == "beat":
            beat = r.get("beat", "")
            counts = {"layer": 0, "card": 0, "clip": 0, "camera": 0}
            out[("beat", beat)] = n
        elif kind in ("layer", "card", "clip", "camera") and beat:
            counts[kind] = counts.get(kind, 0) + 1
            if kind == "layer":
                out[("layer", r.get("id") or f"{beat}_{r.get('type') or 'layer'}{counts['layer']}")] = n
            else:
                out[(kind, beat, counts[kind] - 1)] = n
    return out


def cell_for_finding(text: str, plan, finding) -> Optional[Cell]:
    """A validator finding on a plan imported from `text` -> the cell to change. None when no single cell is at fault
    (for example too many layers at once: several rows share it)."""
    idx = index(text)
    beat = next((b for b in plan.beats if b.id == finding.beat), None)
    if beat is None:
        return None
    msg, code = finding.message, finding.code

    def at(key, column) -> Optional[Cell]:
        n = idx.get(key)
        if n is None:
            return None
        cells = row_cells(text, n)
        return Cell(row=n, column=column, value=cells.get(column, ""), cells=cells, message=msg)

    if code in ("unresolved_place", "fill_not_area"):
        m = re.search(r"place '(.+?)' cannot|but '(.+?)' is a point", msg)
        ref = (m.group(1) or m.group(2)) if m else ""
        if beat.cam_place == ref:
            return at(("beat", beat.id), "place")
        for k, c in enumerate(beat.camera):
            if c.place == ref and ("camera", beat.id, k) in idx:
                return at(("camera", beat.id, k), "place")
        for lay in beat.layers:
            if lay.place == ref or ref in lay.places:
                return at(("layer", lay.id), "place")
        for k, card in enumerate(beat.cards):
            if card.place == ref:
                return at(("card", beat.id, k), "place")
        return None
    if code == "stat_format":
        m = re.search(r"number format '(.*?)' writes", msg)
        for lay in beat.layers:
            if lay.type == "stat" and m and lay.format == m.group(1):
                return at(("layer", lay.id), "format")
        return None
    if code == "map_no_geography":
        return at(("beat", beat.id), "place")
    if code == "footage_too_short":
        return at(("beat", beat.id), "vo_anchor")
    return None


# ---- what would fix it --------------------------------------------------------------------------------------------------------------

def suggest_places(query: str, n: int = 3) -> List[str]:
    """Names the atlas knows that look like `query` (countries, states and provinces, named regions, then cities)."""
    from pakmap.geo import suggest_names

    return suggest_names(query, n)


def suggestions(text: str, cell: Cell, words: Sequence = ()) -> List[str]:
    col, value = cell.column, cell.value
    out: List[str] = []
    if col == "place":
        out += suggest_places(value)
        rows = _rows(text)
        head = [c.strip().lower() for c in rows[0]] if rows else []
        if "place" in head and "row" in head:
            pi, ri = head.index("place"), head.index("row")
            for cells in reversed(rows[1:cell.row - 1]):   # the previous beat's place: the camera simply stays
                if len(cells) > max(pi, ri) and cells[ri].strip().lower() == "beat" and cells[pi].strip():
                    out.append(cells[pi].strip())
                    break
    elif col == "vo_anchor" and words:
        from pakmap.anchor import Transcript

        near = Transcript(list(words)).nearest(value.split("|")[0].strip())
        if near:
            out.append(near[0])
    elif col == "anchor":
        out += [c for c in CARD_CORNERS if c != value]
    elif col == "mode":
        out += [m for m in ("map", "map_footage", "footage") if m != value]
    elif col == "format":
        fixed = re.sub(r"\d[\d,]*(?:\.\d+)?", lambda m: "0.0" if "." in m.group(0) else "0", value, count=1)
        if fixed != value:
            out.append(fixed)
    elif col == "asset" and value and ":" not in value:
        out.append("stock_image:" + value)
    seen: List[str] = []
    for s in out:
        if s and s != value and s not in seen:
            seen.append(s)
    return seen[:4]
