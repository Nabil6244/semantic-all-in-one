"""Toon Tales compiler (pure Python): one plan shot + its real voice line -> shot.json for shots/shot.py.

It decides the shot length (voice + breath), places cast on set marks, turns plan acts into timed
library actions, finds where props stand (spot, wall, in a hand, on the floor to be picked up) and
frames the camera for 9:16 from the camera type and move, kept inside the set's bounds.
"""
import copy
import math

SENSOR_H = 24.0                     # mm, vertical sensor fit
SENSOR_W = SENSOR_H * 9 / 16        # 9:16 frame
BREATH = 0.06                       # silence after each line before the cut
FPS, SIZE = 30, [1080, 1920]

TYPE = {  # camera type: lens, frame width to fit (m), pitch
    "wide": (22, None, 4), "medium": (28, 1.5, 3), "two_shot": (26, None, 3), "close": (40, 0.85, 2),
    "insert": (38, 0.75, 14), "low": (22, 1.7, -9), "high": (26, None, 26), "pov": (34, 1.2, 4),
    "over_shoulder": (30, 1.4, 4),
}


def head_z(cfg):
    return cfg["legs"] + cfg["body"]["h"] - 0.04 + cfg["head_r"] * 0.92


def _dist_for_width(w, lens):
    return (w / 2) * lens / (SENSOR_W / 2)


def piece_size(q):
    """Rough (width, height) in metres of a world piece, for framing a camera on it."""
    m, k = q.get("m", ""), q.get("s", 1.0)
    if m == "@engine":
        n = int(q.get("cyl", 8))
        per = n // 2 if q.get("layout", "V" if n >= 6 else "I") == "V" else n
        w, h = max(per * 0.11 * q.get("bore", 1.0) + 0.16, 0.8), 0.9
    elif m == "@turbo":
        w = h = 0.34 * q.get("size", 1.0)  # housing + outlet, measured off a render
    elif m == "@supercharger":
        w, h = 0.75, 0.35
    elif m == "@motor":
        w, h = 0.75, 0.5
    elif m == "@clock":
        w = h = q.get("r", 0.6) * 2
    elif m == "@stand":
        w, h = 0.5, q.get("h", 1.0)
    elif m.startswith("@"):
        return None  # floors, strips, boards: not something to frame on
    else:
        w, h = 1.2, 1.2  # a pack model
    return w * k, h * k


def _piece_box(q):
    sz = piece_size(q)
    if sz is None:
        return None
    x, y = q["at"][0], q["at"][1]
    z = q["at"][2] if len(q["at"]) > 2 else 0.0
    return {"x": x, "y": y, "z0": z, "w": sz[0], "h": sz[1], "part": q.get("m", "").startswith("@")}


def _min_dist(bx, lens):
    """Closest the camera may sit: the piece must not fill more than ~90% of the frame (no grey slabs)."""
    return max(_dist_for_width(bx["w"] / 0.9, lens), (bx["h"] / 0.9) * lens / SENSOR_H)


def _fit_people(cam, people, margin=0.86, aim=(1.0, 1.2)):
    """Target and distance so every person (feet to hat, start and end of a walk) is inside a 9:16 frame aimed with
    'cam' (yaw within ~25 deg). The aimed area (+-aim[0] across, +-aim[1] up/down: the pit, the pipe) stays in frame
    and keeps its height; the aim only slides sideways, and only as far as the people need."""
    tx, ty, tz = cam["target"]
    lens = cam["lens"]
    xs = [tx - aim[0], tx + aim[0]] + [x for p in people for x in (p["x"] - 0.4, p["x"] + 0.4, p["x_end"] - 0.4,
                                                                    p["x_end"] + 0.4)]
    x0, x1 = min(xs), max(xs)
    ntx = (x0 + x1) / 2 if (x0 < tx - aim[0] or x1 > tx + aim[0]) else tx
    z0 = min([tz - aim[1], 0.0])
    z1 = max([tz + aim[1]] + [p["top_z"] + 0.12 for p in people])
    need_w = (x1 - x0) / margin
    need_h = 2 * max(z1 - tz, tz - z0) / margin
    dist = max(_dist_for_width(need_w, lens), need_h / 2 * lens / (SENSOR_H / 2))
    return {"target": [ntx, ty, tz], "dist": dist}


def _cam_pos(c):
    y, p = math.radians(c["yaw"]), math.radians(c["pitch"])
    t = c["target"]
    return [t[0] + math.sin(y) * math.cos(p) * c["dist"], t[1] - math.cos(y) * math.cos(p) * c["dist"],
            t[2] + math.sin(p) * c["dist"]]


def clamp(c, b):
    """Keep the camera inside the set: shrink yaw at the walls, swap distance for a wider lens at the back,
    keep it under the roof. Each fix can disturb another, so repeat until all hold."""
    c = dict(c, target=list(c["target"]))
    for _ in range(4):
        c = _clamp_once(c, b)
    return c


