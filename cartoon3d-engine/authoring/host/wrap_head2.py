"""Head candidate: keeps the wrapped skin from test t3, rebuilds lids and lips as ring loops, adds a separate mouth interior,
authors keys for this mesh, and paints the texture straight from the mesh (no ray bake).
Run: blender -b build/wrap/wrap_t3.blend --python host/wrap_head2.py -- c1 [--anim]
Writes only to build/wrap/<tag>/ and build/wrap/cand_<tag>.blend."""
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
from stage3_common import BUILD, coords, lin, loft, material, shot

ARGS = sys.argv[sys.argv.index("--") + 1:]; TAG = ARGS[0]
OUT = os.path.join(BUILD, "wrap", TAG); os.makedirs(OUT, exist_ok=True)
C = CONCEPTS["H"]; M = C["mouth"]; L = C["lid"]; SM = C["smile"]
EX, EY, EZ, ER = C["eye_x"], C["eye_y"], C["eye_z"], C["eye_r"]
RIM = ER + 0.0012 + 2 * L["thick"]; DROP = C["drop"]
M = dict(M, curve=M["curve"] * 1.3)                    # h10's resting smile reads from this curve
LIPH = 1.2                                             # lip height factor: thinner, closer to h10
L = dict(L, up=L["up"] * 0.8, down=L["down"] * 0.9)   # h10's rounded rim closes the visible opening a little
EYES = {1: np.array((EX, EY, EZ)), -1: np.array((-EX, EY, EZ))}


def mouth_z(x):
    return M["z"] + M["curve"] * (np.asarray(x) / M["w"]) ** 2


def lip_y(x):
    return M["y"] + M["yc"] * np.asarray(x) ** 2


# ---------- start from the tested wrap
wrap = bpy.data.objects["wrap_head"]
wrap.shape_key_clear()
npz = np.load(os.path.join(BUILD, "wrap", "t3", "wrap.npz"))
Q0, S0, inner, idx = npz["Q"], npz["S"], npz["inner"], npz["idx"]
LIN = np.load(os.path.join(BUILD, "eye_lining.npy"))[idx]
lipf = np.zeros(len(np.load(os.path.join(BUILD, "eye_lining.npy"))), bool); lipf[np.load(os.path.join(BUILD, "lip_verts.npy"))] = True
LIP = lipf[idx]
assert np.allclose(coords(wrap.data), Q0, atol=1e-5)
tgt = bpy.data.objects["concept_head"]
tb = bmesh.new(); tb.from_mesh(tgt.data)
for lay in list(tb.verts.layers.shape):
    tb.verts.layers.shape.remove(lay)
fc = np.array([f.calc_center_median() for f in tb.faces]); keep = np.ones(len(fc), bool)
for c in EYES.values():
    keep &= np.linalg.norm(fc - c, axis=1) > RIM - 0.0006
keep &= ~((np.abs(fc[:, 0]) < M["w"] * 1.12) & (fc[:, 1] > lip_y(fc[:, 0]) + 0.0085) & (fc[:, 1] < M["y"] + 0.1) & (np.abs(fc[:, 2] - M["z"]) < 0.036))
tv = np.array([v.co for v in tb.verts]); qf = np.array([[v.index for v in f.verts] for f in tb.faces])[keep]
bvhO = BVHTree.FromPolygons([tuple(p) for p in tv], [tuple(int(i) for i in q) for q in qf])

bm = bmesh.new(); bm.from_mesh(wrap.data); bm.verts.ensure_lookup_table()
ed = np.array([[e.verts[0].index, e.verts[1].index] for e in bm.edges])


def dilate(m, hops):
    m = m.copy()
    for _ in range(hops):
        n = m.copy(); n[ed[m[ed[:, 0]], 1]] = True; n[ed[m[ed[:, 1]], 0]] = True; m = n
    return m


near_mouth = (np.abs(Q0[:, 0]) < 0.085) & (Q0[:, 2] < M["z"] + 0.018) & (Q0[:, 2] > M["z"] - 0.07) & (Q0[:, 1] < -0.02)
cut_m = dilate(LIP | (inner & near_mouth), C.get("mouth_hops", 2))
cut_e = dilate(LIN, 2)
cut = cut_m | cut_e
print("REPORT cut mouth", cut_m.sum(), "eyes", cut_e.sum())
bmesh.ops.delete(bm, geom=[v for v in bm.verts if cut[v.index]], context="VERTS")
# drop loose islands
seen = set(); comps = []
for v in bm.verts:
    if v in seen:
        continue
    st = [v]; seen.add(v); g = []
    while st:
        a = st.pop(); g.append(a)
        for e in a.link_edges:
            o = e.other_vert(a)
            if o not in seen:
                seen.add(o); st.append(o)
    comps.append(g)
comps.sort(key=len, reverse=True)
for g in comps[1:]:
    bmesh.ops.delete(bm, geom=g, context="VERTS")
print("REPORT islands removed", len(comps) - 1, "verts left", len(bm.verts))


def loops(b):
    done = set(); out = []
    for e0 in b.edges:
        if not e0.is_boundary or e0 in done:
            continue
        lp = [e0.verts[0]]; cur = e0.verts[1]; done.add(e0); prev = e0
        while cur is not lp[0]:
            lp.append(cur)
            nx = [e for e in cur.link_edges if e.is_boundary and e not in done]
            if not nx:
                break
            prev = nx[0]; done.add(prev); cur = prev.other_vert(cur)
        out.append(lp)
    return out


LP = loops(bm)
print("REPORT boundary loops", [(len(l), np.round(np.mean([v.co for v in l], axis=0), 3).tolist()) for l in LP])
holes = {}
for l in LP:
    m = np.mean([v.co for v in l], axis=0)
    if abs(m[2] - EZ) < 0.04 and abs(abs(m[0]) - EX) < 0.03:
        holes[1 if m[0] > 0 else -1] = l
    elif abs(m[0]) < 0.02 and abs(m[2] - M["z"]) < 0.04:
        holes["m"] = l
