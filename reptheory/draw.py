"""Frame drawing for Rep Theory: the near-black canvas and every animated element (section tag, callout column, equation lockup, ring highlight, anatomy glow, tier board).
All sizes are laid out for 1920x1080 and scaled by `S = W / 1920`, so Preview (1280x720) is the same picture."""
from __future__ import annotations
import functools
import math
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from . import library as L, theme as T

def _lerp(a, b, t): return a + (b - a) * t

class Ctx:
    """Per-render drawing context: size, scale, caches of fonts, backdrop and cut-out art."""
    def __init__(self, W: int, H: int):
        self.W, self.H, self.S = W, H, W / 1920.0; self._fonts = {}; self._art = {}; self._back = None
    def font(self, name, px):
        k = (name, int(px * self.S))
        if k not in self._fonts: self._fonts[k] = T.font(name, int(px * self.S))
        return self._fonts[k]
    def px(self, v): return int(round(v * self.S))
    def backdrop(self) -> Image.Image:
        if self._back is None:      # vertical gradient + soft vignette + a faint warm glow behind the subject: restrained depth, no texture that could crawl
            import numpy as np
            W, H = self.W, self.H; y = np.linspace(0, 1, H)[:, None, None]; top, bot = np.array(T.BG_TOP), np.array(T.BG_BOT); base = top + (bot - top) * y; base = np.repeat(base, W, axis=1)
            xx, yy = np.meshgrid(np.linspace(-1, 1, W), np.linspace(-1, 1, H)); r = np.sqrt((xx * 0.9) ** 2 + yy ** 2); vig = np.clip(1.0 - 0.38 * r ** 2, 0.55, 1.0)[..., None]
            gx, gy = (xx + 0.42) / 0.7, (yy + 0.05) / 0.8; glow = np.exp(-(gx ** 2 + gy ** 2) * 2.2)[..., None] * np.array([26, 11, 3])[None, None, :]
            rng = np.random.default_rng(7); grain = rng.normal(0, 1.1, (H, W, 1))     # fixed grain: identical every frame, so it never shimmers
            self._back = Image.fromarray(np.clip(base * vig + glow + grain, 0, 255).astype("uint8"), "RGB")
        return self._back.copy()
    def file_art(self, path: str) -> Optional[Image.Image]:
        """A user-supplied picture (the end card's product image), RGBA, cached; None when it cannot be read."""
        k = ("file", path)
        if k not in self._art:
            try: self._art[k] = Image.open(path).convert("RGBA")
            except Exception: self._art[k] = None
        return self._art[k]
    def art(self, ref: str) -> Image.Image:
        if ref not in self._art: self._art[ref] = L.cutout(ref)
        return self._art[ref]

def paste_art(cv: Image.Image, ctx: Ctx, ref: str, cx: float, cy: float, height: float, scale: float = 1.0, alpha: float = 1.0, dx: float = 0, dy: float = 0, fade_top: float = 0.0, rot: float = 0.0, shear: float = 0.0) -> Tuple[int, int, int, int]:
    """Centre a cut-out picture at (cx, cy) fractions of the canvas, `height` fraction of canvas height tall (x scale). Returns its box (x0, y0, x1, y1)."""
    im = ctx.art(ref); h = max(2, int(ctx.H * height * scale)); w = max(2, int(im.width * h / im.height))
    if w > ctx.W * 0.9: w = int(ctx.W * 0.9); h = int(im.height * w / im.width)
    r = im.resize((w, h), Image.BICUBIC)
    if alpha < 1: a = r.getchannel("A").point(lambda v: int(v * alpha)); r.putalpha(a)
    if fade_top > 0:      # a picture that runs off its top edge (arms, limbs) fades out instead of ending in a hard line
        import numpy as np
        ramp = np.clip(np.arange(h)[:, None] / max(1.0, h * fade_top), 0, 1) * np.ones((1, w)); a = np.asarray(r.getchannel("A")).astype("float32") * ramp; r.putalpha(Image.fromarray(a.astype("uint8")))
    x0, y0 = int(cx * ctx.W - w / 2 + dx * ctx.S), int(cy * ctx.H - h / 2 + dy * ctx.S)
    if shear:      # the top edge stays put and the body swings under it: a hang, not a slide
        pad = int(abs(shear) + 2); r = r.transform((w + 2 * pad, h), Image.AFFINE, (1, -shear / h, -pad, 0, 1, 0), resample=Image.BILINEAR); x0 -= pad
    if rot: r = r.rotate(rot, resample=Image.BILINEAR, expand=True, center=(r.width / 2, r.height)); x0 -= (r.width - w) // 2; y0 -= r.height - h      # sways about its base
    cv.paste(r, (x0, y0), r); return (x0, y0, x0 + r.width, y0 + r.height)

