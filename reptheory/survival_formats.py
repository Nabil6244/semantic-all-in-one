"""Survival: the extras each video format needs (docs/survival/NICHE_STUDY.md), all driven by the narration, on the word that says them.

- thermal: "to a thermal camera ..." -> the picture on screen turns into a heat-camera view (ink is warm, paper is cold) with a wipe on the word, and stays
  thermal while the narration keeps talking about heat ("glow", "warm", "cold", "heat", "bright").
- state: a place ranking ("That's Hawaii", three or more US states named) -> a small US map; the named state fills on its word, the ones already ranked stay grey.
- timeline: "the first hour", "by day three", "the first night", "72 hours in" (three or more different marks) -> a strip along the bottom that moves to the
  mark being said. Not with a countdown (the progress dots are there).
- persona: "Ray, 81," / "a man named Ray" -> a name tag on the name, once.
- prices: two prices in one or two sentences ("a $120 tactical light ... a $4 headlamp") -> two tags on their words, the dearer one struck through.
plan(scenes, ws, sents, has_countdown) sets sc["sv"] keys; draw(cv, ctx, sc, t) paints them."""
from __future__ import annotations
import gzip, json, math, re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import draw as D, lexicon as LX, theme as T

NUM = LX.NUM[1:-1]
THERMAL_RX = re.compile(r"\b(?:thermal|infrared|heat cameras?|heat signatures?)\b", re.I)
HEAT_RX = re.compile(r"\b(?:thermal|infrared|heat|warm\w*|glow\w*|bright\w*|cold\w*|hot\w*|cool\w*|temperature)\b", re.I)
WIPE_S = 0.8
TIME_RX = re.compile(r"\b(?:(?:in|by|on|after|at|for) (?:the )?)?(?:(first|second|third|fourth|fifth|sixth|seventh|last) (hour|night|day|week)|(hour|day|night|week) (" + NUM + r")|(" + NUM + r") (hours?|days?) (?:in|later|after|into))\b", re.I)
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7}
PERSONA_RX = re.compile(r"\b(?:([A-Z][a-z]{2,}), (?:who is |is |an? )?(" + NUM + r")(?:-year-old| years? old)?\b|(?:named|called) ([A-Z][a-z]{2,})\b)")
NOT_NAMES = {"Number", "That", "This", "There", "Here", "And", "But", "So", "Now", "Then", "Most", "Some", "Every", "Each", "One", "Two", "Three"}
PRICE_RX = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)|\b(" + NUM + r") dollars?\b", re.I)
_STATES: Optional[Dict[str, list]] = None


def _scene_at(scenes: List[dict], t: float) -> Optional[dict]:
    for sc in scenes:
        if sc["start"] - 1e-6 <= t < sc["end"]: return sc
    return scenes[-1] if scenes and t >= scenes[-1]["start"] else None

def _sv(sc: dict) -> dict: return sc.setdefault("sv", {})

def _num(tok: str) -> Optional[float]:
    v = LX.num(str(tok).strip().lower().replace(",", ""))
    try: return float(v)
    except (TypeError, ValueError): return None

def _is_picture(sc: dict) -> bool: return sc.get("kind") == "illus" or sc.get("look") == "flow"


# ---- planning --------------------------------------------------------------------------------------------

def _thermal(scenes, ws, sents, text_map) -> int:
    n = 0
    for a, b in sents:
        txt, idx = text_map(ws, a, b); m = THERMAL_RX.search(txt)
        if not m: continue
        at = float(ws[idx[m.start()]]["t0"]); sc = _scene_at(scenes, at)
        if sc is None or not _is_picture(sc) or "thermal" in _sv(sc): continue
        _sv(sc)["thermal"] = {"at": at}; n += 1
        k = scenes.index(sc) + 1
        while k < len(scenes) and _is_picture(scenes[k]) and HEAT_RX.search(scenes[k].get("text", "")) and "thermal" not in _sv(scenes[k]):      # the talk stays on heat: the view stays thermal
            _sv(scenes[k])["thermal"] = {"at": float(scenes[k]["start"]) - WIPE_S}; k += 1
    return n

