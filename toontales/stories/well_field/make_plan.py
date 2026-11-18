"""Ch3 Short 'How a Hole in a Dry Field Fills Itself With Water' (hand-dug well: water table, stone lining, cover, bucket).
    python3 toontales/stories/well_field/make_plan.py && python3 -m toontales.plan.check toontales/stories/well_field/plan.json --fix
"""
import json
from pathlib import Path

WIDE = {"at": [0.0, 1.0, -2.6], "dist": 13.0, "yaw": -6, "pitch": 6, "lens": 28}    # the whole slice: field, shaft, rock
TOP = {"at": [0.4, 1.0, 0.9], "dist": 6.5, "yaw": -8, "pitch": 7, "lens": 30}       # the well head, frame and Sam
DEEP = {"at": [0.0, 0.4, -6.2], "dist": 5.2, "yaw": -4, "pitch": 3, "lens": 32}     # the bottom of the shaft


def look(base, **kw):
    d = dict(base)
    d.update(kw)
    return d


def B(acts, mark="A"):
    return [{"id": "builder", "mark": mark, "acts": acts}]


PLUG = {"m": "@box", "at": [0.0, 0.0, -7.2], "size": [2.1, 2.1, 7.08], "mat": "soil", "id": "plug"}   # the hole before it is dug
LID = {"m": "@box", "at": [0.0, 0.0, 0.7], "size": [1.9, 1.9, 0.1], "mat": "planks", "id": "lid"}
FRAME = ["bucket"]
PLACES = {
    "field": {"world": "dio_field_well", "remove": ["well", "well_water"] + FRAME, "add": [PLUG], "prompt": "A dry open field before the well"},
    "dig": {"world": "dio_field_well", "remove": ["well", "well_water"] + FRAME, "add": [PLUG], "prompt": "The hole being dug down through soil"},
    "shaft": {"world": "dio_field_well", "remove": FRAME, "prompt": "The stone-lined shaft with water at the bottom"},
    "done": {"world": "dio_field_well", "prompt": "The finished well: stone shaft, frame, roof and bucket"},
    "covered": {"world": "dio_field_well", "add": [LID], "prompt": "The finished well with a wooden cover"},
}
DRY = [{"id": "plug", "grow": "up", "from": 1.0, "to": 1.0, "t0": 0, "t1": 0.05}]
FULL = [{"id": "well_water", "level_from": 1.2, "level_to": 1.2, "t0": 0, "t1": 0.05}]

