"""Ch5 Short: Why this soda bottle has a marble in its neck (Hiram Codd's 1872 bottle, still made as Ramune and goli soda).
Facts: Hiram Codd of London patented the bottle in 1872; it was filled upside down so the gas pressure pressed the glass marble
up against a rubber ring in the lip; opening meant pushing the marble down with a wooden plunger (a pop and a fizz); pinches
in the neck catch the marble while you pour; children smashed bottles for the marbles; Painter's crown cap (1892) took over;
Japan's Ramune and India's goli soda still use the marble seal.
"""
import json
from pathlib import Path

Z = 0.9  # counter top
MARBLE = [0.6, 0.9, 0.8]


def bottle(x, y, idn, z=Z, **kw):
    q = {"m": "@bottle", "at": [x, y, z], "style": "codd", "glass": kw.pop("glass", "clear"), "fill": kw.pop("fill", 0.7),
         "liquid": kw.pop("liquid", "water"), "id": idn}
    q.update(kw)
    return q


ROW = [bottle(-0.08, 0.06, "b1", glass="green", liquid="lemonade"), bottle(0.0, 0.05, "hero"), bottle(0.08, 0.06, "b3", glass="green", liquid="lemonade", fill=0.5)]
FLAT = [bottle(0.0, 0.04, "flat", glass="green", fill=0.0),
        {"m": "@cork", "at": [0.08, -0.02, Z], "id": "old_cork"}, {"m": "@cork", "at": [0.11, 0.0, Z], "id": "old_cork2"}]
UPSIDE = [bottle(0.0, 0.05, "inv", z=Z + 0.24, tilt=180), {"m": "@box", "at": [0.0, 0.05, Z], "size": [0.09, 0.09, 0.012], "color": [0.2, 0.2, 0.22]}]
OPEN = [bottle(0.0, 0.05, "pop"), {"m": "@ball", "at": [0.07, -0.02, Z], "r": 0.0085, "color": MARBLE, "id": "loose"}]
SMASH = [bottle(-0.02, 0.06, "whole", glass="green", liquid="lemonade"),
         {"m": "@ball", "at": [0.05, -0.02, Z], "r": 0.0085, "color": MARBLE, "id": "m1"},
         {"m": "@ball", "at": [0.075, 0.0, Z], "r": 0.0085, "color": [0.5, 0.7, 0.95], "id": "m2"},
         {"m": "@ball", "at": [0.1, -0.025, Z], "r": 0.0085, "color": MARBLE, "id": "m3"}]
CAP = [bottle(-0.05, 0.05, "old"), {"m": "@bottle", "at": [0.05, 0.05, Z], "style": "crown", "glass": "amber", "fill": 0.8, "liquid": "cola", "id": "crown"},
       {"m": "@cap", "at": [0.05, 0.05, Z + 0.236], "mat": "red_paint", "crimps": 21, "id": "cap"}]
TODAY = [{"m": "@box", "at": [0, 0.02, 0.96], "size": [0.3, 0.12, 0.04], "color": [0.42, 0.78, 0.76], "rough": 0.6},
         {"m": "@bottle", "at": [-0.04, 0.02, 1.0], "style": "codd", "glass": "clear", "fill": 0.75, "liquid": "water", "id": "ramune"},
         {"m": "@bottle", "at": [0.04, 0.02, 1.0], "style": "codd", "glass": "green", "fill": 0.75, "liquid": "lemonade", "id": "goli"}]
PLACES = {
    "row": {"world": "dio_bar_counter", "add": ROW, "prompt": "Three old marble-stoppered soda bottles on a walnut bar"},
    "flat": {"world": "dio_bar_counter", "add": FLAT, "prompt": "An empty bottle and dried-out corks"},
    "upside": {"world": "dio_bar_counter", "add": UPSIDE, "prompt": "A marble bottle standing upside down"},
    "open": {"world": "dio_bar_counter", "add": OPEN, "prompt": "A marble bottle being opened"},
    "smash": {"world": "dio_bar_counter", "add": SMASH, "prompt": "Glass marbles rolling beside a bottle"},
    "cap": {"world": "dio_bar_counter", "add": CAP, "prompt": "A marble bottle beside a crown-capped bottle"},
    "today": {"world": "dio_mint_studio", "add": TODAY, "prompt": "Two modern marble soda bottles on a mint plinth"},
}


