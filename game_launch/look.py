"""Game Launch look: Vice-sunset colours, cards drawn with PIL, the glitch cut and a synthwave bed made in code.

Everything here draws or writes one file; nothing knows about the CSV or the app."""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
PINK, TEAL, NAVY, WHITE = (255, 46, 136), (0, 214, 201), (12, 16, 40), (255, 255, 255)
TEAL_DARK = (0, 150, 150)
_ROOT = Path(__file__).resolve().parent.parent
_HEAD_FONTS = ("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", "C:/Windows/Fonts/bahnschrift.ttf",
               str(_ROOT / "assets/fonts/Outfit-ExtraBold.ttf"))
_TAG_FONTS = (str(_ROOT / "assets/fonts/Outfit-ExtraBold.ttf"), str(_ROOT / "assets/fonts/Inter-Bold.ttf"))

# a short colour-split + noise burst on the first frames of every shot: the series' cut
GLITCH = "rgbashift=rh=-14:bh=14:gv=6:enable='lt(t,0.18)',noise=alls=35:allf=t:enable='lt(t,0.14)'"
GRADE = "eq=saturation=1.1:contrast=1.04,colorbalance=rs=-0.03:bs=0.05:rh=0.05:bh=-0.03,vignette=PI/5"


def _first(paths) -> str:
    for p in paths:
        if Path(p).is_file():
            return p
    return paths[-1]


F_HEAD, F_TAG = _first(_HEAD_FONTS), _first(_TAG_FONTS)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, max(8, int(size)))


def fit(text: str, path: str, size: int, max_w: float) -> ImageFont.FreeTypeFont:
    """The font at `size`, shrunk until the text fits max_w (the fallback font is wider than the condensed one)."""
    d = ImageDraw.Draw(Image.new("L", (4, 4)))
    f = font(path, size)
    while size > 20 and d.textlength(text, font=f) > max_w:
        size = int(size * 0.92)
        f = font(path, size)
    return f


def shadow_text(img: Image.Image, xy, text: str, f, fill=WHITE, anchor: str = "mm", blur: int = 10) -> None:
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((xy[0] + 4, xy[1] + 6), text, font=f, fill=(0, 0, 0, 200), anchor=anchor)
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(img).text(xy, text, font=f, fill=fill, anchor=anchor)


