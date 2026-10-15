"""News Doc's graphics, drawn to match the reference frames (docs/weather/news_doc_ref_every10s_*.jpg), as short transparent clips.

    render(overlay, out_dir) -> path of a .mov (RGBA, 30 fps, the overlay's own length) — None when it cannot be drawn

Looks (1920x1080):
  place      black box, white bold caps name, small grey sub, bottom-left (above a station's lower third); slides in
  ytag       yellow pill, black bold caps, top-left; slides in from the right
  number     a huge white heavy number counting up, small spaced caps label under it (or top-right, smaller, for a measure)
  chapter    one to three words, huge heavy white caps, centred, words appear one by one, the frame dimmed
  quote      white heavy caps on dimmed footage, the point boxed in red, words appear one by one
  quote_card the same on solid black (full screen)
  checklist  a paper card on the right, red header, handwritten items ticked one after the other
  chart      dark navy full screen, title, bars growing with their values (the last one green)
  panel      a dark navy panel on the right 44 % with a thin teal edge, title and bullets
  glitch     RGB blocks and slices, then a white flash with cyan diagonal stripes (covers a part change)
Fonts are the app's bundled ones (assets/fonts)."""

from __future__ import annotations

import math
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
RED = (214, 28, 40, 255)
YELLOW = (255, 213, 0, 255)
NAVY = (14, 22, 36, 255)
TEAL = (38, 196, 206, 255)
CYAN = (0, 205, 235, 255)
GREEN = (40, 220, 120, 255)
WHITE = (255, 255, 255, 255)
GREY = (190, 194, 200, 255)
PAPER = (246, 236, 222, 255)
IN_S, OUT_S = 0.35, 0.3


def _font_dir() -> Path:
    here = Path(__file__).resolve()
    for base in (here.parents[2], Path.cwd()):
        if (base / "assets" / "fonts").is_dir():
            return base / "assets" / "fonts"
    try:
        import sys

        return Path(getattr(sys, "_MEIPASS")) / "assets" / "fonts"
    except Exception:
        return here.parents[2] / "assets" / "fonts"


def font(name: str, size: int):
    files = {"heavy": ["Outfit-ExtraBold.ttf", "Manrope-ExtraBold.ttf", "Inter-Bold.ttf"], "bold": ["Inter-Bold.ttf", "DMSans-Bold.ttf"],
             "semi": ["Inter-SemiBold.ttf", "Inter-Bold.ttf"], "regular": ["Inter-Regular.ttf", "DMSans-Medium.ttf"],
             "hand": ["ChalkboardSE.ttc"]}[name]
    for f in files:
        p = _font_dir() / f
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                continue
    return ImageFont.load_default()


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _alpha(t: float, d: float, a_in: float = IN_S, a_out: float = OUT_S) -> float:
    return min(_ease(t / a_in) if a_in > 0 else 1.0, _ease((d - t) / a_out) if a_out > 0 else 1.0)


def _fade(img: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return img
    r, g, b, al = img.split()
    al = al.point(lambda v: int(v * max(0.0, a)))
    return Image.merge("RGBA", (r, g, b, al))


def _blank(color=(0, 0, 0, 0)) -> Image.Image:
    return Image.new("RGBA", (W, H), color)


def _text_w(d: ImageDraw.ImageDraw, text: str, f) -> int:
    return int(d.textlength(text, font=f))


def _spaced(d, xy, text, f, fill, spacing: float = 0.08):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) * (1 + spacing)
    return x


def _spaced_w(d, text, f, spacing: float = 0.08) -> float:
    return sum(d.textlength(ch, font=f) * (1 + spacing) for ch in text)


def _wrap(d, words: List[str], f, width: int) -> List[List[str]]:
    lines, cur = [], []
    for w in words:
        if cur and _text_w(d, " ".join(cur + [w]), f) > width:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def _shadow(img: Image.Image, radius: int = 10, strength: int = 150) -> Image.Image:
    a = img.split()[3].filter(ImageFilter.GaussianBlur(radius))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh.putalpha(a.point(lambda v: min(255, int(v * strength / 255))))
    return Image.alpha_composite(sh, img)


# ---- each look ------------------------------------------------------------------------------------------------------------

def place(t: float, d: float, p: dict) -> Image.Image:
    img = _blank()
    dr = ImageDraw.Draw(img)
    fn, fs = font("bold", 42), font("regular", 26)
    name, sub = p.get("name", ""), p.get("sub", "")
    w = int(max(_spaced_w(dr, name, fn, 0.04), _text_w(dr, sub, fs)) + 48)
    h = 112 if sub else 76
    x = 64 + int(-40 * (1 - _ease(t / IN_S)))
    y = int(H * 0.70) - h
    dr.rectangle([x, y, x + w, y + h], fill=(8, 8, 10, 235))
    _spaced(dr, (x + 24, y + 16), name, fn, WHITE, 0.04)
    if sub:
        dr.text((x + 24, y + 70), sub, font=fs, fill=GREY)
    return _fade(img, _alpha(t, d))


