"""List the Z-Anatomy collection tree (name, depth, mesh/curve objects, polygons) so a prep script can pick structures by collection name.
Run: Blender -b Startup.blend --python dump_collections.py -- OUT.json"""
import json, sys
import bpy
OUT = sys.argv[sys.argv.index("--") + 1]
def walk(c, d=0):
    objs = list(c.objects)
    row = {"name": c.name, "depth": d, "meshes": sum(o.type == "MESH" for o in objs), "curves": sum(o.type == "CURVE" for o in objs), "polys": sum(len(o.data.polygons) for o in objs if o.type == "MESH"),
           "sample": [o.name for o in objs[:4]]}
    out = [row]
    for ch in c.children: out += walk(ch, d + 1)
    return out
json.dump(walk(bpy.context.scene.collection), open(OUT, "w"), indent=0)
objs = [{"n": o.name, "t": o.type, "p": len(o.data.polygons) if o.type == "MESH" else 0, "c": [c.name for c in o.users_collection][:1]} for o in bpy.data.objects]
json.dump(objs, open(OUT.replace(".json", "_objects.json"), "w"))
print("DUMP", OUT)
