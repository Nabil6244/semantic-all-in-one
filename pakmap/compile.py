"""CSV rows + narration words -> a pakmap-engine render spec, plus a plan report an author can read.

Timing, in order of what wins for a row:
  t_start        an explicit time in seconds
  vo_anchor      a phrase from the narration; the event lands on its first word (add "|end" to land
                 on the last word, offset_s to nudge). A hud_title lands 0.14 s BEFORE its words.
  neither        spread evenly between the rows around it, and flagged "proportional" in the report
Between items there is a fixed 0.5 s clear beat: every layer of the previous item ends 0.5 s before
the next item's first event. The last item runs to the end of the narration.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .anchor import Transcript, Word
from .geo import GeoError, Located, resolve, resolve_many, view_for
from .schema import CsvError, Row, parse_csv

LEAD_S = 0.14  # the title chip lands this long before the narrator starts the item
CLEAR_S = 0.5  # fixed gap between one item's layers and the next item's first event
MIN_VISIBLE_S = 0.4

# how long a layer stays when the row gives neither t_end nor hold (None = until the item ends)
DEFAULT_HOLD = {
    "stat": 4.5, "caption": 4.0, "marker": 9.0, "zone_label": 9.0, "pip": 6.0, "filmstrip": 7.0, "sticker": 5.0,
    "media_full": 6.0, "ghost_shape": 7.0, "streak": 5.0, "cluster": 8.0, "dots": 10.0,
    "hud_title": None, "fill": None, "line": None, "value_overlay": None,
}
FILL_ROLES = {"subject": "primary", "primary": "primary", "featured": "featured", "compare": "compare", "neutral": "orange",
              "orange": "orange", "accent": "accent", "water": "water", "green": "green", "red": "subject", "": "primary"}
MARKER_ROLES = {"": "dark", "dark": "dark", "neutral": "neutral", "featured": "featured", "subject": "subject", "compare": "compare"}
LINE_KINDS = ("flow", "river", "rail", "border_trace", "divide", "reference", "connector")


class CompileError(ValueError):
    def __init__(self, report: "Report"):
        super().__init__("; ".join(report.errors))
        self.report = report


@dataclass
class EventReport:
    id: str
    type: str
    item: int
    t_in: float
    t_out: float
    timing: str  # anchored | explicit | proportional | derived
    row: int
    anchor: str = ""
    matched: str = ""
    note: str = ""


@dataclass
class Report:
    events: List[EventReport] = field(default_factory=list)
    moves: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration: float = 0.0
    info: List[str] = field(default_factory=list)  # plain facts (for example which pictures will be fetched), shown before the warnings

    def to_dict(self) -> dict:
        return {"duration": self.duration, "events": [e.__dict__ for e in self.events], "moves": self.moves, "warnings": self.warnings, "errors": self.errors, "info": self.info}

    def to_text(self) -> str:
        out = [f"{len(self.events)} events over {self.duration:.1f}s"]
        for e in self.events:
            how = {"anchored": f"on \"{e.matched}\"", "explicit": "set time", "proportional": "PROPORTIONAL (no anchor)", "derived": "from another row"}[e.timing]
            out.append(f"  row {e.row:>3}  item {e.item:>2}  {e.t_in:7.2f}-{e.t_out:7.2f}  {e.type:<13} {e.id:<18} {how}{('  ' + e.note) if e.note else ''}")
        if self.moves:
            out.append(f"{len(self.moves)} camera moves")
            for m in self.moves:
                out.append(f"  {m['t']:7.2f}  {m['type']:<9} {m.get('dur', 0):4.1f}s  -> {m['to']}")
        out += [f"NOTE: {i}" for i in self.info] + [f"WARNING: {w}" for w in self.warnings] + [f"ERROR: {e}" for e in self.errors]
        return "\n".join(out)


@dataclass
class CompileResult:
    spec: dict
    report: Report
    audio_hints: dict = field(default_factory=dict)  # the author's sfx / ambience columns, for pakmap.audio_plan


def _num(v: float) -> float:
    return round(float(v), 3)


def compile_csv(csv_path: "str | Path | None" = None, words: Sequence[Word] = (), *, text: Optional[str] = None, base_dir: "str | Path | None" = None, **kw) -> CompileResult:
    rows, warns = parse_csv(csv_path, text=text) if text is not None else parse_csv(csv_path)
    if base_dir is None and csv_path is not None:
        base_dir = Path(csv_path).resolve().parent
    res = compile_rows(rows, words, base_dir=base_dir, **kw)
    res.report.warnings[:0] = warns
    return res


def hit_first(tr: Transcript, m) -> int:
    """Token index where a match begins (so a following row can reuse the same words)."""
    for i, (a, _b) in enumerate(tr._spans):
        if a >= m.first:
            return i
    return len(tr._spans)


def _engine_root() -> Path:
    """Where pakmap-engine is: the packaged app's copy when there is one, else next to this package."""
    try:
        from .engine_runner import engine_dir

        return engine_dir()
    except Exception:
        return Path(__file__).resolve().parent.parent / "pakmap-engine"


