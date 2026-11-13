"""A business script that tells no flight still gets the real map on its place lines (routes, regions, networks), not on its
'runway' / 'hub' strategy lines; history route lines keep the sticker stage."""
from aviation import planner as P, router as R

LINES = [
    "Portugal's cabinet chose Lufthansa in 2026.",
    "Its first commercial flight, in 1946, went from Lisbon to Madrid.",
    "Lisbon is about to become Lufthansa's next fortress hub.",
    "Instead of Asia, its strength is the South Atlantic, plus a growing set of routes to the United States.",
    "The buyer must keep serving Lisbon, Porto, Faro, the Azores and Madeira.",
    "It is the runway.",
    "Lisbon is a small hub with a big map.",
]


def _scenes():
    return [{"scene_no": i + 1, "text": t, "start": i * 5.0, "end": i * 5.0 + 5.0} for i, t in enumerate(LINES)]


def test_regions_longest_name_and_negation():
    got = R.region_airports("Instead of Asia, its strength is the South Atlantic and North America")
    assert "SIN" not in got and "GIG" in got and "ORD" in got


def test_place_lines_get_the_map_in_a_no_flight_script():
    cls = R.route_script(LINES)
    assert not R.has_flight_story(cls)
    modes = [c.mode for c in cls]
    assert modes[1] != "flight"                      # 1946: history is not a map line
    assert modes[2] != "flight"                      # 'hub' alone is a strategy line
    assert modes[3] == modes[4] == modes[6] == "flight"
    assert modes[5] != "flight"                      # a neutral line is not pulled onto the map


def test_planner_draws_network_from_the_hub():
    rows = [{"airline": "TAP"} for _ in LINES]
    plan = P.plan(_scenes(), rows, retention=False)
    maps = [s for s in plan.shots if s.get("layer") == "flightmap.lay_flight_map"]
    assert maps
    legs = {(lg["from"], lg["to"]) for s in maps for lg in s["params"].get("legs", [])}
    assert ("LIS", "GIG") in legs and ("LIS", "OPO") in legs and ("LIS", "FNC") in legs
    assert not any(a == "SIN" or b == "SIN" for a, b in legs)


def test_csv_map_mode_and_present_day_routes_row():
    rows = [{"airline": "TAP"} for _ in LINES]
    rows[2] = {"airline": "TAP", "mode": "map"}
    rows[1] = {"airline": "TAP", "mode": "story", "graphic": "routes"}      # history routes row stays a stage card
    plan = P.plan(_scenes(), rows, retention=False)
    assert plan.modes[2] == "flight" and plan.modes[1] == "story"
