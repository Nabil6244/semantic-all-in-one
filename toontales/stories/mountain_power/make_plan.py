"""Ch4 Short: why cars get weaker up a mountain, why turbos don't, and why an electric car holds the Pikes Peak record."""
import json
from pathlib import Path

NA = {"m": "@engine", "at": [-0.75, 2.2, 1.0], "rot": 22, "cyl": 8, "layout": "V", "cover": [0.9, 0.12, 0.1], "id": "na", "run": 0.8}
TB = {"m": "@engine", "at": [0.75, 2.2, 1.0], "rot": -22, "cyl": 4, "layout": "I", "induction": "turbo", "cover": [0.2, 0.45, 0.95],
      "id": "tb", "run": 0.8}
TURBO = {"m": "@turbo", "at": [-0.75, 2.2, 1.0], "s": 2.4, "rot": 0, "id": "turbo", "run": 0.6}
MOTOR = {"m": "@motor", "at": [0.75, 2.2, 1.0], "s": 1.3, "rot": -20, "id": "motor", "run": 1.0}
CARS = [{"m": "hatchback-sports", "at": [-5, 5.4, 0], "rot": 90, "s": 0.8, "tint": [0.9, 0.1, 0.1], "tint_mode": "color", "id": "red"},
        {"m": "sedan-sports", "at": [-6.5, 6.8, 0], "rot": 90, "s": 0.8, "tint": [0.15, 0.35, 1.0], "tint_mode": "color", "id": "blue"}]
PLACES = {"garage": {"world": "garage", "add": [NA, TB], "prompt": "A red V8 and a blue turbo four on orange stands"},
          "bench": {"world": "garage", "add": [TURBO, MOTOR], "prompt": "A giant turbocharger and an electric motor on stands"},
          "mountain": {"world": "mountain_road", "remove": ["rig", "car"], "add": CARS, "prompt": "Two cars on a mountain road"},
          "strip": {"world": "drag_strip", "remove": ["car_a", "car_b"],
                    "add": [{**CARS[0], "at": [-1.7, 0, 0], "rot": 180}, {**CARS[1], "at": [1.7, 0, 0], "rot": 180}],
                    "prompt": "A red and a blue car at the start line, sea level"}}
GW = {"at": [0, 2.2, 1.35], "dist": 6.2, "yaw": 0, "pitch": 9, "lens": 26, "fit": ["na", "tb"]}
BW = {"at": [0, 2.2, 1.35], "dist": 6.2, "yaw": 0, "pitch": 9, "lens": 26, "fit": ["turbo", "motor"]}
MW = {"at": [-1.0, 6.0, 0.8], "dist": 13, "yaw": 0, "pitch": 22, "lens": 26}
AIR = lambda a, b, **k: {"label": "AIR", "fmt": "{v}%", "from": a, "to": b, "max": 100, "color": "red", **k}
HP = lambda a, b, **k: {"label": "HORSEPOWER", "fmt": "{v} HP", "from": a, "to": b, "max": 500, "color": "red", **k}
S = []


def sh(beat, text, place, cam, move, look, **kw):
    S.append({"beat": beat, "speaker": "narrator", "text": text, "set": place, "camera": cam, "move": move, "cast": [], "look": look, **kw})


sh("hook", "Up high, this V8 loses a third of its power.", "garage", "wide", "push", GW,
   moves=[{"id": "na", "run_to": 4, "t0": 0.2, "t1": 1.4}], hud=HP(400, 270), sfx=[{"name": "whoosh", "at": 0.1}])
sh("hook", "The turbo four barely notices. Why?", "garage", "medium", "crash_zoom", {**GW, "dist": 3.0, "at": [0.75, 2.2, 1.2], "fit": ["tb"]},
   callout={"text": "WHY?", "x": 0.5, "y": 0.4}, moves=[{"id": "tb", "run_to": 6, "t0": 0.1, "t1": 1.0}])
sh("concept", "Engines burn fuel with air.", "garage", "close", "push", {**GW, "dist": 2.6, "at": [-0.75, 2.2, 1.3], "fit": ["na"]},
   callout={"text": "AIR + FUEL", "x": 0.5, "y": 0.4}, moves=[{"id": "na", "run_to": 5, "t0": 0.1, "t1": 0.8}])
sh("concept", "Down at sea level, air is thick.", "strip", "wide", "push", {"at": [0, 0, 0.7], "dist": 12, "yaw": 0, "pitch": 10, "lens": 26},
   hud=AIR(0, 100, color="green"))
sh("setup", "Drive up a mountain, and it gets thin.", "mountain", "wide", "pan_r", MW,
   moves=[{"id": "red", "to": [4, 5.4, 0], "t0": 0.2, "t1": 2.6, "ease": "out"}], hud=AIR(100, 70), sfx=[{"name": "car", "at": 0.1}])
