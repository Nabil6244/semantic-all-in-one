"""The cast: procedurally drawn paper-cutout characters in the look of the engraved-sepia collage stills: ink outlines, form-following cross-hatching,
halftone dots, light paper-toned fills (cloth in sepia / rust / tan), hand-cut wobbly edges.
Parts are drawn once at SS px/unit, shaded, downsampled to HR px/unit and cached as PNGs under out/puppet_cache/<character>_v<VERSION>_<hash>/
(the hash covers this file's source, the spec and HR, so editing the art rebuilds only what changed)."""
from __future__ import annotations
import hashlib, math
from pathlib import Path
from typing import Dict, List
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .character import HR, Rig

VERSION = 3
SS = 6
CACHE_DIR = Path(__file__).resolve().parents[2] / "out" / "puppet_cache"
INK, INK2 = (31, 22, 15), (58, 40, 28)
SHADOW_C = (66, 36, 22)          # deep warm shadow the tonal shading falls toward (never grey)
LIGHT_C = (255, 232, 190)        # cream light on the lit edge
PAPER, TAN, RUST, KRAFT, LEATHER = (240, 228, 202), (214, 164, 98), (178, 84, 46), (200, 152, 96), (120, 74, 46)
SKIN, SKIN_D = (236, 190, 146), (205, 150, 108)
HATCH_L = (160, 112, 76)

_D = dict(thigh=118, shin=114, foot_h=22, foot_len=70, torso=160, sh_frac=0.9, neck=14, hr=52, uarm=90, farm=80, hand=38)
SPECS: Dict[str, dict] = {
    "suit_man": dict(dims=_D, hip_w=72, waist_w=68, chest_w=88, lw=(60, 48, 38), aw=(36, 30, 24), body="suit", c_body=(64, 112, 110), c_legs=(52, 80, 84), c_shoe=(46, 30, 22),
                     hat="fedora", prop="briefcase", c_hat=(96, 58, 36)),
    "worker": dict(dims={**_D, "thigh": 122, "shin": 118, "torso": 166, "hr": 53, "uarm": 92, "hand": 40}, hip_w=80, waist_w=78, chest_w=100, lw=(62, 50, 40), aw=(38, 32, 26), body="vest",
                   c_body=(214, 150, 66), c_legs=(78, 62, 74), c_shoe=(44, 30, 22), hat="cap", heel=16, c_hat=(70, 98, 104), prop=None),
    "woman": dict(dims={**_D, "thigh": 112, "shin": 110, "foot_len": 62, "torso": 156, "hr": 49, "uarm": 86, "farm": 76, "hand": 34}, hip_w=70, waist_w=54, chest_w=70, lw=(52, 42, 32), aw=(30, 25, 20),
                  body="coat", c_body=(186, 86, 52), c_legs=(92, 64, 54), c_shoe=(46, 30, 22), hat="scarf", ext=26, c_hat=RUST,
                  sway=[dict(part="coat_flap", key="coat", carrier="torso", local=(-28, 8)), dict(part="scarf_tail", key="scarf", carrier="head", local=(-32, -36))]),
    "child": dict(dims=dict(thigh=82, shin=80, foot_h=16, foot_len=50, torso=98, sh_frac=0.9, neck=9, hr=48, uarm=56, farm=52, hand=30), hip_w=56, waist_w=54, chest_w=62, lw=(40, 32, 26), aw=(26, 22, 18),
                  body="jacket", c_body=(226, 164, 64), c_legs=(70, 96, 100), c_shoe=(60, 38, 26), hat="beanie", heel=11, c_hat=(60, 120, 120),
                  sway=[dict(part="scarf_tail", key="scarf", carrier="head", local=(-22, -14))]),
    "silhouette": dict(dims=_D, hip_w=72, waist_w=68, chest_w=88, lw=(60, 48, 38), aw=(36, 30, 24), body="plain", c_body=INK, c_legs=INK, c_shoe=INK, hat="fedora", c_hat=INK, skin=INK),
    "courier": dict(dims={**_D, "torso": 162, "hr": 51}, hip_w=76, waist_w=72, chest_w=94, lw=(60, 48, 38), aw=(38, 31, 25), body="uniform", c_body=(150, 66, 44), c_legs=(66, 52, 48), c_shoe=(40, 28, 20),
                    hat="peak", prop="parcel", c_hat=(96, 44, 30), heel=15),
    "shopkeeper": dict(dims={**_D, "thigh": 112, "shin": 108, "torso": 156, "hr": 52, "uarm": 88, "hand": 38}, hip_w=78, waist_w=82, chest_w=92, lw=(56, 46, 36), aw=(34, 28, 23), body="apron",
                       c_body=(120, 66, 56), c_legs=(84, 70, 60), c_shoe=(44, 30, 22), hat="bald", prop=None, old=True, c_hat=(240, 232, 214), heel=14),
}
for _s in SPECS.values(): _s["dims"] = dict(_s["dims"])


# ---- shapes
def spline(pts, n=6, closed=True):
    P = list(pts); m = len(P); out = []
    for i in range(m if closed else m - 1):
        p0, p1, p2, p3 = P[(i - 1) % m], P[i], P[(i + 1) % m], P[(i + 2) % m]
        if not closed:
            p0 = P[max(i - 1, 0)]; p3 = P[min(i + 2, m - 1)]
        for k in range(n):
            t = k / n; t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    if not closed: out.append(P[-1])
    return out


def wob(pts, amp, seed):
    r = np.random.default_rng(seed); a = np.array(pts, float); n = r.normal(size=a.shape)
    for _ in range(2): n = (np.roll(n, 1, 0) + 2 * n + np.roll(n, -1, 0)) / 4
    return [tuple(p) for p in a + amp * 2.2 * n]


def ellipse(cx, cy, rx, ry, n=40): return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def capsule(p0, p1, w0, w1, n=8):
    (x0, y0), (x1, y1) = p0, p1; L = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / L, (y1 - y0) / L; nx, ny = -uy, ux; pts = []
    for k in range(n + 1):
        a = math.pi * k / n; c, s = math.cos(a), math.sin(a)
        pts.append((x1 + (nx * c + ux * s) * w1 / 2, y1 + (ny * c + uy * s) * w1 / 2))
    for k in range(n + 1):
        a = math.pi * k / n; c, s = math.cos(a), math.sin(a)
        pts.append((x0 + (-nx * c - ux * s) * w0 / 2, y0 + (-ny * c - uy * s) * w0 / 2))
    return pts


