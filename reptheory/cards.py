"""Code-drawn graphic cards for Rep Theory: a stat ring, numbered steps, a versus panel, a spoken-word takeaway and a chapter banner. Nothing to generate or download (no per-video asset burden): each card is
drawn from the words and numbers of the beat it belongs to, and every element arrives on the time its words are spoken. Times in the card dicts are relative to the scene start."""
from __future__ import annotations
import math, re
from typing import Optional, List
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

def _roll(t: float, at: float) -> tuple:
    """(progress 0..1, landing time) of a number that counts up from the scene's first frame and lands on its word: never an empty ring, never a number held before it is said."""
    land_t = max(0.6, at + 0.2); return min(1.0, max(0.0, t / land_t)), land_t

def stat(cv: Image.Image, ctx: D.Ctx, st: dict, t: float) -> None:
    """The number the narration states, large inside a ring, counting up from the scene's start and landing on its word: seconds/minutes fill the ring like a timer, percents fill to
    that percent, counts (sets, reps, weeks, days) light one dot each."""
    cx, cy, r = int(ctx.W * 0.30), int(ctx.H * 0.52), int(ctx.H * 0.22); p, land_t = _roll(t, st["at"]); e = T.ease_in_out(p); v = st["value"]; mode = st["mode"]; d = ImageDraw.Draw(cv, "RGBA")
    if mode == "dots":
        n = int(v); _ring(cv, ctx, cx, cy, r, 0.0, t, orbit=False); k = min(n, 12)
        for i in range(k):      # a dot per count, lit in turn up to the word
            a = math.radians(-90 + 360 * i / max(1, k)); lit = T.ease_back((t - land_t * i / max(1, k)) / 0.3); q = int(ctx.px(17) * min(1.0, max(0.0, lit)))
            if q > 0: x, y = cx + r * math.cos(a), cy + r * math.sin(a); d.ellipse((x - q, y - q, x + q, y + q), fill=T.ORANGE + (255,))
    else: _ring(cv, ctx, cx, cy, r, (min(1.0, v / 100.0) if mode == "fill" else 1.0) * e, t)
    shown = v * e; txt = (f"{shown:.0f}" if abs(v - round(v)) < 1e-6 else f"{shown:.1f}"); f = ctx.font(T.HEAD_FONT, 190); w = D._text_w(d, txt, f, 0)
    land = t - land_t      # the number has reached what was said: it flips to orange and the ring throws a pulse
    if 0 <= land < 0.7: q = T.ease_out(land / 0.7); rr = r * (1.0 + 0.35 * q); d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=T.ORANGE + (int(200 * (1 - q)),), width=ctx.px(6))
    D.text_spaced(d, (cx - w / 2, cy - ctx.px(122)), txt, f, (T.ORANGE if land >= 0 else T.WHITE) + (int(255 * min(1.0, t / 0.25)),), 0)
    u = ctx.font(T.BODY_FONT, 44); uw = D._text_w(d, st["unit"], u, ctx.px(4)); D.text_spaced(d, (cx - uw / 2, cy + ctx.px(76)), st["unit"], u, T.ORANGE + (255,), ctx.px(4))

def steps(cv: Image.Image, ctx: D.Ctx, items: List[dict], t: float, ticks: bool = False) -> None:
    """Numbered steps that appear as the narration reaches them, joined by a line that draws down (a spoken list: a tick instead of the number)."""
    d = ImageDraw.Draw(cv, "RGBA"); n = len(items); x0, top, gap = ctx.px(150), int(ctx.H * 0.5 - (n - 1) * ctx.px(62)), ctx.px(124); r = ctx.px(40); f = ctx.font(T.HEAD_FONT, 76); nf = ctx.font(T.HEAD_FONT, 44)
    for i, it in enumerate(items):
        p = (t - it["at"]) / 0.5; e = T.ease_out(p); y = top + i * gap
        if i and p > -0.3:      # the line from the previous step draws down to this one
            q = T.ease_out((t - items[i - 1]["at"] - 0.2) / 0.5); d.line((x0, y - gap + r, x0, y - gap + r + (gap - 2 * r) * q), fill=T.ORANGE_DEEP + (255,), width=ctx.px(5))
        if p <= 0: d.ellipse((x0 - r, y - r, x0 + r, y + r), outline=T.DIM + (255,), width=ctx.px(4)); continue
        d.ellipse((x0 - r, y - r, x0 + r, y + r), fill=T.ORANGE + (int(255 * min(1, p * 2)),))
        if ticks: q = min(1.0, p); d.line((x0 - ctx.px(16), y + ctx.px(2), x0 - ctx.px(4), y + ctx.px(14) * min(1, q * 2)), fill=T.P(20, 20, 22, 255), width=ctx.px(7)); d.line((x0 - ctx.px(4), y + ctx.px(14), x0 - ctx.px(4) + ctx.px(22) * max(0, q * 2 - 1), y + ctx.px(14) - ctx.px(28) * max(0, q * 2 - 1)), fill=T.P(20, 20, 22, 255), width=ctx.px(7)) if q > 0.5 else None
        else: lw = D._text_w(d, str(i + 1), nf, 0); D.text_spaced(d, (x0 - lw / 2, y - ctx.px(27)), str(i + 1), nf, (20, 20, 22, 255), 0)
        dim = 0.45 if i + 1 < n and t >= items[i + 1]["at"] else 1.0      # the step being said is bright, the ones before it step back
        D.text_spaced(d, (x0 + r + ctx.px(36) + int((1 - e) * 40 * ctx.S), y - ctx.px(48)), it["text"], f, T.WHITE + (int(255 * min(1, p * 1.6) * dim),), ctx.px(1))

def versus(cv: Image.Image, ctx: D.Ctx, v: dict, t: float) -> None:
    """Two panels, one per side of the comparison, each arriving as its side is spoken, with a VS badge between them."""
    d = ImageDraw.Draw(cv, "RGBA"); pw, ph = int(ctx.W * 0.40), int(ctx.H * 0.46); y0 = int(ctx.H * 0.27); f = ctx.font(T.HEAD_FONT, 84)
    for side, key in (("l", "a"), ("r", "b")):
        s = v[key]; p = (t - s["at"]) / 0.55; e = T.ease_out(p)
        if p <= 0: continue
        x0 = int(ctx.W * 0.06) if side == "l" else int(ctx.W * 0.54); x0 += int((1 - e) * (-1 if side == "l" else 1) * 120 * ctx.S); col = T.SOFT_WHITE if side == "l" else T.ORANGE; a = int(255 * min(1, p * 1.6) * (0.5 if key == "a" and t >= v["b"]["at"] + 0.3 else 1.0))      # once the second side is said, the first steps back
        d.rounded_rectangle((x0, y0, x0 + pw, y0 + ph), radius=ctx.px(26), fill=(255, 255, 255, int(12 * min(1, p))), outline=col + (a,), width=ctx.px(4))
        lines = _wrap_lines(d, s["text"], f, pw - ctx.px(80)); h = len(lines) * ctx.px(96); yy = y0 + (ph - h) // 2
        for ln in lines: w = D._text_w(d, ln, f, ctx.px(1)); D.text_spaced(d, (x0 + (pw - w) / 2, yy), ln, f, T.WHITE + (a,), ctx.px(1)); yy += ctx.px(96)
    bp = T.ease_back((t - v["b"]["at"] - 0.1) / 0.45)
    if bp > 0:
        rr = int(ctx.px(58) * min(1.0, bp)); cx, cy = ctx.W // 2, y0 + ph // 2; d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=T.P(14, 14, 16, 255), outline=T.ORANGE + (255,), width=ctx.px(5))
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

def streak_wipe(cv: Image.Image, ctx: D.Ctx, t: float, dur: float = 0.55) -> None:
    """A band of diagonal orange-red speed streaks crossing the frame left to right as a new part of the video opens."""
    if not 0 <= t < dur: return
    p = t / dur; d = ImageDraw.Draw(cv, "RGBA"); W, H = ctx.W, ctx.H; band = W * 0.35; cx = -band + (W + 2 * band) * T.ease_in_out(p); sk = H * 0.35
    for i in range(14):
        x = cx + (i - 7) * band / 14 + ((i * 37) % 11 - 5) * ctx.px(6); w = ctx.px(6 + (i * 13) % 18)
        d.polygon([(x, 0), (x + w, 0), (x + w - sk, H), (x - sk, H)], fill=(T.ORANGE if i % 3 else (214, 40, 30)) + (int(150 * math.sin(math.pi * p)),))

