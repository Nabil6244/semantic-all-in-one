"""Story shots for Toy Vehicles stories: one set, a cast and one action per shot, all reusable.

A shot spec (written by toycolors/story.py, rendered by toycolors/story_scene.py):
{"set": "mud", "dur": 6.2, "action": "stuck", "args": {...},
 "cast": [{"id": "zip", "kind": "car", "colour": "red", "x": -1, "y": 0, "yaw": 0, "muddy": false}],
 "talk": {"zip": [[t0, t1], ...]},              # word times in the shot: each word is a little squash-bounce
 "camera": {"aim": "zip" | [x, y, z], "dist": 9, "height": 2.4, "side": 25, "lens": 45, "push": 0.12, "pan": 0}}

Actions: idle, drive_in, spot, stuck, tow, wash, dance. Each animates the cast and returns the sound events
[{"t", "sfx"}]. Every shot keeps something moving: blinks, eye looks, talk bounces and a slow camera push.
"""
import math
import random

import bpy

from toycolors import kit, templates, toy
from toycolors import timeline as T
from toycolors.templates import F, blinks, confetti, hop, k_loc, k_rot, k_scale, look

COL = dict(T.COLOURS)
COL.setdefault("brown", (0.22, 0.10, 0.035))
MUD_RGB = (0.20, 0.095, 0.03)
MUD = (2.0, 0.0)                    # the mud puddle on the mud set
SINK = -0.22


# ================================================================ sets
def build_set(name):
    # vivid like the reference: the glossy orange-brown toy floor and a toy-blue road (sand + grey measured 0.40 sat vs 0.70)
    toy.playground(slides=True, size=(44, 24))
    kit.road(-34, 34, 0, tint=((0.02, 0.10, 0.42), (0.04, 0.16, 0.58)))
    if name == "mud":
        mud = kit.ramp_mat("mud", (0.09, 0.045, 0.015), (0.20, 0.10, 0.035), scale=2.5, rough=0.55)
        kit.sphere("mud_pool", (MUD[0], MUD[1], 0.0), 1, mud, scale=(2.3, 1.7, 0.1))
        rng = random.Random(4)
        for i in range(9):                      # lumpy edge so it reads as mud, not a disc
            a = i / 9 * 2 * math.pi + rng.uniform(-0.2, 0.2)
            kit.sphere("mud_lump", (MUD[0] + math.cos(a) * 2.1, MUD[1] + math.sin(a) * 1.5, 0.0), 1, mud,
                       scale=(rng.uniform(0.4, 0.7), rng.uniform(0.3, 0.5), 0.09))


# ================================================================ cast
class Cast(dict):
    own_camera = False                      # an action that moves its own camera (a race) sets this


def build_cast(spec):
    cast = Cast()
    for c in spec["cast"]:
        v = toy.vehicle(c["kind"], COL[c["colour"]], loc=(c.get("x", 0), c.get("y", 0), c.get("z", 0)),
                        yaw=math.radians(c.get("yaw", 0)), name=c["id"])
        v.spec = c
        v.top = toy.TOP.get(c["kind"], 1.65)
        v.mud = [kit.wipe(m, MUD_RGB, "Z", below=True) for m in v.body_mats]   # mud climbs up from the ground
        set_mud(v, 0, 1.0 if c.get("muddy") else 0.0)
        cast[c["id"]] = v
    return cast


def set_mud(v, t, amount):
    """amount 0 = clean, 1 = covered up to the roof. Keyframed, so it can climb or wash away."""
    z = -1.0 + amount * (v.top + 1.6)
    for n in v.mud:
        kit.key_value(n, F(t), z)


def pos(v):
    return tuple(v.root.location)


def home(v):
    """Where the script puts this toy in the shot (the camera frames these, not the end of the action)."""
    return (v.spec.get("x", 0), v.spec.get("y", 0), v.spec.get("z", 0))