assert set(holes) == {1, -1, "m"}, list(holes)


def surf(p):
    return np.array(bvhO.find_nearest(Vector(p))[0])


def front(x, z, yfall):
    h = bvhO.ray_cast(Vector((x, -0.6, z)), Vector((0, 1, 0)))
    if h[0] is not None and h[0].y < yfall + 0.0125:
        return np.array(h[0])
    return np.array((x, yfall, z))


def dir_of(u, v, s):
    dz = v + L["tilt"] * u + L["v0"]
    d = np.array((s * u, -math.sqrt(max(1 - u * u - dz * dz, 0.012)), dz))
    return d / np.linalg.norm(d)


def order_ccw(l, ctr):
    a = np.unwrap([math.atan2(v.co.z - ctr[1], v.co.x - ctr[0]) for v in l])
    return l if a[-1] > a[0] else l[::-1]


RING = {}                                             # new vertex -> dict of labels used by keys and paint
new_rings = {}


def add_patch(key, rings, loop_verts, labels, dense_from):
    """Ring 0 is the existing boundary (n columns). Rings from dense_from on have 2n columns: fine detail where lids and lips need it."""
    n = len(loop_verts); prev = list(loop_verts)
    for k, r in enumerate(rings):
        cur = [bm.verts.new(tuple(p)) for p in r]
        for j, v in enumerate(cur):
            RING[v] = labels(k, j if k >= dense_from else 2 * j)
        if len(cur) == len(prev):
            for j in range(len(cur)):
                j2 = (j + 1) % len(cur)
                bm.faces.new((prev[j], prev[j2], cur[j2], cur[j]))
        else:
            m = len(cur)
            for j in range(len(prev)):
                j2 = (j + 1) % len(prev)
                bm.faces.new((prev[j], cur[(2 * j + 1) % m], cur[2 * j]))
                bm.faces.new((prev[j], prev[j2], cur[(2 * j + 2) % m], cur[(2 * j + 1) % m]))
        prev = cur
    new_rings[key] = prev


def double(ph):
    n = len(ph); o = np.zeros(2 * n); o[0::2] = ph
    nxt = np.r_[ph[1:], ph[0] + 2 * np.pi]
    o[1::2] = (ph + nxt) / 2
    return o


# ---------- eyes: rings from the old skin in to the lid edge, then tucked behind the lid
for s, c in EYES.items():
    l = order_ccw(holes[s], (c[0], c[2]))
    n = len(l); Bp = np.array([v.co for v in l])
    D = (Bp - c) / np.linalg.norm(Bp - c, axis=1, keepdims=True)
    u = D[:, 0] * s; v = D[:, 2] - L["tilt"] * u - L["v0"]
    ph = np.unwrap(np.arctan2(v / ((L["up"] + L["down"]) / 2), (u - L["u0"]) / L["a"]))
    if ph[-1] < ph[0]:
        ph = ph[::-1]; l = l[::-1]; Bp = Bp[::-1]
    uni = ph[0] + np.arange(n) / n * 2 * np.pi * np.sign(ph[-1] - ph[0])
    ph = 0.45 * ph + 0.55 * uni
    ph2 = double(ph)
    cs, sn = np.cos(ph2), np.sin(ph2)
    xp = np.sign(cs) * np.abs(cs) ** (2 / L["pow"]); up_ = sn > 0
    rim_u = L["u0"] + xp * L["a"] * 0.985
    rim_v = np.where(up_, L["up"], L["down"]) * sn
    tt = np.clip((xp + 1) / 2, 0, 1)                  # 0 inner corner, 1 outer corner
    wl = C.get("lash_w", 0.028) * (0.25 + 0.75 * tt ** 1.2)
    rim = np.array([c + dir_of(a, b, s) * (RIM + (0.0002 if ui else -0.0005)) for a, b, ui in zip(rim_u, rim_v, up_)])
    ball = np.array([c + dir_of(L["u0"] + (a - L["u0"]) * 0.985, b * 0.985, s) * (ER + 0.0007) for a, b in zip(rim_u, rim_v)])
    tuck = np.array([c + dir_of(L["u0"] + (a - L["u0"]) * 0.9, b * 0.9, s) * (ER - 0.0045) for a, b in zip(rim_u, rim_v)])
    def lid_ring(extra):
        out = []
        for a, b, w_, ui in zip(rim_u, rim_v, wl, up_):
            vb = b + ((w_ + extra) if ui else -(0.02 + extra))
            ua = L["u0"] + (a - L["u0"]) * (1 + (0.045 if ui else 0.03) + extra)
            d = dir_of(ua, vb, s); h_ = bvhO.ray_cast(Vector(c + d * 0.1), Vector(-d))
            out.append(np.array(h_[0]) if h_[0] is not None and (h_[0] - Vector(c)).length < RIM + 0.0065 else c + d * (RIM + 0.0004))
        out = np.array(out)
        for _ in range(2):                            # one clean line, no steps from the surface below
            out = (np.roll(out, 1, 0) + 2 * out + np.roll(out, -1, 0)) / 4
        return out

    lash = lid_ring(0.0); lash2 = lid_ring(0.016)     # lash2 lets the paint stop sharply along a dense ring
    r1 = np.array([surf(p) for p in Bp * 0.68 + lash[0::2] * 0.32])
    r2 = np.array([surf(p) for p in Bp * 0.34 + lash[0::2] * 0.66])
    rings = [r1, r2, lash2, lash, rim, ball, tuck]

    def lab(k, j, up_=up_, s=s, rim_u=rim_u, rim_v=rim_v, xp=xp):
        return dict(kind="eye", s=s, ring=k, j=j, up=bool(up_[j]), u=float(rim_u[j]), v=float(rim_v[j]), x=float(xp[j]))
    add_patch(s, rings, l, lab, 2)

# ---------- mouth: rings to the lip edge, lips, a clean parting line, then rolled inward
l = order_ccw(holes["m"], (0.0, M["z"]))
n = len(l); Bp = np.array([v.co for v in l])
ph = np.unwrap(np.arctan2((Bp[:, 2] - M["z"]) / 0.03, Bp[:, 0] / (M["w"] * 1.2)))
if ph[-1] < ph[0]:
    ph = ph[::-1]; l = l[::-1]; Bp = Bp[::-1]
