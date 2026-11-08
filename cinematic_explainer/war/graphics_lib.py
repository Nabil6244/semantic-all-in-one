"""War Documentary graphics library, part 2: satellite before/after, document / article highlight, animated charts, equipment fly-over.

Same contract as cards.py: fn(t, dur, params) -> RGBA 1280x720 or None, a pure function of t and params (files named in params are read).
Content comes from the script / CSV / narration (numbers, quotes, dates) and from files the user or the app's providers supplied (images);
nothing is downloaded here and nothing is drawn when the needed input is missing (None, never a stand-in).

  lay_satellite  before*, after* (image paths), before_date, after_date, place, caption, credit (e.g. "Contains modified Copernicus Sentinel
                 data 2024"), split (0..1 final slider position, default 0.5). Full frame: both images slowly push in, a slider sweeps
                 across revealing AFTER over BEFORE, dates ride the slider, optional focus box {x, y, w, h} (0..1) on what changed.
  lay_document   image (screenshot path) or text (the narration's words), outlet, date, title, highlight: phrase | [x, y, w, h] (0..1 of the
                 image), credit. Full frame: the page floats in on a dark desk with a soft shadow, the camera drifts in, a marker
                 sweeps over the highlighted line, the rest dims. Without an image it is a plain typeset document of the narration's
                 own words (never a mock-up of an outlet's site).
  kit_chart      items* [{label, value, display?}], kind bars|percent|line|donut, title, unit, source, highlight (index). Full frame;
                 bars grow, values count up, the highlighted bar is yellow, the rest cream.
  kit_flyover    name* (drone|fpv|missile|jet|helicopter|shell...: stickers.py names), label, from (l|r), path (arc|low|dive), count.
                 Transparent overlay over footage: the pictogram crosses the frame on an arc with a speed trail and a label tag.
"""

from __future__ import annotations

import math
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from . import motion as M
from . import stickers as ST
from . import tokens as T
from .. import look as L

W, H = T.W, T.H
YELLOW = (255, 213, 0, 255)
CREAM = (236, 230, 214, 255)
INK = (10, 12, 16, 255)
_IMG: "OrderedDict[tuple, Optional[Image.Image]]" = OrderedDict()


def _load(path: Any, max_side: int = 2200) -> Optional[Image.Image]:
    if not path:
        return None
    p = Path(str(path))
    try:
        st = p.stat()
    except OSError:
        return None
    k = (str(p), st.st_size, st.st_mtime)
    if k in _IMG:
        _IMG.move_to_end(k)
        return _IMG[k]
    try:
        im = Image.open(p)
        im = ImageOps.exif_transpose(im).convert("RGB")
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side), Image.LANCZOS)
    except Exception:
        im = None
    _IMG[k] = im
    while len(_IMG) > 12:
        _IMG.popitem(last=False)
    return im


def _cover(src: Image.Image, w: int, h: int, zoom: float = 1.0, ax: float = 0.5, ay: float = 0.5) -> Image.Image:
    s = max(w / src.width, h / src.height) * zoom
    sw, sh = src.width * s, src.height * s
    x0, y0 = (sw - w) * ax / s, (sh - h) * ay / s
    return src.transform((w, h), Image.AFFINE, (1 / s, 0, x0, 0, 1 / s, y0), resample=Image.BILINEAR)


def _out(t: float, dur: float, fade: float = 0.35) -> float:
    return 1.0 if dur <= 0 else M.clamp01((dur - t) / fade)


def _chip(d: ImageDraw.ImageDraw, x: int, y: int, text: str, f, fill=(10, 12, 16, 230), fg=(242, 244, 248, 255), edge=None) -> Tuple[int, int, int, int]:
    w = int(L.spaced_width(d, text, f, 0.1)) + 20
    h = f.size + 12
    d.rectangle([x, y, x + w, y + h], fill=fill, outline=edge)
    L.spaced(d, (x + 10, y + 5), text, f, fg, 0.1)
    return (x, y, x + w, y + h)


def _credit(d: ImageDraw.ImageDraw, text: str) -> None:
    if not text:
        return
    f = T.font("regular", 13)
    tw = d.textlength(text, font=f)
    d.text((W - 24 - tw, H - 26), text, font=f, fill=(200, 204, 212, 230), stroke_width=2, stroke_fill=(0, 0, 0, 200))