def _clamp_once(c, b):
    for _ in range(40):
        x = _cam_pos(c)[0]
        if b["x"][0] <= x <= b["x"][1] or abs(c["yaw"]) < 0.5:
            break
        c["yaw"] *= 0.8
    x = _cam_pos(c)[0]
    if not b["x"][0] <= x <= b["x"][1]:
        c["target"][0] -= x - max(b["x"][0], min(b["x"][1], x))
    y, p = math.radians(c["yaw"]), math.radians(c["pitch"])
    room = (c["target"][1] - b["y"][0]) / max(0.2, math.cos(y) * math.cos(p))
    if c["dist"] > room:
        c["lens"] = max(14.0, c["lens"] * room / c["dist"])
        c["dist"] = room
    for _ in range(40):
        z = _cam_pos(c)[2]
        if b["z"][0] <= z <= b["z"][1]:
            break
        c["pitch"] += -1.5 if z > b["z"][1] else 1.5
    return c


WORLD_CAM = {  # 3D toon world: show the place, not just the face. kind: (dist x, pitch, yaw x, target drop)
    "medium": (1.9, -3, 2.4, 0.35), "two_shot": (1.45, 1, 2.2, 0.1), "wide": (1.55, 2, 1.8, 0.0),
    "close": (1.2, 0, 2.0, 0.0), "low": (1.5, -12, 1.5, 0.2), "pov": (1.4, 2, 1.5, 0.0),
    "over_shoulder": (1.3, 2, 1.2, 0.0), "high": (1.3, 22, 1.5, 0.0), "insert": (1.0, 10, 1.0, 0.0)}


