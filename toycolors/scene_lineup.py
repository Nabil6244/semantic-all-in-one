"""Vehicle line-up stills to check the kit: all six vehicles in the park, plus a face close-up.

blender -b -P toycolors/scene_lineup.py -- OUT_DIR [--fast]
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from toycolors import kit  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0] if argv else "toycolors/out/lineup")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = kit.setup_render(fast="--fast" in argv)
kit.park_world()

yaw = math.radians(-35)   # noses angled toward the camera
fleet = [("car", (0.85, 0.04, 0.03)), ("bus", (0.98, 0.70, 0.03)), ("monster", (0.12, 0.62, 0.05)),
         ("van", (0.95, 0.95, 0.95)), ("dump", (0.05, 0.22, 0.85)), ("fire", (0.85, 0.05, 0.05))]
xs = [-9.0, -5.6, -1.4, 2.6, 6.4, 10.6]
vs = [kit.vehicle(k, c, loc=(x, 0, 0), yaw=yaw) for (k, c), x in zip(fleet, xs)]
mon = vs[2]

# eyes look a little toward the camera
for v in vs:
    for lk in v.looks:
        lk.rotation_euler = (math.radians(-6), math.radians(-12), 0)

shots = {
    "wide": ((0.8, -16.0, 2.6), (0.8, 0, 1.2), 30, None),
    "monster_face": ((2.4, -5.2, 2.1), (-1.0, -0.3, 1.9), 50, mon.root),
}
for name, (loc, aim, lens, focus) in shots.items():
    cam, tgt = kit.camera(loc, aim, lens=lens, dof_target=focus, fstop=2.0)
    sc.render.filepath = os.path.join(OUT, f"{name}.png")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)
    bpy.data.objects.remove(tgt)