uni = ph[0] + np.arange(n) / n * 2 * np.pi
ph = 0.4 * ph + 0.6 * uni
ph2 = double(ph)
cs, sn = np.cos(ph2), np.sin(ph2)
tx = cs; side = np.where(sn >= 0, 1, -1)
xs = tx * M["w"]; env = np.sqrt(np.clip(1 - tx * tx, 0.0004, 1))
zm = mouth_z(xs); bow = 1 + M["bow"] * (np.exp(-((np.abs(xs) - 0.0085) / 0.0085) ** 2) - 0.75 * np.exp(-(xs / 0.0048) ** 2))
ru = M["up"] * env ** 1.0 * bow; rl = M["low"] * env ** 0.9; rr = np.where(side > 0, ru, rl)   # lips taper to fine corners
yl = lip_y(xs)
seam = np.c_[xs * 0.985, yl + 0.0036, zm + side * 0.00012 * env]
mid = np.array([front(x, z, y + 0.0015) for x, z, y in zip(xs * 0.995, zm + side * (0.6 * rr + 0.0005), yl)])
edge = np.array([front(x, z, y + 0.006) for x, z, y in zip(xs, zm + side * (LIPH * rr + 0.0002), yl)])
edge2 = np.array([front(x, z, y + 0.007) for x, z, y in zip(xs * 1.015, zm + side * (LIPH * rr + 0.0013), yl)])
out1 = np.array([front(x, z, y + 0.008) for x, z, y in zip(xs[0::2] * 1.05, (zm + side * (LIPH * rr + 0.0035))[0::2], yl[0::2])])
for arr in (mid, edge, edge2):
    arr[:] = (np.roll(arr, 1, 0) + 2 * arr + np.roll(arr, -1, 0)) / 4
roll1 = seam + np.c_[0 * xs, 0 * xs + 0.005, side * 0.0024 * env]
roll2 = seam + np.c_[0 * xs, 0 * xs + 0.012, side * 0.0052 * env]
r1 = np.array([surf(p) for p in Bp * 0.6 + out1 * 0.4])


def labm(k, j, side=side, tx=tx, env=env):
    return dict(kind="mouth", ring=k, j=j, side=int(side[j]), t=float(tx[j]), env=float(env[j]))


add_patch("m", [r1, out1, edge2, edge, mid, seam, roll1, roll2], l, labm, 2)

# close stray small openings (none are part of the design), and let the ears follow h10's simple form
for lp in loops(bm):
    m_ = np.mean([v.co for v in lp], axis=0)
    if len(lp) < 20 and abs(m_[0]) > 0.09:
        es = list({e for v in lp for e in v.link_edges if e.is_boundary})
        bmesh.ops.holes_fill(bm, edges=es, sides=len(lp) + 1)
ear = [v for v in bm.verts if abs(v.co.x) > 0.097 and 1.41 < v.co.z < 1.55 and v.co.y > -0.075 and not v.is_boundary]
bm.normal_update()
ec_ = np.array(C["ear_c"]); er_ = np.array(C["ear_r"])
for v in ear:                                         # take h10's ear from the side, so its outline matches
    s_e = 1 if v.co.x > 0 else -1
    q = ((v.co.y - ec_[1]) / (er_[1] * 1.45)) ** 2 + ((v.co.z - ec_[2]) / (er_[2] * 1.45)) ** 2
    hh = bvhO.ray_cast(Vector((s_e * 0.3, v.co.y, v.co.z)), Vector((-s_e, 0, 0))) if q < 1 and v.normal.x * s_e > 0 else (None,)
    v.co = hh[0] if hh[0] is not None else bvhO.find_nearest(v.co)[0]
for _ in range(2):
    newp = {}
    for v in ear:
        nb = [e.other_vert(v).co for e in v.link_edges]
        newp[v] = v.co * 0.75 + sum(nb, Vector()) / len(nb) * 0.25
    for v, p in newp.items():
        v.co = p

bm.verts.index_update(); bm.faces.ensure_lookup_table()
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
# relax the old skin next to the new loops, staying on the approved surface
touch = {v for vs in (holes[1], holes[-1], holes["m"]) for v in vs}
ring_new = {v for v, d in RING.items() if d["ring"] <= 1}
zone = set(touch) | ring_new
for _ in range(3):
    zone |= {e.other_vert(v) for v in list(zone) for e in v.link_edges if e.other_vert(v) not in RING}
zone = [v for v in zone if not v.is_boundary]
for _ in range(14):
    newp = {}
    for v in zone:
        nb = [e.other_vert(v).co for e in v.link_edges]
        newp[v] = v.co * 0.5 + sum(nb, Vector()) / len(nb) * 0.5
    for v, p in newp.items():
        v.co = bvhO.find_nearest(p)[0]
bm.normal_update()
verts = list(bm.verts)
print("REPORT candidate verts", len(verts), "tris", sum(len(f.verts) - 2 for f in bm.faces))
me = bpy.data.meshes.new("cand_head"); bm.to_mesh(me)
info = [RING.get(v) for v in verts]
bm.free()
me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
cand = bpy.data.objects.new("cand_head", me); bpy.context.scene.collection.objects.link(cand); cand.location.z = -DROP
V = coords(me); NV = len(V)
eye_ring = np.array([i["ring"] if i and i["kind"] == "eye" else -1 for i in info])
m_ring = np.array([i["ring"] if i and i["kind"] == "mouth" else -1 for i in info])
m_side = np.array([i["side"] if i and i["kind"] == "mouth" else 0 for i in info], float)
m_env = np.array([i["env"] if i and i["kind"] == "mouth" else 0 for i in info], float)

# ---------- expression fields, authored on this mesh
FACE = {}


