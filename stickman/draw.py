"""Draw one frame: backdrop, place, ground, shadows, props, wobbly figures, title, caption, finish.

Lines are drawn as 2x masks (one per colour) and box-reduced, which gives smooth
anti-aliased lines with plain PIL. Lines 'boil' (re-wobble) every few frames.
Fills (Colour Pop, pale tints in ink looks) sit under the lines on 1x layers.
"""
import math
import random
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import places, props, rig

SS = 2
_CACHE = {}


# ------------------------------------------------------------------ backdrops
def _noise(W, H, cell, seed):
    rng = np.random.default_rng(seed)
    small = rng.normal(0, 1, (H // cell + 2, W // cell + 2)).astype(np.float32)
    return np.asarray(Image.fromarray(small).resize((W, H), Image.BICUBIC), np.float32)


def _radial(W, H):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    return np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2))


def backdrop(W, H, look, place="void"):
    kind = "flat" if look["bg"] == "painted" else look["bg"]      # painted looks fall back to flat colours
    key = ("bg", W, H, look["name"], place if kind == "flat" else "")
    if key in _CACHE:
        return _CACHE[key]
    rng = np.random.default_rng(7)
    img = np.empty((H, W, 3), np.float32)
    if kind == "flat":
        top = np.array(places.PLACES.get(place, places.PLACES["void"])["sky"], np.float32)
        bot = top + (255 - top) * 0.45
        g = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
        img[:] = top * (1 - g) + bot * g
    else:
        img[:] = np.array(look["paper"], np.float32)
        if kind == "paper":
            img += rng.normal(0, 3.2, (H, W, 1)).astype(np.float32)
            img += _noise(W, H, 48, 3)[..., None] * 4.0
            img *= (1 - 0.10 * np.clip(_radial(W, H) - 0.35, 0, None) ** 1.6)[..., None]
        elif kind == "chalk":
            img += _noise(W, H, 90, 4)[..., None] * 5.0 + _noise(W, H, 14, 5)[..., None] * 2.0
            img += rng.normal(0, 2.0, (H, W, 1)).astype(np.float32)
            img *= (1 - 0.25 * np.clip(_radial(W, H) - 0.4, 0, None))[..., None]
        elif kind == "crt":
            img *= (1.25 - 0.55 * np.clip(_radial(W, H), 0, 1.2))[..., None]
        elif kind == "night":
            g = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
            img = img * (1 + 0.9 * (1 - g)) + np.array((4, 6, 14), np.float32) * g
            img += np.clip(_noise(W, H, 160, 6), 0, None)[..., None] * np.array((6, 8, 14), np.float32)
    _CACHE[key] = np.clip(img, 0, 255)
    return _CACHE[key]


PAINT_MARGIN = 1.2          # the picture covers 1.2x the frame so the camera can pan and zoom over it
PARALLAX = 0.7              # the painted room moves a little less than the figures (it is further away)


