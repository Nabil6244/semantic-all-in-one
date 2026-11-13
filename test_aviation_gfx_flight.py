import os

import pytest
from PIL import Image

from aviation import gfx_flight as G

DUR = 6.0


def _is_card(im):
    return im is not None and im.mode == "RGBA" and im.size == (1280, 720)


def _count(im, pred):
    return sum(1 for px in im.convert("RGB").getdata() if pred(px))


def _yellow(px):
    return px[0] > 235 and px[1] > 215 and px[2] < 200


def _black(px):
    return px[0] < 6 and px[1] < 6 and px[2] < 6


def _photo(tmp_path):
    p = tmp_path / "p.png"
    Image.new("RGB", (400, 300), (30, 120, 200)).save(p)
    return str(p)


CASES = {
    "instrument": (G.lay_instrument, {"fob": 460, "warnings": ["FUEL L+R PUMP LO PR"]}),
    "speed": (G.lay_speed_tape, {"speed": 185, "target": 145, "tag": "WINDSHEAR", "delta": "40 KT"}),
    "report": (G.lay_report, {"title": "Final report", "lines": ["The crew lost speed on approach.", "Captain John Smith disagreed."],
                              "highlight": [0], "redact": ["John Smith"], "source": "AAIB"}),
}


@pytest.mark.parametrize("fn", [G.lay_instrument, G.lay_pip, G.lay_speed_tape, G.lay_report])
def test_empty_params_none(fn):
    assert fn(1.0, DUR, {}) is None
    assert fn(1.0, DUR, None) is None


@pytest.mark.parametrize("name", list(CASES))
def test_card_and_animates(name):
    fn, p = CASES[name]
    a, b = fn(0.2, DUR, p), fn(DUR - 0.2, DUR, p)
    assert _is_card(a) and _is_card(b)
    assert a.tobytes() != b.tobytes()


def test_pip_animates_and_missing(tmp_path):
    p = {"image": _photo(tmp_path), "x": 400, "y": 300, "caption": "Hail damage", "year": "2020"}
    a, b = G.lay_pip(0.2, DUR, p), G.lay_pip(DUR - 0.2, DUR, p)
    assert _is_card(a) and _is_card(b) and a.tobytes() != b.tobytes()
    assert G.lay_pip(1.0, DUR, dict(p, image=str(tmp_path / "nope.png"))) is None
    bad = tmp_path / "bad.png"
    bad.write_text("not an image")
    assert G.lay_pip(1.0, DUR, dict(p, image=str(bad))) is None
    assert _is_card(G.lay_pip(1.0, DUR, dict(p, image=Image.new("RGB", (50, 50), "red"))))


def test_instrument_warning_only_and_blink():
    p = {"warnings": ["FUEL L+R PUMP LO PR"]}
    assert _is_card(G.lay_instrument(1.0, DUR, p))
    on, off = G.lay_instrument(0.45, DUR, {"fob": 460, "warnings": ["X"]}), G.lay_instrument(0.95, DUR, {"fob": 460, "warnings": ["X"]})
    assert on.tobytes() != off.tobytes()


def test_report_highlight_colour():
    fn, p = CASES["report"]
    plain = dict(p, highlight=[])
    assert _count(fn(DUR - 0.2, DUR, p), _yellow) > _count(fn(DUR - 0.2, DUR, plain), _yellow) + 500


def test_report_redaction_black():
    fn, p = CASES["report"]
    with_r = _count(fn(DUR - 0.2, DUR, p), _black)
    without = _count(fn(DUR - 0.2, DUR, dict(p, redact=[])), _black)
    assert with_r > without + 300


def test_report_two_pages_and_page_image(tmp_path):
    lines = ["word " * 40 for _ in range(14)]
    im = G.lay_report(DUR - 0.2, DUR, {"title": "T", "lines": lines})
    assert _is_card(im)
    pi = G.lay_report(1.0, DUR, {"page_image": _photo(tmp_path)})
    assert _is_card(pi)


def test_helpers():
    assert G.fob_at(0, DUR, 460) == 460
    assert G.fob_at(DUR, DUR, 460) < 460
    assert G.fob_at(DUR, DUR, 460) >= 450
    assert G.speed_at(0, DUR, 185, 145) == 185
    assert abs(G.speed_at(DUR, DUR, 185, 145) - 145) < 0.01
    ticks = G.tape_ticks(185, half=20, step=10)
    assert [v for v, _ in ticks] == [170, 180, 190, 200]
    assert [o for _, o in ticks] == [-15, -5, 5, 15]
    assert G.redact_spans("Captain John Smith saw Smith", ["smith", "john smith"]) == [(8, 18), (23, 28)]
    assert G.redact_spans("abc", ["", "zz"]) == []
    assert G.highlight_indexes(["a", "Bee", "c"], [0, "bee", 9, "none"]) == [0, 1]
    assert G.blink(0.1) and not G.blink(0.5)
