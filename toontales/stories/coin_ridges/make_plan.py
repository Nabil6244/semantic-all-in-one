"""Writes plan.json for the Channel 5 test Short 'Why Coins Have Ridges on Their Edges' (original topic).
    python3 toontales/stories/coin_ridges/make_plan.py && python3 -m toontales.plan.check toontales/stories/coin_ridges/plan.json --fix
Facts: hand-struck silver coins were worth their metal and had uneven edges, so 'clippers' snipped slivers off and
sold the silver; machine-struck (milled) coins with marked or reeded edges made clipping obvious (England from 1662,
the old hammered coins were called in by the Great Recoinage of 1696); Isaac Newton joined the Royal Mint in 1696
and pursued clippers and counterfeiters; today's base-metal coins keep reeding, which also helps people tell coins
apart by touch (a US dime is reeded, a penny smooth).
"""
import json
from pathlib import Path

Z = 0.9  # counter top
R = 0.0125


def coin(x, y, idn=None, z=Z, **kw):
    q = {"m": "@coin", "at": [x, y, z], "r": kw.pop("r", R), "mat": kw.pop("mat", "silver")}
    q.update(kw)
    if idn:
        q["id"] = idn
    return q


HAM = [coin(-0.045, 0.0, "h1", hammered=True, rot=20), coin(-0.005, 0.03, "h2", hammered=True, rot=80),
       coin(0.03, -0.012, "h3", hammered=True, rot=140), coin(-0.03, 0.06, "h4", hammered=True, rot=200, r=0.013)]
SCALE = [{"m": "@scale_stand", "at": [0.13, 0.16, Z]}, {"m": "@scale_beam", "at": [0.13, 0.16, Z + 0.16], "id": "beam"},
         coin(0.03, 0.16, "pan_full", z=Z + 0.0645, hammered=True, ride="beam"),
         coin(0.23, 0.16, "pan_clip", z=Z + 0.0645, hammered=True, clip=[90, 0.16], ride="beam")]
CLIP = [{"m": "@shears", "at": [-0.12, -0.005, Z], "rot": 0, "open": 26, "id": "shears"},
        coin(0.0, 0.0, "whole", hammered=True, rot=10),
        coin(0.0, 0.0, "clipped", hammered=True, rot=10, clip=[180, 0.14]),
        {"m": "@shavings", "at": [0.045, 0.02, Z], "n": 18, "r": 0.012, "id": "shav"},
        {"m": "@shavings", "at": [0.05, 0.06, Z], "n": 140, "r": 0.03, "seed": 9, "id": "heap"}]
SHRINK = [coin(-0.06 + i * 0.04, 0.0, f"s{i}", hammered=True, rot=i * 50, r=R * (1 - 0.07 * i),
               clip=[40 + i * 70, 0.05 * i] if i else None) for i in range(4)]
for q in SHRINK:
    if q.get("clip") is None:
        q.pop("clip")
PRESS = [coin(0.0, 0.0, "milled", reeds=110, r=0.0135),
         coin(0.06, 0.04, "edge", reeds=110, r=0.0135, tilt=90, z=Z + 0.0136),  # stands on its edge
         coin(-0.06, 0.03, "stack1", reeds=110), coin(-0.06, 0.03, "stack2", reeds=110, z=Z + 0.0022, rot=40),
         coin(-0.06, 0.03, "stack3", reeds=110, z=Z + 0.0044, rot=95),
         coin(0.0, 0.0, "milled_clip", reeds=110, r=0.0135, clip=[200, 0.12]),
         {"m": "@magnifier", "at": [-0.01, -0.035, Z + 0.035], "rot": -35, "id": "glass"}]
TODAY = [coin(-0.03, 0.0, "dime", z=1.0092, reeds=118, r=0.0091, h=0.00135, mat="steel", tilt=90),
         coin(0.03, 0.0, "penny", z=1.0096, r=0.0095, h=0.0015, mat="copper", tilt=90),
         {"m": "@box", "at": [0, 0.02, 0.96], "size": [0.3, 0.12, 0.04], "color": [0.42, 0.78, 0.76], "rough": 0.6}]

PLACES = {
    "desk": {"world": "dio_bar_counter", "add": HAM + SCALE, "prompt": "Old silver coins and a brass scale on a bar"},
    "clip": {"world": "dio_bar_counter", "add": CLIP, "prompt": "Shears clipping a silver coin"},
    "shrink": {"world": "dio_bar_counter", "add": SHRINK + SCALE[:2], "prompt": "Coins getting smaller"},
    "press": {"world": "dio_bar_counter", "add": PRESS, "prompt": "Milled coins with ridged edges"},
    "today": {"world": "dio_mint_studio", "add": TODAY, "prompt": "A ridged and a smooth modern coin"},
}


def L(at, dist=0.32, yaw=-8, pitch=24, lens=55, **kw):
    d = {"at": at, "dist": dist, "yaw": yaw, "pitch": pitch, "lens": lens}
    d.update(kw)
    return d


HIDE_CLIP = [{"id": "milled_clip", "hide": 99}]

