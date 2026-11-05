"""Quick full-body look: blender -b build/host_stage3c.blend --python host/stage3_check.py -- tag"""
import math, os, sys
import bpy, mathutils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD, shot, studio
tag = sys.argv[sys.argv.index("--") + 1]
studio()
for az, n in ((0, "f"), (40, "q"), (90, "s"), (180, "b")):
    shot(os.path.join(BUILD, f"chk_{tag}_{n}.png"), (0, 0, 0.84), 5.2, az, lens=85, res=(420, 760))
