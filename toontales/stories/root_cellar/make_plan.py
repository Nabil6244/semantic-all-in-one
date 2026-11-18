"""Ch3 Short 'How a Hole in the Yard Keeps Food Cold With No Fridge' (a backyard root cellar).
    python3 toontales/stories/root_cellar/make_plan.py && python3 -m toontales.plan.check toontales/stories/root_cellar/plan.json --fix
"""
import json
from pathlib import Path

CUT = {"at": [2.0, 1.0, -0.7], "dist": 9.0, "yaw": -6, "pitch": 6, "lens": 28}    # house corner, pit, garden
PIT = {"at": [2.3, 1.2, -0.9], "dist": 8.2, "yaw": -4, "pitch": 4, "lens": 30}     # the pit in section + Sam at its edge
IN = {"at": [2.7, 1.3, -1.6], "dist": 3.6, "yaw": -6, "pitch": 3, "lens": 34}      # inside the cellar: crates


def look(base, **kw):
    d = dict(base)
    d.update(kw)
    return d


def B(acts, mark="B"):
    return [{"id": "builder", "mark": mark, "acts": acts}]


TANK = ["tank_floor", "tank_back", "tank_l", "tank_r"]
PIPES = ["pipe_a", "pipe_b", "pipe_c", "pump", "pump_pipe", "water"]
GROUND = ["turf", "plug_soil", "plug_gravel"]
CRATES = [{"m": "ph:wooden_crate_01", "at": a, "s": 0.8, "rot": r, "id": f"crate{i}"} for i, (a, r) in enumerate((
    ([2.0, 1.4, -2.17], 5), ([3.3, 1.5, -2.17], -10), ([2.7, 1.2, -1.62], 20)))]
VENT = [{"m": "@beam", "a": [3.85, 2.0, -0.3], "b": [3.85, 2.0, 0.9], "t": 0.12, "color": [0.32, 0.33, 0.35],
         "rough": 0.4, "metal": 0.6, "id": "vent"}]
