"""Scene templates for Toy Vehicles Colours. Each builds one 16-beat verse (8.57 s at 112 bpm) in an empty scene:
set, vehicle(s), animation and camera. Times are seconds from the verse start; F() turns them into frames.

    from toycolors import templates
    info = templates.TEMPLATES["egg"](colour="red", kind="car")
    info -> {"dur": s, "events": [{"t", "sfx"}], "world": ...}

pour     plain white vehicle drives under a hanging bucket; paint flows down its body from the roof
egg      polka-dot surprise egg with a face wobbles, cracks, the vehicle pops out
garage   row of five coloured garages; one door rolls up and its vehicle drives out
portal   vehicle drives through a magic ring on a road and comes out in the new colour
wheels   old wheels pop off, new wheels in the colour roll in and snap on
convoy   four vehicles in one colour drive past in a line on a road
"""
import math
import random

import bpy
from mathutils import Vector

from toycolors import kit, toy
from toycolors import timeline as T
from toycolors.template_events import EGG_CRACK, EVENTS, WHEELS_OFF, WHEELS_ON

DUR = 16 * T.BEAT                       # 8.57 s
COLOURS = dict(T.COLOURS)
WHITE = (0.92, 0.92, 0.94)


def F(t):
    return int(round(t * T.FPS)) + 1


def k_loc(ob, t, xyz, index=-1):
    ob.location = xyz
    ob.keyframe_insert("location", frame=F(t), index=index)


def k_rot(ob, t, xyz):
    ob.rotation_euler = xyz
    ob.keyframe_insert("rotation_euler", frame=F(t))


def k_scale(ob, t, s):
    ob.scale = (s, s, s) if isinstance(s, (int, float)) else s
    ob.keyframe_insert("scale", frame=F(t))


def look(v, t, pitch=0.0, yaw=0.0):
    for lk in v.looks:
        k_rot(lk, t, (math.radians(pitch), math.radians(yaw), 0))


def hop(ob, t, h=0.2, base=0.0):
    for dt, z in [(0, base), (0.15, base + h), (0.38, base)]:
        k_loc(ob, t + dt, (ob.location.x, ob.location.y, z), index=2)


def drive(v, t0, t1, p0, p1, z=0.0):
    k_loc(v.root, t0, (*p0, z))
    k_loc(v.root, t1, (*p1, z))
    kit.roll_wheels(v, F(t0), F(t1), (Vector(p1) - Vector(p0)).length)


def shots(cam, aim, keys):
    for t, cl, al in keys:
        k_loc(cam, t, cl)
        k_loc(aim, t, al)


def confetti(center, t, n=40, seed=1, colours=None):
    rng = random.Random(seed)
    cols = colours or [c for _, c in T.COLOURS]
    for i in range(n):
        m = kit.mat(f"confetti{i % len(cols)}", cols[i % len(cols)], rough=0.3)
        p = kit.box("confetti", center, (0.12, 0.12, 0.02), m, 0.0)
        p.scale = (0, 0, 0)
        k_scale(p, t - 0.1, 0)
        k_scale(p, t, 1)
        vx, vy, vz = rng.uniform(-3, 3), rng.uniform(-2.5, 1.0), rng.uniform(3.5, 6.5)
        for k in range(1, 9):                       # a ballistic arc in 8 steps
            dt = k * 0.2
            k_loc(p, t + dt, (center[0] + vx * dt, center[1] + vy * dt, max(0.02, center[2] + vz * dt - 4.9 * dt * dt)))
        k_rot(p, t, (0, 0, 0))
        k_rot(p, t + 1.6, (rng.uniform(-12, 12), rng.uniform(-12, 12), rng.uniform(-6, 6)))
        k_scale(p, t + 2.6, 1)
        k_scale(p, t + 3.0, 0)


def blinks(v, times):
    for t in times:
        kit.blink(v, F(t))


