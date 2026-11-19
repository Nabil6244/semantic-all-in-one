"""Truck Convoy, the 3rd Toy Vehicles style: big colour trucks pull flatbed trailers loaded with toy cars over
speed bumps, potholes and a train crossing; the cars bounce, one flies off, a crane truck lifts it back on.

Every motion is worked out here (keyframed per frame), not simulated, so each render is the same and the shot
cache holds. Trucks drive toward +x. A cast entry {"kind": "semi", "colour": "red", "load": ["car:blue", ...]}
builds one truck; the story actions are convoy_line, convoy_drive and convoy_lift (story_actions.ACTIONS).
"""
import math
import random

import bpy
from mathutils import Euler, Matrix, Vector

from toycolors import kit, toy
from toycolors import timeline as T
from toycolors.templates import F, confetti, k_loc, k_rot, k_scale, look

COL = dict(T.COLOURS)
COL.setdefault("purple", (0.30, 0.03, 0.75))
COL.setdefault("pink", (0.95, 0.12, 0.45))
KING = Vector((-1.75, 0.0, 1.0))         # the trailer hitch on the truck, in truck space
DECK_Z = 1.16                            # top of the trailer deck, in trailer space
TRAILER_L = 7.2
CARGO_X = (-1.35, -3.65, -5.95)          # where up to three cars sit on the deck (trailer space)
CARGO_S = 0.74                           # cars ride a bit smaller than on the ground, so three fit
AXLES = {"front": 0.6, "drive": (-1.45, -2.1)}          # truck axles (truck space x)
TRAILER_AXLES = (-5.45, -6.35)                           # trailer axles (trailer space x)
LANE = 3.0                                               # side-by-side lanes, like the reference line-ups
ROAD_W = 14.0


# ================================================================ set
def build_set(name):
    """Green grass, a wide grey road with yellow lines, trees and hills: the bright outdoor look of the reference."""
    road_keep = [(-60, 60, -ROAD_W / 2 - 0.6, ROAD_W / 2 + 0.6)]
    ground, sun = kit.park_world(grass_radius=30.0, density=12.0, trees=40, seed=8, keep_out=road_keep)
    # warm and vivid like the rest of Toy Vehicles (measured: the plain park set came out sat 0.41, R-B -0.06 graded):
    # golden sun, less cool sky fill, a warm key from the camera side, a warm-grey road instead of a blue-grey one
    sun.data.color = (1.0, 0.82, 0.58)
    bpy.context.scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    bpy.ops.object.light_add(type="AREA", location=(14, -16, 9))
    key = bpy.context.object
    key.data.energy, key.data.size, key.data.color = 4000, 14, (1.0, 0.80, 0.55)
    key.data.use_shadow = False
    c = key.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = kit.empty("key_aim", (0, 0, 1.2)), "TRACK_NEGATIVE_Z", "UP_Y"
    for m in bpy.data.materials:                     # the grass: richer, warmer green
        if m.name.startswith(("ground", "blade")) and m.node_tree:
            for n in m.node_tree.nodes:
                if n.type == "VALTORGB":
                    for e in n.color_ramp.elements:
                        r, g, b, a = e.color
                        e.color = (min(1, r * 1.2 + 0.01), min(1, g * 1.05), b * 0.6, a)
    asphalt = kit.ramp_mat("asphalt", (0.21, 0.225, 0.25), (0.28, 0.295, 0.32), scale=4.0, rough=0.85)  # cool grey: the warm grade turns it neutral, not tan
    kit.box("road", (0, 0, 0.012), (120, ROAD_W, 0.02), asphalt, 0.0)
    white = kit.mat("road_edge", (0.95, 0.95, 0.95), rough=0.5)
    yellow = kit.mat("road_line", (1.0, 0.72, 0.02), rough=0.5)
    for sy in (-1, 1):
        kit.box("edge", (0, sy * (ROAD_W / 2 - 0.25), 0.024), (120, 0.16, 0.004), white, 0.0)
        kit.box("centre", (0, sy * 0.12, 0.024), (120, 0.12, 0.004), yellow, 0.0)
    kerb = toy.plastic("kerb", (0.80, 0.80, 0.78), rough=0.6)
    for sy in (-1, 1):
        kit.box("kerb", (0, sy * (ROAD_W / 2 + 0.2), 0.08), (120, 0.4, 0.16), kerb, 0.03)


def speed_bump(x, width=ROAD_W - 0.6):
    """Yellow-and-black striped hump across the whole road."""
    yel = toy.plastic("bump_yellow", (1.0, 0.78, 0.02), rough=0.4)
    blk = toy.plastic("bump_black", (0.03, 0.03, 0.035), rough=0.5)
    n = int(width / 0.8)
    for i in range(n):
        y = -width / 2 + (i + 0.5) * width / n
        kit.sphere("bump", (x, y, 0.0), 1, yel if i % 2 == 0 else blk, scale=(0.55, width / n / 2 + 0.01, 0.24), segs=24)


def pothole(x, y, r=0.9):
    """A dark broken hole in the asphalt with chunks round the rim."""
    hole = kit.mat("pothole", (0.03, 0.025, 0.02), rough=0.9)
    rim = kit.ramp_mat("pothole_rim", (0.18, 0.17, 0.16), (0.30, 0.29, 0.28), scale=3.0, rough=0.9)
    kit.sphere("pothole", (x, y, 0.025), 1, hole, scale=(r * 1.2, r, 0.01), segs=24)
    rng = random.Random(int(x * 10 + y))
    for k in range(10):
        a = k / 10 * 2 * math.pi + rng.uniform(-0.2, 0.2)
        kit.box("chunk", (x + math.cos(a) * r * 1.25, y + math.sin(a) * r * 1.05, 0.05),
                (rng.uniform(0.15, 0.3), rng.uniform(0.12, 0.25), 0.07), rim, 0.02,
                rot=(0, 0, rng.uniform(0, math.pi)))