PLACES = {
    "yard": {"world": "dio_backyard_tank", "remove": TANK + PIPES + ["lid", "turf2"], "prompt": "Backyard before: lawn, house, garden"},
    "yard_dug": {"world": "dio_backyard_tank", "remove": GROUND + TANK + PIPES + ["lid", "turf2"], "prompt": "Backyard with an open pit"},
    "lined": {"world": "dio_backyard_tank", "remove": GROUND + PIPES + ["lid", "turf2"], "add": CRATES, "prompt": "Pit lined with concrete, crates inside"},
    "garden": {"world": "dio_backyard_tank", "remove": GROUND + PIPES, "add": CRATES + VENT, "prompt": "The hot garden and house beside the hidden cellar"},
    "cellar": {"world": "dio_backyard_tank", "remove": GROUND + PIPES, "add": CRATES + VENT, "prompt": "Finished root cellar under the lawn with a vent"},
}
SHOTS = [
    dict(beat="hook", text="It's a scorching summer day. Under this lawn, the apples are cold.", set="cellar", camera="wide",
         move="push", cast=B([{"do": "wipe", "at": 0.6}], "A"), look=CUT, overlay={"type": "stamp", "text": "COLD"}),
    dict(beat="hook", text="So how does a hole in the yard keep food cold with no fridge?", set="cellar", camera="medium",
         move="pull", cast=B([{"do": "point", "at": 0.2, "params": {"dir": [-0.7, -0.4, -0.6]}}], "A"), look=look(PIT, dist=5.6), overlay={"type": "circle", "text": "NO FRIDGE?"}),
    dict(beat="concept", text="Sam grows far more potatoes and apples than he can eat.", set="yard", camera="medium", move="push",
         cast=B([{"do": "crouch", "at": 0.1}], "A"), look={"at": [6.4, 1.4, 0.7], "dist": 4.2, "yaw": -14, "pitch": 8, "lens": 32}),
    dict(beat="concept", text="In his hot kitchen, they rot within weeks.", set="yard", camera="wide", move="tilt_down",
         cast=B([{"do": "shock", "at": 0.3}], "C"), look={"at": [-3.6, 2.0, 1.2], "dist": 7.0, "yaw": -12, "pitch": 6, "lens": 28},
         overlay={"type": "cross", "text": "ROTTEN"}),
    dict(beat="setup", text="But the ground hides a trick.", set="yard", camera="medium", move="push",
         cast=B([{"do": "look_down", "at": 0.2}]), look={"at": [1.05, 1.0, 0.8], "dist": 4.8, "yaw": -14, "pitch": 6, "lens": 32}),
    dict(beat="setup", text="A couple of meters down, the earth stays cool all year round.", set="yard", camera="wide", move="tilt_down",
         cast=[], look=look(PIT, at=[2.6, 1.2, -1.6]), overlay={"type": "arrow", "text": "ALWAYS COOL"}),
    dict(beat="obstacle", text="Summer sun can't reach it. Winter frost can't either.", set="yard", camera="medium", move="push",
         cast=[], look=look(PIT, dist=6.0), overlay={"type": "label", "text": "STEADY"}),
    dict(beat="con", text="So Sam starts digging, right beside the house.", set="yard", camera="medium", move="push",
         cast=B([{"do": "dig", "at": 0.2, "params": {"face": 90}}]),
         look={"at": [1.05, 1.0, 0.8], "dist": 4.8, "yaw": -14, "pitch": 6, "lens": 32},
         moves=[{"id": "turf", "grow": "up", "from": 1, "to": 0, "t0": 1.0, "t1": 2.4}], sfx=[{"name": "pick", "at": 0.5}]),
    dict(beat="con", text="Down through the soil.", set="yard", camera="wide", move="push",
         cast=B([{"do": "dig", "at": 0.0, "params": {"face": 90}}]), look=PIT,
         moves=[{"id": "turf", "hide": 0.0}, {"id": "plug_soil", "grow": "up", "from": 1, "to": 0, "t0": 0.2, "t1": 1.6}], sfx=[{"name": "pick", "at": 0.3}]),
    dict(beat="con", text="Past the gravel, deeper than he is tall.", set="yard_dug", camera="close", move="tilt_down",
         cast=B([{"do": "dig", "at": 0.0, "params": {"face": 90}}]), look=look(PIT, dist=5.2),
         overlay={"type": "label", "text": "2 METERS"},
         sfx=[{"name": "pick", "at": 0.3}]),
    dict(beat="escalate", text="He lines the pit with concrete so it won't cave in.", set="lined", camera="medium", move="push",
         cast=B([{"do": "carry", "at": 0.0, "params": {"face": 90}}]), look=PIT,
         moves=[{"id": "tank_back", "grow": "up", "from": 0.05, "to": 1, "t0": 0.2, "t1": 2.0},
                {"id": "crate0", "hide": 99}, {"id": "crate1", "hide": 99}, {"id": "crate2", "hide": 99}],
         overlay={"type": "label", "text": "CONCRETE"}),
    dict(beat="escalate", text="In go the crates of potatoes and apples.", set="lined", camera="medium", move="push",
         cast=B([{"do": "carry", "at": 0.0}], "B"), look=IN, moves=[{"id": "crate0", "show": 0.4}, {"id": "crate1", "show": 1.0}, {"id": "crate2", "show": 1.6}],
         sfx=[{"name": "thud", "at": 0.5}, {"name": "thud", "at": 1.1}]),
    dict(beat="escalate", text="But an open pit isn't cold enough.", set="lined", camera="wide", move="push",
         cast=B([{"do": "shock", "at": 0.3}], "A"), look=CUT, overlay={"type": "stamp", "text": "TOO WARM"}, freeze="WAIT..."),
    dict(beat="twist", text="So he buries it. A concrete lid, then soil and grass on top.", set="cellar", camera="medium", move="tilt_down",
         cast=B([{"do": "dig", "at": 0.2, "params": {"face": 90}}]), look=PIT,
         moves=[{"id": "lid", "show": 0.4}, {"id": "turf2", "show": 1.6}, {"id": "vent", "hide": 99}], sfx=[{"name": "thud", "at": 0.5}]),
    dict(beat="twist", text="The earth on top works like a thick blanket.", set="cellar", camera="wide", move="push",
         cast=[], look=look(CUT, at=[2.7, 1.2, -0.4]), moves=[{"id": "vent", "hide": 99}], overlay={"type": "arrow", "text": "EARTH BLANKET"}),
    dict(beat="twist", text="Then one last part: a pipe sticking up out of the lawn.", set="cellar", camera="medium", move="tilt_up",
         cast=B([{"do": "drill", "at": 0.1, "params": {"face": 90}}], "A"), look=look(PIT, at=[3.8, 1.6, 0.2], dist=4.6),
         moves=[{"id": "vent", "grow": "up", "from": 0.1, "to": 1, "t0": 0.4, "t1": 2.0}]),
    dict(beat="twist", text="Fruit breathes out warm, damp air. The pipe lets it escape.", set="cellar", camera="close", move="push",
         cast=[], look=look(IN, at=[3.4, 1.6, -0.6], dist=3.2), overlay={"type": "arrow", "text": "VENT"}, sfx=[{"name": "whoosh", "at": 0.4}]),
    dict(beat="payoff", text="Then the heatwave arrives.", set="garden", camera="wide", move="push",
         cast=B([{"do": "wipe", "at": 0.2}], "A"), look=CUT, overlay={"type": "chalk", "text": "HEATWAVE"}),
    dict(beat="payoff", text="The lawn bakes. The kitchen is an oven.", set="garden", camera="medium", move="pan_l",
         cast=B([{"do": "look", "at": 0.1, "params": {"yaw": 60, "pitch": 10}}], "C"),
         look={"at": [-3.6, 2.0, 1.2], "dist": 6.0, "yaw": -12, "pitch": 6, "lens": 28}),
    dict(beat="payoff", text="Down below, the crates stay cool.", set="cellar", camera="medium", move="push", cast=[], look=IN,
         overlay={"type": "stamp", "text": "COOL"}),
    dict(beat="payoff", text="Apples that would rot in days now last for months.", set="cellar", camera="close", move="push",
         cast=B([{"do": "nod", "at": 0.3}], "B"), look=look(IN, dist=2.6), overlay={"type": "label", "text": "MONTHS"}),
    dict(beat="payoff", text="And in winter, the same earth keeps them from freezing.", set="garden", camera="wide", move="drift",
         cast=B([{"do": "nod", "at": 0.6}], "A"), look=look(PIT, dist=7.0), overlay={"type": "arrow", "text": "NO FROST"}),
    dict(beat="payoff", text="That's how a hole in the yard keeps food cold with no fridge.", set="cellar", camera="wide", move="pull",
         cast=B([{"do": "cheer", "at": 0.3}], "A"), look=CUT),
]


def main():
    for i, s in enumerate(SHOTS, 1):
        s.setdefault("speaker", "narrator")
        for k, v in (("cast", []), ("props", []), ("sfx", []), ("transition", "cut")):
            s.setdefault(k, v)
        s["id"] = f"s{i:02d}"
    plan = {"id": "root_cellar", "title": "How a Hole in the Yard Keeps Food Cold With No Fridge",
            "topic": "how a backyard root cellar works: steady ground temperature, concrete lining, earth cover, a vent pipe",
            "hook_title": "COLD APPLES IN A HEATWAVE?",
            "keywords": ["cold", "cellar", "earth", "apples", "potatoes", "vent", "lid", "summer", "winter", "crates"],
            "cast": ["builder"], "channel": "channel3",
            "sources": ["https://en.wikipedia.org/wiki/Root_cellar", "https://en.wikipedia.org/wiki/Geothermal_gradient"],
            "places": PLACES, "shots": SHOTS}
    out = Path(__file__).with_name("plan.json")
    out.write_text(json.dumps(plan, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