# ================================================================ pour
def pour(colour="red", kind="car", **_):
    rgb = COLOURS[colour]
    wood = kit.ramp_mat("wood", (0.56, 0.34, 0.15), (0.68, 0.45, 0.22), scale=5.0, kind="wave", rough=0.6)
    for sx in (-1, 1):
        kit.box("post", (sx * 2.6, 0, 2.0), (0.28, 0.28, 4.0), wood, 0.05)
    kit.box("beam", (0, 0, 4.0), (5.6, 0.32, 0.32), wood, 0.05)
    rope_m = kit.mat("rope", (0.75, 0.62, 0.40), rough=0.9)
    # bucket pivots on its right lip and tips toward +X, so the camera sees its side and the pour
    piv = kit.empty("bucket_pivot", (0.55, 0, 3.15))
    bm = kit.toy_paint("bucket", tuple(min(1, c * 1.05 + 0.05) for c in rgb))
    pm = kit.mat(f"paint_{colour}", rgb, rough=0.1, coat=0.8)
    kit.cyl("bucket", (-0.55, 0, -0.42), 0.55, 0.85, bm, parent=piv, bevel=0.03)
    kit.cyl("bucket_paint", (-0.55, 0, -0.06), 0.5, 0.03, pm, parent=piv)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.55, minor_radius=0.045, location=(-0.55, 0, 0.0))
    rim = bpy.context.object
    rim.data.materials.append(bm)
    rim.parent = piv
    kit.cyl("rope", (0.0, 0, 3.6), 0.025, 0.8, rope_m)
    # car parks under the lip
    v = toy.vehicle(kind, WHITE, loc=(-9, 0, 0), name="hero")
    thr_nodes = [kit.wipe(m, rgb, "Z") for m in v.body_mats]
    top = toy.TOP.get(kind, 1.65)
    drive(v, 0.0, 1.6, (-9, 0), (0.55, 0))
    hop(v.root, 1.6, 0.12)
    look(v, 1.6, 0, 0)
    look(v, 2.0, -28, 0)                      # eyes roll up to the bucket
    blinks(v, [1.1, 4.0, 6.0])
    for t, a in [(1.9, 0), (2.5, 110), (5.2, 110), (5.8, 0)]:
        k_rot(piv, t, (0, math.radians(a), 0))
    # stream from the lip down to the roof, then a splash cap spreading on the roof
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.09, depth=1.0, location=(0, 0, -0.5))
    st = bpy.context.object
    bpy.ops.object.transform_apply(location=True)
    st.location = (0.62, 0, 3.12)
    st.data.materials.append(pm)
    kit._smooth(st)
    L = 3.12 - top
    for t, s in [(2.35, (1, 1, 0)), (2.6, (1, 1, L))] + [(2.6 + k * 0.25, (1 + 0.2 * (k % 2), 1 + 0.2 * (k % 2), L)) for k in range(1, 10)] + \
            [(5.1, (0.4, 0.4, L)), (5.3, (0, 0, L))]:
        k_scale(st, t, s)
    cap = kit.sphere("splash", (0.6, 0, top), 0.35, pm, scale=(0, 0, 0))
    for t, s in [(2.55, (0, 0, 0)), (2.75, (1.4, 1.3, 0.35)), (5.2, (1.6, 1.5, 0.3)), (5.5, (0, 0, 0))]:
        k_scale(cap, t, s)
    # paint front runs down the body: everything above the threshold turns the new colour
    for n in thr_nodes:
        kit.key_value(n, F(2.6), top + 0.4)
        kit.key_value(n, F(5.0), -0.1)
    # drips slide down the sides with the front
    for i in range(6):
        d = kit.sphere("drip", (0.55 + (i - 2.5) * 0.35, (-1 if i % 2 else 1) * 0.62, top), 0.07, pm,
                       scale=(1, 1, 1.6))
        d.scale = (0, 0, 0)
        k_scale(d, 2.7 + i * 0.12, 0)
        k_scale(d, 2.9 + i * 0.12, (1, 1, 1.6))
        k_loc(d, 2.9 + i * 0.12, tuple(d.location))
        k_loc(d, 5.0, (d.location.x, d.location.y, 0.25))
        k_scale(d, 5.2, 0)
    look(v, 5.6, -6, 18)
    hop(v.root, 5.8, 0.28)
    drive(v, 6.6, DUR, (0.55, 0), (12, 0))
    cam, aim = kit.camera((4.6, -8.2, 2.4), (0.4, 0, 1.9), lens=32)
    shots(cam, aim, [(0, (4.6, -9.0, 2.6), (0.0, 0, 2.2)), (2.4, (3.8, -8.4, 2.6), (0.5, 0, 2.3)),
                     (5.6, (3.2, -6.4, 1.9), (0.6, 0, 1.3)), (DUR, (5.0, -6.8, 1.8), (3.0, 0, 1.0))])
    return {"dur": DUR, "zoom": 1.15, "keep_out": [(-3, 3, -0.4, 0.4)],
            "events": EVENTS["pour"]}


