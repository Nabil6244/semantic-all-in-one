"""Camera planning for map beats, from the application's own geometry (pakmap.geo: view_for, fit, merc_y; hybrid.geo.resolve). Nothing here draws or moves anything: it chooses the camera
steps a Hybrid map beat carries (`start`, `fly_to`, `pull_back`, `push_in`), proves that every place a layer will outline or label lies inside the view in force when the layer appears,
and says why when it cannot. The Hybrid plan gives the camera one place and a frame, so "show both Koreas" is a view centred on one of them, pulled back until the other fits.

The view in force at time t is the latest step that is at least 60% done (a move still under way is not counted): that is what the viewer sees when the layer appears."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

MARGIN = 0.04                    # the whole bounding box must sit this fraction of the frame inside every edge (the camera also drifts slowly)
READY = 0.6                      # a move counts as done at this fraction of its duration
MIN_SINGLE_ZOOM = 3.0            # a single view that needs a lower zoom than this makes the places too small to read: the camera moves between them instead
DELTAS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5)
FRAMES = ("country", "region", "continental")
FIRST_MOVE_DUR = 0.7
LATER_MOVE_DUR = 1.4
GAP_S = 0.1                      # two moves never overlap, and the next starts this long after the last one ends


def _geo():
    from hybrid import geo
    return geo


def _pk():
    from pakmap import geo
    return geo


def view_box(lon: float, lat: float, zoom: float, w: int = 1920, h: int = 1080) -> Tuple[float, float, float, float]:
    """(west, south, east, north) of the frame for a camera at lon, lat, zoom (512-px world tile, the engine's convention)."""
    G = _pk()
    k = 512 * 2 ** zoom
    dx = w / k * 360.0
    cy, dy = G.merc_y(lat), h / k
    ys = sorted((G.merc_lat(cy - dy / 2), G.merc_lat(cy + dy / 2)))
    return (lon - dx / 2, ys[0], lon + dx / 2, ys[1])


CAPTION_BAND = 0.14              # the bottom of the frame is where captions and statistics sit: planned views keep this much extra room under the places


def inside(box: Sequence[float], bbox: Sequence[float], margin: float = MARGIN, bottom: float = 0.0) -> bool:
    w, s, e, n = box
    bw, bs, be, bn = bbox
    mx, my = (e - w) * margin, (n - s) * margin
    return bw >= w + mx and be <= e - mx and bs >= s + my + (n - s) * bottom and bn <= n - my


def place_bbox(name: str) -> Tuple[float, float, float, float]:
    loc = _geo().resolve(name)
    if getattr(loc, "is_area", False):
        return tuple(loc.bbox)
    return (loc.lon - 0.02, loc.lat - 0.02, loc.lon + 0.02, loc.lat + 0.02)


def step_view(place: str, frame: str) -> Tuple[float, float, float]:
    return _pk().view_for(_geo().resolve(place), frame)


def plan_views(beats: Sequence[Dict[str, Any]]) -> List[Tuple[float, Tuple[float, float, float], str]]:
    """[(time the view is in force, (lon, lat, zoom), step description)] for the camera steps of the map beats, in the order the application compiles them (a `pull_back` or `push_in` with
    no place changes the zoom by `zoom_delta`, default 1)."""
    out: List[Tuple[float, Tuple[float, float, float], str]] = []
    cur: Optional[Tuple[float, float, float]] = None
    steps = sorted(((0.0 if c["action"] == "start" else float(c.get("t", b["start"])), c, b) for b in beats if b.get("mode") in ("map", "map_footage") for c in b.get("camera", [])), key=lambda x: x[0])
    for t, c, b in steps:
        try:
            if c.get("place"):
                v = step_view(c["place"], c.get("frame", ""))
            elif cur is not None and c["action"] in ("push_in", "pull_back"):
                d = float(c.get("zoom_delta") or 1.0)
                v = (cur[0], cur[1], cur[2] + (d if c["action"] == "push_in" else -d))
            else:
                continue
        except Exception:
            continue
        cur = v
        done = t if c["action"] == "start" else t + READY * float(c.get("dur") or (2.2 if c["action"] == "fly_to" else 8.0 if c["action"] == "push_in" else 2.0))
        out.append((done, v, f"{c['action']} {c.get('place', '')}".strip()))
    return out


def view_at(views, t: float) -> Optional[Tuple[float, float, float]]:
    cur = None
    for tt, v, _d in sorted(views, key=lambda x: x[0]):
        if tt <= t + 1e-9:
            cur = v
    return cur


def check_framing(plan: Dict[str, Any]) -> List[str]:
    """Findings (empty when every place a map layer outlines, labels or marks is fully inside the view in force when the layer appears)."""
    views = plan_views(plan.get("beats", []))
    found: List[str] = []
    for b in plan.get("beats", []):
        if b.get("mode") not in ("map", "map_footage"):
            continue
        for lay in b.get("layers", []):
            if lay.get("type") not in ("fill", "marker", "zone_label") or not lay.get("place"):
                continue
            v = view_at(views, float(lay["t"]))
            try:
                bb = place_bbox(lay["place"])
            except Exception as exc:
                found.append(f"beat {b['id']}: layer {lay['id']}: {lay['place']!r} cannot be located ({str(exc)[:60]})")
                continue
            if v is None or not inside(view_box(*v), bb):
                found.append(f"beat {b['id']}: layer {lay['id']}: {lay['place']!r} is not fully inside the camera view when the layer appears at {float(lay['t']):.1f} s")
    return found


def _candidates(places: Sequence[str]):
    seen = []
    for p in places:
        if p in seen:
            continue
        seen.append(p)
        for fr in FRAMES:
            try:
                base = step_view(p, fr)
            except Exception:
                continue
            for d in DELTAS:
                yield p, fr, d, (base[0], base[1], base[2] - d)


def plan_camera(targets: Sequence[Dict[str, Any]], beat_start: float, beat_end: float, first_map: bool, current: Optional[Tuple[float, float, float]] = None,
                allow_push: bool = True) -> Dict[str, Any]:
    """targets: [{name, t}] (t = the time the place's layer wants to appear), in spoken order. Returns {start, moves, view, ready, rejected, notes}:
    `start` {place, frame} for the first map beat, `moves` camera step dicts (fly_to, pull_back, push_in) with absolute times, `view` the (lon, lat, zoom) in force at the end,
    `ready` {name: earliest layer time}, `rejected` [{place, reason}] for places the camera cannot show in this beat."""
    out: Dict[str, Any] = {"start": None, "moves": [], "view": current, "ready": {}, "rejected": [], "notes": []}
    boxes: Dict[str, Tuple[float, float, float, float]] = {}
    for tg in targets:
        try:
            boxes[tg["name"]] = place_bbox(tg["name"])
        except Exception as exc:
            out["rejected"].append({"place": tg["name"], "reason": f"the place cannot be located ({str(exc)[:60]})"})
    live = [tg for tg in targets if tg["name"] in boxes]
    if not live:
        return out
    names = [tg["name"] for tg in live]
    first_t = min(float(tg["t"]) for tg in live)
    # 1. the view already in force (a later map beat of the same story) shows everything
    if current is not None and all(inside(view_box(*current), boxes[n]) for n in names):
        out["notes"].append("the camera already shows every place: no move")
        out["ready"] = {n: 0.0 for n in names}
        return out
    # 2. one view for all of them: the tightest centre-frame-pull_back combination that holds every bounding box
    best = None
    for p, fr, d, v in _candidates(names):
        if v[2] < MIN_SINGLE_ZOOM - 1e-9:
            continue
        if not all(inside(view_box(*v), boxes[n], MARGIN, CAPTION_BAND) for n in names):
            continue
        key = (round(v[2], 3), -d, -FRAMES.index(fr))
        if best is None or key > best[0]:
            best = (key, p, fr, d, v)
    t0 = beat_start + 0.05
    if best is not None:
        _k, p, fr, d, v = best
        base = step_view(p, fr)
        if first_map:
            out["start"] = {"place": p, "frame": fr}
            cur_end = t0
            if d > 0:
                dur = max(0.4, min(FIRST_MOVE_DUR, max(0.4, first_t - t0 - 0.05) / READY if first_t - t0 > 0 else FIRST_MOVE_DUR))
                out["moves"].append({"action": "pull_back", "t": round(t0, 3), "dur": round(dur, 3), "zoom_delta": d})
                cur_end = t0 + dur
        else:
            dur = FIRST_MOVE_DUR
            out["moves"].append({"action": "fly_to", "t": round(t0, 3), "dur": dur, "place": p, "frame": fr})
            cur_end = t0 + dur
            if d > 0:
                t1 = cur_end + GAP_S
                out["moves"].append({"action": "pull_back", "t": round(t1, 3), "dur": 0.6, "zoom_delta": d})
                cur_end = t1 + 0.6
        ready = (out["moves"][-1]["t"] + READY * out["moves"][-1]["dur"]) if out["moves"] else beat_start
        out["ready"] = {n: round(max(0.0, ready), 3) for n in names}
        out["view"] = v
        out["notes"].append(f"one view for {', '.join(names)}: {p} at frame {fr}" + (f", pulled back {d:g}" if d else "") + f" (zoom {v[2]:.2f})")
        # a slow push-in keeps a long single view alive without losing any place
        if allow_push and beat_end - beat_start >= 5.5:
            t_push = round(max((out["moves"][-1]["t"] + out["moves"][-1]["dur"]) if out["moves"] else beat_start, beat_start + 0.45 * (beat_end - beat_start)) + GAP_S, 3)
            nv = (v[0], v[1], v[2] + 0.5)
            if t_push + 3.2 <= beat_end - 0.3 and all(inside(view_box(*nv), boxes[n], 0.08, CAPTION_BAND) for n in names):
                out["moves"].append({"action": "push_in", "t": t_push, "dur": 3.0, "zoom_delta": 0.5})
                out["view"] = nv
                out["notes"].append(f"slow push-in at {t_push:.1f} s: every place stays inside the frame")
        return out
    # 3. no single view is good enough: the camera goes to each place in turn, each fully framed on its own
    cur_end = t0 - GAP_S
    last_view = current
    for i, tg in enumerate(live):
        n, tt = tg["name"], float(tg["t"])
        fr = "country" if getattr(_geo().resolve(n), "is_area", False) else "region"
        v = step_view(n, fr)
        if not inside(view_box(*v), boxes[n]):
            out["rejected"].append({"place": n, "reason": "even a camera centred on it does not show the whole place"})
            continue
        if last_view is not None and inside(view_box(*last_view), boxes[n]):
            out["ready"][n] = round(max(0.0, tt), 3)
            continue
        if first_map and last_view is None and out["start"] is None:
            out["start"] = {"place": n, "frame": fr}
            out["ready"][n] = round(beat_start, 3)
            last_view = v
            cur_end = beat_start
            continue
        dur = FIRST_MOVE_DUR if i == 0 else LATER_MOVE_DUR
        t = max(cur_end + GAP_S, tt - dur * READY - 0.1, t0 if i == 0 else beat_start)
        if t + dur > beat_end - 0.3:
            out["rejected"].append({"place": n, "reason": f"the camera cannot reach it inside this beat (spoken at {tt:.1f} s, the beat ends at {beat_end:.1f} s)"})
            continue
        out["moves"].append({"action": "fly_to", "t": round(t, 3), "dur": round(dur, 3), "place": n, "frame": fr})
        out["ready"][n] = round(t + READY * dur, 3)
        cur_end = t + dur
        last_view = v
    out["view"] = last_view
    out["notes"].append("no single view holds every place: the camera goes to each in turn")
    return out
