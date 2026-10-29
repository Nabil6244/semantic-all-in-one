"""ONE-TIME asset builder for the Explainer "scenes v2" pack (opt-in through DirectorOptions.scenes2). Run by hand, never during a render:

    python3 -B explainer/cartoon/build_scenes_v2.py            # writes explainer/assets/scenes_v2/ (PNG files + manifest.json)
    python3 -B explainer/cartoon/build_scenes_v2.py --check    # rebuilds in memory, compares bytes with the files on disk, writes nothing
    python3 -B explainer/cartoon/build_scenes_v2.py --sheet PATH.jpg   # contact sheet for looking at the art

8 more sets (each day and dusk, flat colour, no outline, same family as the v1 kit) and 15 props / tile pictures. The v1 kit (explainer/assets/cartoon) is NOT touched: its manifest is
part of the cartoon clip cache key. Everything is drawn with Pillow at 2x and reduced with LANCZOS, saved with fixed PNG settings, so the same Pillow gives the same bytes."""

from __future__ import annotations

import hashlib
import io
import json
import math
import sys
from pathlib import Path
from typing import Callable, Dict, Tuple

import PIL
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from explainer.cartoon.build_assets import C, W, H, house, pine, png_bytes     # noqa: E402  (same flat drawing surface as the v1 kit)

OUT = Path(__file__).resolve().parents[1] / "assets" / "scenes_v2"
ASSET_ID = "scenes_v2_v1"
G = 880                                         # the feet line, as in v1
TODS = ("day", "dusk")
SETS = ("border_wall", "mountain_pass", "vault", "station", "barn", "snowy_village", "village", "old_town", "shallows")
PROPS = ("coin_stack", "gold_bars", "vault_door", "folder", "letter", "train", "truck", "tank", "plane", "ship", "barbed_wire", "border_post", "radio", "lantern", "map_table")

SKY = {"day": (186, 222, 244), "dusk": (246, 186, 146)}
SUN = {"day": (255, 224, 120), "dusk": (255, 150, 80)}


def T(col, tod):
    """A day colour as seen at dusk: darker and warmer."""
    if tod == "day":
        return tuple(col)
    return (int(col[0] * 0.86 + 10), int(col[1] * 0.70), int(col[2] * 0.66))


def sh(col, k):
    return tuple(max(0, min(255, int(v * k))) for v in col)


STONE, CONCRETE, DIRT, SNOW, BRICK, PLANK = (176, 176, 182), (196, 192, 184), (196, 164, 120), (244, 247, 250), (168, 92, 72), (150, 106, 70)
GOLD, GOLD2, STEEL, STEEL2, RED, WHITE, WOOD, DWOOD = (232, 182, 50), (250, 214, 100), (128, 138, 150), (96, 106, 118), (196, 70, 64), (248, 248, 244), (170, 124, 80), (120, 84, 56)


def rails(c, x0, x1, y, col=(90, 90, 96)):
    c.rect(x0, y, x1, y + 8, col)
    for x in range(int(x0), int(x1), 34):
        c.rect(x, y + 8, x + 16, y + 20, DWOOD)


def window_grid(c, x, y, cols, rows, dx, dy, w, h, col):
    for i in range(cols):
        for j in range(rows):
            c.rect(x + i * dx, y + j * dy, x + i * dx + w, y + j * dy + h, col)


def peaks(c, pts, base, col, snow, cap=0.28):
    """A mountain range polygon with a snow cap on each peak (pts are (x, y) tops left to right; base is the y of the foot)."""
    outline = [(pts[0][0] - 300, base)]
    for x, y in pts:
        outline.append((x, y))
    outline.append((pts[-1][0] + 300, base))
    c.poly(outline, col)
    for x, y in pts:
        hh = (base - y) * cap
        c.poly([(x, y), (x - hh * 0.55, y + hh), (x - hh * 0.15, y + hh * 0.78), (x + hh * 0.1, y + hh * 1.05), (x + hh * 0.3, y + hh * 0.8), (x + hh * 0.58, y + hh)], snow)


def sky_sun(c, tod, sun=(1560, 260)):
    c.rect(0, 0, W, H, SKY[tod])
    sy = sun[1] + (230 if tod == "dusk" else 0)
    c.ell(sun[0] - 80, sy - 80, sun[0] + 80, sy + 80, SUN[tod])


def cloud(c, x, y, s, tod):
    col = (255, 255, 255) if tod == "day" else (252, 214, 190)
    c.ell(x, y, x + 200 * s, y + 70 * s, col)
    c.ell(x + 40 * s, y - 30 * s, x + 150 * s, y + 50 * s, col)


