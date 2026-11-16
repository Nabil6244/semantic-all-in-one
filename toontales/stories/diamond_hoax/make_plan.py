"""Ch2 Short: The Great Diamond Hoax of 1872 (Arnold & Slack salt a field; Clarence King exposes it)."""
import json
from pathlib import Path

def C(who, mark, *acts):
    return {"id": who, "mark": mark, "acts": [{"do": a, "at": t} for a, t in acts]}
S = []
def sh(beat, text, place, cam, move, cast=(), speaker="narrator", **kw):
    S.append({"beat": beat, "speaker": speaker, "text": text, "set": place, "camera": cam, "move": move, "cast": list(cast), **kw})
B = lambda who, txt: {"type": "board", "held_by": who, "text": txt}
sh("hook", "Two miners walk into a bank with a sack of diamonds.", "bank", "two_shot", "push",
   [C("bart", "A", ("present", 0.2)), C("driver", "C", ("hold", 0.0))], props=[{"type": "sack", "held_by": "driver"}], sfx=[{"name": "ding", "at": 0.3}])
sh("hook", "Every diamond is real. The mine is not. How?", "bank", "medium", "crash_zoom",
   [C("bart", "A", ("laugh", 0.4))], overlay={"type": "stamp", "text": "FAKE MINE"})
sh("concept", "San Francisco, 1872. Everyone is hungry for the next big strike.", "town", "wide", "pan_r",
   [C("sheriff", "B", ("look_around", 0.2))], overlay={"type": "chalk", "text": "1872"})
sh("concept", "Philip Arnold and John Slack say they found a diamond field.", "town", "two_shot", "push",
   [C("bart", "A", ("explain", 0.0)), C("driver", "C", ("nod", 0.8))], props=[B("bart", "DIAMOND FIELD")])
sh("concept", "Where? They won't say.", "town", "close", "push", [C("bart", "A", ("shake_head", 0.2))], overlay={"type": "cross", "text": "SECRET"})
sh("setup", "They leave the sack at the bank, very reluctantly.", "bank", "medium", "push",
   [C("driver", "C", ("hold", 0.0), ("sigh", 1.4))], props=[{"type": "sack", "held_by": "driver"}], moves=[{"id": "safe", "run_to": 0, "t0": 0, "t1": 0.1}])
sh("setup", "The bankers peek inside. Diamonds and rubies.", "bank", "insert", "crash_zoom",
   [C("sheriff", "B", ("shock", 0.3))], props=[{"type": "gold", "held_by": "sheriff"}], overlay={"type": "arrow", "text": "GEMS"})
sh("setup", "Now the richest men in town want in.", "bank", "two_shot", "push",
   [C("sheriff", "B", ("money", 0.2)), C("bart", "A", ("hips", 0.6))], props=[{"type": "money", "held_by": "sheriff"}])
sh("con", "So the miners agree to show an expert. Blindfolded.", "trail", "wide", "pan_l",
   [C("driver", "enter_l", ("walk", 0.0)), C("bart", "A", ("sneak", 0.2))], moves=[{"id": "wagon", "from": [-20, 2, 0], "to": [-4, 2, 0], "t0": 0, "t1": 2.0, "ease": "out"}])
sh("con", "Days of riding in circles, deep into the wild.", "desert", "wide", "drift",
   [C("driver", "B", ("walk", 0.0))], overlay={"type": "chalk", "text": "WHERE ARE WE?"}, sfx=[{"name": "footsteps", "at": 0.0}])
sh("con", "The expert digs, and finds gems everywhere.", "desert", "medium", "push",
   [C("sheriff", "A", ("pick_up", 0.2), ("cheer", 1.4))], props=[{"type": "rock", "held_by": "sheriff"}])
sh("escalate", "Tiffany's in New York calls the sample a fortune.", "town", "insert", "push",
   [C("sheriff", "B", ("hold", 0.0), ("shock", 1.2))], props=[{"type": "newspaper", "held_by": "sheriff", "text": "TIFFANY SAYS YES"}], sfx=[{"name": "paper", "at": 0.2}])
