from types import SimpleNamespace as N

from explainer import csv_hints
from explainer.ui_options import is_explainer_plan


def _plan():
    mk = lambda i, s, e: {"id": i, "mode": "footage", "start": s, "end": e, "footage": {"clips": [{"asset": f"/p/hybrid/explainer/{i}.mp4"}]}}
    return {"beats": [mk("b1", 0, 4), mk("b2", 4, 8), mk("b3", 8, 12), mk("b4", 12, 16)]}


def test_apply_replaces_only_beats_inside_the_span():
    plan = _plan()
    hints = {"spans": [{"start": 4.0, "end": 12.0, "clips": [{"asset": "stock_video:ships"}, {"asset": "stock_video:port"}]}]}
    notes = csv_hints.apply(plan, hints)
    assets = [b["footage"]["clips"][0]["asset"] for b in plan["beats"]]
    assert assets == ["/p/hybrid/explainer/b1.mp4", "stock_video:ships", "stock_video:port", "/p/hybrid/explainer/b4.mp4"]
    assert notes and is_explainer_plan(N(beats=[N(clips=[N(asset=assets[0])])]))


def test_span_without_a_beat_is_skipped_not_fatal():
    plan = _plan()
    assert "skipped" in csv_hints.apply(plan, {"spans": [{"start": 50, "end": 60, "clips": [{"asset": "stock_video:x"}]}]})[0]


def test_read_takes_footage_spans_and_place_names(monkeypatch):
    beat = lambda mode, s, e, clips, place: N(mode=mode, start=s, end=e, clips=[N(asset=c, reason="") for c in clips], cam_place=place, camera=[])
    plan = N(beats=[beat("map", 0, 4, [], "Egypt"), beat("footage", 4, 9, ["stock_video:nile"], ""), beat("map", 9, 12, [], "30.1,31.2")])
    monkeypatch.setattr("hybrid.beat_csv.is_beat_csv", lambda t: True)
    monkeypatch.setattr("hybrid.beat_csv.import_beats", lambda t, w, d: N(plan=plan, notes=[]))
    got = csv_hints.read("x", [], 12.0)
    assert got["places"] == ["Egypt"] and got["spans"] == [{"start": 4.0, "end": 9.0, "clips": [{"asset": "stock_video:nile", "reason": "from the loaded CSV"}]}]


from unittest_adopt import adopt
adopt(globals())
