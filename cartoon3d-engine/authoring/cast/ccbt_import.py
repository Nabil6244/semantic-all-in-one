"""Import a Character Creator based FBX through CC/iC Blender Tools (soupday/cc_blender_tools, GPL-3, kept in
tools/cc_blender_tools_pkg and loaded from there, not installed into the user's Blender): proper skin / eye / hair
shaders, then optional Rigify conversion (hand + finger + face controls).
Run: blender -b --python cast/ccbt_import.py -- <character.fbx> <out dir> [rigify]
"""
import math
import sys
import time
from pathlib import Path

import addon_utils
import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
fbx, out = Path(args[0]).resolve(), Path(args[1])
RIGIFY = "rigify" in args
out.mkdir(parents=True, exist_ok=True)
TOOLS = Path(__file__).resolve().parent.parent / "tools"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.use_preferences_save = False      # session-only: never write the user's Blender prefs
sys.path.insert(0, str(TOOLS))
for mod in ("rigify", "cc_blender_tools_pkg"):
    m = addon_utils.enable(mod, default_set=True, persistent=False)
    print("ADDON", mod, "ok" if m else "FAILED")
t0 = time.time()
res = bpy.ops.cc3.importer(param="IMPORT_QUALITY", filepath=str(fbx), no_rigify=True)
print("IMPORT", res, round(time.time() - t0, 1), "s")
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
print("ARMATURE", arm.name, len(arm.data.bones))
if RIGIFY:
    bpy.context.view_layer.objects.active = arm
    t0 = time.time()
    try:
        res = bpy.ops.cc3.rigifier(param="ALL", no_face_rig=False)
        print("RIGIFY", res, round(time.time() - t0, 1), "s")
    except Exception as e:  # noqa: BLE001
        print("RIGIFY_FAIL", e)
    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE" and o.name.endswith("_Rigify")), arm)
    # this (non-CC-exported) FBX comes out of Rigify lying along +Y: stand the rig up, children follow
    dg = bpy.context.evaluated_depsgraph_get()
    b = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("CC_Base_Body"))
    e = b.evaluated_get(dg)
    me = e.to_mesh()
    P = [b.matrix_world @ v.co for v in me.vertices]
    e.to_mesh_clear()
    span = [max(p[i] for p in P) - min(p[i] for p in P) for i in range(3)]
    if span[1] > span[2] * 2:
        arm.rotation_euler.x += math.radians(90)
        bpy.context.view_layer.update()
        print("STOOD_UP", [round(x, 2) for x in span])
    print("RIG_NOW", arm.name, len(arm.data.bones), [b.name for b in arm.data.bones if "hand" in b.name.lower()][:8])
print("MATS", sorted({m.name for o in bpy.data.objects if o.type == "MESH" for m in o.data.materials if m})[:30])

# --- quick look: face + hands, plain studio light, Eevee without ray tracing (our fast settings) ---
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
if hasattr(sc.eevee, "use_raytracing"):
    sc.eevee.use_raytracing = False
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.86, 0.82, 0.76, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.8
for n, rot, en in (("key", (55, 0, -35), 3.0), ("fill", (65, 0, 40), 1.2), ("rim", (60, 0, 170), 2.0)):
    ld = bpy.data.lights.new(n, "SUN")
    ld.energy = en
    lo = bpy.data.objects.new(n, ld)
    sc.collection.objects.link(lo)
    lo.rotation_euler = [math.radians(a) for a in rot]
body = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("CC_Base_Body"))
dg = bpy.context.evaluated_depsgraph_get()
e = body.evaluated_get(dg)
me = e.to_mesh()
P = [body.matrix_world @ v.co for v in me.vertices]
e.to_mesh_clear()
zmax, zmin = max(p.z for p in P), min(p.z for p in P)
H = zmax - zmin
cx, cy = sum(p.x for p in P) / len(P), sum(p.y for p in P) / len(P)
cd = bpy.data.cameras.new("c")
cam = bpy.data.objects.new("c", cd)
sc.collection.objects.link(cam)
sc.camera = cam


def shot(name, center, fh, res, yaw=0, lens=55):
    cd.lens, cd.sensor_fit, cd.sensor_height = lens, "VERTICAL", 24
    d, a = fh * lens / 24, math.radians(yaw)
    cam.location = center + Vector((math.sin(a) * d, -math.cos(a) * d, 0))
    cam.rotation_euler = (math.radians(90), 0, a)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = str(out / f"{name}.png")
    bpy.ops.render.render(write_still=True)


shot("front", Vector((cx, cy, zmin + H / 2)), H * 1.1, (640, 1000))
shot("face", Vector((cx, cy, zmax - H * 0.075)), H * 0.17, (800, 800), yaw=-12)
bpy.ops.wm.save_as_mainfile(filepath=str(out / "ccbt.blend"))
print("DONE", out)