def place(v, t, x=None, y=None, z=None):
    p = list(v.root.location)
    for i, val in enumerate((x, y, z)):
        if val is not None:
            p[i] = val
    k_loc(v.root, t, tuple(p))


def drive_to(v, t0, t1, x, y=None):
    p0 = pos(v)
    p1 = (x, p0[1] if y is None else y, p0[2])
    k_loc(v.root, t0, p0)
    k_loc(v.root, t1, p1)
    kit.roll_wheels(v, F(t0), F(t1), math.dist(p0[:2], p1[:2]))


def spin_wheels(v, t0, t1, turns):
    for w in v.wheels:
        r = w.get("r", 0.35)
        a0 = w.rotation_euler.y
        for t, a in ((t0, a0), (t1, a0 + turns * 2 * math.pi)):
            w.rotation_euler = (0, a, 0)
            w.keyframe_insert("rotation_euler", frame=F(t))


def talk(v, words):
    """One squash-and-stretch per spoken word, so the toy visibly says its line."""
    for t0, t1 in words:
        mid = t0 + min(0.12, (t1 - t0) / 2)
        for t, s in ((t0, (1, 1, 1)), (mid, (1.035, 1.035, 0.94)), (min(t1, mid + 0.14), (1, 1, 1))):
            k_scale(v.root, t, s)


def idle(cast, dur, seed=0):
    rng = random.Random(seed)
    for i, v in enumerate(cast.values()):
        blinks(v, [0.6 + i * 0.4 + k * rng.uniform(2.2, 3.0) for k in range(int(dur / 2.4) + 1) if 0.6 + k * 2.4 < dur - 0.3])


# ================================================================ actions (all times in seconds from the shot start)
def a_idle(cast, dur, args):
    for v in cast.values():
        look(v, 0, -6, -16)
    return []


def a_drive_in(cast, dur, args):
    v = cast[args["who"]]
    x1 = args.get("to", 0.0)
    ahead = math.cos(v.root.rotation_euler.z) > 0             # facing +x: comes in from the left
    frm = args.get("from") or ("left" if ahead else "right")   # from the other side it backs in (a tow truck reversing)
    x0 = x1 + (-11 if frm == "left" else 11)
    arrive = min(args.get("arrive", 2.4), dur - 0.6)
    place(v, 0, x=x0)
    drive_to(v, 0, arrive, x1)
    hop(v.root, arrive, 0.22, base=pos(v)[2])
    look(v, 0, -4, 0)
    look(v, arrive + 0.2, -6, -18)               # turns its eyes to the viewer once it stops
    for o in cast.values():
        if o is not v:
            look(o, 0, -4, -10)
            look(o, arrive - 0.6, -4, 25 if pos(o)[0] < x1 else -25)
    return [{"t": 0.15, "sfx": "whoosh"}, {"t": arrive + 0.1, "sfx": "whistle"}]


def a_spot(cast, dur, args):
    """The hero stops and looks at something ahead, then bounces with excitement."""
    v = cast[args["who"]]
    look(v, 0, -6, -16)
    look(v, 0.8, 12, 0)                           # eyes down at the mud ahead
    look(v, 1.8, -6, -16)
    for t in (1.9, 2.4):
        hop(v.root, t, 0.18, base=pos(v)[2])
    return [{"t": 1.9, "sfx": "boing"}]


