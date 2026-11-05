"""Stage 3b: hair, brows, lash line, headband, expressions. Opens host_stage3a.blend, saves host_stage3b.blend.
Run: blender -b build/host_stage3a.blend --python host/stage3_face.py -- [--preview]
Everything on the face follows the 89 body shape keys through the same surface binding, so blinks carry the lashes and
jawOpen carries the lower teeth."""
import math
import os
import sys

import bmesh
import bpy
import mathutils
import numpy as np
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import (BUILD, HEX, TEX, Binder, add_key_deltas, coords, key_coords, loft, material, mesh_object, shot, studio)

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
body = bpy.data.objects["host_body"]; rig = bpy.data.objects["host_rig"]
mask = np.load(os.path.join(BUILD, "head_mask.npy")); LIN = np.load(os.path.join(BUILD, "eye_lining.npy"))
P = coords(body.data)
binder = Binder(body, rig)
bones = rig.data.bones
EYE = np.array(bones["eye.L"].head_local)
hairM = material("hair", os.path.join(TEX, "hair.png"), rough=0.38, normal=os.path.join(TEX, "hair_n.png"), nstrength=0.6)
browM = material("brow_soft", os.path.join(TEX, "brow_soft.png"), rough=0.75, alpha=True)
edgeM = material("hair_edge", os.path.join(TEX, "hair_edge.png"), rough=0.5, alpha=True)
teethM = material("teeth_clean", colour="#fbf7ef", rough=0.24)
mouthM = material("mouth_inside", colour="#5e2024", rough=0.6)
_tb = next(n for n in teethM.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
_tb.inputs["Emission Color"].default_value = (1, 0.97, 0.92, 1); _tb.inputs["Emission Strength"].default_value = 0.32   # teeth stay bright inside the mouth
lashM = material("lash_solid", colour="#160c07", rough=0.5)
mintM = material("mint", colour=HEX["mint"], rough=0.42)

# head frame, measured from the scalp
vis = np.array([any(g.group == body.vertex_groups["body"].index for g in v.groups) for v in body.data.vertices])
sc = P[(mask > 0.9) & vis]
top = sc[:, 2].max(); ZC = EYE[2] + 0.01; up = sc[sc[:, 2] > ZC + 0.03]
HX = up[:, 0].max(); Y0, Y1 = up[:, 1].min(), up[:, 1].max(); YC = (Y0 + Y1) / 2; HY = (Y1 - Y0) / 2
C = np.array([0, YC, ZC])
print("REPORT head frame top", top, "HX", HX, "Y", Y0, Y1, "ZC", ZC, "eye", EYE)


def part_notch(p):
    return 0.05 * np.exp(-((p[..., 0] - PART_X) / 0.042) ** 2)


def head_coords(p):
    az = np.degrees(np.arctan2(np.abs(p[..., 0]) / HX, -(p[..., 1] - YC) / HY))
    return az, (p[..., 2] - ZC) / (top - ZC)


LINE = ([0, 14, 34, 60, 78, 90, 104, 122, 150, 180], [0.72, 0.72, 0.67, 0.50, 0.22, -0.05, 0.02, -0.10, -0.60, -0.82])
PART_X = 0.034


# ---------- hair cap
idx = np.where((mask > 0.5) & vis)[0]
remap = {int(v): n for n, v in enumerate(idx)}
bm = bmesh.new()
BV = [bm.verts.new(tuple(P[v])) for v in idx]
for pl in body.data.polygons:
    vs = list(pl.vertices)
    if all(v in remap for v in vs):
        bm.faces.new([BV[remap[v]] for v in vs])
bm.normal_update()
bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=1, use_grid_fill=True)
fl = bm.verts.layers.float.new("f")


def field(p):
    az, w = head_coords(p)
    return w - np.interp(az, *LINE)


def cut(bm, fn):
    fl = bm.verts.layers.float.get("f") or bm.verts.layers.float.new("f")
    bm.verts.ensure_lookup_table()
    vals = fn(np.array([v.co for v in bm.verts]))
    for v, x in zip(bm.verts, vals):
        v[fl] = float(x) if abs(x) > 1e-7 else 1e-7
    for e in list(bm.edges):
        a, b = e.verts
        if a[fl] * b[fl] < 0:
            t = a[fl] / (a[fl] - b[fl])
            _, nv = bmesh.utils.edge_split(e, a, t)
            nv[fl] = 0.0
    for f in list(bm.faces):
        z = [v for v in f.verts if v[fl] == 0.0]
        if len(z) == 2 and not any(z[1] in (e.other_vert(z[0]),) for e in z[0].link_edges):
            bmesh.ops.connect_verts(bm, verts=z)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v[fl] < 0], context="VERTS")


