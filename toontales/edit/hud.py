"""Car-channel HUD for the edit: an animated meter at the top of the frame and a callout label on a thin line.

A plan shot may carry:
  "hud": {"label": "HP", "from": 120, "to": 480, "max": 800, "rival": 717, "rival_label": "HELLCAT",
          "color": "orange"|"green"|"red"|"blue"|[r,g,b], "t0": 0.15, "t1": 0.75, "fmt": "{v} HP"}
      the big number counts from -> to between t0 and t1 (fractions of the shot) while the bar fills; a small
      tick + label marks the rival's value on the bar. "fmt" defaults to "{v} <label>".
  "callout": {"text": "1.0 LITER", "x": 0.5, "y": 0.34}
      white outlined text near the top with a thin line down to the point (x, y) (fractions of the frame).
Both sit in the top third and keep the caption band (~70% down) clear.

Library: hud.frames(spec, dur, size, out_dir) -> png pattern; hud.callout(spec, size, out_dir) -> png
"""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FPS = 30
FONTS = Path("/System/Library/Fonts/Supplemental")
COLORS = {"orange": (255, 150, 40), "green": (70, 220, 90), "red": (240, 60, 55), "blue": (70, 160, 255),
          "yellow": (255, 214, 64)}
INK = (20, 16, 14, 255)
VERSION = "h2"


def _font(size):
    for n in ("Arial Black.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(str(FONTS / n), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _ease(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _num(v, whole=True):
    """whole: the meter's end values are whole numbers, so the count shows none of the decimals in between."""
    return f"{v:,.0f}" if whole or abs(v) >= 100 else f"{v:.1f}"


def _key(*a):
    return hashlib.sha1(json.dumps([a, VERSION], sort_keys=True).encode()).hexdigest()[:14]


def frames(spec, dur, size, out_dir):
    """Render the meter for every frame of the shot. Returns the ffmpeg input pattern."""
    W, H = size
    out = Path(out_dir) / f"hud_{_key(spec, dur, size)}"
    n = int(round(dur * FPS))
    if (out / f"h{n - 1:04d}.png").exists():
        return str(out / "h%04d.png")
    out.mkdir(parents=True, exist_ok=True)
    s = W / 1080
    col = spec.get("color", "orange")
    col = tuple(col) if isinstance(col, list) else COLORS.get(col, COLORS["orange"])
    a, b = float(spec.get("from", 0)), float(spec.get("to", 100))
    mx = float(spec.get("max") or max(a, b, spec.get("rival") or 0) * 1.15 or 1)
    fmt = spec.get("fmt") or ("{v} " + str(spec.get("label", "")).strip()).strip()
    whole = float(a).is_integer() and float(b).is_integer()
    t0, t1 = spec.get("t0", 0.15), spec.get("t1", 0.75)
    big = _font(int(96 * s))
    small = _font(int(34 * s))
    bx0, bx1, by, bh = W * 0.2, W * 0.8, H * 0.135, 26 * s
    for f in range(n):
        k = _ease((f / FPS / dur - t0) / max(0.01, t1 - t0))
        v = a + (b - a) * k
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((W / 2, H * 0.085), fmt.format(v=_num(v, whole)), font=big, anchor="mm", fill=(255, 255, 255, 255),
               stroke_width=int(9 * s), stroke_fill=(*[int(c * 0.45) for c in col], 255))
        d.rounded_rectangle([bx0 - 5 * s, by - 5 * s, bx1 + 5 * s, by + bh + 5 * s], radius=int(18 * s), fill=INK)
        fill = bx0 + (bx1 - bx0) * min(1.0, max(0.0, v / mx))
        if fill > bx0 + 4:
            d.rounded_rectangle([bx0, by, fill, by + bh], radius=int(13 * s), fill=(*col, 255))
        if spec.get("rival") is not None:
            rx = bx0 + (bx1 - bx0) * min(1.0, float(spec["rival"]) / mx)
            d.rectangle([rx - 3 * s, by - 14 * s, rx + 3 * s, by + bh + 14 * s], fill=(255, 255, 255, 255))
            lab = f"{spec.get('rival_label', 'RIVAL')}: {_num(float(spec['rival']))}"
            d.text((rx, by + bh + 36 * s), lab, font=small, anchor="mm", fill=(255, 214, 64, 255),
                   stroke_width=int(5 * s), stroke_fill=INK)
        im.save(out / f"h{f:04d}.png")
    return str(out / "h%04d.png")


def callout(spec, size, out_dir):
    W, H = size
    p = Path(out_dir) / f"callout_{_key(spec, size)}.png"
    if p.exists():
        return p
    s = W / 1080
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x, y = W * spec.get("x", 0.5), H * spec.get("y", 0.34)
    ty = min(y - 120 * s, H * spec.get("text_y", 0.2))
    f = _font(int(76 * s))
    text = str(spec.get("text", "")).upper()
    while d.textbbox((0, 0), text, font=f)[2] > W * 0.86 and f.size > 30:
        f = _font(f.size - 6)
    tx = min(max(x, W * 0.1 + d.textlength(text, font=f) / 2), W * 0.9 - d.textlength(text, font=f) / 2)
    d.line([(x, ty + 46 * s), (x, y)], fill=INK, width=int(11 * s))
    d.line([(x, ty + 46 * s), (x, y)], fill=(255, 255, 255, 255), width=int(5 * s))
    d.text((tx, ty), text, font=f, anchor="mm", fill=(255, 255, 255, 255), stroke_width=int(8 * s), stroke_fill=INK)
    im.save(p)
    return p
