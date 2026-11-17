"""Game Launch scenes CSV -> plan.

One row per shot. A row with narration starts a new voice line; rows under it with the narration cell empty are more shots
over the same line (the line's time is shared between them).

Columns (header names, any case; extra columns are ignored):
  narration   the voice line (empty = another shot of the line above)
  shot        game | real | split | title | chapter | map | board | dossier | timeline | storms
  game_clip   trailer file name in the trailers folder (game, split; title/chapter footage when set)
  game_at     seconds into that trailer where the shot starts
  real        real-life footage: search words (fetched into the Visuals tab) or a video file path (relative to the CSV)
  real_at     seconds into a real file (optional)
  left, right split labels, e.g. VICE CITY / MIAMI
  title, subtitle   big text for title / chapter / map rows
  place       map: "Vice City=Miami@25.77,-80.19" (a pin, zoomed to), or "all" (every pin of the CSV)
              storms: NHC storm ids, "AL041992; AL092022" (their real tracks from NOAA's best track, drawn on the map)

More shot kinds:
  map + game_clip   the region's trailer shot plays in a corner box, tagged with where it was seen ("TRAILER 1 · 0:42")
  board     confirmed / not-confirmed scoreboard: subtitle "Six regions=yes; Map size=no"; an item starting with + is new and
            ticks in one by one (the others are already on the board). game_clip = footage behind it (blurred)
  dossier   character file: title = name, subtitle = "ROLE | one line"; game_clip/game_at = the character; "first seen" is
            written from the trailer and time
  versus    GTA VI | GTA V side by side: game_clip/game_at = the new game's trailer, real = an older game's video FILE (relative to
            the CSV, never fetched), real_at = seconds into it, left/right = labels. A missing file only warns: the new game's
            shot plays full screen until the file is there
  hud       an animated ILLUSTRATION card (title = minimap | stars | heat | tiers | carry | capacity | cash | waink | focus,
            subtitle = its options, e.g. "gta5", "upto=3", "lit=face,outfit", "off=vehicle", "focus=3"); game_clip = background
  tracker   the speed-tracker story on the satellite map (title = heading)
  timeline  dates on a line: subtitle "DEC 2023=Trailer 1; NOV 19 2026=Launch" (the last one is highlighted)

Guide shots (after launch, over your own gameplay recordings put in the same folder as the trailers):
  steps     a walkthrough: game_clip plays sharp, a numbered list on the right lights one step at a time.
            title = heading (default HOW TO DO IT), subtitle "Go to the docs; Steal the boat; Lose the stars"
  rank      one entry of a countdown (top 10 hidden spots, best cars): game_clip full screen, a big #N and the name.
            title = name, subtitle = one line. The numbers count down over the CSV's rank rows (#5, #4 ... #1)
  payout    money methods with a running total: subtitle "Rob the store=$2,400; Sell the car=$9k" (game_clip behind, blurred).
            title = heading (default HOW MUCH YOU MAKE). The total adds up as each one ticks in (no total if a value is not money)
  spot      where something is: game_clip plays, a pulsing ring marks place "x,y" (0-1 of the frame, or percent, "0.62,0.41").
            title = the tag (default IT'S HERE), subtitle = the hint ("Behind the pier, second floor")
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

KINDS = {"game", "real", "split", "title", "chapter", "map", "board", "dossier", "timeline", "storms", "versus", "hud", "tracker", "route",
         "steps", "rank", "payout", "spot"}
GUIDE_KINDS = {"steps", "rank", "payout", "spot"}
STORM_ID = re.compile(r"^(AL|EP|CP)\d{6}$")
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


def parse_items(text: str, board: bool) -> List[Dict[str, Any]]:
    """'Six regions=yes; +Map size=no' -> [{label, value, new}] (board: value True/False; timeline: value = the text after =)."""
    out = []
    for part in str(text or "").split(";"):
        part = part.strip()
        if not part:
            continue
        new = part.startswith("+")
        label, _, val = part.lstrip("+").rpartition("=") if board else part.lstrip("+").partition("=")
        if board and not _:
            label, val = part.lstrip("+"), "yes"
        label, val = label.strip(), val.strip()
        if board:
            out.append({"label": label, "value": val.lower() in ("yes", "y", "true", "1", "confirmed", "ok"), "new": new})
        else:
            out.append({"label": label, "value": val, "new": new})
    return out


def money(text: str) -> Optional[float]:
    """'$2,400' -> 2400, '$9k' -> 9000, '1.2M' -> 1200000; None when it is not an amount."""
    m = re.match(r"^\s*\$?\s*(\d[\d,]*(?:\.\d+)?)\s*([kKmM]?)\s*$", str(text or ""))
    if not m:
        return None
    v = float(m[1].replace(",", ""))
    return v * {"k": 1e3, "m": 1e6}.get(m[2].lower(), 1.0)


def parse_spot(text: str) -> Optional[tuple]:
    """'0.62,0.41' or '62,41' (percent) -> (0.62, 0.41) inside the frame."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*%?\s*[,;\s]\s*(\d+(?:\.\d+)?)\s*%?\s*$", str(text or ""))
    if not m:
        return None
    x, y = float(m[1]), float(m[2])
    if x > 1 or y > 1:
        x, y = x / 100.0, y / 100.0
    return (x, y) if 0 <= x <= 1 and 0 <= y <= 1 else None


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
        if kind == "versus":
            if not shot["game"] or not shot["real"]:
                errors.append(f"row {i}: a versus shot needs game_clip (the new trailer) and real (the older game's video file)")
            else:
                f = Path(shot["real"])
                f = f if f.is_absolute() else path.parent / f
                shot["vs_file"] = str(f)
                if not f.is_file():
                    warnings.append(f"row {i}: older-game clip not there yet: {shot['real']} (the new trailer plays full screen)")
        if kind in ("game", "split") and not shot["game"]:
            errors.append(f"row {i}: a {kind} shot needs game_clip (a trailer file name)")
        if kind in ("real", "split") and not shot["real"]:
            errors.append(f"row {i}: a {kind} shot needs real (search words or a video file)")
        if kind in ("title", "chapter") and not shot["title"]:
            errors.append(f"row {i}: a {kind} shot needs a title")
        if kind in ("title", "chapter") and not (shot["game"] or shot["real"]):
            errors.append(f"row {i}: a {kind} shot needs footage under it (game_clip or real)")
        if kind in ("board", "timeline"):
            shot["items"] = parse_items(shot["subtitle"], board=kind == "board")
            if not shot["items"]:
                errors.append(f"row {i}: a {kind} shot needs items in subtitle, like 'Six regions=yes; Map size=no'")
        if kind == "dossier":
            if not shot["title"] or not shot["game"]:
                errors.append(f"row {i}: a dossier needs a name in title and the character's trailer shot in game_clip")
            role, _, line = shot["subtitle"].partition("|")
            shot["role"], shot["line_text"] = role.strip(), line.strip()
        if kind == "storms":
            ids = [x.strip().upper() for x in re.split(r"[;,\s]+", shot["place"]) if x.strip()]
            bad = [x for x in ids if not STORM_ID.match(x)]
            if not ids or bad:
                errors.append(f"row {i}: storms needs NHC storm ids in place, like 'AL041992; AL092022'")
            shot["storms"] = [x for x in ids if STORM_ID.match(x)]
        if kind == "route":                            # place: "Key Lanto@24.66,-81.5 > Grassrivers@25.6,-80.9 > ..."
            stops = [parse_place(x) for x in shot["place"].split(">")]
            if len(stops) < 2 or any(x is None for x in stops):
                errors.append(f"row {i}: a route needs 2+ stops in place, like 'Key Lanto@24.66,-81.5 > Grassrivers@25.6,-80.9'")
            else:
                shot["stops"] = stops
                for q in stops:
                    if all(r["name"] != q["name"] for r in pins):
                        pins.append(q)
        if kind == "hud":
            from .hud import TEMPLATES
            if shot["title"].strip().lower() not in TEMPLATES:
                errors.append(f"row {i}: hud title must be one of {', '.join(TEMPLATES)}")
        if kind in GUIDE_KINDS and not shot["game"]:
            errors.append(f"row {i}: a {kind} shot needs game_clip (your gameplay recording or a trailer)")
        if kind == "steps":
            shot["items"] = [x.strip() for x in shot["subtitle"].split(";") if x.strip()]
            if not shot["items"]:
                errors.append(f"row {i}: steps needs the steps in subtitle, like 'Go to the docs; Steal the boat'")
            elif len(shot["items"]) > 7:
                warnings.append(f"row {i}: {len(shot['items'])} steps on one shot - more than 7 get small; split it over two rows")
        if kind == "payout":
            shot["items"] = parse_items(shot["subtitle"], board=False)
            if not shot["items"]:
                errors.append(f"row {i}: payout needs items in subtitle, like 'Rob the store=$2,400; Sell the car=$9k'")
            for it in shot["items"]:
                it["amount"] = money(it["value"])
        if kind == "rank" and not shot["title"]:
            errors.append(f"row {i}: a rank shot needs the entry's name in title")
        if kind == "spot":
            shot["spot"] = parse_spot(shot["place"]) or (0.5, 0.5)
            if shot["place"] and not parse_spot(shot["place"]):
                errors.append(f"row {i}: spot place '{shot['place']}' should be x,y inside the frame, like 0.62,0.41")
            elif not shot["place"]:
                warnings.append(f"row {i}: spot has no place - the ring sits in the middle of the frame")
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
    ranks = [s for ln in lines for s in ln["shots"] if s["kind"] == "rank"]
    for k, s in enumerate(ranks):                      # a countdown: the first rank row is the highest number
        s["number"] = f"#{len(ranks) - k}"
    for ln in lines:
        if not ln["shots"]:
            errors.append(f"the line '{ln['text'][:40]}' has no shot")
    if any(s["kind"] == "map" for ln in lines for s in ln["shots"]) and not pins:
        errors.append("map rows need at least one place pin (Name=Real@lat,lon)")
    n = sum(len(ln["shots"]) for ln in lines)
    guide = any(s["kind"] in GUIDE_KINDS for ln in lines for s in ln["shots"])
    if n and not guide and sum(1 for ln in lines for s in ln["shots"] if s["kind"] == "split") == 0:
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
