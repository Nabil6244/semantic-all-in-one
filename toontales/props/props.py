"""Toon Tales props (Blender, procedural): any story prop from the plan, built under one empty so it can
stand on a set spot, hang on a wall, or follow a character's hand.

Library: root = props.build({"type": "sign", "image": ".../sign_x.png", "pos": [x, y, z], "wall": "r"|"l"|None})
Text props show their artwork (made by text_art.py outside Blender) on a front-facing plane.
Sizes are real-world-ish metres; held props are built small so they fit a hand.
"""
import math
import random

import bpy
from mathutils import Vector

from sets.mine import _box, mat_flat, mat_rock, mat_wood  # shared stylised materials

BOOST = {"bottle": 2.2, "letter": 1.9, "coins": 2.0, "gold": 1.9, "money": 2.1, "map": 1.6, "label": 1.8,
         "rock": 1.7, "tool": 1.3, "sack": 1.2, "newspaper": 1.4, "dynamite": 1.6, "gun": 1.5}
HELD_SCALE = 0.55


def _empty(name, pos):
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.location = Vector(pos)
    return e


def _own(parent, objs):
    bpy.context.view_layer.update()
    for o in objs:
        o.parent = parent
        o.matrix_parent_inverse = parent.matrix_world.inverted()
    return parent


def _active():
    return bpy.context.active_object


def _picture(name, image, w, h, loc, mat_name=None):
    """Front-facing (-Y) plane showing a picture, slightly emissive so text always reads."""
    img = bpy.data.images.load(str(image), check_existing=True)
    m = bpy.data.materials.new(mat_name or f"TT_pic_{name}")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.35
    bsdf.inputs["Roughness"].default_value = 0.9
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=(math.pi / 2, 0, 0))
    o = _active()
    o.name = name
    o.scale = (w, h, 1)
    o.data.materials.append(m)
    return o


def _nuggets(name, pos, n, r, mat, rnd, spread=0.12, flat=1.0):
    out = []
    for i in range(n):
        p = Vector(pos) + Vector((rnd.uniform(-spread, spread), rnd.uniform(-spread * 0.6, spread * 0.6),
                                  rnd.uniform(0, spread * 0.5)))
        rr = r * rnd.uniform(0.6, 1.2)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=rr, location=(p.x, p.y, p.z + rr * 0.6))
        o = _active()
        o.name = f"{name}_{i}"
        o.scale = (1.0, rnd.uniform(0.7, 1.1), rnd.uniform(0.6, 0.9) * flat)
        o.rotation_euler = (rnd.uniform(0, 3), rnd.uniform(0, 3), rnd.uniform(0, 3))
        o.data.materials.append(mat)
        out.append(o)
    return out


