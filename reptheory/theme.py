"""Rep Theory look: near-black canvas, white all-caps type, orange emphasis, red section markers. Sizes are 16:9 only: Final 1920x1080, Preview 1280x720, 24 fps."""
from __future__ import annotations
from pathlib import Path

FPS = 24
SIZES = {"final": (1920, 1080), "preview": (1280, 720)}
BG_TOP, BG_BOT = (17, 17, 19), (6, 6, 7)
WHITE, SOFT_WHITE, GREY, DIM = (247, 247, 245), (205, 205, 202), (128, 128, 128), (42, 42, 45)
ORANGE, ORANGE_DEEP, RED = (255, 122, 26), (214, 92, 8), (222, 38, 38)
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
HEAD_FONT, BODY_FONT = "Manrope-ExtraBold.ttf", "Inter-Bold.ttf"

def font(name: str, px: int):
    from PIL import ImageFont
    try: return ImageFont.truetype(str(FONT_DIR / name), int(px))
    except OSError: return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", int(px))

def ease_out(t: float) -> float:
    t = min(1.0, max(0.0, t)); return 1 - (1 - t) ** 3
def ease_in_out(t: float) -> float:
    t = min(1.0, max(0.0, t)); return 3 * t * t - 2 * t ** 3
def ease_back(t: float) -> float:      # overshoots a little, then settles: used for pop-in of numbers and symbols
    t = min(1.0, max(0.0, t)); c = 1.70158; return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2

MODEL_CREDIT = "3D MODEL · Z-ANATOMY · CC BY-SA 4.0"      # shown under every 3D body panel (the shipped model is a Z-Anatomy derivative)