def a_stuck(cast, dur, args):
    v = cast[args["who"]]
    x_in = MUD[0]
    t_in, t_sink = 1.4, 2.0
    drive_to(v, 0, t_in, x_in)
    k_loc(v.root, t_sink, (x_in, pos(v)[1], SINK))
    spin_wheels(v, t_in, dur, turns=(dur - t_in) * 2.2)  # wheels spin, the car goes nowhere
    for k in range(int((dur - t_sink) / 0.32)):    # rocks side to side while it tries
        t = t_sink + k * 0.32
        k_rot(v.root, t, (math.radians(5 if k % 2 else -5), 0, v.root.rotation_euler.z))
    set_mud(v, t_in, 0.0)
    set_mud(v, t_in + 1.6, 1.0)
    look(v, 0, -6, 0)
    look(v, t_sink + 0.2, 14, -10)                 # sad eyes down
    look(v, t_sink + 1.6, -4, -20)
    mud = kit.ramp_mat("mud", (0.09, 0.045, 0.015), (0.20, 0.10, 0.035), scale=2.5, rough=0.55)
    rng = random.Random(7)
    ev = [{"t": t_in, "sfx": "boing"}]
    for k in range(int((dur - t_in - 0.5) / 0.22)):  # mud flies off the back wheels
        t = t_in + 0.2 + k * 0.22
        b = kit.sphere("splat", (x_in - 0.9, 0, 0.1), rng.uniform(0.08, 0.16), mud)
        k_scale(b, t - 0.05, 0)
        k_scale(b, t, 1)
        vx, vy, vz = rng.uniform(-3.5, -1.5), rng.uniform(-1.6, 1.6), rng.uniform(2.5, 4.5)
        for j in range(1, 6):
            dt = j * 0.12
            k_loc(b, t + dt, (x_in - 0.9 + vx * dt, vy * dt, max(0.02, 0.1 + vz * dt - 4.9 * dt * dt)))
        k_scale(b, t + 0.7, 1)
        k_scale(b, t + 0.9, 0)
        if k % 4 == 0:
            ev.append({"t": round(t, 2), "sfx": "pop"})
    return ev


def _rope(a, b, z=0.55):
    """A tow rope from the back of `a` (facing +x) to the front of `b`, carried by `a`."""
    rope_m = kit.mat("rope", (0.95, 0.78, 0.15), rough=0.6)
    bpy.context.view_layer.update()
    xa, xb = pos(a)[0] - 1.0, pos(b)[0] + 1.0
    L = max(0.3, xa - xb)
    r = kit.cyl("rope", ((xa + xb) / 2, pos(a)[1], z), 0.05, L, rope_m, rot=(0, math.pi / 2, 0))
    r.parent = a.root
    r.matrix_parent_inverse = a.root.matrix_world.inverted()
    return r


def a_tow(cast, dur, args):
    h, v = cast[args["helper"]], cast[args["who"]]
    rope = _rope(h, v)
    k_scale(rope, 0.0, 0)
    k_scale(rope, 0.6, 1)
    pull0, pull1 = 1.2, max(3.4, dur - 2.4)
    spin_wheels(h, pull0, pull1, turns=4)          # it strains: wheels turn, it barely moves
    for k in range(int((pull1 - pull0) / 0.3)):
        t = pull0 + k * 0.3
        place(h, t, x=pos(h)[0] + (0.06 if k % 2 else 0))
    look(h, 0, -6, 0)
    look(h, pull0, -2, -20)
    look(v, 0, 10, -12)
    move = 3.4
    hx, vx = pos(h)[0], pos(v)[0]
    k_loc(h.root, pull1, (hx, pos(h)[1], 0))
    k_loc(h.root, pull1 + 1.2, (hx + move, pos(h)[1], 0))
    kit.roll_wheels(h, F(pull1), F(pull1 + 1.2), move)
    k_loc(v.root, pull1, (vx, pos(v)[1], SINK))
    k_loc(v.root, pull1 + 0.5, (vx + move * 0.4, pos(v)[1], 0.25))
    k_loc(v.root, pull1 + 1.2, (vx + move, pos(v)[1], 0))
    kit.roll_wheels(v, F(pull1), F(pull1 + 1.2), move)
    look(v, pull1 + 0.4, -10, -18)
    hop(v.root, pull1 + 1.4, 0.3)
    hop(h.root, pull1 + 1.6, 0.2)
    k_scale(rope, pull1 + 1.5, 1)
    k_scale(rope, pull1 + 1.8, 0)
    return [{"t": pull0, "sfx": "drumroll"}, {"t": pull1 + 0.5, "sfx": "burst"}, {"t": pull1 + 1.4, "sfx": "success"}]


