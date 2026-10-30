"""War Documentary tactical / political explainer maps: a deterministic PIL renderer built on maps.py (same projection, camera maths, label
placement and Natural Earth data; no new mapping engine, no network). TACTICAL_CARDS = {"tac_map": ..., "tac_route": ...}, both full-frame opaque.

Two looks (params["theme"]):
  "tactical"  dark charcoal map, thin country outlines, no fills, faint graticule (default)
  "political" flat navy / crimson schematic country fill with the same graticule and outlines (fills default to Ukraine blue, Russia red)

tac_map params (all optional):
  places   [str | {id|name, lat?, lon?, label?, kind: pin|ring|zone, colour: white|red|blue|amber, start?}]
           a name is resolved from the war catalogue, then the gazetteer, then a small built-in list of well known towns; `lat`/`lon` given by the
           caller are used as given. A place that cannot be resolved (or that is an area such as a country or a sea) is SKIPPED and listed in
           params["_skipped"]; nothing is guessed. `zone` is a dashed highlight circle, never a crosshair.
  routes   [{from, to, style: dashed_blue|dashed_red|arrow, label?, start?, length?}]  between two resolvable places only; the label chip always
           carries ILLUSTRATIVE (a route is a drawing between two named places, not a track)
  glyphs   [{place, kind: drone|explosion|ring|swarm, heading_to?: place, dx?, dy?, start?}]  small symbols at a named place; use only
           for what the narration states. `swarm`: a few small arrows flying in toward the place (drones named by the narration)
  focus    [place | [place, ...], ...]   camera steps: one frame per entry, the camera pushes/pans between them over the card
           (without focus the camera frames every resolved place; without places, `frame` (maps.py presets) or Ukraine)
  frame, theme, fills [{name|iso3, role: blue|red|neutral|gold|teal|brown|purple|pink|green|orange|slate, start?}], graticule (bool),
           badge (text; never empty). A fill with `start` > 0 fades in at that time (the country lights up when it is named);
           country_roles() gives every country one colour for a whole video (Russia red, Ukraine blue, Belarus brown, the rest in order)
  chips    [{title, sub?, variant: dark|red|blue|white, start?, group?}]   note chips stacked on the right; with `group`, only the latest
           group that has started is shown, so the stack clears and builds again
  focus    may also hold {"country": name|iso3}: the camera frames that country's mainland
  focus_times [s, ...]  when each focus step begins (narration sync); without it the steps share the card evenly
  t_offset, total_dur   one long map split around other cards: each piece renders at t + t_offset of a map total_dur long, so markers,
           cards and camera carry on instead of starting again
tac_route params: from, to, label?, style?, theme?  (frames both places, draws one illustrative route and a straight-line distance panel)

Honesty: no frontline, unit position or event is ever drawn from nothing; the badge ILLUSTRATIVE MAP - APPROXIMATE POSITIONS is always on.
"""

from __future__ import annotations

import logging
import math
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from . import geo_data as G
from . import map_fx as FX
from . import maps as MP
from . import motion as M
from . import stickers as ST
from . import tokens as T
from .. import look as L

log = logging.getLogger("cinematic_explainer.war.maps_tactical")

W, H = T.W, T.H
SS = 2
BADGE_DEFAULT = "ILLUSTRATIVE MAP – APPROXIMATE POSITIONS"

BG = (21, 23, 27, 255)
GRID = (64, 70, 80, 255)
GRID_SQ = (46, 52, 62, 255)
OUTLINE = (128, 136, 148, 255)
LAND_T = (31, 34, 40, 255)
WHITE = (242, 242, 240, 255)
RED = (228, 58, 68, 255)
BLUE = (86, 152, 236, 255)
AMBER = (246, 196, 52, 255)
POL_BLUE = (30, 66, 150, 255)
POL_RED = (152, 34, 56, 255)
POL_NEUTRAL = (36, 40, 48, 255)
POL_EDGE = {"blue": (92, 132, 214, 255), "red": (222, 96, 112, 255), "neutral": OUTLINE}
POL_FILL = {"blue": POL_BLUE, "red": POL_RED, "neutral": POL_NEUTRAL, "a": POL_RED, "b": POL_BLUE,
            "gold": (150, 118, 26, 255), "teal": (26, 116, 104, 255), "brown": (112, 74, 44, 255), "purple": (88, 66, 150, 255),
            "pink": (150, 80, 124, 255), "green": (62, 112, 52, 255), "orange": (164, 88, 32, 255), "slate": (70, 96, 118, 255)}
FIXED_ROLES = {"RUS": "red", "UKR": "blue", "BLR": "brown"}
ROLE_ORDER = ("gold", "teal", "purple", "pink", "green", "orange", "slate")