# ------------------------------------------------------------------ sets
def s_border_wall(c, tod):
    sky_sun(c, tod, (400, 250))
    cloud(c, 1200, 150, 1.2, tod)
    c.poly([(0, 600), (260, 470), (560, 600), (900, 500), (1300, 610), (1640, 490), (1920, 600), (1920, 700), (0, 700)], T((200, 170, 130), tod))
    c.rect(0, 640, W, H, T((214, 184, 140), tod))
    # the wall: a long concrete panel run with a barbed-wire top
    c.rect(0, 520, W, 700, T(CONCRETE, tod))
    c.rect(0, 520, W, 540, T((160, 156, 150), tod))
    for x in range(0, W, 160):
        c.rect(x, 540, x + 6, 700, T((150, 146, 140), tod))
    c.rect(0, 690, W, 706, T((130, 126, 120), tod))
    for x in range(0, W, 60):
        c.rect(x, 470, x + 6, 520, T((90, 90, 96), tod))
    for x in range(0, W, 30):
        c.poly([(x, 482), (x + 15, 470), (x + 30, 482), (x + 15, 494)], T((70, 70, 76), tod))
    c.rect(0, 480, W, 484, T((70, 70, 76), tod))
    # watchtower
    tx = 1480
    c.rect(tx, 420, tx + 12, 700, T(DWOOD, tod))
    c.rect(tx + 108, 420, tx + 120, 700, T(DWOOD, tod))
    c.rect(tx - 24, 300, tx + 144, 420, T((120, 112, 100), tod))
    c.rect(tx - 40, 280, tx + 160, 304, T(RED, tod))
    c.rect(tx, 330, tx + 120, 380, (240, 232, 160) if tod == "day" else (255, 214, 120))
    # road with barrier
    c.rect(0, 760, W, 840, T((140, 140, 146), tod))
    for x in range(40, W, 200):
        c.rect(x, 796, x + 100, 804, (236, 236, 228))
    c.rect(560, 700, 580, 820, T(WHITE, tod))
    c.rect(1180, 700, 1200, 820, T(WHITE, tod))
    c.rect(580, 736, 1180, 756, T(WHITE, tod))
    for k in range(6):
        c.rect(580 + k * 100 + 50, 736, 580 + k * 100 + 100, 756, T(RED, tod))
    c.rect(0, G + 20, W, H, T((196, 162, 118), tod))


def s_mountain_pass(c, tod):
    sky_sun(c, tod, (1500, 230))
    cloud(c, 200, 140, 1.0, tod)
    peaks(c, [(260, 220), (780, 120), (1320, 250), (1760, 170)], 640, T((120, 138, 168), tod), T(SNOW, tod), 0.26)
    peaks(c, [(120, 400), (560, 330), (1080, 420), (1560, 340), (1900, 420)], 680, T((92, 112, 124), tod), T((230, 238, 244), tod), 0.22)
    c.rect(0, 660, W, H, T((98, 140, 96), tod))
    c.poly([(0, 700), (500, 640), (1100, 680), (1920, 620), (1920, 700), (0, 760)], T((86, 124, 88), tod))
    # the road winds up into the gap
    c.poly([(780, 1080), (1140, 1080), (1060, 880), (1010, 760), (1000, 680), (940, 680), (930, 780), (880, 900)], T((150, 146, 140), tod))
    c.poly([(960, 1080), (968, 1080), (1002, 760), (996, 760)], (236, 232, 200))
    for x, y, hh in ((120, 820, 330), (300, 860, 260), (1560, 840, 340), (1760, 870, 270), (1900, 800, 300), (560, 760, 200)):
        pine(c, x, y, hh, T((54, 110, 72), tod))
    for x in range(1040, 1800, 120):
        c.rect(x, 940 + (x - 1040) * 0.0, x + 8, 990, T(WOOD, tod))


def s_vault(c, tod):
    wall = T((214, 206, 190), tod) if tod == "day" else (150, 124, 108)
    c.rect(0, 0, W, H, wall)
    c.rect(0, 0, W, 90, T((176, 164, 148), tod))
    c.rect(0, 780, W, H, T((196, 188, 176), tod))
    for i in range(0, W, 160):
        c.rect(i, 780, i + 80, 832, T((170, 162, 150), tod))
        c.rect(i + 80, 832, i + 160, 884, T((170, 162, 150), tod))
        c.rect(i, 884, i + 80, 936, T((170, 162, 150), tod))
        c.rect(i + 80, 936, i + 160, 990, T((170, 162, 150), tod))
    for x in (60, 1700):
        c.rect(x, 90, x + 160, 780, T((180, 170, 156), tod))
        c.rect(x - 14, 90, x + 174, 130, T((158, 148, 134), tod))
        c.rect(x - 14, 740, x + 174, 790, T((158, 148, 134), tod))
    # big round vault door
    cx, cy, R = 1180, 440, 290
    c.ell(cx - R - 40, cy - R - 40, cx + R + 40, cy + R + 40, T((84, 92, 104), tod))
    c.ell(cx - R, cy - R, cx + R, cy + R, T(STEEL, tod))
    c.ell(cx - R + 40, cy - R + 40, cx + R - 40, cy + R - 40, T((152, 162, 174), tod))
    for k in range(16):
        a = k * math.pi / 8
        c.ell(cx + math.cos(a) * (R - 24) - 9, cy + math.sin(a) * (R - 24) - 9, cx + math.cos(a) * (R - 24) + 9, cy + math.sin(a) * (R - 24) + 9, T((100, 108, 120), tod))
    c.ell(cx - 80, cy - 80, cx + 80, cy + 80, T((90, 98, 110), tod))
    for k in range(3):
        a = k * math.pi * 2 / 3 + 0.5
        c.poly([(cx, cy), (cx + math.cos(a - .12) * 190, cy + math.sin(a - .12) * 190), (cx + math.cos(a + .12) * 190, cy + math.sin(a + .12) * 190)], T((70, 78, 90), tod))
        c.ell(cx + math.cos(a) * 190 - 24, cy + math.sin(a) * 190 - 24, cx + math.cos(a) * 190 + 24, cy + math.sin(a) * 190 + 24, T(GOLD, tod))
    c.ell(cx - 34, cy - 34, cx + 34, cy + 34, T(GOLD, tod))
    # shelves of gold on the left
    for k in range(3):
        y = 250 + k * 150
        c.rect(300, y + 120, 800, y + 136, T(DWOOD, tod))
        for j in range(4):
            for i in range(4 - j):
                bx = 330 + j * 28 + i * 112
                c.rect(bx, y + 120 - 30 * (j + 1), bx + 100, y + 120 - 30 * j, T(GOLD if (i + j) % 2 else GOLD2, tod))
    c.ell(870, 70, 930, 130, (255, 240, 170) if tod == "day" else (255, 214, 120))
    c.rect(898, 20, 902, 70, T((90, 90, 96), tod))