def chapter(cv: Image.Image, ctx: D.Ctx, ch: dict, t: float) -> None:
    """A chapter banner for the first moments of a new part of a long video: PART n / N, its title, and a progress bar showing where in the video the viewer is."""
    T_IN, T_HOLD, T_OUT = 0.45, 2.4, 0.5
    if t > T_IN + T_HOLD + T_OUT: return
    if T.THEME == "jung":      # an old book's chapter opening: the scene dims, a gold Roman numeral, thin gold rules, the title in ivory serif
        a = max(0.0, min(1.0, t / T_IN, (T_IN + T_HOLD + T_OUT - t) / T_OUT)); from .film import roman
        lay = Image.new("RGBA", (ctx.W, ctx.H), (8, 6, 4, int(238 * a))); d = ImageDraw.Draw(lay); cx, cy = ctx.W / 2, ctx.H * 0.47      # nearly opaque: the card is its own moment, the scene under it does not show through
        num = roman(int(ch["n"])); fn = ctx.font(T.HEAD_FONT, 150); nw = D._text_w(d, num, fn, 0); e = T.ease_out(min(1.0, t / 0.7))
        d.text((cx - nw / 2, cy - ctx.px(190) + int((1 - e) * 20 * ctx.S)), num, font=fn, fill=T.ORANGE + (int(255 * a),))
        rw = ctx.px(220) * e; d.rectangle((cx - rw, cy + ctx.px(8), cx + rw, cy + ctx.px(10)), fill=T.ORANGE + (int(200 * a),))
        title = ch["title"][:34]; ft = ctx.font(T.HEAD_FONT, 64); tw = D._text_w(d, title, ft, ctx.px(4))
        D.text_spaced(d, (cx - tw / 2, cy + ctx.px(36)), title, ft, T.WHITE + (int(255 * a * min(1.0, max(0.0, (t - 0.25) / 0.5))),), ctx.px(4))
        D.overlay_paste(cv, lay, 1.0); return
    a = min(1.0, t / T_IN, (T_IN + T_HOLD + T_OUT - t) / T_OUT); a = max(0.0, a); lay = Image.new("RGBA", (ctx.W, ctx.H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); x, y = ctx.px(100), int(ctx.H * 0.80)
    if T.THEME in T.LIGHT:      # the light canvases: a white card with a soft shadow, navy title, teal part number and progress (the dark plate made the navy title unreadable)
        e = T.ease_out(min(1.0, t / 0.5)); xx = x + int((1 - e) * -60 * ctx.S); box = (xx - ctx.px(34), y - ctx.px(36), xx + ctx.px(960), y + ctx.px(190))
        d.rounded_rectangle((box[0] + ctx.px(8), box[1] + ctx.px(12), box[2] + ctx.px(8), box[3] + ctx.px(12)), radius=ctx.px(22), fill=(20, 40, 60, 40))
        d.rounded_rectangle(box, radius=ctx.px(22), fill=(255, 255, 255, 245), outline=T.DIM + (255,), width=ctx.px(2)); d.rounded_rectangle((box[0], box[1], box[0] + ctx.px(12), box[3]), radius=ctx.px(6), fill=T.ORANGE + (255,))
        D.text_spaced(d, (xx, y - ctx.px(10)), f"PART {ch['n']:02d} / {ch['of']:02d}", ctx.font(T.BODY_FONT, 30), T.ORANGE + (255,), ctx.px(5))
        title = ch["title"][:34]; typed = title[:max(0, min(len(title), int((t - 0.2) / 0.035)))]; D.text_spaced(d, (xx, y + ctx.px(32)), typed, ctx.font(T.HEAD_FONT, 72), T.WHITE + (255,), ctx.px(1))
        bw = ctx.px(880); d.rounded_rectangle((xx, y + ctx.px(150), xx + bw, y + ctx.px(158)), radius=ctx.px(4), fill=T.DIM + (255,)); d.rounded_rectangle((xx, y + ctx.px(150), xx + int(bw * ch["n"] / ch["of"] * e), y + ctx.px(158)), radius=ctx.px(4), fill=T.ORANGE + (255,))
        D.overlay_paste(cv, lay, a); return
    d.rounded_rectangle((x - ctx.px(34), y - ctx.px(36), x + ctx.px(960), y + ctx.px(190)), radius=ctx.px(22), fill=(8, 8, 10, 200))
    D.text_spaced(d, (x, y - ctx.px(10)), f"PART {ch['n']:02d} / {ch['of']:02d}", ctx.font(T.BODY_FONT, 30), T.ORANGE + (255,), ctx.px(5))
    title = ch["title"][:34]; typed = title[:max(0, min(len(title), int((t - 0.2) / 0.035)))]      # the title types itself on, a letter every 35 ms
    g = 1.0 - (t - 0.15) / 0.45 if 0.15 <= t < 0.6 else 0.0      # glitch entrance: red / cyan copies split off the title and slices jump, settling in 0.45 s
    if g > 0:
        j = int(((t * 97) % 1.0 - 0.5) * 2 * ctx.px(16) * g); d.text((x - ctx.px(10) * g + j, y + ctx.px(32)), typed, font=ctx.font(T.HEAD_FONT, 72), fill=(255, 40, 60, int(170 * g))); d.text((x + ctx.px(10) * g - j, y + ctx.px(32)), typed, font=ctx.font(T.HEAD_FONT, 72), fill=(40, 230, 255, int(170 * g)))
    D.text_spaced(d, (x, y + ctx.px(32)), typed, ctx.font(T.HEAD_FONT, 72), T.WHITE + (255,), ctx.px(1))
    if g > 0.3:
        band = (int(t * 53) % 3) * ctx.px(22); sl = lay.crop((x, y + ctx.px(40) + band, x + ctx.px(900), y + ctx.px(58) + band)); lay.paste(sl, (x + int(ctx.px(26) * g), y + ctx.px(40) + band))
    if typed and len(typed) < len(title): cx = x + D._text_w(d, typed, ctx.font(T.HEAD_FONT, 72), ctx.px(1)) + ctx.px(8); d.rectangle((cx, y + ctx.px(44), cx + ctx.px(8), y + ctx.px(110)), fill=T.ORANGE + (255,))
    bw = ctx.px(880); d.rectangle((x, y + ctx.px(150), x + bw, y + ctx.px(158)), fill=T.DIM + (255,)); d.rectangle((x, y + ctx.px(150), x + int(bw * ch["n"] / ch["of"]), y + ctx.px(158)), fill=T.ORANGE + (255,))
    D.overlay_paste(cv, lay, a)


# ---------------------------------------------------------------- Step 4 cards (detected in variety.py from the sentence's own shape)
RED = (232, 64, 52)      # green is T.GREEN (theme.py): a darker mint on the cat canvas

def _txt(d, ctx, xy, text, size, col, a, head=True, centre=False):
    f = ctx.font(T.HEAD_FONT if head else T.BODY_FONT, size); x, y = xy
    if centre: x -= D._text_w(d, text, f, ctx.px(1)) / 2
    D.text_spaced(d, (x, y), text, f, col + (int(255 * max(0.0, min(1.0, a))),), ctx.px(1))

def timeline(cv: Image.Image, ctx: D.Ctx, tl: dict, t: float) -> None:
    """What you feel as the clock runs: a stopwatch counting through the stated marks on the left, the marks stacking up on the right as they are said; the one being said is bright."""
    d = ImageDraw.Draw(cv, "RGBA"); its = tl["items"]; cx, cy, r = int(ctx.W * 0.25), int(ctx.H * 0.52), int(ctx.H * 0.20)
    live = [i for i, it in enumerate(its) if t >= it["at"]]; k = live[-1] if live else -1
    if k < 0: v = 0.0
    elif k + 1 < len(its): q = min(1.0, (t - its[k]["at"]) / max(0.5, its[k + 1]["at"] - its[k]["at"])); v = its[k]["value"] + (its[k + 1]["value"] - its[k]["value"]) * q * 0.9
    else: v = its[k]["value"] + min(1.0, t - its[k]["at"]) * 0.0
    top = max(it["value"] for it in its); _ring(cv, ctx, cx, cy, r, v / top, t)
    d.rectangle((cx - ctx.px(18), cy - r - ctx.px(34), cx + ctx.px(18), cy - r - ctx.px(14)), fill=T.ORANGE + (255,))
    _txt(d, ctx, (cx, cy - ctx.px(88)), f"{v:0.1f}", 120, T.WHITE, 1, centre=True); _txt(d, ctx, (cx, cy + ctx.px(52)), "SECONDS" if top < 60 else "MIN", 34, T.ORANGE, 1, head=False, centre=True)
    x0, y0, gap = int(ctx.W * 0.47), int(ctx.H * 0.5 - (len(its) - 1) * ctx.px(70)), ctx.px(140)
    for i, it in enumerate(its):
        p = (t - it["at"]) / 0.45
        if p <= 0: continue
        dim = 1.0 if i == k else 0.45; y = y0 + i * gap; off = int((1 - T.ease_out(p)) * 40 * ctx.S)
        room = ctx.W - (x0 + ctx.px(190)) - ctx.px(110); size = 52
        while size > 30 and D._text_w(d, it["text"], ctx.font(T.HEAD_FONT, size), ctx.px(1)) > room: size -= 4      # a long phrase shrinks to fit, never runs off the frame
        _txt(d, ctx, (x0 + off, y - ctx.px(40)), it["mark"], 64, T.ORANGE, min(1, p * 1.6) * dim); _txt(d, ctx, (x0 + ctx.px(190) + off, y - ctx.px(30)), it["text"], size, T.WHITE, min(1, p * 1.6) * dim)

def mistake(cv: Image.Image, ctx: D.Ctx, mk: dict, t: float) -> None:
    """The mistake in a red panel with a cross slashed over it as it is named; the fix, when the narration gives one, in a green panel with a tick."""
    d = ImageDraw.Draw(cv, "RGBA"); sides = [("wrong", mk["wrong"])] + ([("right", mk["right"])] if mk.get("right") else []); pw, ph = int(ctx.W * 0.40), int(ctx.H * 0.40); y0 = int(ctx.H * 0.28)
    xs = [int(ctx.W * 0.07), int(ctx.W * 0.53)] if len(sides) == 2 else [int((ctx.W - pw) / 2)]
    for (kind, s), x0 in zip(sides, xs):
        p = (t - s["at"]) / 0.5
        if p <= 0: continue
        e = T.ease_back(min(1.0, p)); col = RED if kind == "wrong" else T.GREEN; a = min(1, p * 1.6) * (0.55 if kind == "wrong" and len(sides) == 2 and t >= sides[1][1]["at"] + 0.3 else 1.0)
        yy = y0 + int((1 - min(1, e)) * 50 * ctx.S); d.rounded_rectangle((x0, yy, x0 + pw, yy + ph), radius=ctx.px(24), fill=col + (int(26 * a),), outline=col + (int(255 * a),), width=ctx.px(5))
        _txt(d, ctx, (x0 + pw / 2, yy + ctx.px(24)), (mk.get("labels") or ("WRONG", "RIGHT"))[0 if kind == "wrong" else 1], 34, col, a, head=False, centre=True)
        f = ctx.font(T.HEAD_FONT, 62); lines = _wrap_lines(d, s["text"], f, pw - ctx.px(80)); ly = yy + (ph - len(lines) * ctx.px(72)) // 2 + ctx.px(20)
        for ln in lines: _txt(d, ctx, (x0 + pw / 2, ly), ln, 62, T.WHITE, a, centre=True); ly += ctx.px(72)
        q = T.ease_out((t - s["at"] - 0.35) / 0.35); m = ctx.px(46); w = ctx.px(12)
        if q > 0 and kind == "wrong":      # the cross slashes on, stroke by stroke
            d.line((x0 + pw - m - ctx.px(60), yy + m, x0 + pw - m - ctx.px(60) + ctx.px(60) * min(1, q * 2), yy + m + ctx.px(60) * min(1, q * 2)), fill=RED + (255,), width=w)
            if q > 0.5: qq = (q - 0.5) * 2; d.line((x0 + pw - m, yy + m, x0 + pw - m - ctx.px(60) * qq, yy + m + ctx.px(60) * qq), fill=RED + (255,), width=w)
        if q > 0 and kind == "right":
            bx, by = x0 + pw - m - ctx.px(60), yy + m + ctx.px(30); d.line((bx, by, bx + ctx.px(22) * min(1, q * 2), by + ctx.px(26) * min(1, q * 2)), fill=T.GREEN + (255,), width=w)
            if q > 0.5: qq = (q - 0.5) * 2; d.line((bx + ctx.px(22), by + ctx.px(26), bx + ctx.px(22) + ctx.px(44) * qq, by + ctx.px(26) - ctx.px(56) * qq), fill=T.GREEN + (255,), width=w)

def slider(cv: Image.Image, ctx: D.Ctx, sl: dict, t: float) -> None:
    """Make it easier or harder: a track from EASIER to HARDER whose knob slides to each end as that version is said, the version written under its end."""
    d = ImageDraw.Draw(cv, "RGBA"); x0, x1, y = int(ctx.W * 0.14), int(ctx.W * 0.86), int(ctx.H * 0.46); a = min(1.0, t / 0.4)
    d.rounded_rectangle((x0, y - ctx.px(8), x1, y + ctx.px(8)), radius=ctx.px(8), fill=T.DIM + (int(255 * a),))
    _txt(d, ctx, (x0, y - ctx.px(96)), "EASIER", 40, T.GREEN, a, head=False); _txt(d, ctx, (x1 - ctx.px(170), y - ctx.px(96)), "HARDER", 40, RED, a, head=False)
    pos = 0.5
    for key, end in (("easier", 0.0), ("harder", 1.0)):
        s = sl.get(key)
        if not s or t < s["at"]: continue
        q = T.ease_in_out(min(1.0, (t - s["at"]) / 0.6)); pos = pos + (end - pos) * q
        f = ctx.font(T.HEAD_FONT, 54); lines = _wrap_lines(d, s["text"], f, (x1 - x0) * 0.45); ly = y + ctx.px(60)
        for ln in lines: _txt(d, ctx, (x0 if end == 0 else x1 - D._text_w(d, ln, f, ctx.px(1)), ly), ln, 54, T.WHITE, min(1, (t - s["at"]) / 0.4)); ly += ctx.px(64)
    kx = x0 + (x1 - x0) * pos; kr = ctx.px(30); col = tuple(int(g + (r - g) * pos) for g, r in zip(T.GREEN, RED))
    d.rectangle((x0, y - ctx.px(8), kx, y + ctx.px(8)), fill=col + (int(255 * a),)); d.ellipse((kx - kr, y - kr, kx + kr, y + kr), fill=T.P(20, 20, 22, 255), outline=col + (255,), width=ctx.px(6))

def dial(cv: Image.Image, ctx: D.Ctx, dl: dict, t: float) -> None:
    """How hard: a gauge from green to red whose needle swings up to the stated effort, the number under it."""
    d = ImageDraw.Draw(cv, "RGBA"); cx, cy, r = int(ctx.W * 0.30), int(ctx.H * 0.62), int(ctx.H * 0.30); a = min(1.0, t / 0.4)
    for i in range(40):      # the scale: green to red
        f0 = i / 40; col = tuple(int(g + (rr - g) * f0) for g, rr in zip(T.GREEN, RED)); a0 = math.radians(180 + 180 * f0); a1 = math.radians(180 + 180 * (i + 0.8) / 40)
        d.arc((cx - r, cy - r, cx + r, cy + r), math.degrees(a0), math.degrees(a1), fill=col + (int(255 * a),), width=ctx.px(22))
    p, land_t = _roll(t, dl["at"]); v = dl["value"] * T.ease_in_out(p); ang = math.radians(180 + 180 * v / dl["max"])      # the needle swings up from the scene's start and lands on its word
    d.line((cx, cy, cx + (r - ctx.px(40)) * math.cos(ang), cy + (r - ctx.px(40)) * math.sin(ang)), fill=T.WHITE + (255,), width=ctx.px(8)); d.ellipse((cx - ctx.px(16), cy - ctx.px(16), cx + ctx.px(16), cy + ctx.px(16)), fill=T.WHITE + (255,))
    land = t - land_t
    if 0 <= land < 0.7: q = T.ease_out(land / 0.7); rr = r * (1.0 + 0.15 * q); d.arc((cx - rr, cy - rr, cx + rr, cy + rr), 180, 360, fill=T.ORANGE + (int(200 * (1 - q)),), width=ctx.px(6))
    _txt(d, ctx, (cx, cy + ctx.px(26)), f"{v:.0f}", 120, T.ORANGE if land >= 0 else T.WHITE, a, centre=True); _txt(d, ctx, (cx, cy + ctx.px(160)), dl["label"], 34, T.GREY, a, head=False, centre=True)

def study(cv: Image.Image, ctx: D.Ctx, st: dict, t: float) -> None:
    """The evidence: a stack of papers that fans in, its count rolling up to the stated number, what was studied under it."""
    d = ImageDraw.Draw(cv, "RGBA"); cx, cy = int(ctx.W * 0.28), int(ctx.H * 0.52); w, h = int(ctx.H * 0.40), int(ctx.H * 0.52); p = t / 0.8; rp, _land = _roll(t, st["at"])      # papers fan in from the first frame, the count lands on its word
    for i in range(3, -1, -1):      # the papers fan in, back to front
        q = T.ease_out(min(1.0, max(0.0, p - 0.12 * i))); ang = (i - 1.5) * 4 * q; off = (i - 1.5) * ctx.px(26) * q
        card = Image.new("RGBA", (w, h), (0, 0, 0, 0)); dc = ImageDraw.Draw(card); cat = T.THEME in T.LIGHT; qa = int(255 * min(1, q * 2))      # cat: cream notes with peach lines, the front one taped on
        dc.rounded_rectangle((0, 0, w - 1, h - 1), radius=ctx.px(22 if cat else 16), fill=((255, 251, 244) if cat else (236, 232, 224)) + (qa,), outline=(T.DIM + (qa,)) if cat else None, width=ctx.px(3) if cat else 0)
        for k in range(3): dc.rounded_rectangle((ctx.px(30), ctx.px(90) + k * ctx.px(30), w - ctx.px(30 + (k % 3) * 40), ctx.px(100) + k * ctx.px(30)), radius=ctx.px(5), fill=(((180, 222, 220) if T.THEME == "elder" else (250, 200, 176)) if cat else (170, 165, 158)) + (qa,))
        if cat and i == 0: dc.rectangle((w // 2 - ctx.px(60), 0, w // 2 + ctx.px(60), ctx.px(30)), fill=T.ORANGE + (int(qa * 0.55),))      # a strip of tape on the front note
        card = card.rotate(ang, resample=Image.BICUBIC, expand=True); cv.paste(card, (int(cx - card.width / 2 + off), int(cy - card.height / 2)), card)
    d = ImageDraw.Draw(cv, "RGBA"); e = T.ease_in_out(rp); v = st["value"] * e
    if st.get("year"): import datetime; y0 = datetime.date.today().year; v = y0 + (st["value"] - y0) * e      # a year rolls back from today to the one stated
    _txt(d, ctx, (cx, cy - h / 2 + ctx.px(24)), st["kind"], 32, T.ORANGE_DEEP, min(1, p * 2), head=False, centre=True)
    _txt(d, ctx, (cx, cy - ctx.px(10)), f"{v:.0f}" if st.get("year") else f"{v:,.0f}", 130, T.WHITE if T.THEME in T.LIGHT else (24, 24, 26), min(1, p * 2), centre=True); _txt(d, ctx, (cx, cy + ctx.px(140)), st["noun"], 40, T.SOFT_WHITE if T.THEME in T.LIGHT else (60, 60, 62), min(1, p * 2), head=False, centre=True)
    if T.THEME == "cat" and rp >= 1: sp = T.ease_back(min(1.0, (t - _land - 0.2) / 0.35)); D.paw(d, cx + w * 0.30, cy + h * 0.36, ctx.px(26) * max(0.0, sp), T.ORANGE + (int(200 * min(1.0, max(0.0, sp))),)) if sp > 0 else None      # the paw stamp lands once the number has rolled in

def graph(cv: Image.Image, ctx: D.Ctx, gr: dict, t: float) -> None:
    """A change over time: axes draw on, then the line draws itself, bending up, down or level at each word that says so; a dot rides its head and pulses at each bend."""
    d = ImageDraw.Draw(cv, "RGBA"); x0, x1, y0, y1 = int(ctx.W * 0.07), int(ctx.W * 0.54), int(ctx.H * 0.24), int(ctx.H * 0.76); a = min(1.0, t / 0.4)
    ax = T.ease_out(t / 0.6); d.line((x0, y1, x0 + (x1 - x0) * ax, y1), fill=T.GREY + (int(255 * a),), width=ctx.px(4)); d.line((x0, y1, x0, y1 - (y1 - y0) * ax), fill=T.GREY + (int(255 * a),), width=ctx.px(4))
    _txt(d, ctx, (x0 + ctx.px(18), y0 - ctx.px(58)), gr["label"], 40, T.ORANGE, a, head=False); _txt(d, ctx, (x1 - ctx.px(110), y1 + ctx.px(18)), "TIME", 30, T.GREY, a, head=False)
    segs = gr["segs"]; n = len(segs); step = (x1 - x0 - ctx.px(40)) / n; lvl = {"up": -1, "down": 1, "flat": 0}
    y = (y0 + y1) / 2 + (0.18 * (y1 - y0) if segs[0]["dir"] == "up" else -0.18 * (y1 - y0) if segs[0]["dir"] == "down" else 0); pts = [(x0 + ctx.px(20), y)]
    for s in segs: y = max(y0 + ctx.px(30), min(y1 - ctx.px(30), y + lvl[s["dir"]] * 0.34 * (y1 - y0) / max(1, n - 0.5))); pts.append((pts[-1][0] + step, y))
    head = pts[0]; ats = []
    for s in segs: ats.append(max(s["at"], ats[-1] + 0.7) if ats else s["at"])      # bends said close together draw one after the other, never two pieces at once
    for i, s in enumerate(segs):
        s = dict(s, at=ats[i]); q = T.ease_in_out((t - s["at"]) / 0.7)
        if q <= 0: break
        (ax_, ay), (bx, by) = pts[i], pts[i + 1]; k = 12; line = [(ax_ + (bx - ax_) * j / k * q, ay + (by - ay) * (0.5 - 0.5 * math.cos(math.pi * j / k * q))) for j in range(k + 1)]      # an eased bend, not a corner
        col = T.GREEN if s["dir"] == "up" else RED if s["dir"] == "down" else T.SOFT_WHITE; d.line(line, fill=col + (255,), width=ctx.px(9), joint="curve"); head = line[-1]
        land = t - s["at"] - 0.7
        if 0 <= land < 0.6: qq = T.ease_out(land / 0.6); rr = ctx.px(14 + 30 * qq); d.ellipse((bx - rr, by - rr, bx + rr, by + rr), outline=col + (int(220 * (1 - qq)),), width=ctx.px(4))
    if t >= segs[0]["at"]: r = ctx.px(13); d.ellipse((head[0] - r, head[1] - r, head[0] + r, head[1] + r), fill=T.WHITE + (255,))
    for key, xy in (("from", pts[0]), ("to", pts[-1])):
        if gr.get(key) and t >= segs[0 if key == "from" else -1]["at"] + 0.5: _txt(d, ctx, (xy[0], xy[1] - ctx.px(90)), gr[key], 60, T.WHITE, min(1, (t - segs[0 if key == "from" else -1]["at"] - 0.5) / 0.3), centre=True)

def bars(cv: Image.Image, ctx: D.Ctx, br: dict, t: float) -> None:
    """Stated numbers as bars that grow to their value (the biggest in orange), or a stated share as a grid of dots lit one by one."""
    d = ImageDraw.Draw(cv, "RGBA")
    if br["mode"] == "dots":
        of = int(br["of"]); cols = 10 if of > 10 else of; rows = math.ceil(of / cols); sz = min(int(ctx.W * 0.46) // cols, int(ctx.H * 0.48) // max(1, rows)); x0 = int(ctx.W * 0.30 - cols * sz / 2); y0 = int(ctx.H * 0.50 - rows * sz / 2); lit = int(round(br["lit"]))
        for i in range(of):
            p = T.ease_back((t - 0.02 * i) / 0.35); r = int(sz * 0.36 * min(1.0, max(0.0, p)))
            if r <= 0: continue
            on = i < lit and t >= br["at"] + 0.04 * i; cx, cy = x0 + (i % cols) * sz + sz // 2, y0 + (i // cols) * sz + sz // 2; d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(T.ORANGE if on else T.DIM) + (255,))
        a = min(1.0, max(0.0, (t - br["at"]) / 0.4)); _txt(d, ctx, (ctx.W * 0.30, y0 - ctx.px(150)), br["label"], 110, T.ORANGE, a, centre=True); _txt(d, ctx, (ctx.W * 0.30, y0 + rows * sz + ctx.px(26)), br["noun"], 38, T.GREY, a, head=False, centre=True)
        return
    its = br["items"]; top = max(i["value"] for i in its); n = len(its); x0, bw, gap, base, hmax = int(ctx.W * 0.08), int(ctx.W * 0.36 / n), int(ctx.W * 0.10 / max(1, n - 1)) if n > 1 else 0, int(ctx.H * 0.78), int(ctx.H * 0.46)
    d.line((x0 - ctx.px(20), base, x0 + n * bw + (n - 1) * gap + ctx.px(20), base), fill=T.GREY + (int(255 * min(1, t / 0.4)),), width=ctx.px(4))
    for k, it in enumerate(its):
        q = T.ease_out((t - it["at"]) / 0.8)
        if q <= 0: continue
        x = x0 + k * (bw + gap); h = int(hmax * it["value"] / top * q); col = T.ORANGE if it["value"] == top else T.SOFT_WHITE
        d.rounded_rectangle((x, base - h, x + bw, base), radius=ctx.px(10), fill=col + (255,)); _txt(d, ctx, (x + bw / 2, base - h - ctx.px(84)), it["text"], 64, col, min(1, q * 2), centre=True)
        if it["label"]: _txt(d, ctx, (x + bw / 2, base + ctx.px(18)), it["label"], 30, T.GREY, min(1, q * 2), head=False, centre=True)

def calendar(cv: Image.Image, ctx: D.Ctx, cl: dict, t: float) -> None:
    """A week that fills in: seven day cells, each training day lit (with a tick) as it is said, the rest days staying dark, and the total under it."""
    d = ImageDraw.Draw(cv, "RGBA"); n = 7; cw = int(ctx.W * 0.105); gap = int(ctx.W * 0.012); x0 = int((ctx.W - n * cw - (n - 1) * gap) / 2); y0 = int(ctx.H * 0.32); ch = int(ctx.H * 0.30)
    on = {x["day"]: x["at"] for x in cl["days"]}
    for i, lab in enumerate("MON TUE WED THU FRI SAT SUN".split()):
        p = T.ease_back((t - 0.06 * i) / 0.4); yy = y0 + int((1 - min(1.0, max(0.0, p))) * 40 * ctx.S); a = min(1.0, max(0.0, p * 1.5)); x = x0 + i * (cw + gap)
        q = T.ease_out((t - on[i]) / 0.4) if i in on else 0.0; col = tuple(int(c0 + (c1 - c0) * q) for c0, c1 in zip((24, 24, 27), T.ORANGE))
        d.rounded_rectangle((x, yy, x + cw, yy + ch), radius=ctx.px(18), fill=col + (int(255 * a),), outline=(T.ORANGE if i in on else T.DIM) + (int(255 * a),), width=ctx.px(3))
        _txt(d, ctx, (x + cw / 2, yy + ctx.px(22)), lab, 34, (20, 20, 22) if q > 0.5 else T.GREY, a, head=False, centre=True)
        if q > 0:      # the tick draws on
            bx, by, s = x + cw / 2 - ctx.px(34), yy + ch * 0.58, ctx.px(1); d.line((bx, by, bx + 24 * s * min(1, q * 2), by + 26 * s * min(1, q * 2)), fill=T.P(20, 20, 22, 255), width=ctx.px(10))
            if q > 0.5: qq = (q - 0.5) * 2; d.line((bx + 24 * s, by + 26 * s, bx + 24 * s + 46 * s * qq, by + 26 * s - 56 * s * qq), fill=T.P(20, 20, 22, 255), width=ctx.px(10))
    last = max(on.values()) if on else 0.0; _txt(d, ctx, (ctx.W / 2, y0 + ch + ctx.px(46)), cl["total"], 58, T.WHITE, (t - last - 0.3) / 0.4, centre=True)

def result(cv: Image.Image, ctx: D.Ctx, rs: dict, t: float) -> None:
    """A result board: one row per band the narration states, revealed as it is said with what it means; the band being said is lit, the ones before step back."""
    d = ImageDraw.Draw(cv, "RGBA"); tiers = rs["tiers"]; n = len(tiers); x0, x1 = int(ctx.W * 0.16), int(ctx.W * 0.84); rh = ctx.px(128); y0 = int(ctx.H * 0.48 - n * rh / 2)
    _txt(d, ctx, (x0, y0 - ctx.px(70)), "YOUR RESULT", 34, T.ORANGE, t / 0.4, head=False); live = [i for i, tr in enumerate(tiers) if t >= tr["at"]]; k = live[-1] if live else -1
    for i, tr in enumerate(tiers):
        y = y0 + i * rh; col = tuple(int(g + (r - g) * (i / max(1, n - 1))) for g, r in zip(RED, T.GREEN)); p = (t - tr["at"]) / 0.45
        d.rounded_rectangle((x0, y, x1, y + rh - ctx.px(16)), radius=ctx.px(18), fill=(255, 255, 255, 10), outline=(col if p > 0 else T.DIM) + (255 if p > 0 else 120,), width=ctx.px(3))
        if p <= 0: _txt(d, ctx, (x0 + ctx.px(40), y + ctx.px(30)), "? ? ?", 44, T.DIM, 1, head=False); continue      # a band not yet said waits, locked
        a = min(1.0, p * 1.6) * (1.0 if i == k else 0.5); e = T.ease_back(min(1.0, p)); mw = ctx.px(380); w = int(mw * min(1.0, e)); size = 52
        while size > 30 and D._text_w(d, tr["mark"], ctx.font(T.HEAD_FONT, size), ctx.px(1)) > mw - ctx.px(50): size -= 4      # the band's mark always fits its block
        d.rounded_rectangle((x0, y, x0 + w, y + rh - ctx.px(16)), radius=ctx.px(18), fill=col + (int(235 * a),))
        _txt(d, ctx, (x0 + ctx.px(26), y + ctx.px(26) + (52 - size) * ctx.S / 2), tr["mark"], size, (16, 16, 18), a); _txt(d, ctx, (x0 + mw + ctx.px(40) + int((1 - T.ease_out(p)) * 30 * ctx.S), y + ctx.px(26)), tr["text"], 58, T.WHITE, a)

def warning(cv: Image.Image, ctx: D.Ctx, wn: dict, t: float) -> None:
    """Safety rules: a warning card per rule, dropping in on the stack as it is said, each with a warning triangle; the rule being said is bright."""
    d = ImageDraw.Draw(cv, "RGBA"); rules = wn["rules"]; n = len(rules); cw, ch = int(ctx.W * 0.66), ctx.px(150); x0 = (ctx.W - cw) // 2; y0 = int(ctx.H * 0.46 - n * (ch + ctx.px(24)) / 2)
    _txt(d, ctx, (ctx.W / 2, y0 - ctx.px(80)), "BE SAFE", 40, (250, 196, 40), t / 0.4, head=False, centre=True)
    for i, r in enumerate(rules):
        p = (t - r["at"]) / 0.45
        if p <= 0: continue
        e = T.ease_back(min(1.0, p)); y = y0 + i * (ch + ctx.px(24)) - int((1 - min(1, e)) * 60 * ctx.S); a = min(1.0, p * 1.6) * (0.5 if i + 1 < n and t >= rules[i + 1]["at"] else 1.0); amber = (250, 196, 40)
        d.rounded_rectangle((x0, y, x0 + cw, y + ch), radius=ctx.px(20), fill=(40, 30, 8, int(230 * a)), outline=amber + (int(255 * a),), width=ctx.px(4))
        tx, ty, s = x0 + ctx.px(46), y + ch // 2, ctx.px(44); d.polygon([(tx + s, ty - s), (tx + 2 * s, ty + s * 0.8), (tx, ty + s * 0.8)], fill=amber + (int(255 * a),))
        _txt(d, ctx, (tx + s - ctx.px(6), ty - ctx.px(26)), "!", 52, (30, 22, 4), a); _txt(d, ctx, (tx + 2 * s + ctx.px(40), ty - ctx.px(34)), r["text"], 56, T.WHITE, a)

def engage(cv: Image.Image, ctx: D.Ctx, en: dict, t: float) -> None:
    """The call to action as the screen it asks for: a comment box with typing dots, then the asked-for comment typing in; or a like / subscribe button that is pressed on its word."""
    d = ImageDraw.Draw(cv, "RGBA"); at = en["at"]; a = min(1.0, t / 0.4)
    if en["kind"] == "comment":
        bw, bh = int(ctx.W * 0.62), ctx.px(230); x0, y0 = (ctx.W - bw) // 2, int(ctx.H * 0.36); e = T.ease_back(min(1.0, t / 0.5)); y0 += int((1 - e) * 40 * ctx.S)
        d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=ctx.px(22), fill=T.P(28, 28, 31, int(255 * a)), outline=T.DIM + (int(255 * a),), width=ctx.px(3))
        r = ctx.px(40); ax, ay = x0 + ctx.px(40), y0 + ctx.px(40)
        if T.THEME == "cat":      # the avatar is a cat: two ears on the circle
            for sx in (-1, 1): ex = ax + r + sx * r * 0.62; d.polygon([(ex - r * 0.42, ay + r * 0.45), (ex + r * 0.42, ay + r * 0.45), (ex + sx * r * 0.12, ay - r * 0.55)], fill=T.ORANGE + (int(255 * a),))
        d.ellipse((ax, ay, ax + 2 * r, ay + 2 * r), fill=T.ORANGE + (int(255 * a),)); _txt(d, ctx, (x0 + ctx.px(150), y0 + ctx.px(44)), "YOU", 30, T.GREY, a, head=False)
        txt = en["text"]; k = int((t - at - 0.35) / 0.03)
        if t < at + 0.35:      # typing dots before the words come
            for j in range(3): q = 0.5 + 0.5 * math.sin((t * 6) - j * 0.9); rr = ctx.px(9); cx, cy = x0 + ctx.px(170) + j * ctx.px(34), y0 + ctx.px(130); d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=T.SOFT_WHITE + (int(255 * a * q),))
        else:
            typed = txt[:max(0, min(len(txt), k))]; f = ctx.font(T.HEAD_FONT, 50); lines = _wrap_lines(d, typed, f, bw - ctx.px(200)); yy = y0 + ctx.px(96)
            for ln in lines[:2]: _txt(d, ctx, (x0 + ctx.px(150), yy), ln, 50, T.WHITE, 1); yy += ctx.px(60)
            if len(typed) == len(txt) and txt: hp = T.ease_out((t - at - 0.35 - len(txt) * 0.03) / 0.3); d.rectangle((x0, y0 + bh - ctx.px(10), x0 + int(bw * hp), y0 + bh), fill=T.ORANGE + (255,))
        _txt(d, ctx, (ctx.W / 2, y0 + bh + ctx.px(40)), "COMMENT BELOW", 34, T.ORANGE, a, head=False, centre=True)
        return
    if en["kind"] == "link":      # "it's linked below": the link button drops in with an arrow pointing down to the description
        e = T.ease_back(min(1.0, max(0.0, (t - at) / 0.5))); f = ctx.font(T.HEAD_FONT, 60); label = "LINK IN DESCRIPTION"; w = D._text_w(d, label, f, ctx.px(1)) + ctx.px(120); h = ctx.px(120)
        cx, cy = ctx.W / 2, ctx.H * 0.42 - (1 - e) * ctx.px(60); d.rounded_rectangle((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), radius=h // 2, fill=T.P(28, 28, 31, int(255 * a)), outline=T.ORANGE + (int(255 * min(1.0, e)),), width=ctx.px(4))
        _txt(d, ctx, (cx, cy - ctx.px(38)), label, 60, T.WHITE, a, centre=True); bob = math.sin(t * 5) * ctx.px(10); ay = cy + h / 2 + ctx.px(60) + bob; s_ = ctx.px(34)
        if t >= at: d.polygon([(cx - s_, ay), (cx + s_, ay), (cx, ay + s_ * 1.2)], fill=T.ORANGE + (255,)); d.rectangle((cx - ctx.px(9), ay - ctx.px(60), cx + ctx.px(9), ay), fill=T.ORANGE + (255,))
        return
    on = t >= at + 0.25; press = 1.0 - 0.12 * math.sin(math.pi * min(1.0, max(0.0, (t - at) / 0.25))) if t >= at else 1.0
    label = ("LIKED" if on else "LIKE") if en["kind"] == "like" else ("SUBSCRIBED" if on else "SUBSCRIBE"); f = ctx.font(T.HEAD_FONT, 72); w = (D._text_w(d, label, f, ctx.px(1)) + ctx.px(140)) * press; h = ctx.px(140) * press
    cx, cy = ctx.W / 2, ctx.H * 0.48; col = (T.ORANGE if en["kind"] == "like" else RED) if not on or en["kind"] == "like" else T.DIM
    d.rounded_rectangle((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), radius=int(h / 2), fill=col + (int(255 * a),)); _txt(d, ctx, (cx, cy - ctx.px(44) * press), label, int(72 * press), T.WHITE, a, centre=True)
    if on and en["kind"] == "subscribe":      # the bell rings once beside it
        sw = math.sin((t - at) * 18) * max(0.0, 1 - (t - at - 0.25) / 0.8) * 18; bx, by = cx + w / 2 + ctx.px(80), cy; s = ctx.px(34)
        bell = Image.new("RGBA", (4 * s, 4 * s), (0, 0, 0, 0)); db = ImageDraw.Draw(bell); db.pieslice((s, s // 2, 3 * s, 3 * s), 180, 360, fill=T.WHITE + (255,)); db.rectangle((s, int(1.75 * s), 3 * s, int(2.9 * s)), fill=T.WHITE + (255,)); db.ellipse((int(1.7 * s), int(2.8 * s), int(2.3 * s), int(3.4 * s)), fill=T.WHITE + (255,))
        bell = bell.rotate(sw, resample=Image.BICUBIC); cv.paste(bell, (int(bx - 2 * s), int(by - 2 * s)), bell)
    if on: q = T.ease_out((t - at - 0.25) / 0.6); rr = h / 2 * (1 + 0.5 * q); d.rounded_rectangle((cx - w / 2 - (rr - h / 2), cy - rr, cx + w / 2 + (rr - h / 2), cy + rr), radius=int(rr), outline=col + (int(200 * (1 - q)),), width=ctx.px(5))

# ---------------------------------------------------------------- Full Guide blueprint chrome (blueprint.py)
def teaser(cv: Image.Image, ctx: D.Ctx, name: str, t: float) -> None:
    """The last seconds of a unit: a NEXT tag and the next unit's name slide in at the top right (clear of the caption strip)."""
    if t < 0: return
    d = ImageDraw.Draw(cv, "RGBA"); e = T.ease_out(t / 0.5); a = min(1.0, t / 0.3); f = ctx.font(T.HEAD_FONT, 46); w = D._text_w(d, name, f, ctx.px(1)) + ctx.px(200); x = ctx.W - ctx.px(70) - w + int((1 - e) * 80 * ctx.S); y = int(ctx.H * 0.05)
    d.rounded_rectangle((x, y, x + w, y + ctx.px(84)), radius=ctx.px(16), fill=T.P(14, 14, 16, int(230 * a)), outline=T.ORANGE + (int(255 * a),), width=ctx.px(3))
    d.rounded_rectangle((x + ctx.px(12), y + ctx.px(14), x + ctx.px(150), y + ctx.px(70)), radius=ctx.px(10), fill=T.ORANGE + (int(255 * a),))
    _txt(d, ctx, (x + ctx.px(81), y + ctx.px(22)), "NEXT", 32, (16, 16, 18), a, head=False, centre=True); _txt(d, ctx, (x + ctx.px(176), y + ctx.px(16)), name, 46, T.WHITE, a)

def lock(cv: Image.Image, ctx: D.Ctx, t: float) -> None:
    """The curiosity lock on an early test: a padlock and RESULT AT THE END at the top right, from the word that sets the test."""
    if t < 0: return
    d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, t / 0.3); e = T.ease_back(min(1.0, t / 0.45)); x, y = int(ctx.W * 0.66), int(ctx.H * 0.07); s = ctx.px(22) * min(1.0, e)
    d.arc((x - s * 0.7, y - s * 1.3, x + s * 0.7, y + s * 0.2), 180, 360, fill=T.ORANGE + (int(255 * a),), width=ctx.px(5)); d.rounded_rectangle((x - s, y - s * 0.4, x + s, y + s * 1.1), radius=ctx.px(4), fill=T.ORANGE + (int(255 * a),))
    _txt(d, ctx, (x + ctx.px(46), y - ctx.px(18)), "RESULT AT THE END", 32, T.WHITE, a, head=False)

def safety_chip(cv: Image.Image, ctx: D.Ctx, rule: str, t: float) -> None:
    """The script's own safety rule as a small amber chip at the bottom left, through the units."""
    d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, t / 0.4) * 0.85; amber = (250, 196, 40); x, y = ctx.px(60), int(ctx.H * 0.93); s = ctx.px(13)
    d.polygon([(x + s, y), (x + 2 * s, y + 1.7 * s), (x, y + 1.7 * s)], fill=amber + (int(255 * a),)); _txt(d, ctx, (x + 2 * s + ctx.px(14), y - ctx.px(3)), f"BE SAFE · {rule}", 24, amber, a, head=False)

def question(cv: Image.Image, ctx: D.Ctx, qn: dict, t: float) -> None:
    """A question asked for the viewer, as a chat bubble: an avatar, typing dots, the question typing in, then a marker swiped behind its key words."""
    d = ImageDraw.Draw(cv, "RGBA"); at = qn["at"]; a = min(1.0, t / 0.4); f = ctx.font(T.HEAD_FONT, 66); bw = int(ctx.W * 0.60); lines = _wrap_lines(d, qn["text"], f, bw - ctx.px(110)); bh = len(lines) * ctx.px(84) + ctx.px(90)
    x0, y0 = int(ctx.W * 0.24), int(ctx.H * 0.46 - bh / 2); e = T.ease_back(min(1.0, t / 0.5)); y0 += int((1 - e) * 50 * ctx.S); r = ctx.px(52)
    d.ellipse((x0 - ctx.px(150), y0 + bh - 2 * r, x0 - ctx.px(150) + 2 * r, y0 + bh), fill=T.SOFT_WHITE + (int(255 * a),)); d.ellipse((x0 - ctx.px(150) + r * 0.55, y0 + bh - 1.6 * r, x0 - ctx.px(150) + r * 1.45, y0 + bh - 0.75 * r), fill=(60, 60, 64, int(255 * a)))
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=ctx.px(34), fill=T.P(34, 34, 38, int(255 * a))); d.polygon([(x0, y0 + bh - ctx.px(60)), (x0 - ctx.px(30), y0 + bh), (x0 + ctx.px(50), y0 + bh - ctx.px(20))], fill=T.P(34, 34, 38, int(255 * a)))
    if t < at + 0.45:
        for j in range(3): q = 0.5 + 0.5 * math.sin(t * 6 - j * 0.9); rr = ctx.px(11); cx, cy = x0 + ctx.px(70) + j * ctx.px(40), y0 + bh / 2; d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=T.SOFT_WHITE + (int(255 * a * q),))
        return
    k = int((t - at - 0.45) / 0.03); yy = y0 + ctx.px(45); kp = T.ease_out((t - at - 0.45 - len(qn["text"]) * 0.03 - 0.1) / 0.45)
    for ln in lines:
        shown = ln[:max(0, k)]; k -= len(ln) + 1; i = ln.find(qn["key"]) if qn.get("key") else -1
        if kp > 0 and i >= 0:      # the marker swipes behind the key words once the question is typed
            mx = x0 + ctx.px(55) + D._text_w(d, ln[:i], f, ctx.px(1)); mw = D._text_w(d, qn["key"], f, ctx.px(1)); d.rectangle((mx - ctx.px(8), yy + ctx.px(4), mx - ctx.px(8) + (mw + ctx.px(16)) * kp, yy + ctx.px(76)), fill=T.ORANGE_DEEP + (200,))
        if shown: _txt(d, ctx, (x0 + ctx.px(55), yy), shown, 66, T.WHITE, 1)
        yy += ctx.px(84)

# Cards from the arm-wrestling study (docs/rep_theory/STUDY_tendons_arm_wrestling.md, sections 3-5): each one acts out a sentence shape any fitness script has.

def _dashed_box(d, box, col, width, dash):
    x0, y0, x1, y1 = box
    for a, b, horiz in ((x0, x1, True), (y0, y1, False)):
        p = a
        while p < b:
            q = min(b, p + dash)
            if horiz: d.line((p, y0, q, y0), fill=col, width=width); d.line((p, y1, q, y1), fill=col, width=width)
            else: d.line((x0, p, x0, q), fill=col, width=width); d.line((x1, p, x1, q), fill=col, width=width)
            p += dash * 2

def slots(cv: Image.Image, ctx: D.Ctx, sl: dict, t: float) -> None:
    """A spoken count ("four moments", "three mistakes"): the heading, N empty dashed slots, then each slot fills with its item card as the item is named;
    the item being said is lit, the ones before step back. Items not named in the scene are numbered."""
    d = ImageDraw.Draw(cv, "RGBA"); n = len(sl["items"]); a = min(1.0, (t - sl["at"] + 0.2) / 0.4)
    _txt(d, ctx, (ctx.W / 2, ctx.H * 0.20), sl["kicker"], 34, T.SOFT_WHITE, a, head=False, centre=True); _txt(d, ctx, (ctx.W / 2, ctx.H * 0.26), sl["title"], 92, T.WHITE, a, centre=True)
    bw = min(ctx.px(300), int(ctx.W * 0.82 / n) - ctx.px(30)); gap = ctx.px(30); x0 = (ctx.W - (n * bw + (n - 1) * gap)) / 2; y0 = int(ctx.H * 0.46); bh = int(bw * 0.95)
    live = [i for i, it in enumerate(sl["items"]) if t >= it["at"]]
    for i, it in enumerate(sl["items"]):
        box = (int(x0 + i * (bw + gap)), y0, int(x0 + i * (bw + gap) + bw), y0 + bh); p = (t - it["at"]) / 0.45
        if p <= 0: _dashed_box(d, box, (118, 118, 124, int(255 * a)), ctx.px(3), ctx.px(12)); continue      # an empty slot waiting for its item: visible, not black on black
        e = T.ease_back(min(1.0, p)); cur = live and i == live[-1]; s = 0.85 + 0.15 * e; cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2; w2, h2 = bw * s / 2, bh * s / 2
        d.rounded_rectangle((cx - w2, cy - h2, cx + w2, cy + h2), radius=ctx.px(14), fill=T.P(24, 24, 27, 255), outline=(T.RED if cur else (70, 70, 74)) + (255,), width=ctx.px(5 if cur else 3))
        dim = 1.0 if cur else 0.55
        _txt(d, ctx, (cx, cy - h2 + ctx.px(18)), f"{sl['noun']} {i + 1}", 26, T.GREY, dim, head=False, centre=True)
        f = ctx.font(T.HEAD_FONT, 38); lines = _wrap_lines(d, it["text"], f, bw - ctx.px(30))[:2] if it["text"] else []
        num = str(i + 1); _txt(d, ctx, (cx, cy - ctx.px(80) - (ctx.px(20) if len(lines) > 1 else 0)), num, 96, T.ORANGE if cur else T.SOFT_WHITE, dim * min(1, p * 2), centre=True)
        for k, ln in enumerate(lines): _txt(d, ctx, (cx, cy + h2 - ctx.px(58) - (len(lines) - 1 - k) * ctx.px(44)), ln, 38, T.WHITE, dim * min(1, p * 2), centre=True)

def race(cv: Image.Image, ctx: D.Ctx, rc: dict, t: float) -> None:
    """Fast against slow ("stiff tendons get it there fast ... late loses"): a start burst, two lanes to a finish line; the fast one arrives (green tick), the slow one is
    still on its way and gets LATE."""
    d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, t / 0.35); xs, xf = int(ctx.W * 0.22), int(ctx.W * 0.80); ys = (int(ctx.H * 0.42), int(ctx.H * 0.60)); h = ctx.px(46)
    _txt(d, ctx, (ctx.W / 2, ctx.H * 0.20), rc.get("title") or "", 40, T.SOFT_WHITE, a, head=False, centre=True)
    for x in (xs, xf):
        for y in range(ys[0] - ctx.px(60), ys[1] + ctx.px(60), ctx.px(18)): d.line((x, y, x, y + ctx.px(9)), fill=(T.GREY if x == xs else (250, 196, 40)) + (int(200 * a),), width=ctx.px(3))
    _txt(d, ctx, (xf, ys[0] - ctx.px(110)), rc.get("finish") or "FINISH", 28, (250, 196, 40), a, head=False, centre=True)
    st = (t - rc["at"]) / 0.3      # the start burst
    if st > 0: r = ctx.px(40) * T.ease_back(min(1.0, st)); cx, cy = xs - ctx.px(80), (ys[0] + ys[1]) / 2; d.regular_polygon((cx, cy, r), 12, fill=T.RED + (255,)); _txt(d, ctx, (cx, cy - ctx.px(20)), "GO", 34, T.WHITE, 1, centre=True)
    for k, (lane, y) in enumerate(zip((rc["fast"], rc["slow"]), ys)):
        d.rounded_rectangle((xs, y - h / 2, xf, y + h / 2), radius=h // 2, fill=T.P(30, 30, 33, int(255 * a)))
        reach = T.ease_in_out(max(0.0, (t - rc["at"]) / 0.7)) if k == 0 else 0.6 * T.ease_in_out(max(0.0, (t - rc["at"]) / 0.9)) + 0.4 * T.ease_in_out(max(0.0, (t - max(rc["at"] + 0.9, lane["at"])) / 0.8))      # the slow one is still on its way when the fast one has arrived
        x = xs + (xf - xs) * min(1.0, reach)
        if x > xs + h: d.rounded_rectangle((xs, y - h / 2, x, y + h / 2), radius=h // 2, fill=(T.RED if k == 0 else (150, 150, 150)) + (255,))
        lw = D._text_w(d, lane["text"], ctx.font(T.HEAD_FONT, 28), ctx.px(1)); _txt(d, ctx, (max(xs + ctx.px(20), x - lw - ctx.px(24)), y - ctx.px(17)), lane["text"], 28, T.WHITE if k == 0 else (30, 30, 32), 1 if x > xs + lw + ctx.px(40) else 0, head=False)
        if k == 0 and reach >= 1: p = min(1.0, (t - rc["at"] - 0.7) / 0.3); d.line((xf + ctx.px(26), y, xf + ctx.px(40), y + ctx.px(16) * p), fill=T.GREEN + (255,), width=ctx.px(7)); d.line((xf + ctx.px(40), y + ctx.px(16), xf + ctx.px(40) + ctx.px(26) * p, y - ctx.px(22) * p), fill=T.GREEN + (255,), width=ctx.px(7))
        if k == 1 and t >= lane["at"]: D.pill(cv, ctx, xf - ctx.px(150), y + ctx.px(40), "LATE", min(1.0, (t - lane["at"]) / 0.4))      # from the slow word on, also after the lane arrives

def formula(cv: Image.Image, ctx: D.Ctx, fm: dict, t: float) -> None:
    """A claim as a formula ("a big bicep can't save you" -> BIG BICEP ≠ SAFE... built only from the sentence's words): left side, the sign slams in, right side, each on its word."""
    d = ImageDraw.Draw(cv, "RGBA"); size = 120; parts = [(fm["a"]["text"], fm["a"]["at"], T.WHITE), (fm["sign"], fm["b"]["at"] - 0.15, T.RED if fm["sign"] == "≠" else T.ORANGE), (fm["b"]["text"], fm["b"]["at"], T.RED if fm["sign"] == "≠" else T.GREEN)]
    while True:      # the whole formula fits on one line: it shrinks before it runs off the frame
        f = ctx.font(T.HEAD_FONT, size); ws = [D._text_w(d, p[0], f, ctx.px(2)) for p in parts]; gap = ctx.px(40)
        if sum(ws) + 2 * gap <= ctx.W * 0.88 or size <= 56: break
        size -= 8
    x = (ctx.W - sum(ws) - 2 * gap) / 2; y = int(ctx.H * 0.40)
    for (text, at, col), w in zip(parts, ws):
        p = (t - at) / 0.4
        if p > 0:
            e = T.ease_back(min(1.0, p)); off = int((1 - e) * 50 * ctx.S); D.text_spaced(d, (x, y - off), text, f, col + (int(255 * min(1, p * 2)),), ctx.px(2))
        x += w + gap

def mechanism(cv: Image.Image, ctx: D.Ctx, mc: dict, t: float) -> None:
    """Muscle -> tendon -> bone ("the muscle pulls on a tendon and the tendon pulls on the bone"): an anchor, a red muscle, a tendon, a bone. Each part is labelled on its word;
    on "pull" the muscle shortens and glows, the tendon takes up its slack (stiff: at once; stretchy: wavy first) and the bone swings."""
    d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, t / 0.4); cy = int(ctx.H * 0.52); xw, xb = int(ctx.W * 0.16), int(ctx.W * 0.76)
    pull = T.ease_in_out(max(0.0, (t - mc["pull_at"]) / 0.8)) if mc.get("pull_at") is not None else 0.0
    m0, m1 = xw + ctx.px(30), int(ctx.W * 0.44) - int(ctx.px(60) * pull); mh = ctx.px(90) * (1 + 0.25 * pull)
    d.rectangle((xw - ctx.px(14), cy - ctx.px(140), xw + ctx.px(14), cy + ctx.px(140)), fill=(70, 70, 74, int(255 * a)))
    d.line((xw, cy, m0, cy), fill=(200, 200, 200, int(255 * a)), width=ctx.px(10))
    glow = int(80 + 175 * pull); d.ellipse((m0, cy - mh, m1, cy + mh), fill=(min(255, 160 + glow // 3), 34, 30, int(255 * a)))
    for k in range(1, 6): yy = cy - mh + 2 * mh * k / 6; d.arc((m0 + ctx.px(20), yy - ctx.px(30), m1 - ctx.px(20), yy + ctx.px(30)), 200, 340, fill=(120, 20, 20, int(200 * a)), width=ctx.px(2))
    ang = math.radians(-14 * pull); bx = xb + int(ctx.px(30) * math.sin(-ang)); by0, by1 = cy - ctx.px(170), cy + ctx.px(170)
    top = (bx + math.sin(ang) * ctx.px(170), by0); bot = (xb - math.sin(ang) * ctx.px(170), by1)
    d.line((top, bot), fill=(232, 226, 210, int(255 * a)), width=ctx.px(34))
    for (px_, py_) in (top, bot): d.ellipse((px_ - ctx.px(30), py_ - ctx.px(24), px_ + ctx.px(30), py_ + ctx.px(24)), fill=(232, 226, 210, int(255 * a)))
    tx1 = (top[0] + bot[0]) / 2 - ctx.px(20); slack = (1 - pull) if mc.get("stretchy") else max(0.0, 1 - pull * 3)
    pts = [(m1 + (tx1 - m1) * k / 40, cy + math.sin(k / 40 * math.pi * 5) * ctx.px(26) * slack) for k in range(41)]
    d.line(pts, fill=(T.RED if pull > 0.6 else (225, 215, 190)) + (int(255 * a),), width=ctx.px(12))
    for lab, x in (("muscle", (m0 + m1) / 2), ("tendon", (m1 + tx1) / 2), ("bone", xb)):
        at = mc["labels"].get(lab)
        if at is not None: _txt(d, ctx, (x, cy + ctx.px(210)), lab.upper(), 32, T.SOFT_WHITE, (t - at) / 0.4, head=False, centre=True)
    if pull > 0.05: D.pill(cv, ctx, (m0 + m1) / 2 - ctx.px(50), cy - mh - ctx.px(80), "PULLS", min(1.0, pull * 2))

def promise(cv: Image.Image, ctx: D.Ctx, pr: dict, t: float) -> None:
    """A payoff promised for later ("I'll show you what 8 out of 10 had in common"): M cells, N of them turn into red question marks on the number, then a lock closes over them."""
    if not pr["n"]:      # promised without a share: the board it will fill, blurred and locked, with what is promised under it
        d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, t / 0.35); bw, bh = int(ctx.W * 0.42), ctx.px(72); x0 = (ctx.W - bw) // 2; y0 = int(ctx.H * 0.30)
        for k, col in enumerate(((232, 64, 52), (250, 160, 40), (250, 210, 60), T.GREEN)):
            q = min(1.0, max(0.0, (t - pr["at"] - 0.12 * k) / 0.4)); d.rounded_rectangle((x0, y0 + k * (bh + ctx.px(16)), x0 + bw, y0 + k * (bh + ctx.px(16)) + bh), radius=ctx.px(12), fill=T.P(30, 30, 33, int(230 * a)), outline=col + (int(150 * q),), width=ctx.px(3))
            d.rectangle((x0 + ctx.px(24), y0 + k * (bh + ctx.px(16)) + ctx.px(26), x0 + int(bw * 0.45), y0 + k * (bh + ctx.px(16)) + ctx.px(44)), fill=col + (int(70 * q),))
        lk = (t - pr["at"] - 0.6) / 0.4
        if lk > 0:
            e = T.ease_back(min(1.0, lk)); x, yy, s = ctx.W // 2, y0 + 2 * (bh + ctx.px(16)) - ctx.px(10), ctx.px(46) * e
            d.arc((x - s * 0.7, yy - s * 1.4, x + s * 0.7, yy + s * 0.2), 180, 360, fill=T.RED + (255,), width=ctx.px(9)); d.rounded_rectangle((x - s, yy - s * 0.4, x + s, yy + s * 1.1), radius=ctx.px(6), fill=T.RED + (255,))
        _txt(d, ctx, (ctx.W / 2, ctx.H * 0.20), "AT THE END", 34, T.ORANGE, a, head=False, centre=True)
        if pr.get("label"): _txt(d, ctx, (ctx.W / 2, y0 + 4 * (bh + ctx.px(16)) + ctx.px(20)), pr["label"], 40, T.WHITE, min(1, max(0.0, (t - pr["at"]) / 0.4)), centre=True)
        return
    d = ImageDraw.Draw(cv, "RGBA"); n, m = pr["n"], pr["of"]; a = min(1.0, t / 0.35); cw = min(ctx.px(110), int(ctx.W * 0.78 / m) - ctx.px(14)); gap = ctx.px(14); x0 = (ctx.W - (m * cw + (m - 1) * gap)) / 2; y = int(ctx.H * 0.56)
    q = (t - pr["at"]) / 0.9
    for i in range(m):
        box = (int(x0 + i * (cw + gap)), y, int(x0 + i * (cw + gap) + cw), y + int(cw * 0.7)); on = i < n and q * n > i
        d.rounded_rectangle(box, radius=ctx.px(8), fill=((70, 16, 16) if on else (30, 30, 33)) + (int(255 * a),), outline=(T.RED if on else (60, 60, 64)) + (int(255 * a),), width=ctx.px(3))
        cx_, cy_ = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        if on: _txt(d, ctx, (cx_, box[1] + ctx.px(14)), "?", 40, (250, 196, 40), a, centre=True)
        else: s_ = ctx.px(10); d.polygon([(cx_ - s_ * 0.7, cy_ - s_), (cx_ - s_ * 0.7, cy_ + s_), (cx_ + s_, cy_)], fill=T.GREY + (int(255 * a),))      # a play mark
    if q > 0: _txt(d, ctx, (ctx.W / 2 - ctx.px(60), ctx.H * 0.28), f"{n} / {m}", 150, T.RED, min(1, q * 2), centre=True)
    lk = (t - pr["at"] - 1.0) / 0.4
    if lk > 0:
        e = T.ease_back(min(1.0, lk)); x, yy, s = int(ctx.W / 2 + ctx.px(230)), int(ctx.H * 0.36), ctx.px(36) * e
        d.arc((x - s * 0.7, yy - s * 1.4, x + s * 0.7, yy + s * 0.2), 180, 360, fill=T.RED + (255,), width=ctx.px(8)); d.rounded_rectangle((x - s, yy - s * 0.4, x + s, yy + s * 1.1), radius=ctx.px(6), fill=T.RED + (255,))
    if pr.get("label"): _txt(d, ctx, (ctx.W / 2, y + int(cw * 0.7) + ctx.px(40)), pr["label"], 34, T.SOFT_WHITE, min(1, max(0.0, q)), head=False, centre=True)

def stopwatch(cv: Image.Image, ctx: D.Ctx, sw: dict, t_abs: float) -> None:
    """The viewer's timed hold: a stopwatch top right counting real seconds from its start word, frozen and red once the clock is stopped."""
    if t_abs < sw["start"] or t_abs > sw["end"]: return
    d = ImageDraw.Draw(cv, "RGBA"); stopped = sw.get("stop") is not None and t_abs >= sw["stop"]; secs = (min(t_abs, sw["stop"]) if stopped else t_abs) - sw["start"]
    a = min(1.0, (t_abs - sw["start"]) / 0.3, (sw["end"] - t_abs) / 0.3); cx, cy, r = int(ctx.W * 0.91), int(ctx.H * 0.27), ctx.px(88); col = T.RED if stopped else T.WHITE      # below the NEXT teaser pill
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=T.P(14, 14, 16, int(200 * a)), outline=(80, 80, 84, int(255 * a)), width=ctx.px(7)); d.rectangle((cx - ctx.px(14), cy - r - ctx.px(26), cx + ctx.px(14), cy - r - ctx.px(8)), fill=(160, 160, 164, int(255 * a)))
    tg = sw.get("target") or 0; hit = tg and secs >= tg      # the stated target: the ring counts toward it, a tick mark on the rim, green once reached
    d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * (min(secs, tg) / tg if tg else (secs % 60) / 60), fill=(T.GREEN if hit else T.RED if stopped else T.ORANGE) + (int(255 * a),), width=ctx.px(10))
    if tg: _txt(d, ctx, (cx, cy + r + ctx.px(14)), f"TARGET {tg} S", 26, T.GREEN if hit else T.SOFT_WHITE, a, head=False, centre=True)
    _txt(d, ctx, (cx, cy - ctx.px(31)), f"{secs:0.1f}" if secs < 10 else f"{secs:0.0f}", 52, T.GREEN if hit and not stopped else col, a, centre=True)

def _panels_done(c) -> float:
    ts = [x["at"] for x in (c.values() if isinstance(c, dict) else []) if isinstance(x, dict) and "at" in x]
    return (max(ts) if ts else 0.0) + 0.5

def _last(items) -> float: return max((i["at"] for i in items), default=0.0)

CARD_DONE = {
    "tokens": lambda c: c["at"] + 0.3 + 0.25 * c["sets"] + 0.3, "share": lambda c: max(x["at"] for x in c["steps"]) + 0.6,      # card look -> function(card payload with absolute times) -> absolute time its animation has finished (variety keeps the scene on screen until then + a short hold)
    "race": lambda c: max(c["at"] + 0.9, c["slow"]["at"]) + 0.8,
    "slots": lambda c: _last(c["items"]) + 0.45,
    "engage": lambda c: c["at"] + 0.35 + 0.03 * len(c.get("text") or "") + 0.3 if c.get("kind") == "comment" else c["at"] + 0.6,
    "promise": lambda c: c["at"] + (1.4 if c.get("n") else 1.0),
    "study": lambda c: c["at"] + 0.2, "stat": lambda c: c["at"] + 0.3, "dial": lambda c: c["at"] + 0.3,
    "checklist": lambda c: _last(c["items"]) + 0.5, "timeline": lambda c: _last(c["items"]) + 0.5,
    "steps": lambda c: _last(c if isinstance(c, list) else c.get("items", [])) + 0.5,
    "mechanism": lambda c: (c.get("pull_at") if c.get("pull_at") is not None else c["at"]) + 0.8,
    "formula": lambda c: c["b"]["at"] + 0.4, "versus": lambda c: c["b"]["at"] + 0.5,
    "mistake": _panels_done, "myth": _panels_done,
    "question": lambda c: c["at"] + 1.0 + 0.03 * len(c.get("text") or ""),      # dots 0.45 s, typing, then the marker swipe
}

from . import diagrams as _DG      # the Phase 3 diagrams finish on their last mark
CARD_DONE.update(_DG.DONE)


QUOTE_RX = re.compile(r"(?:wrote|said|put it|once said|tells us|writes)\s*[:,]\s*(.+)$", re.I)

def quote_payload(text: str, words: list, source: str = "") -> Optional[dict]:
    """The quote card's content from its sentence: the words after "wrote:" / "said:" (or in quotation marks), else the whole sentence; each word keeps its spoken time.
    None when the sentence has no words. `source` (the book / letter and year) is shown under it: never invented, only what the scenes CSV gives."""
    text = (text or "").strip()
    if not text: return None
    m = re.search(r"[\"\u201c](.+?)[\"\u201d]", text) or QUOTE_RX.search(text); body = (m.group(1) if m else text).strip().strip("\"\u201c\u201d")
    toks = body.split(); ws = list(words or []); times = []
    if toks: toks[0] = toks[0][:1].upper() + toks[0][1:]      # a quote starts with a capital, even when the narration runs it on after "wrote:"
    if ws and toks:      # the quote's words are the sentence's last len(toks) words
        tail = ws[-len(toks):] if len(ws) >= len(toks) else ws; times = [float(w["t0"]) for w in tail]
    while len(times) < len(toks): times.append(times[-1] + 0.25 if times else 0.0)
    return {"words": [{"w": w, "t0": t0} for w, t0 in zip(toks, times)], "source": re.sub(r"\s+", " ", source or "").strip(), "at": times[0] if times else 0.0}

def quote(cv: Image.Image, ctx: D.Ctx, q: dict, t: float) -> None:
    """A quote on its own: a large opening mark in the accent colour, the quote's words appearing as they are spoken (ivory, serif in the Jung theme), the source fading in under it."""
    d = ImageDraw.Draw(cv, "RGBA"); a = min(1.0, t / 0.4); x0, y0, maxw = ctx.px(250), int(ctx.H * 0.36), ctx.W - ctx.px(500)
    por = _quote_portrait(ctx) if T.THEME == "jung" else None
    if por is not None:      # Carl Jung Theory: his portrait in a round sepia frame beside the quote
        maxw = ctx.W - ctx.px(250) - ctx.px(720); pe = T.ease_out(min(1.0, t / 0.6)); px_, py_ = ctx.W - ctx.px(560), int(ctx.H * 0.50 - por.height / 2 + (1 - pe) * 24 * ctx.S)
        lay = por.copy(); lay.putalpha(lay.getchannel("A").point(lambda v: int(v * pe))); cv.paste(lay, (px_, py_), lay)
    mark = ctx.font(T.HEAD_FONT, 260); e = T.ease_back(min(1.0, t / 0.5)); d.text((ctx.px(120), y0 - ctx.px(150) + int((1 - e) * 30 * ctx.S)), "\u201c", font=mark, fill=T.ORANGE + (int(230 * a),))
    face = "sys:Georgia Italic" if T.THEME == "jung" else T.HEAD_FONT; size = 66 if len(q["words"]) <= 18 else 54; f = ctx.font(face, size); lh = ctx.px(size * 1.32)
    x, y, line = x0, y0, 0; space = D._text_w(d, " ", f, 0)
    for w in q["words"]:
        ww = D._text_w(d, w["w"], f, 0)
        if x > x0 and x + ww > x0 + maxw: x, y = x0, y + lh; line += 1
        p = (t - w["t0"]) / 0.3
        if p > 0: d.text((x, y + int((1 - T.ease_out(min(1.0, p))) * 14 * ctx.S)), w["w"], font=f, fill=T.WHITE + (int(255 * min(1.0, p)),))
        x += ww + space
    if q.get("source"):
        last = q["words"][-1]["t0"] if q["words"] else 0.0; sp = (t - last - 0.4) / 0.5
        if sp > 0:
            sy = y + lh + ctx.px(30); d.rectangle((x0, sy + ctx.px(22), x0 + int(ctx.px(60) * min(1.0, sp)), sy + ctx.px(25)), fill=T.ORANGE + (int(255 * min(1.0, sp)),))
            _txt(d, ctx, (x0 + ctx.px(80), sy), q["source"].upper(), 30, T.ORANGE, min(1.0, sp), head=False)


def _quote_portrait(ctx: D.Ctx):
    """Jung's main reference portrait as a round sepia medallion with a gold ring (cached per size); None when there is no reference image."""
    k = ("jung_medallion",)
    if k not in ctx._art:
        ctx._art[k] = None
        try:
            from . import art as AR
            refs = AR.jung_refs()
            if refs:
                from PIL import ImageOps
                size = ctx.px(400); im = ImageOps.fit(Image.open(refs[0]).convert("L"), (size, size), centering=(0.55, 0.32))
                sep = ImageOps.colorize(im, (24, 16, 10), (236, 214, 176)).convert("RGBA"); m = Image.new("L", (size, size), 0); ImageDraw.Draw(m).ellipse((0, 0, size - 1, size - 1), fill=255)
                sep.putalpha(m); ring = Image.new("RGBA", (size + ctx.px(20), size + ctx.px(20)), (0, 0, 0, 0)); rd = ImageDraw.Draw(ring)
                rd.ellipse((0, 0, ring.width - 1, ring.height - 1), outline=T.ORANGE + (255,), width=ctx.px(4)); ring.paste(sep, (ctx.px(10), ctx.px(10)), sep); ctx._art[k] = ring
        except Exception: ctx._art[k] = None
    return ctx._art[k]



BOARD_CPS = 16      # handwriting letters a second: a marker writing, not typing
HILITE = (255, 224, 102)      # the highlighter that sweeps behind the line just written
MARKER_RED = (222, 86, 72)
NOTE_COLS = ((255, 234, 128), (186, 234, 210), (255, 202, 208), (194, 222, 250), (255, 214, 168))      # sticky notes: yellow, mint, pink, blue, peach
BOARD_BOX = (0.05, 0.10, 0.95, 0.80)      # the board's place in the frame (fractions of W, H)

# ---- the board itself: drawn once per frame size and cached (nothing in it moves, so nothing shimmers) ----

def _board_static(ctx: D.Ctx) -> Image.Image:
    """The whiteboard as one picture: brushed-aluminium frame with dark corner caps, a glossy white surface with a soft light sheen and faint ghosts of earlier
    erased writing, and the tray under it holding three capped markers and a felt eraser."""
    key = ("elder_board", ctx.W, ctx.H)
    if key in ctx._art: return ctx._art[key]
    import numpy as np
    from PIL import ImageFilter
    x0, y0, x1, y1 = (int(v * (ctx.W if k % 2 == 0 else ctx.H)) for k, v in enumerate(BOARD_BOX)); w, h = x1 - x0, y1 - y0; tray = ctx.px(46); fr = ctx.px(18); rad = ctx.px(16)
    im = Image.new("RGBA", (w + ctx.px(24), h + tray + ctx.px(24)), (0, 0, 0, 0))
    sh = Image.new("L", im.size, 0); ImageDraw.Draw(sh).rounded_rectangle((ctx.px(10), ctx.px(16), w + ctx.px(10), h + ctx.px(16)), radius=rad, fill=70)
    im.paste((24, 40, 58, 255), (0, 0), sh.filter(ImageFilter.GaussianBlur(ctx.px(12))))      # soft shadow on the wall
    yy = np.linspace(0, 1, h)[:, None]; xx = np.linspace(0, 1, w)[None, :]
    metal = 214 - 46 * yy + 10 * np.sin(xx * 90 + yy * 3) * 0.2 + np.random.default_rng(3).normal(0, 2.0, (h, w))      # brushed aluminium, lighter at the top
    frame = Image.fromarray(np.clip(np.dstack([metal - 6, metal, metal + 6]), 0, 255).astype("uint8"), "RGB")
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=rad, fill=255); im.paste(frame, (0, 0), m)
    iw, ih = w - 2 * fr, h - 2 * fr; diag = (np.linspace(0, 1, iw)[None, :] * 0.6 + np.linspace(0, 1, ih)[:, None] * 0.4)
    sheen = 251 - 7 * diag + 5 * np.exp(-((diag - 0.28) / 0.07) ** 2) + 3 * np.exp(-((diag - 0.36) / 0.03) ** 2)      # a soft band of window light across the gloss
    surf = Image.fromarray(np.clip(np.dstack([sheen - 1, sheen, sheen + 1]), 0, 255).astype("uint8"), "RGB").convert("RGBA")
    ghost = Image.new("RGBA", (iw, ih), (0, 0, 0, 0)); g = ImageDraw.Draw(ghost); rng = np.random.default_rng(11)
    for _ in range(9):      # faint smudges of earlier, erased writing
        gx, gy = rng.uniform(0.05, 0.9) * iw, rng.uniform(0.08, 0.9) * ih; L = rng.uniform(0.08, 0.22) * iw
        pts = [(gx + L * k / 12, gy + ctx.px(8) * math.sin(k * 1.3 + gx)) for k in range(13)]; g.line(pts, fill=(120, 130, 140, 13), width=ctx.px(rng.uniform(10, 26)))
    surf.alpha_composite(ghost.filter(ImageFilter.GaussianBlur(ctx.px(7))))
    sm = Image.new("L", (iw, ih), 0); ImageDraw.Draw(sm).rounded_rectangle((0, 0, iw - 1, ih - 1), radius=ctx.px(6), fill=255); im.paste(surf, (fr, fr), sm)
    d = ImageDraw.Draw(im, "RGBA"); d.rounded_rectangle((fr, fr, fr + iw, fr + ih), radius=ctx.px(6), outline=(150, 160, 168, 255), width=ctx.px(2))
    d.line((ctx.px(14), ctx.px(4), w - ctx.px(14), ctx.px(4)), fill=(255, 255, 255, 150), width=ctx.px(2))      # the frame's top edge catches the light
    c = ctx.px(34)
    for cx, cy in ((0, 0), (w - c, 0), (0, h - c), (w - c, h - c)): d.rounded_rectangle((cx, cy, cx + c, cy + c), radius=ctx.px(9), fill=(58, 64, 72, 255))      # corner caps
    ty = h - ctx.px(6)      # the tray
    d.rounded_rectangle((ctx.px(110), ty, w - ctx.px(110), ty + ctx.px(26)), radius=ctx.px(8), fill=(176, 184, 192, 255)); d.line((ctx.px(116), ty + ctx.px(3), w - ctx.px(116), ty + ctx.px(3)), fill=(230, 234, 238, 255), width=ctx.px(3))
    for k, col in enumerate((T.ORANGE, MARKER_RED, T.WHITE)):
        mx = w - ctx.px(480) + k * ctx.px(118); my = ty - ctx.px(14)
        d.rounded_rectangle((mx, my, mx + ctx.px(104), my + ctx.px(20)), radius=ctx.px(9), fill=(244, 244, 242, 255), outline=(170, 170, 170, 255), width=ctx.px(1))
        d.rounded_rectangle((mx + ctx.px(70), my - ctx.px(1), mx + ctx.px(108), my + ctx.px(21)), radius=ctx.px(9), fill=col + (255,))
        d.rectangle((mx + ctx.px(14), my + ctx.px(6), mx + ctx.px(54), my + ctx.px(13)), fill=col + (200,))      # its label band
    ex = ctx.px(170); d.rounded_rectangle((ex, ty - ctx.px(30), ex + ctx.px(150), ty + ctx.px(2)), radius=ctx.px(7), fill=(44, 58, 86, 255))      # the eraser: felt under a wooden top
    d.rounded_rectangle((ex, ty - ctx.px(34), ex + ctx.px(150), ty - ctx.px(18)), radius=ctx.px(7), fill=(196, 152, 104, 255))
    ctx._art[key] = (im, (x0, y0, x1, y1), fr); return ctx._art[key]

