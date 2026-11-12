"""Aviation CSV: the War CSV columns plus optional aviation columns (docs/aviation/PLAN.md N12). A plain War-style CSV still reads.

    read_rows(path) -> [row]   row = {scene_number, text, asset_type, queries, graphic, mode, mode_source, airline, aircraft,
                                      from, to, time, fuel, altitude, article, radio, cls}
    prompt_text() -> the prompt that asks a chat model to write this CSV from a script (aviation/data/aviation_csv_prompt.txt)

The CSV is our prompt's output, so its columns are trusted where they are valid; an empty or unknown value falls back to the
narration router (no Gemini: a CSV run makes zero model calls). Places resolve through the catalog (code or city name).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import catalog as C
from . import router as R

COLUMNS = ("scene_number", "script_segment", "asset_type", "prompt", "graphic", "mode", "airline", "aircraft", "from", "to", "time",
           "fuel", "altitude", "article", "radio", "url")
PROMPT_FILE = Path(__file__).resolve().parent / "data" / "aviation_csv_prompt.txt"


def prompt_text() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def _airport_id(v: str) -> str:
    v = (v or "").strip()
    if not v:
        return ""
    if len(v) == 3 and C.get_airport(v.upper()):
        return v.upper()
    m = C.find_airports(v)
    return m[0].entry["id"] if m and m[0].entry else ""


def _int(v: str) -> Optional[int]:
    v = (v or "").strip().lower()
    m = re.match(r"^(?:fl\s*)(\d{2,3})$", v)
    if m:
        return int(m.group(1)) * 100
    m = re.search(r"\d[\d,]*", v)
    return int(m.group(0).replace(",", "")) if m else None


def _time(v: str) -> str:
    vals = R.extract_values(v or "").get("times") or []
    return vals[0] if vals else ""


def _article(v: str) -> Optional[Dict[str, str]]:
    parts = [p.strip() for p in (v or "").split("|")]
    if not any(parts):
        return None
    parts += [""] * 3
    return {"outlet": parts[0], "headline": parts[1], "date": parts[2]}


def _radio(v: str) -> List[Dict[str, str]]:
    out = []
    for call in (v or "").split("||"):
        call = call.strip()
        if not call:
            continue
        m = re.match(r"^([A-Z][A-Z .'\-]{1,30}):\s*(.+)$", call)
        if m:
            out.append({"speaker": m.group(1).strip(), "text": m.group(2).strip()})
        else:
            from .hud import speaker_of
            out.append({"speaker": speaker_of(call), "text": call})
    return out


def read_rows(path: Any) -> List[Dict[str, Any]]:
    p = Path(path)
    raw = p.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(raw.splitlines())
    cols = {(k or "").strip().lower(): k for k in (reader.fieldnames or [])}

    def get(row: dict, name: str) -> str:
        k = cols.get(name)
        return str(row.get(k) or "").strip() if k else ""

    rows: List[Dict[str, Any]] = []
    for i, row in enumerate(reader, 1):
        text = get(row, "script_segment") or get(row, "text")
        if not text:
            continue
        cls = R.classify(text)
        mode_csv = get(row, "mode").lower()
        if mode_csv in R.MODES:
            mode, src = mode_csv, "csv"
        else:
            mode, src = cls.mode, f"router (csv mode '{mode_csv}' unknown)" if mode_csv else "router"
        al = C.find_airlines(get(row, "airline"))
        ac = C.find_aircraft(get(row, "aircraft"))
        rows.append({
            "scene_number": get(row, "scene_number") or str(i),
            "text": text,
            "asset_type": get(row, "asset_type").lower(),
            "queries": [q.strip() for q in get(row, "prompt").split("||") if q.strip()],
            "graphic": get(row, "graphic"),
            "mode": mode,
            "mode_source": src,
            "airline": al[0].entry["id"] if al and al[0].entry else (cls.airlines[0]["id"] if cls.airlines else ""),
            "aircraft": next((m.entry["id"] for m in ac if m.entry), cls.aircraft[0]["id"] if cls.aircraft else ""),
            "from": _airport_id(get(row, "from")),
            "to": _airport_id(get(row, "to")),
            "time": _time(get(row, "time")),
            "fuel": _int(get(row, "fuel")),
            "altitude": _int(get(row, "altitude")),
            "article": _article(get(row, "article")),
            "radio": _radio(get(row, "radio")),
            "url": get(row, "url") if get(row, "url").lower().startswith(("http://", "https://")) else "",
            "cls": cls,
        })
    return rows