def frame(shot, idx, people, props, bounds, world=False, pieces=None):
    """people: [{id, x, y, head_z, top_z}]; props: [{pos}] -> camera {from, to, ease, drift}."""
    kind = shot.get("camera", "medium")
    lens, width, pitch = TYPE.get(kind, TYPE["medium"])
    side = -1 if idx % 2 else 1
    speaker = next((p for p in people if p["id"] == shot.get("speaker")), None)
    subj = speaker or (people[0] if people else None)
    look = shot.get("look")
    if kind == "medium" and speaker is None and len(people) > 1 and not look:
        # narrated shot with several people acting: centring on one cut the others out of a 9:16 frame
        return frame(dict(shot, camera="two_shot"), idx, people, props, bounds, world, pieces)
    all_boxes = [(q.get("id"), b) for q in (pieces or []) if (b := _piece_box(q))]
    boxes = {i: b for i, b in all_boxes if i}
    guard = None  # the piece the shot looks at: the camera never gets inside its size
    if look and look.get("fit"):  # {"fit": [piece ids]}: aim at their middle, as close as keeps them all in frame
        fit = [boxes[i] for i in look["fit"] if i in boxes]
        if fit:
            lens = look.get("lens", 30)
            x0, x1 = min(b["x"] - b["w"] / 2 for b in fit), max(b["x"] + b["w"] / 2 for b in fit)
            z0, z1 = min(b["z0"] for b in fit), max(b["z0"] + b["h"] for b in fit)
            look = dict(look, at=[(x0 + x1) / 2, sum(b["y"] for b in fit) / len(fit), (z0 + z1) / 2],
                        dist=max(_dist_for_width((x1 - x0) * 1.12, lens), (z1 - z0) * 1.15 * lens / SENSOR_H))
            guard = {"x": look["at"][0], "y": look["at"][1], "z0": z0, "w": (x1 - x0) * 1.05, "h": z1 - z0}
    if look:  # world shot aimed at a spot (a truck, a bridge): {"at": [x,y,z], "to"?, "dist"?, "yaw"?, "pitch"?, "lens"?}
        base = {"target": list(look["at"]), "dist": look.get("dist", 9.0), "yaw": look.get("yaw", 10 * side),
                "pitch": look.get("pitch", 5), "lens": look.get("lens", 30)}
        if guard is None:  # our own parts only: pack model sizes are guesses
            near = [b for _, b in all_boxes if b.get("part") and
                    (b["x"] - look["at"][0]) ** 2 + (b["y"] - look["at"][1]) ** 2 < 0.8 ** 2]
            guard = max(near, key=lambda b: b["w"] * b["h"], default=None)
        if guard:
            base["dist"] = max(base["dist"], _min_dist(guard, base["lens"]))
        if people:  # a shot aimed at a spot still has to show the people acting in it
            fit = _fit_people(base, people)
            base = dict(base, target=fit["target"], dist=max(base["dist"], fit["dist"]))
    elif subj is None:  # nobody on screen: look at the props or the middle of the set
        tgt = props[0]["pos"] if props else [0.0, 1.0, 1.0]
        base = {"target": [tgt[0], tgt[1], max(0.4, tgt[2] + 0.2)], "dist": 1.8, "yaw": 8 * side, "pitch": 6, "lens": 30}
    elif kind in ("wide", "two_shot", "high"):
        group = people if kind != "two_shot" else sorted(people, key=lambda p: abs(p["x"] - subj["x"]))[:2]
        xs = [p["x"] for p in group]
        xs += [p["x_end"] for p in group]  # walkers/runners: frame where they end up too
        for p in group:  # a faller lands a body-length to the side: keep the landing in frame
            if p.get("falls"):
                xs.append(p["x"] + p["falls"] * (p["top_z"] - 0.1))
        span = max(xs) - min(xs) + (1.7 if kind == "wide" else 1.25)
        top = max(p["top_z"] for p in group)
        tx = (max(xs) + min(xs)) / 2
        ty = sum(p["y"] for p in group) / len(group)
        dist = _dist_for_width(span, lens)
        dist = max(dist, (top * 0.62) * lens / (SENSOR_H / 2))  # whole body fits in height
        base = {"target": [tx, ty, top * 0.5 + (0.1 if kind == "high" else 0.0)], "dist": dist,
                "yaw": (9 if kind == "wide" else 5) * side, "pitch": pitch, "lens": lens}
    elif kind == "insert":
        tgt = props[0]["pos"] if props else [subj["x"] + 0.2, subj["y"] - 0.1, subj["head_z"] - 0.55]
        base = {"target": [tgt[0], tgt[1], tgt[2] + 0.08], "dist": _dist_for_width(width, lens),
                "yaw": 10 * side, "pitch": pitch, "lens": lens}
    elif kind == "over_shoulder":
        fg = next((p for p in people if p is not subj), None)
        if fg is None:
            return frame(dict(shot, camera="medium"), idx, people, props, bounds)
        d = 1 if fg["x"] > subj["x"] else -1
        base = {"target": [subj["x"], subj["y"], subj["head_z"] - 0.18], "dist": 2.3 + abs(fg["y"] - subj["y"]),
                "yaw": 24 * d, "pitch": 4, "lens": lens}
    else:  # medium, close, low, pov
        drop = {"medium": 0.42, "close": 0.06, "low": 0.35, "pov": 0.2}[kind]
        base = {"target": [subj["x"], subj["y"], subj["head_z"] - drop], "dist": _dist_for_width(width, lens),
                "yaw": {"pov": 18, "low": 10}.get(kind, 6) * side, "pitch": pitch, "lens": lens}
    if world and not look:
        dm, pitch_w, yaw_m, drop = WORLD_CAM.get(kind, (1.4, 2, 1.5, 0.0))
        base = dict(base, dist=base["dist"] * dm, pitch=pitch_w, yaw=max(-35, min(35, base["yaw"] * yaw_m)),
                    target=[base["target"][0], base["target"][1], max(0.6, base["target"][2] - drop)])
    a, b = dict(base, target=list(base["target"])), dict(base, target=list(base["target"]))
    mv = shot.get("move", "drift")
    ease = "inout"
    if mv == "push":
        b["dist"] *= 0.78
    elif mv == "pull":
        a["dist"] *= 0.78
    elif mv in ("pan_l", "pan_r"):  # the slide scales with the shot: 35 cm on a set, a few cm on a coin
        a["target"][0] += (0.35 if mv == "pan_l" else -0.35) * min(1.0, base["dist"] / 2.5)
    elif mv in ("tilt_up", "tilt_down"):
        a["target"][2] += (-0.35 if mv == "tilt_up" else 0.35) * min(1.0, base["dist"] / 2.5)
    elif mv in ("orbit_l", "orbit_r"):
        s = -1 if mv == "orbit_l" else 1
        a["yaw"], b["yaw"] = base["yaw"] - 9 * s, base["yaw"] + 7 * s
    elif mv == "crash_zoom":
        b["dist"] *= 0.8 if kind == "close" else 0.58
        ease = "out_fast"
    else:  # drift
        b["dist"] *= 0.95
    if look and people:  # ...and a push-in must not crop them out again
        need = _fit_people(base, people)["dist"]
        a["dist"], b["dist"] = max(a["dist"], need), max(b["dist"], need)
    if guard:  # a push / crash zoom still stops short of filling the frame with the piece
        lo = _min_dist(guard, base["lens"]) * 0.85
        a["dist"], b["dist"] = max(a["dist"], lo), max(b["dist"], lo)
    if look and look.get("to"):  # follow: the aim travels with the moving piece
        b["target"] = list(look["to"])
    return {"from": clamp(a, bounds), "to": clamp(b, bounds), "ease": ease, "drift": 0.012}


