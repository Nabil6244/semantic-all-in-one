"""Scenes CSV for Health Cinema: one row per narration sentence -> the same scene dicts the scenes JSON gives ({text, start, end, sources?, footage?, chapter?}).

Columns (header names are case-insensitive; `,` `;` or tab separated; Excel/Sheets exports with a BOM are fine):
  text (required; also: narration, sentence, script)   start, end (optional, seconds or m:ss; all rows or none)   chapter   footage
  source_title, source_citation, source_url, source_year, source_population, source_context   several sources in one row are separated by ` | `, lined up by position.
Without start/end the rows are aligned to the voiceover's own word times (`align_to_words`), so the timings are the real ones, not estimates.
Nothing here invents text, numbers or sources: it only reads and validates what the file holds.
"""
from __future__ import annotations

import csv
import difflib
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ALIASES = {"text": ("text", "narration", "sentence", "script"), "start": ("start", "start_s", "start_time"), "end": ("end", "end_s", "end_time"),
           "chapter": ("chapter", "section"), "footage": ("footage", "footage_query", "clip")}
SOURCE_FIELDS = ("title", "citation", "url", "year", "population", "context")
MIN_MATCH = 0.5      # below this share of script words found in the voiceover, the CSV is not this narration
WARN_MATCH = 0.8
_TOK = re.compile(r"[a-z0-9%']+")


def _tokens(t: str) -> List[str]:
    return _TOK.findall(t.lower())


def parse_time(raw: str, where: str) -> float:
    """'12.5', '1:02', '1:02.5' or '0:01:02.5' -> seconds."""
    s = (raw or "").strip()
    try:
        parts = [float(p) for p in s.split(":")]
    except ValueError:
        raise ValueError(f"{where}: '{raw}' is not a time (use seconds like 12.5 or minutes:seconds like 1:02)") from None
    if not 1 <= len(parts) <= 3 or any(p < 0 for p in parts):
        raise ValueError(f"{where}: '{raw}' is not a time (use seconds like 12.5 or minutes:seconds like 1:02)")
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def _split(cell: str) -> List[str]:
    return [p.strip() for p in (cell or "").split("|")]


def _sources(row: Dict[str, str], where: str) -> List[dict]:
    cols = {f: _split(row.get(f"source_{f}", "")) for f in SOURCE_FIELDS}
    n = max((len(v) for v in cols.values() if any(v)), default=0)
    out: List[dict] = []
    for i in range(n):
        src: Dict[str, Any] = {}
        for f in SOURCE_FIELDS:
            v = cols[f][i] if i < len(cols[f]) else ""
            if not v:
                continue
            if f == "year":
                if not re.fullmatch(r"\d{4}", v):
                    raise ValueError(f"{where}: source_year '{v}' must be a 4-digit year")
                src[f] = int(v)
            else:
                src[f] = v
        if src.get("title") or src.get("citation") or src.get("url"):
            out.append(src)
        elif src:
            raise ValueError(f"{where}: source {i + 1} has details but no title, citation or url")
    return out


def _header_map(fields: Sequence[str]) -> Dict[str, str]:
    norm = {re.sub(r"[\s\-]+", "_", (f or "").strip().lower()): f for f in fields}
    out: Dict[str, str] = {}
    for key, names in ALIASES.items():
        for n in names:
            if n in norm:
                out[key] = norm[n]
                break
    for f in SOURCE_FIELDS:
        if f"source_{f}" in norm:
            out[f"source_{f}"] = norm[f"source_{f}"]
    return out


def parse_csv_text(content: str) -> List[dict]:
    """Rows -> [{text, start?, end?, chapter?, footage?, sources?}]. `start`/`end` are present on every row or on none. Raises ValueError naming the row."""
    content = content.lstrip("﻿")
    if not content.strip():
        raise ValueError("the scenes CSV is empty")
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    hm = _header_map(reader.fieldnames or [])
    if "text" not in hm:
        raise ValueError("the scenes CSV needs a 'text' column (also accepted: narration, sentence, script); found: " + ", ".join(reader.fieldnames or ["nothing"]))
    rows: List[dict] = []
    for lineno, raw in enumerate(reader, start=2):
        row = {k: (raw.get(col) or "").strip() for k, col in hm.items()}
        if not any(row.values()):
            continue
        where = f"row {lineno}"
        if not row["text"]:
            raise ValueError(f"{where}: the text is empty")
        sc: Dict[str, Any] = {"text": " ".join(row["text"].split())}
        if row.get("start") or row.get("end"):
            if not (row.get("start") and row.get("end")):
                raise ValueError(f"{where}: give both start and end, or neither")
            sc["start"], sc["end"] = parse_time(row["start"], f"{where} start"), parse_time(row["end"], f"{where} end")
            if sc["end"] <= sc["start"]:
                raise ValueError(f"{where}: end ({row['end']}) must be after start ({row['start']})")
        for k in ("chapter", "footage"):
            if row.get(k):
                sc[k] = row[k]
        src = _sources(row, where)
        if src:
            sc["sources"] = src
        rows.append(sc)
    if not rows:
        raise ValueError("the scenes CSV has a header but no rows")
    timed = [("start" in r) for r in rows]
    if any(timed) and not all(timed):
        first_missing = timed.index(False) + 2
        raise ValueError(f"start/end are filled on some rows but not row {first_missing}: fill them on every row, or clear them on all rows to align to the voiceover")
    prev_end = None
    for i, r in enumerate(rows):
        if "start" in r:
            if prev_end is not None and r["start"] < prev_end - 0.05:
                raise ValueError(f"row {i + 2}: starts at {r['start']:.1f}s, before the previous row ends ({prev_end:.1f}s)")
            prev_end = r["end"]
    for i, r in enumerate(rows, start=1):
        r["scene_no"] = i
    return rows


