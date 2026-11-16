"""DEMO ONLY: the Lisbon TAP opening (0-41 s) rebuilt as a cinematic-skill style "one wall" film.
Same voice, same pictures (frames taken from the current v7 film), new presentation:
one dark board, prints pinned on it, one continuous camera gliding between them along red string,
counters / stamps / pen circles / labels landing on the spoken word, spotlight + old-item dimming,
motion blur on fast moves, item-driven synthesised sound. No app file is changed.

Usage: python3 wall_demo.py <work_dir> <project_dir>   (work_dir holds P1..P5.png)
Writes work_dir/after_silent.mp4, work_dir/sfx_events.json
"""
import bisect, json, math, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

WD, PROJ = Path(sys.argv[1]), Path(sys.argv[2])
FONTS = Path("/Users/muhammadnabil/Downloads/video_generator-main/assets/fonts")
W, H, FPS, DUR = 1280, 720, 25, 41.0
WORDS = json.loads((PROJ / "state/narration_words.json").read_text())["words"]


def F(name, size):
    return ImageFont.truetype(str(FONTS / name), max(6, int(size)))


def word(w, after=0.0):
    for x, s, _e in WORDS:
        if s >= after and x.lower() == w:
            return s
    raise KeyError(w)


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


ease_out = lambda k: 1 - (1 - k) ** 3
def back_out(k, s=1.6):
    k -= 1
    return k * k * ((s + 1) * k + s) + 1


# ------------------------------------------------------------------ camera: monotone cubic through keys (never overshoots)
class Spline:
    def __init__(self, keys):
        self.t = [k[0] for k in keys]; self.v = [k[1] for k in keys]
        n = len(keys); d = [(self.v[i + 1] - self.v[i]) / (self.t[i + 1] - self.t[i]) for i in range(n - 1)]
        m = [0.0] * n; m[0], m[-1] = d[0], d[-1]
        for i in range(1, n - 1):
            m[i] = 0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2
        for i in range(n - 1):
            if d[i] == 0:
                m[i] = m[i + 1] = 0.0; continue
            a, b = m[i] / d[i], m[i + 1] / d[i]
            if a * a + b * b > 9:
                k = 3 / math.hypot(a, b); m[i] = k * a * d[i]; m[i + 1] = k * b * d[i]
        self.m = m

    def __call__(self, t):
        T = self.t
        if t <= T[0]: return self.v[0]
        if t >= T[-1]: return self.v[-1]
        i = bisect.bisect_right(T, t) - 1; h = T[i + 1] - T[i]; u = (t - T[i]) / h
        return ((2 * u ** 3 - 3 * u ** 2 + 1) * self.v[i] + (u ** 3 - 2 * u ** 2 + u) * h * self.m[i]
                + (-2 * u ** 3 + 3 * u ** 2) * self.v[i + 1] + (u ** 3 - u ** 2) * h * self.m[i + 1])


# ------------------------------------------------------------------ items (world px; at zoom 1 the frame shows 1280 x 720)
CUES = []          # (t, sound)
ITEMS = []
SHAKES = []        # (t, amp)


class Item:
    z = 0
    def __init__(self, t_in, dim_at=None):
        self.t_in, self.dim_at = t_in, dim_at
    def dim(self, t):
        return 0.0 if self.dim_at is None else 0.5 * clamp((t - self.dim_at) / 0.6)


def add(it):
    ITEMS.append(it); return it