def crossing(x):
    """Rails across the road and two striped barrier arms that drop for the train."""
    steel = kit.chrome()
    wood = toy.plastic("sleeper", (0.35, 0.18, 0.07), rough=0.7)
    for k in range(-30, 31):
        kit.box("sleeper", (x, k * 0.9, 0.04), (2.4, 0.3, 0.06), wood, 0.01)
    for sx in (-0.72, 0.72):
        kit.box("rail", (x + sx, 0, 0.11), (0.1, 56, 0.1), steel, 0.01)
    red = toy.plastic("barrier_red", (0.9, 0.04, 0.03), rough=0.35)
    wht = toy.plastic("barrier_white", (0.95, 0.95, 0.95), rough=0.35)
    arms = []
    for sy in (-1, 1):
        post = (x - 2.0, sy * (ROAD_W / 2 + 0.6), 0)
        kit.cyl("barrier_post", (post[0], post[1], 0.6), 0.1, 1.2, wht, verts=16)
        piv = kit.empty("barrier", (post[0], post[1], 1.1))
        for k in range(6):
            kit.box("arm", (0, -sy * (0.6 + k * 0.55), 0), (0.12, 0.55, 0.12), red if k % 2 == 0 else wht, 0.02,
                    parent=piv)
        arms.append((piv, sy))
    return arms


def train(y0, x, n_cars=3):
    """A smiling toy engine and its wagons, travelling along +y on the crossing rails."""
    root = kit.empty("train", (x, y0, 0.15))
    v = kit.Vehicle("train", root)
    body = toy.plastic("train_body", COL["blue"])
    v.body_mats.append(body)
    red = toy.plastic("train_red", COL["red"])
    blk = toy.plastic("train_black", (0.04, 0.04, 0.05), rough=0.4)
    yel = toy.plastic("train_yellow", COL["yellow"])
    # the engine faces +y: its face is on the y+ end
    toy.sbox("engine_body", (0, 0, 1.1), (1.7, 3.2, 1.3), body, 0.3, root)
    toy.sbox("engine_cab", (0, -0.9, 2.0), (1.7, 1.4, 1.0), red, 0.25, root)
    kit.cyl("chimney", (0, 0.9, 2.15), 0.22, 0.8, blk, verts=24, parent=root)
    face = kit.empty("face", (0, 0, 0), root)
    face.rotation_euler = (0, 0, math.radians(90))      # eyes and mouth are built facing +x: turn them to +y
    toy.eyes(v, 1.62, 0, 1.35, 0.26, 0.3, body, parent=face)
    toy.mouth(v, 1.61, 0, 0.82, 0.56, 0.22, blk, parent=face)
    v.wheels = []
    axle = kit.empty("train_axles", (0, 0, 0), root)
    axle.rotation_euler = (0, 0, math.radians(90))      # wheels roll about their local y: turn them to roll along +y

    def wheel(x, y, r, m):                              # (x, y) in train space -> axle space is (y, -x)
        v.wheels.append(toy.toy_wheel("train_wheel", (y, -x, r), r, 0.2, m, axle))
    for k in range(3):
        for sx in (-1, 1):
            wheel(sx * 0.8, 0.9 - k * 0.9, 0.38, red)
    for c in range(n_cars):
        y = -3.6 - c * 3.4
        m = toy.plastic(f"wagon{c}", COL[("yellow", "green", "orange", "purple")[c % 4]])
        toy.sbox("wagon", (0, y, 1.0), (1.6, 3.0, 1.1), m, 0.2, root)
        for k in (-1, 1):
            for sx in (-1, 1):
                wheel(sx * 0.8, y + k * 0.95, 0.34, yel)
    return v


# ================================================================ copies: build each kind once, copy it in new colours
_PROTO = {}         # kind -> (Vehicle, {material name: role})


def _copy_tree(ob, parent, mats, mp):
    n = ob.copy()                                         # shares the mesh: no rebuilding, no bpy.ops
    bpy.context.scene.collection.objects.link(n)
    n.parent = parent
    mp[ob] = n
    for slot in n.material_slots:
        m = slot.material
        if m is not None and m.name in mats:
            slot.link = "OBJECT"                      # the object slot starts empty: set it from the mesh's material
            slot.material = mats[m.name]
    for ch in ob.children:
        _copy_tree(ch, n, mats, mp)
    return n


def _recolour(proto, rgb, roles):
    """New materials for the colour roles of a prototype: body, trim (dark body) and deck (light body)."""
    out = {}
    for mname, role in roles.items():
        src = bpy.data.materials[mname]
        if role == "body":
            out[mname] = toy.plastic(mname + "_c", rgb)
        elif role == "trim":
            out[mname] = toy.plastic(mname + "_c", tuple(c * 0.35 for c in rgb), rough=0.4)
        elif role == "deck":
            out[mname] = toy.plastic(mname + "_c", tuple(0.55 + 0.45 * c for c in rgb), rough=0.4)
        else:
            out[mname] = src
    return out


