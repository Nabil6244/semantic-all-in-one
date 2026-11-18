"""Ch1 Short: The Great Stink of 1858 and Joseph Bazalgette's sewers (still in use)."""
import json
from pathlib import Path

def C(who, mark, *acts):
    return {"id": who, "mark": mark, "acts": [{"do": a, "at": t} for a, t in acts]}
S = []
def sh(beat, text, place, cam, move, cast=(), speaker="narrator", **kw):
    S.append({"beat": beat, "speaker": speaker, "text": text, "set": place, "camera": cam, "move": move, "cast": list(cast), **kw})
W = lambda who, txt: {"type": "board", "held_by": who, "text": txt}
sh("hook", "In 1858, Parliament soaked its curtains in chemicals.", "square", "wide", "push",
   [C("vic_alder", "B", ("hold", 0.0), ("tremble", 1.2))], props=[{"type": "bottle", "held_by": "vic_alder", "text": "LIME"}], sfx=[{"name": "splash", "at": 0.3}])
sh("hook", "To hide a smell. What smell?", "square", "close", "crash_zoom",
   [C("vic_alder", "B", ("facepalm", 0.2))], overlay={"type": "circle", "text": "?"})
sh("concept", "London's toilets emptied straight into the River Thames.", "river", "wide", "pan_r",
   [C("vic_ned", "B", ("point", 0.3), ("shock", 1.4))], overlay={"type": "arrow", "text": "THE THAMES"})
sh("concept", "And Londoners drank from that same river.", "river", "medium", "push",
   [C("vic_ned", "B", ("hold", 0.0))], props=[{"type": "bottle", "held_by": "vic_ned", "text": "WATER?"}])
sh("concept", "Rich or poor, everyone shared the same brown water.", "street", "two_shot", "pan_l",
   [C("vic_alder", "A", ("hold", 0.0)), C("vic_ned", "C", ("shrug", 0.6))], props=[{"type": "bottle", "held_by": "vic_alder", "text": "TEA"}])
sh("setup", "New flush toilets made it worse. Far more water, far more waste.", "shop", "medium", "drift",
   [C("vic_ned", "B", ("scratch_head", 0.2), ("shrug", 1.4))], overlay={"type": "chalk", "text": "FLUSH!"})
sh("setup", "Then came the hot summer of 1858.", "street", "wide", "tilt_down",
   [C("vic_ned", "B", ("sigh", 0.3))], overlay={"type": "chalk", "text": "SUMMER 1858"})
sh("deadline", "The river baked. The smell hit Parliament's windows.", "square", "two_shot", "push",
   [C("vic_alder", "A", ("shock", 0.2)), C("vic_ned", "C", ("cower", 0.6))], overlay={"type": "stamp", "text": "THE GREAT STINK"}, sfx=[{"name": "gasp", "at": 0.2}])
sh("deadline", "Close the windows! Soak the curtains!", "square", "close", "crash_zoom",
   [C("vic_alder", "A", ("angry", 0.1), ("point", 1.0))], speaker="vic_alder")
sh("obstacle", "Experts argued it was only a bad smell.", "shop", "two_shot", "pan_l",
   [C("vic_alder", "A", ("shrug", 0.2)), C("vic_ned", "C", ("shake_head", 0.8))], props=[W("vic_alder", "JUST A SMELL")])
sh("obstacle", "Meanwhile cholera had killed thousands of Londoners.", "street", "medium", "push",
   [C("vic_ned", "B", ("sad", 0.2))], overlay={"type": "cross", "text": "CHOLERA"}, mood="sad")
sh("con", "Now the lawmakers could smell it themselves.", "square", "wide", "push",
   [C("vic_alder", "B", ("tremble", 0.2))], freeze="WAIT...")
sh("con", "They passed a sewer law in about eighteen days.", "square", "medium", "crash_zoom",
   [C("vic_alder", "A", ("present", 0.2), ("nod", 1.2))], props=[{"type": "letter", "held_by": "vic_alder", "text": "SEWER ACT"}], overlay={"type": "stamp", "text": "18 DAYS"}, sfx=[{"name": "paper", "at": 0.2}])
sh("con", "The engineer? Joseph Bazalgette.", "station", "medium", "push",
   [C("vic_pike", "A", ("wave", 0.2))], overlay={"type": "label", "text": "JOSEPH BAZALGETTE"}, mood="upbeat")
sh("escalate", "His plan: giant tunnels along the river.", "river", "wide", "pan_l",
   [C("vic_pike", "A", ("point", 0.2))], props=[{"type": "map", "held_by": "vic_pike", "text": "SEWERS"}])