class Print(Item):
    """A photo print: white border, drop shadow, red pin, drops in; optional red name bar."""
    def __init__(self, key, x, y, w, rot, t_in, label=None, label_t=None, dim_at=None):
        super().__init__(t_in, dim_at)
        im = Image.open(WD / f"{key}.png").convert("RGB")
        h = int(w * im.height / im.width)
        b = int(w * 0.035)
        card = Image.new("RGBA", (w + 2 * b, h + 2 * b + int(b * 0.6)), (238, 234, 226, 255))
        card.paste(im.resize((w, h), Image.LANCZOS), (b, b))
        pad = 60
        self.base = Image.new("RGBA", (card.width + 2 * pad, card.height + 2 * pad), (0, 0, 0, 0))
        sh = Image.new("RGBA", self.base.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle((pad + 14, pad + 22, pad + card.width + 14, pad + card.height + 22), fill=(0, 0, 0, 150))
        self.base = Image.alpha_composite(self.base, sh.filter(ImageFilter.GaussianBlur(22)))
        self.base.alpha_composite(card, (pad, pad))
        d = ImageDraw.Draw(self.base)
        px, py, r = self.base.width // 2, pad + b // 2, 16
        d.ellipse((px - r, py - r, px + r, py + r), fill=(186, 30, 26), outline=(110, 14, 12), width=3)
        self.x, self.y, self.w, self.h, self.rot = x, y, w, h, rot
        self.label, self.label_t = label, label_t
        self.pad, self.b = pad, b
        CUES.append((t_in, "drop"))
        if label: CUES.append((label_t, "pop"))

    def on(self, fx, fy):
        """World point at a fraction of the picture (rotation included)."""
        dx, dy = (fx - 0.5) * self.w, (fy - 0.5) * self.h
        a = math.radians(self.rot)
        return self.x + dx * math.cos(a) - dy * math.sin(a), self.y + dx * math.sin(a) + dy * math.cos(a)

    def sprite(self, t):
        k = clamp((t - self.t_in) / 0.5)
        lab = 0.0 if not self.label else clamp((t - self.label_t) / 0.35)
        return ("print", round(lab * 12)), (1.0 + 0.25 * (1 - ease_out(k))), clamp(k * 2.5)

    def draw_sprite(self, key):
        im = self.base.copy()
        lab = key[1] / 12
        if self.label and lab > 0:
            d = ImageDraw.Draw(im); f = F("Outfit-ExtraBold.ttf", 46)
            tw = d.textlength(self.label, font=f) + 44
            x0, y0 = self.pad + self.b, self.pad + self.b + self.h - 92
            d.rectangle((x0, y0, x0 + tw * lab, y0 + 70), fill=(176, 24, 20))
            if lab > 0.6:
                d.text((x0 + 22, y0 + 8), self.label, font=f, fill=(250, 246, 238))
        return im


class VideoPrint(Print):
    """A print whose picture is moving footage (frames in WD/<key>/). Camera zoomed in on it = the clip full screen."""
    def __init__(self, key, x, y, w, t_in, t0, label=None, label_t=None, dim_at=None):
        self.frames = sorted((WD / key).glob("*.jpg")); self.t0 = t0
        Image.open(self.frames[0]).save(WD / f"{key}.png")
        super().__init__(key, x, y, w, 0.0, t_in, label, label_t, dim_at)
        self.cur = 0

    def frame_at(self, t):
        n = len(self.frames); i = int((t - self.t0) * FPS)
        if i < 0: return 0
        p = i % (2 * n - 2)                     # after its scene the clip keeps moving (ping-pong), never frozen
        return p if i < n else (p if p < n else 2 * n - 2 - p)

    def sprite(self, t):
        key, s, a = super().sprite(t)
        return ("vid", self.frame_at(t)) + key[1:], s, a

    def draw_sprite(self, key):
        im = self.base.copy()
        fr = Image.open(self.frames[key[1]]).convert("RGB").resize((self.w, self.h), Image.BILINEAR)
        im.paste(fr, (self.pad + self.b, self.pad + self.b))
        lab = key[2] / 12
        if self.label and lab > 0:              # the red name bar sits on top of the footage
            d = ImageDraw.Draw(im); f = F("Outfit-ExtraBold.ttf", 34)
            tw = d.textlength(self.label, font=f) + 36
            x0, y0 = self.pad + self.b + 30, self.pad + self.b + self.h - 110
            d.rectangle((x0, y0, x0 + tw * lab, y0 + 54), fill=(176, 24, 20))
            if lab > 0.6:
                d.text((x0 + 18, y0 + 6), self.label, font=f, fill=(250, 246, 238))
        return im


class Text(Item):
    """Big condensed type; optional yellow block behind it; types on letter by letter."""
    def __init__(self, text, x, y, size, t_in, rgb=(244, 240, 232), block=None, type_on=0.0, rot=0.0, dim_at=None, hit=None):
        super().__init__(t_in, dim_at)
        self.text, self.x, self.y, self.size, self.rgb, self.block, self.type_on, self.rot = text, x, y, size, rgb, block, type_on, rot
        CUES.append((t_in, "type" if type_on else (hit or "impact")))

    def sprite(self, t):
        n = len(self.text) if not self.type_on else int(len(self.text) * clamp((t - self.t_in) / self.type_on))
        k = clamp((t - self.t_in) / 0.3)
        return ("text", n), (1.0 if self.type_on else 1.0 + 0.4 * (1 - ease_out(k))), (1.0 if self.type_on else k)

    def draw_sprite(self, key):
        f = F("Outfit-ExtraBold.ttf", self.size)
        full = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), self.text, font=f)
        w, h = full[2] + 80, int(self.size * 1.35) + 40
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        if self.block:
            d.rectangle((10, 14, w - 10, h - 14), fill=self.block)
        else:
            d.text((44, 26), self.text[:key[1]], font=f, fill=(0, 0, 0, 160))
        d.text((40, 20), self.text[:key[1]], font=f, fill=self.rgb)
        return im


