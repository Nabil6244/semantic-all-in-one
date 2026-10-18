"""A shot CSV for another script stops Generate; flash shots join their neighbour; stock searches come from context."""
import re
import pytest
from whatif.app_integration import plan_from, script_match
from whatif.planner import Shot, absorb_short, stock_query
from whatif.shot_csv import PlanError

SPOKEN = ("right now you are moving through the milky way at about 230 kilometres per second faster than any spacecraft humans have built "
          "and yet if you looked at the night sky tonight and again a lifetime from now the stars would look almost exactly the same ").split() * 3


def _words():
    return [[w, i * 0.4, i * 0.4 + 0.3] for i, w in enumerate(SPOKEN)]


def _csv(text):
    return "beat,row,vo_anchor,text\nb1,beat,,\"%s\"\n" % text


def test_other_script_stops_generate():
    other = " ".join(f"Voyager {i} crossed region {i * 7} beyond the planets and sent signal number {i * 3} back toward Earth" for i in range(12))
    assert script_match(_words(), _csv(other))[0] < 0.25
    with pytest.raises(PlanError):
        plan_from(_words(), "", 100.0, "t", _csv(other))


def test_own_script_matches():
    assert script_match(_words(), _csv(" ".join(SPOKEN)))[0] > 0.9


def test_flash_shots_join_neighbour():
    sh = [Shot(id="", start=0, end=5, text="a", kind="image"), Shot(id="", start=5, end=5.5, text="b", kind="image"),
          Shot(id="", start=5.5, end=9, text="c", kind="image")]
    out = absorb_short(sh, [])
    assert [(s.start, s.end) for s in out] == [(0, 5.5), (5.5, 9)] or [(s.start, s.end) for s in out] == [(0, 5), (5, 9)]
    assert min(s.length for s in out) >= 2.0


def test_stock_query_is_context_and_niche():
    q = stock_query(Shot(id="", start=0, end=.5, text="move"), "planets near the sun move fast and planets far from it move slowly")
    assert len(q.split()) >= 5 and re.search(r"planet|sun", q)
    assert "space" in stock_query(Shot(id="", start=0, end=.5, text="because"))
