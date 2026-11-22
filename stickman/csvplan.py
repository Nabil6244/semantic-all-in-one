"""The Stickman CSV: one row per spoken line, every other cell optional.

Columns (header row required, any order, case does not matter):
  line     what the narrator says on this row (the rows joined = the whole script)   REQUIRED
  action   a pose, optionally for one figure: "cheer", "friend:shrug", "lead:walk"
  props    props and where: "cup", "cup@side, zzz@above", "clock@ground"
  place    bedroom, kitchen, office, street, park, city_night, classroom, void
  text     a big word card at the top while this row is spoken ("3 HOURS")
  camera   wide | medium | close
  sfx      pop, whoosh, boing, sparkle, burst, chime, success, drumroll, ding_1 .. ding_10
  look     (first row only) the whole video's look: ink_paper, chalk_dark, colour_pop, retro_tv, night_thriller, meme;
           add "+host" for your picture as a presenter in the corner ("meme+host", "ink_paper+host:girl")
Empty cells are filled by the director, so a CSV can be as small as one 'line' column.
"""
import csv
import io
from pathlib import Path

from . import looks, places, poses, props

COLUMNS = ("line", "action", "props", "place", "text", "camera", "sfx", "look")
CAMERAS = ("wide", "medium", "close")
SFX = ("pop", "whoosh", "boing", "sparkle", "burst", "chime", "success", "drumroll") + tuple(f"ding_{i}" for i in range(1, 11))
WHERE = ("side", "above", "ground", "hand_f", "hand_b", "hands", "face")
WHO = {"lead": "lead", "you": "lead", "friend": "other", "other": "other"}


class CsvError(ValueError):
    pass


def _parse_props(cell, problems, n):
    out = []
    for part in [p.strip() for p in (cell or "").split(",") if p.strip()]:
        name, _, where = part.partition("@")
        name, where = name.strip().lower(), (where.strip().lower() or "")
        if name not in props.PROPS:
            problems.append(f"row {n}: unknown prop '{name}'")
            continue
        if where and where not in WHERE:
            problems.append(f"row {n}: unknown place for a prop '{where}' (use {', '.join(WHERE)})")
            where = ""
        out.append({"name": name, "at": where or None})
    return out


def read(path_or_text):
    """-> (rows, problems). Rows keep only valid values; problems are plain sentences (unknown names are skipped, never fatal)."""
    text = Path(path_or_text).read_text(encoding="utf-8-sig") if "\n" not in str(path_or_text) and Path(str(path_or_text)).is_file() \
        else str(path_or_text)
    rd = csv.DictReader(io.StringIO(text))
    if not rd.fieldnames or "line" not in [f.strip().lower() for f in rd.fieldnames]:
        raise CsvError("the Stickman CSV needs a header row with a 'line' column")
    rows, problems = [], []
    for n, raw in enumerate(rd, 2):
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        line = r.get("line", "")
        if not line:
            continue
        row = {"line": line}
        act = r.get("action", "").lower()
        if act:
            who, _, pose = act.rpartition(":")
            pose = pose.strip()
            if pose not in poses.ALL:
                problems.append(f"row {n}: unknown action '{pose}'")
            else:
                row["action"] = pose
                if who.strip():
                    if who.strip() not in WHO:
                        problems.append(f"row {n}: unknown figure '{who}' (use lead or friend)")
                    else:
                        row["who"] = WHO[who.strip()]
        pr = _parse_props(r.get("props", ""), problems, n)
        if pr:
            row["props"] = pr
        pl = r.get("place", "").lower()
        if pl:
            if pl in places.PLACES:
                row["place"] = pl
            else:
                problems.append(f"row {n}: unknown place '{pl}'")
        if r.get("text"):
            row["text"] = r["text"][:24]
        cam = r.get("camera", "").lower()
        if cam:
            if cam in CAMERAS:
                row["camera"] = cam
            else:
                problems.append(f"row {n}: camera must be wide, medium or close")
        fx = r.get("sfx", "").lower()
        if fx:
            if fx in SFX:
                row["sfx"] = fx
            else:
                problems.append(f"row {n}: unknown sound '{fx}'")
        for lk in [x.strip() for x in r.get("look", "").lower().split("+") if x.strip()]:
            if lk == "host" or lk.startswith("host:"):
                from . import host as _host
                name = lk.partition(":")[2].strip() or next(iter(_host.hosts()), "")
                if name in _host.hosts():
                    row["host"] = name
                else:
                    problems.append(f"row {n}: no host picture '{name}'")
            elif lk in looks.LOOKS:
                row["look"] = lk
            else:
                problems.append(f"row {n}: unknown look '{lk}'")
        rows.append(row)
    if not rows:
        raise CsvError("the Stickman CSV has no lines")
    return rows, problems


def script_of(rows):
    return " ".join(r["line"] for r in rows)


def look_of(rows):
    return next((r["look"] for r in rows if r.get("look")), None)


def host_of(rows):
    return next((r["host"] for r in rows if r.get("host")), None)


def from_plan(spec):
    """A directed plan back to a Stickman CSV (one row per beat), so a video can be tuned by hand and made again."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    for k, b in enumerate(spec["beats"]):
        acts = b.get("acts") or {}
        actor = b.get("actor", "lead")
        act = acts.get(actor, {})
        a = act.get("then") if act.get("do") in ("walk", "run", "sneak") and act.get("then") else act.get("do", "")
        if a and actor != "lead":
            a = f"friend:{a}"
        pr = ", ".join(f"{p['name']}@{p.get('at', 'side')}" for p in b.get("props") or [])
        w.writerow([" ".join(x["w"] for x in b.get("words") or []) or b.get("caption", "").replace("*", ""),
                    a, pr, b.get("place", ""), b.get("text", ""), (b.get("camera") or {}).get("kind", ""), "",
                    (spec.get("look", "") + (f"+host:{spec['host']['name']}" if spec.get("host") else "")) if k == 0 else ""])
    return buf.getvalue()
