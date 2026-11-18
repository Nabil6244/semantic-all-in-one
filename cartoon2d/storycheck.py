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
HOOK_BY = 2.0             # s: the first line (the hook) starts by then
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


RULES = {"max_quiet": MAX_QUIET, "max_talk": MAX_TALK, "max_no_turn": MAX_NO_TURN, "goal_by": GOAL_BY, "hook_by": HOOK_BY, "calm_in_last": CALM_IN_LAST,
         "teaser_in_last": TEASER_IN_LAST, "end_screen": END_SCREEN, "learn_min": 3, "turn_gap": 0.0}


def check(story, tl, script=None):
    """Limits come from RULES, and a story may change them for its channel ("rules" in the render json), e.g. the baby
    speech channel: {"learn_min": 5, "turn_gap": 2.5, "max_no_turn": 45}. turn_gap = the silence a child gets after a
    "your turn" line before anyone speaks again."""
    lines, total = tl["lines"], tl["total"]
    R = {**RULES, **(story.get("rules") or {})}
    MAX_QUIET, MAX_TALK, MAX_NO_TURN, GOAL_BY = R["max_quiet"], R["max_talk"], R["max_no_turn"], R["goal_by"]
    CALM_IN_LAST, TEASER_IN_LAST, END_SCREEN = R["calm_in_last"], R["teaser_in_last"], R["end_screen"]
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
    # the hook: no preview, no slow hello: the very first line grabs attention (a surprise, a sound, something to see)
    if lines:
        h = lines[0]
        loud = h.get("sfx") or h.get("fx") or h.get("pic") or h.get("game") or h.get("hold") or "move" in events(h)
        if h["start"] > R["hook_by"] or not loud or h["text"].rstrip()[-1:] not in "!?":
            probs.append(f"no hook: the first line must start by {R['hook_by']:.0f} s and grab attention (a big move, sound, "
                         "effect or picture, said with ! or ?), not a plain hello")
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
    # adventure (Kids Channel 3 play adventures, docs/cartoon2d/CHANNEL3_PLAN.md): every play stop opens with its title
    # card, has a ride or game, a learning moment the child joins (your turn) and one goal item found; 6-8 stops, none
    # over 3 minutes, and the goal is counted on screen ("goal": {"pic", "n"} in the render json)
    if story.get("adventure"):
        stays = places.stays(story, tl)
        stops = [s_ for s_ in stays[1:-1]]                  # not the opening place or the goodbye place
        if not 6 <= len(stops) <= 8:
            probs.append(f"{len(stops)} play stops, needs 6-8")
        gl = story.get("goal") or {}
        if not gl.get("pic") or not gl.get("n"):
            probs.append("no goal counter: the render json needs \"goal\": {\"pic\": ..., \"n\": ...}")
        found = [ln for ln in lines if ln.get("found") == gl.get("pic")]
        n_lost = sum(1 for ln in lines if ln.get("lost") == gl.get("pic"))   # a setback loses one; it is found again
        if gl.get("n") and len(found) - n_lost != gl["n"]:
            probs.append(f"goal says {gl.get('n')} {gl.get('pic')}s but {len(found) - n_lost} are found"
                         + (f" ({len(found)} finds, {n_lost} lost again)" if n_lost else ""))
        for name, t0, t1 in stops:
            inside = [ln for ln in lines if t0 <= ln["start"] < t1]
            if t1 - t0 > R.get("max_stop", 180):
                probs.append(f"stop '{name}' {_mmss(t0)} runs {t1 - t0:.0f} s, max {R.get('max_stop', 180)} s")
            if not any(ln.get("title") for ln in inside[:3]):
                probs.append(f"stop '{name}' {_mmss(t0)} has no title card on arrival (title: on one of its first lines)")
            if not any(ln.get("game") for ln in inside):
                probs.append(f"stop '{name}' {_mmss(t0)} has no ride or game")
            if not any(ln.get("your_turn") and (ln.get("card") or ln.get("pic")) for ln in inside):
                probs.append(f"stop '{name}' {_mmss(t0)} has no learning moment (a card or picture with your_turn)")
            if gl.get("pic") and not any(ln.get("found") == gl["pic"] for ln in inside):
                notes.append(f"stop '{name}' finds no {gl['pic']}")
        probs += story_problems(story, lines, stops, total)
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
        if n < R["learn_min"]:
            probs.append(f"learning word '{w}' said {n} time(s), needs {R['learn_min']}+")
    if R["turn_gap"] > 0:                                # babies need real silence to answer
        for a, b in zip(lines, lines[1:]):
            if a.get("your_turn") and b["start"] - a["end"] < R["turn_gap"] - 0.05:
                probs.append(f"'your turn' at {_mmss(a['start'])} leaves {b['start'] - a['end']:.1f} s to answer, needs "
                             f"{R['turn_gap']:.1f} s (gap_after)")
    probs += places.problems(story, tl)
    return probs, notes


