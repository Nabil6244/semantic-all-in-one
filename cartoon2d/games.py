"""Games for cartoon2d episodes: the timing of every game event, shared by render.py (pictures) and mix.py (sounds).

A script line may carry  "game": {...}  or a list of them (times are relative to that line):
  {"type": "throw",   "from": who, "to": who, "pic": "ball", "bounces": 1}   ball thrown, bounces on the floor, caught
  {"type": "dribble", "who": who, "n": 4, "pic": "ball"}                    bounce the ball in place (hand <-> floor)
  {"type": "kick",    "who": who, "to": who | 0..1, "pic": "ball"}           kicked along the floor with little hops
  {"type": "trampoline", "who": who}  ... {"type": "trampoline_off", "who": who}   a trampoline under them (act "bounce")
  {"type": "balloons", "colors": ["red", "blue"], "pop": true}             balloons float up, then pop with confetti
  {"type": "hide", "who": who}  ... {"type": "found", "who": who}          hides behind a toy box, peeks out now and then
  {"type": "slide" | "swing" | "train" | "pit", "who": ...}                play rides (see rides.py)
A line with "your_turn": true shows a "Your turn!" badge in the pause after it (the child joins in), with a chime.
"""

BALL_FLIGHT = 1.15


def _games(ln):
    g = ln.get("game")
    return [] if not g else (g if isinstance(g, list) else [g])


def plan(tl):
    """Absolute-time events: throws/dribbles/kicks (ball paths), trampolines, balloons, hides, your-turn badges."""
    lines = tl["lines"]
    ev = {"ball": [], "tramp": [], "balloons": [], "hide": [], "turn": [], "ride": []}
    open_tr, open_hd = {}, {}
    for i, ln in enumerate(lines):
        t0 = ln["start"]
        nxt = lines[i + 1]["start"] if i + 1 < len(lines) else tl["total"]
        if ln.get("place"):                                   # a new place clears trampolines and hiding spots
            for d, key in ((open_tr, "tramp"), (open_hd, "hide")):
                for w, s in list(d.items()):
                    ev[key].append({"who": w, "t0": s, "t1": max(s, t0 - 0.45)})
                d.clear()
        for g in _games(ln):
            k = g["type"]
            pic = g.get("pic", "ball")
            if k == "throw":
                b = int(g.get("bounces", 1))
                dur = BALL_FLIGHT + 0.25 * b
                s = t0 + float(g.get("at", 0.35))
                hits = [s + dur * (j + 1) / (b + 1) for j in range(b)]
                ev["ball"].append({"kind": "throw", "from": g["from"], "to": g["to"], "pic": pic, "t0": s, "t1": s + dur, "hits": hits})
            elif k == "dribble":
                n = int(g.get("n", 4))
                per = 0.55
                s = t0 + float(g.get("at", 0.2))
                ev["ball"].append({"kind": "dribble", "who": g["who"], "pic": pic, "t0": s, "t1": s + n * per,
                                   "hits": [s + per * (j + 0.5) for j in range(n)], "per": per})
            elif k == "kick":
                s = t0 + float(g.get("at", 0.45))
                ev["ball"].append({"kind": "kick", "who": g["who"], "to": g.get("to"), "pic": pic, "t0": s, "t1": s + 1.3,
                                   "hits": [s + 0.55, s + 0.95, s + 1.2]})
            elif k == "trampoline":
                open_tr.setdefault(g["who"], max(0.0, t0 - 0.3))
            elif k == "trampoline_off":
                if g["who"] in open_tr:
                    ev["tramp"].append({"who": g["who"], "t0": open_tr.pop(g["who"]), "t1": t0})
            elif k == "balloons":
                cols = g.get("colors", ["red", "blue", "yellow"])
                end = max(ln["end"], t0 + 1.5 * len(cols) + 1.0)
                pops = [t0 + 1.4 + 1.0 * j for j in range(len(cols))] if g.get("pop", True) else []
                ev["balloons"].append({"t0": t0, "t1": end + 0.8, "colors": cols, "pops": pops})
            elif k in ("slide", "swing", "train", "pit"):       # play rides (rides.py)
                import rides
                rides.plan_line(ev, g, lines, i, tl["total"])
            elif k == "hide":
                open_hd.setdefault(g["who"], t0)
            elif k == "found":
                if g["who"] in open_hd:
                    ev["hide"].append({"who": g["who"], "t0": open_hd.pop(g["who"]), "t1": t0 + 0.2})
        if ln.get("your_turn"):
            ev["turn"].append({"t0": ln["end"] + 0.15, "t1": max(ln["end"] + 1.2, nxt - 0.1)})
    for w, s in open_tr.items():
        ev["tramp"].append({"who": w, "t0": s, "t1": tl["total"] + 1})
    for w, s in open_hd.items():
        ev["hide"].append({"who": w, "t0": s, "t1": tl["total"] + 1})
    return ev


def sfx(tl, ev=None):
    """Sound effects for the mixer: whoosh on a throw, boing on every bounce, burst on a balloon pop, chime on your turn."""
    ev = ev or plan(tl)
    out = []
    for b in ev["ball"]:
        if b["kind"] in ("throw", "kick"):
            out.append({"t": b["t0"], "name": "whoosh", "gain_db": -9})
        for h in b["hits"]:
            out.append({"t": h, "name": "boing", "gain_db": -7})
    for bl in ev["balloons"]:
        for p in bl["pops"]:
            out.append({"t": p, "name": "burst", "gain_db": -4})
    for tu in ev["turn"]:
        out.append({"t": tu["t0"], "name": "chime", "gain_db": -6})
    import rides
    out += rides.sfx(ev)
    # trampoline / bounce landings: the render's hop timing (lines with act bounce)
    for ln in tl["lines"]:
        acts = [ln.get("act")] + list((ln.get("also") or {}).values())
        if "bounce" in acts:
            n = max(1, round((ln["end"] - ln["start"]) / 0.75))
            per = max(0.6, (ln["end"] - ln["start"]) / n)
            for j in range(n):
                out.append({"t": ln["start"] + per * (j + 1) - 0.02, "name": "boing", "gain_db": -9})
    return out


def pics(tl):
    """Pictures the games need (balls etc.), for render.load()."""
    names = set()
    for ln in tl["lines"]:
        for g in _games(ln):
            if g["type"] in ("throw", "dribble", "kick"):
                names.add(g.get("pic", "ball"))
            if g["type"] == "balloons":
                names |= {f"balloon_{c}" for c in g.get("colors", ["red", "blue", "yellow"])}
    return names
