"""Stage 3c: real 3D clothes. Opens host_stage3b.blend, saves host_stage3c.blend.
Run: blender -b build/host_stage3b.blend --python host/stage3_garments.py
Both garments start from one relaxed shell around the body, so denim always sits outside the tee. Edges are cut along smooth
fields (never along body topology) and folded inward for thickness. Skin under the clothes is removed: nothing can poke through."""
import math
import os
import sys

import bmesh
import bpy
import mathutils
import numpy as np
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD, HEX, TEX, Binder, coords, loft, material, mesh_object

body = bpy.data.objects["host_body"]; rig = bpy.data.objects["host_rig"]
mask = np.load(os.path.join(BUILD, "head_mask.npy"))
P = coords(body.data); binder = Binder(body, rig); bones = rig.data.bones
vis_i = body.vertex_groups["body"].index
vis = np.array([any(g.group == vis_i for g in v.groups) for v in body.data.vertices])
ARM = {b.name for b in bones if any(b.name.startswith(k) for k in ("upperarm", "lowerarm", "wrist", "finger", "metacarpal"))}
armw = np.array([sum(w for n, w in d.items() if n in ARM) for d in binder.w])
coralM = material("coral", colour=HEX["coral"], rough=0.8)
denimM = material("denim", os.path.join(TEX, "denim.png"), rough=0.78, normal=os.path.join(TEX, "denim_n.png"), nstrength=0.7)
silverM = material("silver", colour=HEX["silver"], rough=0.28, metal=1.0)
stitchM = material("stitch", colour=HEX["stitch"], rough=0.7)

ZW, ZB, ZK, HEM, WAIST_TEE = 1.0, 1.178, 1.115, 0.098, 0.93


def smooth(t):
    t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)


def cut(bm, fn):
    """Keep fn(p) >= 0, slicing faces along the zero line."""
    fl = bm.verts.layers.float["f"]
    vals = fn(np.array([v.co for v in bm.verts]), bm)
    for v, x in zip(bm.verts, vals):
        v[fl] = float(x) if abs(x) > 1e-7 else 1e-7
    for e in list(bm.edges):
        a, b = e.verts
        if a[fl] * b[fl] < 0:
            _, nv = bmesh.utils.edge_split(e, a, a[fl] / (a[fl] - b[fl])); nv[fl] = 0.0
    for f in list(bm.faces):
        z = [v for v in f.verts if v[fl] == 0.0]
        if len(z) == 2 and z[1] not in [e.other_vert(z[0]) for e in z[0].link_edges]:
            bmesh.ops.connect_verts(bm, verts=z)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v[fl] < 0], context="VERTS")
    for _ in range(60):                              # the cut edge relaxes into one clean line
        new = {}
        for v in bm.verts:
            if v.is_boundary:
                nb = [e.other_vert(v).co for e in v.link_edges if e.is_boundary]
                if len(nb) == 2:
                    new[v] = v.co * 0.4 + (nb[0] + nb[1]) * 0.3
        for v, q in new.items():
            v.co = q


# ---- master shell: torso, upper arms, legs
idx = np.where((mask < 0.5) & vis)[0]
rm = {int(v): n for n, v in enumerate(idx)}
bm = bmesh.new()
al = bm.verts.layers.float.new("arm")
bm.verts.layers.float.new("f")
BV = [bm.verts.new(tuple(P[v])) for v in idx]
for pl in body.data.polygons:
    vs = list(pl.vertices)
    if all(v in rm for v in vs):
        bm.faces.new([BV[rm[v]] for v in vs])
for v, i in zip(BV, idx):
    v[al] = float(armw[i])
sides = {}
for s, tag in ((1, "L"), (-1, "R")):
    a = np.array(bones[f"upperarm01.{tag}"].head_local); e = np.array(bones[f"lowerarm01.{tag}"].head_local)
    d = (e - a) / np.linalg.norm(e - a)
    sides[s] = (a, e, d, np.linalg.norm(e - a))


