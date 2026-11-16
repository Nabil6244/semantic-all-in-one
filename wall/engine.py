"""Wall Moments engine: one dark evidence wall, a camera gliding over it, items landing on the spoken word.

Everything a wall moment shows is described by plain JSON `params` (the planner writes them, wall/probe.py and the tests read them):

    {"theme": "slate", "dur": 14.0, "work": "<frame cache dir>",
     "fade_in": 0, "fade_out": 0,                       # seconds; only when there is no clip to pull out of / dive into
     "items": [ {...}, ... ],                           # world px; at zoom 1 the frame shows 1280 x 720 world px
     "cam":   [ {"t", "x", "y", "z", "r"} | {"t", "fs": "<video id>", "edge": bool}, ... ]}

Item types (all times are seconds inside the layer; t_in < 0 = already on the wall):
    video    id x y w t_in clip{path, seek, t0, a, b, res} label label_t dim_at   footage that keeps playing inside its print
    print    id x y w rot t_in image label label_t dim_at                         a photo print
    text     text x y size t_in block type_on rgb hit dim_at                      big type, optional block behind it
    counter  x y size value t_in t_land fmt{pre, dec, suf, comma} caption bad     rolls up and lands on its number word
    stamp    text x y size rot t_in                                               slams in with a camera shake
    note     text x y size rot t_in                                               handwriting
    string   a[x,y] b[x,y] t_in dur sag                                           red string drawn from a to b
    pen      cx cy rx ry rot t_in dur                                             pen ring
    under    x0 x1 y t_in                                                         marker underline

A video print's clip time at layer time t is clip.seek + (t - clip.t0); clip.a..clip.b is the decoded window (ping-pong past it).
Camera keys with "fs" frame that video print full screen: zoom = 1280 / w * FILL (or exactly 1280 / w with "edge", the hand-off
frames into and out of the real full-screen shot, so the cut does not jump). Whenever a print fills the frame the camera is clamped
inside its footage, so a full-screen clip never shows its border.

    Wall(params).frame(t) -> RGB 1280x720           the bare frame (no grain, no blur)
    Wall(params).render(t) -> RGBA 1280x720          motion blur on fast moves, grain away from full screen, fades
    Wall(params).cues() -> [(t, sound)]              item sounds + whooshes on fast camera moves
    lay_wall(t, dur, params) -> RGBA                 the render layer (CARDS["wall.lay_wall"]), one Wall per params per thread
"""

from __future__ import annotations

import bisect
import math
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import frames as FR
from . import theme as TH

W, H, FPS = 1280, 720, 25
FILL = 1.025                 # full-screen hold inside a wall moment
EDGE = 1.0                   # first / last frame of a wall moment: the same size the real shot has
PAD = 60                     # sprite margin around a print (its shadow)
BLUR_SPEED = 1600.0          # screen px / s above which a frame gets motion blur
FONTS = Path(__file__).resolve().parents[1] / "assets" / "fonts"
BOLD, SANS, HAND = "Outfit-ExtraBold.ttf", "Inter-Bold.ttf", "ChalkboardSE.ttc"


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def ease_out(k: float) -> float:
    return 1 - (1 - k) ** 3


@lru_cache(maxsize=256)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONTS / name), max(6, int(size)))
    except OSError:
        return ImageFont.truetype(str(FONTS / SANS), max(6, int(size)))


def _measure(text: str, f: ImageFont.FreeTypeFont) -> Tuple[int, int, int, int]:
    return ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f)


def fmt_value(v: float, fmt: Dict[str, Any]) -> str:
    dec = int(fmt.get("dec", 0))
    s = f"{abs(v):,.{dec}f}" if fmt.get("comma") else f"{abs(v):.{dec}f}"
    sign = fmt.get("sign", "")
    return f"{sign}{fmt.get('pre', '')}{s}{fmt.get('suf', '')}"


# ---------------------------------------------------------------------------------------------------------------- camera