def _board_frame(cv: Image.Image, ctx: D.Ctx, t: float):
    """Pastes the board, sliding up into place. Returns the writing surface (x0, y0, x1, y1) and its alpha."""
    im, (x0, y0, x1, y1), fr = _board_static(ctx); e = T.ease_out(t / 0.5); a = min(1.0, t / 0.35); dy = int((1 - e) * 50 * ctx.S)
    layer = im
    if a < 1: layer = im.copy(); layer.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    cv.paste(layer, (x0, y0 + dy), layer)
    return x0 + fr, y0 + fr + dy, x1 - fr, y1 - fr + dy, a

# ---- the pen, the ink and the doodles ----

def _marker_img(ctx: D.Ctx, col) -> Image.Image:
    """A real-looking whiteboard marker (white barrel, coloured cap end and tip, a shine), pointing down-left, tip at the image's bottom-left corner."""
    key = ("elder_marker", ctx.W, col)
    if key in ctx._art: return ctx._art[key]
    L, R = ctx.px(150), ctx.px(15); im = Image.new("RGBA", (L + ctx.px(10), 2 * R + ctx.px(10)), (0, 0, 0, 0)); d = ImageDraw.Draw(im, "RGBA"); cy = R + ctx.px(5)
    d.polygon([(0, cy), (ctx.px(16), cy - ctx.px(6)), (ctx.px(16), cy + ctx.px(6))], fill=col + (255,))      # the felt tip
    d.polygon([(ctx.px(16), cy - ctx.px(7)), (ctx.px(34), cy - R), (ctx.px(34), cy + R), (ctx.px(16), cy + ctx.px(7))], fill=(60, 64, 70, 255))      # the cone
    d.rounded_rectangle((ctx.px(34), cy - R, L - ctx.px(30), cy + R), radius=ctx.px(5), fill=(246, 246, 244, 255), outline=(150, 150, 150, 255), width=ctx.px(1))
    d.rectangle((ctx.px(56), cy - R + ctx.px(4), ctx.px(96), cy + R - ctx.px(4)), fill=col + (220,))      # the label band
    d.rounded_rectangle((L - ctx.px(34), cy - R - ctx.px(1), L + ctx.px(6), cy + R + ctx.px(1)), radius=ctx.px(10), fill=col + (255,))      # the cap on the back
    d.line((ctx.px(38), cy - R * 0.5, L - ctx.px(36), cy - R * 0.5), fill=(255, 255, 255, 220), width=ctx.px(3))      # shine
    im = im.rotate(-32, resample=Image.BICUBIC, expand=True)      # leaning up-right from the tip, as a right hand holds it
    tip = None
    a = __import__("numpy").asarray(im.getchannel("A"))
    ys, xs = __import__("numpy").nonzero(a > 40); k = int(xs.argmin()); tip = (int(xs[k]), int(ys[k]))
    ctx._art[key] = (im, tip); return ctx._art[key]