SHOTS = [
    dict(beat="hook", text="Run your thumb around a coin.",
         set="press", camera="insert", move="push", look=L([0.06, 0.04, Z + 0.0135], dist=0.13, pitch=6, lens=70),
         moves=[{"id": "edge", "rot_to": 90, "t0": 0.0, "t1": 2.0}] + HIDE_CLIP),
    dict(beat="hook", text="Those tiny ridges are an old trick against thieves.", set="clip", camera="medium",
         move="push", look=L([0.02, 0.03, Z + 0.003], dist=0.2, pitch=32),
         moves=[{"id": "whole", "hide": 0}, {"id": "shav", "hide": 99}], overlay={"type": "stamp", "text": "THIEVES"}),
    dict(beat="hook", text="So why do coins have ridges at all?", set="press", camera="wide", move="pull",
         look=L([0.0, 0.02, Z + 0.01], dist=0.36, pitch=30), moves=list(HIDE_CLIP)),
    dict(beat="concept", text="Three hundred years ago, a silver coin was worth the silver inside it.", set="desk",
         camera="medium", move="push", look=L([-0.01, 0.02, Z + 0.004], dist=0.26, pitch=34)),
    dict(beat="concept", text="And coins were struck by hand, so every edge came out uneven.", set="desk",
         camera="insert", move="drift", look=L([0.03, -0.012, Z + 0.002], dist=0.11, pitch=40, lens=70),
         moves=[{"id": "h3", "to": [0.03, -0.012, Z], "rot_to": 260, "t0": 0.0, "t1": 3.4}]),
    dict(beat="setup", text="That gave thieves an idea.", set="clip", camera="medium", move="push",
         look=L([-0.03, 0.0, Z + 0.004], dist=0.3, pitch=30),
         moves=[{"id": "clipped", "hide": 99}, {"id": "shav", "hide": 99}, {"id": "heap", "hide": 99}]),
    dict(beat="setup", text="Snip a thin sliver off the edge.", set="clip", camera="insert", move="push",
         look=L([-0.01, 0.0, Z + 0.003], dist=0.2, pitch=32, lens=60),
         moves=[{"id": "shears", "to": [-0.075, -0.005, Z], "t0": 0.1, "t1": 0.9},
                {"id": "whole", "hide": 1.0}, {"id": "clipped", "show": 1.0},
                {"id": "shav", "grow": "all", "t0": 1.0, "t1": 1.5}, {"id": "heap", "hide": 99}]),
    dict(beat="setup", text="The coin still looked fine, so they spent it at full value.", set="clip",
         camera="medium", move="pan_r", look=L([0.0, 0.0, Z + 0.002], dist=0.22, pitch=36),
         moves=[{"id": "whole", "hide": 0}, {"id": "clipped", "to": [0.09, -0.03, Z], "t0": 0.6, "t1": 2.6},
                {"id": "heap", "hide": 99}]),
    dict(beat="con", text="Then they melted the clippings and sold the silver.", set="clip", camera="insert",
         move="push", look=L([0.045, 0.02, Z + 0.002], dist=0.13, pitch=40, lens=70),
         moves=[{"id": "whole", "hide": 0}, {"id": "heap", "hide": 99}]),
    dict(beat="con", text="Nobody noticed. The coin was only a little smaller.", set="clip", camera="insert",
         move="push", look=L([0.09, -0.03, Z + 0.002], dist=0.12, pitch=45, lens=70),
         moves=[{"id": "whole", "hide": 0}, {"id": "clipped", "to": [0.09, -0.03, Z], "t0": 0.0, "t1": 0.05},
                {"id": "heap", "hide": 99}]),
    dict(beat="con", text="Do it to enough coins, and the silver piles up.", set="clip", camera="medium",
         move="push", look=L([0.05, 0.05, Z + 0.004], dist=0.22, pitch=38),
         moves=[{"id": "whole", "hide": 0}, {"id": "shav", "hide": 0}, {"id": "heap", "grow": "all", "t0": 0.2,
                                                                            "t1": 2.4}],
         overlay={"type": "stamp", "text": "CLIPPING"}),
    dict(beat="escalate", text="Coins kept getting smaller,", set="shrink", camera="wide", move="pan_r",
         look=L([0.0, 0.0, Z + 0.002], dist=0.3, pitch=28)),
    dict(beat="escalate", text="so shopkeepers weighed every coin before they trusted it.", set="desk",
         camera="medium", move="push", look=L([0.13, 0.16, Z + 0.09], dist=0.42, pitch=8),
         moves=[{"id": "beam", "to": [0.13, 0.16, Z + 0.16], "tilt_to": -7, "t0": 0.6, "t1": 2.0, "ease": "out"}]),
    dict(beat="obstacle", text="Trade slowed to a crawl.", set="desk", camera="insert", move="drift",
         look=L([0.03, 0.16, Z + 0.07], dist=0.2, pitch=10, lens=60),
         moves=[{"id": "beam", "to": [0.13, 0.16, Z + 0.16], "tilt_from": -7, "tilt_to": -7, "t0": 0.0, "t1": 0.1}]),
    dict(beat="twist", text="The fix came from machines.", set="press", camera="medium", move="push",
         look=L([0.0, 0.0, Z + 0.004], dist=0.2, pitch=34),
         moves=[{"id": "milled", "grow": "all", "t0": 0.2, "t1": 0.9, "ease": "out"}] + HIDE_CLIP),
    dict(beat="twist", text="Mints began pressing coins in a perfect circle,", set="press", camera="insert",
         move="drift", look=L([0.0, 0.0, Z + 0.002], dist=0.12, pitch=55, lens=70), moves=list(HIDE_CLIP)),
    dict(beat="twist", text="with a ring of fine ridges all around the edge.", set="press", camera="insert",
         move="push", look=L([0.06, 0.04, Z + 0.0135], dist=0.1, pitch=4, lens=75),
         moves=[{"id": "edge", "rot_to": 120, "t0": 0.0, "t1": 4.0}] + HIDE_CLIP),
    dict(beat="twist", text="Now if anyone clipped one, the missing ridges gave it away.", set="press",
         camera="insert", move="push", look=L([0.0, 0.0, Z + 0.002], dist=0.13, pitch=50, lens=70),
         moves=[{"id": "milled", "hide": 0.0}, {"id": "milled_clip", "show": 0.0}]),
    dict(beat="payoff", text="In the 1690s, Isaac Newton joined England's Royal Mint and hunted down clippers.",
         set="press", camera="medium", move="orbit_r", look=L([-0.06, 0.03, Z + 0.004], dist=0.18, pitch=26),
         moves=list(HIDE_CLIP), overlay={"type": "stamp", "text": "1696"}),
    dict(beat="payoff", text="Clipping was treason. Caught clippers could be hanged.", set="clip", camera="medium",
         move="push", look=L([-0.07, 0.0, Z + 0.004], dist=0.22, pitch=26),
         moves=[{"id": "clipped", "hide": 99}, {"id": "shav", "hide": 99}]),
    dict(beat="payoff", text="Today, coins aren't made of silver anymore.", set="today", camera="wide",
         move="push", look=L([0.0, 0.0, 1.01], dist=0.22, yaw=0, pitch=6, lens=60)),
    dict(beat="payoff", text="But the ridges stayed.", set="today", camera="insert", move="push",
         look=L([-0.03, 0.0, 1.009], dist=0.09, yaw=-20, pitch=4, lens=75),
         moves=[{"id": "dime", "rot_to": 70, "t0": 0.0, "t1": 2.0}]),
    dict(beat="payoff", text="A dime is ridged. A penny is smooth.", set="today", camera="insert", move="pan_r",
         look=L([0.0, 0.0, 1.0095], dist=0.4, yaw=-6, pitch=5, lens=70),  # both coins: 6 cm apart
         overlay={"type": "arrow", "text": "RIDGED"}),
    dict(beat="payoff", text="They even help people tell coins apart by touch.", set="today", camera="medium",
         move="orbit_l", look=L([0.0, 0.0, 1.01], dist=0.4, yaw=-12, pitch=8, lens=60),
         moves=[{"id": "dime", "rot_to": -40, "t0": 0.0, "t1": 3.0}, {"id": "penny", "rot_to": 40, "t0": 0.0,
                                                                         "t1": 3.0}]),
    dict(beat="payoff", text="So those tiny ridges are still guarding your pocket change.", set="press",
         camera="wide", move="pull", look=L([0.03, 0.03, Z + 0.006], dist=0.3, pitch=20),
         moves=[{"id": "edge", "rot_to": 90, "t0": 0.0, "t1": 3.5}] + HIDE_CLIP),
]


