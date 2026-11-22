"""Ch3 Short 'How a Backyard Becomes a Tornado Shelter' (an underground concrete safe room).
    python3 toontales/stories/storm_shelter/make_plan.py && python3 -m toontales.plan.check toontales/stories/storm_shelter/plan.json --fix
"""
import json
from pathlib import Path

CUT = {"at": [2.0, 1.0, -0.7], "dist": 9.0, "yaw": -6, "pitch": 6, "lens": 28}    # house corner, pit, garden
PIT = {"at": [2.3, 1.2, -0.9], "dist": 8.2, "yaw": -4, "pitch": 4, "lens": 30}     # the pit in section + Sam at its edge
IN = {"at": [2.7, 1.3, -1.6], "dist": 3.6, "yaw": -6, "pitch": 3, "lens": 34}      # inside the shelter
TOP = {"at": [3.6, 1.0, 0.2], "dist": 4.4, "yaw": -12, "pitch": 10, "lens": 32}    # the hatch in the lawn


def look(base, **kw):
    d = dict(base)
    d.update(kw)
    return d


def B(acts, mark="B"):
    return [{"id": "builder", "mark": mark, "acts": acts}]


TANK = ["tank_floor", "tank_back", "tank_l", "tank_r"]
PIPES = ["pipe_a", "pipe_b", "pipe_c", "pump", "pump_pipe", "water"]
GROUND = ["turf", "plug_soil", "plug_gravel"]
STEEL = {"color": [0.34, 0.36, 0.38], "rough": 0.35, "metal": 0.8}
CRATES = [{"m": "ph:wooden_crate_01", "at": a, "s": 0.7, "rot": r, "id": f"crate{i}"} for i, (a, r) in enumerate((
    ([1.9, 1.5, -2.17], 5), ([2.6, 1.7, -2.17], -10)))]
BENCH = [{"m": "@box", "at": [2.2, 2.2, -1.95], "size": [1.6, 0.4, 0.08], "mat": "planks", "id": "bench"}]
LADDER = [{"m": "ph:wooden_ladder", "at": [3.75, 1.2, -2.17], "s": 1.0, "rot": 0, "id": "ladder"}]
HATCH = [{"m": "@box", "at": [3.6, 1.0, 0.03], "size": [0.8, 0.8, 0.06], **STEEL, "id": "hatch"}]
VENT = [{"m": "@beam", "a": [1.6, 2.0, -0.3], "b": [1.6, 2.0, 0.8], "t": 0.1, "color": [0.32, 0.33, 0.35],
         "rough": 0.4, "metal": 0.6, "id": "vent"}]
