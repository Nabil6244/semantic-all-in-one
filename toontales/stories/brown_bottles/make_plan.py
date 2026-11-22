"""Channel 5 Short 'Why Beer Bottles Are Brown' (original topic).
    python3 toontales/stories/brown_bottles/make_plan.py && python3 -m toontales.plan.check toontales/stories/brown_bottles/plan.json --fix
Facts: blue and ultraviolet light (roughly 350-500 nm) lets riboflavin in beer break down hop bitter compounds
(iso-alpha acids) into 3-methyl-2-butene-1-thiol, a sulfur compound related to skunk spray, noticeable at tiny
(parts-per-trillion) levels; in strong sunlight it can start within minutes ('lightstruck' / 'skunked' beer).
Brown (amber) glass blocks most of that light, green much less, clear almost none. Some brewers who sell beer in
clear bottles use chemically modified hop extracts (reduced iso-alpha acids) that light cannot break down this way.
"""
import json
from pathlib import Path

Z = 0.9  # counter top
CAP_Z = Z + 0.236


def bottle(x, glass, idn, y=0.05, **kw):
    return {"m": "@bottle", "at": [x, y, Z], "style": "crown", "glass": glass, "fill": 0.8, "liquid": "amber", "id": idn, **kw}


def cap(x, idn, y=0.05, mat="gold"):
    return {"m": "@cap", "at": [x, y, CAP_Z], "mat": mat, "crimps": 21, "id": idn}


TRIO = [bottle(-0.12, "clear", "clear"), bottle(0.0, "green", "green"), bottle(0.12, "amber", "brown"),
        cap(-0.12, "cap_c"), cap(0.0, "cap_g", mat="red_paint"), cap(0.12, "cap_b", mat="steel")]
ONE = [bottle(0.0, "clear", "solo"), cap(0.0, "cap_s")]
HOPS = [{"m": "@ball", "at": [-0.06 + 0.03 * i, -0.04 + 0.012 * (i % 2), Z], "r": 0.011, "color": [0.45, 0.68, 0.2],
         "id": f"hop{i}"} for i in range(5)]
LAB = [bottle(-0.05, "clear", "lab_c"), bottle(0.05, "amber", "lab_b"), cap(-0.05, "cap_lc"), cap(0.05, "cap_lb", mat="steel"),
       {"m": "@magnifier", "at": [0.0, -0.07, Z + 0.035], "rot": -30, "id": "glass"}]

PLACES = {
    "trio": {"world": "dio_bar_counter", "add": TRIO, "prompt": "Clear, green and brown beer bottles on a walnut bar"},
    "solo": {"world": "dio_bar_counter", "add": ONE, "prompt": "One clear bottle of beer on the bar"},
    "hops": {"world": "dio_mint_studio", "add": HOPS + [bottle(0.08, "amber", "hb", y=0.02), cap(0.08, "cap_h", y=0.02, mat="steel")],
             "prompt": "Green hop cones beside a brown beer bottle"},
    "lab": {"world": "dio_mint_studio", "add": LAB, "prompt": "A clear and a brown bottle under a magnifier"},
}


def L(at, dist=0.32, yaw=-8, pitch=20, lens=55, **kw):
    d = {"at": at, "dist": dist, "yaw": yaw, "pitch": pitch, "lens": lens}
    d.update(kw)
    return d