def ghost_word(cv: Image.Image, ctx: Ctx, word: str, t: float, alpha: int = 6):
    """The topic as huge, nearly invisible type behind the picture: fills the frame and drifts slowly the other way from the camera, so a plain backdrop is never a static one."""
    if not word: return
    key = ("ghost", word, alpha)
    if key not in ctx._art:      # rasterised once per render, then only moved
        layer = Image.new("RGBA", (int(ctx.W * 1.4), ctx.H), (0, 0, 0, 0)); d = ImageDraw.Draw(layer); f = ctx.font(T.HEAD_FONT, 560); w = _text_w(d, word, f, 0)
        d.text(((layer.width - w) / 2, ctx.H * 0.50 - ctx.px(330)), word, font=f, fill=T.WHITE + (alpha,)); ctx._art[key] = layer
    layer = ctx._art[key]; x = int(ctx.W * 0.66 - layer.width / 2 + (-40 + 6 * t) * ctx.S * -1); cv.paste(layer, (x, 0), layer)

def floor_line(cv: Image.Image, ctx: Ctx, x0: float, x1: float, y: float, p: float):
    """A thin orange floor line that draws on under the trainee's feet and fades at both ends."""
    if p <= 0: return
    import numpy as np
    w = int(x1 - x0); 
    if w <= 4: return
    a = np.clip(np.sin(np.linspace(0, np.pi, w)) * 1.5, 0, 1) * 200 * T.ease_out(p); wd = int(w * T.ease_out(p)); strip = Image.new("RGBA", (w, max(2, ctx.px(3))), T.ORANGE + (0,))
    arr = np.zeros((strip.height, w, 4), "uint8"); arr[..., 0], arr[..., 1], arr[..., 2] = T.ORANGE; arr[..., 3] = a[None, :].astype("uint8"); arr[:, wd:, 3] = 0
    strip = Image.fromarray(arr, "RGBA"); cv.paste(strip, (int(x0), int(y)), strip)

