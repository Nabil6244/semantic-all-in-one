"""Opening hook: a fast "Coming up!" teaser of the episode's funniest moments, placed before the cold open.

Story render json: "hook": "auto" (default) | false | [[t0, dur], ...] (episode seconds).
render.py and mix.py both call windows(), so the picture and the sound are cut from the same moments.
Output time t < length(win) plays episode time source_time(t); after that the episode runs shifted by length(win).
"""
FUN = {"tumble": 5, "sneeze": 5, "dance": 4, "wobble": 3, "freeze": 3, "silly": 2, "jump": 2, "laugh": 1, "march": 1}
CLIP, N_CLIPS, MIN_GAP, SKIP_START = 2.3, 4, 60.0, 35.0


def windows(story, tl):
    cfg = story.get("hook", "auto")
    if not cfg:
        return []
    if isinstance(cfg, list):
        return [(float(a), float(b)) for a, b in cfg]
    cands = []
    seen_chant = False
    for ln in tl["lines"]:
        if ln["start"] < SKIP_START or ln["start"] > tl["total"] - 20:
            continue
        acts = [ln.get("act")] + list((ln.get("also") or {}).values())
        top = max(acts, key=lambda a: FUN.get(a, 0))
        score = FUN.get(top, 0)
        if ln.get("chant") and not seen_chant:          # the first song: kids recognise it at once
            score, top, seen_chant = max(score, 4), "song", True
        if ln.get("give") or ln.get("pic"):
            score = max(score, 1)
        if score:
            # a sneeze / tumble pays off at the end of its line: show the payoff, not the wind-up
            t0 = ln["end"] - CLIP + 0.7 if top in ("sneeze", "tumble") else ln["start"] - 0.1
            cands.append((score, max(ln["start"] - 0.1, t0), top))
    cands.sort(key=lambda c: (-c[0], c[1]))
    picked, kinds = [], set()
    for score, t0, top in cands:                        # different moments: never the same gag twice
        if top not in kinds and all(abs(t0 - p) >= MIN_GAP for p in picked):
            picked.append(t0)
            kinds.add(top)
        if len(picked) == N_CLIPS:
            break
    return [(max(0.0, t0), CLIP) for t0 in sorted(picked)]


def length(win):
    return sum(d for _, d in win)


def source_time(t, win):
    """Episode time shown at output time t (t inside the hook)."""
    for t0, d in win:
        if t < d:
            return t0 + t
        t -= d
    return None
