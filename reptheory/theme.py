"""Rep Theory look: near-black canvas, white all-caps type, orange emphasis, red section markers. Sizes are 16:9 only: Final 1920x1080, Preview 1280x720, 24 fps."""
from __future__ import annotations
from pathlib import Path

FPS = 24
SIZES = {"final": (1920, 1080), "preview": (1280, 720)}
BG_TOP, BG_BOT = (17, 17, 19), (6, 6, 7)
WHITE, SOFT_WHITE, GREY, DIM = (247, 247, 245), (205, 205, 202), (128, 128, 128), (42, 42, 45)
ORANGE, ORANGE_DEEP, RED = (255, 122, 26), (214, 92, 8), (222, 38, 38)
HEAD_FONT, BODY_FONT = "Manrope-ExtraBold.ttf", "Inter-Bold.ttf"
# Niche themes: "cat" (Cat Theory) is the same storytelling engine with a white canvas, dark ink type and cat pictures; "" is Rep Theory exactly as it was.
# set_theme() switches at run time (the engine calls it at the start of every render); REPTHEORY_THEME sets the start value.
import os as _os
_BASE = dict(BG_TOP=BG_TOP, BG_BOT=BG_BOT, WHITE=WHITE, SOFT_WHITE=SOFT_WHITE, GREY=GREY, DIM=DIM, ORANGE=ORANGE, ORANGE_DEEP=ORANGE_DEEP, RED=RED, PLATE=(14, 14, 15),
             GREEN=(74, 222, 128), HEAD_FONT=HEAD_FONT, BODY_FONT=BODY_FONT)
# the cat look is a pet video's: warm cream paper, coral accent, rose warnings, mint for "right", a rounded hand-lettered face (bundled Chalkboard SE Bold), soft white cards
_CAT = dict(BG_TOP=(255, 249, 241), BG_BOT=(252, 238, 226), WHITE=(58, 42, 38), SOFT_WHITE=(110, 88, 80), GREY=(160, 136, 124), DIM=(240, 222, 210),
            ORANGE=(247, 118, 72), ORANGE_DEEP=(214, 88, 50), RED=(228, 76, 104), PLATE=(255, 253, 250), GREEN=(38, 168, 120),
            HEAD_FONT="ChalkboardSE.ttc#2", BODY_FONT="ChalkboardSE.ttc#2")      # "WHITE" stays the main type colour: warm brown ink on the light canvas
THEME = ""

def set_theme(name: str = "") -> str:
    """Switches every colour above for this process ("" or "cat"); returns the theme now in force."""
    global THEME
    THEME = "cat" if str(name or "").strip().lower() == "cat" else ""
    globals().update(_CAT if THEME == "cat" else _BASE); return THEME

def P(r: int, g: int, b: int, a=None) -> tuple:
    """A card's dark panel colour: as given on the black canvas, a light paper tone on the cat canvas (so the WHITE type on it always reads)."""
    c = (r, g, b) if THEME != "cat" else tuple(int(255 - v * 0.12) for v in (r, g, b))      # cat: soft white cards on the cream paper
    return c if a is None else c + (a,)

set_theme(_os.environ.get("REPTHEORY_THEME", ""))
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

def font(name: str, px: int):
    from PIL import ImageFont
    name, _, idx = str(name).partition("#")      # "file.ttc#2": a face inside a collection
    try: return ImageFont.truetype(str(FONT_DIR / name), int(px), index=int(idx or 0))
    except OSError: return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", int(px))

def ease_out(t: float) -> float:
    t = min(1.0, max(0.0, t)); return 1 - (1 - t) ** 3
def ease_in_out(t: float) -> float:
    t = min(1.0, max(0.0, t)); return 3 * t * t - 2 * t ** 3
def ease_back(t: float) -> float:      # overshoots a little, then settles: used for pop-in of numbers and symbols
    t = min(1.0, max(0.0, t)); c = 1.70158
    if t <= 0: return 0.0      # exactly 0 before it starts (it was 2e-16, so `if q <= 0` never held and hidden things drew)
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2

MODEL_CREDIT = "3D MODEL · Z-ANATOMY · CC BY-SA 4.0"      # shown under every 3D body panel (the shipped model is a Z-Anatomy derivative)
