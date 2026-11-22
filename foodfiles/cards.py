"""Food Files shot drawer: every shot kind, frame by frame (PIL). Subclass of Prepper Host's Drawer (host panel, talking
clips, Ken Burns, picture loading), with the Food Files card pack on top.

Host layers: word captions (2-4 words, one yellow keyword), handwritten side note, person name bar, rubber stamp.
Cards: title open, #N item card, next-up sting, photo card, map, case folder, headline, quote, tweet, big number,
flow chart, icon explainer, timeline. Every card builds piece by piece and drifts, so no screen is ever still.
"""
import math
import os
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from prepper_host import render as R
from . import icons, look as L, maps

clamp, ease, ease_out, back = R.clamp, R.ease, R.ease_out, R.back
_FONTS = {}
_STATIC = {}


def font(name, px):
    k = (name, int(px))
    if k not in _FONTS:
        try:
            _FONTS[k] = ImageFont.truetype(str(L.font_path(name)), max(6, int(px)))
        except OSError:
            _FONTS[k] = ImageFont.load_default()
    return _FONTS[k]


def wrap(d, text, ft, width):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=ft) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_font(d, text, name, px, width, lines=1, min_px=20):
    """The biggest size (<= px) at which text fits in `lines` lines of `width`."""
    while px > min_px:
        ft = font(name, px)
        if len(wrap(d, text, ft, width)) <= lines:
            return ft
        px *= 0.92
    return font(name, min_px)


def _alpha(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.split()[3].point(lambda v: int(v * a)))
    return im


def _rot(im, deg):
    return im.rotate(deg, resample=Image.BICUBIC, expand=True)


