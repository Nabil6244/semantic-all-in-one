"""Stage 3: fit the 166-bone rig to the h10 head, skin head/hair/eyes/teeth, trim the old body head, export a skinned GLB, render Gate 3 poses.
Run: blender -b -noaudio build/revisions/s7_gate2/stage2_s7.blend --python host/stage3_rig.py -- g1
Reads the frozen Gate 2 file, writes only to build/stage3/<tag>/ and build/stage3/stage3_<tag>.blend."""
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD, Binder, shot

TAG = sys.argv[sys.argv.index("--") + 1]
OUT = os.path.join(BUILD, "stage3", TAG); os.makedirs(OUT, exist_ok=True)
s = bpy.context.scene
rig = bpy.data.objects["host_rig"]; body = bpy.data.objects["host_body"]
HEADPARTS = ["cand_head", "cand_mouth", "cand_teeth_up", "cand_teeth_low", "cand_tongue", "concept_eyes", "concept_brows", "concept_band", "concept_tie", "host_hair_low"]
OBJ = {n: bpy.data.objects[n] for n in HEADPARTS}


def wco(o):
    a = np.zeros(len(o.data.vertices) * 3); o.data.vertices.foreach_get("co", a); return a.reshape(-1, 3)


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)


# ---- 1. bake the head parts' -0.036 offset into the mesh so object space = rig space
for o in bpy.context.selected_objects:
    o.select_set(False)
for o in OBJ.values():
    o.select_set(True)
bpy.context.view_layer.objects.active = OBJ["cand_head"]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# ---- 2. landmarks on h10
eyes = wco(OBJ["concept_eyes"])
EYE = {sd: (eyes[eyes[:, 0] * sg > 0].min(0) + eyes[eyes[:, 0] * sg > 0].max(0)) / 2 for sd, sg in (("L", 1), ("R", -1))}
hair = wco(OBJ["host_hair_low"])
tie = wco(OBJ["concept_tie"]); TIE = (tie.min(0) + tie.max(0)) / 2


def centre(z0, z1):
    p = hair[(hair[:, 1] > 0.12) & (hair[:, 2] >= z0) & (hair[:, 2] < z1)]; return p.mean(0)


PT = [np.array([TIE[0] * 0.5, 0.125, 1.505]), centre(1.43, 1.47), centre(1.29, 1.33), np.array([*centre(1.146, 1.18)[:2], 1.15])]
OLD_EYE_Z, OLD_EYE_X = 1.49, 0.05
AX = EYE["L"][0] / OLD_EYE_X; DZ = EYE["L"][2] - OLD_EYE_Z
face = lambda p: np.array([p[0] * AX, p[1], p[2] + DZ])          # old r5 face -> h10 face
print("REPORT eye", EYE["L"].round(4), "face x-scale %.3f z-shift %.4f" % (AX, DZ), "ponytail", [p.round(3) for p in PT])

# ---- 3. fit bones
bpy.context.view_layer.objects.active = rig
for o in bpy.context.selected_objects:
    o.select_set(False)
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
eb = rig.data.edit_bones
old = {b.name: (np.array(b.head), np.array(b.tail)) for b in eb}


def under(name, root):
    b = eb[name]
    while b:
        if b.name == root:
            return True
        b = b.parent
    return False


new = {}
for b in eb:
    h, t = old[b.name]
    if b.name.startswith("ponytail"):
        k = int(b.name[-1]) - 1; new[b.name] = (PT[k], PT[k + 1])
    elif b.name in ("eye.L", "eye.R"):
        c = EYE[b.name[-1]]; new[b.name] = (c, c + (t - h))
    elif b.name == "head" or under(b.name, "head"):
        new[b.name] = (face(h), face(t))
HH = new["head"][0]
n01 = old["neck01"][0]
for i, n in enumerate(("neck01", "neck02", "neck03")):
    new[n] = (n01 + (HH - n01) * i / 3, n01 + (HH - n01) * (i + 1) / 3)
for n, (h, t) in new.items():
    eb[n].head = Vector(h); eb[n].tail = Vector(t)
bad = [(b.name, round((b.head - b.parent.tail).length, 4)) for b in eb if b.use_connect and (b.head - b.parent.tail).length > 1e-4]
bpy.ops.object.mode_set(mode="OBJECT")
print("REPORT bones moved", len(new), "connect mismatches", bad)
B = {b.name: np.array(b.head_local) for b in rig.data.bones}