def pose(p):
    """Mouth pose as a field. Patch vertices use their own upper/lower label, so nothing depends on matching old positions."""
    g = dict(lift=0, wide=0, back=0, open_up=0, open_down=0, jaw=0, cheek=0, lid=0, pucker=0, fwd=0, press=0, ll_back=0, ll_up=0); g.update(p)
    x, y, z = V[:, 0], V[:, 1], V[:, 2]; Vn = V.copy(); w_ = M["w"]
    t = np.abs(x) / w_; zc = mouth_z(x)
    fr = np.clip((M["y"] + 0.085 - y) / 0.06, 0, 1) ** 2
    wm = np.exp(-((x / (w_ * 1.4)) ** 2 + ((z - M["z"]) / 0.036) ** 2)) * fr
    wl = np.exp(-((x / (w_ * 1.15)) ** 2 + ((z - M["z"]) / 0.02) ** 2)) * fr
    Vn[:, 2] += g["lift"] * np.clip(t, 0, 1.25) ** 2 * wm
    Vn[:, 0] += (g["wide"] - g["pucker"]) * x * wm
    Vn[:, 1] += (g["back"] * np.clip(t, 0, 1.2) ** 2 - g["fwd"]) * wm
    side = np.where(m_ring >= 0, m_side, np.tanh((z - zc) / 0.007))
    env = np.where(m_ring >= 0, np.sqrt(np.clip(1 - np.clip(t, 0, 1) ** 2, 0, 1)), np.sqrt(np.clip(1 - np.clip(t, 0, 1) ** 2, 0, 1)))
    near = np.exp(-((z - zc) / 0.03) ** 2) * fr * np.clip(1.25 - t, 0, 1) ** 0.5
    Vn[:, 2] += near * env * np.where(side > 0, g["open_up"], -g["open_down"]) * np.abs(side)
    low = np.clip((M["z"] - z) / 0.05, 0, 1)
    Vn[:, 2] -= g["jaw"] * np.exp(-((x / 0.07) ** 2)) * low * fr
    Vn[:, 1] += 0.35 * g["jaw"] * np.exp(-((x / 0.07) ** 2)) * low * fr
    Vn[:, 2] += g["press"] * np.where(m_ring >= 4, -side, 0) * 0.0022 * env * (m_ring >= 4)
    Vn[:, 1] += g["ll_back"] * (side < 0) * wl
    Vn[:, 2] += g["ll_up"] * (side < 0) * wl
    for s_ in (1, -1):
        ck = C["cheek_c"]
        gk = np.exp(-(((x - s_ * ck[0]) / 0.042) ** 2 + ((z - ck[2]) / 0.036) ** 2)) * np.clip((-0.01 - y) / 0.05, 0, 1)
        Vn[:, 2] += g["cheek"] * gk; Vn[:, 1] -= g["cheek"] * 0.55 * gk
        lz = np.exp(-(((x - s_ * EX) / 0.03) ** 2 + ((z - (EZ - ER * 0.75)) / 0.012) ** 2)) * np.clip((EY + 0.03 - y) / 0.04, 0, 1)
        Vn[:, 2] += g["lid"] * lz
    return Vn


SMILE_P = dict(lift=0.0172, wide=0.125, back=0.004, open_up=0.0098, open_down=0.0118, jaw=0.0048, cheek=0.0078, lid=SM["lid"], low_hide=0.0028)
PRESET = {
    "smile": SMILE_P,
    "jawOpen": dict(open_up=0.002, open_down=0.019, jaw=0.021, wide=-0.05),
    "viseme_aa": dict(open_up=0.004, open_down=0.0155, jaw=0.015, cheek=0.001),
    "viseme_E": dict(open_up=0.0034, open_down=0.0068, wide=0.075, lift=0.003, jaw=0.004),
    "viseme_I": dict(open_up=0.0026, open_down=0.004, wide=0.1, lift=0.0045, jaw=0.002),
    "viseme_O": dict(open_up=0.0042, open_down=0.0105, jaw=0.011, pucker=0.26, fwd=0.005),
    "viseme_U": dict(open_up=0.002, open_down=0.0042, jaw=0.004, pucker=0.4, fwd=0.0085),
    "viseme_PP": dict(press=1.0, fwd=0.0015),
    "viseme_FF": dict(open_up=0.0052, open_down=0.0, ll_back=0.0075, ll_up=0.0022, jaw=0.001, low_hide=0.004),
    "viseme_SS": dict(open_up=0.0052, open_down=0.0052, wide=0.095, lift=0.0024, teeth_shut=1),
    "viseme_TH": dict(open_up=0.0042, open_down=0.0062, jaw=0.004, tongue_fwd=0.019, tongue_up=0.009),
    "viseme_CH": dict(open_up=0.003, open_down=0.004, pucker=0.16, fwd=0.0035),
    "viseme_DD": dict(open_up=0.0034, open_down=0.0052, jaw=0.003, tongue_up=0.011, tongue_fwd=0.005),
    "viseme_kk": dict(open_up=0.0026, open_down=0.0058, jaw=0.005),
    "viseme_nn": dict(open_up=0.003, open_down=0.0046, jaw=0.003, tongue_up=0.012, tongue_fwd=0.004),
    "viseme_RR": dict(open_up=0.0024, open_down=0.003, pucker=0.18, fwd=0.003),
    "laugh": dict(SMILE_P, open_down=0.021, jaw=0.017, cheek=0.0095, lid=0.0045, low_hide=0),
}
cand.shape_key_add(name="Basis", from_mix=False)
for name, p in PRESET.items():
    k = cand.shape_key_add(name=name, from_mix=False); k.data.foreach_set("co", pose(p).astype(np.float32).ravel()); k.value = 0