# ================================================================ egg
def egg(colour="red", kind="car", **_):
    rgb = COLOURS[colour]
    m = kit.polka_mat(f"egg_{colour}", rgb)
    R, HS, cut = 1.25, 1.3, 0.15
    base = kit.empty("egg", (0, 0, R * HS))
    top, bot = kit.egg_halves((0, 0, 0), R, HS, m, cut)
    top.parent = bot.parent = base
    top.location, bot.location = (0, 0, cut), (0, 0, cut)
    looks, lids = kit.face(top, (0, -R * 0.93, R * 0.55 - cut), (0, -1, 0.25), 0.3, smile_at=True, lid_m=m)

    class _Egg:                                  # lets blink() treat the egg like a vehicle
        pass
    e = _Egg()
    e.looks, e.lids = looks, lids
    k_scale(base, 0.0, 0)
    k_scale(base, 0.3, 1.12)
    k_scale(base, 0.45, 1.0)
    for i in range(6):                           # wobble on the beat
        k_rot(base, 0.5 + i * T.BEAT, (0, math.radians(9 if i % 2 else -9), 0))
    k_rot(base, 0.5 + 6 * T.BEAT, (0, 0, 0))
    blinks(e, [0.9, 2.2])
    tc = EGG_CRACK                               # crack
    k_loc(top, tc, (0, 0, cut))
    k_rot(top, tc, (0, 0, 0))
    k_loc(top, tc + 0.9, (1.6, 3.5, 4.2))
    k_rot(top, tc + 0.9, (math.radians(-110), math.radians(40), 0))
    k_scale(top, tc + 0.7, 1)
    k_scale(top, tc + 1.0, 0)
    k_scale(bot, tc + 0.4, 1)
    k_scale(bot, tc + 0.9, 0)
    v = toy.vehicle(kind, rgb, loc=(0, 0, 0.0), name="hero", yaw=math.radians(-90))
    sc = 1.0 if kind != "monster" else 0.85
    k_scale(v.root, tc - 0.1, 0)
    k_scale(v.root, tc + 0.3, sc * 1.15)
    k_scale(v.root, tc + 0.5, sc)
    k_loc(v.root, tc, (0, 0, 0.6))
    k_loc(v.root, tc + 0.35, (0, 0, 0.9))
    k_loc(v.root, tc + 0.7, (0, 0, 0))
    look(v, tc + 0.6, -8, 0)
    blinks(v, [tc + 1.3, tc + 3.2])
    hop(v.root, tc + 2.0, 0.3)
    confetti((0, 0, 1.6), tc, seed=3)
    cam, aim = kit.camera((0, -9.0, 2.6), (0, 0, 1.5), lens=34)
    shots(cam, aim, [(0, (0.3, -9.5, 2.6), (0, 0, 1.6)), (tc, (0.2, -8.0, 2.3), (0, 0, 1.4)),
                     (DUR, (-0.6, -6.2, 1.7), (0, 0, 0.9))])
    return {"dur": DUR, "zoom": 1.55, "keep_out": [],
            "events": EVENTS["egg"]}


