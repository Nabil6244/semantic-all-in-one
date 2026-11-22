"""Game Launch look: Vice-sunset colours, cards drawn with PIL, the glitch cut and a synthwave bed made in code.

Everything here draws or writes one file; nothing knows about the CSV or the app."""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
PINK, TEAL, NAVY, WHITE = (255, 46, 136), (0, 214, 201), (12, 16, 40), (255, 255, 255)
TEAL_DARK = (0, 150, 150)
_ROOT = Path(__file__).resolve().parent.parent
_HEAD_FONTS = ("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", "C:/Windows/Fonts/bahnschrift.ttf",
               str(_ROOT / "assets/fonts/Outfit-ExtraBold.ttf"))
_TAG_FONTS = (str(_ROOT / "assets/fonts/Outfit-ExtraBold.ttf"), str(_ROOT / "assets/fonts/Inter-Bold.ttf"))

# a short colour-split + noise burst on the first frames of every shot: the series' cut
GLITCH = "rgbashift=rh=-14:bh=14:gv=6:enable='lt(t,0.18)',noise=alls=35:allf=t:enable='lt(t,0.14)'"
GRADE = "eq=saturation=1.1:contrast=1.04,colorbalance=rs=-0.03:bs=0.05:rh=0.05:bh=-0.03,vignette=PI/5"


def _first(paths) -> str:
    for p in paths:
        if Path(p).is_file():
            return p
    return paths[-1]


F_HEAD, F_TAG = _first(_HEAD_FONTS), _first(_TAG_FONTS)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, max(8, int(size)))


def fit(text: str, path: str, size: int, max_w: float) -> ImageFont.FreeTypeFont:
    """The font at `size`, shrunk until the text fits max_w (the fallback font is wider than the condensed one)."""
    d = ImageDraw.Draw(Image.new("L", (4, 4)))
    f = font(path, size)
    while size > 20 and d.textlength(text, font=f) > max_w:
        size = int(size * 0.92)
        f = font(path, size)
    return f


def shadow_text(img: Image.Image, xy, text: str, f, fill=WHITE, anchor: str = "mm", blur: int = 10) -> None:
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((xy[0] + 4, xy[1] + 6), text, font=f, fill=(0, 0, 0, 200), anchor=anchor)
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(img).text(xy, text, font=f, fill=fill, anchor=anchor)


def pill(img: Image.Image, xy, text: str, bg, size: int = 40, anchor: str = "lt") -> None:
    d = ImageDraw.Draw(img)
    f = font(F_TAG, size)
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    pw, ph = r - l + 44, b - t + 26
    x, y = xy
    if anchor == "rt":
        x -= pw
    elif anchor == "mt":
        x -= pw // 2
    d.rounded_rectangle((x, y, x + pw, y + ph), radius=ph // 2, fill=tuple(bg) + (235,))
    d.text((x + 22 - l, y + 13 - t), text, font=f, fill=WHITE)


def band(img: Image.Image, top: int, strength: int = 180) -> None:
    b = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    h = img.size[1]
    for y in range(top, h):
        a = int(strength * ((y - top) / max(1, h - top)) ** 1.5)
        d.line([(0, y), (img.size[0], y)], fill=NAVY + (a,))
    img.alpha_composite(b)


# ---------------------------------------------------------------------------------------------------------------- cards

def receipt(name: str, at: float) -> str:
    """Where a trailer shot comes from: 'TRAILER 1 · 0:42', 'LAUNCH TRAILER · 1:05'."""
    import re
    stem = Path(str(name or "")).stem.lower()
    m = re.search(r"trailer[ _-]?(\d+)", stem)
    label = f"TRAILER {m.group(1)}" if m else ("LAUNCH TRAILER" if "launch" in stem else stem.replace("_", " ").upper())
    t = max(0, int(at or 0))
    return f"{label}  ·  {t // 60}:{t % 60:02d}"


def is_ai_clip(name: str) -> bool:
    """A clip made with an AI video tool (file name starting 'flow_' or 'ai_'): labelled AI RECREATION, never as trailer footage."""
    return Path(str(name or "")).stem.lower().startswith(("flow_", "ai_"))


def chip_png(real: bool, path, tag: str = "", label: str = "") -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pill(img, (60, 56), label or ("REAL LIFE" if real else "IN GAME"), TEAL_DARK if real else PINK, 38)
    if tag:
        pill(img, (60, H - 120), tag, NAVY, 30)
    img.save(path)


def _check(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, ok: bool) -> None:
    """A filled round badge with a tick (confirmed) or a cross (not confirmed), drawn so no glyph font is needed."""
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=((40, 200, 120) if ok else PINK) + (255,))
    w = max(4, int(r * 0.28))
    if ok:
        d.line([(cx - r * 0.45, cy + r * 0.02), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.35)], fill=WHITE, width=w,
               joint="curve")
    else:
        k = r * 0.4
        d.line([(cx - k, cy - k), (cx + k, cy + k)], fill=WHITE, width=w)
        d.line([(cx - k, cy + k), (cx + k, cy - k)], fill=WHITE, width=w)


