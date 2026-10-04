"""The pakMap CSV: one row per visual event, grouped into items.

Every message names the row (as a spreadsheet shows it: the header is row 1)."""

from __future__ import annotations

import csv
import difflib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LAYER_TYPES = (
    "hud_title", "stat", "caption", "marker", "zone_label", "fill", "line", "pip", "filmstrip", "sticker",
    "media_full", "dots", "cluster", "value_overlay", "ghost_shape", "streak", "camera", "sound",
)
ALIASES = {"title": "hud_title", "hud": "hud_title", "zone": "zone_label", "region": "fill", "route": "line",
           "photo": "pip", "card": "pip", "footage": "media_full", "interlude": "media_full", "dot_density": "dots",
           "heatmap": "value_overlay", "overlay": "value_overlay", "compare": "ghost_shape", "camera_move": "camera"}
CAMERA_ACTIONS = ("start", "fly_to", "push_in", "pull_back", "drift")
LAYER_ACTIONS = ("in", "out")
FRAMES = ("globe", "continental", "country", "region", "local")

COLUMNS = (
    "item_no", "beat", "vo_anchor", "offset_s", "t_start", "t_end", "hold", "layer_type", "layer_id", "layer_action",
    "camera_action", "camera_dur", "lat", "lon", "zoom", "frame", "easing", "geo_ref", "line_kind", "label_text",
    "sub_text", "color_role", "value_from", "value_to", "value_format", "anchor", "asset_path", "data_source", "sfx", "ambience", "params", "notes",
)
_FLOATS = ("offset_s", "t_start", "t_end", "hold", "camera_dur", "lat", "lon", "zoom", "value_from", "value_to")


class CsvError(ValueError):
    """The CSV can't be read; .problems lists every issue with its row number."""

    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class Row:
    line: int  # row number as a spreadsheet shows it
    item_no: int = 0
    layer_type: str = ""
    layer_id: str = ""
    layer_action: str = "in"
    beat: str = ""
    vo_anchor: str = ""
    offset_s: float = 0.0
    t_start: Optional[float] = None
    t_end: Optional[float] = None
    hold: Optional[float] = None
    camera_action: str = ""
    camera_dur: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    zoom: Optional[float] = None
    frame: str = ""
    easing: str = ""
    geo_ref: str = ""
    line_kind: str = ""
    label_text: str = ""
    sub_text: str = ""
    color_role: str = ""
    value_from: Optional[float] = None
    value_to: Optional[float] = None
    value_format: str = ""
    anchor: str = ""
    asset_path: str = ""
    data_source: str = ""
    sfx: str = ""
    ambience: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""


def _check_sound(n: int, column: str, value: str, problems: List[str]) -> str:
    """sfx / ambience cells: none, a vocabulary id, or catalog:<library id>."""
    from .sounds import AMBIENCE_IDS, SFX_IDS

    v = value.strip().lower()
    if not v or v == "none" or v.startswith("catalog:"):
        return v
    own, other = (SFX_IDS, AMBIENCE_IDS) if column == "sfx" else (AMBIENCE_IDS, SFX_IDS)
    if v in own:
        return v
    if v in other:
        problems.append(f"row {n}: {v!r} is {'an ambience' if column == 'sfx' else 'a sound effect'}: put it in the {'ambience' if column == 'sfx' else 'sfx'} column")
    else:
        hint = difflib.get_close_matches(v, own, n=1)
        problems.append(f"row {n}: unknown {column} {v!r}" + (f" (did you mean {hint[0]!r}?)" if hint else f" (use none, catalog:<id>, or one of: {', '.join(own)})"))
    return v


def _header(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "_").replace("-", "_").lstrip("﻿")