def arm_field(t):
    """Positive on the shoulder side of a plane t of the way down the upper arm; arms only."""
    def fn(p, b):
        al_ = b.verts.layers.float["arm"]
        arm = np.array([v[al_] for v in b.verts]) > 0.5
        out = np.ones(len(p))
        for s, (a, e, d, L) in sides.items():
            i = arm & (p[:, 0] * s > 0)
            out[i] = -((p[i] - (a + d * L * t)) @ d)
        return out
    return fn


cut(bm, arm_field(0.86))
cut(bm, lambda p, b: p[:, 2] - 0.07)
bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=1, use_grid_fill=True)
bm.verts.ensure_lookup_table(); bm.normal_update()


def leg_axis(z, tag):
    pts = [np.array(bones[f"upperleg02.{tag}"].head_local), np.array(bones[f"lowerleg01.{tag}"].head_local), np.array(bones[f"lowerleg02.{tag}"].tail_local)]
    zs = [q[2] for q in pts][::-1]
    return np.stack([np.interp(z, zs, [q[i] for q in pts][::-1]) for i in (0, 1)], 1)


def relax(b, off, iters, strength=0.6):
    b.verts.index_update(); b.edges.index_update()
    p = np.array([v.co for v in b.verts])
    ed = np.array([[e.verts[0].index, e.verts[1].index] for e in b.edges])
    free = np.array([not v.is_boundary for v in b.verts])
    offs = np.full(len(p), off) if np.isscalar(off) else off
    for _ in range(iters):
        acc = np.zeros_like(p); cnt = np.zeros(len(p))
        np.add.at(acc, ed[:, 0], p[ed[:, 1]]); np.add.at(acc, ed[:, 1], p[ed[:, 0]]); np.add.at(cnt, ed.ravel(), 1)
        p[free] += strength * (acc[free] / cnt[free, None] - p[free])
        for i in range(len(p)):
            loc, n, _, _ = binder.bvh.find_nearest(mathutils.Vector(p[i]))
            h = (mathutils.Vector(p[i]) - loc).dot(n)
            if h < offs[i]:
                p[i] = np.array(loc + n * offs[i])
    for v, q in zip(b.verts, p):
        v.co = q
    b.normal_update()


# trouser tubes: blend each leg towards a straight relaxed section
p = np.array([v.co for v in bm.verts])
ramp = smooth((0.725 - p[:, 2]) / 0.16)
Rz = np.interp(p[:, 2], [0.09, 0.25, 0.5, 0.72], [0.061, 0.063, 0.074, 0.098])
for tag, s in (("L", 1), ("R", -1)):
    i = (p[:, 0] * s > 0) & (p[:, 2] < 0.74)
    c = leg_axis(p[i, 2], tag)
    d = p[i, :2] - c; r = np.linalg.norm(d, axis=1, keepdims=True); d /= np.maximum(r, 1e-6)
    p[i, :2] = (p[i, :2] * (1 - ramp[i, None])) + (c + d * Rz[i, None]) * ramp[i, None]
for v, q in zip(bm.verts, p):
    v.co = q
relax(bm, 0.0052, 7)


# ---- fields
def neck(p, b=None):
    az = np.degrees(np.arctan2(np.abs(p[:, 0]), -(p[:, 1] + 0.02)))
    return np.interp(az, [0, 12, 40, 80, 120, 180], [1.222, 1.222, 1.24, 1.282, 1.296, 1.3]) - p[:, 2]


def tee_field(p, b):
    return np.minimum(np.minimum(neck(p), arm_field(0.47)(p, b)), p[:, 2] - WAIST_TEE)


def denim_top(p, b=None):
    x, z = np.abs(p[:, 0]), p[:, 2]
    bib = np.minimum(ZB - z, np.interp(z, [ZW, ZB], [0.135, 0.098]) - x)
    bk = np.minimum(ZK - z, np.interp(z, [ZW, ZK], [0.13, 0.078]) - x)
    return np.maximum(ZW - z, np.where(p[:, 1] < -0.02, bib, bk))


def denim_field(p, b):
    al_ = b.verts.layers.float["arm"]
    arm = np.array([v[al_] for v in b.verts]) > 0.5
    return np.where(arm, -1.0, np.minimum(denim_top(p), p[:, 2] - HEM))


