"""Try mocap clips on the cast and render a contact grid.
Run: blender -b <scene.blend> --python sets/mocap_test.py -- <out dir> host=111_37@0:2.6 hoorain=79_69@1:3 noraiz=49_02@2:3
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mocap  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
out = Path(args[0])
out.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
sc.render.fps = 25
O = bpy.data.objects
rigs = {"host": O["Armature"], "noraiz": O["noraiz_rig"],
        "hoorain": next(o for o in bpy.data.collections["CH-hoorain"].objects if o.type == "ARMATURE" and o.name.startswith("rig"))}
holders = {n: O[f"CH-{n}"] for n in rigs}
hp = rigs["hoorain"].pose.bones
for side in ("l", "r"):
    ik = hp.get(f"c_hand_ik.{side}")
    if ik is not None and "ik_fk_switch" in ik.keys():
        ik["ik_fk_switch"] = 1.0
longest = 0
for a in args[1:]:
    who, spec = a.split("=")
    clip, rng = spec.split("@")
    t0, dur = (float(x) for x in rng.split(":"))
    n = mocap.apply(rigs[who], who, mocap.CLIPS / f"{clip}.bvh", t0, dur, 1, holder=holders[who], blend=0.0,
                    root_bounce=0.6 if who != "host" else 0.0)
    longest = max(longest, int(dur * 25))
    print("APPLIED", who, clip, n, "bones")
# fast look
ee = sc.eevee
for attr, val in (("use_raytracing", False), ("taa_render_samples", 6)):
    if hasattr(ee, attr):
        setattr(ee, attr, val)
for o in O:
    if o.type == "LIGHT" and o.name != "sun":
        o.data.use_shadow = False
sc.camera = O["CAM-group"]
sc.render.resolution_x, sc.render.resolution_y = 960, 540
shots = []
for k in range(6):
    f = 1 + int(k * longest / 5)
    sc.frame_set(f)
    sc.render.filepath = str(out / f"m_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    shots.append(sc.render.filepath)
print("SHOTS", len(shots))