def tube(L, prof, n=14, cap=8):
    """Limb outline hanging from (0,0) down to (0,L); prof = [(fraction, width)] (calf/forearm bulges), round caps."""
    fs = np.linspace(0, 1, n); ws = np.interp(fs, [p[0] for p in prof], [p[1] for p in prof])
    pts = [(math.cos(math.pi * k / cap) * ws[0] / 2, -math.sin(math.pi * k / cap) * ws[0] / 2) for k in range(cap + 1)]
    pts += [(-w / 2, f * L) for f, w in zip(fs, ws)]
    pts += [(math.cos(math.pi + math.pi * k / cap) * ws[-1] / 2, L - math.sin(math.pi + math.pi * k / cap) * ws[-1] / 2) for k in range(cap + 1)]
    pts += [(w / 2, f * L) for f, w in zip(fs[::-1], ws[::-1])]
    return pts


def poly_off(pts, dx, dy): return [(x + dx, y + dy) for x, y in pts]


# ---- canvas: draw at SS px/unit, then engrave (hatch / halftone / outline) and downsample
class Cv:
    def __init__(s, x0, y0, x1, y1):
        s.x0, s.y0 = x0, y0; s.w, s.h = int((x1 - x0) * SS) // 2 * 2, int((y1 - y0) * SS) // 2 * 2
        s.im = Image.new("RGBA", (s.w, s.h), (0, 0, 0, 0)); s.d = ImageDraw.Draw(s.im)
        s.dk_im = Image.new("L", (s.w, s.h), 0); s.dkd = ImageDraw.Draw(s.dk_im)
    def P(s, pts): return [((x - s.x0) * SS, (y - s.y0) * SS) for x, y in pts]
    def fill(s, pts, col): s.d.polygon(s.P(pts), fill=tuple(col) + (255,))
    def line(s, pts, col, w): s.d.line(s.P(pts), fill=tuple(col) + (255,), width=max(1, int(w * SS)), joint="curve")
    def paint(s, pts, col):
        t = Image.new("RGBA", s.im.size, (0, 0, 0, 0)); ImageDraw.Draw(t).polygon(s.P(pts), fill=tuple(col) + (255,))
        t.putalpha(ImageChops.multiply(t.getchannel("A"), s.im.getchannel("A"))); s.im.alpha_composite(t)
    def pline(s, pts, col, w):
        """ink line clipped to the part's silhouette"""
        t = Image.new("RGBA", s.im.size, (0, 0, 0, 0)); ImageDraw.Draw(t).line(s.P(pts), fill=tuple(col) + (255,), width=max(1, int(w * 1.3 * SS)), joint="curve")
        t.putalpha(ImageChops.multiply(t.getchannel("A"), s.im.getchannel("A"))); s.im.alpha_composite(t)
    def dk(s, pts, amt):
        """extra shadow (more hatching) inside a polygon, 0..1"""
        s.dkd.polygon(s.P(pts), fill=int(255 * amt))
    def dkl(s, pts, w, amt): s.dkd.line(s.P(pts), fill=int(255 * amt), width=max(1, int(w * SS)), joint="curve")

    def done(s, kind="form", seed=0, pivot=(0, 0), sp=2.8, ink=INK, outline=1.0):
        im = engrave(s, kind, seed, pivot, sp, ink, outline)
        im = im.resize((int(round(s.w * HR / SS)), int(round(s.h * HR / SS))), Image.LANCZOS)
        px, py = (pivot[0] - s.x0) * HR, (pivot[1] - s.y0) * HR
        R = int(math.ceil(max(math.hypot(cx - px, cy - py) for cx in (0, im.width) for cy in (0, im.height)))) + 2
        out = Image.new("RGBA", (2 * R, 2 * R), (0, 0, 0, 0)); out.paste(im, (int(round(R - px)), int(round(R - py)))); return out


