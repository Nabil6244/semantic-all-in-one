"""Assemble the whole-body stage for the Health Cinema body-map scenes from the models that are already prepared (no download).

All the prepared GLBs come from one Z-Anatomy body and share one world frame (metres, Z up, front -Y), so they can be put into one file without moving anything:
  chest.glb  -> Layer_Skin (whole-body shell), Layer_Muscle, Layer_Lungs, Layer_Heart, Layer_Vessels
  msk.glb    -> Layer_Skeleton (277 bones, whole body), Layer_Discs, Layer_Ligaments
Output: body.glb + anchors_body.json (region anchors measured from the skin shell and the skeleton's joints, so they sit on real positions).
Usage: python3 prep_body.py [bench_dir]"""
from __future__ import annotations
import json, struct, sys
from pathlib import Path
import numpy as np

# (model, {layer in that model: layer name in the body}); a layer a model shares with another (Skeleton, Vessels) is taken from one model only, or renamed
PARTS = (("chest.glb", {"Layer_Skin": "Layer_Skin", "Layer_Muscle": "Layer_Muscle", "Layer_Lungs": "Layer_Lungs", "Layer_Heart": "Layer_Heart", "Layer_Vessels": "Layer_Vessels"}),
         ("msk.glb", {"Layer_Skeleton": "Layer_Skeleton", "Layer_Discs": "Layer_Discs", "Layer_Ligaments": "Layer_Ligaments"}),
         ("abdomen.glb", {"Layer_Liver": "Layer_Liver", "Layer_Pancreas": "Layer_Pancreas", "Layer_Spleen": "Layer_Spleen", "Layer_Stomach": "Layer_Stomach", "Layer_Intestines": "Layer_Intestines",
                          "Layer_Bladder": "Layer_Bladder", "Layer_Urinary": "Layer_Urinary", "Layer_Vessels": "Layer_AbdVessels"}),
         ("head.glb", {"Layer_Cortex": "Layer_Cortex", "Layer_Cerebellum": "Layer_Cerebellum", "Layer_Eyes": "Layer_Eyes", "Layer_Arteries": "Layer_HeadArteries"}))
COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

def read_glb(p):
    b = Path(p).read_bytes(); jl = struct.unpack("<I", b[12:16])[0]; j = json.loads(b[20:20 + jl]); o = 20 + jl; bl = struct.unpack("<I", b[o:o + 4])[0]
    return j, b[o + 8:o + 8 + bl]

def merge(parts, out):
    """parts: [(glb path, {root name: new name})] -> one GLB; only the data the kept roots use is copied."""
    new = {"asset": {"version": "2.0", "generator": "health_cinema prep_body"}, "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [], "materials": [], "accessors": [], "bufferViews": [], "buffers": [{}]}
    blob = bytearray(); mats = {}
    for path, keep in parts:
        j, bn = read_glb(path); maps = {"node": {}, "mesh": {}, "acc": {}, "bv": {}, "mat": {}}
        def bv(i):
            if i in maps["bv"]: return maps["bv"][i]
            v = dict(j["bufferViews"][i]); off = v.get("byteOffset", 0)
            while len(blob) % 4: blob.append(0)
            v["byteOffset"] = len(blob); blob.extend(bn[off:off + v["byteLength"]]); v["buffer"] = 0; new["bufferViews"].append(v); maps["bv"][i] = len(new["bufferViews"]) - 1; return maps["bv"][i]
        def acc(i):
            if i in maps["acc"]: return maps["acc"][i]
            a = dict(j["accessors"][i]); a["bufferView"] = bv(a["bufferView"]); new["accessors"].append(a); maps["acc"][i] = len(new["accessors"]) - 1; return maps["acc"][i]
        def mat(i):
            key = (path, i)
            if key not in mats: m = dict(j["materials"][i]); new["materials"].append(m); mats[key] = len(new["materials"]) - 1
            return mats[key]
        def mesh(i):
            if i in maps["mesh"]: return maps["mesh"][i]
            m = json.loads(json.dumps(j["meshes"][i]))
            for pr in m["primitives"]:
                pr["attributes"] = {k: acc(v) for k, v in pr["attributes"].items()}
                if "indices" in pr: pr["indices"] = acc(pr["indices"])
                if "material" in pr: pr["material"] = mat(pr["material"])
            new["meshes"].append(m); maps["mesh"][i] = len(new["meshes"]) - 1; return maps["mesh"][i]
        def node(i):
            n = dict(j["nodes"][i]); ch = n.pop("children", None)
            if "mesh" in n: n["mesh"] = mesh(n["mesh"])
            new["nodes"].append(n); k = len(new["nodes"]) - 1
            if ch: n["children"] = [node(c) for c in ch]
            return k
        for r in j["scenes"][j.get("scene", 0)]["nodes"]:
            nm = j["nodes"][r].get("name")
            if nm in keep: k = node(r); new["nodes"][k]["name"] = keep[nm]; new["scenes"][0]["nodes"].append(k)
    while len(blob) % 4: blob.append(0)
    new["buffers"][0]["byteLength"] = len(blob)
    js = json.dumps(new, separators=(",", ":")).encode(); js += b" " * (-len(js) % 4)
    Path(out).write_bytes(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(blob)) + struct.pack("<I", len(js)) + b"JSON" + js + struct.pack("<I", len(blob)) + b"BIN\0" + bytes(blob))
    return new

