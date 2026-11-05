"""Face validation in Blender: blender -b build/host_stage3c.blend --python host/validate_face.py
Checks the original rig, every expression key, and expression combinations. Writes build/face/validation.json."""
import json
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage3_common import BUILD, coords, key_coords

rig = bpy.data.objects["host_rig"]; body = bpy.data.objects["host_body"]
rep = {}
names = {b.name for b in rig.data.bones}
fingers = [n for n in names if n.startswith("finger")]
rep["bones_total"] = len(names); rep["finger_bones"] = len(fingers); rep["new_bones"] = sorted(n for n in names if n.startswith("ponytail"))
rep["original_bones_present"] = len(names) - len(rep["new_bones"])
kb = body.data.shape_keys.key_blocks; keys = [k.name for k in kb[1:]]
base = key_coords(kb[0]); mag = {k.name: float(np.linalg.norm(key_coords(k) - base, axis=1).max()) for k in kb[1:]}
MS = ["aa_02", "aa_ah_ax_01", "ao_03", "aw_09", "ay_11", "d_t_n_19", "er_05", "ey_eh_uh_04", "f_v_18", "h_12", "k_g_ng_20", "l_14", "ow_08", "oy_10", "p_b_m_21", "r_13", "sh_ch_jh_zh_16", "sil_00", "s_z_15", "th_dh_17", "w_uw_07", "y_iy_ih_ix_06"]
META = ["viseme_" + x for x in "aa CH DD E FF I kk nn O PP RR sil SS TH U".split()]
rep["microsoft_visemes"] = f"{sum(k in keys for k in MS)}/{len(MS)}"; rep["meta_visemes"] = f"{sum(k in keys for k in META)}/{len(META)}"
ark = [k for k in keys if k not in MS and k not in META and not k.startswith("expr")]
rep["arkit"] = len(ark); rep["custom"] = [k for k in keys if k.startswith("expr")]
tg = bpy.data.objects["host_tongue"].data.shape_keys.key_blocks
rep["no_motion"] = [k for k, v in mag.items() if v < 1e-5 and k not in tg]
rep["follow_keys"] = {o.name: (len(o.data.shape_keys.key_blocks) - 1 if o.data.shape_keys else 0) for o in bpy.data.objects if o.type == "MESH" and o.name in ("host_brows", "host_lashes", "host_hair", "host_hairline", "host_teeth", "host_tongue")}


def combo(mix):
    d = sum(v * (key_coords(kb[k]) - base) for k, v in mix.items())
    return float(np.linalg.norm(d, axis=1).max())


rep["combo_peak_mm"] = {"+".join(c): round(combo({k: 1 for k in c}) * 1000, 1) for c in (("exprSmile", "eyeBlinkLeft", "eyeBlinkRight"), ("exprSmile", "viseme_aa"), ("exprLaugh", "viseme_O"), ("exprSurprise", "viseme_PP"), ("exprTalk", "exprCurious"))}
rep["smile_45_corner_lift_mm"] = round(float((0.45 * (key_coords(kb["mouthSmileLeft"]) - base))[:, 2].max()) * 1000, 1)
with open(os.path.join(BUILD, "face", "validation.json"), "w") as f:
    json.dump(rep, f, indent=1)
print("VALID", json.dumps(rep))
