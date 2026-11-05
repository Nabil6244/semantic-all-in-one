"""Face concept sculptor. Run: blender -b build/host_stage3c.blend --python host/concept_head.py -- A|B|C [--tag t]
Builds a purpose-made cartoon head from blended soft volumes (signed distance fields), so forms are designed, not a stretched human skull.
Saves build/concepts/concept_<X>.blend and four portraits; never saves over the file it opened. Concepts are not rigged yet:
the chosen one gets clean topology, the rig binding and the key transfer after approval."""
import math
import os
import sys

import bmesh
import bpy
import mathutils
import numpy as np
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD, TEX, lin, loft, material, shot
from concept_params import CONCEPTS

ARGS = sys.argv[sys.argv.index("--") + 1:]
NAME = ARGS[0]; C = CONCEPTS[NAME]
TAG = ARGS[ARGS.index("--tag") + 1] if "--tag" in ARGS else "v1"
OUT = os.path.join(BUILD, "concepts", TAG, NAME); os.makedirs(OUT, exist_ok=True)
f32 = np.float32


# ---------- field tools
class Grid:
    def __init__(self, lo, hi, h):
        self.lo, self.h = np.array(lo, float), h
        self.n = np.ceil((np.array(hi) - self.lo) / h).astype(int) + 1
        ax = [(self.lo[i] + np.arange(self.n[i]) * h).astype(f32) for i in range(3)]
        self.X, self.Y, self.Z = ax[0][:, None, None], ax[1][None, :, None], ax[2][None, None, :]

    def sub(self, c, rad):
        a = np.maximum(((np.array(c) - rad - self.lo) / self.h).astype(int), 0)
        b = np.minimum(((np.array(c) + rad - self.lo) / self.h).astype(int) + 1, self.n)
        return (slice(a[0], b[0]), slice(a[1], b[1]), slice(a[2], b[2])), self.X[a[0]:b[0]], self.Y[:, a[1]:b[1]], self.Z[:, :, a[2]:b[2]]


def ell(X, Y, Z, c, r):
    dx, dy, dz = (X - c[0]) / r[0], (Y - c[1]) / r[1], (Z - c[2]) / r[2]
    k0 = np.sqrt(dx * dx + dy * dy + dz * dz)
    k1 = np.sqrt((dx / r[0]) ** 2 + (dy / r[1]) ** 2 + (dz / r[2]) ** 2)
    return (k0 * (k0 - 1) / np.maximum(k1, 1e-6)).astype(f32)


def smin(a, b, k):
    if not C.get("c2"):
        h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
        return b * (1 - h) + a * h - k * h * (1 - h)
    k = k * 1.6                                       # cubic blend: curvature stays continuous, so no faint crease where a blend ends
    h = np.maximum(k - np.abs(a - b), 0) / k
    return np.minimum(a, b) - h * h * h * k / 6


def smax(a, b, k):
    return -smin(-a, -b, k)


def capsule(X, Y, Z, a, b, ra, rb):
    a, b = np.array(a, f32), np.array(b, f32); ba = b - a
    t = np.clip(((X - a[0]) * ba[0] + (Y - a[1]) * ba[1] + (Z - a[2]) * ba[2]) / (ba @ ba + 1e-9), 0, 1)
    return np.sqrt((X - a[0] - t * ba[0]) ** 2 + (Y - a[1] - t * ba[1]) ** 2 + (Z - a[2] - t * ba[2]) ** 2) - (ra + (rb - ra) * t)


def surface_nets(g, f):
    """Numpy surface nets: one vertex per crossing cell, quads between. Gives clean smooth quads without extra libraries."""
    s = f < 0
    cnt = np.zeros(np.array(f.shape) - 1, np.uint8)
    for d in np.ndindex(2, 2, 2):
        cnt += s[d[0]:f.shape[0] - 1 + d[0], d[1]:f.shape[1] - 1 + d[1], d[2]:f.shape[2] - 1 + d[2]]
    cells = np.argwhere((cnt > 0) & (cnt < 8))
    vid = np.full(cnt.shape, -1, np.int32); vid[tuple(cells.T)] = np.arange(len(cells))
    acc = np.zeros((len(cells), 3)); num = np.zeros(len(cells))
    co = [(a, b, c) for a in (0, 1) for b in (0, 1) for c in (0, 1)]
    for p in co:
        for ax in range(3):
            if p[ax]:
                continue
            q = list(p); q[ax] = 1
            fa = f[tuple((cells + p).T)]; fb = f[tuple((cells + q).T)]
            m = (fa < 0) != (fb < 0)
            t = fa[m] / (fa[m] - fb[m])
            pos = np.array(p, float)[None] + t[:, None] * (np.array(q) - p)[None]
            acc[m] += pos; num[m] += 1
    V = (cells + acc / num[:, None]) * g.h + g.lo
    Q = []
    for ax in range(3):
        u, v = (ax + 1) % 3, (ax + 2) % 3
        sl0 = [slice(0, -1)] * 3; sl1 = [slice(0, -1)] * 3; sl1[ax] = slice(1, None)
        e = np.argwhere(s[tuple(sl0)] != s[tuple(sl1)])
        e = e[(e[:, u] > 0) & (e[:, v] > 0)]
        du = np.zeros(3, int); du[u] = 1; dv = np.zeros(3, int); dv[v] = 1
        quad = np.stack([vid[tuple((e - du - dv).T)], vid[tuple((e - dv).T)], vid[tuple(e.T)], vid[tuple((e - du).T)]], 1)
        flip = s[tuple(e.T)]
        quad[flip] = quad[flip][:, ::-1]
        Q.append(quad[(quad >= 0).all(1)])
    return V, np.concatenate(Q)


def relax(V, Q, it=2, lam=0.5):
    ed = np.concatenate([Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]])
    for w in [lam, -lam * 1.03] * it:                # Taubin: smooths voxel steps without shrinking
        acc = np.zeros_like(V); c = np.zeros(len(V))
        np.add.at(acc, ed[:, 0], V[ed[:, 1]]); np.add.at(c, ed[:, 0], 1)
        V = V + w * (acc / np.maximum(c, 1)[:, None] - V)
    return V