def build(spec, idx=0):
    t = spec["type"]
    rnd = random.Random(f"{t}{idx}")
    pos = Vector(spec.get("pos", (0, 0, 0)))
    root = _empty(f"PROP_{idx}_{t}", pos)
    held = bool(spec.get("held_by") or spec.get("picked_by"))
    on_wall = spec.get("wall")
    gold = mat_flat("TT_p_gold", (240, 186, 60), rough=0.28, metal=1.0, emit=(255, 196, 70), emit_k=0.4)
    wood = mat_wood("TT_p_wood")
    objs = []
    O = (0, 0, 0)
    if t == "gold":
        objs = _nuggets("gold", O, 7 if not held else 4, 0.05 if not held else 0.085, gold, rnd,
                        spread=0.12 if not held else 0.05)
    elif t == "rock":
        brass = mat_flat("TT_p_pyrite", (196, 168, 88), rough=0.35, metal=0.85)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.09, location=(0, 0, 0.07))
        o = _active()
        o.scale = (1.2, 1.0, 0.85)
        o.data.materials.append(brass)
        objs = [o] + _nuggets("rockbits", O, 3, 0.03, brass, rnd, spread=0.08)
    elif t == "sack":
        burlap = mat_rock("TT_p_burlap", (176, 146, 100), (150, 120, 80), scale=40, bump=0.2)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, location=(0, 0, 0.2))
        o = _active()
        o.scale = (1.0, 0.85, 1.05)
        for v in o.data.vertices:
            if v.co.z > 0.12:
                k = (v.co.z - 0.12) / 0.1
                v.co.x *= max(0.25, 1 - k * 0.7)
                v.co.y *= max(0.25, 1 - k * 0.7)
        o.data.materials.append(burlap)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.06, minor_radius=0.012, location=(0, 0, 0.36))
        tie = _active()
        tie.data.materials.append(mat_flat("TT_p_rope", (120, 84, 50)))
        objs = [o, tie]
        if spec.get("text"):
            objs.append(_picture("sack_label", spec["image"], 0.2, 0.12, (0, -0.2, 0.2)))
    elif t == "coins":
        for s in range(3):
            for k in range(rnd.randint(4, 8)):
                bpy.ops.mesh.primitive_cylinder_add(radius=0.035, depth=0.009,
                                                    location=(s * 0.08 - 0.08 + rnd.uniform(-0.004, 0.004),
                                                              rnd.uniform(-0.01, 0.01), 0.005 + k * 0.0095))
                c = _active()
                c.data.materials.append(gold)
                objs.append(c)
    elif t == "money":
        green = mat_flat("TT_p_bills", (120, 160, 110), rough=0.8)
        band = mat_flat("TT_p_band", (230, 220, 190))
        for k in range(3):
            objs.append(_box(f"bills_{k}", (0.16, 0.08, 0.03), (0, 0, 0.015 + k * 0.032), green, bevel=0.003))
            objs.append(_box(f"band_{k}", (0.04, 0.085, 0.034), (0, 0, 0.015 + k * 0.032), band, bevel=0.002))
    elif t == "box":
        objs = [_box("crate", (0.45, 0.45, 0.4), (0, 0, 0.2), wood, bevel=0.015)]
    elif t == "bottle":
        glass = mat_flat("TT_p_glass", (90, 54, 30), rough=0.15)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.045, depth=0.18, location=(0, 0, 0.09))
        b = _active()
        b.data.materials.append(glass)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.016, depth=0.08, location=(0, 0, 0.21))
        n = _active()
        n.data.materials.append(glass)
        objs = [b, n, _picture("bottle_label", spec["image"], 0.085, 0.06, (0, -0.047, 0.09))]
    elif t in ("sign", "board", "newspaper", "label", "letter", "map"):
        w, h = {"sign": (0.9, 0.39), "board": (0.7, 0.48), "newspaper": (0.34, 0.45), "label": (0.2, 0.12),
                "letter": (0.26, 0.34), "map": (0.5, 0.37)}[t]
        if held:
            w, h = w * 0.75, h * 0.75
        z = h / 2 if (held or on_wall) else ({"sign": 1.05, "board": 0.9}.get(t, h / 2 + 0.02))
        pic = _picture(f"{t}_face", spec["image"], w, h, (0, -0.012, z))
        objs = [pic]
        if t in ("sign", "board"):
            objs.append(_box(f"{t}_back", (w + 0.03, 0.02, h + 0.03), (0, 0, z), wood, bevel=0.005))
            if not (held or on_wall):
                for sx in (-1, 1):
                    objs.append(_box(f"{t}_post_{sx}", (0.05, 0.05, z + h / 2), (sx * w * 0.35, 0.03, (z + h / 2) / 2),
                                     wood, bevel=0.006))
    elif t == "tool":
        objs = [_box("pick_handle", (0.035, 0.035, 0.8), (0, 0, 0.4), wood, bevel=0.006),
                _box("pick_head", (0.04, 0.5, 0.05), (0, 0, 0.8), mat_flat("TT_p_steel", (70, 66, 64), 0.45, 0.8),
                     rot=(math.radians(6), 0, math.radians(90)), bevel=0.008)]
    elif t == "gun":
        steel = mat_flat("TT_p_steel", (60, 58, 58), 0.4, 0.8)
        objs = [_box("gun_stock", (0.3, 0.05, 0.08), (-0.25, 0, 0), wood, rot=(0, math.radians(-8), 0), bevel=0.01)]
        bpy.ops.mesh.primitive_cylinder_add(radius=0.013, depth=0.55, location=(0.18, 0, 0.02), rotation=(0, math.pi / 2, 0))
        objs.append(_active())
        objs[-1].data.materials.append(steel)
    elif t == "dynamite":
        red = mat_flat("TT_p_dyn", (190, 46, 40), rough=0.7)
        for k, (x, y) in enumerate(((-0.03, 0), (0.03, 0), (0, 0.03))):
            bpy.ops.mesh.primitive_cylinder_add(radius=0.026, depth=0.2, location=(x, y, 0.1))
            objs.append(_active())
            objs[-1].data.materials.append(red)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.004, depth=0.12, location=(0, 0, 0.25))
        objs.append(_active())
        objs[-1].data.materials.append(mat_flat("TT_p_fuse", (60, 50, 40)))
    else:
        objs = [_box(f"prop_{t}", (0.2, 0.2, 0.2), (0, 0, 0.1), wood)]
    for o in objs:
        o.location += pos
    _own(root, objs)
    if on_wall:  # turn to face out of the wall, a little toward the camera
        root.rotation_euler = (0, 0, math.radians(-62 if on_wall == "r" else 62))
    k = BOOST.get(t, 1.0)  # story props are drawn big so a phone viewer reads them at a glance
    if held and t not in ("gold", "rock", "coins"):  # small things stay readable at full size
        k *= HELD_SCALE
    root.scale = (k,) * 3
    return root
