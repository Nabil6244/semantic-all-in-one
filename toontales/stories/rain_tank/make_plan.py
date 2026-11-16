"""Writes plan.json for the Channel 3 test Short 'How a Backyard Becomes a Hidden Rain Tank' (original topic).
    python3 toontales/stories/rain_tank/make_plan.py && python3 -m toontales.plan.check toontales/stories/rain_tank/plan.json --fix
"""
import json
from pathlib import Path

CUT = {"at": [2.0, 1.0, -0.7], "dist": 9.0, "yaw": -6, "pitch": 6, "lens": 28}    # house corner, pit, garden
PIT = {"at": [2.3, 1.2, -0.9], "dist": 8.2, "yaw": -4, "pitch": 4, "lens": 30}     # the pit in section + Sam at its edge


def look(base, **kw):
    d = dict(base)
    d.update(kw)
    return d


def B(acts, mark="B"):
    return [{"id": "builder", "mark": mark, "acts": acts}]


BEFORE = ["tank_floor", "tank_back", "tank_l", "tank_r", "lid", "turf2", "pipe_a", "pipe_b", "pipe_c", "pump",
          "pump_pipe", "water"]
GROUND = ["turf", "plug_soil", "plug_gravel"]
PLACES = {
    "yard": {"world": "dio_backyard_tank", "remove": BEFORE, "prompt": "Backyard before: lawn, house, garden"},
    "yard_dug": {"world": "dio_backyard_tank", "remove": GROUND + BEFORE, "prompt": "Backyard with an open pit"},
    "yard_lined": {"world": "dio_backyard_tank", "remove": GROUND + ["lid", "turf2", "pipe_a", "pipe_b", "pipe_c",
                                                                      "pump", "pump_pipe"],
                   "prompt": "Pit lined with concrete"},
    "yard_closed": {"world": "dio_backyard_tank", "remove": GROUND + ["pipe_a", "pipe_b", "pipe_c", "pump",
                                                                       "pump_pipe"],
                    "prompt": "Tank closed under the lawn"},
    "yard_done": {"world": "dio_backyard_tank", "remove": GROUND, "prompt": "Finished hidden rain tank"},
}
FULL = [{"id": "water", "level_from": 1.7, "level_to": 1.7, "t0": 0, "t1": 0.05}]
NO_PUMP = [{"id": "pump", "hide": 99}, {"id": "pump_pipe", "hide": 99}]