# ---- tee
def fold(b, depth, back):
    """Turn raw edges under: gives every hem real thickness without doubling the whole garment."""
    edges = [e for e in b.edges if e.is_boundary]
    b.normal_update()
    ex = bmesh.ops.extrude_edge_only(b, edges=edges)
    nv = [g for g in ex["geom"] if isinstance(g, bmesh.types.BMVert)]
    for v in nv:
        src = next((e.other_vert(v) for e in v.link_edges if not e.is_boundary), None)
        n = src.normal if src else mathutils.Vector((0, 0, 0))
        v.co -= n * depth
    edges = [e for e in b.edges if e.is_boundary]
    ex = bmesh.ops.extrude_edge_only(b, edges=edges)
    for v in [g for g in ex["geom"] if isinstance(g, bmesh.types.BMVert)]:
        src = next((e.other_vert(v) for e in v.link_edges if not e.is_boundary), None)
        src2 = next((e.other_vert(src) for e in src.link_edges if e.other_vert(src) is not v and not e.is_boundary), None) if src else None
        if src2:
            v.co += (src2.co - src.co).normalized() * 0
        v.co += (mathutils.Vector((0, 0, 0)))
    b.normal_update()


tee = bm.copy()
cut(tee, tee_field)
tee.normal_update()
tp = np.array([v.co for v in tee.verts]); tn = np.array([v.normal for v in tee.verts])
rib = smooth(1 - neck(tp) / 0.015) * 0.0016 * (neck(tp) < 0.02)    # raised collar band
sl = np.zeros(len(tp))
arm = np.array([v[tee.verts.layers.float["arm"]] for v in tee.verts]) > 0.5
sl[arm] = 0.0035                                                      # sleeves stand a little off the arm
for v, q in zip(tee.verts, tp + tn * (rib + sl)[:, None]):
    v.co = q
fold(tee, 0.0028, 0.01)
teeO = mesh_object("host_tee", tee, coralM, rig)

# ---- overalls
den = bm.copy()
cut(den, denim_field)
den.normal_update()
dp = np.array([v.co for v in den.verts]); dn = np.array([v.normal for v in den.verts])
# soft cloth folds: knees and hip, a few millimetres, so the legs do not look like tubes
ang = np.arctan2(dp[:, 1] + 0.03, dp[:, 0] - np.sign(dp[:, 0]) * 0.13)
wr = 0.0016 * np.sin(dp[:, 2] * 62 + 2.2 * np.sin(ang * 2)) * (np.exp(-((dp[:, 2] - 0.45) / 0.07) ** 2) + 0.7 * np.exp(-((dp[:, 2] - 0.14) / 0.05) ** 2) + 0.6 * np.exp(-((dp[:, 2] - 0.8) / 0.05) ** 2))
extra = 0.0046 + wr + 0.0012 * smooth((dp[:, 2] - ZW) / 0.02)
dp = dp + dn * extra[:, None]
# a bib is flat cloth hanging off the chest, not a skin over it: fit one gentle surface in front of the bust
bibv = (dp[:, 1] < -0.02) & (dp[:, 2] > ZW - 0.01)
A = lambda q: np.stack([np.ones(len(q)), q[:, 0] ** 2, q[:, 2], q[:, 2] ** 2], 1)
co, *_ = np.linalg.lstsq(A(dp[bibv]), dp[bibv, 1], rcond=None)
surf = A(dp) @ co
surf -= (surf[bibv] - dp[bibv, 1]).max()
wgt = smooth((dp[:, 2] - ZW + 0.03) / 0.09) * bibv
dp[:, 1] += (surf - dp[:, 1]) * wgt
for v, q in zip(den.verts, dp):
    v.co = q
den.normal_update()
shell_bvh = BVHTree.FromBMesh(den)
den_for_iso = den.copy()
fold(den, 0.0034, 0.01)


def box_uv(b, tile=0.16):
    ul = b.loops.layers.uv.get("UVMap") or b.loops.layers.uv.new("UVMap")
    for f in b.faces:
        n = f.normal
        for l in f.loops:
            c = l.vert.co
            l[ul].uv = ((c.y if abs(n.x) > abs(n.y) else c.x) / tile, c.z / tile)


box_uv(den)
denO = mesh_object("host_overalls", den, denimM, rig)