def mesh(name, V, Q, mat):
    me = bpy.data.meshes.new(name)
    n = len(Q)
    me.vertices.add(len(V)); me.vertices.foreach_set("co", V.astype(np.float32).ravel())
    me.loops.add(n * 4); me.loops.foreach_set("vertex_index", Q.astype(np.int32).ravel())
    me.polygons.add(n); me.polygons.foreach_set("loop_start", np.arange(0, n * 4, 4, dtype=np.int32))
    me.update(calc_edges=True); me.validate(clean_customdata=False)
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    return o


# ---------- design maths shared by the sculpt and the colouring
HC = np.array(C["head_c"]); EZ, EX, EY, ER = C["eye_z"], C["eye_x"], C["eye_y"], C["eye_r"]
M = C["mouth"]


def mouth_z(x):
    t = x / M["w"]
    return M["z"] + M["curve"] * t * t


def lip_y(x):
    return M["y"] + M["yc"] * x * x


def lip_fields(X, Y, Z):
    t = np.clip(np.abs(X) / M["w"], 0, 1.0)
    env = np.sqrt(np.clip(1 - t * t, 0.0004, 1))
    yf = lip_y(X) + 0.0075
    zm = mouth_z(X)
    bow = 1 + M["bow"] * (np.exp(-((np.abs(X) - 0.0085) / 0.0085) ** 2) - 0.75 * np.exp(-(X / 0.0048) ** 2))
    ru = M["up"] * env ** 0.75 * bow; rl = M["low"] * env ** 0.62
    ry = 0.0115 * env ** 0.5 + 0.0012
    up = (np.sqrt(((Y - yf) / ry) ** 2 + ((Z - zm - ru * 0.82) / ru) ** 2) - 1) * np.minimum(ru, ry)
    lo = (np.sqrt(((Y - yf) / ry) ** 2 + ((Z - zm + rl * 0.82) / rl) ** 2) - 1) * np.minimum(rl, ry)
    past = np.abs(X) - M["w"]                         # the lips end at the corners: no thin sheet across the cheek
    return np.maximum(up, past).astype(f32), np.maximum(lo, past).astype(f32)


def eye_open(dx, dy, dz, sgn):
    """>0 inside the lid opening, in rough metres. dx,dy,dz: unit direction from the eye centre."""
    e = C["lid"]
    u = dx * sgn; v = dz - e["tilt"] * u - e["v0"]
    b = np.where(v > 0, e["up"], e["down"])
    arc = (np.abs(u - e["u0"]) / e["a"]) ** e["pow"] + (v / b) ** 2 - 1
    return np.minimum(-arc * 0.013, (-dy - 0.08) * 0.06).astype(f32)


