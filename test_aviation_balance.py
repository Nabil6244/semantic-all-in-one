"""Balance director v2 (aviation/balance.py): shares per look against the target bands, no template twice in a row."""

from aviation import balance as BL
from aviation import planner as P


def _scenes(lines, step=7.0, **kw):
    return [dict({"scene_no": i + 1, "text": t, "start": i * step, "end": (i + 1) * step}, **kw) for i, t in enumerate(lines)]


class _Plan:
    def __init__(self, shots):
        self.shots = shots


def test_shares_count_stage_cutaways_as_photos():
    st = {"layer": "stage.lay_stage", "start": 0.0, "end": 20.0, "full_frame": True,
          "params": {"elements": [{"kind": "photo_full", "t0": 5.0, "t1": 9.5}]}}
    sh = BL.shares(_Plan([st, {"kind": "footage", "start": 20.0, "end": 30.0}]), 30.0)
    assert round(sh["photos"], 1) == 4.5 and round(sh["stage"], 1) == 15.5 and sh["footage"] == 10.0


def test_same_template_twice_in_a_row_becomes_the_other_skin():
    a = {"layer": "dossier.lay_icons", "start": 0.0, "end": 5.0, "full_frame": True, "scene": 1, "params": {"count": 26}}
    b = {"layer": "dossier.lay_icons", "start": 5.0, "end": 10.0, "full_frame": True, "scene": 2, "params": {"count": 40}}
    pl = _Plan([a, b])
    sc = _scenes(["Air France ordered 26 aircraft in 2015.", "By 2016 Air France flew 40 aircraft to Asia."], step=5.0)
    rep = BL.apply(pl, sc)
    assert rep["fixed"] and b["layer"] != "dossier.lay_icons" and a["layer"] == "dossier.lay_icons"


def test_every_plan_carries_a_balance_report():
    pl = P.plan(_scenes(["In 1966 Malaysia and Singapore formed one airline together.",
                         "By 1972 the joint airline split into Singapore Airlines and Malaysia Airlines."]))
    assert set(pl.balance["shares"]) >= set(BL.TARGETS) and "out_of_band" in pl.balance
    assert abs(sum(pl.balance["shares"].values()) - 100.0) < 1.5


def test_story_lines_ask_for_archive_clips_when_no_csv_decides():
    from aviation import runner as RN
    lines = ["In 1966 the two governments formed Malaysia-Singapore Airlines, flying Boeing 707s.",
             "Malaysia wanted a domestic network, while Singapore wanted international routes.",
             "By 1972 the joint airline split into Singapore Airlines and Malaysia Airlines.",
             "It was a strange time for everyone."]
    sc = _scenes(lines)
    pl = P.plan(sc)
    RN.request_footage(sc, pl)
    asked = [s for s in sc if s["asset_type"] == "youtube_video"]
    assert asked
    assert "Malaysia-Singapore Airlines" in asked[0]["prompt"] and "1966" in asked[0]["prompt"]
    assert sc[3]["asset_type"] == "none"                                   # names nothing: no search
    csv = _scenes(lines)
    csv[0]["asset_type"] = "none"
    RN.request_footage(csv, pl)
    assert csv[0]["asset_type"] == "none"                                  # the CSV decided: left alone


def test_archive_queries_use_the_name_of_that_year():
    from aviation import runner as RN
    q = RN.archive_queries("In 1963 Singapore Airlines flew Boeing 707s.")
    assert q and "1963" in q[0]
