"""Game Launch scenes CSV -> plan.

One row per shot. A row with narration starts a new voice line; rows under it with the narration cell empty are more shots
over the same line (the line's time is shared between them).

Columns (header names, any case; extra columns are ignored):
  narration   the voice line (empty = another shot of the line above)
  shot        game | real | split | title | chapter | map
  game_clip   trailer file name in the trailers folder (game, split; title/chapter footage when set)
  game_at     seconds into that trailer where the shot starts
  real        real-life footage: search words (fetched into the Visuals tab) or a video file path (relative to the CSV)
  real_at     seconds into a real file (optional)
  left, right split labels, e.g. VICE CITY / MIAMI
  title, subtitle   big text for title / chapter / map rows
  place       map: "Vice City=Miami@25.77,-80.19" (a pin, zoomed to), or "all" (every pin of the CSV)
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

KINDS = {"game", "real", "split", "title", "chapter", "map"}
ALIASES = {"headline": "title", "card": "title", "side_by_side": "split", "vs": "split", "compare": "split",
           "stock": "real", "footage": "real", "trailer": "game"}
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".webm", ".m4v")
_PLACE = re.compile(r"^\s*(?P<name>[^=@]+?)\s*(?:=\s*(?P<real>[^@]+?))?\s*@\s*(?P<lat>-?\d+(?:\.\d+)?)\s*,\s*(?P<lon>-?\d+(?:\.\d+)?)\s*$")


def _num(v: Any) -> Optional[float]:
    s = str(v or "").strip().replace("s", "")
    if not s:
        return None
    if ":" in s:                           # 1:23.5 -> 83.5
        m, _, sec = s.partition(":")
        try:
            return float(m) * 60 + float(sec)
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_place(s: str) -> Optional[Dict[str, Any]]:
    m = _PLACE.match(str(s or ""))
    if not m:
        return None
    return {"name": m["name"].strip(), "real": (m["real"] or "").strip(), "lat": float(m["lat"]), "lon": float(m["lon"])}


def read(csv_path: str) -> Dict[str, Any]:
    """{"lines": [{"text", "shots": [...]}], "pins": [...], "errors": [...], "warnings": [...]}. Never raises on bad rows."""
    path = Path(csv_path)
    errors: List[str] = []
    warnings: List[str] = []
    lines: List[Dict[str, Any]] = []
    pins: List[Dict[str, Any]] = []
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001
        return {"lines": [], "pins": [], "errors": [f"cannot read the CSV: {exc}"], "warnings": []}
    rows = list(csv.DictReader(raw.splitlines()))
    if not rows:
        return {"lines": [], "pins": [], "errors": ["the CSV has no rows"], "warnings": []}
    chapter_no = 0
    scene_no = 0
    for i, r in enumerate(rows, start=2):
        extra = r.pop(None, None) or []                # an unquoted "lat,lon" in the last column spills over: join it back
        r = {str(k or "").strip().lower(): str(v or "").strip() for k, v in r.items()}
        if extra and "place" in r:
            r["place"] = ",".join([r["place"]] + [str(x).strip() for x in extra]).strip(",")
        text = r.get("narration", "")
        kind = ALIASES.get(r.get("shot", "").lower(), r.get("shot", "").lower())
        if not kind and not text:
            continue                                   # blank row
        if kind not in KINDS:
            errors.append(f"row {i}: shot '{r.get('shot', '')}' is not one of {', '.join(sorted(KINDS))}")
            continue
        if text:
            lines.append({"text": text, "shots": []})
        elif not lines:
            errors.append(f"row {i}: the first row needs narration")
            continue
        shot: Dict[str, Any] = {"kind": kind, "row": i,
                                "game": r.get("game_clip", ""), "game_at": _num(r.get("game_at")) or 0.0,
                                "real": r.get("real", ""), "real_at": _num(r.get("real_at")) or 0.0,
                                "left": r.get("left", "").upper(), "right": r.get("right", "").upper(),
                                "title": r.get("title", ""), "subtitle": r.get("subtitle", ""), "place": r.get("place", "")}
        if kind in ("game", "split") and not shot["game"]:
            errors.append(f"row {i}: a {kind} shot needs game_clip (a trailer file name)")
        if kind in ("real", "split") and not shot["real"]:
            errors.append(f"row {i}: a {kind} shot needs real (search words or a video file)")
        if kind in ("title", "chapter") and not shot["title"]:
            errors.append(f"row {i}: a {kind} shot needs a title")
        if kind in ("title", "chapter") and not (shot["game"] or shot["real"]):
            errors.append(f"row {i}: a {kind} shot needs footage under it (game_clip or real)")
        if kind == "chapter":
            chapter_no += 1
            shot["number"] = f"{chapter_no:02d}"
        if kind == "map":
            p = parse_place(shot["place"])
            if p:
                shot["pin"] = p
                if all(q["name"] != p["name"] for q in pins):
                    pins.append(p)
            elif shot["place"].lower() not in ("", "all"):
                errors.append(f"row {i}: place '{shot['place']}' should look like Vice City=Miami@25.77,-80.19 (or 'all')")
        if shot["real"] and kind in ("real", "split", "title", "chapter"):
            scene_no += 1
            shot["scene_no"] = scene_no
            shot["real_is_file"] = shot["real"].lower().endswith(VIDEO_EXT)
            if shot["real_is_file"]:
                f = Path(shot["real"])
                f = f if f.is_absolute() else path.parent / f
                shot["real_file"] = str(f)
                if not f.is_file():
                    errors.append(f"row {i}: the real clip file is not there: {shot['real']}")
        lines[-1]["shots"].append(shot)
    for ln in lines:
        if not ln["shots"]:
            errors.append(f"the line '{ln['text'][:40]}' has no shot")
    if any(s["kind"] == "map" for ln in lines for s in ln["shots"]) and not pins:
        errors.append("map rows need at least one place pin (Name=Real@lat,lon)")
    n = sum(len(ln["shots"]) for ln in lines)
    if n and sum(1 for ln in lines for s in ln["shots"] if s["kind"] == "split") == 0:
        warnings.append("no split shots: the side-by-side game vs real comparison is the style's main shot")
    return {"lines": lines, "pins": pins, "errors": errors, "warnings": warnings}


def visual_scenes(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Visuals-tab rows, one per shot with real footage. A file named in the CSV is seeded as that row's clip first, so only the
    search-word rows are fetched; every row can be changed in the Visuals tab."""
    out = []
    for ln in plan["lines"]:
        for s in ln["shots"]:
            if s.get("scene_no"):
                q = Path(s["real"]).stem.replace("_", " ") if s.get("real_is_file") else s["real"]
                out.append({"scene_no": s["scene_no"], "text": ln["text"], "asset_type": "stock_video",
                            "prompt": q, "stock": q, "start": 0.0, "end": 0.0})
    return out


def local_files(plan: Dict[str, Any]) -> Dict[int, str]:
    return {s["scene_no"]: s["real_file"] for ln in plan["lines"] for s in ln["shots"] if s.get("real_is_file") and s.get("real_file")}
