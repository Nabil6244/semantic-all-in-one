"""Aviation flight-look graphics (Vistara 611 grammar B15-B18): cockpit displays, a map inset, a speed tape and report pages.
Same contract as the other cards: fn(t, dur, params) -> RGBA 1280x720 or None (nothing to show -> nothing drawn).

  lay_instrument  fob, warnings, label          ECAM / fuel page on dark glass, FOB counting down, warning box blinking amber / red
  lay_pip         image, x, y, caption, year    rounded inset with white border over the flight map, leader line to the pin dot (overlay, transparent)
  lay_speed_tape  speed, target, tag, delta     airspeed tape on the left, boxed value easing to the target, red tag blinking, delta arrow
  lay_report      title, lines, highlight, redact, source, page_image   white page(s) drifting on dark, yellow highlight sweeping, black redactions

Helpers (pure, tested): fob_at, speed_at, tape_ticks, redact_spans, highlight_indexes, blink, wrap_rows.
Every value comes from the narration / CSV; the planner decides which line gets which graphic.
"""

from __future__ import annotations

import math
import os
from typing import Any, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from cinematic_explainer.war import motion as M
from cinematic_explainer.war import tokens as T
from cinematic_explainer import look as L

W, H = T.W, T.H
WHITE = (250, 250, 252, 255)
GREEN = (70, 220, 120, 255)
CYAN = (60, 210, 235, 255)
AMBER = (255, 176, 32, 255)
RED = (240, 60, 56, 255)
MAGENTA = (240, 90, 220, 255)
GLASS = (6, 10, 14, 255)
YELLOW_HL = (255, 226, 60)
GOLD = (242, 184, 64, 255)
DIM = (130, 150, 160, 255)


def _fade_in(t: float) -> float:
    return M.ease_out(M.ramp(t, 0.0, 0.4))


def _label(d: ImageDraw.ImageDraw, x: float, y: float, text: str, size: int = 15, col=GOLD) -> float:
    return L.spaced(d, (x, y), text.upper(), T.font("bold", size), col, 0.16)


# ---------------------------------------------------------------------------------------------------------------- helpers

def blink(t: float, period: float = 0.8) -> bool:
    """True during the first half of every period (a warning lamp)."""
    return (t % period) < period / 2.0


def fob_at(t: float, dur: float, fob: float) -> int:
    """Fuel on board ticking down slightly over the card: about 2 % (at least 4 kg) lost between 0 and dur."""
    fob = float(fob)
    k = M.clamp01(t / max(dur, 0.1))
    drop = max(4.0, fob * 0.02) if fob > 0 else 0.0
    return int(round(fob - drop * k))


def speed_at(t: float, dur: float, speed: float, target: Optional[float] = None) -> float:
    """The airspeed eases from `speed` to `target` over the card (no target -> a faint wobble around it)."""
    if target is None:
        return float(speed) + 0.6 * math.sin(t * 1.7)
    return M.lerp(float(speed), float(target), M.ease_in_out(M.ramp(t, 0.5, max(0.5, dur - 1.0))))


def tape_ticks(speed: float, half: float = 40.0, step: int = 10) -> List[Tuple[int, float]]:
    """(value, offset_kt_from_speed) for every multiple of `step` within +-half of the speed; the tape scrolls as speed changes."""
    lo = int(math.ceil((speed - half) / step)) * step
    out = []
    v = lo
    while v <= speed + half:
        out.append((v, v - speed))
        v += step
    return out