def L(at, dist=0.32, yaw=-8, pitch=24, lens=55, **kw):
    d = {"at": at, "dist": dist, "yaw": yaw, "pitch": pitch, "lens": lens}
    d.update(kw)
    return d


NECK = lambda x=0.0, y=0.05, z=Z + 0.16: [x, y, z]
S = []
def sh(beat, text, place, cam, move, look, **kw):
    S.append({"beat": beat, "speaker": "narrator", "text": text, "set": place, "camera": cam, "move": move, "cast": [], "look": look, **kw})
sh("hook", "There's a glass marble stuck inside this bottle's neck.", "row", "insert", "push", L(NECK(), 0.12, -8, 8, 70),
   moves=[{"id": "hero", "rot_to": 60, "t0": 0, "t1": 2.4}], sfx=[{"name": "whoosh", "at": 0.1}])
sh("hook", "It can't fall out. It can't fall in. Why is it there?", "row", "medium", "crash_zoom", L([0.0, 0.05, Z + 0.12], 0.36, -8, 10, 50),
   callout={"text": "WHY?", "x": 0.5, "y": 0.36})
sh("concept", "In the 1800s, fizzy drinks had a big problem.", "flat", "medium", "push", L([0.04, 0.03, Z + 0.1], 0.34, -8, 12, 50))
sh("concept", "Keeping the bubbles in.", "flat", "insert", "crash_zoom", L([0.0, 0.04, Z + 0.25], 0.1, -10, 8, 70), callout={"text": "FIZZ", "x": 0.5, "y": 0.4})
sh("setup", "Corks dried out and shrank.", "flat", "insert", "push", L([0.095, -0.01, Z + 0.01], 0.08, 8, 40, 70),
   moves=[{"id": "old_cork", "rot_to": 90, "t0": 0, "t1": 1.8}])
sh("setup", "And the gas slowly leaked away.", "flat", "medium", "drift", L([0.0, 0.04, Z + 0.14], 0.3, 8, 10, 50), overlay={"type": "stamp", "text": "FLAT"})
sh("obstacle", "Bottlers had to lay them on their sides to keep corks wet.", "flat", "medium", "push", L([0.03, 0.02, Z + 0.06], 0.3, -8, 22, 50),
   moves=[{"id": "flat", "tilt_to": 90, "to": [0.0, 0.04, Z + 0.035], "t0": 0.4, "t1": 1.4}], sfx=[{"name": "thud", "at": 1.3}])
sh("obstacle", "Messy, slow and expensive.", "flat", "insert", "push", L([0.0, 0.04, Z + 0.035], 0.12, 10, 20, 65),
   moves=[{"id": "flat", "tilt_from": 90, "tilt_to": 90, "to": [0.0, 0.04, Z + 0.035], "t0": 0, "t1": 0.1}])
sh("con", "In 1872, a London inventor named Hiram Codd tried a marble.", "row", "medium", "orbit_r", L([0.0, 0.05, Z + 0.14], 0.3, -8, 8, 55),
   callout={"text": "HIRAM CODD 1872", "x": 0.5, "y": 0.34})
sh("con", "He pinched the neck so the marble couldn't escape.", "row", "insert", "push", L(NECK(), 0.09, 12, 6, 72), callout={"text": "PINCH", "x": 0.5, "y": 0.42})
sh("con", "And put a rubber ring inside the lip.", "row", "insert", "crash_zoom", L([0.0, 0.05, Z + 0.225], 0.07, -10, 10, 75), callout={"text": "RUBBER RING", "x": 0.5, "y": 0.42})
sh("con", "But how do you push a marble up and hold it there?", "row", "medium", "push", L([0.0, 0.05, Z + 0.16], 0.2, -8, 6, 60), overlay={"type": "circle", "text": "HOW?"}, freeze="WAIT...")
sh("escalate", "You don't. The fizz does.", "upside", "medium", "crash_zoom", L([0.0, 0.05, Z + 0.12], 0.3, -8, 8, 55), sfx=[{"name": "pop", "at": 0.4}])
sh("escalate", "The bottle is filled upside down.", "upside", "wide", "tilt_up", L([0.0, 0.05, Z + 0.12], 0.42, 8, 8, 45), overlay={"type": "arrow", "text": "UPSIDE DOWN"})
sh("escalate", "The marble drops onto the ring, and the gas pushes it tight.", "upside", "insert", "push", L([0.0, 0.05, Z + 0.025], 0.1, -8, 6, 72),
   hud={"label": "PRESSURE", "fmt": "SEALED", "from": 0, "to": 1, "max": 1, "color": "green"})
