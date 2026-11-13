"""Thumbnails from the film's own stage pictures and words (aviation/thumbs.py)."""

from PIL import Image

from aviation import planner as P
from aviation import thumbs as TH

LINES = ["So why did one airline become two?",
         "In 1966 the two governments formed Malaysia-Singapore Airlines, flying Boeing 707s.",
         "By 1972 the joint airline split into Singapore Airlines and Malaysia Airlines.",
         "Singapore Airlines flew its first Boeing 747s in 1973."]


def _scenes(lines, step=6.0):
    return [{"scene_no": i + 1, "text": t, "start": i * step, "end": (i + 1) * step} for i, t in enumerate(lines)]


def test_words_are_the_narrations_own():
    w = TH.words(_scenes(LINES))
    assert w == "ONE AIRLINE BECOME TWO?"
    assert w.lower().rstrip("?") in LINES[0].lower()


def test_words_fallback_to_airline_names():
    assert "MALAYSIA-SINGAPORE AIRLINES" in TH.words(_scenes(LINES[1:2]))


def test_picks_use_the_split():
    pk = TH.picks(P.plan(_scenes(LINES)))
    assert pk["card"]["kind"] == "split_tree"
    assert [e["args"]["airline"] for e in pk["pair"]] == ["singapore_airlines", "malaysia_airlines"]
    assert pk["hero"]["args"]["airline"] == "singapore_airlines" and pk["year"] == "1972"


def test_make_three_variants(tmp_path):
    paths = TH.make(P.plan(_scenes(LINES)), _scenes(LINES), tmp_path)
    assert len(paths) == 3
    for p in paths:
        im = Image.open(p)
        assert im.size == (1280, 720)
        assert len(set(im.resize((32, 18)).getdata())) > 20          # a real picture, not a blank frame