def redact_spans(line: str, words: Sequence[str]) -> List[Tuple[int, int]]:
    """Case-insensitive (start, end) character spans of every word in the line, overlaps merged."""
    low = line.lower()
    spans: List[Tuple[int, int]] = []
    for w in words or []:
        w = str(w or "").strip().lower()
        if not w:
            continue
        i = low.find(w)
        while i >= 0:
            spans.append((i, i + len(w)))
            i = low.find(w, i + len(w))
    spans.sort()
    merged: List[Tuple[int, int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def highlight_indexes(lines: Sequence[str], highlight: Sequence[Any]) -> List[int]:
    """Highlight entries are line indexes (int) or substrings (case-insensitive); returns the sorted line indexes."""
    out = set()
    for h in highlight or []:
        if isinstance(h, bool):
            continue
        if isinstance(h, int):
            if 0 <= h < len(lines):
                out.add(h)
        elif isinstance(h, str) and h.strip():
            for i, ln in enumerate(lines):
                if h.strip().lower() in str(ln).lower():
                    out.add(i)
    return sorted(out)


def wrap_rows(lines: Sequence[str], font, max_w: float, d: ImageDraw.ImageDraw) -> List[Tuple[int, str]]:
    """Word-wrap every line to max_w; returns (source line index, row text)."""
    rows: List[Tuple[int, str]] = []
    for i, ln in enumerate(lines):
        cur = ""
        for word in str(ln).split():
            trial = (cur + " " + word).strip()
            if cur and d.textlength(trial, font=font) > max_w:
                rows.append((i, cur))
                cur = word
            else:
                cur = trial
        rows.append((i, cur))
    return rows


# ---------------------------------------------------------------------------------------------------------------- instrument

def lay_instrument(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    fob = p.get("fob")
    warns = [str(w) for w in (p.get("warnings") or []) if str(w).strip()]
    if fob is None and not warns:
        return None
    img = Image.new("RGBA", (W, H), (4, 6, 8, 255))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 150, 70, 1130, 650
    d.rounded_rectangle([x0 - 14, y0 - 14, x1 + 14, y1 + 14], 26, fill=(26, 28, 32, 255))
    d.rounded_rectangle([x0, y0, x1, y1], 16, fill=GLASS, outline=(44, 56, 62, 255), width=2)
    _label(d, x0 + 30, y0 + 24, str(p.get("label") or "FUEL"), 20, CYAN)
    _label(d, x1 - 200, y0 + 24, "SYS PAGE", 14, DIM)
    d.line([x0 + 30, y0 + 60, x1 - 30, y0 + 60], fill=(40, 70, 78, 255), width=2)
    if fob is not None:
        cur = fob_at(t, dur, float(fob))
        _label(d, x0 + 40, y0 + 100, "FOB", 20, WHITE)
        d.text((x0 + 40, y0 + 130), f"{cur:,}", font=T.font("display", 150), fill=GREEN)
        _label(d, x0 + 40, y0 + 300, "KG", 20, CYAN)
        # wing tanks: two bars that follow the FOB
        frac = M.clamp01(cur / max(float(fob) * 1.05, 1.0))
        for i, nm in enumerate(("L", "R")):
            bx = x0 + 560 + i * 190
            d.rounded_rectangle([bx, y0 + 100, bx + 90, y0 + 320], 8, outline=CYAN, width=3)
            hh = 210 * frac
            d.rectangle([bx + 6, y0 + 314 - hh, bx + 84, y0 + 314], fill=(40, 190, 110, 255))
            d.text((bx + 34, y0 + 330), nm, font=T.font("bold", 26), fill=WHITE)
    if warns:
        on = blink(t, 0.9)
        col = AMBER if on else RED
        n = min(3, len(warns))
        top = y1 - 40 - n * 56 - 20
        k = M.ease_out(M.ramp(t, 0.5, 0.3))
        box = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(box)
        bd.rounded_rectangle([x0 + 30, top, x1 - 30, y1 - 30], 8, outline=col, width=5, fill=(col[0], col[1], col[2], 60 if on else 20))
        for i, w in enumerate(warns[:n]):
            bd.text((x0 + 60, top + 14 + i * 56), w.upper(), font=T.font("bold", 36), fill=col)
        img.alpha_composite(L.fade(box, k))
    sy = int((t * 140) % (y1 - y0)) + y0                      # scan line: the glass is never a still
    scan = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(scan).rectangle([x0, sy, x1, sy + 3], fill=(120, 220, 240, 26))
    img.alpha_composite(scan)
    return L.fade(img, _fade_in(t))


# ---------------------------------------------------------------------------------------------------------------- pip

def _load_image(src: Any) -> Optional[Image.Image]:
    try:
        if isinstance(src, Image.Image):
            return src.convert("RGB")
        if isinstance(src, (str, os.PathLike)) and os.path.isfile(src):
            with Image.open(src) as im:
                return im.convert("RGB")
    except Exception:
        return None
    return None


def _cover(im: Image.Image, w: int, h: int, zoom: float = 1.0) -> Image.Image:
    s = max(w / im.width, h / im.height) * zoom
    r = im.resize((max(w, int(im.width * s + 1)), max(h, int(im.height * s + 1))))
    x, y = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x, y, x + w, y + h))


def lay_pip(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    im = _load_image(p.get("image"))
    if im is None:
        return None
    px, py = float(p.get("x", W * 0.5)), float(p.get("y", H * 0.5))
    iw, ih = 380, 250
    # sit on the side of the pin that has room
    cx = px + 90 + iw / 2 if px < W / 2 else px - 90 - iw / 2
    cy = py - 120 - ih / 2 if py > H / 2 else py + 120 + ih / 2
    cx = min(max(cx, iw / 2 + 20), W - iw / 2 - 20)
    cy = min(max(cy, ih / 2 + 20), H - ih / 2 - 50)
    k = M.ease_out(M.ramp(t, 0.1, 0.5))
    if k <= 0:
        return Image.new("RGBA", (W, H), (0, 0, 0, 0))
    zoom = 1.0 + 0.06 * M.clamp01(t / max(dur, 0.1))            # slow push inside the frame
    photo = _cover(im, iw - 12, ih - 12, zoom)
    card = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle([0, 0, iw - 1, ih - 1], 16, fill=WHITE)
    mask = Image.new("L", photo.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, photo.width - 1, photo.height - 1], 11, fill=255)
    card.paste(photo, (6, 6), mask)
    sw, sh = max(8, int(iw * k)), max(8, int(ih * k))
    card = card.resize((sw, sh))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([cx - sw / 2 + 6, cy - sh / 2 + 10, cx + sw / 2 + 6, cy + sh / 2 + 10], 16, fill=(0, 0, 0, 150))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(out)
    # leader line from the inset's nearest corner to the pin, drawing out as the card scales in
    ex = cx - sw / 2 if px < cx else cx + sw / 2
    ey = cy + sh / 2 if py > cy else cy - sh / 2
    lx, ly = M.lerp(px, ex, k), M.lerp(py, ey, k)
    d.line([px, py, lx, ly], fill=WHITE, width=2)
    pulse = 0.5 + 0.5 * math.sin(t * 5)
    r = 7 + 4 * pulse
    d.ellipse([px - r - 5, py - r - 5, px + r + 5, py + r + 5], outline=(255, 255, 255, int(120 * (1 - pulse * 0.5))), width=2)
    d.ellipse([px - 7, py - 7, px + 7, py + 7], fill=GOLD, outline=WHITE, width=2)
    out.alpha_composite(card, (int(cx - sw / 2), int(cy - sh / 2)))
    cap = str(p.get("caption") or "").strip()
    yr = str(p.get("year") or "").strip()
    kc = M.ease_out(M.ramp(t, 0.5, 0.4))
    if (cap or yr) and kc > 0:
        lab = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lab)
        f = T.font("bold", 18)
        tx = cx - iw / 2
        ty = cy + ih / 2 + 8
        if yr:
            yw = L.spaced_width(ld, yr, T.font("bold", 16), 0.12)
            ld.rounded_rectangle([tx, ty, tx + yw + 20, ty + 28], 6, fill=GOLD)
            L.spaced(ld, (tx + 10, ty + 4), yr, T.font("bold", 16), (20, 20, 24, 255), 0.12)
            tx += yw + 30
        if cap:
            ld.text((tx + 2, ty + 3), cap, font=f, fill=WHITE, stroke_width=2, stroke_fill=(0, 0, 0, 255))
        out.alpha_composite(L.fade(lab, kc))
    return out