# blink: lids travel over the ball, in eye coordinates, column by column
def blink_positions(s, f):
    P = V.copy(); c = EYES[s]
    wr = {0: 0.2, 1: 0.55, 2: 0.9, 3: 0.97, 4: 1.0, 5: 1.0, 6: 1.0}
    for i, d in enumerate(info):
        if not d or d["kind"] != "eye" or d["s"] != s:
            continue
        x_ = d["x"]; vu = L["up"] * math.sqrt(max(1 - abs(x_) ** L["pow"], 0)); vl = -L["down"] * math.sqrt(max(1 - abs(x_) ** L["pow"], 0))
        vc = vl + 0.2 * (vu - vl)
        dv = (vc - vu) if d["up"] else (vc - vl)
        dv *= f * wr[d["ring"]] * (1.0 if d["up"] else 0.9)
        rel = V[i] - c; r = np.linalg.norm(rel); dd = rel / r
        u = dd[0] * s; v = dd[2] - L["tilt"] * u - L["v0"] + dv
        P[i] = c + dir_of(u, v, s) * r
    return P


eda = np.array([[e.vertices[0], e.vertices[1]] for e in me.edges])


def soften(P, s):
    """Spread the lid movement into the skin around it: no outline on a closed eye. The lid edge itself stays exact."""
    D = P - V
    free = (eye_ring < 2) & (np.linalg.norm(V - EYES[s], axis=1) < RIM + 0.05)   # lid skin (rings 2 and in) stays exact
    for _ in range(10):
        acc = np.zeros_like(D); cnt = np.zeros(len(D))
        np.add.at(acc, eda[:, 0], D[eda[:, 1]]); np.add.at(acc, eda[:, 1], D[eda[:, 0]]); np.add.at(cnt, eda.ravel(), 1)
        D[free] = 0.45 * D[free] + 0.55 * acc[free] / np.maximum(cnt[free, None], 1)
    P2 = V + D
    rel = P2 - EYES[s]; r = np.linalg.norm(rel, axis=1)
    lid = (eye_ring >= 0) & (eye_ring <= 4) & (r < RIM - 0.0006) & (rel[:, 1] < 0) & np.array([bool(d) and d["kind"] == "eye" and d["s"] == s for d in info])
    P2[lid] = EYES[s] + rel[lid] / r[lid, None] * (RIM - 0.0005)   # lid skin can never go inside the eyeball
    return P2


for s, nm in ((1, "Left"), (-1, "Right")):
    closed = soften(blink_positions(s, 1.0), s); half = soften(blink_positions(s, 0.5), s)
    k = cand.shape_key_add(name="eyeBlink" + nm, from_mix=False); k.data.foreach_set("co", closed.astype(np.float32).ravel()); k.value = 0
    corr = V + (half - (V + closed) / 2)              # linear morphs cut through the ball at mid blink: this corrective keeps the lid on it
    k = cand.shape_key_add(name="eyeBlinkArc" + nm, from_mix=False); k.data.foreach_set("co", corr.astype(np.float32).ravel()); k.value = 0

# ---------- interior: separate mouth with teeth and tongue
teethM = bpy.data.materials.get("concept_teeth"); mouthM = bpy.data.materials.get("concept_mouth")
tongueM = material("cand_tongue", colour="#d9666a", rough=0.42)


def arch(zroot, zedge, yf, half, depth, n_teeth):
    rows = []
    for i in range(141):
        t = i / 70 - 1
        x = half * math.sin(t * 1.25) / math.sin(1.25)
        y = yf + depth * (1 - math.cos(t * 1.25)) / (1 - math.cos(1.25))
        fr = ((t + 1) / 2 * n_teeth) % 1; cusp = abs(2 * fr - 1) ** 6
        ze = zedge(x) + (zroot - zedge(x)) * 0.13 * cusp
        yg = y + 0.0008 * cusp
        rows.append(np.array([[x, yg, zroot], [x, yg, ze], [x, yg + 0.006, ze], [x, yg + 0.006, zroot]]))
    return rows


yf = float(lip_y(0)) + 0.0165
ub = loft(arch(M["z"] + 0.0145, lambda x: float(mouth_z(x)) + 0.003, yf, M["w"] * 0.88, 0.03, 10))
lb = loft(arch(M["z"] - 0.0092, lambda x: float(mouth_z(x)) - 0.003, yf + 0.0075, M["w"] * 0.72, 0.03, 10))
bmesh.ops.recalc_face_normals(ub, faces=ub.faces); bmesh.ops.recalc_face_normals(lb, faces=lb.faces)


def obj(name, b, mat):
    m_ = bpy.data.meshes.new(name); b.to_mesh(m_); b.free()
    m_.polygons.foreach_set("use_smooth", np.ones(len(m_.polygons), bool)); m_.materials.append(mat)
    o = bpy.data.objects.new(name, m_); bpy.context.scene.collection.objects.link(o); o.location.z = -DROP
    return o


up_t, lo_t = obj("cand_teeth_up", ub, teethM), obj("cand_teeth_low", lb, teethM)
tr = []
for i in range(14):
    t = i / 13; y = yf + 0.008 + t * 0.05; hw = M["w"] * (0.3 + 0.36 * math.sin(min(1, t * 2.4) * 1.57)); zc = M["z"] - 0.0086 + 0.0065 * math.sin(t * 3.0)
    th = np.arange(16) / 16 * 2 * np.pi
    tr.append(np.c_[np.cos(th) * hw, np.full(16, y), zc + np.sin(th) * 0.0052])
tg = loft(tr); bmesh.ops.contextual_create(tg, geom=[v for v in tg.verts if abs(v.co.y - tr[0][0, 1]) < 1e-5]); bmesh.ops.recalc_face_normals(tg, faces=tg.faces)
tongue = obj("cand_tongue", tg, tongueM)
ms = bmesh.new(); bmesh.ops.create_uvsphere(ms, u_segments=32, v_segments=20, radius=1.0)
for v in ms.verts:
    v.co = Vector((v.co.x * M["w"] * 1.3, M["y"] + 0.066 + v.co.y * 0.052, M["z"] - 0.006 + v.co.z * 0.036))
bmesh.ops.delete(ms, geom=[v for v in ms.verts if v.co.y < M["y"] + 0.03], context="VERTS")   # open front: teeth and tongue stay in view
bmesh.ops.reverse_faces(ms, faces=ms.faces)
bag = obj("cand_mouth", ms, mouthM)


