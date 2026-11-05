"""Approval sheet renders: blender -b build/host_stage3c.blend --python host/stage3_sheet.py
Writes build/sheet/*.png: the 8 required views plus bent-pose deformation tests. Same lights and camera rules for all."""
import math
import os
import sys

import bpy
import mathutils
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD, lin, material, shot, studio

OUT = os.path.join(BUILD, "sheet"); os.makedirs(OUT, exist_ok=True)
rig = bpy.data.objects["host_rig"]
studio(bg="#eef0f2")
bpy.context.scene.render.film_transparent = True
bpy.context.scene.render.image_settings.color_mode = "RGBA"
HEAD_Z = rig.data.bones["head"].head_local.z + 0.075


def setk(name, v):
    for o in bpy.data.objects:
        if o.type == "MESH" and o.data.shape_keys and name in o.data.shape_keys.key_blocks:
            o.data.shape_keys.key_blocks[name].value = v


def aim(name, d):
    bpy.context.view_layer.update()
    pb = rig.pose.bones[name]; M = pb.matrix.copy()
    cur = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
    R = cur.rotation_difference(Vector(d).normalized()).to_matrix().to_4x4()
    t = M.translation.copy()
    pb.matrix = Matrix.Translation(t) @ R @ Matrix.Translation(-t) @ M
    bpy.context.view_layer.update()


def turn(name, axis, deg):
    bpy.context.view_layer.update()
    pb = rig.pose.bones[name]; M = pb.matrix.copy(); t = M.translation.copy()
    pb.matrix = Matrix.Translation(t) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-t) @ M
    bpy.context.view_layer.update()


def rest():
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def arm(tag, upper, lower):
    for b in ("upperarm01", "upperarm02"):
        aim(f"{b}.{tag}", upper)
    for b in ("lowerarm01", "lowerarm02"):
        aim(f"{b}.{tag}", lower)


def leg(tag, thigh, shin):
    for b in ("upperleg01", "upperleg02"):
        aim(f"{b}.{tag}", thigh)
    for b in ("lowerleg01", "lowerleg02"):
        aim(f"{b}.{tag}", shin)


FULL = dict(target=(0, 0, 0.82), dist=5.3, lens=85, res=(640, 1000))
FACE = dict(target=(0, -0.05, HEAD_Z), dist=1.45, lens=85, res=(640, 760))
for n, az in (("front", 0), ("three_quarter", 35), ("side", 90), ("back", 180)):
    shot(os.path.join(OUT, n + ".png"), azimuth=az, **FULL)
shot(os.path.join(OUT, "face.png"), azimuth=0, **FACE)
setk("exprSmile", 1); shot(os.path.join(OUT, "smile.png"), azimuth=12, **FACE)
arm("L", (0.62, -0.1, 0.78), (0.12, -0.18, 1)); arm("R", (-0.3, -0.03, -1), (-0.22, -0.28, -1))
turn("neck02", "Y", 4)
shot(os.path.join(OUT, "wave.png"), azimuth=8, **FULL)
setk("exprSmile", 0); rest()
setk("exprLaugh", 1); shot(os.path.join(OUT, "laugh.png"), azimuth=-12, **FACE); setk("exprLaugh", 0)
setk("exprSurprise", 1); shot(os.path.join(OUT, "surprise.png"), azimuth=0, **FACE); setk("exprSurprise", 0)

# deformation tests: shoulders overhead, arms forward and bent, stride, deep knee, head turn
arm("L", (0.25, 0, 1), (0.1, 0, 1)); arm("R", (-0.25, 0, 1), (-0.1, 0, 1))
shot(os.path.join(OUT, "t_arms_up.png"), azimuth=25, **FULL); rest()
arm("L", (0.3, -1, 0.1), (-0.8, -0.7, 0.2)); arm("R", (-0.3, -1, 0.1), (0.8, -0.7, 0.2))
turn("neck01", "Z", 25); turn("head", "Z", 20)
shot(os.path.join(OUT, "t_arms_front.png"), azimuth=-30, **FULL); rest()
leg("L", (0.03, -0.8, -1), (0.05, 0.25, -1)); leg("R", (-0.03, 0.45, -1), (-0.02, 0.75, -1))
shot(os.path.join(OUT, "t_stride.png"), azimuth=70, **FULL); rest()
leg("L", (0.12, -1, -0.15), (0.03, 0.15, -1)); leg("R", (-0.12, -1, -0.15), (-0.03, 0.15, -1))
shot(os.path.join(OUT, "t_sit.png"), azimuth=50, **FULL); rest()
print("SHEET DONE")