def a_wash(cast, dur, args):
    h, v = cast[args["helper"]], cast[args["who"]]
    water = kit.mat("water", (0.35, 0.70, 1.0), rough=0.03, coat=1.0)
    soap = kit.mat("soap", (0.95, 0.97, 1.0), rough=0.05, coat=1.0)
    hx, vx = pos(h)[0], pos(v)[0]
    side = -1 if hx > vx else 1                  # the helper faces the hero
    src = (hx + side * 0.9, pos(h)[1], 1.5)
    dst = (vx, pos(v)[1], v.top + 0.2)
    t0, t1 = 0.8, max(3.6, dur - 1.6)
    rng = random.Random(3)
    n = 26
    for i in range(n):                           # drops travel the arc again and again, so the stream looks continuous
        d = kit.sphere("drop", src, rng.uniform(0.05, 0.09), water)
        k_scale(d, 0, 0)
        k_scale(d, t0 - 0.01, 0)
        k_scale(d, t0, 1)
        trip = 0.55
        t = t0 + (i / n) * trip
        while t < t1:
            for j in range(4):
                u = j / 3
                p = (src[0] + (dst[0] - src[0]) * u, src[1] + (dst[1] - src[1]) * u + rng.uniform(-0.12, 0.12),
                     src[2] + (dst[2] - src[2]) * u + 1.2 * math.sin(math.pi * u))
                k_loc(d, t + u * trip, p)
            t += trip
        k_scale(d, t1, 1)
        k_scale(d, t1 + 0.1, 0)
    for i in range(14):                          # soap bubbles grow on the body and pop
        b = kit.sphere("bubble", (vx + rng.uniform(-0.9, 0.9), pos(v)[1] + rng.uniform(-0.7, 0.7), rng.uniform(0.4, v.top)),
                       rng.uniform(0.12, 0.25), soap)
        tb = rng.uniform(t0 + 0.4, t1 - 0.6)
        k_scale(b, 0, 0)
        k_scale(b, tb, 0)
        k_scale(b, tb + 0.3, 1)
        k_scale(b, tb + 1.0, 1.1)
        k_scale(b, tb + 1.1, 0)
    set_mud(v, t0 + 0.4, 1.0)
    set_mud(v, t1, 0.0)
    look(h, 0, -4, 0)
    look(v, 0, -20, -8)                           # eyes up at the water
    look(v, t1 + 0.1, -6, -18)
    hop(v.root, t1 + 0.3, 0.3)
    hop(v.root, t1 + 0.8, 0.2)
    return [{"t": t0, "sfx": "whoosh"}, {"t": t0 + 1.5, "sfx": "pop"}, {"t": t1, "sfx": "sparkle"},
            {"t": t1 + 0.3, "sfx": "chime"}]


def a_dance(cast, dur, args):
    vs = list(cast.values())
    beat = 0.54
    for i, v in enumerate(vs):
        look(v, 0, -6, -18)
        for k in range(int((dur - 0.5) / beat)):
            if (k + i) % 2 == 0:
                hop(v.root, 0.3 + k * beat, 0.22)
        ts = 1.0 + i * 0.7                        # one spin each, in turn
        yaw = v.root.rotation_euler.z
        k_rot(v.root, ts, (0, 0, yaw))
        k_rot(v.root, ts + 0.6, (0, 0, yaw + 2 * math.pi))
    xs = [pos(v)[0] for v in vs]
    confetti((sum(xs) / len(xs), 0, 2.8), 1.0, n=36)
    return [{"t": 1.0, "sfx": "burst"}, {"t": 1.1, "sfx": "success"}]