def interior_keys():
    for o in (up_t, lo_t, tongue, bag):
        o.shape_key_add(name="Basis", from_mix=False)
    for name, p in PRESET.items():
        g = dict(lift=0, wide=0, open_up=0, open_down=0, jaw=0, pucker=0, low_hide=0, teeth_shut=0, tongue_fwd=0, tongue_up=0); g.update(p)
        drop = 0.0 if g["teeth_shut"] else g["jaw"] * 0.9 + g["open_down"] * 0.45
        wide = 1 + (g["wide"] - g["pucker"]) * 0.8
        for o, moves in ((up_t, 0), (lo_t, 1), (tongue, 1), (bag, 2)):
            P_ = coords(o.data).copy()
            P_[:, 0] *= wide
            if moves == 0:
                t_ = np.abs(P_[:, 0]) / M["w"]; P_[:, 2] += g["lift"] * 0.6 * np.clip(t_, 0, 1.2) ** 2
            elif moves == 1:
                P_[:, 2] -= drop + (g["low_hide"] if o is lo_t else 0); P_[:, 1] += drop * 0.35
                if g["teeth_shut"] and o is lo_t:
                    P_[:, 2] += 0.0048             # teeth meet for S sounds
                if o is tongue:
                    tip = np.clip(1 - (P_[:, 1] - (yf + 0.008)) / 0.05, 0, 1)
                    P_[:, 1] -= g["tongue_fwd"] * tip; P_[:, 2] += g["tongue_up"] * tip
            else:
                low_ = np.clip((M["z"] - P_[:, 2]) / 0.02, 0, 1); P_[:, 2] -= drop * low_
            k = o.shape_key_add(name=name, from_mix=False); k.data.foreach_set("co", P_.astype(np.float32).ravel()); k.value = 0


interior_keys()

# ---------- UVs and a texture painted straight from the mesh
bpy.context.view_layer.objects.active = cand
for o in bpy.context.selected_objects:
    o.select_set(False)
cand.select_set(True)
for lay in list(me.uv_layers):
    me.uv_layers.remove(lay)
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.012)
bpy.ops.object.mode_set(mode="OBJECT")
# designed layout: one clean front projection for the whole face (no islands through lips or lids), the rest in a side strip.
# Hidden inner rings borrow the lid or lip edge coordinates, so they never overlap visible skin.
uvs = np.zeros(len(me.loops) * 2); me.uv_layers.active.data.foreach_get("uv", uvs); uvs = uvs.reshape(-1, 2)
lv = np.zeros(len(me.loops), int); me.loops.foreach_get("vertex_index", lv)
uvs = np.c_[0.755 + uvs[:, 0] * 0.235, 0.01 + uvs[:, 1] * 0.98]
FX, FZ0, FZ1 = 0.116, 1.345, 1.602
key_of = {(d["kind"], d.get("s"), d["ring"], d["j"]): i for i, d in enumerate(info) if d}
src_v = np.arange(NV)
for i, d in enumerate(info):
    if d and d["kind"] == "eye" and d["ring"] >= 5:
        src_v[i] = key_of[("eye", d["s"], 4, d["j"])]
    elif d and d["kind"] == "mouth" and d["ring"] >= 6:
        src_v[i] = key_of[("mouth", None, 5, d["j"])]
Vp = V[src_v]
face_v = (V[:, 1] < -0.04) & (np.abs(V[:, 0]) < FX) & (V[:, 2] > FZ0) & (V[:, 2] < FZ1)
plan = np.c_[0.01 + (Vp[:, 0] + FX) / (2 * FX) * 0.73, 0.01 + (Vp[:, 2] - FZ0) / (FZ1 - FZ0) * 0.98]
ls = np.zeros(len(me.polygons), int); me.polygons.foreach_get("loop_start", ls); lt = np.zeros(len(me.polygons), int); me.polygons.foreach_get("loop_total", lt)
for a_, n_ in zip(ls, lt):
    ix = lv[a_:a_ + n_]
    if face_v[ix].all():
        uvs[a_:a_ + n_] = plan[ix]
me.uv_layers.active.data.foreach_set("uv", uvs.ravel())
lipw = np.zeros(NV); lashw = np.zeros(NV); loww = np.zeros(NV); fold = np.zeros(NV); seamw = np.zeros(NV); aow = np.zeros(NV)
for i, d in enumerate(info):
    if not d:
        continue
    if d["kind"] == "mouth":
        lipw[i] = 0.0 if d["ring"] <= 2 else 1.0
        seamw[i] = 1.0 if d["ring"] >= 5 else 0.0
    else:
        fade = np.clip((d["x"] + 0.82) / 0.3, 0, 1)
        aow[i] = {0: 0.04, 1: 0.16, 2: 0.32, 3: 0.44, 4: 0.5, 5: 0.5, 6: 0.5}[d["ring"]]   # shading Three.js cannot compute around the eye
        if d["up"]:
            corner = float(np.clip((0.97 - abs(d["x"])) / 0.12, 0, 1))   # lash thins out at both corners, so a closed eye keeps a clean line
            lashw[i] = 0.0 if d["ring"] <= 2 else (fade * corner if d["ring"] == 3 else corner)
        else:
            loww[i] = 0.0 if d["ring"] <= 2 else 0.28
