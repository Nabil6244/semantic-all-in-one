"""Code-drawn graphic cards for Rep Theory: a stat ring, numbered steps, a versus panel, a spoken-word takeaway and a chapter banner. Nothing to generate or download (no per-video asset burden): each card is
drawn from the words and numbers of the beat it belongs to, and every element arrives on the time its words are spoken. Times in the card dicts are relative to the scene start."""
from __future__ import annotations
import math
from typing import List
from PIL import Image, ImageDraw

from . import draw as D, theme as T

def _wrap_lines(d, text: str, font, max_w: float) -> List[str]: return D._wrap(d, text, font, max_w) or [""]

def _ring(cv, ctx, cx, cy, r, frac, t, orbit=True):
    """Track ring + orange progress arc (0..1 of the circle from 12 o'clock) + a dot that orbits once every 4 s (continuous motion while the number stays up). Supersampled for clean edges."""
    k = 2; side = int((r + ctx.px(40)) * 2 * k); lay = Image.new("RGBA", (side, side), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); c = side // 2; rr = int(r * k); w = int(ctx.px(22) * k)
    d.ellipse((c - rr, c - rr, c + rr, c + rr), outline=T.DIM + (255,), width=w)
    if frac > 0.002: d.arc((c - rr, c - rr, c + rr, c + rr), -90, -90 + 360 * min(1.0, frac), fill=T.ORANGE + (255,), width=w)
    if orbit:
        a = math.radians(-90 + 360 * ((t / 4.0) % 1.0)); ox, oy = c + rr * math.cos(a), c + rr * math.sin(a); q = int(ctx.px(9) * k); d.ellipse((ox - q, oy - q, ox + q, oy + q), fill=T.WHITE + (255,))
    lay = lay.resize((side // k, side // k), Image.LANCZOS); cv.paste(lay, (int(cx - side // (2 * k)), int(cy - side // (2 * k))), lay)

def stat(cv: Image.Image, ctx: D.Ctx, st: dict, t: float) -> None:
    """The number the narration states, large inside a ring: seconds/minutes fill the ring like a timer, percents fill to that percent, counts (sets, reps, weeks, days) light one dot each."""
    cx, cy, r = int(ctx.W * 0.30), int(ctx.H * 0.52), int(ctx.H * 0.22); p = max(0.0, (t - st["at"]) / 0.9); e = T.ease_out(p); v = st["value"]; mode = st["mode"]; d = ImageDraw.Draw(cv, "RGBA")
    if mode == "dots":
        n = int(v); _ring(cv, ctx, cx, cy, r, 0.0, t, orbit=False)
        for i in range(min(n, 12)):      # a dot per count, lit in turn
            a = math.radians(-90 + 360 * i / max(1, min(n, 12))); lit = T.ease_back((t - st["at"] - 0.15 * i) / 0.4); q = int(ctx.px(17) * min(1.0, max(0.0, lit)))
            if q > 0: x, y = cx + r * math.cos(a), cy + r * math.sin(a); d.ellipse((x - q, y - q, x + q, y + q), fill=T.ORANGE + (255,))
    else: _ring(cv, ctx, cx, cy, r, (min(1.0, v / 100.0) if mode == "fill" else 1.0) * e, t)
    shown = v * e; txt = (f"{shown:.0f}" if abs(v - round(v)) < 1e-6 else f"{shown:.1f}"); f = ctx.font(T.HEAD_FONT, 190); w = D._text_w(d, txt, f, 0)
    D.text_spaced(d, (cx - w / 2, cy - ctx.px(122)), txt, f, T.WHITE + (255,), 0); u = ctx.font(T.BODY_FONT, 44); uw = D._text_w(d, st["unit"], u, ctx.px(4)); D.text_spaced(d, (cx - uw / 2, cy + ctx.px(76)), st["unit"], u, T.ORANGE + (255,), ctx.px(4))

def steps(cv: Image.Image, ctx: D.Ctx, items: List[dict], t: float) -> None:
    """Numbered steps that appear as the narration reaches them, joined by a line that draws down."""
    d = ImageDraw.Draw(cv, "RGBA"); n = len(items); x0, top, gap = ctx.px(150), int(ctx.H * 0.5 - (n - 1) * ctx.px(62)), ctx.px(124); r = ctx.px(40); f = ctx.font(T.HEAD_FONT, 76); nf = ctx.font(T.HEAD_FONT, 44)
    for i, it in enumerate(items):
        p = (t - it["at"]) / 0.5; e = T.ease_out(p); y = top + i * gap
        if i and p > -0.3:      # the line from the previous step draws down to this one
            q = T.ease_out((t - items[i - 1]["at"] - 0.2) / 0.5); d.line((x0, y - gap + r, x0, y - gap + r + (gap - 2 * r) * q), fill=T.ORANGE_DEEP + (255,), width=ctx.px(5))
        if p <= 0: d.ellipse((x0 - r, y - r, x0 + r, y + r), outline=T.DIM + (255,), width=ctx.px(4)); continue
        d.ellipse((x0 - r, y - r, x0 + r, y + r), fill=T.ORANGE + (int(255 * min(1, p * 2)),)); lw = D._text_w(d, str(i + 1), nf, 0); D.text_spaced(d, (x0 - lw / 2, y - ctx.px(27)), str(i + 1), nf, (20, 20, 22, 255), 0)
        D.text_spaced(d, (x0 + r + ctx.px(36) + int((1 - e) * 40 * ctx.S), y - ctx.px(48)), it["text"], f, T.WHITE + (int(255 * min(1, p * 1.6)),), ctx.px(1))

def versus(cv: Image.Image, ctx: D.Ctx, v: dict, t: float) -> None:
    """Two panels, one per side of the comparison, each arriving as its side is spoken, with a VS badge between them."""
    d = ImageDraw.Draw(cv, "RGBA"); pw, ph = int(ctx.W * 0.40), int(ctx.H * 0.46); y0 = int(ctx.H * 0.27); f = ctx.font(T.HEAD_FONT, 84)
    for side, key in (("l", "a"), ("r", "b")):
        s = v[key]; p = (t - s["at"]) / 0.55; e = T.ease_out(p)
        if p <= 0: continue
        x0 = int(ctx.W * 0.06) if side == "l" else int(ctx.W * 0.54); x0 += int((1 - e) * (-1 if side == "l" else 1) * 120 * ctx.S); col = T.SOFT_WHITE if side == "l" else T.ORANGE; a = int(255 * min(1, p * 1.6))
        d.rounded_rectangle((x0, y0, x0 + pw, y0 + ph), radius=ctx.px(26), fill=(255, 255, 255, int(12 * min(1, p))), outline=col + (a,), width=ctx.px(4))
        lines = _wrap_lines(d, s["text"], f, pw - ctx.px(80)); h = len(lines) * ctx.px(96); yy = y0 + (ph - h) // 2
        for ln in lines: w = D._text_w(d, ln, f, ctx.px(1)); D.text_spaced(d, (x0 + (pw - w) / 2, yy), ln, f, T.WHITE + (a,), ctx.px(1)); yy += ctx.px(96)
    bp = T.ease_back((t - v["b"]["at"] - 0.1) / 0.45)
    if bp > 0:
        rr = int(ctx.px(58) * min(1.0, bp)); cx, cy = ctx.W // 2, y0 + ph // 2; d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(14, 14, 16, 255), outline=T.ORANGE + (255,), width=ctx.px(5))
        if bp > 0.6: bf = ctx.font(T.HEAD_FONT, 52); bw = D._text_w(d, "VS", bf, 0); D.text_spaced(d, (cx - bw / 2, cy - ctx.px(34)), "VS", bf, T.WHITE + (255,), 0)

def takeaway(cv: Image.Image, ctx: D.Ctx, tk: dict, t: float) -> None:
    """The line the viewer should keep, large and centred; each word lights up as it is spoken (the rest waits in grey), with an orange bar and a KEY POINT kicker."""
    d = ImageDraw.Draw(cv, "RGBA"); f = ctx.font(T.HEAD_FONT, 96); words = tk["words"]; max_w = ctx.W * 0.68; x0 = int(ctx.W * 0.17); lines, cur, curw = [], [], 0.0; sp = D._text_w(d, " ", f, 0)
    for i, w in enumerate(words):
        ww = D._text_w(d, w["w"], f, ctx.px(1))
        if cur and curw + sp + ww > max_w: lines.append(cur); cur, curw = [], 0.0
        cur.append((i, w, ww)); curw += (sp if len(cur) > 1 else 0) + ww
    if cur: lines.append(cur)
    lh = ctx.px(118); top = int(ctx.H * 0.5 - len(lines) * lh / 2); bp = T.ease_out(t / 0.7); bh = int(len(lines) * lh * bp)
    d.rectangle((x0 - ctx.px(46), top, x0 - ctx.px(38), top + bh), fill=T.ORANGE + (255,)); D.text_spaced(d, (x0, top - ctx.px(64)), "KEY POINT", ctx.font(T.BODY_FONT, 30), T.ORANGE + (int(255 * min(1, t / 0.4)),), ctx.px(5))
    for li, ln in enumerate(lines):
        x = x0
        for i, w, ww in ln:
            on = T.ease_out((t - w["t0"]) / 0.25); col = tuple(int(a + (b - a) * on) for a, b in zip((78, 78, 82), T.WHITE))
            D.text_spaced(d, (x, top + li * lh), w["w"], f, col + (255,), ctx.px(1)); x += ww + sp

def chapter(cv: Image.Image, ctx: D.Ctx, ch: dict, t: float) -> None:
    """A chapter banner for the first moments of a new part of a long video: PART n / N, its title, and a progress bar showing where in the video the viewer is."""
    T_IN, T_HOLD, T_OUT = 0.45, 2.4, 0.5
    if t > T_IN + T_HOLD + T_OUT: return
    a = min(1.0, t / T_IN, (T_IN + T_HOLD + T_OUT - t) / T_OUT); a = max(0.0, a); lay = Image.new("RGBA", (ctx.W, ctx.H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); x, y = ctx.px(100), int(ctx.H * 0.80)
    d.rounded_rectangle((x - ctx.px(34), y - ctx.px(36), x + ctx.px(960), y + ctx.px(190)), radius=ctx.px(22), fill=(8, 8, 10, 200))
    D.text_spaced(d, (x, y - ctx.px(10)), f"PART {ch['n']:02d} / {ch['of']:02d}", ctx.font(T.BODY_FONT, 30), T.ORANGE + (255,), ctx.px(5))
    D.text_spaced(d, (x, y + ctx.px(32)), ch["title"][:34], ctx.font(T.HEAD_FONT, 72), T.WHITE + (255,), ctx.px(1))
    bw = ctx.px(880); d.rectangle((x, y + ctx.px(150), x + bw, y + ctx.px(158)), fill=T.DIM + (255,)); d.rectangle((x, y + ctx.px(150), x + int(bw * ch["n"] / ch["of"]), y + ctx.px(158)), fill=T.ORANGE + (255,))
    D.overlay_paste(cv, lay, a)
