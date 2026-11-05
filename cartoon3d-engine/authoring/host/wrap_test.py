"""Stage 1 test: wrap the MPFB head (loops, UVs, shape keys on matching vertices) onto approved h10.
Run: blender -b build/concepts/concept_H.blend --python host/wrap_test.py -- t1 [--bake]
Opens the concept read-only and saves only to build/wrap/. Nothing else is written."""
import math
import os
import sys

import bmesh
import bpy
import mathutils
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concept_params import CONCEPTS
from stage3_common import BUILD, coords, key_coords, lin, material, shot

ARGS = sys.argv[sys.argv.index("--") + 1:]; TAG = ARGS[0]
OUT = os.path.join(BUILD, "wrap", TAG); os.makedirs(OUT, exist_ok=True)
C = CONCEPTS["H"]; M = C["mouth"]; L = C["lid"]
EX, EY, EZ, ER = C["eye_x"], C["eye_y"], C["eye_z"], C["eye_r"]
RIM = ER + 0.0012 + 2 * L["thick"]; DROP = C["drop"]


def mouth_z(x):
    return M["z"] + M["curve"] * (np.asarray(x) / M["w"]) ** 2


def lip_y(x):
    return M["y"] + M["yc"] * np.asarray(x) ** 2


# ---- source
with bpy.data.libraries.load(os.path.join(BUILD, "host_stage3b.blend"), link=False) as (src_, dst):
    dst.objects = ["host_body", "host_rig"]
body, srig = dst.objects
mask = np.load(os.path.join(BUILD, "head_mask.npy")); LIN = np.load(os.path.join(BUILD, "eye_lining.npy"))
lip = np.zeros(len(body.data.vertices), bool); lip[np.load(os.path.join(BUILD, "lip_verts.npy"))] = True
P = coords(body.data)
vi = body.vertex_groups["body"].index
vis = np.array([any(g.group == vi for g in v.groups) for v in body.data.vertices])
sel = vis & (P[:, 2] > 1.215) & (np.abs(P[:, 0]) < 0.12)
idx = np.where(sel)[0]; inv = -np.ones(len(P), int); inv[idx] = np.arange(len(idx))
bm = bmesh.new(); bm.from_mesh(body.data)
for layer in list(bm.verts.layers.shape):
    bm.verts.layers.shape.remove(layer)
bm.verts.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not sel[v.index]], context="VERTS")
bm.verts.index_update(); bm.normal_update()
S = np.array([v.co for v in bm.verts])                # order matches idx: delete keeps relative order
assert np.allclose(S, P[idx], atol=1e-5)
nS = np.array([v.normal for v in bm.verts])
faces = [[v.index for v in f.verts] for f in bm.faces]
bvhS = BVHTree.FromBMesh(bm)
edges = np.array([[e.verts[0].index, e.verts[1].index] for e in bm.edges])
border = np.array([v.is_boundary for v in bm.verts])
LINs, LIPs = LIN[idx], lip[idx]

# outer skin vs folded interior: a vertex that looks outward and hits its own mesh is inside a pocket
inner = np.zeros(len(S), bool)
for i in range(len(S)):
    h = bvhS.ray_cast(Vector(S[i] + nS[i] * 0.0006), Vector(nS[i]), 0.08)
    inner[i] = h[0] is not None
inner |= LINs
print("REPORT verts", len(S), "inner", inner.sum(), "lining", LINs.sum())

# ---- target
tgt = bpy.data.objects["concept_head"]; T = coords(tgt.data)
tgt_b = bmesh.new(); tgt_b.from_mesh(tgt.data); bvhT = BVHTree.FromBMesh(tgt_b)
# outer face only: h10 also has inner surfaces (eye sockets, mouth cavity). Skin must never snap to those.
fc = np.array([f.calc_center_median() for f in tgt_b.faces])
keep = np.ones(len(fc), bool)
for s_ in (1, -1):
    keep &= np.linalg.norm(fc - np.array((s_ * EX, EY, EZ)), axis=1) > RIM - 0.0006