hair = bpy.data.objects["concept_hair"]; hb = BVHTree.FromPolygons([tuple(p) for p in coords(hair.data)], [tuple(p.vertices) for p in hair.data.polygons])
hsh = np.array([math.exp(-(hb.find_nearest(Vector(p))[3] / 0.0065) ** 2) if p[2] > EZ - 0.05 else 0.0 for p in V]) * C["hair_shadow"]
RES = 3072
me.calc_loop_triangles()
uvl = np.zeros(len(me.loops) * 2); me.uv_layers.active.data.foreach_get("uv", uvl); uvl = uvl.reshape(-1, 2)
lt_l = np.zeros(len(me.loop_triangles) * 3, int); me.loop_triangles.foreach_get("loops", lt_l); lt_l = lt_l.reshape(-1, 3)
lt_v = np.zeros(len(me.loop_triangles) * 3, int); me.loop_triangles.foreach_get("vertices", lt_v); lt_v = lt_v.reshape(-1, 3)
A5 = np.c_[V, lipw, lashw, loww, hsh, seamw, aow]
buf = np.zeros((RES, RES, A5.shape[1]), np.float32); hit = np.zeros((RES, RES), bool); dep = np.full((RES, RES), 9.0, np.float32)
for tl, tvv in zip(lt_l, lt_v):
    p = uvl[tl] * (RES - 1); x0, y0 = np.floor(p.min(0)).astype(int); x1, y1 = np.ceil(p.max(0)).astype(int) + 1
    xx, yy = np.meshgrid(np.arange(x0, x1), np.arange(y0, y1))
    den = (p[1, 1] - p[2, 1]) * (p[0, 0] - p[2, 0]) + (p[2, 0] - p[1, 0]) * (p[0, 1] - p[2, 1])
    if abs(den) < 1e-9:
        continue
    a = ((p[1, 1] - p[2, 1]) * (xx - p[2, 0]) + (p[2, 0] - p[1, 0]) * (yy - p[2, 1])) / den
    b = ((p[2, 1] - p[0, 1]) * (xx - p[2, 0]) + (p[0, 0] - p[2, 0]) * (yy - p[2, 1])) / den
    c_ = 1 - a - b; ins = (a >= -0.001) & (b >= -0.001) & (c_ >= -0.001)
    if ins.any():
        val = a[..., None] * A5[tvv[0]] + b[..., None] * A5[tvv[1]] + c_[..., None] * A5[tvv[2]]
        yy_, xx_ = yy[ins].clip(0, RES - 1), xx[ins].clip(0, RES - 1)
        vi_ = val[ins]; front_ = vi_[:, 1] < dep[yy_, xx_]    # skin folded under the eye bulge must not overwrite what the camera sees
        yy_, xx_, vi_ = yy_[front_], xx_[front_], vi_[front_]
        buf[yy_, xx_] = vi_; dep[yy_, xx_] = vi_[:, 1]; hit[yy_, xx_] = True
print("REPORT texels covered %.1f%%" % (hit.mean() * 100))
Pz = buf[..., :3].reshape(-1, 3); x, y, z = Pz[:, 0], Pz[:, 1], Pz[:, 2]
col = np.tile(np.array(lin(C["skin"])[:3]), (len(Pz), 1))


def mix(w, h):
    global col
    col = col * (1 - w[:, None]) + np.array(lin(h)[:3]) * w[:, None]


ck = C["cheek_c"]
mix(np.exp(-(((np.abs(x) - ck[0] * 0.96) / 0.034) ** 2 + ((z - ck[2] - 0.004) / 0.027) ** 2)) * (y < -0.03) * C["blush"], C["blush_c"])
mix(np.exp(-(np.linalg.norm(Pz - np.array(C["nose"]["tip"]), axis=1) / 0.016) ** 2) * 0.28, C["blush_c"])
mix(np.clip((np.abs(x) - 0.112) / 0.02, 0, 1) * 0.3, C["blush_c"])
for s, c in EYES.items():
    d = np.linalg.norm(Pz - c, axis=1); uu = (Pz - c) / np.maximum(d, 1e-6)[:, None]
    us = uu[:, 0] * s; fv = uu[:, 2] - L["tilt"] * us - L["v0"]
    fold_ = np.exp(-((fv - L["up"] - L["crease"]) / 0.055) ** 2) * np.exp(-(us / 0.75) ** 2) * (uu[:, 1] < 0) * (d < ER + 0.016)
    mix(fold_ * 0.2, "#d99a78")
A = buf[..., 3:].reshape(-1, 6)
mix(np.clip(A[:, 3], 0, 1), "#a9704c")
mix(np.clip(A[:, 2], 0, 1) * 0.55, "#b56f58")
mix(np.clip(A[:, 5], 0, 1), "#cf8d6e")
mix(np.clip((A[:, 0] - 0.42) / 0.2, 0, 1) * 0.94, C["lip_c"])
mix(np.clip((A[:, 4] - 0.66) / 0.3, 0, 1) * 0.72, "#8f3d38")
mix(np.clip((A[:, 1] - 0.42) / 0.2, 0, 1), "#1a0e08")
img = col.reshape(RES, RES, 3)
for _ in range(12):                                   # bleed past island edges so no seam shows
    for ax, sh in ((0, 1), (0, -1), (1, 1), (1, -1)):
        src, src_h = np.roll(img, sh, ax), np.roll(hit, sh, ax)
        m_ = (~hit) & src_h
        img[m_] = src[m_]; hit = hit | m_
im = bpy.data.images.new("cand_skin", RES, RES, alpha=False, float_buffer=False)
im.colorspace_settings.name = "sRGB"
srgb = np.where(img <= 0.0031308, img * 12.92, 1.055 * np.clip(img, 1e-8, None) ** (1 / 2.4) - 0.055)
im.pixels.foreach_set(np.dstack([np.clip(srgb, 0, 1), np.ones((RES, RES))]).astype(np.float32).ravel())
im.filepath_raw = os.path.join(OUT, "skin.png"); im.file_format = "PNG"; im.save()
sm = material("cand_skin_m", rough=C["skin_rough"])
nt = sm.node_tree; bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = im; nt.links.new(tn.outputs[0], bs.inputs["Base Color"])
bs.inputs["Subsurface Weight"].default_value = 0.35; bs.inputs["Subsurface Radius"].default_value = (0.9, 0.4, 0.25); bs.inputs["Subsurface Scale"].default_value = 0.012
me.materials.clear(); me.materials.append(sm)

for n_ in ("wrap_head", "concept_head", "concept_teeth", "concept_mouth", "concept_lash", "host_shoes", "host_body"):
    if n_ in bpy.data.objects:
        bpy.data.objects[n_].hide_render = True
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "wrap", f"cand_{TAG}.blend"), copy=True)