# ------------------------------------------------------------------ backgrounds and tape
def background(size, tone):
    k = ("bg", tone, size)
    if k in _STATIC:
        return _STATIC[k]
    W, H = size
    import numpy as np
    y, x = np.ogrid[0:H, 0:W]
    d = np.sqrt(((x - W / 2) / (W * 0.62)) ** 2 + ((y - H / 2) / (H * 0.62)) ** 2)
    d = np.clip(d, 0, 1.4)[..., None]
    c0, c1 = {"cream": (L.CREAM, L.CREAM_DARK), "dark": (L.MAROON_2, (18, 8, 10)), "navy": ((34, 44, 74), (12, 16, 30)),
              "red": ((70, 18, 22), (24, 6, 8))}.get(tone, (L.MAROON_2, (18, 8, 10)))
    arr = (np.array(c0)[None, None, :] * (1 - d / 1.4) + np.array(c1)[None, None, :] * (d / 1.4)).astype("uint8")
    im = Image.fromarray(np.broadcast_to(arr, (H, W, 3)).copy(), "RGB").convert("RGBA")
    if tone == "cream":   # a fine paper grain
        rnd = np.random.default_rng(3).integers(0, 14, (H // 2, W // 2), dtype="uint8")
        g = Image.fromarray(rnd, "L").resize((W, H))
        im = Image.composite(Image.new("RGBA", size, (120, 100, 80, 255)), im, g.point(lambda v: v))
    _STATIC[k] = im
    return im


def tape(width, h, offset=0.0):
    """A yellow/black hazard tape strip; offset scrolls the stripes (0..1 = one stripe pair)."""
    k = ("tape", width, h)
    if k not in _STATIC:
        step = h * 1.1
        strip = Image.new("RGBA", (int(width + step * 4), h), L.YELLOW + (255,))
        d = ImageDraw.Draw(strip)
        x = -h
        while x < strip.width + h:
            d.polygon([(x, h), (x + step / 2, h), (x + step / 2 + h, 0), (x + h, 0)], fill=(20, 18, 18, 255))
            x += step
        _STATIC[k] = (strip, step)
    strip, step = _STATIC[k]
    dx = int((offset % 1.0) * step)
    return strip.crop((dx, 0, dx + width, h))


def pill(d, xy, text, ft, fg, bg, anchor="mm", pad=(0.6, 0.28), radius=0.5):
    tw = d.textlength(text, font=ft)
    fh = ft.size
    w, h = tw + fh * pad[0] * 2, fh * (1 + pad[1] * 2)
    x, y = xy
    if anchor[0] == "m":
        x -= w / 2
    elif anchor[0] == "r":
        x -= w
    if anchor[1] == "m":
        y -= h / 2
    elif anchor[1] == "b":
        y -= h
    d.rounded_rectangle((x, y, x + w, y + h), radius=h * radius, fill=bg)
    d.text((x + w / 2, y + h / 2), text, font=ft, fill=fg, anchor="mm")
    return (x, y, x + w, y + h)


def stamp_image(text, px, colour=L.RED):
    k = ("stamp", text, int(px), colour)
    if k in _STATIC:
        return _STATIC[k]
    lines = [text] if len(text) <= 12 else wrap(ImageDraw.Draw(Image.new("RGB", (1, 1))), text, font(L.TITLE_FONT, px),
                                                 px * 7)
    ft = font(L.TITLE_FONT, px)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = max(tmp.textlength(l, font=ft) for l in lines)
    lh = px * 1.08
    W, H = int(tw + px * 1.0), int(lh * len(lines) + px * 0.7)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    bw = max(3, int(px / 9))
    d.rounded_rectangle((bw, bw, W - bw, H - bw), radius=px * 0.18, outline=colour + (255,), width=bw)
    for i, l in enumerate(lines):
        d.text((W / 2, px * 0.35 + lh * (i + 0.5)), l, font=ft, fill=colour + (255,), anchor="mm")
    # worn ink: knock out speckles
    import numpy as np
    a = np.asarray(im.split()[3]).astype("float32")
    rnd = np.random.default_rng(len(text)).random(a.shape)
    a[rnd < 0.10] *= 0.25
    im.putalpha(Image.fromarray(a.astype("uint8")))
    im = _rot(im, -9)
    _STATIC[k] = im
    return im


# ------------------------------------------------------------------ the drawer
class FoodDrawer(R.Drawer):
    def __init__(self, spec, assets):
        super().__init__(spec, assets)
        self.brand = spec.get("brand", "FOOD FILES")

    def host_still(self):
        return getattr(self, "_cur_still", None) or super().host_still()

    def host_frame(self, shot, size, crop, t_local):
        self._cur_still = self.pic_path(shot.get("still"))     # free test mode: a Flow pose picture of the host
        return super().host_frame(shot, size, crop, t_local)

    def frame(self, shot, t):
        if self.spec.get("wall"):           # a Wall Moment covers this time: the evidence wall, opaque
            from . import wall_moments as WM
            wf = WM.frame_at(self.spec, t)
            if wf is not None:
                return wf if wf.size == tuple(self.size) else wf.resize(tuple(self.size), Image.LANCZOS)
        tl, dur = t - shot["t0"], max(0.1, shot["t1"] - shot["t0"])
        f = clamp(tl / dur)
        kind = shot["kind"]
        W, H = self.W, self.H
        if kind == "host":
            crop = (0.5, 0.42, 0.80, 0.80) if shot.get("punch") else (0.5, 0.5, 1.0, 1.0)   # punch-in = a jump cut
            base = self.host_frame(shot, self.size, crop, tl).convert("RGBA")
            base.alpha_composite(self.vig)
        elif kind == "split":
            base = Image.new("RGBA", self.size, (0, 0, 0, 255))
            lw = int(W * 0.44)
            base.paste(self.host_frame(shot, (lw, H), (0.5, 0.5, (lw / H) / (16 / 9), 1.0), tl), (0, 0))
            right = R.kenburns(R.headroom(self.pic(shot.get("pic")), (W - lw, H)), (W - lw, H), shot.get("move", "push_in"), f)
            base.paste(right, (lw, 0))
            base.alpha_composite(self.vig)
        elif kind in ("scene", "pip"):
            base = R.kenburns(R.headroom(self.pic(shot.get("pic")), self.size), self.size, shot.get("move", "push_in"), f)
            base = base.convert("RGBA")
            base.alpha_composite(self.vig)
            if kind == "pip":
                self.pip(base, shot, tl)
        else:
            base = self.card(shot, t, tl, f)
        if kind in ("host", "split", "scene", "pip"):
            self.captions(base, shot, t)
        if shot.get("banner"):
            self.banner(base, shot, t)
        if shot.get("note"):
            self.note(base, shot, t)
        if shot.get("person"):
            self.person(base, shot, t)
        if shot.get("stamp"):
            self.stamp(base, shot, t)
        if shot.get("source"):
            self.source(base, shot["source"], tl)
        end = self.spec["duration"]
        if self.spec.get("subscribe", True) and end - 9 <= t < end - 3:
            self.subscribe(base, t - (end - 9))
        return base.convert("RGB")

    # ---------------------------------------------------------------- cards
    def card(self, shot, t, tl, f):
        kind = shot["kind"]
        tone = shot.get("tone") or "dark"
        if kind in ("photo", "clip") and self.pic_path(shot.get("pic")):
            base = self.blurred(shot.get("pic"), f)
        else:
            base = background(self.size, tone).copy()
        # the whole card layer drifts in a touch, so long builds never sit still
        lay = Image.new("RGBA", self.size, (0, 0, 0, 0))
        getattr(self, "c_" + kind, self.c_unknown)(lay, shot, t, tl, f)
        z = 1.0 + 0.025 * ease(f)
        if z > 1.001:
            W, H = self.size
            w, h = W / z, H / z
            lay = lay.transform(self.size, Image.EXTENT, ((W - w) / 2, (H - h) / 2, (W + w) / 2, (H + h) / 2), Image.BILINEAR)
        base.alpha_composite(lay)
        head = shot.get("card", {}).get("header")
        if head and kind not in ("title", "number", "next"):
            self.header(base, head, tl, tone)
        return base

    def blurred(self, key, f):
        p = self.pic(key)
        k = ("blur", p, self.size)
        if k not in R._IMG_CACHE:
            im = R.headroom(p, self.size).filter(ImageFilter.GaussianBlur(22 * self.u))
            R._IMG_CACHE[k] = Image.blend(im, Image.new("RGB", im.size, (20, 14, 14)), 0.45)
        return R.kenburns(R._IMG_CACHE[k], self.size, "drift", f).convert("RGBA")

    def header(self, base, text, tl, tone):
        u = self.u
        r = ease_out(tl / 0.3)
        d = ImageDraw.Draw(base)
        ft = font(L.TITLE_FONT, 40 * u)
        fg, bg = ((L.YELLOW, (24, 20, 20, 245)) if tone == "cream" else ((24, 20, 20), L.YELLOW + (255,)))
        pill(d, (self.W / 2, 40 * u - 90 * u * (1 - r)), str(text).upper(), ft, fg, bg, anchor="mt", radius=0.18)

    def c_unknown(self, lay, shot, t, tl, f):
        pass

    def c_title(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        d = ImageDraw.Draw(lay)
        th = int(70 * u)
        r = ease_out(tl / 0.45)
        tp = tape(W, th, tl * 0.25)
        lay.alpha_composite(tp, (int(-W * (1 - r)), int(40 * u)))
        lay.alpha_composite(tape(W, th, -tl * 0.25), (int(W * (1 - r)), int(H - 40 * u - th)))
        lines = shot["card"].get("lines") or [self.spec.get("title", "")]
        sizes = [0.62, 1.0, 0.62] if len(lines) == 3 else ([0.6, 1.0] if len(lines) == 2 else [1.0])
        base_px = 170 * u
        y = H / 2 - sum(base_px * s * 1.02 for s in sizes) / 2
        for i, (line, s) in enumerate(zip(lines, sizes)):
            a = back(clamp((tl - 0.25 - 0.28 * i) / 0.35))
            px = base_px * s
            ft = fit_font(d, line.upper(), L.TITLE_FONT, px, W * 0.8)
            col = L.RED if s >= 1.0 else L.CREAM
            if a > 0.02:
                img = Image.new("RGBA", (int(W), int(px * 1.4)), (0, 0, 0, 0))
                di = ImageDraw.Draw(img)
                di.text((W / 2 + 6 * u, px * 0.7 + 6 * u), line.upper(), font=ft, fill=(0, 0, 0, 160), anchor="mm")
                di.text((W / 2, px * 0.7), line.upper(), font=ft, fill=col + (255,), anchor="mm")
                R.paste_scaled(lay, img, W / 2, y + px * 0.55, 0.7 + 0.3 * a, clamp(a))
            y += px * 1.02
        d.text((W / 2, H - 40 * u - th - 34 * u), self.brand, font=font(L.BODY_FONT, 22 * u),
               fill=L.CREAM + (int(200 * clamp((tl - 1.0) / 0.5)),), anchor="mm")

    def c_number(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        d = ImageDraw.Draw(lay)
        d.rectangle((0, 0, W, H), fill=L.CREAM + (255,))
        r = ease_out(tl / 0.35)
        slab_w = W * 0.36
        x1 = slab_w * r
        d.polygon([(0, 0), (x1 + W * 0.06, 0), (x1 - W * 0.02, H), (0, H)], fill=L.RED + (255,))
        num = f"#{c.get('num', '')}"
        nft = font(L.TITLE_FONT, 330 * u)
        nr = back(clamp((tl - 0.2) / 0.35))
        if nr > 0.02:
            img = Image.new("RGBA", (int(W * 0.4), int(H * 0.6)), (0, 0, 0, 0))
            di = ImageDraw.Draw(img)
            di.text((img.width / 2 + 10 * u, img.height / 2 + 10 * u), num, font=nft, fill=(90, 10, 14, 200), anchor="mm")
            di.text((img.width / 2, img.height / 2), num, font=nft, fill=L.WHITE + (255,), anchor="mm")
            R.paste_scaled(lay, img, slab_w * 0.48, H * 0.5, 0.6 + 0.4 * nr, clamp(nr))
        tx = W * 0.44
        prod = self.pic_path((c.get("pic")))
        tw = W * (0.27 if prod else 0.50)          # text width: narrower when the real product photo sits on the right
        if prod:
            self.framed(lay, prod, W * 0.845, H * 0.46, (W * 0.29, H * 0.64), 4.0, back(clamp((tl - 0.45) / 0.4)), f)
        sub = str(c.get("sub", "")).upper()
        name = str(c.get("name", "")).upper()
        if sub:
            a = clamp((tl - 0.45) / 0.3)
            ft = fit_font(d, sub, L.TITLE_FONT, 66 * u, tw)
            d.text((tx - 40 * u * (1 - ease_out(a)), H * 0.44), sub, font=ft, fill=L.INK + (int(255 * a),), anchor="ls")
        if name:
            a = clamp((tl - 0.7) / 0.3)
            ft = fit_font(d, name, L.TITLE_FONT, 96 * u, tw, lines=2)
            y = H * 0.46
            for line in wrap(d, name, ft, tw):
                y += ft.size * 1.02
                d.text((tx - 40 * u * (1 - ease_out(a)), y), line, font=ft, fill=L.RED + (int(255 * a),), anchor="ls")
            d.line((tx, H * 0.44 + 14 * u, tx + tw * ease_out(a), H * 0.44 + 14 * u), fill=L.YELLOW + (255,),
                   width=int(6 * u))
            yr = str(c.get("year", ""))
            if yr:
                b = back(clamp((tl - 1.0) / 0.3))
                if b > 0.02:
                    p = Image.new("RGBA", (int(260 * u), int(70 * u)), (0, 0, 0, 0))
                    pill(ImageDraw.Draw(p), (p.width / 2, p.height / 2), yr, font(L.BODY_FONT, 30 * u), L.WHITE,
                         (24, 20, 20, 255))
                    R.paste_scaled(lay, p, tx + 80 * u, y + 70 * u, b)
        th = int(56 * u)
        lay.alpha_composite(tape(W, th, tl * 0.2), (int(W * (1 - r)), int(H - th - 34 * u)))

    def c_next(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        d = ImageDraw.Draw(lay)
        th = int(64 * u)
        r = ease_out(tl / 0.35)
        lay.alpha_composite(tape(W, th, tl * 0.3), (0, int(30 * u - (th + 40 * u) * (1 - r))))
        pill(d, (W / 2, 30 * u + th / 2 - (th + 40 * u) * (1 - r)), "NEXT UP", font(L.TITLE_FONT, 44 * u), L.YELLOW,
             (20, 18, 18, 255), radius=0.1)
        pulse = 1 + 0.04 * math.sin(tl * 6)
        ic = icons.icon(shot["card"].get("icon"), int(800 * u)) if shot["card"].get("icon") else None
        if ic is not None:          # a dark silhouette of the next food behind the "?"
            sil = Image.new("RGBA", ic.size, (96, 22, 26, 255))
            sil.putalpha(ic.split()[3].point(lambda v: int(v * 0.9)))
            R.paste_scaled(lay, sil, W / 2, H * 0.50, (0.9 + 0.1 * ease_out(clamp((tl - 0.05) / 0.4))) * (1 + 0.03 * ease(f)),
                           ease_out(clamp((tl - 0.05) / 0.4)))
        q = Image.new("RGBA", (int(480 * u), int(600 * u)), (0, 0, 0, 0))
        dq = ImageDraw.Draw(q)
        dq.text((q.width / 2, q.height / 2), "?", font=font(L.TITLE_FONT, 540 * u), fill=L.RED + (240,), anchor="mm")
        glow = q.filter(ImageFilter.GaussianBlur(30 * u))
        R.paste_scaled(lay, glow, W / 2, H * 0.48, pulse * back(clamp((tl - 0.15) / 0.4)), 0.8)
        R.paste_scaled(lay, q, W / 2, H * 0.48, pulse * back(clamp((tl - 0.15) / 0.4)))
        text = str(shot["card"].get("text", "")).upper()
        if text:
            a = clamp((tl - 0.6) / 0.4)
            ft = fit_font(d, text, L.TITLE_FONT, 100 * u, W * 0.84)
            d.text((W / 2, H * 0.875), text, font=ft, fill=L.CREAM + (int(255 * a),), anchor="mm")

    def c_photo(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        p = self.pic(shot.get("pic"))
        if not p:
            return
        tilt = shot.get("tilt", -2.0)
        k = ("photo", p, self.size, tilt)
        if k not in _STATIC:
            src = Image.open(p).convert("RGB")
            mw, mh = W * 0.58, H * 0.66
            s = min(mw / src.width, mh / src.height)
            im = src.resize((max(1, int(src.width * s)), max(1, int(src.height * s))), Image.LANCZOS)
            b = int(14 * u)
            fr = Image.new("RGBA", (im.width + 2 * b, im.height + 2 * b), (252, 252, 250, 255))
            fr.paste(im, (b, b))
            _STATIC[k] = _rot(R.shadowed(fr, int(16 * u)), tilt)
        card = _STATIC[k]
        a = back(clamp(tl / 0.4))
        R.paste_scaled(lay, card, W / 2, H * 0.47, (0.85 + 0.15 * a) * (1 + 0.04 * ease(f)), clamp(a))
        cap = str(shot["card"].get("caption", "")).upper()
        if cap:
            r = ease_out(clamp((tl - 0.45) / 0.3))
            d = ImageDraw.Draw(lay)
            pill(d, (W / 2, H * 0.90 + 60 * u * (1 - r)), cap, font(L.TITLE_FONT, 40 * u), (24, 20, 20),
                 L.YELLOW + (int(255 * r),), radius=0.2)

    # ---------------------------------------------------------------- Phase 3 cards (reference types, our own drawing)
    def c_compare(self, lay, shot, t, tl, f):
        """Two coloured halves, a label and a big icon on each ("FRANCHISE OWNERS" vs "CORPORATE")."""
        W, H, u = self.W, self.H, self.u
        items = (shot["card"].get("items") or [])[:2]
        d = ImageDraw.Draw(lay)
        cols = (L.MAROON, (32, 78, 52))
        for j in range(2):
            r = ease_out(clamp((tl - 0.1 * j) / 0.4))
            x0 = W * j / 2
            if j == 0:
                d.rectangle((0, H * (1 - r), W / 2, H), fill=cols[0] + (255,))
            else:
                d.rectangle((W / 2, 0, W, H * r), fill=cols[1] + (255,))
            if j >= len(items):
                continue
            it = items[j]
            a = clamp((t - it["at"]) / 0.35)
            if a <= 0:
                continue
            lab = it["label"].upper()
            d.text((x0 + W / 4, H * 0.16), lab, font=fit_font(d, lab, L.TITLE_FONT, 80 * u, W * 0.42),
                   fill=L.CREAM + (int(255 * a),), anchor="mm")
            ic = icons.icon(it.get("icon"), int(H * 0.50)) if it.get("icon") else None
            if ic is not None:
                R.paste_scaled(lay, ic, x0 + W / 4, H * 0.56 + math.sin(tl * 2 + j) * 6 * u, 0.7 + 0.3 * back(a), clamp(a * 1.5))
            elif it["value"]:
                v = it["value"].upper()
                d.text((x0 + W / 4, H * 0.56), v, font=fit_font(d, v, L.TITLE_FONT, 180 * u, W * 0.40), fill=L.YELLOW + (int(255 * a),),
                       anchor="mm")
        if tl > 0.4:   # a "VS" coin on the seam
            a = back(clamp((tl - 0.4) / 0.3))
            coin = Image.new("RGBA", (int(150 * u), int(150 * u)), (0, 0, 0, 0))
            dc = ImageDraw.Draw(coin)
            dc.ellipse((0, 0, coin.width - 1, coin.height - 1), fill=L.YELLOW + (255,), outline=(24, 20, 20, 255), width=int(6 * u))
            dc.text((coin.width / 2, coin.height / 2), "VS", font=font(L.TITLE_FONT, 64 * u), fill=(24, 20, 20), anchor="mm")
            R.paste_scaled(lay, coin, W / 2, H * 0.56, a)

    def c_evidence(self, lay, shot, t, tl, f):
        """2-3 tagged evidence bags drop in, a little tilted."""
        W, H, u = self.W, self.H, self.u
        items = (shot["card"].get("items") or [])[:3]
        n = max(1, len(items))
        bw, bh = min(W * 0.26, W * 0.80 / n), H * 0.66
        for j, it in enumerate(items):
            a = clamp((t - it["at"]) / 0.35)
            if a <= 0:
                continue
            k = ("bag", it["label"], it.get("icon"), int(bw))
            if k not in _STATIC:
                bag = Image.new("RGBA", (int(bw), int(bh)), (0, 0, 0, 0))
                db = ImageDraw.Draw(bag)
                db.rounded_rectangle((0, 0, bw - 1, bh - 1), radius=14 * u, fill=(236, 238, 242, 235), outline=(150, 156, 166, 255),
                                     width=int(4 * u))
                db.rectangle((0, 0, bw, bh * 0.16), fill=(200, 40, 46, 255))
                db.text((bw / 2, bh * 0.08), "EVIDENCE", font=font(L.TITLE_FONT, 40 * u), fill=(255, 255, 255), anchor="mm")
                for y in (bh * 0.20, bh * 0.23):
                    db.line((14 * u, y, bw - 14 * u, y), fill=(170, 176, 186, 255), width=int(3 * u))
                ic = icons.icon(it.get("icon"), int(bw * 0.62)) if it.get("icon") else None
                if ic is not None:
                    bag.alpha_composite(ic, (int(bw * 0.19), int(bh * 0.30)))
                lab = it["label"].upper()
                db.rounded_rectangle((bw * 0.08, bh * 0.80, bw * 0.92, bh * 0.94), radius=8 * u, fill=(250, 246, 236, 255),
                                     outline=(24, 20, 20, 255), width=int(3 * u))
                db.text((bw / 2, bh * 0.87), lab, font=fit_font(db, lab, L.TITLE_FONT, 50 * u, bw * 0.78), fill=(24, 20, 20),
                        anchor="mm")
                _STATIC[k] = _rot(R.shadowed(bag, int(14 * u)), (-4, 3, -2)[j % 3])
            x = W / 2 + (j - (n - 1) / 2) * (bw + 50 * u)
            R.paste_scaled(lay, _STATIC[k], x, H * 0.56 - 80 * u * (1 - ease_out(a)), 0.9 + 0.1 * back(a), clamp(a * 1.4))

    def c_symptoms(self, lay, shot, t, tl, f):
        """A person on the left, red-cross symptom pills appearing on the right."""
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        d = ImageDraw.Draw(lay)
        who = icons.icon(c.get("who") or "kid", int(H * 0.76))
        if who is not None:
            a = back(clamp(tl / 0.4))
            sway = math.sin(tl * 1.6) * 0.02
            R.paste_scaled(lay, who.rotate(sway * 60, resample=Image.BICUBIC), W * 0.27, H * 0.56, 0.8 + 0.2 * a, clamp(a))
        items = c.get("items") or []
        n = max(1, len(items))
        gap = min(H * 0.21, H * 0.66 / n)
        y0 = H * 0.56 - gap * (n - 1) / 2
        for j, it in enumerate(items):
            a = clamp((t - it["at"]) / 0.3)
            if a <= 0:
                continue
            y = y0 + gap * j
            x = W * 0.50 + 60 * u * (1 - ease_out(a))
            r = 34 * u
            d.ellipse((x - r, y - r, x + r, y + r), fill=L.RED + (int(255 * a),))
            d.line((x - r * 0.45, y - r * 0.45, x + r * 0.45, y + r * 0.45), fill=(255, 255, 255, int(255 * a)), width=int(8 * u))
            d.line((x + r * 0.45, y - r * 0.45, x - r * 0.45, y + r * 0.45), fill=(255, 255, 255, int(255 * a)), width=int(8 * u))
            lab = it["label"].upper()
            d.text((x + r * 1.6, y), lab, font=fit_font(d, lab, L.TITLE_FONT, 84 * u, W * 0.40), fill=L.CREAM + (int(255 * a),),
                   anchor="lm")

    def c_states(self, lay, shot, t, tl, f):
        """Several states / countries light up one after another, each with its label."""
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        places = c.get("places") or []
        got = maps.layers_multi(tuple(p["place"] for p in places), (int(W * 0.90), int(H * 0.78)))
        if not got:
            return
        base, fills = got
        ox, oy = int(W * 0.05), int(H * 0.14)
        lay.alpha_composite(_alpha(base, ease_out(tl / 0.4)), (ox, oy))
        d = ImageDraw.Draw(lay)
        for p, (fill, pt) in zip(places, fills):
            a = ease(clamp((t - p["at"]) / 0.4))
            if a <= 0:
                continue
            lay.alpha_composite(_alpha(fill, a), (ox, oy))
            if p.get("label"):
                la = ease_out(clamp((t - p["at"] - 0.25) / 0.3))
                pill(d, (ox + pt[0], oy + pt[1] - 30 * u * (1 - la)), p["label"].upper(), font(L.TITLE_FONT, 34 * u), (24, 20, 20),
                     L.YELLOW + (int(255 * la),), radius=0.2)

    def c_browser(self, lay, shot, t, tl, f):
        """A web page mock (FAQ, product page): the site bar, a heading, the text typing in, a highlighter."""
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        fw = W * 0.66
        bar = 52 * u
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        ft = fit_font(probe, c.get("text", ""), L.BODY_SEMI, (70 if len(c.get("text", "")) < 90 else 52) * u, fw - 90 * u, lines=5)
        lines = wrap(probe, c.get("text", ""), ft, fw - 90 * u)[:6]
        fh = max(H * 0.56, min(H * 0.78, bar + 120 * u + len(lines) * ft.size * 1.4 + 80 * u))   # as tall as its text
        page = Image.new("RGBA", (int(fw), int(fh)), (252, 252, 252, 255))
        dp = ImageDraw.Draw(page)
        dp.rectangle((0, 0, fw, bar), fill=(232, 234, 238))
        for i, col in enumerate(((236, 90, 80), (240, 190, 60), (90, 190, 100))):
            dp.ellipse((20 * u + i * 28 * u, bar / 2 - 9 * u, 38 * u + i * 28 * u, bar / 2 + 9 * u), fill=col)
        dp.rounded_rectangle((120 * u, 10 * u, fw - 24 * u, bar - 10 * u), radius=12 * u, fill=(255, 255, 255))
        dp.text((140 * u, bar / 2), str(c.get("site") or "")[:70], font=font(L.BODY_SEMI, 22 * u), fill=(100, 100, 108), anchor="lm")
        dp.rectangle((0, bar, fw, bar + 70 * u), fill=(30, 44, 80))
        dp.text((36 * u, bar + 35 * u), str(c.get("heading") or "").upper(), font=font(L.TITLE_FONT, 40 * u), fill=(255, 255, 255),
                anchor="lm")
        shown = int(sum(len(l) + 1 for l in lines) * clamp((tl - 0.4) / 1.4))
        hl = clamp((tl - 1.9) / 0.6)
        pos, y = 0, bar + 120 * u
        for line in lines:
            vis = line[:max(0, shown - pos)]
            for a0, a1 in c.get("spans", []):
                s0, s1 = max(a0, pos), min(a1, pos + len(line))
                if s1 > s0 and hl > 0:
                    xa = 45 * u + dp.textlength(line[:s0 - pos], font=ft)
                    xb = 45 * u + dp.textlength(line[:s1 - pos], font=ft)
                    dp.rectangle((xa - 4 * u, y, xa + (xb - xa) * hl + 4 * u, y + ft.size * 1.15), fill=(255, 222, 70, 255))
            dp.text((45 * u, y), vis, font=ft, fill=(24, 24, 28), anchor="lt")
            pos += len(line) + 1
            y += ft.size * 1.4
        a = back(clamp(tl / 0.4))
        R.paste_scaled(lay, R.shadowed(page, int(16 * u)), W / 2, H * 0.55, 0.9 + 0.1 * a, clamp(a))

    def c_scale(self, lay, shot, t, tl, f):
        """The thing sits on a scale and the dial swings round; the big words beside it."""
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        d = ImageDraw.Draw(lay)
        cx, top = W * 0.36, H * 0.60
        a = ease_out(clamp(tl / 0.4))
        d.rounded_rectangle((cx - W * 0.17, top, cx + W * 0.17, top + H * 0.06), radius=10 * u, fill=(70, 70, 78, int(255 * a)))
        d.rounded_rectangle((cx - W * 0.13, top + H * 0.06, cx + W * 0.13, top + H * 0.32), radius=16 * u, fill=(40, 40, 46, int(255 * a)))
        r = H * 0.10
        dx, dy = cx, top + H * 0.19
        d.ellipse((dx - r, dy - r, dx + r, dy + r), fill=(250, 250, 250, int(255 * a)), outline=(24, 20, 20, int(255 * a)),
                  width=int(5 * u))
        for k in range(12):
            ang = math.radians(-120 + k * 20)
            d.line((dx + r * 0.80 * math.sin(ang), dy - r * 0.80 * math.cos(ang), dx + r * 0.92 * math.sin(ang),
                    dy - r * 0.92 * math.cos(ang)), fill=(24, 20, 20, int(255 * a)), width=int(3 * u))
        sw = back(clamp((tl - 0.7) / 0.8))
        ang = math.radians(-110 + 200 * sw)
        d.line((dx, dy, dx + r * 0.78 * math.sin(ang), dy - r * 0.78 * math.cos(ang)), fill=L.RED + (255,), width=int(7 * u))
        p = self.pic_path(c.get("pic"))
        drop = back(clamp((tl - 0.3) / 0.45))
        if p:
            self.framed(lay, p, cx, top - H * 0.20 - 120 * u * (1 - drop), (W * 0.28, H * 0.36), -3.0, drop, f)
        else:
            ic = icons.icon(c.get("icon") or "box", int(H * 0.38))
            if ic is not None and drop > 0.02:
                R.paste_scaled(lay, ic, cx, top - H * 0.19 - 120 * u * (1 - drop), drop)
        txt = str(c.get("text") or "").upper()
        if txt:
            ta = clamp((tl - 1.1) / 0.4)
            img = Image.new("RGBA", (int(W * 0.40), int(H * 0.5)), (0, 0, 0, 0))
            di = ImageDraw.Draw(img)
            ft = fit_font(di, txt, L.HAND_FONT, 120 * u, W * 0.36, lines=2)
            for i, line in enumerate(wrap(di, txt, ft, W * 0.36)):
                di.text((img.width / 2, img.height / 2 + (i - 0.5) * ft.size * 1.1), line, font=ft, fill=L.RED + (255,), anchor="mm")
            R.paste_scaled(lay, _rot(img, 8), W * 0.74, H * 0.50, 0.85 + 0.15 * back(ta), ta)

    def c_beforeafter(self, lay, shot, t, tl, f):
        """Two real photos side by side; a wipe reveals the second; labels under each."""
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        pics = [self.pic_path(k) for k in (c.get("pics") or [])]
        labels = c.get("labels") or ["BEFORE", "AFTER"]
        bw, bh = int(W * 0.42), int(H * 0.60)
        wipe = ease(clamp((t - c.get("wipe_at", shot["t0"] + 1.0)) / 0.6))
        d = ImageDraw.Draw(lay)
        for j in range(2):
            x = W * (0.27 if j == 0 else 0.73)
            a = back(clamp((tl - 0.1) / 0.4)) if j == 0 else wipe
            if a <= 0.01:
                continue
            p = pics[j] if j < len(pics) else None
            if p:
                im = R.cover(Image.open(p).convert("RGB"), (bw, bh)).convert("RGBA")
            else:
                im = Image.new("RGBA", (bw, bh), (60, 56, 60, 255))
            if j == 1 and wipe < 1:
                m = Image.new("L", (bw, bh), 0)
                ImageDraw.Draw(m).rectangle((0, 0, int(bw * wipe), bh), fill=255)
                im.putalpha(m)
            fr = Image.new("RGBA", (bw + int(20 * u), bh + int(20 * u)), (252, 252, 250, int(255 * (1 if j == 0 else wipe))))
            fr.alpha_composite(im, (int(10 * u), int(10 * u)))
            R.paste_scaled(lay, R.shadowed(fr, int(14 * u)), x, H * 0.50, 1.0 if j else 0.9 + 0.1 * a, 1.0 if j else clamp(a))
            lab = str(labels[j] or "").upper()
            if lab:
                pill(d, (x, H * 0.89), lab, font(L.TITLE_FONT, 44 * u), (24, 20, 20) if j else L.WHITE,
                     (L.YELLOW if j else L.RED) + (int(255 * clamp(a)),), radius=0.2)
        if wipe > 0:
            ImageDraw.Draw(lay).polygon([(W / 2 - 30 * u, H * 0.50), (W / 2 + 10 * u, H * 0.44), (W / 2 + 10 * u, H * 0.56)],
                                        fill=L.YELLOW + (int(255 * wipe),))

    def c_tally(self, lay, shot, t, tl, f):
        """Icons appear one by one with their count under them ("4 KIDS HOSPITALIZED")."""
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        n = int(c.get("count") or 1)
        per_row = n if n <= 6 else math.ceil(n / 2)
        rows = 1 if n <= 6 else 2
        size = int(min(W * 0.80 / per_row, H * (0.50 if rows == 1 else 0.30)))
        d = ImageDraw.Draw(lay)
        shown = 0
        for j, at in enumerate(c.get("ats") or []):
            a = clamp((t - at) / 0.3)
            if a <= 0:
                continue
            shown = j + 1
            rr, cc = divmod(j, per_row)
            x = W / 2 + (cc - (per_row - 1) / 2) * size * 1.05
            y = H * (0.48 if rows == 1 else 0.36 + rr * 0.34)
            ic = icons.icon(c.get("icon") or "man", size)
            if ic is not None:
                R.paste_scaled(lay, ic, x, y - 40 * u * (1 - back(a)), 0.7 + 0.3 * back(a), clamp(a * 1.5))
            d.text((x, y + size * 0.55), str(j + 1), font=font(L.TITLE_FONT, 50 * u), fill=L.YELLOW + (int(255 * a),), anchor="mm")
        lab = str(c.get("label") or "").upper()
        if lab and shown:
            la = clamp((t - (c.get("ats") or [shot["t0"]])[-1] - 0.3) / 0.35)
            pill(d, (W / 2, H * 0.90), f"{shown} {lab}" if not re.match(r"^\d", lab) else lab, font(L.TITLE_FONT, 54 * u), L.WHITE,
                 L.RED + (int(255 * la),), radius=0.2)

    def c_scene2d(self, lay, shot, t, tl, f):
        """A flat cartoon mini scene: the place (Flow, made once) + code-drawn people acting it out (scene2d.py)."""
        from . import scene2d as S2
        c = shot["card"]
        p = self.pic_path(c.get("pic"))
        bg = None
        if p:
            k = ("place2d", p, self.size)
            if k not in _STATIC:
                _STATIC[k] = R.cover(Image.open(p).convert("RGB"), self.size).convert("RGBA")
            bg = _STATIC[k]
        S2.draw(lay, c, t, shot["t0"], shot["t1"], self.size, bg, font, pill)

    def banner(self, base, shot, t):
        """A red banner strap across the top of a host shot ("BUT IT STILL WASN'T ENOUGH")."""
        b = shot["banner"]
        r = ease_out(clamp((t - b["at"]) / 0.3))
        if r <= 0:
            return
        W, u = self.W, self.u
        d = ImageDraw.Draw(base)
        text = str(b["text"]).upper()
        ft = fit_font(d, text, L.TITLE_FONT, 56 * u, W * 0.70)
        w = d.textlength(text, font=ft) + 70 * u
        x0 = 40 * u - (w + 60 * u) * (1 - r)
        d.polygon([(x0, 36 * u), (x0 + w, 36 * u), (x0 + w - 24 * u, 36 * u + ft.size * 1.5), (x0, 36 * u + ft.size * 1.5)],
                  fill=L.RED + (245,))
        d.text((x0 + 30 * u, 36 * u + ft.size * 0.75), text, font=ft, fill=(255, 255, 255), anchor="lm")

    # ---------------------------------------------------------------- real imagery (Phase 1)
    def pic_path(self, key):
        p = (self.a.get("pictures") or {}).get(key) if key else None
        return p if p and os.path.isfile(p) else None

    def framed(self, lay, path, cx, cy, box, tilt, a, f):
        """A real photo in a white frame with a shadow, fitted inside `box`, popping in with `a`, drifting with `f`."""
        if a <= 0.02:
            return
        u = self.u
        k = ("framed", path, int(box[0]), int(box[1]), tilt)
        if k not in _STATIC:
            src = Image.open(path).convert("RGB")
            s = min(box[0] / src.width, box[1] / src.height)
            im = src.resize((max(1, int(src.width * s)), max(1, int(src.height * s))), Image.LANCZOS)
            b = int(12 * u)
            fr = Image.new("RGBA", (im.width + 2 * b, im.height + 2 * b), (252, 252, 250, 255))
            fr.paste(im, (b, b))
            _STATIC[k] = _rot(R.shadowed(fr, int(14 * u)), tilt)
        R.paste_scaled(lay, _STATIC[k], cx, cy, (0.85 + 0.15 * a) * (1 + 0.03 * ease(f)), clamp(a))

    def c_page(self, lay, shot, t, tl, f):
        """The real page: a browser frame, the screenshot scrolling a little, a highlighter over its headline."""
        W, H, u = self.W, self.H, self.u
        p = self.pic_path(shot.get("page"))
        if not p:
            return self.c_headline(lay, shot, t, tl, f)
        from . import sources
        m = sources.meta(shot["page"]) or {}
        fw, fh = W * 0.62, H * 0.78
        bar = 46 * u
        k = ("page", p, int(fw))
        if k not in _STATIC:
            im = Image.open(p).convert("RGB")
            s = (fw - 4 * u) / im.width
            _STATIC[k] = (im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS), s)
        page_im, s = _STATIC[k]
        view_h = int(fh - bar)
        hb = m.get("headline_box") or None
        y_head = int(hb[1] * s) if hb else 0
        y0 = max(0, min(page_im.height - view_h, y_head - int(view_h * 0.25)))
        scroll = int(min(60 * u, max(0, page_im.height - view_h - y0)) * ease(f))
        crop = page_im.crop((0, y0 + scroll, page_im.width, y0 + scroll + view_h)).convert("RGBA")
        if hb:
            hl = clamp((tl - 0.6) / 0.7)
            if hl > 0:   # a see-through marker layer on top, so the words stay readable under it
                mark = Image.new("RGBA", crop.size, (0, 0, 0, 0))
                d = ImageDraw.Draw(mark)
                bx, by, bw, bh = [v * s for v in hb]
                by -= y0 + scroll
                d.rectangle((bx - 6 * u, by - 4 * u, bx + bw * hl + 6 * u, by + bh + 4 * u), fill=(255, 214, 0, 105))
                crop = Image.alpha_composite(crop, mark)
        frame = Image.new("RGBA", (int(fw), int(fh)), (236, 236, 240, 255))
        df = ImageDraw.Draw(frame)
        for i, col in enumerate(((236, 90, 80), (240, 190, 60), (90, 190, 100))):
            df.ellipse((18 * u + i * 26 * u, bar / 2 - 8 * u, 34 * u + i * 26 * u, bar / 2 + 8 * u), fill=col)
        df.rounded_rectangle((110 * u, 9 * u, fw - 20 * u, bar - 9 * u), radius=12 * u, fill=(255, 255, 255))
        df.text((130 * u, bar / 2), str(m.get("site") or m.get("url") or "")[:80], font=font(L.BODY_SEMI, 18 * u),
                fill=(90, 90, 96), anchor="lm")
        frame.alpha_composite(crop, (int(2 * u), int(bar)))
        a = back(clamp(tl / 0.4))
        R.paste_scaled(lay, R.shadowed(frame, int(16 * u)), W / 2, H * 0.53, 0.9 + 0.1 * a, clamp(a))

    def c_clip(self, lay, shot, t, tl, f):
        """A real news / TV clip playing in a frame (muted: the voice carries on), a strap with outlet and date."""
        W, H, u = self.W, self.H, self.u
        clip = (self.a.get("clips") or {}).get(shot.get("clip")) if shot.get("clip") else None
        if not (clip and os.path.isfile(clip)):
            return self.c_photo(lay, shot, t, tl, f)
        cw, ch = int(W * 0.70) // 2 * 2, int(W * 0.70 * 9 / 16) // 2 * 2
        k = ("clip", shot["i"], cw)
        r = self._readers.get(k)
        if r is None:
            r = self._readers[k] = R.ClipReader(clip, (cw, ch), (0.5, 0.5, 1.0, 1.0), start=0.0, fps=self.spec["fps"], loop=True)
        fr = r.next()
        if fr is None:
            return self.c_photo(lay, shot, t, tl, f)
        b = int(10 * u)
        box = Image.new("RGBA", (cw + 2 * b, ch + 2 * b), (252, 252, 250, 255))
        box.paste(fr, (b, b))
        a = back(clamp(tl / 0.35))
        cx, cy = W / 2, H * 0.47
        R.paste_scaled(lay, R.shadowed(box, int(16 * u)), cx, cy, 0.9 + 0.1 * a, clamp(a))
        strap = str((shot.get("card") or {}).get("strap") or "").upper()
        if strap:
            sa = ease_out(clamp((tl - 0.4) / 0.3))
            pill(ImageDraw.Draw(lay), (cx - cw / 2, cy + ch / 2 + 36 * u + 30 * u * (1 - sa)), strap, font(L.TITLE_FONT, 36 * u),
                 (24, 20, 20), L.YELLOW + (int(255 * sa),), anchor="lm", radius=0.2)

    def c_map(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        got = maps.layers(c.get("place", ""), (int(W * 0.86), int(H * 0.74)))
        ox, oy = int(W * 0.07), int(H * 0.15)
        if got:
            base, fill, pin, _label = got
            lay.alpha_composite(_alpha(base, ease_out(tl / 0.4)), (ox, oy))
            fa = ease(clamp((tl - 0.45) / 0.45))
            if fa > 0:
                lay.alpha_composite(_alpha(fill, fa), (ox, oy))
            if pin:
                pa = clamp((tl - 0.85) / 0.35)
                if pa > 0:
                    px, py = ox + pin[0], oy + pin[1] - 80 * u * (1 - back(pa))
                    self.pin(lay, px, py, pa)
                    lbl = str(c.get("city") or "").upper()
                    if lbl:
                        pill(ImageDraw.Draw(lay), (px + 26 * u, py - 44 * u), lbl, font(L.BODY_FONT, 22 * u), (24, 20, 20),
                             (250, 250, 250, int(255 * pa)), anchor="lm", radius=0.2)
        label = str(c.get("label", "")).upper()
        if label:
            r = ease_out(clamp((tl - 0.9) / 0.3))
            pill(ImageDraw.Draw(lay), (W / 2, H * 0.93 + 50 * u * (1 - r)), label, font(L.TITLE_FONT, 38 * u), L.WHITE,
                 L.RED + (int(255 * r),), radius=0.2)

    def pin(self, lay, x, y, a):
        u = self.u
        d = ImageDraw.Draw(lay)
        r = 22 * u
        d.ellipse((x - r * 0.9, y + r * 1.6, x + r * 0.9, y + r * 2.1), fill=(0, 0, 0, int(90 * a)))
        d.polygon([(x - r * 0.8, y - r * 0.4), (x + r * 0.8, y - r * 0.4), (x, y + r * 1.8)], fill=L.YELLOW + (int(255 * a),))
        d.ellipse((x - r, y - r * 1.6, x + r, y + r * 0.4), fill=L.YELLOW + (int(255 * a),), outline=(30, 24, 24, int(255 * a)),
                  width=int(3 * u))
        d.ellipse((x - r * 0.38, y - r * 0.98, x + r * 0.38, y - r * 0.22), fill=(30, 24, 24, int(255 * a)))

    def c_folder(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        fw, fh = W * 0.58, H * 0.66
        r = back(clamp(tl / 0.4))
        k = ("folder", self.size)
        if k not in _STATIC:
            im = Image.new("RGBA", (int(fw), int(fh + 60 * u)), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, fw * 0.32, 90 * u), radius=14 * u, fill=(214, 184, 118, 255))
            d.rounded_rectangle((0, 50 * u, fw, fh + 50 * u), radius=14 * u, fill=L.MANILA + (255,))
            d.rectangle((26 * u, 80 * u, fw - 26 * u, fh + 24 * u), fill=(252, 250, 244, 255))
            _STATIC[k] = R.shadowed(im, int(18 * u))
        folder = _STATIC[k]
        cx, cy = W / 2, H * 0.53
        R.paste_scaled(lay, folder, cx, cy + 40 * u * (1 - r), 0.9 + 0.1 * r, clamp(r))
        if r < 0.6:
            return
        d = ImageDraw.Draw(lay)
        x0 = cx - fw / 2 + 60 * u
        y = cy - fh / 2 + 40 * u
        d.text((cx - fw / 2 + 36 * u, cy - fh / 2 - 16 * u), str(c.get("tab", "THE CASE")).upper(), font=font(L.TITLE_FONT, 36 * u),
               fill=(70, 50, 20, 255), anchor="lm")
        for it in c.get("items", []):
            a = clamp((t - it["at"]) / 0.3)
            if a <= 0:
                continue
            lab = it["label"].upper()
            val = it["value"].upper() if it["value"] else ""
            d.text((x0, y), lab, font=font(L.BODY_FONT, 26 * u), fill=(140, 120, 100, int(255 * a)), anchor="lt")
            y += 38 * u
            ft = fit_font(d, val or lab, L.TITLE_FONT, 64 * u, fw - 140 * u)
            shown = (val or lab)[:max(1, int(len(val or lab) * clamp((t - it["at"]) / 0.5)))]
            col = L.COLOURS.get(it.get("colour") or "", L.INK)
            d.text((x0, y), shown, font=ft, fill=col + (int(255 * a),), anchor="lt")
            y += ft.size * 1.35
            d.line((x0, y - 12 * u, cx + fw / 2 - 60 * u, y - 12 * u), fill=(220, 214, 200, 255), width=int(2 * u))

    def c_headline(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        cw = W * 0.56
        d0 = ImageDraw.Draw(lay)
        ft = fit_font(d0, c.get("text", ""), L.BODY_FONT, 46 * u, cw - 80 * u, lines=3)
        lines = wrap(d0, c.get("text", ""), ft, cw - 80 * u)
        p = self.pic(shot.get("pic")) if shot.get("pic") else None
        ph = H * 0.30 if p else 0
        ch = 110 * u + len(lines) * ft.size * 1.25 + ph + 60 * u
        r = back(clamp(tl / 0.4))
        k = ("headline", shot["row"], self.size, p)
        if k not in _STATIC:
            im = Image.new("RGBA", (int(cw), int(ch)), (252, 252, 250, 255))
            d = ImageDraw.Draw(im)
            d.rectangle((0, 0, cw, 64 * u), fill=(24, 32, 58, 255))
            d.text((30 * u, 32 * u), str(c.get("outlet", "")).upper(), font=font(L.BODY_FONT, 24 * u), fill=(255, 255, 255),
                   anchor="lm")
            d.text((cw - 30 * u, 32 * u), str(c.get("date", "")).upper(), font=font(L.BODY_SEMI, 20 * u),
                   fill=(190, 200, 220), anchor="rm")
            if p:
                ph_im = R.cover(Image.open(p).convert("RGB"), (int(cw - 60 * u), int(ph)))
                im.paste(ph_im, (int(30 * u), int(ch - ph - 30 * u)))
            _STATIC[k] = R.shadowed(im, int(16 * u))
        card = _STATIC[k].copy()
        d = ImageDraw.Draw(card)
        pad = int(16 * u * 3)
        x0, y0 = pad + 40 * u, pad + 100 * u
        # highlighter sweep over the starred words, then the words on top
        hl = clamp((tl - 0.7) / 0.6)
        pos = 0
        for i, line in enumerate(lines):
            y = y0 + i * ft.size * 1.25
            for a0, a1 in c.get("spans", []):
                s0, s1 = max(a0, pos), min(a1, pos + len(line))
                if s1 > s0 and hl > 0:
                    xa = x0 + d.textlength(line[:s0 - pos], font=ft)
                    xb = x0 + d.textlength(line[:s1 - pos], font=ft)
                    d.rectangle((xa - 4 * u, y - 2 * u, xa + (xb - xa) * hl + 4 * u, y + ft.size * 1.1), fill=(255, 220, 60, 255))
            d.text((x0, y), line, font=ft, fill=(20, 20, 24, 255), anchor="lt")
            pos += len(line) + 1
        R.paste_scaled(lay, card, W / 2, H * 0.54, 0.9 + 0.1 * r, clamp(r))

    def c_quote(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        d = ImageDraw.Draw(lay)
        a = ease_out(tl / 0.4)
        face = self.pic_path(shot.get("pic"))
        tx, tw = (W * 0.43, W * 0.50) if face else (W * 0.16, W * 0.70)
        if face:      # the speaker's real portrait beside the words
            self.framed(lay, face, W * 0.22, H * 0.52, (W * 0.30, H * 0.62), -2.0, back(clamp(tl / 0.4)), f)
        d.text((tx - W * 0.04, H * 0.28), "\u201c", font=font(L.TITLE_FONT, 220 * u), fill=L.RED + (int(255 * a),), anchor="lm")
        ft = fit_font(d, c.get("text", ""), L.BODY_FONT, 58 * u, tw, lines=4)
        lines = wrap(d, c.get("text", ""), ft, tw)
        x0, y0 = tx, H * 0.36
        hl = clamp((tl - 0.8) / 0.6)
        pos = 0
        for i, line in enumerate(lines):
            la = clamp((tl - 0.2 - 0.15 * i) / 0.3)
            y = y0 + i * ft.size * 1.3
            for a0, a1 in c.get("spans", []):
                s0, s1 = max(a0, pos), min(a1, pos + len(line))
                if s1 > s0 and hl > 0:
                    xa = x0 + d.textlength(line[:s0 - pos], font=ft)
                    xb = x0 + d.textlength(line[:s1 - pos], font=ft)
                    d.rectangle((xa - 4 * u, y + ft.size * 0.15, xa + (xb - xa) * hl + 4 * u, y + ft.size * 1.15),
                                fill=L.YELLOW + (200,))
            d.text((x0, y), line, font=ft, fill=L.CREAM + (int(255 * la),), anchor="lt")
            pos += len(line) + 1
        who = str(c.get("who", "")).upper()
        if who:
            wa = clamp((tl - 1.0) / 0.3)
            d.text((x0, y0 + len(lines) * ft.size * 1.3 + 40 * u), "— " + who, font=font(L.BODY_FONT, 30 * u),
                   fill=L.YELLOW + (int(255 * wa),), anchor="lt")

    def c_tweet(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        c = shot["card"]
        cw = W * 0.46
        d0 = ImageDraw.Draw(lay)
        ft = font(L.BODY_SEMI, 36 * u)
        lines = wrap(d0, c.get("text", ""), ft, cw - 80 * u)[:7]
        ch = 150 * u + len(lines) * ft.size * 1.32 + 70 * u
        card = Image.new("RGBA", (int(cw), int(ch)), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=24 * u, fill=(252, 252, 252, 255))
        d.ellipse((36 * u, 36 * u, 106 * u, 106 * u), fill=(120, 140, 170, 255))
        d.text((124 * u, 52 * u), str(c.get("name", "")), font=font(L.BODY_FONT, 30 * u), fill=(20, 20, 24), anchor="lm")
        d.text((124 * u, 90 * u), str(c.get("handle", "")), font=font(L.BODY_SEMI, 24 * u), fill=(120, 124, 130), anchor="lm")
        pos = 0
        hl = clamp((tl - 0.8) / 0.6)
        for i, line in enumerate(lines):
            y = 140 * u + i * ft.size * 1.32
            for a0, a1 in c.get("spans", []):
                s0, s1 = max(a0, pos), min(a1, pos + len(line))
                if s1 > s0 and hl > 0:
                    xa = 40 * u + d.textlength(line[:s0 - pos], font=ft)
                    xb = 40 * u + d.textlength(line[:s1 - pos], font=ft)
                    d.rectangle((xa - 3 * u, y, xa + (xb - xa) * hl + 3 * u, y + ft.size * 1.15), fill=(255, 225, 80, 255))
            d.text((40 * u, y), line, font=ft, fill=(20, 20, 24), anchor="lt")
            pos += len(line) + 1
        d.text((40 * u, ch - 40 * u), str(c.get("date", "")), font=font(L.BODY_SEMI, 22 * u), fill=(140, 144, 150), anchor="lm")
        r = back(clamp(tl / 0.4))
        R.paste_scaled(lay, R.shadowed(card, int(14 * u)), W * 0.40, H * 0.52, 0.9 + 0.1 * r, clamp(r))
        extra = c.get("extra")
        if extra:
            a = clamp((tl - 1.1) / 0.4)
            num = extra.get("num")
            txt = R.fmt_count(extra["value"], num, clamp((tl - 1.1) / 1.0))
            dd = ImageDraw.Draw(lay)
            dd.text((W * 0.80, H * 0.46), txt, font=font(L.TITLE_FONT, 110 * u), fill=L.YELLOW + (int(255 * a),), anchor="mm")
            dd.text((W * 0.80, H * 0.56), extra.get("label", "").upper(), font=font(L.TITLE_FONT, 40 * u),
                    fill=L.CREAM + (int(255 * a),), anchor="mm")

    def c_big(self, lay, shot, t, tl, f):
        """One or more big numbers: huge, counting up in 0.6 s, the label under it, a matching icon beside it."""
        W, H, u = self.W, self.H, self.u
        items = shot["card"].get("items", [])[:3]
        d = ImageDraw.Draw(lay)
        n = max(1, len(items))
        tone = shot.get("tone")
        sub_col = L.INK if tone == "cream" else L.CREAM
        row_h = H * (0.66 if n == 1 else 0.70 / n)
        top = H * (0.17 if n == 1 else 0.19)
        for j, it in enumerate(items):
            a = clamp((t - it["at"]) / 0.25)
            if a <= 0:
                continue
            big, sub = it["label"], it["value"]
            if csv_num(big) is None and csv_num(sub) is not None:
                big, sub = sub, big
            txt = R.fmt_count(big.upper(), csv_num(big), clamp((t - it["at"]) / 0.6))
            col = L.COLOURS.get(it.get("colour") or "", L.RED if tone == "cream" else L.YELLOW)
            cy = top + row_h * (j + 0.5)
            ic = icons.icon(icons.key_of(sub) or icons.key_of(big), int(row_h * (0.92 if n == 1 else 1.0)))
            num_x = W * (0.38 if ic is not None else 0.50)
            num_w = W * (0.56 if ic is not None else 0.84)
            px = row_h * (0.62 if sub else 0.80)
            ft = fit_font(d, big.upper(), L.TITLE_FONT, px, num_w)     # sized on the final text, so it never jumps
            img = Image.new("RGBA", (int(num_w + 40 * u), int(ft.size * 1.3)), (0, 0, 0, 0))
            di = ImageDraw.Draw(img)
            di.text((img.width / 2 + 7 * u, img.height / 2 + 7 * u), txt, font=ft, fill=(0, 0, 0, 120), anchor="mm")
            di.text((img.width / 2, img.height / 2), txt, font=ft, fill=col + (255,), anchor="mm")
            ny = cy - (row_h * 0.12 if sub else 0)
            R.paste_scaled(lay, img, num_x, ny, 0.8 + 0.2 * back(a), a)
            if sub:
                sa = clamp((t - it["at"] - 0.2) / 0.3)
                sf = fit_font(d, sub.upper(), L.TITLE_FONT, row_h * 0.20, num_w)
                d.text((num_x, ny + ft.size * 0.62), sub.upper(), font=sf, fill=sub_col + (int(255 * sa),), anchor="mt")
            if ic is not None:
                ia = back(clamp((t - it["at"] - 0.1) / 0.35))
                bob = math.sin((t - it["at"]) * 2.0 + j) * 5 * u
                R.paste_scaled(lay, ic, W * 0.77, cy + bob, 0.7 + 0.3 * ia, clamp(ia * 1.5))

    def c_flow(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        items = shot["card"].get("items", [])[:4]
        n = max(1, len(items))
        bw = min(560 * u, (W * 0.90 - (n - 1) * 90 * u) / n)
        bh = 400 * u
        x = W / 2 - (n * bw + (n - 1) * 90 * u) / 2
        cy = H * 0.58
        d = ImageDraw.Draw(lay)
        palette = [L.RED, L.YELLOW, L.CREAM, L.WHITE]
        for j, it in enumerate(items):
            a = clamp((t - it["at"]) / 0.3)
            if a > 0:
                col = L.COLOURS.get(it.get("colour") or "", palette[j % len(palette)])
                box = Image.new("RGBA", (int(bw), int(bh)), (0, 0, 0, 0))
                db = ImageDraw.Draw(box)
                db.rounded_rectangle((0, 0, bw - 1, bh - 1), radius=12 * u, fill=col + (255,), outline=(24, 20, 20, 255),
                                     width=int(4 * u))
                txt_col = L.WHITE if col == L.RED else L.INK
                lab, val = it["label"].upper(), it["value"].upper()
                if val:
                    db.text((bw / 2, bh * 0.38), lab, font=fit_font(db, lab, L.TITLE_FONT, 84 * u, bw - 40 * u), fill=txt_col,
                            anchor="mm")
                    db.text((bw / 2, bh * 0.72), val, font=fit_font(db, val, L.TITLE_FONT, 44 * u, bw - 40 * u), fill=txt_col,
                            anchor="mm")
                else:
                    ft = fit_font(db, lab, L.TITLE_FONT, 84 * u, bw - 40 * u, lines=2)
                    ls = wrap(db, lab, ft, bw - 30 * u)
                    for i, l in enumerate(ls):
                        db.text((bw / 2, bh / 2 + (i - (len(ls) - 1) / 2) * ft.size * 1.05), l, font=ft, fill=txt_col,
                                anchor="mm")
                R.paste_scaled(lay, box, x + bw / 2, cy, 0.85 + 0.15 * back(a), a)
            if j < n - 1:
                aa = clamp((t - items[j + 1]["at"] + 0.25) / 0.25)
                if aa > 0:
                    ax0, ax1 = x + bw + 14 * u, x + bw + 76 * u
                    xe = ax0 + (ax1 - ax0) * ease_out(aa)
                    self.arrow(d, ax0, cy, xe, cy, (24, 20, 20) if shot.get("tone") == "cream" else L.CREAM)
            x += bw + 90 * u

    def arrow(self, d, x0, y0, x1, y1, col, w=None):
        u = self.u
        w = w or int(8 * u)
        d.line((x0, y0, x1, y1), fill=col + (255,), width=w)
        ang = math.atan2(y1 - y0, x1 - x0)
        hl = 22 * u
        d.polygon([(x1 + 6 * u * math.cos(ang), y1 + 6 * u * math.sin(ang)),
                   (x1 - hl * math.cos(ang - 0.5), y1 - hl * math.sin(ang - 0.5)),
                   (x1 - hl * math.cos(ang + 0.5), y1 - hl * math.sin(ang + 0.5))], fill=col + (255,))

    def c_explain(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        steps = shot["card"].get("items", [])[:5]
        n = max(1, len(steps))
        size = int(min(520 * u, W * 0.80 / n))
        gap = min(260 * u, (W * 0.90 - n * size) / max(1, n - 1)) if n > 1 else 0
        x = W / 2 - (n * size + (n - 1) * gap) / 2 + size / 2
        cy = H * 0.48
        d = ImageDraw.Draw(lay)
        ink = (24, 20, 20) if shot.get("tone") == "cream" else L.CREAM
        for j, st in enumerate(steps):
            a = clamp((t - st["at"]) / 0.35)
            if j > 0:
                aa = clamp((t - st["at"] + 0.3) / 0.3)
                if aa > 0:
                    mx0, mx1 = x - gap - size / 2 + 20 * u, x - size / 2 - 20 * u
                    if st.get("join"):
                        if aa > 0.3:
                            for dy in (-12 * u, 12 * u):
                                d.rectangle((mx0 + 10 * u, cy + dy - 5 * u, mx1 - 10 * u, cy + dy + 5 * u), fill=ink + (255,))
                    else:
                        self.arrow(d, mx0, cy, mx0 + (mx1 - mx0) * ease_out(aa), cy, L.RED)
            if a > 0:
                im = self.icon_for(st, size)
                if im is not None:
                    sh_a = int(70 * clamp(a * 1.5))     # a soft floor shadow grounds each icon
                    d.ellipse((x - size * 0.36, cy + size * 0.44, x + size * 0.36, cy + size * 0.54), fill=(0, 0, 0, sh_a))
                    bob = math.sin((t - st["at"]) * 2.2 + j) * 6 * u
                    R.paste_scaled(lay, im, x, cy + bob, 0.6 + 0.4 * back(a), clamp(a * 1.5))
                lab = st.get("label_text", "").upper()
                if lab:
                    la = clamp((t - st["at"] - 0.2) / 0.3)
                    ft = fit_font(d, lab, L.TITLE_FONT, 44 * u, size * 1.15)
                    fg, bg = ((255, 255, 255), (36, 80, 140, int(255 * la))) if j % 2 == 0 else ((24, 20, 20), L.YELLOW + (int(255 * la),))
                    pill(d, (x, cy + size * 0.68), lab, ft, fg, bg, radius=0.2)
            x += size + gap

    def icon_for(self, st, size):
        flow_pic = (self.a.get("pictures") or {}).get(st.get("pic")) if st.get("pic") else None
        if flow_pic and os.path.isfile(flow_pic):
            k = ("sticker", flow_pic, size)
            if k not in _STATIC:
                im = R.trim_white(Image.open(flow_pic).convert("RGB"))
                im = im.convert("RGBA")
                # white -> transparent
                import numpy as np
                a = np.asarray(im).copy()
                white = (a[..., :3].min(axis=2) > 238)
                a[white, 3] = 0
                im = Image.fromarray(a, "RGBA")
                s = size / max(im.width, im.height)
                _STATIC[k] = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
            return _STATIC[k]
        return icons.icon(st.get("icon"), size)

    def c_timeline(self, lay, shot, t, tl, f):
        W, H, u = self.W, self.H, self.u
        items = shot["card"].get("items", [])[:6]
        n = max(1, len(items))
        d = ImageDraw.Draw(lay)
        ink = (24, 20, 20) if shot.get("tone") == "cream" else L.CREAM
        x0 = W * 0.27
        y0, y1 = H * 0.21, H * 0.88
        gap = (y1 - y0) / max(1, n - 1) if n > 1 else 0
        la = ease_out(tl / 0.6)
        d.line((x0, y0, x0, y0 + (y1 - y0) * la), fill=ink + (180,), width=int(6 * u))
        for j, it in enumerate(items):
            a = clamp((t - it["at"]) / 0.3)
            if a <= 0:
                continue
            y = y0 + gap * j if n > 1 else (y0 + y1) / 2
            col = L.COLOURS.get(it.get("colour") or "", L.RED)
            r = 24 * u * back(a)
            d.ellipse((x0 - r, y - r, x0 + r, y + r), fill=col + (255,), outline=ink + (255,), width=int(3 * u))
            date = it["label"].upper()
            d.text((x0 - 50 * u, y), date, font=fit_font(d, date, L.TITLE_FONT, 92 * u, W * 0.20), fill=col + (int(255 * a),),
                   anchor="rm")
            txt = it["value"].upper()
            d.text((x0 + 60 * u + 30 * u * (1 - ease_out(a)), y), txt,
                   font=fit_font(d, txt, L.TITLE_FONT, 86 * u, W * 0.64), fill=ink + (int(255 * a),), anchor="lm")

    # ---------------------------------------------------------------- overlays
    def captions(self, base, shot, t):
        cap = next((c for c in shot.get("caps", []) if c["t0"] <= t < c["t1"]), None)
        if not cap:
            return
        W, H, u = self.W, self.H, self.u
        d = ImageDraw.Draw(base)
        words = cap["text"].upper().split()
        ft = font(L.TITLE_FONT, 72 * u)
        sp = d.textlength(" ", font=ft)
        widths = [d.textlength(w, font=ft) for w in words]
        total = sum(widths) + sp * (len(words) - 1)
        if total > W * 0.86:
            ft = font(L.TITLE_FONT, 72 * u * W * 0.86 / total)
            sp = d.textlength(" ", font=ft)
            widths = [d.textlength(w, font=ft) for w in words]
            total = sum(widths) + sp * (len(words) - 1)
        x = W / 2 - total / 2
        y = H - 120 * u
        pop = back(clamp((t - cap["t0"]) / 0.12))
        yy = y + 10 * u * (1 - pop)
        for i, (w, ww) in enumerate(zip(words, widths)):
            col = L.YELLOW if i == cap.get("key") else L.WHITE
            for dx, dy in ((4, 4), (-2, 2), (2, -2), (-2, -2), (3, 0), (0, 3)):
                d.text((x + dx * u, yy + dy * u), w, font=ft, fill=(0, 0, 0, 230), anchor="ls")
            d.text((x, yy), w, font=ft, fill=col + (255,), anchor="ls")
            x += ww + sp

    def note(self, base, shot, t):
        n = shot["note"]
        a = clamp((t - n["at"]) / 0.35)
        if a <= 0:
            return
        W, H, u = self.W, self.H, self.u
        text = n["text"].upper()
        d0 = ImageDraw.Draw(base)
        ft = fit_font(d0, text, L.HAND_FONT, 62 * u, W * 0.30, lines=2)
        lines = wrap(d0, text, ft, W * 0.30)
        img = Image.new("RGBA", (int(W * 0.36), int(ft.size * 1.25 * len(lines) + 40 * u)), (0, 0, 0, 0))
        di = ImageDraw.Draw(img)
        col = L.RED if n.get("red") else L.YELLOW
        shown = int(sum(len(l) for l in lines) * clamp((t - n["at"]) / 0.6))
        for i, l in enumerate(lines):
            part = l[:max(0, shown)]
            shown -= len(l)
            y = 20 * u + i * ft.size * 1.2
            for dx, dy in ((3, 3), (-1, 1)):
                di.text((img.width / 2 + dx * u, y + dy * u), part, font=ft, fill=(0, 0, 0, 200), anchor="mt")
            di.text((img.width / 2, y), part, font=ft, fill=col + (255,), anchor="mt")
        img = _rot(img, 8)
        x = W * 0.78 if shot["kind"] == "host" else W * 0.80
        R.paste_scaled(base, img, x, H * 0.22, 0.9 + 0.1 * back(a))

    def person(self, base, shot, t):
        p = shot["person"]
        tl = t - p["at"]
        r = ease_out(tl / 0.35) * (1 - ease_out((tl - 4.2) / 0.35))
        if r <= 0:
            return
        u = self.u
        d = ImageDraw.Draw(base)
        x = int(60 * u - 600 * u * (1 - r))
        y = int(self.H * 0.66)
        f1, f2 = font(L.TITLE_FONT, 48 * u), font(L.BODY_SEMI, 24 * u)
        name, role = p["name"].upper(), p.get("role", "")
        w = int(max(d.textlength(name, font=f1), d.textlength(role, font=f2)) + 50 * u)
        d.rectangle((x, y, x + int(8 * u), y + int(104 * u)), fill=L.YELLOW + (255,))
        d.rectangle((x + int(8 * u), y, x + w, y + int(64 * u)), fill=(20, 16, 16, int(235 * r)))
        d.text((x + int(26 * u), y + int(34 * u)), name, font=f1, fill=(255, 255, 255, int(255 * r)), anchor="lm")
        if role:
            d.rectangle((x + int(8 * u), y + int(64 * u), x + w, y + int(104 * u)), fill=(250, 246, 236, int(240 * r)))
            d.text((x + int(26 * u), y + int(84 * u)), role, font=f2, fill=(20, 20, 20, int(255 * r)), anchor="lm")

    def stamp(self, base, shot, t):
        s = shot["stamp"]
        a = clamp((t - s["at"]) / 0.18)
        if a <= 0:
            return
        W, H, u = self.W, self.H, self.u
        im = stamp_image(s["text"].upper(), int(84 * u))
        scale = 1.0 + 1.2 * (1 - ease_out(a))
        shake = (math.sin((t - s["at"]) * 60) * 6 * u * max(0.0, 1 - (t - s["at"]) / 0.3)) if a >= 1 else 0
        spot = {"host": (0.74, 0.30), "split": (0.74, 0.30), "explain": (0.5, 0.86), "flow": (0.5, 0.84), "photo": (0.76, 0.70),
                "map": (0.80, 0.70)}.get(shot["kind"], (0.72, 0.72))
        x, y = s.get("xy") or (W * spot[0], H * spot[1])
        R.paste_scaled(base, im, x + shake, y, scale, clamp(a * 1.4))

    def source(self, base, text, tl):
        u = self.u
        d = ImageDraw.Draw(base)
        d.text((self.W - 24 * u, self.H - 16 * u), str(text), font=font(L.MONO_FONT, 16 * u),
               fill=(230, 230, 230, int(160 * clamp(tl / 0.5))), anchor="rb")


def csv_num(text):
    m = re.search(r"\d[\d,]*\.?\d*", str(text or ""))
    return float(m.group(0).replace(",", "")) if m else None


def fill_share(frame, bg, margin=(0.12, 0.06), tol=28):
    """How much of the frame the card's content covers (0..1): the box around every pixel that differs from the plain
    background, leaving out the header strip at the top and the credit line at the bottom. Phase 2 rule: >= 0.5."""
    import numpy as np
    a = np.asarray(frame.convert("RGB")).astype("int16")
    b = np.asarray(bg.convert("RGB").resize(frame.size)).astype("int16")
    H = a.shape[0]
    top, bot = int(H * margin[0]), int(H * (1 - margin[1]))
    diff = np.abs(a - b).max(axis=2)[top:bot] > tol
    ys, xs = np.nonzero(diff)
    if not len(xs):
        return 0.0
    box = (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)
    return round(box / float(a.shape[1] * (bot - top)), 3)