def _copy_vehicle(proto, roles, rgb, loc, yaw, name):
    mats = _recolour(proto, rgb, roles)
    mp = {}
    root = _copy_tree(proto.root, None, mats, mp)
    root.name = name
    root.location, root.rotation_euler = loc, (0, 0, yaw)
    v = kit.Vehicle(proto.kind, root)
    v.looks = [mp[o] for o in getattr(proto, "looks", [])]
    v.lids = [mp[o] for o in getattr(proto, "lids", [])]
    v.parts = {k: mp.get(o, o) for k, o in proto.parts.items()}
    v.body_mats = [mats.get(m.name, m) for m in proto.body_mats]
    for k in ("eye_z", "eye_r"):
        if hasattr(proto, k):
            setattr(v, k, getattr(proto, k))
    if getattr(proto, "trailer", None) is not None:
        tr = _copy_tree(proto.trailer, None, mats, mp)
        tr.name = name + "_trailer"
        tr.location = root.matrix_basis @ KING
        v.trailer = tr
    v.wheels = [mp[w] for w in proto.wheels]
    return v


def toy_copy(kind, rgb, loc=(0, 0, 0), yaw=0.0, name=None):
    """toy.vehicle, but the second car of a kind is a recoloured copy of the first (16 toys built ~4 min -> seconds)."""
    if kind not in _PROTO:
        v = toy.vehicle(kind, rgb, loc=loc, yaw=yaw, name=name)
        roles = {m.name: "body" for m in v.body_mats}
        trim = bpy.data.materials.get(f"{kind}_trim")
        if trim is not None:
            roles[trim.name] = "trim"
        _PROTO[kind] = (v, roles)
        return v
    proto, roles = _PROTO[kind]
    return _copy_vehicle(proto, roles, rgb, loc, yaw, name or kind)


# ================================================================ the truck
def semi_copy(rgb, loc=(0, 0, 0), yaw=0.0, name=None, load=None):
    if "semi" not in _PROTO:
        v = semi(rgb, loc, yaw, name, load)
        _PROTO["semi"] = (v, {"semi_body": "body", "semi_trim": "trim", "deck": "deck"})
        return v
    proto, roles = _PROTO["semi"]
    v = _copy_vehicle(proto, roles, rgb, loc, yaw, name or "semi")
    _load(v, name, load)
    v.top = proto.top
    return v


def semi(rgb, loc=(0, 0, 0), yaw=0.0, name=None, load=None, iris=None):
    """A big friendly truck cab with a face, a flatbed trailer behind it and up to three toy cars on the deck.
    The trailer and the cars are separate objects: convoy actions key them every frame from the truck's motion."""
    root = kit.empty(name or "semi", loc)
    root.rotation_euler = (0, 0, yaw)
    v = kit.Vehicle("semi", root)
    body = toy.plastic("semi_body", rgb)
    v.body_mats.append(body)
    dark = toy.plastic("semi_trim", tuple(c * 0.35 for c in rgb), rough=0.4)
    grey = toy.plastic("semi_grey", (0.12, 0.12, 0.14), rough=0.45)
    glass = kit.mat("windscreen2", (0.50, 0.78, 0.96), rough=0.04, coat=1.0)
    chrome = kit.chrome()
    rim = toy.plastic("semi_rim", (0.95, 0.95, 0.95), rough=0.25)
    up = kit.empty("body_up", (0, 0, 0), root)
    v.parts["up"] = up
    cab = toy.sbox("semi_cab", (0.25, 0, 1.55), (1.7, 1.75, 2.0), body, 0.32, up)
    toy.sbox("semi_visor", (0.95, 0, 2.62), (0.3, 1.7, 0.16), dark, 0.06, up)
    front = 1.1
    toy.panel("windscreen", (front, 0, 1.95), "x", 1.45, 0.72, 0.18, glass, up, cab)
    toy.eyes(v, front + 0.02, 0, 1.93, 0.29, 0.34, body, iris or (0.30, 0.18, 0.08), parent=up)
    toy.mouth(v, front + 0.005, 0, 1.18, 0.62, 0.24, dark, parent=up)
    kit.grille("grille", (front + 0.01, 0, 0.82), 1.0, 0.3, up)
    for sy in (-1, 1):
        kit.headlight(f"lamp{sy}", (front - 0.01, sy * 0.66, 0.82), 0.1, up)
        toy.panel("cab_side_win", (0.45, sy * 0.88, 1.95), "y", 0.6, 0.5, 0.1, glass, up, cab)
        kit.cyl("exhaust", (-0.72, sy * 0.78, 2.1), 0.07, 1.6, chrome, verts=16, parent=up)
        toy.sbox("mirror", (front + 0.1, sy * 1.02, 1.95), (0.08, 0.08, 0.34), grey, 0.03, up)
        toy.sbox("step", (0.55, sy * 0.9, 0.5), (0.5, 0.12, 0.08), grey, 0.02, up)
        toy.sbox("tank", (-0.9, sy * 0.72, 0.6), (0.8, 0.32, 0.4), chrome, 0.15, up)
    toy.sbox("bumper", (front + 0.08, 0, 0.5), (0.18, 1.85, 0.26), grey, 0.08, up)
    toy.sbox("chassis", (-1.2, 0, 0.62), (2.6, 1.0, 0.26), grey, 0.05, up)
    kit.cyl("fifth_wheel", (KING.x, 0, 0.82), 0.45, 0.08, grey, verts=32, parent=up)
    v.wheels = [toy.toy_wheel("wheel", (AXLES["front"], sy * 0.78, 0.5), 0.5, 0.36, rim, root)
                for sy in (-1, 1)]
    for wx in AXLES["drive"]:
        for sy in (-1, 1):
            v.wheels.append(toy.toy_wheel("wheel", (wx, sy * 0.78, 0.5), 0.5, 0.36, rim, root))

    # trailer: its own object, hitched at KING, deck top at DECK_Z
    tr = kit.empty((name or "semi") + "_trailer", root.matrix_world @ KING)
    v.trailer = tr
    deck_m = toy.plastic("deck", tuple(0.55 + 0.45 * c for c in rgb), rough=0.4)
    toy.sbox("deck", (-TRAILER_L / 2 + 0.3, 0, DECK_Z - 1.0 - 0.12), (TRAILER_L, 2.1, 0.24), deck_m, 0.06, tr)
    toy.sbox("deck_beam", (-TRAILER_L / 2 + 0.3, 0, DECK_Z - 1.0 - 0.36), (TRAILER_L - 0.4, 0.9, 0.24), grey, 0.04, tr)
    for sy in (-1, 1):
        toy.sbox("deck_lip", (-TRAILER_L / 2 + 0.3, sy * 1.04, DECK_Z - 1.0 + 0.03), (TRAILER_L, 0.08, 0.08), body, 0.02, tr)
        for wx in TRAILER_AXLES:
            v.wheels.append(toy.toy_wheel("trailer_wheel", (wx, sy * 0.78, 0.46 - 1.0), 0.46, 0.34, rim, tr))
        toy.sbox("mudguard", ((TRAILER_AXLES[0] + TRAILER_AXLES[1]) / 2, sy * 0.78, 0.98 - 1.0), (1.9, 0.42, 0.06),
                 grey, 0.02, tr)
    for sy in (-1, 1):
        kit.headlight("tail_lamp", (-TRAILER_L + 0.32, sy * 0.85, DECK_Z - 1.0 - 0.15), 0.07, tr, normal=(-1, 0, 0))
    v.trailer_wheels = [w for w in v.wheels if w.parent is tr]
    _load(v, name, load)
    v.top = 2.7
    return v