sh("escalate", "Catch the waste. Carry it east.", "line", "wide", "pan_r", [C("vic_pike", "enter_l", ("walk", 0.0))],
   moves=[{"id": "loco", "from": [-30, 0, 0], "to": [30, 0, 0], "t0": 0, "t1": 2.0}], sfx=[{"name": "whoosh", "at": 0.2}])
sh("escalate", "Far past the city.", "line", "medium", "drift", [C("vic_pike", "B", ("present", 0.1))], overlay={"type": "arrow", "text": "EAST"})
sh("escalate", "Then he did something strange. He doubled the pipe size.", "station", "close", "crash_zoom",
   [C("vic_pike", "A", ("hips", 0.1), ("laugh", 1.2))], props=[W("vic_pike", "PIPE x2")])
sh("escalate", "Bricks? Over three hundred million.", "line", "insert", "crash_zoom",
   [C("vic_ned", "B", ("pick_up", 0.1))], props=[{"type": "box", "held_by": "vic_ned"}], overlay={"type": "stamp", "text": "318,000,000"}, sfx=[{"name": "thud", "at": 0.8}])
sh("twist", "We only get to dig this once!", "station", "two_shot", "push",
   [C("vic_pike", "A", ("point_you", 0.1)), C("vic_ned", "C", ("shock", 0.6))], speaker="vic_pike")
sh("twist", "About eleven hundred miles of street sewers were dug.", "street", "wide", "pan_r",
   [C("vic_ned", "B", ("pick_up", 0.2))], props=[{"type": "tool", "held_by": "vic_ned"}], overlay={"type": "stamp", "text": "1,100 MILES"}, sfx=[{"name": "pick", "at": 0.6}])
sh("payoff", "Cholera faded from London.", "shop", "medium", "push", [C("vic_ned", "B", ("cheer", 0.3))], overlay={"type": "cross", "text": "CHOLERA"})
sh("payoff", "And London grew far bigger than anyone planned.", "street", "wide", "drift",
   [C("vic_alder", "A", ("shock", 0.3))], overlay={"type": "chalk", "text": "MILLIONS MORE"})
sh("payoff", "On top of the tunnels, he built the Thames Embankment.", "river", "wide", "tilt_up",
   [C("vic_pike", "A", ("walk", 0.0))], overlay={"type": "label", "text": "EMBANKMENT"}, sfx=[{"name": "footsteps", "at": 0.0}])
sh("payoff", "Today, trains run inside it.", "station", "wide", "pan_r", [C("vic_ned", "B", ("wave", 0.6))],
   moves=[{"id": "loco", "from": [-40, 6, 0], "to": [-4, 6, 0], "t0": 0, "t1": 2.0, "ease": "out"}], sfx=[{"name": "train", "at": 0.0}])
sh("payoff", "Those doubled pipes still carry it today.", "river", "medium", "push",
   [C("vic_pike", "A", ("present", 0.2), ("laugh", 1.4))], props=[W("vic_pike", "STILL WORKING")])
sh("payoff", "All because Parliament once had to smell its own river.", "square", "wide", "pull",
   [C("vic_alder", "B", ("facepalm", 0.3))], props=[{"type": "bottle", "held_by": "vic_alder", "text": "LIME"}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
    for k, v in (("props", []), ("sfx", []), ("transition", "cut")):
        s.setdefault(k, v)
plan = {"id": "great_stink", "title": "The Summer London Smelled So Bad It Built Sewers", "topic": "The Great Stink of 1858 and Joseph Bazalgette's London sewer system",
        "hook_title": "WHY SOAK THE CURTAINS?", "keywords": ["Thames", "stink", "sewer", "Parliament", "cholera", "Bazalgette", "pipe", "toilets"],
        "cast": ["vic_pike", "vic_alder", "vic_ned"], "channel": "channel1",
        "sources": ["https://en.wikipedia.org/wiki/Great_Stink", "https://en.wikipedia.org/wiki/Joseph_Bazalgette"],
        "places": {
            "square": {"world": "victorian_square", "remove": ["cart"], "prompt": "Victorian Westminster square before Parliament with a clock tower"},
            "street": {"world": "victorian_square", "prompt": "A crowded Victorian London street with carts"},
            "river": {"world": "victorian_square", "remove": ["cart"], "prompt": "A Victorian London embankment beside the brown River Thames"},
            "shop": {"world": "clock_shop", "prompt": "A cramped Victorian London shop interior"},
            "station": {"world": "station", "prompt": "A Victorian brick station hall where engineers plan"},
            "line": {"world": "railway_line", "prompt": "Open land east of Victorian London"}},
        "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
