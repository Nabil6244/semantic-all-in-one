"""Retention + story-bible checker for a voiced cartoon2d episode (docs/cartoon2d/STORY_BIBLE.md).

python3 cartoon2d/storycheck.py <story_render.json>     report + energy strip; exit 1 on problems
render.py runs problems() before a full render (with the place rules); a story with "storycheck": false skips it.

Reads the timeline (voiced lines with start/end and story fields) and, when the render json names it, the script json
("script": ".../epXX.json") for its "learn" words.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import places  # noqa: E402

MAX_QUIET = 40.0          # s without anything new
MAX_TALK = 20.0           # s of talking with no action / picture / card
MAX_NO_TURN = 75.0        # s between "Your turn!" moments
GOAL_BY = 15.0
CALM_IN_LAST = 180.0
TEASER_IN_LAST = 90.0
END_SCREEN = 20.0
BIG_ACTS = {"dance", "jump", "bounce", "frog", "kangaroo", "bunny", "spin", "tumble", "run", "walk", "march", "cheer", "yay",
            "stomp", "kick", "squat", "hands_up", "touch_head", "touch_toes", "catch", "freeze", "wobble", "sneeze", "silly", "clap"}


def _mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def events(ln):
    """What is 'new' on a line: the things that reset a child's attention."""
    ev = []
    for k in ("place", "game", "your_turn", "find", "found", "map", "pic", "title", "fx", "give", "hold"):
        if ln.get(k):
            ev.append(k)
    if ln.get("chant"):
        ev.append("song")
    acts = [ln.get("act")] + list((ln.get("also") or {}).values())
    if any(a in BIG_ACTS for a in acts if a):
        ev.append("move")
    return ev


def busy(ln):
    """Talk that still shows something (an action, a picture or a word card)."""
    return bool(events(ln) or ln.get("card") or (ln.get("act") and ln.get("act") not in ("talk", None)))


def check(story, tl, script=None):
    lines, total = tl["lines"], tl["total"]
    probs, notes = [], []
    # something new at least every MAX_QUIET s
    last = 0.0
    for ln in lines:
        if events(ln):
            if ln["start"] - last > MAX_QUIET:
                probs.append(f"nothing new {_mmss(last)}-{_mmss(ln['start'])} ({ln['start'] - last:.0f} s): add a game, picture, "
                             "move or your-turn")
            last = ln["start"]
    if total - last > MAX_QUIET + 25:
        probs.append(f"nothing new from {_mmss(last)} to the end")
    # talking with nothing to see
    run0 = None
    for ln in lines:
        if busy(ln):
            if run0 is not None and ln["start"] - run0 > MAX_TALK:
                probs.append(f"talking only {_mmss(run0)}-{_mmss(ln['start'])} ({ln['start'] - run0:.0f} s): give it an action or picture")
            run0 = None
        elif run0 is None:
            run0 = ln["start"]
    # your turn
    turns = [ln["start"] for ln in lines if ln.get("your_turn")]
    prev = 0.0
    for t in turns + [total]:
        if t - prev > MAX_NO_TURN and not (t == total and total - prev < MAX_NO_TURN + 40):
            probs.append(f"no 'Your turn!' {_mmss(prev)}-{_mmss(t)} ({t - prev:.0f} s)")
        prev = t
    # the goal
    if not any(ln.get("goal") and ln["start"] <= GOAL_BY for ln in lines):
        probs.append(f"the goal is not said (goal: true) in the first {GOAL_BY:.0f} s")
    # journey: every place change after the first opens with the map; every hidden object is found in its place
    if story.get("journey"):
        stays = places.stays(story, tl)
        for name, t0, t1 in stays[1:]:
            if not any(ln.get("map") is not None and t0 - 12 <= ln["start"] <= t0 + 12 for ln in lines):
                probs.append(f"'{name}' at {_mmss(t0)} has no map moment (map: k) around its arrival")
        finds = {}
        for ln in lines:
            if ln.get("find"):
                finds[ln["find"]["pic"]] = ln["start"]
        for ln in lines:
            if ln.get("found"):
                finds.pop(ln["found"], None)
        probs += [f"hidden '{p}' ({_mmss(t)}) is never found" for p, t in finds.items()]
        for name, t0, t1 in stays[1:]:
            if not any(ln.get("find") and t0 <= ln["start"] <= t1 for ln in lines):
                notes.append(f"'{name}' has no hidden object")
    # calm, teaser, end screen
    if not any(ln.get("calm") and ln["start"] >= total - CALM_IN_LAST for ln in lines):
        probs.append(f"no calm part (calm: true) in the last {CALM_IN_LAST / 60:.0f} minutes")
    if not any(ln.get("teaser") and ln["start"] >= total - TEASER_IN_LAST for ln in lines):
        probs.append(f"no teaser (teaser: true) in the last {TEASER_IN_LAST:.0f} s")
    ends = [ln for ln in lines if ln.get("endcard")]
    if not ends or total - ends[-1]["start"] < END_SCREEN:
        probs.append(f"the end screen needs {END_SCREEN:.0f} s after the endcard line (raise the script's tail)")
    # learning words
    for w in (script or {}).get("learn", []):
        n = sum(len(re.findall(rf"\b{re.escape(w)}\b", ln["text"], re.I)) for ln in lines)
        if n < 3:
            probs.append(f"learning word '{w}' said {n} time(s), needs 3+")
    probs += places.problems(story, tl)
    return probs, notes


def energy(tl, step=30.0):
    """One character per 30 s: how much happens (. quiet, - some, = busy, # very busy)."""
    total = tl["total"]
    out = []
    t = 0.0
    while t < total:
        n = sum(len(events(ln)) for ln in tl["lines"] if t <= ln["start"] < t + step)
        out.append(".-=#"[min(3, n // 2)])
        t += step
    return "".join(out)


def load(path):
    story = json.loads(Path(path).read_text())
    tl = json.loads((ROOT / story["timeline"]).read_text())
    script = json.loads((ROOT / story["script"]).read_text()) if story.get("script") else None
    return story, tl, script


def problems(story, tl):
    script = json.loads((ROOT / story["script"]).read_text()) if story.get("script") else None
    return check(story, tl, script)[0]


if __name__ == "__main__":
    story, tl, script = load(sys.argv[1])
    probs, notes = check(story, tl, script)
    print(f"length {_mmss(tl['total'])}, {len(tl['lines'])} lines")
    print("energy (30 s each):", energy(tl))
    for name, t0, t1 in places.stays(story, tl):
        print(f"  {name:14s} {_mmss(t0)}-{_mmss(t1)}")
    for n in notes:
        print("NOTE", n)
    for p in probs:
        print("PROBLEM", p)
    print("OK" if not probs else f"{len(probs)} problem(s)")
    sys.exit(1 if probs else 0)