SHOTS = [
    dict(beat="hook", text="This field hasn't seen rain in weeks. But this hole is full of water.", set="done", camera="wide", move="push",
         cast=B([{"do": "cheer", "at": 0.8}]), look=WIDE, moves=FULL, overlay={"type": "stamp", "text": "FULL"}),
    dict(beat="hook", text="So how does a hole in a dry field fill itself?", set="done", camera="medium", move="tilt_down",
         cast=B([{"do": "point", "at": 0.2, "params": {"dir": [-0.6, -0.3, -0.7]}}]), look=look(TOP, at=[0.0, 0.6, -2.0], dist=8.0), moves=FULL),
    dict(beat="concept", text="Sam's farm sits far from any river or pipe.", set="field", camera="wide", move="pan_r",
         cast=B([{"do": "walk", "at": 0.0}], "enter_l"), look=WIDE, moves=DRY),
    dict(beat="concept", text="And every summer the pond dries up.", set="field", camera="medium", move="push",
         cast=B([{"do": "wipe", "at": 0.2}], "B"), look=TOP, moves=DRY, overlay={"type": "cross", "text": "DRY POND"}),
    dict(beat="setup", text="But under his boots, there's a secret.", set="field", camera="wide", move="tilt_down",
         cast=B([{"do": "look_down", "at": 0.2}], "B"), look=look(WIDE, at=[0.0, 1.0, -4.0]), moves=DRY),
    dict(beat="setup", text="Rain that soaked in long ago is still down there.", set="field", camera="medium", move="push",
         cast=[], look=look(DEEP, at=[0.0, 0.6, -3.0], dist=7.0), moves=DRY, overlay={"type": "arrow", "text": "GROUNDWATER"}),
    dict(beat="setup", text="Filling the tiny gaps between gravel and rock.", set="field", camera="insert", move="push",
         cast=[], look=look(DEEP, at=[1.6, 0.4, -2.0], dist=3.0, lens=40), moves=DRY, overlay={"type": "label", "text": "GRAVEL"}),
    dict(beat="setup", text="So Sam starts to dig.", set="dig", camera="medium", move="push",
         cast=B([{"do": "dig", "at": 0.1, "params": {"face": 180}}]), look=TOP,
         moves=[{"id": "plug", "grow": "up", "from": 1.0, "to": 0.85, "t0": 0.3, "t1": 2.0}], sfx=[{"name": "pick", "at": 0.4}]),
    dict(beat="setup", text="First through the dark topsoil.", set="dig", camera="close", move="tilt_down",
         cast=B([{"do": "dig", "at": 0.0, "params": {"face": 180}}]), look=look(TOP, at=[0.0, 0.6, -0.6], dist=4.6),
         moves=[{"id": "plug", "grow": "up", "from": 0.85, "to": 0.7, "t0": 0.0, "t1": 1.4}], sfx=[{"name": "pick", "at": 0.3}]),
    dict(beat="setup", text="Into the gravel.", set="dig", camera="medium", move="push",
         cast=B([{"do": "dig", "at": 0.0, "params": {"face": 180}}]), look=look(WIDE, at=[0.0, 1.0, -2.0], dist=9.0),
         moves=[{"id": "plug", "grow": "up", "from": 0.7, "to": 0.55, "t0": 0.0, "t1": 1.3}], sfx=[{"name": "pick", "at": 0.3}]),
    dict(beat="obstacle", text="Then the walls start to crumble.", set="dig", camera="close", move="crash_zoom",
         cast=B([{"do": "shock", "at": 0.2}]), look=look(TOP, at=[0.0, 0.5, -1.4], dist=4.0), moves=[{"id": "plug", "grow": "up", "from": 0.55, "to": 0.55, "t0": 0, "t1": 0.05}],
         overlay={"type": "stamp", "text": "COLLAPSE"}, sfx=[{"name": "thud", "at": 0.3}]),
    dict(beat="obstacle", text="Loose ground caves in on a deep hole.", set="dig", camera="wide", move="push", cast=[],
         look=look(WIDE, at=[0.0, 1.0, -2.0], dist=10.0), moves=[{"id": "plug", "grow": "up", "from": 0.55, "to": 0.6, "t0": 0.2, "t1": 1.6}], freeze="WAIT..."),
    dict(beat="con", text="So he lines the shaft with stone, ring by ring.", set="shaft", camera="medium", move="tilt_up",
         cast=B([{"do": "carry", "at": 0.0, "params": {"face": 180}}], "C"), look=look(WIDE, at=[0.0, 0.6, -3.4], dist=9.0),
         moves=[{"id": "well", "show": 0.8}, {"id": "well_water", "level_from": 0.0, "level_to": 0.0, "t0": 0, "t1": 0.05}],
         overlay={"type": "label", "text": "STONE LINING"}),
    dict(beat="con", text="The stones hold the walls back. Water still slips between them.", set="shaft", camera="insert", move="push", cast=[],
         look=look(DEEP, at=[0.7, 0.2, -5.6], dist=3.2, lens=40), moves=[{"id": "well_water", "level_from": 0.0, "level_to": 0.4, "t0": 0.3, "t1": 2.8}],
         overlay={"type": "arrow", "text": "SEEPS IN"}),
    dict(beat="escalate", text="Deep enough, and the shaft drops below the water table.", set="shaft", camera="wide", move="push", cast=[],
         look=look(WIDE, at=[0.0, 1.0, -4.6], dist=11.0), moves=[{"id": "well_water", "level_from": 0.4, "level_to": 0.9, "t0": 0.2, "t1": 2.6}],
         overlay={"type": "label", "text": "WATER TABLE"}),
    dict(beat="twist", text="Now the ground pushes water in by itself.", set="shaft", camera="medium", move="tilt_up", cast=[],
         look=DEEP, moves=[{"id": "well_water", "level_from": 0.9, "level_to": 1.2, "t0": 0.0, "t1": 2.4}], sfx=[{"name": "splash", "at": 0.6}]),
    dict(beat="twist", text="It rises until it matches the water around it.", set="shaft", camera="close", move="push", cast=[],
         look=look(DEEP, dist=4.0), moves=FULL, overlay={"type": "stamp", "text": "LEVEL"}),
    dict(beat="payoff", text="A frame and a roof go on top.", set="done", camera="medium", move="push",
         cast=B([{"do": "hammer", "at": 0.1, "params": {"face": 180}}], "C"), look=TOP, moves=FULL, sfx=[{"name": "bonk", "at": 0.4}, {"name": "bonk", "at": 1.0}]),
    dict(beat="payoff", text="And a bucket on a rope.", set="done", camera="close", move="tilt_down",
         cast=B([{"do": "point", "at": 0.2, "params": {"dir": [-0.8, -0.2, 0.1]}}], "C"), look=look(TOP, at=[0.0, 0.4, 1.8], dist=3.8),
         moves=FULL + [{"id": "bucket", "from": [0, 0.35, 1.9], "to": [0, 0.35, -0.5], "t0": 0.6, "t1": 2.2}]),
    dict(beat="payoff", text="Then the hottest summer in years arrives.", set="covered", camera="wide", move="push",
         cast=B([{"do": "wipe", "at": 0.3}], "B"), look=WIDE, moves=[{"id": "well_water", "level_from": 1.2, "level_to": 1.0, "t0": 0.2, "t1": 2.4}],
         overlay={"type": "chalk", "text": "HEATWAVE"}),
    dict(beat="payoff", text="The pond is dust. The field is brown.", set="covered", camera="medium", move="pan_l",
         cast=B([{"do": "look", "at": 0.1, "params": {"yaw": -60, "pitch": 10}}], "B"), look=TOP, moves=[{"id": "well_water", "level_from": 1.0, "level_to": 1.0, "t0": 0, "t1": 0.05}],
         overlay={"type": "cross", "text": "POND"}),
    dict(beat="payoff", text="But deep down, the water is still waiting.", set="covered", camera="medium", move="push", cast=[],
         look=DEEP, moves=[{"id": "well_water", "level_from": 1.0, "level_to": 1.0, "t0": 0, "t1": 0.05}], overlay={"type": "arrow", "text": "STILL THERE"}),
    dict(beat="payoff", text="The cover keeps out dirt, leaves and animals.", set="covered", camera="close", move="push",
         cast=B([{"do": "nod", "at": 0.3}], "A"), look=look(TOP, at=[0.0, 0.4, 0.8], dist=4.0), moves=FULL, overlay={"type": "label", "text": "COVER"}),
    dict(beat="payoff", text="That's how a hole in a dry field fills itself with water.", set="done", camera="wide", move="pull",
         cast=B([{"do": "cheer", "at": 0.3}]), look=WIDE, moves=FULL),
]


def main():
    for i, s in enumerate(SHOTS, 1):
        s.setdefault("speaker", "narrator")
        for k, v in (("cast", []), ("props", []), ("sfx", []), ("transition", "cut")):
            s.setdefault(k, v)
        s["id"] = f"s{i:02d}"
    plan = {"id": "well_field", "title": "How a Hole in a Dry Field Fills Itself With Water",
            "topic": "how a hand-dug well works: digging below the water table, stone lining, groundwater seeping in, a cover",
            "hook_title": "WATER IN A DRY FIELD?",
            "keywords": ["water", "well", "groundwater", "gravel", "stone", "table", "dig", "dry", "bucket", "summer"],
            "cast": ["builder"], "channel": "channel3",
            "sources": ["https://en.wikipedia.org/wiki/Well", "https://en.wikipedia.org/wiki/Water_table"],
            "places": PLACES, "shots": SHOTS}
    out = Path(__file__).with_name("plan.json")
    out.write_text(json.dumps(plan, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