# ---------- sculpt the head
def sculpt_head():
    g = Grid((-0.17, -0.215, 1.205), (0.17, 0.125, 1.70), C.get("voxel", 0.0012))
    X, Y, Z = g.X, g.Y, g.Z
    f = ell(X, Y, Z, C["cran_c"], C["cran_r"])
    f = smin(f, ell(X, Y, Z, C["face_c"], C["face_r"]), 0.03)
    for s in (1, -1):
        c = C["cheek_c"]; f = smin(f, ell(X, Y, Z, (s * c[0], c[1], c[2]), C["cheek_r"]), C["cheek_k"])
        if C.get("bone"):
            b = C["bone"]; f = smin(f, ell(X, Y, Z, (s * b[0], b[1], b[2]), b[3]), 0.016)
    f = smin(f, ell(X, Y, Z, C["chin_c"], C["chin_r"]), C["chin_k"])
    f = smin(f, capsule(X, Y, Z, C["neck_a"], C["neck_b"], C["neck_r"], C["neck_r"] * 1.05), 0.022)
    f = smin(f, ell(X, Y, Z, (0, -0.012, 1.262 + C["drop"]), (0.125, 0.072, 0.05)), 0.03)   # shoulders under the collar: no gap in the neckline
    if C.get("muzzle"):                               # soft forward mass around the mouth: a fuller, friendlier profile
        f = smin(f, ell(X, Y, Z, *C["muzzle"]), 0.026)
    n = C["nose"]                                     # designed nose: bridge, round tip, soft wings
    tip = np.array(n["tip"])
    sl, x, y, z = g.sub(tip, 0.075)
    br = capsule(x, y, z, n["root"], tip + np.array([0, 0.004, 0.004]), n["bridge"], n["bridge"] * 1.1)
    f[sl] = smin(f[sl], br, 0.012)
    f[sl] = smin(f[sl], ell(x, y, z, tip, n["tip_r"]), 0.0075)
    for s in (1, -1):
        wc = tip + np.array([s * n["wing"], 0.0075, -0.0055])
        f[sl] = smin(f[sl], ell(x, y, z, wc, (n["wing_r"], n["wing_r"], n["wing_r"] * 0.8)), 0.0055)
        nc = tip + np.array([s * n["wing"] * 0.62, -0.0015, -n["tip_r"][2] * 0.98])    # nostril hint
        f[sl] = smax(f[sl], -ell(x, y, z, nc, (0.0034, 0.0042, 0.0022)), 0.0028)
    for s in (1, -1):                                 # ear
        ec = np.array(C["ear_c"]) * [s, 1, 1]
        sl, x, y, z = g.sub(ec, 0.07)
        er = ell(x, y, z, ec, C["ear_r"])
        er = smax(er, -ell(x, y, z, ec + [s * 0.008, -0.002, 0.002], [C["ear_r"][0] * 0.8, C["ear_r"][1] * 0.62, C["ear_r"][2] * 0.66]), 0.003)
        f[sl] = smin(f[sl], er, 0.0055)
    # mouth: lips are their own forms, a real parting line, a real cavity behind
    sl, x, y, z = g.sub((0, M["y"] + 0.02, M["z"]), max(M["w"] * 1.35, 0.068))
    up, lo = lip_fields(x, y, z)
    lips = np.minimum(up, lo)
    ph = ell(x, y, z, (0, lip_y(0) + 0.0015, M["z"] + M["up"] * 2.2), (0.0045, 0.006, 0.0085))
    f[sl] = smax(f[sl], -ph, 0.005) if M.get("philtrum", True) else f[sl]
    f[sl] = smin(f[sl], lips, 0.0028)
    cav = ell(x, y, z, (0, M["y"] + 0.05, M["z"] - 0.002), (M["w"] * 1.08, 0.042, 0.03))
    f[sl] = smax(f[sl], -cav, 0.0025)
    tt = np.abs(x) / (M["w"] * C.get("slit_w", 1.015))
    slit = np.maximum(np.maximum(np.abs(z - mouth_z(x)) - C.get("slit", 0.0009), tt - 1), np.maximum(lip_y(x) - 0.01 - y, y - (lip_y(x) + 0.04)))
    f[sl] = smax(f[sl], -slit.astype(f32), 0.0009)
    for s in (1, -1):                                 # small soft dent at each mouth corner
        cc = np.array((s * M["w"] * 1.02, float(lip_y(M["w"])) + 0.006, float(mouth_z(M["w"]))))
        f[sl] = smax(f[sl], -ell(x, y, z, cc, (0.0042, 0.0045, 0.0042)), 0.005)
    # eyes: designed sockets with real lids that wrap the ball
    for s in (1, -1):
        c = np.array((s * EX, EY, EZ))
        sl, x, y, z = g.sub(c, ER * (2.6 if C.get("c2") else 1.9))
        dx, dy, dz = x - c[0], y - c[1], z - c[2]
        d = np.sqrt(dx * dx + dy * dy + dz * dz); inv = 1 / np.maximum(d, 1e-5)
        op = eye_open(dx * inv, dy * inv, dz * inv, s)
        th = C["lid"]["thick"]
        rim = ER + 0.0012 + 2 * th
        if C.get("c2"):                               # one smooth falloff: no visible edge where the dish ends
            q_ = np.clip((op + 0.02) / 0.02, 0, 1); q_ = q_ * q_ * (3 - 2 * q_)
            dish = ((rim + 0.0022 - d) - 0.03 * (1 - q_)).astype(f32)
            f[sl] = smax(f[sl], dish, 0.009)
        else:
            dish = np.minimum(rim + 0.0022 - d, op + 0.0085).astype(f32)   # soft dish: the lid, not the cheek, is the outer surface around the eye
            f[sl] = smax(f[sl], dish, 0.0075)
        f[sl] = smax(f[sl], -(d - (ER + 0.0012)), 0.0016)
        shell = (np.abs(d - (ER + 0.0012 + th)) - th).astype(f32)
        shell = np.maximum(shell, (dy * inv - 0.42) * 0.05)
        shell = smax(shell, op, 0.0016)
        if C.get("c2"):                               # the lid form sinks away from the opening: no ridge where the ball meets the forehead
            q2 = np.clip((op + 0.052) / 0.04, 0, 1); q2 = q2 * q2 * (3 - 2 * q2)
            shell = (shell + 0.03 * (1 - q2)).astype(f32)
        f[sl] = smin(f[sl], shell, C["lid"]["blend"])
        f[sl] = smax(f[sl], np.minimum(op, (rim + 0.0035 - d)).astype(f32), 0.001)
        if C["lid"].get("crease"):                     # gentle fold above the upper lid
            r_ = ER + 2 * th + 0.0008
            band = ((dz * inv - C["lid"]["up"] - C["lid"]["crease"]) ** 2 / 0.012 ** 2 + (dx * inv * s) ** 2 / 0.62 ** 2)
            near = 1.0
            if C.get("c2"):                           # the fold stays beside the eye: it must not run on across the forehead
                near = np.clip((op + 0.012) / 0.012, 0, 1); near = near * near * (3 - 2 * near)
            f[sl] = f[sl] + C["lid"].get("fold", 0.0009) * np.exp(-band).astype(f32) * (dy < 0) * near
    print("REPORT head grid", g.n, "nets...")
    V, Q = surface_nets(g, f)
    del f
    V = relax(V, Q, C.get("relax", 3))
    print("REPORT head", len(V), "verts", len(Q), "quads")
    return V, Q


def skin_colour(V):
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    col = np.tile(np.array(lin(C["skin"])[:3]), (len(V), 1))
    def mix(w, h):
        nonlocal col
        col = col * (1 - w[:, None]) + np.array(lin(h)[:3]) * w[:, None]
    ck = C["cheek_c"]
    bl = np.exp(-(((np.abs(x) - ck[0] * 0.96) / 0.034) ** 2 + ((z - ck[2] - 0.004) / 0.027) ** 2)) * (y < -0.03)
    mix(bl * C["blush"], C["blush_c"])
    tip = np.array(C["nose"]["tip"])
    mix(np.exp(-(np.linalg.norm(V - tip, axis=1) / 0.016) ** 2) * 0.28, C["blush_c"])
    mix(np.clip((np.abs(x) - 0.112) / 0.02, 0, 1) * 0.3, C["blush_c"])
    up, lo = lip_fields(x, y, z)
    lm = np.clip(1.15 - np.minimum(up, lo) / 0.0016, 0, 1) * (np.abs(x) < M["w"] * 1.02) * (y < M["y"] + 0.03)
    mix(lm * 0.92, C["lip_c"])
    lid = np.zeros(len(V))
    for s in (1, -1):
        d = np.linalg.norm(V - np.array((s * EX, EY, EZ)), axis=1)
        lid = np.maximum(lid, np.exp(-((d - ER - 0.003) / 0.008) ** 2) * (z > EZ))
    mix(lid * 0.18, C["lid_c"])
    if C.get("c2"):                                   # lash line lives on the lid edge itself: it cannot float or split
        L_ = C["lid"]
        for s in (1, -1):
            dv = V - np.array((s * EX, EY, EZ)); d = np.linalg.norm(dv, axis=1); u_ = dv / np.maximum(d, 1e-6)[:, None]
            near_ = d < ER + 0.0085
            op_ = eye_open(u_[:, 0], u_[:, 1], u_[:, 2], s)
            uu_ = u_[:, 0] * s
            t_ = np.clip((uu_ + L_["a"]) / (2 * L_["a"]), 0, 1)
            th_ = 0.0005 + C["lash"]["paint"] * t_ ** 1.8
            upper = (u_[:, 2] - L_["tilt"] * uu_ - L_["v0"]) > 0.03
            inner = np.clip((t_ - 0.1) / 0.2, 0, 1)
            w_ = np.clip((op_ + th_) / 0.0007, 0, 1) * near_ * upper * (u_[:, 1] < 0) * inner
            mix(w_, "#1a0e08")
            lower = (u_[:, 2] - L_["tilt"] * uu_ - L_["v0"]) < -0.03
            lw = np.clip((op_ + 0.0011) / 0.0009, 0, 1) * (d < ER + 0.0085) * lower * (u_[:, 1] < 0)
            mix(lw * 0.5, "#b56f58")                  # soft warm lower lid line
            fold_ = np.exp(-(((u_[:, 2] - L_["tilt"] * uu_ - L_["v0"]) - L_["up"] - L_["crease"]) / 0.055) ** 2) * np.exp(-(uu_ / 0.75) ** 2) * (u_[:, 1] < 0) * (d < ER + 0.016)
            mix(fold_ * 0.34, "#d99a78")              # colour in the upper lid fold gives the eye depth
    return col