# ---- 4. weights
binder = Binder(body, rig)                     # before the body is trimmed


def write(o, W):
    """W: {bone: (n,) weights}; normalised, max 4 per vertex."""
    for g in list(o.vertex_groups):
        o.vertex_groups.remove(g)
    bm = bmesh.new(); bm.from_mesh(o.data)        # wrapped meshes keep stale weight entries (indices up to 255) with no groups: drop them
    for lay in list(bm.verts.layers.deform.values()):
        bm.verts.layers.deform.remove(lay)
    bm.to_mesh(o.data); bm.free()
    names = list(W); M = np.stack([W[n] for n in names], 1)
    order = np.argsort(-M, 1)[:, 4:]
    np.put_along_axis(M, order, 0, 1)
    M = M / np.maximum(M.sum(1, keepdims=True), 1e-9)
    for j, n in enumerate(names):
        idx = np.nonzero(M[:, j] > 1e-4)[0]
        if len(idx):
            g = o.vertex_groups.new(name=n)
            for i in idx:
                g.add([int(i)], float(M[i, j]), "REPLACE")
    o.parent = rig; o.matrix_parent_inverse = rig.matrix_world.inverted()
    m = o.modifiers.new("Armature", "ARMATURE"); m.object = rig
    print("REPORT skin", o.name, {n: int((W[n] > 0.01).sum()) for n in names if (W[n] > 0.01).any()})


def rigid(o, bone):
    write(o, {bone: np.ones(len(o.data.vertices))})


def jawmask(o):
    kb = o.data.shape_keys.key_blocks
    d = np.linalg.norm(np.array([v.co for v in kb["jawOpen"].data]) - np.array([v.co for v in kb["Basis"].data]), axis=1)
    return smooth(0.0, 0.6 * d.max(), d)


def chain(z):
    """neck weights by height: spine01 -> neck01 -> neck02 -> neck03 -> head."""
    names = ["spine01", "neck01", "neck02", "neck03", "head"]
    zc = [B["spine01"][2] + 0.06] + [(B[n][2] + B[m][2]) / 2 for n, m in (("neck01", "neck02"), ("neck02", "neck03"), ("neck03", "head"))] + [B["head"][2] + 0.03]
    W = {n: np.zeros(len(z)) for n in names}
    zi = np.clip(z, zc[0], zc[-1])
    for k in range(4):
        m = (zi >= zc[k]) & (zi <= zc[k + 1]); f = (zi[m] - zc[k]) / (zc[k + 1] - zc[k])
        W[names[k]][m] += 1 - f; W[names[k + 1]][m] += f
    return W


def head_weights(o):
    p = wco(o); n = len(p); j = jawmask(o)
    A = np.array([-0.06, 1.30]); nrm = np.array([-1, 1]) / math.sqrt(2)          # tilted plane under the jaw and over the nape
    t = smooth(-0.015, 0.02, (p[:, 1:] - A) @ nrm)
    W = {k: v * (1 - t) for k, v in chain(p[:, 2]).items()}
    W["head"] = W.get("head", 0) + t * (1 - j); W["jaw"] = t * j
    # the shoulder flare under the tee follows the body like the tee does
    f = 1 - smooth(1.26, 1.30, p[:, 2]); low = np.nonzero(f > 0)[0]
    W = {k: v * (1 - f) for k, v in W.items()}
    I, Bc = binder.locate(p[low])
    for r, v in enumerate(low):
        for i, b in zip(I[r], Bc[r]):
            for bone, w in binder.w[i].items():
                W.setdefault(bone, np.zeros(n))[v] += f[v] * w * b
    write(o, W)


head_weights(OBJ["cand_head"])
pm = jawmask(OBJ["cand_mouth"]); write(OBJ["cand_mouth"], {"head": 1 - pm, "jaw": pm})
for n in ("cand_teeth_low", "cand_tongue"):
    rigid(OBJ[n], "jaw")
for n in ("cand_teeth_up", "concept_brows", "concept_band", "concept_tie"):
    rigid(OBJ[n], "head")
write(OBJ["concept_eyes"], {"eye.L": (eyes[:, 0] > 0).astype(float), "eye.R": (eyes[:, 0] <= 0).astype(float)})
# hair: scalp on head, tail along the three ponytail bones
P = np.array(PT); n = len(hair); W = {k: np.zeros(n) for k in ("head", "ponytail01", "ponytail02", "ponytail03")}
best = np.full(n, 9.0); sp = np.zeros(n)
for k in range(3):
    a, b = P[k], P[k + 1]; ab = b - a; u = np.clip(((hair - a) @ ab) / (ab @ ab), 0, 1)
    d = np.linalg.norm(hair - (a + u[:, None] * ab), axis=1); m = d < best; best[m] = d[m]; sp[m] = k + u[m]