def engrave(cv: Cv, kind, seed, pivot, sp_u, ink, outline):
    a = np.asarray(cv.im, np.float32).copy(); al = a[..., 3] / 255; h, w = al.shape
    alpha_im = cv.im.getchannel("A")
    B = np.asarray(alpha_im.filter(ImageFilter.GaussianBlur(5.5 * SS)), np.float32) / 255
    gy, gx = np.gradient(B); mag = np.hypot(gx, gy) + 1e-9
    lam = (gx + gy) * 0.7071 / mag                        # + = faces the light (upper left)
    edge = np.clip(mag / (mag.max() * 0.35), 0, 1)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rng = np.random.default_rng(seed)
    nz = np.asarray(Image.fromarray(rng.normal(size=(h // 90 + 2, w // 90 + 2)).astype(np.float32), "F").resize((w, h), Image.BICUBIC), np.float32)
    extra = np.asarray(cv.dk_im.filter(ImageFilter.GaussianBlur(1.4 * SS)), np.float32) / 255
    dark = np.clip(0.30 - 0.80 * lam * edge + 0.16 * (yy / h) + 0.03 * nz + 0.85 * extra + 0.10 * edge, 0, 1)
    px, py = (pivot[0] - cv.x0) * SS, (pivot[1] - cv.y0) * SS
    xr, yr = (xx - px) / SS, (yy - py) / SS                # units from the part pivot
    sp = sp_u
    # contour hatch: lines that wrap around the limb (curved a little like a cylinder cross-section), thicker where it is darker
    f1 = ((yr + xr * xr / 150.0) / sp) % 1.0
    thr1 = np.clip((dark - 0.22) * 1.25, 0, 0.66)
    px_per_period = sp * SS
    m1 = np.clip((thr1 - f1) * px_per_period / 2.0 + 0.5, 0, 1) * (thr1 > 0.02)
    # cross hatch in the deep shadow, 50 degrees
    f2 = (((xr * 0.64 - yr * 0.77)) / (sp * 0.85)) % 1.0
    thr2 = np.clip((dark - 0.42) * 1.5, 0, 0.5)
    m2 = np.clip((thr2 - f2) * px_per_period * 0.85 / 2.0 + 0.5, 0, 1) * (thr2 > 0.02)
    # halftone dots
    cell = sp * 1.15
    u, v = ((xr + yr) * 0.7071 / cell) % 1.0 - 0.5, ((xr - yr) * 0.7071 / cell) % 1.0 - 0.5
    rad_ = 0.5 * np.sqrt(np.clip(dark - 0.28, 0, 1) * 1.3)
    md = np.clip((rad_ - np.hypot(u, v)) * cell * SS * 0.7 / 1.0 + 0.5, 0, 1) * (dark > 0.38)
    if kind == "form": m = np.maximum(m1, m2)
    elif kind == "dots": m = np.maximum(md * 0.9, m1 * 0.8)
    elif kind == "both": m = np.maximum(np.maximum(m1, m2), md * 0.85)
    else: m = np.zeros_like(m1)
    lum = a[..., :3].mean(-1, keepdims=True)
    tgt = np.where(lum > 80, np.array(ink, np.float32), np.array(HATCH_L, np.float32))
    # tonal modelling first: a deep warm shadow side, a cream-lit edge (so the cloth reads as inked cut paper, never flat grey)
    cl = (al > 0.5)[..., None]
    ks = (np.clip((dark - 0.36) * 1.0, 0, 0.55) * (al > 0.5))[..., None]
    a[..., :3] = a[..., :3] * (1 - ks) + np.array(SHADOW_C, np.float32) * ks
    kl = (np.clip(lam * edge - 0.15, 0, 1) * 0.32 * (al > 0.5))[..., None]
    a[..., :3] = a[..., :3] * (1 - kl) + np.array(LIGHT_C, np.float32) * kl
    k = (m * 0.93 * (al > 0.9))[..., None]
    a[..., :3] = a[..., :3] * (1 - k) + tgt * k
    # ink contour: alpha minus a slightly eroded alpha, width wobbling along the edge
    bl = np.asarray(alpha_im.filter(ImageFilter.GaussianBlur(2.1 * SS * outline)), np.float32) / 255
    wob_n = np.asarray(Image.fromarray(rng.normal(size=(h // 40 + 2, w // 40 + 2)).astype(np.float32), "F").resize((w, h), Image.BICUBIC), np.float32)
    inner = np.clip((bl - (0.86 + 0.055 * np.clip(wob_n, -1.5, 1.5))) / 0.08, 0, 1)
    ln = np.clip(al - inner, 0, 1)[..., None] * 0.99
    a[..., :3] = a[..., :3] * (1 - ln) + np.array(ink, np.float32) * ln
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


# ---- parts
def b_torso(s, seed):
    d = s["dims"]; T = d["torso"]; hw, ww, cw = s["hip_w"], s["waist_w"], s["chest_w"]; ext = s.get("ext", 14); fl = 10 if ext > 14 else 4; st = s["body"]
    sk = s.get("skin", SKIN)
    ctl = [(-hw * .5 - fl * .5, ext), (-ww * .5 - 1, -T * .3), (-cw * .5, -T * .7), (-cw * .46, -T * .92), (-cw * .22, -T * 1.0), (cw * .12, -T * 1.02), (cw * .36, -T * .96), (cw * .52, -T * .82),
           (cw * .54, -T * .6), (ww * .52, -T * .3), (hw * .5 + 5, 0), (hw * .5 + fl, ext)]
    pts = wob(spline(ctl, 6), 0.7, seed); cv = Cv(-cw - 24, -T - 28, cw + 24, ext + 20)
    cv.fill(pts, s["c_body"])
    cv.dk([(-cw, -T * 1.1), (-cw * .22, -T * 1.1), (-cw * .3, -T * .5), (-cw * .5, ext + 4), (-cw, ext + 4)], 0.55)        # back in shade
    cv.dk([(cw * .1, -T * .35), (cw * .6, -T * .35), (cw * .6, ext + 4), (cw * .1, ext + 4)], 0.25)
    if st == "suit":
        cv.paint([(cw * .1, -T * 1.02), (cw * .38, -T * .98), (cw * .5, -T * .7), (cw * .5, -T * .12), (cw * .2, -T * .12), (cw * .18, -T * .6)], PAPER)            # shirt
        cv.paint([(cw * .24, -T * .96), (cw * .33, -T * .93), (cw * .38, -T * .62), (cw * .3, -T * .5), (cw * .24, -T * .62)], RUST)                                   # tie
        cv.paint([(cw * .22, -T * .98), (cw * .1, -T * .88), (cw * .26, -T * .9)], INK2)
        cv.pline(spline([(cw * .08, -T * 1.0), (cw * .22, -T * .78), (cw * .12, -T * .62), (cw * .3, -T * .56), (cw * .3, -T * .1), (cw * .26, ext)], 5, False), INK, 1.8)   # lapel + front edge
        cv.dk([(cw * .08, -T * 1.0), (cw * .22, -T * .78), (cw * .12, -T * .62), (cw * .02, -T * .7)], 0.8)
        cv.pline([(cw * .38, -T * .38), (cw * .5, -T * .38)], INK, 1.3); cv.pline([(cw * .38, -T * .36), (cw * .5, -T * .36)], INK, 0.8)         # pocket flap
        cv.fill(ellipse(cw * .24, -T * .34, 2.6, 2.6, 10), INK)
        cv.pline(spline([(-cw * .38, -T * .85), (-cw * .22, -T * .5), (-cw * .3, -T * .15)], 5, False), INK2, 1.4)                                                         # back fold
        cv.pline([(-ww * .5, -T * .06), (ww * .52, -T * .06)], INK, 2.0)
    elif st == "vest":
        cv.paint([(-cw, -T * .93), (cw, -T * .93), (cw, -T * .02), (-cw, -T * .02)], (190, 160, 118))
        cv.paint([(cw * .1, -T * 1.0), (cw * .45, -T * .98), (cw * .5, -T * .7), (cw * .3, -T * .78)], PAPER)
        cv.pline([(cw * .1, -T * 1.0), (cw * .3, -T * .78), (cw * .45, -T * .98)], INK, 1.5)
        cv.pline([(cw * .3, -T * .78), (cw * .32, -T * .02)], INK, 1.5)
        for i in range(4): cv.fill(ellipse(cw * .36, -T * (.68 - .17 * i), 2.6, 2.6, 10), INK)
        cv.pline([(cw * .02, -T * .55), (cw * .3, -T * .55), (cw * .3, -T * .34), (cw * .02, -T * .34), (cw * .02, -T * .55)], INK, 1.4)                                   # breast pocket
        cv.pline([(-ww * .5, -T * .08), (ww * .52, -T * .08)], INK, 2.2)
        cv.pline(spline([(-cw * .4, -T * .8), (-cw * .26, -T * .45), (-cw * .36, -T * .12)], 5, False), INK2, 1.4)
        cv.pline([(-cw * .3, -T * .9), (-cw * .05, -T * .6)], INK2, 1.2)
    elif st == "coat":
        cv.paint([(cw * .05, -T * 1.02), (cw * .4, -T * .98), (cw * .5, -T * .78), (cw * .3, -T * .62), (cw * .14, -T * .78)], (190, 130, 100))                   # collar
        cv.pline(spline([(cw * .05, -T * 1.02), (cw * .16, -T * .78), (cw * .3, -T * .62), (cw * .5, -T * .78)], 5, False), INK, 1.6)
        cv.paint([(-cw, -T * .36), (cw, -T * .36), (cw, -T * .27), (-cw, -T * .27)], TAN); cv.pline([(-cw, -T * .36), (cw, -T * .36)], INK, 1.2); cv.pline([(-cw, -T * .27), (cw, -T * .27)], INK, 1.2)
        cv.pline([(cw * .3, -T * .62), (cw * .36, ext)], INK, 1.6)
        for i in range(3): cv.fill(ellipse(cw * .38, -T * (.52 - .12 * i), 3, 3, 10), INK)
        for x_ in (-0.3, -0.1, 0.12): cv.pline(spline([(cw * x_, -T * .25), (cw * (x_ - .05), ext * .3), (cw * (x_ - .02), ext)], 5, False), INK2, 1.2)        # skirt folds
        cv.dkl([(-cw * .3, -T * .2), (-cw * .35, ext)], 3, 0.6)
    elif st == "jacket":
        cv.pline([(cw * .3, -T * .98), (cw * .32, 8)], INK, 1.8); cv.paint([(-cw, -T * .08), (cw, -T * .08), (cw, 14), (-cw, 14)], (206, 162, 110)); cv.pline([(-cw, -T * .08), (cw, -T * .08)], INK, 1.3)
        cv.paint([(cw * .12, -T * 1.02), (cw * .42, -T * .96), (cw * .38, -T * .86), (cw * .15, -T * .9)], (206, 162, 110))
        cv.pline(spline([(-cw * .4, -T * .8), (-cw * .26, -T * .45), (-cw * .36, -T * .15)], 5, False), INK2, 1.3)
        cv.fill(ellipse(cw * .3, -T * .6, 2.6, 2.6, 10), INK)
    elif st == "uniform":
        cv.paint([(cw * .1, -T * 1.02), (cw * .42, -T * .98), (cw * .5, -T * .75), (cw * .3, -T * .66), (cw * .14, -T * .8)], PAPER)
        cv.pline([(cw * .1, -T * 1.02), (cw * .3, -T * .66), (cw * .46, -T * .95)], INK, 1.5)
        cv.paint([(cw * .26, -T * .86), (cw * .34, -T * .84), (cw * .38, -T * .58), (cw * .3, -T * .52)], RUST)
        cv.pline([(cw * .28, -T * .66), (cw * .34, ext)], INK, 1.8)                                                                                                # double-breasted front
        for i in range(3): cv.fill(ellipse(cw * .44, -T * (.56 - .15 * i), 3, 3, 10), INK); cv.fill(ellipse(cw * .16, -T * (.56 - .15 * i), 3, 3, 10), INK)
        cv.pline([(cw * .0, -T * .98), (cw * .5, -T * .72)], INK, 2.2)                                                                                              # shoulder strap of the satchel
        cv.paint([(-cw * .1, -T * .98), (cw * .5, -T * .72), (cw * .5, -T * .62), (-cw * .1, -T * .88)], LEATHER)
        cv.pline([(-ww * .5, -T * .1), (ww * .52, -T * .1)], INK, 2.8); cv.paint([(cw * .08, -T * .13), (cw * .32, -T * .13), (cw * .32, -T * .07), (cw * .08, -T * .07)], TAN)
        cv.pline([(cw * .0, -T * .52), (cw * .44, -T * .5), (cw * .44, -T * .3), (cw * .0, -T * .32), (cw * .0, -T * .52)], INK, 1.3)
    elif st == "apron":
        cv.paint([(cw * .12, -T * 1.02), (cw * .4, -T * .98), (cw * .46, -T * .82), (cw * .2, -T * .72)], PAPER)                                                    # shirt collar
        cv.paint([(-cw * .3, -T * .8), (cw * .54, -T * .8), (cw * .58, ext), (-cw * .4, ext)], (218, 178, 124))                                                              # apron
        cv.pline([(-cw * .3, -T * .8), (-cw * .4, ext)], INK, 1.4); cv.pline([(cw * .54, -T * .8), (cw * .58, ext)], INK, 1.4)
        cv.pline(spline([(cw * .0, -T * .98), (cw * .26, -T * .8), (cw * .46, -T * .98)], 5, False), INK, 1.5)                                                       # neck strap
        cv.pline([(-cw * .5, -T * .38), (cw * .55, -T * .38)], INK2, 1.4)
        cv.pline([(cw * .0, -T * .5), (cw * .42, -T * .5), (cw * .42, -T * .22), (cw * .0, -T * .22), (cw * .0, -T * .5)], INK, 1.4)                                  # pocket
        cv.pline([(-cw * .5, -T * .38), (-cw * .75, -T * .2)], INK2, 1.6)                                                                                            # apron strings
        for x_ in (-0.1, 0.2): cv.pline(spline([(cw * x_, -T * .2), (cw * (x_ - .04), ext * .4), (cw * (x_ - .03), ext)], 5, False), HATCH_L, 1.0)
        cv.dk([(cw * .3, -T * .4), (cw * .58, -T * .4), (cw * .58, ext), (cw * .3, ext)], 0.25)
    return cv.done("both" if st in ("suit", "vest", "uniform", "jacket") else "form" if st != "plain" else "both", seed, sp=2.2, ink=INK)


def b_head(s, seed):
    d = s["dims"]; hr, nk = d["hr"], d["neck"]; cx, cy = 3, -nk - hr * .95; rx, ry = hr * .82, hr
    cv = Cv(-hr * 3.2, -nk - hr * 3, hr * 3.8, 16); hat = s["hat"]; skin = s.get("skin", SKIN); plain = skin == INK; old = s.get("old", False)
    c_hat = s.get("c_hat", INK2)
    cv.fill(capsule((0, 10), (2, -nk - hr * .5), 20, 17), skin if not plain else INK)                    # neck
    cv.dk([(-14, -nk - 4), (14, -nk - 4), (14, -nk + 30), (-14, -nk + 30)], 0.39)
    face = spline([(cx - rx * .9, cy - ry * .25), (cx - rx * .8, cy + ry * .55), (cx - rx * .15, cy + ry * 1.0), (cx + rx * .5, cy + ry * .96), (cx + rx * .72, cy + ry * .66), (cx + rx * .6, cy + ry * .4),
                   (cx + rx * .8, cy + ry * .3), (cx + rx + 5, cy + ry * .12), (cx + rx * .86, cy - ry * .08), (cx + rx * .86, cy - ry * .45), (cx + rx * .72, cy - ry * .9), (cx, cy - ry * 1.04), (cx - rx * .72, cy - ry * .85)], 6)
    cv.fill(wob(face, .35, seed), skin)
    cv.dk([(cx - rx, cy - ry), (cx - rx * .2, cy - ry), (cx - rx * .3, cy + ry * 1.1), (cx - rx, cy + ry * 1.1)], 0.28)      # back of the head in shade
    cv.dk([(cx - rx * .2, cy + ry * .5), (cx + rx * .6, cy + ry * .55), (cx + rx * .4, cy + ry * 1.05), (cx - rx * .3, cy + ry * 1.05)], 0.30)   # under the jaw
    if not plain:
        cv.pline(spline([(cx - rx * .05, cy - ry * .02), (cx - rx * .35, cy + ry * .15), (cx - rx * .05, cy + ry * .4)], 5, False), INK, 1.3)   # ear
        cv.fill(ellipse(cx + rx * .5, cy - ry * .06, 4.6, 3.3, 10), INK)                                                                       # eye
        cv.line([(cx + rx * .32, cy - ry * .22), (cx + rx * .72, cy - ry * .24)], INK, 2.8)                                                    # brow
        cv.line([(cx + rx * .6, cy + ry * .48), (cx + rx * .82, cy + ry * .44)], INK, 1.8)                                                     # mouth
        cv.line([(cx + rx * .82, cy - ry * .06), (cx + rx + 6, cy + ry * .1)], INK, 1.6)
        if old: cv.line([(cx + rx * .3, cy + ry * .16), (cx + rx * .58, cy + ry * .3)], INK2, 1.0); cv.line([(cx + rx * .3, cy - ry * .1), (cx + rx * .2, cy + ry * .12)], INK2, 0.9)
    if hat == "fedora":
        crown = spline([(cx - rx * .92, cy - ry * .5), (cx - rx * .86, cy - ry * 1.28), (cx - rx * .4, cy - ry * 1.68), (cx + rx * .1, cy - ry * 1.62), (cx + rx * .6, cy - ry * 1.42), (cx + rx * .94, cy - ry * .5)], 6)
        cv.fill(wob(crown, .5, seed + 1), c_hat)
        cv.dk([(cx - rx, cy - ry * 1.7), (cx - rx * .3, cy - ry * 1.7), (cx - rx * .4, cy - ry * .5), (cx - rx, cy - ry * .5)], 0.28)
        cv.line(spline([(cx - rx * .5, cy - ry * 1.6), (cx, cy - ry * 1.25), (cx + rx * .5, cy - ry * 1.36)], 5, False), INK2, 1.3)                   # dent in the crown
        cv.paint([(cx - rx, cy - ry * .58), (cx + rx, cy - ry * .58), (cx + rx, cy - ry * .84), (cx - rx, cy - ry * .84)], RUST if not plain else INK2)
        cv.fill(wob(ellipse(cx + rx * .2, cy - ry * .5, rx * 2.2, 12.5), .5, seed + 2), c_hat); cv.line(ellipse(cx + rx * .2, cy - ry * .5, rx * 2.2, 12.5), INK, 1.6)
        cv.dk([(cx - rx * 2, cy - ry * .45), (cx + rx * 2, cy - ry * .45), (cx + rx * 2, cy - ry * .3), (cx - rx * 2, cy - ry * .3)], 0.22)
    elif hat == "cap":                                                                                           # flat cap with a short peak
        cv.fill(wob(spline([(cx - rx * 1.05, cy - ry * .3), (cx - rx * .95, cy - ry * 1.08), (cx - rx * .2, cy - ry * 1.4), (cx + rx * .9, cy - ry * 1.12), (cx + rx * 1.12, cy - ry * .4)], 6), .5, seed + 1), c_hat)
        cv.fill([(cx + rx * .6, cy - ry * .6), (cx + rx * 2.35, cy - ry * .4), (cx + rx * 2.3, cy - ry * .2), (cx + rx * .55, cy - ry * .32)], tuple(int(c * .85) for c in c_hat))
        cv.dk([(cx - rx, cy - ry * 1.5), (cx - rx * .1, cy - ry * 1.5), (cx - rx * .2, cy - ry * .3), (cx - rx, cy - ry * .3)], 0.30)
        cv.line(spline([(cx - rx * .6, cy - ry * 1.2), (cx, cy - ry * .8), (cx + rx * .7, cy - ry * .6)], 5, False), INK2, 1.2)
    elif hat == "peak":                                                                                          # courier peak cap with badge
        cv.fill(wob(spline([(cx - rx * 1.05, cy - ry * .45), (cx - rx * 1.0, cy - ry * 1.15), (cx - rx * .3, cy - ry * 1.48), (cx + rx * .7, cy - ry * 1.38), (cx + rx * 1.12, cy - ry * .5)], 6), .5, seed + 1), c_hat)
        cv.paint([(cx - rx * 1.2, cy - ry * .52), (cx + rx * 1.2, cy - ry * .52), (cx + rx * 1.2, cy - ry * .72), (cx - rx * 1.2, cy - ry * .72)], INK2)
        cv.fill([(cx + rx * .5, cy - ry * .56), (cx + rx * 2.3, cy - ry * .42), (cx + rx * 2.2, cy - ry * .24), (cx + rx * .5, cy - ry * .4)], INK2)
        cv.fill(ellipse(cx + rx * .62, cy - ry * .95, 5, 4.2, 12), TAN)
        cv.dk([(cx - rx, cy - ry * 1.5), (cx - rx * .1, cy - ry * 1.5), (cx - rx * .2, cy - ry * .4), (cx - rx, cy - ry * .4)], 0.30)
    elif hat == "scarf":
        sc_ = spline([(cx + rx * .6, cy - ry * .45), (cx + rx * .2, cy - ry * 1.2), (cx - rx * .8, cy - ry * 1.08), (cx - rx * 1.3, cy + ry * .1), (cx - rx * 1.0, cy + ry * .9),
                      (cx - rx * .2, cy + ry * .7), (cx + rx * .0, cy + ry * .2), (cx + rx * .3, cy - ry * .15)], 6)
        cv.fill(wob(sc_, .5, seed + 1), c_hat)
        cv.fill(spline([(cx - rx * .95, cy + ry * .6), (cx - rx * 1.5, cy + ry * .9), (cx - rx * 1.2, cy + ry * 1.25), (cx - rx * .6, cy + ry * 1.0)], 5), c_hat)                                  # knot
        cv.line([(cx + rx * .1, cy - ry * 1.12), (cx - rx * .7, cy - ry * .2), (cx - rx * .75, cy + ry * .7)], INK2, 1.4)
        cv.dk([(cx - rx * 1.4, cy - ry * 1.2), (cx - rx * .6, cy - ry * 1.2), (cx - rx * .8, cy + ry * 1.3), (cx - rx * 1.5, cy + ry * 1.3)], 0.33)
        cv.fill(spline([(cx + rx * .3, cy - ry * .5), (cx + rx * .7, cy - ry * .42), (cx + rx * .6, cy - ry * .3), (cx + rx * .25, cy - ry * .32)], 4), INK)          # fringe
    elif hat == "beanie":
        cv.fill(wob(spline([(cx - rx * 1.02, cy - ry * .25), (cx - rx * .88, cy - ry * 1.18), (cx, cy - ry * 1.5), (cx + rx * .92, cy - ry * 1.14), (cx + rx * 1.04, cy - ry * .28)], 6), .5, seed + 1), c_hat)
        cv.paint([(cx - rx * 1.2, cy - ry * .22), (cx + rx * 1.2, cy - ry * .22), (cx + rx * 1.2, cy - ry * .56), (cx - rx * 1.2, cy - ry * .56)], TAN)
        for k_ in range(-3, 4): cv.line([(cx + rx * .3 * k_, cy - ry * .22), (cx + rx * .3 * k_, cy - ry * .56)], INK2, 0.8)
        cv.fill(ellipse(cx, cy - ry * 1.52, 9, 9, 14), TAN)
        cv.dk([(cx - rx, cy - ry * 1.6), (cx - rx * .1, cy - ry * 1.6), (cx - rx * .2, cy - ry * .3), (cx - rx, cy - ry * .3)], 0.30)
    elif hat == "bald":
        cv.fill(spline([(cx - rx * .96, cy - ry * .45), (cx - rx * .92, cy - ry * .05), (cx - rx * .6, cy + ry * .15), (cx - rx * .3, cy - ry * .3), (cx - rx * .4, cy - ry * .75)], 6), c_hat)  # white fringe over the ear
        cv.fill(spline([(cx - rx * .5, cy - ry * .85), (cx - rx * .1, cy - ry * .98), (cx + rx * .4, cy - ry * .9), (cx + rx * .3, cy - ry * .8), (cx - rx * .3, cy - ry * .78)], 4), c_hat)
        cv.fill(spline([(cx + rx * .5, cy + ry * .34), (cx + rx * .92, cy + ry * .3), (cx + rx * .9, cy + ry * .42), (cx + rx * .5, cy + ry * .46)], 4), c_hat)                           # moustache
        cv.line(ellipse(cx + rx * .56, cy - ry * .1, 9, 7.5, 16), INK, 1.1); cv.line([(cx + rx * .56 - 9, cy - ry * .1), (cx - rx * .2, cy - ry * .15)], INK, 1.0)                           # spectacles
    else:
        cv.fill(spline([(cx - rx * .95, cy + ry * .2), (cx - rx, cy - ry * .6), (cx, cy - ry * 1.12), (cx + rx * .7, cy - ry * .7), (cx + rx * .1, cy - ry * .3)], 6), INK)
    return cv.done("form", seed, sp=2.1)


def _sleeve(s, which):
    return s["c_body"]


def b_limb(s, which, seed):
    d = s["dims"]; aw, lw = s["aw"], s["lw"]; st = s["body"]
    if which == "uarm": L, w0, w1, col = d["uarm"], aw[0], aw[1], s["c_body"]; prof = [(0, w0 * 1.04), (0.3, w0), (0.7, (w0 + w1) / 2), (1, w1)]
    elif which == "farm": L, w0, w1, col = d["farm"], aw[1], aw[2], s["c_body"]; prof = [(0, w0), (0.25, w0 * 1.06), (0.75, (w0 + w1) / 2), (1, w1 * 1.02)]
    elif which == "thigh": L, w0, w1, col = d["thigh"], lw[0], lw[1], s["c_legs"]; prof = [(0, w0), (0.3, w0 * 1.02), (0.75, (w0 + w1) / 2), (1, w1)]
    else: L, w0, w1, col = d["shin"], lw[1], lw[2], s["c_legs"]; prof = [(0, w0), (0.22, w0 * 1.06), (0.7, (w0 + w1) / 2 * 1.0), (1, w1 * 1.08)]
    cv = Cv(-w0 - 10, -w0 - 10, w0 + 10, L + w1 + 10)
    cv.fill(wob(tube(L, prof), .5, seed), col)
    cv.dk([(w0 * .05, -w0), (w0, -w0), (w0, L + w1), (w0 * .05, L + w1)], 0.3); cv.dk([(-w0, -w0), (-w0 * .1, -w0), (-w0 * .1, L + w1), (-w0, L + w1)], 0.12)
    if "arm" in which:
        sg = INK2
        if which == "farm":
            if st in ("suit", "uniform", "apron"):
                cv.paint([(-30, L - 11), (30, L - 11), (30, L + 30), (-30, L + 30)], PAPER)
                cv.pline([(-w1 / 2 - 2, L - 11), (w1 / 2 + 2, L - 11)], INK, 1.2); cv.fill(ellipse(0, L - 15, 1.8, 1.8, 8), INK)
            if st == "apron": cv.paint([(-30, L * .35), (30, L * .35), (30, L - 8), (-30, L - 8)], SKIN); cv.pline([(-w1 / 2 - 4, L * .35), (w1 / 2 + 4, L * .35)], INK, 1.2)
            if st == "vest": cv.paint([(-30, L * .45), (30, L * .45), (30, L + 20), (-30, L + 20)], SKIN); cv.pline([(-w1 / 2 - 4, L * .45), (w1 / 2 + 4, L * .45)], INK, 1.3)
            if st == "uniform": cv.pline([(-w1 / 2 - 2, L * .6), (w1 / 2 + 2, L * .6)], INK, 1.2)
        cv.pline(spline([(-w0 * .3, L * .5), (-w0 * .05, L * .58), (w0 * .35, L * .52)], 4, False), sg, 1.2)               # crook of the elbow / fold
        if which == "uarm" and st == "suit": cv.pline([(-w0 * .45, L * .2), (w0 * .1, L * .35)], sg, 1.0)
    else:
        cv.pline([(-w0 * .05, 4), (-w0 * .08, L - 6)], INK2 if st != "plain" else HATCH_L, 1.0)                            # trouser crease
        if which == "shin":
            cv.paint([(-40, L - 12), (40, L - 12), (40, L + 30), (-40, L + 30)], tuple(int(c * .8) for c in s["c_legs"]))
            cv.pline([(-w1 / 2 - 4, L - 12), (w1 / 2 + 4, L - 12)], INK, 1.5)                                                # trouser cuff turn-up
            if st in ("coat", "jacket"): cv.paint([(-40, L * .5), (40, L * .5), (40, L - 14), (-40, L - 14)], (96, 72, 58)); cv.pline([(-40, L * .5), (40, L * .5)], INK, 1.2)   # stockings / socks
        else: cv.pline(spline([(-w0 * .3, L * .86), (w0 * .1, L * .92), (w0 * .4, L * .88)], 4, False), INK2, 1.1)         # knee fold
    return cv.done("form" if "arm" in which else "both", seed, sp=2.2)


def b_hand(s, seed):
    k = s["dims"]["hand"] / 34; skin = s.get("skin", SKIN); cv = Cv(-24 * k, -8, 26 * k, 44 * k)
    cv.fill(wob(spline([(-9.5 * k, -2), (-10 * k, 12 * k), (-8 * k, 20 * k), (8 * k, 20 * k), (10.5 * k, 12 * k), (9 * k, -2)], 5), .3, seed), skin)               # palm
    for i, (fx, ln, ang) in enumerate([(-7, 17, -9), (-2.5, 20, -3), (2.5, 19, 4), (7, 15, 11)]):                                                              # four fingers, slightly splayed
        a = math.radians(ang); x0, y0 = fx * k, 17 * k; x1, y1 = x0 + ln * k * math.sin(a), y0 + ln * k * math.cos(a)
        cv.fill(capsule((x0, y0), (x1, y1), 5.4 * k, 4.6 * k, 6), skin)
    cv.fill(capsule((9 * k, 5 * k), (14 * k, 19 * k), 6.4 * k, 5.2 * k, 6), skin)                                                                            # thumb
    cv.dk([(-12 * k, -4), (-3 * k, -4), (-3 * k, 40 * k), (-12 * k, 40 * k)], 0.35)
    return cv.done("form" if skin != INK else None, seed, sp=2.0, outline=0.7)


def b_foot(s, seed):
    d = s["dims"]; fl, fh, hl = d["foot_len"], d["foot_h"], s.get("heel", 14); cv = Cv(-hl - 14, -12, fl + 10, fh + 10); col = s["c_shoe"]
    pts = [(-hl + 1, -3), (-hl - 2, fh * .55), (-hl + 1, fh), (fl * .3, fh + 1), (fl - hl - 5, fh * .95), (fl - hl + 3, fh * .6), (fl * .6, fh * .2), (fl * .38, -1), (6, -6)]
    cv.fill(wob(spline(pts, 5), .35, seed), col)
    cv.paint([(-hl - 4, fh - 5.5), (fl, fh - 5.5), (fl, fh + 4), (-hl - 4, fh + 4)], tuple(int(c * .55) for c in col) if col != INK else INK2)           # sole
    cv.paint([(-hl - 4, fh - 5.5), (-hl + 7, fh - 5.5), (-hl + 7, fh + 4), (-hl - 4, fh + 4)], tuple(int(c * .45) for c in col) if col != INK else INK2)   # heel block
    cv.line([(-hl - 4, fh - 5.5), (fl - hl - 2, fh - 5.5)], INK, 1.2)
    cv.pline(spline([(fl * .3, -2), (fl * .42, fh * .45), (fl * .38, fh - 5)], 4, False), INK2, 1.1)                                                        # toe cap seam
    if s["body"] != "plain":
        cv.paint([(-hl - 4, -8), (fl * .3, -8), (fl * .3, 0), (-hl - 4, 0)], PAPER if s["body"] in ("jacket",) else tuple(int(c * .8) for c in s["c_legs"]))
    cv.dk([(-hl, fh * .5), (fl, fh * .5), (fl, fh + 4), (-hl, fh + 4)], 0.3)
    return cv.done("both", seed, sp=2.2, outline=0.8)


def b_flap(s, seed, kind):
    if kind == "coat":
        cv = Cv(-64, -8, 64, 130); cv.fill(wob(spline([(-28, 0), (26, 0), (38, 60), (44, 112), (-6, 120), (-44, 112), (-36, 55)], 6), .7, seed), s["c_body"])
        cv.paint([(-64, 100), (64, 100), (64, 130), (-64, 130)], (190, 130, 100)); cv.pline([(-64, 100), (64, 100)], INK, 1.3)
        for x_ in (-18, 4, 24): cv.pline(spline([(x_, 14), (x_ * 1.4, 60), (x_ * 1.6, 112)], 5, False), INK2, 1.2)
        cv.dk([(-64, 0), (-10, 0), (-20, 130), (-64, 130)], 0.5)
        return cv.done("form", seed)
    col = s.get("c_hat", RUST); L = 92 if s["hat"] == "scarf" else 62
    cv = Cv(-26, -10, 26, L + 16); cv.fill(wob(spline([(-8, 0), (9, 0), (12, L * .6), (7, L), (-2, L - 9), (-11, L)], 6), .5, seed), col)
    for i in range(3): cv.pline([(-6, L * .55 + i * 4), (8, L * .55 + i * 4)], INK2, 0.9)
    cv.pline([(0, 2), (1, L * .5)], INK2, 1.0)
    return cv.done("form", seed)


def _grow(im, f):
    """enlarge a pivot-centred part about its centre (props are exaggerated so they read from far away)"""
    return im.resize((int(round(im.width * f)) // 2 * 2, int(round(im.height * f)) // 2 * 2), Image.LANCZOS)


def b_prop(name, s, seed):
    r = _b_prop(name, s, seed)
    return _grow(r, {"briefcase": 1.3, "box": 1.1, "parcel": 1.05}.get(name, 1.0))


def _b_prop(name, s, seed):
    if name == "briefcase":
        cv = Cv(-62, -22, 62, 92); cv.line(spline([(-18, 18), (-15, 3), (15, 3), (18, 18)], 4, False), LEATHER, 5.5); cv.line(spline([(-18, 18), (-15, 3), (15, 3), (18, 18)], 4, False), INK, 1.0)
        cv.fill(wob(spline([(-42, 14), (42, 14), (44, 74), (-44, 74)], 4), .5, seed), LEATHER)
        cv.paint([(-42, 14), (42, 14), (42, 24), (-42, 24)], (136, 100, 72)); cv.line([(-42, 24), (42, 24)], INK, 1.2)
        cv.fill(ellipse(0, 30, 4.5, 3.4, 10), TAN); cv.line([(-36, 18), (-36, 70)], HATCH_L, 0.9); cv.line([(36, 18), (36, 70)], HATCH_L, 0.9); cv.line([(-36, 70), (36, 70)], HATCH_L, 0.9)
        for sx in (-1, 1): cv.fill([(sx * 44, 14), (sx * 34, 14), (sx * 34, 24), (sx * 44, 24)], TAN); cv.fill([(sx * 44, 74), (sx * 34, 74), (sx * 34, 64), (sx * 44, 64)], TAN)
        cv.dk([(10, 30), (44, 30), (44, 76), (10, 76)], 0.35)
        return cv.done("both", seed, sp=2.6, outline=0.7)
    if name in ("box", "parcel"):
        w, h = {"box": (118, 86), "parcel": (96, 62)}[name]; col = KRAFT if name == "box" else (200, 168, 124)
        cv = Cv(-w / 2 - 10, -h / 2 - 10, w / 2 + 10, h / 2 + 10); cv.fill(wob(spline([(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)], 6), .6, seed), col)
        if name == "box":
            cv.paint([(-9, -h / 2), (9, -h / 2), (9, h / 2), (-9, h / 2)], (214, 188, 140)); cv.line([(-9, -h / 2), (-9, h / 2)], INK2, 0.9); cv.line([(9, -h / 2), (9, h / 2)], INK2, 0.9)
            cv.paint([(-w / 2 + 12, h * .02), (-w / 2 + 44, h * .02), (-w / 2 + 44, h * .3), (-w / 2 + 12, h * .3)], PAPER)
            for k_ in range(3): cv.line([(-w / 2 + 16, h * (.08 + .07 * k_)), (-w / 2 + 40, h * (.08 + .07 * k_))], INK, 0.9)
            cv.line([(-w / 2, -h * .32), (w / 2, -h * .32)], INK2, 1.1)
            cv.paint([(w / 2 - 36, h * .12), (w / 2 - 12, h * .12), (w / 2 - 12, h * .32), (w / 2 - 36, h * .32)], RUST)
        else:
            cv.line([(-w * .12, -h / 2), (-w * .12, h / 2)], INK, 2.2); cv.line([(-w / 2, h * .1), (w / 2, h * .1)], INK, 2.2)
            cv.fill(ellipse(-w * .12, h * .1, 7.5, 5.5, 12), RUST)
            cv.pline([(-w * .3, -h * .3), (-w * .1, -h * .15)], INK2, 0.9); cv.pline([(w * .15, h * .3), (w * .38, h * .4)], INK2, 0.9)
        cv.dk([(w * .1, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (w * .1, h / 2)], 0.35); cv.dk([(-w / 2, h * .3), (w / 2, h * .3), (w / 2, h / 2), (-w / 2, h / 2)], 0.35)
        return cv.done("both", seed, sp=2.8, outline=0.8)
    if name == "phone":
        cv = Cv(-16, -6, 16, 52); cv.fill(wob(spline([(-11, 0), (11, 0), (11, 44), (-11, 44)], 4), .3, seed), INK2); cv.paint([(-8, 5), (8, 5), (8, 38), (-8, 38)], PAPER)
        for k_ in range(4): cv.line([(-5, 10 + k_ * 6), (5, 10 + k_ * 6)], HATCH_L, 1.0)
        return cv.done(None, seed, outline=0.6)
    if name == "clipboard":
        cv = Cv(-30, -36, 30, 36); cv.fill(wob(spline([(-23, -32), (23, -32), (23, 32), (-23, 32)], 4), .4, seed), LEATHER)
        cv.paint([(-19, -26), (19, -26), (19, 28), (-19, 28)], PAPER); cv.fill([(-9, -35), (9, -35), (9, -26), (-9, -26)], TAN); cv.line([(-9, -35), (9, -35), (9, -26), (-9, -26), (-9, -35)], INK, 1.0)
        for k_ in range(8): cv.line([(-14, -18 + k_ * 5.5), (14 - (k_ % 3) * 4, -18 + k_ * 5.5)], INK2, 1.0)
        return cv.done("both", seed, sp=2.4, outline=0.7)
    if name == "newspaper":
        cv = Cv(-40, -34, 40, 34); cv.fill(wob(spline([(-34, -28), (34, -30), (36, 28), (-34, 30)], 4), .4, seed), PAPER)
        cv.line([(-34, -28), (34, -30), (36, 28), (-34, 30), (-34, -28)], INK, 1.0); cv.paint([(-30, -23), (30, -24), (30, -12), (-30, -11)], INK2)
        for k_ in range(6): cv.line([(-30, -4 + k_ * 5.5), (-2, -4 + k_ * 5.5)], INK2, 1.0); cv.line([(4, -4 + k_ * 5.5), (30, -4 + k_ * 5.5)], INK2, 1.0)
        cv.line([(1, -10), (1, 28)], HATCH_L, 0.8)
        cv.dk([(-40, 12), (40, 12), (40, 34), (-40, 34)], 0.25)
        return cv.done("form", seed, sp=2.4, outline=0.7)
    d = s["dims"]; h = d["foot_h"] + 0.62 * (d["thigh"] + d["shin"]) - 12
    cv = Cv(-72, -8, 72, h + 8); cv.fill(wob(spline([(-62, 0), (62, 0), (62, 14), (-62, 14)], 4), .5, seed), (140, 106, 76))
    for x in (-50, 48): cv.fill([(x - 5, 12), (x + 5, 12), (x + 5, h), (x - 5, h)], (112, 82, 58))
    return cv.done("form", seed, outline=0.8)


PROP_NAMES = ("briefcase", "box", "parcel", "phone", "stool", "clipboard", "newspaper")
_PROP_MEMO: Dict[tuple, Image.Image] = {}


def build_parts(spec, name) -> Dict[str, Image.Image]:
    seed = int(hashlib.md5(name.encode()).hexdigest()[:6], 16)
    P = {"torso": b_torso(spec, seed), "head": b_head(spec, seed + 1), "hand": b_hand(spec, seed + 2), "foot": b_foot(spec, seed + 3)}
    for i, w in enumerate(("uarm", "farm", "thigh", "shin")): P[w] = b_limb(spec, w, seed + 10 + i)
    for sw in spec.get("sway", []): P[sw["part"]] = b_flap(spec, seed + 20, "coat" if sw["part"] == "coat_flap" else "scarf")
    for pn in PROP_NAMES:
        mk = (pn, tuple(sorted(spec["dims"].items())) if pn == "stool" else None)
        if mk not in _PROP_MEMO: _PROP_MEMO[mk] = b_prop(pn, spec, 99 + len(pn))
        P["prop_" + pn] = _PROP_MEMO[mk]
    return P


_RIGS: Dict[str, Rig] = {}


def list_names() -> List[str]: return list(SPECS)


def get_rig(name: str) -> Rig:
    if name in _RIGS: return _RIGS[name]
    if name not in SPECS: raise KeyError(f"unknown puppet character {name!r}; have {sorted(SPECS)}")
    spec = SPECS[name]
    key = f"{name}_v{VERSION}_" + hashlib.md5((repr(sorted(spec.items(), key=lambda kv: kv[0])) + open(__file__).read() + f"HR{HR}").encode()).hexdigest()[:8]
    d = CACHE_DIR / key; parts: Dict[str, Image.Image] = {}
    want = ["torso", "head", "hand", "foot", "uarm", "farm", "thigh", "shin"] + [sw["part"] for sw in spec.get("sway", [])] + ["prop_" + p for p in PROP_NAMES]
    if d.is_dir() and all((d / f"{w}.png").is_file() for w in want):
        parts = {w: Image.open(d / f"{w}.png").convert("RGBA") for w in want}
    else:
        parts = build_parts(spec, name)
        try:
            d.mkdir(parents=True, exist_ok=True)
            for w, im in parts.items(): im.save(d / f"{w}.png")
        except OSError: pass
    _RIGS[name] = Rig(name, spec, parts)
    return _RIGS[name]
