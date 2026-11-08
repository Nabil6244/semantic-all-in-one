"""War Documentary map events: what the SCRIPT says happened on the ground, drawn on the tactical map (maps_tactical.tac_map params "control"),
plus strategic locations (data/strategic.json) as typed site markers.

The script / CSV / narration is the source of truth: "In February 2024, Russian forces captured Avdiivka" draws Avdiivka's area turning red,
with the narration's own verb and date on the chip. No snapshot data is needed (frontline.py adds sourced control areas when it exists).
Areas are schematic: a town is an irregular zone of a few km around its centre, a region is its admin-1 outline; the map badge says so.

params["control"]  [{place | region, side: russia|ukraine, action: gain|loss, verb, date, start, length, from?: place, arrow?: bool}]
   gain  the side takes it: the zone fills in the side's colour, sweeping in from the side's direction, an advance arrow lands on it
   loss  the side gives it up: the zone drains from the side's colour into the other side's, a pale withdrawal arrow leaves it
   chip  "<SIDE> FORCES <VERB>" + the narration's date, beside the place, after the sweep

attach(plan, rows, cfg, cat)    direction post-pass: tactical maps over territorial sentences get their control events (no map is added).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import frontline as FL
from . import geo_data as G
from . import motion as M
from . import tokens as T
from .. import look as L

W, H = T.W, T.H
DATA = Path(__file__).resolve().parent / "data" / "strategic.json"
SIDE_RGB = FL.OCC
GAIN_VERBS = ("captured", "capture", "seized", "took control of", "took", "occupied", "retook", "recaptured", "liberated", "entered", "overran",
              "encircled", "stormed", "taken")
LOSS_VERBS = ("lost", "withdrew from", "withdrew", "retreated from", "abandoned", "pulled out of", "left")
_RU = re.compile(r"\b(russia|russian|russians|moscow|kremlin|wagner|putin's)\b", re.IGNORECASE)
_UA = re.compile(r"\b(ukraine|ukrainian|ukrainians|kyiv|zelensky|zelenskyy|afu)\b", re.IGNORECASE)


# ================================================================================================================ strategic locations
@lru_cache(maxsize=1)
def sites() -> List[Dict[str, Any]]:
    try:
        raw = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [s for s in raw.get("sites", []) if isinstance(s, dict) and s.get("lat") is not None and s.get("lon") is not None]


def _k(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


@lru_cache(maxsize=1)
def _site_index() -> Dict[str, Dict[str, Any]]:
    idx = {}
    for s in sites():
        for a in [s["name"], s.get("id", "")] + list(s.get("aliases") or []):
            if a:
                idx[_k(a)] = s
    return idx


def find_site(name: str) -> Optional[Dict[str, Any]]:
    return _site_index().get(_k(name))


def sites_in(text: str) -> List[Tuple[int, Dict[str, Any]]]:
    """(char offset, site) for every strategic location the text names (longest alias first, no overlaps)."""
    low = " " + _k(text) + " "
    hits, used = [], []
    raw_low = text.lower()
    for alias, s in sorted(_site_index().items(), key=lambda kv: -len(kv[0])):
        i = low.find(" " + alias + " ")
        if i < 0 or any(a <= i < b for a, b in used):
            continue
        used.append((i, i + len(alias) + 1))
        j = raw_low.find(alias.split()[0])
        hits.append((max(0, j), s))
    seen, out = set(), []
    for i, s in sorted(hits, key=lambda x: x[0]):
        if s["id"] not in seen:
            seen.add(s["id"])
            out.append((i, s))
    return out


TYPE_LABEL = {"nuclear": "NUCLEAR PLANT", "dam": "DAM", "bridge": "BRIDGE", "port": "PORT", "airbase": "AIR BASE", "naval": "NAVAL BASE",
              "refinery": "REFINERY", "depot": "DEPOT", "power": "POWER PLANT", "plant": "PLANT", "island": "ISLAND", "airport": "AIRPORT"}


def site_icon(kind: str, size: int, rgb=(246, 196, 52)) -> Image.Image:
    """Small vector pictogram for a site type (drawn at 4x and reduced)."""
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = rgb + (255,)
    w = max(2, s // 14)
    if kind == "nuclear":
        cx = cy = s / 2
        for k in range(3):
            a0 = -90 + 120 * k - 30
            d.pieslice([cx - s * .42, cy - s * .42, cx + s * .42, cy + s * .42], a0, a0 + 60, fill=c)
        d.ellipse([cx - s * .16, cy - s * .16, cx + s * .16, cy + s * .16], fill=(0, 0, 0, 0))
        d.ellipse([cx - s * .1, cy - s * .1, cx + s * .1, cy + s * .1], fill=c)
    elif kind == "dam":
        d.polygon([(s * .2, s * .15), (s * .45, s * .15), (s * .55, s * .85), (s * .1, s * .85)], fill=c)
        for k in range(3):
            y = s * (.35 + .2 * k)
            d.arc([s * .55, y - s * .08, s * .95, y + s * .08], 200, 340, fill=c, width=w)
    elif kind == "bridge":
        d.rectangle([s * .05, s * .55, s * .95, s * .62], fill=c)
        d.arc([s * .12, s * .3, s * .88, s * .95], 180, 360, fill=c, width=w)
        for x in (.3, .5, .7):
            d.line([(s * x, s * .42), (s * x, s * .55)], fill=c, width=w // 2 + 1)
    elif kind in ("port", "naval"):
        d.ellipse([s * .42, s * .08, s * .58, s * .24], outline=c, width=w)
        d.line([(s * .5, s * .24), (s * .5, s * .88)], fill=c, width=w)
        d.line([(s * .3, s * .36), (s * .7, s * .36)], fill=c, width=w)
        d.arc([s * .15, s * .45, s * .85, s * .9], 20, 160, fill=c, width=w)
    elif kind in ("airbase", "airport"):
        d.polygon([(s * .5, s * .05), (s * .58, s * .35), (s * .95, s * .55), (s * .95, s * .62), (s * .58, s * .52), (s * .56, s * .8),
                   (s * .7, s * .9), (s * .7, s * .95), (s * .5, s * .9), (s * .3, s * .95), (s * .3, s * .9), (s * .44, s * .8), (s * .42, s * .52),
                   (s * .05, s * .62), (s * .05, s * .55), (s * .42, s * .35)], fill=c)
    elif kind in ("power", "plant", "refinery", "depot"):
        d.rectangle([s * .1, s * .45, s * .9, s * .9], fill=c)
        d.rectangle([s * .18, s * .15, s * .32, s * .45], fill=c)
        d.rectangle([s * .42, s * .25, s * .56, s * .45], fill=c)
        d.polygon([(s * .6, s * .45), (s * .9, s * .3), (s * .9, s * .45)], fill=c)
    else:
        d.ellipse([s * .25, s * .25, s * .75, s * .75], fill=c)
    return im.resize((size, size), Image.LANCZOS)


def draw_site(img: Image.Image, x: float, y: float, kind: str, t_age: float, colour=(246, 196, 52)) -> None:
    """Diamond site marker with its pictogram; pops in, then a slow square pulse keeps it alive."""
    if t_age < 0:
        return
    k = M.ease_out(min(1.0, t_age / 0.4))
    over = 1.0 + 0.18 * math.sin(min(1.0, t_age / 0.4) * math.pi)
    r = 20 * k * over
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    ph = ((t_age + 0.3) % 1.8) / 1.8
    rp = r * (1.0 + 0.9 * M.ease_out(ph))
    d.polygon([(x, y - rp), (x + rp, y), (x, y + rp), (x - rp, y)], outline=colour + (int(170 * (1 - ph) * k),))
    d.polygon([(x, y - r - 3), (x + r + 3, y), (x, y + r + 3), (x - r - 3, y)], fill=(8, 10, 14, int(230 * k)))
    d.polygon([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], fill=(14, 16, 20, int(240 * k)), outline=colour + (int(255 * k),))
    if r > 6:
        ic = site_icon(kind, int(r * 1.05), colour)
        lay.alpha_composite(L.fade(ic, k), (int(x - ic.width / 2), int(y - ic.height / 2)))
    img.alpha_composite(lay)


# ================================================================================================================ control zones
def _zone_ring(lat: float, lon: float, km: float, seed: str, n: int = 48) -> List[Tuple[float, float]]:
    """An irregular, deterministic zone around a town centre (lon, lat): never a perfect circle, never the same twice for two towns."""
    h = hashlib.sha1(seed.encode()).digest()
    ph = [b / 255 * 2 * math.pi for b in h[:4]]
    pts = []
    for i in range(n):
        a = i / n * 2 * math.pi
        r = km * (1 + 0.16 * math.sin(2 * a + ph[0]) + 0.1 * math.sin(3 * a + ph[1]) + 0.06 * math.sin(5 * a + ph[2]))
        pts.append((lon + r / (111.32 * math.cos(math.radians(lat))) * math.cos(a), lat + r / 110.57 * math.sin(a)))
    return pts


def _zone_km(ev: Dict[str, Any], view: Any) -> float:
    """The town's zone: its own size, but never smaller than ~4 % of the frame (a 9 km zone on a 900 km map would be a dot)."""
    frame_km = view.lon_span * 111.32 * math.cos(math.radians(ev["lat"]))
    return round(max(float(ev.get("km", 9.0)), 0.04 * frame_km), 1)


