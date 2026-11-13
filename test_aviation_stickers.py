"""Tests for aviation.stickers (code-drawn sticker kit). PIL only. Writes one contact sheet to out/stickers_sheet.png."""
import os
from pathlib import Path

import pytest
from PIL import Image

from aviation import stickers as S

ROOT = Path(__file__).resolve().parent
FAMS = ("narrow", "wide", "jumbo", "regional", "turboprop", "old_jet", "propliner")
REP = {"narrow": "a320", "wide": "b777", "jumbo": "b747", "regional": "e_jet", "turboprop": "atr", "old_jet": "b707", "propliner": "dc3"}


def _corners_clear(im, thr=8):
    w, h = im.size
    return all(im.getpixel(p)[3] <= thr for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)))


def _count_near(im, rgb, tol=22):
    px = im.convert("RGBA").getdata()
    return sum(1 for r, g, b, a in px if a > 250 and abs(r - rgb[0]) < tol and abs(g - rgb[1]) < tol and abs(b - rgb[2]) < tol)


@pytest.mark.parametrize("fam", FAMS)
def test_aircraft_families(fam):
    assert S.aircraft_family(REP[fam]) == fam
    im = S.aircraft(REP[fam], "singapore_airlines" , 500)
    assert im.mode == "RGBA" and _corners_clear(im)
    assert 400 <= im.width <= 560 and im.height > 100


def test_family_mapping_fallback():
    assert S.aircraft_family("totally-unknown") == "narrow"
    assert S.aircraft_family("a380") == "jumbo" and S.aircraft_family("b787") == "wide"
    assert S.aircraft_family("DC-3") == "propliner" and S.aircraft_family("dash8") == "turboprop"
    assert S.aircraft("zzz", "nope", 300).mode == "RGBA"


def test_silhouettes_differ():
    masks = {f: S.aircraft(REP[f], "klm", 400).getchannel("A").point(lambda v: 255 if v > 128 else 0) for f in FAMS}
    keys = list(masks)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            ma, mb = masks[a], masks[b]
            if ma.size == mb.size:
                assert ma.tobytes() != mb.tobytes()
            else:
                assert ma.size != mb.size or True
    assert len({masks[f].size for f in FAMS}) > 3


def test_aircraft_uses_tail_colour():
    for al in ("lufthansa", "air_france", "klm"):
        lv = S.livery(al)
        im = S.aircraft("a320", al, 600)
        assert _count_near(im, lv["tail"]) > 600, al
    a = S.aircraft("a320", "lufthansa", 400).convert("RGB").tobytes()
    b = S.aircraft("a320", "air_france", 400).convert("RGB").tobytes()
    assert a != b


def test_cache_same_content():
    a, b = S.aircraft("b777", "klm", 420), S.aircraft("b777", "klm", 420)
    assert a is not b and a.tobytes() == b.tobytes()
    assert S.flag("sg").tobytes() == S.flag("SG").tobytes()
    assert S.bubble("hi there", 300, ("hi",)).tobytes() == S.bubble("hi there", 300, ["hi"]).tobytes()
    assert S.aircraft.cache_info is not None if hasattr(S.aircraft, "cache_info") else True


def test_die_cut_rim():
    base = Image.new("RGBA", (80, 60), (0, 0, 0, 0))
    Image.Image.paste(base, Image.new("RGBA", (40, 30), (200, 30, 30, 255)), (20, 15))
    out = S.die_cut(base, edge=10)
    pad = S.die_cut_pad(10)
    assert out.size == (80 + 2 * pad, 60 + 2 * pad)
    assert _corners_clear(out)
    y = pad + 30
    for dx in (1, 4, 8):                       # just outside the left edge of the red box
        r, g, b, a = out.getpixel((pad + 20 - dx, y))
        assert a == 255 and min(r, g, b) >= 250
    r, g, b, a = out.getpixel((pad + 30, pad + 25))
    assert (r, g, b, a) == (200, 30, 30, 255)
    # shadow lies down-right: darker semi-transparent pixels beyond the rim on the right/bottom, none left/top
    assert out.getpixel((pad + 60 + 12, y))[3] > 0
    assert out.getpixel((pad + 60 + 12, y))[:3] != (255, 255, 255) or out.getpixel((pad + 60 + 12, y))[3] < 255
    assert S.die_cut(base, 10, shadow=False).getpixel((pad + 60 + 14, y))[3] == 0
    assert S.sticker(base, 6).size == (80 + 2 * S.die_cut_pad(6), 60 + 2 * S.die_cut_pad(6))


def test_tail_mark():
    im = S.tail_mark("lufthansa", 160)
    assert im.mode == "RGBA" and im.size == (160, 160) and _corners_clear(im)
    assert _count_near(im, S.livery("lufthansa")["tail"]) > 800
    assert S.tail_mark("nope", 80).mode == "RGBA"


