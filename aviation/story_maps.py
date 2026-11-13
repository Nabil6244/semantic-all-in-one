"""Story-mode maps (docs/aviation/MASTER_PLAN.md S6, S7): a black political map with countries filling in, and a dark route-map
card with arcs drawing out of the hubs. Registered as animated stage kinds (args['_k'] 0..1 = progress), so they enter, float and
leave like every other card.

    political_map  args {countries: [{code|name, color?: 'red'|'blue'|'#hex', label?}], title?, focus?: [codes|names],
                         places?: [airport ids or city names], width=1100, height=620}
                   black land, thin grey borders, the named countries filling one by one, small spaced-caps labels, serif title
                   top-left; framed automatically around the named countries (or `focus`) with a margin.
    route_map      args {hubs: [airport ids], destinations: [airport ids | {id, color}], airline?, year?, title?, legend?: [{color,
                         label}], width=1100, height=620}
                   dark map, glowing hub dots, coloured arcs drawing out of the hubs, small city labels, title + year box
                   top-right and a legend.
    routes_from(text_or_csv, airline) -> {hubs, destinations, airline}   hub = the airline's catalog hub(s), destinations = only
                   the airports the text names (nothing invented); feed it to route_map / add_route_map.
    add_political_map(st, at, countries, title="", focus=None, places=None, anim=2.6, enter="fade", ...) -> id
    add_route_map(st, at, hubs, destinations, airline="", year=None, title="Scheduled Route Map", legend=None, anim=3.0, ...) -> id
Country shapes: Natural Earth 1:50m admin-0 as shipped in map_scene/data/countries.json.gz (loaded once, projected once per card
and cached; a frame is a copy of the cached base plus the filled layers). Unknown countries / airports are ignored, never fatal.
"""

from __future__ import annotations

import gzip
import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from cinematic_explainer import look as L
from cinematic_explainer.war import motion as M

from . import catalog as C
from . import flightmap as F
from . import stage as G
from . import style as S

DATA = Path(__file__).resolve().parent.parent / "map_scene" / "data" / "countries.json.gz"
SS = 2                                              # supersample of the cached layers

SEA_POL = (24, 27, 34, 255)
LAND_POL = (8, 9, 11, 255)
BORDER = (112, 116, 126, 255)
SEA_RT = (11, 13, 18, 255)
LAND_RT = (34, 37, 45, 255)
BORDER_RT = (62, 66, 76, 255)
BLUE = (64, 122, 230, 255)
HUB_COLORS = [S.YELLOW, (96, 202, 255, 255), S.GREEN, S.RED, (220, 150, 255, 255)]

_ALIASES = {"usa": "USA", "us": "USA", "united states": "USA", "america": "USA", "uk": "GBR", "britain": "GBR",
            "great britain": "GBR", "england": "GBR", "russian federation": "RUS", "burma": "MMR", "south korea": "KOR",
            "korea": "KOR", "uae": "ARE", "holland": "NLD", "czechia": "CZE", "ivory coast": "CIV"}
_ISO2 = {"US": "USA", "GB": "GBR", "UK": "GBR", "SG": "SGP", "MY": "MYS", "ID": "IDN", "TH": "THA", "IN": "IND", "PK": "PAK",
         "CN": "CHN", "JP": "JPN", "KR": "KOR", "AU": "AUS", "NZ": "NZL", "FR": "FRA", "DE": "DEU", "IT": "ITA", "ES": "ESP",
         "RU": "RUS", "AE": "ARE", "SA": "SAU", "TR": "TUR", "EG": "EGY", "ZA": "ZAF", "BR": "BRA", "CA": "CAN", "MX": "MEX",
         "VN": "VNM", "PH": "PHL", "BN": "BRN", "MM": "MMR", "HK": "HKG", "TW": "TWN", "NL": "NLD", "CH": "CHE", "IE": "IRL"}


