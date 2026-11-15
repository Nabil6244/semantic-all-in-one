"""Look sheet for Noraiz: arms relaxed, optional face pose; front/3-4/side + face close-up.
Run: blender -b <noraiz.blend> --python cast/boy_sheet.py -- <out dir> [jaw_deg]
"""
import math
import sys

import bpy
from mathutils import Euler, Vector

args = sys.argv[sys.argv.index("--") + 1:]
out, jaw = args[0], float(args[1]) if len(args) > 1 else 0.0
KEYS = dict(a.split("=") for a in args[2:])          # e.g. smile=1 blink.L=1
sc = bpy.context.scene
rig = bpy.data.objects["noraiz_rig"]
pb = rig.pose.bones
def aim(bone, d_world):
    """Rotate a pose bone about its head so it points along d_world."""
    head = rig.matrix_world @ bone.head
    cur = (rig.matrix_world @ bone.tail - head).normalized()
    r = cur.rotation_difference(Vector(d_world).normalized())
    q = rig.matrix_world.to_quaternion()
    r = q.inverted() @ r @ q
    m = bone.matrix.copy()
    loc = m.to_translation()
    m.translation = (0, 0, 0)
    new = r.to_matrix().to_4x4() @ m
    new.translation = loc
    bone.matrix = new
    bpy.context.view_layer.update()


for side, s in (("L", 1), ("R", -1)):
    aim(pb[f"upper_arm.{side}"], (s * 0.38, 0.02, -0.92))
    aim(pb[f"forearm.{side}"], (s * 0.22, -0.18, -0.96))
pb["jaw"].rotation_mode = "XYZ"
pb["jaw"].rotation_euler = Euler((math.radians(jaw), 0, 0), "XYZ")
for o in bpy.data.objects:
    if o.type == "MESH" and o.data.shape_keys:
        for k, v in KEYS.items():
            if k in o.data.shape_keys.key_blocks:
                o.data.shape_keys.key_blocks[k].value = float(v)
only_face = "FACEONLY" in KEYS
bpy.context.view_layer.update()
for n in ("hand.L", "hand.R"):
    print("HAND", n, tuple(round(x, 3) for x in rig.matrix_world @ pb[n].head))

sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
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
cd = bpy.data.cameras.new("c")
cam = bpy.data.objects.new("c", cd)
sc.collection.objects.link(cam)
sc.camera = cam
H = 1.25


def shot(name, center, fh, res, yaw=0, lens=55):
    cd.lens, cd.sensor_fit, cd.sensor_height = lens, "VERTICAL", 24
    d, a = fh * lens / 24, math.radians(yaw)
    cam.location = center + Vector((math.sin(a) * d, -math.cos(a) * d, 0))
    cam.rotation_euler = (math.radians(90), 0, a)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = f"{out}/{name}.png"
    bpy.ops.render.render(write_still=True)


mid = Vector((0, 0, H / 2))
if only_face:
    shot("face", Vector((0, 0, 0.88)), 0.62, (600, 600), yaw=-10)
    raise SystemExit
shot("front", mid, H * 1.1, (700, 1000))
shot("threeq", mid, H * 1.1, (700, 1000), yaw=-35)
shot("side", mid, H * 1.1, (700, 1000), yaw=-90)
shot("face", Vector((0, 0, 0.88)), 0.62, (800, 800), yaw=-15)
