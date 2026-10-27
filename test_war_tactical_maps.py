"""Tactical / political explainer maps: deterministic, inside the frame, never blank, never inventing a place."""
import hashlib

from PIL import Image, ImageChops

from cinematic_explainer.war import maps_tactical as MT
from cinematic_explainer.war import registry

P = {"theme": "tactical", "places": ["Kharkiv", "Kyiv", {"name": "Kupiansk", "kind": "ring"}, "Atlantis"],
     "routes": [{"from": "Kharkiv", "to": "Kupiansk", "style": "dashed_blue", "label": "Supply line"}],
     "glyphs": [{"place": "Kupiansk", "kind": "explosion"}, {"place": "Nowhere", "kind": "drone"}],
     "focus": [["Kharkiv", "Kupiansk"], ["Kyiv"]], "chips": [{"title": "Note", "sub": "approximate", "variant": "red"}]}


def _md5(im):
    return hashlib.md5(im.tobytes()).hexdigest()


def test_registered_in_all_cards():
    cards = registry.all_cards()
    assert "tac_map" in cards and "tac_route" in cards


def test_deterministic_and_full_frame():
    a = MT.tac_map(2.0, 8.0, dict(P))
    b = MT.tac_map(2.0, 8.0, dict(P))
    assert a.size == (1280, 720) and a.mode == "RGBA" and _md5(a) == _md5(b)
    assert a.getchannel("A").getextrema() == (255, 255)          # opaque full frame


def test_never_blank_even_with_nothing_resolvable():
    for params in ({}, {"places": ["Atlantis"]}, {"theme": "political"}):
        im = MT.tac_map(0.5, 4.0, params).convert("L")
        lo, hi = im.getextrema()
        assert hi - lo > 20                                         # grid and outlines are always there


def test_unknown_place_skipped_not_fabricated():
    p = dict(P)
    info = MT.render_info(p, 3.0, 8.0)
    assert any("Atlantis" in s for s in info["skipped"]) and any("Nowhere" in s for s in info["skipped"])
    names = [n for n, _r in info["labels"]]
    assert "ATLANTIS" not in names and "KHARKIV" in names
    assert MT.resolve_place("Atlantis")[0] is None
    assert MT.resolve_place("Ukraine")[0] is None                   # an area is not a point
    assert MT.resolve_place({"name": "Mine", "lat": 50.0, "lon": 36.0})[0]["lat"] == 50.0


def test_labels_inside_frame_and_do_not_overlap():
    info = MT.render_info({"places": ["Kyiv", "Kharkiv", "Odesa", "Dnipro", "Zaporizhzhia", "Donetsk", "Kherson", "Poltava", "Sumy"], "frame": "ukraine"}, 6.0, 8.0)
    rects = [r for _n, r in info["labels"] if r]
    assert rects
    for r in rects:
        assert 0 <= r[0] and r[2] <= 1280 and 0 <= r[1] and r[3] <= 720
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def test_camera_moves_between_focus_steps_and_markers_animate():
    v0 = MT.render_info(P, 0.2, 8.0)["view"]
    v1 = MT.render_info(P, 7.5, 8.0)["view"]
    assert v0 != v1
    early, late = MT.tac_map(0.6, 8.0, dict(P)), MT.tac_map(3.0, 8.0, dict(P))
    assert ImageChops.difference(early.convert("RGB"), late.convert("RGB")).getbbox() is not None


def test_route_label_always_illustrative_and_route_card():
    im = MT.tac_route(3.0, 6.0, {"from": "Odesa", "to": "Moscow"})
    assert im.size == (1280, 720)
    sk = MT.tac_route(3.0, 6.0, {"from": "Odesa", "to": "Atlantis"})
    assert sk.size == (1280, 720)                                    # an unresolvable end draws no route, still a map


def test_political_theme_fills_ukraine_blue_russia_red():
    im = MT.tac_map(3.0, 6.0, {"theme": "political", "frame": "ukraine_russia"}).convert("RGB")
    cols = {im.getpixel((x, y)) for x in (200, 900) for y in (300,)}
    assert len(cols) == 2


_UP = {"places": [{"name": "Odesa"}, {"name": "Mykolaiv", "kind": "ring"}], "regions": [{"name": "Ukraine", "role": "blue"}],
       "glyphs": [{"place": "Odesa", "kind": "sticker", "name": "drone", "start": 1.0}]}


def test_looks_differ_and_are_deterministic():
    a = MT.tac_map(4.0, 7.0, dict(_UP, look="night"))
    b = MT.tac_map(4.0, 7.0, dict(_UP, look="table"))
    assert a.size == (1280, 720)
    assert a.tobytes() != b.tobytes()
    assert a.tobytes() == MT.tac_map(4.0, 7.0, dict(_UP, look="night")).tobytes()


def test_camera_opens_wide_then_settles():
    assert MT.render_info(dict(_UP), 0.0, 7.0)["view"][2] > MT.render_info(dict(_UP), 3.0, 7.0)["view"][2]


def test_unknown_region_is_skipped_not_guessed():
    p = dict(_UP, regions=[{"name": "Atlantis"}])
    MT.tac_map(3.0, 7.0, p)
    assert any("Atlantis" in x for x in p["_skipped"])
