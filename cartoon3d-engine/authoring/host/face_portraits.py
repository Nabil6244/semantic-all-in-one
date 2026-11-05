"""Stage 2.5 revision renders. Same lights, cameras and sizes every run, so revisions compare fairly.
Run: blender -b build/host_stage3c.blend --python host/face_portraits.py -- <tag> [--small]
Writes build/face/<tag>/*.png (transparent background; face_sheet.py composites them)."""
import math
import os
import sys

import bpy
import mathutils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD, lin, shot

ARGS = sys.argv[sys.argv.index("--") + 1:]
TAG = ARGS[0]; SMALL = "--small" in ARGS
OUT = os.path.join(BUILD, "face", TAG); os.makedirs(OUT, exist_ok=True)
s = bpy.context.scene; rig = bpy.data.objects["host_rig"]
s.render.engine = "BLENDER_EEVEE"; s.render.film_transparent = True
s.view_settings.view_transform = "Standard"; s.view_settings.look = "None"; s.view_settings.exposure = 0
for k, v in (("use_raytracing", True), ("taa_render_samples", 48)):
    if hasattr(s.eevee, k):
        setattr(s.eevee, k, v)
w = bpy.data.worlds.get("portrait") or bpy.data.worlds.new("portrait"); s.world = w; w.use_nodes = True
b = w.node_tree.nodes["Background"]; b.inputs[0].default_value = lin("#e9e4de"); b.inputs[1].default_value = 0.42
HZ = rig.data.bones["head"].head_local.z + 0.075
T = Vector((0, -0.04, HZ))
for n, en, off, size, col in (("p_key", 26, (-0.85, -1.15, 0.65), 1.3, (1, .95, .89)),      # large soft key, camera left, above eye line
                              ("p_fill", 7, (1.1, -1.1, 0.05), 1.8, (.94, .96, 1)),          # low-contrast fill
                              ("p_hair", 16, (0.65, 0.95, 0.75), 0.8, (1, .97, .93)),        # hair and shoulder separation
                              ("p_bounce", 3, (0, -0.8, -0.7), 1.2, (1, .86, .76))):         # warm bounce under the chin
    L = bpy.data.lights.new(n, "AREA"); L.energy = en; L.size = size; L.color = col
    o = bpy.data.objects.new(n, L); s.collection.objects.link(o); o.location = T + Vector(off)
    o.rotation_euler = (T - o.location).to_track_quat("-Z", "Y").to_euler()


def keys(**vals):
    for o in bpy.data.objects:
        if o.type == "MESH" and o.data.shape_keys:
            for kb in o.data.shape_keys.key_blocks[1:]:
                kb.value = vals.get(kb.name, 0.0)


def pose_head(tilt=0, turn=0):
    pb = rig.pose.bones["head"]; pb.rotation_mode = "XYZ"; pb.rotation_euler = (0, math.radians(turn), math.radians(tilt))
    bpy.context.view_layer.update()


R = (700, 840) if SMALL else (1400, 1680)
SH = dict(target=tuple(T), dist=1.5, lens=85, res=R)
SHOTS = [("front_neutral", 0, {}), ("front_smile", 0, {"exprSmile": 1}), ("q_neutral", 35, {}), ("q_smile", 35, {"exprSmile": 1}), ("side", 90, {}),
         ("laugh", 15, {"exprLaugh": 1}), ("talk", 15, {"exprTalk": 1}), ("surprise", 0, {"exprSurprise": 1}), ("curious", 15, {"exprCurious": 1}),
         ("smile45_arkit", 0, {"mouthSmileLeft": .45, "mouthSmileRight": .45})]
for name, az, k in SHOTS:
    keys(**k); shot(os.path.join(OUT, name + ".png"), azimuth=az, **SH)
keys()
e = rig.data.bones["eye.L"].head_local
shot(os.path.join(OUT, "eyes.png"), target=(0, e.y, e.z + 0.008), dist=0.62, azimuth=0, lens=85, res=(R[1], int(R[1] * 0.5)))
print("PORTRAITS DONE")
