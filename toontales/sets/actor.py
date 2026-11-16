"""Realistic actor for diorama shots (Channel 3): the MPFB builder rig posed by aiming limbs, run inside Blender.

Poses are written as limb directions in the actor's own space (he faces -y, his left is +x, up is +z), so they do
not depend on how the rig's bones are rolled. Each frame the whole bone chain is solved in Python
(M_child = M_parent @ R_parent^-1 @ R_child @ basis) and matrix_basis is set: no depsgraph updates between bones.
Acts and their tools: diorama/actor_acts.py.
"""
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

from diorama.actor_acts import ACTS
from sets import diorama as D

CAST = Path(__file__).resolve().parents[2] / "assets" / "diorama" / "cast"
BLEND_T = 0.3  # seconds to blend from one act into the next


def _v(x, y, z):
    return Vector((x, y, z)).normalized()


def _lean(a_deg):  # up, tipped forward (toward -y) by a degrees
    a = math.radians(a_deg)
    return _v(0, -math.sin(a), math.cos(a))


def _swing(a, side=0.0, up=False):  # a limb hanging down, swung forward by a radians (positive = forward)
    return _v(side, -math.sin(a), -math.cos(a))


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- poses: t (seconds into the act) -> dict
def _base(t):
    b = 0.012 * math.sin(2 * math.pi * t / 3.2)
    return {"lean": 2 + 1.5 * b * 60, "head": (0.0, -2.0),
            "upperarm_l": _v(0.16, 0.02, -1), "lowerarm_l": _v(0.08, -0.18, -1),
            "upperarm_r": _v(-0.16, 0.02, -1), "lowerarm_r": _v(-0.08, -0.18, -1),
            "thigh_l": _v(0.04, 0, -1), "calf_l": _v(0.02, 0.03, -1),
            "thigh_r": _v(-0.04, 0, -1), "calf_r": _v(-0.02, 0.03, -1), "z": 0.0}


def _legs_walk(p, t, rate=1.05, amp=0.42):
    ph = 2 * math.pi * t / rate
    for side, sx, off in (("l", 0.04, 0.0), ("r", -0.04, math.pi)):
        s = amp * math.sin(ph + off)
        bend = 0.75 * max(0.0, math.sin(ph + off - math.pi / 2))  # knee folds as the leg comes through
        p[f"thigh_{side}"] = _swing(s, sx)
        p[f"calf_{side}"] = _swing(s - bend, sx * 0.5)
    p["z"] = 0.025 * abs(math.sin(ph))
    return ph


def idle(t, prm):
    return _base(t)


def walk(t, prm):
    p = _base(t)
    ph = _legs_walk(p, t)
    for side, sx, off in (("l", 0.16, math.pi), ("r", -0.16, 0.0)):
        a = 0.32 * math.sin(ph + off)
        p[f"upperarm_{side}"] = _swing(a, sx)
        p[f"lowerarm_{side}"] = _swing(a + 0.3, sx * 0.5)
    p["lean"] = 4
    return p


def carry(t, prm):
    p = _base(t)
    if prm.get("to"):
        _legs_walk(p, t)
    for side, sx in (("l", 0.22), ("r", -0.22)):
        p[f"upperarm_{side}"] = _v(sx, -0.35, -0.9)
        p[f"lowerarm_{side}"] = _v(-sx * 0.6, -1.0, 0.05)
    p["lean"] = -3
    return p


def dig(t, prm):
    """Two hands on one handle: right hand high at the hip, left hand low and forward; the shovel runs along the
    line through both palms (step() lays it there), so the blade meets the ground in front of his feet."""
    p = _base(t)
    u = (t % 1.5) / 1.5
    push = _smooth(u / 0.35) if u < 0.35 else (1.0 - _smooth((u - 0.55) / 0.45) if u > 0.55 else 1.0)
    lift = max(0.0, math.sin((u - 0.55) / 0.45 * math.pi)) if u > 0.55 else 0.0   # swing the soil up and aside
    p["lean"] = 30 + 12 * push - 8 * lift
    p["upperarm_r"] = _v(-0.2, 0.05, -1)
    p["lowerarm_r"] = _v(0.35, -0.65, 0.05 + 0.4 * lift)                    # top hand at the belly
    p["upperarm_l"] = _v(0.12, -0.55, -0.85 + 0.2 * lift)
    p["lowerarm_l"] = _v(-0.12, -0.4 - 0.2 * lift, -0.95 + 0.55 * lift)      # low hand near the knee
    p["thigh_l"], p["calf_l"] = _v(0.1, -0.35, -1), _v(0.05, 0.2, -1)      # front foot forward, knees soft
    p["thigh_r"], p["calf_r"] = _v(-0.1, 0.18, -1), _v(-0.05, 0.3, -1)
    p["head"] = (0.0, -28 - 8 * push)
    p["z"] = -0.05 - 0.05 * push
    return p


