"""Channel 5 Short 'Why American Coins Don't Stick to Magnets' (original topic).
    python3 toontales/stories/magnet_coins/make_plan.py && python3 -m toontales.plan.check toontales/stories/magnet_coins/plan.json --fix
Facts: US dimes, quarters and half dollars are copper-nickel clad (75% copper / 25% nickel outer layers over a
copper core); the five-cent 'nickel' is 75% copper and 25% nickel; the cent is copper-plated zinc since 1982.
Nickel metal is magnetic, but this copper-rich alloy is not, so US coins ignore a magnet. Canada began making
coins from multi-ply plated steel (from 2000), and the UK's 1p and 2p have been copper-plated steel since 1992,
because steel is cheaper; those coins jump to a magnet. Vending machines measure a coin's electromagnetic
signature, which is one way they tell real coins from slugs.
"""
import json
from pathlib import Path

Z = 0.9  # counter top
MZ = Z + 0.06  # magnet hover height


def coin(x, y, idn, mat="silver", r=0.012, **kw):
    return {"m": "@coin", "at": [x, y, Z], "r": r, "mat": mat, "id": idn, **kw}


US = [coin(-0.07, 0.0, "quarter", reeds=119, r=0.0121), coin(-0.03, 0.02, "dime", reeds=118, r=0.0089),
      coin(0.01, -0.01, "nickel", r=0.0106), coin(0.05, 0.02, "penny", mat="copper", r=0.0095)]
MAG = {"m": "@magnet", "at": [-0.07, 0.0, MZ], "w": 0.05, "id": "magnet"}
WORLD = [coin(-0.05, 0.0, "us_q", reeds=119, r=0.0121), coin(0.0, 0.0, "ca_q", mat="steel", reeds=120, r=0.0119),
         coin(0.05, 0.0, "uk_2p", mat="copper", r=0.0129)]
MAG2 = {"m": "@magnet", "at": [0.0, 0.0, MZ], "w": 0.05, "id": "magnet2"}
SLUG = [coin(-0.03, 0.0, "real", reeds=119, r=0.0121), coin(0.03, 0.0, "slug", mat="steel", r=0.0121, hole=0.003)]

PLACES = {
    "us": {"world": "dio_bar_counter", "add": US + [MAG], "prompt": "US coins and a red horseshoe magnet on a walnut bar"},
    "world": {"world": "dio_bar_counter", "add": WORLD + [MAG2], "prompt": "A US, a Canadian and a British coin under a magnet"},
    "mint": {"world": "dio_mint_studio", "add": [coin(0.0, 0.0, "big", reeds=119, r=0.0121)], "prompt": "One quarter on a mint backdrop"},
    "slug": {"world": "dio_mint_studio", "add": SLUG + [{"m": "@magnifier", "at": [0.0, -0.05, Z + 0.035], "rot": -30}],
             "prompt": "A real coin and a steel washer under a magnifier"},
}


def L(at, dist=0.32, yaw=-8, pitch=24, lens=55, **kw):
    d = {"at": at, "dist": dist, "yaw": yaw, "pitch": pitch, "lens": lens}
    d.update(kw)
    return d


def over(idn, x, y=0.0):
    return [{"id": idn, "to": [x, y, MZ], "t0": 0.0, "t1": 0.05}]


def dip(idn, x, t0=0.2, y=0.0):
    return [{"id": idn, "from": [x, y, MZ], "to": [x, y, Z + 0.004], "t0": t0, "t1": t0 + 0.6, "ease": "out"},
            {"id": idn, "from": [x, y, Z + 0.004], "to": [x, y, MZ + 0.03], "t0": t0 + 0.9, "t1": t0 + 1.6, "ease": "in"}]


