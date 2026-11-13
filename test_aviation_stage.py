"""Sticker stage engine (aviation/stage.py): builder, layout, motion, sprites, render."""

import json

from PIL import Image

from aviation import stage as G
from aviation import style as S


def _red(args):
    return Image.new("RGBA", (int(args.get("w", 200)), 120), (220, 30, 30, 255))


G.register("redbox", _red)


def test_slots_shrink_and_centre():
    assert G.slots(0) == []
    one = G.slots(1)
    assert one[0][0] == 640 and one[0][2] == 1.0
    three = G.slots(3)
    assert three[1][0] == 640 and three[0][0] < 640 < three[2][0]
    assert three[0][2] < G.slots(2)[0][2] < 1.0


def test_new_element_makes_others_glide_aside():
    st = G.Stage()
    a = st.add("redbox", at=0.0)
    b = st.add("redbox", at=3.0)
    pa = st.params()["elements"][0]
    assert len(pa["keys"]) == 2                          # placed, then glided aside
    xa_before = G.transform(pa, 2.9)[0]
    xa_after = G.transform(pa, 3.0 + S.MOVE_S + 0.01)[0]
    assert abs(xa_before - 640) < 1 and xa_after < 640
    pb = st.params()["elements"][1]
    assert G.transform(pb, 3.0 + S.ENTER_S + 0.01)[0] > 640
    assert st.live(1.0) == [a] and st.live(3.5) == [a, b]


def test_remove_relayouts_and_exit_ends_visibility():
    st = G.Stage()
    a = st.add("redbox", at=0.0)
    b = st.add("redbox", at=1.0)
    st.remove(a, at=4.0, exit="slide_left")
    e = st.params()["elements"]
    assert G.transform(e[0], 4.0 + S.EXIT_S + 0.01) is None
    assert G.transform(e[0], 4.0 + S.EXIT_S / 2)[0] < G.transform(e[0], 3.9)[0]      # leaving to the left
    assert abs(G.transform(e[1], 4.0 + S.MOVE_S + 0.05)[0] - 640) < 1                 # b back to the centre


def test_move_pins_element_out_of_row():
    st = G.Stage()
    a = st.add("redbox", at=0.0)
    st.add("redbox", at=1.0)
    st.move(a, at=2.0, pos=(200, 600), scale=0.5)
    st.add("redbox", at=4.0)
    e = st.params()["elements"][0]
    x, y, s, _, _ = G.transform(e, 6.0)
    assert abs(x - 200) < 1 and abs(y - 600) < S.FLOAT_PX + 1 and abs(s - 0.5) < 1e-6


def test_enter_kinds_animate():
    for how in ("pop", "slide_left", "slide_right", "drop", "rise", "fade"):
        st = G.Stage()
        st.add("redbox", at=1.0, enter=how)
        e = st.params()["elements"][0]
        assert G.transform(e, 0.5) is None
        early, late = G.transform(e, 1.05), G.transform(e, 1.0 + S.ENTER_S + 0.01)
        assert early != late, how


def test_float_keeps_resting_sticker_alive():
    st = G.Stage()
    st.add("redbox", at=0.0)
    e = st.params()["elements"][0]
    ys = {round(G.transform(e, t)[1], 2) for t in (2.0, 3.0, 4.0)}
    assert len(ys) == 3


def test_params_json_safe_and_cues():
    st = G.Stage()
    a = st.add("redbox", at=0.0, enter="slide_left")
    st.year(0.0, 1963)
    st.year(1.0, 1963)                                     # same year twice: one tick
    st.year(2.0, 1966)
    st.remove(a, at=3.0, exit="slide_right")
    json.dumps(st.params())
    names = [n for _, n in st.cues()]
    assert names.count(S.SOUNDS["year"]) == 2 and S.SOUNDS["slide"] in names


def test_badge_roll():
    yrs = [[0.0, "1963"], [2.0, "1966"]]
    assert G.badge_digits(yrs, 1.0) == ("", "1963", 1.0)
    prev, cur, k = G.badge_digits(yrs, 2.1)
    assert (prev, cur) == ("1963", "1966") and 0 < k < 1
    assert G.badge_digits(yrs, 3.0)[2] == 1.0


def test_render_draws_sprite_edge_and_badge():
    st = G.Stage()
    st.add("redbox", at=0.0, args={"w": 300}, edge=True)
    st.year(0.0, 1972)
    p = st.params()
    im = G.lay_stage(2.0, 10.0, p)
    assert im.mode == "RGBA" and im.size == (S.W, S.H)
    px = im.load()
    reds = sum(1 for x in range(400, 900, 5) for y in range(300, 460, 5) if px[x, y][0] > 180 and px[x, y][1] < 80)
    whites = sum(1 for x in range(400, 900, 2) for y in range(250, 520, 2) if min(px[x, y][:3]) > 235)
    assert reds > 50 and whites > 20                         # sticker body + white die-cut rim
    bx = [px[x, y] for x in range(S.W - 200, S.W - 50, 4) for y in range(45, 100, 4)]
    assert any(abs(c[0] - S.NAVY[0]) < 6 and abs(c[2] - S.NAVY[2]) < 6 for c in bx)


def test_render_empty_is_none_and_unknown_kind_placeholder():
    assert G.lay_stage(0.0, 1.0, {}) is None
    st = G.Stage()
    st.add("no_such_kind", at=0.0, args={"label": "MSA"})
    im = G.lay_stage(1.0, 2.0, st.params())
    assert im is not None
    assert im.getpixel((640, 380))[:3] != S.STAGE_BG[:3]


def test_sprite_cache_reuses_drawing():
    st = G.Stage()
    st.add("redbox", at=0.0, args={"w": 210})
    e = st.params()["elements"][0]
    assert G.sprite(e, 0.8) is G.sprite(e, 0.801)
    assert G.sprite(e, 0.8).width < G.sprite(e, 1.0).width


def test_offscreen_paste_clips_without_error():
    st = G.Stage()
    st.add("redbox", at=0.0, pos=(-50, -40), args={"w": 300})
    assert G.lay_stage(1.0, 2.0, st.params()) is not None
