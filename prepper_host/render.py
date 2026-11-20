"""Prepper Host renderer: every shot drawn frame by frame (PIL), encoded per shot in parallel, joined, then mixed.

Layouts: host (full), split (host 44 % | b-roll 56 %), pip (b-roll + round host cam top right), broll (camera move).
Cards over a blurred, darkened picture: product / compare (white photo cards that pop in), data (math rows that count up
and draw their rule), checklist (ticks pop, struck items get a red line), bars (grow with the number), big (one big
number). Over everything: chapter bumpers, the host's name bar on his first shot, a subscribe pop near the end.
"""
import math
import os
import re
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"
SFX_DIR = ROOT / "assets" / "bundled-sfx"
MUSIC_DIR = ROOT / "assets" / "music"
SFX = {"whoosh": ("whoosh/whoosh_004.opus", -21.0), "tick": ("ui/ui_003.opus", -20.0), "pop": ("ui/ui_005.opus", -21.0),
       "chapter": ("transition/transition_01.opus", -17.0), "end": ("impact/impact_005.opus", -20.0)}
MUSIC_BED = "lost_frontier.opus"
YELLOW, RED, GREEN, WHITE = (255, 214, 10), (235, 64, 52), (74, 222, 128), (255, 255, 255)
COLOURS = {"red": RED, "green": GREEN, "yellow": YELLOW, "white": WHITE}


class Stopped(Exception):
    pass


# ------------------------------------------------------------------ helpers
_FONT_CACHE = {}


def font(name, px):
    k = (name, int(px))
    if k not in _FONT_CACHE:
        try:
            _FONT_CACHE[k] = ImageFont.truetype(str(FONTS / name), int(px))
        except OSError:
            _FONT_CACHE[k] = ImageFont.load_default()
    return _FONT_CACHE[k]


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def back(x):
    x = clamp(x)
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


_IMG_CACHE = {}


def load(path, size=None):
    k = (path, size)
    if k not in _IMG_CACHE:
        im = Image.open(path).convert("RGB")
        if size:
            im = cover(im, size)
        _IMG_CACHE[k] = im
    return _IMG_CACHE[k]


def cover(im, size):
    W, H = size
    s = max(W / im.width, H / im.height)
    im = im.resize((max(W, round(im.width * s)), max(H, round(im.height * s))), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def kenburns(src, size, move, f):
    """src already covers `size` with 12 % headroom; f = 0..1 through the shot."""
    W, H = size
    e = ease(f)
    z0, z1, dx, dy = {"push_in": (1.0, 1.10, 0, 0), "pull_out": (1.10, 1.0, 0, 0), "pan_right": (1.10, 1.10, -1, 0),
                      "pan_left": (1.10, 1.10, 1, 0), "push_in_low": (1.02, 1.12, 0, 0.5), "drift": (1.05, 1.09, 0.5, -0.4),
                      "still": (1.03, 1.05, 0, 0)}.get(move, (1.0, 1.08, 0, 0))
    z = z0 + (z1 - z0) * e
    sw, sh = src.width / z, src.height / z
    cx = src.width / 2 + dx * (src.width - sw) / 2 * (2 * e - 1)
    cy = src.height / 2 + dy * (src.height - sh) / 2 * (e if dy > 0 else (2 * e - 1))
    x0, y0 = cx - sw / 2, cy - sh / 2
    a = sw / W
    return src.transform((W, H), Image.AFFINE, (a, 0, x0, 0, sh / H, y0), resample=Image.BILINEAR)


def headroom(path, size):
    W, H = size
    return load(path, (round(W * 1.12), round(H * 1.12)))


def rounded(size, radius, fill):
    m = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=fill)
    return m