SHOTS = [
    dict(beat="hook", text="Hold a magnet over an American quarter.", set="us", camera="medium", move="push",
         look=L([-0.07, 0.0, Z + 0.03], dist=0.3, pitch=16), moves=dip("magnet", -0.07)),
    dict(beat="hook", text="Nothing. It won't budge.", set="us", camera="insert", move="crash_zoom",
         look=L([-0.07, 0.0, Z + 0.005], dist=0.14, pitch=30, lens=70), overlay={"type": "stamp", "text": "NOTHING"}),
    dict(beat="hook", text="Try it in Canada, and the coin jumps. Why?", set="world", camera="medium", move="push",
         look=L([0.0, 0.0, Z + 0.03], dist=0.3, pitch=16),
         moves=dip("magnet2", 0.0) + [{"id": "ca_q", "to": [0.0, 0.0, MZ + 0.03 - 0.004], "t0": 1.1, "t1": 1.8, "ease": "in"}]),
    dict(beat="concept", text="A magnet only grabs a few metals. Mainly iron, nickel and cobalt.", set="us", camera="wide",
         move="pull", look=L([-0.01, 0.01, Z + 0.02], dist=0.42, pitch=22), overlay={"type": "chalk", "text": "IRON  NICKEL  COBALT"}),
    dict(beat="concept", text="Fridge doors are steel. Mostly iron. So magnets stick.", set="world",
         camera="close", move="push", look=L([0.0, 0.0, MZ + 0.02], dist=0.2, pitch=6, lens=65), moves=over("magnet2", 0.0),
         overlay={"type": "label", "text": "STEEL = IRON"}),
    dict(beat="concept", text="American coins look silver.", set="us", camera="medium", move="pan_r",
         look=L([-0.02, 0.01, Z + 0.004], dist=0.26, pitch=34), overlay={"type": "label", "text": "LOOKS SILVER"}),
    dict(beat="setup", text="But there's no silver in them at all.", set="mint", camera="insert", move="push",
         look=L([0.0, 0.0, Z + 0.003], dist=0.12, pitch=40, lens=70), overlay={"type": "cross", "text": "SILVER"}),
    dict(beat="setup", text="A quarter is mostly copper, wrapped in a copper nickel skin.", set="mint", camera="close", move="orbit_r",
         look=L([0.0, 0.0, Z + 0.003], dist=0.16, pitch=30, lens=65), overlay={"type": "label", "text": "COPPER CORE"}),
    dict(beat="setup", text="Three parts copper to one part nickel.", set="mint", camera="medium", move="push",
         look=L([0.0, 0.0, Z + 0.004], dist=0.22, pitch=26), overlay={"type": "chalk", "text": "75% CU / 25% NI"}),
    dict(beat="con", text="Nickel on its own sticks to a magnet.", set="us", camera="close", move="crash_zoom",
         look=L([0.01, -0.01, Z + 0.004], dist=0.16, pitch=30, lens=65), overlay={"type": "label", "text": "NICKEL: MAGNETIC"}),
    dict(beat="con", text="But mixed with that much copper, the pull disappears.", set="us", camera="medium", move="push",
         look=L([-0.07, 0.0, Z + 0.03], dist=0.3, pitch=16), moves=dip("magnet", -0.07), overlay={"type": "stamp", "text": "NO PULL"}),
    dict(beat="con", text="The penny? Copper over zinc. Not magnetic either.", set="us", camera="insert", move="pan_r",
         look=L([0.05, 0.02, Z + 0.004], dist=0.14, pitch=32, lens=70), moves=over("magnet", -0.07)),
    dict(beat="escalate", text="So why do Canadian coins jump?", set="world", camera="wide", move="push",
         look=L([0.0, 0.0, Z + 0.03], dist=0.4, pitch=18), moves=over("magnet2", 0.0), freeze="WAIT..."),
    dict(beat="escalate", text="Copper and nickel got expensive.", set="world", camera="medium", move="drift",
         look=L([-0.05, 0.0, Z + 0.004], dist=0.22, pitch=30), moves=over("magnet2", 0.0), overlay={"type": "chalk", "text": "$$$"}),
    dict(beat="escalate", text="In 2000, Canada started making coins from steel, plated in nickel.", set="world", camera="close",
         move="push", look=L([0.0, 0.0, Z + 0.004], dist=0.16, pitch=30, lens=65), moves=over("magnet2", 0.0),
         overlay={"type": "label", "text": "STEEL CORE"}),
    dict(beat="escalate", text="Steel is far cheaper than nickel.", set="world", camera="medium", move="pan_l",
         look=L([0.0, 0.0, Z + 0.004], dist=0.22, pitch=28), moves=over("magnet2", 0.0), overlay={"type": "chalk", "text": "CHEAPER"}),
    dict(beat="escalate", text="Steel is mostly iron.", set="world", camera="insert", move="crash_zoom",
         look=L([0.0, 0.0, Z + 0.003], dist=0.11, pitch=36, lens=70), moves=over("magnet2", 0.0), overlay={"type": "stamp", "text": "IRON"}),
    dict(beat="twist", text="Britain did the same. Since 1992, its copper coins are copper-coated steel.", set="world", camera="medium",
         move="pan_r", look=L([0.05, 0.0, Z + 0.03], dist=0.28, pitch=16),
         moves=dip("magnet2", 0.05) + [{"id": "uk_2p", "to": [0.05, 0.0, MZ + 0.03 - 0.004], "t0": 1.1, "t1": 1.8, "ease": "in"}]),
    dict(beat="twist", text="Clink. Straight up to the magnet.", set="world", camera="close", move="push",
         look=L([0.05, 0.0, MZ + 0.02], dist=0.18, pitch=6, lens=65), moves=over("magnet2", 0.05) + [
             {"id": "uk_2p", "to": [0.05, 0.0, MZ + 0.026], "t0": 0.0, "t1": 0.05}], overlay={"type": "stamp", "text": "CLINK"}),
    dict(beat="twist", text="Vending machines use this. Every coin leaves its own magnetic signature.", set="slug", camera="medium",
         move="push", look=L([0.0, 0.0, Z + 0.004], dist=0.26, pitch=30), overlay={"type": "label", "text": "SIGNATURE"}),
    dict(beat="twist", text="Canada's layered plating makes that signature extra hard to fake.", set="slug", camera="close",
         move="orbit_r", look=L([-0.03, 0.0, Z + 0.003], dist=0.16, pitch=32, lens=65), overlay={"type": "label", "text": "HARD TO FAKE"}),
    dict(beat="twist", text="A steel washer gives itself away.", set="slug", camera="insert", move="crash_zoom",
         look=L([0.03, 0.0, Z + 0.003], dist=0.12, pitch=38, lens=70), overlay={"type": "stamp", "text": "REJECTED"}),
    dict(beat="payoff", text="One last surprise.", set="us", camera="wide", move="pull",
         look=L([-0.01, 0.01, Z + 0.02], dist=0.42, pitch=22), moves=over("magnet", -0.07)),
    dict(beat="payoff", text="The American coin called the nickel is only one quarter nickel.", set="us", camera="insert", move="push",
         look=L([0.01, -0.01, Z + 0.004], dist=0.14, pitch=32, lens=70), moves=over("magnet", -0.07),
         overlay={"type": "chalk", "text": "25% NICKEL"}),
    dict(beat="payoff", text="The other three quarters? Copper.", set="mint", camera="close", move="orbit_l",
         look=L([0.0, 0.0, Z + 0.003], dist=0.16, pitch=30, lens=65), overlay={"type": "label", "text": "75% COPPER"}),
    dict(beat="payoff", text="Dimes and quarters too. Copper inside, every one.", set="us", camera="medium", move="pan_r",
         look=L([-0.05, 0.01, Z + 0.004], dist=0.24, pitch=30), moves=over("magnet", -0.07), overlay={"type": "chalk", "text": "ALL COPPER"}),
    dict(beat="payoff", text="So go ahead. Hold a magnet over your change.", set="us", camera="medium", move="push",
         look=L([-0.07, 0.0, Z + 0.03], dist=0.3, pitch=16), moves=dip("magnet", -0.07)),
]


def main():
    for i, s in enumerate(SHOTS, 1):
        s.setdefault("speaker", "narrator")
        for k, v in (("cast", []), ("props", []), ("sfx", []), ("transition", "cut")):
            s.setdefault(k, v)
        s["id"] = f"s{i:02d}"
    plan = {"id": "magnet_coins", "title": "Why American Coins Don't Stick to Magnets",
            "topic": "US cupronickel-clad coins are not magnetic; Canada's plated-steel coins (2000) and UK copper-plated steel 1p/2p (1992) are; vending machine electromagnetic signatures; the nickel is 25% nickel",
            "hook_title": "WHY WON'T IT STICK?",
            "keywords": ["magnet", "nickel", "copper", "steel", "Canada", "quarter", "iron", "coins", "Britain"],
            "cast": [], "channel": "channel5",
            "sources": ["https://en.wikipedia.org/wiki/Cupronickel", "https://en.wikipedia.org/wiki/Coins_of_the_Canadian_dollar",
                        "https://en.wikipedia.org/wiki/Nickel_(United_States_coin)"],
            "places": PLACES, "shots": SHOTS}
    out = Path(__file__).with_name("plan.json")
    out.write_text(json.dumps(plan, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