def main():
    for i, s in enumerate(SHOTS, 1):
        s.setdefault("speaker", "narrator")
        for k, v in (("cast", []), ("props", []), ("sfx", []), ("transition", "cut")):
            s.setdefault(k, v)
        for mv in s.get("moves", []):  # rotations ride world.step: give them their own spot as "to"
            if "rot_to" in mv and not mv.get("to"):
                q = next(q for pl in PLACES.values() for q in pl["add"] if q.get("id") == mv["id"])
                mv["to"] = list(q["at"])
        s["id"] = f"s{i:02d}"
    plan = {"id": "coin_ridges", "title": "Why Coins Have Ridges on Their Edges",
            "topic": "coin clipping and milled / reeded coin edges (1600s-1690s), still on coins today",
            "hook_title": "WHY DO COINS HAVE RIDGES?",
            "keywords": ["ridges", "silver", "clip", "coin", "edge", "mint", "Newton", "thieves"],
            "cast": [], "channel": "channel5",
            "sources": ["https://en.wikipedia.org/wiki/Reeding", "https://en.wikipedia.org/wiki/Coin_clipping",
                        "https://en.wikipedia.org/wiki/Great_Recoinage_of_1696"],
            "places": PLACES, "shots": SHOTS}
    out = Path(__file__).with_name("plan.json")
    out.write_text(json.dumps(plan, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
