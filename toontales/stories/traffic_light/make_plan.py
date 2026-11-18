"""Ch1 Short: London's first traffic light (Parliament Square, 1868) and why it exploded."""
import json
from pathlib import Path

def C(who, mark, *acts):
    return {"id": who, "mark": mark, "acts": [{"do": a, "at": t} for a, t in acts]}
S = []
def sh(beat, text, place, cam, move, cast=(), speaker="narrator", **kw):
    S.append({"beat": beat, "speaker": speaker, "text": text, "set": place, "camera": cam, "move": move, "cast": list(cast), **kw})
W = lambda who, txt: {"type": "board", "held_by": who, "text": txt}
sh("hook", "In 1868, London switched on its first traffic light.", "square", "wide", "push",
   [C("vic_ned", "B", ("look_around", 0.0), ("point", 1.2))], overlay={"type": "chalk", "text": "1868"}, sfx=[{"name": "ding", "at": 0.2}])
sh("hook", "A month later, it blew up. Why?", "square", "close", "crash_zoom",
   [C("vic_ned", "B", ("shock", 0.3))], overlay={"type": "stamp", "text": "BOOM"}, sfx=[{"name": "thud", "at": 0.3}])
sh("concept", "Westminster streets were chaos: carts, cabs and horses everywhere.", "street", "wide", "pan_r",
   [C("vic_ned", "B", ("tremble", 0.4))], moves=[{"id": "cart", "from": [-14, 2, 0], "to": [10, 2, 0], "t0": 0, "t1": 2.6}])
sh("concept", "Crossing the road was genuinely dangerous.", "street", "medium", "push",
   [C("vic_ned", "enter_l", ("run", 0.0))], overlay={"type": "cross", "text": "DANGER"})
sh("concept", "Members of Parliament could barely reach their own front door.", "square", "two_shot", "push",
   [C("vic_alder", "A", ("angry", 0.2)), C("vic_ned", "C", ("shrug", 0.8))], overlay={"type": "label", "text": "PARLIAMENT"})
sh("setup", "Then a railway engineer had an idea.", "station", "medium", "push",
   [C("vic_pike", "A", ("think", 0.2), ("point", 1.4))], overlay={"type": "circle", "text": "IDEA"})
sh("setup", "His name was John Peake Knight.", "station", "close", "push",
   [C("vic_pike", "A", ("present", 0.2))], overlay={"type": "label", "text": "JOHN PEAKE KNIGHT"})
sh("setup", "Railways already stopped trains with signal arms.", "line", "wide", "pan_l", [], overlay={"type": "arrow", "text": "SIGNAL ARM"},
   moves=[{"id": "loco", "from": [-30, 0, 0], "to": [-2, 0, 0], "t0": 0, "t1": 2.4, "ease": "out"}], sfx=[{"name": "train", "at": 0.0}])
sh("setup", "Arm out means stop. Arm down means go carefully.", "line", "medium", "push",
   [C("vic_pike", "A", ("point", 0.2), ("nod", 1.4))], props=[W("vic_pike", "STOP / CAUTION")])
sh("setup", "Why not do the same for carts?", "station", "two_shot", "crash_zoom",
   [C("vic_pike", "A", ("hips", 0.1)), C("vic_ned", "C", ("cheer", 0.6))], speaker="vic_pike")
sh("con", "In December 1868, a signal post rose outside Parliament.", "square", "low", "tilt_up",
   [C("vic_pike", "A", ("present", 0.3))], overlay={"type": "chalk", "text": "DEC 1868"}, moves=[{"id": "clock", "run_to": 0.4, "t0": 0, "t1": 0.8}])
sh("con", "About twenty feet tall, with arms by day.", "square", "wide", "tilt_down",
   [C("vic_ned", "B", ("shock", 0.4))], overlay={"type": "arrow", "text": "20 FEET"})
sh("con", "At night, gas lamps. Red and green.", "square", "medium", "drift",
   [C("vic_pike", "A", ("point", 0.2))], props=[W("vic_pike", "RED = STOP")], mood="sneaky")
sh("escalate", "A policeman turned a handle to work it.", "square", "two_shot", "push",
   [C("vic_ned", "B", ("hold", 0.0), ("nod", 1.2))], props=[{"type": "tool", "held_by": "vic_ned"}], sfx=[{"name": "scratch", "at": 0.3}])
