"""Render one scene template (one verse) as frames or quick stills.

blender -b -P toycolors/scene_template.py -- TEMPLATE COLOUR KIND OUT_DIR [--still 2.0,6.0] [--fast] [--from COLOUR]
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from toycolors import kit, templates, toy  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
name, colour, kind, out = argv[:4]
out = os.path.abspath(out)
os.makedirs(out, exist_ok=True)
still = [float(s) for s in argv[argv.index("--still") + 1].split(",")] if "--still" in argv else None
frm = argv[argv.index("--from") + 1] if "--from" in argv else None

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = kit.setup_render(fast="--fast" in argv)
info = templates.TEMPLATES[name](colour=colour, kind=kind, from_colour=frm)
toy.grade()
sc.camera.data.lens *= info.get("zoom", 1.0)          # chibi toys are small: frame them tighter
toy.playground(slides=info.get("slides", True), size=info.get("platform", (34, 20)))
sc.frame_start, sc.frame_end = 1, templates.F(info["dur"]) - 1
if "--frames" in argv:                                  # render only the first N frames (short tests)
    sc.frame_end = min(sc.frame_end, int(argv[argv.index("--frames") + 1]))
sc.render.image_settings.file_format = "PNG"
if still:
    for t in still:
        sc.frame_set(templates.F(t))
        sc.render.filepath = os.path.join(out, f"{name}_{colour}_{t:05.2f}.png")
        import time
        t_r = time.time()
        bpy.ops.render.render(write_still=True)
        print(f"RENDER_SECONDS {time.time() - t_r:.1f}")
else:
    sc.render.filepath = os.path.join(out, "f_")
    bpy.ops.render.render(animation=True)
