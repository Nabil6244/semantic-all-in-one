"""Ch4 Short: How a small bottle of nitrous adds 100 horsepower (and why it can melt pistons)."""
import json
from pathlib import Path

ENG = {"m": "@engine", "at": [-0.6, 2.2, 1.0], "rot": 18, "cyl": 8, "layout": "V", "induction": "none", "cover": [0.85, 0.1, 0.1], "id": "eng", "run": 0.8}
BOTTLE = {"m": "@box", "at": [0.75, 2.3, 0.0], "size": [0.2, 0.2, 0.75], "color": [0.1, 0.3, 0.95], "id": "bottle"}
CUT = {"m": "@engine", "at": [-0.6, 2.2, 1.0], "rot": 0, "cyl": 8, "layout": "V", "induction": "none", "cutaway": True,
       "block": [0.62, 0.64, 0.68], "cover": [0.85, 0.1, 0.1], "id": "v8", "run": 1.0}
CARS = [{"m": "hatchback-sports", "at": [-1.7, 0, 0], "rot": 180, "s": 0.8, "tint": [0.9, 0.1, 0.1], "tint_mode": "color", "id": "red"},
        {"m": "sedan-sports", "at": [1.7, 0, 0], "rot": 180, "s": 0.8, "tint": [0.15, 0.35, 1.0], "tint_mode": "color", "id": "blue"}]
PLACES = {"garage": {"world": "garage", "add": [ENG, BOTTLE]},
          "bench": {"world": "garage", "add": [CUT, BOTTLE]},
          "dyno": {"world": "garage", "add": [{**BOTTLE, "at": [0.0, 2.3, 0.0], "s": 1.6}]},
          "strip": {"world": "drag_strip", "add": CARS}}
GW = {"at": [0, 2.2, 1.1], "dist": 5.6, "yaw": 0, "pitch": 9, "lens": 26, "fit": ["eng", "bottle"]}
BW = lambda **k: {**{"at": [-0.6, 2.2, 1.6], "dist": 2.6, "yaw": 16, "pitch": 10, "lens": 30}, **k}
HP = lambda a, b, **k: {"label": "HORSEPOWER", "fmt": "{v} HP", "from": a, "to": b, "max": 700, "color": "green", **k}
S = []
def sh(beat, text, place, cam, move, look, **kw):
    S.append({"beat": beat, "speaker": "narrator", "text": text, "set": place, "camera": cam, "move": move, "cast": [], "look": look, **kw})
sh("hook", "Same V8. One small blue bottle.", "garage", "wide", "push", GW,
   moves=[{"id": "eng", "run_to": 4, "t0": 0.2, "t1": 1.4}], sfx=[{"name": "whoosh", "at": 0.1}], callout={"text": "+100 HP?", "x": 0.5, "y": 0.4})
sh("hook", "A hundred more horsepower.", "dyno", "close", "crash_zoom", {"at": [0.0, 2.3, 0.8], "dist": 2.4, "yaw": 10, "pitch": 6, "lens": 30},
   hud=HP(450, 550), sfx=[{"name": "boom", "at": 0.3}])
sh("hook", "No turbo, no blower. So how?", "garage", "medium", "crash_zoom", {**GW, "dist": 3.6, "at": [0.6, 2.3, 0.6]},
   callout={"text": "NITROUS", "x": 0.5, "y": 0.4}, sfx=[{"name": "pop", "at": 0.3}])
sh("setup", "An engine burns fuel with oxygen from the air.", "bench", "wide", "orbit_r", BW(),
   callout={"text": "AIR + FUEL", "x": 0.5, "y": 0.38}, moves=[{"id": "v8", "run_to": 3, "t0": 0.2, "t1": 1.4}])
sh("setup", "Air is only about a fifth oxygen.", "bench", "close", "push", BW(dist=1.7, yaw=26),
   hud={"label": "OXYGEN IN AIR", "fmt": "{v}%", "from": 0, "to": 21, "max": 50, "color": "red"})
sh("con", "Nitrous oxide carries more.", "dyno", "medium", "crash_zoom", {"at": [0.0, 2.3, 0.8], "dist": 2.2, "yaw": 20, "pitch": 6, "lens": 30},
   hud={"label": "OXYGEN IN NITROUS", "fmt": "{v}%", "from": 0, "to": 36, "max": 50, "color": "green"})
