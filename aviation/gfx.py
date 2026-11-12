"""Aviation small graphics (docs/aviation/PLAN.md N8). Same contract as the other cards: fn(t, dur, params) -> RGBA 1280x720 or None.
Overlays are transparent except where they draw; lay_altitude and lay_end_card are full frame.

  lay_counters    items [(number, LABEL)]: typed digits in boxes + caps label, stacking lower-left ('1 3 9  PASSENGERS')
  lay_weather     items [(kind, LABEL, SUB)]: right-hand column of drawn icons (wind, haze, cloud, storm, hail, rain, heat, fog)
  lay_place_title name, pill ('RIGHT NOW'): huge spaced caps place name, a small red pill above it
  lay_sheet       title, rows [[key, value]], highlight [row index], stamp, stamp_at: a paper sheet slides in on the left, rows
                  get a yellow marker one by one, then a red stamp lands
  lay_altitude    from_ft, to_ft, lines [ft], label (aircraft tag), bracket {ft_a, ft_b, label}: side view in a dark sky, dashed
                  altitude lines, the aircraft moving between two altitudes
  lay_end_card    kicker, title: black card, spaced type, the episode number (any word with a digit, else the last word) in red

Helpers that read the narration: counters_from(values), weather_items(text). Nothing is invented: labels are the narration's words.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from cinematic_explainer.war import motion as M
from cinematic_explainer.war import tokens as T
from cinematic_explainer import look as L

W, H = T.W, T.H
WHITE = (250, 250, 252, 255)
GOLD = (226, 178, 72, 255)
RED = (226, 52, 52, 255)


def _shadowed(lay: Image.Image, strength: float = 0.6, blur: float = 3) -> Image.Image:
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh.putalpha(lay.getchannel("A").point(lambda v: int(v * strength)))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    out.alpha_composite(lay)
    return out


# ---------------------------------------------------------------------------------------------------------------- counters

_PEOPLE = {"passengers": "PASSENGERS", "cabin crew": "CABIN CREW", "flight attendants": "FLIGHT ATTENDANTS", "pilots": "PILOTS",
           "crew": "CREW"}
DIGIT_S = 0.12


def counters_from(values: Dict[str, Any]) -> List[Tuple[int, str]]:
    return [(int(n), _PEOPLE[noun]) for n, noun in values.get("counts") or [] if noun in _PEOPLE]


def typed_digits(n: int, t: float, start: float) -> str:
    s = str(int(n))
    return s[:max(0, min(len(s), int((t - start) / DIGIT_S + 1e-9)))]


def lay_counters(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    items = list((p or {}).get("items") or [])[:4]
    if not items:
        return None
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    fd, fl = T.font("bold", 26), T.font("bold", 12)
    y = H - 70 - 44 * (len(items) - 1)
    for i, (n, label) in enumerate(items):
        start = 0.2 + 0.7 * i
        if t < start:
            continue
        shown = typed_digits(n, t, start)
        width = len(str(int(n)))
        x = 60 + (3 - min(width, 3)) * 30                     # right-align the numbers like the reference
        for j, ch in enumerate(str(int(n))):
            bx = x + j * 30
            d.rounded_rectangle([bx, y, bx + 24, y + 32], 3, fill=(0, 0, 0, 120))
            if j < len(shown):
                d.text((bx + 12, y + 16), ch, font=fd, fill=WHITE, anchor="mm")
        k = M.ease_out(M.ramp(t, start + DIGIT_S * width, 0.3))
        if k > 0:
            L.spaced(d, (60 + 3 * 30 + 12, y + 10), str(label).upper(), fl, GOLD[:3] + (int(255 * k),), 0.16)
        y += 44
    return _shadowed(lay)


# ---------------------------------------------------------------------------------------------------------------- weather

_NUM = r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)"
# (priority, kind, regex, label) - higher priority claims its words first ('storm clouds' is a storm, not a cloud)
_WEATHER = (
    (5, "storm", r"\b(thunder ?storms?|storm clouds?|storm cells?|storms?|cumulonimbus)\b", None),
    (5, "hail", r"\b(hail(?:storm)?s?)\b", "HAIL"),
    (4, "wind", r"\bgusts?\s+(?:of\s+|up to\s+)?" + _NUM + r"\s*(?:knots|kts|kt)\b", "GUSTY WINDS"),
    (3, "wind", r"\b((?:light|strong|gusty|variable|calm|high|crosswind)\s+)?winds?\b", None),
    (3, "rain", r"\b((?:heavy|light|monsoon)\s+)?rain(?:s|fall)?\b", None),
    (3, "fog", r"\b(fog|mist)\b", "FOG"),
    (3, "haze", r"\b((?:dust)\s+)?haze\b", None),
    (2, "heat", r"\b(hot|heat|hotter)\b", "HEAT"),
    (1, "cloud", r"\b((?:a\s+)?(?:few|scattered|broken|low|thick)\s+)?clouds?\b", None),
)


def weather_items(text: str) -> List[Tuple[str, str, str]]:
    low = str(text or "").lower()
    taken: List[Tuple[int, int]] = []
    found: List[Tuple[int, str, str, str]] = []
    vis = re.search(r"visibility\s+(?:of\s+)?" + _NUM + r"\s*(km|kilomet\w*|m|metres|meters|miles?)\b", low)
    for _, kind, rx, label in sorted(_WEATHER, key=lambda w: -w[0]):
        for m in re.finditer(rx, low):
            if any(s < m.end() and m.start() < e for s, e in taken):
                continue
            if any(k == kind for _, k, _, _ in found) and kind != "wind":
                continue
            taken.append((m.start(), m.end()))
            sub = ""
            if kind == "wind" and "gust" in m.group(0):
                sub = f"GUSTS {m.group(1)} KT"
            lab = label or re.sub(r"\s+", " ", m.group(0)).strip().upper()
            if kind == "haze" and vis:
                sub = f"VISIBILITY {vis.group(1)} {vis.group(2)[:2].upper().replace('KI', 'KM')}"
            if kind == "storm" and lab in ("STORM", "STORMS"):
                lab = "STORM CLOUDS"
            found.append((m.start(), kind, lab, sub))
    # one wind item: a gust reading wins over a plain 'winds'
    winds = [f for f in found if f[1] == "wind"]
    if len(winds) > 1:
        keep = next((w for w in winds if w[3]), winds[0])
        found = [f for f in found if f[1] != "wind" or f is keep]
    return [(k, lab, sub) for _, k, lab, sub in sorted(found)]


def _icon(d: ImageDraw.ImageDraw, kind: str, x: int, y: int, s: int = 40) -> None:
    w = (240, 240, 244, 255)
    if kind == "wind":
        for i, ln in enumerate((0.9, 0.7, 0.5)):
            yy = y + 8 + i * 11
            d.line([(x, yy), (x + s * ln, yy)], fill=w, width=3)
            d.arc([x + s * ln - 7, yy - 7, x + s * ln + 7, yy + 7], 270, 90, fill=w, width=3)
    elif kind in ("cloud", "storm", "hail", "rain"):
        d.ellipse([x + 4, y + 10, x + 22, y + 26], fill=w)
        d.ellipse([x + 14, y + 4, x + 36, y + 26], fill=w)
        d.rounded_rectangle([x + 2, y + 16, x + 40, y + 28], 6, fill=w)
        if kind == "storm":
            d.polygon([(x + 22, y + 28), (x + 15, y + 39), (x + 21, y + 39), (x + 17, y + 48), (x + 28, y + 35), (x + 22, y + 35)], fill=GOLD)
        elif kind == "hail":
            for cx in (x + 10, x + 21, x + 32):
                d.ellipse([cx - 3, y + 34, cx + 3, y + 40], fill=w)
        elif kind == "rain":
            for cx in (x + 10, x + 21, x + 32):
                d.line([(cx, y + 32), (cx - 4, y + 42)], fill=(160, 200, 255, 255), width=3)
        elif kind == "cloud":
            d.ellipse([x + 26, y - 4, x + 42, y + 12], fill=GOLD)
    elif kind in ("haze", "fog"):
        d.pieslice([x + 8, y + 2, x + 34, y + 28], 180, 360, fill=GOLD)
        for i in range(3):
            d.line([(x + (6 if i % 2 else 0), y + 22 + i * 8), (x + s - (0 if i % 2 else 6), y + 22 + i * 8)], fill=w, width=3)
    elif kind == "heat":
        d.rounded_rectangle([x + 16, y, x + 26, y + 30], 5, outline=w, width=3)
        d.ellipse([x + 12, y + 26, x + 30, y + 44], fill=RED)


def lay_weather(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    items = list((p or {}).get("items") or [])[:5]
    if not items:
        return None
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x, y = int(W * 0.68), int(H * 0.16)
    for i, (kind, label, sub) in enumerate(items):
        k = M.ease_out(M.ramp(t, 0.2 + 0.45 * i, 0.4))
        if k <= 0:
            continue
        it = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(it)
        _icon(d, kind, x, y + 2)
        d.text((x + 58, y + 2), label, font=T.font("bold", 24), fill=WHITE)
        if sub:
            L.spaced(d, (x + 58, y + 32), sub, T.font("bold", 11), GOLD, 0.12)
        lay.alpha_composite(L.fade(it, k))
        y += 72
    return _shadowed(lay)


# ---------------------------------------------------------------------------------------------------------------- place title

def lay_place_title(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    name = str((p or {}).get("name") or "").strip().upper()
    if not name:
        return None
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    f = T.font("display", 96)
    tw = L.spaced_width(d, name, f, 0.16)
    k = M.ease_out(M.ramp(t, 0.1, 0.6))
    y = H * 0.40 + 14 * (1 - k)
    L.spaced(d, ((W - tw) / 2, y), name, f, WHITE, 0.16)
    pill = str(p.get("pill") or "").strip().upper()
    if pill:
        fp = T.font("bold", 12)
        pw = d.textlength(pill, font=fp) + 34
        px0 = (W - pw) / 2
        d.rounded_rectangle([px0, y - 34, px0 + pw, y - 12], 4, fill=(214, 68, 52, 255))
        d.ellipse([px0 + 10, y - 26, px0 + 16, y - 20], fill=WHITE)          # drawn dot: not every font has the glyph
        d.text((px0 + 22, y - 30), pill, font=fp, fill=WHITE)
    return L.fade(_shadowed(lay, 0.7, 6), k)


# ---------------------------------------------------------------------------------------------------------------- briefing sheet

def lay_sheet(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    rows = [r for r in (p.get("rows") or []) if isinstance(r, (list, tuple)) and len(r) >= 2]
    if not rows:
        return None
    pw, ph = 400, min(640, 120 + 40 * len(rows))
    paper = Image.new("RGBA", (pw, ph), (244, 240, 228, 255))
    d = ImageDraw.Draw(paper)
    d.text((24, 22), str(p.get("title") or "BRIEFING SHEET").upper(), font=T.font("bold", 17), fill=(24, 24, 28, 255))
    d.line([(24, 48), (pw - 24, 48)], fill=(40, 40, 44, 255), width=2)
    hl = set(int(i) for i in (p.get("highlight") or []))
    y = 66
    fk, fv = T.font("bold", 14), T.font("regular", 15)
    order = sorted(hl)
    for i, (key, val, *_) in enumerate(rows):
        if i in hl:
            mk = M.draw_fraction(t, 0.9 + 0.35 * order.index(i), 0.35)
            if mk > 0:
                d.rectangle([18, y - 4, 18 + (pw - 36) * mk, y + 22], fill=(250, 210, 90, 255))
        d.text((24, y), str(key).upper(), font=fk, fill=(120, 116, 104, 255))
        d.text((110, y), str(val).upper(), font=fv, fill=(20, 20, 24, 255))
        y += 40
    stamp = str(p.get("stamp") or "").strip().upper()
    sa = float(p.get("stamp_at", 2.0))
    if stamp and t >= sa:
        ks = M.ease_out(M.ramp(t, sa, 0.25))
        fs = T.font("display", 30)
        sw = int(ImageDraw.Draw(paper).textlength(stamp, font=fs)) + 30
        st = Image.new("RGBA", (sw, 50), (0, 0, 0, 0))
        sd = ImageDraw.Draw(st)
        sd.rectangle([2, 2, sw - 3, 47], outline=(206, 40, 40, 230), width=4)
        sd.text((15, 8), stamp, font=fs, fill=(206, 40, 40, 230))
        st = st.rotate(8, expand=True, resample=Image.BICUBIC)
        sc = 1.6 - 0.6 * ks
        st = st.resize((max(1, int(st.width * sc)), max(1, int(st.height * sc))), Image.LANCZOS)
        paper.alpha_composite(L.fade(st, ks), (max(0, (pw - st.width) // 2), max(0, int(ph * 0.45) - st.height // 2)))
    k = M.ease_out(M.ramp(t, 0.0, 0.6))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rot = paper.rotate(-1.5, expand=True, resample=Image.BICUBIC)
    lay.alpha_composite(rot, (max(0, int(40 - 380 * (1 - k))), int((H - rot.height) / 2)))
    return L.fade(_shadowed(lay, 0.7, 12), k)


# ---------------------------------------------------------------------------------------------------------------- altitude side view

def altitude_y(ft: float, lo: float, hi: float) -> float:
    top, bottom = H * 0.14, H * 0.86
    return bottom - (bottom - top) * (float(ft) - lo) / max(1.0, hi - lo)


def _sky() -> Image.Image:
    g = Image.linear_gradient("L").resize((W, H))
    return Image.composite(Image.new("RGB", (W, H), (34, 30, 44)), Image.new("RGB", (W, H), (12, 22, 44)), g).convert("RGBA")


def _side_plane(d: ImageDraw.ImageDraw, x: float, y: float, s: float = 1.0, tail=(120, 40, 90, 255)) -> None:
    body = (236, 236, 240, 255)
    d.rounded_rectangle([x - 70 * s, y - 7 * s, x + 70 * s, y + 7 * s], int(7 * s), fill=body)
    d.polygon([(x + 70 * s, y - 6 * s), (x + 84 * s, y), (x + 70 * s, y + 6 * s)], fill=body)               # nose
    d.polygon([(x - 62 * s, y - 6 * s), (x - 80 * s, y - 34 * s), (x - 68 * s, y - 34 * s), (x - 44 * s, y - 6 * s)], fill=tuple(tail))
    d.polygon([(x - 10 * s, y + 2 * s), (x - 34 * s, y + 14 * s), (x - 20 * s, y + 14 * s), (x + 12 * s, y + 3 * s)], fill=(200, 200, 208, 255))


def lay_altitude(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    if p.get("from_ft") is None and p.get("to_ft") is None:
        return None
    a = float(p.get("from_ft") if p.get("from_ft") is not None else p["to_ft"])
    b = float(p.get("to_ft") if p.get("to_ft") is not None else a)
    lines = [float(v) for v in (p.get("lines") or [a, b])]
    hi = max(lines + [a, b]) * 1.25
    img = _sky()
    d = ImageDraw.Draw(img)
    fl = T.font("bold", 16)
    for ft in lines:
        yy = altitude_y(ft, 0, hi)
        for x in range(30, W - 30, 22):
            d.line([(x, yy), (x + 12, yy)], fill=(232, 82, 82, 170) if ft == min(lines) else (200, 204, 214, 120), width=2)
        d.text((40, yy - 24), f"{int(ft):,} FT", font=fl, fill=(232, 234, 240, 255))
    k = M.ease_in_out(M.ramp(t, 0.4, max(0.5, dur - 1.0)))
    ft_now = a + (b - a) * k
    y = altitude_y(ft_now, 0, hi)
    _side_plane(d, W * 0.52, y)
    tag = str(p.get("label") or "").strip()
    if tag:
        d.text((W * 0.52 - 40, y - 52), tag.upper(), font=T.font("bold", 12), fill=(232, 234, 240, 220))
    br = p.get("bracket") or {}
    if br.get("ft_a") is not None and br.get("ft_b") is not None:
        y1, y2 = altitude_y(br["ft_a"], 0, hi), altitude_y(br["ft_b"], 0, hi)
        bx = W * 0.52 + 120
        d.line([(bx, y1), (bx + 10, y1), (bx + 10, y2), (bx, y2)], fill=(232, 82, 82, 255), width=3)
        d.text((bx + 22, (y1 + y2) / 2 - 16), str(br.get("label") or f"{abs(int(br['ft_a'] - br['ft_b'])):,} FT"), font=T.font("bold", 30), fill=(232, 82, 82, 255))
    return L.fade(img, M.ease_out(M.ramp(t, 0.0, 0.3)))


# ---------------------------------------------------------------------------------------------------------------- end card

def lay_end_card(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    title = str((p or {}).get("title") or "").strip().upper()
    if not title:
        return None
    img = Image.new("RGBA", (W, H), (4, 4, 6, 255))
    d = ImageDraw.Draw(img)
    words = title.split()
    red = {i for i, w in enumerate(words) if re.search(r"\d", w)} or {len(words) - 1}
    f = T.font("display", 64)
    sp = 0.32
    gap = L.spaced_width(d, " ", f, sp) + 18
    widths = [L.spaced_width(d, w, f, sp) for w in words]
    x = (W - (sum(widths) + gap * (len(words) - 1))) / 2
    k = M.ease_out(M.ramp(t, 0.5, 0.9))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    for i, (w, ww) in enumerate(zip(words, widths)):
        L.spaced(ld, (x, H * 0.47), w, f, (214, 34, 34, 255) if i in red else WHITE, sp)
        x += ww + gap
    kicker = str(p.get("kicker") or "").strip().upper()
    if kicker:
        fk = T.font("bold", 14)
        kw = L.spaced_width(ld, kicker, fk, 0.5)
        L.spaced(ld, ((W - kw) / 2, H * 0.40), kicker, fk, (210, 212, 220, 255), 0.5)
    img.alpha_composite(L.fade(lay, k))
    return img
