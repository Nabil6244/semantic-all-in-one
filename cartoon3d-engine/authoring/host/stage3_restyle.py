"""Stage 3a: turn the Stage 2 host into the soft cartoon look. Opens host_stage2.blend, saves host_stage3a.blend (Stage 2 untouched).
Run: blender -b build/host_stage2.blend --python host/stage3_restyle.py -- [--preview]
One smooth warp W moves the skin, every shape key, the face parts and the head bones together, so rig and expressions survive.
Build keys (body macros, face shaping) are baked into the rest shape; MPFB can no longer refit after this step."""
import importlib
import math
import os
import sys

import bmesh
import bpy
import mathutils
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD, TEX, coords, key_coords, material, one_material, set_coords, shot, studio

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HEAD_SCALE, EYEBALL, EYE_SPREAD = 1.46, 1.68, 0.0063
NOSE_BACK, NOSE_NARROW, JAW_TAPER, HEAD_DROP = 0.013, 0.2, 0.10, 0.006
MOUTH_WIDE, REST_SMILE, REST_WIDE, SMILE_GAIN, EYE_SINK = 1.20, 0.42, 0.3, 1.45, 0.0038
PIVOT = np.array([0.0, -0.045, 1.345])
USER_DATA = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/.user/user_default/mpfb/data")
HS = importlib.import_module("bl_ext.user_default.mpfb.services.humanservice").HumanService

body = bpy.data.objects["host_body"]; rig = bpy.data.objects["host_rig"]
shoes = HS.add_mhclo_asset(os.path.join(USER_DATA, "clothes/shoes05/shoes05.mhclo"), body, asset_type="Clothes", subdiv_levels=0, material_type="MAKESKIN")
shoes.name = "host_shoes"
bpy.data.objects.remove(bpy.data.objects["host_body.ponytail01"])   # flat strips: replaced by stage3_hair.py
parts = {n: bpy.data.objects[f"host_body.{n}"] for n in ("eyebrow010", "eyelashes02", "high-poly", "teeth_base", "tongue01")}
for o in [*parts.values(), shoes]:
    for m in list(o.modifiers):
        if m.type == "SUBSURF":
            o.modifiers.remove(m)
    print("REPORT part", o.name, "world identity:", o.matrix_world.is_identity if hasattr(o.matrix_world, "is_identity") else o.matrix_world)

# the eye asset is two shells per eye: iris sphere + a clear cornea. Keep the iris sphere only (one opaque glossy surface, glTF-safe).
eo = parts["high-poly"]; bm = bmesh.new(); bm.from_mesh(eo.data); bm.verts.ensure_lookup_table()
seen, isl = set(), []
for v in bm.verts:
    if v in seen:
        continue
    st, grp = [v], []
    seen.add(v)
    while st:
        a = st.pop(); grp.append(a)
        for e in a.link_edges:
            b = e.other_vert(a)
            if b not in seen:
                seen.add(b); st.append(b)
    isl.append(grp)
drop = [min((g for g in isl if g[0].co.x * sgn > 0), key=lambda g: min(v.co.y for v in g)) for sgn in (1, -1)]
bmesh.ops.delete(bm, geom=drop[0] + drop[1], context="VERTS")
bm.to_mesh(eo.data); bm.free()

# --- bake build keys into the rest shape
kbs = body.data.shape_keys.key_blocks
names = [k.name for k in kbs]
first_expr = names.index("aa_02")
basis = key_coords(kbs[0]); rest = basis.copy()
for k in kbs[1:first_expr]:
    rest += k.value * (key_coords(k) - basis)
expr = {k.name: key_coords(k) - basis for k in kbs[first_expr:]}
rest += REST_SMILE * (expr["mouthSmileLeft"] + expr["mouthSmileRight"])   # a resting warmth, not a blank face
rest += REST_WIDE * (expr["eyeWideLeft"] + expr["eyeWideRight"])           # bright awake eyes
for n in ("mouthSmileLeft", "mouthSmileRight"):
    expr[n] = expr[n] * SMILE_GAIN                  # the source key is shy: 45% must read on camera

# --- head mask from skin weights (head bone and everything under it)
fam = {"head"} | {c.name for c in rig.data.bones["head"].children_recursive}
idx = {g.index for g in body.vertex_groups if g.name in fam}
mask = np.array([sum(g.weight for g in v.groups if g.group in idx) for v in body.data.vertices])
ed = np.zeros(len(body.data.edges) * 2, int); body.data.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
for _ in range(6):
    acc = np.zeros_like(mask); cnt = np.zeros_like(mask)
    np.add.at(acc, ed[:, 0], mask[ed[:, 1]]); np.add.at(acc, ed[:, 1], mask[ed[:, 0]]); np.add.at(cnt, ed.ravel(), 1)
    mask = np.where(cnt > 0, 0.5 * mask + 0.5 * acc / np.maximum(cnt, 1), mask)