cut(bm, field)
for _ in range(90):                                 # relax the cut edge into one clean line
    new = {}
    for v in bm.verts:
        if v.is_boundary:
            nb = [e.other_vert(v).co for e in v.link_edges if e.is_boundary]
            if len(nb) == 2:
                new[v] = v.co * 0.4 + (nb[0] + nb[1]) * 0.3
    for v, q in new.items():
        v.co = q
for _ in range(1):
    bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if not v.is_boundary], factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
bm.normal_update()
pts = np.array([v.co for v in bm.verts]); nor = np.array([v.normal for v in bm.verts])
f = np.maximum(field(pts), 0)
az, w = head_coords(pts)
off = 0.0015 + 0.021 * (1 - np.exp(-f / 0.09)) + 0.012 * np.clip(w, 0, 1) ** 2
front = np.clip((-(pts[:, 1] - YC) / HY + 0.1) / 0.6, 0, 1)
part = np.exp(-((pts[:, 0] - PART_X) / 0.0075) ** 2) * front * (w > 0.2)   # side part: a soft valley running back from the forehead
off -= 0.012 * part
new = pts + nor * off[:, None]
for v, q in zip(bm.verts, new):
    v.co = q
bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if not v.is_boundary], factor=0.6, use_axis_x=True, use_axis_y=True, use_axis_z=True)
bm.normal_update()

# strands flow from the part and hairline to the ponytail base
az_a, w_a = 180.0, 0.20
A_dir = mathutils.Vector((0, 1, 0.16)).normalized()
hit = None
cap_bvh = BVHTree.FromBMesh(bm)
hit = cap_bvh.ray_cast(mathutils.Vector(C) + A_dir * 0.5, -A_dir)
ANCHOR = np.array(hit[0]); ANORM = np.array(hit[1])
print("REPORT ponytail anchor", ANCHOR)
ax = (ANCHOR - C) / np.linalg.norm(ANCHOR - C)
e1 = np.cross(ax, [1, 0, 0]); e1 /= np.linalg.norm(e1); e2 = np.cross(ax, e1)
ul = bm.loops.layers.uv.new("UVMap")
for fc in bm.faces:
    us = []
    for l in fc.loops:
        d = np.array(l.vert.co) - C; d /= np.linalg.norm(d)
        us.append(math.atan2(d @ e2, d @ e1) / (2 * math.pi) * 5)
    for i in range(1, len(us)):
        while us[i] - us[0] > 2.5: us[i] -= 5
        while us[i] - us[0] < -2.5: us[i] += 5
    for l, u in zip(fc.loops, us):
        d = np.array(l.vert.co) - C; d /= np.linalg.norm(d)
        l[ul].uv = (u, math.acos(np.clip(d @ ax, -1, 1)) * 0.9)
capbm = bm.copy()
# soft hairline: a thin alpha strip of fine hairs from just inside the cap out over the skin, so no hard edge meets the skin
bm.normal_update()
out_pt, in_pt = {}, {}
for v in bm.verts:
    if not v.is_boundary:
        continue
    inner = [e.other_vert(v).co for e in v.link_edges if not e.is_boundary]
    d = (v.co - sum(inner, mathutils.Vector()) / len(inner)).normalized() if inner else mathutils.Vector((0, 0, -1))
    o_ = v.co + d * 0.010
    loc, n_, _, _ = binder.bvh.find_nearest(o_)
    out_pt[v] = loc + n_ * 0.0007
    in_pt[v] = v.co - d * 0.006 + v.normal * 0.0012
eb = bmesh.new(); ue = eb.loops.layers.uv.new("UVMap"); made = {}
for v in out_pt:
    made[v] = (eb.verts.new(in_pt[v]), eb.verts.new(out_pt[v]))