tail = (hair[:, 1] > 0.115) & (hair[:, 2] < P[0][2] + 0.01) & (best < 0.075)
seg = np.clip(sp, 0, 2.999); k0 = np.floor(seg).astype(int); fr = seg - k0
for v in np.nonzero(tail)[0]:
    s0 = sp[v]
    if s0 < 0.35:                                  # root blends from the scalp into the tail
        f = s0 / 0.35; W["head"][v] += 1 - f; W["ponytail01"][v] += f
    else:
        k = k0[v]; f = fr[v]; nm = lambda i: "ponytail0%d" % (i + 1)
        if f > 0.7 and k < 2:
            g = (f - 0.7) / 0.6; W[nm(k)][v] += 1 - g; W[nm(k + 1)][v] += g
        elif f < 0.3 and k > 0:
            g = (0.3 - f) / 0.6; W[nm(k)][v] += 1 - g; W[nm(k - 1)][v] += g
        else:
            W[nm(k)][v] += 1
W["head"][~tail] = 1
write(OBJ["host_hair_low"], W)

# ---- 5. body: drop the old head, helpers and old face keys
if body.data.shape_keys:
    for k in list(body.data.shape_keys.key_blocks)[::-1]:
        body.shape_key_remove(k)
bc = wco(body); vis = body.vertex_groups["body"].index
inbody = np.array([any(g.group == vis and g.weight > 0 for g in v.groups) for v in body.data.vertices])
drop = (~inbody) | (bc[:, 2] > 1.29) | ((bc[:, 2] > 1.21) & (np.abs(bc[:, 0]) < 0.125))

bm = bmesh.new(); bm.from_mesh(body.data); bm.verts.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.verts[i] for i in np.nonzero(drop)[0]], context="VERTS"); bm.to_mesh(body.data); bm.free()
body.hide_render = False; body.hide_set(False)
bpy.data.objects["host_shoes"].hide_render = False; bpy.data.objects["host_shoes"].hide_set(False)
print("REPORT body verts kept", len(body.data.vertices), "dropped", int(drop.sum()))

# ---- 5b. neckline-only collar fix (approved): smooth the tee's neck edge and keep the tee just outside the neck skin
from mathutils.bvhtree import BVHTree
tee = bpy.data.objects["host_tee"]; bm = bmesh.new(); bm.from_mesh(tee.data); bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table()
bnd = [e for e in bm.edges if e.is_boundary]; loops = []; seen = set()
for e in bnd:                                     # boundary edges -> loops
    if e.index in seen:
        continue
    comp, stack = [], [e]
    while stack:
        x = stack.pop()
        if x.index in seen:
            continue
        seen.add(x.index); comp.append(x)
        for v in x.verts:
            stack += [y for y in v.link_edges if y.is_boundary and y.index not in seen]
    loops.append(comp)
neck = max(loops, key=lambda c: np.mean([v.co.z for e in c for v in e.verts]))
ring0 = {v for e in neck for v in e.verts}
dist = {v: 0 for v in ring0}; front = set(ring0)
for r in range(1, 5):                            # rings inward from the edge
    front = {w for v in front for e in v.link_edges for w in (e.other_vert(v),) if w not in dist}
    for w in front:
        dist[w] = r
nb = {v: [e.other_vert(v) for e in v.link_edges if e.is_boundary] for v in ring0}
for it in range(40):                              # 1-D smoothing along the edge loop removes the sawtooth
    new = {v: v.co * 0.5 + sum((w.co for w in nb[v]), Vector()) * (0.5 / max(len(nb[v]), 1)) for v in ring0 if len(nb[v]) == 2}
    for v, c in new.items():
        v.co = c
for it in range(6):                               # relax the next rings so no triangle folds
    new = {}
    for v, r in dist.items():
        if r == 0:
            continue
        nbr = [e.other_vert(v) for e in v.link_edges]; a = 0.5 * (1 - r / 5)
        new[v] = v.co * (1 - a) + sum((w.co for w in nbr), Vector()) * (a / len(nbr))
    for v, c in new.items():
        v.co = c
