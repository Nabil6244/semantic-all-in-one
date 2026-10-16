"""What If never stops on a shot CSV: every row an AI (or a person) can get wrong is repaired here, or left out with a note.

The same idea as Weather's guard and StarMap's heal: the CSV the user gave is never changed on disk; this works on a copy in memory.
`heal(text)` fixes what can be fixed with certainty (a semicolon CSV, a missing header, "photo" for "image", "nasa" for
"nasa_image", a misspelled template id, a broken extra cell, units in a number column ...). `plan_rows` then reads the healed CSV
with the strict reader; any row the reader still refuses is left out (and named in the notes) and the CSV is read again, so one
bad row never costs the whole plan. Only when no shot is left at all does the plan fall back to the narration-only planner.
"""

from __future__ import annotations

import csv
import difflib
import io
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .shot_csv import ASSET_SOURCES, COLUMNS, HERO_SCENES, KINDS, LAYER_TYPES, PlanError, craft_model, read_shots, world_texture

ROW_ALIASES = {"plan": "plan", "title": "plan", "video": "plan", "shot": "shot", "scene": "shot", "clip": "shot", "beat": "shot", "picture": "shot",
               "layer": "layer", "graphic": "layer", "overlay": "layer", "text": "layer", "hud": "layer", "diagram": "layer", "template": "layer"}
KIND_ALIASES = {"photo": "image", "picture": "image", "still": "image", "img": "image", "illustration": "image", "flow_image": "image",
                "clip": "video", "footage": "video", "film": "video", "movie": "video", "flow_video": "video", "animation": "video",
                "diagram": "plate", "chart": "plate", "graphic": "plate", "dark": "plate", "slate": "plate",
                "model": "craft", "3d": "craft", "spacecraft": "craft", "probe": "craft", "planet": "globe", "world": "globe",
                "scene": "hero", "cg": "hero", "blackout": "black", "silence": "black", "fade": "black"}
SOURCE_ALIASES = {"nasa": "nasa_image", "nasa_photo": "nasa_image", "nasa_clip": "nasa_video", "flow": "flow_image", "ai": "flow_image", "ai_image": "flow_image",
                  "ai_video": "flow_video", "stock": "stock_image", "pexels": "stock_image", "youtube": "youtube_video", "commons": "commons_image",
                  "wikimedia": "commons_image", "archive": "archive_video", "local": "file", "path": "file"}
LAYER_ALIASES = {"number": "metric", "stat": "metric", "callout": "metric", "value": "metric", "chart": "diagram", "graph": "diagram",
                 "card": "title", "heading": "title", "label": "caption", "text": "caption", "lower_third": "caption", "instrument": "hud",
                 "clock": "hud", "gauge": "hud", "ring": "annotate", "circle": "annotate", "visual": "template", "tpl": "template",
                 "blackout": "fade", "fade_out": "fade"}
NUMBER_COLS = ("value_from", "value_to", "hold", "t", "end")


def _rows(text: str) -> Tuple[List[str], List[List[str]], List[str]]:
    notes: List[str] = []
    text = (text or "").lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    first = next((ln for ln in text.split("\n") if ln.strip()), "")
    delim = ","
    if first.count(";") > first.count(",") and first.count(";") >= 3:
        delim = ";"
    elif first.count("\t") >= 3:
        delim = "\t"
    if delim != ",":
        notes.append(f"the CSV used {'semicolons' if delim == ';' else 'tabs'} between columns; read as a normal CSV")
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    if not rows:
        return list(COLUMNS), [], notes
    head = [re.sub(r"[^a-z_]", "", h.strip().lower().replace(" ", "_")) for h in rows[0]]
    if "row" not in head:
        if rows[0] and rows[0][0].strip().lower() in ROW_ALIASES:
            notes.append("the CSV had no header row; the What If columns were assumed")
            return list(COLUMNS), rows, notes
        head[0] = "row"
    return head, rows[1:], notes


def _close(word: str, choices: Sequence[str], cutoff: float = 0.72) -> Optional[str]:
    w = (word or "").strip().lower().replace(" ", "_").replace("-", "_")
    if w in choices:
        return w
    hit = difflib.get_close_matches(w, list(choices), n=1, cutoff=cutoff)
    return hit[0] if hit else None


def _json_cell(cell: str) -> Tuple[str, Optional[str]]:
    """-> (a valid JSON object text, a note when it had to be repaired or dropped)."""
    c = (cell or "").strip()
    if not c:
        return "", None
    try:
        v = json.loads(c)
        return (c, None) if isinstance(v, dict) else ("", "extra was not a JSON object; ignored")
    except ValueError:
        pass
    fixed = re.sub(r",\s*([}\]])", r"\1", c.replace("“", '"').replace("”", '"').replace("'", '"'))
    if not fixed.startswith("{"):
        fixed = "{" + fixed + "}"
    try:
        v = json.loads(fixed)
        if isinstance(v, dict):
            return json.dumps(v), "extra had broken JSON; repaired"
    except ValueError:
        pass
    return "", "extra had broken JSON that could not be repaired; ignored"


