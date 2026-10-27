"""Blender (background) asset prep for the Health Cinema benchmark: Z-Anatomy Startup.blend -> lean layered chest scene.

Run: Blender -b Startup.blend --python prep_asset.py -- OUT_DIR
Writes OUT_DIR/chest.blend, OUT_DIR/chest.glb, OUT_DIR/anchors.json. Object names are the Z-Anatomy names (anatomical identity kept);
layers are empties Layer_* so visibility can be driven by name. Materials are replaced by plain PBR ones (the originals are node groups
that no exporter carries). Derived from CC BY-SA 4.0 material: local evaluation only until licensing is resolved.
"""
import json, sys, time
import bpy, bmesh
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1]
t0 = time.time()

def find(c, name):
    if c.name == name: return c
    for ch in c.children:
        r = find(ch, name)
        if r: return r

root = bpy.context.scene.collection
def meshes_in(cname, pred=lambda o: True, min_polys=1):
    c = find(root, cname)
    return [o for o in c.all_objects if o.type == "MESH" and len(o.data.polygons) >= min_polys and pred(o)]

def mat(name, rgb, rough=0.45, alpha=1.0, sss=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough
    try: b.inputs["Subsurface Weight"].default_value = sss
    except KeyError: pass
    return m
M = {
    "shell": mat("HC_shell", (0.86, 0.62, 0.52), 0.55, sss=0.25),
    "muscle": mat("HC_muscle", (0.55, 0.11, 0.09), 0.5),
    "bone": mat("HC_bone", (0.88, 0.84, 0.72), 0.5),
    "lung": mat("HC_lung", (0.78, 0.46, 0.46), 0.6),
    "heart_L": mat("HC_heart_left", (0.72, 0.10, 0.12), 0.35),
    "heart_R": mat("HC_heart_right", (0.30, 0.34, 0.72), 0.35),
    "valve": mat("HC_valve", (0.93, 0.88, 0.74), 0.4),
    "papillary": mat("HC_papillary", (0.80, 0.42, 0.40), 0.5),
    "artery": mat("HC_artery", (0.78, 0.10, 0.10), 0.35),
    "vein": mat("HC_vein", (0.25, 0.30, 0.68), 0.35),
    "thymus": mat("HC_thymus", (0.86, 0.78, 0.55), 0.6),
}

def dup(o):
    n = o.copy(); n.data = o.data.copy(); n.name = o.name
    bpy.context.scene.collection.objects.link(n); n.parent = None
    n.matrix_world = o.matrix_world.copy()
    return n

def decimate(o, ratio):
    if ratio >= 0.999: return
    md = o.modifiers.new("d", "DECIMATE"); md.ratio = ratio
    bpy.context.view_layer.objects.active = o
    with bpy.context.temp_override(object=o, active_object=o): bpy.ops.object.modifier_apply(modifier=md.name)

def finish(o, key, smooth=True):
    o.data.materials.clear(); o.data.materials.append(M[key])
    if smooth:
        for p in o.data.polygons: p.use_smooth = True
    return o

L = {}   # layer name -> list of objects
src = {}
# --- skeleton of the thorax: ribs, sternum, clavicles, thoracic spine (decimated)
sk = []
for o in meshes_in("1: Skeletal system", lambda o: any(k in o.name.lower() for k in ("rib", "sternum", "clavicle", "vertebra t", "vertebra c7", "scapula")), 50):
    n = dup(o); decimate(n, 0.35); sk.append(finish(n, "bone"))
L["Layer_Skeleton"] = sk
# --- muscles of the chest wall
mu = []
for o in meshes_in("4: Muscular system", lambda o: any(k in o.name.lower() for k in ("pectoralis", "serratus anterior", "intercostal", "diaphragm")) and "(" not in o.name, 50):
    n = dup(o); decimate(n, 0.5); mu.append(finish(n, "muscle"))
L["Layer_Muscle"] = mu
# --- body shell: voxel-remesh of the union of all muscles (the model has no skin mesh)
t1 = time.time()
allm = [dup(o) for o in meshes_in("4: Muscular system", lambda o: "(" not in o.name, 20)]
for o in allm:
    for p in o.data.polygons: pass
bpy.ops.object.select_all(action="DESELECT")
for o in allm: o.select_set(True)
bpy.context.view_layer.objects.active = allm[0]
_join = bpy.ops.object.join; _join()   # a Blender operator, not a wait
shell = bpy.context.view_layer.objects.active; shell.name = "Body shell (derived)"
shell.data.remesh_voxel_size = 0.006
bpy.ops.object.voxel_remesh()
md = shell.modifiers.new("s", "CORRECTIVE_SMOOTH") if False else shell.modifiers.new("s", "SMOOTH")
md.factor = 0.8; md.iterations = 6
with bpy.context.temp_override(object=shell, active_object=shell): bpy.ops.object.modifier_apply(modifier=md.name)
shell_polys_raw = len(shell.data.polygons)
decimate(shell, min(1.0, 90000 / max(1, shell_polys_raw)))
finish(shell, "shell"); L["Layer_Skin"] = [shell]
print("SHELL polys raw", shell_polys_raw, "final", len(shell.data.polygons), "sec", round(time.time() - t1, 1))
# --- lungs, trachea, thymus, pleura-free
lu = []
for o in meshes_in("8: Visceral systems", lambda o: "lobe of" in o.name.lower() and "lung" in o.name.lower(), 50):
    n = dup(o)
    md = n.modifiers.new("ss", "SUBSURF"); md.levels = 2; md.render_levels = 2
    with bpy.context.temp_override(object=n, active_object=n): bpy.ops.object.modifier_apply(modifier=md.name)
    lu.append(finish(n, "lung"))
for o in meshes_in("8: Visceral systems", lambda o: o.name == "Trachea", 50):
    lu.append(finish(dup(o), "lung"))
L["Layer_Lungs"] = lu
for o in meshes_in("6: Lymphoid organs", lambda o: "thymus" in o.name.lower(), 50):
    L["Layer_Lungs"].append(finish(dup(o), "thymus"))
# --- heart
heart = []
hcol = find(root, "Heart")
for o in hcol.all_objects:
    if o.type != "MESH" or len(o.data.polygons) < 50: continue
    n = dup(o); nm = o.name.lower()
    if "leaflet" in nm: k = "valve"
    elif "papillary" in nm: k = "papillary"
    elif "left" in nm: k = "heart_L"
    else: k = "heart_R"
    heart.append(finish(n, k))
L["Layer_Heart"] = heart
# --- great vessels / coronaries (curves -> evaluated meshes)
ves = []
dg = bpy.context.evaluated_depsgraph_get()
for o in find(root, "5: Cardiovascular system").all_objects:
    if o.type == "CURVE" and not o.name.endswith((".t", ".g", ".j")):
        nm = o.name.lower()
        if not any(k in nm for k in ("aorta", "vena cava", "pulmonary", "coronary", "arch", "brachiocephalic", "subclavian", "carotid")): continue
        if "abdominal" in nm: continue
        ev = o.evaluated_get(dg); me = bpy.data.meshes.new_from_object(ev)
        if len(me.polygons) == 0: continue
        n = bpy.data.objects.new(o.name, me); n.matrix_world = o.matrix_world.copy(); bpy.context.scene.collection.objects.link(n)
        ves.append(finish(n, "vein" if any(k in nm for k in ("vena", "vein", "sinus")) else "artery"))
for o in meshes_in("5: Cardiovascular system", lambda o: o.name == "Pulmonary trunk", 10):
    ves.append(finish(dup(o), "vein"))
L["Layer_Vessels"] = ves

# --- heart cutaway: coronal bisect of the chambers, anterior half removed (new objects, originals kept)
hb = Vector((0, 0, 0)); pts = []
for o in heart:
    for c in o.bound_box: pts.append(o.matrix_world @ Vector(c))
hmin = Vector((min(p[i] for p in pts) for i in range(3))); hmax = Vector((max(p[i] for p in pts) for i in range(3)))
hc = (hmin + hmax) / 2
cut = []
for o in heart:
    if o.name.split()[0] in ("Right", "Left") and "ventricle" in o.name.lower() or "atrium" in o.name.lower():
        if "papillary" in o.name.lower() or "leaflet" in o.name.lower(): continue
        n = o.copy(); n.data = o.data.copy(); n.name = o.name + " [cut]"; bpy.context.scene.collection.objects.link(n)
        bm = bmesh.new(); bm.from_mesh(n.data); bm.transform(n.matrix_world); n.matrix_world.identity()
        g = bm.verts[:] + bm.edges[:] + bm.faces[:]
        r = bmesh.ops.bisect_plane(bm, geom=g, plane_co=(0, hc.y + 0.004, 0), plane_no=(0, 1, 0), clear_inner=True, clear_outer=False)
        edges = [e for e in r["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        try: bmesh.ops.holes_fill(bm, edges=edges, sides=64)
        except Exception as ex: print("fill fail", n.name, ex)
        bm.to_mesh(n.data); bm.free()
        finish(n, "heart_L" if "left" in o.name.lower() else "heart_R"); cut.append(n)
L["Layer_HeartCut"] = cut

# --- delete everything not ours
keep = {o for v in L.values() for o in v}
for o in list(bpy.data.objects):
    if o not in keep: bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections): bpy.data.collections.remove(c)
for me in list(bpy.data.meshes):
    if me.users == 0: bpy.data.meshes.remove(me)
# layers as empties
bpy.context.scene.collection.children  # ensure scene collection
for name, objs in L.items():
    e = bpy.data.objects.new(name, None); bpy.context.scene.collection.objects.link(e)
    for o in objs:
        mw = o.matrix_world.copy(); o.parent = e; o.matrix_world = mw
for c in ("Camera", "Light"): pass

# anchors (world space, Blender Z-up, front = -Y)
def bb(objs):
    p = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = [min(q[i] for q in p) for i in range(3)]; mx = [max(q[i] for q in p) for i in range(3)]
    return {"min": mn, "max": mx, "center": [(a + b) / 2 for a, b in zip(mn, mx)]}
A = {"body": bb(L["Layer_Skin"]), "chest": bb(L["Layer_Skeleton"] + L["Layer_Lungs"]), "heart": bb(L["Layer_Heart"]), "lungs": bb(L["Layer_Lungs"])}
for o in L["Layer_Heart"]: A["obj:" + o.name] = bb([o])
for o in L["Layer_Vessels"]: A["obj:" + o.name] = bb([o])
json.dump({"anchors": A, "layers": {k: [o.name for o in v] for k, v in L.items()},
           "polys": {k: sum(len(o.data.polygons) for o in v) for k, v in L.items()}}, open(OUT + "/anchors.json", "w"), indent=1)
print("POLYS", {k: sum(len(o.data.polygons) for o in v) for k, v in L.items()})
bpy.ops.wm.save_as_mainfile(filepath=OUT + "/chest.blend")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=OUT + "/chest.glb", export_format="GLB", use_selection=False, export_apply=True,
                          export_materials="EXPORT", export_cameras=False, export_lights=False, export_yup=True)
print("PREP done sec", round(time.time() - t0, 1))
