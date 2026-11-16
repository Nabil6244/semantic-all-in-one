"""Wall looks per style. Every colour the wall draws comes from here, so a style changes the wall by naming its theme.

    get(name) -> dict      unknown names fall back to "slate" (the look approved on the Lisbon TAP test, 2026-11-16)
    THEME_OF_STYLE         style name -> theme name (Aviation is slate; the others are ready for Phase 4)
"""

from __future__ import annotations

from typing import Any, Dict

SLATE: Dict[str, Any] = {
    "board": (24, 28, 34), "grid": (32, 37, 44), "spot": (6, 8, 11),          # wall, grid lines, the dark outside the spotlight
    "card": (238, 234, 226), "shadow": (0, 0, 0, 150),                      # print border and drop shadow
    "pin": (186, 30, 26), "pin_rim": (110, 14, 12),
    "bar": (176, 24, 20), "bar_text": (250, 246, 238),                      # red name bar
    "ink": (244, 240, 232), "ink_shadow": (0, 0, 0, 160), "caption": (206, 200, 190),
    "bad": (236, 72, 56),                                                   # a loss / a fall
    "stamp": (196, 32, 28, 235),
    "note": (250, 220, 90), "under": (250, 210, 60),                        # handwriting, marker underline
    "string": (190, 30, 26), "pen": (236, 60, 44),
    "block": (244, 200, 40), "block_text": (28, 24, 20),                    # yellow date block
    "slam_block": (16, 18, 22),                                             # "here is the strange part" title block
    "grain": 0.06,
}

WAR: Dict[str, Any] = dict(SLATE, board=(14, 16, 19), grid=(22, 25, 29), spot=(3, 4, 5), card=(226, 222, 212),
                           caption=(190, 186, 178), grain=0.08)

PAPER: Dict[str, Any] = dict(SLATE, board=(222, 214, 196), grid=(208, 199, 180), spot=(120, 112, 96), card=(250, 248, 242),
                             shadow=(40, 30, 20, 110), ink=(30, 28, 26), ink_shadow=(0, 0, 0, 40), caption=(80, 74, 66),
                             note=(30, 60, 150), under=(220, 60, 40), block=(30, 28, 26), block_text=(250, 246, 238),
                             slam_block=(30, 28, 26), grain=0.04)

THEMES = {"slate": SLATE, "war": WAR, "paper": PAPER}
THEME_OF_STYLE = {"aviation": "slate", "explainer": "slate", "war": "war", "newsdoc": "paper", "news_doc": "paper"}


def get(name: Any) -> Dict[str, Any]:
    return THEMES.get(str(name or "slate").lower(), SLATE)