class Counter(Item):
    """A number rolling up to its value on the spoken word, with a caption."""
    def __init__(self, x, y, size, value, t_in, t_land, fmt, caption, rgb=(244, 240, 232), dim_at=None):
        super().__init__(t_in, dim_at)
        self.x, self.y, self.size, self.value, self.t_land, self.fmt, self.caption, self.rgb, self.rot = x, y, size, value, t_land, fmt, caption, rgb, 0.0
        CUES.append((t_in, "ticks:%.2f" % (t_land - t_in))); CUES.append((t_land, "impact"))
        SHAKES.append((t_land, 7))

    def sprite(self, t):
        k = clamp((t - self.t_in) / max(0.2, self.t_land - self.t_in))
        return ("ctr", round(ease_out(k) * 40)), 1.0 + (0.12 * math.sin(math.pi * clamp((t - self.t_land) / 0.25))), clamp(k * 4)

    def draw_sprite(self, key):
        v = self.value * key[1] / 40
        s = self.fmt(v)
        f, fc = F("Outfit-ExtraBold.ttf", self.size), F("Inter-Bold.ttf", self.size * 0.24)
        im = Image.new("RGBA", (int(self.size * 5.2), int(self.size * 1.7)), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        cx = im.width / 2
        d.text((cx + 4, 6), s, font=f, fill=(0, 0, 0, 150), anchor="mt"); d.text((cx, 0), s, font=f, fill=self.rgb, anchor="mt")
        d.text((cx, self.size * 1.18), self.caption, font=fc, fill=(206, 200, 190), anchor="mt")
        return im


class Stamp(Item):
    def __init__(self, text, x, y, size, rot, t_in, dim_at=None):
        super().__init__(t_in, dim_at)
        self.text, self.x, self.y, self.size, self.rot = text, x, y, size, rot
        CUES.append((t_in, "stamp")); SHAKES.append((t_in, 14))

    def sprite(self, t):
        k = clamp((t - self.t_in) / 0.18)
        return ("stamp",), 1.0 + 1.2 * (1 - k) ** 2, clamp(k * 3) * 0.92

    def draw_sprite(self, key):
        f = F("Outfit-ExtraBold.ttf", self.size)
        tw = ImageDraw.Draw(Image.new("L", (1, 1))).textlength(self.text, font=f)
        w, h = int(tw + self.size), int(self.size * 1.6)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        col = (196, 32, 28, 235)
        d.rectangle((8, 8, w - 8, h - 8), outline=col, width=max(4, self.size // 9))
        d.text((w / 2, h / 2), self.text, font=f, fill=col, anchor="mm")
        noise = Image.effect_noise((w, h), 90).point(lambda v: 255 if v > 70 else 0)
        im.putalpha(ImageChops.multiply(im.getchannel("A"), noise))
        return im


class Note(Item):
    """Handwritten note."""
    def __init__(self, text, x, y, size, rot, t_in, rgb=(250, 220, 90), dim_at=None):
        super().__init__(t_in, dim_at)
        self.text, self.x, self.y, self.size, self.rot, self.rgb = text, x, y, size, rot, rgb
        CUES.append((t_in, "pencil"))

    def sprite(self, t):
        n = int(len(self.text) * clamp((t - self.t_in) / 0.7))
        return ("note", n), 1.0, 1.0

    def draw_sprite(self, key):
        f = F("ChalkboardSE.ttc", self.size)
        tw = ImageDraw.Draw(Image.new("L", (1, 1))).textlength(self.text, font=f)
        im = Image.new("RGBA", (int(tw + 40), int(self.size * 1.6)), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((20, 6), self.text[:key[1]], font=f, fill=self.rgb)
        return im


# screen-drawn items (lines): string, pen ellipse, underline
class Line(Item):
    z = 5
    def __init__(self, kind, pts_fn, t_in, dur, width, rgb, persist=True, dim_at=None):
        super().__init__(t_in, dim_at)
        self.kind, self.pts_fn, self.dur, self.width, self.rgb, self.persist = kind, pts_fn, dur, width, rgb, persist
        CUES.append((t_in, {"string": "slide", "pen": "marker", "under": "marker"}[kind]))


def string(a, b, t_in, dur=0.9, sag=0.06, dim_at=None):
    def pts():
        (x0, y0), (x1, y1) = a, b
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2 + sag * math.hypot(x1 - x0, y1 - y0)
        return [((1 - u) ** 2 * x0 + 2 * (1 - u) * u * mx + u * u * x1, (1 - u) ** 2 * y0 + 2 * (1 - u) * u * my + u * u * y1)
                for u in [i / 40 for i in range(41)]]
    return add(Line("string", pts, t_in, dur, 9, (190, 30, 26), dim_at=dim_at))


def pen_ring(cx, cy, rx, ry, t_in, dur=0.55, rot=-6, dim_at=None):
    def pts():
        a0 = math.radians(rot); out = []
        for i in range(57):
            u = i / 48 * 2 * math.pi + 0.4
            r = 1 + 0.06 * math.sin(u * 3)
            x, y = rx * r * math.cos(u), ry * r * math.sin(u)
            out.append((cx + x * math.cos(a0) - y * math.sin(a0), cy + x * math.sin(a0) + y * math.cos(a0)))
        return out
    return add(Line("pen", pts, t_in, dur, 10, (236, 60, 44), dim_at=dim_at))


def underline(x0, x1, y, t_in, dim_at=None):
    return add(Line("under", lambda: [(x0 + (x1 - x0) * i / 20, y + 6 * math.sin(i / 3)) for i in range(21)], t_in, 0.4, 12,
                    (250, 210, 60), dim_at=dim_at))


# ------------------------------------------------------------------ THE FILM: full-screen footage + the wall in between
T = word
ZF = 1280 / 900 * 1.025                          # zoom at which a 900-wide print's footage fills the frame
V1 = add(VideoPrint("FS1", 0, 130, 900, 0.0, 0.0, "WINNER: LUFTHANSA", T("lufthansa")))
add(Text("14 OCTOBER 2026", -175, 300, 44, 0.15, rgb=(28, 24, 20), block=(244, 200, 40), type_on=1.0))
add(Note("Portugal's cabinet decides", -170, 230, 34, -2, T("cabinet")))
C1 = add(Counter(1550, 110, 120, 1.025, T("price"), T("billion"), lambda v: f"€{v:.3f} BN", "THE PRICE", dim_at=20.4))
C2 = add(Counter(2250, 110, 120, 44.9, T("44"), T("9", 12.0) + 0.1, lambda v: f"{v:.1f}%", "OF TAP", dim_at=20.4))
string(V1.on(0.99, 0.2), (1260, 60), T("price") - 0.3, dim_at=20.4)
pen_ring(2250, 72, 250, 100, T("of", 13.0), dim_at=20.4)
underline(1320, 1780, 262, T("climbs"), dim_at=20.4)
add(Note("≈ €1.2 BN with the employee share", 1600, 360, 46, -2, T("billion", 16.0) - 0.3, dim_at=20.4))
V3 = add(VideoPrint("FS3", 3350, 160, 900, 20.3, 20.54, "TAP AIR PORTUGAL", T("tap", 22.0) + 0.1, dim_at=29.4))
add(Text("HERE IS THE STRANGE PART", 3350, 0, 54, T("here", 20.0) + 0.1, hit="boom", block=(16, 18, 22), dim_at=29.4))
string((2250, 230), V3.on(0.01, 0.05), T("here", 20.0) - 0.3, dim_at=29.4)
C3 = add(Counter(3250, 760, 125, 99.2, T("lost"), T("million", 23.5), lambda v: f"−€{v:.1f} M", "LOST IN H1 2026",
                 rgb=(236, 72, 56), dim_at=29.4))
add(Stamp("+40% WORSE", 3820, 690, 64, 8, T("40") + 0.05, dim_at=29.4))
V5 = add(VideoPrint("FS5", 5000, 120, 900, 29.3, 29.58, "LISBON AIRPORT", T("airport", 30.0), dim_at=35.0))
rx, ry = V5.on(0.64, 0.19)
pen_ring(rx, ry, 120, 46, T("single"), rot=-4, dim_at=35.0)
add(Note("ONE runway", rx - 40, ry + 80, 34, -3, T("runway"), dim_at=35.0))
hx, hy = V5.on(0.36, 0.6)
pen_ring(hx, hy, 170, 75, T("neighbourhoods"), rot=3, dim_at=35.0)
add(Note("homes all around it", hx + 230, hy + 20, 32, 2, T("capital") - 0.2, dim_at=35.0))
string(V3.on(0.99, 0.95), V5.on(0.01, 0.05), T("it", 29.0) - 0.3, dim_at=35.0)
V6 = add(VideoPrint("FS6", 6550, 60, 900, 34.9, 35.18, "THE BUYER", T("buyer")))
add(Stamp("NO MAJORITY", 6650, 120, 64, -9, T("majority") + 0.05))
string(V5.on(0.99, 0.95), V6.on(0.01, 0.05), T("and", 35.0) - 0.2)
string(V1.on(0.5, 0.99), V6.on(0.5, 0.99), T("lufthansa", 37.0), dur=1.4, sag=0.08)
add(Text("BEAT AIR FRANCE-KLM", 3300, 1150, 110, T("beat"), rgb=(250, 210, 60)))

# camera keys (t, x, y, zoom, roll). zoom ZF = that clip full screen; two equal keys = a hold
CAM = [
    (0.0, 0, 130, ZF, 0.0), (6.2, 0, 130, ZF, 0.0),                       # scene 1 footage, full screen
    (7.5, 250, 150, 0.8, 0.3),                                            # pull back: the clip becomes a print on the wall
    (T("price") + 0.4, 1350, 130, 0.85, 0.2), (T("billion") + 0.2, 1560, 110, 1.15, 0.0),
    (T("44") + 0.4, 2230, 120, 1.08, -0.3), (T("tap", 13.0) + 0.5, 1950, 140, 0.72, 0.0),
    (T("billion", 16.0) + 0.3, 1700, 300, 0.95, 0.4), (19.8, 1900, 250, 0.55, 0.0),
    (T("here", 20.0) + 0.15, 3350, 160, ZF, 0.0), (22.1, 3350, 160, ZF, 0.0),     # strange part: footage full screen
    (T("lost") + 0.5, 3350, 520, 0.72, -0.3), (T("million", 23.5) + 0.2, 3300, 740, 1.15, 0.0),
    (T("40") + 0.4, 3600, 700, 0.98, 0.5), (28.9, 3900, 400, 0.5, 0.0),
    (29.75, 5000, 120, ZF, 0.0), (T("single") - 0.1, 5000, 120, ZF, 0.0),        # runway footage full screen
    (T("runway") + 0.3, rx, ry, ZF * 1.5, 0.0), (T("neighbourhoods") + 0.3, hx + 60, hy, ZF * 1.3, 0.0),
    (34.95, 5000, 120, ZF, 0.0),
    (35.45, 6550, 60, ZF, 0.0), (37.6, 6550, 60, ZF, 0.0),                       # the buyer, full screen
    (T("yet") + 0.9, 5200, 300, 0.32, 0.0), (DUR, 3300, 400, 0.155, 0.0),        # pull back: the whole wall
]
cx_s, cy_s, z_s, r_s = (Spline([(k[0], k[i]) for k in CAM]) for i in (1, 2, 3, 4))
FOCUS_R = Spline([(k[0], 3.0 if k[3] >= ZF * 0.99 else (0.42 if k[3] > 0.6 else 0.9)) for k in CAM])


def cam(t):
    x, y, z, r = cx_s(t), cy_s(t), z_s(t), r_s(t)
    if z >= ZF * 0.97:                       # a clip is full screen: never let the view leave its footage
        vp = min((i for i in ITEMS if isinstance(i, VideoPrint)), key=lambda i: math.hypot(i.x - x, i.y - y))
        hw, hh = W / 2 / z, H / 2 / z
        x = clamp(x, vp.x - vp.w / 2 + hw, vp.x + vp.w / 2 - hw) if vp.w / 2 > hw else vp.x
        y = clamp(y, vp.y - vp.h / 2 + hh, vp.y + vp.h / 2 - hh) if vp.h / 2 > hh else vp.y
    k = clamp((ZF * 0.98 - z) / 0.3)
    x += k * 5 * math.sin(t * 0.9) / z; y += k * 4 * math.sin(t * 1.3 + 1) / z        # handheld drift
    for ts, amp in SHAKES:
        d = t - ts
        if 0 <= d < 0.35:
            x += amp * math.sin(d * 70) * (1 - d / 0.35) / z; y += amp * math.cos(d * 55) * (1 - d / 0.35) / z
    return x, y, z, r


# ------------------------------------------------------------------ render
_cache = {}


def scaled(it, key, s, rot):
    k = (id(it), key, round(s, 2), round(rot, 1))
    if k not in _cache:
        base = _cache.get((id(it), key))
        if base is None:
            base = _cache[(id(it), key)] = it.draw_sprite(key)
        im = base.resize((max(1, int(base.width * s)), max(1, int(base.height * s))), Image.BILINEAR)
        if abs(rot) > 0.05:
            im = im.rotate(-rot, resample=Image.BICUBIC, expand=True)
        if len(_cache) > 900:
            _cache.clear()
        _cache[k] = im
    return _cache[k]


GRAIN = [Image.effect_noise((W // 2, H // 2), 22).resize((W, H)).convert("L") for _ in range(4)]


def board(x, y, z):
    im = Image.new("RGB", (W, H), (24, 28, 34))
    d = ImageDraw.Draw(im)
    step = 400
    for gx in range(int((x - W / 2 / z) // step) * step, int(x + W / 2 / z) + step, step):
        sx = (gx - x) * z + W / 2
        d.line((sx, 0, sx, H), fill=(32, 37, 44), width=max(1, int(2 * z)))
    for gy in range(int((y - H / 2 / z) // step) * step, int(y + H / 2 / z) + step, step):
        sy = (gy - y) * z + H / 2
        d.line((0, sy, W, sy), fill=(32, 37, 44), width=max(1, int(2 * z)))
    return im


def frame(t):
    x, y, z, r = cam(t)
    im = board(x, y, z).convert("RGBA")
    to_s = lambda wx, wy: ((wx - x) * z + W / 2, (wy - y) * z + H / 2)
    for it in sorted(ITEMS, key=lambda i: i.z):
        if t < it.t_in:
            continue
        if isinstance(it, Line):
            pts = it.pts_fn(); u = clamp((t - it.t_in) / it.dur)
            pts = [to_s(*p) for p in pts[:max(2, int(len(pts) * ease_out(u)))]]
            if max(abs(px - W / 2) for px, _ in pts) > 4 * W:
                continue
            a = int(255 * (1 - it.dim(t)))
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
            wd = max(2, int(it.width * z))
            if it.kind == "string":
                ld.line([(px + 3, py + 5) for px, py in pts], fill=(0, 0, 0, a // 3), width=wd, joint="curve")
            ld.line(pts, fill=it.rgb + (a,), width=wd, joint="curve")
            im.alpha_composite(lay)
            continue
        key, s, alpha = it.sprite(t)
        sx, sy = to_s(it.x, it.y)
        if not (-1500 * z < sx < W + 1500 * z and -1500 * z < sy < H + 1500 * z):
            continue
        sp = scaled(it, key, s * z, getattr(it, "rot", 0.0))
        dm = it.dim(t)
        if alpha < 1 or dm > 0:
            sp = sp.copy(); a = sp.getchannel("A").point(lambda v: int(v * alpha))
            sp.putalpha(a)
            if dm > 0:
                sp = Image.alpha_composite(sp, Image.new("RGBA", sp.size, (10, 12, 16, int(255 * dm)))) if False else \
                    Image.merge("RGBA", [c.point(lambda v: int(v * (1 - dm))) for c in sp.split()[:3]] + [a])
        im.alpha_composite(sp, (int(sx - sp.width / 2), int(sy - sp.height / 2)))
    # spotlight: the centre of the frame (where the camera is looking) stays lit, the rest dims
    fr = FOCUS_R(t)
    key = round(fr, 2)
    if key not in _cache:
        m = Image.new("L", (W // 4, H // 4), 120)
        ImageDraw.Draw(m).ellipse((W / 8 - fr * W / 4, H / 8 - fr * H / 2.6, W / 8 + fr * W / 4, H / 8 + fr * H / 2.6), fill=255)
        _cache[key] = m.filter(ImageFilter.GaussianBlur(28)).resize((W, H), Image.BILINEAR)
    im = Image.composite(im, Image.new("RGBA", (W, H), (6, 8, 11, 255)), _cache[key])
    if abs(r) > 0.05:
        im = im.rotate(r, resample=Image.BICUBIC).resize((W, H))
        im = im.crop((W * 0.02, H * 0.02, W * 0.98, H * 0.98)).resize((W, H), Image.BICUBIC)
    return im.convert("RGB")


def speed(t):
    a, b = cam(t - 0.02), cam(t + 0.02)
    return math.hypot((b[0] - a[0]) * b[2], (b[1] - a[1]) * b[2]) / 0.04 + abs(math.log(b[2] / a[2])) * 2000


if __name__ == "__main__":
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                            str(WD / "mix_silent.mp4")], stdin=subprocess.PIPE)
    whoosh = []
    n = int(DUR * FPS)
    for i in range(n):
        t = i / FPS
        v = speed(t)
        if v > 1600:                                   # fast move: motion blur from sub-frames
            subs = [frame(t + (j - 1.5) / FPS / 4) for j in range(4)]
            f = subs[0]
            for j, s_ in enumerate(subs[1:], 2):
                f = Image.blend(f, s_, 1 / j)
            if not whoosh or t - whoosh[-1] > 0.8:
                whoosh.append(t)
        else:
            f = frame(t)
        g = GRAIN[(i // 2) % 4]
        f = Image.composite(f, Image.blend(f, Image.new("RGB", (W, H), (128, 128, 128)), 0.06), g)
        enc.stdin.write(f.tobytes())
        if i % 100 == 0:
            print(f"frame {i}/{n}", flush=True)
    enc.stdin.close(); enc.wait()
    cues = sorted(CUES + [(t - 0.15, "whoosh") for t in whoosh])
    (WD / "sfx_events_mix.json").write_text(json.dumps(cues))
    print("done", len(cues), "sound cues")