inside = (np.abs(fc[:, 0]) < M["w"] * 1.12) & (fc[:, 1] > lip_y(fc[:, 0]) + 0.0085) & (fc[:, 1] < M["y"] + 0.1) & (np.abs(fc[:, 2] - M["z"]) < 0.036)
keep &= ~inside
tgt_b.faces.ensure_lookup_table()
tv = np.array([v.co for v in tgt_b.verts])
qf = np.array([[v.index for v in f.verts] for f in tgt_b.faces])[keep]
bvhO = BVHTree.FromPolygons([tuple(p) for p in tv], [tuple(int(i) for i in q) for q in qf])
print("REPORT outer faces", keep.sum(), "of", len(keep))


def cast(bvh, centre, d):
    d = np.array(d, float); d /= np.linalg.norm(d)
    h = bvh.ray_cast(Vector(np.array(centre) + d * 0.5), Vector(-d))
    return np.array(h[0]) if h[0] else None


def dirv(az, el):
    a, e = math.radians(az), math.radians(el)
    return (math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e))


pairs = []
hard = {}                                             # vertex -> exact target (kept through relaxing)

# lid edges
eyeL = np.array(srig.data.bones["eye.L"].head_local)
ed_m = edges[LINs[edges[:, 0]] != LINs[edges[:, 1]]]
margin = np.unique(np.where(LINs[ed_m], -1, ed_m)); margin = margin[margin >= 0]
for s in (1, -1):
    m = margin[S[margin, 0] * s > 0]
    q = S[m]; xs = q[:, 0] * s
    a_i, a_o = m[np.argmin(xs)], m[np.argmax(xs)]
    cx = (S[a_i, 0] * s + S[a_o, 0] * s) / 2; ax = (S[a_o, 0] * s - S[a_i, 0] * s) / 2
    line = S[a_i, 2] + (xs - S[a_i, 0] * s) / (2 * ax) * (S[a_o, 2] - S[a_i, 2])
    up = q[:, 2] >= line
    b_up, b_dn = (q[up, 2] - line[up]).max(), (line[~up] - q[~up, 2]).max()
    c = np.array((s * EX, EY, EZ))
    for vtx, x_, up_ in zip(m, (xs - cx) / ax, up):
        x_ = float(np.clip(x_, -1, 1))
        u = L["u0"] + x_ * L["a"] * 0.985
        v = (L["up"] if up_ else -L["down"]) * math.sqrt(max(1 - abs(x_) ** L["pow"], 0))
        dz = v + L["tilt"] * u + L["v0"]
        dy = -math.sqrt(max(1 - u * u - dz * dz, 0.01))
        d = np.array((s * u, dy, dz)); d /= np.linalg.norm(d)
        pt = c + d * (RIM + 0.0002)
        pairs.append((S[vtx], pt)); hard[int(vtx)] = pt
    ln = np.where(LINs & (S[:, 0] * s > 0))[0]        # linings go behind the eyeball
    for vtx in ln:
        q_ = S[vtx]; x_ = float(np.clip((q_[0] * s - cx) / ax, -1, 1))
        l_ = S[a_i, 2] + (q_[0] * s - S[a_i, 0] * s) / (2 * ax) * (S[a_o, 2] - S[a_i, 2])
        z_ = float(np.clip((q_[2] - l_) / (b_up if q_[2] > l_ else b_dn), -1, 1))
        u = L["u0"] + x_ * L["a"] * 0.85; v = (L["up"] if z_ > 0 else L["down"]) * z_ * 0.85
        dz = v + L["tilt"] * u + L["v0"]; dy = -math.sqrt(max(1 - u * u - dz * dz, 0.01))
        d = np.array((s * u, dy, dz)); d /= np.linalg.norm(d)
        hard[int(vtx)] = c + d * (ER - 0.0045)