def states() -> Dict[str, list]:
    """US state name -> list of polygons [[(lon, lat), ...], ...] (map_scene/data/admin1.json.gz, Natural Earth admin-1)."""
    global _STATES
    if _STATES is None:
        _STATES = {}
        p = Path(__file__).resolve().parent.parent / "map_scene" / "data" / "admin1.json.gz"
        try: feats = json.load(gzip.open(p))["features"]
        except (OSError, ValueError, KeyError): feats = []
        for f in feats:
            if f.get("iso") != "USA": continue
            g = f.get("g") if isinstance(f.get("g"), dict) else json.loads(str(f.get("g")).replace("'", '"'))
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            _STATES[f["n"]] = [[(float(x), float(y)) for x, y in poly[0]] for poly in polys]
    return _STATES

def _states_said(scenes, ws, sents, text_map, run) -> int:
    names = [s for s in states() if s != "District of Columbia"]
    if not names: return 0
    rx = re.compile(r"\b(" + "|".join(sorted((re.escape(s) for s in names), key=len, reverse=True)) + r")\b")
    hits = []
    for a, b in sents:
        txt, idx = text_map(ws, a, b)
        for m in rx.finditer(txt): hits.append((m.group(1), float(ws[idx[m.start()]]["t0"])))
    if len({h[0] for h in hits}) < 3: return 0      # one or two states named is a mention, not a ranking
    ranks = {c["at"]: c["n"] for c in run}
    seen: List[str] = []; n = 0
    for name, at in hits:
        if name in seen: continue
        rank = next((ranks[t] for t in sorted(ranks, reverse=True) if t <= at + 0.01 and at - t < 30.0), None)      # the latest announcement before the name: the one this state answers
        nxt = next((h[1] for h in hits if h[1] > at + 0.5 and h[0] not in seen and h[0] != name), at + 12.0)
        st = {"name": name, "at": at, "to": max(at + 4.0, nxt), "done": list(seen), "rank": rank}
        for x in scenes:
            if x["end"] > at and x["start"] < st["to"]: _sv(x)["state"] = st
        seen.append(name); n += 1
    return n

def _hours(m) -> Optional[tuple]:
    """(hours from the start, label) of one spoken time mark."""
    if m.group(1):
        k = ORD.get(m.group(1).lower()); unit = m.group(2).lower()
        if k is None: return None
        h = {"hour": k, "night": (k - 1) * 24 + 20, "day": (k - 1) * 24 + 12, "week": (k - 1) * 168 + 84}[unit]
        return h, f"{unit.upper()} {k}" if unit != "night" else f"NIGHT {k}"
    if m.group(3):
        k = _num(m.group(4)); unit = m.group(3).lower()
        if not k: return None
        return {"hour": k, "night": (k - 1) * 24 + 20, "day": (k - 1) * 24 + 12, "week": (k - 1) * 168 + 84}[unit], f"{unit.upper()} {int(k)}"
    k = _num(m.group(5)); unit = m.group(6).lower()
    if not k: return None
    return (k if unit.startswith("hour") else k * 24), (f"HOUR {int(k)}" if unit.startswith("hour") else f"DAY {int(k)}")

def _timeline(scenes, ws, sents, text_map) -> int:
    marks = []
    for a, b in sents:
        txt, idx = text_map(ws, a, b)
        for m in TIME_RX.finditer(txt):
            h = _hours(m)
            if h: marks.append({"h": h[0], "label": h[1], "at": float(ws[idx[m.start()]]["t0"])})
    labels = sorted({(mk["h"], mk["label"]) for mk in marks})
    if len(labels) < 3: return 0
    tl = {"marks": [{"h": h, "label": l} for h, l in labels], "said": [{"h": mk["h"], "at": mk["at"]} for mk in marks], "from": marks[0]["at"]}
    for x in scenes:
        if x["end"] > tl["from"]: _sv(x)["timeline"] = tl
    return len(labels)

def _persona(scenes, ws, sents, text_map) -> int:
    seen, n = set(), 0
    for a, b in sents:
        txt, idx = text_map(ws, a, b)
        for m in PERSONA_RX.finditer(txt):
            name = m.group(1) or m.group(3)
            if not name or name in NOT_NAMES or name in seen or name in states(): continue
            age = _num(m.group(2)) if m.group(2) else None
            at = float(ws[idx[m.start()]]["t0"]); sc = _scene_at(scenes, at)
            if sc is None: continue
            _sv(sc)["persona"] = {"name": name.upper(), "age": int(age) if age else None, "at": at}; seen.add(name); n += 1
    return n