def _number(cell: str) -> Tuple[str, bool]:
    c = (cell or "").strip()
    if not c:
        return "", True
    try:
        v = float(c.replace(",", ""))
        if v != v or v in (float("inf"), float("-inf")) or abs(v) > 1e12:
            return "", False                      # "nan", "inf", "1e400": not a number a video can use
        return c.replace(",", ""), True
    except ValueError:
        m = re.search(r"-?\d+(?:[.,]\d+)?", c.replace(",", ""))
        return (m.group(0), False) if m else ("", False)


def heal(text: str) -> Tuple[str, List[str]]:
    """A shot CSV -> (a CSV the strict reader accepts in all but the rarest cases, notes saying what was repaired). Never raises."""
    from . import templates as tpl
    from .narration import DIAGRAMS, HUDS

    head, rows, notes = _rows(text)
    col = {h: i for i, h in enumerate(head) if h}
    out: List[Dict[str, str]] = []
    seen_shot = False
    pending_layers: List[Dict[str, str]] = []
    for n, cells in enumerate(rows, start=2):
        r = {h: (cells[i].strip() if i < len(cells) else "") for h, i in col.items()}
        r = {k: v for k, v in r.items() if k in COLUMNS}
        say = lambda msg: notes.append(f"row {n}: {msg}")  # noqa: E731
        kind_cell = r.get("row", "").lower()
        row = ROW_ALIASES.get(kind_cell)
        if row is None:
            row = "shot" if r.get("kind") or r.get("asset") else "layer" if r.get("type") else None
            if row is None:
                say(f"row type {r.get('row')!r} is not plan, shot or layer; left out")
                continue
            say(f"row type {r.get('row')!r} read as {row}")
        elif row != kind_cell:
            say(f"row type {kind_cell!r} read as {row}")
            if kind_cell in ("hud", "diagram", "template") and not r.get("type"):
                r["type"] = kind_cell
        r["row"] = row
        if r.get("extra"):
            r["extra"], msg = _json_cell(r["extra"])
            if msg:
                say(msg)
        for c in NUMBER_COLS:
            if r.get(c):
                r[c], clean = _number(r[c])
                if not clean:
                    say(f"{c} was not a number" + (f"; read as {r[c]}" if r[c] else "; ignored"))
        if row == "plan":
            out.append(r)
            continue
        if row == "shot":
            k = (r.get("kind") or "").lower()
            if k not in KINDS:
                guess = KIND_ALIASES.get(k) or _close(k, KINDS) or ("image" if r.get("asset") else "plate" if r.get("type") else "image")
                say(f"kind {r.get('kind')!r} read as {guess}")
                k = guess
            r["kind"] = k
            what = r.get("label") or r.get("why") or r.get("text") or r.get("model") or r.get("texture") or "the subject of this sentence"
            if k == "hero":
                sc = _close(r.get("model", ""), HERO_SCENES, 0.6)
                if sc is None:
                    say(f"hero scene {r.get('model')!r} is not one the program draws; this shot is a picture instead")
                    k = r["kind"] = "image"
                    r["asset"] = r.get("asset") if ":" in r.get("asset", "") else f"flow_image:{what}"
                else:
                    r["model"] = sc
            if k == "craft":
                try:
                    craft_model(r.get("model", ""))
                except ValueError:
                    say(f"3D model {r.get('model')!r} is not in the library; this shot is a picture of it instead")
                    k = r["kind"] = "image"
                    r["asset"] = f"nasa_image:{r.get('model') or what}"
            if k == "globe":
                try:
                    world_texture(r.get("texture", ""))
                except ValueError:
                    say(f"world {r.get('texture')!r} has no texture; this shot is a NASA picture of it instead")
                    k = r["kind"] = "image"
                    r["asset"] = f"nasa_image:{r.get('texture') or what}"
            if k in ("image", "video"):
                a = r.get("asset", "")
                src, _, rest = a.partition(":")
                s = src.strip().lower().replace(" ", "_")
                if not rest.strip() or (s not in ASSET_SOURCES and s not in SOURCE_ALIASES):
                    fixed = f"{'flow_video' if k == 'video' else 'flow_image'}:{(a if not rest.strip() and a else '') or what}"
                    say(f"asset {a!r} has no source; read as {fixed[:60]}")
                    r["asset"] = fixed
                elif s not in ASSET_SOURCES:
                    r["asset"] = f"{SOURCE_ALIASES[s]}:{rest.strip()}"
                    say(f"asset source {src!r} read as {SOURCE_ALIASES[s]}")
            if seen_shot and not r.get("vo_anchor") and not r.get("t"):
                say("a shot needs its first words (vo_anchor) or a time; left out (the shot before it runs on)")
                continue
            out.append(r)
            if not seen_shot:
                seen_shot = True
                out.extend(pending_layers)
                pending_layers = []
            continue
        # a layer row
        ty = (r.get("type") or "").lower()
        if ty not in LAYER_TYPES:
            if ty in tpl.load_library() or (r.get("id", "").lower() in tpl.load_library() and not ty):
                r["id"] = r.get("id") or ty
                guess = "template"
            else:
                guess = LAYER_ALIASES.get(ty) or _close(ty, LAYER_TYPES)
            if guess is None:
                say(f"layer type {r.get('type')!r} is not one the program knows; left out")
                continue
            say(f"layer type {r.get('type')!r} read as {guess}")
            ty = guess
        r["type"] = ty
        if ty == "template":
            lib = tpl.load_library()
            tid = _close(r.get("id", ""), list(lib), 0.7)
            if tid is None:
                say(f"template {r.get('id')!r} is not in the library; left out")
                continue
            if tid != r.get("id"):
                say(f"template {r.get('id')!r} read as {tid}")
            r["id"] = tid
        elif ty == "diagram":
            d = _close(r.get("id", ""), DIAGRAMS, 0.6)
            if d is None:
                say(f"diagram {r.get('id')!r} is not one the program draws; left out")
                continue
            r["id"] = d
        elif ty == "hud":
            h = _close(r.get("id", ""), HUDS, 0.6)
            if h is None:
                say(f"hud {r.get('id')!r} is not one the program draws; left out")
                continue
            r["id"] = h
        elif ty == "annotate":
            try:
                ex = json.loads(r.get("extra") or "{}")
            except ValueError:
                ex = {}
            if ex.get("x") is None or ex.get("y") is None:
                say("an annotate row needs extra x and y; shown as a caption instead")
                r["type"] = "caption"
        if not seen_shot:
            pending_layers.append(r)
        else:
            out.append(r)
    if pending_layers:
        notes.append(f"{len(pending_layers)} layer row(s) came before any shot and had no shot to go on; left out")
    if not any(r["row"] == "plan" for r in out):
        out.insert(0, {"row": "plan"})
    elif out[0]["row"] != "plan":
        plan = next(r for r in out if r["row"] == "plan")
        out.remove(plan)
        out.insert(0, plan)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(COLUMNS), extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in out:
        w.writerow(r)
    return buf.getvalue(), notes


