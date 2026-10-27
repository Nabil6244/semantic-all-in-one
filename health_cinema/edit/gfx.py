"""Drawing primitives shared by every high-end shot: fonts, anti-aliased shapes, cached text tiles, glass panels, glow, an animated backdrop and
blurred footage plates. Pillow only (already pinned); every function is a pure function of its arguments and the time passed in."""
from __future__ import annotations
import functools, math, random
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

WHITE, SOFT, MUTED, INK = (246, 248, 252), (206, 216, 234), (146, 160, 186), (7, 11, 22)
COOL = (120, 196, 255)

_WEIGHT_IDX = {"bold": 0, "demi": 2, "medium": 5, "regular": 7, "heavy": 8, "light": 10}
_FALLBACK = {"bold": ("Helvetica.ttc", 1), "demi": ("Helvetica.ttc", 1), "medium": ("Helvetica.ttc", 0), "regular": ("Helvetica.ttc", 0), "heavy": ("Helvetica.ttc", 1), "light": ("Helvetica.ttc", 0)}

@functools.lru_cache(maxsize=256)
def font(px: int, weight: str = "demi") -> ImageFont.FreeTypeFont:
    px = max(8, int(px))
    for p in ("/System/Library/Fonts/Avenir Next.ttc",):
        if Path(p).exists():
            try: return ImageFont.truetype(p, px, index=_WEIGHT_IDX[weight])
            except Exception: pass
    for root in ("/System/Library/Fonts", "/System/Library/Fonts/Supplemental", "C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu"):
        name, idx = _FALLBACK[weight]
        for n in (name, "segoeuib.ttf" if weight in ("bold", "demi", "heavy") else "segoeui.ttf", "arialbd.ttf" if weight in ("bold", "demi", "heavy") else "arial.ttf",
                  "DejaVuSans-Bold.ttf" if weight in ("bold", "demi", "heavy") else "DejaVuSans.ttf"):
            p = Path(root) / n
            if p.exists():
                try: return ImageFont.truetype(str(p), px, index=idx) if p.suffix == ".ttc" else ImageFont.truetype(str(p), px)
                except Exception: pass
    return ImageFont.load_default()

class Units:
    """Design in 1080p units; k scales to the real frame so preview (720p) and final (1080p) compose identically."""
    def __init__(self, W: int, H: int): self.W, self.H, self.k = W, H, H / 1080.0
    def u(self, v: float) -> int: return int(round(v * self.k))
    @property
    def margin(self) -> int: return self.u(120)           # title-safe: 6.25% of width
    @property
    def safe_bottom(self) -> int: return self.H - self.u(60)

def aa(w: int, h: int, fn: Callable[[ImageDraw.ImageDraw, int], None], ss: int = 3) -> Image.Image:
    """Anti-aliased RGBA layer: fn(draw, ss) draws at ss x resolution, then a box reduce."""
    im = Image.new("RGBA", (max(1, w) * ss, max(1, h) * ss), (0, 0, 0, 0)); fn(ImageDraw.Draw(im), ss); return im.reduce(ss)

def with_alpha(tile: Image.Image, a: float) -> Image.Image:
    if a >= 0.999: return tile
    t = tile.copy(); t.putalpha(tile.getchannel("A").point([int(i * max(0.0, a)) for i in range(256)])); return t

def paste(base: Image.Image, tile: Image.Image, x: int, y: int, a: float = 1.0) -> None:
    """Straight-alpha composite of an RGBA tile onto an RGB frame, at opacity a."""
    if a <= 0.003: return
    t = with_alpha(tile, a); base.paste(t, (int(x), int(y)), t)

def fill_rect(base: Image.Image, box, color, a: float) -> None:
    if a <= 0.003: return
    x0, y0, x1, y1 = [int(v) for v in box]; x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(base.width, x1), min(base.height, y1)
    if x1 <= x0 or y1 <= y0: return
    sub = base.crop((x0, y0, x1, y1)); base.paste(Image.blend(sub, Image.new("RGB", sub.size, tuple(color)), min(1.0, a)), (x0, y0))