def hammer(t, prm):
    p = _base(t)
    u = (t % 0.55) / 0.55
    k = math.sin(u * math.pi) if u < 0.6 else max(0.0, 1 - (u - 0.6) / 0.15)  # raise slowly, strike fast
    p["upperarm_r"] = _v(-0.2, -0.75, -0.35 + 0.75 * k)
    p["lowerarm_r"] = _v(-0.05, -0.55 + 0.35 * k, 0.65 * k - 0.1)
    p["upperarm_l"] = _v(0.2, -0.85, -0.45)
    p["lowerarm_l"] = _v(-0.15, -0.95, 0.15)
    p["lean"] = 8
    p["head"] = (0.0, -8)
    return p


def drill(t, prm):
    p = hammer(0.0, prm)
    j = 0.015 * math.sin(t * 60)
    p["upperarm_r"] = _v(-0.25, -0.85, -0.3 + j)
    p["lowerarm_r"] = _v(0.05, -1.0, 0.1 + j)
    return p


def climb(t, prm):
    p = _base(t)
    ph = 2 * math.pi * t / 1.2
    for side, sx, off in (("l", 0.25, 0.0), ("r", -0.25, math.pi)):
        k = 0.5 + 0.5 * math.sin(ph + off)
        p[f"upperarm_{side}"] = _v(sx, -0.35, 0.2 + 0.75 * k)
        p[f"lowerarm_{side}"] = _v(sx * 0.4, -0.25, 0.6 + 0.4 * k)
        p[f"thigh_{side}"] = _v(sx * 0.3, -0.75 * k, -1 + 0.7 * k)
        p[f"calf_{side}"] = _v(sx * 0.2, 0.15, -1)
    p["lean"] = 0
    p["head"] = (0.0, 15)
    return p


def crouch(t, prm):
    p = _base(t)
    for side, sx in (("l", 0.18), ("r", -0.18)):
        p[f"thigh_{side}"] = _v(sx, -0.95, -0.35)
        p[f"calf_{side}"] = _v(sx * 0.4, 0.35, -1)
    p["upperarm_l"], p["lowerarm_l"] = _v(0.15, -0.55, -0.8), _v(0.0, -0.9, -0.3)
    p["upperarm_r"], p["lowerarm_r"] = _v(-0.15, -0.55, -0.8), _v(0.0, -0.9, -0.3)
    p["lean"] = 28
    p["head"] = (0.0, -20)
    p["z"] = -0.5
    return p


def point(t, prm):
    p = _base(t)
    d = _v(*prm.get("dir", [-0.6, -0.75, 0.2]))
    p["upperarm_r"] = p["lowerarm_r"] = d
    yaw = math.degrees(math.atan2(-d.x, -d.y))
    p["head"] = (max(-50, min(50, yaw * 0.6)), math.degrees(math.asin(max(-1, min(1, d.z)))) * 0.5)
    return p


def look(t, prm):
    p = _base(t)
    p["head"] = (prm.get("yaw", 35), prm.get("pitch", 0))
    return p


def look_down(t, prm):
    p = _base(t)
    p["lean"] = 14
    p["head"] = (0.0, -40)
    return p


def explain(t, prm):
    p = _base(t)
    w = math.sin(2 * math.pi * t / 0.9)
    p["upperarm_l"], p["lowerarm_l"] = _v(0.2, -0.3, -0.9), _v(0.25, -0.9, 0.15 + 0.15 * w)
    p["upperarm_r"], p["lowerarm_r"] = _v(-0.2, -0.3, -0.9), _v(-0.25, -0.9, 0.15 - 0.15 * w)
    p["head"] = (6 * w, 0)
    return p


def nod(t, prm):
    p = _base(t)
    p["head"] = (0.0, -12 * math.sin(min(1.0, t / 0.6) * math.pi * 2) ** 2)
    return p


def cheer(t, prm):
    p = _base(t)
    w = 0.08 * math.sin(2 * math.pi * t / 0.5)
    p["upperarm_l"], p["lowerarm_l"] = _v(0.45, -0.1, 0.9), _v(0.25 + w, -0.1, 1)
    p["upperarm_r"], p["lowerarm_r"] = _v(-0.45, -0.1, 0.9), _v(-0.25 - w, -0.1, 1)
    p["head"] = (0.0, 12)
    p["z"] = 0.06 * abs(math.sin(2 * math.pi * t / 0.5))
    return p


def shock(t, prm):
    p = _base(t)
    p["upperarm_l"], p["lowerarm_l"] = _v(0.5, -0.4, -0.3), _v(0.1, -0.6, 0.8)
    p["upperarm_r"], p["lowerarm_r"] = _v(-0.5, -0.4, -0.3), _v(-0.1, -0.6, 0.8)
    p["lean"] = -8
    p["head"] = (0.0, 6)
    return p