def pill(img: Image.Image, xy, text: str, bg, size: int = 40, anchor: str = "lt") -> None:
    d = ImageDraw.Draw(img)
    f = font(F_TAG, size)
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    pw, ph = r - l + 44, b - t + 26
    x, y = xy
    if anchor == "rt":
        x -= pw
    d.rounded_rectangle((x, y, x + pw, y + ph), radius=ph // 2, fill=tuple(bg) + (235,))
    d.text((x + 22 - l, y + 13 - t), text, font=f, fill=WHITE)


def band(img: Image.Image, top: int, strength: int = 180) -> None:
    b = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    h = img.size[1]
    for y in range(top, h):
        a = int(strength * ((y - top) / max(1, h - top)) ** 1.5)
        d.line([(0, y), (img.size[0], y)], fill=NAVY + (a,))
    img.alpha_composite(b)


# ---------------------------------------------------------------------------------------------------------------- cards

def chip_png(real: bool, path) -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pill(img, (60, 56), "REAL LIFE" if real else "IN GAME", TEAL_DARK if real else PINK, 38)
    img.save(path)


def title_png(head: str, sub: str, tag: str, path) -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band(img, H // 2)
    f = fit(head, F_HEAD, 210 if len(head) < 10 else 170, W - 200)
    shadow_text(img, (W // 2, 760), head, f)
    tw = ImageDraw.Draw(img).textlength(head, font=f)
    ImageDraw.Draw(img).rectangle((W // 2 - tw / 2, 850, W // 2 + tw / 2, 862), fill=PINK)
    if sub:
        shadow_text(img, (W // 2, 925), sub, fit(sub, F_TAG, 44, W - 200), fill=(255, 220, 235))
    if tag:
        pill(img, (60, 56), tag, PINK, 38)
    img.save(path)


def chapter_png(num: str, title: str, sub: str, path) -> None:
    img = Image.new("RGBA", (W, H), NAVY + (120,))
    d = ImageDraw.Draw(img)
    fn = font(F_HEAD, 300)
    shadow_text(img, (150, 640), num, fn, fill=PINK, anchor="ls")
    nw = d.textlength(num, font=fn)
    x = 150 + nw + 90
    d.rectangle((x - 50, 380, x - 38, 640), fill=WHITE)
    shadow_text(img, (x, 560), title, fit(title, F_HEAD, 170, W - x - 80), anchor="ls")
    if sub:
        shadow_text(img, (x + 4, 630), sub, font(F_TAG, 40), fill=TEAL, anchor="ls")
    img.save(path)


def split_png(left: str, right: str, path) -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((W // 2 - 5, 0, W // 2 + 5, H), fill=PINK + (255,))
    pill(img, (60, 56), "IN GAME", PINK, 38)
    pill(img, (W - 60, 56), "REAL LIFE", TEAL_DARK, 38, anchor="rt")
    band(img, H - 330, 190)
    if left or right:
        eq = "  =  " if left and right else ""
        f = fit(left + eq + right, F_HEAD, 112, W - 160)
        wl, we, wr = (d.textlength(t, font=f) for t in (left, eq, right))
        x = W / 2 - (wl + we + wr) / 2
        shadow_text(img, (x, 990), left, f, anchor="ls")
        shadow_text(img, (x + wl, 990), eq, f, fill=PINK, anchor="ls")
        shadow_text(img, (x + wl + we, 990), right, f, fill=TEAL, anchor="ls")
    img.save(path)


def short_png(top: str, second: str, foot: str, path) -> None:
    img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    shadow_text(img, (540, 330), top, fit(top, F_HEAD, 150, 1000))
    if second:
        shadow_text(img, (540, 470), second, fit(second, F_HEAD, 120, 1000), fill=PINK)
    if foot:
        shadow_text(img, (540, 1560), foot, fit(foot, F_HEAD, 90, 1000), fill=TEAL)
    img.save(path)


def thumbnail(left: Image.Image, right: Image.Image, head: str, sub: str, tag: str, path) -> None:
    """1280x720: game frame | real frame, pink divider, big text at the bottom."""
    from PIL import ImageEnhance

    def half(im):
        im = im.convert("RGB").resize((W, H))
        return ImageEnhance.Color(im.crop((W // 4, 0, W // 4 + W // 2, H))).enhance(1.3)

    img = Image.new("RGBA", (W, H))
    img.paste(half(left), (0, 0))
    img.paste(half(right), (W // 2, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((W // 2 - 8, 0, W // 2 + 8, H), fill=PINK)
    pill(img, (50, 50), tag or "IN GAME", PINK, 70)
    pill(img, (W - 50, 50), "REAL LIFE", TEAL_DARK, 70, anchor="rt")
    band(img, 560, 230)
    shadow_text(img, (W // 2, 880), head, fit(head, F_HEAD, 250, W - 120), blur=16)
    if sub:
        shadow_text(img, (W // 2, 1010), sub, fit(sub, F_HEAD, 110, W - 160), fill=TEAL, blur=12)
    img.convert("RGB").resize((1280, 720)).save(path, quality=92)


# ---------------------------------------------------------------------------------------------------------------- music

SR = 44100
BPM = 108


def _synth(seconds: float) -> np.ndarray:
    """A small synthwave arrangement (pad, bass, arpeggio, drums); its patterns repeat every 4 bars."""
    beat = 60 / BPM
    n = int(seconds * SR)
    t = np.arange(n) / SR
    mix = np.zeros(n)
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)  # noqa: E731
    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]  # Am F C G
    bar = beat * 4

    def lp(x, a):
        y = np.empty_like(x)
        acc = 0.0
        for k in range(len(x)):
            acc += a * (x[k] - acc)
            y[k] = acc
        return y

    def saw(f, tt):
        return 2 * ((tt * f) % 1) - 1

    pad = np.zeros(n)
    for c in range(int(seconds / bar) + 1):
        s0, s1 = int(c * bar * SR), min(n, int((c + 1) * bar * SR))
        if s0 >= n:
            break
        tt = t[s0:s1] - t[s0]
        env = np.minimum(1, tt / 0.6) * np.minimum(1, (bar - tt) / 0.3)
        for m in chords[c % 4]:
            for det in (-0.12, 0.12):
                pad[s0:s1] += saw(hz(m + 12) * 2 ** (det / 12), tt) * env
    mix += lp(pad, 0.06) * 0.05
    for k in range(int(seconds / (beat / 2))):
        s0 = int(k * beat / 2 * SR)
        s1 = min(n, s0 + int(beat / 2 * SR))
        if s0 >= n:
            break
        tt = t[s0:s1] - t[s0]
        root = chords[int(k * beat / 2 / bar) % 4][0] - 24
        mix[s0:s1] += saw(hz(root), tt) * np.exp(-tt * 6) * 0.22
    for k in range(int(seconds / (beat / 4))):
        s0 = int(k * beat / 4 * SR)
        s1 = min(n, s0 + int(beat / 4 * SR))
        if s0 >= n:
            break
        tt = t[s0:s1] - t[s0]
        ch = chords[int(k * beat / 4 / bar) % 4]
        m = (ch + tuple(x + 12 for x in ch))[k % 6] + 12
        mix[s0:s1] += np.sign(np.sin(2 * np.pi * hz(m) * tt)) * np.exp(-tt * 18) * 0.035
    rng = np.random.default_rng(7)
    for k in range(int(seconds / beat) + 1):
        s0 = int(k * beat * SR)
        if s0 >= n:
            break
        seg = min(n - s0, int(0.45 * SR))
        tt = np.arange(seg) / SR
        if k % 2 == 0:
            mix[s0:s0 + seg] += np.sin(2 * np.pi * (45 * tt + 2.5 * (1 - np.exp(-tt * 30)))) * np.exp(-tt * 9) * 0.5
        else:
            mix[s0:s0 + seg] += rng.standard_normal(seg) * np.exp(-tt * 9) * 0.16
        for h in (0, 0.5):
            hs = int((k + h) * beat * SR)
            hl = min(n - hs, int(0.05 * SR))
            if hl > 0:
                mix[hs:hs + hl] += np.diff(rng.standard_normal(hl + 1)) * np.exp(-np.arange(hl) / SR * 80) * 0.03
    return np.tanh(mix * 1.4) * 0.7


def music(total: float, path, cache: Optional[Path] = None) -> None:
    """A synthwave bed `total` s long: one seamless 8-bar loop (made once, cached) tiled, faded in and out. No licensed music."""
    loop_f = Path(cache or Path(path).parent) / "synthwave_loop.npy"
    if loop_f.is_file():
        loop = np.load(loop_f)
    else:
        x = _synth(40.0)
        bar = 60 / BPM * 4
        loop = x[int(4 * bar * SR):int(12 * bar * SR)].astype(np.float32)   # bars 4-12: seamless, past the start
        try:
            loop_f.parent.mkdir(parents=True, exist_ok=True)
            np.save(loop_f, loop)
        except OSError:
            pass
    n = int(total * SR)
    y = np.tile(loop, n // len(loop) + 1)[:n]
    t = np.arange(n) / SR
    y = y * np.minimum(1, t / 1.5) * np.minimum(1, (total - t) / 3.0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())


def size_of(path) -> Tuple[int, int]:
    with Image.open(path) as im:
        return im.size
