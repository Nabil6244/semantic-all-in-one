"""Aviation channel identity (docs/aviation/MASTER_PLAN.md section 3): one fixed palette, type, badge, sticker edge and sound set,
so every film of the channel looks and sounds the same. Every stage element reads its look from here, never from its own constants.

    STAGE_BG, WHITE, YELLOW, NAVY, INK, RED, GREEN   colours (RGBA)
    font(role, size)                                  role: title, heavy, body, badge, hand, serif
    EDGE, SHADOW_*                                    sticker die-cut edge and shadow
    FLOAT_PX, FLOAT_DEG, FLOAT_S                      the slow sticker float
    ENTER_S, EXIT_S, MOVE_S                           motion lengths
    SOUNDS                                            stage event -> sound-set name (mixed in step 12)
    scale()                                           frame size / 1280 (so 1080p uses the same layouts)
"""

from __future__ import annotations

from cinematic_explainer.war import tokens as T

W, H = T.W, T.H

STAGE_BG = (8, 9, 12, 255)          # the black stage (not pure black: keeps shadows readable)
STAGE_LIFT = (22, 24, 30, 255)      # soft centre lift of the stage
WHITE = (250, 250, 250, 255)
YELLOW = (255, 206, 48, 255)        # accent: badges, key words, icons
NAVY = (20, 34, 72, 255)            # year badge box
INK = (18, 18, 22, 255)             # text on white cards / bubbles
GREY = (150, 152, 160, 255)
RED = (226, 64, 58, 255)
GREEN = (72, 190, 120, 255)

EDGE = 10                           # sticker white edge, px at 1280 wide
SHADOW_OFFSET = (6, 9)
SHADOW_BLUR = 9
SHADOW_ALPHA = 150

FLOAT_PX = 4.0                      # slow bob of a resting sticker
FLOAT_DEG = 1.2
FLOAT_S = 5.5

ENTER_S = 0.42
EXIT_S = 0.32
MOVE_S = 0.7

_ROLES = {"title": "heavy", "heavy": "heavy", "body": "bold", "badge": "display", "hand": "serif", "serif": "serif",
          "regular": "regular"}

SOUNDS = {"pop": "pop", "slide": "whoosh_soft", "drop": "thud_soft", "fade": "", "exit": "whoosh_soft",
          "year": "typewriter_tick", "rehook": "low_hit", "write": "pen_scribble"}


def font(role: str, size: int):
    return T.font(_ROLES.get(role, "bold"), int(round(size * scale())))


def scale() -> float:
    return W / 1280.0
