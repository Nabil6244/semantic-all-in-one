"""Ch1 Short: The Family Who Sold the Time (Belville family, Greenwich time by hand, 1836-1940)."""
import json
from pathlib import Path

def C(who, mark, *acts):
    return {"id": who, "mark": mark, "acts": [{"do": a, "at": t} for a, t in acts]}
S = []
def sh(beat, text, place, cam, move, cast=(), speaker="narrator", **kw):
    S.append({"beat": beat, "speaker": speaker, "text": text, "set": place, "camera": cam, "move": move, "cast": list(cast), **kw})
W = lambda who, txt: {"type": "board", "held_by": who, "text": txt}
sh("hook", "For a hundred years, one family sold something invisible.", "shop", "wide", "push",
   [C("vic_ned", "B", ("look_around", 0.0), ("scratch_head", 1.4))], overlay={"type": "circle", "text": "?"}, sfx=[{"name": "ding", "at": 0.2}])
sh("hook", "They sold the time. Door to door. How?", "street", "two_shot", "crash_zoom",
   [C("vic_alder", "A", ("present", 0.2)), C("vic_ned", "B", ("shock", 0.8))], props=[W("vic_alder", "THE TIME")])
sh("concept", "London, 1836. Clocks drift, and nobody knows the exact time.", "street", "wide", "pan_r",
   [C("vic_ned", "B", ("shrug", 0.4))], overlay={"type": "chalk", "text": "1836"}, moves=[{"id": "clock", "run_to": 0.3, "t0": 0, "t1": 0.6}])
sh("concept", "The only perfect clock is at the Greenwich Observatory.", "square", "medium", "tilt_up",
   [C("vic_alder", "A", ("point", 0.3))], overlay={"type": "label", "text": "GREENWICH"})
sh("concept", "John Belville works there.", "square", "medium", "push", [C("vic_alder", "A", ("wave", 0.2), ("nod", 1.2))], overlay={"type": "label", "text": "JOHN BELVILLE"})
sh("setup", "Every Monday he sets his pocket watch to Greenwich,", "square", "close", "push",
   [C("vic_alder", "A", ("hold", 0.0))], props=[W("vic_alder", "GREENWICH TIME")], moves=[{"id": "clock", "run_to": 0.5, "t0": 0, "t1": 0.6}])
sh("setup", "then walks across London to his customers.", "line", "wide", "pan_l",
   [C("vic_alder", "enter_l", ("walk", 0.0))], sfx=[{"name": "footsteps", "at": 0.0}])
sh("setup", "Clockmakers pay him to look at his watch.", "shop", "two_shot", "push",
   [C("vic_ned", "B", ("money", 0.2)), C("vic_alder", "A", ("hold", 0.0))], props=[{"type": "coins", "held_by": "vic_ned"}],
   moves=[{"id": "shop_clock", "run_to": 0.4, "t0": 0.2, "t1": 1.0}])
sh("setup", "That's it. Check the watch, set your clocks, pay up.", "shop", "medium", "push",
   [C("vic_ned", "B", ("nod", 0.3))], overlay={"type": "chalk", "text": "SET IT"}, moves=[{"id": "shop_clock", "run_to": 2.0, "t0": 0.1, "t1": 1.2}])
sh("con", "About two hundred customers bought the time every week.", "street", "wide", "drift",
   [C("vic_alder", "A", ("walk", 0.0)), C("vic_ned", "C", ("wave", 0.6))], overlay={"type": "stamp", "text": "200"})
sh("con", "When John died, his wife Maria took over the round.", "square", "medium", "push",
   [C("vic_ned", "B", ("sad", 0.2))], overlay={"type": "label", "text": "1856"})
sh("con", "Then their daughter Ruth, with the very same watch.", "shop", "close", "push",
   [C("vic_ned", "B", ("hold", 0.0))], props=[W("vic_ned", "ARNOLD 485")])
sh("escalate", "She called the watch Arnold. It was made for a duke.", "shop", "medium", "drift",
   [C("vic_ned", "B", ("present", 0.2), ("laugh", 1.6))], overlay={"type": "arrow", "text": "ARNOLD"})