hd = OBJ["cand_head"].data; hp = wco(OBJ["cand_head"])
bvh = BVHTree.FromPolygons([tuple(p) for p in hp], [tuple(p.vertices) for p in hd.polygons])
GAP = 0.0025; pushed = 0
for v in bm.verts:                                # the tee never sinks into the neck skin
    if v.co.z < 1.18:
        continue
    loc, nrm, _, d = bvh.find_nearest(v.co)
    if loc is None or d > 0.03:
        continue
    want = GAP + (0.0015 if v in dist and dist[v] == 0 else 0)
    if (v.co - loc).dot(nrm) < want:
        v.co = loc + nrm * want; pushed += 1
bm.to_mesh(tee.data); bm.free(); tee.data.update()
print("REPORT collar loop verts", len(ring0), "rings", len(dist), "pushed out", pushed)
for n in ("concept_hair", "concept_head", "concept_lash", "concept_mouth", "concept_teeth", "wrap_head"):
    o = bpy.data.objects.get(n)
    if o:
        bpy.data.objects.remove(o)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "stage3", f"stage3_{TAG}.blend"), copy=True)

# ---- 6. skinned GLB
EXPORT = HEADPARTS + ["host_body", "host_shoes", "host_tee", "host_overalls", "host_pocket", "host_strap_L", "host_strap_R", "host_buttons", "host_stitch"]
for o in bpy.context.selected_objects:
    o.select_set(False)
rig.select_set(True)
for nme in EXPORT:
    bpy.data.objects[nme].select_set(True)
glb = os.path.join(OUT, "host.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=False, export_skins=True, export_all_influences=False,
                          export_morph=True, export_morph_normal=True, export_try_sparse_sk=True, export_animations=False, export_image_format="AUTO", export_yup=True)
tris = sum(sum(len(p.vertices) - 2 for p in bpy.data.objects[n].data.polygons) for n in EXPORT)
print("REPORT glb KB", os.path.getsize(glb) // 1024, "tris", tris)

# ---- 7. Gate 3 poses in Blender (same list is replayed in Three.js by stage3_check.mjs)
s.render.engine = "BLENDER_EEVEE"; s.render.film_transparent = True
s.view_settings.view_transform = "Standard"; s.view_settings.look = "None"; s.view_settings.exposure = 0
for kx, vx in (("use_raytracing", True), ("taa_render_samples", 24)):
    if hasattr(s.eevee, kx):
        setattr(s.eevee, kx, vx)
from stage3_common import lin                    # same studio as the Stage 2 portraits
w = bpy.data.worlds.get("portrait") or bpy.data.worlds.new("portrait"); s.world = w; w.use_nodes = True
b0 = w.node_tree.nodes["Background"]; b0.inputs[0].default_value = lin("#e9e4de"); b0.inputs[1].default_value = 0.44
TG0 = Vector((0, -0.05, 1.475))
for nme, en, off, size, colr in (("p_key", 24, (-0.85, -1.15, 0.65), 1.4, (1, .95, .89)), ("p_fill", 8, (1.1, -1.1, 0.05), 1.8, (.94, .96, 1)),
                                 ("p_hair", 16, (0.65, 0.95, 0.75), 0.8, (1, .97, .93)), ("p_bounce", 3, (0, -0.8, -0.7), 1.2, (1, .86, .76))):
    if nme in bpy.data.objects:
        continue
    Lg = bpy.data.lights.new(nme, "AREA"); Lg.energy = en; Lg.size = size; Lg.color = colr
    o = bpy.data.objects.new(nme, Lg); s.collection.objects.link(o); o.location = TG0 + Vector(off)
    o.rotation_euler = (TG0 - o.location).to_track_quat("-Z", "Y").to_euler()
import json
SHOTS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stage3_shots.json")))
AXES = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}
order = [b.name for b in rig.data.bones]


def pose(rot):
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    for name in sorted(rot, key=order.index):
        for ax, deg in rot[name]:
            pb = rig.pose.bones[name]; h = pb.head.copy()
            pb.matrix = Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, Vector(AXES[ax])) @ Matrix.Translation(-h) @ pb.matrix
            bpy.context.view_layer.update()


for sh in SHOTS:
    pose(sh.get("pose", {}))
    shot(os.path.join(OUT, sh["name"] + ".png"), target=sh["target"], dist=sh["dist"], azimuth=sh["az"], lens=85, res=(600, 712))
print("STAGE3 DONE")