class Spline:
    """Monotone cubic (Fritsch-Carlson) through (t, v) keys: never overshoots, equal neighbours make a hold."""

    def __init__(self, keys: Sequence[Tuple[float, float]]):
        keys = sorted(keys)
        self.t = [float(k[0]) for k in keys]
        self.v = [float(k[1]) for k in keys]
        n = len(keys)
        self.m = [0.0] * n
        if n < 2:
            return
        d = [(self.v[i + 1] - self.v[i]) / max(1e-6, self.t[i + 1] - self.t[i]) for i in range(n - 1)]
        m = [0.0] * n
        m[0], m[-1] = d[0], d[-1]
        for i in range(1, n - 1):
            m[i] = 0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2
        for i in range(n - 1):
            if d[i] == 0:
                m[i] = m[i + 1] = 0.0
                continue
            a, b = m[i] / d[i], m[i + 1] / d[i]
            if a * a + b * b > 9:
                k = 3 / math.hypot(a, b)
                m[i], m[i + 1] = k * a * d[i], k * b * d[i]
        self.m = m

    def __call__(self, t: float) -> float:
        T = self.t
        if len(T) == 1 or t <= T[0]:
            return self.v[0]
        if t >= T[-1]:
            return self.v[-1]
        i = bisect.bisect_right(T, t) - 1
        h = T[i + 1] - T[i]
        u = (t - T[i]) / h
        return ((2 * u ** 3 - 3 * u ** 2 + 1) * self.v[i] + (u ** 3 - 2 * u ** 2 + u) * h * self.m[i]
                + (-2 * u ** 3 + 3 * u ** 2) * self.v[i + 1] + (u ** 3 - u ** 2) * h * self.m[i + 1])


# ---------------------------------------------------------------------------------------------------------------- items

