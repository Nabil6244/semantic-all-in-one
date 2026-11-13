"""Logo cards, timeline bar and dot on the stage (aviation/storycards.py)."""

from aviation import stage as G
from aviation import storycards as K
from aviation import style as S


def test_eras_from_catalog():
    e = K.eras("singapore_airlines")
    names = [n for n, _, _ in e]
    assert names[0] == "Malayan Airways" and names[-1] == "Singapore Airlines"
    assert e[-1][1] == 1972
    assert K.eras("no_such_airline") == []


def test_logo_card_white_with_name():
    im = K.logo_card({"airline": "singapore_airlines", "plane": False})
    assert im.mode == "RGBA" and im.getpixel((im.width // 2, 10))[:3] == S.WHITE[:3]
    assert im.getpixel((0, 0))[3] == 0                       # rounded corner is transparent
    long = K.logo_card({"airline": "msa", "name": "Malaysia-Singapore Airlines Limited Company", "plane": False})
    assert long.width == im.width and long.height <= im.height + 40   # wraps to two lines, type shrinks, never overflows


def test_years_text():
    assert K._years_text({"years": "1963–1966"}) == "1963–1966"
    assert K._years_text({"airline": "singapore_airlines"}) == "since 1972"


def test_bar_x_and_ticks():
    assert K.bar_x(1947, 1947, 1972, 1000) == 140
    assert K.bar_x(1972, 1947, 1972, 1000) == 1140
    assert K.bar_x(1900, 1947, 1972, 1000) == 140            # clamped
    bar = K.timeline_bar({"start": 1947, "end": 2026})
    assert bar.width == 1040 + 60


def test_add_timeline_builds_up_and_ticks_badge():
    st = G.Stage()
    ids = K.add_timeline(st, 0.0, K.eras("singapore_airlines"), airline="singapore_airlines")
    assert len(ids) == 2 + 4                                 # bar, dot, four names
    p = st.params()
    assert [y for _, y in p["years"]] == ["1947", "1963", "1966", "1972"]
    cards = [e["args"]["airline"] for e in p["elements"] if e["kind"] == "logo_card"]
    assert cards == ["malayan_airways", "malaysian_airways", "msa", "singapore_airlines"]   # each era in its own colours
    dot = next(e for e in p["elements"] if e["kind"] == "timeline_dot")
    x0 = G.transform(dot, 0.2)[0]
    x1 = G.transform(dot, 0.4 + 3 * 1.6 + 1.0)[0]
    assert abs(x1 - K.bar_x(1972, 1947, 2026, 1040)) < 1 and x1 > x0 + 300     # the dot travels to 1972 on a bar to today
    im = G.lay_stage(6.0, 8.0, p)
    assert im is not None and im.size == (S.W, S.H)
    assert K.add_timeline(G.Stage(), 0.0, []) == []


def test_logo_card_carries_its_era_plane_above_the_name():
    bare = K.logo_card({"airline": "msa", "name": "Malaysia-Singapore Airlines", "years": "1966–1972", "plane": False})
    with_plane = K.logo_card({"airline": "msa", "name": "Malaysia-Singapore Airlines", "years": "1966–1972"})
    assert with_plane.height > bare.height
    lift = with_plane.height - bare.height
    band = with_plane.crop((0, lift + bare.height // 3, with_plane.width, with_plane.height))      # the name / years area
    ref = bare.crop((0, bare.height // 3, bare.width, bare.height))
    assert band.crop((0, 0, ref.width, ref.height)).tobytes() == ref.tobytes()                  # nothing sits on the text