def _load(v, name, load):
    """Cargo: toy cars parked on the deck, facing forward (separate objects, keyed from the trailer each frame)."""
    v.cargo = []
    for i, item in enumerate((load or [])[:3]):
        kind, _, colour = item.partition(":")
        c = toy_copy(kind or "car", COL.get(colour, COL["red"]), name=f"{name}_cargo{i}")
        c.root.scale = (CARGO_S,) * 3
        c.slot = Vector((CARGO_X[i], 0, DECK_Z - 1.0 + 0.01))
        v.cargo.append(c)


# ================================================================ motion
def _imp(t, t_hit, amp, ring=0.42, decay=2.8):
    """A damped spring kick at t_hit: up first, a small rebound, then still."""
    u = t - t_hit
    if u < 0 or u > 1.4:
        return 0.0
    return amp * math.exp(-decay * u) * math.sin(math.pi * u / ring)


class Plan:
    """One truck's drive: x(t) along the road plus the kicks each axle gets from the obstacle."""

    def __init__(self, v, y, x0, stops, kind, x_hit, amp, seed):
        self.v, self.y, self.kind, self.x_hit, self.amp = v, y, kind, x_hit, amp
        self.stops = stops                                  # [(t, x)] knots, linearly interpolated (constant speed)
        self.rng = random.Random(seed)
        self.sign = 1
        self.hits = self._hits()

    def x(self, t):
        ks = self.stops
        if t <= ks[0][0]:
            return ks[0][1]
        for (t0, x0), (t1, x1) in zip(ks, ks[1:]):
            if t <= t1:
                u = (t - t0) / max(t1 - t0, 1e-6)
                u = u * u * (3 - 2 * u) if x1 == x0 or self.kind == "stop" else u
                return x0 + (x1 - x0) * u
        return ks[-1][1]

    def t_at(self, x):
        """When the truck origin reaches x (None if it never does)."""
        ks = self.stops
        for (t0, x0), (t1, x1) in zip(ks, ks[1:]):
            if x1 > x0 and x0 <= x <= x1:
                return t0 + (x - x0) / (x1 - x0) * (t1 - t0)
        return None

    def _hits(self):
        if self.kind not in ("bump", "pothole"):
            return {}
        s = 1 if self.kind == "bump" else -1               # a bump kicks up, a pothole drops down
        h = {}
        for key, ax in (("front", AXLES["front"]), ("drive", AXLES["drive"][0])):
            h[key] = self.t_at(self.x_hit - ax)
        for k, ax in enumerate(TRAILER_AXLES):
            h[f"trailer{k}"] = self.t_at(self.x_hit - KING.x - ax)
        self.sign = s
        return h

    def cab(self, t):
        """(lift, pitch, pivot_x) of the cab. The front axle rears the nose up about the back wheels; the drive
        axles kick the back up about the front wheels. A pothole does the same downward."""
        if not self.hits:
            return 0.0, 0.0, 0.0
        s, a = self.sign, self.amp
        f, d = self.hits.get("front"), self.hits.get("drive")
        kf = _imp(t, f, 1.0) if f else 0.0
        kd = _imp(t, d, 1.0) if d else 0.0
        lift = (0.10 * kf + 0.14 * kd) * a
        pitch = (-0.15 * kf + 0.09 * kd) * a
        pivot = AXLES["drive"][-1] if abs(kf) >= abs(kd) else AXLES["front"]
        return s * lift, s * pitch, pivot

    def trailer(self, t):
        if not self.hits:
            return 0.0
        a = sum(_imp(t, self.hits[k], 0.06 * self.amp) for k in ("trailer0", "trailer1") if self.hits.get(k))
        return self.sign * a                                # rear end kicks: pitch about the hitch

    def deck_kick(self, t):
        """How hard the deck is being kicked right now (for the cars riding on it)."""
        if not self.hits:
            return 0.0
        return sum(abs(_imp(t, self.hits[k], 1.0, ring=0.3, decay=3.0)) for k in ("trailer0", "trailer1")
                   if self.hits.get(k))


