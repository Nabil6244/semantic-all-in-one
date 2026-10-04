"""HybridPlan -> pakMap rows (the compiled, internal representation) -> pakMap spec.

The rows use explicit times (t_start / t_end) taken from the plan, so nothing is guessed from the narration, and all sit in
ONE pakMap item, so pakMap's per-item clear beat never wipes the map when footage comes and goes.

How the map's state survives footage (the plan's `pause_overlays`, default on):
  * the camera cannot move under footage and its drift stops (the engine already does this), so it resumes continuously;
  * the engine freezes the clocks of the map layers while footage is up, so a layer that was mid-animation at entry is in the
    same state when the map returns, and carries on from there;
  * a layer's planned END stays in narration time. A layer that ends at the footage boundary leaves under the dissolve (it is
    hidden by then). A layer whose planned end falls later under the footage is held `return_grace_s` after the map returns
    and then leaves, so the viewer sees the map resume rather than lose a layer they never saw go.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pakmap.compile import CompileError, CompileResult, compile_rows
from pakmap.schema import COLUMNS, Row

from .plan import EPS, Beat, HybridPlan, Layer, validate_plan

CARD_DEFAULT_ANCHORS = ("tr", "ml", "br")  # where a beat's 1st, 2nd and 3rd card sit when the plan does not say (the title owns the top-left)


@dataclass
class HybridCompile:
    result: CompileResult
    rows: List[Row]
    line_map: Dict[int, str]  # pakMap script row number -> "beat b2 · marker nbo"
    notes: List[str] = field(default_factory=list)

    @property
    def spec(self) -> dict:
        return self.result.spec

    @property
    def report(self):
        return self.result.report


class HybridCompileError(ValueError):
    def __init__(self, problems: List[str], raw: Optional[List[str]] = None):
        super().__init__("; ".join(problems))
        self.problems = problems
        self.raw = raw or []


def spec_extra(plan: HybridPlan) -> dict:
    # media_lazy: video clips are cut into frames when needed and deleted when done, so the disk use does not grow with the length of the video
    return {"hybrid": {"pause_overlays": bool(plan.setting("pause_overlays"))}, "media_lazy": True}


def layer_end(plan: HybridPlan, beat: Beat, lay: Layer, notes: Optional[List[str]] = None) -> float:
    """The narration second a layer leaves, from its `until` / `hold`, adjusted for footage as described above."""
    d, grace = float(plan.setting("dissolve_s")), float(plan.setting("return_grace_s"))
    u = lay.until
    if lay.hold is not None and u == "beat_end":
        end = lay.t + lay.hold
    elif isinstance(u, (int, float)):
        end = float(u)
    elif u == "end":
        end = plan.duration
    elif u == "after_footage":
        i = plan.beats.index(beat)
        later = plan.beats[i + 1:]
        foot = next((k for k, b in enumerate(later) if b.mode == "footage"), None)
        nxt = next((b for b in later[foot + 1:] if plan.is_map_mode(b)), None) if foot is not None else None   # map or map_footage
        if foot is None:
            end = beat.end            # no footage follows, so there is nothing to carry the layer across: it leaves with its beat (never held to the end of the video)
        else:
            end = nxt.end if nxt is not None else plan.duration
    else:
        end = beat.end
    end = min(end, plan.duration)
    windows = plan.footage_windows()
    for k, (fs, fe) in enumerate(windows):
        if lay.t < fs - EPS and fs - EPS < end <= fe + EPS:
            if end <= fs + d + EPS:
                end = fs + d  # leaves under the dissolve-in, hidden by the time it goes
            else:
                nxt_start = windows[k + 1][0] if k + 1 < len(windows) else plan.duration
                held = min(fe + grace, nxt_start, plan.duration)
                if notes is not None:
                    notes.append(f"layer {lay.id}: its planned end ({end:g}s) falls under footage ({fs:g}-{fe:g}s); it is held until {held:g}s, just after the map returns")
                end = held
            break
    return end


def beat_window(plan: HybridPlan, beat: Beat) -> Tuple[float, float]:
    """When a footage beat's footage is on screen, dissolves included (see HybridPlan.footage_windows)."""
    windows = [b for b in plan.beats if b.mode == "footage"]
    return plan.footage_windows()[windows.index(beat)]


