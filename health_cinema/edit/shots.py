"""Shot renderers. A shot spec (plain JSON, see director.py) fully determines its frames: frame(t) is a pure function of the spec and the shot-local time t
(seconds, negative / past the end inside the transition handles). Rendered shots are cached as clips by pipeline.py.

Kinds: footage (full | framed | split layouts), anatomy (the app's Three.js journey clip, composited), counter, bar, timeline, statement, stat, evidence, chapter."""
from __future__ import annotations
import math, random, re
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import gfx, grade, media, motion as M, typo
from .gfx import WHITE, SOFT, MUTED, Units

def _even(v: float) -> int: return int(round(v / 2.0)) * 2

def _draw_overlays(im: Image.Image, spec: dict, U: Units, t: float, dur: float, accent) -> None:
    for o in spec.get("overlays") or []:
        ty = o["type"]
        if ty == "chip":
            px = U.u(36); x = U.margin if o.get("pos", "tl") in ("tl", "bl") else U.W - U.margin; y = U.u(86) if o.get("pos", "tl") in ("tl", "tr") else U.H - U.u(230)
            typo.chip(im, o["text"], x, y, px, accent, t, o["t0"], o["t1"], "left" if o.get("pos", "tl") in ("tl", "bl") else "right")
        elif ty == "title":
            k = typo.Kinetic(o["text"], U.u(o.get("px", 92)), int(U.W * o.get("max_w", 0.55)), accent, "demi", o.get("align", "left"), set(o.get("emph", [])))
            k.draw(im, int(U.W * o.get("x", 0.0625)), int(U.H * o.get("y", 0.30)), t, o["t0"], 0.08, 0.7, o.get("t_out"), 0.4)
        elif ty == "kicker":
            typo.kicker(im, o["text"], U.margin, int(U.H * o.get("y", 0.2)), U.u(26), accent, t, o["t0"])
        elif ty == "tag":      # small honest label on stock footage that is not the person in the story
            a = M.fade_inout(t, o["t0"], o["t1"], 0.4, 0.5)
            if a > 0.01:
                tile = gfx.text_tile(o["text"].upper(), U.u(22), "demi", MUTED if o.get("quiet") else SOFT, 4, 0.14); pad = int(U.u(22) * 0.35) + 8
                gfx.paste(im, tile, U.W - U.margin - (tile.width - 2 * pad) - pad, U.u(54) - pad, a * 0.9)

def _dust_sheet(W: int, H: int, seed: int) -> Image.Image:
    """Out-of-focus motes on a sheet wider than the frame; panned at a different rate from the footage to read as foreground depth."""
    rnd = random.Random(seed); sheet = Image.new("RGBA", (int(W * 1.6), H), (0, 0, 0, 0))
    for _ in range(26):
        s = int(rnd.uniform(0.012, 0.05) * H); b = gfx.radial_blob(max(8, s), (255, 244, 225), rnd.randint(28, 70)); sheet.alpha_composite(b, (rnd.randint(0, sheet.width - s), rnd.randint(0, H - s)))
    return sheet

class _Base:
    def __init__(self, spec: dict, W: int, H: int, handle: int):
        self.spec, self.W, self.H, self.hs = spec, W, H, handle / media.FPS; self.U = Units(W, H); self.dur = spec["t1"] - spec["t0"]; self.accent = tuple(spec.get("accent") or (255, 96, 80))
    def frame(self, t: float, i: int) -> Image.Image: raise NotImplementedError

