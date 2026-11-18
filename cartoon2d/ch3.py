"""Kids Channel 3 episode builder: play adventures in one big place (docs/cartoon2d/CHANNEL3_PLAN.md).

An episode script (scenes/ch3_<name>.py) does:
    from ch3 import Episode, LINA, NIA, POPPY, TOBI, ROSIE, FIZZ, PIP, DOT
    ep = Episode("ch3_ep01_playground", goal=("duckling", 5), music="sunny")
    ep.place("gate", "cartoon2d/art/bg/ch3_gate.png", [LINA, TOBI, ROSIE, FIZZ])
    ep.place("slide", "cartoon2d/art/bg/ch3_slide.png", [LINA, TOBI, ROSIE, FIZZ], rides={TOBI: "slide"})
    ep.say(LINA, "...", act="wave", place="gate", ...)        # any line field render.py / games.py knows
    ep.ask(LINA, "Can you ...?")                               # a your-turn line with a pause to answer
    ep.arrive("slide", "Wheee! The big slide!", "Slide Time!")  # place change + title card + a run in
    ep.write()                                                 # scenes/<name>.json (script) + <name>_render.json

The shape every episode follows (storycheck "adventure" rules check it): a hook line with the goal in the first 15 s,
the hello song, 6-8 play stops (title card, a ride or game, a learning moment with your turn, one goal item found),
the goal complete, a calm recap, a teaser, the goodbye song and the end screen.
Characters are laid out per place from who is there and which rides they take (rides need room beside the rider).

It has to be a story, not a list of stops (storycheck "story" rules):
    ep = Episode(..., hero=TOBI, giver="mama_duck")
    ep.want(TOBI, "I want to help! But not the big slide...")  # the hero's want + fear, early (beat "want")
    ep.tries(TOBI, "I'll try the little slide first!")          # a small brave step in the middle (beat "try")
    ep.payoff(TOBI, "I did it! I went down the big slide!")     # the fear beaten near the end (beat "payoff")
    ep.stuck("swings", ROSIE, "The duckling is too shy...")     # the goal item shown on arrival WITH its problem; the
                                                               # stop's play is how it gets solved, then ep.found(...)
    ep.setback(FIZZ, "TOOT TOOT!", lost=True)                   # something goes wrong; lost=True takes one off the count
    ep.waiting("Mama Duck is still waiting by the pond...")     # the goal-giver comes back between stops
    ep.say(..., funny=True)                                     # a sidekick joke (counted so stops don't all match)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINA, NIA, POPPY, TOBI, ROSIE, FIZZ, PIP, DOT = "lina", "nia", "poppy", "tobi", "rosie", "fizz", "pip", "dot"
CAST = {   # height (share of the world height), head tilt, the hand that holds things, Edge voice, rate, pitch
    LINA: (0.7, 0.35, "sl", "en-US-AvaNeural", "-4%", "+0Hz"),
    NIA: (0.55, 0.5, "sl", "en-US-AnaNeural", "-2%", "-6Hz"),
    POPPY: (0.55, 0.5, "sr", "en-US-AnaNeural", "+2%", "+4Hz"),
    TOBI: (0.4, 0.9, "sr", "en-US-AnaNeural", "+8%", "-16Hz"),
    ROSIE: (0.38, 0.9, "sl", "en-US-AnaNeural", "+6%", "+10Hz"),
    FIZZ: (0.5, 0.6, "sr", "en-US-GuyNeural", "+4%", "+18Hz"),
    PIP: (0.42, 0.6, "sr", "en-US-AnaNeural", "+10%", "-24Hz"),
    DOT: (0.52, 0.6, "sl", "en-US-GuyNeural", "-6%", "+8Hz"),
}
ASPECT = 1440 / 2560
ROOM = {None: (0.3, 0.3), "slide": (1.2, 0.3), "swing": (0.9, 0.9), "pit": (0.45, 0.45), "train": (0.3, 0.3)}   # in heights
ASK_GAP = 2.2


class Episode:
    def __init__(self, name, goal, music="sunny", host=LINA, kids=(TOBI, ROSIE), learn=(), teaser=None, hero=None,
                 giver=None):
        self.name, self.goal, self.music, self.host, self.kids = name, goal, music, host, list(kids)
        self.hero, self.giver = hero, giver
        self.lines, self.places, self.learn = [], {}, list(learn)

    # ---------------------------------------------------------------- places
    def place(self, name, background, who, rides=None, floor_y=0.9, music=None):
        self.places[name] = {"background": background, "floor_y": floor_y, "who": list(who), "rides": dict(rides or {}),
                             "music": music or self.music}

    def spots(self, name):
        """World x (0..1) for everyone: the people here spread out with room for their rides; the rest off stage."""
        pl = self.places[name]
        who = pl["who"]
        need = [tuple(r * CAST[w][0] * ASPECT for r in ROOM[pl["rides"].get(w)]) for w in who]
        used = sum(a + b for a, b in need)
        gap = max(0.0, (0.9 - used) / max(1, len(who) - 1)) if len(who) > 1 else 0.0
        x, out = 0.05, {}
        for w, (a, b) in zip(who, need):
            out[w] = round(x + a, 4)
            x += a + b + gap
        if x - gap > 0.97:
            raise SystemExit(f"place '{name}': {len(who)} characters and their rides do not fit ({x - gap:.2f} of the width)")
        off = [w for w in CAST if w not in out]
        for i, w in enumerate(off):
            out[w] = -0.4 - 0.15 * i if i % 2 == 0 else 1.4 + 0.15 * i
        return out

    def free_spot(self, name, y=0.84):
        """Where a hidden goal item can sit in a place: the middle of the widest empty stretch of floor (characters
        and their rides take their room), so nobody stands in front of it."""
        pl = self.places[name]
        sp = self.spots(name)
        taken = sorted((sp[w] - ROOM[pl["rides"].get(w)][0] * CAST[w][0] * ASPECT * 0.8,
                        sp[w] + ROOM[pl["rides"].get(w)][1] * CAST[w][0] * ASPECT * 0.8) for w in pl["who"])
        best, edge = (0.0, 0.5), 0.04
        for a, b in taken + [(0.96, 0.96)]:
            if a - edge > best[0]:
                best = (a - edge, (edge + a) / 2)
            edge = max(edge, b)
        return (round(best[1], 3), y)

    # ---------------------------------------------------------------- lines
    def say(self, who, text, **k):
        self.lines.append({"who": who, "text": text, **k})

    def ask(self, who, text, **k):
        k.setdefault("gap_after", ASK_GAP)
        k.setdefault("your_turn", True)
        self.say(who, text, **k)

    def arrive(self, place, text, title, who=None, act="run", **k):
        """Into a new play stop: everybody here runs in, the stop's title card pops up."""
        here = self.places[place]["who"]
        who = who or here
        also = {w: act for w in here if w not in (who if isinstance(who, list) else [who])}
        self.say(who, text, act=act, also=also, place=place, title=title, cam="group", chapter=title.replace("\n", " "),
                 sfx="whoosh", gap_after=0.5, **k)

    def found(self, who, text, pic=None, **k):
        pic = pic or self.goal[0]
        k.setdefault("act", "point")
        k.setdefault("cam", "group")
        self.say(who, text, found=pic, sfx="ding_3", **k)

    # ---------------------------------------------------------------- story beats
    def _place_now(self):
        return next((ln["place"] for ln in reversed(self.lines) if ln.get("place")), None)

    BACK_Y, BACK_SIZE = 0.66, 0.07

    def stuck(self, who, text, pic=None, spot=None, size=0.11, at=None, peek=None, mound=None, **k):
        """The goal item of this stop, shown from the arrival, with WHY it can't just be picked up. The stop's play
        is how the friends get it back (storycheck: the problem comes before the play, the find after it).
        Put it where the words say, so the picture matches:
          at=("slide", rider)  on the slide's platform (the rider's slide in this place)
          at=("swing", rider)  by the leg of the rider's swing frame
          at="back"            further back in the place (across the track, behind the water jets): higher, smaller
          peek=0.5, mound=(r, g, b)  only its top half shows over a mound until found (buried in sand, sunk in balls)"""
        place = self._place_now()
        spot = spot or self.free_spot(place)
        f = {"pic": pic or self.goal[0], "x": spot[0], "y": spot[1], "size": size}
        if at == "back":
            f.update(y=self.BACK_Y, size=min(size, self.BACK_SIZE))
        elif isinstance(at, tuple):
            kind, rider = at
            if self.places[place]["rides"].get(rider) != kind:
                raise SystemExit(f"stuck at {at}: {rider} has no {kind} in '{place}' (ep.place(..., rides=...))")
            f.update(on=kind, who=rider)
        if peek:
            f.update(peek=peek, mound=list(mound or (232, 200, 130)))
        k.setdefault("act", "point")
        k.setdefault("cam", "group")
        self.say(who, text, find=f, **k)

    def want(self, who, text, **k):
        k.setdefault("cam", "kids")
        self.say(who, text, beat="want", **k)

    def tries(self, who, text, **k):
        k.setdefault("cam", "kids")
        self.say(who, text, beat="try", **k)

    def payoff(self, who, text, **k):
        k.setdefault("cam", "kids")
        k.setdefault("fx", "stars")
        self.say(who, text, beat="payoff", **k)

    def setback(self, who, text, lost=False, **k):
        k.setdefault("cam", "group")
        k.setdefault("sfx", "boing")
        if lost:
            k["lost"] = self.goal[0]
            k.setdefault("pic", self.goal[0])
        self.say(who, text, setback=True, **k)

    def waiting(self, text, who=None, **k):
        """The goal-giver comes back between stops (still waiting, how many to go)."""
        k.setdefault("cam", "host")
        k.setdefault("pic", self.giver)
        self.say(who or self.host, text, waiting=True, **k)

    # ---------------------------------------------------------------- output
    def write(self, out_dir=None):
        out_dir = Path(out_dir or Path(__file__).resolve().parent / "scenes")
        script = {"voices": {w: {"voice": v[3], "rate": v[4], "pitch": v[5]} for w, v in CAST.items()},
                  "bpm": 104, "lead_in": 0.6, "gap": 0.45, "tail": 22.0, "lines": self.lines, "learn": self.learn}
        sp = out_dir / f"{self.name}.json"
        sp.write_text(json.dumps(script, indent=1))
        first = next(ln["place"] for ln in self.lines if ln.get("place"))
        rel = lambda p: str(Path(p).resolve().relative_to(ROOT)) if Path(p).is_absolute() else str(p)   # noqa: E731
        render = {
            "timeline": f"cartoon2d/build/{self.name}/audio/timeline.json", "build": f"cartoon2d/build/{self.name}",
            "name": self.name, "host": self.host, "kids": self.kids, "start_place": first,
            "places": {n: {"background": p["background"], "floor_y": p["floor_y"], "spots": self.spots(n)}
                       for n, p in self.places.items()},
            "cast": {w: {"dir": f"cartoon2d/cast/{w}", "height": v[0], "tilt": v[1], "hold_side": v[2],
                         **({"hop": 0.1, "listen": 3.0} if w == self.host else {})} for w, v in CAST.items()},
            "music": {n: p["music"] for n, p in self.places.items()},
            "props": ["cartoon2d/art/props"], "script": rel(sp), "storycheck": True, "adventure": True,
            "goal": {"pic": self.goal[0], "n": self.goal[1]},
            "hero": self.hero, "giver": self.giver,
            "collection": False,                                    # the goal counter replaces the old top-right strip
            "rules": {"max_stay": 240},
        }
        rp = out_dir / f"{self.name}_render.json"
        rp.write_text(json.dumps(render, indent=1))
        print(len(self.lines), "lines ->", sp, "+", rp.name)
        return sp, rp
