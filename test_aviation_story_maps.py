"""Political map + route-map card (aviation/story_maps.py)."""

import numpy as np

from aviation import stage as G
from aviation import story_maps as SM
from aviation import style as S

PM = {"countries": [{"name": "Malaysia", "color": "red"}, {"code": "SGP", "color": "blue"}], "title": "British Malaya"}


def test_shapes_load():
    w = SM.world()
    assert len(w) > 200
    assert SM.find_country("Malaysia") is not None and SM.find_country("MYS") == SM.find_country("Malaysia")
    assert SM.find_country("GB") == SM.find_country("United Kingdom")


def test_named_country_is_filled():
    sp = SM._political(SM._clean(PM))
    fl = sp.fills[0]
    x0, y0, x1, y1 = fl["box"]
    ys, xs = np.nonzero(np.asarray(fl["mask"]) > 250)
    i = len(xs) // 2
    px = SM.political_map(dict(PM, _k=1.0)).getpixel((int(xs[i]), int(ys[i])))
    assert px[0] > 150 and px[1] < 100 and px[2] < 100, px          # red-ish
    empty = SM.political_map(dict(PM, _k=0.0)).getpixel((int(xs[i]), int(ys[i])))
    assert empty[0] < 60


def test_animation_differs():
    a = SM.political_map(dict(PM, _k=0.2))
    b = SM.political_map(dict(PM, _k=1.0))
    assert np.asarray(a).tobytes() != np.asarray(b).tobytes()
    r = {"hubs": ["SIN"], "destinations": ["LHR", "SYD"]}
    assert SM.route_map(dict(r, _k=0.2)).tobytes() != SM.route_map(dict(r, _k=1.0)).tobytes()


def test_unknown_names_ignored():
    im = SM.political_map({"countries": [{"name": "Atlantis"}, "Nowhere"], "title": "x", "places": ["Zzzz"]})
    assert im.size == (1100, 620)
    im = SM.route_map({"hubs": ["ZZZ"], "destinations": ["QQQ"], "_k": 0.5})
    assert im.size == (1100, 620)
    assert SM.political_map({"countries": []}).size == (1100, 620)


def test_routes_from_only_named():
    r = SM.routes_from("It flew to London, Sydney and Tokyo, then Bangkok.", "singapore_airlines")
    assert r["hubs"] == ["SIN"] and r["destinations"] == ["LHR", "SYD", "HND", "BKK"]
    assert SM.routes_from("nothing named here", "singapore_airlines")["destinations"] == []
    assert "SIN" not in SM.routes_from("Singapore and Paris", "singapore_airlines")["destinations"]


def test_stage_frame_renders():
    st = G.Stage()
    st.add("x", 0.0) if False else None
    a = SM.add_political_map(st, 0.0, PM["countries"], title="British Malaya")
    b = SM.add_route_map(st, 4.0, ["SIN"], ["LHR", "SYD"], airline="singapore_airlines", year=1972)
    st.remove(a, 4.0)
    p = st.params()
    f1 = G.lay_stage(2.0, 8.0, p)
    f2 = G.lay_stage(7.5, 8.0, p)
    assert f1 is not None and f2 is not None and f1.size == (S.W, S.H)
    assert f1.tobytes() != f2.tobytes()