def wipe(t, prm):
    p = _base(t)
    s = math.sin(2 * math.pi * t / 0.8)
    p["upperarm_r"] = _v(-0.35, -0.75, 0.25)
    p["lowerarm_r"] = _v(0.75 + 0.2 * s, -0.35, 0.45)
    p["head"] = (0.0, 5)
    return p


POSES = {"idle": idle, "walk": walk, "carry": carry, "dig": dig, "hammer": hammer, "drill": drill, "climb": climb,
         "crouch": crouch, "point": point, "look": look, "look_down": look_down, "explain": explain, "nod": nod,
         "cheer": cheer, "shock": shock, "wipe": wipe}
assert set(POSES) == set(ACTS), "actor_acts.ACTS and actor.POSES must list the same acts"


def _mix(a, b, k):
    out = {}
    for key in b:
        va, vb = a.get(key, b[key]), b[key]
        if isinstance(vb, Vector):
            out[key] = (va.lerp(vb, k)).normalized() if (va.lerp(vb, k)).length > 1e-6 else vb
        elif isinstance(vb, tuple):
            out[key] = tuple(x + (y - x) * k for x, y in zip(va, vb))
        else:
            out[key] = va + (vb - va) * k
    return out


# ---------------------------------------------------------------- tools
def _tool(kind):
    root = D._root(f"tool_{kind}")
    wood, metal = D.pbr("planks"), D.flat([0.55, 0.56, 0.6], 0.35, 0.9)
    if kind == "shovel":  # along +x from the top of the handle; step() lays it through both palms
        D.box((1.2, 0.034, 0.034), (0.6, 0.0, 0.0), wood, root, "handle")
        D.box((0.07, 0.14, 0.04), (0.07, 0.0, 0.0), wood, root, "grip")
        D.box((0.3, 0.26, 0.012), (1.32, 0.0, 0.0), metal, root, "blade")
    elif kind == "hammer":
        D.box((0.03, 0.32, 0.03), (0.0, 0.12, 0.0), wood, root, "handle")
        D.box((0.13, 0.04, 0.04), (0.0, 0.28, 0.0), D.flat([0.2, 0.2, 0.22], 0.4, 0.9), root, "head")
    elif kind == "drill":
        D.box((0.06, 0.22, 0.09), (0.0, 0.08, 0.06), D.flat([0.95, 0.65, 0.08], 0.5), root, "body")
        D.box((0.012, 0.12, 0.012), (0.0, 0.24, 0.07), metal, root, "bit")
    elif kind == "crate":
        D.box((0.5, 0.36, 0.34), (0.0, 0.0, 0.0), wood, root, "crate")
    return root


# ---------------------------------------------------------------- build / step
def build(cfg, at, idn):
    """Append the actor collection from its .blend, place it at 'at' facing the camera. Returns the actor dict."""
    path = CAST / f"{cfg.get('actor', 'builder')}.blend"
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c == cfg.get("actor", "builder")]
    col = dst.collections[0]
    bpy.context.scene.collection.children.link(col)
    rig = next(o for o in col.objects if o.type == "ARMATURE")
    root = D._root(f"actor_{idn}")
    root.location = (at[0], at[1], at[2] if len(at) > 2 else 0.0)
    rig.parent = root
    hat = next((o for o in col.objects if "hardhat" in o.name), None)
    if hat is not None:
        hat.hide_render = not cfg.get("hat", True)
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
    bones = [b for b in rig.data.bones]
    order = sorted(bones, key=lambda b: len(b.parent_recursive))
    tools = {k: _tool(k) for k in sorted({v[1] for v in ACTS.values() if v[1]})}
    for t in tools.values():
        D._show(t, False)
    return {"id": idn, "rig": rig, "root": root, "home": Vector(root.location), "order": order, "tools": tools,
            "rest": {b.name: b.matrix_local.copy() for b in bones}, "cfg": cfg}