def smile_field(V, amount=1.0):
    """Same mesh, new shape: this is the prototype of the real smile key."""
    x, y, z = V[:, 0].copy(), V[:, 1].copy(), V[:, 2].copy()
    Vn = V.copy(); w = M["w"]; S = C["smile"]
    t = np.abs(x) / w; zc = mouth_z(x)
    front = np.clip((M["y"] + 0.085 - y) / 0.06, 0, 1) ** 2   # soft: a hard edge here leaves a scar on the cheek
    wm = np.exp(-((x / (w * 1.4)) ** 2 + ((z - M["z"]) / 0.036) ** 2)) * front
    Vn[:, 2] += amount * S["lift"] * np.clip(t, 0, 1.25) ** 2 * wm
    Vn[:, 0] += amount * S["wide"] * x * wm
    Vn[:, 1] += amount * S["back"] * np.clip(t, 0, 1.2) ** 2 * wm
    side = np.tanh((z - zc) / 0.0012)
    env = np.sqrt(np.clip(1 - np.clip(t, 0, 1) ** 2, 0, 1))
    near = np.exp(-((z - zc) / 0.03) ** 2) * front * (t < 1.15)
    Vn[:, 2] += amount * near * env * np.where(side > 0, S["open_up"], -S["open_down"]) * np.abs(side)
    Vn[:, 2] -= amount * S["jaw"] * np.exp(-((x / 0.07) ** 2)) * np.clip((M["z"] - z) / 0.05, 0, 1) * front
    for s in (1, -1):
        ck = C["cheek_c"]
        gk = np.exp(-(((x - s * ck[0]) / 0.042) ** 2 + ((z - ck[2]) / 0.036) ** 2)) * np.clip((-0.01 - y) / 0.05, 0, 1)
        Vn[:, 2] += amount * S["cheek"] * gk; Vn[:, 1] -= amount * S["cheek"] * 0.55 * gk
        lz = np.exp(-(((x - s * EX) / 0.03) ** 2 + ((z - (EZ - ER * 0.75)) / 0.012) ** 2)) * np.clip((EY + 0.03 - y) / 0.04, 0, 1)
        Vn[:, 2] += amount * S["lid"] * lz
    return Vn


# ---------- hair: chunky designed locks that form their own hairline
def dirv(az, el):
    a, e = math.radians(az), math.radians(el)
    return np.array((math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)))


def on_head(d, off):
    r = np.array(C["hair_r"]) + off
    return np.array(C["hair_c"]) + d * r


def lock_path(way, n=12):
    pts = []
    for (a0, e0, o0), (a1, e1, o1) in zip(way[:-1], way[1:]):
        d0, d1 = dirv(a0, e0), dirv(a1, e1)
        ang = math.acos(np.clip(d0 @ d1, -1, 1)) or 1e-4
        for i in range(n):
            t = i / n
            d = (math.sin((1 - t) * ang) * d0 + math.sin(t * ang) * d1) / math.sin(ang)
            pts.append(on_head(d, o0 + (o1 - o0) * t))
    pts.append(on_head(dirv(*way[-1][:2]), way[-1][2]))
    p = np.array(pts)
    for _ in range(5):
        p[1:-1] = (p[:-2] + 2 * p[1:-1] + p[2:]) / 4
    return p