# lips
ext_lip = np.where(LIPs & ~inner)[0]
fit = np.polyfit(S[ext_lip, 0], S[ext_lip, 2], 2)
wS = np.abs(S[ext_lip, 0]).max()
cont = np.unique(edges[LIPs[edges[:, 0]] != LIPs[edges[:, 1]]].ravel()); cont = cont[LIPs[cont] & ~inner[cont]]
seam = np.unique(edges[(inner[edges[:, 0]] != inner[edges[:, 1]])].ravel()); seam = seam[LIPs[seam] & ~inner[seam]]
print("REPORT lips contour", len(cont), "seam", len(seam), "half width", wS)
for vtx in seam:
    t = float(np.clip(S[vtx, 0] / wS, -1, 1)); x = t * M["w"] * 0.97
    side = 1 if S[vtx, 2] >= np.polyval(fit, S[vtx, 0]) else -1
    pt = np.array((x, float(lip_y(x)) + 0.0035, float(mouth_z(x)) + side * 0.0009))
    pairs.append((S[vtx], pt)); hard[int(vtx)] = pt
def on_front(x, z, y0):
    hh = bvhO.ray_cast(Vector((x, -0.6, z)), Vector((0, 1, 0)))
    return np.array(hh[0]) if hh[0] else np.array((x, y0, z))


sline = np.polyval(fit, S[:, 0])
top = {}; 
for vtx in cont:
    side = 1 if S[vtx, 2] >= sline[vtx] else -1
    k = (side, round(float(S[vtx, 0]) * 200))
    top[k] = max(top.get(k, 0), abs(S[vtx, 2] - sline[vtx]))
for vtx in np.where(LIPs & ~inner)[0]:
    if int(vtx) in hard:
        continue
    t = float(np.clip(S[vtx, 0] / wS, -1, 1)); x = t * M["w"]
    env = math.sqrt(max(1 - t * t, 0.0004)); side = 1 if S[vtx, 2] >= sline[vtx] else -1
    r = (M["up"] * env ** 0.75 if side > 0 else M["low"] * env ** 0.62)
    span = max(top.get((side, round(float(S[vtx, 0]) * 200)), 0.0), 0.003)
    f_ = float(np.clip(abs(S[vtx, 2] - sline[vtx]) / span, 0.08, 1))
    z = float(mouth_z(x)) + side * (0.0012 + f_ * 1.7 * r)
    pt = on_front(x, z, float(lip_y(x)))
    pairs.append((S[vtx], pt)); hard[int(vtx)] = pt

# nose, chin, outline, neck
fx = np.abs(S[:, 0]) < 0.004
nz = np.where(fx & ~inner & (S[:, 2] > 1.40) & (S[:, 2] < 1.5))[0]
tip_s = S[nz[np.argmin(S[nz, 1])]]
tip_t = np.array(C["nose"]["tip"]) - np.array((0, C["nose"]["tip_r"][1], 0))
pairs.append((tip_s, tip_t))
for dz_s, dz_t in ((-0.018, -0.0135), (0.03, 0.03), (0.062, 0.05)):
    a = cast(bvhS, (0, 0, tip_s[2] + dz_s), (0, -1, 0)); b = cast(bvhT, (0, 0, tip_t[2] + dz_t), (0, -1, 0))
    if a is not None and b is not None:
        pairs.append((a, b))
mzS = float(np.polyval(fit, 0))
for dz in (-0.03, -0.05):
    a = cast(bvhS, (0, 0, mzS + dz), (0, -1, 0)); b = cast(bvhT, (0, 0, M["z"] + dz * 0.9), (0, -1, 0))
    pairs.append((a, b))
cS, cT = np.array((0, -0.03, 1.50)), np.array((0, -0.02, 1.525))
for az, els in ((0, (48, 62, 76)), (32, (46, 62)), (62, (-18, 30, 55)), (95, (42, 66)), (130, (-16, 12, 42, 68)), (155, (-20, 10, 40, 70)), (180, (-22, 12, 42, 72))):
    for el in els:
        for sg in ((1, -1) if az not in (0, 180) else (1,)):
            a, b = cast(bvhS, cS, dirv(az * sg, el)), cast(bvhT, cT, dirv(az * sg, el))
            if a is not None and b is not None:
                pairs.append((a, b))
for az in range(0, 360, 30):                          # neck ring: keeps the join to the body round
    for zs, zt in ((1.29, 1.29 + DROP), (1.235, 1.235 + DROP)):
        d = (math.sin(math.radians(az)), -math.cos(math.radians(az)), 0)
        a, b = cast(bvhS, (0, -0.02, zs), d), cast(bvhT, (0, -0.02, zt), d)
        if a is not None and b is not None:
            pairs.append((a, b))