def _solve(A, pose):
    """Pose the rig from limb directions; returns the armature-space matrices by bone."""
    rig, rest = A["rig"], A["rest"]
    M = {}
    lean = pose.get("lean", 0.0)
    yaw, pitch = pose.get("head", (0.0, 0.0))
    aims = {k: v for k, v in pose.items() if isinstance(v, Vector)}
    for n, k in (("spine_01", 0.3), ("spine_02", 0.35), ("spine_03", 0.35)):
        aims[n] = _lean(lean * k * 3)
    hy, hp = math.radians(yaw), math.radians(pitch - lean * 0.4)  # a leaning body carries the head forward
    head_dir = Vector((0.0, math.sin(hp), math.cos(hp)))  # pitch + = chin up: the head bone tips back (+y)
    aims["neck_01"] = _lean(lean + pitch * -0.3).lerp(head_dir, 0.5).normalized()
    aims["head"] = head_dir
    for b in A["order"]:
        R = rest[b.name]
        if b.parent is None:
            base = R.copy()
        else:
            P = b.parent.name
            base = M[P] @ rest[P].inverted() @ R
        if b.name in aims:
            d = aims[b.name]
            cur = base.to_3x3() @ Vector((0, 1, 0))
            rot = cur.rotation_difference(d).to_matrix() @ base.to_3x3()
            if b.name == "head" and abs(hy) > 1e-4:  # turn the head about the body's up axis
                rot = Matrix.Rotation(hy, 3, "Z") @ rot
            base = Matrix.Translation(base.translation) @ rot.to_4x4()
        M[b.name] = base
        parent_m = M[b.parent.name] @ rest[b.parent.name].inverted() if b.parent else Matrix.Identity(4)
        rig.pose.bones[b.name].matrix_basis = R.inverted() @ parent_m.inverted() @ base
    return M


def current(A, actions, t):
    """The act playing at t, the one before it, and how far the blend between them is."""
    acts = sorted([a for a in actions if a["t0"] <= t], key=lambda a: a["t0"])
    cur = acts[-1] if acts else {"do": "idle", "t0": 0.0}
    prev = acts[-2] if len(acts) > 1 else {"do": "idle", "t0": 0.0}
    return cur, prev, _smooth((t - cur["t0"]) / BLEND_T) if acts else 1.0


def step(A, actions, t):
    cur, prev, k = current(A, actions, t)
    pc, pp = cur.get("params") or {}, prev.get("params") or {}
    pose = POSES.get(cur["do"], idle)(t - cur["t0"], pc)
    if k < 1.0:
        pose = _mix(POSES.get(prev["do"], idle)(t - prev["t0"], pp), pose, k)
    # where he is: walks/carries with "to" move him, climbs with "up" lift him; he faces where he walks
    pos, face = Vector(A["home"]), math.radians(A["cfg"].get("facing", 0.0))
    for a in sorted(actions, key=lambda a: a["t0"]):
        if a["t0"] > t:
            break
        prm = a.get("params") or {}
        dur = a.get("dur") or ACTS.get(a["do"], (1.0,))[0]
        if prm.get("to") and a["do"] in ("walk", "carry"):
            d = Vector((prm["to"][0], prm["to"][1], 0.0))
            dur = a.get("dur") or max(0.6, d.length / prm.get("speed", 1.3))
            u = min(1.0, (t - a["t0"]) / dur)
            if u < 1.0 and d.length > 1e-3:
                face = math.atan2(d.x, -d.y)
            pos = pos + d * u
            if u >= 1.0 and cur is a:  # arrived: stand
                pose = _mix(pose, idle(t, {}), _smooth((t - a["t0"] - dur) / BLEND_T))
        elif prm.get("up") and a["do"] == "climb":
            pos = pos + Vector((0, 0, prm["up"] * min(1.0, (t - a["t0"]) / dur)))
        if "face" in prm:
            face = math.radians(prm["face"])
    A["root"].location = pos + Vector((0, 0, pose.get("z", 0.0)))
    A["root"].rotation_euler = (0, 0, face)
    M = _solve(A, pose)
    # the rig's world matrix is only refreshed at render time: build this frame's from the root directly
    W = Matrix.Translation(A["root"].location) @ Matrix.Rotation(face, 4, "Z") @ A["rig"].matrix_local
    tool = ACTS.get(cur["do"], (0, None))[1]
    for kind, obj in A["tools"].items():
        on = kind == tool and k > 0.5
        D._show(obj, on)
        if on and "hand_r" in M:
            hand = M["hand_r"]
            if kind == "shovel" and "hand_l" in M:  # handle through both palms, blade at the far end
                pr = (M["hand_r"] @ Matrix.Translation((0, 0.08, 0))).translation
                pl = (M["hand_l"] @ Matrix.Translation((0, 0.08, 0))).translation
                x = (pl - pr).normalized()
                z = (Vector((0, 0, 1)) - x * x.z).normalized() if abs(x.z) < 0.99 else Vector((0, -1, 0))
                y = z.cross(x)
                rot = Matrix((x, y, z)).transposed().to_4x4()
                obj.matrix_world = W @ Matrix.Translation(pr - x * 0.12) @ rot
            elif kind == "crate":  # held between both hands
                mid = (M["hand_r"].translation + M.get("hand_l", hand).translation) / 2
                obj.matrix_world = W @ Matrix.Translation(mid + Vector((0, -0.06, 0.02)))
            else:
                obj.matrix_world = W @ hand @ Matrix.Translation((0, 0.08, 0))
