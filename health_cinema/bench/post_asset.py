"""Second prep step on chest.blend: canonical (suffix-free) object names, remove the stray geometry the muscle union carried to x<-0.45
(reference objects outside the body), re-export chest.glb and anchors.json.  Run: Blender -b chest.blend --python post_asset.py -- OUT_DIR"""
import json, sys, re
import bpy, bmesh
from mathutils import Vector
OUT = sys.argv[sys.argv.index("--") + 1]
for o in bpy.data.objects:
    n = re.sub(r"\.\d{3}$", "", o.name)
    if n != o.name and n not in bpy.data.objects: o.name = n
sh = bpy.data.objects["Body shell (derived)"]
bm = bmesh.new(); bm.from_mesh(sh.data)
import mathutils
if not sh.matrix_world.is_identity:
    bm.transform(sh.matrix_world); sh.matrix_world.identity()    # bake the transform left by the voxel remesh: vertices are in world space
if max(v.co.z for v in bm.verts) < 1.58:
    pass
if not sh.get("head_placeholder"):
    # The muscle union has no real face (mouth/eye cavities show as dark holes), so above the neck the shell is replaced by a smooth,
    # clearly generic head blank. It is a derived stand-in, not a skin or face mesh.
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z > 1.53], context="VERTS")
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=32, radius=1.0, matrix=mathutils.Matrix.Translation((0.0, 0.0, 1.615)) @ mathutils.Matrix.Diagonal((0.078, 0.098, 0.098, 1.0)))
    sh["head_placeholder"] = True
elif max(v.co.z for v in bm.verts) < 1.58:   # earlier run dropped the head island: add it back
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=32, radius=1.0, matrix=mathutils.Matrix.Translation((0.0, 0.0, 1.615)) @ mathutils.Matrix.Diagonal((0.078, 0.098, 0.098, 1.0)))
bad = [v for v in bm.verts if v.co.x < -0.45]
print("stray shell verts", len(bad))
bmesh.ops.delete(bm, geom=bad, context="VERTS")
# keep only the largest connected island (the body); everything else is stray
seen, islands = set(), []
for v in bm.verts:
    if v.index in seen: continue
    comp, stack = [], [v]; seen.add(v.index)
    while stack:
        c = stack.pop(); comp.append(c)
        for e in c.link_edges:
            o = e.other_vert(c)
            if o.index not in seen: seen.add(o.index); stack.append(o)
    islands.append(comp)
islands.sort(key=len, reverse=True); print("islands", [len(i) for i in islands[:6]], "total", len(islands))
bmesh.ops.delete(bm, geom=[v for i in islands[1:] if len(i) < 1000 for v in i], context="VERTS")   # keep body and head blank, drop specks
bm.to_mesh(sh.data); bm.free()
# trim vessels that leave the chest region (carotids to the head, palmar/plantar arches...): they only add edge clutter to the heart framing
_heart = [c for e in bpy.data.objects if e.name == "Layer_Heart" for c in e.children]
_pts = [o.matrix_world @ Vector(c) for o in _heart for c in o.bound_box]
_hcen = sum(_pts, Vector()) / len(_pts)
for e in [e for e in bpy.data.objects if e.name == "Layer_Vessels"]:
    for o in list(e.children):
        _c = sum((o.matrix_world @ Vector(c) for c in o.bound_box), Vector()) / 8
        if (_c - _hcen).length > 0.30 or any(k in o.name.lower() for k in ("carotid", "subclavian")):
            print("trim vessel", o.name, round((_c - _hcen).length, 2)); bpy.data.objects.remove(o, do_unlink=True)

# Cut-away interior: valves and papillary muscles move into their own layer (Layer_HeartInner) so they can be revealed with the cut;
# the cut chambers lose their flat cap faces so the inside of the chamber wall and those structures are visible (HeartCut renders double-sided).
_he = bpy.data.objects.get("Layer_Heart")
if "Layer_HeartInner" not in bpy.data.objects and _he:
    _in = bpy.data.objects.new("Layer_HeartInner", None); bpy.context.scene.collection.objects.link(_in)
    for o in list(_he.children):
        if "leaflet" in o.name.lower() or "papillary" in o.name.lower():
            mw = o.matrix_world.copy(); o.parent = _in; o.matrix_world = mw
_hcut = bpy.data.objects.get("Layer_HeartCut")
if _hcut and _hcut.get("capless") is None and _hcut.children:
    _ys = [(o.matrix_world @ Vector(c)).y for o in _hcut.children for c in o.bound_box]
    for o in _hcut.children:
        bm2 = bmesh.new(); bm2.from_mesh(o.data)
        ycut = max(v.co.y for v in bm2.verts) if False else None
        ys = sorted(v.co.y for v in bm2.verts); import collections
        cnt = collections.Counter(round(y, 4) for y in ys); ycap, n = cnt.most_common(1)[0]   # the cap plane holds many verts at one y
        caps = [f for f in bm2.faces if all(abs(v.co.y - ycap) < 2e-4 for v in f.verts)]
        print("cap", o.name, "y", ycap, "faces", len(caps)); bmesh.ops.delete(bm2, geom=caps, context="FACES_ONLY")
        bm2.to_mesh(o.data); bm2.free()
    _hcut["capless"] = True

def bb(objs):
    p = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = [min(q[i] for q in p) for i in range(3)]; mx = [max(q[i] for q in p) for i in range(3)]
    return {"min": mn, "max": mx, "center": [(a + b) / 2 for a, b in zip(mn, mx)]}
L = {e.name: [c for c in e.children] for e in bpy.data.objects if e.type == "EMPTY" and e.name.startswith("Layer_")}
A = {"body": bb(L["Layer_Skin"]), "chest": bb(L["Layer_Skeleton"] + L["Layer_Lungs"]), "heart": bb(L["Layer_Heart"]), "lungs": bb(L["Layer_Lungs"])}
for k in ("Layer_Heart", "Layer_HeartInner", "Layer_Vessels", "Layer_HeartCut"):
    for o in L[k]: A["obj:" + o.name] = bb([o])
json.dump({"anchors": A, "layers": {k: [o.name for o in v] for k, v in L.items()},
           "polys": {k: sum(len(o.data.polygons) for o in v) for k, v in L.items()}}, open(OUT + "/anchors.json", "w"), indent=1)
print("BODY", A["body"])
bpy.ops.wm.save_as_mainfile(filepath=OUT + "/chest.blend")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=OUT + "/chest.glb", export_format="GLB", use_selection=False, export_apply=True, export_materials="EXPORT", export_cameras=False, export_lights=False, export_yup=True)