def a_race(cast, dur, args):
    """Two toys race side by side along the road; the camera runs beside them. args: a, b, winner."""
    va, vb = cast[args["a"]], cast[args["b"]]
    win = args.get("winner", args["a"])
    x0, x1 = -14.0, 16.0
    t_go, t_end = 0.8, dur - 0.8
    for v, y in ((va, -0.85), (vb, 0.85)):
        place(v, 0, x=x0, y=y)
        place(v, t_go, x=x0, y=y)
        fast = v is cast[win]
        mid = t_go + (t_end - t_go) * (0.5 if fast else 0.56)
        k_loc(v.root, mid, ((x0 + x1) / 2 + (0.6 if fast else -0.6), y, 0))
        k_loc(v.root, t_end, (x1 if fast else x1 - 2.4, y, 0))
        kit.roll_wheels(v, F(t_go), F(t_end), x1 - x0)
        for k in range(int((t_end - t_go) / 0.5)):      # bumpy little bounces on the way
            hop(v.root, t_go + 0.3 + k * 0.5 + (0.12 if fast else 0), 0.08)
        look(v, 0, -4, -18)
        look(v, t_go, -2, 0)
        look(v, t_end, -6, -18)
    hop(cast[win].root, t_end + 0.1, 0.35)
    cam, tgt = kit.camera((x0 + 4, -7.5, 1.8), (x0, 0, 0.8), lens=40)          # tracks two racers side by side: no extra zoom
    for t in (0, t_go, (t_go + t_end) / 2, t_end, dur):
        f = min(1, max(0, (t - t_go) / (t_end - t_go)))
        cx = x0 + (x1 - x0) * f
        k_loc(cam, t, (cx + 3.5, -7.2, 1.7))
        k_loc(tgt, t, (cx, 0, 0.8))
    cast.own_camera = True
    return [{"t": 0.2, "sfx": "drumroll"}, {"t": t_go, "sfx": "whistle"}, {"t": t_go + 0.1, "sfx": "whoosh"},
            {"t": t_end, "sfx": "success"}]


def a_jump(cast, dur, args):
    """Drive up a ramp, fly through the air with a spin of stars, land with a bounce."""
    v = cast[args["who"]]
    ramp_m = toy.plastic("ramp", (1.0, 0.55, 0.05), rough=0.35)
    rx = args.get("ramp_x", 0.0)
    r = kit.box("ramp", (rx, 0, 0.35), (3.0, 2.4, 0.18), ramp_m, 0.05, rot=(0, math.radians(-14), 0))
    kit.box("ramp_leg", (rx + 1.2, 0, 0.35), (0.3, 2.2, 0.7), ramp_m, 0.05)
    t_up, t_off, t_land = 1.2, 1.6, 2.6
    x_off, x_land = rx + 1.4, rx + 7.0
    place(v, 0, x=rx - 10, z=0)
    k_loc(v.root, t_up, (rx - 1.4, 0, 0))
    k_loc(v.root, t_off, (x_off, 0, 0.75))
    for j in range(1, 5):                         # the flight arc
        u = j / 5
        k_loc(v.root, t_off + (t_land - t_off) * u, (x_off + (x_land - x_off) * u, 0, 0.75 + 2.4 * math.sin(math.pi * u) - 0.75 * u))
    k_loc(v.root, t_land, (x_land, 0, 0))
    kit.roll_wheels(v, F(0), F(t_land), x_land - rx + 10)
    yaw = v.root.rotation_euler.z
    for t, pitch in ((t_up, 0), (t_off, -14), ((t_off + t_land) / 2, 0), (t_land - 0.1, 10), (t_land + 0.15, 0)):
        k_rot(v.root, t, (0, math.radians(pitch), yaw))
    hop(v.root, t_land + 0.25, 0.25)
    hop(v.root, t_land + 0.8, 0.12)
    look(v, 0, -4, 0)
    look(v, t_off, -22, -10)                      # wide eyes up in the air
    look(v, t_land + 0.4, -6, -18)
    confetti((x_land - 1.5, 0, 2.6), (t_off + t_land) / 2, n=30, seed=11)
    return [{"t": 0.1, "sfx": "whoosh"}, {"t": t_off, "sfx": "boing"}, {"t": (t_off + t_land) / 2, "sfx": "sparkle"},
            {"t": t_land, "sfx": "burst"}, {"t": t_land + 0.3, "sfx": "success"}]