# ---------------------------------------------------------------------------------------------------------------- speed tape

def lay_speed_tape(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    if p.get("speed") is None:
        return None
    target = float(p["target"]) if p.get("target") is not None else None
    cur = speed_at(t, dur, float(p["speed"]), target)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    tx0, tx1, cy = 150, 290, H // 2
    d.rounded_rectangle([tx0, 70, tx1, H - 70], 10, fill=(10, 16, 22, 225), outline=(70, 90, 100, 255), width=2)
    ppk = 5.5                                                   # pixels per knot
    tape = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(tape)
    for v, off in tape_ticks(cur, half=(H - 140) / 2 / ppk, step=5):
        y = cy - off * ppk
        major = v % 10 == 0
        td.line([tx1 - (26 if major else 14), y, tx1, y], fill=WHITE, width=2)
        if major:
            td.text((tx0 + 14, y - 13), str(v), font=T.font("bold", 24), fill=WHITE)
    clip = Image.new("L", (W, H), 0)
    ImageDraw.Draw(clip).rectangle([tx0 + 3, 73, tx1 - 3, H - 73], fill=255)
    tape.putalpha(Image.composite(tape.getchannel("A"), Image.new("L", (W, H), 0), clip))
    img.alpha_composite(tape)
    d = ImageDraw.Draw(img)
    if target is not None:
        ty = cy - (target - cur) * ppk
        if 80 < ty < H - 80:
            d.polygon([(tx1 + 2, ty), (tx1 + 24, ty - 11), (tx1 + 24, ty + 11)], fill=MAGENTA)
    # the boxed current value
    d.rounded_rectangle([tx0 - 6, cy - 34, tx1 + 4, cy + 34], 6, fill=(0, 0, 0, 255), outline=GREEN, width=3)
    txt = f"{cur:.0f}"
    tw = d.textlength(txt, font=T.font("display", 54))
    d.text(((tx0 + tx1) / 2 - tw / 2 - 4, cy - 26), txt, font=T.font("display", 54), fill=GREEN)
    _label(d, tx0, 40, "SPD KT", 14, CYAN)
    tag = str(p.get("tag") or "").strip()
    if tag:
        k = M.ease_out(M.ramp(t, 0.6, 0.3))
        if k > 0:
            on = blink(t, 0.7)
            tg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(tg)
            f = T.font("display", 64)
            w_ = gd.textlength(tag.upper(), font=f)
            gd.rounded_rectangle([340, cy - 52, 340 + w_ + 44, cy + 28], 8, fill=RED if on else (110, 20, 22, 255), outline=WHITE, width=3)
            gd.text((362, cy - 52), tag.upper(), font=f, fill=WHITE)
            img.alpha_composite(L.fade(tg, k))
    delta = str(p.get("delta") or "").strip()
    if delta:
        k = M.ease_out(M.ramp(t, 1.0, 0.4))
        if k > 0:
            ar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ad = ImageDraw.Draw(ar)
            ax, ay0, ay1 = 330, cy + 70, cy + 70 + int(150 * k)
            up = target is not None and target > float(p["speed"])
            a_, b_ = (ay1, ay0) if up else (ay0, ay1)
            ad.line([ax, a_, ax, b_], fill=AMBER, width=8)
            ad.polygon([(ax - 18, b_ + (14 if up else -14)), (ax + 18, b_ + (14 if up else -14)), (ax, b_)], fill=AMBER)
            ad.text((ax + 30, cy + 90), delta.upper(), font=T.font("display", 60), fill=AMBER)
            img.alpha_composite(L.fade(ar, k))
    return L.fade(img, _fade_in(t))


# ---------------------------------------------------------------------------------------------------------------- report

def _page(size: Tuple[int, int], title: str, rows: List[Tuple[int, str]], hl: List[int], redact: Sequence[str], t: float,
          first: bool, source: str, seq_offset: int) -> Image.Image:
    pw, ph = size
    pg = Image.new("RGBA", size, (248, 247, 242, 255))
    d = ImageDraw.Draw(pg)
    f = T.font("regular", 22)
    y = 34
    if first and title:
        d.text((34, y), title.upper(), font=T.font("bold", 26), fill=(20, 20, 24, 255))
        y += 44
        d.line([34, y, pw - 34, y], fill=(20, 20, 24, 255), width=2)
        y += 20
    lh = 34
    order = {li: n for n, li in enumerate(hl)}
    over = Image.new("RGBA", size, (0, 0, 0, 0))
    od = ImageDraw.Draw(over)
    for li, row in rows:
        d.text((34, y), row, font=f, fill=(30, 30, 36, 255))
        if li in order:
            n = order[li] + seq_offset
            k = M.ease_in_out(M.ramp(t, 0.5 + n * 0.9, 0.7))
            if k > 0:
                od.rectangle([30, y - 2, 30 + (pw - 60) * k, y + lh - 8], fill=YELLOW_HL + (150,))
        for s, e in redact_spans(row, redact):
            x_a = 34 + d.textlength(row[:s], font=f)
            x_b = 34 + d.textlength(row[:e], font=f)
            od.rectangle([x_a - 3, y - 1, x_b + 3, y + lh - 7], fill=(0, 0, 0, 255))
        y += lh
    pg.alpha_composite(over)
    if source:
        d.text((34, ph - 40), source, font=T.font("regular", 15), fill=(110, 110, 118, 255))
    return pg


def lay_report(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    lines = [str(x) for x in (p.get("lines") or []) if str(x).strip()]
    page_img = _load_image(p.get("page_image"))
    if not lines and page_img is None:
        return None
    img = Image.new("RGBA", (W, H), (14, 16, 20, 255))
    pw, ph = 560, 640
    k_in = M.ease_out(M.ramp(t, 0.0, 0.6))
    drift = M.clamp01(t / max(dur, 0.1))
    pages: List[Image.Image] = []
    if page_img is not None:
        pg = Image.new("RGBA", (pw, ph), (248, 247, 242, 255))
        fit = page_img.copy()
        fit.thumbnail((pw - 20, ph - 20))
        pg.paste(fit, ((pw - fit.width) // 2, (ph - fit.height) // 2))
        band_y = int((ph + 120) * M.ease_in_out((t * 0.35) % 1.0)) - 60            # a sweep band in place of text highlights
        band = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        ImageDraw.Draw(band).rectangle([0, band_y, pw, band_y + 46], fill=YELLOW_HL + (90,))
        pg.alpha_composite(band)
        pages.append(pg)
    else:
        probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        rows = wrap_rows(lines, T.font("regular", 22), pw - 70, probe)
        per_first, per_next = 15, 17
        chunks = [rows[:per_first]]
        rest = rows[per_first:]
        if rest:
            chunks.append(rest[:per_next])
        hl = highlight_indexes(lines, p.get("highlight") or [])
        redact = [str(r) for r in (p.get("redact") or [])]
        src = str(p.get("source") or "")
        seen = 0
        for ci, ch in enumerate(chunks):
            idxs = sorted({li for li, _ in ch})
            here = [h for h in hl if h in idxs]
            pages.append(_page((pw, ph), str(p.get("title") or ""), ch, here, redact, t, ci == 0, src if ci == len(chunks) - 1 else "", seen))
            seen += len(here)
    n = len(pages)
    for i, pg in enumerate(pages):
        ang = (-4 + 8 * i) * (1 if n > 1 else 0.0) + 1.0 * math.sin(t * 0.4 + i)
        scale = (1.0 + 0.05 * drift) * (0.9 + 0.1 * k_in)
        pg2 = pg.resize((int(pw * scale), int(ph * scale)))
        sh = Image.new("RGBA", (pw + 80, ph + 80), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle([30, 36, pw + 40, ph + 46], fill=(0, 0, 0, 170))
        stack = Image.new("RGBA", (pw + 80, ph + 80), (0, 0, 0, 0))
        stack.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
        stack = stack.resize((int((pw + 80) * scale), int((ph + 80) * scale)))
        stack.alpha_composite(pg2, (int(40 * scale), int(40 * scale)))
        rot = stack.rotate(ang, expand=True, resample=Image.BICUBIC)
        cx = W / 2 + (-170 + 340 * i if n > 1 else 0) + 12 * math.sin(t * 0.3) - 14 * drift
        cy = H / 2 - 20 * drift + (6 if i else 0)
        img.alpha_composite(rot, (int(cx - rot.width / 2), int(cy - rot.height / 2)))
    return L.fade(img, _fade_in(t))