# ---- chest pocket
PX, PZ0, PZ1 = 0.056, 1.066, 1.142


def pocket(p, b=None):
    x, z = np.abs(p[:, 0]), p[:, 2]
    v_bottom = PZ0 + 0.018 * (x / PX)                # shallow V at the bottom
    return np.where(p[:, 1] < -0.02, np.minimum(np.minimum(PX - x, PZ1 - z), z - v_bottom), -1.0)


pk = den_for_iso.copy()
cut(pk, pocket)
pk.normal_update()
for v in pk.verts:
    v.co += v.normal * 0.0024
fold(pk, 0.0026, 0.004)
box_uv(pk)
pkO = mesh_object("host_pocket", pk, denimM, rig)


# ---- straps
tee_bvh = BVHTree.FromBMesh(den_for_iso)
tee_b = bmesh.new(); tee_b.from_mesh(teeO.data); tb_bvh = BVHTree.FromBMesh(tee_b)


def ray(bvh, o, d):
    h = bvh.ray_cast(mathutils.Vector(o), mathutils.Vector(d).normalized())
    return (np.array(h[0]), np.array(h[1])) if h[0] else (None, None)


def strap_path(s):
    pts = []
    for t in np.linspace(0, 1, 9):                   # up the chest
        x, z = 0.081 + 0.012 * t, ZB - 0.035 + (1.262 - ZB + 0.035) * t
        q, n = ray(shell_bvh, (s * x, -0.6, z), (0, 1, 0))     # on the bib where it exists, on the tee above it
        if q is None:
            q, n = ray(tb_bvh, (s * x, -0.6, z), (0, 1, 0))
        if q is not None:
            pts.append((q, n))
    for y in np.linspace(-0.07, 0.035, 8):           # over the shoulder
        q, n = ray(tb_bvh, (s * 0.095, y, 1.34), (0, 0, -1))
        if q is not None:
            pts.append((q, n))
    for t in np.linspace(0, 1, 10):                  # down the back
        x, z = 0.093 - 0.03 * t, 1.262 - (1.262 - ZK + 0.03) * t
        q, n = ray(tb_bvh, (s * x, 0.6, z), (0, -1, 0))
        if q is not None:
            pts.append((q, n))
    q = np.array([a for a, _ in pts]); n = np.array([b for _, b in pts])
    n = n * np.sign(np.einsum("ij,ij->i", n, q - np.array([0, -0.02, 1.15])))[:, None]
    q = q + n * 0.0072                               # clears the denim bib where it lies on top
    t = np.r_[0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]; g = np.linspace(0, t[-1], 64)
    Q = np.stack([np.interp(g, t, q[:, i]) for i in range(3)], 1); Nn = np.stack([np.interp(g, t, n[:, i]) for i in range(3)], 1)
    for _ in range(14):
        Q[1:-1] = (Q[:-2] + 2 * Q[1:-1] + Q[2:]) / 4; Nn[1:-1] = (Nn[:-2] + 2 * Nn[1:-1] + Nn[2:]) / 4
    return Q, Nn / np.linalg.norm(Nn, axis=1, keepdims=True)


SW, ST = 0.031, 0.0032
strap_lines = []
sbm_all = []
for s in (1, -1):
    Q, Nn = strap_path(s)
    T = np.gradient(Q, axis=0); T /= np.linalg.norm(T, axis=1, keepdims=True)
    S = np.cross(T, Nn); S /= np.linalg.norm(S, axis=1, keepdims=True)
    sec = [(-SW / 2, 0), (-SW / 2, ST * 0.85), (-SW / 2 + 0.002, ST), (SW / 2 - 0.002, ST), (SW / 2, ST * 0.85), (SW / 2, 0)]
    rings = [np.array([Q[i] + S[i] * a + Nn[i] * b for a, b in sec]) for i in range(len(Q))]
    b = loft(rings)
    bmesh.ops.contextual_create(b, geom=[v for v in b.verts if (v.co - mathutils.Vector(Q[0])).length < 0.03 and v.is_boundary])
    bmesh.ops.contextual_create(b, geom=[v for v in b.verts if (v.co - mathutils.Vector(Q[-1])).length < 0.03 and v.is_boundary])
    bmesh.ops.recalc_face_normals(b, faces=b.faces)
    b.normal_update(); box_uv(b)
    o = mesh_object(f"host_strap_{'L' if s > 0 else 'R'}", b, denimM, rig)
    for sign in (1, -1):
        strap_lines.append((Q + S * sign * (SW / 2 - 0.0028) + Nn * (ST + 0.0004), Nn))
    sbm_all.append((Q, Nn, s))