def shadowed(card, blur):
    pad = blur * 3
    sh = Image.new("RGBA", (card.width + pad * 2, card.height + pad * 2), (0, 0, 0, 0))
    alpha = card.split()[3].point(lambda v: int(v * 0.55))
    sh.paste((0, 0, 0, 255), (pad, pad + blur // 2), alpha)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    sh.alpha_composite(card, (pad, pad))
    return sh


def paste_scaled(base, layer, cx, cy, s, alpha=1.0):
    if s <= 0.02 or alpha <= 0.01:
        return
    w, h = max(1, int(layer.width * s)), max(1, int(layer.height * s))
    lay = layer.resize((w, h), Image.BILINEAR) if (w, h) != layer.size else layer
    if alpha < 1:
        a = lay.split()[3].point(lambda v: int(v * alpha))
        lay = lay.copy()
        lay.putalpha(a)
    base.alpha_composite(lay, (int(cx - w / 2), int(cy - h / 2)))


def trim_white(im, margin=0.06):
    """A packshot on white: crop to the product (plus a margin) so it fills its card."""
    g = np.asarray(im.convert("L"))
    ys, xs = np.where(g < 235)
    if len(xs) < 50:
        return im
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    mx, my = int((x1 - x0) * margin) + 4, int((y1 - y0) * margin) + 4
    return im.crop((max(0, x0 - mx), max(0, y0 - my), min(im.width, x1 + mx), min(im.height, y1 + my)))


def vignette(size):
    W, H = size
    y, x = np.ogrid[0:H, 0:W]
    d = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
    a = (np.clip((d - 0.65) / 0.75, 0, 1) ** 1.6 * 150).astype(np.uint8)
    v = Image.new("RGBA", size, (0, 0, 0, 0))
    v.putalpha(Image.fromarray(a))
    return v


def fmt_count(value, num, f):
    """'360 GAL' counting up: the first number in the text runs from 0 to its value."""
    if num is None or f >= 1:
        return value
    cur = num * ease_out(f)
    m = re.search(r"\d[\d,]*\.?\d*", value)
    if not m:
        return value
    s = m.group(0)
    dec = len(s.split(".")[1]) if "." in s else 0
    txt = f"{cur:,.{dec}f}" if "," in s else f"{cur:.{dec}f}"
    return value[:m.start()] + txt + value[m.end():]


# ------------------------------------------------------------------ shot drawer
class Drawer:
    def __init__(self, spec, assets):
        self.spec, self.a = spec, assets
        self.size = tuple(spec["size"])
        W, H = self.size
        self.W, self.H, self.u = W, H, H / 1080.0
        self.vig = vignette(self.size)
        self.host = spec.get("host") or {}
        self._readers = {}

    # ---- sources
    def pic(self, key):
        p = (self.a.get("pictures") or {}).get(key) if key else None
        return p if p and os.path.isfile(p) else self.a.get("fallback")

    def host_still(self):
        return self.host.get("set_image") or self.a.get("fallback")

    def host_frame(self, shot, size, crop, t_local):
        """The host panel: a talking clip frame when there are clips, else his set picture with a slow push."""
        clip = shot.get("talk")
        if clip and os.path.isfile(clip):
            k = (shot["i"], size, crop)
            r = self._readers.get(k)
            if r is None:
                r = self._readers[k] = ClipReader(clip, size, crop, start=shot.get("talk_at", 0.0), fps=self.spec["fps"],
                                                   loop=shot.get("talk_loop", True))
            fr = r.next()
            if fr is not None:
                return fr
        src = load(self.host_still())
        cx, cy, cw, ch = crop
        box = (int((cx - cw / 2) * src.width), int((cy - ch / 2) * src.height), int((cx + cw / 2) * src.width), int((cy + ch / 2) * src.height))
        z = 1.0 + 0.04 * ease(t_local / max(0.1, shot["t1"] - shot["t0"]))
        env = self.a.get("env") or []
        if env:   # a still host leans in a touch on the loud words, so he is never frozen while he talks
            k = int((shot["t0"] + t_local) * self.spec["fps"])
            z += 0.012 * (env[k] if 0 <= k < len(env) else 0.0)
        bw, bh = (box[2] - box[0]) / z, (box[3] - box[1]) / z
        mx, my = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        box = (mx - bw / 2, my - bh / 2, mx + bw / 2, my + bh / 2)
        return src.transform(size, Image.EXTENT, box, resample=Image.BILINEAR)

    def close(self):
        for r in self._readers.values():
            r.close()

    # ---- frame
    def frame(self, shot, t):
        tl, dur = t - shot["t0"], max(0.1, shot["t1"] - shot["t0"])
        f = clamp(tl / dur)
        kind = shot["kind"]
        W, H, u = self.W, self.H, self.u
        if kind == "host":
            base = self.host_frame(shot, self.size, (0.5, 0.5, 1.0, 1.0), tl).convert("RGBA")
        elif kind == "split":
            base = Image.new("RGBA", self.size, (0, 0, 0, 255))
            lw = int(W * 0.44)
            base.paste(self.host_frame(shot, (lw, H), (0.5, 0.5, (lw / H) / (16 / 9), 1.0), tl), (0, 0))
            right = kenburns(headroom(self.pic(shot["pic"]), (W - lw, H)), (W - lw, H), shot["move"], f)
            base.paste(right, (lw, 0))
        elif kind in ("pip", "broll"):
            base = kenburns(headroom(self.pic(shot["pic"]), self.size), self.size, shot["move"], f).convert("RGBA")
        else:
            base = self.card_bg(shot, f)
        base.alpha_composite(self.vig)
        if kind == "pip":
            self.pip(base, shot, tl)
        elif kind in ("product", "compare"):
            self.products(base, shot, t)
        elif kind == "data":
            self.data(base, shot, t)
        elif kind == "checklist":
            self.checklist(base, shot, t)
        elif kind == "bars":
            self.bars(base, shot, t)
        elif kind == "big":
            self.big(base, shot, t)
        if shot.get("card", {}).get("title"):
            self.chip(base, shot["card"]["title"], tl)
        if shot.get("namebar"):
            self.namebar(base, tl)
        for c in self.spec.get("chapters", []):
            if c["t"] <= t < c["t"] + 2.0:
                self.chapter(base, c["text"], t - c["t"])
        end = self.spec["duration"]
        if self.spec.get("subscribe", True) and end - 9 <= t < end - 3:
            self.subscribe(base, t - (end - 9))
        return base.convert("RGB")

    # ---- layers
    def card_bg(self, shot, f):
        p = self.pic(shot.get("bg"))
        k = ("bg", p, self.size)
        if k not in _IMG_CACHE:
            im = headroom(p, self.size).filter(ImageFilter.GaussianBlur(18 * self.u))
            dark = Image.new("RGB", im.size, (8, 9, 10))
            _IMG_CACHE[k] = Image.blend(im, dark, 0.58)
        return kenburns(_IMG_CACHE[k], self.size, "drift", f).convert("RGBA")

    def chip(self, base, text, tl):
        u = self.u
        ft = font("Inter-Bold.ttf", 30 * u)
        d = ImageDraw.Draw(base)
        tw = d.textlength(text, font=ft)
        w, h = int(tw + 32 * u), int(50 * u)
        x = int(60 * u - (w + 80 * u) * (1 - ease_out(tl / 0.35)))
        y = int(54 * u)
        d.rectangle((x, y, x + w, y + h), fill=(250, 250, 250, 255))
        d.text((x + 16 * u, y + h / 2), text, font=ft, fill=(12, 12, 12), anchor="lm")

    def _reveal(self, at, t, span=0.35):
        return clamp((t - at) / span)

    def data(self, base, shot, t):
        W, H, u = self.W, self.H, self.u
        items = shot["card"]["items"]
        n = len(items)
        gap = min(130 * u, 520 * u / max(1, n))
        y0 = H / 2 - gap * (n - 1) / 2
        x0, x1 = W * 0.24, W * 0.76
        lay = Image.new("RGBA", self.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        for j, it in enumerate(items):
            r = self._reveal(it["at"], t)
            if r <= 0:
                continue
            y = y0 + gap * j + 14 * u * (1 - ease_out(r))
            a = int(255 * ease_out(r))
            d.text((x0, y), it["label"], font=font("Inter-Bold.ttf", 34 * u), fill=(255, 255, 255, a), anchor="lm")
            col = COLOURS.get(it.get("colour") or "", WHITE)
            val = fmt_count(it["value"], it.get("num"), (t - it["at"]) / 0.7)
            d.text((x1, y), val, font=font("Outfit-ExtraBold.ttf", 62 * u), fill=col + (a,), anchor="rm")
            lw = (x1 - x0) * ease_out((t - it["at"] - 0.1) / 0.5)
            col_line = col if it.get("colour") else (255, 255, 255)
            d.rectangle((x0, y + 40 * u, x0 + lw, y + 43 * u), fill=col_line + (int(a * 0.55),))
        base.alpha_composite(lay)

    def checklist(self, base, shot, t):
        W, H, u = self.W, self.H, self.u
        items = shot["card"]["items"]
        n = len(items)
        gap = min(96 * u, 600 * u / max(1, n))
        y0 = H / 2 - gap * (n - 1) / 2
        x0 = W * 0.30
        lay = Image.new("RGBA", self.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        ft = font("Inter-Bold.ttf", 40 * u)
        for j, it in enumerate(items):
            r = self._reveal(it["at"], t)
            if r <= 0:
                continue
            y = y0 + gap * j
            a = int(255 * ease_out(r))
            if it.get("tick"):
                s = back(clamp((t - it["at"]) / 0.3))
                rr = 20 * u * s
                d.ellipse((x0 - rr, y - rr, x0 + rr, y + rr), fill=GREEN + (a,))
                if s > 0.5:
                    d.line([(x0 - 9 * u, y + 1 * u), (x0 - 2 * u, y + 8 * u), (x0 + 10 * u, y - 8 * u)], fill=(10, 40, 20, a), width=max(2, int(5 * u)))
            tx = x0 + 44 * u + 30 * u * (1 - ease_out(r))
            col = COLOURS.get(it.get("colour") or "", WHITE)
            d.text((tx, y), it["label"], font=ft, fill=col + (a,), anchor="lm")
            if it.get("strike"):
                tw = d.textlength(it["label"], font=ft)
                sl = tw * ease_out((t - it["at"] - 0.35) / 0.45)
                if sl > 0:
                    d.rectangle((tx - 6 * u, y - 3 * u, tx - 6 * u + sl + 12 * u, y + 3 * u), fill=RED + (255,))
        base.alpha_composite(lay)

    def bars(self, base, shot, t):
        W, H, u = self.W, self.H, self.u
        items = shot["card"]["items"]
        n = len(items)
        top = max([it.get("num") or 0 for it in items] + [1])
        gap = min(120 * u, 560 * u / max(1, n))
        y0 = H / 2 - gap * (n - 1) / 2
        xl, xb, xe = W * 0.10, W * 0.27, W * 0.72
        lay = Image.new("RGBA", self.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        for j, it in enumerate(items):
            r = self._reveal(it["at"], t)
            if r <= 0:
                continue
            y = y0 + gap * j
            a = int(255 * ease_out(r))
            d.text((xb - 24 * u, y), it["label"], font=font("Inter-Bold.ttf", 28 * u), fill=(255, 255, 255, a), anchor="rm")
            d.rectangle((xb, y - 22 * u, xe, y + 22 * u), fill=(255, 255, 255, int(a * 0.12)))
            g = ease_out((t - it["at"]) / 0.8)
            x = xb + (xe - xb) * ((it.get("num") or 0) / top) * g
            col = COLOURS.get(it.get("colour") or "", GREEN)
            if x > xb:
                d.rectangle((xb, y - 22 * u, x, y + 22 * u), fill=col + (a,))
            d.text((x + 18 * u, y), fmt_count(it["value"], it.get("num"), g), font=font("Outfit-ExtraBold.ttf", 34 * u),
                   fill=(255, 255, 255, a), anchor="lm")
        base.alpha_composite(lay)

    def big(self, base, shot, t):
        W, H, u = self.W, self.H, self.u
        it = (shot["card"]["items"] or [{"label": "", "value": "", "at": shot["t0"]}])[0]
        r = self._reveal(it["at"], t, 0.4)
        if r <= 0:
            return
        lay = Image.new("RGBA", self.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        from .csvplan import number_of
        if it["value"] and number_of(it["value"]) is not None and number_of(it["label"]) is None:
            big_txt, small = it["value"], it["label"]
        else:
            big_txt, small = it["label"], it["value"]
        num = number_of(big_txt)
        col = COLOURS.get(it.get("colour") or "", YELLOW)
        px = 210 * u
        while d.textlength(big_txt, font=font("Outfit-ExtraBold.ttf", px)) > W * 0.86 and px > 40 * u:
            px -= 8 * u
        d.text((W / 2, H * 0.46), fmt_count(big_txt, num, (t - it["at"]) / 0.9), font=font("Outfit-ExtraBold.ttf", px),
               fill=col + (int(255 * r),), anchor="mm", stroke_width=int(4 * u), stroke_fill=(0, 0, 0, int(180 * r)))
        if small:
            d.text((W / 2, H * 0.66), small, font=font("Inter-Bold.ttf", 46 * u), fill=(255, 255, 255, int(255 * r)), anchor="mm")
        s = 0.9 + 0.1 * back(r)
        if s != 1:
            lay = lay.resize((int(W * s), int(H * s)), Image.BILINEAR)
            full = Image.new("RGBA", self.size, (0, 0, 0, 0))
            full.alpha_composite(lay, ((W - lay.width) // 2, (H - lay.height) // 2))
            lay = full
        base.alpha_composite(lay)

    def product_card(self, path, w, h, name=""):
        k = ("pcard", path, w, h, name)
        if k not in _IMG_CACHE:
            u = self.u
            card = rounded((w, h), int(22 * u), (255, 255, 255, 255))
            if path and os.path.isfile(path):
                im = trim_white(Image.open(path).convert("RGB"))
                pad = int(26 * u)
                s = min((w - 2 * pad) / im.width, (h - 2 * pad) / im.height)
                im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
                card.paste(im, ((w - im.width) // 2, (h - im.height) // 2), rounded(im.size, int(10 * u), (255, 255, 255, 255)))
            elif name:   # no photo yet: the product's name, so the card still says what it is
                d = ImageDraw.Draw(card)
                words, lines, cur = name.upper().split(), [], ""
                ft = font("Outfit-ExtraBold.ttf", 54 * u)
                for wd in words:
                    if d.textlength((cur + " " + wd).strip(), font=ft) > w * 0.8 and cur:
                        lines.append(cur)
                        cur = wd
                    else:
                        cur = (cur + " " + wd).strip()
                lines.append(cur)
                for j, ln in enumerate(lines[:5]):
                    d.text((w / 2, h / 2 + (j - (len(lines[:5]) - 1) / 2) * 62 * u), ln, font=ft, fill=(30, 30, 30), anchor="mm")
            _IMG_CACHE[k] = shadowed(card, int(18 * u))
        return _IMG_CACHE[k]

    def products(self, base, shot, t):
        W, H, u = self.W, self.H, self.u
        ps = shot["card"]["products"]
        n = max(1, len(ps))
        if n == 1:
            w, h, xs, cy = int(H * 0.62), int(H * 0.78), [W / 2], H * 0.5
        else:
            w = int(min(W * 0.27, (W * 0.86) / n - 30 * u))
            h = int(w * 1.15)
            step = w + 50 * u
            xs = [W / 2 + (j - (n - 1) / 2) * step for j in range(n)]
            cy = H * 0.46
        d = ImageDraw.Draw(base)
        for j, p in enumerate(ps):
            r = clamp((t - p["at"]) / 0.4)
            if r <= 0:
                continue
            card = self.product_card((self.a.get("pictures") or {}).get(p["pic"]), w, h, p.get("name", ""))
            s = (0.86 + 0.14 * back(r)) * (1 + 0.035 * ease(clamp((t - p["at"]) / max(1.0, shot["t1"] - p["at"]))))
            paste_scaled(base, card, xs[j], cy, s, ease_out(r))
            if p.get("label") and n > 1:
                d.text((xs[j], cy + h / 2 + 46 * u), p["label"], font=font("Inter-Bold.ttf", 30 * u),
                       fill=(255, 255, 255, int(255 * ease_out(r))), anchor="mm")

    def pip(self, base, shot, tl):
        W, H, u = self.W, self.H, self.u
        D = int(W * 0.165)
        s = back(clamp(tl / 0.35))
        if s <= 0.02:
            return
        face = self.host_frame(shot, (D, D), (0.5, 0.36, 0.42 * (9 / 16), 0.42), tl).convert("RGBA")
        mask = Image.new("L", (D, D), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, D - 1, D - 1), fill=255)
        face.putalpha(mask)
        ring = Image.new("RGBA", (D + int(10 * u), D + int(10 * u)), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((0, 0, ring.width - 1, ring.height - 1), fill=(255, 255, 255, 255))
        ring.alpha_composite(face, (int(5 * u), int(5 * u)))
        paste_scaled(base, shadowed(ring, int(10 * u)), W * 0.875, H * 0.21, s)

    def namebar(self, base, tl):
        u = self.u
        r = ease_out((tl - 0.6) / 0.4) * (1 - ease_out((tl - 4.6) / 0.4))
        if r <= 0:
            return
        name = str(self.host.get("name", "")).upper()
        tag = str(self.host.get("tagline", "")).upper()
        d = ImageDraw.Draw(base)
        x = int(70 * u - 500 * u * (1 - r))
        y = int(self.H - 210 * u)
        f1, f2 = font("Outfit-ExtraBold.ttf", 54 * u), font("Inter-Bold.ttf", 24 * u)
        w = int(max(d.textlength(name, font=f1), d.textlength(tag, font=f2)) + 60 * u)
        d.rectangle((x, y, x + int(10 * u), y + int(110 * u)), fill=YELLOW + (255,))
        d.rectangle((x + int(10 * u), y, x + w, y + int(70 * u)), fill=(14, 14, 14, int(230 * r)))
        d.text((x + int(30 * u), y + int(35 * u)), name, font=f1, fill=(255, 255, 255, int(255 * r)), anchor="lm")
        d.rectangle((x + int(10 * u), y + int(70 * u), x + w, y + int(110 * u)), fill=(250, 250, 250, int(240 * r)))
        d.text((x + int(30 * u), y + int(90 * u)), tag, font=f2, fill=(20, 20, 20, int(255 * r)), anchor="lm")

    def chapter(self, base, text, tc):
        W, H, u = self.W, self.H, self.u
        r = ease_out(tc / 0.35) * (1 - ease_out((tc - 1.6) / 0.35))
        if r <= 0:
            return
        lay = Image.new("RGBA", self.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        bw = W * r
        d.rectangle((0, H * 0.40, bw, H * 0.60), fill=(10, 10, 10, 215))
        d.rectangle((0, H * 0.40, bw, H * 0.40 + 8 * u), fill=YELLOW + (255,))
        d.text((W / 2 - 60 * u * (1 - r), H * 0.5), str(text).upper(), font=font("Outfit-ExtraBold.ttf", 84 * u),
               fill=(255, 255, 255, int(255 * clamp((tc - 0.12) / 0.3))), anchor="mm")
        base.alpha_composite(lay)

    def subscribe(self, base, ts):
        W, H, u = self.W, self.H, self.u
        r = back(clamp(ts / 0.4)) * (1 - ease_out((ts - 5.6) / 0.4))
        if r <= 0.02:
            return
        btn = Image.new("RGBA", (int(330 * u), int(76 * u)), (0, 0, 0, 0))
        d = ImageDraw.Draw(btn)
        clicked = ts > 1.6
        d.rounded_rectangle((0, 0, btn.width - 1, btn.height - 1), radius=int(12 * u), fill=((90, 90, 90, 255) if clicked else (220, 30, 30, 255)))
        d.text((btn.width / 2, btn.height / 2), "SUBSCRIBED" if clicked else "SUBSCRIBE", font=font("Inter-Bold.ttf", 32 * u),
               fill=(255, 255, 255), anchor="mm")
        paste_scaled(base, shadowed(btn, int(8 * u)), W * 0.16, H * 0.86, r)


class ClipReader:
    """Frames of a talking clip at one size/crop, looped, read through ffmpeg."""

    def __init__(self, path, size, crop, start=0.0, fps=30, loop=True):
        w, h = size
        cx, cy, cw, ch = crop
        vf = (f"crop=iw*{cw:.4f}:ih*{ch:.4f}:iw*{cx - cw / 2:.4f}:ih*{cy - ch / 2:.4f},scale={w}:{h}:flags=bilinear,fps={fps}")
        self.size, self.n, self.last = size, w * h * 3, None
        # A spoken clip (Flow voice) plays once from its speech and then holds its last frame; a silent one loops.
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", *(["-stream_loop", "-1"] if loop else []), "-ss", f"{start:.2f}", "-i", path, "-an",
                                   "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)

    def next(self):
        b = self.p.stdout.read(self.n)
        if len(b) == self.n:
            self.last = Image.frombytes("RGB", self.size, b)
        return self.last

    def close(self):
        try:
            self.p.kill()
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ encode
def _encode_shot(args):
    spec, assets, i, f0, f1, out, crf = args
    shot = dict(spec["shots"][i], i=i)
    dr = Drawer(spec, assets)
    W, H = spec["size"]
    fps = spec["fps"]
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
                          "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
                          "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", out], stdin=subprocess.PIPE)
    try:
        for fr in range(f0, f1):
            p.stdin.write(dr.frame(shot, fr / fps).tobytes())
    finally:
        p.stdin.close()
        p.wait()
        dr.close()
    if p.returncode:
        raise RuntimeError(f"ffmpeg failed on shot {i}")
    return i


def voice_envelope(path, fps, duration):
    """0..1 loudness per frame, smoothed (attack fast, release slow)."""
    try:
        v = _decode(path)
    except Exception:  # noqa: BLE001
        return []
    hop = SR // fps
    n = int(duration * fps) + 1
    v = np.pad(v, (0, max(0, n * hop - len(v))))[:n * hop]
    rms = np.sqrt(np.mean(v.reshape(n, hop) ** 2, axis=1))
    ref = np.percentile(rms[rms > 1e-3], 90) if np.any(rms > 1e-3) else 1.0
    e = np.clip(rms / max(ref, 1e-4), 0, 1)
    out, cur = [], 0.0
    for x in e:
        cur = x if x > cur else cur * 0.85
        out.append(round(float(cur), 3))
    return out


def render_picture(spec, assets, out, workers=None, progress=None, cancel=None, crf=19):
    fps = spec["fps"]
    if spec.get("voice_path") and "env" not in assets:
        assets = dict(assets, env=voice_envelope(spec["voice_path"], fps, spec["duration"]))
    shots = spec["shots"]
    total = int(round(spec["duration"] * fps))
    starts = [int(round(s["t0"] * fps)) for s in shots] + [total]
    starts[0] = 0
    with tempfile.TemporaryDirectory() as wd:
        jobs = []
        for i in range(len(shots)):
            f0, f1 = starts[i], max(starts[i] + 1, starts[i + 1])
            jobs.append((spec, assets, i, f0, f1, os.path.join(wd, f"s{i:04d}.mp4"), crf))
        workers = workers or max(1, min(6, (os.cpu_count() or 4) - 2))
        made = set()

        def tick():
            if progress:
                progress(len(made) / len(jobs), f"drawing shot {len(made)}/{len(jobs)}")
            if cancel and cancel():
                raise Stopped("Stopped.")

        if workers > 1:
            try:   # spawn: the worker start the packaged app uses (Rep Theory, Stickman); one core if workers can't start
                import multiprocessing as mp
                with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
                    futs = {ex.submit(_encode_shot, j): j[2] for j in jobs}
                    try:
                        for fu in as_completed(futs):
                            made.add(fu.result())
                            tick()
                    except Stopped:
                        for g in futs:
                            g.cancel()
                        raise
            except Stopped:
                raise
            except Exception as e:  # noqa: BLE001 - BrokenProcessPool and friends: finish on this core
                if progress:
                    progress(len(made) / len(jobs), f"workers failed ({type(e).__name__}); drawing on one core")
        for j in jobs:
            if j[2] not in made:
                made.add(_encode_shot(j))
                tick()
        lst = os.path.join(wd, "list.txt")
        with open(lst, "w") as fh:
            for j in jobs:
                fh.write(f"file '{j[5]}'\n")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", str(out)], check=True)
    return out


# ------------------------------------------------------------------ sound
SR = 48000


def _decode(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).copy()


def _db(x):
    return 10 ** (x / 20)


def mix(spec, out_wav, sound="fx"):
    """Voice (levelled to about -14 LUFS), + effects on the card cues, + (sound == 'music') a quiet bed that dips under speech."""
    v = _decode(spec["voice_path"])
    n = int(spec["duration"] * SR) + SR
    out = np.zeros(n, np.float32)
    rms = np.sqrt(np.mean(v[np.abs(v) > 0.01] ** 2)) if np.any(np.abs(v) > 0.01) else 0.1
    v = v * (_db(-17.0) / max(rms, 1e-4))
    out[:min(n, len(v))] += v[:n]
    if sound in ("fx", "music"):
        cache = {}
        last = {}
        for e in spec.get("sfx", []):
            name = e["name"]
            if name not in SFX or e["t"] - last.get(name, -9) < 0.25:
                continue
            last[name] = e["t"]
            rel, gain = SFX[name]
            if name not in cache:
                try:
                    s = _decode(SFX_DIR / rel)
                    cache[name] = s / max(1e-4, np.max(np.abs(s)))
                except Exception:  # noqa: BLE001
                    cache[name] = None
            s = cache[name]
            if s is None:
                continue
            i0 = int(max(0, e["t"] - (0.12 if name == "whoosh" else 0)) * SR)
            k = min(len(s), n - i0)
            if k > 0:
                out[i0:i0 + k] += s[:k] * _db(gain)
    if sound == "music" and (MUSIC_DIR / MUSIC_BED).is_file():
        m = _decode(MUSIC_DIR / MUSIC_BED)
        if len(m):
            m = np.tile(m, int(math.ceil(n / len(m))))[:n]
            m = m / max(1e-4, np.sqrt(np.mean(m ** 2))) * _db(-34.0)
            env = np.abs(np.pad(v, (0, max(0, n - len(v))))[:n])
            win = SR // 4
            env = np.convolve(env, np.ones(win) / win, mode="same")
            duck = np.where(env > 0.01, _db(-6), 1.0).astype(np.float32)
            duck = np.convolve(duck, np.ones(SR // 2) / (SR // 2), mode="same")
            fade = np.minimum(1, np.minimum(np.arange(n) / (2 * SR), (n - np.arange(n)) / (3 * SR)))
            out += m * duck * fade
    peak = np.max(np.abs(out)) or 1
    if peak > _db(-1):
        out *= _db(-1) / peak
    out = out[:int(spec["duration"] * SR)]
    pcm = (np.clip(out, -1, 1) * 32767).astype("<i2").tobytes()
    import wave
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return {"peak_db": round(20 * math.log10(max(1e-6, np.max(np.abs(out)))), 1)}


# ------------------------------------------------------------------ thumbnail
def thumbnail(picture, lines, out, size=(1280, 720)):
    W, H = size
    im = cover(Image.open(picture).convert("RGB"), size).convert("RGBA")
    grad = Image.new("RGBA", size, (0, 0, 0, 0))
    g = np.zeros((H, W), np.uint8)
    g[:, :] = (np.clip(1 - np.arange(W) / (W * 0.6), 0, 1) * 150).astype(np.uint8)[None, :]
    grad.putalpha(Image.fromarray(g))
    im.alpha_composite(grad)
    d = ImageDraw.Draw(im)
    u = H / 720
    y = 40 * u
    for j, line in enumerate([l for l in lines if l][:2]):
        line = line.upper()
        px = 120 * u
        ft = font("Outfit-ExtraBold.ttf", px)
        while d.textlength(line, font=ft) > W * 0.62 and px > 40:
            px -= 4
            ft = font("Outfit-ExtraBold.ttf", px)
        d.text((36 * u, y), line, font=ft, fill=(WHITE if j == 0 else YELLOW), stroke_width=int(8 * u), stroke_fill=(0, 0, 0))
        y += px * 1.02
    im.convert("RGB").save(out, quality=92)
    return out