def read_scenes_csv(path: str) -> List[dict]:
    raw = Path(path).read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252")      # older Excel exports
    return parse_csv_text(content)


def needs_alignment(rows: Sequence[dict]) -> bool:
    return bool(rows) and "start" not in rows[0]


def align_to_words(rows: Sequence[dict], words: Sequence[Any], total_s: float = 0.0):
    """Untimed rows + the voiceover's word times [(word, start, end), ...] -> (timed scene dicts, matched share). The scenes are contiguous and each carries its own `words`.
    Rows are matched to the transcript by their words, in order; a row the transcript missed is placed between its neighbours. Raises ValueError if the
    script is clearly not what the voiceover says."""
    wl: List[dict] = []
    for item in words or []:
        try:
            wl.append({"w": str(item[0]), "t0": float(item[1]), "t1": float(item[2])})
        except (TypeError, ValueError, IndexError):
            continue
    if not wl:
        raise ValueError("the voiceover has no recognised words to align the scenes CSV to")
    wtok, widx = [], []                                   # transcript tokens -> index of the word they came from
    for i, w in enumerate(wl):
        for tk in _tokens(w["w"]):
            wtok.append(tk)
            widx.append(i)
    stok, srow = [], []
    for r_i, r in enumerate(rows):
        for tk in _tokens(r["text"]):
            stok.append(tk)
            srow.append(r_i)
    if not stok:
        raise ValueError("the scenes CSV has no words")
    match: Dict[int, int] = {}                            # script token -> transcript token
    for blk in difflib.SequenceMatcher(None, stok, wtok, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            match[blk.a + k] = blk.b + k
    frac = len(match) / len(stok)
    if frac < MIN_MATCH:
        raise ValueError(f"only {frac:.0%} of the CSV's words are in the voiceover: this CSV does not look like this narration (check the voiceover file, or fill start and end)")
    first: List[Optional[int]] = [None] * len(rows)       # transcript word index at each row's first/last matched token
    last: List[Optional[int]] = [None] * len(rows)
    for si, wi in sorted(match.items()):
        r = srow[si]
        w = widx[wi]
        if first[r] is None:
            first[r] = w
        last[r] = w
    n_words = len(wl)
    starts: List[float] = [0.0] * len(rows)
    for i in range(len(rows)):
        if first[i] is not None:
            starts[i] = float(first[i])
    known = [i for i in range(len(rows)) if first[i] is not None]
    for i in range(len(rows)):                            # unmatched rows: share the gap between known neighbours by their word counts
        if first[i] is not None:
            continue
        lo = max((k for k in known if k < i), default=None)
        hi = min((k for k in known if k > i), default=None)
        a = (last[lo] + 1) if lo is not None else 0
        b = float(first[hi]) if hi is not None else float(n_words)
        run = [j for j in range(lo + 1 if lo is not None else 0, hi if hi is not None else len(rows)) if first[j] is None]
        weights = [max(1, len(_tokens(rows[j]["text"]))) for j in run]
        before = sum(weights[:run.index(i)])
        starts[i] = a + (b - a) * before / sum(weights)
    for i in range(1, len(rows)):                         # rows stay in order
        starts[i] = max(starts[i], starts[i - 1])
    starts[0] = 0.0
    out: List[dict] = []
    for i, r in enumerate(rows):
        a = int(starts[i])
        b = int(starts[i + 1]) if i + 1 < len(rows) else n_words
        chunk = wl[a:max(b, a + 1)] if a < n_words else wl[-1:]
        sc = {k: v for k, v in r.items()}
        sc["words"] = [dict(w) for w in chunk]
        sc["start"] = chunk[0]["t0"] if i else 0.0
        sc["end"] = chunk[-1]["t1"]
        out.append(sc)
    for i, sc in enumerate(out):                          # contiguous in time, like the transcript-cut sentences
        sc["end"] = out[i + 1]["start"] if i + 1 < len(out) else max(sc["end"], float(total_s or 0.0))
        if sc["end"] <= sc["start"]:
            sc["end"] = sc["start"] + 0.3
    return out, frac


def match_note(frac: float) -> str:
    return f"{frac:.0%} of the CSV's words matched the voiceover" + ("" if frac >= WARN_MATCH else ": some scenes were placed by estimate, check their timing")
