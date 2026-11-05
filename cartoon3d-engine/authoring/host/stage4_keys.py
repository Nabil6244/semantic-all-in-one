"""Stage 4 (lean): stronger FF and TH, brow keys, surprise and curious, brows in smile/laugh. Renders the Gate 4 shots and exports the GLB.
Run: blender -b -noaudio build/revisions/g2_gate3/stage3_g2.blend --python host/stage4_keys.py -- k1
Reads the frozen Gate 3 file, writes only to build/stage4/<tag>/ and build/stage4/stage4_<tag>.blend."""
import json
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD, portrait_lights, shot

TAG = sys.argv[sys.argv.index("--") + 1]
OUT = os.path.join(BUILD, "stage4", TAG); os.makedirs(OUT, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
s = bpy.context.scene
MOUTH = [bpy.data.objects[n] for n in ("cand_head", "cand_mouth", "cand_teeth_up", "cand_teeth_low", "cand_tongue")]
HEAD, TONGUE, BROWS = MOUTH[0], MOUTH[4], bpy.data.objects["concept_brows"]


def K(o, name):
    kb = o.data.shape_keys.key_blocks[name]; a = np.zeros(len(kb.data) * 3); kb.data.foreach_get("co", a); return a.reshape(-1, 3)


def setkey(o, name, arr):
    if not o.data.shape_keys:
        o.shape_key_add(name="Basis", from_mix=False)
    kb = o.data.shape_keys.key_blocks.get(name) or o.shape_key_add(name=name, from_mix=False)
    kb.data.foreach_set("co", arr.astype(np.float32).ravel()); kb.value = 0


def combo(o, mix):
    """Basis + sum of weighted deltas of existing keys (keys the mesh lacks are skipped)."""
    b = K(o, "Basis"); r = b.copy(); names = o.data.shape_keys.key_blocks.keys()
    for n, w in mix.items():
        if n in names:
            r += w * (K(o, n) - b)
    return r


def apply_keys(v):
    for o in bpy.data.objects:
        if o.type == "MESH" and o.data.shape_keys:
            for k in o.data.shape_keys.key_blocks[1:]:
                k.value = v.get(k.name, 0)


s.render.engine = "BLENDER_EEVEE"; s.render.film_transparent = True
for kx, vx in (("use_raytracing", True), ("taa_render_samples", 24)):
    if hasattr(s.eevee, kx):
        setattr(s.eevee, kx, vx)
portrait_lights()
SHOTS = json.load(open(os.path.join(HERE, "stage4_shots.json")))
for sh in SHOTS:                                  # the old FF and TH, for the before/after
    if sh["name"] in ("c_FF", "c_TH", "q_FF", "q_TH"):
        apply_keys(sh["keys"]); shot(os.path.join(OUT, "before_" + sh["name"] + ".png"), target=sh["target"], dist=sh["dist"], azimuth=sh["az"], lens=85, res=(600, 712))

# ---- FF: upper teeth rest on the lower lip. Built from the clean SS parting, with the lower lip raised to the teeth and tucked a little
b = K(HEAD, "Basis"); dss = K(HEAD, "viseme_SS") - b
lowm = np.clip(-dss[:, 2] / (-dss[:, 2]).max(), 0, 1)[:, None]     # smooth lower-lip field, no thresholds
setkey(HEAD, "viseme_FF", b + 0.75 * dss + lowm * np.array([0, 0.003, 0.75 * 0.0052 + 0.0025]))

# ---- TH: wider parting, tongue tip forward between the teeth
for o in MOUTH:
    bo = K(o, "Basis"); do = K(o, "viseme_TH") - bo
    if o is TONGUE:
        y = bo[:, 1]; tip = np.clip((y.max() - y) / (y.max() - y.min()), 0, 1) ** 2
        setkey(o, "viseme_TH", bo + 1.3 * do + tip[:, None] * np.array([0, -0.007, -0.001]))
    elif o.name != "cand_teeth_up":
        setkey(o, "viseme_TH", bo + 1.3 * do)

# ---- surprise and curious from tested keys
for o in MOUTH:
    sm = {"jawOpen": 0.45, "viseme_O": 0.5}; cm = {"smile": 0.22, "viseme_U": 0.18}
    if o is HEAD:
        sm.update(eyeBlinkLeft=-0.2, eyeBlinkRight=-0.2)                # lids open wider
        cm.update(eyeBlinkRight=0.15, eyeBlinkArcRight=4 * 0.15 * 0.85)  # her right eye narrows a little
    setkey(o, "surprise", combo(o, sm)); setkey(o, "curious", combo(o, cm))

# ---- brows: slide over the forehead, keeping their height above the skin
hp = K(HEAD, "Basis"); bvh = BVHTree.FromPolygons([tuple(p) for p in hp], [tuple(p.vertices) for p in HEAD.data.polygons])
bb = np.array([v.co for v in BROWS.data.vertices]); side = np.sign(bb[:, 0])
u = np.zeros(len(bb))
for sg in (1, -1):
    m = side == sg; ax = np.abs(bb[m, 0]); u[m] = (ax - ax.min()) / (ax.max() - ax.min())     # 0 inner end, 1 outer end
base = []
for p in bb:
    loc, nrm, _, _ = bvh.find_nearest(Vector(p)); base.append((p - np.array(loc)) @ np.array(nrm))
base = np.array(base)


def brow(L=None, R=None):
    """L/R: (inner dz, outer dz, inner dx toward the nose) for her left (+x) and right brows, in metres."""
    r = bb.copy()
    for sg, prm in ((1, L), (-1, R)):
        if not prm:
            continue
        m = side == sg; iz, oz, ix = prm
        r[m, 2] += iz * (1 - u[m]) + oz * u[m]; r[m, 0] -= sg * ix * (1 - u[m])
    for i in range(len(r)):                       # back onto the skin
        loc, nrm, _, _ = bvh.find_nearest(Vector(r[i])); r[i] = np.array(loc) + np.array(nrm) * base[i]
    return r


BK = {"browInnerUp": dict(L=(.011, .002, 0), R=(.011, .002, 0)), "browOuterUpLeft": dict(L=(.002, .011, 0)), "browOuterUpRight": dict(R=(.002, .011, 0)),
      "browDownLeft": dict(L=(-.005, -.0015, .003)), "browDownRight": dict(R=(-.005, -.0015, .003)),
      "smile": dict(L=(.0015, .0015, 0), R=(.0015, .0015, 0)), "laugh": dict(L=(.0035, .0025, 0), R=(.0035, .0025, 0)),
      "surprise": dict(L=(.011, .009, 0), R=(.011, .009, 0)), "curious": dict(L=(.009, .013, 0), R=(-.003, -.0005, .002))}
for n, prm in BK.items():
    setkey(BROWS, n, brow(**prm))
print("REPORT keys head", len(HEAD.data.shape_keys.key_blocks) - 1, "brows", len(BROWS.data.shape_keys.key_blocks) - 1)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BUILD, "stage4", f"stage4_{TAG}.blend"), copy=True)

# ---- GLB (same export as Stage 3)
EXPORT = ["cand_head", "cand_mouth", "cand_teeth_up", "cand_teeth_low", "cand_tongue", "concept_eyes", "concept_brows", "concept_band", "concept_tie", "host_hair_low",
          "host_body", "host_shoes", "host_tee", "host_overalls", "host_pocket", "host_strap_L", "host_strap_R", "host_buttons", "host_stitch"]
for o in bpy.context.selected_objects:
    o.select_set(False)
bpy.data.objects["host_rig"].select_set(True)
for n in EXPORT:
    bpy.data.objects[n].select_set(True)
glb = os.path.join(OUT, "host.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=False, export_skins=True, export_all_influences=False,
                          export_morph=True, export_morph_normal=True, export_try_sparse_sk=True, export_animations=False, export_image_format="AUTO", export_yup=True)
print("REPORT glb KB", os.path.getsize(glb) // 1024)

for sh in SHOTS:
    apply_keys(sh.get("keys", {}))
    shot(os.path.join(OUT, sh["name"] + ".png"), target=sh["target"], dist=sh["dist"], azimuth=sh["az"], lens=85, res=(600, 712))
print("STAGE4 DONE")
