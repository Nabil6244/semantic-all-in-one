"""Flat vector icons drawn in code (our own art): food, body, science, legal, places, people.

icon(name, px) -> RGBA square. Names are loose: 'refrigerator' finds 'fridge', 'kids' finds 'kid'. An unknown name gives
None; the director then asks Flow once for a flat sticker of it (cached for every video) and the card uses that.
Style: thick dark outline, flat fills, one highlight. Drawn at 4x and scaled down for clean edges.
"""
import math
import re

from PIL import Image, ImageDraw

from . import look as L

INKC = (34, 28, 30, 255)
_CACHE = {}


def _c(rgb, a=255):
    return tuple(rgb[:3]) + (a,)


class Pen:
    def __init__(self, S):
        self.S = S
        self.im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)
        self.w = max(2, S // 34)

    def p(self, *xy):
        return [v * self.S for v in xy]

    def rect(self, x0, y0, x1, y1, fill, r=0.0, outline=True):
        box = self.p(x0, y0, x1, y1)
        self.d.rounded_rectangle(box, radius=r * self.S, fill=_c(fill), outline=INKC if outline else None,
                                 width=self.w if outline else 0)

    def ell(self, x0, y0, x1, y1, fill, outline=True):
        self.d.ellipse(self.p(x0, y0, x1, y1), fill=_c(fill) if fill else None, outline=INKC if outline else None,
                       width=self.w if outline else 0)

    def poly(self, pts, fill, outline=True):
        q = [(x * self.S, y * self.S) for x, y in pts]
        self.d.polygon(q, fill=_c(fill) if fill else None)
        if outline:
            self.d.line(q + [q[0]], fill=INKC, width=self.w, joint="curve")

    def line(self, pts, w=1.0, col=None):
        self.d.line([(x * self.S, y * self.S) for x, y in pts], fill=_c(col) if col else INKC, width=max(1, int(self.w * w)),
                    joint="curve")

    def arc(self, x0, y0, x1, y1, a0, a1, w=1.0, col=None):
        self.d.arc(self.p(x0, y0, x1, y1), a0, a1, fill=_c(col) if col else INKC, width=max(1, int(self.w * w)))


# ------------------------------------------------------------------ the icons
def _fridge(P):
    P.rect(0.28, 0.08, 0.72, 0.92, (236, 242, 248), r=0.06)
    P.line([(0.28, 0.40), (0.72, 0.40)])
    P.rect(0.62, 0.16, 0.65, 0.32, (160, 170, 180), r=0.01, outline=False)
    P.rect(0.62, 0.48, 0.65, 0.66, (160, 170, 180), r=0.01, outline=False)
    for a in range(0, 180, 60):   # a snowflake
        r = math.radians(a)
        P.line([(0.46 - 0.07 * math.cos(r), 0.64 - 0.07 * math.sin(r)), (0.46 + 0.07 * math.cos(r), 0.64 + 0.07 * math.sin(r))],
               0.7, L.BLUE)


def _sun(P):
    for k in range(12):
        a = math.radians(k * 30)
        P.line([(0.5 + 0.30 * math.cos(a), 0.5 + 0.30 * math.sin(a)), (0.5 + 0.44 * math.cos(a), 0.5 + 0.44 * math.sin(a))],
               1.4, (245, 160, 30))
    P.ell(0.24, 0.24, 0.76, 0.76, (250, 190, 40))
    P.ell(0.32, 0.30, 0.46, 0.42, (255, 225, 120), outline=False)


def _fire(P):
    P.poly([(0.5, 0.06), (0.74, 0.40), (0.80, 0.66), (0.66, 0.90), (0.34, 0.90), (0.20, 0.66), (0.28, 0.44), (0.40, 0.52)],
           (240, 90, 30))
    P.poly([(0.5, 0.42), (0.64, 0.64), (0.60, 0.86), (0.40, 0.86), (0.36, 0.66)], (252, 200, 50), outline=False)


def _candy(P):
    P.poly([(0.08, 0.36), (0.30, 0.46), (0.30, 0.54), (0.08, 0.64)], (240, 90, 120))
    P.poly([(0.92, 0.36), (0.70, 0.46), (0.70, 0.54), (0.92, 0.64)], (240, 90, 120))
    P.ell(0.26, 0.30, 0.74, 0.70, (250, 120, 150))
    P.arc(0.34, 0.36, 0.66, 0.64, 200, 330, 1.0, (255, 220, 230))


def _lollipop(P):
    P.rect(0.47, 0.50, 0.53, 0.94, (250, 250, 250), r=0.02)
    P.ell(0.22, 0.06, 0.78, 0.62, (240, 80, 110))
    for k, col in enumerate(((255, 255, 255), (250, 200, 60))):
        P.arc(0.30 + k * 0.08, 0.14 + k * 0.08, 0.70 - k * 0.08, 0.54 - k * 0.08, 0, 300, 1.2, col)


def _ball(P, rings=((240, 70, 70), (250, 200, 50), (80, 180, 90), (70, 130, 220), (180, 90, 200))):
    P.ell(0.12, 0.12, 0.88, 0.88, rings[0])
    for k, col in enumerate(rings[1:], 1):
        m = 0.12 + k * 0.07
        P.ell(m, m, 1 - m, 1 - m, col, outline=False)
    P.ell(0.24, 0.22, 0.40, 0.36, (255, 255, 255), outline=False)


def _jawbreaker(P):
    _ball(P)


def _bowling(P):
    P.ell(0.12, 0.12, 0.88, 0.88, (36, 52, 120))
    for x, y in ((0.42, 0.32), (0.56, 0.30), (0.50, 0.44)):
        P.ell(x - 0.04, y - 0.04, x + 0.04, y + 0.04, (12, 16, 40), outline=False)
    P.ell(0.24, 0.50, 0.34, 0.62, (90, 110, 190), outline=False)


def _bottle(P, col=(80, 170, 220), label=(255, 255, 255)):
    P.rect(0.42, 0.06, 0.58, 0.16, (60, 60, 60), r=0.02)
    P.poly([(0.42, 0.16), (0.58, 0.16), (0.58, 0.28), (0.70, 0.40), (0.70, 0.90), (0.30, 0.90), (0.30, 0.40), (0.42, 0.28)], col)
    P.rect(0.30, 0.52, 0.70, 0.74, label, r=0.0)


def _can(P):
    P.rect(0.30, 0.12, 0.70, 0.90, (220, 40, 50), r=0.06)
    P.ell(0.30, 0.08, 0.70, 0.18, (200, 205, 210))
    P.rect(0.30, 0.40, 0.70, 0.56, (250, 250, 250), r=0.0)
    P.line([(0.38, 0.20), (0.38, 0.84)], 0.7, (255, 120, 120))


def _cup(P):
    P.poly([(0.26, 0.24), (0.74, 0.24), (0.66, 0.92), (0.34, 0.92)], (250, 250, 250))
    P.rect(0.22, 0.16, 0.78, 0.26, (220, 40, 50), r=0.02)
    P.line([(0.56, 0.16), (0.64, 0.04)], 1.2, (240, 200, 40))
    P.rect(0.30, 0.48, 0.70, 0.64, (220, 40, 50), r=0.0, outline=False)


def _burger(P):
    P.poly([(0.14, 0.46), (0.20, 0.28), (0.40, 0.16), (0.60, 0.16), (0.80, 0.28), (0.86, 0.46)], (230, 160, 70))
    P.rect(0.12, 0.46, 0.88, 0.54, (100, 190, 70), r=0.03)
    P.rect(0.14, 0.54, 0.86, 0.66, (120, 60, 40), r=0.04)
    P.rect(0.12, 0.66, 0.88, 0.72, (250, 200, 50), r=0.02)
    P.rect(0.16, 0.72, 0.84, 0.86, (230, 160, 70), r=0.05)
    for x, y in ((0.38, 0.26), (0.52, 0.22), (0.64, 0.30)):
        P.ell(x - 0.015, y - 0.01, x + 0.015, y + 0.01, (255, 240, 200), outline=False)


def _fries(P):
    for k in range(6):
        x = 0.30 + k * 0.08
        P.rect(x, 0.12 + (k % 3) * 0.05, x + 0.06, 0.6, (250, 210, 70), r=0.01)
    P.poly([(0.22, 0.44), (0.78, 0.44), (0.70, 0.92), (0.30, 0.92)], (220, 40, 50))


def _cereal(P):
    P.rect(0.24, 0.08, 0.76, 0.92, (250, 200, 40), r=0.02)
    P.rect(0.30, 0.16, 0.70, 0.30, (220, 40, 50), r=0.02)
    P.ell(0.34, 0.42, 0.66, 0.74, (255, 255, 255))
    for x, y in ((0.44, 0.52), (0.55, 0.58), (0.47, 0.64)):
        P.ell(x - 0.035, y - 0.035, x + 0.035, y + 0.035, (230, 140, 60))


def _milk(P):
    P.poly([(0.30, 0.30), (0.50, 0.12), (0.70, 0.30), (0.70, 0.90), (0.30, 0.90)], (250, 250, 250))
    P.line([(0.30, 0.30), (0.70, 0.30)])
    P.rect(0.30, 0.46, 0.70, 0.66, (70, 130, 220), r=0.0)


def _turkey(P):
    P.ell(0.14, 0.30, 0.78, 0.84, (240, 228, 214))
    P.ell(0.66, 0.22, 0.90, 0.46, (240, 228, 214))
    P.ell(0.70, 0.16, 0.80, 0.26, (255, 255, 255))
    P.arc(0.26, 0.40, 0.62, 0.76, 200, 320, 0.8, (200, 190, 175))


def _egg(P):
    P.ell(0.26, 0.10, 0.74, 0.90, (250, 246, 236))
    P.ell(0.34, 0.22, 0.46, 0.40, (255, 255, 255), outline=False)


def _apple(P):
    P.ell(0.16, 0.24, 0.84, 0.90, (220, 50, 50))
    P.line([(0.5, 0.26), (0.54, 0.08)], 1.2, (110, 70, 40))
    P.poly([(0.54, 0.16), (0.74, 0.08), (0.66, 0.22)], (90, 180, 70))


def _pill(P):
    P.d.rounded_rectangle(P.p(0.12, 0.36, 0.88, 0.64), radius=0.14 * P.S, fill=_c((250, 250, 250)), outline=INKC, width=P.w)
    P.d.rounded_rectangle(P.p(0.12, 0.36, 0.50, 0.64), radius=0.14 * P.S, fill=_c((220, 60, 70)), outline=INKC, width=P.w)


def _heart(P):
    P.poly([(0.5, 0.88), (0.12, 0.48), (0.12, 0.28), (0.24, 0.14), (0.40, 0.14), (0.5, 0.26), (0.60, 0.14), (0.76, 0.14),
            (0.88, 0.28), (0.88, 0.48)], (225, 45, 60))
    P.line([(0.22, 0.48), (0.38, 0.48), (0.44, 0.36), (0.52, 0.62), (0.58, 0.48), (0.78, 0.48)], 1.0, (255, 255, 255))


def _kidney(P):
    for x0 in (0.08, 0.52):
        P.ell(x0, 0.16, x0 + 0.40, 0.84, (190, 80, 90))
        cx = x0 + (0.34 if x0 < 0.5 else 0.06)
        P.ell(cx - 0.06, 0.40, cx + 0.06, 0.60, (246, 238, 220), outline=False)


def _tooth(P):
    P.poly([(0.22, 0.20), (0.36, 0.10), (0.50, 0.16), (0.64, 0.10), (0.78, 0.20), (0.76, 0.50), (0.68, 0.90), (0.58, 0.90),
            (0.52, 0.62), (0.48, 0.62), (0.42, 0.90), (0.32, 0.90), (0.24, 0.50)], (252, 252, 248))


def _brain(P):
    P.ell(0.12, 0.20, 0.62, 0.80, (240, 160, 180))
    P.ell(0.38, 0.20, 0.88, 0.80, (240, 160, 180))
    P.line([(0.5, 0.24), (0.5, 0.76)], 0.8)
    for y in (0.36, 0.56):
        P.arc(0.20, y - 0.06, 0.42, y + 0.06, 180, 360, 0.7)
        P.arc(0.58, y - 0.06, 0.80, y + 0.06, 180, 360, 0.7)


def _skull(P):
    P.ell(0.18, 0.08, 0.82, 0.70, (248, 246, 240))
    P.rect(0.32, 0.56, 0.68, 0.84, (248, 246, 240), r=0.05)
    P.ell(0.28, 0.32, 0.46, 0.50, (34, 28, 30))
    P.ell(0.54, 0.32, 0.72, 0.50, (34, 28, 30))
    for x in (0.42, 0.50, 0.58):
        P.line([(x, 0.70), (x, 0.84)], 0.8)


def _warning(P):
    P.poly([(0.5, 0.08), (0.92, 0.86), (0.08, 0.86)], (245, 197, 24))
    P.rect(0.465, 0.32, 0.535, 0.62, (34, 28, 30), r=0.02, outline=False)
    P.ell(0.46, 0.68, 0.54, 0.76, (34, 28, 30), outline=False)


def _factory(P):
    P.rect(0.66, 0.14, 0.78, 0.50, (150, 150, 160))
    P.poly([(0.10, 0.88), (0.10, 0.46), (0.32, 0.34), (0.32, 0.46), (0.54, 0.34), (0.54, 0.46), (0.90, 0.46), (0.90, 0.88)],
           (170, 170, 180))
    for x in (0.18, 0.40, 0.62, 0.78):
        P.rect(x, 0.60, x + 0.08, 0.72, (250, 210, 70), r=0.0)
    for k, (x, y) in enumerate(((0.72, 0.08), (0.80, 0.02))):
        P.ell(x - 0.05, y - 0.04, x + 0.05, y + 0.04, (200, 200, 205), outline=False)


def _truck(P):
    P.rect(0.06, 0.26, 0.62, 0.72, (250, 250, 250), r=0.02)
    P.poly([(0.62, 0.40), (0.82, 0.40), (0.94, 0.56), (0.94, 0.72), (0.62, 0.72)], (220, 40, 50))
    P.rect(0.70, 0.44, 0.82, 0.54, (180, 220, 250), r=0.0)
    for x in (0.22, 0.78):
        P.ell(x - 0.08, 0.66, x + 0.08, 0.82, (50, 50, 55))


def _store(P):
    P.rect(0.12, 0.34, 0.88, 0.90, (250, 246, 236))
    for k in range(6):
        P.rect(0.10 + k * 0.1333, 0.20, 0.2333 + k * 0.1333, 0.36, (220, 40, 50) if k % 2 == 0 else (255, 255, 255), r=0.0)
    P.rect(0.42, 0.56, 0.58, 0.90, (120, 170, 210))
    P.rect(0.18, 0.48, 0.36, 0.66, (180, 220, 250))
    P.rect(0.64, 0.48, 0.82, 0.66, (180, 220, 250))


def _house(P):
    P.poly([(0.10, 0.48), (0.5, 0.12), (0.90, 0.48)], (220, 70, 60))
    P.rect(0.18, 0.46, 0.82, 0.90, (250, 230, 190))
    P.rect(0.44, 0.62, 0.58, 0.90, (130, 80, 50))
    P.rect(0.24, 0.56, 0.38, 0.70, (180, 220, 250))


def _court(P):
    P.poly([(0.08, 0.34), (0.5, 0.10), (0.92, 0.34)], (220, 214, 200))
    P.rect(0.10, 0.34, 0.90, 0.42, (220, 214, 200))
    for x in (0.18, 0.36, 0.56, 0.74):
        P.rect(x, 0.42, x + 0.08, 0.80, (240, 236, 226))
    P.rect(0.06, 0.80, 0.94, 0.90, (200, 194, 180))


def _gavel(P):
    P.line([(0.30, 0.70), (0.66, 0.34)], 2.6, (140, 90, 50))
    P.d.polygon([(0.46 * P.S, 0.18 * P.S), (0.62 * P.S, 0.02 * P.S), (0.90 * P.S, 0.30 * P.S), (0.74 * P.S, 0.46 * P.S)],
                fill=_c((160, 100, 55)), outline=INKC, width=P.w)
    P.rect(0.12, 0.82, 0.56, 0.92, (140, 90, 50), r=0.02)


def _money(P):
    P.rect(0.08, 0.26, 0.92, 0.74, (120, 190, 110), r=0.04)
    P.ell(0.38, 0.32, 0.62, 0.68, (160, 215, 150))
    P.d.text((0.5 * P.S, 0.5 * P.S), "$", fill=INKC, anchor="mm",
             font=_font(int(P.S * 0.26)))


def _person(P, shirt=(220, 60, 60), hair=(60, 40, 30), skin=(240, 200, 160), kid=False, coat=False):
    h = 0.20 if kid else 0.16
    top = 0.22 if kid else 0.10
    P.rect(0.30, top + h * 2 - 0.02, 0.70, 0.88, (250, 250, 250) if coat else shirt, r=0.10)
    if coat:
        P.line([(0.5, top + h * 2), (0.5, 0.88)], 0.8)
    P.ell(0.5 - h, top, 0.5 + h, top + h * 2, skin)
    P.d.chord(P.p(0.5 - h, top - 0.01, 0.5 + h, top + h * 1.4), 180, 360, fill=_c(hair), outline=INKC, width=P.w)
    P.ell(0.44, top + h, 0.47, top + h + 0.03, (34, 28, 30), outline=False)
    P.ell(0.53, top + h, 0.56, top + h + 0.03, (34, 28, 30), outline=False)
    if coat:
        P.line([(0.40, top + h * 2 + 0.06), (0.36, 0.50), (0.46, 0.56)], 0.8, (60, 60, 70))


def _kid(P):
    _person(P, shirt=(70, 130, 220), kid=True)


def _man(P):
    _person(P, shirt=(70, 120, 90))


def _woman(P):
    _person(P, shirt=(200, 80, 150), hair=(120, 60, 30))


def _doctor(P):
    _person(P, coat=True, hair=(90, 70, 50))


def _badge(P):
    pts = []
    for k in range(16):
        a = math.radians(k * 22.5 - 90)
        r = 0.42 if k % 2 == 0 else 0.30
        pts.append((0.5 + r * math.cos(a), 0.5 + r * math.sin(a)))
    P.poly(pts, (245, 197, 24))
    P.ell(0.36, 0.36, 0.64, 0.64, (230, 170, 20))


def _flask(P):
    P.poly([(0.40, 0.08), (0.60, 0.08), (0.60, 0.40), (0.84, 0.88), (0.16, 0.88), (0.40, 0.40)], (236, 242, 248))
    P.poly([(0.30, 0.62), (0.70, 0.62), (0.84, 0.88), (0.16, 0.88)], (120, 210, 120), outline=False)
    P.line([(0.16, 0.88), (0.84, 0.88)])
    for x, y in ((0.44, 0.74), (0.56, 0.80)):
        P.ell(x - 0.025, y - 0.025, x + 0.025, y + 0.025, (255, 255, 255), outline=False)


def _microscope(P):
    P.rect(0.20, 0.82, 0.80, 0.90, (90, 90, 100), r=0.02)
    P.line([(0.66, 0.82), (0.66, 0.46), (0.52, 0.36)], 2.0, (90, 90, 100))
    P.d.polygon([(0.34 * P.S, 0.12 * P.S), (0.46 * P.S, 0.06 * P.S), (0.62 * P.S, 0.50 * P.S), (0.50 * P.S, 0.56 * P.S)],
                fill=_c((236, 242, 248)), outline=INKC, width=P.w)
    P.rect(0.30, 0.64, 0.62, 0.70, (90, 90, 100), r=0.01)


def _clock(P):
    P.ell(0.12, 0.12, 0.88, 0.88, (250, 250, 250))
    P.line([(0.5, 0.5), (0.5, 0.24)], 1.3)
    P.line([(0.5, 0.5), (0.68, 0.58)], 1.3)
    P.ell(0.47, 0.47, 0.53, 0.53, (34, 28, 30), outline=False)


def _calendar(P):
    P.rect(0.14, 0.18, 0.86, 0.88, (250, 250, 250), r=0.04)
    P.rect(0.14, 0.18, 0.86, 0.36, (220, 40, 50), r=0.04)
    for x in (0.30, 0.70):
        P.rect(x - 0.02, 0.10, x + 0.02, 0.26, (90, 90, 100), r=0.01)
    for k in range(9):
        x, y = 0.26 + (k % 3) * 0.2, 0.46 + (k // 3) * 0.13
        P.rect(x - 0.04, y - 0.03, x + 0.04, y + 0.03, (210, 210, 215), r=0.01, outline=False)


def _phone(P):
    P.rect(0.30, 0.06, 0.70, 0.94, (40, 40, 46), r=0.07)
    P.rect(0.34, 0.14, 0.66, 0.82, (150, 200, 240), r=0.02, outline=False)
    P.ell(0.47, 0.85, 0.53, 0.91, (120, 120, 130), outline=False)


def _letter(P):
    P.rect(0.10, 0.24, 0.90, 0.76, (250, 250, 250), r=0.02)
    P.line([(0.10, 0.24), (0.5, 0.54), (0.90, 0.24)])
    P.ell(0.62, 0.56, 0.78, 0.72, (220, 40, 50))


def _box(P):
    P.poly([(0.10, 0.34), (0.5, 0.20), (0.90, 0.34), (0.5, 0.48)], (220, 175, 110))
    P.poly([(0.10, 0.34), (0.5, 0.48), (0.5, 0.90), (0.10, 0.76)], (200, 150, 90))
    P.poly([(0.90, 0.34), (0.5, 0.48), (0.5, 0.90), (0.90, 0.76)], (180, 130, 75))


def _microwave(P):
    P.rect(0.06, 0.20, 0.94, 0.80, (230, 232, 236), r=0.04)
    P.rect(0.12, 0.28, 0.68, 0.72, (60, 70, 80), r=0.02)
    P.ell(0.30, 0.42, 0.50, 0.60, (250, 200, 60), outline=False)
    for y in (0.34, 0.48, 0.62):
        P.ell(0.76, y - 0.03, 0.86, y + 0.05, (150, 150, 160))


def _jar(P):
    P.rect(0.30, 0.08, 0.70, 0.20, (220, 40, 50), r=0.02)
    P.rect(0.22, 0.20, 0.78, 0.92, (236, 242, 248), r=0.08)
    for k, col in enumerate(((240, 80, 110), (250, 200, 60), (80, 180, 90), (70, 130, 220))):
        x = 0.32 + (k % 2) * 0.2
        y = 0.54 + (k // 2) * 0.2
        P.ell(x, y, x + 0.16, y + 0.16, col)


def _bag(P):
    P.poly([(0.22, 0.10), (0.78, 0.10), (0.74, 0.50), (0.80, 0.90), (0.20, 0.90), (0.26, 0.50)], (240, 180, 40))
    P.rect(0.32, 0.34, 0.68, 0.62, (220, 40, 50), r=0.04)
    P.line([(0.22, 0.18), (0.78, 0.18)], 0.6)


def _drop(P):
    P.poly([(0.5, 0.06), (0.74, 0.46), (0.78, 0.64), (0.70, 0.82), (0.5, 0.92), (0.30, 0.82), (0.22, 0.64), (0.26, 0.46)],
           (80, 160, 230))
    P.ell(0.34, 0.52, 0.44, 0.66, (200, 230, 255), outline=False)


def _germ(P):
    for k in range(10):
        a = math.radians(k * 36)
        P.line([(0.5 + 0.26 * math.cos(a), 0.5 + 0.26 * math.sin(a)), (0.5 + 0.40 * math.cos(a), 0.5 + 0.40 * math.sin(a))], 1.0)
        x, y = 0.5 + 0.42 * math.cos(a), 0.5 + 0.42 * math.sin(a)
        P.ell(x - 0.035, y - 0.035, x + 0.035, y + 0.035, (120, 200, 90))
    P.ell(0.22, 0.22, 0.78, 0.78, (120, 200, 90))
    for x, y in ((0.40, 0.40), (0.58, 0.46), (0.46, 0.60)):
        P.ell(x - 0.04, y - 0.04, x + 0.04, y + 0.04, (70, 150, 60), outline=False)


def _barrel(P):
    P.poly([(0.26, 0.10), (0.74, 0.10), (0.82, 0.50), (0.74, 0.90), (0.26, 0.90), (0.18, 0.50)], (170, 110, 60))
    for y in (0.26, 0.74):
        P.line([(0.22, y), (0.78, y)], 1.2, (90, 90, 100))


def _scale(P):
    P.line([(0.5, 0.14), (0.5, 0.86)], 1.4)
    P.line([(0.16, 0.30), (0.84, 0.30)], 1.4)
    P.rect(0.32, 0.84, 0.68, 0.92, (140, 140, 150), r=0.02)
    for x in (0.20, 0.80):
        P.line([(x - 0.06, 0.32), (x - 0.10, 0.56)], 0.6)
        P.line([(x + 0.06, 0.32), (x + 0.10, 0.56)], 0.6)
        P.d.chord(P.p(x - 0.14, 0.46, x + 0.14, 0.66), 0, 180, fill=_c((245, 197, 24)), outline=INKC, width=P.w)


def _x(P):
    P.line([(0.18, 0.18), (0.82, 0.82)], 3.2, L.RED)
    P.line([(0.82, 0.18), (0.18, 0.82)], 3.2, L.RED)


def _check(P):
    P.ell(0.10, 0.10, 0.90, 0.90, L.GREEN)
    P.line([(0.30, 0.52), (0.44, 0.66), (0.72, 0.36)], 2.4, (255, 255, 255))


def _car(P):
    P.poly([(0.10, 0.62), (0.18, 0.44), (0.34, 0.30), (0.66, 0.30), (0.80, 0.44), (0.92, 0.50), (0.92, 0.70), (0.10, 0.70)],
           (240, 240, 245))
    P.poly([(0.36, 0.36), (0.50, 0.36), (0.50, 0.46), (0.26, 0.46)], (150, 200, 240), outline=False)
    P.poly([(0.54, 0.36), (0.64, 0.36), (0.74, 0.46), (0.54, 0.46)], (150, 200, 240), outline=False)
    for x in (0.28, 0.74):
        P.ell(x - 0.09, 0.60, x + 0.09, 0.78, (50, 50, 55))


def _plate(P):
    P.ell(0.06, 0.24, 0.94, 0.80, (250, 250, 250))
    P.ell(0.20, 0.34, 0.80, 0.70, (236, 236, 236), outline=False)
    P.ell(0.28, 0.36, 0.56, 0.62, (170, 100, 60))
    P.ell(0.52, 0.42, 0.70, 0.60, (250, 220, 120))


def _cake(P):
    P.rect(0.16, 0.44, 0.84, 0.88, (250, 220, 180), r=0.04)
    P.rect(0.16, 0.44, 0.84, 0.56, (240, 120, 160), r=0.04)
    for x in (0.34, 0.5, 0.66):
        P.rect(x - 0.025, 0.24, x + 0.025, 0.44, (120, 180, 240), r=0.01)
        P.ell(x - 0.03, 0.14, x + 0.03, 0.24, (250, 190, 40), outline=False)


def _pizza(P):
    P.poly([(0.5, 0.92), (0.10, 0.18), (0.90, 0.18)], (250, 205, 90))
    P.rect(0.08, 0.10, 0.92, 0.22, (220, 150, 70), r=0.06)
    for x, y in ((0.40, 0.36), (0.60, 0.36), (0.50, 0.58)):
        P.ell(x - 0.06, y - 0.06, x + 0.06, y + 0.06, (210, 50, 50))


def _chocolate(P):
    P.rect(0.16, 0.12, 0.84, 0.88, (110, 60, 40), r=0.03)
    for k in range(6):
        x, y = 0.22 + (k % 2) * 0.30, 0.18 + (k // 2) * 0.23
        P.rect(x, y, x + 0.26, y + 0.20, (130, 75, 50), r=0.01)


def _gummy(P):
    P.ell(0.30, 0.08, 0.70, 0.40, (240, 80, 80))
    P.ell(0.24, 0.06, 0.38, 0.20, (240, 80, 80))
    P.ell(0.62, 0.06, 0.76, 0.20, (240, 80, 80))
    P.ell(0.24, 0.34, 0.76, 0.86, (240, 80, 80))
    P.ell(0.18, 0.72, 0.38, 0.94, (240, 80, 80))
    P.ell(0.62, 0.72, 0.82, 0.94, (240, 80, 80))


def _cross(P):
    P.rect(0.38, 0.12, 0.62, 0.88, (230, 50, 60), r=0.03)
    P.rect(0.12, 0.38, 0.88, 0.62, (230, 50, 60), r=0.03)


def _hospital(P):
    P.rect(0.14, 0.20, 0.86, 0.90, (240, 242, 246))
    P.rect(0.42, 0.28, 0.58, 0.50, (230, 50, 60), r=0.0, outline=False)
    P.rect(0.34, 0.34, 0.66, 0.44, (230, 50, 60), r=0.0, outline=False)
    for x in (0.22, 0.66):
        P.rect(x, 0.58, x + 0.12, 0.70, (150, 200, 240))
    P.rect(0.44, 0.66, 0.56, 0.90, (120, 170, 210))


def _document(P):
    P.poly([(0.20, 0.06), (0.64, 0.06), (0.80, 0.22), (0.80, 0.94), (0.20, 0.94)], (250, 250, 250))
    for y in (0.36, 0.48, 0.60, 0.72):
        P.line([(0.30, y), (0.70, y)], 0.7, (160, 160, 170))
    P.line([(0.64, 0.06), (0.64, 0.22), (0.80, 0.22)])


def _arrow_up(P):
    P.poly([(0.5, 0.08), (0.86, 0.48), (0.64, 0.48), (0.64, 0.92), (0.36, 0.92), (0.36, 0.48), (0.14, 0.48)], L.RED)


def _arrow_down(P):
    P.poly([(0.5, 0.92), (0.86, 0.52), (0.64, 0.52), (0.64, 0.08), (0.36, 0.08), (0.36, 0.52), (0.14, 0.52)], L.GREEN)


def _ice(P):
    for k in range(6):
        a = math.radians(k * 60)
        P.line([(0.5, 0.5), (0.5 + 0.40 * math.cos(a), 0.5 + 0.40 * math.sin(a))], 1.6, L.BLUE)
        for s in (0.22, 0.32):
            bx, by = 0.5 + s * math.cos(a), 0.5 + s * math.sin(a)
            for da in (-0.6, 0.6):
                P.line([(bx, by), (bx + 0.08 * math.cos(a + da), by + 0.08 * math.sin(a + da))], 1.2, L.BLUE)


def _energy(P):
    P.rect(0.32, 0.08, 0.68, 0.92, (40, 40, 46), r=0.06)
    P.poly([(0.56, 0.24), (0.40, 0.52), (0.50, 0.52), (0.44, 0.78), (0.62, 0.46), (0.52, 0.46)], (120, 230, 80), outline=False)


ICONS = {
    "fridge": _fridge, "sun": _sun, "fire": _fire, "candy": _candy, "lollipop": _lollipop, "jawbreaker": _jawbreaker,
    "ball": _ball, "bowling": _bowling, "bottle": _bottle, "can": _can, "soda": _can, "cup": _cup, "burger": _burger,
    "fries": _fries, "cereal": _cereal, "milk": _milk, "turkey": _turkey, "egg": _egg, "apple": _apple, "pill": _pill,
    "heart": _heart, "kidney": _kidney, "tooth": _tooth, "brain": _brain, "skull": _skull, "warning": _warning,
    "factory": _factory, "truck": _truck, "store": _store, "house": _house, "court": _court, "gavel": _gavel,
    "money": _money, "kid": _kid, "man": _man, "woman": _woman, "doctor": _doctor, "badge": _badge, "police": _badge,
    "flask": _flask, "lab": _flask, "microscope": _microscope, "clock": _clock, "calendar": _calendar, "phone": _phone,
    "letter": _letter, "box": _box, "microwave": _microwave, "jar": _jar, "bag": _bag, "chips": _bag, "drop": _drop,
    "germ": _germ, "barrel": _barrel, "scale": _scale, "x": _x, "check": _check, "car": _car, "plate": _plate,
    "cake": _cake, "pizza": _pizza, "chocolate": _chocolate, "gummy": _gummy, "cross": _cross, "hospital": _hospital,
    "document": _document, "up": _arrow_up, "down": _arrow_down, "ice": _ice, "energy": _energy,
}
SYNONYMS = {
    "refrigerator": "fridge", "freezer": "fridge", "cold": "ice", "frozen": "ice", "heat": "fire", "hot": "fire",
    "flame": "fire", "sweet": "candy", "sweets": "candy", "lolly": "lollipop", "gobstopper": "jawbreaker",
    "sphere": "ball", "bowlingball": "bowling", "water": "drop", "liquid": "drop", "juice": "bottle", "drink": "cup",
    "coffee": "cup", "cola": "soda", "energydrink": "energy", "hamburger": "burger", "fastfood": "burger", "snack": "chips",
    "crisps": "chips", "cookie": "chocolate", "candybar": "chocolate", "child": "kid", "children": "kid", "toddler": "kid",
    "baby": "kid", "boy": "kid", "girl": "kid", "kids": "kid", "person": "man", "worker": "man", "mother": "woman",
    "mom": "woman", "parent": "woman", "nurse": "doctor", "scientist": "doctor", "medicine": "pill", "drug": "pill",
    "poison": "skull", "death": "skull", "dead": "skull", "danger": "warning", "alert": "warning", "plant": "factory",
    "mill": "factory", "shop": "store", "supermarket": "store", "grocery": "store", "home": "house", "lawsuit": "gavel",
    "judge": "gavel", "law": "court", "courthouse": "court", "dollar": "money", "cash": "money", "fine": "money",
    "cop": "police", "fda": "badge", "test": "flask", "chemical": "flask", "acid": "flask", "time": "clock",
    "date": "calendar", "year": "calendar", "tweet": "phone", "email": "letter", "mail": "letter", "package": "box",
    "shipment": "box", "bacteria": "germ", "virus": "germ", "salmonella": "germ", "weight": "scale", "no": "x",
    "wrong": "x", "yes": "check", "ok": "check", "safe": "check", "meal": "plate", "dinner": "plate", "food": "plate",
    "report": "document", "paper": "document", "study": "document", "rise": "up", "increase": "up", "fall": "down",
    "drop_down": "down", "decrease": "down", "gelatin": "gummy", "jelly": "gummy", "edible": "gummy", "doctorvisit": "hospital",
    "er": "hospital", "ambulance": "hospital", "teeth": "tooth", "mouth": "tooth", "tongue": "tooth",
    "ill": "hospital", "sick": "hospital", "hospitalized": "hospital", "hospitalised": "hospital", "injured": "hospital",
    "injuries": "hospital", "boxes": "box", "units": "box", "bottles": "bottle", "cans": "can", "people": "man",
    "deaths": "skull", "died": "skull", "killed": "skull", "cases": "document", "reports": "document", "complaints": "document",
    "dollars": "money", "fined": "money", "settlement": "money", "liquorice": "candy", "licorice": "candy", "humbug": "candy",
    "humbugs": "candy", "sweet": "candy", "toffee": "candy", "gobstopper": "jawbreaker", "jawbreakers": "jawbreaker",
    "cereals": "cereal", "drinks": "cup", "sodas": "soda", "snacks": "chips", "gummies": "gummy", "turkeys": "turkey",
}


def key_of(name):
    n = re.sub(r"[^a-z_]", "", str(name or "").lower().replace(" ", "").replace("-", ""))
    if n in ICONS:
        return n
    if n in SYNONYMS:
        return SYNONYMS[n]
    if n.endswith("s") and n[:-1] in ICONS:
        return n[:-1]
    for w in reversed(re.findall(r"[a-z]+", str(name or "").lower())):   # the head noun is usually last
        if w in ICONS:
            return w
        if w in SYNONYMS:
            return SYNONYMS[w]
    return None


_FONTS = {}


def _font(px):
    from PIL import ImageFont
    if px not in _FONTS:
        try:
            _FONTS[px] = ImageFont.truetype(str(L.font_path(L.TITLE_FONT)), px)
        except OSError:
            _FONTS[px] = ImageFont.load_default()
    return _FONTS[px]


def icon(name, px=256):
    k = key_of(name)
    if not k:
        return None
    ck = (k, px)
    if ck not in _CACHE:
        P = Pen(px * 4)
        ICONS[k](P)
        _CACHE[ck] = P.im.resize((px, px), Image.LANCZOS)
    return _CACHE[ck]


def sticker_prompt(name):
    """The Flow prompt for an icon we don't draw: a flat sticker on white, trimmed and used like ours."""
    return (f"A single flat vector illustration icon of {name}, simple bold shapes, thick dark outline, flat bright colours, "
            "one soft highlight, centred, on a pure white background, no text, no shadow, no background scene")
