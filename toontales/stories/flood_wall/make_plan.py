"""Ch3 Short 'How a River House Stays Dry When the River Rises' (original topic).
    python3 toontales/stories/flood_wall/make_plan.py && python3 -m toontales.plan.check toontales/stories/flood_wall/plan.json --fix
"""
import json
from pathlib import Path

WIDE = {"at": [2.4, 2.0, 0.4], "dist": 12.5, "yaw": -6, "pitch": 6, "lens": 28}     # house + bank + river in section
EDGE = {"at": [4.4, 2.0, 0.2], "dist": 7.0, "yaw": -8, "pitch": 5, "lens": 30}      # the bank edge where the wall goes
ROOM = {"at": [0.0, 2.4, 1.5], "dist": 6.2, "yaw": -6, "pitch": 4, "lens": 30}


def look(base, **kw):
    d = dict(base)
    d.update(kw)
    return d


def B(acts, mark="enter_r"):
    return [{"id": "builder", "mark": mark, "acts": acts}]


WALL = {"m": "@box", "at": [4.55, 2.0, -1.4], "size": [0.35, 9.0, 3.2], "mat": "concrete", "id": "fwall"}
FOOT = {"m": "@box", "at": [4.1, 2.0, -0.9], "size": [0.9, 9.0, 0.5], "mat": "concrete", "id": "footing"}
BAGS = [{"m": "@box", "at": [-0.2 + 0.45 * i, 0.15, 0.6], "size": [0.42, 0.3, 0.18], "mat": "sand", "tint": [0.75, 0.66, 0.45],
         "id": f"bag{i}"} for i in range(3)]
DRAIN = [{"m": "@beam", "a": [2.6, 2.0, -0.4], "b": [4.6, 2.0, -0.4], "t": 0.14, "mat": "metal", "id": "drain"},
         {"m": "@box", "at": [4.78, 2.0, -0.52], "size": [0.06, 0.3, 0.26], "mat": "metal", "id": "flap"}]
PUMP = [{"m": "@box", "at": [2.4, 3.4, 0.6], "size": [0.4, 0.4, 0.5], "mat": "metal", "tint": [0.2, 0.4, 0.9], "id": "pump"}]
PLACES = {
    "home": {"world": "dio_riverside_house", "prompt": "A riverside house before: river low"},
    "dig": {"world": "dio_riverside_house", "add": [FOOT], "prompt": "A trench dug along the river bank"},
    "walled": {"world": "dio_riverside_house", "add": [FOOT, WALL], "prompt": "A concrete flood wall along the bank"},
    "fitted": {"world": "dio_riverside_house", "add": [FOOT, WALL] + DRAIN + PUMP, "prompt": "Wall, drain flap and pump fitted"},
    "ready": {"world": "dio_riverside_house", "add": [FOOT, WALL] + BAGS + DRAIN + PUMP,
              "prompt": "Finished flood-proof house: wall, drain flap, pump, sandbags"},
}
LOW = [{"id": "river", "level_from": 0.9, "level_to": 0.9, "t0": 0, "t1": 0.05}]
HIGH = [{"id": "river", "level_from": 2.7, "level_to": 2.7, "t0": 0, "t1": 0.05}]

