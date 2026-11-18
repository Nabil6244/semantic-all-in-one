"""Ch2 Short: Jacob Davis, Levi Strauss and the riveted work pants (patent 1873)."""
import json
from pathlib import Path

def C(who, mark, *acts):
    return {"id": who, "mark": mark, "acts": [{"do": a, "at": t} for a, t in acts]}
S = []
def sh(beat, text, place, cam, move, cast=(), speaker="narrator", **kw):
    S.append({"beat": beat, "speaker": speaker, "text": text, "set": place, "camera": cam, "move": move, "cast": list(cast), **kw})
B = lambda who, txt: {"type": "board", "held_by": who, "text": txt}
sh("hook", "A tailor hammers horse-blanket rivets into a pair of trousers.", "tailor", "medium", "push",
   [C("sheriff", "B", ("hold", 0.0), ("nod", 1.2))], props=[{"type": "tool", "held_by": "sheriff"}], sfx=[{"name": "bonk", "at": 0.4}, {"name": "bonk", "at": 1.1}])
sh("hook", "Why would anyone nail their pants?", "tailor", "close", "crash_zoom",
   [C("driver", "C", ("scratch_head", 0.2))], overlay={"type": "circle", "text": "?"})
sh("concept", "Reno, Nevada. The tailor is Jacob Davis.", "town", "wide", "pan_r",
   [C("sheriff", "A", ("wave", 0.3))], overlay={"type": "label", "text": "JACOB DAVIS"})
sh("concept", "A woman brings a problem: her husband rips every pocket.", "tailor", "two_shot", "push",
   [C("hume", "A", ("plead", 0.2)), C("sheriff", "C", ("think", 0.8))], props=[B("hume", "RIPPED AGAIN")])
sh("setup", "He's a woodcutter. Heavy tools, heavy work.", "desert", "wide", "drift",
   [C("hume", "B", ("pick_up", 0.2))], props=[{"type": "tool", "held_by": "hume"}], sfx=[{"name": "pick", "at": 0.8}])
sh("setup", "Pockets tear at the corners. Every time.", "desert", "insert", "crash_zoom",
   [C("hume", "B", ("shock", 0.3))], overlay={"type": "arrow", "text": "CORNERS"})
sh("setup", "Davis spots copper rivets meant for horse blankets.", "tailor", "medium", "push",
   [C("sheriff", "A", ("point", 0.2), ("fist_pump", 1.4))], props=[{"type": "box", "held_by": "sheriff"}])
sh("obstacle", "Rivets? On trousers? You're mad!", "tailor", "two_shot", "crash_zoom",
   [C("driver", "C", ("laugh", 0.1), ("point", 0.9))], speaker="driver")
sh("obstacle", "You see, it's like nailing a board where it splits.", "tailor", "close", "push",
   [C("sheriff", "A", ("explain", 0.0))], speaker="sheriff", props=[B("sheriff", "NAIL THE CORNER")])
sh("con", "Rivet the corners. Done.", "tailor", "insert", "crash_zoom", [C("sheriff", "A", ("hold", 0.0))],
   props=[{"type": "tool", "held_by": "sheriff"}], sfx=[{"name": "bonk", "at": 0.3}])
sh("con", "The woodcutter tugged and tugged. The pockets held.", "desert", "medium", "push", [C("hume", "B", ("celebrate", 0.2))], overlay={"type": "stamp", "text": "HELD"})
sh("con", "Soon every worker wanted a pair.", "town", "wide", "pan_l",
   [C("hume", "A", ("walk", 0.0)), C("driver", "C", ("money", 0.6))], props=[{"type": "money", "held_by": "driver"}], sfx=[{"name": "crowd", "at": 0.2}])
sh("escalate", "Davis wants a patent. It costs sixty-eight dollars.", "tailor", "medium", "push",
   [C("sheriff", "A", ("sad", 0.2))], props=[{"type": "letter", "held_by": "sheriff", "text": "PATENT $68"}], overlay={"type": "stamp", "text": "$68"})
