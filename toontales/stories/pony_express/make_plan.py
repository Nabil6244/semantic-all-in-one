"""Ch2 Short: The Pony Express (1860-1861): fastest mail in the West, beaten by a wire after 18 months."""
import json
from pathlib import Path

def C(who, mark, *acts):
    return {"id": who, "mark": mark, "acts": [{"do": a, "at": t} for a, t in acts]}
S = []
def sh(beat, text, place, cam, move, cast=(), speaker="narrator", **kw):
    S.append({"beat": beat, "speaker": speaker, "text": text, "set": place, "camera": cam, "move": move, "cast": list(cast), **kw})
B = lambda who, txt: {"type": "board", "held_by": who, "text": txt}
sh("hook", "A rider jumps off one horse and onto the next in two minutes.", "station", "wide", "pan_r",
   [C("hume", "enter_l", ("run", 0.0), ("jump", 1.2))], sfx=[{"name": "horse", "at": 0.0}], overlay={"type": "chalk", "text": "2 MINUTES"})
sh("hook", "He carries letters across half a continent. Why the rush?", "desert", "medium", "crash_zoom",
   [C("hume", "B", ("hold", 0.0))], props=[{"type": "sack", "held_by": "hume"}], overlay={"type": "circle", "text": "?"})
sh("concept", "This is the Pony Express.", "town", "wide", "push",
   [C("bart", "A", ("present", 0.2))], props=[{"type": "sign", "held_by": "bart", "text": "PONY EXPRESS"}])
sh("concept", "Missouri to California. About nineteen hundred miles.", "trail", "wide", "pan_l",
   [C("hume", "enter_r", ("run", 0.0))], props=[{"type": "map", "held_by": "hume", "text": "1,900 MILES"}], sfx=[{"name": "horse", "at": 0.0}])
sh("setup", "A letter by stagecoach took weeks.", "office", "medium", "push",
   [C("driver", "A", ("sigh", 0.2))], props=[{"type": "letter", "held_by": "driver", "text": "WEEKS"}])
sh("setup", "The owners promised ten days.", "office", "two_shot", "push",
   [C("bart", "A", ("money", 0.2)), C("driver", "C", ("laugh", 0.8))], overlay={"type": "stamp", "text": "10 DAYS"})
sh("setup", "Ten days? Horses get tired, mister!", "office", "close", "crash_zoom",
   [C("driver", "C", ("point", 0.1), ("laugh", 1.0))], speaker="driver")
sh("obstacle", "You see, it's like a relay race.", "station", "medium", "push",
   [C("bart", "A", ("explain", 0.0))], speaker="bart", props=[B("bart", "RELAY")])
sh("obstacle", "Stations every ten to fifteen miles, with a fresh horse waiting.", "trail", "wide", "drift",
   [C("sheriff", "B", ("wave", 0.3))], moves=[{"id": "wagon", "from": [-14, 3, 0], "to": [-4, 3, 0], "t0": 0, "t1": 2.0, "ease": "out"}], overlay={"type": "arrow", "text": "FRESH HORSE"})
sh("con", "Swap the horse. Keep the mail bag. Go.", "station", "two_shot", "crash_zoom",
   [C("hume", "A", ("throw", 0.1)), C("sheriff", "C", ("pick_up", 0.3))], props=[{"type": "sack", "held_by": "sheriff"}], sfx=[{"name": "whoosh", "at": 0.2}])
sh("con", "Day and night, rain or shine.", "desert", "wide", "pan_r", [C("hume", "enter_l", ("run", 0.0))], sfx=[{"name": "horse", "at": 0.0}])
sh("con", "Through snow, desert and mountains.", "trail", "wide", "pan_l", [C("hume", "enter_r", ("run", 0.0))], overlay={"type": "chalk", "text": "SNOW"})
sh("con", "Only one mail bag was ever lost.", "trail", "insert", "crash_zoom", [C("sheriff", "B", ("hold", 0.0), ("nod", 1.0))], props=[{"type": "sack", "held_by": "sheriff"}], overlay={"type": "stamp", "text": "ONE"})
sh("escalate", "In April 1860, the first mail rode west.", "town", "medium", "push",
   [C("bart", "A", ("cheer", 0.2)), C("hume", "C", ("wave", 0.6))], overlay={"type": "label", "text": "APRIL 1860"}, sfx=[{"name": "crowd", "at": 0.2}])