def layer_vertices(glb_path, layer):
    """All vertices of a Layer_* group in the BLENDER frame (x, y, z up), nodes' own transforms assumed identity (as the prepared files are)."""
    j, bn = read_glb(glb_path); out = []
    def walk(i):
        n = j["nodes"][i]
        if "mesh" in n:
            for pr in j["meshes"][n["mesh"]]["primitives"]:
                a = j["accessors"][pr["attributes"]["POSITION"]]; v = j["bufferViews"][a["bufferView"]]; off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
                arr = np.frombuffer(bn, COMP[a["componentType"]], a["count"] * NCOMP[a["type"]], off).reshape(-1, NCOMP[a["type"]]); out.append(arr)
        for c in n.get("children", []): walk(c)
    for r in j["scenes"][0]["nodes"]:
        if j["nodes"][r].get("name") == layer: walk(r)
    v = np.concatenate(out); return np.stack([v[:, 0], -v[:, 2], v[:, 1]], 1)      # three (x, y up, z) -> Blender (x, -z, y)

def box(pts, pad=0.0):
    lo, hi = pts.min(0) - pad, pts.max(0) + pad; return {"min": [round(float(x), 4) for x in lo], "max": [round(float(x), 4) for x in hi], "center": [round(float((a + b) / 2), 4) for a, b in zip(lo, hi)]}

def regions(skin, A):
    """Region boxes (Blender frame) from the skin shell, cut at the skeleton's joints. Left = +X (the body's left, the viewer's right when facing the front)."""
    c = lambda n: np.array(A[n]["center"]); out = {}
    zmin, zmax = skin[:, 2].min(), skin[:, 2].max()
    def cut(x0, x1, z0, z1, y0=-9, y1=9): m = (skin[:, 0] >= x0) & (skin[:, 0] <= x1) & (skin[:, 2] >= z0) & (skin[:, 2] <= z1) & (skin[:, 1] >= y0) & (skin[:, 1] <= y1); return skin[m]
    out["body"] = box(skin); out["head"] = box(cut(-1, 1, 1.52, zmax + 1))
    # neck: the narrowest ring of the shell between the shoulders and the chin
    zs = np.linspace(1.42, 1.58, 33); w = [np.ptp(cut(-1, 1, z, z + 0.005)[:, 0]) if len(cut(-1, 1, z, z + 0.005)) else 9 for z in zs]; zn = float(zs[int(np.argmin(w))])
    out["neck"] = box(cut(-1, 1, zn - 0.04, zn + 0.05))
    out["chest"] = A["chest"]; out["abdomen"] = box(cut(-0.2, 0.2, 0.9, 1.1)); out["pelvis"] = box(cut(-0.25, 0.25, c("hip_l")[2] - 0.12, c("hip_l")[2] + 0.06))
    for side in ("l", "r"):
        sh, el, wr = c(f"shoulder_{side}"), c(f"elbow_{side}"), c(f"wrist_{side}")
        out[f"upper_arm_{side}"] = box(cut(min(sh[0], el[0]) - 0.05, max(sh[0], el[0]) + 0.05, el[2], sh[2]))
        out[f"forearm_{side}"] = box(cut(min(el[0], wr[0]) - 0.05, max(el[0], wr[0]) + 0.05, wr[2], el[2]))
        out[f"hand_{side}"] = box(cut(wr[0] - 0.08, wr[0] + 0.08, wr[2] - 0.22, wr[2]))
        hip, kn = c(f"hip_{side}"), c(f"knee_{side}")
        out[f"thigh_{side}"] = box(cut(min(hip[0], kn[0]) - 0.09, max(hip[0], kn[0]) + 0.09, kn[2], hip[2]))
        out[f"shin_{side}"] = box(cut(kn[0] - 0.08, kn[0] + 0.08, 0.1, kn[2]))
        out[f"foot_{side}"] = box(cut(kn[0] - 0.09, kn[0] + 0.09, zmin, 0.1))
    for k, v in A.items():
        if k not in out: out[k] = v
    return out

def surface_point(skin, b, y_front=True):
    """The point on the skin shell facing the camera (front, -Y) at the middle of a region box: where a lesion or a card pin sits."""
    cx, cz = b["center"][0], b["center"][2]; m = (abs(skin[:, 0] - cx) < 0.012) & (abs(skin[:, 2] - cz) < 0.012)
    return [round(cx, 4), round(float(skin[m][:, 1].min()), 4), round(cz, 4)] if m.any() else [round(cx, 4), round(b["min"][1], 4), round(cz, 4)]

def main(bench: Path):
    glbs = [(bench / n, keep) for n, keep in PARTS]; out = bench / "body.glb"; merge(glbs, out)
    skin = layer_vertices(out, "Layer_Skin"); A = {}
    for n in ("anchors.json", "anchors_msk.json", "anchors_head.json", "anchors_abdomen.json"):
        d = json.loads((bench / n).read_text())["anchors"]
        for k, v in d.items():
            if not k.startswith("obj:") and k not in A: A[k] = v
    R = regions(skin, A)
    for k in [k for k in R if k.rsplit("_", 1)[0] in ("forearm", "upper_arm", "hand", "thigh", "shin", "foot")]: R[k]["surface"] = surface_point(skin, R[k])
    layers = {}
    for f, (n, ks) in zip(("anchors.json", "anchors_msk.json", "anchors_abdomen.json", "anchors_head.json"), PARTS):
        for old, new in ks.items():
            if old in (src := json.loads((bench / f).read_text())["layers"]): layers[new] = src[old]
    j, _ = read_glb(out)
    (bench / "anchors_body.json").write_text(json.dumps({"anchors": R, "layers": layers, "frame": "blender_z_up_metres", "left": "+x"}, indent=1))
    print("body.glb", out.stat().st_size // 1024, "KB;", len(R), "anchors;", [n["name"] for n in (j["nodes"][i] for i in j["scenes"][0]["nodes"])])

if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "HealthCinemaTools" / "bench")