A = np.array([p[0] for p in pairs]); B = np.array([p[1] for p in pairs])
u_, ui = np.unique(np.round(A, 4), axis=0, return_index=True); A, B = A[ui], B[ui]
print("REPORT landmarks", len(A))


# ---- thin-plate warp
n = len(A); K = np.linalg.norm(A[:, None] - A[None], axis=2)
Pm = np.c_[np.ones(n), A]
Lm = np.block([[K + 1e-5 * np.eye(n), Pm], [Pm.T, np.zeros((4, 4))]])
W = np.linalg.solve(Lm, np.r_[B - A, np.zeros((4, 3))])


def tps(X):
    return X + np.linalg.norm(X[:, None] - A[None], axis=2) @ W[:n] + np.c_[np.ones(len(X)), X] @ W[n:]


Q = tps(S)
for k, v in hard.items():
    Q[k] = v

# ---- project outer skin, relax, keep the fixed loops
fixed = np.zeros(len(S), bool); fixed[list(hard)] = True
free = ~inner & ~fixed & ~border
ears = (np.abs(S[:, 0]) > 0.098) & (S[:, 2] < 1.53) & (S[:, 2] > 1.40) & (S[:, 1] > -0.05)
free &= ~ears
for it in range(24):
    acc = np.zeros_like(Q); cnt = np.zeros(len(Q))
    np.add.at(acc, edges[:, 0], Q[edges[:, 1]]); np.add.at(acc, edges[:, 1], Q[edges[:, 0]]); np.add.at(cnt, edges.ravel(), 1)
    lap = acc / np.maximum(cnt, 1)[:, None]
    Q[free] += 0.5 * (lap[free] - Q[free])
    for i in np.where(free)[0]:
        if abs(Q[i, 0]) < M["w"] * 1.6 and abs(Q[i, 2] - M["z"]) < 0.03 and Q[i, 1] < M["y"] + 0.05:
            hh = bvhO.ray_cast(Vector((Q[i, 0], -0.6, Q[i, 2])), Vector((0, 1, 0)))
            if hh[0] is not None:
                Q[i] = hh[0]; continue
        loc, _, _, _ = bvhO.find_nearest(Vector(Q[i]))
        Q[i] = loc
# inner pocket verts follow softly
pocket = inner & ~fixed
for it in range(10):
    acc = np.zeros_like(Q); cnt = np.zeros(len(Q))
    np.add.at(acc, edges[:, 0], Q[edges[:, 1]]); np.add.at(acc, edges[:, 1], Q[edges[:, 0]]); np.add.at(cnt, edges.ravel(), 1)
    Q[pocket] += 0.5 * (acc[pocket] / np.maximum(cnt[pocket], 1)[:, None] - Q[pocket])
d = np.array([ (Vector(q) - bvhO.find_nearest(Vector(q))[0]).length for q in Q[~inner & ~ears & ~border]])
print("REPORT surface error mm: mean %.3f  p95 %.3f  max %.3f" % (d.mean() * 1000, np.quantile(d, .95) * 1000, d.max() * 1000))
for v, q in zip(bm.verts, Q):
    v.co = q
bm.normal_update()
me = bpy.data.meshes.new("wrap_head"); bm.to_mesh(me); bm.free()
me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
for g in ("host_body", "host_rig"):
    pass
wrap = bpy.data.objects.new("wrap_head", me); bpy.context.scene.collection.objects.link(wrap)
wrap.location.z = -DROP
wrap.data.materials.clear()
np.savez(os.path.join(OUT, "wrap.npz"), S=S, Q=Q, inner=inner, idx=idx)

# colour: nearest h10 vertex colour for this test; a proper bake comes with --bake
hc = np.zeros(len(T) * 4, np.float32); tgt.data.color_attributes["skin"].data.foreach_get("color", hc); hc = hc.reshape(-1, 4)
kd = mathutils.kdtree.KDTree(len(T))
for i, p_ in enumerate(T):
    kd.insert(p_, i)
kd.balance()
col = np.array([hc[kd.find(q)[1]] for q in Q])
ca = me.color_attributes.new("skin", "FLOAT_COLOR", "POINT"); ca.data.foreach_set("color", col.ravel())
me.materials.append(tgt.data.materials[0])