# ================================================================================================================ satellite before / after
def lay_satellite(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    a, b = _load(p.get("before")), _load(p.get("after"))
    if a is None or b is None:
        return None
    z = 1.04 + 0.06 * M.ease_in_out(M.clamp01(t / max(dur, 0.1)))       # one slow push over the card
    fx = p.get("focus") if isinstance(p.get("focus"), dict) else None
    ax, ay = (float(fx["x"]) + float(fx.get("w", 0)) / 2, float(fx["y"]) + float(fx.get("h", 0)) / 2) if fx else (0.5, 0.5)
    A = _cover(a, W, H, z, ax, ay).convert("RGBA")
    B = _cover(b, W, H, z, ax, ay).convert("RGBA")
    if p.get("single"):                      # one image: the frame itself, pushing in, with its date and the focus box
        img = B.copy()
        d = ImageDraw.Draw(img)
        xs = W
        ad = str(p.get("after_date") or "").upper()
        if ad:
            _chip(d, W - 24 - int(L.spaced_width(d, ad, T.font("bold", 16), 0.1)) - 20, H - 84, ad, T.font("bold", 16), fill=(255, 213, 0, 240), fg=INK)
        return _sat_finish(img, d, p, t, dur, fx)
    split = float(p.get("split", 0.5))
    # the slider: holds on BEFORE, sweeps all the way to reveal AFTER, then settles back to the split so both stay readable
    s1 = M.ease_in_out(M.ramp(t, 0.9, 1.6))
    s2 = M.ease_in_out(M.ramp(t, 3.0, 1.0))
    pos = 1.0 - s1 + (split) * s2 if s2 > 0 else 1.0 - s1
    xs = int(W * min(1.0, max(0.0, pos)))
    img = A.copy()
    if xs < W:
        img.paste(B.crop((xs, 0, W, H)), (xs, 0))
    d = ImageDraw.Draw(img)
    # vignette band + slider line + handle
    if 0 < xs < W:
        d.line([(xs, 0), (xs, H)], fill=(255, 255, 255, 255), width=3)
        d.ellipse([xs - 18, H / 2 - 18, xs + 18, H / 2 + 18], fill=(255, 255, 255, 255))
        d.polygon([(xs - 10, H / 2), (xs - 4, H / 2 - 6), (xs - 4, H / 2 + 6)], fill=INK)
        d.polygon([(xs + 10, H / 2), (xs + 4, H / 2 - 6), (xs + 4, H / 2 + 6)], fill=INK)
    fd = T.font("bold", 16)
    bd, ad = str(p.get("before_date") or "BEFORE").upper(), str(p.get("after_date") or "AFTER").upper()
    if xs > 120:
        _chip(d, max(24, min(xs - 24 - int(L.spaced_width(d, bd, fd, 0.1)) - 20, 24)), H - 84, bd, fd)
    if xs < W - 120:
        _chip(d, max(xs + 24, W - 24 - int(L.spaced_width(d, ad, fd, 0.1)) - 20), H - 84, ad, fd, fill=(255, 213, 0, 240), fg=INK)
    return _sat_finish(img, d, p, t, dur, fx)


def _sat_finish(img: Image.Image, d: ImageDraw.ImageDraw, p: dict, t: float, dur: float, fx: Optional[dict]) -> Image.Image:
    if fx and t > 3.6:                                                       # what changed: a box draws itself around it
        k = M.draw_fraction(t, 3.6, 0.7)
        bx, by, bw, bh = (float(fx[c]) for c in ("x", "y", "w", "h"))
        z0 = (W * bx, H * by, W * (bx + bw), H * (by + bh))
        pts = [(z0[0], z0[1]), (z0[2], z0[1]), (z0[2], z0[3]), (z0[0], z0[3]), (z0[0], z0[1])]
        part = M.partial_polyline(pts, k)
        if len(part) > 1:
            d.line(part, fill=(0, 0, 0, 160), width=6)
            d.line(part, fill=YELLOW, width=3)
        if k >= 1 and fx.get("label"):
            _chip(d, int(z0[0]), int(z0[3] + 8), str(fx["label"]).upper(), T.font("bold", 14), fill=YELLOW, fg=INK)
    # caption top-left
    cap, place = str(p.get("caption") or "").upper(), str(p.get("place") or "").upper()
    kc = M.ease_out(M.ramp(t, 0.2, 0.5))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    _chip(ld, 24, 22, "SATELLITE IMAGE" + (f" · {place}" if place else ""), T.font("bold", 14))
    if cap:
        f = T.font("display", 40)
        ld.text((24, 60), cap, font=f, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 220))
    img.alpha_composite(L.fade(lay, kc))
    _credit(d, str(p.get("credit") or ""))
    k = M.ease_out(M.ramp(t, 0.0, 0.4)) * _out(t, dur)
    return L.fade(img, k) if k < 1 else img