def board_layout(n: int):
    """Row positions for n board items: one column up to 6, two above."""
    cols = 1 if n <= 6 else 2
    rows = -(-n // cols)
    rh = min(96, int(580 / max(1, rows)))
    top = 395 + (580 - rows * rh) // 2
    xs = [W // 2 - 500] if cols == 1 else [180, W // 2 + 50]
    return [(xs[k // rows], top + (k % rows) * rh, rh) for k in range(n)], (1000 if cols == 1 else 690)


def board_pngs(title: str, items, folder: Path, stem: str):
    """[(png, item index or -1 for the frame)]: the panel + heading, then one png per item (ticked in one by one by the renderer)."""
    out = []
    base = Image.new("RGBA", (W, H), NAVY + (150,))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle((110, 150, W - 110, H - 80), radius=36, fill=NAVY + (215,), outline=PINK + (255,), width=5)
    shadow_text(base, (W // 2, 245), title, fit(title, F_HEAD, 120, W - 400))
    yes = sum(1 for it in items if it["value"])
    pill(base, (W // 2, 315), f"{yes} CONFIRMED  ·  {len(items) - yes} NOT YET", PINK, 30, anchor="mt")
    f0 = folder / f"{stem}_board.png"
    base.save(f0)
    out.append((f0, -1))
    pos, width = board_layout(len(items))
    for k, (it, (x, y, rh)) in enumerate(zip(items, pos)):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = rh * 0.32
        _check(d, x + r, y + rh / 2, r, it["value"])
        label = it["label"].upper()
        tag = "CONFIRMED" if it["value"] else "NOT CONFIRMED"
        fl = fit(label, F_HEAD, int(rh * 0.6), width - 2 * r - 300)
        d.text((x + 2 * r + 28, y + rh / 2), label, font=fl, fill=WHITE, anchor="lm")
        ft = font(F_TAG, max(18, int(rh * 0.26)))
        d.text((x + width, y + rh / 2), tag, font=ft, fill=((90, 230, 150) if it["value"] else PINK), anchor="rm")
        d.line([(x, y + rh - 3), (x + width, y + rh - 3)], fill=(255, 255, 255, 40), width=2)
        f = folder / f"{stem}_item{k:02d}.png"
        img.save(f)
        out.append((f, k))
    return out


def timeline_pngs(title: str, items, folder: Path, stem: str):
    """[(png, item index or -1)]: the heading and the line, then one png per date (dot, date above, text below)."""
    out = []
    base = Image.new("RGBA", (W, H), NAVY + (165,))
    shadow_text(base, (W // 2, 230), title, fit(title, F_HEAD, 120, W - 300))
    d = ImageDraw.Draw(base)
    y = 600
    d.rounded_rectangle((150, y - 5, W - 150, y + 5), radius=5, fill=(255, 255, 255, 90))
    f0 = folder / f"{stem}_line.png"
    base.save(f0)
    out.append((f0, -1))
    n = len(items)
    xs = [W // 2] if n == 1 else [200 + k * (W - 400) / (n - 1) for k in range(n)]
    span = (W - 400) / max(1, n - 1) if n > 1 else W - 400
    for k, (it, x) in enumerate(zip(items, xs)):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        last = k == n - 1
        col = PINK if last else TEAL
        if k:
            d.rounded_rectangle((xs[k - 1], y - 5, x, y + 5), radius=5, fill=col + (255,))
        r = 30 if last else 20
        d.ellipse((x - r, y - r, x + r, y + r), fill=col + (255,), outline=WHITE, width=5)
        date = it["label"].upper()
        shadow_text(img, (x, y - 80), date, fit(date, F_HEAD, 74 if last else 58, span * 0.95), fill=col if last else WHITE)
        words = it["value"].split()
        lines, cur = [], ""
        ft = font(F_TAG, 34 if last else 30)
        for w_ in words:
            t = (cur + " " + w_).strip()
            if d.textlength(t, font=ft) > span * 0.9 and cur:
                lines.append(cur)
                cur = w_
            else:
                cur = t
        if cur:
            lines.append(cur)
        for j, ln in enumerate(lines[:4]):
            shadow_text(img, (x, y + 80 + j * 46), ln, ft, fill=(235, 235, 245), blur=6)
        f = folder / f"{stem}_date{k:02d}.png"
        img.save(f)
        out.append((f, k))
    return out


DOSSIER_BOX = (110, 230, 1070, 770)          # where the character's footage plays (960x540)


def dossier_png(name: str, role: str, line: str, seen: str, path) -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = DOSSIER_BOX
    d.rectangle((x0 - 14, y0 - 14, x1 + 14, y1 + 14), outline=WHITE + (255,), width=6)
    d.rectangle((x0 - 14, y1 + 14, x1 + 14, y1 + 96), fill=WHITE + (255,))
    d.text((x0 + 10, y1 + 55), "FIRST SEEN  ·  " + seen, font=font(F_TAG, 32), fill=NAVY, anchor="lm")
    pill(img, (x0 - 14, y0 - 90), "CHARACTER FILE", PINK, 34)
    tx = x1 + 90
    shadow_text(img, (tx, 420), name.upper(), fit(name.upper(), F_HEAD, 130, W - tx - 70), anchor="ls")
    d.rectangle((tx, 445, tx + 220, 455), fill=PINK + (255,))
    if role:
        shadow_text(img, (tx, 520), role.upper(), fit(role.upper(), F_TAG, 44, W - tx - 70), fill=TEAL, anchor="ls")
    if line:
        ft = font(F_TAG, 34)
        words, lines, cur = line.split(), [], ""
        for w_ in words:
            t = (cur + " " + w_).strip()
            if d.textlength(t, font=ft) > W - tx - 90 and cur:
                lines.append(cur)
                cur = w_
            else:
                cur = t
        if cur:
            lines.append(cur)
        for j, ln in enumerate(lines[:5]):
            shadow_text(img, (tx, 600 + j * 50), ln, ft, fill=(235, 235, 245), anchor="ls", blur=6)
    img.save(path)


# ---------------------------------------------------------------------------------------------------------------- guide cards

GREEN = (90, 230, 150)
STEPS_BOX = (1180, 110, W - 70, H - 110)     # the walkthrough panel on the right (the gameplay stays sharp on the left)


def wrap(d: ImageDraw.ImageDraw, text: str, f, max_w: float, most: int = 3):
    lines, cur = [], ""
    for w_ in str(text).split():
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=f) > max_w and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = t
    if cur:
        lines.append(cur)
    if len(lines) > most:
        lines = lines[:most]
        lines[-1] = lines[-1].rstrip(".,") + "..."
    return lines


def steps_pngs(title: str, items, folder: Path, stem: str):
    """[png per step]: the whole list every time, step k lit (pink badge, white text), the ones before it ticked, the rest dim."""
    out = []
    x0, y0, x1, y1 = STEPS_BOX
    n = len(items)
    top = y0 + 150
    rh = min(150, int((y1 - 40 - top) / max(1, n)))
    ft = font(F_TAG, max(24, min(38, int(rh * 0.3))))
    for k in range(n):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((x0, y0, x1, y1), radius=30, fill=NAVY + (225,), outline=PINK + (255,), width=4)
        head = title.upper()
        shadow_text(img, (x0 + 50, y0 + 85), head, fit(head, F_HEAD, 84, x1 - x0 - 100), anchor="ls", blur=6)
        d = ImageDraw.Draw(img)
        d.text((x0 + 52, y0 + 112), f"STEP {k + 1} OF {n}", font=font(F_TAG, 26), fill=TEAL, anchor="ls")
        for j, it in enumerate(items):
            y = top + j * rh
            r = min(34, rh * 0.3)
            cx, cy = x0 + 50 + r, y + rh / 2
            if j < k:
                _check(d, cx, cy, r, True)
            else:
                lit = j == k
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(PINK if lit else (60, 66, 100)) + (255,))
                d.text((cx, cy), str(j + 1), font=font(F_HEAD, int(r * 1.3)), fill=WHITE if lit else (170, 175, 200), anchor="mm")
            if j == k:
                d.rounded_rectangle((x0 + 24, y + 6, x1 - 24, y + rh - 6), radius=18, outline=PINK + (255,), width=3)
            col = WHITE if j == k else ((200, 205, 225) if j < k else (130, 136, 165))
            tx = cx + r + 26
            lines = wrap(d, it, ft, x1 - tx - 40, most=max(1, int(rh * 0.8 / (ft.size * 1.2))))
            lh = ft.size * 1.2
            y_text = cy - (len(lines) - 1) * lh / 2
            for m, ln in enumerate(lines):
                d.text((tx, y_text + m * lh), ln, font=ft, fill=col, anchor="lm")
        f = folder / f"{stem}_step{k:02d}.png"
        img.save(f)
        out.append(f)
    return out


def money_text(v: float) -> str:
    if v >= 1e6:
        return f"${v / 1e6:.1f}M".replace(".0M", "M")
    return f"${v:,.0f}"


def payout_pngs(title: str, items, folder: Path, stem: str):
    """[png per state]: state 0 the heading and an empty board, state k the first k methods with their money and the running
    total (no total when a value is not an amount)."""
    out = []
    n = len(items)
    totals = all(it.get("amount") is not None for it in items)
    pos, width = board_layout(n)
    for k in range(n + 1):
        img = Image.new("RGBA", (W, H), NAVY + (150,))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((110, 150, W - 110, H - 80), radius=36, fill=NAVY + (215,), outline=PINK + (255,), width=5)
        shadow_text(img, (W // 2, 245), title.upper(), fit(title.upper(), F_HEAD, 120, W - 400))
        if totals:
            tot = sum(it["amount"] for it in items[:k])
            pill(img, (W // 2, 315), "TOTAL  " + money_text(tot), (30, 150, 90) if k else (60, 66, 100), 34, anchor="mt")
        d = ImageDraw.Draw(img)
        for j, (it, (x, y, rh)) in enumerate(zip(items[:k], pos)):
            label = it["label"].upper()
            fl = fit(label, F_HEAD, int(rh * 0.6), width - 320)
            d.text((x, y + rh / 2), label, font=fl, fill=WHITE, anchor="lm")
            val = ("+" + money_text(it["amount"])) if it.get("amount") is not None else it["value"].upper()
            fv = fit(val, F_HEAD, int(rh * 0.62), 300)
            d.text((x + width, y + rh / 2), val, font=fv, fill=GREEN if j == k - 1 else (200, 235, 210), anchor="rm")
            d.line([(x, y + rh - 3), (x + width, y + rh - 3)], fill=(255, 255, 255, 40), width=2)
        f = folder / f"{stem}_pay{k:02d}.png"
        img.save(f)
        out.append(f)
    return out


def rank_png(number: str, name: str, line: str, path) -> None:
    """A countdown entry: the big pink #N top left, the name and its line in a lower third."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band(img, H // 2 + 60, 200)
    fn = font(F_HEAD, 260)
    shadow_text(img, (80, 330), number, fn, fill=PINK, anchor="ls", blur=14)
    head = name.upper()
    f = fit(head, F_HEAD, 140, W - 220)
    shadow_text(img, (100, 900), head, f, anchor="ls")
    d = ImageDraw.Draw(img)
    d.rectangle((100, 922, 100 + min(W - 200, d.textlength(head, font=f)), 934), fill=PINK)
    if line:
        shadow_text(img, (102, 995), line, fit(line, F_TAG, 42, W - 220), fill=(255, 220, 235), anchor="ls", blur=6)
    img.save(path)


def spot_pngs(tag: str, hint: str, xy, folder: Path, stem: str):
    """(ring png, pulse png, label png): a ring on the place, a wider thin ring for the pulse, the tag beside it with a leader
    line, the hint along the bottom."""
    cx, cy = xy[0] * W, xy[1] * H
    ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ring)
    r = 70
    d.ellipse((cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6), outline=(0, 0, 0, 150), width=16)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=PINK + (255,), width=10)
    d.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=WHITE + (255,))
    pulse = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    r2 = 108
    ImageDraw.Draw(pulse).ellipse((cx - r2, cy - r2, cx + r2, cy + r2), outline=WHITE + (200,), width=5)
    lab = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lab)
    right = cx < W * 0.62                               # the tag goes to the side with room
    up = cy > H * 0.3
    lx = cx + (r + 150 if right else -(r + 150))
    ly = cy + (-(r + 70) if up else r + 70)
    d.line([(cx + (r if right else -r) * 0.7, cy + (-r if up else r) * 0.7), (lx, ly)], fill=WHITE + (255,), width=5)
    text = tag.upper()
    f = font(F_TAG, 40)
    tw = d.textlength(text, font=f) + 44
    px = lx if right else lx - tw
    px = max(40, min(W - tw - 40, px))
    py = ly - 32
    pill(lab, (px, py), text, PINK, 40)
    if hint:
        band(lab, H - 260, 210)
        shadow_text(lab, (W // 2, H - 90), hint, fit(hint, F_TAG, 46, W - 200), fill=WHITE, blur=6)
    paths = []
    for name, im in (("ring", ring), ("pulse", pulse), ("label", lab)):
        f_ = folder / f"{stem}_{name}.png"
        im.save(f_)
        paths.append(f_)
    return tuple(paths)


def inset_png(tag: str, path, box) -> None:
    """The frame and the 'seen in' tag around a map's trailer box."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.rectangle((x0 - 8, y0 - 8, x1 + 8, y1 + 8), outline=WHITE + (255,), width=6)
    pill(img, (x0 - 8, y1 + 18), "SEEN IN  " + tag, PINK, 28)
    img.save(path)


def progress_png(n: int, idx: int, title: str, path) -> None:
    """The chapter bar along the top: n segments, the current one lit, 'CHAPTER 2/5 · THE CHARACTERS'."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, x1, y, gap = W // 2 - 300, W // 2 + 300, 34, 10
    seg = (x1 - x0 - gap * (n - 1)) / n
    for k in range(n):
        a = x0 + k * (seg + gap)
        col = PINK + (255,) if k == idx else (WHITE + (230,) if k < idx else (255, 255, 255, 70))
        d.rounded_rectangle((a, y, a + seg, y + 10), radius=5, fill=col)
    txt = f"CHAPTER {idx + 1}/{n}  ·  {title.upper()}"
    f = font(F_TAG, 24)
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((W // 2 + 2, y + 32), txt, font=f, fill=(0, 0, 0, 200), anchor="mt")
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4)))
    d.text((W // 2, y + 30), txt, font=f, fill=WHITE, anchor="mt")
    img.save(path)


def title_png(head: str, sub: str, tag: str, path) -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band(img, H // 2)
    f = fit(head, F_HEAD, 210 if len(head) < 10 else 170, W - 200)
    shadow_text(img, (W // 2, 760), head, f)
    tw = ImageDraw.Draw(img).textlength(head, font=f)
    ImageDraw.Draw(img).rectangle((W // 2 - tw / 2, 850, W // 2 + tw / 2, 862), fill=PINK)
    if sub:
        shadow_text(img, (W // 2, 925), sub, fit(sub, F_TAG, 44, W - 200), fill=(255, 220, 235))
    if tag:
        pill(img, (60, 56), tag, PINK, 38)
    img.save(path)


def chapter_png(num: str, title: str, sub: str, path) -> None:
    img = Image.new("RGBA", (W, H), NAVY + (120,))
    d = ImageDraw.Draw(img)
    fn = font(F_HEAD, 300)
    shadow_text(img, (150, 640), num, fn, fill=PINK, anchor="ls")
    nw = d.textlength(num, font=fn)
    x = 150 + nw + 90
    d.rectangle((x - 50, 380, x - 38, 640), fill=WHITE)
    shadow_text(img, (x, 560), title, fit(title, F_HEAD, 170, W - x - 80), anchor="ls")
    if sub:
        shadow_text(img, (x + 4, 630), sub, font(F_TAG, 40), fill=TEAL, anchor="ls")
    img.save(path)


def split_png(left: str, right: str, path, tag: str = "", pills=("IN GAME", "REAL LIFE")) -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((W // 2 - 5, 0, W // 2 + 5, H), fill=PINK + (255,))
    pill(img, (60, 56), pills[0], PINK, 38)
    if tag:
        pill(img, (60, 128), tag, NAVY, 26)
    pill(img, (W - 60, 56), pills[1], TEAL_DARK, 38, anchor="rt")
    band(img, H - 330, 190)
    if left or right:
        eq = "  =  " if left and right else ""
        f = fit(left + eq + right, F_HEAD, 112, W - 160)
        wl, we, wr = (d.textlength(t, font=f) for t in (left, eq, right))
        x = W / 2 - (wl + we + wr) / 2
        shadow_text(img, (x, 990), left, f, anchor="ls")
        shadow_text(img, (x + wl, 990), eq, f, fill=PINK, anchor="ls")
        shadow_text(img, (x + wl + we, 990), right, f, fill=TEAL, anchor="ls")
    img.save(path)


def short_png(top: str, second: str, foot: str, path) -> None:
    img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    shadow_text(img, (540, 330), top, fit(top, F_HEAD, 150, 1000))
    if second:
        shadow_text(img, (540, 470), second, fit(second, F_HEAD, 120, 1000), fill=PINK)
    if foot:
        shadow_text(img, (540, 1560), foot, fit(foot, F_HEAD, 90, 1000), fill=TEAL)
    img.save(path)


def thumbnail(left: Image.Image, right: Image.Image, head: str, sub: str, tag: str, path, right_tag: str = "REAL LIFE") -> None:
    """1280x720: game frame | real frame, pink divider, big text at the bottom."""
    from PIL import ImageEnhance

    def half(im):
        im = im.convert("RGB").resize((W, H))
        return ImageEnhance.Color(im.crop((W // 4, 0, W // 4 + W // 2, H))).enhance(1.3)

    img = Image.new("RGBA", (W, H))
    img.paste(half(left), (0, 0))
    img.paste(half(right), (W // 2, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((W // 2 - 8, 0, W // 2 + 8, H), fill=PINK)
    pill(img, (50, 50), tag or "IN GAME", PINK, 70)
    if right_tag:
        pill(img, (W - 50, 50), right_tag, TEAL_DARK, 70, anchor="rt")
    band(img, 560, 230)
    shadow_text(img, (W // 2, 880), head, fit(head, F_HEAD, 250, W - 120), blur=16)
    if sub:
        shadow_text(img, (W // 2, 1010), sub, fit(sub, F_HEAD, 110, W - 160), fill=TEAL, blur=12)
    img.convert("RGB").resize((1280, 720)).save(path, quality=92)


# ---------------------------------------------------------------------------------------------------------------- music

SR = 44100
BPM = 108


def _synth(seconds: float) -> np.ndarray:
    """A small synthwave arrangement (pad, bass, arpeggio, drums); its patterns repeat every 4 bars."""
    beat = 60 / BPM
    n = int(seconds * SR)
    t = np.arange(n) / SR
    mix = np.zeros(n)
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)  # noqa: E731
    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]  # Am F C G
    bar = beat * 4

    def lp(x, a):
        y = np.empty_like(x)
        acc = 0.0
        for k in range(len(x)):
            acc += a * (x[k] - acc)
            y[k] = acc
        return y

    def saw(f, tt):
        return 2 * ((tt * f) % 1) - 1

    pad = np.zeros(n)
    for c in range(int(seconds / bar) + 1):
        s0, s1 = int(c * bar * SR), min(n, int((c + 1) * bar * SR))
        if s0 >= n:
            break
        tt = t[s0:s1] - t[s0]
        env = np.minimum(1, tt / 0.6) * np.minimum(1, (bar - tt) / 0.3)
        for m in chords[c % 4]:
            for det in (-0.12, 0.12):
                pad[s0:s1] += saw(hz(m + 12) * 2 ** (det / 12), tt) * env
    mix += lp(pad, 0.06) * 0.05
    for k in range(int(seconds / (beat / 2))):
        s0 = int(k * beat / 2 * SR)
        s1 = min(n, s0 + int(beat / 2 * SR))
        if s0 >= n:
            break
        tt = t[s0:s1] - t[s0]
        root = chords[int(k * beat / 2 / bar) % 4][0] - 24
        mix[s0:s1] += saw(hz(root), tt) * np.exp(-tt * 6) * 0.22
    for k in range(int(seconds / (beat / 4))):
        s0 = int(k * beat / 4 * SR)
        s1 = min(n, s0 + int(beat / 4 * SR))
        if s0 >= n:
            break
        tt = t[s0:s1] - t[s0]
        ch = chords[int(k * beat / 4 / bar) % 4]
        m = (ch + tuple(x + 12 for x in ch))[k % 6] + 12
        mix[s0:s1] += np.sign(np.sin(2 * np.pi * hz(m) * tt)) * np.exp(-tt * 18) * 0.035
    rng = np.random.default_rng(7)
    for k in range(int(seconds / beat) + 1):
        s0 = int(k * beat * SR)
        if s0 >= n:
            break
        seg = min(n - s0, int(0.45 * SR))
        tt = np.arange(seg) / SR
        if k % 2 == 0:
            mix[s0:s0 + seg] += np.sin(2 * np.pi * (45 * tt + 2.5 * (1 - np.exp(-tt * 30)))) * np.exp(-tt * 9) * 0.5
        else:
            mix[s0:s0 + seg] += rng.standard_normal(seg) * np.exp(-tt * 9) * 0.16
        for h in (0, 0.5):
            hs = int((k + h) * beat * SR)
            hl = min(n - hs, int(0.05 * SR))
            if hl > 0:
                mix[hs:hs + hl] += np.diff(rng.standard_normal(hl + 1)) * np.exp(-np.arange(hl) / SR * 80) * 0.03
    return np.tanh(mix * 1.4) * 0.7


def music(total: float, path, cache: Optional[Path] = None) -> None:
    """A synthwave bed `total` s long: one seamless 8-bar loop (made once, cached) tiled, faded in and out. No licensed music."""
    loop_f = Path(cache or Path(path).parent) / "synthwave_loop.npy"
    if loop_f.is_file():
        loop = np.load(loop_f)
    else:
        x = _synth(40.0)
        bar = 60 / BPM * 4
        loop = x[int(4 * bar * SR):int(12 * bar * SR)].astype(np.float32)   # bars 4-12: seamless, past the start
        try:
            loop_f.parent.mkdir(parents=True, exist_ok=True)
            np.save(loop_f, loop)
        except OSError:
            pass
    n = int(total * SR)
    y = np.tile(loop, n // len(loop) + 1)[:n]
    t = np.arange(n) / SR
    y = y * np.minimum(1, t / 1.5) * np.minimum(1, (total - t) / 3.0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())


def size_of(path) -> Tuple[int, int]:
    with Image.open(path) as im:
        return im.size
