"""Story cards set 2 (aviation/story_cards2.py): portrait, fleet card, icon stat, handwriting, flight title, photo card,
big type, paper sticker."""

import os

import pytest
from PIL import Image, ImageDraw

from aviation import stage as G
from aviation import story_cards2 as K


@pytest.fixture()
def imgs(tmp_path):
    face = Image.new("RGB", (300, 380), (190, 120, 90))
    ImageDraw.Draw(face).ellipse((90, 60, 210, 200), fill=(230, 180, 150))
    p1 = tmp_path / "face.png"
    face.save(p1)
    page = Image.new("RGB", (1280, 900), (250, 250, 245))
    pd = ImageDraw.Draw(page)
    pd.rectangle((60, 80, 1200, 190), fill=(30, 30, 30))
    for y in range(240, 800, 40):
        pd.line((60, y, 1200, y), fill=(120, 120, 120), width=6)
    p2 = tmp_path / "page.png"
    page.save(p2)
    photo = Image.new("RGB", (1600, 900), (60, 110, 170))
    ImageDraw.Draw(photo).rectangle((200, 300, 1400, 700), fill=(210, 210, 215))
    p3 = tmp_path / "photo.jpg"
    photo.save(p3)
    return {"face": str(p1), "page": str(p2), "photo": str(p3)}


def _differs(a, b):
    return a.size != b.size or a.tobytes() != b.tobytes()


def _sprite(kind, args):
    im = G._make(kind, args)
    assert im.mode == "RGBA" and im.width > 20 and im.height > 20
    return im


def test_portrait_with_image_and_quote(imgs):
    im = _sprite("portrait", {"name": "Capt. Jane Doe", "role": "Captain", "quote": "We lost the right engine.", "image": imgs["face"]})
    assert im.width > 600
    assert im.getbbox() is not None