def _find_node() -> Optional[str]:
    """The app's own Node (packaged builds ship one and have no node on PATH), else the system's."""
    try:
        from providers.flow.engine_manager import _find_node_binary

        found = _find_node_binary()
        if found:
            return str(found)
    except Exception:
        pass
    return shutil.which("node")


def check_with_engine(spec: dict) -> Tuple[List[str], List[str], bool]:
    """Run the renderer's own rule check. Returns (errors, warnings, ran)."""
    node = _find_node()
    tool = _engine_root() / "tools" / "validate_spec.mjs"
    if not node or not tool.exists():
        return [], [], False
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "spec.json"
        f.write_text(json.dumps(spec), encoding="utf-8")
        r = subprocess.run([node, str(tool), str(f)], capture_output=True, text=True, timeout=60)
    try:
        data = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return [], [f"the renderer's rule check could not run: {(r.stderr or r.stdout).strip()[:200]}"], False
    return data.get("errors", []), data.get("warnings", []), True


def compile_rows(rows: List[Row], words: Sequence[Word], *, duration: Optional[float] = None, width: int = 1920, height: int = 1080,
                 fps: int = 30, base_dir: "str | Path | None" = None, watermark: Optional[dict] = None, borders: bool = True,
                 output: str = "OUTPUT.mp4", cache_dir: str = "CACHE_DIR", validate: bool = True,
                 media_map: Optional[Dict[str, str]] = None) -> CompileResult:
    rep = Report()
    err = rep.errors.append
    # pictures named by source (stock_image:..., flow_image:...): a sticker needs a transparent PNG, which no provider can supply;
    # everything else is swapped for the fetched file when the caller has fetched them (media_map), else left as written (a plan check)
    import dataclasses
    from .sourcing import find_occurrences, media_for

    for row in rows:
        if row.layer_type == "sticker" and find_occurrences([row]):
            err(f"row {row.line}: a sticker must be a PNG with transparency, so it cannot be fetched from {row.asset_path!r}: give a file")
    if media_map:
        swapped = []
        for r in rows:
            if not r.asset_path:
                swapped.append(r)
                continue
            path = media_for(r, media_map)
            if path:
                swapped.append(dataclasses.replace(r, asset_path=path))
            else:  # every picture of this layer was skipped by the author: the layer is left out
                rep.warnings.append(f"row {r.line}: its picture was skipped, so the {r.layer_type} is left out")
        rows = swapped
    tr = Transcript(words)
    if not len(tr) and duration is None:
        raise CompileError(_report_with(rep, ["no narration words and no duration: pass the transcript or the video length"]))
    total = float(duration) if duration else float(math.ceil(tr.end + 1.0))
    rep.duration = total

    # ---- 1. anchor every row to a time -------------------------------------------------
    times: Dict[int, Tuple[Optional[float], str, str, str]] = {}  # row.line -> (time, timing, anchor, matched)
    cursor = 0
    for row in rows:
        if row.t_start is not None:
            times[row.line] = (row.t_start + row.offset_s, "explicit", "", "")
            continue
        if not row.vo_anchor:
            times[row.line] = (None, "proportional", "", "")
            continue
        phrase, _, mod = row.vo_anchor.partition("|")
        hit = tr.find(phrase, cursor) if len(tr) else None
        if not hit:
            heard = tr.nearest(phrase) if len(tr) else None
            hint = (f" The closest words heard are {heard[0]!r} at {heard[1]:.1f}s: use that spelling in vo_anchor, or give t_start." if heard
                    else " Use words as they are spoken, or give t_start.")
            err(f"row {row.line}: can't find {phrase.strip()!r} in the narration.{hint}")
            times[row.line] = (None, "proportional", row.vo_anchor, "")
            continue
        m, nxt = hit
        cursor = min(nxt, hit_first(tr, m))  # the next row may anchor on the same words
        if m.out_of_order:
            rep.warnings.append(f"row {row.line}: {phrase.strip()!r} is said earlier in the narration than the rows before it ({m.t_start:.1f}s); check the row order")
        elif m.fuzzy:
            rep.warnings.append(f"row {row.line}: {phrase.strip()!r} matched the spoken {m.text!r} (a spelling variant); check it")
        t = (m.t_end if mod.strip().lower() == "end" else m.t_start) + row.offset_s
        if row.layer_type == "hud_title":
            t -= LEAD_S
        times[row.line] = (max(0.0, t), "anchored", row.vo_anchor, m.text)

    # ---- 2. item windows --------------------------------------------------------------
    items: "OrderedDict[int, List[Row]]" = OrderedDict()
    for row in rows:
        items.setdefault(row.item_no, []).append(row)
    starts: Dict[int, float] = {}
    for n, rs in items.items():
        known = [times[r.line][0] for r in rs if times[r.line][0] is not None]
        if not known:
            err(f"item {n}: none of its rows has a vo_anchor or t_start, so there is no way to place it. Anchor at least one row (the title is a good choice).")
            starts[n] = 0.0
            continue
        starts[n] = min(known)
    order = list(items)
    ends: Dict[int, float] = {}
    for i, n in enumerate(order):
        ends[n] = total if i == len(order) - 1 else max(starts[n] + MIN_VISIBLE_S, starts[order[i + 1]] - CLEAR_S)
        if i + 1 < len(order) and starts[order[i + 1]] < starts[n]:
            err(f"item {order[i + 1]} starts at {starts[order[i + 1]]:.1f}s, before item {n} ({starts[n]:.1f}s): items must follow the narration in order")

    # ---- 3. spread unanchored rows evenly ---------------------------------------------
    final: Dict[int, float] = {}
    for n, rs in items.items():
        seq = [(r, times[r.line][0]) for r in rs]
        i = 0
        while i < len(seq):
            if seq[i][1] is not None:
                final[seq[i][0].line] = seq[i][1]; i += 1; continue
            j = i
            while j < len(seq) and seq[j][1] is None:
                j += 1
            prev_t = final[seq[i - 1][0].line] if i > 0 else None
            next_t = seq[j][1] if j < len(seq) else None
            lo = prev_t if prev_t is not None else max(starts[n], (next_t or starts[n]) - 2.0)
            hi = next_t if next_t is not None else ends[n]
            m = j - i
            for k in range(m):
                final[seq[i + k][0].line] = lo + (hi - lo) * (k + 1) / (m + 1) if prev_t is not None or next_t is None else lo + (hi - lo) * k / m
            i = j
    for line, (t, timing, *_rest) in times.items():
        pass

    # ---- 4. events ---------------------------------------------------------------------
    hints: Dict[str, Any] = {"events": {}, "camera": [], "cues": [], "ambience": []}
    events: List[dict] = []
    by_id: Dict[str, dict] = {}
    info: Dict[str, EventReport] = {}
    counters: Dict[Tuple[int, str], int] = {}
    last_strip: Dict[int, dict] = {}
    cam_rows: List[Tuple[Row, float]] = []
    base = Path(base_dir) if base_dir else None

    def new_id(row: Row) -> str:
        if row.layer_id:
            return row.layer_id
        k = counters.get((row.item_no, row.layer_type), 0) + 1
        counters[(row.item_no, row.layer_type)] = k
        return f"i{row.item_no}_{row.layer_type}{k}"

    for row in rows:
        t = final.get(row.line, starts[row.item_no])
        timing, anchor, matched = times[row.line][1], times[row.line][2], times[row.line][3]
        if row.camera_action:
            cam_rows.append((row, t))
        if row.ambience:
            hints["ambience"].append({"t": _num(t), "ambience": row.ambience, "row": row.line})
        if row.layer_type == "sound" and row.sfx:
            hints["cues"].append({"t": _num(t), "sfx": row.sfx, "source": f"sound row {row.line}"})
        if row.layer_type == "camera" and row.sfx:
            hints["camera"].append({"t": _num(t), "sfx": row.sfx})
        if row.layer_type in ("camera", "sound"):
            continue
        if row.layer_action == "out":
            ev = by_id.get(row.layer_id)
            if not ev:
                err(f"row {row.line}: 'out' refers to layer {row.layer_id!r}, which no earlier row created")
            elif t <= ev["t_in"]:
                err(f"row {row.line}: layer {row.layer_id!r} would end at {t:.1f}s, before it starts ({ev['t_in']:.1f}s)")
            else:
                ev["t_out"] = _num(t); info[ev["id"]].t_out = _num(t); info[ev["id"]].note = f"ended by row {row.line}"
            continue
        try:
            if row.layer_type == "filmstrip" and row.item_no in last_strip and (not row.layer_id or row.layer_id == last_strip[row.item_no]["id"]):
                last_strip[row.item_no]["cards"].append(_card(row, base))
                continue
            ev = _build(row, new_id(row), base)
        except (GeoError, ValueError, KeyError) as exc:
            err(f"row {row.line}: {exc.args[0] if exc.args else exc}")
            continue
        end = ends[row.item_no]
        hold = row.hold if row.hold is not None else DEFAULT_HOLD.get(row.layer_type)
        t_out = row.t_end if row.t_end is not None else (t + hold if hold is not None else end)
        if t_out > end + 1e-9:
            if row.t_end is not None or row.hold is not None:
                rep.warnings.append(f"row {row.line}: {row.layer_type} {ev['id']!r} would run to {t_out:.1f}s but item {row.item_no} ends at {end:.1f}s (0.5 s clear beat); it ends with the item")
            t_out = end
        if t_out - t < MIN_VISIBLE_S:
            rep.warnings.append(f"row {row.line}: {ev['id']!r} is on screen for only {max(0.0, t_out - t):.2f}s because the next item starts at {end + CLEAR_S:.1f}s")
            t_out = t + MIN_VISIBLE_S
        ev["t_in"], ev["t_out"] = _num(t), _num(t_out)
        events.append(ev); by_id[ev["id"]] = ev
        if row.sfx:
            hints["events"][ev["id"]] = row.sfx
        if ev["id"] in info:
            err(f"row {row.line}: duplicate layer_id {ev['id']!r}")
        info[ev["id"]] = EventReport(ev["id"], row.layer_type, row.item_no, ev["t_in"], ev["t_out"], timing, row.line, anchor, matched)
        if row.layer_type == "filmstrip":
            last_strip[row.item_no] = ev
    for ev in events:  # report the final windows (an 'out' row or clipping may have changed them)
        info[ev["id"]].t_in, info[ev["id"]].t_out = ev["t_in"], ev["t_out"]
    rep.events = sorted(info.values(), key=lambda e: (e.t_in, e.row))

    # ---- 5. camera ---------------------------------------------------------------------
    camera, moves = _camera(cam_rows, events, total, width, height, rep)
    rep.moves = moves

    spec: Dict[str, Any] = {
        "width": width, "height": height, "fps": fps, "duration": _num(total), "output": output, "cache_dir": cache_dir,
        "ffmpeg": "ffmpeg", "overlays": {"borders": borders, "fills": []}, "camera": camera,
        "events": sorted(events, key=lambda e: (e["t_in"], e["id"])),
    }
    if base is not None:
        spec["base_dir"] = str(base)
    if watermark:
        spec["watermark"] = watermark
    if validate and not rep.errors:
        e2, w2, ran = check_with_engine(spec)
        rep.errors.extend(f"renderer rule: {m}" for m in e2)
        rep.warnings.extend(w2)
    if rep.errors:
        raise CompileError(rep)
    return CompileResult(spec, rep, hints)


