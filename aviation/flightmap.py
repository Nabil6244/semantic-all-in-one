"""Aviation flight map (docs/aviation/PLAN.md N5): the Vistara-style dark map that carries a flight story.

    lay_flight_map(t, dur, params) -> RGBA 1280x720 or None      (same contract as the War cards)

params
  airports     [id, ...]  IATA ids from aviation/data/airports.json: a dot + caps label each (unknown ids are skipped)
  active       id         gold glow that breathes on this airport
  route        {from, to, start, length}   gold dotted planned line; a solid gold flown line with an aircraft mark grows over it
  track        [id or (lat, lon), ...]     a flown path through several points (drawn instead of a straight route)
  holding      {at: id | (lat, lon), laps, start, length, leg_km, radius_km, heading}  racetrack loops drawn lap by lap, each
               a little wider so they stack up like the reference
  callouts     [{from, to, label?, start}] thin white line + big distance label at its middle (label defaults to the distance)
  range_ring   {at, km}   pink translucent range circle
  crossed      [id, ...]  the airport's label struck through in red, dimmed
  bbox         (lon0, lat0, lon1, lat1) to override the automatic fit; pad (default 0.22)
  storms       [{at, km, label, start, cells}]  soft drifting cloud cells (seeded by place), label beside them
  t0, total    for a map split around a footage break: seconds already played and the whole map's length (no restart)
  fetch_tile, cache       elevation source and cache folder (tests use a fake; default: free Terrarium tiles, cached once)
The camera always drifts in slowly (about 5 % over the shot): the map is never a still frame. Labels are the catalog's city names.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from cinematic_explainer.war import motion as M
from cinematic_explainer.war import tokens as T
from cinematic_explainer import look as L

from . import basemap as B
from . import catalog as C

W, H = T.W, T.H
GOLD = (242, 184, 64, 255)
GOLD_SOFT = (242, 184, 64, 190)
PINK = (232, 82, 122)
RED = (232, 60, 60, 255)
MARGIN = 1.10                  # the basemap covers 10 % more than the view so the camera can move


def _airport(x: Any) -> Optional[dict]:
    return C.get_airport(str(x).upper()) if isinstance(x, str) else None


def _latlon(x: Any) -> Optional[Tuple[float, float]]:
    if isinstance(x, (list, tuple)) and len(x) == 2:
        return float(x[0]), float(x[1])
    a = _airport(x)
    return (a["lat"], a["lon"]) if a else None


def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def distance_label(a: Any, b: Any, unit: str = "km") -> str:
    pa, pb = _latlon(a), _latlon(b)
    if not pa or not pb:
        return ""
    km = haversine_km(pa, pb)
    if unit == "nm":
        return f"~{int(round(km / 1.852 / 10.0) * 10)} NM"
    step = 10 if km >= 100 else 5
    return f"~{int(round(km / step) * step)} KM"


def racetrack_km(leg_km: float, radius_km: float, heading_deg: float = 0.0, steps: int = 72) -> List[Tuple[float, float]]:
    """A closed holding racetrack in km (east, north), starting at the inbound end, legs along `heading`."""
    pts: List[Tuple[float, float]] = []
    n = max(8, steps // 4)
    half = leg_km / 2.0
    # inbound leg (x = 0) going north, turn right over the top, outbound leg (x = 2r) going south, turn back at the bottom
    for i in range(n + 1):
        pts.append((0.0, -half + leg_km * i / n))
    for i in range(1, n + 1):
        a = math.pi - math.pi * i / n
        pts.append((radius_km + radius_km * math.cos(a), half + radius_km * math.sin(a)))
    for i in range(1, n + 1):
        pts.append((2 * radius_km, half - leg_km * i / n))
    for i in range(1, n + 1):
        a = -math.pi * i / n
        pts.append((radius_km + radius_km * math.cos(a), -half + radius_km * math.sin(a)))
    pts[-1] = pts[0]
    hd = math.radians(heading_deg)
    return [(x * math.cos(hd) + y * math.sin(hd), -x * math.sin(hd) + y * math.cos(hd)) for x, y in pts]


def _km_to_latlon(origin: Tuple[float, float], east: float, north: float) -> Tuple[float, float]:
    lat = origin[0] + north / 110.57
    lon = origin[1] + east / (111.32 * math.cos(math.radians(origin[0])))
    return lat, lon


def _holding_points(h: dict) -> List[List[Tuple[float, float]]]:
    at = _latlon(h.get("at"))
    if not at:
        return []
    laps = max(1, int(h.get("laps", 2)))
    leg, rad = float(h.get("leg_km", 22.0)), float(h.get("radius_km", 8.0))
    out = []
    for j in range(laps):
        k = 1.0 + 0.14 * j
        pts = racetrack_km(leg * k, rad * k, float(h.get("heading", 0.0)))
        out.append([_km_to_latlon(at, x - rad * k, y) for x, y in pts])
    return out


def _poly_partial(pts: Sequence[Tuple[float, float]], f: float) -> List[Tuple[float, float]]:
    return M.partial_polyline(list(pts), max(0.0, min(1.0, f))) if len(pts) > 1 else list(pts)


def _dotted(d: ImageDraw.ImageDraw, a: Tuple[float, float], b: Tuple[float, float], gap: float = 10.0, r: float = 1.9, fill=GOLD_SOFT) -> None:
    n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / gap))
    for i in range(n + 1):
        x, y = a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


# a top-down airliner, nose along +x, in units of its length (1.0)
_AIRLINER = [(0.50, 0.00), (0.44, 0.035), (0.10, 0.045), (0.02, 0.42), (-0.06, 0.42), (-0.06, 0.05), (-0.36, 0.045), (-0.44, 0.17),
             (-0.50, 0.17), (-0.47, 0.03), (-0.50, 0.0)]
_AIRLINER = _AIRLINER + [(x, -y) for x, y in reversed(_AIRLINER[1:-1])]


def _plane_mark(d: ImageDraw.ImageDraw, p: Tuple[float, float], q: Tuple[float, float], size: float = 40.0) -> None:
    """A white top-down airliner at q pointing from p to q (the reference's aircraft icon on the route)."""
    ang = math.atan2(q[1] - p[1], q[0] - p[0])
    pts = [(q[0] + size * (x * math.cos(ang) - y * math.sin(ang)), q[1] + size * (x * math.sin(ang) + y * math.cos(ang))) for x, y in _AIRLINER]
    d.polygon([(x + 2, y + 3) for x, y in pts], fill=(0, 0, 0, 120))
    d.polygon(pts, fill=(250, 250, 252, 255), outline=(40, 40, 46, 255))


def leg_curve(a: Tuple[float, float], b: Tuple[float, float], bend: float = 0.12, n: int = 48) -> List[Tuple[float, float]]:
    """A gently curved leg (quadratic Bezier bowed sideways by `bend` of its length), like the reference's route lines."""
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    cx, cy = mx - dy / L * L * bend * 2, my + dx / L * L * bend * 2
    return [((1 - u) ** 2 * a[0] + 2 * (1 - u) * u * cx + u * u * b[0], (1 - u) ** 2 * a[1] + 2 * (1 - u) * u * cy + u * u * b[1])
            for u in (k / n for k in range(n + 1))]


def _dotted_path(d: ImageDraw.ImageDraw, pts: Sequence[Tuple[float, float]], gap: float = 11.0, r: float = 2.0, fill=GOLD_SOFT) -> None:
    acc = 0.0
    for p0, p1 in zip(pts, pts[1:]):
        seg = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        while acc <= seg:
            x, y = p0[0] + (p1[0] - p0[0]) * acc / max(seg, 1e-6), p0[1] + (p1[1] - p0[1]) * acc / max(seg, 1e-6)
            d.ellipse([x - r, y - r, x + r, y + r], fill=fill)
            acc += gap
        acc -= seg


def _all_points(p: dict) -> List[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    for a in p.get("airports") or []:
        ll = _latlon(a)
        if ll:
            pts.append(ll)
    r = p.get("route") or {}
    for k in ("from", "to"):
        ll = _latlon(r.get(k))
        if ll:
            pts.append(ll)
    for x in p.get("track") or []:
        ll = _latlon(x)
        if ll:
            pts.append(ll)
    for lap in _holding_points(p.get("holding") or {}):
        pts.extend(lap)
    return pts


_TEX: List[Any] = []


def _cloud_texture():
    """A fixed fractal-noise field (0.35..1.0) the storm cells are multiplied by: made once, the same every frame."""
    if not _TEX:
        import numpy as _np

        rng = _np.random.default_rng(611)
        acc = _np.zeros((H, W), dtype=_np.float32)
        for size, wgt in ((6, 0.45), (14, 0.28), (34, 0.17), (90, 0.10)):
            small = rng.random((max(2, H * size // W), size)).astype(_np.float32)
            acc += wgt * _np.asarray(Image.fromarray((small * 255).astype("uint8"), "L").resize((W, H), Image.BICUBIC), dtype=_np.float32) / 255.0
        acc = (acc - acc.min()) / max(1e-6, acc.max() - acc.min())
        _TEX.append(0.35 + 0.65 * acc)
    return _TEX[0]


def _storms(img: Image.Image, storms: Sequence[dict], t: float, view, px) -> None:
    """Soft cloud cells around each storm centre, seeded by the place so every frame of a shot agrees; they drift slowly east and
    breathe, a label (the narration's gusts / distance) sits beside the cell."""
    if not storms:
        return
    import random
    import zlib

    kpp = B.km_per_px(view, W)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    labels = []
    for s in storms:
        at = _latlon(s.get("at"))
        if not at:
            continue
        k = M.ease_out(M.ramp(t, float(s.get("start", 0.0)), 0.8))
        if k <= 0:
            continue
        c = px(at)
        rad = float(s.get("km", 30.0)) / kpp
        rng = random.Random(zlib.crc32(f"{at[0]:.3f},{at[1]:.3f}".encode()))
        # several separate cells (the reference's cumulus puffs), each a cluster of soft blobs, not one wall of cloud
        for _ in range(int(s.get("cells", 5))):
            ang, dist = rng.uniform(0, 2 * math.pi), rad * (0.35 + 0.75 * rng.random())
            cx, cy = c[0] + dist * math.cos(ang), c[1] + dist * math.sin(ang)
            size = rad * rng.uniform(0.16, 0.26)
            for _ in range(6):
                a2, d2 = rng.uniform(0, 2 * math.pi), size * 0.8 * math.sqrt(rng.random())
                r = size * rng.uniform(0.45, 0.8) * (1.0 + 0.06 * math.sin(t * 0.9 + a2))
                x = cx + d2 * math.cos(a2) + t * 6.0          # drift east about 6 px/s
                y = cy + d2 * math.sin(a2) - t * 1.5
                d.ellipse([x - r, y - r, x + r, y + r], fill=(226, 230, 238, int(rng.uniform(110, 170) * k)))
        if s.get("label"):
            labels.append((c[0] + rad * 0.9, c[1] - 12, str(s["label"]).upper(), k))
    blur = max(3.0, min(14.0, sum(float(s.get("km", 30.0)) for s in storms) / len(storms) / kpp * 0.05))
    soft = lay.filter(ImageFilter.GaussianBlur(blur))
    tex = _cloud_texture()
    import numpy as _np
    a = _np.asarray(soft, dtype=_np.float32)
    a[..., 3] *= tex                                         # cloudy, broken edges and thin patches instead of smooth discs
    a[..., :3] *= (0.78 + 0.22 * tex)[..., None]             # and some shading inside each cell
    img.alpha_composite(Image.fromarray(a.clip(0, 255).astype("uint8"), "RGBA"))
    if labels:
        tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        td = ImageDraw.Draw(tl)
        for x, y, text, k in labels:
            td.text((x, y), text, font=T.font("bold", 24), fill=(250, 250, 252, int(255 * k)))
        img.alpha_composite(tl)


TRANS_S = 1.6                  # how long the camera takes to move from one framing to the next
CLOSE_KM = 150.0               # a one-airport framing shows about this much ground across


def _focus_bbox(p: dict, focus: Sequence[str]):
    pts = [ll for ll in (_latlon(a) for a in focus) if ll]
    if not pts:
        return None
    if len(pts) == 1:
        h = p.get("holding") or {}
        if _latlon(h.get("at")) == pts[0]:
            for lap in _holding_points(h):
                pts.extend(lap)
        return B.fit_bbox(pts, pad=0.25, min_km=CLOSE_KM)
    return B.fit_bbox(pts, pad=0.35)


def _merc_lerp(a, b, k: float):
    ax0, ay0, ax1, ay1 = B.bbox_merc(a)
    bx0, by0, bx1, by1 = B.bbox_merc(b)
    m = [ax0 + (bx0 - ax0) * k, ay0 + (by0 - ay0) * k, ax1 + (bx1 - ax1) * k, ay1 + (by1 - ay1) * k]
    lon0, lat1 = B.unmerc(m[0], m[1])
    lon1, lat0 = B.unmerc(m[2], m[3])
    return lon0, lat0, lon1, lat1


def _union(a, b):
    ax0, ay0, ax1, ay1 = B.bbox_merc(a)
    bx0, by0, bx1, by1 = B.bbox_merc(b)
    lon0, lat1 = B.unmerc(min(ax0, bx0), min(ay0, by0))
    lon1, lat0 = B.unmerc(max(ax1, bx1), max(ay1, by1))
    return lon0, lat0, lon1, lat1


def view_at(p: dict, t: float, dur: float):
    """(view bbox, source bbox for the terrain) at time t. Without `views`: one framing of everything. With them: each keyframe's framing,
    the camera easing over TRANS_S from the previous one; always a slow push-in so the map never sits still."""
    return _camera(p, t, dur)[0]


def _camera(p: dict, t: float, dur: float):
    pts = _all_points(p)
    whole = tuple(p["bbox"]) if p.get("bbox") else B.fit_bbox(pts, pad=float(p.get("pad", 0.22)))
    keys = [(float(v.get("start", 0.0)), _focus_bbox(p, v.get("focus") or [])) for v in (p.get("views") or [])]
    keys = [(st, bb) for st, bb in keys if bb]
    if not keys:
        z, dx, dy = _drift(t)
        return B.scale_bbox(whole, z, dx, dy), whole
    idx = max([i for i, (st, _) in enumerate(keys) if st <= t + 1e-9] or [0])
    st, cur = keys[idx]
    src = cur
    if idx > 0 and t - st < TRANS_S:
        prev = keys[idx - 1][1]
        cur = _merc_lerp(prev, cur, M.ease_in_out(M.clamp01((t - st) / TRANS_S)))
        src = _union(prev, keys[idx][1])
    z, dx, dy = _drift(t - st)
    return B.scale_bbox(cur, z, dx, dy), src


DRIFT_ZOOM_PER_S = 0.014      # the camera never stops: ~1.4 % closer each second (visible, calm)
DRIFT_PAN_PER_S = 0.003
DRIFT_MAX = 0.15              # never so close that a route's far end leaves the frame (framings are padded ~25-35 %)


def _drift(age: float) -> Tuple[float, float, float]:
    """(scale, pan x, pan y) of the slow push-in, from the seconds since the camera settled on its framing. Time-based: a framing that
    holds 7 s or 60 s moves at the same calm pace (spread over the time to the next framing it was ~4 % a minute: a still screen)."""
    age = max(0.0, age)
    a = age * age / 3.0 if age < 1.5 else age - 0.75          # eases in over 1.5 s (no jolt), then a steady pace
    zoom = min(DRIFT_MAX, DRIFT_ZOOM_PER_S * a)
    pan = min(DRIFT_MAX / 5.0, DRIFT_PAN_PER_S * a)
    return 1.0 - zoom, pan, -0.7 * pan


def lay_flight_map(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    pts = _all_points(p)
    if not pts:
        return None
    # a map split around a footage break carries on where it was: t0 = time already played, total = the whole map's length
    t, dur = t + float(p.get("t0", 0.0)), float(p.get("total", dur))
    view, src = _camera(p, t, dur)
    big = B.scale_bbox(src, MARGIN)
    bw, bh = int(W * MARGIN), int(H * MARGIN)
    base = B.relief(big, (bw, bh), p.get("fetch_tile"), p.get("cache"))
    bx0, by0, bx1, by1 = B.bbox_merc(big)
    vx0, vy0, vx1, vy1 = B.bbox_merc(view)
    box = ((vx0 - bx0) / (bx1 - bx0) * bw, (vy0 - by0) / (by1 - by0) * bh, (vx1 - bx0) / (bx1 - bx0) * bw, (vy1 - by0) / (by1 - by0) * bh)
    img = base.transform((W, H), Image.EXTENT, box, Image.BILINEAR).convert("RGBA")

    def px(ll: Tuple[float, float]) -> Tuple[float, float]:
        return B.to_px(view, ll[0], ll[1], W, H)

    _storms(img, p.get("storms") or [], t, view, px)

    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)

    # range ring (under everything)
    rr = p.get("range_ring") or {}
    at = _latlon(rr.get("at"))
    if at and rr.get("km"):
        c = px(at)
        rad = float(rr["km"]) / B.km_per_px(view, W)
        ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse([c[0] - rad, c[1] - rad, c[0] + rad, c[1] + rad], fill=PINK + (52,), outline=PINK + (170,), width=2)
        over.alpha_composite(L.fade(ring, M.ease_out(M.ramp(t, float(rr.get("start", 0.3)), 0.6))))

    # planned route (dotted) and flown line
    r = p.get("route") or {}
    a, b = _latlon(r.get("from")), _latlon(r.get("to"))
    track = [ll for ll in (_latlon(x) for x in (p.get("track") or [])) if ll]
    if a and b and not track:
        track = [a, b]
    legs = [lg for lg in (p.get("legs") or []) if _latlon(lg.get("from")) and _latlon(lg.get("to"))]
    if legs:
        track = []                                     # legs replace the single route: each appears when it is said
        live = None
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gdr = ImageDraw.Draw(glow)
        for n_, lg in enumerate(legs):
            st = float(lg.get("start", 0.4))
            if t < st - 0.3:
                continue
            pts_ = leg_curve(px(_latlon(lg["from"])), px(_latlon(lg["to"])), bend=0.10 if n_ % 2 == 0 else -0.10)
            kk = M.ease_out(M.ramp(t, st - 0.3, 0.5))
            dl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            _dotted_path(ImageDraw.Draw(dl), pts_)
            over.alpha_composite(L.fade(dl, kk))
            f = M.ease_in_out(M.ramp(t, st, float(lg.get("length", 3.0))))
            if f > 0:
                flown = _poly_partial(pts_, f)
                if len(flown) > 1:
                    gdr.line(flown, fill=(242, 184, 64, 120), width=12, joint="curve")
                    d.line(flown, fill=GOLD, width=4, joint="curve")
                    live = (flown[-2], flown[-1])
        over.alpha_composite(glow.filter(ImageFilter.GaussianBlur(6)), (0, 0))
        if live and math.hypot(live[1][0] - live[0][0], live[1][1] - live[0][1]) > 0.5:
            _plane_mark(d, live[0], live[1])
    if len(track) > 1:
        tp = [px(ll) for ll in track]
        for i in range(len(tp) - 1):
            _dotted(d, tp[i], tp[i + 1])
        f = M.ease_in_out(M.ramp(t, float(r.get("start", 0.4)), float(r.get("length", max(1.0, dur * 0.6)))))
        flown = _poly_partial(tp, f)
        if len(flown) > 1 and f > 0:
            d.line(flown, fill=GOLD, width=3, joint="curve")
            _plane_mark(d, flown[-2], flown[-1])

    # holding loops, lap by lap
    h = p.get("holding") or {}
    laps = _holding_points(h)
    if laps:
        prog = M.ramp(t, float(h.get("start", 0.4)), float(h.get("length", max(1.0, dur * 0.7)))) * len(laps)
        for j, lap in enumerate(laps):
            if prog <= j:
                break
            lp = _poly_partial([px(ll) for ll in lap], min(1.0, prog - j))
            if len(lp) > 1:
                d.line(lp, fill=GOLD if j == len(laps) - 1 or prog < j + 1 else GOLD_SOFT, width=3, joint="curve")

    # distance callouts
    for co in p.get("callouts") or []:
        ca, cb = _latlon(co.get("from")), _latlon(co.get("to"))
        if not ca or not cb:
            continue
        kk = M.ease_out(M.ramp(t, float(co.get("start", 0.5)), 0.5))
        if kk <= 0:
            continue
        pa, pb = px(ca), px(cb)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.line([pa, (pa[0] + (pb[0] - pa[0]) * kk, pa[1] + (pb[1] - pa[1]) * kk)], fill=(235, 238, 245, 210), width=2)
        label = str(co.get("label") or distance_label(co.get("from"), co.get("to")))
        f = T.font("bold", 34)
        mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
        ld.text((mx + 16, my - 20), label, font=f, fill=(250, 250, 252, 255))
        over.alpha_composite(L.fade(lay, kk))

    # airports: dot, label, active glow, crossed out
    active = str(p.get("active") or "").upper()
    crossed = {str(x).upper() for x in (p.get("crossed") or [])}
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    fl = T.font("bold", 21)
    appear = p.get("appear") or {}
    for aid in p.get("airports") or []:
        ap = _airport(aid)
        if not ap:
            continue
        pop = M.ease_out(M.ramp(t, float(appear.get(ap["id"], -1.0)) - 0.05, 0.45))
        if pop <= 0.0:
            continue                                   # this airport has not been named yet
        if pop < 1.0:                                  # pops in: drawn on its own layer, faded
            lay_ = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d_save, d = d, ImageDraw.Draw(lay_)
        x, y = px((ap["lat"], ap["lon"]))
        if ap["id"] == active:
            breathe = 0.75 + 0.25 * math.sin(t * 2.2)
            gr = 26 * breathe
            gd.ellipse([x - gr, y - gr, x + gr, y + gr], fill=(242, 184, 64, int(150 * breathe)))
        d.ellipse([x - 6, y - 6, x + 6, y + 6], outline=GOLD, width=2)
        d.ellipse([x - 2.5, y - 2.5, x + 2.5, y + 2.5], fill=GOLD)
        name = str(ap.get("city") or ap["name"]).upper()
        dim = ap["id"] in crossed
        col = (150, 150, 158, 255) if dim else (250, 250, 252, 255)
        tw = d.textlength(name, font=fl)
        lx, ly = x - tw - 14, y - 26
        d.text((lx, ly), name, font=fl, fill=col)
        d.text((lx + tw - d.textlength(ap["id"], font=T.font("regular", 12)), ly + 24), ap["id"], font=T.font("regular", 12), fill=(190, 194, 204, 220))
        if dim:
            d.line([(lx - 3, ly + 12), (lx + tw + 3, ly + 12)], fill=RED, width=3)
        if pop < 1.0:
            over.alpha_composite(L.fade(lay_, pop))
            d = d_save
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10)))
    img.alpha_composite(over)
    ImageDraw.Draw(img).text((14, H - 18), B.CREDIT, font=T.font("regular", 10), fill=(150, 154, 164, 160))
    return img