SHOTS = [
    dict(beat="hook", text="This river just rose higher than the yard. The house is still dry.", set="ready", camera="wide",
         move="push", cast=B([{"do": "cheer", "at": 0.6}], "A"), look=WIDE, moves=HIGH,
         overlay={"type": "stamp", "text": "BONE DRY"}),
    dict(beat="hook", text="So how does a house beat a flood?", set="ready", camera="medium", move="pull",
         cast=B([{"do": "point", "at": 0.2, "params": {"dir": [0.9, -0.2, 0.0]}}], "A"), look=look(EDGE, dist=6.0), moves=HIGH),
    dict(beat="concept", text="Mia's little house sits right beside a lazy, slow river.", set="home", camera="wide", move="push",
         cast=B([{"do": "idle", "at": 0.0}], "A"), look=WIDE, moves=LOW),
    dict(beat="concept", text="Most days, the water stays far below the bank.", set="home", camera="medium", move="tilt_down",
         cast=[], look=look(EDGE, at=[6.0, 2.0, -0.6]), moves=LOW, overlay={"type": "arrow", "text": "RIVER"}),
    dict(beat="setup", text="But after one rainy spring week, it starts to climb.", set="home", camera="wide", move="push", cast=[],
         look=look(EDGE, dist=8.0), moves=[{"id": "river", "level_from": 0.9, "level_to": 1.35, "t0": 0.2, "t1": 2.8}]),
    dict(beat="setup", text="Right up to the top of the bank.", set="home", camera="medium", move="crash_zoom",
         cast=B([{"do": "shock", "at": 0.2}], "A"), look=look(EDGE, dist=5.0),
         moves=[{"id": "river", "level_from": 1.35, "level_to": 1.4, "t0": 0, "t1": 1.0}]),
    dict(beat="con", text="One more storm, and it pours into the living room.", set="home", camera="medium", move="push",
         cast=B([{"do": "wipe", "at": 0.4}], "B"), look=ROOM, moves=[{"id": "river", "level_from": 1.4, "level_to": 1.4, "t0": 0, "t1": 0.05}],
         overlay={"type": "stamp", "text": "FLOOD RISK"}),
    dict(beat="escalate", text="So the builder digs a deep trench along the bank,", set="dig", camera="medium", move="push",
         cast=B([{"do": "dig", "at": 0.2, "params": {"face": 90}}]), look=EDGE, moves=LOW + [{"id": "footing", "grow": "up", "t0": 0.4, "t1": 2.4}]),
    dict(beat="escalate", text="and fills it with a heavy concrete footing.", set="dig", camera="wide", move="tilt_down",
         cast=[], look=look(EDGE, at=[4.2, 2.0, -0.8], dist=6.0), moves=LOW, overlay={"type": "arrow", "text": "FOOTING"}),
    dict(beat="escalate", text="On top, a thick concrete wall rises.", set="walled", camera="wide", move="push",
         cast=B([{"do": "carry", "at": 0.0, "params": {"face": 90}}], "C"), look=EDGE,
         moves=LOW + [{"id": "fwall", "grow": "up", "t0": 0.3, "t1": 2.6}]),
    dict(beat="escalate", text="Taller than the worst flood anyone remembers.", set="walled", camera="medium", move="tilt_up",
         cast=B([{"do": "look", "at": 0.1, "params": {"yaw": 60, "pitch": 35}}], "C"), look=look(EDGE, at=[4.5, 2.0, 0.8], dist=5.0), moves=LOW,
         overlay={"type": "stamp", "text": "1.8 M"}),
    dict(beat="obstacle", text="But water is sneaky. It comes back up through the drains.", set="walled", camera="medium", move="push",
         cast=B([{"do": "look_down", "at": 0.1}], "B"), look=look(ROOM, at=[1.4, 2.0, 0.2], dist=5.2), moves=LOW),
    dict(beat="twist", text="So he adds a flap valve on the drain.", set="fitted", camera="medium", move="push",
         cast=B([{"do": "drill", "at": 0.1, "params": {"face": 90}}], "C"), look=look(EDGE, at=[4.6, 2.0, -0.45], dist=4.0),
         moves=LOW + [{"id": "flap", "show": 0.8}]),
    dict(beat="twist", text="Rain can flow out of the yard, but the river can't push back in.", set="fitted", camera="insert", move="push", cast=[],
         look=look(EDGE, at=[4.75, 2.0, -0.5], dist=2.4, lens=40), moves=LOW, overlay={"type": "arrow", "text": "ONE WAY"}),
    dict(beat="twist", text="Then a pump inside, for any water that still seeps through.", set="fitted", camera="medium", move="push",
         cast=B([{"do": "point", "at": 0.3, "params": {"dir": [0.3, 0.6, -0.4]}}], "A"), look=look(ROOM, at=[2.0, 3.0, 0.9], dist=4.4), moves=LOW),
    dict(beat="twist", text="And sandbags at the door, just in case.", set="ready", camera="medium", move="push",
         cast=B([{"do": "carry", "at": 0.0}], "A"), look=look(ROOM, at=[0.3, 0.6, 0.8], dist=4.2), moves=LOW),
    dict(beat="payoff", text="Then the big storm hits.", set="ready", camera="wide", move="push", cast=[], look=WIDE,
         moves=[{"id": "river", "level_from": 0.9, "level_to": 1.9, "t0": 0.2, "t1": 2.2}]),
    dict(beat="payoff", text="The river climbs past the bank, past the yard,", set="ready", camera="wide", move="tilt_up", cast=[],
         look=look(EDGE, dist=7.6), moves=[{"id": "river", "level_from": 1.9, "level_to": 2.7, "t0": 0.1, "t1": 2.8}]),
    dict(beat="payoff", text="and stops dead against the wall.", set="ready", camera="medium", move="crash_zoom", cast=[],
         look=look(EDGE, dist=4.6), moves=HIGH, overlay={"type": "stamp", "text": "HELD"}),
    dict(beat="payoff", text="Inside, the floor stays bone dry.", set="ready", camera="medium", move="push",
         cast=B([{"do": "nod", "at": 0.3}], "A"), look=ROOM, moves=HIGH),
    dict(beat="payoff", text="That's how a river house stays dry when the water rises.", set="ready", camera="wide", move="pull",
         cast=B([{"do": "cheer", "at": 0.3}], "A"), look=WIDE, moves=HIGH),
]


def main():
    for i, s in enumerate(SHOTS, 1):
        s.setdefault("speaker", "narrator")
        for k, v in (("cast", []), ("props", []), ("sfx", []), ("transition", "cut")):
            s.setdefault(k, v)
        s["id"] = f"s{i:02d}"
    plan = {"id": "flood_wall", "title": "How a River House Stays Dry When the River Rises",
            "topic": "flood-proofing a riverside house: concrete flood wall on a footing, flap valve on the drain, pump, sandbags",
            "hook_title": "THE RIVER IS HIGHER THAN THE YARD?",
            "keywords": ["river", "flood", "wall", "concrete", "drain", "valve", "pump", "dry", "storm", "bank"],
            "cast": ["builder"], "channel": "channel3",
            "sources": ["https://en.wikipedia.org/wiki/Flood_wall", "https://en.wikipedia.org/wiki/Flap_valve"],
            "places": PLACES, "shots": SHOTS}
    out = Path(__file__).with_name("plan.json")
    out.write_text(json.dumps(plan, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
