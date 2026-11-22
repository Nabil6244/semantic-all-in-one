"""Beat timeline -> one small state per frame (figures in screen px, camera, text).

Rules checked before anything is drawn:
  * beats run back to back from 0 s, each at most MAX_HOLD seconds;
  * every beat changes something (an action, a caption or a title).
Walk and run use a foot lock: the planted foot never slides, so the body moves exactly
as far as the steps carry it. Every figure's lowest foot sits on the ground line
(the jump adds lift on top).
"""
import math

from . import looks, poses, rig

MAX_HOLD = 3.0
BLEND = 0.28            # seconds to move into a new action
CAM_EASE = 0.8          # seconds for the camera to reach a beat's framing
CAM_DRIFT = 0.012       # slow push-in per second inside a beat
MOVING = ("walk", "run", "sneak")
DEFAULT_CAM = {"zoom": 1.0, "x": 0.5, "y": 0.56}


class TimelineError(ValueError):
    pass


def ease_back(x):
    """0..1 with a small overshoot, for snappy cartoon pose changes."""
    x = min(max(x, 0.0), 1.0)
    c = 1.4
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def validate(spec):
    """Raise TimelineError for a broken plan; return the total length in seconds."""
    beats = spec.get("beats") or []
    if not beats:
        raise TimelineError("the plan has no beats")
    figs = spec.get("figures") or {}
    t = 0.0
    for i, b in enumerate(beats, 1):
        if abs(float(b.get("t", -1)) - t) > 1e-6:
            raise TimelineError(f"beat {i} starts at {b.get('t')} s, expected {t:g} s")
        d = float(b.get("dur", 0))
        if d <= 0:
            raise TimelineError(f"beat {i} has no length")
        if d > MAX_HOLD + 1e-9:
            raise TimelineError(f"beat {i} holds {d:g} s; the most one picture may hold is {MAX_HOLD:g} s")
        if not (b.get("acts") or b.get("caption") or b.get("title")):
            raise TimelineError(f"beat {i} changes nothing on screen")
        for name, act in (b.get("acts") or {}).items():
            if name not in figs:
                raise TimelineError(f"beat {i} uses unknown figure '{name}'")
            if act.get("do") not in poses.ALL:
                raise TimelineError(f"beat {i}: unknown action '{act.get('do')}' for {name}")
            if act.get("then") and act["then"] not in poses.STATIC:
                raise TimelineError(f"beat {i}: '{act['then']}' can't follow an action (needs a still pose)")
        t += d
    if abs(float(spec.get("duration", t)) - t) > 1e-6:
        raise TimelineError(f"beats add up to {t:g} s but duration says {spec['duration']} s")
    return t


def _start(fs, act, t):
    fs["from"] = dict(fs["last"])
    fs["act"] = dict(act)
    fs["t0"] = t
    if "face" in act:
        fs["facing"] = 1 if act["face"] >= 0 else -1
    if act["do"] in MOVING and "to" in act:
        fs["facing"] = 1 if act["to"] * fs["W"] >= fs["x"] else -1
    fs["planted"] = None
    fs["rel"] = None


def _step(fs, t, ground):
    act = fs["act"]
    do = act["do"]
    lt = t - fs["t0"]
    lift = 0.0
    if do in MOVING:
        base = poses.cycle(do, lt / poses.CYCLES[do])
    elif do == "jump":
        u = lt / poses.JUMP_DUR
        if u >= 1.0:
            _start(fs, {"do": act.get("then", "stand")}, t)
            return _step(fs, t, ground)
        base, lift = poses.jump(u)
    else:
        base = poses.idle(poses.STATIC[do], t, fs["seed"], do)
    pose = rig.blend(fs["from"], base, ease_back(lt / BLEND)) if lt < BLEND else base
    fs["last"] = pose
    j = rig.fk(pose, fs["facing"])
    h = fs["hpx"]

    if do in MOVING:
        planted = "foot_b" if j["foot_b"][1] > j["foot_f"][1] else "foot_f"
        relx = j[planted][0] * h
        if fs["planted"] == planted and fs["rel"] is not None:
            fs["x"] += fs["rel"] - relx
        fs["planted"], fs["rel"] = planted, relx
        if "to" in act and (fs["x"] - act["to"] * fs["W"]) * fs["facing"] >= 0:
            _start(fs, {"do": act.get("then", "stand")}, t)

    low = rig.lowest(j) * h
    root_y = ground - low - lift * h
    joints = {k: (fs["x"] + v[0] * h, root_y + v[1] * h) for k, v in j.items()}
    carried = []
    if do in poses.POSE_PROPS and fs["act"]["do"] == do:
        for name, where, size in poses.POSE_PROPS[do]:
            x, y = anchor(joints, h, fs["facing"], ground, where, size * h)
            carried.append({"name": name, "x": x, "y": y, "size": size * h, "age": t - fs["t0"]})
    return {
        "props": carried,
        "name": fs["name"], "joints": joints, "hpx": h, "facing": fs["facing"],
        "tilt": pose["lean"] + pose["head"] + pose.get("rot", 0.0), "mouth": pose["mouth"], "eyes": pose["eyes"],
        "lift": lift, "seed": fs["seed"], "do": do,
    }