# ---- footage ---------------------------------------------------------------------------------------------------------------------------
class FootageShot(_Base):
    def __init__(self, spec, W, H, handle, cancel=None):
        super().__init__(spec, W, H, handle); cm = spec.get("camera") or {}; n = round(self.dur * media.FPS) + 2 * handle
        self.cam = M.camera_path(cm.get("move", "push_in"), self.dur, cm.get("amount", 0.12), tuple(cm.get("focus", (0.5, 0.5))), self.hs, int(spec.get("seed", 0)))
        self.SW, self.SH = _even(W * 1.4), _even(H * 1.4); self.base_zoom = float((spec.get("camera") or {}).get("base", 1.0))
        sp_ = float(spec.get("speed", 1.0)); self.reader = media.read_frames(spec["src"], self.SW, self.SH, spec["src_in"] - self.hs / sp_, n, loop=True, cancel=cancel, speed=sp_)
        pf = media.poster(spec["src"], spec["src_in"] + self.dur / 2); self.gain = grade.exposure_gain(grade.measure_luma(pf)) if spec.get("normalize", True) else 1.0
        self.look = spec.get("look", "neutral"); self.dust = _dust_sheet(W, H, int(spec.get("seed", 0)) + 11); self.layout = spec.get("layout", "full")
        self.bokeh = spec.get("dust", True)
    def _camera_frame(self, src: Image.Image, t: float, out_w: int, out_h: int, extra_zoom: float = 1.0) -> Image.Image:
        z, cx, cy = self.cam(t); ext = M.crop_extent(self.SW, self.SH, z * extra_zoom * self.base_zoom, cx, cy)
        if out_w != self.W or out_h != self.H:   # window with a different aspect: crop the same camera region to it
            aw = out_w / out_h; w = ext[2] - ext[0]; h = w / aw
            if h > ext[3] - ext[1]: h = ext[3] - ext[1]; w = h * aw
            cxp, cyp = (ext[0] + ext[2]) / 2, (ext[1] + ext[3]) / 2; ext = (cxp - w / 2, cyp - h / 2, cxp + w / 2, cyp + h / 2)
        return src.transform((out_w, out_h), Image.EXTENT, ext, Image.BICUBIC)
    def frame(self, t, i):
        U, W, H = self.U, self.W, self.H; src = next(self.reader); sp = self.spec; lay = self.layout
        boost = 1.0 + 0.06 * M.smooth((t - 0.0) / max(0.5, self.dur)) * sp.get("light_push", 0.0)
        if lay == "full":
            im = grade.apply(self._camera_frame(src, t, W, H), self.look, self.gain, boost)
            if self.bokeh:
                z, cx, cy = self.cam(t); off = int(((cx - 0.5) * -2.4 * W) + t * U.u(10)) % (self.dust.width - W)
                layer = self.dust.crop((off, 0, off + W, H)); im.paste(layer, (0, 0), layer)
        elif lay == "framed":
            ww = int(W * 0.56); wh = int(ww * 9 / 16); wx = W - U.margin - ww; wy = (H - wh) // 2 - U.u(26)
            fg = grade.apply(self._camera_frame(src, t, ww, wh), self.look, self.gain, boost)
            bg = grade.apply(self._camera_frame(src, t, W, H, 1.0 + 0.0), self.look, self.gain * 0.5, 1.0).resize((W // 12, H // 12), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2)).resize((W, H), Image.BICUBIC)
            bgz = 1.06 + 0.02 * math.sin(t * 0.4); im = bg.transform((W, H), Image.EXTENT, (W * (1 - 1 / bgz) / 2 - t * U.u(3), H * (1 - 1 / bgz) / 2, W - W * (1 - 1 / bgz) / 2 - t * U.u(3), H - H * (1 - 1 / bgz) / 2), Image.BICUBIC)
            im = gfx.vignette(Image.blend(im, Image.new("RGB", (W, H), (6, 10, 20)), 0.35), 0.5)
            a = M.out_cubic(t / 0.7) if t < 5 else 1.0; ox = int((1 - a) * U.u(70))
            panel = gfx.glass_panel(ww, wh, U.u(14), self.accent, False); gfx.paste(im, panel, wx - 24 + ox, wy - 24, a)
            mask = gfx.aa(ww, wh, lambda d, ss: d.rounded_rectangle([0, 0, ww * ss, wh * ss], radius=U.u(14) * ss, fill=(255, 255, 255, 255))).getchannel("A")
            m2 = mask.point([int(v * a) for v in range(256)]); im.paste(fg, (wx + ox, wy), m2)
        else:   # split: the footage panel opens from the right edge over a typographic panel
            pw_full = int(W * 0.58); e = M.out_cubic((t + 0.0) / 0.9) if t < 5 else 1.0; pw = max(2, int(pw_full * e)); full = grade.apply(self._camera_frame(src, t, W, H), self.look, self.gain, boost)
            im = Backdrop_cache(self, t)
            im.paste(full.crop((W - pw_full, 0, W - pw_full + pw, H)), (W - pw, 0))
            gfx.fill_rect(im, (W - pw - 3, 0, W - pw, H), self.accent, 0.9 * e)
            self._profile_panel(im, t, W - pw_full - U.margin)
        _draw_overlays(im, sp, U, t, self.dur, self.accent); return im
    def _profile_panel(self, im, t, max_x):
        U = self.U; p = self.spec.get("profile") or {}; typo.kicker(im, p.get("kicker", ""), U.margin, int(U.H * 0.20), U.u(26), self.accent, t, 0.3)
        name = typo.Kinetic(p.get("title", ""), U.u(120), int(max_x * 0.95), self.accent, "bold", "left", set(p.get("title_emph", []))); name.draw(im, U.margin, int(U.H * 0.27), t, p.get("title_t0", 0.5), 0.08, 0.7)
        y = int(U.H * 0.27) + U.u(150)
        for k, row in enumerate(p.get("rows", [])):
            a = M.out_cubic((t - row["t0"]) / 0.55)
            if a <= 0: continue
            gfx.fill_rect(im, (U.margin, y + U.u(6), U.margin + int(U.u(40) * a), y + U.u(8)), self.accent, 1.0)
            tile = gfx.text_tile(row["text"], U.u(46), "medium", WHITE if k else SOFT, 4); pad = int(U.u(46) * 0.35) + 8
            gfx.paste(im, tile, U.margin + U.u(58) - pad + int((1 - a) * U.u(24)), y - pad - U.u(8), a); y += U.u(74)
        if p.get("note"):
            tile = gfx.text_tile(p["note"], U.u(26), "regular", MUTED); pad = int(U.u(26) * 0.35)
            gfx.paste(im, tile, U.margin - pad, int(U.H * 0.74) - pad, M.fade_inout(t, 1.0, 1e9, 0.5, 0.3))

def Backdrop_cache(shot: _Base, t: float) -> Image.Image:
    bd = getattr(shot, "_bd", None)
    if bd is None: bd = shot._bd = gfx.Backdrop(shot.W, shot.H, shot.accent, int(shot.spec.get("seed", 0)) + 5)
    return bd.frame(t)

# ---- anatomy (3D journey clip) ---------------------------------------------------------------------------------------------------------
class AnatomyShot(_Base):
    def __init__(self, spec, W, H, handle, cancel=None):
        super().__init__(spec, W, H, handle); self.n_body = round(self.dur * media.FPS); self.handle = handle
        body = media.read_frames(spec["clip"], W, H, 0.0, self.n_body, loop=False, cancel=cancel)
        self.frames = body; self.first = None; self.i = 0
    def frame(self, t, i):
        U, W, H = self.U, self.W, self.H
        if i < self.handle:
            if self.first is None: self.first = next(self.frames); self.i = 1
            src = self.first
        else:
            src = next(self.frames, None) if self.i < self.n_body + 0 else None
            if src is None: src = self.last
            else: self.i += 1
            if i == self.handle and self.first is not None and self.i == 1: pass
        self.last = src
        im = gfx.vignette(src, 0.18)
        # HUD: corner brackets that draw on, and the disclaimer that must stay on every 3D illustration
        a = M.out_cubic((t + 0.2) / 0.8); L = int(U.u(56) * a); m = U.u(54); wd = max(2, U.u(3)); col = (*self.accent, 200)
        d = ImageDraw.Draw(im, "RGBA")
        for (x, y, sx, sy) in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
            d.line([x, y, x + sx * L, y], fill=col, width=wd); d.line([x, y, x, y + sy * L], fill=col, width=wd)
        ill = self.spec.get("illustrative") or "3D illustration. Not clinical imagery."
        aa_ = M.fade_inout(t, 0.2, self.dur + 1.0, 0.6, 0.01)
        tile = gfx.text_tile(ill.upper().replace(".", " ·").rstrip(" ·"), U.u(22), "demi", SOFT, 4, 0.12); pad = int(U.u(22) * 0.35) + 8
        gfx.paste(im, tile, W - U.margin - (tile.width - 2 * pad) - pad, H - U.u(58) - pad, aa_ * 0.95)
        _draw_overlays(im, self.spec, U, t, self.dur, self.accent); return im

# ---- data graphics ---------------------------------------------------------------------------------------------------------------------
class DataShot(_Base):
    def __init__(self, spec, W, H, handle, cancel=None):
        super().__init__(spec, W, H, handle); self.bd = gfx.Backdrop(W, H, self.accent, int(spec.get("seed", 0)) + 3); self.plate = None
        if spec.get("plate"):
            try: self.plate = gfx.blur_plate(media.poster(spec["plate"], spec.get("plate_t", 1.0)), W, H, 0.55)
            except Exception: self.plate = None
    def base(self, t) -> Image.Image:
        return self.bd.frame(t, self.plate, 0.55 if self.plate is not None else 0.0)
    def notes(self, im, t, lines: List[str], source: str, y0: Optional[float] = None) -> None:
        U = self.U; y = int(U.H * (y0 if y0 else 0.715)); a = M.out_cubic((t - 0.9) / 0.6)
        for ln in lines:
            tile = gfx.text_tile(ln, U.u(30), "medium", SOFT, 5); pad = gfx.tile_pad(U.u(30), 5); gfx.paste(im, tile, U.margin - pad, y - pad, a); y += U.u(42)
        if source:
            sp_ = U.u(28); w, h = gfx.text_size(source.upper(), sp_, "demi", 0.08); box_w = w + U.u(50)
            gfx.paste(im, gfx.glass_panel(box_w, U.u(46), U.u(23), self.accent), U.margin - 24, y + U.u(2) - 24, a)
            gfx.fill_rect(im, (U.margin + U.u(14), y + U.u(21), U.margin + U.u(22), y + U.u(29)), self.accent, a)
            tile = gfx.text_tile(source.upper(), sp_, "demi", SOFT, 0, 0.08); pad = int(sp_ * 0.35); gfx.paste(im, tile, U.margin + U.u(34) - pad, y + U.u(25) - h // 2 - pad, a)
        ill = self.spec.get("illustrative")
        if ill: tile = gfx.text_tile(ill, U.u(24), "regular", MUTED); gfx.paste(im, tile, U.margin - 8, U.H - U.u(100), a)
    def frame(self, t, i):
        im = self.base(t); self.draw(im, t); _draw_overlays(im, self.spec, self.U, t, self.dur, self.accent); return im
    def draw(self, im, t): raise NotImplementedError

class CounterShot(DataShot):
    def draw(self, im, t):
        U, W, H, g, acc = self.U, self.W, self.H, self.spec["gfx"], self.accent; n = g["interval"]; unit = g["unit"]; cyc = g.get("cycle_s", 2.4)
        typo.kicker(im, g.get("kicker", "Average frequency"), U.margin, int(H * 0.225), U.u(26), acc, t, 0.1)
        head = typo.Kinetic(f"Every {n} {unit}", U.u(104), int(W * 0.56), acc, "bold", "left", {1}); head.draw(im, U.margin, int(H * 0.285), t, 0.2, 0.09, 0.75)
        ctx = g.get("context", "")
        if ctx:
            k2 = typo.Kinetic(ctx, U.u(44), int(W * 0.42), acc, "regular", "left", set(), SOFT); k2.draw(im, U.margin, int(H * 0.285) + head.h + U.u(36), t, 0.75, 0.04, 0.6)
        cx, cy, r = int(W * 0.735), int(H * 0.45), int(H * 0.27); phase = (t / cyc) % 1.0; done = int(t // cyc) if t > 0 else 0; e = M.in_out_cubic(phase) if t > 0 else 0.0
        ent = M.out_cubic((t - 0.1) / 0.8); size = 2 * r + U.u(120)
        def ring(d, ss):
            c = size * ss // 2; R = r * ss; wd = U.u(10) * ss
            d.ellipse([c - R, c - R, c + R, c + R], outline=(40, 56, 88, 255), width=wd)
            for k in range(60):
                a = math.radians(k * 6 - 90); inner = R - wd - U.u(18) * ss * (1.6 if k % 5 == 0 else 1.0); outer = R - wd - U.u(6) * ss
                lit = (k / 60.0) <= e; col = (*acc, 255) if lit else (70, 88, 124, 255)
                d.line([c + inner * math.cos(a), c + inner * math.sin(a), c + outer * math.cos(a), c + outer * math.sin(a)], fill=col, width=max(2, U.u(3) * ss))
            if e > 0: d.arc([c - R, c - R, c + R, c + R], -90, -90 + 360 * e, fill=(*acc, 255), width=wd)
        lay = gfx.aa(size, size, ring, 2); base_a = ent
        gl = gfx.glow(lay, U.u(16), 1.1); gfx.paste(im, gl, cx - size // 2, cy - size // 2, 0.55 * base_a); gfx.paste(im, lay, cx - size // 2, cy - size // 2, base_a)
        ang = math.radians(-90 + 360 * e); hx, hy = cx + (r - U.u(5)) * math.cos(ang), cy + (r - U.u(5)) * math.sin(ang); hr = U.u(15)
        gfx.paste(im, gfx.aa(hr * 4, hr * 4, lambda d, ss: d.ellipse([hr * ss, hr * ss, 3 * hr * ss, 3 * hr * ss], fill=(255, 255, 255, 255))), int(hx - 2 * hr), int(hy - 2 * hr), base_a)
        shown = round(n * e) if phase > 0 or t <= 0 else 0
        typo.draw_number(im, f"{shown}", cx, cy - U.u(92), U.u(190), WHITE, "center", "bold", base_a, U.u(10))
        tile = gfx.text_tile(unit.upper(), U.u(32), "demi", SOFT, 0, 0.2); pad = int(U.u(32) * 0.35); gfx.paste(im, tile, cx - (tile.width - 2 * pad) // 2 - pad, cy + U.u(118) - pad, base_a)
        # completed-cycle pulse and tally
        if t > 0 and phase < 0.28 and done >= 1:
            pk = phase / 0.28; rr = int(r + U.u(30) + U.u(110) * pk); layer = gfx.aa(2 * rr + 8, 2 * rr + 8, lambda d, ss: d.ellipse([4 * ss, 4 * ss, (2 * rr + 4) * ss, (2 * rr + 4) * ss], outline=(*acc, 255), width=U.u(4) * ss))
            gfx.paste(im, layer, cx - rr - 4, cy - rr - 4, (1 - pk) * 0.8)
        tally_n = min(done, 12); ty = cy + r + U.u(70); step = U.u(44); x0 = cx - (11 * step) // 2
        for k in range(12):
            on = k < tally_n; pop = M.out_back((t - (k + 1) * cyc) / 0.35) if on else 0.0; rad = int(U.u(11) * (0.5 + 0.5 * pop)) if on else U.u(6)
            col = acc if on else (60, 78, 112); gfx.paste(im, gfx.aa(2 * rad + 4, 2 * rad + 4, lambda d, ss: d.ellipse([2 * ss, 2 * ss, (2 * rad + 2) * ss, (2 * rad + 2) * ss], fill=(*col, 255))), x0 + k * step - rad - 2, ty - rad - 2, base_a)
        lab = f"{done} {g.get('event', 'events')} so far in this animation"; tile = gfx.text_tile(lab, U.u(28), "medium", acc, 0, 0.02); pad = int(U.u(28) * 0.35)
        gfx.paste(im, tile, cx - (tile.width - 2 * pad) // 2 - pad, ty + U.u(30) - pad, base_a)
        self.notes(im, t, ["Time is compressed: this illustrates the stated average, it is not a live count."], g.get("source_line") or "Source needed (flagged for review)", 0.73)

class BarShot(DataShot):
    def draw(self, im, t):
        U, W, H, g, acc = self.U, self.W, self.H, self.spec["gfx"], self.accent; val = float(g["value"]); k = M.in_out_cubic((t - 0.55) / 1.9); shown = val * k
        typo.kicker(im, g.get("kicker", "The figure"), U.margin, int(H * 0.18), U.u(26), acc, t, 0.1)
        if g.get("qualifier"):
            tile = gfx.text_tile(g["qualifier"], U.u(60), "medium", SOFT, 4); pad = int(U.u(60) * 0.35); gfx.paste(im, tile, U.margin - pad, int(H * 0.25) - pad, M.out_cubic((t - 0.15) / 0.5))
        typo.draw_number(im, f"{shown:.0f}%", U.margin, int(H * 0.31), U.u(330), acc, "left", "bold", M.out_cubic((t - 0.15) / 0.5), U.u(14))
        if g.get("context"):
            kk = typo.Kinetic(g["context"], U.u(42), int(W * 0.44), acc, "regular", "left", set(), SOFT); kk.draw(im, U.margin, int(H * 0.31) + U.u(380), t, 1.2, 0.04, 0.6)
        cell, rad = U.u(52), U.u(15); gx0 = int(W * 0.60); gy0 = int(H * 0.2); lit_n = int(round(shown)); ent = M.out_cubic((t - 0.1) / 0.8)
        for idx in range(100):
            r_, c_ = divmod(idx, 10); on = idx < lit_n; x = gx0 + c_ * cell; y = gy0 + r_ * cell
            pulse = M.out_cubic((t - 2.6 - 0.012 * idx) / 0.4) * (1 - M.smooth((t - 2.6 - 0.012 * idx - 0.4) / 0.6)) if on else 0.0
            rr = rad + int(U.u(3) * pulse); col = acc if on else (46, 62, 96)
            layer = gfx.aa(2 * rr + 4, 2 * rr + 4, lambda d, ss: d.ellipse([2 * ss, 2 * ss, (2 * rr + 2) * ss, (2 * rr + 2) * ss], fill=(*col, 255)))
            gfx.paste(im, layer, x - rr - 2, y - rr - 2, ent * (0.28 + 0.72 * ent) if not on else ent)
        tile = gfx.text_tile("Each dot = 1 in 100. Illustrative.", U.u(24), "regular", MUTED); pad = int(U.u(24) * 0.35); gfx.paste(im, tile, gx0 - rad - pad, gy0 + 10 * cell - rad + U.u(10) - pad, ent)
        self.notes(im, t, [], g.get("source_line") or "Source needed: not shown as established fact until a source is attached", 0.74)

class TimelineShot(DataShot):
    def draw(self, im, t):
        U, W, H, g, acc = self.U, self.W, self.H, self.spec["gfx"], self.accent; ev = g["events"]; n = max(1, len(ev))
        typo.kicker(im, g.get("kicker", "What happened, in order"), U.margin, int(H * 0.10), U.u(26), acc, t, 0.1)
        y = int(H * 0.50); x0, x1 = U.margin + U.u(200), W - U.margin - U.u(200); xs = [x0 + (x1 - x0) * (i / max(1, n - 1)) for i in range(n)] if n > 1 else [(x0 + x1) / 2]
        lw = U.u(8); gfx.fill_rect(im, (x0, y - lw // 2, x1, y + lw // 2), (44, 60, 94), M.out_cubic(t / 0.6))
        cur = max([k for k, e in enumerate(ev) if t >= e["t0"]] or [-1])
        if cur >= 0:
            prog = xs[cur - 1] + (xs[cur] - xs[cur - 1]) * M.in_out_cubic((t - ev[cur]["t0"]) / 0.55) if cur > 0 else xs[0]
            gfx.fill_rect(im, (x0, y - lw // 2, int(prog), y + lw // 2), acc, 1.0)
            gfx.paste(im, gfx.glow(gfx.aa(int(prog - x0) + 40, 40, lambda d, ss: d.rectangle([20 * ss, 16 * ss, (20 + prog - x0) * ss, 24 * ss], fill=(*acc, 255))), U.u(10)), x0 - 20, y - 20, 0.5)
        colw = (x1 - x0) / max(1, n - 1) if n > 1 else U.u(900)
        for k, e in enumerate(ev):
            on = t >= e["t0"]; kk = M.out_back((t - e["t0"]) / 0.5) if on else 0.0; rr = int(U.u(20) + U.u(8) * min(1.0, kk))
            gfx.paste(im, gfx.aa(2 * rr + 8, 2 * rr + 8, lambda d, ss: (d.ellipse([4 * ss, 4 * ss, (2 * rr + 4) * ss, (2 * rr + 4) * ss], fill=(*(acc if on else (44, 60, 94)), 255), outline=(255, 255, 255, 255 if on else 70), width=U.u(4) * ss))), int(xs[k]) - rr - 4, y - rr - 4, 1.0)
            if not on: continue
            up = k % 2 == 0; a = M.out_cubic((t - e["t0"] - 0.1) / 0.55); rise = int((1 - a) * U.u(26)) * (1 if up else -1)
            when = gfx.text_tile(e["when"], U.u(60), "bold", WHITE, 4); pad = int(U.u(60) * 0.35)
            lab = typo.Kinetic(e["label"], U.u(38), int(min(colw * 0.92, U.u(560))), acc, "medium", "center", set(), WHITE)
            lh = lab.h; wx = int(xs[k]) - (when.width - 2 * pad) // 2 - pad
            if up:
                gfx.paste(im, when, wx, y - U.u(60) - when.height + rise + pad, a); lab.draw(im, int(xs[k]) - lab.w // 2, y - U.u(60) - when.height + pad - lh - U.u(6), t, e["t0"] + 0.15, 0.03, 0.5)
            else:
                gfx.paste(im, when, wx, y + U.u(50) + rise - pad, a); lab.draw(im, int(xs[k]) - lab.w // 2, y + U.u(50) + when.height - pad + U.u(2), t, e["t0"] + 0.15, 0.03, 0.5)
        self.notes(im, t, ["Order of events only; spacing is not to scale."], g.get("source_line") or "From the narration. A composite example, not a patient record.", 0.755)

class StatementShot(DataShot):
    def draw(self, im, t):
        U, W, H, g, acc = self.U, self.W, self.H, self.spec["gfx"], self.accent; beats = g["beats"]
        for k, b in enumerate(beats):
            t_out = beats[k + 1]["t0"] - 0.05 if k + 1 < len(beats) else None
            words = b["text"].split(); kin = typo.Kinetic(b["text"], U.u(g.get("px", 104)), int(W * 0.78), acc, "demi", "left", typo.emphasis_indices(words, 2))
            if t < b["t0"] - 0.05 or (t_out is not None and t > t_out + 0.8): continue
            kin.draw(im, U.margin, int(H * 0.5 - kin.h / 2), t, b["t0"], 0.07, 0.65, t_out, 0.35)
        if g.get("kicker"): typo.kicker(im, g["kicker"], U.margin, int(H * 0.22), U.u(26), acc, t, 0.1)

class StatShot(DataShot):
    def draw(self, im, t):
        U, W, H, g, acc = self.U, self.W, self.H, self.spec["gfx"], self.accent
        typo.kicker(im, g.get("kicker", "The figure"), U.margin, int(H * 0.2), U.u(26), acc, t, 0.1)
        raw = str(g.get("number", "")); unit = g.get("unit", "")
        try: v = float(raw.replace(",", "")); s = f"{v * M.out_cubic(t / 1.5):,.{0 if v == int(v) else 1}f}" if t < 1.5 else raw
        except ValueError: s = raw
        w = typo.draw_number(im, s, U.margin, int(H * 0.27), U.u(290), acc, "left", "bold", M.out_cubic(t / 0.5), U.u(14))
        if unit: tile = gfx.text_tile(unit, U.u(150), "bold", acc); pad = int(U.u(150) * 0.35); gfx.paste(im, tile, U.margin + w + U.u(8) - pad, int(H * 0.27) + U.u(120) - pad, M.out_cubic(t / 0.5))
        kk = typo.Kinetic(g.get("context", ""), U.u(44), int(W * 0.7), acc, "regular", "left", set(), SOFT); kk.draw(im, U.margin, int(H * 0.27) + U.u(360), t, 0.9, 0.04, 0.6)
        self.notes(im, t, [], g.get("source_line") or "Source needed (not shown to viewers until attached)", 0.76)

class EvidenceShot(DataShot):
    def draw(self, im, t):
        U, W, H, g, acc = self.U, self.W, self.H, self.spec["gfx"], self.accent
        typo.kicker(im, g.get("heading", "What the evidence says"), U.margin, int(H * 0.17), U.u(26), acc, t, 0.1)
        words = g.get("claim", "").split(); kin = typo.Kinetic(g.get("claim", ""), U.u(62), int(W * 0.76), acc, "demi", "left", typo.emphasis_indices(words, 3)); kin.draw(im, U.margin, int(H * 0.25), t, 0.3, 0.05, 0.65)
        lvl = {"established": "Established evidence", "preliminary": "Preliminary research", "unsourced": "Source needed"}.get(g.get("level", ""), "")
        if lvl: typo.chip(im, lvl, U.margin, int(H * 0.64), U.u(30), acc, t, 1.0, 1e9)
        self.notes(im, t, [], g.get("source_line") or ("" if g.get("level") == "unsourced" else "Source needed"), 0.74)

class ChapterShot(DataShot):
    def draw(self, im, t):
        U, W, H, g, acc = self.U, self.W, self.H, self.spec["gfx"], self.accent
        typo.kicker(im, g.get("kicker", "Chapter"), U.margin, int(H * 0.40), U.u(26), acc, t, 0.1)
        words = g.get("title", "").split(); kin = typo.Kinetic(g.get("title", ""), U.u(96), int(W * 0.76), acc, "bold", "left", typo.emphasis_indices(words, 1)); kin.draw(im, U.margin, int(H * 0.40) + U.u(60), t, 0.3, 0.08, 0.75)

KINDS = {"footage": FootageShot, "anatomy": AnatomyShot, "counter": CounterShot, "bar": BarShot, "timeline": TimelineShot, "statement": StatementShot, "stat": StatShot,
         "evidence": EvidenceShot, "chapter": ChapterShot}

def render_shot(spec: dict, W: int, H: int, out, handle: int, cancel=None) -> None:
    """Render the shot (body + `handle` frames each side) to an intermediate clip. Written to a .part file and moved into place, so a failure leaves nothing."""
    from pathlib import Path
    out = Path(out); tmp = out.with_suffix(".part.mp4"); n = round((spec["t1"] - spec["t0"]) * media.FPS) + 2 * handle
    shot = KINDS[spec["kind"]](spec, W, H, handle, cancel); enc = media.Encoder(tmp, W, H, 12, "fast")
    try:
        for i in range(n):
            if cancel is not None and cancel.is_set(): raise media.Cancelled("cancelled")
            enc.write(shot.frame((i - handle) / media.FPS, i))
        enc.close(); tmp.replace(out)
    except BaseException:
        enc.abort(); tmp.unlink(missing_ok=True); raise