def ytag(t: float, d: float, p: dict) -> Image.Image:
    img = _blank()
    dr = ImageDraw.Draw(img)
    f = font("bold", 30)
    text = p.get("text", "")
    w = int(_spaced_w(dr, text, f, 0.05) + 40)
    x = 64 + int(160 * (1 - _ease(t / IN_S)))
    y = 64
    dr.rounded_rectangle([x, y, x + w, y + 54], radius=6, fill=YELLOW)
    _spaced(dr, (x + 20, y + 10), text, f, (0, 0, 0, 255), 0.05)
    return _fade(img, _alpha(t, d))


def number(t: float, d: float, p: dict) -> Image.Image:
    img = _blank()
    dr = ImageDraw.Draw(img)
    shown, label, value = str(p.get("shown", "")), str(p.get("label", "")), p.get("value")
    k = _ease(t / 0.9)
    if isinstance(value, (int, float)) and shown.replace(",", "").replace(".", "").replace("%", "").isdigit() and value > 1:
        decimals = len(shown.split(".")[1].rstrip("%")) if "." in shown else 0
        v = value * k
        shown_now = (f"{v:,.{decimals}f}" if decimals else f"{int(round(v)):,}") + ("%" if shown.endswith("%") else "")
    else:
        shown_now = shown
    corner = bool(p.get("corner"))
    fn = font("heavy", 120 if corner else 200)
    fl = font("bold", 30 if corner else 38)
    tw = _text_w(dr, shown_now, fn)
    lw = _spaced_w(dr, label, fl, 0.18)
    if corner:
        x, y = W - 90 - max(tw, lw), 70
    else:
        x, y = (W - tw) // 2, int(H * 0.36)
    layer = _blank()
    ld = ImageDraw.Draw(layer)
    ld.text((x, y), shown_now, font=fn, fill=WHITE)
    if label:
        lx = x + (tw - lw) / 2 if not corner else x + max(tw, lw) - lw
        _spaced(ld, (lx, y + (140 if corner else 228)), label, fl, WHITE, 0.18)
    img = _shadow(layer, 14, 170)
    return _fade(img, _alpha(t, d, 0.25))


def chapter(t: float, d: float, p: dict) -> Image.Image:
    img = _blank((0, 0, 0, int(95 * _alpha(t, d, 0.3))))
    words = str(p.get("text", "")).upper().split()
    dr = ImageDraw.Draw(img)
    size = 132
    f = font("heavy", size)
    while size > 56 and _spaced_w(dr, " ".join(words), f, 0.04) > W - 220:   # always fits on screen
        size -= 6
        f = font("heavy", size)
    total = _spaced_w(dr, " ".join(words), f, 0.04)
    x = (W - total) / 2
    layer = _blank()
    ld = ImageDraw.Draw(layer)
    shown = max(1, min(len(words), int(t / 0.28) + 1))
    for i, w in enumerate(words):
        if i < shown:
            _spaced(ld, (x, H / 2 - 90), w, f, WHITE, 0.04)
        x += _spaced_w(ld, w + " ", f, 0.04)
    img = Image.alpha_composite(img, _shadow(layer, 12, 140))
    return _fade(img, _alpha(t, d, 0.2, 0.3))


def _quote(t: float, d: float, p: dict, solid: bool) -> Image.Image:
    base = (0, 0, 0, 255) if solid else (0, 0, 0, 150)
    img = _blank(base)
    dr = ImageDraw.Draw(img)
    f = font("heavy", 92)
    words = str(p.get("text", "")).upper().split()
    red = str(p.get("red", "")).upper().split()
    red_from = len(words) - len(red) if red and [w.strip(".,!?") for w in words[-len(red):]] == [w.strip(".,!?") for w in red] else len(words)
    lines = _wrap(dr, words, f, 1330)
    lh = 124
    y = (H - lh * len(lines)) // 2
    shown = int(len(words) * min(1.0, t / max(0.8, min(1.8, d * 0.4)))) + 1
    k = 0
    for ln in lines:
        x = 300
        for w in ln:
            ww = _text_w(dr, w, f)
            if k < shown:
                if k >= red_from:
                    dr.rectangle([x - 10, y - 4, x + ww + 10, y + 110], fill=RED)
                dr.text((x, y), w, font=f, fill=WHITE)
            x += ww + _text_w(dr, " ", f)
            k += 1
        y += lh
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def quote(t, d, p):
    return _quote(t, d, p, False)


def quote_card(t, d, p):
    return _quote(t, d, p, True)


