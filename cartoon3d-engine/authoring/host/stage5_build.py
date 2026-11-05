"""Stage 5: make the accepted Gate 4 host light enough for the app. Trims body skin hidden under the clothes,
resizes textures to the plan's budget and exports colour maps as JPEG (maps with alpha stay PNG).
Run: blender -b -noaudio build/revisions/k3_gate4/stage4_k3.blend --python host/stage5_build.py -- f1
Reads the frozen Gate 4 file, writes only to build/stage5/<tag>/ and build/stage5/stage5_<tag>.blend."""
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD

TAG = sys.argv[sys.argv.index("--") + 1]
OUT = os.path.join(BUILD, "stage5", TAG); os.makedirs(OUT, exist_ok=True)
EXPORT = ["cand_head", "cand_mouth", "cand_teeth_up", "cand_teeth_low", "cand_tongue", "concept_eyes", "concept_brows", "concept_band", "concept_tie", "host_hair_low",
          "host_body", "host_shoes", "host_tee", "host_overalls", "host_pocket", "host_strap_L", "host_strap_R", "host_buttons", "host_stitch"]
CLOTH = ["host_tee", "host_overalls", "host_shoes", "host_pocket", "host_strap_L", "host_strap_R"]
tris = lambda n: sum(len(p.vertices) - 2 for p in bpy.data.objects[n].data.polygons)
before = {n: tris(n) for n in EXPORT}

# ---- 1. body skin that the clothes cover in every direction we test is never seen: drop it
for p in bpy.context.scene.objects:
    if p.type == "ARMATURE":
        for pb in p.pose.bones:
            pb.matrix_basis.identity()
bpy.context.view_layer.update()
pts, polys = [], []
for n in CLOTH:
    me = bpy.data.objects[n].data; o0 = len(pts)
    pts += [tuple(v.co) for v in me.vertices]; polys += [tuple(i + o0 for i in p.vertices) for p in me.polygons]
bvh = BVHTree.FromPolygons(pts, polys)
body = bpy.data.objects["host_body"]; bm = bmesh.new(); bm.from_mesh(body.data); bm.verts.ensure_lookup_table(); bm.normal_update()
REACH = 0.06


def covered(v):
    n = v.normal
    if n.length < 0.5:
        return False
    t1 = n.orthogonal().normalized(); t2 = n.cross(t1)
    for d in (n, (n + 0.5 * t1).normalized(), (n - 0.5 * t1).normalized(), (n + 0.5 * t2).normalized(), (n - 0.5 * t2).normalized()):
        hit = bvh.ray_cast(v.co + d * 0.0005, d, REACH)
        if hit[0] is None:
            return False
    return True


hid = np.array([covered(v) for v in bm.verts])
for _ in range(2):                                 # keep two rings of margin next to anything visible (armholes, hems, neck)
    hid = np.array([hid[v.index] and all(hid[e.other_vert(v).index] for e in v.link_edges) for v in bm.verts])
gone = [f for f in bm.faces if all(hid[v.index] for v in f.verts)]
bmesh.ops.delete(bm, geom=gone, context="FACES")
loose = [v for v in bm.verts if not v.link_faces]
bmesh.ops.delete(bm, geom=loose, context="VERTS")
bm.to_mesh(body.data); bm.free()
print("REPORT body tris", before["host_body"], "->", tris("host_body"))

# ---- 2. textures to budget
SIZE = {"cand_skin": 2048, "skin_rough": 512, "hair_low_col": 1024, "hair_low_nrm": 1024, "brow_soft": None, "eye_h": None}
used = set()
for n in EXPORT:
    for m in bpy.data.objects[n].data.materials:
        if m and m.use_nodes:
            used |= {nd.image for nd in m.node_tree.nodes if nd.type == "TEX_IMAGE" and nd.image}
for img in sorted(used, key=lambda i: i.name):
    w, h = img.size; nm = img.name.lower()
    tgt = SIZE.get(img.name, 512 if ("rough" in nm or nm.endswith("_r")) else 1024)
    if tgt and max(w, h) > tgt:
        f = tgt / max(w, h); img.scale(max(1, int(w * f)), max(1, int(h * f)))
    print("REPORT image", img.name, (w, h), "->", tuple(img.size), "alpha" if img.alpha_mode != "NONE" and img.depth in (32, 128) else "")

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "stage5", f"stage5_{TAG}.blend"), copy=True)

# ---- 3. export
for o in bpy.context.selected_objects:
    o.select_set(False)
bpy.data.objects["host_rig"].select_set(True)
for n in EXPORT:
    bpy.data.objects[n].select_set(True)
glb = os.path.join(OUT, "host.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=False, export_skins=True, export_all_influences=False,
                          export_morph=True, export_morph_normal=True, export_try_sparse_sk=True, export_animations=False,
                          export_image_format="JPEG", export_image_quality=90, export_yup=True)
after = {n: tris(n) for n in EXPORT}
print("REPORT glb KB", os.path.getsize(glb) // 1024, "tris", sum(before.values()), "->", sum(after.values()))
print("STAGE5 DONE")