def _truck_matrix(p, t):
    lift, pitch, px = p.cab(t)
    turn = Matrix.Translation((px, 0, 0)) @ Euler((0, pitch, 0)).to_matrix().to_4x4() @ Matrix.Translation((-px, 0, 0))
    return Matrix.Translation((p.x(t), p.y, max(0.0, lift) if p.sign > 0 else lift)) @ turn


def _trailer_matrix(p, t):
    hitch = Matrix.Translation((p.x(t), p.y, 0)) @ Matrix.Translation(KING)     # the hitch rides level with the road
    hz = (_truck_matrix(p, t) @ KING).z - KING.z if p.hits else 0.0         # the hitch rides with the truck
    return Matrix.Translation((0, 0, hz)) @ hitch @ Euler((0, p.trailer(t), 0)).to_matrix().to_4x4()


_KEYS = {}                               # ob -> {data_path: [(frame, (x, y, z))]}, written in one go by _flush()


def _key_matrix(ob, t, m):
    loc, rot, _ = m.decompose()
    d = _KEYS.setdefault(ob, {})
    d.setdefault("location", []).append((F(t), tuple(loc)))
    d.setdefault("rotation_euler", []).append((F(t), tuple(rot.to_euler())))


def _key_rot(ob, t, xyz):
    _KEYS.setdefault(ob, {}).setdefault("rotation_euler", []).append((F(t), tuple(xyz)))


def _fcurves(ob):
    ad = ob.animation_data
    act = ad.action
    if hasattr(act, "fcurves"):
        return act.fcurves
    from bpy_extras import anim_utils
    return anim_utils.action_get_channelbag_for_slot(act, ad.action_slot).fcurves


def _flush():
    """Per-frame motion as whole f-curves (keyframe_insert per frame took minutes for a convoy shot)."""
    for ob, paths in _KEYS.items():
        for path, keys in paths.items():
            f0, v0 = keys[0]
            setattr(ob, path, v0)
            ob.keyframe_insert(path, frame=f0)            # makes the three curves
        fcs = {(fc.data_path, fc.array_index): fc for fc in _fcurves(ob)}
        for path, keys in paths.items():
            for i in range(3):
                fc = fcs[(path, i)]
                fc.keyframe_points.clear()
                fc.keyframe_points.add(len(keys))
                fc.keyframe_points.foreach_set("co", [c for f, v in keys for c in (f, v[i])])
                fc.keyframe_points.foreach_set("interpolation", [1] * len(keys))      # LINEAR: one key per frame
                fc.update()
    _KEYS.clear()


def _cargo_hop(p, i, t):
    """Each car on the deck jumps when the trailer axles kick, the rear car a bit more."""
    k = p.deck_kick(t)
    return k * (0.22 + 0.1 * i) * p.amp


def bake(plans, dur, falls=None, lifts=None):
    """Key every truck, trailer, wheel and cargo car each frame. falls: {(truck_id, i): Fall}; lifts likewise."""
    falls, lifts = falls or {}, lifts or {}
    step = 1.0 / T.FPS
    n = int(round(dur * T.FPS)) + 1
    for p in plans:
        v = p.v
        dist0 = p.x(0)
        for j in range(n):
            t = j * step
            _key_matrix(v.root, t, _truck_matrix(p, t))
            _key_matrix(v.trailer, t, _trailer_matrix(p, t))
            for w in v.wheels:
                _key_rot(w, t, (0, (p.x(t) - dist0) / max(w.get("r", 0.5), 0.05), 0))
            for i, c in enumerate(v.cargo):
                key = (v.root.name, i)
                if key in falls and t >= falls[key].t0:
                    continue
                if key in lifts and t < lifts[key].t1:
                    continue
                hop = _cargo_hop(p, i, t)
                m = _trailer_matrix(p, t) @ Matrix.Translation(c.slot + Vector((0, 0, max(0.0, hop))))
                wobble = Euler((math.radians(6) * math.sin(t * 17 + i) * min(1, hop * 4), 0, 0)).to_matrix().to_4x4()
                _key_matrix(c.root, t, m @ wobble)
    _flush()
    for f in falls.values():
        f.key()
    for li in lifts.values():
        li.key()