# keys: same vertices, so a key is carried through the warp
kbs = body.data.shape_keys.key_blocks
base = key_coords(kbs[0])[idx]
wrap.shape_key_add(name="Basis", from_mix=False)
for name in ("eyeBlinkLeft", "eyeBlinkRight", "jawOpen", "viseme_aa", "viseme_O", "mouthSmileLeft", "mouthSmileRight"):
    dlt = tps(base + (key_coords(kbs[name])[idx] - base)) - tps(base)
    KP = Q + dlt
    for s_ in (1, -1):
        c_ = np.array((s_ * EX, EY, EZ)); v_ = KP - c_; r_ = np.linalg.norm(v_, axis=1)
        moved = np.linalg.norm(dlt, axis=1) > 1e-5
        z_ = (r_ < RIM + 0.012) & (v_[:, 1] < 0) & ~inner & moved
        KP[z_] = c_ + v_[z_] / r_[z_, None] * np.maximum(r_[z_], RIM + 0.0003)[:, None]
    k = wrap.shape_key_add(name=name, from_mix=False); k.data.foreach_set("co", KP.astype(np.float32).ravel()); k.value = 0

# the approved h10 smile, evaluated on this light mesh (same field as the concept)
def smile_field(V):
    x, y, z = V[:, 0].copy(), V[:, 1].copy(), V[:, 2].copy(); Vn = V.copy(); w_ = M["w"]; Sm = C["smile"]
    t = np.abs(x) / w_; zc = mouth_z(x)
    front = np.clip((M["y"] + 0.085 - y) / 0.06, 0, 1) ** 2
    wm = np.exp(-((x / (w_ * 1.4)) ** 2 + ((z - M["z"]) / 0.036) ** 2)) * front
    Vn[:, 2] += Sm["lift"] * np.clip(t, 0, 1.25) ** 2 * wm
    Vn[:, 0] += Sm["wide"] * x * wm
    Vn[:, 1] += Sm["back"] * np.clip(t, 0, 1.2) ** 2 * wm
    side = np.tanh((z - zc) / 0.0012)
    env = np.sqrt(np.clip(1 - np.clip(t, 0, 1) ** 2, 0, 1))
    near = np.exp(-((z - zc) / 0.03) ** 2) * front * (t < 1.15)
    Vn[:, 2] += near * env * np.where(side > 0, Sm["open_up"], -Sm["open_down"]) * np.abs(side)
    Vn[:, 2] -= Sm["jaw"] * np.exp(-((x / 0.07) ** 2)) * np.clip((M["z"] - z) / 0.05, 0, 1) * front
    for s_ in (1, -1):
        ck = C["cheek_c"]
        gk = np.exp(-(((x - s_ * ck[0]) / 0.042) ** 2 + ((z - ck[2]) / 0.036) ** 2)) * np.clip((-0.01 - y) / 0.05, 0, 1)
        Vn[:, 2] += Sm["cheek"] * gk; Vn[:, 1] -= Sm["cheek"] * 0.55 * gk
        lz = np.exp(-(((x - s_ * EX) / 0.03) ** 2 + ((z - (EZ - ER * 0.75)) / 0.012) ** 2)) * np.clip((EY + 0.03 - y) / 0.04, 0, 1)
        Vn[:, 2] += Sm["lid"] * lz
    return Vn


k = wrap.shape_key_add(name="h10smile", from_mix=False); k.data.foreach_set("co", smile_field(Q).astype(np.float32).ravel()); k.value = 0

# bake the approved h10 colours onto the wrapped head
bpy.context.view_layer.objects.active = wrap
for o in bpy.context.selected_objects:
    o.select_set(False)
