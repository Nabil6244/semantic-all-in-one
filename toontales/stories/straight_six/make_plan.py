"""Ch4 Short: why a straight six runs smoother than a V6 (and why carmakers went back to it)."""
import json
from pathlib import Path

I6 = {"m": "@engine", "at": [-0.75, 2.2, 1.0], "rot": 22, "cyl": 6, "layout": "I", "cover": [0.2, 0.45, 0.95], "id": "i6", "run": 0.8}
V6 = {"m": "@engine", "at": [0.75, 2.2, 1.0], "rot": -22, "cyl": 6, "layout": "V", "cover": [0.9, 0.12, 0.1], "id": "v6", "run": 0.8}
CUT_I6 = {"m": "@engine", "at": [-0.75, 2.2, 1.0], "rot": 0, "cyl": 6, "layout": "I", "cutaway": True, "block": [0.62, 0.64, 0.68],
          "cover": [0.2, 0.45, 0.95], "id": "ci6", "run": 1.0}
CUT_V6 = {"m": "@engine", "at": [-0.75, 2.2, 1.0], "rot": 0, "cyl": 6, "layout": "V", "cutaway": True, "block": [0.62, 0.64, 0.68],
          "cover": [0.9, 0.12, 0.1], "id": "cv6", "run": 1.0}
CARS = [{"m": "sedan-sports", "at": [-1.7, 0, 0], "rot": 180, "s": 0.8, "tint": [0.15, 0.35, 1.0], "tint_mode": "color", "id": "blue"},
        {"m": "hatchback-sports", "at": [1.7, 0, 0], "rot": 180, "s": 0.8, "tint": [0.9, 0.1, 0.1], "tint_mode": "color", "id": "red"}]
PLACES = {"garage": {"world": "garage", "add": [I6, V6], "prompt": "Two six-cylinder engines on orange stands: a long inline six and a short V6"},
          "i6_bench": {"world": "garage", "remove": ["stand_b"], "add": [CUT_I6], "prompt": "A cutaway inline six engine on a stand"},
          "v6_bench": {"world": "garage", "remove": ["stand_b"], "add": [CUT_V6], "prompt": "A cutaway V6 engine on a stand"},
          "strip": {"world": "drag_strip", "remove": ["car_a", "car_b"], "add": CARS, "prompt": "A blue sedan and a red hatchback at the start"}}
GW = {"at": [0, 2.2, 1.35], "dist": 6.2, "yaw": 0, "pitch": 9, "lens": 26, "fit": ["i6", "v6"]}
BW = lambda **k: {**{"at": [-0.75, 2.2, 1.5], "dist": 2.6, "yaw": 16, "pitch": 8, "lens": 30}, **k}
SHAKE = lambda a, b, **k: {"label": "SHAKE", "fmt": "{v}%", "from": a, "to": b, "max": 100, "color": "red", **k}
S = []


def sh(beat, text, place, cam, move, look, **kw):
    S.append({"beat": beat, "speaker": "narrator", "text": text, "set": place, "camera": cam, "move": move, "cast": [], "look": look, **kw})


sh("hook", "Both engines have six cylinders.", "garage", "wide", "push", GW,
   moves=[{"id": "i6", "run_to": 4, "t0": 0.2, "t1": 1.4}, {"id": "v6", "run_to": 4, "t0": 0.2, "t1": 1.4}],
   callout={"text": "6 vs 6", "x": 0.5, "y": 0.42}, sfx=[{"name": "whoosh", "at": 0.1}])
sh("hook", "But one is way smoother. Why?", "garage", "medium", "crash_zoom", {**GW, "dist": 3.4, "at": [-0.75, 2.2, 1.2], "fit": ["i6"]},
   callout={"text": "SMOOTH?", "x": 0.5, "y": 0.4}, moves=[{"id": "i6", "run_to": 6, "t0": 0.1, "t1": 1.0}])
sh("concept", "Blue: a straight six. One long row.", "i6_bench", "wide", "orbit_r", BW(),
   callout={"text": "INLINE 6", "x": 0.5, "y": 0.38}, moves=[{"id": "ci6", "run_to": 3, "t0": 0.2, "t1": 1.4}])
sh("concept", "Red: a V6. Two rows of three.", "v6_bench", "wide", "orbit_l", BW(yaw=-16),
   callout={"text": "V6", "x": 0.5, "y": 0.38}, moves=[{"id": "cv6", "run_to": 3, "t0": 0.2, "t1": 1.4}])
sh("setup", "Every piston slams up and down.", "i6_bench", "close", "push", BW(dist=1.6, yaw=24),
   hud=SHAKE(0, 60), moves=[{"id": "ci6", "run_to": 5, "t0": 0, "t1": 0.6}], sfx=[{"name": "thud", "at": 0.4}])