def anchor(j, h, fc, ground, where, size):
    """Where a prop goes on or next to a figure (screen px)."""
    if where in ("hand_f", "hand_b"):
        return j[where]
    if where in ("hands", "front_low", "hands_up"):
        x = (j["hand_f"][0] + j["hand_b"][0]) / 2
        y = (j["hand_f"][1] + j["hand_b"][1]) / 2
        return (x, y + {"front_low": 0.07, "hands_up": -0.09}.get(where, 0.0) * h)
    if where == "above":
        return (j["head"][0] + fc * 0.05 * h, j["head"][1] - rig.HEAD_R * h - size * 0.62)
    if where == "face":
        return (j["head"][0] + fc * 0.5 * rig.HEAD_R * h, j["head"][1] + 0.25 * rig.HEAD_R * h)
    if where == "ground":
        return (j["pelvis"][0] + fc * (0.3 * h + size / 2), ground - size * 0.48)
    # side: beside the figure at chest height, on the side it faces
    return (j["pelvis"][0] + fc * (0.32 * h + size * 0.55), ground - 0.62 * h)


def _beat_props(beat, lt, outs, W, H, ground):
    res = []
    by = {o["name"]: o for o in outs}
    for p in beat.get("props") or []:
        if "x" in p:
            size = float(p.get("size", 0.16)) * H
            res.append({"name": p["name"], "x": p["x"] * W, "y": p["y"] * H, "size": size, "age": lt})
            continue
        o = by.get(p.get("fig")) or outs[0]
        size = float(p.get("size", 0.45)) * o["hpx"]
        x, y = anchor(o["joints"], o["hpx"], o["facing"], ground, p.get("at", "side"), size)
        res.append({"name": p["name"], "x": x, "y": y, "size": size, "age": lt})
    return res


def _cam(c0, c1, k, drift):
    c = {n: c0[n] + (c1[n] - c0[n]) * k for n in DEFAULT_CAM}
    c["zoom"] *= 1 + CAM_DRIFT * drift
    return c


def simulate(spec):
    """Every frame's state, in order. Pure maths, so frames can then be drawn in parallel."""
    total = validate(spec)
    W, H = spec["size"]
    fps = int(spec.get("fps", 30))
    look = looks.get(spec.get("look", "ink_paper"))
    ground = H * float(spec.get("ground", look["ground"]))
    figs = {}
    for i, (name, f) in enumerate(spec["figures"].items()):
        figs[name] = {
            "name": name, "W": W, "x": float(f["x"]) * W, "facing": 1 if f.get("facing", 1) >= 0 else -1,
            "hpx": float(f.get("height", 0.4)) * H, "act": {"do": "stand"}, "t0": -10.0,
            "from": dict(rig.NEUTRAL), "last": dict(rig.NEUTRAL), "seed": 1.0 + i * 7.3,
            "planted": None, "rel": None,
        }
    starts = {int(round(float(b["t"]) * fps)): b for b in spec["beats"]}
    frames = []
    card = spec.get("title") if isinstance(spec.get("title"), dict) else None
    place = spec.get("place", "void")
    beat, beat_t = None, 0.0
    cam_from = cam_to = cam_now = dict(DEFAULT_CAM)
    for fi in range(int(round(total * fps))):
        t = fi / fps
        if fi in starts:
            beat, beat_t = starts[fi], t
            cam_from = dict(cam_now)
            cam_from["zoom"] = cam_now["zoom"]
            cam_to = dict(DEFAULT_CAM, **(beat.get("camera") or {}))
            for name, act in (beat.get("acts") or {}).items():
                _start(figs[name], act, t)
        lt = t - beat_t
        k = poses.smooth(lt / CAM_EASE)
        cam_now = _cam(cam_from, cam_to, k, lt)
        title, tl, td = beat.get("title") or "", lt, float(beat["dur"])
        if card and t < card["t1"]:
            title, tl, td = card["text"], t, card["t1"]
        else:
            for cd in spec.get("cards") or ():
                if cd["t0"] <= t < cd["t1"]:
                    title, tl, td = cd["text"], t - cd["t0"], cd["t1"] - cd["t0"]
                    break
        if beat.get("place"):
            place = beat["place"]
        outs = [_step(fs, t, ground) for fs in figs.values()]
        held = [p for o in outs for p in o.pop("props")]
        frames.append({
            "i": fi, "t": t, "lt": lt, "beat_dur": float(beat["dur"]),
            "figs": outs, "place": place, "props": held + _beat_props(beat, lt, outs, W, H, ground),
            "cam": cam_now, "ground": ground,
            "caption": beat.get("caption") or "", "words": beat.get("words") or [],
            "title": title, "title_lt": tl, "title_dur": td,
        })
    return frames
