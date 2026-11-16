"""Living places for the cartoon2d renderer (Stage A): depth parallax, drifting clouds, swaying trees, water sparkles,
birds and butterflies, and light that makes the characters belong to the place.

prepare(bg, floor_y, spots) -> place info (once per place per worker; depth is cached on disk)
view(P, rect, ref, t)       -> the background as the camera sees it at t (RGBA, OUT size). rect = camera now, ref = the
                               same shot's camera at its first frame. Far things move less than the characters' plane,
                               near things move more, so every push-in / drift has real depth. rect == ref gives a plain crop.
life(P, frame, rect, t)     -> birds, butterflies, water sparkles drawn on the background (before the characters)
light(P, layer, z)          -> the characters' layer tinted by the place light, with a soft rim light from the sun side
"""
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT_W, OUT_H = 1920, 1080
PADF = 0.08                       # world padded by 8 % each side (edge pixels) so near layers never sample outside
GX, GY = 25, 15                   # mesh vertices across / down (80 x 77 px cells at 1080p; depth is smooth)
P_FAR, P_NEAR = 0.3, 1.45         # parallax factor of the farthest sky / the nearest ground (characters' plane = 1)
CLOUD_SPEED = 6.0                 # world px per second
LEVELS = (1.0, 0.75)              # source scales: wide shots sample the 0.75 copy (no aliasing from a big downscale)
LINE = (70, 45, 30)


# ------------------------------------------------------------------ preparing a place
def _depth(bg):
    try:
        from health_cinema.puppet import depth as dm
        if dm.available():
            return dm.depth_map(bg)
    except Exception as e:                        # no model: a simple floor-is-near guess still gives parallax
        print("scenery: depth model unavailable:", e, flush=True)
    h = bg.height
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    return np.repeat(np.clip((y - 0.35) / 0.65, 0, 1), bg.width, axis=1)


def _blur(a, r):
    im = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(r))
    return np.asarray(im, np.float32) / 255


def _clean(mask, r=2):
    im = Image.fromarray((mask * 255).astype(np.uint8), "L")
    im = im.filter(ImageFilter.MinFilter(2 * r + 1)).filter(ImageFilter.MaxFilter(2 * r + 1))
    return np.asarray(im) > 127


def _components(mask):
    """Label connected parts of a small bool mask (flood fill, few parts)."""
    lab = Image.fromarray(mask.astype(np.uint8) * 255, "L")
    out, n = [], 0
    arr = np.asarray(lab).copy()
    while n < 250:
        ys, xs = np.nonzero(arr == 255)
        if not len(ys):
            break
        n += 1
        im = Image.fromarray(arr, "L").copy()      # fromarray shares the read-only buffer: fill a copy
        ImageDraw.floodfill(im, (int(xs[0]), int(ys[0])), n)
        arr = np.asarray(im).copy()
        out.append(arr == n)
    return out


