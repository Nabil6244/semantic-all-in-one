"""Rep Theory look: near-black canvas, white all-caps type, orange emphasis, red section markers. Sizes are 16:9 only: Final 1920x1080, Preview 1280x720, 24 fps."""
from __future__ import annotations
from pathlib import Path

FPS = 24
SIZES = {"final": (1920, 1080), "preview": (1280, 720)}
BG_TOP, BG_BOT = (17, 17, 19), (6, 6, 7)
WHITE, SOFT_WHITE, GREY, DIM = (247, 247, 245), (205, 205, 202), (128, 128, 128), (42, 42, 45)
ORANGE, ORANGE_DEEP, RED = (255, 122, 26), (214, 92, 8), (222, 38, 38)
HEAD_FONT, BODY_FONT = "Manrope-ExtraBold.ttf", "Inter-Bold.ttf"
# Niche themes: "cat" (Cat Theory) and "jung" (Carl Jung Theory) are the same storytelling engine with a white canvas, dark ink type and cat pictures; "" is Rep Theory exactly as it was.
# set_theme() switches at run time (the engine calls it at the start of every render); REPTHEORY_THEME sets the start value.
import os as _os
_BASE = dict(BG_TOP=BG_TOP, BG_BOT=BG_BOT, WHITE=WHITE, SOFT_WHITE=SOFT_WHITE, GREY=GREY, DIM=DIM, ORANGE=ORANGE, ORANGE_DEEP=ORANGE_DEEP, RED=RED, PLATE=(14, 14, 15),
             GREEN=(74, 222, 128), HEAD_FONT=HEAD_FONT, BODY_FONT=BODY_FONT)
# the cat look is a pet video's: warm cream paper, coral accent, rose warnings, mint for "right", a rounded hand-lettered face (bundled Chalkboard SE Bold), soft white cards
_CAT = dict(BG_TOP=(255, 249, 241), BG_BOT=(252, 238, 226), WHITE=(58, 42, 38), SOFT_WHITE=(110, 88, 80), GREY=(160, 136, 124), DIM=(240, 222, 210),
            ORANGE=(247, 118, 72), ORANGE_DEEP=(214, 88, 50), RED=(228, 76, 104), PLATE=(255, 253, 250), GREEN=(38, 168, 120),
            HEAD_FONT="ChalkboardSE.ttc#2", BODY_FONT="ChalkboardSE.ttc#2")      # "WHITE" stays the main type colour: warm brown ink on the light canvas
# the Jung look is an old master's: dark umber canvas, ivory serif type, gold accent, deep red for the shadow / warnings, sage for "right"
# (Georgia Bold: a system font on macOS and Windows, see font() below)
_JUNG = dict(BG_TOP=(34, 26, 20), BG_BOT=(12, 9, 7), WHITE=(242, 232, 212), SOFT_WHITE=(204, 190, 166), GREY=(150, 134, 112), DIM=(66, 54, 44),
             ORANGE=(214, 170, 88), ORANGE_DEEP=(178, 134, 60), RED=(184, 48, 42), PLATE=(26, 20, 16), GREEN=(132, 176, 120),
             HEAD_FONT="sys:Georgia Bold", BODY_FONT="sys:Georgia Bold")
# the elder look is a calm clinic's: soft off-white canvas, deep navy type, teal accent, coral for warnings, sage for "do this"; large plain type an older viewer reads at a glance
_ELDER = dict(BG_TOP=(250, 251, 249), BG_BOT=(236, 242, 241), WHITE=(28, 44, 70), SOFT_WHITE=(78, 96, 120), GREY=(130, 144, 158), DIM=(214, 226, 228),
              ORANGE=(22, 150, 150), ORANGE_DEEP=(12, 112, 116), RED=(226, 98, 82), PLATE=(255, 255, 255), GREEN=(92, 158, 104),
              HEAD_FONT="PlusJakartaSans-ExtraBold.ttf", BODY_FONT="PlusJakartaSans-Bold.ttf")
# the survival look is a frontier field notebook's: off-white paper, dark ink type, rust red accent, a hand-lettered marker face for headlines
_SURVIVAL = dict(BG_TOP=(250, 248, 242), BG_BOT=(240, 236, 226), WHITE=(34, 32, 30), SOFT_WHITE=(92, 86, 78), GREY=(150, 142, 130), DIM=(226, 220, 206),
                 ORANGE=(178, 64, 38), ORANGE_DEEP=(140, 46, 26), RED=(196, 52, 40), PLATE=(255, 254, 250), GREEN=(86, 128, 74),
                 HEAD_FONT="sys:Marker Felt", BODY_FONT="PlusJakartaSans-Bold.ttf")