def parse_csv(source: "str | Path", *, text: Optional[str] = None) -> Tuple[List[Row], List[str]]:
    """Read the CSV. Returns (rows, warnings); raises CsvError listing every problem found."""
    if text is None:
        text = Path(source).read_text(encoding="utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    try:
        head = next(reader)
    except StopIteration:
        raise CsvError(["the CSV is empty"])
    names = [_header(h) for h in head]
    problems: List[str] = []
    warnings: List[str] = []
    unknown = [h for h in names if h and h not in COLUMNS]
    for h in unknown:
        hint = difflib.get_close_matches(h, COLUMNS, n=1)
        warnings.append(f"row 1: unknown column \"{h}\" is ignored" + (f" (did you mean \"{hint[0]}\"?)" if hint else ""))
    if "layer_type" not in names and "camera_action" not in names:
        raise CsvError(["row 1: the header needs a layer_type column"])
    rows: List[Row] = []
    for n, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue
        extra = [c for c in cells[len(names):] if c.strip()]
        if extra:
            problems.append(f"row {n}: has {len(cells)} cells but the header has {len(names)}: a cell that contains a comma (such as a number format like UP TO #,##0 MM) must be wrapped in double quotes")
            continue
        rec = {names[i]: (cells[i].strip() if i < len(cells) else "") for i in range(len(names)) if names[i] in COLUMNS}
        row = Row(line=n)
        for key, raw in rec.items():
            if raw == "":
                continue
            try:
                if key == "item_no":
                    row.item_no = int(float(raw))
                elif key in _FLOATS:
                    setattr(row, key, float(raw.replace(",", "")))
                elif key == "params":
                    obj = json.loads(raw)
                    if not isinstance(obj, dict):
                        raise ValueError("params must be a JSON object like {\"per_million\": 150}")
                    row.params = obj
                else:
                    setattr(row, key, raw)
            except (ValueError, json.JSONDecodeError) as exc:
                problems.append(f"row {n}: {key} is not valid ({raw!r}): {exc}")
        lt = row.layer_type.strip().lower().replace(" ", "_")
        row.layer_type = ALIASES.get(lt, lt)
        if not row.layer_type and row.camera_action:
            row.layer_type = "camera"
        if row.layer_type not in LAYER_TYPES:
            hint = difflib.get_close_matches(row.layer_type, list(LAYER_TYPES) + list(ALIASES), n=1)
            problems.append(f"row {n}: unknown layer_type {row.layer_type!r}" + (f" (did you mean {hint[0]!r}?)" if hint else f" (use one of: {', '.join(LAYER_TYPES)})"))
        row.layer_action = (row.layer_action or "in").lower()
        if row.layer_action not in LAYER_ACTIONS:
            problems.append(f"row {n}: layer_action must be in or out (got {row.layer_action!r})")
        if row.camera_action:
            row.camera_action = row.camera_action.lower()
            if row.camera_action not in CAMERA_ACTIONS:
                problems.append(f"row {n}: camera_action must be one of {', '.join(CAMERA_ACTIONS)} (got {row.camera_action!r})")
        if row.frame and row.frame.lower() not in FRAMES:
            problems.append(f"row {n}: frame must be one of {', '.join(FRAMES)} (got {row.frame!r})")
        row.frame = row.frame.lower()
        if row.asset_path:
            from .sourcing import misspelled_source, split_parts

            for part in split_parts(row.asset_path):
                hint = misspelled_source(part)
                if hint:
                    problems.append(f"row {n}: asset_path {part!r} looks like a picture source but {part.split(':')[0]!r} is not one (did you mean {hint!r}?)")
        row.sfx = _check_sound(n, "sfx", row.sfx, problems)
        row.ambience = _check_sound(n, "ambience", row.ambience, problems)
        if row.layer_type == "sound" and not (row.sfx or row.ambience):
            problems.append(f"row {n}: a sound row needs an sfx or an ambience value")
        if row.layer_action == "out" and not row.layer_id:
            problems.append(f"row {n}: an 'out' row needs the layer_id of the layer it ends")
        if (row.lat is None) != (row.lon is None):
            problems.append(f"row {n}: give both lat and lon, or neither")
        rows.append(row)
    if problems:
        raise CsvError(problems)
    if not rows:
        raise CsvError(["the CSV has a header but no rows"])
    return rows, warnings