def _prices(scenes, ws, sents, text_map) -> int:
    n = 0
    for k in range(len(sents)):
        a = sents[k][0]; b = sents[min(k + 1, len(sents) - 1)][1]
        txt, idx = text_map(ws, a, b); found = []
        for m in PRICE_RX.finditer(txt):
            v = _num(m.group(1) or m.group(2))
            if v is not None and v > 0: found.append((v, float(ws[idx[m.start()]]["t0"])))
        if len(found) < 2 or found[0][1] < float(ws[sents[k][0]]["t0"]) - 1e-6: continue
        (v1, t1), (v2, t2) = found[0], found[1]
        if v1 == v2 or max(v1, v2) < 2 * min(v1, v2): continue      # a real gap ("$120 ... $4"), not two similar prices
        sc = _scene_at(scenes, t1)
        if sc is None or "prices" in _sv(sc) or any("prices" in _sv(x) and abs(_sv(x)["prices"]["tags"][0]["at"] - t1) < 1 for x in scenes): continue
        pr = {"tags": [{"v": v1, "at": t1}, {"v": v2, "at": t2}], "to": t2 + 2.5}
        for x in scenes:
            if x["end"] > t1 and x["start"] < pr["to"]: _sv(x)["prices"] = pr
        n += 1
    return n

def plan(scenes: List[dict], ws: list, sents: list, text_map, run: list) -> Dict[str, int]:
    out = {"thermal": _thermal(scenes, ws, sents, text_map), "states": _states_said(scenes, ws, sents, text_map, run),
           "timeline": 0 if run else _timeline(scenes, ws, sents, text_map), "persona": _persona(scenes, ws, sents, text_map), "prices": _prices(scenes, ws, sents, text_map)}
    return out


# ---- drawing ---------------------------------------------------------------------------------------------

_LUT: Optional[np.ndarray] = None

def _ironbow() -> np.ndarray:
    """A heat-camera palette: cold black-blue -> purple -> red -> orange -> yellow -> white (256 x 3)."""
    global _LUT
    if _LUT is None:
        stops = [(0, (8, 6, 24)), (60, (40, 12, 92)), (110, (130, 20, 120)), (160, (214, 52, 40)), (205, (250, 140, 20)), (235, (252, 220, 70)), (255, (255, 255, 230))]
        x = np.arange(256); _LUT = np.stack([np.interp(x, [s[0] for s in stops], [s[1][c] for s in stops]) for c in range(3)], axis=1).astype(np.uint8)
    return _LUT