for e in bm.edges:
    if e.is_boundary and all(x in made for x in e.verts):
        a_, b_ = e.verts
        fq = eb.faces.new((made[a_][0], made[b_][0], made[b_][1], made[a_][1]))
        ua = math.atan2(a_.co.x, -(a_.co.y - YC)) * 2.2; ub = math.atan2(b_.co.x, -(b_.co.y - YC)) * 2.2
        if abs(ua - ub) > 3:
            ub = ua
        for l, uvv in zip(fq.loops, ((ua, 0.04), (ub, 0.04), (ub, 0.96), (ua, 0.96))):
            l[ue].uv = uvv
bmesh.ops.recalc_face_normals(eb, faces=eb.faces)
edge = mesh_object("host_hairline", eb, edgeM, rig)
cap = mesh_object("host_hair", bm, hairM, rig)


# ---------- ponytail: thick sculpted loft with clumped section
def smooth_path(pts, n):
    pts = np.array(pts, float); t = np.linspace(0, 1, len(pts)); s = np.linspace(0, 1, n)
    out = np.stack([np.interp(s, t, pts[:, i]) for i in range(3)], 1)
    for _ in range(12):
        out[1:-1] = out[1:-1] * 0.5 + (out[:-2] + out[2:]) * 0.25
    return out


TAIL = [(0, 0, 0), (0.0, 0.05, 0.012), (0.004, 0.095, -0.03), (0.012, 0.115, -0.11), (0.02, 0.102, -0.2), (0.03, 0.082, -0.29), (0.05, 0.075, -0.37)]
path = smooth_path(ANCHOR + np.array(TAIL) + ANORM * -0.004, 36)
RAD = ([0, 0.05, 0.16, 0.4, 0.7, 0.88, 1], [0.021, 0.023, 0.042, 0.05, 0.04, 0.022, 0.003])
K = 28
rings = []
for i, p in enumerate(path):
    t = path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]; t /= np.linalg.norm(t)
    a = np.cross(t, [1, 0, 0]); a /= np.linalg.norm(a); b = np.cross(t, a)
    s = i / (len(path) - 1); R = np.interp(s, *RAD)
    th = np.arange(K) / K * 2 * np.pi
    lobes = 1 + 0.11 * np.sin(5 * th + s * 5.5) * min(1, s * 6) + 0.05 * np.sin(9 * th - s * 8)
    rings.append(p + (np.cos(th) * R * lobes)[:, None] * a * 1.08 + (np.sin(th) * R * lobes)[:, None] * b)
pb = loft(rings, uv=lambda i, j: (j / K * 3, i / len(path) * 2.2))
bmesh.ops.contextual_create(pb, geom=[v for v in pb.verts if v.is_boundary and (v.co - mathutils.Vector(path[-1])).length < 0.02])
pony = mesh_object("host_ponytail", pb, hairM, rig)

th = np.arange(40) / 40 * 2 * np.pi
tp = path[2]; tt = path[3] - path[1]; tt /= np.linalg.norm(tt)
a = np.cross(tt, [1, 0, 0]); a /= np.linalg.norm(a); b = np.cross(tt, a)
tie_rings = []
for k in range(12):
    ph = k / 12 * 2 * np.pi
    R = 0.0265 + 0.0065 * np.cos(ph)
    bump = 1 + 0.08 * np.sin(th * 9)
    tie_rings.append(tp + (np.cos(th) * R * bump)[:, None] * a * 1.08 + (np.sin(th) * R * bump)[:, None] * b + tt * (0.0085 * math.sin(ph)))
tb = loft(tie_rings + [tie_rings[0]], uv=lambda i, j: (0, 0))
tie = mesh_object("host_hairtie", tb, mintM, rig)

# ponytail bones under the head, so the renderer can let it swing
bpy.context.view_layer.objects.active = rig; rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
marks = [2, 13, 24, 35]; prev = rig.data.edit_bones["head"]
for n in range(3):
    eb = rig.data.edit_bones.new(f"ponytail0{n + 1}")
    eb.head, eb.tail = path[marks[n]], path[marks[n + 1]]; eb.parent = prev; eb.use_connect = n > 0; eb.use_deform = True; prev = eb
bpy.ops.object.mode_set(mode="OBJECT")


def rigid(obj, name):
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    obj.vertex_groups.new(name=name).add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")


