"""Fixes from the TAP / Lufthansa render review: the label's own percent on a big-number card, a map camera that never stops."""
from aviation import flightmap as F
from aviation import planner as P
from aviation import router as R


def test_big_number_takes_the_labels_own_percent():
    c = R.classify("TAP carried a record 8.2 million passengers, up 4.2 percent, with operating revenue up 4.3 percent.")
    big = [p for n, p in P._air_graphics(c, {}) if n == "gfx_air.lay_big_number"]
    assert big and big[0]["label"] == "REVENUE" and big[0]["value"] == 4.3


def test_map_camera_keeps_moving_at_a_calm_time_based_pace():
    zs = [F._drift(t)[0] for t in (0.0, 2.0, 4.0, 7.0, 60.0)]
    assert zs[0] == 1.0 and zs[1] > zs[2] > zs[3]            # closer every second, the same pace on a 7 s or a 60 s map
    assert 1.0 - zs[3] > 0.05                                 # visibly closer after 7 s (was ~0.5 %)
    assert zs[4] >= 1.0 - F.DRIFT_MAX - 1e-9                  # capped: a route's far end never leaves the frame


def test_fallback_sticker_beat_gets_the_films_own_picture(tmp_path):
    from aviation import story as ST
    img = tmp_path / "045.png"
    img.write_bytes(b"x")
    scenes = [{"scene_no": 43, "text": "Lisbon links Brazil and Africa."},
              {"scene_no": 44, "text": "Now think about what a fortress hub is."},
              {"scene_no": 45, "text": "One airline controls most of the flights.", "footage": str(tmp_path / "045.still.mp4")}]
    assert ST.film_still(scenes, 43) == str(img)                         # a modern line: a picture up to 2 lines away
    st = ST.fallback_stage(scenes[0]["text"], 5.0, backdrop=ST.film_still(scenes, 43))
    assert any(e["kind"] == "backdrop" for e in st["elements"])          # never a sticker on plain black
    old = [{"scene_no": 1, "text": "In 1946 TAP flew a DC-3 to Madrid."}, scenes[2]]
    assert ST.film_still(old, 1) == ""                                   # a history line never borrows a modern picture


def test_cards_hold_five_seconds_at_most():
    from aviation import planner as P
    assert P.CARD_HOLD_S == 5.0
    scenes = [{"scene_no": 1, "text": "TAP lost 99.2 million euros in the first half of this year, 40 percent more than a year earlier.",
               "start": 0.0, "end": 12.0}]
    plan = P.plan(scenes, [{"graphic": "dossier", "mode": "numbers"}])
    cards = [s for s in plan.shots if s.get("full_frame") and str(s.get("layer") or "").startswith(("dossier.", "gfx_air.", "cards."))]
    assert cards and all(s["end"] - s["start"] <= 5.0 + 1e-6 for s in cards)


def test_employees_are_owners_of_their_own_not_the_airline():
    from aviation import story_relations as SR
    o = SR.owners_from("Portugal 50.1% / Lufthansa 44.9% / TAP employees 5%")
    assert o[2]["name"] == "TAP employees" and o[2].get("people") and "airline" not in o[2]


def test_a_stage_with_only_its_blurred_backdrop_left_cuts_to_footage():
    from aviation import planner as P
    out = P.Plan(modes=["story", "story"])
    out.shots = [{"layer": "stage.lay_stage", "start": 0.0, "end": 9.0, "scene": 1, "full_frame": True,
                  "params": {"elements": [{"kind": "backdrop", "t0": 0.0, "t1": None},
                                          {"kind": "big_type", "t0": 0.0, "t1": 2.2},
                                          {"kind": "hand_flag", "t0": 8.0, "t1": None}]}}]
    scenes = [{"scene_no": 1, "text": "Yet it will run the airline day to day.", "start": 0.0, "end": 3.0},
              {"scene_no": 2, "text": "The decree allows the state to sell the rest.", "start": 3.0, "end": 9.0}]
    cls = [P.R.classify(s["text"]) for s in scenes]
    P._cap_holds(out, scenes, cls, None)
    foot = [s for s in out.shots if s.get("kind") == "footage"]
    assert foot and min(s["start"] for s in foot) <= 2.3 and max(s["end"] for s in foot) >= 7.9   # the blurred-only gap is footage
