"""Ch5 story: Why bottle caps have 21 teeth. python3 toontales/stories/cap_teeth/make_plan.py -> plan.json"""
import json
from pathlib import Path
Z = 0.9
bar = lambda add, prompt: {"world": "dio_bar_counter", "add": add, "prompt": prompt}
places = {
 "lineup": bar([
   {"m": "@bottle", "at": [-0.12, 0.05, Z], "style": "cork", "glass": "green", "fill": 0.75, "liquid": "amber", "id": "b_cork"},
   {"m": "@bottle", "at": [0.0, 0.05, Z], "style": "codd", "glass": "clear", "fill": 0.7, "liquid": "water", "id": "b_codd"},
   {"m": "@bottle", "at": [0.12, 0.05, Z], "style": "crown", "glass": "amber", "fill": 0.8, "liquid": "cola", "id": "b_crown"},
   {"m": "@cap", "at": [0.12, 0.05, Z + 0.236], "mat": "red_paint", "crimps": 21, "id": "cap_on"}],
   "Three old soda bottles on a walnut bar: cork, marble and crown cap"),
 "cork": bar([
   {"m": "@bottle", "at": [0.0, 0.05, Z], "style": "cork", "glass": "green", "fill": 0.75, "liquid": "amber", "id": "bc"},
   {"m": "@cork", "at": [0.0, 0.05, Z + 0.215], "id": "plug"},
   {"m": "@cork", "at": [0.09, -0.02, Z], "id": "spare"}],
   "A green glass bottle with a cork stopper"),
 "codd": bar([
   {"m": "@bottle", "at": [0.0, 0.05, Z], "style": "codd", "glass": "clear", "fill": 0.7, "liquid": "water", "id": "bm"},
   {"m": "@bottle", "at": [0.1, 0.1, Z], "style": "codd", "glass": "green", "fill": 0.5, "liquid": "lemonade", "id": "bm2"}],
   "A Codd bottle with a glass marble in its neck"),
 "caps": bar([
   {"m": "@cap", "at": [0.0, 0.0, Z], "mat": "red_paint", "crimps": 21, "id": "c21"},
   {"m": "@cap", "at": [-0.05, 0.03, Z], "mat": "steel", "crimps": 21, "id": "c_a"},
   {"m": "@cap", "at": [0.05, 0.03, Z], "mat": "gold", "crimps": 21, "id": "c_b"},
   {"m": "@cap", "at": [-0.03, -0.04, Z], "mat": "steel", "crimps": 21, "id": "c_c"},
   {"m": "@cap", "at": [0.04, -0.035, Z], "mat": "red_paint", "crimps": 21, "id": "c_d"}],
   "Crown caps scattered on a walnut bar"),
 "teeth": bar([
   {"m": "@cap", "at": [-0.05, 0.0, Z], "mat": "steel", "crimps": 14, "id": "few"},
   {"m": "@cap", "at": [0.0, 0.0, Z], "mat": "red_paint", "crimps": 21, "id": "just"},
   {"m": "@cap", "at": [0.05, 0.0, Z], "mat": "steel", "crimps": 30, "id": "many"}],
   "Three crown caps with different numbers of teeth"),
 "pop": {"world": "dio_mint_studio", "add": [
   {"m": "@box", "at": [0, 0.02, 0.96], "size": [0.3, 0.14, 0.04], "color": [0.42, 0.78, 0.76], "rough": 0.6},
   {"m": "@bottle", "at": [0.0, 0.02, 1.0], "style": "crown", "glass": "green", "fill": 0.82, "liquid": "lemonade", "id": "hero"},
   {"m": "@cap", "at": [0.0, 0.02, 1.236], "mat": "gold", "crimps": 21, "id": "hero_cap"}
   ], "prompt": "A green soda bottle with a gold crown cap in a mint studio"},
 "razor": {"world": "dio_mint_studio", "add": [
   {"m": "@box", "at": [0, 0.02, 0.96], "size": [0.3, 0.14, 0.04], "color": [0.42, 0.78, 0.76], "rough": 0.6},
   {"m": "@cap", "at": [-0.03, 0.02, 1.0], "mat": "steel", "crimps": 21, "id": "rc"},
   {"m": "@coin", "at": [0.035, 0.02, 1.0], "r": 0.016, "h": 0.0012, "mat": "steel", "hole": 0.004, "id": "blade"}
   ], "prompt": "A crown cap next to a thin steel disc"},
}
L = lambda at, d, yaw=-8, pitch=20, lens=55: {"at": at, "dist": d, "yaw": yaw, "pitch": pitch, "lens": lens}
S = []
def sh(beat, text, place, cam, move, look, **kw):
    S.append({"beat": beat, "speaker": "narrator", "text": text, "set": place, "camera": cam, "move": move, "cast": [], "look": look, **kw})