SHOTS = [
    dict(beat="hook", text="Under this lawn hides a tank full of free rainwater.", set="yard_done", camera="wide",
         move="push", cast=B([{"do": "cheer", "at": 0.6}], "A"), look=CUT, moves=FULL,
         overlay={"type": "stamp", "text": "HIDDEN TANK"}),
    dict(beat="hook", text="So how does a backyard become a secret rain tank?", set="yard_done", camera="medium",
         move="pull", cast=B([{"do": "point", "at": 0.2, "params": {"dir": [-0.7, -0.4, -0.6]}}], "A"),
         look=look(PIT, dist=5.6), moves=FULL),
    dict(beat="concept", text="Every summer, Sam's garden dries out.", set="yard", camera="medium", move="push",
         cast=B([{"do": "crouch", "at": 0.1}], "A"),
         look={"at": [6.4, 1.4, 0.7], "dist": 4.2, "yaw": -14, "pitch": 8, "lens": 32}),
    dict(beat="concept", text="But every storm, rain pours off his roof and soaks away.", set="yard", camera="wide",
         move="tilt_down", cast=B([{"do": "look", "at": 0.1, "params": {"yaw": 40, "pitch": 25}}], "C"),
         look={"at": [-2.2, 1.6, 1.8], "dist": 7.5, "yaw": -12, "pitch": 6, "lens": 28},
         overlay={"type": "arrow", "text": "RUNOFF"}),
    dict(beat="setup", text="So Sam grabs a shovel and starts digging.", set="yard", camera="medium", move="push",
         cast=B([{"do": "dig", "at": 0.2, "params": {"face": 90}}]),
         look={"at": [1.05, 1.0, 0.8], "dist": 4.8, "yaw": -14, "pitch": 6, "lens": 32},
         moves=[{"id": "turf", "grow": "up", "from": 1, "to": 0, "t0": 1.0, "t1": 2.4}]),
    dict(beat="setup", text="Right next to the house, down through the soil,", set="yard", camera="wide",
         move="push", cast=B([{"do": "dig", "at": 0.0, "params": {"face": 90}}]), look=PIT,
         moves=[{"id": "turf", "hide": 0.0}, {"id": "plug_soil", "grow": "up", "from": 1, "to": 0, "t0": 0.2,
                                               "t1": 2.6}]),
    dict(beat="setup", text="past the gravel, more than two meters deep.", set="yard", camera="wide",
         move="tilt_down", cast=B([{"do": "dig", "at": 0.0, "params": {"face": 90}}]), look=PIT,
         moves=[{"id": "turf", "hide": 0.0}, {"id": "plug_soil", "hide": 0.0},
                {"id": "plug_gravel", "grow": "up", "from": 1, "to": 0, "t0": 0.1, "t1": 2.4}],
         overlay={"type": "stamp", "text": "2.3 M"}),
    dict(beat="con", text="Now he has a big hole. But a hole in the ground leaks.", set="yard_dug",
         camera="medium", move="push",
         cast=B([{"do": "look_down", "at": 0.0, "params": {"face": 90}}, {"do": "wipe", "at": 1.6,
                                                                             "params": {"face": 90}}]),
         look=look(PIT, dist=6.0), overlay={"type": "stamp", "text": "LEAKS"}),
    dict(beat="escalate", text="So he lines it with thick concrete walls,", set="yard_lined", camera="wide",
         move="push", cast=B([{"do": "carry", "at": 0.0, "params": {"face": 90}}]), look=PIT,
         moves=[{"id": "tank_l", "grow": "up", "t0": 0.2, "t1": 1.6}, {"id": "tank_back", "grow": "up", "t0": 0.6,
                                                                         "t1": 2.0},
                {"id": "tank_r", "grow": "up", "t0": 1.0, "t1": 2.4}]),
    dict(beat="escalate", text="and a heavy concrete floor.", set="yard_lined", camera="medium", move="push",
         cast=[], look=look(PIT, at=[2.7, 1.2, -1.5], dist=6.4, pitch=10),
         moves=[{"id": "tank_floor", "grow": "up", "t0": 0.1, "t1": 0.9}]),
    dict(beat="escalate", text="Then a strong lid on top, so nobody falls in.", set="yard_closed", camera="wide",
         move="pull", cast=B([{"do": "hammer", "at": 0.2, "params": {"face": 90}}]), look=PIT,
         moves=[{"id": "turf2", "hide": 99}, {"id": "lid", "show": 0.6}]),
    dict(beat="escalate", text="And fresh grass over it, so nobody even knows it's there.", set="yard_closed",
         camera="wide", move="pull", cast=B([{"do": "nod", "at": 1.6}], "A"), look=CUT,
         moves=[{"id": "turf2", "grow": "up", "t0": 0.3, "t1": 1.2}]),
    dict(beat="obstacle", text="But how does the rain get in?", set="yard_closed", camera="medium", move="push",
         cast=B([{"do": "look", "at": 0.1, "params": {"yaw": -40, "pitch": 20}}], "C"),
         look={"at": [-1.3, 1.0, 1.6], "dist": 5.2, "yaw": -14, "pitch": 6, "lens": 30}),
    dict(beat="twist", text="The clever part: a pipe from the roof gutter,", set="yard_done", camera="wide",
         move="tilt_down", cast=B([{"do": "drill", "at": 0.1, "params": {"face": -90}}], "C"),
         look={"at": [-0.6, 0.8, 1.0], "dist": 7.0, "yaw": -8, "pitch": 5, "lens": 28},
         moves=[{"id": "pipe_a", "grow": "all", "t0": 0.2, "t1": 1.2}, {"id": "pipe_b", "show": 1.2},
                {"id": "pipe_c", "show": 1.2}] + NO_PUMP),
    dict(beat="twist", text="hidden under the lawn, straight into the tank.", set="yard_done", camera="wide",
         move="pan_r", cast=[], look=look(CUT, at=[0.6, 1.0, -0.6], dist=7.0), moves=list(NO_PUMP)),
    dict(beat="twist", text="Next storm, every drop off the roof pours inside.", set="yard_done", camera="wide",
         move="push", cast=[], look=PIT,
         moves=[{"id": "water", "level_from": 0.001, "level_to": 0.9, "t0": 0.2, "t1": 3.0}] + NO_PUMP),
    dict(beat="twist", text="Storm after storm, the tank fills to the top.", set="yard_done", camera="wide",
         move="pull", cast=[], look=look(PIT, dist=7.4),
         moves=[{"id": "water", "level_from": 0.9, "level_to": 1.7, "t0": 0.1, "t1": 2.6}] + NO_PUMP),
    dict(beat="payoff", text="Then the dry summer comes back.", set="yard_done", camera="medium", move="push",
         cast=B([{"do": "walk", "at": 0.0, "params": {"to": [0.9, 0.2]}}, {"do": "crouch", "at": 1.4}], "A"),
         look={"at": [5.6, 1.2, 0.6], "dist": 4.6, "yaw": -12, "pitch": 8, "lens": 32},
         moves=FULL + [{"id": "pump", "show": 0.8}]),
    dict(beat="payoff", text="A small pump pulls the water back up for the garden.", set="yard_done", camera="wide",
         move="push", cast=B([{"do": "crouch", "at": 0.0}], "A"), look=look(CUT, at=[3.6, 1.0, -0.6], dist=7.6),
         moves=[{"id": "water", "level_from": 1.7, "level_to": 1.45, "t0": 0.4, "t1": 3.0}]),
    dict(beat="payoff", text="His plants drink rain that fell months ago.", set="yard_done", camera="medium",
         move="push", cast=B([{"do": "explain", "at": 0.2}], "A"),
         look={"at": [7.0, 1.6, 0.8], "dist": 4.8, "yaw": -10, "pitch": 8, "lens": 32}, moves=list(FULL)),
    dict(beat="payoff", text="That's how a backyard hides a rain tank under the grass.", set="yard_done",
         camera="wide", move="pull", cast=B([{"do": "cheer", "at": 0.3}], "A"), look=CUT,
         moves=[{"id": "water", "level_from": 1.45, "level_to": 1.45, "t0": 0, "t1": 0.05}]),
]


def main():
    for i, s in enumerate(SHOTS, 1):
        s.setdefault("speaker", "narrator")
        for k, v in (("cast", []), ("props", []), ("sfx", []), ("transition", "cut")):
            s.setdefault(k, v)
        s["id"] = f"s{i:02d}"
    plan = {"id": "rain_tank", "title": "How a Backyard Becomes a Hidden Rain Tank",
            "topic": "underground rainwater tank (cistern) dug next to a house: downpipe in, pump out",
            "hook_title": "A TANK UNDER THE LAWN?",
            "keywords": ["rain", "tank", "concrete", "pipe", "pump", "storm", "garden", "hidden", "water", "dig"],
            "cast": ["builder"], "channel": "channel3",
            "sources": ["https://en.wikipedia.org/wiki/Rainwater_tank", "https://en.wikipedia.org/wiki/Cistern"],
            "places": PLACES, "shots": SHOTS}
    out = Path(__file__).with_name("plan.json")
    out.write_text(json.dumps(plan, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