def country_roles(names: Sequence[str], assigned: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """{ISO3: colour role} for the countries named, in order of first mention: Russia red, Ukraine blue, Belarus brown, the others take the
    next free colour. Pass the same `assigned` dict for a whole video so a country keeps its colour from map to map. Unknown names are skipped."""
    out = assigned if assigned is not None else {}
    for nm in names:
        f = G.find_country(str(nm))
        if f is None or f.iso in out:
            continue
        if f.iso in FIXED_ROLES:
            out[f.iso] = FIXED_ROLES[f.iso]
            continue
        used = set(out.values())
        free = [r for r in ROLE_ORDER if r not in used]
        out[f.iso] = free[0] if free else ROLE_ORDER[len(out) % len(ROLE_ORDER)]
    return out
COLOURS = {"white": WHITE, "red": RED, "blue": BLUE, "amber": AMBER}

# Well known towns the catalogue and gazetteer do not hold yet (approximate town-centre coordinates; lat, lon).
EXTRA_PLACES: Dict[str, Tuple[float, float]] = {
    "kupiansk": (49.71, 37.62), "sudzha": (51.19, 35.27), "ryazan": (54.63, 39.74), "lyman": (48.99, 37.80), "ukhta": (63.57, 53.68),
    "tuapse": (44.10, 39.07), "vovchansk": (50.29, 36.94), "kostiantynivka": (48.53, 37.71), "chasiv yar": (48.59, 37.83),
    "zaporizhzhia": (47.84, 35.14), "orsk": (51.20, 58.57), "saratov": (51.53, 46.03), "engels": (51.48, 46.12), "yeysk": (46.71, 38.27),
}
_AREA_TYPES = ("country", "sea", "region", "area", "state")


# ---------------------------------------------------------------------------------------------------------------- places
def _key(s: Any) -> str:
    return " ".join(str(s or "").lower().replace("-", " ").split())


def resolve_place(ref: Any) -> Tuple[Optional[Dict[str, Any]], str]:
    """({name, lat, lon, approximate}, '') or (None, reason). Never guesses: unknown, ambiguous and area-type names give a reason."""
    if isinstance(ref, dict):
        name = str(ref.get("name") or ref.get("id") or ref.get("label") or "").strip()
        try:
            if ref.get("lat") is not None and ref.get("lon") is not None:
                return {"name": name or "place", "lat": float(ref["lat"]), "lon": float(ref["lon"]), "approximate": True}, ""
        except (TypeError, ValueError):
            return None, "unusable coordinates"
    else:
        name = str(ref or "").strip()
    if not name:
        return None, "no name"
    try:
        from . import catalog as C

        for m in C.find_place(name):
            e = m.entry
            if e and m.confidence == "exact" and _key(name) in {_key(a) for a in [e.get("name"), e.get("id")] + list(e.get("aliases") or [])}:
                if str(e.get("type") or "") in _AREA_TYPES or e.get("lat") is None:
                    return None, f"{e.get('name')} is an area, not a point"
                return {"name": str(e["name"]), "lat": float(e["lat"]), "lon": float(e["lon"]), "approximate": bool(e.get("approximate"))}, ""
    except Exception as exc:  # the catalogue must never stop a render
        log.debug("catalogue lookup failed: %s", exc)
    ll = G.gazetteer(name)
    if ll:
        return {"name": name, "lat": ll[0], "lon": ll[1], "approximate": False}, ""
    ex = EXTRA_PLACES.get(_key(name))
    if ex:
        return {"name": name.title() if name.islower() else name, "lat": ex[0], "lon": ex[1], "approximate": True}, ""
    return None, "unknown place"


def _T(params: dict, kind: str, i: int, default: float) -> float:
    """Start time (s from card start) of the i-th element of a kind: params["times"][kind][i] when given (narration sync), else the default."""
    try:
        v = (params.get("times") or {}).get(kind)
        return float(v[i]) if v is not None and i < len(v) else float(default)
    except (TypeError, ValueError, IndexError):
        return float(default)


def _after_places(params: dict) -> float:
    """When the last marker has landed: routes, glyphs and chips follow it (region first, then markers, then route, then notes)."""
    n = len([p for p in (params.get("places") or []) if p])
    return 0.8 + 0.3 * max(0, n - 1) + 0.35


def _chip_defaults(params: dict) -> List[dict]:
    """Chips with their start times filled in: after the last route has drawn (or after the markers when there is no route)."""
    chips = [dict(c) for c in (params.get("chips") or []) if isinstance(c, dict)]
    n_routes = len([r for r in (params.get("routes") or []) if isinstance(r, dict)])
    base = _after_places(params) + (0.3 + 0.7 * max(0, n_routes - 1) + 1.2 if n_routes else 0.0) + 0.2
    for i, c in enumerate(chips):
        if "start" not in c:
            c["start"] = _T(params, "chips", i, base + 0.45 * i)
    return chips


def _find_region(name: str) -> Any:
    """A country (ISO3 or name) or an oblast / region of the theatre by name; None when unknown (nothing is guessed)."""
    if not name.strip():
        return None
    f = G.find_country(name)
    if f is not None:
        return f
    k = G._norm(name)
    for a in G.theatre_admin1():
        if G._norm(a.name) == k or any(G._norm(x) == k for x in a.alts):
            return a
    return None


def _gather(params: dict) -> Dict[str, Any]:
    """Resolve everything the card names once: places, routes, glyphs, focus steps, skipped list. Pure function of params."""
    skipped: List[str] = []
    cache: Dict[str, Optional[Dict[str, Any]]] = {}

    def get(ref: Any, what: str) -> Optional[Dict[str, Any]]:
        k = repr(ref)
        if k not in cache:
            p, why = resolve_place(ref)
            cache[k] = p
            if p is None:
                skipped.append(f"{what} {ref if not isinstance(ref, dict) else ref.get('name') or ref.get('id')}: {why}")
        return cache[k]

    places = []
    for i, r in enumerate(params.get("places") or []):
        p = get(r, "place")
        if p is None:
            continue
        spec = r if isinstance(r, dict) else {}
        kind = str(spec.get("kind") or "pin")
        kind = "zone" if kind == "target_zone" else kind
        places.append({**p, "label": str(spec.get("label") or p["name"]), "kind": kind if kind in ("pin", "ring", "zone") else "pin",
                       "colour": COLOURS.get(str(spec.get("colour") or ("red" if kind == "ring" else "white")), WHITE),
                       "start": float(spec.get("start", _T(params, "places", i, 0.8 + 0.3 * i)))})
    routes = []
    for i, r in enumerate(params.get("routes") or []):
        if not isinstance(r, dict):
            continue
        a, b = get(r.get("from"), "route from"), get(r.get("to"), "route to")
        if a and b:
            routes.append({"a": a, "b": b, "style": str(r.get("style") or "dashed_blue"), "label": str(r.get("label") or ""),
                           "start": float(r.get("start", _T(params, "routes", i, _after_places(params) + 0.3 + 0.7 * i))), "length": float(r.get("length", 1.2))})
    glyphs = []
    for i, g in enumerate(params.get("glyphs") or []):
        if not isinstance(g, dict):
            continue
        p = get(g.get("place"), "glyph at")
        if p:
            h = get(g.get("heading_to"), "glyph heading") if g.get("heading_to") else None
            glyphs.append({"p": p, "kind": str(g.get("kind") or "ring"), "name": str(g.get("name") or ""), "h": h, "dx": float(g.get("dx", 0)), "dy": float(g.get("dy", 0)),
                           "start": float(g.get("start", _T(params, "glyphs", i, _after_places(params) + 0.3 * i)))})
    regions = []
    for i, r in enumerate(params.get("regions") or []):
        spec = r if isinstance(r, dict) else {"name": r}
        feat = _find_region(str(spec.get("iso3") or spec.get("name") or ""))
        if feat is None:
            skipped.append(f"region {spec.get('iso3') or spec.get('name')}: unknown area")
            continue
        regions.append({"f": feat, "label": str(spec.get("label") or feat.name), "colour": COLOURS.get(str(spec.get("colour") or spec.get("role") or "amber"), AMBER),
                        "start": float(spec.get("start", _T(params, "regions", i, 0.4 + 0.35 * i)))})
    steps: List[List[Dict[str, Any]]] = []
    for f in params.get("focus") or []:
        refs = f if isinstance(f, (list, tuple)) else [f]
        pts = []
        for r in refs:
            if isinstance(r, dict) and r.get("country"):
                pts += _country_points(str(r["country"]))
            else:
                x = get(r, "focus")
                if x:
                    pts.append(x)
        if pts:
            steps.append(pts)
    if not steps:
        pts = [x for x in ({"lat": p["lat"], "lon": p["lon"]} for p in places)]
        for r in routes:
            pts += [r["a"], r["b"]]
        if pts:
            steps = [pts]
    return {"places": places, "routes": routes, "glyphs": glyphs, "regions": regions, "steps": steps, "skipped": skipped}


_MAINLAND = {"RUS": (28.0, 44.0, 50.0, 62.0), "USA": (-125.0, 25.0, -67.0, 49.0), "FRA": (-5.0, 42.3, 8.2, 51.1), "NOR": (4.5, 57.9, 31.0, 71.2)}


def _country_points(name: str) -> List[Dict[str, Any]]:
    """Two corners of a country's mainland (its largest polygon; western Russia for Russia) for the camera; [] when unknown."""
    f = G.find_country(name)
    if f is None or not f.polys:
        return []
    bb = _MAINLAND.get(f.iso) or max((p[0].bbox for p in f.polys), key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    return [{"lon": bb[0], "lat": bb[1]}, {"lon": bb[2], "lat": bb[3]}]


# ---------------------------------------------------------------------------------------------------------------- framing
PANEL_W = 316                    # note-chip column (px); the framing keeps the subject in the frame to its left
PANEL_FRAC = 0.70                # share of the frame width left of the panel
MIN_SPAN_DEG = {"tactical": 9.0, "political": 10.0}   # never frame tighter than this many degrees of longitude (about 640 km at 50 N)
MIN_CONTEXT = 3                                       # at least this many quiet context cities in view; the frame widens until they are
MAX_SPAN_DEG = 70.0


def _frame_points(params: dict) -> List[Dict[str, Any]]:
    """The corners of an explicit `frame` (when no focus steps are given) so the named region stays in view around the places."""
    if params.get("focus") or params.get("frame") is None:
        return []
    try:
        bb = MP._frame_bbox(params.get("frame"), [])
    except Exception:
        return []
    return [{"lon": bb[0], "lat": bb[1]}, {"lon": bb[2], "lat": bb[3]}]


def _has_panel(params: dict, extra_panel: Optional[dict] = None) -> bool:
    return bool([c for c in (params.get("chips") or []) if isinstance(c, dict) and c.get("title")]) or bool(extra_panel)


def _step_view(pts: Sequence[Dict[str, Any]], theme: str, panel: bool, size: Tuple[int, int]) -> MP.View:
    """A useful regional view for the points: the subject stays within the middle 60 % of the space left of the panel, and the view is never
    tighter than MIN_SPAN_DEG of longitude, so country context and several context labels are always on screen."""
    w, h = size
    x0, x1 = math.radians(min(p["lon"] for p in pts)), math.radians(max(p["lon"] for p in pts))
    y0, y1 = G.merc(min(p["lat"] for p in pts)), G.merc(max(p["lat"] for p in pts))
    u = PANEL_FRAC if panel else 1.0
    hw = max((x1 - x0) / (2 * 0.60 * u), (y1 - y0) / (2 * 0.58 * h / w), math.radians(MIN_SPAN_DEG[theme] / 2))
    hw = min(hw, math.radians(MAX_SPAN_DEG / 2))
    cx = (x0 + x1) / 2 + hw * (1 - u)
    return MP.View(cx, (y0 + y1) / 2, hw, w, h)


def _context_count(view: MP.View, named: Sequence[str] = ()) -> int:
    lo0, la0, lo1, la1 = view.bounds()
    inset = 0.06 * (lo1 - lo0)
    return sum(1 for c in G.context_cities() if lo0 + inset < c["lon"] < lo1 - inset and la0 < c["lat"] < la1 and str(c["n"]).lower() not in named)


def _widen(v: MP.View, named: Sequence[str]) -> MP.View:
    """Widen a view by 25 % (up to three times) until at least MIN_CONTEXT context cities are on screen: a map of two dots on empty charcoal says
    nothing, so when the geography around the subject is thin the frame shows more of it (never invented detail)."""
    for _ in range(3):
        if _context_count(v, named) >= MIN_CONTEXT or v.hw >= math.radians(MAX_SPAN_DEG / 2):
            break
        v = MP.View(v.cx, v.cy, v.hw * 1.25, v.w, v.h)
    return v


def _views(params: dict, g: Dict[str, Any], size: Tuple[int, int], warn: List[str], theme: str = "tactical", panel: bool = False) -> List[MP.View]:
    if g["steps"]:
        extra = _frame_points(params)
        named = {str(x.get("label", "")).lower() for x in g["places"]} | {str(x.get("name", "")).lower() for x in g["places"]}
        return [_widen(_step_view(list(s) + extra, theme, panel, size), named) for s in g["steps"]]
    v = MP.view_for(params.get("frame") if params.get("frame") is not None else "ukraine", size, warn, pad=1.0)
    lo = math.radians(MIN_SPAN_DEG[theme] / 2)
    return [MP.View(v.cx, v.cy, max(v.hw, lo), size[0], size[1])]


def _scaled(v: MP.View, f: float) -> MP.View:
    return MP.View(v.cx, v.cy, v.hw * f, v.w, v.h)


WIDE = 1.32                     # the establishing shot opens this much wider than the subject frame


def _cine(view: MP.View, g: Dict[str, Any], t: float, dur: float) -> MP.View:
    """Establishing shot and travel: opens wide, settles onto the subject in 1.5 s, then drifts a little toward where the first route ends."""
    m = 1.0 + (WIDE - 1.0) * (1.0 - M.ease_out(M.ramp(t, 0.0, 1.5)))
    cx, cy = view.cx, view.cy
    if g["routes"]:
        r = g["routes"][0]
        bx, by = math.radians(r["b"]["lon"]), G.merc(r["b"]["lat"])
        k = 0.05 * M.ease_in_out(min(1.0, t / max(dur, 0.1)))
        cx, cy = cx + (bx - cx) * k, cy + (by - cy) * k
    return MP.View(cx, cy, view.hw * m, view.w, view.h)


def _camera(views: List[MP.View], t: float, dur: float, times: Optional[Sequence[float]] = None) -> Tuple[MP.View, bool]:
    """Static-ish push inside each step, eased pan/zoom between steps. Returns (view, moving). `times`: when each step begins."""
    n = len(views)
    if times is not None and len(times) == n and n > 1:
        starts = [0.0] + [max(0.0, float(x)) for x in list(times)[1:]]
        i = max(j for j in range(n) if starts[j] <= t) if t >= 0 else 0
        nxt = starts[i + 1] if i + 1 < n else max(dur, starts[i] + 0.1)
        sd = max(0.5, nxt - starts[i])
        local = t - starts[i]
    else:
        sd = dur / n if dur > 0 else 1.0
        i = min(n - 1, max(0, int(t / sd)))
        local = t - i * sd
    push = lambda f: 1.0 - 0.04 * max(0.0, min(1.0, f))                   # noqa: E731  gentle push-in, 4 % per step
    if i > 0:
        mv = min(1.6, 0.55 * sd)
        if local < mv:
            a = _scaled(views[i - 1], push(1.0))
            b = _scaled(views[i], 1.0)
            k = M.ease_in_out(local / mv)
            return MP.View(M.lerp(a.cx, b.cx, k), M.lerp(a.cy, b.cy, k),
                           math.exp(M.lerp(math.log(a.hw), math.log(b.hw), k)), a.w, a.h), True
    return _scaled(views[i], push(local / sd)), True


# ---------------------------------------------------------------------------------------------------------------- palette
SEA_T, LAND_TAC, NEIGH_TAC = (13, 19, 27), (36, 41, 48), (31, 35, 42)
BORDER_TAC, OBL_TAC, RIVER_TAC, LAKE_TAC = (118, 128, 142), (60, 68, 80), (84, 138, 196), (13, 19, 27)
SEA_P, NEIGH_P = (10, 22, 52), (52, 58, 74)
LABEL_DIM = (150, 158, 170, 255)
LABEL_CTX = (176, 184, 196, 255)
HALO = (8, 10, 14, 255)

# ---------------------------------------------------------------------------------------------------------------- base map (one mosaic per card, cropped per frame)
_BASE: "OrderedDict[tuple, Tuple[Image.Image, tuple]]" = OrderedDict()
_BASE_MAX = 4
_MOSAIC_MAX_W = 4800


def clear_cache() -> None:
    _BASE.clear()
    _ANCH.clear()


def _fills(params: dict, theme: str) -> List[dict]:
    if theme != "political":
        return []
    fills = [f for f in (params.get("fills") or []) if isinstance(f, dict)]
    return fills or [{"iso3": "UKR", "role": "blue"}, {"iso3": "RUS", "role": "red"}]


def _mosaic_view(views: List[MP.View]) -> MP.View:
    """One view that contains every camera step (and the push-in between them) with a small margin; pixel density follows the tightest step."""
    x0 = min(v.cx - v.hw for v in views)
    x1 = max(v.cx + v.hw for v in views)
    y0 = min(v.cy - v.hh for v in views)
    y1 = max(v.cy + v.hh for v in views)
    mx, my = (x1 - x0) * 0.04, (y1 - y0) * 0.04
    x0, x1, y0, y1 = x0 - mx, x1 + mx, y0 - my, y1 + my
    ppr = max(v.w / (2 * v.hw) for v in views) * 1.12            # pixels per radian of longitude
    wpx = (x1 - x0) * ppr
    if wpx > _MOSAIC_MAX_W:
        ppr *= _MOSAIC_MAX_W / wpx
    wpx = max(W, int(round((x1 - x0) * ppr)))
    hpx = max(H, int(round((y1 - y0) * ppr)))
    return MP.View((x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, wpx, hpx)


def _poly_line(d, view: MP.View, pts, ss: int, fill, width: int) -> None:
    import numpy as np

    a = np.asarray(pts, dtype=np.float64)
    x, y = view.px(a[:, 0], G.merc(a[:, 1]), ss)
    q = [(float(i), float(j)) for i, j in zip(x, y)]
    if len(q) >= 2:
        d.line(q, fill=fill, width=width, joint="curve")


def _build_mosaic(mv: MP.View, theme: str, fills: List[dict], grid: bool, look: str = "night") -> Image.Image:
    ss = 2 if mv.w * 2 <= 5200 else 1
    vb = mv.bounds()
    vb = (vb[0] - 0.5, vb[1] - 0.5, vb[2] + 0.5, vb[3] + 0.5)
    pol = theme == "political"
    pl = FX.pal(look)
    SEA_T, LAND_TAC, NEIGH_TAC = pl["sea"], pl["land"], pl["neigh"]
    BORDER_TAC, OBL_TAC, RIVER_TAC, LAKE_TAC = pl["border"], pl["obl"], pl["river"], pl["sea"]
    big = Image.new("RGBA", (mv.w * ss, mv.h * ss), (SEA_P if pol else SEA_T) + (255,))
    d = ImageDraw.Draw(big)
    roles: Dict[str, str] = {}
    for fl in fills:
        feat = G.find_country(str(fl.get("iso3") or fl.get("name") or ""))
        if feat is not None:
            roles[feat.iso] = str(fl.get("role", "neutral"))
    lw = max(1, ss)
    for f in G.countries():
        role = roles.get(f.iso)
        only = None
        if f.iso == "RUS" and "UKR" in roles:
            only = lambda bb: not MP._in_crimea(bb)                   # noqa: E731  Crimea is drawn with Ukraine (recognised borders)
        if pol:
            fill = tuple(POL_FILL.get(role, NEIGH_P))[:3] if role else NEIGH_P
            edge = (236, 238, 242, 255) if role else (150, 156, 170, 255)
            MP._draw_feature(d, f, mv, vb, fill, edge, (SEA_P + (255,)), ss, 2 * lw if role else lw, only=only)
        else:
            fill = LAND_TAC if f.iso in ("UKR", "RUS", "BLR") else NEIGH_TAC
            MP._draw_feature(d, f, mv, vb, fill + (255,), BORDER_TAC + (255,), (SEA_T + (255,)), ss, lw + (ss // 2 if f.iso in ("UKR", "RUS") else 0), only=only)
    if "UKR" in roles and MP._intersects(vb, (32.0, 44.0, 37.0, 46.3)):
        rus = G.find_country("RUS")
        if rus is not None:
            MP._draw_feature(d, rus, mv, vb, POL_FILL.get(roles["UKR"], POL_BLUE), (236, 238, 242, 255), SEA_P + (255,), ss, 2 * lw, only=MP._in_crimea)
    ctx = G.context()
    for lk in ctx.get("lakes", []) or []:                              # lakes and reservoirs in the colour of the sea
        for poly in lk.get("p", []):
            ring = poly[0]
            xs = [c[0] for c in ring]
            ys = [c[1] for c in ring]
            if min(xs) > vb[2] or max(xs) < vb[0] or min(ys) > vb[3] or max(ys) < vb[1]:
                continue
            import numpy as np

            a = np.asarray(ring, dtype=np.float64)
            x, y = mv.px(a[:, 0], G.merc(a[:, 1]), ss)
            if len(x) >= 3:
                MP._poly(d, [(float(i), float(j)) for i, j in zip(x, y)], (SEA_P if pol else LAKE_TAC) + (255,), None)
    if not pol:
        for f in G.theatre_admin1():                                  # oblast / region borders, faint
            if MP._intersects(f.bbox, vb):
                MP._draw_feature(d, f, mv, vb, None, OBL_TAC + (255,), None, ss, lw)
    for rv in ctx.get("rivers", []) or []:
        major = (rv.get("rank") or 9) <= 5 or rv.get("n") in G.RIVER_LABELS
        if not major:
            continue
        for line in rv.get("l", []):
            xs = [c[0] for c in line]
            ys = [c[1] for c in line]
            if min(xs) > vb[2] or max(xs) < vb[0] or min(ys) > vb[3] or max(ys) < vb[1]:
                continue
            _poly_line(d, mv, line, ss, (RIVER_TAC + (255,)) if not pol else (70, 112, 176, 255), max(1, int(round(ss * (1.6 if (rv.get("rank") or 9) <= 3 else 1.1)))))
    if grid:
        col = (255, 255, 255, 22) if pol else (86, 98, 114, 90)
        lay = Image.new("RGBA", big.size, (0, 0, 0, 0))
        MP._graticule(ImageDraw.Draw(lay), mv, col, ss, lw)
        big = Image.alpha_composite(big, lay)
    img = (big.reduce(ss) if ss > 1 else big).convert("RGB")
    return FX.shade_coast(img, SEA_P if pol else SEA_T, look)


def _mosaic(views: List[MP.View], theme: str, fills: List[dict], grid: bool, look: str = "night") -> Tuple[Image.Image, MP.View]:
    mv = _mosaic_view(views)
    key = (mv.key(), theme, tuple((str(f.get("iso3") or f.get("name")), f.get("role")) for f in fills), grid, look)
    hit = _BASE.get(key)
    if hit is not None:
        _BASE.move_to_end(key)
        return hit
    img = _build_mosaic(mv, theme, fills, grid, look)
    _BASE[key] = (img, mv)
    while len(_BASE) > _BASE_MAX:
        _BASE.popitem(last=False)
    return img, mv


_VIGS: Dict[Tuple[int, int], Image.Image] = {}


def _crop(mosaic: Image.Image, mv: MP.View, view: MP.View) -> Image.Image:
    """The frame's view out of the mosaic (linear in longitude and Mercator y), resampled to 1280x720 with a soft vignette."""
    mw, mh = mosaic.size
    x0 = (view.cx - view.hw) - (mv.cx - mv.hw)
    y0 = (mv.cy + mv.hh) - (view.cy + view.hh)
    sx = mw / (2 * mv.hw)
    sy = mh / (2 * mv.hh)
    box = (x0 * sx, y0 * sy, (x0 + 2 * view.hw) * sx, (y0 + 2 * view.hh) * sy)
    box = (max(0.0, box[0]), max(0.0, box[1]), min(float(mw), box[2]), min(float(mh), box[3]))
    down = (box[2] - box[0]) / W
    img = mosaic.resize((W, H), Image.LANCZOS if down > 1.4 else Image.BILINEAR, box=box).convert("RGBA")
    if (W, H) not in _VIGS:
        _VIGS[(W, H)] = MP._vignette((W, H), 0.5)
    return Image.composite(Image.new("RGBA", img.size, (0, 0, 0, 255)), img, _VIGS[(W, H)])


# ---------------------------------------------------------------------------------------------------------------- context labels
_ANCH: Dict[tuple, Optional[Tuple[float, float]]] = {}


def _country_anchors(view: MP.View) -> List[Tuple[str, Tuple[float, float]]]:
    """(NAME, (lon, merc y)) label anchors of the theatre's countries visible in the view (cached per view)."""
    key = view.key()
    if key in _ANCH:
        return _ANCH[key] or []
    out = []
    vb = view.bounds()
    for f in G.countries():
        if f.iso not in G.THEATRE_ISO or not MP._intersects(f.bbox, vb):
            continue
        a = MP._anchor(f, view)
        if a and f.iso == "RUS" and 32.0 <= a[0] <= 37.0 and 44.0 <= G.unmerc(a[1]) <= 46.3:
            continue                          # the only visible piece of the polygon is the peninsula: a country name there would be a claim, so none
        if a:
            out.append((f.name.upper(), a))
    _ANCH[key] = out
    return out


def _is_sea(base: Image.Image, x: float, y: float, theme: str, look: str = "night") -> bool:
    """True when the bare map pixel at (x, y) is sea (a label for a sea must not sit on land)."""
    ix, iy = int(max(0, min(W - 1, x))), int(max(0, min(H - 1, y)))
    px = base.getpixel((ix, iy))[:3]
    ref = SEA_P if theme == "political" else FX.pal(look)["sea"]
    return all(abs(int(a) - int(b)) <= 24 for a, b in zip(px, ref))


def _nice_km(target: float) -> int:
    for v in (25, 50, 100, 200, 250, 500, 1000, 2000):
        if v >= target:
            return v
    return 2000


def _scale_bar(img: Image.Image, view: MP.View) -> Tuple[int, int, int, int]:
    d = ImageDraw.Draw(img)
    lat = G.unmerc(view.cy)
    km_per_px = (view.lon_span * 111.32 * math.cos(math.radians(lat))) / W
    km = _nice_km(150 * km_per_px)
    px = int(km / km_per_px)
    f = T.font("bold", 14)
    x, y = 26, H - 40
    d.line([(x, y), (x + px, y)], fill=WHITE, width=3)
    for xx in (x, x + px):
        d.line([(xx, y - 6), (xx, y + 1)], fill=WHITE, width=3)
    d.text((x, y - 24), f"{km} KM", font=f, fill=WHITE, stroke_width=2, stroke_fill=HALO)
    return (x - 4, y - 28, x + px + 8, y + 6)


# ---------------------------------------------------------------------------------------------------------------- glyphs and chips
def _rounded(d: ImageDraw.ImageDraw, box, fill, outline=None, width: int = 1, r: int = 8) -> None:
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _star(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill, rot: float = 0.0) -> None:
    pts = []
    for i in range(16):
        a = rot + math.pi * i / 8
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)


def _chevron(d: ImageDraw.ImageDraw, cx: float, cy: float, ang: float, size: float, fill) -> None:
    tip = (cx + size * math.cos(ang), cy + size * math.sin(ang))
    l = (cx + size * 0.8 * math.cos(ang + 2.5), cy + size * 0.8 * math.sin(ang + 2.5))
    r = (cx + size * 0.8 * math.cos(ang - 2.5), cy + size * 0.8 * math.sin(ang - 2.5))
    n = (cx - size * 0.25 * math.cos(ang), cy - size * 0.25 * math.sin(ang))
    d.polygon([tip, l, n, r], fill=fill)


_CHIP = {"dark": ((22, 24, 28, 245), (128, 134, 144, 255), WHITE, (190, 194, 200, 255)),
         "red": ((206, 40, 56, 250), (255, 150, 150, 255), WHITE, (255, 226, 226, 255)),
         "blue": ((36, 94, 196, 250), (150, 190, 255, 255), WHITE, (222, 234, 255, 255)),
         "white": ((244, 240, 230, 250), (255, 255, 255, 255), (24, 24, 28, 255), (70, 70, 76, 255))}


def _panel(img: Image.Image, t: float, first_start: float, bottom: int) -> Tuple[int, int, int, int]:
    """The bordered side panel the note chips live in: a dark column on the right 28 % of the frame, as tall as its chips."""
    k = M.ease_out(M.ramp(t, max(0.0, first_start - 0.25), 0.4))
    box = (W - 24 - PANEL_W - 14, 60, W - 14, min(H - 56, bottom + 16))
    if k > 0:
        lay = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rectangle([0, 0, lay.width - 1, lay.height - 1], fill=(8, 10, 14, 176), outline=(120, 128, 140, 200), width=1)
        ld.rectangle([0, 0, 4, lay.height - 1], fill=AMBER)
        img.alpha_composite(L.fade(lay, k), (box[0] + int((1 - k) * 40), box[1]))
    return box


def _chip_stack(img: Image.Image, chips: List[dict], t: float, x_right: int, y0: int, draw: bool = True) -> List[Tuple[int, int, int, int]]:
    """Note chips stacked inside the side panel, each sliding in from the edge. Returns the rectangles drawn (full size) for label avoidance."""
    d = ImageDraw.Draw(img)
    ft, fs = T.font("bold", 18), T.font("regular", 15)
    width = PANEL_W - 20
    rects: List[Tuple[int, int, int, int]] = []
    y = y0
    for i, c in enumerate(chips):
        title = str(c.get("title") or "").upper()
        if not title:
            continue
        fill, line, tc, sc = _CHIP.get(str(c.get("variant") or "dark"), _CHIP["dark"])
        lines = MP._wrap(d, c.get("sub", ""), fs, width - 30)[:4] if c.get("sub") else []
        tl = MP._wrap(d, title, ft, width - 30)[:2]
        h = 16 + 24 * len(tl) + (6 + 21 * len(lines) if lines else 0) + 12
        box = (x_right - width, y, x_right, y + h)
        rects.append(box)
        k = M.ease_out(M.ramp(t, float(c.get("start", 1.0 + 0.45 * i)), 0.4))
        if k > 0 and draw:
            dx = int((1 - k) * 60)
            lay = Image.new("RGBA", (width + 8, h + 8), (0, 0, 0, 0))
            ld = ImageDraw.Draw(lay)
            _rounded(ld, (4, 4, width + 4, h + 4), fill, line, 2)
            yy = 4 + 14
            for s in tl:
                L.spaced(ld, (20, yy), s, ft, tc, 0.04)
                yy += 24
            if lines:
                yy += 4
                for s in lines:
                    ld.text((20, yy), s, font=fs, fill=sc)
                    yy += 21
            lay = L.fade(lay, k)
            img.alpha_composite(lay, (box[0] - 4 + dx, box[1] - 4))
        y += h + 14
    return rects


# ---------------------------------------------------------------------------------------------------------------- the renderer
def _km(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _outlined(d: ImageDraw.ImageDraw, xy, text: str, font, fill, stroke: int = 3) -> None:
    d.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=HALO)


def _fill_in_view(fill: dict, vb: G.BBox) -> bool:
    """The filled country shows at least a sliver in the current view (a key for Russia on a map of Bulgaria says nothing)."""
    feat = G.find_country(str(fill.get("iso3") or fill.get("name") or ""))
    if feat is None:
        return False
    y0, y1 = G.merc(vb[1]), G.merc(vb[3])
    for p in feat.polys:                       # a border point inside the view (Russia's own box covers half the globe, so boxes say nothing)
        r = p[0]
        if MP._intersects(r.bbox, vb) and bool(((r.lon >= vb[0]) & (r.lon <= vb[2]) & (r.ym >= y0) & (r.ym <= y1)).any()):
            return True
    return False


def _render(params: dict, t: float, dur: float, extra_panel: Optional[dict] = None) -> Tuple[Image.Image, dict]:
    theme = "political" if str(params.get("theme") or "tactical") == "political" else "tactical"
    g = _gather(params)
    params["_skipped"] = list(g["skipped"])
    info: Dict[str, Any] = {"skipped": g["skipped"], "labels": [], "theme": theme, "warnings": [], "context_labels": []}
    panel_on = _has_panel(params, extra_panel)
    views = _views(params, g, (W, H), info["warnings"], theme, panel_on)
    look = str(params.get("look") or "night")
    look = look if look in FX.LOOKS else "night"
    ft = params.get("focus_times") if g["steps"] and len(params.get("focus_times") or []) == len(views) else None
    view, _moving = _camera(views, t, max(dur, 0.1), ft)
    view = _cine(view, g, t, dur)
    info["view"] = view.key()
    fills = _fills(params, theme)
    late = [f for f in fills if float(f.get("start") or 0.0) > 0.0]       # these light up when named; the rest are in the base map
    mosaic, mv = _mosaic(views + [_scaled(v, WIDE) for v in views], theme, [f for f in fills if f not in late],
                         params.get("graticule", True) is not False, look)
    img = _crop(mosaic, mv, view)
    basecrop = img.copy()                                                  # the bare map, to test whether a label anchor really is open water
    named_px = [view.pt(pl["lat"], pl["lon"]) for pl in g["places"]]
    if named_px:                                                           # the subject carries the frame: everything away from it falls into shadow
        img = FX.spotlight(img, sum(p[0] for p in named_px) / len(named_px), sum(p[1] for p in named_px) / len(named_px))
    img = FX.grain(img, int(round(t * 25)))
    k_in = 0.35 + 0.65 * M.ease_out(M.ramp(t, 0.0, 0.6))                  # the region establishes first: the map brightens in over 0.6 s
    if k_in < 1.0:
        img = Image.blend(Image.new("RGBA", img.size, (0, 0, 0, 255)), img, k_in)

    ov = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)

    def P(lat: float, lon: float) -> Tuple[float, float]:
        return view.pt(lat, lon, SS)

    vb_now = view.bounds()
    for fl in late:                                                        # a country named later fills in with its colour
        k = M.ease_out(M.ramp(t, float(fl["start"]), 0.6))
        feat = G.find_country(str(fl.get("iso3") or fl.get("name") or ""))
        if k <= 0 or feat is None or not MP._intersects(feat.bbox, vb_now):
            continue
        col = tuple(POL_FILL.get(str(fl.get("role")), NEIGH_P + (255,)))[:3]
        MP._draw_feature(od, feat, view, vb_now, col + (int(255 * k),), (236, 238, 242, int(235 * k)), (0, 0, 0, 0), SS, 2 * SS)

    # region highlights (the first layer after the base map): a soft tint, a clean outline, a name tag
    region_tags: List[Tuple[str, Tuple[float, float], float]] = []
    for rg in g["regions"]:
        k = M.ease_out(M.ramp(t, rg["start"], 0.7))
        if k <= 0:
            continue
        col = rg["colour"]
        MP._draw_feature(od, rg["f"], view, vb_now, col[:3] + (int(46 * k),), col[:3] + (int(235 * k),), (0, 0, 0, 0), SS, 2 * SS)
        c = MP._anchor(rg["f"], view)
        if c:
            ax, ay = view.px(c[0], c[1])
            region_tags.append((rg["label"], (float(ax), float(ay)), k))

    # routes (under markers)
    route_marks: List[Tuple[str, Tuple[float, float], bool]] = []
    for r in g["routes"]:
        xy = MP._curve(P(r["a"]["lat"], r["a"]["lon"]), P(r["b"]["lat"], r["b"]["lon"]), 0.12)
        frac = M.draw_fraction(t, r["start"], r["length"])
        if frac <= 0:
            continue
        part = M.partial_polyline(xy, frac)
        if len(part) < 2:
            continue
        style = r["style"]
        col = RED if style == "dashed_red" else BLUE if style == "dashed_blue" else WHITE
        lw = 4 * SS
        under = tuple(HALO[:3]) + (200,)
        if style == "arrow":
            od.line(part, fill=under, width=lw + 3 * SS, joint="curve")
            od.line(part, fill=col, width=lw + SS, joint="curve")
            MP._arrow_head(od, part[-1], part[-2] if len(part) > 2 else part[0], 20 * SS, col)
        else:
            for seg in MP._dashes(part, 15 * SS, 9 * SS):
                od.line(seg, fill=under, width=lw + 3 * SS, joint="curve")
            for seg in MP._dashes(part, 15 * SS, 9 * SS):
                od.line(seg, fill=col, width=lw, joint="curve")
            MP._arrow_head(od, part[-1], part[-2] if len(part) > 2 else part[0], 16 * SS, col)
        hx, hy = part[-1]
        if frac < 0.999:                                           # the head of the line glows and leaves a bright trail
            tail = part[int(len(part) * 0.72):]
            if len(tail) >= 2:
                od.line(tail, fill=(255, 255, 255, 150), width=lw + SS, joint="curve")
            for gr, ga in ((20, 60), (12, 120)):
                od.ellipse([hx - gr * SS, hy - gr * SS, hx + gr * SS, hy + gr * SS], fill=col[:3] + (ga,))
            od.ellipse([hx - 5 * SS, hy - 5 * SS, hx + 5 * SS, hy + 5 * SS], fill=(255, 255, 255, 255))
        else:                                                      # once drawn, a light travels along it so the line stays alive
            for off in (0.0, 0.5):
                s_ = ((t - r["start"] - r["length"]) / 2.2 + off) % 1.0
                px_, py_ = M.point_on_polyline(xy, s_)
                for gr, ga in ((12, 70), (7, 150)):
                    od.ellipse([px_ - gr * SS, py_ - gr * SS, px_ + gr * SS, py_ + gr * SS], fill=(255, 255, 255, ga))
        if frac >= 0.7:
            mid = M.point_on_polyline(xy, 0.5)
            km = int(round(_km(r["a"], r["b"]) / 10.0) * 10)
            route_marks.append(((r["label"] + " · " if r["label"] and r["label"].upper() != "ILLUSTRATIVE" else "") + f"≈ {km:,} KM STRAIGHT LINE",
                                (mid[0] / SS, mid[1] / SS), True))

    # glyphs
    for gl in g["glyphs"]:
        if t < gl["start"]:
            continue
        cx, cy = P(gl["p"]["lat"], gl["p"]["lon"])
        off = (gl["dx"], gl["dy"]) if (gl["dx"] or gl["dy"]) else ((20, -20) if gl["kind"] == "drone" else (-38, -34) if gl["kind"] == "sticker" else (0, 0))   # beside the marker, not on it
        cx, cy = cx + off[0] * SS, cy + off[1] * SS
        k = M.ease_out(M.ramp(t, gl["start"], 0.35))
        if gl["kind"] == "explosion":
            _star(od, cx, cy, (17 + 3 * math.sin((t - gl["start"]) * 5)) * SS * k, AMBER)
            _star(od, cx, cy, 8 * SS * k, (255, 120, 40, 255), 0.4)
        elif gl["kind"] == "sticker":
            sx, sy = cx, cy
            rr = int(30 * SS * k)
            od.ellipse([sx - rr, sy - rr, sx + rr, sy + rr], fill=HALO[:3] + (int(215 * k),), outline=(200, 206, 216, int(230 * k)), width=SS)
            size = max(8, int(40 * SS * k))
            stk = ST.draw_sticker(gl["name"] or "question", size)
            ov.alpha_composite(stk, (int(sx - size / 2), int(sy - size / 2)))
        elif gl["kind"] == "swarm":
            ang = -0.6 + math.pi                                    # from the east unless a heading is given
            if gl["h"]:
                hx, hy = P(gl["h"]["lat"], gl["h"]["lon"])
                ang = math.atan2(cy - hy, cx - hx)
            for j in range(4):                                      # four arrows fly in toward the place, one after another, and repeat
                u = ((t - gl["start"]) / 2.6 + j * 0.23) % 1.0
                dist = (150 - 130 * M.ease_out(u)) * SS
                spread = (j - 1.5) * 16 * SS
                px_ = cx + math.cos(ang) * dist - math.sin(ang) * spread
                py_ = cy + math.sin(ang) * dist + math.cos(ang) * spread
                a_ = int(255 * k * min(1.0, 4 * (1 - u)) * min(1.0, 5 * u))
                _chevron(od, px_, py_, ang + math.pi, 9 * SS, (236, 214, 200, a_))
        elif gl["kind"] == "drone":
            ang = -0.6
            if gl["h"]:
                hx, hy = P(gl["h"]["lat"], gl["h"]["lon"])
                ang = math.atan2(hy - cy, hx - cx)
            _chevron(od, cx, cy, ang, 14 * SS * k, (214, 218, 224, 255))
        else:
            for off in (0.0, 0.5):
                sc, al = M.pulse(t - gl["start"] + off * T.PULSE_S)
                rr = 12 * sc * SS
                od.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=RED[:3] + (int(210 * al * k),), width=2 * SS)

    # markers: glow, ring, core
    for pl in g["places"]:
        if t < pl["start"]:
            continue
        cx, cy = P(pl["lat"], pl["lon"])
        k = M.ease_out(M.ramp(t, pl["start"], 0.35))
        cy -= (1 - k) * 18 * SS                                   # the marker drops in
        col = pl["colour"]
        if pl["kind"] == "zone":
            rr = 30 * SS
            for seg in MP._dashes([(cx + rr * math.cos(a / 40 * 2 * math.pi), cy + rr * math.sin(a / 40 * 2 * math.pi)) for a in range(41)], 8 * SS, 6 * SS):
                od.line(seg, fill=col[:3] + (int(230 * k),), width=3 * SS)
        else:
            if theme == "tactical":
                for gr, ga in ((26, 26), (19, 44)):                # soft glow under the ring
                    rr = gr * SS
                    od.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col[:3] + (int(ga * k),))
            if pl["kind"] == "ring":
                for off in (0.0, 0.5):
                    sc, al = M.pulse(t - pl["start"] + off * T.PULSE_S)
                    rr = 13 * sc * SS
                    od.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=col[:3] + (int(220 * al * k),), width=2 * SS)
            rr = 13 * SS
            od.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=HALO[:3] + (int(220 * k),), width=5 * SS)
            od.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=col[:3] + (int(240 * k),), width=3 * SS)
        age = t - pl["start"]
        if 0.0 < age < 1.0:                                       # one expanding ripple when the place is named
            kk = M.ease_out(age / 1.0)
            rr = (12 + 44 * kk) * SS
            od.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=col[:3] + (int(190 * (1 - kk)),), width=2 * SS)
        rr = 6 * SS * (0.4 + 0.6 * k)
        od.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col[:3] + (int(255 * k),))
    img = Image.alpha_composite(img, ov.reduce(SS))

    # text layer
    d = ImageDraw.Draw(img)
    fb = T.font("bold", 13)
    badge_text = str(params.get("badge") or BADGE_DEFAULT).upper()
    bw = int(L.spaced_width(d, badge_text, fb, 0.08)) + 22
    badge = (20, 16, 20 + bw, 16 + 28)
    d.rectangle(badge, fill=(10, 12, 16, 240), outline=(170, 176, 186, 255), width=1)
    L.spaced(d, (31, 22), badge_text, fb, (224, 228, 234, 255), 0.08)
    reserved = [badge]
    chips = _chip_defaults(params)
    if any("group" in c for c in chips):                                   # the stack clears: only the latest group that has started
        firsts: Dict[Any, float] = {}
        for c in chips:
            firsts[c.get("group")] = min(firsts.get(c.get("group"), 1e9), float(c["start"]))
        live = [gk for gk, s0 in firsts.items() if s0 <= t]
        cur = max(live, key=lambda gk: firsts[gk]) if live else min(firsts, key=lambda gk: firsts[gk])
        chips = [c for c in chips if c.get("group") == cur]
    if chips:
        first = min(float(c["start"]) for c in chips)
        layout = _chip_stack(img, chips, t, W - 24 - 14, 76, draw=False)
        if any("group" in c for c in chips):                               # building-map cards float on the map (no column behind them)
            reserved.append((min(r[0] for r in layout), 76, W - 24, max((r[3] for r in layout), default=200)))
        else:
            reserved.append(_panel(img, t, first, max((r[3] for r in layout), default=200)))
        reserved += _chip_stack(img, chips, t, W - 24 - 14, 76)
    if extra_panel:
        reserved.append(_number_panel(img, extra_panel, t))
    reserved.append(_scale_bar(img, view))
    loc = FX.locator(img, view, look, theme, [(pl["lat"], pl["lon"]) for pl in g["places"]], 20, 52, M.ease_out(M.ramp(t, 0.5, 0.5)))
    if loc:
        reserved.append(loc)
    if theme == "political":
        n_leg = min(4, len(_fills(params, theme)))
        reserved.append((20, H - 84 - 22 * n_leg, 330, H - 82))           # the fill legend
    for pl in g["places"]:                                                # labels never sit on any marker (placed or not yet dropped)
        mx0, my0 = view.pt(pl["lat"], pl["lon"])
        reserved.append((int(mx0 - 21), int(my0 - 21), int(mx0 + 21), int(my0 + 21)))
    placer = MP.Placer((24, 56, W - 24, H - 24), reserved)
    fl = T.font("display", 27)
    fs = T.font("bold", 13)
    marker_pts: List[Tuple[float, float]] = []
    for pl in g["places"]:
        cx, cy = view.pt(pl["lat"], pl["lon"])
        marker_pts.append((cx, cy))
        if t < pl["start"] + 0.15:
            continue
        if not (10 <= cx <= W - 10 and 10 <= cy <= H - 10):
            continue
        txt = pl["label"].upper()
        tb = d.textbbox((0, 0), txt, font=fl, stroke_width=3)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        r = placer.first_free(MP._side_candidates(cx, cy, tw + 8, th + 8, 25))
        if r is None:
            info["labels"].append((txt, None))
            continue
        placer.take(txt, r)
        k = M.ease_out(M.ramp(t, pl["start"] + 0.15, 0.3))
        lay = Image.new("RGBA", (tw + 20, th + 20), (0, 0, 0, 0))
        _outlined(ImageDraw.Draw(lay), (10 - tb[0], 10 - tb[1]), txt, fl, WHITE)
        img.alpha_composite(L.fade(lay, k), (r[0] - 6, r[1] - 6))
        info["labels"].append((txt, r))
    for label, (rx, ry), rk in region_tags:                               # region name tags, below the subject's own labels in priority
        txt = label.upper()
        rf = T.font("bold", 15)
        rw = int(L.spaced_width(d, txt, rf, 0.12)) + 18
        r = placer.first_free([(rx - rw / 2, ry - 12, rx + rw / 2, ry + 12)])
        if r is None:
            continue
        placer.take(txt, r)
        lay = Image.new("RGBA", (rw, 24), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rectangle([0, 0, rw - 1, 23], fill=(10, 12, 16, 225), outline=(246, 196, 52, 255))
        L.spaced(ld, (9, 4), txt, rf, (246, 238, 214, 255), 0.12)
        img.alpha_composite(L.fade(lay, rk), (int(r[0]), int(r[1])))
    for text, (mx, my), _ill in route_marks:
        txt = (text.upper() + " · " if text and text.upper() != "ILLUSTRATIVE" else "") + "ILLUSTRATIVE"
        w_ = int(L.spaced_width(d, txt, fs, 0.08)) + 18
        r = placer.first_free([(mx - w_ / 2, my - 12, mx + w_ / 2, my + 12), (mx - w_ / 2, my - 38, mx + w_ / 2, my - 14),
                               (mx - w_ / 2, my + 14, mx + w_ / 2, my + 38)])
        if r is None:
            continue
        placer.take(txt, r)
        d.rectangle(r, fill=(10, 12, 16, 240), outline=(170, 176, 186, 255), width=1)
        L.spaced(d, (r[0] + 9, r[1] + 6), txt, fs, (224, 228, 234, 255), 0.08)

    # quiet context: cities, countries, seas, rivers (never over the subject's own labels)
    fc, fcs = T.font("regular", 17), T.font("display", 24)
    k_ctx = M.ease_out(M.ramp(t, 0.2, 0.6))
    ctx = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(ctx)
    anchor_view = views[0]
    for name, (lon, ym) in _country_anchors(anchor_view):
        x, y = view.px(lon, ym)
        x, y = float(x), float(y)
        if not (40 <= x <= W - 40 and 70 <= y <= H - 50):
            continue
        sp = 0.22
        wtxt = int(L.spaced_width(cd, name, fcs, sp))
        r = placer.first_free([(x - wtxt / 2, y - 14, x + wtxt / 2, y + 14)])
        if r is None:
            continue
        placer.take(name, r)
        col = (200, 206, 216, 112) if theme == "tactical" else (255, 255, 255, 140)       # context stays quieter than the subject
        L.spaced(cd, (r[0], r[1]), name, fcs, col, sp)
        info["context_labels"].append(name)
    for sea, (la, lo) in G.SEAS.items():
        r = None
        wtxt = int(L.spaced_width(cd, sea, fc, 0.3))
        for (la2, lo2) in ((la, lo),) + tuple(G.SEA_ALT.get(sea, ())):
            x, y = view.pt(la2, lo2)
            if not (60 <= x <= W - 60 and 80 <= y <= H - 60):
                continue
            if not all(_is_sea(basecrop, x + dx, y, theme, look) for dx in (-wtxt / 2 + 4, 0, wtxt / 2 - 4)):
                continue
            r = placer.first_free([(x - wtxt / 2, y - 11, x + wtxt / 2, y + 11)])
            if r is not None:
                break
        if r is None:
            continue
        placer.take(sea, r)
        L.spaced(cd, (r[0], r[1]), sea, fc, (96, 140, 190, 190) if theme == "tactical" else (150, 186, 236, 200), 0.3)
        info["context_labels"].append(sea)
    named = {pl["label"].lower() for pl in g["places"]} | {pl["name"].lower() for pl in g["places"]}
    cities = sorted(G.context_cities(), key=lambda c: -float(c["w"]))
    shown = 0
    for c in cities:
        if shown >= 12 or str(c["n"]).lower() in named:
            continue
        x, y = view.pt(float(c["lat"]), float(c["lon"]))
        if not (30 <= x <= W - 30 and 70 <= y <= H - 50):
            continue
        if any(math.hypot(x - mx, y - my) < 34 for mx, my in marker_pts):
            continue
        name = str(c["n"])
        tb = cd.textbbox((0, 0), name, font=fc, stroke_width=2)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        r = placer.first_free(MP._side_candidates(x, y, tw + 6, th + 6, 8)[:4])
        if r is None:
            continue
        placer.take(name, r)
        cd.ellipse([x - 3.5, y - 3.5, x + 3.5, y + 3.5], fill=LABEL_CTX, outline=HALO, width=1)
        _outlined(cd, (r[0] + 3 - tb[0], r[1] + 3 - tb[1]), name, fc, LABEL_CTX, 2)
        info["context_labels"].append(name)
        shown += 1
    img = Image.alpha_composite(img, L.fade(ctx, k_ctx * 0.82))
    d = ImageDraw.Draw(img)
    if theme == "political":
        shown_f = [f for f in fills if float(f.get("start") or 0.0) <= t and _fill_in_view(f, vb_now)][:4]    # a key only for what is on screen
        lx, ly = 26, H - 80 - 22 * len(shown_f)
        fl2 = T.font("bold", 14)
        for i, fl in enumerate(shown_f):
            nm = str(fl.get("name") or fl.get("iso3") or "").title()
            feat = G.find_country(str(fl.get("iso3") or fl.get("name") or ""))
            nm = feat.name if feat is not None else nm
            d.rectangle([lx, ly + i * 22, lx + 16, ly + i * 22 + 14], fill=tuple(POL_FILL.get(str(fl.get("role")), NEIGH_P + (255,)))[:3] + (255,), outline=(236, 238, 242, 255))
            d.text((lx + 24, ly + i * 22 - 1), nm.upper(), font=fl2, fill=WHITE, stroke_width=2, stroke_fill=HALO)
    ft_ = T.font("regular", 12)
    src = "Map data: Natural Earth (public domain). Schematic."
    d.text((W - 24 - d.textlength(src, font=ft_), H - 22), src, font=ft_, fill=(150, 156, 166, 255), stroke_width=2, stroke_fill=HALO)
    img = Image.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, 255)), img)     # the card is opaque: boxes drawn with alpha settle on black
    return img, info