wrap.select_set(True)
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(70), island_margin=0.004)
bpy.ops.object.mode_set(mode="OBJECT")
img = bpy.data.images.new("wrap_skin", 2048, 2048, float_buffer=False)
wm = material("wrap_skin_m", rough=C["skin_rough"])
nt = wm.node_tree; bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = img; nt.nodes.active = tn
nt.links.new(tn.outputs[0], bs.inputs["Base Color"])
bs.inputs["Subsurface Weight"].default_value = 0.35; bs.inputs["Subsurface Radius"].default_value = (0.9, 0.4, 0.25); bs.inputs["Subsurface Scale"].default_value = 0.012
wrap.data.materials.clear(); wrap.data.materials.append(wm)
sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.samples = 1; sc.cycles.device = "CPU"
tb = tgt.data.materials[0]
tgt.hide_render = False; tgt.select_set(True); wrap.select_set(True); bpy.context.view_layer.objects.active = wrap
sc.render.bake.use_selected_to_active = True; sc.render.bake.cage_extrusion = 0.014; sc.render.bake.max_ray_distance = 0.04; sc.render.bake.margin = 16
sc.render.bake.use_pass_direct = False; sc.render.bake.use_pass_indirect = False; sc.render.bake.use_pass_color = True
bpy.ops.object.bake(type="DIFFUSE")
img.filepath_raw = os.path.join(OUT, "skin_baked.png"); img.file_format = "PNG"; img.save()
print("REPORT baked")
tgt.hide_render = True
for o in ("host_shoes", "host_body", "concept_lash"):
    if o in bpy.data.objects:
        bpy.data.objects[o].hide_render = True
bpy.data.objects.remove(body); bpy.data.objects.remove(srig)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "wrap", f"wrap_{TAG}.blend"), copy=True)

s = bpy.context.scene
s.render.engine = "BLENDER_EEVEE"; s.render.film_transparent = True
s.view_settings.view_transform = "Standard"; s.view_settings.look = "None"; s.view_settings.exposure = 0
for kx, vx in (("use_raytracing", True), ("taa_render_samples", 48)):
    if hasattr(s.eevee, kx):
        setattr(s.eevee, kx, vx)
w = bpy.data.worlds.get("portrait") or bpy.data.worlds.new("portrait"); s.world = w; w.use_nodes = True
b0 = w.node_tree.nodes["Background"]; b0.inputs[0].default_value = lin("#e9e4de"); b0.inputs[1].default_value = 0.44
TG = Vector((0, -0.05, 1.475))
for nme, en, off, size, colr in (("p_key", 24, (-0.85, -1.15, 0.65), 1.4, (1, .95, .89)), ("p_fill", 8, (1.1, -1.1, 0.05), 1.8, (.94, .96, 1)),
                                 ("p_hair", 16, (0.65, 0.95, 0.75), 0.8, (1, .97, .93)), ("p_bounce", 3, (0, -0.8, -0.7), 1.2, (1, .86, .76))):
    Lg = bpy.data.lights.new(nme, "AREA"); Lg.energy = en; Lg.size = size; Lg.color = colr
    o = bpy.data.objects.new(nme, Lg); s.collection.objects.link(o); o.location = TG + Vector(off)
    o.rotation_euler = (TG - o.location).to_track_quat("-Z", "Y").to_euler()
SH = dict(target=tuple(TG), dist=1.58, lens=85, res=(800, 950))
kb = wrap.data.shape_keys.key_blocks


tk = bpy.data.objects["concept_teeth"].data.shape_keys.key_blocks["smile"]


def keys(**v):
    for k in kb[1:]:
        k.value = v.get(k.name, 0)
    tk.value = v.get("h10smile", 0)


for name, az, kv in (("front_neutral", 0, {}), ("q_neutral", 35, {}), ("side_neutral", 90, {}), ("blink", 0, {"eyeBlinkLeft": 1, "eyeBlinkRight": 1}),
                     ("aa", 0, {"viseme_aa": 1}), ("smile", 0, {"mouthSmileLeft": 1, "mouthSmileRight": 1}), ("h10smile", 0, {"h10smile": 1}), ("h10smile_q", 35, {"h10smile": 1})):
    keys(**kv)
    args = dict(SH)
    if name == "side_neutral":
        args["target"] = (0.1, 0.035, 1.43)
    shot(os.path.join(OUT, name + ".png"), azimuth=az, **args)
keys()
shot(os.path.join(OUT, "eyes.png"), target=(0, EY, EZ - DROP + 0.004), dist=0.68, azimuth=0, lens=85, res=(1200, 640))
print("WRAP DONE")