def a_flat(cast, dur, args):
    """A tyre pops and goes flat; the helper (optional) pumps it back up. args: who, helper."""
    v = cast[args["who"]]
    w = sorted(v.wheels, key=lambda o: (-o.location.x, o.location.y))[0]     # the front wheel nearest the camera
    t_pop = 1.0
    k_scale(w, t_pop - 0.05, 1)
    k_scale(w, t_pop + 0.15, (1, 1, 0.55))
    yaw = v.root.rotation_euler.z
    k_rot(v.root, t_pop, (0, 0, yaw))
    k_rot(v.root, t_pop + 0.2, (math.radians(-4), math.radians(5), yaw))   # it sags onto the flat corner
    look(v, 0, -6, -18)
    look(v, t_pop + 0.2, 16, -6)
    ev = [{"t": t_pop, "sfx": "burst"}]
    h = cast.get(args.get("helper"))
    if h is not None:
        t_fix0, t_fix1 = max(3.0, dur - 3.0), max(4.2, dur - 1.6)
        puff = kit.mat("puff", (0.95, 0.97, 1.0), rough=0.2)
        wp = w.matrix_world.translation
        for k in range(6):                        # pump puffs
            p = kit.sphere("puff", (wp.x, wp.y - 0.4, wp.z + 0.1), 0.12, puff)
            tk = t_fix0 + k * (t_fix1 - t_fix0) / 6
            k_scale(p, 0, 0)
            k_scale(p, tk, 0)
            k_scale(p, tk + 0.1, 1)
            k_loc(p, tk, tuple(p.location))
            k_loc(p, tk + 0.45, (wp.x, wp.y - 0.9, wp.z + 0.6))
            k_scale(p, tk + 0.45, 0)
        k_scale(w, t_fix0, (1, 1, 0.55))
        k_scale(w, t_fix1, 1)
        k_rot(v.root, t_fix1 - 0.2, (math.radians(-4), math.radians(5), yaw))
        k_rot(v.root, t_fix1, (0, 0, yaw))
        look(h, 0, 6, 0)
        look(v, t_fix1 + 0.1, -8, -18)
        hop(v.root, t_fix1 + 0.2, 0.3)
        ev += [{"t": t_fix0, "sfx": "chuff"}, {"t": (t_fix0 + t_fix1) / 2, "sfx": "chuff"}, {"t": t_fix1, "sfx": "success"}]
    return ev


def a_hide(cast, dur, args):
    """Hide and seek: one toy hides behind a big bush, the seeker looks left and right, the hider pops out."""
    v, s_ = cast[args["who"]], cast[args["seeker"]]
    leaf = kit.ramp_mat("bush", (0.10, 0.45, 0.04), (0.35, 0.78, 0.10), rough=0.5, kind="instance")
    bx = args.get("bush_x", 1.0)
    for dx, dy, r in ((0, 0, 1.25), (-0.9, 0.2, 0.95), (0.95, 0.15, 1.0), (0.1, 0.5, 1.1)):
        kit.sphere("bush", (bx + dx, 2.2 + dy, r * 0.75), r, leaf)
    place(v, 0, x=bx, y=3.4, z=0)
    t_peek, t_out = dur * 0.45, dur - 1.6
    k_loc(v.root, t_out - 0.2, (bx, 3.4, 0))
    k_loc(v.root, t_out + 0.35, (bx + 0.2, 1.6, 0.45))     # bursts out over the bush edge
    k_loc(v.root, t_out + 0.7, (bx + 0.3, 0.6, 0))
    hop(v.root, t_out + 0.9, 0.3)
    for k, yaw in enumerate((-35, 35, -35, 0)):
        look(s_, 0.6 + k * 0.7, -4, yaw)                     # the seeker looks around
    look(s_, t_out + 0.35, -20, 20)
    hop(s_.root, t_out + 0.45, 0.25)
    look(v, t_out + 0.5, -6, -18)
    return [{"t": t_peek, "sfx": "drumroll"}, {"t": t_out + 0.3, "sfx": "pop"}, {"t": t_out + 0.5, "sfx": "boing"}]


