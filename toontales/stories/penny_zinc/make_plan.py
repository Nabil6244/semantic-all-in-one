"""Ch5 Short: Why the US penny is mostly zinc (1982 switch; 1943 steel cents; cost 3.69 cents in 2024; last circulating penny 2025).
Facts: 1962-1982 cents were 95% copper (3.11 g); mid-1982 onward 97.5% zinc core plated with copper (2.5 g); 1943 cents were
zinc-coated steel because copper went to the war, and they stick to a magnet; the US Mint's 2024 report put a cent's cost at
3.69 cents; the Treasury ended penny production for circulation and the last one was struck in Philadelphia in November 2025.
"""
import json
from pathlib import Path

Z = 0.9  # counter top
R = 0.0095  # a cent is 19.05 mm across


def coin(x, y, idn=None, z=Z, **kw):
    q = {"m": "@coin", "at": [x, y, z], "r": kw.pop("r", R), "h": kw.pop("h", 0.0015), "mat": kw.pop("mat", "copper")}
    q.update(kw)
    if idn:
        q["id"] = idn
    return q


SCALE = [{"m": "@scale_stand", "at": [0.13, 0.16, Z]}, {"m": "@scale_beam", "at": [0.13, 0.16, Z + 0.16], "id": "beam"},
         coin(0.03, 0.16, "pan_old", z=Z + 0.0645, ride="beam"),
         coin(0.23, 0.16, "pan_new", z=Z + 0.0645, ride="beam")]