INSIDE = CRATES + BENCH + LADDER
PLACES = {
    "yard": {"world": "dio_backyard_tank", "remove": TANK + PIPES + ["lid", "turf2"], "prompt": "Backyard before: lawn, house, garden"},
    "dug": {"world": "dio_backyard_tank", "remove": GROUND + TANK + PIPES + ["lid", "turf2"], "prompt": "Backyard with an open pit"},
    "shell": {"world": "dio_backyard_tank", "remove": GROUND + PIPES + ["lid", "turf2"], "add": INSIDE,
              "prompt": "Concrete walls in the pit, bench, ladder, supplies"},
    "shelter": {"world": "dio_backyard_tank", "remove": GROUND + PIPES, "add": INSIDE + HATCH + VENT,
                "prompt": "Finished underground shelter under the lawn: concrete roof, steel hatch, air vent"},
}
PLACES["storm"] = dict(PLACES["shelter"], prompt="The finished shelter during the storm")
SHOTS = [
    dict(beat="hook", text="A tornado is coming. Sam runs into the backyard and vanishes into the lawn.", set="shelter", camera="wide",
         move="push", cast=B([{"do": "walk", "at": 0.2, "params": {"to": [-1.5, 0.0]}}], "A"), look=CUT,
         overlay={"type": "stamp", "text": "TORNADO"}, sfx=[{"name": "whoosh", "at": 0.3}]),
    dict(beat="hook", text="So how does a hole in the yard beat a tornado?", set="shelter", camera="medium",
         move="pull", cast=B([{"do": "point", "at": 0.2, "params": {"dir": [-0.7, -0.4, -0.6]}}], "A"), look=TOP,
         overlay={"type": "circle", "text": "IN HERE?"}),
    dict(beat="concept", text="The strongest tornadoes spin faster than two hundred miles an hour.", set="yard", camera="wide",
         move="push", cast=B([{"do": "shock", "at": 0.3}], "C"), look=CUT, overlay={"type": "chalk", "text": "200+ MPH"}),
    dict(beat="concept", text="They can rip a house right off its floor.", set="yard", camera="medium", move="tilt_down",
         cast=[], look={"at": [-3.6, 2.0, 1.2], "dist": 7.0, "yaw": -12, "pitch": 6, "lens": 28}, overlay={"type": "arrow", "text": "WHOOSH"}),
    dict(beat="setup", text="Most injuries come from flying junk, not the wind itself.", set="yard", camera="medium", move="push",
         cast=B([{"do": "look", "at": 0.2, "params": {"yaw": 50, "pitch": 30}}], "A"),
         look={"at": [5.0, 1.3, 0.9], "dist": 4.6, "yaw": -14, "pitch": 6, "lens": 32}, overlay={"type": "label", "text": "DEBRIS"}),
    dict(beat="setup", text="But the safest place is underground.", set="yard", camera="wide", move="tilt_down",
         cast=[], look=look(PIT, at=[2.6, 1.2, -1.6]), overlay={"type": "arrow", "text": "SAFE"}),
    dict(beat="con", text="So Sam digs, right beside the house.", set="yard", camera="medium", move="push",
         cast=B([{"do": "dig", "at": 0.2, "params": {"face": 90}}]),
         look={"at": [1.05, 1.0, 0.8], "dist": 4.8, "yaw": -14, "pitch": 6, "lens": 32},
         moves=[{"id": "turf", "grow": "up", "from": 1, "to": 0, "t0": 1.0, "t1": 2.4}], sfx=[{"name": "pick", "at": 0.5}]),
    dict(beat="con", text="Down through the soil.", set="yard", camera="wide", move="push",
         cast=B([{"do": "dig", "at": 0.0, "params": {"face": 90}}]), look=PIT,
         moves=[{"id": "turf", "hide": 0.0}, {"id": "plug_soil", "grow": "up", "from": 1, "to": 0, "t0": 0.2, "t1": 1.6}],
         sfx=[{"name": "pick", "at": 0.3}]),
    dict(beat="con", text="Past the gravel, deeper than he is tall.", set="dug", camera="close", move="tilt_down",
         cast=B([{"do": "dig", "at": 0.0, "params": {"face": 90}}]), look=look(PIT, dist=5.2),
         overlay={"type": "label", "text": "2 METERS"}, sfx=[{"name": "pick", "at": 0.3}]),
    dict(beat="escalate", text="Then thick concrete walls, packed with steel bars.", set="shell", camera="medium", move="push",
         cast=B([{"do": "carry", "at": 0.0, "params": {"face": 90}}]), look=PIT,
         moves=[{"id": "tank_back", "grow": "up", "from": 0.05, "to": 1, "t0": 0.2, "t1": 2.0},
                {"id": "crate0", "hide": 99}, {"id": "crate1", "hide": 99}, {"id": "bench", "hide": 99}, {"id": "ladder", "hide": 99}],
         overlay={"type": "label", "text": "CONCRETE + STEEL"}),
    dict(beat="escalate", text="Inside, a bench, a ladder and supplies.", set="shell", camera="medium", move="push",
         cast=B([{"do": "carry", "at": 0.0}], "B"), look=IN,
         moves=[{"id": "bench", "show": 0.3}, {"id": "ladder", "show": 0.8}, {"id": "crate0", "show": 1.2}, {"id": "crate1", "show": 1.6}],
         sfx=[{"name": "thud", "at": 0.5}, {"name": "thud", "at": 1.3}]),
    dict(beat="escalate", text="Water, flashlights, a radio.", set="shell", camera="close", move="push", cast=[],
         look=look(IN, at=[2.2, 1.6, -1.9], dist=2.4), overlay={"type": "chalk", "text": "WATER + LIGHT + RADIO"}),
    dict(beat="escalate", text="But an open pit is a trap. Debris could fall right in.", set="shell", camera="wide", move="push",
         cast=B([{"do": "shock", "at": 0.3}], "A"), look=CUT, overlay={"type": "stamp", "text": "OPEN TOP"}, freeze="WAIT..."),
    dict(beat="twist", text="So he pours a concrete roof, then soil and grass on top.", set="shelter", camera="medium", move="tilt_down",
         cast=B([{"do": "dig", "at": 0.2, "params": {"face": 90}}]), look=PIT,
         moves=[{"id": "lid", "show": 0.4}, {"id": "turf2", "show": 1.6}, {"id": "hatch", "hide": 99}, {"id": "vent", "hide": 99}],
         sfx=[{"name": "thud", "at": 0.5}]),
    dict(beat="twist", text="The way in is a steel hatch, bolted from the inside.", set="shelter", camera="close", move="push",
         cast=B([{"do": "hammer", "at": 0.1, "params": {"face": 90}}], "A"), look=TOP,
         moves=[{"id": "hatch", "show": 0.5}], sfx=[{"name": "thud", "at": 0.6}, {"name": "thud", "at": 1.2}]),
    dict(beat="twist", text="Shelters are tested with planks fired at 100 mph.", set="shelter",
         camera="medium", move="crash_zoom", cast=[], look=look(TOP, dist=3.2), overlay={"type": "chalk", "text": "100 MPH TEST"}),
    dict(beat="twist", text="Last, a pipe so fresh air can get in.", set="shelter", camera="medium", move="tilt_up",
         cast=B([{"do": "drill", "at": 0.1, "params": {"face": 90}}], "B"), look=look(PIT, at=[1.6, 1.8, 0.2], dist=4.6),
         moves=[{"id": "vent", "grow": "up", "from": 0.1, "to": 1, "t0": 0.4, "t1": 2.0}]),
    dict(beat="payoff", text="Then the sirens go off.", set="storm", camera="wide", move="push",
         cast=B([{"do": "look", "at": 0.2, "params": {"yaw": 40, "pitch": 30}}], "A"), look=CUT,
         overlay={"type": "stamp", "text": "SIRENS"}, sfx=[{"name": "whoosh", "at": 0.2}]),
    dict(beat="payoff", text="Sam climbs down and bolts the hatch.", set="shelter", camera="medium", move="tilt_down",
         cast=B([{"do": "climb", "at": 0.2, "params": {"up": -1.8}}], "A"), look=look(IN, at=[3.6, 1.2, -1.0], dist=4.0)),
    dict(beat="payoff", text="Up top, the wind howls and junk flies past.", set="storm", camera="wide", move="pan_l", cast=[],
         look=look(CUT, at=[0.0, 2.0, 0.4]), overlay={"type": "arrow", "text": "DEBRIS"}, sfx=[{"name": "whoosh", "at": 0.2}, {"name": "thud", "at": 1.4}]),
    dict(beat="payoff", text="Down below, under a metre of concrete and earth, he waits it out.", set="shelter", camera="medium", move="push",
         cast=B([{"do": "nod", "at": 0.3}], "B"), look=IN, overlay={"type": "stamp", "text": "SAFE"}),
    dict(beat="payoff", text="That's how a backyard becomes a tornado shelter.", set="shelter", camera="wide", move="pull",
         cast=B([{"do": "cheer", "at": 0.3}], "A"), look=CUT),
]


def main():
    for i, s in enumerate(SHOTS, 1):
        s.setdefault("speaker", "narrator")
        for k, v in (("cast", []), ("props", []), ("sfx", []), ("transition", "cut")):
            s.setdefault(k, v)
        s["id"] = f"s{i:02d}"
    plan = {"id": "storm_shelter", "title": "How a Backyard Becomes a Tornado Shelter",
            "topic": "how an underground tornado shelter works: below-ground pit, reinforced concrete, buried roof, steel hatch, debris testing, air vent",
            "hook_title": "HE VANISHED INTO THE LAWN?",
            "keywords": ["tornado", "shelter", "concrete", "steel", "hatch", "debris", "underground", "vent", "safe", "sirens"],
            "cast": ["builder"], "channel": "channel3",
            "sources": ["https://en.wikipedia.org/wiki/Storm_cellar", "https://www.fema.gov/emergency-managers/risk-management/safe-rooms"],
            "places": PLACES, "shots": SHOTS}
    out = Path(__file__).with_name("plan.json")
    out.write_text(json.dumps(plan, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