def _norm(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# ---------------------------------------------------------------------------------------------------------------- shapes

def merc_xy(lon: np.ndarray, lat: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    lat = np.clip(lat, -85.0, 85.0)
    r = np.radians(lat)
    return (lon + 180.0) / 360.0, (1.0 - np.arcsinh(np.tan(r)) / math.pi) / 2.0


@lru_cache(maxsize=1)
def world() -> List[Dict[str, Any]]:
    """Natural Earth countries: [{iso, name, keys, polys: [(N,2) merc arrays, outer rings], areas, bbox}]. Loaded once."""
    try:
        with gzip.open(DATA, "rt", encoding="utf-8") as fh:
            feats = json.load(fh)["features"]
    except Exception:
        return []
    out = []
    for f in feats:
        g = f.get("g") or {}
        polys_raw = g.get("coordinates") or []
        if g.get("type") == "Polygon":
            polys_raw = [polys_raw]
        polys, areas = [], []
        for poly in polys_raw:
            if not poly or len(poly[0]) < 3:
                continue
            a = np.asarray(poly[0], dtype=float)
            x, y = merc_xy(a[:, 0], a[:, 1])
            xy = np.stack([x, y], 1)
            polys.append(xy)
            areas.append(abs(0.5 * float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))))
        if not polys:
            continue
        allp = np.concatenate(polys)
        keys = {_norm(f.get("n")), _norm(f.get("iso"))} | {_norm(a) for a in f.get("alt") or []}
        out.append({"iso": f.get("iso", ""), "name": f.get("n", ""), "keys": keys, "polys": polys, "areas": areas,
                    "bbox": (float(allp[:, 0].min()), float(allp[:, 1].min()), float(allp[:, 0].max()), float(allp[:, 1].max()))})
    return out


@lru_cache(maxsize=512)
def find_country(ref: str) -> Optional[int]:
    """Index into world() of a country given its name, alt name, ISO-3 or ISO-2 code; None when unknown."""
    k = _norm(ref)
    if not k:
        return None
    iso = _ISO2.get(str(ref).strip().upper()) if len(str(ref).strip()) == 2 else None
    iso = _norm(iso or _ALIASES.get(k, "")) or None
    w = world()
    for i, c in enumerate(w):
        if iso and _norm(c["iso"]) == iso:
            return i
        if k in c["keys"]:
            return i
    return None


def _main_polys(c: Dict[str, Any]) -> List[np.ndarray]:
    """The country's real shapes for framing: drop far specks (< 4 % of the largest part)."""
    big = max(c["areas"])
    return [p for p, a in zip(c["polys"], c["areas"]) if a >= big * 0.04]


def _color(v: Any, default=S.RED) -> Tuple[int, int, int, int]:
    if isinstance(v, str):
        s = v.strip().lower()
        if s == "red":
            return S.RED
        if s == "blue":
            return BLUE
        if s in ("yellow", "gold"):
            return S.YELLOW
        if s == "green":
            return S.GREEN
        m = re.fullmatch(r"#?([0-9a-f]{6})", s)
        if m:
            h = m.group(1)
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    return default


# ---------------------------------------------------------------------------------------------------------------- framing

def _view(bounds: Tuple[float, float, float, float], w: int, h: int, pad: float = 0.22, min_span: float = 0.0016,
          lift: float = 0.0) -> Tuple[float, float, float, float]:
    """A merc box of the card's aspect around `bounds` with a margin; lift > 0 moves the content down (room for a title)."""
    x0, y0, x1, y1 = bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    bw, bh = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    vw = max(bw * (1 + 2 * pad), bh * (1 + 2 * pad) * w / h, min_span)
    vh = vw * h / w
    cy -= lift * vh
    return cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2


class _Proj:
    def __init__(self, view: Tuple[float, float, float, float], w: int, h: int, ss: int = 1):
        self.v, self.w, self.h, self.ss = view, w, h, ss

    def xy(self, p: np.ndarray) -> np.ndarray:
        x0, y0, x1, y1 = self.v
        return np.stack([(p[:, 0] - x0) / (x1 - x0) * self.w * self.ss, (p[:, 1] - y0) / (y1 - y0) * self.h * self.ss], 1)

    def pt(self, lat: float, lon: float) -> Tuple[float, float]:
        x, y = merc_xy(np.array([lon]), np.array([lat]))
        q = self.xy(np.array([[x[0], y[0]]]))[0]
        return float(q[0]), float(q[1])