def hold_figure(cv: Image.Image, ctx: Ctx, fig_ref: str, prop_ref: str, cx: float, cy: float, height: float, t: float, squeezes=(), flip_p: float = 0.0, zoom: float = 1.0, dx: float = 0, dy: float = 0):
    """The trainee gripping the bottle by its neck, built from the two existing pictures: the bottle hangs from the trainee's right hand (it swings a little about the neck, and is squeezed
    narrower for a moment at each 'pinch/squeeze'), the hand is drawn over the neck so the fingers wrap it, and a switch of hands mirrors the whole picture with a quick squash.
    Returns (figure box, neck point on the canvas, forearm point on the canvas)."""
    import math
    fig, bot = ctx.art(fig_ref), ctx.art(prop_ref); Hf = int(ctx.H * height * zoom); Wf = int(fig.width * Hf / fig.height); pad = int(Hf * 0.30)
    fr = fig.resize((Wf, Hf), Image.BICUBIC); layer = Image.new("RGBA", (Wf + 2 * pad, Hf), (0, 0, 0, 0)); fx = pad
    hb = int(Hf * 0.27); wb = max(2, int(bot.width * hb / bot.height)); px_, py_ = fx + int(Wf * 0.955), int(Hf * 0.585)      # neck pivot: just outside the right hand
    sq = max([max(0.0, 1 - abs(t - s - 0.18) / 0.45) for s in squeezes] or [0.0]); bw = max(2, int(wb * (1 - 0.10 * sq)))
    b = bot.resize((bw, hb), Image.BICUBIC); m_ = int(hb * 0.5); spr = Image.new("RGBA", (bw + 2 * m_, hb + 2 * m_), (0, 0, 0, 0)); spr.paste(b, (m_, m_ - int(hb * 0.03)), b)
    spr = spr.rotate(3.2 * math.sin(t * 2.3), resample=Image.BILINEAR, center=(spr.width / 2, m_)); layer.alpha_composite(spr, (px_ - spr.width // 2, py_ - m_))      # swings about the neck; only the small sprite is rotated
    layer.paste(fr, (fx, 0), fr)
    hx0, hx1, hy0, hy1 = int(Wf * 0.78), Wf, int(Hf * 0.50), int(Hf * 0.62); hand = fr.crop((hx0, hy0, hx1, hy1)); hand2 = Image.new("RGBA", layer.size, (0, 0, 0, 0)); hand2.paste(hand, (fx + hx0, hy0), hand); layer.alpha_composite(hand2)      # fingers over the neck
    L0 = layer.width; neck, fore = (px_, py_), (fx + int(Wf * 0.90), int(Hf * 0.42)); f = T.ease_in_out(flip_p); flipped = f >= 0.5; k = 1.0
    if f > 0:      # a switch of hands: the picture squashes through its edge and comes out mirrored
        k = max(0.04, abs(math.cos(math.pi * f))); layer = (layer.transpose(Image.FLIP_LEFT_RIGHT) if flipped else layer).resize((max(2, int(L0 * k)), Hf), Image.BICUBIC)
    m = lambda x: ((L0 - x) if flipped else x) * k
    x0, y0 = int(cx * ctx.W - layer.width / 2 + dx * ctx.S), int(cy * ctx.H - Hf / 2 + dy * ctx.S); cv.paste(layer, (x0, y0), layer)
    xa, xb = sorted((m(fx), m(fx + Wf)))
    return (x0 + xa, y0, x0 + xb, y0 + Hf), (x0 + m(neck[0]), y0 + neck[1]), (x0 + m(fore[0]), y0 + fore[1])

def squeeze_pulses(cv: Image.Image, ctx: Ctx, pt, t: float, squeezes) -> None:
    """Rings that close in on the gripping fingers at every 'pinch'/'squeeze': the word, made visible."""
    for s in squeezes:
        p = (t - s) / 0.7
        if 0 < p < 1:
            r = ctx.px(78) * (1 - T.ease_out(p)) + ctx.px(16); a = int(220 * (1 - p)); d = ImageDraw.Draw(cv, "RGBA"); d.ellipse((pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r), outline=T.ORANGE + (a,), width=ctx.px(4))

def connector(cv: Image.Image, ctx: Ctx, pts, p: float, dot_end: bool = True):
    """A thin orange line that draws itself along a list of points (a leader between two parts of one idea)."""
    if p <= 0 or len(pts) < 2: return
    import math
    d = ImageDraw.Draw(cv, "RGBA"); seg = [math.dist(a, b) for a, b in zip(pts, pts[1:])]; total = sum(seg) or 1; run = total * T.ease_out(min(1, p)); out = [pts[0]]
    for (a, b), L_ in zip(zip(pts, pts[1:]), seg):
        if run >= L_: out.append(b); run -= L_
        else: out.append((a[0] + (b[0] - a[0]) * run / L_, a[1] + (b[1] - a[1]) * run / L_)); break
    d.line(out, fill=T.ORANGE + (230,), width=ctx.px(3), joint="curve"); d.ellipse((pts[0][0] - 6, pts[0][1] - 6, pts[0][0] + 6, pts[0][1] + 6), fill=T.ORANGE + (255,))
    if dot_end and p >= 1: e = pts[-1]; d.ellipse((e[0] - 6, e[1] - 6, e[0] + 6, e[1] + 6), fill=T.ORANGE + (255,))

def _text_w(d: ImageDraw.ImageDraw, text: str, font, spacing: float = 0) -> float:
    return d.textlength(text, font=font) + spacing * max(0, len(text) - 1)

def text_spaced(d: ImageDraw.ImageDraw, xy, text: str, font, fill, spacing: float = 0, anchor_x: str = "l"):
    x, y = xy; w = _text_w(d, text, font, spacing)
    if anchor_x == "c": x -= w / 2
    elif anchor_x == "r": x -= w
    if not spacing: d.text((x, y), text, font=font, fill=fill); return w
    for ch in text: d.text((x, y), ch, font=font, fill=fill); x += d.textlength(ch, font=font) + spacing
    return w

def overlay_paste(cv: Image.Image, layer: Image.Image, alpha: float = 1.0, xy=(0, 0)):
    if alpha < 1: layer = layer.copy(); layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    cv.paste(layer, xy, layer)

def _tag_draw(d, ctx: Ctx, text: str, bg_a: float, bar_p: float, text_a: float, text_dy: float):
    """One section label at its fixed place: dark plate, red bar (`bar_p` of its height, growing from the bottom), spaced all-caps text."""
    f = ctx.font(T.BODY_FONT, 30); x, y = ctx.px(72), ctx.px(58); bh = ctx.px(46); w = _text_w(d, text, f, ctx.px(2.5)) + ctx.px(26) + ctx.px(34)
    if bg_a > 0: d.rectangle((x, y, x + w, y + bh), fill=(14, 14, 15, int(210 * bg_a)))
    if bar_p > 0: d.rectangle((x, y + int(bh * (1 - bar_p)), x + ctx.px(7), y + bh), fill=T.RED + (int(255 * (text_a if bar_p >= 1 else 1.0)),))
    if text_a > 0: text_spaced(d, (x + ctx.px(26), y + ctx.px(6) + int(text_dy * ctx.S)), text, f, T.WHITE + (int(255 * text_a),), ctx.px(2.5))

TAG_SWAP_S, TAG_OUT_FRAC = 0.5, 0.4

def tag_phase(t: float, prev_text: Optional[str], text: str, t_changed: float = 0.0):
    """Which label is on screen and how far along it is: ("old", fade_out 0..1) | ("new", reveal 0..1). The outgoing label is gone (out = 1) before the incoming one starts (reveal > 0),
    so the two never share a frame. An unchanged label is simply ("new", 1)."""
    if prev_text is None: return ("new", T.ease_out(t / 0.6))
    if prev_text == text: return ("new", 1.0)
    q = (t - t_changed) / TAG_SWAP_S
    if q >= 1: return ("new", 1.0)
    if q < TAG_OUT_FRAC: return ("old", max(0.0, q / TAG_OUT_FRAC))
    return ("new", T.ease_out((q - TAG_OUT_FRAC) / (1 - TAG_OUT_FRAC)))

def section_tag(cv: Image.Image, ctx: Ctx, text: str, t: float, prev_text: Optional[str] = None, t_changed: float = 0.0):
    """Top-left label: red vertical bar + white all-caps text. A changed label first fades the old one out (0.2 s), then wipes the new one in (bar grows, text slides up, 0.3 s); the two are never drawn
    together. An unchanged label just stays."""
    if not text: return
    d = ImageDraw.Draw(cv, "RGBA"); which, p = tag_phase(t, prev_text, text, t_changed)
    if which == "old": a = 1 - p; _tag_draw(d, ctx, prev_text, a, 1.0, a, -10 * p)
    else: _tag_draw(d, ctx, text, p, p, p, 12 * (1 - p))

PILL_TEXT_AT = 0.3      # by p = 0.3 the plate has grown to ~90% of its width, so the first letters always sit inside the outline

def pill(cv: Image.Image, ctx: Ctx, x: float, y: float, text: str, p: float, accent=T.ORANGE, size: int = 36):
    """Outlined pill chip, left-anchored at (x, y); p = 0..1 reveal (grows from its left edge, text fades in)."""
    if p <= 0 or not (text or "").strip(): return 0      # no text, no outline: an empty chip is never drawn
    p = min(1.0, p); d = ImageDraw.Draw(cv, "RGBA"); f = ctx.font(T.BODY_FONT, size); pad = ctx.px(30); h = ctx.px(size + 36); w = int(_text_w(d, text, f, ctx.px(1.5)) + pad * 2); e = T.ease_back(p); ww = max(h, int(w * min(1.0, e)))
    yo = int((1 - T.ease_out(p)) * 18 * ctx.S); box = (int(x), int(y) + yo, int(x) + ww, int(y) + yo + h)
    ta = min(1.0, (p - PILL_TEXT_AT) / 0.25)      # the outline and its text arrive together: the plate only starts once the first letters can be seen
    if ta <= 0: return w
    d.rounded_rectangle(box, radius=h // 2, fill=(255, 255, 255, int(14 * p)), outline=accent + (int(255 * min(1, ta * 2)),), width=ctx.px(3))
    text_spaced(d, (int(x) + pad, int(y) + yo + (h - ctx.px(size)) // 2 - ctx.px(3)), text, f, T.WHITE + (int(255 * ta),), ctx.px(1.5))
    return w

def callout_column(cv: Image.Image, ctx: Ctx, headline: str, hl_p: float, value: str, val_p: float, chips: List[Tuple[str, float]], x: float = 1130, anchor_y: float = 0.5, kicker: str = "", k_p: float = 1.0, floor: float = 0.0):
    """Right-hand callout: bold headline, key value (orange), outlined chips. Each piece slides up and fades in as its own time arrives. Stack is centred on anchor_y."""
    d = ImageDraw.Draw(cv, "RGBA"); hf, vf = ctx.font(T.HEAD_FONT, 104), ctx.font(T.HEAD_FONT, 168); x = ctx.px(x)
    lines = _wrap(d, headline, hf, ctx.W - x - ctx.px(80)) if headline else []; hh = len(lines) * ctx.px(112); vh = ctx.px(180) if value else 0; ch = len(chips) * ctx.px(96)
    kh = ctx.px(48) if kicker else 0; total = kh + hh + (ctx.px(14) if lines else 0) + vh + ch + (ctx.px(26) if chips and (lines or value) else 0); y = int(ctx.H * anchor_y - total / 2)
    if kicker: text_spaced(d, (x, y + int((1 - T.ease_out(k_p)) * 16 * ctx.S)), kicker, ctx.font(T.BODY_FONT, 28), T.ORANGE + (int(255 * min(1, k_p * 1.6)),), ctx.px(4)); y += kh
    hl_p, val_p = min(1.0, max(floor if headline else 0.0, hl_p)), min(1.0, max(floor if (value and not headline) else 0.0, val_p))      # the page's main element is legible from its first frame (floor), its entrance only moves it into place
    for ln in lines:
        a = hl_p; off = int((1 - T.ease_out(a)) * 34 * ctx.S); text_spaced(d, (x, y + off), ln, hf, T.WHITE + (int(255 * min(1, a * 1.6)),), ctx.px(1)); y += ctx.px(112)
    if lines:      # the orange accent: a short bar that sweeps out under the headline
        bw = int(ctx.px(150) * T.ease_out((hl_p - 0.3) / 0.7)); d.rectangle((x, y + ctx.px(2), x + bw, y + ctx.px(9)), fill=T.ORANGE + (255,)); y += ctx.px(14)
    if value:
        a = val_p; off = int((1 - T.ease_back(a)) * 40 * ctx.S); text_spaced(d, (x, y + off), value, vf, T.ORANGE + (int(255 * min(1, a * 1.6)),), 0); y += ctx.px(180)
    y += ctx.px(26) if chips and (lines or value) else 0
    for text, p in chips:
        pill(cv, ctx, x, y, text, p); y += ctx.px(96)

def _wrap(d, text: str, font, max_w: float) -> List[str]:
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if _text_w(d, t, font, ctx_sp(font)) > max_w and cur: out.append(cur); cur = w
        else: cur = t
    return out + ([cur] if cur else [])
def ctx_sp(font): return 1

def glow_ring(cv: Image.Image, ctx: Ctx, cx: float, cy: float, r: float, p: float, pulse: float = 0.0, width: float = 7):
    """Orange ring that draws itself on (clockwise from 12 o'clock) over p = 0..1, then breathes with `pulse` (seconds since drawn). Soft outer glow, tiny arrow tick at the start."""
    if p <= 0: return
    r = r + 4 * ctx.S * (0.5 + 0.5 * __import__("math").sin(pulse * 4.2)) * (1 if p >= 1 else 0); pad = int(r * 0.9 + 40 * ctx.S); size = int(2 * (r + pad)); k = 2
    layer = Image.new("RGBA", (size * k, size * k), (0, 0, 0, 0)); d = ImageDraw.Draw(layer); c = size * k / 2; rr = r * k; w = int(width * ctx.S * k)
    end = -90 + 360 * T.ease_in_out(min(1, p)); d.arc((c - rr, c - rr, c + rr, c + rr), -90, end, fill=T.ORANGE + (255,), width=w)
    layer = layer.resize((size, size), Image.LANCZOS); glow = layer.filter(ImageFilter.GaussianBlur(10 * ctx.S)); a = glow.getchannel("A").point(lambda v: min(255, int(v * 1.1))); glow.putalpha(a)
    x0, y0 = int(cx - size / 2), int(cy - size / 2); cv.paste(glow, (x0, y0), glow); cv.paste(layer, (x0, y0), layer)

def anatomy_glow(cv: Image.Image, ctx: Ctx, box, regions, p: float, pulse: float = 0.0):
    """Orange glow over named regions of an anatomy picture (ellipses as fractions of the picture box), fading in then breathing."""
    if p <= 0: return
    x0, y0, x1, y1 = box; w, h = x1 - x0, y1 - y0; q = 4; layer = Image.new("RGBA", (ctx.W // q, ctx.H // q), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    breathe = 0.82 + 0.18 * math.sin(pulse * 3.4)
    for (fx, fy, fw, fh) in regions:      # drawn and blurred at 1/4 size, then scaled up: the glow is a soft blur anyway, and a full-frame blur was the slowest step of the scene
        cx, cy = (x0 + fx * w) / q, (y0 + fy * h) / q; d.ellipse((cx - fw * w / 2 / q, cy - fh * h / 2 / q, cx + fw * w / 2 / q, cy + fh * h / 2 / q), fill=T.ORANGE + (int(120 * T.ease_out(p) * breathe),))
    layer = layer.filter(ImageFilter.GaussianBlur(ctx.px(46) / q)).resize((ctx.W, ctx.H), Image.BILINEAR); cv.paste(layer, (0, 0), layer)
    d2 = ImageDraw.Draw(cv, "RGBA")
    for (fx, fy, fw, fh) in regions:      # thin outline that draws on with the glow: reads as a deliberate highlight, not a stain
        cx, cy = x0 + fx * w, y0 + fy * h; e = T.ease_out(p); d2.ellipse((cx - fw * w / 2 * e, cy - fh * h / 2 * e, cx + fw * w / 2 * e, cy + fh * h / 2 * e), outline=T.ORANGE + (int(220 * e),), width=ctx.px(3))

def leader(cv: Image.Image, ctx: Ctx, p0, p1, p: float, label: str, lp: float):
    """Line from a point on the art to a label that fades in at its end."""
    d = ImageDraw.Draw(cv, "RGBA"); e = T.ease_out(p); x0, y0 = p0; x1, y1 = p1; xm, ym = _lerp(x0, x1, e), _lerp(y0, y1, e)
    d.line((x0, y0, xm, ym), fill=T.ORANGE + (230,), width=ctx.px(3)); d.ellipse((x0 - 7, y0 - 7, x0 + 7, y0 + 7), fill=T.ORANGE + (255,))
    if lp > 0:
        f = ctx.font(T.HEAD_FONT, 62); off = int((1 - T.ease_out(lp)) * 26 * ctx.S); text_spaced(d, (x1 + ctx.px(24), y1 - ctx.px(46) + off), label, f, T.WHITE + (int(255 * min(1, lp * 1.6)),), ctx.px(1))

def equation(cv: Image.Image, ctx: Ctx, eqs: list, t: float, cx: float = 0.64, cy: float = 0.46):
    """Equation lockup: terms pop in at their own times (back-ease), the symbol between them arrives with the right-hand term; a later pair replaces the earlier one with a slide.
    Each eq is {lhs, rhs, at_l, at_r} with times relative to the scene start."""
    d = ImageDraw.Draw(cv, "RGBA"); big, sym = ctx.font(T.HEAD_FONT, 190), ctx.font(T.HEAD_FONT, 150); lay = None
    for i, e in enumerate(eqs):
        nxt = eqs[i + 1]["at_l"] if i + 1 < len(eqs) else None
        out = T.ease_in_out((t - nxt) / 0.45) if nxt is not None else 0.0
        if out >= 1: continue
        pl, pr = T.ease_back((t - e["at_l"]) / 0.5), T.ease_back((t - e["at_r"]) / 0.5)
        if pl <= 0: continue
        wl, wr, ws = _text_w(d, e["lhs"], big), _text_w(d, e["rhs"], big), ctx.px(128); gap = ctx.px(64); total = wl + ws + wr + gap * 2; x = ctx.W * cx - total / 2; y = ctx.H * cy - ctx.px(110) - out * ctx.px(120) - (1 - T.ease_out((t - e["at_l"]) / 0.5)) * ctx.px(-30)
        fade = 1 - out; lay = (x, y + ctx.px(110), wl)
        for (txt, xx, wd, prog, col) in ((e["lhs"], x, wl, pl, T.WHITE), ("≈", x + wl + gap, ws, pr, T.ORANGE), (e["rhs"], x + wl + gap * 2 + ws, wr, pr, T.ORANGE)):
            if prog <= 0: continue
            sc = 0.82 + 0.18 * min(1.2, prog); layer = Image.new("RGBA", (int(wd * 1.3) + 40, ctx.px(260)), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer); fill = col + (int(255 * min(1, prog * 1.5) * fade),)
            if txt == "≈": _approx(ld, 20, ctx.px(96), wd, ctx.px(120), fill, ctx)
            else: ld.text((20, 20), txt, font=big, fill=fill)
            if sc != 1: layer = layer.resize((int(layer.width * sc), int(layer.height * sc)), Image.BICUBIC)
            cv.paste(layer, (int(xx - 20 + wd * (1 - sc) / 2), int(y - 20 + ctx.px(260) * (1 - sc) / 2)), layer)
    return lay

def _approx(d: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float, fill, ctx: Ctx):
    """The ≈ sign as two waves (the bundled fonts have no glyph for it)."""
    import math
    for k, yy in enumerate((y + h * 0.30, y + h * 0.72)):
        pts = [(x + w * i / 40, yy + math.sin(i / 40 * 2 * math.pi * 1.0 - 0.0) * h * 0.13) for i in range(41)]
        d.line(pts, fill=fill, width=ctx.px(15), joint="curve")
        for (px_, py_) in (pts[0], pts[-1]): d.ellipse((px_ - ctx.px(7.5), py_ - ctx.px(7.5), px_ + ctx.px(7.5), py_ + ctx.px(7.5)), fill=fill)

TIERS = ("S", "A", "B", "C", "D", "F")
TIER_COL = {"S": (222, 38, 38), "A": (255, 122, 26), "B": (240, 176, 40), "C": (170, 170, 168), "D": (120, 120, 120), "F": (84, 84, 86)}

def tier_pointer(t: float, letter: Optional[str], placed_at: Optional[float], marks=()) -> Optional[float]:
    """Row position (0 = S ... 5 = F, fractional while moving) of the ranking pointer at time t, or None before anything is named. It rests on each row the narration names (marks), and
    after the last one travels to the row the item is about to land in, arriving just before `placed_at`: the ranking is walked through, never a still board. Only rows from the narration."""
    way = sorted((float(at), TIERS.index(lt)) for (lt, at) in marks if lt in TIERS and (placed_at is None or float(at) < placed_at - 0.6))
    if letter in TIERS and placed_at is not None: way.append((placed_at - 0.25, TIERS.index(letter)))
    if way and way[0][1] == 0 and way[0][0] > 1.0: way.insert(0, (0.9, 0))      # the scale is read from S down: the pointer waits on S as the rows land, instead of the board sitting empty until the word
    if not way or t < way[0][0]: return None
    for (t0, r0), (t1, r1) in zip(way, way[1:]):
        if t >= t1: continue
        travel = min(max(0.35, 1.4 * abs(r1 - r0)), max(0.3, (t1 - t0) - 0.7)); ts = t1 - travel      # leaves late, so each named row is held first
        return float(r0) if t <= ts else float(r0) + (r1 - r0) * T.ease_in_out((t - ts) / travel)
    return float(way[-1][1])

def tier_board(cv: Image.Image, ctx: Ctx, tier: dict, t: float, thumb: Optional[str], now_name: str, placed_at: float, flash: float, marks=()):
    """S-F ranking: rows on the left, a NOW RANKING card on the right. A pointer rests on each row the narration names and then walks to the row the item will land in; the row under it lifts,
    lights and carries a marker. At `placed_at` the card's picture flies into its row (curved path), the row's letter lights up, a light sweeps the row, the other rows dim and the card
    reads RANKED. Only the current item is ranked here; the progress pill shows 'n / total' only when the narration or scenes file gave a total."""
    d = ImageDraw.Draw(cv, "RGBA"); x0, y0 = ctx.px(120), ctx.px(190); rh, gap = ctx.px(108), ctx.px(12); bw = ctx.px(1010); lw = ctx.px(120); lf = ctx.font(T.HEAD_FONT, 78)
    intro = T.ease_out(t / 0.7); letter = tier["letter"]; placed = T.ease_in_out((t - placed_at) / 0.8) if (placed_at is not None and letter) else 0.0
    pos = tier_pointer(t, letter, placed_at if letter else None, marks); fin = T.ease_out(flash / 0.6) if placed >= 1 else 0.0      # fin: 0 -> 1 after the item has landed
    for i, k in enumerate(TIERS):
        ry = y0 + i * (rh + gap); a = T.ease_out((t - 0.08 * i) / 0.5); on = (k == letter) and placed >= 1
        act = 0.0 if pos is None else max(0.0, 1 - abs(pos - i) * 1.4)      # how much the pointer is on this row
        if on: act = 1.0
        xo = int((1 - a) * -60 * ctx.S + 18 * act * ctx.S); grow = int(3 * act * ctx.S)
        d.rounded_rectangle((x0 + xo, ry - grow, x0 + xo + bw, ry + rh + grow), radius=ctx.px(10), fill=(20 + int(60 * act), 20 + int(26 * act), 22 + int(2 * act), int(235 * a)), outline=((60, 60, 64) if act < 0.05 else T.ORANGE) + (int(255 * a),), width=2 + int(4 * act))
        col = T.ORANGE if on else tuple(int(c + (255 - c) * 0.22 * act) for c in TIER_COL[k]); d.rounded_rectangle((x0 + xo, ry - grow, x0 + xo + lw, ry + rh + grow), radius=ctx.px(10), fill=col + (int(255 * a),))
        text_spaced(d, (x0 + xo + lw / 2, ry + ctx.px(10)), k, lf, (12, 12, 12, int(255 * a)), 0, anchor_x="c")
    if pos is not None and placed < 1:      # the marker: a small orange arrow on the left edge that rides with the pointer
        my = y0 + pos * (rh + gap) + rh / 2; mx = x0 - ctx.px(34) + int(5 * ctx.S * math.sin(t * 7)); s_ = ctx.px(15); d.polygon([(mx - s_, my - s_), (mx + s_, my), (mx - s_, my + s_)], fill=T.ORANGE + (int(255 * intro),))
    if fin > 0 and letter:      # finish: the other rows dim, a light sweeps along the landed row, which keeps a heavier outline
        row = TIERS.index(letter); ry = y0 + row * (rh + gap); dim = Image.new("RGBA", (bw, rh), (0, 0, 0, int(120 * fin)))
        for i in range(len(TIERS)):
            if i != row: cv.paste(dim, (x0, y0 + i * (rh + gap)), dim)
        sw = T.ease_in_out(flash / 0.9)
        if 0 < sw < 1:
            bx = x0 + lw + (bw - lw) * sw; sweep = Image.new("RGBA", (ctx.px(110), rh), (255, 214, 160, 70)); sweep.putalpha(sweep.getchannel("A").point(lambda v: int(v * math.sin(math.pi * sw)))); cv.paste(sweep, (int(bx - sweep.width / 2), int(ry)), sweep)
    pill_txt = ("RANKED " + (f"{tier.get('rank') or 1}" + (f" / {tier['total']}" if tier.get("total") else "") if placed >= 1 else "0" + (f" / {tier['total']}" if tier.get("total") else ""))); pf = ctx.font(T.BODY_FONT, 28)
    d.text((x0, y0 - ctx.px(60)), pill_txt, font=pf, fill=T.ORANGE + (int(255 * intro),))
    cxp, cyp, cw, chh = ctx.px(1330), ctx.px(190), ctx.px(470), ctx.px(640); slide = (1 - T.ease_out((t - 0.25) / 0.6)) * ctx.px(220); wait = 0.5 + 0.5 * math.sin(t * 3.0) if placed <= 0 else 1.0      # the card breathes while it waits
    d.rounded_rectangle((cxp + slide, cyp, cxp + slide + cw, cyp + chh), radius=ctx.px(16), fill=(18, 18, 20, 240), outline=T.ORANGE + (int(255 * intro * (0.55 + 0.45 * wait)),), width=ctx.px(3))
    text_spaced(d, (cxp + slide + ctx.px(28), cyp + ctx.px(24)), "RANKED" if placed >= 1 else "NOW RANKING", ctx.font(T.BODY_FONT, 30), T.ORANGE + (255,), ctx.px(3))
    if now_name: text_spaced(d, (cxp + slide + cw / 2, cyp + chh - ctx.px(86)), now_name, ctx.font(T.BODY_FONT, 34), T.WHITE + (255,), ctx.px(1.5), anchor_x="c")
    if placed >= 1 and letter:      # the card closes on the verdict: the tier letter, big
        text_spaced(d, (cxp + slide + cw / 2, cyp + ctx.px(150)), letter, ctx.font(T.HEAD_FONT, 300), TIER_COL.get(letter, T.ORANGE) + (int(255 * min(1, (placed - 0.9) * 10)),), 0, anchor_x="c")
    if thumb and letter:
        im = ctx.art(thumb); th = ctx.px(380); small = ctx.px(100)
        sx, sy = cxp + slide + cw / 2, cyp + ctx.px(290); row = TIERS.index(letter); ex, ey = x0 + lw + ctx.px(70), y0 + row * (rh + gap) + rh / 2
        e = placed; sy += (1 - e) * ctx.px(8) * math.sin(t * 2.4)      # a gentle bob while the card waits
        px_ = _lerp(sx, ex, e); py_ = _lerp(sy, ey, e) - 4 * ctx.px(120) * e * (1 - e); hh = int(_lerp(th, small, e)); ww = max(2, int(im.width * hh / im.height))
        r = im.resize((ww, max(2, hh)), Image.BICUBIC); cv.paste(r, (int(px_ - ww / 2), int(py_ - hh / 2)), r)
        if placed >= 1 and flash > 0: glow_ring(cv, ctx, ex, ey, ctx.px(64), min(1, flash / 0.5), flash, 5)
        if placed >= 1 and now_name:      # the ranked item is named in its row, so the final ranking reads without the card
            a = int(255 * T.ease_out(flash / 0.5)); text_spaced(d, (ex + ctx.px(78), ey - ctx.px(20)), now_name, ctx.font(T.BODY_FONT, 34), T.WHITE + (a,), ctx.px(1.5))

END_CARD_S = 5.0

def end_card(cv: Image.Image, ctx: Ctx, title: str, url: str, image: Optional[Image.Image], t: float) -> None:
    """Optional product end card on the same near-black canvas: the product picture (when given) on the left, the title in the headline type with the orange accent bar, the URL in the outlined pill.
    Without a picture the text block is centred. Everything arrives in the first ~1.4 s, then the card holds with a very slow push on the picture."""
    d = ImageDraw.Draw(cv, "RGBA"); hf = ctx.font(T.HEAD_FONT, 112); has_img = image is not None; cx = ctx.W * (0.70 if has_img else 0.5)
    if has_img:
        p = T.ease_out((t - 0.1) / 0.6); box_w, box_h = ctx.px(760), ctx.px(700); k = min(box_w / image.width, box_h / image.height) * (1.0 + 0.02 * min(1.0, t / END_CARD_S))
        r = image.resize((max(2, int(image.width * k)), max(2, int(image.height * k))), Image.BICUBIC)
        m = Image.new("L", r.size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, r.width - 1, r.height - 1), radius=ctx.px(22), fill=255)      # rounded corners: a picture with its own black ground reads as a panel, not a stray box
        r.putalpha(Image.fromarray((__import__("numpy").asarray(r.getchannel("A")).astype("float32") * __import__("numpy").asarray(m).astype("float32") / 255 * p).astype("uint8")))
        x0, y0 = int(ctx.W * 0.27 - r.width / 2), int(ctx.H * 0.5 - r.height / 2 + (1 - p) * ctx.px(24)); cv.paste(r, (x0, y0), r)
        d.rounded_rectangle((x0, y0, x0 + r.width - 1, y0 + r.height - 1), radius=ctx.px(22), outline=T.ORANGE + (int(200 * p),), width=ctx.px(3))
    lines = _wrap(d, title.upper(), hf, ctx.W * (0.42 if has_img else 0.8)) if title else []; lh = ctx.px(124); pill_h = ctx.px(72)
    total = len(lines) * lh + (ctx.px(30) if lines else 0) + (pill_h if url else 0); y = int(ctx.H * 0.5 - total / 2); anchor = "l" if has_img else "c"; x = ctx.W * 0.50 if has_img else ctx.W * 0.5
    for i, ln in enumerate(lines):
        a = T.ease_out((t - 0.3 - 0.12 * i) / 0.55); w = _text_w(d, ln, hf, ctx.px(1)); xx = x if has_img else x
        text_spaced(d, (xx, y + int((1 - a) * 34 * ctx.S)), ln, hf, T.WHITE + (int(255 * min(1, a * 1.6)),), ctx.px(1), anchor_x=anchor); y += lh
    if lines:
        bw = int(ctx.px(170) * T.ease_out((t - 0.7) / 0.6)); bx = int(x if has_img else x - ctx.px(85)); d.rectangle((bx, y, bx + bw, y + ctx.px(8)), fill=T.ORANGE + (255,)); y += ctx.px(30)
    if url:
        pf = ctx.font(T.BODY_FONT, 36); w = int(_text_w(d, url, pf, ctx.px(1.5)) + ctx.px(60)); px0 = x if has_img else x - w / 2; pill(cv, ctx, px0, y, url, (t - 1.0) / 0.5)