sh("escalate", "Investors pay Arnold and Slack about six hundred thousand dollars.", "bank", "medium", "crash_zoom",
   [C("bart", "A", ("money", 0.2), ("laugh", 1.4))], props=[{"type": "money", "held_by": "bart"}], overlay={"type": "stamp", "text": "$600,000"})
sh("obstacle", "But a government geologist, Clarence King, is mapping that same land.", "desert", "wide", "pan_r",
   [C("hume", "enter_r", ("walk", 0.0))], overlay={"type": "label", "text": "CLARENCE KING"}, freeze="WAIT...")
sh("obstacle", "He tracks down the secret field himself.", "desert", "medium", "push", [C("hume", "B", ("look_around", 0.0), ("point", 1.4))], props=[{"type": "map", "held_by": "hume", "text": "FIELD"}])
sh("twist", "The gems are only in loose, dug up dirt.", "desert", "close", "push",
   [C("hume", "B", ("think", 0.2))], overlay={"type": "circle", "text": "LOOSE DIRT"})
sh("twist", "One diamond even has a jeweler's cut on it.", "desert", "insert", "crash_zoom",
   [C("hume", "B", ("hold", 0.0), ("shock", 1.0))], props=[{"type": "gold", "held_by": "hume"}], overlay={"type": "arrow", "text": "CUT MARKS"})
sh("twist", "The field was salted. Cheap gems, scattered by hand.", "trail", "medium", "push",
   [C("driver", "A", ("throw", 0.2))], props=[{"type": "sack", "held_by": "driver"}], overlay={"type": "stamp", "text": "SALTED"})
sh("payoff", "King races to warn the bankers before they lose more.", "town", "wide", "pan_l",
   [C("hume", "enter_l", ("run", 0.0))], moves=[{"id": "wagon", "from": [8, 4, 0], "to": [-6, 4, 0], "t0": 0, "t1": 2.2}])
sh("payoff", "The investors are ruined. The newspapers howl.", "bank", "two_shot", "push",
   [C("sheriff", "B", ("facepalm", 0.2)), C("hume", "A", ("point", 0.4))], props=[{"type": "newspaper", "held_by": "hume", "text": "HOAX!"}])
sh("payoff", "And Arnold? He's already home in Kentucky, with the cash.", "trail", "medium", "pull",
   [C("bart", "A", ("wave", 0.2), ("laugh", 1.4))], props=[{"type": "money", "held_by": "bart"}])
sh("payoff", "Two miners, one sack of real diamonds, and a whole fake mine.", "bank", "wide", "pull",
   [C("bart", "A", ("present", 0.2)), C("driver", "C", ("nod", 0.6))], props=[{"type": "sack", "held_by": "driver"}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
    for k, v in (("props", []), ("sfx", []), ("transition", "cut")):
        s.setdefault(k, v)
plan = {"id": "diamond_hoax", "title": "How Two Miners Sold a Fake Diamond Mine", "topic": "The Great Diamond Hoax of 1872 (Arnold and Slack, Clarence King)",
        "hook_title": "A MINE FULL OF FAKE DIAMONDS?", "keywords": ["diamonds", "mine", "bank", "salted", "King", "Tiffany", "investors", "Arnold"],
        "cast": ["bart", "driver", "hume", "sheriff"], "channel": "channel2",
        "sources": ["https://en.wikipedia.org/wiki/Diamond_hoax_of_1872", "https://en.wikipedia.org/wiki/Clarence_King"],
        "places": {
            "bank": {"world": "frontier_office", "prompt": "An 1870s San Francisco bank office with a big iron safe"},
            "town": {"world": "frontier_town", "remove": ["coffin"], "prompt": "A Wild West main street at dusk"},
            "trail": {"world": "frontier_desert", "prompt": "A dusty trail with a wagon at sunset"},
            "desert": {"world": "frontier_desert", "remove": ["wagon"], "prompt": "Remote high desert with red rocks and scrub"}},
        "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