def _in_view(bb, v, slack: float = 0.0) -> bool:
    return not (bb[2] < v[0] - slack or bb[0] > v[2] + slack or bb[3] < v[1] - slack or bb[1] > v[3] + slack)


def _draw_land(w: int, h: int, view, land, border, sea, bw: float = 1.0) -> Image.Image:
    """Sea + every country in view + thin borders, drawn at SS x and brought down once (this is the cached base)."""
    P = _Proj(view, w, h, SS)
    im = Image.new("RGBA", (w * SS, h * SS), sea)
    d = ImageDraw.Draw(im)
    for c in world():
        if not _in_view(c["bbox"], view):
            continue
        for poly in c["polys"]:
            if poly[:, 0].max() < view[0] or poly[:, 0].min() > view[2] or poly[:, 1].max() < view[1] or poly[:, 1].min() > view[3]:
                continue
            pts = [tuple(p) for p in P.xy(poly).tolist()]
            if len(pts) >= 3:
                d.polygon(pts, fill=land)
                d.line(pts + [pts[0]], fill=border, width=max(1, int(round(bw * SS))), joint="curve")
    return im.resize((w, h), Image.LANCZOS)


def _rounded(w: int, h: int, r: int = 28) -> Image.Image:
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), radius=r * SS, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def _spaced_w(d, text, f, sp=0.2) -> float:
    return L.spaced_width(d, text, f, sp) - f.size * sp


def _spaced(d, xy, text, f, fill, sp=0.2, halo=(0, 0, 0, 255), halo_w=2) -> None:
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill, stroke_width=halo_w, stroke_fill=halo)
        x += d.textlength(ch, font=f) + f.size * sp


def _free_rect(r, placed, w, h):
    return not any(not (r[2] < p[0] or r[0] > p[2] or r[3] < p[1] or r[1] > p[3]) for p in placed) and r[0] >= 8 and r[2] <= w - 8 and r[1] >= 8 and r[3] <= h - 8


# ---------------------------------------------------------------------------------------------------------------- places

def _place(ref: Any) -> Optional[Dict[str, Any]]:
    """An airport id or a city name from the catalog -> {name, lat, lon}; None when it isn't there."""
    if isinstance(ref, dict) and "lat" in ref and "lon" in ref:
        return {"name": str(ref.get("name") or ref.get("city") or ""), "lat": float(ref["lat"]), "lon": float(ref["lon"])}
    s = str(ref or "").strip()
    a = C.get_airport(s.upper()) if len(s) == 3 else None
    if not a:
        hits = C.find_airports(s)
        a = hits[0].entry if hits else None
    return {"name": a["city"], "lat": a["lat"], "lon": a["lon"], "id": a["id"]} if a else None


# ---------------------------------------------------------------------------------------------------------------- S6 political map