def s_station(c, tod):
    sky_sun(c, tod, (1640, 240))
    for i, (x, w_, hh) in enumerate(((60, 220, 260), (320, 180, 340), (540, 260, 220), (1500, 200, 300), (1730, 240, 240))):
        c.rect(x, 560 - hh, x + w_, 600, T((130 + 10 * i, 140, 160), tod))
        window_grid(c, x + 24, 580 - hh, max(1, int(w_ // 52)), int(hh // 60), 48, 56, 22, 28, (240, 232, 160) if tod == "dusk" else (214, 226, 238))
    # canopy
    c.rect(0, 120, W, 168, T((70, 76, 90), tod))
    c.poly([(0, 168), (W, 168), (W, 196), (0, 196)], T((54, 58, 70), tod))
    for x in range(200, W, 440):
        c.rect(x, 196, x + 26, 800, T((84, 90, 100), tod))
    # tracks and a train
    c.rect(0, 600, W, 780, T((120, 116, 114), tod))
    for x in range(360, 1560, 260):
        c.rect(x, 430, x + 240, 640, T((176, 56, 52) if (x // 260) % 2 else (64, 96, 156), tod))
        c.rect(x, 560, x + 240, 580, T((240, 220, 160), tod))
        for wx in range(x + 24, x + 220, 70):
            c.rect(wx, 460, wx + 46, 540, (240, 232, 170) if tod == "dusk" else (214, 232, 244))
        for wx in (x + 40, x + 170):
            c.ell(wx, 616, wx + 50, 666, T((50, 50, 56), tod))
    rails(c, 0, W, 690)
    rails(c, 0, W, 730)
    # platform
    c.rect(0, 780, W, H, T((206, 202, 196), tod))
    c.rect(0, 780, W, 800, T((236, 200, 60), tod))
    for x in range(0, W, 240):
        c.rect(x, 800, x + 6, H, T((186, 182, 176), tod))
    # clock and sign
    c.rect(850, 210, 1070, 330, T((60, 100, 70), tod))
    c.rect(866, 226, 1054, 244, T(WHITE, tod))
    c.ell(1430, 210, 1550, 330, T(WHITE, tod))
    c.rect(1488, 226, 1492, 270, (50, 50, 56))
    c.rect(1490, 268, 1520, 272, (50, 50, 56))


def s_barn(c, tod):
    c.rect(0, 0, W, H, T(PLANK, tod))
    for x in range(0, W, 96):
        c.rect(x, 0, x + 5, H, T(DWOOD, tod))
    # open doorway on the right showing the field
    c.rect(1180, 150, 1780, 800, T((60, 40, 28), tod))
    c.rect(1200, 170, 1760, 800, SKY[tod])
    c.ell(1600, 260 + (180 if tod == "dusk" else 0), 1690, 350 + (180 if tod == "dusk" else 0), SUN[tod])
    c.poly([(1200, 640), (1450, 560), (1760, 620), (1760, 800), (1200, 800)], T((122, 178, 98), tod))
    c.rect(1500, 600, 1516, 700, T(WOOD, tod))
    # beams
    c.rect(0, 70, W, 130, T(DWOOD, tod))
    c.poly([(0, 130), (560, 130), (0, 360)], T(DWOOD, tod))
    c.rect(1150, 130, 1190, 800, T(DWOOD, tod))
    c.rect(1770, 130, 1810, 800, T(DWOOD, tod))
    # floor of straw
    c.rect(0, 800, W, H, T((206, 170, 100), tod))
    for x in range(0, W, 70):
        c.rect(x, 830 + (x * 7) % 110, x + 46, 836 + (x * 7) % 110, T((234, 200, 124), tod))
    # hay bales
    for (x, y) in ((80, 720), (270, 720), (170, 640)):
        c.rect(x, y, x + 180, y + 80, T((228, 194, 96), tod))
        c.rect(x + 40, y, x + 48, y + 80, T((150, 120, 60), tod))
        c.rect(x + 130, y, x + 138, y + 80, T((150, 120, 60), tod))
    # hanging lantern
    c.rect(698, 130, 702, 250, (60, 50, 44))
    c.rect(670, 250, 730, 330, T((70, 60, 54), tod))
    c.rect(680, 262, 720, 318, (255, 224, 130))
    # tools on the wall
    c.rect(930, 300, 938, 640, T((90, 70, 52), tod))
    c.rect(900, 300, 968, 310, T((90, 70, 52), tod))
    for x in (902, 922, 946, 964):
        c.rect(x, 300, x + 4, 360, T((150, 154, 160), tod))


def s_snowy_village(c, tod):
    c.rect(0, 0, W, H, (214, 228, 240) if tod == "day" else (240, 188, 160))
    c.ell(1500, 130 + (220 if tod == "dusk" else 0), 1620, 250 + (220 if tod == "dusk" else 0), (255, 246, 214) if tod == "day" else SUN[tod])
    peaks(c, [(300, 280), (900, 220), (1500, 300)], 620, T((150, 170, 196), tod), T(SNOW, tod), 0.38)
    c.rect(0, 600, W, H, T(SNOW, tod))
    c.poly([(0, 680), (400, 620), (900, 690), (1500, 630), (1920, 690), (1920, 760), (0, 780)], T((226, 234, 244), tod))
    c.rect(0, 840, W, H, T((232, 238, 246), tod))
    for x, wl, hh, wall in ((120, 260, 170, (196, 120, 90)), (520, 220, 150, (170, 130, 100)), (1180, 280, 190, (190, 110, 84)), (1600, 240, 160, (160, 124, 96))):
        y = 760
        c.rect(x + wl * 0.7, y - hh - 70, x + wl * 0.84, y - hh, T((120, 90, 80), tod))
        c.ell(x + wl * 0.66, y - hh - 120, x + wl * 0.88, y - hh - 76, (236, 236, 240))
        house(c, x, y, wl, hh, T(wall, tod), T((120, 78, 64), tod), win=(255, 224, 130))
        c.poly([(x - wl * 0.08, y - hh), (x + wl * 0.5, y - hh - hh * 0.55), (x + wl * 1.08, y - hh), (x + wl * 1.0, y - hh + 14), (x + wl * 0.5, y - hh - hh * 0.55 + 28), (x + wl * 0.0, y - hh + 14)], T(SNOW, tod))
    for x, y, hh in ((40, 800, 290), (420, 780, 230), (980, 790, 260), (1500, 800, 220), (1860, 790, 300)):
        pine(c, x, y, hh, T((52, 100, 84), tod))
        c.poly([(x, y - hh), (x - hh * 0.18, y - hh * 0.62), (x + hh * 0.18, y - hh * 0.62)], T(SNOW, tod))
    for k in range(60):
        x, y = (k * 223) % W, (k * 131) % 700
        c.ell(x, y, x + 8, y + 8, WHITE)
    c.rect(60, 900, 700, 910, T(DWOOD, tod))


def s_village(c, tod):
    sky_sun(c, tod, (1560, 240))
    cloud(c, 300, 160, 1.1, tod)
    c.poly([(0, 560), (400, 470), (900, 560), (1400, 460), (1920, 560), (1920, 700), (0, 700)], T((130, 180, 120), tod))
    c.rect(0, 640, W, H, T((122, 178, 98), tod))
    c.poly([(700, 1080), (1160, 1080), (1060, 900), (980, 700), (900, 700), (850, 900)], T((206, 180, 130), tod))
    # church
    c.rect(880, 330, 980, 640, T((226, 216, 196), tod))
    c.poly([(870, 330), (930, 200), (990, 330)], T((150, 70, 60), tod))
    c.rect(926, 150, 934, 210, (90, 70, 52))
    c.rect(914, 166, 946, 172, (90, 70, 52))
    c.rect(1000, 520, 1240, 700, T((236, 226, 204), tod))
    c.poly([(990, 520), (1120, 430), (1250, 520)], T((176, 84, 70), tod))
    c.rect(900, 560, 960, 700, T(DWOOD, tod))
    c.rect(900, 380, 960, 440, (60, 60, 70))
    for x, wl, hh, rf in ((80, 240, 150, (190, 90, 70)), (420, 220, 140, (176, 120, 80)), (1380, 260, 160, (190, 90, 70)), (1700, 230, 150, (150, 100, 70))):
        house(c, x, 780, wl, hh, T((240, 230, 206), tod), T(rf, tod))
    for x, y, hh in ((330, 800, 250), (1340, 820, 280), (1860, 840, 260)):
        c.rect(x - 14, y - 120, x + 14, y, T(DWOOD, tod))
        c.ell(x - 100, y - hh, x + 100, y - 70, T((74, 140, 80), tod))
    c.rect(560, 790, 640, 850, T((130, 124, 120), tod))     # well
    c.poly([(550, 790), (600, 740), (650, 790)], T((176, 84, 70), tod))
    for x in range(1000, 1700, 70):
        c.rect(x, 860, x + 9, 920, T(WOOD, tod))
    c.rect(1000, 876, 1700, 886, T(WOOD, tod))


def s_old_town(c, tod):
    sky_sun(c, tod, (260, 220))
    cols = [BRICK, (196, 160, 110), (150, 110, 120), (180, 130, 90), (120, 140, 160), (200, 170, 130)]
    x, k = -30, 0
    while x < W:
        bw, bh = 230 + (k * 53) % 80, 380 + (k * 67) % 220
        c.rect(x, 760 - bh, x + bw, 760, T(cols[k % 6], tod))
        c.rect(x - 8, 760 - bh - 18, x + bw + 8, 760 - bh, T(sh(cols[k % 6], 0.7), tod))
        window_grid(c, x + 24, 760 - bh + 30, int(bw // 70), int(bh // 120), 66, 110, 34, 64, (240, 232, 160) if tod == "dusk" else (206, 226, 240))
        c.rect(x + 20, 690, x + bw - 20, 760, T((150, 120, 90), tod))
        c.rect(x + 14, 676, x + bw - 14, 700, T(RED if k % 2 else (60, 110, 150), tod))
        x += bw + 6
        k += 1
    # clock tower
    c.rect(880, 160, 1010, 700, T((190, 176, 150), tod))
    c.poly([(868, 170), (945, 60), (1022, 170)], T((120, 70, 60), tod))
    c.ell(900, 220, 990, 310, T(WHITE, tod))
    c.rect(943, 232, 947, 270, (50, 50, 56))
    c.rect(945, 266, 972, 270, (50, 50, 56))
    # cobbled street
    c.rect(0, 760, W, H, T((148, 142, 138), tod))
    for r_ in range(8):
        for xx in range(-60 + (r_ % 2) * 40, W, 80):
            c.rect(xx, 790 + r_ * 34, xx + 66, 818 + r_ * 34, T((166, 160, 154), tod))
    c.rect(0, 760, W, 790, T((200, 196, 188), tod))
    for x in (150, 1000, 1720):
        c.rect(x, 560, x + 8, 770, (60, 60, 66))
        c.ell(x - 14, 536, x + 22, 572, (255, 232, 150))


def s_shallows(c, tod):
    """A shore whose water is too shallow to sail: the deep sea far off, a pale shoal band with sandbars breaking the surface, rocks and ripples, a ship run aground and tilted on a
    sandbar, and the dry sand where people would have to land. (The 'shallow water kept the invaders out' picture.)"""
    d = tod == "dusk"
    sky_sun(c, tod, (330, 250))
    deep, mid, pale = ((80, 110, 160), (110, 146, 178), (150, 178, 186)) if d else ((96, 160, 206), (126, 190, 214), (176, 222, 224))
    bar, wet, sand = ((196, 150, 108), (170, 126, 92), (200, 150, 110)) if d else ((232, 208, 160), (206, 180, 134), (226, 200, 150))
    c.rect(0, 520, W, 600, deep)                                   # deep water far off
    c.rect(0, 600, W, 700, mid)                                    # getting shallow
    c.rect(0, 700, W, 780, pale)                                   # the shoal: the bottom shows through
    for k in range(14):                                            # ripples
        x = (k * 167) % W
        y = 540 + (k * 41) % 220
        c.rect(x, y, x + 70, y + 7, tuple(min(255, v + 34) for v in (deep if y < 600 else mid if y < 700 else pale)))
    for x0, x1, y0 in ((40, 360, 722), (520, 760, 740), (840, 1080, 716), (1760, 1920, 730)):      # sandbars just under and above the surface
        c.ell(x0, y0, x1, y0 + 46, bar)
        c.ell(x0 + 14, y0 + 6, x1 - 14, y0 + 30, tuple(min(255, v + 12) for v in bar))
    for x, y in ((120, 700), (610, 716), (950, 696), (1840, 706)):                               # rocks and reeds breaking the surface
        c.ell(x, y, x + 46, y + 26, (118, 118, 126))
        c.ell(x + 8, y + 4, x + 30, y + 14, (150, 150, 158))
    # the sandbar the ship is stuck on, and the ship tilted on it (hull low and slanted, mast leaning, sail slack)
    c.ell(1180, 668, 1800, 760, bar)
    c.ell(1220, 676, 1760, 742, tuple(min(255, v + 12) for v in bar))
    hull = [(1260, 600), (1700, 640), (1650, 724), (1330, 704)]
    c.poly(hull, (110, 70, 52))
    c.poly([(1260, 600), (1700, 640), (1694, 656), (1262, 616)], (84, 52, 40))
    c.poly([(1480, 622), (1494, 628), (1560, 396), (1544, 392)], (90, 60, 44))
    c.poly([(1548, 410), (1690, 560), (1520, 600)], (236, 230, 214))
    c.poly([(1536, 440), (1420, 560), (1500, 604)], (222, 214, 196))
    # the dry beach where the troops stand
    c.rect(0, 780, W, H, wet)
    c.rect(0, 800, W, H, sand)
    for x in range(0, W, 210):
        c.rect(x, 940 + (x // 210) % 3 * 40, x + 60, 948 + (x // 210) % 3 * 40, T((200, 172, 126), tod))
    for k in range(8):
        c.rect((k * 263) % W, 782 + (k % 2) * 4, (k * 263) % W + 120, 794, tuple(min(255, v + 30) for v in pale))     # foam at the edge


SET_FNS: Dict[str, Callable] = {"border_wall": s_border_wall, "mountain_pass": s_mountain_pass, "vault": s_vault, "station": s_station, "barn": s_barn, "snowy_village": s_snowy_village,
                                "village": s_village, "old_town": s_old_town, "shallows": s_shallows}


def draw_set(name: str, tod: str) -> Image.Image:
    c = C(W, H)
    SET_FNS[name](c, tod)
    return c.done().convert("RGB")


# ------------------------------------------------------------------ props (RGBA, drawn with the feet on the bottom edge)
OUTLINE = (60, 52, 48)


def p_coin_stack(c, w, h):
    for (x, n) in ((20, 6), (120, 9), (220, 4), (170, 3)):
        yb = h - 6 - (28 if x in (170,) else 0)
        for i in range(n):
            y = yb - 18 * (i + 1)
            c.ell(x, y, x + 90, y + 28, GOLD2 if i % 2 else GOLD)
            c.rect(x, y + 14, x + 90, y + 24, GOLD)
            c.ell(x, y + 10, x + 90, y + 38, (190, 140, 30))
            c.ell(x, y, x + 90, y + 28, GOLD2)
    c.ell(120, h - 6 - 9 * 18 - 4, 210, h - 6 - 9 * 18 + 24, GOLD2)


def p_gold_bars(c, w, h):
    rows = (4, 3, 2, 1)
    for j, n in enumerate(rows):
        for i in range(n):
            x = 10 + j * 56 + i * 112
            y = h - 8 - 58 * (j + 1)
            c.poly([(x + 14, y), (x + 106, y), (x + 120, y + 52), (x, y + 52)], GOLD)
            c.poly([(x + 22, y + 8), (x + 98, y + 8), (x + 106, y + 22), (x + 14, y + 22)], GOLD2)


def p_vault_door(c, w, h):
    cx, cy, R = w / 2, h / 2, h / 2 - 8
    c.ell(cx - R, cy - R, cx + R, cy + R, STEEL2)
    c.ell(cx - R + 16, cy - R + 16, cx + R - 16, cy + R - 16, (160, 170, 182))
    for k in range(12):
        a = k * math.pi / 6
        c.ell(cx + math.cos(a) * (R - 36) - 7, cy + math.sin(a) * (R - 36) - 7, cx + math.cos(a) * (R - 36) + 7, cy + math.sin(a) * (R - 36) + 7, STEEL2)
    c.ell(cx - R * .5, cy - R * .5, cx + R * .5, cy + R * .5, STEEL)
    for k in range(3):
        a = k * math.pi * 2 / 3 + .5
        c.poly([(cx, cy), (cx + math.cos(a - .14) * R * .45, cy + math.sin(a - .14) * R * .45), (cx + math.cos(a + .14) * R * .45, cy + math.sin(a + .14) * R * .45)], STEEL2)
        c.ell(cx + math.cos(a) * R * .45 - 14, cy + math.sin(a) * R * .45 - 14, cx + math.cos(a) * R * .45 + 14, cy + math.sin(a) * R * .45 + 14, GOLD)
    c.ell(cx - 22, cy - 22, cx + 22, cy + 22, GOLD)


def p_folder(c, w, h):
    c.rect(20, 40, w - 20, h - 12, (214, 168, 80), 10)
    c.rect(20, 24, 150, 56, (214, 168, 80), 8)
    c.rect(20, 66, w - 20, h - 12, (236, 192, 100), 10)
    c.rect(60, 104, w - 60, 140, (250, 244, 228), 4)
    c.rect(60, 160, w - 100, 176, (200, 190, 170))
    c.rect(60, 190, w - 130, 206, (200, 190, 170))
    c.rect(w - 130, h - 90, w - 40, h - 40, RED, 6)


def p_letter(c, w, h):
    c.rect(10, 40, w - 10, h - 10, (250, 244, 226), 6)
    c.poly([(10, 40), (w / 2, h * 0.62), (w - 10, 40)], (232, 222, 196))
    c.poly([(10, h - 10), (w * 0.4, h * 0.5), (w * 0.5, h * 0.58), (w * 0.6, h * 0.5), (w - 10, h - 10)], (240, 230, 206))
    c.ell(w / 2 - 22, h * 0.62 - 22, w / 2 + 22, h * 0.62 + 22, RED)


def p_train(c, w, h):
    c.rect(20, h - 70, w - 20, h - 52, (60, 60, 66))
    c.rect(20, h - 190, 240, h - 70, (60, 80, 90), 12)                      # engine boiler
    c.rect(220, h - 250, 330, h - 70, (60, 80, 90), 8)                      # cab
    c.rect(238, h - 232, 312, h - 180, (210, 232, 244))
    c.rect(36, h - 226, 76, h - 190, (40, 40, 46))                          # chimney
    c.rect(28, h - 236, 84, h - 222, (40, 40, 46))
    c.ell(120, h - 214, 170, h - 190, (70, 100, 112))
    c.poly([(20, h - 70), (20, h - 110), (6, h - 70)], RED)
    for wx, r in ((60, 36), (130, 36), (200, 36), (290, 44)):
        c.ell(wx - r, h - 52 - 2 * r + 20, wx + r, h - 12, (46, 46, 52))
        c.ell(wx - r + 12, h - 52 - 2 * r + 32, wx + r - 12, h - 24, RED)
    for x0, col in ((350, (176, 56, 52)), (570, (64, 96, 156))):
        c.rect(x0, h - 190, x0 + 200, h - 70, col, 8)
        for wx in range(x0 + 20, x0 + 190, 60):
            c.rect(wx, h - 170, wx + 40, h - 120, (240, 232, 170))
        for wx in (x0 + 40, x0 + 160):
            c.ell(wx - 22, h - 56, wx + 22, h - 12, (46, 46, 52))
    c.rect(330, h - 106, 350, h - 98, (60, 60, 66))
    c.rect(550, h - 106, 570, h - 98, (60, 60, 66))


def p_truck(c, w, h):
    c.rect(10, h - 210, 300, h - 60, (196, 150, 84), 8)
    for x in range(40, 290, 50):
        c.rect(x, h - 205, x + 6, h - 66, (150, 110, 60))
    c.rect(320, h - 160, 470, h - 60, (66, 110, 150), 10)
    c.poly([(380, h - 160), (440, h - 160), (470, h - 110), (380, h - 110)], (206, 230, 242))
    c.rect(10, h - 64, 480, h - 48, (60, 60, 66))
    for wx in (90, 230, 410):
        c.ell(wx - 36, h - 84, wx + 36, h - 12, (40, 40, 44))
        c.ell(wx - 16, h - 64, wx + 16, h - 32, (170, 170, 176))
    c.rect(466, h - 90, 484, h - 72, (250, 230, 140))


def p_tank(c, w, h):
    c.rect(30, h - 90, w - 30, h - 30, (84, 98, 70), 28)
    c.rect(30, h - 70, w - 30, h - 14, (60, 68, 54), 26)
    for wx in range(70, w - 50, 50):
        c.ell(wx - 22, h - 62, wx + 22, h - 18, (110, 120, 96))
        c.ell(wx - 9, h - 49, wx + 9, h - 31, (60, 68, 54))
    c.rect(90, h - 150, w - 90, h - 88, (96, 112, 80), 12)
    c.rect(w / 2 - 6, h - 130, w - 6, h - 112, (70, 82, 60))
    c.rect(w - 50, h - 134, w - 6, h - 108, (50, 58, 46))
    c.ell(110, h - 176, 166, h - 140, (80, 94, 66))
    c.rect(120, h - 188, 146, h - 170, (66, 78, 54))
    c.rect(w / 2 - 12, h - 126, w / 2 + 12, h - 108, (60, 68, 54))


def p_plane(c, w, h):
    cy = h / 2
    c.poly([(10, cy - 6), (40, cy - 30), (w - 120, cy - 34), (w - 40, cy - 12), (w - 20, cy + 6), (w - 60, cy + 26), (60, cy + 22)], (204, 208, 214))
    c.poly([(30, cy - 10), (20, cy - 90), (70, cy - 90), (110, cy - 26)], (160, 168, 178))              # tail fin
    c.poly([(40, cy - 4), (120, cy - 10), (150, cy + 2), (60, cy + 10)], (176, 184, 194))               # tailplane
    c.poly([(200, cy + 6), (300, cy + 2), (230, cy + 130), (170, cy + 130)], (140, 148, 160))           # wing
    c.poly([(200, cy - 22), (270, cy - 24), (250, cy - 70), (216, cy - 70)], (176, 184, 194))
    c.ell(w - 210, cy - 36, w - 120, cy - 6, (130, 190, 220))
    c.rect(w - 24, cy - 24, w - 10, cy + 34, (80, 80, 88))
    c.ell(w - 150, cy + 4, w - 130, cy + 18, RED)
    c.ell(90, cy - 6, 112, cy + 2, RED)


def p_ship(c, w, h):
    c.poly([(10, h - 120), (w - 10, h - 120), (w - 70, h - 36), (70, h - 36)], (60, 70, 100))
    c.poly([(40, h - 120), (w - 40, h - 120), (w - 52, h - 104), (52, h - 104)], RED)
    c.rect(130, h - 190, w - 150, h - 120, (240, 236, 224))
    c.rect(200, h - 250, w - 260, h - 190, (240, 236, 224))
    c.rect(w - 330, h - 300, w - 290, h - 250, (60, 60, 70))
    for x in range(150, w - 170, 50):
        c.ell(x, h - 172, x + 24, h - 148, (120, 160, 190))
    c.rect(230, h - 236, 270, h - 210, (120, 160, 190))
    c.rect(330, h - 236, 370, h - 210, (120, 160, 190))
    c.rect(w - 420, h - 322, w - 380, h - 190, (60, 60, 70))
    c.rect(w - 420, h - 336, w - 380, h - 316, RED)


def p_barbed_wire(c, w, h):
    for x in range(14, w - 20, 130):
        c.rect(x, 20, x + 14, h - 4, DWOOD)
    for y in (50, 100, 150):
        c.rect(0, y, w, y + 5, (70, 70, 76))
        for x in range(40, w - 20, 44):
            c.poly([(x - 8, y - 8), (x + 8, y + 12), (x + 4, y + 14), (x - 12, y - 6)], (70, 70, 76))
            c.poly([(x + 8, y - 8), (x - 8, y + 12), (x - 4, y + 14), (x + 12, y - 6)], (70, 70, 76))


def p_border_post(c, w, h):
    c.rect(w / 2 - 22, 40, w / 2 + 22, h - 4, WHITE)
    for k in range(6):
        c.rect(w / 2 - 22, 60 + k * 48, w / 2 + 22, 84 + k * 48, RED) if k % 2 == 0 else None
    c.poly([(w / 2 - 22, 40), (w / 2, 10), (w / 2 + 22, 40)], RED)
    c.rect(w / 2 + 22, 60, w - 6, 130, (60, 100, 150), 6)
    c.rect(w / 2 + 34, 72, w - 18, 118, (236, 236, 228), 4)
    c.rect(w / 2 + 40, 88, w - 24, 98, (60, 100, 150))


def p_radio(c, w, h):
    c.rect(10, 60, w - 10, h - 6, (150, 100, 60), 14)
    c.rect(24, 76, w * 0.62, h - 22, (236, 220, 170), 8)
    for x in range(34, int(w * 0.62) - 6, 14):
        c.rect(x, 86, x + 5, h - 32, (150, 120, 80))
    c.ell(w * 0.68, 84, w * 0.68 + 54, 138, (240, 230, 200))
    c.ell(w * 0.68 + 12, 96, w * 0.68 + 42, 126, (120, 90, 60))
    c.rect(w * 0.68, h - 66, w - 24, h - 34, (240, 230, 200), 6)
    c.rect(w - 56, 10, w - 48, 60, (80, 80, 86))


def p_lantern(c, w, h):
    c.rect(w / 2 - 3, 4, w / 2 + 3, 40, (70, 70, 76))
    c.ell(w / 2 - 14, 22, w / 2 + 14, 50, (70, 70, 76))
    c.poly([(w / 2 - 36, 80), (w / 2, 40), (w / 2 + 36, 80)], (60, 60, 66))
    c.rect(w / 2 - 36, 80, w / 2 + 36, h - 40, (255, 226, 130))
    c.ell(w / 2 - 18, 110, w / 2 + 18, 170, (255, 244, 190))
    for x in (w / 2 - 36, w / 2 + 30):
        c.rect(x, 80, x + 6, h - 40, (60, 60, 66))
    c.rect(w / 2 - 42, h - 42, w / 2 + 42, h - 8, (60, 60, 66), 6)


def p_map_table(c, w, h):
    c.rect(20, 80, w - 20, 118, DWOOD)
    for x in (44, w - 70):
        c.rect(x, 118, x + 26, h - 4, DWOOD)
    c.poly([(60, 88), (w - 60, 88), (w - 30, 40), (90, 40)], (236, 224, 190))
    c.poly([(110, 52), (170, 46), (200, 66), (150, 80), (110, 74)], (122, 178, 98))
    c.poly([(240, 56), (330, 50), (352, 74), (270, 84)], (122, 178, 98))
    c.ell(w - 190, 56, w - 160, 74, RED)
    c.rect(w - 150, 58, w - 100, 64, RED)


PROP_FNS: Dict[str, Tuple[Callable, Tuple[int, int]]] = {
    "coin_stack": (p_coin_stack, (320, 260)), "gold_bars": (p_gold_bars, (480, 270)), "vault_door": (p_vault_door, (360, 360)), "folder": (p_folder, (300, 240)),
    "letter": (p_letter, (300, 210)), "train": (p_train, (800, 300)), "truck": (p_truck, (500, 260)), "tank": (p_tank, (460, 210)), "plane": (p_plane, (560, 270)),
    "ship": (p_ship, (700, 330)), "barbed_wire": (p_barbed_wire, (520, 190)), "border_post": (p_border_post, (240, 340)), "radio": (p_radio, (300, 220)),
    "lantern": (p_lantern, (160, 280)), "map_table": (p_map_table, (420, 280)),
}


def draw_prop(name: str) -> Image.Image:
    fn, (w, h) = PROP_FNS[name]
    c = C(w, h)
    fn(c, w, h)
    return c.done()


def build() -> Dict[str, bytes]:
    files: Dict[str, bytes] = {}
    meta: Dict = {"sets": {}, "props": {}}

    def put(name: str, im: Image.Image, slot: dict, bbox: bool) -> None:
        b = png_bytes(im)
        files[name] = b
        slot.update({"file": name, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), "size": list(im.size)})
        if bbox:
            slot["bbox"] = list(im.getchannel("A").getbbox())

    for s in SETS:
        meta["sets"][s] = {"ground_y": G, "tod": {}}
        for t in TODS:
            slot: dict = {}
            put(f"set_{s}_{t}.png", draw_set(s, t), slot, False)
            meta["sets"][s]["tod"][t] = slot
    for pr in PROPS:
        slot = {}
        put(f"prop_{pr}.png", draw_prop(pr), slot, True)
        meta["props"][pr] = slot
    digest = hashlib.sha256("".join(hashlib.sha256(files[n]).hexdigest() for n in sorted(files)).encode()).hexdigest()
    manifest = {"asset_id": ASSET_ID, "version": 1, "pillow_version": PIL.__version__, "built_by": "explainer/cartoon/build_scenes_v2.py", "layers_digest": digest, **meta}
    files["manifest.json"] = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode()
    return files


def contact_sheet(files: Dict[str, bytes], path: str) -> None:
    """Small JPG: every set (day and dusk) at 1/6 size, then every prop on a grey tile. For looking at the art."""
    tw, th = 320, 180
    n_sets = len(SETS) * 2
    cols = 4
    rows_sets = (n_sets + cols - 1) // cols
    ph = 190
    rows_props = (len(PROPS) + 4) // 5
    sheet = Image.new("RGB", (cols * tw, rows_sets * th + rows_props * ph), (236, 236, 232))
    i = 0
    for s in SETS:
        for t in TODS:
            im = Image.open(io.BytesIO(files[f"set_{s}_{t}.png"])).convert("RGB").resize((tw, th), Image.LANCZOS)
            sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
            i += 1
    y0 = rows_sets * th
    for k, pr in enumerate(PROPS):
        im = Image.open(io.BytesIO(files[f"prop_{pr}.png"])).convert("RGBA")
        s = min(250 / im.width, (ph - 10) / im.height)
        im = im.resize((max(2, int(im.width * s)), max(2, int(im.height * s))), Image.LANCZOS)
        cx, cy = (k % 5) * (cols * tw // 5), y0 + (k // 5) * ph
        cell = (cols * tw // 5)
        sheet.paste((200, 214, 224), (cx, cy, cx + cell, cy + ph))
        sheet.paste(im, (cx + (cell - im.width) // 2, cy + ph - im.height - 4), im)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, "JPEG", quality=82)


def main(argv) -> int:
    files = build()
    if "--sheet" in argv:
        contact_sheet(files, argv[argv.index("--sheet") + 1])
        return 0
    if "--check" in argv:
        bad = [n for n, b in files.items() if not (OUT / n).is_file() or (OUT / n).read_bytes() != b]
        extra = sorted(p.name for p in OUT.glob("*") if p.name not in files) if OUT.exists() else []
        print(json.dumps({"files": len(files), "differ_or_missing": bad, "extra_on_disk": extra}, indent=1))
        return 0 if not bad and not extra else 1
    OUT.mkdir(parents=True, exist_ok=True)
    for n, b in files.items():
        (OUT / n).write_bytes(b)
    print(f"wrote {len(files)} files to {OUT}; manifest sha256 {hashlib.sha256(files['manifest.json']).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