def _report_with(rep: Report, errors: List[str]) -> Report:
    rep.errors.extend(errors)
    return rep


# ---- one row -> one event -----------------------------------------------------------------

def _place_args(row: Row, prefer: str = "area") -> Located:
    if row.lat is not None and row.lon is not None and not row.geo_ref:
        return resolve(f"{row.lat},{row.lon}")
    if not row.geo_ref:
        raise ValueError(f"{row.layer_type} needs a geo_ref (a place name, an ISO code, or lat,lon)")
    return resolve(row.geo_ref, prefer)


def _card(row: Row, base: Optional[Path]) -> dict:
    if not row.asset_path:
        raise ValueError("a filmstrip card needs asset_path (its picture)")
    c: Dict[str, Any] = {"media": row.asset_path}
    if row.label_text:
        c["label"] = row.label_text
    if row.params.get("start_s") is not None:
        c["start_s"] = row.params["start_s"]
    return c


def _build(row: Row, eid: str, base: Optional[Path]) -> dict:
    t = row.layer_type
    ev: Dict[str, Any] = {"id": eid, "type": t}
    p = dict(row.params)
    if t == "hud_title":
        if not row.label_text:
            raise ValueError("hud_title needs label_text (for example PART 1)")
        ev.update(label=row.label_text)
        if row.sub_text:
            ev["sub"] = row.sub_text
    elif t == "stat":
        if row.value_to is None:
            raise ValueError("stat needs value_to (the number it counts to)")
        ev.update(anchor=row.anchor or "br", value_from=row.value_from if row.value_from is not None else row.value_to, value_to=row.value_to,
                  format=row.value_format or "#,##0")
        if row.sub_text:
            ev["sub"] = row.sub_text
    elif t == "caption":
        if not row.label_text:
            raise ValueError("caption needs label_text")
        ev.update(text=row.label_text.replace("\\n", "\n"), anchor=row.anchor or "bc")
        if row.sub_text:
            ev["sub"] = row.sub_text
    elif t in ("marker", "zone_label"):
        loc = _place_args(row, "point")
        if not row.label_text:
            raise ValueError(f"{t} needs label_text")
        ev.update(type="marker", lon=round(loc.lon, 5), lat=round(loc.lat, 5), label=row.label_text, role=MARKER_ROLES.get(row.color_role, row.color_role or "dark"))
        if t == "zone_label":
            ev.update(dot=False, role=MARKER_ROLES.get(row.color_role, "neutral") if row.color_role else "neutral")
        if row.sub_text:
            ev["sub"] = row.sub_text
        if p.get("value"):
            ev["value"] = str(p.pop("value"))
        if p.get("side"):
            ev["side"] = p.pop("side")
    elif t == "fill":
        loc = _place_args(row)
        if not loc.is_area:
            raise ValueError(f"fill needs an area (a country, state, county or region), but {row.geo_ref!r} is a point")
        role = FILL_ROLES.get(row.color_role.lower() if row.color_role else "", None)
        if role is None:
            raise ValueError(f"unknown color_role {row.color_role!r} for a fill (use {', '.join(sorted(set(FILL_ROLES) - {''}))})")
        ev["role"] = role
        if loc.kind == "country" and loc.iso:
            ev["iso"] = [loc.iso]
        else:
            ev["polys"] = loc.polys
    elif t == "line":
        kind = (row.line_kind or p.pop("kind", "")).lower()
        if kind not in LINE_KINDS:
            raise ValueError(f"line needs line_kind: one of {', '.join(LINE_KINDS)}")
        if "coords" in p:
            coords = p.pop("coords")
        else:
            pts = resolve_many(row.geo_ref) if row.geo_ref else []
            coords = [[round(x.lon, 5), round(x.lat, 5)] for x in pts]
        if len(coords) < 2:
            raise ValueError("line needs at least two waypoints in geo_ref (A;B;C) or params.coords")
        ev.update(kind=kind, coords=coords)
    elif t == "pip":
        if not row.asset_path:
            raise ValueError("pip needs asset_path (a picture or clip; use a|b for a crossfade)")
        imgs = [s.strip() for s in row.asset_path.split("|") if s.strip()]
        if len(imgs) > 1:
            ev["images"] = imgs
        else:
            ev["media"] = imgs[0]
        ev["anchor"] = row.anchor or "tr"
        if row.label_text:
            ev["label"] = row.label_text
        if row.geo_ref:
            lead = resolve(row.geo_ref, "point")
            ev["leader"] = {"lon": round(lead.lon, 5), "lat": round(lead.lat, 5)}
    elif t == "filmstrip":
        ev["cards"] = [_card(row, base)]
        if row.anchor in ("left", "right", "center"):
            ev["align"] = row.anchor
    elif t == "sticker":
        if not row.asset_path:
            raise ValueError("sticker needs asset_path (a PNG with transparency)")
        ev["media"] = row.asset_path
        if "at" in p:
            ev["at"] = p.pop("at")
        else:
            loc = _place_args(row, "point")
            ev.update(lon=round(loc.lon, 5), lat=round(loc.lat, 5))
    elif t == "media_full":
        if not row.asset_path:
            raise ValueError("media_full needs asset_path (a picture or clip)")
        ev["media"] = row.asset_path
    elif t in ("dots", "cluster"):
        if t == "dots":
            if not row.data_source and "points" not in p:
                raise ValueError("dots needs data_source (bundled:populated_places or file:points.csv) or params.points")
            if row.data_source:
                ev["data"] = row.data_source
            if row.geo_ref:
                loc = _place_args(row)
                if loc.kind == "country" and loc.iso:
                    ev["region_iso"] = [loc.iso]
                else:
                    ev["bbox"] = [round(v, 4) for v in loc.bbox]
        else:
            pts = p.pop("points", None) or [[round(x.lon, 5), round(x.lat, 5)] for x in resolve_many(row.geo_ref)] if (p.get("points") or row.geo_ref) else None
            if not pts:
                raise ValueError("cluster needs points in geo_ref (A;B;C) or params.points")
            ev["points"] = pts
        if row.color_role and row.color_role.startswith("#"):
            ev["color"] = row.color_role
    elif t == "value_overlay":
        if not row.data_source:
            raise ValueError("value_overlay needs data_source (bundled:rainfall_chirps or file:grid.tif)")
        loc = _place_args(row)
        if loc.kind != "country" or not loc.iso:
            raise ValueError("value_overlay is clipped to a country: give its name or ISO code in geo_ref")
        ev.update(data=row.data_source, clip_iso=[loc.iso])
    elif t == "ghost_shape":
        loc = _place_args(row)
        if loc.kind != "country" or not loc.iso:
            raise ValueError("ghost_shape copies a country: give its name or ISO code in geo_ref")
        to = p.pop("to", None)
        if not to:
            raise ValueError("ghost_shape needs params.to, for example {\"lon\": 37.6, \"lat\": 2.6} (where its centre goes)")
        ev.update(iso=loc.iso, to=to, role=row.color_role or "compare")
    elif t == "streak":
        loc = _place_args(row)
        if loc.kind == "country" and loc.iso:
            ev["region_iso"] = [loc.iso]
        else:
            ev["bbox"] = [round(v, 4) for v in loc.bbox]
    else:
        raise ValueError(f"layer type {t} is not handled")
    for k, v in p.items():  # whatever else the author put in params goes straight to the renderer
        ev[k] = v
    return ev


