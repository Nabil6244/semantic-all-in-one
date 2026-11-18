"""Render one story shot (toycolors/story_actions.py) as frames or quick stills, and write its sound events.

blender -b -P toycolors/story_scene.py -- SHOT.json OUT_DIR [--still 1.0,3.0] [--fast]
OUT_DIR gets f_0001.png ... (or still_<t>.png) and events.json.
"""
import json
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from toycolors import kit, story_actions as A, toy  # noqa: E402
from toycolors.templates import F  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
spec = json.load(open(argv[0]))
out = os.path.abspath(argv[1])
os.makedirs(out, exist_ok=True)
still = [float(s) for s in argv[argv.index("--still") + 1].split(",")] if "--still" in argv else None

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = kit.setup_render(fast="--fast" in argv)
ev = A.build_shot(spec)
toy.grade()
json.dump(ev, open(os.path.join(out, "events.json"), "w"))
sc.frame_start, sc.frame_end = 1, max(1, F(spec["dur"]) - 1)
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.compression = 0          # frames are encoded to mp4 and deleted: no time spent squeezing PNGs
if still:
    for t in still:
        sc.frame_set(F(t))
        sc.render.filepath = os.path.join(out, f"still_{t:05.2f}.png")
        t_r = time.time()
        bpy.ops.render.render(write_still=True)
        print(f"RENDER_SECONDS {time.time() - t_r:.1f}")
else:
    sc.render.filepath = os.path.join(out, "f_")
    bpy.ops.render.render(animation=True)