# ---------- renders: same light and camera rule as h10
s_ = bpy.context.scene
s_.render.engine = "BLENDER_EEVEE"; s_.render.film_transparent = True
s_.view_settings.view_transform = "Standard"; s_.view_settings.look = "None"; s_.view_settings.exposure = 0
for kx, vx in (("use_raytracing", True), ("taa_render_samples", 32)):
    if hasattr(s_.eevee, kx):
        setattr(s_.eevee, kx, vx)
if "p_key" not in bpy.data.objects:
    TG0 = Vector((0, -0.05, 1.475))
    for nme, en, off, size, colr in (("p_key", 24, (-0.85, -1.15, 0.65), 1.4, (1, .95, .89)), ("p_fill", 8, (1.1, -1.1, 0.05), 1.8, (.94, .96, 1)),
                                     ("p_hair", 16, (0.65, 0.95, 0.75), 0.8, (1, .97, .93)), ("p_bounce", 3, (0, -0.8, -0.7), 1.2, (1, .86, .76))):
        Lg = bpy.data.lights.new(nme, "AREA"); Lg.energy = en; Lg.size = size; Lg.color = colr
        o = bpy.data.objects.new(nme, Lg); s_.collection.objects.link(o); o.location = TG0 + Vector(off)
        o.rotation_euler = (TG0 - o.location).to_track_quat("-Z", "Y").to_euler()
w = bpy.data.worlds.get("portrait") or bpy.data.worlds.new("portrait"); s_.world = w; w.use_nodes = True
b0 = w.node_tree.nodes["Background"]; b0.inputs[0].default_value = lin("#e9e4de"); b0.inputs[1].default_value = 0.44
TG = (0, -0.05, 1.475)
KO = [cand, up_t, lo_t, tongue, bag]


def setk(**v):
    for o in KO:
        for k in o.data.shape_keys.key_blocks[1:]:
            k.value = v.get(k.name, 0)


def blink(w_):
    return {"eyeBlinkLeft": w_, "eyeBlinkRight": w_, "eyeBlinkArcLeft": 4 * w_ * (1 - w_), "eyeBlinkArcRight": 4 * w_ * (1 - w_)}


SHOTS = [("front_neutral", 0, {}, (800, 950)), ("q_neutral", 35, {}, (800, 950)), ("side_neutral", 90, {}, (800, 950)), ("front_smile", 0, {"smile": 1}, (800, 950)), ("q_smile", 35, {"smile": 1}, (800, 950)), ("side_smile", 90, {"smile": 1}, (800, 950))]
for name, kv in (("blink_half", blink(.5)), ("blink_full", blink(1)), ("jaw", {"jawOpen": 1}), ("laugh", {"laugh": 1}), ("aa", {"viseme_aa": 1}), ("E", {"viseme_E": 1}), ("I", {"viseme_I": 1}), ("O", {"viseme_O": 1}), ("U", {"viseme_U": 1}),
                 ("PP", {"viseme_PP": 1}), ("FF", {"viseme_FF": 1}), ("SS", {"viseme_SS": 1}), ("TH", {"viseme_TH": 1}), ("smile_blink", dict(blink(1), smile=1)), ("smile_aa", {"smile": 0.6, "viseme_aa": 0.6})):
    SHOTS.append((name, 0, kv, (480, 570)))
for name, az, kv, res in SHOTS:
    setk(**kv); a = dict(target=TG, dist=1.58, lens=85, res=res)
    if name.startswith("side"):
        a["target"] = (0.1, 0.035, 1.43)
    shot(os.path.join(OUT, name + ".png"), azimuth=az, **a)
setk()
e_ = (0, EY, EZ - DROP + 0.004)
shot(os.path.join(OUT, "eyes.png"), target=e_, dist=0.68, azimuth=0, lens=85, res=(1200, 640))
setk(**blink(1)); shot(os.path.join(OUT, "eyes_closed.png"), target=e_, dist=0.68, azimuth=0, lens=85, res=(1200, 640))
setk(); m_ = (0, M["y"], M["z"] - DROP)
shot(os.path.join(OUT, "mouth_neutral.png"), target=m_, dist=0.5, azimuth=0, lens=85, res=(800, 560))
setk(smile=1); shot(os.path.join(OUT, "mouth_smile.png"), target=m_, dist=0.5, azimuth=0, lens=85, res=(800, 560))
setk(); shot(os.path.join(OUT, "ear.png"), target=(0.11, 0.0, 1.45), dist=0.75, azimuth=90, lens=85, res=(640, 640))
shot(os.path.join(OUT, "neck.png"), target=(0, -0.02, 1.30), dist=0.8, azimuth=25, lens=85, res=(640, 640))
if "--anim" in ARGS:
    os.makedirs(os.path.join(OUT, "anim"), exist_ok=True)
    s_.eevee.taa_render_samples = 12
    seq = [("viseme_sil", 3), ("viseme_aa", 5), ("viseme_E", 4), ("viseme_PP", 3), ("viseme_O", 5), ("viseme_nn", 3), ("viseme_I", 4), ("viseme_FF", 3), ("viseme_aa", 5), ("viseme_U", 4), ("viseme_sil", 5), ("smile", 8)]
    tl = []
    for nme, dur in seq:
        tl += [nme] * dur
    prev = {}
    for f, nme in enumerate(tl):
        tgtv = {nme: 1.0} if nme in PRESET else {}
        cur = {k: prev.get(k, 0) * 0.45 for k in set(prev) | set(tgtv)}
        for k, v_ in tgtv.items():
            cur[k] = cur.get(k, 0) + v_ * 0.55
        prev = cur
        bl = max(0.0, 1 - abs(f - 21) / 3.0)
        kv = dict(cur); kv.update(blink(bl)); kv["smile"] = max(kv.get("smile", 0), 0.18)
        setk(**kv)
        shot(os.path.join(OUT, "anim", f"f{f:03d}.png"), target=TG, dist=1.58, azimuth=10, lens=85, res=(400, 476))
print("CAND DONE")