MID = Z + 0.12
SHOTS = [
    dict(beat="hook", text="Leave this beer in the sun for a few minutes.",
         set="solo", camera="medium", move="push", look=L([0.0, 0.05, MID], dist=0.5, pitch=10),
         overlay={"type": "chalk", "text": "5 MINUTES OF SUN"}),
    dict(beat="hook", text="It starts to smell like a skunk.", set="solo", camera="close", move="crash_zoom",
         look=L([0.0, 0.05, Z + 0.2], dist=0.22, pitch=6, lens=65), overlay={"type": "stamp", "text": "SKUNKED"}),
    dict(beat="hook", text="Same beer, same sun. This brown one doesn't.", set="trio", camera="insert", move="push",
         look=L([0.12, 0.05, MID], dist=0.32, pitch=8, lens=60), overlay={"type": "label", "text": "STILL FRESH"}),
    dict(beat="hook", text="So why are beer bottles brown?", set="trio", camera="wide", move="pull",
         look=L([0.0, 0.05, MID], dist=0.85, pitch=8), overlay={"type": "circle", "text": "WHY BROWN?"}),
    dict(beat="concept", text="It starts with hops, the flowers that make beer bitter.", set="hops", camera="medium",
         move="push", look=L([-0.0, -0.035, Z + 0.02], dist=0.28, pitch=30), overlay={"type": "label", "text": "HOPS"}),
    dict(beat="concept", text="Their bitter part is a fragile molecule.", set="hops", camera="insert", move="drift",
         look=L([-0.03, -0.035, Z + 0.012], dist=0.14, pitch=34, lens=70),
         moves=[{"id": "hop1", "to": [-0.03, -0.028, Z], "rot_to": 120, "t0": 0.0, "t1": 2.6}]),
    dict(beat="setup", text="Beer also carries a vitamin, riboflavin.", set="lab", camera="medium", move="push",
         look=L([-0.05, 0.05, MID], dist=0.36, pitch=10), overlay={"type": "label", "text": "VITAMIN B2"}),
    dict(beat="setup", text="It soaks up blue and ultraviolet light.", set="lab", camera="insert", move="push",
         look=L([-0.05, 0.05, Z + 0.1], dist=0.2, pitch=8, lens=65), overlay={"type": "arrow", "text": "UV LIGHT"}),
    dict(beat="con", text="Then it passes that energy on.", set="lab", camera="close", move="crash_zoom",
         look=L([-0.05, 0.05, Z + 0.08], dist=0.14, pitch=10, lens=70), overlay={"type": "arrow", "text": "ENERGY"}),
    dict(beat="con", text="The hop molecule snaps in half.", set="hops", camera="insert", move="crash_zoom",
         look=L([0.0, -0.035, Z + 0.012], dist=0.12, pitch=36, lens=70), overlay={"type": "stamp", "text": "SNAP"},
         moves=[{"id": "hop2", "to": [0.03, -0.06, Z], "t0": 0.2, "t1": 0.8, "ease": "out"},
                {"id": "hop3", "to": [0.05, 0.0, Z], "t0": 0.2, "t1": 0.8, "ease": "out"}]),
    dict(beat="con", text="One piece grabs a sulfur atom.", set="hops", camera="close", move="push",
         look=L([0.03, -0.05, Z + 0.012], dist=0.16, pitch=30, lens=65), overlay={"type": "label", "text": "+ SULFUR"}),
    dict(beat="con", text="And becomes a close cousin of skunk spray.", set="solo", camera="medium", move="push",
         look=L([0.0, 0.05, MID], dist=0.36, pitch=8), overlay={"type": "stamp", "text": "SKUNK"}, freeze="WAIT..."),
    dict(beat="escalate", text="Your nose can smell it at a few parts per trillion.", set="solo", camera="close",
         move="crash_zoom", look=L([0.0, 0.05, Z + 0.2], dist=0.2, pitch=6, lens=65),
         overlay={"type": "chalk", "text": "PARTS PER TRILLION"}),
    dict(beat="escalate", text="That's one drop in a lake.", set="solo", camera="wide", move="pull",
         look=L([0.0, 0.05, MID], dist=0.7, pitch=12), overlay={"type": "chalk", "text": "1 DROP IN A LAKE"}),
    dict(beat="escalate", text="Brewers call it lightstruck beer.", set="lab", camera="medium", move="push",
         look=L([-0.05, 0.05, MID], dist=0.34, pitch=10), overlay={"type": "label", "text": "LIGHTSTRUCK"}),
    dict(beat="escalate", text="And not just sunlight. Bright shop lights do it too, only slower.", set="solo", camera="close",
         move="drift", look=L([0.0, 0.05, MID], dist=0.3, pitch=8), overlay={"type": "chalk", "text": "SHOP LIGHTS TOO"}),
    dict(beat="escalate", text="Clear glass lets almost all of that light straight through.", set="trio", camera="medium",
         move="push", look=L([-0.12, 0.05, MID], dist=0.34, pitch=8), overlay={"type": "label", "text": "CLEAR: NO SHIELD"}),
    dict(beat="escalate", text="Green glass stops some of it.", set="trio", camera="insert", move="pan_r",
         look=L([0.0, 0.05, MID], dist=0.3, pitch=8, lens=60), overlay={"type": "label", "text": "GREEN: SOME"}),
    dict(beat="twist", text="Brown glass blocks most of the light that does the damage.", set="trio", camera="medium",
         move="push", look=L([0.12, 0.05, MID], dist=0.34, pitch=8), overlay={"type": "label", "text": "BROWN: SHIELD"}),
    dict(beat="twist", text="So the beer inside stays fresh far longer.", set="lab", camera="medium", move="orbit_r",
         look=L([0.05, 0.05, MID], dist=0.36, pitch=10), overlay={"type": "stamp", "text": "FRESH"}),
    dict(beat="twist", text="That's why most brewers chose brown.", set="trio", camera="wide", move="pull",
         look=L([0.0, 0.05, MID], dist=0.8, pitch=10), overlay={"type": "stamp", "text": "BROWN WINS"}),
    dict(beat="twist", text="Why green? Supposedly, brown glass ran short after the war.", set="trio",
         camera="medium", move="pan_l", look=L([0.0, 0.05, MID], dist=0.34, pitch=8), overlay={"type": "chalk", "text": "AFTER WW2"}),
    dict(beat="twist", text="And green looked fancy, like an import.", set="trio", camera="insert", move="push",
         look=L([0.0, 0.05, Z + 0.18], dist=0.22, pitch=6, lens=65), overlay={"type": "label", "text": "FANCY"}),
    dict(beat="payoff", text="But some beers still come in clear bottles.", set="solo", camera="medium", move="push",
         look=L([0.0, 0.05, MID], dist=0.4, pitch=10), overlay={"type": "circle", "text": "CLEAR?"}),
    dict(beat="payoff", text="Their trick is special, chemically tweaked hops.", set="hops", camera="insert", move="push",
         look=L([0.0, -0.035, Z + 0.012], dist=0.16, pitch=32, lens=65), overlay={"type": "label", "text": "TWEAKED HOPS"}),
    dict(beat="payoff", text="Light can't snap them apart, so no skunk.", set="lab", camera="close", move="push",
         look=L([-0.05, 0.05, Z + 0.1], dist=0.22, pitch=8, lens=60), overlay={"type": "stamp", "text": "NO SKUNK"}),
    dict(beat="payoff", text="Everyone else? Keep your beer in the dark.", set="solo", camera="wide", move="pull",
         look=L([0.0, 0.05, MID], dist=0.6, pitch=10), overlay={"type": "stamp", "text": "KEEP IT DARK"}),
]