# ---- buttons
def button(c, n, r=0.0092):
    n = n / np.linalg.norm(n)
    a = np.cross(n, [0, 0, 1.0]); a = a / max(np.linalg.norm(a), 1e-6); b = np.cross(n, a)
    th = np.arange(20) / 20 * 2 * np.pi
    prof = [(0.0, 0), (1.0, 0), (1.0, 0.0018), (0.82, 0.0032), (0.55, 0.0026), (0.3, 0.0036), (0.0, 0.0038)]
    return [c + (np.cos(th) * r * q)[:, None] * a + (np.sin(th) * r * q)[:, None] * b + n * h for q, h in prof]


bb = bmesh.new(); centres = []
spots = []
for Q, Nn, s in sbm_all:
    spots.append((Q[3] + Nn[3] * ST, Nn[3]))
    q, n = ray(shell_bvh, (s * 0.124, -0.6, ZW + 0.006), (0, 1, 0))
    if q is not None:
        spots.append((q, n if n[1] < 0 else -n))
for c, n in spots:
    rings = button(np.array(c), np.array(n))
    tmp = loft(rings)
    me_t = bpy.data.meshes.new("t"); tmp.to_mesh(me_t); tmp.free(); bb.from_mesh(me_t); bpy.data.meshes.remove(me_t)
    centres.append(c)
bmesh.ops.recalc_face_normals(bb, faces=bb.faces)
btn = mesh_object("host_buttons", bb, silverM, rig)


# ---- stitching: thin raised dashes along iso-lines of the same fields
def isolines(b, fn, val):
    vals = {v: x for v, x in zip(b.verts, fn(np.array([v.co for v in b.verts]), b) - val)}
    segs = []
    for f in b.faces:
        cross = []
        for l in f.loops:
            a, c = l.vert, l.link_loop_next.vert
            if vals[a] * vals[c] < 0:
                t = vals[a] / (vals[a] - vals[c]); cross.append(a.co.lerp(c.co, t).copy())
        if len(cross) == 2:
            segs.append(cross)
    key = lambda q: (round(q.x, 5), round(q.y, 5), round(q.z, 5))
    nb = {}
    for i, (a, c) in enumerate(segs):
        nb.setdefault(key(a), []).append((i, c)); nb.setdefault(key(c), []).append((i, a))
    used = set(); lines = []
    for i, (a, c) in enumerate(segs):
        if i in used:
            continue
        used.add(i); line = [a, c]
        for end in (1, 0):
            while True:
                q = line[-1] if end else line[0]
                nxt = next(((j, o) for j, o in nb.get(key(q), []) if j not in used), None)
                if not nxt:
                    break
                used.add(nxt[0]); line.append(nxt[1]) if end else line.insert(0, nxt[1])
        lines.append(np.array(line))
    return lines


