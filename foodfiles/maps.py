"""Map cards: a dark map, the story's state / country fills red, a pin drops on the city.

place: "Starke, Florida" | "Florida" | "Japan" | "Bradford, England" | "Sydney, Australia".
US states draw on a lower-48 map; anywhere else on the country with its neighbours. A city we can't find puts the pin
in the middle of its region. Uses the app's own shapes (map_scene/data) and city list (pakmap-engine/data); no network.
"""
import gzip
import json
import math
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "map_scene" / "data"
PLACES = ROOT / "pakmap-engine" / "data" / "places_index.json.gz"

LAND = (64, 58, 62, 255)
LAND_EDGE = (98, 90, 94, 255)
FILL = (214, 38, 43, 255)
US_BOX = (-125.0, 24.0, -66.5, 49.6)
COUNTRY_ALIASES = {"usa": "United States of America", "us": "United States of America", "america": "United States of America",
                   "united states": "United States of America", "uk": "United Kingdom", "britain": "United Kingdom",
                   "great britain": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
                   "wales": "United Kingdom", "south korea": "South Korea", "korea": "South Korea", "holland": "Netherlands",
                   "the netherlands": "Netherlands", "czech republic": "Czechia", "ivory coast": "Côte d'Ivoire"}
US_STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
             "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
             "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
             "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
             "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
             "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
             "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
             "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
             "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia"}


@lru_cache(maxsize=1)
def _admin1_us():
    d = json.load(gzip.open(DATA / "admin1.json.gz"))
    return [f for f in d["features"] if f.get("iso") == "USA"]


@lru_cache(maxsize=1)
def _countries():
    return json.load(gzip.open(DATA / "countries.json.gz"))["features"]


@lru_cache(maxsize=1)
def _places():
    try:
        return json.load(gzip.open(PLACES))
    except OSError:
        return []


def _rings(g):
    t, c = g.get("type"), g.get("coordinates") or []
    if t == "Polygon":
        return [c[0]] if c else []
    if t == "MultiPolygon":
        return [p[0] for p in c if p]
    return []


