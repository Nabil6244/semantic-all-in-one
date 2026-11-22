"""Ch3 Short 'How a Backyard Becomes a Swimming Pool' (and why an empty pool can pop out of the ground).
    python3 toontales/stories/plunge_pool/make_plan.py && python3 -m toontales.plan.check toontales/stories/plunge_pool/plan.json --fix
"""
import json
from pathlib import Path

CUT = {"at": [2.0, 1.0, -0.7], "dist": 9.0, "yaw": -6, "pitch": 6, "lens": 28}    # house corner, pit, garden
PIT = {"at": [2.3, 1.2, -0.9], "dist": 8.2, "yaw": -4, "pitch": 4, "lens": 30}     # the pit in section + Sam at its edge
IN = {"at": [2.7, 1.3, -1.6], "dist": 3.6, "yaw": -6, "pitch": 3, "lens": 34}      # inside the pool
DEEP = {"at": [2.7, 1.3, -2.6], "dist": 6.0, "yaw": -4, "pitch": 2, "lens": 30}    # the ground under the pool


def look(base, **kw):
    d = dict(base)
    d.update(kw)
    return d


def B(acts, mark="B"):
    return [{"id": "builder", "mark": mark, "acts": acts}]


TANK = ["tank_floor", "tank_back", "tank_l", "tank_r"]
DOWNPIPE = ["pipe_a", "pipe_b", "pipe_c"]
PUMP = ["pump", "pump_pipe"]
GROUND = ["turf", "plug_soil", "plug_gravel"]
TILE = [{"m": "@box", "at": [2.7, 0.08, -0.22], "size": [3.0, 0.16, 0.12], "color": [0.15, 0.45, 0.75], "rough": 0.2, "id": "coping"}]
LADDER = [{"m": "ph:wooden_ladder", "at": [3.75, 1.2, -2.17], "s": 1.0, "rot": 0, "id": "ladder"}]
VALVE = [{"m": "@box", "at": [2.7, 1.3, -2.2], "size": [0.25, 0.25, 0.06], "color": [0.85, 0.85, 0.85], "rough": 0.3, "metal": 0.7, "id": "valve"}]
FULL = [{"id": "water", "level_from": 1.9, "level_to": 1.9, "t0": 0, "t1": 0.05}]
EMPTY = [{"id": "water", "level_from": 0.001, "level_to": 0.001, "t0": 0, "t1": 0.05}]
PLACES = {
    "yard": {"world": "dio_backyard_tank", "remove": TANK + DOWNPIPE + PUMP + ["water", "lid", "turf2"], "prompt": "Backyard before: lawn, house, garden"},
    "dug": {"world": "dio_backyard_tank", "remove": GROUND + TANK + DOWNPIPE + PUMP + ["water", "lid", "turf2"], "prompt": "Backyard with an open pit"},
    "shell": {"world": "dio_backyard_tank", "remove": GROUND + DOWNPIPE + PUMP + ["lid", "turf2"], "add": TILE + LADDER + VALVE,
              "prompt": "A concrete pool shell in the pit with blue tile edge"},
    "pool": {"world": "dio_backyard_tank", "remove": GROUND + DOWNPIPE + ["lid", "turf2"], "add": TILE + LADDER + VALVE,
             "prompt": "Finished backyard plunge pool with pump"},
}
SHOTS = [
    dict(beat="hook", text="Last spring, this was just a lawn. Now Sam swims in it.", set="pool", camera="wide",
         move="push", cast=B([{"do": "cheer", "at": 0.6}], "A"), look=CUT, moves=FULL, overlay={"type": "stamp", "text": "POOL"}),
    dict(beat="hook", text="But an empty pool can pop right out of the ground. How?", set="pool", camera="medium",
         move="pull", cast=B([{"do": "point", "at": 0.2, "params": {"dir": [-0.7, -0.4, -0.6]}}], "A"), look=look(PIT, dist=5.6),
         moves=FULL, overlay={"type": "circle", "text": "POP?"}),
    dict(beat="concept", text="Sam wants a small, deep pool beside the house.", set="yard", camera="medium", move="push",
         cast=B([{"do": "wipe", "at": 0.2}], "A"), look={"at": [5.0, 1.3, 0.9], "dist": 4.6, "yaw": -14, "pitch": 6, "lens": 32},
         overlay={"type": "label", "text": "PLUNGE POOL"}),
    dict(beat="concept", text="First, the hole.", set="yard", camera="medium", move="push",
         cast=B([{"do": "dig", "at": 0.2, "params": {"face": 90}}]),
         look={"at": [1.05, 1.0, 0.8], "dist": 4.8, "yaw": -14, "pitch": 6, "lens": 32},
         moves=[{"id": "turf", "grow": "up", "from": 1, "to": 0, "t0": 0.6, "t1": 2.0}], sfx=[{"name": "pick", "at": 0.4}]),
    dict(beat="setup", text="Soil out. Gravel out.", set="yard", camera="wide", move="push",
         cast=B([{"do": "dig", "at": 0.0, "params": {"face": 90}}]), look=PIT,
         moves=[{"id": "turf", "hide": 0.0}, {"id": "plug_soil", "grow": "up", "from": 1, "to": 0, "t0": 0.2, "t1": 1.6}],
         sfx=[{"name": "pick", "at": 0.3}]),
    dict(beat="setup", text="Down to the rock, over two meters deep.", set="dug", camera="close", move="tilt_down",
         cast=B([{"do": "dig", "at": 0.0, "params": {"face": 90}}]), look=look(PIT, dist=5.2),
         overlay={"type": "label", "text": "2.3 METERS"}, sfx=[{"name": "pick", "at": 0.3}]),
    dict(beat="setup", text="Then a shell of concrete and steel bars.", set="shell", camera="medium", move="push",
         cast=B([{"do": "carry", "at": 0.0, "params": {"face": 90}}]), look=PIT, moves=EMPTY + [
             {"id": "tank_back", "grow": "up", "from": 0.05, "to": 1, "t0": 0.2, "t1": 2.0}, {"id": "ladder", "hide": 99},
             {"id": "coping", "hide": 99}], overlay={"type": "label", "text": "CONCRETE SHELL"}),
    dict(beat="setup", text="Blue tiles round the edge, and a ladder.", set="shell", camera="medium", move="push",
         cast=B([{"do": "hammer", "at": 0.1, "params": {"face": 90}}], "A"), look=IN, moves=EMPTY + [
             {"id": "coping", "show": 0.4}, {"id": "ladder", "show": 1.2}], sfx=[{"name": "thud", "at": 0.5}]),
    dict(beat="con", text="Now fill it.", set="shell", camera="wide", move="push", cast=B([{"do": "point", "at": 0.2,
         "params": {"dir": [-0.6, 0.2, -0.6]}}], "A"), look=PIT,
         moves=[{"id": "water", "level_from": 0.001, "level_to": 0.8, "t0": 0.2, "t1": 2.0}], sfx=[{"name": "splash", "at": 0.3}]),
    dict(beat="con", text="Up, and up.", set="shell", camera="medium", move="tilt_up", cast=[], look=IN,
         moves=[{"id": "water", "level_from": 0.8, "level_to": 1.9, "t0": 0.1, "t1": 1.6}]),
    dict(beat="con", text="That's about fourteen tonnes of water.", set="pool", camera="medium", move="crash_zoom",
         cast=B([{"do": "shock", "at": 0.2}], "A"), look=look(PIT, dist=6.0), moves=FULL, overlay={"type": "chalk", "text": "14 TONNES"}),
    dict(beat="escalate", text="A pump pulls it through a filter, around and around.", set="pool", camera="medium", move="push",
         cast=B([{"do": "drill", "at": 0.1, "params": {"face": 90}}], "A"), look=look(IN, at=[4.2, 0.6, -0.4], dist=3.6),
         moves=FULL, overlay={"type": "arrow", "text": "PUMP"}),
    dict(beat="escalate", text="Sam jumps in. Perfect.", set="pool", camera="wide", move="push",
         cast=B([{"do": "cheer", "at": 0.3}], "B"), look=CUT, moves=FULL, sfx=[{"name": "splash", "at": 0.6}]),
    dict(beat="escalate", text="But one autumn, he drains it to clean it after a week of rain.", set="shell", camera="medium",
         move="push", cast=B([{"do": "wipe", "at": 0.3}], "A"), look=PIT,
         moves=[{"id": "water", "level_from": 1.9, "level_to": 0.001, "t0": 0.2, "t1": 2.6}], freeze="WAIT..."),
    dict(beat="twist", text="Under the pool, the rain has soaked the ground.", set="shell", camera="wide", move="tilt_down", cast=[],
         look=DEEP, moves=EMPTY, overlay={"type": "label", "text": "WET GROUND"}),
    dict(beat="twist", text="That water pushes up on the shell, like a hand under a boat.", set="shell", camera="medium",
         move="push", cast=[], look=look(DEEP, dist=4.6), moves=EMPTY, overlay={"type": "arrow", "text": "PUSH UP"}),
    dict(beat="twist", text="Full, the pool's weight holds it down. Empty, it can float right up.", set="shell", camera="close",
         move="crash_zoom", cast=[], look=look(IN, dist=3.0), moves=EMPTY, overlay={"type": "stamp", "text": "POP!"}),
    dict(beat="twist", text="Pools have really floated up out of yards like this.", set="shell", camera="wide", move="pull",
         cast=B([{"do": "shock", "at": 0.2}], "A"), look=CUT, moves=EMPTY, overlay={"type": "chalk", "text": "IT HAPPENS"}),
    dict(beat="payoff", text="So the floor hides a small valve.", set="shell", camera="close", move="push", cast=[],
         look=look(IN, at=[2.7, 1.3, -2.1], dist=2.0), moves=EMPTY, overlay={"type": "arrow", "text": "VALVE"}),
    dict(beat="payoff", text="When ground water pushes too hard, it opens and lets the water in.", set="shell", camera="medium",
         move="push", cast=[], look=IN, moves=[{"id": "water", "level_from": 0.001, "level_to": 0.25, "t0": 0.4, "t1": 2.4}],
         overlay={"type": "label", "text": "RELIEF VALVE"}),
    dict(beat="payoff", text="The push evens out, and the pool stays put.", set="pool", camera="medium", move="push",
         cast=B([{"do": "nod", "at": 0.3}], "A"), look=look(PIT, dist=6.0), moves=FULL, overlay={"type": "stamp", "text": "STAYS PUT"}),
    dict(beat="payoff", text="That's how a backyard becomes a pool that never pops.", set="pool", camera="wide", move="pull",
         cast=B([{"do": "cheer", "at": 0.3}], "A"), look=CUT, moves=FULL),
]


def main():
    for i, s in enumerate(SHOTS, 1):
        s.setdefault("speaker", "narrator")
        for k, v in (("cast", []), ("props", []), ("sfx", []), ("transition", "cut")):
            s.setdefault(k, v)
        s["id"] = f"s{i:02d}"
    plan = {"id": "plunge_pool", "title": "How a Backyard Becomes a Swimming Pool",
            "topic": "building an in-ground plunge pool: excavation, concrete shell, pump and filter, buoyancy of an empty pool in wet ground, hydrostatic relief valve",
            "hook_title": "POOLS CAN POP OUT?",
            "keywords": ["pool", "concrete", "water", "tonnes", "pump", "drain", "float", "valve", "rain", "pop"],
            "cast": ["builder"], "channel": "channel3",
            "sources": ["https://en.wikipedia.org/wiki/Swimming_pool", "https://en.wikipedia.org/wiki/Hydrostatic_pressure"],
            "places": PLACES, "shots": SHOTS}
    out = Path(__file__).with_name("plan.json")
    out.write_text(json.dumps(plan, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
