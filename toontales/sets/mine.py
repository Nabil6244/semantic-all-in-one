"""Toon Tales set kit: mine tunnel (procedural, built once per shot inside Blender, no downloads).

The tunnel runs away from camera along +Y. Floor at z=0, walls at x=+-HALF_W, arched roof.
Timber frames every FRAME_STEP metres, cart track on the left, hanging lanterns, a gold vein on the
right wall. build() returns named marks the shot builder places cast and camera on.

Library use (inside Blender):  from sets import mine; marks = mine.build()
"""
import json
import math
import random
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

HALF_W = 1.7
WALL_H = 1.55
ROOF_H = 2.75
Y0, Y1 = -4.0, 16.0
FRAME_STEP = 2.6
TRACK_X = -0.85


def _srgb(c):
    def f(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return (f(c[0]), f(c[1]), f(c[2]), 1.0)


# ---------------------------------------------------------------- materials


def _principled(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    return m, nt, nt.nodes["Principled BSDF"]


def mat_rock(name, c1, c2, scale=3.0, bump=0.35):
    """Two-tone stylised rock: noise picks between two browns, plus a soft bump."""
    m, nt, bsdf = _principled(name)
    L = nt.links
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 3.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    a, b = ramp.color_ramp.elements
    a.position, a.color = 0.42, _srgb(c1)
    b.position, b.color = 0.58, _srgb(c2)
    L.new(noise.outputs["Fac"], ramp.inputs[0])
    L.new(ramp.outputs[0], bsdf.inputs["Base Color"])
    bn = nt.nodes.new("ShaderNodeBump")
    bn.inputs["Strength"].default_value = bump
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = scale * 1.6
    L.new(vor.outputs["Distance"], bn.inputs["Height"])
    L.new(bn.outputs[0], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.95
    return m


def mat_wood(name, c1=(122, 82, 50), c2=(92, 58, 34)):
    m, nt, bsdf = _principled(name)
    L = nt.links
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = 4.0
    wave.inputs["Distortion"].default_value = 1.5
    wave.bands_direction = "X"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    a, b = ramp.color_ramp.elements
    a.position, a.color = 0.3, _srgb(c2)
    b.position, b.color = 0.7, _srgb(c1)
    L.new(wave.outputs["Fac"], ramp.inputs[0])
    L.new(ramp.outputs[0], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    return m


def mat_flat(name, c, rough=0.8, metal=0.0, emit=None, emit_k=0.0):
    m, nt, bsdf = _principled(name)
    bsdf.inputs["Base Color"].default_value = _srgb(c)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit:
        bsdf.inputs["Emission Color"].default_value = _srgb(emit)
        bsdf.inputs["Emission Strength"].default_value = emit_k
    return m


# ---------------------------------------------------------------- geometry


def _box(name, size, loc, mat, rot=(0, 0, 0), bevel=0.015):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        bm = o.modifiers.new("bevel", "BEVEL")
        bm.width = bevel
        bm.segments = 2
    o.data.materials.append(mat)
    return o


def _profile(n_arc=14):
    """Tunnel cross-section from the left floor corner, up the wall, over the arch, down to the right."""
    pts = [(-HALF_W, 0.0), (-HALF_W, WALL_H * 0.5), (-HALF_W, WALL_H)]
    rise = ROOF_H - WALL_H
    for i in range(1, n_arc):
        a = math.pi * i / n_arc
        pts.append((-HALF_W * math.cos(a), WALL_H + rise * math.sin(a)))
    pts += [(HALF_W, WALL_H), (HALF_W, WALL_H * 0.5), (HALF_W, 0.0)]
    return pts


def _tunnel(mat):
    prof = _profile()
    me = bpy.data.meshes.new("mine_tunnel")
    bm = bmesh.new()
    steps = int((Y1 - Y0) / 0.25)
    rows = []
    for j in range(steps + 1):
        y = Y0 + (Y1 - Y0) * j / steps
        rows.append([bm.verts.new((x, y, z)) for x, z in prof])
    for j in range(steps):
        for i in range(len(prof) - 1):
            # winding so normals face into the tunnel
            bm.faces.new((rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("mine_tunnel", me)
    bpy.context.scene.collection.objects.link(o)
    sub = o.modifiers.new("sub", "SUBSURF")
    sub.levels = sub.render_levels = 2
    sub.subdivision_type = "SIMPLE"
    tex = bpy.data.textures.new("mine_rock_disp", "VORONOI")
    tex.noise_scale = 0.55
    d = o.modifiers.new("disp", "DISPLACE")
    d.texture = tex
    d.strength = 0.16
    d.mid_level = 0.5
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def _floor(mat):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=40, y_subdivisions=120, size=1, location=(0, (Y0 + Y1) / 2, 0))
    o = bpy.context.active_object
    o.name = "mine_floor"
    o.scale = (HALF_W * 2 + 0.2, Y1 - Y0, 1)
    bpy.ops.object.transform_apply(scale=True)
    tex = bpy.data.textures.new("mine_floor_disp", "CLOUDS")
    tex.noise_scale = 0.4
    d = o.modifiers.new("disp", "DISPLACE")
    d.texture = tex
    d.strength = 0.04
    d.mid_level = 0.9  # mostly pushes down so feet stay on top
    o.data.materials.append(mat)
    return o


def _frame(y, wood):
    parts = []
    for sx in (-1, 1):
        parts.append(_box(f"mine_post_{y:.1f}_{sx}", (0.2, 0.2, 2.3), (sx * (HALF_W - 0.22), y, 1.15), wood))
        # knee brace
        parts.append(_box(f"mine_brace_{y:.1f}_{sx}", (0.1, 0.12, 0.62), (sx * (HALF_W - 0.42), y, 2.06), wood,
                          rot=(0, sx * math.radians(42), 0)))
    parts.append(_box(f"mine_cap_{y:.1f}", (HALF_W * 2 - 0.1, 0.24, 0.24), (0, y, 2.36), wood))
    return parts


def _track(wood, steel):
    for sx in (-1, 1):
        _box(f"mine_rail_{sx}", (0.05, Y1 - Y0, 0.07), (TRACK_X + sx * 0.32, (Y0 + Y1) / 2, 0.075), steel, bevel=0.01)
    y = Y0 + 0.2
    rnd = random.Random(7)
    while y < Y1:
        _box(f"mine_sleeper_{y:.2f}", (0.95, 0.15, 0.06), (TRACK_X + rnd.uniform(-0.03, 0.03), y, 0.03), wood,
             rot=(0, 0, math.radians(rnd.uniform(-3, 3))), bevel=0.01)
        y += 0.55


def _cart(y, rust, steel):
    c = _box("mine_cart", (0.8, 1.05, 0.55), (TRACK_X, y, 0.55), rust, bevel=0.03)
    # taper: shrink the bottom
    for v in c.data.vertices:
        if v.co.z < 0.55:
            v.co.x *= 0.82
            v.co.y = (v.co.y - y) * 0.86 + y
    _box("mine_cart_rim", (0.86, 1.1, 0.05), (TRACK_X, y, 0.84), steel, bevel=0.01)
    # ore heap
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.36, location=(TRACK_X, y, 0.82))
    heap = bpy.context.active_object
    heap.name = "mine_cart_ore"
    heap.scale = (1.0, 1.35, 0.42)
    heap.data.materials.append(mat_rock("TT_ore", (70, 60, 56), (104, 92, 84), scale=9, bump=0.8))
    for sx in (-1, 1):
        for sy in (-1, 1):
            bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=0.06, location=(TRACK_X + sx * 0.32, y + sy * 0.32, 0.14),
                                                rotation=(0, math.pi / 2, 0))
            bpy.context.active_object.data.materials.append(steel)


def _lantern(loc, glass, steel, energy=55):
    x, y, z = loc
    # cap + wire sit right above the bulb: no shadows from them or they paint a blot on the roof
    _box(f"mine_lamp_top_{y:.1f}", (0.14, 0.14, 0.04), (x, y, z + 0.13), steel, bevel=0.01).visible_shadow = False
    bpy.ops.mesh.primitive_cylinder_add(radius=0.006, depth=2.36 - (z + 0.15) - 0.12, location=(x, y, (2.36 - 0.12 + z + 0.15) / 2))
    bpy.context.active_object.data.materials.append(steel)
    bpy.context.active_object.visible_shadow = False
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.075, location=(x, y, z))
    g = bpy.context.active_object
    g.name = f"mine_lamp_glass_{y:.1f}"
    g.scale = (1, 1, 1.3)
    g.data.materials.append(glass)
    g.visible_shadow = False
    bpy.ops.object.light_add(type="POINT", location=(x, y, z - 0.02))
    li = bpy.context.active_object
    li.name = f"mine_lamp_light_{y:.1f}"
    li.data.energy = energy
    li.data.color = (1.0, 0.68, 0.36)
    li.data.shadow_soft_size = 0.06
    li.data.use_shadow = y < 7  # far lamps only glow; keeps the Eevee shadow pool small
    return li


def _gold_vein(gold, rnd):
    """Jagged band of nuggets on the right wall, slightly proud of the rock so they catch the light."""
    pts = [(-0.85, 0.95), (-0.45, 1.25), (-0.1, 1.15), (0.25, 1.55), (0.6, 1.45), (0.95, 1.8)]
    made = 0
    for (y0, z0), (y1, z1) in zip(pts, pts[1:]):
        for k in range(9):
            t = k / 9
            y = y0 + (y1 - y0) * t + rnd.uniform(-0.05, 0.05)
            z = z0 + (z1 - z0) * t + rnd.uniform(-0.09, 0.09)
            r = rnd.uniform(0.035, 0.075)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=r, location=(HALF_W - 0.13, y, z))
            n = bpy.context.active_object
            n.name = f"mine_gold_{made}"
            n.scale = (0.55, 1.0, rnd.uniform(0.6, 1.0))
            n.rotation_euler = (rnd.uniform(0, 3), rnd.uniform(0, 3), rnd.uniform(0, 3))
            n.data.materials.append(gold)
            made += 1
    bpy.ops.object.light_add(type="POINT", location=(HALF_W - 0.6, 0.5, 1.45))
    gl = bpy.context.active_object
    gl.location.y = 0.05
    gl.name = "mine_gold_glow"
    gl.data.energy = 12
    gl.data.color = (1.0, 0.82, 0.35)
    gl.data.shadow_soft_size = 0.3
    gl.data.use_shadow = False
    return Vector((HALF_W - 0.13, 0.05, 1.4))


def _rocks(rock, rnd):
    for i in range(14):
        sx = rnd.choice((-1, 1))
        x = sx * rnd.uniform(HALF_W - 0.55, HALF_W - 0.2)
        y = rnd.uniform(-1.5, 12)
        r = rnd.uniform(0.07, 0.2)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=r, location=(x, y, r * 0.45))
        o = bpy.context.active_object
        o.name = f"mine_rock_{i}"
        o.scale = (1.0, rnd.uniform(0.8, 1.3), rnd.uniform(0.5, 0.8))
        o.data.materials.append(rock)


