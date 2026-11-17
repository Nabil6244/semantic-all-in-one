"""Graphics pass 2 check: chibi toys on the playground. Stills only.

blender -b -P toycolors/scene_toy.py -- OUT_DIR [--fast]
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from toycolors import kit, toy  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0] if argv else "toycolors/out/toy")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = kit.setup_render(fast="--fast" in argv)
toy.grade()
toy.playground()

yaw = math.radians(-58)
fleet = [("fire", (0.85, 0.04, 0.03), (0.30, 0.18, 0.08)), ("bus", (1.0, 0.74, 0.02), (0.15, 0.35, 0.75)),
         ("dump", (0.20, 0.72, 0.05), (0.35, 0.20, 0.08)), ("tanker", (0.05, 0.40, 0.95), (0.12, 0.35, 0.80)),
         ("crane", (1.0, 0.40, 0.02), (0.30, 0.18, 0.08))]
vs = []
for i, (k, c, ir) in enumerate(fleet):
    v = toy.chibi(k, c, loc=(-4.6 + i * 2.3, 1.2 - abs(i - 2) * 0.5, 0), yaw=yaw, iris=ir)
    vs.append(v)
# a stack of football-pattern balls next to the hero, like the counting songs
for k in range(3):
    toy.ball((1.0, 0.75, 0.02), (-1.6, -3.2, 0.45 + k * 0.88), r=0.45, name=f"ball{k}")
toy.ball((0.85, 0.04, 0.03), (2.6, -1.6, 0.45), r=0.45)
hero = toy.chibi("fire", (0.85, 0.04, 0.03), loc=(0.6, -3.0, 0), yaw=math.radians(-62), monster=True,
                 name="Rolly", iris=(0.30, 0.18, 0.08))
for v in vs + [hero]:
    for lk in v.looks:
        lk.rotation_euler = (0, math.radians(-6), math.radians(-14))

shots = {"toy_wide": ((1.6, -11.5, 2.0), (0.0, 0.0, 1.0), 38, vs[2].root, 4.0),
         "toy_hero": ((4.2, -8.6, 1.5), (0.5, -3.0, 1.35), 50, hero.root, 2.4)}
for name, (loc, aim, lens, focus, fstop) in shots.items():
    cam, tgt = kit.camera(loc, aim, lens=lens, dof_target=focus, fstop=fstop)
    sc.render.filepath = os.path.join(OUT, f"{name}.png")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)
    bpy.data.objects.remove(tgt)
