"""The clip CSV: the plan of a Podcast Cut video, one row per kept stretch of the episode.

    n, role, start, end, length, score, text
    role   hook (played first, once) | body | question (a host question kept for its answer)
    start / end   H:MM:SS.ss in the episode (plain seconds, M:SS and MM:SS.ss are read too)

It can be edited by hand or written by Claude from a transcript. When the user gives one, it IS the plan: the
picker is skipped and no Gemini call is made.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import List

from .picker import Clip

COLS = ["n", "role", "start", "end", "length", "score", "text"]
ROLES = ("hook", "body", "question")


def fmt_time(t: float) -> str:
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def parse_time(v) -> float:
    s = str(v or "").strip()
    if not s:
        raise ValueError("empty time")
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    parts = s.split(":")
    if len(parts) > 3 or not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        raise ValueError(f"bad time {s!r} (use H:MM:SS.ss, M:SS or seconds)")
    val = 0.0
    for p in parts:
        val = val * 60 + float(p)
    return val


def write(clips: List[Clip], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for k, c in enumerate(clips, 1):
            w.writerow([k, c.role, fmt_time(c.start), fmt_time(c.end), f"{c.length:.1f}", f"{c.score:.2f}", c.text])
    return path


def read(path: Path) -> List[Clip]:
    """Rows in file order. Raises ValueError naming the row for anything unreadable."""
    clips: List[Clip] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        heads = {(h or "").strip().lower() for h in (rd.fieldnames or [])}
        if not {"start", "end"} <= heads:
            raise ValueError("The clip CSV needs at least the columns start and end (and usually role and text).")
        for k, row in enumerate(rd, 2):
            row = {(a or "").strip().lower(): (b or "").strip() for a, b in row.items()}
            if not row.get("start") and not row.get("end"):
                continue
            try:
                s, e = parse_time(row.get("start")), parse_time(row.get("end"))
            except ValueError as exc:
                raise ValueError(f"line {k}: {exc}") from None
            role = (row.get("role") or "body").lower()
            if role not in ROLES:
                raise ValueError(f"line {k}: role {role!r} must be one of {', '.join(ROLES)}")
            try:
                sc = float(row.get("score") or 0)
            except ValueError:
                sc = 0.0
            clips.append(Clip(role=role, start=s, end=e, text=row.get("text", ""), score=sc))
    return clips
