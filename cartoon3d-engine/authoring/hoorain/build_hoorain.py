"""Hoorain (kids story lead) from the finished host f1: child proportions (uniform pose-bone scales, same values work on the GLB
in Three.js), colours from the user's girl picture (pink bow headband, pink tee, blue overalls, white sneakers, brown ponytail),
and a bow on the headband. Renders a character sheet for approval.
Run: blender -b build/revisions/f1_gate5/stage5_f1.blend --python hoorain/build_hoorain.py -- <tag>
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
TAG = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "v1"
OUT = HERE.parent / "build" / "hoorain" / TAG
OUT.mkdir(parents=True, exist_ok=True)

# Child proportions: uniform scales only (Three.js inherits scale the same way Blender does for uniform scales).
SCALES = {"root": 0.76, "head": 1.4, "neck01": 0.8, "upperleg01.L": 0.82, "upperleg01.R": 0.82,
          "clavicle.L": 0.92, "clavicle.R": 0.92, "breast.L": 0.15, "breast.R": 0.15}
# Child torso: front-back depth of the chest and the seat pulled toward the torso centre (rest mesh, every body/clothes mesh alike).
# (z0, z1, side, keep): side -1 = front (chest), +1 = back (seat); keep = fraction of the depth beyond the centre kept.
CHILD_DEPTH = [(1.0, 1.3, -1, 0.55), (0.62, 0.98, 1, 0.6), (0.62, 0.98, -1, 0.85)]
TORSO_MESHES = ["host_body", "host_tee", "host_overalls", "host_pocket", "host_stitch", "host_buttons", "host_strap_L", "host_strap_R"]
COLORS = {"tee": "#f59ac0", "band": "#ec5f9a", "shoes": "#f4f4f2", "hair_value": 1.45}


def hex_rgba(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x ** 2.2 for x in c) + (1.0,)


def flat_material(name, hexcol, rough=0.55):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = hex_rgba(hexcol)
    p.inputs["Roughness"].default_value = rough
    return m


def swap(obj_names, mat):
    for n in obj_names:
        o = bpy.data.objects[n]
        for i in range(len(o.data.materials)):
            o.data.materials[i] = mat


rig = bpy.data.objects["host_rig"]
# --- colours ---
swap(["host_tee"], flat_material("hoorain_tee", COLORS["tee"]))
band = flat_material("hoorain_band", COLORS["band"], 0.45)
swap(["concept_band", "concept_tie"], band)
# shoes: keep the texture's shading, push it to white
sh = bpy.data.materials["shoes"].node_tree
p = sh.nodes["Principled BSDF"]
link = p.inputs["Base Color"].links[0] if p.inputs["Base Color"].links else None
if link:
    hsv = sh.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = 0.0
    hsv.inputs["Value"].default_value = 2.2
    sh.links.new(link.from_socket, hsv.inputs["Color"])
    sh.links.new(hsv.outputs["Color"], p.inputs["Base Color"])
# hair: a warmer, lighter brown like the picture
hn = bpy.data.materials["hair_low"].node_tree
hp = hn.nodes["Principled BSDF"]
if hp.inputs["Base Color"].links:
    l = hp.inputs["Base Color"].links[0]
    hsv = hn.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Value"].default_value = COLORS["hair_value"]
    hsv.inputs["Saturation"].default_value = 1.1
    hn.links.new(l.from_socket, hsv.inputs["Color"])
    hn.links.new(hsv.outputs["Color"], hp.inputs["Base Color"])

# --- bow on the headband (rest space, then parented to the head bone) ---
bv = [bpy.data.objects["concept_band"].matrix_world @ v.co for v in bpy.data.objects["concept_band"].data.vertices]
cx = sum(v.x for v in bv) / len(bv)
side_pts = [v for v in bv if 0.05 < v.x - cx < 0.085]
top = max(side_pts, key=lambda v: v.z - 0.5 * v.y) + Vector((0, -0.012, 0.01))      # upper side, toward the front
bow_parts = []
for side in (-1, 1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1.0)
    o = bpy.context.object
    o.scale = (0.05, 0.018, 0.034)
    o.location = top + Vector((side * 0.042, 0, side * 0.012))
    o.rotation_euler = (0, side * math.radians(-20) + math.radians(-28), 0)
    bow_parts.append(o)
bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.018)
knot = bpy.context.object
knot.location = top + Vector((0, -0.004, 0.002))
bow_parts.append(knot)
for o in bow_parts:
    o.data.materials.append(band)
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.shade_smooth()
bpy.ops.object.select_all(action="DESELECT")
for o in bow_parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = bow_parts[0]
bpy.ops.object.join()
bow = bpy.context.object
bow.name = "hoorain_bow"
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
mw = bow.matrix_world.copy()
bow.parent = rig
bow.parent_type = "BONE"
bow.parent_bone = "head"
bow.matrix_world = mw
# the bow is rotated a bit so it sits on the band's slope


# --- child torso (rest mesh) ---
import numpy as np


def smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


body = bpy.data.objects["host_body"]
bco = np.array([body.matrix_world @ v.co for v in body.data.vertices])
torso = bco[np.abs(bco[:, 0]) < 0.12]
zb = np.linspace(0.55, 1.4, 35)
cy = np.array([np.median(torso[np.abs(torso[:, 2] - z) < 0.03][:, 1]) if (np.abs(torso[:, 2] - z) < 0.03).any() else 0.0 for z in zb])


def reshape(o):
    mw, inv = o.matrix_world, o.matrix_world.inverted()
    blocks = o.data.shape_keys.key_blocks if o.data.shape_keys else [None]
    for kb in blocks:
        data = kb.data if kb else o.data.vertices
        pts = np.array([mw @ d.co for d in data])
        x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
        c = np.interp(z, zb, cy)
        f = np.ones(len(pts))
        side_w = smooth((0.22 - np.abs(x)) / 0.08)          # torso only, fades out toward the arms
        for z0, z1, side, keep in CHILD_DEPTH:
            band_w = smooth((z - z0) / 0.06) * smooth((z1 - z) / 0.06)
            on = (np.sign(y - c) == side)
            k = keep * (0.92 if o.name == 'host_body' else 1.0)
            f = np.where(on, f * (1 - band_w * side_w * (1 - k)), f)
        pts[:, 1] = c + (y - c) * f
        for d, p in zip(data, pts):
            d.co = inv @ Vector(p)


for n in TORSO_MESHES:
    if n in bpy.data.objects:
        reshape(bpy.data.objects[n])

# --- proportions ---
for name, s in SCALES.items():
    pb = rig.pose.bones.get(name)
    if pb:
        pb.scale = (s, s, s)
bpy.context.view_layer.update()

# --- sheet renders ---
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.film_transparent = False
w = sc.world or bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = hex_rgba("#f6efe4")
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
sc.view_settings.view_transform = "Standard"

# character bounds after scaling
dg = bpy.context.evaluated_depsgraph_get()
zs = []
for o in bpy.data.objects:
    if o.type == "MESH" and o.visible_get():
        e = o.evaluated_get(dg)
        zs += [(o.matrix_world @ v.co).z for v in list(e.to_mesh().vertices)[::50]]
        e.to_mesh_clear()
zmin, zmax = min(zs), max(zs)
height = zmax - zmin
print("HEIGHT", round(height, 3))

cam_d = bpy.data.cameras.new("sheet_cam")
cam = bpy.data.objects.new("sheet_cam", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam


def shot(name, yaw_deg, frame_h, center_z, res=(640, 960), keys=None, lens=60):
    for o in bpy.data.objects:
        if o.type == "MESH" and o.data.shape_keys:
            for kb in o.data.shape_keys.key_blocks[1:]:
                kb.value = (keys or {}).get(kb.name, 0.0)
    rig.rotation_euler = (0, 0, math.radians(yaw_deg))
    cam_d.lens = lens
    cam_d.sensor_fit = "VERTICAL"
    cam_d.sensor_height = 24
    dist = frame_h * lens / 24
    cam.location = (0, -dist, center_z)
    cam.rotation_euler = (math.radians(90), 0, 0)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)


H = height * 1.12
mid = zmin + height / 2
shot("front", 0, H, mid)
shot("threeq", -35, H, mid)
shot("side", -90, H, mid)
shot("back", 180, H, mid)
face_h = height * 0.42
face_z = zmax - face_h * 0.44
shot("face_smile", -15, face_h, face_z, res=(640, 640), keys={"smile": 1.0})
shot("face_laugh", 10, face_h, face_z, res=(640, 640), keys={"laugh": 1.0})
shot("face_surprise", 0, face_h, face_z, res=(640, 640), keys={"surprise": 1.0})
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "hoorain.blend"))
(OUT / "params.json").write_text(json.dumps({"scales": SCALES, "colors": COLORS, "height_m": round(height, 3)}, indent=1))
print("DONE", OUT)