def _pen(cv: Image.Image, ctx: D.Ctx, xy, col) -> None:
    im, (tx, ty) = _marker_img(ctx, col); x, y = int(xy[0] - tx), int(xy[1] - ty)
    sh = im.copy(); sh.putalpha(im.getchannel("A").point(lambda v: int(v * 0.18))); sh = Image.composite(Image.new("RGBA", im.size, (0, 0, 0, 255)), Image.new("RGBA", im.size, (0, 0, 0, 0)), sh.getchannel("A"))
    cv.paste(sh, (x + ctx.px(10), y + ctx.px(12)), sh); cv.paste(im, (x, y), im)

def _hand_w(ctx: D.Ctx, text: str, size: int) -> float: return D._text_w(ImageDraw.Draw(Image.new("RGB", (4, 4))), text, ctx.font(T.HAND_FONT, size), 0)

def _hand_line(cv: Image.Image, ctx: D.Ctx, xy, text: str, size: int, col, frac: float, pen: bool) -> float:
    """One handwritten line, revealed left to right up to frac (0..1) as a marker writes it (the marker rides the writing edge while pen). Returns the line's width."""
    if frac <= 0 or not text: return 0.0
    f = ctx.font(T.HAND_FONT, size); w = int(_hand_w(ctx, text, size)) + ctx.px(8); h = ctx.px(size * 1.4)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0)); ImageDraw.Draw(layer).text((0, 0), text, font=f, fill=col + (255,))
    cut = int(w * min(1.0, frac)); part = layer.crop((0, 0, max(1, cut), h)); cv.paste(part, (int(xy[0]), int(xy[1])), part)
    if pen and frac < 1: _pen(cv, ctx, (xy[0] + cut, xy[1] + h * (0.55 + 0.12 * math.sin(frac * 46))), col)
    return w