class Fall:
    """A cargo car thrown off the deck: it leaves at t0, tumbles once and lands on the road beside the truck."""

    def __init__(self, plan, i, t0, side=1, seed=3):
        self.p, self.i, self.t0, self.side = plan, i, t0, side
        self.car = plan.v.cargo[i]
        self.rng = random.Random(seed)
        m0 = _trailer_matrix(plan, t0) @ Matrix.Translation(self.car.slot)
        self.start = m0.to_translation()
        self.land = Vector((self.start.x - 2.0, plan.y + side * 2.4, 0.0))
        self.t_land = t0 + 0.95

    def key(self):
        c, s, e = self.car.root, self.start, self.land
        yaw = 0.0
        for j in range(0, 13):
            u = j / 12
            t = self.t0 + (self.t_land - self.t0) * u
            pos = s.lerp(e, u) + Vector((0, 0, 2.2 * math.sin(math.pi * u) * (1 - 0.2 * u)))
            roll = self.side * 2 * math.pi * u                     # one full roll in the air
            k_loc(c, t, tuple(pos))
            k_rot(c, t, (roll, math.radians(-12) * math.sin(math.pi * u), yaw + math.radians(35) * u))
            k_scale_s(c, t)
        for dt, z in ((0.14, 0.32), (0.3, 0.0), (0.42, 0.1), (0.54, 0.0)):        # two landing bounces
            k_loc(c, self.t_land + dt, (e.x, e.y, z))
            k_rot(c, self.t_land + dt, (self.side * 2 * math.pi, 0, yaw + math.radians(35)))
        look(self.car, self.t0, -20, 0)                           # wide eyes up in the air
        look(self.car, self.t_land + 0.6, 10, -20)


def k_scale_s(ob, t):
    ob.scale = (CARGO_S,) * 3
    ob.keyframe_insert("scale", frame=F(t))


class Lift:
    """A fallen car lifted by the crane's hook from the road back onto its slot on the deck (deck parked)."""

    def __init__(self, plan, i, crane, t0, t1, ground):
        self.p, self.i, self.crane, self.t0, self.t1, self.ground = plan, i, crane, t0, t1, Vector(ground)
        self.car = plan.v.cargo[i]

    def key(self):
        c = self.car.root
        slot = (_trailer_matrix(self.p, self.t1) @ Matrix.Translation(self.car.slot)).to_translation()
        g = self.ground
        k_loc(c, 0, tuple(g))
        k_rot(c, 0, (0, 0, math.radians(35)))
        k_loc(c, self.t0, tuple(g))
        k_rot(c, self.t0, (0, 0, math.radians(35)))
        for j in range(1, 9):
            u = j / 8
            t = self.t0 + (self.t1 - self.t0) * u
            p = g.lerp(slot, u) + Vector((0, 0, 1.3 * math.sin(math.pi * u)))
            k_loc(c, t, tuple(p))
            k_rot(c, t, (math.radians(8) * math.sin(u * 9), 0, math.radians(35) * (1 - u)))
        k_loc(c, self.t1 + 0.12, (slot.x, slot.y, slot.z + 0.12))
        k_loc(c, self.t1 + 0.3, tuple(slot))
        look(self.car, self.t0, -18, 0)
        look(self.car, self.t1 + 0.4, -6, -18)
        rope = kit.cyl("crane_rope", (0, 0, 3.4), 0.035, 3.6, kit.mat("rope", (0.95, 0.78, 0.15), rough=0.6), verts=10,
                       parent=c)                               # the crane's cable, hooked to the car's roof
        kit.sphere("hook", (0, 0, 1.7), 0.12, kit.chrome(), parent=c)
        for t, sc in ((0, 0), (self.t0 - 0.5, 0), (self.t0 - 0.2, 1), (self.t1 + 0.25, 1), (self.t1 + 0.5, 0)):
            k_scale(rope, t, sc)


# ================================================================ story actions
def trucks(cast):
    return [v for v in cast.values() if v.kind == "semi"]


def lanes(n):
    return [(i - (n - 1) / 2) * LANE * (-1) for i in range(n)]       # first truck farthest (+y), last nearest the camera


def _hook_cam(spec_cam, cast, frm, aim, lens, dur, to=None, aim_to=None):
    cam, tgt = kit.camera(frm, aim, lens=lens)
    k_loc(cam, 0, frm)
    k_loc(tgt, 0, aim)
    k_loc(cam, dur, to or frm)
    k_loc(tgt, dur, aim_to or aim)
    cast.own_camera = True
    return cam


def a_line(cast, dur, args):
    """The convoy parked side by side facing the camera; each truck bounces as it's named (the reference's line-up)."""
    vs = trucks(cast)
    plans = [Plan(v, y, 0.0, [(0, 0.0), (dur, 0.0)], "none", 0, 0, i) for i, (v, y) in enumerate(zip(vs, lanes(len(vs))))]
    for p in plans:                                  # trucks face +x toward the camera, parked at x = 0
        p.stops = [(0, -0.4 * abs(p.y)), (dur, -0.4 * abs(p.y))]
    bake(plans, dur)
    order = args.get("order") or [v.root.name for v in vs]
    gap = max(0.8, (dur - 1.0) / max(1, len(order)))
    for k, who in enumerate(order):
        v = cast.get(who)
        if v is None:
            continue
        t = 0.5 + k * gap
        up = v.parts["up"]
        for dt, z in ((0, 0), (0.15, 0.35), (0.38, 0)):
            k_loc(up, t + dt, (0, 0, z))
        look(v, 0, -6, 0)
        look(v, t, -8, -10)
    w = (len(vs) - 1) * LANE
    _hook_cam(None, cast, (11.5, -5.0, 2.1), (-1.0, 0, 1.8), 34, dur,
              to=(10.0, -4.4, 2.0), aim_to=(-1.0, 0, 1.8))
    return [{"t": 0.5 + k * gap, "sfx": "boing"} for k in range(len(order))]


