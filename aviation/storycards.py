"""Story-mode stage pieces (docs/aviation/MASTER_PLAN.md S2, S3; step 2): logo cards on a timeline bar with a moving dot.
Registered as stage sprite kinds, so they float, glide and leave like every other sticker.

    logo_card sprite  args {airline, name?, years?}         white rounded card: tail-fin mark + name + 'founded–defunct'
    timeline_bar      args {start, end, width?}             white bar with year ticks
    timeline_dot      args {}                               yellow dot that glides along the bar
    eras(airline_id) -> [(name, from, to)]                  the airline's names over time, from the catalog (previous_names + now)
    add_timeline(stage, at, eras, airline, step=1.6, y=560) -> ids   bar, then one card per era popping in above its years,
                                                            the dot gliding era to era and the year badge ticking with it
Names, years and colours come only from the catalog or the narration; the mark is drawn from the livery, never a copied logo.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from . import catalog as C
from . import stage as G
from . import style as S


def _years_text(a: Dict[str, Any]) -> str:
    y = str(a.get("years") or "").strip()
    if y:
        return y
    al = C.get_airline(a.get("airline", "")) or {}
    f, d = al.get("founded"), al.get("defunct")
    return f"{f}–{d}" if f and d else (f"since {f}" if f else "")


def _mark(airline: str, size: int) -> Image.Image:
    try:
        from . import stickers
        return stickers.tail_mark(airline, size)
    except Exception:
        al = C.get_airline(airline) or {}
        cols = [c for c in (al.get("colors") or al.get("colours") or []) if isinstance(c, str)]
        col = cols[0] if cols else "#3060a0"
        rgb = tuple(int(col.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(im).polygon([(size * .2, size * .95), (size * .55, size * .05), (size * .85, size * .05),
                                    (size * .7, size * .95)], fill=rgb)
        return im


def _first_year(years: str) -> int:
    m = re.search(r"(19|20)\d\d", str(years or ""))
    return int(m.group(0)) if m else 0


def logo_card(a: Dict[str, Any]) -> Image.Image:
    """The card, with its airline's aircraft of that era perched on its top edge (the reference never shows a bare card)."""
    card = _logo_card(a)
    if a.get("plane") is False or not a.get("airline"):
        return card
    try:
        from . import stickers as SK
        from .story import era_type
        typ = a.get("type") or era_type(_first_year(_years_text(a)))
        from . import sticker_flow as SF
        pl = SK.die_cut(SF.aircraft_image(typ, a["airline"], int(card.width * 0.8)), 6)
    except Exception:
        return card
    lift = int(pl.height * 0.86)                       # the plane stands on the card's top edge: only its belly overlaps
    out = Image.new("RGBA", (max(card.width, pl.width + card.width // 6), card.height + lift), (0, 0, 0, 0))
    out.alpha_composite(card, (0, lift))
    out.alpha_composite(pl, (min(out.width - pl.width, card.width // 6), 0))
    return out


def _logo_card(a: Dict[str, Any]) -> Image.Image:
    """White rounded card in one row, as in the reference: the tail-fin mark on the left, the name (bold, up to two lines) and
    the years (grey) on the right."""
    al = C.get_airline(a.get("airline", "")) or {}
    name = str(a.get("name") or al.get("name") or a.get("airline", "")).strip()
    years = _years_text(a)
    w = int(a.get("width", 420))
    mark = int(w * 0.24)
    pad = 22
    tx = pad + mark + 18
    fn, fy = S.font("title", 32), S.font("body", 22)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    words, lines, cur = name.replace("-", "- ").split(), [], ""     # 'Malaysia-Singapore' may break after its hyphen
    for wd in words:
        t = (cur + ("" if cur.endswith("-") else " ") + wd).strip()
        if probe.textlength(t, font=fn) > w - tx - pad and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = t
    lines.append(cur)
    while len(lines) > 2 and fn.size > 20:               # never three lines: the type shrinks instead
        fn = S.font("title", int(fn.size * 0.86 / S.scale()))
        lines, cur = [], ""
        for wd in words:
            t = (cur + ("" if cur.endswith("-") else " ") + wd).strip()
            if probe.textlength(t, font=fn) > w - tx - pad and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = t
        lines.append(cur)
    lh = int(fn.size * 1.12)
    text_h = len(lines) * lh + (int(fy.size * 1.35) if years else 0)
    h = max(mark + 2 * pad, text_h + 2 * pad)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=22, fill=S.WHITE)
    m = _mark(a.get("airline", ""), mark)
    im.alpha_composite(m, (pad, (h - m.height) // 2))
    y = (h - text_h) // 2
    for ln in lines:
        d.text((tx, y), ln, font=fn, fill=S.INK)
        y += lh
    if years:
        d.text((tx, y + 2), years, font=fy, fill=S.GREY)
    return im


def bar_x(year: float, start: float, end: float, width: float, cx: float = 640.0) -> float:
    if end <= start:
        return cx
    return cx - width / 2 + (min(max(year, start), end) - start) / (end - start) * width


def timeline_bar(a: Dict[str, Any]) -> Image.Image:
    start, end = int(a["start"]), int(a["end"])
    w = int(a.get("width", 1040))
    f = S.font("body", 20)
    im = Image.new("RGBA", (w + 60, 70), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((30, 14, 30 + w, 22), radius=4, fill=S.WHITE)
    span = max(1, end - start)
    step = next(s for s in (1, 2, 5, 10, 20, 25, 50) if span / s <= 10)
    y0 = (start // step) * step
    for yr in range(y0, end + 1, step):
        if yr < start:
            continue
        x = 30 + (yr - start) / span * w
        d.line((x, 8, x, 28), fill=S.WHITE, width=3)
        lab = str(yr)
        d.text((x - d.textlength(lab, font=f) / 2, 36), lab, font=f, fill=S.GREY)
    return im


def timeline_dot(a: Dict[str, Any]) -> Image.Image:
    r = int(a.get("r", 16))
    im = Image.new("RGBA", (r * 2 + 2, r * 2 + 2), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((1, 1, r * 2, r * 2), fill=S.YELLOW, outline=S.WHITE, width=3)
    return im


def caption(a: Dict[str, Any]) -> Image.Image:
    """The line's own words under the stickers (the reference's 'Would not actually start flying up until 1947'): white bold,
    centred, wrapped to two lines at most; an optional small grey subtitle under it."""
    text = str(a.get("text") or "").strip()
    sub = str(a.get("sub") or "").strip()
    w = int(a.get("width", 900))
    f, fs = S.font("title", int(a.get("size", 40))), S.font("body", 22)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines, cur = [], ""
    for wd in text.split():
        t = (cur + " " + wd).strip()
        if probe.textlength(t, font=f) > w and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = t
    lines.append(cur)
    lines = lines[:2]
    lh = int(f.size * 1.18)
    h = len(lines) * lh + (int(fs.size * 1.6) if sub else 0) + 12
    im = Image.new("RGBA", (w + 20, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y = 4
    for ln in lines:
        d.text(((w + 20 - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=S.WHITE, stroke_width=2, stroke_fill=(0, 0, 0, 200))
        y += lh
    if sub:
        d.text(((w + 20 - d.textlength(sub, font=fs)) / 2, y + 2), sub, font=fs, fill=S.GREY)
    return im


def backdrop(a: Dict[str, Any]) -> Image.Image:
    """A real photo behind the stage (the reference puts its stickers over archive pictures): cover-fit a little larger than the
    frame (so it can pan), softly blurred and darkened so the stickers stay the subject. Missing / unreadable -> nothing."""
    from PIL import ImageEnhance, ImageFilter
    try:
        im = Image.open(a["image"]).convert("RGB")
    except Exception:
        return Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    W_, H_ = int(1280 * 1.1), int(720 * 1.1)
    f = max(W_ / im.width, H_ / im.height)
    im = im.resize((max(W_, int(im.width * f)), max(H_, int(im.height * f))), Image.LANCZOS)
    x0, y0 = (im.width - W_) // 2, (im.height - H_) // 2
    im = im.crop((x0, y0, x0 + W_, y0 + H_)).filter(ImageFilter.GaussianBlur(float(a.get("blur", 2.5))))
    im = ImageEnhance.Brightness(im).enhance(float(a.get("dim", 0.38)))
    im = ImageEnhance.Color(im).enhance(0.75)
    out = im.convert("RGBA")
    if a.get("credit"):
        d = ImageDraw.Draw(out)
        f2 = S.font("body", 15)
        d.text((int(1280 * 0.05) + 40, H_ - int(720 * 0.05) - 34), f"Credits: {a['credit']}", font=f2, fill=(220, 220, 220, 200))
    return out


def photo_full(a: Dict[str, Any]) -> Image.Image:
    """A full-screen real photo cut into the stage (the stage cuts away to footage-like pictures, then back): cover-fit, NOT
    dimmed, a slow zoom over the beat (args _k), a small title chip top-left and 'Credits: X' lower-left."""
    from PIL import ImageEnhance
    try:
        im = Image.open(a["image"]).convert("RGB")
    except Exception:
        return Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    k = float(a.get("_k", 1.0))
    z = 1.0 + 0.09 * k
    W_, H_ = 1280, 720
    f = max(W_ * z / im.width, H_ * z / im.height)
    big = im.resize((max(W_, int(im.width * f)), max(H_, int(im.height * f))), Image.BILINEAR)
    ox = int((big.width - W_) * (0.35 + 0.3 * k))
    oy = int((big.height - H_) / 2)
    out = ImageEnhance.Contrast(big.crop((ox, oy, ox + W_, oy + H_))).enhance(1.04).convert("RGBA")
    if im.width / max(1, im.height) < 1.5:
        # not a 16:9 picture (J-11 study J6): the whole photo in a thin white frame over its own blurred, darkened copy -
        # an old 4:3 or portrait photo is never cropped to a strip
        from PIL import ImageFilter as _F
        out = ImageEnhance.Brightness(out.filter(_F.GaussianBlur(18))).enhance(0.45)
        fh = int(H_ * (0.74 + 0.03 * k))
        fw = int(im.width * fh / im.height)
        if fw > W_ * 0.86:
            fw = int(W_ * 0.86)
            fh = int(im.height * fw / im.width)
        inner = im.resize((fw, fh), Image.LANCZOS).convert("RGBA")
        fr = Image.new("RGBA", (fw + 12, fh + 12), (245, 245, 245, 255))
        fr.alpha_composite(inner, (6, 6))
        out.alpha_composite(fr, ((W_ - fr.width) // 2, (H_ - fr.height) // 2))
    d = ImageDraw.Draw(out)
    title = str(a.get("title") or "").strip()
    if title:
        ft = S.font("title", 30)
        tw = d.textlength(title, font=ft)
        d.rounded_rectangle((40, 40, 40 + tw + 36, 40 + ft.size + 26), radius=12, fill=(10, 10, 14, 200))
        d.text((58, 52), title, font=ft, fill=S.WHITE)
    if a.get("credit"):
        fc = S.font("body", 16)
        d.text((44, H_ - 40), f"Credits: {a['credit']}", font=fc, fill=(235, 235, 235, 230), stroke_width=2, stroke_fill=(0, 0, 0, 160))
    if a.get("ai"):                                      # a Flow picture is never passed off as an archive photo
        fa = S.font("body", 16)
        tw = d.textlength("AI ILLUSTRATION", font=fa)
        d.rounded_rectangle((W_ - tw - 70, H_ - 52, W_ - 40, H_ - 22), radius=8, fill=(10, 10, 14, 190))
        d.text((W_ - tw - 55, H_ - 46), "AI ILLUSTRATION", font=fa, fill=S.YELLOW)
    return out


G.register("caption", caption)
G.register("photo_full", photo_full)
G.register("backdrop", backdrop)
G.register("logo_card", logo_card)
G.register("timeline_bar", timeline_bar)
G.register("timeline_dot", timeline_dot)


def eras(airline_id: str) -> List[Tuple[str, Optional[int], Optional[int]]]:
    """The airline's names over time, oldest first: catalog previous_names, then its current name. Ancestors first if listed."""
    al = C.get_airline(airline_id) or {}
    out: List[Tuple[str, Optional[int], Optional[int]]] = []
    for pn in al.get("previous_names") or []:
        out.append((str(pn.get("name", "")), pn.get("from"), pn.get("to")))
    if al.get("name"):
        start = out[-1][2] if out and out[-1][2] else al.get("founded")
        out.append((al["name"], start, al.get("defunct")))
    return [e for e in out if e[0]]


def add_timeline(st: G.Stage, at: float, era_list: Sequence[Tuple[str, Optional[int], Optional[int]]], airline: str = "",
                 step: float = 1.6, y: float = 560.0, now: int = 2026, badge: bool = True) -> List[str]:
    """Bar, then each era's logo card above its years with the dot gliding to it and the year badge ticking (badge=False:
    the badge keeps the line's own year, so a recap of the past never winds the story's clock back)."""
    era_list = [e for e in era_list if e[1]]
    if not era_list:
        return []
    start = int(era_list[0][1])
    end = int(max((e[2] or now) for e in era_list))
    width = 1040.0
    ids = [st.add("timeline_bar", at, {"start": start, "end": end, "width": int(width)}, pos=(640, y + 22), enter="fade",
                  float_=False, edge=False)]
    dot = st.add("timeline_dot", at, {}, pos=(bar_x(start, start, end, width), y + 4), enter="pop", float_=False, edge=False, z=999)
    ids.append(dot)
    card_scale = min(1.0, 2.6 / max(1, len(era_list)))
    prev = None
    for i, (name, a, b) in enumerate(era_list):
        t = at + 0.4 + i * step
        n = len(era_list)
        gap = min(300.0, 1120.0 / n)
        cx = 640.0 + (i - (n - 1) / 2.0) * gap          # evenly spaced: short eras squeezed on the bar never overlap
        st.move(dot, t, pos=(bar_x(int(a), start, end, width), y + 4), dur=0.6)
        if badge:
            st.year(t, int(a))
        if prev:
            st.move(prev, t, scale=card_scale * 0.78)
        yrs = f"{a}–{b}" if b else f"since {a}"
        hits = C.find_airlines(name)
        own = ((hits[0].entry or {}).get("id", "") if hits else "")   # Malayan Airways has its own livery in the catalog
        prev = st.add("logo_card", t, {"airline": own or airline, "name": name, "years": yrs}, pos=(cx, y - 200), scale=card_scale,
                      edge=False)
        ids.append(prev)
    return ids