def checklist(t: float, d: float, p: dict) -> Image.Image:
    img = _blank()
    items = [str(i) for i in p.get("items", [])][:6]
    fh, fi = font("bold", 34), font("hand", 46)
    x0, y0, w = 1080, 120, 760
    h = 110 + 76 * len(items) + 30
    card = Image.new("RGBA", (w + 30, h + 30), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rectangle([18, 18, w + 18, h + 18], fill=(0, 0, 0, 90))
    card = card.filter(ImageFilter.GaussianBlur(8))
    cd = ImageDraw.Draw(card)
    cd.rectangle([0, 0, w, h], fill=PAPER, outline=(150, 30, 30, 255), width=3)
    cd.rectangle([0, 0, w, 74], fill=(170, 26, 32, 255))
    cd.text((26, 18), str(p.get("title", "")).upper()[:34], font=fh, fill=WHITE)
    step = max(0.35, (d - 1.2) / max(1, len(items)))
    for i, it in enumerate(items):
        yy = 106 + 76 * i
        cd.rectangle([26, yy + 8, 60, yy + 42], outline=(170, 26, 32, 255), width=3)
        if t >= 0.5 + i * step:
            cd.line([(31, yy + 25), (41, yy + 37), (58, yy + 6)], fill=(170, 26, 32, 255), width=6)
        cd.text((82, yy), it[:26], font=fi, fill=(40, 34, 30, 255))
    off = int(80 * (1 - _ease(t / IN_S)))
    img.alpha_composite(card, (x0 + off, y0))
    return _fade(img, _alpha(t, d))


def chart(t: float, d: float, p: dict) -> Image.Image:
    img = _blank(NAVY)
    dr = ImageDraw.Draw(img)
    ft, fv, fl = font("bold", 46), font("bold", 34), font("semi", 24)
    title = str(p.get("title", "")).upper()
    _spaced(dr, ((W - _spaced_w(dr, title, ft, 0.04)) / 2, 90), title, ft, WHITE, 0.04)
    vals = [float(v) for v in p.get("values", [])]
    shown = [str(s) for s in p.get("shown", [])]
    labels = [str(s) for s in p.get("labels", [])]
    unit = str(p.get("unit", ""))
    if vals:
        top = max(vals) or 1.0
        n = len(vals)
        bw = min(220, int(1100 / n))
        gap = int((1300 - n * bw) / max(1, n - 1)) if n > 1 else 0
        x = (W - (n * bw + (n - 1) * gap)) // 2
        base = 900
        dr.line([(x - 40, base), (x + n * bw + (n - 1) * gap + 40, base)], fill=(70, 84, 104, 255), width=2)
        for i, v in enumerate(vals):
            k = _ease((t - 0.3 - 0.15 * i) / 0.9)
            hgt = int(560 * (v / top) * k)
            col = GREEN if i == n - 1 else CYAN
            dr.rectangle([x, base - hgt, x + bw, base], fill=col)
            if k > 0.6:
                s = (shown[i] if i < len(shown) else f"{v:g}") + (f" {unit}" if unit and unit not in ("%",) else "")
                dr.text((x + (bw - _text_w(dr, s, fv)) / 2, base - hgt - 52), s, font=fv, fill=WHITE)
            lab = labels[i] if i < len(labels) else ""
            dr.text((x + (bw - _text_w(dr, lab, fl)) / 2, base + 18), lab, font=fl, fill=GREY)
            x += bw + gap
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def panel(t: float, d: float, p: dict) -> Image.Image:
    img = _blank()
    px = int(W * 0.56) + int(300 * (1 - _ease(t / 0.4)))
    dr = ImageDraw.Draw(img)
    dr.rectangle([px, 0, W, H], fill=(12, 20, 32, 240))
    dr.rectangle([px, 0, px + 4, H], fill=TEAL)
    ft, fb = font("bold", 40), font("regular", 30)
    y = 380
    for ln in _wrap(dr, str(p.get("title", "")).upper().split(), ft, W - px - 140):
        dr.text((px + 70, y), " ".join(ln), font=ft, fill=WHITE)
        y += 54
    y += 30
    bullets = [str(b) for b in p.get("bullets", [])][:3]
    for i, b in enumerate(bullets):
        if t < 0.5 + 0.6 * i:
            break
        lines = _wrap(dr, b.split(), fb, W - px - 170)
        dr.ellipse([px + 72, y + 14, px + 84, y + 26], fill=TEAL)
        for ln in lines[:3]:
            dr.text((px + 104, y), " ".join(ln), font=fb, fill=(220, 226, 232, 255))
            y += 40
        y += 22
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def glitch(t: float, d: float, p: dict) -> Image.Image:
    rnd = random.Random(int(t * 1000) + int(p.get("seed", 0)))
    if t < 0.14:   # RGB blocks and slices over the outgoing picture
        img = _blank()
        dr = ImageDraw.Draw(img)
        for _ in range(18):
            y = rnd.randint(0, H - 40)
            hh = rnd.randint(8, 60)
            x = rnd.randint(-200, W - 200)
            ww = rnd.randint(200, 900)
            col = rnd.choice([(255, 0, 80, 150), (0, 255, 200, 150), (80, 120, 255, 160), (255, 255, 255, 120), (255, 230, 0, 140)])
            dr.rectangle([x, y, x + ww, y + hh], fill=col)
        return img
    k = (t - 0.14) / max(0.01, d - 0.14)
    img = _blank((255, 255, 255, 255))
    dr = ImageDraw.Draw(img)
    for i in range(-H, W, 70):
        dr.line([(i, H), (i + H, 0)], fill=(150, 235, 245, 255), width=22)
    return _fade(img, 1.0 - _ease(max(0.0, (k - 0.45) / 0.55)))


def ring(t: float, d: float, p: dict) -> Image.Image:
    """Cyan ring filling to the percent, the number inside, a white label chip under it (reference 3:40, '90%')."""
    img = _blank((0, 0, 0, int(70 * _alpha(t, d, 0.3))))
    dr = ImageDraw.Draw(img)
    v = max(0.0, min(100.0, float(p.get("value", 0))))
    k = _ease((t - 0.2) / 1.2)
    cx, cy, r = W // 2, int(H * 0.44), 150
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 70), width=26)
    if k > 0:
        dr.arc([cx - r, cy - r, cx + r, cy + r], start=-90, end=-90 + 360 * v / 100 * k, fill=CYAN, width=26)
    f = font("heavy", 96)
    txt = f"{int(round(v * k))}%"
    dr.text((cx - _text_w(dr, txt, f) / 2, cy - 62), txt, font=f, fill=WHITE)
    lab = str(p.get("label", "")).upper()
    if lab:
        fl = font("bold", 30)
        w = _spaced_w(dr, lab, fl, 0.08) + 48
        dr.rectangle([cx - w / 2, cy + r + 50, cx + w / 2, cy + r + 106], fill=(255, 255, 255, 235))
        _spaced(dr, (cx - w / 2 + 24, cy + r + 61), lab, fl, (20, 20, 24, 255), 0.08)
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def line(t: float, d: float, p: dict) -> Image.Image:
    """Dark navy full screen, a white line drawing in through its labelled points, the last point red (reference 0:30, 3:10)."""
    img = _blank(NAVY)
    dr = ImageDraw.Draw(img)
    ft, fv, fl = font("bold", 44), font("bold", 30), font("semi", 22)
    title = str(p.get("title", "")).upper()
    _spaced(dr, ((W - _spaced_w(dr, title, ft, 0.04)) / 2, 80), title, ft, WHITE, 0.04)
    vals = [float(v) for v in p.get("values", [])]
    if len(vals) >= 2:
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        x0, x1, y0, y1 = 260, W - 260, 820, 260
        pts = [(x0 + (x1 - x0) * i / (len(vals) - 1), y0 - (y0 - y1) * (v - lo) / span) for i, v in enumerate(vals)]
        dr.line([(x0 - 30, y0 + 40), (x1 + 30, y0 + 40)], fill=(70, 84, 104, 255), width=2)
        k = _ease((t - 0.3) / 1.8) * (len(pts) - 1)
        for i in range(len(pts) - 1):
            if k <= i:
                break
            f = min(1.0, k - i)
            a, b = pts[i], pts[i + 1]
            dr.line([a, (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)], fill=WHITE, width=5)
        shown = [str(x) for x in p.get("shown", [])]
        labels = [str(x) for x in p.get("labels", [])]
        for i, (x, y) in enumerate(pts):
            if k + 1e-6 < i:
                break
            col = RED if i == len(pts) - 1 else (255, 214, 64, 255)
            dr.ellipse([x - 11, y - 11, x + 11, y + 11], fill=col)
            s = shown[i] if i < len(shown) else f"{vals[i]:g}"
            dr.text((x - _text_w(dr, s, fv) / 2, y - 56), s, font=fv, fill=WHITE)
            lab = labels[i] if i < len(labels) else ""
            dr.text((x - _text_w(dr, lab, fl) / 2, y0 + 56), lab, font=fl, fill=GREY)
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def year(t: float, d: float, p: dict) -> Image.Image:
    """A huge white year wiping in digit by digit over a dimmed shot (reference 7:55 '2019', 13:00 '2025')."""
    img = _blank((0, 0, 0, int(80 * _alpha(t, d, 0.3))))
    text = str(p.get("text", ""))
    f = font("heavy", 230)
    dr = ImageDraw.Draw(img)
    n = min(len(text), int(t / 0.12) + 1)
    layer = _blank()
    ImageDraw.Draw(layer).text(((W - _text_w(dr, text, f)) / 2, H / 2 - 150), text[:n], font=f, fill=WHITE)
    img = Image.alpha_composite(img, _shadow(layer, 16, 180))
    return _fade(img, _alpha(t, d, 0.15, 0.3))