def _sig(inside):
    """A stop's beat order: H problem shown, G play, S song, F found, X setback, B hero beat, J joke (repeats collapsed)."""
    out = []
    for ln in inside:
        for key, tag in (("find", "H"), ("game", "G"), ("chant", "S"), ("found", "F"), ("setback", "X"), ("beat", "B"),
                         ("funny", "J")):
            if ln.get(key) and (not out or out[-1] != tag):
                out.append(tag)
    return "".join(out)


def story_problems(story, lines, stops, total):
    """Adventure = a story, not a list of stops. 1) every goal item is stuck for a reason and the stop's play is how it
    is got back: its problem (find) comes before the play (game), the found after it; 2) the hero wants something and
    is scared of something early, takes a small brave step in the middle, beats the fear near the end; 3) at least one
    setback; 4) the goal-giver comes back at least every two stops; 5) no two stops in a row share a beat order, and no
    spoken line repeats across 3+ stops."""
    probs = []
    pic = (story.get("goal") or {}).get("pic")
    for name, t0, t1 in stops:
        inside = [ln for ln in lines if t0 <= ln["start"] < t1]
        fi = next((i for i, ln in enumerate(inside) if ln.get("find")), None)
        fo = next((i for i, ln in enumerate(inside) if pic and ln.get("found") == pic), None)
        if fo is None:
            continue
        if fi is None:
            probs.append(f"stop '{name}' {_mmss(t0)}: the {pic} is found but never shown stuck first (ep.stuck)")
            continue
        games = [i for i, ln in enumerate(inside) if ln.get("game")]
        if not any(fi < g < fo for g in games):
            probs.append(f"stop '{name}' {_mmss(t0)}: the play does not happen between the {pic}'s problem and its "
                         f"rescue, so the play is not how it is got back")
        if inside[fi]["start"] - t0 > 0.35 * (t1 - t0):
            probs.append(f"stop '{name}' {_mmss(t0)}: the {pic}'s problem comes {inside[fi]['start'] - t0:.0f} s in; "
                         f"show it in the first third of the stop")
    hero = story.get("hero")
    if not hero:
        probs.append("no hero: Episode(hero=...) - whose want and fear the story follows")
    else:
        beats = [(ln.get("beat"), ln["start"]) for ln in lines if ln.get("beat") and hero in _who(ln)]
        want = [t for b, t in beats if b == "want"]
        tries = [t for b, t in beats if b == "try"]
        pay = [t for b, t in beats if b == "payoff"]
        if not want or want[0] > 180:
            probs.append(f"the hero ({hero}) says what they want and fear (ep.want) in the first 3 minutes")
        if not tries or not want or not any(want[0] < t < (pay[0] if pay else total) for t in tries):
            probs.append(f"the hero ({hero}) needs a small brave step (ep.tries) between the want and the payoff")
        if not pay or pay[-1] < (stops[-2][1] if len(stops) > 1 else 0):
            probs.append(f"the hero ({hero}) beats the fear (ep.payoff) in the last two stops")
    if not any(ln.get("setback") for ln in lines):
        probs.append("no setback (ep.setback): something has to go wrong before the end")
    if story.get("giver"):
        wt = [ln["start"] for ln in lines if ln.get("waiting")]
        for a, b in zip(stops, stops[2:]):
            if not any(a[1] <= t < b[1] for t in wt):
                probs.append(f"the goal-giver is gone from {_mmss(a[1])} to {_mmss(b[1])}: bring them back (ep.waiting)")
                break
    sigs = [(name, t0, _sig([ln for ln in lines if t0 <= ln["start"] < t1])) for name, t0, t1 in stops]
    for (n1, _, s1), (n2, t2, s2) in zip(sigs, sigs[1:]):
        if s1 == s2:
            probs.append(f"stops '{n1}' and '{n2}' ({_mmss(t2)}) run the same beats in the same order ({s1})")
    seen = {}
    for name, t0, t1 in stops:
        for ln in lines:
            if t0 <= ln["start"] < t1 and not ln.get("chant"):
                k = re.sub(r"[^a-z ]", "", ln["text"].lower()).strip()
                if k:
                    seen.setdefault(k, set()).add(name)
    probs += [f"the line '{k}' is said at {len(v)} stops; write each stop its own words" for k, v in seen.items() if len(v) >= 3]
    return probs


def _who(ln):
    w = ln.get("who")
    return w if isinstance(w, list) else [w]


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
