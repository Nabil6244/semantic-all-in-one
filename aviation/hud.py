"""Aviation flight HUD and radio lines (docs/aviation/PLAN.md N6, N7). Transparent overlays over the flight map or aircraft shots.

    lay_hud(t, dur, params)   time (from, to) 'HH:MM' 24h, fuel (from, to) kg, altitude ft, altitude_label ('CLEARED TO' | 'ALTITUDE'),
                              fuel_bar {trip, contingency, discretionary, alternate, final_reserve} kg (any subset).
                              Top-left: small caps label over a big value per reading; values tick from 'from' to 'to' across the
                              layer, fuel turns red once it is below the final reserve. Right: a vertical stacked fuel bar that drains.
    hud_plan(classifications) -> per line {time, fuel, altitude, flight} or None, from aviation.router.route_script: a line between two
                              readings ticks from the earlier one to the later one; nothing is shown before the first reading.
    lay_radio(t, dur, params) lines [{speaker, text}] (max 2 shown): lower-left, a coloured speaker label over the call.
    speaker_of(text)          'ATC' when the call starts with the aircraft's callsign (ATC talking to it), else 'CREW'.
Values come only from the narration (router) or the CSV; nothing is made up.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from cinematic_explainer.war import motion as M
from cinematic_explainer.war import tokens as T
from cinematic_explainer.war.graphics_lib import _wrap_px
from cinematic_explainer import look as L

from . import catalog as C

W, H = T.W, T.H
WHITE = (250, 250, 252, 255)
LABEL = (226, 178, 72, 255)
RED = (238, 66, 66, 255)
SEG_ORDER = (("trip", "TRIP", (246, 196, 60)), ("contingency", "CONTINGENCY", (70, 200, 180)),
              ("discretionary", "DISCRETIONARY", (150, 100, 220)), ("alternate", "ALTERNATE", (232, 82, 122)),
              ("final_reserve", "FINAL RESERVE", (120, 124, 134)))


# ---------------------------------------------------------------------------------------------------------------- values

def _mins(hhmm: str) -> int:
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def _clock(mins: int) -> str:
    mins %= 24 * 60
    h, m = divmod(mins, 60)
    return f"{(h % 12) or 12}:{m:02d} {'PM' if h >= 12 else 'AM'}"


def _k(t: float, dur: float) -> float:
    return M.ease_in_out(M.clamp01(t / max(dur, 0.1)))


def time_at(t: float, dur: float, span: Tuple[str, str]) -> str:
    a, b = _mins(span[0]), _mins(span[1])
    if b < a:
        b += 24 * 60
    return _clock(int(round(a + (b - a) * _k(t, dur))))


def fuel_at(t: float, dur: float, span: Tuple[float, float]) -> int:
    a, b = float(span[0]), float(span[1])
    v = a + (b - a) * _k(t, dur)
    return int(round(v / 10.0) * 10) if abs(b - a) >= 50 else int(round(v))


def is_critical(fuel: float, bar: Optional[dict]) -> bool:
    reserve = float((bar or {}).get("final_reserve") or 0)
    return reserve > 0 and fuel < reserve


# ---------------------------------------------------------------------------------------------------------------- plan

def hud_plan(lines: Sequence[Any]) -> List[Optional[Dict[str, Any]]]:
    """HUD values per routed line (aviation.router.Classification). A line with a reading shows it; a line between two readings
    ticks from the earlier to the later; after the last reading the value holds."""
    n = len(lines)

    def readings(key: str) -> List[Optional[Any]]:
        out: List[Optional[Any]] = []
        for c in lines:
            vals = c.values.get(key) or []
            out.append(vals[-1] if vals else None)
        return out

    times, fuels = readings("times"), readings("fuel_kg")

    def spans(vals: List[Optional[Any]]) -> List[Optional[Tuple[Any, Any]]]:
        res: List[Optional[Tuple[Any, Any]]] = [None] * n
        last = None
        for i in range(n):
            if vals[i] is not None:
                res[i] = (vals[i], vals[i])
                last = vals[i]
            elif last is not None:
                nxt = next((vals[j] for j in range(i + 1, n) if vals[j] is not None), None)
                res[i] = (last, nxt if nxt is not None else last)
        return res

    ts, fs = spans(times), spans(fuels)
    plan: List[Optional[Dict[str, Any]]] = []
    for i, c in enumerate(lines):
        if ts[i] is None and fs[i] is None:
            plan.append(None)
            continue
        st = getattr(c, "state", {}) or {}
        plan.append({"time": ts[i], "fuel": fs[i], "altitude": st.get("altitude_ft"), "flight": st.get("flight")})
    return plan


# ---------------------------------------------------------------------------------------------------------------- HUD

def _reading(d: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str, col=WHITE) -> int:
    L.spaced(d, (x, y), label, T.font("bold", 11), LABEL, 0.14)
    d.text((x, y + 14), value, font=T.font("bold", 30), fill=col)
    return y + 58


def _fuel_bar(d: ImageDraw.ImageDraw, fuel: float, bar: dict, critical: bool) -> None:
    segs = [(key, name, col, float(bar.get(key) or 0)) for key, name, col in SEG_ORDER if float(bar.get(key) or 0) > 0]
    total = sum(s[3] for s in segs)
    if total <= 0:
        return
    x0, x1, top, bottom = W - 96, W - 70, 150, 560
    span = bottom - top
    level = bottom - span * max(0.0, min(1.0, fuel / total))        # fuel left, measured from the bottom
    d.rounded_rectangle([x0 - 3, top - 3, x1 + 3, bottom + 3], 4, outline=(200, 204, 214, 120), width=1)
    y = bottom
    for key, name, col, kg in reversed(segs):                          # final reserve at the bottom, trip on top
        h = span * kg / total
        y0 = y - h
        full_from = max(y0, level)
        if full_from < y:
            d.rectangle([x0, full_from, x1, y], fill=col + (255,))
        if y0 < min(y, level):
            d.rectangle([x0, y0, x1, min(y, level)], fill=col + (55,))
        L.spaced(d, (x0 - 12 - L.spaced_width(d, name, T.font("bold", 9), 0.12), (y0 + y) / 2 - 5), name, T.font("bold", 9), col + (230,), 0.12)
        y = y0
    lab = f"{int(round(fuel)):,} KG"
    fl = T.font("bold", 15)
    d.text((x0 - 12 - d.textlength(lab, font=fl), level - 24), lab, font=fl, fill=RED if critical else WHITE)


def lay_hud(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    tspan, fspan, alt = p.get("time"), p.get("fuel"), p.get("altitude")
    if not tspan and not fspan and not alt:
        return None
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    bar = p.get("fuel_bar") or {}
    x, y = 40, 34
    if tspan:
        y = _reading(d, x, y, "TIME", time_at(t, dur, tuple(tspan)))
    if fspan:
        fuel = fuel_at(t, dur, tuple(fspan))
        y = _reading(d, x, y, "FUEL", f"~{fuel:,} KG", RED if is_critical(fuel, bar) else WHITE)
        if bar:
            _fuel_bar(d, fuel, bar, is_critical(fuel, bar))
    if alt:
        _reading(d, x, y, str(p.get("altitude_label") or "ALTITUDE"), f"{int(alt):,} FT")
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow.putalpha(lay.getchannel("A").point(lambda v: int(v * 0.6)))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3)))
    out.alpha_composite(lay)
    return L.fade(out, M.ease_out(M.ramp(t, 0.0, 0.3)))


# ---------------------------------------------------------------------------------------------------------------- radio

def speaker_of(text: str) -> str:
    first = str(text or "").split(",")[0]
    for m in C.find_airlines(first):
        if re.match(r"\s+(\d{2,4}|\d(?:[\- ]\d){1,3})\b", first[m.end:]):
            return "ATC"                                   # 'Vistara 611, runway 34, cleared to land' - ATC calling the aircraft
    return "CREW"


def lay_radio(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    lines = [ln for ln in ((p or {}).get("lines") or []) if str(ln.get("text") or "").strip()][-2:]
    if not lines:
        return None
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    ft, fs = T.font("regular", 20), T.font("bold", 11)
    blocks = []
    for ln in lines:
        speaker = str(ln.get("speaker") or speaker_of(ln["text"])).upper()
        col = (90, 200, 190, 255) if "ATC" in speaker or "TOWER" in speaker or "CONTROL" in speaker or "RADAR" in speaker else LABEL
        wrapped = _wrap_px(d, str(ln["text"]).strip(), ft, 620)[:2]
        blocks.append((speaker, col, wrapped))
    y = H - 54 - sum(22 + 26 * len(w) + 14 for _, _, w in blocks)
    for i, (speaker, col, wrapped) in enumerate(blocks):
        k = M.ease_out(M.ramp(t, 0.15 + 0.8 * i, 0.35))
        blk = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(blk)
        x = 60
        bd.ellipse([x, y + 3, x + 7, y + 10], outline=col, width=2)
        L.spaced(bd, (x + 14, y), speaker, fs, col, 0.14)
        bd.line([(x + 2, y + 20), (x + 2, y + 20 + 26 * len(wrapped))], fill=col, width=2)
        for j, w in enumerate(wrapped):
            bd.text((x + 14, y + 20 + 26 * j), w, font=ft, fill=WHITE)
        lay.alpha_composite(L.fade(blk, k))
        y += 22 + 26 * len(wrapped) + 14
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh.putalpha(lay.getchannel("A").point(lambda v: int(v * 0.7)))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4)))
    out.alpha_composite(lay)
    return out