# ================================================================================================================ document / article highlight
def _typeset(p: dict) -> Tuple[Image.Image, List[Tuple[str, Tuple[int, int, int, int]]]]:
    """A plain document page of the narration's own words: (page image, [(line, rect)])."""
    pw, ph = 760, 900
    page = Image.new("RGB", (pw, ph), (244, 241, 234))
    d = ImageDraw.Draw(page)
    fo, ft, fb = T.font("bold", 18), T.font("display", 44), T.font("regular", 26)
    y = 56
    head = " · ".join(x for x in (str(p.get("outlet") or "").upper(), str(p.get("date") or "").upper()) if x)
    if head:
        d.text((56, y), head, font=fo, fill=(120, 30, 30))
        y += 40
    d.line([(56, y), (pw - 56, y)], fill=(30, 30, 30), width=2)
    y += 24
    title = str(p.get("title") or "").strip()
    if title:
        for ln in _wrap_px(d, title, ft, pw - 112)[:3]:
            tw = d.textlength(ln, font=ft)
            d.rectangle([50, y + 2, 62 + tw, y + 50], fill=(255, 196, 0))      # the reference's yellow headline highlight
            d.text((56, y), ln, font=ft, fill=(20, 20, 24))
            y += 54
        y += 16
    lines = []
    for ln in _wrap_px(d, str(p.get("text") or ""), fb, pw - 112)[:16]:
        d.text((56, y), ln, font=fb, fill=(40, 40, 46))
        lines.append((ln, (50, y - 4, pw - 50, y + 34)))
        y += 40
    return page.crop((0, 0, pw, max(420, y + 48))), lines


def _wrap_px(d: ImageDraw.ImageDraw, text: str, f, width: int) -> List[str]:
    out, cur = [], ""
    for w in text.split():
        nxt = (cur + " " + w).strip()
        if d.textlength(nxt, font=f) <= width or not cur:
            cur = nxt
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


_DESK: List[Image.Image] = []
_PLATES: "OrderedDict[tuple, Image.Image]" = OrderedDict()


_STILLS: "OrderedDict[tuple, Optional[Image.Image]]" = OrderedDict()


def _still(video: str, at: float) -> Optional[Image.Image]:
    """One sharp frame of a clip (cached): the round map inset's picture."""
    import subprocess

    k = (str(video), round(float(at), 1))
    if k not in _STILLS:
        im = None
        try:
            r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, float(at)):.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=480:-2",
                                "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=60)
            if r.stdout:
                import io

                im = Image.open(io.BytesIO(r.stdout)).convert("RGB")
        except Exception:
            im = None
        _STILLS[k] = im
        while len(_STILLS) > 12:
            _STILLS.popitem(last=False)
    return _STILLS[k]


def _plate(video: str, at: float) -> Optional[Image.Image]:
    """The reference's article backdrop: the scene's own clip, one frame, blurred and dimmed, with faint topographic lines and rings."""
    import subprocess

    k = (str(video), round(float(at), 1))
    if k in _PLATES:
        return _PLATES[k]
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, float(at)):.2f}", "-i", str(video), "-frames:v", "1", "-vf",
                            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           capture_output=True, timeout=60)
        if len(r.stdout) < W * H * 3:
            return None
        im = Image.frombytes("RGB", (W, H), r.stdout[:W * H * 3]).filter(ImageFilter.GaussianBlur(14))
    except Exception:
        return None
    im = Image.blend(im, Image.new("RGB", (W, H), (20, 28, 36)), 0.35).convert("RGBA")
    d = ImageDraw.Draw(im)
    for i in range(9):                                          # topographic contour lines
        cx, cy = W * 0.2, H * 0.8
        rr = 120 + 95 * i
        d.ellipse([cx - rr * 1.6, cy - rr, cx + rr * 1.6, cy + rr], outline=(255, 255, 255, 26), width=2)
    for (x, y, rr) in ((90, 160, 34), (1180, 560, 26), (230, 610, 12)):
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=(255, 255, 255, 70), width=2)
    _PLATES[k] = im
    while len(_PLATES) > 6:
        _PLATES.popitem(last=False)
    return im