def painted(path, W, H, cam, shift=0.0):
    """A Flow picture as the room, following the camera (with parallax). None when the file cannot be read."""
    key = ("paint", path, W, H)
    src = _CACHE.get(key)
    if src is None:
        try:
            im = Image.open(path).convert("RGB")
        except Exception:  # noqa: BLE001
            _CACHE[key] = False
            return None
        r = W / H
        if im.width / im.height > r:
            nw = int(im.height * r)
            im = im.crop(((im.width - nw) // 2, 0, (im.width - nw) // 2 + nw, im.height))
        else:
            nh = int(im.width / r)
            im = im.crop((0, (im.height - nh) // 2, im.width, (im.height - nh) // 2 + nh))
        src = _CACHE[key] = im.resize((int(W * PAINT_MARGIN), int(H * PAINT_MARGIN)), Image.LANCZOS)
    if src is False:
        return None
    zb = 1 + (cam["zoom"] - 1) * PARALLAX
    cxw = W / 2 + ((cam["x"] + shift) * W - W / 2) * PARALLAX
    cyw = H * 0.56 + (cam["y"] * H - H * 0.56) * PARALLAX
    m = (PAINT_MARGIN - 1) / 2
    # output (x, y) -> world -> picture pixel
    coeffs = (1 / zb, 0, (-W / 2) / zb + cxw + m * W, 0, 1 / zb, (-H * 0.56) / zb + cyw + m * H)
    out = src.transform((W, H), Image.AFFINE, coeffs, resample=Image.BILINEAR)
    return np.asarray(out, np.float32)


# ------------------------------------------------------------------ pens
class Pen:
    """Line masks by colour (2x) plus fill layers (1x)."""

    def __init__(self, W, H):
        self.W, self.H = W, H
        self.masks = {}
        self.fills = {}

    def d(self, key):
        if key not in self.masks:
            self.masks[key] = Image.new("L", (self.W * SS, self.H * SS), 0)
        return ImageDraw.Draw(self.masks[key])

    def f(self, layer):
        if layer not in self.fills:
            self.fills[layer] = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        return ImageDraw.Draw(self.fills[layer])


class _Haloed:
    """Draws each figure line twice with the same wobble: a wide white outline under it (Meme look), then the line."""

    def __init__(self, main, halo, on):
        self.main, self.halo, self.on = main, halo, on

    def line(self, pts, fill=255, width=1, joint=None):
        if self.on:
            self.halo.line(pts, fill=fill, width=int(width * 2.3) + 2, joint=joint)
            r = (width * 2.3 + 2) / 2
            for p in (pts[0], pts[-1]):
                self.halo.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=fill)
        self.main.line(pts, fill=fill, width=width, joint=joint)

    def ellipse(self, box, fill=255):
        if self.on:
            g = (box[2] - box[0]) * 0.65 + 2
            self.halo.ellipse((box[0] - g, box[1] - g, box[2] + g, box[3] + g), fill=fill)
        self.main.ellipse(box, fill=fill)


def _stroke(d, a, b, w, amp, rng, n=6):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    p1, p2 = rng.uniform(0, 6.283), rng.uniform(0, 6.283)
    pts = []
    for i in range(n + 1):
        s = i / n
        o = amp * math.sin(math.pi * s) * (0.7 * math.sin(p1 + 3 * s) + 0.3 * math.sin(p2 + 7 * s))
        pts.append((a[0] + dx * s + nx * o, a[1] + dy * s + ny * o))
    d.line(pts, fill=255, width=max(1, int(round(w))), joint="curve")
    r = w / 2
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=255)


def _circle(d, c, rad, w, amp, rng, n=30):
    p1, p2 = rng.uniform(0, 6.283), rng.uniform(0, 6.283)
    pts = []
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        rr = rad + amp * (0.7 * math.sin(p1 + 2 * a) + 0.3 * math.sin(p2 + 5 * a))
        pts.append((c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr))
    d.line(pts, fill=255, width=max(1, int(round(w))), joint="curve")


def _polyline(d, pts, w, amp, rng, closed=False):
    pts = [(x + rng.uniform(-amp, amp), y + rng.uniform(-amp, amp)) for x, y in pts]
    if closed:
        pts = pts + [pts[0]]
    if len(pts) < 2:
        return
    d.line(pts, fill=255, width=max(1, int(round(w))), joint="curve")
    r = w / 2
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=255)


def _shape_pts(sh):
    k = sh[0]
    if k == "R":
        x0, y0, x1, y1 = sh[1:5]
        r = min(0.05, abs(x1 - x0) / 4, abs(y1 - y0) / 4)
        pts = []
        for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
            pts += [(cx + math.cos(math.radians(a0 + t)) * r, cy + math.sin(math.radians(a0 + t)) * r) for t in (0, 45, 90)]
        return pts, True
    if k == "C":
        cx, cy, r = sh[1:4]
        return [(cx + math.cos(a) * r, cy + math.sin(a) * r) for a in [2 * math.pi * i / 26 for i in range(26)]], True
    if k == "A":
        cx, cy, r, a0, a1 = sh[1:6]
        n = max(3, int(abs(a1 - a0) / 12))
        return [(cx + math.cos(math.radians(a0 + (a1 - a0) * i / n)) * r,
                 cy + math.sin(math.radians(a0 + (a1 - a0) * i / n)) * r) for i in range(n + 1)], False
    if k == "P":
        return list(sh[1]), True
    if k == "L":
        return list(sh[1]), bool(sh[2])
    return [], False


def draw_prop(pen, name, c2, size2, w, amp, rng, look, line_key="ink", fill_layer="fg", alpha=1.0, flip=1):
    """A prop centred at c2 (2x screen px), box size2 (2x px)."""
    shapes = props.PROPS.get(name)
    if not shapes:
        return
    d = pen.d(line_key)
    fd = pen.f(fill_layer)
    fa = int(255 * alpha * (look["fill_alpha"] if fill_layer == "fg" else look["bg_fill_alpha"]))
    for sh in shapes:
        if sh[0] == "T":
            _, x, y, text, s = sh
            px = max(6, int(s * size2))
            key = ("font", look["font"], px)
            if key not in _CACHE:
                _CACHE[key] = ImageFont.truetype(look["font"], px)
            d.text((c2[0] + x * size2 * flip, c2[1] + y * size2), text, font=_CACHE[key], fill=255, anchor="mm")
            continue
        pts, closed = _shape_pts(sh)
        pts = [(c2[0] + x * size2 * flip, c2[1] + y * size2) for x, y in pts]
        fill = sh[-1] if sh[0] in ("R", "C", "P") else None
        if fill and fa > 0:
            col = look["fills"].get(fill, look["ink"])
            fd.polygon([(x / SS, y / SS) for x, y in pts], fill=(*col, fa))
        _polyline(d, pts, w, amp, rng, closed)


# ------------------------------------------------------------------ face
def _face(d, c, rad, tilt, f, eyes, mouth, w):
    t = math.radians(tilt)
    fwd = (math.cos(t) * f, math.sin(t))
    down = (-math.sin(t) * f, math.cos(t))

    def P(u, v):
        return (c[0] + (u * fwd[0] + v * down[0]) * rad, c[1] + (u * fwd[1] + v * down[1]) * rad)

    def dot(u, v, r):
        p = P(u, v)
        d.ellipse((p[0] - r * rad, p[1] - r * rad, p[0] + r * rad, p[1] + r * rad), fill=255)

    fw = max(1, int(round(w)))
    for k, u in enumerate((0.16, 0.54)):
        if eyes == "closed":
            d.line([P(u - 0.10, -0.10), P(u + 0.10, -0.10)], fill=255, width=fw)
        elif eyes == "happy":
            d.line([P(u - 0.11, -0.04), P(u, -0.16), P(u + 0.11, -0.04)], fill=255, width=fw, joint="curve")
        elif eyes == "half":
            d.line([P(u - 0.10, -0.06), P(u + 0.10, -0.06)], fill=255, width=fw)
            dot(u, -0.02, 0.05)
        elif eyes == "wide":
            dot(u, -0.14, 0.135)
        elif eyes == "up":
            dot(u + 0.04, -0.22, 0.085)
        elif eyes == "angry":
            dot(u, -0.1, 0.08)
            inner = 0.10 if k == 0 else -0.10
            d.line([P(u - inner, -0.34), P(u + inner, -0.24)], fill=255, width=fw)
        else:
            dot(u, -0.12, 0.085)

    mu, mv = 0.36, 0.40
    if mouth in ("smile", "frown"):
        sgn = 1 if mouth == "smile" else -1
        pts = [P(mu + x, mv + sgn * 0.11 * (1 - (x / 0.2) ** 2) - sgn * 0.05) for x in (-0.2, -0.1, 0, 0.1, 0.2)]
        d.line(pts, fill=255, width=fw, joint="curve")
    elif mouth == "flat":
        d.line([P(mu - 0.17, mv), P(mu + 0.17, mv)], fill=255, width=fw)
    elif mouth == "open":
        dot(mu, mv, 0.10)
    elif mouth == "o":
        p = P(mu, mv + 0.02)
        r = 0.12 * rad
        d.ellipse((p[0] - r, p[1] - r * 1.2, p[0] + r, p[1] + r * 1.2), outline=255, width=fw)
    elif mouth == "big":
        pts = [P(mu - 0.24, mv - 0.08)]
        pts += [P(mu + 0.24 * math.cos(a), mv - 0.08 + 0.26 * math.sin(a))
                for a in [math.pi * k / 8 for k in range(9)]][::-1]
        d.polygon(pts, fill=255)


# ------------------------------------------------------------------ text
def _rich(text):
    """'Meet *Sam*.' -> [('Meet ', False), ('Sam', True), ('.', False)]"""
    out, acc = [], False
    for part in text.split("*"):
        if part:
            out.append((part, acc))
        acc = not acc
    return out


def text_layer(text, size, look):
    key = ("text", text, size, look["name"])
    if key not in _CACHE:
        font = ImageFont.truetype(look["font"], size)
        segs = _rich(text.upper() if look["upper"] else text)
        widths = [font.getlength(s) for s, _ in segs]
        asc, desc = font.getmetrics()
        sw = max(2, int(size * 0.085)) if look["text_stroke"] else 0     # meme captions: white with a black edge
        pad = 4 + sw
        img = Image.new("RGBA", (int(sum(widths)) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = pad
        for (s, acc), wdt in zip(segs, widths):
            kw = {"stroke_width": sw, "stroke_fill": (*look["text_stroke"], 255)} if sw else {}
            d.text((x, pad), s, font=font, fill=(*(look["accent"] if acc else look["text"]), 255), **kw)
            x += wdt
        _CACHE[key] = img
    return _CACHE[key]


def _place(base, layer, cx, cy, scale=1.0, alpha=1.0, reveal=1.0):
    if alpha <= 0.01 or reveal <= 0:
        return
    lay = layer
    if abs(scale - 1) > 1e-3:
        lay = lay.resize((max(1, int(lay.width * scale)), max(1, int(lay.height * scale))), Image.BICUBIC)
    if alpha < 0.999 or reveal < 0.999:
        a = np.asarray(lay.getchannel("A"), np.float32) * alpha
        if reveal < 0.999:
            edge = 40.0
            xs = np.arange(lay.width, dtype=np.float32)
            a *= np.clip((reveal * (lay.width + edge) - xs) / edge, 0, 1)[None, :]
        lay = lay.copy()
        lay.putalpha(Image.fromarray(a.astype(np.uint8)))
    base.alpha_composite(lay, (int(cx - lay.width / 2), int(cy - lay.height / 2)))


def ease_pop(x):
    x = min(max(x, 0.0), 1.0)
    c = 1.7
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def _spoken_caption(out, fr, look, W, H, lay_):
    """One line; each word darkens as it is spoken (the key word in accent), upcoming words wait faintly."""
    size = int(H * lay_["caption_size"])
    segs = fr["caption"].split()
    layers = [text_layer(w + " ", size, look) for w in segs]
    total = sum(l.width for l in layers) - 8 * len(layers)
    pop = ease_pop(fr["lt"] / 0.22)
    s = (0.88 + 0.12 * pop) * min(1.0, W * lay_.get("caption_w", 0.9) / max(1, total))
    x = W * lay_.get("caption_x", 0.5) - total * s / 2
    y = H * lay_["caption_y"]
    if look["caption_box"]:
        hh = layers[0].height * s
        box = Image.new("RGBA", out.size, (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle((x - 22, y - hh * 0.55, x + total * s + 14, y + hh * 0.55),
                                              radius=int(hh * 0.4), fill=(*look["caption_box"], int(235 * min(1, fr["lt"] / 0.1))))
        out.alpha_composite(box)
    times = [w["t"] for w in fr["words"]]
    for k, lay in enumerate(layers):
        tk = times[k] if k < len(times) else times[-1]
        a = 0.28 + 0.72 * min(1.0, max(0.0, (fr["t"] - tk + 0.05) / 0.12))
        w = (lay.width - 8) * s
        _place(out, lay, x + w / 2 + 4 * s, y, scale=s, alpha=a * min(1.0, fr["lt"] / 0.1))
        x += w


# ------------------------------------------------------------------ finishing
def _post(img, look, fr, W, H, stage):
    for p in look["post"]:
        if stage == "pre" and p == "vignette":
            r = _CACHE.setdefault(("rad", W, H), _radial(W, H))
            img *= (1 - 0.55 * np.clip(r - 0.25, 0, 1) ** 1.3)[..., None]
        elif stage == "pre" and p == "grain":
            g = _CACHE.setdefault(("grain", W, H), np.random.default_rng(3).normal(0, 6, (H + 64, W + 64)).astype(np.float32))
            o = (fr["i"] * 37) % 64
            img += g[o:o + H, o:o + W, None]
        elif stage == "post" and p == "scanlines":
            a = np.asarray(img, np.float32)
            a[::3] *= 0.80
            a[:, :, 0] = np.roll(a[:, :, 0], 2, axis=1)
            a[:, :, 2] = np.roll(a[:, :, 2], -2, axis=1)
            img = a
        elif stage == "post" and p == "bezel":
            m = _CACHE.get(("bezel", W, H))
            if m is None:
                bz = Image.new("L", (W, H), 255)
                pad = int(H * 0.035)
                ImageDraw.Draw(bz).rounded_rectangle((pad, pad, W - pad, H - pad), radius=int(H * 0.09), fill=0)
                bz = bz.filter(ImageFilter.GaussianBlur(H * 0.006))
                m = np.asarray(bz, np.float32)[..., None] / 255
                _CACHE[("bezel", W, H)] = m
            img = np.asarray(img, np.float32) * (1 - m) + np.array((14, 14, 16), np.float32) * m
    return img


LAYOUT = {"caption_y": 0.905, "caption_size": 0.062, "title_y": 0.155, "title_size": 0.095, "place_scale": 1.0}


# ------------------------------------------------------------------ frame
def frame(fr, spec, look):
    W, H = spec["size"]
    lay_ = dict(LAYOUT, **(spec.get("layout") or {}))
    cam = fr["cam"]
    z = cam["zoom"]
    shift = spec.get("host_shift", 0.0)          # a host in the corner: the stage slides away from it
    cx, cy = (cam["x"] + shift) * W, cam["y"] * H

    def C(p):  # world px -> 2x screen px
        return (((p[0] - cx) * z + W * 0.5) * SS, ((p[1] - cy) * z + H * 0.56) * SS)

    pen = Pen(W, H)
    tone = Image.new("L", (W, H), 0)
    dt = ImageDraw.Draw(tone)
    boil = fr["i"] // look["boil_frames"]
    hmax = max(f["hpx"] for f in fr["figs"])
    base_w = look["line"] * hmax * SS * z
    base_amp = look["wobble"] * hmax * SS * z
    place = fr.get("place") or "void"
    gy = C((0, fr["ground"]))[1]
    pic = None
    if look["bg"] == "painted" and (spec.get("backdrops") or {}).get(place):
        pic = painted(spec["backdrops"][place], W, H, cam, shift)

    # ground band (Colour Pop) and place, faint, behind everything; a painted room replaces both
    ground_fill = look["ground_fill"] or ((132, 206, 138) if look["bg"] == "painted" else None)
    if ground_fill and pic is None:
        pen.f("bg").rectangle((0, gy / SS, W, H), fill=(*ground_fill, 255))
    prng = random.Random(boil * 13 + 1)
    for name, x, base, size in ([] if pic is not None else places.PLACES.get(place, places.PLACES["void"])["items"]):
        s = size * H * lay_["place_scale"]
        base = base * lay_["place_scale"]
        if lay_.get("wall_min") is not None and base > 0:      # Shorts: wall items hang above the figures' heads
            base = max(base, lay_["wall_min"])
        x = min(0.97, max(0.03, 0.5 + (x - 0.5) * lay_.get("spread", 1.0)))
        c = C((x * W, fr["ground"] - base * H - s * 0.48))
        draw_prop(pen, name, c, s * SS * z, base_w * 0.62, base_amp * 0.6, prng, look, line_key="bg", fill_layer="bg")

    # ground line with a few hand-drawn breaks
    rng = random.Random(boil * 31 + 5)
    gw = base_w * 0.55
    x = -0.2 * W
    seg = random.Random(11)
    d_ink = pen.d("ink")
    while x < 1.2 * W and (look["ground_line"] or pic is None):
        L = seg.uniform(0.22, 0.45) * W
        _stroke(d_ink, C((x, fr["ground"])), C((x + L, fr["ground"])), gw, base_amp * 0.6, rng, n=10)
        x += L + seg.uniform(0.015, 0.04) * W

    # props: beat props and the ones poses carry
    for p in fr.get("props") or []:
        pop = ease_pop(p["age"] / 0.25) if p["age"] < 0.25 else 1.0
        if pop <= 0.02:
            continue
        r = random.Random(zlib.crc32(f"{p['name']}:{boil}".encode()))
        size2 = p["size"] * SS * z * max(0.05, pop)
        small = p["size"] < 0.12 * H
        draw_prop(pen, p["name"], C((p["x"], p["y"])), size2, base_w * (0.55 if small else 0.75),
                  base_amp * 0.5, r, look, line_key=p.get("line", "ink"))

    # figures
    for k, f in enumerate(fr["figs"]):
        j, h, fc = f["joints"], f["hpx"], f["facing"]
        rng = random.Random(zlib.crc32(f"{f['name']}:{boil}".encode()))
        w = look["line"] * h * SS * z
        amp = look["wobble"] * h * SS * z
        key = f"fig{k}" if look["fig_colors"] else "ink"
        d = _Haloed(pen.d(key), pen.d("halo") if look["halo"] is not None else None, look["halo"] is not None)
        if look["shadow"] > 0:
            sx, sy = ((j["pelvis"][0] - cx) * z + W * 0.5), ((fr["ground"] - cy) * z + H * 0.56)
            kk = max(0.35, 1 - f["lift"] * 1.6)
            rx, ry = 0.17 * h * z * kk, 0.028 * h * z * kk
            dt.ellipse((sx - rx, sy - ry, sx + rx, sy + ry), fill=255)
        _stroke(d, C(j["pelvis"]), C(j["neck"]), w, amp, rng)
        hc = C(j["head"])
        rad = rig.HEAD_R * h * SS * z
        tl = math.radians(f["tilt"])
        under = (hc[0] - math.sin(tl) * fc * rad, hc[1] + math.cos(tl) * rad)
        _stroke(d, C(j["neck"]), under, w, amp * 0.3, rng, n=2)
        for s in ("b", "f"):
            _stroke(d, C(j["shoulder"]), C(j["elbow_" + s]), w, amp, rng)
            _stroke(d, C(j["elbow_" + s]), C(j["hand_" + s]), w, amp, rng)
            _stroke(d, C(j["pelvis"]), C(j["knee_" + s]), w, amp, rng)
            _stroke(d, C(j["knee_" + s]), C(j["foot_" + s]), w, amp, rng)
            ft = j["foot_" + s]
            _stroke(d, C(ft), C((ft[0] + 0.05 * h * fc, ft[1])), w, amp * 0.2, rng, n=2)
        if look["fig_colors"] or look["head_fill"]:   # filled head so coloured figures read as characters
            pen.f("fg").ellipse(((hc[0] - rad) / SS, (hc[1] - rad) / SS, (hc[0] + rad) / SS, (hc[1] + rad) / SS),
                                fill=(*(look["head_fill"] or (255, 255, 255)), 255))
        _circle(d, hc, rad, w, amp * 0.8, rng)
        eyes = f["eyes"]
        if eyes not in ("closed", "happy") and ((fr["t"] + f["seed"] * 1.37) % 3.3) < 0.12:
            eyes = "closed"
        _face(pen.d("face") if look["fig_colors"] else d.main, hc, rad, f["tilt"], fc, eyes, f["mouth"], w * 0.6)

    # title: writes on, then an accent underline draws itself; fades out at its end
    lt = fr["lt"]
    tlt, bd = fr.get("title_lt", lt), fr.get("title_dur", fr["beat_dur"])
    title_layer, t_alpha = None, 0.0
    if fr["title"]:
        t_alpha = min(1.0, max(0.0, (bd - tlt) / 0.3))
        title_layer = text_layer(fr["title"], int(H * lay_["title_size"]), look)
        t_scale = min(1.0, W * 0.9 / max(1, title_layer.width))
        u = min(1.0, max(0.0, (tlt - 0.9) / 0.4))
        if u > 0:
            half = title_layer.width * t_scale / 2 * 0.92
            y = H * lay_["title_y"] + title_layer.height * t_scale * 0.52
            a = ((W / 2 - half) * SS, y * SS)
            b = ((W / 2 - half + 2 * half * u) * SS, (y + 4) * SS)
            ul = Image.new("L", (W * SS, H * SS), 0)
            _stroke(ImageDraw.Draw(ul), a, b, H * 0.009 * SS, H * 0.004 * SS, random.Random(boil), n=10)
            pen.d("accent")
            pen.masks["accent"].paste(ul.point(lambda v: int(v * t_alpha)), (0, 0), ul)

    # composite
    img = pic if pic is not None else backdrop(W, H, look, place).copy()

    def over(layer):
        a = np.asarray(layer, np.float32)
        al = a[..., 3:4] / 255
        return img * (1 - al) + a[..., :3] * al

    if "bg" in pen.fills:
        img = over(pen.fills["bg"])
    ink_c = np.array(look["ink"], np.float32)
    if "bg" in pen.masks:
        a = np.asarray(pen.masks["bg"].reduce(SS), np.float32)[..., None] / 255 * look["bg_alpha"]
        img = img * (1 - a) + np.array(look["bg_ink"], np.float32) * a
    if look["shadow"] > 0:
        tn = np.asarray(tone.filter(ImageFilter.GaussianBlur(H * 0.006)), np.float32)[..., None] / 255 * look["shadow"]
        img = img * (1 - tn) + ink_c * tn
    if "fg" in pen.fills:
        img = over(pen.fills["fg"])
    grain = None
    if "chalk" in look["post"]:
        grain = _CACHE.setdefault(("chalkgrain", W, H), np.clip(0.72 + _noise(W, H, 2, 9) * 0.25, 0.35, 1.0)[..., None])
    if look["halo"] is not None:
        # figures have their own wide outline; props and other ink lines get a thinner one from the ink itself
        hm = pen.masks["ink"].reduce(SS).filter(ImageFilter.MaxFilter(5)) if "ink" in pen.masks else None
        if "halo" in pen.masks:
            fh = pen.masks["halo"].reduce(SS)
            hm = fh if hm is None else Image.fromarray(np.maximum(np.asarray(hm), np.asarray(fh)))
        pen.masks["halo"] = hm
    if pen.masks.get("halo") is not None:
        a = np.asarray(pen.masks["halo"], np.float32)[..., None] / 255
        img = img * (1 - a) + np.array(look["halo"], np.float32) * a
    order = ["ink"] + [f"fig{k}" for k in range(len(fr["figs"]))] + ["face", "accent"]
    for key in order:
        if key not in pen.masks:
            continue
        col = (np.array(look["fig_colors"][int(key[3:]) % len(look["fig_colors"])], np.float32) if key.startswith("fig")
               else np.array(look["accent"], np.float32) if key == "accent" else ink_c)
        a = np.asarray(pen.masks[key].reduce(SS), np.float32)[..., None] / 255
        if grain is not None:
            a = a * grain
        img = img * (1 - a) + col * a
    img = _post(img, look, fr, W, H, "pre")
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    if spec.get("host"):
        from . import host as _host
        _host.paste(out, fr, spec)

    if title_layer is not None:
        _place(out, title_layer, W / 2, H * lay_["title_y"], scale=t_scale, alpha=t_alpha, reveal=min(1.0, tlt / 0.9))
    if fr["caption"] and fr.get("words"):
        _spoken_caption(out, fr, look, W, H, lay_)
    elif fr["caption"]:
        cap = text_layer(fr["caption"], int(H * lay_["caption_size"]), look)
        pop = ease_pop(lt / 0.22)
        _place(out, cap, W * lay_.get("caption_x", 0.5), H * lay_["caption_y"],
               scale=(0.85 + 0.15 * pop) * min(1.0, W * lay_.get("caption_w", 0.9) / max(1, cap.width)),
               alpha=min(1.0, lt / 0.12))
    if any(p in look["post"] for p in ("scanlines", "bezel")):
        img = _post(np.asarray(out.convert("RGB"), np.float32), look, fr, W, H, "post")
        return np.clip(img, 0, 255).astype(np.uint8).tobytes()
    return out.convert("RGB").tobytes()