def _number_panel(img: Image.Image, spec: dict, t: float) -> Tuple[int, int, int, int]:
    """Black info panel bottom right: kicker, big figure, line (the tac_route distance panel)."""
    d = ImageDraw.Draw(img)
    fk, fn, fl = T.font("bold", 13), T.font("display", 62), T.font("regular", 16)
    w, h = 360, 142
    k = M.ease_out(M.ramp(t, float(spec.get("start", 1.6)), 0.4))
    box = (W - 28 - w, H - 44 - h, W - 28, H - 44)
    if k > 0:
        lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rectangle([0, 0, w, h], fill=(10, 12, 16, 245))
        ld.rectangle([0, 0, 5, h], fill=AMBER)
        L.spaced(ld, (20, 14), str(spec.get("kicker", "")).upper(), fk, AMBER, 0.1)
        ld.text((20, 30), str(spec.get("figure", "")), font=fn, fill=WHITE)
        ld.text((20, 108), str(spec.get("line", "")), font=fl, fill=(190, 194, 200, 255))
        img.alpha_composite(L.fade(lay, k), (box[0] - int((1 - k) * 40), box[1]))
    return box


def tac_map(t: float, dur: float, params: dict) -> Optional[Image.Image]:
    p = params if isinstance(params, dict) else {}
    off, tot = float(p.get("t_offset") or 0.0), float(p.get("total_dur") or 0.0)
    return _render(p, t + off, tot if tot > 0 else dur)[0]