mask = np.clip(mask, 0, 1)

# --- face landmarks, measured on this body
eye = coords(parts["high-poly"].data)
ec = []
for s in (1, -1):
    e = eye[eye[:, 0] * s > 0]; r = (e[:, 2].max() - e[:, 2].min()) / 2
    ec.append(np.array([(e[:, 0].max() + e[:, 0].min()) / 2, e[:, 1].min() + (e[:, 0].max() - e[:, 0].min()) / 2, (e[:, 2].max() + e[:, 2].min()) / 2]))
print("REPORT eye centres", ec, "radius", r)
hm = (mask > 0.9) & (np.abs(rest[:, 0]) < 0.004)
tip = rest[hm][np.argmin(rest[hm][:, 1])]
mi = np.zeros(len(body.data.polygons), int); body.data.polygons.foreach_get("material_index", mi)
lip_v = np.unique([v for p, m in zip(body.data.polygons, mi) if body.data.materials[m].name.endswith(".lips") for v in p.vertices])
mouth = rest[lip_v].mean(0)
print("REPORT nose tip", tip, "mouth", mouth)
EZ = ec[0][2]
R2, LID_GAP, RED_LINE = 0.0148 * EYEBALL, 0.0012, 0.34
eye_front = eye[:, 1].min()
EYE_BACK = (eye_front - ec[0][1]) * (1 - EYEBALL) + EYE_SINK  # sphere grows backwards, and sits deeper so lids stay flush with the face


def fall(d, r0, r1):
    t = np.clip((r1 - d) / (r1 - r0), 0, 1)
    return t * t * (3 - 2 * t)


# Monotone remaps (original -> cartoon), so nothing can fold: heights of the face features, and width across the eyes.
ZMAP = ([1.30, 1.335, 1.384, 1.398, 1.41, 1.4435, 1.4575, 1.478, 1.50, 1.559, 1.60],
        [1.30, 1.350, 1.3855, 1.3955, 1.408, 1.432, 1.469, 1.491, 1.508, 1.559, 1.60])
XMAP = ([0, 0.0147, 0.0417, 0.07, 0.10, 0.2], [0, 0.0118, 0.0572, 0.0765, 0.10, 0.2])


def smooth_map(pts, sigma):
    g = np.linspace(pts[0][0] - 0.05, pts[0][-1] + 0.05, 1600)
    f = np.interp(g, *pts); f = np.where(g < pts[0][0], g, np.where(g > pts[0][-1], g, f))
    k = np.exp(-0.5 * ((np.arange(-60, 61) * (g[1] - g[0])) / sigma) ** 2); k /= k.sum()
    return g, np.convolve(np.pad(f - g, 60, mode="edge"), k, "valid") + g


GZ, FZ = smooth_map(ZMAP, 0.0028)
GX, FX = smooth_map(XMAP, 0.0028)


def warp(P, m, lining=None):
    """P: (n,3) rest-space points, m: (n,) head mask. Returns warped points."""
    Q = P.copy()
    band = np.exp(-((P[:, 2] - EZ) / 0.034) ** 2)
    front = fall(P[:, 1], -0.105, 0.012)
    Q[:, 0] += np.sign(P[:, 0]) * (np.interp(np.abs(P[:, 0]), GX, FX) - np.abs(P[:, 0])) * band * front
    Q[:, 2] += (np.interp(P[:, 2], GZ, FZ) - P[:, 2]) * front
    mb = np.exp(-(np.linalg.norm((P - mouth) / np.array([1.35, 1, 1]), axis=1) / 0.034) ** 2)
    Q[:, 0] += P[:, 0] * (MOUTH_WIDE - 1) * mb       # wider, friendlier mouth
    for s_ in (1, -1):                              # full round cheeks
        g = np.exp(-(np.linalg.norm(P - np.array([s_ * 0.07, -0.095, EZ - 0.05]), axis=1) / 0.042) ** 2)
        Q[:, 0] += g * s_ * 0.0055; Q[:, 1] -= g * 0.0035
    for c in ec:                                    # lids lie exactly on the larger eyeball, open or blinking
        dist = np.linalg.norm(P - c, axis=1)
        near = fall(dist, 0.021, 0.046)
        Q[:, 1] += near * ((P[:, 1] - eye_front) * (EYEBALL - 1) + EYE_SINK)   # same depth curve as the bigger, deeper eyeball
        c2 = c + np.array([np.sign(c[0]) * EYE_SPREAD, EYE_BACK, 0])
        rr = np.clip((Q[:, 0] - c2[0]) ** 2 + (Q[:, 2] - c2[2]) ** 2, 0, (R2 * 0.985) ** 2)
        on_ball = c2[1] - np.sqrt(R2 ** 2 - rr)
        hit = (dist < 0.036) & (Q[:, 0] * c[0] > 0)
        if lining is not None:                       # socket lining goes behind the ball; skin only ever moves forward, never tears
            Q[:, 1] = np.where(hit & lining, on_ball + 0.005, Q[:, 1])
            hit = hit & ~lining
        Q[:, 1] = np.where(hit, np.minimum(Q[:, 1], on_ball - LID_GAP), Q[:, 1])
    r = np.linalg.norm((P - (tip + np.array([0, 0.008, 0.004]))) / np.array([1, 1, 1.15]), axis=1)
    g = np.exp(-(r / 0.024) ** 2)                   # small soft nose: pull the tip in, narrow it
    Q[:, 1] += g * NOSE_BACK
    Q[:, 0] -= Q[:, 0] * g * NOSE_NARROW
    taper = np.clip((EZ - 0.02 - P[:, 2]) / 0.095, 0, 1)   # soft narrowing towards a small round chin
    Q[:, 0] -= Q[:, 0] * JAW_TAPER * (taper * taper * (3 - 2 * taper)) * m
    Q[:, 2] -= HEAD_DROP * m
    Q = np.where(m[:, None] > 0, P + (Q - P) * m[:, None], P)
    Q += ((PIVOT + (Q - PIVOT) * HEAD_SCALE) - Q) * m[:, None]
    return Q