def thermal_image(im: Image.Image) -> Image.Image:
    """A drawing seen through a heat camera: ink and colour read as warm, white paper as cold, with a soft heat bloom."""
    a = np.asarray(im.convert("L"), dtype=np.float32); heat = np.clip((248.0 - a) * 1.25, 0, 255)
    h = Image.fromarray(heat.astype(np.uint8), "L"); bloom = h.filter(ImageFilter.GaussianBlur(max(2, im.width // 90)))
    heat = np.maximum(np.asarray(h, dtype=np.float32) * 0.75, np.asarray(bloom, dtype=np.float32) * 1.1).clip(0, 255).astype(np.uint8)
    return Image.fromarray(_ironbow()[heat], "RGB")

def _draw_thermal(cv: Image.Image, ctx: D.Ctx, sc: dict, th: dict, t: float) -> None:
    if t < th["at"] or not sc.get("_shown"): return
    _, rect = sc["_shown"]; x0, y0, x1, y1 = [int(v) for v in rect]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(ctx.W, x1), min(ctx.H, y1)
    if x1 - x0 < 8 or y1 - y0 < 8: return
    region = cv.crop((x0, y0, x1, y1)); hot = thermal_image(region)
    p = min(1.0, (t - th["at"]) / WIPE_S); edge = int((x1 - x0) * T.ease_in_out(p))
    if edge <= 0: return
    mask = Image.new("L", region.size, 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, edge, region.height), radius=ctx.px(18), fill=255)
    cv.paste(hot, (x0, y0), mask)
    d = ImageDraw.Draw(cv, "RGBA")
    if p < 1.0: d.line((x0 + edge, y0, x0 + edge, y1), fill=(255, 255, 255, 220), width=ctx.px(4))      # the wipe line
    f = ctx.font(T.BODY_FONT, 26); a = min(1.0, (t - th["at"]) / 0.4)
    ly = y1 - ctx.px(90)      # bottom left of the picture: the section tag is at the top
    d.rounded_rectangle((x0 + ctx.px(24), ly, x0 + ctx.px(214), ly + ctx.px(46)), radius=ctx.px(8), fill=(10, 8, 24, int(200 * a)))
    d.ellipse((x0 + ctx.px(38), ly + ctx.px(16), x0 + ctx.px(52), ly + ctx.px(30)), fill=(240, 60, 40, int(255 * a * (0.5 + 0.5 * math.sin(t * 6)))))
    D.text_spaced(d, (x0 + ctx.px(64), ly + ctx.px(8)), "THERMAL", f, (255, 255, 255, int(255 * a)), ctx.px(3))

_MAP_CACHE: Dict[tuple, tuple] = {}

def _project(lon: float, lat: float, w: int, h: int) -> tuple:
    """The lower 48 in a simple conic-like projection; Alaska and Hawaii moved into the bottom-left corner, as on most US maps."""
    if lon < -130 and lat > 50:      # Alaska, shrunk into the corner
        lon = -120 + (lon + 150) * 0.35; lat = 26 + (lat - 58) * 0.35
    elif lon < -150 and lat < 25:      # Hawaii
        lon = -107 + (lon + 157) * 0.9; lat = 25.5 + (lat - 20.5) * 0.9
    k = math.cos(math.radians(38)); x = (lon + 125) / 59.0 * k / 0.79; y = (50 - lat) / 26.0
    return (x * w * 0.94 + w * 0.03, y * h * 0.78 + h * 0.18)      # room at the top for the label

def _base_map(w: int, h: int):
    key = (w, h)
    if key not in _MAP_CACHE:
        polys = {name: [[_project(lon, lat, w, h) for lon, lat in ring] for ring in rings if len(ring) > 2] for name, rings in states().items()}
        _MAP_CACHE[key] = polys
    return _MAP_CACHE[key]

def _draw_state_map(cv: Image.Image, ctx: D.Ctx, st: dict, t: float) -> None:
    if not (st["at"] <= t < st["to"]): return
    a = min(1.0, (t - st["at"]) / 0.35, (st["to"] - t) / 0.3); w, h = ctx.px(520), ctx.px(330); x0, y0 = ctx.W - w - ctx.px(50), ctx.H - h - ctx.px(80)
    lay = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=ctx.px(14), fill=T.PLATE + (240,), outline=T.DIM + (255,), width=ctx.px(2))
    fill_p = T.ease_out(min(1.0, (t - st["at"]) / 0.6))
    for name, rings in _base_map(w, h).items():
        col = T.ORANGE if name == st["name"] else (T.GREY if name in st["done"] else T.DIM)
        alpha = int(255 * (fill_p if name == st["name"] else 1.0))
        for ring in rings: d.polygon(ring, fill=col + (alpha,), outline=T.PLATE + (255,))
    f = ctx.font(T.HEAD_FONT, 40); label = (f"#{st['rank']} " if st.get("rank") else "") + st["name"].upper()
    D.text_spaced(d, (ctx.px(22), ctx.px(12)), label, f, T.WHITE + (255,), ctx.px(1))      # top left: Alaska and Hawaii sit in the bottom-left corner
    cv.paste(lay, (x0, y0), lay.split()[3].point(lambda v: int(v * a)))

def _draw_timeline(cv: Image.Image, ctx: D.Ctx, tl: dict, t: float) -> None:
    if t < tl["from"]: return
    marks = tl["marks"]; now = max((s["h"] for s in tl["said"] if s["at"] <= t), default=marks[0]["h"])
    k = max(i for i, m in enumerate(marks) if m["h"] <= now) if any(m["h"] <= now for m in marks) else 0
    d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, (t - tl["from"]) / 0.5); n = len(marks)
    x0, x1, y = ctx.px(160), ctx.W - ctx.px(160), ctx.H - ctx.px(46); step = (x1 - x0) / max(1, n - 1)
    last = next((s["at"] for s in reversed(tl["said"]) if s["at"] <= t), tl["from"]); grow = T.ease_out(min(1.0, (t - last) / 0.6))
    prev_k = max([i for i, m in enumerate(marks) if m["h"] < marks[k]["h"]] or [k]); xe = x0 + step * (prev_k + (k - prev_k) * grow)
    d.line((x0, y, x1, y), fill=T.DIM + (int(255 * a),), width=ctx.px(4)); d.line((x0, y, xe, y), fill=T.ORANGE + (int(255 * a),), width=ctx.px(6))
    f = ctx.font(T.BODY_FONT, 30)
    for i, m in enumerate(marks):
        x = x0 + step * i; on = i <= k; r = ctx.px(9 if i == k else 6)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(T.ORANGE if on else T.DIM) + (int(255 * a),))
        lw = D._text_w(d, m["label"], f, ctx.px(2))
        D.text_spaced(d, (x - lw / 2, y - ctx.px(50)), m["label"], f, (T.WHITE if i == k else T.GREY) + (int(255 * a * (1.0 if i == k else 0.7)),), ctx.px(2))