rigid(tie, "head")
pv = coords(pony.data)
seg = np.array([path[m] for m in marks]); gs = [pony.vertex_groups.new(name=n) for n in ("head", "ponytail01", "ponytail02", "ponytail03")]
d = np.linalg.norm(pv[:, None] - path[None], axis=2).argmin(1)
for i, s in enumerate(d):
    u = np.interp(s, marks, [0, 1, 2, 3]); lo = min(int(u), 2); fr = u - lo
    gs[lo].add([i], 1 - fr, "REPLACE"); gs[lo + 1].add([i], fr, "REPLACE")


# ---------- brows: clean tapered shapes laid on the skin
body_bvh = binder.bvh


def on_skin(x, z, lift=0.0014):
    h = body_bvh.ray_cast(mathutils.Vector((x, -0.6, z)), mathutils.Vector((0, 1, 0)))
    return np.array(h[0]) - np.array((0, 1, 0)) * lift if h[0] else None


brow_rings = []
bm = bmesh.new(); ub = bm.loops.layers.uv.new("UVMap"); buv = {}
for s in (1, -1):
    N = 22; prevrow = None
    ex, ez = abs(EYE[0]), EYE[2]
    for i in range(N):
        t = i / (N - 1)
        x = ex - 0.034 + 0.068 * t
        zc = ez + 0.041 + 0.009 * math.sin(math.pi * min(1, t * 1.1) ** 0.8) - 0.012 * t ** 2
        th_ = 0.0078 * (min(1, t / 0.2) ** 0.75) * (1 - t ** 2.2) + 0.0012
        row = [bm.verts.new(tuple(on_skin(s * x, zc + d_) )) for d_ in (th_, 0.33 * th_, -0.33 * th_, -th_)]
        for q_, vv in zip(row, (0, 0.33, 0.67, 1)):
            buv[q_] = (t * 1.3 + (0 if s > 0 else 0.37), vv)
        if prevrow:
            for a_ in range(3):
                q = (prevrow[a_], row[a_], row[a_ + 1], prevrow[a_ + 1]) if s > 0 else (prevrow[a_ + 1], row[a_ + 1], row[a_], prevrow[a_])
                bm.faces.new(q)
        prevrow = row
for fc in bm.faces:
    for l in fc.loops:
        l[ub].uv = buv[l.vert]
brows = mesh_object("host_brows2", bm, browM, rig)

# ---------- lash line: follows the real upper lid margin
ed = np.zeros(len(body.data.edges) * 2, int); body.data.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
edge_m = (LIN[ed[:, 0]] != LIN[ed[:, 1]]) & vis[ed].all(1)
margin = np.unique(np.where(LIN[ed[edge_m]], -1, ed[edge_m]))
margin = margin[margin >= 0]
bm = bmesh.new()
for s in (1, -1):
    for lower in (False,):
        m = P[margin]; m = m[(m[:, 0] * s > 0) & ((m[:, 2] < EYE[2] - 0.002) if lower else (m[:, 2] > EYE[2] - 0.001))]
        m = m[np.argsort(np.abs(m[:, 0]))]
        N = 26; xs = np.linspace(np.abs(m[:, 0]).min(), np.abs(m[:, 0]).max(), N)
        curve = np.stack([np.interp(xs, np.abs(m[:, 0]), m[:, i]) for i in range(3)], 1)
        for _ in range(4):
            curve[1:-1] = (curve[:-2] + 2 * curve[1:-1] + curve[2:]) / 4
        prev = None
        for i in range(int(N * 0.4) if lower else 0, N):
            t = i / (N - 1)
            wth = -(0.0007 + 0.0016 * t) if lower else 0.003 + 0.0068 * t ** 1.3
            row = []
            for u in (0.0, 0.55, 1.0):              # root on the lid edge, rising over the lid skin; outer end flicks out
                x = abs(curve[i, 0]) + (0 if lower else 0.0065 * t ** 3 * u)
                z = curve[i, 2] + (0.0005 if lower else -0.0008) + wth * u
                q = on_skin(s * x, z, 0.0016)
                if q is None or q[1] > curve[i, 1] + 0.004:
                    q = np.array([s * x, curve[i, 1] - 0.0016, z])
                row.append(bm.verts.new(tuple(q)))
            if prev:
                flip = (s > 0) != lower
                for a_ in range(2):
                    q = (prev[a_], row[a_], row[a_ + 1], prev[a_ + 1]) if flip else (prev[a_ + 1], row[a_ + 1], row[a_], prev[a_])
                    bm.faces.new(q)
            prev = row