# socket lining = the red-toned faces around each eye in the skin texture
src = bpy.data.images.load(os.path.join(USER_DATA, "skins/young_caucasian_female/young_lightskinned_female_diffuse.png"), check_existing=True)
Wd, Hd = src.size; px = np.zeros(Wd * Hd * 4, np.float32); src.pixels.foreach_get(px); px = px.reshape(Hd, Wd, 4)
me = body.data; uvs = np.zeros(len(me.loops) * 2); me.uv_layers.active.data.foreach_get("uv", uvs); uvs = uvs.reshape(-1, 2)
lv = np.zeros(len(me.loops), int); me.loops.foreach_get("vertex_index", lv)
col = px[np.clip((uvs[:, 1] * Hd).astype(int), 0, Hd - 1), np.clip((uvs[:, 0] * Wd).astype(int), 0, Wd - 1)]
red = np.zeros(len(me.vertices)); np.maximum.at(red, lv, col[:, 0] - col[:, 1])
LIN = np.zeros(len(rest), bool)
for c in ec:
    LIN |= (np.linalg.norm(rest - c, axis=1) < 0.024) & (red > RED_LINE)
print("REPORT lining verts", LIN.sum(), "red quantiles", np.quantile(red[np.linalg.norm(rest - ec[0], axis=1) < 0.024], [.1, .3, .5, .7, .9]).round(3))
W0 = warp(rest, mask, LIN)
for k in list(kbs)[1:first_expr]:
    body.shape_key_remove(k)
kbs = body.data.shape_keys.key_blocks
# melt any leftover ridge in the warp (temples, cheeks): smooth the displacement, leaving lids and lips exact
disp = W0 - rest; sm = disp.copy()
free = (mask > 0.5) & (np.linalg.norm(rest - mouth, axis=1) > 0.034)
for c in ec:
    free &= np.linalg.norm(rest - c, axis=1) > 0.027
for _ in range(40):
    acc = np.zeros_like(sm); cnt = np.zeros(len(sm))
    np.add.at(acc, ed[:, 0], sm[ed[:, 1]]); np.add.at(acc, ed[:, 1], sm[ed[:, 0]]); np.add.at(cnt, ed.ravel(), 1)
    sm[free] = 0.5 * sm[free] + 0.5 * acc[free] / np.maximum(cnt[free, None], 1)
corr = sm - disp
Wn = W0 + corr
for c in ec:                                         # smoothing must never let the eyeball show through skin
    Cf = PIVOT + (c + np.array([np.sign(c[0]) * EYE_SPREAD, EYE_BACK, -HEAD_DROP]) - PIVOT) * HEAD_SCALE; Rf = R2 * HEAD_SCALE
    rr = (Wn[:, 0] - Cf[0]) ** 2 + (Wn[:, 2] - Cf[2]) ** 2
    i = (rr < Rf ** 2) & ~LIN & (np.linalg.norm(rest - c, axis=1) < 0.045)
    limit = Cf[1] - np.sqrt(Rf ** 2 - np.minimum(rr[i], 0.97 * Rf ** 2)) - LID_GAP * HEAD_SCALE
    corr[i, 1] += np.minimum(limit - Wn[i, 1], 0)
W0 = W0 + corr
kbs[0].data.foreach_set("co", W0.ravel())
for k in kbs[1:]:
    k.data.foreach_set("co", (warp(rest + expr[k.name], mask, LIN) + corr).ravel())
