"""Map framing, context layers and sequencing for the War Documentary tactical / political maps (cinematic_explainer/war/maps_tactical.py)."""
import math

from PIL import Image

from cinematic_explainer.war import geo_data as G
from cinematic_explainer.war import maps_tactical as MT


def _px(img, x, y):
    return img.convert("RGB").getpixel((x, y))


def test_context_data_present_and_sourced():
    ctx = G.context()
    assert len(ctx["rivers"]) > 20 and len(ctx["lakes"]) > 20 and "public domain" in ctx["source"]
    assert any(r["n"] in ("Dnipro", "Dnepre") for r in ctx["rivers"]) and any(r["n"] == "Volga" for r in ctx["rivers"])
    names = {c["n"] for c in G.context_cities()}
    assert {"Kyiv", "Moscow", "Kharkiv"} <= names
    assert len(G.theatre_admin1()) > 200


def test_view_never_tighter_than_the_minimum_span():
    for places in (["Kupiansk"], ["Kharkiv", "Kupiansk"], ["Sudzha", "Kursk"]):
        info = MT.render_info({"places": places, "chips": [{"title": "x"}]}, 3.0, 8.0)
        cx, cy, hw, w, h = info["view"]
        assert math.degrees(2 * hw) >= 8.5          # at least about 9 degrees of longitude (the push-in takes 4 %)


def test_subject_stays_left_of_the_panel_and_inside_the_frame():
    params = {"places": ["Kharkiv", "Kupiansk", "Lyman"], "chips": [{"title": "Note", "sub": "text"}]}
    info = MT.render_info(params, 6.0, 8.0)
    assert len(info["labels"]) == 3
    for txt, rect in info["labels"]:
        assert rect is not None and rect[2] <= MT.W - 330 and rect[0] >= 20


def test_map_has_real_detail_labels_and_scale():
    info = MT.render_info({"places": ["Moscow", "Ryazan"]}, 3.0, 8.0)
    assert len(info["context_labels"]) >= 3
    assert any(n in info["context_labels"] for n in ("RUSSIA", "Nizhny Novgorod", "Voronezh", "Kazan", "Belarus".upper()))


def test_sea_label_only_on_open_water():
    MT.clear_cache()
    info = MT.render_info({"places": ["Odesa", "Sevastopol"], "frame": "black_sea"}, 3.0, 8.0)
    assert "BLACK SEA" in info["context_labels"]


def test_political_and_tactical_look_different():
    a = MT.tac_map(3.0, 8.0, {"places": ["Kyiv", "Moscow"], "theme": "political", "frame": "ukraine_russia"})
    b = MT.tac_map(3.0, 8.0, {"places": ["Kyiv", "Moscow"], "theme": "tactical", "frame": "ukraine_russia"})
    ra, rb = _px(a, 560, 200), _px(b, 560, 200)           # inside Russia
    assert ra[0] > ra[2] + 40 and rb[0] < 80               # crimson fill versus quiet charcoal


def test_badge_always_present_both_themes():
    for theme in ("tactical", "political"):
        img = MT.tac_map(3.0, 8.0, {"places": ["Kyiv"], "theme": theme, "badge": ""})
        crop = img.convert("L").crop((20, 16, 400, 44))
        assert crop.getextrema()[1] > 180                   # light badge text on a dark plate


def test_sequence_region_then_markers_then_route_then_chips():
    p = {"places": ["Kharkiv", "Kupiansk"], "routes": [{"from": "Kharkiv", "to": "Kupiansk"}], "chips": [{"title": "Note", "sub": "s"}]}
    c = MT._chip_defaults(p)
    g = MT._gather(p)
    assert g["places"][0]["start"] >= 0.8
    assert g["routes"][0]["start"] > g["places"][-1]["start"]
    assert c[0]["start"] > g["routes"][0]["start"] + g["routes"][0]["length"] - 0.3


def test_times_param_overrides_defaults():
    p = {"places": ["Kharkiv", "Kupiansk"], "routes": [{"from": "Kharkiv", "to": "Kupiansk"}], "chips": [{"title": "Note"}],
         "times": {"places": [1.0, 2.5], "routes": [4.0], "chips": [6.0]}}
    g = MT._gather(p)
    assert [x["start"] for x in g["places"]] == [1.0, 2.5] and g["routes"][0]["start"] == 4.0 and MT._chip_defaults(p)[0]["start"] == 6.0
    early = MT.render_info(p, 1.8, 8.0)["labels"]
    late = MT.render_info(p, 3.5, 8.0)["labels"]
    assert len(early) == 1 and len(late) == 2


def test_cached_base_makes_frames_cheap_and_identical_for_same_t():
    import time

    p = {"places": ["Moscow", "Ryazan"]}
    a = MT.tac_map(2.0, 8.0, dict(p))
    t0 = time.time()
    for i in range(6):
        MT.tac_map(2.0 + 0.04 * i, 8.0, dict(p))
    assert (time.time() - t0) / 6 < 0.35
    b = MT.tac_map(2.0, 8.0, dict(p))
    assert list(a.getdata())[::997] == list(b.getdata())[::997]


def test_unknown_place_skipped_and_never_blank():
    img = MT.tac_map(3.0, 8.0, {"places": ["Atlantis"], "chips": []})
    assert img.convert("L").getextrema()[1] > 60 and img.size == (MT.W, MT.H)