lashes = mesh_object("host_lashes2", bm, lashM, rig)
for n in ("host_brows", "host_lashes"):
    bpy.data.objects.remove(bpy.data.objects[n])
brows.name = "host_brows"; lashes.name = "host_lashes"

# ---------- headband: a real band following the hair, sampled by rays in a tilted plane
hb_bvh = BVHTree.FromBMesh(capbm)
az_f = mathutils.Vector((0, -1, 1.2)).normalized()
hf = hb_bvh.ray_cast(mathutils.Vector(C) + az_f * 0.5, -az_f)[0]
back = mathutils.Vector((0, 1, -0.32)).normalized()
hbk = hb_bvh.ray_cast(mathutils.Vector(C) + back * 0.5, -back)[0]
pf, pk = np.array(hf), np.array(hbk)
print("REPORT band front", pf, "back", pk)
cen = (pf + pk) / 2 + np.array([0, 0, 0.015]); e2 = (pf - pk) / np.linalg.norm(pf - pk); e1 = np.array([1.0, 0, 0]); nrm = np.cross(e1, e2)
N = 120; ring = []; nr = []
for i in range(N):
    a_ = i / N * 2 * math.pi
    d = np.cos(a_) * e1 + np.sin(a_) * e2
    h = hb_bvh.ray_cast(mathutils.Vector(cen + d * 0.5), mathutils.Vector(-d))
    ring.append(np.linalg.norm(np.array(h[0]) - cen) if h[0] else np.nan)
ring = np.array(ring); ok = ~np.isnan(ring); ring = np.interp(np.arange(N), np.arange(N)[ok], ring[ok], period=N)
for _ in range(10):
    ring = 0.5 * ring + 0.25 * (np.roll(ring, 1) + np.roll(ring, -1))
Wd, Th = 0.030, 0.0062
sect = [(-Wd / 2, 0.0), (-Wd / 2, Th * 0.72), (-Wd / 3, Th), (0, Th * 1.08), (Wd / 3, Th), (Wd / 2, Th * 0.72), (Wd / 2, 0.0), (0, -0.001)]
rows = []
for i in range(N + 1):
    a_ = (i % N) / N * 2 * math.pi
    d = np.cos(a_) * e1 + np.sin(a_) * e2
    rows.append(np.array([cen + d * (ring[i % N] + 0.0006 + o) + nrm * w_ for w_, o in sect]))
band = mesh_object("host_headband", loft(rows), mintM, rig)
rigid(band, "head"); rigid(cap, "head"); rigid(edge, "head")

# ---------- expressions: tuned composites, then every key carried to the face parts
kb = body.data.shape_keys.key_blocks
base = key_coords(kb[0])
D = {k.name: key_coords(k) - base for k in kb[1:]}
MIX = {
    "exprSmile": {"mouthSmileLeft": 0.72, "mouthSmileRight": 0.72, "cheekSquintLeft": 0.4, "cheekSquintRight": 0.4, "eyeSquintLeft": 0.15, "eyeSquintRight": 0.15,
                  "mouthUpperUpLeft": 0.95, "mouthUpperUpRight": 0.95, "mouthLowerDownLeft": 0.8, "mouthLowerDownRight": 0.8, "jawOpen": 0.14, "browInnerUp": 0.15},
    "exprLaugh": {"mouthSmileLeft": 0.72, "mouthSmileRight": 0.72, "cheekSquintLeft": 0.45, "cheekSquintRight": 0.45, "eyeSquintLeft": 0.45, "eyeSquintRight": 0.45,
                  "mouthUpperUpLeft": 0.7, "mouthUpperUpRight": 0.7, "mouthLowerDownLeft": 0.9, "mouthLowerDownRight": 0.9, "jawOpen": 0.55, "browInnerUp": 0.3},
    "exprSurprise": {"jawOpen": 0.42, "eyeWideLeft": 0.8, "eyeWideRight": 0.8, "browInnerUp": 1.0, "browOuterUpLeft": 0.9, "browOuterUpRight": 0.9, "mouthFunnel": 0.3},
    "exprCurious": {"browOuterUpLeft": 1.0, "browInnerUp": 0.4, "browDownRight": 0.35, "eyeSquintRight": 0.3, "eyeWideLeft": 0.25, "mouthSmileLeft": 0.3, "mouthRight": 0.35},
    "exprTalk": {"viseme_aa": 0.6, "mouthSmileLeft": 0.28, "mouthSmileRight": 0.28, "browInnerUp": 0.25},
}
lips_v = np.zeros(len(P), bool); lips_v[np.load(os.path.join(BUILD, "lip_verts.npy"))] = True
ed2 = np.zeros(len(body.data.edges) * 2, int); body.data.edges.foreach_get("vertices", ed2); ed2 = ed2.reshape(-1, 2)
pin = lips_v | (np.abs(P - EYE * [1, 1, 1]).sum(1) < 0) | (np.linalg.norm(P - EYE, axis=1) < 0.055) | (np.linalg.norm(P - EYE * [-1, 1, 1], axis=1) < 0.055)
soft = (mask > 0.5) & ~pin