class _Political:
    def __init__(self, a: Dict[str, Any]):
        self.w, self.h = int(a.get("width", 1100)), int(a.get("height", 620))
        self.title = str(a.get("title") or "")
        items = []
        seen = set()
        for c in a.get("countries") or []:
            c = c if isinstance(c, dict) else {"name": c}
            i = find_country(str(c.get("code") or c.get("name") or ""))
            if i is None or i in seen:
                continue
            seen.add(i)
            items.append((i, _color(c.get("color")), str(c.get("label") or world()[i]["name"])))
        self.items = items
        focus_idx = [j for j in (find_country(str(f)) for f in a.get("focus") or []) if j is not None] or [i for i, _, _ in items]
        pts = [p for i in focus_idx for p in _main_polys(world()[i])]
        self.places = [p for p in (_place(x) for x in a.get("places") or []) if p]
        px = [merc_xy(np.array([p["lon"]]), np.array([p["lat"]])) for p in self.places]
        xs = [float(p[:, 0].min()) for p in pts] + [float(p[0][0]) for p in px]
        xe = [float(p[:, 0].max()) for p in pts] + [float(p[0][0]) for p in px]
        ys = [float(p[:, 1].min()) for p in pts] + [float(p[1][0]) for p in px]
        ye = [float(p[:, 1].max()) for p in pts] + [float(p[1][0]) for p in px]
        if xs:
            self.view = _view((min(xs), min(ys), max(xe), max(ye)), self.w, self.h, pad=0.2, lift=0.05)
        else:                                                                    # nothing known: a quiet world view
            self.view = _view((0.0, 0.18, 1.0, 0.78), self.w, self.h, pad=0.02)
        self.base = _draw_land(self.w, self.h, self.view, LAND_POL, BORDER, SEA_POL)
        self.mask = _rounded(self.w, self.h)
        P = _Proj(self.view, self.w, self.h, SS)
        self.fills = []
        for i, col, label in items:
            c = world()[i]
            m = Image.new("L", (self.w * SS, self.h * SS), 0)
            md = ImageDraw.Draw(m)
            for poly in c["polys"]:
                if _in_view(c["bbox"], self.view):
                    pts_ = [tuple(p) for p in P.xy(poly).tolist()]
                    if len(pts_) >= 3:
                        md.polygon(pts_, fill=255)
            m = m.resize((self.w, self.h), Image.LANCZOS)
            box = m.getbbox()
            edge = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(3)), m.filter(ImageFilter.MinFilter(3)))
            big = max(range(len(c["polys"])), key=lambda j: c["areas"][j])
            ring = P.xy(c["polys"][big]) / SS
            ax, ay = float(ring[:, 0].mean()), float(ring[:, 1].mean())
            self.fills.append({"mask": m, "edge": edge, "box": box, "col": col, "label": label.upper(), "anchor": (ax, ay),
                               "size": (box[2] - box[0], box[3] - box[1]) if box else (0, 0)})
        self.labels = self._label_layout()
        self.pin_xy = [(P.pt(p["lat"], p["lon"]), p["name"]) for p in self.places]
        self.pin_xy = [((x / SS, y / SS), n) for (x, y), n in self.pin_xy]

    def _label_layout(self):
        f = S.font("body", 15)
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        placed: List[Tuple[float, float, float, float]] = []
        out = []
        for fl in self.fills:
            if not fl["box"]:
                out.append(None)
                continue
            text = fl["label"]
            tw = _spaced_w(probe, text, f)
            th = f.size + 4
            ax, ay = fl["anchor"]
            inside = fl["size"][0] > tw * 1.15 and fl["size"][1] > th * 1.6
            if inside:
                cands = [(ax - tw / 2, ay - th / 2, False)]
            else:
                bx0, by0, bx1, by1 = fl["box"]
                cands = [(bx1 + 14, ay - th / 2 + dy, True) for dy in (0, -th - 6, th + 6, -2 * th - 12, 2 * th + 12)] + \
                        [(bx0 - 14 - tw, ay - th / 2 + dy, True) for dy in (0, th + 6, -th - 6)]
            pos = None
            for x, y, lead in cands:
                r = (x - 4, y - 2, x + tw + 4, y + th + 2)
                if _free_rect(r, placed, self.w, self.h):
                    pos = (x, y, lead)
                    placed.append(r)
                    break
            if pos is None:
                x, y, lead = cands[0]
                placed.append((x, y, x + tw, y + th))
                pos = (x, y, lead)
            out.append({"text": text, "x": pos[0], "y": pos[1], "lead": pos[2], "w": tw, "h": th})
        return out

    def frame(self, k: float) -> Image.Image:
        im = self.base.copy()
        n = max(1, len(self.fills))
        for i, fl in enumerate(self.fills):
            a = M.ease_out(M.clamp01((k - (0.12 + 0.62 * i / n)) / 0.26))
            if a <= 0 or not fl["box"]:
                continue
            col = fl["col"][:3]
            im.paste(col + (255,), (0, 0), fl["mask"].point(lambda v, a=a: int(v * a * 0.9)))
            hi = tuple(min(255, c + 70) for c in col)
            im.paste(hi + (255,), (0, 0), fl["edge"].point(lambda v, a=a: int(v * a * 0.55)))
            if max(fl["size"]) < 18:                           # a speck of a country gets a ring so it can be seen
                ax, ay = fl["anchor"]
                r = 11 + 6 * (1 - a)
                ImageDraw.Draw(im).ellipse((ax - r, ay - r, ax + r, ay + r), outline=col + (255,), width=3)
        d = ImageDraw.Draw(im)
        f = S.font("body", 15)
        for i, (fl, lb) in enumerate(zip(self.fills, self.labels)):
            a = M.clamp01((k - (0.12 + 0.62 * i / n) - 0.12) / 0.2)
            if not lb or a <= 0:
                continue
            col = tuple(int(c * a + 24 * (1 - a)) for c in S.WHITE[:3]) + (255,)
            if lb["lead"]:
                ax, ay = fl["anchor"]
                ex = lb["x"] - 4 if lb["x"] > ax else lb["x"] + lb["w"] + 4
                d.line([(ax, ay), (ex, lb["y"] + lb["h"] / 2)], fill=S.GREY, width=1)
                d.ellipse((ax - 2, ay - 2, ax + 2, ay + 2), fill=S.WHITE)
            _spaced(d, (lb["x"], lb["y"]), lb["text"], f, col)
        fp = S.font("body", 14)
        for (x, y), name in self.pin_xy:
            a = M.clamp01((k - 0.8) / 0.18)
            if a <= 0:
                continue
            r = 4 + 3 * (1 - a)
            d.ellipse((x - r, y - r, x + r, y + r), fill=S.YELLOW, outline=S.WHITE, width=1)
            if a > 0.5 and name and name.upper() not in {fl["label"] for fl in self.fills}:
                _spaced(d, (x + 10, y - fp.size / 2 - 1), name.upper(), fp, S.YELLOW, 0.16)
        if self.title:
            ta = M.ease_out(M.clamp01(k / 0.2))
            ft = S.font("serif", 50)
            col = tuple(int(c * ta + 20 * (1 - ta)) for c in S.WHITE[:3]) + (255,)
            d.text((38, 26 + (1 - ta) * 10), self.title, font=ft, fill=col, stroke_width=3, stroke_fill=(0, 0, 0, 255))
        im.putalpha(ImageChops.multiply(im.getchannel("A"), self.mask))
        return im


