"""The Podcast Cut look: one dark grade for the speaker's camera and the stock (so both read as one film), and the text
drawn with PIL (the app's ffmpeg has no libass / drawtext): the one-line caption, the channel watermark, the
"<channel> presents" card and the thumbnail words.

Grade: blacks pulled down, about 25 % less colour, warm highlights, soft vignette, light grain.
Caption: 3-6 words, small spaced uppercase, centred at about 52 % height, white at 88 % with a soft shadow.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"
W, H = 1920, 1080

GRADE = ("eq=contrast=1.08:brightness=-0.07:saturation=0.6:gamma=0.86,"
         "colorbalance=rs=0.02:gs=-0.01:bs=-0.04:bm=-0.02:rh=0.06:gh=0.025:bh=-0.06,"
         "curves=all='0/0 0.25/0.17 0.6/0.52 1/0.92',vignette=PI/3.6,noise=alls=5:allf=t")
GRADE_LIGHT = "eq=contrast=1.08:brightness=-0.07:saturation=0.6:gamma=0.86,vignette=PI/3.6"   # previews: no grain (smaller, faster)


def fit_filter(w: int = W, h: int = H) -> str:
    """Fill the frame (scale up and centre-crop): 16:9 sources fill a 16:9 frame, any source fills a 9:16 Short."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},setsar=1")


def grade(preview: bool = False) -> str:
    return GRADE_LIGHT if preview else GRADE


@lru_cache(maxsize=16)
def font(size: int, bold: bool = True):
    from PIL import ImageFont
    for name in (("Manrope-Bold.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf") if bold else ("Inter-Regular.ttf", "DMSans-Medium.ttf")):
        p = FONTS / name
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def _spaced(draw, text: str, fnt, tracking: float) -> Tuple[int, int]:
    w = 0
    for ch in text:
        w += draw.textlength(ch, font=fnt) + tracking
    asc, desc = fnt.getmetrics()
    return int(max(0, w - tracking)), asc + desc


def _draw_spaced(draw, xy, text, fnt, tracking, fill):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + tracking


def caption_png(text: str, path: Path, w: int = W, h: int = H, short: bool = False) -> int:
    """One caption line as a full-width transparent strip PNG. Returns the y to overlay it at (x is 0)."""
    from PIL import Image, ImageDraw, ImageFilter
    text = " ".join(text.upper().split())
    size = int(h * 0.026) if not short else int(w * 0.05)
    fnt = font(size)
    tracking = size * 0.16
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    tw, th = _spaced(probe, text, fnt, tracking)
    while tw > w * 0.86 and size > 14:
        size -= 2
        fnt = font(size)
        tracking = size * 0.16
        tw, th = _spaced(probe, text, fnt, tracking)
    sh = th + 40
    y_mid = int(h * (0.52 if not short else 0.68))
    x, y = (w - tw) // 2, 20
    img = Image.new("RGBA", (w, sh), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (w, sh), (0, 0, 0, 0))
    _draw_spaced(ImageDraw.Draw(shadow), (x, y + 2), text, fnt, tracking, (0, 0, 0, 210))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(4)))
    _draw_spaced(ImageDraw.Draw(img), (x, y), text, fnt, tracking, (255, 255, 255, 228))
    img.save(path)
    return max(0, y_mid - sh // 2)


def watermark_png(channel: str, path: Path, w: int = W, h: int = H) -> Path:
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if channel.strip():
        d = ImageDraw.Draw(img)
        fnt = font(int(h * 0.019), bold=False)
        tw = d.textlength(channel, font=fnt)
        d.text(((w - tw) / 2, h * 0.94), channel, font=fnt, fill=(255, 255, 255, 90))
    img.save(path)
    return path


def presents_png(channel: str, path: Path, w: int = W, h: int = H) -> Path:
    """'<Channel>' big, 'presents' small under it, centred: the card between the hook and the talk."""
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    big, small = font(int(min(w, h * 1.6) * 0.045)), font(int(min(w, h * 1.6) * 0.018), bold=False)
    name = channel.strip() or "Presents"
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bw = d.textlength(name, font=big)
    sw = d.textlength("presents", font=small)
    y = h * 0.44
    d.text(((w - bw) / 2, y), name, font=big, fill=(255, 255, 255, 245))
    d.text(((w - sw) / 2, y + big.size * 1.25), "presents", font=small, fill=(255, 255, 255, 200))
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh.paste((0, 0, 0, 180), mask=layer.split()[3])
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(8)))
    img = Image.alpha_composite(img, layer)
    img.save(path)
    return path