def main():
    for i, s in enumerate(SHOTS, 1):
        s.setdefault("speaker", "narrator")
        for k, v in (("cast", []), ("props", []), ("sfx", []), ("transition", "cut")):
            s.setdefault(k, v)
        for mv in s.get("moves", []):
            if "rot_to" in mv and not mv.get("to"):
                q = next(q for pl in PLACES.values() for q in pl["add"] if q.get("id") == mv["id"])
                mv["to"] = list(q["at"])
        s["id"] = f"s{i:02d}"
    plan = {"id": "brown_bottles", "title": "Why Beer Bottles Are Brown",
            "topic": "lightstruck beer: riboflavin + blue/UV light break hop iso-alpha acids into a skunk-like thiol; brown vs green vs clear glass; modified hops",
            "hook_title": "WHY ARE BEER BOTTLES BROWN?",
            "keywords": ["brown", "light", "skunk", "hops", "glass", "clear", "green", "sulfur", "riboflavin"],
            "cast": [], "channel": "channel5",
            "sources": ["https://en.wikipedia.org/wiki/3-Methyl-2-butene-1-thiol", "https://en.wikipedia.org/wiki/Beer_bottle"],
            "places": PLACES, "shots": SHOTS}
    out = Path(__file__).with_name("plan.json")
    out.write_text(json.dumps(plan, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
