"""Blender (background) prep: add the BodyParts3D kidneys, ureters and adrenal glands to the Health Cinema abdomen model.
Why: Z-Anatomy's own kidney is CC BY-NC (Lissie Cowley) and is excluded; the original BodyParts3D kidney (FMA7204/FMA7205) is CC BY 4.0
(The Database Center for Life Science), see https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html .
Run: Blender -b abdomen.blend --python prep_kidney.py -- OBJ_DIR OUT_DIR       (OBJ_DIR holds parts.json and partof_BP3D_4.0_obj_99/FJ*.obj for the kidneys, ureters, adrenals and the liver)
BodyParts3D meshes are in its own frame (mm): the liver, present in both models, is used to find the rotation/scale/offset into the abdomen model's frame, and the fit error
is printed (and stored in the anchors file) so a bad fit is visible."""
import itertools, json, math, sys, time
import bpy
from mathutils import Matrix, Vector
OBJ_DIR, OUT = sys.argv[sys.argv.index("--") + 1], sys.argv[sys.argv.index("--") + 2]; t0 = time.time()
PARTS_FJ = json.load(open(f"{OBJ_DIR}/parts.json"))      # BodyParts3D concept -> element files (partof_element_parts.txt): FMA7204/7205 kidneys, 15571/15572 ureters, 15629/15630 adrenals, 7197 liver
PARTS = {k: v for k, v in PARTS_FJ.items() if k != "liver"}
def load(fjs):
    new = []
    for fj in ([fjs] if isinstance(fjs, str) else fjs):
        before = set(bpy.data.objects); bpy.ops.wm.obj_import(filepath=f"{OBJ_DIR}/partof_BP3D_4.0_obj_99/{fj}.obj")
        new += [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    for o in new: o.select_set(False)
    return new
def bbox(objs, M=None):
    pts = [(M or Matrix.Identity(4)) @ o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]
target = [o for o in bpy.data.objects if o.name.rstrip("0123456789.").lower() == "liver" and o.type == "MESH"]
if not target: raise SystemExit("no Liver object in the abdomen model")
tmn, tmx = bbox(target)
liv = load(PARTS_FJ["liver"]); smn, smx = bbox(liv)
from mathutils.kdtree import KDTree
def verts(objs, step):
    out = []
    for o in objs:
        for k, v in enumerate(o.data.vertices):
            if k % step == 0: out.append(o.matrix_world @ v.co)
    return out
tv = verts(target, max(1, sum(len(o.data.vertices) for o in target) // 3000)); tree = KDTree(len(tv))
for i, p in enumerate(tv): tree.insert(p, i)
tree.balance(); tc = sum(tv, Vector()) / len(tv)
sv = verts(liv, max(1, sum(len(o.data.vertices) for o in liv) // 3000)); sc_ = sum(sv, Vector()) / len(sv)
ts = math.sqrt(sum((tmx[i] - tmn[i]) ** 2 for i in range(3))); ss = math.sqrt(sum((smx[i] - smn[i]) ** 2 for i in range(3))); s = ts / ss
cands = []
for perm in itertools.permutations(range(3)):
    for signs in itertools.product((1, -1), repeat=3):
        R = Matrix([[signs[r] if perm[r] == c else 0 for c in range(3)] for r in range(3)])
        if R.determinant() < 0: continue        # a mirror would flip left and right
        T = Matrix.Translation(tc - s * (R @ sc_)) @ Matrix.Scale(s, 4) @ R.to_4x4()
        err = sum(tree.find(T @ p)[2] for p in sv) / len(sv)         # mean distance from each BodyParts3D liver vertex to the Z-Anatomy liver surface points
        cands.append((err, T, perm, signs, s))
cands.sort(key=lambda c: c[0]); best = cands[0]
print("FIT candidates (mean vertex distance, m):", [round(c[0], 4) for c in cands[:3]], "of", len(cands))
if cands[1][0] < cands[0][0] * 1.25: raise SystemExit("the liver does not tell the orientations apart: refusing to place the kidneys")
err, T, perm, signs, s = best; print("FIT liver bbox err (m)", round(err, 4), "scale", s, "perm", perm, "signs", signs)
if err > 0.02: raise SystemExit(f"liver fit error {err:.3f} m is too large: refusing to place the kidneys")
for o in liv: bpy.data.objects.remove(o, do_unlink=True)
def mat(name, rgb, rough=0.5):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough; return m
M = {"kidney": mat("HC_kidney", (0.62, 0.22, 0.18), 0.45), "ureter": mat("HC_ureter", (0.93, 0.85, 0.55), 0.5), "adrenal": mat("HC_adrenal", (0.80, 0.60, 0.34), 0.55)}
group = []; made = {}
for key, fjs in PARTS.items():
    for o in load(fjs):
        o.matrix_world = T @ o.matrix_world; bpy.context.view_layer.update()
        o.name = {"kidney": "Kidney", "ureter": "Ureter", "adrenal": "Adrenal gland"}[key.split("_")[0]] + "." + key.split("_")[1]
        decimate = o.modifiers.new("d", "DECIMATE"); decimate.ratio = 0.5 if len(o.data.polygons) > 4000 else 1.0
        with bpy.context.temp_override(object=o, active_object=o): bpy.ops.object.modifier_apply(modifier=decimate.name)
        o.data.materials.clear(); o.data.materials.append(M[key.split("_")[0]])
        for p in o.data.polygons: p.use_smooth = True
        group.append(o); made.setdefault(key, []).append(o)
mn_r, mx_r = bbox(made["kidney_r"]); mn_l, mx_l = bbox(made["kidney_l"]); dx = -((mn_r[0] + mx_r[0]) / 2 + (mn_l[0] + mx_l[0]) / 2) / 2      # the two kidneys sit symmetrically either side of the midline (x = 0)
for o in group: o.location.x += dx
bpy.context.view_layer.update(); print("MIDLINE correction (m)", round(dx, 4))
e = bpy.data.objects.new("Layer_Urinary", None); bpy.context.scene.collection.objects.link(e)
for o in group: mw = o.matrix_world.copy(); o.parent = e; o.matrix_world = mw
def bb(objs):
    p = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = [min(q[i] for q in p) for i in range(3)]; mx = [max(q[i] for q in p) for i in range(3)]; return {"min": mn, "max": mx, "center": [(a + b) / 2 for a, b in zip(mn, mx)]}
A = json.load(open(f"{OUT}/anchors_abdomen.json")); an = A["anchors"]
for key in ("kidney_r", "kidney_l", "ureter_r", "ureter_l", "adrenal_r", "adrenal_l"): an[key] = bb(made[key])
an["kidneys"] = bb(made["kidney_r"] + made["kidney_l"]); an["urinary"] = bb(group + [o for o in bpy.data.objects if o.name.startswith("Urinary bladder")])
A["layers"]["Layer_Urinary"] = [o.name for o in group]; A["polys"]["Layer_Urinary"] = sum(len(o.data.polygons) for o in group)
A["kidney_source"] = {"model": "BodyParts3D 4.0 partof (99% reduction), FMA7204/FMA7205 + ureters + adrenal glands", "licence": "CC BY 4.0, (c) The Database Center for Life Science", "liver_fit_err_m": round(err, 4)}
json.dump(A, open(f"{OUT}/anchors_abdomen.json", "w"), indent=1)
print("URINARY", {k: [round(x, 3) for x in an[k]["center"]] for k in ("kidney_r", "kidney_l", "kidneys")}, "bladder z", [round(bb([o])["center"][2], 3) for o in bpy.data.objects if o.name.startswith("Urinary bladder")])
bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/abdomen.blend")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=f"{OUT}/abdomen.glb", export_format="GLB", use_selection=False, export_apply=True, export_materials="EXPORT", export_cameras=False, export_lights=False, export_yup=True)
print("KIDNEY done sec", round(time.time() - t0, 1))