def a_drive(cast, dur, args):
    """The convoy drives over an obstacle. args: obstacle bump|pothole|train, amp (kick size), fall {who, car, side},
    x (obstacle x, default 0). Trucks run side by side, a little staggered; the camera waits low beyond it."""
    vs = trucks(cast)
    kind = args.get("obstacle", "bump")
    bx = args.get("x", 0.0)
    amp = args.get("amp", 1.9)                  # the reference trucks rear right up
    speed = args.get("speed", 4.2)
    ys = lanes(len(vs))
    plans = []
    ev = [{"t": 0.1, "sfx": "whoosh"}, {"t": 0.5, "sfx": "horn"}]
    if kind == "train":
        arms = crossing(bx)
        t_stop, t_go = 2.2, dur - 2.6
        x_stop = bx - 3.6
        tr = train(-30.0, bx)
        k_loc(tr.root, 0, (bx, -34.0, 0.15))
        k_loc(tr.root, dur, (bx, 34.0, 0.15))
        kit.roll_wheels(tr, F(0), F(dur), 68.0)
        look(tr, 0, -6, 0)
        for piv, sy in arms:                                   # arms come down before, lift after
            up_, down = (sy * math.radians(-80), 0, 0), (0, 0, 0)
            k_rot(piv, 0, up_)
            k_rot(piv, 0.9, down)
            k_rot(piv, t_go - 0.7, down)
            k_rot(piv, t_go - 0.1, up_)
        for i, (v, y) in enumerate(zip(vs, ys)):
            st = x_stop - i * 0.0
            x0 = st - speed * t_stop
            plans.append(Plan(v, y, x0, [(0, x0), (t_stop, st), (t_go, st), (dur, st + speed * (dur - t_go))],
                              "stop", bx, 0, i))
            look(v, t_stop, -4, -40)                          # every truck turns its eyes to the train
            look(v, t_go - 0.4, -6, 0)
        ev += [{"t": t_stop - 0.3, "sfx": "whistle"}, {"t": t_go - 0.2, "sfx": "horn"}, {"t": t_go, "sfx": "whoosh"}]
        ev += [{"t": round(1.0 + k * 0.42, 2), "sfx": "chuff"} for k in range(int((dur - 2.0) / 0.42))]
        bake(plans, dur)
        _hook_cam(None, cast, (bx + 9, -14, 2.4), (bx - 3, 0, 1.6), 30, dur, to=(bx + 8, -13, 2.2))
        return ev

    rng = random.Random(len(vs) * 7 + int(bx))
    for i, (v, y) in enumerate(zip(vs, ys)):
        t_hit = args.get("t_hit", 1.6) + i * 0.7 + rng.uniform(-0.15, 0.15)   # staggered: bumps land one by one
        x0 = bx - AXLES["front"] - speed * t_hit
        x_end = x0 + speed * dur
        plans.append(Plan(v, y, x0, [(0, x0), (dur, x_end)], kind, bx, amp * rng.uniform(0.85, 1.15), i))
        if kind == "pothole":
            pothole(bx, y + 0.78, 0.7)
            pothole(bx + 0.4, y - 0.78, 0.55)
    if kind == "bump":
        speed_bump(bx)
    falls = {}
    fa = args.get("fall")
    if fa:
        p = next((p for p in plans if p.v.root.name == fa["who"]), None)
        if p is not None and p.hits.get("trailer0"):
            i = min(fa.get("car", len(p.v.cargo) - 1), len(p.v.cargo) - 1)
            f = Fall(p, i, p.hits["trailer0"] + 0.08, side=fa.get("side", -1))
            falls[(p.v.root.name, i)] = f
            ev += [{"t": round(f.t0, 2), "sfx": "boing"}, {"t": round(f.t_land, 2), "sfx": "clank"},
                   {"t": round(f.t_land + 0.3, 2), "sfx": "pop"}]
            look(p.v, f.t0 + 0.3, -4, 40)                     # the truck looks back at its lost car
    for p in plans:
        for key in ("front", "drive", "trailer0"):
            t = p.hits.get(key)
            if t is not None and t < dur:
                ev.append({"t": round(t, 2), "sfx": "thud" if key != "trailer0" else "boing"})
        look(p.v, 0, -6, 0)
    bake(plans, dur, falls)
    drive_camera(cast, plans, args.get("cam", "front"), bx, dur, falls)
    return ev


