"""Toon Tales set kit: painted backdrop stage (one Flow picture per story place, built inside Blender).

A portrait painting (9:16) is wrapped on a curved stage: the lower part of the picture lies on the floor
the puppets stand on, the rest bends up into a tall back wall, so the painted ground runs straight into
the painted scenery. Puppets keep real light and shadows; the camera keeps its real moves and depth.

Geometry (metres): floor z=0 from y=FLOOR_Y0 to y=CURVE_Y, a quarter-circle of radius R, then a vertical
wall at y=CURVE_Y+R up to WALL_TOP. Width WIDTH centred on x=0. The picture spans the whole surface
(arc length = WIDTH * 16/9), its bottom edge at y=PAINT_Y0; the floor in front of that repeats the
picture's bottom row (only seen in low, wide shots).

Library use (inside Blender):  from sets import backdrop; marks = backdrop.build("/path/place.png")
"""
import json
import math
from pathlib import Path

import bpy

WIDTH = 8.0
PAINT_LEN = WIDTH * 16 / 9          # arc length the 9:16 picture covers
PAINT_Y0 = -3.0                      # picture's bottom edge on the floor
CURVE_Y = 2.0
R = 1.0
FLOOR_Y0 = -7.0
WALL_TOP = R + (PAINT_LEN - (CURVE_Y - PAINT_Y0) - math.pi * R / 2)   # wall height where the picture ends


def _profile():
    """(y, z, s) points along the stage, s = arc length from the picture's bottom edge."""
    pts = []
    for k in range(9):  # front apron (before the picture starts), then the painted floor
        y = FLOOR_Y0 + (PAINT_Y0 - FLOOR_Y0) * k / 8
        pts.append((y, 0.0, y - PAINT_Y0))
    for k in range(1, 21):
        y = PAINT_Y0 + (CURVE_Y - PAINT_Y0) * k / 20
        pts.append((y, 0.0, y - PAINT_Y0))
    s0 = CURVE_Y - PAINT_Y0
    for k in range(1, 13):
        a = (math.pi / 2) * k / 12
        pts.append((CURVE_Y + R * math.sin(a), R - R * math.cos(a), s0 + R * a))
    s1 = s0 + math.pi * R / 2
    for k in range(1, 13):
        z = R + (WALL_TOP - R) * k / 12
        pts.append((CURVE_Y + R, z, s1 + (z - R)))
    return pts


def _stage(img):
    prof = _profile()
    cols = 8
    verts, faces, uvs = [], [], []
    for (y, z, s) in prof:
        for i in range(cols + 1):
            verts.append((-WIDTH / 2 + WIDTH * i / cols, y, z))
    for j in range(len(prof) - 1):
        for i in range(cols):
            a = j * (cols + 1) + i
            faces.append((a, a + 1, a + cols + 2, a + cols + 1))
    me = bpy.data.meshes.new("stage")
    me.from_pydata(verts, [], faces)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            j, i = divmod(vi, cols + 1)
            uv.data[li].uv = (i / cols, max(0.0, prof[j][2] / PAINT_LEN))
    o = bpy.data.objects.new("stage", me)
    bpy.context.scene.collection.objects.link(o)
    for p in me.polygons:
        p.use_smooth = True

    m = bpy.data.materials.new("TT_backdrop")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(img))
    tex.extension = "EXTEND"
    tex.interpolation = "Cubic"
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
    emi = nt.nodes.new("ShaderNodeEmission")
    emi.inputs["Strength"].default_value = 1.0
    add = nt.nodes.new("ShaderNodeMixShader")
    add.inputs[0].default_value = 0.55       # mostly self-lit so the painting keeps its colours; rest takes shadows
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    L = nt.links
    L.new(tex.outputs["Color"], dif.inputs["Color"])
    L.new(tex.outputs["Color"], emi.inputs["Color"])
    L.new(dif.outputs[0], add.inputs[1])
    L.new(emi.outputs[0], add.inputs[2])
    L.new(add.outputs[0], out.inputs["Surface"])
    o.data.materials.append(m)
    return o


def build(image, kit_name="stage"):
    sc = bpy.context.scene
    world = sc.world or bpy.data.worlds.new("W")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.92, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.55
    _stage(image)

    # key light from camera-left above (puppet shadows on the painted floor), soft fill from the right
    bpy.ops.object.light_add(type="AREA", location=(-1.4, -2.8, 3.0))
    key = bpy.context.active_object
    key.name = "stage_key"
    key.data.energy = 260
    key.data.size = 1.2
    key.data.color = (1.0, 0.93, 0.84)
    key.rotation_euler = (math.radians(55), 0, math.radians(-24))
    bpy.ops.object.light_add(type="AREA", location=(1.6, -2.2, 1.6))
    fill = bpy.context.active_object
    fill.name = "stage_fill"
    fill.data.energy = 60
    fill.data.size = 2.0
    fill.rotation_euler = (math.radians(75), 0, math.radians(40))
    fill.data.use_shadow = False

    kit = json.loads((Path(__file__).resolve().parent / "kits.json").read_text())["kits"][kit_name]
    return {"cast": {k: tuple(v) for k, v in kit["marks"].items()}, "props": kit["props"], "spots": kit["spots"]}