def sculpt_hair():
    H = C["hair"]; g = Grid((-0.215, -0.235, 1.09), (0.215, 0.44, 1.78), C.get("hvoxel", 0.0017)); X, Y, Z = g.X, g.Y, g.Z
    az = np.degrees(np.arctan2(np.abs(X), -(Y - C["hair_c"][1]) + 1e-6))
    rr = np.sqrt(X ** 2 + (Y - C["hair_c"][1]) ** 2 + (Z - C["hair_c"][2]) ** 2) + 1e-6
    el = np.degrees(np.arcsin(np.clip((Z - C["hair_c"][2]) / rr, -1, 1)))
    line = np.interp(az, H["line_az"], H["line_el"]).astype(f32)
    cap = ell(X, Y, Z, C["hair_c"], np.array(C["hair_r"]) + H["cap_off"])
    f = smax(cap, (line - el) * 0.0016, 0.006)
    del az, rr, el, line
    samples = []                                      # (point, lock id, s, tangent) for strand direction
    lid = 0

    def add(path, r0, r1, k):
        nonlocal f, lid
        n = len(path)
        lo = path.min(0) - 0.05; hi = path.max(0) + 0.05
        c = (lo + hi) / 2
        sl, x, y, z = g.sub(c, (hi - lo) / 2)
        d = None
        prof = (lambda t: (r0 + (r1 - r0) * t) * (0.16 + 0.84 * min(1, t / 0.2) ** 0.8)) if not callable(r0) else r0   # a lock grows out of the hairline
        for i in range(n - 1):
            q = capsule(x, y, z, path[i], path[i + 1], prof(i / (n - 1)), prof((i + 1) / (n - 1)))
            d = q if d is None else np.minimum(d, q)
        f[sl] = smin(f[sl], d, k)
        for i in range(n):
            samples.append((path[i], lid, i / (n - 1), path[min(i + 1, n - 1)] - path[max(i - 1, 0)]))
        lid += 1

    A = H["anchor"]                                   # (az, el) of the ponytail base
    for way, r0, r1 in H["locks"]:
        add(lock_path(way), r0, r1, H["lock_k"])
    base = on_head(dirv(*A), H["cap_off"] - 0.002)
    T = H["tail"]
    pts = base + np.array(T["path"], float)
    t = np.linspace(0, 1, len(pts)); s = np.linspace(0, 1, 44)
    tail = np.stack([np.interp(s, t, pts[:, i]) for i in range(3)], 1)
    for _ in range(14):
        tail[1:-1] = (tail[:-2] + 2 * tail[1:-1] + tail[2:]) / 4
    tan = np.gradient(tail, axis=0); tan /= np.linalg.norm(tan, axis=1, keepdims=True)
    e1 = np.cross(tan, [1.0, 0, 0]); e1 /= np.linalg.norm(e1, axis=1, keepdims=True); e2 = np.cross(tan, e1)
    prof = np.interp(s, T["prof_s"], T["prof_r"])
    N = T["strands"]
    for k in range(N):                               # the tail is several twisting chunky locks, not a tube
        ph = 2 * math.pi * k / N + 0.5
        tw = ph + s * T["twist"]
        spread = prof * 0.66
        off = np.cos(tw)[:, None] * e1 * spread[:, None] + np.sin(tw)[:, None] * e2 * spread[:, None]
        L = tail + off
        L[-5:] = L[-5:] * 0.65 + tail[-5:] * 0.35
        rad = prof * T["strand_r"]
        add(L[::2], lambda u, rad=rad: float(np.interp(u, np.linspace(0, 1, len(rad)), rad)), None, T["k"])
    print("REPORT hair grid", g.n, "locks", lid)
    V, Q = surface_nets(g, f); del f
    V = relax(V, Q, 3)
    # strand direction: nearest lock sample gives each vertex an along/around coordinate
    kd = mathutils.kdtree.KDTree(len(samples))
    for i, sm in enumerate(samples):
        kd.insert(sm[0], i)
    kd.balance()
    uv = np.zeros((len(V), 2), np.float32)
    for i, p in enumerate(V):
        _, j, _ = kd.find(p)
        pt, l, sv, tg = samples[j]
        tg = tg / (np.linalg.norm(tg) + 1e-9)
        a = np.cross(tg, (0.3, 0.2, 0.9)); a /= np.linalg.norm(a) + 1e-9; b = np.cross(tg, a)
        d = p - pt
        uv[i] = (math.atan2(d @ b, d @ a) / 6.2832 * 1.5 + l * 0.37, sv * 0.3 + l * 0.11)
    return V, Q, uv, tail


# ---------- build
for n in ("host_hair", "host_ponytail", "host_hairtie", "host_hairline", "host_headband", "host_brows", "host_lashes", "host_eyes", "host_teeth", "host_tongue", "host_mouth"):
    if n in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[n])
bpy.data.objects["host_body"].hide_render = True
for o in ("host_shoes",):
    bpy.data.objects[o].hide_render = True

Vh, Qh = sculpt_head()
skinM = material("concept_skin", rough=C["skin_rough"])
nt = skinM.node_tree; bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
at = nt.nodes.new("ShaderNodeVertexColor"); at.layer_name = "skin"
nt.links.new(at.outputs[0], bs.inputs["Base Color"])
bs.inputs["Subsurface Weight"].default_value = 0.35; bs.inputs["Subsurface Radius"].default_value = (0.9, 0.4, 0.25); bs.inputs["Subsurface Scale"].default_value = 0.012
head = mesh("concept_head", Vh, Qh, skinM)
ca = head.data.color_attributes.new("skin", "FLOAT_COLOR", "POINT")
ca.data.foreach_set("color", np.c_[skin_colour(Vh), np.ones(len(Vh))].astype(np.float32).ravel())
head.shape_key_add(name="Basis", from_mix=False)
head.shape_key_add(name="smile", from_mix=False).data.foreach_set("co", smile_field(Vh).astype(np.float32).ravel())
head.data.shape_keys.key_blocks["smile"].value = 0

# eyeballs
eyeM = material("concept_eye_" + NAME, os.path.join(TEX, C.get("eye_tex", "eye.png")), rough=0.18)
bm = bmesh.new(); ul = bm.loops.layers.uv.new("UVMap")
for s in (1, -1):
    c = (s * EX, EY, EZ)
    r = bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=32, radius=ER + C.get("ball_off", 0.0008))
    bmesh.ops.rotate(bm, verts=r["verts"], cent=(0, 0, 0), matrix=mathutils.Matrix.Rotation(math.pi / 2, 3, "X"))
    bmesh.ops.translate(bm, verts=r["verts"], vec=c)
    k = C["iris_k"]
    for v in r["verts"]:
        for fc in v.link_faces:
            fc.smooth = True
            for l in fc.loops:
                if l.vert is v:
                    l[ul].uv = (0.5 + (v.co.x - c[0] - s * C["gaze_in"] * -ER) / (2 * ER) * k, 0.5 + (v.co.z - c[2] - 0.0) / (2 * ER) * k)
eo = bpy.data.objects.new("concept_eyes", bpy.data.meshes.new("concept_eyes")); bm.to_mesh(eo.data); bm.free()
bpy.context.scene.collection.objects.link(eo); eo.data.materials.append(eyeM)