# ================================================================ garage
def garage(colour="red", kind="car", **_):
    names = [n for n, _ in T.COLOURS]
    idx = names.index(colour)
    wall = kit.mat("garage_wall", (0.96, 0.90, 0.72), rough=0.6)
    dark = kit.mat("garage_dark", (0.03, 0.03, 0.04), rough=0.9)
    trim = kit.mat("garage_trim", (0.98, 0.98, 0.98), rough=0.4)
    W, D, H = 3.0, 4.0, 3.4
    door = H - 0.95                      # the arched roof band sits above the door
    xs = [(i - 2) * (W + 0.3) for i in range(5)]
    shutter = None
    for i, (n, c) in enumerate(T.COLOURS):
        x = xs[i]
        for sx in (-1, 1):
            kit.box("garage_side", (x + sx * (W / 2 - 0.15), 3.0, H / 2), (0.3, D, H), wall, 0.05)
        kit.box("garage_back", (x, 3.0 + D / 2 - 0.1, H / 2), (W, 0.2, H), wall, 0.05)
        kit.box("garage_back_dark", (x, 3.0 + D / 2 - 0.25, H / 2), (W - 0.6, 0.06, H), dark, 0.0)
        kit.box("garage_ceiling", (x, 3.0, door + 0.03), (W - 0.6, D, 0.06), dark, 0.0)
        roof = kit.cyl("garage_roof", (x, 3.0, H), W / 2 + 0.1, D + 0.2, kit.toy_paint(f"roof_{n}", c), verts=48,
                       rot=(math.pi / 2, 0, 0), bevel=0.06)
        roof.scale = (1, 0.55, 1)
        kit.box("garage_lintel", (x, 3.0 - D / 2 - 0.22, door + 0.08), (W, 0.14, 0.16), trim, 0.03)
        kit.box("garage_facade", (x, 3.0 - D / 2 - 0.16, (door + H) / 2), (W + 0.1, 0.1, H - door), wall, 0.04)
        # shutter door: origin at the top, scale Z to roll it up
        sp = kit.empty(f"shutter_{n}", (x, 3.0 - D / 2, door))
        sm = kit.toy_paint(f"shutter_{n}", c)
        for k in range(8):
            kit.box("slat", (0, 0, -(k + 0.5) * door / 8), (W - 0.6, 0.08, door / 8 * 0.9), sm, 0.03,
                    parent=sp)
        kit.sphere("door_light", (x, 3.0 - D / 2 - 0.12, door + 0.45), 0.16, kit.mat(f"lamp_{n}", c, 0.2, emit=2.5),
                   scale=(1, 0.5, 1))
        if i == idx:
            shutter = sp
    kit.box("garage_floor", (0, 1.2, 0.01), (5 * (W + 0.3), 2.4, 0.02), kit.mat("concrete", (0.72, 0.72, 0.72), 0.8),
            0.0)
    x = xs[idx]
    for t, s in [(1.6, 1.0), (2.8, 0.06)]:
        k_scale(shutter, t, (1, 1, s))
    v = toy.vehicle(kind, COLOURS[colour], loc=(x, 3.4, 0), yaw=math.radians(-90), name="hero")
    sc = 1.0 if kind != "monster" else 0.8
    v.root.scale = (sc, sc, sc)
    look(v, 0, 0, 0)
    look(v, 2.9, -6, 0)
    blinks(v, [3.2, 6.5])
    drive(v, 3.2, 5.0, (x, 3.4), (x, -1.6))
    hop(v.root, 5.0, 0.2)
    k_rot(v.root, 5.2, (0, 0, math.radians(-90)))
    k_rot(v.root, 5.8, (0, 0, math.radians(-60)))
    cam, aim = kit.camera((0, -13, 3.4), (0, 2.5, 1.4), lens=28)
    shots(cam, aim, [(0, (0, -14, 3.6), (0, 2.5, 1.4)), (1.5, (x * 0.6, -9.5, 2.6), (x, 2.0, 1.3)),
                     (5.0, (x * 0.8 + 1.2, -7.6, 2.0), (x, 0.0, 1.0)), (DUR, (x * 0.8 + 2.0, -7.0, 1.8), (x, -0.6, 0.9))])
    return {"dur": DUR, "zoom": 1.15, "keep_out": [(-9, 9, 0.0, 5.5)], "slides": False,
            "events": EVENTS["garage"]}


