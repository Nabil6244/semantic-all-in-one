"""Ocean Predators thumbnail (the reference channel's look, our own drawing): the film's main animal as a black-and-white
stippled ink drawing on black, a short hook line in white with one red word, a red arrow to a tiny diver for scale.

    make(animal, hook, dst, size=(1280, 720)) -> dst
    hook_for(texts) -> "IT HUNTS YOU.."             from what the script says the animal does to "you"
    make_for_plan(plan, dst) -> dst | None          main animal = the one on stage longest; written next to the video
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from . import animals as A
from .cards import F

RED = (226, 40, 40, 255)
HOOKS = [  # (what the script says, hook) first match wins
    (r"\b(won'?t|doesn'?t|never|does not|will not) (hunt|attack|eat|bite)", "WON'T HUNT ", "YOU..."),
    (r"\b(follow\w*|circl\w*|stalk\w*|track\w*)\b", "IT FOLLOWS ", "YOU.."),
    (r"\b(can'?t|cannot|doesn'?t) see\b|\bblind\b", "IT CAN'T SEE ", "YOU"),
    (r"\b(sees?|watch\w*|eyes? (?:are )?fixed)\b", "IT SEES ", "YOU.."),
    (r"\b(surviv\w*)\b", "STILL ", "KING?"),
    (r"\b(hunt\w*|attack\w*|eat\w*|kill\w*|bit\w*)\b", "IT HUNTS ", "YOU.."),
]


def hook_for(texts: Sequence[str]) -> Tuple[str, str]:
    whole = " ".join(texts[:12])
    for pat, a, b in HOOKS:
        if re.search(pat, whole, re.I):
            return a, b
    return "YOU'RE ", "NEXT.."


def ink(sp: Image.Image, width: int) -> Image.Image:
    """Painted animal -> stippled black-and-white ink drawing (dither at 2x, then soften back down)."""
    s = width / max(1, sp.width)
    big = sp.resize((max(1, int(sp.width * s * 2)), max(1, int(sp.height * s * 2))), Image.LANCZOS)
    alpha = big.getchannel("A")
    g = ImageOps.autocontrast(big.convert("L"), cutoff=2)
    g = ImageEnhance.Contrast(g).enhance(1.5)
    g = g.filter(ImageFilter.UnsharpMask(radius=3, percent=180, threshold=2))
    dots = g.convert("1").convert("L")                       # Floyd-Steinberg dither: the stipple
    edges = g.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 40 else 0)
    ink_l = Image.composite(Image.new("L", g.size, 255), dots, edges)
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    out.paste((240, 240, 236, 255), (0, 0), Image.composite(ink_l, Image.new("L", g.size, 0), alpha.point(lambda v: 255 if v > 90 else 0)))
    return out.resize((max(1, int(sp.width * s)), max(1, int(sp.height * s))), Image.LANCZOS)


def _arrow(d: ImageDraw.ImageDraw, p0, p1, bend: float = 0.35, width: int = 9) -> None:
    (x0, y0), (x1, y1) = p0, p1
    mx, my = (x0 + x1) / 2 - (y1 - y0) * bend, (y0 + y1) / 2 + (x1 - x0) * bend
    pts = [((1 - t) ** 2 * x0 + 2 * (1 - t) * t * mx + t * t * x1, (1 - t) ** 2 * y0 + 2 * (1 - t) * t * my + t * t * y1)
           for t in [i / 30 for i in range(31)]]
    d.line(pts, fill=RED, width=width, joint="curve")
    ang = math.atan2(y1 - pts[-4][1], x1 - pts[-4][0])
    s = width * 3.2
    d.polygon([(x1, y1), (x1 - s * math.cos(ang - 0.5), y1 - s * math.sin(ang - 0.5)),
               (x1 - s * math.cos(ang + 0.5), y1 - s * math.sin(ang + 0.5))], fill=RED)


def make(animal: str, hook: Tuple[str, str], dst: str, size: Tuple[int, int] = (1280, 720)) -> str:
    w, h = size
    im = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    rnd_specks = [((i * 7919) % w, (i * 104729) % h) for i in range(160)]
    for x, y in rnd_specks:                                   # faint marine snow
        d.ellipse((x, y, x + 2, y + 2), fill=(70, 70, 70, 255))
    from . import art_flow as AF
    pose = "jaw" if AF.path(animal, "jaw") else "side"
    src = Image.open(AF.path(animal, pose)).convert("RGBA") if AF.path(animal, pose) else A.draw(animal, 900, 0, face="left")
    if AF.path(animal, pose):
        src = src.transpose(Image.FLIP_LEFT_RIGHT)            # facing the diver on the left
    drawn = ink(src, int(w * 0.78))
    im.alpha_composite(drawn, (int(w * 0.3), int(h * 0.56 - drawn.height / 2)))
    diver = ink(A.draw("diver", 260, 0, face="right"), int(w * 0.09))
    dx, dy = int(w * 0.14), int(h * 0.66)
    im.alpha_composite(diver, (dx, dy))
    plain, key = hook
    f = F("heavy", int(h * 0.15))
    x, y = int(w * 0.05), int(h * 0.05)
    for ox, oy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
        d.text((x + ox, y + oy), plain + key, font=f, fill=(0, 0, 0, 255))
    d.text((x, y), plain, font=f, fill=(250, 250, 250, 255))
    d.text((x + d.textlength(plain, font=f), y), key, font=f, fill=RED)
    _arrow(d, (x + w * 0.1, y + f.size * 1.3), (dx + diver.width * 0.4, dy - 12), bend=0.25)
    im.convert("RGB").save(dst, quality=92)
    return dst


def make_for_plan(plan: Dict[str, Any], dst: str) -> Optional[str]:
    seen: Counter = Counter()
    for ly in plan.get("layers") or []:
        for e in (ly.get("params") or {}).get("elements") or []:
            a = e.get("args") or {}
            if e.get("kind") == "animal" and a.get("name") not in (None, "diver", "boat", "cage", "tooth") and not a.get("silhouette"):
                t1 = e.get("t1")
                seen[str(a["name"])] += (float(t1) if t1 is not None else float(ly["end"]) - float(ly["start"])) - float(e["t0"])
    if not seen:
        return None
    texts = [str(s.get("text", "")) for s in plan.get("scenes") or []]
    return make(seen.most_common(1)[0][0], hook_for(texts), dst)