# teeth
teethM = material("concept_teeth", colour="#fdf9f1", rough=0.22)
tb_ = next(n for n in teethM.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
tb_.inputs["Emission Color"].default_value = (1, 0.97, 0.92, 1); tb_.inputs["Emission Strength"].default_value = 0.28


def arch(zroot, zedge_fn, yf, half, depth, n_teeth):
    rows = []
    for i in range(141):
        t = i / 70 - 1
        x = half * math.sin(t * 1.25) / math.sin(1.25)
        y = yf + depth * (1 - math.cos(t * 1.25)) / (1 - math.cos(1.25))
        fr = ((t + 1) / 2 * n_teeth) % 1; cusp = abs(2 * fr - 1) ** 6
        ze = zedge_fn(x) + (zroot - zedge_fn(x)) * 0.13 * cusp
        yg = y + 0.0008 * cusp
        rows.append(np.array([[x, yg, zroot], [x, yg, ze], [x, yg + 0.006, ze], [x, yg + 0.006, zroot]]))
    return rows


yfront = float(lip_y(0)) + 0.0175
up_edge = lambda x: float(mouth_z(x)) - C["smile"]["teeth_show"]
tb = loft(arch(M["z"] + C["smile"].get("teeth_root", 0.0078), up_edge, yfront, M["w"] * 0.9, 0.03, 10))
to = mathutils.Vector((0, 0, 0))
bmesh.ops.recalc_face_normals(tb, faces=tb.faces)
me_t = bpy.data.meshes.new("concept_teeth"); tb.to_mesh(me_t); tb.free()
teeth = bpy.data.objects.new("concept_teeth", me_t); bpy.context.scene.collection.objects.link(teeth); me_t.materials.append(teethM)
me_t.polygons.foreach_set("use_smooth", np.ones(len(me_t.polygons), bool))
teeth.shape_key_add(name="Basis", from_mix=False)
_tv = np.zeros(len(me_t.vertices) * 3); me_t.vertices.foreach_get("co", _tv); _tv = _tv.reshape(-1, 3)
_tt = np.abs(_tv[:, 0]) / M["w"]
_ts = _tv.copy(); _ts[:, 2] += C["smile"]["lift"] * C["smile"].get("teeth_follow", 0.0) * np.clip(_tt, 0, 1.2) ** 2; _ts[:, 0] *= 1 + C["smile"]["wide"] * 0.75 * C["smile"].get("teeth_wide", 0.0)
teeth.shape_key_add(name="smile", from_mix=False).data.foreach_set("co", _ts.astype(np.float32).ravel())
mouthM = material("concept_mouth", colour="#5e2024", rough=0.6)
ms = bmesh.new(); bmesh.ops.create_uvsphere(ms, u_segments=24, v_segments=16, radius=1.0)
for v in ms.verts:
    v.co = mathutils.Vector((v.co.x * M["w"] * 1.05, M["y"] + 0.066 + v.co.y * 0.04, M["z"] - 0.002 + v.co.z * 0.028))
bmesh.ops.reverse_faces(ms, faces=ms.faces)
me_m = bpy.data.meshes.new("concept_mouth"); ms.to_mesh(me_m); ms.free()
mo = bpy.data.objects.new("concept_mouth", me_m); bpy.context.scene.collection.objects.link(mo); me_m.materials.append(mouthM)

# hair
Vr, Qr, uv, tail = sculpt_hair()
hairM = material("concept_hair_" + NAME, os.path.join(TEX, C.get("hair_tex", "hair.png")), rough=C.get("hair_rough", 0.36), normal=os.path.join(TEX, C.get("hair_n", "hair_n.png")), nstrength=0.45)
hair = mesh("concept_hair", Vr, Qr, hairM)
ul = hair.data.uv_layers.new(name="UVMap")
idx = np.zeros(len(hair.data.loops), int); hair.data.loops.foreach_get("vertex_index", idx)
ul.data.foreach_set("uv", uv[idx].ravel())
print("REPORT hair", len(Vr), "verts")

# brows
head_bvh = BVHTree.FromPolygons([tuple(p) for p in Vh], [tuple(int(i) for i in q) for q in Qh])
B = C["brow"]
browM = bpy.data.materials.get("brow_soft")
bm = bmesh.new(); ub = bm.loops.layers.uv.new("UVMap"); buv = {}


def on_skin(x, z, lift):
    h = head_bvh.ray_cast(mathutils.Vector((x, -0.6, z)), mathutils.Vector((0, 1, 0)))
    return (np.array(h[0]) - np.array((0, lift, 0))) if h[0] else None


for s in (1, -1):
    prev = None
    for i in range(26):
        t = i / 25
        x = EX + B["x0"] + (B["x1"] - B["x0"]) * t
        zc = EZ + ER + B["z"] + B["arch"] * math.sin(math.pi * min(1, t ** B["peak"])) - B["drop"] * t * t
        th = B["th"] * min(1, (t / 0.16)) ** 0.7 * (1 - t ** 2.4) + 0.0008
        row = [on_skin(s * x, zc + d, 0.0013) for d in (th, 0.33 * th, -0.33 * th, -th)]
        if any(q is None for q in row):
            continue
        row = [bm.verts.new(tuple(q)) for q in row]
        for q, vv in zip(row, (0, 0.33, 0.67, 1)):
            buv[q] = (t * 1.3 + (0 if s > 0 else 0.37), vv)
        if prev:
            for a in range(3):
                bm.faces.new((prev[a], row[a], row[a + 1], prev[a + 1]) if s > 0 else (prev[a + 1], row[a + 1], row[a], prev[a]))
        prev = row
for fc in bm.faces:
    for l in fc.loops:
        l[ub].uv = buv[l.vert]
me_b = bpy.data.meshes.new("concept_brows"); bm.to_mesh(me_b); bm.free()
bo = bpy.data.objects.new("concept_brows", me_b); bpy.context.scene.collection.objects.link(bo); me_b.materials.append(browM)
me_b.polygons.foreach_set("use_smooth", np.ones(len(me_b.polygons), bool))

# lash line along the designed lid edge
L = C["lid"]; lashM = material("concept_lash", colour="#170c07", rough=0.45)
bm = bmesh.new()
for s in (1, -1):
    c = np.array((s * EX, EY, EZ)); prev = None; N = 44
    for i in range(N):
        t = i / (N - 1)
        uu = L["u0"] - L["a"] * 0.985 + 2 * L["a"] * 0.985 * t
        base = (1 - (abs(uu - L["u0"]) / L["a"]) ** L["pow"])
        vv = L["up"] * math.sqrt(max(base, 0)) + L["tilt"] * uu + L["v0"]
        wth = C["lash"]["w0"] + C["lash"]["w1"] * t ** 1.5
        row = []
        for k_, lift in ((0, -0.002), (0.55, 0.0), (1, 0.0)):
            u2 = uu + C["lash"]["wing"] * t ** 3 * k_
            v2 = vv + wth * k_
            r2 = ER + 2 * L["thick"] + 0.0016 + 0.0014 * k_
            dy = -math.sqrt(max(1 - u2 * u2 - v2 * v2, 0.02))
            d = np.array((s * u2, dy, v2)); d /= np.linalg.norm(d)
            p_ = c + d * r2
            if C.get("c2") and k_ == 0:               # root sits on the eyeball, so the line covers the lid edge with no pale gap
                d0 = np.array((s * uu, -math.sqrt(max(1 - uu * uu - (vv - 0.03) ** 2, 0.02)), vv - 0.03)); d0 /= np.linalg.norm(d0)
                p_ = c + d0 * (ER + 0.0014)
            elif C.get("c2"):                         # the rest lies on the real lid surface
                hh = head_bvh.ray_cast(mathutils.Vector(c + d * 0.2), mathutils.Vector(-d))
                if hh[0] is not None and ER + 0.001 < (hh[0] - mathutils.Vector(c)).length < ER + 0.0115:
                    p_ = np.array(hh[0]) + d * (0.0007 + 0.0009 * k_)
            row.append(bm.verts.new(tuple(p_)))
        if prev:
            for a in range(2):
                bm.faces.new((prev[a], row[a], row[a + 1], prev[a + 1]) if s > 0 else (prev[a + 1], row[a + 1], row[a], prev[a]))
        prev = row
me_l = bpy.data.meshes.new("concept_lash"); bm.to_mesh(me_l); bm.free()
lo_ = bpy.data.objects.new("concept_lash", me_l); bpy.context.scene.collection.objects.link(lo_); me_l.materials.append(lashM)
me_l.polygons.foreach_set("use_smooth", np.ones(len(me_l.polygons), bool))
if C.get("c2"):
    lo_.hide_render = True

# headband and tie
mintM = bpy.data.materials.get("mint")
if C.get("hair_shadow"):                              # soft shadow where hair meets skin: the hairline melts in instead of ending on a line
    hb_ = BVHTree.FromPolygons([tuple(p) for p in Vr], [tuple(int(i) for i in q) for q in Qr])
    cols = np.zeros(len(Vh) * 4, np.float32); ca = head.data.color_attributes["skin"]; ca.data.foreach_get("color", cols); cols = cols.reshape(-1, 4)
    shade = np.array(lin("#a9704c")[:3])
    for i in np.where(Vh[:, 2] > EZ - 0.05)[0]:
        loc, _, _, dist = hb_.find_nearest(mathutils.Vector(Vh[i]))
        if loc is not None and dist < 0.02:
            w_ = C["hair_shadow"] * math.exp(-(dist / 0.0065) ** 2)
            cols[i, :3] = cols[i, :3] * (1 - w_) + shade * w_
    ca.data.foreach_set("color", cols.ravel())
hb = C["hair"]["band"]
hair_bvh = BVHTree.FromPolygons([tuple(p) for p in Vr], [tuple(int(i) for i in q) for q in Qr])
cen = np.array(C["hair_c"], float)
df, dk = dirv(*hb["front"]), dirv(*hb["back"])


def hit(d):
    h = hair_bvh.ray_cast(mathutils.Vector(cen + d * 0.6), mathutils.Vector(-d))
    return np.array(h[0]) if h[0] else cen + d * 0.13


pf, pk = hit(df), hit(dk)
mid = (pf + pk) / 2; e2 = (pf - pk) / np.linalg.norm(pf - pk); e1 = np.array([1.0, 0, 0]); nrm = np.cross(e1, e2)
NN = 120; ring = np.zeros(NN)
Rr = np.array(C["hair_r"]) + C["hair"]["cap_off"] + C["hair"].get("band_lift", 0.0125)   # analytic limit: the band follows the head, ignoring the ponytail
for i in range(NN):
    a = i / NN * 2 * math.pi; d = math.cos(a) * e1 + math.sin(a) * e2
    o_ = (mid - cen) / Rr; v_ = d / Rr
    A_, B_, C_ = v_ @ v_, 2 * o_ @ v_, o_ @ o_ - 1
    ring[i] = (-B_ + math.sqrt(max(B_ * B_ - 4 * A_ * C_, 0))) / (2 * A_)
if C["hair"].get("band_seat"):                        # sit on the real hair surface, with the ellipsoid as the ceiling
    real = np.zeros(NN)
    for i in range(NN):
        a = i / NN * 2 * math.pi; d = math.cos(a) * e1 + math.sin(a) * e2
        hh = hair_bvh.ray_cast(mathutils.Vector(mid + d * 0.45), mathutils.Vector(-d))
        real[i] = np.linalg.norm(np.array(hh[0]) - mid) if hh[0] else ring[i]
    real = np.minimum(real, ring)
    env = np.max([np.roll(real, k) for k in range(-3, 4)], axis=0)
    for _ in range(24):
        env = 0.5 * env + 0.25 * (np.roll(env, 1) + np.roll(env, -1))
    ring = env + 0.0005
Wd, Th = hb["w"], 0.0075
if C["hair"].get("band_seat"):                        # every lane of the band finds the hair: it hugs the curve across its width
    lanes = [-0.5, -0.25, 0.0, 0.25, 0.5]; prof = [0.42, 0.88, 1.0, 0.88, 0.42]; R_l = []
    for lw in lanes:
        off = nrm * (lw * Wd); r_ = np.zeros(NN)
        for i in range(NN):
            a = i / NN * 2 * math.pi; d = math.cos(a) * e1 + math.sin(a) * e2
            o_ = (mid + off - cen) / Rr; v_ = d / Rr
            A_, B_, C_ = v_ @ v_, 2 * o_ @ v_, o_ @ o_ - 1
            top = (-B_ + math.sqrt(max(B_ * B_ - 4 * A_ * C_, 0))) / (2 * A_)
            hh = hair_bvh.ray_cast(mathutils.Vector(mid + off + d * 0.45), mathutils.Vector(-d))
            r_[i] = min(np.linalg.norm(np.array(hh[0]) - (mid + off)), top) if hh[0] else top
        e_ = np.max([np.roll(r_, k) for k in range(-1, 2)], axis=0)
        for _ in range(12):
            e_ = 0.5 * e_ + 0.25 * (np.roll(e_, 1) + np.roll(e_, -1))
        R_l.append(e_)
    R_l = np.array(R_l)
    for _ in range(2):                                # lanes also relax across the width
        R_l[1:-1] = 0.5 * R_l[1:-1] + 0.25 * (R_l[:-2] + R_l[2:])
    rows = []
    for i in range(NN + 1):
        k_ = i % NN; a = k_ / NN * 2 * math.pi; d = math.cos(a) * e1 + math.sin(a) * e2
        pts = [mid + nrm * (lanes[0] * Wd) + d * (R_l[0, k_] - 0.002)]
        pts += [mid + nrm * (lw * Wd) + d * (R_l[j, k_] + 0.0004 + Th * prof[j]) for j, lw in enumerate(lanes)]
        pts += [mid + nrm * (lanes[-1] * Wd) + d * (R_l[-1, k_] - 0.002)]
        rows.append(np.array(pts))
else:
    sect = [(-Wd / 2, 0.0), (-Wd / 2, Th * 0.72), (-Wd / 3, Th), (0, Th * 1.08), (Wd / 3, Th), (Wd / 2, Th * 0.72), (Wd / 2, 0.0), (0, -0.001)]
    rows = []
    for i in range(NN + 1):
        a = (i % NN) / NN * 2 * math.pi; d = math.cos(a) * e1 + math.sin(a) * e2
        rows.append(np.array([mid + d * (ring[i % NN] + 0.0008 + o) + nrm * w_ for w_, o in sect]))
bb = loft(rows); bmesh.ops.recalc_face_normals(bb, faces=bb.faces)
me_h = bpy.data.meshes.new("concept_band"); bb.to_mesh(me_h); bb.free()
band = bpy.data.objects.new("concept_band", me_h); bpy.context.scene.collection.objects.link(band); me_h.materials.append(mintM)
me_h.polygons.foreach_set("use_smooth", np.ones(len(me_h.polygons), bool))
th_ = np.arange(40) / 40 * 2 * np.pi; tp = tail[3]; tt = tail[5] - tail[1]; tt /= np.linalg.norm(tt)
a = np.cross(tt, [1, 0, 0]); a /= np.linalg.norm(a); b = np.cross(tt, a); tr = []
Rt = float(np.interp(0.07, C["hair"]["tail"]["prof_s"], C["hair"]["tail"]["prof_r"])) * 1.15
for k in range(12):
    ph = k / 12 * 2 * np.pi; R = Rt + 0.0075 * math.cos(ph); bump = 1 + 0.07 * np.sin(th_ * 9)
    tr.append(tp + (np.cos(th_) * R * bump)[:, None] * a + (np.sin(th_) * R * bump)[:, None] * b + tt * (0.0095 * math.sin(ph)))
tie = loft(tr + [tr[0]]); bmesh.ops.recalc_face_normals(tie, faces=tie.faces)
me_ti = bpy.data.meshes.new("concept_tie"); tie.to_mesh(me_ti); tie.free()
to_ = bpy.data.objects.new("concept_tie", me_ti); bpy.context.scene.collection.objects.link(to_); me_ti.materials.append(mintM)
me_ti.polygons.foreach_set("use_smooth", np.ones(len(me_ti.polygons), bool))

for o in bpy.data.objects:
    if o.name.startswith("concept_"):
        o.location.z -= C["drop"]                     # sits on the shoulders: short cute neck
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "concepts", f"concept_{NAME}.blend"), copy=True)
print("REPORT saved concept", NAME)