def _clip_spans(plan: HybridPlan, beat: Beat) -> List[Tuple[float, float]]:
    n, x = len(beat.clips), float(plan.setting("dissolve_s"))
    start, end = beat_window(plan, beat)
    D = end - start
    if n == 1:
        return [(start, end)]
    if all(c.dur for c in beat.clips):
        spans, t = [], start
        for c in beat.clips:
            spans.append((t, t + float(c.dur)))
            t += float(c.dur) - x
        spans[-1] = (spans[-1][0], end)
        return spans
    L = (D + (n - 1) * x) / n
    return [(start + i * (L - x), start + i * (L - x) + L) for i in range(n - 1)] + [(start + (n - 1) * (L - x), end)]


def _bottom_band(lay: Layer) -> bool:
    """A caption (centred along the bottom) and a stat chip in a bottom corner share the same strip of the screen."""
    return lay.type == "caption" or (lay.type == "stat" and (lay.anchor or "br") in ("br", "bl"))


def text_collisions(plan: HybridPlan, beat: Beat, notes: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """Layers that would be drawn on top of each other: {layer id: {"end": seconds} or {"anchor": "tr"}}. The earlier one leaves just before
    the later one arrives when it has had time to be read; otherwise a stat chip moves to the top-right corner."""
    spans = sorted(((lay, layer_end(plan, beat, lay)) for lay in beat.layers if lay.type in ("stat", "caption") and _bottom_band(lay)),
                   key=lambda p: p[0].t)
    out: Dict[str, Dict[str, Any]] = {}
    for i, (first, f_end) in enumerate(spans):
        for second, _s_end in spans[i + 1:]:
            if second.t >= out.get(first.id, {}).get("end", f_end) - EPS:
                continue
            if first.type == "stat" and second.type == "stat" and (first.anchor or "br") != (second.anchor or "br"):
                continue  # one in each corner: they sit side by side
            end = out.get(first.id, {}).get("end", f_end)
            if second.t - first.t >= 2.0:
                out[first.id] = {"end": round(second.t - 0.25, 3)}
                if notes is not None:
                    notes.append(f"layer {first.id} leaves {end - second.t + 0.25:g}s early so it does not sit on top of {second.id}")
            else:
                mover = first if first.type == "stat" else second if second.type == "stat" else None
                if mover is not None and mover.id not in out:
                    out[mover.id] = {"anchor": "tr"}
                    if notes is not None:
                        notes.append(f"layer {mover.id} moves to the top-right corner so it does not sit on top of {(second if mover is first else first).id}")
    return out


def plan_to_rows(plan: HybridPlan) -> Tuple[List[Row], Dict[int, str], List[str]]:
    problems = validate_plan(plan)
    if problems:
        raise HybridCompileError(problems)
    rows: List[Row] = []
    line_map: Dict[int, str] = {}
    notes: List[str] = []
    x = float(plan.setting("dissolve_s"))

    def add(label: str, **kw: Any) -> Row:
        row = Row(line=len(rows) + 2, item_no=1, **kw)
        rows.append(row)
        line_map[row.line] = label
        return row

    prev_footage_end: Optional[float] = None  # when the previous beat was footage: where its last clip ends
    for beat in plan.beats:
        if plan.is_map_mode(beat):
            prev_footage_end = None
            for c in beat.camera:
                params = {"zoom_delta": c.zoom_delta} if c.zoom_delta is not None else {}
                add(f"beat {beat.id} · camera {c.action}", layer_type="camera", layer_id=f"{beat.id}_cam_{c.action}_{len(rows)}", camera_action=c.action,
                    t_start=0.0 if c.action == "start" else c.t, geo_ref=c.place, frame=c.frame, camera_dur=c.dur, params=params)
            clash = text_collisions(plan, beat, notes)
            for lay in beat.layers:
                end = clash.get(lay.id, {}).get("end") or layer_end(plan, beat, lay, notes)
                kw: Dict[str, Any] = dict(layer_type=lay.type, layer_id=lay.id, t_start=lay.t, t_end=end, params=dict(lay.params))
                label = f"beat {beat.id} · {lay.type} {lay.id}"
                if lay.type == "hud_title":
                    kw.update(label_text=lay.label, sub_text=lay.sub)
                elif lay.type in ("marker", "zone_label"):
                    kw.update(geo_ref=lay.place, label_text=lay.label, sub_text=lay.sub, color_role=lay.role)
                elif lay.type == "fill":
                    kw.update(geo_ref=lay.place, color_role=lay.role or "subject")
                elif lay.type == "line":
                    kw.update(geo_ref=";".join(lay.places), line_kind=lay.kind)
                elif lay.type == "stat":
                    kw.update(value_from=lay.value_from, value_to=lay.value_to, value_format=lay.format or "#,##0", sub_text=lay.sub, anchor=clash.get(lay.id, {}).get("anchor") or lay.anchor or "br")
                elif lay.type == "caption":
                    kw.update(label_text=lay.text, sub_text=lay.sub, anchor=lay.anchor or "bc")
                add(label, **kw)
            cards = beat.cards  # MAP+FOOTAGE: the map says where, photo cards show what it looks like (up to MAX_CARDS, in different corners)
            landed = max([c.t + (c.dur or 0.0) for c in beat.camera if c.action == "fly_to"] or [0.0]) + 0.25
            for k, sp in enumerate(cards):
                # a card follows the map from the place it first appears: born during a camera fly-in it is dragged off the screen,
                # so it waits for the camera to arrive (unless that would leave it no time to be read)
                if sp.t is not None:
                    t0 = sp.t
                elif k == 0:
                    t0 = min(beat.start + 1.0, beat.end - 2.0)
                else:
                    t0 = beat.start + (beat.end - beat.start) * k / len(cards)  # the others are spread over the beat
                if t0 < landed and beat.end - landed - 0.4 >= 1.5:
                    t0 = landed
                room = beat.end - t0 - 0.4
                if room < 2.0 and beat.end - beat.start - 0.4 >= 2.0:
                    # spoken in the last words of its beat: it comes up a little earlier so it can be seen, not refused
                    t0 = max(beat.start + 0.2, beat.end - 0.4 - 2.0)
                    notes.append(f"beat {beat.id}: photo card {k + 1} was brought forward to {t0:.1f}s so it stays on screen for at least 2 seconds")
                    room = beat.end - t0 - 0.4
                hold = min(sp.hold if sp.hold else 6.0, room)
                if hold < 1.0:
                    raise HybridCompileError([f"beat {beat.id}: no room for its " + (f"photo card {k + 1}" if len(cards) > 1 else "supporting card") + f" ({room:.1f}s left after it would appear)"])
                anchor = sp.anchor or CARD_DEFAULT_ANCHORS[k % len(CARD_DEFAULT_ANCHORS)]
                add(f"beat {beat.id} · supporting card" + (f" {k + 1}" if k else ""), layer_type="pip", layer_id=f"{beat.id}_support" + (f"{k + 1}" if k else ""),
                    t_start=t0, t_end=t0 + hold, asset_path=sp.asset, geo_ref=sp.place, label_text=sp.label, anchor=anchor, params={})
        else:
            spans = _clip_spans(plan, beat)
            if prev_footage_end is not None:  # footage straight after footage: the first clip dissolves in over the last one, never over the map
                spans[0] = (min(spans[0][0], prev_footage_end - x), spans[0][1])
            for k, (clip, (a, b)) in enumerate(zip(beat.clips, spans)):
                if b - a < 2 * x - EPS and len(beat.clips) > 1:
                    raise HybridCompileError([f"beat {beat.id}: clip {k + 1} would be on screen for only {b - a:.2f}s, shorter than its two {x:g}s dissolves; use fewer or shorter-overlap clips"])
                params: Dict[str, Any] = {"dissolve_s": x}
                if plan.setting("cover_ui") and not beat.keep_overlays:
                    params["cover_ui"] = True
                handed_over = k > 0 or prev_footage_end is not None
                if handed_over:
                    params["xfade_prev"] = True
                # a picture drifts slowly, a video does not: "auto" lets the renderer decide from the file actually fetched (the user may
                # have changed a clip's source to a still, or attached a local picture, after the plan was made)
                params["kenburns"] = True if clip.kenburns else "auto"
                params["fit"] = "slow"   # a clip shorter than its slot plays slower to cover it, then back and forth: never a hard restart (the engine decides from the real file)
                if clip.loop or is_video_asset(clip.asset):
                    params["loop"] = True  # a clip shorter than its slot repeats instead of freezing on its last frame (no effect on a longer one)
                # No transition sound unless the beat asks for one: a dissolve is not an event to announce (and a clip handing over to the next never is)
                sfx = (beat.transition_sound or "none") if not handed_over else "none"
                add(f"beat {beat.id} · footage clip {k + 1}", layer_type="media_full", layer_id=f"{beat.id}_c{k + 1}", t_start=a, t_end=b, asset_path=clip.asset, params=params, sfx=sfx)
            prev_footage_end = spans[-1][1]
    # the always-on drift (what makes the map feel alive between camera moves)
    add("plan · camera drift", layer_type="camera", layer_id="drift", camera_action="drift", t_start=0.0, params={"pct_per_s": float(plan.setting("drift_pct_per_s")), "heading_deg": 60})
    return rows, line_map, notes


def is_video_asset(asset: str) -> bool:
    a = (asset or "").strip().lower()
    return a.split(":", 1)[0] in ("stock_video", "flow_video", "youtube_video") or a.endswith((".mp4", ".mov", ".webm", ".mkv", ".m4v"))


def longest_slot(plan: HybridPlan) -> float:
    """The longest time any single footage clip is on screen: how much footage a provider should be asked for."""
    longest = 0.0
    for b in plan.beats:
        if b.mode == "footage" and b.clips:
            longest = max(longest, max(e - s for s, e in _clip_spans(plan, b)))
    return longest


def rows_to_csv(rows: List[Row]) -> str:
    """The compiled pakMap script (what pakmap.schema.parse_csv reads back), for the work folder and for the pakMap generator."""
    import csv
    import io

    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in rows:
        cells = []
        for col in COLUMNS:
            v = getattr(r, col, "")
            if col == "params":
                v = json.dumps(v, ensure_ascii=False, separators=(",", ":")) if v else ""
            cells.append("" if v is None else (f"{v:g}" if isinstance(v, float) else str(v)))
        w.writerow(cells)
    return out.getvalue()


def explain(plan_line_map: Dict[int, str], messages: List[str]) -> List[str]:
    """Replace 'row N' in a compiler message by the beat/layer it came from."""
    import re

    out = []
    for m in messages:
        mm = re.match(r"^(renderer rule: )?row (\d+): (.*)$", str(m), re.S)
        if mm and int(mm.group(2)) in plan_line_map:
            out.append(f"{plan_line_map[int(mm.group(2))]}: {mm.group(3)}")
        else:
            out.append(str(m))
    return out


def compile_plan(plan: HybridPlan, *, base_dir: "str | Path | None" = None, watermark: Optional[dict] = None, width: int = 1920, height: int = 1080, fps: int = 30,
                 validate: bool = True, media_map: Optional[Dict[Any, Optional[str]]] = None) -> HybridCompile:
    rows, line_map, notes = plan_to_rows(plan)
    try:
        res = compile_rows(rows, [], duration=plan.duration, width=width, height=height, fps=fps, base_dir=base_dir, watermark=watermark, validate=validate,
                           media_map=media_map, spec_extra=spec_extra(plan))
    except CompileError as exc:
        raise HybridCompileError(explain(line_map, exc.report.errors), exc.report.errors) from exc
    res.report.warnings[:] = explain(line_map, res.report.warnings)
    return HybridCompile(res, rows, line_map, notes)