sh("con", "Heat splits it apart inside the cylinder.", "bench", "close", "crash_zoom", BW(dist=1.5, yaw=-20, at=[-0.6, 2.2, 1.7]),
   callout={"text": "SPLIT!", "x": 0.5, "y": 0.42}, moves=[{"id": "v8", "run_to": 7, "t0": 0, "t1": 0.5}], sfx=[{"name": "boom", "at": 0.4}])
sh("con", "Extra oxygen. Bigger bang.", "bench", "medium", "push", BW(dist=2.0, yaw=30),
   hud=HP(450, 550), moves=[{"id": "v8", "run_to": 8, "t0": 0, "t1": 0.4}], sfx=[{"name": "boom", "at": 0.2}])
sh("escalate", "And it sprays in ice cold, so the air gets denser too.", "garage", "close", "push", {**GW, "dist": 2.4, "at": [0.0, 2.3, 1.0]},
   hud={"label": "INTAKE TEMP", "fmt": "{v} F", "from": 90, "to": 30, "max": 120, "color": "green"}, sfx=[{"name": "whoosh", "at": 0.2}])
sh("escalate", "But there's a catch.", "bench", "wide", "pull", BW(dist=2.8, yaw=-12), freeze="WAIT...")
sh("escalate", "More oxygen needs more fuel.", "bench", "medium", "push", BW(dist=1.9, yaw=8),
   callout={"text": "MORE FUEL", "x": 0.5, "y": 0.4})
sh("escalate", "Too little, and the flame burns so hot it can melt a piston.", "bench", "close", "crash_zoom", BW(dist=1.4, yaw=-28, at=[-0.6, 2.2, 1.5]),
   hud={"label": "PISTON TEMP", "fmt": "{v} F", "from": 900, "to": 1300, "max": 1400, "color": "red"}, sfx=[{"name": "boom", "at": 0.5}])
sh("twist", "So kits add extra fuel with the nitrous.", "garage", "medium", "crash_zoom", {**GW, "dist": 3.0},
   callout={"text": "WET KIT", "x": 0.5, "y": 0.4}, moves=[{"id": "eng", "run_to": 6, "t0": 0.1, "t1": 0.8}])
sh("twist", "And the bottle empties in seconds.", "garage", "close", "push", {**GW, "dist": 2.2, "at": [0.75, 2.3, 0.6]},
   hud={"label": "BOTTLE", "fmt": "{v}%", "from": 100, "to": 0, "max": 100, "color": "red"})
sh("payoff", "That's why you only press the button at full throttle.", "strip", "wide", "push", {"at": [0, 0, 0.7], "dist": 16, "yaw": 0, "pitch": 10, "lens": 26},
   callout={"text": "SPRAY!", "x": 0.5, "y": 0.4})
sh("payoff", "The blue car sprays. The red car doesn't.", "strip", "medium", "drift",
   {"at": [-1.7, 4, 0.6], "to": [-1.7, 40, 0.6], "dist": 9, "yaw": 8, "pitch": 9, "lens": 26},
   moves=[{"id": "red", "to": [-1.7, 40, 0], "t0": 0.2, "t1": 2.6, "ease": "in"}, {"id": "blue", "to": [1.7, 48, 0], "t0": 0.1, "t1": 2.6, "ease": "out"}],
   sfx=[{"name": "car", "at": 0.1}])
sh("payoff", "One blue bottle, one hundred horsepower.", "dyno", "wide", "pull", {"at": [0.0, 2.3, 0.8], "dist": 3.6, "yaw": -8, "pitch": 6, "lens": 28},
   hud=HP(450, 550))
sh("payoff", "Would you push the button?", "garage", "wide", "pull", GW, moves=[{"id": "eng", "run_to": 5, "t0": 0.2, "t1": 1.0}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
    for k, v in (("props", []), ("sfx", []), ("transition", "cut")):
        s.setdefault(k, v)
plan = {"id": "nitrous_shot", "title": "How a Small Bottle Adds 100 Horsepower", "topic": "How nitrous oxide injection adds power: extra oxygen, a colder intake charge, and why it needs extra fuel",
        "hook_title": "100 HP IN A BOTTLE?", "keywords": ["nitrous", "oxygen", "fuel", "piston", "bottle", "horsepower", "cold", "button"],
        "cast": [], "channel": "channel4",
        "sources": ["https://en.wikipedia.org/wiki/Nitrous_oxide_engine", "https://en.wikipedia.org/wiki/Nitrous_oxide"],
        "places": PLACES, "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
