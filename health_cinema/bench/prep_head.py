"""Blender (background) asset prep for the brain/carotid/eye scene: Z-Anatomy Startup.blend -> lean layered head scene (head.blend, head.glb, anchors_head.json).
Run: Blender -b Startup.blend --python prep_head.py -- OUT_DIR.  Object names are the Z-Anatomy names; layers are empties named Layer_*.
Only structures present in the source are used (skull/cranium, neo-cortex gyri, cerebellum, brainstem, carotid/vertebral/basilar/cerebral arteries, eyes).
CC BY-SA derivative: local evaluation only."""
import json, sys, time, re
import bpy
from mathutils import Vector
OUT = sys.argv[sys.argv.index("--") + 1]; t0 = time.time()
def find(c, n):
    if c.name == n: return c
    for ch in c.children:
        r = find(ch, n)
        if r: return r
root = bpy.context.scene.collection
def meshes(cname, min_polys=60, skip=lambda o: False):
    c = find(root, cname); return [o for o in c.all_objects if o.type == "MESH" and len(o.data.polygons) >= min_polys and not o.name.endswith((".j", ".g", ".i", ".t")) and not skip(o)]
def mat(name, rgb, rough=0.5):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough; return m
M = {"bone": mat("HC_bone", (0.88, 0.84, 0.72)), "cortex": mat("HC_cortex", (0.80, 0.62, 0.62), 0.55), "cerebellum": mat("HC_cerebellum", (0.68, 0.52, 0.54), 0.55),
     "stem": mat("HC_stem", (0.76, 0.64, 0.58), 0.55), "artery": mat("HC_artery", (0.78, 0.10, 0.10), 0.4), "sclera": mat("HC_sclera", (0.93, 0.92, 0.9), 0.45),
     "cornea": mat("HC_cornea", (0.75, 0.85, 0.95), 0.2), "lens": mat("HC_lens", (0.9, 0.92, 1.0), 0.2), "retina": mat("HC_retina", (0.82, 0.42, 0.32), 0.5), "nerve": mat("HC_nerve", (0.95, 0.88, 0.6), 0.5)}
def dup(o):
    n = o.copy(); n.data = o.data.copy(); n.name = o.name; bpy.context.scene.collection.objects.link(n); n.parent = None; n.matrix_world = o.matrix_world.copy(); return n
def decimate(o, ratio):
    if ratio >= 0.999: return
    md = o.modifiers.new("d", "DECIMATE"); md.ratio = ratio
    with bpy.context.temp_override(object=o, active_object=o): bpy.ops.object.modifier_apply(modifier=md.name)
def fin(o, key):
    o.data.materials.clear(); o.data.materials.append(M[key])
    for p in o.data.polygons: p.use_smooth = True
    return o
L = {}
L["Layer_Skull"] = [fin((lambda n: (decimate(n, 0.45), n)[1])(dup(o)), "bone") for o in meshes("Cranium", 40)]
for o in [o for o in bpy.data.objects if o.type == "MESH" and re.match(r"vertebra c[1-7]\b", o.name.lower())]:
    L["Layer_Skull"].append(fin((lambda n: (decimate(n, 0.4), n)[1])(dup(o)), "bone"))
L["Layer_Cortex"] = [fin(dup(o), "cortex") for o in meshes("Neo-cortex", 100)]
bs = []
for o in meshes("Cerebellum", 100): n = dup(o); decimate(n, 0.5); bs.append(fin(n, "cerebellum"))
for o in meshes("Brainstem", 100): n = dup(o); decimate(n, 0.6); bs.append(fin(n, "stem"))
L["Layer_Cerebellum"] = bs
# arteries: curves -> evaluated meshes
dg = bpy.context.evaluated_depsgraph_get(); art = []
for o in bpy.data.objects:
    if o.type != "CURVE" or o.name.endswith((".t", ".g", ".j")): continue
    nm = o.name.lower()
    if any(x in nm for x in ("nerve", "vein", "plexus", "sinus")): continue
    if not any(x in nm for x in ("carotid", "vertebral artery", "basilar", "cerebral artery", "communicating artery", "cerebral arterial")): continue
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    if len(me.polygons) == 0: continue
    n = bpy.data.objects.new(o.name, me); n.matrix_world = o.matrix_world.copy(); bpy.context.scene.collection.objects.link(n); art.append(fin(n, "artery"))