def _zone_feature(ev: Dict[str, Any], km: float) -> Optional[G.Feature]:
    if ev.get("feature") is not None:
        return ev["feature"]
    ring = _zone_ring(ev["lat"], ev["lon"], km, ev.get("name", ""))
    return G.Feature({"n": ev.get("name", ""), "iso": "", "g": {"type": "Polygon", "coordinates": [ring]}})


def _resolve(ev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from . import maps_tactical as MT

    e = dict(ev)
    if e.get("region"):
        f = MT._find_region(str(e["region"]))
        if f is None:
            return None
        e["feature"] = f
        e["name"] = f.name
        e["lon"], e["lat"] = f.centroid
        return e
    s = find_site(str(e.get("place") or ""))
    p = {"name": s["name"], "lat": s["lat"], "lon": s["lon"]} if s else MT.resolve_place(e.get("place"))[0]
    if p is None:
        return None
    e.update({"name": p["name"], "lat": float(p["lat"]), "lon": float(p["lon"])})
    return e


def _origin(ev: Dict[str, Any], gaining: str) -> Tuple[float, float]:
    """Where the gaining side comes from (lat, lon): a named `from` place, else schematically from its own side of the theatre."""
    from . import maps_tactical as MT

    if ev.get("from"):
        p, _ = MT.resolve_place(ev["from"])
        if p:
            return p["lat"], p["lon"]
    d = 0.75
    return (ev["lat"] + 0.08, ev["lon"] + d) if gaining == "russia" else (ev["lat"] - 0.05, ev["lon"] - d)


def draw_control(img: Image.Image, view: Any, events: Sequence[Dict[str, Any]], t: float) -> Tuple[Image.Image, Dict[str, Any]]:
    """Composite the control events onto the map image at time t. Returns (image, info with chips to place)."""
    info: Dict[str, Any] = {"events": 0, "chips": [], "skipped": []}
    land = FL._land_mask(view)
    out = img
    for raw in events:
        ev = _resolve(raw)
        if ev is None:
            info["skipped"].append(str(raw.get("place") or raw.get("region")))
            continue
        side = str(ev.get("side") or "russia")
        other = FL.OTHER.get(side, "ukraine")
        gain = str(ev.get("action") or "gain") == "gain"
        gaining = side if gain else other
        st, ln = float(ev.get("start", 0.8)), float(ev.get("length", 1.8))
        p = M.ease_in_out(M.ramp(t, st, ln))
        if t < st - 0.6:
            continue
        info["events"] += 1
        km = _zone_km(ev, view)
        feat = _zone_feature(ev, km)
        key = "ev:" + ev["name"] + ":" + str(km) + (":r" if ev.get("region") else "")
        m = FL._mask(key, feat, view)
        if not ev.get("region"):
            m = ImageChops.multiply(m, land) if np.asarray(ImageChops.multiply(m, land))[::4, ::4].any() else m
        olat, olon = _origin(ev, gaining)
        ox, oy = view.pt(olat, olon)
        k_pre = M.ease_out(M.ramp(t, st - 0.6, 0.5))
        before_rgb = SIDE_RGB[other] if gain else SIDE_RGB[side]
        after_rgb = SIDE_RGB[gaining]
        # the place as it was: a faint tint of whoever held it, outlined, so the change reads as a change
        out = Image.alpha_composite(out, FL._tint(m, before_rgb, 0.18 * k_pre))
        now = FL._sweep(m, (ox, oy), p)
        out = Image.alpha_composite(out, FL._tint(now, after_rgb, 0.55))
        edge = ImageChops.subtract(FL._dilate(m, 2), m)
        out = Image.alpha_composite(out, FL._tint(edge, (236, 238, 242), 0.55 * k_pre))
        if 0.0 < p < 1.0:                                  # the moving front of the sweep glows
            rim = ImageChops.subtract(FL._dilate(now, 2), now)
            rim = ImageChops.multiply(rim, m)
            out = Image.alpha_composite(out, FL._tint(rim.filter(ImageFilter.GaussianBlur(3)), tuple(min(255, c + 80) for c in after_rgb), 1.0))
        if p >= 1.0:                                        # settle flash
            fl = math.exp(-5 * (t - st - ln))
            if fl > 0.02:
                out = Image.alpha_composite(out, FL._tint(m, (255, 255, 255), 0.25 * fl))
        # the movement arrow: an advance landing on the place, or a withdrawal leaving it
        if ev.get("arrow", True):
            out = _arrow(out, view, ev, (ox, oy), gain, after_rgb, t, st, ln)
        cx, cy = view.pt(ev["lat"], ev["lon"])
        verb = str(ev.get("verb") or ("captured" if gain else "withdrew from")).upper()
        title = f"{FL.SIDE_NAME.get(side, '')} FORCES {verb}".strip()
        info["chips"].append({"title": title, "sub": str(ev.get("date") or "").upper(), "x": cx, "y": cy, "rgb": SIDE_RGB[side],
                              "k": M.ease_out(M.ramp(t, st + ln * 0.7, 0.4))})
    return out, info


def _arrow(img: Image.Image, view: Any, ev: Dict[str, Any], origin: Tuple[float, float], gain: bool, rgb, t: float, st: float, ln: float) -> Image.Image:
    cx, cy = view.pt(ev["lat"], ev["lon"])
    ox, oy = origin
    dx, dy = cx - ox, cy - oy
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    stop = 22.0
    if gain:
        a, b = (ox + ux * min(n * 0.15, 40), oy + uy * min(n * 0.15, 40)), (cx - ux * stop, cy - uy * stop)
    else:
        a, b = (cx + ux * stop, cy + uy * stop), (cx + ux * (stop + min(110.0, n * 0.6)), cy + uy * (stop + min(110.0, n * 0.6)))
    if math.hypot(b[0] - a[0], b[1] - a[1]) < 30:
        return img
    frac = M.draw_fraction(t, st - 0.4, ln * 0.8)
    if frac <= 0:
        return img
    S = 2
    lay = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    bend = 0.12
    mx, my = (a[0] + b[0]) / 2 - (b[1] - a[1]) * bend, (a[1] + b[1]) / 2 + (b[0] - a[0]) * bend
    pts = [((1 - f) ** 2 * a[0] + 2 * (1 - f) * f * mx + f * f * b[0], (1 - f) ** 2 * a[1] + 2 * (1 - f) * f * my + f * f * b[1])
           for f in (i / 30 for i in range(31))]
    part = M.partial_polyline(pts, frac)
    if len(part) < 2:
        return img
    col = rgb + (255,) if gain else (226, 230, 236, 220)
    for i in range(len(part) - 1):                           # tapered body: thin at the tail, full at the head
        f = (i + 1) / len(part)
        wdt = int((3 + 9 * f) * S) if gain else int(4 * S)
        x0, y0 = part[i]
        x1, y1 = part[i + 1]
        d.line([(x0 * S, y0 * S), (x1 * S, y1 * S)], fill=(8, 10, 14, 200), width=wdt + 4 * S)
    for i in range(len(part) - 1):
        f = (i + 1) / len(part)
        wdt = int((3 + 9 * f) * S) if gain else int(4 * S)
        x0, y0 = part[i]
        x1, y1 = part[i + 1]
        if gain or (i // 2) % 2 == 0:
            d.line([(x0 * S, y0 * S), (x1 * S, y1 * S)], fill=col, width=wdt)
    hx, hy = part[-1]
    px, py = part[-2]
    ang = math.atan2(hy - py, hx - px)
    sz = 22 if gain else 14
    tip = (hx + math.cos(ang) * sz * 0.6, hy + math.sin(ang) * sz * 0.6)
    l1 = (hx + math.cos(ang + 2.5) * sz, hy + math.sin(ang + 2.5) * sz)
    r1 = (hx + math.cos(ang - 2.5) * sz, hy + math.sin(ang - 2.5) * sz)
    d.polygon([(x * S, y * S) for x, y in (tip, l1, r1)], fill=col, outline=(8, 10, 14, 220))
    return Image.alpha_composite(img, lay.reduce(S))


def draw_chips(img: Image.Image, info: Dict[str, Any], placer: Any) -> List[str]:
    d = ImageDraw.Draw(img)
    ft, fs = T.font("bold", 15), T.font("bold", 12)
    done = []
    for c in info.get("chips", []):
        if c["k"] <= 0:
            continue
        w = max(int(L.spaced_width(d, c["title"], ft, 0.08)), int(L.spaced_width(d, c["sub"], fs, 0.1)) if c["sub"] else 0) + 26
        h = 44 if c["sub"] else 28
        x, y = c["x"], c["y"]
        r = placer.first_free([(x + 26, y - h / 2, x + 26 + w, y + h / 2), (x - 26 - w, y - h / 2, x - 26, y + h / 2),
                               (x - w / 2, y + 30, x + w / 2, y + 30 + h), (x - w / 2, y - 30 - h, x + w / 2, y - 30)])
        if r is None:
            continue
        placer.take(c["title"], r)
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rectangle(r, fill=(10, 12, 16, 238), outline=(200, 206, 216, 255), width=1)
        ld.rectangle((r[0], r[1], r[0] + 4, r[3]), fill=c["rgb"] + (255,))
        L.spaced(ld, (r[0] + 13, r[1] + 6), c["title"], ft, (242, 244, 248, 255), 0.08)
        if c["sub"]:
            L.spaced(ld, (r[0] + 13, r[1] + 26), c["sub"], fs, (246, 196, 52, 255), 0.1)
        dx = 10 * (1 - c["k"])
        img.alpha_composite(L.fade(lay, c["k"]), (int(dx), 0))
        done.append(c["title"])
    return done


# ================================================================================================================ narration -> events
def side_of(text: str, verb_at: int) -> str:
    """Who acts: the side named before the verb (nearest), else ''."""
    head = text[:verb_at]
    ru = [m.start() for m in _RU.finditer(head)]
    ua = [m.start() for m in _UA.finditer(head)]
    if not ru and not ua:
        return ""
    return "russia" if (max(ru) if ru else -1) > (max(ua) if ua else -1) else "ukraine"


def events_for(text: str, A: Any, t0: float) -> List[Dict[str, Any]]:
    """Control events the narration states, timed to its words (seconds from t0). Unknown actor -> no event."""
    out: List[Dict[str, Any]] = []
    for s in A.sentences:
        terr = getattr(s, "territorial", None)
        if not terr:
            continue
        verb, places = terr
        low = A.text.lower()
        vi = low.find(verb, s.span[0] if hasattr(s, "span") else 0)
        if vi < 0:
            vi = low.find(verb)
        side = side_of(A.text, vi)
        if not side:
            continue
        gain = any(verb.startswith(v) or v.startswith(verb) for v in GAIN_VERBS) and not any(verb.startswith(v) for v in LOSS_VERBS)
        ds = re.search(r"\b(?:(?:early|mid|late)[- ])?(january|february|march|april|may|june|july|august|september|october|november|december)"
                       r"(?:\s+\d{1,2})?,?\s+(?:19|20)\d{2}\b|\b(?:19|20)\d{2}\b", s.text, re.IGNORECASE)
        for pl in places[:2]:
            when = max(0.4, A.time_at(pl.span[0]) - t0)
            out.append({"place": pl.name, "side": side, "action": "gain" if gain else "loss", "verb": verb, "date": ds.group(0) if ds else "",
                        "start": round(when + 0.2, 2), "length": 1.8})
    return out


def _push_in(p: Dict[str, Any], ev: Dict[str, Any]) -> None:
    """The camera holds the wider picture, then pushes in close on the place as the narration names what happened there."""
    foc = list(p.get("focus") or [])
    ft = list(p.get("focus_times") or [])
    cs = list(p.get("close_steps") or [])
    if not foc:
        refs = [x if not isinstance(x, dict) else x.get("name") for x in p.get("places") or []]
        refs = [r for r in refs if r]
        if len(refs) < 2:
            foc, ft, cs = [ev["place"]], [0.0], [True]
            p.update({"focus": foc, "focus_times": ft, "close_steps": cs})
            return
        foc, ft, cs = [refs], [0.0], [False]
    if len(ft) != len(foc):
        return
    at = round(max(0.0, ev["start"] - 0.9), 2)
    if at >= (ft[-1] if ft else 0.0) + 1.2:
        foc.append(ev["place"])
        ft.append(at)
        cs = (cs + [False] * len(foc))[:len(foc) - 1] + [True]
        p.update({"focus": foc, "focus_times": ft, "close_steps": cs})


_COUNT = re.compile(r"\b(\d[\d,]{1,6})\s+(drones|missiles|ballistic missiles|rockets|shells|strikes|attacks)\b", re.IGNORECASE)
_BDATE = re.compile(r"\b(?:\d{1,2}(?:st|nd|rd|th)?\s+)?(?:january|february|march|april|may|june|july|august|september|october|november|december)"
                    r"(?:\s+\d{1,2}(?:st|nd|rd|th)?)?(?:,?\s+(?:19|20)\d{2})?\b", re.IGNORECASE)


def attach(plan: Any, rows: Sequence[Dict[str, Any]], cfg: Dict[str, Any], cat: Any) -> Dict[str, Any]:
    """Tactical maps over sentences that state a capture / retreat get the event drawn (and its place pinned). Returns counts."""
    from . import semantics as S

    out = {"attached": 0, "sites": 0, "upgraded": 0}
    rows = sorted(rows, key=lambda r: r["_start"])
    for ly in plan.layers:                       # a plain situation map over a capture / withdrawal sentence becomes the animated tactical map
        if ly.kind != "map_card" or (ly.params or {}).get("control") or (ly.params or {}).get("snapshot") or (ly.params or {}).get("control_snapshots"):
            continue
        r = next((r for r in rows if r["_start"] - 0.05 <= ly.start < r["_end"]), None)
        if r is None:
            continue
        A = S.analyze_scene(str(r.get("text") or ""), cat, r.get("words"), r["_start"], r["_end"])
        if not events_for(str(r.get("text") or ""), A, ly.start):
            continue
        old = dict(ly.params or {})
        names = [str(x.get("name") or x.get("label") or "") for x in (old.get("pins") or []) + (old.get("cities") or []) if isinstance(x, dict)]
        ly.kind, ly.dim = "tac_map", False
        ly.params = {"theme": "tactical", "places": [{"name": n} for n in names if n], **({"csv_graphic": True} if old.get("csv_graphic") else {})}
        out["upgraded"] += 1
    for ly in plan.layers:
        if ly.kind != "tac_map":
            continue
        p = dict(ly.params or {})
        span_rows = [r for r in rows if r["_end"] > ly.start + 0.05 and r["_start"] < ly.end - 0.05]
        evs: List[Dict[str, Any]] = []
        site_marks: List[Dict[str, Any]] = []
        for r in span_rows:
            text = str(r.get("text") or "")
            if not text.strip():
                continue
            A = S.analyze_scene(text, cat, r.get("words"), r["_start"], r["_end"])
            if not p.get("control") and cfg.get("map_events", True):
                for e in events_for(text, A, ly.start):
                    if e["start"] < ly.end - ly.start - 0.8:
                        evs.append(e)
            for i, s in sites_in(text):
                at = round(max(0.4, A.time_at(i) - ly.start), 2)
                if at < ly.end - ly.start - 1.0:             # only what is named while this map is on screen
                    site_marks.append({"name": s["name"], "start": at})
        if evs:
            p["control"] = evs[:3]
            names = {str((x.get("name") if isinstance(x, dict) else x) or "").lower() for x in p.get("places") or []}
            p["places"] = list(p.get("places") or []) + [{"name": e["place"], "kind": "pin", "start": e["start"]} for e in evs[:3]
                                                          if e["place"].lower() not in names]
            _push_in(p, evs[0])
            out["attached"] += 1
        if site_marks:
            names = {str((x.get("name") if isinstance(x, dict) else x) or "").lower() for x in p.get("places") or []}
            add = [s for s in site_marks if s["name"].lower() not in names][:3]
            p["places"] = list(p.get("places") or []) + [{"name": s["name"], "kind": "pin", "start": s["start"]} for s in add]
            out["sites"] += len(add)
        for r in span_rows:                      # the count the narration gives, big over the map; the scene's own clip in a round inset
            text = str(r.get("text") or "")
            if not p.get("banner"):
                m = _COUNT.search(text)
                if m:
                    A2 = S.analyze_scene(text, cat, r.get("words"), r["_start"], r["_end"])
                    dm = _BDATE.search(text)
                    p["banner"] = {"text": f"{m.group(1)} {m.group(2)}", "sub": dm.group(0) if dm else "",
                                   "start": round(max(0.4, A2.time_at(m.start()) - ly.start), 2)}
                    out["banners"] = out.get("banners", 0) + 1
            if not p.get("inset") and r.get("footage") and p.get("places"):
                from .broadcast import _fits

                if _fits(r.get("footage_meta") or {}):
                    first = p["places"][0]
                    p["inset"] = {"place": first.get("name") if isinstance(first, dict) else first, "video": str(r["footage"]), "at": 1.5,
                                  "start": round(max(1.2, float((first.get("start") if isinstance(first, dict) else 0) or 0) + 0.8), 2)}
                    out["insets"] = out.get("insets", 0) + 1
        if evs or site_marks or p.get("banner") or p.get("inset"):
            ly.params = p
    return out


# ================================================================================================================ map-to-map continuity
CONTINUITY_GAP_S = 9.0


def continuity(plan: Any, gap_s: float = CONTINUITY_GAP_S) -> int:
    """Consecutive tactical maps (a few seconds apart) become one journey: the next map's camera starts where the last one ended and
    travels to its own subject, instead of opening on a new establishing shot. Only between nearby frames of similar scale (a jump
    across the continent keeps its own establishing shot). Returns how many maps were linked."""
    from . import maps_tactical as MT

    maps = sorted([ly for ly in plan.layers if ly.kind == "tac_map"], key=lambda ly: ly.start)
    linked = 0
    for prev, nxt in zip(maps, maps[1:]):
        pp, np_ = dict(prev.params or {}), dict(nxt.params or {})
        if nxt.start - prev.end > gap_s or nxt.start < prev.end - 0.01 or float(np_.get("t_offset") or 0) > 0 or np_.get("enter_from"):
            continue
        if str(pp.get("theme") or "tactical") != str(np_.get("theme") or "tactical"):
            continue
        try:
            off = float(pp.get("t_offset") or 0.0)
            tot = float(pp.get("total_dur") or 0.0) or (prev.end - prev.start)
            a = MT.view_at(pp, off + (prev.end - prev.start), tot)
            b = MT.view_at(np_, 2.5, nxt.end - nxt.start)
        except Exception:
            continue
        ratio = max(a[2], b[2]) / max(1e-9, min(a[2], b[2]))
        dist = math.hypot(a[0] - b[0], a[1] - b[1])
        if ratio > 4.0 or dist > 2.5 * max(a[2], b[2]):
            continue
        np_["enter_from"] = [round(a[0], 7), round(a[1], 7), round(a[2], 7)]
        nxt.params = np_
        linked += 1
    return linked