def test_portrait_without_image_is_a_silhouette(imgs):
    im = _sprite("portrait", {"name": "Someone", "role": "Executive"})
    assert im.width < 600
    # the face area holds the neutral grey silhouette, never colour
    px = im.getpixel((im.width // 2, 140))
    assert abs(px[0] - px[1]) < 12 and abs(px[1] - px[2]) < 16
    _sprite("portrait", {"name": "X", "role": "Y", "image": "/no/such/file.png"})


def test_portrait_photo_is_greyscale(imgs):
    im = _sprite("portrait", {"name": "A", "role": "B", "image": imgs["face"]})
    x = im.width // 2
    r, g, b, _ = im.getpixel((x, 140))
    assert abs(r - g) < 4 and abs(g - b) < 4


def test_fleet_card_badge_pops():
    a = {"count": 3, "type": "b707", "airline": "singapore_airlines"}
    lo, hi = _sprite("fleet_card", dict(a, _k=0.05)), _sprite("fleet_card", dict(a, _k=1.0))
    assert lo.size == hi.size and _differs(lo, hi)
    assert _differs(_sprite("fleet_card", dict(a, _k=0.2)), hi)


def test_icon_stat_all_icons_and_count_up():
    for ic in ("chart", "plane", "globe", "people", "cash", "route", "seat", "fuel", "nonsense"):
        _sprite("icon_stat", {"value": "5", "label": "x", "icon": ic})
    a = {"value": "S$100", "unit": "Million", "label": "in Profit", "icon": "cash"}
    assert _differs(_sprite("icon_stat", dict(a, _k=0.2)), _sprite("icon_stat", dict(a, _k=1.0)))
    assert K.counted("S$100", 1.0) == "S$100"
    assert K.counted("S$100", 0.5) == "S$50"
    assert K.counted("1,200", 0.0) == "0"
    assert K.counted("2.5", 0.4) == "1.0"
    assert K.counted("none", 0.3) == "none"
    assert _sprite("icon_stat", dict(a, _k=1.0)).tobytes() == _sprite("icon_stat", a).tobytes()


def test_handwriting_sequence():
    a = {"text": "Malayan Airways", "strike": True, "rewrite": "Singapore Airlines"}
    shots = [_sprite("handwriting", dict(a, _k=k)) for k in (0.0, 0.2, 0.5, 1.0)]
    assert len({s.size for s in shots}) == 1
    for x, y in zip(shots, shots[1:]):
        assert _differs(x, y)
    # red strike line exists only after the writing phase
    def reds(im):
        return sum(1 for p in im.getdata() if p[3] > 200 and p[0] > 200 and p[1] < 90 and p[2] < 90)
    assert reds(shots[1]) == 0 and reds(shots[3]) > 200
    plain = _sprite("handwriting", {"text": "Name", "_k": 0.5})
    assert _differs(plain, _sprite("handwriting", {"text": "Name", "_k": 1.0}))


def test_flight_title():
    a = {"flight": "SQ 108", "from": "SIN", "to": "TPE"}
    lo, hi = _sprite("flight_title", dict(a, _k=0.2)), _sprite("flight_title", dict(a, _k=1.0))
    assert _differs(lo, hi)
    _sprite("flight_title", {"flight": "XX 1", "from": "ZZZ", "to": "QQQ", "_k": 1.0})


def test_photo_card_ken_burns_and_fallback(imgs):
    a = {"image": imgs["photo"], "title": "The crash site", "subtitle": "Taipei, 2000", "credit": "Some Agency"}
    assert _differs(_sprite("photo_card", dict(a, _k=0.0)), _sprite("photo_card", dict(a, _k=1.0)))
    _sprite("photo_card", dict(a, image="/nope.jpg"))
    _sprite("photo_card", {"title": "t", "credit": "c"})


def test_big_type_arrows_draw(imgs):
    a = {"text": "What happened to this airline?", "highlight": ["airline"], "arrows": [[200, 600], [1000, 560]]}
    lo, hi = _sprite("big_type", dict(a, _k=0.1)), _sprite("big_type", dict(a, _k=1.0))
    assert lo.size == hi.size == (1280, 720) and _differs(lo, hi)
    plain = _sprite("big_type", {"text": "Hello world", "highlight": ["world"]})
    assert plain.width < 1280
    yel = [p for p in plain.getdata() if p[3] > 200 and p[0] > 240 and 190 < p[1] < 220 and p[2] < 70]
    assert yel


def test_paper_sweep_and_fallback(imgs):
    a = {"image": imgs["page"], "headline_box": [60, 80, 1140, 110], "source": "The Straits Times"}
    lo, hi = _sprite("paper", dict(a, _k=0.0)), _sprite("paper", dict(a, _k=1.0))
    assert lo.size == hi.size and _differs(lo, hi)
    _sprite("paper", {"image": "/missing.png", "source": "x"})
    _sprite("paper", {"image": imgs["page"], "highlight_box": ["a", "b"]})


def test_builders_and_full_stage_frame(imgs):
    st = G.Stage()
    ids = [
        K.add_portrait(st, 0.0, "Jane", "Captain", "Quote here", imgs["face"]),
        K.add_fleet_card(st, 1.0, 3, "b707", "singapore_airlines"),
        K.add_icon_stat(st, 2.0, "S$100", "in Profit", "cash", unit="Million"),
        K.add_handwriting(st, 3.0, "Malayan", strike=True, rewrite="Singapore"),
        K.add_flight_title(st, 4.0, "SQ 108", "SIN", "TPE"),
        K.add_photo_card(st, 5.0, imgs["photo"], "Title", "Credit"),
        K.add_big_type(st, 6.0, "Why did it fail?", ["fail"], [[300, 600]]),
        K.add_paper(st, 7.0, imgs["page"], [60, 80, 1000, 100], source="News"),
    ]
    assert len(set(ids)) == 8
    params = st.params()
    for t in (0.8, 2.6, 4.0, 5.2, 7.5, 9.0):
        frame = G.lay_stage(t, 12.0, params)
        assert frame is not None and frame.size == (1280, 720)