sh("twist", "The more fizz inside, the harder it seals.", "row", "insert", "push", L(NECK(z=Z + 0.2), 0.08, -12, 6, 72), overlay={"type": "arrow", "text": "TIGHTER"})
sh("twist", "To open it, you shove the marble down.", "open", "insert", "crash_zoom", L(NECK(), 0.1, 10, 8, 72), sfx=[{"name": "pop", "at": 0.5}])
sh("twist", "Pop, and the fizz rushes out.", "open", "medium", "push", L([0.0, 0.05, Z + 0.14], 0.24, -8, 8, 55), callout={"text": "POP!", "x": 0.5, "y": 0.36}, sfx=[{"name": "splash", "at": 0.3}])
sh("twist", "Little dents in the neck catch the marble while you drink.", "open", "insert", "push", L(NECK(z=Z + 0.17), 0.08, 14, 6, 72),
   moves=[{"id": "pop", "tilt_to": 35, "t0": 0.3, "t1": 1.6}])
sh("payoff", "There was one flaw.", "smash", "medium", "push", L([0.04, 0.02, Z + 0.06], 0.3, -8, 18, 50))
sh("payoff", "Children smashed the bottles to steal the marbles.", "smash", "insert", "crash_zoom", L([0.075, -0.01, Z + 0.008], 0.1, -8, 30, 70),
   moves=[{"id": "m1", "to": [0.02, -0.04, Z], "rot_to": 300, "t0": 0.2, "t1": 1.6, "ease": "out"}], sfx=[{"name": "glass", "at": 0.2}])
sh("payoff", "Then the crown cap arrived, and most marble bottles vanished.", "cap", "medium", "orbit_l", L([0.0, 0.05, Z + 0.14], 0.36, -8, 8, 50))
sh("payoff", "But not all of them.", "cap", "insert", "push", L([-0.05, 0.05, Z + 0.16], 0.1, 10, 8, 70), moves=[{"id": "old", "rot_to": 90, "t0": 0, "t1": 1.8}])
sh("payoff", "In Japan it's called Ramune. In India, goli soda.", "today", "medium", "push", L([0.0, 0.02, 1.13], 0.36, -8, 6, 50),
   callout={"text": "RAMUNE / GOLI SODA", "x": 0.5, "y": 0.34})
sh("payoff", "Still sealed the same way, with a marble pushed up by the fizz.", "today", "insert", "pull", L([-0.04, 0.02, 1.16], 0.1, -8, 6, 70),
   moves=[{"id": "ramune", "rot_to": 90, "t0": 0, "t1": 2.4}])
sh("payoff", "Now you know why that marble is stuck in the neck.", "row", "medium", "pull", L([0.0, 0.05, Z + 0.12], 0.4, -8, 10, 50),
   moves=[{"id": "hero", "rot_to": 120, "t0": 0, "t1": 3.0}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
plan = {"id": "codd_marble", "title": "Why This Bottle Has a Marble in Its Neck", "topic": "Hiram Codd's 1872 marble-stoppered soda bottle, sealed by its own gas pressure, still used as Ramune and goli soda",
        "hook_title": "WHY IS THERE A MARBLE?", "keywords": ["marble", "bottle", "fizz", "Codd", "seal", "neck", "Ramune", "pressure"],
        "cast": [], "channel": "channel5", "sources": ["https://en.wikipedia.org/wiki/Codd-neck_bottle", "https://en.wikipedia.org/wiki/Ramune"],
        "places": PLACES, "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
