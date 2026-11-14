"""Ocean card pack (docs/ocean/PATTERNS.md section 5, plan step 4). Every card is a stage kind: a sprite drawn in
1280 x 720 units that pops onto the ocean stage like an animal. Animated cards read args["_k"] (0..1, set by the stage
from the element's `anim` seconds) to grow bars, fill dots or count up; without it they draw finished.

Data cards
    number_hero    {number, line, key, color}                    "16" + "didn't come back UNTIL NEXT YEAR" (counts up)
    dot_grid       {total, marked, cols, left:[num,label], right:[num,label]}   90 dots, 5 red
    icon_rows      {animal, count, per_row, title, sub}           rows of little whales, "FEWER THAN 80"
    standoff       {left:[num,label], right:[num,label]}          "35 ORCAS" ... "9 SPERM WHALES"
    progress       {value, label, note}                           "~93%" bar
    bar_race       {title, rows:[[label, value, text]]}           top speed bars
    meters         {rows:[[label, level]], title}                 LIGHT / FOOD / OXYGEN
    counter        {number, label, color}                         "0 APEX PREDATORS LEFT"
    calendar       {month, day, year, line}                       NOV page
    clock          {time, hours}                                  clock face + "0:30 HRS"
    size_bar       {label, length}                                |---- ~16 m ----|
    callout        {text, dx, dy}                                 leader line + caps label
    name_tag       {text, sub}                                    "Otodus chubutensis" underlined
    name_chips     {chips:[[name, sub]], lit}                     O. angustidens | grandpa
    strata         {rows:[label], key}                            stacked rock layers with ages
Story / joke cards
    mystery        {slots:[label or ""], animals:[name or ""], lit}   3 "?" cards, revealed one by one
    paper          {journal, title, authors}                      study card
    choose_move    {title, options, selected}                     game menu
    quiz           {title, options:[[text, mark]]}                mark: "x" | "check" | ""
    playbook       {title, step}                                  chalk Xs and dotted arrows
    crime_tape     {text}                                         two crossing tapes (full frame)
    wanted         {animal, crime, reward}                        poster
    halo           {}                                             halo + sparkles
    bunting        {}                                             party flags
    shop           {title, price, animal}                         online listing
    diver_hud      {depth, air, tip}                              depth / air panel
    duel           {left:[animal,label], right:[animal,label]}    predator / victim panels
    silhouettes    {title, rows:[[animal, label]]}                paper chart of black shapes
    comments       {text}                                         a viewer comment card
    watch_next     {channel, line}                                end screen
All text is our own; nothing is copied from the reference channel.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from cinematic_explainer.war import tokens as T

from . import animals as A
from . import look as L

PANEL = (14, 22, 32, 236)
PANEL_EDGE = (70, 96, 116, 255)
PAPER = (240, 236, 226, 255)
CHALK = (232, 236, 232, 255)
BOARD = (30, 46, 40, 255)
DIM = (120, 138, 150, 255)
GREEN = (88, 200, 140, 255)


# ------------------------------------------------------------------------------------------------------------------ helpers

def F(kind: str, size: int):
    """Font in 1280-unit pixels (the stage scales the finished sprite)."""
    return T.font(kind, int(size))


def _k(a: Dict[str, Any]) -> float:
    k = a.get("_k")
    return 1.0 if k is None else max(0.0, min(1.0, float(k)))


def _ease(k: float) -> float:
    return 1 - (1 - k) ** 3


def _col(name: Any) -> Tuple[int, ...]:
    if isinstance(name, (list, tuple)):
        return tuple(int(c) for c in name[:3]) + (255,)
    return {"red": L.RED, "white": L.WHITE, "teal": L.TEAL, "green": GREEN}.get(str(name or ""), L.ORANGE)


def _tw(d: ImageDraw.ImageDraw, text: str, f) -> float:
    return d.textlength(text, font=f)


def _canvas(w: int, h: int) -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _panel(d: ImageDraw.ImageDraw, box, fill=PANEL, edge=PANEL_EDGE, r: int = 14, width: int = 2) -> None:
    d.rounded_rectangle(box, radius=r, fill=fill, outline=edge, width=width)


def _centre(d: ImageDraw.ImageDraw, cx: float, y: float, text: str, f, fill) -> None:
    d.text((cx - _tw(d, text, f) / 2, y), text, font=f, fill=fill)


def _fit(d: ImageDraw.ImageDraw, text: str, kind: str, size: int, max_w: float):
    f = F(kind, size)
    while size > 12 and _tw(d, text, f) > max_w:
        size -= 2
        f = F(kind, size)
    return f


def _wrap(d: ImageDraw.ImageDraw, text: str, f, max_w: float) -> List[str]:
    lines, cur = [], ""
    for w in str(text).split():
        t = (cur + " " + w).strip()
        if cur and _tw(d, t, f) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + ([cur] if cur else [])


def _count(number: Any, k: float) -> str:
    """Count a number up with k (keeps prefix / suffix like '~', '%', '+')."""
    s = str(number)
    m = re.match(r"^(\D*)([\d,]+(?:\.\d+)?)(.*)$", s)
    if not m or k >= 1:
        return s
    pre, num, post = m.groups()
    v = float(num.replace(",", ""))
    cur = v * _ease(k)
    dec = len(num.split(".")[1]) if "." in num else 0
    out = f"{cur:,.{dec}f}" if "," in num else f"{cur:.{dec}f}"
    return pre + out + post


def _two_tone(d: ImageDraw.ImageDraw, x: float, y: float, plain: str, key: str, size: int, key_col, centre: bool = True,
              plain_col=L.SOFT) -> None:
    fp, fk = F("regular", int(size * 0.8)), F("heavy", size)
    gap = 10 if plain and key else 0
    w = _tw(d, plain, fp) + gap + _tw(d, key, fk)
    x0 = x - w / 2 if centre else x
    base = y + fk.size
    if plain:
        d.text((x0, base), plain, font=fp, fill=plain_col, anchor="ls")
    d.text((x0 + _tw(d, plain, fp) + gap, base), key, font=fk, fill=key_col, anchor="ls")


def _animal(name: str, width: int, **kw: Any) -> Image.Image:
    return A.draw(name or "great_white", int(width), 0, **kw)


def _paste_c(im: Image.Image, sp: Image.Image, cx: float, cy: float) -> None:
    im.alpha_composite(sp, (int(cx - sp.width / 2), int(cy - sp.height / 2)))


# ------------------------------------------------------------------------------------------------------------------ data cards

def number_hero(a: Dict[str, Any]) -> Image.Image:
    k = _k(a)
    num = _count(a.get("number", "0"), min(1.0, k * 1.4))
    im, d = _canvas(900, 260)
    f = F("heavy", int(a.get("size", 120)))
    _centre(d, 450, 10, num, f, _col(a.get("color")))
    line, key = str(a.get("line", "")), str(a.get("key", "")).upper()
    if line or key:
        _two_tone(d, 450, 10 + f.size * 1.12, line, key, 34, _col(a.get("key_color", a.get("color"))))
    return im


def dot_grid(a: Dict[str, Any]) -> Image.Image:
    total, marked = int(a.get("total", 90)), int(a.get("marked", 5))
    cols = int(a.get("cols", 15))
    rows = math.ceil(total / cols)
    gap, r = 30, 7
    w = cols * gap + 120
    h = rows * gap + 150
    im, d = _canvas(max(w, 760), h)
    x0 = (im.width - cols * gap) / 2 + gap / 2
    y0 = 120
    k = _k(a)
    shown = int(round(total * _ease(k)))
    picks = set(int(i * total / max(1, marked) + (total / max(1, marked)) * 0.37) % total for i in range(marked))
    for i in range(shown):
        x, y = x0 + (i % cols) * gap, y0 + (i // cols) * gap
        c = L.RED if i in picks else (170, 186, 196, 255)
        d.ellipse((x - r, y - r, x + r, y + r), fill=c)
    for side, (anchor_x, align) in (("left", (20, "l")), ("right", (im.width - 20, "r"))):
        v = a.get(side)
        if not v:
            continue
        fn, fl = F("heavy", 64), F("bold", 20)
        num, lab = str(v[0]), str(v[1]).upper()
        col = L.ORANGE if side == "left" else L.RED
        nw, lw = _tw(d, num, fn), _tw(d, lab, fl)
        x = anchor_x if align == "l" else anchor_x - max(nw, lw)
        d.text((x, 6), num, font=fn, fill=col)
        d.text((x, 6 + fn.size * 1.05), lab, font=fl, fill=L.WHITE)
    return im


def icon_rows(a: Dict[str, Any]) -> Image.Image:
    n = int(a.get("count", 40))
    per = int(a.get("per_row", 16))
    rows = math.ceil(n / per)
    icon = _animal(a.get("animal", "orca"), 54)
    gx, gy = 66, icon.height + 22
    w = per * gx + 40
    top = 120 if a.get("title") else 20
    im, d = _canvas(max(w, 700), top + rows * gy + 20)
    if a.get("title"):
        f = _fit(d, str(a["title"]).upper(), "heavy", 56, im.width - 40)
        _centre(d, im.width / 2, 10, str(a["title"]).upper(), f, L.RED)
        if a.get("sub"):
            fs = F("regular", 24)
            _centre(d, im.width / 2, 12 + f.size * 1.15, str(a["sub"]), fs, L.SOFT)
    shown = int(round(n * _ease(_k(a))))
    x0 = (im.width - per * gx) / 2 + gx / 2
    for i in range(shown):
        _paste_c(im, icon, x0 + (i % per) * gx, top + (i // per) * gy + gy / 2)
    return im


def standoff(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(1180, 160)
    for side in ("left", "right"):
        v = a.get(side)
        if not v:
            continue
        num, lab = _count(v[0], min(1.0, _k(a) * 1.5)), str(v[1]).upper()
        fn, fl = F("heavy", 84), F("bold", 24)
        col = L.RED if side == "left" else L.WHITE
        nw, lw = _tw(d, num, fn), _tw(d, lab, fl)
        x = 10 if side == "left" else im.width - 10 - max(nw, lw)
        if side == "right":
            d.text((im.width - 10 - nw, 0), num, font=fn, fill=col)
            d.text((im.width - 10 - lw, fn.size * 1.02), lab, font=fl, fill=L.SOFT)
        else:
            d.text((x, 0), num, font=fn, fill=col)
            d.text((x, fn.size * 1.02), lab, font=fl, fill=L.SOFT)
    return im


def progress(a: Dict[str, Any]) -> Image.Image:
    v = max(0.0, min(100.0, float(re.sub(r"[^\d.]", "", str(a.get("value", 50))) or 50)))
    k = _ease(_k(a))
    im, d = _canvas(820, 230)
    f = F("heavy", 80)
    txt = str(a.get("label") or f"~{int(round(v))}%")
    _centre(d, 410, 0, _count(txt, k), f, GREEN)
    y = f.size * 1.2
    d.rounded_rectangle((40, y, 780, y + 34), radius=17, fill=(40, 56, 66, 255))
    if k > 0:
        d.rounded_rectangle((40, y, 40 + max(34, 740 * v / 100 * k), y + 34), radius=17, fill=GREEN)
    if a.get("note"):
        _centre(d, 410, y + 52, str(a["note"]), F("regular", 24), L.SOFT)
    return im


def bar_race(a: Dict[str, Any]) -> Image.Image:
    rows = list(a.get("rows") or [])[:6]
    im, d = _canvas(880, 90 + 62 * max(1, len(rows)))
    if a.get("title"):
        d.text((20, 10), str(a["title"]).upper(), font=F("bold", 26), fill=L.WHITE)
    vmax = max([float(r[1]) for r in rows] + [1.0])
    k = _ease(_k(a))
    fl = F("regular", 24)
    for i, r in enumerate(rows):
        y = 70 + i * 62
        d.text((20, y + 4), str(r[0]), font=fl, fill=L.SOFT)
        w = 520 * float(r[1]) / vmax * k
        d.rounded_rectangle((200, y, 200 + max(6, w), y + 34), radius=6, fill=L.ORANGE if i == 0 else (150, 162, 172, 255))
        if k > 0.95:
            d.text((214 + w, y + 4), str(r[2] if len(r) > 2 else r[1]), font=F("bold", 24), fill=L.WHITE)
    return im


def meters(a: Dict[str, Any]) -> Image.Image:
    rows = list(a.get("rows") or [["LIGHT", 0.1], ["FOOD", 0.2], ["OXYGEN", 0.8]])[:5]
    im, d = _canvas(640, 70 + 70 * len(rows))
    if a.get("title"):
        _centre(d, 320, 0, str(a["title"]).upper(), F("heavy", 44), L.ORANGE)
    k = _ease(_k(a))
    for i, (lab, lvl) in enumerate(rows):
        y = 70 + i * 70
        d.text((10, y + 2), str(lab).upper(), font=F("bold", 26), fill=L.WHITE)
        d.rounded_rectangle((190, y + 6, 620, y + 28), radius=11, fill=(40, 56, 66, 255))
        lv = 1.0 + (float(lvl) - 1.0) * k                              # bars fall from full to their level
        c = L.RED if lv < 0.25 else (L.ORANGE if lv < 0.55 else (140, 190, 240, 255))
        d.rounded_rectangle((190, y + 6, 190 + max(22, 430 * lv), y + 28), radius=11, fill=c)
    return im


def counter(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(520, 70)
    num, lab = str(a.get("number", "0")), str(a.get("label", "")).upper()
    fn, fl = F("heavy", 46), F("bold", 20)
    col = _col(a.get("color", "red"))
    r = 22
    d.ellipse((0, 12, 2 * r, 12 + 2 * r), fill=col)
    _centre(d, r, 12 + r - fn.size * 0.62, num, fn, L.WHITE)
    d.text((2 * r + 14, 12 + r - fl.size * 0.6), lab, font=fl, fill=L.WHITE)
    return im.crop(im.getbbox() or (0, 0, 1, 1))


def calendar(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(300, 300)
    d.rounded_rectangle((10, 30, 290, 290), radius=14, fill=PAPER)
    d.rounded_rectangle((10, 30, 290, 100), radius=14, fill=L.RED)
    d.rectangle((10, 80, 290, 100), fill=L.RED)
    _centre(d, 150, 38, (str(a.get("month") or "").upper()[:3] or "YEAR"), F("heavy", 44), L.WHITE)
    big = str(a.get("day") or a.get("year") or "")
    f = _fit(d, big, "heavy", 96, 250)
    _centre(d, 150, 108, big, f, L.INK)
    if a.get("line"):
        _centre(d, 150, 240, str(a["line"]), _fit(d, str(a["line"]), "bold", 24, 250), (90, 96, 104, 255))
    for x in (90, 210):
        d.rounded_rectangle((x - 8, 14, x + 8, 50), radius=6, fill=(170, 176, 182, 255))
    return im


def clock(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(300, 380)
    cx, cy, r = 150, 150, 130
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(20, 24, 30, 255), outline=L.WHITE, width=6)
    for i in range(12):
        ang = math.radians(i * 30)
        d.line((cx + math.sin(ang) * r * 0.82, cy - math.cos(ang) * r * 0.82, cx + math.sin(ang) * r * 0.94,
                cy - math.cos(ang) * r * 0.94), fill=L.WHITE, width=4)
    hours = float(a.get("hours", 0.5)) * _ease(_k(a))
    for length, turns, wdt in ((0.55, hours / 12.0, 8), (0.8, hours, 5)):
        ang = 2 * math.pi * turns
        d.line((cx, cy, cx + math.sin(ang) * r * length, cy - math.cos(ang) * r * length), fill=L.WHITE, width=wdt)
    d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=L.ORANGE)
    t = str(a.get("time") or f"{int(hours)}:{int((hours % 1) * 60):02d} HRS")
    _centre(d, 150, 300, t, F("heavy", 46), L.ORANGE)
    return im


def size_bar(a: Dict[str, Any]) -> Image.Image:
    ln = int(a.get("length", 500))
    im, d = _canvas(ln + 20, 70)
    k = _ease(_k(a))
    w = ln * k
    x0 = 10 + (ln - w) / 2
    y = 46
    d.line((x0, y, x0 + w, y), fill=L.ORANGE, width=3)
    for x in (x0, x0 + w):
        d.line((x, y - 10, x, y + 10), fill=L.ORANGE, width=3)
    if k > 0.6:
        _centre(d, 10 + ln / 2, 4, str(a.get("label", "")), F("bold", 26), L.WHITE)
    return im


def callout(a: Dict[str, Any]) -> Image.Image:
    dx, dy = float(a.get("dx", 120)), float(a.get("dy", -60))
    text = str(a.get("text", "")).upper()
    f = F("bold", int(a.get("size", 22)))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = _tw(probe, text, f)
    w = int(abs(dx) + 2 * tw + 60)             # room for the label on either side of the centred line
    h = int(abs(dy) + 60)
    im, d = _canvas(w, h)
    sx = w / 2 - dx / 2                       # the sprite is centred on the middle of the line
    sy = h / 2 - dy / 2
    ex, ey = sx + dx * _ease(_k(a)), sy + dy * _ease(_k(a))
    d.ellipse((sx - 5, sy - 5, sx + 5, sy + 5), fill=L.WHITE)
    d.line((sx, sy, ex, ey), fill=L.WHITE, width=2)
    if _k(a) > 0.7:
        tx = ex + 10 if dx >= 0 else ex - 10 - tw
        d.text((tx, ey - f.size * 0.6), text, font=f, fill=_col(a.get("color", "white")))
    return im


def name_tag(a: Dict[str, Any]) -> Image.Image:
    text = str(a.get("text", ""))
    im, d = _canvas(700, 90)
    f = F("bold", int(a.get("size", 30)))
    d.text((8, 4), text, font=f, fill=L.WHITE)
    tw = _tw(d, text, f)
    d.line((8, 8 + f.size * 1.15, 8 + tw * _ease(_k(a)), 8 + f.size * 1.15), fill=L.WHITE, width=2)
    if a.get("sub"):
        d.text((8, 18 + f.size * 1.2), str(a["sub"]), font=F("regular", 20), fill=DIM)
    return im.crop(im.getbbox() or (0, 0, 1, 1))


def name_chips(a: Dict[str, Any]) -> Image.Image:
    chips = list(a.get("chips") or [])[:5]
    lit = a.get("lit")
    fw, fs = F("bold", 28), F("regular", 18)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    widths = [max(_tw(probe, str(c[0]), fw), _tw(probe, str(c[1] if len(c) > 1 else ""), fs)) + 44 for c in chips]
    im, d = _canvas(sum(widths) + 24 * max(0, len(chips) - 1) + 8, 110)
    x = 4
    for i, (c, w) in enumerate(zip(chips, widths)):
        on = lit is None or int(lit) == i
        _panel(d, (x, 4, x + w, 70), fill=(12, 14, 18, 240), edge=L.WHITE if on else DIM, r=6, width=3 if on else 2)
        _centre(d, x + w / 2, 18, str(c[0]), fw, L.WHITE if on else DIM)
        if len(c) > 1:
            _centre(d, x + w / 2, 78, str(c[1]), fs, L.SOFT)
        x += w + 24
    return im


def strata(a: Dict[str, Any]) -> Image.Image:
    rows = list(a.get("rows") or [])[:5]
    im, d = _canvas(820, 100 * max(1, len(rows)) + (80 if a.get("key") else 20))
    tones = [(150, 116, 78, 255), (128, 98, 66, 255), (108, 82, 56, 255), (90, 68, 46, 255), (72, 54, 38, 255)]
    shown = max(1, int(math.ceil(len(rows) * _ease(_k(a))))) if rows else 0
    for i in range(shown):
        y = 10 + i * 100
        d.rectangle((0, y, 820, y + 96), fill=tones[i % len(tones)])
        d.text((20, y + 30), str(rows[i]), font=F("bold", 26), fill=(240, 228, 206, 255))
        tooth = _animal("tooth", 54)
        _paste_c(im, tooth, 520, y + 50)
    if a.get("key"):
        _centre(d, 410, 10 + 100 * len(rows) + 18, str(a["key"]).upper(), F("heavy", 34), L.ORANGE)
    return im


# ------------------------------------------------------------------------------------------------------------------ story / joke cards

def mystery(a: Dict[str, Any]) -> Image.Image:
    slots = list(a.get("slots") or ["", "", ""])[:5]
    animals = list(a.get("animals") or [""] * len(slots))
    lit = a.get("lit")
    cw, ch, gap = 200, 270, 30
    im, d = _canvas(len(slots) * cw + (len(slots) - 1) * gap + 10, ch + 10)
    for i, lab in enumerate(slots):
        x = 5 + i * (cw + gap)
        known = bool(lab)
        on = lit is not None and int(lit) == i
        edge = L.RED if known else ((120, 150, 170, 255) if not on else L.WHITE)
        _panel(d, (x, 5, x + cw, 5 + ch), fill=(22, 40, 54, 240), edge=edge, r=8, width=4 if (known or on) else 2)
        name = animals[i] if i < len(animals) else ""
        if known:
            _centre(d, x + cw / 2, 22, str(lab).upper(), _fit(d, str(lab).upper(), "bold", 24, cw - 20), L.WHITE)
            if name:
                _paste_c(im, _animal(name, cw - 40), x + cw / 2, 5 + ch * 0.55)
        else:
            _centre(d, x + cw / 2, 30, "?", F("heavy", 70), L.WHITE)
            if name:
                _paste_c(im, _animal(name, cw - 40, silhouette=True), x + cw / 2, 5 + ch * 0.6)
        _centre(d, x + cw / 2, ch - 34, f"{i + 1:02d}", F("bold", 22), L.SOFT)
    return im


def paper(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(520, 620)
    d.rectangle((10, 10, 510, 610), fill=PAPER)
    d.rectangle((10, 10, 510, 610), outline=(200, 194, 182, 255), width=2)
    j = str(a.get("journal", "")).upper()
    if j:
        d.text((40, 40), j, font=F("bold", 16), fill=(110, 112, 118, 255))
    f = F("serif", 34)
    y = 80
    for ln in _wrap(d, str(a.get("title", "")), f, 440)[:5]:
        d.text((40, y), ln, font=f, fill=L.INK)
        y += f.size * 1.2
    if a.get("authors"):
        d.text((40, y + 12), str(a["authors"]), font=F("regular", 18), fill=(90, 92, 98, 255))
        y += 50
    for i in range(9):
        w = 440 if i % 3 != 2 else 300
        d.rounded_rectangle((40, y + 20 + i * 30, 40 + w, y + 32 + i * 30), radius=6, fill=(206, 202, 192, 255))
    return im


def choose_move(a: Dict[str, Any]) -> Image.Image:
    opts = list(a.get("options") or ["FIGHT", "RUN", "HIDE"])[:5]
    sel = a.get("selected")
    im, d = _canvas(460, 120 + 56 * len(opts))
    _panel(d, (4, 4, 456, im.height - 4), fill=(16, 16, 14, 240), edge=(150, 130, 80, 255), r=8, width=3)
    _centre(d, 230, 26, str(a.get("title", "CHOOSE YOUR MOVE")).upper(), F("heavy", 28), L.ORANGE)
    shown = len(opts) if a.get("_k") is None else max(1, int(math.ceil(len(opts) * _k(a))))
    for i, o in enumerate(opts[:shown]):
        y = 90 + i * 56
        on = sel is not None and int(sel) == i
        if on:
            d.rectangle((24, y - 6, 436, y + 40), fill=(70, 60, 30, 255))
            d.polygon([(32, y + 8), (32, y + 26), (46, y + 17)], fill=L.ORANGE)
        d.text((60, y), str(o).upper(), font=F("bold", 30), fill=L.ORANGE if on else L.WHITE)
    return im


def quiz(a: Dict[str, Any]) -> Image.Image:
    opts = list(a.get("options") or [])[:4]
    im, d = _canvas(520, 120 + 80 * max(1, len(opts)))
    d.rounded_rectangle((4, 4, 516, im.height - 4), radius=14, fill=PAPER)
    d.text((32, 30), str(a.get("title", "")).upper(), font=_fit(d, str(a.get("title", "")).upper(), "bold", 26, 450), fill=L.INK)
    for i, o in enumerate(opts):
        text, mark = (o[0], o[1] if len(o) > 1 else "") if isinstance(o, (list, tuple)) else (o, "")
        y = 100 + i * 80
        d.text((32, y), str(text).upper(), font=F("bold", 28), fill=L.INK)
        d.rectangle((440, y - 4, 480, y + 36), outline=(150, 150, 150, 255), width=3)
        if mark == "x":
            d.line((444, y, 476, y + 32), fill=L.RED, width=5)
            d.line((476, y, 444, y + 32), fill=L.RED, width=5)
        elif mark == "check":
            d.line((444, y + 18, 456, y + 32), fill=(40, 160, 90, 255), width=6)
            d.line((456, y + 32, 480, y - 2), fill=(40, 160, 90, 255), width=6)
    return im


def playbook(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(780, 480)
    d.rectangle((0, 0, 780, 480), fill=BOARD)
    for i in range(0, 780, 60):
        d.line((i, 0, i - 200, 480), fill=(36, 54, 48, 255), width=18)
    _centre(d, 390, 20, str(a.get("title", "THE PLAYBOOK")).upper(), F("heavy", 40), CHALK)
    k = _ease(_k(a))
    tx, ty = 560, 250
    d.ellipse((tx - 34, ty - 34, tx + 34, ty + 34), outline=CHALK, width=4)
    _centre(d, tx, ty - 24, "T", F("heavy", 36), CHALK)
    for j, (x, y) in enumerate(((150, 140), (130, 250), (160, 360))):
        d.line((x - 16, y - 16, x + 16, y + 16), fill=CHALK, width=5)
        d.line((x + 16, y - 16, x - 16, y + 16), fill=CHALK, width=5)
        ex, ey = x + (tx - 40 - x) * k, y + (ty - y) * k
        steps = 14
        for s in range(steps):
            if s % 2:
                continue
            f0, f1 = s / steps, (s + 1) / steps
            mid = math.sin(math.pi * f0) * (j - 1) * 30
            d.line((x + 30 + (ex - x - 30) * f0, y + (ey - y) * f0 + mid, x + 30 + (ex - x - 30) * f1,
                    y + (ey - y) * f1 + mid), fill=CHALK, width=3)
    if a.get("step"):
        d.text((40, 420), str(a["step"]).upper(), font=F("bold", 28), fill=CHALK)
    return im


def crime_tape(a: Dict[str, Any]) -> Image.Image:
    text = (str(a.get("text") or "CRIME SCENE - DO NOT CROSS").upper() + "   ") * 6
    im = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    for ang, y in ((-14, 120), (12, 600)):
        band = Image.new("RGBA", (1800, 58), (246, 206, 40, 255))
        bd = ImageDraw.Draw(band)
        bd.text((20, 12), text, font=F("heavy", 30), fill=(20, 20, 20, 255))
        band = band.rotate(ang, expand=True, resample=Image.BICUBIC)
        im.alpha_composite(band, (int(640 - band.width / 2), int(y - band.height / 2)))
    return im


def wanted(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(440, 600)
    d.rectangle((10, 10, 430, 590), fill=(232, 214, 170, 255))
    d.rectangle((10, 10, 430, 590), outline=(150, 120, 80, 255), width=4)
    _centre(d, 220, 30, "WANTED", F("heavy", 72), (40, 30, 24, 255))
    d.rectangle((50, 130, 390, 340), fill=(214, 194, 150, 255))
    _paste_c(im, _animal(a.get("animal", "orca"), 300), 220, 235)
    y = 360
    for ln in _wrap(d, str(a.get("crime", "")).upper(), F("bold", 26), 360)[:3]:
        _centre(d, 220, y, ln, F("bold", 26), (40, 30, 24, 255))
        y += 34
    if a.get("reward"):
        for ln in _wrap(d, "REWARD: " + str(a["reward"]).upper(), F("bold", 22), 360)[:3]:
            _centre(d, 220, y + 16, ln, F("bold", 22), (170, 40, 30, 255))
            y += 28
    return im


def halo(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(300, 160)
    d.ellipse((40, 20, 260, 70), outline=(255, 214, 90, 255), width=8)
    glow = im.filter(ImageFilter.GaussianBlur(8))
    im = Image.alpha_composite(glow, im)
    d = ImageDraw.Draw(im)
    for x, y, s in ((20, 110, 10), (270, 100, 12), (150, 140, 8), (60, 20, 7)):
        d.polygon([(x, y - s), (x + s * 0.3, y - s * 0.3), (x + s, y), (x + s * 0.3, y + s * 0.3), (x, y + s),
                   (x - s * 0.3, y + s * 0.3), (x - s, y), (x - s * 0.3, y - s * 0.3)], fill=(255, 240, 180, 255))
    return im


def bunting(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(1200, 140)
    pts = [(x, 20 + 40 * math.sin(math.pi * x / 1200)) for x in range(0, 1201, 20)]
    d.line(pts, fill=(220, 220, 220, 255), width=3)
    cols = [L.RED, L.ORANGE, (80, 170, 220, 255), (240, 220, 80, 255), (100, 200, 140, 255)]
    for i in range(12):
        x = 40 + i * 100
        y = 20 + 40 * math.sin(math.pi * x / 1200)
        d.polygon([(x - 28, y), (x + 28, y), (x, y + 60)], fill=cols[i % len(cols)])
    return im


def shop(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(520, 640)
    d.rounded_rectangle((10, 10, 510, 630), radius=16, fill=(248, 248, 246, 255))
    d.rectangle((40, 40, 480, 330), fill=(234, 234, 230, 255))
    sp = _animal(a.get("animal", "tooth"), 220 if a.get("animal", "tooth") == "tooth" else 380)
    _paste_c(im, sp, 260, 185)
    f = F("heavy", 32)
    y = 350
    for ln in _wrap(d, str(a.get("title", "")).upper(), f, 440)[:2]:
        d.text((40, y), ln, font=f, fill=L.INK)
        y += f.size * 1.15
    for i in range(5):                                             # drawn stars (fonts may lack the glyph)
        cx, cy, ro, ri = 54 + i * 32, y + 20, 13, 5.5
        d.polygon([(cx + (ro if j % 2 == 0 else ri) * math.sin(math.pi * j / 5),
                    cy - (ro if j % 2 == 0 else ri) * math.cos(math.pi * j / 5)) for j in range(10)], fill=(240, 170, 30, 255))
    d.text((40, y + 46), str(a.get("price", "$249.99")), font=F("heavy", 52), fill=L.INK)
    d.rounded_rectangle((40, 560, 480, 610), radius=25, fill=L.RED)
    _centre(d, 260, 568, "ADD TO CART", F("heavy", 28), L.WHITE)
    return im


def diver_hud(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(560, 150)
    if a.get("tip"):
        d.ellipse((6, 6, 30, 30), fill=L.RED)
        d.text((40, 4), str(a["tip"]).upper(), font=F("bold", 22), fill=L.ORANGE)
    _panel(d, (6, 44, 300, 144), fill=(10, 16, 22, 220), edge=(100, 120, 130, 255), r=10)
    d.text((22, 52), "DEPTH", font=F("bold", 14), fill=DIM)
    d.text((22, 70), str(a.get("depth", "12 m")), font=F("heavy", 50), fill=L.WHITE)
    d.text((170, 52), "AIR", font=F("bold", 14), fill=DIM)
    air = max(0.0, min(1.0, float(a.get("air", 0.7))))
    c = GREEN if air > 0.4 else (L.ORANGE if air > 0.2 else L.RED)
    d.rounded_rectangle((170, 76, 284, 96), radius=6, fill=(40, 56, 66, 255))
    d.rounded_rectangle((170, 76, 170 + max(12, 114 * air), 96), radius=6, fill=c)
    d.text((170, 104), f"{int(air * 200)} bar", font=F("regular", 16), fill=L.SOFT)
    return im


def duel(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(820, 320)
    for i, side in enumerate(("left", "right")):
        v = a.get(side) or (["orca", "PREDATOR"] if i == 0 else ["humpback", "VICTIM"])
        x = 10 + i * 420
        _panel(d, (x, 10, x + 380, 300), fill=(24, 30, 38, 236), edge=(60, 70, 84, 255), r=16)
        _paste_c(im, _animal(v[0], 300, face="right" if i == 0 else "left"), x + 190, 130)
        _centre(d, x + 190, 240, str(v[1]).upper(), F("heavy", 34), L.WHITE)
    return im


def silhouettes(a: Dict[str, Any]) -> Image.Image:
    rows = list(a.get("rows") or [])[:5]
    im, d = _canvas(820, 140 + 100 * max(1, len(rows)))
    d.rectangle((0, 0, 820, im.height), fill=PAPER)
    _centre(d, 410, 24, str(a.get("title", "")).upper(), F("heavy", 44), L.INK)
    if a.get("sub"):
        _centre(d, 410, 80, str(a["sub"]), F("regular", 20), (100, 100, 100, 255))
    for i, r in enumerate(rows):
        y = 150 + i * 100
        sp = _animal(r[0], 380, silhouette=True)
        _paste_c(im, sp, 260, y)
        d.text((520, y - 16), str(r[1]).upper(), font=F("bold", 26), fill=L.INK)
    return im


def comments(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(740, 230)
    d.rounded_rectangle((6, 6, 734, 224), radius=16, fill=(244, 244, 242, 255))
    d.text((34, 26), "COMMENTS", font=F("bold", 18), fill=(40, 40, 44, 255))
    d.rounded_rectangle((34, 66, 706, 140), radius=10, fill=(232, 232, 230, 255))
    d.ellipse((46, 80, 92, 126), fill=(120, 170, 200, 255))
    txt = str(a.get("text", ""))
    shown = txt[: int(round(len(txt) * _k(a)))] if a.get("_k") is not None else txt
    d.text((108, 90), shown, font=_fit(d, txt, "regular", 26, 580), fill=(30, 30, 34, 255))
    return im


def watch_next(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(1100, 420)
    d.ellipse((20, 30, 70, 80), fill=(110, 70, 160, 255))
    _centre(d, 45, 40, str(a.get("channel", "OC"))[:2].upper(), F("heavy", 24), L.WHITE)
    d.text((86, 42), str(a.get("channel", "OCEAN")).upper(), font=F("bold", 22), fill=L.WHITE)
    d.text((20, 150), "WATCH", font=F("heavy", 64), fill=L.WHITE)
    d.text((20, 220), "NEXT", font=F("heavy", 64), fill=L.ORANGE)
    if a.get("line"):
        d.text((20, 300), str(a["line"]), font=F("regular", 22), fill=L.SOFT)
    d.polygon([(400, 190), (400, 240), (440, 215)], fill=L.ORANGE)
    for x in range(500, 1090, 24):
        d.line((x, 60, x + 12, 60), fill=DIM, width=3)
        d.line((x, 380, x + 12, 380), fill=DIM, width=3)
    for y in range(60, 381, 24):
        d.line((500, y, 500, y + 12), fill=DIM, width=3)
        d.line((1090, y, 1090, y + 12), fill=DIM, width=3)
    return im


# ------------------------------------------------------------------------------------------------------------------ story scenes
# Two full-frame scenes from the reference cold opens: the top-down map where a group circles a place and then leaves
# (a counter running down), and the size check beside an everyday thing (a diver, a car, a bus) with measure bars.

_ISLAND_CACHE: Dict[Tuple[int, int], Image.Image] = {}


def _island_base(seed: int = 7) -> Image.Image:
    """Top-down sea: depth bands that get lighter towards a rocky island in the middle."""
    key = (seed, L.W)
    if key in _ISLAND_CACHE:
        return _ISLAND_CACHE[key]
    import random
    rnd = random.Random(seed)
    w, h = 1280, 720
    im = Image.new("RGBA", (w, h), (10, 44, 64, 255))
    d = ImageDraw.Draw(im)
    cx, cy = 640, 350
    base = [rnd.uniform(0.85, 1.15) for _ in range(14)]
    def ring(rx: float, ry: float, wob: float):
        pts = []
        for i in range(56):
            a = 2 * math.pi * i / 56
            j = base[int(i / 4) % 14]
            r = 1 + (j - 1) * wob
            pts.append((cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)))
        return pts
    bands = [(760, 520, (14, 56, 80)), (600, 410, (18, 68, 94)), (470, 320, (22, 82, 108)), (360, 250, (28, 98, 122)),
             (270, 190, (36, 116, 134)), (205, 146, (48, 136, 146))]
    for rx, ry, col in bands:
        d.polygon(ring(rx, ry, 1.0), fill=col + (255,))
    rock = ring(150, 112, 2.2)
    d.polygon([(x + 6, y + 8) for x, y in rock], fill=(12, 30, 38, 160))
    d.polygon(rock, fill=(120, 98, 72, 255), outline=(24, 22, 20, 255))
    d.line(rock + [rock[0]], fill=(24, 22, 20, 255), width=4)
    for _ in range(70):                                    # rocky texture
        x, y = cx + rnd.uniform(-120, 120), cy + rnd.uniform(-85, 85)
        if ((x - cx) / 125) ** 2 + ((y - cy) / 92) ** 2 < 1:
            r = rnd.uniform(2, 6)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(78, 62, 46, 255) if rnd.random() < 0.6 else (150, 128, 98, 255))
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse((-200, -160, w + 200, h + 160), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(120))
    dark = Image.new("RGBA", (w, h), (2, 8, 14, 255))
    im = Image.composite(im, dark, vig)
    _ISLAND_CACHE[key] = im
    return im


_ICON_CACHE: Dict[str, Image.Image] = {}


def _top_icon(name: str) -> Image.Image:
    """A small top-down animal pointing right (+x): spindle body, two side fins, a tail."""
    if name in _ICON_CACHE:
        return _ICON_CACHE[name]
    from . import art_flow as AF
    top = AF.path(name, "top")
    if top is not None:                                    # the painted top-down animal from the library
        src = Image.open(top).convert("RGBA")
        out = src.resize((72, max(1, int(src.height * 72 / max(1, src.width)))), Image.LANCZOS)
        _ICON_CACHE[name] = out
        return out
    ss = 4
    w, h = 64 * ss, 34 * ss
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    dark = name in ("orca",)
    body_c = (26, 28, 32, 255) if dark else (196, 204, 210, 255)
    edge = (14, 18, 22, 255)
    cy = h / 2
    body = [(62, 17), (56, 13.5), (44, 11.5), (30, 12.5), (18, 14.5), (10, 16.2), (10, 17.8), (18, 19.5), (30, 21.5),
            (44, 22.5), (56, 20.5)]
    fins = [[(40, 12.5), (33, 2), (30, 3), (33, 13)], [(40, 21.5), (33, 32), (30, 31), (33, 21)]]
    tail = [(12, 17), (2, 9), (0, 10), (5, 17), (0, 24), (2, 25)]
    S_ = lambda pts: [(x * ss, y * ss) for x, y in pts]
    for poly in fins + [tail, body]:
        d.polygon(S_(poly), fill=body_c, outline=edge)
        d.line(S_(poly) + [S_(poly)[0]], fill=edge, width=ss * 2)
    d.line(S_([(56, 17), (22, 17)]), fill=(120, 130, 138, 255) if not dark else (70, 74, 80, 255), width=ss)
    out = im.resize((64, 34), Image.LANCZOS)
    _ICON_CACHE[name] = out
    return out


def island_map(a: Dict[str, Any]) -> Image.Image:
    """Full frame. args: count, label ("tagged sharks"), animal, year, place, dur (s), leave (s after start, or None).
    The group circles the island; from `leave` each one swims straight out and the counter runs down to 0."""
    import random
    k = _k(a)
    dur = float(a.get("dur", 6.0))
    t = k * dur
    n = max(1, min(24, int(a.get("count", 12))))
    leave = a.get("leave")
    im = _island_base().copy()
    rnd = random.Random(11)
    icon = _top_icon(str(a.get("animal", "great_white")))
    here = 0
    for i in range(n):
        rx = rnd.uniform(230, 360)
        ry = rx * rnd.uniform(0.62, 0.74)
        a0 = 2 * math.pi * i / n + rnd.uniform(-0.2, 0.2)
        sp = rnd.uniform(0.32, 0.5) * (1 if i % 5 else -1)
        ang = a0 + sp * t
        x, y = 640 + rx * math.cos(ang), 350 + ry * math.sin(ang)
        hd = math.atan2(ry * math.cos(ang) * sp, -rx * math.sin(ang) * sp)          # heading along the orbit
        alpha = 1.0
        if leave is not None:
            tl = float(leave) + i * (min(2.2, dur - float(leave) - 1.0) / max(1, n))
            if t > tl:                                                     # swims straight out, away from the island
                out_t = t - tl
                hd = math.atan2(y - 350, x - 640)
                x += math.cos(hd) * out_t * 260
                y += math.sin(hd) * out_t * 260
                alpha = max(0.0, 1 - out_t / 1.4)
        if alpha > 0.05:
            here += 1 if alpha > 0.5 else 0
            sp_im = icon.rotate(-math.degrees(hd), expand=True, resample=Image.BICUBIC)
            if alpha < 1:
                sp_im.putalpha(sp_im.getchannel("A").point(lambda v: int(v * alpha)))
            im.alpha_composite(sp_im, (int(x - sp_im.width / 2), int(y - sp_im.height / 2)))
    d = ImageDraw.Draw(im)
    num = str(here)
    fn, fl = F("heavy", 70), F("bold", 24)
    col = L.ORANGE if here else L.RED
    d.text((40, 26), num, font=fn, fill=col)
    d.text((40 + _tw(d, num, fn) + 16, 26 + fn.size * 0.52), str(a.get("label", "")).upper(), font=fl, fill=L.WHITE)
    if a.get("year"):
        _centre(d, 640, 630, str(a["year"]), F("heavy", 52), L.ORANGE)
    if a.get("place"):
        _centre(d, 640, 352 + 150, str(a["place"]), F("regular", 20), L.SOFT)
    return im


def _car(d: ImageDraw.ImageDraw, x: float, y: float, w: float) -> None:
    """A plain sedan side-on, wheels on y (ground), w long."""
    u = w / 100
    body = [(0, -12), (2, -19), (22, -21), (33, -31), (64, -31), (78, -21), (98, -19), (100, -12), (100, -6), (0, -6)]
    P = [(x + px * u, y + py * u) for px, py in body]
    d.polygon(P, fill=(196, 202, 208, 255), outline=(20, 24, 28, 255))
    d.line(P + [P[0]], fill=(20, 24, 28, 255), width=max(2, int(u * 1.2)))
    for wx0, wx1 in ((37, 49), (52, 76)):
        d.polygon([(x + wx0 * u, y - 29 * u), (x + wx1 * u, y - 29 * u), (x + (wx1 + 2) * u, y - 21 * u), (x + (wx0 - 3) * u, y - 21 * u)],
                  fill=(120, 138, 152, 255))
    for cx in (20, 80):
        r = 7 * u
        d.ellipse((x + cx * u - r, y - 7 * u - r, x + cx * u + r, y - 7 * u + r), fill=(22, 24, 28, 255))
        d.ellipse((x + cx * u - r * 0.45, y - 7 * u - r * 0.45, x + cx * u + r * 0.45, y - 7 * u + r * 0.45), fill=(150, 156, 162, 255))


def _bus(d: ImageDraw.ImageDraw, x: float, y: float, w: float) -> None:
    u = w / 100
    d.rounded_rectangle((x, y - 30 * u, x + w, y - 6 * u), radius=int(3 * u), fill=(214, 170, 60, 255), outline=(20, 24, 28, 255),
                        width=max(2, int(u)))
    for i in range(8):
        wx = x + (6 + i * 11.5) * u
        d.rectangle((wx, y - 27 * u, wx + 8 * u, y - 19 * u), fill=(120, 138, 152, 255))
    for cx in (15, 85):
        r = 5 * u
        d.ellipse((x + cx * u - r, y - 6 * u - r, x + cx * u + r, y - 6 * u + r), fill=(22, 24, 28, 255))


REF_SIZES = {"diver": 1.8, "car": 4.5, "bus": 12.0}


def size_compare(a: Dict[str, Any]) -> Image.Image:
    """Full frame (transparent over the stage): the animal above an everyday thing drawn to the same scale, each with a
    measure bar. args: animal, metres, label ("5 m · 1,100+ kg"), ref ("diver" | "car" | "bus", picked by size if absent)."""
    k = _ease(_k(a))
    m = max(0.3, float(a.get("metres", 5.0)))
    ref = a.get("ref") or ("diver" if m < 3 else "car" if m < 9 else "bus")
    rm = REF_SIZES[ref]
    big = max(m, rm)
    px_per_m = 700 / big
    im = Image.new("RGBA", (1280, 720), (0, 0, 0, 255))      # its own dark water: the comparison stands alone, like the reference
    d = ImageDraw.Draw(im)
    for y in range(720):
        k2 = y / 719
        c = tuple(int(L.WATER_MID[i] * (1 - k2) + L.WATER_DEEP[i] * k2) for i in range(3)) + (255,)
        d.line((0, y, 1280, y), fill=c)
    aw = int(m * px_per_m)
    animal = A.draw(str(a.get("animal", "great_white")), max(60, aw))
    ax = 190
    ay = 200
    im.alpha_composite(animal, (ax, int(ay - animal.height / 2)))
    rw = rm * px_per_m
    gy = 610
    from . import art_flow as AF
    ref_art = AF.path(ref, "side") if ref in ("car", "bus") else None
    if ref_art is not None:                               # the painted car / bus from the library, to scale
        src = Image.open(ref_art).convert("RGBA")
        pic = src.resize((max(1, int(rw)), max(1, int(src.height * rw / max(1, src.width)))), Image.LANCZOS)
        im.alpha_composite(pic, (int(ax), int(gy - pic.height)))
    elif ref == "car":
        _car(d, ax, gy, rw)
    elif ref == "bus":
        _bus(d, ax, gy, rw)
    else:
        diver = A.draw("diver", max(40, int(rw)))
        im.alpha_composite(diver, (ax, int(gy - diver.height)))
    for (x0, length, y, text) in ((ax, aw * k, ay + animal.height / 2 + 18, str(a.get("label", ""))),
                                  (ax, rw * k, gy + 30, str(a.get("ref_label", "")))):
        if length < 4:
            continue
        x1 = x0 + length
        d.line((x0, y, x1, y), fill=(232, 210, 120, 255), width=3)
        for xx, sgn in ((x0, 1), (x1, -1)):
            d.polygon([(xx, y), (xx + 12 * sgn, y - 7), (xx + 12 * sgn, y + 7)], fill=(232, 210, 120, 255))
        if text and k > 0.6:                              # the label sits after the bar's end, clear of both drawings
            ft = F("bold", 26)
            d.text((x1 + 18, y - ft.size * 0.62), text, font=ft, fill=(240, 226, 160, 255))
    return im


KINDS = {
    "number_hero": number_hero, "dot_grid": dot_grid, "icon_rows": icon_rows, "standoff": standoff, "progress": progress,
    "bar_race": bar_race, "meters": meters, "counter": counter, "calendar": calendar, "clock": clock, "size_bar": size_bar,
    "callout": callout, "name_tag": name_tag, "name_chips": name_chips, "strata": strata,
    "mystery": mystery, "paper": paper, "choose_move": choose_move, "quiz": quiz, "playbook": playbook,
    "crime_tape": crime_tape, "wanted": wanted, "halo": halo, "bunting": bunting, "shop": shop, "diver_hud": diver_hud,
    "duel": duel, "silhouettes": silhouettes, "comments": comments, "watch_next": watch_next,
    "island_map": island_map, "size_compare": size_compare,
}
ANIMATED = ("number_hero", "dot_grid", "icon_rows", "standoff", "progress", "bar_race", "meters", "clock", "size_bar",
            "callout", "name_tag", "strata", "choose_move", "playbook", "comments", "island_map", "size_compare")
FULL_FRAME = ("crime_tape",)


def register_all() -> None:
    from aviation import stage as AV
    for name, fn in KINDS.items():
        AV.register("ocean_" + name, fn)