def pullquote(t: float, d: float, p: dict) -> Image.Image:
    """A serif italic quote beside the person, its attribution in small caps (reference 9:10)."""
    img = _blank((0, 0, 0, int(120 * _alpha(t, d, 0.3))))
    dr = ImageDraw.Draw(img)
    try:
        fq = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia Italic.ttf", 54)
    except OSError:
        fq = font("semi", 50)
    lines = _wrap(dr, ("“" + str(p.get("text", "")).strip() + "”").split(), fq, 1100)
    y = H / 2 - 40 * len(lines)
    for ln in lines[:5]:
        dr.text((180, y), " ".join(ln), font=fq, fill=WHITE)
        y += 76
    who = str(p.get("who", "")).upper()
    if who:
        _spaced(dr, (184, y + 20), "— " + who, font("bold", 26), (225, 225, 225, 255), 0.12)
    return _fade(img, _alpha(t, d, 0.35, 0.3))


def nametag(t: float, d: float, p: dict) -> Image.Image:
    """An orange bar with a condensed white name and the role under it, bottom-left (reference 10:05 'JULIE LAUGHTON')."""
    img = _blank()
    dr = ImageDraw.Draw(img)
    fn, fr = font("heavy", 58), font("semi", 24)
    x = 90 + int(-60 * (1 - _ease(t / IN_S)))
    y = int(H * 0.68)
    dr.rectangle([x, y, x + 10, y + 96], fill=(255, 122, 26, 255))
    dr.text((x + 26, y - 4), str(p.get("name", "")), font=fn, fill=WHITE)
    if p.get("role"):
        dr.text((x + 28, y + 66), str(p["role"]), font=fr, fill=(230, 230, 230, 255))
    return _fade(_shadow(img, 8, 160), _alpha(t, d))