sh("setup", "In a straight six, the front three mirror the back three.", "i6_bench", "medium", "push", BW(dist=2.0, yaw=-10),
   callout={"text": "MIRROR", "x": 0.5, "y": 0.4})
sh("setup", "Every shove gets cancelled.", "i6_bench", "close", "crash_zoom", BW(dist=1.5, yaw=30, at=[-0.75, 2.2, 1.6]),
   hud=SHAKE(60, 0, color="green"), moves=[{"id": "ci6", "run_to": 7, "t0": 0, "t1": 0.6}])
sh("setup", "Almost zero shake.", "garage", "medium", "push", {**GW, "dist": 3.0, "at": [-0.75, 2.2, 1.2], "fit": ["i6"]},
   hud=SHAKE(5, 0, color="green"))
sh("obstacle", "A V6 has two short rows.", "v6_bench", "close", "push", BW(dist=1.8, yaw=-26),
   callout={"text": "3 + 3", "x": 0.5, "y": 0.4}, moves=[{"id": "cv6", "run_to": 5, "t0": 0, "t1": 0.6}])
sh("obstacle", "Three can't balance. It rocks.", "v6_bench", "medium", "crash_zoom", BW(dist=2.2, yaw=10),
   hud=SHAKE(0, 45), sfx=[{"name": "thud", "at": 0.3}, {"name": "thud", "at": 0.8}], freeze="WAIT...")
sh("escalate", "So V6s often need extra spinning weights.", "garage", "close", "push", {**GW, "dist": 2.6, "at": [0.75, 2.2, 1.2], "fit": ["v6"]},
   callout={"text": "BALANCE SHAFT", "x": 0.5, "y": 0.4}, moves=[{"id": "v6", "run_to": 5, "t0": 0.1, "t1": 1.0}])
sh("escalate", "Then why build V6s?", "garage", "wide", "pull", GW, callout={"text": "WHY V6?", "x": 0.5, "y": 0.42})
sh("twist", "Because a straight six is long.", "garage", "medium", "pan_r", {**GW, "dist": 3.4, "at": [-0.75, 2.2, 1.2], "fit": ["i6"]},
   callout={"text": "TOO LONG", "x": 0.5, "y": 0.4})
sh("twist", "It won't fit sideways in small cars.", "strip", "wide", "push", {"at": [0, 0, 0.7], "dist": 12, "yaw": 0, "pitch": 10, "lens": 26},
   callout={"text": "NO ROOM", "x": 0.5, "y": 0.4})
sh("twist", "So in the 1990s, most brands went V6.", "strip", "medium", "drift",
   {"at": [0.6, 2, 0.6], "dist": 11, "yaw": 10, "pitch": 9, "lens": 26}, callout={"text": "1990s: V6", "x": 0.5, "y": 0.4})
sh("payoff", "BMW never gave up the straight six.", "i6_bench", "medium", "orbit_r", BW(dist=2.2, yaw=6),
   moves=[{"id": "ci6", "run_to": 6, "t0": 0.2, "t1": 1.2}], callout={"text": "BMW", "x": 0.5, "y": 0.4})
sh("payoff", "Now Mercedes and Mazda build them again.", "garage", "wide", "push", GW,
   callout={"text": "IT'S BACK", "x": 0.5, "y": 0.42}, moves=[{"id": "i6", "run_to": 5, "t0": 0.1, "t1": 1.0}])
sh("payoff", "Same six. Smoother answer.", "strip", "medium", "drift",
   {"at": [-1.7, 4, 0.6], "to": [-1.7, 40, 0.6], "dist": 9, "yaw": 8, "pitch": 9, "lens": 26},
   moves=[{"id": "blue", "to": [-1.7, 48, 0], "t0": 0.1, "t1": 2.4, "ease": "out"}, {"id": "red", "to": [1.7, 40, 0], "t0": 0.2, "t1": 2.4, "ease": "in"}],
   sfx=[{"name": "car", "at": 0.1}])
sh("payoff", "Which six would you pick?", "garage", "wide", "pull", GW,
   moves=[{"id": "i6", "run_to": 5, "t0": 0.2, "t1": 1.0}, {"id": "v6", "run_to": 5, "t0": 0.2, "t1": 1.0}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
    for k, v in (("props", []), ("sfx", []), ("transition", "cut")):
        s.setdefault(k, v)
plan = {"id": "straight_six", "title": "Why a Straight Six Is Smoother Than a V6",
        "topic": "inline six vs V6: mirrored piston pairs give an inline six perfect primary and secondary balance; a V6 needs balance shafts; packaging",
        "hook_title": "SAME 6 CYLINDERS. WHY SMOOTHER?", "keywords": ["six", "straight", "V6", "shake", "balance", "BMW", "smooth", "long"],
        "cast": [], "channel": "channel4",
        "sources": ["https://en.wikipedia.org/wiki/Straight-six_engine", "https://en.wikipedia.org/wiki/V6_engine"],
        "places": PLACES, "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