# ---- text -----------------------------------------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=2048)
def text_tile(text: str, px: int, weight: str, color: Tuple[int, int, int], shadow: int = 0, tracking: float = 0.0) -> Image.Image:
    f = font(px, weight); pad = int(px * 0.35) + shadow * 2
    if tracking:
        w = sum(f.getlength(c) + tracking * px for c in text)
    else: w = f.getlength(text)
    asc, desc = f.getmetrics(); W, H = int(w) + 2 * pad, asc + desc + 2 * pad
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    def draw_text(dr, fill):
        if tracking:
            x = pad
            for c in text: dr.text((x, pad), c, font=f, fill=fill); x += f.getlength(c) + tracking * px
        else: dr.text((pad, pad), text, font=f, fill=fill)
    if shadow:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); draw_text(ImageDraw.Draw(sh), (0, 0, 0, 170)); sh = sh.filter(ImageFilter.GaussianBlur(shadow)); im = Image.alpha_composite(im, sh); d = ImageDraw.Draw(im)
    draw_text(d, (*color, 255)); return im

def tile_pad(px: int, shadow: int = 0) -> int:
    """Padding text_tile() puts around its glyphs (so callers can align the glyphs, not the tile)."""
    return int(px * 0.35) + shadow * 2

def text_size(text: str, px: int, weight: str = "demi", tracking: float = 0.0) -> Tuple[int, int]:
    f = font(px, weight); asc, desc = f.getmetrics()
    return (int(sum(f.getlength(c) + tracking * px for c in text)) if tracking else int(f.getlength(text))), asc + desc

def wrap_words(words: Sequence[str], px: int, weight: str, max_w: int) -> List[List[int]]:
    """Greedy line breaking -> list of lines, each a list of word indices."""
    f = font(px, weight); sp = f.getlength(" "); lines: List[List[int]] = [[]]; cur = 0.0
    for i, w in enumerate(words):
        wl = f.getlength(w)
        if lines[-1] and cur + sp + wl > max_w: lines.append([]); cur = 0.0
        cur += (sp if lines[-1] else 0) + wl; lines[-1].append(i)
    return lines

def layout(words: Sequence[str], px: int, weight: str, max_w: int, line_gap: float = 1.18, align: str = "left") -> Tuple[List[Tuple[int, int, int]], int, int]:
    """-> ([(x, y, line_index) per word], block_w, block_h). x,y are text-origin (top-left of the glyph box without tile padding)."""
    f = font(px, weight); sp = f.getlength(" "); lines = wrap_words(words, px, weight, max_w); pos: Dict[int, Tuple[int, int, int]] = {}
    widths = [sum(f.getlength(words[i]) for i in ln) + sp * (len(ln) - 1) for ln in lines]; bw = int(max(widths) if widths else 0); lh = int(px * line_gap)
    for li, ln in enumerate(lines):
        x = {"left": 0, "center": (bw - widths[li]) / 2, "right": bw - widths[li]}[align]
        for i in ln: pos[i] = (int(x), li * lh, li); x += f.getlength(words[i]) + sp
    return [pos[i] for i in range(len(words))], bw, lh * len(lines)

# ---- shapes ---------------------------------------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=128)
def glass_panel(w: int, h: int, radius: int, accent: Tuple[int, int, int], edge: bool = True) -> Image.Image:
    """Dark translucent panel with a hairline edge, a soft top sheen and an accent tick: readable on any footage, consistent across the film."""
    pad = 24
    def fn(d, ss):
        d.rounded_rectangle([pad * ss, pad * ss, (pad + w) * ss, (pad + h) * ss], radius=radius * ss, fill=(8, 13, 26, 196))
    base = aa(w + 2 * pad, h + 2 * pad, fn)
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0)); shadow.paste((0, 0, 0, 120), (0, 0, *base.size), base.getchannel("A")); shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    out = Image.alpha_composite(shadow, base)
    if edge:
        line = aa(w + 2 * pad, h + 2 * pad, lambda d, ss: d.rounded_rectangle([pad * ss, pad * ss, (pad + w) * ss, (pad + h) * ss], radius=radius * ss, outline=(255, 255, 255, 46), width=max(1, ss)))
        out = Image.alpha_composite(out, line)
    return out

def glow(tile: Image.Image, radius: int, strength: float = 1.0) -> Image.Image:
    g = tile.filter(ImageFilter.GaussianBlur(radius)); a = g.getchannel("A").point([min(255, int(i * strength)) for i in range(256)]); g.putalpha(a); return g

@functools.lru_cache(maxsize=64)
def radial_blob(size: int, color: Tuple[int, int, int], peak: int) -> Image.Image:
    a = Image.radial_gradient("L").resize((size, size), Image.BICUBIC).point([max(0, int(peak * (1 - i / 255.0) ** 1.6)) for i in range(256)])
    im = Image.new("RGBA", (size, size), (*color, 0)); im.putalpha(a); return im