def melt(d, n=30):
    """Cartoon cheeks stay round: remove the realistic folds from a smile, keep lips and lids exact."""
    d = d.copy()
    for _ in range(n):
        acc = np.zeros_like(d); cnt = np.zeros(len(d))
        np.add.at(acc, ed2[:, 0], d[ed2[:, 1]]); np.add.at(acc, ed2[:, 1], d[ed2[:, 0]]); np.add.at(cnt, ed2.ravel(), 1)
        d[soft] = 0.5 * d[soft] + 0.5 * acc[soft] / np.maximum(cnt[soft, None], 1)
    return d


for name in ("mouthSmileLeft", "mouthSmileRight"):   # same rounding on the raw smile keys, so partial smiles stay clean too
    D[name] = melt(D[name]); kb[name].data.foreach_set("co", (base + D[name]).ravel())

for name, mix in MIX.items():
    D[name] = sum(v * D[k] for k, v in mix.items())
    if name in ("exprSmile", "exprLaugh"):
        D[name] = melt(D[name])
    k = body.shape_key_add(name=name, from_mix=False); k.data.foreach_set("co", (base + D[name]).ravel()); k.value = 0.0

for o, skin_it in ((bpy.data.objects["host_brows"], True), (bpy.data.objects["host_lashes"], True), (cap, False), (edge, False)):
    p = coords(o.data); I, B = binder.locate(p)
    if skin_it:
        binder.skin(o, I, B)
    add_key_deltas(o, p, {n: (d[I] * B[..., None]).sum(1) for n, d in D.items()})

# clean cartoon teeth: one upper and one lower arch, plus a dark mouth interior. The asset teeth stay in Stage 2.
old = bpy.data.objects["host_teeth"]; tp_ = coords(old.data)
jgi = {g.index for g in old.vertex_groups if g.name != "head"}
lowm = np.array([sum(g.weight for g in v.groups if g.group in jgi) for v in old.data.vertices]) > 0.5
up_, lo_ = tp_[~lowm], tp_[lowm]
mz = float((np.quantile(up_[:, 2], 0.03) + np.quantile(lo_[:, 2], 0.97)) / 2); yl = float(up_[:, 1].min()); hw = float(np.abs(up_[:, 0]).max()) * 0.95
print("REPORT teeth from asset: line z", mz, "front y", yl, "half", hw, "upper z", up_[:, 2].min(), up_[:, 2].max(), "lower z", lo_[:, 2].min(), lo_[:, 2].max())


def arch(zroot, zedge, yf, half, depth, teeth_n):
    N = 140; rows = []
    for i in range(N + 1):
        t = i / N * 2 - 1
        x = half * math.sin(t * 1.25) / math.sin(1.25)
        y = yf + depth * (1 - math.cos(t * 1.25)) / (1 - math.cos(1.25))
        fr = ((t + 1) / 2 * teeth_n) % 1
        cusp = abs(2 * fr - 1) ** 6                  # 0 mid-tooth, 1 at the gap between teeth
        ze = zedge + (zroot - zedge) * 0.16 * cusp * (1 if zroot > zedge else 1)
        yg = y + 0.0009 * cusp
        rows.append(np.array([[x, yg, zroot], [x, yg, ze], [x, yg + 0.006, ze], [x, yg + 0.006, zroot]]))
    return rows