# ---------- identical portrait setup for every concept
s = bpy.context.scene
s.render.engine = "BLENDER_EEVEE"; s.render.film_transparent = True
s.view_settings.view_transform = "Standard"; s.view_settings.look = "None"; s.view_settings.exposure = 0
for k, v in (("use_raytracing", True), ("taa_render_samples", 48)):
    if hasattr(s.eevee, k):
        setattr(s.eevee, k, v)
w = bpy.data.worlds.get("portrait") or bpy.data.worlds.new("portrait"); s.world = w; w.use_nodes = True
b0 = w.node_tree.nodes["Background"]; b0.inputs[0].default_value = lin("#e9e4de"); b0.inputs[1].default_value = 0.44
T = mathutils.Vector((0, -0.05, 1.475))
for n, en, off, size, col in (("p_key", 24, (-0.85, -1.15, 0.65), 1.4, (1, .95, .89)), ("p_fill", 8, (1.1, -1.1, 0.05), 1.8, (.94, .96, 1)),
                              ("p_hair", 16, (0.65, 0.95, 0.75), 0.8, (1, .97, .93)), ("p_bounce", 3, (0, -0.8, -0.7), 1.2, (1, .86, .76))):
    Lg = bpy.data.lights.new(n, "AREA"); Lg.energy = en; Lg.size = size; Lg.color = col
    o = bpy.data.objects.new(n, Lg); s.collection.objects.link(o); o.location = T + mathutils.Vector(off)
    o.rotation_euler = (T - o.location).to_track_quat("-Z", "Y").to_euler()