# ---- camera ------------------------------------------------------------------------------

DEFAULT_DUR = {"fly_to": 2.2, "push_in": 8.0, "pull_back": 2.0}


def _target(row: Row, current: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if row.lat is not None and row.lon is not None:
        return row.lon, row.lat, row.zoom if row.zoom is not None else (FRAME_DEFAULT.get(row.frame) or current[2])
    if row.geo_ref:
        loc = resolve(row.geo_ref)
        lon, lat, z = view_for(loc, row.frame)
        return lon, lat, row.zoom if row.zoom is not None else z
    return current[0], current[1], row.zoom if row.zoom is not None else current[2]


FRAME_DEFAULT = {"globe": 1.7, "continental": 3.3, "local": 8.4}


def _camera(cam_rows: List[Tuple[Row, float]], events: List[dict], total: float, width: int, height: int, rep: Report):
    drift = {"pct_per_s": 0.5, "heading_deg": 60}
    start = None
    moves: List[dict] = []
    current = (20.0, 20.0, 2.0)
    for row, t in sorted(cam_rows, key=lambda x: x[1]):
        try:
            if row.camera_action == "drift":
                drift.update({k: v for k, v in row.params.items() if k in ("pct_per_s", "heading_deg", "turn_deg_per_s")})
                continue
            if row.camera_action in ("start", "fly_to") and not (row.geo_ref or row.lat is not None or row.zoom is not None):
                raise GeoError(f"camera {row.camera_action} needs a target: geo_ref (a place), or lat and lon, or zoom")
            lon, lat, z = _target(row, current)
            if row.camera_action == "start":
                start = {"lon": round(lon, 4), "lat": round(lat, 4), "zoom": round(z, 3)}
                current = (lon, lat, z)
                continue
            dur = row.camera_dur or DEFAULT_DUR[row.camera_action]
            if row.camera_action in ("push_in", "pull_back") and row.zoom is None and not row.frame and not row.geo_ref:
                z = current[2] + (1.0 if row.camera_action == "push_in" else -1.0) * float(row.params.get("zoom_delta", 1.0))
            mv: Dict[str, Any] = {"type": row.camera_action, "t": _num(t), "dur": _num(dur), "to": {"zoom": round(z, 3)}}
            if row.camera_action == "fly_to" or row.geo_ref or row.lat is not None:
                mv["to"].update(lon=round(lon, 4), lat=round(lat, 4))
            if row.easing:
                mv["easing"] = row.easing
            moves.append(mv)
            current = (lon if "lon" in mv["to"] else current[0], lat if "lat" in mv["to"] else current[1], z)
        except GeoError as exc:
            rep.errors.append(f"row {row.line}: {exc.args[0]}")
    # moves must not overlap: a move is cut short where the next one begins
    for a, b in zip(moves, moves[1:]):
        if a["t"] + a["dur"] > b["t"] - 0.05:
            new = b["t"] - 0.05 - a["t"]
            if new < 0.3:
                rep.errors.append(f"camera moves at {a['t']:.1f}s and {b['t']:.1f}s are too close together ({new:.2f}s left for the first); space them out")
            else:
                rep.warnings.append(f"the camera move at {a['t']:.1f}s was shortened from {a['dur']:.1f}s to {new:.1f}s so it ends before the next one")
                a["dur"] = _num(new)
    for m in moves:
        if m["t"] + m["dur"] > total:
            m["dur"] = _num(max(0.3, total - m["t"]))
    if start is None:
        first = next((m for m in moves if m["type"] == "fly_to"), None)
        if first:
            start = {"lon": first["to"]["lon"], "lat": first["to"]["lat"], "zoom": first["to"]["zoom"]}
            moves.remove(first)
            rep.warnings.append("no camera start row: the camera starts at the first fly_to target")
        else:
            start = {"lon": 20.0, "lat": 20.0, "zoom": 2.0}
            rep.warnings.append("no camera rows: the camera sits on a default world view")
    return {"start": start, "drift": drift, "moves": moves}, moves