tb2 = loft(arch(mz + 0.017, mz - 0.0012, yl - 0.0055, hw, 0.036, 10))
lo2 = loft(arch(mz - 0.015, mz + 0.0005, yl - 0.002, hw * 0.86, 0.033, 10))
tmp = bpy.data.meshes.new("t"); lo2.to_mesh(tmp); lo2.free(); nup = len(tb2.verts); tb2.from_mesh(tmp); bpy.data.meshes.remove(tmp)
bmesh.ops.recalc_face_normals(tb2, faces=tb2.faces)
bpy.data.objects.remove(bpy.data.objects["host_teeth"])
newt = mesh_object("host_teeth", tb2, teethM, rig)
newt.vertex_groups.new(name="head").add(list(range(nup)), 1.0, "REPLACE")
newt.vertex_groups.new(name="jaw").add(list(range(nup, len(newt.data.vertices))), 1.0, "REPLACE")
ms = bmesh.new()
rr = bmesh.ops.create_uvsphere(ms, u_segments=24, v_segments=16, radius=1.0)
for v in ms.verts:
    v.co = mathutils.Vector((v.co.x * hw * 1.02, yl + 0.04 + v.co.y * 0.036, mz - 0.004 + v.co.z * 0.022))
bmesh.ops.reverse_faces(ms, faces=ms.faces)
inside = mesh_object("host_mouth", ms, mouthM, rig)
rigid(inside, "head")

pivot = np.array(bones["jaw"].head_local)
ch = np.where((mask > 0.9) & vis & (np.abs(P[:, 0]) < 0.004) & (P[:, 1] < pivot[1] - 0.03))[0]
chin = ch[np.argmin(P[ch, 2])]
r0 = P[chin] - pivot
ang = {}
for n, d in D.items():
    r1 = r0 + d[chin]
    ang[n] = math.atan2(r1[1], -r1[2]) - math.atan2(r0[1], -r0[2])
print("REPORT jawOpen angle deg", math.degrees(ang["jawOpen"]), "laugh", math.degrees(ang["exprLaugh"]), "chin", P[chin])
for name in ("host_teeth", "host_tongue"):
    o = bpy.data.objects[name]; p = coords(o.data)
    jg = {g.index for g in o.vertex_groups if g.name != "head"}
    low = np.array([sum(g.weight for g in v.groups if g.group in jg) for v in o.data.vertices]) > 0.5
    rel = p[low] - pivot; deltas = {}
    for n, a_ in ang.items():
        if abs(a_) < math.radians(0.15):
            continue
        c, s_ = math.cos(a_), math.sin(a_)
        d = np.zeros_like(p)
        d[low, 1] = rel[:, 1] * c - rel[:, 2] * s_ - rel[:, 1]
        d[low, 2] = rel[:, 1] * s_ + rel[:, 2] * c - rel[:, 2]
        deltas[n] = d
    if name == "host_tongue":                        # the source key only moved helper geometry, now removed: drive the tongue itself
        reach = np.clip((pivot[1] - p[:, 1]) / max(pivot[1] - p[:, 1].min(), 1e-6), 0, 1) ** 1.5
        deltas["tongueOut"] = np.stack([0 * reach, -0.05 * reach, -0.012 * reach], 1)
    add_key_deltas(o, p, deltas)
    print("REPORT", name, "lower verts", int(low.sum()), "keys", len(deltas))

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "host_stage3b.blend"))
print("SAVED stage3b")
if "--preview" in ARGS:
    studio()
    bpy.data.objects["host_shoes"].hide_render = True
    hz = float(bones["head"].head_local.z) + 0.07

    def setk(name, v):
        for o in bpy.data.objects:
            if o.type == "MESH" and o.data.shape_keys and name in o.data.shape_keys.key_blocks:
                o.data.shape_keys.key_blocks[name].value = v

    shot(os.path.join(BUILD, "s3b_front.png"), (0, -0.05, hz), 1.6, 0, res=(560, 620))
    shot(os.path.join(BUILD, "s3b_q.png"), (0, -0.03, hz), 1.6, 40, res=(560, 620))
    shot(os.path.join(BUILD, "s3b_back.png"), (0, 0, hz - 0.1), 2.2, 150, res=(560, 620))
    for n in ("exprSmile", "exprLaugh", "exprSurprise"):
        setk(n, 1); shot(os.path.join(BUILD, f"s3b_{n}.png"), (0, -0.05, hz), 1.6, 0, res=(560, 620)); setk(n, 0)
    setk("eyeBlinkLeft", 1); setk("eyeBlinkRight", 1); shot(os.path.join(BUILD, "s3b_blink.png"), (0, -0.05, hz), 1.6, 0, res=(560, 620))
