"""Blender (background) asset prep for the Health Cinema 3D library: Z-Anatomy Startup.blend -> lean layered regional scenes.
Run: Blender -b Startup.blend --python prep_regions.py -- OUT_DIR abdomen|msk
  abdomen: liver, gallbladder, pancreas, spleen, stomach + oesophagus, duodenum/small/large bowel, bladder, abdominal vessels, lower ribs/lumbar spine/pelvis as context.
  msk:     full skeleton (decimated), intervertebral discs, ligaments, menisci; joint anchors (knee, hip, shoulder, elbow ...) from the articular capsules.
Writes OUT_DIR/<region>.glb and OUT_DIR/anchors_<region>.json (same format as chest/head: Layer_* empties, named anchors with min/max/center, layer->object names).
NOT used (licence): the kidneys and inner ear (Z-Anatomy credits them CC BY-NC / BY-NC-SA, not usable commercially). CC BY-SA 4.0 derivative: credit Z-Anatomy and BodyParts3D."""
import json, re, sys, time
import bpy
from mathutils import Vector
OUT, REGION = sys.argv[sys.argv.index("--") + 1], sys.argv[sys.argv.index("--") + 2]; t0 = time.time()
EXCLUDE = re.compile(r"kidney|renal|inner ear|cochlea|vestibul|semicircular")      # licence: never exported
def mat(name, rgb, rough=0.5):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough; return m
M = {"bone": mat("HC_bone", (0.88, 0.84, 0.72)), "liver": mat("HC_liver", (0.50, 0.14, 0.10), 0.45), "gall": mat("HC_gall", (0.22, 0.55, 0.26), 0.4), "pancreas": mat("HC_pancreas", (0.90, 0.70, 0.45), 0.55),
     "spleen": mat("HC_spleen", (0.45, 0.10, 0.22), 0.5), "stomach": mat("HC_stomach", (0.86, 0.46, 0.42), 0.5), "gut": mat("HC_gut", (0.88, 0.58, 0.52), 0.5), "bladder": mat("HC_bladder", (0.92, 0.82, 0.52), 0.4),
     "artery": mat("HC_artery", (0.78, 0.10, 0.10), 0.4), "vein": mat("HC_vein", (0.20, 0.30, 0.75), 0.4), "lig": mat("HC_lig", (0.95, 0.92, 0.78), 0.5), "menisc": mat("HC_meniscus", (0.55, 0.78, 0.92), 0.35),
     "disc": mat("HC_disc", (0.40, 0.70, 0.88), 0.4)}
def usable(o, min_polys=1):
    n = o.name.lower()
    return not EXCLUDE.search(n) and not n.endswith((".t", ".j", ".g", ".i", ".ol", ".or")) and ((o.type == "MESH" and len(o.data.polygons) >= min_polys) or o.type == "CURVE")
def by_name(pat, types=("MESH",), min_polys=1, side=None):
    rx = re.compile(pat, re.I); out = []
    for o in bpy.data.objects:
        if o.type in types and rx.search(o.name) and usable(o, min_polys):
            if side and not o.name.lower().endswith("." + side): continue
            out.append(o)
    return out
dg = bpy.context.evaluated_depsgraph_get()
def to_mesh(o):
    if o.type == "MESH": return o
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    if len(me.polygons) == 0: return None
    n = bpy.data.objects.new(o.name, me); n.matrix_world = o.matrix_world.copy(); bpy.context.scene.collection.objects.link(n); return n
def dup(o):
    if o.type == "CURVE": return to_mesh(o)
    n = o.copy(); n.data = o.data.copy(); n.name = o.name; bpy.context.scene.collection.objects.link(n); n.parent = None; n.matrix_world = o.matrix_world.copy(); return n
def decimate(o, ratio):
    if ratio >= 0.999 or len(o.data.polygons) < 300: return
    md = o.modifiers.new("d", "DECIMATE"); md.ratio = ratio
    with bpy.context.temp_override(object=o, active_object=o): bpy.ops.object.modifier_apply(modifier=md.name)
def fin(o, key, ratio=1.0):
    if o is None: return None
    decimate(o, ratio); o.data.materials.clear(); o.data.materials.append(M[key])
    for p in o.data.polygons: p.use_smooth = True
    return o
def bb(objs):
    objs = [o for o in objs if o is not None]
    if not objs: return None
    p = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = [min(q[i] for q in p) for i in range(3)]; mx = [max(q[i] for q in p) for i in range(3)]; return {"min": mn, "max": mx, "center": [(a + b) / 2 for a, b in zip(mn, mx)]}