def _draw_persona(cv: Image.Image, ctx: D.Ctx, p: dict, t: float) -> None:
    ts = t - p["at"]
    if not (0 <= ts < 3.8): return
    a = min(1.0, ts / 0.3, (3.8 - ts) / 0.4); e = T.ease_out(min(1.0, ts / 0.45)); d = ImageDraw.Draw(cv, "RGBA")
    f = ctx.font(T.HEAD_FONT, 54); fs = ctx.font(T.BODY_FONT, 26); x = ctx.px(80) - int((1 - e) * ctx.px(60)); y = ctx.H - ctx.px(250)
    w = max(D._text_w(d, p["name"], f, ctx.px(2)), ctx.px(140)) + ctx.px(60)
    d.rectangle((x, y, x + ctx.px(8), y + ctx.px(110)), fill=T.ORANGE + (int(255 * a),))
    d.rounded_rectangle((x + ctx.px(14), y, x + ctx.px(14) + w, y + ctx.px(110)), radius=ctx.px(6), fill=T.PLATE + (int(235 * a),))
    D.text_spaced(d, (x + ctx.px(38), y + ctx.px(10)), p["name"], f, T.WHITE + (int(255 * a),), ctx.px(2))
    if p.get("age"): D.text_spaced(d, (x + ctx.px(40), y + ctx.px(72)), f"{p['age']} YEARS OLD", fs, T.SOFT_WHITE + (int(255 * a),), ctx.px(3))

def _price_txt(v: float) -> str: return f"${v:,.0f}" if v >= 10 or float(v).is_integer() else f"${v:,.2f}"

def _draw_prices(cv: Image.Image, ctx: D.Ctx, pr: dict, t: float, side: str = "") -> None:
    t0 = pr["tags"][0]["at"]
    if not (t0 <= t < pr["to"]): return
    d = ImageDraw.Draw(cv, "RGBA"); f = ctx.font(T.HEAD_FONT, 64); hi = max(pr["tags"], key=lambda g: g["v"])
    fade = min(1.0, (pr["to"] - t) / 0.3); cx = ctx.W * (0.73 if side == "right" else 0.27 if side == "left" else 0.5); y = int(ctx.H * 0.70)      # on the words side of a picture
    for k, g in enumerate(pr["tags"]):
        ts = t - g["at"]
        if ts < 0: continue
        a = min(1.0, ts / 0.25) * fade; e = T.ease_back(min(1.0, ts / 0.4)); txt = _price_txt(g["v"]); tw = D._text_w(d, txt, f, ctx.px(1))
        x = cx + (-1 if k == 0 else 1) * ctx.px(150) - tw / 2; yy = y + int((1 - e) * ctx.px(30))
        d.rounded_rectangle((x - ctx.px(28), yy - ctx.px(14), x + tw + ctx.px(28), yy + ctx.px(84)), radius=ctx.px(12), fill=T.PLATE + (int(240 * a),), outline=(T.RED if g is hi else T.GREEN) + (int(255 * a),), width=ctx.px(4))
        D.text_spaced(d, (x, yy), txt, f, ((T.GREY if g is hi else T.GREEN) + (int(255 * a),)), ctx.px(1))
        if g is hi and t >= pr["tags"][1]["at"]:      # struck through once the cheaper one is said
            s = min(1.0, (t - pr["tags"][1]["at"]) / 0.3); d.line((x - ctx.px(10), yy + ctx.px(54), x - ctx.px(10) + (tw + ctx.px(20)) * s, yy + ctx.px(22)), fill=T.RED + (int(255 * a),), width=ctx.px(7))

def draw(cv: Image.Image, ctx: D.Ctx, sc: dict, t: float) -> None:
    sv = sc.get("sv") or {}
    if sv.get("thermal"): _draw_thermal(cv, ctx, sc, sv["thermal"], t)
    if sv.get("timeline"): _draw_timeline(cv, ctx, sv["timeline"], t)
    if sv.get("state"): _draw_state_map(cv, ctx, sv["state"], t)
    if sv.get("prices"): _draw_prices(cv, ctx, sv["prices"], t, (sc.get("_layout") or ("",))[0])
    if sv.get("persona"): _draw_persona(cv, ctx, sv["persona"], t)