def _desk() -> Image.Image:
    if not _DESK:
        g = Image.new("L", (W, H), 0)
        ImageDraw.Draw(g).ellipse([int(W * 0.05), int(-H * 0.2), int(W * 0.8), int(H * 1.1)], fill=255)
        g = g.filter(ImageFilter.GaussianBlur(160)).point(lambda v: v // 2)
        _DESK.append(Image.composite(Image.new("RGB", (W, H), (44, 48, 56)), Image.new("RGB", (W, H), (12, 14, 18)), g).convert("RGBA"))
    return _DESK[0]


def lay_document(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    shot = _load(p.get("image"))
    if shot is None and not str(p.get("text") or "").strip():
        return None
    if shot is not None:
        page = shot.copy()
        lines: List[Tuple[str, Tuple[int, int, int, int]]] = []
        hb = p.get("highlight")
        hls: List[Tuple[int, int, int, int]] = []
        if isinstance(hb, (list, tuple)) and len(hb) == 4:
            hls = [(int(hb[0] * page.width), int(hb[1] * page.height), int((hb[0] + hb[2]) * page.width), int((hb[1] + hb[3]) * page.height))]
    else:
        page, lines = _typeset(p)
        phrase = str(p.get("highlight") or "").lower()
        words = set(re.findall(r"\w+", phrase)) - {"the", "a", "an", "of", "and", "to", "in", "on", "at", "for", "by", "with", "was", "were", "is"}
        need = 1
        hls = [r for ln, r in lines if words and len(words & set(re.findall(r"\w+", ln.lower()))) >= need]
    # the desk
    pl = _plate(str(p["plate"]), float(p.get("plate_t", 1.0))) if p.get("plate") else None
    img = (pl if pl is not None else _desk()).copy()
    # the page: floats in, slight tilt, camera drifts toward the highlight
    k = M.ease_out(M.ramp(t, 0.0, 0.7))
    zoom = 1.0 + 0.10 * M.ease_in_out(M.clamp01(t / max(dur, 0.1)))
    maxh = H * 0.86
    s = min(maxh / page.height, W * 0.56 / page.width) * zoom
    pg = page.resize((max(1, int(page.width * s)), max(1, int(page.height * s))), Image.LANCZOS).convert("RGBA")
    dim = M.ease_in_out(M.ramp(t, 1.4, 0.6))
    hl = (min(r[0] for r in hls), min(r[1] for r in hls), max(r[2] for r in hls), max(r[3] for r in hls)) if hls else None
    if hls:
        shade = Image.new("RGBA", pg.size, (0, 0, 0, int(110 * dim)))
        sd_ = ImageDraw.Draw(shade)
        mark = Image.new("RGBA", pg.size, (0, 0, 0, 0))
        md = ImageDraw.Draw(mark)
        for j, hr in enumerate(hls):                                # the marker sweeps each highlighted line in turn
            r = tuple(int(v * s) for v in hr)
            sd_.rectangle(r, fill=(0, 0, 0, 0))
            mk = M.draw_fraction(t, 1.2 + 0.6 * j, 0.6)
            if mk > 0:
                md.rectangle([r[0], r[1], r[0] + int((r[2] - r[0]) * mk), r[3]], fill=(255, 213, 0, 110))
        pg.alpha_composite(shade)
        pg = Image.alpha_composite(pg, mark)
    ang = -2.0 * (1 - 0.4 * M.ease_in_out(M.clamp01(t / max(dur, 0.1))))
    pr = pg.rotate(ang, resample=Image.BICUBIC, expand=True)
    sh = Image.new("RGBA", pr.size, (0, 0, 0, 0))
    sh.putalpha(pr.getchannel("A").point(lambda v: int(v * 0.6)))
    sh = sh.filter(ImageFilter.GaussianBlur(18))
    cx = int(W * 0.37 - pr.width / 2 + (W * 0.06) * (1 - k))
    cy = int(H / 2 - pr.height / 2 + 24 * (1 - k))
    if hl is not None:                                             # keep the highlighted line near the middle as the camera drifts
        cy = int(cy - ((hl[1] + hl[3]) / 2 * s - pr.height / 2) * 0.35 * M.ease_in_out(M.ramp(t, 1.0, 1.5)))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lay.alpha_composite(sh, (cx + 14, cy + 22))
    lay.alpha_composite(pr, (cx, cy))
    img.alpha_composite(L.fade(lay, k))
    # side text: outlet and date, the narration's quoted line
    d = ImageDraw.Draw(img)
    x0 = int(W * 0.72)
    ko = M.ease_out(M.ramp(t, 0.6, 0.5))
    side = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(side)
    yy = int(H * 0.30)
    for txt, f, col in ((str(p.get("outlet") or "").upper(), T.font("bold", 18), (236, 56, 56, 255)),
                        (str(p.get("date") or "").upper(), T.font("bold", 16), (200, 204, 212, 255))):
        if txt:
            L.spaced(sd, (x0, yy), txt, f, col, 0.12)
            yy += 30
    q = str(p.get("quote") or "").strip()
    if q:
        fq = T.font("display", 34)
        yy += 12
        for ln in _wrap_px(sd, "“" + q.upper() + "”", fq, W - x0 - 40)[:6]:
            sd.text((x0, yy), ln, font=fq, fill=(250, 248, 244, 255))
            yy += 40
    img.alpha_composite(L.fade(side, ko))
    _credit(d, str(p.get("credit") or ""))
    return L.fade(img, _out(t, dur))


# ================================================================================================================ animated charts
def _num(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _fmt(v: float, like: str) -> str:
    dec = len(like.split(".")[1]) if "." in like else 0
    s = f"{v:,.{dec}f}"
    return s + ("%" if like.strip().endswith("%") else "")


def kit_chart(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    items = [(str(i.get("label") or ""), _num(i.get("value")), str(i.get("display") or i.get("value") or "")) for i in p.get("items") or []
             if isinstance(i, dict) and _num(i.get("value")) is not None]
    if len(items) < 2:
        return None
    kind = str(p.get("kind") or "bars")
    hi = p.get("highlight")
    img = Image.new("RGBA", (W, H), (12, 14, 18, 255))
    d = ImageDraw.Draw(img)
    for gx in range(0, W, 40):                                        # faint grid, the reference's data-board look
        d.line([(gx, 0), (gx, H)], fill=(22, 26, 32, 255))
    for gy in range(0, H, 40):
        d.line([(0, gy), (W, gy)], fill=(22, 26, 32, 255))
    title = str(p.get("title") or "").upper()
    ft = T.font("display", 44)
    kt = M.ease_out(M.ramp(t, 0.0, 0.5))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    if title:
        ld.text((64, 48), title, font=ft, fill=(255, 255, 255, 255))
        ld.rectangle([64, 104, 64 + int(140 * kt), 108], fill=(236, 56, 56, 255))
    img.alpha_composite(L.fade(lay, kt))
    d = ImageDraw.Draw(img)
    vmax = max(v for _, v, _ in items) or 1.0
    n = len(items)
    fl, fv = T.font("bold", 20), T.font("display", 40)
    if kind in ("bars", "percent"):
        horizontal = n > 4 or kind == "percent"
        if horizontal:
            top, bh = 150, min(64, int((H - 220) / n) - 14)
            lw = 300
            for i, (lab, v, disp) in enumerate(items):
                k = M.ease_out(M.ramp(t, 0.4 + 0.18 * i, 0.9))
                y = top + i * (bh + 14)
                full = (W - 64 - 160 - (64 + lw))
                tot = 100.0 if kind == "percent" else vmax
                bw = int(full * min(1.0, v / tot) * k)
                L.spaced(d, (64, y + bh / 2 - 12), lab.upper()[:26], fl, (220, 224, 230, 255), 0.06)
                if kind == "percent":
                    d.rectangle([64 + lw, y, 64 + lw + full, y + bh], fill=(30, 34, 42, 255))
                col = YELLOW if (hi == i or (hi is None and v == vmax)) else CREAM
                d.rectangle([64 + lw, y, 64 + lw + bw, y + bh], fill=col)
                d.text((64 + lw + bw + 14, y + bh / 2 - 24), _fmt(v * k, disp or str(v)), font=fv, fill=col)
        else:
            base = H - 110
            area = base - 190
            slot = (W - 128) / n
            bw = min(150, slot * 0.55)
            for i, (lab, v, disp) in enumerate(items):
                k = M.ease_out(M.ramp(t, 0.4 + 0.2 * i, 0.9))
                cx = 64 + slot * (i + 0.5)
                bh = area * v / vmax * k
                col = YELLOW if (hi == i or (hi is None and v == vmax)) else CREAM
                d.rectangle([cx - bw / 2, base - bh, cx + bw / 2, base], fill=col)
                txt = _fmt(v * k, disp or str(v))
                d.text((cx - d.textlength(txt, font=fv) / 2, base - bh - 52), txt, font=fv, fill=col)
                lw_ = L.spaced_width(d, lab.upper()[:18], fl, 0.06)
                L.spaced(d, (cx - lw_ / 2, base + 16), lab.upper()[:18], fl, (220, 224, 230, 255), 0.06)
            d.line([(64, base), (W - 64, base)], fill=(120, 126, 136, 255), width=2)
    elif kind == "line":
        x0, x1, y0, y1 = 110, W - 110, H - 120, 170
        vmin = min(0.0, min(v for _, v, _ in items))
        pts = [(x0 + (x1 - x0) * i / (n - 1), y0 - (y0 - y1) * (v - vmin) / ((vmax - vmin) or 1)) for i, (_, v, _) in enumerate(items)]
        d.line([(x0, y0), (x1, y0)], fill=(120, 126, 136, 255), width=2)
        frac = M.draw_fraction(t, 0.4, 1.8)
        part = M.partial_polyline(pts, frac)
        if len(part) > 1:
            d.line(part, fill=(0, 0, 0, 255), width=10, joint="curve")
            d.line(part, fill=YELLOW, width=5, joint="curve")
        for i, ((lab, v, disp), (px, py)) in enumerate(zip(items, pts)):
            if frac * (n - 1) + 1e-6 < i:
                continue
            d.ellipse([px - 8, py - 8, px + 8, py + 8], fill=YELLOW, outline=INK, width=2)
            txt = disp or _fmt(v, str(v))
            d.text((px - d.textlength(txt, font=T.font("bold", 24)) / 2, py - 44), txt, font=T.font("bold", 24), fill=(255, 255, 255, 255))
            lw_ = L.spaced_width(d, lab.upper()[:14], fl, 0.06)
            L.spaced(d, (px - lw_ / 2, y0 + 14), lab.upper()[:14], fl, (200, 204, 212, 255), 0.06)
    elif kind == "donut":
        cx, cy, r = W * 0.34, H * 0.56, 190
        tot = sum(v for _, v, _ in items) or 1.0
        a0 = -90.0
        frac = M.ease_in_out(M.ramp(t, 0.3, 1.4))
        cols = [YELLOW, CREAM, (236, 56, 56, 255), (86, 152, 236, 255), (120, 126, 136, 255)]
        for i, (lab, v, disp) in enumerate(items):
            sweep = 360 * v / tot * frac
            d.pieslice([cx - r, cy - r, cx + r, cy + r], a0, a0 + sweep, fill=cols[i % len(cols)])
            a0 += sweep
            ly = H * 0.36 + i * 56
            d.rectangle([W * 0.62, ly, W * 0.62 + 22, ly + 22], fill=cols[i % len(cols)])
            L.spaced(d, (W * 0.62 + 36, ly - 2), f"{(disp or _fmt(v, str(v)))}  {lab.upper()}"[:34], fl, (236, 238, 242, 255), 0.06)
        d.ellipse([cx - r * 0.58, cy - r * 0.58, cx + r * 0.58, cy + r * 0.58], fill=(12, 14, 18, 255))
    src = str(p.get("source") or "")
    if src:
        f = T.font("regular", 15)
        d.text((64, H - 44), src, font=f, fill=(150, 156, 166, 255))
    return L.fade(img, _out(t, dur))


# ================================================================================================================ equipment fly-over
def kit_flyover(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """A named system crosses the frame over footage: pictogram on an arc, motion trail, a label tag that rides along."""
    p = p or {}
    name = str(p.get("name") or "")
    if not name or name not in ST.DEFAULTS:
        return None
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    n = max(1, min(5, int(p.get("count", 1) or 1)))
    rtl = str(p.get("from") or "l").startswith("r")
    path = str(p.get("path") or ("dive" if name in ("missile", "fpv", "shell", "bomb") else "arc"))
    span = max(1.2, min(dur - 0.4, 3.2))
    size = int(p.get("size") or (150 if n == 1 else 96))
    stk = ST.draw_sticker(name, size)
    if rtl:
        stk = stk.transpose(Image.FLIP_LEFT_RIGHT)
    d = ImageDraw.Draw(img)
    for j in range(n):
        u = M.ease_in_out(M.ramp(t, 0.2 + 0.25 * j, span))
        if u <= 0 or u >= 1:
            continue
        x = -size + (W + 2 * size) * u
        if rtl:
            x = W - x
        oy = (j - (n - 1) / 2) * size * 0.8
        if path == "dive":
            y = H * 0.18 + H * 0.5 * u * u + oy
        elif path == "low":
            y = H * 0.62 + 12 * math.sin(u * 6) + oy
        else:
            y = H * 0.42 - H * 0.18 * math.sin(u * math.pi) + oy
        for q in range(14):                                         # the speed trail
            uu = max(0.0, u - 0.012 * (q + 1))
            tx = -size + (W + 2 * size) * uu
            tx = W - tx if rtl else tx
            ty = (H * 0.18 + H * 0.5 * uu * uu if path == "dive" else H * 0.62 + 12 * math.sin(uu * 6) if path == "low"
                  else H * 0.42 - H * 0.18 * math.sin(uu * math.pi)) + oy
            a = int(110 * (1 - q / 14))
            rr = max(2, int(size * 0.07 * (1 - q / 18)))
            d.ellipse([tx - rr, ty - rr, tx + rr, ty + rr], fill=(255, 255, 255, a))
        img.alpha_composite(stk, (int(x - size / 2), int(y - size / 2)))
        if j == 0 and p.get("label"):
            f = T.font("bold", 18)
            lab = str(p["label"]).upper()
            w = int(L.spaced_width(d, lab, f, 0.1)) + 22
            lx = int(min(max(24, x - w / 2), W - w - 24))
            ly = int(y + size / 2 + 10)
            d.rectangle([lx, ly, lx + w, ly + 30], fill=(10, 12, 16, 220))
            d.rectangle([lx, ly, lx + 4, ly + 30], fill=YELLOW)
            L.spaced(d, (lx + 12, ly + 6), lab, f, (244, 246, 250, 255), 0.1)
    return img


def lay_speaker_quote(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Black panel, gold NAME and role, the quote typing on word by word (`words_t` when given), a round portrait in a white ring on the
    right (initials when there is no portrait). The reference's 'official says' card."""
    p = p or {}
    name, quote = str(p.get("name") or "").strip(), str(p.get("quote") or "").strip()
    if not name or not quote:
        return None
    img = Image.new("RGBA", (W, H), (14, 14, 16, 255))
    d = ImageDraw.Draw(img)
    gold = (232, 178, 64, 255)
    k = M.ease_out(M.ramp(t, 0.0, 0.5))
    # portrait circle, partly off the right edge
    R = 300
    cx, cy = int(W - 250 + 60 * (1 - k)), H // 2 + 20
    d.ellipse([cx - R - 14, cy - R - 14, cx + R + 14, cy + R + 14], fill=(236, 236, 236, 255))
    ph = _load(p.get("portrait"))
    disc = Image.new("RGBA", (2 * R, 2 * R), (40, 44, 52, 255))
    if ph is not None:
        disc = _cover(ph, 2 * R, 2 * R, 1.0 + 0.04 * M.clamp01(t / max(dur, 0.1)), 0.5, 0.35).convert("RGBA")
    else:
        dd = ImageDraw.Draw(disc)
        ini = "".join(w[0] for w in name.split()[:2]).upper()
        fi = T.font("display", 200)
        dd.text((R - dd.textlength(ini, font=fi) / 2, R - 120), ini, font=fi, fill=gold)
    m = Image.new("L", (2 * R, 2 * R), 0)
    ImageDraw.Draw(m).ellipse([0, 0, 2 * R - 1, 2 * R - 1], fill=255)
    disc.putalpha(m)
    img.alpha_composite(disc, (cx - R, cy - R))
    # text column
    x0, w0 = 70, 560
    fn, fr_, fq = T.font("display", 54), T.font("bold", 22), T.font("display", 36)
    y = 150
    d.text((x0, y), name.upper(), font=fn, fill=gold)
    y += 66
    for ln in _wrap_px(d, str(p.get("role") or "").upper(), fr_, w0)[:2]:
        d.text((x0, y), ln, font=fr_, fill=gold)
        y += 28
    y += 34
    words = ("“" + quote + "”").upper().split()
    wt = [float(v) for v in (p.get("words_t") or [])]
    if len(wt) == len(words):
        shown = [w_ for w_, tt in zip(words, wt) if tt <= t]
    else:
        shown = words[:int(math.ceil(len(words) * M.clamp01((t - 0.5) / max(0.8, min(3.0, 0.22 * len(words))))))]
    for ln in _wrap_px(d, " ".join(shown), fq, w0)[:6]:
        d.text((x0, y), ln, font=fq, fill=(245, 245, 245, 255))
        y += 44
    return L.fade(img, min(M.ramp(t, 0.0, 0.25), _out(t, dur)))


GFX_CARDS = {"lay_satellite": lay_satellite, "lay_document": lay_document, "kit_chart": kit_chart, "kit_flyover": kit_flyover,
             "lay_speaker_quote": lay_speaker_quote}
FULL = {"lay_satellite", "lay_document", "kit_chart"}


# ================================================================================================================ narration -> chart / article / fly-over
_MONTH = r"(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
_LAB_AFTER = re.compile(r"^\s*(?:\w+\s+){0,2}?(?:in|by|during|for|of)\s+(" + _MONTH + r"(?:\s+(?:19|20)\d{2})?|(?:19|20)\d{2}|[A-Z][\w-]+(?:\s+[A-Z][\w-]+)?)")
_LAB_BEFORE = re.compile(r"(?:in|by|during)\s+(" + _MONTH + r"(?:\s+(?:19|20)\d{2})?|(?:19|20)\d{2}),?\s*(?:\w+\s+){0,3}$")


def chart_of(text: str, numbers: Sequence[Any]) -> Optional[Dict[str, Any]]:
    """A chart from three or more figures the sentence states (or two percentages tied to dates): the script's own numbers and labels.
    None when the figures cannot each be given a label from the sentence (a chart of unlabelled bars says nothing)."""
    nums = [n for n in numbers if not getattr(n, "is_year", False)]
    if len(nums) < 2:
        return None
    pct = all(getattr(n, "unit", "") == "%" for n in nums)
    if len(nums) < 3 and not pct:
        return None
    items = []
    for n in nums[:6]:
        a, b = n.span
        m = _LAB_AFTER.match(text[b:b + 40])
        lab = m.group(1) if m else ""
        if not lab:
            mb = _LAB_BEFORE.search(text[max(0, a - 40):a])
            lab = mb.group(1) if mb else ""
        if not lab:
            return None
        items.append({"label": lab, "value": n.value, "display": n.raw})
    if len({i["label"].lower() for i in items}) < len(items):
        return None
    unit = next((n.unit for n in nums if n.unit and n.unit != "%"), "")
    timeish = all(re.fullmatch(_MONTH + r"(\s+(19|20)\d{2})?|(19|20)\d{2}", i["label"], re.IGNORECASE) for i in items)
    kind = "line" if timeish and len(items) >= 3 else "percent" if pct and not timeish else "bars"
    title = (unit[:1].upper() + unit[1:]) if unit else ""
    return {"items": items, "kind": kind, "title": title, "source": ""}


def article_of(sentence: Any) -> Optional[Dict[str, Any]]:
    """A cited report as a document page: the outlet the narration names, the sentence's words, the reported clause highlighted."""
    cite = getattr(sentence, "citation", None)
    if cite is None:
        return None
    cites = [cite]
    text = str(sentence.text)
    m = re.search(r"\b(?:said|says|reported|reports|wrote|found|concluded|stated|warned)\s+(?:that\s+)?(.+)$", text)
    hl = (m.group(1) if m else text).strip().rstrip(".")
    return {"outlet": str(cites[0].outlet), "text": text, "highlight": hl, "quote": " ".join(hl.split()[:12])}


_FLY = re.compile(r"\b(launched|fired|flew|flying|struck|shot down|intercepted|swarm\w*|waves? of)\b", re.IGNORECASE)
_FLY_NAMES = [(r"\b(fpv|kamikaze drones?)\b", "fpv"), (r"\b(shahed\w*|geran\w*|drones?|uavs?)\b", "drone"), (r"\b(missiles?|rockets?|kalibr|iskander\w*|storm shadow|atacms)\b", "missile"),
              (r"\b(jets?|aircraft|warplanes?|bombers?|fighters?|f-16s?|su-\d+)\b", "jet"), (r"\b(helicopters?)\b", "helicopter")]


def flyover_of(text: str) -> Optional[Dict[str, Any]]:
    if not _FLY.search(text):
        return None
    for rx, name in _FLY_NAMES:
        m = re.search(rx, text, re.IGNORECASE)
        if m:
            plural = m.group(0).lower().endswith("s") or re.search(r"\b(swarm|waves?|hundreds|dozens|\d{2,})\b", text, re.IGNORECASE)
            return {"name": name, "label": m.group(0).upper(), "count": 3 if plural else 1, "from": "r" if name in ("drone", "missile", "fpv") else "l"}
    return None
