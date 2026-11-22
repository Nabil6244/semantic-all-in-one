"""The Food Files look: palette, fonts, sound cues. Our own take on the reference's 'warning file' feel."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWN_FONTS = Path(__file__).resolve().parent / "assets" / "fonts"
APP_FONTS = ROOT / "assets" / "fonts"
HAND_FONTS = (ROOT / "stickman" / "assets" / "fonts", ROOT / "explainer" / "assets" / "fonts")

CREAM = (246, 238, 220)
CREAM_DARK = (232, 221, 196)
MAROON = (42, 18, 20)
MAROON_2 = (62, 26, 28)
NAVY = (22, 28, 48)
RED = (214, 38, 43)
RED_DARK = (150, 20, 26)
YELLOW = (245, 197, 24)
INK = (24, 20, 20)
WHITE = (255, 255, 255)
GREEN = (60, 170, 90)
BLUE = (60, 120, 200)
MANILA = (233, 205, 140)
COLOURS = {"red": RED, "green": GREEN, "yellow": YELLOW, "white": WHITE}

TITLE_FONT = "Anton-Regular.ttf"       # condensed heavy (OFL)
BODY_FONT = "Inter-Bold.ttf"
BODY_SEMI = "Inter-SemiBold.ttf"
HAND_FONT = "Kalam-Bold.ttf"           # handwritten side notes (OFL)
MONO_FONT = "Inter-Regular.ttf"


def font_path(name):
    for d in (OWN_FONTS, APP_FONTS, *HAND_FONTS):
        p = d / name
        if p.is_file():
            return p
    return APP_FONTS / BODY_FONT


# sound cue -> (bundled-sfx file, dB)
SFX = {"whoosh": ("whoosh/whoosh_004.opus", -21.0), "pop": ("ui/ui_005.opus", -21.0), "tick": ("ui/ui_003.opus", -21.0),
       "stamp": ("impact/impact_005.opus", -15.0), "sting": ("transition/transition_01.opus", -16.0),
       "number": ("impact/impact_005.opus", -18.0), "end": ("impact/impact_005.opus", -20.0)}
MUSIC_BED = "lost_frontier.opus"