# ================================================================ portal
def portal(colour="red", kind="car", from_colour=None, **_):
    rgb = COLOURS[colour]
    old = COLOURS[from_colour] if from_colour else WHITE
    kit.road(-20, 20, 0)
    ring = kit.empty("portal", (0, 0, 1.9))
    ring.rotation_euler = (0, math.pi / 2, 0)
    glow = kit.mat(f"portal_{colour}", rgb, rough=0.2, emit=4.0)
    bpy.ops.mesh.primitive_torus_add(major_radius=1.95, minor_radius=0.16, major_segments=64, location=(0, 0, 0))
    tor = bpy.context.object
    tor.data.materials.append(glow)
    tor.parent = ring
    kit._smooth(tor)
    # swirling inside: a thin glowing disc with a spiral pattern, half see-through
    disc = kit.cyl("portal_disc", (0, 0, 0), 1.85, 0.02, _swirl_mat(rgb), verts=64, parent=ring)
    for t, a in [(0, 0), (DUR, 4 * math.pi)]:
        k_rot(disc, t, (0, 0, a))
    spin = kit.empty("sparkles", (0, 0, 0), ring)
    star = kit.mat("star", (1, 0.95, 0.6), rough=0.2, emit=5.0)
    for i in range(10):
        a = 2 * math.pi * i / 10
        kit.sphere("spark", (math.cos(a) * 2.2, math.sin(a) * 2.2, 0), 0.07, star, parent=spin, segs=12)
    for t, a in [(0, 0), (DUR, -6 * math.pi)]:
        k_rot(spin, t, (0, 0, a))
    for s in (0.0,):
        k_scale(ring, 0.0, 0.0)
        k_scale(ring, 0.5, 1.1)
        k_scale(ring, 0.7, 1.0)
    v = toy.vehicle(kind, old, loc=(-12, 0, 0), name="hero")
    for m in v.body_mats:
        kit.key_value(kit.wipe(m, rgb, "X"), F(0), 0.0)     # new colour wherever the body is past the ring
    drive(v, 1.0, 4.4, (-12, 0), (4.5, 0))
    hop(v.root, 4.4, 0.25)
    k_rot(v.root, 4.6, (0, 0, 0))
    k_rot(v.root, 5.2, (0, 0, math.radians(-50)))
    look(v, 4.6, 0, 0)
    look(v, 5.2, -6, 0)
    blinks(v, [2.0, 5.6, 7.4])
    cam, aim = kit.camera((-4, -9, 2.4), (-2, 0, 1.4), lens=30)
    # camera stands past the ring, so the swirl faces it and the vehicle comes out toward it
    shots(cam, aim, [(0, (7.0, -7.5, 2.6), (-2.5, 0, 1.8)), (2.6, (6.5, -7.0, 2.3), (-0.5, 0, 1.5)),
                     (4.6, (8.0, -6.6, 2.0), (3.2, 0, 1.1)), (DUR, (8.4, -5.8, 1.8), (4.2, 0, 1.0))])
    return {"dur": DUR, "zoom": 1.4, "keep_out": [(-20, 20, -1.7, 1.7)], "platform": (44, 22),
            "events": EVENTS["portal"]}