set_coords(body.data, W0)
def warp_eyeball(P):
    """Spheres stay spheres: uniform scale per eye, then the same head scale as the skin."""
    Q = P.copy()
    for c in ec:
        i = P[:, 0] * c[0] > 0
        Q[i] = c + np.array([np.sign(c[0]) * EYE_SPREAD, EYE_BACK, 0]) + (P[i] - c) * EYEBALL
    Q[:, 2] -= HEAD_DROP
    return PIVOT + (Q - PIVOT) * HEAD_SCALE


def build_eyeballs(o):
    """The asset's iris shell has a hole at the pupil. Replace it with clean spheres, UV-planar from the front, skinned to the eye bones."""
    bm = bmesh.new(); uv = bm.loops.layers.uv.new("UVMap")
    groups = []
    for c in ec:
        centre = warp_eyeball(c[None])[0]; R = R2 * HEAD_SCALE
        r = bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=24, radius=R)
        bmesh.ops.rotate(bm, verts=r["verts"], cent=(0, 0, 0), matrix=mathutils.Matrix.Rotation(math.pi / 2, 3, "X"))
        bmesh.ops.translate(bm, verts=r["verts"], vec=centre)
        groups.append((r["verts"], "eye.L" if c[0] > 0 else "eye.R"))
        for v in r["verts"]:
            for f in v.link_faces:
                f.smooth = True
                for l in f.loops:
                    if l.vert is v:
                        l[uv].uv = (0.5 + (v.co.x - centre[0]) / (2 * R), 0.5 + (v.co.z - centre[2]) / (2 * R))
    ids = [[v.index for v in g] for g, _ in groups] if bm.verts.index_update() is None else None
    bm.to_mesh(o.data); bm.free()
    for g in list(o.vertex_groups):
        o.vertex_groups.remove(g)
    for (_, name), i in zip(groups, ids):
        o.vertex_groups.new(name=name).add(i, 1.0, "REPLACE")


for n, o in parts.items():
    if n == "high-poly":
        build_eyeballs(o)
    else:
        p = warp(coords(o.data), np.ones(len(o.data.vertices)))
        if n in ("teeth_base", "tongue01"):           # stay inside the lips at full stretch
            p[:, 0] *= 0.8; p[:, 1] += 0.008
        set_coords(o.data, p)

bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for eb in rig.data.edit_bones:
    if eb.name in fam:
        q = np.array([eb.head, eb.tail], float)
        q = warp_eyeball(q) if eb.name in ("eye.L", "eye.R") else warp(q, np.ones(2))
        eb.head, eb.tail = q[0], q[1]
bpy.ops.object.mode_set(mode="OBJECT")

# --- plain glTF materials
skin = material("skin", os.path.join(TEX, "skin.png"), normal=os.path.join(TEX, "skin_n.png"), nstrength=0.35, roughtex=os.path.join(TEX, "skin_r.png"))
one_material(body, skin)
one_material(parts["high-poly"], material("eye", os.path.join(TEX, "eye.png"), rough=0.32))
one_material(parts["eyebrow010"], material("brow", os.path.join(TEX, "brow.png"), rough=0.7, alpha=True))
one_material(parts["eyelashes02"], material("lash", os.path.join(TEX, "lash.png"), rough=0.6, alpha=True))
for n, t in (("teeth_base", "teeth/teeth_base/teeth.png"), ("tongue01", "tongue/tongue01/tongue01_diffuse.png")):
    one_material(parts[n], material(n, os.path.join(TEX, "teeth.png") if n == "teeth_base" else os.path.join(USER_DATA, t), rough=0.3))
one_material(shoes, material("shoes", os.path.join(TEX, "shoes.png"), rough=0.7))
names = {"eyebrow010": "host_brows", "eyelashes02": "host_lashes", "high-poly": "host_eyes", "teeth_base": "host_teeth", "tongue01": "host_tongue"}
for k, v in names.items():
    parts[k].name = v
np.save(os.path.join(BUILD, "head_mask.npy"), mask); np.save(os.path.join(BUILD, "eye_lining.npy"), LIN); np.save(os.path.join(BUILD, "lip_verts.npy"), lip_v)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "host_stage3a.blend"))
print("REPORT keys kept", len(kbs) - 1, "height", W0[:, 2].max(), "SAVED")
if "--preview" in ARGS:
    studio()
    hz = float(rig.data.bones["head"].head_local.z) + 0.06
    bpy.data.objects["host_shoes"].hide_render = True
    for tag, az in (("front", 0), ("q", 35)):
        shot(os.path.join(BUILD, f"s3a_{tag}.png"), (0, -0.05, hz), 1.45, az, res=(620, 760))