def prepare(bg, floor_y, spots, outdoor=None):
    W, H = bg.size
    a = np.asarray(bg, np.float32) / 255
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1e-3)
    d = _blur(_depth(bg), 6)
    fy = int(floor_y * H)
    dc = float(np.median(d[max(0, fy - 12):fy + 1, int(min(spots.values())):int(max(spots.values())) + 1]))
    yy = np.arange(H)[:, None] / H

    # sky: each row's own sky colour (strong blue pixels); the sky zone is that colour plus anything it fully surrounds
    blue = (b > 0.55) & (b > r + 0.08) & (b >= g - 0.03)
    strong = (b > r + 0.15) & (b > 0.6)
    rows = np.zeros((H, 3), np.float32)
    have = np.array([strong[y].sum() > 30 for y in range(H)])
    for y in np.nonzero(have)[0]:
        rows[y] = a[y][strong[y]].mean(0)
    if have.sum() > H * 0.08:
        idx = np.arange(H)
        for c in range(3):
            rows[:, c] = np.interp(idx, idx[have], rows[have, c])
    skyc = (np.abs(a - rows[:, None, :]).max(-1) < 0.07) & have[:, None]
    sky = _clean(skyc & (d < max(0.22, dc * 0.3)) & (yy < floor_y - 0.12), 2)
    has_sky = sky.mean() > 0.06
    if outdoor is None:                                 # sky across the top edge = outdoors (a sky mural is not)
        outdoor = has_sky and sky[: max(2, H // 25)].mean() > 0.45

    # clouds: blobs inside the sky (sky colour all round them, outline included) drift; ones touching trees / sides stay
    cloud = np.zeros((H, W), bool)
    sun_zone = np.zeros((H, W), bool)
    if outdoor:
        sm = 4
        ss = sky[::sm, ::sm]
        rest = _clean(~ss & (np.arange(ss.shape[0])[:, None] < ss.shape[0] * (floor_y - 0.12)), 1)   # no 1-row slivers
        a4 = a[::sm, ::sm]
        for comp in _components(rest):
            if comp.sum() < 30:
                continue
            ys, xs = np.nonzero(comp)
            if xs.min() == 0 or xs.max() >= comp.shape[1] - 1:
                continue
            ring = np.asarray(Image.fromarray(comp.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(5))) > 0
            ring &= ~comp
            if ys.min() > 0 and ss[ring].mean() < 0.9:
                continue
            if ys.min() == 0 and ss[ring & (np.arange(comp.shape[0])[:, None] > 0)].mean() < 0.9:
                continue
            cp = a4[comp]
            yellow = ((cp[:, 0] > 0.85) & (cp[:, 2] < 0.6)).mean()
            if yellow > 0.03:                             # the sun stays, clouds may drift in front of it
                sun_zone |= np.asarray(Image.fromarray(comp.astype(np.uint8) * 255).resize((W, H), Image.NEAREST)) > 0
                continue
            if cp.mean(0)[2] < 0.6 or ys.max() - ys.min() < 4:   # slivers stay
                continue
            cloud |= np.asarray(Image.fromarray(comp.astype(np.uint8) * 255).resize((W, H), Image.NEAREST)) > 0
        if cloud.any():                                   # nearest upscale leaves a stair edge: grow a little into non-sky
            grown = np.asarray(Image.fromarray(cloud.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(9))) > 0
            cloud = grown                                 # a ring of plain sky too: its soft shading leaves no ghost
            sky = sky | cloud
    calpha = _blur(cloud.astype(np.float32), 1.2)
    # where a drifting cloud may show: sky, the sun, and painted clouds that stay (light, far, above the hills);
    # a small close bridges the outlines of those still clouds so a moving one is not cut by a thin line
    lightc = (mx > 0.78) & (sat < 0.3) & (d < max(0.22, dc * 0.3)) & (yy < floor_y - 0.2)
    show = Image.fromarray(((sky | sun_zone | lightc) * 255).astype(np.uint8), "L")
    show = np.asarray(show.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))) > 127
    show &= ~(green := (g > r + 0.04) & (g > b + 0.02)) | sky

    # the sky without the moving clouds: each row's own sky colour fills where a cloud was
    clean = a.copy()
    if cloud.any():
        k = calpha[..., None]
        clean = a * (1 - k) + rows[:, None, :] * k

    # water: blue below the sky line, nearer than the sky; foliage: green, above the floor, not ground right by the feet
    water = _clean(blue & ~sky & (yy > 0.35) & (d > max(0.15, dc * 0.25)), 2) if outdoor else np.zeros((H, W), bool)
    green = (g > r + 0.04) & (g > b + 0.02) & ~sky
    lum = a.mean(-1)                                    # leaves have shading and outlines; flat hills and lawns do not
    gx = np.abs(np.diff(lum, axis=1, prepend=lum[:, :1])) + np.abs(np.diff(lum, axis=0, prepend=lum[:1]))
    busy = _blur((gx > 0.06).astype(np.float32), 30) > 0.035
    tree = _clean(green & busy, 3)
    fol = _blur(tree.astype(np.float32), 16) * np.clip((floor_y - 0.3 - yy) / 0.15, 0, 1)   # canopies only: fences stay

    # light: the place's own colour, and the sun's side (bright yellow blob in the sky)
    mean = a.reshape(-1, 3).mean(0)
    amb = tuple(int(255 * (0.55 + 0.45 * v / mean.max())) for v in mean)
    sun = (r > 0.9) & (g > 0.78) & (b < 0.55) & (yy < 0.45)
    if sun.sum() > 400:
        sy, sx = np.nonzero(sun)
        ldir = np.array([sx.mean() - W / 2, sy.mean() - H * 0.6])
    else:
        ldir = np.array([-0.6, -0.8])
    ldir = ldir / max(np.linalg.norm(ldir), 1e-6)
    warm = np.clip((mean[0] - mean[2]) * 2, -0.3, 0.6)
    rim = (255, int(238 + 10 * warm), int(200 - 40 * warm))

    pw, ph = int(W * PADF), int(H * PADF)
    pad = lambda x, mode="edge": np.pad(x, ((ph, ph), (pw, pw)) + (((0, 0),) if x.ndim == 3 else ()), mode=mode)
    P = {"W": W, "H": H, "pw": pw, "ph": ph, "dc": max(dc, 0.05), "has_sky": outdoor, "amb": amb, "ldir": ldir, "rim": rim,
         "depth_s": np.asarray(Image.fromarray(d).resize((W // 8, H // 8), Image.BILINEAR)),
         "fol_s": np.asarray(Image.fromarray(fol.astype(np.float32)).resize((W // 8, H // 8), Image.BILINEAR)),
         "water_s": np.asarray(Image.fromarray(_blur(water.astype(np.float32), 8)).resize((W // 8, H // 8), Image.BILINEAR)),
         "levels": {}}
    base = Image.fromarray((pad(clean) * 255).astype(np.uint8), "RGB")
    skym = Image.fromarray((pad(_blur(show.astype(np.float32), 1.0) if outdoor else np.zeros((H, W), np.float32), "constant") * 255).astype(np.uint8), "L")
    cl = Image.fromarray((pad(a) * 255).astype(np.uint8), "RGB").convert("RGBA")
    cl.putalpha(Image.fromarray((pad(calpha, "constant") * 255).astype(np.uint8), "L"))
    rows = np.nonzero(cloud.any(1))[0]
    ctop, cbot = (int(rows.min()) + ph - 8, int(rows.max()) + ph + 9) if len(rows) else (0, 0)
    for lv in LEVELS:
        sz = (round(base.width * lv), round(base.height * lv))
        L = {"base": base if lv == 1 else base.resize(sz, Image.LANCZOS)}
        if cbot > ctop:
            t0, t1 = int(ctop * lv), int(cbot * lv)
            L["band"] = (t0, t1)
            L["cloud"] = (cl if lv == 1 else cl.resize(sz, Image.LANCZOS)).crop((0, t0, sz[0], t1))
            L["sky"] = (skym if lv == 1 else skym.resize(sz, Image.LANCZOS)).crop((0, t0, sz[0], t1))
        P["levels"][lv] = L
    # water sparkle spots and the place's random life, fixed per place
    rnd = random.Random(W * 31 + int(mean.sum() * 1000))
    wy, wx = np.nonzero(water[::6, ::6])
    P["glints"] = [(int(wx[i]) * 6, int(wy[i]) * 6, rnd.uniform(0, 6.28), rnd.uniform(0.6, 1.4))
                   for i in (rnd.sample(range(len(wy)), min(28, len(wy))) if len(wy) else [])]
    P["sky_rows"] = (int(np.nonzero(sky.any(1))[0].min()), int(np.nonzero(sky.any(1))[0].max())) if outdoor and sky.any() else None
    P["seed"] = rnd.random()
    fy_, fx_ = np.nonzero(fol[::8, ::8] > 0.5)           # where leaves can fall from
    P["leaf_from"] = [(int(fx_[i]) * 8, int(fy_[i]) * 8) for i in rnd.sample(range(len(fy_)), min(6, len(fy_)))] if outdoor and len(fy_) else []
    return P


# ------------------------------------------------------------------ the camera's view with depth
def _sample(arr, xw, yw):
    h, w = arr.shape
    xi = np.clip((xw / 8).astype(int), 0, w - 1)
    yi = np.clip((yw / 8).astype(int), 0, h - 1)
    return arr[yi, xi]


def _base_at(P, lv, t):
    L = P["levels"][lv]
    if "cloud" not in L:
        return L["base"]
    im = L["base"].copy()
    cl, (t0, t1) = L["cloud"], L["band"]
    s = int(t * CLOUD_SPEED * lv) % cl.width
    mv = Image.new("RGBA", cl.size, (0, 0, 0, 0))
    mv.paste(cl, (s, 0))
    mv.paste(cl, (s - cl.width, 0))
    mv.putalpha(ImageChops.multiply(mv.getchannel("A"), L["sky"]))      # behind trees / roofs: only where sky shows
    im.paste(mv, (0, t0), mv)
    return im


def view(P, rect, ref, t):
    x0, y0, w = rect
    rx0, ry0, rw = ref
    zc, zr = OUT_W / w, OUT_W / rw
    cx, cy = x0 + w / 2, y0 + w * OUT_H / OUT_W / 2
    rcx, rcy = rx0 + rw / 2, ry0 + rw * OUT_H / OUT_W / 2
    us = np.round(np.linspace(0, OUT_W, GX)).astype(int)
    vs = np.round(np.linspace(0, OUT_H, GY)).astype(int)
    U, V = np.meshgrid(us.astype(np.float32), vs.astype(np.float32))
    xw, yw = x0 + U / zc, y0 + V / zc
    d = _sample(P["depth_s"], xw, yw)
    p = np.clip(P_FAR + (1 - P_FAR) * d / P["dc"], P_FAR, P_NEAR)
    zp = zr * (zc / zr) ** p
    xs = rcx + (cx - rcx) * p + (U - OUT_W / 2) / zp
    ys = rcy + (cy - rcy) * p + (V - OUT_H / 2) / zp
    fol = _sample(P["fol_s"], xw, yw)                     # leaves in the wind: a slow wave across the place
    xs += fol * 3.2 * np.sin(1.7 * t + xw * 0.011 + P["seed"] * 6) + fol * 1.2 * np.sin(3.9 * t + yw * 0.02)
    wat = _sample(P["water_s"], xw, yw)                   # water: a tiny ripple
    xs += wat * 1.6 * np.sin(2.4 * t + yw * 0.09)
    lv = 0.75 if zc < 0.9 else 1.0
    xs, ys = (xs + P["pw"]) * lv, (ys + P["ph"]) * lv
    src = _base_at(P, lv, t)
    mesh = []
    for j in range(GY - 1):
        for i in range(GX - 1):
            mesh.append(((int(us[i]), int(vs[j]), int(us[i + 1]), int(vs[j + 1])),
                         (xs[j, i], ys[j, i], xs[j + 1, i], ys[j + 1, i], xs[j + 1, i + 1], ys[j + 1, i + 1], xs[j, i + 1], ys[j, i + 1])))
    return src.transform((OUT_W, OUT_H), Image.MESH, mesh, Image.BICUBIC).convert("RGBA")


def to_screen(P, rect, ref, xw, yw, p):
    """Where a world point at parallax p lands on screen (for things that live in the place: birds, sparkles)."""
    x0, y0, w = rect
    rx0, ry0, rw = ref
    zc, zr = OUT_W / w, OUT_W / rw
    cx, cy = x0 + w / 2, y0 + w * OUT_H / OUT_W / 2
    rcx, rcy = rx0 + rw / 2, ry0 + rw * OUT_H / OUT_W / 2
    zp = zr * (zc / zr) ** p
    return (xw - (rcx + (cx - rcx) * p)) * zp + OUT_W / 2, (yw - (rcy + (cy - rcy) * p)) * zp + OUT_H / 2, zp


# ------------------------------------------------------------------ life in the place
def _bird(d, x, y, s, flap):
    wy = y - s * 0.5 * flap
    d.line([(x - s, wy), (x - s * 0.45, y - s * 0.15), (x, y)], fill=LINE + (230,), width=max(2, int(s * 0.16)), joint="curve")
    d.line([(x, y), (x + s * 0.45, y - s * 0.15), (x + s, wy)], fill=LINE + (230,), width=max(2, int(s * 0.16)), joint="curve")


def _butterfly(d, x, y, s, open_, col):
    ww = s * max(0.15, open_)
    for sx in (-1, 1):
        d.ellipse([x + sx * ww * 0.1 - (ww if sx < 0 else 0), y - s * 0.75, x + sx * ww * 0.1 + (ww if sx > 0 else 0), y + s * 0.1],
                  fill=col + (255,), outline=LINE + (255,), width=max(1, int(s * 0.1)))
        d.ellipse([x - (ww * 0.75 if sx < 0 else 0), y - s * 0.05, x + (ww * 0.75 if sx > 0 else 0), y + s * 0.55],
                  fill=tuple(min(255, c + 40) for c in col) + (255,), outline=LINE + (255,), width=max(1, int(s * 0.1)))
    d.line([(x, y - s * 0.6), (x, y + s * 0.5)], fill=LINE + (255,), width=max(2, int(s * 0.16)))


def life(P, frame, rect, ref, t):
    d = ImageDraw.Draw(frame)
    W, H = P["W"], P["H"]
    if P["has_sky"] and P["sky_rows"]:
        period = 26.0                                       # a little flock crosses the sky now and then
        k = int(t // period)
        rnd = random.Random(k * 7919 + int(P["seed"] * 1e6))
        q = (t % period) / 14.0
        if q < 1:
            dirn = 1 if rnd.random() < 0.5 else -1
            r0, r1 = P["sky_rows"]
            by = r0 + (r1 - r0) * rnd.uniform(0.15, 0.5)
            bx = (-0.1 + 1.2 * q) * W if dirn > 0 else (1.1 - 1.2 * q) * W
            for i in range(3):
                x, y, zp = to_screen(P, rect, ref, bx - dirn * i * 70, by + (i % 2) * 34 + 12 * math.sin(t * 1.3 + i), 0.45)
                _bird(d, x, y, 15 * zp + 4, math.sin(t * 9 + i * 1.7))
        for j, col in enumerate(((250, 120, 170), (255, 205, 60))):       # two butterflies wander in the middle ground
            ph = P["seed"] * 10 + j * 3.1
            xw = W * (0.5 + 0.42 * math.sin(t * 0.07 + ph) + 0.05 * math.sin(t * 0.53 + ph * 2))
            yw = H * (0.48 + 0.08 * math.sin(t * 0.31 + ph) + 0.025 * math.sin(t * 2.1 + ph))
            x, y, zp = to_screen(P, rect, ref, xw, yw, 0.85)
            _butterfly(d, x, y, 19 * zp + 4, abs(math.sin(t * 11 + ph)), col)
    for i, (lx, ly) in enumerate(P.get("leaf_from", [])):   # now and then a leaf falls from a tree, swinging
        cyc = 11.0 + 2.3 * i
        q = ((t + i * 4.1) % cyc) / 6.0
        if q < 1:
            xw = lx + 70 * math.sin(q * 7 + i) + 60 * q
            yw = ly + q * H * 0.38
            x, y, zp = to_screen(P, rect, ref, xw, yw, 0.9)
            r = 9 * zp + 3
            ang = 0.9 * math.sin(q * 7 + i)
            c, s_ = math.cos(ang), math.sin(ang)
            pts = [(x + c * dx - s_ * dy, y + s_ * dx + c * dy) for dx, dy in ((0, -r), (r * 0.55, 0), (0, r), (-r * 0.55, 0))]
            al = int(255 * min(1.0, (1 - q) / 0.25))
            d.polygon(pts, fill=((120, 185, 60), (240, 170, 50))[i % 2] + (al,), outline=LINE + (al,))
    for gx, gy, ph, sp in P["glints"]:                       # sparkles on water
        a = max(0.0, math.sin(t * 2.2 * sp + ph)) ** 6
        if a < 0.05:
            continue
        x, y, zp = to_screen(P, rect, ref, gx, gy, 1.0)
        s = (5 + 5 * a) * zp
        c = (255, 255, 255, int(235 * a))
        d.line([(x - s, y), (x + s, y)], fill=c, width=max(1, int(s * 0.3)))
        d.line([(x, y - s * 0.7), (x, y + s * 0.7)], fill=c, width=max(1, int(s * 0.3)))


# ------------------------------------------------------------------ light on the characters
def light(P, layer, z):
    """Tint the characters' layer a little toward the place colour and add a soft rim light on the sun side, just inside
    the outline. Only the box that holds characters is processed."""
    bb = layer.getbbox()
    if not bb:
        return layer
    m = 24
    bb = (max(0, bb[0] - m), max(0, bb[1] - m), min(layer.width, bb[2] + m), min(layer.height, bb[3] + m))
    cr = layer.crop(bb)
    rgb, a = cr.convert("RGB"), cr.getchannel("A")
    rgb = Image.blend(rgb, ImageChops.multiply(rgb, Image.new("RGB", rgb.size, P["amb"])), 0.2)
    ol = float(max(2.0, 4.0 * z / 0.75))                # plain float: Pillow 12's GaussianBlur breaks on a numpy radius
    lx, ly = P["ldir"]

    def shifted(k):                                     # alpha sampled k px toward the light
        s = Image.new("L", a.size, 0)
        s.paste(a, (int(round(-lx * k)), int(round(-ly * k))))
        return s
    band = ImageChops.multiply(ImageChops.multiply(a, ImageChops.invert(shifted(ol * 3.6))), shifted(ol * 1.4))
    band = band.filter(ImageFilter.GaussianBlur(ol * 0.7)).point(lambda v: int(v * 0.5))
    rgb = Image.composite(ImageChops.screen(rgb, Image.new("RGB", rgb.size, P["rim"])), rgb, band)
    out = rgb.convert("RGBA")
    out.putalpha(a)
    layer.paste(out, bb[:2])
    return layer