sh("escalate", "Every Monday, rain or shine, Ruth walked the same long route.", "line", "wide", "pan_r",
   [C("vic_ned", "enter_l", ("walk", 0.0))], sfx=[{"name": "footsteps", "at": 0.0}], overlay={"type": "chalk", "text": "EVERY MONDAY"})
sh("escalate", "But the world was changing.", "station", "wide", "pan_l", [C("vic_pike", "A", ("present", 0.4))],
   moves=[{"id": "loco", "from": [-40, 6, 0], "to": [-4, 6, 0], "t0": 0, "t1": 2.0, "ease": "out"}], sfx=[{"name": "train", "at": 0.0}])
sh("escalate", "Telegraph wires now sent the time electrically.", "line", "wide", "push", [],
   moves=[{"id": "loco", "from": [-30, 0, 0], "to": [30, 0, 0], "t0": 0, "t1": 3.0}], overlay={"type": "chalk", "text": "TELEGRAPH"})
sh("obstacle", "Our time is modern! Hers is a joke!", "station", "medium", "crash_zoom",
   [C("vic_pike", "A", ("point", 0.2), ("laugh", 1.2))], speaker="vic_pike", props=[W("vic_pike", "ELECTRIC TIME")])
sh("obstacle", "In 1908 a rival mocked her in a speech. The Times printed it.", "street", "insert", "push",
   [C("vic_ned", "B", ("hold", 0.0), ("shock", 1.4))], props=[{"type": "newspaper", "held_by": "vic_ned", "text": "THE TIMES"}],
   sfx=[{"name": "paper", "at": 0.2}], freeze="WAIT...")
sh("twist", "But it backfired.", "street", "medium", "crash_zoom", [C("vic_alder", "A", ("hips", 0.1))], overlay={"type": "stamp", "text": "BACKFIRED"})
sh("twist", "The story made her famous. New customers signed up.", "shop", "two_shot", "push",
   [C("vic_ned", "B", ("cheer", 0.4)), C("vic_alder", "A", ("nod", 0.6))], overlay={"type": "stamp", "text": "FREE ADVERT"})
sh("payoff", "Ruth kept selling the time until 1940.", "square", "wide", "pan_r",
   [C("vic_alder", "A", ("walk", 0.0))], overlay={"type": "chalk", "text": "1940"}, moves=[{"id": "clock", "run_to": 0.6, "t0": 0, "t1": 1.0}])
sh("payoff", "She was eighty six years old.", "square", "close", "push", [C("vic_ned", "B", ("shock", 0.3))], overlay={"type": "stamp", "text": "86"})
sh("payoff", "By then, radio was beeping the exact time into every home.", "station", "medium", "push",
   [C("vic_pike", "A", ("shrug", 0.3))], overlay={"type": "label", "text": "RADIO PIPS"})
sh("payoff", "Three Belvilles, one watch, over a hundred years of selling the time.", "shop", "wide", "pull",
   [C("vic_ned", "B", ("present", 0.2))], props=[W("vic_ned", "ARNOLD 485")], moves=[{"id": "shop_clock", "run_to": 0.5, "t0": 0, "t1": 1.0}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
    for k, v in (("props", []), ("sfx", []), ("transition", "cut")):
        s.setdefault(k, v)
plan = {"id": "time_seller", "title": "The Family Who Sold the Time", "topic": "John, Maria and Ruth Belville sold Greenwich time door to door in London, 1836-1940",
        "hook_title": "THEY SOLD THE TIME?", "keywords": ["time", "watch", "Greenwich", "Ruth", "clock", "Arnold", "telegraph", "customers"],
        "cast": ["vic_pike", "vic_alder", "vic_ned"], "channel": "channel1",
        "sources": ["https://en.wikipedia.org/wiki/Ruth_Belville", "https://en.wikipedia.org/wiki/John_Henry_Belville"],
        "places": {
            "street": {"world": "victorian_square", "prompt": "A busy Victorian London street with a big public clock"},
            "square": {"world": "victorian_square", "remove": ["cart"], "prompt": "A grand Victorian square before an observatory-like hall with a clock"},
            "shop": {"world": "clock_shop", "prompt": "A Victorian clockmaker's shop full of clocks"},
            "station": {"world": "station", "prompt": "A Victorian railway platform with a steam train"},
            "line": {"world": "railway_line", "prompt": "A railway line with telegraph poles across the country"}},
        "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
