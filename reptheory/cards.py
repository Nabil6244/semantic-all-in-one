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
    land = t - st["at"] - 0.9      # the number has reached what was said: it flips to orange and the ring throws a pulse
    if 0 <= land < 0.7: q = T.ease_out(land / 0.7); rr = r * (1.0 + 0.35 * q); d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=T.ORANGE + (int(200 * (1 - q)),), width=ctx.px(6))
    D.text_spaced(d, (cx - w / 2, cy - ctx.px(122)), txt, f, (T.ORANGE if land >= 0 else T.WHITE) + (255,), 0); u = ctx.font(T.BODY_FONT, 44); uw = D._text_w(d, st["unit"], u, ctx.px(4)); D.text_spaced(d, (cx - uw / 2, cy + ctx.px(76)), st["unit"], u, T.ORANGE + (255,), ctx.px(4))

def steps(cv: Image.Image, ctx: D.Ctx, items: List[dict], t: float, ticks: bool = False) -> None:
    """Numbered steps that appear as the narration reaches them, joined by a line that draws down (a spoken list: a tick instead of the number)."""
    d = ImageDraw.Draw(cv, "RGBA"); n = len(items); x0, top, gap = ctx.px(150), int(ctx.H * 0.5 - (n - 1) * ctx.px(62)), ctx.px(124); r = ctx.px(40); f = ctx.font(T.HEAD_FONT, 76); nf = ctx.font(T.HEAD_FONT, 44)
    for i, it in enumerate(items):
        p = (t - it["at"]) / 0.5; e = T.ease_out(p); y = top + i * gap
        if i and p > -0.3:      # the line from the previous step draws down to this one
            q = T.ease_out((t - items[i - 1]["at"] - 0.2) / 0.5); d.line((x0, y - gap + r, x0, y - gap + r + (gap - 2 * r) * q), fill=T.ORANGE_DEEP + (255,), width=ctx.px(5))
        if p <= 0: d.ellipse((x0 - r, y - r, x0 + r, y + r), outline=T.DIM + (255,), width=ctx.px(4)); continue
        d.ellipse((x0 - r, y - r, x0 + r, y + r), fill=T.ORANGE + (int(255 * min(1, p * 2)),))
        if ticks: q = min(1.0, p); d.line((x0 - ctx.px(16), y + ctx.px(2), x0 - ctx.px(4), y + ctx.px(14) * min(1, q * 2)), fill=(20, 20, 22, 255), width=ctx.px(7)); d.line((x0 - ctx.px(4), y + ctx.px(14), x0 - ctx.px(4) + ctx.px(22) * max(0, q * 2 - 1), y + ctx.px(14) - ctx.px(28) * max(0, q * 2 - 1)), fill=(20, 20, 22, 255), width=ctx.px(7)) if q > 0.5 else None
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
    a = min(1.0, t / T_IN, (T_IN + T_HOLD + T_OUT - t) / T_OUT); a = max(0.0, a); lay = Image.new("RGBA", (ctx.W, ctx.H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); x, y = ctx.px(100), int(ctx.H * 0.80)
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
GREEN, RED = (74, 222, 128), (232, 64, 52)

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
        e = T.ease_back(min(1.0, p)); col = RED if kind == "wrong" else GREEN; a = min(1, p * 1.6) * (0.55 if kind == "wrong" and len(sides) == 2 and t >= sides[1][1]["at"] + 0.3 else 1.0)
        yy = y0 + int((1 - min(1, e)) * 50 * ctx.S); d.rounded_rectangle((x0, yy, x0 + pw, yy + ph), radius=ctx.px(24), fill=col + (int(26 * a),), outline=col + (int(255 * a),), width=ctx.px(5))
        _txt(d, ctx, (x0 + pw / 2, yy + ctx.px(24)), (mk.get("labels") or ("WRONG", "RIGHT"))[0 if kind == "wrong" else 1], 34, col, a, head=False, centre=True)
        f = ctx.font(T.HEAD_FONT, 62); lines = _wrap_lines(d, s["text"], f, pw - ctx.px(80)); ly = yy + (ph - len(lines) * ctx.px(72)) // 2 + ctx.px(20)
        for ln in lines: _txt(d, ctx, (x0 + pw / 2, ly), ln, 62, T.WHITE, a, centre=True); ly += ctx.px(72)
        q = T.ease_out((t - s["at"] - 0.35) / 0.35); m = ctx.px(46); w = ctx.px(12)
        if q > 0 and kind == "wrong":      # the cross slashes on, stroke by stroke
            d.line((x0 + pw - m - ctx.px(60), yy + m, x0 + pw - m - ctx.px(60) + ctx.px(60) * min(1, q * 2), yy + m + ctx.px(60) * min(1, q * 2)), fill=RED + (255,), width=w)
            if q > 0.5: qq = (q - 0.5) * 2; d.line((x0 + pw - m, yy + m, x0 + pw - m - ctx.px(60) * qq, yy + m + ctx.px(60) * qq), fill=RED + (255,), width=w)
        if q > 0 and kind == "right":
            bx, by = x0 + pw - m - ctx.px(60), yy + m + ctx.px(30); d.line((bx, by, bx + ctx.px(22) * min(1, q * 2), by + ctx.px(26) * min(1, q * 2)), fill=GREEN + (255,), width=w)
            if q > 0.5: qq = (q - 0.5) * 2; d.line((bx + ctx.px(22), by + ctx.px(26), bx + ctx.px(22) + ctx.px(44) * qq, by + ctx.px(26) - ctx.px(56) * qq), fill=GREEN + (255,), width=w)

def slider(cv: Image.Image, ctx: D.Ctx, sl: dict, t: float) -> None:
    """Make it easier or harder: a track from EASIER to HARDER whose knob slides to each end as that version is said, the version written under its end."""
    d = ImageDraw.Draw(cv, "RGBA"); x0, x1, y = int(ctx.W * 0.14), int(ctx.W * 0.86), int(ctx.H * 0.46); a = min(1.0, t / 0.4)
    d.rounded_rectangle((x0, y - ctx.px(8), x1, y + ctx.px(8)), radius=ctx.px(8), fill=T.DIM + (int(255 * a),))
    _txt(d, ctx, (x0, y - ctx.px(96)), "EASIER", 40, GREEN, a, head=False); _txt(d, ctx, (x1 - ctx.px(170), y - ctx.px(96)), "HARDER", 40, RED, a, head=False)
    pos = 0.5
    for key, end in (("easier", 0.0), ("harder", 1.0)):
        s = sl.get(key)
        if not s or t < s["at"]: continue
        q = T.ease_in_out(min(1.0, (t - s["at"]) / 0.6)); pos = pos + (end - pos) * q
        f = ctx.font(T.HEAD_FONT, 54); lines = _wrap_lines(d, s["text"], f, (x1 - x0) * 0.45); ly = y + ctx.px(60)
        for ln in lines: _txt(d, ctx, (x0 if end == 0 else x1 - D._text_w(d, ln, f, ctx.px(1)), ly), ln, 54, T.WHITE, min(1, (t - s["at"]) / 0.4)); ly += ctx.px(64)
    kx = x0 + (x1 - x0) * pos; kr = ctx.px(30); col = tuple(int(g + (r - g) * pos) for g, r in zip(GREEN, RED))
    d.rectangle((x0, y - ctx.px(8), kx, y + ctx.px(8)), fill=col + (int(255 * a),)); d.ellipse((kx - kr, y - kr, kx + kr, y + kr), fill=(20, 20, 22, 255), outline=col + (255,), width=ctx.px(6))

def dial(cv: Image.Image, ctx: D.Ctx, dl: dict, t: float) -> None:
    """How hard: a gauge from green to red whose needle swings up to the stated effort, the number under it."""
    d = ImageDraw.Draw(cv, "RGBA"); cx, cy, r = int(ctx.W * 0.30), int(ctx.H * 0.62), int(ctx.H * 0.30); a = min(1.0, t / 0.4)
    for i in range(40):      # the scale: green to red
        f0 = i / 40; col = tuple(int(g + (rr - g) * f0) for g, rr in zip(GREEN, RED)); a0 = math.radians(180 + 180 * f0); a1 = math.radians(180 + 180 * (i + 0.8) / 40)
        d.arc((cx - r, cy - r, cx + r, cy + r), math.degrees(a0), math.degrees(a1), fill=col + (int(255 * a),), width=ctx.px(22))
    p = T.ease_back(min(1.0, max(0.0, (t - dl["at"]) / 0.9))); v = dl["value"] * min(1.0, p); ang = math.radians(180 + 180 * v / dl["max"])
    d.line((cx, cy, cx + (r - ctx.px(40)) * math.cos(ang), cy + (r - ctx.px(40)) * math.sin(ang)), fill=T.WHITE + (255,), width=ctx.px(8)); d.ellipse((cx - ctx.px(16), cy - ctx.px(16), cx + ctx.px(16), cy + ctx.px(16)), fill=T.WHITE + (255,))
    land = t - dl["at"] - 0.9
    if 0 <= land < 0.7: q = T.ease_out(land / 0.7); rr = r * (1.0 + 0.15 * q); d.arc((cx - rr, cy - rr, cx + rr, cy + rr), 180, 360, fill=T.ORANGE + (int(200 * (1 - q)),), width=ctx.px(6))
    _txt(d, ctx, (cx, cy + ctx.px(26)), f"{v:.0f}" if dl["max"] == 10 else f"{v:.0f}", 120, T.ORANGE if land >= 0 else T.WHITE, 1, centre=True); _txt(d, ctx, (cx, cy + ctx.px(160)), dl["label"], 34, T.GREY, a, head=False, centre=True)

def study(cv: Image.Image, ctx: D.Ctx, st: dict, t: float) -> None:
    """The evidence: a stack of papers that fans in, its count rolling up to the stated number, what was studied under it."""
    d = ImageDraw.Draw(cv, "RGBA"); cx, cy = int(ctx.W * 0.28), int(ctx.H * 0.52); w, h = int(ctx.H * 0.40), int(ctx.H * 0.52); p = (t - st["at"]) / 0.8
    for i in range(3, -1, -1):      # the papers fan in, back to front
        q = T.ease_out(min(1.0, max(0.0, p - 0.12 * i))); ang = (i - 1.5) * 4 * q; off = (i - 1.5) * ctx.px(26) * q
        card = Image.new("RGBA", (w, h), (0, 0, 0, 0)); dc = ImageDraw.Draw(card); dc.rounded_rectangle((0, 0, w - 1, h - 1), radius=ctx.px(16), fill=(236, 232, 224, int(255 * min(1, q * 2))))
        for k in range(3): dc.rectangle((ctx.px(30), ctx.px(90) + k * ctx.px(30), w - ctx.px(30 + (k % 3) * 40), ctx.px(100) + k * ctx.px(30)), fill=(170, 165, 158, int(255 * min(1, q * 2))))
        card = card.rotate(ang, resample=Image.BICUBIC, expand=True); cv.paste(card, (int(cx - card.width / 2 + off), int(cy - card.height / 2)), card)
    d = ImageDraw.Draw(cv, "RGBA"); e = T.ease_out(min(1.0, max(0.0, p))); v = st["value"] * e
    if st.get("year"): import datetime; y0 = datetime.date.today().year; v = y0 + (st["value"] - y0) * e      # a year rolls back from today to the one stated
    _txt(d, ctx, (cx, cy - h / 2 + ctx.px(24)), st["kind"], 32, T.ORANGE_DEEP, min(1, p * 2), head=False, centre=True)
    _txt(d, ctx, (cx, cy - ctx.px(10)), f"{v:.0f}" if st.get("year") else f"{v:,.0f}", 130, (24, 24, 26), min(1, p * 2), centre=True); _txt(d, ctx, (cx, cy + ctx.px(140)), st["noun"], 40, (60, 60, 62), min(1, p * 2), head=False, centre=True)

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
        col = GREEN if s["dir"] == "up" else RED if s["dir"] == "down" else T.SOFT_WHITE; d.line(line, fill=col + (255,), width=ctx.px(9), joint="curve"); head = line[-1]
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
            bx, by, s = x + cw / 2 - ctx.px(34), yy + ch * 0.58, ctx.px(1); d.line((bx, by, bx + 24 * s * min(1, q * 2), by + 26 * s * min(1, q * 2)), fill=(20, 20, 22, 255), width=ctx.px(10))
            if q > 0.5: qq = (q - 0.5) * 2; d.line((bx + 24 * s, by + 26 * s, bx + 24 * s + 46 * s * qq, by + 26 * s - 56 * s * qq), fill=(20, 20, 22, 255), width=ctx.px(10))
    last = max(on.values()) if on else 0.0; _txt(d, ctx, (ctx.W / 2, y0 + ch + ctx.px(46)), cl["total"], 58, T.WHITE, (t - last - 0.3) / 0.4, centre=True)

def result(cv: Image.Image, ctx: D.Ctx, rs: dict, t: float) -> None:
    """A result board: one row per band the narration states, revealed as it is said with what it means; the band being said is lit, the ones before step back."""
    d = ImageDraw.Draw(cv, "RGBA"); tiers = rs["tiers"]; n = len(tiers); x0, x1 = int(ctx.W * 0.16), int(ctx.W * 0.84); rh = ctx.px(128); y0 = int(ctx.H * 0.48 - n * rh / 2)
    _txt(d, ctx, (x0, y0 - ctx.px(70)), "YOUR RESULT", 34, T.ORANGE, t / 0.4, head=False); live = [i for i, tr in enumerate(tiers) if t >= tr["at"]]; k = live[-1] if live else -1
    for i, tr in enumerate(tiers):
        y = y0 + i * rh; col = tuple(int(g + (r - g) * (i / max(1, n - 1))) for g, r in zip(RED, GREEN)); p = (t - tr["at"]) / 0.45
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
        d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=ctx.px(22), fill=(28, 28, 31, int(255 * a)), outline=T.DIM + (int(255 * a),), width=ctx.px(3))
        r = ctx.px(40); d.ellipse((x0 + ctx.px(40), y0 + ctx.px(40), x0 + ctx.px(40) + 2 * r, y0 + ctx.px(40) + 2 * r), fill=T.ORANGE + (int(255 * a),)); _txt(d, ctx, (x0 + ctx.px(150), y0 + ctx.px(44)), "YOU", 30, T.GREY, a, head=False)
        txt = en["text"]; k = int((t - at - 0.6) / 0.045)
        if t < at + 0.6:      # typing dots before the words come
            for j in range(3): q = 0.5 + 0.5 * math.sin((t * 6) - j * 0.9); rr = ctx.px(9); cx, cy = x0 + ctx.px(170) + j * ctx.px(34), y0 + ctx.px(130); d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=T.SOFT_WHITE + (int(255 * a * q),))
        else:
            typed = txt[:max(0, min(len(txt), k))]; f = ctx.font(T.HEAD_FONT, 50); lines = _wrap_lines(d, typed, f, bw - ctx.px(200)); yy = y0 + ctx.px(96)
            for ln in lines[:2]: _txt(d, ctx, (x0 + ctx.px(150), yy), ln, 50, T.WHITE, 1); yy += ctx.px(60)
            if len(typed) == len(txt) and txt: hp = T.ease_out((t - at - 0.6 - len(txt) * 0.045) / 0.4); d.rectangle((x0, y0 + bh - ctx.px(10), x0 + int(bw * hp), y0 + bh), fill=T.ORANGE + (255,))
        _txt(d, ctx, (ctx.W / 2, y0 + bh + ctx.px(40)), "COMMENT BELOW", 34, T.ORANGE, a, head=False, centre=True)
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
    d.rounded_rectangle((x, y, x + w, y + ctx.px(84)), radius=ctx.px(16), fill=(14, 14, 16, int(230 * a)), outline=T.ORANGE + (int(255 * a),), width=ctx.px(3))
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
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=ctx.px(34), fill=(34, 34, 38, int(255 * a))); d.polygon([(x0, y0 + bh - ctx.px(60)), (x0 - ctx.px(30), y0 + bh), (x0 + ctx.px(50), y0 + bh - ctx.px(20))], fill=(34, 34, 38, int(255 * a)))
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
