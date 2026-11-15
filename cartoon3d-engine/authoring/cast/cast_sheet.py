"""Cast sheet: the CGTrader kid (Blender file) and the woman (FBX) side by side, plus face close-ups.
Run: blender -b --disable-autoexec "<kid .blend>" --python cast/cast_sheet.py -- <woman.fbx> <kid texture dir> <out dir>
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

woman_fbx, tex_dir, out = sys.argv[sys.argv.index("--") + 1:][:3]
OUT = Path(out)
OUT.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene

# kid textures: relink anything missing from the downloaded texture folder
try:
    bpy.ops.file.find_missing_files(directory=tex_dir)
except Exception as e:  # noqa: BLE001
    print("find_missing_files:", e)
miss = [i.name for i in bpy.data.images if i.source == "FILE" and not i.packed_file and not Path(bpy.path.abspath(i.filepath)).exists()]
print("KID_MISSING_IMAGES", len(miss), miss[:6])


def visible_meshes(objs):
    return [o for o in objs if o.type == "MESH" and not o.hide_render and o.visible_get()]


def bounds(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in objs:
        e = o.evaluated_get(dg)
        m = e.to_mesh()
        for v in list(m.vertices)[::20]:
            p = o.matrix_world @ v.co
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
        e.to_mesh_clear()
    return lo, hi


# hide helper objects that are not part of the character in renders (rig widgets, landmarks, floor)
for o in bpy.data.objects:
    if o.name.startswith(("cs_", "WGT-", "bone_shape", "facial_landmarks")) or o.name in ("Plane",):
        o.hide_render = True
        o.hide_viewport = True
kid_objs = visible_meshes(bpy.data.objects)
print("KID_MESHES", [o.name for o in kid_objs])
klo, khi = bounds(kid_objs)
print("KID_BOUNDS", tuple(round(x, 3) for x in klo), tuple(round(x, 3) for x in khi))

before = set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=woman_fbx)
w_new = [o for o in bpy.data.objects if o not in before]
w_root = [o for o in w_new if o.parent is None]
w_meshes = visible_meshes(w_new)
wlo, whi = bounds(w_meshes)
print("WOMAN_BOUNDS raw", tuple(round(x, 3) for x in wlo), tuple(round(x, 3) for x in whi))
kid_h = khi.z - klo.z
target = kid_h * 1.6                                   # a ~1.05 m child next to a ~1.68 m adult
s = target / (whi.z - wlo.z)
for o in w_root:
    o.scale = o.scale * s
bpy.context.view_layer.update()
wlo, whi = bounds(w_meshes)
gap = 0.15 * target
dx = (klo.x - gap) - whi.x
dz = klo.z - wlo.z
dy = (klo.y + khi.y) / 2 - (wlo.y + whi.y) / 2
for o in w_root:
    o.location += Vector((dx, dy, dz))
bpy.context.view_layer.update()
wlo, whi = bounds(w_meshes)
print("WOMAN_BOUNDS placed", tuple(round(x, 3) for x in wlo), tuple(round(x, 3) for x in whi))

# lighting: soft world + key/fill suns, our own camera
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.film_transparent = False
w = sc.world or bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
nt = w.node_tree
bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None)
if bg is None:
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    outn = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs[0], outn.inputs[0])
bg.inputs["Color"].default_value = (0.86, 0.82, 0.76, 1)
bg.inputs["Strength"].default_value = 0.8
for o in bpy.data.objects:
    if o.type == "LIGHT":
        o.hide_render = True
for name, rot, en in (("key", (55, 0, -35), 3.2), ("fill", (65, 0, 40), 1.3), ("rim", (60, 0, 170), 2.0)):
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy = en
    ld.angle = math.radians(12)
    lo_ = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(lo_)
    lo_.rotation_euler = tuple(math.radians(a) for a in rot)

cd = bpy.data.cameras.new("cast_cam")
cam = bpy.data.objects.new("cast_cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam


def shot(name, center, frame_h, res, yaw=0.0, lens=55):
    cd.lens, cd.sensor_fit, cd.sensor_height = lens, "VERTICAL", 24
    d = frame_h * lens / 24
    a = math.radians(yaw)
    cam.location = center + Vector((math.sin(a) * d, -math.cos(a) * d, 0))
    cam.rotation_euler = (math.radians(90), 0, a)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)


lo = Vector(map(min, klo, wlo))
hi = Vector(map(max, khi, whi))
mid = (lo + hi) / 2
H = (hi.z - lo.z) * 1.12
shot("together_front", mid, H, (1600, 1000))
shot("together_threeq", mid, H, (1600, 1000), yaw=-30)
kh = khi.z - klo.z
kface = Vector(((klo.x + khi.x) / 2, (klo.y + khi.y) / 2, khi.z - kh * 0.23))
wh = whi.z - wlo.z
wface = Vector(((wlo.x + whi.x) / 2, (wlo.y + whi.y) / 2, whi.z - wh * 0.08))
shot("kid_face", kface, kh * 0.44, (800, 800), yaw=-12)
shot("woman_face", wface, wh * 0.17, (800, 800), yaw=-12)
print("DONE", OUT)
