"""Eight flat code-drawn props (Milestone 2): same registry and drawing proxy as the icons, used wherever an icon asset is accepted.
Ids: prop:note, prop:scale, prop:magnifier, prop:book, prop:key, prop:flag, prop:chest, prop:bulb. Drawn in a 100 x 100 design space; `d` is the scaled drawing
proxy from icons.py, `c` the role colour, `o` the outline colour, `w` the line width."""

from __future__ import annotations

PAPER = (240, 232, 200)
GOLD = (226, 170, 40)
BROWN = (130, 86, 52)


def _note(d, c, o, w):
    d.polygon([(14, 14), (86, 14), (86, 70), (70, 88), (14, 88)], fill=(250, 226, 110))
    d.line([(14, 14), (86, 14), (86, 70), (70, 88), (14, 88), (14, 14)], fill=o, width=w, joint="curve")
    d.polygon([(70, 88), (70, 70), (86, 70)], fill=(226, 196, 80), outline=o)
    for y in (34, 50, 66):
        d.line([(26, y), (72, y)], fill=o, width=w)


def _scale(d, c, o, w):
    d.line([(50, 14), (50, 84)], fill=o, width=w + 2)
    d.rectangle([30, 84, 70, 92], fill=c, outline=o, width=w)
    d.line([(22, 30), (78, 30)], fill=o, width=w + 1)
    for cx in (22, 78):
        d.line([(cx, 30), (cx - 11, 62)], fill=o, width=w - 1)
        d.line([(cx, 30), (cx + 11, 62)], fill=o, width=w - 1)
        d.polygon([(cx - 15, 62), (cx + 15, 62), (cx + 9, 74), (cx - 9, 74)], fill=GOLD, outline=o)
    d.ellipse([44, 8, 56, 20], fill=c, outline=o, width=w)


def _magnifier(d, c, o, w):
    d.line([(60, 60), (88, 88)], fill=o, width=w + 8)
    d.line([(60, 60), (88, 88)], fill=BROWN, width=w + 3)
    d.ellipse([10, 10, 66, 66], fill=(214, 236, 244), outline=o, width=w + 1)
    d.ellipse([10, 10, 66, 66], outline=c, width=w - 1)
    d.line([(24, 30), (32, 22)], fill=(255, 255, 255), width=w)


def _book(d, c, o, w):
    d.polygon([(8, 22), (50, 32), (50, 90), (8, 80)], fill=PAPER)
    d.polygon([(92, 22), (50, 32), (50, 90), (92, 80)], fill=(250, 244, 220))
    d.line([(8, 22), (50, 32), (92, 22), (92, 80), (50, 90), (8, 80), (8, 22)], fill=o, width=w, joint="curve")
    d.line([(50, 32), (50, 90)], fill=o, width=w)
    d.polygon([(8, 80), (50, 90), (50, 96), (8, 86)], fill=c, outline=o)
    d.polygon([(92, 80), (50, 90), (50, 96), (92, 86)], fill=c, outline=o)
    for y in (42, 54, 66):
        d.line([(16, y - 6), (42, y)], fill=o, width=w - 1)
        d.line([(84, y - 6), (58, y)], fill=o, width=w - 1)


def _key(d, c, o, w):
    d.ellipse([8, 20, 44, 56], fill=GOLD, outline=o, width=w + 1)
    d.ellipse([20, 32, 32, 44], fill=(192, 192, 192), outline=o, width=w - 1)
    d.rectangle([42, 34, 92, 44], fill=GOLD, outline=o, width=w)
    d.rectangle([72, 44, 80, 62], fill=GOLD, outline=o, width=w)
    d.rectangle([84, 44, 92, 56], fill=GOLD, outline=o, width=w)


def _flag(d, c, o, w):
    d.line([(24, 8), (24, 94)], fill=o, width=w + 3)
    d.ellipse([19, 3, 29, 13], fill=GOLD, outline=o, width=w - 1)
    d.polygon([(24, 16), (50, 10), (76, 18), (92, 14), (92, 52), (76, 56), (50, 48), (24, 54)], fill=c)
    d.line([(24, 16), (50, 10), (76, 18), (92, 14), (92, 52), (76, 56), (50, 48), (24, 54)], fill=o, width=w, joint="curve")
    d.rectangle([14, 90, 36, 96], fill=BROWN, outline=o, width=w - 1)


def _chest(d, c, o, w):
    d.rectangle([10, 46, 90, 90], fill=BROWN, outline=o, width=w)
    d.polygon([(10, 46), (16, 22), (84, 22), (90, 46)], fill=(160, 106, 64), outline=o)
    d.line([(10, 46), (16, 22), (84, 22), (90, 46), (10, 46)], fill=o, width=w, joint="curve")
    d.rectangle([10, 40, 90, 52], fill=GOLD, outline=o, width=w - 1)
    d.rectangle([43, 38, 57, 62], fill=c, outline=o, width=w - 1)
    d.ellipse([47, 46, 53, 52], fill=o)


def _bulb(d, c, o, w):
    d.ellipse([18, 6, 82, 70], fill=(255, 238, 120), outline=o, width=w + 1)
    d.polygon([(34, 58), (66, 58), (62, 78), (38, 78)], fill=(255, 238, 120), outline=o)
    d.rectangle([36, 76, 64, 92], fill=(180, 180, 190), outline=o, width=w)
    d.line([(38, 84), (62, 84)], fill=o, width=w - 1)
    d.line([(42, 50), (42, 34), (50, 42), (58, 34), (58, 50)], fill=c, width=w, joint="curve")


PROPS = {"prop:note": _note, "prop:scale": _scale, "prop:magnifier": _magnifier, "prop:book": _book, "prop:key": _key, "prop:flag": _flag, "prop:chest": _chest,
         "prop:bulb": _bulb}