def _swirl_mat(rgb):
    """A clean candy spiral (3 arms) that turns as the disc spins: calm and readable, not noise."""
    m = bpy.data.materials.new("swirl")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    out = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"][0]
    N, L = nt.nodes.new, nt.links.new
    tc = N("ShaderNodeTexCoord")
    sep = N("ShaderNodeSeparateXYZ")
    ang = N("ShaderNodeMath"); ang.operation = "ARCTAN2"
    rad = N("ShaderNodeVectorMath"); rad.operation = "LENGTH"
    arms = N("ShaderNodeMath"); arms.operation = "MULTIPLY"; arms.inputs[1].default_value = 3 / (2 * math.pi)
    twist = N("ShaderNodeMath"); twist.operation = "MULTIPLY"; twist.inputs[1].default_value = 1.3
    add = N("ShaderNodeMath"); add.operation = "ADD"
    fr = N("ShaderNodeMath"); fr.operation = "FRACT"
    ramp = N("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*[min(1, c + 0.55) for c in rgb], 1)
    els[1].position, els[1].color = 0.5, (*[c * 0.55 for c in rgb], 1)
    e3 = els.new(1.0)
    e3.color = els[0].color
    glow = N("ShaderNodeMath"); glow.operation = "SUBTRACT"; glow.inputs[0].default_value = 1.0   # brighter centre
    em = N("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 2.2
    tr = N("ShaderNodeBsdfTransparent")
    mix = N("ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.8
    L(tc.outputs["Object"], sep.inputs[0])
    L(sep.outputs["Y"], ang.inputs[0]); L(sep.outputs["X"], ang.inputs[1])
    L(tc.outputs["Object"], rad.inputs[0])
    L(ang.outputs[0], arms.inputs[0])
    L(rad.outputs["Value"], twist.inputs[0])
    L(arms.outputs[0], add.inputs[0]); L(twist.outputs[0], add.inputs[1])
    L(add.outputs[0], fr.inputs[0])
    L(fr.outputs[0], ramp.inputs["Fac"])
    L(ramp.outputs["Color"], em.inputs["Color"])
    L(tr.outputs[0], mix.inputs[1])
    L(em.outputs[0], mix.inputs[2])
    L(mix.outputs[0], out.inputs["Surface"])
    return m


# ================================================================ wheels
def wheels(colour="red", kind="monster", **_):
    rgb = COLOURS[colour]
    v = toy.vehicle(kind, (0.92, 0.92, 0.94) if kind != "monster" else (0.2, 0.55, 0.95), loc=(0, 0, 0),
                    yaw=math.radians(-30), name="hero", rim=kit.mat(f"rim_{colour}", rgb, rough=0.25, coat=0.6))
    # old grey wheels sit where the new ones go, then pop off
    grey = kit.mat("rim_grey", (0.45, 0.45, 0.48), rough=0.4)
    t_off, t_on = WHEELS_OFF, WHEELS_ON
    homes = []
    for w in v.wheels:
        r = w.get("r", 0.4)
        hw = abs(w.location.y)
        old = toy.toy_wheel("old_wheel", tuple(w.location), r, r * (0.88 if kind == "monster" else 0.85), grey,
                            v.root, monster=(kind == "monster"))
        side = 1 if w.location.y > 0 else -1
        k_loc(old, t_off, tuple(old.location))
        k_loc(old, t_off + 0.35, (old.location.x * 1.4, side * (hw + 1.8), old.location.z + 1.4))
        k_loc(old, t_off + 0.8, (old.location.x * 1.8, side * (hw + 4.0), r))
        k_scale(old, t_off + 0.9, 1)
        k_scale(old, t_off + 1.2, 0)
        k_rot(old, t_off, (0, 0, 0))
        k_rot(old, t_off + 0.8, (math.radians(side * 70), math.radians(200), 0))
        homes.append((w, tuple(w.location), side, hw))
        # new wheel waits far out to the side, hidden
        k_scale(w, 0, 0)
        k_scale(w, t_on - 0.01, 0)
        k_scale(w, t_on, 1)
    body_lift = 0.12
    k_loc(v.root, t_off - 0.1, (0, 0, 0))
    k_loc(v.root, t_off + 0.2, (0, 0, body_lift))     # it bobs up a little with no wheels
    k_loc(v.root, t_on + 0.7, (0, 0, body_lift))
    k_loc(v.root, t_on + 0.9, (0, 0, 0))
    for i, (w, home, side, hw) in enumerate(homes):
        tt = t_on + i * 0.12
        out = (home[0], side * (hw + 3.5), home[2])
        k_loc(w, tt, out)
        k_loc(w, tt + 0.55, (home[0], side * (hw - 0.08), home[2]))
        k_loc(w, tt + 0.7, home)
        k_rot(w, tt, (0, 0, 0))
        k_rot(w, tt + 0.7, (0, math.radians(-540), 0))
    look(v, 0, -6, 0)
    look(v, t_off + 0.2, -6, -25)
    look(v, t_off + 0.9, -6, 25)
    look(v, t_on + 1.0, -8, 0)
    blinks(v, [1.0, t_on + 1.2, 7.0])
    hop(v.root, t_on + 1.6, 0.35)
    hop(v.root, t_on + 2.6, 0.22)
    cam, aim = kit.camera((4.5, -8.5, 2.4), (0, 0, 1.2), lens=32)
    shots(cam, aim, [(0, (4.5, -9.0, 2.6), (0, 0, 1.4)), (t_off, (3.0, -8.4, 2.0), (0, 0, 1.0)),
                     (t_on + 1.5, (2.2, -6.6, 1.7), (0, 0, 1.1)), (DUR, (0.6, -6.2, 1.6), (0, 0, 1.1))])
    return {"dur": DUR, "zoom": 1.55, "keep_out": [],
            "events": EVENTS["wheels"]}


# ================================================================ convoy
def convoy(colour="red", kind="monster", kinds=None, **_):
    """colour "rainbow": five vehicles, one in each colour (a chorus that names every colour)."""
    rainbow = colour == "rainbow"
    rgbs = [c for _, c in T.COLOURS] if rainbow else None
    rgb = rgbs[0] if rainbow else COLOURS[colour]
    others = [k for k in ("monster", "bus", "fire", "dump", "tanker", "crane", "car") if k != kind]
    kinds = kinds or [kind] + others[:4 if rainbow else 3]   # the verse's own vehicle leads the line
    kit.road(-40, 40, 0)
    speed, gap = 3.6, 3.6                           # chibi toys are short: a tight, cheerful line
    vs = []
    for i, k in enumerate(kinds):
        v = toy.vehicle(k, rgbs[i % len(rgbs)] if rainbow else rgb, loc=(0, 0, 0), name=f"convoy{i}")
        x0 = -14 - i * gap
        drive(v, 0, DUR, (x0, 0), (x0 + speed * DUR, 0))
        for b in range(0, 16, 4):                  # each one hops on its own beat
            hop(v.root, (b + i) * T.BEAT, 0.14)
        look(v, 0, -4, -14)
        blinks(v, [1.0 + i * 0.7, 5.0 + i * 0.5])
        vs.append(v)
    lead0 = -14
    cam, aim = kit.camera((0, -9, 2.2), (0, 0, 1.2), lens=30)
    keys = []
    # the camera leads the line and looks back along it, so every face is seen
    for t, ahead in ((0, 9.0), (DUR * 0.5, 7.0), (DUR, 5.5)):
        cx = lead0 + speed * t
        keys.append((t, (cx + ahead, -6.8, 2.1), (cx - 5.0, 0, 1.2)))
    shots(cam, aim, keys)
    return {"dur": DUR, "zoom": 1.8, "keep_out": [(-40, 40, -1.7, 1.7)], "platform": (90, 26),
            "events": EVENTS["convoy"]}


TEMPLATES = {"pour": pour, "egg": egg, "garage": garage, "portal": portal, "wheels": wheels, "convoy": convoy}