def _hand_frac(text: str, t: float, at: float) -> float:
    return max(0.0, min(1.0, (t - at) * BOARD_CPS / max(4, len(text)))) if t > at else 0.0

def _write_end(text: str, at: float) -> float: return at + max(4, len(text)) / BOARD_CPS

def _hilite(d, x, y, w, h, p) -> None:
    """A highlighter stroke sweeping behind a written line (drawn before the ink), slightly tilted like a real swipe."""
    if p <= 0: return
    ww = w * min(1.0, p); d.polygon([(x - 8, y + h * 0.30), (x + ww, y + h * 0.26), (x + ww + 6, y + h * 0.98), (x - 4, y + h * 1.02)], fill=HILITE + (120,))

def _circle(d, cx, cy, r, p, col, width) -> None:
    """A marker circle drawn around something, slightly wobbly and overshooting its start like a hand."""
    if p <= 0: return
    n = max(3, int(40 * min(1.0, p))); pts = []
    for k in range(n + 1):
        a = -2.2 + (2 * math.pi + 0.5) * min(1.0, p) * k / n; rr = r * (1 + 0.06 * math.sin(a * 3))
        pts.append((cx + rr * 1.15 * math.cos(a), cy + rr * math.sin(a)))
    d.line(pts, fill=col + (235,), width=width, joint="curve")