def read_text(path: "str | Any") -> str:
    """A CSV file as text, whatever saved it: UTF-8 (with or without a BOM), or Excel's Windows encoding."""
    from pathlib import Path

    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def looks_usable(text: str) -> bool:
    """True when the repaired CSV has at least one shot row (the What If panel accepts it; Generate repairs the rest)."""
    healed, _ = heal(text)
    return any(line.startswith("shot,") for line in healed.splitlines())


_ROW_NO = re.compile(r"^row (\d+):")


def read_healed(text: str, words: Sequence[Any], duration: float) -> Tuple[List[Any], List[Any], Dict[str, Any], List[str]]:
    """heal() then the strict reader; rows it still refuses are left out one pass at a time (named in the notes). Raises PlanError only
    when no shot can be read at all."""
    healed, notes = heal(text)
    rows = list(csv.reader(io.StringIO(healed)))
    if not words and duration:
        # no transcript (it failed or is missing): the CSV's shots are spread evenly over the voiceover instead of being lost
        head = rows[0]
        it, ia, ir = head.index("t"), head.index("vo_anchor"), head.index("row")
        shots = [r for r in rows[1:] if r[ir] == "shot"]
        for k, r in enumerate(shots):
            if not r[it]:
                r[it] = f"{duration * k / max(1, len(shots)):.2f}"
        for r in rows[1:]:
            if r[ir] == "layer":
                r[ia] = ""                         # a layer appears at the start of its shot
        if shots:
            notes.append(f"no transcript: the {len(shots)} shots were spread evenly over the voiceover; plan again once it is transcribed")
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        healed = buf.getvalue()
    for _ in range(12):
        try:
            shots, items, info, more = read_shots(healed, words, duration)
            return shots, items, info, notes + more
        except PlanError as exc:
            bad = set()
            for p in exc.problems:
                m = _ROW_NO.match(p)
                if m:
                    bad.add(int(m.group(1)))
                    notes.append(f"{p}; left out")
            if not bad or len(rows) - len(bad) < 2:
                raise PlanError(list(exc.problems))
            rows = [r for i, r in enumerate(rows, start=1) if i not in bad]
            buf = io.StringIO()
            csv.writer(buf, lineterminator="\n").writerows(rows)
            healed = buf.getvalue()
    raise PlanError(["the shot CSV could not be read after repairs"])
