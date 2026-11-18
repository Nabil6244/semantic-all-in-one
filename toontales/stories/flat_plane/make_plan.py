"""Ch4 Short: Why a Ferrari V8 screams and a Mustang V8 rumbles (flat-plane vs cross-plane crank)."""
import json
from pathlib import Path

RED = {"m": "@engine", "at": [-0.75, 2.2, 1.0], "rot": 22, "cyl": 8, "layout": "V", "induction": "none", "cover": [0.85, 0.1, 0.1], "id": "flat", "run": 0.8}
BLUE = {"m": "@engine", "at": [0.75, 2.2, 1.0], "rot": -22, "cyl": 8, "layout": "V", "induction": "none", "block": [0.32, 0.33, 0.37],
        "cover": [0.15, 0.35, 0.9], "id": "cross", "run": 0.8}
CUT_R = {"m": "@engine", "at": [-0.75, 2.2, 1.0], "rot": 0, "cyl": 8, "layout": "V", "induction": "none", "cutaway": True,
         "block": [0.62, 0.64, 0.68], "cover": [0.85, 0.1, 0.1], "id": "flat_cut", "run": 1.0}
CUT_B = {"m": "@engine", "at": [0.75, 2.2, 1.0], "rot": 0, "cyl": 8, "layout": "V", "induction": "none", "cutaway": True,
         "block": [0.32, 0.33, 0.37], "cover": [0.15, 0.35, 0.9], "id": "cross_cut", "run": 1.0}
CARS = [{"m": "hatchback-sports", "at": [-1.7, 0, 0], "rot": 180, "s": 0.8, "tint": [0.9, 0.1, 0.1], "tint_mode": "color", "id": "red"},
        {"m": "sedan-sports", "at": [1.7, 0, 0], "rot": 180, "s": 0.8, "tint": [0.15, 0.35, 1.0], "tint_mode": "color", "id": "blue"}]
PLACES = {"garage": {"world": "garage", "add": [RED, BLUE]},
          "flat_bench": {"world": "garage", "add": [CUT_R]},
          "cross_bench": {"world": "garage", "add": [CUT_B]},
          "strip": {"world": "drag_strip", "add": CARS}}
GW = {"at": [0, 2.2, 1.35], "dist": 6.2, "yaw": 0, "pitch": 9, "lens": 26, "fit": ["flat", "cross"]}
FB = lambda **k: {**{"at": [-0.75, 2.2, 1.6], "dist": 2.6, "yaw": 16, "pitch": 10, "lens": 30}, **k}
CB = lambda **k: {**{"at": [0.75, 2.2, 1.6], "dist": 2.6, "yaw": -16, "pitch": 10, "lens": 30}, **k}
RPM = lambda a, b, c="green", **k: {"label": "REDLINE", "fmt": "{v} RPM", "from": a, "to": b, "max": 10000, "color": c, **k}
S = []
def sh(beat, text, place, cam, move, look, **kw):
    S.append({"beat": beat, "speaker": "narrator", "text": text, "set": place, "camera": cam, "move": move, "cast": [], "look": look, **kw})
sh("hook", "Two V8s. Eight cylinders each.", "garage", "wide", "push", GW,
   moves=[{"id": "flat", "run_to": 4, "t0": 0.2, "t1": 1.2}, {"id": "cross", "run_to": 4, "t0": 0.4, "t1": 1.4}], sfx=[{"name": "car", "at": 0.2}])
sh("hook", "One screams, one rumbles. Why?", "garage", "medium", "crash_zoom", {**GW, "dist": 4.4},
   callout={"text": "SCREAM vs RUMBLE", "x": 0.5, "y": 0.38}, sfx=[{"name": "boom", "at": 0.3}])
sh("setup", "The secret is the crankshaft inside.", "cross_bench", "wide", "orbit_l", CB(),
   callout={"text": "CRANKSHAFT", "x": 0.5, "y": 0.4}, moves=[{"id": "cross_cut", "run_to": 3, "t0": 0.2, "t1": 1.4}])
sh("setup", "Most American V8s use a cross-plane crank.", "cross_bench", "medium", "push", CB(dist=1.9, yaw=-26),
   callout={"text": "CROSS-PLANE", "x": 0.5, "y": 0.42})