PILE = [coin(-0.05 + 0.022 * (i % 5), -0.01 + 0.022 * (i // 5), f"p{i}", rot=i * 37) for i in range(10)]
CUT = [coin(-0.03, 0.0, "whole"), coin(0.03, 0.0, "cut", clip=[180, 0.45]),
       coin(0.03, 0.0, "core", r=R * 0.93, h=0.0013, mat="silver", z=Z + 0.0001),
       {"m": "@shears", "at": [0.1, -0.01, Z], "rot": 180, "open": 20, "id": "shears"},
       {"m": "@magnifier", "at": [0.0, -0.04, Z + 0.035], "rot": -30, "id": "glass"}]
STEEL = [coin(-0.03, 0.0, "steel43", mat="steel"), coin(0.03, 0.0, "copper82"),
         {"m": "@magnet", "at": [-0.03, 0.02, Z + 0.045], "w": 0.05, "id": "mag"}]
HERO = [coin(0.0, 0.0, "hero", z=1.0096, tilt=90),
        {"m": "@box", "at": [0, 0.02, 0.96], "size": [0.3, 0.12, 0.04], "color": [0.42, 0.78, 0.76], "rough": 0.6}]
LAST = [coin(-0.03, 0.0, "last", z=1.0096, tilt=90), coin(0.03, 0.0, "nickel", z=1.0106, r=0.0106, h=0.00195, mat="silver", tilt=90),
        {"m": "@box", "at": [0, 0.02, 0.96], "size": [0.3, 0.12, 0.04], "color": [0.42, 0.78, 0.76], "rough": 0.6}]
PLACES = {
    "scale": {"world": "dio_bar_counter", "add": SCALE, "prompt": "A brass balance with a penny on each pan"},
    "pile": {"world": "dio_bar_counter", "add": PILE, "prompt": "A pile of shiny copper pennies on a walnut bar"},
    "cut": {"world": "dio_bar_counter", "add": CUT, "prompt": "A penny cut open showing its silver zinc core"},
    "war": {"world": "dio_bar_counter", "add": STEEL, "prompt": "A grey 1943 steel cent and a copper cent under a magnet"},
    "hero": {"world": "dio_mint_studio", "add": HERO, "prompt": "One penny standing on edge in a mint studio"},
    "last": {"world": "dio_mint_studio", "add": LAST, "prompt": "A penny beside a nickel on a mint plinth"},
}


def L(at, dist=0.32, yaw=-8, pitch=24, lens=55, **kw):
    d = {"at": at, "dist": dist, "yaw": yaw, "pitch": pitch, "lens": lens}
    d.update(kw)
    return d


TIP = lambda a, b, t0=0.4, t1=1.8: [{"id": "beam", "to": [0.13, 0.16, Z + 0.16], "tilt_from": a, "tilt_to": b, "t0": t0, "t1": t1, "ease": "out"}]
SC = [0.13, 0.16, Z + 0.1]
S = []
def sh(beat, text, place, cam, move, look, **kw):
    S.append({"beat": beat, "speaker": "narrator", "text": text, "set": place, "camera": cam, "move": move, "cast": [], "look": look, **kw})
sh("hook", "Two pennies on a scale. Same coin. One is heavier.", "scale", "medium", "push", L(SC, 0.42, -6, 12, 45), moves=TIP(0, -7))
sh("hook", "So what's hiding inside the light one?", "scale", "insert", "crash_zoom", L([0.23, 0.16, Z + 0.07], 0.12, -8, 20, 70),
   moves=TIP(-7, -7, 0, 0.1), callout={"text": "?", "x": 0.5, "y": 0.4})
sh("concept", "For years, the American penny was almost pure copper.", "pile", "medium", "push", L([0.0, 0.01, Z + 0.004], 0.22, -8, 40, 55),
   moves=[{"id": "p0", "rot_to": 120, "t0": 0, "t1": 2.0}])
sh("concept", "Heavy, shiny, solid copper almost all the way through.", "hero", "insert", "orbit_l", L([0.0, 0.0, 1.0096], 0.1, -8, 6, 70))
sh("concept", "About ninety five percent.", "pile", "insert", "crash_zoom", L([-0.006, 0.01, Z + 0.003], 0.09, -6, 55, 70),
   hud={"label": "COPPER", "fmt": "{v}% COPPER", "from": 0, "to": 95, "max": 100, "color": "orange", "t0": 0.05, "t1": 0.7})
sh("concept", "A cent was worth a cent, and it cost less than that to make.", "hero", "medium", "orbit_r", L([0.0, 0.0, 1.012], 0.2, -8, 6, 60))
sh("setup", "Then, in the late 1970s, copper prices shot up.", "pile", "wide", "pull", L([0.0, 0.01, Z + 0.01], 0.4, -8, 22, 45),
   callout={"text": "COPPER UP", "x": 0.5, "y": 0.38})
sh("setup", "The metal in a penny was almost worth more than the penny.", "pile", "insert", "push", L([0.03, 0.0, Z + 0.003], 0.08, 10, 55, 70),
   callout={"text": "1¢ ?", "x": 0.5, "y": 0.4})
sh("obstacle", "People could melt coins for profit.", "cut", "medium", "push", L([0.0, 0.0, Z + 0.01], 0.22, -8, 35, 55))
sh("obstacle", "And the Mint was losing money on every one.", "pile", "medium", "drift", L([0.0, 0.01, Z + 0.004], 0.26, 8, 30, 55), moves=[{"id": "p3", "rot_to": 90, "t0": 0, "t1": 2.4}],
   overlay={"type": "stamp", "text": "LOSS"})
sh("con", "They'd tried other metals before.", "war", "medium", "push", L([0.0, 0.0, Z + 0.02], 0.24, -8, 25, 55))
sh("con", "In 1943, copper went to war for bullet casings.", "war", "insert", "push", L([-0.03, 0.0, Z + 0.003], 0.08, -8, 55, 70),
   callout={"text": "1943", "x": 0.5, "y": 0.36})
sh("con", "So pennies were made of steel, coated in zinc.", "war", "insert", "crash_zoom", L([-0.03, 0.0, Z + 0.003], 0.06, 8, 60, 75),
   moves=[{"id": "steel43", "rot_to": 90, "t0": 0, "t1": 1.6}])
sh("con", "They stuck to magnets.", "war", "medium", "push", L([-0.03, 0.01, Z + 0.03], 0.14, -10, 15, 60),
   moves=[{"id": "steel43", "to": [-0.03, 0.02, Z + 0.042], "t0": 0.4, "t1": 0.9, "ease": "in"}], sfx=[{"name": "ding", "at": 0.9}])
sh("con", "People mistook them for dimes. They lasted one year.", "war", "medium", "drift", L([0.0, 0.0, Z + 0.01], 0.2, 8, 30, 55),
   overlay={"type": "cross", "text": "ONE YEAR"}, moves=[{"id": "copper82", "rot_to": 120, "t0": 0, "t1": 2.6}])
sh("escalate", "So in 1982, the Mint tried something sneaky.", "cut", "medium", "push", L([0.0, 0.0, Z + 0.006], 0.2, -8, 30, 55),
   callout={"text": "1982", "x": 0.5, "y": 0.36}, freeze="WAIT...")
sh("escalate", "A cheap zinc coin.", "cut", "insert", "crash_zoom", L([0.03, 0.0, Z + 0.002], 0.07, 6, 60, 75),
   moves=[{"id": "shears", "to": [0.06, -0.01, Z], "t0": 0.0, "t1": 0.6}], sfx=[{"name": "scratch", "at": 0.5}])
sh("escalate", "Wearing a paper-thin coat of copper.", "cut", "insert", "push", L([0.03, 0.0, Z + 0.002], 0.06, -14, 62, 75),
   hud={"label": "ZINC INSIDE", "fmt": "{v}% ZINC", "from": 0, "to": 97.5, "max": 100, "color": "green", "t0": 0.1, "t1": 0.8})
sh("twist", "It looks the same, but it weighs less. 2.5 grams, not 3.1.", "scale", "medium", "push", L(SC, 0.36, 8, 12, 50), moves=TIP(0, -7, 0.3, 1.6))
sh("twist", "That's your scale mystery solved.", "scale", "insert", "pull", L([0.03, 0.16, Z + 0.07], 0.12, -8, 20, 70), moves=TIP(-7, -7, 0, 0.1))
sh("payoff", "But zinc got expensive too.", "pile", "medium", "push", L([0.0, 0.01, Z + 0.004], 0.24, -8, 35, 55))
sh("payoff", "By 2024, one penny cost almost four cents to make.", "hero", "insert", "crash_zoom", L([0.0, 0.0, 1.0096], 0.09, -6, 6, 70),
   hud={"label": "COST", "fmt": "{v}¢ EACH", "from": 1, "to": 3.69, "max": 5, "color": "red"})
sh("payoff", "So in 2025, America struck its last penny for circulation.", "last", "medium", "orbit_l", L([0.0, 0.0, 1.012], 0.22, -8, 6, 55),
   callout={"text": "LAST PENNY", "x": 0.5, "y": 0.36})
sh("payoff", "It was struck in Philadelphia, that November.", "last", "insert", "push", L([-0.03, 0.0, 1.0096], 0.08, -10, 6, 70),
   moves=[{"id": "last", "rot_to": 60, "t0": 0, "t1": 2.0}])
sh("payoff", "The pennies in your pocket still spend.", "hero", "medium", "pull", L([0.0, 0.0, 1.012], 0.24, 8, 6, 55),
   moves=[{"id": "hero", "rot_to": 90, "t0": 0, "t1": 2.0}])
sh("payoff", "Weigh one, and you'll know which kind you've got.", "scale", "wide", "pull", L(SC, 0.5, -6, 12, 45),
   moves=TIP(0, -7, 0.3, 1.6))
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
plan = {"id": "penny_zinc", "title": "Why Your Penny Is Secretly Zinc", "topic": "The 1982 switch of the US cent from 95% copper to copper-plated zinc, the 1943 steel cent, and the end of penny production in 2025",
        "hook_title": "WHY IS ONE LIGHTER?", "keywords": ["penny", "copper", "zinc", "steel", "Mint", "1982", "scale", "magnet"],
        "cast": [], "channel": "channel5", "sources": ["https://en.wikipedia.org/wiki/Penny_(United_States_coin)", "https://en.wikipedia.org/wiki/1943_steel_cent"],
        "places": PLACES, "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