def tac_route(t: float, dur: float, params: dict) -> Optional[Image.Image]:
    p = dict(params if isinstance(params, dict) else {})
    a, _ = resolve_place(p.get("from"))
    b, _ = resolve_place(p.get("to"))
    sub = {"theme": p.get("theme", "tactical"), "places": [p.get("from"), p.get("to")] if a and b else [], "badge": p.get("badge")}
    if a and b:
        km = int(round(_km(a, b) / 10.0) * 10)
        sub["routes"] = [{"from": p["from"], "to": p["to"], "style": p.get("style", "dashed_red"), "label": p.get("label", ""), "start": 0.8,
                          "length": 1.4}]
        panel = {"kicker": "STRAIGHT-LINE DISTANCE", "figure": f"≈ {km:,} km", "line": f"{a['name']} to {b['name']} · not a flight path",
                 "start": 1.6}
    else:
        panel = None
        sub["frame"] = p.get("frame", "ukraine")
    img, _ = _render(sub, t, dur, panel)
    if sub.get("_skipped"):
        p["_skipped"] = sub["_skipped"]
    return img


def render_info(params: dict, t: float, dur: float = 8.0) -> dict:
    """What a frame contains (resolved places, skipped names, label rectangles) for tests and the plan report."""
    p = dict(params)
    off, tot = float(p.get("t_offset") or 0.0), float(p.get("total_dur") or 0.0)
    return _render(p, t + off, tot if tot > 0 else dur)[1]


TACTICAL_CARDS = {"tac_map": tac_map, "tac_route": tac_route}