def _arrow(d, a, b, p, col, width) -> None:
    """A curved marker arrow from a to b, drawn in over p (0..1), the head once it arrives."""
    if p <= 0: return
    c = ((a[0] + b[0]) / 2, min(a[1], b[1]) - abs(b[0] - a[0]) * 0.10); n = 24; m = max(2, int(n * min(1.0, p)))
    pts = [((1 - u) ** 2 * a[0] + 2 * (1 - u) * u * c[0] + u * u * b[0], (1 - u) ** 2 * a[1] + 2 * (1 - u) * u * c[1] + u * u * b[1]) for u in (k / n for k in range(m + 1))]
    d.line(pts, fill=col + (235,), width=width, joint="curve")
    if p >= 1:
        ang = math.atan2(b[1] - pts[-2][1], b[0] - pts[-2][0]); L = width * 4.5
        for s_ in (-0.5, 0.5): d.line((b, (b[0] - L * math.cos(ang + s_), b[1] - L * math.sin(ang + s_))), fill=col + (235,), width=width)

def _star(d, cx, cy, r, col) -> None:
    if r <= 1: return
    pts = [(cx + (r if k % 2 == 0 else r * 0.42) * math.cos(-math.pi / 2 + k * math.pi / 5), cy + (r if k % 2 == 0 else r * 0.42) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(10)]
    d.polygon(pts, fill=col + (230,))

DOODLES = (      # (words in the tip, doodle, colour): the first match is drawn beside the tip
    (r"\b(walk\w*|steps?|stroll\w*|exercis\w*|move|moving|movement|active|activity)\b", "feet", (22, 150, 150)),
    (r"\b(water|drink\w*|hydrat\w*|fluids?|tea)\b", "glass", (60, 140, 220)),
    (r"\b(sleep\w*|bed|rest\w*|nap\w*|night|tired)\b", "moon", (96, 92, 190)),
    (r"\b(heart|blood pressure|cholesterol|pulse|circulation)\b", "heart", (222, 86, 72)),
    (r"\b(pills?|medic\w*|vitamins?|supplements?|tablets?|dose)\b", "pill", (230, 120, 60)),
    (r"\b(bones?|knees?|joints?|hips?|calcium|spine|back)\b", "bone", (150, 120, 90)),
    (r"\b(sun\w*|outside|outdoors?|morning light|daylight)\b", "sun", (240, 176, 30)),
    (r"\b(brain|memory|mind|think\w*|remember\w*|learn\w*|read\w*|puzzles?)\b", "bulb", (240, 176, 30)),
    (r"\b(eat\w*|food|meals?|fruit|vegetables?|veg|diet|fiber|fibre|protein|breakfast|lunch|dinner|apple)\b", "apple", (92, 158, 104)),
    (r"\b(doctor|check\w*|test\w*|screening|blood sugar|visit)\b", "cross", (22, 150, 150)),
    (r"\b(minutes?|hours?|daily|every day|times? a|o'?clock|pm|am)\b", "clock", (28, 44, 70)),
)

def doodle_for(text: str) -> tuple:
    import re as _re
    for rx, kind, col in DOODLES:
        if _re.search(rx, text, _re.I): return kind, col
    return "star", (240, 180, 40)

def _doodle_img(ctx: D.Ctx, kind: str, col, r: int) -> Image.Image:
    """A small marker doodle (outline + a light fill), drawn in code: feet, glass, moon, heart, pill, bone, sun, bulb, apple, cross, clock, star."""
    key = ("elder_doodle", kind, col, r)
    if key in ctx._art: return ctx._art[key]
    S = 2 * r + ctx.px(12); im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im, "RGBA"); c = S / 2; w = max(3, ctx.px(6)); lt = col + (70,); ink = col + (255,)
    if kind == "feet":      # a walking shoe, side view: sole, upper, laces
        sole = [(c - r * 0.95, c + r * 0.45), (c + r * 0.95, c + r * 0.45), (c + r * 0.98, c + r * 0.62), (c - r * 0.92, c + r * 0.62)]
        upper = [(c - r * 0.9, c + r * 0.45), (c - r * 0.9, c - r * 0.35), (c - r * 0.35, c - r * 0.45), (c - r * 0.05, c - r * 0.05), (c + r * 0.55, c + r * 0.1), (c + r * 0.92, c + r * 0.3), (c + r * 0.95, c + r * 0.45)]
        d.polygon(upper, fill=lt); d.line(upper + [upper[0]], fill=ink, width=w, joint="curve"); d.polygon(sole, fill=ink)
        for k in range(3): x_ = c - r * 0.25 + k * r * 0.22; d.line([(x_, c - r * 0.05 + k * r * 0.06), (x_ + r * 0.16, c - r * 0.2 + k * r * 0.06)], fill=ink, width=max(2, w // 2))
    elif kind == "glass":
        d.polygon([(c - r * 0.55, c - r * 0.8), (c + r * 0.55, c - r * 0.8), (c + r * 0.42, c + r * 0.85), (c - r * 0.42, c + r * 0.85)], fill=(255, 255, 255, 0), outline=ink)
        d.polygon([(c - r * 0.5, c - r * 0.2), (c + r * 0.5, c - r * 0.2), (c + r * 0.42, c + r * 0.85), (c - r * 0.42, c + r * 0.85)], fill=lt)
        d.line([(c - r * 0.55, c - r * 0.8), (c - r * 0.42, c + r * 0.85), (c + r * 0.42, c + r * 0.85), (c + r * 0.55, c - r * 0.8)], fill=ink, width=w, joint="curve")
        d.line([(c - r * 0.5, c - r * 0.2), (c + r * 0.5, c - r * 0.2)], fill=ink, width=max(2, w // 2))
    elif kind == "moon":
        d.ellipse((c - r * 0.8, c - r * 0.8, c + r * 0.8, c + r * 0.8), fill=lt, outline=ink, width=w); d.ellipse((c - r * 0.35, c - r * 1.0, c + r * 1.05, c + r * 0.45), fill=(0, 0, 0, 0))
        m = Image.new("L", (S, S), 255); ImageDraw.Draw(m).ellipse((c - r * 0.35, c - r * 1.0, c + r * 1.05, c + r * 0.45), fill=0); im.putalpha(Image.fromarray(__import__("numpy").minimum(__import__("numpy").asarray(im.getchannel("A")), __import__("numpy").asarray(m))))
        d = ImageDraw.Draw(im, "RGBA"); f = ctx.font(T.HAND_FONT, int(r * 0.7 / ctx.S)); d.text((c + r * 0.3, c - r * 0.95), "z", font=f, fill=ink)
    elif kind == "heart":
        pts = [(c + r * 0.9 * (16 * math.sin(a) ** 3) / 16, c - r * 0.9 * (13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)) / 16) for a in (k * math.pi / 30 for k in range(61))]
        d.polygon(pts, fill=lt); d.line(pts, fill=ink, width=w, joint="curve")
        d.line([(c - r * 0.6, c), (c - r * 0.25, c), (c - r * 0.1, c - r * 0.35), (c + r * 0.1, c + r * 0.3), (c + r * 0.25, c), (c + r * 0.6, c)], fill=ink, width=max(2, w // 2), joint="curve")      # a pulse line
    elif kind == "pill":
        pill = Image.new("RGBA", (S, S), (0, 0, 0, 0)); p_ = ImageDraw.Draw(pill, "RGBA")
        p_.rounded_rectangle((c - r * 0.9, c - r * 0.36, c + r * 0.9, c + r * 0.36), radius=int(r * 0.36), fill=(255, 255, 255, 255), outline=ink, width=w)
        p_.rounded_rectangle((c, c - r * 0.36, c + r * 0.9, c + r * 0.36), radius=int(r * 0.36), fill=col + (150,), outline=ink, width=w); p_.line([(c, c - r * 0.36), (c, c + r * 0.36)], fill=ink, width=w)
        im = pill.rotate(30, resample=Image.BICUBIC); d = ImageDraw.Draw(im, "RGBA")
    elif kind == "bone":
        d.rounded_rectangle((c - r * 0.65, c - r * 0.18, c + r * 0.65, c + r * 0.18), radius=int(r * 0.1), fill=(255, 255, 255, 255), outline=ink, width=w)
        for sx in (-1, 1):
            for sy in (-1, 1): d.ellipse((c + sx * r * 0.72 - r * 0.24, c + sy * r * 0.2 - r * 0.24, c + sx * r * 0.72 + r * 0.24, c + sy * r * 0.2 + r * 0.24), fill=(255, 255, 255, 255), outline=ink, width=w)
        d.rectangle((c - r * 0.65, c - r * 0.18 + w, c + r * 0.65, c + r * 0.18 - w), fill=(255, 255, 255, 255))
    elif kind == "sun":
        d.ellipse((c - r * 0.45, c - r * 0.45, c + r * 0.45, c + r * 0.45), fill=lt, outline=ink, width=w)
        for k in range(8): a = k * math.pi / 4; d.line([(c + r * 0.62 * math.cos(a), c + r * 0.62 * math.sin(a)), (c + r * 0.92 * math.cos(a), c + r * 0.92 * math.sin(a))], fill=ink, width=w)
    elif kind == "bulb":
        d.ellipse((c - r * 0.58, c - r * 0.9, c + r * 0.58, c + r * 0.3), fill=lt, outline=ink, width=w); d.rectangle((c - r * 0.28, c + r * 0.3, c + r * 0.28, c + r * 0.62), fill=(200, 200, 200, 255), outline=ink, width=w)
        for k in (-1, 0, 1): d.line([(c + k * r * 0.75, c - r * 1.0 + abs(k) * r * 0.2), (c + k * r * 0.95, c - r * 1.15 + abs(k) * r * 0.25)], fill=ink, width=max(2, w // 2))
    elif kind == "apple":
        d.ellipse((c - r * 0.75, c - r * 0.5, c + r * 0.05, c + r * 0.8), fill=lt, outline=ink, width=w); d.ellipse((c - r * 0.05, c - r * 0.5, c + r * 0.75, c + r * 0.8), fill=lt, outline=ink, width=w)
        d.line([(c, c - r * 0.45), (c + r * 0.1, c - r * 0.85)], fill=(110, 80, 50, 255), width=w); d.ellipse((c + r * 0.12, c - r * 0.95, c + r * 0.55, c - r * 0.7), fill=(92, 158, 104, 255))
    elif kind == "cross":
        d.ellipse((c - r * 0.85, c - r * 0.85, c + r * 0.85, c + r * 0.85), fill=lt, outline=ink, width=w); D.plus(d, c, c, r * 0.5, ink)
    elif kind == "clock":
        d.ellipse((c - r * 0.85, c - r * 0.85, c + r * 0.85, c + r * 0.85), fill=lt, outline=ink, width=w); d.line([(c, c), (c, c - r * 0.55)], fill=ink, width=w); d.line([(c, c), (c + r * 0.4, c + r * 0.15)], fill=ink, width=w)
    else: _star(d, c, c, r * 0.9, col)
    ctx._art[key] = im; return im

def _doodle(cv: Image.Image, ctx: D.Ctx, kind: str, col, cx: float, cy: float, r: int, p: float, wob: float = 0.0) -> None:
    """Draws the doodle in as a pen would: a sweep that uncovers it around its centre, with a small pop; it then rocks gently."""
    if p <= 0: return
    im = _doodle_img(ctx, kind, col, r)
    if p < 1:
        m = Image.new("L", im.size, 0); ImageDraw.Draw(m).pieslice((-im.width, -im.height, 2 * im.width, 2 * im.height), -90, -90 + 360 * p, fill=255)
        a = im.getchannel("A"); im = im.copy(); im.putalpha(Image.fromarray(__import__("numpy").minimum(__import__("numpy").asarray(a), __import__("numpy").asarray(m))))
    sc_ = 0.7 + 0.3 * T.ease_back(min(1.0, p * 1.3))
    if abs(sc_ - 1) > 0.01 or wob: im = im.resize((max(1, int(im.width * sc_)), max(1, int(im.height * sc_))), Image.BICUBIC).rotate(wob, resample=Image.BICUBIC)
    cv.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)

# ---- the picture on the board ----

def _pinned(cv: Image.Image, ctx: D.Ctx, pic: Image.Image, box, t: float, caption: str = "") -> tuple:
    """The scene's picture as a photo held on the board by two magnets: it drops in and settles with a small tilt, the picture inside slowly pushes in, a handwritten
    caption under it, marker stars pop around it. Returns the photo's left-middle point (for the arrows)."""
    bx0, by0, bx1, by1 = box; p = T.ease_back(min(1.0, max(0.0, (t - 0.15) / 0.6)))
    if p <= 0: return (bx0, (by0 + by1) / 2)
    W, H = int(bx1 - bx0), int(by1 - by0); pad = ctx.px(18); cap = ctx.px(70) if caption else pad; iw, ih = W - 2 * pad, H - pad - cap
    z = 1.0 + min(0.10, max(0.0, t) * 0.012); src = pic.convert("RGB"); sw, sh = src.size; k = max(iw / sw, ih / sh) * z; cw, ch = iw / k, ih / k
    crop = (max(0, min(sw - cw, sw * 0.5 - cw / 2)), max(0, min(sh - ch, sh * 0.45 - ch / 2)))
    img = src.crop((int(crop[0]), int(crop[1]), int(crop[0] + cw), int(crop[1] + ch))).resize((iw, ih), Image.BICUBIC)
    card = Image.new("RGBA", (W, H), (253, 252, 248, 255)); card.paste(img, (pad, pad)); dc = ImageDraw.Draw(card, "RGBA")
    dc.rectangle((pad, pad, pad + iw, pad + ih), outline=(220, 222, 220, 255), width=ctx.px(2)); dc.rectangle((0, 0, W - 1, H - 1), outline=(214, 220, 222, 255), width=ctx.px(2))
    if caption:
        cs = 46; f = ctx.font(T.HAND_FONT, cs)
        while cs > 26 and _hand_w(ctx, caption, cs) > iw: cs -= 4; f = ctx.font(T.HAND_FONT, cs)
        cw_ = _hand_w(ctx, caption, cs); dc.text(((W - cw_) / 2, pad + ih + (cap - ctx.px(cs * 1.25)) / 2), caption, font=f, fill=T.WHITE + (255,))
    ang = -2.5 + (1 - min(1.0, p)) * -8.0 + 0.4 * math.sin(t * 0.9); card = card.rotate(ang, resample=Image.BICUBIC, expand=True)
    yy = int(by0 - (1 - min(1.0, p)) * ctx.px(140)); xx = int(bx0)
    shd = Image.composite(Image.new("RGBA", card.size, (20, 30, 40, 255)), Image.new("RGBA", card.size, (0, 0, 0, 0)), card.getchannel("A").point(lambda v: int(v * 0.22)))
    cv.paste(shd, (xx + ctx.px(14), yy + ctx.px(18)), shd); cv.paste(card, (xx, yy), card)
    d = ImageDraw.Draw(cv, "RGBA")
    for n, (fx, col) in enumerate(((0.22, MARKER_RED), (0.78, T.ORANGE))):      # two round magnets
        mx, my, r = xx + card.width * fx, yy + ctx.px(26), ctx.px(22)
        d.ellipse((mx - r + ctx.px(4), my - r + ctx.px(6), mx + r + ctx.px(4), my + r + ctx.px(6)), fill=(0, 0, 0, 50)); d.ellipse((mx - r, my - r, mx + r, my + r), fill=col + (255,))
        d.ellipse((mx - r * 0.55, my - r * 0.6, mx - r * 0.05, my - r * 0.15), fill=(255, 255, 255, 120))
    for n, (sx, sy) in enumerate(((-0.07, 0.12), (1.05, 0.9), (1.03, 0.1))):      # marker stars pop in one after another, then twinkle
        q = T.ease_back(min(1.0, max(0.0, (t - 0.8 - 0.18 * n) / 0.35)))
        if q > 0: _star(d, xx + card.width * sx, yy + card.height * sy, ctx.px(22) * q * (1 + 0.12 * math.sin(t * 4 + n * 2)), (MARKER_RED, T.ORANGE, (240, 180, 40))[n])
    return (xx - ctx.px(10), yy + card.height * 0.45)

def _photo_box(ctx: D.Ctx, x0, y0, x1, y1) -> tuple:
    pw = (x1 - x0) * 0.37; ph = min((y1 - y0) * 0.86, pw * 0.98); px0 = x1 - pw - ctx.px(46); py0 = (y0 + y1) / 2 - ph / 2
    return (px0, py0, px0 + pw, py0 + ph)

# ---- the two board layouts ----

def board(cv: Image.Image, ctx: D.Ctx, items: List[dict], t: float, ticks: bool = False, title: str = "", pic: Optional[Image.Image] = None, caption: str = "", notes: bool = False) -> None:
    """Elder Health Theory's handwriting board. Each step / list item is written by a marker as the narration reaches it, with a doodle of what it is about (a glass for
    water, feet for walking, a moon for sleep...) drawn beside it, the number circled while it is said (or a tick), a highlighter swipe behind it, and an arrow to the scene's
    picture held on the board by magnets. notes: the items are sticky notes slapped onto the board instead of lines (same timing). Items are steps()'s ({text, at})."""
    x0, y0, x1, y1, a = _board_frame(cv, ctx, t)
    if a < 1 and t < 0.2: return
    photo = _pinned(cv, ctx, pic, _photo_box(ctx, x0, y0, x1, y1), t, caption) if pic is not None else None
    tx1 = (_photo_box(ctx, x0, y0, x1, y1)[0] - ctx.px(60)) if pic is not None else x1 - ctx.px(60)
    if notes: return _notes(cv, ctx, items, t, x0 + ctx.px(50), y0, tx1, y1, photo)
    d = ImageDraw.Draw(cv, "RGBA"); n = max(1, len(items)); size = 66 if n <= 3 else 56 if n <= 5 else 46; dr = ctx.px(size * 0.5)
    bx = x0 + ctx.px(80); text_x = bx + ctx.px(size * 0.9); room = lambda sz: tx1 - (bx + ctx.px(sz * 0.9)) - ctx.px(sz * 1.3)      # the doodle sits after the words
    longest = max((_hand_w(ctx, it["text"], size) for it in items), default=0)
    while size > 36 and longest > room(size): size -= 4; longest = max(_hand_w(ctx, it["text"], size) for it in items)
    text_x = bx + ctx.px(size * 0.9); dr = ctx.px(size * 0.66); lh = ctx.px(size * 1.7); top = max(y0 + ctx.px(40), int((y0 + y1) / 2 - n * lh / 2))
    if title: _hand_line(cv, ctx, (x0 + ctx.px(70), y0 + ctx.px(30)), title, 56, T.ORANGE_DEEP, _hand_frac(title, t, 0.2), True)
    pens = []
    for i, it in enumerate(items):
        if t < it["at"]: continue
        at = it["at"] + 0.25; fr = _hand_frac(it["text"], t, at); y = top + i * lh; q = T.ease_out((t - it["at"]) / 0.3); cx, cy = bx, y + ctx.px(size * 0.72)
        soft = i + 1 < n and t >= items[i + 1]["at"]; done = _write_end(it["text"], at); w = _hand_w(ctx, it["text"], size)
        if not soft: _hilite(d, text_x, y, w, ctx.px(size * 1.15), T.ease_out((t - done) / 0.35))      # the highlighter swipe, behind the ink
        if ticks:      # a green tick drawn in two strokes
            k = ctx.px(size * 0.32); d.line((cx - k, cy, cx - k * 0.2, cy + k * 0.8 * min(1, q * 2)), fill=T.GREEN + (255,), width=ctx.px(8))
            if q > 0.5: d.line((cx - k * 0.2, cy + k * 0.8, cx - k * 0.2 + k * 1.6 * (q * 2 - 1), cy + k * 0.8 - k * 2.0 * (q * 2 - 1)), fill=T.GREEN + (255,), width=ctx.px(8))
        else:
            _hand_line(cv, ctx, (cx - ctx.px(size * 0.3), y), f"{i + 1}", size, T.ORANGE, min(1.0, q * 1.4), False)
            if not soft: _circle(d, cx - ctx.px(size * 0.05), cy - ctx.px(size * 0.05), ctx.px(size * 0.55), T.ease_out((t - it["at"]) / 0.45), MARKER_RED, ctx.px(5))      # the number being said is circled
        _hand_line(cv, ctx, (text_x, y), it["text"], size, T.SOFT_WHITE if soft else T.WHITE, fr, False)
        if not soft and 0 < fr < 1: pens.append((text_x + (w + ctx.px(8)) * fr, y + ctx.px(size * 1.4) * (0.55 + 0.12 * math.sin(fr * 46))))
        kind, col = doodle_for(it["text"]); dx = text_x + w + ctx.px(size * 0.95)
        _doodle(cv, ctx, kind, col, dx, cy, dr, (t - done) / 0.45, 4 * math.sin(t * 2.2 + i) if not soft else 0.0)
        d = ImageDraw.Draw(cv, "RGBA")
        if photo and not soft and dx + dr + ctx.px(40) < photo[0] - ctx.px(40):      # an arrow from the line just written to the picture
            _arrow(d, (dx + dr + ctx.px(16), cy), photo, T.ease_in_out((t - done - 0.35) / 0.5), MARKER_RED, ctx.px(6))
    for xy in pens: _pen(cv, ctx, xy, T.WHITE)      # the marker on top of everything

def _wrap_hand(ctx: D.Ctx, text: str, size: int, width: float) -> list:
    out, cur = [], ""
    for w in text.split():
        nxt = (cur + " " + w).strip()
        if cur and _hand_w(ctx, nxt, size) > width: out.append(cur); cur = w
        else: cur = nxt
    return out + ([cur] if cur else [])

def _notes(cv: Image.Image, ctx: D.Ctx, items: List[dict], t: float, ax0, ay0, ax1, ay1, photo) -> None:
    """The sticky-note layout: each item slapped onto the board on its own coloured note as it is said (a quick drop with a tilt, a curled corner, a soft shadow),
    its doodle on top and its words handwritten under it; the note being said is lifted slightly and an arrow runs from it to the picture."""
    n = max(1, len(items)); cols = n if n <= 3 else (2 if n == 4 else 3); rows = math.ceil(n / cols); gap = ctx.px(34)
    nw = min((ax1 - ax0 - gap * (cols - 1)) / cols, (ay1 - ay0 - ctx.px(60) - gap * (rows - 1)) / rows * 1.05, ctx.px(380)); nh = nw * 0.95
    gx0 = ax0 + (ax1 - ax0 - (cols * nw + (cols - 1) * gap)) / 2; gy0 = (ay0 + ay1) / 2 - (rows * nh + (rows - 1) * gap) / 2
    for i, it in enumerate(items):
        if t < it["at"]: continue
        p = (t - it["at"]) / 0.45; e = T.ease_back(min(1.0, p)); now = not (i + 1 < n and t >= items[i + 1]["at"])
        r_, c_ = divmod(i, cols); x, y = gx0 + c_ * (nw + gap), gy0 + r_ * (nh + gap); col = NOTE_COLS[i % len(NOTE_COLS)]
        W_, H_ = int(nw), int(nh); note = Image.new("RGBA", (W_, H_), (0, 0, 0, 0)); dn = ImageDraw.Draw(note, "RGBA"); fold = ctx.px(46)
        dn.polygon([(0, 0), (W_, 0), (W_, H_ - fold), (W_ - fold, H_), (0, H_)], fill=col + (255,))
        dn.polygon([(W_, H_ - fold), (W_ - fold, H_), (W_ - fold * 0.86, H_ - fold * 0.86)], fill=tuple(max(0, v - 40) for v in col) + (255,))      # the curled corner
        dn.rectangle((0, 0, W_, ctx.px(30)), fill=tuple(max(0, v - 14) for v in col) + (255,))      # the sticky strip
        kind, dcol = doodle_for(it["text"]); dr = int(nh * 0.17)
        size = 50
        while size > 28 and len(_wrap_hand(ctx, it["text"], size, W_ - ctx.px(50))) * ctx.px(size * 1.2) > H_ * 0.52: size -= 3
        lines = _wrap_hand(ctx, it["text"], size, W_ - ctx.px(50)); ty = int(H_ * 0.42)
        frac = _hand_frac(it["text"], t, it["at"] + 0.35); total = sum(len(l) for l in lines) or 1; left = frac * total
        for ln in lines:
            fr = max(0.0, min(1.0, left / max(1, len(ln)))); left -= len(ln)
            _hand_line(note, ctx, ((W_ - _hand_w(ctx, ln, size)) / 2, ty), ln, size, T.WHITE, fr, False); ty += ctx.px(size * 1.2)
        _doodle(note, ctx, kind, dcol, W_ / 2, H_ * 0.22, dr, (t - it["at"] - 0.2) / 0.4, 0.0)
        ang = ((i * 37) % 7 - 3) * 1.1 + (1 - min(1.0, e)) * 10 + (0.6 * math.sin(t * 1.6 + i) if now else 0)
        scale = (1.25 - 0.25 * min(1.0, e)) * (1.04 if now else 1.0)
        note = note.resize((max(1, int(W_ * scale)), max(1, int(H_ * scale))), Image.BICUBIC).rotate(ang, resample=Image.BICUBIC, expand=True)
        if p < 1: note.putalpha(note.getchannel("A").point(lambda v: int(v * min(1.0, p * 2.5))))
        px_, py_ = int(x + nw / 2 - note.width / 2), int(y + nh / 2 - note.height / 2)
        shd = Image.composite(Image.new("RGBA", note.size, (20, 30, 40, 255)), Image.new("RGBA", note.size, (0, 0, 0, 0)), note.getchannel("A").point(lambda v: int(v * (0.30 if now else 0.18))))
        lift = ctx.px(16 if now else 8); cv.paste(shd, (px_ + lift, py_ + lift + ctx.px(4)), shd); cv.paste(note, (px_, py_), note)
        if photo and now and x + nw + ctx.px(40) < photo[0]:
            _arrow(ImageDraw.Draw(cv, "RGBA"), (x + nw + ctx.px(10), y + nh * 0.4), photo, T.ease_in_out((t - _write_end(it["text"], it["at"] + 0.35) - 0.2) / 0.5), MARKER_RED, ctx.px(6))

def board_takeaway(cv: Image.Image, ctx: D.Ctx, tk: dict, t: float, pic: Optional[Image.Image] = None, caption: str = "") -> None:
    """The takeaway on the whiteboard: each word handwritten as it is spoken, wrapped to the board, a highlighter swipe, a coral underline and a doodle of what it is
    about once it is all said; the scene's picture held by magnets on the right."""
    x0, y0, x1, y1, a = _board_frame(cv, ctx, t); words = tk["words"]
    if pic is not None: _pinned(cv, ctx, pic, _photo_box(ctx, x0, y0, x1, y1), t, caption)
    size = 88 if pic is None else 74; f = ctx.font(T.HAND_FONT, size); d0 = ImageDraw.Draw(cv, "RGBA"); sp = D._text_w(d0, " ", f, 0)
    max_w = ((_photo_box(ctx, x0, y0, x1, y1)[0] - x0) if pic is not None else (x1 - x0)) - ctx.px(200); lines, cur, curw = [], [], 0.0
    for w in words:
        ww = D._text_w(d0, w["w"], f, 0)
        if cur and curw + sp + ww > max_w: lines.append((cur, curw)); cur, curw = [], 0.0
        cur.append((w, ww)); curw += (sp if len(cur) > 1 else 0) + ww
    if cur: lines.append((cur, curw))
    lh = ctx.px(size * 1.45); top = int((y0 + y1) / 2 - len(lines) * lh / 2); end = max((w["t0"] for w in words), default=0) + 0.5
    for li, (ln, lw) in enumerate(lines): _hilite(d0, x0 + ctx.px(90), top + li * lh, lw, ctx.px(size * 1.15), T.ease_out((t - end - 0.1 * li) / 0.35))
    last_x, pen = x0, None
    for li, (ln, lw) in enumerate(lines):
        x = x0 + ctx.px(90)
        for w, ww in ln:
            fr = max(0.0, min(1.0, (t - w["t0"]) * BOARD_CPS / max(2, len(w["w"]))))
            _hand_line(cv, ctx, (x, top + li * lh), w["w"], size, T.WHITE, fr, False)
            if 0 < fr < 1: pen = (x + (ww + ctx.px(8)) * fr, top + li * lh + ctx.px(size * 0.8))
            x += ww + sp
        last_x = x
    u = T.ease_out((t - end) / 0.45)
    if u > 0 and lines:
        d = ImageDraw.Draw(cv, "RGBA"); uy = top + len(lines) * lh - ctx.px(6); d.line((x0 + ctx.px(90), uy, x0 + ctx.px(90) + (last_x - x0 - ctx.px(90)) * u, uy - ctx.px(6) * u), fill=MARKER_RED + (230,), width=ctx.px(7))
        kind, col = doodle_for(" ".join(w["w"] for w in words)); _doodle(cv, ctx, kind, col, last_x + ctx.px(46), top + (len(lines) - 1) * lh + ctx.px(size * 0.6), ctx.px(42), (t - end - 0.3) / 0.45, 4 * math.sin(t * 2))
    if pen: _pen(cv, ctx, pen, T.WHITE)