def _low(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _state(name):
    n = _low(name)
    full = US_STATES.get(name.strip().upper()) if len(name.strip()) == 2 else None
    for f in _admin1_us():
        if _low(f["n"]) in (n, _low(full or "")) or _low(f.get("postal")) == n:
            return f
    return None


def _country(name):
    n = _low(COUNTRY_ALIASES.get(_low(name), name))
    for f in _countries():
        if _low(f["n"]) == n or n in [_low(a) for a in f.get("alt") or []]:
            return f
    for f in _countries():
        if n and (n in _low(f["n"]) or _low(f["n"]) in n):
            return f
    return None


def _city(name, iso=None, admin=None):
    n = _low(name)
    best = None
    for p in _places():
        if _low(p[0]) == n or _low(p[1]) == n or n in [_low(a) for a in p[2] or []]:
            if iso and p[6] != iso:
                continue
            if admin and _low(p[7]) != _low(admin):
                continue
            if best is None or (p[5] or 0) > (best[5] or 0):
                best = p
    return (best[3], best[4]) if best else None


def resolve(place):
    """-> {"kind": "us"|"world", "region": feature|None, "city": (lon,lat)|None, "label": str, "box": (lon0,lat0,lon1,lat1)}."""
    parts = [p.strip() for p in str(place or "").split(",") if p.strip()]
    if not parts:
        return None
    region_name = parts[-1]
    city_name = parts[0] if len(parts) > 1 else None
    st = _state(region_name)
    if st is None and len(parts) > 2:
        st = _state(parts[-2])
    if st is not None:
        city = _city(city_name, "USA", st["n"]) if city_name else None
        return {"kind": "us", "region": st, "city": city, "label": ", ".join(parts).upper(), "box": US_BOX}
    co = _country(region_name)
    if co is None and city_name is None:
        # maybe a city on its own ("Bradford")
        c = _city(region_name)
        if c:
            box = (c[0] - 9, c[1] - 6, c[0] + 9, c[1] + 6)
            return {"kind": "world", "region": None, "city": c, "label": region_name.upper(), "box": box}
        return None
    city = None
    if city_name:
        iso = co.get("iso") if co else None
        city = _city(city_name, iso) or _city(city_name)
    box = _bbox(co) if co else None
    if box:
        lon0, lat0, lon1, lat1 = box
        cx, cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
        span = max(lon1 - lon0, (lat1 - lat0) * 1.6, 14.0)
        if span > 120:          # Russia, Canada... keep it readable
            span = 120
        box = (cx - span / 2, cy - span / 3.2, cx + span / 2, cy + span / 3.2)
    elif city:
        box = (city[0] - 9, city[1] - 6, city[0] + 9, city[1] + 6)
    else:
        return None
    return {"kind": "world", "region": co, "city": city, "label": ", ".join(parts).upper(), "box": box}


def _bbox(f):
    xs, ys = [], []
    rings = _rings(f["g"])
    # the biggest ring decides (France without its islands, the US without Alaska)
    rings = sorted(rings, key=len, reverse=True)
    main = rings[:1]
    for r in rings[1:]:
        if len(r) > 0.25 * len(main[0]):
            main.append(r)
    for r in main:
        for x, y in r:
            xs.append(x)
            ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _projector(box, size, margin=0.06):
    lon0, lat0, lon1, lat1 = box
    W, H = size
    k = math.cos(math.radians((lat0 + lat1) / 2))
    sx = (W * (1 - 2 * margin)) / max(1e-6, (lon1 - lon0) * k)
    sy = (H * (1 - 2 * margin)) / max(1e-6, (lat1 - lat0))
    s = min(sx, sy)
    cx, cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2

    def proj(lon, lat):
        return (W / 2 + (lon - cx) * k * s, H / 2 - (lat - cy) * s)
    return proj


def _draw_feature(d, f, proj, fill, edge, width):
    for ring in _rings(f["g"]):
        pts = [proj(x, y) for x, y in ring]
        if len(pts) > 2:
            d.polygon(pts, fill=fill)
            if edge:
                d.line(pts + [pts[0]], fill=edge, width=width)


@lru_cache(maxsize=24)
def layers(place, size):
    """-> (base RGBA, fill RGBA, pin (x, y) | None, label) or None if the place is unknown. Cached per place + size."""
    r = resolve(place)
    if not r:
        return None
    W, H = size
    proj = _projector(r["box"], size)
    base = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    w = max(1, int(round(H / 540)))
    lon0, lat0, lon1, lat1 = r["box"]
    if r["kind"] == "us":
        for f in _countries():   # Canada / Mexico for context
            if f["n"] in ("Canada", "Mexico"):
                _draw_feature(d, f, proj, (48, 44, 48, 255), None, w)
        for f in _admin1_us():
            if f["n"] in ("Alaska", "Hawaii"):
                continue
            _draw_feature(d, f, proj, LAND, LAND_EDGE, w)
    else:
        for f in _countries():
            b = _bbox(f)
            if b and b[2] >= lon0 - 5 and b[0] <= lon1 + 5 and b[3] >= lat0 - 5 and b[1] <= lat1 + 5:
                _draw_feature(d, f, proj, LAND, LAND_EDGE, w)
    fill = Image.new("RGBA", size, (0, 0, 0, 0))
    if r["region"] is not None:
        df = ImageDraw.Draw(fill)
        _draw_feature(df, r["region"], proj, FILL, (255, 120, 120, 255), w)
    pin = None
    if r["city"]:
        pin = proj(*r["city"])
    elif r["region"] is not None:
        b = _bbox(r["region"])
        pin = proj((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) if b else None
    if pin and not (0 <= pin[0] <= W and 0 <= pin[1] <= H):
        pin = None
    # a soft glow under the region so it reads at a glance
    if r["region"] is not None:
        glow = fill.filter(ImageFilter.GaussianBlur(H / 60))
        glow.putalpha(glow.split()[3].point(lambda v: int(v * 0.55)))
        g2 = Image.new("RGBA", size, (0, 0, 0, 0))
        g2.alpha_composite(glow)
        g2.alpha_composite(fill)
        fill = g2
    return base, fill, pin, r["label"]


@lru_cache(maxsize=12)
def layers_multi(places, size):
    """Several places on one map (a tuple of names) -> (base, [(fill RGBA, label point (x, y)) per place]) or None.
    All US states -> the lower-48 map; otherwise a box around every place."""
    rs = [resolve(p) for p in places]
    rs = [r for r in rs if r and r.get("region") is not None]
    if not rs:
        return None
    W, H = size
    if all(r["kind"] == "us" for r in rs):
        box, kind = US_BOX, "us"
    else:
        bs = [_bbox(r["region"]) for r in rs]
        lon0, lat0 = min(b[0] for b in bs), min(b[1] for b in bs)
        lon1, lat1 = max(b[2] for b in bs), max(b[3] for b in bs)
        cx, cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
        span = min(170.0, max(lon1 - lon0, (lat1 - lat0) * 1.6, 14.0) * 1.15)
        box, kind = (cx - span / 2, cy - span / 3.2, cx + span / 2, cy + span / 3.2), "world"
    proj = _projector(box, size)
    base = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    w = max(1, int(round(H / 540)))
    if kind == "us":
        for f in _countries():
            if f["n"] in ("Canada", "Mexico"):
                _draw_feature(d, f, proj, (48, 44, 48, 255), None, w)
        for f in _admin1_us():
            if f["n"] not in ("Alaska", "Hawaii"):
                _draw_feature(d, f, proj, LAND, LAND_EDGE, w)
    else:
        for f in _countries():
            b = _bbox(f)
            if b and b[2] >= box[0] - 5 and b[0] <= box[2] + 5 and b[3] >= box[1] - 5 and b[1] <= box[3] + 5:
                _draw_feature(d, f, proj, LAND, LAND_EDGE, w)
    out = []
    for r in rs:
        fill = Image.new("RGBA", size, (0, 0, 0, 0))
        _draw_feature(ImageDraw.Draw(fill), r["region"], proj, FILL, (255, 120, 120, 255), w)
        b = _bbox(r["region"])
        out.append((fill, proj((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)))
    return base, out
