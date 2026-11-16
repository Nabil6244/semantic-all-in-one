"""Place rules for cartoon2d episodes.

1. A new place at least every ~2 minutes: no stay in one place longer than MAX_STAY seconds.
2. Every background is new to the show: a background used by another episode is refused (cartoon2d/art/bg/used.json).
3. Inside one episode a place may come back once (e.g. home again for the goodbye song), not more.

python3 cartoon2d/places.py check <story_render.json>      problems, exit 1 if any (render.py runs the same check)
python3 cartoon2d/places.py register <story_render.json>   record this episode's backgrounds as used (render.py does
                                                            this after a full render)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "cartoon2d" / "art" / "bg" / "used.json"
MAX_STAY = 125.0                 # seconds: "after 2 minutes" with a few seconds for the line that moves everyone on
MAX_VISITS = 2


def _mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def stays(story, tl):
    """[(place, t0, t1)] in episode time. A change happens in the pause before its line (as render.plan does)."""
    places = story.get("places") or {"main": {}}
    cur = story.get("start_place", next(iter(places)))
    out, t0 = [], 0.0
    for ln in tl["lines"]:
        p = ln.get("place")
        if p and p != cur:
            tc = max(0.0, ln["start"] - 0.45)
            out.append((cur, t0, tc))
            cur, t0 = p, tc
    out.append((cur, t0, tl["total"]))
    return [s for s in out if s[2] - s[1] > 0.5]


def registry():
    return json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}


def problems(story, tl):
    """A story can loosen these for its channel: "rules": {"max_stay": 300, "unique_backgrounds": false}."""
    rules = story.get("rules") or {}
    max_stay = rules.get("max_stay", MAX_STAY)
    probs = []
    for name, t0, t1 in stays(story, tl):
        if t1 - t0 > max_stay:
            probs.append(f"'{name}' stays {_mmss(t1 - t0)} ({_mmss(t0)}-{_mmss(t1)}): move the story to a new place by "
                         f"{_mmss(t0 + max_stay)} (and every {max_stay / 60:.0f} minutes or so after)")
    visits = {}
    for name, *_ in stays(story, tl):
        visits[name] = visits.get(name, 0) + 1
    probs += [f"'{n}' is visited {v} times: a place may come back once at most" for n, v in visits.items()
              if v > rules.get("max_visits", MAX_VISITS)]
    if rules.get("unique_backgrounds", True) is False:
        return probs
    used = registry()
    ep = story["name"]
    seen = {n for n, *_ in stays(story, tl)}
    for name, pl in (story.get("places") or {}).items():
        if name not in seen:
            continue
        others = [e for e in used.get(pl["background"], []) if e != ep]
        if others:
            probs.append(f"'{name}' uses {pl['background']}, already used by {', '.join(others)}: paint a new background")
    return probs


def register(story, tl=None):
    used = registry()
    seen = {n for n, *_ in stays(story, tl)} if tl else None
    for name, pl in (story.get("places") or {}).items():
        if seen is not None and name not in seen:
            continue
        eps = used.setdefault(pl["background"], [])
        if story["name"] not in eps:
            eps.append(story["name"])
    REGISTRY.write_text(json.dumps(used, indent=1) + "\n")


def _load(path):
    story = json.loads(Path(path).read_text())
    tl = json.loads((ROOT / story["timeline"]).read_text())
    return story, tl


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    story, tl = _load(path)
    if cmd == "register":
        register(story, tl)
        print("REGISTERED", story["name"])
    else:
        for name, t0, t1 in stays(story, tl):
            print(f"  {name:12s} {_mmss(t0)}-{_mmss(t1)}  ({_mmss(t1 - t0)})")
        probs = problems(story, tl)
        for p in probs:
            print("PROBLEM", p)
        print("OK" if not probs else f"{len(probs)} problem(s)")
        sys.exit(1 if probs else 0)
