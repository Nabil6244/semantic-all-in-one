"""Plan checker: finds screen problems before rendering and repairs what it can.

check(spec) -> list of problems (strings).  repair(spec) -> (fixed spec, notes).
Rules:
  hold      no beat longer than timeline.MAX_HOLD (split it, with a new pose)
  hook      something moves in the first beat (the lead runs in)
  still     every beat changes a pose, or someone is mid-move during it
  variety   a figure never does the same still pose three acted beats running
  camera    the same framing never three beats running
  caption   one short line (warned, the director keeps them short)
  onscreen  figures stay inside the frame once they have entered, and don't stand on each other
"""
import copy

from . import poses, timeline

ROTATION = ("point", "think", "shrug", "stand", "cheer")
CAPTION_MAX = 38


def _acted(beat, name):
    return (beat.get("acts") or {}).get(name)


def _moving_during(spec, i):
    """True if some figure started a walk/run/jump earlier and is still going in beat i."""
    b = spec["beats"][i]
    for j in range(i - 1, max(-1, i - 4), -1):
        for a in (spec["beats"][j].get("acts") or {}).values():
            if a["do"] in ("walk", "run", "jump") and spec["beats"][j]["t"] + 1.2 > b["t"]:
                return True
    return False


def _fresh(recent):
    for p in ROTATION:
        if p not in recent:
            return p
    return "stand"


def _split(spec, i):
    b = spec["beats"][i]
    half = round(b["dur"] / 2, 3)
    words = b.get("words") or []
    cut = len(words) // 2
    if words and cut:
        mid_t = words[cut]["t"]
        if 0.6 < mid_t - b["t"] < b["dur"] - 0.6 and mid_t - b["t"] <= timeline.MAX_HOLD:
            half = round(mid_t - b["t"], 3)
    second = copy.deepcopy(b)
    second["t"] = round(b["t"] + half, 3)
    second["dur"] = round(b["dur"] - half, 3)
    b["dur"] = half
    if words and cut:
        b["words"], second["words"] = words[:cut], words[cut:]
        cap = b["caption"].split()
        b["caption"], second["caption"] = " ".join(cap[:cut]), " ".join(cap[cut:])
    actor = b.get("actor") or next(iter(spec["figures"]))
    recent = [x.get("action") for x in spec["beats"][max(0, i - 2):i + 1]]
    pose = _fresh(recent)
    second["acts"] = {actor: {"do": pose}}
    second["action"] = pose
    spec["beats"].insert(i + 1, second)


def check(spec):
    probs = []
    beats = spec["beats"]
    lead = next(iter(spec["figures"]))
    for i, b in enumerate(beats):
        if b["dur"] > timeline.MAX_HOLD + 1e-9:
            probs.append(f"hold: beat {i + 1} lasts {b['dur']:g} s")
        if not b.get("acts") and not _moving_during(spec, i):
            probs.append(f"still: beat {i + 1} changes no pose")
        if len((b.get("caption") or "").replace("*", "")) > CAPTION_MAX:
            probs.append(f"caption: beat {i + 1} line is too long")
    first = beats[0].get("acts") or {}
    if not any(a["do"] in ("walk", "run", "jump") for a in first.values()):
        probs.append("hook: nothing moves in the first beat")
    for name in spec["figures"]:
        seq = [(i, _acted(b, name)["do"]) for i, b in enumerate(beats) if _acted(b, name)]
        for (i0, a), (i1, b_), (i2, c) in zip(seq, seq[1:], seq[2:]):
            if a == b_ == c and a in poses.STATIC and "action" not in beats[i1].get("locked", ()):
                probs.append(f"variety: {name} does '{a}' three times running (beats {i0 + 1}-{i2 + 1})")
    kinds = [(b.get("camera") or {}).get("kind") for b in beats]
    for i in range(2, len(kinds)):
        if kinds[i] and kinds[i] == kinds[i - 1] == kinds[i - 2] and "camera" not in beats[i - 1].get("locked", ()):
            probs.append(f"camera: same '{kinds[i]}' framing for beats {i - 1}-{i + 1}")
    probs += _screen(spec)
    return probs