sh("hook", "Count the teeth on a bottle cap.", "caps", "insert", "push", L([0, 0, Z + 0.004], 0.08, -6, 60, 70),
   moves=[{"id": "c21", "rot_to": 120, "to": [0, 0, Z], "t0": 0, "t1": 2.4}], sfx=[{"name": "whoosh", "at": 0.1}])
sh("hook", "No matter the brand, it's almost always twenty one.", "caps", "insert", "crash_zoom", L([0, 0, Z + 0.004], 0.06, 10, 70, 75),
   hud={"label": "TEETH", "fmt": "{v} TEETH", "from": 0, "to": 21, "max": 30, "color": "green", "t0": 0.05, "t1": 0.7})
sh("hook", "Not twenty. Not thirty. Why?", "teeth", "medium", "pull", L([0, 0, Z + 0.005], 0.2, -8, 40, 55), freeze="WAIT...")
sh("concept", "In the 1800s, sealing a fizzy drink was a real problem.", "lineup", "wide", "push", L([0, 0.05, Z + 0.12], 0.62, -8, 8, 45))
sh("concept", "Some were plugged with corks, like wine.", "cork", "medium", "push", L([0, 0.05, Z + 0.17], 0.3, -10, 10, 55))
sh("setup", "But corks dried out, shrank, and all the fizz escaped.", "cork", "insert", "push", L([0, 0.05, Z + 0.215], 0.12, -14, 12, 70),
   moves=[{"id": "plug", "to": [0, 0.05, Z + 0.245], "t0": 0.4, "t1": 1.8, "ease": "out"}])
sh("setup", "And a cork could make the soda taste like wood.", "cork", "medium", "drift", L([0.04, 0.02, Z + 0.06], 0.3, -6, 18, 55), overlay={"type": "stamp", "text": "YUCK"})
sh("setup", "Others trapped a glass marble in the neck.", "codd", "medium", "push", L([0, 0.05, Z + 0.15], 0.28, -8, 8, 55), overlay={"type": "arrow", "text": "MARBLE"})
sh("con", "Bottlers hated them. Kids smashed the bottles just to get the marble out.", "codd", "insert", "crash_zoom", L([0, 0.05, Z + 0.158], 0.1, -12, 6, 70),
   moves=[{"id": "bm", "tilt_to": 25, "t0": 0.3, "t1": 1.0}])
sh("escalate", "Then in 1892, a Baltimore inventor named William Painter had a better idea.", "lineup", "medium", "push", L([0.12, 0.05, Z + 0.2], 0.25, -8, 10, 55), overlay={"type": "stamp", "text": "1892"})
sh("escalate", "A thin metal cap, crimped tight around the lip.", "pop", "insert", "push", L([0, 0.02, 1.236], 0.1, -10, 18, 70),
   moves=[{"id": "hero_cap", "to": [0, 0.02, 1.236], "rot_to": 60, "t0": 0, "t1": 2.0}])
sh("escalate", "With a cork disc inside to seal it.", "caps", "insert", "push", L([-0.05, 0.03, Z + 0.004], 0.07, -6, 75, 75),
   moves=[{"id": "c_a", "to": [-0.05, 0.03, Z + 0.0065], "tilt_to": 180, "t0": 0, "t1": 0.8}])