sh("escalate", "He can't afford it.", "tailor", "close", "drift", [C("sheriff", "A", ("sigh", 0.2))], overlay={"type": "cross", "text": "NO MONEY"})
sh("escalate", "So he writes to the man who sells him his cloth.", "office", "wide", "push",
   [C("bart", "B", ("hold", 0.0), ("think", 1.2))], props=[{"type": "letter", "held_by": "bart", "text": "DEAR LEVI"}], sfx=[{"name": "paper", "at": 0.2}], freeze="WAIT...")
sh("twist", "A San Francisco merchant named Levi Strauss.", "office", "medium", "crash_zoom",
   [C("bart", "B", ("present", 0.2), ("laugh", 1.2))], overlay={"type": "label", "text": "LEVI STRAUSS"})
sh("twist", "In 1873, they share the patent.", "office", "two_shot", "push",
   [C("bart", "A", ("money", 0.2)), C("sheriff", "C", ("cheer", 0.6))], overlay={"type": "chalk", "text": "1873"}, sfx=[{"name": "cash", "at": 0.3}])
sh("payoff", "Blue denim work pants became the uniform of miners and cowboys.", "desert", "wide", "pan_l",
   [C("hume", "enter_r", ("walk", 0.0)), C("driver", "B", ("wave", 0.8))], sfx=[{"name": "horse", "at": 0.2}])
sh("payoff", "But rivets weren't all good news.", "town", "wide", "pan_r", [C("driver", "B", ("hips", 0.3))], mood="sneaky")
sh("payoff", "Back pocket rivets scratched saddles and chairs.", "desert", "medium", "push",
   [C("hume", "B", ("tremble", 0.2))], overlay={"type": "cross", "text": "SCRATCH"}, sfx=[{"name": "scratch", "at": 0.3}])
sh("payoff", "So in 1937 they were hidden under the cloth.", "office", "insert", "push",
   [C("bart", "A", ("nod", 0.3))], overlay={"type": "chalk", "text": "1937"})
sh("payoff", "Look at your jeans today. The front pockets still have them.", "town", "medium", "pull",
   [C("sheriff", "B", ("point_you", 0.2), ("laugh", 1.4))], props=[B("sheriff", "LOOK DOWN")], mood="upbeat")
sh("payoff", "All from a tailor with a box of horse-blanket rivets.", "tailor", "wide", "pull",
   [C("sheriff", "B", ("present", 0.2))], props=[{"type": "box", "held_by": "sheriff"}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
    for k, v in (("props", []), ("sfx", []), ("transition", "cut")):
        s.setdefault(k, v)
plan = {"id": "rivet_jeans", "title": "Why Your Jeans Have Tiny Rivets", "topic": "Jacob Davis's riveted work pants and the 1873 patent he shared with Levi Strauss",
        "hook_title": "WHY NAIL YOUR PANTS?", "keywords": ["rivets", "jeans", "pockets", "patent", "Levi", "Davis", "tailor", "copper"],
        "cast": ["bart", "driver", "hume", "sheriff"], "channel": "channel2",
        "sources": ["https://en.wikipedia.org/wiki/Jacob_W._Davis", "https://en.wikipedia.org/wiki/Levi_Strauss_%26_Co."],
        "places": {
            "tailor": {"world": "frontier_laundry", "prompt": "A small 1870s frontier tailor's shop with bolts of cloth"},
            "town": {"world": "frontier_town", "remove": ["coffin"], "prompt": "A busy Nevada frontier main street"},
            "office": {"world": "frontier_office", "prompt": "An 1870s San Francisco dry-goods merchant's office"},
            "desert": {"world": "frontier_desert", "remove": ["wagon"], "prompt": "Open desert scrub where a woodcutter works"}},
        "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