sh("con", "Each bank fires unevenly. Bang, bang... bang.", "cross_bench", "close", "crash_zoom", CB(dist=1.5, yaw=20, at=[0.75, 2.2, 1.75]),
   moves=[{"id": "cross_cut", "run_to": 6, "t0": 0, "t1": 0.5}], sfx=[{"name": "boom", "at": 0.2}, {"name": "boom", "at": 0.6}, {"name": "boom", "at": 1.3}])
sh("con", "That uneven beat is the rumble.", "garage", "medium", "push", {**GW, "dist": 2.6, "at": [0.75, 2.2, 1.4]},
   callout={"text": "BURBLE", "x": 0.5, "y": 0.4})
sh("con", "But that crank is heavy.", "cross_bench", "close", "push", CB(dist=1.6, yaw=30, at=[0.75, 2.2, 1.3]),
   callout={"text": "HEAVY", "x": 0.5, "y": 0.42})
sh("escalate", "Big counterweights keep it smooth, but slow to rev.", "cross_bench", "wide", "pull", CB(dist=2.8, yaw=-10),
   hud=RPM(0, 7500, "red"))
sh("escalate", "Ferrari's flat-plane crank is flat, like a ruler.", "flat_bench", "wide", "orbit_r", FB(),
   callout={"text": "FLAT-PLANE", "x": 0.5, "y": 0.4}, moves=[{"id": "flat_cut", "run_to": 4, "t0": 0.2, "t1": 1.4}])
sh("escalate", "Banks take turns. Left, right, left, right.", "flat_bench", "close", "crash_zoom", FB(dist=1.5, yaw=-22, at=[-0.75, 2.2, 1.75]),
   moves=[{"id": "flat_cut", "run_to": 9, "t0": 0, "t1": 0.4}], sfx=[{"name": "whoosh", "at": 0.2}])
sh("twist", "Lighter crank, higher revs.", "flat_bench", "medium", "push", FB(dist=2.0, yaw=28), hud=RPM(0, 9000), freeze="WAIT...")
sh("twist", "Even exhaust pulses. That's the scream.", "garage", "medium", "crash_zoom", {**GW, "dist": 2.6, "at": [-0.75, 2.2, 1.4]},
   callout={"text": "SCREAM", "x": 0.5, "y": 0.4}, moves=[{"id": "flat", "run_to": 9, "t0": 0.1, "t1": 0.6}])
sh("obstacle", "The catch? More shaking.", "flat_bench", "close", "push", FB(dist=1.6, yaw=10),
   callout={"text": "SHAKE", "x": 0.5, "y": 0.42}, moves=[{"id": "flat_cut", "run_to": 9, "t0": 0, "t1": 0.3}])
sh("payoff", "Then Ford built a flat-plane Mustang, the GT350.", "strip", "wide", "push", {"at": [0, 0, 0.7], "dist": 16, "yaw": 0, "pitch": 10, "lens": 26},
   callout={"text": "GT350 VOODOO", "x": 0.5, "y": 0.38})
sh("payoff", "It revved to 8,250.", "strip", "medium", "drift", {"at": [1.7, 4, 0.6], "to": [1.7, 40, 0.6], "dist": 9, "yaw": -8, "pitch": 9, "lens": 26},
   hud=RPM(0, 8250), moves=[{"id": "blue", "to": [1.7, 46, 0], "t0": 0.1, "t1": 2.4, "ease": "out"}, {"id": "red", "to": [-1.7, 44, 0], "t0": 0.2, "t1": 2.4, "ease": "out"}],
   sfx=[{"name": "car", "at": 0.1}])
sh("payoff", "Same eight cylinders. Scream or rumble, which one's yours?", "garage", "wide", "pull", GW,
   moves=[{"id": "flat", "run_to": 5, "t0": 0.2, "t1": 1.0}, {"id": "cross", "run_to": 5, "t0": 0.2, "t1": 1.0}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
    for k, v in (("props", []), ("sfx", []), ("transition", "cut")):
        s.setdefault(k, v)
plan = {"id": "flat_plane", "title": "Why a Ferrari V8 Screams and a Mustang V8 Rumbles", "topic": "flat-plane vs cross-plane V8 crankshafts: firing order, exhaust pulses, crank weight, revs and vibration",
        "hook_title": "SCREAM OR RUMBLE?", "keywords": ["crank", "flat-plane", "cross-plane", "V8", "rumble", "scream", "revs", "Ferrari"],
        "cast": [], "channel": "channel4",
        "sources": ["https://en.wikipedia.org/wiki/Crossplane", "https://en.wikipedia.org/wiki/Flat-plane_crankshaft"],
        "places": PLACES, "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