SH = dict(target=tuple(T), dist=1.58, lens=85, res=(640, 760))
class _Both:                                          # head and teeth smile together
    def __setattr__(self, n, v):
        head.data.shape_keys.key_blocks["smile"].value = v
        teeth.data.shape_keys.key_blocks["smile"].value = v


kb = _Both()
VIEWS = (("front_neutral", 0, 0), ("q_neutral", 35, 0), ("front_smile", 0, 1), ("q_smile", 35, 1))
if C.get("full_views"):
    VIEWS = VIEWS + (("side_neutral", 90, 0), ("side_smile", 90, 1))
    SH["res"] = (800, 950)
for name, az, val in VIEWS:
    kb.value = val
    args = dict(SH)
    if name.startswith("side"):
        args["target"] = (0.1, 0.035, 1.43)           # room for the whole ponytail; same lens, distance and light
    shot(os.path.join(OUT, name + ".png"), azimuth=az, **args)
if C.get("full_views"):
    dz = C["drop"]
    kb.value = 0
    shot(os.path.join(OUT, "eyes.png"), target=(0, EY, EZ - dz + 0.004), dist=0.68, azimuth=0, lens=85, res=(1200, 640))
    M_ = (0, M["y"], M["z"] - dz)
    shot(os.path.join(OUT, "mouth_neutral.png"), target=M_, dist=0.5, azimuth=0, lens=85, res=(800, 560))
    kb.value = 1
    shot(os.path.join(OUT, "mouth_smile.png"), target=M_, dist=0.5, azimuth=0, lens=85, res=(800, 560))
print("CONCEPT DONE", NAME)