@lru_cache(maxsize=8)
def _political(key: str) -> _Political:
    return _Political(json.loads(key))


def _clean(a: Dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in a.items() if k != "_k"}, sort_keys=True, default=str)


def political_map(a: Dict[str, Any]) -> Image.Image:
    k = a.get("_k")
    return _political(_clean(a)).frame(1.0 if k is None else float(k))


# ---------------------------------------------------------------------------------------------------------------- S7 route map

class _Route:
    def __init__(self, a: Dict[str, Any]):
        self.w, self.h = int(a.get("width", 1100)), int(a.get("height", 620))
        self.title = str(a.get("title") or "Scheduled Route Map")
        self.year = str(a.get("year") or "").strip()
        al = C.get_airline(str(a.get("airline") or "")) if a.get("airline") else None
        self.airline_name = (al or {}).get("name") or str(a.get("airline") or "")
        self.hubs = [p for p in (_place(h) for h in a.get("hubs") or []) if p]
        self.dests = []
        hub_ids = {h.get("id") for h in self.hubs}
        for dd in a.get("destinations") or []:
            col = _color(dd.get("color"), None) if isinstance(dd, dict) else None
            p = _place(dd.get("id") if isinstance(dd, dict) and "id" in dd else dd)
            if p and p.get("id") not in hub_ids and all(p.get("id") != q[0].get("id") for q in self.dests):
                self.dests.append((p, col))
        pts = [(h["lat"], h["lon"]) for h in self.hubs] + [(p["lat"], p["lon"]) for p, _ in self.dests]
        if pts:
            xs, ys = merc_xy(np.array([p[1] for p in pts]), np.array([p[0] for p in pts]))
            self.view = _view((float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())), self.w, self.h, pad=0.26,
                              min_span=0.004, lift=0.06)
        else:
            self.view = _view((0.0, 0.18, 1.0, 0.78), self.w, self.h, pad=0.02)
        self.base = _draw_land(self.w, self.h, self.view, LAND_RT, BORDER_RT, SEA_RT, 0.8)
        self.mask = _rounded(self.w, self.h)
        P = _Proj(self.view, self.w, self.h, 1)
        self.hub_px = [P.pt(h["lat"], h["lon"]) for h in self.hubs]
        self.arcs = []
        for p, col in self.dests:
            hi = 0 if len(self.hubs) == 1 else min(range(len(self.hubs)),
                                                    key=lambda j: math.hypot(self.hub_px[j][0] - P.pt(p["lat"], p["lon"])[0],
                                                                             self.hub_px[j][1] - P.pt(p["lat"], p["lon"])[1]))
            if not self.hubs:
                break
            q = P.pt(p["lat"], p["lon"])
            h0 = self.hub_px[hi]
            best = None
            for bend in (0.12, -0.12):                       # bow the arc poleward, like a great circle on a flat map
                pts_ = F.leg_curve(h0, q, bend=bend, n=64)
                if best is None or pts_[32][1] < best[32][1]:
                    best = pts_
            self.arcs.append({"pts": best, "end": q, "name": p["name"], "col": col or HUB_COLORS[hi % len(HUB_COLORS)]})
        self.layout_labels()
        self.glow = self._glow()
        self.head = self._header()

    def layout_labels(self):
        f = S.font("body", 14)
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        placed = [(x - 10, y - 10, x + 10, y + 10) for x, y in self.hub_px]
        self.labels = []
        for ar in self.arcs:
            x, y = ar["end"]
            tw = _spaced_w(probe, ar["name"].upper(), f, 0.16)
            for dx, dy in ((10, -8), (-10 - tw, -8), (-tw / 2, -26), (-tw / 2, 12), (10, 8), (-10 - tw, 8)):
                r = (x + dx - 3, y + dy - 2, x + dx + tw + 3, y + dy + f.size + 4)
                if _free_rect(r, placed, self.w, self.h):
                    placed.append(r)
                    self.labels.append((x + dx, y + dy))
                    break
            else:
                self.labels.append((x + 10, y - 8))
        self.hub_labels = []
        for (x, y), h in zip(self.hub_px, self.hubs):
            tw = _spaced_w(probe, h["name"].upper(), S.font("body", 17), 0.16)
            for dx, dy in ((14, -30), (-14 - tw, -30), (14, 10), (-14 - tw, 10)):
                r = (x + dx - 3, y + dy - 2, x + dx + tw + 3, y + dy + 26)
                if _free_rect(r, placed, self.w, self.h):
                    placed.append(r)
                    self.hub_labels.append((x + dx, y + dy))
                    break
            else:
                self.hub_labels.append((x + 14, y - 30))

    @staticmethod
    def _glow() -> Image.Image:
        g = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse((30, 30, 66, 66), fill=(255, 206, 48, 200))
        return g.filter(ImageFilter.GaussianBlur(12))

    def _header(self) -> Image.Image:
        """Title (serif) top-left, year box + legend top-right: drawn once."""
        im = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((36, 24), self.title, font=S.font("serif", 44), fill=S.WHITE, stroke_width=3, stroke_fill=(0, 0, 0, 255))
        if self.airline_name:
            _spaced(d, (38, 82), self.airline_name.upper(), S.font("body", 17), S.YELLOW, 0.18)
        y = 28
        if self.year:
            f = S.font("badge", 34)
            tw = L.spaced_width(d, self.year, f, 0.4)
            bw = tw + 40
            d.rounded_rectangle((self.w - 30 - bw, y, self.w - 30, y + 58), radius=10, fill=S.NAVY)
            L.spaced(d, (self.w - 30 - bw + 20, y + 8), self.year, f, S.WHITE, 0.4)
            y += 78
        leg = self.legend_items
        if leg:
            fl = S.font("body", 17)
            rows = [(c, l) for c, l in leg]
            lw = max(_spaced_w(d, l.upper(), fl, 0.12) for _, l in rows) + 62
            lh = 18 + 30 * len(rows)
            card = Image.new("RGBA", (int(lw), lh), (0, 0, 0, 0))
            cd = ImageDraw.Draw(card)
            cd.rounded_rectangle((0, 0, lw - 1, lh - 1), radius=10, fill=(16, 18, 24, 215), outline=(70, 74, 86, 255), width=1)
            for i, (c, l) in enumerate(rows):
                yy = 14 + 30 * i
                cd.rounded_rectangle((16, yy + 8, 40, yy + 12), radius=2, fill=c)
                _spaced(cd, (50, yy), l.upper(), fl, S.WHITE, 0.12, halo_w=0)
            im.alpha_composite(card, (int(self.w - 30 - lw), y))
        return im

    legend_items: List[Tuple[Tuple[int, int, int, int], str]] = []

    def frame(self, k: float) -> Image.Image:
        im = self.base.copy()
        n = max(1, len(self.arcs))
        over = Image.new("RGBA", (self.w * 2, self.h * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        for i, ar in enumerate(self.arcs):
            st = 0.1 + 0.62 * i / n
            f = M.ease_in_out(M.clamp01((k - st) / 0.36))
            if f <= 0:
                continue
            pts = ar["pts"]
            m = max(2, int(round(f * (len(pts) - 1))) + 1)
            seg = [(x * 2, y * 2) for x, y in pts[:m]]
            if len(seg) > 1:
                d.line(seg, fill=ar["col"][:3] + (70,), width=9, joint="curve")        # soft under-glow
                d.line(seg, fill=ar["col"][:3] + (235,), width=4, joint="curve")
            if f >= 0.98:
                x, y = ar["end"]
                r = 5 + 3 * (1 - M.clamp01((k - st - 0.36) / 0.08))
                d.ellipse((x * 2 - r * 2, y * 2 - r * 2, x * 2 + r * 2, y * 2 + r * 2), fill=S.WHITE, outline=ar["col"], width=3)
        over = over.resize((self.w, self.h), Image.LANCZOS)
        ha = M.ease_out(M.clamp01(k / 0.12))
        for (x, y) in self.hub_px:
            g = self.glow.copy()
            g.putalpha(g.getchannel("A").point(lambda v: int(v * ha)))
            im.alpha_composite(g, (int(x - 48), int(y - 48)))
        im.alpha_composite(over)
        d = ImageDraw.Draw(im)
        f = S.font("body", 14)
        for i, (ar, (lx, ly)) in enumerate(zip(self.arcs, self.labels)):
            st = 0.1 + 0.62 * i / n
            a = M.clamp01((k - st - 0.3) / 0.12)
            if a > 0:
                col = tuple(int(c * a + 30 * (1 - a)) for c in S.WHITE[:3]) + (255,)
                _spaced(d, (lx, ly), ar["name"].upper(), f, col, 0.16)
        for (x, y), (lx, ly), h in zip(self.hub_px, self.hub_labels, self.hubs):
            d.ellipse((x - 8, y - 8, x + 8, y + 8), fill=S.YELLOW, outline=S.WHITE, width=2)
            if ha > 0.3:
                _spaced(d, (lx, ly), h["name"].upper(), S.font("body", 17), S.YELLOW, 0.16)
        hd = self.head
        if ha < 1:
            hd = hd.copy()
            hd.putalpha(hd.getchannel("A").point(lambda v: int(v * ha)))
        im.alpha_composite(hd)
        im.putalpha(ImageChops.multiply(im.getchannel("A"), self.mask))
        return im


def _route_legend(r: _Route, a: Dict[str, Any]) -> List[Tuple[Tuple[int, int, int, int], str]]:
    if a.get("legend"):
        return [(_color(x.get("color"), S.YELLOW), str(x.get("label", ""))) for x in a["legend"] if isinstance(x, dict) and x.get("label")]
    if len(r.hubs) > 1:
        return [(HUB_COLORS[i % len(HUB_COLORS)], f"From {h['name']}") for i, h in enumerate(r.hubs)]
    if r.airline_name and r.arcs:
        return [(r.arcs[0]["col"], r.airline_name)]
    return []


@lru_cache(maxsize=8)
def _route(key: str) -> _Route:
    a = json.loads(key)
    r = _Route.__new__(_Route)
    r.legend_items = []
    _Route.__init__(r, a)                 # builds the map; the legend (needs the arc colours) then the header
    r.legend_items = _route_legend(r, a)
    r.head = r._header()
    return r


def route_map(a: Dict[str, Any]) -> Image.Image:
    k = a.get("_k")
    return _route(_clean(a)).frame(1.0 if k is None else float(k))


G.register("political_map", political_map)
G.register("route_map", route_map)


def routes_from(text_or_csv: str, airline: str = "") -> Dict[str, Any]:
    """Hub = the airline's catalog hub(s); destinations = the airports the text names, once each, in order of mention. Nothing else."""
    al = C.get_airline(airline) if airline else None
    if not al and airline:
        hits = C.find_airlines(airline)
        al = hits[0].entry if hits else None
    hubs = [h for h in (al or {}).get("hubs", []) if C.get_airport(h)]
    seen, dests = set(hubs), []
    spans = set()
    for m in sorted(C.find_airports(str(text_or_csv or "")), key=lambda m: m.start):
        if m.start in spans or m.entry["id"] in seen:
            continue                     # a city with two airports (Tokyo, Paris) is named once: the first listed
        spans.add(m.start)
        seen.add(m.entry["id"])
        dests.append(m.entry["id"])
    return {"hubs": hubs, "destinations": dests, "airline": (al or {}).get("id", "")}


# ---------------------------------------------------------------------------------------------------------------- builders

def add_political_map(st: G.Stage, at: float, countries: Sequence[Any], title: str = "", focus: Optional[Sequence[str]] = None,
                      places: Optional[Sequence[Any]] = None, anim: float = 2.6, enter: str = "fade", pos: Tuple[float, float] = (640, 392),
                      width: int = 1100, height: int = 620, **kw) -> str:
    args = {"countries": [c for c in countries], "title": title, "width": width, "height": height}
    if focus:
        args["focus"] = list(focus)
    if places:
        args["places"] = list(places)
    return st.add("political_map", at, args, pos=pos, enter=enter if enter in ("fade", "rise") else "fade", anim=anim, float_=False,
                  edge=False, **kw)


def add_route_map(st: G.Stage, at: float, hubs: Sequence[str], destinations: Sequence[Any], airline: str = "",
                  year: Any = None, title: str = "Scheduled Route Map", legend: Optional[Sequence[Dict[str, Any]]] = None,
                  anim: float = 3.0, enter: str = "fade", pos: Tuple[float, float] = (640, 398), width: int = 1200, height: int = 590,
                  **kw) -> str:
    args: Dict[str, Any] = {"hubs": list(hubs), "destinations": list(destinations), "title": title, "width": width, "height": height}
    if airline:
        args["airline"] = airline
    if year:
        args["year"] = str(year)
    if legend:
        args["legend"] = list(legend)
    return st.add("route_map", at, args, pos=pos, enter=enter if enter in ("fade", "rise") else "fade", anim=anim, float_=False,
                  edge=False, **kw)