def drive_camera(cast, plans, mode, bx, dur, falls):
    """front: low and ahead, the trucks come at it over the obstacle, then it backs off as they pass.
    side: runs beside the convoy like a TV chase. low: down at the bump, wide lens, trucks thunder past.
    chase: behind and above the last truck. A fall pulls any camera toward the falling car."""
    near = plans[-1]                                          # the truck nearest the camera side
    if mode == "side":
        pts = []
        for t in (0, dur * 0.33, dur * 0.66, dur):
            cx = sum(p.x(t) for p in plans) / len(plans) - 2.0
            pts.append((t, (cx + 3.0, -17.0, 2.6), (cx, 0.5, 1.4)))
        cam, tgt = kit.camera(pts[0][1], pts[0][2], lens=34)
        for t, c, a in pts:
            k_loc(cam, t, c)
            k_loc(tgt, t, a)
    elif mode == "low":
        cam, tgt = kit.camera((bx + 8, -10.5, 0.75), (bx - 6, 1.0, 1.5), lens=24)
        k_loc(cam, 0, (bx + 8, -10.5, 0.75))
        k_loc(cam, dur, (bx + 10, -11.5, 0.9))
        k_loc(tgt, 0, (bx - 6, 1.0, 1.5))
        k_loc(tgt, dur, (bx + 10, 1.0, 1.6))
    elif mode == "chase":
        pts = []
        for t in (0, dur / 2, dur):
            lx = near.x(t)
            pts.append((t, (lx - 15.0, near.y - 7.0, 4.2), (lx + 2.0, 0.0, 1.2)))
        cam, tgt = kit.camera(pts[0][1], pts[0][2], lens=30)
        for t, c, a in pts:
            k_loc(cam, t, c)
            k_loc(tgt, t, a)
    else:
        cam, tgt = kit.camera((bx + 10, -8.0, 1.4), (bx - 4, 1.0, 1.6), lens=34)
        k_loc(cam, 0, (bx + 10, -8.0, 1.4))
        k_loc(tgt, 0, (bx - 4, 1.0, 1.6))
        k_loc(cam, dur, (bx + 22, -9.5, 2.0))
        k_loc(tgt, dur, (bx + 8, 1.0, 1.6))
    for f in falls.values():                                  # follow the car that flies off: aim at it from take-off
        bpy.context.scene.frame_set(F(f.t0 - 0.4))
        k_loc(tgt, f.t0 - 0.4, tuple(tgt.matrix_world.translation))
        k_loc(tgt, f.t_land + 0.2, (f.land.x, f.land.y * 0.6, 0.8))
        k_loc(tgt, dur, (f.land.x + 1.0, f.land.y * 0.6, 0.9))
    cast.own_camera = True


def a_lift(cast, dur, args):
    """The convoy waits; the crane truck rolls up and lifts the fallen car back onto its trailer.
    args: who (truck), car (index), helper (crane cast id), x (where the trucks park)."""
    vs = trucks(cast)
    ys = lanes(len(vs))
    x = args.get("x", 0.0)
    plans = [Plan(v, y, x, [(0, x), (dur, x)], "none", 0, 0, i) for i, (v, y) in enumerate(zip(vs, ys))]
    p = next(p for p in plans if p.v.root.name == args["who"])
    i = min(args.get("car", len(p.v.cargo) - 1), len(p.v.cargo) - 1)
    slot = (_trailer_matrix(p, 0) @ Matrix.Translation(p.v.cargo[i].slot)).to_translation()
    side = args.get("side", -1)
    ground = (slot.x - 0.6, p.y + side * 2.6, 0.0)
    t0, t1 = 2.4, min(dur - 1.4, 5.6)
    lifts = {(p.v.root.name, i): Lift(p, i, None, t0, t1, ground)}
    bake(plans, dur, lifts=lifts)
    h = cast.get(args.get("helper", ""))
    if h is not None:                                          # the crane drives in behind the fallen car
        hx, hy = ground[0] - 2.4, ground[1] + side * 0.2
        k_loc(h.root, 0, (hx - 9, hy, 0))
        k_loc(h.root, 1.8, (hx, hy, 0))
        kit.roll_wheels(h, F(0), F(1.8), 9)
        look(h, 2.0, -12, 30)
    car = p.v.cargo[i]
    look(car, 0, 10, -20)
    look(p.v, 0, -4, 40)
    confetti((slot.x, slot.y, slot.z + 2.0), t1 + 0.3, n=26, seed=5)
    _hook_cam(None, cast, (slot.x + 5.5, slot.y - 11 * (1 if side < 0 else -1), 2.6), (slot.x - 1.2, slot.y + side * 1.4, 1.5),
              30, dur, to=(slot.x + 4.5, slot.y - 10 * (1 if side < 0 else -1), 2.5))
    return [{"t": 0.2, "sfx": "whoosh"}, {"t": t0, "sfx": "drumroll"}, {"t": t1, "sfx": "pop"},
            {"t": t1 + 0.3, "sfx": "success"}]


ACTIONS = {"convoy_line": a_line, "convoy_drive": a_drive, "convoy_lift": a_lift}
MIN_DUR = {"convoy_line": 4.0, "convoy_drive": 7.5, "convoy_lift": 7.0}


# ================================================================ one shot (toycolors/convoy_scene.py)
def build_cast(spec):
    from toycolors import story_actions as A
    cast = A.Cast()
    for c in spec["cast"]:
        loc = (c.get("x", 0), c.get("y", 0), c.get("z", 0))
        if c["kind"] == "semi":
            v = semi_copy(COL[c["colour"]], loc=loc, name=c["id"], load=c.get("load"))
        else:
            v = toy_copy(c["kind"], COL[c["colour"]], loc=loc, yaw=math.radians(c.get("yaw", 0)), name=c["id"])
            v.top = toy.TOP.get(c["kind"], 1.65)
        v.spec = c
        cast[c["id"]] = v
    return cast


def build_shot(spec):
    from toycolors import story_actions as A
    cast = build_cast(spec)                                  # the toys first: bpy.ops slow down as the scene fills
    build_set(spec.get("set", "convoy"))
    A.idle(cast, spec["dur"], seed=len(spec.get("action", "")))
    for v in cast.values():                                    # the cars on the decks blink too
        for k, c in enumerate(getattr(v, "cargo", [])):
            A.blinks(c, [0.9 + k * 0.5 + j * 2.7 for j in range(int(spec["dur"] / 2.7) + 1)])
    ev = ACTIONS[spec["action"]](cast, spec["dur"], spec.get("args", {}))
    for who, words in (spec.get("talk") or {}).items():
        if who in cast:
            A.talk(cast[who], words)
    if not cast.own_camera:
        A.camera(cast, spec)
    return ev