def rings(t: float, d: float, p: dict) -> Image.Image:
    """Three outlined circles on black, each with a word, popping in one by one (reference 14:35)."""
    img = _blank((0, 0, 0, 255))
    dr = ImageDraw.Draw(img)
    items = [str(i) for i in p.get("items", [])][:3]
    f = font("bold", 28)
    r = 120
    for i, it in enumerate(items):
        k = _ease((t - 0.25 - 0.35 * i) / 0.35)
        if k <= 0:
            continue
        cx = W / 2 + (i - (len(items) - 1) / 2) * 420
        rr = r * (0.6 + 0.4 * k)
        dr.ellipse([cx - rr, H / 2 - rr, cx + rr, H / 2 + rr], outline=(255, 255, 255, int(255 * k)), width=5)
        dr.text((cx - _text_w(dr, it, f) / 2, H / 2 - 18), it, font=f, fill=(255, 255, 255, int(255 * k)))
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def caption(t: float, d: float, p: dict) -> Image.Image:
    """Small white caps, bottom-left over the shot, typed in (reference 6:50 'THE PRIVATIZATION OF COASTAL DEFENSE')."""
    img = _blank()
    dr = ImageDraw.Draw(img)
    for y in range(H - 260, H):   # a soft dark floor so the words read on any shot
        dr.line([(0, y), (W, y)], fill=(0, 0, 0, int(140 * (y - (H - 260)) / 260)))
    text = str(p.get("text", "")).upper()
    n = max(1, min(len(text), int(t / 0.03)))
    _spaced(dr, (80, H - 150), text[:n], font("bold", 34), WHITE, 0.06)
    return _fade(img, _alpha(t, d, 0.2, 0.3))