def dashes(out, line, normals=None, dash=0.0052, gap=0.0028, w=0.0015, lift=0.0007):
    if len(line) < 3:
        return
    t = np.r_[0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
    pos = 0.0
    while pos + dash < t[-1]:
        a = np.array([np.interp(pos, t, line[:, i]) for i in range(3)]); c = np.array([np.interp(pos + dash, t, line[:, i]) for i in range(3)])
        m = (a + c) / 2
        if normals is None:
            loc, n, _, _ = shell_bvh.find_nearest(mathutils.Vector(m)); n = np.array(n)
            if n @ (m - np.array([0, -0.03, m[2]])) < 0:
                n = -n
        else:
            n = np.array([np.interp(pos, t, normals[:, i]) for i in range(3)])
        d = c - a; sd = np.cross(d, n); sd = sd / max(np.linalg.norm(sd), 1e-9) * w / 2
        vs = [out.verts.new(tuple(q + n * lift)) for q in (a - sd, c - sd, c + sd, a + sd)]
        out.faces.new(vs)
        pos += dash + gap


st = bmesh.new()
ref = den_for_iso
for fn, vals in ((lambda p, b: denim_top(p), (0.0055, 0.0105)), (lambda p, b: p[:, 2] - HEM, (0.012, 0.0165)), (pocket, (0.0045,))):
    for val in vals:
        for line in isolines(ref, fn, val):
            dashes(st, line)
for line in isolines(ref, lambda p, b: ZW + 0.0 - p[:, 2], 0.0):        # waistband seam
    dashes(st, line)
for line in isolines(ref, lambda p, b: ZW - 0.034 - p[:, 2], 0.0):
    dashes(st, line)
fly = lambda p, b: 0.024 - np.abs(p[:, 0]) + (p[:, 1] > -0.02) * 9
for line in isolines(ref, fly, 0.0):
    keep = (line[:, 2] > 0.84) & (line[:, 2] < ZW - 0.034)
    if keep.sum() > 3:
        dashes(st, line[keep])
for line, nn in strap_lines:
    dashes(st, line, normals=nn)
print("REPORT stitches", len(st.faces))
stO = mesh_object("host_stitch", st, stitchM, rig)

# ---- skin everything to the skeleton through the body surface
REMAP = {"breast.L": "spine01", "breast.R": "spine01"}
for o in (teeO, denO, pkO, bpy.data.objects["host_strap_L"], bpy.data.objects["host_strap_R"], stO):
    I, B = binder.locate(coords(o.data)); binder.skin(o, I, B, REMAP)
    print("REPORT", o.name, "verts", len(o.data.vertices), "faces", len(o.data.polygons))
bc = coords(btn.data)
for g in list(btn.vertex_groups):
    btn.vertex_groups.remove(g)
per = len(bc) // max(len(centres), 1)
for k, c in enumerate(centres):                      # each button moves as one rigid piece
    I, B = binder.locate([np.array(c)])
    acc = {}
    for i, w in zip(I[0], B[0]):
        for n, x in binder.w[i].items():
            n = REMAP.get(n, n); acc[n] = acc.get(n, 0) + x * w
    top = sorted(acc.items(), key=lambda kv: -kv[1])[:4]; tot = sum(x for _, x in top)
    for n, x in top:
        g = btn.vertex_groups.get(n) or btn.vertex_groups.new(name=n)
        g.add(list(range(k * per, (k + 1) * per)), x / tot, "REPLACE")

# ---- remove skin that clothes cover, plus MakeHuman helper geometry (keeps all shape keys)
class FakeArm:
    pass


armmask = armw > 0.5
covered = np.zeros(len(P), bool)
top_ok = neck(P) > 0.022
for s, (a, e, d, L) in sides.items():
    sleeve = -((P - (a + d * L * 0.47)) @ d)
    side = P[:, 0] * s > 0
    covered |= side & armmask & (sleeve > 0.03)
covered |= (~armmask) & top_ok & (P[:, 2] > 0.1) & (mask < 0.05)
covered |= (~armmask) & (P[:, 2] <= 0.075)
drop = covered | ~vis
bpy.context.view_layer.objects.active = body
for o in bpy.context.selected_objects:
    o.select_set(False)
body.select_set(True)
for m in list(body.modifiers):
    if m.type == "MASK":
        body.modifiers.remove(m)
body.data.vertices.foreach_set("select", drop)
body.data.edges.foreach_set("select", np.zeros(len(body.data.edges), bool)); body.data.polygons.foreach_set("select", np.zeros(len(body.data.polygons), bool))
body.data.update()
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_mode(type="VERT")
bpy.ops.mesh.delete(type="VERT"); bpy.ops.object.mode_set(mode="OBJECT")
print("REPORT body verts now", len(body.data.vertices), "keys", len(body.data.shape_keys.key_blocks))

sh = bpy.data.objects["host_shoes"]
print("REPORT shoes z", coords(sh.data)[:, 2].min(), coords(sh.data)[:, 2].max(), "mats", [m.name for m in sh.data.materials])
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "host_stage3c.blend"))
print("SAVED stage3c")
