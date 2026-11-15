"""Face options for a restyled kid: pose-library expressions at full or partial strength, one close-up each.
Run: blender -b --disable-autoexec <hoorain.blend> --python cast/kid_face_board.py -- <out dir> Name[:strength] ...
"""
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

args = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(args[0])
OUT.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
cam = sc.camera


def clear():
    for ob in arms:
        if ob.animation_data:
            ob.animation_data.action = None
        for pb in ob.pose.bones:
            pb.location = (0, 0, 0)
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
            pb.scale = (1, 1, 1)


def pose(name, k):
    clear()
    act = bpy.data.actions.get(name)
    if act is None:
        return False
    snap = {}
    for ob in arms:
        ob.animation_data_create()
        ob.animation_data.action = act
        try:
            if act.slots:
                ob.animation_data.action_slot = act.slots[0]
        except Exception:  # noqa: BLE001
            pass
    sc.frame_set(int(act.frame_range[0]))
    for ob in arms:
        for pb in ob.pose.bones:
            snap[(ob.name, pb.name)] = (pb.location.copy(), pb.rotation_quaternion.copy(), pb.rotation_euler.copy(), pb.scale.copy())
        ob.animation_data.action = None
    for ob in arms:
        for pb in ob.pose.bones:
            l, q, e, s = snap[(ob.name, pb.name)]
            pb.location = l * k
            pb.rotation_quaternion = Quaternion().slerp(q, k)
            pb.rotation_euler = (e[0] * k, e[1] * k, e[2] * k)
            pb.scale = Vector((1, 1, 1)).lerp(s, k)
    bpy.context.view_layer.update()
    return True


# friendlier skin (KID_FACE_TEX env = cleaned diffuse): new image on the node + calmer red scatter on nose/lids
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kid_skin import friendly_skin   # noqa: E402
friendly_skin(os.environ.get("KID_FACE_TEX"))

# camera: front face close-up (reuse the sheet's face framing by looking at the head bone)
rig = bpy.data.objects["rig"]
hb = rig.matrix_world @ rig.data.bones["head.x"].head_local
cam.location = Vector((hb.x, hb.y - 0.62, hb.z + 0.03))
cam.rotation_euler = (1.5708, 0, 0)
cam.data.lens = 55
sc.render.resolution_x = sc.render.resolution_y = 600
for spec in args[1:]:
    name, _, k = spec.partition(":")
    k = float(k or 1)
    if pose(name, k):
        sc.render.filepath = str(OUT / f"{name.strip().replace(' ', '_')}_{int(k * 100)}.png")
        bpy.ops.render.render(write_still=True)
        print("FACE", name, k)
