"""YouTube Studio retention import -> dips -> what was on screen -> tuned limits (aviation/retention_import.py)."""

import json

from aviation import planner as P
from aviation import retention as RT
from aviation import retention_import as RI

LINES = ["In 1966 the two governments formed Malaysia-Singapore Airlines together.",
         "The airline grew every year after that, with more and more passengers.",
         "It added many routes and its staff grew too, year after year.",
         "Then in 1972 the joint airline split into Singapore Airlines and Malaysia Airlines."] * 3


def _scenes(lines, step=10.0):
    return [{"scene_no": i + 1, "text": t, "start": i * step, "end": (i + 1) * step} for i, t in enumerate(lines)]


def _csv(tmp_path, rows, head=("Video position (%)", "Absolute audience retention (%)")):
    p = tmp_path / "ret.csv"
    p.write_text(",".join(head) + "\n" + "\n".join(f"{a},{b}" for a, b in rows), encoding="utf-8")
    return p


def test_read_curve_percent_and_time_columns(tmp_path):
    c = RI.read_curve(_csv(tmp_path, [(0, 100), (50, 60), (100, 40)]), 120.0)
    assert c == [(0.0, 100.0), (60.0, 60.0), (120.0, 40.0)]
    c2 = RI.read_curve(_csv(tmp_path, [("0:00", 1.0), ("1:00", 0.6)], head=("Moment", "Audience retention")), 120.0)
    assert c2 == [(0.0, 100.0), (60.0, 60.0)]


def test_dips_find_the_steep_fall_only():
    curve = [(t, 100 - 0.2 * t) for t in range(0, 120, 2)]
    curve = [(t, r - (8.0 if t >= 70 else 0.0)) for t, r in curve]        # a sudden 8-point loss at ~70 s
    d = RI.dips(curve)
    assert len(d) == 1 and 66 <= d[0]["start"] <= 70 and d[0]["drop"] >= 7


def test_analyze_names_the_picture_and_tune_steps_once(tmp_path):
    sc = _scenes(LINES)
    pl = P.plan(sc)
    curve = [(t, 100 - 0.1 * t) for t in range(0, 120, 2)]
    curve = [(t, r - (6.0 if t >= 56 else 0.0)) for t, r in curve]
    rep = RI.analyze(curve, pl, lim=dict(RI.DEFAULTS))
    assert rep["dips"] and rep["dips"][0]["look"] and rep["dips"][0]["cause"]
    path = tmp_path / "tuning.json"
    rep["drop_by_cause"] = {"stage_idle": 6.0, "card_long": 1.0}
    lim = RI.tune(rep, path)
    assert lim["MAX_SAME_S"] == RI.DEFAULTS["MAX_SAME_S"] - RI.STEP["MAX_SAME_S"]
    assert lim["CARD_MAX"] == RI.DEFAULTS["CARD_MAX"]                       # too small a loss to act on
    for _ in range(20):
        lim = RI.tune(rep, path)
    assert lim["MAX_SAME_S"] == RI.FLOORS["MAX_SAME_S"]                     # never past the floor
    assert RI.limits(path)["MAX_SAME_S"] == RI.FLOORS["MAX_SAME_S"]
    json.loads(path.read_text())


def test_retention_uses_tuned_limits(tmp_path, monkeypatch):
    path = tmp_path / "tuning.json"
    path.write_text(json.dumps({"MAX_SAME_S": 6.0}))
    monkeypatch.setattr(RI, "tuning_path", lambda p=None: path)
    old = RT.MAX_SAME_S
    try:
        P.plan(_scenes(LINES[:4]))
        assert RT.MAX_SAME_S == 6.0
    finally:
        RT.MAX_SAME_S = old