def prop_spot(p, shot, kit, people):
    """Where a plan prop goes: [x, y, z] plus wall side / holder."""
    out = {k: p[k] for k in ("type", "text") if k in p}
    holder = p.get("held_by") or p.get("picked_by")
    if holder:
        out["held_by" if p.get("held_by") else "picked_by"] = holder
        who = next((q for q in people if q["id"] == holder), None)
        if who:
            out["pos"] = [who["x"] + 0.24, who["y"] - 0.2, 0.0]
            return out
    spot = p.get("spot", "floor_front")
    if spot in kit["spots"]:
        out["pos"] = list(kit["spots"][spot])
        if spot.startswith("wall_") and kit.get("kind") != "backdrop":  # painted stage: signs stand on the floor
            out["wall"] = spot[-1]
    elif spot in kit["props"]:
        out["pos"] = list(kit["props"][spot])
    elif spot in kit["marks"]:
        out["pos"] = list(kit["marks"][spot]) + [0.0]
    else:
        out["pos"] = list(kit["spots"].get("floor_front", [0, -0.5, 0]))
    return out


def compile_shot(shot, idx, line, cast_cfg, kit, art=None):
    """line: voice result {dur, cues, wav} for this shot's sentence. art: fn(type, text) -> png path."""
    shot = copy.deepcopy(shot)
    dur = round(max(1.0, line["dur"] + BREATH), 3)
    people = []
    for c in shot.get("cast", []):
        cfg = cast_cfg[c["id"]]
        x, y = kit["marks"][c["mark"]]
        hz = head_z(cfg)
        fall = next((a for a in c.get("acts", []) if a.get("do") == "fall"), None)
        falls = 0
        if fall:
            side = (fall.get("params") or {}).get("side") or ("left" if x > 0 else "right")  # fall into open floor
            fall["params"] = dict(fall.get("params") or {}, side=side)
            falls = -1 if side == "left" else 1
        dx = sum(((a.get("params") or {}).get("to") or [0, 0])[0] for a in c.get("acts", [])
                 if a.get("do") in ("walk", "run", "sneak_walk"))
        people.append({"id": c["id"], "mark": c["mark"], "x": x, "y": y, "head_z": hz,
                       "top_z": hz + cfg["head_r"] + 0.12, "falls": falls, "x_end": x + dx})
    if any(p["falls"] for p in people) and shot.get("camera") in ("medium", "close", "low", "pov", "over_shoulder"):
        shot = dict(shot, camera="two_shot" if len(people) > 1 else "wide")
    if any(abs(p["x_end"] - p["x"]) > 0.3 for p in people) and shot.get("camera") not in ("wide", "two_shot", "high"):
        shot = dict(shot, camera="wide")  # someone crosses the set: show the whole move
    leaps = {"jump", "celebrate", "cheer"}
    if shot.get("camera") == "close" and any(a.get("do") in leaps for c in shot.get("cast", []) for a in c.get("acts", [])):
        shot = dict(shot, camera="medium")  # a jumping head leaves a close-up
    actions, faces = [], []
    for c in shot.get("cast", []):
        for a in c.get("acts", []):
            act = {"who": c["id"], "do": a["do"], "t0": round(min(float(a.get("at", 0)), max(0.0, dur - 0.3)), 3)}
            if a.get("params"):
                act["params"] = a["params"]
            actions.append(act)
        if c.get("eyes") or c.get("mouth"):
            fo = {"who": c["id"], "t0": 0.0, "t1": 99.0}
            fo.update({k: c[k] for k in ("eyes", "mouth") if c.get(k)})
            faces.append(fo)
    lines = []
    if shot.get("speaker") in [p["id"] for p in people]:
        lines.append({"who": shot["speaker"], "start": 0.0, "dur": line["dur"], "cues": line["cues"]})
    props = []
    for p in shot.get("props", []):
        q = prop_spot(p, shot, kit, people)
        if p.get("text") and art:
            q["image"] = str(art(p["type"], p["text"]))
        props.append(q)
    for q in props:  # a sack/bottle label needs art too
        if q.get("text") and "image" not in q and art:
            q["image"] = str(art("label", q["text"]))
    cam_props = [{"pos": [q["pos"][0], q["pos"][1], q["pos"][2] if not q.get("held_by") else 1.0]} for q in props]
    camera = frame(shot, idx, people, cam_props, kit["bounds"], world=bool(kit.get("world")), pieces=kit.get("pieces"))
    return {"id": shot["id"], "set": "stage" if kit.get("place") else shot["set"], "fps": FPS, "size": SIZE, "dur": dur,
            "cast": [{"id": p["id"], "mark": p["mark"]} for p in people],
            "lines": lines, "actions": actions, "faces": faces, "props": props, "camera": camera}
