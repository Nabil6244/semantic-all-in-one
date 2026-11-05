"""Rules Horror CSV reader (lenient). Format (docs/rules_horror/PLAN.md):

    #subject,deer,"tall deer, long thin legs, antlers"
    #location,house,yard
    order,section,line,set,shot,subject,pose,action,tag,value,prompt
    1,hook,If you ever wake up at three in the morning,bedroom,wide,,,figure_sleep,,3:00 AM,

A BOM, extra spaces, blank lines, missing columns and a missing `order` are fine. Returns {"meta": {...}, "rows": [...], "notes": [...]}."""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any, Dict, List

COLS = ("order", "section", "line", "set", "shot", "subject", "pose", "action", "tag", "value", "prompt", "mood")
SET_ALIASES = {"house": "house_section", "room": "bedroom", "bed": "bedroom", "garden": "yard", "outside": "yard", "hall": "hallway",
               "corridor": "hallway", "school": "classroom", "windowsill": "window", "front_door": "door", "stair": "stairs", "staircase": "stairs",
               "lit_hall": "hall_lit", "lit_hallway": "hall_lit", "lamp": "street", "road": "street", "night_street": "street", "cutaway": "cutaway",
               "cross_section": "cutaway", "house_cutaway": "cutaway", "section": "cutaway", "theatre": "cinema", "theater": "cinema", "audience": "crowd",
               "bath": "bathroom", "toilet": "bathroom", "washroom": "bathroom", "mirror_hall": "hall_mirror", "hallway_mirror": "hall_mirror", "shop": "store", "aisle": "store", "supermarket": "store", "shelves": "store", "paper": "prop", "object": "prop", "document": "prop", "phone": "prop"}
SHOTS = ("wide", "push_in", "pull_out", "static")
SHOT_ALIASES = {"push": "push_in", "pushin": "push_in", "zoom_in": "push_in", "pull": "pull_out", "pullout": "pull_out", "zoom_out": "pull_out",
                "still": "static", "medium": "wide", "close": "push_in"}


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace("﻿", "")).strip()


def read_csv(path) -> Dict[str, Any]:
    if isinstance(path, io.StringIO):
        return parse_csv_text(path.getvalue())
    return parse_csv_text(Path(path).read_text(encoding="utf-8-sig", errors="replace"))


def parse_csv_text(text: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    notes: List[str] = []
    body: List[str] = []
    for line in text.replace("﻿", "").splitlines():
        raw = line.strip()
        if raw.startswith("#"):
            vals = [_norm(v) for v in next(csv.reader([raw[1:]]), [])]
            if vals and vals[0]:
                meta[vals[0].lower()] = vals[1:] if len(vals) > 2 else (vals[1] if len(vals) > 1 else "")
            continue
        if raw:
            body.append(line)
    rows: List[Dict[str, Any]] = []
    if not body:
        return {"meta": meta, "rows": rows, "notes": ["the CSV has no rows"]}
    head = [_norm(h).lower() for h in next(csv.reader([body[0]]))]
    if "line" in head or "order" in head:
        cols, data = head, body[1:]
    else:   # no header: the standard columns in order
        cols, data = list(COLS), body
        notes.append("no header row: the standard columns were assumed")
    for n, rec in enumerate(csv.reader(data), 1):
        if not any(_norm(c) for c in rec):
            continue
        r = {c: "" for c in COLS}
        for c, v in zip(cols, rec):
            if c in r:
                r[c] = _norm(v)
        try:
            r["order"] = float(r["order"]) if r["order"] else float(n)
        except ValueError:
            notes.append(f"row {n}: order '{r['order']}' is not a number; row position used")
            r["order"] = float(n)
        s = r["set"].lower().replace(" ", "_")
        r["set"] = SET_ALIASES.get(s, s)
        sh = r["shot"].lower().replace(" ", "_").replace("-", "_")
        sh = SHOT_ALIASES.get(sh, sh)
        if sh and sh not in SHOTS:
            notes.append(f"row {n}: shot '{r['shot']}' is not known; 'wide' used")
            sh = "wide"
        r["shot"] = sh or "wide"
        r["action"] = r["action"].lower().replace(" ", "_")
        r["pose"] = r["pose"].lower().replace(" ", "_")
        r["subject"] = r["subject"].lower()
        rows.append(r)
    rows.sort(key=lambda r: r["order"])
    if not any(r["line"] for r in rows):
        notes.append("no row has a voice-over line; the rows are spread evenly over the voice")
    return {"meta": meta, "rows": rows, "notes": notes}