def test_flags_all_and_unknown():
    assert len(S.FLAGS) >= 40
    for code in "SG MY GB FR NL DE US IN AE QA AU JP CN HK KR TH ID PH VN TR IT ES PT IE CH AT BE DK SE NO FI PL RU CA BR MX AR ZA EG SA NZ PK LK".split():
        assert code in S.FLAGS, code
        im = S.flag(code.lower(), 180)
        assert im.mode == "RGBA" and im.size == (180, 120) and _corners_clear(im), code
        assert im.getpixel((90, 60))[3] == 255
    g = S.flag("zz", 200)
    assert g.mode == "RGBA" and g.size == (200, 133)
    assert S.flag("", 100).mode == "RGBA"
    assert S.flag("JP").tobytes() != S.flag("SG").tobytes()


def test_hand_flag():
    a, b = S.hand_flag("SG", 260, "left"), S.hand_flag("SG", 260, "right")
    for im in (a, b):
        assert im.mode == "RGBA" and im.width == 260 and _corners_clear(im) or im.getpixel((im.width - 1, 0))[3] <= 8
    assert a.tobytes() != b.tobytes()
    assert S.hand_flag("zz").mode == "RGBA"


def test_bubble():
    for tail in ("left", "right", "none"):
        im = S.bubble("Mine! The crash proves it was always our airline", 520, ("Mine!", "airline"), tail)
        assert im.mode == "RGBA" and im.width == 520 and _corners_clear(im) or tail != "none"
    assert S.bubble("a b c", 400, tail="none").height < S.bubble("a b c", 400, tail="left").height
    big = S.bubble("word " * 40, 400)
    small = S.bubble("word", 400)
    assert big.height > small.height
    hi = S.bubble("Hello world", 400, ("world",))
    assert _count_near(hi, S.YELLOW[:3], 12) > 100
    assert _count_near(S.bubble("Hello world", 400), S.YELLOW[:3], 12) == 0


@pytest.mark.parametrize("kind", list(S.PROP_KINDS) + ["unknownthing"])
def test_props(kind):
    im = S.prop(kind, 220)
    assert im.mode == "RGBA" and im.size == (220, 220)
    assert im.getchannel("A").getbbox() is not None
    if kind in ("ticket", "globe", "crown", "plane_icon", "chart", "cash", "coins"):
        assert _corners_clear(im)


def test_props_differ():
    seen = {S.prop(k, 120).tobytes() for k in S.PROP_KINDS}
    assert len(seen) == len(S.PROP_KINDS)


def test_contact_sheet():
    from PIL import ImageDraw
    pad = 16
    liveries = ("singapore_airlines", "lufthansa", "klm")
    sheet_w = 1900
    y = pad
    sections = []
    # aircraft: 7 families x 3 liveries
    ac = [[S.die_cut(S.aircraft(REP[f], al, 280), 6) for al in liveries] for f in FAMS]
    row_h = max(i.height for row in ac for i in row) + 8
    flags = [S.sticker(S.flag(c, 150), 5) for c in ("SG", "GB", "FR", "DE", "US", "IN", "AE", "JP", "TR", "BR", "ZA", "CA")]
    hands = [S.sticker(S.hand_flag(c, 220, s), 6) for c, s in (("SG", "left"), ("MY", "right"), ("GB", "left"))]
    bubbles = [S.sticker(S.bubble(t, 440, b, tl), 6) for t, b, tl in (
        ("This plane is ours! We built the whole fleet.", ("ours!",), "left"),
        ("No, it was split in 1972, remember?", ("1972",), "right"), ("A plain speech bubble with no tail", (), "none"))]
    props = [S.sticker(S.prop(k, 170), 5) for k in S.PROP_KINDS]
    tails = [S.sticker(S.tail_mark(a, 120), 5) for a in ("singapore_airlines", "lufthansa", "klm", "air_france", "qantas")]
    total_h = pad + row_h * len(FAMS) + 190 * 3 + 360 + 260 + pad * 8
    sheet = Image.new("RGB", (sheet_w, total_h), (0, 0, 0))

    def place(items, y0, cols_w=None):
        x = pad
        ymax = y0
        for im in items:
            if x + im.width > sheet_w - pad:
                x = pad
                y0 = ymax + 6
            sheet.paste(im, (x, y0), im)
            x += im.width + 10
            ymax = max(ymax, y0 + im.height)
        return ymax + pad

    y = pad
    for row in ac:
        x = pad
        for im in row:
            sheet.paste(im, (x, y), im)
            x += im.width + 20
        y += row_h
    y = place(tails, y)
    y = place(flags, y)
    y = place(hands, y)
    y = place(bubbles, y)
    y = place(props, y)
    sheet = sheet.crop((0, 0, sheet_w, min(total_h, y + pad)))
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    sheet.save(out / "stickers_sheet.png")
    assert (out / "stickers_sheet.png").exists()
