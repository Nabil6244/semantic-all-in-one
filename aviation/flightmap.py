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


def _plane_mark(d: ImageDraw.ImageDraw, p: Tuple[float, float], q: Tuple[float, float]) -> None:
    ang = math.atan2(q[1] - p[1], q[0] - p[0])
    pts = [(9, 0), (-6, -6), (-3, 0), (-6, 6)]
    d.polygon([(q[0] + x * math.cos(ang) - y * math.sin(ang), q[1] + x * math.sin(ang) + y * math.cos(ang)) for x, y in pts], fill=GOLD)


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
        for _ in range(int(s.get("cells", 16))):
            ang, dist = rng.uniform(0, 2 * math.pi), rad * math.sqrt(rng.random())
            r = rad * rng.uniform(0.32, 0.58) * (1.0 + 0.06 * math.sin(t * 0.9 + ang))
            x = c[0] + dist * math.cos(ang) + t * 6.0          # drift east about 6 px/s
            y = c[1] + dist * math.sin(ang) - t * 1.5
            d.ellipse([x - r, y - r, x + r, y + r], fill=(222, 226, 234, int(rng.uniform(90, 150) * k)))
        if s.get("label"):
            labels.append((c[0] + rad * 0.9, c[1] - 12, str(s["label"]).upper(), k))
    blur = max(5.0, min(28.0, sum(float(s.get("km", 30.0)) for s in storms) / len(storms) / kpp * 0.10))
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(blur)))
    if labels:
        tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        td = ImageDraw.Draw(tl)
        for x, y, text, k in labels:
            td.text((x, y), text, font=T.font("bold", 24), fill=(250, 250, 252, int(255 * k)))
        img.alpha_composite(tl)


def lay_flight_map(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    pts = _all_points(p)
    if not pts:
        return None
    # a map split around a footage break carries on where it was: t0 = time already played, total = the whole map's length
    t, dur = t + float(p.get("t0", 0.0)), float(p.get("total", dur))
    view0 = tuple(p["bbox"]) if p.get("bbox") else B.fit_bbox(pts, pad=float(p.get("pad", 0.22)))
    big = B.scale_bbox(view0, MARGIN)
    bw, bh = int(W * MARGIN), int(H * MARGIN)
    base = B.relief(big, (bw, bh), p.get("fetch_tile"), p.get("cache"))
    # camera: a slow push-in with a slight drift, so nothing is ever still
    k = M.ease_in_out(M.clamp01(t / max(dur, 0.1)))
    view = B.scale_bbox(view0, 1.0 - 0.05 * k, 0.012 * k, -0.008 * k)
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
    fl = T.font("bold", 16)
    for aid in p.get("airports") or []:
        ap = _airport(aid)
        if not ap:
            continue
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
        lx, ly = x - tw - 12, y - 22
        d.text((lx, ly), name, font=fl, fill=col)
        d.text((lx + tw - d.textlength(ap["id"], font=T.font("regular", 10)), ly + 19), ap["id"], font=T.font("regular", 10), fill=(190, 194, 204, 220))
        if dim:
            d.line([(lx - 3, ly + 10), (lx + tw + 3, ly + 10)], fill=RED, width=3)
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10)))
    img.alpha_composite(over)
    ImageDraw.Draw(img).text((14, H - 18), B.CREDIT, font=T.font("regular", 10), fill=(150, 154, 164, 160))
    return img
