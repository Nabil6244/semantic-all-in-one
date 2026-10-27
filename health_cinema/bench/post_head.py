"""Fix-up on head.blend: drop non-eye objects the first selection caught (retinaculum), recompute anchors, re-export head.glb.
Run: Blender -b head.blend --python post_head.py -- OUT_DIR"""
import json, sys
import bpy
from mathutils import Vector
OUT = sys.argv[sys.argv.index("--") + 1]
eyes = bpy.data.objects["Layer_Eyes"]
for o in list(eyes.children):
    if "retinaculum" in o.name.lower(): bpy.data.objects.remove(o, do_unlink=True)
for me in list(bpy.data.meshes):
    if me.users == 0: bpy.data.meshes.remove(me)
L = {e.name: list(e.children) for e in bpy.data.objects if e.type == "EMPTY" and e.name.startswith("Layer_")}
def bb(objs):
    p = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = [min(q[i] for q in p) for i in range(3)]; mx = [max(q[i] for q in p) for i in range(3)]; return {"min": mn, "max": mx, "center": [(a + b) / 2 for a, b in zip(mn, mx)]}
A = json.load(open(OUT + "/anchors_head.json")); an = A["anchors"]
an["eyes"] = bb(L["Layer_Eyes"])
for side in ("l", "r"):
    s = [o for o in L["Layer_Eyes"] if o.name.endswith("." + side) and "optic" not in o.name.lower()]
    if s: an["eye_" + side] = bb(s)
for o in L["Layer_Eyes"]: an["obj:" + o.name] = bb([o])
A["layers"] = {k: [o.name for o in v] for k, v in L.items()}; A["polys"] = {k: sum(len(o.data.polygons) for o in v if o.type == "MESH") for k, v in L.items()}
json.dump(A, open(OUT + "/anchors_head.json", "w"), indent=1)
print("EYES", [o.name for o in L["Layer_Eyes"]], an["eye_l"]["center"], an["eye_r"]["center"])
bpy.ops.wm.save_as_mainfile(filepath=OUT + "/head.blend")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=OUT + "/head.glb", export_format="GLB", use_selection=False, export_apply=True, export_materials="EXPORT", export_cameras=False, export_lights=False, export_yup=True)
print("POST done")
