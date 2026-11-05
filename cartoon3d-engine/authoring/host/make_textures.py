"""Flat, glTF-ready textures for the cartoon host. Run with system python3: python3 make_textures.py
Writes build/tex/. Skin is softened from the CC0 MakeHuman texture; eyes, hair and denim are drawn here."""
import os
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "build", "tex")
os.makedirs(OUT, exist_ok=True)
DATA = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/.user/user_default/mpfb/data")
rng = np.random.default_rng(7)


def srgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float) / 255


def save(a, name):
    Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).save(os.path.join(OUT, name))


def blur1d(a, sigma, axis):
    k = np.exp(-0.5 * (np.arange(-int(3 * sigma), int(3 * sigma) + 1) / sigma) ** 2); k /= k.sum()
    f = np.fft.rfft(a, axis=axis)
    pad = np.zeros(a.shape[axis]); idx = (np.arange(len(k)) - len(k) // 2) % a.shape[axis]
    np.add.at(pad, idx, k)                          # circular kernel, so long blurs stay tileable
    sh = [1] * a.ndim; sh[axis] = -1
    return np.fft.irfft(f * np.fft.rfft(pad).reshape(sh), n=a.shape[axis], axis=axis)


def normal_from(h, strength):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength
    n = np.dstack([-dx, dy, np.ones_like(h)]); n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def skin():
    src = Image.open(f"{DATA}/skins/young_caucasian_female/young_lightskinned_female_diffuse.png").convert("RGB")
    soft = np.asarray(src.filter(ImageFilter.GaussianBlur(14)), float) / 255
    fine = np.asarray(src.filter(ImageFilter.GaussianBlur(3)), float) / 255
    H, W, _ = soft.shape
    yy, xx = np.mgrid[0:H, 0:W]; u, v = xx / W, yy / H
    # keep the lips and nails crisp (red-dominant areas), melt pores and stubble-like scalp tone everywhere else
    red = np.clip((fine[..., 0] - fine[..., 1] - 0.27) * 8, 0, 1)[..., None]
    lid = ((np.abs(u - 0.838) < 0.05) & (v > 0.42) & (v < 0.61)).astype(float)
    red = red * (1 - blur1d(blur1d(lid, 12, 0), 12, 1))[..., None]             # lids go plain skin: no dark rings once they stretch
    a = soft * (1 - red) + fine * red
    target = srgb("#f8c9a6")
    lum = a.mean(2, keepdims=True); shade = 0.72 + 0.28 * lum / lum.mean()
    face = (u > 0.78) & (u < 0.98) & (v > 0.36) & (v < 0.68)                 # one even tone over the face: no rings when features stretch
    fm = blur1d(blur1d(face.astype(float), 45, 0), 45, 1)[..., None]            # soft edge: a hard mask reads as a groove on the face
    shade = shade * (1 - fm) + fm
    a = target * shade * (1 - red) + a * red
    lips = np.exp(-(((u - 0.91) / 0.034) ** 4 + ((v - 0.515) / 0.058) ** 4))[..., None] * np.clip((fine[..., 0:1] - fine[..., 1:2] - 0.2) * 9, 0, 1)
    a = a * (1 - lips) + (a * 0.35 + srgb("#e8705f") * 0.65) * lips           # warmer, cleaner lip colour
    for cu, cv in ((0.875, 0.437), (0.875, 0.59)):   # cheek blush, in the face island of the atlas
        g = np.exp(-(((u - cu) / 0.040) ** 2 + ((v - cv) / 0.040) ** 2))[..., None]
        a = a * (1 - 0.5 * g) + srgb("#f58f7f") * 0.5 * g
    g = np.exp(-(((u - 0.875) / 0.014) ** 2 + ((v - 0.515) / 0.016) ** 2))[..., None]   # a touch of colour on the nose tip
    a = a * (1 - 0.4 * g) + srgb("#f58f7f") * 0.4 * g
    mott = blur1d(blur1d(rng.standard_normal((H, W)), 40, 0), 40, 1); mott /= mott.std()
    fine_n = blur1d(blur1d(rng.standard_normal((H, W)), 1.3, 0), 1.3, 1); fine_n /= fine_n.std()
    a = a * (1 + 0.012 * mott[..., None]) * (1 + np.array([0.012, -0.004, -0.012]) * mott[..., None])   # living skin is never one tone
    a = a * (1 + 0.006 * fine_n[..., None])
    save(a, "skin.png")
    save(normal_from(fine_n, 0.05), "skin_n.png")
    rough = 0.56 + 0.03 * mott + 0.02 * fine_n
    tz = np.exp(-(((u - 0.86) / 0.035) ** 2 + ((v - 0.515) / 0.03) ** 2))     # slight sheen down the nose
    lipm = np.exp(-(((u - 0.91) / 0.028) ** 2 + ((v - 0.515) / 0.05) ** 2))
    rough = rough - 0.13 * tz - 0.24 * lipm
    save(np.dstack([np.zeros_like(rough), np.clip(rough, 0, 1), np.zeros_like(rough)]), "skin_r.png")


def eyes():
    """Front view of one eyeball: u,v span the sphere's diameter, v up, iris in the middle."""
    H = 512; yy, xx = np.mgrid[0:H, 0:H].astype(float)
    dx, dy = xx / H - 0.5, yy / H - 0.5; r = np.hypot(dx, dy); th = np.arctan2(dy, dx)
    a = np.ones((H, H, 3)) * srgb("#fbf8f3")
    a = a * (1 - np.clip((r - 0.30) / 0.2, 0, 1)[..., None] * 0.10)
    R = 0.31
    t = np.clip(r / R, 0, 1)[..., None]
    fib = (0.5 + 0.5 * np.sin(th * 46 + 3 * np.sin(th * 7)))[..., None] * 0.16
    col = (srgb("#4a2712") * (1 - t) + srgb("#c0792e") * t) * (0.92 + fib)
    glow = np.clip(1 - np.hypot(dx, dy + 0.1) / 0.2, 0, 1)[..., None] * 0.35   # warm light pooling low in the iris
    col = col + srgb("#e8a24e") * glow * (t > 0.45)
    ring = np.clip((t - 0.84) / 0.16, 0, 1)
    col = col * (1 - ring) + srgb("#22120a") * ring
    pupil = np.clip((0.16 - r) / 0.008, 0, 1)[..., None]
    col = col * (1 - pupil) + srgb("#0a0605") * pupil
    m = np.clip((R - r) / 0.006, 0, 1)[..., None]
    a = a * (1 - m) + col * m
    a = a * (1 - 0.5 * np.clip((-0.02 - dy) / 0.26, 0, 1)[..., None] ** 1.5)  # shadow the upper lid casts: depth
    for cx, cy, rad in ((-0.09, -0.11, 0.062), (0.1, 0.1, 0.026)):         # catchlights (image y is down)
        h = np.clip((rad - np.hypot(dx - cx, dy - cy)) / 0.006, 0, 1)[..., None]
        a = a * (1 - h) + h
    save(a, "eye.png")


def hair():
    S = 1024
    n = rng.standard_normal((S, S))
    streak = blur1d(blur1d(n, 2.2, 1), 90, 0); streak /= streak.std()
    broad = blur1d(blur1d(rng.standard_normal((S, S)), 16, 1), 200, 0); broad /= broad.std()
    h = 0.6 * streak + 0.7 * broad
    t = np.clip(0.5 + h * 0.2, 0, 1)[..., None]
    a = srgb("#2a170d") * (1 - t) + srgb("#6a3f22") * t
    save(a, "hair.png"); save(normal_from(h, 0.55), "hair_n.png")


def denim():
    S = 1024
    yy, xx = np.mgrid[0:S, 0:S].astype(float)
    tw = np.sin((xx + yy) * 2 * np.pi / 8)          # diagonal twill, tileable
    slub = blur1d(blur1d(rng.standard_normal((S, S)), 1.2, 0), 26, 1); slub /= slub.std()
    fade = blur1d(blur1d(rng.standard_normal((S, S)), 40, 0), 40, 1); fade /= fade.std()
    t = np.clip(0.5 + 0.2 * tw + 0.12 * slub + 0.025 * fade, 0, 1)[..., None]
    a = srgb("#28558f") * (1 - t) + srgb("#5b8ac2") * t
    save(a, "denim.png"); save(normal_from(tw * 0.5 + slub * 0.5, 0.45), "denim_n.png")


def alpha_card(rel, name, colour):
    """Keep an asset's alpha, replace its colour: brows and lashes become one clean dark tone."""
    a = np.asarray(Image.open(f"{DATA}/{rel}").convert("RGBA"), float) / 255
    rgb = np.ones_like(a[..., :3]) * srgb(colour)
    Image.fromarray((np.dstack([rgb, a[..., 3]]) * 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, name))


def strands(name, colour, H, W, fade, along=False, amount=0.42):
    """Alpha hair strip: fine hairs that thin out towards one edge. along=True runs hairs lengthwise (brows)."""
    n = blur1d(blur1d(rng.standard_normal((H, W)), 40, 1), 1.6, 0) if along else blur1d(blur1d(rng.standard_normal((H, W)), 1.0, 1), 34, 0)
    n /= n.std()
    v = np.linspace(0, 1, H)[:, None]
    al = np.clip(fade(v) + amount * n * (fade(v) > 0.02), 0, 1)
    rgb = np.ones((H, W, 3)) * srgb(colour)
    Image.fromarray((np.dstack([rgb, al]) * 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, name))


def teeth():
    a = np.asarray(Image.open(f"{DATA}/teeth/teeth_base/teeth.png").convert("RGB"), float) / 255
    pink = np.clip((a[..., 0] - a[..., 2] - 0.12) * 6, 0, 1)[..., None]        # gums keep their colour
    save(a * pink + np.clip(a * 1.6 + 0.12, 0, 1) * (1 - pink), "teeth.png")


def shoes():
    """Clean white canvas sneakers from the CC0 pair: keep its shading, drop its colour."""
    a = np.asarray(Image.open(f"{DATA}/clothes/shoes05/shoes05_diffuse.png").convert("RGB"), float) / 255
    g = a.mean(2, keepdims=True)
    save(np.clip(0.88 + 0.16 * g, 0, 1) * srgb("#fffdf8"), "shoes.png")


if __name__ == "__main__":
    skin(); eyes(); hair(); denim(); teeth(); shoes()
    strands("hair_edge.png", "#3b2214", 256, 2048, lambda v: np.clip(v * 1.2 - 0.05, 0, 1) ** 1.4)   # image row 0 is the outer edge
    strands("brow_soft.png", "#2f1b10", 256, 1024, lambda v: np.clip(2.6 - np.abs(v - 0.5) * 5.2, 0, 1), along=True, amount=0.2)
    alpha_card("eyebrows/eyebrow010/eyebrow010.png", "brow.png", "#2e1a10")
    alpha_card("eyelashes/eyelashes02/eyelashes02.png", "lash.png", "#1c100a")
    print("textures in", OUT)