THEMES = {"": _BASE, "cat": _CAT, "jung": _JUNG, "elder": _ELDER, "survival": _SURVIVAL}
NO_GYM = ("cat", "jung", "elder", "survival")
LIGHT = ("cat", "elder", "survival")      # light canvases: pictures drawn on white paper, multiplied onto the canvas; dark ink type
HAND_FONT = "sys:Marker Felt"      # Elder Health Theory's handwriting board (a marker on a whiteboard)      # niches with no 3D body and no gym trainee art: every picture is the niche's own (Flow)
THEME = ""

def set_theme(name: str = "") -> str:
    """Switches every colour and font above for this process ("", "cat" or "jung"; anything else is ""); returns the theme now in force."""
    global THEME
    THEME = str(name or "").strip().lower(); THEME = THEME if THEME in THEMES else ""
    globals().update(THEMES[THEME]); return THEME

NICHE_KICKERS = {"CUE": "", "TEST": "TRY THIS", "ROUTINE": "PRACTICE", "PROGRESSION": "", "LIMIT": ""}      # Rep Theory's gym labels, as a cat or Jung video says them ("" = no label)

def kicker(k: str) -> str:
    """The small label over a headline in this theme: Rep Theory's own words, or the niche's (no "CUE" / "TEST" in a cat or Jung video)."""
    k = str(k or ""); return NICHE_KICKERS.get(k.upper(), k) if THEME in NO_GYM else k

def P(r: int, g: int, b: int, a=None) -> tuple:
    """A card's dark panel colour: as given on the black canvas, a light paper tone on the cat canvas, a warm umber on the Jung canvas (the WHITE type on it always reads)."""
    c = tuple(int(255 - v * 0.12) for v in (r, g, b)) if THEME in LIGHT else tuple(min(255, int(v * 1.15) + d) for v, d in zip((r, g, b), (16, 10, 4))) if THEME == "jung" else (r, g, b)
    return c if a is None else c + (a,)

set_theme(_os.environ.get("REPTHEORY_THEME", ""))
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

def font(name: str, px: int):
    from PIL import ImageFont
    name, _, idx = str(name).partition("#")      # "file.ttc#2": a face inside a collection
    if name.startswith("sys:"):      # a system font (not bundled): the macOS and Windows file names, else the bundled heading face
        for cand in SYSTEM_FONTS.get(name[4:], ()):
            try: return ImageFont.truetype(cand, int(px))
            except OSError: continue
        name, idx = "Manrope-ExtraBold.ttf", ""
    try: return ImageFont.truetype(str(FONT_DIR / name), int(px), index=int(idx or 0))
    except OSError: return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", int(px))

SYSTEM_FONTS = {"Georgia Bold": ("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", "C:/Windows/Fonts/georgiab.ttf", "/Library/Fonts/Georgia Bold.ttf"),
                "Georgia Italic": ("/System/Library/Fonts/Supplemental/Georgia Italic.ttf", "C:/Windows/Fonts/georgiai.ttf", "/Library/Fonts/Georgia Italic.ttf"),
                "Marker Felt": ("/System/Library/Fonts/MarkerFelt.ttc", "/System/Library/Fonts/Noteworthy.ttc", "C:/Windows/Fonts/segoeprb.ttf", "C:/Windows/Fonts/Inkfree.ttf",
                                "/System/Library/Fonts/Supplemental/ChalkboardSE.ttc")}

def ease_out(t: float) -> float:
    t = min(1.0, max(0.0, t)); return 1 - (1 - t) ** 3
def ease_in_out(t: float) -> float:
    t = min(1.0, max(0.0, t)); return 3 * t * t - 2 * t ** 3
def ease_back(t: float) -> float:      # overshoots a little, then settles: used for pop-in of numbers and symbols
    t = min(1.0, max(0.0, t)); c = 1.70158
    if t <= 0: return 0.0      # exactly 0 before it starts (it was 2e-16, so `if q <= 0` never held and hidden things drew)
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2

MODEL_CREDIT = "3D MODEL · Z-ANATOMY · CC BY-SA 4.0"      # shown under every 3D body panel (the shipped model is a Z-Anatomy derivative)
