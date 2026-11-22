"""Looks = pens, paper and finishing. Every pose, prop and place works in every look.

bg: paper | chalk | flat | crt | night | painted   (painted = a Flow picture per place, flat colours if none)
fills: palette for props/places (pale tints in ink looks, bright in Colour Pop)
fig_colors: per-figure line colours (None = all figures in ink)
post: finishing passes (grain, vignette, scanlines, bezel)
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = HERE / "assets" / "fonts"

_BASE = {
    "line": 0.028, "wobble": 0.0045, "boil_frames": 3, "ground": 0.80, "shadow": 0.16,
    "bg_alpha": 0.42, "fill_alpha": 1.0, "bg_fill_alpha": 0.55, "fig_colors": None,
    "caption_box": None, "upper": False, "post": (), "ground_fill": None,
    "font": str(FONTS / "Kalam-Bold.ttf"),
    "head_fill": None, "halo": None, "text_stroke": None, "ground_line": True,
}


def _look(**kw):
    d = dict(_BASE)
    d.update(kw)
    d.setdefault("text", d["ink"])
    d.setdefault("bg_ink", d["ink"])
    return d


INK_PAPER = _look(
    name="ink_paper", bg="paper", paper=(243, 235, 219), ink=(32, 28, 25), accent=(198, 52, 40),
    fills={"a": (236, 196, 186), "b": (205, 214, 222), "c": (240, 222, 170), "d": (204, 222, 196),
           "e": (222, 204, 182), "light": (250, 246, 238), "dark": (120, 112, 104), "ink": (32, 28, 25)},
)

CHALK_DARK = _look(
    name="chalk_dark", bg="chalk", paper=(34, 42, 38), ink=(236, 236, 226), accent=(244, 208, 96),
    line=0.026, wobble=0.0055, shadow=0.0, bg_alpha=0.38, bg_fill_alpha=0.18,
    fills={"a": (150, 90, 90), "b": (90, 120, 140), "c": (170, 150, 80), "d": (90, 130, 95),
           "e": (130, 110, 90), "light": (70, 80, 76), "dark": (24, 28, 26), "ink": (236, 236, 226)},
    post=("chalk",),
)

COLOUR_POP = _look(
    name="colour_pop", bg="flat", paper=(236, 241, 248), ink=(34, 38, 64), accent=(232, 64, 84),
    line=0.033, wobble=0.003, shadow=0.22, bg_alpha=0.85, bg_fill_alpha=1.0,
    fig_colors=[(36, 96, 206), (232, 112, 36), (40, 160, 110)],
    fills={"a": (240, 92, 104), "b": (96, 170, 236), "c": (255, 204, 64), "d": (88, 196, 120),
           "e": (214, 140, 84), "light": (255, 255, 255), "dark": (70, 78, 110), "ink": (34, 38, 64)},
    ground_fill=(132, 206, 138), caption_box=(255, 255, 255),
    font=str(FONTS / "Outfit-ExtraBold.ttf"),
)

RETRO_TV = _look(
    name="retro_tv", bg="crt", paper=(44, 58, 70), ink=(238, 240, 232), accent=(255, 176, 64),
    line=0.034, wobble=0.0025, shadow=0.0, bg_alpha=0.32, bg_fill_alpha=0.22,
    fills={"a": (200, 110, 70), "b": (90, 140, 170), "c": (220, 180, 90), "d": (100, 160, 120),
           "e": (150, 120, 96), "light": (90, 108, 118), "dark": (30, 38, 46), "ink": (238, 240, 232)},
    upper=True, post=("scanlines", "bezel"), font=str(FONTS / "JetBrainsMono-Bold.ttf"),
)

NIGHT_THRILLER = _look(
    name="night_thriller", bg="night", paper=(14, 18, 30), ink=(208, 216, 230), accent=(226, 40, 46),
    line=0.026, wobble=0.004, shadow=0.0, bg_alpha=0.30, bg_fill_alpha=0.16,
    fills={"a": (130, 30, 36), "b": (50, 70, 110), "c": (150, 130, 70), "d": (50, 90, 70),
           "e": (90, 70, 60), "light": (44, 52, 72), "dark": (10, 12, 20), "ink": (208, 216, 230)},
    upper=True, post=("vignette", "grain"), font=str(FONTS / "Outfit-ExtraBold.ttf"),
)

# Meme: stickmen on painted rooms (Flow pictures, made once per place and kept), thick black line with a white
# outline so they read on any picture, white heads, white captions with a black edge.
MEME = _look(
    name="meme", bg="painted", paper=(236, 241, 248), ink=(18, 18, 20), accent=(255, 212, 0),
    line=0.036, wobble=0.0022, shadow=0.34, bg_alpha=0.85, bg_fill_alpha=1.0,
    fills={"a": (240, 92, 104), "b": (96, 170, 236), "c": (255, 204, 64), "d": (88, 196, 120),
           "e": (214, 140, 84), "light": (255, 255, 255), "dark": (70, 78, 110), "ink": (18, 18, 20)},
    head_fill=(255, 255, 255), halo=(255, 255, 255), text=(255, 255, 255), text_stroke=(12, 12, 14),
    upper=True, ground_line=False, font=str(FONTS / "Outfit-ExtraBold.ttf"),
)

LOOKS = {l["name"]: l for l in (INK_PAPER, CHALK_DARK, COLOUR_POP, RETRO_TV, NIGHT_THRILLER, MEME)}


def get(name):
    if name not in LOOKS:
        raise ValueError(f"unknown stickman look '{name}' (have: {', '.join(LOOKS)})")
    return LOOKS[name]