sh("escalate", "Carts stopped. People crossed. Total success.", "street", "wide", "pan_r",
   [C("vic_ned", "enter_l", ("walk", 0.0)), C("vic_alder", "C", ("wave", 0.8))], sfx=[{"name": "footsteps", "at": 0.0}])
sh("escalate", "Even the grumpy members of Parliament were impressed.", "square", "close", "crash_zoom", [C("vic_alder", "C", ("celebrate", 0.2))], overlay={"type": "stamp", "text": "SUCCESS"})
sh("twist", "A fancy lamp post won't last a winter!", "square", "medium", "push",
   [C("vic_alder", "A", ("laugh", 0.2), ("point", 1.4))], speaker="vic_alder", freeze="WAIT...")
sh("twist", "But gas pipes leak, and in January 1869 one did.", "square", "insert", "push",
   [C("vic_ned", "B", ("look_around", 0.2), ("scratch_head", 1.4))], overlay={"type": "chalk", "text": "JAN 1869"}, mood="sad")
sh("twist", "The lamp exploded, right beside the policeman.", "square", "wide", "crash_zoom",
   [C("vic_ned", "B", ("fall", 0.2))], overlay={"type": "stamp", "text": "BOOM"}, sfx=[{"name": "thud", "at": 0.2}, {"name": "glass", "at": 0.3}])
sh("twist", "He was badly burned. The signal was taken away.", "street", "medium", "push",
   [C("vic_ned", "B", ("sad", 0.2)), C("vic_alder", "A", ("hips", 0.6))], props=[{"type": "newspaper", "held_by": "vic_alder", "text": "SIGNAL BLOWS UP"}], sfx=[{"name": "paper", "at": 0.3}])
sh("payoff", "London waited almost sixty years to try again.", "station", "wide", "pan_l",
   [C("vic_pike", "A", ("sigh", 0.2))], overlay={"type": "chalk", "text": "60 YEARS"}, mood="upbeat")
sh("payoff", "In 1926, a policeman's handle worked the new signal again.", "street", "two_shot", "push",
   [C("vic_ned", "B", ("hold", 0.0), ("nod", 1.0))], props=[{"type": "tool", "held_by": "vic_ned"}], overlay={"type": "chalk", "text": "1926"})
sh("payoff", "This time with electric lights. No gas.", "square", "medium", "push",
   [C("vic_ned", "B", ("cheer", 0.3))], overlay={"type": "label", "text": "ELECTRIC"})
sh("payoff", "And the colours? Still railway red and green.", "line", "medium", "drift",
   [C("vic_pike", "A", ("present", 0.2), ("laugh", 1.4))], props=[W("vic_pike", "RED / GREEN")])
sh("payoff", "The handle became a timer, and the timer became a computer.", "station", "medium", "drift",
   [C("vic_pike", "A", ("explain", 0.0))], props=[W("vic_pike", "HANDLE > TIMER > COMPUTER")])
sh("payoff", "Every traffic light today began with one gas lamp outside Parliament.", "square", "wide", "pull",
   [C("vic_ned", "B", ("point", 0.3))], moves=[{"id": "clock", "run_to": 0.6, "t0": 0, "t1": 1.0}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
    for k, v in (("props", []), ("sfx", []), ("transition", "cut")):
        s.setdefault(k, v)
plan = {"id": "traffic_light", "title": "The First Traffic Light Exploded", "topic": "John Peake Knight's gas-lit semaphore traffic signal outside Parliament, London 1868-1869",
        "hook_title": "THE TRAFFIC LIGHT BLEW UP?", "keywords": ["traffic", "light", "signal", "gas", "Parliament", "policeman", "railway", "exploded"],
        "cast": ["vic_pike", "vic_alder", "vic_ned"], "channel": "channel1",
        "sources": ["https://en.wikipedia.org/wiki/John_Peake_Knight", "https://en.wikipedia.org/wiki/Traffic_light#History"],
        "places": {
            "square": {"world": "victorian_square", "remove": ["cart"], "prompt": "Parliament Square in Victorian London with a tall clock tower"},
            "street": {"world": "victorian_square", "prompt": "A busy Victorian London street full of carts and cabs"},
            "station": {"world": "station", "prompt": "A Victorian railway platform with a steam train"},
            "line": {"world": "railway_line", "prompt": "A railway line with signal posts across the country"}},
        "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