sh("escalate", "He called it the crown cork.", "pop", "medium", "orbit_r", L([0, 0.02, 1.15], 0.4, -8, 6, 50), callout={"text": "CROWN CORK", "x": 0.5, "y": 0.36})
sh("obstacle", "But how many teeth?", "teeth", "medium", "push", L([0, 0, Z + 0.005], 0.18, -8, 45, 55))
sh("obstacle", "Too few, and the seal leaks.", "teeth", "insert", "crash_zoom", L([-0.05, 0, Z + 0.004], 0.07, -8, 55, 75),
   hud={"label": "PRESSURE", "fmt": "{v}% FIZZ LEFT", "from": 100, "to": 40, "max": 100, "color": "red"})
sh("obstacle", "Too many, and the cap grips so hard you can barely pop it off.", "teeth", "insert", "push", L([0.05, 0, Z + 0.004], 0.07, 8, 55, 75), hud={"label": "GRIP", "fmt": "{v}% GRIP", "from": 40, "to": 100, "max": 100, "color": "red"})
sh("twist", "Painter's first caps had twenty four.", "teeth", "medium", "push", L([0, 0, Z + 0.005], 0.16, -8, 50, 55),
   hud={"label": "TEETH", "fmt": "{v} TEETH", "from": 0, "to": 24, "max": 30, "color": "orange"})
sh("twist", "Later, as bottling machines got faster, caps with twenty one teeth worked best.", "caps", "medium", "drift", L([0, 0, Z + 0.004], 0.2, -8, 40, 55),
   hud={"label": "TEETH", "fmt": "{v} TEETH", "from": 24, "to": 21, "max": 30, "color": "green"})
sh("twist", "So twenty one became the standard.", "teeth", "insert", "crash_zoom", L([0, 0, Z + 0.004], 0.06, -8, 62, 75), overlay={"type": "stamp", "text": "21"})
sh("payoff", "And the twist? Painter's salesman watched those caps get thrown away.", "razor", "medium", "push", L([0, 0.02, 1.005], 0.2, -8, 30, 55))
sh("payoff", "His name was King Gillette.", "razor", "insert", "push", L([0.035, 0.02, 1.001], 0.08, -8, 50, 70), callout={"text": "GILLETTE", "x": 0.5, "y": 0.38})
sh("payoff", "Use it once, then toss it. What a business.", "razor", "medium", "drift", L([0, 0.02, 1.005], 0.16, 8, 35, 55), overlay={"type": "stamp", "text": "USE ONCE"})
sh("payoff", "So he invented the throwaway razor blade.", "razor", "insert", "crash_zoom", L([0.035, 0.02, 1.001], 0.06, 10, 60, 75),
   moves=[{"id": "blade", "rot_to": 90, "to": [0.035, 0.02, 1.0], "t0": 0, "t1": 2.0}])
sh("payoff", "Next time you pop one open, count them. Twenty one.", "pop", "wide", "pull", L([0, 0.02, 1.15], 0.5, -8, 6, 45),
   moves=[{"id": "hero_cap", "to": [0, 0.02, 1.33], "rot_to": 200, "t0": 0.3, "t1": 1.4, "ease": "out"}], sfx=[{"name": "pop", "at": 0.3}])
sh("payoff", "Twenty one tiny teeth, holding in all that fizz.", "caps", "insert", "pull", L([0, 0, Z + 0.004], 0.1, -6, 60, 70),
   moves=[{"id": "c21", "rot_to": 240, "to": [0, 0, Z], "t0": 0, "t1": 2.4}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
plan = {"id": "cap_teeth", "title": "Why Bottle Caps Have 21 Teeth", "topic": "William Painter's crown cork (1892) and why 21 crimps became standard",
        "hook_title": "WHY 21 TEETH?", "keywords": ["teeth", "cap", "cork", "fizz", "marble", "Painter", "twenty", "Gillette"],
        "cast": [], "channel": "channel5", "sources": ["https://en.wikipedia.org/wiki/Bottle_cap", "https://en.wikipedia.org/wiki/William_Painter_(inventor)"],
        "places": places, "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