def _pickaxe(wood, steel, loc=(-HALF_W + 0.22, 1.9)):
    x, y = loc
    tilt = math.radians(14)
    _box("mine_pick_handle", (0.045, 0.045, 1.0), (x + 0.12, y, 0.5), wood, rot=(0, -tilt, 0), bevel=0.008)
    top = Vector((x + 0.12, y, 0.5)) + Vector((-math.sin(tilt) * 0.5, 0, math.cos(tilt) * 0.5))
    _box("mine_pick_head", (0.05, 0.62, 0.06), (top.x, top.y, top.z - 0.02), steel, rot=(math.radians(8), 0, 0), bevel=0.01)


def _crate(wood, loc):
    _box("mine_crate", (0.55, 0.55, 0.5), (loc[0], loc[1], 0.25), wood, rot=(0, 0, math.radians(12)), bevel=0.02)
    _box("mine_crate_lid", (0.6, 0.6, 0.05), (loc[0], loc[1], 0.52), wood, rot=(0, 0, math.radians(18)), bevel=0.01)


# ---------------------------------------------------------------- build


def build(seed=3):
    rnd = random.Random(seed)
    sc = bpy.context.scene
    world = sc.world or bpy.data.worlds.new("W")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = _srgb((30, 20, 16))
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.35

    rock = mat_rock("TT_mine_rock", (96, 66, 46), (134, 96, 66))
    dirt = mat_rock("TT_mine_dirt", (124, 92, 64), (150, 114, 80), scale=5, bump=0.2)
    wood = mat_wood("TT_mine_wood")
    dark_wood = mat_wood("TT_mine_wood_dark", (88, 58, 38), (64, 42, 28))
    steel = mat_flat("TT_mine_steel", (70, 66, 64), rough=0.45, metal=0.8)
    rust = mat_flat("TT_mine_rust", (120, 62, 40), rough=0.75, metal=0.3)
    glass = mat_flat("TT_mine_glass", (255, 210, 140), emit=(255, 196, 120), emit_k=9.0)
    gold = mat_flat("TT_mine_gold", (240, 186, 60), rough=0.28, metal=1.0, emit=(255, 196, 70), emit_k=0.6)

    _tunnel(rock)
    _floor(dirt)
    lamps = []
    y = 1.3
    while y < Y1 - 1:
        _frame(y, wood)
        lamps.append(_lantern((0.0, y - 0.05, 1.95), glass, steel, energy=55 if y < 6 else 35))
        y += FRAME_STEP
    _frame(-1.3, wood)
    _track(dark_wood, steel)
    _cart(4.6, rust, steel)
    vein = _gold_vein(gold, rnd)
    _rocks(rock, rnd)
    _pickaxe(wood, steel)
    _crate(dark_wood, (HALF_W - 0.55, 3.4))

    # key light from camera-left above (casts the puppet shadows), weak cool bounce from the right
    bpy.ops.object.light_add(type="AREA", location=(-1.1, -2.6, 2.4))
    key = bpy.context.active_object
    key.name = "mine_key"
    key.data.energy = 220
    key.data.size = 0.9
    key.data.color = (1.0, 0.8, 0.58)
    key.rotation_euler = (math.radians(62), 0, math.radians(-24))
    bpy.ops.object.light_add(type="AREA", location=(1.3, -1.8, 1.4))
    bounce = bpy.context.active_object
    bounce.name = "mine_bounce"
    bounce.data.energy = 35
    bounce.data.size = 1.5
    bounce.data.color = (0.75, 0.82, 1.0)
    bounce.rotation_euler = (math.radians(75), 0, math.radians(40))
    bounce.data.use_shadow = False

    kit = json.loads((Path(__file__).resolve().parent / "kits.json").read_text())["kits"]["mine"]
    return {
        "cast": {k: tuple(v) for k, v in kit["marks"].items()},   # floor spots (x, y)
        "props": kit["props"], "spots": kit["spots"],
        "vein": tuple(vein),
        "deep": (0.0, 9.0, 1.2),
        "lamps": [tuple(l.location) for l in lamps],
    }