ACTIONS = {"idle": a_idle, "race": a_race, "jump": a_jump, "flat": a_flat, "hide": a_hide, "drive_in": a_drive_in, "spot": a_spot, "stuck": a_stuck, "tow": a_tow,
           "wash": a_wash, "dance": a_dance}
MIN_DUR = {"idle": 2.0, "drive_in": 3.2, "spot": 3.0, "stuck": 4.5, "tow": 6.0, "wash": 5.5, "dance": 4.0,
           "race": 6.0, "jump": 5.0, "flat": 6.5, "hide": 6.0}


# ================================================================ camera
def camera(cast, spec):
    c = spec.get("camera", {})
    aim = c.get("aim")
    if isinstance(aim, str):
        p = home(cast[aim])
        aim = (p[0], p[1], 0.9)
    elif aim is None:                              # frame the whole cast
        xs = [home(v)[0] for v in cast.values()]
        aim = ((min(xs) + max(xs)) / 2, 0, 0.9)
    dist, h, side = c.get("dist", 9.0), c.get("height", 2.3), math.radians(c.get("side", 45))   # 45: faces, not profiles
    push, pan, dur = c.get("push", 0.12), c.get("pan", 0.0), spec["dur"]
    lens = c["lens"] if "lens" in c else 45 * templates.FILL     # a lens set in the story is a hand-tuned frame: kept
    xs = [home(v)[0] for v in cast.values()]
    if len(xs) > 1:                                # bigger toys, but the whole cast stays in frame, even after the push
        need = (max(xs) - min(xs) + 3.6) / max(0.5, math.cos(side))
        dist = max(dist, need * lens / 36 / (1 - push))

    def at(d, dx):
        return ((aim[0] + dx + math.sin(side) * d, aim[1] - math.cos(side) * d, aim[2] + h * d / dist),
                (aim[0] + dx, aim[1], aim[2]))
    cam, tgt = kit.camera(at(dist, 0)[0], aim, lens=lens)
    for t, d, dx in ((0, dist, 0), (dur, dist * (1 - push), pan)):
        cl, al = at(d, dx)
        k_loc(cam, t, cl)
        k_loc(tgt, t, al)
    return cam


def template_shot(spec):
    """A colour-song scene (egg, pour, garage, portal, wheels, convoy) used as a story shot: same animation and camera,
    the toy talks with its lines. args: {"name": "egg", "colour": "red", "kind": "car", "from": "blue", "who": "zip"}."""
    from toycolors import templates
    a = spec["args"]
    info = templates.TEMPLATES[a["name"]](colour=a["colour"], kind=a["kind"], from_colour=a.get("from"))
    sc = bpy.context.scene
    sc.camera.data.lens *= info.get("zoom", 1.0) * templates.FILL
    toy.playground(slides=info.get("slides", True), size=info.get("platform", (34, 20)))
    hero = bpy.data.objects.get("hero") or bpy.data.objects.get("convoy0")
    if hero is not None:
        class _V:
            root = hero
        for words in (spec.get("talk") or {}).values():
            talk(_V, words)
    return [dict(e) for e in info.get("events", [])]


def build_shot(spec):
    if spec["action"] == "template":
        return template_shot(spec)
    build_set(spec.get("set", "mud"))
    cast = build_cast(spec)
    idle(cast, spec["dur"], seed=len(spec.get("action", "")))
    ev = ACTIONS[spec["action"]](cast, spec["dur"], spec.get("args", {}))
    for who, words in (spec.get("talk") or {}).items():
        if who in cast:
            talk(cast[who], words)
    if not cast.own_camera:
        camera(cast, spec)
    return ev