def _screen(spec):
    probs = []
    try:
        frames = timeline.simulate(spec)
    except timeline.TimelineError as e:
        return [f"plan: {e}"]
    W = spec["size"][0]
    fps = int(spec.get("fps", 30))
    names = list(spec["figures"])
    entered = {n: False for n in names}
    out_for = {n: 0 for n in names}
    close_for = 0
    reported = set()
    last_beat_t = spec["beats"][-1]["t"]
    for fr in frames:
        xs = {}
        for f in fr["figs"]:
            x = f["joints"]["pelvis"][0]
            xs[f["name"]] = x
            inside = 0.05 * W < x < 0.95 * W
            if inside:
                entered[f["name"]] = True
            if entered[f["name"]] and not inside and fr["t"] < last_beat_t:
                out_for[f["name"]] += 1
                if out_for[f["name"]] > fps // 2 and f["name"] not in reported:
                    probs.append(f"onscreen: {f['name']} leaves the frame at {fr['t']:.1f} s")
                    reported.add(f["name"])
            else:
                out_for[f["name"]] = 0
        on = [n for n in names if entered[n] and 0.05 * W < xs[n] < 0.95 * W]
        if len(on) == 2 and abs(xs[on[0]] - xs[on[1]]) < 0.12 * W:
            close_for += 1
            if close_for == fps // 2:
                probs.append(f"onscreen: figures overlap at {fr['t']:.1f} s")
        else:
            close_for = 0
    return probs


def repair(spec, max_rounds=4):
    spec = copy.deepcopy(spec)
    notes = []
    lead = next(iter(spec["figures"]))
    for _ in range(max_rounds):
        probs = check(spec)
        if not probs:
            break
        beats = spec["beats"]
        changed = False
        for i in range(len(beats) - 1, -1, -1):              # back to front so indexes stay valid
            if beats[i]["dur"] > timeline.MAX_HOLD + 1e-9:
                _split(spec, i)
                notes.append(f"fixed hold: split beat {i + 1}")
                changed = True
        first = beats[0].setdefault("acts", {})
        if not any(a["do"] in ("walk", "run", "jump") for a in first.values()):
            first[lead] = {"do": "jump"}
            beats[0]["action"] = "jump"
            notes.append("fixed hook: lead jumps on the first beat")
            changed = True
        for i, b in enumerate(beats):
            if not b.get("acts") and not _moving_during(spec, i):
                actor = b.get("actor") or lead
                recent = [x.get("action") for x in beats[max(0, i - 2):i]]
                pose = _fresh(recent)
                b["acts"] = {actor: {"do": pose}}
                b["action"] = pose
                notes.append(f"fixed still: beat {i + 1} -> {actor} {pose}")
                changed = True
        for name in spec["figures"]:
            seq = [i for i, b in enumerate(beats) if _acted(b, name)]
            for i0, i1, i2 in zip(seq, seq[1:], seq[2:]):
                a, b_, c = (_acted(beats[k], name)["do"] for k in (i0, i1, i2))
                if a == b_ == c and a in poses.STATIC and "action" not in beats[i1].get("locked", ()):
                    pose = _fresh([a])
                    beats[i1]["acts"][name]["do"] = pose
                    notes.append(f"fixed variety: beat {i1 + 1} {name} -> {pose}")
                    changed = True
        for i in range(2, len(beats)):
            k = [(beats[j].get("camera") or {}).get("kind") for j in (i - 2, i - 1, i)]
            if k[0] and k[0] == k[1] == k[2] and "camera" not in beats[i - 1].get("locked", ()):
                cam = beats[i - 1]["camera"]
                if k[1] == "wide":
                    cam.update(zoom=1.08, kind="medium")
                else:
                    cam.update(zoom=1.0, x=0.5, kind="wide")
                notes.append(f"fixed camera: beat {i} reframed")
                changed = True
        for b in beats:
            for a in (b.get("acts") or {}).values():
                if "to" in a and b is not beats[-1] and not 0.12 <= a["to"] <= 0.88:
                    a["to"] = min(0.88, max(0.12, a["to"]))
                    notes.append("fixed onscreen: walk target pulled inside the frame")
                    changed = True
        if not changed:
            break
    left = check(spec)
    return spec, notes, left