sh("escalate", "Sending a letter cost five dollars for half an ounce.", "office", "insert", "push",
   [C("driver", "B", ("shock", 0.4))], props=[{"type": "coins", "held_by": "driver"}], overlay={"type": "stamp", "text": "$5"}, sfx=[{"name": "coins", "at": 0.3}])
sh("escalate", "Lincoln's first speech as president crossed in under eight days.", "desert", "medium", "push",
   [C("hume", "B", ("hold", 0.0), ("fist_pump", 1.4))], props=[{"type": "letter", "held_by": "hume", "text": "LINCOLN"}], freeze="WAIT...")
sh("twist", "But beside the trail, men were planting poles.", "trail", "wide", "tilt_up",
   [C("sheriff", "B", ("pick_up", 0.2), ("look_around", 1.6))], props=[{"type": "tool", "held_by": "sheriff"}], sfx=[{"name": "pick", "at": 0.5}], mood="sad")
sh("twist", "Poles for a telegraph wire.", "office", "close", "crash_zoom",
   [C("driver", "A", ("point", 0.1), ("laugh", 0.9))], overlay={"type": "arrow", "text": "TELEGRAPH"})
sh("twist", "In October 1861 the wire reached California.", "town", "wide", "pan_r",
   [C("driver", "B", ("celebrate", 0.2))], overlay={"type": "chalk", "text": "OCT 1861"}, sfx=[{"name": "ding", "at": 0.2}])
sh("twist", "A message now crossed in minutes, not days.", "office", "medium", "push",
   [C("bart", "A", ("facepalm", 0.3))], props=[{"type": "letter", "held_by": "bart", "text": "MINUTES"}])
sh("payoff", "Two days later, the Pony Express shut down.", "station", "medium", "pull",
   [C("hume", "A", ("sad", 0.2)), C("bart", "C", ("sigh", 0.6))], overlay={"type": "stamp", "text": "CLOSED"})
sh("payoff", "It ran about eighteen months and lost its owners a fortune.", "office", "two_shot", "push",
   [C("bart", "A", ("plead", 0.2)), C("driver", "C", ("laugh", 0.8))], props=[{"type": "money", "held_by": "driver"}], overlay={"type": "cross", "text": "BROKE"})
sh("payoff", "Yet it's still the most famous mail in American history.", "town", "wide", "drift",
   [C("sheriff", "B", ("present", 0.3))], props=[{"type": "sign", "held_by": "sheriff", "text": "PONY EXPRESS"}], mood="upbeat")
sh("payoff", "All for riders who swapped horses in two minutes.", "station", "wide", "pan_r",
   [C("hume", "enter_l", ("run", 0.0), ("jump", 1.2))], sfx=[{"name": "horse", "at": 0.0}])
for i, s in enumerate(S):
    s["id"] = f"s{i + 1:02d}"
    for k, v in (("props", []), ("sfx", []), ("transition", "cut")):
        s.setdefault(k, v)
plan = {"id": "pony_express", "title": "The Pony Express Lasted 18 Months", "topic": "The Pony Express mail relay (April 1860 - October 1861) and the transcontinental telegraph that ended it",
        "hook_title": "WHY THE RUSH?", "keywords": ["Pony", "Express", "horse", "mail", "telegraph", "relay", "Lincoln", "rider"],
        "cast": ["bart", "driver", "hume", "sheriff"], "channel": "channel2",
        "sources": ["https://en.wikipedia.org/wiki/Pony_Express", "https://en.wikipedia.org/wiki/First_transcontinental_telegraph"],
        "places": {
            "station": {"world": "frontier_town", "remove": ["coffin"], "prompt": "A dusty Pony Express relay station with a corral"},
            "town": {"world": "frontier_town", "remove": ["coffin", "wagon"], "prompt": "A frontier town main street in 1860"},
            "office": {"world": "frontier_office", "prompt": "An 1860 express company office with a safe"},
            "trail": {"world": "frontier_desert", "prompt": "A long western trail with a wagon"},
            "desert": {"world": "frontier_desert", "remove": ["wagon"], "prompt": "Open desert with red rocks and scrub"}},
        "shots": S}
Path(__file__).with_name("plan.json").write_text(json.dumps(plan, indent=1))
print(len(S), "shots")