def dossier(t: float, d: float, p: dict) -> Image.Image:
    """A case file on paper: the event's name circled in red, its facts typed below (reference 0:35 'STORM RACHEL')."""
    img = _blank((232, 230, 224, 255))
    dr = ImageDraw.Draw(img)
    for i in range(0, W, 3):   # paper grain
        dr.line([(i, 0), (i, H)], fill=(222, 220, 214, 255) if i % 6 == 0 else (236, 234, 228, 255))
    zoom = 1.0 + 0.04 * min(1.0, t / max(0.1, d))
    title = str(p.get("title", ""))
    size = 120
    f = font("heavy", size)
    while _text_w(dr, title, f) > W - 400 and size > 60:
        size -= 6
        f = font("heavy", size)
    tw = _text_w(dr, title, f)
    x, y = (W - tw) / 2, 200
    dr.text((x, y), title, font=f, fill=(20, 20, 20, 255))
    k = _ease((t - 0.4) / 0.8)
    if k > 0:
        dr.arc([x - 60, y - 40, x + tw + 60, y + size + 50], start=200, end=200 + 360 * k, fill=(200, 20, 30, 255), width=10)
    ff = font("semi", 34)
    for i, (key, val) in enumerate(p.get("fields", [])):
        if t < 0.9 + 0.3 * i:
            break
        yy = 520 + i * 70
        dr.text((520, yy), f"{key}:", font=ff, fill=(90, 90, 90, 255))
        dr.text((800, yy), str(val).upper(), font=ff, fill=(20, 20, 20, 255))
    if zoom > 1.0:
        img = img.resize((int(W * zoom), int(H * zoom)), Image.BICUBIC).crop((int(W * (zoom - 1) / 2), int(H * (zoom - 1) / 2),
                                                                          int(W * (zoom - 1) / 2) + W, int(H * (zoom - 1) / 2) + H))
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def headline(t: float, d: float, p: dict) -> Image.Image:
    """A news headline over the shot, left-centre: white bold caps and a grey line under it (reference 1:30, 3:50)."""
    img = _blank()
    dr = ImageDraw.Draw(img)
    for x in range(0, 1100):   # a dark wash from the left so the words read
        dr.line([(x, 0), (x, H)], fill=(0, 0, 0, int(150 * (1 - x / 1100))))
    ft, fs = font("bold", 46), font("regular", 28)
    y = int(H * 0.38)
    off = int(-50 * (1 - _ease(t / 0.4)))
    for ln in _wrap(dr, str(p.get("title", "")).split(), ft, 760)[:3]:
        dr.text((160 + off, y), " ".join(ln), font=ft, fill=WHITE)
        y += 58
    if p.get("sub") and t > 0.4:
        dr.text((162 + off, y + 12), str(p["sub"]), font=fs, fill=(205, 210, 215, 255))
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def hbars(t: float, d: float, p: dict) -> Image.Image:
    """Dark navy, horizontal bars growing from the left, labels on the left, values at the ends (reference 9:20)."""
    img = _blank(NAVY)
    dr = ImageDraw.Draw(img)
    ft, fl, fv = font("bold", 44), font("semi", 26), font("bold", 28)
    title = str(p.get("title", "")).upper()
    _spaced(dr, ((W - _spaced_w(dr, title, ft, 0.04)) / 2, 110), title, ft, WHITE, 0.04)
    vals = [float(v) for v in p.get("values", [])]
    shown = [str(x) for x in p.get("shown", [])]
    labels = [str(x) for x in p.get("labels", [])]
    top = max(vals) if vals else 1.0
    cols = [(64, 150, 255, 255), (112, 120, 230, 255), (40, 220, 160, 255), CYAN, (255, 196, 64, 255)]
    for i, v in enumerate(vals):
        y = 300 + i * 130
        k = _ease((t - 0.3 - 0.2 * i) / 0.9)
        dr.text((200, y + 8), labels[i] if i < len(labels) else "", font=fl, fill=GREY)
        w = int(1100 * (v / (top or 1.0)) * k)
        dr.rectangle([520, y, 520 + w, y + 44], fill=cols[i % len(cols)])
        if k > 0.6:
            s_ = (shown[i] if i < len(shown) else f"{v:g}") + (f" {p.get('unit')}" if p.get("unit") not in (None, "", "%") else "")
            dr.text((540 + w, y + 6), s_, font=fv, fill=WHITE)
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def _still(path: str, size) -> Optional[Image.Image]:
    try:
        im = Image.open(path).convert("RGB")
    except Exception:
        return None
    w, h = size
    r = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.BICUBIC)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def framed(t: float, d: float, p: dict) -> Image.Image:
    """A still of the story's own footage in a thin frame on dark navy, its caption under it, slowly pushing in (reference 7:30)."""
    img = _blank(NAVY)
    dr = ImageDraw.Draw(img)
    stills = p.get("stills") or []
    z = 1.0 + 0.05 * min(1.0, t / max(0.1, d))
    w, h = int(980 * z), int(560 * z)
    pic = _still(stills[0], (w, h)) if stills else None
    x, y = (W - w) // 2, (H - h) // 2 - 40
    dr.rectangle([x - 8, y - 8, x + w + 8, y + h + 8], fill=(230, 232, 236, 255))
    if pic is not None:
        img.paste(pic, (x, y))
    cap = str(p.get("caption", "")).upper()
    f = font("semi", 26)
    _spaced(dr, ((W - _spaced_w(dr, cap, f, 0.12)) / 2, y + h + 40), cap, f, (225, 228, 232, 255), 0.12)
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def polaroids(t: float, d: float, p: dict) -> Image.Image:
    """Two pinned polaroids of the story's footage on a paper board, each labelled, a taped title above (reference 4:50)."""
    img = _blank((176, 160, 130, 255))
    dr = ImageDraw.Draw(img)
    for r in range(0, 900, 6):   # a warm vignette on the board
        dr.ellipse([W / 2 - 1300 + r, H / 2 - 900 + r, W / 2 + 1300 - r, H / 2 + 900 - r], outline=(180 + r // 30, 164 + r // 30, 134 + r // 30, 255))
    title = str(p.get("title", "")).upper()
    ft = font("bold", 46)
    tw = _spaced_w(dr, title, ft, 0.08)
    dr.rectangle([(W - tw) / 2 - 40, 90, (W + tw) / 2 + 40, 170], fill=(245, 240, 228, 255))
    _spaced(dr, ((W - tw) / 2, 104), title, ft, (60, 50, 40, 255), 0.08)
    stills = p.get("stills") or []
    labels = [str(x) for x in p.get("labels", [])]
    for i in range(2):
        if t < 0.3 + 0.4 * i:
            continue
        card = Image.new("RGBA", (560, 600), (250, 250, 248, 255))
        pic = _still(stills[i], (500, 420)) if i < len(stills) else None
        if pic is not None:
            card.paste(pic, (30, 30))
        cd = ImageDraw.Draw(card)
        lab = labels[i] if i < len(labels) else ""
        fl = font("bold", 30)
        cd.text(((560 - _text_w(cd, lab, fl)) / 2, 490), lab, font=fl, fill=(50, 50, 50, 255))
        card = card.rotate(-4 if i == 0 else 5, expand=True, resample=Image.BICUBIC)
        img.alpha_composite(_shadow(card, 10, 140), (340 + i * 680, 260))
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def orange_place(t: float, d: float, p: dict) -> Image.Image:
    """Weather Teamplate's place tag, adopted: an orange box with the name, a white pulse ring beside it."""
    img = _blank()
    dr = ImageDraw.Draw(img)
    f, fs = font("bold", 38), font("semi", 22)
    name, sub = str(p.get("name", "")), str(p.get("sub", ""))
    w = int(max(_spaced_w(dr, name, f, 0.05), _text_w(dr, sub, fs)) + 44)
    x, y = W // 2 + 60, int(H * 0.40)
    k = (t % 1.2) / 1.2
    rr = 14 + 36 * k
    dr.ellipse([x - 70 - rr, y + 30 - rr, x - 70 + rr, y + 30 + rr], outline=(255, 255, 255, int(255 * (1 - k))), width=4)
    dr.ellipse([x - 78, y + 22, x - 62, y + 38], fill=WHITE)
    off = int(30 * (1 - _ease(t / IN_S)))
    dr.rectangle([x + off, y, x + off + w, y + (92 if sub else 62)], fill=(255, 112, 20, 240))
    _spaced(dr, (x + off + 22, y + 10), name, f, WHITE, 0.05)
    if sub:
        dr.text((x + off + 22, y + 58), sub, font=fs, fill=(255, 236, 220, 255))
    return _fade(img, _alpha(t, d))


def forecast(t: float, d: float, p: dict) -> Image.Image:
    """Weather's day-by-day strip, adopted for News Doc: dark navy, a card per day with its value, cards dealt in one by one."""
    img = _blank(NAVY)
    dr = ImageDraw.Draw(img)
    ft, fd, fv = font("bold", 44), font("bold", 30), font("heavy", 70)
    title = str(p.get("title", "")).upper()
    _spaced(dr, ((W - _spaced_w(dr, title, ft, 0.04)) / 2, 130), title, ft, WHITE, 0.04)
    days = [str(x) for x in p.get("days", [])][:5]
    vals = [str(x) for x in p.get("values", [])][:5]
    unit = str(p.get("unit", ""))
    n = max(1, len(days))
    cw, gap = 280, 36
    x0 = (W - (n * cw + (n - 1) * gap)) // 2
    for i, day in enumerate(days):
        k = _ease((t - 0.25 - 0.18 * i) / 0.5)
        if k <= 0:
            continue
        x = x0 + i * (cw + gap)
        y = 330 + int(40 * (1 - k))
        dr.rounded_rectangle([x, y, x + cw, y + 420], radius=18, fill=(26, 38, 58, int(255 * k)), outline=(60, 90, 120, int(255 * k)), width=2)
        dr.text((x + (cw - _text_w(dr, day, fd)) / 2, y + 40), day, font=fd, fill=(190, 205, 220, int(255 * k)))
        v = vals[i] if i < len(vals) else ""
        dr.text((x + (cw - _text_w(dr, v, fv)) / 2, y + 170), v, font=fv, fill=(255, 255, 255, int(255 * k)))
        dr.text((x + (cw - _text_w(dr, unit, fd)) / 2, y + 290), unit, font=fd, fill=CYAN)
    return _fade(img, _alpha(t, d, 0.3, 0.3))


def watermark(t: float, d: float, p: dict) -> Image.Image:
    """The channel name, small, bottom right (drawn here so the renderer can copy pure footage frames straight from the clips)."""
    img = _blank()
    dr = ImageDraw.Draw(img)
    f = font("bold", 26)
    text = str(p.get("text", ""))
    dr.text((W - 60 - _text_w(dr, text, f), H - 70), text, font=f, fill=(255, 255, 255, 170))
    return img


LOOKS = {"place": place, "ytag": ytag, "number": number, "chapter": chapter, "quote": quote, "quote_card": quote_card,
         "checklist": checklist, "chart": chart, "panel": panel, "glitch": glitch, "ring": ring, "line": line, "year": year,
         "pullquote": pullquote, "nametag": nametag, "rings": rings, "watermark": watermark, "caption": caption, "dossier": dossier,
         "headline": headline, "hbars": hbars, "framed": framed, "polaroids": polaroids, "orange_place": orange_place, "forecast": forecast}
ANIM_S = {"place": 0.4, "ytag": 0.4, "number": 1.0, "chapter": 1.0, "quote": 1.9, "quote_card": None, "checklist": None, "chart": None,
          "panel": 2.0, "glitch": None, "ring": 1.5, "line": 2.3, "year": 0.6, "pullquote": 0.4, "nametag": 0.4, "rings": 1.4,
          "watermark": 0.04, "caption": 1.2, "dossier": None, "headline": 0.6, "hbars": 1.6, "framed": None, "polaroids": 1.2,
          "orange_place": None, "forecast": 1.4}
# None: animated for its whole length
BREATHE = {"quote_card": 0.035, "chart": 0.03, "hbars": 0.03, "line": 0.02}   # full-screen cards drift in slowly: the screen never stands still


def _breathe(img: Image.Image, k: float, amount: float) -> Image.Image:
    s = 1.0 + amount * min(1.0, max(0.0, k))
    w, h = int(W * s), int(H * s)
    big = img.resize((w, h), Image.BICUBIC)
    x, y = (w - W) // 2, (h - H) // 2
    return big.crop((x, y, x + W, y + H))


def _ffmpeg() -> str:
    try:
        from map_scene.render import _ffmpeg as find

        return find()
    except Exception:
        return "ffmpeg"


def render(ov, out_dir: "str | Path") -> Optional[Path]:
    """The overlay as a transparent .mov (qtrle, 30 fps): its animation frame by frame, the still middle as one held frame."""
    fn = LOOKS.get(ov.kind)
    d = float(ov.t1 - ov.t0)
    if fn is None or d <= 0.05:
        return None
    out = Path(out_dir) / f"{ov.kind}_{int(ov.t0 * 1000):08d}.mov"
    tmp = Path(tempfile.mkdtemp(prefix="nd_", dir=str(out_dir)))
    try:
        frames: List[Tuple[Path, float]] = []
        anim = ANIM_S.get(ov.kind)
        n = int(round(d * FPS))
        if anim is None or anim + OUT_S + 0.2 >= d:
            ts = [i / FPS for i in range(n)]
            steps = [(t, 1.0 / FPS) for t in ts]
        else:
            a_n, o_n = int(anim * FPS), int(OUT_S * FPS) + 1
            steps = [(i / FPS, 1.0 / FPS) for i in range(a_n)]
            steps.append((anim, d - anim - o_n / FPS))
            steps += [(d - (o_n - i) / FPS, 1.0 / FPS) for i in range(o_n)]
        if ov.kind == "checklist":   # the ticks: one frame per change is enough
            steps = [(i / 10.0, 0.1) for i in range(int(d * 10))]
        if ov.kind in BREATHE:       # the slow drift: 15 frames a second is smooth enough for a 3 % zoom
            steps = [(i / 15.0, 1.0 / 15.0) for i in range(int(d * 15))]
        for k, (t, hold) in enumerate(steps):
            p = tmp / f"f{k:05d}.png"
            frame = fn(t, d, ov.params)
            if ov.kind in BREATHE:
                frame = _breathe(frame, t / d, BREATHE[ov.kind])
            frame.save(p, compress_level=1)
            frames.append((p, max(1.0 / FPS, hold)))
        lst = tmp / "list.txt"
        lines = []
        for p, hold in frames:
            lines += [f"file '{p}'", f"duration {hold:.4f}"]
        lines.append(f"file '{frames[-1][0]}'")
        lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
        r = subprocess.run([_ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", f"fps={FPS},format=argb",
                            "-t", f"{d:.3f}", "-c:v", "qtrle", str(out)], capture_output=True, text=True, timeout=600)
        return out if r.returncode == 0 and out.is_file() else None
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