@functools.lru_cache(maxsize=16)
def vignette_mask(W: int, H: int, strength: float) -> Image.Image:
    """'L' multiply mask: 255 in the centre falling to 255*(1-strength) at the corners."""
    m = Image.radial_gradient("L").resize((W, H), Image.BICUBIC)       # 0 centre -> 255 edge
    return m.point([int(255 * (1 - strength * (max(0.0, (i / 255.0 - 0.45) / 0.55)) ** 1.5)) for i in range(256)])

def vignette(im: Image.Image, strength: float) -> Image.Image:
    if strength <= 0: return im
    m = vignette_mask(im.width, im.height, strength); return ImageChops.multiply(im, Image.merge("RGB", (m, m, m)))

# ---- backdrop and footage plate ------------------------------------------------------------------------------------------------------
class Backdrop:
    """Deep ink gradient + two slow light pools + faint grid + drifting motes. Time-driven only (no state), so any frame is reproducible."""
    def __init__(self, W: int, H: int, accent: Tuple[int, int, int], seed: int = 0):
        self.W, self.H, self.accent, self.seed = W, H, accent, seed; self.U = Units(W, H)
        g = Image.linear_gradient("L").resize((W, H), Image.BICUBIC)
        top, bot = (14, 22, 40), (4, 7, 15)
        self.base = Image.merge("RGB", tuple(g.point([int(top[c] + (bot[c] - top[c]) * i / 255.0) for i in range(256)]) for c in range(3)))
        step = self.U.u(96); grid = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(grid)
        for x in range(0, W, step): d.line([x, 0, x, H], fill=(120, 160, 220, 9), width=1)
        for y in range(0, H, step): d.line([0, y, W, y], fill=(120, 160, 220, 9), width=1)
        self.grid = grid; rnd = random.Random(seed or 7)
        self.motes = [(rnd.random(), rnd.random(), rnd.uniform(0.012, 0.034), rnd.uniform(0.2, 1.0), rnd.uniform(0, 6.28)) for _ in range(46)]
        self.blobs = [(radial_blob(self.U.u(1500), accent, 62), 0.18, 0.12, 0.31, 0.53, 0.0), (radial_blob(self.U.u(1300), COOL, 40), 0.17, 0.10, 0.23, 0.41, 2.1)]
    def frame(self, t: float, plate: Optional[Image.Image] = None, plate_alpha: float = 0.0) -> Image.Image:
        im = self.base.copy(); W, H = self.W, self.H
        if plate is not None and plate_alpha > 0: im = Image.blend(im, plate, min(1.0, plate_alpha))
        for blob, ax, ay, fx, fy, ph in self.blobs:
            cx = W * (0.5 + ax * math.sin(t * fx + ph) + 0.22 * (1 if ph == 0 else -1)); cy = H * (0.5 + ay * math.cos(t * fy + ph) - 0.12 * (1 if ph == 0 else -1))
            paste(im, blob, int(cx - blob.width / 2), int(cy - blob.height / 2), 1.0)
        im.paste(self.grid, (0, 0), self.grid)
        mote = radial_blob(self.U.u(16), WHITE, 120)
        for mx, my, sp, al, ph in self.motes:
            y = (my - t * sp) % 1.0; x = mx + 0.012 * math.sin(t * 0.6 + ph)
            paste(im, mote, int(x * W), int(y * H), al * (0.55 + 0.45 * math.sin(t * 0.9 + ph)))
        return vignette(im, 0.45)

def blur_plate(poster: Image.Image, W: int, H: int, dim: float = 0.30, tint: Tuple[int, int, int] = (10, 18, 34)) -> Image.Image:
    """Large, blurred, darkened still of a footage frame used as a quiet plate behind graphics (texture and colour continuity, never evidence)."""
    small = poster.convert("RGB").resize((max(8, W // 8), max(8, H // 8)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
    im = small.resize((W, H), Image.BICUBIC); return Image.blend(Image.new("RGB", (W, H), tint), im, dim)

def cover(im: Image.Image, W: int, H: int) -> Image.Image:
    s = max(W / im.width, H / im.height); r = im.resize((int(math.ceil(im.width * s)), int(math.ceil(im.height * s))), Image.BICUBIC)
    x, y = (r.width - W) // 2, (r.height - H) // 2; return r.crop((x, y, x + W, y + H))
