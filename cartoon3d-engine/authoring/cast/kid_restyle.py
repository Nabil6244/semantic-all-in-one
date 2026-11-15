"""Hoorain from the CGTrader 'Little Kid 1' girl: the dress becomes a pink tee + denim overall-dress (pinafore: bib, straps,
skirt) by splitting its faces into two materials along clean cuts; pink headband with a bow on the head bone; white sneakers;
soft happy face, clean skin. Renders a sheet.
Run: blender -b --disable-autoexec "<Little Kid 1.blend>" --python cast/kid_restyle.py -- <texture dir> <out dir>
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

tex_dir, out = sys.argv[sys.argv.index("--") + 1:][:2]
OUT = Path(out)
OUT.mkdir(parents=True, exist_ok=True)
LOOK = {"tee": "#f58fba", "denim": "#3f69a8", "band": "#ec4f8f", "shoes_value": 1.9}

sc = bpy.context.scene
try:
    bpy.ops.file.find_missing_files(directory=tex_dir)
except Exception as e:  # noqa: BLE001
    print("find_missing_files:", e)
for o in bpy.data.objects:
    if o.name.startswith(("cs_", "WGT-", "bone_shape", "facial_landmarks")) or o.name in ("Plane",):
        o.hide_render = True
        o.hide_viewport = True
rig = bpy.data.objects["rig"]


def lin(h):
    h = h.lstrip("#")
    return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4)) + (1.0,)


def bone(name):
    return rig.matrix_world @ rig.data.bones[name].head_local


names = [b.name for b in rig.data.bones]
print("DEFORM_BONES", [n for n in names if not n.startswith(("c_", "mch", "MCH")) and any(k in n for k in ("spine", "neck", "head", "arm", "shoulder", "thigh"))][:30])


def first(*cands):
    for c in cands:
        if c in rig.data.bones:
            return bone(c)
    raise KeyError(cands)


neck = first("neck.x", "c_neck.x")
spine3 = first("spine_03.x", "c_spine_03.x")
arm_l = first("arm.l", "c_arm_fk.l", "shoulder.l")
head = first("head.x", "c_head.x")
print("LANDMARKS neck", tuple(round(v, 3) for v in neck), "spine3", tuple(round(v, 3) for v in spine3), "arm", tuple(round(v, 3) for v in arm_l))

# --- dress -> pink tee + denim pinafore (material split along clean cuts) ---
dress = bpy.data.objects["Cube_002"]
dw = dress.matrix_world
pts = [dw @ v.co for v in dress.data.vertices]
dcy = sum(p.y for p in pts) / len(pts)
arm_x = abs(arm_l.x)
chest_z = spine3.z + 0.25 * (neck.z - spine3.z)
sx0, sx1 = 0.32 * arm_x, 0.62 * arm_x
bib_x = 0.72 * arm_x
print("CUTS chest", round(chest_z, 3), "straps", round(sx0, 3), round(sx1, 3), "bib", round(bib_x, 3))


def mat_flat(name, hexcol, rough=0.8, noise=0.15, scale=300):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    mx = nt.nodes.new("ShaderNodeMixRGB")
    mx.blend_type, mx.inputs["Fac"].default_value = "MULTIPLY", noise
    mx.inputs["Color1"].default_value = lin(hexcol)
    nt.links.new(nz.outputs["Color"], mx.inputs["Color2"])
    nt.links.new(mx.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = rough
    return m


tee_m, denim_m = mat_flat("hoorain_tee", LOOK["tee"], 0.75, 0.08), mat_flat("hoorain_denim", LOOK["denim"], 0.9, 0.3, 700)
dress.data.materials.clear()
dress.data.materials.append(tee_m)
dress.data.materials.append(denim_m)
bm = bmesh.new()
bm.from_mesh(dress.data)
inv = dw.inverted()
nrm = inv.to_3x3().transposed().inverted()
sleeve_x = 0.8 * arm_x
hem_z = arm_l.z - 0.018                                  # under-edge of the sleeves
dz_, dx_ = hem_z - chest_z, sleeve_x - sx1                # armhole: a straight slope from the strap down to the sleeve's under-edge
slopes = [((sgn * sx1, 0, chest_z), (sgn * dz_, 0, -dx_)) for sgn in (1, -1)]
for co, no in [((0, 0, chest_z), (0, 0, 1)), ((0, 0, hem_z), (0, 0, 1))] + [((x, 0, 0), (1, 0, 0)) for x in (sx0, -sx0, sx1, -sx1)] + slopes:
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=inv @ Vector(co), plane_no=(nrm @ Vector(no)).normalized(), dist=1e-7)
for f in bm.faces:
    c = dw @ f.calc_center_median()
    ax = abs(c.x)
    if c.z < chest_z:
        f.material_index = 1 if (c.z < hem_z or (ax - sx1) * dz_ - (c.z - chest_z) * dx_ > 0) else 0      # skirt + bib denim; only the sleeves stay tee
    else:
        f.material_index = 1 if sx0 < ax < sx1 else 0
bm.to_mesh(dress.data)
bm.free()

# --- headband + bow on the head bone ---
dg = bpy.context.evaluated_depsgraph_get()
hair = bpy.data.objects["Hair"]
he = hair.evaluated_get(dg)
hm = he.to_mesh()
hp = [hair.matrix_world @ v.co for v in hm.vertices]
he.to_mesh_clear()
lo = Vector((min(p.x for p in hp), min(p.y for p in hp), min(p.z for p in hp)))
hi = Vector((max(p.x for p in hp), max(p.y for p in hp), max(p.z for p in hp)))
cx, cy = (lo.x + hi.x) / 2, lo.y + 0.42 * (hi.y - lo.y)          # a little in front of the middle: the band sits behind the fringe
ear_z = lo.z + 0.45 * (hi.z - lo.z)
band_y = cy
sect = [p for p in hp if abs(p.y - band_y) < 0.01 * (hi.y - lo.y) + 0.004]
half_w = max(abs(p.x - cx) for p in sect) if sect else (hi.x - lo.x) / 2
top = max(p.z for p in sect) if sect else hi.z
from mathutils.bvhtree import BVHTree
htree = BVHTree.FromObject(hair, dg)
hinv = hair.matrix_world.inverted()
band_m = mat_flat("hoorain_band", LOOK["band"], 0.45, 0.05)
tilt = math.radians(-18)                                   # leans back from the fringe
ctr = Vector((cx, band_y, ear_z))
path = []
for i in range(41):
    t = math.radians(-82 + 164 * i / 40)                  # ear to ear over the top
    d = Vector((math.sin(t), 0, math.cos(t)))
    d = Vector((d.x, -math.sin(tilt) * d.z, math.cos(tilt) * d.z))
    far = ctr + d * 0.5
    hit = htree.ray_cast(hinv @ far, (hinv.to_3x3() @ (-d)).normalized())
    if hit[0] is None:
        continue
    pw = hair.matrix_world @ hit[0]
    path.append(pw + d * 0.004)
print("BAND_POINTS", len(path))
cu = bpy.data.curves.new("hoorain_band", "CURVE")
cu.dimensions = "3D"
sp = cu.splines.new("POLY")
sp.points.add(len(path) - 1)
for pt, pw in zip(sp.points, path):
    pt.co = (pw.x, pw.y, pw.z, 1)
cu.bevel_depth = 0.0065
cu.bevel_resolution = 4
cu.use_fill_caps = True
band = bpy.data.objects.new("hoorain_headband", cu)
sc.collection.objects.link(band)
band.data.materials.append(band_m)
band.scale = (1, 1, 1)
R = half_w
zs = 1.0
mid_pt = path[len(path) // 2 + 5]
# bow: two puffy loops + knot, up on the band toward the character's left
ang = math.radians(38)
bow_at = path[int(len(path) * 0.73)] + Vector((0, -0.002, 0.002))
R = half_w * 0.75
parts = []
for sgn in (-1, 1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1.0)
    o = bpy.context.object
    o.scale = (R * 0.34, R * 0.13, R * 0.22)
    o.rotation_euler = (0, sgn * math.radians(25) - ang, 0)
    o.location = bow_at + Vector((sgn * R * 0.26 * math.cos(ang), -R * 0.05, -sgn * R * 0.26 * math.sin(ang)))
    parts.append(o)
bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=R * 0.1, location=bow_at + Vector((0, -R * 0.08, 0)))
parts.append(bpy.context.object)
for o in parts:
    o.data.materials.append(band_m)
bpy.ops.object.select_all(action="DESELECT")
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
bow = bpy.context.object
bow.name = "hoorain_bow"
bpy.ops.object.shade_smooth()
head_bone = "head.x" if "head.x" in rig.data.bones else "c_head.x"
for o in (band, bow):
    m = o.matrix_world.copy()
    o.parent, o.parent_type, o.parent_bone = rig, "BONE", head_bone
    o.matrix_world = m

# --- white sneakers ---
sm = bpy.data.objects["Toon_Sneakers_B"].data.materials[0]
nt = sm.node_tree
p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
if p.inputs["Base Color"].links:
    l = p.inputs["Base Color"].links[0]
    mx = nt.nodes.new("ShaderNodeMixRGB")
    mx.inputs["Fac"].default_value = 0.8
    mx.inputs["Color2"].default_value = (0.92, 0.92, 0.92, 1)
    nt.links.new(l.from_socket, mx.inputs["Color1"])
    nt.links.new(mx.outputs["Color"], p.inputs["Base Color"])

# --- face: the artist's own "Happy" expression at half strength (user pick: Happy soft) + clean friendly skin ---
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kid_skin import friendly_skin, pose_face   # noqa: E402
FACE = ("Happy", 0.5)
friendly_skin(os.environ.get("KID_FACE_TEX"))     # cleaned head diffuse from cast/kid_soften_face.py
pose_face(*FACE)

# --- sheet ---
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.film_transparent = False
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value, bg.inputs["Strength"].default_value = (0.86, 0.82, 0.76, 1), 0.8
for o in bpy.data.objects:
    if o.type == "LIGHT":
        o.hide_render = True
for name, rot, en in (("key", (55, 0, -35), 3.0), ("fill", (65, 0, 40), 1.2), ("rim", (60, 0, 170), 2.0)):
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy, ld.angle = en, math.radians(12)
    lo_ = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(lo_)
    lo_.rotation_euler = tuple(math.radians(a) for a in rot)
cd = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
dg = bpy.context.evaluated_depsgraph_get()
allp = []
for o in bpy.data.objects:
    if o.type == "MESH" and not o.hide_render and o.visible_get():
        e = o.evaluated_get(dg)
        mm = e.to_mesh()
        allp += [o.matrix_world @ v.co for v in list(mm.vertices)[::25]]
        e.to_mesh_clear()
zmin, zmax = min(p.z for p in allp), max(p.z for p in allp)
H = zmax - zmin
ccx = sum(p.x for p in allp) / len(allp)
ccy = sum(p.y for p in allp) / len(allp)


def shot(name, center, frame_h, res, yaw=0.0, lens=55):
    cd.lens, cd.sensor_fit, cd.sensor_height = lens, "VERTICAL", 24
    d = frame_h * lens / 24
    a = math.radians(yaw)
    cam.location = center + Vector((math.sin(a) * d, -math.cos(a) * d, 0))
    cam.rotation_euler = (math.radians(90), 0, a)
    cd.clip_start = d * 0.01
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)


mid = Vector((ccx, ccy, zmin + H / 2))
shot("front", mid, H * 1.1, (640, 1000))
shot("threeq", mid, H * 1.1, (640, 1000), yaw=-35)
shot("side", mid, H * 1.1, (640, 1000), yaw=-90)
shot("back", mid, H * 1.1, (640, 1000), yaw=180)
face = Vector((ccx, ccy, zmax - H * 0.25))
shot("face", face, H * 0.46, (800, 800), yaw=-15)
shot("face_front", face, H * 0.46, (800, 800))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "hoorain.blend"))
print("DONE", OUT, "height", round(H, 3))
