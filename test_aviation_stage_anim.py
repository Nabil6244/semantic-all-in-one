"""Animated stage sprites (anim / _k) and kind auto-loading."""

from PIL import Image, ImageDraw

from aviation import stage as G
from aviation import style as S


def _grow(a):
    k = float(a.get("_k", 1.0))
    im = Image.new("RGBA", (400, 100), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((0, 0, max(1, int(400 * k)), 99), fill=(200, 40, 40, 255))
    return im


G.register("grow", _grow)


def test_anim_progress_quantised_and_drawn_per_step():
    st = G.Stage()
    st.add("grow", at=1.0, anim=2.0, pos=(640, 360), float_=False)
    e = st.params()["elements"][0]
    assert G.anim_k(e, 1.0) == 0.0
    assert G.anim_k(e, 10.0) == 1.0
    k = G.anim_k(e, 2.2)
    assert 0 < k < 1 and abs(k * G.ANIM_STEPS - round(k * G.ANIM_STEPS)) < 1e-9
    assert G.sprite(e, 1.0, 0.25) is G.sprite(e, 1.0, 0.25)
    early, late = G.lay_stage(1.6, 5, st.params()), G.lay_stage(4.0, 5, st.params())

    def red(im):
        return sum(1 for x in range(400, 900, 4) if im.getpixel((x, 360))[0] > 150 and im.getpixel((x, 360))[1] < 90)
    assert red(late) > red(early) * 2


def test_static_element_has_no_progress():
    st = G.Stage()
    st.add("grow", at=0.0)
    assert G.anim_k(st.params()["elements"][0], 3.0) is None


def test_load_kinds_skips_missing_modules():
    G.load_kinds()
    assert "logo_card" in G._FACTORIES


def test_hide_span_goes_out_and_comes_back():
    st = G.Stage()
    st.add("grow", at=0.0, pos=(640, 360), float_=False)
    e = st.params()["elements"][0]
    e["hide"] = [[3.0, 5.0]]
    assert G.transform(e, 2.9) is not None
    assert G.transform(e, 4.0) is None
    assert G.transform(e, 5.0 + S.ENTER_S + 0.05) is not None