L, A = {}, {}
def layer(name, objs): L[name] = [o for o in objs if o is not None]
if REGION == "abdomen":
    layer("Layer_Skeleton", [fin(dup(o), "bone", 0.3) for o in by_name(r"^(vertebra (t9|t10|t11|t12|l[1-5])|sacrum|hip bone\.[lr]|(seventh|eighth|ninth|tenth|eleventh|twelfth) rib\.[lr])$", min_polys=50)])
    layer("Layer_Liver", [fin(dup(o), "liver") for o in by_name(r"^liver$")] + [fin(dup(o), "gall") for o in by_name(r"^gallbladder$")])
    layer("Layer_Pancreas", [fin(dup(o), "pancreas") for o in by_name(r"^pancreas$")])
    layer("Layer_Spleen", [fin(dup(o), "spleen") for o in by_name(r"^spleen$")])
    layer("Layer_Stomach", [fin(dup(o), "stomach") for o in by_name(r"^stomach$")] + [fin(dup(o), "stomach") for o in by_name(r"^oesophagus$", ("CURVE",))])
    layer("Layer_Intestines", [fin(dup(o), "gut") for o in by_name(r"^(duodenum|ascending colon|transverse colon|descending colon|sigmoid colon|vermiform appendix|caecum)$")] +
          [fin(dup(o), "gut") for o in by_name(r"^(jejunum|ileum)$", ("CURVE",))])
    layer("Layer_Bladder", [fin(dup(o), "bladder") for o in by_name(r"^urinary bladder$")])
    art = [fin(dup(o), "artery") for o in by_name(r"^(abdominal aorta|coeliac trunk|celiac trunk|hepatic artery|common hepatic|splenic artery|superior mesenteric artery|inferior mesenteric artery)", ("CURVE",))]
    vein = [fin(dup(o), "vein") for o in by_name(r"^(inferior vena cava|portal vein|hepatic vein|splenic vein|superior mesenteric vein|inferior mesenteric vein)", ("CURVE",))]
    layer("Layer_Vessels", art + vein)
elif REGION == "msk":
    skel = [o for o in bpy.data.objects if o.type == "MESH" and o.users_collection and "skeletal system" in o.users_collection[0].name.lower() and usable(o, 40)]
    layer("Layer_Skeleton", [fin(dup(o), "bone", 0.22) for o in skel])
    layer("Layer_Discs", [fin(dup(o), "disc", 0.5) for o in by_name(r"^intervertebral disc", min_polys=100)])
    layer("Layer_Ligaments", [fin(dup(o), "lig") for o in by_name(r"ligament", min_polys=20) if "line" not in o.name.lower()])
    layer("Layer_Menisci", [fin(dup(o), "menisc") for o in by_name(r"meniscus")])
else: raise SystemExit("region must be abdomen or msk")
# anchors from the SOURCE objects (capsules, bones) before anything is removed
def anc(name, objs):
    b = bb(objs)
    if b: A[name] = b
if REGION == "abdomen":
    for key, lay in (("liver", "Layer_Liver"), ("pancreas", "Layer_Pancreas"), ("spleen", "Layer_Spleen"), ("stomach", "Layer_Stomach"), ("intestines", "Layer_Intestines"), ("bladder", "Layer_Bladder"), ("vessels", "Layer_Vessels"), ("skeleton", "Layer_Skeleton")): anc(key, L[lay])
    anc("gallbladder", [o for o in L["Layer_Liver"] if re.sub(r"\.\d{3}$", "", o.name.lower()) == "gallbladder"])
    anc("liver_only", [o for o in L["Layer_Liver"] if re.sub(r"\.\d{3}$", "", o.name.lower()) == "liver"])
    anc("abdomen", [o for v in L.values() for o in v])
else:
    anc("skeleton", L["Layer_Skeleton"]); anc("spine", [o for o in L["Layer_Skeleton"] if re.match(r"(vertebra|sacrum)", o.name.lower())]); anc("discs", L["Layer_Discs"])
    for joint, rx in (("knee", r"articular capsule of knee joint"), ("hip", r"articular capsule of hip joint"), ("shoulder", r"articular capsule of glenohumeral joint"), ("elbow", r"articular capsule of elbow joint"),
                      ("wrist", r"articular capsule of radiocarpal joint")):
        for side in ("l", "r"): anc(f"{joint}_{side}", by_name(rx, side=side))
    for key in ("ligaments", "menisci"): anc(key, L["Layer_" + key.capitalize()])
for lname, objs in L.items():
    for o in objs: A["obj:" + o.name] = bb([o]) if len(objs) < 60 else A.get("obj:" + o.name)
A = {k: v for k, v in A.items() if v}
keep = {o for v in L.values() for o in v}
for o in list(bpy.data.objects):
    if o not in keep: bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections): bpy.data.collections.remove(c)
for o in list(bpy.data.objects):      # the originals are gone: give the copies their Z-Anatomy names back
    n = re.sub(r"\.\d{3}$", "", o.name)
    if n != o.name and n not in bpy.data.objects: o.name = n
for me in list(bpy.data.meshes):
    if me.users == 0: bpy.data.meshes.remove(me)
for name, objs in L.items():
    e = bpy.data.objects.new(name, None); bpy.context.scene.collection.objects.link(e)
    for o in objs: mw = o.matrix_world.copy(); o.parent = e; o.matrix_world = mw
polys = {k: sum(len(o.data.polygons) for o in v) for k, v in L.items()}
json.dump({"anchors": A, "layers": {k: [o.name for o in v] for k, v in L.items()}, "polys": polys}, open(f"{OUT}/anchors_{REGION}.json", "w"), indent=1)
print("POLYS", polys, "counts", {k: len(v) for k, v in L.items()}, "anchors", len(A))
bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/{REGION}.blend")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=f"{OUT}/{REGION}.glb", export_format="GLB", use_selection=False, export_apply=True, export_materials="EXPORT", export_cameras=False, export_lights=False, export_yup=True)
print("REGION", REGION, "done sec", round(time.time() - t0, 1))