L["Layer_Arteries"] = art
eyes = []
for o in [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) >= 100 and any(k in o.name.lower() for k in ("cornea", "lens.", "retina.", "segment of eyeball", "anterior chamber")) and not o.name.endswith((".j", ".g", ".i", ".t"))]:
    nm = o.name.lower(); k = "cornea" if "cornea" in nm else "lens" if nm.startswith("lens") else "retina" if "retina." in nm else "sclera"
    eyes.append(fin(dup(o), k))
for o in bpy.data.objects:
    if o.type == "CURVE" and o.name.startswith("Optic nerve"):
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        if len(me.polygons): n = bpy.data.objects.new(o.name, me); n.matrix_world = o.matrix_world.copy(); bpy.context.scene.collection.objects.link(n); eyes.append(fin(n, "nerve"))
L["Layer_Eyes"] = eyes
keep = {o for v in L.values() for o in v}
for o in list(bpy.data.objects):
    if o not in keep: bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections): bpy.data.collections.remove(c)
for me in list(bpy.data.meshes):
    if me.users == 0: bpy.data.meshes.remove(me)
for o in list(bpy.data.objects):
    n = re.sub(r"\.\d{3}$", "", o.name)
    if n != o.name and n not in bpy.data.objects: o.name = n
for name, objs in L.items():
    e = bpy.data.objects.new(name, None); bpy.context.scene.collection.objects.link(e)
    for o in objs: mw = o.matrix_world.copy(); o.parent = e; o.matrix_world = mw
def bb(objs):
    p = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = [min(q[i] for q in p) for i in range(3)]; mx = [max(q[i] for q in p) for i in range(3)]; return {"min": mn, "max": mx, "center": [(a + b) / 2 for a, b in zip(mn, mx)]}
sel = lambda objs, *keys: [o for o in objs if any(k in o.name.lower() for k in keys)]
A = {"head": bb(L["Layer_Skull"]), "brain": bb(L["Layer_Cortex"] + L["Layer_Cerebellum"]), "cortex": bb(L["Layer_Cortex"]), "cerebellum": bb(L["Layer_Cerebellum"]),
     "arteries": bb(L["Layer_Arteries"]), "eyes": bb(L["Layer_Eyes"])}
for key, kws in (("carotid_l", ("internal carotid artery.l", "common carotid artery")), ("carotid_r", ("internal carotid artery.r", "right common carotid"))):
    s = sel(L["Layer_Arteries"], *kws)
    if s: A[key] = bb(s)
for side in ("l", "r"):
    s = [o for o in L["Layer_Eyes"] if o.name.endswith("." + side) and "optic" not in o.name.lower()]
    if s: A["eye_" + side] = bb(s)
circ = sel(L["Layer_Arteries"], "anterior cerebral", "middle cerebral", "posterior cerebral", "basilar", "communicating")
if circ: A["circle_of_willis"] = bb(circ)
for o in L["Layer_Arteries"]: A["obj:" + o.name] = bb([o])
json.dump({"anchors": A, "layers": {k: [o.name for o in v] for k, v in L.items()}, "polys": {k: sum(len(o.data.polygons) for o in v) for k, v in L.items()}}, open(OUT + "/anchors_head.json", "w"), indent=1)
print("POLYS", {k: sum(len(o.data.polygons) for o in v) for k, v in L.items()}, "counts", {k: len(v) for k, v in L.items()})
bpy.ops.wm.save_as_mainfile(filepath=OUT + "/head.blend")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=OUT + "/head.glb", export_format="GLB", use_selection=False, export_apply=True, export_materials="EXPORT", export_cameras=False, export_lights=False, export_yup=True)
print("HEAD done sec", round(time.time() - t0, 1))