def _paste(dst: Image.Image, src: Image.Image, x: int, y: int) -> None:
    """alpha_composite that accepts a sprite hanging over the frame's edge."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst.width, x + src.width), min(dst.height, y + src.height)
    if x1 <= x0 or y1 <= y0:
        return
    part = src if (x0 - x, y0 - y, x1 - x, y1 - y) == (0, 0, src.width, src.height) else src.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    dst.alpha_composite(part, (x0, y0))


def _alpha(im: Image.Image, k: float) -> Image.Image:
    if k >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * k)))
    return im


def _darken(im: Image.Image, k: float) -> Image.Image:
    if k <= 0.001:
        return im
    r, g, b, a = im.split()
    f = lambda v: int(v * (1 - k))
    return Image.merge("RGBA", [r.point(f), g.point(f), b.point(f), a])


class Item:
    z = 0
    sprite_item = True

    def __init__(self, d: Dict[str, Any], th: Dict[str, Any], n: int):
        self.d, self.th = d, th
        self.id = str(d.get("id") or f"i{n}")
        self.t_in = float(d.get("t_in", 0.0))
        self.dim_at = d.get("dim_at")
        self.x, self.y = float(d.get("x", 0.0)), float(d.get("y", 0.0))
        self.rot = float(d.get("rot", 0.0))

    def dim(self, t: float) -> float:
        return 0.0 if self.dim_at is None else 0.5 * clamp((t - float(self.dim_at)) / 0.6)

    def cues(self) -> List[Tuple[float, str]]:
        return []

    def shakes(self) -> List[Tuple[float, float]]:
        return []

    # sprite items: state(t) -> (key, scale, alpha); draw(key) -> RGBA at world scale, centred on (x, y)
    def state(self, t: float):
        return ("k",), 1.0, 1.0

    def draw(self, key) -> Image.Image:
        raise NotImplementedError


class Print(Item):
    """A photo print: cream border, drop shadow, red pin, drops in; optional red name bar."""

    def __init__(self, d, th, n):
        super().__init__(d, th, n)
        self.w = int(d.get("w", 900))
        self.label, self.label_t = d.get("label"), float(d.get("label_t", self.t_in + 0.6))
        self.image = d.get("image")
        self.h = int(d.get("h") or self._h())
        self.b = int(self.w * 0.035)

    def _h(self) -> int:
        try:
            with Image.open(self.image) as im:
                return int(self.w * im.height / im.width)
        except Exception:  # noqa: BLE001
            return int(self.w * 9 / 16)

    def cues(self):
        out = [] if self.t_in < 0 else [(self.t_in, "drop")]
        if self.label and self.label_t >= 0:
            out.append((self.label_t, "pop"))
        return out

    def drop(self, t: float) -> Tuple[float, float]:
        k = clamp((t - self.t_in) / 0.5)
        return 1.0 + 0.25 * (1 - ease_out(k)), clamp(k * 2.5)

    def card(self) -> Image.Image:
        """Border + shadow + pin (the footage / photo area is left plain card)."""
        w, h, b = self.w, int(round(self.h)), self.b
        cw, ch = w + 2 * b, h + 2 * b + int(b * 0.6)
        im = Image.new("RGBA", (cw + 2 * PAD, ch + 2 * PAD), (0, 0, 0, 0))
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle((PAD + 14, PAD + 22, PAD + cw + 14, PAD + ch + 22), fill=self.th["shadow"])
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(22)))
        d = ImageDraw.Draw(im)
        d.rectangle((PAD, PAD, PAD + cw, PAD + ch), fill=self.th["card"] + (255,))
        px, py, r = im.width // 2, PAD + b // 2, 16
        d.ellipse((px - r, py - r, px + r, py + r), fill=self.th["pin"], outline=self.th["pin_rim"], width=3)
        return im

    def centre_offset(self) -> Tuple[float, float]:
        """Sprite centre minus picture centre (world px at scale 1): the card's bottom lip is deeper than its top."""
        h = int(round(self.h))
        cw, ch = self.w + 2 * self.b, h + 2 * self.b + int(self.b * 0.6)
        return (cw / 2 - (self.b + self.w / 2), ch / 2 - (self.b + h / 2))

    def label_sprite(self, k: float, size: int) -> Image.Image:
        f = font(BOLD, size)
        tw = _measure(self.label, f)[2] + size
        bh = int(size * 1.55)
        im = Image.new("RGBA", (int(tw) + 2, bh), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, int(tw * k), bh), fill=self.th["bar"] + (255,))
        if k > 0.6:
            d.text((size // 2, int(size * 0.15)), self.label, font=f, fill=self.th["bar_text"])
        return im

    def state(self, t):
        s, a = self.drop(t)
        lab = 0.0 if not self.label else clamp((t - self.label_t) / 0.35)
        return ("print", round(lab * 12)), s, a

    def draw(self, key):
        im = self.card()
        try:
            ph = Image.open(self.image).convert("RGB").resize((self.w, self.h), Image.LANCZOS)
            im.paste(ph, (PAD + self.b, PAD + self.b))
        except Exception:  # noqa: BLE001
            pass
        lab = key[1] / 12
        if self.label and lab > 0:
            ls = self.label_sprite(lab, 46)
            _paste(im, ls, PAD + self.b, PAD + self.b + self.h - 92)
        return im

    def on(self, fx: float, fy: float) -> Tuple[float, float]:
        dx, dy = (fx - 0.5) * self.w, (fy - 0.5) * self.h
        a = math.radians(self.rot)
        return self.x + dx * math.cos(a) - dy * math.sin(a), self.y + dx * math.sin(a) + dy * math.cos(a)


class VideoPrint(Print):
    """A print whose picture is moving footage. Drawn straight from the decoded frame at screen size (sharp at full screen)."""

    def __init__(self, d, th, n):
        d = dict(d, rot=0.0)
        super().__init__(d, th, n)
        self.h = self.w * 9 / 16                     # exact: the full-screen view is exactly this tall at the hand-off zoom
        c = d.get("clip") or {}
        self.path = c.get("path")
        self.seek, self.t0 = float(c.get("seek", 0.0)), float(c.get("t0", 0.0))
        self.a, self.b_t = float(c.get("a", self.seek)), float(c.get("b", self.seek + 6.0))
        self.res = tuple(c.get("res") or (1280, 720))
        self.graph = str(c.get("graph") or "")      # a style's own decode of the shot (War: its grade, fill and hand-off zoom)
        self.work = d.get("_work")
        self._frames: Optional[FR.Frames] = None

    def draw(self, key):
        return self.card()                  # the footage itself is drawn straight onto the frame (Wall._video)

    def frames(self) -> Optional[FR.Frames]:
        if self._frames is None and self.path:
            self._frames = FR.window(self.path, self.a, self.b_t, self.res, self.work, self.graph)
        return self._frames

    def clip_time(self, t: float) -> float:
        return self.seek + (t - self.t0)

    def frame_at(self, t: float) -> Optional[Image.Image]:
        fr = self.frames()
        return fr.at(self.clip_time(t)) if fr is not None else None


class Text(Item):
    """Big condensed type; optional block behind it; types on letter by letter."""

    def __init__(self, d, th, n):
        super().__init__(d, th, n)
        self.text, self.size = str(d.get("text", "")), int(d.get("size", 54))
        self.block = tuple(d["block"]) if d.get("block") else None
        self.type_on = float(d.get("type_on", 0.0))
        self.rgb = tuple(d["rgb"]) if d.get("rgb") else (th["block_text"] if self.block == tuple(th["block"]) else th["ink"])
        self.hit = d.get("hit") or "impact"

    def cues(self):
        return [] if self.t_in < 0 else [(self.t_in, "type" if self.type_on else self.hit)]

    def shakes(self):
        return [(self.t_in, 10.0)] if self.hit == "boom" and self.t_in >= 0 else []

    def state(self, t):
        n = len(self.text) if not self.type_on else int(len(self.text) * clamp((t - self.t_in) / self.type_on))
        k = clamp((t - self.t_in) / 0.3)
        return ("text", n), (1.0 if self.type_on else 1.0 + 0.4 * (1 - ease_out(k))), (1.0 if self.type_on else k)

    def draw(self, key):
        f = font(BOLD, self.size)
        bb = _measure(self.text, f)
        w, h = bb[2] + 80, int(self.size * 1.35) + 40
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if self.block:
            d.rectangle((10, 14, w - 10, h - 14), fill=self.block)
        else:
            d.text((44, 26), self.text[:key[1]], font=f, fill=self.th["ink_shadow"])
        d.text((40, 20), self.text[:key[1]], font=f, fill=self.rgb)
        return im


class Counter(Item):
    """A number rolling up to its value, landing on the spoken number word, with a caption under it."""

    def __init__(self, d, th, n):
        super().__init__(d, th, n)
        self.size, self.value = int(d.get("size", 120)), float(d.get("value", 0.0))
        self.t_land = float(d.get("t_land", self.t_in + 1.0))
        self.fmt = dict(d.get("fmt") or {})
        self.caption = str(d.get("caption", "")).upper()
        self.rgb = th["bad"] if d.get("bad") else th["ink"]

    def cues(self):
        if self.t_in < 0:
            return []
        return [(self.t_in, "ticks:%.2f" % max(0.2, self.t_land - self.t_in)), (self.t_land, "impact")]

    def shakes(self):
        return [] if self.t_in < 0 else [(self.t_land, 7.0)]

    def state(self, t):
        k = clamp((t - self.t_in) / max(0.2, self.t_land - self.t_in))
        pulse = 0.12 * math.sin(math.pi * clamp((t - self.t_land) / 0.25)) if t >= self.t_land else 0.0
        return ("ctr", round(ease_out(k) * 40)), 1.0 + pulse, clamp(k * 4)

    def text_at(self, step: int) -> str:
        return fmt_value(self.value * step / 40, self.fmt)

    def draw(self, key):
        s = self.text_at(key[1])
        f, fc = font(BOLD, self.size), font(SANS, int(self.size * 0.24))
        im = Image.new("RGBA", (int(self.size * 5.6), int(self.size * 1.7)), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        cx = im.width / 2
        d.text((cx + 4, 6), s, font=f, fill=self.th["ink_shadow"], anchor="mt")
        d.text((cx, 0), s, font=f, fill=self.rgb, anchor="mt")
        if self.caption:
            d.text((cx, self.size * 1.18), self.caption, font=fc, fill=self.th["caption"], anchor="mt")
        return im


def _speckle(w: int, h: int, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    a = (rng.random((h, w)) > 0.22).astype(np.uint8) * 255
    return Image.fromarray(a, "L")


class Stamp(Item):
    def __init__(self, d, th, n):
        super().__init__(d, th, n)
        self.text, self.size = str(d.get("text", "")).upper(), int(d.get("size", 64))

    def cues(self):
        return [] if self.t_in < 0 else [(self.t_in, "stamp")]

    def shakes(self):
        return [] if self.t_in < 0 else [(self.t_in, 14.0)]

    def state(self, t):
        k = clamp((t - self.t_in) / 0.18)
        return ("stamp",), 1.0 + 1.2 * (1 - k) ** 2, clamp(k * 3) * 0.92

    def draw(self, key):
        f = font(BOLD, self.size)
        tw = _measure(self.text, f)[2]
        w, h = int(tw + self.size), int(self.size * 1.6)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        col = tuple(self.th["stamp"])
        d.rectangle((8, 8, w - 8, h - 8), outline=col, width=max(4, self.size // 9))
        d.text((w / 2, h / 2), self.text, font=f, fill=col, anchor="mm")
        seed = sum(map(ord, self.text)) + 7
        from PIL import ImageChops
        im.putalpha(ImageChops.multiply(im.getchannel("A"), _speckle(w, h, seed)))
        return im


class Note(Item):
    """Handwritten note, written out over 0.7 s."""

    def __init__(self, d, th, n):
        super().__init__(d, th, n)
        self.text, self.size = str(d.get("text", "")), int(d.get("size", 40))

    def cues(self):
        return [] if self.t_in < 0 else [(self.t_in, "pencil")]

    def state(self, t):
        return ("note", int(len(self.text) * clamp((t - self.t_in) / 0.7))), 1.0, 1.0

    def draw(self, key):
        f = font(HAND, self.size)
        tw = _measure(self.text, f)[2]
        im = Image.new("RGBA", (int(tw + 40), int(self.size * 1.6)), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((20, 6), self.text[:key[1]], font=f, fill=self.th["note"])
        return im


class Line(Item):
    """String, pen ring or underline: drawn in screen space over the sprites."""
    z = 5
    sprite_item = False
    SOUND = {"string": "slide", "pen": "marker", "under": "marker"}

    def __init__(self, d, th, n):
        super().__init__(d, th, n)
        self.kind = d["type"]
        self.dur = float(d.get("dur", {"string": 0.9, "pen": 0.55, "under": 0.4}[self.kind]))
        self.width = float(d.get("width", {"string": 9, "pen": 10, "under": 12}[self.kind]))
        self.rgb = {"string": th["string"], "pen": th["pen"], "under": th["under"]}[self.kind]
        self.pts = self._points(d)

    def cues(self):
        return [] if self.t_in < 0 else [(self.t_in, self.SOUND[self.kind])]

    @staticmethod
    def _points(d) -> List[Tuple[float, float]]:
        k = d["type"]
        if k == "string":
            (x0, y0), (x1, y1) = d["a"], d["b"]
            sag = float(d.get("sag", 0.06))
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2 + sag * math.hypot(x1 - x0, y1 - y0)
            return [((1 - u) ** 2 * x0 + 2 * (1 - u) * u * mx + u * u * x1, (1 - u) ** 2 * y0 + 2 * (1 - u) * u * my + u * u * y1)
                    for u in [i / 40 for i in range(41)]]
        if k == "pen":
            cx, cy, rx, ry = (float(d[q]) for q in ("cx", "cy", "rx", "ry"))
            a0 = math.radians(float(d.get("rot", -6)))
            out = []
            for i in range(57):
                u = i / 48 * 2 * math.pi + 0.4
                r = 1 + 0.06 * math.sin(u * 3)
                x, y = rx * r * math.cos(u), ry * r * math.sin(u)
                out.append((cx + x * math.cos(a0) - y * math.sin(a0), cy + x * math.sin(a0) + y * math.cos(a0)))
            return out
        x0, x1, y = float(d["x0"]), float(d["x1"]), float(d["y"])
        return [(x0 + (x1 - x0) * i / 20, y + 6 * math.sin(i / 3)) for i in range(21)]


TYPES = {"video": VideoPrint, "print": Print, "text": Text, "counter": Counter, "stamp": Stamp, "note": Note,
         "string": Line, "pen": Line, "under": Line}


# ---------------------------------------------------------------------------------------------------------------- the wall

class Wall:
    def __init__(self, params: Dict[str, Any]):
        p = params
        self.p = p
        self.th = TH.get(p.get("theme"))
        self.dur = float(p.get("dur", 10.0))
        self.fade_in, self.fade_out = float(p.get("fade_in", 0.0)), float(p.get("fade_out", 0.0))
        self.items: List[Item] = []
        for n, d in enumerate(p.get("items", [])):
            cls = TYPES.get(d.get("type"))
            if cls is None:
                continue
            if cls is VideoPrint:
                d = dict(d, _work=p.get("work"))
            self.items.append(cls(d, self.th, n))
        self.order = sorted(self.items, key=lambda i: i.z)
        self.videos = [i for i in self.items if isinstance(i, VideoPrint)]
        self.by_id = {i.id: i for i in self.items}
        self.keys = self._keys(p.get("cam") or [{"t": 0, "x": 0, "y": 0, "z": 1}])
        self.sx, self.sy, self.sz, self.sr = (Spline([(k[0], k[i]) for k in self.keys]) for i in (1, 2, 3, 4))
        self.focus = Spline([(k[0], k[5]) for k in self.keys])
        self.shakes = sorted(s for i in self.items for s in i.shakes())
        self._sprites: Dict[Any, Image.Image] = {}
        self._spot: Dict[float, Image.Image] = {}

    # camera -------------------------------------------------------------------------------------------------------------
    def fill_zoom(self, v: VideoPrint, edge: bool = False) -> float:
        return W / v.w * (EDGE if edge else FILL)

    def _keys(self, cam: Sequence[Dict[str, Any]]) -> List[Tuple[float, float, float, float, float, float]]:
        out = []
        for k in cam:
            t = float(k["t"])
            if k.get("fs") and k["fs"] in self.by_id:
                v = self.by_id[k["fs"]]
                out.append((t, v.x, v.y, self.fill_zoom(v, bool(k.get("edge"))), 0.0, 3.0))
            else:
                z = float(k.get("z", 1.0))
                out.append((t, float(k.get("x", 0.0)), float(k.get("y", 0.0)), z, float(k.get("r", 0.0)), 0.42 if z > 0.6 else 0.9))
        out.sort(key=lambda q: q[0])
        clean = []
        for q in out:                                  # two keys at the same moment: the later one wins
            if clean and abs(clean[-1][0] - q[0]) < 1e-4:
                clean[-1] = q
            else:
                clean.append(q)
        return clean

    def nearest_video(self, x: float, y: float) -> Optional[VideoPrint]:
        if not self.videos:
            return None
        return min(self.videos, key=lambda v: math.hypot(v.x - x, v.y - y))

    def cam(self, t: float) -> Tuple[float, float, float, float]:
        x, y, z, r = self.sx(t), self.sy(t), self.sz(t), self.sr(t)
        v = self.nearest_video(x, y)
        fz = self.fill_zoom(v, True) if v is not None else 1e9
        wild = clamp((fz * 0.98 - z) / 0.3)            # 0 at full screen: no drift, no shake, no roll there
        x += wild * 5 * math.sin(t * 0.9) / z
        y += wild * 4 * math.sin(t * 1.3 + 1) / z
        for ts, amp in self.shakes:
            dt = t - ts
            if 0 <= dt < 0.35:
                x += amp * math.sin(dt * 70) * (1 - dt / 0.35) / z
                y += amp * math.cos(dt * 55) * (1 - dt / 0.35) / z
        if v is not None and z >= fz * 0.97:           # a clip (nearly) fills the frame: never let the view leave its footage
            hw, hh = W / 2 / z, H / 2 / z
            x = clamp(x, v.x - v.w / 2 + hw, v.x + v.w / 2 - hw) if v.w / 2 > hw else v.x
            y = clamp(y, v.y - v.h / 2 + hh, v.y + v.h / 2 - hh) if v.h / 2 > hh else v.y
            r = 0.0
        return x, y, z, r * wild

    def speed(self, t: float) -> float:
        a, b = self.cam(t - 0.02), self.cam(t + 0.02)
        return math.hypot((b[0] - a[0]) * b[2], (b[1] - a[1]) * b[2]) / 0.04 + abs(math.log(b[2] / a[2])) * 2000

    # drawing ------------------------------------------------------------------------------------------------------------
    def _board(self, x: float, y: float, z: float) -> Image.Image:
        im = Image.new("RGBA", (W, H), self.th["board"] + (255,))
        d = ImageDraw.Draw(im)
        step, lw = 400, max(1, int(2 * z))
        for gx in range(int((x - W / 2 / z) // step) * step, int(x + W / 2 / z) + step, step):
            sx = (gx - x) * z + W / 2
            d.line((sx, 0, sx, H), fill=self.th["grid"], width=lw)
        for gy in range(int((y - H / 2 / z) // step) * step, int(y + H / 2 / z) + step, step):
            sy = (gy - y) * z + H / 2
            d.line((0, sy, W, sy), fill=self.th["grid"], width=lw)
        return im

    def _sprite(self, it: Item, key, s: float, dim: float) -> Image.Image:
        k = (it.id, key, round(s, 3), round(dim, 1))
        sp = self._sprites.get(k)
        if sp is None:
            base = self._sprites.get((it.id, key))
            if base is None:
                base = self._sprites[(it.id, key)] = it.draw(key)
            sp = base.resize((max(1, int(base.width * s)), max(1, int(base.height * s))), Image.BILINEAR)
            if abs(it.rot) > 0.05:
                sp = sp.rotate(-it.rot, resample=Image.BICUBIC, expand=True)
            sp = _darken(sp, round(dim, 1))
            if len(self._sprites) > 600:
                self._sprites.clear()
            self._sprites[k] = sp
        return sp

    def _video(self, im: Image.Image, v: VideoPrint, t: float, x: float, y: float, z: float) -> None:
        s, alpha = v.drop(t)
        zs = z * s
        dm = v.dim(t)
        cxs, cys = (v.x - x) * z + W / 2, (v.y - y) * z + H / 2          # footage centre on screen
        l, tp = cxs - v.w / 2 * zs, cys - v.h / 2 * zs
        r, bt = cxs + v.w / 2 * zs, cys + v.h / 2 * zs
        if r < -200 or l > W + 200 or bt < -200 or tp > H + 200:
            return
        covers = l <= 2.5 and tp <= 2.5 and r >= W - 2.5 and bt >= H - 2.5
        layer = im if alpha >= 0.999 else Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if not covers:                                                   # the print's border, shadow and pin
            card = self._sprite(v, ("card",), zs, dm)
            ox, oy = v.centre_offset()
            _paste(layer, card, int(round(cxs + ox * zs - card.width / 2)), int(round(cys + oy * zs - card.height / 2)))
        if covers and abs(l) < 2.5 and abs(tp) < 2.5 and abs(r - W) < 2.5 and abs(bt - H) < 2.5:
            l, tp, r, bt = 0.0, 0.0, float(W), float(H)                  # exactly full screen: the hand-off frame
        vl, vt, vr, vb = max(0.0, l), max(0.0, tp), min(float(W), r), min(float(H), bt)
        fr = v.frame_at(t)
        if vr - vl >= 1 and vb - vt >= 1:
            ox0, oy0, ox1, oy1 = int(round(vl)), int(round(vt)), int(round(vr)), int(round(vb))
            if fr is not None:
                fw, fh = fr.size
                box = ((vl - l) / (r - l) * fw, (vt - tp) / (bt - tp) * fh, (vr - l) / (r - l) * fw, (vb - tp) / (bt - tp) * fh)
                pic = fr.resize((max(1, ox1 - ox0), max(1, oy1 - oy0)), Image.BILINEAR, box=box)
                if dm > 0.001:
                    pic = Image.blend(pic, Image.new("RGB", pic.size, (0, 0, 0)), dm)
                layer.paste(pic.convert("RGBA"), (ox0, oy0))
            else:
                ImageDraw.Draw(layer).rectangle((ox0, oy0, ox1, oy1), fill=(10, 10, 12, 255))
        if v.label:
            lab = clamp((t - v.label_t) / 0.35)
            fade = 1.0 - clamp(((r - l) / W - 0.72) / 0.2)               # the name bar leaves before the print fills the frame
            if lab > 0 and fade > 0:
                size = max(6, int(34 * zs))
                ls = _darken(_alpha(v.label_sprite(lab, size), fade), dm)
                _paste(layer, ls, int(l + 30 * zs), int(bt - 110 * zs))
        if layer is not im:
            im.alpha_composite(_alpha(layer, alpha))

    def _lines(self, im: Image.Image, t: float, x: float, y: float, z: float) -> None:
        lay, draw = None, None
        for it in self.order:
            if not isinstance(it, Line) or t < it.t_in:
                continue
            u = 1.0 if it.t_in < 0 else clamp((t - it.t_in) / it.dur)
            pts = [((px - x) * z + W / 2, (py - y) * z + H / 2) for px, py in it.pts[:max(2, int(len(it.pts) * ease_out(u)))]]
            if all(px < -50 or px > W + 50 for px, _ in pts) or all(py < -50 or py > H + 50 for _, py in pts):
                continue
            if lay is None:
                lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                draw = ImageDraw.Draw(lay)
            a = int(255 * (1 - it.dim(t)))
            wd = max(2, int(it.width * z))
            if it.kind == "string":
                draw.line([(px + 3, py + 5) for px, py in pts], fill=(0, 0, 0, a // 3), width=wd, joint="curve")
            draw.line(pts, fill=tuple(it.rgb) + (a,), width=wd, joint="curve")
        if lay is not None:
            im.alpha_composite(lay)

    def _spotlight(self, im: Image.Image, t: float) -> Image.Image:
        fr = round(self.focus(t), 2)
        if fr >= 2.5:
            return im
        m = self._spot.get(fr)
        if m is None:
            q = Image.new("L", (W // 4, H // 4), 120)
            ImageDraw.Draw(q).ellipse((W / 8 - fr * W / 4, H / 8 - fr * H / 2.6, W / 8 + fr * W / 4, H / 8 + fr * H / 2.6), fill=255)
            m = self._spot[fr] = q.filter(ImageFilter.GaussianBlur(28)).resize((W, H), Image.BILINEAR)
        return Image.composite(im, Image.new("RGBA", (W, H), self.th["spot"] + (255,)), m)

    def frame(self, t: float) -> Image.Image:
        x, y, z, r = self.cam(t)
        im = self._board(x, y, z)
        for it in self.order:
            if t < it.t_in or isinstance(it, Line):
                continue
            if isinstance(it, VideoPrint):
                self._video(im, it, t, x, y, z)
                continue
            key, s, alpha = it.state(t)
            sx, sy = (it.x - x) * z + W / 2, (it.y - y) * z + H / 2
            if not (-1500 * z < sx < W + 1500 * z and -1500 * z < sy < H + 1500 * z):
                continue
            sp = _alpha(self._sprite(it, key, s * z, it.dim(t)), alpha)
            if isinstance(it, Print):
                ox, oy = it.centre_offset()
                a = math.radians(it.rot)
                sx += (ox * math.cos(a) - oy * math.sin(a)) * s * z
                sy += (ox * math.sin(a) + oy * math.cos(a)) * s * z
            _paste(im, sp, int(sx - sp.width / 2), int(sy - sp.height / 2))
        self._lines(im, t, x, y, z)
        im = self._spotlight(im, t)
        if abs(r) > 0.05:
            im = im.rotate(r, resample=Image.BICUBIC)
            im = im.crop((W * 0.02, H * 0.02, W * 0.98, H * 0.98)).resize((W, H), Image.BICUBIC)
        return im.convert("RGB")

    def wildness(self, t: float) -> float:
        x, y, z, _r = self.cam(t)
        v = self.nearest_video(x, y)
        return 1.0 if v is None else clamp((self.fill_zoom(v, True) * 0.98 - z) / 0.3)

    def render(self, t: float) -> Image.Image:
        if self.speed(t) > BLUR_SPEED:                                   # fast move: three sub-frames blended
            subs = [self.frame(t + o / FPS) for o in (-0.25, 0.0, 0.25)]
            f = Image.blend(Image.blend(subs[0], subs[1], 0.5), subs[2], 1 / 3)
        else:
            f = self.frame(t)
        g = self.th["grain"] * self.wildness(t)
        if g > 0.002:
            f = Image.composite(f, Image.blend(f, Image.new("RGB", (W, H), (128, 128, 128)), g), _grain(int(t * FPS) // 2 % 4))
        out = f.convert("RGBA")
        k = 1.0
        if self.fade_in > 0:
            k = min(k, clamp(t / self.fade_in))
        if self.fade_out > 0:
            k = min(k, clamp((self.dur - t) / self.fade_out))
        return _alpha(out, k)

    def cues(self) -> List[Tuple[float, str]]:
        out = [c for it in self.items for c in it.cues() if 0 <= c[0] <= self.dur]
        last = -9.0
        t = 0.0
        while t < self.dur:
            if self.speed(t) > BLUR_SPEED and t - last > 0.8:
                out.append((max(0.0, t - 0.15), "whoosh"))
                last = t
            t += 0.04
        return sorted(out)


@lru_cache(maxsize=4)
def _grain(i: int) -> Image.Image:
    rng = np.random.default_rng(1000 + i)
    a = np.clip(rng.normal(128, 22, (H // 2, W // 2)), 0, 255).astype(np.uint8)
    return Image.fromarray(a, "L").resize((W, H))


# ---------------------------------------------------------------------------------------------------------------- the layer

_LOCAL = threading.local()


def wall_for(params: Dict[str, Any]) -> Wall:
    """One Wall per params dict per render thread (sprite caches are not shared between threads)."""
    cache = getattr(_LOCAL, "walls", None)
    if cache is None:
        cache = _LOCAL.walls = {}
    hit = cache.get(id(params))
    if hit is not None and hit[0] is params:
        return hit[1]
    if len(cache) >= 3:
        cache.clear()
    w = Wall(params)
    cache[id(params)] = (params, w)
    return w


def lay_wall(t: float, dur: float, params: Dict[str, Any]) -> Optional[Image.Image]:
    if t < 0 or t > dur:
        return None
    return wall_for(params).render(t)


CARDS = {"wall.lay_wall": lay_wall}