sh("setup", "At ten thousand feet, thirty percent less.", "mountain", "medium", "push", {**MW, "dist": 10, "at": [-4.5, 5.6, 0.6]},
   callout={"text": "10,000 FT", "x": 0.5, "y": 0.4})
sh("obstacle", "Less air. Less bang.", "garage", "close", "crash_zoom", {**GW, "dist": 2.2, "at": [-0.75, 2.2, 1.4], "fit": ["na"]},
   hud=HP(400, 280), moves=[{"id": "na", "run_to": 2, "t0": 0, "t1": 1.0}])
sh("obstacle", "The red car starts to struggle.", "mountain", "medium", "drift", {**MW, "dist": 10, "at": [-2, 5.8, 0.6]},
   moves=[{"id": "red", "to": [-1, 5.4, 0], "t0": 0.1, "t1": 2.4, "ease": "in"}], freeze="WAIT...")
sh("con", "But a turbo is an air pump.", "bench", "wide", "orbit_r", {**BW, "dist": 3.2, "at": [-0.75, 2.2, 1.2], "fit": ["turbo"]},
   callout={"text": "AIR PUMP", "x": 0.5, "y": 0.4}, moves=[{"id": "turbo", "run_to": 4, "t0": 0.2, "t1": 1.4}])
sh("con", "Exhaust spins it. It squeezes air in.", "bench", "close", "push", {**BW, "dist": 2.0, "at": [-0.75, 2.2, 1.2], "fit": ["turbo"]},
   moves=[{"id": "turbo", "run_to": 7, "t0": 0, "t1": 1.0}], sfx=[{"name": "whoosh", "at": 0.3}])
sh("con", "Thin air? Spin faster.", "bench", "medium", "crash_zoom", {**BW, "dist": 2.4, "at": [-0.75, 2.2, 1.2], "fit": ["turbo"]},
   hud={"label": "TURBO SPEED", "fmt": "{v}K RPM", "from": 120, "to": 180, "max": 200, "color": "green"},
   moves=[{"id": "turbo", "run_to": 9, "t0": 0, "t1": 0.8}])
sh("escalate", "So the blue car keeps pulling.", "mountain", "wide", "pan_r", MW,
   moves=[{"id": "blue", "to": [6, 6.8, 0], "t0": 0.1, "t1": 2.4, "ease": "out"}], hud=HP(300, 290, color="green"), sfx=[{"name": "car", "at": 0.1}])
sh("escalate", "That's why turbos rule Pikes Peak.", "mountain", "medium", "push", {**MW, "dist": 10, "at": [2, 6.4, 0.6]},
   callout={"text": "PIKES PEAK", "x": 0.5, "y": 0.4})
sh("escalate", "Finish line: fourteen thousand feet.", "mountain", "wide", "tilt_up", {**MW, "pitch": 26, "dist": 14},
   callout={"text": "14,115 FT", "x": 0.5, "y": 0.4})
sh("twist", "But the record run used no air at all.", "bench", "medium", "push", {**BW, "dist": 2.6, "at": [0.75, 2.2, 1.2], "fit": ["motor"]},
   moves=[{"id": "motor", "run_to": 5, "t0": 0.1, "t1": 1.0}])
sh("twist", "An electric car. In 2018, under eight minutes.", "bench", "close", "crash_zoom", {**BW, "dist": 1.8, "at": [0.75, 2.2, 1.2], "fit": ["motor"]},
   callout={"text": "7:57", "x": 0.5, "y": 0.4}, moves=[{"id": "motor", "run_to": 8, "t0": 0, "t1": 0.6}])
sh("payoff", "Electric motors don't breathe. Thin air costs nothing.", "bench", "wide", "pull", BW,
   hud=AIR(100, 0, label="AIR NEEDED"))
sh("payoff", "Turbo or battery, up the mountain?", "garage", "wide", "pull", GW,
   moves=[{"id": "na", "run_to": 4, "t0": 0.2, "t1": 1.0}, {"id": "tb", "run_to": 5, "t0": 0.2, "t1": 1.0}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
    for k, v in (("props", []), ("sfx", []), ("transition", "cut")):
        s.setdefault(k, v)
plan = {"id": "mountain_power", "title": "Why Cars Get Weaker Up a Mountain",
        "topic": "altitude power loss in naturally aspirated engines, turbochargers compensating for thin air, Pikes Peak and the electric VW ID.R record (2018)",
        "hook_title": "WHY DO CARS GET WEAK UP HIGH?", "keywords": ["air", "mountain", "turbo", "thin", "Pikes", "Peak", "electric", "power"],
        "cast": [], "channel": "channel4",
        "sources": ["https://en.wikipedia.org/wiki/Turbocharger", "https://en.wikipedia.org/wiki/Volkswagen_I.D._R"],
        "places": PLACES, "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
