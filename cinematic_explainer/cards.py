"""Cinematic Explainer cards: every card is a pure function card(t, dur, params) -> RGBA frame, so the same t always gives the same pixels.

    kicker      red section tag, top-left
    source      paper source card; words darken as they are spoken; a yellow highlighter wipes under the key phrase
    number      figure counts up, label fades in, a red rule draws left to right
    list        title, then one row per narrated item
    portrait    circle portrait with ring and red name plate (portrait supplied by the caller; none -> no card)
    shot_head   short headline lower third for a footage shot
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from . import look as L
from .look import H, W


def kicker(t: float, dur: float, p: dict) -> Image.Image:
    img = L.blank()
    d = ImageDraw.Draw(img)
    f = L.font("bold", 13)
    text = str(p.get("text", "")).upper()
    w = int(L.spaced_width(d, text, f, 0.12)) + 20
    d.rectangle([24, 18, 24 + w, 18 + 24], fill=L.RED)
    L.spaced(d, (34, 23), text, f, L.WHITE, 0.12)
    return L.fade(img, L.card_alpha(t, dur))


def _wrap(d, words: Sequence[str], f, width: int) -> List[List[int]]:
    """Indexes of the words per line."""
    lines: List[List[int]] = [[]]
    for i, w in enumerate(words):
        trial = " ".join(words[j] for j in lines[-1] + [i])
        if lines[-1] and d.textlength(trial, font=f) > width:
            lines.append([i])
        else:
            lines[-1].append(i)
    return lines


def source(t: float, dur: float, p: dict) -> Image.Image:
    """p: outlet, date, words [str], times [s from card start, one per word], mark (first, last word index of the key phrase)."""
    img = L.blank()
    d = ImageDraw.Draw(img)
    a = L.card_alpha(t, dur)
    lift = int(16 * (1 - L.ease_out(t / L.CARD_IN_S)))
    fh, fo, fc = L.font("serif", 31), L.font("serif", 24), L.font("bold", 11)
    words = list(p["words"])
    times = list(p["times"])
    cw, pad = 800, 30
    lines = _wrap(d, words, fh, cw - 2 * pad)
    lh = 40
    ch = 62 + lh * len(lines) + 22
    x0, y0 = (W - cw) // 2, int(H * 0.52) - ch // 2 + lift
    d.rectangle([x0, y0, x0 + cw, y0 + ch], fill=L.PAPER)
    d.rectangle([x0, y0, x0 + cw, y0 + 5], fill=L.RED)
    d.text((x0 + pad, y0 + 20), str(p.get("outlet", "")), font=fo, fill=L.INK)
    date = str(p.get("date", "")).upper()
    dw = int(L.spaced_width(d, date, fc, 0.1)) + 18
    d.rectangle([x0 + cw - pad - dw, y0 + 24, x0 + cw - pad, y0 + 44], fill=(28, 28, 32, 255))
    L.spaced(d, (x0 + cw - pad - dw + 9, y0 + 29), date, fc, L.WHITE, 0.1)
    mark = p.get("mark")
    y = y0 + 62
    for line in lines:
        x = x0 + pad
        bar_x0: Optional[int] = None
        bar_x1 = 0
        for i in line:
            w = d.textlength(words[i] + " ", font=fh)
            k = L.ramp(t, times[i], L.WORD_S)
            if mark and mark[0] <= i <= mark[1] and k > 0:
                # one continuous highlighter per line: it follows the words as they are said
                if bar_x0 is None:
                    bar_x0 = int(x) - 2
                bar_x1 = int(x + (d.textlength(words[i], font=fh)) * k) + 2
            x += w
        if bar_x0 is not None:
            d.rectangle([bar_x0, y + 8, bar_x1, y + lh - 6], fill=(255, 213, 0, 235))
        x = x0 + pad
        for i in line:
            k = L.ramp(t, times[i], L.WORD_S)
            d.text((x, y), words[i], font=fh, fill=L.lerp_color(L.GHOST, L.INK, k))
            x += d.textlength(words[i] + " ", font=fh)
        y += lh
    return L.fade(img, a)


def number(t: float, dur: float, p: dict) -> Image.Image:
    """p: value (int), prefix ('x'), label, sub, colour ('red'|'yellow')."""
    img = L.blank()
    d = ImageDraw.Draw(img)
    a = L.card_alpha(t, dur)
    col = L.YELLOW if p.get("colour") == "yellow" else L.RED
    value = int(p["value"])
    k = L.ramp(t, 0.15, L.COUNT_S)
    shown = max(1, int(round(value * L.ease_out(k)))) if k > 0 else 0
    fy = L.font("heavy", 150)
    fp = L.font("heavy", 70)
    fl = L.font("heavy", 40)
    fs = L.font("bold", 15)
    x, y = 64, int(H * 0.40)
    prefix = str(p.get("prefix", ""))
    if shown:
        px = x
        if prefix:
            d.text((x, y + 70), prefix, font=fp, fill=col)
            px = x + int(d.textlength(prefix, font=fp)) + 6
        d.text((px, y), str(shown), font=fy, fill=col)
        nw = int(d.textlength(str(value), font=fy))
        lx = px + nw + 30
        la = L.ramp(t, 0.15 + L.COUNT_S, 0.2)
        lab = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lab)
        ld.text((lx, y + 48), str(p.get("label", "")).upper(), font=fl, fill=L.WHITE)
        sub = str(p.get("sub", ""))
        if sub:
            ld.text((lx, y + 100), sub, font=fs, fill=L.GREY)
        img = Image.alpha_composite(img, L.fade(lab, la))
        d = ImageDraw.Draw(img)
        rk = L.ramp(t, 0.15 + L.COUNT_S + 0.1, L.RULE_S)
        d.rectangle([x, y + 178, x + int(760 * L.ease_out(rk)), y + 180], fill=L.RED)
    return L.fade(img, a)


def list_card(t: float, dur: float, p: dict) -> Image.Image:
    """p: title, items [str], times [s from card start, one per item]."""
    img = L.blank()
    d = ImageDraw.Draw(img)
    a = L.card_alpha(t, dur)
    d.text((40, 66), str(p["title"]).upper(), font=L.font("heavy", 34), fill=L.WHITE)
    fr = L.font("bold", 17)
    fn = L.font("heavy", 17)
    for i, (item, ti) in enumerate(zip(p["items"], p["times"])):
        k = L.ramp(t, ti, L.CARD_IN_S)
        if k <= 0:
            continue
        row = L.blank()
        rd = ImageDraw.Draw(row)
        y = 128 + i * 46
        rd.rectangle([40, y, 40 + 520, y + 38], fill=(14, 22, 36, 205))
        rd.text((54, y + 8), str(i + 1), font=fn, fill=L.YELLOW)
        rd.text((84, y + 9), str(item).upper(), font=fr, fill=L.WHITE)
        img = Image.alpha_composite(img, L.fade(row, k))
    return L.fade(img, a)


def portrait(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """p: image (PIL image or None), name, role. No image -> None: the planner must not show an identity it cannot prove."""
    src = p.get("image")
    if src is None:
        return None
    a = L.card_alpha(t, dur)
    k = L.ease_out(t / L.CARD_IN_S)
    size = int(250 * (0.94 + 0.06 * k))
    face = src.convert("RGB").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    img = L.blank()
    cx, cy = W // 2, int(H * 0.40)
    ring = Image.new("RGBA", (size + 12, size + 12), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([0, 0, size + 11, size + 11], fill=(255, 255, 255, 255))
    img.paste(ring, (cx - size // 2 - 6, cy - size // 2 - 6), ring)
    img.paste(face, (cx - size // 2, cy - size // 2), mask)
    d = ImageDraw.Draw(img)
    fn, fr = L.font("heavy", 24), L.font("bold", 15)
    name = str(p.get("name", "")).upper()
    nw = int(L.spaced_width(d, name, fn, 0.05)) + 36
    ny = cy + size // 2 + 14
    d.rectangle([cx - nw // 2, ny, cx + nw // 2, ny + 42], fill=L.RED)
    L.spaced(d, (cx - nw // 2 + 18, ny + 8), name, fn, L.WHITE, 0.05)
    role = str(p.get("role", ""))
    d.text((cx - d.textlength(role, font=fr) / 2, ny + 54), role, font=fr, fill=L.GREY)
    return L.fade(img, a)


def shot_head(t: float, dur: float, p: dict) -> Image.Image:
    img = L.blank()
    d = ImageDraw.Draw(img)
    f = L.font("heavy", 22)
    text = str(p.get("text", "")).upper()
    w = int(L.spaced_width(d, text, f, 0.04)) + 40
    x = 38
    y = H - 96
    # the words type in: one character group per frame step, never faster than the card fade
    n = len(text)
    shown = text[: max(1, int(n * L.ramp(t, 0.1, 0.5)))]
    d.rectangle([x, y, x + w, y + 40], fill=(10, 10, 12, 235))
    d.rectangle([x, y, x + 5, y + 40], fill=L.YELLOW)
    L.spaced(d, (x + 20, y + 8), shown, f, L.WHITE, 0.04)
    return L.fade(img, L.card_alpha(t, dur))


CARDS: Dict[str, Callable] = {"kicker": kicker, "source": source, "number": number, "list": list_card, "portrait": portrait,
                              "shot_head": shot_head}
